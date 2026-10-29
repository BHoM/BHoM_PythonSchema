"""Builds tiny generated-style Python packages and C# trees on disk for the py2cs tests."""

from __future__ import annotations

import os
import textwrap
from collections.abc import Iterable
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parents[2] / "golden" / "py2cs"


def require_patcher() -> None:
    """Skips the calling test when the built C# patcher is missing, or fails it when the CI environment variable is true.

    Every test that plans changes to an existing C# file calls it first, because those plans run the Roslyn patcher.
    """
    from py2cs.patch import BUILD_HINT, default_patcher

    if default_patcher().exists():
        return
    message = f"the C# patcher is not built; {BUILD_HINT}"
    if os.environ.get("CI", "").lower() == "true":
        pytest.fail(message)
    pytest.skip(message)


def write(root: Path, relative: str, source: str) -> Path:
    """Writes dedented source text to a file under root (creating folders) and returns its path.

    Used by the py2cs tests that need one hand-made source file on disk.
    """
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8", newline="\n")
    return path


def assert_golden(name: str, actual: str) -> None:
    """Asserts that the text equals the committed golden file under golden/py2cs, ignoring line endings, or rewrites that file when UPDATE_GOLDEN=1.

    Protects the whole-file C# that csharp.emit_new drafts for new types from unintended changes.
    """
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
    """Builds the source text of one generated-style Python module (a class, enum or interface with its __bhom__ marker, imports and body) in the exact style the C# generator writes.

    The base of every hand-built package in the py2cs tests.
    """
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
    """Writes the given modules under <root>/bhom_schema and returns that folder, which py2cs reads as the Python package (base or head of a change).

    Used by nearly every py2cs test to set up input.
    """
    pkg = root / "bhom_schema"
    pkg.mkdir(parents=True, exist_ok=True)
    for relative, source in files.items():
        path = pkg / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8", newline="\n")
    return pkg


def demo_package(root: Path, extra_fields: Iterable[str] = ()) -> Path:
    """Builds the standard demo package in Demo_oM: an interface IdentityBase, a class ProjectInfo that derives from it (plus any extra fields) and an enum Mode.

    The default input of the diff, plan, align, PR and status tests.
    """
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


def cs(namespace: str, declaration: str) -> str:
    """Returns the text of a minimal C# file that declares one type in the given namespace.

    csharp_tree uses it to fake the existing .cs files of a C# repository.
    """
    return f"using System;\n\nnamespace {namespace}\n{{\n    {declaration}\n    {{\n    }}\n}}\n"


def csharp_tree(root: Path) -> Path:
    """Writes a fake C# repository (Demo_Toolkit) whose folders do not follow the namespaces, with same-named types, several types in one file and an obj folder to ignore, and returns its path.

    The locate, place, plan, PR and breaking-change tests run against it.
    """
    repo = root / "Demo_Toolkit"
    files = {
        "Demo_oM/AdministrativeInformation/ProjectInfo.cs": cs("BH.oM.Demo", "public class ProjectInfo : IdentityBase"),
        "Demo_oM/AdministrativeInformation/IdentityBase.cs": cs("BH.oM.Demo", "public interface IdentityBase : IObject"),
        "Demo_oM/Enums/Colour.cs": cs("BH.oM.Demo", "public enum Colour"),
        "Demo_oM/Enums/Shade.cs": cs("BH.oM.Demo", "public enum Shade"),
        "Demo_oM/Enums/Elements/Wall.cs": cs("BH.oM.Demo.Elements", "public class Wall : IObject"),
        "Demo_oM/Misc/Several.cs": cs("BH.oM.Demo", "public class Alpha : IObject") + cs("BH.oM.Demo", "public class Beta : IObject"),
        "Demo_oM/Curves/Line.cs": cs("BH.oM.Demo", "public class Line : IObject"),
        "Demo_oM/Other/Line.cs": cs("BH.oM.Other", "public class Line : IObject"),
        "Demo_oM/Elements/Door.cs": cs("BH.oM.Demo.Elements", "public class Door : IObject"),
        "Demo_oM/obj/Debug/Ghost.cs": cs("BH.oM.Demo", "public class Ghost : IObject"),
        "Other_oM/Thing.cs": cs("BH.oM.Other", "public class Thing : IObject"),
    }
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return repo
