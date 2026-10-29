"""Base class of every generated model: it reads and writes the JSON that BHoM_JSONSchema describes."""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, model_serializer, model_validator

FRAGMENT_SET = "BH.oM.Base.FragmentSet"

def type_name(model: type[BaseModel]) -> str:
    """Returns the C# full name of a generated class, from its `__bhom__` marker, or the Python class name when there is none."""
    marker: dict[str, Any] = getattr(model, "__bhom__", {})
    return str(marker.get("clr_name", model.__name__))

def add_type_property(schema: dict[str, Any], model: type[BaseModel]) -> None:
    """Adds the optional `_t` property to the JSON Schema of a class, fixed to its C# name, as every schema of BHoM_JSONSchema has it."""
    properties = cast(dict[str, Any], schema.setdefault("properties", {}))
    properties["_t"] = {"type": ["string", "null"], "description": "Optional type disciminator.", "const": type_name(model)}

class SchemaModel(BaseModel):
    """Pydantic base of the generated classes.

    JSON follows BHoM_JSONSchema: every object is written with `_t`, its C# class name, and may carry `_bhomVersion`. A `_t` that is read
    must name this class. Interfaces are plain ABC classes, so fields typed with them need an isinstance check.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True, validate_by_name=True, validate_by_alias=True, serialize_by_alias=True, json_schema_extra=add_type_property)

    bhom_version: str | None = Field(default=None, alias="_bhomVersion", description="Optional version of BHoM used as part of automatic versioning and schema upgrades.")

    @model_validator(mode="before")
    @classmethod
    def read_type_tag(cls, data: Any) -> Any:
        """Checks and removes `_t` before a mapping is validated, and unwraps a FragmentSet written as an object.

        `_t` is optional, but when it is there it must be this class (the base name, for a generic class). BHoM writes a FragmentSet as
        `{"_t": "BH.oM.Base.FragmentSet", "_v": [...]}` or as a plain array; the fields hold a list, so both end up as one.
        """
        if not isinstance(data, dict):
            return data

        values = {str(key): value for key, value in cast(dict[Any, Any], data).items()}
        tag = values.pop("_t", None)
        if tag is not None:
            expected = type_name(cls)
            if str(tag).split("`")[0] != expected.split("`")[0]:
                raise ValueError(f"_t is {tag}, but this class is {expected}")

        for key, value in list(values.items()):
            if isinstance(value, dict) and cast(dict[str, Any], value).get("_t") == FRAGMENT_SET:
                values[key] = cast(dict[str, Any], value).get("_v") or []

        return values

    @model_serializer(mode="wrap")
    def write_type_tag(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Writes `_t` first, and leaves out `_bhomVersion` when it is not set, so the JSON matches what BHoM writes."""
        data = cast(dict[str, Any], handler(self))
        if data.get("_bhomVersion", 0) is None:
            del data["_bhomVersion"]

        return {"_t": type_name(type(self)), **data}
