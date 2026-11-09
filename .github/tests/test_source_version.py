import importlib.util
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
INTAKE = "14cff9ed01dee21a448de8fea71e5b5790a5f320"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("source_version", ROOT / ".github/scripts/source_version.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intake = {
            path: subprocess.run(
                ["git", "-C", str(ROOT), "show", f"{INTAKE}:{path}"],
                check=True, capture_output=True,
            ).stdout for path in source.SOURCE_PATHS
        }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".source-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.copy_source()
        self.current = source.read(self.root)
        self.drift = f"{int(self.current.split('.')[0]) + 1}.9.7"

    def copy_source(self):
        # The immutable intake intentionally contains stale build/localized metadata.
        # Repair a private fixture, never the tracked source or copied bundle.
        version = plistlib.loads(self.intake[source.PLIST])["CFBundleShortVersionString"]
        for path, data in self.intake.items():
            if path == source.PROJECT:
                data = re.sub(
                    rb"(CURRENT_PROJECT_VERSION = )[^;]+",
                    lambda m: m[1] + version.encode(), data,
                )
            elif path == source.LOCALIZED:
                old = source.localized_fields(data.decode())["CFBundleShortVersionString"][0]
                data = data.replace(old.encode(), version.encode())
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def plist(self, **values):
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        data.update(values)
        path.write_bytes(plistlib.dumps(data))

    def snapshot(self):
        return {path: ((self.root / path).read_bytes(),
                       stat.S_IMODE((self.root / path).stat().st_mode))
                for path in source.SOURCE_PATHS}

    def assert_rejected(self):
        before = self.snapshot()
        with patch.object(Path, "write_bytes") as write:
            with self.assertRaises(ValueError):
                source.bump("patch", self.root)
            write.assert_not_called()
        self.assertEqual(before, self.snapshot())

    def test_live_metadata_and_all_bump_modes(self):
        current = source.read(ROOT)
        parts = list(map(int, current.split(".")))
        self.assertEqual(source.SETTING_COUNT, 6)
        self.assertEqual(source.inspect(ROOT)[0], current)
        for mode, expected in (
            ("patch", [parts[0], parts[1], parts[2] + 1]),
            ("minor", [parts[0], parts[1] + 1, 0]),
            ("major", [parts[0] + 1, 0, 0]),
        ):
            with self.subTest(mode=mode):
                for path in source.SOURCE_PATHS:
                    shutil.copy2(ROOT / path, self.root / path)
                expected = ".".join(map(str, expected))
                self.assertEqual(source.bump(mode, self.root), expected)
                self.assertEqual(source.read(self.root), expected)
                self.assertNotIn("CFBundleVersion",
                                 plistlib.loads((self.root / source.PLIST).read_bytes()))
                fields = source.project_settings(source.text(self.root / source.PROJECT))
                for key in source.KEYS:
                    self.assertEqual([v for v, _, _ in fields[key]], [expected] * 6)

    def test_immutable_intake_has_expected_six_settings_and_stale_metadata(self):
        fields = source.project_settings(self.intake[source.PROJECT].decode())
        self.assertEqual({key: len(value) for key, value in fields.items()},
                         {key: 6 for key in source.KEYS})
        marketing = {v for v, _, _ in fields["MARKETING_VERSION"]}
        self.assertNotEqual(marketing, {v for v, _, _ in fields["CURRENT_PROJECT_VERSION"]})
        self.assertNotIn("CFBundleVersion", plistlib.loads(self.intake[source.PLIST]))
        for path, data in self.intake.items():
            (self.root / path).write_bytes(data)
        self.assert_rejected()

    def test_stable_fixture_coordinated_contract(self):
        project = self.root / source.PROJECT
        project.write_text(
            ("MARKETING_VERSION = 3.2.1;\nCURRENT_PROJECT_VERSION = 3.2.1;\n") * 6
        )
        self.plist(CFBundleShortVersionString="3.2.1", CFBundleVersion="3.2.1")
        (self.root / source.LOCALIZED).write_text(
            'CFBundleName = "vision";\nCFBundleShortVersionString = "3.2.1";\n'
            'CFBundleGetInfoString = "vision version 3.2.1, Copyright 2021 miyako.";\n',
            encoding="utf-8-sig",
        )
        self.assertEqual(source.bump("minor", self.root), "3.3.0")
        self.assertEqual(project.read_text().count("CURRENT_PROJECT_VERSION = 3.3.0;"), 6)
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         "3.3.0")
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)")
        self.assertEqual(source.read(self.root), "3.3.0")

    def test_invalid_missing_extra_and_drifted_settings(self):
        path = self.root / source.PROJECT
        original = source.text(path)
        for key in source.KEYS:
            for bad in ("1.2", "77", "v1.2.3", "01.2.3", "1.2.3-beta", "$(UNKNOWN)",
                        "", self.drift, f"$({key})", f"${{{key}}}"):
                for count in (1, 6):
                    with self.subTest(key=key, bad=bad, count=count):
                        path.write_text(original.replace(
                            f"{key} = {self.current};", f"{key} = {bad};", count))
                        self.assert_rejected()
            path.write_text(original.replace(f"{key} = {self.current};", "", 1))
            self.assert_rejected()
            path.write_text(original + f"\n{key} = {self.current};\n")
            self.assert_rejected()

    def test_references_resolve_recursively_and_remain_literal(self):
        for referencing, target in (source.KEYS, tuple(reversed(source.KEYS))):
            for brace in (False, True):
                for plist_ref in source.REFERENCES:
                    with self.subTest(referencing=referencing, brace=brace, plist_ref=plist_ref):
                        self.copy_source()
                        reference = f"${{{target}}}" if brace else f"$({target})"
                        path = self.root / source.PROJECT
                        path.write_text(source.text(path).replace(
                            f"{referencing} = {self.current};",
                            f'"{referencing}" = "{reference}";'))
                        self.plist(CFBundleShortVersionString=plist_ref, CFBundleVersion=plist_ref)
                        before = self.snapshot()
                        new = source.bump("patch", self.root)
                        self.assertEqual(source.read(self.root), new)
                        for name, (original, _) in before.items():
                            self.assertEqual((self.root / name).read_bytes(),
                                             original.replace(self.current.encode(), new.encode()))

    def test_cycles_and_reference_drift_rejected(self):
        project = self.root / source.PROJECT
        original = source.text(project)
        for key, target in (source.KEYS, tuple(reversed(source.KEYS))):
            project.write_text(original.replace(
                f"{key} = {self.current};", f"{key} = $({target});").replace(
                f"{target} = {self.current};", f"{target} = ${{{key}}};"))
            self.assert_rejected()
        self.copy_source()
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)",
                   CFBundleVersion="${CURRENT_PROJECT_VERSION}")
        project.write_text(original.replace(
            f"CURRENT_PROJECT_VERSION = {self.current};", "CURRENT_PROJECT_VERSION = 77;"))
        self.assert_rejected()

    def test_inline_quoted_unquoted_duplicates_and_malformed_assignments(self):
        project = self.root / source.PROJECT
        original = source.text(project)
        for key in source.KEYS:
            for quoted in (False, True):
                name = f'"{key}"' if quoted else key
                for value in (self.current, f'"{self.current}"', self.drift,
                              f'"{self.drift}"', "$(UNKNOWN)", '"$(UNKNOWN)"'):
                    for location in ("after-version", "after-other"):
                        with self.subTest(key=key, quoted=quoted, value=value, location=location):
                            duplicate = f"{name} = {value};"
                            existing = f"{key} = {self.current};"
                            mutated = original.replace(existing, f"{existing} {duplicate}", 1) \
                                if location == "after-version" else \
                                original + f'\nOTHER = "unchanged"; {duplicate}\n'
                            project.write_text(mutated)
                            self.assert_rejected()
                project.write_text(original + f"\n{name} = {self.current}\n")
                self.assert_rejected()

    def test_project_comments_and_quoted_noise_preserved(self):
        project = self.root / source.PROJECT
        noise = (
            '\n/* MARKETING_VERSION = 9.8.7; "CURRENT_PROJECT_VERSION" = 9.8.7; */\n'
            '/*\nMARKETING_VERSION = 9.8.7;\nCURRENT_PROJECT_VERSION = 9.8.7;\n*/\n'
            '// "MARKETING_VERSION" = 9.8.7;\rCURRENT_PROJECT_VERSION_SUFFIX = unchanged;\r'
            'OTHER = "MARKETING_VERSION = 9.8.7; \\"CURRENT_PROJECT_VERSION\\" = 9.8.7;";\n'
        ).replace("9.8.7", self.drift)
        project.write_bytes(project.read_bytes() + noise.encode())
        new = source.bump("patch", self.root)
        self.assertTrue(project.read_bytes().endswith(noise.encode()))
        self.assertEqual(source.read(self.root), new)

    def test_plist_invalid_and_drift(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in ("$(UNKNOWN)", "$(PRODUCT_NAME)", "", "invalid", 123,
                          self.drift, "1.2", "7", "01.2.3", "v1.2.3"):
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    self.plist(**{key: value})
                    self.assert_rejected()

    def test_missing_short_only_is_zero_write(self):
        self.plist(CFBundleVersion=self.current)
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        del data["CFBundleShortVersionString"]
        path.write_bytes(plistlib.dumps(data))
        self.assert_rejected()

    def test_both_versions_absent_is_zero_write(self):
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        data.pop("CFBundleShortVersionString")
        data.pop("CFBundleVersion", None)
        path.write_bytes(plistlib.dumps(data))
        self.assert_rejected()

    def test_optional_build_absence_preserved_and_present_build_co_bumped(self):
        new = source.bump("patch", self.root)
        self.assertNotIn("CFBundleVersion",
                         plistlib.loads((self.root / source.PLIST).read_bytes()))
        self.plist(CFBundleVersion=new)
        new = source.bump("minor", self.root)
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         new)

    def test_duplicate_plist_keys_and_invalid_serialization(self):
        path = self.root / source.PLIST
        original = source.text(path)
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in (self.current, self.drift):
                self.copy_source()
                if key == "CFBundleVersion":
                    self.plist(CFBundleVersion=self.current)
                data = source.text(path)
                path.write_text(data.replace(
                    "</dict>", f"<key>{key}</key><string>{value}</string>\n</dict>"))
                self.assert_rejected()
        for malformed in (
            b"not a plist", b"\xffnot utf8", plistlib.dumps([]),
            original.replace("</dict>", "").encode(),
            original.replace("<string>" + self.current,
                             f"<string>&#{ord(self.current[0])};" + self.current[1:]).encode(),
            plistlib.dumps(plistlib.loads(original.encode()), fmt=plistlib.FMT_BINARY),
        ):
            self.copy_source()
            path.write_bytes(malformed)
            with patch.object(Path, "write_bytes") as write:
                with self.assertRaises((ValueError, UnicodeError)):
                    source.bump("patch", self.root)
                write.assert_not_called()

    def test_localized_validation_and_inline_duplicates(self):
        path = self.root / source.LOCALIZED
        original = source.text(path)
        for pattern in (source.LOCALIZED_SHORT, source.LOCALIZED_INFO):
            for bad in ("1.0", self.drift, "invalid", "", "$(UNKNOWN)", "$(MARKETING_VERSION)",
                        "${CURRENT_PROJECT_VERSION}", "01.2.3", "1.2.3-beta"):
                path.write_text(pattern.sub(lambda m: f"{m[1]}{bad}{m[3]}", original))
                self.assert_rejected()
            path.write_text(pattern.sub("", original))
            self.assert_rejected()
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            path.write_text(original.replace(key, "UnknownKey"))
            self.assert_rejected()
            for quoted in (False, True):
                name = f'"{key}"' if quoted else key
                path.write_text(original + f'OTHER = "other"; {name} = "bad";\n')
                self.assert_rejected()
        for old, bad in (("vision", "Other Product"), ("Copyright 2021", "Copyright 2023"),
                         ("Copyright 2021 miyako", "Copyright 2021 someone")):
            path.write_text(original.replace(old, bad))
            self.assert_rejected()

    def test_localized_quoted_keys_and_comment_noise(self):
        path = self.root / source.LOCALIZED
        original = source.text(path)
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            original = original.replace(key + " =", f'"{key}" =')
        original += '// CFBundleShortVersionString = "not an assignment";\r'
        original += '/* "CFBundleGetInfoString" = "not an assignment"; */\n'
        original += 'Noise = "CFBundleShortVersionString = \\"noise\\";";\n'
        path.write_text(original)
        new = source.bump("patch", self.root)
        self.assertEqual(path.read_bytes(), original.replace(self.current, new).encode())

    def test_byte_preserving_encodings_individual_endings_and_modes(self):
        for newline in ("\n", "\r", "\r\n", "mixed"):
            for encoding, bom in (("utf-8", b""), ("utf-8", b"\xef\xbb\xbf"),
                                  ("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
                                  ("utf-16-le", b""), ("utf-16-be", b"")):
                with self.subTest(newline=newline, encoding=encoding, bom=bom):
                    self.copy_source()
                    for index, name in enumerate(source.SOURCE_PATHS):
                        path = self.root / name
                        lines = source.text(path).splitlines(keepends=True)
                        value = "".join(line.replace(
                            "\n", ("\r", "\r\n", "\n")[j % 3] if newline == "mixed" else newline
                        ) for j, line in enumerate(lines))
                        if name == source.PLIST and encoding.startswith("utf-16"):
                            value = value.replace('encoding="UTF-8"', 'encoding="UTF-16"')
                        path.write_bytes(bom + value.encode(encoding))
                        path.chmod((0o755, 0o640, 0o644)[index])
                    before = self.snapshot()
                    new = source.bump("minor", self.root)
                    for name, (original, mode) in before.items():
                        path = self.root / name
                        self.assertEqual(path.read_bytes(), original.replace(
                            self.current.encode(encoding), new.encode(encoding)))
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_whitespace_and_quotes_preserved(self):
        project = self.root / source.PROJECT
        original = source.text(project)
        for key in source.KEYS:
            original = original.replace(f"{key} = {self.current};",
                                        f'"{key}" \t= \t"{self.current}" \t;')
        project.write_text(original)
        localized = self.root / source.LOCALIZED
        localized.write_bytes(localized.read_bytes().replace(b" = ", b" \t= \t")
                              .replace(b'";', b'" \t; \t'))
        before = self.snapshot()
        new = source.bump("patch", self.root)
        for name, (original, _) in before.items():
            self.assertEqual((self.root / name).read_bytes(),
                             original.replace(self.current.encode(), new.encode()))

    def test_utf16_source_references_and_unrelated_unicode_preserved(self):
        for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
                              ("utf-16-le", b""), ("utf-16-be", b"")):
            with self.subTest(encoding=encoding):
                self.copy_source()
                project = self.root / source.PROJECT
                project.write_text(source.text(project).replace(
                    f"CURRENT_PROJECT_VERSION = {self.current};",
                    'CURRENT_PROJECT_VERSION = "$(MARKETING_VERSION)";'
                ) + '\nOTHER = "café 日本語";\n')
                self.plist(CFBundleShortVersionString="${CURRENT_PROJECT_VERSION}",
                           CFBundleVersion="$(MARKETING_VERSION)", UnrelatedVersion=self.current)
                localized = self.root / source.LOCALIZED
                localized.write_bytes(localized.read_bytes() + '\rOTHER = "café 日本語";\n'.encode())
                for name in source.SOURCE_PATHS:
                    path = self.root / name
                    value = source.text(path)
                    if name == source.PLIST:
                        value = value.replace('encoding="UTF-8"', 'encoding="UTF-16"')
                    lines = value.splitlines(keepends=True)
                    value = "".join(line.replace("\n", ("\r", "\r\n", "\n")[j % 3])
                                    for j, line in enumerate(lines))
                    path.write_bytes(bom + value.encode(encoding))
                before = self.snapshot()
                new = source.bump("patch", self.root)
                for name, (original, mode) in before.items():
                    # The unrelated plist string must not be changed, even when it
                    # contains precisely the selected source version.
                    expected = original
                    if name != source.PLIST:
                        expected = original.replace(self.current.encode(encoding),
                                                    new.encode(encoding))
                    self.assertEqual((self.root / name).read_bytes(), expected)
                    self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), mode)
                self.assertEqual(source.read(self.root), new)

    def test_utf16_source_drift_is_zero_write_for_each_file(self):
        for name in source.SOURCE_PATHS:
            for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
                                  ("utf-16-le", b""), ("utf-16-be", b"")):
                with self.subTest(path=name, encoding=encoding):
                    self.copy_source()
                    path = self.root / name
                    value = source.text(path).replace(self.current, self.drift, 1)
                    if name == source.PLIST:
                        value = value.replace('encoding="UTF-8"', 'encoding="UTF-16"')
                    lines = value.splitlines(keepends=True)
                    value = "".join(line.replace("\n", ("\r", "\r\n", "\n")[j % 3])
                                    for j, line in enumerate(lines))
                    path.write_bytes(bom + value.encode(encoding))
                    path.chmod(0o640)
                    self.assert_rejected()

    def test_utf16_xml_declarations_respected_and_ambiguous_encoding_rejected(self):
        for encoding, bom in (("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff"),
                              ("utf-16-le", b""), ("utf-16-be", b"")):
            self.copy_source()
            path = self.root / source.PLIST
            # UTF-16 bytes claiming UTF-8 are invalid XML, not an invitation to
            # rewrite the declaration or normalize the original file.
            path.write_bytes(bom + source.text(path).encode(encoding))
            self.assert_rejected()
        for name in source.SOURCE_PATHS:
            self.copy_source()
            (self.root / name).write_bytes(b"\0\0ambiguous\0\0")
            self.assert_rejected()

    def test_unrelated_versions_and_xml_comments_not_rewritten(self):
        project = self.root / source.PROJECT
        project.write_bytes(project.read_bytes() + f"\n/* Historical {self.current} */\n".encode())
        self.plist(UnrelatedVersion=self.current)
        plist = self.root / source.PLIST
        noise = f"<!-- <key>CFBundleVersion</key><string>{self.drift}</string> -->"
        plist.write_text(source.text(plist).replace("</dict>", noise + "\n</dict>"))
        localized = self.root / source.LOCALIZED
        localized.write_bytes(localized.read_bytes() + f'\rUnrelatedVersion = "{self.current}";\r'.encode())
        source.bump("minor", self.root)
        self.assertIn(f"/* Historical {self.current} */".encode(), project.read_bytes())
        self.assertIn(noise.encode(), plist.read_bytes())
        self.assertEqual(plistlib.loads(plist.read_bytes())["UnrelatedVersion"], self.current)
        self.assertIn(f'UnrelatedVersion = "{self.current}";'.encode(), localized.read_bytes())

    def test_copied_bundle_is_never_a_source_or_edited(self):
        self.assertEqual(source.SOURCE_PATHS, (
            Path("vision.xcodeproj/project.pbxproj"), Path("Info.plist"),
            Path("English.lproj/InfoPlist.strings"),
        ))
        excluded = (
            "test/Plugins/vision.bundle/Contents/Info.plist",
            "test/Plugins/vision.bundle/Contents/Resources/English.lproj/InfoPlist.strings",
            "English.lproj/locversion.plist", "manifest.json", "constants.xlf",
        )
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Excluded metadata must never be parsed or changed.\r\n")
            path.chmod(0o640)
        before = {name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
                  for name in excluded}
        source.bump("major", self.root)
        self.assertEqual(before, {
            name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
            for name in excluded
        })

    def test_missing_source_and_invalid_encoding_never_write(self):
        for name in source.SOURCE_PATHS:
            self.copy_source()
            (self.root / name).unlink()
            with patch.object(Path, "write_bytes") as write:
                with self.assertRaises(FileNotFoundError):
                    source.bump("patch", self.root)
                write.assert_not_called()
        self.copy_source()
        (self.root / source.LOCALIZED).write_bytes(b"\xffinvalid")
        before = self.snapshot()
        with patch.object(Path, "write_bytes") as write:
            with self.assertRaises(UnicodeError):
                source.bump("patch", self.root)
            write.assert_not_called()
        self.assertEqual(before, self.snapshot())

    def test_invalid_mode_and_cli_inspection_do_not_write(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.bump("other", self.root)
        output = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/source_version.py")],
            cwd=self.root, check=True, capture_output=True, text=True,
        )
        self.assertEqual(output.stdout.strip(), self.current)
        self.assertEqual(before, self.snapshot())

    def bundle(self):
        contents = self.root / "built.bundle/Contents"
        localized = contents / "Resources/English.lproj/InfoPlist.strings"
        localized.parent.mkdir(parents=True)
        shutil.copy2(self.root / source.LOCALIZED, localized)
        (contents / "Info.plist").write_bytes((self.root / source.PLIST).read_bytes())
        return contents, localized

    def test_built_plist_root_optional_build_and_mismatches(self):
        contents, _ = self.bundle()
        built = contents / "Info.plist"
        source.verify_bundle(contents.parent, self.root)
        for data, message in (
            ([], "display version"), ({}, "display version"),
            ({"CFBundleShortVersionString": self.drift}, "display version"),
            ({"CFBundleShortVersionString": self.current, "CFBundleVersion": self.drift},
             "build version"),
        ):
            built.write_bytes(plistlib.dumps(data))
            with self.assertRaisesRegex(ValueError, message):
                source.verify_bundle(contents.parent, self.root)
        self.plist(CFBundleVersion=self.current)
        built.write_bytes(plistlib.dumps({"CFBundleShortVersionString": self.current}))
        with self.assertRaisesRegex(ValueError, "build version"):
            source.verify_bundle(contents.parent, self.root)
        built.write_bytes((self.root / source.PLIST).read_bytes())
        source.verify_bundle(contents.parent, self.root)

    def test_built_xml_binary_plists_and_utf16_localization(self):
        contents, localized = self.bundle()
        value = source.text(self.root / source.LOCALIZED)
        fields = {
            "CFBundleShortVersionString": self.current,
            "CFBundleGetInfoString": f"vision version {self.current}, Copyright 2021 miyako.",
        }
        for fmt in (plistlib.FMT_XML, plistlib.FMT_BINARY):
            (contents / "Info.plist").write_bytes(plistlib.dumps(
                {"CFBundleShortVersionString": self.current}, fmt=fmt))
            for encoding, bom in (("utf-8", b"\xef\xbb\xbf"), ("utf-16-le", b"\xff\xfe"),
                                  ("utf-16-be", b"\xfe\xff")):
                localized.write_bytes(bom + value.encode(encoding))
                source.verify_bundle(contents.parent, self.root)
            for localized_fmt in (plistlib.FMT_XML, plistlib.FMT_BINARY):
                localized.write_bytes(plistlib.dumps(fields, fmt=localized_fmt))
                source.verify_bundle(contents.parent, self.root)
        localized.write_bytes(value.replace(self.current, "invalid").encode("utf-16"))
        with self.assertRaises(ValueError):
            source.verify_bundle(contents.parent, self.root)
        for bad in ({}, [], {**fields, "CFBundleGetInfoString": "wrong"}):
            localized.write_bytes(plistlib.dumps(bad))
            with self.assertRaises(ValueError):
                source.verify_bundle(contents.parent, self.root)


if __name__ == "__main__":
    unittest.main()
