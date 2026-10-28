"""MÁS PIELES DE FACHADA v3.45.0 — domain/elevaciones.py.

v3.45 pasa de 4 a 12 pieles deterministas: hexagonal (malla de
celdas), diagrid (diagonales cruzadas), celosia (breeze block),
gradiente (perforación con radio decreciente), fins (aletas
profundas), cortina (muro cortina con spandrel), bandas (banda opaca
+ vidrio) y parametrica (paneles facetados de ancho variable) junto
a las 4 de v3.44 (panos, ventana_corrida, brise, perforada).

Cobertura:
  * las 12 pieles generan entidades en los 4 lados
  * hexagonal: celdas de 6 líneas en FACH_PERFORACION
  * diagrid y celosia: malla PURA (sin ventanas por paño)
  * gradiente: el radio de perforación decrece con la altura
  * cortina: montantes a todo el alto + spandrel opaco
  * fins: aletas dobles separadas 0.12 m
  * parametrica: montantes con espaciado IRREGULAR (torsión)
  * determinismo, ValueError con piel desconocida
  * PNG y DXF R12 en disco con las capas FACH_*
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core import APP_VERSION
from domain import elevaciones as fc

CONT = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]

NUEVAS = ("hexagonal", "diagrid", "celosia", "gradiente",
          "fins", "cortina", "bandas", "parametrica")


class TestPielesNuevas(unittest.TestCase):

    def test_doce_pieles_generan_entidades(self):
        self.assertEqual(len(fc.PIELES), 12)
        for piel in fc.PIELES:
            res = fc.elevacion(CONT, n_pisos=3, piel=piel)
            self.assertEqual(len(res["fachadas"]), 4, piel)
            n = sum(len(f["entidades"]) for f in res["fachadas"])
            self.assertGreater(n, 40, piel)

    def test_hexagonal_celdas_de_seis_lineas(self):
        res = fc.elevacion(CONT, n_pisos=2, piel="hexagonal")
        lineas_perf = [e for f in res["fachadas"] for e in
                       f["entidades"] if e["tipo"] == "linea"
                       and e.get("capa") == "FACH_PERFORACION"]
        self.assertGreater(len(lineas_perf), 0)
        self.assertEqual(len(lineas_perf) % 6, 0,
                         "cada celda hexagonal son 6 líneas")

    def test_diagrid_y_celosia_malla_pura(self):
        for piel in ("diagrid", "celosia"):
            res = fc.elevacion(CONT, n_pisos=3, piel=piel)
            capas = {e.get("capa") for f in res["fachadas"]
                     for e in f["entidades"]}
            self.assertNotIn("FACH_VENTANA", capas, piel)
            self.assertIn("FACH_LAMAS", capas, piel)

    def test_gradiente_radio_decreciente(self):
        res = fc.elevacion(CONT, n_pisos=3, piel="gradiente")
        circulos = [e for f in res["fachadas"] for e in
                    f["entidades"] if e["tipo"] == "circulo"]
        self.assertGreater(len(circulos), 10)
        abajo = min(c["cy"] for c in circulos)
        arriba = max(c["cy"] for c in circulos)
        r_abajo = max(c["r"] for c in circulos if c["cy"] == abajo)
        r_arriba = max(c["r"] for c in circulos
                       if c["cy"] == arriba)
        self.assertGreater(r_abajo, r_arriba,
                           "el radio decrece con la altura")

    def test_cortina_montantes_a_todo_el_alto(self):
        res = fc.elevacion(CONT, n_pisos=3, piel="cortina")
        lado1 = res["fachadas"][0]
        mullions = [e for e in lado1["entidades"]
                    if e["tipo"] == "linea"
                    and e.get("capa") == "FACH_VENTANA"
                    and e["x1"] == e["x2"] and e["y1"] == 0.0
                    and e["y2"] == res["altura_total_m"]]
        self.assertGreaterEqual(len(mullions), 3)
        spandrels = [e for e in lado1["entidades"]
                     if e["tipo"] == "linea"
                     and e.get("capa") == "FACH_MURO"
                     and e["y1"] == e["y2"]]
        self.assertGreaterEqual(len(spandrels), 3)

    def test_fins_aletas_dobles(self):
        res = fc.elevacion(CONT, n_pisos=2, piel="fins")
        xs = sorted({e["x1"] for f in res["fachadas"][:1]
                     for e in f["entidades"]
                     if e["tipo"] == "linea"
                     and e.get("capa") == "FACH_LAMAS"})
        self.assertGreaterEqual(len(xs), 4)
        pares = sum(1 for a, b in zip(xs, xs[1:])
                    if abs(b - a - 0.12) < 1e-6)
        self.assertGreaterEqual(pares, 3,
                                "cada aleta lleva su doble a 0.12 m")

    def test_parametrica_montantes_irregulares(self):
        res = fc.elevacion(CONT, n_pisos=3, piel="parametrica")
        lado1 = res["fachadas"][0]
        xs = sorted({e["x1"] for e in lado1["entidades"]
                     if e["tipo"] == "linea"
                     and e.get("capa") == "FACH_MURO"
                     and e["x1"] == e["x2"] and e["y1"] == 0.0})
        self.assertGreater(len(xs), 5)
        pasos = {round(b - a, 3) for a, b in zip(xs, xs[1:])}
        self.assertGreater(len(pasos), 1,
                           "el ancho aparente de los paneles varía")

    def test_bandas_con_banda_opaca(self):
        res = fc.elevacion(CONT, n_pisos=2, piel="bandas")
        lado1 = res["fachadas"][0]
        opacas = [e for e in lado1["entidades"]
                  if e["tipo"] == "linea"
                  and e.get("capa") == "FACH_MURO"
                  and e["y1"] == e["y2"]
                  and abs(e["y1"] - 0.35) < 1e-6]
        self.assertGreaterEqual(len(opacas), 1)

    def test_determinista_en_las_nuevas(self):
        for piel in ("hexagonal", "parametrica", "cortina"):
            a = fc.elevacion(CONT, piel=piel, n_pisos=2, ritmo_m=1.2)
            b = fc.elevacion(CONT, piel=piel, n_pisos=2, ritmo_m=1.2)
            self.assertEqual(a, b, piel)

    def test_piel_desconocida_sigue_lanzando(self):
        with self.assertRaises(ValueError):
            fc.elevacion(CONT, piel="churrigueresca")


class TestSalidasNuevas(unittest.TestCase):

    def test_png_hexagonal_en_disco(self):
        res = fc.elevacion(CONT, piel="hexagonal", n_pisos=2)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "hex.png")
            fc.render_elevacion_png(res, ruta)
            self.assertTrue(os.path.exists(ruta))
            self.assertGreater(os.path.getsize(ruta), 10000)

    def test_dxf_gradiente_con_capas(self):
        import ezdxf
        res = fc.elevacion(CONT, piel="gradiente", n_pisos=2)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "grad.dxf")
            fc.exportar_elevacion_dxf(res, ruta)
            doc = ezdxf.readfile(ruta)
            nombres = [l.dxf.name for l in doc.layers
                       if l.dxf.name.startswith("FACH")]
            for esperada in ("FACH_MURO", "FACH_PERFORACION",
                             "FACH_TEXTO"):
                self.assertIn(esperada, nombres)
            self.assertGreater(len(list(doc.modelspace())), 40)


class TestContratos(unittest.TestCase):

    def test_version_3450(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
