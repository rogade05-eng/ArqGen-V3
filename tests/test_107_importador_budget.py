"""Integraciones v2.0.0: asistente §94 headless, comando budget e
instalación de catálogos desde archivo.

El flujo del asistente GUI (ui.app_window.open_importar_catalogo) es
una cáscara fina sobre CatalogImporter + escritura del ruleset: aquí
se prueba ese flujo sin Tk, más el comando CLI `precons budget`.
"""

from __future__ import annotations

import json
import os
import unittest

from tests.base import ARQGenTestCase

REAL_CODE = "precons_iii_rospres_330"


def _write_small_catalog(path: str) -> None:
    """XLSX con las hojas SECCIONES + RENGLONES_PRECONS (forma §94)."""
    import openpyxl

    workbook = openpyxl.Workbook()
    sections = workbook.active
    sections.title = "SECCIONES"
    sections.append(("Código", "Nombre", "Renglones"))
    sections.append(("01", "Seccion 01 - Prueba", 2))
    renglones = workbook.create_sheet("RENGLONES_PRECONS")
    renglones.append(("Sección código", "Sección", "Capítulo código",
                      "Capítulo", "Subcapítulo código", "Subcapítulo",
                      "Código PRECONS", "Unidad", "Materiales CUP",
                      "Mano de obra CUP", "Equipos CUP", "Total CUP",
                      "Descripción"))
    for row in (
            ("01", "Seccion 01 - Prueba", "011", "PRELIMINARES", "0111",
             "CHAPEA", "011111", "m2", 26.81, 0, 0, 26.81,
             "MANIGUA MANUAL"),
            ("01", "Seccion 01 - Prueba", "011", "PRELIMINARES", "0111",
             "CHAPEA", "011112", "m2", 0.66, 13.76, 0, 14.42,
             "MANIGUA LIGERA MECANIZADA")):
        renglones.append(row)
    workbook.save(path)


class TestImportarFlow(ARQGenTestCase):
    """Flujo analizar → aplicar → ruleset instalado (asistente §94)."""

    def test_preview_and_apply_small_catalog(self):
        from importers.catalog import CatalogImporter
        # XLSX con hojas SECCIONES + RENGLONES_PRECONS: la forma §94.
        xlsx_path = os.path.join(self.tmp, "catalogo_prueba.xlsx")
        _write_small_catalog(xlsx_path)
        report_payload, report, prices = \
            CatalogImporter().convert(xlsx_path)
        self.assertEqual(report["counts"]["work_items"], 2)
        self.assertEqual(report["errors"], [])

        out_path = os.path.join(self.tmp, "ruleset_test.json")
        CatalogImporter().apply(xlsx_path, code="catalogo_test",
                                name="Catálogo de prueba",
                                out_path=out_path)
        self.assertTrue(os.path.exists(out_path))
        data = json.load(open(out_path, encoding="utf-8"))
        self.assertEqual(data["code"], "catalogo_test")
        self.assertEqual(len(data["work_items"]), 2)
        # el ruleset instalado se carga como cualquier otro
        from engines.precons_engine import PreconsRuleset
        ruleset = PreconsRuleset.from_file(out_path)
        self.assertEqual(ruleset.item("011111")["name"], "MANIGUA MANUAL")

    def test_import_dialog_headless_helpers(self):
        """El diálogo del asistente existe y su lógica no depende de Tk."""
        from ui import app_window
        self.assertTrue(hasattr(app_window.ARQGenWindow,
                                "open_importar_catalogo"))
        self.assertTrue(hasattr(app_window.ARQGenWindow,
                                "open_presupuesto_precons"))
        self.assertTrue(hasattr(app_window.ARQGenWindow,
                                "add_to_presupuesto"))


class TestPreconsBudgetCommand(ARQGenTestCase):
    """Comando `precons budget` de la CLI, punta a punta."""

    def test_budget_command_end_to_end(self):
        path = self.project_path("cli.arqgen")
        self.application.create_project(path, "Proyecto CLI")
        from app.cli import HANDLERS, _build_parser
        parser = _build_parser()
        argv = parser.parse_args([
            "precons", "budget", path, "--add", "011111:500",
            "--add", "020112:2", "--show",
            "--export-csv", os.path.join(self.tmp, "b.csv"),
            "--export-pdf", os.path.join(self.tmp, "b.pdf"),
            "--chart-png", os.path.join(self.tmp, "b.png"),
        ])
        handler = HANDLERS[("precons", "budget")]
        application = self.application
        exit_code = handler(application, argv)
        self.assertEqual(exit_code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "b.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "b.pdf")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "b.png")))
        # persistencia: reabrir y comprobar el total
        from services.precons_budget_service import PreconsBudgetService
        service = PreconsBudgetService(
            self.application.open_project(path))
        service.load_ruleset(REAL_CODE)
        self.assertEqual(len(service.lines()), 2)
        self.assertAlmostEqual(service.totals()["total"], 72849.04, places=2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
