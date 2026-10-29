# Python packages: a primer for reading `py2cs`

This is for someone who knows C# well and has not built a Python package before. It explains only what you need to read
[`.ci/generation/py2cs`](../.ci/generation/py2cs), with C# comparisons where they help.

## 1. The vocabulary

| Python term | What it is | Closest C# idea |
|---|---|---|
| **module** | One `.py` file. Its name is the file name without `.py`. | A `.cs` file (but the file *is* the namespace member, there is no `namespace` keyword) |
| **package** | A folder of modules that contains a file called `__init__.py`. | A namespace backed by a folder, or a small assembly |
| **import** | Loads a module and gives you names from it. | `using` plus a project reference |
| **`sys.path`** | The list of folders Python searches when you `import` something. | The assembly search path |
| **virtual environment** (`.venv`) | A private copy of Python plus the libraries this project needs. | A per-project `packages` folder |
| **`pyproject.toml`** | Project settings: name, dependencies, tool configuration. | A `.csproj` |

There is no compile step. Python reads the `.py` files directly when you run them.

## 2. What makes `py2cs` a package

```
.ci/generation/
  py2cs/
    __init__.py      <- its presence makes the folder a package
    __main__.py      <- lets you run the package: python -m py2cs
    model.py
    reader.py
    ...
```

- **`__init__.py`** runs when the package is first imported. In `py2cs` it only holds a one-line description, so it does nothing.
  (A package can put code there to choose what `import py2cs` exposes; this one does not.)
- **`__main__.py`** is what runs for `python -m py2cs <command>`. The `-m` flag means "run this package as a program".
  The bottom of the file has the usual guard:

  ```python
  if __name__ == "__main__":
      sys.exit(main())
  ```

  `__name__` is `"__main__"` only when the file is run as a program, not when something imports it. This keeps the
  command-line code from running during tests. `sys.exit(main())` makes the number returned by `main()` the process exit code,
  like `return 1;` from a C# `Main`.

## 3. How Python finds `py2cs` (the part that confuses most people)

`py2cs` is **not installed**. It has no `pyproject.toml` of its own, so `pip` does not know about it. Python can import it only
if the folder that *contains* `py2cs/`, which is `.ci/generation`, is on `sys.path`. This repository arranges that in two places:

- **pytest:** `pyproject.toml` has `pythonpath = ["src", ".ci/generation", ".ci/unit-tests/python"]`, so tests can write
  `from py2cs.reader import read_package`.
- **Command line:** `run-all.ps1` sets the environment variable `PYTHONPATH` to `.ci/generation`. If you run it by hand you
  must do the same, or run it from inside `.ci/generation`:

  ```powershell
  $env:PYTHONPATH = ".ci/generation"
  .venv\Scripts\python -m py2cs --help
  ```

If you ever see `ModuleNotFoundError: No module named 'py2cs'`, the folder is not on `sys.path`.

There are two different packages in this repository. Do not mix them up:

| Package | Where | Purpose | Installed? |
|---|---|---|---|
| `bhom_schema` | `src/bhom_schema` | The **output**: generated Pydantic classes for the C# oM. | Yes, `pip install -e .` from the root `pyproject.toml` |
| `py2cs` | `.ci/generation/py2cs` | A **tool**: reads `bhom_schema` and writes C#. | No, only put on the path |

## 4. Imports as used in `py2cs`

```python
import ast
from pathlib import Path
from py2cs.model import Manifest, TypeInfo
```

- `import ast` loads the whole module; you then write `ast.parse(...)`.
- `from pathlib import Path` takes one name out of a module.
- `from py2cs.model import TypeInfo` means: package `py2cs`, module `model` (the file `model.py`), name `TypeInfo`.
  All imports inside `py2cs` are written this way, starting from the package name (called *absolute* imports).
- Standard library modules (`ast`, `json`, `re`, `argparse`, `pathlib`) ship with Python and need no installation.

Python runs a module's code top to bottom the first time it is imported. Two modules that import each other can therefore fail.
`py2cs` avoids that: the dependencies only point one way (see section 7).

## 5. Python features you will meet on almost every page

**Type hints.** They are written after a colon and `->`, and look like C# types:

```python
def locate(repo_root: Path, info: TypeInfo) -> Located:
```

They are not enforced when the program runs. They are checked by **Pyright** (the project runs it in strict mode) and they help the
editor. `list[str]` is `List<string>`, `dict[str, int]` is `Dictionary<string, int>`, `str | None` is a nullable `string`, and
`Callable[[Path], Path | None]` is a `Func<Path, Path?>`.

**`from __future__ import annotations`.** The line at the top of most files. It makes type hints be read as text and resolved
later, so a class can mention a type defined further down the file.

**Dataclasses** (`@dataclass`). A decorator, which is a function that wraps the class below it, so a `@dataclass` class gets a
constructor, equality and a readable `repr` for free from its field list. This is how `model.py` defines `TypeInfo`, `PropertyInfo`
and the rest. They behave like C# `record`s:

```python
@dataclass
class PropertyInfo:
    name: str
    clr_type: str
    description: str | None = None
```

A field with a default must come after fields without one. A list default must not be written as `[]` (every instance would share
one list), so the code uses `field(default_factory=lambda: [])`, which means "make a fresh list for each instance".

**Comprehensions** are one-line loops that build collections:

```python
names = [p.name for p in info.properties if p.has_default]
by_name = {p.name: p for p in info.properties}
```

The first is `info.properties.Where(p => p.HasDefault).Select(p => p.Name).ToList()`; the second is `ToDictionary`.

**f-strings** are interpolated strings: `f"{clr_name}: missing"` is `$"{clrName}: missing"`.

**Indentation is syntax.** Blocks are defined by indentation, not braces, and `if`, `for`, `def` and `class` lines end with a colon.

**Names.** Functions and variables are `snake_case`, classes are `PascalCase`. A leading underscore (`_name`) means "internal, do
not use from outside" by convention only; nothing enforces it. `self` is the explicit first parameter of a method, like `this`,
but you must write it.

**Exceptions** use `raise` and `try ... except`, like `throw` and `try ... catch`. `ResolveError` in `resolve.py` is a custom one.

**Paths.** `pathlib.Path` objects replace string handling: `root / "Demo_oM" / "Line.cs"` joins paths, `path.read_text()` reads a
file, `path.stem` is the name without extension, `path.rglob("*.cs")` searches recursively.

## 6. The standard-library parts that matter here

- **`ast`**: parses Python source into a tree of node objects without running it. `reader.py` uses it to read the generated
  classes. Useful nodes: `ClassDef` (a class), `AnnAssign` (`Name: str = ''`, a field), `Subscript` (`list[str]`), `BinOp` with a
  `BitOr` operator (`str | None`), `Call` (`Field(...)`), `Constant` (a literal). `ast.literal_eval` turns a literal's source text into
  a value, and `ast.unparse` turns a node back into source text.
- **`argparse`**: builds the command line (`python -m py2cs plan --base-root ...`). `__main__.py` defines one sub-command per
  action: `manifest`, `diff`, `plan`, `drafts`, `resolve`.
- **`json`**: reads and writes the manifest files.
- **`re`**: regular expressions, used in `locate.py` to find `class Name` declarations in C# files.

## 7. A map of the package

Read the files in this order. Each one only imports files above it in the table, so you can understand them one at a time.

| Order | File | What it does | Ideas it uses |
|---|---|---|---|
| 1 | `model.py` | The data shapes: `TypeInfo`, `PropertyInfo`, `MemberInfo`, and reading and writing the manifest JSON. The same shape the C# generator writes. | dataclasses, `json` |
| 2 | `reader.py` | Turns the generated Python files into `TypeInfo` objects by parsing them with `ast`. The `Converter` class turns an annotation such as `list[str] \| None` back into a C# type name such as `System.Collections.Generic.List<string>`. | `ast`, classes, recursion |
| 3 | `compare.py` | Compares two manifests and returns a list of differences (used by tests). | functions, sets |
| 4 | `diff.py` | Compares the manifest at the PR base with the one at the PR head: added, removed and changed types. | dataclasses |
| 5 | `resolve.py` | Decides which GitHub repository owns a class, from the repo recorded in the class or a repository listing. | exceptions |
| 6 | `locate.py` | Finds an existing `.cs` file by searching for the declaration, and chooses a place for a new one. | `pathlib`, `re` |
| 7 | `csharp.py` | The C# writer: type names, default values, properties, constructors, whole files and replacement files. The largest file. | string building, `ast` |
| 8 | `plan.py` | Combines the pieces: for each change, which repo, which file, new or replacement, and the C# text. | dataclasses, callables |
| 9 | `report.py` | Writes the Markdown that goes into the C# pull request. | string building |
| 10 | `__main__.py` | The command line that calls everything above. | `argparse` |

The data flow is:

```
bhom_schema/*.py --reader--> manifest --diff--> changes --plan--> C# files + report
                                                  ^
                          resolve (repo) + locate (file) + csharp (text)
```

Nothing writes into a C# checkout: `plan.py` only reads the clones and returns text, and `__main__.py` writes the results into a
separate output folder.

## 8. Running and checking it

All commands are from the repository root, with the virtual environment's Python:

```powershell
.venv\Scripts\python -m pytest .ci/unit-tests/python/test_py2cs -q
```

runs the `py2cs` tests (about 37 of them). To see one command work:

```powershell
$env:PYTHONPATH = ".ci/generation"
.venv\Scripts\python -m py2cs manifest --root .ci/unit-tests/_output/spike/bhom_schema --out spike-manifest.json
```

(the spike folder exists after `dotnet test` has run; see `run-all.ps1`).

```powershell
.venv\Scripts\python -m pyright
```

type-checks the package in strict mode.

Useful habits for reading unfamiliar Python:

- Run `python -i` or add a `print(...)` and look at real values. Python has no compile step, so experiments are cheap.
- `dir(obj)` lists what an object offers, and `help(obj)` shows its documentation.
- The tests in `.ci/unit-tests/python/test_py2cs` double as examples: each one builds a tiny package, calls a function and checks
  the result, which is often the quickest way to see what a function expects.

## 9. Things that look odd but are normal

- `__pycache__` folders appear next to the `.py` files. They hold cached compiled bytecode and are git-ignored.
- `# pyright: ignore[...]` or `# type: ignore` comments tell the type checker to skip a line.
- Files start with a triple-quoted string. That is a **docstring**, Python's equivalent of a `[Description]` or XML comment, read by
  tools such as `help()`.
- There is no `public`, `private` or `static` keyword. Everything is public, and top-level functions are used where C# would
  use a static class.
- `*` and `**` in calls spread a list or dictionary into arguments, like `params`.
- Python modules are objects. You can pass a function around like a delegate, which is how `plan.py` receives the function that finds
  a clone folder.
