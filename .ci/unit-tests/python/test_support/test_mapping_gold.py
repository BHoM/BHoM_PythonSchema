"""Applying a mapping to the rows of a silver table, validating it, and writing the gold tables, run against the example mapping (Building, Storey, Beam) and a stand-in SparkSession.

The classes are the real ones of the DataSchema_oM assembly. The stand-in understands the statements and DataFrames the helpers use; the real workspace check is the demo notebook.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from bhom_schema.DataSchema_oM.Elements.Beam import Beam
from bhom_schema.DataSchema_oM.Enums.StructuralMaterial import StructuralMaterial
from bhom_schema.DataSchema_oM.Storey import Storey
from bhom_schema.mapping import (
    GoldRefused, TableMapping, apply_mapping, gold_id, gold_table, parse_mapping, save_mapping, validate_dataframe, validate_mapping, validate_rows, write_gold)
from bhom_schema.mapping.apply import ordered
from bhom_schema.tables import BASE_SKIPPED, rows_to_objects
from mapping_fakes import FakePandas, FakeSpark
from test_mapping import TABLE, example

COLUMNS = ["project_number", "model_name", "levels_above_ground", "levels_below_ground", "typical_level_gap", "structural_material", "family_type", "source_file"]

def silver_rows() -> list[dict[str, Any]]:
    """Returns the rows of a flat silver table for the example mapping: two projects with two models each, three beam families per model, building and storey values repeated on every row.

    A tower has two basement levels and a podium none (empty, so the default of the mapping is used); heights are in millimetres; materials are free text.
    """
    rows: list[dict[str, Any]] = []
    for project in ("P-1", "P-2"):
        for model, levels, basements, height in (("Tower", 24, 2, 3900.0), ("Podium", 4, None, 4200.0)):
            for index, family in enumerate(("UB-0", "UB-1", "UB-2")):
                rows.append({
                    "project_number": project, "model_name": model, "levels_above_ground": levels + (1 if project == "P-2" else 0), "levels_below_ground": basements,
                    "typical_level_gap": height, "structural_material": "glulam" if index == 1 else "Steel - hot rolled", "family_type": family, "source_file": f"{project}/{model}/{family}.parquet"})

    return rows

def the_mapping() -> TableMapping:
    """Returns the example mapping."""
    return parse_mapping(example())

def counts(report_or_applied: Any) -> dict[str, tuple[int, int]]:
    """Returns {entity: (objects, valid)} of an Applied result."""
    return {item.entity.name: (len(item.objects), item.valid) for item in report_or_applied.entities}

# ---------------------------------------------------------------- applying

def test_the_rows_become_the_objects_of_each_entity():
    """Checks that the example rows give four buildings, four storeys and twelve beams, all valid, with the values converted: millimetres to metres, free text to enum members, an empty cell to its default.

    Protects the main path from a silver row to a BHoM object.
    """
    applied = apply_mapping(silver_rows(), the_mapping())

    assert (applied.rows, counts(applied)) == (12, {"Building": (4, 4), "Storey": (4, 4), "Beam": (12, 12)})
    assert applied.problems() == []
    building = next(item for item in applied.entities if item.entity.name == "Building")
    tower = next(item.instance for item in building.objects if item.key == ("P-2", "Tower"))
    podium = next(item.instance for item in building.objects if item.key == ("P-1", "Podium"))
    assert (tower.Name, tower.StoreysAboveGround, tower.StoreysBelowGround) == ("Tower", 25, 2)  # type: ignore[union-attr]
    assert (podium.StoreysBelowGround, podium.StoreysAboveGround) == (0, 4)  # type: ignore[union-attr]
    storey = next(item.instance for item in next(item for item in applied.entities if item.entity.name == "Storey").objects if item.key == ("P-1", "Tower"))
    assert isinstance(storey, Storey) and storey.TypicalHeight == pytest.approx(3.9)
    beams = [item.instance for item in next(item for item in applied.entities if item.entity.name == "Beam").objects]
    assert all(isinstance(beam, Beam) for beam in beams)
    assert {beam.TypicalMaterial for beam in beams if isinstance(beam, Beam)} == {StructuralMaterial.SteelHotRolled, StructuralMaterial.TimberGlulam}

def test_ids_are_deterministic_and_parents_are_linked_by_id():
    """Checks that an object's id is the same on every run and differs between entities and keys, that BHoM_Guid is that id, and that a storey and a beam carry the id of their building.

    Protects writing gold again: the same silver row must always land on the same gold row.
    """
    first = apply_mapping(silver_rows(), the_mapping())
    second = apply_mapping(list(reversed(silver_rows())), the_mapping())
    by_entity = {item.entity.name: item for item in first.entities}
    building_ids = {item.key: item.id for item in by_entity["Building"].objects}

    assert {item.id for item in by_entity["Building"].objects} == {item.id for item in second.entities[0].objects}
    assert len({item.id for item in by_entity["Building"].objects} | {item.id for item in by_entity["Storey"].objects}) == 8
    assert all(item.instance is not None and str(item.instance.BHoM_Guid) == item.id for item in by_entity["Building"].objects)  # type: ignore[attr-defined]
    assert building_ids[("P-1", "Tower")] == gold_id("Building", ["P-1", "Tower"])
    assert all(item.parent_id == building_ids[item.key[:2]] for item in by_entity["Beam"].objects)
    assert all(item.parent_id == building_ids[item.key] for item in by_entity["Storey"].objects)
    assert all(item.parent_id is None for item in by_entity["Building"].objects)

def test_an_id_does_not_depend_on_how_a_key_is_written():
    """Checks that 24 and 24.0 give the same id, that text keys are stripped, and that the entity name is part of the id.

    Protects the id from a silver column that is a float in one run and an int in the next.
    """
    assert gold_id("Building", ["P-1", 24]) == gold_id("Building", [" P-1 ", 24.0]) != gold_id("Storey", ["P-1", 24])
    assert gold_id("Building", ["a"]) != gold_id("Building", ["b"])

def test_parents_come_before_their_children():
    """Checks that the entities are processed with each parent before its children even when the file lists a child first.

    Protects write_gold, which creates the tables parent first.
    """
    data = example()
    data["entities"] = {name: data["entities"][name] for name in ("Beam", "Storey", "Building")}

    assert [entity.name for entity in ordered(parse_mapping(data))] == ["Building", "Beam", "Storey"]

def test_what_does_not_fit_is_reported_not_dropped():
    """Checks each kind of problem: an enum text that is not a member (counted per object), a value that is not a number under a unit, two values for one object (the first is used), a value the class
    refuses, and rows without a key.

    Protects the rule that nothing is dropped silently: gold would otherwise lose data without a word.
    """
    rows = silver_rows()
    for row in rows:
        if row["structural_material"] == "glulam":
            row["structural_material"] = "unobtainium"

    rows[0]["typical_level_gap"] = "tall"
    rows[3]["levels_above_ground"] = 30
    for row in rows[6:9]:
        row["levels_above_ground"] = "many"

    rows[9]["family_type"] = None
    rows[10]["family_type"] = ""
    applied = apply_mapping(rows, the_mapping())
    problems = {(problem.entity, problem.kind): problem for problem in applied.problems()}

    assert problems[("Beam", "unknown-value")].count == 3 and "'unobtainium' is not a member of StructuralMaterial" in problems[("Beam", "unknown-value")].message
    assert problems[("Beam", "unknown-value")].example == "project_number=P-1, model_name=Tower, family_type=UB-1"
    assert problems[("Storey", "unit")].count == 1 and problems[("Storey", "conflict")].count == 1 and "'tall' is not a number, so the unit mm cannot be converted" in problems[("Storey", "unit")].message
    assert problems[("Building", "conflict")].count == 1 and "has more than one value" in problems[("Building", "conflict")].message
    assert problems[("Building", "invalid")].count == 1 and "StoreysAboveGround" in problems[("Building", "invalid")].message
    by_entity = {item.entity.name: item for item in applied.entities}
    assert (by_entity["Beam"].empty_key_rows, len(by_entity["Beam"].objects), by_entity["Beam"].valid) == (2, 10, 7)
    assert (by_entity["Building"].valid, by_entity["Storey"].valid) == (3, 3)
    assert next(item for item in by_entity["Building"].objects if item.key == ("P-1", "Podium")).instance is not None

def test_the_first_value_is_used_when_an_object_has_two():
    """Checks that when the rows of one building disagree about its levels the first value is used and the object stays valid, with the conflict reported.

    Protects the choice: the data is not guessed at, and it is not lost either.
    """
    rows = silver_rows()
    rows[1]["levels_above_ground"] = 99
    applied = apply_mapping(rows, the_mapping())
    building = next(item for item in applied.entities if item.entity.name == "Building")
    first = next(item.instance for item in building.objects if item.key == ("P-1", "Tower"))

    assert first is not None and first.StoreysAboveGround == 24  # type: ignore[attr-defined]
    assert "99" in (building.problems[0].example or "") and building.valid == 4

def test_a_text_that_already_is_a_member_needs_no_map():
    """Checks that an enum text that already is a member name passes without an entry in the value map, next to texts that are mapped.

    Protects the value maps of the example mapping: they list only what needs translating.
    """
    rows = silver_rows()
    rows[0]["structural_material"] = "SteelHotRolled"
    applied = apply_mapping(rows, the_mapping())

    assert applied.problems() == []

# ---------------------------------------------------------------- validating

def test_a_valid_mapping_gets_a_clean_report():
    """Checks that the report of the example mapping on its table is ok, counts the objects of each entity, and says so in the summary.

    Protects the good answer Genie Code gives: nothing to fix.
    """
    spark = FakeSpark.silver(TABLE, silver_rows(), COLUMNS)
    report = validate_mapping(spark, TABLE, the_mapping())

    assert report.ok and report.problems == [] and report.rows == 12 and not report.sampled
    assert [(item.name, item.objects, item.valid) for item in report.entities] == [("Building", 4, 4), ("Storey", 4, 4), ("Beam", 12, 12)]
    assert report.summary().splitlines()[0] == f"{TABLE}: 12 rows read" and report.summary().endswith("The mapping is valid for this table.")

def test_the_report_says_what_is_wrong_in_words():
    """Checks that a table with a new column, a lost column and bad values gives a report that is not ok, lists each problem with its count and an example, and ends with the number of problems.

    Protects the loop of Genie Code and the engineer: one run shows everything to fix.
    """
    rows = silver_rows()
    for row in rows:
        row["brand_new"] = 1
        row.pop("source_file")
        if row["structural_material"] == "glulam":
            row["structural_material"] = "unobtainium"

    columns = [column for column in COLUMNS if column != "source_file"] + ["brand_new"]
    report = validate_mapping(FakeSpark.silver(TABLE, rows, columns), TABLE, the_mapping())
    text = report.summary()

    assert not report.ok and report.new_columns == ("brand_new",) and report.missing_columns == ("source_file",)
    assert "columns: the table has columns the mapping does not know: brand_new" in text
    assert "columns: the mapping uses columns the table does not have: source_file" in text
    assert "unknown-value: TypicalMaterial: 'unobtainium' is not a member of StructuralMaterial and not in values [4 objects] (for example project_number=P-1" in text
    assert text.endswith("The mapping is not valid: 3 problems.")
    assert validate_rows(rows, columns, the_mapping()).problems == report.problems

def test_a_sample_is_marked_and_the_mapping_is_found_by_the_table_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Checks that validating the first rows says the table was sampled, and that with no mapping given the file for the table is found from the notebook's folder.

    Protects the call an engineer makes in a notebook: validate_mapping(spark, "catalog.schema.table", limit=1000).
    """
    save_mapping(the_mapping(), folder=tmp_path)
    monkeypatch.chdir(tmp_path)
    report = validate_mapping(FakeSpark.silver(TABLE, silver_rows(), COLUMNS), TABLE, limit=10)

    assert report.sampled and report.rows == 10 and "(a sample: the table has more)" in report.summary()

# ---------------------------------------------------------------- writing

def written(tmp_path: Path) -> tuple[FakeSpark, Any]:
    """Writes the example gold tables from the example silver table and returns the session and the result."""
    spark = FakeSpark.silver(TABLE, silver_rows(), COLUMNS)
    return spark, write_gold(spark, TABLE, the_mapping())

def test_gold_tables_are_made_and_filled_for_each_entity(tmp_path: Path):
    """Checks that write_gold makes a table for each entity in the gold schema, adds the parent column to the children and the Delta constraints for the enum columns, and writes the rows with
    their ids and the id of the parent.

    Protects the end of the flow: BHoM tables an engineer's production code can read.
    """
    spark, result = written(tmp_path)
    mapping = the_mapping()
    names = {entity.name: gold_table(mapping, entity) for entity in mapping.entities}

    assert names == {"Building": "dev_catalog.precedents_gold.Building", "Storey": "dev_catalog.precedents_gold.Storey", "Beam": "dev_catalog.precedents_gold.Beam"}
    assert result.tables == names and result.written == {"Building": 4, "Storey": 4, "Beam": 12} and result.existing == {"Building": 0, "Storey": 0, "Beam": 0}
    assert "Beam: dev_catalog.precedents_gold.Beam, 12 rows written, 0 already there" in result.text()
    statements = spark.statements
    assert sum(1 for statement in statements if statement.startswith("CREATE TABLE IF NOT EXISTS `dev_catalog`.`precedents_gold`.`")) == 3
    links = [statement for statement in statements if "ADD COLUMNS" in statement]
    assert links == ["ALTER TABLE `dev_catalog`.`precedents_gold`.`Storey` ADD COLUMNS (`Building_id` STRING)", "ALTER TABLE `dev_catalog`.`precedents_gold`.`Beam` ADD COLUMNS (`Building_id` STRING)"]
    constraints = [statement for statement in statements if "ADD CONSTRAINT" in statement]
    assert constraints and all("`Beam`" in statement for statement in constraints)

    buildings = spark.tables[names["Building"]].rows
    storeys = spark.tables[names["Storey"]].rows
    beams = spark.tables[names["Beam"]].rows
    assert (len(buildings), len(storeys), len(beams)) == (4, 4, 12)
    assert {row["BHoM_Guid"] for row in buildings} >= {gold_id("Building", ["P-1", "Tower"])}
    assert all(row["Building_id"] in {item["BHoM_Guid"] for item in buildings} for row in storeys + beams) and all("Building_id" not in row for row in buildings)
    assert {row["TypicalMaterial"] for row in beams} == {"SteelHotRolled", "TimberGlulam"}
    assert next(row for row in storeys if row["Building_id"] == gold_id("Building", ["P-1", "Tower"]))["TypicalHeight"] == pytest.approx(3.9)

def test_gold_rows_read_back_as_the_same_objects(tmp_path: Path):
    """Checks that the rows of the gold Beam table read back, through rows_to_objects, as Beam objects equal to the ones the mapping built.

    Protects the round trip: what is written can be read back as BHoM objects.
    """
    spark, _ = written(tmp_path)
    mapping = the_mapping()
    beam = mapping.entity("Beam")
    expected = {item.id: item.instance for item in next(item for item in apply_mapping(silver_rows(), mapping).entities if item.entity.name == "Beam").objects}
    found = rows_to_objects(Beam, spark.tables["dev_catalog.precedents_gold.Beam"].rows, fields=beam.fields, keyed=True, key="BHoM_Guid")

    assert found == expected

def test_writing_again_adds_nothing_twice(tmp_path: Path):
    """Checks that a second write_gold finds every row already there, writes none, and does not add the parent column or the constraints again.

    Protects the engineer who runs the notebook twice: the same silver row stays one gold row.
    """
    spark, _ = written(tmp_path)
    before = len(spark.statements)
    again = write_gold(spark, TABLE, the_mapping())

    assert again.written == {"Building": 0, "Storey": 0, "Beam": 0} and again.existing == {"Building": 4, "Storey": 4, "Beam": 12}
    assert not [statement for statement in spark.statements[before:] if "ALTER TABLE" in statement]
    assert sum(len(table.rows) for name, table in spark.tables.items() if name != TABLE) == 20

def test_a_new_silver_row_is_added_and_the_others_are_left_alone(tmp_path: Path):
    """Checks that after a new element row appears in silver, writing again adds only the new beam, and that replace=True makes every table again.

    Protects the second run of a notebook after the silver table grew.
    """
    spark, _ = written(tmp_path)
    spark.tables[TABLE].rows.append({**silver_rows()[0], "family_type": "UB-9", "source_file": "extra.parquet"})
    again = write_gold(spark, TABLE, the_mapping())

    assert again.written == {"Building": 0, "Storey": 0, "Beam": 1} and again.existing["Beam"] == 12
    replaced = write_gold(spark, TABLE, the_mapping(), replace=True)
    assert replaced.written == {"Building": 4, "Storey": 4, "Beam": 13} and replaced.existing == {"Building": 0, "Storey": 0, "Beam": 0}
    assert any(statement.startswith("CREATE OR REPLACE TABLE") for statement in spark.statements)

def test_nothing_is_written_while_the_mapping_is_not_valid(tmp_path: Path):
    """Checks that write_gold raises GoldRefused with the report, runs no statement and writes no row, when the data has a value that does not fit.

    Protects gold from data the mapping cannot account for.
    """
    rows = silver_rows()
    rows[0]["structural_material"] = "unobtainium"
    spark = FakeSpark.silver(TABLE, rows, COLUMNS)

    with pytest.raises(GoldRefused, match="nothing was written to gold") as error:
        write_gold(spark, TABLE, the_mapping())

    assert not error.value.report.ok and "unobtainium" in str(error.value)
    assert spark.statements == [] and list(spark.tables) == [TABLE]

def test_the_mapping_file_is_found_by_the_table_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Checks that write_gold without a mapping reads the file of the table from the notebook's folder.

    Protects the call an engineer makes in a notebook: write_gold(spark, "catalog.schema.table").
    """
    save_mapping(the_mapping(), folder=tmp_path)
    monkeypatch.chdir(tmp_path)
    spark = FakeSpark.silver(TABLE, silver_rows(), COLUMNS)

    assert write_gold(spark, TABLE).written == {"Building": 4, "Storey": 4, "Beam": 12}

# ---------------------------------------------------------------- a DataFrame against a class

def test_a_dataframe_is_checked_against_a_class():
    """Checks that rows of a pandas-like frame and of a Spark-like frame are checked against Storey, that the good rows are counted, and that a bad row is reported with its position and message.

    Protects option 1: a table built straight from the columns of a class can be checked without making objects.
    """
    rows: list[dict[str, Any]] = [
        {"BHoM_Guid": "11111111-1111-4111-8111-111111111111", "Name": "ok", "TypicalHeight": 3.5},
        {"BHoM_Guid": "22222222-2222-4222-8222-222222222222", "Name": "bad", "TypicalHeight": "tall"},
        {"BHoM_Guid": "33333333-3333-4333-8333-333333333333", "Name": "nan", "TypicalHeight": float("nan")}]
    pandas_report = validate_dataframe(FakePandas(rows), Storey, BASE_SKIPPED)
    spark_report = validate_dataframe(FakeSpark.silver("a.b.c", copy.deepcopy(rows)).table("a.b.c"), Storey, BASE_SKIPPED)

    assert (pandas_report.rows, pandas_report.valid, len(pandas_report.problems), pandas_report.ok) == (3, 2, 1, False)
    assert pandas_report.problems[0].index == 1 and pandas_report.problems[0].key == "22222222-2222-4222-8222-222222222222" and "TypicalHeight" in pandas_report.problems[0].message
    assert pandas_report.text().startswith("Storey: 2 of 3 rows are valid\n  row 1 (22222222-2222-4222-8222-222222222222): ")
    assert (spark_report.rows, spark_report.valid, len(spark_report.problems)) == (3, 2, 1) and spark_report.problems[0].index == 1
    assert validate_dataframe(FakePandas(rows), Storey, BASE_SKIPPED, limit=1).ok
