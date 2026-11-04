"""The column mapping of bhom_schema.tables: the column type of each Python type, the fields that need a decision, and the decisions themselves.

They run against the classes of the FixtureAlpha_oM assembly that the package carries, so every Python type of the mapping is met in a real generated class.
"""

from __future__ import annotations

import collections.abc
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

import pytest

from bhom_schema._support import ClrType, Polymorphic
from bhom_schema.BHoM.IFragment import IFragment
from bhom_schema.FixtureAlpha_oM.Beam import Beam
from bhom_schema.FixtureAlpha_oM.Collections import Collections
from bhom_schema.FixtureAlpha_oM.CycleA import CycleA
from bhom_schema.FixtureAlpha_oM.GeometryHolder import GeometryHolder
from bhom_schema.FixtureAlpha_oM.LineLike import LineLike
from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
from bhom_schema.FixtureAlpha_oM.Scalars import Scalars
from bhom_schema.FixtureAlpha_oM.SupportKind import SupportKind
from bhom_schema.FixtureAlpha_oM.Wrapper_1 import Wrapper_1
from bhom_schema.tables import BASE_SKIPPED, Json, Ref, Skip, Struct, UnmappedType, column_type, custom_fields, describe, require_decided

def columns_of(model: type, **options: Any) -> dict[str, tuple[str | None, str]]:
    """Describes a class and returns {column name: (type, decision)}, which is all most checks need."""
    return {column.name: (column.type, column.decision) for column in describe(model, **options)}

@pytest.mark.parametrize("annotation, markers, expected", [
    (bool, [], "BOOLEAN"),
    (int, [], "INT"),
    (int, [ClrType("long")], "BIGINT"),
    (int, [ClrType("short")], "SMALLINT"),
    (int, [ClrType("sbyte")], "TINYINT"),
    (int, [ClrType("byte")], "SMALLINT"),
    (int, [ClrType("ushort")], "INT"),
    (int, [ClrType("uint")], "BIGINT"),
    (int, [ClrType("ulong")], "DECIMAL(20,0)"),
    (float, [], "DOUBLE"),
    (float, [ClrType("float")], "FLOAT"),
    (str, [], "STRING"),
    (str, [ClrType("char")], "STRING"),
    (Decimal, [], "DECIMAL(38,10)"),
    (datetime, [], "TIMESTAMP_NTZ"),
    (date, [], "DATE"),
    (timedelta, [], "DOUBLE"),
    (UUID, [], "STRING"),
    (SupportKind, [], "STRING"),
    (int | None, [], "INT"),
    (Annotated[int, ClrType("long")] | None, [], "BIGINT"),
    (list[str], [], "ARRAY<STRING>"),
    (set[int], [], "ARRAY<INT>"),
    (list[int | None], [], "ARRAY<INT>"),
    (list[list[float]], [], "ARRAY<ARRAY<DOUBLE>>"),
    (list[int], [ClrType("long[]")], "ARRAY<BIGINT>"),
    (list[int], [ClrType("System.Collections.Generic.List<long>")], "ARRAY<BIGINT>"),
    (list[list[int]], [ClrType("long[][]")], "ARRAY<ARRAY<BIGINT>>"),
    (dict[str, float], [], "MAP<STRING, DOUBLE>"),
    (dict[str, int], [ClrType("System.Collections.Generic.Dictionary<string, long>")], "MAP<STRING, BIGINT>"),
    (dict[str, list[str]], [], "MAP<STRING, ARRAY<STRING>>"),
])
def test_primitive_annotations_have_a_column_type(annotation: Any, markers: list[object], expected: str):
    """Checks the column type of every primitive Python annotation of the type mapping, with the ClrType markers that tell `long` from `int`, and `Optional` and collection forms.

    Protects the type mapping table, which every table that is created depends on.
    """
    assert column_type(annotation, markers) == expected

@pytest.mark.parametrize("annotation", [
    Any, Any | None, tuple[int, str], int | str, dict[int, str], dict[str, Any], list[tuple[int, str]],
    PointLike, list[PointLike], Polymorphic[IFragment], list[Polymorphic[IFragment]], collections.abc.Callable[..., Any], object,
])
def test_other_annotations_have_no_column_type(annotation: Any):
    """Checks that a class, an interface, `Any`, a tuple, a choice of types, a function and a collection of any of them raise UnmappedType.

    Protects the rule that only a primitive is mapped on its own and everything else is the user's decision.
    """
    with pytest.raises(UnmappedType, match="has no column type"):
        column_type(annotation)

def test_scalars_class_maps_every_scalar_type():
    """Checks the columns of the Scalars fixture: datetime, UUID, Decimal, timedelta, char, plain strings and the largest float, and the fields with no column.

    Protects the scalar rows of the type mapping against real generated annotations, which carry markers that the tests of single types do not.
    """
    columns = columns_of(Scalars, fields={"Colour": Skip(), "TypeRef": Json(), "Callback": Skip(), **BASE_SKIPPED})

    assert columns["BHoM_Guid"] == ("STRING", "key")
    assert columns["Created"] == ("TIMESTAMP_NTZ", "primitive")
    assert columns["Fixed"] == ("TIMESTAMP_NTZ", "primitive")
    assert columns["Key"] == ("STRING", "primitive")
    assert columns["Cost"] == ("DECIMAL(38,10)", "primitive")
    assert columns["Duration"] == ("DOUBLE", "primitive")
    assert columns["Letter"] == ("STRING", "primitive")
    assert columns["Quote"] == ("STRING", "primitive")
    assert columns["Big"] == ("DOUBLE", "primitive")
    assert columns["TypeRef"] == ("STRING", "json")
    assert columns["Colour"] == (None, "skip")
    assert columns["Callback"] == (None, "skip")

def test_collections_class_maps_collections_and_names_the_rest():
    """Checks the columns of the Collections fixture: sets, lists, dicts and matrices map, and a list of classes, a tuple and `Any` wait for a decision.

    Protects the collection rows of the type mapping, and the list of classes that a Struct or a Json then stores.
    """
    columns = columns_of(Collections, fields=BASE_SKIPPED)

    assert columns["Names"] == ("ARRAY<STRING>", "primitive")
    assert columns["Lookup"] == ("MAP<STRING, DOUBLE>", "primitive")
    assert columns["Values"] == ("ARRAY<DOUBLE>", "primitive")
    assert columns["Matrix"] == ("ARRAY<ARRAY<INT>>", "primitive")
    assert columns["Words"] == ("ARRAY<STRING>", "primitive")
    assert columns["OptionalCount"] == ("INT", "primitive")
    assert columns["Points"] == (None, "undecided")
    assert columns["ByPoint"] == (None, "undecided")
    assert columns["Pair"] == (None, "undecided")
    assert columns["Anything"] == (None, "undecided")

def test_beam_class_maps_enums_markers_and_comments():
    """Checks the columns of the Beam fixture: enums and flags are STRING with the allowed names in the comment, long and float come from the markers, and the quantity is in the comment.

    Protects the enum rows, the ClrType reading and the column comments, which document the table in the catalog.
    """
    columns = {column.name: column for column in describe(Beam, fields={"Start": Skip(), **BASE_SKIPPED})}

    assert columns["Span"].type == "DOUBLE"
    assert columns["Span"].comment == "Span length. Distance between the supports. [Length, m]"
    assert columns["Support"].type == "STRING"
    assert columns["Support"].comment == "One of: None, Fixed, Pinned."
    assert columns["Flags"].type == "STRING"
    assert columns["Flags"].comment == "Any of: A, B, Both, joined by ', '."
    assert columns["Count"].type == "BIGINT"
    assert columns["Small"].type == "FLOAT"

def test_comments_say_what_the_stored_value_means():
    """Checks that a timedelta column says it holds seconds, a char column says it holds one character, and a field with no description has no comment.

    Protects the notes that stand in for the Python type, which the table cannot say.
    """
    columns = {column.name: column for column in describe(Scalars, fields={"Colour": Skip(), "TypeRef": Skip(), "Callback": Skip(), **BASE_SKIPPED})}

    assert columns["Duration"].comment == "Seconds."
    assert columns["Letter"].comment == "One character."
    assert columns["Quote"].comment is None

def test_the_version_of_bhom_is_a_column_named_by_its_json_alias():
    """Checks that `bhom_version` is the column `_bhomVersion` and keeps its description as the comment.

    Protects the rule that columns follow the BHoM JSON names, not the Python field names.
    """
    column = next(column for column in describe(PointLike) if column.field == "bhom_version")

    assert column.name == "_bhomVersion"
    assert column.type == "STRING"
    assert column.comment is not None and column.comment.startswith("Optional version of BHoM")

def test_a_class_without_a_guid_gets_an_added_key_and_a_bhomobject_uses_its_guid():
    """Checks that `_id STRING NOT NULL` is added in front of PointLike, and that Beam keys on its BHoM_Guid, which is moved to the front and made NOT NULL.

    Protects the key column that other tables point at.
    """
    added = describe(PointLike)[0]
    own = describe(Beam, fields={"Start": Skip(), **BASE_SKIPPED})[0]

    assert (added.name, added.type, added.nullable, added.field, added.decision) == ("_id", "STRING", False, None, "key")
    assert (own.name, own.type, own.nullable, own.field, own.decision) == ("BHoM_Guid", "STRING", False, "BHoM_Guid", "key")
    assert [column.name for column in describe(PointLike, key=None)] == ["_bhomVersion", "X", "Y", "Z"]

def test_any_field_can_be_the_key_and_an_unknown_one_is_refused():
    """Checks that `key=` can name another field of the class, and that a name the class does not have, or a field with no column type, raises.

    Protects the key choice against typos.
    """
    assert describe(LineLike, fields={"Start": Skip(), "End": Skip()}, key="Label")[0].name == "Label"

    with pytest.raises(ValueError, match="no field 'Nope'"):
        describe(PointLike, key="Nope")

    with pytest.raises(ValueError, match="cannot be the key"):
        describe(LineLike, key="Start")

def test_custom_fields_names_the_fields_without_a_column_and_their_types():
    """Checks custom_fields for LineLike (two PointLike fields), for the Collections fixture (a list of classes) and for Scalars (a class, `Any` and a function).

    Protects the way a user finds out which tables to make next.
    """
    assert custom_fields(LineLike) == {"Start": PointLike, "End": PointLike}
    assert custom_fields(PointLike) == {}
    assert custom_fields(Collections)["Points"] == list[PointLike]
    assert set(custom_fields(Scalars)) == {"Fragments", "CustomData", "Colour", "TypeRef", "Callback"}

def test_undecided_fields_are_listed_by_describe_and_refused_by_require_decided():
    """Checks that describe lists an undecided field with no type, and that require_decided raises the error that names the fields and the four choices.

    Protects the rule that no field is ever left out of a table without the user saying so.
    """
    undecided = [column for column in describe(LineLike) if column.decision == "undecided"]

    assert [(column.name, column.type, column.undecided) for column in undecided] == [
        ("Start", None, (("Start", "PointLike"),)), ("End", None, (("End", "PointLike"),))]

    with pytest.raises(UnmappedType) as error:
        require_decided(LineLike)

    assert str(error.value) == (
        "LineLike has 2 fields of a custom type, so they have no column until you decide how to store them:\n"
        "  Start: PointLike\n"
        "  End: PointLike\n"
        'Pass fields={"Start": ...} with one of:\n'
        '  Ref("catalog.schema.Table")  an id column that points at a row of that table\n'
        "  Struct()                     a STRUCT column holding the object's own fields\n"
        "  Json()                       the object as JSON text in a STRING column\n"
        "  Skip()                       no column; the field keeps its default when a row is read")
    assert error.value.fields == {"Start": "PointLike", "End": "PointLike"}

def test_the_error_for_one_field_is_singular_and_a_decided_class_does_not_raise():
    """Checks the wording for a single undecided field, and that require_decided returns the columns when every field is decided.

    Protects the message from reading like a plural for one field, and the path that the SQL helpers take when nothing is left to decide.
    """
    with pytest.raises(UnmappedType, match="LineLike has a field of a custom type, so it has no column until"):
        require_decided(LineLike, {"Start": Ref("main.default.PointLike")})

    columns = require_decided(LineLike, {"Start": Skip(), "End": Skip()})

    assert [column.name for column in columns] == ["_id", "_bhomVersion", "Start", "End", "Infinite", "Label"]

def test_ref_is_an_id_column_named_after_the_field_unless_told_otherwise():
    """Checks that a Ref gives a STRING column `<Field>_id`, or the column that is asked for, and keeps the field it comes from.

    Protects the column naming of the links between tables.
    """
    columns = {column.field: column for column in describe(LineLike, {"Start": Ref("main.default.PointLike"), "End": Ref("main.default.PointLike", column="EndPoint")})}

    assert (columns["Start"].name, columns["Start"].type, columns["Start"].decision) == ("Start_id", "STRING", "ref")
    assert (columns["End"].name, columns["End"].type, columns["End"].decision) == ("EndPoint", "STRING", "ref")

def test_struct_stores_a_class_as_its_own_fields_and_a_list_of_classes_as_an_array():
    """Checks the STRUCT type of a class field (the nested `_bhomVersion` is left out, names are quoted) and the ARRAY of STRUCT of a list of classes.

    Protects the Struct decision, the one that stores objects inside the row.
    """
    line = columns_of(LineLike, fields={"Start": Struct(), "End": Struct()})
    collection = columns_of(Collections, fields={**BASE_SKIPPED, "Points": Struct(), "ByPoint": Skip(), "Pair": Skip(), "Anything": Skip()})
    point = "STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE>"

    assert line["Start"] == (point, "struct")
    assert line["End"] == (point, "struct")
    assert collection["Points"] == (f"ARRAY<{point}>", "struct")

def test_struct_names_the_path_of_a_nested_undecided_field():
    """Checks that a Struct whose class holds a class that is not decided leaves the column undecided and names the path, and that a nested decision settles it.

    Protects the nested rule of the Struct decision and the example the error gives for it.
    """
    column = next(column for column in describe(GeometryHolder, {**BASE_SKIPPED, "Geometry": Skip(), "Curves": Skip()}) if column.field == "Geometry")

    assert column.decision == "skip"

    holder = describe(CycleA, {"Other": Struct()})[-1]

    assert (holder.decision, holder.undecided) == ("undecided", (("Other.Other", "CycleA"),))

    with pytest.raises(UnmappedType) as error:
        require_decided(CycleA, {"Other": Struct()})

    assert 'Pass fields={"Other": Struct(fields={"Other": ...})} with one of:' in str(error.value)
    assert error.value.fields == {"Other.Other": "CycleA"}

def test_a_struct_that_would_contain_itself_is_refused():
    """Checks that CycleA holding CycleB holding CycleA raises, naming the cycle, once the user asks for a Struct at every level.

    Protects against a struct type that never ends.
    """
    with pytest.raises(ValueError, match=r"CycleA -> CycleB -> CycleA"):
        describe(CycleA, {"Other": Struct(fields={"Other": Struct()})})

def test_json_and_skip_decide_any_field_that_has_no_column():
    """Checks that Json gives a STRING column for a tuple, `Any`, a class and a list of interfaces, that Skip gives no column, and that BASE_SKIPPED skips Fragments and CustomData.

    Protects the two escape hatches and the constant that most BHoMObject tables use.
    """
    columns = columns_of(Collections, fields={**BASE_SKIPPED, "Points": Json(), "ByPoint": Json(), "Pair": Json(), "Anything": Skip()})

    assert columns["Points"] == ("STRING", "json")
    assert columns["ByPoint"] == ("STRING", "json")
    assert columns["Pair"] == ("STRING", "json")
    assert columns["Anything"] == (None, "skip")
    assert columns["Fragments"] == (None, "skip")
    assert columns["CustomData"] == (None, "skip")

def test_decisions_that_make_no_sense_are_refused():
    """Checks the refusals: Json on a function, Struct on an interface, Ref on a list, a decision other than Skip on a field with a column, and a field the class does not have.

    Protects the user from a table that could not be read back, and from a typo that would otherwise be ignored.
    """
    with pytest.raises(ValueError, match="function, which has no JSON"):
        describe(Scalars, {"Callback": Json()})

    with pytest.raises(ValueError, match="Struct needs the fields of a class"):
        describe(GeometryHolder, {"Geometry": Struct()})

    with pytest.raises(ValueError, match="a Ref points at one object"):
        describe(Collections, {"Points": Ref("main.default.PointLike")})

    with pytest.raises(ValueError, match="has a column of its own"):
        describe(PointLike, {"X": Json()})

    with pytest.raises(ValueError, match="PointLike has no field 'Nope'"):
        describe(PointLike, {"Nope": Skip()})

    with pytest.raises(ValueError, match=r"Start \(PointLike\) has no field 'Nope'"):
        describe(LineLike, {"Start": Struct(fields={"Nope": Skip()}), "End": Skip()})

def test_a_field_with_a_column_can_still_be_skipped_and_a_ref_may_point_at_an_interface():
    """Checks that Skip leaves out a field that has a column, and that a Ref is accepted for a field typed with an interface.

    Protects the two decisions that are allowed on more than their usual field.
    """
    assert columns_of(PointLike, fields={"Z": Skip()})["Z"] == (None, "skip")
    assert columns_of(GeometryHolder, fields={**BASE_SKIPPED, "Geometry": Ref("main.default.Geometry"), "Curves": Skip()})["Geometry_id"] == ("STRING", "ref")

def test_a_generic_class_is_refused_by_every_helper():
    """Checks that describe, custom_fields and require_decided raise for Wrapper_1, naming the class and its type parameter.

    Protects the rule that a table cannot record which type argument its rows were written with.
    """
    for helper in (describe, custom_fields, require_decided):
        with pytest.raises(UnmappedType, match=r"Wrapper_1 is a generic class \(type parameters T\)"):
            helper(Wrapper_1)  # pyright: ignore[reportArgumentType]
