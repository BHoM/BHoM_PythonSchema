"""The enum columns of a table, and the CHECK constraints that make Delta refuse a value that is not a member of the enum. Nothing here runs SQL."""

from __future__ import annotations

import typing
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, Flag
from typing import Any

from pydantic import BaseModel

from bhom_schema.tables.columns import KEY_COLUMN, bare, column_for, quote, require_decided, shape_of
from bhom_schema.tables.decisions import Decision, Struct
from bhom_schema.tables.sql import literal, quote_table

@dataclass(frozen=True)
class EnumColumn:
    """A column that holds the member names of an enum: `path` is the column, or `Column.Field` inside a Struct; `many` is true for a list or set of members."""

    path: str
    enum: type[Enum]
    many: bool

def names_of(enum: type[Enum]) -> list[str]:
    """Returns the member names as BHoM writes them (`None`, not `None_`), including the combined members of a flags enum."""
    members: Mapping[str, Any] = getattr(enum, "bhom_members", lambda: {member.name: member for member in enum})()
    return list(members)

def collect(model: type[BaseModel], decisions: Mapping[str, Decision], prefix: str, stack: tuple[type[BaseModel], ...], found: dict[str, EnumColumn]) -> None:
    """Adds the enum columns of one class to `found`, following a Struct decision into the class it holds."""
    for name, info in model.model_fields.items():
        if prefix and name == "bhom_version":
            continue

        decision = decisions.get(name)
        column = column_for(name, info, decision, name, (*stack, model))
        if column.decision == "struct" and isinstance(decision, Struct):
            held: Any = bare(info.annotation)[0]
            if shape_of(info.annotation) == "class":
                collect(held, decision.fields or {}, f"{prefix}{column.name}.", (*stack, model), found)

            continue

        if column.decision not in ("primitive", "key"):
            continue

        kind, _ = bare(info.annotation, info.metadata)
        many = False
        arguments = typing.get_args(kind)
        if typing.get_origin(kind) in (list, set, frozenset) and len(arguments) == 1:
            kind, _ = bare(arguments[0])
            many = True

        if isinstance(kind, type) and issubclass(kind, Enum):
            path = f"{prefix}{column.name}"
            found[path] = EnumColumn(path, kind, many)

def enum_columns(model: type[BaseModel], fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN) -> dict[str, EnumColumn]:
    """Lists the columns of the table of a class that hold enum members, by column (or `Column.Field` inside a Struct).

    A list of enums counts, with `many` set. An enum inside a list of Structs has no path that a constraint can name, so it is not listed.
    """
    require_decided(model, fields, key)
    found: dict[str, EnumColumn] = {}
    collect(model, dict(fields or {}), "", (), found)
    return found

def valid_names(expression: str, enum: type[Enum], variable: str) -> str:
    """Writes the condition that holds when `expression` is a member name; for flags, when every name in the comma-separated text is one."""
    names = ", ".join(literal(name) for name in names_of(enum))
    if issubclass(enum, Flag):
        return f"size(array_except(transform(split({expression}, ','), {variable} -> trim({variable})), array({names}))) = 0"

    return f"{expression} IN ({names})"

def condition_of(column: EnumColumn) -> str:
    """Writes the CHECK condition of one enum column."""
    expression = ".".join(quote(part) for part in column.path.split("."))
    if column.many:
        return f"forall({expression}, item -> {valid_names('item', column.enum, 'part')})"

    return valid_names(expression, column.enum, "part")

def enum_constraints_sql(model: type[BaseModel], table: str, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN) -> list[str]:
    """Returns one `ALTER TABLE ... ADD CONSTRAINT ... CHECK` statement per enum column, so Delta refuses any write whose value is not a member.

    A NULL passes, since it means the default of the field. Run the statements after the table is created; adding one to a table that already holds a wrong value fails.
    """
    target = quote_table(table)
    prefix = table.replace("`", "").split(".")[-1]
    statements: list[str] = []
    for path, column in enum_columns(model, fields, key).items():
        name = f"{prefix}_{path.replace('.', '_')}_enum"
        statements.append(f"ALTER TABLE {target} ADD CONSTRAINT {quote(name)} CHECK ({condition_of(column)})")

    return statements
