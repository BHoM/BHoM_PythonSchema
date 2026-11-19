"""Checks any DataFrame, Spark or pandas, against a BHoM class, without making objects by hand: for a table that already has the columns of a class (the option of building BHoM tables directly)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from bhom_schema.tables import RowError, rows_to_objects
from bhom_schema.tables.decisions import Decision

EXAMPLES = 5

@dataclass(frozen=True)
class FrameReport:
    """The result of checking a DataFrame against a class: `rows` read, how many became valid objects, and the problem of each bad row (its position, its key and why)."""

    model: str
    rows: int
    valid: int
    problems: tuple[RowError, ...]

    @property
    def ok(self) -> bool:
        """Tells whether every row is valid."""
        return not self.problems

    def text(self) -> str:
        """Writes the report for reading: the counts, and the first few bad rows with the first line of their message."""
        lines = [f"{self.model}: {self.valid} of {self.rows} rows are valid"]
        for problem in self.problems[:EXAMPLES]:
            first = problem.message.splitlines()[:2]
            lines.append(f"  row {problem.index}" + (f" ({problem.key})" if problem.key else "") + ": " + " ".join(part.strip() for part in first))

        if len(self.problems) > EXAMPLES:
            lines.append(f"  and {len(self.problems) - EXAMPLES} more")

        return "\n".join(lines)

def frame_rows(frame: Any, limit: int | None = None) -> list[dict[str, Any]]:
    """Returns the rows of a pandas or Spark DataFrame as dicts, at most `limit` of them: a pandas NaN becomes None, a Spark row becomes a dict."""
    if hasattr(frame, "to_dict"):
        records: list[dict[str, Any]] = frame.head(limit).to_dict("records") if limit is not None else frame.to_dict("records")
        return [{name: (None if isinstance(value, float) and value != value else value) for name, value in record.items()} for record in records]

    shown = frame.limit(limit) if limit is not None else frame
    return [row.asDict(recursive=True) for row in shown.collect()]

def validate_dataframe(frame: Any, model: type[BaseModel], fields: Mapping[str, Decision] | None = None, limit: int | None = None) -> FrameReport:
    """Checks the rows of a DataFrame, whose columns are named like the table of the class, and reports the bad ones; `fields` are the decisions of the class, as for its table.

    A pandas or a Spark DataFrame is accepted. Only the first `limit` rows are read when it is given. It collects the rows to the notebook, like `read_rows`.
    """
    rows = frame_rows(frame, limit)
    objects, problems = rows_to_objects(model, rows, fields=fields, errors="collect")
    return FrameReport(model.__name__, len(rows), len(objects), tuple(problems))
