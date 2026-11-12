"""scripts/check-version.py: the release number follows strict SemVer (CLAUDE.md › Versions)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-version.py"
spec = importlib.util.spec_from_file_location("check_version", SCRIPT)
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)


@pytest.mark.parametrize("version, previous, kinds", [
    ("0.3.1", "0.3.0", {"Fixed"}),
    ("0.3.1", "0.3.0", {"Fixed", "Security"}),
    ("0.4.0", "0.3.1", {"Added", "Fixed"}),
    ("0.4.0", "0.3.1", {"Changed"}),
    ("0.4.0", "0.3.1", {"Removed"}),         # before 1.0.0, a breaking change raises the MINOR
    ("2.0.0", "1.4.2", {"Removed", "Fixed"}),
    ("0.4.0", "0.3.1", {"Fixed"}),           # a bigger step than needed is allowed
])
def test_right_numbers_pass(version, previous, kinds):
    assert cv.check(cv.parse(version), cv.parse(previous), kinds) is None


@pytest.mark.parametrize("version, previous, kinds, want", [
    ("0.2.2", "0.2.1", {"Added", "Fixed"}, "expected 0.3.0"),
    ("0.3.1", "0.3.0", {"Deprecated"}, "expected 0.4.0"),
    ("1.5.0", "1.4.2", {"Removed"}, "expected 2.0.0"),
    ("0.5.0", "0.3.1", {"Added"}, "does not follow 0.3.1 by one step"),
    ("0.3.2", "0.3.0", {"Fixed"}, "does not follow 0.3.0 by one step"),
])
def test_wrong_numbers_are_refused_with_the_expected_one(version, previous, kinds, want):
    assert want in cv.check(cv.parse(version), cv.parse(previous), kinds)


def test_the_sections_come_from_the_changelog():
    assert cv.sections(cv.parse("0.2.0")) >= {"Added", "Changed", "Fixed"}
