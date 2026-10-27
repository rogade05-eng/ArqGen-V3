"""ARQ GEN error engine (spec section 83).

Every error carries: code, message, severity, context, object_ids,
recoverable and suggested_action, exactly as required by the master
technical specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ErrorSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ARQGenError(Exception):
    """Base class for every controlled error raised by ARQ GEN."""

    message: str = ""
    code: str = "ARQ-ERR-000"
    severity: ErrorSeverity = ErrorSeverity.ERROR
    context: dict[str, Any] = field(default_factory=dict)
    object_ids: list[str] = field(default_factory=list)
    recoverable: bool = True
    suggested_action: str = ""

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "context": self.context,
            "object_ids": self.object_ids,
            "recoverable": self.recoverable,
            "suggested_action": self.suggested_action,
        }


class DomainError(ARQGenError):
    """Domain rule violation (invalid state transition, bad argument)."""

    code = "ARQ-DOM-001"


class GeometryError(ARQGenError):
    """Geometry engine error (degenerate or invalid geometry)."""

    code = "ARQ-GEO-001"


class RuleError(ARQGenError):
    """Rule engine error (malformed rule, bad expression)."""

    code = "ARQ-RUL-001"


class CalculationError(ARQGenError):
    """Calculation engine error (missing variable, unit mismatch)."""

    code = "ARQ-CAL-001"


class ImportErrorARQ(ARQGenError):
    """Import pipeline error (parse, validate or map failure)."""

    code = "ARQ-IMP-001"


class ExportError(ARQGenError):
    """Export pipeline error (writer failure, unsupported format)."""

    code = "ARQ-EXP-001"


class PersistenceError(ARQGenError):
    """SQLite persistence error (connection, transaction, integrity)."""

    code = "ARQ-PER-001"


class MigrationError(ARQGenError):
    """Schema migration error."""

    code = "ARQ-MIG-001"


class PluginError(ARQGenError):
    """Plugin load or registration error."""

    code = "ARQ-PLG-001"


class RoutingError(ARQGenError):
    """Routing / network path error (reserved for routing engine)."""

    code = "ARQ-ROU-001"


class UnitError(ARQGenError):
    """Unit conversion or dimension mismatch error."""

    code = "ARQ-UNI-001"


class DataError(ARQGenError):
    """Data-driven operation error (unresolved variables, bad datasets)."""

    code = "ARQ-DAT-001"


class PermissionDeniedError(ARQGenError):
    """User lacks the required permission."""

    code = "ARQ-PRM-001"

    def __init__(self, user: str, permission: str) -> None:
        super().__init__(
            message=f"El usuario '{user}' no tiene el permiso requerido: {permission}",
            severity=ErrorSeverity.ERROR,
            context={"user": user, "permission": permission},
            recoverable=True,
            suggested_action="Solicite el permiso a un administrador o cambie de usuario.",
        )


__all__ = [
    "ARQGenError",
    "ErrorSeverity",
    "DomainError",
    "GeometryError",
    "RuleError",
    "CalculationError",
    "ImportErrorARQ",
    "ExportError",
    "PersistenceError",
    "MigrationError",
    "PluginError",
    "RoutingError",
    "UnitError",
    "DataError",
    "PermissionDeniedError",
]
