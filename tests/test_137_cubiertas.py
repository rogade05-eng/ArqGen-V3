"""CUBIERTAS SEGÚN ESTILO, TIPOLOGÍA CONSTRUCTIVA Y ESTRUCTURAL (v3.15.0).

Lo pedido: «también el tema de las cubiertas según estilo arquitectónico,
tipología constructiva y estructural».

Cobertura:
* Envolvente convexa y offset del alero (casos verificados a mano).
* Resolución de parámetros: el estilo manda en «auto» (colonial → teja
  a dos aguas, racionalista → plana, sostenible → vegetal transitable),
  los valores explícitos ganan, y material/tipología se compasan.
* Cumbrera: por el eje LARGO, altura = semivano × pendiente; en cuatro
  aguas se acorta el eje; en un agua el borde alto es un borde.
* Superficie real = proyección × sqrt(1 + pendiente²); QTO ROOF_AREA.
* Entidad ROOF persistente al reabrir, quitar/regenerar idempotente y
  purga con la regeneración de la edificación.
* Estimador paramétrico: teja → 126211, chapa → 124151, plana → 110120
  (compatibilidad con el comportamiento anterior) y mobiliario/barandas.
* Geometría 3D (caras de faldones, frontones, parapeto) y PNG.
* Mensajes cp1252 y GUI.
"""

from __future__ import annotations

from types import SimpleNamespace
import math
import unittest

from core.errors import ARQGenError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from domain import cubiertas
from ui import building_wizard as bwiz
from ui import variant_budget as vbudget


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


DISPLAY = _display_available()


class _ProyectoBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("cub.arqgen"), name="Cubiertas")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta 1", 0.0, 3.0)
        self.sala = self.arq.create_space(
            self.nivel.code, "Sala", "ROOM",
            [(0, 0), (8, 0), (8, 5), (0, 5)])

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()


class TestGeometria(ARQGenTestCase):

    def test_envolvente_convexa_rectangulo(self):
        hull = cubiertas.envolvente_convexa(
            [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.assertEqual(len(hull), 4)

    def test_envolvente_convexa_en_l_descarta_interior(self):
        puntos = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6)]
        hull = cubiertas.envolvente_convexa(puntos)
        self.assertNotIn((3.0, 3.0), hull)
        self.assertEqual(len(hull), 5)

    def test_offset_convexo_aumenta_el_area(self):
        rect = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
        grande = cubiertas.offset_convexo(rect, 0.6)
        self.assertGreater(cubiertas.area_poligono(grande),
                           cubiertas.area_poligono(rect))
        # un rectángulo se convierte en rectángulo de 4+0.6*2 por 3+0.6*2
        self.assertAlmostEqual(cubiertas.area_poligono(grande),
                               5.2 * 4.2, places=6)

    def test_superficie_inclinada_con_pendiente(self):
        from domain.model import Roof
        roof = Roof(project_id="p", code="ARQ-ROOF-001",
                    tipologia="dos_aguas", material="teja_curva",
                    pendiente_pct=30.0,
                    footprint=[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0),
                               (0.0, 3.0)],
                    ridge=((2.0, 0.0), (2.0, 3.0)), altura_cumbrera_m=0.6)
        datos = cubiertas.superficie_cubierta(roof)
        self.assertAlmostEqual(datos["area_proyectada"], 12.0, places=2)
        esperado = 12.0 * math.sqrt(1.0 + 0.3 ** 2)
        self.assertAlmostEqual(datos["area_inclinada"], esperado, places=2)


class TestParametros(ARQGenTestCase):

    def test_estilo_colonial_sugiere_teja_a_dos_aguas(self):
        data = bwiz.BuildingWizardData(architectural_style="Colonial cubano")
        p = cubiertas.resolver_parametros(data)
        self.assertEqual(p["tipologia"], "dos_aguas")
        self.assertEqual(p["material"], "teja_curva")
        self.assertEqual(p["estructura"], "madera")

    def test_estilo_racionalista_sugiere_plana(self):
        data = bwiz.BuildingWizardData(architectural_style="Racionalista")
        p = cubiertas.resolver_parametros(data)
        self.assertTrue(p["tipologia"].startswith("plana"))
        self.assertEqual(p["material"], "losa_impermeabilizada")
        self.assertEqual(p["estructura"], "hormigon")

    def test_estilo_sostenible_sugiere_vegetal_transitable(self):
        data = bwiz.BuildingWizardData(
            architectural_style="Sostenible (bioclimático)")
        p = cubiertas.resolver_parametros(data)
        self.assertEqual(p["tipologia"], "plana_transitable")
        self.assertEqual(p["material"], "cubierta_vegetal")

    def test_lo_explicito_gana_al_estilo(self):
        data = bwiz.BuildingWizardData(architectural_style="Colonial cubano")
        p = cubiertas.resolver_parametros(data, tipologia="un_agua",
                                          material="chapa_metalica")
        self.assertEqual(p["tipologia"], "un_agua")
        self.assertEqual(p["material"], "chapa_metalica")

    def test_plana_no_lleva_teja_y_agua_no_lleva_losa(self):
        p = cubiertas.resolver_parametros(None, tipologia="plana_no_transitable",
                                          material="teja_curva")
        self.assertEqual(p["material"], "losa_impermeabilizada")
        p2 = cubiertas.resolver_parametros(None, tipologia="dos_aguas",
                                           material="losa_impermeabilizada")
        self.assertEqual(p2["material"], "teja_curva")

    def test_tipologia_desconocida_da_error_amable(self):
        with self.assertRaises(ARQGenError) as ctx_err:
            cubiertas.resolver_parametros(None, tipologia="cónica")
        self.assertEqual(getattr(ctx_err.exception, "code", ""),
                         "ARQ-CUB-001")

    def test_alero_por_defecto_sale_del_asistente(self):
        data = bwiz.BuildingWizardData(eaves_m=0.9)
        p = cubiertas.resolver_parametros(data, tipologia="dos_aguas")
        self.assertAlmostEqual(p["alero_m"], 0.9)


class TestCumbrera(_ProyectoBase):

    def test_cumbrera_en_el_eje_largo_con_altura_correcta(self):
        resumen = cubiertas.generar_cubierta(
            self.context, None, tipologia="dos_aguas",
            pendiente_pct=30.0, con_qto=False)
        roof = self.context.architecture.list("ROOF",
                                              self.context.project.id)[0]
        # el eje largo es X (8 m): la cumbrera corre en X a y = centro
        x1, y1 = roof.ridge[0]
        x2, y2 = roof.ridge[1]
        self.assertAlmostEqual(y1, y2, places=6)
        self.assertAlmostEqual(abs(x2 - x1), 8.0 + 2 * roof.alero_m,
                               places=6)
        semivano = (5.0 + 2 * roof.alero_m) / 2.0
        self.assertAlmostEqual(roof.altura_cumbrera_m,
                               semivano * 0.30, places=6)
        self.assertGreater(resumen["superficie"]["area_inclinada"], 0)

    def test_edificio_vertical_cumbrera_en_y(self):
        self.arq.create_space(self.nivel.code, "Sala Alta", "ROOM",
                              [(0, 0), (3, 0), (3, 9), (0, 9)])
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="dos_aguas", con_qto=False)
        roof = self.context.architecture.list("ROOF",
                                              self.context.project.id)[0]
        self.assertAlmostEqual(roof.ridge[0][0], roof.ridge[1][0],
                               places=6)

    def test_cuatro_aguas_acorta_la_cumbrera(self):
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="cuatro_aguas",
                                   pendiente_pct=30.0, con_qto=False)
        roof = self.context.architecture.list("ROOF",
                                              self.context.project.id)[0]
        largo_cumbrera = abs(roof.ridge[1][0] - roof.ridge[0][0])
        self.assertLess(largo_cumbrera, 8.0 + 2 * roof.alero_m)
        self.assertGreater(largo_cumbrera, 0.0)

    def test_plana_sin_cumbrera_y_con_pendiente_de_evacuacion(self):
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="plana_transitable",
                                   con_qto=False)
        roof = self.context.architecture.list("ROOF",
                                              self.context.project.id)[0]
        self.assertIsNone(roof.ridge)
        self.assertGreater(roof.pendiente_pct, 0.0)
        self.assertLess(roof.pendiente_pct, 5.0)

    def test_un_agua_deja_el_borde_alto_en_un_lado(self):
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="un_agua", con_qto=False)
        roof = self.context.architecture.list("ROOF",
                                              self.context.project.id)[0]
        self.assertIsNotNone(roof.ridge)
        self.assertAlmostEqual(roof.altura_cumbrera_m,
                               (5.0 + 2 * roof.alero_m) * 0.15, places=6)


class TestGeneracion(_ProyectoBase):

    def test_entidad_persistente_al_reabrir(self):
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="dos_aguas", con_qto=False)
        self.context.commit()
        ruta = self.context.db_path
        self.context.close()
        self.context = self.application.open_project(ruta)
        roofs = self.context.architecture.list("ROOF",
                                               self.context.project.id)
        self.assertEqual(len(roofs), 1)
        self.assertEqual(len(roofs[0].footprint), 4)
        self.assertEqual(roofs[0].tipologia, "dos_aguas")

    def test_regenerar_la_cubierta_no_duplica(self):
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="dos_aguas", con_qto=False)
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="cuatro_aguas", con_qto=False)
        roofs = self.context.architecture.list("ROOF",
                                               self.context.project.id)
        self.assertEqual(len(roofs), 1)
        self.assertEqual(roofs[0].tipologia, "cuatro_aguas")

    def test_quitar_cubierta(self):
        cubiertas.generar_cubierta(self.context, None, con_qto=False)
        bajas = cubiertas.quitar_cubierta(self.context)
        self.assertEqual(len(bajas), 1)
        self.assertEqual(len(self.context.architecture.list(
            "ROOF", self.context.project.id)), 0)

    def test_sin_espacios_da_aviso_y_no_falla(self):
        self.arq.create_level("Vacio", 10.0, 3.0)
        _ctx_alt = self.application.create_project(
            self.project_path("cub_vacio.arqgen"), name="Vacio")
        try:
            resumen = cubiertas.generar_cubierta(_ctx_alt, None,
                                                 con_qto=False)
            self.assertEqual(resumen["creados"], [])
            self.assertTrue(resumen["avisos"])
        finally:
            _ctx_alt.close()

    def test_qto_con_roof_area(self):
        from services.quantity_service import QuantityService
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="dos_aguas", con_qto=False)
        QuantityService(self.context).compute_all()
        formulas = {c["formula_code"] for c in
                    self.context.quantities_repo.all(
                        self.context.project.id)}
        self.assertIn("ROOF_AREA", formulas)
        self.assertIn("ROOF_PROJECTED_AREA", formulas)

    def test_replace_plan_incluye_la_cubierta_y_se_purga(self):
        data = bwiz.BuildingWizardData(
            name="Casa Cubierta",
            levels=[bwiz.LevelSpec(name="Planta 1", height_m=3.0)],
            rooms=[bwiz.RoomSpec(name="Sala", space_type="LIVING_ROOM",
                                 width_m=5.0, depth_m=4.0,
                                 level_ref="Planta 1")],
            installations=[])
        data.cubierta_tipologia = "dos_aguas"
        bwiz.replace_plan(data, self.context)
        self.assertEqual(len(self.context.architecture.list(
            "ROOF", self.context.project.id)), 1)
        purga = bwiz.purge_generated(self.context)
        self.assertEqual(purga["diseno_espacios"], 1)
        self.assertEqual(len(self.context.architecture.list(
            "ROOF", self.context.project.id)), 0)


class TestEstimador(ARQGenTestCase):
    """El takeoff paramétrico honra tipología/material y añade mobiliario
    y barandillas con renglones oficiales."""

    def _data(self, **kw):
        return bwiz.BuildingWizardData(**kw)

    def _variant(self):
        layout = SimpleNamespace(
            level_name="Planta 1",
            all_rooms=[SimpleNamespace(x=0, y=0, w=5, d=4,
                                       space_type="LIVING_ROOM",
                                       area_m2=lambda: 20.0),
                       SimpleNamespace(x=5, y=0, w=4, d=4,
                                       space_type="BEDROOM",
                                       area_m2=lambda: 16.0),
                       SimpleNamespace(x=0, y=4, w=2, d=2,
                                       space_type="STAIR",
                                       area_m2=lambda: 4.0)],
            walls=[], doors=[], windows=[],
            total_area_m2=lambda: 40.0)
        return SimpleNamespace(layouts=[layout], key="k", title="t",
                               score=1.0, metrics={})

    def test_por_defecto_mantiene_impermeabilizacion(self):
        filas = vbudget.variant_takeoff(self._data(), self._variant())
        cub = [f for f in filas if f["code"] == "110120"]
        self.assertEqual(len(cub), 1)

    def test_teja_a_dos_aguas_usa_el_renglon_126211(self):
        filas = vbudget.variant_takeoff(
            self._data(cubierta_tipologia="dos_aguas",
                       cubierta_pendiente_pct=30.0), self._variant())
        teja = [f for f in filas if f["code"] == "126211"]
        self.assertEqual(len(teja), 1)
        # el nivel superior suma salón + dormitorio + escalera = 40 m2
        esperado = 40.0 * math.sqrt(1.0 + 0.09)
        self.assertAlmostEqual(teja[0]["quantity"], esperado, places=2)

    def test_chapa_a_un_agua_usa_el_renglon_124151(self):
        filas = vbudget.variant_takeoff(
            self._data(cubierta_tipologia="un_agua"), self._variant())
        self.assertTrue(any(f["code"] == "124151" for f in filas))

    def test_mobiliario_y_barandillas_en_el_estimador(self):
        filas = vbudget.variant_takeoff(self._data(), self._variant())
        closet = [f for f in filas if f["code"] == "072411"]
        self.assertEqual(len(closet), 1)
        self.assertAlmostEqual(closet[0]["quantity"], 4.32, places=2)
        baranda = [f for f in filas if f["code"] == "094211"]
        self.assertEqual(len(baranda), 1)
        self.assertAlmostEqual(baranda[0]["quantity"], 4.0, places=2)

    def test_mobiliario_apagado_no_aporta_renglones(self):
        filas = vbudget.variant_takeoff(self._data(mobiliario=False),
                                        self._variant())
        self.assertFalse(any(f["code"] == "072411" for f in filas))

    def test_estimador_precia_con_reglas_oficiales(self):
        from app.paths import resource_path
        from engines.precons_engine import PreconsRuleset
        ruleset = PreconsRuleset.from_file(resource_path(
            "rulesets", "precons_iii_rospres_330.json"))
        data = self._data(cubierta_tipologia="dos_aguas",
                          cubierta_pendiente_pct=30.0)
        coste = vbudget.estimate_variant_cost(data, self._variant(),
                                              ruleset)
        tejas = [r for r in coste.rows if r["code"] == "126211"]
        self.assertEqual(len(tejas), 1)
        self.assertGreater(tejas[0]["amount"], 0.0)
        # el renglón de teja sale PRECIADO con el total oficial
        oficial = ruleset.official_price("126211")
        self.assertAlmostEqual(tejas[0]["unit_price"],
                               float(oficial.get("total", 0.0)), places=2)


class Test3DYMensajes(_ProyectoBase):

    def test_caras_3d_para_las_tipologias(self):
        from ui import view3d as v3
        from domain.model import Roof
        cam = v3.Camara3D()
        nivel = v3.Nivel3D("n1", "Planta 1", 0.0, 3.0)
        for tipologia, ridge in (
                # dos aguas: cumbrera hasta el alero en los extremos
                ("dos_aguas", ((-0.6, 2.5), (8.6, 2.5))),
                # cuatro aguas: cumbrera acortada (hips en los extremos)
                ("cuatro_aguas", ((2.0, 2.5), (6.0, 2.5))),
                # un agua: el borde ALTO es un borde del alero
                ("un_agua", ((-0.6, 5.6), (-0.6, -0.6))),
                ("plana_transitable", None)):
            roof = Roof(project_id="p", code="ARQ-ROOF-009",
                        tipologia=tipologia, material="teja_curva",
                        pendiente_pct=30.0, alero_m=0.6,
                        altura_cumbrera_m=0.6,
                        footprint=[(-0.6, -0.6), (8.6, -0.6), (8.6, 5.6),
                                   (-0.6, 5.6)],
                        ridge=ridge)
            caras = v3.caras_de_cubierta(roof, nivel, 0.0, cam)
            self.assertTrue(any(c.kind == "cubierta" for c in caras),
                            tipologia)
            if tipologia == "plana_transitable":
                self.assertTrue(any(c.kind == "parapeto" for c in caras))
            if tipologia == "dos_aguas":
                self.assertTrue(any(c.kind == "fronton" for c in caras))

    def test_png_3d_con_cubierta_y_mobiliario(self):
        import os
        import tempfile
        from ui import view3d as v3
        cubiertas.generar_cubierta(self.context, None,
                                   tipologia="dos_aguas", con_qto=False)
        modelo2, _av2 = v3.modelo3d_desde_proyecto(self.context)
        caras = v3.construir_caras(modelo2, v3.Camara3D())
        self.assertTrue(any(c.kind == "cubierta" for c in caras))
        ruta = os.path.join(tempfile.mkdtemp(), "cub.png")
        v3.export_vista3d_png(caras, v3.Camara3D(), ruta, titulo="cub")
        with open(ruta, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")

    def test_resumen_texto_es_cp1252(self):
        resumen = {"operacion": "cubierta", "creados": ["ARQ-ROOF-001"],
                   "eliminados": [], "avisos": [], "qto": None,
                   "parametros": {"tipologia": "dos_aguas",
                                  "material": "teja_curva",
                                  "pendiente_pct": 30.0,
                                  "alero_m": 0.6,
                                  "estructura": "madera"},
                   "superficie": {"area_proyectada": 60.0,
                                  "area_inclinada": 62.6,
                                  "perimetro": 32.0}}
        cubiertas.resumen_texto(resumen).encode("cp1252")

    def test_resumen_sin_parametros_no_falla(self):
        cubiertas.resumen_texto({"operacion": "cubierta",
                                 "creados": [], "avisos": ["vacío"]})


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoCubiertas(_ProyectoBase):

    def test_dialogo_cubre_y_quita(self):
        from ui.app_window import ARQGenWindow
        self.arq = ArchitectureService(self.context)
        nivel = self.arq.create_level("Planta GUI", 0.0, 3.0)
        self.arq.create_space(nivel.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (5, 0), (5, 4), (0, 4)])
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            # seleccionar dos aguas explícito
            valores = list(state["combo_tip"]["values"])
            state["combo_tip"].current(valores.index("dos_aguas"))
            dialogo._diseno_cubierta_generar()
            self.assertEqual(len(self.context.architecture.list(
                "ROOF", self.context.project.id)), 1)
            dialogo._diseno_cubierta_quitar()
            self.assertEqual(len(self.context.architecture.list(
                "ROOF", self.context.project.id)), 0)
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
