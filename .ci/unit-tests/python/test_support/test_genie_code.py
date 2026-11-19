"""The Genie Code package of the repository (databricks/genie-code): publishing the skill and the instructions into a workspace, and the text of the skill against the code it describes.

Publishing runs against a temporary folder that stands in for the workspace. The text tests keep the skill from drifting: the tools it names must exist, the example mapping in its format reference must load, and
the units and keys it lists must be the ones the code knows.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from bhom_schema.mapping import parse_mapping
from bhom_schema.mapping import units as unit_table
from bhom_schema.mapping.model import COLUMN_KEYS, ENTITY_KEYS, TOP_KEYS

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "databricks" / "genie-code"
SKILL = SOURCE / "skills" / "bhom-mapping"

def load_publisher() -> Any:
    """Imports publish.py, a Databricks notebook in source form, as a module: its code runs only when it is the main notebook, so importing defines the functions and nothing else."""
    spec = importlib.util.spec_from_file_location("genie_publish", SOURCE / "publish.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

PUBLISH = load_publisher()

def copy_source(destination: Path) -> Path:
    """Copies the source folder (skills and instructions) to a temporary folder, so a test can change it, and returns the copy."""
    import shutil

    shutil.copytree(SOURCE, destination)
    return destination

# ---------------------------------------------------------------- publishing

def test_a_dry_run_lists_what_it_would_do_and_writes_nothing(tmp_path: Path):
    """Checks that publishing with dry_run writes no file in the workspace and lists the skill and the instructions it would write.

    Protects the admin who wants to see the effect first.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    actions = PUBLISH.publish(SOURCE, workspace, dry_run=True)

    assert list(workspace.iterdir()) == []
    assert actions[0].startswith("would copy skill bhom-mapping to ") and actions[1].startswith("would write the BHoM section of the instructions in ")

def test_publishing_copies_the_skill_and_writes_the_marked_section(tmp_path: Path):
    """Checks that publishing copies the skill folder with all its files and writes the instructions file with the section between the two markers, and that the skill is the one of the source.

    Protects the result an admin gets: `@bhom-mapping` and the instructions in place.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    actions = PUBLISH.publish(SOURCE, workspace, dry_run=False)
    skill = workspace / ".assistant" / "skills" / "bhom-mapping"
    instructions = (workspace / ".assistant_workspace_instructions.md").read_text(encoding="utf-8")

    assert actions[0].startswith("copied skill bhom-mapping") and actions[1].startswith("wrote the BHoM section")
    assert sorted(item.name for item in skill.iterdir()) == ["SKILL.md", "mapping-format.md", "mapping-guidance.md"]
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert instructions.startswith("<!-- bhom-schema: start -->\n## BHoM data") and instructions.endswith("<!-- bhom-schema: end -->\n")

def test_publishing_again_changes_nothing(tmp_path: Path):
    """Checks that a second publish leaves the instructions as they are and says so, and copies the skill again to the same result.

    Protects the admin who runs the notebook twice.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    PUBLISH.publish(SOURCE, workspace, dry_run=False)
    before = (workspace / ".assistant_workspace_instructions.md").read_text(encoding="utf-8")
    actions = PUBLISH.publish(SOURCE, workspace, dry_run=False)

    assert actions[-1].endswith("are up to date") and (workspace / ".assistant_workspace_instructions.md").read_text(encoding="utf-8") == before

def test_other_teams_skills_and_instructions_are_kept(tmp_path: Path):
    """Checks that a skill folder of another team, and the text of other teams in the instructions file (before and after the section), are kept when the BHoM section is updated.

    Protects the shared workspace: only what BHoM owns is replaced.
    """
    workspace = tmp_path / "workspace"
    other = workspace / ".assistant" / "skills" / "other-team"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("---\nname: other-team\ndescription: x\n---\n", encoding="utf-8")
    file = workspace / ".assistant_workspace_instructions.md"
    file.write_text("## Team A\n- Use tabs.\n\n<!-- bhom-schema: start -->\nold text\n<!-- bhom-schema: end -->\n\n## Team B\n- Be brief.\n", encoding="utf-8")

    PUBLISH.publish(SOURCE, workspace, dry_run=False)
    text = file.read_text(encoding="utf-8")

    assert (other / "SKILL.md").is_file()
    assert text.startswith("## Team A\n- Use tabs.\n\n<!-- bhom-schema: start -->\n## BHoM data") and "old text" not in text
    assert text.endswith("<!-- bhom-schema: end -->\n\n## Team B\n- Be brief.\n")

def test_the_section_is_added_at_the_end_when_the_file_has_none(tmp_path: Path):
    """Checks that an instructions file with other text and no markers gets the section after that text, with a blank line between.

    Protects the first publish into a workspace that already has instructions.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    file = workspace / ".assistant_workspace_instructions.md"
    file.write_text("## Team A\n- Use tabs.\n", encoding="utf-8")
    PUBLISH.publish(SOURCE, workspace, dry_run=False)

    assert file.read_text(encoding="utf-8").startswith("## Team A\n- Use tabs.\n\n<!-- bhom-schema: start -->\n")

def test_a_removed_file_goes_with_a_replaced_skill_and_a_changed_section_is_rewritten(tmp_path: Path):
    """Checks that a file left in the published skill that is no longer in the source is removed when the skill is published again, and that a changed instruction replaces the old section.

    Protects the skill from stale files after an edit.
    """
    source = copy_source(tmp_path / "source")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    PUBLISH.publish(source, workspace, dry_run=False)
    (workspace / ".assistant" / "skills" / "bhom-mapping" / "stale.md").write_text("old", encoding="utf-8")
    (source / "workspace-instructions.md").write_text("## BHoM data\n- A new rule.\n", encoding="utf-8")
    actions = PUBLISH.publish(source, workspace, dry_run=False)

    assert not (workspace / ".assistant" / "skills" / "bhom-mapping" / "stale.md").exists()
    assert actions[1].startswith("wrote the BHoM section") and "- A new rule." in (workspace / ".assistant_workspace_instructions.md").read_text(encoding="utf-8")
    assert "Use bhom_schema" not in (workspace / ".assistant_workspace_instructions.md").read_text(encoding="utf-8")

def test_a_damaged_marker_or_a_file_that_is_too_long_stops_before_anything_is_written(tmp_path: Path):
    """Checks that a file with only one marker, and instructions that would be over the 20,000 characters Genie Code reads, raise ValueError and leave the workspace without the skill.

    Protects the workspace from a half-done publish.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    file = workspace / ".assistant_workspace_instructions.md"
    file.write_text("text\n<!-- bhom-schema: start -->\nnever closed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="one of the markers"):
        PUBLISH.publish(SOURCE, workspace, dry_run=False)

    file.write_text("x" * 20000, encoding="utf-8")
    with pytest.raises(ValueError, match="Genie Code reads at most 20000"):
        PUBLISH.publish(SOURCE, workspace, dry_run=False)

    assert not (workspace / ".assistant").exists() and file.read_text(encoding="utf-8") == "x" * 20000

def test_publish_py_is_a_databricks_notebook_that_only_runs_as_main():
    """Checks that publish.py starts as a Databricks notebook source and has its widgets under the main guard, so importing it (as the tests do) runs nothing.

    Protects the notebook that an admin opens in the workspace.
    """
    text = (SOURCE / "publish.py").read_text(encoding="utf-8")

    assert text.startswith("# Databricks notebook source\n") and 'if __name__ == "__main__":' in text
    assert text.index("dbutils.widgets") > text.index('if __name__ == "__main__":')

# ---------------------------------------------------------------- the text of the skill

def frontmatter(text: str) -> dict[str, str]:
    """Reads the frontmatter of a SKILL.md: the `key: value` lines between the two `---` lines."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match is not None
    return {key.strip(): value.strip() for key, value in (line.split(":", 1) for line in match.group(1).splitlines())}

def test_the_skill_has_the_frontmatter_genie_code_needs():
    """Checks that SKILL.md starts with a name that is the name of its folder and a description that says what it does and when to use it, within a size that keeps the skill focused.

    Protects the skill from not being listed, or not being loaded when it is relevant.
    """
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    header = frontmatter(text)

    assert header["name"] == SKILL.name == "bhom-mapping"
    assert "Use when" in header["description"] and 100 < len(header["description"]) < 600
    assert len(text) < 12000 and "mapping-guidance.md" in text and "mapping-format.md" in text

def test_the_tools_the_skill_names_exist():
    """Checks that the import statement in SKILL.md runs, so every tool it names is in bhom_schema.mapping, and that every tool is used in the text of the skill.

    Protects the skill from naming a function that was renamed or removed.
    """
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    statement = re.search(r"```python\n(from bhom_schema\.mapping import \(.*?\))\n```", text, re.S)
    assert statement is not None
    namespace: dict[str, Any] = {}
    exec(statement.group(1), namespace)
    names = sorted(name for name in namespace if not name.startswith("__"))

    assert names == sorted(["alignment", "profile", "sample_rows", "check_key", "schema_overview", "describe_class", "search_properties", "find_mapping", "load_mapping", "save_mapping", "parse_mapping",
                            "mapping_path", "validate_mapping", "write_gold"])
    assert all(len(re.findall(rf"\b{name}\b", text)) >= 2 for name in names)

def test_the_example_mapping_in_the_format_reference_loads():
    """Checks that the YAML example of mapping-format.md is a valid mapping: it loads with every rule checked against the real classes.

    Protects the reference an agent copies from.
    """
    text = (SKILL / "mapping-format.md").read_text(encoding="utf-8")
    block = re.search(r"```yaml\n(.*?)\n```", text, re.S)
    assert block is not None
    mapping = parse_mapping(yaml.safe_load(block.group(1)))

    assert [entity.name for entity in mapping.entities] == ["Building", "Storey", "Beam"]

def test_the_format_reference_names_the_keys_and_units_of_the_code():
    """Checks that every key of a mapping, entity and column, and every unit of every quantity, that the code knows appears in mapping-format.md.

    Protects the reference from missing a key or a unit that was added.
    """
    text = (SKILL / "mapping-format.md").read_text(encoding="utf-8")
    keys = set(TOP_KEYS) | set(ENTITY_KEYS) | set(COLUMN_KEYS)

    assert [key for key in sorted(keys) if f"`{key}`" not in text] == []
    for category, table in unit_table.FACTORS.items():
        line = next(line for line in text.splitlines() if line.startswith(f"{category}:") or f" {category}:" in line)
        assert [unit for unit in table if unit not in line] == [], category

def test_the_instructions_are_short_and_install_the_package_as_the_demo_does():
    """Checks that the BHoM instructions are far below the 20,000-character limit, carry no markers (the publisher adds them), and use the same install line as the demo notebook.

    Protects a single source for the install line, and the room left for the instructions of other teams.
    """
    text = (SOURCE / "workspace-instructions.md").read_text(encoding="utf-8")
    notebook = json.loads((ROOT / ".ci" / "unit-tests" / "notebooks" / "Bronze-To-BHoM-Demo.ipynb").read_text(encoding="utf-8"))
    install = next("".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code" and "".join(cell["source"]).startswith("%pip"))

    assert len(text) < 3000 and "bhom-schema:" not in text
    assert install.removeprefix("%pip ") in text and "`@bhom-mapping check <table>`" in text

# ---------------------------------------------------------------- publishing through the Workspace API

class Missing(Exception):
    """The exception the stand-in client raises for a path that does not exist, as the SDK's NotFound."""

class FakeWorkspace:
    """The `workspace` part of a WorkspaceClient, as far as the publisher uses it: it keeps files and folders by their API path and records the calls."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        """Starts with the given files (API path to text) and an empty log."""
        self.files = dict(files or {})
        self.folders: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def download(self, path: str) -> Any:
        """Returns a file-like object with the bytes of the file, or raises Missing."""
        import io

        if path not in self.files:
            raise Missing(path)

        return io.BytesIO(self.files[path].encode("utf-8"))

    def mkdirs(self, path: str) -> None:
        """Records the folder."""
        self.calls.append(("mkdirs", path))
        self.folders.add(path)

    def upload(self, path: str, content: Any, format: Any = None, overwrite: bool = False) -> None:
        """Stores the file, refusing to replace one unless overwrite is set, and records the format."""
        assert overwrite and format == "AUTO"
        self.calls.append(("upload", path))
        self.files[path] = content.read().decode("utf-8")

    def delete(self, path: str, recursive: bool = False) -> None:
        """Removes a folder and what is under it, or raises Missing when there is nothing there."""
        self.calls.append(("delete", path))
        found = [name for name in self.files if name.startswith(path + "/")]
        if not found:
            raise Missing(path)

        for name in found:
            del self.files[name]

class FakeClient:
    """A WorkspaceClient with only the `workspace` part."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        """Keeps the stand-in workspace."""
        self.workspace = FakeWorkspace(files)

def test_publishing_through_the_workspace_api_uses_paths_without_the_workspace_prefix():
    """Checks that the workspace store writes the skill files and the instructions with the paths the Workspace API takes (`/.assistant/...`, not `/Workspace/.assistant/...`), as files in AUTO
    format, replacing the skill folder and keeping other text of the instructions.

    Protects the publish that failed through the file system: the root of the workspace cannot be written that way.
    """
    from pathlib import PurePosixPath

    client = FakeClient({"/.assistant_workspace_instructions.md": "## Team A\n- Use tabs.\n", "/.assistant/skills/bhom-mapping/stale.md": "old"})
    store = PUBLISH.WorkspaceStore(client, Missing, "AUTO")
    actions = PUBLISH.publish(SOURCE, PurePosixPath("/Workspace"), dry_run=False, store=store)
    files = client.workspace.files

    assert actions[0] == "copied skill bhom-mapping to /Workspace/.assistant/skills/bhom-mapping"
    assert sorted(name for name in files if name.startswith("/.assistant/skills/")) == [
        "/.assistant/skills/bhom-mapping/SKILL.md", "/.assistant/skills/bhom-mapping/mapping-format.md", "/.assistant/skills/bhom-mapping/mapping-guidance.md"]
    assert files["/.assistant/skills/bhom-mapping/SKILL.md"].replace("\r\n", "\n") == (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert files["/.assistant_workspace_instructions.md"].startswith("## Team A\n- Use tabs.\n\n<!-- bhom-schema: start -->\n## BHoM data")
    assert ("delete", "/.assistant/skills/bhom-mapping") in client.workspace.calls and not any(path.startswith("/Workspace") for _, path in client.workspace.calls)

def test_a_dry_run_through_the_workspace_api_only_reads():
    """Checks that a dry run through the workspace store downloads the instructions (a missing file counts as empty) and makes no write, delete or folder call.

    Protects the first look an admin takes before publishing.
    """
    from pathlib import PurePosixPath

    client = FakeClient()
    actions = PUBLISH.publish(SOURCE, PurePosixPath("/Workspace"), dry_run=True, store=PUBLISH.WorkspaceStore(client, Missing, "AUTO"))

    assert client.workspace.calls == [] and actions[0].startswith("would copy skill bhom-mapping to /Workspace/.assistant/skills/bhom-mapping")
    assert actions[1].startswith("would write the BHoM section of the instructions in /Workspace/.assistant_workspace_instructions.md")
