"""Enums written and read the way BHoM's JSON does: by member name, like "Centre".

BHoM writes an enum as its name, except at top level or in an `object` property, where it writes the object
`{"_t": "System.Enum", "TypeName": {"_t": "System.Type", "Name": "<C# enum name>"}, "Value": "<name>"}`. Both are read; the name is written.
"""

from __future__ import annotations

from enum import Enum, IntFlag
from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import PydanticCustomError, core_schema

class NamedMembers:
    """Mixin that gives a generated enum its BHoM JSON behaviour: names in and out, and the matching Pydantic schema and JSON Schema."""

    @classmethod
    def bhom_members(cls) -> dict[str, Any]:
        """Maps each member name as C# spells it to the member; `None_` is "None", from the renamed members of the marker.

        Used to read names from JSON and to list the allowed names in the JSON Schema. Aliases (a named combination of flags) are included.
        """
        renamed: dict[str, str] = getattr(cls, "__bhom__", {}).get("renamed_members", {})
        members: dict[str, Any] = getattr(cls, "__members__")
        return {renamed.get(name, name): member for name, member in members.items()}

    def bhom_name(self) -> str:
        """Returns the name BHoM writes for this value: the member's C# name, or the names of the set flags joined by ", " for a combination.

        The serializer of every generated enum field calls it.
        """
        cls = type(self)
        members = cls.bhom_members()
        value: int = getattr(self, "value")
        known: Any = getattr(cls, "_value2member_map_").get(value)
        if known is not None:
            return next(name for name, member in members.items() if member is known)

        parts = [name for name, member in members.items() if member.value & value and (member.value & (member.value - 1)) == 0]
        return ", ".join(parts) if parts else str(value)

    @classmethod
    def from_bhom(cls, value: Any) -> Any:
        """Reads a member from what BHoM JSON holds: a member name, "A, B" for combined flags, BHoM's object form, a number, or a member itself.

        The validator of every generated enum field calls it.
        """
        if isinstance(value, cls):
            return value

        if isinstance(value, dict) and "Value" in value:
            return cls.from_bhom(value["Value"])  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]

        if isinstance(value, bool):
            raise PydanticCustomError("enum_value", "{value} is not a value of {enum}", {"value": str(value), "enum": cls.__name__})

        if isinstance(value, int):
            try:
                return cls(value)  # pyright: ignore[reportCallIssue]
            except ValueError:
                raise PydanticCustomError("enum_value", "{value} is not a value of {enum}", {"value": str(value), "enum": cls.__name__}) from None

        if isinstance(value, str):
            members = cls.bhom_members()
            tokens = [part.strip() for part in value.split(",")]
            if len(tokens) > 1 and not issubclass(cls, IntFlag):
                raise PydanticCustomError("enum_value", "{value} names several members, and {enum} is not a flags enum", {"value": value, "enum": cls.__name__})

            result: Any = None
            for token in tokens:
                if token not in members:
                    raise PydanticCustomError("enum_value", "{value} is not a member of {enum}", {"value": token, "enum": cls.__name__})

                result = members[token] if result is None else result | members[token]

            return result

        raise PydanticCustomError("enum_value", "expected a member name of {enum}", {"enum": cls.__name__})

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        """Builds the schema Pydantic uses for a field of this enum: read with `from_bhom`, written as the name with `bhom_name`."""
        return core_schema.no_info_plain_validator_function(
            cls.from_bhom, serialization=core_schema.plain_serializer_function_ser_schema(lambda member: member.bhom_name(), return_schema=core_schema.str_schema()))

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """Describes the enum as BHoM_JSONSchema does: a name from the list of members, or BHoM's object form holding the same name.

        A flags enum may combine names ("A, B"), so for those the names are only suggestions and any string is allowed.
        """
        names = list(cls.bhom_members())
        name_schema: JsonSchemaValue = {"type": ["string", "null"]} if issubclass(cls, IntFlag) else {"type": ["string", "null"], "enum": names}
        return {"anyOf": [name_schema, {
            "type": ["object", "null"],
            "properties": {
                "_t": {"type": ["string", "null"], "const": "System.Enum"},
                "TypeName": {"type": ["object", "null"], "properties": {"_t": {"type": ["string", "null"], "const": "System.Type"}, "Name": {"type": ["string", "null"]}}},
                "Value": name_schema,
            },
        }]}

class BHoMEnum(NamedMembers, Enum):
    """Base class of the generated enums."""

class BHoMFlags(NamedMembers, IntFlag):
    """Base class of the generated enums that are C# [Flags] enums."""
