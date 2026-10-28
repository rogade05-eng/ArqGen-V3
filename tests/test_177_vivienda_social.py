"""VIVIENDA SOCIAL v3.43.0 — domain/desde_dibujo.py + space_dna.json
+ mobiliario + aplicar_plan.

Los 4 planos de referencia que subió el usuario (48 m2 en Z del
«plan85», estudio de 25 m2 con chaflán, casa cubana de 6.00 x 8.40
del expediente técnico y la casa de 10 x 11 con garaje) contra el
motor: DNA de vivienda (Sala 9 m2, Comedor 6 m2, Lavadero doméstico
separado del hospitalario), «1 nivel» como TOPE DURO (compacta antes
de crecer), modo SALA DISTRIBUIDORA sin pasillo para casas de <=
60 m2, CHAFLANES a 45 grados hacia la sala y MUEBLES automáticos.

Cobertura:
  * catálogo: LIVING_ROOM 9.0, DINING_ROOM 6.0, LAVADERO doméstico
    (2.0/4.0) y LAUNDRY hospitalario INTACTO; quick lavadero/lavandería
  * tope duro: vivienda a 1 nivel por defecto (aviso), «2 niveles»
    crece, ARQ-DDI-011 NOMBRANDO los locales que quedan fuera, el
    servicio (morgue) NO se toca
  * sala distribuidora: sin pasillo en casas <= 60 m2; con pasillo
    en la de 110 m2
  * chaflanes: poligonal de 5 vértices sin aristas nulas, la sala
    absorbe el triángulo (más vértices y más área), desactivables
  * orden por área descendente cuando nadie lleva flujo real
  * los 4 casos dorados (B, C, D completos; A sin lavadero; A con
    lavadero lanza ARQ-DDI-011 nombrándolo)
  * aplicar_plan: mobiliario doméstico automático (cama, sofá...),
    espacios con poligonal, servicios sin muebles
  * contratos: PlanRequest.chaflanes round-trip y plan_de
  * informe: TOPE DE NIVELES / MODO SALA DISTRIBUIDORA / CHAFLANES
  * ganchos de ventana: checkboxes v3.43 del marco experto
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

Z_REAL = [(0.0, 2.9), (2.6, 2.9), (2.6, 0.0), (6.5, 0.0),
          (6.5, 2.9), (3.9, 2.9), (3.9, 6.4), (5.5, 6.4),
          (5.5, 10.4), (0.0, 10.4)]
# el contorno REAL del plano «AP Y MORGUE.dxf» (174.91 m2) para los
# pruebas de servicio (la morgue no cabe en la casa de 48 m2)
Z_AP = [(0.179, 3.617), (0.179, 15.007), (6.829, 15.007),
        (6.829, 8.177), (17.681, 8.177), (17.681, 0.037),
        (3.804, 0.037), (3.804, 3.617)]
B25 = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
CUBANO = [(0.0, 0.0), (6.0, 0.0), (6.0, 8.4), (0.0, 8.4)]
CASA11 = [(0.0, 0.0), (10.0, 0.0), (10.0, 11.0), (0.0, 11.0)]

SEL_SIN_LAVADERO = ["BEDROOM", "BATHROOM", "KITCHEN",
                    "LIVING_ROOM", "DINING_ROOM"]


def _codigo(exc: Exception) -> str:
    return str(getattr(exc, "code", ""))


# ---------------------------------------------------------------------------
# 1) DNA DE VIVIENDA
# ---------------------------------------------------------------------------

class TestDNAVivienda(unittest.TestCase):

    def test_sala_con_minimo_de_vivienda_social(self):
        dna = eng._dna_de(None, "LIVING_ROOM")
        self.assertEqual(float(dna.minimum_area), 9.0)
        self.assertEqual(float(dna.minimum_width), 2.7)

    def test_comedor_con_minimo_de_vivienda_social(self):
        dna = eng._dna_de(None, "DINING_ROOM")
        self.assertEqual(float(dna.minimum_area), 6.0)

    def test_lavadero_domestico_existe_y_es_chico(self):
        dna = eng._dna_de(None, "LAVADERO")
        self.assertIsNotNone(dna)
        self.assertEqual(dna.name_es, "Lavadero doméstico")
        self.assertEqual(float(dna.minimum_area), 2.0)
        self.assertEqual(float(dna.preferred_area), 4.0)
        self.assertEqual(float(dna.minimum_width), 1.2)
        self.assertTrue(dna.wet_zone)

    def test_lavanderia_hospitalaria_intacta(self):
        dna = eng._dna_de(None, "LAUNDRY")
        self.assertEqual(dna.name_es, "Lavandería hospitalaria")
        self.assertEqual(float(dna.minimum_area), 20.0)

    def test_quick_lavadero_va_al_domestico(self):
        prog = dd.programa_quick("dormitorio, bano, lavadero", "x")
        tipos = {r["space_type"] for r in prog["renglones"]}
        self.assertIn("LAVADERO", tipos)
        self.assertNotIn("LAUNDRY", tipos)

    def test_quick_lavanderia_sigue_siendo_hospitalaria(self):
        prog = dd.programa_quick("dormitorio, lavanderia", "x")
        tipos = {r["space_type"] for r in prog["renglones"]}
        self.assertIn("LAUNDRY", tipos)

    def test_el_garaje_del_quick_se_llama_garaje(self):
        prog = dd.programa_quick("dormitorio, garaje", "x")
        nombres = [r["nombre"] for r in prog["renglones"]]
        self.assertIn("Garaje", nombres)

    def test_orden_por_area_descendente_sin_flujos(self):
        renglones = [{"nombre": "a", "flujo": "libre", "area_m2": 5.0},
                     {"nombre": "b", "flujo": "libre", "area_m2": 12.0},
                     {"nombre": "c", "flujo": "libre", "area_m2": 8.0}]
        orden = dd._orden_flujo(renglones)
        self.assertEqual([r["nombre"] for r in orden],
                         ["b", "c", "a"])

    def test_orden_hospitalario_se_conserva(self):
        renglones = [{"nombre": "p", "flujo": "publico",
                      "area_m2": 30.0},
                     {"nombre": "s", "flujo": "sucio",
                      "area_m2": 2.0}]
        orden = dd._orden_flujo(renglones)
        self.assertEqual([r["nombre"] for r in orden], ["s", "p"])


# ---------------------------------------------------------------------------
# 2) TOPE DURO DE NIVELES
# ---------------------------------------------------------------------------

class TestTopeNiveles(unittest.TestCase):

    def test_vivienda_se_topa_a_un_nivel_por_defecto(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala", "casa")
        aj = dd.ajustar(prog, CUBANO, encaje_estricto=True)
        self.assertEqual(aj["niveles"], 1)
        self.assertEqual(aj["tope_niveles"], 1)
        self.assertTrue(any("tope de 1 nivel" in a
                            for a in aj["avisos"]))

    def test_dos_niveles_pedidos_permeten_crecer(self):
        prog = dd.programa_quick("4 dormitorios, 2 banos, sala, "
                                 "cocina, comedor, 2 niveles", "casa2")
        aj = dd.ajustar(prog, Z_REAL, encaje_estricto=True)
        self.assertEqual(aj["niveles"], 2)
        self.assertEqual(aj["tope_niveles"], 2)

    def test_arq_ddi_011_nombra_los_locales_que_quedan(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala, lavadero", "casaZ")
        with self.assertRaises(DomainError) as cm:
            dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                       seleccion=["BEDROOM", "BATHROOM", "KITCHEN",
                                  "LIVING_ROOM", "DINING_ROOM",
                                  "LAVADERO"])
        self.assertEqual(_codigo(cm.exception), "ARQ-DDI-011")
        self.assertIn("Lavadero", str(cm.exception.message))

    def test_el_servicio_no_se_topa(self):
        p = eng.programa_servicio("MORGUE", {})
        aj = dd.ajustar(p, Z_AP, encaje_estricto=True,
                        ajuste="estricto")
        self.assertIsNone(aj["tope_niveles"])
        self.assertEqual(aj["niveles"], 1)

    def test_plan_de_respeta_los_niveles_deseados(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala", "casa")
        pet = dd.PlanRequest(contorno=CUBANO, programa=prog,
                             niveles_deseados=1)
        res = dd.plan_de(pet)
        self.assertEqual(res.analisis["niveles"], 1)


# ---------------------------------------------------------------------------
# 3) MODO SALA DISTRIBUIDORA
# ---------------------------------------------------------------------------

class TestSalaDistribuidora(unittest.TestCase):

    def test_casa_pequena_sin_pasillo(self):
        prog = dd.programa_quick("dormitorio, bano, cocina, sala", "b")
        aj = dd.ajustar(prog, B25, encaje_estricto=True)
        self.assertTrue(aj["sala_distribuidora"])
        self.assertIsNone(aj["reparto"][0]["pasillo"])
        self.assertTrue(any("SALA DISTRIBUIDORA" in a
                            for a in aj["avisos"]))

    def test_casa_grande_con_pasillo(self):
        prog = dd.programa_quick("dormitorio, cocina, bano, sala, "
                                 "garaje", "d")
        aj = dd.ajustar(prog, CASA11, encaje_estricto=True)
        self.assertFalse(aj["sala_distribuidora"])
        self.assertIsNotNone(aj["reparto"][0]["pasillo"])

    def test_el_servicio_nunca_es_distribuidor(self):
        p = eng.programa_servicio("MORGUE", {})
        aj = dd.ajustar(p, Z_AP, encaje_estricto=True,
                        ajuste="estricto")
        self.assertFalse(aj["sala_distribuidora"])


# ---------------------------------------------------------------------------
# 4) CHAFLANES A 45 GRADOS
# ---------------------------------------------------------------------------

class TestChaflanes(unittest.TestCase):

    def setUp(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala", "casaZ")
        self.aj = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                             seleccion=SEL_SIN_LAVADERO)

    def test_la_casa_z_sale_en_un_nivel_al_completo(self):
        self.assertEqual(self.aj["niveles"], 1)
        self.assertTrue(self.aj["dentro_del_contorno"])
        self.assertGreaterEqual(
            float(self.aj["totales"]["aprovechamiento_pct"]), 99.0)

    def test_hay_chaflan_con_poligonal_de_cinco_vertices(self):
        self.assertTrue(self.aj["chaflanes"])
        cortados = [r for r in self.aj["reparto"][0]["locales"]
                    if r.get("chaflan")]
        self.assertTrue(cortados)
        for r in cortados:
            poly = r["poligono"]
            self.assertEqual(len(poly), 5)
            n = len(poly)
            for i in range(n):
                a, b = poly[i], poly[(i + 1) % n]
                d = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                self.assertGreater(d, 1e-6,
                                   f"arista nula en {r['nombre']}")
        for r in self.aj["reparto"][0]["locales"]:
            if r.get("poligono"):
                n = len(r["poligono"])
                for i in range(n):
                    a, b = r["poligono"][i], \
                        r["poligono"][(i + 1) % n]
                    d = ((a[0] - b[0]) ** 2
                         + (a[1] - b[1]) ** 2) ** 0.5
                    self.assertGreater(d, 1e-6,
                                       f"arista nula en {r['nombre']}")

    def test_la_sala_absorbe_el_triangulo(self):
        sala = next(r for r in self.aj["reparto"][0]["locales"]
                    if r["space_type"] == "LIVING_ROOM")
        self.assertGreater(len(sala.get("poligono") or []), 4)

    def test_la_perdida_queda_documentada(self):
        for h in self.aj["chaflanes"]:
            self.assertGreater(h["perdida_m2"], 0.0)
            self.assertGreaterEqual(h["cateto_m"], 0.45)
        self.assertTrue(any("chaflanes a 45 grados" in a
                            for a in self.aj["avisos"]))

    def test_desactivables(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala", "casaZ")
        aj = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                        seleccion=SEL_SIN_LAVADERO, chaflanes=False)
        self.assertEqual(aj["chaflanes"], [])
        self.assertTrue(all(not r.get("poligono")
                            for n in aj["reparto"]
                            for r in n["locales"]))

    def test_el_servicio_sin_sala_no_tiene_chaflanes(self):
        p = eng.programa_servicio("MORGUE", {})
        aj = dd.ajustar(p, Z_AP, encaje_estricto=True,
                        ajuste="estricto")
        self.assertEqual(aj["chaflanes"], [])


# ---------------------------------------------------------------------------
# 5) LOS CUATRO CASOS DE REFERENCIA
# ---------------------------------------------------------------------------

class TestCasosDeReferencia(unittest.TestCase):

    def test_estudio_25m2_entero(self):
        prog = dd.programa_quick("dormitorio, bano, cocina, sala", "b")
        aj = dd.ajustar(prog, B25, encaje_estricto=True)
        self.assertEqual(aj["niveles"], 1)
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertEqual(len(aj["reparto"][0]["locales"]), 4)
        self.assertGreaterEqual(
            float(aj["totales"]["aprovechamiento_pct"]), 95.0)

    def test_cubano_6x84_con_dormitorios_normativos(self):
        prog = dd.programa_quick("2 dormitorios, bano, sala, cocina, "
                                 "comedor", "c")
        aj = dd.ajustar(prog, CUBANO, encaje_estricto=True)
        self.assertEqual(aj["niveles"], 1)
        dorms = [r for r in aj["reparto"][0]["locales"]
                 if r["space_type"] == "BEDROOM"]
        self.assertEqual(len(dorms), 2)
        for d in dorms:
            self.assertGreaterEqual(float(d["area_m2"]), 9.0)
            w = abs(d["rect"][2][0] - d["rect"][0][0])
            h = abs(d["rect"][2][1] - d["rect"][0][1])
            self.assertGreaterEqual(min(w, h), 2.4, d["nombre"])

    def test_casa_10x11_con_garaje(self):
        prog = dd.programa_quick("dormitorio, cocina, bano, sala, "
                                 "garaje", "d")
        aj = dd.ajustar(prog, CASA11, encaje_estricto=True)
        self.assertEqual(aj["niveles"], 1)
        tipos = {r["space_type"]
                 for r in aj["reparto"][0]["locales"]}
        self.assertIn("PARKING", tipos)
        self.assertTrue(aj["dentro_del_contorno"])

    def test_casa_z_48m2_sin_lavadero_al_100(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala", "a")
        aj = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                        seleccion=SEL_SIN_LAVADERO)
        self.assertEqual(aj["niveles"], 1)
        self.assertTrue(aj["dentro_del_contorno"])
        self.assertGreaterEqual(
            float(aj["totales"]["aprovechamiento_pct"]), 99.0)

    def test_casa_z_con_lavadero_exige_decision_honesta(self):
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala, lavadero", "a")
        with self.assertRaises(DomainError) as cm:
            dd.ajustar(prog, Z_REAL, encaje_estricto=True)
        self.assertEqual(_codigo(cm.exception), "ARQ-DDI-011")
        self.assertIn("Lavadero", str(cm.exception.message))


# ---------------------------------------------------------------------------
# 6) INFORME Y CONTRATOS
# ---------------------------------------------------------------------------

class TestInformeYContratos(unittest.TestCase):

    def _casa(self):
        prog = dd.programa_quick("dormitorio, bano, cocina, sala", "b")
        return dd.ajustar(prog, B25, encaje_estricto=True)

    def test_informe_documenta_tope_distribuidora_y_chaflanes(self):
        texto = dd.texto_ajuste(self._casa())
        self.assertIn("TOPE DE NIVELES (v3.43.0)", texto)
        self.assertIn("MODO SALA DISTRIBUIDORA (v3.43.0)", texto)

    def test_planrequest_chaflanes_round_trip(self):
        prog = dd.programa_quick("dormitorio, bano, cocina, sala", "b")
        pet = dd.PlanRequest(contorno=B25, programa=prog,
                             niveles_deseados=1, chaflanes=False)
        datos = pet.to_dict()
        self.assertIs(datos["chaflanes"], False)
        pet2 = dd.PlanRequest.from_dict(datos)
        self.assertFalse(pet2.chaflanes)
        self.assertEqual(pet2.niveles_deseados, 1)
        pet3 = dd.PlanRequest.from_dict({"contorno": B25,
                                         "programa": prog})
        self.assertIsNone(pet3.chaflanes)

    def test_version_coherente_con_v3430(self):
        self.assertEqual(APP_VERSION, "3.50.0")


# ---------------------------------------------------------------------------
# 7) APLICAR_PLAN: MUEBLES Y POLIGONALES
# ---------------------------------------------------------------------------

class TestAplicarVivienda(ARQGenTestCase):

    def test_muebles_y_poligonales_en_el_proyecto(self):
        from domain import mobiliario as mob
        prog = dd.programa_quick("2 dormitorios, bano, cocina, "
                                 "comedor, sala", "casaZ")
        aj = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                        seleccion=SEL_SIN_LAVADERO)
        self.assertTrue(aj["chaflanes"])
        ctx = self.application.create_project(
            self.project_path("v43.arqgen"), name="v43")
        res = dd.aplicar_plan(ctx, aj, {"nombre_edificio": "Casa Z"})
        self.assertTrue(res["mobiliario"]["activado"])
        self.assertGreater(res["mobiliario"]["piezas"], 0)
        conteo = mob.conteo_por_tipo(ctx)
        self.assertTrue(any("cama" in k for k in conteo))
        poligonales = [e for e in mob.lista_tipos(ctx, "SPACE")
                       if len(list(getattr(e, "boundary", []) or [])) > 4]
        self.assertTrue(poligonales)

    def test_sin_muebles_si_se_desactiva(self):
        from domain import mobiliario as mob
        prog = dd.programa_quick("dormitorio, bano, cocina, sala", "b")
        aj = dd.ajustar(prog, B25, encaje_estricto=True)
        ctx = self.application.create_project(
            self.project_path("v43b.arqgen"), name="v43b")
        res = dd.aplicar_plan(ctx, aj, {"nombre_edificio": "Casa B2",
                                        "mobiliario": False})
        self.assertFalse(res["mobiliario"]["activado"])
        self.assertEqual(sum(mob.conteo_por_tipo(ctx).values()), 0)

    def test_el_servicio_no_se_amuebla(self):
        p = eng.programa_servicio("MORGUE", {})
        aj = dd.ajustar(p, Z_AP, encaje_estricto=True,
                        ajuste="estricto")
        ctx = self.application.create_project(
            self.project_path("v43c.arqgen"), name="v43c")
        res = dd.aplicar_plan(ctx, aj, {"nombre_edificio": "Morgue"})
        self.assertFalse(res["mobiliario"]["activado"])


# ---------------------------------------------------------------------------
# 8) GANCHOS DE VENTANA
# ---------------------------------------------------------------------------

@unittest.skipUnless(DISPLAY, "requiere display (Xvfb)")
class TestGanchosVentana(ARQGenTestCase):
    """El diálogo «Desde dibujo» lleva los checkboxes v3.43 y el
    análisis respeta el tope y la sala distribuidora."""

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
        self.window.open_desde_dibujo_dialog()
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_los_checkboxes_v343_existen_y_van_activos(self):
        self.assertTrue(self.window._dd_chaflanes.get())
        self.assertTrue(self.window._dd_mobiliario.get())

    def test_ajustar_respeta_el_tope_y_la_distribuidora(self):
        w = self.window
        w._dd_modo.set("edificacion")
        w._dd_modo_cambio()
        w._dd_origen.set("rectangulo")
        w._dd_origen_cambio()
        w._dd_rec_ancho.set("5.0")
        w._dd_rec_fondo.set("5.0")
        w._dd_rec_ox.set("0.0")
        w._dd_rec_oy.set("0.0")
        w._dd_quick.set("dormitorio, bano, cocina, sala")
        w._dd_quick_aplicar()
        # el mínimo no cabe en 25 m2: con Estricto la escalera entra
        from domain import desde_dibujo as _dd43
        w._dd_ajuste.set(_dd43.ETIQUETA_AJUSTE["estricto"])
        w._dd_ajustar()
        analisis = w._dd_analisis
        self.assertIsNotNone(analisis)
        self.assertEqual(analisis["niveles"], 1)
        self.assertTrue(analisis["sala_distribuidora"])

    def test_los_controles_del_programa_adaptable_siguen_vivos(self):
        self.assertTrue(hasattr(self.window, "_dd_locales_vars"))
        self.assertTrue(hasattr(self.window, "_dd_ajuste_actual"))


if __name__ == "__main__":
    unittest.main()
