"""Perimeter Engine (spec section 47).

Perímetro / Fence / Gate / Barrier / Sensor / Camera / AccessPoint /
Zone. El perímetro se modela como un anillo de segmentos (FENCE) con
sensores (FENCE_SENSOR) a separación regular, puertas (GATE) y barreras
(BARRIER); se relaciona con intrusión, CCTV y control de acceso
(perímetro → intrusión → CCTV → acceso).

Cálculos:
  - Longitud del anillo y número de tramos (geometría).
  - Sensores exigidos: techo(length / spacing) + 1 por extremo de tramo.
  - Cobertura CCTV del perímetro: cámaras necesarias a cadencia fija
    (distancia entre cámaras perimetrales) y puntos ciegos declarados.
  - Accesos: cada GATE debe tener un punto de acceso (AccessPoint) y las
    barreras cuentan para el control vehicular.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from core.errors import CalculationError

SENSOR_SPACING_M = 30.0          # separación clásica de sensor de valla
CAMERA_SPACING_M = 60.0          # cadencia clásica de cámara perimetral
MIN_SENSORS_PER_SEGMENT = 1


@dataclass
class PerimeterReport:
    """Chequeo del perímetro (perímetro)."""

    fence_length_m: float = 0.0
    segments: int = 0
    required_sensors: int = 0
    installed_sensors: int = 0
    required_cameras: int = 0
    installed_cameras: int = 0
    gates: int = 0
    barriers: int = 0
    access_points: int = 0
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fence_length_m": round(self.fence_length_m, 2),
            "segments": self.segments,
            "required_sensors": self.required_sensors,
            "installed_sensors": self.installed_sensors,
            "required_cameras": self.required_cameras,
            "installed_cameras": self.installed_cameras,
            "gates": self.gates, "barriers": self.barriers,
            "access_points": self.access_points,
            "ok": self.ok, "findings": self.findings,
        }


def check_perimeter(fence_segments: Sequence[float],
                    installed_sensors: int, installed_cameras: int,
                    gates: int, barriers: int, access_points: int,
                    sensor_spacing_m: float = SENSOR_SPACING_M,
                    camera_spacing_m: float = CAMERA_SPACING_M
                    ) -> PerimeterReport:
    """Chequeo integral del perímetro (sensores, cámaras y accesos)."""
    if any(s < 0 for s in fence_segments):
        raise CalculationError(
            message="Los tramos de valla no pueden ser negativos",
            code="ARQ-PER-001", context={"segments": list(fence_segments)})
    if sensor_spacing_m <= 0 or camera_spacing_m <= 0:
        raise CalculationError(
            message="Las separaciones de sensor y cámara deben ser positivas",
            code="ARQ-PER-002",
            context={"sensor_spacing_m": sensor_spacing_m,
                     "camera_spacing_m": camera_spacing_m})
    report = PerimeterReport()
    report.segments = len(fence_segments)
    report.fence_length_m = sum(fence_segments)
    # Sensores: por tramo, techo(longitud/sep) con mínimo 1 por extremo.
    report.required_sensors = sum(
        max(MIN_SENSORS_PER_SEGMENT, math.ceil(length / sensor_spacing_m) + 1)
        for length in fence_segments)
    report.required_cameras = max(
        1, math.ceil(report.fence_length_m / camera_spacing_m)) \
        if report.fence_length_m > 0 else 0
    report.installed_sensors = installed_sensors
    report.installed_cameras = installed_cameras
    report.gates = gates
    report.barriers = barriers
    report.access_points = access_points
    if installed_sensors < report.required_sensors:
        report.findings.append(
            f"Sensores de valla: {installed_sensors} instalados, "
            f"exigidos {report.required_sensors} a {sensor_spacing_m:.0f} m")
    if installed_cameras < report.required_cameras:
        report.findings.append(
            f"Cámaras perimetrales: {installed_cameras} instaladas, "
            f"exigidas {report.required_cameras} a {camera_spacing_m:.0f} m")
    if gates > access_points:
        report.findings.append(
            f"{gates} puertas sin punto de acceso asociado "
            f"({access_points} AccessPoint declarados)")
    report.ok = not report.findings
    return report


def ring_length(points: Sequence[Tuple[float, float]]) -> float:
    """Longitud del anillo cerrado del perímetro (geometría)."""
    if len(points) < 3:
        raise CalculationError(
            message="El anillo perimetral exige al menos 3 vértices",
            code="ARQ-PER-003", context={"points": len(points)})
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


__all__ = [
    "SENSOR_SPACING_M", "CAMERA_SPACING_M", "PerimeterReport",
    "check_perimeter", "ring_length",
]
