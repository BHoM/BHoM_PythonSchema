"""Keeping the Python PR and the C# PR in step: breaking changes, and the alignment check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import csharp_tree, demo_package, module, package, require_patcher
from py2cs.__main__ import main
from py2cs.align import align
from py2cs.diff import Diff, breaking_changes, diff_manifests
from py2cs.plan import make_plan
from py2cs.reader import read_package
from py2cs.report import render_report

ENUM = {"kind": "enum", "bases": "Enum", "imports": ["from enum import Enum"]}

def thing(root: Path, body: list[str], **options: object):
    """Builds a package with one Demo_oM class Thing from the given body and marker options and returns its manifest entry.

    The breaking-change tests use it to compare two versions of the same class.
    """
    return read_package(package(root, {"Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM", body=body, **options)}))["BH.oM.Demo.Thing"]  # type: ignore[arg-type]

# ---------------------------------------------------------------- breaking changes

def test_removed_property_is_breaking(tmp_path: Path):
    """Checks that removing a property is reported as a breaking change.

    Protects the breaking-change label and report section that the diff and plan stages produce.
    """
    before, after = thing(tmp_path / "a", ["A: int = 0", "B: str = ''"]), thing(tmp_path / "b", ["A: int = 0"])
    assert breaking_changes(before, after) == ["property removed: string B"]

def test_a_removed_and_an_added_property_of_the_same_type_is_a_rename(tmp_path: Path):
    """Checks that one removed and one added property of the same type are reported as a rename, not as a removal.

    Keeps the breaking-change notes of the linked C# PR accurate.
    """
    before, after = thing(tmp_path / "a", ["Old: str = ''", "A: int = 0"]), thing(tmp_path / "b", ["A: int = 0", "New: str = ''"])
    assert breaking_changes(before, after) == ["property renamed: Old to New (string)"]

def test_several_candidates_are_not_guessed_as_renames(tmp_path: Path):
    """Checks that when several removed and added properties share a type, the removals are reported and no rename is guessed.

    Protects the breaking-change list from wrong rename claims.
    """
    before, after = thing(tmp_path / "a", ["X: str = ''", "Y: str = ''"]), thing(tmp_path / "b", ["P: str = ''", "Q: str = ''"])
    assert breaking_changes(before, after) == ["property removed: string X", "property removed: string Y"]

def test_type_change_is_breaking_but_an_added_property_or_new_default_is_not(tmp_path: Path):
    """Checks that changing a property type is breaking while adding a property or changing a default is not.

    Protects the line between breaking and safe changes in breaking_changes.
    """
    before = thing(tmp_path / "a", ["A: int = 0", "B: str = ''"])
    assert breaking_changes(before, thing(tmp_path / "b", ["A: float = 0.0", "B: str = ''"])) == ["property A type changed from int to double"]
    assert breaking_changes(before, thing(tmp_path / "c", ["A: int = 5", "B: str = 'x'", "C: int = 0"])) == []

def test_enum_member_removed_or_renumbered_is_breaking_but_added_is_not(tmp_path: Path):
    """Checks that removing or renumbering an enum member is breaking while adding one is not.

    Protects the breaking-change rules for enums, whose values may be stored by users.
    """
    before = thing(tmp_path / "a", ["A = 1", "B = 2", "C = 3"], **ENUM)
    after = thing(tmp_path / "b", ["A = 1", "B = 5", "D = 4"], **ENUM)
    assert breaking_changes(before, after) == ["enum member B value changed from 2 to 5", "enum member removed: C"]
    assert breaking_changes(before, thing(tmp_path / "c", ["A = 1", "B = 2", "C = 3", "D = 4"], **ENUM)) == []

def test_removed_base_and_changed_kind_are_breaking(tmp_path: Path):
    """Checks that removing a base type or changing the kind of a class is breaking while adding a base is not.

    Protects the breaking-change rules for inheritance and class kind.
    """
    interface = {"Demo_oM/IdentityBase.py": module("IdentityBase", "BH.oM.Demo.IdentityBase", "BH.oM.Demo", "Demo_oM", kind="interface", bases="ABC", imports=["from abc import ABC"])}
    imports = ["from bhom_schema.Demo_oM.IdentityBase import IdentityBase"]

    def version(name: str, **options: object):
        """Builds a package with the IdentityBase interface and a Thing class made with the given options, and returns the manifest entry of Thing.

        Used by the removed-base and changed-kind test to make its versions of Thing.
        """
        files = {**interface, "Demo_oM/Thing.py": module("Thing", "BH.oM.Demo.Thing", "BH.oM.Demo", "Demo_oM", **options)}  # type: ignore[arg-type]
        return read_package(package(tmp_path / name, files))["BH.oM.Demo.Thing"]

    with_base = version("a", bases="SchemaModel, IdentityBase", imports=imports)
    without = version("b", bases="SchemaModel")
    assert breaking_changes(with_base, without) == ["base removed: BH.oM.Demo.IdentityBase"]
    assert breaking_changes(without, with_base) == []
    assert breaking_changes(without, version("c", kind="abstract", bases="SchemaModel, ABC", imports=["from abc import ABC"])) == ["kind changed from class to abstract"]

def test_diff_carries_breaking_changes_and_keeps_them_through_json(tmp_path: Path):
    """Checks that diff_manifests records breaking changes on each change (removed type, renamed property) and that the diff is unchanged after a JSON round trip.

    Protects the diff file that passes between the jobs of the workflows.
    """
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head")
    (head_root / "Demo_oM" / "Mode.py").unlink()
    (head_root / "Demo_oM" / "ProjectInfo.py").write_text(module(
        "ProjectInfo", "BH.oM.Demo.ProjectInfo", "BH.oM.Demo", "Demo_oM", bases="SchemaModel, IdentityBase",
        imports=["from bhom_schema.Demo_oM.IdentityBase import IdentityBase"], body=["Reference: str = ''", "Title: str = ''"]), encoding="utf-8")
    diff = diff_manifests(base, read_package(head_root))
    by_name = {c.clr_name: c for c in diff.changes}
    assert by_name["BH.oM.Demo.Mode"].breaking == ["type removed"]
    assert by_name["BH.oM.Demo.ProjectInfo"].breaking == ["property renamed: Name to Title (string)"]
    assert Diff.from_json(json.loads(json.dumps(diff.to_json()))) == diff

def test_plan_labels_and_reports_breaking_changes(tmp_path: Path):
    """Checks that make_plan gives the plan the breaking-change label when a type is removed and that the report has a Breaking changes section that names Versioning_Toolkit.

    Protects the label and text of the linked C# PR.
    """
    clones = tmp_path / "clones"
    repo = csharp_tree(clones)
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head")
    (head_root / "Demo_oM" / "Mode.py").unlink()
    head = read_package(head_root)
    plan = make_plan(diff_manifests(base, head), head, base, lambda r: repo, {"BHoM/Demo_Toolkit": ["Demo_oM"]})
    assert plan.labels() == ["breaking-change"]
    assert json.loads(json.dumps(plan.summary()))["labels"] == ["breaking-change"]
    report = render_report(plan)
    assert "## Breaking changes" in report and "Versioning_Toolkit" in report and "- `BH.oM.Demo.Mode`: type removed" in report

def test_plan_for_a_modified_type_lists_its_breaking_changes(tmp_path: Path):
    """Checks that a planned patch of a modified class carries its breaking changes into the plan file entry, the label and the report text.

    Protects the review text of the linked C# PR for changes to existing files.
    """
    require_patcher()
    clones = tmp_path / "clones"
    repo = csharp_tree(clones)
    base = read_package(demo_package(tmp_path / "base", ["Count: int = 0"]))
    head = read_package(demo_package(tmp_path / "head", ["Count: float = 0.0"]))
    plan = make_plan(diff_manifests(base, head), head, base, lambda r: repo, {"BHoM/Demo_Toolkit": ["Demo_oM"]})
    assert plan.errors == []
    assert plan.files[0].breaking == ["property Count type changed from int to double"]
    assert plan.labels() == ["breaking-change"]
    assert "Breaking changes:\n- property Count type changed from int to double" in render_report(plan)

def test_plan_without_breaking_changes_has_no_label(tmp_path: Path):
    """Checks that a plan with only a safe change has no labels and no Breaking changes section in the report.

    Protects the linked C# PR from false breaking-change labels.
    """
    require_patcher()
    clones = tmp_path / "clones"
    repo = csharp_tree(clones)
    base = read_package(demo_package(tmp_path / "base"))
    head = read_package(demo_package(tmp_path / "head", ["ProjectNumber: str = ''"]))
    plan = make_plan(diff_manifests(base, head), head, base, lambda r: repo, {"BHoM/Demo_Toolkit": ["Demo_oM"]})
    assert plan.labels() == [] and "## Breaking changes" not in render_report(plan)

# ---------------------------------------------------------------- the alignment check

def versions(tmp_path: Path, merged_extra: list[str] | None = None):
    """Builds the three manifests that align compares: the base, a head that adds ProjectNumber, and the package generated from the merged C# (with merged_extra fields, or none when None).

    Used by the align tests.
    """
    base = read_package(demo_package(tmp_path / "base"))
    head = read_package(demo_package(tmp_path / "head", ["ProjectNumber: str = ''"]))
    generated = read_package(demo_package(tmp_path / "generated", merged_extra if merged_extra is not None else []))
    return base, head, generated

def test_same_python_passes(tmp_path: Path):
    """Checks that align passes and lists the checked class when the PR's Python equals what the generator wrote from the merged C#.

    Protects the align step of the PR checks from false alarms.
    """
    base, head, generated = versions(tmp_path, ["ProjectNumber: str = ''"])
    result = align(base, head, generated)
    assert result.ok and result.checked == ["BH.oM.Demo.ProjectInfo"]

def test_a_different_default_fails(tmp_path: Path):
    """Checks that align reports a property whose default differs between the merged C# and the PR's Python.

    Protects the align step, which makes the Python match the C#, the source of truth.
    """
    base, head, generated = versions(tmp_path, ["ProjectNumber: str = 'n/a'"])
    assert align(base, head, generated).problems == ["BH.oM.Demo.ProjectInfo.ProjectNumber: default differs: \"'n/a'\" != \"''\""]

def test_a_property_missing_in_the_csharp_fails(tmp_path: Path):
    """Checks that align reports a class whose property list differs because the C# does not have the PR's new property.

    Protects the align step by blocking a Python PR until the C# change is merged.
    """
    base, head, generated = versions(tmp_path)
    problems = align(base, head, generated).problems
    assert len(problems) == 1 and problems[0].startswith("BH.oM.Demo.ProjectInfo: property names differs")

def test_a_class_not_yet_in_the_csharp_or_not_yet_removed_fails(tmp_path: Path):
    """Checks that align reports a new Python class missing from the C# and a removed Python class that the C# still declares.

    Protects the align step by tying the Python PR to the merge of the linked C# PR.
    """
    base = read_package(demo_package(tmp_path / "base"))
    head_root = demo_package(tmp_path / "head")
    (head_root / "Demo_oM" / "Mode.py").unlink()
    (head_root / "Demo_oM" / "Fresh.py").write_text(module("Fresh", "BH.oM.Demo.Fresh", "BH.oM.Demo", "Demo_oM", body=["X: float = 0.0"]), encoding="utf-8")
    generated = read_package(demo_package(tmp_path / "generated"))
    assert align(base, read_package(head_root), generated).problems == [
        "BH.oM.Demo.Fresh: not found in the C#; merge and build the linked C# pull request first",
        "BH.oM.Demo.Mode: removed in the Python, but the C# still declares it",
    ]

def test_command_line_align_with_a_generated_package(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that py2cs align exits 0 and prints the compared count when the generated package matches the PR, and exits 1 and prints the difference when it does not.

    Protects the align command that the PR checks workflow runs.
    """
    demo_package(tmp_path / "base")
    demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    demo_package(tmp_path / "same", ["ProjectNumber: str = ''"])
    demo_package(tmp_path / "other")
    arguments = ["align", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(tmp_path / "head" / "bhom_schema")]

    assert main([*arguments, "--generated-root", str(tmp_path / "same" / "bhom_schema")]) == 0
    assert "1 classes compared, 0 differences" in capsys.readouterr().out

    assert main([*arguments, "--generated-root", str(tmp_path / "other" / "bhom_schema")]) == 1
    out = capsys.readouterr().out
    assert "difference: BH.oM.Demo.ProjectInfo: property names differs" in out and "first value: the C#, second: this PR" in out

def test_nothing_to_compare_passes_without_running_the_generator(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that py2cs align exits 0 and reports nothing to compare, without needing the generator, when the PR changes no classes.

    Keeps PRs that do not touch classes from paying for a generator run.
    """
    demo_package(tmp_path / "base")
    demo_package(tmp_path / "head")
    status = main(["align", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(tmp_path / "head" / "bhom_schema"),
                   "--assemblies", str(tmp_path / "does-not-exist")])
    assert status == 0 and "nothing to compare" in capsys.readouterr().out

def test_missing_generator_is_a_clear_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that py2cs align exits 2 with a clear message when the generator program is not found.

    Protects the PR checks from a silent pass when the generator is not built.
    """
    demo_package(tmp_path / "base")
    demo_package(tmp_path / "head", ["ProjectNumber: str = ''"])
    (tmp_path / "dlls").mkdir()
    status = main(["align", "--base-root", str(tmp_path / "base" / "bhom_schema"), "--head-root", str(tmp_path / "head" / "bhom_schema"),
                   "--assemblies", str(tmp_path / "dlls"), "--generator", str(tmp_path / "nowhere.dll")])
    assert status == 2 and "the generator was not found" in capsys.readouterr().err
