"""Behaviour of the Python generated from the real oM assemblies for the spike set."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from support import module_names, run_pyright


def cls(path: str) -> Any:
    """Returns the generated class at a path such as `Geometry_oM.Line`, by importing `bhom_schema.<path>` and taking the class named after the last segment.

    Helper used by the spike tests to get a generated type.
    """
    module = importlib.import_module(f"bhom_schema.{path}")
    return getattr(module, path.rsplit(".", 1)[-1])


def test_every_module_imports_and_every_model_rebuilds(spike_package):
    """Checks that every module generated from the real oM assemblies imports and that every Pydantic model in them rebuilds without error.

    Protects the generator's output on real BHoM types, not only on the small fixtures.
    """
    names = module_names(spike_package)
    assert len(names) > 30
    for name in names:
        generated = getattr(importlib.import_module(name), name.rsplit(".", 1)[-1])
        if isinstance(generated, type) and issubclass(generated, BaseModel):
            assert generated.model_rebuild(force=True) in (True, None), name


def test_pyright_strict_is_clean(spike_package):
    """Checks that pyright in strict mode reports no problems on the Python generated from the real oM spike types.

    Protects the committed schema from type errors the fixtures alone would not reveal.
    """
    result = run_pyright(spike_package.parent)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------- the other spike types

def test_line_and_curve_interfaces():
    """Checks that the generated `Line` has distinct start and end points, implements the curve, geometry and element interfaces, and records its assembly.

    Protects the generator's handling of a real interface hierarchy and object defaults.
    """
    Line, Point = cls("Geometry_oM.Line"), cls("Geometry_oM.Point")
    ICurve, IGeometry, IElement1D = cls("Geometry_oM.ICurve"), cls("Geometry_oM.IGeometry"), cls("Dimensional_oM.IElement1D")
    line = Line()
    assert isinstance(line.Start, Point) and line.Start is not line.End
    assert issubclass(ICurve, IGeometry) and issubclass(ICurve, IElement1D) and isinstance(line, ICurve)
    assert Line.__bhom__["assembly"] == "Geometry_oM"


def test_bhom_object_defaults():
    """Checks that two `BHoMObject` instances get different GUIDs and do not share their tags or custom data.

    Protects the generator's defaults on the base class of all oM types.
    """
    BHoMObject = cls("BHoM.BHoMObject")
    a, b = BHoMObject(), BHoMObject()
    assert a.BHoM_Guid != b.BHoM_Guid
    a.Tags.add("x")
    a.CustomData["k"] = 1
    assert b.Tags == set() and b.CustomData == {}


def test_bar_is_a_bhom_object_with_a_quantity():
    """Checks that the generated structural `Bar` derives from `BHoMObject` and that its orientation angle carries the 'Angle' quantity.

    Protects base-class and quantity extraction on a real type.
    """
    Bar, BHoMObject = cls("Structure_oM.Elements.Bar"), cls("BHoM.BHoMObject")
    assert issubclass(Bar, BHoMObject)
    angle = next(m for m in Bar.model_fields["OrientationAngle"].metadata if type(m).__name__ == "Quantity")
    assert angle.category == "Angle"


def test_enum_with_none_member():
    """Checks that a real enum with a `None` member is generated with `None_` and records the rename in `__bhom__`.

    Protects the enum naming rule on a real assembly.
    """
    options = cls("Graphics_oM.Enums.GradientCenteringOptions")
    assert [m.name for m in options] == ["None_", "Asymmetric", "Symmetric"]
    assert options.__bhom__["renamed_members"] == {"None_": "None"}


def test_generic_with_constraint():
    """Checks that the generated `BHoMGroup<T>` records its CLR name, accepts a list of the bound type and rejects invalid items.

    Protects the generic and constraint mapping on a real type.
    """
    BHoMGroup_1, BHoMObject = cls("BHoM.BHoMGroup_1"), cls("BHoM.BHoMObject")
    assert BHoMGroup_1.__bhom__["clr_name"] == "BH.oM.Base.BHoMGroup`1"
    group = BHoMGroup_1[BHoMObject](Elements=[BHoMObject()])
    assert len(group.Elements) == 1
    with pytest.raises(ValidationError):
        BHoMGroup_1[BHoMObject](Elements=[1])


def test_same_named_rooms_are_different_classes():
    """Checks that the two `Room` classes in the acoustic and architecture assemblies are separate classes with their own namespaces.

    Protects name tracking when real assemblies reuse a type name.
    """
    acoustic, architecture = cls("Acoustic_oM.Room"), cls("Architecture_oM.Elements.Room")
    assert acoustic is not architecture
    assert acoustic.__bhom__["namespace"] == "BH.oM.Acoustic"
    assert architecture.__bhom__["namespace"] == "BH.oM.Architecture.Elements"


def test_gradient_has_color_and_decimal_keyed_markers():
    """Checks that the generated `Gradient` has a `Markers` field that defaults to an empty dictionary.

    Protects the mapping of a dictionary keyed by decimal numbers with colour values.
    """
    Gradient = cls("Graphics_oM.Gradient")
    assert "Markers" in Gradient.model_fields
    assert Gradient().Markers == {}


def test_comparison_config_holds_object_collections_as_lists():
    """Checks that `ComparisonConfig` holds its tolerance objects in a list that starts empty and accepts new items.

    Protects the type mapper's list fallback for collections of objects on a real type.
    """
    ComparisonConfig = cls("BHoM.ComparisonConfig")
    NamedNumericTolerance = cls("BHoM.NamedNumericTolerance")
    config = ComparisonConfig()
    assert config.PropertyNumericTolerances == []
    config.PropertyNumericTolerances.append(NamedNumericTolerance())
    assert len(config.PropertyNumericTolerances) == 1
