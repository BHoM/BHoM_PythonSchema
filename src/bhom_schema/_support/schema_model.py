"""Base class of every generated model."""

from __future__ import annotations
from pydantic import BaseModel, ConfigDict

class SchemaModel(BaseModel):
    # Interfaces are plain ABC classes, so fields typed with them need an isinstance check.
    model_config = ConfigDict(arbitrary_types_allowed=True)
