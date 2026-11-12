# Further tests for the sync between BHoM_PythonSchema and DataSchema_Toolkit

Tests worth running after the main sequence in [Sync-Test-Procedure.md](Sync-Test-Procedure.md). Each one uses the same cleanup rule: use a field or a class that the test creates
(`SyncTestField` on `Grid`, `SyncTestDummy`), and undo it. The "Local" column says whether the result was already seen with the offline rehearsal (`py2cs plan` against a copy of
the real DataSchema_Toolkit, no GitHub); everything else is a suggestion for what to look for.

| # | Test | Local |
|---|---|---|
| A | The other direction: a change in C# comes back into Python | no |
| B | A rename is a remove plus an add | seen |
| C | Description-only and default-only changes | seen |
| D | A change and its revert in one pull request | seen |
| E | Field types beyond `str` and `int` | seen |
| F | Quantities, display text and `long` | seen |
| G | A class that refers to another class, and an inheritance change | no |
| H | An enum: add a member, remove one | no |
| I | Two classes, and two repositories, in one pull request | no |
| J | Pushing again, closing unmerged, and a fork | no |
| K | Mistakes that must be refused | partly |
| L | A reviewer changes the C# draft | no |
| M | The generation or an alpha release runs while a pull request is open | no |
| N | What a Python user gets after the sync | no |
| O | The formatting of the patched C# file | seen for an added property |

## A. The other direction: C# to Python

The C# is the source of truth, and the weekly generation brings every C# change into `src/bhom_schema`. Prove it for a C# change that nobody drafted:

1. In DataSchema_Toolkit, a branch that adds `public virtual string SyncTestFromCSharp { get; set; } = "";` to `Grid.cs` (with a `Description`). Merge it into `develop`.
2. Run *Python schema generation* with `dry_run` ticked. Expect the report to show `Grid` changed, and no failed types.
3. Run it live. Expect one commit to `develop` that adds one line to `Grid.py`: `SyncTestFromCSharp: str = Field(default='', description='...')`. No other file changes.
4. Undo it: remove the property in C#, merge, run the generation live again, and check the line is gone from `Grid.py`.

Compare the line the generator wrote with what `py2cs` would have drafted from it. They must agree (that is what the alignment check proves for a pull request).

## B. A rename is a remove plus an add

Rename a field in Python (for example `SyncTestField` to `SyncTestRenamed`). Python cannot tell a rename from a removal and an addition, and neither can the draft: it adds the new property, removes the old
one, and lists one breaking change `property renamed: <old> to <new>`. Seen locally with `TypicalYSpacing` to `BayY`. Check that the label is `breaking-change` and that anything in the Python
that referred to the old name (a JSON file, a table column in the notebooks) breaks in the way the notes say. Rename it back to undo.

## C. Description-only and default-only changes

- Change only the description of a class or a field. Expect `description changed`, no breaking label, and one `Description(...)` line changed in the draft (seen).
- Change only a default (`default=None` to `default=8.0`). Expect `property <name> default changed from None to 8.0`, no breaking label (seen).

These are the cheapest changes, and the ones most likely to be made by people. Undo them by changing the text or the value back.

## D. A change and its revert in one pull request

Add `SyncTestField`, push, then push a commit that removes it again, in the same pull request. The diff of the pull request against `develop` is empty for the Python, so the plan has nothing: `0 files planned`
and `pr` prints `would skip ... no planned files for this repository` (seen). On GitHub, check what happens to a draft that was already raised by the first push: it should be updated to nothing or closed,
and not left with the first version. Write down which.

## E. Field types beyond `str` and `int`

One field at a time on `Grid`, adding it, checking the draft, then removing it. For each, compare the C# type with the table in [CSharp-to-Python-Gotchas.md](CSharp-to-Python-Gotchas.md).

| Python | C# in the draft (seen locally) |
|---|---|
| `bool` | `bool`, `= false` |
| `float \| None` | `double?` |
| `Decimal` | `decimal`, `= 0m` |
| `datetime \| None`, `timedelta \| None`, `UUID \| None` | `DateTime?`, `TimeSpan?`, `Guid?` |
| `list[str]` with `default_factory=list` | `List<string>`, `= new List<string>()` |
| `dict[str, float]` | `Dictionary<string, double>`, `= new Dictionary<string, double>()` |
| `set[str]` | `HashSet<string>`, `= new HashSet<string>()` |
| `tuple[int, str] \| None` | `Tuple<int, string>` |
| `Any` | `object` |

The offline rehearsal (adding all of these to `Grid` in a scratch copy) planned one file and `check` reported 0 errors. The real test is the same, one pull request, followed by the build of the draft
(a type the C# project cannot compile, such as a missing `using`, only shows up there).

After the merge and the removal, run the type-validation notebook against the new package, and `describe` on the class in the Databricks notebook: a new field type is also a new column type.

## F. Quantities, display text and `long`

- `Annotated[float, Quantity('Length', 'm')]` gives `[Length]` on the C# property (seen: `[Length]` above the property; check that it **disappears** again when the `Quantity` is removed, which the plan lists as `attributes changed`).
- `Annotated[float | None, DisplayText('A label')]` gives `[DisplayText("A label")]` (seen).
- `Annotated[int, ClrType('long')]` gives `long` (seen). Then change it to `ClrType('short')`: that is a type change, so it must be labelled breaking.

## G. A class that refers to another class, and inheritance

- Add `SyncTestRef: Grid | None = Field(default=None, description='...')` to `SyncTestDummy` (add the dummy first, as in test 1). The draft refers to `Grid` and does not touch `Grid.cs`.
- Change the base class of `SyncTestDummy` from `BHoMObject` to `SchemaModel` and back. A base class removed or changed is a breaking change; the draft changes only the declaration line.
- A class in a sub-namespace: put the dummy in a new folder `src/bhom_schema/DataSchema_oM/SyncTest/`. Expect the file in `DataSchema_oM/SyncTest/` and namespace `BH.oM.DataSchema.SyncTest`.
- A class in an assembly folder that does not exist (`NoSuch_oM/Thing.py`) must be refused by `check`.

## H. An enum

Add a dummy enum in `DataSchema_oM` (one enum per file), with three members, then add a fourth and remove one. Expect: a new enum file; a member added is not breaking; a member removed or renumbered is
breaking and is labelled. After the merge, use the enum as the type of a field of the dummy class, and in the Databricks notebook watch `enum_constraints_sql` list the new members for it.

## I. Two classes, and two repositories, in one pull request

- Change `SyncTestField` on `Grid` and add `SyncTestDummy` in one pull request: one draft with two files, and the plan lists both.
- Change a class of `FixtureAlpha_oM` too (the repository `BHoM/CSharpSchema_Test`). Expect **two** drafts, one in each repository, two links in the comment on the Python PR, and a token made for the two
  repositories only.

## J. Pushing again, closing unmerged, and a fork

- Push three commits to one Python PR: the branch `python-schema/pr-<N>` is force-updated, there is still one draft and one comment.
- Close a Python PR without merging: the draft is closed with a comment; the branch stays until you delete it. Re-open the Python PR: the draft must come back or be updated.
- Open a Python PR from a fork: no draft, the job says that forks get none.
- Check whether the **C# alignment** job is a required check on `develop`. If it is not, a Python PR can be merged before its C# draft; that is a gap to note, not something to try on the real repositories.

## K. Mistakes that must be refused

Each of these should fail `py2cs check` with a message that names the file and the line, before any draft is made. Run them locally with `py2cs check` on a scratch copy; none of these has been tried against the real DataSchema_oM yet.

- a class or field without a description;
- two classes in one file;
- a `__bhom__` marker whose `repo` is not in `Converted-repositories.txt`;
- a type `py2cs` does not understand (a `Callable`, a class from outside `bhom_schema`);
- a field without a default (allowed, but the C# property must then have no initial value: check the draft);
- a field named like a C# keyword (`class`, `object`, `string`).

## L. A reviewer changes the draft

The C# is the source of truth. In the C# draft of a field addition, change the property type by hand (for example `string` to `int`) and merge that. The Python PR's **C# alignment** must go red and
list the difference (the first value is from the C#, the second from the PR). Copy the C# change into the Python PR and check that the alignment turns green. This is the situation the alignment
check exists for.

## M. The generation or an alpha while a pull request is open

- While a Python PR is open, merge an unrelated C# change in DataSchema_Toolkit and run the generation. The Python PR now sits on an older `develop`: update the branch, and check that the plan is
  recomputed against the new C# and the draft is updated.
- Run the generation after the C# draft is merged but **before** the Python PR is merged: the generation writes the change into `develop`, and the Python PR becomes empty or conflicts. Close it, as
  the README says: both ways give the same files.
- Let one daily alpha run while `SyncTestDummy` is on `develop`, and install it (`pip install --pre bhom-schema`): the class is importable. After the removal and the next alpha, it is not.

## N. What a Python user gets after the sync

After each of the three tests of the main procedure, install the alpha built after the merge in a clean environment and check the change as the user sees it:

- the new field is in `Grid.model_fields`, has its description, and `Grid(SyncTestField="x")` works; `Grid(SyncTestField=3)` is refused when the type is `str`;
- JSON written by the new version and read by the old one (and the other way round): an unknown field must not break `model_validate_json`; a missing field takes its default;
- the table helpers: `describe(Grid)` shows the new column, `create_table_sql` includes it, and an existing table gets it from `add_columns_sql`;
- the `Databricks-DataSchema-Demo` and `Type-Validation-Showcase` notebooks still run end to end.

## O. The formatting of the patched C# file

The draft of an existing file must change only the lines of the property that changed. Check this for the C# files of DataSchema_Toolkit: the line endings (CRLF or LF) and the byte order mark
are kept, the indentation of the new lines matches the neighbours, and the order of the properties follows the Python. The added property of test 1 was seen to change exactly three lines.
Repeat it on a file with section comments (`/**** Properties ****/`) and on one without.
