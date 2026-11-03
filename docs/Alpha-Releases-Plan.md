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

Same example as in VS Code (`LineLike`, its `bool` property `Infinite`), then a table made from the class and read back into objects. Decided: the team's tables follow the BHoM field names, so a column is a property of the class and a row validates straight into an object.

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
4. **Cell 4, the table helper.** It derives the column definitions from the class, so the table and the class cannot drift apart. It is plain Python (no Spark needed) and is a good candidate to move into the package later as `bhom_schema.tables`.

   ```python
   import types
   import typing
   from pydantic import BaseModel

   SCALARS = {bool: "BOOLEAN", int: "BIGINT", float: "DOUBLE", str: "STRING"}
   # bhom_version is the optional _bhomVersion of the JSON: not a column
   SKIPPED = {"bhom_version"}

   def spark_type(annotation):
       """The Spark SQL type of a property: nested classes become STRUCT, lists ARRAY, Optional is just nullable."""
       origin = typing.get_origin(annotation)
       if origin in (typing.Union, types.UnionType):
           options = [a for a in typing.get_args(annotation) if a is not type(None)]
           if len(options) != 1:
               raise NotImplementedError(f"{annotation} is a choice between types; it has no single column type")
           return spark_type(options[0])
       if origin is list:
           return f"ARRAY<{spark_type(typing.get_args(annotation)[0])}>"
       if isinstance(annotation, type) and issubclass(annotation, BaseModel):
           return "STRUCT<" + ", ".join(f"`{name}`: {spark_type(field.annotation)}" for name, field in annotation.model_fields.items() if name not in SKIPPED) + ">"
       if annotation in SCALARS:
           return SCALARS[annotation]
       raise NotImplementedError(f"{annotation} has no column type yet (enums, ids and interface-typed properties are not supported)")

   def columns(model):
       """The column list of a class, as Spark SQL DDL."""
       return ", ".join(f"`{name}` {spark_type(field.annotation)}" for name, field in model.model_fields.items() if name not in SKIPPED)

   def create_table_sql(model, table):
       """The CREATE TABLE statement for a class."""
       return f"CREATE TABLE IF NOT EXISTS {table} ({columns(model)}) USING DELTA"

   def plain(value):
       """Takes the type tags (_t, _bhomVersion) out of a dumped object: the table holds the properties only."""
       if isinstance(value, dict):
           return {key: plain(item) for key, item in value.items() if key not in ("_t", "_bhomVersion")}
       if isinstance(value, list):
           return [plain(item) for item in value]
       return value

   def to_rows(objects):
       """Objects to rows for spark.createDataFrame."""
       return [plain(item.model_dump()) for item in objects]

   def from_rows(model, rows):
       """Spark rows to objects of the class; every row is validated."""
       return [model.model_validate(row.asDict(recursive=True)) for row in rows]
   ```

5. **Cell 5, make the table.** Put your own catalog and schema in the name (you need *USE SCHEMA* and *CREATE TABLE* on it):

   ```python
   TABLE = "main.default.line_like"

   sql = create_table_sql(LineLike, TABLE)
   print(sql)
   spark.sql(sql)
   ```

   The statement printed is the SQL that makes the same table, so it can be pasted into a SQL warehouse, a pipeline or a migration script:

   ```sql
   CREATE TABLE IF NOT EXISTS main.default.line_like (`Start` STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE>, `End` STRUCT<`X`: DOUBLE, `Y`: DOUBLE, `Z`: DOUBLE>, `Infinite` BOOLEAN, `Label` STRING) USING DELTA
   ```

   `PointLike` is a nested class, so `Start` and `End` are one `STRUCT` column each. Check it with `display(spark.table(TABLE))` or `DESCRIBE TABLE main.default.line_like`.
6. **Cell 6, fill it from objects** (a few rows; the schema comes from the table's own DDL):

   ```python
   lines = [LineLike(Infinite=bool(i % 2), Label=f"line-{i}") for i in range(10)]
   spark.createDataFrame(to_rows(lines), schema=columns(LineLike)).write.mode("append").saveAsTable(TABLE)
   ```

   A wrong value fails at `LineLike(...)`, before anything is written, so a bad object never reaches the table.
7. **Cell 7, fill it at scale.** A large set is built in Spark itself, never as Python objects. The columns must be in the same order and of the same types as the class:

   ```python
   spark.range(1_000_000).selectExpr(
       "named_struct('X', cast(id as double), 'Y', 0D, 'Z', 0D) as Start",
       "named_struct('X', cast(id as double) + 1D, 'Y', 0D, 'Z', 0D) as End",
       "false as Infinite",
       "concat('line-', id) as Label",
   ).write.insertInto(TABLE)

   print(spark.table(TABLE).count())
   ```

8. **Cell 8, read the table into a list of `LineLike`:**

   ```python
   rows = spark.table(TABLE).limit(1000).collect()
   lines = from_rows(LineLike, rows)

   print(len(lines), type(lines[0]).__name__)
   print(lines[0].Start.X, lines[0].Infinite)
   ```

   With columns that follow the class, every row validates; the first line prints as a `LineLike` with a `PointLike` in `Start`. A column of the wrong type, or a null in a property that is not optional, raises the same `ValidationError` as in step 3, naming the property. Reading the whole table this way pulls every row onto the driver, so for millions of rows take a slice (`limit`, a `WHERE` on a key) or walk the table with `spark.table(TABLE).toLocalIterator()` instead of `collect()`.
9. **Clean up** when done: `spark.sql(f"DROP TABLE IF EXISTS {TABLE}")`.

Expected results to record: the Python version, the installed package version (`%pip show bhom-schema`), the `ValidationError` text from step 3, the printed `CREATE TABLE` statement, the row count after step 7, and the output of step 8.

Not yet tested in a workspace: the Spark parts (steps 5 to 9) have not been run on Databricks. The helper's SQL, its rows and the read back into objects were checked in plain Python against `LineLike`.

### What the helper does not cover (follow-up plan)

The helper handles the simple shapes: `bool`, `int`, `float`, `str`, nested classes, lists, and optional properties. Every other generated class meets one of the things it refuses with a clear error: enums (a column of the name, as `SupportKind`), ids (`BHoM_Guid`, which `Beam` has through `BHoMObject`), interface-typed properties (they need `_t` to pick the class, so a `_t` field in the struct), and quantities. The follow-up plan, once this works on a workspace:

- Move the helper into the package as `bhom_schema.tables` with `pyspark` as an optional extra, and cover those types.
- Generate the `CREATE TABLE` statements for a whole namespace at once, so a catalog schema can be built from the package in one step.
- Validate a big table in parallel (`mapInPandas`) and report the invalid rows instead of failing on the first.
- Write a table's rows back from objects with `_t` where the property is an interface.
