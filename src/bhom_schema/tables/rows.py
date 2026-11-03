"""Rows to objects and back, for the table of one class: the objects become dicts with the column names of the table, and the rows become objects of the class.

The conversions follow the column mapping: UUIDs and enums are text, a timedelta is seconds, a Json field is JSON text, a Struct field is a nested dict. Nothing here
reads or writes a table; the rows are plain dicts (or Spark Rows, which are turned into dicts).
"""

from __future__ import annotations

import typing
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, overload
from uuid import UUID, uuid4

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from bhom_schema._support import ClrType
from bhom_schema.tables.columns import KEY_COLUMN, bare, clr_elements, clr_name_of, column_for, column_type, quote, require_decided, shape_of
from bhom_schema.tables.decisions import Decision, Struct

INTEGER_BITS = {"TINYINT": 8, "SMALLINT": 16, "INT": 32, "BIGINT": 64}

@dataclass(frozen=True)
class RowError:
    """A row that could not become an object: its position in the rows, its key (None when the row has none), and why."""

    index: int
    key: str | None
    message: str

@dataclass
class Entry:
    """How one field of a class is stored in a row: its column, how it was decided, and for a Struct the entries of the class inside it."""

    field: str
    column: str
    kind: str
    info: FieldInfo
    child: list[Entry] | None = None
    many: bool = False
    adapter: TypeAdapter[Any] | None = None

def element_markers(clr: str | None) -> list[object]:
    """Returns the ClrType marker for the elements of a collection field, so a `long[]` keeps its `long` elements."""
    elements = clr_elements(clr)
    return [ClrType(elements)] if elements else []

def to_cell(value: Any, annotation: Any, markers: list[object], path: str) -> Any:
    """Turns the value of a primitive field into what its column holds: UUIDs and enums become text, a timedelta becomes seconds, collections convert element by element.

    Raises ValueError for an integer that does not fit its column and for a datetime with a time zone, naming the field.
    """
    if value is None:
        return None

    kind, found = bare(annotation, markers)
    clr = clr_name_of(found)
    origin = typing.get_origin(kind)
    arguments = typing.get_args(kind)
    if origin in (list, set, frozenset) and len(arguments) == 1:
        items = list(typing.cast(Iterable[Any], value))
        if origin is not list:
            try:
                items.sort()
            except TypeError:
                pass

        return [to_cell(item, arguments[0], element_markers(clr), f"{path}[{index}]") for index, item in enumerate(items)]

    if origin is dict and len(arguments) == 2:
        return {str(name): to_cell(item, arguments[1], element_markers(clr), f"{path}[{name!r}]") for name, item in typing.cast(Mapping[Any, Any], value).items()}

    if kind is int:
        bits = INTEGER_BITS.get(column_type(int, found))
        if bits is not None and not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
            raise ValueError(f"{path} is {value}, which does not fit its {column_type(int, found)} column")

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, timedelta):
        return value.total_seconds()

    if isinstance(value, datetime) and value.tzinfo is not None:
        raise ValueError(f"{path} is a datetime with a time zone, but BHoM DateTimes have none and the column is TIMESTAMP_NTZ; pass one without tzinfo")

    name = getattr(value, "bhom_name", None)
    if callable(name):
        return name()

    return value

def as_mapping(value: Any) -> Mapping[str, Any]:
    """Returns a row or a struct value as a mapping: a dict as it is, a Spark Row through its asDict."""
    if isinstance(value, Mapping):
        return typing.cast(Mapping[str, Any], value)

    as_dict = getattr(value, "asDict", None)
    if callable(as_dict):
        return typing.cast(Mapping[str, Any], as_dict(recursive=True))

    raise TypeError(f"{type(value).__name__} is not a row: pass a dict, or a Spark Row")

def build_entries(model: type[BaseModel], decisions: Mapping[str, Decision], path: str, stack: tuple[type[BaseModel], ...], nested: bool) -> list[Entry]:
    """Lists how every stored field of a class is kept in a row; the decisions have been checked, so each field is decided or skipped."""
    entries: list[Entry] = []
    for name, info in model.model_fields.items():
        # The version of BHoM is kept once per row, not inside every nested object
        if nested and name == "bhom_version":
            continue

        decision = decisions.get(name)
        column = column_for(name, info, decision, f"{path}{name}", (*stack, model))
        if column.decision == "skip":
            continue

        entry = Entry(name, column.name, column.decision, info)
        if column.decision == "json":
            entry.adapter = TypeAdapter(info.annotation)
        elif column.decision == "struct" and isinstance(decision, Struct):
            shape = shape_of(info.annotation)
            held: Any = bare(info.annotation)[0]
            child: type[BaseModel] = bare(typing.get_args(held)[0])[0] if shape == "classes" else held
            entry.many = shape == "classes"
            entry.child = build_entries(child, decision.fields or {}, f"{path}{name}.", (*stack, model), True)

        entries.append(entry)

    return entries

class RowPlan:
    """How the rows of one class, with the decisions and the key the table was made with, are written and read; built once, used for every row."""

    def __init__(self, model: type[BaseModel], fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN) -> None:
        """Checks that every field is decided (raising UnmappedType when not), and works out the entries and the key column."""
        columns = require_decided(model, fields, key)
        self.model = model
        self.key_column = next((column.name for column in columns if column.decision == "key"), None)
        self.adds_key = any(column.decision == "key" and column.field is None for column in columns)
        self.entries = build_entries(model, dict(fields or {}), "", (), False)
        self.refs = [entry for entry in self.entries if entry.kind == "ref"]

    def key_of(self, row: Mapping[str, Any]) -> str | None:
        """Returns the key of a row as text, or None when the table has no key or the row has no value for it."""
        value = row.get(self.key_column) if self.key_column else None
        return None if value is None else str(value)

    def cell(self, entry: Entry, value: Any, ids: Mapping[str, str | None]) -> Any:
        """Turns the value of one field into the cell of its column, by the way the field was decided."""
        if entry.kind == "ref":
            if entry.field in ids:
                return ids[entry.field]

            if value is None:
                return None

            raise ValueError(f"{entry.field} is a Ref: pass ids={{{entry.field!r}: <id of its row>}}, or None for no row")

        if value is None:
            return None

        if entry.kind == "json" and entry.adapter is not None:
            return entry.adapter.dump_json(value).decode()

        if entry.kind == "struct" and entry.child is not None:
            if entry.many:
                return [self.struct_cell(entry.child, item) for item in value]

            return self.struct_cell(entry.child, value)

        return to_cell(value, entry.info.annotation, list(entry.info.metadata), entry.field)

    def struct_cell(self, entries: list[Entry], item: Any) -> dict[str, Any]:
        """Turns an object held in a Struct field into a dict with the names of its columns."""
        return {entry.column: self.cell(entry, getattr(item, entry.field), {}) for entry in entries}

    def to_row(self, obj: BaseModel, ids: Mapping[str, str | None] | None = None) -> dict[str, Any]:
        """Writes an object as a dict with the column names of its table; `ids` gives the `_id` of the row and the id of the row of each Ref field."""
        ids = ids or {}
        if not isinstance(obj, self.model):
            raise TypeError(f"expected a {self.model.__name__}, not a {type(obj).__name__}")

        known = {entry.field for entry in self.refs} | {KEY_COLUMN}
        for name in ids:
            if name not in known:
                raise ValueError(f"ids names {name!r}, which is neither '_id' nor a Ref field of {self.model.__name__}")

        row: dict[str, Any] = {}
        if self.adds_key:
            row[KEY_COLUMN] = ids.get(KEY_COLUMN) or str(uuid4())

        for entry in self.entries:
            row[entry.column] = self.cell(entry, getattr(obj, entry.field), ids)

        return row

    def read_cells(self, entries: list[Entry], source: Mapping[str, Any], held: Mapping[str, Any]) -> dict[str, Any]:
        """Reads the cells of a row, or of a struct value, into the values of the fields; a NULL or absent cell leaves the field out, so it takes its default."""
        data: dict[str, Any] = {}
        for entry in entries:
            value = source.get(entry.column)
            if value is None:
                continue

            if entry.kind == "ref":
                if entry.field in held:
                    data[entry.field] = held[entry.field]
                else:
                    warnings.warn(f"{entry.field} is a Ref to the row {value}, but held has no object for it, so it keeps its default", stacklevel=4)
            elif entry.kind == "json" and entry.adapter is not None:
                data[entry.field] = entry.adapter.validate_json(value) if isinstance(value, (str, bytes)) else entry.adapter.validate_python(value)
            elif entry.kind == "struct" and entry.child is not None:
                if entry.many:
                    data[entry.field] = [self.read_cells(entry.child, as_mapping(item), {}) for item in value]
                else:
                    data[entry.field] = self.read_cells(entry.child, as_mapping(value), {})
            else:
                data[entry.field] = value

        return data

    def from_row(self, row: Any, held: Mapping[str, Any] | None = None) -> Any:
        """Reads one row into an object of the class; `held` gives the object of each Ref field, since no other table is read here."""
        return self.model.model_validate(self.read_cells(self.entries, as_mapping(row), held or {}))

def to_row(obj: BaseModel, *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN, ids: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """Writes one object as a dict with the column names of its table, ready for `createDataFrame` or an INSERT.

    `fields` and `key` are the ones the table was made with. `ids` gives the id of the row in `_id` when the table has an added key (otherwise a uuid4 text is made), and the
    id of the row in the other table for each Ref field, for example `{"Start": "abc"}`; None means no row. The key of the row is in the returned dict, for the Ref columns of other tables.
    """
    return RowPlan(type(obj), fields, key).to_row(obj, ids)

def from_row(model: type[BaseModel], row: Any, *, fields: Mapping[str, Decision] | None = None, held: Mapping[str, Any] | None = None) -> Any:
    """Reads one row (a dict, or a Spark Row) into an object of the class, the reverse of `to_row`.

    A NULL, or a column the row lacks, leaves the field with its default. `held` gives the object for each Ref field (`{"Start": point}`); a Ref with no entry keeps the default
    of the field, with a warning. Raises pydantic's ValidationError when a value does not fit the class.
    """
    return RowPlan(model, fields, KEY_COLUMN).from_row(row, held)

def read_many[M: BaseModel](
        model: type[M], rows: Iterable[Any], fields: Mapping[str, Decision] | None, key: str | None, held: Mapping[str, Mapping[str, Any]] | None, errors: str
) -> tuple[list[tuple[str | None, M]], list[RowError]]:
    """Reads every row, returning the (key, object) pairs and the errors; with errors='raise' the first bad row raises instead."""
    plan = RowPlan(model, fields, key)
    found: list[tuple[str | None, M]] = []
    problems: list[RowError] = []
    for index, row in enumerate(rows):
        mapping = as_mapping(row)
        row_key = plan.key_of(mapping)
        resolved: dict[str, Any] = {}
        for entry in plan.refs:
            identifier = mapping.get(entry.column)
            if identifier is not None and held is not None and identifier in held.get(entry.field, {}):
                resolved[entry.field] = held[entry.field][identifier]

        try:
            found.append((row_key, plan.from_row(mapping, resolved)))
        except (ValidationError, ValueError) as error:
            if errors != "collect":
                raise

            problems.append(RowError(index, row_key, str(error)))

    return found, problems

@overload
def rows_to_objects[M: BaseModel](
        model: type[M], rows: Iterable[Any], *, fields: Mapping[str, Decision] | None = ..., key: str | None = ..., held: Mapping[str, Mapping[str, Any]] | None = ...,
        keyed: Literal[False] = ..., errors: Literal["raise"] = ...) -> list[M]:
    """Reads the rows into a list of objects."""
@overload
def rows_to_objects[M: BaseModel](
        model: type[M], rows: Iterable[Any], *, fields: Mapping[str, Decision] | None = ..., key: str | None = ..., held: Mapping[str, Mapping[str, Any]] | None = ...,
        keyed: Literal[True], errors: Literal["raise"] = ...) -> dict[str, M]:
    """Reads the rows into a dict of objects by key."""
@overload
def rows_to_objects[M: BaseModel](
        model: type[M], rows: Iterable[Any], *, fields: Mapping[str, Decision] | None = ..., key: str | None = ..., held: Mapping[str, Mapping[str, Any]] | None = ...,
        keyed: Literal[False] = ..., errors: Literal["collect"]) -> tuple[list[M], list[RowError]]:
    """Reads the rows into a list of objects and the bad rows."""
@overload
def rows_to_objects[M: BaseModel](
        model: type[M], rows: Iterable[Any], *, fields: Mapping[str, Decision] | None = ..., key: str | None = ..., held: Mapping[str, Mapping[str, Any]] | None = ...,
        keyed: Literal[True], errors: Literal["collect"]) -> tuple[dict[str, M], list[RowError]]:
    """Reads the rows into a dict of objects by key and the bad rows."""
def rows_to_objects[M: BaseModel](
        model: type[M], rows: Iterable[Any], *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN, held: Mapping[str, Mapping[str, Any]] | None = None,
        keyed: bool = False, errors: Literal["raise", "collect"] = "raise") -> Any:
    """Reads many rows into objects of the class, with the decisions and key of its table.

    The result is the list of objects, or with `keyed=True` a dict {key: object}, which is what `held` of another table needs (a class such as PointLike keeps its id only in its row).
    `held` is {field: {id: object}} for each Ref field. With `errors="collect"` a bad row does not stop the others: the result is followed by a RowError per bad row; with "raise"
    (the default) the first one raises.
    """
    if keyed and key is None:
        raise ValueError("keyed=True needs a key to key the objects by, but key is None")

    found, problems = read_many(model, rows, fields, key, held, errors)
    if keyed:
        missing = [index for index, (row_key, _) in enumerate(found) if row_key is None]
        if missing:
            raise ValueError(f"keyed=True, but {len(missing)} rows have no value in the key column")

        result: Any = {str(row_key): item for row_key, item in found}
    else:
        result = [item for _, item in found]

    return (result, problems) if errors == "collect" else result

def ddl_schema(model: type[BaseModel], *, fields: Mapping[str, Decision] | None = None, key: str | None = KEY_COLUMN) -> str:
    """Returns the columns of the table of a class as a DDL string, for `spark.createDataFrame(rows, schema=...)`; the same columns as create_table_sql, without the comments."""
    columns = require_decided(model, fields, key)
    return ", ".join(f"{quote(column.name)} {column.type}" + ("" if column.nullable else " NOT NULL") for column in columns if column.type is not None)

def example_row(model: type[BaseModel], *, fields: Mapping[str, Decision] | None = None) -> dict[str, Any]:
    """Returns a row with the defaults of the class, with a made-up key and no row for each Ref, for a quick insert or `createDataFrame` check.

    Raises ValueError for a class that has required fields, since it has no default object.
    """
    try:
        item = model()
    except ValidationError as error:
        raise ValueError(f"{model.__name__} has required fields, so it has no default row: {error.error_count()} errors") from error

    plan = RowPlan(model, fields)
    return plan.to_row(item, {entry.field: None for entry in plan.refs})
