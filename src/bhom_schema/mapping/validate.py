"""The judge of every mapping: applies it to the rows of the silver table and reports everything that is wrong, in one place.

`validate_mapping` is what Genie Code runs after each change to a mapping, and what `write_gold` runs before it writes anything. It reports the columns the mapping does not know (or no
longer finds), the values that do not fit, the objects that the BHoM classes refuse, and the objects that disagree with themselves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from bhom_schema.mapping.apply import Applied, Problem, apply_mapping
from bhom_schema.mapping.files import load_mapping
from bhom_schema.mapping.model import TableMapping
from bhom_schema.mapping.profile import read_slice, table_columns

@dataclass(frozen=True)
class EntityReport:
    """What applying the mapping gave for one entity: how many `objects`, how many are `valid`, how many rows were left out for an empty key column, and the problems."""

    name: str
    objects: int
    valid: int
    empty_key_rows: int
    problems: tuple[Problem, ...]

@dataclass(frozen=True)
class MappingReport:
    """The result of validating a mapping against a silver table.

    `new_columns` are columns of the table that the mapping does not know, and `missing_columns` the ones the mapping uses that the table no longer has; both make the mapping not ok. `sampled`
    says the table was only read in part.
    """

    table: str
    rows: int
    sampled: bool
    new_columns: tuple[str, ...]
    missing_columns: tuple[str, ...]
    entities: tuple[EntityReport, ...]

    @property
    def problems(self) -> list[Problem]:
        """Returns every problem: the columns first, then those of each entity."""
        columns: list[Problem] = []
        if self.new_columns:
            columns.append(Problem("", "columns", f"the table has columns the mapping does not know: {', '.join(self.new_columns)}", len(self.new_columns)))

        if self.missing_columns:
            columns.append(Problem("", "columns", f"the mapping uses columns the table does not have: {', '.join(self.missing_columns)}", len(self.missing_columns)))

        return columns + [problem for entity in self.entities for problem in entity.problems]

    @property
    def ok(self) -> bool:
        """Tells whether the mapping is valid for the table: no problem of any kind."""
        return not self.problems

    def summary(self, examples: int = 3) -> str:
        """Writes the report for reading: the rows, each entity with its counts, each problem with how many objects it affects and an example, and the verdict."""
        lines = [f"{self.table}: {self.rows} rows read" + (" (a sample: the table has more)" if self.sampled else "")]
        for problem in self.problems:
            if problem.kind == "columns":
                lines.append(f"  columns: {problem.message}")

        for entity in self.entities:
            skipped = f", {entity.empty_key_rows} rows without a key left out" if entity.empty_key_rows else ""
            lines.append(f"{entity.name}: {entity.objects} objects, {entity.valid} valid{skipped}")
            for problem in entity.problems[:examples * 3]:
                example = f" (for example {problem.example})" if problem.example else ""
                lines.append(f"  {problem.kind}: {problem.message} [{problem.count} objects]{example}")

        count = len(self.problems)
        lines.append("The mapping is valid for this table." if count == 0 else f"The mapping is not valid: {count} problem{'s' if count != 1 else ''}.")
        return "\n".join(lines)

def report_for(applied: Applied, columns: Sequence[str], table: str, sampled: bool = False) -> MappingReport:
    """Builds the report of a mapping that was applied: the columns the mapping does not know or no longer finds, and what each entity gave."""
    entities = tuple(EntityReport(item.entity.name, len(item.objects), item.valid, item.empty_key_rows, tuple(item.problems)) for item in applied.entities)
    return MappingReport(table, applied.rows, sampled, tuple(applied.mapping.unaccounted(columns)), tuple(applied.mapping.missing(columns)), entities)

def validate_rows(rows: Sequence[Mapping[str, Any]], columns: Sequence[str], mapping: TableMapping, table: str | None = None, sampled: bool = False) -> MappingReport:
    """Validates a mapping against rows and the column names of the silver table: the same as `validate_mapping`, with no Spark."""
    return report_for(apply_mapping(rows, mapping), columns, table or mapping.source, sampled)

def validate_mapping(spark: Any, table: str, mapping: TableMapping | None = None, limit: int | None = None) -> MappingReport:
    """Validates a mapping against a silver table and returns the report: see `MappingReport`.

    The mapping is the one given, or the file found for the table (`find_mapping`). The rows are collected to the notebook: all of them by default, or the first `limit` while iterating, which the
    report says (`sampled`). A mapping valid on a sample can still fail on the rest, so the last check, before `write_gold`, reads all rows.
    """
    mapping = mapping if mapping is not None else load_mapping(table)
    rows, sampled = read_slice(spark, table, limit)
    return validate_rows(rows, table_columns(spark, table), mapping, table, sampled)
