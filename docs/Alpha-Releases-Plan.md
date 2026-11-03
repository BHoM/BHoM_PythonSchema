# Plan: daily alpha releases next to the quarterly beta release

Goal: Python users can install the latest alpha and always get what is on `develop`. The quarterly beta (`release.yml`, see "Making a release" in
[Workflows.md](Workflows.md)) stays the stable, frozen release.

## How C# does it (BuroHappold_Installer)

- `ReleaseType` defaults to `alpha`. An alpha gets the patch number `yyMMdd` (the build date), so the installer is `X.Y.0.<yyMMdd>`, built daily from `master`/develop of every repository.
- A `beta` gets `X.Y.1.0` and is built from the tag of that version (`BuildSolution.ps1` checks out the latest matching tag).
- Same pipeline, two inputs: nothing is hand-edited for an alpha.

## Mapping to Python

| | Alpha | Beta (exists today) |
|---|---|---|
| Trigger | daily schedule, and by hand | by hand, end of a quarter's milestone |
| Source | tip of `develop`, as committed (no C# clone/build) | regenerated from the C#, then frozen on branch `vX.Y` |
| Version | `X.Y.0aYYMMDDHHmm`, UTC (PEP 440 pre-release) | `X.Y.0` |
| Install | `pip install --pre bhom-schema` | `pip install bhom-schema` |
| Published to | TestPyPI (PyPI later, same as beta) | TestPyPI (PyPI later) |
| Git | one moving tag `alpha-latest`, no GitHub Release | branch `vX.Y`, tag `vX.Y.0`, GitHub Release |

pip has no `--alpha` option: `--pre` is the only built-in switch for pre-releases, so that is what the docs tell users to run. A specifier that names a pre-release (`"bhom-schema>=0a0"`, or an exact `bhom-schema==10.1.0a2605030600`) also works without `--pre`. A separate `bhom-schema-alpha` distribution was rejected: it would install the same `bhom_schema` package as `bhom-schema` and the two would overwrite each other.

Why this shape:

- **Reflect `develop`, not regenerate.** `develop` is already regenerated from the C# every Saturday by `python-schema-generation.yml` and takes human PRs in between. The alpha packages `develop` as it is, so it needs no C# build and runs in about a minute on ubuntu.
- **`aYYMMDDHHmm` extends the installer's date stamp with the time.** The installer's `yyMMdd` allows one build a day; here several alphas a day are needed, so the UTC time is added. The number after `a` is a plain integer in PEP 440, so it orders by time. pip ignores pre-releases by default, so stable users stay on the beta and alpha users opt in with `--pre`. Order is correct: `10.1.0a2601010600` < `10.1.0a2601021430` < `10.1.0`.
- **No tag per alpha.** `release.yml` finds the previous release with `git tag --list "v*.0"`; a tag per day would clutter tags and branches for nothing. One moving tag records the last published commit.

## Version ordering around a beta release

PEP 440 puts `10.0.0aYYMMDDHHmm` **below** `10.0.0`. Once `10.0.0` is released, alphas must be of the **next** version (`10.1.0aYYMMDDHHmm`), or `--pre` users would be
served the old beta. `__version__` comes from the BHoM version read from `BHoM.dll` (`_version.py`), so this holds once the BHoM version on `develop` has been
bumped after the milestone. The alpha workflow therefore refuses to publish, with a clear message, when `v{__bhom_version__}.0` already exists as a tag.

Decided: a forgotten version bump fails the alpha (no fallback to `X.Y.0.post1.devYYMMDD`). The bump is a release checklist step (below).

## The workflow: `.github/workflows/alpha-release.yml`

Triggers: `schedule` daily (06:00 UTC, after Saturday's 04:00 generation has pushed) and `workflow_dispatch` with `dry_run` (default true) and `force` (publish even when nothing changed).

Concurrency: one group shared with `python-schema-generation.yml` and `release.yml`, `cancel-in-progress: false`, so an alpha never packages a half-pushed `develop` or races a beta.

One job on ubuntu, then a publish job (same split as `release.yml`):

1. Checkout `develop`, `fetch-depth: 0`.
2. **Gate.** Skip (green, with a summary line) when `HEAD` equals the commit `alpha-latest` points at, unless `force`. Quiet days publish nothing.
3. **Guard.** Read `__bhom_version__` from `src/bhom_schema/_version.py`; fail when tag `v{version}.0` exists (see above).
4. **Stamp.** Compute `{bhom_version}.0a{yyMMddHHmm}` from the current UTC time and rewrite `__version__` in `_version.py` in the runner's checkout only. It is never committed, so `develop` keeps `X.Y.0.dev0`.
5. **Check.** `pip install -e ".[dev]" build`, `pytest`, `pyright`. These are the same fast checks as `pr-checks.yml` and need no C# assemblies (tests marked `realtypes` are skipped, as on the unit-test job).
6. **Build** the wheel; assert the wheel filename carries the stamped version.
7. Upload the wheel as an artifact. Stop here on `dry_run`.
8. **Publish job** (needs build, not dry run): environment `testpypi-alpha`, trusted publishing with `skip-existing: true` so a re-run of the same job is harmless (the stamp is computed once, in the build job, and passed on in the wheel); then move tag `alpha-latest` to `HEAD` (`git tag -f` + `git push -f` of that one tag, `contents: write` on this step only).

Several alphas on the same day are allowed: each run has its own time in the stamp, and the gate only stops a run when `develop` has not moved since the last alpha. A manual run after a merge therefore publishes a new alpha at once, and the scheduled run that follows skips.

## One-time setup (admin)

### On the GitHub repository

- Create the environment `testpypi` (used by `release.yml`; it can require a reviewer, since a beta is by hand) and the environment `testpypi-alpha` (used by `alpha-release.yml`; no reviewer, it runs unattended). Settings, Environments, New environment.
- Allow the workflow's token to push the `alpha-latest` tag (it is a tag, so it does not touch `develop` protection).

### On test.pypi.org (once, for both releases)

TestPyPI is a separate site with its own accounts: a pypi.org login does not work there. Trusted publishing means no token or password is stored in GitHub.

1. Sign in at test.pypi.org with the account that will own the project (create it if needed), and turn on two-factor authentication, which is required to publish.
2. Open *Your account*, then *Publishing*. The project `bhom-schema` does not exist yet, so add **pending publishers** (they create the project on the first upload). Use *Add a new pending publisher*, GitHub tab, and enter, for the **beta**:
   - PyPI project name: `bhom-schema`
   - Owner: `BHoM`
   - Repository name: `BHoM_PythonSchema`
   - Workflow name: `release.yml`
   - Environment name: `testpypi`
3. Add a second pending publisher for the **alpha**, identical except:
   - Workflow name: `alpha-release.yml`
   - Environment name: `testpypi-alpha`

   Two entries are needed: a publisher is bound to one workflow file and one environment, so the beta entry does not cover the alpha.
4. After the first successful upload the project exists and the pending publishers turn into normal ones. Under the project's *Manage*, then *Publishing*, check that both are listed. Under *Collaborators*, add the other maintainers as owners so the project does not depend on one person.
5. Check the first upload on the project page: the version, and that the wheel is there. Install it with `pip install --pre --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bhom-schema` (the extra index is for pydantic).

Real PyPI is set up the same way on pypi.org when it is time (the same two entries, with the same environment names or new ones), and the `repository-url` lines in both workflows are removed.

### Scheduled runs

- GitHub disables scheduled workflows after 60 days without repository activity; `develop` receives the weekly generation commit, which keeps it alive. If that ever stops, re-enable by hand.
- Allow the workflow's token to push the `alpha-latest` tag (it is a tag, so it does not touch `develop` protection).

## Quarterly cycle

| When | What |
|---|---|
| Daily | `alpha-release.yml` publishes `X.Y.0aYYMMDDHHmm` if `develop` changed (and by hand whenever a merge should be available at once) |
| Saturday | `python-schema-generation.yml` commits regenerated classes to `develop`; Sunday's alpha carries them |
| End of quarter (by hand) | Run `release.yml` dry run, then live: `vX.Y` branch, `vX.Y.0` tag, wheel on TestPyPI |
| Right after the beta | Bump the BHoM version on `develop` to the next `Major.Minor`; the next Saturday generation then writes `__bhom_version__ = "X.(Y+1)"` and alphas continue as `X.(Y+1).0aYYMMDDHHmm`. Until then the alpha guard fails by design |
| Between | Fixes to a released beta go on branch `vX.Y` and are released as `X.Y.N` (out of scope here; the beta workflow today only makes `X.Y.0`) |

## Changes to make

1. Add `.github/workflows/alpha-release.yml` as above. Put the stamp and guard logic in a small `py2cs` command (for example `python -m py2cs alpha-version --package src/bhom_schema --tags <list>`) rather than inline PowerShell, so it can be unit tested under `.ci/unit-tests/python`.
2. Add the workflow to the shared concurrency group in `python-schema-generation.yml` and `release.yml`.
3. Update [Workflows.md](Workflows.md): a row in the table, a box in the diagram, a "Making an alpha release" section, and a line in the release section saying the BHoM version is bumped on `develop` afterwards. Document `pip install --pre bhom-schema` for users.
4. Add the unit test for the version stamp and guard (pre-release ordering against a released tag, two stamps on the same day ordering by time, no-tag-yet cases).

## Verification (includes the test build)

- Build and tests: run `run-all.ps1` (build, NUnit, pytest, Pyright) after adding the `py2cs` command and its tests.
- Dry run on GitHub: *Alpha release* with `dry_run` ticked on `develop`; check the wheel artifact's filename and that nothing is tagged or published.
- Ordering: `pip install --pre --dry-run --index-url https://test.pypi.org/simple/ bhom-schema` picks the newest alpha, and a plain install picks the beta.
- Live: untick `dry_run` once; confirm the TestPyPI project page, then re-run and confirm the second run skips.
- Guard: run against a state where `v{version}.0` exists and confirm it fails with the bump message.

## Trying the package in a new VS Code project

Do this after the first successful upload (the TestPyPI steps above). It shows what a user sees: wrong data types are underlined in the editor as they are typed, and rejected when the code runs.
The example class is `LineLike` of the test namespace `FixtureAlpha_oM`; its `Infinite` property is a `bool`.

1. **Install** Python 3.12 or later, and VS Code with the *Python* extension (it brings *Pylance*, which does the live type checking).
2. **Make the project.** Create an empty folder, for example `bhom-try`, and open it in VS Code (*File*, *Open Folder*).
3. **Make a virtual environment.** Open the terminal (*Terminal*, *New Terminal*) and run:

   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   If PowerShell refuses to run the script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.
4. **Select it.** Press `Ctrl+Shift+P`, run *Python: Select Interpreter*, and choose the one in `.\.venv`. The bottom right of the window then shows `3.12.x ('.venv')`.
5. **Install the alpha.** While the package is on TestPyPI only:

   ```powershell
   pip install --pre --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bhom-schema
   ```

   `--pre` is what picks the alpha. The extra index is where `pydantic` comes from. Once the package is on PyPI this is `pip install --pre bhom-schema`, and without `--pre` you get the beta.
   Check with `pip show bhom-schema`: the version should look like `10.1.0a2611031430`.
6. **Write the first file.** Create `try_schema.py`:

   ```python
   from bhom_schema.FixtureAlpha_oM.LineLike import LineLike

   line = LineLike(Infinite=True, Label="axis")
   print(line.Infinite)
   ```

   Run it with the play button or `python try_schema.py`. It prints `True`.
7. **See the error in the editor.** Change the line to a string where a `bool` belongs:

   ```python
   line = LineLike(Infinite="banana", Label="axis")
   ```

   Pylance underlines `"banana"` in red at once, with no run needed. Hover over it: *Argument of type "Literal['banana']" cannot be assigned to parameter "Infinite" of type "bool"*. The *Problems* panel (`Ctrl+Shift+M`) lists it too.
   Other wrong types show the same way, for example `Label=5` (should be `str`) or `Infinite=1.5`.
8. **See the error when it runs.** Run the file. pydantic rejects the value: `ValidationError: 1 validation error for LineLike`, `Infinite`, *Input should be a valid boolean, unable to interpret input*.
   Note that pydantic reads simple text such as `"true"` or `"yes"` as a boolean when it runs, so the run would accept them, but the editor still flags them. The editor check is the stricter one.
9. **Check the types come from the package.** Hover over `LineLike` and press `F12` (*Go to Definition*): it opens the generated `.venv\Lib\site-packages\bhom_schema\FixtureAlpha_oM\LineLike.py`. Type `line.` and the property list (`Start`, `End`, `Infinite`, `Label`) pops up.
10. **Optional: stricter checking.** For every type problem to show, not only argument types, add to `.vscode/settings.json`: `{ "python.analysis.typeCheckingMode": "standard" }` (or `"strict"`).

Expected results to record: the version installed, a screenshot of the red underline with its hover text, and the `ValidationError` text.

If the underline does not appear, check in this order: the interpreter is the `.venv` one (step 4); the package is installed in that venv (`pip show bhom-schema`); Pylance is enabled (the status bar shows *Pylance*, not *Jedi*); and the file is saved.
The package currently has no `py.typed` marker. Pylance still reads the types from the installed source, so the check works, but adding `py.typed` (and listing it under `package-data` in `pyproject.toml`) would declare the package as typed for every tool. That is a small change to add to the release workflow's checks.

## Trying the package in a Databricks notebook

Same example as in VS Code (`LineLike`, its `bool` property `Infinite`), then tables made from the classes with the helpers of `bhom_schema.tables` (see [Table-Helpers-Plan.md](Table-Helpers-Plan.md)) and read back into objects. Decided: the team's tables follow the BHoM field names, so a column is a property of the class and a row validates straight into an object. You decide which tables exist and how they link; the helpers do the mechanical work for one class at a time.

The helpers are in the package from the first alpha built after they were merged. Check with `from bhom_schema.tables import describe` in step 4; if it fails, the alpha you installed is older.

### Notebook steps

1. **Compute.** Attach the notebook to compute with Python 3.12 or later (the package needs it): Databricks Runtime 16.0 or later, or serverless with an environment version that has 3.12. Check in a cell: `import sys; print(sys.version)`. The compute needs outbound access to test.pypi.org and pypi.org. If it has none, put the wheel in a Unity Catalog volume and install it with `%pip install /Volumes/<catalog>/<schema>/<volume>/bhom_schema-<version>-py3-none-any.whl` (the wheel is the artifact of an alpha run, or the file on a GitHub Release for a beta).
2. **Cell 1, install** (a `%pip` cell must be on its own):

   ```
   %pip install --pre --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bhom-schema
   ```

   **Cell 2, restart Python** so the notebook sees the package:

   ```python
   dbutils.library.restartPython()
   ```

   Once the package is on PyPI the install is `%pip install --pre bhom-schema`. To pin a version for a job, use `bhom-schema==10.1.0a2611031430`.
3. **Cell 3, the same example as in VS Code:**

   ```python
   from bhom_schema.FixtureAlpha_oM.LineLike import LineLike

   line = LineLike(Infinite="banana", Label="axis")
   print(line.Infinite)
   ```

   Expected: the cell fails with `ValidationError: 1 validation error for LineLike`, `Infinite`, *Input should be a valid boolean, unable to interpret input*. That error is the pass criterion in a notebook. The red underline of VS Code is not promised here: the notebook editor does not run Pylance. To see the underline against Databricks, use the same `.venv` project as in VS Code, or the Databricks extension for VS Code with Databricks Connect.
   Then change `"banana"` to `True` and run again: it prints `True`.
4. **Cell 4, which fields need a decision.** A field with a primitive type (`bool`, `int`, `float`, `str`, dates, enums, lists and dicts of those) gets a column by itself. Any other field is never mapped silently:

   ```python
   from bhom_schema.FixtureAlpha_oM.PointLike import PointLike
   from bhom_schema.tables import Json, Ref, Skip, Struct, check_table, custom_fields, describe

   print(custom_fields(LineLike))

   for column in describe(LineLike):
       print(column.name, column.type, column.decision)
   ```

   Expected: `Start` and `End`, both `PointLike`. `describe` shows the table that would be made: `Start` and `End` have no type and the decision `undecided`, and the other columns (`_id`, `_bhomVersion`, `Infinite`, `Label`) are mapped. Creating the table now would fail with an error that names the two fields and the four choices:

   | Decision | What is stored |
   |---|---|
   | `Ref(table)` | `<Field>_id`, the id of a row of another table (a table per class, linked by id) |
   | `Struct()` | a `STRUCT` column holding the object's own fields (and an `ARRAY` of them for a list of classes) |
   | `Json()` | the object as JSON text in a `STRING` column |
   | `Skip()` | nothing; a row that is read keeps the default of the field |
5. **Cell 5, make the tables, one table per class.** Put your own catalog and schema in the prefix (you need *USE SCHEMA* and *CREATE TABLE* on it). The line stores the id of its two points, and the points are rows of the `PointLike` table:

   ```python
   from bhom_schema.tables import rows_to_objects
   from bhom_schema.tables.spark import create_table, fetch_by_ids, read_objects, read_rows, write_objects

   PREFIX = "student_area.vcl"
   POINTS = f"{PREFIX}.PointLike"
   LINES = f"{PREFIX}.LineLike"
   LINE_FIELDS = {"Start": Ref(POINTS), "End": Ref(POINTS)}

   print(create_table(spark, PointLike, POINTS))
   print(create_table(spark, LineLike, LINES, fields=LINE_FIELDS))
   ```

   Each call runs the statement and returns it, so it can also be pasted into a SQL warehouse, a pipeline or a migration script. Expect:

   ```sql
   CREATE TABLE IF NOT EXISTS `student_area`.`vcl`.`PointLike` (
     `_id` STRING NOT NULL COMMENT 'Key of the row.',
     `_bhomVersion` STRING COMMENT 'Optional version of BHoM used as part of automatic versioning and schema upgrades.',
     `X` DOUBLE,
     `Y` DOUBLE,
     `Z` DOUBLE
   )
   USING DELTA
   TBLPROPERTIES ('bhom.type' = 'BH.oM.FixtureAlpha.PointLike', 'bhom.schema_version' = '...')
   ```

   and the `LineLike` statement with `Start_id`, `End_id`, `Infinite` and `Label`, and the class summary as the table comment. Check with `display(spark.table(LINES))` or `DESCRIBE TABLE`.
6. **Cell 6, link the tables by hand (optional).** The helpers do not write constraints; you decide whether to add them. Unity Catalog records them as informational (it does not enforce them), which documents the link for readers and tools:

   ```python
   spark.sql(f"ALTER TABLE {POINTS} ADD CONSTRAINT point_pk PRIMARY KEY (`_id`)")
   spark.sql(f"ALTER TABLE {LINES} ADD CONSTRAINT line_pk PRIMARY KEY (`_id`)")
   spark.sql(f"ALTER TABLE {LINES} ADD CONSTRAINT line_start_fk FOREIGN KEY (`Start_id`) REFERENCES {POINTS} (`_id`)")
   spark.sql(f"ALTER TABLE {LINES} ADD CONSTRAINT line_end_fk FOREIGN KEY (`End_id`) REFERENCES {POINTS} (`_id`)")
   ```

   A primary key column must be `NOT NULL`, and `_id` is.
7. **Cell 7, fill them from objects** (a few rows). The points are real `PointLike` objects, so each one is validated. `write_objects` writes one class into one table and returns the `_id` of each row it wrote, which is what the line rows need:

   ```python
   objects = [
       LineLike(Start=PointLike(X=i), End=PointLike(X=i + 1, Y=2), Infinite=bool(i % 2), Label=f"line-{i}")
       for i in range(10)
   ]

   starts = write_objects(spark, [line.Start for line in objects], POINTS)
   ends = write_objects(spark, [line.End for line in objects], POINTS)
   write_objects(spark, objects, LINES, fields=LINE_FIELDS, ids=[{"Start": start, "End": end} for start, end in zip(starts, ends)])

   print(spark.table(POINTS).count(), spark.table(LINES).count())
   ```

   A wrong value, such as `PointLike(X="north")`, fails at the constructor, and a value the column cannot hold (an integer that does not fit its `INT`, a `datetime` with a time zone) raises before anything is written, naming the field. Expect `20 10`: two points per line.
8. **Cell 8, fill them at scale.** A large set is built in Spark itself, never as Python objects. The ids must be the same in the point rows and the line rows, so they are made from the row number (a random id such as `uuid()` would be different each time the query runs). The batch text keeps the ids of two runs apart:

   ```python
   import uuid

   batch = uuid.uuid4().hex[:8]
   base = spark.range(1_000_000).selectExpr(
       "id",
       f"concat('{batch}-start-', id) as start_id",
       f"concat('{batch}-end-', id) as end_id",
   )
   no_version = "cast(null as string) as _bhomVersion"

   base.selectExpr("start_id as _id", no_version, "cast(id as double) as X", "0D as Y", "0D as Z").write.insertInto(POINTS)
   base.selectExpr("end_id as _id", no_version, "cast(id as double) + 1D as X", "0D as Y", "0D as Z").write.insertInto(POINTS)
   base.selectExpr(f"concat('{batch}-line-', id) as _id", no_version, "start_id as Start_id", "end_id as End_id", "false as Infinite", "concat('line-', id) as Label").write.insertInto(LINES)

   print(spark.table(POINTS).count(), spark.table(LINES).count())
   ```

   The columns of each query follow the order of the table (`insertInto` goes by position). Expect two million more points and one million more lines.
9. **Cell 9, read the tables into a list of `LineLike`.** Reading is one table at a time, so the step from the lines to their points stays visible: read the line rows, fetch only the point rows they name, build the points keyed by id, then build the lines with those points:

   ```python
   line_rows = read_rows(spark, LINES, limit=1000)
   point_ids = {row["Start_id"] for row in line_rows} | {row["End_id"] for row in line_rows}
   points = rows_to_objects(PointLike, fetch_by_ids(spark, POINTS, point_ids), keyed=True)
   found = rows_to_objects(LineLike, line_rows, fields=LINE_FIELDS, held={"Start": points, "End": points})

   print(len(found), type(found[0]).__name__)
   print(type(found[0].Start).__name__, isinstance(found[0].End, PointLike))
   print(found[0].Start.X, found[0].Infinite)
   ```

   Every row is validated, so a column of the wrong type raises the same `ValidationError` as in step 3. A NULL in a column reads as the default of the property. `Start` and `End` are real `PointLike` objects (the second print shows `PointLike True`), not dictionaries. To keep the bad rows instead of stopping at the first, pass `errors="collect"` to `rows_to_objects`: it then returns the objects and a `RowError` per bad row.
   `read_rows(..., limit=...)` and `where="..."` take a slice, because the rows are collected to the notebook; read a table with millions of rows in batches, not in one go.
10. **Cell 10, the same line with the points inside the row (`Struct`).** If the points are only ever stored inside their line, one table is enough, and the decision for the two fields is the only difference:

    ```python
    LINES_STRUCT = f"{PREFIX}.LineLikeStruct"
    STRUCT_FIELDS = {"Start": Struct(), "End": Struct()}

    print(create_table(spark, LineLike, LINES_STRUCT, fields=STRUCT_FIELDS))
    write_objects(spark, objects, LINES_STRUCT, fields=STRUCT_FIELDS)

    back = read_objects(spark, LineLike, LINES_STRUCT, fields=STRUCT_FIELDS)
    print(len(back), back[0].Start)
    print(sorted(line.Label for line in back) == sorted(line.Label for line in objects))
    ```

    Expect the `Start` column to be `STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE>`, `10`, a `PointLike` and `True`.
11. **Cell 11, will this table read as this class?** For a table that already exists (made by hand, or by an older alpha), compare its columns with the class before reading anything:

    ```python
    columns = {}
    for row in spark.sql(f"DESCRIBE TABLE {LINES}").collect():
        if not row.col_name or row.col_name.startswith("#"):
            break

        columns[row.col_name] = row.data_type

    check = check_table(LineLike, columns, fields=LINE_FIELDS)
    print(check.ok)
    print(check)
    ```

    Expect `True` and `the table matches the class`. When a newer alpha adds a property to a class, the check lists the new column as missing, and `add_columns_sql(check, LINES)` gives the `ALTER TABLE ... ADD COLUMNS` for it (run it yourself); rows written before read the new property as its default.
12. **Clean up** when done: `spark.sql(f"DROP TABLE IF EXISTS {POINTS}")` and the same for `LINES` and `LINES_STRUCT`.

Expected results to record: the Python version, the installed package version (`%pip show bhom-schema`), the `ValidationError` text from step 3, the output of step 4, the printed `CREATE TABLE` statements, the row counts after step 7 (`20 10`) and after step 8, the output of steps 9 and 10, and the output of step 11.

Not yet tested in a workspace: the Spark steps (5 to 11) have not been run on Databricks. The helpers are tested in plain Python against a stand-in `SparkSession` that keeps tables in memory (the SQL text, the rows, the DDL schema, the writes, the reads and the round trip of `LineLike` through both layouts). What that cannot show is whether Databricks accepts the statements and the `createDataFrame` rows, and whether the informational constraints of step 6 are accepted; this notebook is that check.

### What the helpers do not cover

- A generic class (`Wrapper_1`) is refused: a table cannot record which type its rows were written with.
- A field typed with an interface can be stored as `Json()` (the JSON carries `_t`, so it reads back as the right class) or as a `Ref` to a table of your choice, but not as a `Struct`.
- `Color` and other classes that are not generated are custom fields like any other, so they need a decision.
- A list of classes is an `ARRAY` of `STRUCT` (`Struct()`) or JSON text (`Json()`); a table of its own for the elements is built by you from `create_table` and the ids of the rows.
- Primary keys, foreign keys and `CHECK` constraints are written by you (step 6), and so are merges and upserts.
- A table is named by you, so two classes with the same name in different assemblies do not collide, but the name is not checked against the class: `check_table` is how to find a table that does not match.
- Whole-table reads are collected to the notebook. A join-based read that fills `held` in Spark, and validating a big table in parallel (`mapInPandas`), are follow-ups.
- Adding `py.typed` to the package, so every tool treats the helpers as typed.
