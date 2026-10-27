"""Sanitary Engine (spec section 28).

Sistemas: ColdWater, HotWater, SanitaryDrainage, Stormwater, Pumping,
Storage. Funciones del spec: caudal, presión, pendiente, diámetro,
pérdidas, bombeo.

Métodos (documentados y configurables por datos):
  - Caudal de diseño: q_n por aparato (tabla) × coeficiente de
    simultaneidad k = min(1, 1,8/√n) sobre el número de aparatos
    servidos (método clásico de simultaneidad). Los Fixture Units de
    Hunter viajan como dato informativo del nodo.
  - Pérdidas (tubería a presión): Hazen-Williams
        J (m/m) = 10.67 · Q^1.852 / (C^1.852 · D^4.87)
    con Q en m³/s y D en m; accesorios como % adicional del tramo.
  - Diámetro: menor DN comercial con velocidad dentro de límites
    (0,6–2,0 m/s recomendado en impulsión/gravedad de red interior).
  - Pendiente (gravedad): tabla mínima por diámetro (IPC 704.1 aprox.)
    y capacidad por Manning con lámina al 50 %.
  - Presión/bombeo: TDH = altura estática + pérdidas del camino peor +
    presión residual requerida; P_hidr = ρ·g·Q·H, P_elec = P_hidr/η.
  - Almacenamiento: V = dotación × personas × autonomía (o caudal × horas).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.errors import CalculationError

GRAVITY_ACCEL = 9.81                    # m/s²
WATER_DENSITY = 1000.0                  # kg/m³

# -- Caudales nominales por aparato (L/s), valores interiores clásicos ------
FIXTURE_FLOW_LS: Dict[str, float] = {
    "WC": 0.10, "LAVATORY": 0.10, "BIDET": 0.10, "SHOWER": 0.15,
    "BATHTUB": 0.20, "SINK": 0.15, "KITCHEN_SINK": 0.15, "LAUNDRY": 0.20,
    "HOSE_BIBB": 0.30, "DISHWASHER": 0.15, "WASHER": 0.20, "FOUNTAIN": 0.05,
}

# Fixture Units de Hunter por aparato (informativo, spec 28).
FIXTURE_UNITS: Dict[str, float] = {
    "WC": 3.0, "LAVATORY": 1.0, "BIDET": 2.0, "SHOWER": 2.0,
    "BATHTUB": 3.0, "SINK": 2.0, "KITCHEN_SINK": 2.0, "LAUNDRY": 3.0,
    "HOSE_BIBB": 2.5, "DISHWASHER": 2.0, "WASHER": 3.0, "FOUNTAIN": 0.5,
}

SIMULTANEITY_K = 1.8                    # k = min(1, 1.8/√n)

# -- Diámetros comerciales (mm interiores nominales) --------------------------
PRESSURE_DN_MM: Tuple[float, ...] = (13.0, 19.0, 25.0, 32.0, 38.0, 50.0,
                                     63.0, 75.0, 90.0, 110.0, 125.0, 160.0)
DRAIN_DN_MM: Tuple[float, ...] = (50.0, 75.0, 100.0, 125.0, 150.0, 200.0, 250.0, 300.0)

HAZEN_WILLIAMS_C: Dict[str, float] = {
    "PVC": 140.0, "PE": 140.0, "PPR": 140.0, "COPPER": 130.0,
    "STEEL": 100.0, "GALVANIZED": 120.0, "": 130.0,
}
MANNING_N: Dict[str, float] = {
    "PVC": 0.011, "PE": 0.011, "CONCRETE": 0.013, "": 0.012,
}

# Pendiente mínima por diámetro (%, IPC tabla 704.1 aproximada).
MIN_SLOPE_PCT: Dict[float, float] = {
    50.0: 2.08, 75.0: 1.04, 100.0: 1.04, 125.0: 0.52, 150.0: 0.52,
    200.0: 0.52, 250.0: 0.40, 300.0: 0.33,
}

VELOCITY_MIN_MS = 0.60
VELOCITY_MAX_MS = 2.00
DRAIN_FILL_RATIO = 0.50                 # lámina de diseño en ramales
FITTINGS_ALLOWANCE_PCT = 30.0           # accesorios como % de la longitud
REQUIRED_RESIDUAL_M = 5.0               # presión residual mínima en el aparato (m.c.a.)
PUMP_EFFICIENCY = 0.70


def simultaneity(count: int) -> float:
    """Coeficiente de simultaneidad k = min(1, 1,8/√n)."""
    if count <= 0:
        return 0.0
    return min(1.0, SIMULTANEITY_K / math.sqrt(count))


def design_flow_ls(flows_ls: List[float]) -> float:
    """Caudal de diseño a partir de caudales nominales servidos (caudal)."""
    served = [f for f in flows_ls if f > 0]
    if not served:
        return 0.0
    k = simultaneity(len(served))
    return round(k * sum(served), 4)


def hazen_williams_j(q_ls: float, diameter_mm: float, material: str = "PVC") -> float:
    """Pérdida de carga unitaria J (m/m) por Hazen-Williams (pérdidas)."""
    if q_ls <= 0 or diameter_mm <= 0:
        return 0.0
    c = HAZEN_WILLIAMS_C.get(material.upper(), HAZEN_WILLIAMS_C[""])
    q_m3s = q_ls / 1000.0
    d_m = diameter_mm / 1000.0
    return 10.67 * (q_m3s ** 1.852) / ((c ** 1.852) * (d_m ** 4.87))


def segment_head_loss_m(q_ls: float, diameter_mm: float, length_m: float,
                        material: str = "PVC",
                        fittings_pct: float = FITTINGS_ALLOWANCE_PCT) -> float:
    """Pérdida de carga del tramo con accesorios incluidos (pérdidas)."""
    j = hazen_williams_j(q_ls, diameter_mm, material)
    return j * length_m * (1.0 + fittings_pct / 100.0)


def velocity_ms(q_ls: float, diameter_mm: float) -> float:
    if diameter_mm <= 0:
        return 0.0
    area_m2 = math.pi * (diameter_mm / 1000.0) ** 2 / 4.0
    return (q_ls / 1000.0) / area_m2


def select_pressure_diameter(q_ls: float, material: str = "PVC",
                             v_max: float = VELOCITY_MAX_MS,
                             v_min: float = VELOCITY_MIN_MS,
                             catalog: Tuple[float, ...] = PRESSURE_DN_MM
                             ) -> Tuple[float, float]:
    """Menor DN comercial con velocidad ≤ v_max (diámetro).

    Devuelve (diameter_mm, velocity_ms). Advertencia de velocidad baja la
    emite el servicio si v < v_min.
    """
    if q_ls <= 0:
        raise CalculationError(
            message="No se puede dimensionar tubería con caudal nulo",
            code="ARQ-SAN-001")
    for dn in catalog:
        v = velocity_ms(q_ls, dn)
        if v <= v_max + 1e-9:
            return dn, v
    raise CalculationError(
        message=f"El caudal {q_ls:.2f} L/s no cabe en el catálogo de diámetros",
        code="ARQ-SAN-002",
        context={"q_ls": q_ls},
        suggested_action="Divida la red en ramales menores o use diámetros especiales.")


def min_slope_pct(diameter_mm: float) -> float:
    """Pendiente mínima normativa por diámetro (pendiente)."""
    return MIN_SLOPE_PCT.get(float(diameter_mm), MIN_SLOPE_PCT[max(MIN_SLOPE_PCT)])


def manning_capacity_ls(diameter_mm: float, slope_pct: float,
                        material: str = "PVC", fill: float = DRAIN_FILL_RATIO) -> float:
    """Capacidad en gravedad por Manning con lámina parcial (pendiente)."""
    if diameter_mm <= 0 or slope_pct <= 0:
        return 0.0
    n = MANNING_N.get(material.upper(), MANNING_N[""])
    d_m = diameter_mm / 1000.0
    s = slope_pct / 100.0
    theta = 2.0 * math.acos(1.0 - 2.0 * fill)      # ángulo del nivel de agua
    area = (d_m ** 2 / 8.0) * (theta - math.sin(theta))
    perimeter = d_m * theta / 2.0
    hydraulic_radius = area / perimeter if perimeter > 0 else 0.0
    return (1.0 / n) * area * (hydraulic_radius ** (2.0 / 3.0)) * math.sqrt(s) * 1000.0


def select_drain_diameter(q_ls: float, material: str = "PVC",
                          catalog: Tuple[float, ...] = DRAIN_DN_MM
                          ) -> Tuple[float, float, float]:
    """Menor DN con capacidad ≥ caudal a lámina 50 % (diámetro/pendiente).

    Devuelve (diameter_mm, slope_pct, capacity_ls).
    """
    if q_ls <= 0:
        raise CalculationError(
            message="No se puede dimensionar desagüe con caudal nulo",
            code="ARQ-SAN-003")
    for dn in catalog:
        slope = min_slope_pct(dn)
        capacity = manning_capacity_ls(dn, slope, material)
        if capacity >= q_ls - 1e-9:
            return dn, slope, capacity
    largest = catalog[-1]
    return largest, min_slope_pct(largest), manning_capacity_ls(largest, min_slope_pct(largest), material)


@dataclass
class PumpResult:
    """Dimensionamiento de bombeo (bombeo)."""

    static_head_m: float = 0.0
    friction_head_m: float = 0.0
    residual_m: float = REQUIRED_RESIDUAL_M
    tdh_m: float = 0.0
    flow_ls: float = 0.0
    hydraulic_kw: float = 0.0
    electric_kw: float = 0.0

    def to_dict(self) -> dict:
        return {
            "static_head_m": round(self.static_head_m, 2),
            "friction_head_m": round(self.friction_head_m, 2),
            "residual_m": round(self.residual_m, 2),
            "tdh_m": round(self.tdh_m, 2),
            "flow_ls": round(self.flow_ls, 3),
            "hydraulic_kw": round(self.hydraulic_kw, 3),
            "electric_kw": round(self.electric_kw, 3),
        }


def size_pump(flow_ls: float, static_head_m: float, friction_head_m: float,
              residual_m: float = REQUIRED_RESIDUAL_M,
              efficiency: float = PUMP_EFFICIENCY) -> PumpResult:
    """Bombeo: TDH y potencias (bombeo)."""
    if efficiency <= 0 or efficiency > 1:
        raise CalculationError(
            message="El rendimiento de la bomba debe estar entre 0 y 1",
            code="ARQ-SAN-004")
    tdh = static_head_m + friction_head_m + residual_m
    q_m3s = flow_ls / 1000.0
    hydraulic_kw = WATER_DENSITY * GRAVITY_ACCEL * q_m3s * tdh / 1000.0
    return PumpResult(
        static_head_m=round(static_head_m, 3),
        friction_head_m=round(friction_head_m, 3),
        residual_m=residual_m, tdh_m=round(tdh, 3), flow_ls=flow_ls,
        hydraulic_kw=round(hydraulic_kw, 3),
        electric_kw=round(hydraulic_kw / efficiency, 3),
    )


def tank_volume_ls(liters_per_person_day: float, persons: int,
                   autonomy_days: float) -> float:
    """Almacenamiento: V = dotación × personas × autonomía (almacenamiento)."""
    if persons < 0 or autonomy_days < 0:
        raise CalculationError(
            message="Personas y autonomía no pueden ser negativas",
            code="ARQ-SAN-005")
    return round(liters_per_person_day * persons * autonomy_days, 1)


__all__ = [
    "PumpResult", "FIXTURE_FLOW_LS", "FIXTURE_UNITS", "PRESSURE_DN_MM",
    "DRAIN_DN_MM", "MIN_SLOPE_PCT", "VELOCITY_MIN_MS", "VELOCITY_MAX_MS",
    "simultaneity", "design_flow_ls", "hazen_williams_j",
    "segment_head_loss_m", "velocity_ms", "select_pressure_diameter",
    "min_slope_pct", "manning_capacity_ls", "select_drain_diameter",
    "size_pump", "tank_volume_ls",
]
