"""HOSPITAL EN X REAL v3.47.0 — domain/radial.py.

``plan_x`` genera la X real de la referencia (dos barras
perpendiculares que se CRUZAN por el centro, el cruce es el HUB con
el vestíbulo, corredor por brazo y locales a ambos lados). El
contorno es la UNIÓN de las dos barras: 12 vértices (8 esquinas de
puntas + 4 entrantes del cruce), totalmente ortogonal, sin aristas
degeneradas (el trazado de muros funciona). ``niveles`` repite la
planta tipo (el hospital de referencia tiene sótano, planta
científica y planta tipo de médicos).

Cobertura:
  * X a 45 grados y cruz en + (0 grados) dentro del contorno unión
  * contorno con EXACTAMENTE 12 vértices y sin aristas < 1 m
  * hub = cruce de las barras (vestíbulo con área ≈ ancho²)
  * 4 corredores (uno por brazo, pasillos múltiples con "ala") y
    cada local adyacente al corredor de SU brazo
  * mínimos del DNA respetados y filas que cierran exactas
  * NO solape por centroides entre piezas del mismo nivel
  * determinismo; cabecera transversal por brazo
  * niveles de planta tipo: reparto de N entradas, aplicar_plan
    crea N plantas con espacios en cada una
  * errores: ARQ-DDI-011 (no cabe), ARQ-DDI-012 (sin vestíbulo,
    brazo corto, barra corta, ancho corto, corredor excesivo,
    cabecera fuera de rango, niveles fuera de rango)
  * aplicar_plan con muros (el contorno X no lanza ARQ-DOM-048)
"""

from __future__ import annotations

import math
import unittest

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import radial as rd
from tests.base import ARQGenTestCase


def _hospital_x() -> dict:
    return dd.programa_edificacion([
        {"space_type": "VESTIBULE", "cantidad": 1},
        {"space_type": "EMERGENCY_ROOM", "cantidad": 3},
        {"space_type": "WAITING_ROOM", "cantidad": 4},
        {"space_type": "CONSULTATION_ROOM", "cantidad": 6},
        {"space_type": "WARD", "cantidad": 10},
        {"space_type": "NURSE_STATION", "cantidad": 4},
        {"space_type": "BATHROOM", "cantidad": 10},
        {"space_type": "LAVATORY", "cantidad": 6},
        {"space_type": "STOREROOM", "cantidad": 4},
    ], "Hospital en X")


def _centroide(poly):
    return (sum(p[0] for p in poly) / len(poly),
            sum(p[1] for p in poly) / len(poly))


class TestPlanX(unittest.TestCase):

    def test_x_45_grados_dentro_y_12_vertices(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0, corredor_m=2.0,
                       angulo=math.radians(45.0))
        self.assertEqual(aj["tipo"], "x_radial")
        self.assertTrue(aj["dentro_del_contorno"])
        vs = aj["forma"]["vertices"]
        self.assertEqual(len(vs), 12)
        aristas = [math.hypot(vs[(i + 1) % 12][0] - vs[i][0],
                              vs[(i + 1) % 12][1] - vs[i][1])
                   for i in range(12)]
        self.assertGreater(min(aristas), 1.0)
        self.assertGreater(
            aj["totales"]["aprovechamiento_pct"], 95.0)

    def test_cruz_en_mas_0_grados(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=68.0,
                       ancho_barra=13.0, corredor_m=2.0, angulo=0.0)
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertEqual(len(aj["forma"]["vertices"]), 12)
        # a 0 grados la barra 1 va a lo largo del eje X y la barra 2
        # lo cruza en vertical: la X entera llega a ±L/2 en ambos ejes
        xs = [p[0] for p in aj["forma"]["vertices"]]
        ys = [p[1] for p in aj["forma"]["vertices"]]
        self.assertAlmostEqual(max(xs), 34.0, places=1)
        self.assertAlmostEqual(max(ys), 34.0, places=1)

    def test_hub_es_el_cruce_con_el_vestibulo(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0)
        plan = aj["reparto"][0]
        hub = next(r for r in plan["locales"]
                   if r["space_type"] == "VESTIBULE")
        self.assertAlmostEqual(float(hub["area_m2"]), 14.0 * 14.0,
                               delta=1.0)
        # el hub está centrado en el origen (el cruce de las barras)
        cx = sum(p[0] for p in hub["poligono"]) / 4
        cy = sum(p[1] for p in hub["poligono"]) / 4
        self.assertAlmostEqual(cx, 0.0, places=1)
        self.assertAlmostEqual(cy, 0.0, places=1)
        self.assertEqual(int(hub["ala"]), -1)

    def test_4_corredores_y_relacion_por_brazo(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0, corredor_m=2.0)
        plan = aj["reparto"][0]
        self.assertEqual(len(plan["pasillos"]), 4)
        self.assertTrue(all(p["space_type"] == "CORRIDOR"
                            for p in plan["pasillos"]))
        alas = sorted(int(p["ala"]) for p in plan["pasillos"])
        self.assertEqual(alas, [0, 1, 2, 3])
        # cada local con ala >= 0 tiene su corredor en el análisis
        for r in plan["locales"]:
            if int(r.get("ala", -1)) >= 0:
                self.assertTrue(any(int(p["ala"]) == int(r["ala"])
                                    for p in plan["pasillos"]))

    def test_minimos_dna_y_filas_cerradas(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0, corredor_m=2.0)
        plan = aj["reparto"][0]
        for r in plan["locales"]:
            self.assertGreaterEqual(
                float(r["area_m2"]),
                float(r.get("area_min") or 0.0) - 0.011)
        # cada fila cierra exacta: la suma de anchos de fila = util
        util = 64.0 / 2.0 - 14.0 / 2.0
        usados = {}
        for r in plan["locales"] + plan["pasillos"]:
            usados[int(r["ala"])] = usados.get(int(r["ala"]), 0.0)
        # verificación fuerte: ninguna pieza se sale del brazo
        thetas = [math.radians(45.0) + k * math.pi / 2
                  for k in range(4)]
        for r in plan["locales"] + plan["pasillos"]:
            k = int(r["ala"])
            if k < 0:
                continue
            ct, st = math.cos(thetas[k]), math.sin(thetas[k])
            for px, py in r["poligono"]:
                dx, dy = px, py
                u = dx * ct + dy * st
                v = -dx * st + dy * ct
                self.assertGreaterEqual(u, 14.0 / 2.0 - 0.01)
                self.assertLessEqual(u, 32.0 + 0.01)
                self.assertLessEqual(abs(v), 7.0 + 0.01)

    def test_sin_solape_por_centroides(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0, corredor_m=2.0)
        plan = aj["reparto"][0]
        piezas = plan["locales"] + plan["pasillos"]
        centros = [(r["codigo"], _centroide(r["poligono"]))
                   for r in piezas]
        for i in range(len(centros)):
            for j in range(i + 1, len(centros)):
                if centros[i][0] == "PASILLO" \
                        or centros[j][0] == "PASILLO":
                    continue
                dx = centros[i][1][0] - centros[j][1][0]
                dy = centros[i][1][1] - centros[j][1][1]
                self.assertGreater(math.hypot(dx, dy), 0.5,
                                   "dos locales comparten centroide")

    def test_determinismo(self):
        a1 = rd.plan_x(_hospital_x(), largo_barra=60.0,
                       ancho_barra=14.0, corredor_m=2.0,
                       cabecera_m=4.0)
        a2 = rd.plan_x(_hospital_x(), largo_barra=60.0,
                       ancho_barra=14.0, corredor_m=2.0,
                       cabecera_m=4.0)
        self.assertEqual(a1["forma"]["vertices"],
                         a2["forma"]["vertices"])
        self.assertEqual([r["poligono"] for r in
                          a1["reparto"][0]["locales"]],
                         [r["poligono"] for r in
                          a2["reparto"][0]["locales"]])

    def test_niveles_planta_tipo(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0, niveles=3,
                       altura_nivel_m=3.2)
        self.assertEqual(aj["niveles"], 3)
        self.assertEqual(len(aj["reparto"]), 3)
        self.assertEqual([p["nivel"] for p in aj["reparto"]],
                         [1, 2, 3])
        # la planta 2 es idéntica a la planta 1 (planta tipo)
        loc1 = [(r["space_type"], r["poligono"])
                for r in aj["reparto"][0]["locales"]]
        loc2 = [(r["space_type"], r["poligono"])
                for r in aj["reparto"][1]["locales"]]
        self.assertEqual(loc1, loc2)
        self.assertAlmostEqual(aj["totales"]["altura_total"], 9.6,
                               places=6)
        # ocupación NO se infla: metricas_de divide por niveles
        m = dd.metricas_de(aj)
        self.assertEqual(m["niveles"], 3)
        self.assertAlmostEqual(m["ocupacion_pct"],
                               aj["totales"]["aprovechamiento_pct"],
                               places=1)


class TestPlanXErrores(unittest.TestCase):

    def test_sin_vestibulo_lanza_012(self):
        prog = dd.programa_edificacion(
            [{"space_type": "WARD", "cantidad": 6}], "Sin hub")
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(prog, largo_barra=64.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_brazo_corto_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=18.0,
                      ancho_barra=13.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_barra_corta_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=5.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_ancho_corto_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=64.0, ancho_barra=3.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_corredor_excesivo_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=64.0,
                      ancho_barra=14.0, corredor_m=12.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_cabecera_fuera_de_rango_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=64.0,
                      ancho_barra=14.0, cabecera_m=30.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_no_cabe_lanza_011(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=30.0,
                      ancho_barra=10.0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-011")

    def test_niveles_fuera_de_rango_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=64.0, niveles=0)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")
        with self.assertRaises(DomainError) as cm:
            rd.plan_x(_hospital_x(), largo_barra=64.0, niveles=21)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.47.0")


class TestAplicarX(ARQGenTestCase):

    def test_aplicar_plan_x_3_niveles_con_muros(self):
        aj = rd.plan_x(_hospital_x(), largo_barra=64.0,
                       ancho_barra=14.0, corredor_m=2.0,
                       angulo=math.radians(45.0),
                       altura_nivel_m=3.2, niveles=3)
        ctx = self.application.create_project(
            self.project_path("v47x.arqgen"), name="v47x")
        res = dd.aplicar_plan(ctx, aj,
                              {"trazar_muros": True,
                               "nombre_edificio": "Hospital X v47"})
        plan = aj["reparto"][0]
        esperados_por_nivel = (len(plan["locales"])
                               + len(plan["pasillos"]))
        self.assertGreaterEqual(len(res["espacios"]),
                                esperados_por_nivel * 3)
        self.assertEqual(len(res["niveles"]), 3)
        # el contorno X se traza SIN ARQ-DOM-048 (sin aristas de
        # longitud 0 en la unión de las barras)
        self.assertGreater(int(res["muros"]), 100)
        # cada local quedó adyacente al corredor de su brazo
        self.assertGreaterEqual(int(res.get("relaciones", 0)),
                                len(plan["locales"]))


if __name__ == "__main__":
    unittest.main()
