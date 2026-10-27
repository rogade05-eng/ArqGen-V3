"""Intrusion Engine (spec section 45): zonificación, cobertura, particiones,
armado, rutas, panel, batería y sirenas.

Cobertura de detectores volumétricos (PIR): radio y ángulo de catálogo;
la cobertura exigida por local se evalúa por área (criterio conservador
de 1 PIR por sector de ~12 m2 con montaje típico en esquina).

Zonificación (zonas/particiones): los dispositivos se agrupan en zonas
nombradas; cada partición agrupa zonas y se arma/desarma de conjunto
(armado/desarmado). El panel (panel/batería/sirenas) exige:

    dispositivos por panel ≤ límite (68 zonas clásicas ampliables)
    batería: reposo 24 h (panel + expandidores) + alarma (sirenas) 0,5 h
    sirenas: cobertura sonora por SPL y distancia (informativo)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.errors import CalculationError

PIR_RADIUS_M = 6.0               # PIR de esquina típico (catálogo)
PIR_AREA_M2 = math.pi * PIR_RADIUS_M ** 2 / 4.0   # cuarto de círculo útil
PANEL_ZONE_LIMIT = 68            # zonas direccionables clásicas
STANDBY_HOURS = 24.0
ALARM_HOURS = 0.5
BATTERY_MARGIN = 1.25

PANEL_STANDBY_A = 0.06           # consumo del panel en reposo
EXPANDER_STANDBY_A = 0.04        # consumo por expandidor
SIREN_ALARM_A = 1.2              # sirena interior en alarma
SIREN_SPL_DB = 105.0             # SPL nominal a 1 m


@dataclass
class IntrusionZoneReport:
    """Chequeo de una zona (zonificación/cobertura)."""

    zone: str = ""
    spaces: int = 0
    area_m2: float = 0.0
    required_pirs: int = 0
    installed_pirs: int = 0
    perimeter_contacts: int = 0
    perimeter_openings: int = 0
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "zone": self.zone, "spaces": self.spaces,
            "area_m2": round(self.area_m2, 2),
            "required_pirs": self.required_pirs,
            "installed_pirs": self.installed_pirs,
            "perimeter_contacts": self.perimeter_contacts,
            "perimeter_openings": self.perimeter_openings,
            "ok": self.ok, "findings": self.findings,
        }


def required_pirs(area_m2: float, radius_m: float = PIR_RADIUS_M) -> int:
    """PIR exigidos por área (cobertura): cuarto de círculo útil por PIR."""
    if area_m2 < 0:
        raise CalculationError(
            message="El área de la zona no puede ser negativa",
            code="ARQ-INT-001", context={"area_m2": area_m2})
    useful = math.pi * radius_m ** 2 / 4.0
    return max(1, math.ceil(area_m2 / useful)) if area_m2 > 0 else 1


def check_zone(zone_code: str, area_m2: float, installed_pirs: int,
               perimeter_contacts: int, perimeter_openings: int
               ) -> IntrusionZoneReport:
    """Chequeo de cobertura y perímetro de una zona (zonificación)."""
    need = required_pirs(area_m2)
    report = IntrusionZoneReport(zone=zone_code, area_m2=area_m2,
                                 required_pirs=need,
                                 installed_pirs=installed_pirs,
                                 perimeter_contacts=perimeter_contacts,
                                 perimeter_openings=perimeter_openings)
    if installed_pirs < need:
        report.findings.append(
            f"{zone_code}: {installed_pirs} PIR instalados, exigidos {need}")
    # Los vanos exteriores de la zona deben tener contacto magnético.
    if perimeter_openings > perimeter_contacts:
        report.findings.append(
            f"{zone_code}: {perimeter_openings} vanos perimetrales y "
            f"{perimeter_contacts} contactos magnéticos")
    report.spaces = 1
    report.ok = not report.findings
    return report


@dataclass
class Partition:
    """Partición armable (particiones/armado)."""

    code: str = ""
    zones: Tuple[str, ...] = ()
    armed: bool = False

    def to_dict(self) -> dict:
        return {"code": self.code, "zones": list(self.zones),
                "armed": self.armed}


@dataclass
class PanelReport:
    """Panel de intrusión: zonas, batería y sirenas (panel/batería/sirenas)."""

    zones: int = 0
    zone_limit: int = PANEL_ZONE_LIMIT
    partitions: int = 0
    expanders: int = 0
    sirens: int = 0
    battery_ah: float = 0.0
    siren_spl_at_distance_db: float = 0.0
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "zones": self.zones, "zone_limit": self.zone_limit,
            "partitions": self.partitions, "expanders": self.expanders,
            "sirens": self.sirens, "battery_ah": round(self.battery_ah, 2),
            "siren_spl_db": round(self.siren_spl_at_distance_db, 1),
            "ok": self.ok, "findings": self.findings,
        }


def panel_report(zones: int, partitions: List[Partition], expanders: int = 0,
                 sirens: int = 0, siren_distance_m: float = 3.0
                 ) -> PanelReport:
    """Panel: límite de zonas, batería y sirenas (panel/batería/sirenas)."""
    if zones < 0 or expanders < 0 or sirens < 0:
        raise CalculationError(
            message="Zonas, expandidores y sirenas no pueden ser negativos",
            code="ARQ-INT-002",
            context={"zones": zones, "expanders": expanders, "sirens": sirens})
    report = PanelReport(zones=zones, partitions=len(partitions),
                         expanders=expanders, sirens=sirens)
    # Batería: reposo 24 h (panel + expandidores) + sirenas 0,5 h.
    standby = PANEL_STANDBY_A + expanders * EXPANDER_STANDBY_A
    alarm = sirens * SIREN_ALARM_A
    report.battery_ah = (standby * STANDBY_HOURS
                         + alarm * ALARM_HOURS) * BATTERY_MARGIN
    # SPL de las sirenas a la distancia de referencia (sirenas).
    if sirens > 0:
        report.siren_spl_at_distance_db = SIREN_SPL_DB + 6.0 * math.log2(max(sirens, 1)) \
            - 20.0 * math.log10(max(siren_distance_m, 1.0))
    if zones > report.zone_limit:
        report.findings.append(
            f"El panel supera el límite de zonas ({zones} > {report.zone_limit}): "
            "añada expandidores o reparta el proyecto")
    zone_names = [zone for partition in partitions for zone in partition.zones]
    if len(zone_names) != len(set(zone_names)):
        report.findings.append("Hay zonas asignadas a más de una partición")
    if partitions and not any(p.armed for p in partitions):
        report.findings.append("Ninguna partición está armada (armado informativo)")
    report.ok = not report.findings
    return report


__all__ = [
    "PIR_RADIUS_M", "PANEL_ZONE_LIMIT", "STANDBY_HOURS", "ALARM_HOURS",
    "IntrusionZoneReport", "Partition", "PanelReport",
    "required_pirs", "check_zone", "panel_report",
]
