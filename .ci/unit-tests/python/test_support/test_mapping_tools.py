"""The tools Genie Code (or a person) looks with: the BHoM classes (overview, cards, search), the facts about a silver table (profile, sample rows, a proposed key), and the alignment check.

They report facts and rank nothing. They run on rows and on a stand-in SparkSession, against the real classes of the DataSchema_oM assembly.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from bhom_schema.DataSchema_oM.Building import Building
from bhom_schema.DataSchema_oM.Storey import Storey
from bhom_schema.mapping import (
    alignment, check_key, check_key_rows, describe_class, parse_mapping, profile, profile_rows, sample_rows, save_mapping, schema_classes, schema_overview, search_properties)
from bhom_schema.mapping.profile import profile_column
from mapping_fakes import FakeSpark
from test_mapping import TABLE, example

# ---------------------------------------------------------------- the classes

def test_the_overview_lists_each_real_class_once_without_the_demo():
    """Checks that the overview has a line for each class of the DataSchema assembly (name, path, first sentence, number of properties), once each, and leaves out the demo class ExampleObject.

    Protects the way into the schema: it never offers a demo class as a place for real data.
    """
    overview = schema_overview()
    names = [item.name for item in overview]
    storey = next(item for item in overview if item.name == "Storey")

    assert {"Building", "Storey", "Beam", "Grid"} <= set(names)
    assert len(names) == len(set(names)) and "ExampleObject" not in names and "BHoMObject" not in names
    assert storey.path == "bhom_schema.DataSchema_oM.Storey.Storey" and storey.properties == 4
    assert storey.summary == "Typical storey properties of a building: slab-to-slab height, and the floor slab areas below and at the roof."
    assert [model.__name__ for model in schema_classes()] == names

def test_a_class_card_gives_what_a_reader_needs_to_judge_each_property():
    """Checks the card of Storey and Beam: each property's kind, unit, description, display text and aliases, the members of an enum, and the fields that still need a decision.

    Protects what Genie Code reads before it maps a column: the facts, in a form that fits a conversation.
    """
    card = describe_class("Storey")
    height = next(entry for entry in card.properties if entry.name == "TypicalHeight")

    assert (card.name, card.path) == ("Storey", "bhom_schema.DataSchema_oM.Storey.Storey")
    assert [entry.name for entry in card.properties] == ["Name", "TypicalHeight", "NonRoofArea", "RoofArea"]
    assert (height.kind, height.quantity.unit if height.quantity else None) == ("number", "m")
    assert height.display_text == "Typical slab-to-slab height"
    assert height.aliases == ("slab-to-slab height", "floor-to-floor height", "storey height")
    assert {"Fragments", "CustomData"} <= {name for name, _ in card.undecided}
    text = card.text()
    assert "TypicalHeight: number in m (Length)" in text and "aliases: slab-to-slab height, floor-to-floor height, storey height" in text
    assert "Derivation:" not in text and "Derivation:" in card.text(full=True)

    material = next(entry for entry in describe_class("Beam").properties if entry.name == "TypicalMaterial")
    assert material.kind == "text" and {"SteelHotRolled", "TimberGlulam", "ConcreteInSitu"} <= set(material.members)
    assert "members: SteelHotRolled" in material.text()

def test_a_class_is_found_by_name_or_path_and_a_wrong_name_lists_the_classes():
    """Checks that describe_class takes a simple name, a full path and the class itself, and that an unknown name raises KeyError that lists the classes.

    Protects the message the agent sees when it spells a class wrong.
    """
    by_name = describe_class("Building")

    assert by_name == describe_class("bhom_schema.DataSchema_oM.Building.Building") == describe_class(Building)

    with pytest.raises(KeyError, match="'Floor' is not a class of the package; the classes are bhom_schema.DataSchema_oM.Building.Building"):
        describe_class("Floor")

def test_a_search_finds_properties_by_words_and_ranks_nothing():
    """Checks that a search finds a property by a word of its alias, display text, name or description, says where it matched, matches plurals, gives the same list in the same order every time,
    and carries no score.

    Protects the rule that code narrows a large schema and the reader judges.
    """
    found = search_properties("storey height")
    labels = [match.label for match in found]
    best = next(match for match in found if match.label == "Storey.TypicalHeight")

    assert "Storey.TypicalHeight" in labels and set(best.found_in) == {"name", "display text", "alias", "description"}
    assert search_properties("storey height") == found
    assert [match.label for match in search_properties("storeys above ground")][:1] == ["Building.StoreysAboveGround"]
    assert [match.label for match in search_properties("GIA")] == ["Storey.NonRoofArea"]
    assert not hasattr(found[0], "score")

    anything = search_properties("basement roof", any_word=True)
    everything = search_properties("basement roof")
    assert len(anything) > len(everything) and {match.label for match in everything} <= {match.label for match in anything}
    assert search_properties("") == [] and search_properties("zzzz") == []
    assert {match.entry.model for match in search_properties("name", classes=[Storey])} == {Storey}

# ---------------------------------------------------------------- the table

def model_rows() -> list[dict[str, Any]]:
    """Returns the rows of a flat table of two projects with two models each (the same model names in both), six element rows per model: project and model values repeat on every row, element values vary."""
    rows: list[dict[str, Any]] = []
    for project in ("P-1", "P-2"):
        for model, levels in (("Tower", 24), ("Podium", 4)):
            for element in range(6):
                rows.append({
                    "project_number": project, "client": "Acme" if project == "P-1" else "Birch", "model_name": model, "levels_above_ground": levels + (1 if project == "P-2" else 0),
                    "family_type": f"UB-{element % 3}", "length_mm": 4000 + 100 * element, "source_file": f"{project}/{model}/{element}.parquet"})

    return rows

def test_a_column_is_profiled_by_kind_nulls_values_and_range():
    """Checks the profile of columns of numbers, text, booleans (not counted as numbers), dates, lists, a mix and nothing but empty values, and how it is written out.

    Protects what Genie Code reads instead of the data: counts, a few top values and the numeric range.
    """
    numbers = profile_column("height", [3500, 3600, 3500, None, 4200.5, float("nan")])
    assert (numbers.kind, numbers.rows, numbers.nulls, numbers.distinct) == ("number", 6, 2, 3)
    assert (numbers.minimum, numbers.median, numbers.maximum) == (3500.0, 3550.0, 4200.5)
    assert numbers.top[0] == (3500, 2) and numbers.null_rate == pytest.approx(2 / 6) and numbers.values()[0] == 3500
    assert numbers.text() == "height: number; 33% empty; 3 distinct; range 3500 to 4200.5, median 3550; top 3500 x2, 3600 x1, 4200.5 x1"

    assert profile_column("flag", [True, False, True]).kind == "boolean"
    assert profile_column("name", ["a", "b", "", None]).kind == "text" and profile_column("name", ["a", "b", "", None]).nulls == 2
    assert profile_column("day", [date(2026, 1, 1)]).kind == "datetime"
    assert profile_column("points", [[1, 2], [1, 2], {"a": 1}]).kind == "collection" and profile_column("points", [[1, 2], [1, 2], {"a": 1}]).distinct == 2
    assert profile_column("both", ["a", 1]).kind == "mixed"
    nothing = profile_column("none", [None, ""])
    assert (nothing.kind, nothing.distinct, nothing.minimum, nothing.null_rate) == ("empty", 0, None, 1.0)
    assert profile_column("nothing", []).null_rate == 0.0

def test_the_profile_of_a_table_reads_a_slice_and_says_so():
    """Checks that profile reads at most `limit` rows and reports sampled when there are more, reads all rows with no limit, profiles only the columns asked for, lists the columns of a table that
    has no rows, and writes a few lines.

    Protects a large table from being collected whole, and the engineer from mistaking a sample for the table.
    """
    spark = FakeSpark.silver(TABLE, model_rows())
    spark.tables["a.b.empty"] = FakeSpark.silver("a.b.empty", [], ["x", "y"]).tables["a.b.empty"]

    sampled = profile(spark, TABLE, limit=10)
    assert (sampled.rows, sampled.sampled) == (10, True) and "(a sample: the table has more)" in sampled.text()
    assert (profile(spark, TABLE, limit=None).rows, profile(spark, TABLE, limit=None).sampled) == (24, False)
    assert profile(spark, TABLE, limit=24).sampled is False
    assert [column.name for column in profile(spark, TABLE, columns=["client", "model_name"]).columns] == ["client", "model_name"]
    assert profile(spark, TABLE).column("client").distinct == 2 and profile(spark, TABLE).text().splitlines()[0] == f"{TABLE}: 24 rows"

    empty = profile(spark, "a.b.empty")
    assert [column.name for column in empty.columns] == ["x", "y"] and empty.rows == 0

    with pytest.raises(KeyError):
        empty.column("nothing")

    assert profile_rows(TABLE, model_rows()[:2]).columns[0].name == "project_number"

def test_sample_rows_are_few_cut_and_only_the_columns_asked_for():
    """Checks that sample_rows returns at most n rows (and never more than 50), keeps only the columns asked for, cuts long texts, and takes a condition.

    Protects the conversation: raw values enter it in small amounts.
    """
    rows = [{"id": index, "note": "x" * 200, "kind": "a"} for index in range(80)]
    spark = FakeSpark.silver(TABLE, rows)

    assert len(sample_rows(spark, TABLE)) == 10 and len(sample_rows(spark, TABLE, n=500)) == 50 and sample_rows(spark, TABLE, n=0) == []
    shown = sample_rows(spark, TABLE, columns=["note"], n=2)
    assert shown == [{"note": "x" * 80 + "…"}, {"note": "x" * 80 + "…"}]
    assert sample_rows(spark, TABLE, n=1, width=5)[0]["note"] == "xxxxx…" and sample_rows(spark, TABLE, n=1)[0]["id"] == 0

def test_a_proposed_key_is_checked_against_the_data():
    """Checks that a key (project and model) makes four groups, that the columns constant within them are listed (and the element columns, which vary, are not), and that a key that is too coarse
    or too fine says so.

    Protects the step where the agent proposes the entities: the code says whether the data agrees.
    """
    spark = FakeSpark.silver(TABLE, model_rows())
    building = check_key(spark, TABLE, ["project_number", "model_name"])

    assert (building.groups, building.rows, building.empty_rows) == (4, 24, 0)
    assert set(building.constant) == {"client", "levels_above_ground"} and set(building.varying) == {"family_type", "length_mm", "source_file"}
    assert building.conflicts == () and "constant in every group: client, levels_above_ground" in building.text()

    coarse = check_key_rows(model_rows(), ["model_name"])
    assert coarse.constant == () and "levels_above_ground" in coarse.varying and coarse.groups == 2

    fine = check_key_rows(model_rows(), ["source_file"])
    assert fine.groups == 24 and "levels_above_ground" in fine.constant

def test_rows_that_disagree_within_a_group_are_shown_with_examples():
    """Checks that a column with one value in nine of ten groups is reported as almost constant with its share, the groups that disagree and what they hold, and that rows with an empty key column
    are counted and left out.

    Protects the finding of a few rows that disagree with the rest of their building.
    """
    rows: list[dict[str, Any]] = [{"group": f"g{index}", "levels": 5, "colour": "red" if index == 3 and copy == 1 else "blue"} for index in range(10) for copy in range(2)]
    rows.append({"group": None, "levels": 5, "colour": "blue"})
    check = check_key_rows(rows, ["group"])

    assert (check.groups, check.rows, check.empty_rows) == (10, 21, 1)
    assert check.constant == ("levels",) and check.almost == (("colour", 0.9),)
    assert check.conflicts[0].column == "colour" and check.conflicts[0].groups == 1
    assert check.conflicts[0].examples == ((("g3",), ("blue", "red")),)
    text = check.text()
    assert "one value in 90% of the groups, but 1 groups have more" in text and "('g3',) has 'blue', 'red'" in text and "1 rows with an empty key column left out" in text

def test_a_key_that_is_not_a_column_is_refused():
    """Checks that a key naming a column the table lacks, and a key with no column, raise ValueError that names the columns.

    Protects the agent from a typo in a proposed key.
    """
    with pytest.raises(ValueError, match="project is not a column of the table; its columns are project_number"):
        check_key_rows(model_rows(), ["project"])

    with pytest.raises(ValueError, match="needs at least one column"):
        check_key_rows(model_rows(), [])

    assert check_key_rows([], ["a"]).groups == 0 and check_key_rows([{"a": None}], ["a"], ["a"]).constant == ()

# ---------------------------------------------------------------- the alignment check

def tool_with_mapping(root: Path) -> Path:
    """Makes a tool folder with a notebook subfolder and the mapping of the example table saved in it, and returns the notebook subfolder."""
    tool = root / "precedent-tool"
    (tool / "notebooks").mkdir(parents=True)
    save_mapping(parse_mapping(example()), folder=tool)
    return tool / "notebooks"

def mapped_columns() -> list[str]:
    """Returns the silver columns the example mapping accounts for."""
    return sorted(parse_mapping(example()).accounted_columns())

def test_a_table_with_no_mapping_is_not_aligned(tmp_path: Path):
    """Checks that a table with no mapping file is reported as such and that the summary says so.

    Protects the first answer an engineer gets for a new flat table.
    """
    result = alignment(None, TABLE, start=tmp_path, columns=["storey_height", "qa_flag"])

    assert (result.status, result.aligned, result.mapping_path) == ("no-mapping", False, None)
    assert result.summary() == f"{TABLE} has no mapping yet, so it is not BHoM-aligned."

def test_a_table_that_matches_its_mapping_is_aligned(tmp_path: Path):
    """Checks that a table whose columns are exactly the mapping's is aligned, found from a notebook folder below the tool, and that the summary names the file.

    Protects the good answer: nothing to do.
    """
    notebooks = tool_with_mapping(tmp_path)
    result = alignment(None, TABLE, start=notebooks, columns=mapped_columns())

    assert (result.status, result.aligned) == ("aligned", True)
    assert result.mapping_path == (notebooks.parent / "bhom-mappings" / f"{TABLE}.yml").resolve()
    assert result.summary().startswith(f"{TABLE} is aligned: the mapping ") and result.summary().endswith("covers every column.")

def test_a_table_that_changed_since_its_mapping_is_out_of_date(tmp_path: Path):
    """Checks that a new column of the table and a mapped column that the table lost are both reported, with the columns named, in the status and in the summary.

    Protects the engineer who added columns to the flat table after the mapping was made.
    """
    notebooks = tool_with_mapping(tmp_path)
    columns = [column for column in mapped_columns() if column != "family_type"] + ["brand_new"]
    result = alignment(None, TABLE, start=notebooks, columns=columns)

    assert result.status == "out-of-date" and not result.aligned
    assert (result.new_columns, result.missing_columns) == (("brand_new",), ("family_type",))
    assert "new columns the mapping does not know: brand_new" in result.summary()
    assert "columns the mapping uses that the table no longer has: family_type" in result.summary()

def test_a_mapping_that_breaks_a_rule_is_reported_with_its_problems(tmp_path: Path):
    """Checks that a mapping file with a bad unit is reported as invalid, with the problems, and that the summary lists them.

    Protects the loop in which Genie Code edits the file: the next check shows what is wrong.
    """
    notebooks = tool_with_mapping(tmp_path)
    path = notebooks.parent / "bhom-mappings" / f"{TABLE}.yml"
    path.write_text(path.read_text(encoding="utf-8").replace("unit: mm", "unit: kg"), encoding="utf-8")
    result = alignment(None, TABLE, start=notebooks, columns=mapped_columns())

    assert result.status == "invalid" and len(result.problems) == 1
    assert "'kg' is not a unit of Length" in result.summary() and "breaks its rules" in result.summary()

def test_the_columns_are_read_from_the_table_when_not_given(tmp_path: Path):
    """Checks that alignment reads the column names from the table through the session when `columns` is not given, even for a table with no rows.

    Protects the call an engineer makes in a notebook: alignment(spark, "catalog.schema.table").
    """
    notebooks = tool_with_mapping(tmp_path)
    spark = FakeSpark.silver(TABLE, [], mapped_columns())

    assert alignment(spark, TABLE, start=notebooks).aligned
