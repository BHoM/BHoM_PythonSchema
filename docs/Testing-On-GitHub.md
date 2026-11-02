# Testing the loop on GitHub

A procedure for proving, on GitHub, the whole loop between this repository and [CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test)
(the C# repository that owns the classes for now). It has three exercises, each ending with the Python and the C# matching again:

| Exercise | You change in Python | Expected in C# |
|---|---|---|
| A. Reuse a class | a new class that uses an existing one (`Beam`) | one new file; `Beam` is not touched |
| B. Update a class | a property of `Beam` (added, then changed or removed) | the lines of that property change in the existing file; breaking changes are labelled |
| C. Add a class | a new class and its file | one new file in the right folder and namespace |

Separately, "Testing the build cache" proves that the PR checks build only the C# repositories that changed. This procedure has not been run
yet. Part 0 is done once; the three exercises can be done in any order. How each workflow works is in
[Workflows.md](Workflows.md); the Python authoring rules are checked by `py2cs check`.

## Part 0: before the first exercise

**Setup (an administrator, once).** Everything in "One-time setup" of [Workflows.md](Workflows.md): the GitHub App installed on
CSharpSchema_Test with *Contents* and *Pull requests* write access, the secrets `BHOM_APP_ID` and `BHOM_APP_PRIVATE_KEY`, and the
App (or `github-actions[bot]`) allowed to push to `develop` if it is protected. CSharpSchema_Test must be public.

**Protect the `develop` branch of the C# repository (once per C# repository).** The tooling of the linked PR runs from the Python pull
request, with a token that has *Contents: write*. Protecting `develop` means that token can open pull requests but never push to `develop`.
In CSharpSchema_Test: Settings, Rules, Rulesets, New ruleset, New branch ruleset:

1. Name it `Protect develop`, set *Enforcement status* to **Active**, and leave the *Bypass list* empty (the App must not be on it).
2. Under *Target branches*, Add target, Include by pattern, `develop`.
3. Tick **Restrict deletions**, **Block force pushes** and **Require a pull request before merging** (required approvals can be 0 for this test repository).
4. Create. Then check it: a direct `git push origin develop` from a clone must be refused, while merging a pull request still works.

(The older equivalent is Settings, Branches, Add branch protection rule, branch name pattern `develop`, with *Require a pull request before
merging* ticked. The real BHoM repositories already have this.)

**Check the starting point.**

1. Run *Python schema generation* from the Actions tab (branch `develop`, `dry_run` ticked). It must be green. Open the attached
   `generation-report`: no failed types.
2. Run it again with `dry_run` unticked. The log must end with `No changes: the Python already matches the C#`. If it commits instead,
   that commit is the difference between the C# and what is in `develop`; look at it before going on, because every exercise below
   assumes the two are in step.
3. Check that `develop` has `src/bhom_schema/FixtureAlpha_oM/Beam.py` and that CSharpSchema_Test `develop` has no open
   `python-schema/pr-*` branch left over from an earlier test.

**For every exercise.**

- Work on a branch of this repository (not a fork: forks get no linked C# pull request) and open a pull request to `develop`.
- Check it locally first, so GitHub is not the first place to find a mistake. In a clone with the C# repository next to it:

  ```powershell
  $env:PYTHONPATH = ".ci/generation"
  .venv\Scripts\python -m py2cs check --root src/bhom_schema --base-root <the same folder at develop>
  ```

  `check` reports every problem, including missing descriptions on new classes and fields.
- After pushing, three things start by themselves; Part "What to look at" below lists what each should show.

## Exercise A: reuse an existing Python class

Goal: a new class that has a `Beam` inside it, and a C# file that refers to `Beam` without changing it.

1. Add `src/bhom_schema/FixtureAlpha_oM/BeamPair.py`. Copy the header comments and the `__bhom__` marker style of `Beam.py`, then:

   ```python
   from __future__ import annotations

   from typing import Any, ClassVar

   from pydantic import Field

   from bhom_schema.BHoM.BHoMObject import BHoMObject
   from bhom_schema.FixtureAlpha_oM.Beam import Beam


   class BeamPair(BHoMObject):
       __bhom__: ClassVar[dict[str, Any]] = {
           'clr_name': 'BH.oM.FixtureAlpha.BeamPair',
           'assembly': 'FixtureAlpha_oM',
           'namespace': 'BH.oM.FixtureAlpha',
           'repo': 'BHoM/CSharpSchema_Test',
           'kind': 'class',
       }

       First: Beam | None = Field(default=None, description='The first beam of the pair.')
       Second: Beam | None = Field(default=None, description='The second beam of the pair.')
   ```

   Variation to try afterwards: a subclass, `class TallBeam(Beam)`, with `'clr_name': 'BH.oM.FixtureAlpha.TallBeam'`.
2. Open the pull request and follow "What to look at". Expected in the linked C# draft: one new file `BeamPair.cs`, with properties typed
   `Beam`, and **no change** to `Beam.cs`. The plan lists `Beam` only as something the new class refers to.
3. Finish with "Closing the loop".

## Exercise B: update an existing class

Goal: change `Beam` and see only the changed lines change in `Beam.cs`.

Do these as three separate pull requests (or three commits that you test one at a time), so each result is clear.

1. **Add** a property to `src/bhom_schema/FixtureAlpha_oM/Beam.py`, with a description:

   ```python
   Material: str = Field(default='Steel', description='Name of the material.')
   ```

   Expected: the draft adds one property to `Beam.cs`. Everything else in the file (other members, comments, formatting) is unchanged, and
   there is no `breaking-change` label.
2. **Change** it: for example the default `'Steel'` to `'Concrete'`, or its description. Expected: only that property changes.
3. **Break** it: remove `Material`, or change its type from `str` to `int`. Expected: the draft is labelled `breaking-change`, and the
   pull request text has a "Breaking changes" section naming the class and the change. Whoever reviews the C# decides whether it needs
   a versioning upgrade; nothing is merged by itself.

## Exercise C: add a new Python class

Goal: a class that nothing else uses, written from scratch.

1. Add `src/bhom_schema/FixtureAlpha_oM/Column.py` in the style of `BeamPair.py`, with its own fields:

   ```python
   Height: float = Field(default=3.0, description='Height of the column.')
   Label: str = Field(default='', description='Name shown to the user.')
   ```

   Use a `clr_name` in a namespace that already exists in CSharpSchema_Test, then repeat with a new sub-namespace
   (`'BH.oM.FixtureAlpha.Columns'`) to see where the file is placed.
2. Expected: one new file in the matching folder of `FixtureAlpha_oM`, with the namespace of its `clr_name`. The draft pull request lists
   it as an added class.
3. Try one mistake on purpose: remove a `description` or give a `clr_name` that names no repository in `Converted-repositories.txt`.
   Expected: `pr-checks` fails with a message that names the file and line, and no C# pull request is raised for a class that cannot be placed.

## What to look at (every exercise)

| Where | What you should see |
|---|---|
| **PR / Build and tests** on the Python PR | Build, NUnit, pytest and Pyright pass. `py2cs check` passes |
| **PR / C# alignment** on the Python PR | **Fails until the linked C# PR is merged**, with an explanation in the job summary: it compares the Python with what the C# `develop` generates. That failure is the proof that the two are not in step yet |
| **C# PR / Raise or update draft** | Green. The step *Which repositories does the change touch?* names `BHoM/CSharpSchema_Test`; *Push the branch and open or update the draft pull request* pushes `python-schema/pr-<N>` and opens a **draft** PR |
| The C# draft PR | The files and lines in the table at the top of the exercise, a link back to the Python PR, labels, and nothing else changed. Open the diff and read it as a C# reviewer would. Check that it builds |
| Comment on the Python PR | `Draft C# pull request: <link>`, written once and updated in place on later pushes |
| The Python PR after a push | Pushing again updates the same branch and the same draft; no second PR |

To try the flow before relying on the automatic run, start *C# PR* by hand with the Python PR number: with `dry_run` ticked it
prints what it would do and proves the App token; unticked it does it.

## Closing the loop (every exercise)

1. In CSharpSchema_Test, review the draft, fix anything wrong **in C#** (the C# is the source of truth), mark it ready and merge it.
2. Back on the Python PR, re-run **C# alignment** by hand (Re-run jobs); nothing re-runs it for you.
3. Check **C# alignment**. It must now pass: the Python generated from the merged C# equals the Python in the PR.
   If it still fails, the message lists what differs; either the C# review changed something (copy the change into the Python)
   or the generator and `py2cs` disagree (a bug to fix in this repository).
   The NUnit tests and their golden files use their own test classes (`.ci/unit-tests/csharp/Fixtures`), so a merged
   C# change never needs a golden update. A test that deletes a fixture class file must pick a class that no other fixture imports.
4. Merge the Python PR.
5. Run *Python schema generation* live (or wait for Saturday). Expected: `No changes: the Python already matches the C#`.
   If it commits, the commit shows exactly how the generated Python differs from what was written by hand (often only formatting or
   ordering); that is the real result of the exercise and what to improve next.

A pull request that is closed without merging closes its draft with a comment; delete the `python-schema/pr-<N>` branch in C# by hand.

## Testing the build cache

The PR checks keep a build cache with one entry per C# repository (see [Per-Repository-Build-Cache-Plan.md](Per-Repository-Build-Cache-Plan.md)).
These tests prove that a repository is built only when its commit, or a dependency's commit, changed, and that `develop` shares the build
with every pull request.

**Part D1 can run from the `ImproveCaching` pull request before it is merged. Part D2 needs it merged into `develop` first.** A pull request runs
the `pr-checks.yml` of its own branch, so D1 tests the new action as it is. `build-cache.yml` is different: GitHub starts a `workflow_run`
workflow, and lists a workflow under *Run workflow*, only from the default branch, so before the merge it never runs. And only a run on
`develop` can save the cache that every pull request reads.

### Where to look

| Where | What it tells you |
|---|---|
| Step *Plan the build* of the job | The commit and entry name of each repository, and the cache key |
| Step *Restore the build cache* | `Cache restored from key: <key>`; when that key differs from the planned key it was a prefix hit, an earlier state. `Cache not found` means nothing could be restored |
| Step *Build the repositories in dependency order* | The same table with `hit` or `miss` per repository, then `Restoring <name> from the cache...` for a hit, `Cloning <repo> at <commit>...` and `Building <name>...` for a miss, `Deleting the old entry <entry>`, and finally `Built: <names>` or `Built: nothing` |
| Step *Save the build cache* | Skipped when nothing was built |
| Actions tab, *Caches* (under Management) | Each `bhom-build-cache-v1-Windows-...` entry and its branch: `refs/pull/<N>/merge` for a pull request, `refs/heads/develop` for `develop` |

### Part D1: on the `ImproveCaching` pull request (before merging)

1. **First run, everything is built.** Open the pull request from `ImproveCaching` to `develop`. In **PR / Build and tests**: the restore
   says `Cache not found` (the old `bhom-assemblies-v1-...` entries do not match the new prefix), the build clones the four repositories at
   the commits of the plan and ends with `Built: BHoM, BHoM_Engine, JSONSchema_Toolkit, CSharpSchema_Test`, and the save runs. Every test
   passes, which shows that the assemblies installed this way are the ones the tests need. *Caches* shows one new entry on `refs/pull/<N>/merge`.
2. **The alignment job waits.** **PR / C# alignment** starts only once **Build and tests** has finished. This pull request does not change
   `src/bhom_schema`, so its steps are skipped; D2 step 5 tests it with a build.
3. **A re-run builds nothing.** Re-run all jobs. The restore names the planned key exactly, the build table says `hit` for all four, the log
   has four `Restoring ... from the cache...` lines and `Built: nothing`, and the save is skipped. Note how long *Build the repositories* takes
   compared with step 1.
4. **One changed repository is built alone.** Make a commit on `develop` of CSharpSchema_Test (for example merge the C# draft of an exercise,
   or a small pull request there), then re-run the jobs. The table says `miss` for CSharpSchema_Test and `hit` for the others, the log ends with
   `Built: CSharpSchema_Test`, the old entry of CSharpSchema_Test is deleted, and the save runs under a new key.
   If BHoM_Engine or BHoM changed upstream in the meantime, that repository and the ones that depend on it are built too. Compare the commits
   in the table with the repositories to check it.
5. **Nothing runs on `develop` yet.** No *Build cache* run appears in the Actions tab. That is expected before the merge.

### Part D2: after merging into `develop`

1. **Fill the `develop` cache by hand.** Actions, *Build cache*, Run workflow, branch `develop`. The gate prints `develop has no entry
   starting with bhom-build-cache-v1-Windows-...`, then **Build and save on develop** builds the four repositories (`develop` cannot read
   a pull request's cache) and saves. *Caches* shows an entry on `refs/heads/develop`.
2. **Try a manual run from another branch.** Run *Build cache* from `ImproveCaching` or any other branch: both jobs are skipped, so
   nothing but `develop` can write to the `develop` cache.
3. **A new pull request builds nothing.** Open a new pull request that changes `src/bhom_schema` (Exercise A is a good one). Its first run
   restores the exact key from `develop` and logs `Built: nothing` in **Build and tests**, and **C# alignment** logs `Built: nothing` too.
4. **No refresh when `develop` is up to date.** When that PR run completes, *Build cache* starts by itself. The gate prints `develop has:
   <key>` and the refresh job is skipped.
5. **One changed repository is built once, then shared.** Make a commit on `develop` of CSharpSchema_Test (closing the loop of an exercise does
   this), then push to the pull request or re-run its jobs.
   - **Build and tests** builds only CSharpSchema_Test.
   - **C# alignment** waits for it and logs `Built: nothing`, because it restores what the first job just saved. Without the wait it would
     have built CSharpSchema_Test a second time.
   - The *Build cache* run that follows finds no entry for the new state on `develop`. Its refresh builds only CSharpSchema_Test, from the
     `develop` entries of the others, and saves on `develop`.
   - Open, or re-run, a second pull request. It restores that `develop` entry and builds nothing.
6. **The C# alignment still runs when a test fails** (optional). Push a commit that makes one pytest test fail. **Build and tests** fails,
   and **C# alignment** still runs.
7. **A fork gets no refresh** (optional, needs a fork). A pull request from a fork runs the PR checks with its own cache, and the *Build cache*
   run that follows skips both jobs.
8. **Switching the cache off** (optional). On a branch, give the action `with: no-cache: 'true'` in `pr-checks.yml`. The restore and save are
   skipped, and every repository is built, as before this cache. Do not merge that change.

## If something goes wrong

| Symptom | Likely cause |
|---|---|
| `linked-csharp-pr` fails with `No module named py2cs` | the base branch has no `py2cs` yet (only for the very first pull request) |
| `repos` reports `[]` and nothing is raised | the class changed is not under a repository in `Converted-repositories.txt`, or its `repo` marker is wrong |
| `raise` fails when making the token | the App is not installed on CSharpSchema_Test, or the secrets are missing |
| the draft changes more than the lines you changed | report it: that is a bug in the patcher, with the file and your Python diff |
| `py2cs align` still fails after the C# merge | the C# `develop` clone in the workflow is older than the merge, or the C# review changed the class; read the listed differences |
| the weekly run commits after everything merged | the generator writes the class differently from what `py2cs` drafted: look at the commit |
| *Build cache* never runs after a PR run | `build-cache.yml` is not on `develop` yet, or the PR workflow was renamed (the trigger names `PR`) |
| the gate fails on `gh cache list` | the `gh` of the ubuntu runner is too old for `--ref`; the log shows the error |
| every pull request builds everything | `develop` has no entry, or one made with other build tools after an MSBuild update on the runner: run *Build cache* by hand on `develop` |
| `Building <name> failed` | the C# of that repository does not build at its planned commit. The run stops so a failed build never becomes an entry |
| tests fail after a restore but pass with `no-cache` | a wrong entry: bump `-Salt` (the `v1`) in `Build-Repositories.ps1` to throw every cache away, and report it with both logs |

## Record the result

For each exercise note the Python PR, the C# PR, whether the draft matched "Expected", and the final generation result. Anything that did not
match is a finding for [audit-1](audit-1/Fix-Plan.md).
