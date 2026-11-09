"""Fail-closed, create-only publication; partial remote state is never repaired."""

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from urllib.parse import quote
from xml.parsers.expat import ExpatError

sys.dont_write_bytecode = True
from source_version import read

REPOSITORY = "miyako/4d-plugin-vision"
BUNDLE = "test/Plugins/vision.bundle/Contents/"
GENERATED_FILES = {
    BUNDLE + "MacOS/vision",
    BUNDLE + "Info.plist",
    BUNDLE + "Resources/English.lproj/InfoPlist.strings",
}


def run(*args, input=None):
    return subprocess.run(
        args, input=input, text=True, stdout=subprocess.PIPE, check=True
    ).stdout.rstrip("\n")


def api(endpoint, payload=None, asset=None):
    command = ["gh", "api", "--method",
               "GET" if payload is None and asset is None else "POST", endpoint]
    if payload is not None:
        command += ["--input", "-"]
    if asset is not None:
        command += ["--header", "Content-Type: application/octet-stream", "--input", str(asset)]
    return json.loads(run(*command, input=json.dumps(payload) if payload is not None else None))


def selected_sha(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected immutable selected github.sha")
    if run("git", "rev-parse", "HEAD") != sha:
        raise ValueError("Checkout does not match selected github.sha")


def generated(path):
    return (path in GENERATED_FILES or path.startswith(BUNDLE + "_CodeSignature/")
            or path.startswith("build/vision.build/")
            or path.startswith("build/XCBuildData/"))


def context(sha, *, final=False):
    selected_sha(sha)
    if final:
        # Inspect index and worktree separately: an unstaged reversal must not hide
        # a staged source/config change. NUL separation preserves unusual names.
        changed = set()
        for args in (("diff", "--cached", "--name-only", "--no-renames", "-z", sha, "--"),
                     ("diff", "--name-only", "--no-renames", "-z", "--")):
            changed.update(filter(None, run("git", *args).split("\0")))
        if any(not generated(path) for path in changed):
            raise ValueError("Tracked source/config differs from the selected commit")
    elif run("git", "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Build preflight requires a clean source checkout")
    repo = os.environ["GITHUB_REPOSITORY"]
    if repo != REPOSITORY:
        raise ValueError(f"Expected repository {REPOSITORY}")
    version = read()
    if not isinstance(version, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Expected coordinated semantic source version")
    if final:
        expected_assets = {f"vision-{version}.zip", f"vision-{version}.dmg"}
        untracked = filter(None, run("git", "ls-files", "--others", "-z", "--").split("\0"))
        if any(not generated(path) and path not in expected_assets for path in untracked):
            raise ValueError("Untracked source/config or unexpected output in checkout")
    return repo, version, f"v{version}"


def remote_ref(ref):
    output = run("git", "ls-remote", "--refs", "origin", ref)
    if not output:
        return None
    lines = output.splitlines()
    if len(lines) != 1:
        raise ValueError(f"Malformed remote ref response for {ref}")
    parts = lines[0].split()
    if len(parts) != 2 or parts[1] != ref or not re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        raise ValueError(f"Malformed remote ref response for {ref}")
    return parts[0]


def available(repo, tag):
    run("gh", "auth", "status", "--active", "--hostname", "github.com")
    if remote_ref(f"refs/tags/{tag}") is not None:
        raise ValueError(f"{tag} already exists remotely")
    page = 1
    while True:
        releases = api(f"repos/{repo}/releases?per_page=100&page={page}")
        if not isinstance(releases, list) or len(releases) > 100:
            raise ValueError("Malformed releases page")
        for release in releases:
            if (
                not isinstance(release, dict)
                or type(release.get("id")) is not int
                or release["id"] <= 0
                or not isinstance(release.get("tag_name"), str)
                or not release["tag_name"]
                or type(release.get("draft")) is not bool
                or type(release.get("prerelease")) is not bool
            ):
                raise ValueError("Malformed release entry")
            if release["tag_name"] == tag:
                raise ValueError(f"{tag} already has a draft or published release")
        if len(releases) < 100:
            break
        page += 1


def preflight(sha):
    repo, version, tag = context(sha)
    available(repo, tag)
    return version, tag


def publish(sha, assets):
    repo, version, tag = context(sha, final=True)
    expected = [f"vision-{version}.zip", f"vision-{version}.dmg"]
    if [str(path) for path in assets] != expected:
        raise ValueError(f"Expected release assets: {expected}")
    for path in assets:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing or empty release asset: {path}")
    # This gate belongs after every native/sign/notary/staple operation.
    available(repo, tag)
    ref = api(f"repos/{repo}/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
    if (
        not isinstance(ref, dict)
        or ref.get("ref") != f"refs/tags/{tag}"
        or not isinstance(ref.get("object"), dict)
        or ref["object"].get("sha") != sha
        or ref["object"].get("type") != "commit"
        or remote_ref(f"refs/tags/{tag}") != sha
    ):
        raise ValueError("New remote tag failed exact-SHA verification")
    print(f"Created remote tag {tag} at {sha}; retained if later steps fail", flush=True)
    # Preserve the original softprops inputs: tag/name/files, no release notes.
    release = api(f"repos/{repo}/releases", {
        "tag_name": tag, "target_commitish": sha, "name": tag,
        "draft": False, "prerelease": False, "body": "", "generate_release_notes": False,
    })
    if (
        not isinstance(release, dict)
        or type(release.get("id")) is not int
        or release["id"] <= 0
        or release.get("tag_name") != tag
        or release.get("name") != tag
        or release.get("target_commitish") != sha
        or release.get("body") not in ("", None)
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("Malformed create-release response; inspect retained remote state")
    release_id = release["id"]
    print(f"Created {tag}, release ID {release_id}; uploading assets", flush=True)
    for asset in assets:
        result = api(
            f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name={quote(asset.name, safe='')}",
            asset=asset,
        )
        if (
            not isinstance(result, dict)
            or type(result.get("id")) is not int
            or result["id"] <= 0
            or result.get("name") != asset.name
            or type(result.get("size")) is not int
            or result["size"] != asset.stat().st_size
            or result.get("state") != "uploaded"
        ):
            raise ValueError(f"Malformed upload response for {asset}; inspect retained release")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "check", "publish"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("assets", nargs="*", type=Path)
    args = parser.parse_intermixed_args(argv)
    if args.command in ("preflight", "check"):
        if args.assets:
            parser.error("check/preflight does not accept assets")
        version, tag = preflight(args.sha)
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(f"version={version}\ntag={tag}\n")
    else:
        publish(args.sha, args.assets)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, plistlib.InvalidFileException,
            ExpatError, subprocess.CalledProcessError) as error:
        print(f"::error::{error}. Stopped without rollback/retry. Any remote tag, "
              "release and uploaded assets are retained; manual recovery is required.",
              file=sys.stderr)
        sys.exit(1)
