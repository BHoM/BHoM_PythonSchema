from __future__ import annotations

from pathlib import Path

from helpers import demo_package, module
from py2cs.__main__ import main


def run_notes(tmp_path: Path, extra_fields: list[str], remove_mode: bool = False, first: bool = False) -> str:
    """Runs the notes command on a demo package changed against another and returns the release notes text.

    The tests of the release notes use it.
    """
    base = demo_package(tmp_path / "base")
    head = demo_package(tmp_path / "head", extra_fields)
    if remove_mode:
        (head / "Demo_oM" / "Mode.py").unlink()
        (head / "Demo_oM" / "Fresh.py").write_text(module("Fresh", "BH.oM.Demo.Fresh", "BH.oM.Demo", "Demo_oM", body=["X: float = 0.0"]), encoding="utf-8")

    out = tmp_path / "notes.md"
    arguments = ["notes", "--head-root", str(head), "--version", "10.1.0", "--out", str(out)]
    if not first:
        arguments += ["--base-root", str(base), "--previous", "v10.0.0"]

    assert main(arguments) == 0
    return out.read_text(encoding="utf-8")


def test_notes_with_no_change_say_none_are_breaking(tmp_path: Path):
    """Checks that notes for an unchanged schema name the version and the previous release and say there are no breaking changes.

    Protects the Breaking changes section from being left out when nothing breaks.
    """
    notes = run_notes(tmp_path, [])
    assert notes.startswith("# BHoM schema 10.1.0")
    assert "since v10.0.0" in notes
    assert "## Breaking changes\n\nNone." in notes
    assert "## Added classes" not in notes


def test_notes_list_added_removed_and_breaking_changes(tmp_path: Path):
    """Checks that notes list a removed class as breaking, an added class under Added classes, and an added property under Changed classes.

    Protects what a Python user reads before upgrading.
    """
    notes = run_notes(tmp_path, ["ProjectNumber: str = ''"], remove_mode=True)
    breaking = notes.split("## Breaking changes")[1].split("## ")[0]
    assert "`BH.oM.Demo.Mode`: type removed" in breaking
    assert "## Added classes\n\n- `BH.oM.Demo.Fresh`" in notes
    assert "## Removed classes\n\n- `BH.oM.Demo.Mode`" in notes
    assert "  - property added: string ProjectNumber" in notes


def test_notes_for_a_first_release_list_every_class_as_added(tmp_path: Path):
    """Checks that notes without a previous release say it is the first release and list every class as added.

    Protects the first release, which has nothing to compare with.
    """
    notes = run_notes(tmp_path, [], first=True)
    assert "(the first release)" in notes
    assert "- `BH.oM.Demo.ProjectInfo`" in notes.split("## Added classes")[1]
