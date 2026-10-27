"""Telecom Engine (spec section 32).

Red de telecomunicaciones sobre el modelo genérico de instalaciones:
NODE RACK / PATCH_PANEL / TELECOM_SWITCH / TELECOM_OUTLET y SEGMENT
CONDUIT / CABLE / FIBER. Integración futura con CCTV/Access/Fire/
Intrusion a través de nodos DEVICE_LV en la misma red (spec 32).

Métodos (documentados y configurables por datos):
  - Diámetros exteriores de cable por categoría (datos de catálogo).
  - Llenado de canalización: % = Σ áreas de cable / área interior del
    conducto, con límite 40 % (criterio telecom clásico).
  - Canalización: menor conducto comercial con llenado ≤ límite.
  - Enlace horizontal: longitud máxima 90 m de enlace permanente
    (TIA-568 cobre).
  - Rack: unidades U ocupadas frente a capacidad del rack.
  - Puertos: patch panel y switch con capacidad de puertos por equipo.
  - Fibra: presupuesto óptico
        Pérdida (dB) = L (km) · atenuación (dB/km) + conectores · dB
                      + empalmes · dB  ≤  presupuesto del enlace.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from core.errors import CalculationError

# -- Cables (diámetro exterior mm por categoría) ---------------------------------
CABLE_DIAMETER_MM: Dict[str, float] = {
    "CAT5E": 5.5, "CAT6": 6.0, "CAT6A": 7.0, "CAT7": 8.5,
    "FIBER": 3.0, "": 6.0,
}

# -- Canalización telecom (diámetro interior mm comercial) ------------------------
TELECONDUIT_ID_MM: Tuple[float, ...] = (16.0, 20.0, 25.0, 32.0, 40.0, 50.0,
                                        63.0, 75.0, 90.0, 110.0)
TELECOM_FILL_LIMIT_PCT = 40.0           # llenado máximo de conducto

# -- Enlace horizontal (TIA-568) ----------------------------------------------------
MAX_HORIZONTAL_LINK_M = 90.0            # enlace permanente de cobre

# -- Rack y puertos -------------------------------------------------------------------
DEFAULT_RACK_U = 12.0                   # U de un rack de pared estándar
DEVICE_U: Dict[str, float] = {
    "PATCH_PANEL": 1.0, "TELECOM_SWITCH": 1.0, "DEVICE_LV": 0.5,
    "": 0.5,
}
PATCH_PANEL_PORTS = 24
SWITCH_PORTS = 24

# -- Fibra (presupuesto óptico) --------------------------------------------------------
FIBER_ATT_DB_PER_KM = 3.5               # OM3 @ 850 nm
FIBER_CONNECTOR_DB = 0.75               # por conector
FIBER_SPLICE_DB = 0.30                  # por empalme
FIBER_DEFAULT_BUDGET_DB = 3.6           # 1000BASE-SX sobre OM3


def cable_diameter_mm(category: str = "CAT6") -> float:
    """Diámetro exterior del cable por categoría (datos)."""
    return CABLE_DIAMETER_MM.get(category.upper(), CABLE_DIAMETER_MM[""])


def conduit_fill_pct(cable_count: int, cable_diameter_mm: float,
                     conduit_id_mm: float) -> float:
    """Llenado del conducto en % (llenado)."""
    if conduit_id_mm <= 0 or cable_count <= 0:
        return 0.0
    cables_area = cable_count * math.pi * (cable_diameter_mm / 1000.0) ** 2 / 4.0
    conduit_area = math.pi * (conduit_id_mm / 1000.0) ** 2 / 4.0
    return round(cables_area / conduit_area * 100.0, 2)


def select_conduit(cable_count: int, cable_diameter_mm: float,
                   fill_limit_pct: float = TELECOM_FILL_LIMIT_PCT,
                   catalog: Tuple[float, ...] = TELECONDUIT_ID_MM
                   ) -> Tuple[float, float]:
    """Menor conducto comercial con llenado ≤ límite (canalización).

    Devuelve (conduit_id_mm, fill_pct).
    """
    if cable_count <= 0:
        raise CalculationError(
            message="No se puede dimensionar canalización sin cables",
            code="ARQ-TEL-001", context={"cable_count": cable_count})
    if cable_diameter_mm <= 0:
        raise CalculationError(
            message="El diámetro del cable debe ser positivo",
            code="ARQ-TEL-002", context={"cable_diameter_mm": cable_diameter_mm})
    for cid in catalog:
        fill = conduit_fill_pct(cable_count, cable_diameter_mm, cid)
        if fill <= fill_limit_pct + 1e-9:
            return cid, fill
    largest = catalog[-1]
    return largest, conduit_fill_pct(cable_count, cable_diameter_mm, largest)


def link_length_findings(length_m: float, category: str = "CAT6",
                         max_m: float = MAX_HORIZONTAL_LINK_M) -> Tuple[str, ...]:
    """Chequeo del enlace horizontal TIA-568 (cable)."""
    if length_m > max_m + 1e-9:
        return (f"Enlace {category} de {length_m:.1f} m supera el máximo "
                f"de {max_m:.0f} m (TIA-568)",)
    return ()


def device_u(kind: str) -> float:
    """Unidades U ocupadas por un equipo de rack (rack)."""
    return DEVICE_U.get(kind.upper(), DEVICE_U[""])


@dataclass
class RackSummary:
    """Ocupación de un rack (rack)."""

    rack: str = ""
    capacity_u: float = DEFAULT_RACK_U
    used_u: float = 0.0
    devices: int = 0
    findings: Tuple[str, ...] = ()

    @property
    def free_u(self) -> float:
        return self.capacity_u - self.used_u

    @property
    def usage_pct(self) -> float:
        return round(self.used_u / self.capacity_u * 100.0, 1) \
            if self.capacity_u > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "rack": self.rack, "capacity_u": round(self.capacity_u, 1),
            "used_u": round(self.used_u, 1), "free_u": round(self.free_u, 1),
            "usage_pct": self.usage_pct, "devices": self.devices,
            "findings": list(self.findings),
        }


def rack_summary(rack_code: str, capacity_u: float,
                 device_kinds: Tuple[str, ...]) -> RackSummary:
    """Ocupación U de un rack a partir de los equipos instalados (rack)."""
    if capacity_u <= 0:
        raise CalculationError(
            message="La capacidad del rack debe ser positiva",
            code="ARQ-TEL-003", context={"capacity_u": capacity_u})
    used = sum(device_u(k) for k in device_kinds)
    findings: Tuple[str, ...] = ()
    if used > capacity_u + 1e-9:
        findings = (f"Rack {rack_code} saturado: {used:.1f} U ocupadas de "
                    f"{capacity_u:.1f} U disponibles",)
    return RackSummary(rack=rack_code, capacity_u=capacity_u, used_u=used,
                       devices=len(device_kinds), findings=findings)


def port_usage(capacity: int, used: int, label: str = "puertos"
               ) -> Dict[str, float]:
    """Uso de puertos de un patch panel o switch (puertos)."""
    if capacity <= 0:
        raise CalculationError(
            message="La capacidad de puertos debe ser positiva",
            code="ARQ-TEL-004", context={"capacity": capacity})
    return {
        "capacity": float(capacity), "used": float(used),
        "usage_pct": round(used / capacity * 100.0, 1),
        "label": label,
    }


def fiber_loss_db(length_m: float, connectors: int = 2, splices: int = 0,
                  att_db_per_km: float = FIBER_ATT_DB_PER_KM,
                  connector_db: float = FIBER_CONNECTOR_DB,
                  splice_db: float = FIBER_SPLICE_DB) -> float:
    """Pérdida óptica del enlace (fibra)."""
    if length_m < 0 or connectors < 0 or splices < 0:
        raise CalculationError(
            message="Longitud, conectores y empalmes no pueden ser negativos",
            code="ARQ-TEL-005",
            context={"length_m": length_m, "connectors": connectors})
    return round(length_m / 1000.0 * att_db_per_km
                 + connectors * connector_db + splices * splice_db, 3)


def fiber_budget_findings(length_m: float, connectors: int = 2,
                          splices: int = 0,
                          budget_db: float = FIBER_DEFAULT_BUDGET_DB) -> Tuple[str, ...]:
    """Chequeo del presupuesto óptico del enlace (fibra)."""
    loss = fiber_loss_db(length_m, connectors, splices)
    if loss > budget_db + 1e-9:
        return (f"Enlace de fibra con {loss:.2f} dB supera el presupuesto "
                f"{budget_db:.2f} dB",)
    return ()


__all__ = [
    "RackSummary", "CABLE_DIAMETER_MM", "TELECONDUIT_ID_MM",
    "TELECOM_FILL_LIMIT_PCT", "MAX_HORIZONTAL_LINK_M", "DEFAULT_RACK_U",
    "DEVICE_U", "PATCH_PANEL_PORTS", "SWITCH_PORTS", "FIBER_ATT_DB_PER_KM",
    "FIBER_CONNECTOR_DB", "FIBER_SPLICE_DB", "FIBER_DEFAULT_BUDGET_DB",
    "cable_diameter_mm", "conduit_fill_pct", "select_conduit",
    "link_length_findings", "device_u", "rack_summary", "port_usage",
    "fiber_loss_db", "fiber_budget_findings",
]
