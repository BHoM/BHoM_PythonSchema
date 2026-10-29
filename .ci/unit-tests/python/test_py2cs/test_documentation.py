"""Every function in the repository's own Python code says what it does."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FOLDERS = [REPO / ".ci", REPO / "src"]
SKIPPED = {"_output", ".venv", "__pycache__", "bin", "obj", ".vs", "TestResults", "golden"}

def python_files() -> list[Path]:
    """Finds the Python files of the repository that are written by hand or by the converters' own tools."""
    found: list[Path] = []
    for folder in FOLDERS:
        found += [p for p in folder.rglob("*.py") if not SKIPPED & set(p.relative_to(REPO).parts)]
    return sorted(found)

def undocumented(path: Path) -> list[str]:
    """Lists the functions of one file that have no docstring, as 'file:line name'."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [f"{path.relative_to(REPO).as_posix()}:{node.lineno} {node.name}" for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node, clean=False) is None]

def test_every_function_has_a_docstring():
    """Fails with the list of functions that have no docstring, so a new function cannot be added without saying what it does."""
    missing = [entry for path in python_files() for entry in undocumented(path)]
    assert missing == [], f"{len(missing)} functions have no docstring:\n" + "\n".join(missing[:60])

def test_the_search_covers_the_converters_and_their_tests():
    """Guards the check above against silently looking at nothing, for example after a folder is renamed."""
    names = {p.name for p in python_files()}
    assert {"reader.py", "pr.py", "github.py", "test_linked_pr.py", "support.py"} <= names
