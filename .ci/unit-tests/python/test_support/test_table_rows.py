"""Rows to objects and back with bhom_schema.tables, against the classes of the FixtureAlpha_oM assembly that the package carries.

The round trip of every kind of field is the test that matters most: an object written with `to_row` and read with `from_row` is equal to the object.
"""

from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from bhom_schema.FixtureAlpha_oM.Beam import Beam
from bhom_schema.FixtureAlpha_oM.Collections import Collections
from bhom_schema.FixtureAlpha_oM.CycleA import CycleA
from bhom_schema.FixtureAlpha_oM.GeometryHolder import GeometryHolder
from bhom_schema.FixtureAlpha_oM.LineLike import LineLike
from bhom_schema.FixtureAlpha_oM.Options import Options
from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
from bhom_schema.FixtureAlpha_oM.Scalars import Scalars
from bhom_schema.FixtureAlpha_oM.SupportKind import SupportKind
from bhom_schema.tables import BASE_SKIPPED, Json, Ref, RowError, Skip, Struct, UnmappedType, ddl_schema, example_row, from_row, rows_to_objects, to_row

POINT = Ref("main.default.PointLike")
LINE_REFS = {"Start": POINT, "End": POINT}
LINE_STRUCTS = {"Start": Struct(), "End": Struct()}
UUID_TEXT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

def a_line() -> LineLike:
    """Builds a LineLike with two different points and a label, so a round trip cannot pass by comparing defaults."""
    return LineLike(Start=PointLike(X=1, Y=2, Z=3), End=PointLike(X=4, Y=5, Z=6), Infinite=True, Label="axis")

class FakeRow:
    """Stands in for a Spark Row: it is not a dict, and gives a dict through asDict, as pyspark does."""

    def __init__(self, values: dict[str, Any]) -> None:
        """Keeps the values the row holds."""
        self.values = values

    def asDict(self, recursive: bool = False) -> dict[str, Any]:
        """Returns the values as a dict, the way a Row does."""
        return self.values

def test_a_line_with_struct_points_round_trips_and_keeps_the_points_inside_the_row():
    """Checks the row of a LineLike whose points are Structs: nested dicts under the field names, an added `_id`, and the object that comes back.

    Protects the Struct decision end to end, the one that stores objects inside the row.
    """
    line = a_line()

    row = to_row(line, fields=LINE_STRUCTS)

    assert list(row) == ["_id", "_bhomVersion", "Start", "End", "Infinite", "Label"]
    assert UUID_TEXT.match(row["_id"])
    assert row["Start"] == {"X": 1.0, "Y": 2.0, "Z": 3.0}
    assert row["End"] == {"X": 4.0, "Y": 5.0, "Z": 6.0}
    assert from_row(LineLike, row, fields=LINE_STRUCTS) == line

def test_a_line_with_ref_points_takes_the_ids_and_the_held_objects():
    """Checks that the Ref columns hold the ids that were passed, that the key can be given, and that from_row takes the points from `held`.

    Protects the multi-table write and read, where the user links the tables.
    """
    line = a_line()

    row = to_row(line, fields=LINE_REFS, ids={"_id": "line-1", "Start": "p-1", "End": "p-2"})

    assert row == {"_id": "line-1", "_bhomVersion": None, "Start_id": "p-1", "End_id": "p-2", "Infinite": True, "Label": "axis"}
    assert from_row(LineLike, row, fields=LINE_REFS, held={"Start": line.Start, "End": line.End}) == line

def test_a_ref_needs_an_id_unless_the_field_is_empty_and_an_unknown_id_name_is_refused():
    """Checks that a Ref field with an object but no id raises, that `None` is a way to say no row, that an empty optional field needs none, and that ids rejects other names.

    Protects the link columns from being left empty by mistake, and a typo in ids from being ignored.
    """
    with pytest.raises(ValueError, match=r"Start is a Ref: pass ids=\{'Start'"):
        to_row(a_line(), fields=LINE_REFS)

    assert to_row(a_line(), fields=LINE_REFS, ids={"Start": None, "End": None})["Start_id"] is None

    with pytest.raises(ValueError, match="ids names 'Strat'"):
        to_row(a_line(), fields=LINE_REFS, ids={"Strat": "x"})

def test_a_ref_without_a_held_object_keeps_the_default_with_a_warning():
    """Checks that reading a row whose Ref has no entry in `held` leaves the field at its default and warns, naming the field.

    Protects the user from a silent default where an object was expected.
    """
    row = {"_id": "l", "Start_id": "p-1", "End_id": None, "Infinite": False}

    with pytest.warns(UserWarning, match="Start is a Ref to the row p-1"):
        line = from_row(LineLike, row, fields=LINE_REFS)

    assert line.Start == PointLike()

def test_the_key_is_a_made_up_uuid_text_or_the_guid_of_a_bhomobject():
    """Checks that an added `_id` is a lower-case uuid4 text and differs per call, and that a BHoMObject row holds its BHoM_Guid as text.

    Protects the form of the ids, which is one form whichever table a Ref points at.
    """
    first = to_row(PointLike())["_id"]

    assert UUID_TEXT.match(first)
    assert to_row(PointLike())["_id"] != first

    beam = Beam(Start=PointLike())
    row = to_row(beam, fields={**BASE_SKIPPED, "Start": Struct()})

    assert row["BHoM_Guid"] == str(beam.BHoM_Guid)
    assert "_id" not in row

def test_values_are_converted_to_what_a_column_holds():
    """Checks the row of a Beam: enum names (`None` for None_), flag names, a BHoM_Guid as text, and of Collections: a set as a sorted list; of Scalars: seconds and a UUID text.

    Protects the conversions of the type mapping.
    """
    beam = Beam(Start=PointLike(), Support=SupportKind.None_, Flags=Options.A | Options.B, Count=2_000_000_000_000)
    row = to_row(beam, fields={**BASE_SKIPPED, "Start": Struct()})

    assert row["Support"] == "None"
    assert row["Flags"] == "Both"
    assert row["Count"] == 2_000_000_000_000
    assert to_row(Collections(Names={"b", "a", "c"}), fields={**BASE_SKIPPED, "Points": Skip(), "ByPoint": Skip(), "Pair": Skip(), "Anything": Skip()})["Names"] == ["a", "b", "c"]

    scalars = to_row(Scalars(), fields={**BASE_SKIPPED, "Colour": Skip(), "TypeRef": Skip(), "Callback": Skip()})

    assert scalars["Duration"] == 90.0
    assert scalars["Key"] == "00000000-0000-0000-0000-000000000000"

def test_every_kind_of_field_round_trips():
    """Checks from_row(to_row(x)) == x for Beam, Collections (sets, a list of classes as ARRAY of STRUCT, tuples and `Any` as JSON), Scalars and GeometryHolder (interface fields as JSON).

    Protects the whole mapping: if a conversion loses a value, an object does not come back equal.
    """
    skip_rest = {"Colour": Skip(), "TypeRef": Skip(), "Callback": Skip(), **BASE_SKIPPED}
    cases: list[tuple[Any, dict[str, Any]]] = [
        (Beam(Start=PointLike(X=1), Support=SupportKind.Fixed, Flags=Options.B, Count=7, Small=0.25, Tags={"x", "y"}), {**BASE_SKIPPED, "Start": Struct()}),
        (Scalars(Quote="it's"), skip_rest),
        (
            Collections(
                Names={"b", "a"}, Points=[PointLike(X=1), PointLike(Y=2)], Lookup={"k": 1.5}, ByPoint=[(PointLike(X=2), "z")], Values=[1.0, 2.0],
                Matrix=[[1, 2], [3]], Words=["p"], OptionalCount=4, Pair=(1, "x"), Anything={"a": [1, 2]}),
            {**BASE_SKIPPED, "Points": Struct(), "ByPoint": Json(), "Pair": Json(), "Anything": Json()}),
        (GeometryHolder(Geometry=PointLike(X=1), Curves=[a_line()]), {**BASE_SKIPPED, "Geometry": Json(), "Curves": Json()}),
        (a_line(), LINE_STRUCTS),
    ]

    for item, fields in cases:
        assert from_row(type(item), to_row(item, fields=fields), fields=fields) == item, type(item).__name__

def test_a_null_or_a_missing_column_reads_as_the_default():
    """Checks that a NULL in a non-optional column (`Infinite: bool`), and a row from before a column was added, read as the default of the field.

    Protects the reading of rows written by an older version of the table.
    """
    row = {"_id": "l", "Infinite": None, "Label": "a"}

    line = from_row(LineLike, row, fields={"Start": Skip(), "End": Skip()})

    assert line.Infinite is False
    assert line.Label == "a"
    assert from_row(PointLike, {"X": 1.5}).Y == 0.0

def test_a_value_that_does_not_fit_raises_a_validation_error():
    """Checks that a text in a DOUBLE column raises pydantic's ValidationError from from_row.

    Protects the user from a table that does not hold what the class says.
    """
    with pytest.raises(ValidationError):
        from_row(PointLike, {"X": "not a number"})

def test_to_row_refuses_what_the_column_cannot_hold():
    """Checks the refusals: an int outside 32 bits for an INT column, one outside 64 for BIGINT, and a datetime with a time zone.

    Protects the write from failing late, inside Spark, with a message that names no field.
    """
    with pytest.raises(ValueError, match=r"Count is 9223372036854775808, which does not fit its BIGINT column"):
        to_row(Beam(Start=PointLike(), Count=2 ** 63), fields={**BASE_SKIPPED, "Start": Struct()})

    with pytest.raises(ValueError, match="OptionalCount is 3000000000, which does not fit its INT column"):
        to_row(Collections(OptionalCount=3_000_000_000), fields={**BASE_SKIPPED, "Points": Skip(), "ByPoint": Skip(), "Pair": Skip(), "Anything": Skip()})

    with pytest.raises(ValueError, match="Fixed is a datetime with a time zone"):
        to_row(Scalars(Fixed=datetime(2020, 1, 1, tzinfo=timezone.utc)), fields={**BASE_SKIPPED, "Colour": Skip(), "TypeRef": Skip(), "Callback": Skip()})

def test_a_spark_row_and_its_struct_values_are_read_through_asdict():
    """Checks that from_row reads a row object that is not a dict, with a struct value that is one too, through `asDict`.

    Protects the use with Spark, whose rows and struct values are Row objects.
    """
    row = FakeRow({"_id": "l", "Start": FakeRow({"X": 1.0, "Y": 2.0, "Z": 3.0}), "End": None, "Infinite": False, "Label": None})

    line = from_row(LineLike, row, fields=LINE_STRUCTS)

    assert line.Start == PointLike(X=1, Y=2, Z=3)
    assert line.End == PointLike()

def test_a_json_cell_can_be_text_or_an_already_parsed_value():
    """Checks that a Json column read back as text, or as a parsed dict, gives the same object.

    Protects against a catalog that returns the value of a column in another form than the one that was written.
    """
    fields = {**BASE_SKIPPED, "Geometry": Json(), "Curves": Skip()}
    row = to_row(GeometryHolder(Geometry=PointLike(X=9)), fields=fields)

    assert isinstance(row["Geometry"], str)

    row["Geometry"] = {"_t": "BH.oM.FixtureAlpha.PointLike", "X": 9.0}

    assert from_row(GeometryHolder, row, fields=fields).Geometry == PointLike(X=9)

def test_rows_to_objects_reads_many_rows_and_keys_them_by_id():
    """Checks the list of objects, and `keyed=True` giving {id: object} with the generated keys, which is what `held` of another table needs.

    Protects the multi-table read: the points are read keyed, then the lines take them from `held`.
    """
    points = [PointLike(X=float(index)) for index in range(3)]
    rows = [to_row(point) for point in points]

    assert rows_to_objects(PointLike, rows) == points

    keyed = rows_to_objects(PointLike, rows, keyed=True)

    assert keyed == {row["_id"]: point for row, point in zip(rows, points)}

def test_rows_to_objects_resolves_refs_from_held_by_id():
    """Checks that the lines of two rows take their points from the {id: object} dicts of `held`, and that a missing id warns and keeps the default.

    Protects the join the user writes between two tables.
    """
    start = PointLike(X=1)
    end = PointLike(X=2)
    held = {"Start": {"s": start}, "End": {"e": end}}
    rows = [
        to_row(a_line(), fields=LINE_REFS, ids={"Start": "s", "End": "e"}),
        to_row(a_line(), fields=LINE_REFS, ids={"Start": "s", "End": "gone"}),
    ]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        lines = rows_to_objects(LineLike, rows, fields=LINE_REFS, held=held)

    assert [line.Start for line in lines] == [start, start]
    assert [line.End for line in lines] == [end, PointLike()]
    assert len(caught) == 1 and "End is a Ref to the row gone" in str(caught[0].message)

def test_rows_to_objects_can_collect_the_bad_rows():
    """Checks that errors='collect' returns the good objects and a RowError per bad row, with its position and key, and that errors='raise' raises for the first.

    Protects the read of a large table from stopping at one bad row.
    """
    rows = [{"_id": "a", "X": 1.0}, {"_id": "b", "X": "bad"}, {"_id": "c", "X": 3.0}]

    result, problems = rows_to_objects(PointLike, rows, errors="collect")

    assert [point.X for point in result] == [1.0, 3.0]
    assert [(problem.index, problem.key) for problem in problems] == [(1, "b")]
    assert isinstance(problems[0], RowError)
    assert "X" in problems[0].message

    with pytest.raises(ValidationError):
        rows_to_objects(PointLike, rows)

    keyed, problems = rows_to_objects(PointLike, rows, keyed=True, errors="collect")

    assert list(keyed) == ["a", "c"]
    assert len(problems) == 1

def test_keyed_needs_a_key():
    """Checks that keyed=True raises when the table has no key, and when a row has no value in the key column.

    Protects the dict from being built on missing ids.
    """
    with pytest.raises(ValueError, match="needs a key"):
        rows_to_objects(PointLike, [], key=None, keyed=True)

    with pytest.raises(ValueError, match="1 rows have no value in the key column"):
        rows_to_objects(PointLike, [{"X": 1.0}], keyed=True)

def test_a_ref_inside_a_struct_is_refused():
    """Checks that a Struct whose nested class is given a Ref raises, since nothing could follow an id inside a struct.

    Protects the Struct decision from a column that can never be read back.
    """
    with pytest.raises(ValueError, match="is a Ref inside a Struct"):
        to_row(CycleA(), fields={"Other": Struct(fields={"Other": POINT})})

def test_ddl_schema_lists_the_columns_of_the_table_for_createdataframe():
    """Checks the DDL string for LineLike with Refs and with Structs, and that an undecided field raises.

    Protects the pairing of the rows with the table: the same columns create_table_sql makes.
    """
    assert ddl_schema(LineLike, fields=LINE_REFS) == "`_id` STRING NOT NULL, `_bhomVersion` STRING, `Start_id` STRING, `End_id` STRING, `Infinite` BOOLEAN, `Label` STRING"
    assert "`Start` STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE>, " in ddl_schema(LineLike, fields=LINE_STRUCTS)

    with pytest.raises(UnmappedType):
        ddl_schema(LineLike)

def test_example_row_holds_the_defaults_with_empty_refs():
    """Checks the example row of LineLike: defaults, a made-up `_id`, empty Ref columns, and that it reads back as a default object.

    Protects the smoke test of a new table.
    """
    row = example_row(LineLike, fields=LINE_REFS)

    assert UUID_TEXT.match(row["_id"])
    assert (row["Start_id"], row["End_id"], row["Infinite"], row["Label"]) == (None, None, False, None)
    assert example_row(PointLike)["X"] == 0.0
