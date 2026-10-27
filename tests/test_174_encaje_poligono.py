"""ENCAJE ESTRICTO AL POLÍGONO v3.40.0 (domain/encaje.py + el camino
estricto de domain/desde_dibujo.py).

Queja del usuario: «lo que genera se sale de este polígono y su forma
y no aprovecha todos los espacios». Causa: el empaquetado usaba la
caja envolvente y solo avisaba. Arreglo: la parcela se tesela en
contenedores reales (franjas de barrido para ortogonales; mayor
rectángulo inscrito para generales) y los locales se empaquetan DENTRO
con contención verificada local a local contra el polígono.
"""

from __future__ import annotations

import os
import tkinter as tk
import unittest

from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import encaje
from domain.desde_dibujo import rect_dentro
from tests.base import ARQGenTestCase

L = [(0, 0), (20, 0), (20, 6), (10, 6), (10, 10), (0, 10)]
U = [(0, 0), (20, 0), (20, 12), (14, 12), (14, 6), (6, 6),
     (6, 12), (0, 12)]
T = [(0, 0), (20, 0), (20, 6), (15, 6), (15, 14), (5, 14),
     (5, 6), (0, 6)]
ROMBO = [(5, 0), (10, 5), (5, 10), (0, 5)]
L_DESPLAZADA = [(1000, 2000), (1020, 2000), (1020, 2006),
                (1010, 2006), (1010, 2010), (1000, 2010)]


def _prog(area: float, cantidad: int, tipo: str = "OFFICE"):
    return dd.programa_edificacion(
        [{"space_type": tipo, "cantidad": cantidad,
          "area_m2": area}])


def _todos_dentro(analisis, poligono) -> bool:
    for plan in analisis["reparto"]:
        for r in plan["locales"]:
            if not rect_dentro([tuple(p) for p in r["rect"]],
                               poligono):
                return False
        for pieza in ([plan["pasillo"]] if plan.get("pasillo") else []) \
                + ([plan["escalera"]] if plan["escalera"] else []) \
                + ([plan["patio"]] if plan.get("patio") else []):
            if not rect_dentro([tuple(p) for p in pieza["rect"]],
                               poligono):
                return False
    return True


# ---------------------------------------------------------------------------
# 1) CONTENEDORES (domain/encaje.py)
# ---------------------------------------------------------------------------

class TestContenedores(unittest.TestCase):

    def test_L_se_tesela_exacta(self):
        c = encaje.contenedores_de(L)
        self.assertEqual(c["estrategia"], "descompuesto")
        self.assertEqual(len(c["contenedores"]), 2)
        self.assertAlmostEqual(c["area_aprovechable"], 160.0, places=2)
        # unión de contenedores == polígono (sin huecos ni solapes)
        self.assertAlmostEqual(sum(x["area"] for x in c["contenedores"]),
                               160.0, places=2)

    def test_U_tres_brazos(self):
        c = encaje.contenedores_de(U)
        self.assertEqual(len(c["contenedores"]), 3)
        self.assertAlmostEqual(c["area_aprovechable"], 192.0, places=2)

    def test_T_dos_piezas(self):
        c = encaje.contenedores_de(T)
        self.assertAlmostEqual(c["area_aprovechable"], 200.0, places=2)

    def test_rectangulo_con_margen(self):
        c = encaje.contenedores_de([(0, 0), (12, 0), (12, 8), (0, 8)],
                                   margen=0.5)
        self.assertEqual(c["estrategia"], "rectangulo")
        self.assertAlmostEqual(c["contenedores"][0]["area"], 77.0,
                               places=2)

    def test_rombo_usa_inscrito(self):
        c = encaje.contenedores_de(ROMBO)
        self.assertEqual(c["estrategia"], "inscrito")
        self.assertGreaterEqual(c["contenedores"][0]["area"], 24.5)
        self.assertTrue(any("inscrito" in a for a in c["avisos"]))

    def test_coordenadas_locales_respetadas(self):
        c = encaje.contenedores_de(L_DESPLAZADA)
        self.assertAlmostEqual(c["area_aprovechable"], 160.0, places=2)
        for x in c["contenedores"]:
            self.assertGreaterEqual(x["x0"], 1000.0)
            self.assertLessEqual(x["x1"], 1020.0)

    def test_franjas_diminutas_descartadas(self):
        # una parcela L con pata de 0.4 m: la pata no se admite como
        # contenedor (min_lado) y no revienta: se queda con la base
        c = encaje.contenedores_de(
            [(0, 0), (10, 0), (10, 4), (0.4, 4), (0.4, 9), (0, 9)],
            min_lado=1.0)
        self.assertTrue(c["contenedores"])
        self.assertLess(c["area_aprovechable"], 10.0 * 9.0)

    def test_comparten_banda_regla(self):
        a = {"x0": 0, "y0": 0, "x1": 10, "y1": 6}
        b = {"x0": 10, "y0": 0, "x1": 20, "y1": 10}
        self.assertTrue(encaje.comparten_banda(a, b, 1.0))
        lejos = {"x0": 10, "y0": 7, "x1": 20, "y1": 10}
        self.assertFalse(encaje.comparten_banda(a, lejos, 1.5))


# ---------------------------------------------------------------------------
# 2) AJUSTAR ESTRICTO: nada fuera y la forma se aprovecha
# ---------------------------------------------------------------------------

class TestAjustarEstricto(unittest.TestCase):

    def test_L_todo_dentro_y_ala_aprovechada(self):
        a = dd.ajustar(_prog(20.0, 6), L)
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(_todos_dentro(a, L))
        self.assertEqual(a["encaje"]["estrategia"], "descompuesto")
        usados_alas = [r for r in a["reparto"][0]["locales"]
                       if r.get("contenedor", 0) > 0]
        self.assertTrue(usados_alas, "el ala de la L debe tener locales")
        self.assertTrue(any("encaje estricto" in x
                            for x in a["avisos"]))

    def test_U_multinivel_todo_dentro(self):
        a = dd.ajustar(_prog(18.0, 8), U)
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(_todos_dentro(a, U))
        self.assertEqual(a["niveles"], 2)
        for plan in a["reparto"]:
            self.assertTrue(plan["dentro"])

    def test_poligono_desplazado_del_origen(self):
        # locales de 8 m2 (fondo 3.22): caben en banda con pasillo
        # (2.4 + 3.22 <= 6), así que el pasillo también queda dentro
        # de las coordenadas originales de la parcela
        a = dd.ajustar(_prog(8.0, 6), L_DESPLAZADA)
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(_todos_dentro(a, L_DESPLAZADA))
        self.assertIsNotNone(a["reparto"][0].get("pasillo"))
        xs = [p[0] for p in a["reparto"][0]["pasillo"]["rect"]]
        self.assertGreaterEqual(min(xs), 1000.0)

    def test_rombo_inscrito_con_aviso_honesto(self):
        a = dd.ajustar(_prog(16.0, 1), ROMBO)
        self.assertEqual(a["encaje"]["estrategia"], "inscrito")
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(_todos_dentro(a, ROMBO))
        self.assertTrue(any("inscrito" in x for x in a["avisos"]))

    def test_rombo_grande_error_honesto(self):
        # 4 x 16 m2 = 64 m2 en un rombo de 50 m2: honestamente no cabe
        # con la escalera multinivel
        with self.assertRaises(DomainError) as ctx:
            dd.ajustar(_prog(16.0, 4), ROMBO)
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "ARQ-DDI-003")

    def test_local_imposible_error_con_contenedor_mayor(self):
        # 120 m2 en una L cuyos contenedores son 20x6 y 10x4: ni en
        # uno solo ni en la unión de dos contiguos (10x10)
        with self.assertRaises(DomainError) as ctx:
            dd.ajustar(_prog(120.0, 1), L)
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         "ARQ-DDI-003")
        self.assertIn("contenedor", str(ctx.exception))

    def test_metricas_cumplimiento_100(self):
        a = dd.ajustar(_prog(20.0, 6), L)
        m = dd.metricas_de(a)
        self.assertEqual(m["locales_fuera"], 0)
        self.assertEqual(m["cumplimiento_pct"], 100.0)

    def test_aprovechamiento_en_totales(self):
        a = dd.ajustar(_prog(20.0, 6), L)
        pct = a["totales"]["aprovechamiento_pct"]
        self.assertGreater(pct, 50.0)
        self.assertLessEqual(pct, 100.0)
        esperado = round(a["totales"]["area_aprovechada"]
                         / (a["totales"]["area_contorno"]
                            * a["niveles"]) * 100.0, 2)
        self.assertAlmostEqual(pct, esperado, places=2)

    def test_decisiones_mencionan_el_contenedor(self):
        a = dd.ajustar(_prog(20.0, 6), L)
        textos = " ".join(d["texto"] for d in a["decisiones"])
        self.assertIn("contenedor", textos)

    def test_texto_ajuste_declara_encaje(self):
        a = dd.ajustar(_prog(20.0, 6), L)
        texto = dd.texto_ajuste(a)
        self.assertIn("Encaje:", texto)
        self.assertIn("contenedor", texto)
        self.assertIn("Aprovechamiento del polígono:", texto)

    def test_camino_historico_conserva_aviso(self):
        a = dd.ajustar(_prog(20.0, 6), L, encaje_estricto=False)
        self.assertFalse(a["dentro_del_contorno"])
        self.assertTrue(any("fuera del polígono" in x
                            for x in a["avisos"]))
        self.assertNotIn("encaje", a)

    def test_patio_experto_dentro_del_poligono(self):
        # con locales de 8 m2 las bandas funcionan y el patio se
        # reserva dentro del contenedor mayor
        a = dd.ajustar(_prog(8.0, 4), L, patio=True,
                       patio_ancho_m=2.0)
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(_todos_dentro(a, L))
        self.assertIsNotNone(a.get("patio"))
        self.assertGreater(a["patio"]["area_m2"], 0.0)

    def test_rectangulo_sigue_igual_que_antes(self):
        # el rectángulo alineado no cambia: contenedor = caja
        rect = [(0, 0), (30, 0), (30, 16), (0, 16)]
        a = dd.ajustar(_prog(20.0, 8), rect)
        self.assertEqual(a["encaje"]["estrategia"], "rectangulo")
        self.assertTrue(a["dentro_del_contorno"])
        self.assertEqual(a["reparto"][0]["area_disponible"], 480.0)


# ---------------------------------------------------------------------------
# 3) NIVEL SIN PASILLO (contenedores profundos)
# ---------------------------------------------------------------------------

class TestSinPasillo(unittest.TestCase):

    def test_U_profunda_usa_todo_con_pasillo_adaptado(self):
        # v3.42.0: los locales más profundos que el pasillo + fondo
        # ya NO renuncian al corredor: cambian fondo por ancho
        # conservando su área y CADA nivel lleva su pasillo; el área
        # de la U se aprovecha con el teselado completo
        a = dd.ajustar(_prog(18.0, 8), U)
        self.assertTrue(all(p.get("pasillo") for p in a["reparto"]),
                        "todos los niveles llevan pasillo adaptado")
        for plan in a["reparto"]:
            self.assertTrue(plan["locales"])
            self.assertGreater(plan["area_ocupada"], 0.0)
        self.assertTrue(_todos_dentro(a, U))
        self.assertGreaterEqual(
            float(a["totales"]["aprovechamiento_pct"]), 60.0)

    def test_sin_pasillo_mas_aprovechado_que_bands_vacias(self):
        # el contenedor mayor se llena también (>= 3 locales en el
        # nivel sin pasillo de la U)
        a = dd.ajustar(_prog(18.0, 8), U)
        mejor = max(a["reparto"], key=lambda p: len(p["locales"]))
        self.assertGreaterEqual(len(mejor["locales"]), 3)


# ---------------------------------------------------------------------------
# 4) CONTRATOS Y APLICACIÓN REAL
# ---------------------------------------------------------------------------

class TestContratos(unittest.TestCase):

    def test_plan_request_roundtrip_encaje(self):
        p = dd.PlanRequest(contorno=L, programa=_prog(20.0, 2).copy(),
                           encaje_estricto=False)
        datos = p.to_dict()
        self.assertIn("encaje_estricto", datos)
        q = dd.PlanRequest.from_dict(datos)
        self.assertFalse(q.encaje_estricto)
        r = dd.PlanRequest.from_dict({"contorno": [[0, 0], [1, 0],
                                                   [1, 1], [0, 1]],
                                      "programa": {}})
        self.assertTrue(r.encaje_estricto)  # por defecto

    def test_plan_de_aplica_encaje_estricto(self):
        p = dd.PlanRequest(contorno=L, programa=_prog(20.0, 6))
        res = dd.plan_de(p)
        self.assertTrue(res.analisis["dentro_del_contorno"])
        self.assertEqual(res.metricas["locales_fuera"], 0)


class TestAplicarReal(ARQGenTestCase):
    """Generación real: los espacios del proyecto quedan DENTRO."""

    def setUp(self):
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("encaje.arqgen"), name="Encaje")

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_generar_en_la_L_no_deja_nada_fuera(self):
        analisis = dd.ajustar(_prog(20.0, 6), L)
        res = dd.aplicar_plan(self.ctx, analisis,
                              {"reemplazar_previo": True})
        self.ctx.commit()
        self.assertGreater(len(res["espacios"]), 0)
        for espacio in self.ctx.architecture.list(
                "SPACE", self.ctx.project.id):
            pts = list(getattr(espacio, "boundary", []) or [])
            if len(pts) != 4:
                continue
            rect = [tuple(p[:2]) if isinstance(p, (tuple, list))
                    else p for p in pts]
            self.assertTrue(rect_dentro(rect, L),
                            f"{espacio.name} fuera del polígono")

    def test_generar_en_la_U_con_pasillo_adaptado(self):
        analisis = dd.ajustar(_prog(18.0, 8), U)
        res = dd.aplicar_plan(self.ctx, analisis,
                              {"reemplazar_previo": True})
        self.ctx.commit()
        self.assertGreater(len(res["espacios"]), 0)
        espacios = self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)
        usos = {s.space_type for s in espacios}
        # v3.42.0: la U profunda sale CON pasillo en todos los niveles
        self.assertIn("CORRIDOR", usos)


# ---------------------------------------------------------------------------
# 5) GANCHOS DE VENTANA (con display)
# ---------------------------------------------------------------------------

class TestGanchosEncaje(ARQGenTestCase):
    """El interruptor experto «Encajar estrictamente» vive, se pasa al
    ajuste y su estado viaja en la petición."""

    def setUp(self):
        super().setUp()
        self._prefs_old = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp,
                                                  "prefs.json")
        from ui.app_window import ARQGenWindow
        self.ctx = self.demo_context()
        self.window = ARQGenWindow(self.ctx, self.application)
        self.window.update()
        self.window.open_desde_dibujo_dialog()
        self.window.update()
        self.d = self.window._dd_dialog

    def tearDown(self):
        self.window.destroy()
        self.ctx.close()
        if self._prefs_old:
            os.environ["ARQGEN_PREFS"] = self._prefs_old
        else:
            os.environ.pop("ARQGEN_PREFS", None)
        super().tearDown()

    def _modo_edificacion(self):
        self.window._dd_modo.set("edificacion")
        self.window._dd_modo_cambio()
        self.window._dd_origen.set("rectangulo")
        self.window._dd_origen_cambio()
        self.window._dd_usos = [{"space_type": "OFFICE",
                                 "cantidad": 2, "area_m2": 20.0},
                                {"space_type": "BATHROOM",
                                 "cantidad": 1, "area_m2": 8.0}]
        self.window._dd_arbol_refresca()

    def test_interruptor_existe_y_activo(self):
        w = self.window
        self.assertIsInstance(getattr(w, "_dd_encaje", None),
                              tk.BooleanVar)
        self.assertTrue(w._dd_encaje.get())

    def test_ajustar_estricto_muestra_encaje(self):
        w = self.window
        self._modo_edificacion()
        w._dd_nivel.set("experto")
        w._dd_nivel_cambio()
        w._dd_ajustar()
        texto = w._dd_texto.get("1.0", "end")
        self.assertIn("Encaje:", texto)

    def test_peticion_lleva_el_interruptor(self):
        w = self.window
        self._modo_edificacion()
        w._dd_encaje.set(False)
        p = w._dd_peticion()
        self.assertFalse(p.encaje_estricto)
        w._dd_encaje.set(True)
        self.assertTrue(w._dd_peticion().encaje_estricto)


if __name__ == "__main__":
    unittest.main()
