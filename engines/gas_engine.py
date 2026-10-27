"""Gas Engine (spec section 31).

Instalación de gas integrada como plugin del sistema de instalaciones:
usa el modelo genérico de redes (NODE SOURCE / METER / REGULATOR / VALVE /
APPLIANCE, SEGMENT PIPE) y añade el cálculo y las validaciones del spec.

Métodos (documentados y configurables por datos):
  - Caudal de gas: q (m3/h) = P (kW) / (PCI (kWh/m3) · rendimiento),
    con PCI del gas natural 10,6 kWh/m3.
  - Unidades de consumo: UC = P (kW) / 2,33 kW por UC (criterio clásico
    de la práctica española; informativo para plantillas).
  - Diámetro: Darcy-Weisbach con factor de fricción f constante de
    tubería lisa comercial y densidad ρ = S · 1,225 kg/m3:
        ΔP (Pa) = f · (L/D) · (ρ · v2 / 2) · (1 + accesorios %)
    Se elige el menor DN comercial cuyo ΔP ≤ presupuesto de pérdida de
    carga de la instalación (20 mbar de servicio → 5 kPa por defecto).
  - Velocidad: v = Q/A con límite superior por ruido/golpe de ariete.

Validaciones del spec (sección 31) implementadas en el servicio:
  diámetros, recorridos, válvulas, ventilación, separación y puntos de
  consumo (ver InstallationsService.validate_gas).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from core.errors import CalculationError

# -- Datos de combustible ---------------------------------------------------------
PCI_NATURAL_GAS_KWH_M3 = 10.6           # poder calorífico inferior gas natural
GAS_SPECIFIC_GRAVITY = 0.65             # S = ρ_gas / ρ_aire
AIR_DENSITY = 1.225                     # kg/m3 a nivel del mar
GAS_DENSITY = GAS_SPECIFIC_GRAVITY * AIR_DENSITY

# -- Diámetros comerciales (mm interiores nominales) -------------------------------
GAS_DN_MM: Tuple[float, ...] = (15.0, 20.0, 25.0, 32.0, 40.0, 50.0, 65.0, 80.0, 100.0)

GAS_FRICTION_F = 0.025                  # tubería lisa cobre/acero comercial
FITTINGS_ALLOWANCE_PCT = 25.0           # accesorios como % de la longitud
DP_BUDGET_PA = 5000.0                   # 5 kPa de pérdida admisible (servicio 20 mbar)
MAX_GAS_VELOCITY_MS = 5.0               # límite por ruido/impulsos
MIN_GAS_VELOCITY_MS = 0.5               # evita estancamiento/suciedad

KW_PER_UC = 2.33                        # 1 UC ≈ 2000 kcal/h ≈ 2,33 kW

# -- Validaciones (spec 31) ----------------------------------------------------------
MAX_RUN_M = 50.0                        # recorrido máximo sin junta/regulación extra
VENT_AREA_RATIO = 1.0 / 50.0            # ventilación ≥ 1/50 del suelo del local
VENT_MIN_M2 = 0.02                      # y nunca menor de 0,02 m2
SEPARATION_M = 0.10                     # separación mínima gas ↔ eléctrico


def gas_flow_m3h(power_kw: float, pci_kwh_m3: float = PCI_NATURAL_GAS_KWH_M3,
                 efficiency: float = 1.0) -> float:
    """Caudal de gas de un aparato: q = P/(PCI·η) (puntos de consumo)."""
    if power_kw < 0:
        raise CalculationError(
            message="La potencia del aparato no puede ser negativa",
            code="ARQ-GAS-001", context={"power_kw": power_kw})
    if pci_kwh_m3 <= 0:
        raise CalculationError(
            message="El PCI del gas debe ser positivo",
            code="ARQ-GAS-002", context={"pci_kwh_m3": pci_kwh_m3})
    if efficiency <= 0 or efficiency > 1:
        raise CalculationError(
            message="El rendimiento del aparato debe estar entre 0 y 1",
            code="ARQ-GAS-003", context={"efficiency": efficiency})
    return round(power_kw / (pci_kwh_m3 * efficiency), 4)


def consumption_units(power_kw: float) -> float:
    """Unidades de consumo UC = kW/2,33 (puntos de consumo, informativo)."""
    return round(power_kw / KW_PER_UC, 2)


def velocity_ms(q_m3h: float, diameter_mm: float) -> float:
    """Velocidad del gas en la tubería (diámetros)."""
    if diameter_mm <= 0:
        return 0.0
    area_m2 = math.pi * (diameter_mm / 1000.0) ** 2 / 4.0
    return (q_m3h / 3600.0) / area_m2


def segment_dp_pa(q_m3h: float, diameter_mm: float, length_m: float,
                  s: float = GAS_SPECIFIC_GRAVITY, f: float = GAS_FRICTION_F,
                  fittings_pct: float = FITTINGS_ALLOWANCE_PCT) -> float:
    """Pérdida de carga del tramo por Darcy-Weisbach (diámetros)."""
    if q_m3h <= 0 or diameter_mm <= 0 or length_m <= 0:
        return 0.0
    d_m = diameter_mm / 1000.0
    v = (q_m3h / 3600.0) / (math.pi * d_m ** 2 / 4.0)
    rho = s * AIR_DENSITY
    dp = f * (length_m / d_m) * (rho * v ** 2 / 2.0)
    return dp * (1.0 + fittings_pct / 100.0)


def select_gas_diameter(q_m3h: float, length_m: float,
                        dp_budget_pa: float = DP_BUDGET_PA,
                        catalog: Tuple[float, ...] = GAS_DN_MM,
                        s: float = GAS_SPECIFIC_GRAVITY) -> Tuple[float, float, float]:
    """Menor DN comercial con ΔP ≤ presupuesto y v ≤ límite (diámetros).

    Devuelve (diameter_mm, dp_pa, velocity_ms).
    """
    if q_m3h <= 0:
        raise CalculationError(
            message="No se puede dimensionar tubería de gas con caudal nulo",
            code="ARQ-GAS-004")
    if dp_budget_pa <= 0:
        raise CalculationError(
            message="El presupuesto de pérdida de carga debe ser positivo",
            code="ARQ-GAS-005", context={"dp_budget_pa": dp_budget_pa})
    for dn in catalog:
        dp = segment_dp_pa(q_m3h, dn, length_m, s=s)
        v = velocity_ms(q_m3h, dn)
        if dp <= dp_budget_pa - 1e-9 and v <= MAX_GAS_VELOCITY_MS + 1e-9:
            return dn, dp, v
    largest = catalog[-1]
    return largest, segment_dp_pa(q_m3h, largest, length_m, s=s), \
        velocity_ms(q_m3h, largest)


def required_vent_area_m2(room_area_m2: float) -> float:
    """Superficie de ventilación exigida al local del aparato (ventilación)."""
    if room_area_m2 < 0:
        raise CalculationError(
            message="El área del local no puede ser negativa",
            code="ARQ-GAS-006", context={"room_area_m2": room_area_m2})
    return max(VENT_MIN_M2, room_area_m2 * VENT_AREA_RATIO)


@dataclass
class GasSegmentCheck:
    """Resultado del chequeo de un tramo de gas (diámetros/recorridos)."""

    segment: str = ""
    from_node: str = ""
    to_node: str = ""
    uc_served: float = 0.0
    q_m3h: float = 0.0
    length_m: float = 0.0
    diameter_mm: float = 0.0
    diameter_suggested_mm: float = 0.0
    dp_pa: float = 0.0
    velocity_ms: float = 0.0
    findings: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "segment": self.segment, "from": self.from_node, "to": self.to_node,
            "uc_served": round(self.uc_served, 2), "q_m3h": round(self.q_m3h, 3),
            "length_m": round(self.length_m, 2),
            "diameter_mm": round(self.diameter_mm, 1),
            "diameter_suggested_mm": round(self.diameter_suggested_mm, 1),
            "dp_pa": round(self.dp_pa, 1), "velocity_ms": round(self.velocity_ms, 2),
            "findings": list(self.findings),
        }


__all__ = [
    "GasSegmentCheck", "PCI_NATURAL_GAS_KWH_M3", "GAS_SPECIFIC_GRAVITY",
    "GAS_DENSITY", "GAS_DN_MM", "GAS_FRICTION_F", "FITTINGS_ALLOWANCE_PCT",
    "DP_BUDGET_PA", "MAX_GAS_VELOCITY_MS", "MIN_GAS_VELOCITY_MS", "KW_PER_UC",
    "MAX_RUN_M", "VENT_AREA_RATIO", "VENT_MIN_M2", "SEPARATION_M",
    "gas_flow_m3h", "consumption_units", "velocity_ms", "segment_dp_pa",
    "select_gas_diameter", "required_vent_area_m2",
]
