# Converting all oM classes to Python, and checking the result

This is a procedure for a full test conversion, plus what a trial run on 2026-10-26 showed. The full-corpus run and hardening is
phase 7 of the coding plan; section 5 records the problems found and fixed so far.

## 1. What actually gets converted

The generator reads **compiled assemblies**, not the C# source. It converts every oM assembly it finds in
`%ProgramData%\BHoM\Assemblies` whose description points at `github.com/BHoM/`. Two consequences:

- The result is only as current as the last build. Build the repos you care about first (for `C:\Github\BHoM`, build
  `BHoM.sln`; the post-build step copies the dlls to `ProgramData`).
- You get **every installed BHoM-organisation oM**, not only the ones in `C:\Github\BHoM`. On this machine that was 1,800 types from
  about 70 assemblies, including toolkits such as `dKoP_oM`, `Revit_oM` and `Excel_oM`. There is no repo filter option yet. To look
  at only the main repo, filter afterwards on `repo == "BHoM/BHoM"` in `manifest.json`.

## 2. Run the conversion

Build the generator (from the repository root):

```powershell
dotnet build .ci/generation/PythonSchemaGeneration.sln -c Release
```

Prepare an output package folder. The generated modules import the hand-written `_support` package, so copy it in first:

```powershell
New-Item -ItemType Directory -Force .ci/unit-tests/_output/corpus/bhom_schema
Copy-Item src/bhom_schema/__init__.py .ci/unit-tests/_output/corpus/bhom_schema/
Copy-Item -Recurse -Force src/bhom_schema/_support .ci/unit-tests/_output/corpus/bhom_schema/
```

All commands in this guide are for PowerShell (the default terminal on Windows), run one line at a time from the repository root.

Convert everything (no `--types` filter means all types):

```powershell
dotnet .ci/generation/PythonSchemaGeneration/bin/Release/net8.0/PythonSchemaGeneration.dll --output .ci/unit-tests/_output/corpus/bhom_schema --manifest .ci/unit-tests/_output/corpus/manifest.json --report .ci/unit-tests/_output/corpus/report.txt
```

It takes about 20 seconds and prints one summary line, for example `Generated 1800 of 1800 types, wrote 2033 files, 165 warnings.`
`.ci/unit-tests/_output` is git-ignored, so this is safe to repeat. Running without a filter also **deletes** files of the written
assemblies that are no longer generated, so only point `--output` at `src/bhom_schema` when you mean to update the real package.

What you get:

| Output | Meaning |
|---|---|
| `bhom_schema/<Assembly>/<Namespace>/<Type>.py` | One file per C# type, plus empty `__init__.py` files |
| `manifest.json` | A language-neutral description of every generated type (name, bases, properties with C# types, defaults, enum members) |
| `report.txt` | Counts, the assemblies loaded or skipped, types in reference cycles, and every warning |

## 3. Checks, from cheapest to deepest

Run them in this order; each one catches a different kind of mistake.

### Check 1: the summary and the report

Open `report.txt`.

- `Types available` should equal `Types generated`. If not, some types failed to convert (the warning says why).
- `Types in reference cycles` is the number of types that import each other. The trial found 0.
- `Loaded assembly` / `Skipped assembly` lines show which dlls were used. A skipped one is usually not a BHoM-organisation oM.
- Read the warning summary. Group them by kind (see section 5); a **new** kind after a BHoM change is the signal that the generator
  needs an update.

### Check 2: compare with the JSON schema repo

`BHoM_JSONSchema` is generated from the same assemblies with the same folder rule, so the two repos should list the same types.
Compare the set of types per assembly folder. Save this as a scratch script and run it with the virtual environment's Python:

```python
from pathlib import Path
python = Path(r".ci/unit-tests/_output/corpus/bhom_schema")
json_root = Path(r"C:\Github\BHoM_JSONSchema")
def names(root, suffix):
    found = set()
    for file in root.rglob("*" + suffix):
        parts = file.relative_to(root).parts
        if parts[0].startswith((".", "_")) or parts[0] in ("bhom_schema",) or file.name == "__init__.py":
            continue
        found.add("/".join(parts)[: -len(suffix)].replace("`", "_"))
    return found
only_python = names(python, ".py") - names(json_root, ".json")
only_json = names(json_root, ".json") - names(python, ".py")
print(len(only_python), "only in Python;", len(only_json), "only in JSON")
print(sorted(only_python)[:20])
print(sorted(only_json)[:20])
```

Differences are expected for assemblies one repo has and the other does not (the JSON repo is built from a different set of
repositories) and for a different build date; look at whether the differences cluster in whole assemblies (fine) or are single types
inside an assembly both have (investigate).

### Check 3: every module imports

Import every generated module and report the failures. This catches invalid Python, bad names, wrong import order and circular
imports. Scratch script, run from the repository root:

```python
import importlib, sys, pathlib
root = pathlib.Path(".ci/unit-tests/_output/corpus").resolve()
sys.path.insert(0, str(root))
failures = []
for path in sorted((root / "bhom_schema").rglob("*.py")):
    if path.name == "__init__.py" or "_support" in path.parts:
        continue
    module = ".".join(path.relative_to(root).with_suffix("").parts)
    try:
        importlib.import_module(module)
    except Exception as error:
        failures.append((module, type(error).__name__, str(error)[:100]))
print(len(failures), "failures")
for failure in failures:
    print(failure)
```

Run it with `.venv\Scripts\python`. It took about 4 seconds for 1,800 modules.

### Check 4: type-check the whole package

Pyright in strict mode finds wrong annotations and defaults that do not match their types. Put a `pyrightconfig.json` in the output
folder:

```json
{ "include": ["bhom_schema"], "typeCheckingMode": "strict", "pythonVersion": "3.12", "extraPaths": ["."] }
```

```powershell
$root = (Get-Location).Path
Set-Location .ci/unit-tests/_output/corpus
& "$root\.venv\Scripts\pyright.exe" --pythonpath "$root\.venv\Scripts\python.exe"
Set-Location $root
```

It took about 17 seconds. The goal is `0 errors`.

### Check 5: structural comparison with the C# reflection

The C# side wrote `manifest.json` from reflection. The Python reader can read the generated files back and the two must agree
(names, bases, property types, defaults, enum members). This is the strongest check that nothing was lost or mis-written. It is
verified on the fixtures and the 11 spike types by `test_alignment`, but **not yet run on the full corpus**, so treat discrepancies
as findings.

```python
import sys
from pathlib import Path
sys.path.insert(0, ".ci/generation")
from py2cs.compare import compare_manifests
from py2cs.model import load_manifest
from py2cs.reader import read_package
base = Path(".ci/unit-tests/_output/corpus")
problems = compare_manifests(load_manifest(base / "manifest.json"), read_package(base / "bhom_schema"), allow_extra=False)
print(len(problems), "problems")
print("\n".join(problems[:40]))
```

### Check 6 (optional, heavier): the Python to C# round trip

Draft C# from the generated Python and compile it. Compile errors point at types whose Python could not be turned back into valid C#.

```powershell
$env:PYTHONPATH = ".ci/generation"
.venv\Scripts\python -m py2cs drafts --root .ci/unit-tests/_output/corpus/bhom_schema --out .ci/unit-tests/_output/roundtrip/corpus
```

The Roslyn test that compiles the drafts currently covers only the fixtures and the spike set (`RoundTripTests`), so compiling the
whole corpus needs a new test case. Expect work here; it is not a required check for the Python output.

### Check 7: read a few files yourself

Automated checks cannot tell whether a file is a *good* Python class. Open these in
`.ci/unit-tests/_output/corpus/bhom_schema/` and compare with the C# source:

| File | What to look for |
|---|---|
| `dKoP_oM/ProjectIdentification.py` | Four `str` fields defaulting to `''`, base `IdKoPObject`, `__bhom__` with repo `BHoM/dKoP_Toolkit` |
| `Geometry_oM/Line.py` and `Curve` types | Interface bases in a valid order, default `Point()` objects |
| `Structure_oM/Elements/Bar.py` | Quantity markers (for example `Quantity('Angle', ...)`), enum fields |
| An enum with a member named `None` (for example `Graphics_oM/Enums/GradientCenteringOptions.py`) | Member renamed `None_` and recorded in `renamed_members` |
| `BHoM/BHoMGroup_1.py` | Generic class with a bound |
| A class whose C# properties use `HashSet<T>` of objects | Falls back to `list[...]` with a `ClrType` marker |

## 4. What "correct" means (suggested pass criteria)

1. Every available type is generated, and the number of warnings is stable between runs (no new kinds of warning).
2. All modules import.
3. Pyright strict reports 0 errors.
4. The structural comparison reports 0 problems.
5. The type list matches the JSON schema repo for the assemblies both contain.
6. Your hand review of the sample files shows what the C# says.

## 5. What the trial runs showed

Both runs used the 1,800 types installed on this machine (2,033 files including `__init__.py`, about 20 s, 0 types in reference cycles).

| Measure | First run (2026-10-26) | After the fixes below |
|---|---|---|
| Modules that import | 1,789 of 1,800 (11 failed) | **1,800 of 1,800** |
| Pyright strict | 6 errors | **0 errors** |
| Structural comparison (check 5) | not run | **0 problems** |
| Warnings | 165 | 181 |

The 16 extra warnings are deliberate: fields that used to crash on import are now reported as required (see the bugs below).

The 181 warnings, by kind:

| Count | Warning | Is it a problem? |
|---|---|---|
| 104 | A .NET type with no Python equivalent was mapped to `Any` (for example `System.IComparable`, `System.IO.FileAttributes`) | Acceptable for now. The original type is kept in a `ClrType` marker. |
| 32 | Base type `System.Attribute` dropped (the C# attribute classes such as `DisplayTextAttribute`) | Acceptable: the attribute classes are generated as plain classes. Consider excluding attribute classes from the output. |
| 16 | A default value could not be written in Python, so the field is required (for example `System.RuntimeType`) | Review: these fields become required in Python. |
| 14 | The default instance of a type cannot be created in Python because that type has a required field, so the field is required too (the `dKoP` part types holding `AdministrativeInformation`) | Follows from the `DFMACategory` row below; fixing that C# default removes it. |
| 6 | A default collection holds complex items, an empty one was used instead | Review: the default differs from C#. |
| 4 | A generic type could not be instantiated to read its defaults (`PriorityQueue<T>`, `Quantity<T>`) | The fields are then required; acceptable but note it. |
| 2 | `DFMACategory` default is the value 0, which is not a member of the enum | Real C# oddity: `Overview.DFMACategory` defaults to an undefined value, so Python makes it required. |
| 3 | Other (types with no Python equivalent in toolkits, a malformed base) | Review individually. |

### Bugs found by the first run, and what was done

All four were in the generator (not in the C# source) and are fixed, with regression fixtures in `FixtureAlpha_oM/Hardening.cs`:

| Symptom | Cause | Fix |
|---|---|---|
| `NameError: name 'Tree_1' is not defined` (`Tree_1`, `DomainTree_1`, `Graph`) | A generic class named itself in `Field(default_factory=dict[str, Tree_1[T]])`, evaluated while the class was still being defined | Defaults of collections that mention a type parameter are now `lambda: []`, `lambda: {}` or `lambda: set()` |
| `ValueError: 0 is not a valid DFMACategory` (8 `dKoP_oM` types) | The C# default is 0 but the enum has no member 0 | A default that is not an enum member (and the enum is not `[Flags]`) is dropped and reported: the field is required. A field whose default instance cannot be built is required too |
| Pyright: `list[str]` not assignable to `list[T]` (`VennDiagram_1`) | `default_factory=list[T]` was inferred wrongly | Same lambda fix as the first row |
| Pyright: `list[float]` not assignable to `list[list[float]]` (`TransformMatrix`) | A `double[,]` default was written as a flat list | Two-dimensional arrays are written as rows: `lambda: [[...], [...]]` |

Three more problems turned up while re-running and were fixed too:

| Symptom | Cause | Fix |
|---|---|---|
| Pyright: "TypeVar constraint type cannot be generic" (`IPanel_2`) | A bound that names another type parameter (`TOpening : IOpening<TEdge>`) is illegal in a Python type parameter | The other parameter is replaced by `Any`: `TOpening: IOpening_1[Any]` |
| `ReadOnlyDictionary<K, V>` read back as a list of tuples (`IEnvironmentalResult` base) | The type was missing from the dictionary list of the type mapper | Added; the structural comparison also ignores collection flavour in base type arguments, which carry no `ClrType` marker, and line-ending differences in descriptions |
| Empty folders left behind by a clean-up run | `OutputWriter` checked the parent instead of the sub-folder | Fixed (caught by the existing clean-up test) |

The golden files were regenerated: besides the intended default changes, the committed ones still said `2015 - 2025` while the generator writes `2015 - 2026`.

Check 6 (the Python to C# round trip on the full corpus) is still not run; the fixture and spike round trips pass, including the new fixture types.

## 6. After a clean result

To land the output in the real package, run the same command with `--output src/bhom_schema` (the `_support` folder is already
there and is never touched). Review the resulting diff in git before committing: a first full conversion adds about 2,000 files.
