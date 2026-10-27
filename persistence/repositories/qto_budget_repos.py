"""Repositories for QTO quantities and budget structures (spec 51-62)."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Dict, List, Optional

from core.entities.base import utc_now
from persistence.sqlite.connection import Session, json_dumps, json_loads


class QuantityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, project_id: str, object_id: str, object_type: str, object_code: str,
             formula_code: str, formula_expression: str, variables: Dict[str, float],
             raw_quantity: float, waste_factor: float, final_quantity: float,
             unit: str, source: str, input_hash: str) -> str:
        existing = self.session.query_one(
            "SELECT id FROM quantities WHERE object_id = ? AND formula_code = ?",
            (object_id, formula_code))
        quantity_id = existing["id"] if existing else str(uuid.uuid4())
        self.session.execute(
            "INSERT INTO quantities (id, project_id, object_id, object_type, object_code, "
            "formula_code, formula_expression, variables_json, raw_quantity, waste_factor, "
            "final_quantity, unit, source, input_hash, stale, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?) "
            "ON CONFLICT(id) DO UPDATE SET variables_json=excluded.variables_json, "
            "raw_quantity=excluded.raw_quantity, waste_factor=excluded.waste_factor, "
            "final_quantity=excluded.final_quantity, input_hash=excluded.input_hash, "
            "stale=0, computed_at=excluded.computed_at",
            (quantity_id, project_id, object_id, object_type, object_code, formula_code,
             formula_expression, json_dumps(variables), raw_quantity, waste_factor,
             final_quantity, unit, source, input_hash, utc_now().isoformat()),
        )
        return quantity_id

    def for_object(self, object_id: str) -> List[Dict[str, Any]]:
        rows = self.session.query_all(
            "SELECT * FROM quantities WHERE object_id = ? ORDER BY formula_code", (object_id,))
        return [self._dict(r) for r in rows]

    def all(self, project_id: str, only_stale: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM quantities WHERE project_id = ?"
        if only_stale:
            sql += " AND stale = 1"
        sql += " ORDER BY object_code, formula_code"
        rows = self.session.query_all(sql, (project_id,))
        return [self._dict(r) for r in rows]

    def total(self, project_id: str, formula_code: str = "") -> float:
        sql = "SELECT COALESCE(SUM(final_quantity), 0) AS t FROM quantities WHERE project_id = ?"
        params: list[Any] = [project_id]
        if formula_code:
            sql += " AND formula_code = ?"
            params.append(formula_code)
        row = self.session.query_one(sql, tuple(params))
        return float(row["t"]) if row else 0.0

    def mark_stale_for_object(self, object_id: str) -> int:
        cursor = self.session.execute(
            "UPDATE quantities SET stale = 1 WHERE object_id = ?", (object_id,))
        return cursor.rowcount

    def mark_all_stale(self, project_id: str) -> int:
        cursor = self.session.execute(
            "UPDATE quantities SET stale = 1 WHERE project_id = ?", (project_id,))
        return cursor.rowcount

    def delete_for_object(self, object_id: str) -> int:
        cursor = self.session.execute("DELETE FROM quantities WHERE object_id = ?", (object_id,))
        return cursor.rowcount

    def count(self, project_id: str) -> int:
        row = self.session.query_one(
            "SELECT COUNT(*) AS n FROM quantities WHERE project_id = ?", (project_id,))
        return int(row["n"]) if row else 0

    @staticmethod
    def _dict(r: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": r["id"], "project_id": r["project_id"], "object_id": r["object_id"],
            "object_type": r["object_type"], "object_code": r["object_code"],
            "formula_code": r["formula_code"], "formula_expression": r["formula_expression"],
            "variables": json_loads(r["variables_json"], {}) or {},
            "raw_quantity": r["raw_quantity"], "waste_factor": r["waste_factor"],
            "final_quantity": r["final_quantity"], "unit": r["unit"], "source": r["source"],
            "input_hash": r["input_hash"], "stale": bool(r["stale"]),
            "computed_at": r["computed_at"],
        }


class BudgetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- resources -------------------------------------------------------
    def save_resource(self, project_id: str, resource_id: str, code: str, name: str,
                      type_: str, unit: str, category: str = "",
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        now = utc_now().isoformat()
        self.session.execute(
            "INSERT INTO resources (id, project_id, code, name, type, unit, category, metadata_json, "
            "discipline, level_id, status, revision, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'BUDGET', NULL, 'ACTIVE', 1, ?, ?) "
            "ON CONFLICT(project_id, code) DO UPDATE SET name=excluded.name, type=excluded.type, "
            "unit=excluded.unit, category=excluded.category, metadata_json=excluded.metadata_json, "
            "updated_at=excluded.updated_at, revision=resources.revision+1",
            (resource_id, project_id, code, name, type_, unit, category,
             json_dumps(metadata or {}), now, now),
        )

    def get_resource_by_code(self, project_id: str, code: str) -> Optional[Dict[str, Any]]:
        row = self.session.query_one(
            "SELECT * FROM resources WHERE project_id = ? AND code = ?", (project_id, code))
        return self._resource_dict(row) if row else None

    def list_resources(self, project_id: str) -> List[Dict[str, Any]]:
        rows = self.session.query_all(
            "SELECT * FROM resources WHERE project_id = ? ORDER BY code", (project_id,))
        return [self._resource_dict(r) for r in rows]

    # -- price lists & historical prices ----------------------------------
    def save_price_list(self, project_id: str, list_id: str, code: str, name: str,
                        currency: str, region: str = "") -> None:
        self.session.execute(
            "INSERT INTO price_lists (id, project_id, code, name, currency, region) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, code) DO UPDATE SET name=excluded.name, "
            "currency=excluded.currency, region=excluded.region",
            (list_id, project_id, code, name, currency, region),
        )

    def get_price_list_by_code(self, project_id: str, code: str) -> Optional[Dict[str, Any]]:
        row = self.session.query_one(
            "SELECT * FROM price_lists WHERE project_id = ? AND code = ?", (project_id, code))
        return dict(row) if row else None

    def add_price(self, project_id: str, resource_id: str, price_list_id: str, price: float,
                  currency: str, region: str, valid_from: str, note: str = "") -> str:
        price_id = str(uuid.uuid4())
        self.session.execute(
            "INSERT INTO prices (id, project_id, resource_id, price_list_id, price, currency, "
            "region, valid_from, created_at, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (price_id, project_id, resource_id, price_list_id, price, currency,
             region, valid_from, utc_now().isoformat(), note),
        )
        return price_id

    def price_history(self, resource_id: str, price_list_id: str) -> List[Dict[str, Any]]:
        rows = self.session.query_all(
            "SELECT * FROM prices WHERE resource_id = ? AND price_list_id = ? ORDER BY valid_from",
            (resource_id, price_list_id))
        return [dict(r) for r in rows]

    def get_price(self, resource_id: str, price_list_id: str, date_iso: str,
                  region: str = "") -> Optional[float]:
        """Latest price whose valid_from <= date. Never mutates history (spec 61)."""
        sql = (
            "SELECT price FROM prices WHERE resource_id = ? AND price_list_id = ? "
            "AND valid_from <= ?"
        )
        params: list[Any] = [resource_id, price_list_id, date_iso]
        if region:
            sql += " AND (region = ? OR region = '')"
            params.append(region)
        sql += " ORDER BY valid_from DESC, created_at DESC LIMIT 1"
        row = self.session.query_one(sql, tuple(params))
        return float(row["price"]) if row else None

    # -- budgets ----------------------------------------------------------
    def save_budget(self, project_id: str, budget: Dict[str, Any]) -> None:
        now = utc_now().isoformat()
        self.session.execute(
            "INSERT INTO budgets (id, project_id, name, currency, indirect_pct, other_pct, status, "
            "ruleset_code, price_list_code, direct_cost, indirect_cost, other_cost, total_cost, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, currency=excluded.currency, "
            "indirect_pct=excluded.indirect_pct, other_pct=excluded.other_pct, "
            "status=excluded.status, ruleset_code=excluded.ruleset_code, "
            "price_list_code=excluded.price_list_code, direct_cost=excluded.direct_cost, "
            "indirect_cost=excluded.indirect_cost, other_cost=excluded.other_cost, "
            "total_cost=excluded.total_cost, updated_at=excluded.updated_at",
            (
                budget["id"], project_id, budget.get("name", ""), budget.get("currency", "CUP"),
                budget.get("indirect_pct", 0), budget.get("other_pct", 0),
                budget.get("status", "DRAFT"), budget.get("ruleset_code", ""),
                budget.get("price_list_code", ""), budget.get("direct_cost", 0),
                budget.get("indirect_cost", 0), budget.get("other_cost", 0),
                budget.get("total_cost", 0), budget.get("created_at", now), now,
            ),
        )

    def list_budgets(self, project_id: str) -> List[Dict[str, Any]]:
        rows = self.session.query_all(
            "SELECT id, name, currency, indirect_pct, other_pct, status, direct_cost, "
            "indirect_cost, other_cost, total_cost, created_at, updated_at "
            "FROM budgets WHERE project_id = ? ORDER BY created_at", (project_id,))
        return [dict(r) for r in rows]

    def get_budget(self, budget_id: str) -> Optional[Dict[str, Any]]:
        row = self.session.query_one("SELECT * FROM budgets WHERE id = ?", (budget_id,))
        return dict(row) if row else None

    def latest_budget(self, project_id: str) -> Optional[Dict[str, Any]]:
        row = self.session.query_one(
            "SELECT * FROM budgets WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (project_id,))
        return dict(row) if row else None

    def replace_structure(self, budget_id: str, chapters: List[Dict[str, Any]],
                          items: List[Dict[str, Any]],
                          item_resources: List[Dict[str, Any]]) -> None:
        self.session.execute("DELETE FROM budget_item_resources WHERE item_id IN "
                             "(SELECT id FROM budget_items WHERE chapter_id IN "
                             "(SELECT id FROM budget_chapters WHERE budget_id = ?))", (budget_id,))
        self.session.execute(
            "DELETE FROM budget_items WHERE chapter_id IN "
            "(SELECT id FROM budget_chapters WHERE budget_id = ?)", (budget_id,))
        self.session.execute("DELETE FROM budget_chapters WHERE budget_id = ?", (budget_id,))
        for chapter in chapters:
            self.session.execute(
                "INSERT INTO budget_chapters (id, budget_id, code, name, parent_id, position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chapter["id"], budget_id, chapter.get("code", ""), chapter.get("name", ""),
                 chapter.get("parent_id"), chapter.get("position", 0)),
            )
        for item in items:
            self.session.execute(
                "INSERT INTO budget_items (id, chapter_id, code, description, unit, quantity, "
                "performance, source, formula_code, direct_cost) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item["id"], item["chapter_id"], item.get("code", ""), item.get("description", ""),
                 item.get("unit", ""), item.get("quantity", 0), item.get("performance", 0),
                 item.get("source", ""), item.get("formula_code", ""), item.get("direct_cost", 0)),
            )
        for rel in item_resources:
            self.session.execute(
                "INSERT INTO budget_item_resources (id, item_id, resource_id, factor, waste_pct, kind) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), rel["item_id"], rel["resource_id"],
                 rel.get("factor", 0), rel.get("waste_pct", 0), rel.get("kind", "MATERIAL")),
            )

    def budget_tree(self, budget_id: str) -> Dict[str, Any]:
        """Chapters + items (without prices; pricing is computed by BudgetService)."""
        chapters = [dict(r) for r in self.session.query_all(
            "SELECT * FROM budget_chapters WHERE budget_id = ? ORDER BY position, code", (budget_id,))]
        items = [dict(r) for r in self.session.query_all(
            "SELECT bi.* FROM budget_items bi JOIN budget_chapters bc ON bc.id = bi.chapter_id "
            "WHERE bc.budget_id = ? ORDER BY bc.position, bi.code", (budget_id,))]
        return {"chapters": chapters, "items": items}

    def budget_items_full(self, budget_id: str) -> List[Dict[str, Any]]:
        """Items with their resource breakdown for reports and recompute."""
        chapters = {c["id"]: c for c in (
            dict(r) for r in self.session.query_all(
                "SELECT * FROM budget_chapters WHERE budget_id = ?", (budget_id,)))}
        items: List[Dict[str, Any]] = []
        rows = self.session.query_all(
            "SELECT bi.* FROM budget_items bi JOIN budget_chapters bc ON bc.id = bi.chapter_id "
            "WHERE bc.budget_id = ? ORDER BY bc.position, bi.code", (budget_id,))
        for row in rows:
            item = dict(row)
            item["chapter"] = chapters.get(item["chapter_id"], {})
            item["resources"] = [
                dict(r) for r in self.session.query_all(
                    "SELECT * FROM budget_item_resources WHERE item_id = ?", (item["id"],))
            ]
            items.append(item)
        return items

    @staticmethod
    def _resource_dict(r: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": r["id"], "project_id": r["project_id"], "code": r["code"],
            "name": r["name"], "type": r["type"], "unit": r["unit"],
            "category": r["category"], "metadata": json_loads(r["metadata_json"], {}) or {},
        }


__all__ = ["QuantityRepository", "BudgetRepository"]
