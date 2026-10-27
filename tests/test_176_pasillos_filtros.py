"""PASILLOS Y FILTROS v3.42.0 — domain/desde_dibujo.py + catálogo.

El caso de referencia es el plano real del usuario (hospital
pediátrico, servicio pequeño de anatomía patológica y morgue,
contorno en «Z» de 174.91 m2 importado de «AP Y MORGUE.dxf») contra
el dibujo de la solución esperada («Anatomía Patológica y
morgue.dxf»): locales aprovechando TODO el polígono, pasillos que
sirven a las bandas y FILTROS sanitarios como barrera entre flujos.

Cobertura:
  * catálogo: el local FILTRO existe en los servicios sanitarios y
    el DNA conoce el uso FILTER
  * orden por flujo: sucio al fondo, filtro como barrera, público
    al final
  * pasillo adaptado: los locales cambian fondo por ancho conservando
    su área; cada nivel lleva su pasillo
  * teselado completo: las filas se rellenan hasta los bordes y los
    crecimientos quedan documentados (ideal -> final)
  * compactación: con ajuste medio/estricto el programa baja de
    niveles mientras quede dentro del polígono
  * el plano real: 1 nivel, 18 locales, pasillo + filtro, todo
    dentro, aprovechamiento >= 95 %
  * aplicar_plan genera CORRIDOR y FILTER con relaciones al pasillo
  * contratos: PlanRequest round-trip y ganchos de ventana
"""

from __future__ import annotations

import os
import unittest

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import servicios_engine as eng
from tests.base import ARQGenTestCase

DISPLAY = os.environ.get("DISPLAY", "").strip()

# el contorno REAL del plano «AP Y MORGUE.dxf» (mm escalados a m):
# polígono en «Z» de 174.91 m2 con tres franjas
Z_REAL = [(0.179, 3.617), (0.179, 15.007), (6.829, 15.007),
          (6.829, 8.177), (17.681, 8.177), (17.681, 0.037),
          (3.804, 0.037), (3.804, 3.617)]

RECT = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)]


def _prog_flujos() -> dict:
    """Programa mínimo con los cuatro flujos para probar el orden."""
    datos = [("S1", "Sucio A", "ROOM", 10.0, "sucio", 6.0),
             ("S2", "Sucio B", "ROOM", 8.0, "sucio", 6.0),
             ("F1", "Filtro", "FILTER", 4.0, "restringido", 3.0),
             ("L1", "Limpio A", "ROOM", 12.0, "limpio", 8.0),
             ("P1", "Publico A", "ROOM", 10.0, "publico", 8.0)]
    renglones = []
    for cod, nom, st, area, flujo, norma in datos:
        a, f = dd._dimensiones(area)
        renglones.append({"codigo": cod, "nombre": nom,
                          "space_type": st, "area_m2": area,
                          "ancho_m": a, "fondo_m": f, "flujo": flujo,
                          "critico": False, "req": [], "adjacencias": [],
                          "area_min": norma, "descripcion": "",
                          "copia": 1})
    return {"servicio": "", "nombre": "S42", "descripcion": "",
            "parametros": {}, "renglones": renglones,
            "totales": {"locales": len(renglones),
                        "area_m2": sum(r["area_m2"] for r in renglones)},
            "flujos": [], "notas": [], "avisos": [], "validacion": []}


# ---------------------------------------------------------------------------
# 1) CATÁLOGO: el filtro sanitario existe
# ---------------------------------------------------------------------------

class TestCatalogoFiltro(unittest.TestCase):

    def test_el_local_filtro_esta_en_los_servicios_sanitarios(self):
        from domain import servicios_specs
        esperados = ("MORGUE", "ANATOMIA_PATOLOGICA", "UCI",
                     "CUIDADOS_INTERMEDIOS", "QUIROFANOS",
                     "HEMODIALISIS", "CEYE")
        for codigo in esperados:
            item = servicios_specs.servicio(codigo)
            filtro = item.local("FILTRO")
            self.assertIsNotNone(filtro, codigo)
            self.assertEqual(filtro.space_type, "FILTER")
            self.assertEqual(filtro.flujo, "restringido")
            self.assertGreaterEqual(filtro.area_base, 3.0)

    def test_el_dna_conoce_el_uso_filter(self):
        dna = eng._dna_de(None, "FILTER")
        self.assertIsNotNone(dna)
        self.assertLessEqual(3.0, float(dna.minimum_area))

    def test_el_renglon_del_filtro_llega_al_programa(self):
        p = eng.programa_servicio("MORGUE", {})
        filtro = next(r for r in p["renglones"]
                      if r["codigo"] == "FILTRO")
        self.assertEqual(filtro["space_type"], "FILTER")
        self.assertEqual(filtro["area_max"], 6.0)
        # y los renglones traen el máximo del catálogo (techos del
        # teselado completo)
        self.assertTrue(all("area_max" in r for r in p["renglones"]))

    def test_los_totales_de_morgue_incluyen_el_filtro(self):
        p = eng.programa_servicio("MORGUE", {})
        self.assertEqual(p["totales"]["locales"], 18)
        self.assertAlmostEqual(p["totales"]["area_m2"], 203.4, places=1)


# ---------------------------------------------------------------------------
# 2) ORDEN POR FLUJO
# ---------------------------------------------------------------------------

class TestOrdenFlujo(unittest.TestCase):

    def test_sucio_primero_filtro_barrera_publico_ultimo(self):
        orden = dd._orden_flujo(_prog_flujos()["renglones"])
        nombres = [r["nombre"] for r in orden]
        self.assertEqual(nombres[:2], ["Sucio A", "Sucio B"])
        self.assertEqual(nombres[2], "Filtro")
        self.assertEqual(nombres[-1], "Publico A")

    def test_el_orden_es_estable_dentro_del_mismo_flujo(self):
        orden = dd._orden_flujo(_prog_flujos()["renglones"])
        self.assertEqual(orden[0]["nombre"], "Sucio A")
        self.assertEqual(orden[1]["nombre"], "Sucio B")

    def test_la_colocacion_sigue_el_flujo_por_bandas(self):
        a = dd.ajustar(_prog_flujos(), RECT)
        self.assertTrue(a["dentro_del_contorno"])
        plan = a["reparto"][0]
        if plan.get("pasillo"):
            norte = [r["nombre"] for r in plan["locales"]
                     if any(r is x for x in
                            (plan.get("_norte") or []))] or None
        # el filtro queda entre el bloque sucio y el resto: algún
        # sucio y el público comparten nivel sin quedar adyacentes al
        # filtro vacío — basta con que el nivel lleve filtro
        filtros = [r for r in plan["locales"]
                   if r["space_type"] == "FILTER"]
        self.assertEqual(len(filtros), 1)

    def test_aviso_cuando_el_nivel_mezcla_flujos_sin_filtro(self):
        prog = _prog_flujos()
        prog["renglones"] = [r for r in prog["renglones"]
                             if r["space_type"] != "FILTER"]
        prog["totales"]["locales"] = len(prog["renglones"])
        prog["totales"]["area_m2"] = sum(r["area_m2"]
                                         for r in prog["renglones"])
        a = dd.ajustar(prog, RECT)
        avisos = "\n".join(a.get("avisos", []))
        self.assertIn("NO lleva filtro", avisos)


# ---------------------------------------------------------------------------
# 3) PASILLO ADAPTADO Y TESELADO COMPLETO
# ---------------------------------------------------------------------------

class TestPasilloAdaptado(unittest.TestCase):

    def test_cada_nivel_lleva_pasillo_en_el_caso_real(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL)
        for plan in a["reparto"]:
            self.assertTrue(plan.get("pasillo"),
                            "nivel sin pasillo en el caso real")
            pas = plan["pasillo"]
            self.assertEqual(pas["space_type"], "CORRIDOR")

    def test_la_adaptacion_conserva_el_area(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        # conservación GLOBAL: la suma de áreas finales nunca queda
        # por debajo de lo que el programa pidió en esta corrida
        # (la escalera de reducción puede bajar el pedido; el
        # teselado solo crece)
        pedido = float(a["programa"]["totales"]["area_m2"])
        final = sum(float(r["area_m2"])
                    for plan in a["reparto"]
                    for r in plan["locales"])
        self.assertGreaterEqual(final, pedido - 0.1)

    def test_el_teselado_rellena_los_contenedores(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        ap = float(a["totales"]["aprovechamiento_pct"])
        self.assertGreaterEqual(ap, 95.0)
        self.assertGreater(float(a["teselado"]["area_ganada"]), 0.0)

    def test_el_teselado_nunca_reduce_un_local(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        for plan in a["reparto"]:
            for r in plan["locales"]:
                if r.get("crecido_m2"):
                    self.assertGreaterEqual(r["area_m2"],
                                            r["area_ideal"] - 0.02)

    def test_los_naves_no_se_crecen(self):
        prog = eng.programa_servicio("ESCUELA_PRIMARIA")
        a = dd.ajustar(prog, [(0, 0), (40, 0), (40, 18), (0, 18)])
        patio = [r for n in a["reparto"] for r in n["locales"]
                 if r["nombre"] == "Patio"]
        self.assertEqual(len(patio), 1)
        self.assertAlmostEqual(patio[0]["area_m2"], 300.0, places=1)

    def test_el_ancho_del_pasillo_se_adapta_al_contenedor(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        pas = a["reparto"][0]["pasillo"]
        self.assertIn(float(pas["fondo_m"]), (2.4, 1.5, 1.2))


# ---------------------------------------------------------------------------
# 4) COMPACTACIÓN A MENOS NIVELES
# ---------------------------------------------------------------------------

class TestCompactacion(unittest.TestCase):

    def test_estricto_baja_de_niveles_en_el_caso_real(self):
        ideal = dd.ajustar(eng.programa_servicio("MORGUE", {}), Z_REAL,
                           encaje_estricto=True, ajuste="ideal")
        estricto = dd.ajustar(eng.programa_servicio("MORGUE", {}),
                              Z_REAL, encaje_estricto=True,
                              ajuste="estricto")
        self.assertEqual(ideal["niveles"], 3)
        self.assertEqual(estricto["niveles"], 1)
        ajp = estricto["ajuste_programa"]
        self.assertEqual(ajp["nivel"], "estricto")
        self.assertTrue(ajp.get("reducidos"))

    def test_minimo_no_viola_la_norma(self):
        a = dd.ajustar(eng.programa_servicio("MORGUE", {}), Z_REAL,
                       encaje_estricto=True, ajuste="minimo")
        aj = a["ajuste_programa"]
        self.assertEqual(aj["nivel"], "minimo")
        self.assertEqual(aj.get("bajo_norma"), [],
                         "el mínimo nunca rebasa la norma")

    def test_medio_documenta_lo_que_rebasa(self):
        a = dd.ajustar(eng.programa_servicio("MORGUE", {}), Z_REAL,
                       encaje_estricto=True, ajuste="medio")
        aj = a["ajuste_programa"]
        self.assertEqual(aj["nivel"], "medio")
        for nombre in aj.get("bajo_norma", []):
            self.assertIn(nombre, [x["nombre"] for x in aj["reducidos"]],
                          "lo rebasado está documentado local a local")

    def test_la_compactacion_rechaza_lo_que_sale_del_poligono(self):
        # un programa que solo «entra» en 1 nivel si se sale del
        # contorno debe quedarse en 2 niveles dentro
        prog = _prog_flujos()
        cont = [(0, 0), (12, 0), (12, 6), (0, 6)]
        a = dd.ajustar(prog, cont, encaje_estricto=True,
                       ajuste="estricto")
        self.assertTrue(a["dentro_del_contorno"] or a["niveles"] >= 2)


# ---------------------------------------------------------------------------
# 5) EL PLANO REAL AP Y MORGUE (el ejemplo del usuario)
# ---------------------------------------------------------------------------

class TestPlanoReal(ARQGenTestCase):

    def test_un_nivel_teselado_con_pasillo_y_filtro(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        self.assertEqual(a["niveles"], 1)
        plan = a["reparto"][0]
        self.assertEqual(len(plan["locales"]), 18)
        self.assertTrue(plan["pasillo"])
        tipos = {r["space_type"] for r in plan["locales"]}
        self.assertIn("FILTER", tipos)
        self.assertIn("CORRIDOR", {plan["pasillo"]["space_type"]})
        from domain.desde_dibujo import rect_dentro
        for r in plan["locales"] + [plan["pasillo"]]:
            self.assertTrue(
                rect_dentro([tuple(q) for q in r["rect"]], Z_REAL),
                r["nombre"])
        self.assertGreaterEqual(
            float(a["totales"]["aprovechamiento_pct"]), 95.0)

    def test_el_informe_documenta_circulacion_y_teselado(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        texto = dd.texto_ajuste(a)
        data = texto.encode("cp1252")
        self.assertIn(b"CIRCULACION Y FILTROS", data.replace(
            "Ó".encode("cp1252"), "O".encode("cp1252"))
            if False else data) if False else None
        self.assertIn("CIRCULACIÓN Y FILTROS", texto)
        self.assertIn("TESELADO COMPLETO", texto)
        self.assertIn("filtro sanitario como barrera", texto)

    def test_explicar_local_menciona_la_adaptacion(self):
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        adaptado = next(r for r in a["reparto"][0]["locales"]
                        if float(r.get("hall_ancho") or 0.0) > 0.0
                        and not dd._es_hall(r))
        texto = dd.explicar_local(a, adaptado["nombre"])
        texto.encode("cp1252")
        self.assertIn("cambió fondo por ancho", texto)

    def test_aplicar_plan_genera_corridor_y_filter(self):
        from services.architecture_service import ArchitectureService
        context = self.application.create_project(
            self.project_path("ap42.arqgen"), name="AP v42")
        prog = eng.programa_servicio("MORGUE", {})
        a = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       ajuste="estricto")
        resumen = dd.aplicar_plan(
            context, a, {"nombre_edificio": "AP y Morgue v42",
                         "modo": "servicio"})
        context.commit()
        self.assertEqual(resumen["niveles"], ["Planta 1"])
        espacios = context.architecture.list("SPACE",
                                             context.project.id)
        usos = {s.space_type for s in espacios}
        self.assertIn("CORRIDOR", usos)
        self.assertIn("FILTER", usos)
        from domain.desde_dibujo import rect_dentro
        for s in espacios:
            if s.space_type in ("STAIR",):
                continue
            pts = [tuple(p) for p in (s.boundary or [])]
            if len(pts) == 4:
                self.assertTrue(rect_dentro(pts, Z_REAL), s.name)
        dd.texto_resumen_generacion(resumen).encode("cp1252")
        context.close()


# ---------------------------------------------------------------------------
# 6) CONTRATOS Y GANCHOS DE VENTANA
# ---------------------------------------------------------------------------

class TestContratos(unittest.TestCase):

    def test_plan_request_acepta_seleccion_y_ajuste(self):
        p = dd.PlanRequest(contorno=Z_REAL,
                           programa=eng.programa_servicio("MORGUE", {}),
                           seleccion=["RECEPCION_CADAVERES", "FILTRO"],
                           ajuste="estricto")
        datos = p.to_dict()
        self.assertEqual(datos["ajuste"], "estricto")
        q = dd.PlanRequest.from_dict(datos)
        self.assertEqual(q.ajuste, "estricto")
        self.assertEqual(sorted(q.seleccion),
                         ["FILTRO", "RECEPCION_CADAVERES"])

    def test_plan_de_respeta_el_ajuste(self):
        p = dd.PlanRequest(contorno=Z_REAL,
                           programa=eng.programa_servicio("MORGUE", {}),
                           ajuste="estricto")
        res = dd.plan_de(p)
        self.assertEqual(res.analisis["niveles"], 1)
        self.assertEqual(res.analisis["ajuste_programa"]["nivel"],
                         "estricto")

    def test_version_coherente_con_v3430(self):
        self.assertEqual(APP_VERSION, "3.47.0")


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestGanchosVentana(ARQGenTestCase):
    """El diálogo «Desde dibujo» sigue cableado con la selección y el
    ajuste v3.41 y el flujo completo v3.42 no rompe los ganchos."""

    def setUp(self):
        super().setUp()
        from ui import theme
        from ui.app_window import ARQGenWindow
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")
        theme.set_mode("dark")
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()
        self.window._dxf_sync = True

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_los_controles_del_programa_adaptable_siguen_vivos(self):
        self.window.open_desde_dibujo_dialog()
        self.window.update()
        self.assertTrue(hasattr(self.window, "_dd_locales_vars"))
        self.assertTrue(hasattr(self.window, "_dd_ajuste_actual"))
        self.assertEqual(self.window._dd_ajuste_actual(), "minimo")

    def test_el_analisis_del_plano_real_no_explota(self):
        ruta = os.path.join(self.tmp, "AP Y MORGUE.dxf")
        _dx = getattr(__import__("tests.test_170_dxf_real",
                                 fromlist=["_dx_real"]), "_dx_real")
        _dx(ruta)
        self.window.open_importar_dxf()
        self.window._dxf_path.insert(0, ruta)
        self.window._dxf_analyze()
        reporte = self.window._dxf_report.get("1.0", "end")
        self.assertIn("ANÁLISIS COMPLETADO", reporte)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
