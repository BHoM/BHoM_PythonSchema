"""What a user decides for a field that has no column of its own, and the constant that most BHoMObject tables need.

A field whose type is a primitive gets a column without a decision. Any other field (another class, an interface, `Any`, a tuple) is stored the way the
user says here, one decision per field name, passed as `fields=` to the helpers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

@dataclass(frozen=True)
class Ref:
    """Stores the field as the id of a row in another table: a STRING column named `<Field>_id`, or `column` when it is given.

    For a field that holds one object of a class or of an interface. The table is the one the user has made (or will make) for that class.
    """

    table: str
    column: str | None = None

@dataclass(frozen=True)
class Struct:
    """Stores the field as a STRUCT column that holds the fields of the object, or an ARRAY of them for a list of objects.

    The class of the field is mapped by the same rules as a table: its primitive fields are automatic and its own custom fields need a decision, given in `fields`.
    """

    fields: Mapping[str, Decision] | None = None

@dataclass(frozen=True)
class Json:
    """Stores the field as the JSON text that the schema writes for it, in a STRING column."""

@dataclass(frozen=True)
class Skip:
    """Leaves the field out of the table; a row that is read keeps the default of the field."""

type Decision = Ref | Struct | Json | Skip

# The two fields of every BHoMObject that no table needs by default; spread it into `fields=` to leave them out
BASE_SKIPPED: Mapping[str, Decision] = {"Fragments": Skip(), "CustomData": Skip()}
