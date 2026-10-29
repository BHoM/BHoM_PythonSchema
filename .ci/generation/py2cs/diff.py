"""What changed between two manifests (the Python at the PR base and at the PR head)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from py2cs.compare import clean, normalise_default
from py2cs.model import Manifest, PropertyInfo, TypeInfo


@dataclass
class TypeChange:
    clr_name: str
    kind: str                       # added | removed | modified
    details: list[str] = field(default_factory=lambda: [])
    # The details that break existing C# code or saved data and may need a versioning upgrade
    breaking: list[str] = field(default_factory=lambda: [])


@dataclass
class Diff:
    changes: list[TypeChange] = field(default_factory=lambda: [])

    def __bool__(self) -> bool:
        """Returns True when there is at least one change.

        Lets the workflow ask whether a pull request changes the schema.
        """
        return bool(self.changes)

    def to_json(self) -> dict[str, Any]:
        """Converts the diff to a JSON-ready dictionary of changes with their details and breaking items.

        The `diff` command writes it so later workflow jobs can read it.
        """
        return {"changes": [{"clrName": c.clr_name, "kind": c.kind, "details": c.details, "breaking": c.breaking} for c in self.changes]}

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Diff":
        """Rebuilds a Diff from the dictionary that `to_json` wrote.

        Lets later steps of the linked-PR workflow read a saved diff.
        """
        return Diff([TypeChange(c["clrName"], c["kind"], list(c["details"]), list(c.get("breaking", []))) for c in data["changes"]])


def diff_manifests(base: Manifest, head: Manifest) -> Diff:
    """Compares the Python manifest at the pull request base with the one at its head and returns a Diff of added, removed and modified types with details and breaking changes.

    The start of the Python to C# flow: `plan`, `report`, `align` and the repos job all work from this result.
    """
    changes: list[TypeChange] = []
    for key in sorted(set(base) | set(head)):
        before, after = base.get(key), head.get(key)
        if before is None:
            changes.append(TypeChange(key, "added", ["new type"]))
        elif after is None:
            changes.append(TypeChange(key, "removed", ["type removed"], ["type removed"]))
        else:
            details = type_details(before, after)
            if details:
                changes.append(TypeChange(key, "modified", details, breaking_changes(before, after)))
    return Diff(changes)


def describe(p: PropertyInfo) -> str:
    """Returns a property as `<C# type> <name>` for use in change messages.

    Used by `type_details` and `breaking_changes`.
    """
    return f"{p.clr_type} {p.name}"


def type_details(before: TypeInfo, after: TypeInfo) -> list[str]:
    """Lists every change between two versions of a type: kind, bases, generics, description, properties added, removed or changed, and enum members.

    Called by `diff_manifests`; the text goes into the pull request description.
    """
    details: list[str] = []
    if before.kind != after.kind:
        details.append(f"kind changed from {before.kind} to {after.kind}")
    if before.bases != after.bases:
        details.append(f"bases changed from [{', '.join(before.bases)}] to [{', '.join(after.bases)}]")
    if [(g.name, g.constraints) for g in before.generic_params] != [(g.name, g.constraints) for g in after.generic_params]:
        details.append("generic parameters changed")
    if clean(before.description) != clean(after.description):
        details.append("description changed")

    old = {p.name: p for p in before.properties}
    new = {p.name: p for p in after.properties}
    for name in new:
        if name not in old:
            details.append(f"property added: {describe(new[name])}")
    for name in old:
        if name not in new:
            details.append(f"property removed: {describe(old[name])}")
    for name in new:
        if name in old:
            a, b = old[name], new[name]
            if a.clr_type != b.clr_type:
                details.append(f"property {name} type changed from {a.clr_type} to {b.clr_type}")
            if a.has_default != b.has_default or normalise_default(a.default) != normalise_default(b.default):
                details.append(f"property {name} default changed from {a.default} to {b.default}")
            if clean(a.description) != clean(b.description):
                details.append(f"property {name} description changed")
            if a.quantity != b.quantity or a.display_text != b.display_text or a.dynamic != b.dynamic:
                details.append(f"property {name} attributes changed")

    old_members = {m.name: m.value for m in before.members}
    new_members = {m.name: m.value for m in after.members}
    for name, value in new_members.items():
        if name not in old_members:
            details.append(f"enum member added: {name} = {value}")
        elif old_members[name] != value:
            details.append(f"enum member {name} value changed from {old_members[name]} to {value}")
    for name in old_members:
        if name not in new_members:
            details.append(f"enum member removed: {name}")
    return details


def breaking_changes(before: TypeInfo, after: TypeInfo) -> list[str]:
    """Lists the changes of a modified type that can break existing C# code or saved data.

    A removed property that has an added property of the same type to take its place is reported as a rename. That is a guess from the types, so a person confirms it; it is breaking either way.
    """
    breaking: list[str] = []
    if before.kind != after.kind:
        breaking.append(f"kind changed from {before.kind} to {after.kind}")
    removed_bases = [b for b in before.bases if b not in after.bases]
    if removed_bases:
        breaking.append(f"base removed: {', '.join(removed_bases)}")

    old = {p.name: p for p in before.properties}
    new = {p.name: p for p in after.properties}
    removed = [p for name, p in old.items() if name not in new]
    added = [p for name, p in new.items() if name not in old]
    for prop in removed:
        same_type_removed = [p for p in removed if p.clr_type == prop.clr_type]
        same_type_added = [p for p in added if p.clr_type == prop.clr_type]
        if len(same_type_removed) == 1 and len(same_type_added) == 1:
            breaking.append(f"property renamed: {prop.name} to {same_type_added[0].name} ({prop.clr_type})")
        else:
            breaking.append(f"property removed: {describe(prop)}")
    for name, prop in new.items():
        if name in old and old[name].clr_type != prop.clr_type:
            breaking.append(f"property {name} type changed from {old[name].clr_type} to {prop.clr_type}")

    old_members = {m.name: m.value for m in before.members}
    new_members = {m.name: m.value for m in after.members}
    for name, value in old_members.items():
        if name not in new_members:
            breaking.append(f"enum member removed: {name}")
        elif new_members[name] != value:
            breaking.append(f"enum member {name} value changed from {value} to {new_members[name]}")
    return breaking
