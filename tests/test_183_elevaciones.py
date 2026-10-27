"""ELEVACIONES PARAMÉTRICAS v3.44.0 (FASE E) — domain/elevaciones.py.

``elevacion`` genera las elevaciones de los lados del contorno con
4 pieles deterministas (panos, ventana_corrida, brise, perforada),
con render PNG (matplotlib) y export DXF R12 por capas (LINE,
CIRCLE, TEXT con ezdxf): la maquinaria de pieles de las imágenes de
referencia (paños, banda corrida, celosía, panel perforado).

Cobertura:
  * las 4 pieles generan entidades en los 4 lados
  * puerta de acceso en el primer paño del lado 1
  * determinismo (mismos parámetros -> mismas entidades)
  * ValueError con piel desconocida y contorno degenerado
  * PNG y DXF en disco; el DXF se reabre con ezdxf y trae capas
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core import APP_VERSION
from domain import elevaciones as fc

CONT = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]


class TestElevacion(unittest.TestCase):

    def test_cuatro_pieles_generan_entidades(self):
        for piel in fc.PIELES:
            res = fc.elevacion(CONT, n_pisos=3, piel=piel)
            self.assertEqual(len(res["fachadas"]), 4, piel)
            n = sum(len(f["entidades"]) for f in res["fachadas"])
            self.assertGreater(n, 40, piel)
            self.assertEqual(res["n_pisos"], 3)
            self.assertAlmostEqual(res["altura_total_m"], 9.0)

    def test_puerta_en_el_lado_1(self):
        res = fc.elevacion(CONT, n_pisos=1, piel="panos",
                           puerta=True)
        lado1 = res["fachadas"][0]
        ys = [e["y1"] for e in lado1["entidades"]
              if e["tipo"] == "linea" and e.get("capa")
              == "FACH_VENTANA"]
        self.assertIn(0.0, [round(v, 3) for v in ys])

    def test_determinista(self):
        a = fc.elevacion(CONT, piel="brise", n_pisos=2, ritmo_m=1.2)
        b = fc.elevacion(CONT, piel="brise", n_pisos=2, ritmo_m=1.2)
        self.assertEqual(a, b)

    def test_piel_desconocida_value_error(self):
        with self.assertRaises(ValueError):
            fc.elevacion(CONT, piel="churrigueresca")

    def test_contorno_degenerado(self):
        with self.assertRaises(ValueError):
            fc.elevacion([(0.0, 0.0), (5.0, 0.0)], piel="panos")

    def test_alturas_recortadas_sanamente(self):
        res = fc.elevacion(CONT, n_pisos=1, altura_piso_m=2.5,
                           antepecho_m=1.5, ventana_m=2.5)
        self.assertLessEqual(res["parametros"]["ventana_m"],
                             res["altura_piso_m"]
                             - res["parametros"]["antepecho_m"]
                             - 0.3 + 1e-9)


class TestSalidas(unittest.TestCase):

    def test_png_en_disco(self):
        res = fc.elevacion(CONT, piel="perforada", n_pisos=2)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "fachadas.png")
            fc.render_elevacion_png(res, ruta)
            self.assertTrue(os.path.exists(ruta))
            self.assertGreater(os.path.getsize(ruta), 10000)

    def test_dxf_en_disco_con_capas(self):
        import ezdxf
        res = fc.elevacion(CONT, piel="brise", n_pisos=2)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "fachadas.dxf")
            fc.exportar_elevacion_dxf(res, ruta)
            self.assertTrue(os.path.exists(ruta))
            doc = ezdxf.readfile(ruta)
            nombres = [l.dxf.name for l in doc.layers
                       if l.dxf.name.startswith("FACH")]
            for esperada in ("FACH_MURO", "FACH_VENTANA",
                             "FACH_LAMAS", "FACH_TEXTO"):
                self.assertIn(esperada, nombres)
            entidades = list(doc.modelspace())
            self.assertGreater(len(entidades), 50)


class TestContratos(unittest.TestCase):

    def test_version_3440(self):
        self.assertEqual(APP_VERSION, "3.47.0")


if __name__ == "__main__":
    unittest.main()
