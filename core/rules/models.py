"""Rule and Ruleset models (spec sections 12, 13).

Rules are parametrizable data. Norms are never embedded in code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.entities.base import Entity
from core.errors import RuleError
from core.rules.evaluator import Expression


class RuleSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    HARD_BLOCK = "HARD_BLOCK"


@dataclass
class Rule:
    """A single parametrizable rule (spec section 12)."""

    code: str
    discipline: str
    category: str
    severity: RuleSeverity
    expression: str
    message: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    source: str = "ARQ GEN"
    version: str = "1.0"
    applies_to: str = "*"  # entity type filter, * = all
    id: str = ""

    def __post_init__(self) -> None:
        # Validate expression at construction: bad rules fail fast.
        self._compiled: Expression = Expression(self.expression)

    @property
    def compiled(self) -> Expression:
        return self._compiled

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "discipline": self.discipline,
            "category": self.category,
            "severity": self.severity.value,
            "expression": self.expression,
            "message": self.message,
            "parameters": self.parameters,
            "source": self.source,
            "version": self.version,
            "applies_to": self.applies_to,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        return cls(
            code=data["code"],
            discipline=data.get("discipline", "GENERAL"),
            category=data.get("category", "GENERAL"),
            severity=RuleSeverity(data.get("severity", "WARNING")),
            expression=data["expression"],
            message=data.get("message", ""),
            parameters=dict(data.get("parameters", {})),
            source=data.get("source", "ARQ GEN"),
            version=data.get("version", "1.0"),
            applies_to=data.get("applies_to", "*"),
        )


@dataclass
class Ruleset:
    """A versioned set of rules for a jurisdiction/discipline (spec 13)."""

    code: str
    jurisdiction: str
    discipline: str
    version: str
    effective_date: str
    source: str
    rules: List[Rule] = field(default_factory=list)
    id: str = ""

    def rule(self, code: str) -> Optional[Rule]:
        for rule in self.rules:
            if rule.code == code:
                return rule
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "jurisdiction": self.jurisdiction,
            "discipline": self.discipline,
            "version": self.version,
            "effective_date": self.effective_date,
            "source": self.source,
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Ruleset":
        return cls(
            code=data["code"],
            jurisdiction=data.get("jurisdiction", ""),
            discipline=data.get("discipline", "GENERAL"),
            version=data.get("version", "1.0"),
            effective_date=data.get("effective_date", ""),
            source=data.get("source", ""),
            rules=[Rule.from_dict(r) for r in data.get("rules", [])],
        )


__all__ = ["Rule", "Ruleset", "RuleSeverity"]
