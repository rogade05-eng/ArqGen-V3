"""Fire Engine: detección, lazos, alimentación y causa/efecto (spec 43-44).

Cobertura de detectores (regla práctica EN 54-7 / NFPA 72 aproximada):
    radio efectivo del detector óptico de humo: 7,5 m bajo techo estándar
    separación entre detectores ≤ 2·R; cada detector cubre
    π·R² dentro del local. El chequeo se hace por local con su área y
    sus muros (geometría del proyecto).

Lazo (loop): direccionamiento y carga
    dispositivos por lazo ≤ límite (126 clásico de direccionamiento)
    corriente de reposo = Σ consumo (mA) con margen 20 %

Alimentación (batería):
    I_repo (A) × 24 h + I_alarma (A) × 0,5 h, con margen 1,25 → Ah

Causa/efecto (spec 44): INPUT → CONDITION → ACTION → OUTPUT → DELAY,
parametrizado por ruleset JSON (resources/rulesets/fire_cause_effect_v1.json).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.errors import CalculationError

DETECTOR_RADIUS_M: Dict[str, float] = {
    "SMOKE_DETECTOR": 7.5,
    "HEAT_DETECTOR": 5.3,
    "BEAM_DETECTOR": 15.0,
    "": 7.5,
}

DEVICE_CURRENT_MA: Dict[str, float] = {
    "SMOKE_DETECTOR": 0.10, "HEAT_DETECTOR": 0.10, "BEAM_DETECTOR": 0.30,
    "CALL_POINT": 0.0, "SOUNDER": 0.0, "STROBE": 0.0, "FIRE_MODULE": 0.5,
    "": 0.1,
}

SOUNDER_CURRENT_A = 0.35       # sirena interior en alarma
STROBE_CURRENT_A = 0.20        # estrobo en alarma
LOOP_DEVICE_LIMIT = 126        # direccionamiento clásico por lazo
STANDBY_HOURS = 24.0           # autonomía en reposo (EN 54-4)
ALARM_HOURS = 0.5              # autonomía en alarma
BATTERY_MARGIN = 1.25
CURRENT_MARGIN = 1.20

# Consumo por unidad en alarma (A) para el cálculo de batería.
ALARM_CURRENT_A: Dict[str, float] = {
    "SOUNDER": SOUNDER_CURRENT_A, "STROBE": STROBE_CURRENT_A,
}


@dataclass
class CoverageReport:
    """Cobertura de detección por local (cobertura)."""

    space: str = ""
    area_m2: float = 0.0
    required_detectors: int = 0
    installed: int = 0
    detector_radius_m: float = 7.5
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "space": self.space, "area_m2": round(self.area_m2, 2),
            "required": self.required_detectors, "installed": self.installed,
            "radius_m": self.detector_radius_m, "ok": self.ok,
            "findings": self.findings,
        }


def required_detectors(area_m2: float, kind: str = "SMOKE_DETECTOR",
                       ceiling_height_m: float = 3.0) -> int:
    """Detectores exigidos en un local (cobertura).

    R = radio efectivo reducido por altura (cada 3 m extra, -10 % de R,
    criterio conservador); N = ceil(área / (π·R²)).
    """
    if area_m2 < 0:
        raise CalculationError(
            message="El área del local no puede ser negativa",
            code="ARQ-FIR-001", context={"area_m2": area_m2})
    radius = DETECTOR_RADIUS_M.get(kind.upper(), DETECTOR_RADIUS_M[""])
    if ceiling_height_m > 3.0:
        radius *= max(0.6, 1.0 - 0.10 * math.floor((ceiling_height_m - 3.0) / 3.0))
    coverage_area = math.pi * radius ** 2
    return max(1, math.ceil(area_m2 / coverage_area)) if area_m2 > 0 else 1


def check_space_coverage(space_code: str, area_m2: float,
                         installed_count: int, kind: str = "SMOKE_DETECTOR",
                         ceiling_height_m: float = 3.0) -> CoverageReport:
    """Chequeo de cobertura de un local (cobertura)."""
    need = required_detectors(area_m2, kind, ceiling_height_m)
    report = CoverageReport(space=space_code, area_m2=area_m2,
                            required_detectors=need,
                            installed=installed_count,
                            detector_radius_m=DETECTOR_RADIUS_M.get(kind.upper(),
                                                                    DETECTOR_RADIUS_M[""]))
    report.ok = installed_count >= need
    if not report.ok:
        report.findings.append(
            f"{space_code}: {installed_count} detector(es) para un área que "
            f"exige {need} (radio {report.detector_radius_m:.1f} m)")
    return report


@dataclass
class LoopReport:
    """Carga del lazo (lazos/direccionamiento)."""

    devices: int = 0
    device_limit: int = LOOP_DEVICE_LIMIT
    standby_ma: float = 0.0
    alarm_a: float = 0.0
    battery_ah: float = 0.0
    ok: bool = True
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "devices": self.devices, "device_limit": self.device_limit,
            "standby_ma": round(self.standby_ma, 2),
            "alarm_a": round(self.alarm_a, 3),
            "battery_ah": round(self.battery_ah, 2),
            "ok": self.ok, "findings": self.findings,
        }


def loop_report(device_kinds: List[str]) -> LoopReport:
    """Carga del lazo y batería del panel (lazos, alimentación, batería)."""
    report = LoopReport(devices=len(device_kinds))
    for kind in device_kinds:
        report.standby_ma += DEVICE_CURRENT_MA.get(kind.upper(),
                                                   DEVICE_CURRENT_MA[""])
        report.alarm_a += ALARM_CURRENT_A.get(kind.upper(), 0.0)
    report.standby_ma *= CURRENT_MARGIN
    if report.alarm_a == 0:
        # Sin sirenas declaradas: el panel asume 1 sirena interior mínima.
        report.alarm_a = SOUNDER_CURRENT_A
    # Batería: 24 h reposo + 0,5 h alarma, margen 1,25 (alimentación).
    report.battery_ah = (report.standby_ma / 1000.0 * STANDBY_HOURS
                         + report.alarm_a * ALARM_HOURS) * BATTERY_MARGIN
    if report.devices > report.device_limit:
        report.findings.append(
            f"El lazo supera el límite de direccionamiento ({report.devices} > "
            f"{report.device_limit})")
    report.ok = not report.findings
    return report


# -- Causa / efecto (spec 44) ------------------------------------------------------

@dataclass
class CauseEffectResult:
    """Evaluación de la matriz causa/efecto (causa/efecto)."""

    triggered: List[Dict[str, Any]] = field(default_factory=list)
    missing_rules: List[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict:
        return {"triggered": self.triggered, "missing_rules": self.missing_rules,
                "ok": self.ok}


def evaluate_cause_effect(input_event: str, context: Dict[str, Any],
                          rules: List[Dict[str, Any]]) -> CauseEffectResult:
    """Matriz INPUT → CONDITION → ACTION → OUTPUT → DELAY (spec 44).

    rules: lista de reglas del ruleset con la forma:
        {"code", "when": "SMOKE_DETECTOR", "condition": "night_mode",
         "actions": [{"output": "SOUNDER", "delay_s": 0}, ...]}
    ``condition`` es opcional; si existe, debe ser verdadero en context.
    """
    if not rules:
        raise CalculationError(
            message="La matriz causa/efecto no tiene reglas cargadas",
            code="ARQ-FIR-002",
            suggested_action="Cargue el ruleset fire_cause_effect_v1.")
    result = CauseEffectResult()
    matched = False
    for rule in rules:
        when = str(rule.get("when", "")).upper()
        if when != input_event.upper():
            continue
        matched = True
        condition = rule.get("condition")
        if condition and not context.get(str(condition), False):
            continue
        for action in rule.get("actions", []):
            result.triggered.append({
                "rule": rule.get("code", ""),
                "input": input_event,
                "condition": condition or "",
                "action": action.get("action", ""),
                "output": action.get("output", ""),
                "delay_s": float(action.get("delay_s", 0.0)),
            })
    if not matched:
        result.missing_rules.append(input_event)
        result.ok = False
    return result


__all__ = [
    "DETECTOR_RADIUS_M", "DEVICE_CURRENT_MA", "LOOP_DEVICE_LIMIT",
    "STANDBY_HOURS", "ALARM_HOURS", "BATTERY_MARGIN",
    "CoverageReport", "LoopReport", "CauseEffectResult",
    "required_detectors", "check_space_coverage", "loop_report",
    "evaluate_cause_effect",
]
