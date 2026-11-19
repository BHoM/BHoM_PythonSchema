"""The short answer to "is this silver table aligned with BHoM?": is there a mapping, is it valid, and does it still cover the columns of the table.

This is what Genie Code runs first when an engineer asks for a check. It looks at the columns only; checking the rows against the BHoM classes is `validate_mapping`.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bhom_schema.mapping.files import find_mapping, load_mapping
from bhom_schema.mapping.model import MappingError
from bhom_schema.mapping.profile import table_columns

@dataclass(frozen=True)
class Alignment:
    """Whether a silver table is aligned with BHoM, as far as its columns can tell.

    `status` is `no-mapping` (no file was found), `invalid` (the file breaks a rule: `problems`), `out-of-date` (the table has `new_columns` the mapping does not know, or the mapping uses
    `missing_columns` that the table no longer has) or `aligned`.
    """

    table: str
    status: str
    mapping_path: Path | None = None
    new_columns: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()

    @property
    def aligned(self) -> bool:
        """Tells whether the table is aligned."""
        return self.status == "aligned"

    def summary(self) -> str:
        """Writes the answer in a few lines: the status, and what is missing or wrong. Genie Code reads it out to the engineer."""
        if self.status == "no-mapping":
            return f"{self.table} has no mapping yet, so it is not BHoM-aligned."

        if self.status == "invalid":
            return f"The mapping {self.mapping_path} breaks its rules:\n" + "\n".join(f"  - {problem}" for problem in self.problems)

        if self.status == "out-of-date":
            lines = [f"The mapping {self.mapping_path} no longer matches {self.table}:"]
            if self.new_columns:
                lines.append(f"  new columns the mapping does not know: {', '.join(self.new_columns)}")

            if self.missing_columns:
                lines.append(f"  columns the mapping uses that the table no longer has: {', '.join(self.missing_columns)}")

            return "\n".join(lines)

        return f"{self.table} is aligned: the mapping {self.mapping_path} covers every column."

def alignment(spark: Any, table: str, *, start: str | os.PathLike[str] | None = None, columns: Iterable[str] | None = None) -> Alignment:
    """Checks a silver table against its mapping, looked for from `start` (a notebook's own folder by default): no mapping, a mapping that breaks a rule, a mapping that no longer
    matches the columns of the table, or a mapping that does.

    `columns` are the table's columns when they are already known; otherwise they are read from the table, which needs no rows.
    """
    names = list(columns) if columns is not None else table_columns(spark, table)
    path = find_mapping(table, start)
    if path is None:
        return Alignment(table, "no-mapping")

    try:
        mapping = load_mapping(path)
    except MappingError as error:
        return Alignment(table, "invalid", path, problems=error.problems)

    new, missing = tuple(mapping.unaccounted(names)), tuple(mapping.missing(names))
    if new or missing:
        return Alignment(table, "out-of-date", path, new, missing)

    return Alignment(table, "aligned", path)
