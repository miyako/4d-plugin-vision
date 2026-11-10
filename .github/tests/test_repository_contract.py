import os
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
INTAKE = "14cff9ed01dee21a448de8fea71e5b5790a5f320"
AUTHORITY = "2791822db05ec42c98430985a628e50f05deae2f"
sys.path.insert(0, str(ROOT / ".github/scripts"))
import source_version


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


class RepositoryContractTests(unittest.TestCase):
    def test_exact_two_independent_manual_entries(self):
        workflows = sorted(p for p in (ROOT / ".github/workflows").glob("*")
                           if "\n  workflow_dispatch:" in p.read_text())
        self.assertEqual([p.name for p in workflows], ["bump-version.yml", "release.yml"])
        bump, build = [p.read_text() for p in workflows]
        self.assertTrue(bump.startswith("name: Bump\n"))
        self.assertTrue(build.startswith("name: Build\n"))
        for text in (bump, build):
            events = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
            self.assertNotIn("push:", events)
            self.assertNotIn("pull_request", events)
            self.assertEqual(events.count("workflow_dispatch:"), 1)
            self.assertIn("cancel-in-progress: false", text)
            concurrency = text.split("\nconcurrency:\n", 1)[1].split("\njobs:", 1)[0]
            self.assertNotIn("${{", concurrency)
            for checkout in re.findall(r"uses: actions/checkout@[^\n]+\n(.*?)(?=\n      -|\Z)", text, re.S):
                self.assertIn("ref: ${{ github.sha }}", checkout)
            self.assertNotIn("refs/heads/main", text)
        self.assertEqual(bump.count("type: choice"), 1)
        self.assertIn("default: patch\n        required: true", bump)
        self.assertEqual(re.findall(r"^          - (\w+)$", bump, re.M), ["patch", "minor", "major"])
        self.assertNotIn("inputs:", build)
        self.assertNotIn("release.py", bump)
        self.assertNotIn("bump.py", build)

    def test_ownership_ci_is_read_only_and_nonrelease(self):
        workflows = sorted(p.name for p in (ROOT / ".github/workflows").glob("*"))
        self.assertEqual(workflows, ["bump-version.yml", "ownership.yml", "release.yml"])
        text = (ROOT / ".github/workflows/ownership.yml").read_text()
        self.assertIn("  pull_request:", text)
        self.assertIn("  push:", text)
        self.assertIn("  contents: read", text)
        self.assertIn("--expect-baseline-failure", text)
        self.assertIn("run: python3 .github/tests/run_ownership.py\n", text)
        for forbidden in ("workflow_dispatch", "secrets.", "contents: write",
                          "release.py", "bump.py", "codesign", "notarytool", "hdiutil"):
            self.assertNotIn(forbidden, text)

    def test_actual_macos_only_jobs_and_native_configuration(self):
        build = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertEqual(re.findall(r"^  ([a-z-]+):\n", build.split("\njobs:\n")[1], re.M),
                         ["version", "build-macos"])
        for value in ("-configuration Default", 'CONFIGURATION_BUILD_DIR="$PWD/test/Plugins"',
                      'ARCHS="arm64 x86_64"', "ONLY_ACTIVE_ARCH=NO",
                      "MACOS_DEPLOYMENT_TARGET: '10.13'"):
            self.assertIn(value, build)
        self.assertNotIn("windows-latest", build)
        self.assertNotIn("msbuild", build.lower())
        self.assertIn("lipo -verify_arch arm64 x86_64", build)
        self.assertNotIn("i386", build)
        self.assertNotIn("otool", build)

    def test_early_final_publication_gate_order(self):
        text = (ROOT / ".github/workflows/release.yml").read_text()
        markers = ("release.py check", "import Developer ID certificate",
                   "store notarytool credentials", "build macOS plugin",
                   "verify universal binary", "      - name: codesign",
                   "package, notarize & staple", "xcrun stapler staple", "release.py publish")
        positions = [text.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(text.count('--wait --output-format json'), 2)
        self.assertEqual(text.count('d.get("status") == "Accepted"'), 2)
        self.assertIn("codesign --verify --deep --strict", text)
        self.assertNotIn("softprops", text)

    def test_original_triggers_and_release_notes_are_immutable_evidence(self):
        old = git("show", INTAKE + ":.github/workflows/release.yml").decode()
        self.assertIn("name: Build & Release", old)
        self.assertIn("  push:\n    tags:\n      - 'v*.*.*'", old)
        self.assertNotIn("pull_request:", old)
        self.assertNotIn("branches:", old)
        self.assertIn("      tag:\n", old)
        release = old.split("uses: softprops/action-gh-release@v2", 1)[1]
        self.assertEqual(re.findall(r"^          (\w+):", release, re.M),
                         ["tag_name", "name", "files"])
        header = git("show", AUTHORITY + ":.github/workflows/bump-version.yml").decode()
        self.assertIn("MARKETING_VERSION/CURRENT_PROJECT_VERSION", header)
        self.assertIn("CFBundleShortVersionString/CFBundleVersion", header)

    def test_only_necessary_native_source_tokens_changed(self):
        version = source_version.read().encode()
        expected = {
            "vision.xcodeproj/project.pbxproj":
                git("show", INTAKE + ":vision.xcodeproj/project.pbxproj")
                .replace(b"MARKETING_VERSION = 1.0.8;", b"MARKETING_VERSION = " + version + b";")
                .replace(b"CURRENT_PROJECT_VERSION = 1.0.6;", b"CURRENT_PROJECT_VERSION = " + version + b";"),
            "Info.plist": git("show", INTAKE + ":Info.plist").replace(b"1.0.8", version),
            "English.lproj/InfoPlist.strings":
                git("show", INTAKE + ":English.lproj/InfoPlist.strings").replace(b"1.0.2", version),
        }
        for path, data in expected.items():
            self.assertEqual((ROOT / path).read_bytes(), data, path)
            mode = git("ls-tree", INTAKE, "--", path).split()[0]
            self.assertEqual(bool(os.stat(ROOT / path).st_mode & 0o111), mode == b"100755")
        self.assertNotIn(b"CFBundleVersion", (ROOT / "Info.plist").read_bytes())

    def test_native_deps_resources_prebuilts_and_4d_untouched(self):
        paths = git("ls-tree", "-r", "--name-only", INTAKE).decode().splitlines()
        preserved = [p for p in paths if not p.startswith(".github/") and p not in
                     ("README.md", "Info.plist", "vision.xcodeproj/project.pbxproj",
                      "English.lproj/InfoPlist.strings",
                      # Intentional first-party ownership fixes, not SDK/resource changes.
                      "4DPlugin-vision.cpp", "support/4DPlugin-JSON.cpp",
                      "support/4DPlugin-JSON.h")]
        self.assertGreater(len(preserved), 100)
        subprocess.run(["git", "diff", "--exit-code", INTAKE, "--", *preserved],
                       cwd=ROOT, check=True, stdout=subprocess.PIPE)

    def test_secret_names_preserved_without_values(self):
        old = git("show", INTAKE + ":.github/workflows/release.yml").decode()
        new = (ROOT / ".github/workflows/release.yml").read_text()
        pattern = r"secrets\.([A-Z_]+)"
        self.assertEqual(set(re.findall(pattern, old)), set(re.findall(pattern, new)))

    def test_selective_invalidation_never_removes_whole_bundle(self):
        sys.path.insert(0, str(ROOT / ".github/scripts"))
        import native
        self.assertEqual(native.FILES, (
            Path("test/Plugins/vision.bundle/Contents/MacOS/vision"),
            Path("test/Plugins/vision.bundle/Contents/Info.plist"),
            Path("test/Plugins/vision.bundle/Contents/Resources/English.lproj/InfoPlist.strings"),
        ))
        self.assertEqual(native.DIRECTORIES, (
            Path("test/Plugins/vision.bundle/Contents/_CodeSignature"),
            Path("build/vision.build"),
            Path("build/XCBuildData"),
        ))


if __name__ == "__main__":
    unittest.main()
