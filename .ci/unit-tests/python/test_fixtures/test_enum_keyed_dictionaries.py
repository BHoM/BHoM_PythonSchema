"""Dictionaries with a key that is not a string, for the generated fixture classes SupportTotals (enum keys) and Collections (a class as the key).

What the real BHoM serialiser does (Serialiser_Engine, run on a SupportTotals with `Fixed` and `None` keys):

- It writes a dictionary with a key that is not a string as an array of `{"k": <key>, "v": <value>}`, with the member name as the key; BHoM_JSONSchema describes the same form.
- It reads that form, and also reads the plain object form `{"Fixed": 2.5}` that the Python side writes.
- It does not flag a key that is not a member: the key silently becomes the member with value 0.

The Python side reads that array into the dictionary (or, for a class as the key, into a list of pairs), writes it back as the array, and describes it so in its JSON Schema.
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator
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

def test_python_writes_the_array_that_csharp_writes():
    """Checks that the dictionary is written as an array of `k`/`v` objects with the C# member names as keys (`None`, not `None_`), and that it is read back to an equal object."""
    SupportTotals, SupportKind = cls("SupportTotals"), cls("SupportKind")
    totals = SupportTotals(ByKind={SupportKind.Fixed: 2.5, SupportKind.None_: 1.0})

    written = json.loads(totals.model_dump_json())

    assert written["ByKind"] == [{"k": "Fixed", "v": 2.5}, {"k": "None", "v": 1.0}]
    assert totals.model_dump()["ByKind"] == [{"k": "Fixed", "v": 2.5}, {"k": "None", "v": 1.0}]
    assert SupportTotals.model_validate_json(totals.model_dump_json()) == totals
    assert SupportTotals.model_validate(totals.model_dump()) == totals

def test_the_object_form_is_still_read():
    """Checks that a dictionary written as a plain JSON object (older Python output, or a hand-written file) is still read."""
    SupportTotals, SupportKind = cls("SupportTotals"), cls("SupportKind")

    assert SupportTotals.model_validate({"ByKind": {"Fixed": 1.0, "None": 2.0}}).ByKind == {SupportKind.Fixed: 1.0, SupportKind.None_: 2.0}

def test_a_key_that_is_not_a_member_is_flagged():
    """Checks that a wrong key is refused with the members listed, whether it comes from a constructor or from JSON; C# would not flag it."""
    SupportTotals = cls("SupportTotals")

    with pytest.raises(ValidationError, match=r"Bogus is not a member of SupportKind\. Members: None, Fixed, Pinned\."):
        SupportTotals(ByKind={"Bogus": 1.0})  # pyright: ignore[reportArgumentType]

    with pytest.raises(ValidationError, match="Fixd is not a member of SupportKind. Members: None, Fixed, Pinned. Did you mean Fixed"):
        SupportTotals.model_validate({"ByKind": {"Fixd": 1.0}})

    with pytest.raises(ValidationError, match="Bogus is not a member of SupportKind"):
        SupportTotals.model_validate({"ByKind": [{"k": "Bogus", "v": 1.0}]})

def test_the_json_that_csharp_writes_is_read():
    """Checks that the k/v array that the BHoM serialiser writes for an enum-keyed dictionary, plain and flags, is read into the dictionary."""
    SupportTotals, SupportKind, Options = cls("SupportTotals"), cls("SupportKind"), cls("Options")

    totals = SupportTotals.model_validate_json(CSHARP_JSON)

    assert totals.ByKind == {SupportKind.Fixed: 2.5, SupportKind.None_: 1.0}
    assert totals.ByOptions == {Options.A: 3, Options.Both: 5}

def test_the_json_schema_describes_the_array():
    """Checks that the JSON Schema of the class describes the array of `k`/`v` objects, with the member names as the allowed keys, and that the C# JSON validates against it."""
    SupportTotals = cls("SupportTotals")
    schema = SupportTotals.model_json_schema()
    items = schema["properties"]["ByKind"]["items"]

    assert schema["properties"]["ByKind"]["type"] == "array"
    assert items["properties"]["v"] == {"type": "number"}
    assert "None" in json.dumps(items["properties"]["k"])
    assert list(Draft202012Validator(schema).iter_errors(json.loads(CSHARP_JSON))) == []
    assert list(Draft202012Validator(schema).iter_errors({"ByKind": {"Fixed": 2.5}})) != []

def test_a_class_as_the_key_is_a_list_of_pairs_and_written_as_the_array():
    """Checks the dictionary whose key is a class (a list of pairs in Python): the k/v array is read into pairs, written back as the array, and described so."""
    Collections, PointLike = cls("Collections"), cls("PointLike")
    text = json.dumps({"ByPoint": [{"k": {"X": 1.0}, "v": "one"}, {"k": {"X": 2.0}, "v": "two"}]})

    collections = Collections.model_validate_json(text)

    assert [(point.X, name) for point, name in collections.ByPoint] == [(1.0, "one"), (2.0, "two")]
    assert [item["v"] for item in json.loads(collections.model_dump_json())["ByPoint"]] == ["one", "two"]
    assert json.loads(collections.model_dump_json())["ByPoint"][0]["k"]["X"] == 1.0
    assert Collections.model_validate_json(collections.model_dump_json()) == collections
    assert Collections.model_json_schema()["properties"]["ByPoint"]["items"]["properties"]["v"] == {"type": "string"}
    assert Collections(ByPoint=[(PointLike(X=3), "x")]).ByPoint[0][1] == "x"
