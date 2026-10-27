"""CCTV Engine: cableado (spec 41) y red (spec 42).

Cableado (ruta Cámara → Cable → Bandeja → Rack → NVR):
    route_length + service_loop + vertical_rise + installation_reserve
con service_loop 3 m por cámara, installation_reserve 10 % y
vertical_rise declarado por el usuario (altura de racks, bandejas).

Red (spec 42):
    TotalBandwidth = Σ bitrate × (1 + overhead)
    Storage        = bitrate × time × cameras   (GB, MBIT→GB)
    PoE            = Σ cámara W ≤ presupuesto PoE del switch
    Switch/NVR     canales usados ≤ canales disponibles

Catálogo de cámaras por resolución (bitrate Mbps y consumo PoE W)
como datos del motor, ampliable por catálogo de proyecto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.errors import CalculationError

# -- Catálogo de cámaras (resolution → bitrate Mbps, PoE W) ----------------------
CAMERA_CATALOG: Dict[str, Dict[str, float]] = {
    "1080P": {"bitrate_mbps": 4.0, "power_w": 6.5},
    "2MP": {"bitrate_mbps": 4.0, "power_w": 6.5},
    "4MP": {"bitrate_mbps": 6.0, "power_w": 8.0},
    "4K": {"bitrate_mbps": 16.0, "power_w": 12.0},
    "": {"bitrate_mbps": 4.0, "power_w": 6.5},
}

SERVICE_LOOP_M = 3.0            # rulo de servicio por cámara
INSTALL_RESERVE_PCT = 10.0      # reserva de instalación
BANDWIDTH_OVERHEAD = 0.25       # 25 % de overhead de red (espec 42)
POE_BUDGET_W = 240.0            # switch PoE típico de 8-16 puertos (media)
SWITCH_CHANNELS = 16            # canales del switch PoE
NVR_CHANNELS = 16               # canales del NVR
DEFAULT_RETENTION_DAYS = 30.0   # retención de grabación


def camera_profile(resolution: str) -> Dict[str, float]:
    """Perfil de cámara por resolución (catálogo de equipos, spec 50)."""
    return CAMERA_CATALOG.get(resolution.upper(), CAMERA_CATALOG[""])


def camera_cable_length_m(route_length_m: float, vertical_rise_m: float = 0.0,
                          service_loop_m: float = SERVICE_LOOP_M,
                          reserve_pct: float = INSTALL_RESERVE_PCT) -> float:
    """Longitud de cable por cámara (cableado, spec 41)."""
    if route_length_m < 0 or vertical_rise_m < 0:
        raise CalculationError(
            message="La longitud de ruta y el desnivel no pueden ser negativos",
            code="ARQ-CCT-001",
            context={"route_length_m": route_length_m,
                     "vertical_rise_m": vertical_rise_m})
    base = route_length_m + service_loop_m + vertical_rise_m
    return round(base * (1.0 + reserve_pct / 100.0), 2)


@dataclass
class CablingReport:
    """Cableado CCTV del sistema (cableado, spec 41)."""

    cameras: int = 0
    total_route_m: float = 0.0
    service_loop_m: float = 0.0
    vertical_rise_m: float = 0.0
    reserve_m: float = 0.0
    total_cable_m: float = 0.0

    def to_dict(self) -> dict:
        return {
            "cameras": self.cameras,
            "route_m": round(self.total_route_m, 2),
            "service_loop_m": round(self.service_loop_m, 2),
            "vertical_rise_m": round(self.vertical_rise_m, 2),
            "reserve_m": round(self.reserve_m, 2),
            "total_cable_m": round(self.total_cable_m, 2),
        }


def cabling_report(camera_route_lengths: List[float],
                   vertical_rise_m: float = 0.0) -> CablingReport:
    """Cableado total del sistema a partir de las rutas por cámara."""
    report = CablingReport(cameras=len(camera_route_lengths),
                           vertical_rise_m=vertical_rise_m)
    for route in camera_route_lengths:
        if route < 0:
            raise CalculationError(
                message="La ruta de una cámara no puede ser negativa",
                code="ARQ-CCT-002", context={"route_m": route})
        cable = camera_cable_length_m(route, vertical_rise_m)
        report.total_route_m += route
        report.service_loop_m += SERVICE_LOOP_M
        report.vertical_rise_m += vertical_rise_m
        report.total_cable_m += cable
    report.reserve_m = report.total_cable_m - report.total_route_m \
        - report.service_loop_m - report.vertical_rise_m
    return report


@dataclass
class NetworkReport:
    """Red CCTV: ancho de banda, PoE, almacenamiento y capacidad (red)."""

    cameras: int = 0
    total_bitrate_mbps: float = 0.0
    bandwidth_mbps: float = 0.0
    poe_demand_w: float = 0.0
    poe_budget_w: float = POE_BUDGET_W
    storage_gb: float = 0.0
    retention_days: float = DEFAULT_RETENTION_DAYS
    switch_channels: int = SWITCH_CHANNELS
    nvr_channels: int = NVR_CHANNELS
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cameras": self.cameras,
            "total_bitrate_mbps": round(self.total_bitrate_mbps, 2),
            "bandwidth_mbps": round(self.bandwidth_mbps, 2),
            "poe_demand_w": round(self.poe_demand_w, 1),
            "poe_budget_w": self.poe_budget_w,
            "storage_gb": round(self.storage_gb, 1),
            "retention_days": self.retention_days,
            "switch_channels": self.switch_channels,
            "nvr_channels": self.nvr_channels,
            "findings": self.findings,
        }


def network_report(resolutions: List[str], retention_days: float = DEFAULT_RETENTION_DAYS,
                   poe_budget_w: float = POE_BUDGET_W,
                   switch_channels: int = SWITCH_CHANNELS,
                   nvr_channels: int = NVR_CHANNELS) -> NetworkReport:
    """Cálculo de red CCTV (spec 42): bandwidth, PoE, storage, capacity."""
    if not resolutions:
        raise CalculationError(
            message="No hay cámaras para calcular la red CCTV",
            code="ARQ-CCT-003")
    report = NetworkReport(cameras=len(resolutions),
                           retention_days=retention_days,
                           poe_budget_w=poe_budget_w,
                           switch_channels=switch_channels,
                           nvr_channels=nvr_channels)
    for resolution in resolutions:
        profile = camera_profile(resolution)
        report.total_bitrate_mbps += profile["bitrate_mbps"]
        report.poe_demand_w += profile["power_w"]
    # TotalBandwidth = Σ bitrate × (1 + overhead)
    report.bandwidth_mbps = report.total_bitrate_mbps * (1.0 + BANDWIDTH_OVERHEAD)
    # Storage = bitrate × time × cameras (Mbps → GB/día: Mbps/8 MB/s → GB/día)
    gigabytes_per_camera_day = (report.total_bitrate_mbps / len(resolutions)) \
        / 8.0 * 86400.0 / 1000.0
    report.storage_gb = gigabytes_per_camera_day * len(resolutions) * retention_days
    if report.poe_demand_w > poe_budget_w + 1e-9:
        report.findings.append(
            f"PoE exigido {report.poe_demand_w:.1f} W supera el presupuesto "
            f"del switch ({poe_budget_w:.0f} W)")
    if report.cameras > switch_channels:
        report.findings.append(
            f"{report.cameras} cámaras superan los {switch_channels} canales del switch")
    if report.cameras > nvr_channels:
        report.findings.append(
            f"{report.cameras} cámaras superan los {nvr_channels} canales del NVR")
    return report


__all__ = [
    "CAMERA_CATALOG", "SERVICE_LOOP_M", "INSTALL_RESERVE_PCT",
    "BANDWIDTH_OVERHEAD", "POE_BUDGET_W", "SWITCH_CHANNELS", "NVR_CHANNELS",
    "DEFAULT_RETENTION_DAYS", "CablingReport", "NetworkReport",
    "camera_profile", "camera_cable_length_m", "cabling_report",
    "network_report",
]
