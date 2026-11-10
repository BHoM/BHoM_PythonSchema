"""Dictionaries with a key that is not a string, as BHoM writes them: an array of `{"k": <key>, "v": <value>}`.

BHoM_JSONSchema describes that form, and the BHoM serialiser writes and reads it, with an enum key as the member name. The generated field is a Python `dict` (or a
list of pairs, for a key that is a class), so a model reads the array into it before validation, writes the array back, and describes it in its JSON Schema.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass
from functools import cache
from typing import Annotated, Any, cast

from pydantic import BaseModel, TypeAdapter

from bhom_schema._support.markers import ClrType

@dataclass(frozen=True)
class KeyedField:
    """A field that BHoM writes as an array of key/value objects: its name, its JSON name, whether it holds a `dict` or a list of `pairs`, and whether it may be null."""

    name: str
    alias: str
    kind: str
    nullable: bool

def unwrap(annotation: Any) -> tuple[Any, bool]:
    """Removes `Annotated` and `| None` from an annotation, and says whether `None` was one of the options."""
    nullable = False
    while True:
        origin = typing.get_origin(annotation)
        arguments = typing.get_args(annotation)
        if origin is Annotated:
            annotation = arguments[0]
            continue

        if origin in (typing.Union, types.UnionType):
            options = [argument for argument in arguments if argument is not type(None)]
            nullable = nullable or len(options) < len(arguments)
            if len(options) == 1:
                annotation = options[0]
                continue

        return annotation, nullable

@cache
def keyed_fields(model: type[BaseModel]) -> tuple[KeyedField, ...]:
    """Lists the fields of a class that BHoM writes as key/value arrays: a `dict` whose key is not a string, and a list of pairs that came from a C# dictionary.

    The list of pairs is what a dictionary with a class as its key becomes, since a class cannot be a Python dictionary key; the field keeps the C# type in a ClrType marker.
    """
    found: list[KeyedField] = []
    for name, info in model.model_fields.items():
        kind, nullable = unwrap(info.annotation)
        arguments = typing.get_args(kind)
        origin = typing.get_origin(kind)
        alias = info.alias or name
        if origin is dict and len(arguments) == 2 and unwrap(arguments[0])[0] is not str:
            found.append(KeyedField(name, alias, "dict", nullable))
        elif origin is list and len(arguments) == 1 and typing.get_origin(unwrap(arguments[0])[0]) is tuple and len(typing.get_args(unwrap(arguments[0])[0])) == 2:
            clr = next((marker.name for marker in info.metadata if isinstance(marker, ClrType)), "")
            if "Dictionary<" in clr:
                found.append(KeyedField(name, alias, "pairs", nullable))

    return tuple(found)

def as_pairs(value: Any) -> list[tuple[Any, Any]] | None:
    """Reads a list of `{"k": ..., "v": ...}` objects into (key, value) pairs; returns None when the value is anything else, so it is left for validation to refuse."""
    if not isinstance(value, list):
        return None

    pairs: list[tuple[Any, Any]] = []
    for item in cast(list[Any], value):
        if not isinstance(item, dict) or set(cast(dict[str, Any], item)) != {"k", "v"}:
            return None

        entry = cast(dict[str, Any], item)
        pairs.append((entry["k"], entry["v"]))

    return pairs

def read_key_values(model: type[BaseModel], values: dict[str, Any]) -> None:
    """Replaces, in place, each key/value array of a mapping about to be validated by what the field holds: a dictionary, or a list of pairs for a class key.

    A value that is not an array of `k`/`v` objects (a dictionary written by Python, for one) is left as it is.
    """
    for field in keyed_fields(model):
        for key in (field.alias, field.name):
            pairs = as_pairs(values.get(key))
            if pairs is None:
                continue

            try:
                values[key] = dict(pairs) if field.kind == "dict" else [list(pair) for pair in pairs]
            except TypeError:
                raise ValueError(f"{key} has a key that cannot be a dictionary key") from None

def write_key_values(model: type[BaseModel], data: dict[str, Any]) -> None:
    """Replaces, in place, each dictionary or list of pairs of a serialised model by the array of `k`/`v` objects that BHoM writes."""
    for field in keyed_fields(model):
        value = data.get(field.alias)
        if isinstance(value, dict):
            data[field.alias] = [{"k": key, "v": item} for key, item in cast(dict[Any, Any], value).items()]
        elif isinstance(value, (list, tuple)):
            data[field.alias] = [{"k": pair[0], "v": pair[1]} for pair in cast(list[Any], value)]

def describe_key_values(model: type[BaseModel], properties: dict[str, Any]) -> None:
    """Replaces, in place, the JSON Schema of each key/value field by BHoM_JSONSchema's form: an array of objects with a key `k` and a value `v`."""
    for field in keyed_fields(model):
        schema = cast(dict[str, Any] | None, properties.get(field.alias))
        if schema is None:
            continue

        branch = next((option for option in cast(list[dict[str, Any]], schema.get("anyOf", [])) if option.get("type") != "null"), schema)
        if field.kind == "dict":
            info = model.model_fields[field.name]
            key_type = typing.get_args(unwrap(info.annotation)[0])[0]
            key_schema = {name: part for name, part in TypeAdapter(key_type).json_schema().items() if name != "title"}
            value_schema = branch.get("additionalProperties", {})
        else:
            prefix = cast(list[dict[str, Any]], branch.get("items", {}).get("prefixItems", [{}, {}]))
            key_schema, value_schema = prefix[0], prefix[1]

        replacement: dict[str, Any] = {
            "type": ["array", "null"] if field.nullable else "array",
            "items": {"type": "object", "properties": {"k": key_schema, "v": value_schema}},
        }
        for name in ("title", "description"):
            if name in schema:
                replacement[name] = schema[name]

        properties[field.alias] = replacement
