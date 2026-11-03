# Table helpers: plan

Helpers in the `bhom-schema` package that help a user turn **one schema class** into **one Databricks (Spark SQL / Delta) table**, and read its rows back as objects of that class.

The user decides which tables exist and how they link. The helpers never walk a class hierarchy and never create tables on their own. They answer questions about one class ("what would its table look like?", "which of its fields need a table of their own?") and do the mechanical work for the table the user has chosen.

This replaces the whole-hierarchy helper (`create_tables_sql(LineLike, PREFIX)` creating every held class) in the Databricks section of [Alpha-Releases-Plan.md](Alpha-Releases-Plan.md). That helper is a sketch to prove the idea, not the API.

## Principles

1. **One class in, one table out.** Every helper takes a single model class. Nothing recurses.
2. **Primitives are automatic, everything else is explicit.** A field whose type is a primitive (including lists, sets and dicts of primitives) gets a column. A field of any other type (another schema class, an interface, `Any`, a tuple, `Color`) is never mapped silently: the helper raises an error that names the field and the choices, until the user says what to do with it (see [Custom-typed fields](#custom-typed-fields)).
3. **Column names are the BHoM field names.** No renaming layer. The one exception is the column that holds the id of a row in another table, which is named `<Field>_id` unless the user overrides it.
4. **No structs.** A class-typed field is never stored as a nested column. It is an id pointing at a row in another table, or it is skipped, or it is stored as JSON text, as the user chooses.
5. **Pure Python at the core.** Nothing outside the optional Spark layer imports `pyspark`, so everything runs and is tested without a cluster. Spark is only needed to execute the SQL or to build a DataFrame.
6. **The user can see what will happen.** Every helper that produces SQL returns a string, and a `describe` helper shows the same decisions as a table before anything runs.

## What a user does with them

```python
from bhom_schema.FixtureAlpha_oM import LineLike
from bhom_schema.tables import Ref, create_table_sql, custom_fields

# 1. Which fields need a decision?
custom_fields(LineLike)
# {'Start': PointLike, 'End': PointLike}

# 2. Make the decision, get the SQL
sql = create_table_sql(
    LineLike,
    "main.default.LineLike",
    fields={"Start": Ref("main.default.PointLike"), "End": Ref("main.default.PointLike")},
)
spark.sql(sql)
```

Before step 2 is answered, `create_table_sql(LineLike, "main.default.LineLike")` raises:

```
LineLike has 2 fields of a custom type, so they have no column until you decide how to store them:
  Start: PointLike
  End: PointLike
Pass fields={"Start": ...} with one of:
  Ref("catalog.schema.Table")  an id column that points at a row of that table
  Json()                       the object as JSON text in a STRING column
  Skip()                       no column; the field keeps its default when a row is read
```

## Type mapping

The mapping is a table in code (`COLUMN_TYPES`), so it is easy to review and to extend. The generator already records the original C# type of a field in a `ClrType` marker when Python cannot say it (`long`, `float`, `char`, `short`, `byte`), and the helpers read it.

| Python annotation | C# type | Column type | Notes |
|---|---|---|---|
| `bool` | `bool` | `BOOLEAN` | |
| `int` | `int` | `INT` | Python `int` is unbounded, so a value outside 32 bits fails validation when the row is read back, not when it is written |
| `Annotated[int, ClrType('long')]` | `long` | `BIGINT` | `short` is `SMALLINT`, `byte` is `TINYINT` |
| `float` | `double` | `DOUBLE` | |
| `Annotated[float, ClrType('float')]` | `float` | `FLOAT` | |
| `str` | `string` | `STRING` | |
| `Annotated[str, ClrType('char')]` | `char` | `STRING` | A comment on the column says it holds one character |
| `Decimal` | `decimal` | `DECIMAL(38,10)` | C# `decimal` has 28 digits; Spark allows 38 in total. Override with `types={"Cost": "DECIMAL(18,2)"}` |
| `datetime` | `DateTime` | `TIMESTAMP_NTZ` | BHoM DateTimes carry no time zone. Needs Databricks Runtime 13.3 or later |
| `date` | `DateOnly` | `DATE` | |
| `timedelta` | `TimeSpan` | `DOUBLE` | Seconds. Delta tables cannot hold interval columns. The column comment says "seconds" and `to_row` / `from_row` convert |
| `UUID` | `Guid` | `STRING` | Lower-case with dashes, as `str(uuid)` writes it |
| a `BHoMEnum` | `enum` | `STRING` | The member name as BHoM writes it. A comment lists the allowed names, and `constraints_sql` can add a `CHECK` |
| a `BHoMFlags` | `[Flags] enum` | `STRING` | Names joined by `", "`, as BHoM writes them |
| `list[X]`, `set[X]` | `List<X>`, `X[]`, `HashSet<X>`, `IEnumerable<X>` | `ARRAY<X>` | X must itself be a primitive. A `set` loses its order in the table, which does not matter |
| `list[list[X]]` | `X[][]` | `ARRAY<ARRAY<X>>` | |
| `dict[str, X]` | `Dictionary<string, X>` | `MAP<STRING, X>` | X must be a primitive. Other key types are custom |
| `X \| None` | nullable `X` | same as `X`, nullable | Every column is nullable except the key |

Everything else is a [custom-typed field](#custom-typed-fields): another schema class, an interface or `Polymorphic[...]`, `Any`, `tuple[...]`, `Color`, a list of classes, a dict with a non-string key or a non-primitive value, `Callable`, `System.Type`.

`describe` and `create_table_sql` also write the field's `description` (from the C# XML summary) as the column `COMMENT`, so the table documents itself in Unity Catalog.

## The key column

A table needs an id for other tables to point at. Two cases:

- The class derives from `BHoMObject`: it already has `BHoM_Guid`, so that column is the key and nothing is added.
- It does not (`PointLike`, `LineLike`): the helper adds `_id STRING NOT NULL`.

`create_table_sql(..., key="_id")` is the default; `key="BHoM_Guid"` or any other field name uses that field; `key=None` adds no key. A key is only informational in Unity Catalog (see `constraints_sql`), so the helper does not claim uniqueness.

## Custom-typed fields

`custom_fields(model)` returns `{field name: type}` for every field that has no automatic column. For each one the user passes a decision in `fields=`:

| Decision | Column | Reading a row | Use when |
|---|---|---|---|
| `Ref(table, column=None)` | `<Field>_id STRING` (or `column`) | `from_row` takes the object from `held={"Start": point}` | The field is a class that has, or will have, its own table |
| `Json()` | `<Field> STRING`, the JSON the schema writes | validated back into the field's type | A one-off or deeply nested value that does not deserve a table: `Any`, `CustomData`, a tuple |
| `Skip()` | none | the field keeps its default | `Fragments`, or anything the table does not need |

`Ref` has no second argument for lists. A list of classes (`Collections.Points`) is a one-to-many link, and it needs a table of its own holding the parent id and the position. That is the `child_table_sql` helper below, so the user still chooses it, and the parent class gets `Skip()` for that field.

The helpers do not offer a struct decision. If the team ever wants one, it is a fourth decision class, added without changing the others.

## The helpers

All live in one public module, `bhom_schema.tables`. Names are final only after the open questions below are answered.

### Inspect

| Helper | Returns | Purpose |
|---|---|---|
| `describe(model, fields=None, key="_id")` | `list[ColumnInfo]` | One entry per column the table would have: name, column type, nullable, comment, the Python field it comes from and the decision that produced it (`primitive`, `ref`, `json`, `key`). Printed as a table in a notebook, so the user sees the table before creating it. Does not raise for undecided fields; it lists them with the decision `undecided` |
| `custom_fields(model)` | `dict[str, type]` | The fields that need a decision, with their Python types. For a class-typed field the type is the schema class, so the user knows which other table to create next |
| `column_type(annotation)` | `str` | The column type of one annotation. Raises `UnmappedType` for a custom one. The building block of the rest |

### Create and change the table

| Helper | Returns | Purpose |
|---|---|---|
| `create_table_sql(model, table, *, fields=None, key="_id", types=None, replace=False)` | `str` | One `CREATE TABLE IF NOT EXISTS table (...) USING DELTA`, with column comments, a table comment (the class summary) and `TBLPROPERTIES ('bhom.type' = 'BH.oM.FixtureAlpha.LineLike', 'bhom.schema_version' = '...')`. `replace=True` gives `CREATE OR REPLACE TABLE`. `types` overrides the column type of a field |
| `add_columns_sql(model, table, existing, *, fields=None, types=None)` | `str` or `None` | Given the existing column names, the `ALTER TABLE ... ADD COLUMNS (...)` for the ones the class has and the table lacks. For when a new alpha adds a property to a class. `None` when the table is complete |
| `constraints_sql(model, table, *, fields=None, key="_id", checks=True)` | `list[str]` | Statements for the informational primary key, a foreign key per `Ref` (`ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY (Start_id) REFERENCES main.default.PointLike`), and a `CHECK` per enum column listing its allowed names. Separate from `create_table_sql` because the referenced table must exist first and the user decides whether to add them |
| `child_table_sql(parent, field, table, *, parent_table, child_table=None)` | `str` | The table for a list of classes: `<parent>_id`, `Position`, and either the id of a row in the child table or, with `child_table=None`, nothing else for a list of primitives. The one helper that takes two classes, and it only describes the link |

### Rows to objects and back

| Helper | Returns | Purpose |
|---|---|---|
| `to_row(obj, *, fields=None, key="_id", ids=None)` | `dict` | One object as a dict with the table's column names. Applies the conversions (`UUID` and enums to text, `timedelta` to seconds, `Json` fields to JSON text). `ids={"Start": "abc"}` fills the `Ref` columns; the user got those ids from the rows of the other tables. The key is `obj.BHoM_Guid` when the key is that field, otherwise `uuid4().hex` unless `ids` or the call gives one |
| `from_row(model, row, *, fields=None, held=None)` | object | The reverse, for one row. `held={"Start": point}` supplies the objects of `Ref` fields, since the helper does not fetch them. A `Ref` field with no entry in `held` keeps its default and `from_row` says so in a warning, not silently |
| `rows_to_objects(model, rows, *, fields=None, held=None, errors="raise")` | `list` or `(list, list[RowError])` | `from_row` over many rows. `errors="collect"` returns the valid objects and a `RowError(index, key, message)` per bad row, so one bad row in a million does not hide the rest. `held` is `{field: {id: object}}` here |
| `ddl_schema(model, *, fields=None, key="_id")` | `str` | The columns as a DDL string for `spark.createDataFrame(rows, schema=...)`, always the same columns `create_table_sql` makes |

### Check an existing table against a class

The team will have tables that exist before the helpers do, and tables written by an older alpha. These two helpers answer "will this table read as this class?" without reading the whole table.

| Helper | Returns | Purpose |
|---|---|---|
| `check_table(model, columns, *, fields=None, key="_id")` | `TableCheck` | `columns` is `{name: type}` from `DESCRIBE TABLE` or `df.dtypes`. Reports `missing` (fields with no column and no default), `extra` (columns the class does not know), `mismatched` (column has another type than the class expects) and `undecided` fields. `TableCheck.ok` and a readable `str()` |
| `example_row(model, *, fields=None)` | `dict` | A row with the class's defaults, for a quick `INSERT` or `createDataFrame` smoke test |

### Spark layer (optional)

Imported separately, `from bhom_schema.tables.spark import ...`, and `pyspark` is imported inside the functions, so the core module never needs it. Databricks always has it.

| Helper | Purpose |
|---|---|
| `create_table(spark, model, table, **options)` | `spark.sql(create_table_sql(...))` and return the SQL it ran |
| `write_objects(spark, objects, table, *, fields=None, key="_id", ids=None)` | `to_row` over the objects, `createDataFrame` with `ddl_schema`, append to the table |
| `read_objects(spark, model, table, *, fields=None, held=None, where=None, limit=None)` | Query the table (optionally filtered) and run `rows_to_objects` over the rows |
| `fetch_by_ids(spark, table, ids, *, key="_id", batch=5000)` | The rows of another table by id, in batches. What the user calls to get the `held` objects, with `rows_to_objects` on the result. Walking from one table to another stays a visible step in the user's code |

The user composes the multi-table read themselves, one table at a time:

```python
points = read_objects(spark, PointLike, "main.default.PointLike", where="...")
lines = read_objects(spark, LineLike, "main.default.LineLike", limit=1000,
                     fields={"Start": Ref("main.default.PointLike"), "End": Ref("main.default.PointLike")},
                     held={"Start": points_by_id, "End": points_by_id})
```

## Where the code goes

The generator treats every module under `src/bhom_schema` as a generated class, except `_support`, `__init__.py` and `_version.py`. A new `bhom_schema/tables/` package would be read as schema classes, so one of these has to happen:

1. Put it in `src/bhom_schema/_support/tables/` and re-export it from a public place. Zero generator changes, but `_support` is meant to be private, and a user would import from `bhom_schema._support.tables`.
2. Add `tables` to the skip lists in `.ci/generation/py2cs/reader.py` (lines 254, 426, 639) and `ci.py` (line 48), next to `_support`. The public path is `bhom_schema.tables`. **Recommended**: it is a handful of lines, with a test that a module under `tables` is never listed as a class.

Either way the package stays one wheel. `pydantic` is the only dependency of the core module. `pyspark` is not added to `dependencies`; the Spark layer documents that it needs the Databricks runtime or `pip install pyspark`. Pyright runs on the package, so the new code is typed, and its `import pyspark` goes inside the functions with a `TYPE_CHECKING` stub, because the wheel has no `pyspark` stubs in CI.

## Build order

Each step is mergeable alone, and the Databricks guide section is rewritten when step 4 lands.

1. **Core mapping and inspection.** `column_type`, `custom_fields`, `describe`, `UnmappedType` with the readable error, the `Ref` / `Json` / `Skip` decisions, and the generator skip. Tests: one per row of the type mapping above, run against the real fixture classes (`Scalars` covers `datetime`, `UUID`, `Decimal`, `timedelta`, `char`; `Collections` covers lists, sets, dicts, tuples; `Beam` covers enums, `Quantity` and `ClrType('long')`; `LineLike` covers `Ref`).
2. **DDL.** `create_table_sql`, `add_columns_sql`, `constraints_sql`. Tests compare the SQL text for `LineLike`, `PointLike`, `Scalars`, `Beam`, and the error text for an undecided field.
3. **Rows.** `to_row`, `from_row`, `rows_to_objects`, `ddl_schema`, `example_row`. The test that matters most is the round trip: for every fixture class, `from_row(to_row(obj))` equals `obj`, including `Json` fields and the `Ref` ids.
4. **Checks and Spark layer.** `check_table` with a fake `DESCRIBE` output, then the Spark functions with a stub `spark` that records the SQL. The Databricks notebook in the guide is the only test that needs a real workspace, run by hand: create the two tables, write 10 `LineLike` objects, read them back and compare.
5. **Child tables.** `child_table_sql` for a list of classes, after the team has shown they need one.

After every step: `python -m pytest`, `python -m pyright`, `python -m py2cs verify --package src/bhom_schema` (to prove the skip works and nothing in `tables` is taken for a schema class), and a build of the wheel, installed into a clean virtual environment where `from bhom_schema.tables import create_table_sql` works.

## Not in scope

- Creating all the tables of a class hierarchy at once. That is the decision the user keeps.
- Renaming columns or mapping to a differently named existing table. Tables follow the BHoM field names.
- Structs, and any column whose type is a nested object.
- Merge, upsert and schema-evolution policies beyond `add_columns_sql`. The helpers produce the statement; the team decides when to run it.
- Types in other warehouses (Postgres, Snowflake). The mapping table is the only thing that would change, so it stays a table in code.
- `pyspark` as a package dependency.

## Open questions

1. **Name of a `Ref` column.** `Start_id` (recommended: the column holds an id, not the point, and the field name `Start` stays free) or `Start` (closest to "tables follow BHoM field names"). `Ref(table, column=...)` overrides either, so this only sets the default.
2. **`int` is `INT`, not `BIGINT`.** It matches C# `int` and the generator's `ClrType('long')` marker for `long`. The earlier sketch used `BIGINT` for every `int`, which is safe for values but does not match the C# type. Confirm the team wants the exact mapping.
3. **`Color`.** Treated as custom, so the user picks `Json()`. If the team wants a plain column, it could be an `INT` of ARGB, but the schema's `Color` class would need a documented conversion first.
4. **`Fragments` and `CustomData` on every `BHoMObject`.** They are custom, so every `BHoMObject` table needs two decisions. Should `create_table_sql` have a `base=Skip` shortcut (`fields={**BASE_SKIPPED, ...}`) or stay strictly explicit? Recommended: ship the shortcut as a named constant the user passes in, so the choice is still visible in their code.
5. **`TIMESTAMP_NTZ` needs Databricks Runtime 13.3 or later.** The notebook guide already requires Python 3.12 (so runtime 16 or later), so this holds, but confirm no older cluster is in the picture.
