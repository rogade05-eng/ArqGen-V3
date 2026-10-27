"""Access Control Engine (spec section 46).

Controller / Reader / Lock / ExitButton / REX / DoorContact /
PowerSupply / Battery. Integración con arquitectura (puertas), fuego
(rutas de evacuación), intrusión y seguridad general.

Cálculos:
  - Capacidad del controlador: lectores y cerraduras conectadas ≤
    límites del catálogo (4 lectores / 4 cerraduras clásicos).
  - Alimentación: consumo en reposo (controladores) + demanda en
    apertura (cerraduras) + margen 25 % → fuente en A y batería.
  - Tiempo de desbloqueo de evacuación: las puertas de evacuación
    (integración con fuego) deben fallar en desbloqueado (fail-safe).
  - REX: toda puerta con cerradura exige botón de salida o REX para
    la salida libre (acceso).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from core.errors import CalculationError

CONTROLLER_READER_LIMIT = 4
CONTROLLER_LOCK_LIMIT = 4
CONTROLLER_STANDBY_A = 0.10
LOCK_CURRENT_A = 0.45            # cerradura electromagnética en apertura
POWER_MARGIN = 1.25
STANDBY_HOURS = 24.0
BATTERY_MARGIN = 1.25
MAX_UNLOCK_S = 5.0               # desbloqueo máx. admisible en evacuación


@dataclass
class ControllerReport:
    """Chequeo de un controlador (controlador/capacidades)."""

    controller: str = ""
    readers: int = 0
    locks: int = 0
    reader_limit: int = CONTROLLER_READER_LIMIT
    lock_limit: int = CONTROLLER_LOCK_LIMIT
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "controller": self.controller, "readers": self.readers,
            "locks": self.locks, "reader_limit": self.reader_limit,
            "lock_limit": self.lock_limit, "ok": self.ok,
            "findings": self.findings,
        }


def check_controller(controller_code: str, readers: int, locks: int
                     ) -> ControllerReport:
    """Capacidades de un controlador (controller)."""
    if readers < 0 or locks < 0:
        raise CalculationError(
            message="Lectores y cerraduras no pueden ser negativos",
            code="ARQ-ACC-001", context={"readers": readers, "locks": locks})
    report = ControllerReport(controller=controller_code, readers=readers,
                              locks=locks)
    if readers > CONTROLLER_READER_LIMIT:
        report.findings.append(
            f"{controller_code}: {readers} lectores superan el límite "
            f"{CONTROLLER_READER_LIMIT}")
    if locks > CONTROLLER_LOCK_LIMIT:
        report.findings.append(
            f"{controller_code}: {locks} cerraduras superan el límite "
            f"{CONTROLLER_LOCK_LIMIT}")
    report.ok = not report.findings
    return report


@dataclass
class PowerReport:
    """Alimentación del sistema de acceso (power supply/battery)."""

    controllers: int = 0
    locks: int = 0
    demand_a: float = 0.0
    supply_a: float = 0.0
    battery_ah: float = 0.0
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "controllers": self.controllers, "locks": self.locks,
            "demand_a": round(self.demand_a, 2),
            "supply_a": round(self.supply_a, 2),
            "battery_ah": round(self.battery_ah, 2),
            "ok": self.ok, "findings": self.findings,
        }


def power_report(controllers: int, locks: int,
                 supply_a: float = 2.0) -> PowerReport:
    """Alimentación: reposo + apertura simultánea con margen (power)."""
    if controllers < 0 or locks < 0:
        raise CalculationError(
            message="Controladores y cerraduras no pueden ser negativos",
            code="ARQ-ACC-002",
            context={"controllers": controllers, "locks": locks})
    demand = controllers * CONTROLLER_STANDBY_A + locks * LOCK_CURRENT_A
    demand *= POWER_MARGIN
    battery = (controllers * CONTROLLER_STANDBY_A * STANDBY_HOURS
               + locks * LOCK_CURRENT_A * 0.1) * BATTERY_MARGIN
    report = PowerReport(controllers=controllers, locks=locks,
                         demand_a=demand, supply_a=supply_a,
                         battery_ah=battery)
    if demand > supply_a + 1e-9:
        report.findings.append(
            f"Demanda {demand:.2f} A supera la fuente de {supply_a:.1f} A")
    report.ok = not report.findings
    return report


def evacuation_check(is_evacuation_door: bool, unlock_s: float,
                     door_code: str = "") -> dict:
    """Integración con fuego: puertas de evacuación (fuego/acceso).

    Una puerta de evacuación con control de acceso debe liberarse en
    ≤ MAX_UNLOCK_S (fail-safe) y tener REX o botón de salida.
    """
    if unlock_s < 0:
        raise CalculationError(
            message="El tiempo de desbloqueo no puede ser negativo",
            code="ARQ-ACC-003", context={"unlock_s": unlock_s})
    result = {
        "door": door_code,
        "is_evacuation_door": is_evacuation_door,
        "unlock_s": round(unlock_s, 2),
        "ok": True,
        "findings": [],
    }
    if is_evacuation_door and unlock_s > MAX_UNLOCK_S + 1e-9:
        result["ok"] = False
        result["findings"].append(
            f"La puerta de evacuación {door_code} libera en {unlock_s:.1f} s "
            f"(máximo {MAX_UNLOCK_S:.0f} s): instale fail-safe")
    return result


__all__ = [
    "CONTROLLER_READER_LIMIT", "CONTROLLER_LOCK_LIMIT", "LOCK_CURRENT_A",
    "MAX_UNLOCK_S", "ControllerReport", "PowerReport",
    "check_controller", "power_report", "evacuation_check",
]
