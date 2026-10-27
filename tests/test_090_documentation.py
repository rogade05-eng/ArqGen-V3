"""FASE 34 — Documentation module tests (spec 68, 69, 70, 106; TEST-021).

All expected values are verified by hand:
    * 1:50 scale → denominator 50; drawing 10 mm = 500 real mm
    * A3 landscape paper = 420 x 297 mm
    * openings_table: 0.9 x 2.1 m = 1.89 m2
    * area_table totals: 10 + 20 = 30 m2; 2+4 persons → 5.0 m2/person
    * demo variables: 4 doors, 3 windows, budget 1.295.093,90 CUP
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase
from tests.base import PROJECT_ROOT  # noqa: F401

from core.errors import DomainError, DataError
from domain.documentation import Drawing, DocTemplate, parse_scale
from engines.documentation_engine import (
    area_table, build_titleblock, collect_placeholders, dimension_text,
    elements_table, format_table, module_doc, openings_table,
    render_html_document, render_markdown_document, render_template,
)


class TestEngine(unittest.TestCase):
    def test_parse_scale(self):
        self.assertEqual(parse_scale("1:50"), 50)
        self.assertEqual(parse_scale(" 1:100 "), 100)
        with self.assertRaises(DomainError) as ctx:
            parse_scale("50")
        self.assertEqual(ctx.exception.code, "ARQ-DOC-001")
        with self.assertRaises(DomainError):
            parse_scale("1:37")  # fuera del catálogo normalizado

    def test_drawing_geometry_and_elements(self):
        drawing = Drawing(sheet="A-01", sheet_size="A3", scale="1:50",
                          orientation="LANDSCAPE", view="PLAN")
        self.assertEqual(drawing.paper_size(), (420.0, 297.0))
        self.assertEqual(drawing.real_length_mm(10.0), 500.0)
        self.assertEqual(drawing.drawing_length_mm(1000.0), 20.0)
        record = drawing.add_element("DIMENSION", {"value_mm": 100.0})
        self.assertEqual(record["kind"], "DIMENSION")
        with self.assertRaises(DomainError) as ctx:
            drawing.add_element("ROTULO", {})
        self.assertEqual(ctx.exception.code, "ARQ-DOC-005")
        with self.assertRaises(DomainError) as ctx:
            Drawing(sheet_size="A9")
        self.assertEqual(ctx.exception.code, "ARQ-DOC-002")

    def test_dimension_text(self):
        self.assertEqual(dimension_text(5000.0, 50), "5.00 m")
        self.assertEqual(dimension_text(900.0, 50, decimals=3), "0.900 m")

    def test_render_template_strict(self):
        text = "Proyecto {{PROJECT.NAME}} — {{PROJECT.AREA}}"
        out = render_template(text, {"PROJECT.NAME": "Demo",
                                     "PROJECT.AREA": 1234.5})
        self.assertEqual(out, "Proyecto Demo — 1234.5")
        self.assertEqual(collect_placeholders(text),
                         ["PROJECT.AREA", "PROJECT.NAME"])
        with self.assertRaises(DataError) as ctx:
            render_template("{{NO_EXISTE}}", {})
        self.assertEqual(ctx.exception.code, "ARQ-DAT-DOC-010")

    def test_titleblock(self):
        block = build_titleblock(
            {"name": "P", "client": "C", "address": "X"},
            {"sheet": "A-01", "scale": "1:50", "view": "PLAN",
             "orientation": "LANDSCAPE", "sheet_size": "A3"},
            app_version="1.3.0")
        self.assertEqual(block["PROJECT"], "P")
        self.assertEqual(block["SCALE"], "1:50")
        self.assertEqual(block["APP_VERSION"], "1.3.0")

    def test_tables(self):
        rows = area_table([
            {"name": "Sala", "area": 10.0, "perimeter": 14.0, "occupancy": 2.0},
            {"name": "Cocina", "area": 20.0, "perimeter": 18.0, "occupancy": 4.0},
        ])
        self.assertEqual(rows[-1]["name"], "TOTAL")
        self.assertAlmostEqual(rows[-1]["area"], 30.0)
        self.assertAlmostEqual(rows[-1]["area_per_person"], 5.0)
        vanos = openings_table([
            {"code": "D1", "kind": "DOOR", "host": "W1",
             "width": 0.9, "height": 2.1}])
        self.assertAlmostEqual(vanos[0]["area"], 1.89)
        listing = elements_table([{"code": "A", "name": "x", "extra": 1}],
                                 ["code", "name"])
        self.assertEqual(listing, [{"code": "A", "name": "x"}])
        self.assertIn("| code |", format_table(listing))
        self.assertEqual(format_table([], ["a"]), "(sin datos)")

    def test_module_doc_and_renderers(self):
        text = module_doc("core", {
            "purpose": "Núcleo del sistema", "api": ["EventBus.emit"],
            "data_model": ["Entity"], "rules": [], "formulas": [],
            "tests": ["test_010"], "changelog": ["1.0.0"],
        })
        for section in ("## README", "## API", "## DATA MODEL", "## RULES",
                        "## FORMULAS", "## TESTS", "## CHANGELOG"):
            self.assertIn(section, text)
        doc = render_markdown_document(
            "Título", [("Sección", "Cuerpo")], header="Encabezado",
            footer="Pie")
        self.assertTrue(doc.startswith("Encabezado"))
        self.assertIn("# Título", doc)
        self.assertTrue(doc.rstrip().endswith("Pie"))
        html = render_html_document("T", "# Título\n| a | b |\n| - | - |\n| 1 | <2 |")
        self.assertIn("<h1>Título</h1>", html)
        self.assertIn("<table>", html)
        self.assertIn("&lt;2", html)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))


class TestDocumentationService(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_variables_map(self):
        from services.documentation_service import DocumentationService
        variables = DocumentationService(self.ctx).variables()
        self.assertEqual(variables["PROJECT.NAME"], "Proyecto Demo Residencial")
        self.assertEqual(variables["QTO.DOOR_COUNT"], 4)
        self.assertEqual(variables["QTO.WINDOW_COUNT"], 3)
        self.assertEqual(variables["QTO.OPENING_COUNT"], 7)
        self.assertAlmostEqual(variables["BUDGET.TOTAL"], 1295093.90, places=2)
        self.assertGreater(variables["QTO.TOTAL_WALL_AREA"], 0.0)

    def test_create_drawing_with_titleblock_and_element(self):
        from services.documentation_service import DocumentationService
        service = DocumentationService(self.ctx)
        drawing = service.create_drawing("A-01", sheet_size="A3",
                                         scale="1:50", view="PLAN")
        self.ctx.commit()
        self.assertTrue(drawing.code.startswith("DOC-"))
        # Titleblock automático con datos del proyecto
        self.assertEqual(drawing.titleblock["PROJECT"],
                         "Proyecto Demo Residencial")
        record = service.add_drawing_element(drawing.code, "TEXT",
                                             {"text": "Sala"})
        self.assertEqual(record["text"], "Sala")
        # Persistencia
        again = service.ctx.documentation.drawings.get_by_code(drawing.code)
        self.assertEqual(len(again.annotations), 1)
        rows = service.list_drawings()
        self.assertEqual(rows[0]["elements"], 1)
        # Escala: conversión por plano
        self.assertEqual(service.dimension_for(drawing.code, 5000.0), "5.00 m")
        service.delete_drawing(drawing.code)
        self.ctx.commit()
        self.assertEqual(service.list_drawings(), [])

    def test_templates_render(self):
        from services.documentation_service import DocumentationService
        service = DocumentationService(self.ctx)
        template = service.create_template(
            "carta", "Estimado {{CLIENT.NAME}}, proyecto {{PROJECT.NAME}}.")
        self.ctx.commit()
        with self.assertRaises(DomainError):
            service.create_template("carta", "duplicado")  # nombre único
        rendered = service.render_template(template.code)
        self.assertIn("Cliente Demo", rendered)
        self.assertIn("Proyecto Demo Residencial", rendered)
        self.assertEqual(service.list_templates()[0]["placeholders"], 2)

    def test_generate_memoria_and_cuadros(self):
        from services.documentation_service import DocumentationService
        service = DocumentationService(self.ctx)
        memoria = service.generate_memoria()
        self.assertIn("Memoria descriptiva — Proyecto Demo Residencial", memoria)
        self.assertIn("Cliente Demo", memoria)
        # TEST-021 (determinismo): dos generaciones idénticas
        self.assertEqual(memoria, service.generate_memoria())
        cuadros = service.generate_cuadros()
        self.assertIn("Cuadro de superficies", cuadros)
        self.assertIn("TOTAL", cuadros)
        self.assertIn("Cuadro de vanos", cuadros)
        for generated in (service.generate_tecnica(),
                          service.generate_especificaciones(),
                          service.generate_listados(),
                          service.generate_informe()):
            self.assertIn("Proyecto Demo Residencial", generated)
        # El informe refleja el estado de interferencias (demo: 238 abiertas)
        self.assertIn("Total: 238", service.generate_informe())

    def test_module_docs_and_errors(self):
        from services.documentation_service import DocumentationService
        service = DocumentationService(self.ctx)
        text = service.module_docs("documentation")
        self.assertIn("# documentation", text)
        self.assertIn("## FORMULAS", text)
        with self.assertRaises(DomainError) as ctx:
            service.module_docs("no_existe")
        self.assertEqual(ctx.exception.code, "ARQ-DOC-008")
        with self.assertRaises(DomainError):
            service._resolve_drawing("ARQ-NOPE-999")

    def test_export_document(self):
        from services.documentation_service import DocumentationService
        service = DocumentationService(self.ctx)
        memoria = service.generate_memoria()
        out_md = os.path.join(self.tmp, "memoria.md")
        out_html = os.path.join(self.tmp, "memoria.html")
        service.export_document(memoria, out_md, "md")
        service.export_document(memoria, out_html, "html")
        self.assertTrue(os.path.getsize(out_md) > 0)
        html = open(out_html, encoding="utf-8").read()
        self.assertIn("<!DOCTYPE html>", html)
        with self.assertRaises(Exception):
            service.export_document(memoria, out_md, "docx")
        # v3.8.0: el PDF es un formato de primera clase (export_markdown_pdf)
        out_pdf = os.path.join(self.tmp, "memoria.pdf")
        service.export_document(memoria, out_pdf, "pdf")
        self.assertTrue(open(out_pdf, "rb").read(5) == b"%PDF-")
        self.assertTrue(os.path.getsize(out_pdf) > 0)


if __name__ == "__main__":
    unittest.main()
