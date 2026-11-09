#!/usr/bin/env python3
"""Invalidate only generated macOS outputs, retaining the packaged resources."""

import argparse
from pathlib import Path
import shutil


BUNDLE = Path("test/Plugins/vision.bundle")
FILES = (
    BUNDLE / "Contents/MacOS/vision",
    BUNDLE / "Contents/Info.plist",
    BUNDLE / "Contents/Resources/English.lproj/InfoPlist.strings",
)
DIRECTORIES = (
    BUNDLE / "Contents/_CodeSignature",
    Path("build/vision.build"),
    Path("build/XCBuildData"),
)


def prepare():
    root = Path.cwd().resolve()
    paths = (*FILES, *DIRECTORIES)
    for path in paths:
        for parent in (path, *path.parents):
            if parent == Path("."):
                break
            if parent.is_symlink():
                raise ValueError(f"Refusing symlink output: {parent}")
        if not path.resolve().is_relative_to(root):
            raise ValueError(f"Output escapes checkout: {path}")
    for path in FILES:
        path.unlink(missing_ok=True)
    for path in DIRECTORIES:
        if path.exists():
            shutil.rmtree(path)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    prepare()
