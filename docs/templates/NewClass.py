"""Template for a hand-written class in src/bhom_schema. Copy it to <Assembly>/<namespace folders>/<ClassName>.py and edit it.

No __bhom__ marker is needed: py2cs works it out from the folder and the generated classes next to it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from bhom_schema._support import ClrType, Quantity
from bhom_schema.BHoM.BHoMObject import BHoMObject

# Derive from SchemaModel (from bhom_schema._support) instead when the class has no BHoM base class
class Example(BHoMObject):
    """What this class describes. BHoM requires a description on every oM class."""
    # Text, with a default and a description
    Reference: str = Field("", description="The project reference.")
    # A whole number; ClrType('long') says the C# type is long rather than int
    Count: Annotated[int, ClrType("long")] = Field(0, description="How many there are.")
    # A physical quantity: the C# property gets the [Length] attribute
    Span: Annotated[float, Quantity("Length", "m")] = Field(1.5, description="Distance between the supports.")
    # Optional value: "or nothing"
    Stage: int | None = Field(None, description="The RIBA stage, when known.")
    # A list starts empty for every new object
    Tags: list[str] = Field(default_factory=list, description="Free labels.")
