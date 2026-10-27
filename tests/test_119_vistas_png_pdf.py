"""Exportación de vistas a PNG y PDF (v3.3.0, brecha #4).

Las 4 vistas del asistente (Planta, Elevación, Corte, Detalles) salen
ahora también en PNG raster (100% stdlib sobre exporters.png_exporter)
y PDF vectorial A4 apaisado con cajetín (100% stdlib sobre
exporters.pdf_exporter). Lienzo Tkinter, SVG, PNG y PDF comparten el
mismo Drawing de core.geometry.representation: los cuatro canales
dibujan lo mismo.

Aquí se verifica: estructura de los contenedores (chunks PNG, objetos
PDF), determinismo byte a byte, las 4 vistas × 3 formatos, tolerancia
con datos vacíos, soporte de muros curvos (arcos orgánicos) y que
PdfDoc conserva su API antigua en grises (retrocompatibilidad).
"""

from __future__ import annotations

import os
import re
import struct
import unittest
import zlib

from ui import building_wizard as bwiz
from tests.base import ARQGenTestCase


def _data(name: str = "Edificio vistas") -> bwiz.BuildingWizardData:
    data = bwiz.BuildingWizardData()
    data.name = name
    bwiz.apply_usage_program(data)
    data.distribucion = "organica"
    data.semilla = 7
    data.curvatura_m = 1.5
    return data


def _variant(data: bwiz.BuildingWizardData):
    variants = bwiz.generate_variants(data)
    assert variants and variants[0].layouts
    return variants[0]


VIEWS_AUX = (("Planta", ""), ("Elevación", "Norte"),
             ("Corte", "Transversal"), ("Detalles", ""))


class TestVistaPNG(ARQGenTestCase):
    """export_view_png: contenedor, determinismo y cobertura de vistas."""

    def test_png_de_las_cuatro_vistas_es_png_valido(self):
        from exporters import view_exporter as ve
        data = _data()
        variant = _variant(data)
        for view, aux in VIEWS_AUX:
            path = os.path.join(self.tmp, f"{view}.png")
            ve.export_view_png(variant, data, path, view=view, aux=aux,
                               title="Prueba")
            raw = open(path, "rb").read()
            self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"), view)
            chunks, pos = [], 8
            while pos < len(raw):
                (length,) = struct.unpack(">I", raw[pos:pos + 4])
                chunks.append(raw[pos + 4:pos + 8].decode())
                pos += 12 + length
            self.assertEqual(chunks[0], "IHDR", view)
            self.assertEqual(chunks[-1], "IEND", view)
            self.assertIn("IDAT", chunks, view)
            self.assertGreater(os.path.getsize(path), 1000, view)

    def test_png_determinista_byte_a_byte(self):
        from exporters import view_exporter as ve
        data = _data("Determinismo")
        variant = _variant(data)
        paths = [os.path.join(self.tmp, f"d{i}.png") for i in range(2)]
        for path in paths:
            ve.export_view_png(variant, data, path, view="Planta",
                               title="T")
        self.assertEqual(open(paths[0], "rb").read(),
                         open(paths[1], "rb").read())

    def test_png_de_vistas_distintas_difiere(self):
        from exporters import view_exporter as ve
        data = _data()
        variant = _variant(data)
        blobs = []
        for view, aux in VIEWS_AUX:
            path = os.path.join(self.tmp, f"{view}_x.png")
            ve.export_view_png(variant, data, path, view=view, aux=aux)
            blobs.append(open(path, "rb").read())
        for index in range(len(blobs) - 1):
            self.assertNotEqual(blobs[index], blobs[index + 1],
                                "dos vistas distintas no deben coincidir")

    def test_png_con_muros_curvos_y_limites_de_resolucion(self):
        from exporters import view_exporter as ve
        data = _data()
        variant = _variant(data)
        # variante orgánica: la planta contiene arcos (PArc)
        drawing = ve.view_drawing(variant, data, "Planta")
        self.assertTrue(any(type(p).__name__ == "PArc"
                            for p in drawing.prims))
        path = os.path.join(self.tmp, "curva.png")
        ve.export_view_png(variant, data, path, view="Planta",
                           px_per_m=40, max_px=600)
        # con max_px el canvas queda acotado aunque el edificio sea grande
        (width, height) = struct.unpack(">II", open(path, "rb").read()[16:24])
        self.assertLessEqual(max(width, height), 1200)


class TestVistaPDF(ARQGenTestCase):
    """export_view_pdf: PDF 1.4 vectorial con cajetín y escala."""

    def test_pdf_de_las_cuatro_vistas(self):
        from exporters import view_exporter as ve
        data = _data()
        variant = _variant(data)
        for view, aux in VIEWS_AUX:
            path = os.path.join(self.tmp, f"{view}.pdf")
            ve.export_view_pdf(variant, data, path, view=view, aux=aux,
                               title="Edificio vistas")
            raw = open(path, "rb").read()
            self.assertTrue(raw.startswith(b"%PDF-1.4"), view)
            self.assertTrue(raw.rstrip().endswith(b"%%EOF"), view)
            self.assertGreater(os.path.getsize(path), 800, view)

    def test_pdf_determinista_y_una_pagina(self):
        from exporters import view_exporter as ve
        data = _data("Casa pdf")
        variant = _variant(data)
        paths = [os.path.join(self.tmp, f"p{i}.pdf") for i in range(2)]
        for path in paths:
            ve.export_view_pdf(variant, data, path, view="Elevación",
                               aux="Norte", title="Elevación norte")
        raw1 = open(paths[0], "rb").read()
        self.assertEqual(raw1, open(paths[1], "rb").read())
        self.assertEqual(raw1.count(b"/Type /Page "), 1)

    def test_pdf_usa_rgb_y_cajetin(self):
        from exporters import view_exporter as ve
        data = _data()
        variant = _variant(data)
        path = os.path.join(self.tmp, "planta.pdf")
        ve.export_view_pdf(variant, data, path, view="Planta",
                           title="Planta arq")
        raw = open(path, "rb").read()
        stream = zlib.decompress(
            re.findall(rb"stream\n(.*?)\nendstream", raw, re.S)[0])
        content = stream.decode("cp1252")
        self.assertIn(" RG", content)   # trazos en color
        self.assertIn(" rg", content)   # rellenos en color
        self.assertIn("Planta", content)  # cajetín con el caption
        self.assertIn("ESC 1:", content)  # escala aproximada

    def test_pdf_con_datos_vacios_no_rompe(self):
        from exporters import view_exporter as ve
        data = bwiz.BuildingWizardData()
        data.name = "Vacio"
        # Detalles solo usa data: con un asistente recién creado la
        # biblioteca de detalles puede estar vacía y no debe romper.
        pdf_path = os.path.join(self.tmp, "detalles.pdf")
        ve.export_view_pdf(None, data, pdf_path, view="Detalles")
        self.assertTrue(open(pdf_path, "rb").read().startswith(b"%PDF-1.4"))
        png_path = os.path.join(self.tmp, "detalles.png")
        ve.export_view_png(None, data, png_path, view="Detalles")
        self.assertTrue(open(png_path, "rb").read().startswith(
            b"\x89PNG\r\n\x1a\n"))


class TestExportViewYRetrocompat(unittest.TestCase):
    """Dispatcher por extensión y compatibilidad de PdfDoc en grises."""

    def test_export_view_despacha_por_extension(self):
        import tempfile
        from exporters import view_exporter as ve
        data = _data("Dispatcher")
        variant = _variant(data)
        tmp = tempfile.mkdtemp()
        produced = []
        for ext in ("svg", "png", "pdf"):
            path = os.path.join(tmp, f"v.{ext}")
            ve.export_view(variant, data, path, view="Planta")
            produced.append(os.path.exists(path))
        self.assertEqual(produced, [True, True, True])
        raw = open(os.path.join(tmp, "v.pdf"), "rb").read()
        self.assertTrue(raw.startswith(b"%PDF-1.4"))

    def test_pdfdoc_grises_sigue_funcionando(self):
        import tempfile
        from exporters.pdf_exporter import PdfDoc
        doc = PdfDoc("Solo grises")
        doc.rect(10, 10, 100, 50, fill_gray=0.92)
        doc.line(0, 0, 60, 60, width=0.8, gray=0.25)
        doc.text(12, 12, 9, "Sin color")
        path = os.path.join(tempfile.gettempdir(), "arq_gray_test.pdf")
        doc.save(path)
        raw = open(path, "rb").read()
        self.assertTrue(raw.startswith(b"%PDF-1.4"))
        stream = zlib.decompress(
            re.findall(rb"stream\n(.*?)\nendstream", raw, re.S)[0])
        content = stream.decode("cp1252")
        self.assertIn("0.92 g", content)
        self.assertIn("0.25 G", content)
        self.assertNotIn(" rg", content)
        self.assertNotIn(" RG", content)


class TestFuenteBitmap(ARQGenTestCase):
    """La fuente 5x7 se lee MSB-primero: sin glifos en espejo (v3.11.0).

    Antes del arreglo, «Canvas.text» leía los bits LSB-primero y cada
    glifo salía reflejado (la L con el palo a la derecha). La corrección
    vale para TODOS los PNG con texto: gráficos de presupuesto, vistas
    del asistente, detalles y la vista 3D.
    """

    def _mapa(self, texto: str):
        from exporters.png_exporter import Canvas
        lienzo = Canvas(40, 20, (255, 255, 255))
        lienzo.text(4, 4, texto, scale=1, color=(0, 0, 0))
        buf = lienzo.buf
        w = lienzo.w

        def negro(x: int, y: int) -> bool:
            return buf[(y * w + x) * 3] == 0

        return [[negro(x, y) for x in range(4, 9)]
                for y in range(4, 11)]

    def test_l_con_el_palo_a_la_izquierda(self):
        mapa = self._mapa("L")
        for fila in mapa[:6]:
            self.assertTrue(fila[0], "el palo de la L va a la izquierda")
            self.assertFalse(fila[4], "la L no debe salir en espejo")
        self.assertTrue(all(mapa[6]), "la base de la L es horizontal")

    def test_p_con_la_panza_a_la_izquierda(self):
        mapa = self._mapa("P")
        # panza arriba (filas 0 y 3 llenas salvo la última columna)
        for fila in (0, 3):
            self.assertTrue(all(mapa[fila][:4]), mapa[fila])
            self.assertFalse(mapa[fila][4], "la P no debe salir en espejo")
        # palo abajo solo en la primera columna
        for fila in (4, 5, 6):
            self.assertTrue(mapa[fila][0])
            self.assertFalse(any(mapa[fila][1:]), mapa[fila])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
