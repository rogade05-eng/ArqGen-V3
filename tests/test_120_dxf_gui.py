"""Importador DXF en GUI (v3.3.0, brecha #2) y primitivas nuevas de Canvas.

El motor DXF (importers.dxf_reader.DxfImporter) ya está cubierto a
fondo en test_099 (preview, apply, auditoría, capas explícitas, CLI).
Aquí se prueba la capa que lo expone al usuario:

- ui.app_window.open_importar_dxf: diálogo con ganchos _dxf_*, flujo
  analizar → importar en modo síncrono (_dxf_sync) contra un proyecto
  real, con muros y espacios verificables en el explorador.
- Entrada de menú Herramientas y tooltips dxf_* de ui.help.
- exporters.png_exporter.Canvas: line (Bresenham con grosor),
  polyline, arc y polygon_fill — la base del rasterizador de vistas.
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


DISPLAY = _display_available()


def _write_dxf(path: str) -> None:
    """DXF mínimo: 4 muros y 2 locales con su rótulo TEXT."""
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "ARQ-MUROS"})
    msp.add_line((12, 0), (12, 8), dxfattribs={"layer": "ARQ-MUROS"})
    msp.add_line((12, 8), (0, 8), dxfattribs={"layer": "ARQ-MUROS"})
    msp.add_line((0, 8), (0, 0), dxfattribs={"layer": "ARQ-MUROS"})
    msp.add_line((12, 0), (12, 8), dxfattribs={"layer": "OTRA-CAPA"})
    msp.add_lwpolyline([(0.2, 0.2), (6, 0.2), (6, 7.8), (0.2, 7.8)],
                       close=True, dxfattribs={"layer": "ARQ-LOCAL"})
    msp.add_lwpolyline([(6.2, 0.2), (11.8, 0.2), (11.8, 7.8), (6.2, 7.8)],
                       close=True, dxfattribs={"layer": "ARQ-LOCAL"})
    msp.add_text("SALA", height=0.3).set_placement((2.0, 4.0))
    msp.add_text("DORM", height=0.3).set_placement((8.0, 4.0))
    doc.saveas(path)


class TestCanvasPrimitivas(unittest.TestCase):
    """Primitivas vectoriales añadidas a Canvas (v3.3.0)."""

    def test_line_grosor_pinta_pixeles(self):
        from exporters.png_exporter import Canvas
        canvas = Canvas(40, 30)
        canvas.line(2, 2, 30, 2, (10, 20, 30), thickness=3)
        self.assertEqual(canvas.buf[(2 * 40 + 15) * 3:(2 * 40 + 15) * 3 + 3],
                         bytes((10, 20, 30)))
        # grosor 3: el píxel inferior también quedó pintado
        self.assertEqual(canvas.buf[(3 * 40 + 15) * 3:(3 * 40 + 15) * 3 + 3],
                         bytes((10, 20, 30)))

    def test_line_no_se_cuelga_con_extremos_iguales(self):
        from exporters.png_exporter import Canvas
        canvas = Canvas(10, 10)
        canvas.line(5, 5, 5, 5, (255, 0, 0))
        canvas.line(20, -20, 20, 40, (0, 255, 0))  # fuera del lienzo
        self.assertEqual(canvas.buf[(5 * 10 + 5) * 3:(5 * 10 + 5) * 3 + 3],
                         bytes((255, 0, 0)))

    def test_polygon_fill_area_interior(self):
        from exporters.png_exporter import Canvas
        canvas = Canvas(20, 20)
        canvas.polygon_fill([(2, 2), (18, 2), (18, 18), (2, 18)],
                            (9, 9, 9))
        interior = canvas.buf[(10 * 20 + 10) * 3:(10 * 20 + 10) * 3 + 3]
        self.assertEqual(bytes(interior), bytes((9, 9, 9)))

    def test_arc_y_polyline_sin_excepciones(self):
        from exporters.png_exporter import Canvas
        canvas = Canvas(60, 60)
        canvas.arc(30, 30, 20, 0, 270, (0, 0, 0), thickness=2)
        canvas.polyline([(5, 5), (20, 15), (40, 10)], (0, 0, 255))
        # el arco tocó el punto (30+r, 30) aproximado
        self.assertTrue(any(canvas.buf[((30) * 60 + x) * 3] == 0
                            for x in range(45, 55)))


class TestDXFGUIHeadless(ARQGenTestCase):
    """Capa de diálogo sin display: método, tooltips y reporte."""

    def test_dialogo_dxf_existe_en_la_ventana(self):
        from ui import app_window
        self.assertTrue(hasattr(app_window.ARQGenWindow,
                                "open_importar_dxf"))

    def test_tooltips_dxf_registrados(self):
        from ui.help import TOOLTIPS
        for key in ("dxf_file", "dxf_walls", "dxf_spaces", "dxf_thick",
                    "dxf_level"):
            self.assertIn(key, TOOLTIPS)
            self.assertTrue(TOOLTIPS[key].strip())
        # la ayuda de vistas menciona los tres formatos de exportación
        vistas = TOOLTIPS["bld_views"]
        for token in ("SVG", "PNG", "PDF"):
            self.assertIn(token, vistas)

    def test_menu_herramientas_declara_dxf(self):
        # la entrada del menú apunta al método del asistente DXF
        from ui import app_window
        self.assertTrue(callable(getattr(app_window.ARQGenWindow,
                                         "open_importar_dxf")))


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDXFGuiFlow(ARQGenTestCase):
    """Flujo completo analizar → importar en la ventana real."""

    def setUp(self):
        super().setUp()
        from ui import theme
        from ui.app_window import ARQGenWindow
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")
        theme.set_mode("dark")
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()
        self.window._dxf_sync = True   # pruebas deterministas, sin hilos

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_analizar_muestra_conteos_y_avisos(self):
        dxf_path = os.path.join(self.tmp, "plano.dxf")
        _write_dxf(dxf_path)
        self.window.open_importar_dxf()
        window = self.window
        window._dxf_path.insert(0, dxf_path)
        window._dxf_analyze()
        report = window._dxf_report.get("1.0", "end")
        self.assertIn("ANÁLISIS COMPLETADO", report)
        counts = window._dxf_result.get("counts", {})
        self.assertEqual(counts.get("walls"), 4)
        self.assertEqual(counts.get("spaces"), 2)
        status = window._dxf_status.get()
        self.assertIn("Listo para importar", status)

    def test_analizar_sin_archivo_avisa(self):
        self.window.open_importar_dxf()
        self.window._dxf_analyze()
        self.assertIn("Elige un archivo", self.window._dxf_status.get())

    def test_importar_crea_muros_y_espacios_en_el_proyecto(self):
        from services.architecture_service import ArchitectureService
        dxf_path = os.path.join(self.tmp, "plano.dxf")
        _write_dxf(dxf_path)
        window = self.window
        window.open_importar_dxf()
        window._dxf_path.insert(0, dxf_path)
        window._dxf_level.delete(0, "end")
        window._dxf_level.insert(0, "Planta Importada")
        window._dxf_analyze()
        pid = self.context.project.id
        walls_before = len(self.context.architecture.list("WALL", pid))
        window._dxf_apply()
        result = window._dxf_result
        self.assertEqual(result.get("walls"), 4)
        self.assertEqual(result.get("spaces"), 2)
        self.assertEqual(result.get("level"), "Planta Importada")
        service = ArchitectureService(self.context)
        level = service.get_level_by_name_or_code("Planta Importada")
        walls = self.context.architecture.list("WALL", pid)
        self.assertEqual(len(walls), walls_before + 4)
        spaces = [s for s in self.context.architecture.list("SPACE", pid)
                  if s.level_id == level.id]
        names = {s.name for s in spaces}
        self.assertIn("SALA", names)
        self.assertIn("DORM", names)
        self.assertIn("Importado", window._dxf_status.get())

    def test_importar_sin_proyecto_o_sin_analisis_avisa(self):
        window = self.window
        window.open_importar_dxf()
        window._dxf_path.insert(0, os.path.join(self.tmp, "falta.dxf"))
        window._dxf_apply()
        self.assertIn("Primero analiza", window._dxf_status.get())

    def test_export_hooks_de_vistas_en_el_asistente(self):
        """El asistente de edificación expone SVG, PNG y PDF."""
        window = self.window
        window.open_building_wizard()
        dialog = window._building_dialog
        try:
            self.assertTrue(callable(dialog._bld_export_view_svg))
            self.assertTrue(callable(dialog._bld_export_view_png))
            self.assertTrue(callable(dialog._bld_export_view_pdf))
        finally:
            dialog.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
