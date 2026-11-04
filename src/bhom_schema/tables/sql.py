"""The SQL that creates the table of a class and adds the columns that a newer version of the class has. Each helper returns text; nothing is run."""

from __future__ import annotations

import inspect
from collections.abc import Mapping

from pydantic import BaseModel

from bhom_schema._version import __version__
from bhom_schema.tables.check import TableCheck
from bhom_schema.tables.columns import KEY_COLUMN, ColumnInfo, override_types, quote, require_decided
from bhom_schema.tables.decisions import Decision

def quote_table(table: str) -> str:
    """Quotes every part of a table name (`main.default.LineLike` becomes `main`.`default`.`LineLike`); a name that already has backticks is used as it is."""
    if "`" in table:
        return table

    parts = table.split(".")
    if not table or any(not part for part in parts):
        raise ValueError(f"{table!r} is not a table name; write it as catalog.schema.table")

    return ".".join(quote(part) for part in parts)

def literal(text: str) -> str:
    """Writes text as a Spark SQL string literal: single quotes, with backslash, quote and line breaks escaped."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'").replace("\r", "").replace("\n", "\\n") + "'"

def column_definition(column: ColumnInfo, *, nullable: bool) -> str:
    """Writes one column as `name TYPE [NOT NULL] [COMMENT '...']`."""
    parts = [quote(column.name), str(column.type)]
    if not nullable:
        parts.append("NOT NULL")

    if column.comment:
        parts.append(f"COMMENT {literal(column.comment)}")

    return " ".join(parts)

def table_comment(model: type[BaseModel]) -> str | None:
    """Returns the docstring of the class on one line (the C# summary of the type), or None when it has none."""
    summary = inspect.cleandoc(model.__doc__) if model.__doc__ else ""
    return " ".join(summary.split()) or None

def create_table_sql(
        model: type[BaseModel], table: str, *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN,
        types: Mapping[str, str] | None = None, replace: bool = False) -> str:
    """Returns the statement that creates the Delta table of a class, with a comment on each column, a comment on the table, and the BHoM type and package version as properties.

    Fields that have no column of their own follow `fields` (a decision each); one that is not decided raises UnmappedType, listing it. `key` is `_id` (the key of the class: its
    BHoM_Guid, or an added `_id` column), a field name, or None. `types` replaces the column type of a field (`{"Cost": "DECIMAL(18,2)"}`). `replace` writes CREATE OR REPLACE
    TABLE, which drops what the table holds.
    """
    columns = override_types(model, require_decided(model, fields, key), types)
    definitions = ",\n".join("  " + column_definition(column, nullable=column.nullable) for column in columns if column.type is not None)
    clr_name = getattr(model, "__bhom__", {}).get("clr_name", model.__name__)
    lines = [
        f"{'CREATE OR REPLACE TABLE' if replace else 'CREATE TABLE IF NOT EXISTS'} {quote_table(table)} (",
        definitions,
        ")",
        "USING DELTA",
    ]
    comment = table_comment(model)
    if comment:
        lines.append(f"COMMENT {literal(comment)}")

    lines.append(f"TBLPROPERTIES ('bhom.type' = {literal(str(clr_name))}, 'bhom.schema_version' = {literal(__version__)})")
    return "\n".join(lines)

def add_columns_sql(check: TableCheck, table: str) -> str | None:
    """Returns the statement that adds the columns a table lacks, from the `check_table` of that table, or None when nothing is missing.

    The added columns are all nullable, since Delta cannot add a NOT NULL column to a table that has rows; the rows that exist read as the default of each field.
    """
    if not check.missing:
        return None

    definitions = ", ".join(column_definition(column, nullable=True) for column in check.missing)
    return f"ALTER TABLE {quote_table(table)} ADD COLUMNS ({definitions})"
