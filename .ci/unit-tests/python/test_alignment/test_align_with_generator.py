"""The alignment check end to end: the real generator runs over the built fixture assemblies, as it will over the merged C#."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from py2cs.__main__ import main
from py2cs.align import BUILD_HINT, default_generator
from support import REPO, require_output

BEAM = "FixtureAlpha_oM/Beam.py"
TEST_BUILD = REPO / ".ci" / "unit-tests" / "csharp" / "PythonSchemaGeneration.Tests" / "bin" / "Release" / "net8.0"

@pytest.fixture
def assemblies(tmp_path: Path) -> Path:
    """Fixture that copies the fixture oM assemblies and `BHoM.dll` from the test build into a temporary folder and returns it, or fails in CI and skips locally if the generator or build is missing.

    The `py2cs align` tests pass it as `--assemblies`, like the folder of a build of the merged C#.
    """
    sources = [TEST_BUILD / name for name in ("FixtureAlpha_oM.dll", "FixtureBeta_oM.dll", "BHoM.dll")]
    if not default_generator().exists() or not all(s.exists() for s in sources):
        message = f"the generator or the test build is missing; {BUILD_HINT}"
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail(message)
        pytest.skip(message)

    folder = tmp_path / "dlls"
    folder.mkdir()
    for source in sources:
        shutil.copy(source, folder)
    return folder

def copy_fixtures(destination: Path) -> Path:
    """Copies the generated fixtures package into a `bhom_schema` folder under the given folder and returns it.

    Builds the base and head package roots that the `py2cs align` tests compare.
    """
    shutil.copytree(require_output("fixtures"), destination / "bhom_schema")
    return destination / "bhom_schema"

def edit(package: Path, old: str, new: str) -> None:
    """Replaces a text in the generated `Beam.py` of a package, asserting that the text exists, and writes the file back.

    Lets the align tests make a Python PR that differs from the C#.
    """
    path = package / BEAM
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")

def test_a_pr_that_matches_the_csharp_passes(tmp_path: Path, assemblies: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that `py2cs align` exits 0 and reports no differences when the PR adds a property exactly as the generator writes it from the C#.

    Protects the pull request check that lets a correct Python change through.
    """
    base = copy_fixtures(tmp_path / "base")
    text = (base / BEAM).read_text(encoding="utf-8")
    (base / BEAM).write_text("".join(line for line in text.splitlines(keepends=True) if not line.startswith("    Small:")), encoding="utf-8", newline="\n")
    head = copy_fixtures(tmp_path / "head")

    status = main(["align", "--base-root", str(base), "--head-root", str(head), "--assemblies", str(assemblies)])
    assert status == 0, capsys.readouterr().out
    assert "1 classes compared, 0 differences" in capsys.readouterr().out

def test_a_pr_that_differs_from_the_csharp_lists_the_difference(tmp_path: Path, assemblies: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that `py2cs align` exits 1 and names the property and default value that differ when the PR changes a default from the C#.

    Protects the pull request check that stops Python that diverges from the merged C#.
    """
    base = copy_fixtures(tmp_path / "base")
    head = copy_fixtures(tmp_path / "head")
    edit(head, "Count: Annotated[int, ClrType('long')] = 3", "Count: Annotated[int, ClrType('long')] = 4")

    status = main(["align", "--base-root", str(base), "--head-root", str(head), "--assemblies", str(assemblies)])
    assert status == 1
    assert "difference: BH.oM.FixtureAlpha.Beam.Count: default differs: '3' != '4'" in capsys.readouterr().out

def test_a_class_the_csharp_does_not_have_fails(tmp_path: Path, assemblies: Path, capsys: pytest.CaptureFixture[str]):
    """Checks that `py2cs align` exits 1 and reports a class missing from the C# when the PR adds a class the C# does not have.

    Protects the pull request check that stops Python classes whose C# was not merged.
    """
    base = copy_fixtures(tmp_path / "base")
    head = copy_fixtures(tmp_path / "head")
    (head / "FixtureAlpha_oM" / "Proposed.py").write_text(
        (head / "FixtureAlpha_oM" / "Beam.py").read_text(encoding="utf-8").replace("class Beam(", "class Proposed(").replace("BH.oM.FixtureAlpha.Beam", "BH.oM.FixtureAlpha.Proposed"),
        encoding="utf-8", newline="\n")

    status = main(["align", "--base-root", str(base), "--head-root", str(head), "--assemblies", str(assemblies)])
    assert status == 1
    assert "BH.oM.FixtureAlpha.Proposed: not found in the C#" in capsys.readouterr().out
