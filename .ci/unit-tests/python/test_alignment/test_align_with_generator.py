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
# The fixtures belong to the CSharpSchema_Test repository; BHoM is needed for the base classes
ORGS = "BHoM,BuroHappoldEngineering"
TEST_BUILD = REPO / ".ci" / "unit-tests" / "csharp" / "PythonSchemaGeneration.Tests" / "bin" / "Release" / "net8.0"

@pytest.fixture
def assemblies(tmp_path: Path) -> Path:
    """A folder with just the fixture oM assemblies and BHoM.dll, like the folder of a build of the merged C#."""
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
    shutil.copytree(require_output("fixtures"), destination / "bhom_schema")
    return destination / "bhom_schema"

def edit(package: Path, old: str, new: str) -> None:
    path = package / BEAM
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")

def test_a_pr_that_matches_the_csharp_passes(tmp_path: Path, assemblies: Path, capsys: pytest.CaptureFixture[str]):
    """The base lacks the Small property that the C# already has; the PR adds it exactly as the C# says."""
    base = copy_fixtures(tmp_path / "base")
    text = (base / BEAM).read_text(encoding="utf-8")
    (base / BEAM).write_text("".join(line for line in text.splitlines(keepends=True) if not line.startswith("    Small:")), encoding="utf-8", newline="\n")
    head = copy_fixtures(tmp_path / "head")

    status = main(["align", "--base-root", str(base), "--head-root", str(head), "--assemblies", str(assemblies), "--org", ORGS])
    assert status == 0, capsys.readouterr().out
    assert "1 classes compared, 0 differences" in capsys.readouterr().out

def test_a_pr_that_differs_from_the_csharp_lists_the_difference(tmp_path: Path, assemblies: Path, capsys: pytest.CaptureFixture[str]):
    base = copy_fixtures(tmp_path / "base")
    head = copy_fixtures(tmp_path / "head")
    edit(head, "Count: Annotated[int, ClrType('long')] = 3", "Count: Annotated[int, ClrType('long')] = 4")

    status = main(["align", "--base-root", str(base), "--head-root", str(head), "--assemblies", str(assemblies), "--org", ORGS])
    assert status == 1
    assert "difference: BH.oM.FixtureAlpha.Beam.Count: default differs: '3' != '4'" in capsys.readouterr().out

def test_a_class_the_csharp_does_not_have_fails(tmp_path: Path, assemblies: Path, capsys: pytest.CaptureFixture[str]):
    base = copy_fixtures(tmp_path / "base")
    head = copy_fixtures(tmp_path / "head")
    (head / "FixtureAlpha_oM" / "Proposed.py").write_text(
        (head / "FixtureAlpha_oM" / "Beam.py").read_text(encoding="utf-8").replace("class Beam(", "class Proposed(").replace("BH.oM.FixtureAlpha.Beam", "BH.oM.FixtureAlpha.Proposed"),
        encoding="utf-8", newline="\n")

    status = main(["align", "--base-root", str(base), "--head-root", str(head), "--assemblies", str(assemblies), "--org", ORGS])
    assert status == 1
    assert "BH.oM.FixtureAlpha.Proposed: not found in the C#" in capsys.readouterr().out
