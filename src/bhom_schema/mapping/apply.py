"""Applies a mapping to the rows of a silver table: groups the rows into the objects of each entity, converts the values, and builds the BHoM objects.

It is where the hard rules meet the data. Every value is converted by the mapping (a value map for enums, a unit factor for numbers), every object is built by its BHoM class, which validates it,
and everything that does not fit is recorded as a `Problem` instead of being dropped. `validate_mapping` reports the problems and `write_gold` refuses to write while there are any.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, Flag
from typing import Any

from pydantic import BaseModel, ValidationError

from bhom_schema.mapping import units
from bhom_schema.mapping.model import ColumnMapping, EntityMapping, TableMapping, field_facts
from bhom_schema.mapping.profile import empty, hashable
from bhom_schema.tables.enums import names_of

# The namespace of the ids of gold rows: an id is made from the entity and its key values, so the same silver row always gets the same id
ID_NAMESPACE = uuid.UUID("5b3f1c0e-6a52-4f0c-9d64-2d1f7a8b9c10")
EXAMPLES = 3

@dataclass(frozen=True)
class Problem:
    """Something in the data that the mapping cannot turn into a valid object.

    `kind` is `unknown-value` (an enum value that is not a member and not in the value map), `unit` (a value that is not a number under a unit), `conflict` (a column with two values
    in one object), `invalid` (the BHoM class refuses the object) or `columns` (a column of the table the mapping does not know, or the reverse). `count` is how many objects it affects, and `example` names the first.
    """

    entity: str
    kind: str
    message: str
    count: int = 1
    example: str | None = None

@dataclass
class GoldObject:
    """One object of an entity: its deterministic `id`, the id of its parent (None when the entity has none), its key values, and the BHoM object, or None when it is invalid."""

    id: str
    parent_id: str | None
    key: tuple[Any, ...]
    instance: BaseModel | None

@dataclass
class AppliedEntity:
    """The result of applying the mapping to one entity: the objects, the number of rows that were left out because a key column was empty, and the problems found."""

    entity: EntityMapping
    objects: list[GoldObject] = field(default_factory=list[GoldObject])
    empty_key_rows: int = 0
    problems: list[Problem] = field(default_factory=list[Problem])

    @property
    def valid(self) -> int:
        """Returns how many objects are valid."""
        return sum(1 for item in self.objects if item.instance is not None)

@dataclass
class Applied:
    """The result of applying a mapping to rows: `rows` read, and an AppliedEntity for each entity, parents first."""

    mapping: TableMapping
    rows: int
    entities: list[AppliedEntity] = field(default_factory=list[AppliedEntity])

    def problems(self) -> list[Problem]:
        """Returns every problem of every entity."""
        return [problem for applied in self.entities for problem in applied.problems]

class Log:
    """Collects the problems of one entity, adding up the ones that are the same (the same kind and message) and keeping the first example."""

    def __init__(self, entity: str) -> None:
        """Starts an empty log for an entity."""
        self.entity = entity
        self.found: dict[tuple[str, str], tuple[int, str | None]] = {}

    def add(self, kind: str, message: str, example: str | None = None, count: int = 1) -> None:
        """Records a problem, or adds to the count of the same one."""
        before = self.found.get((kind, message))
        self.found[(kind, message)] = (count + (before[0] if before else 0), before[1] if before else example)

    def problems(self) -> list[Problem]:
        """Returns the problems in the order they were first found."""
        return [Problem(self.entity, kind, message, count, example) for (kind, message), (count, example) in self.found.items()]

@dataclass(frozen=True)
class Facts:
    """What a mapped property needs to convert a value: its enum members, and the factor from the silver unit to the unit of the property."""

    column: ColumnMapping
    enum: type[Enum] | None
    members: frozenset[str]
    factor: float | None

def normal(value: Any) -> Any:
    """Writes a key value in one form, so `24` and `24.0` and ` 24 ` are one value: a whole float becomes an int, a text is stripped."""
    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)

    return value.strip() if isinstance(value, str) else value

def gold_id(entity: str, values: Sequence[Any]) -> str:
    """Returns the id of the gold row of an entity with those key values: a UUID made from the entity and the values, the same every time."""
    text = json.dumps([entity, *(normal(value) for value in values)], ensure_ascii=False, default=str)
    return str(uuid.uuid5(ID_NAMESPACE, text))

def gold_table(mapping: TableMapping, entity: EntityMapping) -> str:
    """Returns the full name of the gold table of an entity: the gold schema of the mapping and the name of the entity."""
    return f"{mapping.gold_schema}.{entity.name}"

def parent_column(entity: EntityMapping) -> str | None:
    """Returns the name of the column that holds the id of the parent row (`Building_id`), or None for an entity with no parent."""
    return f"{entity.parent}_id" if entity.parent else None

def ordered(mapping: TableMapping) -> list[EntityMapping]:
    """Returns the entities with each parent before its children, otherwise in the order of the file."""
    done: list[EntityMapping] = []
    pending = list(mapping.entities)
    while pending:
        ready = next(entity for entity in pending if entity.parent is None or any(item.name == entity.parent for item in done))
        done.append(ready)
        pending.remove(ready)

    return done

def facts_for(entity: EntityMapping) -> list[Facts]:
    """Works out, for each mapped property of an entity, its enum (with the member names) and the factor of its unit."""
    found: list[Facts] = []
    for column in entity.columns:
        kind, quantity = field_facts(entity.model, column.property)
        enum = kind if isinstance(kind, type) and issubclass(kind, Enum) else None
        factor = units.factor(quantity.category, column.unit, quantity.unit) if column.unit and quantity else None
        found.append(Facts(column, enum, frozenset(names_of(enum)) if enum else frozenset(), factor))

    return found

def convert(facts: Facts, raw: Any) -> tuple[Any, tuple[str, str] | None]:
    """Converts one silver value for its property: through the value map, then to the unit of the property.

    Returns the value and, when the value cannot be used, the problem as (kind, message) with the value None.
    """
    column = facts.column
    if isinstance(raw, str) and raw in column.values:
        raw = column.values[raw]

    if facts.enum is not None and isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",")] if issubclass(facts.enum, Flag) else [raw]
        if not all(part in facts.members for part in parts):
            return None, ("unknown-value", f"{column.property}: {raw!r} is not a member of {facts.enum.__name__} and not in values")

    if facts.factor is not None:
        if isinstance(raw, bool) or not isinstance(raw, int | float | Decimal | str):
            return None, ("unit", f"{column.property}: {raw!r} is not a number, so the unit {column.unit} cannot be converted")

        try:
            return float(raw) * facts.factor, None
        except ValueError:
            return None, ("unit", f"{column.property}: {raw!r} is not a number, so the unit {column.unit} cannot be converted")

    return raw, None

def apply_entity(entity: EntityMapping, mapping: TableMapping, rows: Sequence[Mapping[str, Any]]) -> AppliedEntity:
    """Applies the mapping to one entity: groups the rows by the key columns, reads each property from the group, and builds the objects."""
    applied = AppliedEntity(entity)
    log = Log(entity.name)
    facts = facts_for(entity)
    parent = next((item for item in mapping.entities if item.name == entity.parent), None)
    groups: dict[tuple[Hashable, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        values = [row.get(name) for name in entity.key]
        if any(empty(value) for value in values):
            applied.empty_key_rows += 1
            continue

        groups.setdefault(tuple(hashable(normal(value)) for value in values), []).append(row)

    for key, members in groups.items():
        label = ", ".join(f"{name}={value}" for name, value in zip(entity.key, key))
        data: dict[str, Any] = {}
        unusable = False
        for item in facts:
            found = list(dict.fromkeys(hashable(row.get(item.column.source)) for row in members if not empty(row.get(item.column.source))))
            if len(found) > 1:
                log.add("conflict", f"{item.column.source} has more than one value for one {entity.name}; the first is used", f"{label}: {', '.join(map(repr, found[:EXAMPLES]))}")

            raw = found[0] if found else None
            if raw is None:
                if item.column.has_default:
                    data[item.column.property] = item.column.default

                continue

            value, problem = convert(item, raw)
            if problem is not None:
                log.add(problem[0], problem[1], label)
                unusable = True
                continue

            data[item.column.property] = value

        identifier = gold_id(entity.name, key)
        # The key of an entity holds the key columns of its parent (a rule of the mapping), so the parent's key values are in the same rows
        parent_id = gold_id(parent.name, [normal(members[0].get(name)) for name in parent.key]) if parent is not None else None
        if "BHoM_Guid" in entity.model.model_fields:
            data["BHoM_Guid"] = identifier

        applied.objects.append(GoldObject(identifier, parent_id, tuple(key), None if unusable else build(entity, data, label, log)))

    applied.problems = log.problems()
    return applied

def build(entity: EntityMapping, data: Mapping[str, Any], label: str, log: Log) -> BaseModel | None:
    """Builds the object of an entity from its values with the BHoM class, which validates it. Records what the class refuses, one problem for each message, and returns None."""
    try:
        return entity.model.model_validate({name: value for name, value in data.items() if value is not None})
    except ValidationError as error:
        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"])
            log.add("invalid", f"{location}: {item['msg']}", label)

        return None

def apply_mapping(rows: Sequence[Mapping[str, Any]], mapping: TableMapping) -> Applied:
    """Applies a mapping to rows of its silver table: for each entity (parents first) the objects, with their deterministic ids and the id of their parent, and every problem found.

    Nothing is written and nothing is dropped silently: a row with an empty key column is counted for that entity, a value that does not fit becomes a problem, and an object that its BHoM
    class refuses is kept as invalid so it is reported.
    """
    result = Applied(mapping, len(rows))
    for entity in ordered(mapping):
        result.entities.append(apply_entity(entity, mapping, rows))

    return result
