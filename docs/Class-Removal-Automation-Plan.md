# Plan: raise a C# pull request when a Python class is removed

**Status: implemented** (patcher `removeType`, the `delete` action in `plan` and `pr`, `delete_file` in the GitHub client, with tests in `PatcherTests.cs` and `test_class_removal.py`). Still to do: run the sync test on GitHub ([Sync-Test-Procedure.md](Sync-Test-Procedure.md), test 3). The text below is the plan as agreed; where the code differs it is noted.

## The gap

A Python pull request that **adds** a class gets a draft C# pull request with the new file. One that **changes** a class gets the changed members patched. One that
**removes** a class gets nothing: the report says `Removed in Python (delete or deprecate in C# by hand)` and, when the removal is the only change, no pull request is raised at all.
The **C# alignment** check then fails on the Python pull request (`removed in the Python, but the C# still declares it`) until someone removes the class by hand, on a branch
nobody created. The sync test ([Sync-Test-Procedure.md](Sync-Test-Procedure.md), test 3) has to work around it.

## Was there a reason?

Nothing in the design documents gives one. The decision record ([audit-1/Fix-Plan.md](audit-1/Fix-Plan.md), step 3.3) lists "a class removed" as a **breaking change** that gets the
`breaking-change` label and a Versioning_Toolkit reminder, and says "nothing is blocked automatically; the reviewer decides". That describes a draft the reviewer can refuse, not a case left out. The code
shows how the gap came about, and it reads as unfinished scope:

- `plan.py` already records the removed class and its repository, and `Plan.repos()` and `py2cs repos` already count a removal as touching that repository, so the *C# PR* job runs for it.
- `pr.py` then builds its list of files from `plan.json["files"]` only, finds it empty, and prints `skip ... no planned files for this repository`.
- The Roslyn patcher can remove a property, an enum member or a base type from an existing file, but has no change that removes a whole type, and the GitHub client has no operation to delete a file.

Deleting needs no more care than the other drafts: the C# pull request is a draft, a person reviews it, and it has its own checks, including a full build, so a deletion that breaks something else in C# is
caught there, not by this tool. (DataSchema_Toolkit is owned by the person who runs this loop, which settles the question of whether the draft may delete.)

## Goal

When a Python class is removed, the linked C# draft removes the C# class that matches it, and nothing else:

- a removal-only Python pull request raises a draft like any other;
- the **C# alignment** check passes after that draft is merged, with no hand-made branch;
- only the class named by the Python change is touched. Other types in the same file, and every other file, stay as they are.

Not a goal: deprecating a class (it needs a replacement type, a version and a message that the Python change does not carry), editing the Versioning_Toolkit, and checking whether other C# still uses the class (the C# pull request is reviewed and built on its own).

## The rule

For each class removed in Python, found in the base Python and resolved to a repository, `locate` finds the C# file that declares it (as it does for a patch). Then:

| What the file holds | The draft does |
|---|---|
| The class and other types (or other meaningful code) | removes only the declaration of the class, with its attributes, description and comments, and keeps the rest of the file as it is |
| The class and nothing else that is meaningful | removes the class, and, because nothing meaningful is left, **deletes the file** |
| The file cannot be found | nothing; the report says so (the class may already be removed, or lives in another repository) |
| The class is gone from the C# already (an earlier draft was merged) | nothing; the report says `already removed`, as it says `already declares` for an addition |

"Nothing meaningful" means that, once the class is removed, the file has no type declaration, no member and no statement left: only `using` lines, the namespace braces, comments and blank lines (the
copyright header, for example). A file that keeps even one other class, an enum, an interface, a delegate or a stray member is kept. The test is made on the syntax tree, not on the text.

## Design

### 1. Patcher (`PythonSchemaGeneration.Patcher`)

- A new change `removeType` for a file job. It removes the declaration of the named type from its namespace (or the file), together with the attributes, the description and the comments that belong to it,
  through the same `TextEdits` that `removeProperty` uses, so the rest of the file keeps its bytes (line endings, byte order mark, formatting).
- When the namespace is left with no member, the patcher also removes the empty namespace block (or the empty file-scoped namespace line) and the `using` lines no longer needed are **left alone** (an unused `using` is harmless and
  removing it would change lines the Python change did not touch).
- The result tells whether the file is now empty in the sense above: a new field `empty` in the result of the file, next to `text` and `notes`.
- Only the named type is removed. A nested type of the class goes with it; a type of the same name in another namespace in the same file is not touched, and the patcher says so in a note when it finds one.

### 2. Plan (`plan.py`, `patch.py`)

- `build_patch` gets a variant for a removed class (`FilePatch` with one `removeType` change). The base manifest supplies the type, since the head no longer has it.
- `PlannedFile` has a third action, `delete` (alongside `new` and `patch`). When the patcher reports `empty`, the planned file becomes a `delete` with no text; otherwise it is a `patch` with the new text, as today.
- `changes` is `type removed` and `breaking` is `type removed`, so the label, the "Breaking changes" section and the Versioning reminder are produced as they are now.
- `Plan.removed` keeps only the classes that could not be removed in C# (file not found, unknown repository) so the report can still list them.
- Still reads the clones and never writes into them. `Plan.repos()` includes a repository that has only a removal, as it already does.

### 3. Report (`report.py`)

- `### <path> (type removed)` for a patch, `### <path> (file deleted)` for a delete, each with `Type`, `Location` and `Changes in Python: type removed`.
- The line `Removed in Python, but no C# declaration of it was found (it may be removed already; otherwise delete or deprecate it by hand)` stays only for the classes that could not be found.

### 4. GitHub client (`github.py`)

- Add `delete_file(repo, branch, path, message, sha)` to the `GitHubClient` protocol, `RestClient` (`DELETE /repos/{repo}/contents/{path}` with the `sha` of the file on the branch) and `MockGitHub` (removes the file and
  records the call, so tests see it).
- No new permission: the App already has *Contents: write*.

### 5. Raising the pull request (`pr.py`)

- A `patch` entry for a removal needs nothing new: it is written like any other patch.
- A `delete` entry is a file with no content:
  - in the "already in sync" test it is in sync when `get_file(base, path)` is `None`;
  - on the branch, if the file exists the action is `delete file <path>` (and, unless a dry run, `delete_file` with the sha it just read); if it is absent, `unchanged`;
  - the dry-run line reads `would delete file BHoM/DataSchema_Toolkit DataSchema_oM/SyncTestDummy.cs`. The offline dry run (no token) starts from an empty stand-in, so `py2cs pr --dry-run` puts a placeholder for each file to delete on the default branch of the stand-in; without it the preview would say the base is already in step.
- A removal-only plan now has a file, so the branch, the draft, the label and the comment on the Python PR are made as for any other change. A later push to the Python PR updates the same branch.

### 6. Workflow and alignment

- `linked-csharp-pr.yml`: no change expected. The repository list already includes a repository with only a removal, and the clone, `plan` and `pr` steps run per repository.
- `align.py`: no change. It already reports `removed in the Python, but the C# still declares it` and passes once the class is gone.

## Tests

In `.ci/unit-tests/python/test_py2cs` (small fake C# trees and `MockGitHub`; they run without GitHub) and, for the patcher, in the NUnit project next to the existing patcher tests:

| Test | Checks |
|---|---|
| patcher: remove a class that is alone in its file | the result is `empty`, and the text has no declaration |
| patcher: the file also has another class, an enum or an interface | only the named type goes; the rest of the file is byte for byte as before; not `empty` |
| patcher: the class has attributes, a description and comments above it | they go with it |
| patcher: a file with a header comment and `using` lines only after the removal | `empty` is true; a file that keeps a stray member is not empty |
| patcher: line endings and byte order mark | unchanged on a file that is kept |
| patcher: a nested type, and the same name in another namespace | the nested type goes with its class; the other one stays, with a note |
| plan: a removed class alone in its file | one `delete`, the breaking line, the label, and the clone is unchanged |
| plan: a removed class with other types in the file | one `patch` that keeps them |
| plan: the file is not found, or the class is already gone | nothing planned; `already removed` / listed as not found |
| plan: a class removed with a property of another class changed | one `delete` or `patch` and one `patch` in the same repository |
| plan: `--only-repo` | a class of another repository is left out |
| pr: a removal-only plan with a `delete` | branch created, file deleted, draft opened, labelled, comment made |
| pr: dry run | the `would delete file` line and no write calls |
| pr: run twice, and a later push | the second run is `unchanged`; the same PR is updated |
| pr: the base already lacks the file | `already has the planned files, nothing to raise` |
| report: golden text | the deleted-file and the class-removed sections |

The end-to-end test is the sync test itself: [Sync-Test-Procedure.md](Sync-Test-Procedure.md), test 3, with its step 5 (the hand-made deletion) removed.

## Steps

1. Patcher: the `removeType` change and the `empty` result, with its NUnit tests.
2. `github.py`: `delete_file` on the protocol, the REST client and the mock, with tests.
3. `patch.py`, `plan.py` and `report.py`: the removal patch, the `delete` action, the report text, with tests.
4. `pr.py`: raise, update and dry-run for a `delete`, with tests.
5. Local rehearsal: the offline `plan` and `pr --dry-run` for the removal of `SyncTestDummy` against the real clone. They must print `would delete file` (and, for a class in a file with other types, `would write file ... (patch)`).
6. Update the documents: the removal rules in the README ("Changing the Python classes", "Life of a Python change"), [Workflows.md](Workflows.md), and test 3 of the sync procedure.
7. Run the sync test on GitHub, then the whole `run-all.ps1` and a test build, as for any change to this repository.

## Risks

- **The deletion breaks other C#.** Accepted: the C# draft has its own checks, including a full build, and a reviewer. The "Breaking changes" section and the `breaking-change` label stay, as the reminder for a Versioning_Toolkit upgrade.
- **"Nothing meaningful" is judged wrongly.** The syntax-tree test is conservative: any remaining type or member keeps the file. The worst case is an empty-looking file that is kept, which the reviewer deletes in one click.
- **A removal that is really a rename of a class.** A renamed class is a removed class plus an added one, so the draft removes the old class and adds the new one in the same pull request, which is correct for C#.
  Add a test for the pair, and say in the report that it may be a rename.
- **Two classes with the same simple name in different namespaces.** The patcher matches the type in the namespace the Python class names; the other one is left alone, with a note.
