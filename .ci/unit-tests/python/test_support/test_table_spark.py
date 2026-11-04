"""The Spark helpers of bhom_schema.tables, run against a stand-in SparkSession that keeps tables in memory and records what it is asked.

The stand-in understands only what the helpers send: SQL statements (recorded), `createDataFrame` with a DDL string, `saveAsTable` in append mode, `table`, `where` with an
`IN` list, `limit` and `collect`. The real workspace check is the notebook of the guide.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from bhom_schema.FixtureAlpha_oM.LineLike import LineLike
from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
from bhom_schema.tables import Ref, Struct, UnmappedType, rows_to_objects
from bhom_schema.tables.spark import create_table, fetch_by_ids, read_objects, read_rows, write_objects

POINT = Ref("main.default.PointLike")
LINE_REFS = {"Start": POINT, "End": POINT}
IN_LIST = re.compile(r"^`(?P<column>[^`]+)` IN \((?P<items>.*)\)$")

class FakeRow:
    """A row of the stand-in, which gives its values as a dict through asDict, as a Spark Row does."""

    def __init__(self, values: dict[str, Any]) -> None:
        """Keeps the values of the row."""
        self.values = values

    def asDict(self, recursive: bool = False) -> dict[str, Any]:
        """Returns a copy of the values."""
        return dict(self.values)

class FakeWriter:
    """The `write` of a stand-in frame: it records the mode and appends the rows to the table that saveAsTable names."""

    def __init__(self, session: FakeSession, rows: list[dict[str, Any]]) -> None:
        """Keeps the session whose tables are written, and the rows to write."""
        self.session = session
        self.rows = rows
        self.mode_name = ""

    def mode(self, name: str) -> FakeWriter:
        """Records the write mode and returns the writer, as the real one does."""
        self.mode_name = name
        return self

    def saveAsTable(self, name: str) -> None:
        """Appends the rows to the named table, creating it when it does not exist, and records the call."""
        assert self.mode_name == "append"
        self.session.saved.append(name)
        self.session.tables.setdefault(name.replace("`", ""), []).extend(self.rows)

class FakeFrame:
    """A stand-in DataFrame over a list of dict rows."""

    def __init__(self, session: FakeSession, rows: list[dict[str, Any]]) -> None:
        """Keeps the session and the rows."""
        self.session = session
        self.rows = rows

    @property
    def write(self) -> FakeWriter:
        """Returns the writer of the frame."""
        return FakeWriter(self.session, self.rows)

    def where(self, condition: str) -> FakeFrame:
        """Records the condition and keeps the rows that an `IN` condition lets through; any other condition keeps every row."""
        self.session.conditions.append(condition)
        match = IN_LIST.match(condition)
        if match is None:
            return self

        items = {item.strip()[1:-1].replace("\\'", "'") for item in match["items"].split(", ")}
        return FakeFrame(self.session, [row for row in self.rows if row.get(match["column"]) in items])

    def limit(self, count: int) -> FakeFrame:
        """Keeps the first rows."""
        return FakeFrame(self.session, self.rows[:count])

    def collect(self) -> list[FakeRow]:
        """Returns the rows as stand-in Row objects."""
        return [FakeRow(row) for row in self.rows]

class FakeSession:
    """A stand-in SparkSession: it keeps the tables in memory and records the SQL, the schemas and the conditions it was given."""

    def __init__(self) -> None:
        """Starts with no tables and nothing recorded."""
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.statements: list[str] = []
        self.schemas: list[str] = []
        self.saved: list[str] = []
        self.conditions: list[str] = []

    def sql(self, statement: str) -> None:
        """Records a statement."""
        self.statements.append(statement)

    def createDataFrame(self, rows: list[dict[str, Any]], schema: str) -> FakeFrame:
        """Records the DDL schema and returns a frame over the rows."""
        self.schemas.append(schema)
        return FakeFrame(self, rows)

    def table(self, name: str) -> FakeFrame:
        """Returns a frame over the rows of a table; the name comes back as `a`.`b`.`c`, and is looked up without the backticks."""
        return FakeFrame(self, list(self.tables[name.replace("`", "")]))

def a_line(index: int) -> LineLike:
    """Builds a LineLike with its own points, so each line of a test can be told apart."""
    return LineLike(Start=PointLike(X=index), End=PointLike(X=index + 100, Y=1), Infinite=index % 2 == 0, Label=f"line-{index}")

def test_create_table_runs_the_statement_and_returns_it():
    """Checks that create_table sends exactly the create_table_sql text to spark.sql and returns it.

    Protects the pairing of the notebook cell with the SQL the user can read and copy.
    """
    session = FakeSession()

    sql = create_table(session, PointLike, "main.default.PointLike")

    assert session.statements == [sql]
    assert sql.startswith("CREATE TABLE IF NOT EXISTS `main`.`default`.`PointLike` (")

def test_write_objects_appends_rows_with_the_schema_of_the_table_and_returns_the_keys():
    """Checks that the rows go to the quoted table in append mode with the DDL schema of the class, and that the returned keys are the `_id` of each row, in order.

    Protects the write: the same columns as the table, and the keys that the next table's Ref columns need.
    """
    session = FakeSession()
    points = [PointLike(X=1), PointLike(X=2)]

    keys = write_objects(session, points, "main.default.PointLike", ids=[{"_id": "p-1"}, {"_id": "p-2"}])

    assert keys == ["p-1", "p-2"]
    assert session.saved == ["`main`.`default`.`PointLike`"]
    assert session.schemas == ["`_id` STRING NOT NULL, `_bhomVersion` STRING, `X` DOUBLE, `Y` DOUBLE, `Z` DOUBLE"]
    assert [row["_id"] for row in session.tables["main.default.PointLike"]] == ["p-1", "p-2"]
    assert [row["X"] for row in session.tables["main.default.PointLike"]] == [1.0, 2.0]

def test_write_objects_refuses_what_it_cannot_write_as_one_table():
    """Checks that mixed classes, an ids list of the wrong length, a value that does not fit its column and an undecided field raise before anything is written, and that no objects write nothing.

    Protects the table from a partial or mixed write.
    """
    session = FakeSession()

    with pytest.raises(TypeError, match="one class at a time: PointLike and LineLike"):
        write_objects(session, [PointLike(), a_line(1)], "main.default.PointLike")

    with pytest.raises(ValueError, match="ids has 1 entries for 2 objects"):
        write_objects(session, [PointLike(), PointLike()], "main.default.PointLike", ids=[{}])

    with pytest.raises(ValueError, match="Start is a Ref"):
        write_objects(session, [a_line(1)], "main.default.LineLike", fields=LINE_REFS)

    with pytest.raises(UnmappedType, match="custom type"):
        write_objects(session, [a_line(1)], "main.default.LineLike")

    assert write_objects(session, [], "main.default.PointLike") == []
    assert session.tables == {} and session.saved == []

def test_a_table_without_a_key_returns_no_keys():
    """Checks that write_objects with key=None writes the rows and returns an empty list.

    Protects the return value for a table that has no key column.
    """
    session = FakeSession()

    assert write_objects(session, [PointLike()], "main.default.PointLike", key=None) == []
    assert "_id" not in session.tables["main.default.PointLike"][0]

def test_read_rows_takes_a_condition_and_a_limit():
    """Checks that read_rows collects dict rows, applies a limit, and sends the condition it was given.

    Protects the slice of a large table that a notebook reads.
    """
    session = FakeSession()
    session.tables["main.default.PointLike"] = [{"_id": str(index), "X": float(index)} for index in range(5)]

    assert [row["X"] for row in read_rows(session, "main.default.PointLike", limit=2)] == [0.0, 1.0]

    read_rows(session, "main.default.PointLike", where="X > 1")

    assert session.conditions == ["X > 1"]

def test_fetch_by_ids_reads_the_rows_in_batches_and_escapes_the_ids():
    """Checks that the ids are de-duplicated, None is dropped, an id with a quote is escaped, the ids go in batches of the size asked, and missing ids are not an error.

    Protects the step from one table to the next, which can name millions of ids.
    """
    session = FakeSession()
    session.tables["main.default.PointLike"] = [{"_id": "a"}, {"_id": "b'c"}, {"_id": "d"}]

    rows = fetch_by_ids(session, "main.default.PointLike", ["a", "a", None, "b'c", "d", "gone"], batch=2)

    assert [row["_id"] for row in rows] == ["a", "b'c", "d"]
    assert session.conditions == ["`_id` IN ('a', 'b\\'c')", "`_id` IN ('d', 'gone')"]
    assert fetch_by_ids(session, "main.default.PointLike", []) == []

def test_fetch_by_ids_uses_the_key_column_of_the_table():
    """Checks that `key` names the column that is searched, as for the table of a BHoMObject, whose key is BHoM_Guid.

    Protects the join to a table whose key is not `_id`.
    """
    session = FakeSession()
    session.tables["t.s.beam"] = [{"BHoM_Guid": "g-1"}, {"BHoM_Guid": "g-2"}]

    assert fetch_by_ids(session, "t.s.beam", ["g-2"], key="BHoM_Guid") == [{"BHoM_Guid": "g-2"}]
    assert session.conditions == ["`BHoM_Guid` IN ('g-2')"]

def test_lines_and_points_in_two_tables_round_trip_as_in_the_guide():
    """Checks the multi-table write and read of the guide: the points first, then the lines with the keys of their points, then the lines read with the points that they name.

    Protects the whole Ref flow, from objects to tables and back to equal objects.
    """
    session = FakeSession()
    lines = [a_line(index) for index in range(4)]

    starts = write_objects(session, [line.Start for line in lines], "main.default.PointLike")
    ends = write_objects(session, [line.End for line in lines], "main.default.PointLike")
    write_objects(session, lines, "main.default.LineLike", fields=LINE_REFS, ids=[{"Start": start, "End": end} for start, end in zip(starts, ends)])

    assert len(session.tables["main.default.PointLike"]) == 8
    assert len(session.tables["main.default.LineLike"]) == 4

    line_rows = read_rows(session, "main.default.LineLike", limit=3)
    point_ids = {row["Start_id"] for row in line_rows} | {row["End_id"] for row in line_rows}
    points = rows_to_objects(PointLike, fetch_by_ids(session, "main.default.PointLike", point_ids), keyed=True)
    found = rows_to_objects(LineLike, line_rows, fields=LINE_REFS, held={"Start": points, "End": points})

    assert found == lines[:3]

def test_lines_with_struct_points_round_trip_through_one_table():
    """Checks the Struct variant: one table, the points inside each row, written and read back with read_objects.

    Protects the Struct decision through the Spark helpers.
    """
    session = FakeSession()
    lines = [a_line(index) for index in range(3)]
    fields = {"Start": Struct(), "End": Struct()}

    write_objects(session, lines, "main.default.LineLikeStruct", fields=fields)

    assert read_objects(session, LineLike, "main.default.LineLikeStruct", fields=fields) == lines
    assert len(read_objects(session, LineLike, "main.default.LineLikeStruct", fields=fields, limit=2)) == 2

    keyed = read_objects(session, LineLike, "main.default.LineLikeStruct", fields=fields, keyed=True)

    assert list(keyed) == [row["_id"] for row in session.tables["main.default.LineLikeStruct"]]
    assert list(keyed.values()) == lines
