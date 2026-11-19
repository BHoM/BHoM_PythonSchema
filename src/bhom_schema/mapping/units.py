"""The units a mapping may name for a silver column, and how to convert them to the unit of a BHoM property.

A BHoM property that carries a `Quantity` marker has one unit (`Quantity('Length', 'm')`). The values in a silver column may be in another unit of the same quantity (Revit
gives lengths in feet or millimetres, for example); the mapping says which, and `factor` gives the number to multiply by.
"""

from __future__ import annotations

# For each quantity, the units that can be named and the size of each in the base unit of the quantity (the unit of the first entry)
FACTORS: dict[str, dict[str, float]] = {
    "Length": {"m": 1.0, "mm": 0.001, "cm": 0.01, "km": 1000.0, "in": 0.0254, "ft": 0.3048, "yd": 0.9144},
    "Area": {"m²": 1.0, "mm²": 1e-6, "cm²": 1e-4, "km²": 1e6, "in²": 0.0254**2, "ft²": 0.3048**2},
    "Volume": {"m³": 1.0, "mm³": 1e-9, "cm³": 1e-6, "l": 1e-3, "in³": 0.0254**3, "ft³": 0.3048**3},
    "Mass": {"kg": 1.0, "g": 0.001, "t": 1000.0, "lb": 0.45359237},
    "Force": {"N": 1.0, "kN": 1000.0, "MN": 1e6, "lbf": 4.4482216152605, "kip": 4448.2216152605},
    "Pressure": {"Pa": 1.0, "kPa": 1000.0, "MPa": 1e6, "GPa": 1e9, "psi": 6894.757293168, "ksi": 6894757.293168},
    "Angle": {"rad": 1.0, "deg": 0.017453292519943295},
    "Time": {"s": 1.0, "min": 60.0, "h": 3600.0},
}
# Spellings that are written without the superscript
ALIASES: dict[str, str] = {
    "m2": "m²", "mm2": "mm²", "cm2": "cm²", "km2": "km²", "in2": "in²", "ft2": "ft²",
    "m3": "m³", "mm3": "mm³", "cm3": "cm³", "in3": "in³", "ft3": "ft³", "L": "l",
}

def normalise(unit: str) -> str:
    """Returns a unit in the spelling of the table (`m2` as `m²`), without surrounding spaces."""
    unit = unit.strip()
    return ALIASES.get(unit, unit)

def units_of(category: str) -> list[str]:
    """Lists the units that can be named for a quantity, or nothing when no conversion is known for it."""
    return list(FACTORS.get(category, {}))

def factor(category: str, source: str, target: str) -> float:
    """Returns the number that turns a value in `source` into a value in `target`, both units of the quantity `category`.

    Raises ValueError for a quantity with no table, or a unit that is not in it, naming the units that are.
    """
    table = FACTORS.get(category)
    if table is None:
        raise ValueError(f"no unit conversion is known for the quantity {category}")

    source, target = normalise(source), normalise(target)
    for unit in (source, target):
        if unit not in table:
            raise ValueError(f"{unit!r} is not a unit of {category}; use one of {', '.join(table)}")

    return table[source] / table[target]
