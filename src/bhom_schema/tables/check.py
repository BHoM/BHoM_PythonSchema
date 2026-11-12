"""Compares an existing table with a class: which columns the class would read that the table lacks, which the class does not know, and which have another type."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import BaseModel

from bhom_schema.tables.columns import KEY_COLUMN, ColumnInfo, UndecidedField, describe, override_types
from bhom_schema.tables.decisions import Decision

def normalized(column_type: str) -> str:
    """Writes a column type so two spellings of it compare equal: lower case, without spaces and backticks (`STRUCT<`X`: DOUBLE>` and `struct<x:double>`)."""
    return "".join(column_type.lower().split()).replace("`", "")

@dataclass(frozen=True)
class TableCheck:
    """What differs between a table and the table a class would have.

    `missing` are the columns of the class that the table lacks (a row is read with the default of the field); `extra` are the table's columns that the class
    does not store (they are ignored when a row is read); `mismatched` are the expected columns whose table type is another, with that type; `undecided_fields`
    are the fields that still need a decision. `ok` is true when the table reads as the class: nothing missing, mismatched or undecided.
    """

    missing: list[ColumnInfo] = field(default_factory=list[ColumnInfo])
    extra: list[str] = field(default_factory=list[str])
    mismatched: list[tuple[ColumnInfo, str]] = field(default_factory=list[tuple[ColumnInfo, str]])
    undecided_fields: list[UndecidedField] = field(default_factory=list[UndecidedField])

    @property
    def ok(self) -> bool:
        """Tells whether the table reads as the class."""
        return not (self.missing or self.mismatched or self.undecided_fields)

    def __str__(self) -> str:
        """Writes the differences, one per line, or says the table matches."""
        lines = [f"missing column {column.name} {column.type}" for column in self.missing]
        lines += [f"column {column.name} is {actual}, the class expects {column.type}" for column, actual in self.mismatched]
        lines += [f"field {entry.path} ({entry.type}) still needs a decision" for entry in self.undecided_fields]
        lines += [f"extra column {name}, which the class does not store" for name in self.extra]
        return "\n".join(lines) if lines else "the table matches the class"

def check_table(
        model: type[BaseModel], columns: Mapping[str, str], *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN,
        types: Mapping[str, str] | None = None) -> TableCheck:
    """Compares the columns of an existing table, as {name: type} from `DESCRIBE TABLE` or `df.dtypes`, with the table the class would have.

    `fields`, `key` and `types` are the ones the table was made with. Names are compared without regard to case, as Delta does, and types as `normalized` writes them.
    It reads no data and raises nothing for an undecided field; it lists it.
    """
    expected = override_types(model, describe(model, fields, key), types)
    actual = {name.lower(): (name, kind) for name, kind in columns.items()}
    result = TableCheck()
    known: set[str] = set()
    for column in expected:
        result.undecided_fields.extend(column.undecided_fields)
        if column.type is None:
            continue

        known.add(column.name.lower())
        found = actual.get(column.name.lower())
        if found is None:
            result.missing.append(column)
        elif normalized(found[1]) != normalized(column.type):
            result.mismatched.append((column, found[1]))

    result.extra.extend(name for lowered, (name, _) in actual.items() if lowered not in known)
    return result
