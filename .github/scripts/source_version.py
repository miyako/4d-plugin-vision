"""Coordinated source versions; copied bundles and 4D counters are not sources."""

import argparse
from pathlib import Path
import plistlib
import re
from xml.parsers.expat import ExpatError


PROJECT = Path("vision.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
LOCALIZED = Path("English.lproj/InfoPlist.strings")
SOURCE_PATHS = (PROJECT, PLIST, LOCALIZED)
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
KEYS = ("MARKETING_VERSION", "CURRENT_PROJECT_VERSION")
SETTING_COUNT = 6
REFERENCES = {f"$({key})": key for key in KEYS}
REFERENCES.update({f"${{{key}}}": key for key in KEYS})
SETTING = re.compile(
    r"(?m)^([ \t]*(MARKETING_VERSION|CURRENT_PROJECT_VERSION)[ \t]*=[ \t]*)([^;\n]*)(;)"
)
PROJECT_TOKEN = re.compile(
    r'/\*.*?\*/|//[^\r\n]*|"(?:\\.|[^"\\])*"|'
    r'\$\([^()\s]*\)|\$\{[^{}\s]*\}|[^\s"=;{}(),/]+|[^\s]',
    re.DOTALL,
)
LOCALIZED_SHORT = re.compile(
    r'(?m)^([ \t]*(?:"CFBundleShortVersionString"|CFBundleShortVersionString)'
    r'[ \t]*=[ \t]*")([^"]*)("[ \t]*;[ \t]*)$'
)
LOCALIZED_INFO = re.compile(
    r'(?m)^([ \t]*(?:"CFBundleGetInfoString"|CFBundleGetInfoString)'
    r'[ \t]*=[ \t]*"vision version )'
    r'([^,"]*)(, Copyright 2021 miyako\."[ \t]*;[ \t]*)$'
)
LOCALIZED_TOKEN = re.compile(
    r'\s+|/\*.*?\*/|//[^\r\n]*|'
    r'(?P<key>"[A-Za-z_][A-Za-z_0-9]*"|[A-Za-z_][A-Za-z_0-9]*)'
    r'\s*=\s*"(?P<value>(?:\\.|[^"\\])*)"\s*;',
    re.DOTALL,
)
PLIST_VERSION = re.compile(
    r"(<key>CFBundle(?:ShortVersionString|Version)</key>\s*<string>)([^<]*)(</string>)"
)


class UniqueDictionary(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError(f"Duplicate metadata key: {key}")
        super().__setitem__(key, value)


def unquote(value):
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


def decode(data):
    for bom, encoding in (
        (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"),
        (b"\xef\xbb\xbf", "utf-8"),
    ):
        if data.startswith(bom):
            return data[len(bom):].decode(encoding), encoding, bom
    if b"\0" in data:
        even = data[::2].count(0)
        odd = data[1::2].count(0)
        if len(data) % 2:
            raise ValueError("Malformed or ambiguous BOM-less source encoding")
        if odd > 2 * even:
            encoding = "utf-16-le"
        elif even > 2 * odd:
            encoding = "utf-16-be"
        else:
            raise ValueError("Ambiguous BOM-less source encoding")
        value = data.decode(encoding)
        if "\0" in value:
            raise ValueError("NUL characters are unsupported in source metadata")
        return value, encoding, b""
    return data.decode("utf-8"), "utf-8", b""


def text(path):
    return decode(Path(path).read_bytes())[0].replace("\r\n", "\n").replace("\r", "\n")


def rendered(path, transform):
    value, encoding, bom = decode(Path(path).read_bytes())
    return bom + transform(value).encode(encoding)


def project_settings(project):
    """Return value spans, including quoted and inline assignments, excluding noise."""
    tokens = [m for m in PROJECT_TOKEN.finditer(project)
              if not m[0].startswith(("/*", "//"))]
    fields = {key: [] for key in KEYS}
    for index, token in enumerate(tokens[:-1]):
        key = unquote(token[0])
        if key not in fields or tokens[index + 1][0] != "=":
            continue
        if index + 3 >= len(tokens) or tokens[index + 3][0] != ";":
            raise ValueError(f"Malformed source assignment for {key}")
        value = tokens[index + 2]
        fields[key].append((unquote(value[0]), value.start(), value.end()))
    if any(len(values) != SETTING_COUNT for values in fields.values()):
        raise ValueError(f"Expected {SETTING_COUNT} source assignments for each version key")
    return fields


def resolve_settings(fields):
    resolved = {}

    def resolve(key, visiting=()):
        if key in visiting:
            raise ValueError("Cyclic source version reference")
        if key not in resolved:
            values = set()
            for value, _, _ in fields[key]:
                if value in REFERENCES:
                    value = resolve(REFERENCES[value], visiting + (key,))
                elif not re.fullmatch(VERSION, value):
                    raise ValueError(f"{key} must resolve to strict X.Y.Z")
                values.add(value)
            if len(values) != 1:
                raise ValueError(f"{key} has drifted across configurations")
            resolved[key] = values.pop()
        return resolved[key]

    if len({resolve(key) for key in KEYS}) != 1:
        raise ValueError("MARKETING_VERSION and CURRENT_PROJECT_VERSION have drifted")
    return resolved


def load_plist(data):
    try:
        # Explicit XML parsing also recognizes BOM-less UTF-16. Expat still
        # enforces the XML encoding declaration against the original bytes.
        fmt = plistlib.FMT_BINARY if data.startswith(b"bplist00") else plistlib.FMT_XML
        return plistlib.loads(data, fmt=fmt, dict_type=UniqueDictionary)
    except (plistlib.InvalidFileException, ExpatError, UnicodeError) as exc:
        raise ValueError("Invalid plist serialization") from exc


def localized_fields(value):
    fields = UniqueDictionary()
    offset = 0
    while offset < len(value):
        token = LOCALIZED_TOKEN.match(value, offset)
        if token is None:
            raise ValueError("Unsupported strings serialization")
        if token["key"] is not None:
            fields[unquote(token["key"])] = (
                token["value"], token.start("value"), token.end("value"),
            )
        offset = token.end()
    return fields


def validate_localized(value, version, message):
    fields = localized_fields(value)
    expected = {
        "CFBundleShortVersionString": version,
        "CFBundleGetInfoString": f"vision version {version}, Copyright 2021 miyako.",
    }
    if any(key not in fields or fields[key][0] != wanted for key, wanted in expected.items()):
        raise ValueError(message)
    return fields


def inspect_data(data):
    decoded = {path: decode(data[path])[0] for path in SOURCE_PATHS}
    settings = project_settings(decoded[PROJECT])
    resolved = resolve_settings(settings)
    version = resolved["MARKETING_VERSION"]
    plist = load_plist(data[PLIST])
    if not isinstance(plist, dict):
        raise ValueError("Source Info.plist must be a dictionary")
    if "CFBundleShortVersionString" not in plist:
        raise ValueError("CFBundleShortVersionString is required")
    # Mask XML comments without changing token offsets.
    xml = re.sub(r"<!--.*?-->", lambda m: " " * len(m[0]),
                 decoded[PLIST], flags=re.DOTALL)
    serialized = list(PLIST_VERSION.finditer(xml))
    expected = 1 + ("CFBundleVersion" in plist)
    if len(serialized) != expected:
        raise ValueError("Source plist versions must be editable XML strings")
    edits = {path: [] for path in SOURCE_PATHS}
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if key not in plist:
            continue
        value = plist[key]
        if not isinstance(value, str) or resolved.get(REFERENCES.get(value), value) != version:
            raise ValueError(f"{key} is invalid, unresolved or has drifted")
        matches = [m for m in serialized if f"<key>{key}</key>" in m[1]]
        if len(matches) != 1 or matches[0][2] != value:
            raise ValueError(f"{key} has unsupported XML serialization")
        if value not in REFERENCES:
            edits[PLIST].append(matches[0].span(2))
    for values in settings.values():
        for value, start, end in values:
            if value not in REFERENCES:
                quoted = decoded[PROJECT][start] == '"'
                edits[PROJECT].append((start + quoted, end - quoted))
    localized = validate_localized(
        decoded[LOCALIZED], version, "Localized source version is missing, invalid or has drifted",
    )
    _, start, end = localized["CFBundleShortVersionString"]
    edits[LOCALIZED].append((start, end))
    _, start, _ = localized["CFBundleGetInfoString"]
    start += len("vision version ")
    edits[LOCALIZED].append((start, start + len(version)))
    return version, edits


def inspect(root=Path(".")):
    """Return the coordinated version and validated per-file token spans."""
    root = Path(root)
    return inspect_data({path: (root / path).read_bytes() for path in SOURCE_PATHS})


def read(root=Path(".")):
    return inspect(root)[0]


def bump(mode, root=Path(".")):
    index = ("major", "minor", "patch").index(mode)
    root = Path(root)
    data = {path: (root / path).read_bytes() for path in SOURCE_PATHS}
    current, edits = inspect_data(data)
    parts = list(map(int, current.split(".")))
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    new = ".".join(map(str, parts))
    updates = {}
    for path in SOURCE_PATHS:
        value, encoding, bom = decode(data[path])
        for start, end in sorted(edits[path], reverse=True):
            value = value[:start] + new + value[end:]
        updates[path] = bom + value.encode(encoding)
    # Validate every rendered file before the first write.
    if inspect_data(updates)[0] != new:
        raise ValueError("Bumped metadata did not validate")
    for path, content in updates.items():
        if content != data[path]:
            (root / path).write_bytes(content)
    return new


def verify_bundle(bundle, root=Path(".")):
    version = read(root)
    contents = Path(bundle) / "Contents"
    data = load_plist((contents / "Info.plist").read_bytes())
    if not isinstance(data, dict) or data.get("CFBundleShortVersionString") != version:
        raise ValueError("Built bundle display version differs from selected source")
    source_plist = load_plist((Path(root) / PLIST).read_bytes())
    if ("CFBundleVersion" in source_plist or "CFBundleVersion" in data) \
            and data.get("CFBundleVersion") != version:
        raise ValueError("Built bundle build version differs from selected source")
    serialized = (contents / "Resources/English.lproj/InfoPlist.strings").read_bytes()
    if serialized.startswith(b"bplist00") or decode(serialized)[0].lstrip().startswith("<?xml"):
        localized = load_plist(serialized)
        if not isinstance(localized, dict) or (
            localized.get("CFBundleShortVersionString") != version
            or localized.get("CFBundleGetInfoString")
            != f"vision version {version}, Copyright 2021 miyako."
        ):
            raise ValueError("Built localized display differs from selected source")
    else:
        validate_localized(decode(serialized)[0], version,
                           "Built localized display differs from selected source")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--bump", choices=("patch", "minor", "major"))
    operation.add_argument("--verify-bundle", type=Path)
    args = parser.parse_args()
    if args.verify_bundle:
        verify_bundle(args.verify_bundle)
    else:
        print(bump(args.bump) if args.bump else read())
