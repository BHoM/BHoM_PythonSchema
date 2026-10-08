"""Plain metadata markers used inside ``typing.Annotated``. Pydantic ignores them at runtime."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ClrType:
    """The original C# type of a field when it cannot be recovered from the Python annotation."""
    name: str


@dataclass(frozen=True)
class Quantity:
    """The physical quantity (for example ``Length``) and SI unit (for example ``m``) of a field."""
    category: str
    unit: str


@dataclass(frozen=True)
class DisplayText:
    """The C# ``DisplayText`` attribute of a field."""
    text: str


@dataclass(frozen=True)
class DynamicProperty:
    """Marks a field that is a C# ``DynamicProperty``."""
    pass
