"""Clash entity for the coordination module (spec sections 35, 36).

The Coordination Engine is the intermediary between disciplines
(Architecture → Coordination → MEP/Structure/Security/BIM). It detects:

    HARD        physical overlap (two solids occupy the same space)
    SOFT        proximity below the comfort/work tolerance
    CLEARANCE   required free distance around equipment violated
    ACCESS      access route to a panel/equipment obstructed
    MAINTENANCE maintenance zone invaded (withdrawal space)
    ROUTE       two distribution routes cross in conflict

Clash lifecycle states (spec 36): OPEN → REVIEWED → ACCEPTED / RESOLVED
/ IGNORED. The ``status`` field of a Clash stores the clash lifecycle
(OPEN/REVIEWED/...), overriding the generic Entity lifecycle which does
not apply to findings. Every clash stores the pair of objects, the
type, severity, location, distance, the rule that fired and its status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.entities.base import Entity, utc_now
from core.errors import DomainError

CLASH_TYPES: tuple[str, ...] = (
    "HARD", "SOFT", "CLEARANCE", "ACCESS", "MAINTENANCE", "ROUTE",
)

CLASH_SEVERITIES: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

CLASH_STATUSES: tuple[str, ...] = (
    "OPEN", "REVIEWED", "ACCEPTED", "RESOLVED", "IGNORED",
)

# Severity implied by clash type when the engine does not state it.
DEFAULT_SEVERITY: dict[str, str] = {
    "HARD": "CRITICAL",
    "CLEARANCE": "HIGH",
    "ACCESS": "HIGH",
    "MAINTENANCE": "MEDIUM",
    "ROUTE": "MEDIUM",
    "SOFT": "LOW",
}


@dataclass
class Clash(Entity):
    """One clash between two project objects (spec 36).

    ``status`` shadows the generic Entity lifecycle with the clash
    lifecycle of spec 36 (OPEN / REVIEWED / ACCEPTED / RESOLVED /
    IGNORED).
    """

    ENTITY_TYPE = "CLASH"
    object_a_type: str = ""
    object_a_id: str = ""
    object_a_code: str = ""
    object_b_type: str = ""
    object_b_id: str = ""
    object_b_code: str = ""
    type: str = "HARD"
    severity: str = "MEDIUM"
    rule: str = ""
    location: tuple[float, float] = (0.0, 0.0)
    distance: float = 0.0
    resolved_at: Optional[str] = None
    notes: str = ""
    status: str = "OPEN"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.type not in CLASH_TYPES:
            raise DomainError(
                message=f"Tipo de interferencia desconocido: {self.type}",
                code="ARQ-CLS-001",
                context={"type": self.type, "allowed": list(CLASH_TYPES)})
        if self.severity not in CLASH_SEVERITIES:
            raise DomainError(
                message=f"Severidad desconocida: {self.severity}",
                code="ARQ-CLS-002",
                context={"severity": self.severity})
        if self.status not in CLASH_STATUSES:
            raise DomainError(
                message=f"Estado de interferencia desconocido: {self.status}",
                code="ARQ-CLS-003",
                context={"status": self.status})
        if not self.object_a_id or not self.object_b_id:
            raise DomainError(
                message="La interferencia exige dos objetos implicados",
                code="ARQ-CLS-004")

    def set_status(self, new_status: str) -> None:
        if new_status not in CLASH_STATUSES:
            raise DomainError(
                message=f"Estado de interferencia desconocido: {new_status}",
                code="ARQ-CLS-003",
                context={"status": new_status, "allowed": list(CLASH_STATUSES)})
        self.status = new_status
        if new_status == "RESOLVED":
            self.resolved_at = utc_now().isoformat()
        self.touch()


__all__ = [
    "Clash", "CLASH_TYPES", "CLASH_SEVERITIES", "CLASH_STATUSES",
    "DEFAULT_SEVERITY",
]
