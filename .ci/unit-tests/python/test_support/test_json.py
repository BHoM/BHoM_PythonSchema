"""The JSON of the hand-written support package: `_t`, `_bhomVersion`, interface fields and enums, as BHoM_JSONSchema describes them.

The classes here are small stand-ins for generated ones, so these tests need no generated output.
"""

from __future__ import annotations

import json
import sys
import types
from abc import ABC
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from bhom_schema._support import BHoMEnum, BHoMFlags, Polymorphic, SchemaModel

class ICurve(ABC):
    """A stand-in interface with two implementers."""
    __bhom__: ClassVar[dict[str, Any]] = {
        "clr_name": "BH.oM.Geometry.ICurve", "kind": "interface",
        "implementers": {"BH.oM.Geometry.Line": "TestAsm.Line", "BH.oM.Geometry.Arc": "TestAsm.Arc"},
    }

class INothing(ABC):
    """A stand-in interface that nothing implements."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Geometry.INothing", "kind": "interface"}

class Point(SchemaModel):
    """A stand-in class."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Geometry.Point", "kind": "class"}
    X: float = 0.0

class Line(SchemaModel, ICurve):
    """A stand-in implementer with required fields."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Geometry.Line", "kind": "class"}
    Start: Point
    End: Point

class Arc(SchemaModel, ICurve):
    """A stand-in implementer with defaults only."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Geometry.Arc", "kind": "class"}
    Radius: float = 1.0

class Edge(SchemaModel):
    """A stand-in class with interface fields of every shape."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Structure.Edge", "kind": "class"}
    Curve: Polymorphic[ICurve]
    Curves: list[Polymorphic[ICurve]] = []
    Maybe: Polymorphic[ICurve] | None = None
    Never: Polymorphic[INothing] | None = None

class Mode(BHoMEnum):
    """A stand-in enum with a member that C# calls None."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Mode", "kind": "enum", "renamed_members": {"None_": "None"}}
    None_ = 0
    Fast = 1

class Options(BHoMFlags):
    """A stand-in flags enum with a named combination."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Options", "kind": "enum", "flags": True}
    A = 1
    B = 2
    Both = 3

class Holder(SchemaModel):
    """A stand-in class with enum fields."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Holder", "kind": "class"}
    Level: Mode = Mode.Fast
    Flags: Options = Options.A

class Sets(SchemaModel):
    """A stand-in class with a list that BHoM may write as a FragmentSet."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Sets", "kind": "class"}
    Fragments: list[Point] = []

LINE = {"_t": "BH.oM.Geometry.Line", "Start": {"X": 1}, "End": {"X": 2}}

@pytest.fixture(autouse=True)
def implementer_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes `bhom_schema.TestAsm.Line` and `.Arc` importable, as the generated modules of the implementers would be."""
    for cls in (Line, Arc):
        module = types.ModuleType(f"bhom_schema.TestAsm.{cls.__name__}")
        setattr(module, cls.__name__, cls)
        monkeypatch.setitem(sys.modules, module.__name__, module)

# ---------------------------------------------------------------- _t and _bhomVersion

def test_every_object_is_written_with_its_class_name_first():
    """Checks that saving a model writes `_t` as the first entry, for the model and for the models inside it."""
    data = json.loads(Edge(Curve=Line(Start=Point(X=1), End=Point(X=2))).model_dump_json())
    assert list(data)[0] == "_t" and data["_t"] == "BH.oM.Structure.Edge"
    assert data["Curve"]["_t"] == "BH.oM.Geometry.Line" and data["Curve"]["Start"]["_t"] == "BH.oM.Geometry.Point"

def test_a_type_tag_is_optional_but_must_be_right_when_it_is_there():
    """Checks that `_t` may be left out, is accepted when it names the class, and is refused when it names another class."""
    assert Point.model_validate({"X": 1}).X == 1
    assert Point.model_validate({"_t": "BH.oM.Geometry.Point", "X": 1}).X == 1
    with pytest.raises(ValidationError, match="_t is BH.oM.Geometry.Arc, but this class is BH.oM.Geometry.Point"):
        Point.model_validate({"_t": "BH.oM.Geometry.Arc"})

def test_bhom_version_is_left_out_until_it_is_set_and_read_back():
    """Checks that `_bhomVersion` is not written when empty, and is written, and read, under that name when set."""
    assert "_bhomVersion" not in json.loads(Point().model_dump_json())
    versioned = Point(bhom_version="10.0")
    assert json.loads(versioned.model_dump_json())["_bhomVersion"] == "10.0"
    assert Point.model_validate_json(versioned.model_dump_json()).bhom_version == "10.0"

def test_a_fragment_set_written_as_an_object_is_read_as_a_list():
    """Checks that BHoM's `{"_t": "BH.oM.Base.FragmentSet", "_v": [...]}` form and a plain array both fill a list field."""
    wrapped = {"Fragments": {"_t": "BH.oM.Base.FragmentSet", "_v": [{"X": 1}, {"X": 2}]}}
    assert [p.X for p in Sets.model_validate(wrapped).Fragments] == [1, 2]
    assert [p.X for p in Sets.model_validate({"Fragments": [{"X": 3}]}).Fragments] == [3]
    assert Sets.model_validate({"Fragments": {"_t": "BH.oM.Base.FragmentSet"}}).Fragments == []

def test_the_json_schema_of_a_class_has_the_optional_type_property():
    """Checks that `model_json_schema()` lists `_t` (fixed to the class name) and `_bhomVersion`, as the BHoM_JSONSchema files do."""
    properties = Point.model_json_schema()["properties"]
    assert properties["_t"]["const"] == "BH.oM.Geometry.Point" and "_bhomVersion" in properties

# ---------------------------------------------------------------- interface fields

def test_an_interface_field_loads_the_class_named_by_its_type_tag():
    """Checks the loop that failed before: an Edge saved to JSON loads again, and its curve is a Line, not just any curve."""
    edge = Edge(Curve=Line(Start=Point(X=1), End=Point(X=2)), Curves=[Arc(Radius=3)])
    again = Edge.model_validate_json(edge.model_dump_json())
    assert type(again.Curve) is Line and again.Curve.End.X == 2
    assert type(again.Curves[0]) is Arc and again.Curves[0].Radius == 3
    assert again == edge

def test_the_class_is_imported_only_when_a_type_tag_names_it(monkeypatch: pytest.MonkeyPatch):
    """Checks that an implementer's module is not imported until JSON names it, so loading one class does not load the whole package."""
    imported: list[str] = []
    real = __import__("importlib").import_module
    monkeypatch.setattr("bhom_schema._support.polymorphic.importlib.import_module", lambda name: (imported.append(name), real(name))[1])
    Edge.model_validate({"Curve": {"_t": "BH.oM.Geometry.Arc"}})
    assert imported == ["bhom_schema.TestAsm.Arc"]

def test_objects_of_the_interface_are_accepted_as_they_are_and_others_are_not():
    """Checks that an object of an implementing class needs no `_t`, and an object of an unrelated class is refused."""
    arc = Arc()
    assert Edge(Curve=arc).Curve is arc
    with pytest.raises(ValidationError, match="expected an object of ICurve"):
        Edge(Curve=Point())  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="expected an object of ICurve"):
        Edge.model_validate({"Curve": "Line"})

def test_a_value_validated_as_an_interface_must_carry_a_known_type_tag():
    """Checks the two refusals: no `_t` at all, and a `_t` that is not one of the interface's implementers."""
    with pytest.raises(ValidationError, match="needs _t, the name of its class"):
        Edge.model_validate({"Curve": {"Radius": 1}})
    with pytest.raises(ValidationError, match="BH.oM.Other.Foo is not a class of ICurve in bhom_schema"):
        Edge.model_validate({"Curve": {"_t": "BH.oM.Other.Foo"}})

def test_the_error_names_the_real_problem_of_the_chosen_class_only():
    """Checks that a Line with a missing end reports that field and nothing about Arc, the other implementer."""
    with pytest.raises(ValidationError) as error:
        Edge.model_validate({"Curve": {"_t": "BH.oM.Geometry.Line", "Start": {"X": 1}}})
    text = str(error.value)
    assert "End" in text and "Field required" in text and "Radius" not in text and "Arc" not in text

def test_optional_and_list_interface_fields_work_too():
    """Checks `Polymorphic[...] | None` and `list[Polymorphic[...]]`: empty, null and filled."""
    assert Edge.model_validate({"Curve": {"_t": "BH.oM.Geometry.Arc"}, "Maybe": None}).Maybe is None
    again = Edge.model_validate({"Curve": {"_t": "BH.oM.Geometry.Arc"}, "Curves": [LINE, {"_t": "BH.oM.Geometry.Arc"}]})
    assert [type(c) for c in again.Curves] == [Line, Arc]

def test_an_interface_with_no_implementers_accepts_objects_only():
    """Checks that an interface the generator found no implementer for refuses JSON, with a clear message, instead of failing in some other way."""
    with pytest.raises(ValidationError, match="is not a class of INothing"):
        Edge.model_validate({"Curve": {"_t": "BH.oM.Geometry.Arc"}, "Never": {"_t": "BH.oM.Geometry.Arc"}})

def test_the_json_schema_of_an_interface_field_is_the_one_of_bhom_json_schema():
    """Checks that the field's schema requires `_t`, lists the implementers as its allowed values, and picks each class with an if/then rule."""
    schema = Edge.model_json_schema()
    interface = schema["$defs"]["Polymorphic_ICurve_"]
    assert interface["required"] == ["_t"]
    assert interface["properties"]["_t"]["enum"] == ["BH.oM.Geometry.Line", "BH.oM.Geometry.Arc"]
    rule = interface["allOf"][0]
    assert rule["if"]["properties"]["_t"]["const"] == "BH.oM.Geometry.Line" and rule["if"]["required"] == ["_t"]
    assert rule["then"] == {"$ref": "#/$defs/Line"}
    assert schema["properties"]["Curve"] == {"$ref": "#/$defs/Polymorphic_ICurve_"}

# ---------------------------------------------------------------- enums

def test_an_enum_is_written_as_its_name_and_none_keeps_its_csharp_spelling():
    """Checks that members are saved by name, and that `None_` is saved as "None" from the renamed members of the marker."""
    assert json.loads(Holder().model_dump_json())["Level"] == "Fast"
    assert json.loads(Holder(Level=Mode.None_).model_dump_json())["Level"] == "None"

def test_an_enum_is_read_from_a_name_a_number_or_the_object_form():
    """Checks every form BHoM JSON, or a Python caller, may hold an enum in."""
    assert Holder.model_validate({"Level": "None"}).Level is Mode.None_
    assert Holder.model_validate({"Level": 1}).Level is Mode.Fast
    form = {"_t": "System.Enum", "TypeName": {"_t": "System.Type", "Name": "BH.oM.Mode"}, "Value": "Fast"}
    assert Holder.model_validate({"Level": form}).Level is Mode.Fast
    assert Holder(Level=Mode.None_).Level is Mode.None_

def test_an_enum_refuses_what_is_not_a_member():
    """Checks the messages for an unknown name, an unknown number, a boolean and several names for a plain enum."""
    for bad, message in (("Slow", "Slow is not a member of Mode"), (7, "7 is not a value of Mode"), (True, "True is not a value of Mode"),
                         ("Fast, None", "names several members")):
        with pytest.raises(ValidationError, match=message):
            Holder.model_validate({"Level": bad})

def test_flags_are_written_and_read_as_comma_separated_names():
    """Checks a defined combination (by its own name), an undefined combination (the single flags joined), and reading both back."""
    assert json.loads(Holder(Flags=Options.A).model_dump_json())["Flags"] == "A"
    assert json.loads(Holder(Flags=Options.A | Options.B).model_dump_json())["Flags"] == "Both"
    assert Holder.model_validate({"Flags": "A, B"}).Flags == Options.Both
    assert Holder.model_validate({"Flags": "B"}).Flags is Options.B

def test_the_json_schema_of_an_enum_is_a_name_or_the_object_form():
    """Checks the `anyOf` of BHoM_JSONSchema: the allowed names, or the System.Enum object that holds the same name."""
    holder = Holder.model_json_schema()["properties"]
    names, form = holder["Level"]["anyOf"]
    assert names["enum"] == ["None", "Fast"]
    assert form["properties"]["_t"]["const"] == "System.Enum" and form["properties"]["Value"]["enum"] == ["None", "Fast"]
    assert "enum" not in holder["Flags"]["anyOf"][0], "combined flags are free text"
