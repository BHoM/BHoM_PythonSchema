"""The JSON of the Python generated from real BHoM types: it round trips, every class has a JSON Schema, and what is written is what BHoM_JSONSchema accepts.

The last group needs a clone of BHoM_JSONSchema (next to this repository, or at BHOM_JSONSCHEMA_ROOT). The clone is read only and is only
the test: the generator does not use that repository.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource
from referencing.jsonschema import DRAFT202012

from support import module_names

RAW = "https://raw.githubusercontent.com/BHoM/BHoM_JSONSchema/develop/"
ROOT = Path(os.environ.get("BHOM_JSONSCHEMA_ROOT", Path(__file__).resolve().parents[5] / "BHoM_JSONSchema"))

def cls(path: str) -> Any:
    """Returns the generated class at a path such as `Geometry_oM.Line`, by importing `bhom_schema.<path>` and taking the class named after the last segment."""
    module = importlib.import_module(f"bhom_schema.{path}")
    return getattr(module, path.rsplit(".", 1)[-1])

def retrieve(uri: str) -> Resource[Any]:
    """Finds a schema that another schema refers to, in the local clone instead of on GitHub: the raw URL of a file maps to the same path in the clone."""
    if not uri.startswith(RAW) or not (ROOT / uri[len(RAW):]).is_file():
        raise NoSuchResource(uri)

    return Resource.from_contents(json.loads((ROOT / uri[len(RAW):]).read_text(encoding="utf-8")), default_specification=DRAFT202012)

def validator(schema_path: str) -> Draft202012Validator:
    """Builds a validator for one published schema, such as `Geometry_oM/Line.json`, that resolves its references in the local clone."""
    schema: dict[str, Any] = json.loads((ROOT / schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=Registry(retrieve=retrieve))  # type: ignore[arg-type]

def errors(schema_path: str, instance: Any) -> list[str]:
    """Lists, as text, why an instance does not validate against a published schema; empty when it does."""
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message[:140]}" for e in validator(schema_path).iter_errors(instance))

def written(model: BaseModel) -> Any:
    """Saves a model to JSON text and reads it as plain data, the way another program would receive it."""
    return json.loads(model.model_dump_json())

needs_clone = pytest.mark.skipif(not ROOT.is_dir(), reason=f"no clone of BHoM_JSONSchema at {ROOT}; set BHOM_JSONSCHEMA_ROOT")

def bar() -> Any:
    """Builds a small Bar from generated classes: two nodes, so JSON has nested objects, an enum, a quantity and the BHoMObject fields."""
    Bar, Node, Point = cls("Structure_oM.Elements.Bar"), cls("Structure_oM.Elements.Node"), cls("Geometry_oM.Point")
    return Bar(Name="B1", Start=Node(Position=Point(X=0, Y=0, Z=0)), End=Node(Position=Point(X=3, Y=0, Z=0)), OrientationAngle=0.5,
               FEAType=cls("Structure_oM.Elements.BarFEAType").Axial, Tags={"a", "b"}, CustomData={"k": 1})

def test_every_generated_class_has_a_json_schema(spike_package: Path):
    """Checks that `model_json_schema()` works for every generated class; before the interface support it failed for every BHoMObject."""
    for name in module_names(spike_package):
        generated = getattr(importlib.import_module(name), name.rsplit(".", 1)[-1])
        if isinstance(generated, type) and issubclass(generated, BaseModel):
            assert generated.model_json_schema(), name

def test_a_real_class_round_trips_through_json():
    """Checks that a Bar, with nested nodes, an enum, a set and a dictionary, is the same object after saving to JSON and loading again."""
    original = bar()
    again = type(original).model_validate_json(original.model_dump_json())
    assert again == original
    data = written(original)
    assert data["_t"] == "BH.oM.Structure.Elements.Bar" and data["FEAType"] == "Axial" and data["Start"]["_t"] == "BH.oM.Structure.Elements.Node"

def test_a_curve_saved_as_an_interface_value_loads_as_its_class():
    """Checks the interface rule on real types: JSON saved from a Line names its class in `_t`, and the ICurve interface field of Edge loads a Line."""
    Line, Point = cls("Geometry_oM.Line"), cls("Geometry_oM.Point")
    line = Line(Start=Point(X=1), End=Point(X=2))
    assert "BH.oM.Geometry.Line" in cls("Geometry_oM.ICurve").__bhom__["implementers"]
    assert type(Line.model_validate_json(line.model_dump_json())) is Line

@needs_clone
def test_a_point_and_a_line_are_valid_against_the_published_schemas():
    """Checks that JSON saved from generated Python validates against the schemas BHoM_JSONSchema publishes for Point and Line."""
    Line, Point = cls("Geometry_oM.Line"), cls("Geometry_oM.Point")
    line = Line(Start=Point(X=1, Y=2, Z=3), End=Point(X=4, Y=5, Z=6))
    assert errors("Geometry_oM/Point.json", written(Point(X=1, Y=2, Z=3))) == []
    assert errors("Geometry_oM/Line.json", written(line)) == []

@needs_clone
def test_a_line_is_valid_as_an_icurve_because_it_carries_its_type_tag():
    """Checks the interface rule of the published ICurve schema: it requires `_t`, picks the class from it, and then validates the Line."""
    Line, Point = cls("Geometry_oM.Line"), cls("Geometry_oM.Point")
    data = written(Line(Start=Point(X=1), End=Point(X=2)))
    assert errors("Geometry_oM/ICurve.json", data) == []

    without_tag = {key: value for key, value in data.items() if key != "_t"}
    assert any("'_t' is a required property" in e for e in errors("Geometry_oM/ICurve.json", without_tag))

@needs_clone
def test_a_bar_is_valid_against_the_published_schema():
    """Checks a whole real class: the Bar saved from Python, with nodes, an enum written as its name, a set, a dictionary and the BHoMObject fields, is valid."""
    assert errors("Structure_oM/Elements/Bar.json", written(bar())) == []

@needs_clone
def test_an_enum_is_valid_as_its_name_and_as_the_object_form():
    """Checks that the name Python writes for an enum, and the object form BHoM writes for a top-level enum, are both accepted by the published enum schema."""
    Options = cls("Graphics_oM.Enums.GradientCenteringOptions")
    path = "Graphics_oM/Enums/GradientCenteringOptions.json"
    assert errors(path, Options.None_.bhom_name()) == [] and Options.None_.bhom_name() == "None"
    form = {"_t": "System.Enum", "TypeName": {"_t": "System.Type", "Name": "BH.oM.Graphics.Enums.GradientCenteringOptions"}, "Value": "Symmetric"}
    assert errors(path, form) == []

    holder = Options.from_bhom(form)
    assert holder is Options.Symmetric

@needs_clone
def test_the_published_schemas_reject_what_python_would_not_write():
    """Checks that the comparison above can fail: a Point with a field missing, or with the wrong type of value, is invalid in the published schema."""
    assert any("'Z' is a required property" in e for e in errors("Geometry_oM/Point.json", {"X": 1, "Y": 2}))
    assert errors("Geometry_oM/Point.json", {"X": "one", "Y": 2, "Z": 3}) != []
