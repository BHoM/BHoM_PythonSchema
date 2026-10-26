from __future__ import annotations

from pathlib import Path

import pytest

from helpers import demo_package, module, package
from py2cs.diff import diff_manifests
from py2cs.model import dump_manifest, load_manifest
from py2cs.reader import read_package


def test_reads_interface_class_and_enum(tmp_path: Path):
    manifest = read_package(demo_package(tmp_path))
    assert sorted(manifest) == ["BH.oM.Demo.IdentityBase", "BH.oM.Demo.Mode", "BH.oM.Demo.ProjectInfo"]

    info = manifest["BH.oM.Demo.ProjectInfo"]
    assert info.kind == "class" and info.bases == ["BH.oM.Demo.IdentityBase"]
    assert (info.namespace, info.assembly, info.repo) == ("BH.oM.Demo", "Demo_oM", "BHoM/Demo_Toolkit")
    assert info.relative_path == "Demo_oM/ProjectInfo.py"
    assert [(p.name, p.clr_type, p.has_default, p.default) for p in info.properties] == [
        ("Reference", "string", True, "''"), ("Name", "string", True, "''")]

    mode = manifest["BH.oM.Demo.Mode"]
    assert [(m.name, m.value, m.description) for m in mode.members] == [("None", "0", None), ("Fast", "1", "Faster.")]


def test_reads_every_annotation_shape(tmp_path: Path):
    pkg = package(tmp_path, {
        "A_oM/Target.py": module("Target", "BH.oM.A.Target", "BH.oM.A", "A_oM", repo="BHoM/A"),
        "A_oM/Kind.py": module("Kind", "BH.oM.A.Kind", "BH.oM.A", "A_oM", repo="BHoM/A", kind="enum", bases="Enum", imports=["from enum import Enum"], body=["One = 1"]),
        "A_oM/Thing_1.py": module(
            "Thing_1", "BH.oM.A.Thing`1", "BH.oM.A", "A_oM", repo="BHoM/A", type_params="[T: Target]",
            marker_extra=["'generic_params': {'T': ['BH.oM.A.Target']}"],
            imports=["from bhom_schema.A_oM.Target import Target", "from bhom_schema.A_oM.Kind import Kind", "from bhom_schema.A_oM.Target import Target as OtherTarget",
                     "from datetime import datetime", "from decimal import Decimal", "from uuid import UUID", "from collections.abc import Callable"],
            body=[
                "Items: list[T] = Field(default_factory=list[T])",
                "Count: Annotated[int, ClrType('long')] = 3",
                "Names: set[str] = Field(default_factory=set)",
                "Lookup: dict[str, float] = Field(default_factory=dict)",
                "Pair: tuple[int, str] | None = None",
                "Maybe: int | None = None",
                "Which: Kind = Kind.One",
                "MaybeKind: Kind | None = None",
                "Own: Thing_1[Target] | None = None",
                "Aliased: OtherTarget | None = None",
                "When: datetime = Field(default_factory=datetime.now)",
                "Cost: Decimal = Decimal('1.5')",
                "Key: UUID = UUID(int=0)",
                "Callback: Annotated[Callable[..., Any] | None, ClrType('System.Func<double, double>')] = None",
                "Span: Annotated[float, Quantity('Length', 'm'), DisplayText('Span')] = Field(default=1.5, description='Distance.')",
                "Matrix: list[list[int]] = Field(default_factory=list)",
            ]),
    })
    info = read_package(pkg)["BH.oM.A.Thing`1"]
    types = {p.name: p.clr_type for p in info.properties}
    assert info.name == "BH.oM.A.Thing<T>"
    assert info.generic_params[0].name == "T" and info.generic_params[0].constraints == ["BH.oM.A.Target"]
    assert types["Items"] == "System.Collections.Generic.List<T>"
    assert types["Count"] == "long"
    assert types["Names"] == "System.Collections.Generic.HashSet<string>"
    assert types["Lookup"] == "System.Collections.Generic.Dictionary<string, double>"
    assert types["Pair"] == "System.Tuple<int, string>"
    assert types["Maybe"] == "int?"
    assert types["Which"] == "BH.oM.A.Kind" and types["MaybeKind"] == "BH.oM.A.Kind?"
    assert types["Own"] == "BH.oM.A.Thing<BH.oM.A.Target>"
    assert types["Aliased"] == "BH.oM.A.Target"
    assert types["When"] == "System.DateTime" and types["Cost"] == "decimal" and types["Key"] == "System.Guid"
    assert types["Callback"] == "System.Func<double, double>"
    assert types["Matrix"] == "System.Collections.Generic.List<System.Collections.Generic.List<int>>"
    span = next(p for p in info.properties if p.name == "Span")
    assert span.quantity == ("Length", "m") and span.display_text == "Span" and span.description == "Distance." and span.default == "1.5"
    items = next(p for p in info.properties if p.name == "Items")
    assert items.default == "<factory> list[T]"


def test_manifest_round_trips_through_json(tmp_path: Path):
    manifest = read_package(demo_package(tmp_path))
    dump_manifest(manifest, tmp_path / "m.json")
    again = load_manifest(tmp_path / "m.json")
    assert again == manifest


def test_unsupported_annotation_is_reported(tmp_path: Path):
    pkg = package(tmp_path, {"A_oM/Bad.py": module("Bad", "BH.oM.A.Bad", "BH.oM.A", "A_oM", body=["Value: int | str = 1"])})
    with pytest.raises(ValueError):
        read_package(pkg)


# ---------------------------------------------------------------- diff

def changed(tmp_path: Path, extra: list[str] | None = None, **edits: str):
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head", extra or [])
    for relative, source in edits.items():
        (head_root / relative.replace("__", "/")).write_text(source, encoding="utf-8", newline="\n")
    return base, read_package(head_root)


def test_diff_of_identical_packages_is_empty(tmp_path: Path):
    base, head = changed(tmp_path)
    assert not diff_manifests(base, head)


def test_diff_property_added(tmp_path: Path):
    base, head = changed(tmp_path, ["ProjectNumber: str = ''"])
    diff = diff_manifests(base, head)
    assert [(c.clr_name, c.kind, c.details) for c in diff.changes] == [("BH.oM.Demo.ProjectInfo", "modified", ["property added: string ProjectNumber"])]


def test_diff_added_removed_and_changed(tmp_path: Path):
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head")
    (head_root / "Demo_oM" / "Mode.py").unlink()
    (head_root / "Demo_oM" / "Fresh.py").write_text(module("Fresh", "BH.oM.Demo.Fresh", "BH.oM.Demo", "Demo_oM", body=["X: float = 0.0"]), encoding="utf-8")
    (head_root / "Demo_oM" / "ProjectInfo.py").write_text(module(
        "ProjectInfo", "BH.oM.Demo.ProjectInfo", "BH.oM.Demo", "Demo_oM", bases="SchemaModel",
        body=["Reference: int = 0", "Extra: str = Field(default='x', description='new')"]), encoding="utf-8")
    diff = diff_manifests(base, read_package(head_root))
    by_name = {c.clr_name: c for c in diff.changes}
    assert by_name["BH.oM.Demo.Fresh"].kind == "added"
    assert by_name["BH.oM.Demo.Mode"].kind == "removed"
    details = by_name["BH.oM.Demo.ProjectInfo"].details
    assert "property removed: string Name" in details
    assert "property added: string Extra" in details
    assert any(d.startswith("property Reference type changed from string to int") for d in details)
    assert any(d.startswith("property Reference default changed") for d in details)
    assert any(d.startswith("bases changed") for d in details)


def test_diff_enum_members(tmp_path: Path):
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head")
    (head_root / "Demo_oM" / "Mode.py").write_text(module(
        "Mode", "BH.oM.Demo.Mode", "BH.oM.Demo", "Demo_oM", kind="enum", bases="Enum", imports=["from enum import Enum"],
        marker_extra=["'renamed_members': {'None_': 'None'}"], body=["None_ = 0", "Fast = 5", "Slow = 2"]), encoding="utf-8")
    details = diff_manifests(base, read_package(head_root)).changes[0].details
    assert details == ["enum member Fast value changed from 1 to 5", "enum member added: Slow = 2"]
