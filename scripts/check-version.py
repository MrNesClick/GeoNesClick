#!/usr/bin/env python3
"""Checks that a release number follows strict SemVer against the previous tag and its CHANGELOG section.

    scripts/check-version.py 0.3.0                 # previous version: the highest v* tag below it
    scripts/check-version.py 0.3.0 --previous 0.2.4

Rules (CLAUDE.md, "Versions"): one step from the previous version; Added, Changed or Deprecated need at least a MINOR;
Removed needs a MAJOR (a MINOR before 1.0.0); only Fixed or Security allow a PATCH. Exit code 1 with the expected
number when the rule is broken. Used by the release workflow before anything is built.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
Version = tuple[int, int, int]


def parse(text: str) -> Version:
    match = VERSION.match(text.removeprefix("v"))
    if not match:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {text}")
    return tuple(int(n) for n in match.groups())  # type: ignore[return-value]


def show(v: Version) -> str:
    return ".".join(map(str, v))


def previous_tag(version: Version) -> Version | None:
    tags = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    older = sorted(v for v in (parse(t) for t in tags.split() if VERSION.match(t.removeprefix("v"))) if v < version)
    return older[-1] if older else None


def sections(version: Version) -> set[str]:
    """The ### headings of the version's CHANGELOG section (Added, Changed…)."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(show(version))}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    if not match:
        raise ValueError(f"CHANGELOG.md has no section for {show(version)}")
    return set(re.findall(r"^### (\w+)", match.group(1), re.M))


def expected(previous: Version, kinds: set[str]) -> Version:
    major, minor, patch = previous
    breaking, feature = "Removed" in kinds, bool(kinds & {"Added", "Changed", "Deprecated"})
    if breaking and major >= 1:
        return (major + 1, 0, 0)
    if breaking or feature:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def check(version: Version, previous: Version, kinds: set[str]) -> str | None:
    """None if the number is right, otherwise why."""
    steps = {(previous[0], previous[1], previous[2] + 1), (previous[0], previous[1] + 1, 0), (previous[0] + 1, 0, 0)}
    if version not in steps:
        return f"{show(version)} does not follow {show(previous)} by one step"
    want = expected(previous, kinds)
    if version < want:
        listed = ", ".join(sorted(kinds)) or "no section"
        return f"{show(version)} is too small for a section with {listed}: expected {show(want)}"
    return None


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("version")
    args.add_argument("--previous")
    a = args.parse_args()
    version = parse(a.version)
    previous = parse(a.previous) if a.previous else previous_tag(version)
    if previous is None:
        print(f"{show(version)}: first release, nothing to compare")
        return 0
    error = check(version, previous, sections(version))
    if error:
        print(f"error: {error} (strict SemVer, see CLAUDE.md › Versions)", file=sys.stderr)
        return 1
    print(f"{show(version)} after {show(previous)}: right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
