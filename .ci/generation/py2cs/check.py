"""Strict reading of a bhom_schema folder: every problem a hand-written class has, before any C# is drafted."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from py2cs.model import TypeInfo
from py2cs.reader import ReadError, read_package

@dataclass
class CheckResult:
    errors: list[ReadError] = field(default_factory=lambda: [])
    warnings: list[str] = field(default_factory=lambda: [])

def description_warnings(before: TypeInfo | None, after: TypeInfo) -> list[str]:
    """BHoM requires a description on every oM class and property: warn about new ones without one."""
    warnings: list[str] = []
    if before is None and not after.description:
        warnings.append(f"{after.simple_name} has no description; add a docstring (BHoM requires one on every oM class)")
    known = {p.name for p in before.properties} if before is not None else set[str]()
    for prop in after.properties:
        if prop.name not in known and not prop.description:
            warnings.append(f"{after.simple_name}.{prop.name} has no description; add Field(description=...) (BHoM requires one on every oM property)")
    return warnings

def check_package(root: Path, base_root: Path | None = None) -> CheckResult:
    """Reads root strictly. With base_root (the package before the change), new classes and fields are checked for descriptions;
    without it, only classes without a written __bhom__ marker are, since those are hand-written."""
    result = CheckResult()
    head = read_package(root, result.errors)
    base = read_package(base_root, []) if base_root is not None else None
    for clr_name in sorted(head):
        info = head[clr_name]
        warnings = list(info.notes)
        if base is not None:
            before = base.get(clr_name)
            if before is None or before != info:
                warnings += description_warnings(before, info)
        elif info.notes:
            warnings += description_warnings(None, info)
        result.warnings += [f"{info.relative_path}: {w}" for w in warnings]
    return result
