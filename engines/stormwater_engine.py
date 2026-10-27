"""Stormwater Engine (spec section 30).

Sistema pluvial: captación, pendientes, bajantes, colectores,
almacenamiento y evacuación. Funciona sobre el modelo genérico de redes
(NODE ROOF_DRAIN / GUTTER / TANK / OUTFALL, SEGMENT DRAIN_PIPE) y por eso
no define entidades propias.

Métodos (documentados y configurables por datos):
  - Captación: método racional
        Q (L/s) = C · i (mm/h) · A (m2) / 3600
    con C el coeficiente de escorrentía de la superficie e i la
    intensidad de diseño de la lluvia local.
  - Canal (canalón/cuneta): Manning de canal rectangular abierto
        Q = (1/n) · A · R^(2/3) · S^(1/2)
    a lámina completa del canalón (hipótesis conservadora de borde libre).
  - Bajante vertical: tabla de capacidad hidráulica por diámetro
    (bajante ~1/3 de sección llena, valores clásicos de pluvial).
  - Colector horizontal: Manning con lámina al 50 % — reutiliza el motor
    sanitario (engines.sanitary_engine) para pendientes y capacidad.
  - Almacenamiento (detención): V (L) = Q (L/s) · t_retención (s).
  - Evacuación: la capacidad del tramo de salida debe superar el caudal
    aforado aguas arriba (validado por el servicio).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from core.errors import CalculationError

# -- Captación (método racional) ------------------------------------------------
RUNOFF_COEFFICIENTS: Dict[str, float] = {
    "ROOF": 0.90,        # cubierta impermeable
    "CONCRETE": 0.85,    # hormigón/asfalto
    "PAVING": 0.85,
    "GRAVEL": 0.65,
    "GREEN_ROOF": 0.40,
    "GRASS": 0.25,
    "": 0.80,            # valor por defecto prudente
}

DEFAULT_INTENSITY_MMH = 100.0          # lluvia de diseño local

# -- Bajantes verticales (capacidad hidráulica en L/s) ---------------------------
# Valores clásicos de pluviales para bajante a ~1/3 de sección llena.
DOWNPIPE_CAPACITY_LS: Dict[float, float] = {
    50.0: 1.5, 75.0: 4.0, 100.0: 8.0, 125.0: 12.5, 150.0: 18.0,
}

# -- Canalones (catálogo comercial de canal rectangular, mm) ---------------------
GUTTER_WIDTH_MM: Tuple[float, ...] = (100.0, 125.0, 150.0, 200.0, 250.0, 300.0, 400.0)
GUTTER_MANNING_N = 0.012               # metal galvanizado / PVC liso
MIN_GUTTER_SLOPE_PCT = 0.50            # pendiente mínima de canalón

# -- Almacenamiento ---------------------------------------------------------------
DEFAULT_RETENTION_MIN = 15.0           # minutos de retención de diseño


def runoff_coefficient(surface: str) -> float:
    """Coeficiente de escorrentía de la superficie (captación)."""
    return RUNOFF_COEFFICIENTS.get(surface.upper(), RUNOFF_COEFFICIENTS[""])


def runoff_ls(area_m2: float, intensity_mmh: float = DEFAULT_INTENSITY_MMH,
              coeff: float = 0.80) -> float:
    """Captación por método racional: Q = C·i·A/3600 (captación)."""
    if area_m2 < 0 or intensity_mmh < 0:
        raise CalculationError(
            message="El área y la intensidad de lluvia no pueden ser negativas",
            code="ARQ-PLU-001",
            context={"area_m2": area_m2, "intensity_mmh": intensity_mmh})
    if coeff <= 0 or coeff > 1:
        raise CalculationError(
            message="El coeficiente de escorrentía debe estar entre 0 y 1",
            code="ARQ-PLU-002", context={"coeff": coeff})
    return round(coeff * intensity_mmh * area_m2 / 3600.0, 4)


def gutter_capacity_ls(width_mm: float, depth_mm: float,
                       slope_pct: float,
                       manning_n: float = GUTTER_MANNING_N) -> float:
    """Capacidad del canalón como canal rectangular (pendiente)."""
    if width_mm <= 0 or depth_mm <= 0 or slope_pct <= 0:
        return 0.0
    b = width_mm / 1000.0
    h = depth_mm / 1000.0
    area = b * h
    perimeter = b + 2.0 * h
    hydraulic_radius = area / perimeter if perimeter > 0 else 0.0
    return (1.0 / manning_n) * area * (hydraulic_radius ** (2.0 / 3.0)) \
        * math.sqrt(slope_pct / 100.0) * 1000.0


def select_gutter(inflow_ls: float, slope_pct: float = MIN_GUTTER_SLOPE_PCT,
                  catalog: Tuple[float, ...] = GUTTER_WIDTH_MM
                  ) -> Tuple[float, float, float]:
    """Menor canalón comercial con capacidad ≥ caudal (pendiente).

    Devuelve (width_mm, depth_mm, capacity_ls) con profundidad = ancho/2.
    """
    if inflow_ls <= 0:
        raise CalculationError(
            message="No se puede dimensionar canalón con caudal nulo",
            code="ARQ-PLU-003")
    for width in catalog:
        depth = width / 2.0
        capacity = gutter_capacity_ls(width, depth, slope_pct)
        if capacity >= inflow_ls - 1e-9:
            return width, depth, capacity
    largest = catalog[-1]
    return largest, largest / 2.0, gutter_capacity_ls(largest, largest / 2.0, slope_pct)


def downpipe_capacity_ls(diameter_mm: float) -> float:
    """Capacidad de bajante vertical por diámetro (bajantes)."""
    return DOWNPIPE_CAPACITY_LS.get(float(diameter_mm), 0.0)


def select_downpipe(q_ls: float,
                    catalog: Tuple[float, ...] = tuple(sorted(DOWNPIPE_CAPACITY_LS))
                    ) -> Tuple[float, float]:
    """Menor bajante comercial con capacidad ≥ caudal (bajantes).

    Devuelve (diameter_mm, capacity_ls).
    """
    if q_ls <= 0:
        raise CalculationError(
            message="No se puede dimensionar bajante con caudal nulo",
            code="ARQ-PLU-004")
    for dn in catalog:
        capacity = DOWNPIPE_CAPACITY_LS[dn]
        if capacity >= q_ls - 1e-9:
            return dn, capacity
    largest = catalog[-1]
    return largest, DOWNPIPE_CAPACITY_LS[largest]


@dataclass
class DetentionResult:
    """Almacenamiento de detención (almacenamiento)."""

    flow_ls: float = 0.0
    retention_min: float = DEFAULT_RETENTION_MIN
    volume_l: float = 0.0

    def to_dict(self) -> dict:
        return {
            "flow_ls": round(self.flow_ls, 3),
            "retention_min": round(self.retention_min, 1),
            "volume_l": round(self.volume_l, 1),
        }


def detention_volume_ls(q_ls: float,
                        retention_min: float = DEFAULT_RETENTION_MIN) -> DetentionResult:
    """Volumen de detención: V = Q · t (almacenamiento)."""
    if q_ls < 0 or retention_min < 0:
        raise CalculationError(
            message="El caudal y la retención no pueden ser negativos",
            code="ARQ-PLU-005")
    return DetentionResult(
        flow_ls=q_ls, retention_min=retention_min,
        volume_l=round(q_ls * retention_min * 60.0, 1))


def outfall_required_capacity(q_ls: float) -> float:
    """Capacidad exigida al punto de evacuación (evacuación).

    Se aplica un margen del 10 % sobre el caudal de llegada.
    """
    return round(q_ls * 1.10, 4)


__all__ = [
    "DetentionResult", "RUNOFF_COEFFICIENTS", "DEFAULT_INTENSITY_MMH",
    "DOWNPIPE_CAPACITY_LS", "GUTTER_WIDTH_MM", "GUTTER_MANNING_N",
    "MIN_GUTTER_SLOPE_PCT", "DEFAULT_RETENTION_MIN",
    "runoff_coefficient", "runoff_ls", "gutter_capacity_ls", "select_gutter",
    "downpipe_capacity_ls", "select_downpipe", "detention_volume_ls",
    "outfall_required_capacity",
]
