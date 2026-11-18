"""The mapping of one silver table to BHoM classes: the typed objects, and the rules that every mapping file must meet.

A mapping says which columns of a flat silver table become which properties of which BHoM classes. `parse_mapping` turns the data of a YAML file into these objects and checks every rule
that can be checked without the table itself; it reports all the problems at once, so a person (or Genie Code) can fix them in one go. The rules that need the table's columns are
the methods `unaccounted` and `missing` of `TableMapping`, which `validate_mapping` uses.
"""

from __future__ import annotations

import difflib
import importlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel

from bhom_schema._support import Quantity
from bhom_schema.mapping import units
from bhom_schema.tables import Json, Ref, Skip, Struct
from bhom_schema.tables.columns import bare, describe
from bhom_schema.tables.decisions import Decision
from bhom_schema.tables.enums import names_of

VERSION = 1
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TABLE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
SCHEMA = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
TOP_KEYS = {"version", "source", "gold_schema", "entities", "unmapped"}
ENTITY_KEYS = {"class", "key", "parent", "fields", "columns"}
COLUMN_KEYS = {"from", "unit", "values", "default"}

class MappingError(ValueError):
    """A mapping file that breaks its rules. `problems` lists every one, each starting with where it is (`entities.Storey.columns.TypicalHeight`)."""

    def __init__(self, problems: Sequence[str]) -> None:
        """Keeps the problems and writes them, one per line, as the message."""
        self.problems = tuple(problems)
        noun = "a problem" if len(self.problems) == 1 else f"{len(self.problems)} problems"
        super().__init__(f"the mapping has {noun}:\n" + "\n".join(f"  - {problem}" for problem in self.problems))

@dataclass(frozen=True)
class ColumnMapping:
    """One property of a BHoM class and the silver column that fills it.

    `source` is the silver column. `unit` is the unit of the silver values when it is not the unit of the property. `values` maps silver text to member names of the property's enum.
    `has_default` says whether `default` is used when the silver value is empty.
    """

    property: str
    source: str
    unit: str | None = None
    values: Mapping[str, str] = field(default_factory=dict[str, str])
    default: Any = None
    has_default: bool = False

@dataclass(frozen=True)
class EntityMapping:
    """One BHoM class that the silver table holds rows of.

    `key` is the silver columns that identify one object: rows with the same values are one object. `parent` is the name of the entity this one belongs to; the parent's key columns
    are part of this key. `fields` holds the decisions (`bhom_schema.tables`) for the fields that have no column of their own.
    """

    name: str
    class_path: str
    model: type[BaseModel]
    key: tuple[str, ...]
    columns: tuple[ColumnMapping, ...]
    parent: str | None = None
    fields: Mapping[str, Decision] = field(default_factory=dict[str, Decision])

    def source_columns(self) -> set[str]:
        """Returns every silver column this entity uses: its key and the sources of its properties."""
        return set(self.key) | {column.source for column in self.columns}

@dataclass(frozen=True)
class TableMapping:
    """The mapping of one silver table: `source` is its full name, `gold_schema` the `catalog.schema` where the gold tables go, and `unmapped` the silver columns with no BHoM home, with the reason."""

    source: str
    gold_schema: str
    entities: tuple[EntityMapping, ...]
    unmapped: Mapping[str, str] = field(default_factory=dict[str, str])
    version: int = VERSION

    def entity(self, name: str) -> EntityMapping:
        """Returns the entity with that name, or raises KeyError."""
        for entity in self.entities:
            if entity.name == name:
                return entity

        raise KeyError(name)

    def used_columns(self) -> set[str]:
        """Returns the silver columns that some entity uses, as a key or as the source of a property."""
        columns: set[str] = set()
        for entity in self.entities:
            columns |= entity.source_columns()

        return columns

    def accounted_columns(self) -> set[str]:
        """Returns the silver columns the mapping knows about: the ones an entity uses, and the ones listed as unmapped."""
        return self.used_columns() | set(self.unmapped)

    def unaccounted(self, columns: Iterable[str]) -> list[str]:
        """Returns the columns of the silver table that the mapping does not know about, in the order given. A new column of the table shows up here."""
        known = self.accounted_columns()
        return [column for column in columns if column not in known]

    def missing(self, columns: Iterable[str]) -> list[str]:
        """Returns the columns the mapping uses or lists that the silver table no longer has, sorted. A renamed or dropped column shows up here."""
        present = set(columns)
        return sorted(self.accounted_columns() - present)

# ------------------------------------------------------------------------------------------------ reading

def as_dict(value: object, where: str, problems: list[str]) -> dict[str, Any] | None:
    """Returns the value as a dictionary with text keys, or records the problem and returns None."""
    if not isinstance(value, dict):
        problems.append(f"{where} must be a mapping of names to values")
        return None

    items = cast(dict[object, Any], value)
    if not all(isinstance(key, str) for key in items):
        problems.append(f"{where} must have text names")
        return None

    return cast(dict[str, Any], items)

def as_names(value: object, where: str, problems: list[str]) -> tuple[str, ...]:
    """Returns the value as a tuple of non-empty texts, or records the problem and returns an empty tuple."""
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in cast(list[object], value)):
        problems.append(f"{where} must be a list of column names, with at least one")
        return ()

    names = tuple(cast(list[str], value))
    if len(set(names)) != len(names):
        problems.append(f"{where} lists a column twice")

    return names

def unknown_keys(data: Mapping[str, Any], allowed: set[str], where: str, problems: list[str]) -> None:
    """Records a problem for every key that is not allowed, with the closest allowed key as a hint."""
    for key in data:
        if key in allowed:
            continue

        hint = difflib.get_close_matches(key, sorted(allowed), n=1)
        problems.append(f"{where}: unknown key {key!r}" + (f" (did you mean {hint[0]!r}?)" if hint else f"; the keys are {', '.join(sorted(allowed))}"))

def read_decision(value: object, where: str, problems: list[str]) -> Decision | None:
    """Reads a decision: `skip`, `json`, `struct`, `ref:<table>`, `{struct: {<field>: <decision>}}` or `{ref: <table>, column: <name>}`. Records a problem and returns None for anything else."""
    if value == "skip":
        return Skip()

    if value == "json":
        return Json()

    if value == "struct":
        return Struct()

    if isinstance(value, str) and value.startswith("ref:") and value[4:].strip():
        return Ref(value[4:].strip())

    if isinstance(value, dict):
        data = as_dict(cast(object, value), where, problems)
        if data is not None and set(data) == {"struct"}:
            inner = as_dict(data["struct"], f"{where}.struct", problems)
            decisions = {name: read_decision(item, f"{where}.struct.{name}", problems) for name, item in (inner or {}).items()}
            return Struct({name: decision for name, decision in decisions.items() if decision is not None})

        if data is not None and "ref" in data and set(data) <= {"ref", "column"} and isinstance(data["ref"], str) and data["ref"].strip():
            column = data.get("column")
            if column is None or isinstance(column, str) and column.strip():
                return Ref(data["ref"].strip(), column)

    problems.append(f"{where} must be skip, json, struct, ref:<table>, {{struct: {{...}}}} or {{ref: <table>, column: <name>}}")
    return None

def load_class(path: object, where: str, problems: list[str]) -> type[BaseModel] | None:
    """Imports the BHoM class a mapping names, such as `bhom_schema.DataSchema_oM.Storey.Storey`. Only classes of `bhom_schema` are accepted."""
    if not isinstance(path, str) or "." not in path:
        problems.append(f"{where} must be the full path of a class, such as bhom_schema.DataSchema_oM.Storey.Storey")
        return None

    module_name, _, class_name = path.rpartition(".")
    if not module_name.startswith("bhom_schema."):
        problems.append(f"{where}: {path} is not a class of bhom_schema")
        return None

    try:
        found: Any = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError):
        problems.append(f"{where}: {path} was not found in bhom_schema")
        return None

    if not (isinstance(found, type) and issubclass(found, BaseModel)):
        problems.append(f"{where}: {path} is not a BHoM class")
        return None

    return found

def read_column(prop: str, value: object, model: type[BaseModel] | None, where: str, problems: list[str]) -> ColumnMapping | None:
    """Reads the mapping of one property: where its value comes from, its unit, its value map and its default. Checks the unit and the values against the property of the class."""
    data = as_dict(value, where, problems)
    if data is None:
        return None

    unknown_keys(data, COLUMN_KEYS, where, problems)
    source = data.get("from")
    if not isinstance(source, str) or not source:
        problems.append(f"{where}: from must name the silver column")
        return None

    unit, values = data.get("unit"), data.get("values")
    if unit is not None and not isinstance(unit, str):
        problems.append(f"{where}: unit must be text")
        unit = None

    mapped: dict[str, str] = {}
    if values is not None:
        items = as_dict(values, f"{where}.values", problems)
        for text, member in (items or {}).items():
            if isinstance(member, str):
                mapped[text] = member
            else:
                problems.append(f"{where}.values.{text}: the enum member must be text")

    default = data.get("default")
    if default is not None and not isinstance(default, str | int | float | bool):
        problems.append(f"{where}: default must be a single value")

    if model is not None and prop in model.model_fields:
        check_property(model, prop, unit, mapped, where, problems)

    return ColumnMapping(prop, source, unit, mapped, default, "default" in data)

def check_property(model: type[BaseModel], prop: str, unit: str | None, values: Mapping[str, str], where: str, problems: list[str]) -> None:
    """Checks a unit against the quantity of the property, and a value map against the members of its enum."""
    info = model.model_fields[prop]
    kind, markers = bare(info.annotation, info.metadata)
    quantity = next((marker for marker in markers if isinstance(marker, Quantity)), None)
    if unit is not None:
        if quantity is None:
            problems.append(f"{where}: {prop} has no quantity, so it takes no unit")
        else:
            try:
                units.factor(quantity.category, unit, quantity.unit)
            except ValueError as error:
                problems.append(f"{where}: unit {unit!r} does not fit {prop}, a {quantity.category} in {quantity.unit}: {error}")

    if not values:
        return

    if not (isinstance(kind, type) and issubclass(kind, Enum)):
        problems.append(f"{where}: {prop} is not an enum, so it takes no values")
        return

    members = names_of(kind)
    for text, member in values.items():
        if member not in members:
            hint = difflib.get_close_matches(member, members, n=1)
            problems.append(f"{where}.values.{text}: {member!r} is not a member of {kind.__name__}" + (f" (did you mean {hint[0]!r}?)" if hint else ""))

def check_fields(model: type[BaseModel], decisions: Mapping[str, Decision], columns: Sequence[ColumnMapping], where: str, problems: list[str]) -> None:
    """Checks the properties of an entity against its class: every name exists, a property is either mapped to a column or decided (not both), a mapped property has a column of its own,
    and no field is left without a decision."""
    names = list(model.model_fields)
    for column in columns:
        if column.property not in names:
            hint = difflib.get_close_matches(column.property, names, n=1)
            problems.append(f"{where}.columns.{column.property}: {model.__name__} has no property {column.property!r}" + (f" (did you mean {hint[0]!r}?)" if hint else ""))

    unknown = [name for name in decisions if name not in names]
    for name in unknown:
        problems.append(f"{where}.fields.{name}: {model.__name__} has no field {name!r}")

    mapped = {column.property for column in columns}
    for name in sorted(mapped & set(decisions)):
        problems.append(f"{where}: {name} is both mapped to a column and decided under fields; use one")

    known = {name: decision for name, decision in decisions.items() if name in names and name not in mapped}
    try:
        described = describe(model, known)
    except ValueError as error:
        problems.append(f"{where}.fields: {error}")
        return

    columns_by_field = {column.field: column for column in described if column.field is not None}
    for name in sorted(mapped & set(names)):
        column = columns_by_field[name]
        if column.needs_decision:
            problems.append(f"{where}.columns.{name}: {name} holds {column.undecided_fields[0].type}, which has no column of its own; decide it under fields instead")

    needing = [f"{column.field} ({column.undecided_fields[0].type})" for column in described if column.needs_decision and column.field not in mapped]
    if needing:
        problems.append(f"{where}.fields: still needs a decision (skip, json, struct or ref:<table>): {', '.join(needing)}")

def read_entity(name: str, value: object, problems: list[str]) -> EntityMapping | None:
    """Reads one entity: its class, key, parent, decisions and columns, and checks them against the class. Records problems and returns None when it cannot be built."""
    where = f"entities.{name}"
    if not NAME.match(name):
        problems.append(f"{where}: the entity name must be letters, digits and underscores")

    data = as_dict(value, where, problems)
    if data is None:
        return None

    unknown_keys(data, ENTITY_KEYS, where, problems)
    model = load_class(data.get("class"), f"{where}.class", problems)
    key = as_names(data.get("key"), f"{where}.key", problems)
    parent = data.get("parent")
    if parent is not None and not isinstance(parent, str):
        problems.append(f"{where}.parent must be the name of another entity")
        parent = None

    decisions: dict[str, Decision] = {}
    fields = as_dict(data["fields"], f"{where}.fields", problems) if data.get("fields") is not None else {}
    for prop, item in (fields or {}).items():
        decision = read_decision(item, f"{where}.fields.{prop}", problems)
        if decision is not None:
            decisions[prop] = decision

    columns: list[ColumnMapping] = []
    items = as_dict(data.get("columns"), f"{where}.columns", problems)
    if items is not None and not items:
        problems.append(f"{where}.columns must map at least one property")

    for prop, item in (items or {}).items():
        column = read_column(prop, item, model, f"{where}.columns.{prop}", problems)
        if column is not None:
            columns.append(column)

    if model is None:
        return None

    check_fields(model, decisions, columns, where, problems)
    return EntityMapping(name, cast(str, data["class"]), model, key, tuple(columns), parent, decisions)

def check_links(entities: Sequence[EntityMapping], problems: list[str]) -> None:
    """Checks the parents: each names another entity of the mapping, its key columns are part of the child's key, and no entity is its own ancestor."""
    by_name = {entity.name: entity for entity in entities}
    for entity in entities:
        if entity.parent is None:
            continue

        where = f"entities.{entity.name}.parent"
        parent = by_name.get(entity.parent)
        if parent is None:
            problems.append(f"{where}: there is no entity {entity.parent!r}; the entities are {', '.join(by_name)}")
        elif parent is entity:
            problems.append(f"{where}: an entity cannot be its own parent")
        elif not set(parent.key) <= set(entity.key):
            absent = sorted(set(parent.key) - set(entity.key))
            problems.append(f"{where}: the key of {entity.name} must include the key columns of {parent.name}; missing {', '.join(absent)}")

    for entity in entities:
        seen = {entity.name}
        current = entity
        while current.parent is not None and current.parent in by_name:
            current = by_name[current.parent]
            if current.name in seen:
                problems.append(f"entities.{entity.name}.parent: the parents of {entity.name} go round in a circle")
                break

            seen.add(current.name)

def parse_mapping(data: object) -> TableMapping:
    """Turns the data of a mapping file (a dictionary, as YAML gives it) into a TableMapping, or raises MappingError listing every problem.

    Checks the version, the table names, every entity against its class (properties, units, enum values, decisions), the parents, and that no silver column is both used and listed as unmapped.
    """
    problems: list[str] = []
    top = as_dict(data, "the mapping", problems)
    if top is None:
        raise MappingError(problems)

    unknown_keys(top, TOP_KEYS, "the mapping", problems)
    if top.get("version") != VERSION:
        problems.append(f"version must be {VERSION}")

    source, gold = top.get("source"), top.get("gold_schema")
    if not isinstance(source, str) or not TABLE.match(source):
        problems.append("source must be the full name of the silver table: catalog.schema.table")

    if not isinstance(gold, str) or not SCHEMA.match(gold):
        problems.append("gold_schema must be catalog.schema")

    entities: list[EntityMapping] = []
    items = as_dict(top.get("entities"), "entities", problems)
    if items is not None and not items:
        problems.append("entities must hold at least one entity")

    for name, item in (items or {}).items():
        entity = read_entity(name, item, problems)
        if entity is not None:
            entities.append(entity)

    unmapped: dict[str, str] = {}
    listed = as_dict(top["unmapped"], "unmapped", problems) if top.get("unmapped") is not None else {}
    for column, reason in (listed or {}).items():
        if isinstance(reason, str) and reason.strip():
            unmapped[column] = reason
        else:
            problems.append(f"unmapped.{column} must say why it has no BHoM property")

    check_links(entities, problems)
    used: set[str] = set()
    for entity in entities:
        used |= entity.source_columns()

    for column in sorted(used & set(unmapped)):
        problems.append(f"unmapped.{column}: the column is listed as unmapped but an entity uses it")

    if problems:
        raise MappingError(problems)

    return TableMapping(cast(str, source), cast(str, gold), tuple(entities), unmapped)

# ------------------------------------------------------------------------------------------------ writing

def write_decision(decision: Decision) -> Any:
    """Writes a decision the way `read_decision` reads it."""
    if isinstance(decision, Skip):
        return "skip"

    if isinstance(decision, Json):
        return "json"

    if isinstance(decision, Ref):
        return f"ref:{decision.table}" if decision.column is None else {"ref": decision.table, "column": decision.column}

    if decision.fields is None:
        return "struct"

    return {"struct": {name: write_decision(inner) for name, inner in decision.fields.items()}}

def write_column(column: ColumnMapping) -> dict[str, Any]:
    """Writes one property's mapping as a dictionary, leaving out what is not set."""
    data: dict[str, Any] = {"from": column.source}
    if column.unit is not None:
        data["unit"] = column.unit

    if column.values:
        data["values"] = dict(column.values)

    if column.has_default:
        data["default"] = column.default

    return data

def mapping_to_data(mapping: TableMapping) -> dict[str, Any]:
    """Turns a TableMapping into the dictionary that is written as YAML, in the order a person reads it: header, entities, unmapped."""
    entities: dict[str, Any] = {}
    for entity in mapping.entities:
        data: dict[str, Any] = {"class": entity.class_path, "key": list(entity.key)}
        if entity.parent is not None:
            data["parent"] = entity.parent

        if entity.fields:
            data["fields"] = {name: write_decision(decision) for name, decision in entity.fields.items()}

        data["columns"] = {column.property: write_column(column) for column in entity.columns}
        entities[entity.name] = data

    result: dict[str, Any] = {"version": mapping.version, "source": mapping.source, "gold_schema": mapping.gold_schema, "entities": entities}
    if mapping.unmapped:
        result["unmapped"] = dict(mapping.unmapped)

    return result
