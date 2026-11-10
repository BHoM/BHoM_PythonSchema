"""Dictionaries keyed by an enum, for the generated fixture class SupportTotals.

What the real BHoM serialiser does (Serialiser_Engine, run on a SupportTotals with `Fixed` and `None` keys):

- It writes a dictionary with a key that is not a string as an array of `{"k": <key>, "v": <value>}`, with the member name as the key; BHoM_JSONSchema describes the same form.
- It reads that form, and also reads the plain object form `{"Fixed": 2.5}` that the Python side writes.
- It does not flag a key that is not a member: the key silently becomes the member with value 0.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from pydantic import ValidationError

# Written by the BHoM serialiser for ByKind {Fixed: 2.5, None: 1} and ByOptions {A: 3, Both: 5}
CSHARP_JSON = (
    '{ "_t" : "BH.oM.FixtureAlpha.SupportTotals", "ByKind" : [{ "k" : "Fixed", "v" : 2.5 }, { "k" : "None", "v" : 1.0 }], '
    '"ByOptions" : [{ "k" : "A", "v" : 3 }, { "k" : "Both", "v" : 5 }], "BHoM_Guid" : "b131870a-7a86-4a8f-9251-bc69b29d9fa6", "Name" : "", "_bhomVersion" : "9.3" }')

def cls(name: str) -> Any:
    """Returns a generated fixture class by name, imported from `bhom_schema.FixtureAlpha_oM`; the package is attached by the fixture suite's session fixture."""
    return getattr(importlib.import_module(f"bhom_schema.FixtureAlpha_oM.{name}"), name)

def test_the_generated_class_types_the_keys_as_the_enum():
    """Checks that the generator emits `dict[Enum, value]` for a dictionary keyed by an enum, plain and flags."""
    SupportTotals = cls("SupportTotals")

    assert str(SupportTotals.model_fields["ByKind"].annotation) == "dict[bhom_schema.FixtureAlpha_oM.SupportKind.SupportKind, float]"
    assert str(SupportTotals.model_fields["ByOptions"].annotation) == "dict[bhom_schema.FixtureAlpha_oM.Options.Options, int]"

def test_python_writes_member_names_and_reads_them_back():
    """Checks that the keys are written as the C# member names (`None`, not `None_`) and that what is written is read back to an equal object."""
    SupportTotals, SupportKind = cls("SupportTotals"), cls("SupportKind")
    totals = SupportTotals(ByKind={SupportKind.Fixed: 2.5, SupportKind.None_: 1.0})

    written = json.loads(totals.model_dump_json())

    assert written["ByKind"] == {"Fixed": 2.5, "None": 1.0}
    assert SupportTotals.model_validate_json(totals.model_dump_json()) == totals

def test_a_key_that_is_not_a_member_is_flagged():
    """Checks that a wrong key is refused with the members listed, whether it comes from a constructor or from JSON; C# would not flag it."""
    SupportTotals = cls("SupportTotals")

    with pytest.raises(ValidationError, match=r"Bogus is not a member of SupportKind\. Members: None, Fixed, Pinned\."):
        SupportTotals(ByKind={"Bogus": 1.0})  # pyright: ignore[reportArgumentType]

    with pytest.raises(ValidationError, match="Fixd is not a member of SupportKind. Members: None, Fixed, Pinned. Did you mean Fixed"):
        SupportTotals.model_validate({"ByKind": {"Fixd": 1.0}})

@pytest.mark.xfail(strict=True, reason="BHoM writes a dictionary with a non-string key as an array of k/v objects; the generated Python only reads the object form")
def test_the_json_that_csharp_writes_is_read():
    """Checks that the k/v array that the BHoM serialiser writes for an enum-keyed dictionary is read into the dictionary.

    Fails today: the field expects an object. It must pass once the support layer reads (and ideally writes) the k/v form for every dictionary with a non-string key.
    """
    SupportTotals, SupportKind = cls("SupportTotals"), cls("SupportKind")

    totals = SupportTotals.model_validate_json(CSHARP_JSON)

    assert totals.ByKind == {SupportKind.Fixed: 2.5, SupportKind.None_: 1.0}
