"""`py2cs verify`: the check the weekly generation runs on its output before committing it."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from py2cs.__main__ import main
from py2cs.ci import verify_package
from support import OUTPUT, require_output

def test_the_generated_fixtures_pass(capsys: pytest.CaptureFixture[str]):
    package = require_output("fixtures")
    count, problems = verify_package(package, OUTPUT / "fixtures" / "manifest.json")
    assert problems == [] and count > 20

    assert main(["verify", "--package", str(package), "--manifest", str(OUTPUT / "fixtures" / "manifest.json")]) == 0
    assert "0 problems" in capsys.readouterr().out

def test_a_module_that_does_not_import_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    package = tmp_path / "bhom_schema"
    shutil.copytree(require_output("fixtures"), package)
    (package / "FixtureAlpha_oM" / "Broken.py").write_text("from bhom_schema.Nowhere import Missing\n", encoding="utf-8")

    count, problems = verify_package(package)
    assert any(p.startswith("import failed: bhom_schema.FixtureAlpha_oM.Broken: ModuleNotFoundError") for p in problems)

    assert main(["verify", "--package", str(package)]) == 1
    assert "error: import failed" in capsys.readouterr().out

def test_a_package_that_differs_from_the_csharp_manifest_fails(tmp_path: Path):
    package = tmp_path / "bhom_schema"
    shutil.copytree(require_output("fixtures"), package)
    (package / "FixtureAlpha_oM" / "Beam.py").unlink()

    _, problems = verify_package(package, OUTPUT / "fixtures" / "manifest.json")
    assert "BH.oM.FixtureAlpha.Beam: missing" in problems
