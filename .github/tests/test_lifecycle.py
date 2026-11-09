"""Real Git coverage of the branch-only Bump lifecycle; no hosted services."""

import contextlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / ".github/scripts"))
import bump as lifecycle
import source_version as source


@contextlib.contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(path, *args, input=None):
    location = ["--git-dir", str(path)] if path.name.endswith(".git") else ["-C", str(path)]
    return subprocess.run(
        ["git", *location, *args], input=input, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


class BumpTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / f".lifecycle-tests-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.remote = self.root / "remote.git"
        self.local = self.root / "local"
        self.peer = self.root / "peer"
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "init", "-b", "selected", str(self.local))
        for key, value in (("user.name", "Lifecycle Test"), ("user.email", "test@example.invalid"),
                           ("push.followTags", "true")):
            git(self.local, "config", key, value)
        git(self.local, "commit", "--allow-empty", "-m", "ancestor")
        self.ancestor = git(self.local, "rev-parse", "HEAD")
        for path in source.SOURCE_PATHS:
            (self.local / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, self.local / path)
        shutil.copytree(ROOT / ".github/scripts", self.local / ".github/scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "fixture")
        git(self.local, "remote", "add", "origin", str(self.remote))
        git(self.local, "push", "origin", "HEAD:refs/heads/selected")
        self.sha = git(self.local, "rev-parse", "HEAD")
        self.version = source.read(self.local)
        git(self.root, "clone", "--branch", "selected", str(self.remote), str(self.peer))
        git(self.peer, "config", "user.name", "Peer")
        git(self.peer, "config", "user.email", "peer@example.invalid")
        self.enter = cwd(self.local)
        self.enter.__enter__()
        self.addCleanup(self.enter.__exit__, None, None, None)
        self.file_patch = patch.object(lifecycle, "__file__",
                                      str(self.local / ".github/scripts/bump.py"))
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)

    def bump(self):
        lifecycle.bump_branch(self.sha, "refs/heads/selected", "patch")

    def assert_remote(self, sha):
        self.assertEqual(lifecycle.remote_ref("refs/heads/selected"), sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def advance_peer(self):
        (self.peer / "peer.txt").write_text("concurrent branch update")
        git(self.peer, "add", ".")
        git(self.peer, "commit", "-m", "peer")
        git(self.peer, "push", "origin", "HEAD:refs/heads/selected")
        return git(self.peer, "rev-parse", "HEAD")

    def test_explicit_branch_source_trailer_and_no_follow_annotated_tag(self):
        git(self.local, "tag", "-a", "unrelated-annotated", "-m", "must not follow")
        git(self.remote, "update-ref", "refs/heads/other", self.sha)
        with patch.object(lifecycle, "run", wraps=lifecycle.run) as run:
            self.bump()
        new = git(self.local, "rev-parse", "HEAD")
        self.assert_remote(new)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/other"), self.sha)
        self.assertEqual(git(self.local, "rev-list", "--parents", "-n", "1", new),
                         f"{new} {self.sha}")
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(set(git(self.local, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", new).splitlines()), set(map(str, source.SOURCE_PATHS)))
        self.assertIn(lifecycle.TRAILER, git(self.local, "log", "-1", "--format=%B"))
        pushes = [call.args for call in run.call_args_list if "push" in call.args]
        self.assertEqual(len(pushes), 1)
        self.assertIn("push.followTags=false", pushes[0])
        self.assertIn("--no-follow-tags", pushes[0])
        self.assertEqual(pushes[0][-2:], ("origin", f"{new}:refs/heads/selected"))
        self.assertTrue(any(str(arg).startswith("core.hooksPath=") for arg in pushes[0]))
        self.assertEqual(git(self.local, "config", "push.followTags"), "true")
        self.assertEqual(source.read(self.local).split(".")[-1],
                         str(int(self.version.split(".")[-1]) + 1))

    def test_cli_clean_checkout_without_bytecode_environment(self):
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        subprocess.run(
            [sys.executable, ".github/scripts/bump.py", "patch", "--sha", self.sha,
             "--ref", "refs/heads/selected"], env=env, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assert_remote(git(self.local, "rev-parse", "HEAD"))

    def test_cli_detached_checkout_without_configured_identity(self):
        git(self.local, "config", "--local", "--unset-all", "user.name")
        git(self.local, "config", "--local", "--unset-all", "user.email")
        git(self.local, "checkout", "--detach", self.sha)
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_", "GIT_CONFIG_"))
            and key != "EMAIL"
        }
        env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(
            [sys.executable, ".github/scripts/bump.py", "patch", "--sha", self.sha,
             "--ref", "refs/heads/selected"], env=env, check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        identity = "github-actions[bot] <github-actions[bot]@users.noreply.github.com>"
        self.assertEqual(git(self.local, "log", "-1", "--format=%an <%ae>%n%cn <%ce>"),
                         f"{identity}\n{identity}")
        for key in ("user.name", "user.email"):
            result = subprocess.run(
                ["git", "config", "--local", "--get", key], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(result.returncode, 1)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assert_remote(git(self.local, "rev-parse", "HEAD"))

    def test_selected_sha_ref_and_dirty_checkout(self):
        for sha in ("selected", "a" * 40, "a" * 39, "a" * 41):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                lifecycle.selected_sha(sha)
        for ref in ("selected", "refs/tags/v1.0.0", "refs/pull/1/merge", "refs/heads/a..b"):
            with self.subTest(ref=ref), \
                    self.assertRaises((ValueError, subprocess.CalledProcessError)):
                lifecycle.bump_branch(self.sha, ref, "patch")
        (self.local / "dirty").write_text("untracked")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            self.bump()
        self.assert_remote(self.sha)

    def test_initial_remote_moved(self):
        expected = self.advance_peer()
        with self.assertRaisesRegex(ValueError, "moved since"):
            self.bump()
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        self.assert_remote(expected)

    def test_remote_moves_during_preparation(self):
        real_bump = lifecycle.bump

        def concurrent(mode):
            result = real_bump(mode)
            self.advance_peer()
            return result

        with patch.object(lifecycle, "bump", side_effect=concurrent):
            with self.assertRaisesRegex(ValueError, "moved during"):
                self.bump()
        self.assert_remote(git(self.peer, "rev-parse", "HEAD"))

    def advertised_race(self, kind):
        real_run = lifecycle.run
        expected = None
        pushes = 0
        reads = 0

        def concurrent(*args, **kwargs):
            nonlocal expected, pushes, reads
            if args[:2] == ("git", "ls-remote"):
                reads += 1
            # Inject after the final remote read, before push starts advertising.
            if "push" in args:
                self.assertEqual(reads, 2)
                pushes += 1
                if kind == "rewind":
                    expected = self.ancestor
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                elif kind == "delete":
                    git(self.remote, "update-ref", "-d", "refs/heads/selected")
                elif kind == "advance":
                    expected = self.advance_peer()
                elif kind == "same-result":
                    expected = git(self.local, "rev-parse", "HEAD")
                    git(self.remote, "fetch", "--no-tags", str(self.local), "HEAD")
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                else:
                    self.fail(kind)
            return real_run(*args, **kwargs)

        with patch.object(lifecycle, "run", side_effect=concurrent):
            with self.assertRaises(subprocess.CalledProcessError):
                self.bump()
        self.assertEqual(pushes, 1)
        self.assert_remote(expected)

    def test_advertised_rewind(self):
        self.advertised_race("rewind")

    def test_advertised_delete(self):
        self.advertised_race("delete")

    def test_advertised_advance(self):
        self.advertised_race("advance")

    def test_advertised_same_result_zero_updates(self):
        self.advertised_race("same-result")

    def guard_loss(self, late, missing):
        runtime = self.root / "runtime"
        shutil.copytree(self.local / ".github/scripts", runtime)
        guard = runtime / "bump-hooks/pre-push"
        real_remote_ref = lifecycle.remote_ref
        reads = 0

        def lose():
            if missing:
                guard.unlink()
            else:
                guard.chmod(0o644)

        def remote_read(ref):
            nonlocal reads
            result = real_remote_ref(ref)
            reads += 1
            if late and reads == 2:
                lose()
            return result

        if not late:
            lose()
        with patch.object(lifecycle, "__file__", str(runtime / "bump.py")), \
                patch.object(lifecycle, "remote_ref", side_effect=remote_read), \
                patch.object(lifecycle, "run", wraps=lifecycle.run) as run:
            with self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
                self.bump()
            self.assertFalse(any("push" in call.args for call in run.call_args_list))
        self.assertEqual(reads, 2 if late else 0)
        self.assert_remote(self.sha)

    def test_initial_missing_guard(self):
        self.guard_loss(False, True)

    def test_initial_nonexecutable_guard(self):
        self.guard_loss(False, False)

    def test_late_missing_guard(self):
        self.guard_loss(True, True)

    def test_late_nonexecutable_guard(self):
        self.guard_loss(True, False)

    def corrupt_commit(self, kind):
        real_run = lifecycle.run

        def corrupt(*args, **kwargs):
            if "commit" in args and kind == "non-source":
                (self.local / "unrelated").write_text("not metadata")
                git(self.local, "add", "unrelated")
            result = real_run(*args, **kwargs)
            if "commit" in args and kind != "non-source":
                tree = git(self.local, "rev-parse",
                           f"{self.sha}^{{tree}}" if kind == "empty" else "HEAD^{tree}")
                parents = ["-p", self.sha]
                if kind == "merge":
                    parents += ["-p", self.ancestor]
                message = "replacement\n"
                if kind != "trailer":
                    message += f"\n{lifecycle.TRAILER}\n"
                new = git(self.local, "commit-tree", tree, *parents, input=message)
                git(self.local, "reset", "--hard", new)
            return result

        with patch.object(lifecycle, "run", side_effect=corrupt) as run:
            with self.assertRaisesRegex(ValueError, {
                "merge": "single-parent direct child",
                "non-source": "source version metadata only",
                "empty": "source version metadata only",
                "trailer": "co-author trailer",
            }[kind]):
                self.bump()
            self.assertFalse(any("push" in call.args for call in run.call_args_list))
        self.assert_remote(self.sha)

    def test_reject_multiparent_commit(self):
        self.corrupt_commit("merge")

    def test_reject_non_source_commit(self):
        self.corrupt_commit("non-source")

    def test_reject_empty_commit(self):
        self.corrupt_commit("empty")

    def test_reject_missing_trailer(self):
        self.corrupt_commit("trailer")

    def test_hook_exact_literal_head_parent_ref_and_one_update(self):
        git(self.local, "commit", "--allow-empty", "-m", "direct child")
        new = git(self.local, "rev-parse", "HEAD")
        guard = self.local / ".github/scripts/bump-hooks/pre-push"
        env = {**os.environ, "BUMP_EXPECTED_SHA": self.sha,
               "BUMP_EXPECTED_REF": "refs/heads/selected", "BUMP_NEW_SHA": new}
        valid = f"{new} {new} refs/heads/selected {self.sha}\n"

        def invoke(row, environment=env):
            return subprocess.run([str(guard)], input=row, env=environment, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode

        self.assertEqual(invoke(valid), 0)
        for row in (
            f"{new} {new} refs/heads/wrong {self.sha}\n",
            f"HEAD {new} refs/heads/selected {self.sha}\n",
            f"{new} {self.ancestor} refs/heads/selected {self.sha}\n",
            f"{new} {new} refs/heads/selected {self.ancestor}\n",
            valid * 2, "",
        ):
            with self.subTest(row=row):
                self.assertNotEqual(invoke(row), 0)
        self.assertNotEqual(invoke(valid, {}), 0)
        git(self.local, "reset", "--hard", self.sha)
        self.assertNotEqual(invoke(valid), 0)
        tree = git(self.local, "rev-parse", "HEAD^{tree}")
        merge = git(self.local, "commit-tree", tree, "-p", self.sha, "-p", self.ancestor,
                    input="merge\n")
        git(self.local, "update-ref", "HEAD", merge)
        env["BUMP_NEW_SHA"] = merge
        self.assertNotEqual(invoke(f"{merge} {merge} refs/heads/selected {self.sha}\n"), 0)
        result = subprocess.run(
            ["git", "-c", f"core.hooksPath={guard.parent}", "-c", "push.followTags=false",
             "push", "--porcelain", "--no-follow-tags", "origin",
             f"{merge}:refs/heads/selected"], env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("advertised branch state differs", result.stderr)
        self.assert_remote(self.sha)


if __name__ == "__main__":
    unittest.main()
