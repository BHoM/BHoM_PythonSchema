"""A stand-in for a SparkSession that the tests of bhom_schema.mapping share: tables in memory, the few statements the helpers send, and DataFrames over dict rows.

It understands what the helpers ask for and nothing more: CREATE TABLE (with IF NOT EXISTS and OR REPLACE), DROP TABLE IF EXISTS, ALTER TABLE ... ADD COLUMNS, other statements (recorded),
`createDataFrame` with a DDL string, `saveAsTable` in append mode (refusing a column the table does not have, as Delta does) or overwrite mode, `table`, `where` with an IN list, `limit`, `collect`, `columns` and `catalog.tableExists`.
"""

from __future__ import annotations

import re
from typing import Any

CREATE = re.compile(r"^CREATE (?P<replace>OR REPLACE )?TABLE (?P<exists>IF NOT EXISTS )?(?P<name>\S+) \(\n(?P<body>.*?)\n\)", re.S)
DROP = re.compile(r"^DROP TABLE IF EXISTS (?P<name>\S+)$")
ADD_COLUMNS = re.compile(r"^ALTER TABLE (?P<name>\S+) ADD COLUMNS \(`(?P<column>[^`]+)` \w+\)$")
IN_LIST = re.compile(r"^`(?P<column>[^`]+)` IN \((?P<items>.*)\)$")

class FakeRow:
    """A row that gives its values as a dict through asDict, as a Spark Row does."""

    def __init__(self, values: dict[str, Any]) -> None:
        """Keeps the values of the row."""
        self.values = values

    def asDict(self, recursive: bool = False) -> dict[str, Any]:
        """Returns a copy of the values."""
        return dict(self.values)

class FakeTable:
    """A table: its column names and its rows."""

    def __init__(self, columns: list[str], rows: list[dict[str, Any]] | None = None) -> None:
        """Keeps the columns and the rows."""
        self.columns = columns
        self.rows = rows if rows is not None else []

class FakeWriter:
    """The `write` of a frame: it appends the rows of the frame to the table that saveAsTable names, refusing a column the table does not have; in overwrite mode it makes the table again from the frame."""

    def __init__(self, session: FakeSpark, rows: list[dict[str, Any]], columns: list[str]) -> None:
        """Keeps the session, the rows to write and their columns."""
        self.session = session
        self.rows = rows
        self.columns = columns
        self.mode_name = ""

    def mode(self, name: str) -> FakeWriter:
        """Records the write mode and returns the writer."""
        self.mode_name = name
        return self

    def option(self, name: str, value: str) -> FakeWriter:
        """Accepts a write option (such as overwriteSchema) and returns the writer."""
        return self

    def saveAsTable(self, name: str) -> None:
        """Appends the rows to the table."""
        key = name.replace("`", "")
        if self.mode_name == "overwrite" or key not in self.session.tables:
            self.session.tables[key] = FakeTable(list(self.columns), [])

        assert self.mode_name in ("append", "overwrite")
        table = self.session.tables[key]
        for row in self.rows:
            unknown = [column for column in row if column not in table.columns]
            if unknown:
                raise ValueError(f"[DELTA_FAILED_TO_MERGE_FIELDS] {', '.join(unknown)} is not a column of {name}")

        table.rows.extend(dict(row) for row in self.rows)

class FakeFrame:
    """A DataFrame over a list of dict rows and the column names it was made with."""

    def __init__(self, session: FakeSpark, rows: list[dict[str, Any]], columns: list[str]) -> None:
        """Keeps the session, the rows and the columns."""
        self.session = session
        self.rows = rows
        self.columns = columns

    @property
    def write(self) -> FakeWriter:
        """Returns the writer of the frame."""
        return FakeWriter(self.session, self.rows, self.columns)

    def where(self, condition: str) -> FakeFrame:
        """Keeps the rows that an `IN` condition lets through; any other condition keeps every row."""
        match = IN_LIST.match(condition)
        if match is None:
            return self

        items = {item.strip()[1:-1].replace("\\'", "'") for item in match["items"].split(", ")}
        return FakeFrame(self.session, [row for row in self.rows if row.get(match["column"]) in items], self.columns)

    def limit(self, count: int) -> FakeFrame:
        """Keeps the first rows."""
        return FakeFrame(self.session, self.rows[:count], self.columns)

    def collect(self) -> list[FakeRow]:
        """Returns the rows."""
        return [FakeRow(row) for row in self.rows]

class FakeCatalog:
    """The catalog of the session: it knows which tables exist."""

    def __init__(self, session: FakeSpark) -> None:
        """Keeps the session."""
        self.session = session

    def tableExists(self, name: str) -> bool:
        """Tells whether the table exists."""
        return name in self.session.tables

class FakeSpark:
    """A session with tables in memory. `statements` records every statement run through `sql`, and `tables` holds the tables by their full name without backticks."""

    def __init__(self, tables: dict[str, FakeTable] | None = None) -> None:
        """Starts with the given tables (none by default) and an empty log."""
        self.tables = tables if tables is not None else {}
        self.statements: list[str] = []
        self.catalog = FakeCatalog(self)

    @staticmethod
    def silver(name: str, rows: list[dict[str, Any]], columns: list[str] | None = None) -> FakeSpark:
        """Returns a session with one table, whose columns are those given or the keys of the first row."""
        return FakeSpark({name: FakeTable(columns if columns is not None else list(rows[0]) if rows else [], rows)})

    def sql(self, statement: str) -> None:
        """Records the statement, and acts on CREATE TABLE and ALTER TABLE ... ADD COLUMNS."""
        self.statements.append(statement)
        created = CREATE.match(statement)
        if created:
            name = created["name"].replace("`", "")
            columns = [line.strip().split("`")[1] for line in created["body"].splitlines() if line.strip().startswith("`")]
            if created["replace"] or name not in self.tables:
                self.tables[name] = FakeTable(columns)

            return

        dropped = DROP.match(statement)
        if dropped:
            self.tables.pop(dropped["name"].replace("`", ""), None)
            return

        added = ADD_COLUMNS.match(statement)
        if added:
            self.tables[added["name"].replace("`", "")].columns.append(added["column"])

    def table(self, name: str) -> FakeFrame:
        """Returns the frame of a table."""
        found = self.tables[name.replace("`", "")]
        return FakeFrame(self, found.rows, found.columns)

    def createDataFrame(self, rows: list[dict[str, Any]], schema: str) -> FakeFrame:
        """Returns a frame over the rows, with the column names of the DDL schema."""
        return FakeFrame(self, rows, re.findall(r"`([^`]+)`", schema))

class FakePandas:
    """A pandas DataFrame, as far as the helpers use it: `head` and `to_dict("records")`."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Keeps the rows."""
        self.rows = rows

    def head(self, count: int) -> FakePandas:
        """Returns the first rows."""
        return FakePandas(self.rows[:count])

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        """Returns the rows as a list of dicts."""
        assert orient == "records"
        return [dict(row) for row in self.rows]
