# Converting all oM classes to Python, and checking the result

This is a procedure for a full test conversion, plus what a trial run on 2026-10-26 showed. The full-corpus run and hardening is
phase 7 of the coding plan, so expect the checks below to find problems; section 6 lists the ones already found.

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

## 5. What the trial run on 2026-10-26 showed

Run against the 1,800 types installed on this machine:

| Measure | Result |
|---|---|
| Types generated | 1,800 of 1,800 (2,033 files including `__init__.py`) |
| Time | about 20 s |
| Types in reference cycles | 0 |
| Warnings | 165 |
| Modules that import | **1,789 of 1,800 (11 fail)** |
| Pyright strict | **6 errors** |

The 165 warnings, by kind:

| Count | Warning | Is it a problem? |
|---|---|---|
| about 106 | A .NET type with no Python equivalent was mapped to `Any` (for example `System.IComparable`, `System.IO.FileAttributes`) | Acceptable for now. The original type is kept in a `ClrType` marker. |
| 32 | Base type `System.Attribute` dropped (the C# attribute classes such as `DisplayTextAttribute`) | Acceptable: the attribute classes are generated as plain classes. Consider excluding attribute classes from the output. |
| 16 | A default value could not be written in Python, so the field is required (for example `System.RuntimeType`) | Review: these fields become required in Python. |
| 6 | A default collection holds complex items, an empty one was used instead | Review: the default differs from C#. |
| 4 | A generic type could not be instantiated to read its defaults (`PriorityQueue<T>`, `Quantity<T>`) | The fields are then required; acceptable but note it. |

Real bugs found by checks 3 and 4 (all in the generator, to be fixed in phase 7):

| Symptom | Cause | Types |
|---|---|---|
| `NameError: name 'Tree_1' is not defined` | A generic class uses its own name in `Field(default_factory=dict[str, Tree_1[T]])`, which runs while the class is still being defined | `Data_oM/Collections/Tree_1`, `DomainTree_1`, and `DeepLearning_oM/Models/Graph` through its import |
| `ValueError: 0 is not a valid DFMACategory` | The C# default is the enum value 0, but the enum has no member with that value, and the generated default `DFMACategory(0)` fails at import | 8 `dKoP_oM` types that use `DFMACategory` |
| Pyright: `list[str]` not assignable to `list[T]` | A default list of literals in a generic class | `Data_oM/Collections/VennDiagram_1` (2 errors) |
| Pyright: `list[float]` not assignable to `list[list[float]]` | A multi-dimensional array default written as a flat list | `Geometry_oM/TransformMatrix` and similar |

None of these indicate a problem with the C# source; each is a case the generator does not handle yet. After fixing the generator,
repeat sections 2 and 3 and expect the failure counts to fall to 0.

## 6. After a clean result

To land the output in the real package, run the same command with `--output src/bhom_schema` (the `_support` folder is already
there and is never touched). Review the resulting diff in git before committing: a first full conversion adds about 2,000 files.
