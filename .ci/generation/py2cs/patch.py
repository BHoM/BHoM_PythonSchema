"""Member-level changes to an existing C# file: the change list sent to the Roslyn patcher, and the call to it.

Only the members that changed in Python are touched. Everything else in the file (comments, formatting, attributes the
Python does not know about) is kept as it is.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py2cs.compare import clean, normalise_default
from py2cs.csharp import Defaults, Names, ambiguous_names, csharp_string, property_attributes, untranslated_default
from py2cs.model import Manifest, PropertyInfo, TypeInfo

PATCHER = Path(__file__).resolve().parents[1] / "PythonSchemaGeneration.Patcher" / "bin" / "Release" / "net8.0" / "PythonSchemaGeneration.Patcher.dll"
BUILD_HINT = "build it with: dotnet build .ci/generation/PythonSchemaGeneration.sln -c Release"

class PatcherError(Exception):
    pass

@dataclass
class FilePatch:
    """The changes for one existing C# file."""
    path: Path
    type_name: str
    namespace: str
    changes: list[dict[str, Any]] = field(default_factory=lambda: [])
    usings: list[str] = field(default_factory=lambda: [])
    notes: list[str] = field(default_factory=lambda: [])

@dataclass
class PatchResult:
    text: str = ""
    bom: bool = False
    notes: list[str] = field(default_factory=lambda: [])
    error: str | None = None

def default_patcher() -> Path:
    """The built patcher; the PY2CS_PATCHER environment variable points elsewhere."""
    configured = os.environ.get("PY2CS_PATCHER")
    return Path(configured) if configured else PATCHER

def run_patcher(patches: list[FilePatch], patcher: Path | None = None) -> list[PatchResult]:
    """Runs the C# patcher once for every file. The input files are only read."""
    if not patches:
        return []

    dll = patcher or default_patcher()
    if not dll.exists():
        raise PatcherError(f"the C# patcher was not found at {dll}; {BUILD_HINT}")

    with tempfile.TemporaryDirectory() as folder:
        outputs = [Path(folder) / f"{i}.cs" for i in range(len(patches))]
        job = {"files": [{"path": str(p.path), "output": str(o), "type": p.type_name, "namespace": p.namespace, "usings": p.usings, "changes": p.changes}
                         for p, o in zip(patches, outputs)]}
        job_path = Path(folder) / "job.json"
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        completed = subprocess.run(["dotnet", str(dll), str(job_path)], capture_output=True, text=True, encoding="utf-8", timeout=600)
        if completed.returncode != 0:
            raise PatcherError(f"the C# patcher failed: {(completed.stderr or completed.stdout).strip()}")

        results: list[PatchResult] = []
        for output, entry in zip(outputs, json.loads(completed.stdout)["files"]):
            if entry.get("error"):
                results.append(PatchResult(error=str(entry["error"])))
                continue
            data = output.read_bytes()
            results.append(PatchResult(data.decode("utf-8-sig"), data.startswith(b"\xef\xbb\xbf"), list(entry.get("notes") or [])))
        return results

def build_patch(path: Path, before: TypeInfo, after: TypeInfo, head: Manifest) -> FilePatch:
    """The change list turning the C# of `before` into the C# of `after`."""
    ambiguous = ambiguous_names(head)
    names = Names(after.namespace, ambiguous)
    defaults = Defaults(names, head)
    usings: set[str] = set()
    patch = FilePatch(path, after.simple_name, after.namespace)

    def literal(text: str | None) -> str | None:
        if not text:
            return None
        usings.add("System.ComponentModel")
        return csharp_string(text)

    if before.kind != after.kind:
        patch.notes.append(f"the kind changed from {before.kind} to {after.kind}; change the declaration by hand")
    if [(g.name, g.constraints) for g in before.generic_params] != [(g.name, g.constraints) for g in after.generic_params]:
        patch.notes.append("the generic parameters changed; change the declaration by hand")
    if clean(before.description) != clean(after.description):
        patch.changes.append({"kind": "setDescription", "description": literal(after.description)})
    if before.bases != after.bases:
        # Removed bases are only matched by name, so they are rendered without collecting usings
        removed = Names(after.namespace, ambiguous)
        patch.changes.append({"kind": "setBases",
                              "remove": [removed.render(b) for b in before.bases if b not in after.bases],
                              "add": [names.render(b) for b in after.bases if b not in before.bases]})

    old = {p.name: p for p in before.properties}
    new = {p.name: p for p in after.properties}
    anchor: str | None = None
    for prop in after.properties:
        if prop.name not in old:
            patch.changes.append(_added_property(after, prop, anchor, names, defaults, usings, patch.notes))
        else:
            patch.changes += _changed_property(old[prop.name], prop, names, defaults, usings, patch.notes, literal)
            anchor = prop.name
    for name in old:
        if name not in new:
            patch.changes.append({"kind": "removeProperty", "name": name})

    old_members = {m.name: m for m in before.members}
    new_members = {m.name for m in after.members}
    anchor = None
    for member in after.members:
        if member.name not in old_members:
            patch.changes.append({"kind": "addEnumMember", "name": member.name, "value": member.value, "description": literal(member.description), "after": anchor})
        else:
            if old_members[member.name].value != member.value:
                patch.changes.append({"kind": "setEnumValue", "name": member.name, "value": member.value})
            anchor = member.name
    for name in old_members:
        if name not in new_members:
            patch.changes.append({"kind": "removeEnumMember", "name": name})

    patch.usings = sorted(usings | names.usings)
    return patch

def _added_property(info: TypeInfo, prop: PropertyInfo, anchor: str | None, names: Names, defaults: Defaults, usings: set[str], notes: list[str]) -> dict[str, Any]:
    initialiser = defaults.initialiser(prop) if info.kind != "interface" else None
    note = untranslated_default(prop, initialiser) if info.kind != "interface" else None
    if note is not None:
        notes.append(note)
    if not prop.has_default and info.kind != "interface":
        notes.append(f"{prop.name} has no default in Python, so it was added without an initial value")
    return {"kind": "addProperty", "name": prop.name, "type": names.render(prop.clr_type), "initialiser": initialiser,
            "add": property_attributes(prop, usings), "after": anchor}

def _changed_property(a: PropertyInfo, b: PropertyInfo, names: Names, defaults: Defaults, usings: set[str], notes: list[str], literal: Callable[[str | None], str | None]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    if a.clr_type != b.clr_type:
        changes.append({"kind": "setPropertyType", "name": b.name, "type": names.render(b.clr_type)})
    if a.has_default != b.has_default or normalise_default(a.default) != normalise_default(b.default):
        initialiser = defaults.initialiser(b)
        note = untranslated_default(b, initialiser)
        if note is not None:
            notes.append(note)
        else:
            changes.append({"kind": "setPropertyInitialiser", "name": b.name, "initialiser": initialiser})
    if clean(a.description) != clean(b.description):
        changes.append({"kind": "setDescription", "name": b.name, "description": literal(b.description)})

    remove: list[str] = []
    add: list[str] = []
    if a.quantity != b.quantity:
        if a.quantity:
            remove.append(a.quantity[0])
        if b.quantity:
            usings.add("BH.oM.Quantities.Attributes")
            add.append(b.quantity[0])
    if a.display_text != b.display_text:
        if a.display_text:
            remove.append("DisplayText")
        if b.display_text:
            usings.add("BH.oM.Base.Attributes")
            add.append(f"DisplayText({csharp_string(b.display_text)})")
    if a.dynamic != b.dynamic:
        if a.dynamic:
            remove.append("DynamicProperty")
        else:
            usings.add("BH.oM.Base.Attributes")
            add.append("DynamicProperty")
    if remove or add:
        changes.append({"kind": "setAttributes", "name": b.name, "remove": remove, "add": add})
    return changes
