"""Behaviour of the Python generated from the real oM assemblies for the spike set."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from support import module_names, run_pyright


def cls(path: str) -> Any:
    module = importlib.import_module(f"bhom_schema.{path}")
    return getattr(module, path.rsplit(".", 1)[-1])


def test_every_module_imports_and_every_model_rebuilds(spike_package):
    names = module_names(spike_package)
    assert len(names) > 30
    for name in names:
        generated = getattr(importlib.import_module(name), name.rsplit(".", 1)[-1])
        if isinstance(generated, type) and issubclass(generated, BaseModel):
            assert generated.model_rebuild(force=True) in (True, None), name


def test_pyright_strict_is_clean(spike_package):
    result = run_pyright(spike_package.parent)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------- ProjectIdentification

def test_project_identification_defaults_and_bases():
    ProjectIdentification = cls("dKoP_oM.ProjectIdentification")
    IdKoPObject = cls("dKoP_oM.IdKoPObject")
    BHoMObject = cls("BHoM.BHoMObject")
    value = ProjectIdentification()
    assert (value.ProjectReference, value.ProjectName, value.ProjectLocation, value.AdditionalReferences) == ("", "", "", "")
    assert isinstance(value, IdKoPObject) and not isinstance(value, BHoMObject)
    assert ProjectIdentification(ProjectName="Tower").ProjectName == "Tower"


def test_project_identification_provenance():
    assert cls("dKoP_oM.ProjectIdentification").__bhom__ == {
        "clr_name": "BH.oM.dKoP.ProjectIdentification",
        "namespace": "BH.oM.dKoP",
        "assembly": "dKoP_oM",
        "repo": "BHoM/dKoP_Toolkit",
        "kind": "class",
    }


def test_interface_field_rejects_unrelated_objects():
    IdKoPObject = cls("dKoP_oM.IdKoPObject")

    class Holder(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        Item: IdKoPObject  # type: ignore[valid-type]

    Holder(Item=cls("dKoP_oM.ProjectIdentification")())
    with pytest.raises(ValidationError):
        Holder(Item=cls("Geometry_oM.Point")())


# ---------------------------------------------------------------- the other spike types

def test_line_and_curve_interfaces():
    Line, Point = cls("Geometry_oM.Line"), cls("Geometry_oM.Point")
    ICurve, IGeometry, IElement1D = cls("Geometry_oM.ICurve"), cls("Geometry_oM.IGeometry"), cls("Dimensional_oM.IElement1D")
    line = Line()
    assert isinstance(line.Start, Point) and line.Start is not line.End
    assert issubclass(ICurve, IGeometry) and issubclass(ICurve, IElement1D) and isinstance(line, ICurve)
    assert Line.__bhom__["assembly"] == "Geometry_oM"


def test_bhom_object_defaults():
    BHoMObject = cls("BHoM.BHoMObject")
    a, b = BHoMObject(), BHoMObject()
    assert a.BHoM_Guid != b.BHoM_Guid
    a.Tags.add("x")
    a.CustomData["k"] = 1
    assert b.Tags == set() and b.CustomData == {}


def test_bar_is_a_bhom_object_with_a_quantity():
    Bar, BHoMObject = cls("Structure_oM.Elements.Bar"), cls("BHoM.BHoMObject")
    assert issubclass(Bar, BHoMObject)
    angle = next(m for m in Bar.model_fields["OrientationAngle"].metadata if type(m).__name__ == "Quantity")
    assert angle.category == "Angle"


def test_enum_with_none_member():
    options = cls("Graphics_oM.Enums.GradientCenteringOptions")
    assert [m.name for m in options] == ["None_", "Asymmetric", "Symmetric"]
    assert options.__bhom__["renamed_members"] == {"None_": "None"}


def test_generic_with_constraint():
    BHoMGroup_1, BHoMObject = cls("BHoM.BHoMGroup_1"), cls("BHoM.BHoMObject")
    assert BHoMGroup_1.__bhom__["clr_name"] == "BH.oM.Base.BHoMGroup`1"
    group = BHoMGroup_1[BHoMObject](Elements=[BHoMObject()])
    assert len(group.Elements) == 1
    with pytest.raises(ValidationError):
        BHoMGroup_1[BHoMObject](Elements=[1])


def test_same_named_rooms_are_different_classes():
    acoustic, architecture = cls("Acoustic_oM.Room"), cls("Architecture_oM.Elements.Room")
    assert acoustic is not architecture
    assert acoustic.__bhom__["namespace"] == "BH.oM.Acoustic"
    assert architecture.__bhom__["namespace"] == "BH.oM.Architecture.Elements"


def test_gradient_has_color_and_decimal_keyed_markers():
    Gradient = cls("Graphics_oM.Gradient")
    assert "Markers" in Gradient.model_fields
    assert Gradient().Markers == {}


def test_comparison_config_holds_object_collections_as_lists():
    ComparisonConfig = cls("BHoM.ComparisonConfig")
    NamedNumericTolerance = cls("BHoM.NamedNumericTolerance")
    config = ComparisonConfig()
    assert config.PropertyNumericTolerances == []
    config.PropertyNumericTolerances.append(NamedNumericTolerance())
    assert len(config.PropertyNumericTolerances) == 1
