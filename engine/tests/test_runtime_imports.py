"""Every module the engine imports is installed by the AppImage, not only in the development venv.

The AppImage installs the engine from `uv export --no-dev` (scripts/bundle_meta.py): a package that comes only from
the dev group (httpx, pytest) is missing there, while the tests, run in the dev venv, still pass. 0.2.0 and 0.2.1
shipped `import httpx` in fetch.py and failed at the model step of every installation.
"""

from __future__ import annotations

import ast
import importlib.metadata
import re
import sys
import tomllib
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
SOURCES = ENGINE / "src" / "geonesclick"


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_packages() -> set[str]:
    """The packages uv.lock installs for geonesclick without the dev group (its dependencies, transitively)."""
    lock = tomllib.loads((ENGINE / "uv.lock").read_text(encoding="utf-8"))
    by_name = {_normalized(p["name"]): p for p in lock["package"]}
    seen, todo = set(), [_normalized("geonesclick")]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo += [_normalized(d["name"]) for d in by_name[name].get("dependencies", [])]
    return seen


def imported_modules() -> dict[str, str]:
    """Top-level module -> first file importing it, for every import of the engine (inside functions too)."""
    found: dict[str, str] = {}
    for path in sorted(SOURCES.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                found.setdefault(name.split(".")[0], path.name)
    return found


def test_every_import_comes_from_a_runtime_dependency():
    runtime = runtime_packages()
    distributions = importlib.metadata.packages_distributions()
    missing = []
    for module, where in sorted(imported_modules().items()):
        if module in sys.stdlib_module_names or module == "geonesclick":
            continue
        dists = {_normalized(d) for d in distributions.get(module, [])}
        if not dists & runtime:
            missing.append(f"{module} ({where}): from {sorted(dists) or 'no installed package'}")
    assert not missing, "imported but not installed by the AppImage: " + "; ".join(missing)


def test_the_check_sees_a_dev_only_package():
    assert "pytest" not in runtime_packages() and "httpx" not in runtime_packages()
    assert "httpx2" in runtime_packages() and "huggingface-hub" in runtime_packages()
