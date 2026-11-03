"""The helpers that talk to Spark: make the table of a class, write objects into it, and read rows or objects back.

They take the SparkSession the notebook already has (`spark`) and import nothing from pyspark, so the package needs no Spark to be installed; everything they send is the SQL and
the rows that the other modules of `bhom_schema.tables` build. Each call works on one table; the user links tables by passing the ids, as in the example of the guide.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal, overload

from pydantic import BaseModel

from bhom_schema.tables.columns import KEY_COLUMN, quote
from bhom_schema.tables.decisions import Decision
from bhom_schema.tables.rows import RowPlan, ddl_schema, rows_to_objects
from bhom_schema.tables.sql import create_table_sql, literal, quote_table

def create_table(
        spark: Any, model: type[BaseModel], table: str, *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN,
        types: Mapping[str, str] | None = None, replace: bool = False) -> str:
    """Runs `create_table_sql` for a class and returns the statement it ran, so the notebook can print it; the arguments are those of `create_table_sql`."""
    sql = create_table_sql(model, table, fields=fields, key=key, types=types, replace=replace)
    spark.sql(sql)
    return sql

def write_objects(
        spark: Any, objects: Sequence[BaseModel], table: str, *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN,
        ids: Sequence[Mapping[str, str | None]] | None = None) -> list[str]:
    """Appends objects of one class to the table of that class, and returns the key of each written row, in the order of the objects.

    `fields` and `key` are the ones the table was made with. `ids` has one `to_row` ids dict per object, in the same order: the `_id` of the row and the id of the row of each Ref
    field, which the user got from writing the other table first. The objects are validated already (they are pydantic objects), and a value that the column cannot hold raises
    before anything is written. A table with no key returns an empty list.
    """
    items = list(objects)
    if not items:
        return []

    model = type(items[0])
    others = sorted({type(item).__name__ for item in items if type(item) is not model})
    if others:
        raise TypeError(f"write_objects writes one class at a time: {model.__name__} and {', '.join(others)}")

    if ids is not None and len(ids) != len(items):
        raise ValueError(f"ids has {len(ids)} entries for {len(items)} objects; it needs one per object, in the same order")

    plan = RowPlan(model, fields, key)
    rows = [plan.to_row(item, ids[index] if ids is not None else None) for index, item in enumerate(items)]
    frame = spark.createDataFrame(rows, schema=ddl_schema(model, fields=fields, key=key))
    frame.write.mode("append").saveAsTable(quote_table(table))
    return [str(row[plan.key_column]) for row in rows] if plan.key_column else []

def read_rows(spark: Any, table: str, *, where: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Reads the rows of a table as dicts, before any of them becomes an object; `where` is a SQL condition, `limit` the number of rows to take.

    The rows are collected to the notebook, so take a slice of a large table, not all of it.
    """
    frame = spark.table(quote_table(table))
    if where:
        frame = frame.where(where)

    if limit is not None:
        frame = frame.limit(limit)

    return [row.asDict(recursive=True) for row in frame.collect()]

@overload
def read_objects[M: BaseModel](
        spark: Any, model: type[M], table: str, *, fields: Mapping[str, Decision] | None = ..., key: str | None = ..., held: Mapping[str, Mapping[str, Any]] | None = ...,
        keyed: Literal[False] = ..., where: str | None = ..., limit: int | None = ...) -> list[M]:
    """Reads the table into a list of objects."""
@overload
def read_objects[M: BaseModel](
        spark: Any, model: type[M], table: str, *, fields: Mapping[str, Decision] | None = ..., key: str | None = ..., held: Mapping[str, Mapping[str, Any]] | None = ...,
        keyed: Literal[True], where: str | None = ..., limit: int | None = ...) -> dict[str, M]:
    """Reads the table into a dict of objects by key."""
def read_objects[M: BaseModel](
        spark: Any, model: type[M], table: str, *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN, held: Mapping[str, Mapping[str, Any]] | None = None,
        keyed: bool = False, where: str | None = None, limit: int | None = None) -> Any:
    """Reads a table into objects of its class: `read_rows`, then `rows_to_objects`; `fields`, `key`, `held` and `keyed` are those of `rows_to_objects`.

    For a table with no Ref fields, or when `held` (the objects of the other tables, by id) is already known. To keep the bad rows instead of raising for the first,
    call `read_rows` and `rows_to_objects(..., errors="collect")` yourself.
    """
    rows = read_rows(spark, table, where=where, limit=limit)
    if keyed:
        return rows_to_objects(model, rows, fields=fields, key=key, held=held, keyed=True)

    return rows_to_objects(model, rows, fields=fields, key=key, held=held)

def fetch_by_ids(spark: Any, table: str, ids: Iterable[str | None], *, key: str = KEY_COLUMN, batch: int = 5000) -> list[dict[str, Any]]:
    """Reads the rows of a table whose key column holds one of the ids, in batches of `batch` ids, as dicts.

    It is the step from one table to the next: the ids that a table's Ref columns hold are the `ids`, and the rows are read with `rows_to_objects(..., keyed=True)` to give the
    `held` of the first table. `key` is the key column of that table (`BHoM_Guid` for the table of a BHoMObject). Missing ids are not an error; their rows are just not returned.
    """
    wanted = sorted({str(identifier) for identifier in ids if identifier is not None})
    rows: list[dict[str, Any]] = []
    for start in range(0, len(wanted), batch):
        listed = ", ".join(literal(identifier) for identifier in wanted[start:start + batch])
        rows.extend(read_rows(spark, table, where=f"{quote(key)} IN ({listed})"))

    return rows
