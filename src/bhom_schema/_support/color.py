"""Stand-in for ``System.Drawing.Color``."""

from __future__ import annotations
from pydantic import BaseModel

class Color(BaseModel):
    A: int = 0
    R: int = 0
    G: int = 0
    B: int = 0
