"""From a diff to the C# files to propose. Reads the C# clones, never writes into them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py2cs.check import description_warnings
from py2cs.csharp import emit_new
from py2cs.diff import Diff
from py2cs.locate import locate, place
from py2cs.model import Manifest
from py2cs.patch import FilePatch, PatcherError, PatchResult, build_patch, run_patcher
from py2cs.resolve import Listing, ResolveError, resolve_repo

Patcher = Callable[[list[FilePatch]], list[PatchResult]]

@dataclass
class PlannedFile:
    repo: str
    path: str                 # relative to the repository root
    action: str               # new | patch
    clr_name: str
    text: str
    rule: str = ""
    notes: list[str] = field(default_factory=lambda: [])
    changes: list[str] = field(default_factory=lambda: [])
    # The changes that can break existing C# code or saved data, for the "Breaking changes" section of the report
    breaking: list[str] = field(default_factory=lambda: [])
    # The existing file starts with a byte order mark, kept when the file is written
    bom: bool = False

@dataclass
class Plan:
    files: list[PlannedFile] = field(default_factory=lambda: [])
    removed: list[tuple[str, str]] = field(default_factory=lambda: [])    # (repo or "?", clr name)
    errors: list[str] = field(default_factory=lambda: [])
    # New in Python, but the C# already declares them (the C# pull request was merged): nothing to raise, `align` compares them
    existing: list[str] = field(default_factory=lambda: [])

    def repos(self) -> list[str]:
        """Returns the sorted repositories that have a planned file or a removed type with a known repository. `plan` writes one report per repository and `pr` raises one pull request per repository.
        """
        return sorted({f.repo for f in self.files} | {r for r, _ in self.removed if r != "?"})

    def labels(self) -> list[str]:
        """Labels for the C# pull request: breaking-change when any file changes or removes something existing code may use."""
        return ["breaking-change"] if self.removed or any(f.breaking for f in self.files) else []

    def summary(self) -> dict[str, Any]:
        """Returns the plan as a dictionary of files, removed types, labels and errors for plan.json. `pr` reads it later to push the planned files.
        """
        return {
            "files": [{"repo": f.repo, "path": f.path, "action": f.action, "type": f.clr_name, "rule": f.rule, "notes": f.notes, "breaking": f.breaking}
                      for f in self.files],
            "removed": [{"repo": r, "type": t} for r, t in self.removed],
            "labels": self.labels(),
            "errors": self.errors,
        }

def make_plan(diff: Diff, head: Manifest, base: Manifest, clone_for: Callable[[str], Path | None], listing: Listing | None = None,
              patcher: Patcher | None = None, only_repo: str | None = None) -> Plan:
    """Turns a diff of two Python versions into the planned C# files: whole new files for new types, member-level patches (through the Roslyn patcher) for types that already exist.

    It resolves the repository and finds the file in the clone of each class, and records problems instead of raising. Reads the clones, never writes into them. With only_repo, classes of other repositories are left out for the linked-PR job. The `plan` command calls it.
    """
    plan = Plan()
    pending: list[tuple[PlannedFile, FilePatch]] = []
    for change in diff.changes:
        if change.kind == "removed":
            info = base.get(change.clr_name)
            repo = "?"
            if info is not None:
                try:
                    repo = resolve_repo(info, listing).repo
                except ResolveError as e:
                    plan.errors.append(str(e))
            if only_repo is None or repo.lower() == only_repo.lower():
                plan.removed.append((repo, change.clr_name))
            continue

        info = head[change.clr_name]
        try:
            repo = resolve_repo(info, listing).repo
        except ResolveError as e:
            plan.errors.append(str(e))
            continue
        if only_repo is not None and repo.lower() != only_repo.lower():
            continue
        root = clone_for(repo)
        if root is None:
            plan.errors.append(f"{change.clr_name}: no checkout of {repo} is available")
            continue

        notes = list(info.notes) + description_warnings(base.get(change.clr_name), info)
        found = locate(root, info)
        if found.path is not None:
            relative = found.path.relative_to(root).as_posix()
            if change.kind == "added":
                plan.existing.append(f"{change.clr_name}: {relative} in {repo} already declares {info.simple_name}")
                continue
            patch = build_patch(found.path, base[change.clr_name], info, head)
            if found.note:
                notes.append(found.note)
            if not patch.changes:
                plan.errors += [f"{change.clr_name}: {n}" for n in patch.notes or ["nothing to change in C#"]]
                continue
            planned = PlannedFile(repo, relative, "patch", change.clr_name, "", "existing file found by searching for the declaration",
                                  notes + patch.notes, change.details, change.breaking)
            plan.files.append(planned)
            pending.append((planned, patch))
        else:
            placement = place(root, info)
            if change.kind == "modified":
                notes.append("the existing C# declaration was not found, so the type is drafted as a new file")
            text = emit_new(info, head, notes)
            plan.files.append(PlannedFile(repo, placement.path, "new", change.clr_name, text, placement.rule, notes, change.details, change.breaking))

    if pending:
        try:
            results = (patcher or run_patcher)([p for _, p in pending])
        except PatcherError as e:
            plan.errors.append(str(e))
            plan.files = [f for f in plan.files if f.action != "patch"]
            return plan

        for (planned, _), result in zip(pending, results):
            if result.error is not None:
                plan.errors.append(f"{planned.clr_name}: {result.error}")
                plan.files.remove(planned)
                continue
            planned.text, planned.bom = result.text, result.bom
            planned.notes += result.notes
    return plan
