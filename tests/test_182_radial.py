"""GEOMETRÍA CURVA/RADIAL v3.44.0 (FASE D) — domain/radial.py.

``plan_radial`` genera la planta de N sectores radiales alrededor de
un núcleo circular con corredor anular (torres y hospitales
radiantes de las imágenes). Los arcos van por CUERDAS: el modelo de
datos sigue siendo de poligonales, así que aplicar_plan y el DXF
funcionan sin cambios.

Cobertura:
  * anillo lleno (99-100 %), corredor anular, núcleo con el
    vestíbulo dentro, dentro_del_contorno True
  * mínimos del DNA respetados en el crecimiento proporcional
  * errores: ARQ-DDI-011 (no cabe), ARQ-DDI-012 (núcleo sin
    vestíbulo; radio pequeño; sectores fuera de rango)
  * cuerdas suaves (muchos vértices por arco) y determinismo
  * aplicar_plan aplica la planta radial y OMITE el mobiliario
    automático (geometría curva) con aviso
"""

from __future__ import annotations

import math
import unittest

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import radial as rd
from tests.base import ARQGenTestCase


def _torre() -> dict:
    return dd.programa_edificacion([
        {"space_type": "VESTIBULE", "cantidad": 1},
        {"space_type": "BEDROOM", "cantidad": 12},
        {"space_type": "BATHROOM", "cantidad": 6},
    ], "Torre radiante")


class TestPlanRadial(unittest.TestCase):

    def test_anillo_lleno_con_corredor_y_nucleo(self):
        aj = rd.plan_radial(_torre(), radio_ext=14.0,
                            radio_nucleo=3.0, sectores=8,
                            corredor_m=1.6)
        self.assertEqual(aj["tipo"], "radial")
        plan = aj["reparto"][0]
        self.assertIsNotNone(plan["pasillo"])
        self.assertEqual(plan["pasillo"]["space_type"], "CORRIDOR")
        tipos = [r["space_type"] for r in plan["locales"]]
        self.assertIn("VESTIBULE", tipos)
        nucleo = [r for r in plan["locales"]
                  if r["space_type"] == "VESTIBULE"][0]
        esperado = math.pi * 9.0
        self.assertAlmostEqual(float(nucleo["area_m2"]), esperado,
                               delta=esperado * 0.05)
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertGreater(
            aj["totales"]["aprovechamiento_pct"], 95.0)

    def test_locales_no_bajan_del_minimo_dna(self):
        aj = rd.plan_radial(_torre(), radio_ext=14.0,
                            radio_nucleo=3.0, sectores=8,
                            corredor_m=1.6)
        for r in aj["reparto"][0]["locales"]:
            if float(r.get("area_min") or 0.0) > 0.0:
                self.assertGreaterEqual(float(r["area_m2"]),
                                        float(r["area_min"]) - 0.01,
                                        r["nombre"])

    def test_cuerdas_suaves(self):
        aj = rd.plan_radial(_torre(), radio_ext=14.0,
                            radio_nucleo=3.0, sectores=8,
                            corredor_m=1.6, chord_m=0.2)
        pas = aj["reparto"][0]["pasillo"]
        self.assertGreater(len(pas["poligono"]), 60)

    def test_determinista(self):
        a = rd.plan_radial(_torre(), radio_ext=14.0, sectores=8)
        b = rd.plan_radial(_torre(), radio_ext=14.0, sectores=8)
        self.assertEqual([r["poligono"] for r in
                          a["reparto"][0]["locales"]],
                         [r["poligono"] for r in
                          b["reparto"][0]["locales"]])

    def test_sin_corredor_sin_nucleo(self):
        aj = rd.plan_radial(_torre(), radio_ext=14.0, sectores=6,
                            corredor_m=0.0, radio_nucleo=0.0)
        self.assertIsNone(aj["reparto"][0]["pasillo"])

    def test_desbordamiento_lanza_011(self):
        grande = dd.programa_edificacion(
            [{"space_type": "WARD", "cantidad": 30}], "Grande")
        with self.assertRaises(DomainError) as cm:
            rd.plan_radial(grande, radio_ext=8.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-011")

    def test_nucleo_sin_vestibulo_lanza_012(self):
        solo = dd.programa_edificacion(
            [{"space_type": "BEDROOM", "cantidad": 4}], "Solo")
        with self.assertRaises(DomainError) as cm:
            rd.plan_radial(solo, radio_ext=12.0, radio_nucleo=3.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_radio_pequeno_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_radial(_torre(), radio_ext=2.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_sectores_fuera_de_rango(self):
        with self.assertRaises(DomainError):
            rd.plan_radial(_torre(), radio_ext=14.0, sectores=99)


class TestAplicarRadial(ARQGenTestCase):

    def test_aplicar_plan_radial_sin_mobiliario(self):
        aj = rd.plan_radial(_torre(), radio_ext=14.0,
                            radio_nucleo=3.0, sectores=8,
                            corredor_m=1.6)
        ctx = self.application.create_project(
            self.project_path("v44rad.arqgen"), name="v44rad")
        res = dd.aplicar_plan(ctx, aj,
                              {"nombre_edificio": "Torre radiante"})
        self.assertGreaterEqual(len(res["espacios"]), 15)
        self.assertFalse(res["mobiliario"]["activado"])
        self.assertTrue(any("radial" in a.lower()
                            for a in res["avisos"]))


class TestContratos(unittest.TestCase):

    def test_version_3440(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
