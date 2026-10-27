"""Units of the metric system (spec section 11).

Every internal magnitude carries a unit. Dangerous implicit conversions
are forbidden: converting between different dimensions raises UnitError.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from core.errors import UnitError

# Base dimension exponents: (length_m, mass_kg, time_s)
Dimension = Tuple[int, int, int]

ZERO: Dimension = (0, 0, 0)


@dataclass(frozen=True)
class Unit:
    name: str
    symbol: str
    dimension: Dimension
    factor: float  # multiplier to the base unit of its dimension

    def compatible(self, other: "Unit") -> bool:
        return self.dimension == other.dimension


class UnitRegistry:
    """Registry of all units handled by the Core (spec section 11)."""

    def __init__(self) -> None:
        self._units: Dict[str, Unit] = {}

    def register(self, unit: Unit) -> None:
        self._units[unit.symbol.lower()] = unit

    def get(self, symbol: str) -> Unit:
        key = (symbol or "").strip().lower()
        unit = self._units.get(key)
        if unit is None:
            raise UnitError(
                message=f"Unidad desconocida: '{symbol}'",
                code="ARQ-UNI-002",
                context={"symbol": symbol},
                suggested_action="Use una unidad registrada del núcleo.",
            )
        return unit

    def has(self, symbol: str) -> bool:
        return (symbol or "").strip().lower() in self._units

    def all_symbols(self) -> list[str]:
        return sorted(u.symbol for u in self._units.values())

    def convert(self, value: float, source: str, target: str) -> float:
        src = self.get(source)
        dst = self.get(target)
        if not src.compatible(dst):
            raise UnitError(
                message=(
                    f"Conversión implícita peligrosa prohibida: "
                    f"{source} -> {target} ({src.dimension} -> {dst.dimension})"
                ),
                code="ARQ-UNI-003",
                context={"source": source, "target": target},
                suggested_action="Convierta manualmente con las fórmulas de la disciplina.",
            )
        return value * (src.factor / dst.factor)


def _build_default_registry() -> UnitRegistry:
    reg = UnitRegistry()
    registered: list[Unit] = [
        # Length (base unit: m)
        Unit("milímetro", "mm", (1, 0, 0), 0.001),
        Unit("centímetro", "cm", (1, 0, 0), 0.01),
        Unit("metro", "m", (1, 0, 0), 1.0),
        Unit("kilómetro", "km", (1, 0, 0), 1000.0),
        # Area (base unit: m2)
        Unit("milímetro cuadrado", "mm2", (2, 0, 0), 1.0e-6),
        Unit("centímetro cuadrado", "cm2", (2, 0, 0), 1.0e-4),
        Unit("metro cuadrado", "m2", (2, 0, 0), 1.0),
        # Volume (base unit: m3)
        Unit("milímetro cúbico", "mm3", (3, 0, 0), 1.0e-9),
        Unit("centímetro cúbico", "cm3", (3, 0, 0), 1.0e-6),
        Unit("metro cúbico", "m3", (3, 0, 0), 1.0),
        Unit("litro", "L", (3, 0, 0), 0.001),
        # Mass (base unit: kg)
        Unit("gramo", "g", (0, 1, 0), 0.001),
        Unit("kilogramo", "kg", (0, 1, 0), 1.0),
        Unit("tonelada", "t", (0, 1, 0), 1000.0),
        # Force (base unit: N = kg·m/s2)
        Unit("newton", "N", (1, 1, -2), 1.0),
        Unit("kilonewton", "kN", (1, 1, -2), 1000.0),
        # Pressure (base unit: Pa = kg/(m·s2))
        Unit("pascal", "Pa", (-1, 1, -2), 1.0),
        Unit("kilopascal", "kPa", (-1, 1, -2), 1000.0),
        Unit("megapascal", "MPa", (-1, 1, -2), 1.0e6),
        # Power (base unit: W = kg·m2/s3)
        Unit("watt", "W", (2, 1, -3), 1.0),
        Unit("kilowatt", "kW", (2, 1, -3), 1000.0),
        # Electrical units get dedicated pseudo-dimensions so that V, A and Hz
        # are never mutually convertible (dangerous implicit conversion).
        Unit("voltio", "V", (2, 1, -4), 1.0),
        Unit("amperio", "A", (0, 1, -4), 1.0),
        Unit("hertz", "Hz", (0, 0, -5), 1.0),
        # Flow (base unit: m3/s)
        Unit("litro por segundo", "L/s", (3, 0, -1), 0.001),
        Unit("metro cúbico por hora", "m3/h", (3, 0, -1), 1.0 / 3600.0),
    ]
    for unit in registered:
        reg.register(unit)
    return reg


DEFAULT_REGISTRY = _build_default_registry()

__all__ = ["Unit", "UnitRegistry", "DEFAULT_REGISTRY", "Dimension", "ZERO"]
