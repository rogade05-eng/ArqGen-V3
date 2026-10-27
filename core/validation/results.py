"""Validation engine (spec section 82).

ValidationResult(status, errors, warnings, info, affected_objects)
Statuses: VALID, VALID_WITH_WARNINGS, INVALID, BLOCKED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.rules.models import RuleSeverity


class ValidationStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"


@dataclass
class Finding:
    """One finding: raised by a rule or a built-in validator."""

    severity: str  # INFO | WARNING | ERROR | HARD_BLOCK
    code: str
    message: str
    object_id: str = ""
    object_type: str = ""
    rule_code: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "rule_code": self.rule_code,
            "source": self.source,
        }


@dataclass
class ValidationResult:
    """Contract of spec section 82."""

    status: ValidationStatus = ValidationStatus.VALID
    errors: List[Finding] = field(default_factory=list)
    warnings: List[Finding] = field(default_factory=list)
    info: List[Finding] = field(default_factory=list)
    affected_objects: List[str] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        sev = finding.severity
        if sev == RuleSeverity.HARD_BLOCK.value:
            self.errors.append(finding)
        elif sev == RuleSeverity.ERROR.value:
            self.errors.append(finding)
        elif sev == RuleSeverity.WARNING.value:
            self.warnings.append(finding)
        else:
            self.info.append(finding)
        if finding.object_id and finding.object_id not in self.affected_objects:
            self.affected_objects.append(finding.object_id)

    def merge(self, other: "ValidationResult") -> None:
        for f in other.errors:
            self.add(f)
        for f in other.warnings:
            self.add(f)
        for f in other.info:
            self.add(f)

    def finalize(self) -> "ValidationResult":
        """Recompute status from findings (worst severity wins)."""
        if any(f.severity == RuleSeverity.HARD_BLOCK.value for f in self.errors):
            self.status = ValidationStatus.BLOCKED
        elif self.errors:
            self.status = ValidationStatus.INVALID
        elif self.warnings:
            self.status = ValidationStatus.VALID_WITH_WARNINGS
        else:
            self.status = ValidationStatus.VALID
        return self

    @property
    def is_ok(self) -> bool:
        return self.status in (ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "errors": [f.to_dict() for f in self.errors],
            "warnings": [f.to_dict() for f in self.warnings],
            "info": [f.to_dict() for f in self.info],
            "affected_objects": list(self.affected_objects),
        }


__all__ = ["ValidationResult", "ValidationStatus", "Finding"]
