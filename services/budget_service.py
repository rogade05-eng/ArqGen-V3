"""PricingService and BudgetService (spec sections 53-62).

The budget is a CONSEQUENCE of the model: MODEL → QTO → WORK ITEMS →
RESOURCES → PRICES → INDIRECT → TOTAL. The QTO→item mapping lives in
data templates (resources/budget_templates/*.json), never in code.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.calculations.contracts import BudgetResult
from core.errors import CalculationError, DomainError
from engines.budget_engine import BudgetEngine, Chapter, ItemResourceLink, WorkItem, resolve_item_costs
from engines.pricing_engine import RESOURCE_TYPES, PricingEngine
from services.context import ProjectContext


class PricingService:
    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context
        self.repo = context.budget_repo
        self.engine = PricingEngine(self.repo)

    # -- resources ------------------------------------------------------------
    def add_resource(self, code: str, name: str, type_: str, unit: str,
                     category: str = "", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if type_ not in RESOURCE_TYPES:
            raise DomainError(
                message=f"Tipo de recurso inválido: {type_}",
                code="ARQ-DOM-012",
                context={"type": type_, "allowed": list(RESOURCE_TYPES)},
            )
        existing = self.repo.get_resource_by_code(self.ctx.project.id, code)
        if existing:
            raise DomainError(
                message=f"Ya existe un recurso con el código {code}",
                code="ARQ-DOM-060",
                suggested_action="Use otro código o actualice el recurso existente.",
            )
        resource_id = str(uuid.uuid4())
        self.repo.save_resource(self.ctx.project.id, resource_id, code, name, type_,
                                unit, category, metadata)
        resource = self.repo.get_resource_by_code(self.ctx.project.id, code)
        self.ctx.emit("OBJECT_CREATED", {"type": "RESOURCE", "code": code})
        return resource  # type: ignore[return-value]

    def resources(self) -> List[Dict[str, Any]]:
        return self.repo.list_resources(self.ctx.project.id)

    def resource_by_code(self, code: str) -> Dict[str, Any]:
        resource = self.repo.get_resource_by_code(self.ctx.project.id, code)
        if resource is None:
            raise DomainError(
                message=f"Recurso no encontrado: {code}", code="ARQ-DOM-061",
                suggested_action="Regístrelo con 'resource add'.")
        return resource

    # -- price lists -------------------------------------------------------------
    def ensure_price_list(self, code: str, name: str = "", currency: str = "CUP",
                          region: str = "") -> Dict[str, Any]:
        existing = self.repo.get_price_list_by_code(self.ctx.project.id, code)
        if existing:
            return existing
        list_id = str(uuid.uuid4())
        self.repo.save_price_list(self.ctx.project.id, list_id, code,
                                  name or code, currency, region)
        return self.repo.get_price_list_by_code(self.ctx.project.id, code)  # type: ignore[return-value]

    def price_list(self, code: str) -> Dict[str, Any]:
        plist = self.repo.get_price_list_by_code(self.ctx.project.id, code)
        if plist is None:
            raise DomainError(
                message=f"Lista de precios no encontrada: {code}", code="ARQ-DOM-062")
        return plist

    # -- historical prices (spec 61) ------------------------------------------------
    def set_price(self, resource_code: str, price: float, price_list_code: str,
                  date_iso: Optional[str] = None, currency: str = "CUP",
                  region: str = "", note: str = "") -> Dict[str, Any]:
        if price < 0:
            raise DomainError(message="El precio no puede ser negativo", code="ARQ-DOM-063")
        resource = self.resource_by_code(resource_code)
        plist = self.ensure_price_list(price_list_code, currency=currency, region=region)
        valid_from = date_iso or datetime.now().strftime("%Y-%m-%d")
        price_id = self.repo.add_price(
            self.ctx.project.id, resource["id"], plist["id"], float(price),
            currency, region, valid_from, note)
        self.ctx.emit("PRICE_CHANGED", {"resource": resource_code, "price": price,
                                        "valid_from": valid_from})
        return {"resource": resource_code, "price": price, "price_list": price_list_code,
                "valid_from": valid_from, "id": price_id}

    def current_price(self, resource_code: str, price_list_code: str,
                      date_iso: Optional[str] = None, region: str = "") -> float:
        resource = self.resource_by_code(resource_code)
        plist = self.price_list(price_list_code)
        date = date_iso or datetime.now().strftime("%Y-%m-%d")
        return self.engine.price_or_fail(resource_code, resource["id"], date,
                                         plist["id"], region)

    def price_history(self, resource_code: str, price_list_code: str) -> List[Dict[str, Any]]:
        resource = self.resource_by_code(resource_code)
        plist = self.price_list(price_list_code)
        return self.engine.history(resource["id"], plist["id"])


@dataclass
class BudgetTemplateResource:
    resource_code: str
    factor: float
    waste_pct: float = 0.0
    kind: str = "MATERIAL"


@dataclass
class BudgetTemplateItem:
    code: str
    description: str
    unit: str
    quantity_source: Dict[str, Any]
    resources: List[BudgetTemplateResource] = field(default_factory=list)
    performance: float = 0.0


@dataclass
class BudgetTemplate:
    code: str
    name: str
    currency: str
    indirect_pct: float
    other_pct: float
    price_list: str
    chapters: List[Dict[str, Any]] = field(default_factory=list)  # {code, name, items: [...]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BudgetTemplate":
        return cls(
            code=data["code"], name=data.get("name", data["code"]),
            currency=data.get("currency", "CUP"),
            indirect_pct=float(data.get("indirect_pct", 0.0)),
            other_pct=float(data.get("other_pct", 0.0)),
            price_list=data.get("price_list", "GENERAL"),
            chapters=data.get("chapters", []),
        )


class BudgetService:
    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context
        self.engine = BudgetEngine()
        self.pricing = PricingService(context)

    def load_template(self, code: str) -> BudgetTemplate:
        from app.paths import resource_path
        path = resource_path("budget_templates", f"{code}.json")
        if not os.path.exists(path):
            raise DomainError(
                message=f"Plantilla de presupuesto no encontrada: {code}",
                code="ARQ-DOM-064",
                context={"path": path},
            )
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return BudgetTemplate.from_dict(data)

    def _quantity_for_source(self, source: Dict[str, Any]) -> float:
        kind = source.get("kind", "qto_formula")
        quantities_repo = self.ctx.quantities_repo
        if kind == "qto_formula":
            formula_code = source.get("qto_formula") or source.get("formula")
            if not formula_code:
                raise DomainError(message="quantity_source sin fórmula", code="ARQ-DOM-065")
            aggregate = source.get("aggregate", "SUM")
            if aggregate == "SUM":
                return round(quantities_repo.total(self.ctx.project.id, formula_code), 4)
            if aggregate == "COUNT":
                return float(len(quantities_repo.all(self.ctx.project.id)))
            raise DomainError(message=f"Agregación desconocida: {aggregate}", code="ARQ-DOM-066")
        if kind == "count_type":
            entity_type = source.get("entity_type", "")
            return float(self.ctx.architecture.count(entity_type, self.ctx.project.id))
        if kind == "fixed":
            return float(source.get("value", 0.0))
        raise DomainError(message=f"Tipo de quantity_source desconocido: {kind}",
                          code="ARQ-DOM-067")

    def compute_budget(self, template_code: str, name: str = "",
                       date_iso: Optional[str] = None) -> BudgetResult:
        template = self.load_template(template_code)
        plist = self.pricing.ensure_price_list(template.price_list, currency=template.currency)
        budget_id = str(uuid.uuid4())
        chapters: List[Chapter] = []
        all_items: List[WorkItem] = []

        for chapter_def in template.chapters:
            chapter = Chapter(code=chapter_def["code"], name=chapter_def.get("name", ""))
            for item_def in chapter_def.get("items", []):
                quantity = self._quantity_for_source(item_def.get("quantity_source", {}))
                links = [
                    ItemResourceLink(
                        resource_code=r["resource_code"], resource_id="", factor=float(r["factor"]),
                        waste_pct=float(r.get("waste_pct", 0.0)), kind=r.get("kind", "MATERIAL"))
                    for r in item_def.get("resources", [])
                ]
                item = WorkItem(
                    code=item_def["code"], description=item_def.get("description", ""),
                    unit=item_def.get("unit", ""), quantity=quantity,
                    resources=links, performance=float(item_def.get("performance", 0.0)),
                    formula_code=item_def.get("quantity_source", {}).get("qto_formula", ""),
                    source=f"template:{template.code}")
                all_items.append(item)
                chapter.items.append(item)
            chapters.append(chapter)

        # Resolve resource ids and prices (spec 61: historical lookup).
        def price_of_resource_id(resource_id: str) -> float:
            return self.pricing.engine.get_price(
                resource_id, date_iso or datetime.now().strftime("%Y-%m-%d"),
                price_list_id=plist["id"]) or 0.0

        resource_cache: Dict[str, Dict[str, Any]] = {}
        for item in all_items:
            for link in item.resources:
                if link.resource_code not in resource_cache:
                    resource_cache[link.resource_code] = self.pricing.resource_by_code(
                        link.resource_code)
                link.resource_id = resource_cache[link.resource_code]["id"]
            resolve_item_costs(item, price_of_resource_id)

        result = self.engine.compute(
            chapters, template.indirect_pct, template.other_pct,
            self.ctx.project.id, template.currency, template.price_list,
            ruleset=self.ctx.project.ruleset_code or "none")

        # Persist the budget structure and totals (traceable, versioned).
        chapter_rows = []
        item_rows = []
        item_resource_rows = []
        chapter_id_by_code: Dict[str, str] = {}
        for index, chapter in enumerate(chapters):
            chapter_id = str(uuid.uuid4())
            chapter_id_by_code[chapter.code] = chapter_id
            chapter_rows.append({"id": chapter_id, "code": chapter.code,
                                 "name": chapter.name, "parent_id": None, "position": index})
        for item in all_items:
            parent_code = item.code.split(".")[0] if "." in item.code else item.code
            chapter_id = chapter_id_by_code.get(parent_code) or next(iter(chapter_id_by_code.values()))
            item_rows.append({
                "id": str(uuid.uuid4()) , "chapter_id": chapter_id, "code": item.code,
                "description": item.description, "unit": item.unit,
                "quantity": item.quantity, "performance": item.performance,
                "source": item.source, "formula_code": item.formula_code,
                "direct_cost": round(item.direct_cost, 2),
            })
        item_resource_rows = []
        for row, item in zip(item_rows, all_items):
            for link in item.resources:
                item_resource_rows.append({
                    "item_id": row["id"], "resource_id": link.resource_id,
                    "factor": link.factor, "waste_pct": link.waste_pct, "kind": link.kind,
                })
        self.ctx.budget_repo.replace_structure(budget_id, chapter_rows, item_rows, item_resource_rows)
        self.ctx.budget_repo.save_budget(self.ctx.project.id, {
            "id": budget_id, "name": name or template.name, "currency": template.currency,
            "indirect_pct": template.indirect_pct, "other_pct": template.other_pct,
            "status": "COMPLETED", "ruleset_code": self.ctx.project.ruleset_code,
            "price_list_code": template.price_list, "direct_cost": result.direct_cost,
            "indirect_cost": result.indirect_cost, "other_cost": result.other_cost,
            "total_cost": result.total,
        })
        self.ctx.emit("BUDGET_CHANGED", {"budget_id": budget_id, "total": result.total})
        return result

    def latest_budget(self) -> Optional[Dict[str, Any]]:
        return self.ctx.budget_repo.latest_budget(self.ctx.project.id)

    def list_budgets(self) -> List[Dict[str, Any]]:
        return self.ctx.budget_repo.list_budgets(self.ctx.project.id)


__all__ = ["PricingService", "BudgetService", "BudgetTemplate", "RESOURCE_TYPES"]
