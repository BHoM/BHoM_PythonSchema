# Generating the real `bhom_schema` package

[Converting-All-oM-Classes.md](Converting-All-oM-Classes.md) is a **trial run** into the git-ignored `_output` folder. This guide
is the **real run**: the generated classes land in `src/bhom_schema`, the package that Python projects install, and you commit
them. All commands are PowerShell, run one at a time from the repository root.

## 0. Current state: only the CSharpSchema_Test classes

For now `src/bhom_schema` holds only the classes of the [CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test) repository,
plus the five BHoM base classes they import (`BHoMObject`, `IBHoMObject`, `IObject`, `IFragment`, `IImmutable`). Nothing else from
BHoM/BHoM is converted yet. The `--repos` option does this: it converts the assemblies whose description points at the named
repositories, and their dependencies. A run with `--repos` only cleans up the assembly folders of those repositories, so the
rest of a dependency's folder (for example `BHoM/`) is never deleted.

Build CSharpSchema_Test (`dotnet build CSharpSchema_Test.sln -c Release -p:SkipAssemblyCopy=true`), copy its dlls with `BHoM.dll` and
`Quantities_oM.dll` into an empty folder, then:

```powershell
dotnet .ci/generation/PythonSchemaGeneration/bin/Release/net8.0/PythonSchemaGeneration.dll --output src/bhom_schema --assemblies <folder> --repos BHoM/CSharpSchema_Test
```

The rest of this guide describes the full run over every installed assembly.

## 1. Read this first: what a real run does

- It writes about 2,000 files into `src/bhom_schema` (one `.py` per C# type plus `__init__.py` files). The folder
  `src/bhom_schema/_support` and the file `src/bhom_schema/__init__.py` are hand-written and are never touched.
- On every run it **deletes** generated files of the assemblies it wrote that are no longer generated, so removing a C# type
  removes its Python file. Anything you hand-edit inside a generated folder is lost; never edit generated files.
- The input is whatever is compiled in `%ProgramData%\BHoM\Assemblies` on this machine. That folder holds every BHoM toolkit you
  have built, at whatever commit you built it, so a local run is only as current and as clean as your last builds.
- The generator needs no internet and does not read `BHoM_JSONSchema`.

### Known limits of the generated package

The trial run (see section 5 of the trial guide) found four generator bugs, now fixed; a full run imports all 1,800 modules, passes
Pyright strict and the structural comparison. What remains is deliberate and shows up as warnings:

| Limit | Effect |
|---|---|
| `Overview.DFMACategory` defaults to the undefined enum value 0 in C# | The field is required in Python, and so are the fields holding a `dKoP` `Overview` or `AdministrativeInformation` (for example `UpperFloor()` needs its `AdministrativeInformation`) |
| About 16 other defaults cannot be written (for example `System.RuntimeType`) | Those fields are required |
| About 104 .NET types have no Python equivalent | Mapped to `Any`, with the C# type kept in a `ClrType` marker |

## 2. Before you start

1. **Build the C# you want converted.** For the main repo, build `C:\Github\BHoM\BHoM.sln`; the post-build step copies the dlls to
   `%ProgramData%\BHoM\Assemblies`. For a toolkit (for example `C:\Github\dKoP_Toolkit`), build it too. A toolkit that is not built
   is not converted.
2. **Decide the scope.** There is no repo filter, so the run converts every installed assembly whose description points at
   `github.com/BHoM/` (about 70 assemblies on the trial machine). To use another organisation or a different assembly folder, use
   the options in section 3.
3. **Use a clean branch** off `develop`, so the result is one reviewable commit:

```powershell
git switch develop
```

```powershell
git switch -c schema-initial-generation
```

4. **Check the working tree is clean** (an untracked `docs` file is fine):

```powershell
git status --short
```

## 3. Run the conversion into `src`

Build the generator:

```powershell
dotnet build .ci/generation/PythonSchemaGeneration.sln -c Release
```

Generate straight into the package, with a manifest and report kept outside the repository's tracked files:

```powershell
New-Item -ItemType Directory -Force .ci/unit-tests/_output/real | Out-Null
```

```powershell
dotnet .ci/generation/PythonSchemaGeneration/bin/Release/net8.0/PythonSchemaGeneration.dll --output src/bhom_schema --manifest .ci/unit-tests/_output/real/manifest.json --report .ci/unit-tests/_output/real/report.txt
```

You should see a line like `Generated 1800 of 1800 types, wrote 2033 files, 165 warnings.` in about 20 seconds.

Options when the default is not what you want:

| Option | Meaning |
|---|---|
| `--assemblies <folder>` | Read dlls from another folder instead of `%ProgramData%\BHoM\Assemblies` |
| `--org BHoM,Other` | Organisations whose assemblies are included (matched against the repo URL in each assembly description) |
| `--types A,B` | Convert only these types (a partial run: **do not** use this for the real package, it deletes nothing but gives an incomplete result) |

Open `.ci/unit-tests/_output/real/report.txt` and read the `Loaded assembly` and `Skipped assembly` lines. If a toolkit you expect
is missing, it was not built or its description has no BHoM repo URL.

## 4. Check the result

All checks run against the real package. The first three are fast.

**Count.** `Types available` and `Types generated` in the report must be equal, and the number of files in `src/bhom_schema`
should be close to the number in the summary line:

```powershell
(Get-ChildItem src/bhom_schema -Recurse -Filter *.py).Count
```

**Import every module.** Save this script as `.ci/unit-tests/_output/real/import_all.py` (git-ignored), then run it:

```python
import importlib, pathlib, sys
root = pathlib.Path("src").resolve()
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

```powershell
.venv\Scripts\python .ci/unit-tests/_output/real/import_all.py
```

**Type-check.** The repository's `pyrightconfig.json` already includes `src` in strict mode:

```powershell
.venv\Scripts\python -m pyright
```

**Structural comparison** of the C# manifest with the Python read back from the files:

```python
import sys
from pathlib import Path
sys.path.insert(0, ".ci/generation")
from py2cs.compare import compare_manifests
from py2cs.model import load_manifest
from py2cs.reader import read_package
problems = compare_manifests(
    load_manifest(Path(".ci/unit-tests/_output/real/manifest.json")),
    read_package(Path("src/bhom_schema")),
    allow_extra=False,
)
print(len(problems), "problems")
print("\n".join(problems[:40]))
```

**The existing test suite**, which now also sees the real package:

```powershell
.ci\unit-tests\run-all.ps1
```

**Determinism.** Run the generator a second time (same command as above). Then:

```powershell
git status --short
```

Nothing may change between the two runs apart from what the first run already added. If files change, the output is not
deterministic and must not be committed.

**Try it as a user.** The package is installed in editable mode in the project `.venv`, so this works immediately:

```powershell
.venv\Scripts\python -c "from bhom_schema.dKoP_oM.ProjectIdentification import ProjectIdentification as P; print(P(ProjectName='Demo'))"
```

## 5. Success criteria for committing

1. `Types available` equals `Types generated` in the report.
2. Every module imports (0 failures).
3. Pyright strict reports 0 errors.
4. The structural comparison reports 0 problems.
5. `run-all.ps1` finishes green, including the build step.
6. A second run produces no further changes.
7. The warning list has been read (see the warning kinds in the trial guide) and no new kind appeared.

## 6. Commit

Review the size of the change before staging; a first run adds about 2,000 new files and no edits to hand-written ones:

```powershell
git status --short | Select-String -NotMatch "^\?\? src/bhom_schema/"
```

That should print nothing except unrelated files you expect (for example your docs). If it lists a modified file under
`src/bhom_schema/_support` or `src/bhom_schema/__init__.py`, stop: the generator must not change them.

```powershell
git add src/bhom_schema
```

```powershell
git commit -m "Generate bhom_schema from the BHoM oM"
```

A commit message hook or the repository's own conventions may require an issue reference; follow them. Push and open a pull
request only when you are ready for review, because the diff is too large to read in full: reviewers should rely on the report
and checks above plus a spot check of a few files (see check 7 in the trial guide).

## 7. Updating later

Rebuild the C# you changed, repeat section 3, then review `git diff`. The diff should contain only the types that changed in C#
(plus removals of types deleted in C#). A diff that touches many unrelated files means the installed dlls differ from the last
run, for example one toolkit built from a different branch; fix the inputs rather than committing the noise.

The weekly generation workflow (phase 8 of the plan) will do exactly this in a clean environment: clone the repositories in
`Included-repositories.txt`, build them, run this command and commit the result straight to `develop` (no pull request, since the
C# is the source of truth). Until that exists, the package is only as reproducible as the machine it was generated on, so note
the commits of the repositories you built in the pull request description.

## 8. If something goes wrong

| Symptom | Likely cause and fix |
|---|---|
| `Missing --output` | The option is `--output <folder>`, not a positional argument |
| `Generated 0 of 0 types` | `%ProgramData%\BHoM\Assemblies` is empty or the `--org` filter excludes everything; build BHoM and check `report.txt` |
| A toolkit's types are missing | The toolkit was not built, or its assembly description has no `github.com/<org>/<repo>` URL |
| Many unexpected files deleted in `git status` | The installed assemblies are a smaller set than when the package was last generated; restore with `git restore src/bhom_schema` and rebuild the missing toolkits |
| Different output on every run | Do not commit; run the determinism check and report which files differ |
| You ran with `--types` by mistake | `git restore src/bhom_schema` and `git clean -fd src/bhom_schema`, then run without `--types` |
