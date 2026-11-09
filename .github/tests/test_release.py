"""Offline create-only publication tests, including a real-Git native build."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import call, patch
from uuid import uuid4

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
SPEC = importlib.util.spec_from_file_location("publication_release", ROOT / ".github/scripts/release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
SHA = "a" * 40
TAG = "v1.2.3"
REPO = "miyako/4d-plugin-vision"


def entry(tag="v0.0.1", draft=False):
    return {"id": 9, "tag_name": tag, "draft": draft, "prerelease": False}


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(release, "run", return_value="")
        self.run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_all_pages_and_drafts(self):
        for draft in (True, False):
            with self.subTest(draft=draft), \
                    patch.object(release, "remote_ref", return_value=None), \
                    patch.object(release, "api", side_effect=[
                        [entry()] * 100, [entry(TAG, draft)],
                    ]) as api:
                with self.assertRaisesRegex(ValueError, "draft or published"):
                    release.available(REPO, TAG)
                self.assertEqual(api.call_args_list, [
                    call(f"repos/{REPO}/releases?per_page=100&page=1"),
                    call(f"repos/{REPO}/releases?per_page=100&page=2"),
                ])
        with patch.object(release, "remote_ref", return_value=None), \
                patch.object(release, "api", side_effect=[
                    [entry()] * 100, [entry()] * 100, [],
                ]) as api:
            release.available(REPO, TAG)
            self.assertEqual(api.call_count, 3)
        self.run.assert_called_with("gh", "auth", "status", "--active", "--hostname", "github.com")

    def test_every_page_errors_and_malformed_fail_closed(self):
        errors = [
            *(subprocess.CalledProcessError(1, ["gh", str(code)])
              for code in (401, 403, 404, 422, 500)),
            OSError("network"), json.JSONDecodeError("bad", "?", 0),
        ]
        malformed = [
            {}, None, "[]", [None], [{}], [dict(entry(), id=True)],
            [dict(entry(), id=0)], [dict(entry(), id=-1)],
            [dict(entry(), tag_name=None)], [dict(entry(), tag_name="")],
            [dict(entry(), draft=0)], [dict(entry(), prerelease="false")],
            [entry()] * 101,
        ]
        for page in (1, 2, 3):
            for response in errors + malformed:
                with self.subTest(page=page, response=response), \
                        patch.object(release, "remote_ref", return_value=None), \
                        patch.object(release, "api", side_effect=(
                            [[entry()] * 100] * (page - 1) + [response]
                        )) as api:
                    with self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                        release.available(REPO, TAG)
                    self.assertEqual(api.call_count, page)

    def test_auth_failure_stops_before_remote_or_api(self):
        self.run.side_effect = subprocess.CalledProcessError(1, ["gh", "auth"])
        with patch.object(release, "api") as api, patch.object(release, "remote_ref") as remote:
            with self.assertRaises(subprocess.CalledProcessError):
                release.available(REPO, TAG)
            api.assert_not_called()
            remote.assert_not_called()

    def test_exact_remote_tag_and_malformed_remote(self):
        ref = f"refs/tags/{TAG}"
        self.run.return_value = f"{SHA}\t{ref}"
        self.assertEqual(release.remote_ref(ref), SHA)
        self.run.assert_called_once_with("git", "ls-remote", "--refs", "origin", ref)
        for output in ("invalid", f"{SHA}\t{ref}-other", f"bad\t{ref}",
                       f"{SHA}\t{ref}\n{SHA}\t{ref}"):
            with self.subTest(output=output):
                self.run.return_value = output
                with self.assertRaises(ValueError):
                    release.remote_ref(ref)
        for response in (SHA, OSError("network"), ValueError("malformed")):
            with self.subTest(response=response), \
                    patch.object(release, "remote_ref", side_effect=[response]), \
                    patch.object(release, "api") as api:
                with self.assertRaises((ValueError, OSError)):
                    release.available(REPO, TAG)
                api.assert_not_called()

    def test_transport_explicit_methods_no_retry(self):
        self.run.return_value = "[]"
        release.api("repos/o/r/releases?per_page=100&page=2")
        self.run.assert_called_once_with(
            "gh", "api", "--method", "GET",
            "repos/o/r/releases?per_page=100&page=2", input=None,
        )
        payload = {"ref": f"refs/tags/{TAG}", "sha": SHA}
        release.api("repos/o/r/git/refs", payload)
        self.assertIn("POST", self.run.call_args.args)
        self.assertEqual(json.loads(self.run.call_args.kwargs["input"]), payload)
        release.api("https://uploads.github.com/repos/o/r/releases/123/assets",
                    asset=Path("asset.zip"))
        self.assertEqual(self.run.call_args.args[-4:], (
            "--header", "Content-Type: application/octet-stream", "--input", "asset.zip",
        ))
        self.run.reset_mock()
        self.run.side_effect = subprocess.CalledProcessError(1, "gh")
        with self.assertRaises(subprocess.CalledProcessError):
            release.api("repos/o/r/releases")
        self.assertEqual(self.run.call_count, 1)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / ".github/tests" / (".release-fixture-" + uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)
        previous = Path.cwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)
        self.env = self.start_patch(patch.dict(os.environ, GITHUB_REPOSITORY=REPO))
        self.start_patch(patch("sys.stdout", new_callable=io.StringIO))

    def start_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def write(self, name, data=b"fixture"):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


class PublicationTests(Fixture):
    def setUp(self):
        super().setUp()
        self.assets = [self.write("vision-1.2.3.zip"), self.write("vision-1.2.3.dmg")]
        self.calls = []
        self.tag = None
        self.published = None
        self.uploaded = []
        self.fail = None
        self.race = None
        self.bad_kind = None
        self.bad_result = None
        self.pages = [[]]
        self.start_patch(patch.object(release, "context", return_value=(REPO, "1.2.3", TAG)))
        self.start_patch(patch.object(release, "run", return_value=""))
        self.start_patch(patch.object(release, "remote_ref", side_effect=lambda ref: self.tag))
        self.start_patch(patch.object(release, "api", side_effect=self.api))

    def api(self, endpoint, payload=None, asset=None):
        self.calls.append((endpoint, payload, asset))
        if "/releases?" in endpoint:
            page = int(endpoint.rsplit("=", 1)[1])
            result = self.pages[page - 1]
            if isinstance(result, Exception):
                raise result
            return result
        if endpoint.endswith("/git/refs"):
            kind = "tag"
            if self.race:
                self.tag = self.race
            if self.tag is not None or self.fail == kind:
                raise subprocess.CalledProcessError(1, ["gh", "api", "422"])
            self.tag = payload["sha"]
            result = {"ref": payload["ref"], "object": {"sha": self.tag, "type": "commit"}}
        elif endpoint.endswith("/releases"):
            kind = "release"
            if self.fail == kind:
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            self.published = {"id": 123, **payload}
            result = self.published
        elif asset is not None:
            kind = asset.suffix
            if self.fail == kind:
                raise subprocess.CalledProcessError(1, ["gh", "api"])
            self.uploaded.append(asset.name)
            result = {"id": 456, "name": asset.name, "size": asset.stat().st_size,
                      "state": "uploaded"}
        else:
            raise AssertionError(endpoint)
        return self.bad_result if self.bad_kind == kind else result

    def publish(self):
        release.publish(SHA, self.assets)

    def test_create_only_order_payload_and_returned_release_id(self):
        self.publish()
        self.assertEqual(self.tag, SHA)
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(self.calls[1], (
            f"repos/{REPO}/git/refs", {"ref": f"refs/tags/{TAG}", "sha": SHA}, None,
        ))
        self.assertEqual(self.calls[2], (f"repos/{REPO}/releases", {
            "tag_name": TAG, "target_commitish": SHA, "name": TAG,
            "draft": False, "prerelease": False, "body": "", "generate_release_notes": False,
        }, None))
        for endpoint, payload, asset in self.calls[3:]:
            self.assertEqual(endpoint,
                             f"https://uploads.github.com/repos/{REPO}/releases/123/assets?name={asset.name}")
            self.assertIsNone(payload)
        self.assertEqual(self.uploaded, [asset.name for asset in self.assets])

    def test_same_and_different_sha_tag_races_fail_without_reuse(self):
        for sha in (SHA, "b" * 40):
            with self.subTest(sha=sha):
                self.calls.clear()
                self.tag = None
                self.race = sha
                with self.assertRaises(subprocess.CalledProcessError):
                    self.publish()
                self.assertEqual(self.tag, sha)
                self.assertEqual(len(self.calls), 2)
                self.assertIsNone(self.published)
                self.assertEqual(self.uploaded, [])

    def test_each_post_failure_retains_all_prior_state_without_retry(self):
        for kind, count, tag, published, uploaded in (
            ("tag", 2, None, False, []),
            ("release", 3, SHA, False, []),
            (".zip", 4, SHA, True, []),
            (".dmg", 5, SHA, True, [self.assets[0].name]),
        ):
            with self.subTest(kind=kind):
                self.calls.clear()
                self.tag, self.published, self.uploaded = None, None, []
                self.fail = kind
                with self.assertRaises(subprocess.CalledProcessError):
                    self.publish()
                self.assertEqual(len(self.calls), count)
                self.assertEqual(self.tag, tag)
                self.assertEqual(self.published is not None, published)
                self.assertEqual(self.uploaded, uploaded)
                self.assertTrue(all(path.read_bytes() == b"fixture" for path in self.assets))

    def test_final_recheck_rejects_new_draft_and_later_page_errors(self):
        for result in ([entry(TAG, True)], {"message": "bad"},
                       subprocess.CalledProcessError(1, ["gh", "404"])):
            with self.subTest(result=result):
                self.calls.clear()
                self.pages = [[]]
                release.preflight(SHA)
                self.calls.clear()
                self.pages = [[entry()] * 100, result]
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    self.publish()
                self.assertEqual(len(self.calls), 2)
                self.assertIsNone(self.tag)
                self.assertIsNone(self.published)

    def test_final_recheck_rejects_new_remote_tag(self):
        release.preflight(SHA)
        self.calls.clear()
        self.tag = SHA
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_remote_verification_failure_never_creates_release(self):
        for response in (None, "b" * 40, OSError("network"), ValueError("malformed")):
            with self.subTest(response=response):
                self.tag = None
                self.calls.clear()
                with patch.object(release, "remote_ref", side_effect=[None, response]):
                    with self.assertRaises((ValueError, OSError)):
                        self.publish()
                self.assertEqual(self.tag, SHA)
                self.assertEqual(len(self.calls), 2)
                self.assertIsNone(self.published)

    def test_malformed_mutation_responses_stop_and_retain_created_state(self):
        tag_response = {"ref": f"refs/tags/{TAG}", "object": {"sha": SHA, "type": "commit"}}
        release_response = {"id": 123, "tag_name": TAG, "target_commitish": SHA,
                            "name": TAG, "draft": False, "prerelease": False, "body": ""}
        asset_response = {"id": 456, "name": self.assets[0].name, "size": 7, "state": "uploaded"}
        for kind, responses, count in (
            ("tag", [None, {}, dict(tag_response, ref="refs/tags/wrong"),
                     dict(tag_response, object={"sha": "b" * 40, "type": "commit"}),
                     dict(tag_response, object={"sha": SHA, "type": "tag"})], 2),
            ("release", [None, {}, dict(release_response, id=True),
                         dict(release_response, id=0), dict(release_response, draft=True),
                         dict(release_response, prerelease=True),
                         dict(release_response, tag_name="v9.9.9"),
                         dict(release_response, name="wrong"),
                         dict(release_response, target_commitish="main")], 3),
            (".zip", [None, {}, dict(asset_response, id=True), dict(asset_response, size=True),
                      dict(asset_response, size=1), dict(asset_response, name="wrong"),
                      dict(asset_response, state="new")], 4),
        ):
            for response in responses:
                with self.subTest(kind=kind, response=response):
                    self.tag, self.published, self.uploaded = None, None, []
                    self.calls.clear()
                    self.bad_kind, self.bad_result = kind, response
                    with self.assertRaises(ValueError):
                        self.publish()
                    self.assertEqual(len(self.calls), count)
                    self.assertEqual(self.tag, SHA)
                    self.assertEqual(self.published is not None, kind != "tag")
                    self.assertEqual(self.uploaded, [self.assets[0].name] if kind == ".zip" else [])

    def test_invalid_assets_fail_before_remote_operations(self):
        for assets in ([], [self.assets[0], self.assets[0]], [Path("missing.zip")],
                       [self.directory], list(reversed(self.assets))):
            with self.subTest(assets=assets), patch.object(release, "available") as available:
                with self.assertRaises(ValueError):
                    release.publish(SHA, assets)
                available.assert_not_called()
                self.assertEqual(self.calls, [])
        self.assets[0].write_bytes(b"")
        with self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])


class RealGitTests(Fixture):
    def setUp(self):
        super().setUp()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Offline fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.generated = [*sorted(release.GENERATED_FILES),
                          release.BUNDLE + "_CodeSignature/CodeResources",
                          "build/vision.build/intermediate"]
        self.protected = [
            "vision.xcodeproj/project.pbxproj", "Info.plist", "English.lproj/InfoPlist.strings",
            ".github/workflows/release.yml", ".github/scripts/source_version.py",
            "sources/plugin.cpp", release.BUNDLE + "Resources/other.txt",
            release.BUNDLE + "Windows/vision.4DX", "unrelated.txt",
            "build/unproven/config",
        ]
        for name in self.generated + self.protected:
            self.write(name)
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "fixture baseline")
        self.sha = self.git("rev-parse", "HEAD")
        self.start_patch(patch.object(release, "read", return_value="1.2.3"))
        self.real_run = release.run
        self.api_calls = []
        self.tag = None
        self.start_patch(patch.object(release, "run", side_effect=self.fake_gh))
        self.start_patch(patch.object(release, "remote_ref", side_effect=lambda ref: self.tag))

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()

    def fake_gh(self, *args, input=None):
        if args[:2] == ("gh", "auth"):
            return ""
        if args[:2] != ("gh", "api"):
            return self.real_run(*args, input=input)
        self.api_calls.append((args, input))
        method, endpoint = args[3:5]
        if method == "GET":
            return "[]"
        if endpoint.endswith("/git/refs"):
            payload = json.loads(input)
            self.tag = payload["sha"]
            return json.dumps({"ref": payload["ref"], "object": {"sha": self.tag, "type": "commit"}})
        if endpoint.endswith("/releases"):
            return json.dumps({"id": 789, **json.loads(input)})
        asset = Path(args[-1])
        self.assertIn("/releases/789/assets?name=" + asset.name, endpoint)
        return json.dumps({"id": 123, "name": asset.name, "size": asset.stat().st_size,
                           "state": "uploaded"})

    def assets(self):
        return [self.write("vision-1.2.3.zip"), self.write("vision-1.2.3.dmg")]

    def test_clean_early_check_then_tracked_native_dirt_publishes_without_reset(self):
        output = self.directory / "build/XCBuildData/outputs"
        output.parent.mkdir(parents=True)
        with patch.dict(os.environ, GITHUB_OUTPUT=str(output)):
            release.main(["check", "--sha", self.sha])
        self.assertEqual(output.read_text(), "version=1.2.3\ntag=v1.2.3\n")
        retained = {}
        for index, name in enumerate(self.generated):
            retained[name] = b"\x00signed-native-" + str(index).encode()
            self.write(name, retained[name])
        self.git("add", "--", self.generated[0])
        self.write("build/XCBuildData/intermediate", b"intermediate build bytes")
        self.write(release.BUNDLE + "_CodeSignature/new-seal", b"new signature bytes")
        assets = self.assets()
        release.main(["publish", "--sha", self.sha, *map(str, assets)])
        self.assertEqual(self.tag, self.sha)
        self.assertEqual(len(self.api_calls), 6)
        for name, data in retained.items():
            self.assertEqual(Path(name).read_bytes(), data)
        self.assertEqual(Path("build/XCBuildData/intermediate").read_bytes(), b"intermediate build bytes")
        self.assertEqual(Path(release.BUNDLE + "_CodeSignature/new-seal").read_bytes(),
                         b"new signature bytes")
        self.assertTrue(self.git("status", "--porcelain"))

    def test_source_config_resources_windows_staged_and_unstaged_fail_before_api(self):
        assets = self.assets()
        for name in self.protected:
            for staged in (False, True, "reversed"):
                with self.subTest(path=name, staged=staged):
                    self.write(name, b"changed")
                    if staged:
                        self.git("add", "--", name)
                    if staged == "reversed":
                        self.write(name)
                    with self.assertRaisesRegex(ValueError, "source/config"):
                        release.publish(self.sha, assets)
                    self.assertEqual(self.api_calls, [])
                    # Fixture-only cleanup; production code must never reset.
                    self.git("restore", "--source=HEAD", "--staged", "--worktree", "--", name)

    def test_rename_and_deletion_of_protected_files_fail(self):
        self.git("mv", "unrelated.txt", "build/disguised")
        with self.assertRaisesRegex(ValueError, "source/config"):
            release.publish(self.sha, self.assets())
        self.assertEqual(self.api_calls, [])

    def test_head_mutation_fails_before_api(self):
        self.git("commit", "--quiet", "--allow-empty", "-m", "unexpected HEAD")
        with self.assertRaisesRegex(ValueError, "Checkout"):
            release.publish(self.sha, self.assets())
        self.assertEqual(self.api_calls, [])

    def test_early_check_rejects_even_native_dirt_and_untracked_files(self):
        for name in (self.generated[0], "untracked-source.cpp"):
            with self.subTest(path=name):
                self.write(name, b"changed")
                with self.assertRaisesRegex(ValueError, "clean"):
                    release.preflight(self.sha)
                self.assertEqual(self.api_calls, [])
                if name in self.generated:
                    self.git("restore", "--", name)
                else:
                    Path(name).unlink()

    def test_wrong_repository_and_invalid_sha_fail_before_api(self):
        for sha in ("main", SHA.upper(), "a" * 39):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                release.publish(sha, self.assets())
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/other"):
            with self.assertRaisesRegex(ValueError, "repository"):
                release.publish(self.sha, self.assets())
        self.assertEqual(self.api_calls, [])

    def test_untracked_source_config_and_unproven_outputs_fail_before_api(self):
        assets = self.assets()
        paths = [
            "sources/injected.cpp", ".github/workflows/injected.yml",
            "vision.xcodeproj/injected.xcconfig", "build/unproven/injected",
            release.BUNDLE + "Resources/injected.txt", release.BUNDLE + "Windows/injected.4DX",
            "unexpected.zip",
        ]
        for name in paths:
            with self.subTest(path=name):
                path = self.write(name, b"injected bytes")
                with self.assertRaisesRegex(ValueError, "Untracked source/config"):
                    release.publish(self.sha, assets)
                self.assertEqual(self.api_calls, [])
                self.assertEqual(path.read_bytes(), b"injected bytes")
                path.unlink()

    def test_ignored_untracked_source_config_also_fails_before_api(self):
        self.write(".git/info/exclude", b"ignored-source.cpp\n")
        self.write("ignored-source.cpp")
        with self.assertRaisesRegex(ValueError, "Untracked source/config"):
            release.publish(self.sha, self.assets())
        self.assertEqual(self.api_calls, [])


class CLITests(unittest.TestCase):
    def test_preflight_check_publish_interfaces(self):
        for command in ("preflight", "check"):
            with self.subTest(command=command), \
                    patch.object(release, "preflight", return_value=("1.2.3", TAG)) as preflight, \
                    patch.dict(os.environ, GITHUB_OUTPUT="fixture-output"), \
                    patch("builtins.open", unittest.mock.mock_open()) as output:
                release.main([command, "--sha", SHA])
                preflight.assert_called_once_with(SHA)
                output.assert_called_once_with("fixture-output", "a")
                output().write.assert_called_once_with(f"version=1.2.3\ntag={TAG}\n")
        with patch.object(release, "publish") as publish:
            release.main(["publish", "--sha", SHA, "first.zip", "second.dmg"])
            publish.assert_called_once_with(SHA, [Path("first.zip"), Path("second.dmg")])
        for args in (["bump", "--sha", SHA], ["check", "--sha", SHA, "extra.zip"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    release.main(args)

    def test_explicit_error_retention_message_and_nonzero_status(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/release.py"),
             "publish", "--sha", "invalid"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Stopped without rollback/retry", result.stderr)
        self.assertIn("remote tag, release and uploaded assets are retained", result.stderr)


if __name__ == "__main__":
    unittest.main()
