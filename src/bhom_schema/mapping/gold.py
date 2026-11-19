"""Writes the gold tables: one BHoM table for each entity of a mapping, from the rows of the silver table, when the mapping is valid.

It uses the helpers of `bhom_schema.tables` for everything about the tables (the statement that creates one, the Delta constraints on the enum columns, the rows), and adds the one thing a mapping
needs: a column with the id of the parent row (`Building_id`), which links a Storey or a Beam to its Building.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bhom_schema.mapping.apply import apply_mapping, gold_table, parent_column
from bhom_schema.mapping.files import load_mapping
from bhom_schema.mapping.model import TableMapping
from bhom_schema.mapping.profile import table_columns
from bhom_schema.mapping.validate import MappingReport, report_for
from bhom_schema.tables import enum_constraints_sql
from bhom_schema.tables.columns import KEY_COLUMN, quote
from bhom_schema.tables.rows import RowPlan, ddl_schema
from bhom_schema.tables.spark import create_table, fetch_by_ids, read_rows
from bhom_schema.tables.sql import quote_table

class GoldRefused(ValueError):
    """The mapping is not valid for the table, so no gold table was written. `report` says why."""

    def __init__(self, report: MappingReport) -> None:
        """Keeps the report and writes it as the message."""
        self.report = report
        super().__init__("nothing was written to gold, because the mapping is not valid for the table:\n" + report.summary())

@dataclass(frozen=True)
class GoldResult:
    """What `write_gold` did: the gold table of each entity, how many rows were written to it, and how many were already there (left as they are)."""

    tables: Mapping[str, str]
    written: Mapping[str, int]
    existing: Mapping[str, int]

    def text(self) -> str:
        """Writes the result for reading: one line for each gold table."""
        return "\n".join(f"{name}: {self.tables[name]}, {self.written[name]} rows written, {self.existing[name]} already there" for name in self.tables)

def table_exists(spark: Any, table: str) -> bool:
    """Tells whether a table exists, through the catalog of the session."""
    return bool(spark.catalog.tableExists(table))

def write_gold(spark: Any, table: str, mapping: TableMapping | None = None, *, replace: bool = False) -> GoldResult:
    """Writes the gold tables of a silver table, one for each entity of its mapping, parents first; returns what was written. Raises GoldRefused, writing nothing, when the mapping is not valid.

    The mapping is the one given, or the file found for the table. All the rows of the silver table are read and validated first, whatever `validate_mapping` was run on. A gold row has a
    deterministic id, made from its entity and key values, so writing again does not add the same row twice: with `replace=False` (the default) a missing table is created and only the rows that are
    not there yet are added, and rows that are there are left as they are. With `replace=True` each gold table is made again, which drops what it held.
    """
    mapping = mapping if mapping is not None else load_mapping(table)
    rows = read_rows(spark, table)
    applied = apply_mapping(rows, mapping)
    report = report_for(applied, table_columns(spark, table), table)
    if not report.ok:
        raise GoldRefused(report)

    names: dict[str, str] = {}
    written: dict[str, int] = {}
    existing: dict[str, int] = {}
    for item in applied.entities:
        entity = item.entity
        name = gold_table(mapping, entity)
        known = not replace and table_exists(spark, name)
        create_table(spark, entity.model, name, fields=entity.fields, key=KEY_COLUMN, replace=replace)
        link = parent_column(entity)
        if not known:
            if link:
                spark.sql(f"ALTER TABLE {quote_table(name)} ADD COLUMNS ({quote(link)} STRING)")

            for statement in enum_constraints_sql(entity.model, name, entity.fields, KEY_COLUMN):
                spark.sql(statement)

        plan = RowPlan(entity.model, entity.fields, KEY_COLUMN)
        present: set[str] = set()
        if known and plan.key_column:
            present = {str(row[plan.key_column]) for row in fetch_by_ids(spark, name, [object_.id for object_ in item.objects], key=plan.key_column)}

        data: list[dict[str, Any]] = []
        for object_ in item.objects:
            if object_.id in present or object_.instance is None:
                continue

            row = plan.to_row(object_.instance, {KEY_COLUMN: object_.id} if plan.adds_key else None)
            if link:
                row[link] = object_.parent_id

            data.append(row)

        if data:
            schema = ddl_schema(entity.model, fields=entity.fields, key=KEY_COLUMN) + (f", {quote(link)} STRING" if link else "")
            spark.createDataFrame(data, schema=schema).write.mode("append").saveAsTable(quote_table(name))

        names[entity.name], written[entity.name], existing[entity.name] = name, len(data), len(present)

    return GoldResult(names, written, existing)
