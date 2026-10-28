"""PROGRAMA ADAPTABLE v3.41.0 + PASILLOS Y FILTROS v3.42.0
(domain/desde_dibujo.py + diálogo).

Petición del usuario: además de encajar en el polígono, el asistente
debe AJUSTAR LAS DIMENSIONES DE LOS LOCALES del programa social
elegido hasta entrar en él, con niveles mínimo (ajuste leve) / medio
/ estricto (el más agresivo), y debe permitir ELEGIR qué locales de
cada temática y uso social se aplican — la realidad del arquitecto en
Cuba: locales y edificaciones ya construidas a las que hay que hacer
un cambio de uso, donde casi nunca se puede demoler a gran escala y
a veces hay que trabajar por debajo de la norma (documentándolo).
"""

from __future__ import annotations

import os
import unittest

from core.errors import DomainError
from core import APP_VERSION
from domain import desde_dibujo as dd
from domain import servicios_engine as eng
from domain.desde_dibujo import rect_dentro
from tests.base import ARQGenTestCase

RECT5 = [(0, 0), (5, 0), (5, 5), (0, 5)]          # 25 m2, 1 contenedor
RECT9X8 = [(0, 0), (9, 0), (9, 8), (0, 8)]        # FARMACIA íntegra cabe
L = [(0, 0), (20, 0), (20, 6), (10, 6), (10, 10), (0, 10)]


def _prog_uno(ideal: float, norma: float) -> dict:
    a, f = dd._dimensiones(ideal)
    return {"servicio": "", "nombre": "P", "descripcion": "",
            "parametros": {},
            "renglones": [{"codigo": "X", "nombre": "Local X",
                           "space_type": "ROOM", "area_m2": float(ideal),
                           "ancho_m": a, "fondo_m": f, "flujo": "libre",
                           "critico": False, "req": [], "adjacencias": [],
                           "area_min": float(norma),
                           "descripcion": "", "copia": 1}],
            "totales": {"locales": 1, "area_m2": float(ideal)},
            "flujos": [], "notas": [], "avisos": [], "validacion": []}


def _prog_tres() -> dict:
    return {"servicio": "", "nombre": "S", "descripcion": "",
            "parametros": {},
            "renglones": [{"codigo": c, "nombre": "Local " + c,
                           "space_type": "ROOM", "area_m2": 18.0,
                           "ancho_m": 4.0, "fondo_m": 4.5,
                           "flujo": "libre", "critico": False,
                           "req": [], "adjacencias": [],
                           "area_min": 12.0, "descripcion": "",
                           "copia": 1}
                          for c in ("A", "B", "C")],
            "totales": {"locales": 3, "area_m2": 54.0},
            "flujos": [], "notas": [], "avisos": [], "validacion": []}


def _codigo_error(fn) -> str:
    try:
        fn()
    except DomainError as exc:
        return str(getattr(exc, "code", ""))
    return ""


# ---------------------------------------------------------------------------
# 1) SELECCIÓN DE LOCALES (programa_filtrado)
# ---------------------------------------------------------------------------

class TestProgramaFiltrado(unittest.TestCase):

    def test_none_devuelve_el_programa_completo(self):
        p = _prog_tres()
        q = dd.programa_filtrado(p, None)
        self.assertIs(q, p)

    def test_conserva_solo_elegidos(self):
        q = dd.programa_filtrado(_prog_tres(), ["A", "C"])
        self.assertEqual([r["codigo"] for r in q["renglones"]],
                         ["A", "C"])
        self.assertEqual(q["totales"]["locales"], 2)
        self.assertAlmostEqual(q["totales"]["area_m2"], 36.0, places=2)

    def test_exclusion_documentada_en_avisos(self):
        q = dd.programa_filtrado(_prog_tres(), ["A", "C"])
        self.assertTrue(any("se excluyen 1 local(es)" in a
                            and "Local B" in a for a in q["avisos"]))
        self.assertEqual(q["seleccion"], ["A", "C"])

    def test_seleccion_vacia_es_error_amable(self):
        self.assertEqual(
            _codigo_error(lambda: dd.programa_filtrado(
                _prog_tres(), [])),
            "ARQ-DDI-009")
        self.assertEqual(
            _codigo_error(lambda: dd.programa_filtrado(
                _prog_tres(), ["NOEXISTE"])),
            "ARQ-DDI-009")

    def test_grupos_recalculados_en_servicio(self):
        p = eng.programa_servicio("FARMACIA")
        codigos = sorted({r["codigo"] for r in p["renglones"]})
        q = dd.programa_filtrado(p, codigos[:2])
        self.assertEqual(len(q["renglones"]), 2)
        self.assertIn("grupos", q["totales"])
        self.assertEqual(sum(g["locales"]
                             for g in q["totales"]["grupos"].values()), 2)

    def test_ajustar_respecta_la_seleccion(self):
        a = dd.ajustar(_prog_tres(), L, seleccion=["A", "C"])
        self.assertEqual(
            sorted({r["codigo"]
                    for r in a["programa"]["renglones"]}),
            ["A", "C"])
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(any("selección de locales" in x
                            for x in a["avisos"]))


# ---------------------------------------------------------------------------
# 2) LA NORMA VIAJA EN LOS RENGLONES
# ---------------------------------------------------------------------------

class TestAreaMinEnRenglones(unittest.TestCase):

    def test_servicio_del_catalogo_lleva_area_min(self):
        p = eng.programa_servicio("FARMACIA")
        normas = {r["codigo"]: r["area_min"] for r in p["renglones"]}
        self.assertEqual(normas["DISPENSACION"], 12.0)
        self.assertEqual(normas["CAMARA_FRIA"], 4.0)
        self.assertTrue(all(n > 0 for n in normas.values()))

    def test_uso_del_dna_lleva_su_minimo(self):
        p = dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 2, "area_m2": 20.0}])
        self.assertTrue(all(r["area_min"] > 0 for r in p["renglones"]))
        p2 = dd.programa_edificacion(
            [{"space_type": "USO_INVENTADO_XYZ", "cantidad": 1,
              "area_m2": 12.0}])
        self.assertEqual(p2["renglones"][0]["area_min"], 0.0)


# ---------------------------------------------------------------------------
# 3) PISOS, DIMENSIONADO Y ESCALA
# ---------------------------------------------------------------------------

class TestPisosYEscala(unittest.TestCase):

    def test_piso_por_nivel(self):
        cfg_min = dd.AJUSTE_CONFIG["minimo"]
        cfg_med = dd.AJUSTE_CONFIG["medio"]
        cfg_est = dd.AJUSTE_CONFIG["estricto"]
        r = {"area_m2": 30.0, "area_min": 28.0}
        self.assertAlmostEqual(dd._piso_de(r, cfg_min), 28.0, places=6)
        self.assertAlmostEqual(dd._piso_de(r, cfg_med), 23.8, places=6)
        self.assertAlmostEqual(dd._piso_de(r, cfg_est), 18.2, places=6)
        # sin norma: rebaja proporcional sobre el ideal
        r2 = {"area_m2": 30.0, "area_min": 0.0}
        self.assertAlmostEqual(dd._piso_de(r2, cfg_min), 30.0, places=6)
        self.assertAlmostEqual(dd._piso_de(r2, cfg_med), 25.5, places=6)
        # el piso nunca crece el local
        r3 = {"area_m2": 3.0, "area_min": 9.0}
        self.assertAlmostEqual(dd._piso_de(r3, cfg_min), 3.0, places=6)

    def test_dimensiones_ajuste_pisos_de_lado(self):
        a, f = dd._dimensiones_ajuste(4.0, 2.0)
        self.assertGreaterEqual(min(a, f), 2.0)
        self.assertAlmostEqual(a * f, 4.0, delta=0.6)
        a2, f2 = dd._dimensiones_ajuste(4.0, 1.5)
        self.assertGreaterEqual(min(a2, f2), 1.5)

    def test_escala_registra_reducciones(self):
        p = _prog_tres()
        escalado, registro = dd._escala_programa(
            p, 0.5, dd.AJUSTE_CONFIG["medio"])
        self.assertEqual(len(registro), 3)
        for r, item in zip(escalado["renglones"], registro):
            # piso medio de la norma 12 = max(12*0.85, 4) = 10.2
            self.assertAlmostEqual(r["area_m2"], 10.2, places=2)
            self.assertEqual(item["area_ideal"], 18.0)
            self.assertAlmostEqual(item["area_final"], 10.2, places=2)
            # 10.2 < norma 12: SÍ rebasa, y queda documentado
            self.assertTrue(item["bajo_norma"])
        self.assertAlmostEqual(escalado["totales"]["area_m2"], 30.6,
                               places=2)

    def test_escala_no_toca_las_naves(self):
        p = dd.programa_edificacion(
            [{"space_type": "ROOM", "cantidad": 1, "area_m2": 120.0}])
        r = p["renglones"][0]
        self.assertTrue(dd._es_hall(r))
        escalado, registro = dd._escala_programa(
            p, 0.5, dd.AJUSTE_CONFIG["estricto"])
        self.assertEqual(registro, [])
        self.assertAlmostEqual(escalado["renglones"][0]["area_m2"],
                               120.0, places=2)


# ---------------------------------------------------------------------------
# 4) LA ESCALERA DE REDUCCIÓN EN ajustar()
# ---------------------------------------------------------------------------

class TestEscaleraEnAjustar(unittest.TestCase):

    def test_nivel_desconocido(self):
        self.assertEqual(
            _codigo_error(lambda: dd.ajustar(
                _prog_uno(30.0, 28.0), RECT5, ajuste="brutal")),
            "ARQ-DDI-009")

    def test_seleccion_vacia_en_ajustar(self):
        self.assertEqual(
            _codigo_error(lambda: dd.ajustar(
                _prog_uno(30.0, 28.0), RECT5, seleccion=[])),
            "ARQ-DDI-009")

    def test_ideal_no_cabe_tal_cual(self):
        self.assertEqual(
            _codigo_error(lambda: dd.ajustar(
                _prog_uno(30.0, 28.0), RECT5, ajuste="ideal")),
            "ARQ-DDI-003")

    def test_minimo_no_viola_la_norma(self):
        # norma 28: su piso (4.64 x 6.03) no cabe en 5x5 -> agotado
        self.assertEqual(
            _codigo_error(lambda: dd.ajustar(
                _prog_uno(30.0, 28.0), RECT5, ajuste="minimo")),
            "ARQ-DDI-010")

    def test_medio_agotado_con_norma_alta(self):
        # piso medio 23.8 -> 4.28 x 5.56: fondo > 5 -> no cabe
        self.assertEqual(
            _codigo_error(lambda: dd.ajustar(
                _prog_uno(30.0, 28.0), RECT5, ajuste="medio")),
            "ARQ-DDI-010")

    def test_estricto_entra_y_documenta_la_rebaja(self):
        a = dd.ajustar(_prog_uno(30.0, 28.0), RECT5, ajuste="estricto")
        self.assertTrue(a["dentro_del_contorno"])
        aj = a["ajuste_programa"]
        self.assertEqual(aj["nivel"], "estricto")
        self.assertEqual(len(aj["reducidos"]), 1)
        item = aj["reducidos"][0]
        self.assertAlmostEqual(item["area_ideal"], 30.0, places=2)
        self.assertAlmostEqual(item["area_final"], 18.2, places=2)
        self.assertTrue(item["bajo_norma"])
        self.assertEqual(aj["bajo_norma"], ["Local X"])
        for plan in a["reparto"]:
            for r in plan["locales"]:
                self.assertTrue(rect_dentro([tuple(p) for p in r["rect"]],
                                            RECT5))

    def test_minimo_reduce_solo_hasta_la_norma(self):
        a = dd.ajustar(_prog_uno(30.0, 18.0), RECT5, ajuste="minimo")
        aj = a["ajuste_programa"]
        self.assertEqual(aj["nivel"], "minimo")
        item = aj["reducidos"][0]
        self.assertAlmostEqual(item["area_final"], 18.0, places=2)
        self.assertFalse(item["bajo_norma"])

    def test_programa_que_cabe_no_se_reducido(self):
        a = dd.ajustar(_prog_uno(16.0, 12.0), RECT5, ajuste="estricto")
        self.assertNotIn("ajuste_programa", a)
        # v3.42.0: sin reducción que documentar; el teselado completo
        # puede CRECER el local para aprovechar el contorno (jamás
        # dejarlo por debajo del área pedida)
        self.assertGreaterEqual(
            a["programa"]["renglones"][0]["area_m2"], 16.0)
        for r in a["programa"]["renglones"]:
            if r.get("crecido_m2"):
                self.assertGreaterEqual(r["area_m2"], r["area_ideal"])

    def test_seleccion_y_ajuste_combinados(self):
        # el local B no se aplica; los restantes entran (reducidos a
        # su norma o tal cual, según quepa) y nada se sale
        RECT7 = [(0, 0), (7, 0), (7, 7), (0, 7)]
        a = dd.ajustar(_prog_tres(), RECT7, seleccion=["A", "C"],
                       ajuste="minimo")
        self.assertEqual(
            sorted(r["codigo"] for r in a["programa"]["renglones"]),
            ["A", "C"])
        self.assertLessEqual(a["programa"]["totales"]["area_m2"], 36.0)
        self.assertTrue(a["dentro_del_contorno"])

    def test_informe_muestra_ajuste_dimensional(self):
        a = dd.ajustar(_prog_uno(30.0, 28.0), RECT5, ajuste="estricto")
        texto = dd.texto_ajuste(a)
        self.assertIn("AJUSTE DIMENSIONAL (ESTRICTO)", texto)
        self.assertIn("30.00 -> 18.20 m2", texto)
        self.assertIn("BAJO LA NORMATIVA", texto)
        self.assertIn("decisión del proyectista", texto)

    def test_servicio_real_farmacia_cabe_y_se_aplica(self):
        p = eng.programa_servicio("FARMACIA")
        a = dd.ajustar(p, RECT9X8)
        self.assertTrue(a["dentro_del_contorno"])
        self.assertNotIn("ajuste_programa", a)


# ---------------------------------------------------------------------------
# 5) CONTRATO PlanRequest + plan_de
# ---------------------------------------------------------------------------

class TestContrato(unittest.TestCase):

    def test_round_trip_seleccion_y_ajuste(self):
        p = dd.PlanRequest(contorno=L, programa={},
                           seleccion=["A", "C"], ajuste="estricto")
        q = dd.PlanRequest.from_dict(p.to_dict())
        self.assertEqual(q.seleccion, ["A", "C"])
        self.assertEqual(q.ajuste, "estricto")

    def test_valores_por_defecto_y_legado(self):
        r = dd.PlanRequest.from_dict({"contorno": L, "programa": {}})
        self.assertIsNone(r.seleccion)
        self.assertEqual(r.ajuste, "ideal")
        r2 = dd.PlanRequest.from_dict({"contorno": L, "programa": {},
                                       "ajuste": "genial",
                                       "seleccion": ["", "  "]})
        self.assertEqual(r2.ajuste, "ideal")
        self.assertEqual(r2.seleccion, [])

    def test_plan_de_aplica_ambos(self):
        p = dd.PlanRequest(contorno=RECT5, programa=_prog_uno(30.0, 28.0),
                           ajuste="estricto")
        res = dd.plan_de(p)
        self.assertIsNotNone(res.analisis)
        self.assertEqual(res.analisis["ajuste_programa"]["nivel"],
                         "estricto")

    def test_alternativas_respeta_ajuste(self):
        lista = dd.alternativas(_prog_uno(30.0, 28.0), RECT5,
                                cantidad=1, ajuste="estricto")
        self.assertIsNotNone(lista[0]["analisis"])
        self.assertEqual(
            lista[0]["analisis"]["ajuste_programa"]["nivel"],
            "estricto")


# ---------------------------------------------------------------------------
# 6) GENERACIÓN REAL (proyecto temporal)
# ---------------------------------------------------------------------------

class TestAplicarReal(ARQGenTestCase):

    def setUp(self):
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("adaptable.arqgen"), name="Adaptable")

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_locales_reducidos_se_generan_dentro(self):
        a = dd.ajustar(_prog_uno(30.0, 28.0), RECT5, ajuste="estricto")
        res = dd.aplicar_plan(self.ctx, a, {"reemplazar_previo": True})
        self.ctx.commit()
        self.assertGreater(len(res["espacios"]), 0)
        for espacio in self.ctx.architecture.list(
                "SPACE", self.ctx.project.id):
            pts = list(getattr(espacio, "boundary", []) or [])
            if len(pts) != 4:
                continue
            rect = [tuple(p[:2]) if isinstance(p, (tuple, list))
                    else p for p in pts]
            self.assertTrue(rect_dentro(rect, RECT5),
                            f"{espacio.name} fuera del polígono")

    def test_seleccion_excluye_espacios_reales(self):
        a = dd.ajustar(_prog_tres(), L, seleccion=["A", "C"])
        res = dd.aplicar_plan(self.ctx, a, {"reemplazar_previo": True})
        self.ctx.commit()
        nombres = [getattr(e, "name", "") for e in res["espacios"]]
        self.assertFalse(any("Local B" in n for n in nombres),
                         "el local excluido no debió generarse")


# ---------------------------------------------------------------------------
# 7) GANCHOS DE VENTANA (con display)
# ---------------------------------------------------------------------------

class TestGanchosPrograma(ARQGenTestCase):
    """El selector de nivel y el diálogo de locales viven, viajan en
    la petición y la selección restaurada vuelve a los controles."""

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

    def test_version_coherente_con_v3430(self):
        self.assertEqual(APP_VERSION, "3.50.0")

    def test_selector_de_ajuste_existe_y_por_defecto_minimo(self):
        w = self.window
        self.assertEqual(
            tuple(w._dd_ajuste_combo.cget("values")),
            tuple(dd.ETIQUETA_AJUSTE[k] for k in dd.AJUSTE_NIVELES))
        self.assertEqual(w._dd_ajuste_actual(), "minimo")
        w._dd_ajuste.set(dd.ETIQUETA_AJUSTE["estricto"])
        self.assertEqual(w._dd_ajuste_actual(), "estricto")

    def test_dialogo_de_locales_lista_y_aplica(self):
        w = self.window
        w._dd_locales_dialogo()
        w.update()
        dialogo = getattr(w, "_dd_locales_dialog", None)
        self.assertIsNotNone(dialogo)
        self.assertTrue(dialogo.winfo_exists())
        vars_locales = w._dd_locales_vars
        self.assertTrue(vars_locales)
        self.assertTrue(all(var.get() for _c, var in vars_locales))
        # desmarcar uno y aplicar
        codigo0, var0 = vars_locales[0]
        var0.set(False)
        w._dd_locales_aplicar()
        seleccion = w._dd_seleccion_actual()
        self.assertIsNotNone(seleccion)
        self.assertNotIn(codigo0, seleccion)
        # Todos los vuelve a marcar
        for _c, var in vars_locales:
            var.set(True)
        w._dd_locales_aplicar()
        self.assertEqual(len(w._dd_seleccion_actual()),
                         len(vars_locales))
        dialogo.destroy()

    def test_peticion_lleva_seleccion_y_ajuste(self):
        w = self.window
        w._dd_origen.set("rectangulo")
        w._dd_origen_cambio()
        w._dd_ajuste.set(dd.ETIQUETA_AJUSTE["medio"])
        w._dd_seleccion = {"DISPENSACION": True,
                           "ALMACEN_FARMACIA": False}
        p = w._dd_peticion()
        self.assertEqual(p.ajuste, "medio")
        self.assertEqual(p.seleccion, ["DISPENSACION"])

    def test_carga_peticion_restaura_controles(self):
        w = self.window
        w._dd_origen.set("rectangulo")
        w._dd_origen_cambio()
        p = dd.PlanRequest(contorno=[(0, 0), (9, 0), (9, 8), (0, 8)],
                           programa={}, ajuste="estricto",
                           seleccion=["DISPENSACION"])
        w._dd_carga_peticion(p)
        self.assertEqual(w._dd_ajuste_actual(), "estricto")
        self.assertEqual(w._dd_seleccion_actual(), ["DISPENSACION"])
        p2 = dd.PlanRequest(contorno=[(0, 0), (9, 0), (9, 8), (0, 8)],
                            programa={})
        w._dd_carga_peticion(p2)
        self.assertEqual(w._dd_ajuste_actual(), "ideal")
        self.assertIsNone(w._dd_seleccion_actual())


if __name__ == "__main__":
    unittest.main()
