"""The enum columns of a table and the CHECK constraints that follow from them, for the enums of the FixtureAlpha_oM assembly and a class with lists of enums."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from bhom_schema._support import SchemaModel
from bhom_schema.FixtureAlpha_oM.Beam import Beam
from bhom_schema.FixtureAlpha_oM.LineLike import LineLike
from bhom_schema.FixtureAlpha_oM.Options import Options
from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
from bhom_schema.FixtureAlpha_oM.SparseHolder import SparseHolder
from bhom_schema.FixtureAlpha_oM.SupportKind import SupportKind
from bhom_schema.tables import BASE_SKIPPED, Ref, Skip, Struct, UnmappedType, enum_columns, enum_constraints_sql, to_row

BEAM_FIELDS = {**BASE_SKIPPED, "Start": Struct()}

class Bearing(SchemaModel):
    """A stand-in class with a plain enum, a list of enums and a list of flags."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Bearing", "kind": "class"}
    Kind: SupportKind = SupportKind.Fixed
    Kinds: list[SupportKind] = []
    Combos: list[Options] = []

class Joint(SchemaModel):
    """A stand-in class that holds a Bearing, to reach an enum inside a Struct."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Joint", "kind": "class"}
    Support: Bearing = Bearing()

def test_the_enum_columns_of_a_class_are_listed_with_their_enum():
    """Checks the plain enum and the flags enum of Beam, with the Struct field left alone, and that a class without enums lists none.

    Protects the list that the constraints are built from.
    """
    columns = enum_columns(Beam, BEAM_FIELDS)

    assert {path: (column.enum, column.many) for path, column in columns.items()} == {"Support": (SupportKind, False), "Flags": (Options, False)}
    assert enum_columns(PointLike) == {}

def test_the_enum_columns_follow_a_struct_and_see_lists():
    """Checks the dotted path of an enum inside a Struct and the `many` of a list of enums.

    Protects the constraints of a table that stores an object inside the row.
    """
    columns = enum_columns(Joint, {"Support": Struct()})

    assert list(columns) == ["Support.Kind", "Support.Kinds", "Support.Combos"]
    assert [column.many for column in columns.values()] == [False, True, True]

def test_a_plain_enum_gets_an_in_list_of_the_names_bhom_writes():
    """Checks the constraint of Beam.Support: the names as BHoM writes them, so `None_` is `None`.

    Protects the text that users run, and that a row of the stored names passes.
    """
    sql = enum_constraints_sql(Beam, "main.default.Beam", BEAM_FIELDS)

    assert sql[0] == "ALTER TABLE `main`.`default`.`Beam` ADD CONSTRAINT `Beam_Support_enum` CHECK (`Support` IS NULL OR `Support` IN ('None', 'Fixed', 'Pinned'))"

def test_a_flags_enum_is_checked_name_by_name():
    """Checks that the constraint of Beam.Flags splits the text at commas, so `A, B` passes and an unknown name does not.

    Protects the combined values that to_row writes.
    """
    sql = enum_constraints_sql(Beam, "main.default.Beam", BEAM_FIELDS)

    assert sql[1] == (
        "ALTER TABLE `main`.`default`.`Beam` ADD CONSTRAINT `Beam_Flags_enum` "
        "CHECK (`Flags` IS NULL OR size(array_except(transform(split(`Flags`, ','), part -> trim(part)), array('A', 'B', 'Both'))) = 0)")

def test_lists_and_structs_have_their_own_constraints():
    """Checks `forall` for lists of enums and of flags, and a dotted path with its own constraint name for an enum inside a Struct."""
    sql = enum_constraints_sql(Joint, "t.s.Joint", {"Support": Struct()})

    assert "`Joint_Support_Kind_enum` CHECK (`Support`.`Kind` IS NULL OR `Support`.`Kind` IN ('None', 'Fixed', 'Pinned'))" in sql[0]
    assert "CHECK (`Support`.`Kinds` IS NULL OR forall(`Support`.`Kinds`, item -> item IS NULL OR item IN ('None', 'Fixed', 'Pinned')))" in sql[1]
    assert "`Support`.`Combos` IS NULL OR forall(`Support`.`Combos`, item -> item IS NULL OR size(array_except(transform(split(item, ','), part -> trim(part)), array('A', 'B', 'Both'))) = 0)" in sql[2]

def test_a_class_without_enums_has_no_constraints_and_an_undecided_field_is_refused():
    """Checks the empty list, the Skip of an enum field, and that an undecided custom field raises before anything is returned."""
    assert enum_constraints_sql(PointLike, "t.s.p") == []
    assert list(enum_columns(Beam, {**BEAM_FIELDS, "Support": Skip()})) == ["Flags"]

    with pytest.raises(UnmappedType, match="custom type"):
        enum_constraints_sql(LineLike, "t.s.LineLike")

    assert enum_constraints_sql(LineLike, "t.s.LineLike", {"Start": Ref("t.s.p"), "End": Ref("t.s.p")}) == []

def test_sparse_has_no_zero_member_and_is_still_checked():
    """Checks an enum whose members start at 1: the constraint lists exactly its two names."""
    sql = enum_constraints_sql(SparseHolder, "t.s.SparseHolder", BASE_SKIPPED)

    assert "`Level` IS NULL OR `Level` IN ('One', 'Two')" in sql[0]

def test_a_wrong_value_that_got_into_an_object_is_refused_when_the_row_is_made():
    """Checks that to_row raises for a string in an enum field, which model_construct (and a skipped validation) allows, and names the field and the members.

    Protects the table from a value that bypassed the checks of the class.
    """
    beam = Beam.model_construct(Support="Bogus", Start=PointLike())  # pyright: ignore[reportArgumentType]

    with pytest.raises(ValueError, match=r"Support is 'Bogus', which is not a member of SupportKind \(None, Fixed, Pinned\)"):
        to_row(beam, fields=BEAM_FIELDS)

    assert to_row(Beam(Start=PointLike(), Support=SupportKind.None_), fields=BEAM_FIELDS)["Support"] == "None"
