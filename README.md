# BHoM_PythonSchema

Python (Pydantic) classes generated from the BHoM C# object model (oM), the Python counterpart of
[BHoM_JSONSchema](https://github.com/BHoM/BHoM_JSONSchema).

- `src/bhom_schema/`: the generated Python package (`bhom_schema.<Assembly>.<Namespace>.<Type>`).
- `.ci/generation/PythonSchemaGeneration*`: the C# to Python converter (reads the compiled oM assemblies).
- `.ci/generation/py2cs`: the Python to C# converter, used by the linked-PR workflow to draft aligned C#.
- `.ci/unit-tests`: NUnit and pytest tests, plus `run-all.ps1` that runs everything.
- `docs/`: research notes and the coding plan.

## Development setup

Prerequisites: .NET 8 SDK, Python 3.12, a clone of [CSharpSchema_Test](https://github.com/BHoM/CSharpSchema_Test) next to this repository (the C# classes the tests use), and the BHoM assemblies installed in `%ProgramData%\BHoM\Assemblies`
(build the BHoM repos, for example `BHoM`, `BHoM_Engine`, `JSONSchema_Toolkit` and `dKoP_Toolkit`).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.ci\unit-tests\run-all.ps1
```

`run-all.ps1` starts with a preflight that reports missing assemblies. It never builds a repo for you.

## Changing the Python classes

A change to `src/bhom_schema` in a pull request is turned into a draft C# pull request by `py2cs`. It reads the Python
without running it, so it only understands these rules:

- **One class per file**, in `src/bhom_schema/<Assembly>/<namespace folders>/<ClassName>.py`, inside an assembly folder that
  already exists (for example `Structure_oM/Elements/Bar.py` for `BH.oM.Structure.Elements.Bar`).
- **A new class needs no `__bhom__` marker**: its C# name, namespace and repository are worked out from the folder and the
  generated classes next to it, and the PR report says so.
- **Every field has a default** where C# would have one: `Name: str = ""`, `Stage: int = Field(0, description="...")`,
  `Tags: list[str] = Field(default_factory=list)`. A field without a default becomes a C# property without an initial value.
- **Every class and field has a description**: a docstring on the class, `Field(description="...")` on a field.
- **Supported types**: `str`, `int`, `float`, `bool`, `Decimal`, `datetime`, `timedelta`, `UUID`, `Any`, `list[...]`,
  `dict[...]`, `set[...]`, `tuple[...]`, `X | None` (or `Optional[X]`), and other `bhom_schema` classes. Use
  `Annotated[int, ClrType("long")]` when the C# type is not the usual one, and `Quantity("Length", "m")` for physical quantities.
- **Existing C# files are changed member by member**: only the properties that changed in Python are touched.

[docs/templates/NewClass.py](docs/templates/NewClass.py) is a class to copy. Check your change before pushing:

```powershell
$env:PYTHONPATH = ".ci/generation"
.venv\Scripts\python -m py2cs check --root src/bhom_schema
```

## Life of a Python change

The C# is the source of truth. A Python pull request is a **proposal**, and it is linked to a C# pull request in the
repository that owns the class.

1. Open the Python PR. `py2cs` drafts the linked C# PR (a draft, with a report). The Python PR is **never merged before its
   C# PR**.
2. The C# PR is reviewed and merged in its own repository, as usual. Reviewers may change it.
3. Before the Python PR can be merged, the **alignment check** must pass. It generates the Python from the merged C# and
   compares it with the PR. If they differ, change the Python PR to match what was merged. Or close the Python PR and let the
   next weekly generation bring in the same change; both give the same files.
4. If the C# PR is closed without merging, close the Python PR too, with a comment saying why. Otherwise the next weekly
   generation removes the change from the Python again.

```powershell
# After the C# is merged and built (the folder holds the built oM dlls)
.venv\Scripts\python -m py2cs align --base-root <Python before the PR> --head-root src/bhom_schema --assemblies <folder with the oM dlls>
```

It exits with 0 when they match, and lists every difference otherwise (the first value is from the C#, the second from your PR).

**Breaking changes** are listed in their own section of the C# PR, which also gets the `breaking-change` label. They are:
a property removed or renamed, a property whose type changed, an enum member removed or renumbered, a class removed, and a base
class or interface removed. BHoM needs an upgrade in Versioning_Toolkit for these so old files still open. Nothing is blocked
automatically; the reviewer decides.

The weekly generation writes the Python straight from the C# and commits it to `develop`. It is not a pull request, so it never
raises a C# PR.
