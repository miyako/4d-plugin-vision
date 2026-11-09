"""Create one source-version commit and push only the selected branch, fail closed."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from source_version import SOURCE_PATHS, bump


TRAILER = "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"


def run(*args, input=None, env=None):
    return subprocess.run(
        args, input=input, env=env, text=True, stdout=subprocess.PIPE, check=True
    ).stdout.strip()


def selected_sha(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected immutable selected github.sha")
    if run("git", "rev-parse", "HEAD") != sha:
        raise ValueError("Checkout does not match selected github.sha")


def remote_ref(ref):
    output = run("git", "ls-remote", "--refs", "origin", ref)
    if not output:
        return None
    lines = output.splitlines()
    parts = lines[0].split()
    if len(lines) != 1 or len(parts) != 2 or parts[1] != ref \
            or not re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        raise ValueError(f"Malformed remote ref response for {ref}")
    return parts[0]


def require_guard(guard):
    if not guard.is_file() or not os.access(guard, os.X_OK):
        raise ValueError("Required advertised-SHA pre-push guard is missing or not executable")


def bump_branch(sha, ref, mode):
    selected_sha(sha)
    if not ref.startswith("refs/heads/"):
        raise ValueError("Bump requires a full refs/heads/* branch ref")
    run("git", "check-ref-format", ref)
    hooks = Path(__file__).resolve().parent / "bump-hooks"
    guard = hooks / "pre-push"
    require_guard(guard)
    if remote_ref(ref) != sha:
        raise ValueError("Selected branch moved since dispatch; dispatch again")
    if run("git", "status", "--porcelain"):
        raise ValueError("Bump requires a clean checkout")
    new = bump(mode)
    run("git", "add", "--", *map(str, SOURCE_PATHS))
    run("git", "-c", "user.name=github-actions[bot]",
        "-c", "user.email=github-actions[bot]@users.noreply.github.com",
        "commit", "-m", f"chore: bump version to {new}", "-m", TRAILER)
    if remote_ref(ref) != sha:
        raise ValueError("Selected branch moved during bump; nothing pushed")
    commit = run("git", "rev-parse", "HEAD")
    if run("git", "rev-list", "--parents", "-n", "1", commit) != f"{commit} {sha}" \
            or run("git", "status", "--porcelain"):
        raise ValueError("Bump commit must be a clean single-parent direct child of selected SHA")
    changed = set(run("git", "diff-tree", "--no-commit-id", "--name-only",
                      "-r", commit).splitlines())
    if not changed or not changed.issubset(set(map(str, SOURCE_PATHS))):
        raise ValueError("Bump commit must change source version metadata only")
    trailers = run("git", "log", "-1", "--format=%(trailers:only,unfold)", commit)
    if TRAILER not in trailers.splitlines():
        raise ValueError("Bump commit is missing the required co-author trailer")
    require_guard(guard)
    result = run("git", "-c", f"core.hooksPath={hooks}", "-c", "push.followTags=false",
                 "push", "--porcelain", "--no-follow-tags", "origin", f"{commit}:{ref}",
                 env={**os.environ, "BUMP_EXPECTED_SHA": sha,
                      "BUMP_EXPECTED_REF": ref, "BUMP_NEW_SHA": commit})
    if not any(line.startswith(" \t") and line.split("\t")[1] == f"{commit}:{ref}"
               for line in result.splitlines()):
        raise ValueError("Branch push was not a new update; inspect remote state")
    if remote_ref(ref) != commit:
        raise ValueError("Pushed branch failed exact-SHA verification; inspect remote state")
    print(f"Bumped source metadata to {new}; run Build manually on {ref}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("patch", "minor", "major"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ref", required=True)
    args = parser.parse_args(argv)
    bump_branch(args.sha, args.ref, args.mode)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"::error::{error}. Stopped without rollback/retry; inspect retained state.",
              file=sys.stderr)
        sys.exit(1)
