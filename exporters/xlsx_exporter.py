"""XLSX exporter: quantities, budget, resources (spec 68, 95).

FASE B (v3.49.0): con el acelerador Rust activo (ARQ_GEN_ACELERADOR=rust
o usar_rust=True, y el crate arqgen_core instalado) el libro lo escribe
el núcleo Rust (`arqgen_core.xlsx_escribir`) con el MISMO formato
profesional (cabecera azul 2F5496 con fuente blanca en negrita y
centrada, pane congelado en A2, anchos de columna). Ante cualquier
fallo de escritura Rust, la ruta openpyxl queda como fallback
transparente. El formato de los datos es agnóstico: se recogen las
hojas primero y el escritor se elige después.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.errors import ExportError
from exporters.pricing_math import item_unit_cost


class XLSXExporter:
    """Professional workbook: formatted headers, freeze panes, number formats."""

    HEADER_FILL = "FF2F5496"
    HEADER_FONT = "FFFFFF"

    def export(self, context, out_path: str, include_budget: bool = True,
               usar_rust: Optional[bool] = None) -> str:
        hojas = self._hojas(context, include_budget)
        if usar_rust is None:
            usar_rust = os.environ.get("ARQ_GEN_ACELERADOR", "").strip().lower() == "rust"
        if usar_rust:
            from core import acelerador
            if acelerador.disponible():
                try:
                    import arqgen_core
                    arqgen_core.xlsx_escribir(out_path, hojas)
                    context.emit("EXPORT_COMPLETED", {"format": "XLSX", "path": out_path})
                    return out_path
                except Exception:
                    pass  # fallback transparente: mismo contenido vía openpyxl
        return self._exportar_openpyxl(context, out_path, hojas)

    # ------------------------------------------------------------------
    # datos de las hojas (formato-agnóstico)
    # ------------------------------------------------------------------

    def _hojas(self, context, include_budget: bool) -> List[Dict[str, Any]]:
        hojas: List[Dict[str, Any]] = []

        # Hoja 1: Cantidades
        quantities = context.quantities_repo.all(context.project.id)
        qty_rows = [
            [
                q["object_code"], q["object_type"], q["formula_code"],
                q["formula_expression"], round(q["raw_quantity"], 4),
                f"{q['waste_factor'] * 100:.1f}%", round(q["final_quantity"], 4),
                q["unit"], q["input_hash"][:12], q["computed_at"],
            ]
            for q in quantities
        ]
        hojas.append({
            "titulo": "Cantidades",
            "headers": ["Objeto", "Tipo", "Fórmula", "Expresión", "Bruta",
                        "Desperdicio", "Final", "Unidad", "Hash", "Calculado"],
            "filas": qty_rows,
            "anchos": [16, 10, 20, 34, 10, 12, 10, 8, 14, 20],
        })

        # Hoja 2: Presupuesto (si lo hay)
        if include_budget:
            budget = context.budget_repo.latest_budget(context.project.id)
            if budget:
                items = context.budget_repo.budget_items_full(budget["id"])
                price_date = budget.get("updated_at", "")[:10]
                plist = context.budget_repo.get_price_list_by_code(
                    context.project.id, budget.get("price_list_code", ""))
                rows = []
                for item in items:
                    unit_cost = item_unit_cost(context, item, plist, price_date)
                    direct = round(unit_cost * item["quantity"], 2)
                    rows.append([
                        item["chapter"].get("code", ""), item["code"],
                        item["description"], item["unit"],
                        round(item["quantity"], 4), item["performance"] or "",
                        round(unit_cost, 2), direct,
                    ])
                indirect = round(budget["direct_cost"] * budget["indirect_pct"] / 100.0, 2)
                other = round(budget["direct_cost"] * budget["other_pct"] / 100.0, 2)
                rows.append(["", "", "COSTO DIRECTO", "", "", "", "", round(budget["direct_cost"], 2)])
                rows.append(["", "", f"INDIRECTOS ({budget['indirect_pct']}%)", "", "", "", "", indirect])
                rows.append(["", "", f"OTROS ({budget['other_pct']}%)", "", "", "", "", other])
                rows.append(["", "", "TOTAL", "", "", "", "", round(budget["total_cost"], 2)])
                hojas.append({
                    "titulo": "Presupuesto",
                    "headers": ["Capítulo", "Partida", "Descripción", "Unidad", "Cantidad",
                                "Rendimiento", "Precio unit.", "Costo"],
                    "filas": rows,
                    "anchos": [10, 10, 42, 8, 12, 12, 12, 14],
                })

        # Hoja 3: Recursos y precios
        resources = context.budget_repo.list_resources(context.project.id)
        res_rows = []
        for resource in resources:
            res_rows.append([
                resource["code"], resource["name"], resource["type"], resource["unit"],
                resource["category"],
            ])
        hojas.append({
            "titulo": "Recursos",
            "headers": ["Código", "Nombre", "Tipo", "Unidad", "Categoría"],
            "filas": res_rows,
            "anchos": [14, 34, 12, 8, 16],
        })
        return hojas

    # ------------------------------------------------------------------
    # escritor openpyxl (camino clásico y fallback)
    # ------------------------------------------------------------------

    def _exportar_openpyxl(self, context, out_path: str,
                           hojas: List[Dict[str, Any]]) -> str:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as exc:  # pragma: no cover
            raise ExportError(
                message="openpyxl no está instalado; ejecute el bat de instalación de dependencias",
                code="ARQ-EXP-040") from exc

        wb = Workbook()
        header_fill = PatternFill("solid", fgColor=self.HEADER_FILL)
        header_font = Font(color=self.HEADER_FONT, bold=True)

        for hoja in hojas:
            ws = wb.create_sheet(hoja["titulo"][:31])
            ws.append(hoja["headers"])
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")
            for row in hoja["filas"]:
                ws.append(row)
            for index, width in enumerate(hoja["anchos"], start=1):
                ws.column_dimensions[get_column_letter(index)].width = width
            ws.freeze_panes = "A2"

        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]
        directory = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(directory, exist_ok=True)
        try:
            wb.save(out_path)
        except Exception as exc:
            raise ExportError(
                message=f"No se pudo escribir el XLSX: {exc}",
                code="ARQ-EXP-041", context={"path": out_path}) from exc
        context.emit("EXPORT_COMPLETED", {"format": "XLSX", "path": out_path})
        return out_path


__all__ = ["XLSXExporter"]
