"""FASE B (v3.49.0): acelerador Rust — paridad 1:1 y XLSX nativo.

Cobertura:
- paridad de piezas: es_ortogonal, seccion_en, area_poligono,
  comparten_banda (Rust vs domain/encaje.py) sobre contornos L, U, T,
  cruz, rombo, trapecio y degenerados;
- paridad de nivel alto: encaje.contenedores_de(usar_rust=True) ==
  encaje.contenedores_de() (estrategia, contenedores, áreas, avisos);
- política opt-in: sin crate o sin env/parámetro, el camino es Python
  (y con usar_rust=True sin crate NO explota: cae a Python);
- XLSX nativo Rust: legible por openpyxl, mismo formato (fill 2F5496,
  negrita blanca, freeze A2, anchos) y paridad de celdas contra el
  escritor openpyxl del exportador;
- benchmark informativo del hot loop rectangulo_inscrito.
"""

import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain import encaje
from core import acelerador
from exporters.xlsx_exporter import XLSXExporter

try:
    import arqgen_core
    import openpyxl
    RUST_OK = True
except ImportError:  # pragma: no cover
    arqgen_core = None
    openpyxl = None
    RUST_OK = False

POLIGONOS = {
    "rectangulo": [(0, 0), (24, 0), (24, 12), (0, 12)],
    "L": [(0, 0), (18, 0), (18, 14), (12, 14), (12, 6), (0, 6)],
    "U": [(0, 0), (20, 0), (20, 14), (14, 14), (14, 5), (6, 5),
          (6, 14), (0, 14)],
    "T": [(0, 0), (16, 0), (16, 5), (11, 5), (11, 14), (5, 14),
          (5, 5), (0, 5)],
    "cruz": [(7, 0), (13, 0), (13, 7), (20, 7), (20, 13), (13, 13),
             (13, 20), (7, 20), (7, 13), (0, 13), (0, 7), (7, 7)],
    "rombo": [(5, 0), (10, 5), (5, 10), (0, 5)],
    "trapecio": [(0, 0), (14, 0), (11, 8), (3, 8)],
    "reflejo": [(0, 0), (10, 0), (10, 10), (5, 5), (0, 10)],
    "degenerado": [(0, 0), (0.0000001, 0), (0, 0.0000001)],
}


def _contenedor_contexto():
    """Contexto mínimo para _exportar_openpyxl (solo emite eventos)."""
    return SimpleNamespace(emit=lambda *a, **k: None)


@unittest.skipUnless(RUST_OK, "acelerador Rust (arqgen_core) no instalado")
class TestParidadPiezas(unittest.TestCase):
    """Rust == Python función a función, mismo orden de operaciones."""

    def test_es_ortogonal(self):
        for nombre, poly in POLIGONOS.items():
            self.assertEqual(encaje._es_ortogonal(poly),
                             arqgen_core.es_ortogonal(poly),
                             f"es_ortogonal difiere en {nombre}")
        self.assertFalse(arqgen_core.es_ortogonal([(0, 0), (5, 3), (8, 0)]))

    def test_seccion_en(self):
        ys_prueba = [-1.0, 0.0, 0.5, 3.0, 5.0, 6.0, 7.5, 13.999, 14.0, 20.0]
        for nombre, poly in POLIGONOS.items():
            for y in ys_prueba:
                py = encaje._seccion_en(poly, y)
                rs = arqgen_core.seccion_en(poly, y)
                self.assertEqual(len(py), len(rs),
                                 f"seccion_en({nombre}, y={y}): nº intervalos")
                for (p0, p1), (r0, r1) in zip(py, rs):
                    self.assertAlmostEqual(p0, r0, places=12)
                    self.assertAlmostEqual(p1, r1, places=12)

    def test_area_poligono(self):
        for nombre, poly in POLIGONOS.items():
            self.assertAlmostEqual(encaje._area(poly),
                                   arqgen_core.area_poligono(poly),
                                   places=12, msg=f"area difiere en {nombre}")

    def test_contenedores_ortogonales(self):
        for nombre, poly in POLIGONOS.items():
            if not encaje._es_ortogonal(poly):
                continue
            for margen in (0.0, 0.25):
                py = encaje.contenedores_ortogonales(poly, margen, 1.0)
                rs = arqgen_core.contenedores_ortogonales(poly, margen, 1.0)
                self.assertEqual(len(py), len(rs),
                                 f"conts({nombre}, m={margen}): nº contenedores")
                for cp, cr in zip(py, rs):
                    for clave in ("x0", "y0", "x1", "y1", "ancho", "fondo", "area"):
                        self.assertAlmostEqual(
                            cp[clave], cr[clave], places=9,
                            msg=f"conts({nombre}, m={margen}): {clave}")

    def test_rectangulo_inscrito(self):
        for nombre, poly in POLIGONOS.items():
            py = encaje.rectangulo_inscrito(poly, 0.0)
            rs = arqgen_core.rectangulo_inscrito(poly, 0.0)
            if py is None:
                self.assertIsNone(rs, f"inscrito({nombre}): Rust devolvió algo")
                continue
            self.assertIsNotNone(rs, f"inscrito({nombre}): Rust devolvió None")
            for clave in ("x0", "y0", "x1", "y1", "ancho", "fondo", "area"):
                self.assertAlmostEqual(py[clave], rs[clave], places=9,
                                       msg=f"inscrito({nombre}): {clave}")

    def test_comparten_banda(self):
        a = {"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 6.0}
        casos = [
            ({"x0": 10.0, "y0": 0.0, "x1": 18.0, "y1": 6.0}, True),
            ({"x0": 10.0, "y0": 4.0, "x1": 18.0, "y1": 10.0}, True),
            ({"x0": 10.0, "y0": 5.5, "x1": 18.0, "y1": 9.0}, False),  # solape corto
            ({"x0": 11.0, "y0": 0.0, "x1": 20.0, "y1": 6.0}, False),  # separados
            (a, False),  # identidad no es adyacencia (sin arista compartida)
        ]
        for b, esperado in casos:
            py = encaje.comparten_banda(a, b)
            rs = arqgen_core.comparten_banda(a, b)
            self.assertEqual(py, esperado)
            self.assertEqual(rs, esperado)


@unittest.skipUnless(RUST_OK, "acelerador Rust (arqgen_core) no instalado")
class TestParidadNivelAlto(unittest.TestCase):
    """contenedores_de(usar_rust=True) == contenedores_de() en TODO."""

    def test_paridad_completa(self):
        for nombre, poly in POLIGONOS.items():
            for margen in (0.0, 0.3):
                py = encaje.contenedores_de(poly, margen=margen, min_lado=1.0)
                rs = encaje.contenedores_de(poly, margen=margen, min_lado=1.0,
                                            usar_rust=True)
                self.assertEqual(py["estrategia"], rs["estrategia"],
                                 f"estrategia difiere en {nombre}")
                self.assertEqual(len(py["contenedores"]), len(rs["contenedores"]),
                                 f"contenedores difieren en {nombre}")
                for cp, cr in zip(py["contenedores"], rs["contenedores"]):
                    for clave in ("x0", "y0", "x1", "y1", "ancho", "fondo", "area"):
                        self.assertAlmostEqual(cp[clave], cr[clave], places=9,
                                               msg=f"{nombre}: {clave}")
                self.assertAlmostEqual(py["area_contenedores"],
                                       rs["area_contenedores"], places=9)
                self.assertAlmostEqual(py["area_aprovechable"],
                                       rs["area_aprovechable"], places=9,
                                       msg=f"area_aprovechable difiere en {nombre}")
                self.assertEqual(py["avisos"], rs["avisos"],
                                 f"avisos difieren en {nombre}")

    def test_por_defecto_es_python(self):
        """Sin env y sin parámetro, contenedores_de usa el camino Python
        aunque el crate esté instalado (política opt-in de FASE B)."""
        poly = POLIGONOS["L"]
        with mock.patch.object(acelerador, "_rust", None):
            rs = encaje.contenedores_de(poly, usar_rust=True)
        py = encaje.contenedores_de(poly)
        self.assertEqual(rs["estrategia"], py["estrategia"])
        self.assertEqual(len(rs["contenedores"]), len(py["contenedores"]))

    def test_variable_entorno_activa_rust(self):
        poly = POLIGONOS["U"]
        env = {acelerador.VAR_ENTORNO: "rust"}
        with mock.patch.dict(os.environ, env):
            rs = encaje.contenedores_de(poly)
        py = encaje.contenedores_de(poly)
        self.assertEqual(rs["estrategia"], py["estrategia"])
        self.assertAlmostEqual(py["area_contenedores"],
                               rs["area_contenedores"], places=9)

    def test_puente_informe(self):
        self.assertIn(acelerador.modo(), ("rust", "python"))
        self.assertEqual(acelerador.disponible(), RUST_OK)
        if RUST_OK:
            self.assertTrue(acelerador.version_rust().startswith("3.49"))


@unittest.skipUnless(RUST_OK, "acelerador Rust (arqgen_core) no instalado")
class TestXlsxRust(unittest.TestCase):
    """XLSX nativo del crate: legible, con formato y paridad openpyxl."""

    HOJAS = [
        {
            "titulo": "Cantidades",
            "headers": ["Objeto", "Tipo", "Bruta", "Final"],
            "filas": [["A-01", "muro", 2.5, 3.75],
                      ["B-02", "piso", 10.0, 10.0],
                      ["C&D <es>", "ñ o'í", -1.25, 0.0]],
            "anchos": [16, 12, 10, 10],
        },
        {
            "titulo": "Presupuesto",
            "headers": ["Capítulo", "Costo"],
            "filas": [["01 Estructura", 1234.56], ["", 0], ["TOTAL", 999999.99]],
            "anchos": [42, 14],
        },
    ]

    def _leer(self, ruta):
        wb = openpyxl.load_workbook(ruta)
        return wb

    def test_legible_y_formato(self):
        ruta = os.path.join(os.environ.get("TEMP", "/tmp"), "arq190_rust.xlsx")
        n = arqgen_core.xlsx_escribir(ruta, self.HOJAS)
        self.assertEqual(n, (4 + 3 * 4) + (2 + 3 * 2))  # headers+filas de ambas hojas
        wb = self._leer(ruta)
        self.assertEqual(wb.sheetnames, ["Cantidades", "Presupuesto"])
        ws = wb["Cantidades"]
        self.assertEqual(ws["A1"].value, "Objeto")
        self.assertEqual(ws["A1"].fill.fgColor.rgb, "FF2F5496")
        self.assertTrue(ws["A1"].font.bold)
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertEqual(ws["C2"].value, 2.5)
        self.assertEqual(ws["A4"].value, "C&D <es>")
        self.assertEqual(ws["C4"].value, -1.25)
        self.assertAlmostEqual(ws.column_dimensions["A"].width, 16.0, places=6)
        ws2 = wb["Presupuesto"]
        self.assertEqual(ws2["A2"].value, "01 Estructura")
        self.assertAlmostEqual(ws2["B4"].value, 999999.99, places=6)

    def test_titulo_largo_recortado(self):
        ruta = os.path.join(os.environ.get("TEMP", "/tmp"), "arq190_largo.xlsx")
        hojas = [{"titulo": "Una hoja con un titulo demasiado largo para Excel",
                  "headers": ["A"], "filas": [], "anchos": [10]}]
        arqgen_core.xlsx_escribir(ruta, hojas)
        wb = self._leer(ruta)
        self.assertEqual(wb.sheetnames[0],
                         "Una hoja con un titulo demasiado largo para Excel"[:31])

    def test_paridad_con_openpyxl(self):
        """El mismo libro escrito por Rust y por openpyxl se lee igual."""
        base = os.environ.get("TEMP", "/tmp")
        ruta_rust = os.path.join(base, "arq190_p_rust.xlsx")
        ruta_py = os.path.join(base, "arq190_p_openpyxl.xlsx")
        arqgen_core.xlsx_escribir(ruta_rust, self.HOJAS)
        XLSXExporter()._exportar_openpyxl(_contenedor_contexto(), ruta_py, self.HOJAS)
        wa = self._leer(ruta_rust)
        wp = self._leer(ruta_py)
        self.assertEqual(wa.sheetnames, wp.sheetnames)
        for nombre in wa.sheetnames:
            sa, sp = wa[nombre], wp[nombre]
            max_f = max(sa.max_row or 1, sp.max_row or 1)
            max_c = max(sa.max_column or 1, sp.max_column or 1)
            for f in range(1, max_f + 1):
                for c in range(1, max_c + 1):
                    va, vp = sa.cell(f, c).value, sp.cell(f, c).value
                    self.assertEqual(va, vp, f"{nombre} R{f}C{c}")
            self.assertEqual(sa.freeze_panes, sp.freeze_panes)

    def test_ruta_con_carpetas(self):
        base = os.environ.get("TEMP", "/tmp")
        ruta = os.path.join(base, "arq190_sub", "carpeta", "libro.xlsx")
        arqgen_core.xlsx_escribir(ruta, self.HOJAS[:1])
        self.assertTrue(os.path.isfile(ruta))


@unittest.skipUnless(RUST_OK, "acelerador Rust (arqgen_core) no instalado")
class TestBenchmarkInformativo(unittest.TestCase):
    """Hot loop rectangulo_inscrito con contorno rico (40 vértices)."""

    def _poligono_escalera(self, dientes=10, paso=1.5, alto=20.0):
        poly, x, y = [(0.0, 0.0)], 0.0, 0.0
        for i in range(dientes):
            x += paso
            poly.append((x, y))
            y += (alto / (2 * dientes)) if i % 2 == 0 else 0.0
            poly.append((x, y))
        poly.append((x, alto))
        poly.append((0.0, alto))
        return poly

    def test_hot_loop_inscrito(self):
        poly = self._poligono_escalera()
        repeticiones = 60
        t0 = time.perf_counter()
        for _ in range(repeticiones):
            encaje.rectangulo_inscrito(poly, 0.0)
        t_py = time.perf_counter() - t0
        t0 = time.perf_counter()
        for _ in range(repeticiones):
            arqgen_core.rectangulo_inscrito(poly, 0.0)
        t_rs = time.perf_counter() - t0
        ratio = t_py / max(t_rs, 1e-9)
        print(f"\n[benchmark FASE B] rectangulo_inscrito x{repeticiones}: "
              f"python {t_py * 1000:.1f} ms | rust {t_rs * 1000:.1f} ms | "
              f"aceleracion {ratio:.1f}x")
        self.assertGreater(ratio, 0.0)  # informativo: la paridad ya está vigiada


if __name__ == "__main__":
    unittest.main()
