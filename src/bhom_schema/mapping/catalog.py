"""The BHoM classes and properties a silver column can be mapped to, read from the classes themselves for Genie Code (or a person) to look at.

`schema_overview` lists the classes, `describe_class` gives a card for each property (description, aliases, unit, enum members) and `search_properties` finds properties by words. They
report what the classes say and decide nothing: no score, no ranking. Which property a column means is a judgment, left to whoever reads these.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from functools import cache

from pydantic import BaseModel

from bhom_schema._support import DisplayText, Quantity
from bhom_schema.tables.columns import UnmappedType, bare, column_type, describe
from bhom_schema.tables.enums import names_of

DEFAULT_PACKAGE = "bhom_schema.DataSchema_oM"
# Fields every BHoM object has that a silver column is never mapped to (`Name` is kept: it is often a real column)
BASE_FIELDS = {"BHoM_Guid", "Fragments", "Tags", "CustomData", "bhom_version"}
# The demo classes of the package are not offered as a place for real data
DEMO_PREFIX = "Example"
ALIASES = re.compile(r"Aliases:\s*([^.]*)\.?\s*$")

@dataclass(frozen=True)
class PropertyEntry:
    """One property of a BHoM class that a silver column can fill.

    `kind` is how its values are held: `number`, `text`, `boolean`, `datetime` or `collection`. `quantity` is its `Quantity` marker (category and unit). `members` are the member names of its
    enum, when it has one.
    """

    model: type[BaseModel]
    name: str
    kind: str
    description: str
    display_text: str | None = None
    aliases: tuple[str, ...] = ()
    quantity: Quantity | None = None
    members: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """Returns the property as `Class.Property`, the way a person says it."""
        return f"{self.model.__name__}.{self.name}"

    @property
    def summary(self) -> str:
        """Returns the first sentence of the description."""
        return first_sentence(self.description)

    def text(self, full: bool = False) -> str:
        """Writes the card of the property as a few lines: how it is held, the unit, the description (the first sentence, or all of it with `full`), the display text, the aliases and the enum members."""
        held = self.kind + (f" in {self.quantity.unit} ({self.quantity.category})" if self.quantity else "")
        lines = [f"{self.name}: {held}"]
        description = self.description if full else self.summary
        if description:
            lines.append(f"    {description}")

        if self.display_text:
            lines.append(f"    display text: {self.display_text}")

        if self.aliases:
            lines.append(f"    aliases: {', '.join(self.aliases)}")

        if self.members:
            lines.append(f"    members: {', '.join(self.members)}")

        return "\n".join(lines)

@dataclass(frozen=True)
class ClassSummary:
    """One line of the overview: a BHoM class, where it is, the first sentence of its description, and how many properties take a silver column."""

    name: str
    path: str
    summary: str
    properties: int

@dataclass(frozen=True)
class ClassCard:
    """A BHoM class in full: its properties (the ones a silver column can fill) and the fields that have no column of their own, with their types, which a mapping must decide under `fields`."""

    name: str
    path: str
    description: str
    properties: tuple[PropertyEntry, ...]
    undecided: tuple[tuple[str, str], ...]

    def text(self, full: bool = False) -> str:
        """Writes the card for a person or Genie Code to read: the class, then each property, then the fields that need a decision."""
        lines = [f"{self.name} ({self.path})", f"    {self.description if full else first_sentence(self.description)}", "", "Properties a silver column can fill:"]
        lines += [entry.text(full) for entry in self.properties]
        lines += ["", "Fields with no column of their own (decide each under fields: skip, json, struct or ref):"]
        lines += [f"    {name}: {kind}" for name, kind in self.undecided]
        return "\n".join(lines)

@dataclass(frozen=True)
class PropertyMatch:
    """A property that a search found, and where the words were found (`name`, `display text`, `alias` or `description`)."""

    entry: PropertyEntry
    found_in: tuple[str, ...]

    @property
    def label(self) -> str:
        """Returns the property as `Class.Property`."""
        return self.entry.label

def first_sentence(text: str) -> str:
    """Returns the text up to the end of its first sentence, on one line."""
    flat = " ".join(inspect.cleandoc(text).split())
    found = re.search(r"(?<=[a-z0-9\)])\.(?=\s|$)", flat)
    return flat[:found.start() + 1] if found else flat

def words(text: str) -> set[str]:
    """Splits a text into lower-case words: on spaces and punctuation and at the capitals of `TypicalSlabHeight`, with a trailing plural `s` removed (`storeys` and `storey` are one word)."""
    found: set[str] = set()
    for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", text):
        word = part.lower()
        found.add(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)

    return found

def kind_of_column_type(sql_type: str) -> str:
    """Names how a column type holds its values: `number` for DOUBLE, INT and the like, `text` for STRING, `boolean`, `datetime`, or `collection` for ARRAY, MAP and STRUCT."""
    upper = sql_type.upper()
    if upper.startswith(("ARRAY", "MAP", "STRUCT")):
        return "collection"

    if upper == "BOOLEAN":
        return "boolean"

    if upper in ("DATE", "TIMESTAMP"):
        return "datetime"

    if upper == "STRING":
        return "text"

    return "number"

def aliases_of(description: str) -> tuple[str, ...]:
    """Reads the "Aliases: a, b, c." sentence at the end of a description, as a tuple of the aliases."""
    found = ALIASES.search(description)
    if found is None:
        return ()

    return tuple(alias.strip() for alias in found.group(1).split(",") if alias.strip())

def properties_of(model: type[BaseModel]) -> list[PropertyEntry]:
    """Lists the properties of a class that a silver column can fill: the ones with a column of their own, without the fields every BHoM object has (Fragments, CustomData and so on)."""
    entries: list[PropertyEntry] = []
    for name, info in model.model_fields.items():
        if name in BASE_FIELDS:
            continue

        try:
            sql_type = column_type(info.annotation, info.metadata)
        except UnmappedType:
            continue

        annotation, markers = bare(info.annotation, info.metadata)
        description = info.description or ""
        display = next((marker.text for marker in markers if isinstance(marker, DisplayText)), None)
        quantity = next((marker for marker in markers if isinstance(marker, Quantity)), None)
        members = tuple(names_of(annotation)) if isinstance(annotation, type) and issubclass(annotation, Enum) else ()
        entries.append(PropertyEntry(model, name, kind_of_column_type(sql_type), description, display, aliases_of(description), quantity, members))

    return entries

@cache
def entries_of(model: type[BaseModel]) -> tuple[PropertyEntry, ...]:
    """Returns the properties of a class that a silver column can fill, read once for each class."""
    return tuple(properties_of(model))

@cache
def schema_classes(package: str = DEFAULT_PACKAGE) -> tuple[type[BaseModel], ...]:
    """Lists the BHoM classes of a package of `bhom_schema` (`bhom_schema.DataSchema_oM` by default), each once, in module order, without the demo classes.

    The classes are found by importing the modules of the package, so the first call takes a moment.
    """
    root = importlib.import_module(package)
    classes: list[type[BaseModel]] = []
    for module_info in pkgutil.walk_packages(root.__path__, package + "."):
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if not (isinstance(value, type) and issubclass(value, BaseModel)) or value.__module__ != module.__name__ or value in classes:
                continue

            if getattr(value, "__bhom__", {}).get("kind") != "class" or value.__name__.startswith(DEMO_PREFIX):
                continue

            classes.append(value)

    return tuple(classes)

def schema_overview(package: str = DEFAULT_PACKAGE) -> list[ClassSummary]:
    """Lists the BHoM classes of a package, one line each: the name, the path to use in a mapping, the first sentence of the description and how many properties take a silver column.

    It is the way into the schema: small enough to read whole today, and the place to start when the schema grows.
    """
    return [
        ClassSummary(model.__name__, f"{model.__module__}.{model.__name__}", first_sentence(model.__doc__ or ""), len(entries_of(model)))
        for model in schema_classes(package)]

def resolve_class(name: str, package: str = DEFAULT_PACKAGE) -> type[BaseModel]:
    """Finds a class by its simple name (`Storey`) among the classes of the package, or by its full path. Raises KeyError listing the classes when there is none, or when a name fits several."""
    classes = schema_classes(package)
    if "." in name:
        module_name, _, class_name = name.rpartition(".")
        matches = [model for model in classes if model.__module__ == module_name and model.__name__ == class_name]
    else:
        matches = [model for model in classes if model.__name__ == name]

    if len(matches) == 1:
        return matches[0]

    reason = "fits several classes; use the full path" if matches else "is not a class of the package"
    raise KeyError(f"{name!r} {reason}; the classes are {', '.join(f'{model.__module__}.{model.__name__}' for model in classes)}")

def describe_class(name: str | type[BaseModel], package: str = DEFAULT_PACKAGE) -> ClassCard:
    """Gives the card of a class: its description, a card for each property a silver column can fill, and the fields with no column of their own (with their types) that a mapping must decide.

    `name` is the simple name (`Storey`), the full path, or the class itself. `ClassCard.text()` writes it for reading.
    """
    model = name if isinstance(name, type) else resolve_class(name, package)
    undecided = tuple((column.field or column.name, column.undecided_fields[0].type) for column in describe(model) if column.needs_decision)
    return ClassCard(model.__name__, f"{model.__module__}.{model.__name__}", inspect.cleandoc(model.__doc__ or ""), entries_of(model), undecided)

def search_properties(text: str, classes: Iterable[type[BaseModel]] | None = None, *, any_word: bool = False) -> list[PropertyMatch]:
    """Finds the properties whose name, display text, aliases or description contain the words of `text`: all of the words, or any of them with `any_word`.

    The matches come in the order of the classes and of the properties, each with where the words were found. Nothing is scored or ranked: it narrows a schema too large to read, and the
    reader judges. A word matches its plural (`storeys` finds `storey`) and the parts of a name (`height` finds `TypicalHeight`).
    """
    wanted = words(text)
    if not wanted:
        return []

    matches: list[PropertyMatch] = []
    for model in (classes if classes is not None else schema_classes()):
        for entry in entries_of(model):
            sources = {"name": words(entry.name), "display text": words(entry.display_text or ""), "alias": words(" ".join(entry.aliases)), "description": words(entry.description)}
            found = {word for word in wanted if any(word in source for source in sources.values())}
            if found == wanted or (any_word and found):
                matches.append(PropertyMatch(entry, tuple(label for label, source in sources.items() if wanted & source)))

    return matches
