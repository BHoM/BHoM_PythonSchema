"""The mapping of a silver table to BHoM classes: the rules a mapping file must meet, how a file is found, read and written, and the units it may name.

They run against the real classes of the DataSchema_oM assembly that the package carries (Building, Storey, Beam, ExampleObject).
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from bhom_schema.mapping import MappingError, find_mapping, load_mapping, mapping_path, parse_mapping, save_mapping
from bhom_schema.mapping import units
from bhom_schema.mapping.model import mapping_to_data

TABLE = "dev_catalog.precedents.elements_flat"
BASE = {"Fragments": "skip", "CustomData": "skip"}

def example() -> dict[str, Any]:
    """Returns the data of a complete, valid mapping: a Building, a Storey that belongs to it, and a Beam with an enum value map, a Json field and an unmapped column."""
    return {
        "version": 1,
        "source": TABLE,
        "gold_schema": "dev_catalog.precedents_gold",
        "entities": {
            "Building": {
                "class": "bhom_schema.DataSchema_oM.Building.Building",
                "key": ["project_number", "model_name"],
                "fields": dict(BASE),
                "columns": {"Name": {"from": "model_name"}, "StoreysAboveGround": {"from": "levels_above_ground"}, "StoreysBelowGround": {"from": "levels_below_ground", "default": 0}},
            },
            "Storey": {
                "class": "bhom_schema.DataSchema_oM.Storey.Storey",
                "key": ["project_number", "model_name"],
                "parent": "Building",
                "fields": dict(BASE),
                "columns": {"TypicalHeight": {"from": "typical_level_gap", "unit": "mm"}},
            },
            "Beam": {
                "class": "bhom_schema.DataSchema_oM.Elements.Beam.Beam",
                "key": ["project_number", "model_name", "family_type"],
                "parent": "Building",
                "fields": {**BASE, "MaterialDistribution": "json"},
                "columns": {
                    "TypicalMaterial": {"from": "structural_material", "values": {"Steel - hot rolled": "SteelHotRolled", "glulam": "TimberGlulam"}},
                    "TypicalSize": {"from": "family_type"},
                },
            },
        },
        "unmapped": {"source_file": "lineage back to the bronze Parquet file; stays in silver"},
    }

def problems_of(data: dict[str, Any]) -> list[str]:
    """Parses the data, expects it to be refused, and returns the problems."""
    with pytest.raises(MappingError) as error:
        parse_mapping(data)

    return list(error.value.problems)

def has(problems: list[str], *parts: str) -> bool:
    """Tells whether one problem contains all the parts, so a test names the place and the reason but not the whole sentence."""
    return any(all(part in problem for part in parts) for problem in problems)

# ---------------------------------------------------------------- the valid mapping

def test_a_complete_mapping_loads_into_typed_entities():
    """Checks that the example mapping becomes three entities with their classes, keys, parent, decisions and columns, and the unmapped column.

    Protects the shape that validate_mapping and write_gold will read.
    """
    mapping = parse_mapping(example())

    assert [entity.name for entity in mapping.entities] == ["Building", "Storey", "Beam"]
    storey = mapping.entity("Storey")
    assert (storey.model.__name__, storey.parent, storey.key) == ("Storey", "Building", ("project_number", "model_name"))
    assert [(column.property, column.source, column.unit) for column in storey.columns] == [("TypicalHeight", "typical_level_gap", "mm")]
    beam = mapping.entity("Beam")
    assert beam.columns[0].values == {"Steel - hot rolled": "SteelHotRolled", "glulam": "TimberGlulam"}
    assert type(beam.fields["MaterialDistribution"]).__name__ == "Json"
    building = mapping.entity("Building")
    assert [(column.property, column.has_default, column.default) for column in building.columns] == [
        ("Name", False, None), ("StoreysAboveGround", False, None), ("StoreysBelowGround", True, 0)]
    assert mapping.unmapped == {"source_file": "lineage back to the bronze Parquet file; stays in silver"}

def test_writing_the_data_back_gives_the_same_mapping():
    """Checks that a mapping turned back into data and parsed again equals the first one, and that the data is what was read.

    Protects the file that a person or Genie Code edits from drifting when it is saved.
    """
    data = example()
    mapping = parse_mapping(data)

    assert mapping_to_data(mapping) == data
    assert parse_mapping(mapping_to_data(mapping)) == mapping

def test_every_kind_of_decision_survives_a_round_trip():
    """Checks that skip, json, struct (with and without inner decisions) and ref (with and without a column) are read and written back unchanged.

    Protects the decisions of ExampleObject, which has a class, a list of classes and fields of other shapes.
    """
    data = example()
    data["entities"] = {"Example": {
        "class": "bhom_schema.DataSchema_oM.ExampleObject.ExampleObject",
        "key": ["name"],
        "fields": {**BASE, "MainGrid": "ref:dev_catalog.precedents_gold.grid", "Storeys": {"struct": dict(BASE)}, "Anything": {"ref": "x.y.z", "column": "AnythingId"},
                   "TotalsByStatus": "json", "Pair": "json", "Extra": "skip"},
        "columns": {"Name": {"from": "name"}},
    }}
    mapping = parse_mapping(data)

    assert mapping_to_data(mapping) == data
    assert type(mapping.entity("Example").fields["Storeys"]).__name__ == "Struct"

# ---------------------------------------------------------------- the rules

def test_a_wrong_version_table_or_key_is_refused_with_a_hint():
    """Checks the header: the version, the full name of the silver table, the schema of the gold tables, and an unknown key with the closest key as a hint.

    Protects the file name that find_mapping depends on (the table name) and the typos a person makes.
    """
    data = example()
    data.update({"version": 2, "source": "elements_flat", "gold_schema": "gold", "entites": {}})
    problems = problems_of(data)

    assert has(problems, "version must be 1")
    assert has(problems, "source must be the full name", "catalog.schema.table")
    assert has(problems, "gold_schema must be catalog.schema")
    assert has(problems, "unknown key 'entites'", "did you mean 'entities'")

def test_the_class_must_be_a_real_class_of_bhom_schema():
    """Checks that a class outside bhom_schema, one that does not exist, one that is not a BHoM class and a text that is no path are each refused with a message of their own.

    Protects the mapping from importing and running anything but the schema classes.
    """
    data = example()
    classes = {"Building": "os.path.join", "Storey": "bhom_schema.DataSchema_oM.Nothing.Nothing", "Beam": "bhom_schema.mapping.units.FACTORS"}
    for name, path in classes.items():
        data["entities"][name]["class"] = path
    problems = problems_of(data)

    assert has(problems, "entities.Building.class", "os.path.join is not a class of bhom_schema")
    assert has(problems, "entities.Storey.class", "was not found in bhom_schema")
    assert has(problems, "entities.Beam.class", "is not a BHoM class")
    data["entities"]["Building"]["class"] = "Building"
    assert has(problems_of(data), "entities.Building.class", "must be the full path of a class")

def test_properties_are_checked_against_the_class():
    """Checks that an unknown property gets a hint, that a property both mapped and decided is refused, and that a mapped property with no column of its own is refused.

    Protects the rule that a property is either filled from a silver column or decided under fields, never both.
    """
    data = example()
    data["entities"]["Storey"]["columns"]["TypicalHeigth"] = {"from": "x"}
    data["entities"]["Storey"]["fields"]["TypicalHeight"] = "skip"
    data["entities"]["Storey"]["fields"]["Nothing"] = "skip"
    problems = problems_of(data)

    assert has(problems, "entities.Storey.columns.TypicalHeigth", "no property 'TypicalHeigth'", "did you mean 'TypicalHeight'")
    assert has(problems, "TypicalHeight is both mapped to a column and decided")
    assert has(problems, "entities.Storey.fields.Nothing", "no field 'Nothing'")

    data = example()
    data["entities"] = {"Example": {
        "class": "bhom_schema.DataSchema_oM.ExampleObject.ExampleObject", "key": ["name"],
        "fields": {**BASE, "Storeys": "struct", "Anything": "json", "TotalsByStatus": "json", "Pair": "json", "Extra": "skip"},
        "columns": {"Name": {"from": "name"}, "MainGrid": {"from": "grid"}},
    }}
    assert has(problems_of(data), "entities.Example.columns.MainGrid", "no column of its own", "decide it under fields")

def test_a_field_with_no_decision_is_listed():
    """Checks that the fields that still need a decision (Fragments and CustomData of every BHoM class) are named with their types, in one message.

    Protects the rule that gold tables are never made with a field left out without anyone saying so.
    """
    data = example()
    data["entities"]["Storey"]["fields"] = {}
    problems = problems_of(data)

    assert has(problems, "entities.Storey.fields", "still needs a decision", "Fragments", "CustomData")

def test_a_decision_must_be_one_the_tables_understand():
    """Checks that a decision that is not skip, json, struct or ref is refused, as is a ref with no table, and that an invalid inner decision of a struct is found.

    Protects the decisions of bhom_schema.tables from being given a text they do not know.
    """
    data = example()
    data["entities"]["Beam"]["fields"]["MaterialDistribution"] = "keep"
    data["entities"]["Storey"]["fields"]["Fragments"] = "ref:"
    problems = problems_of(data)

    assert has(problems, "entities.Beam.fields.MaterialDistribution must be skip, json, struct")
    assert has(problems, "entities.Storey.fields.Fragments must be skip, json, struct")

def test_a_unit_must_fit_the_quantity_of_the_property():
    """Checks that a unit of another quantity, an unknown unit, and a unit on a property with no quantity are refused, and that a unit written without a superscript is accepted.

    Protects the conversion of Revit lengths (feet, millimetres) to the unit of the BHoM property.
    """
    data = example()
    data["entities"]["Storey"]["columns"]["TypicalHeight"]["unit"] = "kg"
    data["entities"]["Storey"]["columns"]["NonRoofArea"] = {"from": "area", "unit": "furlong"}
    data["entities"]["Building"]["columns"]["Name"]["unit"] = "m"
    problems = problems_of(data)

    assert has(problems, "TypicalHeight", "'kg' is not a unit of Length")
    assert has(problems, "NonRoofArea", "'furlong' is not a unit of Area")
    assert has(problems, "entities.Building.columns.Name", "has no quantity, so it takes no unit")

    data = example()
    data["entities"]["Storey"]["columns"]["NonRoofArea"] = {"from": "area", "unit": "ft2"}
    assert parse_mapping(data).entity("Storey").columns[1].unit == "ft2"

def test_values_must_name_members_of_the_enum():
    """Checks that a value map on a property that is not an enum is refused, and that a member that does not exist gets the closest member as a hint.

    Protects the value maps that turn free text such as "Steel - hot rolled" into StructuralMaterial members.
    """
    data = example()
    data["entities"]["Building"]["columns"]["Name"]["values"] = {"a": "b"}
    data["entities"]["Beam"]["columns"]["TypicalMaterial"]["values"] = {"Steel": "SteelHotRolld"}
    problems = problems_of(data)

    assert has(problems, "entities.Building.columns.Name", "Name is not an enum")
    assert has(problems, "TypicalMaterial.values.Steel", "'SteelHotRolld' is not a member of StructuralMaterial", "did you mean 'SteelHotRolled'")

def test_a_column_needs_a_source_and_only_the_known_keys():
    """Checks that a column with no `from`, one with an unknown key, and one with a default that is a list are each refused.

    Protects the file from keys that would be silently ignored.
    """
    data = example()
    data["entities"]["Storey"]["columns"] = {"TypicalHeight": {"unit": "mm"}, "NonRoofArea": {"from": "a", "units": "m²"}, "RoofArea": {"from": "b", "default": [1]}}
    problems = problems_of(data)

    assert has(problems, "TypicalHeight", "from must name the silver column")
    assert has(problems, "NonRoofArea", "unknown key 'units'", "did you mean 'unit'")
    assert has(problems, "RoofArea", "default must be a single value")

def test_parents_must_exist_share_their_key_and_not_go_round():
    """Checks that a parent that does not exist, a parent that is the entity itself, a key that lacks the parent's key columns, and a circle of parents are each refused.

    Protects the link between gold tables, which is made through the shared key columns.
    """
    data = example()
    data["entities"]["Storey"]["parent"] = "Floor"
    data["entities"]["Beam"]["key"] = ["family_type"]
    assert has(problems_of(data), "entities.Storey.parent", "no entity 'Floor'")
    assert has(problems_of(data), "entities.Beam.parent", "must include the key columns of Building", "model_name", "project_number")

    data = example()
    data["entities"]["Storey"]["parent"] = "Storey"
    assert has(problems_of(data), "an entity cannot be its own parent")

    data = example()
    data["entities"]["Building"]["parent"] = "Storey"
    assert has(problems_of(data), "go round in a circle")

def test_a_column_cannot_be_both_used_and_unmapped():
    """Checks that a silver column listed under unmapped and used by an entity is refused, and that an unmapped column must say why.

    Protects the rule that every silver column is accounted for once, as used or as unmapped, and never both.
    """
    data = example()
    data["unmapped"]["model_name"] = "no BHoM home"
    data["unmapped"]["notes"] = ""
    problems = problems_of(data)

    assert has(problems, "unmapped.model_name", "listed as unmapped but an entity uses it")
    assert has(problems, "unmapped.notes", "must say why")

def test_all_the_problems_are_reported_at_once():
    """Checks that a mapping with several mistakes in different entities raises one error that lists them all, with the count in its message.

    Protects the loop of Genie Code and the engineer: one run shows everything to fix.
    """
    data = example()
    data["version"] = 3
    data["entities"]["Storey"]["columns"]["TypicalHeight"]["unit"] = "kg"
    data["entities"]["Beam"]["parent"] = "Nobody"
    with pytest.raises(MappingError) as error:
        parse_mapping(data)

    assert len(error.value.problems) == 3
    assert str(error.value).startswith("the mapping has 3 problems:\n  - ")

# ---------------------------------------------------------------- the columns of the table

def test_new_and_missing_columns_of_the_table_are_found():
    """Checks that unaccounted lists the columns of a table that the mapping does not know (in the order given), and missing lists the ones the mapping uses that the table lost.

    Protects the check that a mapping has not fallen behind its silver table.
    """
    mapping = parse_mapping(example())
    columns = ["project_number", "model_name", "levels_above_ground", "brand_new", "source_file", "another_new"]

    assert mapping.unaccounted(columns) == ["brand_new", "another_new"]
    assert mapping.missing(columns) == ["family_type", "levels_below_ground", "structural_material", "typical_level_gap"]
    assert mapping.used_columns() >= {"project_number", "family_type", "typical_level_gap"}
    assert "source_file" in mapping.accounted_columns() and "source_file" not in mapping.used_columns()

# ---------------------------------------------------------------- the units

def test_units_convert_to_the_unit_of_the_property():
    """Checks the conversion factors of a length, an area, a volume and a force, a unit written without its superscript, and the message for a quantity or unit that is not known.

    Protects the numbers: millimetres to metres, square feet to square metres.
    """
    assert units.factor("Length", "mm", "m") == pytest.approx(0.001)
    assert units.factor("Length", "ft", "m") == pytest.approx(0.3048)
    assert units.factor("Length", "m", "mm") == pytest.approx(1000)
    assert units.factor("Area", "ft2", "m²") == pytest.approx(0.09290304)
    assert units.factor("Volume", "l", "m³") == pytest.approx(0.001)
    assert units.factor("Force", "kip", "kN") == pytest.approx(4.4482216)
    assert units.factor("Length", "m", "m") == 1
    assert "Length" in units.FACTORS and units.units_of("Length")[:2] == ["m", "mm"] and units.units_of("Colour") == []

    with pytest.raises(ValueError, match="'in²' is not a unit of Length; use one of m, mm"):
        units.factor("Length", "in2", "m")

    with pytest.raises(ValueError, match="no unit conversion is known for the quantity Colour"):
        units.factor("Colour", "a", "b")

# ---------------------------------------------------------------- finding, reading and writing the file

def tool_folder(root: Path) -> Path:
    """Makes a tool folder with a notebook subfolder and the mapping of the example table in its bhom-mappings folder, and returns the tool folder."""
    tool = root / "Users" / "someone" / "precedent-tool"
    (tool / "experiments" / "deep").mkdir(parents=True)
    save_mapping(parse_mapping(example()), folder=tool)
    return tool

def test_the_mapping_is_found_from_the_tool_folder_and_from_below_it(tmp_path: Path):
    """Checks that find_mapping finds the file from the tool's own folder and from subfolders at any depth, and returns None from a folder that is not under the tool or for another table.

    Protects the rule that every notebook of a tool uses one mapping per table without a copy.
    """
    tool = tool_folder(tmp_path)
    expected = (tool / "bhom-mappings" / f"{TABLE}.yml").resolve()

    assert find_mapping(TABLE, tool) == expected
    assert find_mapping(TABLE, tool / "experiments") == expected
    assert find_mapping(TABLE, tool / "experiments" / "deep") == expected
    assert find_mapping(TABLE, tmp_path / "Users" / "someone") is None
    assert find_mapping("dev_catalog.precedents.other", tool) is None

def test_the_nearest_mapping_wins(tmp_path: Path):
    """Checks that a mapping kept in a subfolder is found before the one of the tool above it.

    Protects an engineer who deliberately keeps another mapping for an experiment.
    """
    tool = tool_folder(tmp_path)
    nested = tool / "experiments"
    save_mapping(parse_mapping(example()), folder=nested)

    assert find_mapping(TABLE, nested / "deep") == (nested / "bhom-mappings" / f"{TABLE}.yml").resolve()

def test_the_current_folder_is_where_a_notebook_starts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Checks that find_mapping and load_mapping start from the current folder, which is a notebook's own folder on Databricks, when no start is given.

    Protects the call an engineer writes in a notebook: load_mapping("catalog.schema.table").
    """
    tool = tool_folder(tmp_path)
    monkeypatch.chdir(tool / "experiments")

    assert find_mapping(TABLE) == (tool / "bhom-mappings" / f"{TABLE}.yml").resolve()
    assert load_mapping(TABLE).source == TABLE
    assert mapping_path(TABLE) == Path(tool / "experiments").resolve() / "bhom-mappings" / f"{TABLE}.yml"

def test_a_mapping_is_loaded_by_table_name_or_by_path(tmp_path: Path):
    """Checks that load_mapping reads a file by table name (searching upwards from a start) and by path, and that a missing file or a name that is no table name is a clear error.

    Protects both ways of calling it, and the messages the engineer or Genie Code sees.
    """
    tool = tool_folder(tmp_path)
    path = tool / "bhom-mappings" / f"{TABLE}.yml"

    assert load_mapping(TABLE, start=tool / "experiments") == load_mapping(path) == load_mapping(str(path))

    with pytest.raises(FileNotFoundError, match="no bhom-mappings/dev_catalog.precedents.other.yml in"):
        load_mapping("dev_catalog.precedents.other", start=tool)

    with pytest.raises(ValueError, match="not the full name of a table"):
        load_mapping("elements_flat", start=tool)

def test_saving_writes_the_file_in_the_mappings_folder(tmp_path: Path):
    """Checks that save_mapping without a path creates bhom-mappings/<table>.yml in the folder, writes plain YAML that loads back equal, and leaves no temporary file.

    Protects the file the engineer reviews as a diff and keeps in version control.
    """
    mapping = parse_mapping(example())
    path = save_mapping(mapping, folder=tmp_path / "new-tool")

    assert path == tmp_path / "new-tool" / "bhom-mappings" / f"{TABLE}.yml"
    assert sorted(item.name for item in path.parent.iterdir()) == [f"{TABLE}.yml"]
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == example()
    assert load_mapping(path) == mapping
    assert path.read_text(encoding="utf-8").startswith("version: 1\nsource: dev_catalog.precedents.elements_flat\n")

def test_a_mapping_that_would_not_load_is_never_saved(tmp_path: Path):
    """Checks that save_mapping refuses a mapping that breaks a rule, raises before writing, and keeps the file that was there.

    Protects a good mapping file from being replaced by a bad one.
    """
    mapping = parse_mapping(example())
    path = save_mapping(mapping, folder=tmp_path)
    before = path.read_text(encoding="utf-8")
    storey = mapping.entity("Storey")
    broken = replace(mapping, entities=(*mapping.entities[:1], replace(storey, parent="Nobody"), *mapping.entities[2:]))

    with pytest.raises(MappingError, match="no entity 'Nobody'"):
        save_mapping(broken, folder=tmp_path)

    assert path.read_text(encoding="utf-8") == before
    assert not list(path.parent.glob("*.tmp"))

def test_an_edited_file_that_breaks_a_rule_is_reported_with_all_its_problems(tmp_path: Path):
    """Checks that a file a person edited by hand, with a bad unit and an unknown key, raises MappingError from load_mapping with both problems, and that a file that is not a mapping is refused.

    Protects the loop in which Genie Code edits the file and runs the check.
    """
    data = example()
    data["entities"]["Storey"]["columns"]["TypicalHeight"]["unit"] = "kg"
    data["extra"] = 1
    path = tmp_path / "edited.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(MappingError) as error:
        load_mapping(path)

    assert len(error.value.problems) == 2

    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(MappingError, match="the mapping must be a mapping"):
        load_mapping(path)

def test_a_missing_yaml_package_is_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Checks that reading or writing a file without PyYAML raises ImportError that names the extra to install.

    Protects an engineer whose environment has only the base package.
    """
    mapping = parse_mapping(example())
    monkeypatch.setitem(sys.modules, "yaml", None)

    with pytest.raises(ImportError, match=r"pip install bhom-schema\[mapping\]"):
        save_mapping(mapping, folder=tmp_path)
