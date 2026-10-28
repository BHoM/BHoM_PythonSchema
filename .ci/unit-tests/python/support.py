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
    """The generated package folder, made by the NUnit run (dotnet test). Missing output fails in CI and skips locally."""
    package = OUTPUT / name / "bhom_schema"
    if (package / "__init__.py").exists():
        return package
    message = f"{package} not found: run `dotnet test` on the solution first (needs the BHoM assemblies for 'spike')"
    if os.environ.get("CI", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)


def attach(package: Path) -> None:
    """Make `bhom_schema.<Assembly>...` resolve to the generated folder, which wins over the committed classes in src."""
    import bhom_schema

    path = str(package)
    if path in bhom_schema.__path__:
        bhom_schema.__path__.remove(path)

    # First, so a test package is not shadowed by a same-named folder of the committed package (for example BHoM)
    bhom_schema.__path__.insert(0, path)
    importlib.invalidate_caches()


def module_names(package: Path) -> list[str]:
    names: list[str] = []
    for file in sorted(package.rglob("*.py")):
        relative = file.relative_to(package.parent).with_suffix("")
        if relative.parts[-1] == "__init__" or relative.parts[1] == "_support":
            continue
        names.append(".".join(relative.parts))
    return names


def run_pyright(root: Path, include: str = "bhom_schema") -> subprocess.CompletedProcess[str]:
    """Pyright strict over a generated package folder."""
    config = root / "pyrightconfig.json"
    config.write_text('{ "include": ["%s"], "typeCheckingMode": "strict", "pythonVersion": "3.12", "extraPaths": ["."] }' % include, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pyright", "--pythonpath", sys.executable],
        cwd=root, capture_output=True, text=True, timeout=600,
    )
