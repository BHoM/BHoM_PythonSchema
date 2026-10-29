"""The alignment check: does the Python of a PR equal the Python the generator writes from the merged C#?

The C# is the source of truth. A Python PR is only a proposal until the C# has the same change, so the check asks the generator
what the C# says about the changed classes and compares that with the PR.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from py2cs.compare import compare_types
from py2cs.diff import diff_manifests
from py2cs.model import Manifest

GENERATOR = Path(__file__).resolve().parents[1] / "PythonSchemaGeneration" / "bin" / "Release" / "net8.0" / "PythonSchemaGeneration.dll"
BUILD_HINT = "build it with: dotnet build .ci/generation/PythonSchemaGeneration.sln -c Release"

class AlignError(Exception):
    """The check could not be run (as opposed to running and finding differences)."""

@dataclass
class AlignResult:
    # The types that were compared
    checked: list[str] = field(default_factory=lambda: [])
    # One line per difference. In a "differs" line the first value comes from the C#, the second from the Python PR.
    problems: list[str] = field(default_factory=lambda: [])

    @property
    def ok(self) -> bool:
        """Tells whether the alignment check found no difference. The `align` command returns exit code 0 when it is true."""
        return not self.problems

def changed_types(base: Manifest, head: Manifest) -> tuple[list[str], list[str]]:
    """(added or modified, removed) class names between the two versions of the Python."""
    diff = diff_manifests(base, head)
    return [c.clr_name for c in diff.changes if c.kind != "removed"], [c.clr_name for c in diff.changes if c.kind == "removed"]

def align(base: Manifest, head: Manifest, generated: Manifest) -> AlignResult:
    """Compares the changed classes of a PR with the classes generated from the merged C#."""
    result = AlignResult()
    changed, removed = changed_types(base, head)
    for name in changed:
        result.checked.append(name)
        csharp = generated.get(name)
        if csharp is None:
            result.problems.append(f"{name}: not found in the C#; merge and build the linked C# pull request first")
            continue
        result.problems += compare_types(csharp, head[name])

    for name in removed:
        result.checked.append(name)
        if name in generated:
            result.problems.append(f"{name}: removed in the Python, but the C# still declares it")
    return result

def default_generator() -> Path:
    """Returns the path of the built C# generator dll that `generate` runs when no other path is given."""
    return GENERATOR

def generate(types: list[str], assemblies: Path, output: Path, generator: Path | None = None) -> None:
    """Runs the C# to Python generator for just these classes (and what they refer to) over a folder of built assemblies."""
    dll = generator or default_generator()
    if not dll.exists():
        raise AlignError(f"the generator was not found at {dll}; {BUILD_HINT}")
    if not assemblies.is_dir():
        raise AlignError(f"{assemblies} is not a folder; pass the folder with the built oM dlls of the merged C#")

    output.mkdir(parents=True, exist_ok=True)
    command = ["dotnet", str(dll), "--output", str(output), "--assemblies", str(assemblies), "--types", ",".join(types)]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=600)
    if completed.returncode != 0:
        raise AlignError(f"the generator failed: {(completed.stderr or completed.stdout).strip()}")
