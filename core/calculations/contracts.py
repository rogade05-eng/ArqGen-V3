"""Calculation contracts (spec sections 102-104) and calculation modes (85).

Every calculation must produce a reproducible CalculationResult with
input hash, formula version, ruleset version, values, units, warnings,
errors, engine version and timestamp.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from core import APP_VERSION
from core.entities.base import CalculationStatus, new_uuid, utc_now


class CalculationMode(str, Enum):
    """Modes FAST / BALANCED / DEEP (spec section 85)."""

    FAST = "FAST"
    BALANCED = "BALANCED"
    DEEP = "DEEP"


def input_hash_of(objects: List[Dict[str, Any]], parameters: Optional[Dict[str, Any]] = None,
                  extra: Optional[Dict[str, Any]] = None) -> str:
    """Deterministic SHA-256 of the participating objects + parameters."""
    payload = {
        "objects": sorted(objects, key=lambda o: (o.get("type", ""), o.get("id", ""), o.get("revision", 0))),
        "parameters": parameters or {},
        "extra": extra or {},
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class CalculationResult:
    """Reproducible calculation contract (spec section 102)."""

    calculation_type: str
    input_objects: List[Dict[str, Any]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    values: Dict[str, float] = field(default_factory=dict)
    units: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    formula_version: str = "1.0"
    ruleset_version: str = "none"
    engine_version: str = APP_VERSION
    mode: CalculationMode = CalculationMode.BALANCED
    status: CalculationStatus = CalculationStatus.COMPLETED
    duration_ms: float = 0.0
    objects_processed: int = 0
    id: str = field(default_factory=new_uuid)
    input_hash: str = ""
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.input_hash:
            self.input_hash = input_hash_of(self.input_objects, self.parameters)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "calculation_type": self.calculation_type,
            "input_objects": self.input_objects,
            "input_hash": self.input_hash,
            "formula_version": self.formula_version,
            "ruleset_version": self.ruleset_version,
            "parameters": self.parameters,
            "values": self.values,
            "units": self.units,
            "warnings": self.warnings,
            "errors": self.errors,
            "engine_version": self.engine_version,
            "mode": self.mode.value,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "objects_processed": self.objects_processed,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class QuantityResult:
    """Quantity contract (spec section 103): traceable origin."""

    source_objects: List[Dict[str, Any]] = field(default_factory=list)
    formula_code: str = ""
    formula_expression: str = ""
    variables: Dict[str, float] = field(default_factory=dict)
    raw_quantity: float = 0.0
    waste_factor: float = 0.0
    final_quantity: float = 0.0
    unit: str = ""
    source: str = ""
    id: str = field(default_factory=new_uuid)

    def __post_init__(self) -> None:
        if self.final_quantity == 0.0 and self.raw_quantity:
            self.final_quantity = self.raw_quantity * (1.0 + self.waste_factor)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_objects": self.source_objects,
            "formula_code": self.formula_code,
            "formula_expression": self.formula_expression,
            "variables": self.variables,
            "raw_quantity": self.raw_quantity,
            "waste_factor": self.waste_factor,
            "final_quantity": round(self.final_quantity, 6),
            "unit": self.unit,
            "source": self.source,
        }


@dataclass
class BudgetResult:
    """Budget contract (spec section 104)."""

    project_id: str = ""
    version: str = "1.0"
    price_list: str = ""
    ruleset: str = ""
    direct_cost: float = 0.0
    indirect_cost: float = 0.0
    other_cost: float = 0.0
    total: float = 0.0
    currency: str = "CUP"
    timestamp: datetime = field(default_factory=utc_now)
    id: str = field(default_factory=new_uuid)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "version": self.version,
            "price_list": self.price_list,
            "ruleset": self.ruleset,
            "direct_cost": round(self.direct_cost, 2),
            "indirect_cost": round(self.indirect_cost, 2),
            "other_cost": round(self.other_cost, 2),
            "total": round(self.total, 2),
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
        }


__all__ = [
    "CalculationResult", "QuantityResult", "BudgetResult",
    "CalculationMode", "input_hash_of",
]
