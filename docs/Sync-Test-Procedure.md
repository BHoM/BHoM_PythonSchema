# Testing the sync between BHoM_PythonSchema and DataSchema_Toolkit

A step-by-step procedure for proving that a change in the Python classes (`src/bhom_schema/DataSchema_oM`) is followed by the C# classes in
[DataSchema_Toolkit](https://github.com/BHoM/DataSchema_Toolkit) (`DataSchema_oM`), and that the two end up matching again.
Every change is **undone by the next test of the same sequence**, so when the procedure ends, neither repository holds anything that was not there
before. Ideas for further tests are in [Sync-Extra-Tests.md](Sync-Extra-Tests.md); how each workflow works is in [Workflows.md](Workflows.md).

| Test | You change in Python | Expected in C# | Undone by |
|---|---|---|---|
| 1. Add a field | a new property `SyncTestField` (`str`) on `Grid` | one property added to `Grid.cs`, nothing else touched | test 3 |
| 2. Change the field type | `SyncTestField` from `str` to `int` | the type and the initial value of that property change; labelled `breaking-change` | test 3 |
| 3. Remove the field | `SyncTestField` removed | the property is removed from `Grid.cs`; labelled `breaking-change`; `Grid.cs` is the same as before test 1 | |
| 4. Add a class | a new dummy class `SyncTestDummy` | one new file `SyncTestDummy.cs` in `DataSchema_oM` | test 5 |
| 5. Remove the class | `SyncTestDummy` removed | **no file is drafted**: a class removed in Python is deleted in C# by hand | |

The field tests use only a field that the procedure itself creates, so no existing property of an existing class is ever changed, and `Grid` is the
host because it is a small class with only two properties (`ExampleObject` has a `Grid` field, which a new field on `Grid` does not disturb). The same holds for the class tests: only `SyncTestDummy` is added
and removed.

## Read this before you start

- **The C# pull requests are merged into the real `develop` of DataSchema_Toolkit.** The loop only proves itself when the C# is merged (the alignment
  check compares against the merged C#). Tell the owners of DataSchema_Toolkit when you run this, and do the whole sequence in one sitting.
- **Do not leave a test half done over a Saturday or a morning alpha.** The weekly *Python schema generation* (Saturday 4 AM UTC) rewrites
  `src/bhom_schema` from the C# `develop`, and the daily *alpha release* (6 AM UTC) publishes `develop` as it is. A dummy field or class that is merged
  and not yet removed would be generated into `develop` and published. Run the sequence between two of those times, or accept that one alpha
  carries the dummy.
- **If you only want to see the drafts**, do steps 1 to 6 of each test and then close both pull requests without merging (see "Stop early" at the end of
  "Closing the loop"). Nothing changes in either repository; you test the draft, but not the alignment.
- The Python file you edit starts with `Do not edit by hand` because it is normally generated. That comment is about the weekly generation, which
  overwrites such files; the linked-PR loop is the sanctioned way to change them, and the generation brings your change back into line once the C# is merged.

## Part 0: before the first test

**Setup (once, an administrator).** Everything under "One-time setup" in [Workflows.md](Workflows.md), with one addition that this procedure needs:

- The GitHub App is **installed on DataSchema_Toolkit** (that page says CSharpSchema_Test only; `Converted-repositories.txt` now lists both). A repository outside the
  installation gets no token, and the *C# PR* job then fails at *Make a token for the C# repositories touched*.
- The `develop` branch of DataSchema_Toolkit is protected as described under "Protect the `develop` branch" in [Testing-On-GitHub.md](Testing-On-GitHub.md):
  a pull request is required, direct pushes are refused.
- `Converted-repositories.txt` lists `BHoM/DataSchema_Toolkit`. It does.

**Starting point.**

1. In this repository on `develop`: `git pull`, and note the commit: `git rev-parse HEAD`. Write it in the results table at the end.
2. In `C:\Github\DataSchema_Toolkit` on `develop`: `git pull`, and note its commit the same way.
3. Run *Python schema generation* from the Actions tab (branch `develop`, `dry_run` ticked): it must be green. Then run it with `dry_run` unticked: the log must
   end with `No changes: the Python already matches the C#`. If it commits instead, stop and look at that commit; every test below assumes the two repositories
   are in step. Pull `develop` again afterwards.
4. DataSchema_Toolkit has no open `python-schema/pr-*` branch or draft from an earlier test.
5. Build the C# patcher once, for the local rehearsal: `dotnet build .ci/generation/PythonSchemaGeneration.Patcher -c Release`. The repository needs its `.venv` as in the README.

## Part 1: the local rehearsal (every test)

Before each push, run what the workflows will run, so GitHub is not the first place to find a mistake. Nothing here writes to a C# repository: `plan` only
drafts into a scratch folder, and `pr --dry-run` is offline.

```powershell
cd C:\Github\BHoM_PythonSchema
$env:PYTHONPATH = ".ci/generation"
$env:PY2CS_PATCHER = ".ci/generation/PythonSchemaGeneration.Patcher/bin/Release/net8.0/PythonSchemaGeneration.Patcher.dll"

# 1. Keep the Python as it is on develop, BEFORE you edit it
Remove-Item -Recurse -Force $env:TEMP\sync-base -ErrorAction SilentlyContinue
Copy-Item -Recurse src\bhom_schema $env:TEMP\sync-base

# 2. Edit the Python as the test says, then:
.venv\Scripts\python -m py2cs check --root src/bhom_schema --base-root $env:TEMP\sync-base
.venv\Scripts\python -m py2cs plan --base-root $env:TEMP\sync-base --head-root src/bhom_schema --clones-parent C:\Github --allowed-repos Converted-repositories.txt --only-repo BHoM/DataSchema_Toolkit --python-pr BHoM/BHoM_PythonSchema#0 --out $env:TEMP\sync-plan
.venv\Scripts\python -m py2cs pr --plan-dir $env:TEMP\sync-plan --repo BHoM/DataSchema_Toolkit --python-repo BHoM/BHoM_PythonSchema --python-pr 0 --dry-run

# 3. Read the draft the way a C# reviewer would
Get-Content $env:TEMP\sync-plan\reports\BHoM__DataSchema_Toolkit.md
git diff --no-index C:\Github\DataSchema_Toolkit\DataSchema_oM $env:TEMP\sync-plan\BHoM__DataSchema_Toolkit\DataSchema_oM
```

`C:\Github\DataSchema_Toolkit` must be at the current `develop`, because `plan` reads the existing C# from it. What to see:

- `check` ends with `0 errors` (a new class prints a warning that its `__bhom__` marker was worked out; that is expected).
- `plan` ends with `1 files planned in 1 repositories, 0 problems`.
- `pr --dry-run` prints `would create branch BHoM/DataSchema_Toolkit python-schema/pr-0 from develop` and `would write file ... (patch)` (or `(new file)`).
  For a removal it prints `would skip BHoM/DataSchema_Toolkit no planned files for this repository`.
- The git diff shows only the lines the test expects.

## Part 2: what is the same in every test (GitHub)

Do each test on a branch **of this repository** (a fork gets no linked C# pull request, because forks get no secrets), named `sync-test/<number>-<what>`,
with a pull request to `develop`. After each push, look at:

| Where | What you should see |
|---|---|
| **PR checks / Build and tests** | Green: build, NUnit, pytest, Pyright, and `py2cs check` (the PR changes `src/bhom_schema`) |
| **PR checks / C# alignment** | **Red until the C# is merged**, with the explanation in the job summary. That failure proves the two are not in step yet |
| **C# PR / Raise or update draft** | Green. *Which repositories does the change touch?* names `BHoM/DataSchema_Toolkit` (and nothing else); the last step opens a **draft** PR from the branch `python-schema/pr-<N>` |
| The draft in DataSchema_Toolkit | The lines named in the test, a link back to the Python PR, the `breaking-change` label when the test says so, and no other file changed |
| Comment on the Python PR | `Draft C# pull request: <link>`, once; pushing again updates it in place |
| A second push to the Python PR | The same branch and the same draft are updated; no second PR |

To try the flow before relying on the automatic run, start *C# PR* by hand with the Python PR number: with `dry_run` ticked it makes the App token (which
proves the installation) and prints what it would do.

## Closing the loop (after every test)

1. **Build the draft.** In `C:\Github\DataSchema_Toolkit`: `git fetch`, `git checkout python-schema/pr-<N>`, then
   `dotnet build DataSchema_oM\DataSchema_oM.csproj` (the BHoM assemblies must be installed, as for any BHoM build). It must compile. Go back with `git checkout develop`.
2. **Review and merge the C# draft** in DataSchema_Toolkit: read the diff, fix anything wrong **in C#** (the C# is the source of truth), mark it ready, merge.
   Delete the `python-schema/pr-<N>` branch.
3. **Re-run the alignment** on the Python PR (Actions, *Re-run jobs*; nothing re-runs it for you). It must go **green**: the Python generated from the merged C#
   equals the Python in the PR. If it lists a difference, either the C# review changed something (copy it into the Python) or the generator and `py2cs`
   disagree, which is a bug to fix in this repository.
4. **Merge the Python PR.**
5. **Run *Python schema generation* live** (not dry run) and look at the end of the log. `No changes: the Python already matches the C#` is the best result. If it
   commits, the commit shows how the generated Python differs from what was written by hand (usually only formatting, the `__bhom__` marker or the order of
   members); that is the real result of the test. Pull `develop`, and start the next test from it.

**Stop early (drafts only).** Close the Python PR without merging. *Linked C# PR close* closes the draft with a comment; delete the `python-schema/pr-<N>`
branch in DataSchema_Toolkit by hand. Neither repository has changed.

## Test 1: add a field

Goal: one new property in `Grid.cs`, and nothing else in that file changes.

1. Branch `sync-test/1-add-field`. Do step 1 of Part 1 (copy the Python before you edit).
2. In `src/bhom_schema/DataSchema_oM/Grid.py` add one line at the end of the class, after `TypicalYSpacing`:

   ```python
       SyncTestField: str = Field(default='', description='A field added to test the sync.')
   ```

3. Run Part 1. Expect, in the report: `Changes in Python: - property added: string SyncTestField`, no "Breaking changes" section, and a draft that differs from
   `Grid.cs` by exactly three lines:

   ```csharp

           [Description("A field added to test the sync.")]
           public virtual string SyncTestField { get; set; } = "";
   ```

4. Push, open the pull request, and follow Part 2. The draft must not carry the `breaking-change` label (adding a property is not breaking).
5. Push a second commit that only changes the description text. Expect the same draft and branch to be updated, with one `Description` line changed.
6. Close the loop (all five steps). After step 5 the C# `develop` has `SyncTestField` in `Grid.cs`, and so does `src/bhom_schema` on `develop`.

## Test 2: change the field type

Goal: a type change is drafted as a change of that one property, and is labelled as breaking.

1. Branch `sync-test/2-change-type` from the `develop` that holds test 1. Do step 1 of Part 1.
2. In `Grid.py` change the line of test 1 to an `int`, and its default to match (a string default with an `int` type is refused by Pydantic):

   ```python
       SyncTestField: int = Field(default=0, description='A field added to test the sync.')
   ```

3. Run Part 1. Expect: `property SyncTestField type changed from string to int` and `property SyncTestField default changed from '' to 0`, a "Breaking changes" section that names
   `BH.oM.DataSchema.Grid`, and a draft that changes one line:

   ```csharp
           public virtual int SyncTestField { get; set; } = 0;
   ```

4. Push and follow Part 2. This time the draft **must** carry the `breaking-change` label, and the PR text must have the "Breaking changes" section. Nothing is blocked by it;
   a reviewer would decide on a Versioning_Toolkit upgrade.
5. Optional variation, in a throw-away commit that you drop afterwards: change the type to `float | None` with `Annotated[..., Quantity('Length', 'm')]` and see the
   `[Length]` attribute appear in the draft.
6. Close the loop.

## Test 3: remove the field

Goal: the property goes, and `Grid.cs` is the same as before test 1.

1. Branch `sync-test/3-remove-field` from `develop`. Do step 1 of Part 1.
2. In `Grid.py` delete the `SyncTestField` line.
3. Run Part 1. Expect: `property removed: int SyncTestField`, a "Breaking changes" section, and a draft that removes the three lines added in test 1 (the blank line, the `Description` and the property).
4. Push and follow Part 2: `breaking-change` label again.
5. Close the loop.
6. **Check the field is gone from both sides:**

   ```powershell
   git diff <starting commit of this repository> HEAD -- src/bhom_schema/DataSchema_oM/Grid.py
   git -C C:\Github\DataSchema_Toolkit diff <starting commit of DataSchema_Toolkit> HEAD -- DataSchema_oM/Grid.cs
   ```

   Both must print nothing (the commits in between are in the history; their net effect is zero). If the generation of test 3 step 5 changed the formatting of `Grid.py`,
   that is the only difference you may see, and it belongs in the results.

## Test 4: add a class

Goal: one new file in the right folder and namespace, and no existing file touched.

1. Branch `sync-test/4-add-class` from `develop`. Do step 1 of Part 1.
2. Add `src/bhom_schema/DataSchema_oM/SyncTestDummy.py` (one class per file, in the assembly folder that already exists, in the style of `docs/templates/NewClass.py`):

   ```python
   """A dummy class that tests the sync between Python and C#."""

   from __future__ import annotations

   from pydantic import Field

   from bhom_schema.BHoM.BHoMObject import BHoMObject


   class SyncTestDummy(BHoMObject):
       """A dummy class that tests the sync between Python and C#."""
       Label: str = Field("", description="A label.")
       Count: int = Field(0, description="A count.")
   ```

   No `__bhom__` marker is written: the folder says the assembly is `DataSchema_oM`, the namespace `BH.oM.DataSchema` and the repository `BHoM/DataSchema_Toolkit`.
3. Run Part 1. Expect: `check` ends with `0 errors, 1 warnings` and the warning says the marker was worked out as `BH.oM.DataSchema.SyncTestDummy`, `BHoM/DataSchema_Toolkit`, `class`; the report says
   `DataSchema_oM/SyncTestDummy.cs (new file)`, `Location: folder of 4 existing same kind files in namespace BH.oM.DataSchema`; and the git diff is one new file:

   ```csharp
   using BH.oM.Base;
   using System.ComponentModel;

   namespace BH.oM.DataSchema
   {
       [Description("A dummy class that tests the sync between Python and C#.")]
       public class SyncTestDummy : BHoMObject
       {
           [Description("A label.")]
           public virtual string Label { get; set; } = "";

           [Description("A count.")]
           public virtual int Count { get; set; } = 0;
       }
   }
   ```

   (with the same copyright header as its neighbours, and the section comments of the generated style). No existing file may be listed.
4. Push and follow Part 2. The draft has one added file and **no** `breaking-change` label.
5. Try one mistake on purpose, in a separate commit that you revert: delete the `description` of `Count`. Expect `py2cs check` to fail in **Build and tests** with the file and line. Write down
   what **C# PR** does with that commit (it runs on its own, so it may still update the draft); the draft must not be merged from that commit. Revert the commit.
6. Close the loop. In step 5 (generation) expect it to commit once: the generated `SyncTestDummy.py` has the `Generated by` header and the `__bhom__` marker that yours lacked. Pull `develop`.
7. Open `src/bhom_schema/DataSchema_oM/SyncTestDummy.py` on `develop` and check it imports: `python -c "from bhom_schema.DataSchema_oM.SyncTestDummy import SyncTestDummy; print(SyncTestDummy())"`.

## Test 5: remove the class

Goal: see what happens to a class that disappears from Python. The expected result is that **no C# is drafted** (the draft tooling never deletes a C# file), so the C# side is deleted by hand and the
alignment check then proves the two agree.

1. Branch `sync-test/5-remove-class` from `develop`. Do step 1 of Part 1.
2. Delete `src/bhom_schema/DataSchema_oM/SyncTestDummy.py`. (Do not touch any class that refers to it: nothing does.)
3. Run Part 1. Expect `check` to pass, the report to contain `Removed in Python (delete or deprecate in C# by hand): BH.oM.DataSchema.SyncTestDummy` and a "Breaking changes" section
   (`BH.oM.DataSchema.SyncTestDummy: type removed`), and `pr --dry-run` to print `would skip BHoM/DataSchema_Toolkit no planned files for this repository`.
4. Push and open the pull request. Expect:
   - **C# PR / Raise or update draft** does not open a pull request (there is nothing to draft). Write down what it shows: green with a skip, or no comment on the Python PR. This is the part of the
     procedure that has not been observed before.
   - **C# alignment** is red.
5. **Delete the class in C# by hand:** a branch `sync-test/remove-dummy` of DataSchema_Toolkit with `DataSchema_oM/SyncTestDummy.cs` deleted, and a pull request to `develop`. Merge it.
6. Re-run **C# alignment** on the Python PR: it must go green (the Python generated from the merged C# no longer has the class).
7. Merge the Python PR. Run *Python schema generation* live: `No changes`.
8. **End-state check.** Both of these must print nothing:

   ```powershell
   git diff <starting commit of this repository> HEAD -- src/bhom_schema
   git -C C:\Github\DataSchema_Toolkit diff <starting commit of DataSchema_Toolkit> HEAD -- DataSchema_oM
   ```

   Also look in DataSchema_Toolkit for leftover `python-schema/pr-*` and `sync-test/*` branches, and in this repository for leftover `sync-test/*` branches; delete them.

## Results

Fill in as you go.

| | Test 1 | Test 2 | Test 3 | Test 4 | Test 5 |
|---|---|---|---|---|---|
| Local rehearsal matched the expectation | | | | | |
| Python PR number | | | | | |
| C# draft number | | | | | |
| Draft as expected, label as expected | | | | | |
| Draft built | | | | | |
| Alignment green after the C# merge | | | | | |
| Generation after the merge: `No changes`? If not, what differed | | | | | |

| | Starting commit | After test 5 |
|---|---|---|
| BHoM_PythonSchema `develop` | | |
| DataSchema_Toolkit `develop` | | |
| Net difference in `src/bhom_schema` / `DataSchema_oM` | | |

## If something fails

| Symptom | Likely cause |
|---|---|
| *C# PR* fails at *Make a token for the C# repositories touched* | The App is not installed on DataSchema_Toolkit, or `BHOM_APP_ID` / `BHOM_APP_PRIVATE_KEY` are missing |
| *C# PR* is green but no draft appears | The PR is from a fork, or the change is only a removal (nothing to draft), or the C# already has the planned content (`already has the planned files, nothing to raise`) |
| `plan` says it cannot find the file of a class | `C:\Github\DataSchema_Toolkit` is not on the current `develop`, or the class is in a folder that is not an assembly folder of `src/bhom_schema` |
| `check` fails on a description or a default | Every class and field needs a description; a field without a default becomes a C# property without an initial value |
| Alignment stays red after the C# merge | Re-run it by hand; then read the list it prints (the first value is from the C#, the second from the PR) |
| Generation commits after the merge | Expected for a hand-written new class (header and marker); only a difference in the content of a field is a problem |
