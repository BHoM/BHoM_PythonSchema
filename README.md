# BHoM_PythonSchema

Python (Pydantic) classes generated from the BHoM C# object model (oM), the Python counterpart of
[BHoM_JSONSchema](https://github.com/BHoM/BHoM_JSONSchema).

- `src/bhom_schema/`: the generated Python package (`bhom_schema.<Assembly>.<Namespace>.<Type>`).
- `.ci/generation/PythonSchemaGeneration*`: the C# to Python converter (reads the compiled oM assemblies).
- `.ci/generation/py2cs`: the Python to C# converter, used by the linked-PR workflow to draft aligned C#.
- `.ci/unit-tests`: NUnit and pytest tests, plus `run-all.ps1` that runs everything.
- `docs/`: research notes and the coding plan.

## Development setup

Prerequisites: .NET 8 SDK, Python 3.12, and the BHoM assemblies installed in `%ProgramData%\BHoM\Assemblies`
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
