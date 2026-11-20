"""The test notebook Databricks-User-Guide-Test.ipynb, run cell by cell against the stand-in SparkSession of mapping_fakes.

The code cells are run as they are, except the `%pip` cell, the restart of Python and the cells marked `# databricks-only` (they need Spark joins, which the stand-in does not have). The notebook
only demonstrates Genie Code, so the Genie Code steps are played by the test, which writes the mapping file and the gold tables the way Genie Code would. The real check is running the notebook on
Databricks.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from bhom_schema.mapping import parse_mapping, save_mapping, write_gold
from mapping_fakes import FakeSpark

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "Databricks-User-Guide-Test.ipynb"
SILVER = "student_area.vcl.bhom_user_guide_test_flat"
GOLD = "student_area.vcl_gold"
BASE = {"Fragments": "skip", "CustomData": "skip"}

def genie_mapping() -> dict[str, Any]:
    """Returns the mapping that Genie Code is expected to propose for the sample silver table, as the guide shows it: Project at the root, Buildings under it, Storeys and Beams under the Building."""
    return {
        "version": 1,
        "source": SILVER,
        "gold_schema": GOLD,
        "entities": {
            "Project": {
                "class": "bhom_schema.DataSchema_oM.Project.Project", "key": ["project_number"], "fields": dict(BASE),
                "columns": {"Number": {"from": "project_number"}, "Name": {"from": "project_name"}}},
            "Building": {
                "class": "bhom_schema.DataSchema_oM.Building.Building", "key": ["project_number", "model_name"], "parent": "Project", "fields": dict(BASE),
                "columns": {"Name": {"from": "model_name"}, "StoreysAboveGround": {"from": "levels_above_ground"}}},
            "Storey": {
                "class": "bhom_schema.DataSchema_oM.Storey.Storey", "key": ["project_number", "model_name"], "parent": "Building", "fields": dict(BASE),
                "columns": {"TypicalHeight": {"from": "typical_level_gap", "unit": "mm"}}},
            "Beam": {
                "class": "bhom_schema.DataSchema_oM.Elements.Beam.Beam", "key": ["project_number", "model_name", "family_type"], "parent": "Building",
                "fields": {**BASE, "MaterialDistribution": "json"},
                "columns": {
                    "TypicalMaterial": {"from": "structural_material", "values": {"Steel - hot rolled": "SteelHotRolled", "glulam": "TimberGlulam"}},
                    "TypicalSize": {"from": "family_type"}}}},
        "unmapped": {
            "source_file": "lineage back to the bronze Parquet file; stays in silver",
            "number_of_lifts": "no BHoM property for the number of lifts yet"}}

class Run:
    """A notebook being run cell by cell in one namespace, so a test can stop where the notebook waits for Genie Code and do that step itself."""

    def __init__(self) -> None:
        """Reads the code cells that the stand-in can run, and starts with an empty session."""
        self.spark = FakeSpark()
        self.shown: list[Any] = []
        self.namespace: dict[str, Any] = {"spark": self.spark, "display": self.shown.append, "__name__": "__main__"}
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        self.cells = [
            ("".join(cell["source"]), cell["id"]) for cell in notebook["cells"]
            if cell["cell_type"] == "code" and not "".join(cell["source"]).startswith(("%", "dbutils.library", "# databricks-only"))]
        self.next = 0

    def execute(self, source: str, name: str) -> None:
        """Runs one cell in the namespace."""
        exec(compile(source, f"<{name}>", "exec"), self.namespace)

    def run_through(self, marker: str) -> None:
        """Runs the next cells in order, up to and including the first one that contains the marker."""
        while self.next < len(self.cells):
            source, name = self.cells[self.next]
            self.next += 1
            self.execute(source, name)
            if marker in source:
                return

        raise AssertionError(f"no cell contains {marker!r}")

    def run_again(self, marker: str) -> None:
        """Runs the cell that contains the marker once more, wherever the run is."""
        source, name = next(cell for cell in self.cells if marker in cell[0])
        self.execute(source, name)

    def run_all(self) -> None:
        """Runs every remaining cell."""
        while self.next < len(self.cells):
            source, name = self.cells[self.next]
            self.next += 1
            self.execute(source, name)

    def genie_saves(self, data: dict[str, Any], folder: Path) -> None:
        """Plays Genie Code saving a mapping file."""
        save_mapping(parse_mapping(data), folder=folder)

def test_the_notebook_runs_end_to_end_when_genie_code_does_its_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Checks that with the three Genie Code steps done the way the guide says every cell runs: the silver table, the Project-rooted mapping, the gold tables with their row counts and links, the unmapped
    column, and a clean-up that drops every table and the mapping file.

    Protects the notebook that tests the guide on Databricks from rotting when the package changes.
    """
    monkeypatch.chdir(tmp_path)
    run = Run()
    run.run_through("MAPPING_FOLDER = ")
    run.run_through("wrote {len(SILVER_ROWS)} rows")
    run.run_through("print(alignment(")
    output = capsys.readouterr().out

    assert f"wrote 12 rows to {SILVER}" in output
    assert f"{SILVER} has no mapping yet, so it is not BHoM-aligned." in output

    run.genie_saves(genie_mapping(), tmp_path)
    run.run_through("MAPPING = check_mapping()")
    output = capsys.readouterr().out

    assert "Project    Project    key project_number" in output and "parent Project" in output
    assert "number_of_lifts: unmapped, because: no BHoM property for the number of lifts yet" in output
    assert "the mapping is aligned and valid" in output

    write_gold(run.spark, SILVER, run.namespace["MAPPING"])
    run.run_through("GOLD_ROWS = check_gold(MAPPING)")
    output = capsys.readouterr().out
    gold = {name.rsplit(".", 1)[1]: len(table.rows) for name, table in run.spark.tables.items() if name.startswith(f"{GOLD}.")}

    assert gold == {"Project": 2, "Building": 4, "Storey": 4, "Beam": 12}
    assert "Project_id -> Project" in output and output.count("Building_id -> Building") == 2

    run.run_all()
    output = capsys.readouterr().out

    assert "project 12345: Alpha Tower" in output and "beam UB-1" in output and "TimberGlulam" in output
    assert "properties that mention 'lift': none" in output and "properties that mention 'elevator': none" in output
    assert output.count("dropped ") == 5 and "removed " in output and list(run.spark.tables) == []
    assert not (tmp_path / "bhom-mappings").exists() or not list((tmp_path / "bhom-mappings").iterdir())

def test_the_checks_after_the_genie_steps_say_what_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Checks that each check cell after a Genie Code step fails with a clear message until the step is done: no mapping file, a mapping with no Project root, and gold tables that were not written. It then
    passes when the steps are done the way the guide says.

    Protects the person running the notebook, who must be told exactly what Genie Code still has to do.
    """
    monkeypatch.chdir(tmp_path)
    run = Run()
    run.run_through("print(alignment(")

    with pytest.raises(AssertionError, match="no mapping file was found"):
        run.run_through("MAPPING = check_mapping()")

    # Genie Code, if it forgot the Project: a building at the root
    without_project = copy.deepcopy(genie_mapping())
    del without_project["entities"]["Project"]
    del without_project["entities"]["Building"]["parent"]
    run.genie_saves(without_project, tmp_path)
    with pytest.raises(AssertionError, match="there is no entity of the class Project"):
        run.run_again("MAPPING = check_mapping()")

    # Genie Code, the way the guide asks: Project at the root
    run.genie_saves(genie_mapping(), tmp_path)
    run.run_again("MAPPING = check_mapping()")
    namespace = run.namespace
    assert [entity.name for entity in namespace["MAPPING"].entities] == ["Project", "Building", "Storey", "Beam"]

    with pytest.raises(AssertionError, match="does not exist: has the gold step been done"):
        run.run_through("GOLD_ROWS = check_gold(MAPPING)")

    # Genie Code writes gold because the engineer asked
    write_gold(run.spark, SILVER, namespace["MAPPING"])
    run.run_again("GOLD_ROWS = check_gold(MAPPING)")
    assert {name: len(rows) for name, rows in namespace["GOLD_ROWS"].items()} == {"Project": 2, "Building": 4, "Storey": 4, "Beam": 12}

    run.run_all()

def test_a_mapping_of_an_earlier_run_is_removed_at_the_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Checks that the silver cell removes the mapping file that an earlier run of the notebook left for the demo table, so that Genie Code starts from nothing.

    Protects a second run from a check that says the table is aligned before anything was mapped.
    """
    monkeypatch.chdir(tmp_path)
    stale = tmp_path / "bhom-mappings" / f"{SILVER}.yml"
    stale.parent.mkdir()
    stale.write_text("version: 1\n", encoding="utf-8")

    run = Run()
    run.run_through("wrote {len(SILVER_ROWS)} rows")

    assert not stale.exists() and "removed the mapping file of an earlier run" in capsys.readouterr().out

def test_the_notebook_refuses_a_gold_schema_that_already_holds_its_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Checks that the silver cell stops with a clear message when the gold schema already has a table named like one of the entities, before anything is written.

    Protects the tables of somebody else from the clean-up of the last section, which drops the gold tables of the notebook.
    """
    monkeypatch.chdir(tmp_path)
    run = Run()
    run.spark.tables[f"{GOLD}.Building"] = FakeSpark.silver(f"{GOLD}.Building", [], ["Name"]).tables[f"{GOLD}.Building"]

    with pytest.raises(AssertionError, match=r"these tables exist already: student_area.vcl_gold.Building\. Use a gold schema that holds nothing else"):
        run.run_through("wrote {len(SILVER_ROWS)} rows")

    assert SILVER not in run.spark.tables

def test_the_notebook_is_stored_without_outputs_and_says_how_to_run_it():
    """Checks that the notebook has no stored outputs or execution counts, uses no widget and has no way around Genie Code, that its first code cell installs the package with the mapping extra, and that
    its first cell tells the reader how to upload and run it.

    Protects the file from carrying someone's run, from drifting back to inputs in widgets, and the instructions from going missing.
    """
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    first = "".join(notebook["cells"][0]["source"])
    sources = "".join("".join(cell["source"]) for cell in notebook["cells"])

    assert all(cell["outputs"] == [] and cell["execution_count"] is None for cell in code)
    assert '"bhom-schema[mapping]"' in "".join(code[0]["source"])
    assert "How to upload and run this notebook" in first and "**Import the file.**" in first and "**Git folder.**" in first and "`CATALOG`" in first
    assert "widget" not in sources.replace('"widgets": {}', "") and "use_genie" not in sources and "write_gold(spark" not in sources
