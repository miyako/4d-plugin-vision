#!/usr/bin/env python3
"""Compile actual plugin/helper source and unchanged SDK; never build a bundle."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
GROUPS = ("setters", "getters", "collections", "consumers", "arrays", "failed-reads")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", help="Immutable git revision to test with this harness")
    parser.add_argument("--expect-baseline-failure", action="store_true")
    args = parser.parse_args()
    if args.expect_baseline_failure and not args.source_ref:
        parser.error("--expect-baseline-failure requires --source-ref")
    with tempfile.TemporaryDirectory(prefix="vision-ownership-") as directory:
        temp = Path(directory)
        source = ROOT
        if args.source_ref:
            source = temp / "source"
            files = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", args.source_ref, "--",
                 "4DPlugin-vision.cpp", "4DPlugin-vision.h", "support", "4D Plugin API"],
                cwd=ROOT, text=True).splitlines()
            for name in files:
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(
                    ["git", "show", f"{args.source_ref}:{name}"], cwd=ROOT))
        compiler = subprocess.check_output(["xcrun", "--find", "clang++"], text=True).strip()
        sysroot = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
        common = [compiler, "-std=c++17", "-g", "-O1", "-fno-omit-frame-pointer",
                  "-isysroot", sysroot,
                  "-fsanitize=address,undefined", "-Wno-deprecated-declarations", "-Wno-multichar",
                  "-I" + str(source), "-I" + str(source / "4D Plugin API"),
                  "-I" + str(source / "support")]
        sdk = temp / "sdk.o"
        subprocess.run(common + ["-x", "objective-c++", "-c",
                       str(source / "4D Plugin API/4DPluginAPI.c"), "-o", str(sdk)], check=True)
        binary = temp / "ownership"
        subprocess.run(common + ["-x", "objective-c++", str(ROOT / ".github/tests/ownership.mm"),
                       str(source / "support/4DPlugin-JSON.cpp"), "-x", "none", str(sdk),
                       "-framework", "Cocoa", "-framework", "Vision",
                       "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
        failed = {}
        groups = GROUPS[:-1] if args.expect_baseline_failure else GROUPS
        for group in groups:
            for empty in ("allocated", "null"):
                result = subprocess.run([str(binary), group, empty], env=env,
                                        text=True, capture_output=True)
                print(result.stdout + result.stderr, end="")
                if result.returncode:
                    failed[(group, empty)] = result.stdout + result.stderr
        if args.expect_baseline_failure:
            required = {
                ("setters", "allocated"): "setter leaked an overwritten empty allocation",
                ("getters", "null"): "getter leaked owning result (including mismatches)",
                ("collections", "null"): "collection element results leaked",
                ("consumers", "null"): "consumer leaked owning nested reference",
            }
            if not all(message in failed.get(case, "") for case, message in required.items()):
                raise SystemExit(f"Baseline did not reproduce required failures: {failed}")
            allowed = set(required) | {(group, "allocated") for group in
                                      ("getters", "collections", "consumers")}
            messages = {case[0]: message for case, message in required.items()}
            if failed.keys() - allowed or any(
                    messages[case[0]] not in output for case, output in failed.items()):
                raise SystemExit(f"Unexpected baseline failure: {failed}")
            print("Immutable baseline reproduced all four ownership defect groups.")
        elif failed:
            raise SystemExit(f"Ownership regressions failed: {failed}")


if __name__ == "__main__":
    main()
