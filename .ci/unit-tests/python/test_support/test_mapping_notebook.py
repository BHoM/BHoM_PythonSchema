"""The demo notebook Bronze-To-BHoM-Demo.ipynb, run cell by cell against the stand-in SparkSession of mapping_fakes.

The code cells are run as they are, except the `%pip` cell and the restart of Python. The stand-in understands only what the helpers send, so the real workspace check is running the notebook on Databricks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mapping_fakes import FakeSpark

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks" / "Bronze-To-BHoM-Demo.ipynb"

class Widgets:
    """The `dbutils.widgets` of a notebook: it keeps the default of each widget, or the value the test sets."""

    def __init__(self, values: dict[str, str]) -> None:
        """Keeps the values the test sets for some widgets."""
        self.values = values
        self.defaults: dict[str, str] = {}

    def text(self, name: str, default: str, label: str = "") -> None:
        """Declares a text widget with its default."""
        self.defaults[name] = default

    def dropdown(self, name: str, default: str, choices: list[str], label: str = "") -> None:
        """Declares a dropdown widget with its default."""
        self.defaults[name] = default

    def get(self, name: str) -> str:
        """Returns the value of a widget: the one the test set, or the default."""
        return self.values.get(name, self.defaults[name])

class Dbutils:
    """The `dbutils` of a notebook, as far as the demo uses it: widgets, and the restart of Python (which does nothing here)."""

    def __init__(self, values: dict[str, str]) -> None:
        """Keeps the widgets."""
        self.widgets = Widgets(values)

def run_notebook(values: dict[str, str], printed: list[str]) -> tuple[dict[str, Any], FakeSpark]:
    """Runs the code cells of the notebook in one namespace, as a notebook does, and returns the namespace and the session. `printed` is not used by the cells; output is read from capsys."""
    spark = FakeSpark()
    shown: list[Any] = []
    namespace: dict[str, Any] = {"spark": spark, "dbutils": Dbutils(values), "display": shown.append, "__name__": "__main__"}
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] != "code" or source.startswith("%") or source.startswith("dbutils.library"):
            continue

        exec(compile(source, f"<{cell['id']}>", "exec"), namespace)

    namespace["shown"] = shown
    return namespace, spark

def test_the_notebook_runs_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Checks that every code cell of the demo notebook runs, in order, against the stand-in, and that the outputs say what the text promises: no mapping at first, two problems that are then fixed,
    gold tables with their rows, the objects read back with the height in metres, and an out-of-date mapping that is then aligned.

    Protects the notebook that shows the flow to engineers for the first time.
    """
    monkeypatch.chdir(tmp_path)
    namespace, spark = run_notebook({}, [])
    output = capsys.readouterr().out
    silver = "student_area.vcl.bhom_demo_elements_flat"

    assert f"wrote 12 rows to {silver}" in output
    assert f"{silver} has no mapping yet, so it is not BHoM-aligned." in output
    assert "key project_number, model_name: 4 groups over 12 rows" in output and "  constant in every group: typical_level_gap" in output
    assert "Storey (bhom_schema.DataSchema_oM.Storey.Storey)" in output and "Building.StoreysAboveGround (found in" in output

    first = output.split("The mapping is not valid")[0]
    assert "unknown-value: TypicalMaterial: 'Steel hot roled' is not a member of StructuralMaterial and not in values [1 objects]" in first
    assert "conflict: levels_above_ground has more than one value for one Building; the first is used [1 objects]" in first
    assert "The mapping is not valid: 2 problems." in output and output.count("The mapping is valid for this table.") == 1

    assert "Building: dev_catalog" not in output and "Beam: student_area.vcl_gold.Beam, 12 rows written, 0 already there" in output
    assert "Tower    storey height 3.90 m" in output and "Podium   storey height 4.20 m" in output
    assert "UB-1   TimberGlulam" in output and "SteelHotRolled" in output
    assert "new columns the mapping does not know: levels_below_ground" in output
    assert f"{silver} is aligned: the mapping " in output

    gold = {name: table for name, table in spark.tables.items() if name.startswith("student_area.vcl_gold.")}
    assert {name.rsplit(".", 1)[1]: len(table.rows) for name, table in gold.items()} == {"Building": 4, "Storey": 4, "Beam": 12}
    assert "kept these tables and the mapping file" in output and (tmp_path / "bhom-mappings" / f"{silver}.yml").is_file()
    assert len(namespace["shown"]) == 1

def test_the_cleanup_drops_the_tables_and_the_mapping_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Checks that with the cleanup widget set to yes the notebook drops the silver table and the three gold tables and removes the mapping file it saved.

    Protects the engineer's catalog from leftovers of the demo.
    """
    monkeypatch.chdir(tmp_path)
    _, spark = run_notebook({"cleanup": "yes", "catalog": "demo", "schema": "s", "gold_schema": "g"}, [])
    output = capsys.readouterr().out

    assert output.count("dropped ") == 4 and "removed " in output and list(spark.tables) == []
    assert not (tmp_path / "bhom-mappings").exists() or not list((tmp_path / "bhom-mappings").iterdir())

def test_the_notebook_is_stored_without_outputs():
    """Checks that the notebook has no stored outputs or execution counts, as the other notebooks, and that its first code cell installs the package with the mapping extra.

    Protects the file from carrying the output of someone's run.
    """
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    code = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]

    assert all(cell["outputs"] == [] and cell["execution_count"] is None for cell in code)
    assert '"bhom-schema[mapping]"' in "".join(code[0]["source"])
