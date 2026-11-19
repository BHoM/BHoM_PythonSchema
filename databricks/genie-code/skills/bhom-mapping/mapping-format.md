# The mapping file

One YAML file per silver table, named after the table, in a `bhom-mappings` folder of the tool: `<tool folder>/bhom-mappings/<catalog>.<schema>.<table>.yml`. `find_mapping(table)` finds it from a notebook's folder or any folder above it.

```yaml
version: 1
source: dev_catalog.precedents.elements_flat
gold_schema: dev_catalog.precedents_gold

entities:
  Building:
    class: bhom_schema.DataSchema_oM.Building.Building
    key: [project_number, model_name]
    fields: {Fragments: skip, CustomData: skip}
    columns:
      Name: {from: model_name}
      StoreysAboveGround: {from: levels_above_ground}
      StoreysBelowGround: {from: levels_below_ground, default: 0}
  Storey:
    class: bhom_schema.DataSchema_oM.Storey.Storey
    key: [project_number, model_name]
    parent: Building
    fields: {Fragments: skip, CustomData: skip}
    columns:
      TypicalHeight: {from: typical_level_gap, unit: mm}
  Beam:
    class: bhom_schema.DataSchema_oM.Elements.Beam.Beam
    key: [project_number, model_name, family_type]
    parent: Building
    fields: {Fragments: skip, CustomData: skip, MaterialDistribution: json}
    columns:
      TypicalMaterial:
        from: structural_material
        values: {Steel - hot rolled: SteelHotRolled, glulam: TimberGlulam}
      TypicalSize: {from: family_type}

unmapped:
  source_file: lineage back to the bronze Parquet file; stays in silver
```

## Keys

- `version`: always `1`.
- `source`: the full name of the silver table, `catalog.schema.table`. `gold_schema`: `catalog.schema`, where the gold tables go.
- `entities`: at least one. The name of an entity is letters, digits and underscores; it is also the name of its gold table.
- `unmapped`: silver columns with no BHoM home, each with the reason (not empty).

An entity has:

- `class`: the full path of a class of `bhom_schema`, such as `bhom_schema.DataSchema_oM.Storey.Storey`. Find the paths with `schema_overview()`.
- `key`: the silver columns that identify one object; rows with the same values are one object. A row with an empty key column is left out of that entity.
- `parent` (optional): the name of another entity. The parent's key columns must be part of this entity's `key`, and parents must not go round in a circle. Gold rows of a child carry a `<Parent>_id` column.
- `columns`: property of the class, mapped to a silver column. At least one.
- `fields` (optional): a decision for each field that has no column of its own.

A column (property) has:

- `from`: the silver column (required).
- `unit` (optional): the unit of the silver values. It must fit the quantity of the property (a length takes `mm`, `ft`, `m` and so on); a property with no quantity takes no unit.
- `values` (optional): a map from silver text to a member name of the property's enum. Only for an enum property. Texts that already are member names need no entry.
- `default` (optional): a single value used when the silver value is empty.

## Decisions (`fields`)

For a field that has no column of its own (another class, a list, `Any`): `skip` (not stored), `json` (stored as JSON text), `struct` (stored as a STRUCT of its own fields), `ref:<table>` (an id column pointing at another table), or the
long forms `{struct: {<field>: <decision>}}` and `{ref: <table>, column: <name>}`. Every BHoM class has `Fragments` and `CustomData`, which are normally `skip`. `describe_class(name)` lists the fields that need a decision.

## Rules that are checked when the file is read (`load_mapping`)

- A property is either mapped under `columns` or decided under `fields`, never both. A mapped property must have a column of its own. Every field with no column of its own must be decided.
- Every property and field exists in the class (a misspelling gets a suggestion). Every unit fits its quantity. Every enum member in `values` exists.
- A silver column is either used by an entity (in a `key` or as a `from`) or listed under `unmapped`, never both.
- All problems are reported at once, each with where it is (`entities.Storey.columns.TypicalHeight`).

## Rules that are checked against the rows (`validate_mapping`)

- Every column of the table is accounted for, and every column the mapping uses exists in the table.
- An enum text that is not a member and not in `values`; a value that is not a number under a `unit`; a BHoM class that refuses an object; two different values for one object (the first is used, and the conflict is reported).

## Units

Length: m, mm, cm, km, in, ft, yd. Area: m², mm², cm², km², in², ft² (also written m2, ft2). Volume: m³, mm³, cm³, l, in³, ft³. Mass: kg, g, t, lb. Force: N, kN, MN, lbf, kip. Pressure: Pa, kPa, MPa, GPa, psi, ksi.
Angle: rad, deg. Time: s, min, h. A property with another quantity takes no unit yet.

## Gold tables

`write_gold` makes `<gold_schema>.<Entity>` for each entity, parents first. Ids are made from the entity and its key values, so writing again does not add a row twice.
