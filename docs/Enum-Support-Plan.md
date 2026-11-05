# Enum support: plan

Goal: when a notebook user gives an enum field a value that is not a member of the enum, flag it at once, with a message that names the field and the allowed members. This covers a value set in Python and a value written to a table.

## Where we stand

Enums already go through the whole pipeline. Nothing in the pipeline needs to be added for a new kind of enum.

| Stage | What exists | Where |
|---|---|---|
| C# test enums | `SupportKind` (member `None`, a `[Description]` on `Fixed`), `Options` (`[Flags]`, with a combined member `Both`), `Sparse` (no member with the value 0) | `.ci/unit-tests/csharp/Fixtures/FixtureAlpha_oM/Enums/Enums.cs`, `Hardening.cs` |
| Generated Python | `BHoMEnum` and `BHoMFlags` classes; `None` is renamed `None_` and recorded in `renamed_members` | `src/bhom_schema/FixtureAlpha_oM/SupportKind.py`, `Options.py`, `Sparse.py` |
| Used by a class | `Beam.Support: SupportKind`, `Beam.Flags: Options`, `SparseHolder.Level: Sparse` | `Beam.py`, `SparseHolder.py` |
| JSON in and out | Read by member name, as BHoM's `System.Enum` object, or as a number; written as the name. `from_bhom` raises `{value} is not a member of {enum}` | `_support/enums.py` |
| JSON Schema | The allowed names as an `enum` list (free text for flags, which may be combined) | `_support/enums.py` |
| Table column | `STRING`, with the comment `One of: None, Fixed, Pinned.` (`Any of: ..., joined by ', '.` for flags) | `tables/columns.py` |
| Table rows | `to_row` writes the member name; `from_row` and `rows_to_objects` read it back through `from_bhom` | `tables/rows.py` |
| Tests | Generated enums and `Beam` defaults, JSON round trips, the column type and comment, the `Beam` row round trip | `test_fixtures`, `test_support/test_json.py`, `test_tables.py`, `test_table_rows.py` |

So the C# side already has a test enum for every case that matters: a plain enum, a renamed member, a flags enum, and an enum with no zero member. This plan adds no C# fixture; `Beam` carries both a `SupportKind` and an `Options` field and is used for the manual test.

## What is flagged today, and what is not

Checked against the installed package:

| Case | Today |
|---|---|
| `Beam(Support="Bogus")`, `Support="fixed"`, `Support=9`, `Flags="A, Z"` | Raises `ValidationError: Bogus is not a member of SupportKind`. Good, but the message does not list the members and does not say that `fixed` is the wrong case of `Fixed`. |
| `beam.Support = "Bogus"` (assignment after construction) | **Not flagged.** The object now holds a string. |
| `to_row(beam)` of that object | **Not flagged.** `to_cell` writes the string as it is, so `Bogus` reaches the table. |
| `Beam(Flags=8)` (a bit that no member has) | **Not flagged.** `IntFlag` keeps the unknown bit; it is written as the number `8`. A string `"8"` read from a row is refused, so a value can be written that cannot be read back. |
| A hand-written `INSERT` into the table with a wrong string | **Not flagged.** Databricks accepts any string in the column; a wrong value is only found when the row is read back. |

Each of the last four rows is a way for a wrong value to reach the table or the object without a flag.

## What to add

### 1. Say more when a value is refused (`_support/enums.py`)

The error of `from_bhom` lists the members and suggests the closest one:

```
fixed is not a member of SupportKind. Members: None, Fixed, Pinned. Did you mean Fixed?
```

The suggestion is a case-insensitive match, then `difflib.get_close_matches`. For a flags enum the message says that names are combined with `, `. The error type stays `PydanticCustomError("enum_value", ...)`, so existing handling of `ValidationError` does not change.

For a flags enum, a number or a text number with a bit that no member has is refused (`8 has bits that Options does not define`), so `Flags=8` fails at once and what is written can always be read back.

### 2. Flag a wrong value set after construction

Two parts, both in the core, not in Spark:

- **`to_cell` checks enums.** When the annotation of a field is an enum and the value is not one of its members, `to_cell` raises `ValueError: Support is 'Bogus', which is not a member of SupportKind (None, Fixed, Pinned)`, naming the field path as it already does for integers. This stops a bad value on its way to a table, whatever put it into the object.
- **Assignment is validated.** `validate_assignment=True` in the `model_config` of `SchemaModel`, so `beam.Support = "Bogus"` raises at the line that assigns it, in the notebook cell where the mistake is. This applies to every generated class and also checks the other fields (decided, see below).

### 3. Refuse a wrong value at write time, in the table (`tables`)

Steps 1 and 2 only protect values that go through Python. A user can also write to the table with a plain `INSERT` in `spark.sql()`, and Databricks accepts any string in a `STRING` column. A Delta `CHECK` constraint closes that: the table itself refuses the row.

`enum_constraints_sql(model, table, fields)` returns the statements that add these constraints, one per enum column. The user runs them after `create_table_sql`, as in the notebook steps:

```sql
ALTER TABLE `main`.`default`.`Beam` ADD CONSTRAINT `Beam_Support_enum` CHECK (`Support` IN ('None', 'Fixed', 'Pinned'))
```

A flags column is checked name by name, so a combination such as `A, B` passes and `A, Z` does not:

```sql
ALTER TABLE `main`.`default`.`Beam` ADD CONSTRAINT `Beam_Flags_enum` CHECK (size(array_except(transform(split(`Flags`, ','), x -> trim(x)), array('A', 'B', 'Both'))) = 0)
```

Details:

- The members are the names BHoM writes (`None`, not `None_`), taken from `bhom_members()`.
- `NULL` passes a `CHECK`, which agrees with "NULL in a column means the field default".
- An enum inside a `Struct` is reached by its dotted path (`` `Start`.`Kind` ``); a list of enums uses `forall(col, x -> x IN (...))`.
- `enum_columns(model, fields)` is the small function underneath: it lists the enum columns of the table (`{'Support': SupportKind, 'Flags': Options}`) and is exported for the same reason as `custom_fields`.
- The statements are `ALTER TABLE`, run after `CREATE TABLE`, because I have not confirmed that Databricks accepts a `CHECK` inside `CREATE TABLE`. The helper only returns text and never runs it, as for every other SQL helper.

## Decisions taken

1. **`validate_assignment=True` on `SchemaModel`:** yes. The whole suite (`test_fixtures`, `test_support`, the spike tests) must pass with it before the step is done.
2. **Generate the `CHECK` statements:** yes. This is different from the primary and foreign keys, which the user adds by hand because they link tables, a choice the user makes. An enum check does not link anything; it is a rule of one column that the class already holds, so the helper writes it. The user still chooses whether to run the statements.
3. **Flags with unknown bits:** refused. If some BHoM data holds unknown bits on purpose, a `strict=False` keyword can allow them, but it is not the default.

## Build order

1. **Messages and unknown flag bits** (`_support/enums.py`). Tests in `test_support/test_json.py`: the member list and the suggestion in the message, `Flags=8` refused, `"A, B"` still read, the object form still read.
2. **`to_cell` checks enums, and assignment is validated** (`tables/rows.py`, `_support/schema_model.py`). Tests: `beam.Support = "Bogus"` raises; an object built with `model_construct` that holds a wrong value makes `to_row` raise; the whole existing suite still passes.
3. **`enum_columns` and `enum_constraints_sql`** (new `tables/enums.py`, exported from `tables/__init__.py`). Tests compare the SQL text for `SupportKind`, `Options` (flags), a list of enums, an enum in a `Struct`, and `Sparse` (no member 0); every function has a docstring.
4. **Manual test.** Add the enum step below to "Testing the helpers by hand" in [Table-Helpers-Plan.md](Table-Helpers-Plan.md), and run it in a notebook.

After every step: `python -m pytest` (the `test_py2cs` and `test_support` subset, plus `test_fixtures` for the `validate_assignment` change), `python -m pyright`, `python -m py2cs verify --package src/bhom_schema` (the new `tables/enums.py` is hand-written and already covered by the skip of `tables`), and a build of the package, installed into a clean virtual environment where `from bhom_schema.tables import enum_constraints_sql` works.

## Text to add to "Testing the helpers by hand"

A new step 9 after `rows_to_objects`, using `Beam`, which has a `SupportKind` and an `Options` field. Parts a and b need no table:

```python
from bhom_schema.FixtureAlpha_oM.Beam import Beam

BEAMS = "main.default.Beam"
BEAM_FIELDS = {**BASE_SKIPPED, "Start": Struct()}

# a. A wrong value set in Python is flagged where it is set
Beam(Start=PointLike(), Support="Bogus")
beam = Beam(Start=PointLike())
beam.Support = "Fixd"

# b. The flags enum takes names combined with ", ", and nothing else
print(Beam(Start=PointLike(), Flags="A, B").Flags)
Beam(Start=PointLike(), Flags="A, Z")

# c. A wrong value written by hand is refused by the table
spark.sql(create_table_sql(Beam, BEAMS, fields=BEAM_FIELDS))

for statement in enum_constraints_sql(Beam, BEAMS, BEAM_FIELDS):
    print(statement)
    spark.sql(statement)

spark.sql(f"INSERT INTO {BEAMS} (`_id`, `Support`, `Flags`) VALUES ('b1', 'Fixed', 'A, B'), ('b2', NULL, NULL)")
print(spark.table(BEAMS).count())

spark.sql(f"INSERT INTO {BEAMS} (`_id`, `Support`) VALUES ('b3', 'Bogus')")
spark.sql(f"INSERT INTO {BEAMS} (`_id`, `Flags`) VALUES ('b4', 'A, Z')")
```

Expect:

- **a.** Both lines raise: `Bogus is not a member of SupportKind. Members: None, Fixed, Pinned.` for the first, and the same for `Fixd` with `Did you mean Fixed?` for the second, at the assignment itself.
- **b.** The first line prints `Options.Both`; the second raises `Z is not a member of Options`.
- **c.** Two `ALTER TABLE ... ADD CONSTRAINT ... CHECK` statements are printed and run (one for `Support`, one for `Flags`). The first `INSERT` succeeds, including the row of `NULL`s, and the count is `2`. The last two `INSERT`s each fail with a Delta constraint violation that names the constraint and the value (`Bogus`, `A, Z`), and the count stays `2`.

Finish by dropping the `Beam` table with the others.
