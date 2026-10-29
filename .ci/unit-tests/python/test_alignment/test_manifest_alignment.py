"""The structural check: what the C# reflection says must equal what is read back from the generated Python."""

from __future__ import annotations

from pathlib import Path

import pytest

from py2cs.compare import compare_manifests
from py2cs.model import load_manifest
from py2cs.reader import read_package
from support import OUTPUT, require_output


@pytest.mark.parametrize("name", ["fixtures", "spike"])
def test_python_reads_back_exactly_what_csharp_reflection_reported(name: str):
    """Checks that reading the generated Python without running it gives the same manifest the generator wrote from C# reflection, for the fixtures and the spike set.

    Protects the py2cs reader and the generator against drifting apart, which the diff and align stages depend on.
    """
    package = require_output(name)
    expected = load_manifest(OUTPUT / name / "manifest.json")
    actual = read_package(package)
    problems = compare_manifests(expected, actual, allow_extra=False)
    assert problems == [], "\n".join(problems[:30])
    assert len(expected) > 20


def test_every_generated_class_names_a_resolvable_repo():
    """Checks that every generated class resolves to a C# repository, using a small listing for the fixtures and the real repository listing for the spike types.

    Protects the provenance data that py2cs `resolve` uses to pick where a draft pull request goes.
    """
    from py2cs.resolve import load_listing, resolve_repo

    package = require_output("fixtures")
    manifest = read_package(package)
    listing = {"BHoM/CSharpSchema_Test": ["FixtureAlpha_oM", "FixtureBeta_oM"], "BHoM/BHoM": ["BHoM"]}
    for info in manifest.values():
        resolve_repo(info, listing)

    spike = read_package(require_output("spike"))
    real = load_listing(Path(__file__).resolve().parents[2] / "github-fixtures" / "repo-listing.json")
    for info in spike.values():
        assert resolve_repo(info, real).repo.startswith("BHoM/"), info.clr_name
