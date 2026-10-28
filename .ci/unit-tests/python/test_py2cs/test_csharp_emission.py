from __future__ import annotations

from pathlib import Path

from helpers import assert_golden, module, package
from py2cs.csharp import Names, emit_new, parse_type
from py2cs.reader import read_package


def draft(tmp_path: Path, files: dict[str, str], clr: str) -> str:
    manifest = read_package(package(tmp_path, files))
    return emit_new(manifest[clr], manifest, read_only_required=True)


def test_names_shorten_and_collect_usings():
    names = Names("BH.oM.Demo")
    assert names.render("System.Collections.Generic.Dictionary<string, BH.oM.Geometry.Point>") == "Dictionary<string, Point>"
    assert names.render("BH.oM.Demo.Local[]") == "Local[]"
    assert names.render("int?") == "int?"
    assert names.render("BH.oM.Other.Point") == "BH.oM.Other.Point", "a second type with the same simple name stays qualified"
    assert names.usings == {"System.Collections.Generic", "BH.oM.Geometry"}


def test_parse_type_shapes():
    node = parse_type("System.Tuple<int, System.Collections.Generic.List<string[,]>>?")
    assert node.name == "System.Tuple" and node.suffix == "?" and node.args[1].args[0].suffix == "[,]"


def test_new_class_with_every_property_kind(tmp_path: Path):
    files = {
        "Demo_oM/Mode.py": module("Mode", "BH.oM.Demo.Mode", "BH.oM.Demo", "Demo_oM", kind="enum", bases="Enum", imports=["from enum import Enum"],
                                  marker_extra=["'renamed_members': {'None_': 'None'}"], body=["None_ = 0", "Fast = 1"]),
        "Demo_oM/IdentityBase.py": module("IdentityBase", "BH.oM.Demo.IdentityBase", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"]),
        "Demo_oM/Everything.py": module(
            "Everything", "BH.oM.Demo.Everything", "BH.oM.Demo", "Demo_oM", bases="SchemaModel, IdentityBase", doc="Has every kind of property.",
            imports=["from bhom_schema.Demo_oM.IdentityBase import IdentityBase", "from bhom_schema.Demo_oM.Mode import Mode",
                     "from datetime import datetime, timedelta", "from decimal import Decimal", "from uuid import UUID, uuid4"],
            body=[
                "Required: str",
                "Text: str = ''",
                "Quoted: str = 'say \"hi\"'",
                "Count: Annotated[int, ClrType('long')] = 3",
                "Small: Annotated[float, ClrType('float')] = 0.5",
                "Ratio: float = 1.5",
                "Flag: bool = Field(default=False, description='A flag.')",
                "Choice: Mode = Mode.None_",
                "Other: Mode = Mode.Fast",
                "Names: set[str] = Field(default_factory=set)",
                "Lookup: dict[str, float] = Field(default_factory=dict)",
                "Values: Annotated[list[float], ClrType('double[]')] = Field(default_factory=list)",
                "Words: Annotated[list[str], ClrType('System.Collections.Generic.IEnumerable<string>')] = Field(default_factory=lambda: ['a', 'b'])",
                "Maybe: int | None = None",
                "Key: UUID = UUID(int=0)",
                "Fresh: UUID = Field(default_factory=uuid4)",
                "Cost: Decimal = Decimal('1.5')",
                "Fixed: datetime = datetime(2020, 1, 2, 3, 4, 5, 0)",
                "Created: datetime = Field(default_factory=datetime.now)",
                "Span: Annotated[float, Quantity('Length', 'm'), DisplayText('Span length')] = Field(default=1.5, description='Distance between supports.')",
            ]),
    }
    assert_golden("Everything.cs", draft(tmp_path, files, "BH.oM.Demo.Everything"))


def test_new_enum_interface_and_generic(tmp_path: Path):
    files = {
        "Demo_oM/Mode.py": module("Mode", "BH.oM.Demo.Mode", "BH.oM.Demo", "Demo_oM", kind="enum", bases="Enum", imports=["from enum import Enum"],
                                  marker_extra=["'renamed_members': {'None_': 'None'}"], body=["None_ = 0", "# Quick.", "Fast = 1"], doc="Speeds."),
        "Demo_oM/Flags.py": module("Flags", "BH.oM.Demo.Flags", "BH.oM.Demo", "Demo_oM", kind="enum", bases="IntFlag", imports=["from enum import IntFlag"],
                                   marker_extra=["'flags': True"], body=["A = 1", "B = 2", "Both = 3"]),
        "Demo_oM/ILabelled.py": module("ILabelled", "BH.oM.Demo.ILabelled", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"],
                                       marker_extra=["'properties': {'Label': {'type': 'string', 'description': 'The label.'}}"]),
        "Demo_oM/Box_1.py": module(
            "Box_1", "BH.oM.Demo.Box`1", "BH.oM.Demo", "Demo_oM", bases="SchemaModel, ILabelled", type_params="[T: ILabelled]",
            marker_extra=["'generic_params': {'T': ['BH.oM.Demo.ILabelled']}"],
            imports=["from bhom_schema.Demo_oM.ILabelled import ILabelled"], body=["Items: list[T] = Field(default_factory=list[T])", "Label: str | None = None"]),
    }
    manifest = read_package(package(tmp_path, files))
    assert_golden("Mode.cs", emit_new(manifest["BH.oM.Demo.Mode"], manifest))
    assert_golden("Flags.cs", emit_new(manifest["BH.oM.Demo.Flags"], manifest))
    assert_golden("ILabelled.cs", emit_new(manifest["BH.oM.Demo.ILabelled"], manifest))
    assert_golden("Box.cs", emit_new(manifest["BH.oM.Demo.Box`1"], manifest))


def test_untranslatable_default_becomes_a_reviewer_note(tmp_path: Path):
    files = {"Demo_oM/Odd.py": module("Odd", "BH.oM.Demo.Odd", "BH.oM.Demo", "Demo_oM", body=["Value: str = some_function()"])}
    manifest = read_package(package(tmp_path, files))
    notes: list[str] = []
    text = emit_new(manifest["BH.oM.Demo.Odd"], manifest, notes)
    assert "public virtual string Value { get; set; }\n" in text
    assert notes == ["the default some_function() of Value could not be translated to C#; set it by hand"]


def test_new_fields_without_a_default_stay_settable(tmp_path: Path):
    files = {"Demo_oM/Loose.py": module("Loose", "BH.oM.Demo.Loose", "BH.oM.Demo", "Demo_oM", body=["Id: str", "Stage: int = Field(0, description='RIBA stage')"])}
    manifest = read_package(package(tmp_path, files))
    notes: list[str] = []
    text = emit_new(manifest["BH.oM.Demo.Loose"], manifest, notes)
    assert "public virtual string Id { get; set; }\n" in text
    assert "public virtual int Stage { get; set; } = 0;" in text
    assert "public Loose(" not in text
    assert notes == ["Id has no default in Python, so it was drafted without an initial value"]


def test_required_fields_become_get_only_properties_set_by_a_constructor(tmp_path: Path):
    files = {"Demo_oM/Fixed.py": module("Fixed", "BH.oM.Demo.Fixed", "BH.oM.Demo", "Demo_oM",
                                        body=["Id: str", "class_: int = Field(alias='class')", "Length: float"])}
    manifest = read_package(package(tmp_path, files))
    text = emit_new(manifest["BH.oM.Demo.Fixed"], manifest, read_only_required=True)
    assert "public virtual string Id { get; }" in text
    assert "public Fixed(string id, int @class, double length)" in text
    assert "Id = id;" in text and "@class = @class;" in text and "public virtual int @class { get; }" in text
    assert_golden("Fixed.cs", text)


def test_same_simple_name_in_two_namespaces_is_written_in_full(tmp_path: Path):
    files = {
        "A_oM/Point.py": module("Point", "BH.oM.A.Point", "BH.oM.A", "A_oM"),
        "B_oM/Point.py": module("Point", "BH.oM.B.Point", "BH.oM.B", "B_oM"),
        "B_oM/Holder.py": module("Holder", "BH.oM.B.Holder", "BH.oM.B", "B_oM",
                                 imports=["from bhom_schema.A_oM.Point import Point as A_Point", "from bhom_schema.B_oM.Point import Point"],
                                 body=["FromA: A_Point | None = None", "Local: Point | None = None"]),
    }
    manifest = read_package(package(tmp_path, files))
    text = emit_new(manifest["BH.oM.B.Holder"], manifest)
    assert "public virtual BH.oM.A.Point FromA { get; set; }" in text
    assert "public virtual BH.oM.B.Point Local { get; set; }" in text
