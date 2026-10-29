"""Behaviour of the Python generated from the fixture assemblies (one test per gotcha in the research notes)."""

from __future__ import annotations

import importlib
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from support import module_names, run_pyright


def load(module: str) -> Any:
    """Imports a module by its dotted name and returns it.

    Helper of the fixture tests that look at generated modules.
    """
    return importlib.import_module(module)


def cls(path: str) -> Any:
    """Returns the generated class at a path such as `FixtureAlpha_oM.Beam`, by importing `bhom_schema.<path>` and taking the class named after the last segment.

    Helper used by most fixture tests to get a generated type.
    """
    module = load(f"bhom_schema.{path}")
    return getattr(module, path.rsplit(".", 1)[-1])


def test_every_module_imports_and_every_model_rebuilds(fixtures_package):
    """Checks that every module generated from the fixture assemblies imports and that every Pydantic model in them rebuilds without error.

    Protects the generator's emitted Python (imports, forward references, cycles) from being syntactically or structurally broken.
    """
    names = module_names(fixtures_package)
    assert len(names) > 20
    for name in names:
        module = load(name)
        generated = getattr(module, name.rsplit(".", 1)[-1])
        if isinstance(generated, type) and issubclass(generated, BaseModel):
            assert generated.model_rebuild(force=True) in (True, None), name


def test_pyright_strict_is_clean(fixtures_package):
    """Checks that pyright in strict mode reports no problems on the Python generated from the fixture assemblies.

    Protects the generator's type expressions and imports, so the committed schema stays type-clean.
    """
    result = run_pyright(fixtures_package.parent)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------- interfaces and MRO

def test_interface_chain_has_a_consistent_mro():
    """Checks that interface-only fixture types (curve, geometry, element) and a class implementing them form a valid inheritance chain.

    Protects the generator's base ordering, which Python needs for a consistent method resolution order.
    """
    ICurveLike = cls("FixtureAlpha_oM.ICurveLike")
    IGeometryLike = cls("FixtureAlpha_oM.IGeometryLike")
    IElement1DLike = cls("FixtureAlpha_oM.IElement1DLike")
    LineLike = cls("FixtureAlpha_oM.LineLike")
    assert issubclass(ICurveLike, IGeometryLike) and issubclass(ICurveLike, IElement1DLike)
    assert issubclass(LineLike, ICurveLike) and issubclass(LineLike, IGeometryLike)


def test_interface_typed_field_accepts_implementers_and_keeps_the_subclass():
    """Checks that a field typed as an interface accepts any generated implementer, singly or in a list, and keeps the actual subclass instead of coercing it.

    Protects how the generator maps C# interface types to Python annotations.
    """
    GeometryHolder = cls("FixtureAlpha_oM.GeometryHolder")
    LineLike = cls("FixtureAlpha_oM.LineLike")
    PointLike = cls("FixtureAlpha_oM.PointLike")
    holder = GeometryHolder(Geometry=PointLike(X=2.0))
    assert type(holder.Geometry) is PointLike
    holder = GeometryHolder(Geometry=LineLike(), Curves=[LineLike()])
    assert type(holder.Geometry) is LineLike
    assert type(holder.Curves[0]) is LineLike


def test_interface_typed_field_rejects_non_implementers():
    """Checks that an interface-typed field raises a validation error for a number, for an unrelated class and for a list item that does not implement the interface.

    Protects the generated annotations from being too loose, which would let invalid objects into the schema.
    """
    GeometryHolder = cls("FixtureAlpha_oM.GeometryHolder")
    ProjectLike = cls("FixtureAlpha_oM.ProjectLike")
    with pytest.raises(ValidationError):
        GeometryHolder(Geometry=3)
    with pytest.raises(ValidationError):
        GeometryHolder(Geometry=ProjectLike())
    with pytest.raises(ValidationError):
        GeometryHolder(Curves=[cls("FixtureAlpha_oM.PointLike")()])


# ---------------------------------------------------------------- the ProjectIdentification twin

def test_project_like_is_a_flat_interface_only_class():
    """Checks that a class implementing only interfaces has its defaults and field order as the C# declares, derives from its interface twin and not from `BHoMObject`.

    Protects how the generator handles types with no base class and no inherited properties.
    """
    ProjectLike = cls("FixtureAlpha_oM.ProjectLike")
    ThingIdentity = cls("FixtureAlpha_oM.ThingIdentity")
    BHoMObject = cls("BHoM.BHoMObject")
    project = ProjectLike()
    assert (project.ProjectReference, project.ProjectName, project.ProjectLocation, project.AdditionalReferences) == ("", "", "", "")
    assert isinstance(project, ThingIdentity)
    assert not isinstance(project, BHoMObject)
    assert list(ProjectLike.model_fields) == ["ProjectReference", "ProjectName", "ProjectLocation", "AdditionalReferences"]


def test_project_like_lives_at_the_namespace_path_not_the_source_folder():
    """Checks that a generated class sits in the module path of its assembly and carries the expected `__bhom__` provenance (CLR name, namespace, assembly, repo, kind).

    Protects the metadata that py2cs later uses to find the owning C# repository.
    """
    module = load("bhom_schema.FixtureAlpha_oM.ProjectLike")
    assert module.ProjectLike.__bhom__ == {
        "clr_name": "BH.oM.FixtureAlpha.ProjectLike",
        "namespace": "BH.oM.FixtureAlpha",
        "assembly": "FixtureAlpha_oM",
        "repo": "BHoM/CSharpSchema_Test",
        "kind": "class",
    }


# ---------------------------------------------------------------- defaults and required fields

def test_required_fields_after_defaulted_base_fields():
    """Checks that a class with required properties validates only when they are given, keeps the base class defaults and generates a fresh GUID.

    Protects the generator's defaults and required-field handling when a base has defaulted fields.
    """
    ImmutableThing = cls("FixtureAlpha_oM.ImmutableThing")
    with pytest.raises(ValidationError):
        ImmutableThing()
    thing = ImmutableThing(Id="a", Length=2.0)
    assert thing.Name == "" and thing.Tags == set()
    assert isinstance(thing.BHoM_Guid, UUID)


def test_mutable_defaults_are_not_shared():
    """Checks that list, set and matrix defaults are new objects per instance and that a literal list default keeps its values.

    Protects the generator's default formatting from sharing mutable state between instances.
    """
    Collections = cls("FixtureAlpha_oM.Collections")
    a, b = Collections(), Collections()
    a.Names.add("x")
    a.Matrix.append([1])
    assert b.Names == set() and b.Matrix == []
    assert a.Words == ["a", "b"]


def test_guid_and_datetime_defaults_are_fresh_per_instance():
    """Checks that GUID and creation-time defaults are produced per instance, and that fixed datetime, decimal, colour and quoted-string defaults come out as the C# declares.

    Protects the generator's literal and default-factory emission.
    """
    Scalars = cls("FixtureAlpha_oM.Scalars")
    BHoMObject = cls("BHoM.BHoMObject")
    assert BHoMObject().BHoM_Guid != BHoMObject().BHoM_Guid
    first, second = Scalars(), Scalars()
    assert isinstance(first.Created, datetime) and first.Created <= second.Created
    assert first.Fixed == datetime(2020, 1, 2, 3, 4, 5)
    assert first.Cost == Decimal("1.5")
    assert first.Colour.A == 0 and first.Quote == 'it\'s "here"'


def test_object_default_is_a_new_instance_each_time():
    """Checks that an object-typed default (a nested class) is a new instance for each parent and that a nullable object defaults to None.

    Protects the generator's default-instance reading and emission.
    """
    LineLike = cls("FixtureAlpha_oM.LineLike")
    a, b = LineLike(), LineLike()
    assert a.Start is not b.Start
    assert a.Label is None


# ---------------------------------------------------------------- enums

def test_enum_member_named_none_is_renamed_and_recorded():
    """Checks that an enum member named `None` is generated as `None_`, that the original name is recorded in `__bhom__`, and that a property defaulting to the enum resolves to the renamed member.

    Protects the naming rules that keep generated names valid Python while staying traceable to the C#.
    """
    SupportKind = cls("FixtureAlpha_oM.SupportKind")
    assert [m.name for m in SupportKind] == ["None_", "Fixed", "Pinned"]
    assert SupportKind.__bhom__["renamed_members"] == {"None_": "None"}
    Beam = cls("FixtureAlpha_oM.Beam")
    assert Beam().Support is SupportKind.Pinned


def test_flags_enum_supports_combinations():
    """Checks that a generated flags enum supports bitwise combination, with a combined member equal to the OR of its parts.

    Protects how the generator emits `[Flags]` enums.
    """
    Options = cls("FixtureAlpha_oM.Options")
    assert Options.A | Options.B == Options.Both


# ---------------------------------------------------------------- generics

def test_bounded_generic_accepts_the_bound_only():
    """Checks that a generic class with a constraint records its CLR name and bounds, accepts a parameterised list of the bound type and rejects invalid items.

    Protects the generator's mapping of C# generics and their constraints.
    """
    Wrapper_1 = cls("FixtureAlpha_oM.Wrapper_1")
    Beam = cls("FixtureAlpha_oM.Beam")
    assert Wrapper_1.__bhom__["clr_name"] == "BH.oM.FixtureAlpha.Wrapper`1"
    assert Wrapper_1.__bhom__["generic_params"] == {"T": ["BH.oM.Base.IBHoMObject"]}
    group = Wrapper_1[Beam](Items=[Beam()])
    assert len(group.Items) == 1
    with pytest.raises(ValidationError):
        Wrapper_1[Beam](Items=[3])


# ---------------------------------------------------------------- same names, cycles, collections

def test_same_named_classes_import_together():
    """Checks that classes with the same name in two fixture assemblies are distinct and can be used together in one class without confusion.

    Protects the generator's name tracking and import aliasing across assemblies.
    """
    UsesBoth = cls("FixtureBeta_oM.Elements.UsesBoth")
    AlphaPoint = cls("FixtureAlpha_oM.PointLike")
    BetaPoint = cls("FixtureBeta_oM.PointLike")
    assert AlphaPoint is not BetaPoint
    value = UsesBoth(FromAlpha=AlphaPoint(X=1.0), Local=BetaPoint(X=2.0))
    assert type(value.FromAlpha) is AlphaPoint and type(value.Local) is BetaPoint
    with pytest.raises(ValidationError):
        UsesBoth(FromAlpha=BetaPoint())


def test_cyclic_references_import_and_validate():
    """Checks that two classes that reference each other import and validate, and that a nested instance of each can be built.

    Protects the cycle detection that decides which imports are placed after the class.
    """
    CycleA = cls("FixtureAlpha_oM.CycleA")
    CycleB = cls("FixtureAlpha_oM.CycleB")
    a = CycleA(Other=CycleB(Other=CycleA()))
    assert isinstance(cast(Any, a.Other), CycleB)


def test_unhashable_items_fall_back_to_lists():
    """Checks that collections of unhashable items are generated as lists (not sets) and that tuple lists and dictionaries still validate.

    Protects the type mapper's choice of collection type for item types that cannot go in a set.
    """
    Collections = cls("FixtureAlpha_oM.Collections")
    PointLike = cls("FixtureAlpha_oM.PointLike")
    value = Collections(Points=[PointLike(X=1.0), PointLike(X=1.0)], ByPoint=[(PointLike(), "a")], Names={"a", "b"}, Lookup={"k": 1.0})
    assert len(value.Points) == 2 and value.ByPoint[0][1] == "a"


def test_metadata_markers_are_in_the_annotation():
    """Checks that a property's annotation carries its quantity (category and unit), display text, description and CLR type markers as the C# declares.

    Protects the metadata that the generator extracts and py2cs reads back.
    """
    Beam = cls("FixtureAlpha_oM.Beam")
    metadata = Beam.model_fields["Span"].metadata
    kinds = {type(m).__name__ for m in metadata}
    assert {"Quantity", "DisplayText"} <= kinds
    quantity = next(m for m in metadata if type(m).__name__ == "Quantity")
    assert (quantity.category, quantity.unit) == ("Length", "m")
    assert Beam.model_fields["Span"].description == "Distance between the supports."
    count_metadata = Beam.model_fields["Count"].metadata
    assert [m.name for m in count_metadata if type(m).__name__ == "ClrType"] == ["long"]
