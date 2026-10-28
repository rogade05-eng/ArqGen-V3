"""Y DESIGUAL + NIVELES v3.48.0 — domain/radial.py.

``largos_alas`` en ``plan_y``: la estrella radial de alas de
longitudes DESIGUALES (el hospital oncológico de referencia: brazos
de distinto largo alrededor del núcleo circular). ``niveles`` en
``plan_y``/``plan_radial``: la planta tipo se repite en N plantas
(sótano de servicios / planta científica / planta típica).

Cobertura:
  * 4 alas de largos [18, 13, 20, 11] dentro del contorno Y real
  * contorno cerrado: perímetro calculado == suma de aristas
  * corredores con largos desiguales (área/ancho distintos por ala)
  * cabecera solo en las alas y por el área de cada una
  * determinismo y retrocompatibilidad (sin largos_alas = uniforme)
  * niveles de planta tipo en plan_y y plan_radial (reparto de N
    entradas idénticas salvo el número de nivel; altura_total = N·h)
  * errores: ARQ-DDI-012 (largos_alas con longitud equivocada, ala
    corta, cabecera que no deja filas)
  * aplicar_plan crea las N plantas
"""

from __future__ import annotations

import math
import unittest

from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import radial as rd
from tests.base import ARQGenTestCase


def _mixto() -> dict:
    return dd.programa_edificacion([
        {"space_type": "VESTIBULE", "cantidad": 1},
        {"space_type": "LABORATORY", "cantidad": 2},
        {"space_type": "MICROBIOLOGY_LAB", "cantidad": 2},
        {"space_type": "WARD", "cantidad": 5},
        {"space_type": "NURSE_STATION", "cantidad": 2},
        {"space_type": "BATHROOM", "cantidad": 5},
        {"space_type": "OFFICE", "cantidad": 2},
        {"space_type": "LAVATORY", "cantidad": 4},
        {"space_type": "STOREROOM", "cantidad": 2},
    ], "Hospital radial mixto")


class TestLargosAlas(unittest.TestCase):

    def test_estrella_desigual_dentro(self):
        aj = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6, cabecera_m=4.0,
                       largos_alas=[18.0, 13.0, 20.0, 11.0])
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertEqual(aj["y_radial"]["largos_alas"],
                         [18.0, 13.0, 20.0, 11.0])
        plan = aj["reparto"][0]
        self.assertEqual(len(plan["pasillos"]), 4)
        # largos de corredor desiguales (área / ancho)
        largos = sorted({round(float(p["area_m2"])
                              / float(p["ancho_m"]), 1)
                         for p in plan["pasillos"]})
        self.assertEqual(largos, [7.0, 9.0, 14.0, 16.0])

    def test_contorno_cierra_exacto(self):
        aj = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6,
                       largos_alas=[18.0, 13.0, 20.0, 11.0])
        vs = aj["forma"]["vertices"]
        per = sum(math.hypot(vs[(i + 1) % len(vs)][0] - vs[i][0],
                             vs[(i + 1) % len(vs)][1] - vs[i][1])
                  for i in range(len(vs)))
        self.assertAlmostEqual(per,
                               aj["forma"]["perimetro_m"], places=1)
        self.assertGreater(aj["totales"]["aprovechamiento_pct"], 90.0)

    def test_cabeceras_en_alas_desiguales(self):
        aj = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6, cabecera_m=4.0,
                       largos_alas=[18.0, 13.0, 20.0, 11.0])
        plan = aj["reparto"][0]
        cabs = [r for r in plan["locales"]
                if r["nombre"].startswith("Cabecera")]
        self.assertEqual(len(cabs), 4)
        for c in cabs:
            # la cabecera mide cab x ancho en TODAS las alas
            self.assertAlmostEqual(float(c["area_m2"]),
                                   4.0 * (12.0 - 0.002), delta=0.05)

    def test_determinismo(self):
        a1 = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6,
                       largos_alas=[18.0, 13.0, 20.0, 11.0])
        a2 = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6,
                       largos_alas=[18.0, 13.0, 20.0, 11.0])
        self.assertEqual(a1["forma"]["vertices"],
                         a2["forma"]["vertices"])
        self.assertEqual([r["poligono"] for r in
                          a1["reparto"][0]["locales"]],
                         [r["poligono"] for r in
                          a2["reparto"][0]["locales"]])

    def test_retrocompatible_sin_largos(self):
        aj = rd.plan_y(_mixto(), radio_nucleo=9.0, largo_ala=16.0,
                       ancho_ala=12.0, n_alas=4, corredor_m=1.6)
        self.assertIsNone(aj["y_radial"]["largos_alas"])
        plan = aj["reparto"][0]
        largos = {round(float(p["area_m2"]) / float(p["ancho_m"]), 1)
                  for p in plan["pasillos"]}
        self.assertEqual(len(largos), 1)

    def test_largos_incompleto_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                      n_alas=4, largos_alas=[18.0, 13.0])
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_ala_corta_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                      n_alas=4, largos_alas=[18.0, 13.0, 20.0, 2.0])
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_cabecera_vs_ala_corta_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                      n_alas=4, cabecera_m=4.0,
                      largos_alas=[18.0, 13.0, 20.0, 6.0])
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")


class TestNivelesPlantaTipo(ARQGenTestCase):

    def test_plan_y_niveles(self):
        aj = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6,
                       largos_alas=[18.0, 13.0, 20.0, 11.0],
                       niveles=2, altura_nivel_m=3.0)
        self.assertEqual(aj["niveles"], 2)
        self.assertEqual(len(aj["reparto"]), 2)
        self.assertEqual([p["nivel"] for p in aj["reparto"]],
                         [1, 2])
        self.assertAlmostEqual(aj["totales"]["altura_total"], 6.0)
        # plantas idénticas salvo el número de nivel
        self.assertEqual(aj["reparto"][0]["locales"],
                         aj["reparto"][1]["locales"])
        self.assertTrue(any("planta tipo repetida" in a.lower()
                            for a in aj["avisos"]))

    def test_plan_radial_niveles(self):
        aj = rd.plan_radial(dd.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "BEDROOM", "cantidad": 12},
            {"space_type": "BATHROOM", "cantidad": 6}], "Torre"),
            radio_ext=12.0, sectores=8, corredor_m=1.5,
            radio_nucleo=3.0, niveles=2)
        self.assertEqual(aj["niveles"], 2)
        self.assertEqual(len(aj["reparto"]), 2)
        self.assertEqual(aj["reparto"][0]["locales"],
                         aj["reparto"][1]["locales"])

    def test_niveles_fuera_de_rango_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                      n_alas=4, niveles=21)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")
        with self.assertRaises(DomainError) as cm:
            rd.plan_radial(_mixto(), radio_ext=12.0, sectores=8,
                           niveles=0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_aplicar_plan_y_2_niveles(self):
        aj = rd.plan_y(_mixto(), radio_nucleo=9.0, ancho_ala=12.0,
                       n_alas=4, corredor_m=1.6, niveles=2)
        ctx = self.application.create_project(
            self.project_path("v47y.arqgen"), name="v47y")
        res = dd.aplicar_plan(ctx, aj,
                              {"nombre_edificio":
                               "Estrella v47"})
        plan = aj["reparto"][0]
        esperados = len(plan["locales"]) + len(plan["pasillos"])
        self.assertGreaterEqual(len(res["espacios"]), esperados * 2)
        self.assertEqual(len(res["niveles"]), 2)


if __name__ == "__main__":
    unittest.main()
