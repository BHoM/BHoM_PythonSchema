# Testing guide: reading `.ci/unit-tests`

This explains how the tests in [`.ci/unit-tests`](../.ci/unit-tests) are organised and how Python testing (pytest) works, for
someone who knows NUnit but has not written Python tests. For the Python language basics used in the code, see
[Python-Packages-Primer.md](Python-Packages-Primer.md).

## 1. The big picture

The project has two converters, so the tests have two halves that feed each other:

```
 NUnit (C#)                                           pytest (Python)
 ----------                                           ---------------
 1. generate Python from C# types ----writes----->  _output/fixtures/bhom_schema
    (fixture assemblies + real BHoM)                 _output/spike/bhom_schema
                                                              |
                                     test_fixtures, test_spike: import it, use it, run Pyright on it
                                     test_alignment: compare it with the C# manifest
                                                              |
 2. py2cs drafts C# from that Python --writes--->    _output/roundtrip/*/*.cs
 3. NUnit compiles the C# with Roslyn  ----------->  draft-manifest.json
                                                              |
                                     test_alignment: draft-manifest must equal the original
```

So the C# tests are not only checks; they **produce the input** the Python tests read. That is why the order matters and why
`run-all.ps1` exists.

## 2. What is in the folder

| Path | What it is |
|---|---|
| `run-all.ps1` | Runs every stage in the right order. Use this unless you are working on one part. |
| `csharp/PythonSchemaGeneration.Tests/` | The NUnit tests (44 tests). |
| `csharp/Fixtures/` | The fake oM assemblies `FixtureAlpha_oM` and `FixtureBeta_oM`: the test classes of the generator, in this repository. They started as a copy of [CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test) and are separate from it: that repository is where the loop is rehearsed, and changes there never reach these tests. Their assembly `Description` names CSharpSchema_Test on purpose, because the generator reads the owning repository from it. See section 3. |
| `python/` | The pytest tests (about 73 test cases) in four folders: `test_py2cs`, `test_fixtures`, `test_spike`, `test_alignment`. |
| `python/support.py` | Shared helpers for the pytest folders. |
| `golden/` | Committed "expected output" files. See section 6. |
| `github-fixtures/repo-listing.json` | A recorded list of which repository owns which assembly folder, so tests need no network. |
| `_output/` | Everything the tests generate. Git-ignored; safe to delete, it is rebuilt by the next run. |

## 3. Two kinds of test input

| Tier | Input | Needs | Where |
|---|---|---|---|
| **Fixtures** | `FixtureAlpha_oM` and `FixtureBeta_oM` in `csharp/Fixtures`, small assemblies written for the tests. Each type is there to provoke one situation: an enum member named `None`, an interface chain, a generic, a same-named type in two assemblies, a reference cycle, and so on. | Only `BHoM.dll` | Run anywhere |
| **Real types** | The actual BHoM oM, for example `ProjectIdentification`, `Line` and `Bar`. | The BHoM assemblies installed in `%ProgramData%\BHoM\Assemblies` | Ignored locally if missing; fail in CI |

The fixtures exist so the logic can be tested precisely and without depending on whatever the BHoM `develop` branch looks like
today. The real-type tests then prove it works on the real thing.

## 4. NUnit side (`csharp/PythonSchemaGeneration.Tests`)

You know this style already. Where to look:

- `TestSupport.cs`: helpers. `TestPaths` finds the repo root, `FixtureOutput` generates the fixture package once and shares it, and
  `RealAssemblies` checks the real assemblies exist (`RequireOrSkip` ignores the test locally, fails it in CI).
- `FixtureExtractionTests.cs`: what the generator produces for each fixture type (bases, defaults, type mapping, generics,
  metadata, paths, cycles). Most tests assert that the generated Python text contains an expected line.
- `RealTypeTests.cs`: the same ideas against the real spike types. Marked `[Category("RealTypes")]`.
- `GoldenAndWorkflowTests.cs`: golden-file comparisons, deterministic output, clean-up of stale files, and a guard that the
  generator does not depend on the JSON schema repo.
- `RoundTripTests.cs`: compiles the drafted C# with Roslyn and writes `draft-manifest.json`. Marked `[Category("RoundTrip")]`.
- `DocumentationTests.cs`: every C# method and constructor under `.ci` has a `[Description]` saying what it does and where it fits in the
  workflow. The Python counterpart is `test_py2cs/test_documentation.py`, which checks every function for a docstring. Golden expected-output
  files are skipped. A new method fails these tests until it is described.

Run only some of them with a filter:

```powershell
dotnet test .ci/generation/PythonSchemaGeneration.sln -c Release --filter "Category=RealTypes"
```

## 5. pytest in ten minutes

pytest finds tests by **naming convention**, there are no attributes:

- files named `test_*.py`
- functions named `test_*` inside them

```python
def test_diff_property_added(tmp_path):
    ...
    assert diff.changes[0].kind == "modified"
```

| NUnit | pytest |
|---|---|
| `[Test]` | any function named `test_...` |
| `Assert.That(a, Is.EqualTo(b))` | `assert a == b` |
| `Assert.Throws<T>(...)` | `with pytest.raises(T):` |
| `[TestCase(1)] [TestCase(2)]` | `@pytest.mark.parametrize("name", [1, 2])`, one test case per value |
| `[SetUp]`, `[OneTimeSetUp]` | **fixtures** (below) |
| `Assert.Ignore(...)` | `pytest.skip("reason")` |
| `[Category("X")]` | `@pytest.mark.x` markers |
| `[TestCaseSource]` | `parametrize` with a list |

**Plain `assert`.** pytest rewrites it so that a failure shows both sides, so you never write `Assert.AreEqual`. A message can
follow a comma: `assert problems == [], "\n".join(problems)`.

**Fixtures.** A fixture is a function marked `@pytest.fixture` that provides something a test needs. A test asks for it simply by
naming it as a parameter; pytest calls the fixture and passes the result in. Built-in ones you will see:

- `tmp_path`: a fresh empty temporary folder (a `Path`) for each test. Most `test_py2cs` tests build a small fake package or C# tree
  in it and never touch the real repository.
- `capsys`: captures what the code prints, so a test can check console output.

Custom fixtures live in `conftest.py` files. pytest loads `conftest.py` automatically for the tests in the same folder. For example
`test_fixtures/conftest.py`:

```python
@pytest.fixture(scope="session", autouse=True)
def fixtures_package():
    package = require_output("fixtures")
    attach(package)
    return package
```

- `scope="session"`: run once for the whole test run, not once per test.
- `autouse=True`: apply to every test in the folder without being requested. It makes the generated package importable before any
  test runs, and the value it returns can still be requested by name, which is how `test_every_module_imports...(fixtures_package)`
  receives the folder.

**Parametrize.** `test_manifest_alignment.py` runs one function twice, once for `"fixtures"` and once for `"spike"`; the report
lists them as two test cases, which is why the case count is higher than the number of functions.

**Skip and fail.** `support.require_output` returns the generated folder, or skips the test locally if `dotnet test` has not run
yet, or fails it when the `CI` environment variable is `true`. That is the Python twin of `RealAssemblies.RequireOrSkip`.

## 6. Golden files

A golden file is a committed copy of expected output. The test generates the output, compares it with the file, and fails on any
difference. Use `golden/` when exact text matters:

- `golden/fixtures/`: the Python generated for eight fixture classes, one per output shape (a class with many field kinds, a reference cycle, an interface, a get-only class, a flags enum, a plain enum, a generic, a same-named class in another assembly). The list is `GoldenTests.m_PinnedClasses`; add a class only for a shape no listed class shows. The manifest has no golden file: the alignment tests cover it.
- `golden/spike/`: a small, stable real type (`GradientCenteringOptions`).
- `golden/py2cs/`: the C# that `py2cs` writes for small example classes.

When you change the generator on purpose, regenerate them with the environment variable `UPDATE_GOLDEN=1`, then **read the diff**
in git before committing. A golden file you did not review proves nothing.

```powershell
$env:UPDATE_GOLDEN = "1"
dotnet test .ci/generation/PythonSchemaGeneration.sln -c Release
Remove-Item Env:UPDATE_GOLDEN
```

The same variable works for the Python golden tests (`test_py2cs`).

## 7. The four pytest folders

They are run as **separate pytest sessions**, because the fixture and spike packages both contain folders such as `BHoM` and
cannot be imported side by side in one process.

| Folder | Needs | What it checks |
|---|---|---|
| `test_py2cs/` | nothing generated | The Python to C# converter on tiny hand-built packages: reading, diff, C# emission against golden files, finding and placing files, repo resolution, the planned output, the command line. `helpers.py` has the builders (`module(...)` writes source in the generated style, `package(...)` writes it to disk). Two tests use the real `C:\Github\dKoP_Toolkit` clone and are skipped if it is missing. |
| `test_fixtures/` | `_output/fixtures` | The generated fixture Python **behaves** correctly: every module imports, Pyright strict is clean, interface fields accept and reject the right objects, defaults are not shared, enums, generics, cycles, same-named classes. |
| `test_spike/` | `_output/spike` | The same ideas on the real spike types. `test_json.py` also checks the JSON: round trips, a JSON Schema for every class, and (with a read-only clone of BHoM_JSONSchema next to this repository, or at `BHOM_JSONSCHEMA_ROOT`) that what Python writes validates against the published schemas |
| `test_support/` | nothing generated | The hand-written support package alone, with small stand-in classes: `_t`, `_bhomVersion`, interface fields (`Polymorphic`), enums by name, and their JSON Schema |
| `test_alignment/` | both outputs | Two structural checks: the Python read back by `py2cs` equals what C# reflection reported, and the drafted-then-compiled C# equals the original. |

`test_fixtures` and `test_spike` also run **Pyright** on the generated package by launching it as a separate process
(`support.run_pyright`). That is a test of the generated code's types, not of `py2cs`.

## 8. Running things

Everything, in the right order:

```powershell
.ci\unit-tests\run-all.ps1
```

Its stages are: build; NUnit (which generates `_output`); `py2cs drafts`; NUnit round trip; the four pytest folders; Pyright.

One part, from the repository root with the virtual environment's Python:

```powershell
.venv\Scripts\python -m pytest .ci/unit-tests/python/test_py2cs -q
```

Useful options:

| Command | Meaning |
|---|---|
| `... -k project` | only tests whose name contains `project` |
| `... -x` | stop at the first failure |
| `... -vv` | show every test name and fuller diffs |
| `... path/to/test_file.py::test_name` | run exactly one test |
| `... -s` | show `print` output while running |

If a pytest folder reports `skipped`, the message says what is missing; most often you have not run `dotnet test` yet. Locally,
real-type tests are ignored when a BHoM assembly is missing, and the preflight at the start of `run-all.ps1` lists which.

## 9. How to read one test, step by step

Take `test_diff_property_added` in `python/test_py2cs/test_reader_and_diff.py`:

1. It asks for `tmp_path`, an empty folder.
2. It builds a base package and a head package inside it (`demo_package(...)`); the head has one extra field.
3. It reads both with `read_package` and calls `diff_manifests`.
4. It asserts the result is one change, `modified`, saying `property added: string ProjectNumber`.

Almost every test follows **arrange, act, assert**. When a test fails, the report prints the values on both sides of the `assert`.

## 10. Where to add a test

| You changed | Add the test in |
|---|---|
| How a C# type becomes Python text | `FixtureExtractionTests.cs` (add a type to `FixtureAlpha_oM` in `csharp/Fixtures` if you need a new situation, then regenerate the golden files) |
| Behaviour of the generated Python classes | `test_fixtures/test_generated_fixtures.py` |
| Something specific to a real BHoM type | `RealTypeTests.cs` and `test_spike/` |
| The Python to C# converter | `test_py2cs/` |
| The shape of the manifest shared by both sides | `test_alignment/` |

After a change, run `run-all.ps1`. Per the project rules it must finish green, including the build, before the work is done.
