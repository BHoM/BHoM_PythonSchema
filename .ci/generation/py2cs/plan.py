"""From a diff to the C# files to propose. Reads the C# clones, never writes into them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py2cs.csharp import emit_new, emit_replacement
from py2cs.diff import Diff
from py2cs.locate import locate, place, read
from py2cs.model import Manifest
from py2cs.resolve import Listing, ResolveError, resolve_repo


@dataclass
class PlannedFile:
    repo: str
    path: str                 # relative to the repository root
    action: str               # new | replace
    clr_name: str
    text: str
    rule: str = ""
    notes: list[str] = field(default_factory=lambda: [])
    changes: list[str] = field(default_factory=lambda: [])


@dataclass
class Plan:
    files: list[PlannedFile] = field(default_factory=lambda: [])
    removed: list[tuple[str, str]] = field(default_factory=lambda: [])    # (repo or "?", clr name)
    errors: list[str] = field(default_factory=lambda: [])

    def repos(self) -> list[str]:
        return sorted({f.repo for f in self.files} | {r for r, _ in self.removed if r != "?"})

    def summary(self) -> dict[str, Any]:
        return {
            "files": [{"repo": f.repo, "path": f.path, "action": f.action, "type": f.clr_name, "rule": f.rule, "notes": f.notes} for f in self.files],
            "removed": [{"repo": r, "type": t} for r, t in self.removed],
            "errors": self.errors,
        }


def make_plan(diff: Diff, head: Manifest, base: Manifest, clone_for: Callable[[str], Path | None], listing: Listing | None = None) -> Plan:
    plan = Plan()
    for change in diff.changes:
        if change.kind == "removed":
            info = base.get(change.clr_name)
            repo = "?"
            if info is not None:
                try:
                    repo = resolve_repo(info, listing).repo
                except ResolveError as e:
                    plan.errors.append(str(e))
            plan.removed.append((repo, change.clr_name))
            continue

        info = head[change.clr_name]
        try:
            repo = resolve_repo(info, listing).repo
        except ResolveError as e:
            plan.errors.append(str(e))
            continue
        root = clone_for(repo)
        if root is None:
            plan.errors.append(f"{change.clr_name}: no checkout of {repo} is available")
            continue

        found = locate(root, info)
        if found.path is not None:
            text, notes = emit_replacement(info, head, read(found.path))
            if found.note:
                notes.append(found.note)
            if change.kind == "added":
                notes.append("the type is new in Python but a C# declaration already exists; check this is the same type")
            plan.files.append(PlannedFile(repo, found.path.relative_to(root).as_posix(), "replace", change.clr_name, text,
                                          "existing file found by searching for the declaration", notes, change.details))
        else:
            placement = place(root, info)
            notes = []
            if change.kind == "modified":
                notes.append("the existing C# declaration was not found, so the type is drafted as a new file")
            plan.files.append(PlannedFile(repo, placement.path, "new", change.clr_name, emit_new(info, head), placement.rule, notes, change.details))
    return plan
