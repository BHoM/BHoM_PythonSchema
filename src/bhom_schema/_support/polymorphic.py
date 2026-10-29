"""Fields typed with a C# interface or abstract class, written and read the way BHoM_JSONSchema describes them.

A value of such a field is an object of one of the implementing classes. In JSON it carries `_t`, the C# class name, which picks the class.
The generator writes the implementers of every interface (and abstract class) into its `__bhom__` marker, as text, so nothing is imported until
a `_t` value names a class.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Mapping
from typing import Annotated, Any, cast

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import PydanticCustomError, core_schema

ROOT_PACKAGE = "bhom_schema"
# How many interface descriptions are being written at this moment on this thread; see PolymorphicMarker.__get_pydantic_json_schema__
_describing = threading.local()

def implementers_of(interface: type) -> dict[str, str]:
    """Returns the classes that implement an interface, as {C# class name: module path below bhom_schema}, from the `implementers` entry of its marker.

    `Polymorphic` reads it to know which `_t` values an interface field accepts; an interface with no entry accepts no JSON, only objects.
    """
    marker: dict[str, Any] = getattr(interface, "__bhom__", {})
    return dict(marker.get("implementers", {}))

def load_class(location: str) -> type:
    """Imports the module of an implementing class and returns the class; the location is the module path below bhom_schema, optionally followed by :ClassName.

    Called only when a `_t` value names the class, so loading one class does not load the whole package.
    """
    path, _, name = location.partition(":")
    module = importlib.import_module(f"{ROOT_PACKAGE}.{path}")
    return getattr(module, name or path.rsplit(".", 1)[-1])

class PolymorphicMarker:
    """Metadata for `Polymorphic[...]`: makes Pydantic validate, save and describe an interface field the way BHoM_JSONSchema does."""

    def __get_pydantic_core_schema__(self, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        """Builds the validation of an interface field: an object of the interface is accepted as it is, JSON is validated against the class its `_t` names.

        Pydantic calls it once per field. The interface is the annotated type; it is kept in the schema metadata for the JSON Schema.
        """
        interface: type = source_type

        def validate(value: Any) -> Any:
            """Accepts an object of the interface, or a mapping whose `_t` names one of the implementers and which is valid for that class alone."""
            if isinstance(value, interface):
                return value

            if not isinstance(value, Mapping):
                raise PydanticCustomError("polymorphic_type", "expected an object of {interface} or a JSON object with _t", {"interface": interface.__name__})

            mapping = cast(Mapping[str, Any], value)
            tag = mapping.get("_t")
            if tag is None:
                raise PydanticCustomError("polymorphic_tag_missing", "a value for {interface} needs _t, the name of its class", {"interface": interface.__name__})

            implementers = implementers_of(interface)
            if tag not in implementers:
                raise PydanticCustomError("polymorphic_tag_unknown", "{tag} is not a class of {interface} in bhom_schema", {"tag": str(tag), "interface": interface.__name__})

            # The error of the chosen class is the only one reported: it names the real problem
            return getattr(load_class(implementers[tag]), "model_validate")(dict(mapping))

        return core_schema.no_info_plain_validator_function(validate, metadata={"bhom_interface": interface})

    def __get_pydantic_json_schema__(self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """Describes an interface field as BHoM_JSONSchema does: `_t` is required and one of the implementers, and the class it names decides the rest.

        `model_json_schema()` uses it, which is what makes the JSON Schema of every class with an interface field (for example every BHoMObject) work.
        """
        interface: type = schema["metadata"]["bhom_interface"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
        implementers = implementers_of(interface)
        description: JsonSchemaValue = {"required": ["_t"], "properties": {"_t": {"enum": list(implementers)}}}

        # An implementer can hold a field of an interface again, so describing every implementer inside every interface would never end:
        # only the outermost interface lists the classes with their schemas, and an interface met inside them lists the allowed _t values.
        depth: int = getattr(_describing, "depth", 0)
        if depth > 0:
            return description

        _describing.depth = depth + 1
        try:
            choices: list[JsonSchemaValue] = []
            for tag, location in implementers.items():
                model_schema: core_schema.CoreSchema = getattr(load_class(location), "__pydantic_core_schema__")
                choices.append({
                    "if": {"properties": {"_t": {"type": "string", "const": tag}}, "required": ["_t"]},
                    "then": handler(model_schema),
                })
        finally:
            _describing.depth = depth

        if choices:
            description["allOf"] = choices

        return description

type Polymorphic[T] = Annotated[T, PolymorphicMarker()]
