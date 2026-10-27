"""Pricing engine: versioned price lists and historical prices (spec 61, 62).

get_price(resource_id, date, region, currency, price_list) with full
history. A previous price is NEVER silently overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.errors import CalculationError
from persistence.repositories.qto_budget_repos import BudgetRepository

RESOURCE_TYPES = ("MATERIAL", "LABOR", "EQUIPMENT", "CONSUMABLE", "TRANSPORT", "OTHER")


@dataclass
class Resource:
    code: str
    name: str
    type: str
    unit: str
    category: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if self.type not in RESOURCE_TYPES:
            from core.errors import DomainError
            raise DomainError(
                message=f"Tipo de recurso inválido: {self.type}",
                code="ARQ-DOM-012",
                context={"type": self.type, "allowed": list(RESOURCE_TYPES)},
            )


class PricingEngine:
    """Historical, append-only price management."""

    def __init__(self, repo: BudgetRepository) -> None:
        self.repo = repo

    def get_price(self, resource_id: str, date_iso: str, region: str = "",
                  currency: str = "", price_list_id: str = "") -> Optional[float]:
        """Latest effective price valid_from <= date; history is preserved."""
        return self.repo.get_price(resource_id, price_list_id, date_iso, region)

    def price_or_fail(self, resource_code: str, resource_id: str, date_iso: str,
                      price_list_id: str, region: str = "") -> float:
        price = self.get_price(resource_id, date_iso, region, price_list_id=price_list_id)
        if price is None:
            raise CalculationError(
                message=f"El recurso '{resource_code}' no tiene precio vigente a la fecha {date_iso}",
                code="ARQ-CAL-020",
                context={"resource": resource_code, "date": date_iso},
                object_ids=[resource_id],
                suggested_action="Registre un precio para el recurso con 'price set' antes de presupuestar.",
            )
        return price

    def history(self, resource_id: str, price_list_id: str) -> List[Dict[str, Any]]:
        return self.repo.price_history(resource_id, price_list_id)


__all__ = ["PricingEngine", "Resource", "RESOURCE_TYPES"]
