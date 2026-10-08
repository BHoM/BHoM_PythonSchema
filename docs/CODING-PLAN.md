# Coding plan: BHoM_PythonSchema converters

Status: **plan only, no code written yet.** Background and evidence are in
[CSharp-to-Python-Gotchas.md](CSharp-to-Python-Gotchas.md); gotcha numbers below refer to that document.

Revision 3: adds `ProjectIdentification` to the spike set, brings the CI work and the linked-PR Action into scope with the
existing GitHub App, uses the real `BHoM/dKoP_Toolkit` for the rehearsal (no scratch repository), and records the decisions
taken so far (section 9).

## Implementation status (phases 0 to 6 done, 7 and 8 not started)

Run `.ci/unit-tests/run-all.ps1`; it builds, generates, drafts, round-trips, runs NUnit (44 tests), pytest (73 tests) and Pyright.

Where the implementation differs from the plan above:

- **Golden files are reviewed generator snapshots**, not hand-written specifications. The behaviour of the spike types is pinned by the pytest suites
  (`test_fixtures`, `test_spike`); only small, stable real types (`ProjectIdentification`, `IdKoPObject`, `GradientCenteringOptions`) have committed golden files, so a change in the
  moving BHoM develop branch does not break the golden tests.
- **Pytest suites are separate sessions** (`test_py2cs`, `test_fixtures`, `test_spike`, `test_alignment`) because the fixture and spike packages share assembly folder names such as `BHoM`.
- **Imports:** a type outside any reference cycle is imported at the top of the module; only cyclic references use bottom-of-module imports plus `model_rebuild()`. The spike set has no cycle; the fixtures
  contain one on purpose.
- **Generated model files start with** `# pyright: reportUnknownVariableType=false, reportIncompatibleVariableOverride=false`: Pyright cannot infer `Field(default_factory=list)` with a
  `description`, and some C# classes redeclare a base property with another type.
- **Interface members** (names, types, descriptions) are kept in the `__bhom__` marker, because annotations on a plain base class would be collected by Pydantic as fields. Types they mention are generated too.
- **Required fields** (no default found because the C# type has no parameterless constructor) are drafted back as get-only properties plus a constructor.
- Same simple type names used by several types are written in full in the drafted C#, because an unqualified name can bind to a type in an enclosing namespace instead of the `using`.
- Drafts compile against `BHoM.dll` and `Quantities_oM.dll`; types the generator maps specially (for example `FragmentSet`) resolve from there.

## 1. End goal

1. **C# → Python converter** ready: reads the compiled BHoM oM assemblies and writes one Pydantic class per C# type.
2. **Python → C# converter** ready: reads the Python classes and drafts the aligned C# for the linked PR.
3. Both converters have their **entry points and core logic in `.ci/generation`**. They may reference C# logic from
   other repos (BHoM, BHoM_Engine, JSONSchema_Toolkit), but nothing of the business logic lives elsewhere.
4. **Tests** that verify the spike set (research doc section 11: ten slots, eleven types) plus the tests the workflow in
   the system-design diagram needs (section 6 below).
5. Generated `.py` files land in a **new Python project** in this repo (`bhom_schema`).
6. The repo's **template leftovers are removed**.
7. **CI is wired**: weekly schema generation, PR checks, and the automatic linked C# PR using the existing GitHub App.
8. Everything ends with a clean **build and full test run** (repo policy).

Out of scope: BHoM JSON (de)serialisation, and anything in `BHoM_JSONSchema` (the weekly JSON export stays untouched and
independent).

---

## 2. Target repository layout

```
BHoM_PythonSchema/
├─ .github/
│  ├─ ISSUE_TEMPLATE/ (kept, identical to the JSON repo's)
│  ├─ PULL_REQUEST_TEMPLATE.md (kept)
│  ├─ CODEOWNERS (new, copied from the JSON repo)
│  └─ workflows/
│     ├─ build.ps1 (copied from the JSON repo)
│     ├─ python-schema-generation.yml   weekly + manual: C# → Python, opens the schema-update PR
│     ├─ pr-checks.yml                  build, NUnit, pytest, Pyright on every PR
│     └─ linked-csharp-pr.yml           Python PR → draft C# PR(s), uses the GitHub App
├─ .ci/
│  ├─ generation/
│  │  ├─ PythonSchemaGeneration.sln
│  │  ├─ PythonSchemaGeneration/        C# console app, the C# → Python entry point
│  │  ├─ PythonSchemaGeneration.Core/   C# class library: all the real logic (testable)
│  │  └─ py2cs/                         Python package, the Python → C# converter (python -m py2cs)
│  │     ├─ reader / diff / locate / place / emitter / report / resolve
│  │     └─ pr.py                       GitHub client interface + PR raiser (real client and fake client)
│  └─ unit-tests/
│     ├─ csharp/
│     │  ├─ PythonSchemaGeneration.Tests/     NUnit tests
│     │  ├─ Fixtures.Alpha_oM/                small fake oM assembly used as test input
│     │  └─ Fixtures.Beta_oM/                 second fake assembly (same-named types, other repo URL, folder ≠ namespace)
│     ├─ python/                              pytest tests (converters, PR raiser, generated package)
│     ├─ golden/                              hand-written expected .py / .cs / report outputs
│     ├─ github-fixtures/                     recorded repository listings and API replies for offline tests
│     └─ run-all.ps1                          one script that runs every stage end to end
├─ src/
│  └─ bhom_schema/                    the new Python project (generated output lands here)
│     ├─ _support/                    small hand-written helpers (section 4.3)
│     └─ <Assembly>/<Namespace…>/<Type>.py   e.g. dKoP_oM/ProjectIdentification.py   (generated)
├─ pyproject.toml                     package metadata, pytest and pyright config, dev extras
├─ pyrightconfig.json                 strict type-checking rules shared by editor and CI
├─ Included-repositories.txt          copied from the JSON repo: repos to clone and build before generating
├─ dependencies.txt                   kept, trimmed to what the converter really references
├─ README.md                          rewritten
└─ CSharp-to-Python-Gotchas.md, CODING-PLAN.md
```

Folder names follow the `.ci/generation` spelling you gave (the JSON repo uses `.ci/Generation`; git is case-sensitive so
we stay consistent from the start).

### Template files to remove (phase 0)

Everything is a BHoM *toolkit* template and unrelated to this repo:
`SoftwareName_Adapter/`, `SoftwareName_Engine/`, `SoftwareName_oM/`, `SoftwareName_Toolkit.sln`,
`PowershellScript.ps1`, `RenameToolkitFiles.bat`. Rewrite `README.md`. Trim `dependencies.txt` (currently lists
`BHoM_Adapter`, which we don't use). Keep `LICENSE`, `.github/ISSUE_TEMPLATE`, `.github/PULL_REQUEST_TEMPLATE.md`.
Extend `.gitignore`: it currently has no entries for `bin/`, `obj/`, `__pycache__/`, `.venv/`, `.pytest_cache/`,
`.pyright/`, or generated test output, so these must be added before the first build.

---

## 3. How the pieces fit (data flow)

```
                                 BHoM assemblies (ProgramData\BHoM\Assemblies, or built in CI)
                                                │
                       PythonSchemaGeneration (C#, reflection)
                                                │
              ┌─────────────────────────────────┴───────────────────────────┐
     Type model (in memory)                                              report + type manifest
              │  (map types, order bases, add metadata + provenance)         (warnings, counts; test input)
              ▼
     src/bhom_schema/**/*.py  ──────────────►  Pydantic classes used by Python projects

 Python PR in this repo  (not from the weekly job)
              │
      py2cs diff     what changed between base and head (static read with ast)
              │
      py2cs resolve  repo(s) from each class's __bhom__["repo"]  (validated through the GitHub App)
              │
      py2cs locate   find the existing .cs file by searching the C# repo (never by namespace)
              │
      py2cs emit     new types → whole new files; modified types → suggested full-file replacement
              │
      py2cs pr       draft C# PR per repo, linked both ways
```

Both converters share one **language-neutral type manifest** (name, namespace, assembly, repo, kind, bases, generic
parameters, properties with C# type and metadata). C# → Python writes it next to the Python it generates; Python → C#
rebuilds it from Python. Structural tests compare two manifests, so each converter is testable without the other.

---

## 4. Design

### 4.1 C# → Python (`PythonSchemaGeneration.Core`)

| Stage | Responsibility | Notes |
|---|---|---|
| `AssemblyLoader` | Find and load `*oM.dll` from the BHoM folder, organisation-filtered | Same pattern as the existing generator; reports loaded and skipped assemblies (gotcha 13) |
| `TypeSelector` | Choose oM types: enums, `IObject` implementers, not static, oM namespace | Same rules as `Generate.GenerateAssembly`, so the two repos cover the same types |
| `TypeExtractor` | Reflection → type model (declared properties only, ordered bases, generic info, metadata) | Classifies interface vs class by reflection, **never by name** (`IdKoPObject` has no `I`). Reads defaults by instantiating where a parameterless constructor exists (gotcha 3). Reduces and orders interface bases (gotcha 6) |
| `ProvenanceReader` | Reads `AssemblyDescription` for the repo, plus namespace and assembly | Normalises `https://github.com/BHoM/dKoP_Toolkit` → `BHoM/dKoP_Toolkit` (gotcha 12) |
| `TypeMapper` | C# type → Python type expression + required imports | One table (research doc, section 5). Unknowns become `Any` plus a warning (gotcha 11) |
| `NameSanitiser` | Python-safe names | ``Output`1`` → `Output_1`; enum `None` → `None_`; keyword/builtin shadow checks (gotchas 5, 7) |
| `PythonEmitter` | Type model → `.py` text | Deterministic: sorted members, LF line endings, fixed header, generated-file banner |
| `OutputWriter` | Paths, `__init__.py`, clean-up | Path layout from the same helper the JSON generator uses, so folders match the JSON repo. Only deletes folders it owns; never touches `_support/` |
| `Reporter` | Warnings list, counts, manifest file | Feeds tests and PR descriptions |

Entry point `PythonSchemaGeneration` (console): arguments for output folder, organisation list, optional type filter
(for tests and quick local runs), and a switch to write the manifest.

Shared C# logic is **referenced, not copied**: `BHoM_Engine` (`IsOmNamespace`, `IsOmAssembly`), `Reflection_Engine`
(`Subtypes`), `Quantities_oM` (quantity attributes) and `JsonSchema_Engine` (`RelativeSchemaId`, `IsInOrg`), with
`HintPath`s into `ProgramData\BHoM\Assemblies` like the existing projects. All of these go through one small internal
adapter file, so replacing a reference later is a one-file change.

### 4.2 Shape of the generated Python (per type)

- File per type: `bhom_schema/<Assembly>/<namespace path>/<Type>.py`, class names unchanged except where unavoidable
  (`Output_1`).
- Concrete classes: Pydantic models inheriting from the support base class and from their interfaces.
- Interfaces: plain `ABC` marker classes. Abstract classes: model + `ABC`.
- Enums: `Enum` subclasses; `None` member emitted as `None_` with the real name kept in the metadata.
- Fields: PascalCase exactly as in C#; required unless a default was found; `Field(default_factory=…)` for mutable
  defaults; typed `Annotated[...]` with `ClrType`, `Quantity`, `DisplayText` markers where applicable.
- Docstrings and `Field(description=…)` from `[Description]`.
- Class-level `__bhom__` marker: C# full name, namespace, assembly, **repo**, plus generic and obsolete info.
- Cross-module references: bottom-of-module import plus `model_rebuild()` (gotcha 9); `from __future__ import annotations`.
- Sets/dictionaries keyed or filled by BHoM objects fall back to lists (gotcha 11).

### 4.3 Hand-written support package `bhom_schema/_support/`

Small and stable, imported by every generated file: `SchemaModel` base class (shared `model_config`), the `ClrType`,
`Quantity` and `DisplayText` markers, a `Color` model, and a helper that calls `model_rebuild()` safely. Written by hand
and under test, never overwritten by the generator.

### 4.4 Python → C# (`.ci/generation/py2cs`)

| Stage | Responsibility |
|---|---|
| `reader` | Parse a `.py` file with `ast` (no import side effects, works per file) into the same type manifest |
| `diff` | Compare the manifest at the PR base and head: added, removed, modified types and members |
| `resolve` | `__bhom__["repo"]` → repository, validated against the GitHub API; falls back to scanning the repos in `Included-repositories.txt` for a folder named after the assembly; compares names case-insensitively |
| `locate` | Finds the existing `.cs` file inside a checked-out C# repo by searching for the declaration (`class/interface/enum/struct <Name>`), file name first. **Never derives the path from the namespace** (43% of files don't match, gotcha 14) |
| `place` | Chooses a path for a **new** type: folder of sibling types in the same namespace, else `Enums/` convention, else namespace folder, else assembly root; the choice is stated in the PR |
| `emitter` | New type → whole new file (BHoM copyright header, namespace, usings, `[Description]`, properties, enum members). Modified type → **suggested full-file replacement** that reuses the existing file's header, usings and comments where it can (the Action passes the existing file in) |
| `report` | Structured change report per type (added/removed/changed members) for the PR body |
| `pr` | Creates or updates the draft C# PR and the links back (section 8); real and fake GitHub clients |
| `__main__` | `python -m py2cs diff / resolve / locate / emit / pr` |

The reader does static parsing instead of importing so it can run on exactly the files a PR changed, on the base
revision without installing it, and without executing any code.

Decision recorded: for a modified C# type the converter produces a **suggested full-file replacement** (written over the
existing path, in a **draft** PR, so GitHub's diff shows precisely what changes) plus the change report. A human reviews and
merges; nothing is auto-merged.

### 4.5 Tooling and conventions

Python 3.12, Pydantic `>=2.13,<3`, pytest, Pyright pinned (strict) in CI with Pylance in the editor. C# targets net8.0 like
the current generator (net8 SDK and runtime are installed here). Tests use NUnit, as in the JSON repo. The BHoM copyright
header and the repo's comment style apply to C# files; comment length stays in line with existing files.

---

## 5. Phases

Sizes are relative: S = hours, M = a day or two, L = several days. Every phase ends with its own build and test run.

### Phase 0: Clean up and scaffold (S)

- Remove the template files listed in section 2; rewrite `README.md`; trim `dependencies.txt`; extend `.gitignore`;
  copy `Included-repositories.txt`, `CODEOWNERS`, `build.ps1`.
- Add `pyproject.toml`, `pyrightconfig.json`, empty `src/bhom_schema/` with `_support/`, and the folder skeleton.
- Create `PythonSchemaGeneration.sln` with the exe, core, test and fixture projects (empty but building), referencing the
  BHoM assemblies via `HintPath`.
- **Assembly preflight:** `run-all.ps1` first checks that every assembly the spike set needs is present in
  `ProgramData\BHoM\Assemblies` (`BHoM`, `Geometry_oM`, `Structure_oM`, `Graphics_oM`, `Acoustic_oM`, `Architecture_oM`,
  `Quantities_oM`, `dKoP_oM`, and the engine dlls the generator references). `dKoP_oM.dll` is already installed on this
  machine (built 2026-10-07), so nothing needs building now. The preflight **reports** what is missing and never builds a
  repo itself; **build a repo only when its dll is actually missing**. In CI the real-type tests for the spike set must
  **fail**, not skip, when an assembly is missing; locally they skip with a clear message.
- A first `run-all.ps1` that builds and runs the empty test projects, `pytest` and `pyright`.
- **Done when:** `dotnet build` of the solution succeeds; `pytest` and `pyright` run (zero tests, zero errors).

### Phase 1: Executable specification for the spike set (M)

Hand-write the expected Python for the spike set as **golden files**, plus the support package. This turns the design into
something Pyright and pytest can already check.

- `ProjectIdentification` (and its interface `IdKoPObject`), `Line` (+ `Point`), `ICurve` chain, `BHoMObject`, `Bar`,
  `GradientCenteringOptions`, ``BHoMGroup`1``, the two `Room`s, `Gradient`, `ComparisonConfig`.
- Tests: all golden files import; `model_rebuild()` succeeds; Pyright strict clean; behaviour tests per gotcha (MRO order,
  `None_` enum, bounded generic, interface acceptance and rejection, same-name classes importable together, mutable defaults
  not shared, `__bhom__` present).
- `ProjectIdentification`-specific: four string fields default to `""` (constructing with no arguments works); it is an
  instance of `IdKoPObject` and **not** of `BHoMObject`; an `IdKoPObject`-typed field accepts it and rejects an unrelated
  object; `__bhom__["repo"] == "BHoM/dKoP_Toolkit"`, assembly `dKoP_oM`, namespace `BH.oM.dKoP`; file lives at
  `dKoP_oM/ProjectIdentification.py` (not under `AdministrativeInformation/`).
- Add the hand-written cyclic fixture pair for the cycle pattern.
- **Done when:** the golden set passes pytest and Pyright. Design flaws found here are cheap to fix.

### Phase 2: Type model and extraction (M)

- Build `Fixtures.Alpha_oM` and `Fixtures.Beta_oM`: small fake oM assemblies that mimic every spike case (enum with `None`,
  generic with constraint, interface chain with two parents, defaulted base plus required subclass, same-named types in the
  two assemblies, a set and dictionary of objects, `DateTime`, `Color`, quantity and description attributes). Specific
  `ProjectIdentification` twins: an interface **without** an `I` prefix, a flat class of defaulted `string` properties
  implementing it, source files placed in a folder that deliberately differs from the namespace, and an assembly
  `Description` pointing at a different repo URL than the other fixture assembly.
- Implement `AssemblyLoader`, `TypeSelector`, `TypeExtractor`, `ProvenanceReader`, the manifest writer.
- NUnit tests: extraction result per fixture type equals an expected manifest; selection rules; base reduction and
  ordering; default discovery (string defaults); generic handling; interface detected without name heuristics; repo
  normalisation.
- Tier-2 tests (installed or CI-built BHoM assemblies): the real spike types extract with the expected bases, properties
  and defaults; for `ProjectIdentification`: four declared properties, defaults `""`, base chain `IdKoPObject → IObject`,
  repo `BHoM/dKoP_Toolkit`.
- **Done when:** manifests for fixtures and real spike types match expectations.

### Phase 3: Mapping, emission and writing (L)

- Implement `TypeMapper`, `NameSanitiser`, `PythonEmitter`, `OutputWriter`, `Reporter`.
- Golden-file tests: emitted text for each fixture type equals the committed expected output (and the phase 1 golden files
  for the real-type equivalents, including `ProjectIdentification`).
- Path test: `BH.oM.dKoP.ProjectIdentification` is written to `dKoP_oM/ProjectIdentification.py` using the same rule as the
  JSON repo (assembly folder, namespace minus its first segment).
- Determinism test: two runs are byte-identical. Clean-up test: a type removed from the input removes only its file and
  empty folders, never `_support/`. Warning test: unsupported types become `Any` with a warning.
- Run the generator over the real spike types into a scratch folder and push it through the phase 1 pytest and Pyright
  checks.
- **Done when:** generated output for fixtures and real spike types passes pytest and Pyright strict.

### Phase 4: Metadata and provenance (M)

- Descriptions, quantity markers, display text, dynamic-property marker, CLR type annotations, full `__bhom__` content.
- Tests: `__bhom__` complete for every generated class (CLR name, namespace, assembly, repo); quantity unit and category on
  the right properties (for example `Bar.OrientationAngle`); descriptions appear as docstrings and field descriptions; CLR
  types preserved (`long` stays recoverable); `ProjectIdentification` carries no description and that does not break
  emission (no empty docstring noise).
- **Done when:** the metadata assertions pass on fixtures and real types.

### Phase 5: Python → C# reader, diff, locate, place and emitter (L)

- Implement `py2cs` reader, `diff`, `resolve`, `locate`, `place`, `emitter`, `report`.
- Unit tests with before/after Python fixture pairs: new type, new/removed/changed property, renamed enum member, new
  interface, removed type, and a change to `ProjectIdentification` (add `ProjectNumber`). Expected diff, C# and report are
  committed golden files.
- `locate` tests on a recorded mini C# tree: `ProjectIdentification.cs` is found under `AdministrativeInformation/` although
  the namespace is `BH.oM.dKoP`; `Line.cs` is found under `Curve/`; a missing type gives a clear "not found, treat as new"
  result; two files with the same name resolve by declaration.
- `place` tests: sibling-folder rule, `Enums/` rule, namespace-folder rule, assembly-root fallback.
- `emitter` tests: whole-file output for new types; suggested replacement for a modified type keeps the existing header,
  usings and comments.
- `resolve` tests against recorded repo listings: `dKoP_oM → BHoM/dKoP_Toolkit`, `Geometry_oM → BHoM/BHoM`,
  `CodeCompliance_oM → BHoM/Test_Toolkit`, case differences (`dKop_Toolkit`), a missing `repo` (scan fallback), an unknown
  assembly (clear error, no guess).
- **Done when:** the golden diff, locate, place and emission tests pass and the CLI works end to end on fixtures.

### Phase 6: Alignment round trip (M)

For each spike type: generated Python → `py2cs` draft C# → compile with Roslyn inside an NUnit test → reflect → compare the
resulting manifest with the original (loose comparison per research doc section 8: names, namespaces, assemblies, bases,
interfaces, property names and types, enum members, carried attributes).
- `run-all.ps1` orchestrates: generate Python, run `py2cs`, then `dotnet test` with the draft folder passed in.
- `ProjectIdentification` round trip: the draft compiles, keeps `: IdKoPObject`, four `virtual string` properties with `= ""`
  defaults, namespace `BH.oM.dKoP`.
- **Done when:** all spike round trips compile and match within the agreed tolerance; differences are listed and
  intentional.

### Phase 7: Full-corpus run and hardening (M)

- Run the generator over every available oM assembly. Import every module, rebuild every model, Pyright strict over the whole
  package; record import time and Pyright time.
- Re-measure the cycle count from the DLLs (including abstract classes); decide on lazy loading if import time or memory is
  poor.
- Fix mapping gaps surfaced by the warnings list; confirm counts: manifest, files written and modules imported are equal.
- **Done when:** the whole corpus imports and type-checks, the warnings list is reviewed, timings are recorded.

### Phase 8: CI wiring (L)

Both parts are in scope.

- **8a `python-schema-generation.yml`** (the diagram's "Create/Update schema"): weekly and manual. Same recipe as the JSON
  repo's weekly job (clone the repos in `Included-repositories.txt`, build in dependency order with `build.ps1`, build and
  run the generator), then commit to a `schema-updates` branch and open or update the PR to `develop`.
- **8b `pr-checks.yml`:** on every PR run `dotnet build`, NUnit, pytest and Pyright.
- **8c `linked-csharp-pr.yml`:** the two linked PRs. Full design and wiring in section 8.
- **8d Rehearsal on the real `dKoP_Toolkit`** (no scratch repository needed). The test subject is a new property added to the
  Python version of `ProjectIdentification`, for example `ProjectNumber: str = ""`:
  1. **Local dry run.** Create a throwaway branch of this repo, add the property in
     `src/bhom_schema/dKoP_oM/ProjectIdentification.py`, then run `py2cs diff`, `resolve`, `locate`, `emit` and `pr --dry-run`
     against the existing clone `C:\Github\dKoP_Toolkit` (on `develop`, clean, level with `origin/develop` when checked).
     The dry run **never writes into that clone**: it works on a temporary copy or in memory and prints the proposed
     replacement of `dKoP_oM/AdministrativeInformation/ProjectIdentification.cs`, the diff against the current file, the branch
     name, the PR title and the PR body.
  2. **Workflow dry run.** Open the Python PR and run `linked-csharp-pr.yml` with `dry_run=true`: it mints the App token for
     `BHoM/dKoP_Toolkit` only (proving the installation and permissions work) and prints what it would do.
  3. **Live run (needs your explicit go-ahead at that moment).** Re-run with `dry_run=false`. It pushes branch
     `python-schema/pr-<N>` to `BHoM/dKoP_Toolkit` and opens a **draft** PR, so dKoP maintainers will see it. The PR body
     states that it is a rehearsal. Afterwards check the cross-links, then **close the C# PR and delete its branch, and close
     the Python PR without merging** (the property was never added in C#; merging it would make the next weekly generation
     revert it). Re-running confirms idempotence (same branch, same PR) and the close behaviour.
- **Done when:** the three workflows run green on a branch of this repo, the dry runs match the expected golden output, and the
  rehearsal produced a correctly linked draft PR in `BHoM/dKoP_Toolkit` that has then been cleaned up.

### Final step (every phase, and last): full build and test

`run-all.ps1` runs, in order: `dotnet build` of the solution (Release), `dotnet test`, generator over fixtures, `pytest`,
`pyright`, `py2cs` over fixtures, the round-trip tests and the PR-raiser dry run; then, where the BHoM assemblies are
installed, the real-type tests and the full-corpus run. A phase is only finished when this script passes.

---

## 6. Test matrix (mapped to the workflow in the diagram)

| Workflow step / requirement | Test | Layer |
|---|---|---|
| C# → Python produces valid Python | Every generated module imports, every model rebuilds, Pyright strict clean | pytest + Pyright |
| Output is stable, so scheduled runs create small diffs | Two runs byte-identical; output sorted; fixed header | NUnit |
| "Create/Update schema" PR contains only real changes | Remove or rename a fixture type: only its file changes or disappears; `_support/` untouched | NUnit |
| Same types as the JSON export | Selector gives the same type set as the JSON generator rules for the fixtures; folder paths use the same helper (`ProjectIdentification` → `dKoP_oM/ProjectIdentification.py`) | NUnit |
| Independent of the weekly JSON job | Generator has no read or write dependency on `BHoM_JSONSchema` (project and path guard test) | NUnit |
| Re-use of schema by Python projects | Public import paths match the layout; importing a type does not import unrelated assemblies | pytest |
| PR → Python → C# converter | Before/after fixture pairs give the exact expected diff, C# draft and report | pytest |
| Existing C# file found although folders ≠ namespaces | `locate` finds `ProjectIdentification.cs` in `AdministrativeInformation/` and `Line.cs` in `Curve/` | pytest |
| New C# file placed sensibly | `place` rules (siblings, `Enums/`, namespace, root) | pytest |
| Modified type → suggested full-file replacement | Replacement keeps existing header/usings/comments; PR is a draft; body carries the report | pytest |
| Alignment of Python and C# changes | Round trip of the spike set compiles and matches the original manifest | NUnit + pytest (orchestrated) |
| Locating the C# repository for the linked PR | `__bhom__["repo"]` used first; scan fallback; case-insensitive; unknown assembly gives a clear error | pytest |
| Class carries what the Action needs | `__bhom__` has CLR name, namespace, assembly and repo on every generated class | pytest |
| **Loop guard:** the weekly schema PR must not spawn C# PRs | Workflow condition and `py2cs pr` refuse when the head branch is `schema-updates` or the actor is the App | pytest (+ workflow dry run) |
| Idempotent re-run | Pushing again to the same Python PR updates the same C# branch and PR, no duplicates | pytest with fake GitHub client |
| Closing the Python PR | Closed unmerged → linked C# PRs closed with a comment; merged → comment only | pytest with fake GitHub client |
| App token is least-privilege | One token per target repository, minted for that repository only; token never printed | workflow review + dry run |
| Fork PRs | Workflow does not run with the App secrets on fork PRs | workflow condition check |
| The spike set | Phase 1 golden, phase 2 extraction, phase 3 emission, phase 4 metadata, phase 5 locate/diff, phase 6 round trips | all layers |
| Scale | Full-corpus import, rebuild, Pyright, timings, count equality | CI / local with BHoM installed |

Two input tiers keep tests reliable: **fixtures** (tiny fake assemblies built in the repo; need only `BHoM.dll`) run anywhere,
and **real-type tests** (the actual oM) run when the BHoM assemblies are installed or built in CI.

### Where `ProjectIdentification` is checked

| Phase | Check |
|---|---|
| 1 | Golden file, defaults, interface-only base, `__bhom__`, path |
| 2 | Fixture twin and real-type extraction (interface without `I`, defaults `""`, repo) |
| 3 | Emission golden and output path |
| 4 | Provenance (`repo`, assembly, namespace); no description handled cleanly |
| 5 | `locate` (folder ≠ namespace), `resolve` (toolkit repo), diff/emit for an added property |
| 6 | Round trip compiles and matches |
| 7 | Part of the full-corpus import and type-check (needs `dKoP_oM.dll`, already installed) |
| 8 | Subject of the rehearsal: a new `ProjectNumber` property in Python, dry-run against `C:\Github\dKoP_Toolkit`, then a live draft PR in `BHoM/dKoP_Toolkit` |

---

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Hidden dependencies on a locally installed BHoM make results differ on CI | Fixtures for logic tests; real-type tests fail in CI and skip locally with a message; CI builds the BHoM repos itself, as the JSON job does |
| A needed assembly is missing from `ProgramData\BHoM\Assemblies` (`dKoP_oM.dll` is present now) | Phase 0 preflight reports it; build that repo only if its dll is really missing; fixture twins cover the logic meanwhile |
| The live rehearsal leaves a stray PR or branch in `BHoM/dKoP_Toolkit`, or the test property gets merged | Draft PR clearly labelled as a rehearsal, explicit go-ahead before the live step, mandatory clean-up step, Python PR is closed unmerged |
| `IsInOrg` and other helpers come from JSONSchema_Toolkit, which must be built before our generator in CI | `JSONSchema_Toolkit` is already in `Included-repositories.txt`; one adapter file isolates the reference |
| Reflection can't see default values (gotcha 3) | Instantiate-and-read where possible; required otherwise; golden tests pin the behaviour |
| Cycle or import-time problems only appear on the full corpus | Phase 1 cycle fixture, phase 7 full-corpus gate, lazy loading as the fallback |
| Pyright strict is noisy on generated code | Emit typed default factories; agree a short, explicit list of rule exceptions in `pyrightconfig.json` |
| Round-trip comparison is too strict or too loose | Define the loose comparison once and keep it in one test helper; review differences in phase 6 |
| Suggested replacement files create noisy C# diffs | Reuse the existing header, usings and comments; always a draft PR; report in the PR body |
| New-file placement guesses wrong | State the rule used in the PR; reviewer moves the file |
| Weekly schema PR triggers C# PRs (feedback loop) | Branch and actor guard, tested (section 6) |
| App token over-privileged or leaked | One token per target repo, short-lived, `permissions` minimised, masked in logs, no fork access |
| Target repo not covered by the App installation | `resolve` checks reachability first and comments on the Python PR with the missing repo instead of failing silently |

---

## 8. Linked C# PR workflow and GitHub App wiring

You already have a GitHub App with the needed access, so no new credential type is required. This is how to connect it to
this repository.

### 8.1 One-time setup (done by someone with org owner/admin rights)

1. **Confirm the App's permissions** (App settings → *Permissions & events*): *Contents: read and write* (push a branch to a
   C# repo), *Pull requests: read and write* (open, update and close the C# PR and comment), *Metadata: read* (automatic).
   Nothing else is needed. Add *Workflows* only if a C# PR would ever change `.github/workflows` (it won't).
2. **Confirm the installation covers every target repo.** App settings → *Install App* → the organisation → *Repository access*.
   It must include `BHoM_PythonSchema` (so the workflow can use its secrets) and every repository that owns oM assemblies
   (the repos in `Included-repositories.txt`). A repo outside the installation cannot get a token.
3. **Store the credentials.** Note the App ID (or Client ID) and generate a private key (`.pem`). Add them where the workflow can
   read them: either an organisation secret/variable shared with `BHoM_PythonSchema`, or repository-level ones. Suggested
   names (reuse the names your other workflows already use if the secret exists):
   - variable `BHOM_APP_ID`
   - secret `BHOM_APP_PRIVATE_KEY` (the full PEM text including the BEGIN/END lines)
4. **Protect the secrets.** Optionally attach them to a GitHub **Environment** (for example `linked-csharp-pr`) so only the
   linked-PR job can read them, with a required reviewer if you want a human gate before anything is raised.
5. **No scratch repository is needed.** The rehearsal uses the real `BHoM/dKoP_Toolkit` (phase 8d), so that repo must be within
   the installation (step 2).

### 8.2 How the workflow uses it

`linked-csharp-pr.yml`:
- **Triggers:** `pull_request` (opened, synchronize, reopened, ready_for_review, closed) with a path filter on
  `src/bhom_schema/**`, plus `workflow_dispatch` with `pr_number` and `dry_run` inputs. `concurrency` is per PR number so a
  newer push cancels an older run.
- **Guards (job `if`):** head repository is this repo (not a fork, because forks never receive secrets); head branch is not
  `schema-updates`; actor is not the App's bot account.
- **Job `plan`:** check out with full history, set up Python, `pip install`, run `py2cs diff` between the PR base and head, and
  `py2cs resolve` to list the affected repositories. Exit cleanly if there are no changes. Output the repo list as a matrix.
- **Job `raise` (one matrix leg per affected repo):**
  1. mint a token scoped to just that repo:
     `actions/create-github-app-token` (pin a major version or commit SHA; check the current release when implementing) with
     `app-id`, `private-key`, `owner: BHoM` and `repositories: <that repo only>`; the token lasts about an hour and is revoked
     when the job ends;
  2. check out that C# repo's `develop` branch with the token;
  3. `py2cs locate` + `py2cs emit` write the new files and suggested replacements into the checkout;
  4. commit on branch `python-schema/pr-<N>` as the App's bot identity and push;
  5. `py2cs pr` creates or updates a **draft** PR to `develop` whose body follows the C# repo's PR template (with
     "Depends on BHoM/BHoM_PythonSchema#N"), embeds the change report, and states the file-placement choices;
  6. comment on the Python PR with the link (using the workflow's own `GITHUB_TOKEN`: `pull-requests: write`, `contents: read`).
- **On `closed`:** unmerged → close the linked C# PRs with a comment; merged → comment on them that the Python PR merged.
- **`dry_run`:** does everything except pushing and creating PRs, and prints what it would do; used for the rehearsal and for
  debugging. It still mints the real App token, so a dry run proves the installation and permissions. Run locally, the same
  mode takes `--repo-root <existing clone>` and works on a temporary copy, so a developer's clone is never modified.
- **Safety details:** the token is only passed to steps that need it, via environment variables, never echoed; the default
  `GITHUB_TOKEN` permissions are set to read-only at workflow level and raised per job.

### 8.3 In code

`py2cs.pr` talks to GitHub only through a small `GitHubClient` interface (get repo, list tree, create or update branch and
file, create or update PR, comment, close). The real client wraps the REST API directly (the `gh` CLI is not installed on
this machine, so local dry runs must not depend on it; GitHub-hosted runners have it, but we don't rely on it). Tests use a
fake client with recorded responses, so branch naming, idempotence, the loop guard and the close behaviour are unit-tested
without network access.

### 8.4 What I need from you before phase 8c

1. The App's name/slug and its **App ID or Client ID**, and the names of the secret and variable that already hold them (so
   the workflow reuses them rather than creating duplicates).
2. Confirmation that the installation covers `BHoM_PythonSchema` and **all repos in `Included-repositories.txt`**.
3. Your go-ahead, at the time, for the **live rehearsal** that opens a draft PR in `BHoM/dKoP_Toolkit` (the dry runs need no
   approval), and who in dKoP should be told in advance.
4. Whether the linked PR should run for every Python PR automatically (current plan) or only when a label such as
   `csharp-sync` is present, or after approval of an Environment.
5. Whether the weekly generation job should also use the App token to clone any private BHoM-organisation toolkits (public
   repos don't need it).

---

## 9. Decisions recorded

| Question | Decision |
|---|---|
| Modified C# types | **Suggested full-file replacement** for a human to merge (draft PR, existing header/usings kept, change report in the PR body); no automatic patching. |
| CI scope | **Both** the weekly generation / PR-check workflows **and** the linked-PR Action are in scope now. |
| Repository list, owners, workflow recipe | Start as **copies of the JSON repo's**. |
| Spike set | `Point` replaced by `ProjectIdentification` as the "simple flat class" slot; `Point` is still generated and checked as `Line`'s dependency. |
| Cross-repo credential | Existing **GitHub App**, one short-lived token per target repository. |
| `dKoP_oM.dll` | Already installed locally; preflight reports missing dlls and builds a repo only if its dll is missing. |
| Rehearsal target | The real **`BHoM/dKoP_Toolkit`** (local clone `C:\Github\dKoP_Toolkit` for dry runs) using a new property on the Python `ProjectIdentification`; no scratch repository. Live step needs explicit go-ahead and is cleaned up afterwards. |
| Repo discovery | `__bhom__["repo"]` from the assembly's `Description` first; folder scan only as fallback. |
| Existing C# file lookup | Search by declaration; never by namespace path. |
