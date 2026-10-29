"""The change list py2cs sends to the C# patcher, and a run of the real patcher on a copy of a real file."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from helpers import module, package, require_patcher
from py2cs.patch import build_patch, run_patcher
from py2cs.reader import read_package

PATCHER_INPUTS = Path(__file__).resolve().parents[2] / "golden" / "patcher"

def changes_between(tmp_path: Path, before: list[str], after: list[str], **marker: Any) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Builds two versions of a Demo_oM class Thing from the two bodies and returns the changes, usings and notes that build_patch produces between them.

    The patch change tests use it to see the change list that py2cs sends to the C# patcher.
    """
    def version(name: str, body: list[str]):
        """Reads a package holding IdentityBase, Other and Thing (with the given body or extra fields) and returns its manifest.

        Used by changes_between for its before and after versions.
        """
        return read_package(package(tmp_path / name, {
            "Demo_oM/IdentityBase.py": module("IdentityBase", "BH.oM.Demo.IdentityBase", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
            "Demo_oM/Other.py": module("Other", "BH.oM.Geometry.Other", "BH.oM.Geometry", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
            "Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM", body=body, **marker)}))

    base, head = version("base", before), version("head", after)
    patch = build_patch(Path("Thing.cs"), base["BH.oM.Demo.Thing"], head["BH.oM.Demo.Thing"], head)
    return patch.changes, patch.usings, patch.notes

def test_added_properties_name_their_existing_neighbour(tmp_path: Path):
    """Checks that added properties become addProperty changes that name the existing property they follow, with initialiser, description and quantity attributes, and that a property with no default adds a note and the needed usings.

    Protects the member-level change list that the patcher applies.
    """
    changes, usings, notes = changes_between(tmp_path, ["A: int = 0", "B: int = 0"], [
        "First: str = ''", "A: int = 0", "Mid: Annotated[float, Quantity('Length', 'm')] = Field(default=1.5, description='Middle.')", "B: int = 0", "Last: str"])
    assert changes == [
        {"kind": "addProperty", "name": "First", "type": "string", "initialiser": '""', "add": [], "after": None},
        {"kind": "addProperty", "name": "Mid", "type": "double", "initialiser": "1.5", "add": ['Description("Middle.")', "Length"], "after": "A"},
        {"kind": "addProperty", "name": "Last", "type": "string", "initialiser": None, "add": [], "after": "B"},
    ]
    assert usings == ["BH.oM.Quantities.Attributes", "System.ComponentModel"]
    assert notes == ["Last has no default in Python, so it was added without an initial value"]

def test_changed_and_removed_properties(tmp_path: Path):
    """Checks that a changed type, default, description or quantity, and a removed property, become the matching change entries and that an untranslatable default adds a note.

    Protects the member-level change list that the patcher applies.
    """
    changes, _, notes = changes_between(tmp_path,
        ["A: int = 0", "B: str = Field(default='', description='Old.')", "C: Annotated[float, Quantity('Length', 'm')] = 0.0", "D: int = 0", "E: str = ''"],
        ["A: float = 0.0", "B: str = Field(default='x', description='New.')", "C: Annotated[float, Quantity('Area', 'm2'), DisplayText('Area')] = 0.0", "E: str = odd()"])
    assert changes == [
        {"kind": "setPropertyType", "name": "A", "type": "double"},
        {"kind": "setPropertyInitialiser", "name": "A", "initialiser": "0.0"},
        {"kind": "setPropertyInitialiser", "name": "B", "initialiser": '"x"'},
        {"kind": "setDescription", "name": "B", "description": '"New."'},
        {"kind": "setAttributes", "name": "C", "remove": ["Length"], "add": ["Area", 'DisplayText("Area")']},
        {"kind": "removeProperty", "name": "D"},
    ]
    assert notes == ["the default odd() of E could not be translated to C#; set it by hand"]

def test_class_description_and_bases(tmp_path: Path):
    """Checks that a changed class description and changed bases become setDescription and setBases changes and that only the added base adds a using.

    Protects the member-level change list that the patcher applies.
    """
    before = read_package(package(tmp_path / "base", {
        "Demo_oM/IdentityBase.py": module("IdentityBase", "BH.oM.Demo.IdentityBase", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
        "Demo_oM/Other.py": module("Other", "BH.oM.Geometry.Other", "BH.oM.Geometry", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
        "Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM", bases="SchemaModel, IdentityBase", doc="Old.",
                                   imports=["from bhom_schema.Demo_oM.IdentityBase import IdentityBase"])}))
    after = read_package(package(tmp_path / "head", {
        "Demo_oM/IdentityBase.py": module("IdentityBase", "BH.oM.Demo.IdentityBase", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
        "Demo_oM/Other.py": module("Other", "BH.oM.Geometry.Other", "BH.oM.Geometry", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
        "Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM", bases="SchemaModel, Other", doc="New.",
                                   imports=["from bhom_schema.Demo_oM.Other import Other"])}))
    patch = build_patch(Path("Thing.cs"), before["BH.oM.Demo.Thing"], after["BH.oM.Demo.Thing"], after)
    assert patch.changes == [
        {"kind": "setDescription", "description": '"New."'},
        {"kind": "setBases", "remove": ["IdentityBase"], "add": ["Other"]},
    ]
    assert patch.usings == ["BH.oM.Geometry", "System.ComponentModel"], "only the added base needs a using"

def test_enum_members(tmp_path: Path):
    """Checks that added, renumbered and removed enum members become addEnumMember, setEnumValue and removeEnumMember changes.

    Protects the member-level change list that the patcher applies to enums.
    """
    enum = {"kind": "enum", "bases": "Enum", "imports": ["from enum import Enum"]}
    changes, _, _ = changes_between(tmp_path, ["A = 1", "B = 2", "C = 3"], ["A = 1", "# Brand new.", "New = 4", "B = 5"], **enum)
    assert changes == [
        {"kind": "addEnumMember", "name": "New", "value": "4", "description": '"Brand new."', "after": "A"},
        {"kind": "setEnumValue", "name": "B", "value": "5"},
        {"kind": "removeEnumMember", "name": "C"},
    ]

def test_kind_and_generic_changes_are_left_to_a_person(tmp_path: Path):
    """Checks that an unchanged class gives no notes and that a change of kind gives no change entries and a note to change the declaration by hand.

    Protects the patcher from editing declarations that only a person should change.
    """
    _, _, notes = changes_between(tmp_path, ["A: int = 0"], ["A: int = 0"])
    assert notes == []
    before = read_package(package(tmp_path / "b", {"Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM")}))
    after = read_package(package(tmp_path / "a", {"Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM", kind="abstract", bases="SchemaModel, ABC",
                                                                             imports=["from abc import ABC"])}))
    patch = build_patch(Path("Thing.cs"), before["BH.oM.Demo.Thing"], after["BH.oM.Demo.Thing"], after)
    assert patch.changes == [] and patch.notes == ["the kind changed from class to abstract; change the declaration by hand"]

def test_the_real_patcher_changes_only_the_new_lines(tmp_path: Path):
    """Checks that running the real C# patcher on a copy of a real file adds only the new property (with its description and using) and leaves the input file unchanged.

    Protects the Roslyn patcher round trip behind the plan stage.
    """
    require_patcher()
    original = PATCHER_INPUTS / "ProjectIdentification.cs"
    copy = tmp_path / "ProjectIdentification.cs"
    shutil.copyfile(original, copy)

    def project_identification(root: Path, extra: list[str]):
        """Builds a package with the dKoP IdKoPObject interface and ProjectIdentification class (plus any extra fields) and returns its manifest.

        The real patcher test uses it for the base and head versions.
        """
        return read_package(package(root, {
            "dKoP_oM/IdKoPObject.py": module("IdKoPObject", "BH.oM.dKoP.IdKoPObject", "BH.oM.dKoP", "dKoP_oM", repo="BHoM/dKoP_Toolkit", kind="interface", bases="ABC",
                                             imports=["from abc import ABC"]),
            "dKoP_oM/ProjectIdentification.py": module(
                "ProjectIdentification", "BH.oM.dKoP.ProjectIdentification", "BH.oM.dKoP", "dKoP_oM", repo="BHoM/dKoP_Toolkit", bases="SchemaModel, IdKoPObject",
                imports=["from bhom_schema.dKoP_oM.IdKoPObject import IdKoPObject"],
                body=["ProjectReference: str = ''", "ProjectName: str = ''", "ProjectLocation: str = ''", "AdditionalReferences: str = ''", *extra])}))

    base = project_identification(tmp_path / "base", [])
    head = project_identification(tmp_path / "head", ["ProjectNumber: str = Field('', description='The project number.')"])
    clr = "BH.oM.dKoP.ProjectIdentification"
    [result] = run_patcher([build_patch(copy, base[clr], head[clr], head)])

    source = original.read_bytes().decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in source else "\n"
    anchor = '        public virtual string AdditionalReferences { get; set; } = "";' + nl
    added = nl + '        [Description("The project number.")]' + nl + '        public virtual string ProjectNumber { get; set; } = "";' + nl
    expected = source.replace(anchor, anchor + added).replace("using System.Text;" + nl, "using System.Text;" + nl + "using System.ComponentModel;" + nl)
    assert result.error is None and result.notes == []
    assert result.text == expected
    assert copy.read_bytes() == original.read_bytes(), "the input file is only read"
