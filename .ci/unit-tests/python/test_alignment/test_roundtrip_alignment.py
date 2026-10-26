"""Python to C# round trip: the draft C# (compiled and reflected by the NUnit RoundTrip tests) must match the original types."""

from __future__ import annotations

import pytest

from py2cs.compare import compare_manifests
from py2cs.model import load_manifest
from support import OUTPUT, require_output

# The drafts are one assembly with a different name, so only the shape of each type is compared
IGNORED = frozenset({"assembly", "repo", "path"})


@pytest.mark.parametrize("name", ["fixtures", "spike"])
def test_drafted_csharp_reflects_back_to_the_original_types(name: str):
    require_output(name)
    draft = OUTPUT / "roundtrip" / name / "draft-manifest.json"
    if not draft.exists():
        pytest.skip(f"{draft} not found: run the RoundTrip NUnit tests first")
    original = load_manifest(OUTPUT / name / "manifest.json")
    problems = compare_manifests(original, load_manifest(draft), allow_extra=False, ignore=IGNORED)
    assert problems == [], "\n".join(problems[:40])
