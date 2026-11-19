"""Facts about a silver table: what each column holds, a few real rows, and what a key that someone proposes says about the table.

Nothing here proposes anything. The profile is made from rows (dictionaries), so the core needs no Spark; `profile`, `sample_rows` and `check_key` read a slice of the table with `read_rows`.
Genie Code reads the profile instead of the data, so only counts and a few example values go into the conversation.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from bhom_schema.tables.spark import read_rows
from bhom_schema.tables.sql import quote_table

TOP = 5
# A column that is constant in this share of the groups, or more, is reported as almost constant
ALMOST = 0.9
MAX_SAMPLE = 50
SAMPLE_WIDTH = 80
EXAMPLES = 3

@dataclass(frozen=True)
class ColumnProfile:
    """What one silver column holds, over the rows that were read.

    `kind` is `number`, `text`, `boolean`, `datetime`, `collection`, `mixed` (more than one of these) or `empty`. `top` is the most common values with their counts. `minimum`, `median`
    and `maximum` are set for a column of numbers.
    """

    name: str
    kind: str
    rows: int
    nulls: int
    distinct: int
    top: tuple[tuple[Any, int], ...]
    minimum: float | None = None
    median: float | None = None
    maximum: float | None = None

    @property
    def null_rate(self) -> float:
        """Returns the share of the rows where the column is empty, between 0 and 1."""
        return self.nulls / self.rows if self.rows else 0.0

    def values(self) -> list[Any]:
        """Returns the most common values, without their counts."""
        return [value for value, _ in self.top]

    def text(self) -> str:
        """Writes the profile of the column on one line: the name, how it is held, the empty share, the number of values, the range for numbers and the most common values."""
        parts = [f"{self.name}: {self.kind}", f"{self.null_rate:.0%} empty", f"{self.distinct} distinct"]
        if self.minimum is not None:
            parts.append(f"range {self.minimum:g} to {self.maximum:g}, median {self.median:g}")

        parts.append("top " + ", ".join(f"{value!r} x{count}" for value, count in self.top))
        return "; ".join(parts)

@dataclass(frozen=True)
class TableProfile:
    """The profile of a table: the number of `rows` read, whether they are only a `sampled` slice of the table, and a profile for each column."""

    table: str
    rows: int
    sampled: bool
    columns: tuple[ColumnProfile, ...]

    def column(self, name: str) -> ColumnProfile:
        """Returns the profile of a column, or raises KeyError."""
        for column in self.columns:
            if column.name == name:
                return column

        raise KeyError(name)

    def text(self) -> str:
        """Writes the profile for reading: the table, the rows read (and that they are a sample), then one line per column."""
        head = f"{self.table}: {self.rows} rows" + (" (a sample: the table has more)" if self.sampled else "")
        return "\n".join([head, *(column.text() for column in self.columns)])

@dataclass(frozen=True)
class KeyConflict:
    """A column that has one value in most groups of a key but two or more in some: `groups` is how many, and `examples` are a few of them as (key values, the values found)."""

    column: str
    groups: int
    examples: tuple[tuple[tuple[Any, ...], tuple[Any, ...]], ...]

@dataclass(frozen=True)
class KeyCheck:
    """What a proposed key says about the table.

    `groups` is how many different values the key columns have together, over `rows` rows (`empty_rows` have no value in a key column and are left out). `constant` are the other columns that have
    one value in every group: the columns that describe what the key identifies. `almost` are the columns with one value in most groups, with the share, and `conflicts` shows the groups
    where they have more. `varying` are the columns that differ within groups, which describe something finer than the key.
    """

    keys: tuple[str, ...]
    rows: int
    empty_rows: int
    groups: int
    constant: tuple[str, ...]
    almost: tuple[tuple[str, float], ...]
    conflicts: tuple[KeyConflict, ...]
    varying: tuple[str, ...]

    def text(self) -> str:
        """Writes the check for reading: the groups, the constant columns, each almost-constant column with its conflicting groups, and the columns that vary."""
        skipped = f" ({self.empty_rows} rows with an empty key column left out)" if self.empty_rows else ""
        lines = [f"key {', '.join(self.keys)}: {self.groups} groups over {self.rows - self.empty_rows} rows{skipped}", f"  constant in every group: {', '.join(self.constant) or 'none'}"]
        shares = dict(self.almost)
        for conflict in self.conflicts:
            shown = "; ".join(f"{key} has {', '.join(map(repr, values))}" for key, values in conflict.examples)
            lines.append(f"  {conflict.column}: one value in {shares[conflict.column]:.0%} of the groups, but {conflict.groups} groups have more ({shown})")

        lines.append(f"  vary within groups: {', '.join(self.varying) or 'none'}")
        return "\n".join(lines)

def kind_of_value(value: Any) -> str:
    """Names how a Python value is held: `boolean` (before `number`, because a bool is an int), `number`, `text`, `datetime` or `collection`."""
    if isinstance(value, bool):
        return "boolean"

    if isinstance(value, int | float | Decimal):
        return "number"

    if isinstance(value, str):
        return "text"

    if isinstance(value, datetime | date):
        return "datetime"

    return "collection"

def hashable(value: Any) -> Hashable:
    """Returns the value if it can be counted, or its text when it is a list or a dictionary."""
    try:
        hash(value)
    except TypeError:
        return str(value)

    return value

def empty(value: Any) -> bool:
    """Tells whether a cell is empty: None, an empty text, or a number that is not a number (NaN)."""
    return value is None or value == "" or (isinstance(value, float) and value != value)

def profile_column(name: str, values: Sequence[Any]) -> ColumnProfile:
    """Profiles one column from its values: the kind, how many are empty, how many different ones there are, the most common, and for numbers the range."""
    present = [value for value in values if not empty(value)]
    kinds = {kind_of_value(value) for value in present}
    kind = "empty" if not kinds else next(iter(kinds)) if len(kinds) == 1 else "mixed"
    counts = Counter(hashable(value) for value in present)
    numbers = [float(value) for value in present if kind == "number"]
    return ColumnProfile(
        name, kind, len(values), len(values) - len(present), len(counts), tuple(counts.most_common(TOP)),
        min(numbers) if numbers else None, statistics.median(numbers) if numbers else None, max(numbers) if numbers else None)

def profile_rows(table: str, rows: Sequence[Mapping[str, Any]], columns: Sequence[str] | None = None, sampled: bool = False) -> TableProfile:
    """Profiles a table from its rows. `columns` is the column names to profile, in order (all the columns of the first row when not given)."""
    names = list(columns) if columns is not None else list(rows[0]) if rows else []
    return TableProfile(table, len(rows), sampled, tuple(profile_column(name, [row.get(name) for row in rows]) for name in names))

def table_columns(spark: Any, table: str) -> list[str]:
    """Returns the column names of a table, in order, even when it has no rows."""
    return list(spark.table(quote_table(table)).columns)

def read_slice(spark: Any, table: str, limit: int | None) -> tuple[list[dict[str, Any]], bool]:
    """Reads the first `limit` rows of a table (all of them when `limit` is None), and says whether the table has more."""
    rows = read_rows(spark, table, limit=None if limit is None else limit + 1)
    sampled = limit is not None and len(rows) > limit
    return (rows[:limit] if sampled else rows), sampled

def profile(spark: Any, table: str, *, columns: Sequence[str] | None = None, limit: int | None = 20000) -> TableProfile:
    """Profiles a silver table from the first `limit` rows (all of them when `limit` is None), for the `columns` asked for or all of them.

    The rows are collected to the notebook, so `limit` keeps a large table affordable; `sampled` in the result says when the table has more rows than were read.
    """
    rows, sampled = read_slice(spark, table, limit)
    return profile_rows(table, rows, columns if columns is not None else table_columns(spark, table), sampled)

def cut(value: Any, width: int) -> Any:
    """Cuts a long text to `width` characters, ending in an ellipsis; any other value is returned as it is."""
    if isinstance(value, str) and len(value) > width:
        return value[:width] + "…"

    return value

def sample_rows(spark: Any, table: str, columns: Sequence[str] | None = None, n: int = 10, where: str | None = None, width: int = SAMPLE_WIDTH) -> list[dict[str, Any]]:
    """Returns a few real rows of a table, for the `columns` asked for (all by default), at most `n` of them (never more than 50), with texts cut to `width` characters.

    `where` is a SQL condition. These are the only raw values that need to enter a conversation, so ask for few rows and only the columns that the profile does not explain.
    """
    rows = read_rows(spark, table, where=where, limit=max(0, min(n, MAX_SAMPLE)))
    names = list(columns) if columns is not None else None
    return [{name: cut(value, width) for name, value in row.items() if names is None or name in names} for row in rows]

def check_key_rows(rows: Sequence[Mapping[str, Any]], keys: Sequence[str], columns: Sequence[str] | None = None) -> KeyCheck:
    """Checks a proposed key against rows: groups the rows by the key columns and finds the other columns that have one value in each group, in most groups, or vary.

    Raises ValueError for a key column that is not a column of the rows, or for no key columns.
    """
    names = list(columns) if columns is not None else list(rows[0]) if rows else list(keys)
    if not keys:
        raise ValueError("a key needs at least one column")

    absent = [key for key in keys if key not in names]
    if absent:
        raise ValueError(f"{', '.join(absent)} is not a column of the table; its columns are {', '.join(names)}")

    groups: dict[tuple[Hashable, ...], list[Mapping[str, Any]]] = {}
    empty_rows = 0
    for row in rows:
        values = tuple(row.get(key) for key in keys)
        if any(empty(value) for value in values):
            empty_rows += 1
            continue

        groups.setdefault(tuple(hashable(value) for value in values), []).append(row)

    constant: list[str] = []
    almost: list[tuple[str, float]] = []
    conflicts: list[KeyConflict] = []
    varying: list[str] = []
    for column in (name for name in names if name not in keys and groups):
        found = [(key, tuple(dict.fromkeys(hashable(member.get(column)) for member in members))) for key, members in groups.items()]
        disagreeing = [(key, values) for key, values in found if len(values) > 1]
        share = (len(groups) - len(disagreeing)) / len(groups) if groups else 0.0
        if not disagreeing:
            constant.append(column)
        elif share >= ALMOST:
            almost.append((column, round(share, 3)))
            conflicts.append(KeyConflict(column, len(disagreeing), tuple((key, values[:EXAMPLES]) for key, values in disagreeing[:EXAMPLES])))
        else:
            varying.append(column)

    return KeyCheck(tuple(keys), len(rows), empty_rows, len(groups), tuple(constant), tuple(almost), tuple(conflicts), tuple(varying))

def check_key(spark: Any, table: str, keys: Sequence[str], *, limit: int | None = 20000) -> KeyCheck:
    """Checks a proposed key against the first `limit` rows of a silver table (all of them when `limit` is None): see `check_key_rows` and `KeyCheck`."""
    rows, _ = read_slice(spark, table, limit)
    return check_key_rows(rows, keys, table_columns(spark, table))
