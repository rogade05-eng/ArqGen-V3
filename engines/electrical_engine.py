"""Electrical Engine (spec section 27).

Cálculos parametrizables del spec 27:

    Potencia / Corriente / Factor de potencia / Demanda
    Caída de tensión / Protección / Sección / Canalización / Balance

Métodos y valores por defecto (todos configurables por datos):
  - Corriente: I = P / (V·pf) monofásica; I = P / (√3·V·pf) trifásica.
  - Demanda: factores por tipo de circuito (datos en DEMAND_FACTORS).
  - Caída de tensión: ΔV = 2·ρ·L·I / S (1φ) ó √3·ρ·L·I / S (3φ),
    ρ cobre 0,0175 Ω·mm²/m (1,75 % de la norma IEC a 20 °C ajustado).
  - Protección: siguiente valor normalizado IEC (BREAKER_RATINGS) ≥ I.
  - Sección: menor sección normalizada que cumple
      Ib ≤ In ≤ Iz (ampacidad IEC 60364-5-52 método C, Cu/PVC)
      y caída de tensión ≤ máximo (3 % ramal, 5 % total por defecto).
  - Canalización: sección de conducto (área útil) según número de
    conductores y su diámetro exterior nominal (tabla A.52 del anexo A
    IEC 60364-5-52 aproximada: 40 % de llenado).
  - Balance: reparto de circuitos por fase y desbalance
    (max−min)/media.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.errors import CalculationError

# -- constantes normalizadas (datos, editables) ------------------------------
RESISTIVITY_OHM_MM2_M: Dict[str, float] = {
    "CU": 0.0175,   # cobre a 20 °C, con corrección de temperatura incluida
    "AL": 0.0283,   # aluminio
}

BREAKER_RATINGS: Tuple[float, ...] = (
    6.0, 10.0, 16.0, 20.0, 25.0, 32.0, 40.0, 50.0, 63.0, 80.0, 100.0,
    125.0, 160.0, 200.0, 250.0,
)

# Ampacidad aproximada IEC 60364-5-52 tabla B.52.4 — método C, PVC, Cu,
# 2 conductores cargados, 30 °C ambiente.
AMPACITY_CU: Dict[float, float] = {
    1.5: 19.5, 2.5: 26.0, 4.0: 35.0, 6.0: 46.0, 10.0: 63.0, 16.0: 85.0,
    25.0: 112.0, 35.0: 138.0, 50.0: 168.0, 70.0: 213.0, 95.0: 258.0,
    120.0: 299.0, 150.0: 344.0, 185.0: 392.0, 240.0: 461.0,
}
AMPACITY_AL: Dict[float, float] = {
    2.5: 20.0, 4.0: 27.0, 6.0: 35.0, 10.0: 47.0, 16.0: 63.0, 25.0: 82.0,
    35.0: 101.0, 50.0: 123.0, 70.0: 155.0, 95.0: 192.0, 120.0: 221.0,
    150.0: 253.0, 185.0: 288.0, 240.0: 341.0,
}

STANDARD_SECTIONS: Tuple[float, ...] = tuple(sorted(AMPACITY_CU))

# Conductores por tramo según el sistema (L + N + PE por defecto 1φ; 3φ + N + PE).
CONDUCTORS_1PH = 3      # L, N, PE
CONDUCTORS_3PH = 5      # 3L, N, PE

# Factores de demanda por tipo de circuito (orientativos, configurables).
DEMAND_FACTORS: Dict[str, float] = {
    "LIGHTING": 1.00,
    "POWER": 1.00,
    "KITCHEN": 0.80,
    "CLIMATE": 1.00,
    "MOTOR": 1.25,          # arranque de motor: sobredimensiona protección
    "GENERAL": 1.00,
}

# Diámetro exterior nominal aproximado por sección (mm), aislamiento PVC.
OUTER_DIAMETER_MM: Dict[float, float] = {
    1.5: 3.0, 2.5: 3.6, 4.0: 4.1, 6.0: 4.6, 10.0: 5.6, 16.0: 6.5,
    25.0: 8.4, 35.0: 9.6, 50.0: 11.4, 70.0: 13.2, 95.0: 15.2,
    120.0: 16.8, 150.0: 18.6, 185.0: 20.4, 240.0: 22.8,
}

CONDUIT_FILL = 0.40     # llenado máximo de canalización (IEC annexe A)
CONDUIT_SIZES_MM: Tuple[float, ...] = (16.0, 20.0, 25.0, 32.0, 40.0, 50.0, 63.0, 75.0, 90.0, 110.0)

VD_LIMIT_BRANCH_PCT = 3.0
VD_LIMIT_TOTAL_PCT = 5.0


@dataclass
class LoadSummary:
    """Connected and demand load of a circuit (spec 27: demanda)."""

    connected_w: float = 0.0
    demand_w: float = 0.0
    demand_factor: float = 1.0
    devices: int = 0
    current_a: float = 0.0

    def to_dict(self) -> dict:
        return {
            "connected_w": round(self.connected_w, 2),
            "demand_w": round(self.demand_w, 2),
            "demand_factor": round(self.demand_factor, 3),
            "devices": self.devices,
            "current_a": round(self.current_a, 2),
        }


@dataclass
class CircuitCheck:
    """Full electrical check of one circuit radial (spec 27)."""

    circuit_code: str = ""
    circuit_kind: str = "POWER"
    voltage: float = 220.0
    phases: int = 1
    power_factor: float = 1.0
    load: LoadSummary = field(default_factory=LoadSummary)
    breaker_a: float = 0.0
    breaker_standard: float = 0.0
    section_mm2: float = 0.0
    ampacity_a: float = 0.0
    worst_vd_pct: float = 0.0
    conductors: int = CONDUCTORS_1PH
    conduit_mm: float = 0.0
    findings: List[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict:
        return {
            "circuit": self.circuit_code, "kind": self.circuit_kind,
            "voltage": self.voltage, "phases": self.phases,
            "power_factor": self.power_factor,
            "load": self.load.to_dict(),
            "breaker_a": round(self.breaker_a, 1),
            "breaker_standard": round(self.breaker_standard, 1),
            "section_mm2": round(self.section_mm2, 2),
            "ampacity_a": round(self.ampacity_a, 1),
            "worst_vd_pct": round(self.worst_vd_pct, 2),
            "conductors": self.conductors,
            "conduit_mm": round(self.conduit_mm, 1),
            "findings": self.findings, "ok": self.ok,
        }


def current_a(power_w: float, voltage: float, power_factor: float = 1.0,
              phases: int = 1) -> float:
    """Corriente de línea (spec 27)."""
    if power_factor <= 0 or voltage <= 0 or phases not in (1, 3):
        raise CalculationError(
            message="Parámetros eléctricos inválidos (V > 0, pf > 0, fases 1 o 3)",
            code="ARQ-ELE-001",
            context={"voltage": voltage, "pf": power_factor, "phases": phases},
        )
    if phases == 1:
        return power_w / (voltage * power_factor)
    return power_w / (math.sqrt(3.0) * voltage * power_factor)


def demand_power(connected_w: float, circuit_kind: str = "POWER",
                 factor_override: Optional[float] = None) -> Tuple[float, float]:
    """Potencia de demanda; devuelve (demanda_w, factor)."""
    factor = factor_override if factor_override is not None \
        else DEMAND_FACTORS.get(circuit_kind, 1.0)
    return connected_w * factor, factor


def voltage_drop_pct(section_mm2: float, length_m: float, current: float,
                     voltage: float, phases: int = 1, material: str = "CU") -> float:
    """Caída de tensión en % (spec 27)."""
    if section_mm2 <= 0 or voltage <= 0:
        raise CalculationError(
            message="Sección y tensión deben ser positivas para calcular la caída de tensión",
            code="ARQ-ELE-002",
        )
    rho = RESISTIVITY_OHM_MM2_M.get(material.upper(), RESISTIVITY_OHM_MM2_M["CU"])
    k = 2.0 if phases == 1 else math.sqrt(3.0)
    delta_v = k * rho * length_m * current / section_mm2
    return delta_v / voltage * 100.0


def select_breaker(design_current_a: float) -> float:
    """Menor interruptor normalizado ≥ corriente de diseño (spec 27)."""
    for rating in BREAKER_RATINGS:
        if rating >= design_current_a - 1e-9:
            return rating
    raise CalculationError(
        message=f"No hay interruptor normalizado para {design_current_a:.1f} A "
                f"(máximo {BREAKER_RATINGS[-1]:.0f} A)",
        code="ARQ-ELE-003",
        context={"current_a": design_current_a},
        suggested_action="Divida la carga en varios circuitos.",
    )


def select_section(design_current_a: float, length_m: float, voltage: float,
                   phases: int = 1, max_vd_pct: float = VD_LIMIT_BRANCH_PCT,
                   material: str = "CU",
                   breaker_a: Optional[float] = None) -> Tuple[float, float]:
    """Sección mínima que cumple Ib ≤ In ≤ Iz y caída de tensión.

    Devuelve (sección_mm2, ampacidad_a). Coordina con el interruptor:
    la ampacidad debe cubrir la protección normalizada.
    """
    table = AMPACITY_AL if material.upper() == "AL" else AMPACITY_CU
    required = breaker_a if breaker_a else design_current_a
    for section in STANDARD_SECTIONS:
        ampacity = table[section]
        if ampacity < required - 1e-9:
            continue
        vd = voltage_drop_pct(section, length_m, design_current_a, voltage, phases, material)
        if vd <= max_vd_pct + 1e-9:
            return section, ampacity
    raise CalculationError(
        message=f"No se cumple caída de tensión ({max_vd_pct:.1f} %) con las secciones "
                "normalizadas disponibles",
        code="ARQ-ELE-004",
        context={"current_a": round(design_current_a, 2), "length_m": round(length_m, 2)},
        suggested_action="Aumente la tensión, reduzca la longitud o suba el límite de caída.",
    )


def select_conduit(section_mm2: float, conductors: int) -> float:
    """Diámetro comercial de conducto con llenado ≤ 40 % (canalización, spec 27)."""
    outer = OUTER_DIAMETER_MM.get(section_mm2)
    if outer is None:
        raise CalculationError(
            message=f"Sección sin diámetro exterior catalogado: {section_mm2} mm²",
            code="ARQ-ELE-005")
    cable_area = math.pi * (outer / 2.0) ** 2 * conductors
    for size in CONDUIT_SIZES_MM:
        inner_area = math.pi * (size * 0.85 / 2.0) ** 2   # pared aproximada 15 %
        if inner_area * CONDUIT_FILL >= cable_area:
            return size
    raise CalculationError(
        message="No hay conducto normalizado suficiente para el haz de conductores",
        code="ARQ-ELE-006")


def phase_balance(phase_loads_w: Dict[int, float]) -> Dict[str, float]:
    """Balance de fases (spec 27): reparto y desbalance (max−min)/media."""
    loads = {phase: max(value, 0.0) for phase, value in phase_loads_w.items()}
    values = list(loads.values())
    if not values or sum(values) <= 0:
        return {"imbalance_pct": 0.0, "max_phase_w": 0.0, "min_phase_w": 0.0}
    imbalance = (max(values) - min(values)) / (sum(values) / len(values)) * 100.0
    return {
        "imbalance_pct": round(imbalance, 2),
        "max_phase_w": round(max(values), 2),
        "min_phase_w": round(min(values), 2),
    }


__all__ = [
    "LoadSummary", "CircuitCheck",
    "current_a", "demand_power", "voltage_drop_pct", "select_breaker",
    "select_section", "select_conduit", "phase_balance",
    "RESISTIVITY_OHM_MM2_M", "BREAKER_RATINGS", "AMPACITY_CU", "AMPACITY_AL",
    "STANDARD_SECTIONS", "DEMAND_FACTORS", "CONDUCTORS_1PH", "CONDUCTORS_3PH",
    "VD_LIMIT_BRANCH_PCT", "VD_LIMIT_TOTAL_PCT",
]
