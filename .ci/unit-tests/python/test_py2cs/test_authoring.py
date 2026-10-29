"""Python written by people, not by the generator: common idioms, classes without a __bhom__ marker, and clear errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers import demo_package, module, package, write
from py2cs.__main__ import main
from py2cs.check import check_package
from py2cs.csharp import emit_new
from py2cs.diff import diff_manifests
from py2cs.reader import ReadError, ReadErrors, read_package

def demo_with_folders(tmp_path: Path) -> Path:
    """Builds the demo package plus a generated Wall class in a Demo_oM/Elements sub folder.

    test_namespace_of_a_new_folder_follows_the_generator_rule uses it so the reader can work out the namespace of a class in a new sub folder.
    """
    pkg = demo_package(tmp_path)
    (pkg / "Demo_oM" / "Elements").mkdir()
    (pkg / "Demo_oM" / "Elements" / "Wall.py").write_text(module("Wall", "BH.oM.Demo.Elements.Wall", "BH.oM.Demo.Elements", "Demo_oM"), encoding="utf-8")
    return pkg

# ---------------------------------------------------------------- idioms

def test_common_typing_idioms_are_understood(tmp_path: Path):
    """Checks that the reader understands the usual ways a person writes a field (Optional, Union, List, Dict, typing., Field with positional or keyword default, required Field, quoted forward reference, ClassVar skipped) and gives the right C# type, default and description.

    Protects the reader stage of py2cs, which must accept hand-written Python and not only generator output.
    """
    pkg = demo_package(tmp_path)
    write(pkg, "Demo_oM/Idioms.py", """
        import typing
        from typing import Dict, List, Optional, Union
        import pydantic
        from pydantic import Field
        from bhom_schema._support import SchemaModel
        from bhom_schema.Demo_oM.Mode import Mode

        class Idioms(SchemaModel):
            \"\"\"Every common way of writing a field.\"\"\"
            Stage: Optional[int] = None
            Other: Union[None, str] = None
            Names: List[str] = Field(default_factory=list)
            Lookup: Dict[str, float] = Field(default_factory=dict)
            Qualified: typing.List[int] = Field(default_factory=list)
            Positional: int = Field(0, description="RIBA stage")
            Keyword: int = pydantic.Field(default=2)
            Required: str = Field(..., description="Must be given")
            Forward: "Mode | None" = None
            Constant: typing.ClassVar[int] = 3
    """)
    info = read_package(pkg)["BH.oM.Demo.Idioms"]
    props = {p.name: p for p in info.properties}
    assert {n: p.clr_type for n, p in props.items()} == {
        "Stage": "int?", "Other": "string", "Names": "System.Collections.Generic.List<string>",
        "Lookup": "System.Collections.Generic.Dictionary<string, double>", "Qualified": "System.Collections.Generic.List<int>",
        "Positional": "int", "Keyword": "int", "Required": "string", "Forward": "BH.oM.Demo.Mode?"}
    assert (props["Positional"].has_default, props["Positional"].default, props["Positional"].description) == (True, "0", "RIBA stage")
    assert (props["Keyword"].has_default, props["Keyword"].default) == (True, "2")
    assert (props["Required"].has_default, props["Required"].description) == (False, "Must be given")
    assert "Constant" not in props

def test_positional_field_default_drafts_a_settable_property(tmp_path: Path):
    """Checks that Field(0, description=...) is read as a field with a default, so the drafted C# property is settable with an initial value and the class gets no read-only constructor.

    Protects the reader and csharp.emit_new from a past bug that read such a field as required.
    """
    pkg = demo_package(tmp_path, ["Stage: int = Field(0, description='RIBA stage')"])
    manifest = read_package(pkg)
    text = emit_new(manifest["BH.oM.Demo.ProjectInfo"], manifest)
    assert "public virtual int Stage { get; set; } = 0;" in text
    assert "public ProjectInfo(" not in text

# ---------------------------------------------------------------- worked-out markers

def test_a_new_class_without_a_marker_is_read_not_skipped(tmp_path: Path):
    """Checks that a hand-written class with no __bhom__ marker is read with namespace, assembly, repository, kind and bases worked out from its folder and neighbours, and that diff reports it as added.

    Protects the diff stage from a past bug where such a class was skipped and the PR looked unchanged.
    """
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head")
    write(head_root, "Demo_oM/ProjectStage.py", """
        from bhom_schema._support import SchemaModel
        from bhom_schema.Demo_oM.IdentityBase import IdentityBase

        class ProjectStage(SchemaModel, IdentityBase):
            \"\"\"A RIBA stage.\"\"\"
            Stage: int = 0
    """)
    head = read_package(head_root)
    info = head["BH.oM.Demo.ProjectStage"]
    assert (info.namespace, info.assembly, info.repo, info.kind) == ("BH.oM.Demo", "Demo_oM", "BHoM/Demo_Toolkit", "class")
    assert info.bases == ["BH.oM.Demo.IdentityBase"]
    assert info.notes and "worked out" in info.notes[0]
    assert [(c.clr_name, c.kind) for c in diff_manifests(base, head).changes] == [("BH.oM.Demo.ProjectStage", "added")]

def test_namespace_of_a_new_folder_follows_the_generator_rule(tmp_path: Path):
    """Checks that a class in a new sub folder gets the namespace the generator would use (the parent namespace plus the folder name).

    Protects the namespace of the new C# files that py2cs drafts from hand-written Python.
    """
    pkg = demo_with_folders(tmp_path)
    write(pkg, "Demo_oM/Elements/Openings/Door.py", """
        from bhom_schema._support import SchemaModel

        class Door(SchemaModel):
            Width: float = 0.9
    """)
    info = read_package(pkg)["BH.oM.Demo.Elements.Openings.Door"]
    assert info.namespace == "BH.oM.Demo.Elements.Openings"

def test_kind_generic_and_enum_details_are_worked_out(tmp_path: Path):
    """Checks that the reader works out an interface (I prefix), a generic class with constraints (PEP 695 type parameters) and a flags enum (IntFlag, None_ read as None) for classes without a marker.

    Protects the drafting of new C# types from hand-written Python.
    """
    pkg = demo_package(tmp_path)
    write(pkg, "Demo_oM/ILabelled.py", """
        from bhom_schema.Demo_oM.IdentityBase import IdentityBase

        class ILabelled(IdentityBase):
            Label: str
    """)
    write(pkg, "Demo_oM/Group_1.py", """
        from pydantic import Field
        from bhom_schema._support import SchemaModel
        from bhom_schema.Demo_oM.ILabelled import ILabelled

        class Group_1[T: ILabelled](SchemaModel):
            Items: list[T] = Field(default_factory=list)
    """)
    write(pkg, "Demo_oM/Access.py", """
        from enum import IntFlag

        class Access(IntFlag):
            None_ = 0
            Read = 1
            Write = 2
    """)
    manifest = read_package(pkg)
    assert manifest["BH.oM.Demo.ILabelled"].kind == "interface"
    assert [(p.name, p.clr_type) for p in manifest["BH.oM.Demo.ILabelled"].properties] == [("Label", "string")]
    group = manifest["BH.oM.Demo.Group`1"]
    assert (group.name, group.generic_params[0].constraints) == ("BH.oM.Demo.Group<T>", ["BH.oM.Demo.ILabelled"])
    access = manifest["BH.oM.Demo.Access"]
    assert access.kind == "enum" and access.flags and [m.name for m in access.members] == ["None", "Read", "Write"]

def test_a_new_assembly_folder_is_an_error(tmp_path: Path):
    """Checks that a class in a folder that is not an existing assembly folder (Brand_oM) is a read error.

    Protects the reader from inventing a C# assembly, which only a person can create.
    """
    pkg = demo_package(tmp_path)
    write(pkg, "Brand_oM/Thing.py", """
        from bhom_schema._support import SchemaModel

        class Thing(SchemaModel):
            X: int = 0
    """)
    with pytest.raises(ReadErrors, match="Brand_oM is not an existing assembly folder"):
        read_package(pkg)

# ---------------------------------------------------------------- errors

def test_problems_are_collected_per_file_and_the_rest_is_read(tmp_path: Path):
    """Checks that read errors (a second class in a file, an unsupported type, an underscore field name) are collected with file and line while the rest of the package is still read.

    Lets one py2cs run report every Python problem of a PR at once.
    """
    pkg = demo_package(tmp_path)
    write(pkg, "Demo_oM/Broken.py", """
        from collections.abc import Sequence
        from bhom_schema._support import SchemaModel

        class Broken(SchemaModel):
            Good: int = 0
            Bad: Sequence[int] = ()
            _hidden: int = 0

        class Helper(SchemaModel):
            X: int = 0
    """)
    errors: list[ReadError] = []
    manifest = read_package(pkg, errors)
    assert "BH.oM.Demo.ProjectInfo" in manifest
    assert [p.name for p in manifest["BH.oM.Demo.Broken"].properties] == ["Good"]
    messages = [str(e) for e in errors]
    assert messages == [
        "Demo_oM/Broken.py:9: only one class per file is read; move Helper to its own file",
        "Demo_oM/Broken.py:6: Bad: unsupported type 'Sequence'; use str, int, float, bool, Decimal, datetime, timedelta, UUID, Any, list[...], dict[...], "
        "set[...], tuple[...], X | None, or a bhom_schema class",
        "Demo_oM/Broken.py:7: _hidden: a field name cannot start with an underscore (Pydantic treats it as private)",
    ]

def test_two_files_declaring_the_same_class_is_an_error(tmp_path: Path):
    """Checks that the same C# class declared in two Python files is reported as one read error naming both files.

    Protects the manifest, which needs a single source for each class.
    """
    pkg = demo_package(tmp_path)
    (pkg / "Demo_oM" / "Copy.py").write_text((pkg / "Demo_oM" / "ProjectInfo.py").read_text(encoding="utf-8"), encoding="utf-8")
    errors: list[ReadError] = []
    read_package(pkg, errors)
    assert [str(e) for e in errors] == ["Demo_oM/ProjectInfo.py: BH.oM.Demo.ProjectInfo is already declared in Demo_oM/Copy.py"]

def test_command_line_reports_problems_instead_of_a_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that py2cs diff prints the Python read errors on stderr and exits with 1 instead of a traceback.

    Protects the diff command that the linked-PR workflow runs on the PR's Python.
    """
    demo_package(tmp_path / "base")
    head = demo_package(tmp_path / "head", ["Stage: Sequence[int] = ()"])
    status = main(["diff", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(head), "--out", str(tmp_path / "d.json")])
    assert status == 1
    err = capsys.readouterr().err
    assert "error: Demo_oM/ProjectInfo.py:" in err and "unsupported type 'Sequence'" in err and "1 problems in the Python files" in err

# ---------------------------------------------------------------- check

def test_check_lists_errors_and_missing_descriptions(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that check_package returns warnings for unmarked classes and missing class or property descriptions, that py2cs check exits 0 for warnings only, and exits 1 and prints the error for an unsupported union.

    Protects the check step of the PR checks, which lists problems of hand-written Python before any C# is drafted.
    """
    base = demo_package(tmp_path / "base")
    head = demo_package(tmp_path / "head", ["Stage: int = 0", "Note: str = Field(default='', description='A note.')"])
    write(head, "Demo_oM/Fresh.py", """
        from bhom_schema._support import SchemaModel

        class Fresh(SchemaModel):
            X: int = 0
    """)
    result = check_package(head, base)
    assert result.errors == []
    assert result.warnings == [
        "Demo_oM/Fresh.py: no __bhom__ marker was written, so it was worked out: C# name BH.oM.Demo.Fresh, repository BHoM/Demo_Toolkit, kind class",
        "Demo_oM/Fresh.py: Fresh has no description; add a docstring (BHoM requires one on every oM class)",
        "Demo_oM/Fresh.py: Fresh.X has no description; add Field(description=...) (BHoM requires one on every oM property)",
        "Demo_oM/ProjectInfo.py: ProjectInfo.Stage has no description; add Field(description=...) (BHoM requires one on every oM property)",
    ]

    assert main(["check", "--root", str(head)]) == 0
    write(head, "Demo_oM/Bad.py", """
        from bhom_schema._support import SchemaModel

        class Bad(SchemaModel):
            X: int | str = 0
    """)
    capsys.readouterr()
    assert main(["check", "--root", str(head)]) == 1
    assert "error: Demo_oM/Bad.py:4: X: unsupported union" in capsys.readouterr().out
