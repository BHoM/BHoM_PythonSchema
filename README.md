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
