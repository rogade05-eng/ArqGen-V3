"""Budget engine: MODEL → QTO → WORK ITEMS → RESOURCES → PRICES → TOTAL (spec 53-62)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.calculations.contracts import BudgetResult
from core.errors import CalculationError, DomainError


@dataclass
class ItemResourceLink:
    resource_id: str
    resource_code: str
    factor: float          # quantity of resource per unit of work item
    waste_pct: float = 0.0
    kind: str = "MATERIAL"

    def __post_init__(self) -> None:
        if self.factor < 0:
            raise DomainError(
                message="El factor de recurso no puede ser negativo",
                code="ARQ-DOM-013",
            )


@dataclass
class WorkItem:
    """Partida de obra (spec section 55)."""

    code: str
    description: str
    unit: str
    quantity: float
    resources: List[ItemResourceLink] = field(default_factory=list)
    performance: float = 0.0          # units/day; 0 = not defined
    formula_code: str = ""
    source: str = "QTO"
    id: str = ""

    @property
    def direct_cost(self) -> float:
        total = 0.0
        for res in self.resources:
            price = getattr(res, "_price", None)
            if price is None:
                raise CalculationError(
                    message=f"La partida '{self.code}' tiene recursos sin precio resuelto",
                    code="ARQ-CAL-022",
                    object_ids=[res.resource_id],
                    suggested_action="Ejecute resolve_item_costs antes de calcular la partida.",
                )
            total += self.quantity * res.factor * (1.0 + res.waste_pct / 100.0) * price
        return total

    @property
    def labor_hours(self) -> float:
        """Estimated labor hours from LABOR resources with factor in hours/unit."""
        return sum(
            self.quantity * r.factor * (1.0 + r.waste_pct / 100.0)
            for r in self.resources if r.kind == "LABOR"
        )


@dataclass
class Chapter:
    """Chapter / subchapter of the budget tree (spec section 54)."""

    code: str
    name: str
    parent: Optional["Chapter"] = None
    items: List[WorkItem] = field(default_factory=list)
    id: str = ""
    position: int = 0

    @property
    def direct_cost(self) -> float:
        own = sum(item.direct_cost for item in self.items)
        return own


@dataclass
class _PricedResource:
    """Internal link carrying resolved price (kept out of persisted data)."""

    resource_id: str
    price: float


def resolve_item_costs(item: WorkItem, price_of: Any) -> WorkItem:
    """Attach resolved prices through the callable price_of(resource_id)->float."""
    for link in item.resources:
        price = price_of(link.resource_id)
        if price is None:
            raise CalculationError(
                message=f"Recurso sin precio: {link.resource_code}",
                code="ARQ-CAL-021",
                object_ids=[link.resource_id],
                suggested_action="Registre precios para todos los recursos de la partida.",
            )
        setattr(link, "_price", price)  # transient, never persisted
    return item


def build_budget_result(direct: float, indirect_pct: float, other_pct: float,
                        project_id: str, currency: str, price_list: str,
                        ruleset: str) -> BudgetResult:
    if indirect_pct < 0 or other_pct < 0:
        raise DomainError(
            message="Los porcentajes indirectos no pueden ser negativos",
            code="ARQ-DOM-014",
            context={"indirect_pct": indirect_pct, "other_pct": other_pct},
        )
    indirect = direct * indirect_pct / 100.0
    other = direct * other_pct / 100.0
    return BudgetResult(
        project_id=project_id, version="1.0", price_list=price_list, ruleset=ruleset,
        direct_cost=direct, indirect_cost=indirect, other_cost=other,
        total=direct + indirect + other, currency=currency,
    )


__all__ = ["BudgetEngine", "Chapter", "WorkItem", "ItemResourceLink", "build_budget_result", "resolve_item_costs"]


class BudgetEngine:
    """Budget calculation over resolved work items."""

    def compute(self, chapters: List[Chapter], indirect_pct: float, other_pct: float,
                project_id: str, currency: str, price_list: str, ruleset: str) -> BudgetResult:
        direct = 0.0
        for chapter in chapters:
            for item in chapter.items:
                direct += item.direct_cost
        return build_budget_result(direct, indirect_pct, other_pct,
                                   project_id, currency, price_list, ruleset)
