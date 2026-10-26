"""Builds tiny generated-style Python packages and C# trees on disk for the py2cs tests."""

from __future__ import annotations

import os
import textwrap
from collections.abc import Iterable
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "golden" / "py2cs"


def write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8", newline="\n")
    return path


def assert_golden(name: str, actual: str) -> None:
    """Compare with a committed file; UPDATE_GOLDEN=1 rewrites it (then review the diff)."""
    path = GOLDEN / name
    actual = actual.replace("\r\n", "\n")
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"missing golden file {path} (run with UPDATE_GOLDEN=1)"
    assert actual == path.read_text(encoding="utf-8").replace("\r\n", "\n"), f"{name} differs"


def module(
    cls: str,
    clr: str,
    namespace: str,
    assembly: str,
    repo: str | None = "BHoM/Demo_Toolkit",
    kind: str = "class",
    bases: str = "SchemaModel",
    body: Iterable[str] = (),
    imports: Iterable[str] = (),
    marker_extra: Iterable[str] = (),
    type_params: str = "",
    doc: str | None = None,
) -> str:
    """Source text in the exact style the C# generator writes."""
    lines = ["from __future__ import annotations", ""]
    lines += ["from typing import Annotated, Any, ClassVar", "from pydantic import Field", "from bhom_schema._support import ClrType, DisplayText, Quantity, SchemaModel"]
    lines += list(imports) + ["", "", f"class {cls}{type_params}({bases}):"]
    if doc:
        lines.append(f'    """{doc}"""')
    lines.append("    __bhom__: ClassVar[dict[str, Any]] = {")
    lines += [f"        'clr_name': {clr!r},", f"        'namespace': {namespace!r},", f"        'assembly': {assembly!r},"]
    if repo:
        lines.append(f"        'repo': {repo!r},")
    lines.append(f"        'kind': {kind!r},")
    lines += [f"        {x}," for x in marker_extra]
    lines.append("    }")
    body_lines = list(body)
    if body_lines:
        lines.append("")
        lines += [f"    {line}" for line in body_lines]
    return "\n".join(lines) + "\n"


def package(root: Path, files: dict[str, str]) -> Path:
    """Writes modules under <root>/bhom_schema and returns that folder."""
    pkg = root / "bhom_schema"
    pkg.mkdir(parents=True, exist_ok=True)
    for relative, source in files.items():
        path = pkg / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="\n")
    return pkg


def demo_package(root: Path, extra_fields: Iterable[str] = ()) -> Path:
    """Interface + a ProjectIdentification-like class + an enum + a generic, all in Demo_oM."""
    return package(root, {
        "Demo_oM/IdentityBase.py": module("IdentityBase", "BH.oM.Demo.IdentityBase", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC",
                                          imports=["from abc import ABC"]),
        "Demo_oM/ProjectInfo.py": module(
            "ProjectInfo", "BH.oM.Demo.ProjectInfo", "BH.oM.Demo", "Demo_oM", bases="SchemaModel, IdentityBase",
            imports=["from bhom_schema.Demo_oM.IdentityBase import IdentityBase"],
            body=["Reference: str = ''", "Name: str = ''", *extra_fields]),
        "Demo_oM/Mode.py": module(
            "Mode", "BH.oM.Demo.Mode", "BH.oM.Demo", "Demo_oM", kind="enum", bases="Enum", imports=["from enum import Enum"],
            marker_extra=["'renamed_members': {'None_': 'None'}"], body=["None_ = 0", "# Faster.", "Fast = 1"]),
    })
