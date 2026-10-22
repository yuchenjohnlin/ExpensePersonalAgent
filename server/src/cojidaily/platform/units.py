"""Units of measure, shared by what a reading writes and what a ledger line stores.

oz is mass; liquids use fl_oz, which never converts to mL or to a weight. gal is the US liquid
gallon, for fuel. Only the mass units convert, with exact factors.
"""
from decimal import Decimal

UNITS = ("each", "pack", "g", "kg", "lb", "oz", "fl_oz", "mL", "L", "gal")
GRAMS_PER_UNIT = {"g": Decimal("1"), "kg": Decimal("1000"), "lb": Decimal("453.59237"), "oz": Decimal("28.349523125")}
WEIGHT_UNITS = tuple(GRAMS_PER_UNIT)
