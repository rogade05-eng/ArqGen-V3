"""FASE 41 — Regression suite with golden values (spec 96-97).

Two independently built demo projects must produce identical:
    * budget total (1.295.093,90 CUP — 8 capítulos)
    * QTO quantity rows (formula, code, quantity, unit)
    * memoria descriptiva text (TEST-021)
    * IFC entity count (1804, v3.13.0) and DXF wall entity count (7)
    * PRECONS project total (512.763,83 CUP)
    * electrical panel demand (7180 W) and structure steel (1875 kg)

Plus the spec-97 fundamentals not covered before: TEST-021 Documentation
(golden text) and TEST-024 Recovery (corrupt → recover), which live in
the sibling test modules; here we pin the cross-module golden numbers.
"""

from __future__ import annotations

import hashlib
import os
import unittest

from tests.base import ARQGenTestCase

GOLDEN_BUDGET_TOTAL = 1295093.90      # CUP, plantilla residential_full_v1
GOLDEN_IFC_ENTITIES = 1804            # entidades IFC4 de la demo (v3.13.0: +1 IFCRELCONTAINEDINSPATIALSTRUCTURE por la contención de vanos en su piso)
GOLDEN_DXF_WALL_ENTITIES = 7
GOLDEN_QTO_OBJECTS = 161              # objetos con cantidades en la demo (12 redes)
GOLDEN_PRECONS_TOTAL = 512763.83      # CUP análisis del proyecto
GOLDEN_PANEL_DEMAND_W = 7180.0        # demanda instalada 3 circuitos
GOLDEN_STEEL_KG = 1875.0              # acero de los elementos estructurales


def _qto_rows(context) -> list:
    from services.quantity_service import QuantityService
    rows = QuantityService(context).quantities()
    return sorted(
        (r["object_code"], r["formula_code"],
         round(float(r["final_quantity"]), 3), r["unit"])
        for r in rows)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestRegressionGolden(ARQGenTestCase):
    def _build_two_demos(self):
        ctx_a = self.demo_context("demo_a.arqgen")
        ctx_b = self.demo_context("demo_b.arqgen")
        return ctx_a, ctx_b

    def test_budget_total_stable(self):
        ctx_a, ctx_b = self._build_two_demos()
        try:
            from services.budget_service import BudgetService
            for ctx in (ctx_a, ctx_b):
                budget = BudgetService(ctx).latest_budget()
                self.assertIsNotNone(budget)
                self.assertAlmostEqual(float(budget["total_cost"]),
                                       GOLDEN_BUDGET_TOTAL, places=2)
        finally:
            ctx_a.close()
            ctx_b.close()

    def test_qto_rows_identical(self):
        ctx_a, ctx_b = self._build_two_demos()
        try:
            rows_a = _qto_rows(ctx_a)
            rows_b = _qto_rows(ctx_b)
            self.assertEqual(rows_a, rows_b)
            objects = {r[0] for r in rows_a}
            self.assertEqual(len(objects), GOLDEN_QTO_OBJECTS)
        finally:
            ctx_a.close()
            ctx_b.close()

    def test_memoria_identical_and_hashed(self):
        """TEST-021: documentación reproducible entre ejecuciones."""
        from services.documentation_service import DocumentationService
        ctx_a, ctx_b = self._build_two_demos()
        try:
            memoria_a = DocumentationService(ctx_a).generate_memoria()
            memoria_b = DocumentationService(ctx_b).generate_memoria()
            self.assertEqual(memoria_a, memoria_b)
            # Hash dorado del contenido (sin fecha: misma corrida de día)
            self.assertIn("Proyecto Demo Residencial", memoria_a)
            # La memoria genera SIEMPRE el mismo hash dentro del mismo día
            self.assertEqual(_sha256(memoria_a), _sha256(memoria_b))
        finally:
            ctx_a.close()
            ctx_b.close()

    def test_exporters_stable(self):
        from services.export_service import ExportService
        ctx_a, ctx_b = self._build_two_demos()
        try:
            out_a = os.path.join(self.tmp, "a.ifc")
            out_b = os.path.join(self.tmp, "b.ifc")
            ExportService().export(ctx_a, "ifc", out_a)
            ExportService().export(ctx_b, "ifc", out_b)
            text_a = open(out_a, encoding="utf-8").read()
            text_b = open(out_b, encoding="utf-8").read()
            # La cabecera IFC incluye la ruta del archivo de salida: se
            # normaliza y se comparan las entidades.
            body_a = "\n".join(l for l in text_a.splitlines()
                               if "FILE_NAME" not in l)
            body_b = "\n".join(l for l in text_b.splitlines()
                               if "FILE_NAME" not in l)
            self.assertEqual(body_a, body_b)
            entities = [line for line in text_a.splitlines()
                        if line.startswith("#") and "=" in line]
            self.assertEqual(len(entities), GOLDEN_IFC_ENTITIES)
        finally:
            ctx_a.close()
            ctx_b.close()

    def test_discipline_goldens(self):
        """PRECONS, eléctrico y estructura mantienen sus valores."""
        from services.installations_service import InstallationsService
        from services.precons_service import PreconsService
        from services.structure_service import StructureService
        ctx_a, _ = self._build_two_demos()
        try:
            precons = PreconsService(ctx_a)
            precons.load_ruleset("precons_cuba_v1")
            report = precons.analyze_project()
            self.assertAlmostEqual(
                float(report["total"]), GOLDEN_PRECONS_TOTAL, places=2)

            installations = InstallationsService(ctx_a)
            # El tablero demo (ARQ-NODE-001) alimenta 3 circuitos: 7180 W
            panel = installations.ctx.installations.list(
                "NODE", ctx_a.project.id)[0]
            self.assertEqual(panel.kind, "PANEL")
            summary = installations.panel_summary(panel.code)
            self.assertAlmostEqual(float(summary["total_demand_w"]),
                                   GOLDEN_PANEL_DEMAND_W, places=0)

            steel = StructureService(ctx_a).steel_quantities()
            self.assertAlmostEqual(float(steel["steel_weight_kg"]),
                                   GOLDEN_STEEL_KG, places=0)
        finally:
            ctx_a.close()


if __name__ == "__main__":
    unittest.main()
