"""A dummy class that tests the sync between Python and C#."""

from __future__ import annotations

from pydantic import Field

from bhom_schema.BHoM.BHoMObject import BHoMObject


class SyncTestDummy(BHoMObject):
    """A dummy class that tests the sync between Python and C#."""
    Label: str = Field("", description="A label.")
    Count: int = Field(0, description="A count.")
