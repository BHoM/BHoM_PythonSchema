"""The columns of the table of one class: the type of each, the fields that still need a decision, and what each column would say in its comment.

Nothing here runs SQL or imports Spark. Every function takes one class; a field that holds another class is never followed, only reported or stored as the user decided.
"""

from __future__ import annotations

import collections.abc
import types
import typing
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum, Flag
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from bhom_schema._support import ClrType, DisplayText, Polymorphic, Quantity
from bhom_schema.tables.decisions import Decision, Json, Ref, Skip

CALLABLE: Any = collections.abc.Callable
KEY_COLUMN = "_id"
DECIMAL_TYPE = "DECIMAL(38,10)"
# Column types of the C# integer types that Python cannot tell apart; a plain int is a C# int
INTEGER_TYPES = {
    "long": "BIGINT", "short": "SMALLINT", "sbyte": "TINYINT",
    # byte is 0 to 255, which TINYINT (up to 127) cannot hold
    "byte": "SMALLINT", "ushort": "INT", "uint": "BIGINT", "ulong": "DECIMAL(20,0)",
}
DECISION_HELP = (
    '  Ref("catalog.schema.Table")  an id column that points at a row of that table\n'
    "  Struct()                     a STRUCT column holding the object's own fields\n"
    "  Json()                       the object as JSON text in a STRING column\n"
    "  Skip()                       no column; the field keeps its default when a row is read"
)

class UnmappedType(TypeError):
    """A type that has no column type, or fields that need a decision before the class can have a table.

    `fields` maps the path of each undecided field (`Start`, or `Start.Inner` inside a Struct) to its type, as text; it is empty for a single type.
    """

    def __init__(self, message: str, fields: Mapping[str, str] | None = None) -> None:
        """Keeps the message and the undecided fields (path to type text) that the message lists."""
        super().__init__(message)
        self.fields: dict[str, str] = dict(fields or {})

@dataclass(frozen=True)
class ColumnInfo:
    """One column of a table, or a field that has none.

    `name` is the column name, `type` the column type (None when there is no column yet), `field` the Python field the column comes from (None for the added
    key), and `decision` how it was decided: `primitive`, `key`, `ref`, `struct`, `json`, `skip`, or `undecided`. `undecided` lists the path and type of every
    field that still needs a decision.
    """

    name: str
    type: str | None
    nullable: bool
    comment: str | None
    field: str | None
    decision: str
    undecided: tuple[tuple[str, str], ...] = ()

def quote(name: str) -> str:
    """Quotes a column or field name with backticks, as Spark SQL needs for names such as `End` and `Key`."""
    return "`" + name.replace("`", "``") + "`"

def bare(annotation: Any, markers: Sequence[object] = ()) -> tuple[Any, list[object]]:
    """Removes `Annotated` and `| None` from an annotation, and returns the bare type with every marker that was inside it, after `markers`.

    `Annotated[int, ClrType('long')] | None` gives `int` and the ClrType.
    """
    found = list(markers)
    while True:
        origin = typing.get_origin(annotation)
        arguments = typing.get_args(annotation)
        if origin is Annotated:
            annotation = arguments[0]
            found.extend(arguments[1:])
            continue

        if origin in (typing.Union, types.UnionType):
            options = [argument for argument in arguments if argument is not type(None)]
            if len(options) == 1:
                annotation = options[0]
                continue

        return annotation, found

def describe_type(annotation: Any) -> str:
    """Writes a type the way a user would: `PointLike`, `list[PointLike]`, `Polymorphic[IFragment]`."""
    kind, _ = bare(annotation)
    if kind is Any:
        return "Any"

    origin = typing.get_origin(kind)
    if origin is not None:
        arguments = ", ".join(describe_type(argument) for argument in typing.get_args(kind))
        return f"{getattr(origin, '__name__', str(origin))}[{arguments}]"

    if isinstance(kind, type):
        return kind.__name__

    return str(kind)

def clr_name_of(markers: Sequence[object]) -> str | None:
    """Returns the C# type the generator recorded for a field (`long`, `double[]`, `List<float>`), or None."""
    return next((marker.name for marker in markers if isinstance(marker, ClrType)), None)

def clr_elements(clr: str | None) -> str | None:
    """Returns the C# type of the elements of a collection type: `long` for `long[]` and `List<long>`, the value type for a `Dictionary<string, long>`."""
    if clr is None:
        return None

    if clr.endswith("[]"):
        return clr[:-2]

    start = clr.find("<")
    if start < 0 or not clr.endswith(">"):
        return None

    depth = 0
    last = start + 1
    for index in range(start + 1, len(clr) - 1):
        if clr[index] == "<":
            depth += 1
        elif clr[index] == ">":
            depth -= 1
        elif clr[index] == "," and depth == 0:
            last = index + 1

    return clr[last:len(clr) - 1].strip()

def element_type(annotation: Any, clr: str | None) -> str:
    """Returns the column type of an element of a list, a set or a dict, using the C# element type that the field recorded."""
    elements = clr_elements(clr)
    return column_type(annotation, [ClrType(elements)] if elements else [])

def column_type(annotation: Any, markers: Sequence[object] = ()) -> str:
    """Returns the Spark SQL type of a primitive annotation, or raises UnmappedType when the type has no column of its own.

    `markers` are the metadata of the field (pydantic keeps `ClrType` there, outside the annotation); they tell `long` from `int`, `float` from `double`.
    """
    kind, found = bare(annotation, markers)
    clr = clr_name_of(found)
    if kind is bool:
        return "BOOLEAN"

    if kind is int:
        return INTEGER_TYPES.get(clr or "", "INT")

    if kind is float:
        return "FLOAT" if clr == "float" else "DOUBLE"

    if kind is str or kind is UUID:
        return "STRING"

    if kind is Decimal:
        return DECIMAL_TYPE

    if kind is datetime:
        return "TIMESTAMP_NTZ"

    if kind is date:
        return "DATE"

    if kind is timedelta:
        return "DOUBLE"

    if isinstance(kind, type) and issubclass(kind, Enum):
        return "STRING"

    origin = typing.get_origin(kind)
    arguments = typing.get_args(kind)
    if origin in (list, set, frozenset) and len(arguments) == 1:
        return f"ARRAY<{element_type(arguments[0], clr)}>"

    if origin is dict and len(arguments) == 2 and bare(arguments[0])[0] is str:
        return f"MAP<STRING, {element_type(arguments[1], clr)}>"

    raise UnmappedType(f"{describe_type(annotation)} has no column type")

def shape_of(annotation: Any) -> str:
    """Tells what a field that has no column type holds: `class`, `classes` (a list of them), `interface`, `interfaces`, `callable` or `other`.

    The decisions use it to refuse what makes no sense, for example a Struct for an interface.
    """
    kind, _ = bare(annotation)
    origin = typing.get_origin(kind)
    if isinstance(kind, type) and issubclass(kind, BaseModel):
        return "class"

    if origin is Polymorphic or (isinstance(kind, type) and getattr(kind, "__bhom__", {}).get("kind") == "interface"):
        return "interface"

    if origin is CALLABLE:
        return "callable"

    arguments = typing.get_args(kind)
    if origin in (list, set, frozenset) and len(arguments) == 1:
        element = shape_of(arguments[0])
        if element == "class":
            return "classes"

        if element == "interface":
            return "interfaces"

    return "other"

def refuse_generic(model: type[BaseModel]) -> None:
    """Raises UnmappedType for a generic class, whose fields depend on a type argument that a table cannot record."""
    parameters: Sequence[Any] = model.__pydantic_generic_metadata__["parameters"]
    if parameters:
        names = ", ".join(str(parameter) for parameter in parameters)
        raise UnmappedType(f"{model.__name__} is a generic class (type parameters {names}), and a table cannot record which type its rows were written with")

def check_names(model: type[BaseModel], decisions: Mapping[str, Decision], path: str) -> None:
    """Raises ValueError for a decision that names a field the class does not have, so a typo is not ignored."""
    for name in decisions:
        if name not in model.model_fields:
            owner = f"{path} ({model.__name__})" if path else model.__name__
            raise ValueError(f"{owner} has no field {name!r}; its fields are {', '.join(model.model_fields)}")

def comment_of(info: FieldInfo, kind: Any) -> str | None:
    """Writes the column comment of a field: its display text, its description, its quantity and unit, and what the stored value means."""
    parts: list[str] = []
    for marker in info.metadata:
        if isinstance(marker, DisplayText):
            parts.append(marker.text if marker.text.endswith((".", "!", "?")) else marker.text + ".")

    if info.description:
        parts.append(info.description)

    for marker in info.metadata:
        if isinstance(marker, Quantity):
            parts.append(f"[{marker.category}, {marker.unit}]")

    if kind is timedelta:
        parts.append("Seconds.")
    elif kind is str and clr_name_of(info.metadata) == "char":
        parts.append("One character.")
    elif isinstance(kind, type) and issubclass(kind, Enum):
        members: Mapping[str, Any] = getattr(kind, "bhom_members", lambda: {member.name: member for member in kind})()
        names = ", ".join(members)
        parts.append(f"Any of: {names}, joined by ', '." if issubclass(kind, Flag) else f"One of: {names}.")

    return " ".join(parts) or None

def struct_type(model: type[BaseModel], decisions: Mapping[str, Decision] | None, path: str, stack: tuple[type[BaseModel], ...], missing: dict[str, str]) -> str:
    """Builds the STRUCT type of a class from its fields, mapped by the same rules as a table; the fields still undecided go into `missing` by path."""
    refuse_generic(model)
    if model in stack:
        cycle = " -> ".join(owner.__name__ for owner in (*stack, model))
        raise ValueError(f"{path} would nest {model.__name__} inside itself ({cycle}); store one of them as a Ref or Json, or Skip it")

    decisions = decisions or {}
    check_names(model, decisions, path)
    parts: list[str] = []
    for name, info in model.model_fields.items():
        # The version of BHoM is kept once per row, in the table, not inside every nested object
        if name == "bhom_version":
            continue

        entry = column_for(name, info, decisions.get(name), f"{path}.{name}", (*stack, model))
        missing.update(entry.undecided)
        if entry.type is not None:
            parts.append(f"{quote(entry.name)}: {entry.type}")

    if not parts and not missing:
        raise ValueError(f"{path}: every field of {model.__name__} is skipped, so there is nothing to store")

    return f"STRUCT<{', '.join(parts)}>"

def column_for(name: str, info: FieldInfo, decision: Decision | None, path: str, stack: tuple[type[BaseModel], ...]) -> ColumnInfo:
    """Builds the column of one field: its automatic type, or the one the decision gives, or the note that it is undecided."""
    column = info.alias or name
    annotation: Any = info.annotation
    kind, _ = bare(annotation, info.metadata)
    comment = comment_of(info, kind)
    try:
        primitive: str | None = column_type(annotation, info.metadata)
    except UnmappedType:
        primitive = None

    if decision is None:
        if primitive is not None:
            return ColumnInfo(column, primitive, True, comment, name, "primitive")

        return ColumnInfo(column, None, True, comment, name, "undecided", ((path, describe_type(annotation)),))

    if isinstance(decision, Skip):
        return ColumnInfo(column, None, True, comment, name, "skip")

    if primitive is not None:
        raise ValueError(f"{path} has a column of its own ({primitive}), so it takes no {type(decision).__name__}(); use Skip() to leave it out")

    shape = shape_of(annotation)
    if isinstance(decision, Json):
        if shape == "callable":
            raise ValueError(f"{path} is a function, which has no JSON; Skip() is its only decision")

        return ColumnInfo(column, "STRING", True, comment, name, "json")

    if isinstance(decision, Ref):
        if shape not in ("class", "interface"):
            raise ValueError(f"{path} holds {describe_type(annotation)}; a Ref points at one object, so use Struct() or Json() for a list, or Skip()")

        return ColumnInfo(decision.column or f"{name}_id", "STRING", True, comment, name, "ref")

    if shape not in ("class", "classes"):
        raise ValueError(f"{path} holds {describe_type(annotation)}; a Struct needs the fields of a class, which an interface or another type does not give. Use Ref(), Json() or Skip()")

    nested: Any = bare(annotation)[0]
    model: type[BaseModel] = bare(typing.get_args(nested)[0])[0] if shape == "classes" else nested
    missing: dict[str, str] = {}
    text = struct_type(model, decision.fields, path, stack, missing)
    if missing:
        return ColumnInfo(column, None, True, comment, name, "undecided", tuple(missing.items()))

    return ColumnInfo(column, f"ARRAY<{text}>" if shape == "classes" else text, True, comment, name, "struct")

def key_field_of(model: type[BaseModel], key: str | None) -> str | None:
    """Returns the field that is the key of the table, or None when the key is a column that is added (`_id`) or there is none.

    `_id` stands for the key of the class: the BHoM_Guid of a BHoMObject, or an added `_id` column otherwise. Any other value must be a field of the class.
    """
    if key is None:
        return None

    if key == KEY_COLUMN:
        return "BHoM_Guid" if "BHoM_Guid" in model.model_fields else None

    if key not in model.model_fields:
        raise ValueError(f"{model.__name__} has no field {key!r} to use as the key; its fields are {', '.join(model.model_fields)}")

    return key

def describe(model: type[BaseModel], fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN) -> list[ColumnInfo]:
    """Lists the columns that the table of a class would have, the key first, so the user sees the table before creating it.

    Fields with a primitive type are mapped; the others follow `fields` (a decision per field name). A field that still needs a decision is listed with the
    decision `undecided` and no type, and does not raise; `require_decided` raises for them. `key` is `_id` (the key of the class), a field name, or None.
    """
    refuse_generic(model)
    decisions = dict(fields or {})
    check_names(model, decisions, "")
    key_field = key_field_of(model, key)
    columns: list[ColumnInfo] = []
    if key == KEY_COLUMN and key_field is None:
        columns.append(ColumnInfo(KEY_COLUMN, "STRING", False, "Key of the row.", None, "key"))

    for name, info in model.model_fields.items():
        entry = column_for(name, info, decisions.get(name), name, (model,))
        if name == key_field:
            if entry.type is None:
                raise ValueError(f"{name} cannot be the key: it has no column type of its own")

            entry = ColumnInfo(entry.name, entry.type, False, entry.comment, name, "key")
            columns.insert(0, entry)
            continue

        columns.append(entry)

    return columns

def override_types(model: type[BaseModel], columns: Sequence[ColumnInfo], types: Mapping[str, str] | None) -> list[ColumnInfo]:
    """Returns the columns with the column type of the named fields replaced, for example `{"Cost": "DECIMAL(18,2)"}`.

    A name that is not a field of the class, or a field that has no column, raises ValueError, so a typo does not go unnoticed.
    """
    types = types or {}
    stored = {column.field for column in columns if column.type is not None}
    for name in types:
        if name not in model.model_fields:
            raise ValueError(f"{model.__name__} has no field {name!r} to give a column type; its fields are {', '.join(model.model_fields)}")

        if name not in stored:
            raise ValueError(f"{name} has no column to give a type, because its decision leaves it out")

    return [replace(column, type=types[column.field]) if column.field is not None and column.field in types else column for column in columns]

def custom_fields(model: type[BaseModel]) -> dict[str, Any]:
    """Returns the fields of a class that have no column of their own, with their types (`Start: PointLike`, `Points: list[PointLike]`).

    For a field that holds a class, the type is that class, so the user knows which table to make next.
    """
    refuse_generic(model)
    result: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        try:
            column_type(info.annotation, info.metadata)
        except UnmappedType:
            result[name] = bare(info.annotation)[0]

    return result

def require_decided(model: type[BaseModel], fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN) -> list[ColumnInfo]:
    """Returns the columns of a class like `describe`, but raises UnmappedType, listing the fields and the choices, when a field still needs a decision.

    The helpers that write SQL call it, so no column is ever left out without the user saying so.
    """
    columns = describe(model, fields, key)
    undecided = {path: kind for column in columns for path, kind in column.undecided}
    if not undecided:
        return columns

    count = len(undecided)
    noun = "a field" if count == 1 else f"{count} fields"
    verb = "it has" if count == 1 else "they have"
    lines = "\n".join(f"  {path}: {kind}" for path, kind in undecided.items())
    example = "..."
    for part in reversed(next(iter(undecided)).split(".")):
        example = f'{{"{part}": {example}}}' if example == "..." else f'{{"{part}": Struct(fields={example})}}'

    raise UnmappedType(
        f"{model.__name__} has {noun} of a custom type, so {verb} no column until you decide how to store them:\n{lines}\n"
        f"Pass fields={example} with one of:\n{DECISION_HELP}", undecided)
