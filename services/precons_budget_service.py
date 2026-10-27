"""PreconsBudgetService (v2.0.0) — presupuesto por catálogo PRECONS III.

Construye presupuestos reales con los 15981 renglones oficiales del
catálogo PRECONS III (RoPres 3.30): cada línea toma su precio oficial
CUP del ruleset, se agrupa por sección del catálogo (capítulos) y
totaliza con los coeficientes de la ruleset (transporte, indirectos,
beneficio). Persiste en las tablas estándar de presupuesto
(budgets / budget_chapters / budget_items) vía BudgetRepository, de
modo que el presupuesto viaja con el proyecto y es auditable.

Los precios nunca se copian a la base: los items guardan código y
cantidad, y el desglose se resuelve siempre desde el ruleset (fuente
única de verdad). La columna ``performance`` guarda una instantánea
del precio oficial al momento de editar, solo informativa.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from core.errors import DomainError
from engines.precons_engine import PreconsRuleset, is_official_item
from services.context import ProjectContext

DEFAULT_RULESET = "precons_iii_rospres_330"


class PreconsBudgetService:
    """Presupuesto por renglones del catálogo PRECONS III (v2.0.0)."""

    def __init__(self, context: ProjectContext,
                 ruleset: Optional[PreconsRuleset] = None) -> None:
        self.ctx = context
        self.repo = context.budget_repo
        self.ruleset = ruleset

    # -- ruleset ----------------------------------------------------------
    def load_ruleset(self, code: str = DEFAULT_RULESET) -> PreconsRuleset:
        from app.paths import resource_path
        self.ruleset = PreconsRuleset.from_file(
            resource_path("rulesets", f"{code}.json"))
        return self.ruleset

    def _require_ruleset(self) -> PreconsRuleset:
        if self.ruleset is None:
            raise DomainError(
                message="No hay catálogo PRECONS cargado",
                code="ARQ-PRE-014",
                suggested_action="Llame load_ruleset() antes de operar.")
        return self.ruleset

    # -- ciclo de vida ------------------------------------------------------
    def create(self, name: str = "Presupuesto PRECONS III") -> Dict[str, Any]:
        """Crea el presupuesto (uno activo por proyecto; si existe, lo
        devuelve) con los coeficientes de la ruleset."""
        ruleset = self._require_ruleset()
        existing = self.latest()
        if existing is not None:
            return existing
        coefficients = ruleset.coefficients
        budget = {
            "id": str(uuid.uuid4()),
            "name": name,
            "currency": ruleset.currency,
            "indirect_pct": float(coefficients.get("indirect_pct", 0.0)),
            "other_pct": float(coefficients.get("benefit_pct", 0.0)),
            "status": "DRAFT",
            "ruleset_code": ruleset.code,
            "price_list_code": "PRECONS-OFICIAL",
            "direct_cost": 0.0,
            "indirect_cost": 0.0,
            "other_cost": 0.0,
            "total_cost": 0.0,
        }
        self.repo.save_budget(self.ctx.project.id, budget)
        self.ctx.commit()
        return budget

    def latest(self) -> Optional[Dict[str, Any]]:
        """Último presupuesto PRECONS del proyecto (por ruleset_code).

        Excluye los presupuestos de plantilla de otros módulos (el
        proyecto puede tener varios presupuestos conviviendo).
        """
        ruleset = self._require_ruleset()
        row = self.repo.session.query_one(
            "SELECT * FROM budgets WHERE project_id = ? AND ruleset_code = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (self.ctx.project.id, ruleset.code))
        return dict(row) if row else None

    def get(self, budget_id: str) -> Dict[str, Any]:
        row = self.repo.get_budget(budget_id)
        if row is None:
            raise DomainError(
                message=f"Presupuesto no encontrado: {budget_id}",
                code="ARQ-PRE-015")
        return row

    def ensure_active(self) -> Dict[str, Any]:
        """Presupuesto activo del proyecto (lo crea si no existe)."""
        active = self.latest()
        if active is None:
            active = self.create()
        return active

    # -- edición de líneas --------------------------------------------------
    def add_item(self, item_code: str, quantity: float) -> Dict[str, Any]:
        """Añade (o acumula) un renglón del catálogo al presupuesto."""
        ruleset = self._require_ruleset()
        if quantity < 0:
            raise DomainError(
                message="La cantidad no puede ser negativa",
                code="ARQ-PRE-016", context={"quantity": quantity})
        work_item = ruleset.item(item_code)
        if not is_official_item(work_item):
            raise DomainError(
                message=f"El renglón {item_code} no trae precio oficial",
                code="ARQ-PRE-017",
                suggested_action="Use partidas del catálogo PRECONS III.")
        budget = self.ensure_active()
        tree = self.repo.budget_tree(budget["id"])
        chapter = self._ensure_chapter(budget["id"], tree, work_item)
        price_ref = float(work_item.get("price_ref", 0.0) or 0.0)
        for item in tree["items"]:
            if item["code"] == item_code:
                item["quantity"] = float(item["quantity"]) + float(quantity)
                item["direct_cost"] = round(
                    item["quantity"] * price_ref, 2)
                item["performance"] = price_ref
                self._rewrite(budget["id"], tree["chapters"], tree["items"])
                self.recompute(budget["id"])
                return self.item_view(budget["id"], item_code)
        new_item = {
            "id": str(uuid.uuid4()),
            "chapter_id": chapter["id"],
            "code": work_item["code"],
            "description": work_item.get("name", ""),
            "unit": work_item.get("unit", ""),
            "quantity": float(quantity),
            "performance": price_ref,
            "source": "PRECONS",
            "formula_code": "",
            "direct_cost": round(float(quantity) * price_ref, 2),
        }
        tree["items"].append(new_item)
        self._rewrite(budget["id"], tree["chapters"], tree["items"])
        self.recompute(budget["id"])
        return self.item_view(budget["id"], item_code)

    def set_quantity(self, item_code: str, quantity: float) -> Dict[str, Any]:
        """Fija la cantidad de un renglón del presupuesto."""
        ruleset = self._require_ruleset()
        if quantity < 0:
            raise DomainError(
                message="La cantidad no puede ser negativa",
                code="ARQ-PRE-016", context={"quantity": quantity})
        budget = self.ensure_active()
        tree = self.repo.budget_tree(budget["id"])
        target = None
        for item in tree["items"]:
            if item["code"] == item_code:
                target = item
                break
        if target is None:
            raise DomainError(
                message=f"El renglón {item_code} no está en el presupuesto",
                code="ARQ-PRE-018")
        target["quantity"] = float(quantity)
        price_ref = float(ruleset.item(item_code).get("price_ref", 0.0) or 0.0)
        target["direct_cost"] = round(quantity * price_ref, 2)
        target["performance"] = price_ref
        self._rewrite(budget["id"], tree["chapters"], tree["items"])
        self.recompute(budget["id"])
        return self.item_view(budget["id"], item_code)

    def remove_item(self, item_code: str) -> None:
        """Quita un renglón del presupuesto (y su capítulo si queda vacío)."""
        budget = self.ensure_active()
        tree = self.repo.budget_tree(budget["id"])
        before = len(tree["items"])
        tree["items"] = [i for i in tree["items"] if i["code"] != item_code]
        if len(tree["items"]) == before:
            raise DomainError(
                message=f"El renglón {item_code} no está en el presupuesto",
                code="ARQ-PRE-018")
        used = {i["chapter_id"] for i in tree["items"]}
        tree["chapters"] = [c for c in tree["chapters"]
                            if c["id"] in used]
        self._rewrite(budget["id"], tree["chapters"], tree["items"])
        self.recompute(budget["id"])

    def clear(self) -> int:
        """Vacía el presupuesto; devuelve el número de líneas quitadas."""
        budget = self.ensure_active()
        tree = self.repo.budget_tree(budget["id"])
        count = len(tree["items"])
        self._rewrite(budget["id"], [], [])
        self.recompute(budget["id"])
        return count

    # -- lectura --------------------------------------------------------------
    def tree(self) -> Dict[str, Any]:
        """Presupuesto completo: totales + capítulos (secciones) +
        renglones con desglose oficial resuelto desde el ruleset."""
        ruleset = self._require_ruleset()
        budget = self.ensure_active()
        data = self.repo.budget_tree(budget["id"])
        chapters: List[Dict[str, Any]] = []
        for chapter in sorted(data["chapters"],
                              key=lambda c: (c["position"], c["code"])):
            rows: List[Dict[str, Any]] = []
            chapter_direct = 0.0
            chapter_material = 0.0
            chapter_labor = 0.0
            chapter_equipment = 0.0
            for item in data["items"]:
                if item["chapter_id"] != chapter["id"]:
                    continue
                view = self.item_view(budget["id"], item["code"])
                rows.append(view)
                chapter_direct += view["amount"]
                chapter_material += view["material"]
                chapter_labor += view["labor"]
                chapter_equipment += view["equipment"]
            chapters.append({
                "code": chapter["code"], "name": chapter["name"],
                "items": rows, "direct": round(chapter_direct, 2),
                "material": round(chapter_material, 2),
                "labor": round(chapter_labor, 2),
                "equipment": round(chapter_equipment, 2),
            })
        return {
            "budget": self.get(budget["id"]),
            "ruleset": ruleset.code,
            "ruleset_version": ruleset.version,
            "currency": ruleset.currency,
            "chapters": chapters,
            **self.totals(),
        }

    def item_view(self, budget_id: str, item_code: str) -> Dict[str, Any]:
        """Renglón con precio oficial y desglose resuelto del ruleset."""
        ruleset = self._require_ruleset()
        data = self.repo.budget_tree(budget_id)
        for item in data["items"]:
            if item["code"] == item_code:
                official = ruleset.official_price(item_code)
                quantity = float(item["quantity"])
                return {
                    "code": item["code"],
                    "description": item["description"],
                    "unit": item["unit"],
                    "quantity": quantity,
                    "unit_price": official["total"],
                    "material": official["material"] * quantity,
                    "labor": official["labor"] * quantity,
                    "equipment": official["equipment"] * quantity,
                    "amount": round(official["total"] * quantity, 2),
                    "section": official.get("section", ""),
                }
        raise DomainError(
            message=f"El renglón {item_code} no está en el presupuesto",
            code="ARQ-PRE-018")

    def lines(self) -> List[Dict[str, Any]]:
        """Renglones planos del presupuesto activo."""
        budget = self.ensure_active()
        data = self.repo.budget_tree(budget["id"])
        return [self.item_view(budget["id"], item["code"])
                for item in sorted(data["items"], key=lambda i: i["code"])]

    # -- totals ------------------------------------------------------------
    def recompute(self, budget_id: str) -> Dict[str, float]:
        """Recalcula totales y los persiste en la fila del presupuesto."""
        totals = self.totals()
        budget = self.get(budget_id)
        budget.update({
            "direct_cost": totals["direct"],
            "indirect_cost": round(totals["indirect"] + totals["transport"], 2),
            "other_cost": totals["benefit"],
            "total_cost": totals["total"],
        })
        self.repo.save_budget(self.ctx.project.id, budget)
        self.ctx.commit()
        return totals

    def totals(self) -> Dict[str, float]:
        """Totales con coeficientes (transporte sobre materiales,
        indirectos y beneficio sobre directo + transporte)."""
        ruleset = self._require_ruleset()
        budget = self.ensure_active()
        data = self.repo.budget_tree(budget["id"])
        coefficients = ruleset.coefficients
        transport_pct = float(coefficients.get("transport_pct", 0.0))
        indirect_pct = float(budget.get("indirect_pct", 0.0))
        benefit_pct = float(budget.get("other_pct", 0.0))
        direct = 0.0
        material = 0.0
        for item in data["items"]:
            official = ruleset.official_price(item["code"])
            quantity = float(item["quantity"])
            direct += official["total"] * quantity
            material += official["material"] * quantity
        transport = material * transport_pct / 100.0
        base = direct + transport
        indirect = base * indirect_pct / 100.0
        benefit = base * benefit_pct / 100.0
        return {
            "direct": round(direct, 2),
            "transport": round(transport, 2),
            "indirect": round(indirect, 2),
            "benefit": round(benefit, 2),
            "total": round(direct + transport + indirect + benefit, 2),
        }

    # -- exportación ---------------------------------------------------------
    def to_csv(self) -> str:
        """CSV del presupuesto completo (secciones, renglones y totales)."""
        tree = self.tree()
        currency = tree.get("currency", "CUP")
        lines = [
            "Seccion;Codigo;Descripcion;Unidad;Cantidad;Precio unitario;"
            "Materiales;Mano de obra;Equipos;Importe;Moneda",
        ]
        for chapter in tree.get("chapters", []):
            for item in chapter.get("items", []):
                lines.append(";".join([
                    f"{chapter['code']} — {chapter['name']}",
                    item["code"], item["description"].replace(";", ","),
                    item["unit"], f"{item['quantity']:.3f}",
                    f"{item['unit_price']:.2f}",
                    f"{item['material']:.2f}", f"{item['labor']:.2f}",
                    f"{item['equipment']:.2f}",
                    f"{item['amount']:.2f}", currency,
                ]))
        totals = {key: tree.get(key, 0.0) for key in
                  ("direct", "transport", "indirect", "benefit", "total")}
        lines.append("")
        lines.append(f"Costo directo;{totals['direct']:.2f};{currency}")
        lines.append(f"Transporte;{totals['transport']:.2f};{currency}")
        lines.append(f"Indirectos;{totals['indirect']:.2f};{currency}")
        lines.append(f"Beneficio;{totals['benefit']:.2f};{currency}")
        lines.append(f"TOTAL;{totals['total']:.2f};{currency}")
        return "\n".join(lines) + "\n"

    def save_csv(self, path: str) -> str:
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(self.to_csv())
        return path

    # -- helpers --------------------------------------------------------------
    def _ensure_chapter(self, budget_id: str, tree: Dict[str, Any],
                        work_item: Dict[str, Any]) -> Dict[str, Any]:
        sec = str(work_item.get("sec", ""))
        sec_name = work_item.get("sec_name", "") or f"Sección {sec}"
        for chapter in tree["chapters"]:
            if chapter["code"] == sec:
                return chapter
        chapter = {
            "id": str(uuid.uuid4()), "budget_id": budget_id,
            "code": sec, "name": sec_name,
            "parent_id": None, "position": len(tree["chapters"]),
        }
        tree["chapters"].append(chapter)
        return chapter

    def _rewrite(self, budget_id: str, chapters: List[Dict[str, Any]],
                 items: List[Dict[str, Any]]) -> None:
        chapters_payload = [{
            "id": c["id"], "code": c["code"], "name": c["name"],
            "parent_id": c.get("parent_id"),
            "position": c.get("position", 0),
        } for c in chapters]
        items_payload = [{
            "id": i["id"], "chapter_id": i["chapter_id"],
            "code": i["code"], "description": i.get("description", ""),
            "unit": i.get("unit", ""), "quantity": i.get("quantity", 0),
            "performance": i.get("performance", 0),
            "source": i.get("source", "PRECONS"),
            "formula_code": i.get("formula_code", ""),
            "direct_cost": i.get("direct_cost", 0),
        } for i in items]
        self.repo.replace_structure(budget_id, chapters_payload,
                                    items_payload, [])
        self.ctx.commit()


__all__ = ["PreconsBudgetService", "DEFAULT_RULESET"]
