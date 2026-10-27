"""Quantity: every magnitude carries its unit (spec section 11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from core.errors import UnitError
from core.units.registry import DEFAULT_REGISTRY, Unit, UnitRegistry


@dataclass(frozen=True)
class Quantity:
    """A value with an explicit unit. No implicit conversions allowed."""

    value: float
    unit_symbol: str
    registry: UnitRegistry = DEFAULT_REGISTRY

    def __post_init__(self) -> None:
        try:
            self.registry.get(self.unit_symbol)
        except UnitError:
            raise
        if not isinstance(self.value, (int, float)):
            raise UnitError(
                message=f"El valor de una Quantity debe ser numérico, recibido: {type(self.value).__name__}",
                code="ARQ-UNI-004",
            )

    # -- conversions ---------------------------------------------------
    def to(self, target_unit: str) -> "Quantity":
        converted = self.registry.convert(self.value, self.unit_symbol, target_unit)
        return Quantity(round(converted, 10), target_unit, self.registry)

    # -- arithmetic ----------------------------------------------------
    def _check(self, other: "Quantity", op: str) -> None:
        if not isinstance(other, Quantity):
            raise UnitError(
                message=f"No se puede operar Quantity {op} {type(other).__name__}",
                code="ARQ-UNI-005",
            )
        if self.registry.get(self.unit_symbol).dimension != self.registry.get(other.unit_symbol).dimension:
            raise UnitError(
                message=(
                    f"Dimensiones incompatibles: {self.unit_symbol} {op} {other.unit_symbol}"
                ),
                code="ARQ-UNI-006",
                context={"left": self.unit_symbol, "right": other.unit_symbol, "op": op},
                suggested_action="Convierta ambas cantidades a la misma unidad antes de operar.",
            )

    def __add__(self, other: Union["Quantity", float]) -> "Quantity":
        if isinstance(other, (int, float)):
            other = Quantity(float(other), self.unit_symbol, self.registry)
        self._check(other, "+")
        return Quantity(self.value + other.value, self.unit_symbol, self.registry)

    def __sub__(self, other: Union["Quantity", float]) -> "Quantity":
        if isinstance(other, (int, float)):
            other = Quantity(float(other), self.unit_symbol, self.registry)
        self._check(other, "-")
        return Quantity(self.value - other.value, self.unit_symbol, self.registry)

    def __mul__(self, factor: Union[float, int]) -> "Quantity":
        if not isinstance(factor, (int, float)):
            raise UnitError(
                message="Quantity solo multiplica por escalares; use el motor de fórmulas para magnitudes compuestas",
                code="ARQ-UNI-007",
            )
        return Quantity(self.value * factor, self.unit_symbol, self.registry)

    def __truediv__(self, divisor: Union[float, int]) -> "Quantity":
        if not isinstance(divisor, (int, float)) or divisor == 0:
            raise UnitError(
                message="Quantity solo divide entre escalares distintos de cero",
                code="ARQ-UNI-008",
            )
        return Quantity(self.value / divisor, self.unit_symbol, self.registry)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.value:g} {self.unit_symbol}"


__all__ = ["Quantity"]
