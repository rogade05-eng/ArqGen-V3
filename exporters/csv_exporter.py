"""CSV exporter (stdlib csv): quantities or budget tables (spec 95)."""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional

from core.errors import ExportError
from exporters.pricing_math import item_unit_cost


class CSVExporter:
    def export(self, context, out_path: str, table: str = "quantities") -> str:
        if table == "quantities":
            headers, rows = self._quantities(context)
        elif table == "budget":
            headers, rows = self._budget(context)
        else:
            raise ExportError(
                message=f"Tabla CSV desconocida: {table} (use quantities|budget)",
                code="ARQ-EXP-050")
        directory = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(directory, exist_ok=True)
        try:
            with open(out_path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as exc:
            raise ExportError(
                message=f"No se pudo escribir el CSV: {exc}",
                code="ARQ-EXP-051", context={"path": out_path}) from exc
        context.emit("EXPORT_COMPLETED", {"format": "CSV", "path": out_path, "table": table})
        return out_path

    @staticmethod
    def _quantities(context):
        rows = []
        for q in context.quantities_repo.all(context.project.id):
            rows.append([
                q["object_code"], q["object_type"], q["formula_code"],
                q["formula_expression"], round(q["raw_quantity"], 4),
                round(q["waste_factor"], 4), round(q["final_quantity"], 4),
                q["unit"], q["computed_at"],
            ])
        return (["objeto", "tipo", "formula", "expresion", "bruta",
                 "desperdicio", "final", "unidad", "calculado"], rows)

    def _budget(self, context):
        budget = context.budget_repo.latest_budget(context.project.id)
        if budget is None:
            raise ExportError(
                message="No hay presupuesto calculado para exportar",
                code="ARQ-EXP-052",
                suggested_action="Ejecute 'budget compute' antes de exportar.")
        items = context.budget_repo.budget_items_full(budget["id"])
        plist = context.budget_repo.get_price_list_by_code(
            context.project.id, budget.get("price_list_code", ""))
        price_date = (budget.get("updated_at") or "")[:10]
        rows: List[List[Any]] = []
        total_direct = 0.0
        xlsx_helper = None
        for item in items:
            unit_cost = item_unit_cost(context, item, plist, price_date)
            direct = round(unit_cost * item["quantity"], 2)
            total_direct += direct
            rows.append([item["chapter"].get("code", ""), item["code"],
                         item["description"], item["unit"],
                         round(item["quantity"], 4), round(unit_cost, 2), direct])
        rows.append(["", "", "COSTO DIRECTO", "", "", "", round(budget["direct_cost"], 2)])
        rows.append(["", "", "INDIRECTOS", "", "", "", round(budget["indirect_cost"], 2)])
        rows.append(["", "", "OTROS", "", "", "", round(budget["other_cost"], 2)])
        rows.append(["", "", "TOTAL", "", "", "", round(budget["total_cost"], 2)])
        return (["capitulo", "partida", "descripcion", "unidad", "cantidad",
                 "precio_unitario", "costo"], rows)


__all__ = ["CSVExporter"]
