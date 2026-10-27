"""TORRE EN Y REAL CON NÚCLEO CENTRAL v3.45.0 — domain/radial.py.

``plan_y`` genera la Y real de las imágenes de referencia (núcleo
circular con el vestíbulo, N alas radiantes a 120/90/180 grados,
corredor por ala y locales a ambos lados) con el contorno Y real
(arcos por cuerdas entre alas). El modelo de datos sigue siendo de
poligonales: aplicar_plan, métricas y DXF funcionan sin cambios.

Cobertura:
  * 3 alas (Y), 4 alas (X) y 2 alas (barra doble) dentro del
    contorno Y con aprovechamiento alto
  * núcleo circular con el vestíbulo (área ≈ πR²) y corredores por
    ala (pasillos múltiples con el campo "ala")
  * mínimos del DNA respetados y filas que cierran exactas
  * NO solape: cada pieza des-rotada cae en su franja de fila y
    ningún centroide cae dentro del polígono de otra pieza
  * determinismo; cabecera transversal con el uso mayor
  * errores: ARQ-DDI-011 (no cabe), ARQ-DDI-012 (núcleo sin
    vestíbulo, solape de alas por radio corto, n_alas fuera de
    rango, ala corta)
  * aplicar_plan crea UN edificio con los corredores de las alas y
    OMITE el mobiliario automático (geometría radiante)
  * métricas honestas: el fallback por centroide de v3.45 hace que
    las piezas SOLO-poligonal cuenten como dentro (radial y Y)
"""

from __future__ import annotations

import math
import unittest

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import radial as rd
from tests.base import ARQGenTestCase


def _hospital() -> dict:
    return dd.programa_edificacion([
        {"space_type": "VESTIBULE", "cantidad": 1},
        {"space_type": "WARD", "cantidad": 9},
        {"space_type": "NURSE_STATION", "cantidad": 3},
        {"space_type": "BATHROOM", "cantidad": 6},
    ], "Hospital en Y")


def _residencia() -> dict:
    return dd.programa_edificacion([
        {"space_type": "VESTIBULE", "cantidad": 1},
        {"space_type": "BEDROOM", "cantidad": 18},
        {"space_type": "BATHROOM", "cantidad": 9},
        {"space_type": "LIVING_ROOM", "cantidad": 3},
    ], "Residencia en Y")


def _punto_dentro(p: tuple, poly: list) -> bool:
    """Ray-casting local del test (copia del patrón del motor)."""
    x, y = p
    dentro = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            cruz = (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            if x < cruz:
                dentro = not dentro
        j = i
    return dentro


class TestPlanY(unittest.TestCase):

    def test_y_hospital_3_alas_completa(self):
        aj = rd.plan_y(_hospital(), radio_nucleo=7.5,
                       largo_ala=16.0, ancho_ala=11.0, n_alas=3,
                       corredor_m=1.6)
        self.assertEqual(aj["tipo"], "y_radial")
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertGreater(
            aj["totales"]["aprovechamiento_pct"], 70.0)
        plan = aj["reparto"][0]
        self.assertEqual(len(plan.get("pasillos") or []), 3)
        self.assertTrue(all(p["space_type"] == "CORRIDOR"
                            and p.get("ala") == i
                            for i, p in enumerate(plan["pasillos"])))
        nucleo = next(r for r in plan["locales"]
                      if r["space_type"] == "VESTIBULE")
        esperado = math.pi * 7.5 * 7.5
        self.assertAlmostEqual(float(nucleo["area_m2"]), esperado,
                               delta=esperado * 0.02)
        # el contorno es la Y REAL: arcos por cuerdas entre alas
        self.assertGreater(len(aj["forma"]["vertices"]), 30)
        self.assertEqual(aj["forma"]["forma"], "y_radial")

    def test_minimos_dna_respetados(self):
        aj = rd.plan_y(_hospital(), radio_nucleo=7.5,
                       largo_ala=16.0, ancho_ala=11.0, n_alas=3,
                       corredor_m=1.6)
        for r in aj["reparto"][0]["locales"]:
            if float(r.get("area_min") or 0.0) > 0.0:
                self.assertGreaterEqual(
                    float(r["area_m2"]),
                    float(r["area_min"]) - 0.01, r["nombre"])

    def test_piezas_en_su_franja_sin_solape(self):
        aj = rd.plan_y(_hospital(), radio_nucleo=7.5,
                       largo_ala=18.0, ancho_ala=11.0, n_alas=3,
                       corredor_m=1.6, cabecera_m=4.0)
        plan = aj["reparto"][0]
        yparam = aj["y_radial"]
        R, L, a, cor, cab = (yparam["radio_nucleo"],
                             yparam["largo_ala"],
                             yparam["ancho_ala"],
                             yparam["corredor_m"],
                             yparam["cabecera_m"])
        ang_entre = 2.0 * math.pi / yparam["n_alas"]
        piezas = (list(plan.get("pasillos") or []) + plan["locales"])
        centros = []
        for pieza in piezas:
            ala = int(pieza.get("ala", -1))
            if ala < 0:
                continue
            theta = math.pi / 2.0 + ala * ang_entre
            ct, st = math.cos(theta), math.sin(theta)
            for px, py in pieza["poligono"]:
                dx, dy = px, py
                u = dx * ct + dy * st
                v = -dx * st + dy * ct
                self.assertGreaterEqual(u, R - 1e-3, pieza["nombre"])
                self.assertLessEqual(u, R + L + 1e-3,
                                     pieza["nombre"])
                self.assertLessEqual(abs(v), a / 2.0 + 1e-3,
                                     pieza["nombre"])
                if pieza["codigo"] != "PASILLO" \
                        and "Cabecera" not in pieza["nombre"]:
                    self.assertGreaterEqual(abs(v), cor / 2.0 - 1e-3,
                                            pieza["nombre"])
            centro = (sum(q[0] for q in pieza["poligono"])
                      / len(pieza["poligono"]),
                      sum(q[1] for q in pieza["poligono"])
                      / len(pieza["poligono"]))
            centros.append((pieza["nombre"], centro,
                            pieza["poligono"]))
        # ningún centroide cae dentro del polígono de otra pieza
        for nombre_a, c_a, _ in centros:
            for nombre_b, _, poly_b in centros:
                if nombre_a == nombre_b:
                    continue
                self.assertFalse(
                    _punto_dentro(c_a, poly_b),
                    f"el centro de {nombre_a} cae dentro de "
                    f"{nombre_b}")

    def test_determinista(self):
        a = rd.plan_y(_hospital(), radio_nucleo=7.5, n_alas=3)
        b = rd.plan_y(_hospital(), radio_nucleo=7.5, n_alas=3)
        self.assertEqual([r["poligono"] for r in
                          a["reparto"][0]["locales"]],
                         [r["poligono"] for r in
                          b["reparto"][0]["locales"]])
        self.assertEqual(a["forma"]["vertices"],
                         b["forma"]["vertices"])

    def test_cabecera_transversal_con_el_uso_mayor(self):
        aj = rd.plan_y(_residencia(), radio_nucleo=7.0,
                       largo_ala=18.0, ancho_ala=12.0, n_alas=3,
                       corredor_m=1.5, cabecera_m=4.0)
        plan = aj["reparto"][0]
        cabeceras = [r for r in plan["locales"]
                     if r["nombre"].startswith("Cabecera ala")]
        self.assertEqual(len(cabeceras), 3)
        esperado = 4.0 * (12.0 - 0.002)
        for cab in cabeceras:
            self.assertAlmostEqual(float(cab["area_m2"]), esperado,
                                   delta=0.05)
            self.assertEqual(cab["space_type"], "LIVING_ROOM")
        self.assertTrue(any("cabecera" in av.lower()
                            for av in aj["avisos"]))

    def test_torre_x_4_alas(self):
        aj = rd.plan_y(_residencia(), radio_nucleo=9.0,
                       largo_ala=14.0, ancho_ala=11.0, n_alas=4,
                       corredor_m=1.5)
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertEqual(len(aj["reparto"][0]["pasillos"]), 4)

    def test_barra_doble_2_alas(self):
        aj = rd.plan_y(_residencia(), radio_nucleo=6.5,
                       largo_ala=20.0, ancho_ala=11.5, n_alas=2,
                       corredor_m=1.5)
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertEqual(len(aj["reparto"][0]["pasillos"]), 2)

    def test_desbordamiento_lanza_011(self):
        grande = dd.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "WARD", "cantidad": 40}], "Grande")
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(grande, radio_nucleo=7.5, largo_ala=16.0,
                      ancho_ala=11.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-011")

    def test_nucleo_sin_vestibulo_lanza_012(self):
        solo = dd.programa_edificacion(
            [{"space_type": "BEDROOM", "cantidad": 4}], "Solo")
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(solo, radio_nucleo=7.5)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_alas_solapadas_por_radio_corto_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(_hospital(), radio_nucleo=5.0, ancho_ala=11.0,
                      n_alas=3)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")
        self.assertIn("solapa", cm.exception.message)

    def test_n_alas_fuera_de_rango_lanza_012(self):
        for malas in (1, 9):
            with self.assertRaises(DomainError) as cm:
                rd.plan_y(_hospital(), radio_nucleo=7.5,
                          n_alas=malas)
            self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_ala_corta_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_y(_hospital(), radio_nucleo=7.5, largo_ala=2.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")


class TestAplicarYMetricas(ARQGenTestCase):

    def test_aplicar_plan_y_sin_mobiliario(self):
        # residencia (programa de vivienda): el mobiliario automático
        # se detecta y se OMITE por la geometría radiante con aviso
        aj = rd.plan_y(_residencia(), radio_nucleo=7.5,
                       largo_ala=18.0, ancho_ala=11.0, n_alas=3,
                       corredor_m=1.6, cabecera_m=4.0)
        plan = aj["reparto"][0]
        esperados = len(plan["locales"]) + len(plan["pasillos"])
        ctx = self.application.create_project(
            self.project_path("v45y.arqgen"), name="v45y")
        res = dd.aplicar_plan(ctx, aj,
                              {"nombre_edificio":
                               "Torre en Y real"})
        self.assertGreaterEqual(len(res["espacios"]), esperados)
        self.assertFalse(res["mobiliario"]["activado"])
        self.assertTrue(any("radial" in a.lower()
                            for a in res["avisos"]))
        # cada local (y cabecera y núcleo) quedó adyacente a un
        # corredor: tantas relaciones como locales
        self.assertGreaterEqual(int(res.get("relaciones", 0)),
                                len(plan["locales"]))

    def test_metricas_honestas_con_piezas_solo_poligonal(self):
        aj = rd.plan_y(_hospital(), radio_nucleo=7.5, n_alas=3)
        m = dd.metricas_de(aj)
        self.assertAlmostEqual(m["cumplimiento_pct"], 100.0,
                               places=6)
        aj_r = rd.plan_radial(dd.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "BEDROOM", "cantidad": 12},
            {"space_type": "BATHROOM", "cantidad": 6}], "Torre"),
            radio_ext=14.0, radio_nucleo=3.0, sectores=8,
            corredor_m=1.6)
        m_r = dd.metricas_de(aj_r)
        self.assertAlmostEqual(m_r["cumplimiento_pct"], 100.0,
                               places=6)

    def test_textos_cp1252_y_forma_radial(self):
        aj = rd.plan_y(_hospital(), radio_nucleo=7.5, n_alas=3)
        texto = dd.texto_ajuste(aj)
        texto.encode("cp1252")
        infer = dd.texto_inferencia(aj["forma"])
        self.assertIn("torre en y", infer.lower())
        # la forma del plan_radial (v3.44, sin claves de caja) ya no
        # rompe texto_inferencia
        forma_r = {"forma": "circulo", "area_m2": 100.0,
                   "vertices": [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0)]}
        dd.texto_inferencia(forma_r)


class TestContratos(unittest.TestCase):

    def test_version_3450(self):
        self.assertEqual(APP_VERSION, "3.47.0")


if __name__ == "__main__":
    unittest.main()
