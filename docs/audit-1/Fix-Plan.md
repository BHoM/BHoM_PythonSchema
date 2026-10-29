# Audit 1: plan to fix the review findings

Date: 2026-10-26. Status: **Steps 1 to 3 done**; Step 4 written and tested, but not run on GitHub yet (see "What was done in Step 4"); Step 5 done (see "What was done in Step 5"); Step 6 done, but the release workflow has not run on GitHub yet (see "What was done in Step 6"); Steps 7 and 8 not started.

The solution was reviewed against the Option 2 system design: the C# oM is the "source of truth", meaning that when the
Python and the C# disagree, the C# wins. The review found eight issues (**Issue 1** to **Issue 8**). This plan fixes them in
eight **steps**. The steps are numbered in the order to do them, so just follow Step 1, Step 2, and so on.

Each step is written for someone new to Python. It says what is wrong in plain words, shows a small example, lists what we
will do, and says how we will know it works.

---

## Before you start: words used in this plan

| Word | Plain meaning |
|---|---|
| **oM** | The BHoM "object model": the C# classes that describe things like `Bar`, `Line` or `Room`. Data only, no logic. |
| **Generator** (C# → Python converter) | Our C# program in `.ci/generation/PythonSchemaGeneration`. It looks inside the compiled BHoM `.dll` files and writes one Python file per C# class. |
| **py2cs** (Python → C# converter) | Our Python program in `.ci/generation/py2cs`. It reads the Python files and drafts the matching C# code. |
| **Pydantic** | A popular Python library for data classes. A Pydantic class lists its fields with types, checks values when you create an object, and can turn an object into JSON and back. Our generated classes are Pydantic classes. |
| **Field** | One piece of data in a class, the Python version of a C# property. `ProjectName: str = ''` is a field named `ProjectName`, of type `str` (text), with default value `''` (empty text). |
| **Type annotation** | The `: str` part after a field name. It tells Python and Pydantic what kind of value the field holds. |
| **Default** | The value a field gets when you don't give one. A field with no default is **required**: you must give it when creating the object. |
| **`__bhom__` marker** | A small dictionary at the top of every generated class that remembers where it came from: the C# full name, assembly, namespace and GitHub repository. py2cs needs it to know which C# repository and file to change. |
| **Interface** | In C#, a contract such as `ICurve` that many classes fulfil (`Line`, `Arc`, `Polyline`...). In our Python it becomes an empty base class. |
| **AST** | "Abstract syntax tree". py2cs reads Python files as text and turns them into a tree of code pieces, without running them. That is safe, but it only understands the shapes of code it was taught. |
| **Roslyn** | Microsoft's C# compiler as a library. It can read a `.cs` file into a tree, change one piece, and write it back with everything else untouched. |
| **Manifest** | A JSON file listing every type with its fields, written by the generator. Used to compare the C# view and the Python view. |
| **PR** (pull request) | A proposed change on GitHub that people review before it is merged. |
| **Linked PRs** | The two PRs in the system design: one in this repository (Python), one in the C# repository (C#), raised together. |
| **CI** / **workflow** | Scripts GitHub runs for us automatically (on a schedule, or when a PR changes). They live in `.github/workflows/*.yml`. |
| **pytest** / **NUnit** | The test runners for Python and C#. |
| **Pyright** | A tool that reads Python code and reports type mistakes, like the C# compiler would. |
| **JSON** | The text format used to save objects to files or send them over the web, for example `{"Name": "Bar 1", "Length": 3.2}`. |
| **Wheel** | The file you install a Python package from (`pip install ...`). |
| **Build and test gate** | `dotnet build .ci/generation/PythonSchemaGeneration.sln -c Release` with no errors, then `.ci/unit-tests/run-all.ps1` fully green. **Every step ends with this gate**; a step is only done when it passes. |

---

## Decisions taken (2026-10-26)

| Topic | Decision |
|---|---|
| How py2cs changes an existing C# file (Step 2) | **Patch member by member.** This reverses the old "suggested full-file replacement" decision in CODING-PLAN section 9. Whole files are written only for brand-new types. |
| Where the input assemblies come from (Step 4) | **Our own build, on GitHub** (revised 2026-10-29; was: share the BHoM_JSONSchema weekly build). Our workflows clone BHoM, BHoM_Engine, JSONSchema_Toolkit and CSharpSchema_Test from GitHub and build them. BHoM_JSONSchema is not changed until our system is proven, and with far fewer projects converted to Python than to JSON, the two DLL sets may stay separate for good. |
| Which assemblies go into the package (Step 6) | **For now, only `BHoM/CSharpSchema_Test`; BHoM/BHoM later** (by adding it to `Converted-repositories.txt` and `Included-repositories.txt`). Toolkits such as `dKoP_Toolkit` stay out. |
| BHoM JSON compatibility (Step 5) | **Approved** (2026-10-29) and done: follow the rules of BHoM_JSONSchema (`_t`, interface implementers as the allowed `_t` values, enums as names). The old 5A/5B split is dropped. Reasons are in Step 5. |

What the scope decision changes in the other steps:
- Step 1: a brand-new Python class must go into an existing assembly of BHoM/BHoM; there is no `Python_Toolkit` fallback for now.
- Step 4: the generator only reads assemblies whose repository is `BHoM/BHoM`, even though the shared build contains more.
- Step 4: the rehearsal can no longer use `dKoP_Toolkit`, because dKoP is outside the package. A new target must be chosen.

---

## The order at a glance

| Step | Fixes | In one sentence | Why at this point |
|---|---|---|---|
| 1 (done) | Issue 2 | Make py2cs understand Python written by people, not only by the generator | Everything py2cs drafts depends on reading the Python correctly |
| 2 (done) | Issue 1 | Change only the lines that need changing in an existing C# file | So the drafted C# is something BHoM reviewers will accept |
| 3 (done) | Issue 4 | Agree how the Python PR and the C# PR stay in step, and warn about breaking changes | The rules must exist before they are automated |
| 4 (code done) | Issue 5 | Automate everything on GitHub, using the JSON repository's build | Once the loop is safe, make it run by itself |
| 5 (done) | Issue 3 | Let objects with interface-typed fields be saved to JSON and loaded back | Makes the package useful to other Python projects (decision needed) |
| 6 (code done) | Issue 6 | The scope (test repository for now), a version number from BHoM, release notes, publishing | Needed before anyone installs it |
| 7 | Issue 7 | Five small generator fixes | Low risk; can be picked up at any time |
| 8 | Issue 8 | Tidy the documentation | Last, so the docs describe the finished state |

---

## Step 1 (Issue 2): make py2cs understand Python written by people

### What's wrong, in plain words

In the system design, a developer edits the Python classes in a PR, and py2cs turns that edit into a C# PR. But py2cs was
only taught to read the exact style the generator writes. Normal Python written by a person confuses it, and some of the
failures are silent.

We reproduced four problems:

1. **A new class without the `__bhom__` marker is ignored without any message.** No C# PR would be raised, and nobody would know why.

   ```python
   class ProjectStage(SchemaModel, IdKoPObject):   # no __bhom__ dictionary
       Stage: int = 0                              # py2cs: "0 changes"
   ```

2. **A very common way of writing a default is misread.** In Pydantic, `Field(0, description="...")` means "default 0, with
   a description". py2cs only understands `Field(default=0, ...)`, so it thinks the field has *no* default. Its C# draft
   then made the whole class read-only, with a new constructor, which would break every existing `new ProjectIdentification()`
   in BHoM code.

3. **Other common type styles crash it.** `Optional[int]` ("an int or nothing") stops the whole run with a Python error
   message (a "traceback") instead of a clear explanation.

4. **Only the first class in a file is read.** A second class in the same file is ignored without a message.

### What we will do

1.1 **Write down the rules for editing the Python** in the README, with a template file to copy. For example: one class per
file; the file goes in `src/bhom_schema/<Assembly>/<namespace folders>/<ClassName>.py`; how to write a default and a
description; how to say "this is a C# `long`, not an `int`".

1.2 **Teach py2cs the common styles** so these all work:

```python
Stage: Optional[int] = None                        # same as  int | None = None
Names: List[str] = Field(default_factory=list)     # same as  list[str]
Stage: int = Field(0, description="RIBA stage")    # positional default
Stage: int = pydantic.Field(default=0)             # Field called through the module name
```

1.3 **Fill in `__bhom__` automatically when it is missing**, instead of skipping the class. py2cs can work it out from where
the file is: the folder gives the assembly, and the other classes in the same folder give the namespace and repository.
The PR report says these values were worked out, so a reviewer can check them. A class placed in a folder that is not an
existing BHoM/BHoM assembly gets a clear error (see "Decisions taken").

1.4 **Collect problems instead of crashing.** py2cs reads every file, gathers all the problems (file, line, message), prints
them together and then stops. For example:

```
src/bhom_schema/Structure_oM/Elements/Bar.py:42: unsupported type 'Sequence[int]'; use list[int]
src/bhom_schema/Geometry_oM/Line.py: two classes in one file; move 'LineHelper' to its own file
```

1.5 **Never turn a missing default into a read-only C# class.** A new field without a default becomes a normal C# property
(`{ get; set; }`) and the report notes it. Read-only properties and a constructor are only drafted when the C# class is
already built that way.

1.6 **Add a checking command**, `python -m py2cs check --root src/bhom_schema`, that runs all of the above without drafting
anything. It also warns when a new class or field has no description, because BHoM requires a `[Description]` on every oM
class and property. Step 4 runs it on every PR.

### How we'll know it works

- New tests in `.ci/unit-tests/python/test_py2cs`, one "before and after" pair of Python files for each style in 1.2, each
  with the expected C#.
- The four reproduced problems now give correct C# or a clear message.
- The build and test gate passes.

---

## Step 2 (Issue 1): change only the lines that need changing in an existing C# file

### What's wrong, in plain words

When a Python class changes, py2cs currently rewrites the **whole** C# file from what it knows. But the Python doesn't know
everything that is in the C# file, so the rewrite loses things and reformats others.

We tested this by adding one field (`Mark`) to the Python `Bar`. The proposed `Bar.cs`:
- lost both `[DocumentationURL(...)]` attributes (links to the documentation);
- lost the interface `IElement1D` from the class line and reordered the others;
- joined long descriptions that were split over several lines into one long line;
- changed `= null` to nothing and `= 0` to `= 0.0`.

One new line of Python became about 40 changed lines of C#. A BHoM reviewer would rightly reject that.

### What we will do

2.1 **Record the decision** (already taken): existing C# files are patched member by member. Update CODING-PLAN section 9.

2.2 **Add a small C# tool**, `PythonSchemaGeneration.Patcher`, to the generation solution. It uses Roslyn (already used in our
tests) to open a `.cs` file, change only the listed members, and save it. Everything else, including comments, blank lines
and attributes it doesn't know about, stays exactly as it was.

2.3 **Give the tool a precise list of changes** instead of a new file. py2cs already works out what changed (the "diff"); it
will save it as a list like this:

```json
[
  { "change": "property added", "name": "Mark", "type": "string", "default": "\"\"", "after": "SectionProperty" },
  { "change": "description changed", "name": "OrientationAngle", "description": "..." }
]
```

For the `Bar` example, the result must contain **only** the new `Mark` property and its attributes.

2.4 **Treat equal things as equal**, so nothing is changed for no reason: `= null` and no value on a class-typed property are
the same; `0` and `0.0` are the same; an interface already implied by another one doesn't need to be added.

2.5 **Wire it in**: `py2cs plan` builds the change list and calls the tool for existing files; brand-new types still get a
whole new file. Anything the tool could not translate is listed in the PR description, not left as a comment in the code.

### How we'll know it works

- NUnit tests on copies of real files (`Bar.cs`, `ProjectIdentification.cs`, a file with several classes, a file with
  `#region` blocks). Adding one property changes only the added lines.
- An empty change list gives back the file exactly as it was, byte for byte.
- The `Bar` test above gives a small, clean diff.
- The build and test gate passes.

---

## What was done in Steps 1 and 2

- **Step 1:** `py2cs/reader.py` accepts the common styles (1.2), works out a missing `__bhom__` marker (1.3) and collects problems
  per file (1.4). New fields without a default become settable properties (1.5). `python -m py2cs check` is in `py2cs/check.py` (1.6).
  The rules are in the README, with a class to copy in `docs/templates/NewClass.py` (1.1). Tests: `test_py2cs/test_authoring.py`.
- **Step 2:** the Roslyn patcher is `.ci/generation/PythonSchemaGeneration.Patcher`, and py2cs builds its change list in
  `py2cs/patch.py`. `py2cs plan` patches existing files and writes whole files only for new types. CODING-PLAN section 9 records
  the new decision. Tests: `PatcherTests.cs` (NUnit, on copies of the real `Bar.cs` and `ProjectIdentification.cs` in
  `golden/patcher`) and `test_py2cs/test_patch_changes.py`.
- **Differences from the plan:**
  - The round-trip drafts (`py2cs drafts`) still turn fields without a default into get-only properties set by a constructor,
    because those come from immutable C# types.
  - A type that is new in Python but already declared in C# is reported as a problem instead of being patched.
  - In an enum whose members have no explicit values, new members always go at the end, so the other members keep their numbers.
- **Result:** the `Bar` example from the review is now a 3-line C# diff. `run-all.ps1` passes: 65 NUnit tests, 88 pytest tests,
  Pyright 0 errors.

---

## What was done in Step 3

- **3.1 rules:** README section "Life of a Python change", and a checklist for Python schema changes in
  `.github/PULL_REQUEST_TEMPLATE.md`.
- **3.2 alignment check:** `python -m py2cs align` (`py2cs/align.py`). It diffs base against head, runs the generator for the
  changed classes over a folder of built oM dlls (`--assemblies`), reads the result back and compares it with the PR using
  `compare.py`. Exit code 0 when they match, 1 with the differences listed (first value from the C#, second from the PR), 2 when
  it could not run. `--generated-root` takes a package that was already generated. Building the merged C# is left to the caller:
  the Step 4 workflow does it.
- **3.3 breaking changes:** `diff.py` lists them per type (`breaking_changes`, plus a rename guess when exactly one removed and
  one added property share a type). `py2cs plan` puts them in a "Breaking changes" section of the report and writes the
  `breaking-change` label to `plan.json` (`labels`). Kind changes are also treated as breaking. Putting the label on the C# PR is
  part of `pr.py` in Step 4.
- **3.4 loop guard:** first built (`py2cs/guard.py`), then removed on 2026-10-28 because it guarded against a pull request that
  does not exist: the weekly generation commits directly. Nothing in the code opens a weekly generation PR.
- **Tests:** `test_py2cs/test_lifecycle.py`, and `test_alignment/test_align_with_generator.py`, which runs the real generator over
  the fixture assemblies.

---

## Step 3 (Issue 4): keep the Python PR and the C# PR in step, and warn about breaking changes

### What's wrong, in plain words

The system design raises two linked PRs: one for the Python, one for the C#. But nothing says what happens next. Some
situations that can go wrong today:

- The Python PR is merged first, then the C# reviewers rename the property. Next week the generator rebuilds the Python from
  the C#, so the Python silently changes again, and any Python code using the first name breaks.
- The C# PR is rejected. Next week the generator silently removes the property from the Python again.
- Someone renames or deletes a C# property. BHoM needs a "versioning" entry (in Versioning_Toolkit) for that, so old saved
  files can still be opened. Nothing warns about it.

### What we will do

3.1 **Write down the rules** in the README and in this repository's PR template:
1. A Python PR is a **proposal**. It is never merged before its C# PR.
2. The C# PR is reviewed and merged in its own repository, as usual.
3. Before the Python PR can be merged, an automatic **alignment check** (3.2) must pass. Or simply close the Python PR and
   let the next weekly generation bring in the same change; both give the same files.
4. If the C# PR is closed without merging, the Python PR is closed too, with a comment explaining why.

3.2 **Add the alignment check**, `python -m py2cs align`. It asks: "if we generate the Python from the C# that was actually
merged, do we get the same Python as in this PR?" It builds the affected C# assembly, runs the generator for just the
changed classes, and compares the result with the PR using the comparison code we already have
(`py2cs/compare.py`). It passes only when they match, and otherwise lists the differences.

3.3 **Spot breaking changes** and list them in a "Breaking changes" section of the C# PR description, with a
`breaking-change` label and a reminder to add a versioning entry. Breaking changes are: a property removed or renamed (seen
as one removed and one added with the same type), a property's type changed, an enum value removed or renumbered, a class
removed, or a base class or interface removed. Nothing is blocked automatically; the reviewer decides.

3.4 ~~**Stop the loop going round forever.**~~ **Not needed (decided 2026-10-28).** The weekly generation writes the Python
straight from the C# and commits it to `develop`. It is not a pull request, so it can never raise a C# PR, and there is no loop
to stop. The only rule left is that `linked-csharp-pr.yml` triggers on `pull_request` and never on `push` (Step 4).

### How we'll know it works

- Tests for `align`: same Python (pass), a different default (fail), a missing property (fail).
- Tests that each kind of breaking change is spotted, including a rename.
- The build and test gate passes.

---

## What was done in Step 4

Everything is written and tested here. It has **not been run on GitHub yet**: that needs the GitHub App and two settings (see
[Workflows.md](../Workflows.md)), and the first runs are yours to start.

- **4.1 generator:** `--baseline-warnings <file>` and `--write-baseline <file>`, a committed `.ci/generation/warnings-baseline.txt`
  (two known kinds), exit code 1 when a type could not be converted or a warning kind is new, exit code 2 for a misspelt option
  (`CommandLine.cs`, `WarningBaseline.cs`).
- **4.2 repository filter:** `--repos`, done earlier.
- **4.3 build:** `Included-repositories.txt` now lists BHoM, BHoM_Engine, JSONSchema_Toolkit and CSharpSchema_Test.
  `.github/scripts/Clone-Repositories.ps1` clones them from GitHub (read only) and records each commit;
  `Build-Repositories.ps1` builds them in dependency order with the JSON repo's `build.ps1`. Nothing comes from a laptop.
- **4.4 weekly generation:** `python-schema-generation.yml`. It generates only what `Converted-repositories.txt` lists
  (CSharpSchema_Test), checks it (`py2cs verify`: every module imports and reads back as the C# manifest says; Pyright), and commits
  straight to `develop` with the commit of every built repository in the message.
- **4.5 PR checks:** `pr-checks.yml` runs `run-all.ps1`, and `py2cs check` and `py2cs align` for a PR that changes `src/bhom_schema`.
  The test project finds the CSharpSchema_Test clone through the `CSharpSchemaTestRoot` environment variable.
- **4.6 linked C# PR:** `linked-csharp-pr.yml`, `py2cs/pr.py` (raise, update, close), `py2cs/github.py` (a REST client and an
  in-memory mock) and the commands `repos`, `plan --only-repo --allowed-repos`, `pr` and `close`. C# pull requests can only be raised in
  the repositories of `Converted-repositories.txt`.
- **4.7 first generation:** `src/bhom_schema` holds the 27 CSharpSchema_Test classes and 5 BHoM base classes, generated on a laptop
  last week. The first weekly run on GitHub should change nothing; if it does, it commits the difference.
- **4.8 rehearsal:** the local dry run is done (a new property on `Beam` becomes 3 lines in `Objects.cs`, and a new `Panel.cs`, with
  the clone untouched). The workflow dry run and the live run are for you to start, in the order in [Workflows.md](../Workflows.md).
- **Tests:** `test_linked_pr.py` (branch names, a second run changing nothing, a changed PR updating the same PR, closing, dry runs,
  the REST calls and that the token never appears), `test_workflows.py` (no `push` trigger, read-only permissions, one-repository
  tokens, base-branch tooling, BHoM never written to), `test_verify.py` and `CommandLineAndBaselineTests.cs`.
- **Differences from the plan:** the linked-PR comment on the Python PR is updated in place instead of repeated; `align` is part of the
  PR checks job, so that job stays red until the linked C# PR is merged.
- **Changes after review (2026-10-29):**
  - The dKoP tests were dropped, so the PR checks build only `Included-repositories.txt` and no extra repositories are declared anywhere.
  - `CommandLine.cs` moved from the Core library into the `PythonSchemaGeneration` console project; the tests reference that project.
  - The linked-PR workflow sets a commit status on the Python PR (`status.py`, `py2cs status`): pending, success or failure from the
    state of the linked C# PR. An hourly run refreshes it, because nothing tells this repository when a C# PR is merged.

---

## Step 4 (Issue 5): automate everything on GitHub, using the JSON repository's build

### What's wrong, in plain words

Today everything runs by hand on one machine:
- There are no GitHub workflows yet, and no code to open PRs (`pr.py` doesn't exist).
- The real generated package has never been committed: `src/bhom_schema` only has the hand-written helper folder.
- The generator always reports success (exit code 0), even when a class failed to convert, so automation couldn't notice a problem.
- The generator reads whatever `.dll` files happen to be installed in `%ProgramData%\BHoM\Assemblies` on that machine, so two
  people can get different results.

### What we will do

4.1 **Make the generator report failure properly**:
- Exit code 1 when any class could not be converted.
- A committed list of known warning kinds (`--baseline-warnings <file>`). A new kind of warning fails the run, so a BHoM
  change that needs a generator update is noticed.
- Complain about misspelt command-line options instead of ignoring them.

4.2 **Add a repository filter** to the generator, `--repos BHoM/BHoM` (**done 2026-10-28**: implemented as `--repos`, first used with `BHoM/CSharpSchema_Test`; a repo run only cleans its own assembly folders), which keeps only assemblies whose description points at
that repository. This applies the scope decision while still reading the shared build (see Step 6).

4.3 **Build the C# repositories ourselves** (revised 2026-10-29; the text below is the original idea, kept for later):
- The JSON repository's weekly job already downloads and builds the BHoM repositories. We add one step to it that uploads the
  built `.dll` files as a workflow "artifact" (a file GitHub keeps for a few days).
- When their job finishes, our workflow starts, downloads that artifact and runs our generator on it. Their logic and ours
  stay separate; only the build is shared.
- This needs a small change in the BHoM_JSONSchema repository, so its maintainers must agree. Until then, a stop-gap is to
  build `BHoM`, `BHoM_Engine` and `JSONSchema_Toolkit` ourselves, which is small now that only BHoM/BHoM is in scope.
- The generation commit message lists the commit of every repository that was built, so anyone can reproduce it.

4.4 **Weekly generation workflow** (`python-schema-generation.yml`): get the `.dll` files (4.3), run the generator into
`src/bhom_schema`, run the checks (every module imports, Pyright, the C# vs Python comparison), then commit the result straight
to `develop`. It is not a pull request: the C# is the source of truth, so the weekly run just rewrites the Python. If a check
fails, nothing is committed. If `develop` is protected, the GitHub App must be allowed to bypass the pull request rule.

4.5 **PR checks workflow** (`pr-checks.yml`), on every PR: build, NUnit, pytest, Pyright, `py2cs check` (Step 1), and
`py2cs align` (Step 3) for PRs that change the Python classes.

4.6 **Linked C# PR workflow** (`linked-csharp-pr.yml`) and `py2cs/pr.py`, as designed in CODING-PLAN section 8. In short: when
a Python PR changes, work out which C# repository owns each changed class, get a short-lived access token for that
repository only (from the existing GitHub App), push a branch `python-schema/pr-<N>`, open a **draft** C# PR, and add links
both ways. Running it again updates the same PR rather than opening a new one. `pr.py` talks to GitHub through a small
interface, so tests can use a mock GitHub that never touches the network.

4.7 **First real generation**: run the weekly workflow once and commit its result to `src/bhom_schema`, rather than generating
on a laptop.

4.8 **Rehearsal**: a dry run first (prints what it would do, changes nothing), then one live draft PR, only with your explicit
go-ahead, cleaned up afterwards. **The target needs choosing again**: the old plan used `dKoP_Toolkit`, which is now out of
scope. **Decided: `BHoM/CSharpSchema_Test`**, a repository made for this. No BHoM repository is written to.

### How we'll know it works

- Tests: exit codes; a new warning kind fails; the repository filter keeps only BHoM/BHoM.
- Tests with the mock GitHub: branch names, re-running updates the same PR, closing behaviour.
- The three workflows run green on a test branch of this repository.
- The build and test gate passes.

---

## What was done in Step 5

- **5.2 `_t` and `_bhomVersion`:** `SchemaModel` (hand-written, in `_support`) writes `_t` first on every object, reads it (optional, and refused when it names
  another class), carries `_bhomVersion` (left out when empty), adds `_t` to the JSON Schema, and reads a FragmentSet written as `{"_t": "BH.oM.Base.FragmentSet",
  "_v": [...]}` as a list. No generated field is added, so py2cs and the C# manifest are not affected.
- **5.3 implementers:** the generator writes `implementers` into the marker of every non-generic interface and abstract class: the generated, concrete, non-generic
  classes that implement it, as C# name to module path. A run for some repositories lists only what it generates (`--repos`).
- **5.4 `Polymorphic[X]`** (`_support/polymorphic.py`): for fields typed with an interface or abstract class (also inside lists and optionals, and as a generic
  bound). An object of the interface is accepted; JSON needs `_t`, which must be an implementer, and the class is imported only then and validates alone, so the
  error names the real problem. Base classes are never wrapped.
- **5.5 JSON Schema:** the same shape as BHoM_JSONSchema (`_t` required, the implementers as its allowed values, an if/then rule per class). Descriptions are nested one
  level only, because an implementer can hold the interface again; an interface met inside lists the allowed `_t` values. Delegate fields are left out of the schema.
  `model_json_schema()` works for every generated class, including every BHoMObject.
- **5.6 enums:** `BHoMEnum` and `BHoMFlags` (`_support/enums.py`) are written by name (`None_` as `"None"`; flags as one name or the set flags joined by ", ") and
  read from a name, a number, or BHoM's `System.Enum` object form. No [Flags] enum exists in BHoM/BHoM, so the flags form is only tested on the fixtures.
- **5.7 py2cs:** reads `Polymorphic[...]` and `SkipJsonSchema[...]` as the plain type, and the two new enum bases as enums.
- **Tests:** `test_support/test_json.py` (the support package alone), `test_fixtures` (JSON round trips on generated classes, a JSON Schema for every class),
  `test_spike/test_json.py` (round trip of a real Bar, and the conformance tests), NUnit tests for the generator output.
- **Conformance** with the published schemas (read-only clone of BHoM_JSONSchema, only as the test oracle; skipped when it is not there, cloned by the PR checks
  workflow): Point, Line, Line as an ICurve, a whole Bar, and an enum in both forms validate.
- **Still open:** `BHoM_Guid`, `Tags` and `CustomData` pass the Bar test; the special float values (`NaN`, infinity), `System.Type`, `Color` and a generic class's `_t`
  (written without its type arguments) are not checked against C# output yet. Loading real JSON written by BHoM in C# is only covered through the published schemas, no
  recorded C# sample is in the repository.

---

## Step 5 (Issue 3): let objects with interface-typed fields be saved to JSON and loaded back

> **Revised 2026-10-29** after reading the documentation of BHoM_JSONSchema. The first version of this step invented its own way of
> handling interfaces. BHoM already has a written, published way, so this step now follows it. **Approved 2026-10-29** (BHoM JSON is back in
> scope) and done: see "What was done in Step 5" above.

### What's wrong, in plain words

The point of the package (the "Re-use schema" arrow in the system design) is that other Python projects use these classes.
In practice, a Python project almost always needs to **save** objects and **load** them again: to a file, through a web API,
or to and from C# through Python_Toolkit. That is done with JSON.

Today that works for simple classes, but not for most of BHoM, because BHoM uses interfaces everywhere. For example, the
structural `Edge` class has a field `Curve: ICurve`, which can hold a `Line`, an `Arc`, a `Polyline` and so on. We tested it:

```python
edge = Edge(Curve=Line(Start=Point(X=1), End=Point(X=2)))   # creating it works
text = edge.model_dump_json()                               # saving to JSON works...
Edge.model_validate_json(text)                              # ...but loading it back FAILS
Edge.model_json_schema()                                    # describing it as JSON Schema FAILS
```

Why:
- The saved JSON doesn't say *which kind* of curve it was. It only contains `{"Start": ..., "End": ...}`. When loading,
  Pydantic sees "an `ICurve`" and can't know whether to build a `Line` or an `Arc`, so it gives up.
- Every `BHoMObject` has a `Fragments` field typed with the interface `IFragment`, so describing the class as a JSON Schema
  fails for **every** BHoM object.
- BHoM's C# JSON adds a `"_t"` entry to every object, holding the full C# class name (for example
  `"_t": "BH.oM.Geometry.Line"`). Our Python doesn't write or read `_t`, so JSON can't pass between Python and C#.

So without this step, people can create BHoM objects in Python, but can't reliably save them, load them, or exchange them with
C#. That is most of what "reusing the schema" means.

### What BHoM_JSONSchema already does (and so what this step copies)

BHoM_JSONSchema is generated from the same C# classes, and its documentation describes how it handles interfaces. Its rules:

| BHoM_JSONSchema rule | Meaning |
|---|---|
| Every class has an optional `_t` that must equal the C# class name | A plain `Line` can be written without `_t`, but when it is written it must be right |
| An interface schema lists **every class that implements it**, as the allowed values of `_t` (for example `IPolyline`: `Polyline` or `Polygon`; `IFragment` lists about 130 classes from some 40 repositories) | The set of allowed classes is fixed when the schemas are generated |
| A value validated as an interface **must** carry `_t` | `_t` is how the right class is picked |
| After `_t` picks the class, the value is validated against that class only (an "if `_t` is X then X's schema" rule) | An error names the real problem (for example "Z is missing"), not a failure for every possible class |
| Enums are written as their names: `"Centre"`. Top-level enums, and enums held in an `object` property, are written as an object `{"_t": "System.Enum", "TypeName": {...}, "Value": "Centre"}`. The schema accepts both | |
| Every class also has an optional `_bhomVersion` text (for upgrades between BHoM versions) | |
| The schemas must always be generated as one full package, because an interface has to know all of its implementers | A class in a repository that is not converted cannot be validated against its interface |

**Is this compatible with what I first proposed? Yes, and it improves it.** The first proposal (a lookup table from `_t` to class,
chosen when loading) is the same idea. The differences it removes:

- **How the allowed classes are decided.** I had a table filled in as modules were imported. BHoM fixes the list when it generates.
  We copy that: the generator writes the list of implementers into each interface (as text, like `generic_params`), so the
  Python and the JSON Schema agree on exactly which classes an interface accepts.
- **How errors read.** I had not thought about this. BHoM picks the class from `_t` first, so the message names the real problem.
  Pydantic's "tagged union" does the same, so we get the same behaviour.
- **Enums.** I had left open whether enums are saved by name or number. BHoM saves names. Our generated enums are numbers
  (`None_ = 0`), so they would save as numbers and not match. They need to save as names, and load from a name or from BHoM's
  object form.

**One thing not copied: a plain Pydantic `Union` of all the implementers.** It is the closest built-in match to the JSON Schema, but
each interface field would have to import every implementer. `IFragment` alone has about 130, in 40 repositories, and the classes
refer to each other, which would create import cycles and a very slow import. So the implementers stay as text, and a class is
imported only when a `_t` value names it.

**The same limit applies.** An interface only accepts classes that are in the generated package. With the scope of Step 6
(BHoM/BHoM plus the test repository), an interface such as `IFragment` accepts only its implementers in those repositories, and
loading JSON that names another class gives a clear error ("`BH.oM.X.Y` is not in bhom_schema"). This is the same as the BHoM_JSONSchema
warning about partial generation, and it goes away as more repositories are converted.

### The decision

| Option | What you get | Effort |
|---|---|---|
| **Stop at the current state** | Python objects can be created but not reliably saved or loaded | none |
| **Follow the BHoM JSON Schema rules** (recommended) | Python saves and loads JSON that BHoM_JSONSchema accepts, and loads what BHoM C# writes. Interface fields, JSON Schema output and enums all work | Medium. Smaller than the old "5B", because the rules are written down and the published schemas can serve as the test |

The old split into 5A (Python only) and 5B (compatible with C#) is gone: following the published rules is one piece of work, and it
is also the lower-risk one, because there is no second format to invent and maintain.

### What we will do

5.1 **Record the decision** and update CODING-PLAN section 1 (BHoM JSON becomes in scope, as "the JSON that BHoM_JSONSchema describes").

5.2 **`_t` and `_bhomVersion` on every class.** Every generated class gets an optional `_t`, fixed to its C# class name, and an
optional `_bhomVersion`. Python field names cannot start with `_`, so they are written with an alias (`_t` in the JSON) and objects
are saved using the aliases. The reader in py2cs ignores both.

5.3 **The implementers of an interface, written by the generator.** Each interface module gets a list of the C# names of the classes
that implement it, from the classes the generator converts (like `generic_params`, as text, with no imports).

5.4 **One reusable type for interface fields.** In `src/bhom_schema/_support`, a `Polymorphic[ICurve]` type. To validate a value:
if it is already an object of an allowed class, accept it; if it is JSON, require `_t`, check it is one of the interface's
implementers, import that class only now, and validate against it alone. When saving, write the real class with its `_t`. The
generator writes `Polymorphic[...]` for interface-typed and abstract-typed fields, and for lists and dictionaries of them.

5.5 **JSON Schema output that matches BHoM_JSONSchema.** `model_json_schema()` describes a `Polymorphic` field the way BHoM does
(`_t` required, one of the implementers, then that class's schema), so it works for every class, `BHoMObject.Fragments` included.

5.6 **Enums as names.** Generated enums save as their name (`None_` saves as `"None"`, using the renamed-members record) and load
from a name, a number, or BHoM's object form `{"_t": "System.Enum", "TypeName": {...}, "Value": "..."}`. Check flags enums and
the other special values (`BHoM_Guid`, `CustomData`, `FragmentSet`, `NaN`) against the published schemas and C# output before fixing
their form.

5.7 **Keep py2cs working**: it learns to ignore `_t` and `_bhomVersion`, and to read `Polymorphic[...]` as the plain interface.

### How we'll know it works

- The `Edge` example above saves and loads correctly, and a loaded `ICurve` is the right class (`Line`, not just any curve).
- `model_json_schema()` works for every generated class.
- **Conformance with BHoM_JSONSchema.** JSON saved from Python objects validates against the matching schemas of BHoM_JSONSchema (a
  read-only clone, used only as the test, so the generator still does not depend on that repository), and an object with a missing
  field is rejected by both with the same reason. Skipped when the clone is not there.
- JSON written by BHoM in C# (a few recorded samples) loads in Python and saves back as equivalent JSON.
- An error for a bad interface value names the real problem, and a `_t` that is not an implementer is refused with a clear message. (Python is looser than the
  published schema in one way: a field that has a default may be left out, while BHoM_JSONSchema lists every field as required.)
- Loading one class doesn't import unrelated parts of the package.
- The build and test gate passes.

---

## What was done in Step 6

- **6.2 attribute classes:** `TypeSelector` skips every class based on `System.Attribute`.
- **6.3 version:** the generator reads `Major.Minor` from the assembly version of `BHoM.dll`, or of another loaded assembly when it is missing (`BHoMAdapter.BHoMVersion`; every BHoM project sets `<AssemblyVersion>`, which DevOps raises), and, on a full run (not `--types`), writes
  `bhom_schema/_version.py` with `__bhom_version__` and `__version__` (`X.Y.0.dev0`, or `X.Y.0` with `--release X.Y`). The file is only rewritten when its
  text changes. `--release` fails with exit code 1 when `X.Y` is not the version read. `pyproject.toml` takes the version from that file, `bhom_schema.__version__`
  shows it, and `py2cs` and the test helpers skip `_version.py`. The committed `_version.py` says `10.0`, the version the CI builds; the next weekly run corrects it
  if BHoM says otherwise (a laptop with another BHoM installed, such as 9.3, would write that).
- **6.4 notes:** `python -m py2cs notes --head-root ... [--base-root ... --previous TAG] --version X.Y.0 --out notes.md`.
- **6.5 `release.yml`:** manual, dry run by default, the steps of 6.5 above; the build job has `contents: write`, only the TestPyPI job has `id-token: write`, and no
  secret is used.
- **Tests:** NUnit `VersionTests` (attribute classes, the version read, `_version.py` once, `--release` match and mismatch, no file for a partial run);
  pytest `test_notes.py` and two workflow tests. A wheel built from the repository is named `bhom_schema-10.0.0.dev0`.
- **Not verified:** the release workflow has never run on GitHub; TestPyPI trusted publishing is not set up (an administrator does it once, see
  [Workflows.md](../Workflows.md)); real PyPI is left for when BHoM/BHoM is in scope; the relation between a BHoM release number and the `AssemblyVersion` is
  assumed (the `--release` check stops a wrong name).

---

## Step 6 (Issue 6): the scope, a version number, and publishing

> **Revised 2026-10-29** after reading BHoM_JSONSchema's releases, BHoM's versioning code and Step 5. The scope is the CSharpSchema_Test
> repository for now; BHoM/BHoM comes later.

### What's wrong, in plain words

- It also includes C# *attribute* classes (the things written in square brackets, like `[Description]`). They aren't data, so they don't
  belong in the package.
- The version is always `0.1.0`, so users can't tell which BHoM release the classes match, and nobody can `pip install` the package.

### What we decided

| Question | Decision |
|---|---|
| Scope | Only `BHoM/CSharpSchema_Test` for now (already the case: `Converted-repositories.txt` and `--repos`). BHoM/BHoM is added later by adding it to the two repository lists |
| What is a version for? | pip needs one, users pin and upgrade by it, and a release is a point you can name in a bug report. Nothing else: Python users do not run Versioning_Toolkit |
| Where does the number come from? | From BHoM, not typed by hand: the generator reads the `Major.Minor` of the `AssemblyVersion` of `BHoM.dll`, or of any loaded assembly when it is missing (for example `10.0`; DevOps raises it in every project) |
| Version in every class marker? | No |
| Stamping `_bhomVersion` when saving JSON, a warning when loading JSON of another version, refusing unknown keys? | No. Python never writes JSON for C# to upgrade, so nothing needs them. The optional `bhom_version` field stays, so the published schemas and the classes agree, and a value that is set is written and read |
| How are releases made? | Like BHoM_JSONSchema: `develop` is regenerated every week; at the end of a milestone a branch `vX.Y` is made, regenerated, tagged and released, and then left alone |
| Where is it published? | A GitHub Release with the wheel, and TestPyPI. Real PyPI when BHoM/BHoM is in scope: putting the test classes there would keep them on a public index for good |

### What we will do

6.1 **Scope:** nothing new. It is done (`--repos`, `Converted-repositories.txt`).

6.2 **Leave out attribute classes.** The generator skips any class based on `System.Attribute`. (The list of test-only assemblies is not
needed until BHoM/BHoM is in scope.)

6.3 **Version from BHoM.** The generator writes `bhom_schema/_version.py`:
- `__bhom_version__ = "10.0"`: the BHoM `Major.Minor` of the assemblies it read.
- `__version__ = "10.0.0.dev0"` on `develop` (the committed value only changes when the BHoM version changes, so the weekly run does not
  make a commit just for a date), and `"10.0.0"` for a release.
- `--release X.Y` makes a release version. It fails when `X.Y` is not the BHoM version it read, so a release cannot be named wrongly.
- `pyproject.toml` takes the package version from `_version.py`, and `bhom_schema.__version__` shows it.

6.4 **Release notes.** `python -m py2cs notes` compares the classes of the previous release with the new ones and writes the added and
removed classes and a "Breaking changes" section (removed or renamed properties, changed types and so on, the same list the linked C# pull
request uses). That is how a Python user learns what to change before upgrading.

6.5 **`release.yml`** (by hand, input `X.Y`, with a dry run): clones and builds the C# repositories, regenerates with `--release`,
checks the result, commits it to a new branch `vX.Y`, tags `vX.Y.0`, builds the wheel, creates a GitHub Release with the wheel and the
release notes, and publishes to TestPyPI. TestPyPI is reached with "trusted publishing" (GitHub proves who it is, so there is no password or
token to store); that is set up once on TestPyPI.

### How we'll know it works

- Tests: attribute classes are not generated; `_version.py` holds the BHoM version and `X.Y.0.dev0`; `--release` gives `X.Y.0` and fails for a
  different `X.Y`; the release notes list added, removed and breaking changes; the release workflow has no push or schedule trigger, only
  the publish job can ask for the identity token, and it uses no stored secret.
- A wheel built from the repository installs and reports the right version.
- The build and test gate passes.

---

## Step 7 (Issue 7): five small generator fixes

Each is small and independent; do them in any order.

7.1 **The copyright year.** Every generated file starts with `Copyright (c) 2015 - 2026`, typed into the code. In January
someone changes it to 2027, and **every** generated file changes at once, which makes a huge, meaningless PR. Fix: leave the
year range out of generated Python files, or read it from one setting that is changed on purpose in its own PR. C# files must
still follow the BHoM copyright rule.

7.2 **Old folders left behind.** When a run doesn't include an assembly at all (for example because its build failed), its old
Python files stay, and nobody is told. Fix: a full run lists every assembly folder it didn't generate; the weekly job can also
delete them with a new option, `--clean-missing-assemblies`.

7.3 **Two classes with the same file name.** On Windows, file names ignore upper and lower case, so `Panel` and `PANEL` would land
in the same file. Today one class is dropped with only a warning. Fix: make it an error that stops the run.

7.4 **`DateTimeOffset` turns into `DateTime`.** C# has two date types; both become Python `datetime`, and on the way back the
difference is lost. Fix: remember the original C# type in the field's `ClrType` marker.

7.5 **`Included-repositories.txt`**: it spells the dKoP repository `dKop_Toolkit` and the file doesn't end with a newline, which
makes some tools skip the last line. Fix both. (This file is copied from the JSON repository; keep it in line with theirs.)

### How we'll know it works

One test per fix, then the build and test gate passes.

---

## Step 8 (Issue 8): tidy the documentation

8.1 **CODING-PLAN.md** still says "plan only, no code written yet", right above a section saying phases 0 to 6 are done. Move the
status to the top, remove the old line, and record the decisions from this audit.

8.2 **Reusing-oM-Classes.md** is a pasted chat answer, and part of it is out of date (it says `Tree_1` fails to import; that was
fixed). Rewrite it as a short reference, or merge it into the gotchas document.

8.3 **The same commands are repeated** in "Converting all oM classes" and "Generating the real package", including small scripts
you copy and paste. Keep one procedure, and turn the scripts into proper commands (for example `python -m py2cs import-all`
and `python -m py2cs compare`) that the guides and the workflows both use.

8.4 **README**: add the rules for editing the Python (Step 1), the PR rules (Step 3), how to install and use the package, and
links to the other guides.

8.5 **Testing guide**: update the test counts and describe the new tests (patcher, alignment check, JSON).

### How we'll know it works

The docs match the code and workflows, nothing in them is out of date, and a final run of the build and test gate passes.
