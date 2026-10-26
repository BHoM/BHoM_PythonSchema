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


@dataclass
class Diff:
    changes: list[TypeChange] = field(default_factory=lambda: [])

    def __bool__(self) -> bool:
        return bool(self.changes)

    def of_kind(self, kind: str) -> list[TypeChange]:
        return [c for c in self.changes if c.kind == kind]

    def to_json(self) -> dict[str, Any]:
        return {"changes": [{"clrName": c.clr_name, "kind": c.kind, "details": c.details} for c in self.changes]}

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Diff":
        return Diff([TypeChange(c["clrName"], c["kind"], list(c["details"])) for c in data["changes"]])


def diff_manifests(base: Manifest, head: Manifest) -> Diff:
    changes: list[TypeChange] = []
    for key in sorted(set(base) | set(head)):
        before, after = base.get(key), head.get(key)
        if before is None:
            changes.append(TypeChange(key, "added", ["new type"]))
        elif after is None:
            changes.append(TypeChange(key, "removed", ["type removed"]))
        else:
            details = type_details(before, after)
            if details:
                changes.append(TypeChange(key, "modified", details))
    return Diff(changes)


def describe(p: PropertyInfo) -> str:
    return f"{p.clr_type} {p.name}"


def type_details(before: TypeInfo, after: TypeInfo) -> list[str]:
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
