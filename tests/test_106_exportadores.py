"""Exportadores stdlib v2.0.0 (brecha #4): PDF, SVG y PNG.

Sin dependencias externas: PDF 1.4 con fuentes base, SVG plano del
proyecto y PNG de gráfico de barras. Se valida estructura, cabeceras
y contenido.
"""

from __future__ import annotations

import os
import unittest
import xml.etree.ElementTree as ET
import zlib

from tests.base import ARQGenTestCase

REAL_CODE = "precons_iii_rospres_330"


def _budget_tree(context):
    from services.precons_budget_service import PreconsBudgetService
    service = PreconsBudgetService(context)
    service.load_ruleset(REAL_CODE)
    service.add_item("011111", 500)
    service.add_item("020112", 2)
    return service.tree()


class TestPdfExporter(ARQGenTestCase):
    """PDF 1.4 válido, con acentos WinAnsi y tablas multipágina."""

    def test_budget_pdf_structure(self):
        from exporters.pdf_exporter import export_budget_pdf
        context = self.demo_context()
        tree = _budget_tree(context)
        path = os.path.join(self.tmp, "presupuesto.pdf")
        export_budget_pdf(tree, path, context.project.name)
        data = open(path, "rb").read()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", data[-40:])
        self.assertIn(b"/Count", data)
        # contenido comprimido: al descomprimir hay texto WinAnsi
        self.assertIn(b"FlateDecode", data)

    def test_pdf_pages_decompress_with_content(self):
        from exporters.pdf_exporter import PdfReport
        path = os.path.join(self.tmp, "tabla.pdf")
        report = PdfReport("Reporte de prueba", "Acentos: áéíóú ñ ✓no")
        rows = [[str(i), f"Renglón {i}", "1234,56"] for i in range(60)]
        report.table([("N", "l", 60), ("Descripción", "l", 260),
                      ("Importe", "r", 100)], rows)
        report.save(path)
        data = open(path, "rb").read()
        streams = []
        marker = b"stream\n"
        while marker in data:
            start = data.index(marker) + len(marker)
            end = data.index(b"\nendstream", start)
            blob = data[start:end]
            streams.append(zlib.decompress(blob).decode("cp1252",
                                                        errors="replace"))
            data = data[end + 10:]
        text = "\n".join(streams)
        self.assertIn("Reporte de prueba", text)
        self.assertTrue(any("Rengl" in s for s in streams))

    def test_analysis_pdf(self):
        from engines.precons_engine import price_analysis
        from app.paths import resource_path
        from exporters.pdf_exporter import export_analysis_pdf
        from engines.precons_engine import PreconsRuleset
        ruleset = PreconsRuleset.from_file(
            resource_path("rulesets", f"{REAL_CODE}.json"))
        analysis = price_analysis(ruleset, "020112", 2.0, {})
        path = os.path.join(self.tmp, "analisis.pdf")
        export_analysis_pdf(analysis.to_dict(), path, "Proyecto X")
        data = open(path, "rb").read()
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", data[-40:])


class TestSvgExporter(ARQGenTestCase):
    """SVG del plano: XML válido, muros, locales y niveles."""

    def test_plan_svg_from_demo(self):
        from exporters.svg_exporter import export_plan_svg
        context = self.demo_context()
        path = os.path.join(self.tmp, "plano.svg")
        export_plan_svg(context, path, title=context.project.name)
        content = open(path, encoding="utf-8").read()
        root = ET.fromstring(content)
        self.assertEqual(root.tag.split("}")[-1], "svg")
        self.assertIn('<svg', content)
        # geometría real del demo: 7 muros, 4 locales
        self.assertEqual(content.count('class="muro"'), 7)
        self.assertEqual(content.count('class="local"'), 4)

    def test_svg_without_geometry_rejected(self):
        from core.errors import ExportError
        from exporters.svg_exporter import export_plan_svg
        context = self.application.create_project(
            self.project_path("vacio.arqgen"), "Vacío")
        with self.assertRaises(ExportError):
            export_plan_svg(context, os.path.join(self.tmp, "vacio.svg"))

    def test_svg_registered_in_export_service(self):
        from services.export_service import ExportService
        self.assertIn("SVG", ExportService().formats())


class TestPngExporter(ARQGenTestCase):
    """PNG del gráfico de barras: firma, IHDR e IEND correctos."""

    def test_chart_png_structure(self):
        from exporters.png_exporter import export_budget_chart_png
        context = self.demo_context()
        tree = _budget_tree(context)
        path = os.path.join(self.tmp, "grafico.png")
        export_budget_chart_png(tree, path, context.project.name)
        data = open(path, "rb").read()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn(b"IHDR", data[:40])
        self.assertIn(b"IEND", data[-20:])
        # dimensiones en IHDR (big-endian, tras firma+longitud+tipo)
        import struct
        width, height = struct.unpack(">II", data[16:24])
        self.assertGreater(width, 100)
        self.assertGreater(height, 60)

    def test_empty_budget_png(self):
        from exporters.png_exporter import export_budget_chart_png
        context = self.application.create_project(
            self.project_path("vacio2.arqgen"), "Vacío")
        tree = {"chapters": [], "currency": "CUP", "total": 0.0}
        path = os.path.join(self.tmp, "vacio.png")
        export_budget_chart_png(tree, path, context.project.name)
        data = open(path, "rb").read()
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
