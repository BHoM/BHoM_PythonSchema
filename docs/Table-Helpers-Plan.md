# Table helpers: plan

Helpers in the `bhom-schema` package that help a user turn **one schema class** into **one Databricks (Spark SQL / Delta) table**, and read its rows back as objects of that class.

The user decides which tables exist and how they link. The helpers never walk a class hierarchy and never create tables on their own. They answer questions about one class ("what would its table look like?", "which of its fields need a table of their own?") and do the mechanical work for the table the user has chosen.

This replaces the whole-hierarchy helper (`create_tables_sql(LineLike, PREFIX)` creating every held class) in the Databricks section of [Alpha-Releases-Plan.md](Alpha-Releases-Plan.md). That helper is a sketch to prove the idea, not the API.

## Principles

1. **One class in, one table out.** Every helper takes a single model class. Nothing recurses.
2. **Primitives are automatic, everything else is explicit.** A field whose type is a primitive (including lists, sets and dicts of primitives) gets a column. A field of any other type (another schema class, an interface, `Any`, a tuple, `Color`) is never mapped silently: the helper raises an error that names the field and the choices, until the user says what to do with it (see [Custom-typed fields](#custom-typed-fields)).
3. **Column names are the BHoM field names.** No renaming layer. A field with a JSON alias uses the alias, so `bhom_version` is the column `_bhomVersion` on every table. The one exception is the column that holds the id of a row in another table, which is named `<Field>_id` unless the user overrides it. Every identifier in the generated SQL is quoted with backticks, because field names such as `End` and `Key` are SQL keywords.
4. **Structs are a choice, not a default.** A class-typed field is never stored as a nested column unless the user asks for `Struct()`. The other choices are an id pointing at a row in another table, JSON text, or leaving the field out.
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
    "student_area.vcl.LineLike",
    fields={"Start": Ref("student_area.vcl.PointLike"), "End": Ref("student_area.vcl.PointLike")},
)
spark.sql(sql)
```

Before step 2 is answered, `create_table_sql(LineLike, "student_area.vcl.LineLike")` raises:

```
LineLike has 2 fields of a custom type, so they have no column until you decide how to store them:
  Start: PointLike
  End: PointLike
Pass fields={"Start": ...} with one of:
  Ref("catalog.schema.Table")  an id column that points at a row of that table
  Struct()                     a STRUCT column holding the object's own fields
  Json()                       the object as JSON text in a STRING column
  Skip()                       no column; the field keeps its default when a row is read
```

## Type mapping

The mapping is a table in code (`COLUMN_TYPES`), so it is easy to review and to extend. The generator already records the original C# type of a field in a `ClrType` marker when Python cannot say it (`long`, `float`, `char`, `short`, `byte`), and the helpers read it.

| Python annotation | C# type | Column type | Notes |
|---|---|---|---|
| `bool` | `bool` | `BOOLEAN` | |
| `int` | `int` | `INT` | Python `int` is unbounded, so `to_row` raises for a value outside 32 bits, naming the field, rather than leaving it to `createDataFrame` |
| `Annotated[int, ClrType('long')]` | `long` | `BIGINT` | `short` is `SMALLINT`, `sbyte` is `TINYINT`, `byte` is `SMALLINT` (it goes up to 255, and `TINYINT` stops at 127), `ushort` is `INT`, `uint` is `BIGINT`, `ulong` is `DECIMAL(20,0)`. The element type of `long[]` or `List<long>` counts the same way |
| `float` | `double` | `DOUBLE` | |
| `Annotated[float, ClrType('float')]` | `float` | `FLOAT` | |
| `str` | `string` | `STRING` | |
| `Annotated[str, ClrType('char')]` | `char` | `STRING` | A comment on the column says it holds one character |
| `Decimal` | `decimal` | `DECIMAL(38,10)` | C# `decimal` has 28 digits; Spark allows 38 in total. Override with `types={"Cost": "DECIMAL(18,2)"}` |
| `datetime` | `DateTime` | `TIMESTAMP_NTZ` | BHoM DateTimes carry no time zone, so `to_row` raises for a time-zone-aware value. Needs Databricks Runtime 13.3 or later |
| `date` | `DateOnly` | `DATE` | |
| `timedelta` | `TimeSpan` | `DOUBLE` | Seconds. Delta tables cannot hold interval columns. The column comment says "seconds" and `to_row` / `from_row` convert |
| `UUID` | `Guid` | `STRING` | Lower-case with dashes, as `str(uuid)` writes it |
| a `BHoMEnum` | `enum` | `STRING` | The member name as BHoM writes it. A comment lists the allowed names. A `CHECK` constraint is the user's to add |
| a `BHoMFlags` | `[Flags] enum` | `STRING` | Names joined by `", "`, as BHoM writes them |
| `list[X]`, `set[X]` | `List<X>`, `X[]`, `HashSet<X>`, `IEnumerable<X>` | `ARRAY<X>` | X must itself be a primitive. A `set` loses its order in the table, which does not matter |
| `list[list[X]]` | `X[][]` | `ARRAY<ARRAY<X>>` | |
| `dict[str, X]` | `Dictionary<string, X>` | `MAP<STRING, X>` | X must be a primitive. Other key types are custom |
| `X \| None` | nullable `X` | same as `X`, nullable | Every column is nullable except the key |

Everything else is a [custom-typed field](#custom-typed-fields): another schema class, an interface or `Polymorphic[...]`, `Any`, `tuple[...]`, `Color`, a list of classes, a dict with a non-string key or a non-primitive value, `Callable`, `System.Type`. A `Struct()` decision on an interface-typed field is refused, because the fields of the object are not known until it is read. A `Json()` decision on a `Callable` field is refused, because it has no JSON; `Skip()` is its only choice.

A generic class (`Wrapper_1`, `TreeLike_1`) is refused by every helper, with an error that names the class. Its fields depend on a type argument that the table cannot record.

`describe` and `create_table_sql` also write the field's `description` (from the C# XML summary) as the column `COMMENT`, so the table documents itself in Unity Catalog. A `Quantity` marker adds the quantity and unit (`Distance between the supports. [Length, m]`) and a `DisplayText` marker is put first when there is one.

**NULL in a column means the field's default.** `from_row` treats a NULL in a column of a non-optional field (`LineLike.Infinite: bool`) as the field being absent, so the field takes its default. This is what lets rows written before `add_columns_sql` added a column still read as the class.

## The key column

A table needs an id for other tables to point at. Two cases:

- The class derives from `BHoMObject`: it already has `BHoM_Guid`, so that column is the key and nothing is added.
- It does not (`PointLike`, `LineLike`): the helper adds `_id STRING NOT NULL`. A generated id is `str(uuid4())`, lower-case with dashes, the same text as a `BHoM_Guid` key, so a `Ref` column holds ids of one form whichever table it points at.

`create_table_sql(..., key="_id")` is the default; `key="BHoM_Guid"` or any other field name uses that field; `key=None` adds no key. A key is only informational in Unity Catalog, and the helper adds no constraint, so it does not claim uniqueness.

## Custom-typed fields

`custom_fields(model)` returns `{field name: type}` for every field that has no automatic column. For each one the user passes a decision in `fields=`:

| Decision | Column | Reading a row | Use when |
|---|---|---|---|
| `Ref(table, column=None)` | `<Field>_id STRING` (or `column`) | `from_row` takes the object from `held={"Start": point}` | The field is a class that has, or will have, its own table |
| `Struct(fields=None)` | `<Field> STRUCT<...>` (or `ARRAY<STRUCT<...>>` for a list of classes) | the nested dict is validated into the class (or a list of them) | The field is a class that is only ever stored inside its parent: a point inside a line, a list of points inside a collection |
| `Json()` | `<Field> STRING`, the JSON the schema writes | validated back into the field's type | A one-off or deeply nested value that does not deserve a table: `Any`, `CustomData`, a tuple |
| `Skip()` | none | the field keeps its default | `Fragments`, or anything the table does not need |

`Struct` maps the nested class by the same rules as a table: its primitive fields are automatic, and its own custom-typed fields need decisions, given as `Struct(fields={"Inner": Struct()})`. An undecided nested field raises the same error, naming the path (`Start.Inner`). The `_bhomVersion` of the nested class is left out of the struct: the version is kept once per row, in the table. A `Ref` inside a `Struct` is refused, since an id inside a struct cannot be followed to another table; `Json` and `Skip` are allowed there. A class that would nest itself (`CycleA` holding `CycleB` holding `CycleA`) is refused, naming the cycle. `Struct` also accepts a list of classes (`Collections.Points`), which gives `ARRAY<STRUCT<...>>`. `Ref` does not accept a list; a one-to-many link through a table of its own is something the user builds themselves (see [Not in scope](#not-in-scope)).

## The helpers

All live in one public module, `bhom_schema.tables`.

### Inspect

| Helper | Returns | Purpose |
|---|---|---|
| `describe(model, fields=None, key="_id")` | `list[ColumnInfo]` | One entry per column the table would have: name, column type, nullable, comment, the Python field it comes from and the decision that produced it (`primitive`, `ref`, `struct`, `json`, `key`, or `skip` for a field with no column; `None` when the field still needs a decision, which `needs_decision` tells and `undecided_fields` lists as `UndecidedField(path, type)`). Printed as a table in a notebook, so the user sees the table before creating it. Does not raise for undecided fields; it lists them with the decision `None` |
| `custom_fields(model)` | `dict[str, type]` | The fields that need a decision, with their Python types. For a class-typed field the type is the schema class, so the user knows which other table to create next |
| `column_type(annotation)` | `str` | The column type of one annotation. Raises `UnmappedType` for a custom one. The building block of the rest |

### Create and change the table

| Helper | Returns | Purpose |
|---|---|---|
| `create_table_sql(model, table, *, fields=None, key="_id", types=None, replace=False)` | `str` | One `CREATE TABLE IF NOT EXISTS table (...) USING DELTA`, with column comments, a table comment (the class summary) and `TBLPROPERTIES ('bhom.type' = 'BH.oM.FixtureAlpha.LineLike', 'bhom.schema_version' = '...')`. `replace=True` gives `CREATE OR REPLACE TABLE`. `types` overrides the column type of a field |
| `add_columns_sql(check, table)` | `str` or `None` | Given the `TableCheck` of the table (see [Check an existing table](#check-an-existing-table-against-a-class)), the `ALTER TABLE ... ADD COLUMNS (...)` for its `missing` columns. For when a new alpha adds a property to a class. `None` when nothing is missing. Comparing a class with a table happens in one place, `check_table` |

Primary keys, foreign keys and `CHECK` constraints have no helper. The user creates each table with `create_table_sql`, then adds the constraints with their own `ALTER TABLE ... ADD CONSTRAINT` in Databricks once the referenced tables exist (in Unity Catalog they are informational, so this is documented in the guide, with the `LineLike` / `PointLike` statements as the example). A helper can come later if the same statements keep being written.

### Rows to objects and back

| Helper | Returns | Purpose |
|---|---|---|
| `to_row(obj, *, fields=None, key="_id", ids=None)` | `dict` | One object as a dict with the table's column names. Applies the conversions (`UUID` and enums to text, `timedelta` to seconds, `Json` fields to JSON text, `Struct` fields to nested dicts). `ids={"Start": "abc"}` fills the `Ref` columns; the user got those ids from the rows of the other tables. The key is `str(obj.BHoM_Guid)` when the key is that field, otherwise `str(uuid4())` unless `ids` gives one (`ids={"_id": ...}`). The user reads the key from the returned dict to fill the `Ref` columns of other tables |
| `from_row(model, row, *, fields=None, held=None)` | object | The reverse, for one row. `held={"Start": point}` supplies the objects of `Ref` fields, since the helper does not fetch them. A `Ref` field with no entry in `held` keeps its default and `from_row` says so in a warning, not silently |
| `rows_to_objects(model, rows, *, fields=None, key="_id", held=None, keyed=False, errors="raise")` | `list` or `dict`, or that and `list[RowError]` | `from_row` over many rows. `keyed=True` returns `{key: object}`, which is what `held` of another table needs, since a class such as `PointLike` has no field that keeps its id. `errors="collect"` also returns a `RowError(index, key, message)` per bad row, so one bad row in a million does not hide the rest. `held` is `{field: {id: object}}` here |
| `ddl_schema(model, *, fields=None, key="_id")` | `str` | The columns as a DDL string for `spark.createDataFrame(rows, schema=...)`, always the same columns `create_table_sql` makes |

### Check an existing table against a class

The team will have tables that exist before the helpers do, and tables written by an older alpha. These two helpers answer "will this table read as this class?" without reading the whole table.

| Helper | Returns | Purpose |
|---|---|---|
| `check_table(model, columns, *, fields=None, key="_id", types=None)` | `TableCheck` | `columns` is `{name: type}` from `DESCRIBE TABLE` or `df.dtypes`. Reports `missing` (the `ColumnInfo` of each column the class has and the table lacks; the rows read with the field's default), `extra` (columns the class does not know), `mismatched` (column has another type than the class expects) and `undecided_fields` (the `UndecidedField` of each field that still needs a decision). `TableCheck.ok` and a readable `str()` |
| `example_row(model, *, fields=None)` | `dict` | A row with the class's defaults, for a quick `INSERT` or `createDataFrame` smoke test |

### Spark layer (optional)

Imported separately, `from bhom_schema.tables.spark import ...`. The functions take the `SparkSession` the notebook already has and import nothing from `pyspark` (the conditions are SQL text, the rows are dicts and a DDL string), so the package needs no Spark installed and the functions are tested with a stand-in session.

| Helper | Purpose |
|---|---|
| `create_table(spark, model, table, **options)` | `spark.sql(create_table_sql(...))` and return the SQL it ran |
| `write_objects(spark, objects, table, *, fields=None, key="_id", ids=None)` | `to_row` over the objects, `createDataFrame` with `ddl_schema`, append to the table. `ids` is a list of `to_row` `ids` dicts in the order of `objects`. Returns the keys of the written rows, in the same order |
| `read_rows(spark, table, *, where=None, limit=None)` | Query the table (optionally filtered) and return its rows as dicts, before any of them become objects |
| `read_objects(spark, model, table, *, fields=None, key="_id", held=None, keyed=False, where=None, limit=None)` | `read_rows` then `rows_to_objects`. For a table with no `Ref` fields, or when `held` is already known |
| `fetch_by_ids(spark, table, ids, *, key="_id", batch=5000)` | The rows of another table by id, in batches. What the user calls to get the `held` objects, with `rows_to_objects(..., keyed=True)` on the result. Walking from one table to another stays a visible step in the user's code |

The user composes the multi-table write and read themselves, one table at a time:

```python
line_fields = {"Start": Ref("student_area.vcl.PointLike"), "End": Ref("student_area.vcl.PointLike")}

# Write: the points first, then the lines with the keys of their points
starts = write_objects(spark, [line.Start for line in lines], "student_area.vcl.PointLike")
ends = write_objects(spark, [line.End for line in lines], "student_area.vcl.PointLike")
write_objects(spark, lines, "student_area.vcl.LineLike", fields=line_fields,
              ids=[{"Start": start, "End": end} for start, end in zip(starts, ends)])

# Read: the line rows first, then only the points they point at
line_rows = read_rows(spark, "student_area.vcl.LineLike", limit=1000)
point_ids = {row["Start_id"] for row in line_rows} | {row["End_id"] for row in line_rows}
point_rows = fetch_by_ids(spark, "student_area.vcl.PointLike", point_ids)
points = rows_to_objects(PointLike, point_rows, keyed=True)
lines = rows_to_objects(LineLike, line_rows, fields=line_fields, held={"Start": points, "End": points})
```

## Where the code goes

The generator treats every module under `src/bhom_schema` as a generated class, except `_support`, `__init__.py` and `_version.py`. A new `bhom_schema/tables/` package would be read as schema classes, so `tables` is added next to `_support` in each list of skipped modules in `.ci/generation/py2cs/reader.py` and `ci.py`. The public path is `bhom_schema.tables`. It is a handful of lines, with a test that a module under `tables` is never listed as a class.

The package stays one wheel. `pydantic` is the only dependency of the core module. `pyspark` is not added to `dependencies`, and no module imports it: the Spark layer only calls methods of the session it is given. Pyright runs on the package, so the new code is typed; the session is typed `Any`.

## Build order

Each step is mergeable alone, and the Databricks guide section is rewritten when step 4 lands.

1. **Core mapping and inspection.** `column_type`, `custom_fields`, `describe`, `UnmappedType` with the readable error, the `Ref` / `Struct` / `Json` / `Skip` decisions, the `BASE_SKIPPED` constant, and the generator skip. Tests: one per row of the type mapping above, run against the real fixture classes (`Scalars` covers `datetime`, `UUID`, `Decimal`, `timedelta`, `char`; `Collections` covers lists, sets, dicts, tuples and a list of classes as `Struct`; `Beam` covers enums, `Quantity` and `ClrType('long')`; `LineLike` covers `Ref` and `Struct`), plus the refusal of a generic class (`Wrapper_1`) and of `Json()` on a `Callable`.
2. **DDL and checks.** `create_table_sql`, `check_table`, `add_columns_sql`. Tests compare the SQL text for `LineLike` (once with `Ref`, once with `Struct`, both quoting `` `End` ``), `PointLike`, `Scalars`, `Beam` (the unit in the comment of `Span`), the `_bhomVersion` column, and the error text for an undecided field, including a nested one. `check_table` and `add_columns_sql` run on a fake `DESCRIBE` output.
3. **Rows.** `to_row`, `from_row`, `rows_to_objects`, `ddl_schema`, `example_row`. The test that matters most is the round trip: for every fixture class, `from_row(to_row(obj))` equals `obj`, including `Json` and `Struct` fields and the `Ref` ids. Also a row with a NULL in a non-optional column reads as the default, `keyed=True` gives the generated keys, and `to_row` raises for an `int` outside 32 bits and for a time-zone-aware `datetime`.
4. **Spark layer.** The Spark functions with a stub `spark` that records the SQL. The Databricks notebook in the guide is the only test that needs a real workspace, run by hand: create the tables, write 10 `LineLike` objects, read them back and compare, once with `Ref` and once with `Struct`. The guide also shows adding the primary and foreign keys by hand.

After every step: `python -m pytest`, `python -m pyright`, `python -m py2cs verify --package src/bhom_schema` (to prove the skip works and nothing in `tables` is taken for a schema class), and a build of the wheel, installed into a clean virtual environment where `from bhom_schema.tables import create_table_sql` works.

## Testing the helpers by hand

The unit tests cover every helper, but only against a stand-in for Spark. This procedure checks them in a real Databricks notebook, one cell per block, in order. Steps 2 to 4 need no tables; steps 5 and 6 create and fill two real tables; steps 7 and 8 read them back; step 9 checks enum members. Anything other than the expected result is a bug to report, with the statement and the error text.

Every cell below assumes this first cell has run (change `student_area.vcl` to a catalog and schema you may write to):

```python
from bhom_schema.FixtureAlpha_oM.LineLike import LineLike
from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
from bhom_schema.tables import *

POINTS = "student_area.vcl.PointLike"
LINES = "student_area.vcl.LineLike"
REFS = {"Start": Ref(POINTS), "End": Ref(POINTS)}
```

### 1. Install or update the package

The helpers are in the first alpha built after they were merged. An old install is not replaced by a plain `pip install`, so upgrade, in a cell of its own:

```
%pip install --upgrade --pre --no-cache-dir --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bhom-schema
```

Then restart Python in the next cell, and check in a third:

```python
dbutils.library.restartPython()
```

```python
import bhom_schema
print(bhom_schema.__version__)
from bhom_schema.tables import describe
```

The version must be the one shown on test.pypi.org, and the import must not fail. If it does, the old version is still installed: pin the version (`bhom-schema==<version>`) and restart again.

### 2. `column_type`

```python
print(column_type(float), column_type(list[str]))
column_type(PointLike)
```

Expect `DOUBLE ARRAY<STRING>`, then the last line raises `UnmappedType: PointLike has no column type`. `custom_fields(LineLike)` names the fields that need a decision: `Start` and `End`, both `PointLike`.

### 3. `describe`

```python
for column in describe(PointLike):
    print(column.name, column.type, column.decision)

for column in describe(LineLike):
    print(column.name, column.type, column.decision)
```

Expect for `PointLike`: `_id STRING key`, `_bhomVersion STRING primitive`, then `X`, `Y`, `Z` as `DOUBLE primitive`. For `LineLike`: `_id STRING key`, `_bhomVersion STRING primitive`, `Start None None`, `End None None`, `Infinite BOOLEAN primitive`, `Label STRING primitive`. The rows with the decision `None` (`needs_decision`) are what `create_table_sql` refuses until the user decides.

### 4. `create_table_sql`

```python
print(create_table_sql(PointLike, POINTS))
print(create_table_sql(LineLike, LINES, fields=REFS))
print(create_table_sql(LineLike, LINES + "Struct", fields={"Start": Struct(), "End": Struct()}))
create_table_sql(LineLike, LINES)
```

Expect, for the first three, a `CREATE TABLE IF NOT EXISTS` with every name in backticks, a column comment on `Infinite`, `USING DELTA`, the comment `A straight segment between two points.` on the `LineLike` tables, and `TBLPROPERTIES` with the `bhom.type` and the package version. The `Ref` version has `` `Start_id` STRING `` and `` `End_id` STRING ``; the `Struct` version has `` `Start` STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE> ``. The last call, with no decision, raises `UnmappedType` with `LineLike has 2 fields of a custom type, ...`, the two fields, and the four choices (`Ref`, `Struct`, `Json`, `Skip`); no SQL is produced.

### 5. Create the tables with `spark.sql()`

```python
spark.sql(create_table_sql(PointLike, POINTS))
spark.sql(create_table_sql(LineLike, LINES, fields=REFS))

spark.sql(f"DESCRIBE TABLE {POINTS}").show(truncate=False)
spark.sql(f"DESCRIBE TABLE {LINES}").show(truncate=False)
```

Expect both statements to run without error and the two `DESCRIBE` outputs to list the columns of step 3 (with `Start_id` and `End_id` in place of `Start` and `End`) and the comments. In the catalog explorer, each table shows the table comment and the properties `bhom.type` and `bhom.schema_version`. To start over, drop the tables or pass `replace=True` to `create_table_sql`.

### 6. Add test data

```python
spark.sql(f"""
    INSERT INTO {POINTS} (`_id`, `X`, `Y`, `Z`) VALUES
    ('p1', 1, 0, 0), ('p2', 2, 0, 0), ('p3', 3, 4, 0)
""")
spark.sql(f"""
    INSERT INTO {LINES} (`_id`, `Start_id`, `End_id`, `Infinite`, `Label`) VALUES
    ('l1', 'p1', 'p2', false, 'axis'), ('l2', 'p2', 'p3', true, NULL)
""")

print(spark.table(POINTS).count(), spark.table(LINES).count())
spark.table(LINES).show()
```

Expect `3 2`, and the two lines with their point keys. A `NULL` is the default of its field: `Label` of `l2` reads back as the default in step 8.

### 7. `to_row` and `from_row`

```python
line = LineLike(Start=PointLike(X=5), End=PointLike(X=6), Label="new")

row = to_row(line, fields=REFS, ids={"Start": "p4", "End": "p5"})
print(row)
```

Expect a dict with `_id` (a uuid text), `Start_id` `p4`, `End_id` `p5`, `Infinite` `False`, `Label` `new`. Without `ids`, `to_row` raises `Start is a Ref: pass ids=...`. Next, check that Spark accepts the row with the schema of the table, then rebuild the objects from the rows of the tables:

```python
spark.createDataFrame([row], schema=ddl_schema(LineLike, fields=REFS)).write.mode("append").saveAsTable(LINES)
print(spark.table(LINES).count())

points = {r["_id"]: from_row(PointLike, r.asDict()) for r in spark.table(POINTS).collect()}
stored = spark.table(LINES).where("`_id` = 'l1'").collect()[0].asDict()
rebuilt = from_row(LineLike, stored, fields=REFS, held={"Start": points[stored["Start_id"]], "End": points[stored["End_id"]]})
print(rebuilt)
```

What each line does:

1. `spark.createDataFrame([row], schema=ddl_schema(LineLike, fields=REFS)).write.mode("append").saveAsTable(LINES)` writes the `row` dict from `to_row` into the `LineLike` table.
   - `ddl_schema(LineLike, fields=REFS)` gives the column names and types of the table (`` `_id` STRING NOT NULL, ..., `Start_id` STRING, ... ``), so Spark does not guess the types from the values.
   - `createDataFrame([row], schema=...)` builds a one-row DataFrame from the dict.
   - `.write.mode("append")` adds the row and keeps the existing ones; the default mode would fail because the table exists.
   - `.saveAsTable(LINES)` writes it to the table by name. This is what `write_objects` does for many objects. It proves that Spark accepts what `to_row` produces.
2. `print(spark.table(LINES).count())` counts the rows of the table, to see that the row was added.
3. `points = {r["_id"]: from_row(PointLike, r.asDict()) for r in spark.table(POINTS).collect()}` reads every row of the points table into Python (`collect()`), turns each row into a dict (`asDict()`) and then into a `PointLike` (`from_row`). The result maps each point's `_id` to its object, which is what a `Ref` column holds.
4. `stored = spark.table(LINES).where("`_id` = 'l1'").collect()[0].asDict()` reads the one line row with the key `l1` and turns it into a dict. It holds `Start_id` and `End_id`, the keys of the two points, not the points.
5. `rebuilt = from_row(LineLike, stored, fields=REFS, held={...})` makes the `LineLike` from that dict. `fields=REFS` says that `Start` and `End` are stored as ids. `held` gives the objects that those ids point at, looked up in `points` by `stored["Start_id"]` and `stored["End_id"]`. `from_row` cannot fetch a point itself, because the user decides where the other table is.
6. `print(rebuilt)` shows the object, to check that it matches the line that was stored.

Expect `3` (the written row is the third), then `LineLike` with `Start` at `X=1.0`, `End` at `X=2.0`, `Infinite` `False` and `Label` `axis`. Without `held`, `from_row` warns that `Start` keeps its default.

### 8. `rows_to_objects`

```python
line_rows = [r.asDict() for r in spark.table(LINES).collect()]
point_rows = [r.asDict() for r in spark.table(POINTS).collect()]

points = rows_to_objects(PointLike, point_rows, keyed=True)
lines = rows_to_objects(LineLike, line_rows, fields=REFS, held={"Start": points, "End": points})
print(len(lines))
for line in lines:
    print(line.Label, line.Start.X, line.End.X)

objects, problems = rows_to_objects(PointLike, [{"_id": "a", "X": 1.0}, {"_id": "b", "X": "bad"}], errors="collect")
print(len(objects), problems[0].index, problems[0].key)
```

Expect `3`, then one line per row with its label and the `X` of its two points (the `Label` of `l2` is the default, and its points are `p2` and `p3`), then `1 1 b` (one good object; the bad row is at position 1 with key `b`). Without `errors="collect"` the bad row raises `ValidationError`.

### 9. Enum members

`Beam` has a `SupportKind` field and an `Options` (flags) field. Parts a and b need no table; part c checks that the table itself refuses a wrong value.

```python
from bhom_schema.FixtureAlpha_oM.Beam import Beam

BEAMS = "student_area.vcl.Beam"
BEAM_FIELDS = {**BASE_SKIPPED, "Start": Struct()}

# a. A wrong value set in Python is flagged where it is set
Beam(Start=PointLike(), Support="Bogus")
beam = Beam(Start=PointLike())
beam.Support = "Fixd"

# b. The flags enum takes names combined with ", ", and nothing else
print(Beam(Start=PointLike(), Flags="A, B").Flags)
Beam(Start=PointLike(), Flags="A, Z")

# c. A wrong value written by hand is refused by the table
spark.sql(f"DROP TABLE IF EXISTS {BEAMS}")
spark.sql(create_table_sql(Beam, BEAMS, fields=BEAM_FIELDS))

for statement in enum_constraints_sql(Beam, BEAMS, BEAM_FIELDS):
    print(statement)
    spark.sql(statement)

spark.sql(f"INSERT INTO {BEAMS} (`BHoM_Guid`, `Support`, `Flags`) VALUES ('b1', 'Fixed', 'A, B'), ('b2', NULL, NULL)")
print(spark.table(BEAMS).count())

spark.sql(f"INSERT INTO {BEAMS} (`BHoM_Guid`, `Support`) VALUES ('b3', 'Bogus')")
spark.sql(f"INSERT INTO {BEAMS} (`BHoM_Guid`, `Flags`) VALUES ('b4', 'A, Z')")
```

Expect:

- **a.** Both lines raise a `ValidationError`, the second at the assignment itself. The first says `Bogus is not a member of SupportKind. Members: None, Fixed, Pinned.`; the second says `Fixd is not a member of SupportKind. Members: None, Fixed, Pinned. Did you mean Fixed?`
- **b.** The first line prints `Options.Both`; the second raises `Z is not a member of Options. Members: A, B, Both.`. `Beam(Flags=8)` raises too, because no member has that bit.
- **c.** Two `ALTER TABLE ... ADD CONSTRAINT ... CHECK` statements are printed and run (`Beam_Support_enum` and `Beam_Flags_enum`). The first `INSERT` succeeds, including the row of `NULL`s, and the count is `2`. The last two `INSERT`s each fail with a Delta constraint violation that names the constraint (`Beam_Support_enum`, `Beam_Flags_enum`), and the count stays `2`. `to_row` also refuses a wrong value that got into an object without validation, for example from `Beam.model_construct(Support="Bogus", Start=PointLike())`.

### Afterwards

The Spark wrappers (`create_table`, `write_objects`, `read_rows`, `fetch_by_ids`, `read_objects`) and the `check_table` and `add_columns_sql` helpers are exercised by steps 5 to 11 of "Trying the package in a Databricks notebook" in [Alpha-Releases-Plan.md](Alpha-Releases-Plan.md). A step that fails in Spark but passed in the steps above means Databricks rejected the SQL or the rows, not the Python logic.

## Not in scope

- Creating all the tables of a class hierarchy at once. That is the decision the user keeps.
- Renaming columns or mapping to a differently named existing table. Tables follow the BHoM field names.
- Primary key, foreign key and `CHECK` statements, and the table for a one-to-many link. The user writes those in Databricks, or builds the link table from `create_table_sql` and the ids of the rows.
- Merge, upsert and schema-evolution policies beyond `add_columns_sql`. The helpers produce the statement; the team decides when to run it.
- Types in other warehouses (Postgres, Snowflake). The mapping table is the only thing that would change, so it stays a table in code.
- `pyspark` as a package dependency.

## Decisions taken

1. **Name of a `Ref` column** is `<Field>_id` (`Start_id`): the column holds an id, not the point, and the field name stays free. `Ref(table, column=...)` overrides it.
2. **`int` is `INT`**, the exact C# `int`; `long` is `BIGINT` through the `ClrType('long')` marker.
3. **`Color` is custom**, so the user picks a decision for it.
4. **`Fragments` and `CustomData`** of every `BHoMObject` are custom. The module ships a named constant, `BASE_SKIPPED = {"Fragments": Skip(), "CustomData": Skip()}`, that the user spreads into `fields=` (`fields={**BASE_SKIPPED, "Start": Ref(...)}`), so the choice stays visible in their code and is not made for them.
5. **`TIMESTAMP_NTZ`** is fine: the guide already needs Databricks Runtime 16 or later for Python 3.12.
6. **`_bhomVersion`** is a column of every table, named after the JSON alias as every other column follows the BHoM name.
7. **Generic classes are refused.** A table cannot say which type argument its rows were written with.
8. **NULL means the default**, so rows written before `add_columns_sql` still read.
