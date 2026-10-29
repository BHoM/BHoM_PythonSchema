"""Helpers shared by the pytest suites that import generated packages."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
OUTPUT = REPO / ".ci" / "unit-tests" / "_output"


def require_output(name: str) -> Path:
    """Returns the folder of the generated `bhom_schema` package that the NUnit run wrote for a named set ('fixtures' or 'spike'), or fails the test in CI and skips it locally when it is missing.

    The pytest suites for the generated package and the alignment checks call it first, since they all depend on the generator's output.
    """
    package = OUTPUT / name / "bhom_schema"
    if (package / "__init__.py").exists():
        return package
    message = f"{package} not found: run `dotnet test` on the solution first (needs the BHoM assemblies for 'spike')"
    if os.environ.get("CI", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)


def attach(package: Path) -> None:
    """Makes `bhom_schema.<Assembly>...` imports resolve to a generated package folder, ahead of the committed classes in `src`.

    The conftest fixtures of `test_fixtures` and `test_spike` call it so the tests import what the generator just wrote, not the committed package.
    """
    import bhom_schema

    path = str(package)
    if path in bhom_schema.__path__:
        bhom_schema.__path__.remove(path)

    # First, so a test package is not shadowed by a same-named folder of the committed package (for example BHoM)
    bhom_schema.__path__.insert(0, path)
    importlib.invalidate_caches()


def module_names(package: Path) -> list[str]:
    """Lists the dotted module names of every generated class file in a package, skipping `__init__` and `_version` files and the `_support` folder.

    The fixture and spike suites use it to import every generated module and rebuild its model.
    """
    names: list[str] = []
    for file in sorted(package.rglob("*.py")):
        relative = file.relative_to(package.parent).with_suffix("")
        if relative.parts[-1] in ("__init__", "_version") or relative.parts[1] == "_support":
            continue
        names.append(".".join(relative.parts))
    return names


def run_pyright(root: Path, include: str = "bhom_schema") -> subprocess.CompletedProcess[str]:
    """Writes a strict `pyrightconfig.json` in a generated package's root and runs pyright over it, returning the completed process.

    The fixture and spike suites use it to check that the generator's output type-checks cleanly.
    """
    config = root / "pyrightconfig.json"
    config.write_text('{ "include": ["%s"], "typeCheckingMode": "strict", "pythonVersion": "3.12", "extraPaths": ["."] }' % include, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pyright", "--pythonpath", sys.executable],
        cwd=root, capture_output=True, text=True, timeout=600,
    )
