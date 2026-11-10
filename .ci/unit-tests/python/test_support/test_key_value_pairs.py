"""Dictionaries with a key that is not a string, read, written and described as BHoM does: an array of `{"k": ..., "v": ...}`. Stand-in classes only; the generated fixtures are in test_fixtures."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from bhom_schema._support import BHoMEnum, SchemaModel
from bhom_schema._support.key_value_pairs import keyed_fields

class Level(BHoMEnum):
    """A stand-in enum with a member that C# calls None."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Level", "kind": "enum", "renamed_members": {"None_": "None"}}
    None_ = 0
    High = 1

class Table(SchemaModel):
    """A stand-in class with dictionaries keyed by an enum, a UUID and a decimal, one of them optional, and one with a string key."""
    __bhom__: ClassVar[dict[str, Any]] = {"clr_name": "BH.oM.Table", "kind": "class"}
    ByLevel: dict[Level, float] = {}
    ById: dict[UUID, str] = {}
    ByCost: dict[Decimal, int] | None = None
    ByName: dict[str, int] = {}

IDENTIFIER = "0b6e5a52-3c0e-4a56-8c3e-7f4f3b4a9c11"

def test_only_the_dictionaries_with_a_key_that_is_not_a_string_are_keyed_fields():
    """Checks that the enum, UUID and decimal keys are found (with the optional one marked), and that a string key is not."""
    assert [(field.name, field.kind, field.nullable) for field in keyed_fields(Table)] == [("ByLevel", "dict", False), ("ById", "dict", False), ("ByCost", "dict", True)]

def test_the_array_is_read_and_written_for_every_kind_of_key():
    """Checks the round trip of the enum, UUID and decimal keys through the `k`/`v` array, and that a string-keyed dictionary stays an object."""
    table = Table.model_validate({"ByLevel": [{"k": "None", "v": 1.5}], "ById": [{"k": IDENTIFIER, "v": "a"}], "ByCost": [{"k": "2.5", "v": 3}], "ByName": {"x": 1}})

    assert table.ByLevel == {Level.None_: 1.5}
    assert table.ById == {UUID(IDENTIFIER): "a"}
    assert table.ByCost == {Decimal("2.5"): 3}

    written = json.loads(table.model_dump_json())

    assert written["ByLevel"] == [{"k": "None", "v": 1.5}]
    assert written["ById"] == [{"k": IDENTIFIER, "v": "a"}]
    assert written["ByName"] == {"x": 1}
    assert Table.model_validate_json(table.model_dump_json()) == table

def test_an_empty_or_missing_dictionary_and_a_null_one():
    """Checks that an empty array is an empty dictionary, that nothing written gives an empty array, and that a null optional dictionary stays null."""
    assert Table.model_validate({"ByLevel": []}).ByLevel == {}
    assert json.loads(Table().model_dump_json())["ByLevel"] == []
    assert json.loads(Table().model_dump_json())["ByCost"] is None
    assert Table.model_validate({"ByCost": None}).ByCost is None

def test_what_is_not_a_key_value_array_is_left_for_validation_to_refuse():
    """Checks that an array of anything but `k`/`v` objects, and a key that cannot be a dictionary key, are refused with an error and not read in part."""
    with pytest.raises(ValidationError):
        Table.model_validate({"ByLevel": [{"k": "None"}]})

    with pytest.raises(ValidationError):
        Table.model_validate({"ByLevel": [{"k": "None", "v": 1.0, "extra": 1}]})

    with pytest.raises(ValidationError, match="cannot be a dictionary key"):
        Table.model_validate({"ByLevel": [{"k": {"a": 1}, "v": 1.0}]})

def test_the_json_schema_is_an_array_of_key_value_objects():
    """Checks the schema of each kind: an array (or null for the optional one) of objects with `k` and `v`, and that the written JSON validates against it."""
    schema = Table.model_json_schema()
    properties = schema["properties"]

    assert properties["ByLevel"]["type"] == "array"
    assert properties["ByCost"]["type"] == ["array", "null"]
    assert properties["ById"]["items"]["properties"]["k"] == {"format": "uuid", "type": "string"}
    assert properties["ByName"]["type"] == "object"
    assert list(Draft202012Validator(schema).iter_errors(json.loads(Table(ByLevel={Level.High: 1.0}).model_dump_json()))) == []
