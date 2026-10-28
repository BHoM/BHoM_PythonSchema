"""Language-neutral type manifest, the same JSON shape the C# generator writes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PropertyInfo:
    name: str
    clr_type: str
    py_name: str = ""
    has_default: bool = False
    default: str | None = None
    description: str | None = None
    quantity: tuple[str, str] | None = None
    display_text: str | None = None
    dynamic: bool = False


@dataclass
class MemberInfo:
    name: str
    value: str
    description: str | None = None


@dataclass
class GenericParam:
    name: str
    constraints: list[str] = field(default_factory=lambda: [])


@dataclass
class TypeInfo:
    clr_name: str                 # BH.oM.Base.BHoMGroup`1
    name: str                     # canonical, BH.oM.Base.BHoMGroup<T>
    python_name: str
    relative_path: str            # Assembly/Folders/Name.py
    namespace: str
    assembly: str
    kind: str                     # class | abstract | interface | enum | struct
    repo: str | None = None
    description: str | None = None
    flags: bool = False
    bases: list[str] = field(default_factory=lambda: [])
    generic_params: list[GenericParam] = field(default_factory=lambda: [])
    properties: list[PropertyInfo] = field(default_factory=lambda: [])
    members: list[MemberInfo] = field(default_factory=lambda: [])
    # Reviewer notes from reading the file (for example a worked-out marker); not part of the manifest
    notes: list[str] = field(default_factory=lambda: [], compare=False)

    @property
    def simple_name(self) -> str:
        """C# type name without namespace and generic arity."""
        return self.clr_name.rsplit(".", 1)[-1].split("`")[0]


Manifest = dict[str, TypeInfo]


def from_json(data: dict[str, Any]) -> TypeInfo:
    properties: list[PropertyInfo] = []
    for p in data.get("properties", []):
        quantity = p.get("quantity")
        properties.append(PropertyInfo(
            name=p["name"], clr_type=p["clrType"], py_name=p.get("pyName", p["name"]),
            has_default=p.get("hasDefault", False), default=p.get("default"), description=p.get("description"),
            quantity=(quantity["category"], quantity["unit"]) if quantity else None,
            display_text=p.get("displayText"), dynamic=p.get("dynamic", False)))
    return TypeInfo(
        clr_name=data["clrName"], name=data["name"], python_name=data["pythonName"], relative_path=data["relativePath"],
        namespace=data["namespace"], assembly=data["assembly"], kind=data["kind"], repo=data.get("repo"),
        description=data.get("description"), flags=data.get("flags", False), bases=list(data.get("bases", [])),
        generic_params=[GenericParam(g["name"], list(g["constraints"])) for g in data.get("genericParams", [])],
        properties=properties,
        members=[MemberInfo(m["name"], m["value"], m.get("description")) for m in data.get("members", [])])


def to_json(info: TypeInfo) -> dict[str, Any]:
    data: dict[str, Any] = {
        "clrName": info.clr_name, "name": info.name, "pythonName": info.python_name, "relativePath": info.relative_path,
        "namespace": info.namespace, "assembly": info.assembly, "kind": info.kind, "bases": info.bases,
    }
    if info.repo:
        data["repo"] = info.repo
    if info.description:
        data["description"] = info.description
    if info.flags:
        data["flags"] = True
    if info.generic_params:
        data["genericParams"] = [{"name": g.name, "constraints": g.constraints} for g in info.generic_params]
    props: list[dict[str, Any]] = []
    for p in info.properties:
        entry: dict[str, Any] = {"name": p.name, "clrType": p.clr_type}
        if info.kind != "interface":
            entry["pyName"] = p.py_name
            entry["hasDefault"] = p.has_default
            if p.default is not None:
                entry["default"] = p.default
        if p.description:
            entry["description"] = p.description
        if p.quantity:
            entry["quantity"] = {"category": p.quantity[0], "unit": p.quantity[1]}
        if p.display_text:
            entry["displayText"] = p.display_text
        if p.dynamic:
            entry["dynamic"] = True
        props.append(entry)
    data["properties"] = props
    if info.kind == "enum":
        data["members"] = [{"name": m.name, "value": m.value, **({"description": m.description} if m.description else {})} for m in info.members]
    return data


def load_manifest(path: Path) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {t["clrName"]: from_json(t) for t in data["types"]}


def dump_manifest(manifest: Manifest, path: Path) -> None:
    types = [to_json(manifest[k]) for k in sorted(manifest)]
    path.write_text(json.dumps({"schemaVersion": 1, "types": types}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
