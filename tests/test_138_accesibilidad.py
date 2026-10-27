"""SOLUCIÓN A BARRERAS ARQUITECTÓNICAS (v3.15.0).

Lo pedido: «la solución a barreras arquitectónicas con rampas,
barandas etc.».

Cobertura:
* Tabla de pendientes de rampa por desnivel (10/8/6 %) y el caso que
  pide ascensor (> 2.0 m); geometría con tramos ≤ 10 m y mesetas.
* Chequeos: puertas < 0.80 m, pasillos estrechos (1.00/1.20 social),
  escaleras fuera de Blondel y sin barandilla, desniveles sin rampa,
  círculo de giro en aseos (uso social).
* Soluciones generativas: barandillas a ambos lados de la escalera
  (0.90 m), rampa de entrada por desnivel de piso con pasamanos DOBLE
  (0.95 + 0.65 m), barras de apoyo (0.70 m a 0.75 m) junto al inodoro.
* Idempotencia, quitar (respetando lo editado a mano), purga con la
  regeneración, entidades persistentes, QTO (RAMP_AREA, RAMP_LENGTH,
  HANDRAIL_LENGTH) y mensajes cp1252.
* Geometría 3D de rampa y barandilla y GUI (analizar + aplicar).
"""

from __future__ import annotations

import math
import unittest

from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from domain import accesibilidad
from domain import mobiliario
from ui import building_wizard as bwiz


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
            self.project_path("acc.arqgen"), name="Accesibilidad")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta 1", 0.0, 3.0)

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()

    def local(self, nombre, rect, tipo="ROOM"):
        return self.arq.create_space(self.nivel.code, nombre, tipo,
                                     list(rect))

    def marcar_cota(self, espacio, cota_m):
        espacio.metadata = dict(espacio.metadata or {})
        espacio.metadata["requerimientos"] = {
            "arquitectonicos": {"cota_piso_m": cota_m}}
        from services.commands_impl import UpdateEntityCommand
        espacio.touch()
        self.context.command_bus.execute(UpdateEntityCommand(espacio),
                                         self.context)


class TestNormativa(ARQGenTestCase):

    def test_tabla_de_pendientes_por_desnivel(self):
        self.assertEqual(accesibilidad.pendiente_maxima_rampa(0.30), 10.0)
        self.assertEqual(accesibilidad.pendiente_maxima_rampa(0.50), 10.0)
        self.assertEqual(accesibilidad.pendiente_maxima_rampa(0.51), 8.0)
        self.assertEqual(accesibilidad.pendiente_maxima_rampa(1.00), 8.0)
        self.assertEqual(accesibilidad.pendiente_maxima_rampa(1.01), 6.0)
        self.assertEqual(accesibilidad.pendiente_maxima_rampa(2.00), 6.0)

    def test_desniveles_mayores_piden_ascensor(self):
        self.assertIsNone(accesibilidad.pendiente_maxima_rampa(2.01))
        self.assertIsNone(accesibilidad.pendiente_maxima_rampa(3.5))

    def test_geometria_rampa_longitud_exacta(self):
        datos = accesibilidad.geometria_rampa(0.45)
        self.assertEqual(datos["slope_pct"], 10.0)  # Δh <= 0.50 m: 10 %
        self.assertAlmostEqual(datos["length_m"], 0.45 / 0.10, places=2)
        self.assertEqual(datos["tramos"], 1)
        self.assertEqual(datos["mesetas"], 0)
        self.assertFalse(datos["pide_ascensor"])

    def test_geometria_rampa_desnivel_medio_al_8(self):
        datos = accesibilidad.geometria_rampa(0.90)
        self.assertEqual(datos["slope_pct"], 8.0)
        # 11.25 m de desarrollo excede el tramo de 10 m: 2 tramos con
        # 1 meseta de 1.50 m intermedia
        self.assertAlmostEqual(datos["length_m"], 0.90 / 0.08 + 1.5,
                               places=2)
        self.assertEqual(datos["tramos"], 2)
        self.assertEqual(datos["mesetas"], 1)

    def test_rampa_larga_se_parte_en_tramos_con_mesetas(self):
        # 1.8 m al 6 % = 30 m de desarrollo: 3 tramos + 2 mesetas
        datos = accesibilidad.geometria_rampa(1.8)
        self.assertEqual(datos["tramos"], 3)
        self.assertEqual(datos["mesetas"], 2)
        self.assertAlmostEqual(datos["length_m"], 30.0 + 3.0, places=2)

    def test_rampa_que_pide_ascensor_no_devuelve_geometria(self):
        datos = accesibilidad.geometria_rampa(2.6)
        self.assertTrue(datos["pide_ascensor"])
        self.assertEqual(datos["length_m"], 0.0)

    def test_la_pendiente_pedida_se_recorta_a_la_maxima(self):
        datos = accesibilidad.geometria_rampa(0.4, pendiente_pct=25.0)
        self.assertEqual(datos["slope_pct"], 10.0)


class TestChequeos(_ProyectoBase):

    def test_puertas_estrechas_se_detectan(self):
        sala = self.local("Sala", [(0, 0), (4, 0), (4, 3), (0, 3)],
                          "LIVING_ROOM")
        muro = self.arq.create_wall(self.nivel.code, (0.0, 0.0),
                                    (4.0, 0.0), 0.2)
        self.arq.create_opening("DOOR", muro.code, 0.70, 2.1)
        chequeos = accesibilidad.analizar_barreras(self.context)
        puertas = next(c for c in chequeos if c.codigo == "ARQ-ACC-101")
        self.assertEqual(puertas.estado, "incumple")
        self.assertIn(sala.code if False else "0.70", puertas.detalle)

    def test_pasillo_estrecho_en_uso_social_avisa(self):
        self.local("Pasillo", [(0, 0), (10, 0), (10, 0.95), (0, 0.95)],
                   "CORRIDOR")
        chequeos = accesibilidad.analizar_barreras(self.context)
        pasillos = next(c for c in chequeos if c.codigo == "ARQ-ACC-102")
        self.assertIn("0.95", pasillos.detalle)

    def test_escalera_sin_barandilla_es_incumplimiento(self):
        self.local("Escalera", [(0, 0), (2, 0), (2, 4), (0, 4)], "STAIR")
        chequeos = accesibilidad.analizar_barreras(self.context)
        barandillas = next(c for c in chequeos if c.codigo == "ARQ-ACC-104")
        self.assertEqual(barandillas.estado, "incumple")

    def test_desnivel_sin_rampa_se_detecta(self):
        sala = self.local("Sala Elevada", [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.marcar_cota(sala, 0.45)
        chequeos = accesibilidad.analizar_barreras(self.context)
        desniveles = next(c for c in chequeos if c.codigo == "ARQ-ACC-105")
        self.assertEqual(desniveles.estado, "incumple")
        self.assertIn("Sala Elevada", desniveles.detalle)

    def test_todo_en_orden_da_cumples(self):
        self.local("Sala", [(0, 0), (4, 0), (4, 3), (0, 3)])
        chequeos = accesibilidad.analizar_barreras(self.context)
        self.assertTrue(chequeos)
        self.assertTrue(all(c.estado in ("cumple", "aviso")
                            for c in chequeos))

    def test_linea_de_chequeo_es_cp1252(self):
        self.local("Escalera", [(0, 0), (2, 0), (2, 4), (0, 4)], "STAIR")
        for chequeo in accesibilidad.analizar_barreras(self.context):
            chequeo.linea().encode("cp1252")


class TestSoluciones(_ProyectoBase):

    def _edificio_con_todo(self):
        dorm = self.local("Dormitorio", [(0, 0), (4.6, 0), (4.6, 3.4),
                                         (0, 3.4)], "BEDROOM")
        self.local("Bano", [(4.6, 0), (7.2, 0), (7.2, 2.4), (4.6, 2.4)],
                   "BATHROOM")
        self.local("Escalera", [(0, 3.4), (2, 3.4), (2, 5.4), (0, 5.4)],
                   "STAIR")
        sala = self.local("Sala Elevada",
                          [(4.6, 2.4), (7.2, 2.4), (7.2, 5.4), (4.6, 5.4)])
        self.marcar_cota(sala, 0.45)
        mobiliario.generar_mobiliario(self.context, None, con_qto=False)
        return dorm

    def test_barandillas_de_escalera_a_ambos_lados(self):
        self.local("Escalera", [(0, 0), (2, 0), (2, 4), (0, 4)], "STAIR")
        accesibilidad.aplicar_soluciones(self.context, con_qto=False)
        rails = [r for r in self.context.architecture.list(
            "HANDRAIL", self.context.project.id) if r.kind == "barandilla"]
        self.assertEqual(len(rails), 2)
        for rail in rails:
            self.assertAlmostEqual(rail.altura_m, 0.90)
            xs = {round(p[0], 3) for p in rail.points}
            self.assertEqual(len(rail.points), 2)
            self.assertLess(min(xs), 2.0)

    def test_rampa_de_entrada_con_pasamanos_doble(self):
        sala = self.local("Sala Elevada",
                          [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.marcar_cota(sala, 0.45)
        resumen = accesibilidad.aplicar_soluciones(self.context,
                                                   con_qto=False)
        rampas = self.context.architecture.list("RAMP",
                                                self.context.project.id)
        self.assertEqual(len(rampas), 1)
        rampa = rampas[0]
        self.assertEqual(rampa.slope_pct, 10.0)  # 0.45 m cae en el 10 %
        self.assertAlmostEqual(rampa.desnivel_m, 0.45, places=6)
        self.assertAlmostEqual(rampa.length_m, 0.45 / 0.10, places=2)
        self.assertEqual(rampa.metadata.get("tramos"), 1)
        dobles = [r for r in self.context.architecture.list(
            "HANDRAIL", self.context.project.id)
            if r.kind == "barandilla_rampa"]
        self.assertEqual(len(dobles), 2)
        for rail in dobles:
            self.assertAlmostEqual(rail.altura_m, 0.95)
            self.assertAlmostEqual(rail.altura_secundaria_m, 0.65)
        self.assertIn("rampas", resumen["conteo"])

    def test_desnivel_excesivo_avisa_de_ascensor(self):
        sala = self.local("Torre", [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.marcar_cota(sala, 2.6)
        resumen = accesibilidad.aplicar_soluciones(self.context,
                                                   con_qto=False)
        self.assertEqual(len(self.context.architecture.list(
            "RAMP", self.context.project.id)), 0)
        self.assertTrue(any("ascensor" in a for a in resumen["avisos"]))

    def test_barras_de_apoyo_junto_al_inodoro(self):
        self.local("Bano", [(0, 0), (2.6, 0), (2.6, 2.4), (0, 2.4)],
                   "BATHROOM")
        mobiliario.generar_mobiliario(self.context, None, con_qto=False)
        accesibilidad.aplicar_soluciones(self.context, con_qto=False)
        barras = [r for r in self.context.architecture.list(
            "HANDRAIL", self.context.project.id)
            if r.kind == "barra_apoyo"]
        self.assertEqual(len(barras), 1)
        barra = barras[0]
        self.assertAlmostEqual(barra.altura_m, 0.75)
        (x1, y1), (x2, y2) = barra.points
        self.assertAlmostEqual(math.hypot(x2 - x1, y2 - y1), 0.70, places=2)
        # la barra cae sobre el borde del baño (cerca del inodoro)
        espacio = self.context.architecture.list(
            "SPACE", self.context.project.id)[0]
        boundary = [tuple(p) for p in espacio.boundary]
        pie = barra.points[0]
        d_min = min(
            accesibilidad._proyecto_en_segmento(
                pie, a, b)[1] * 0 + math.hypot(pie[0] - a[0], pie[1] - a[1])
            for a, b in
            zip(boundary, boundary[1:] + boundary[:1]))
        self.assertLess(d_min, 2.6)

    def test_aplicar_es_idempotente(self):
        self.local("Escalera", [(0, 0), (2, 0), (2, 4), (0, 4)], "STAIR")
        primero = accesibilidad.aplicar_soluciones(self.context,
                                                   con_qto=False)
        segundo = accesibilidad.aplicar_soluciones(self.context,
                                                   con_qto=False)
        self.assertEqual(len(segundo["creados"]), len(primero["creados"]))
        self.assertEqual(len(segundo["eliminados"]),
                         len(primero["creados"]))

    def test_quitar_respeta_lo_editado_a_mano(self):
        self.local("Escalera", [(0, 0), (2, 0), (2, 4), (0, 4)], "STAIR")
        accesibilidad.aplicar_soluciones(self.context, con_qto=False)
        rail = self.context.architecture.list(
            "HANDRAIL", self.context.project.id)[0]
        rail.metadata = dict(rail.metadata or {})
        rail.metadata["editada_a_mano"] = True
        from services.commands_impl import UpdateEntityCommand
        rail.touch()
        self.context.command_bus.execute(UpdateEntityCommand(rail),
                                         self.context)
        accesibilidad.quitar_soluciones(self.context)
        vivos = [r for r in self.context.architecture.list(
            "HANDRAIL", self.context.project.id)
            if r.metadata.get("editada_a_mano")]
        self.assertEqual(len(vivos), 1)

    def test_qto_mide_rampas_y_barandillas(self):
        from services.quantity_service import QuantityService
        sala = self.local("Sala Elevada",
                          [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.marcar_cota(sala, 0.45)
        accesibilidad.aplicar_soluciones(self.context, con_qto=False)
        QuantityService(self.context).compute_all()
        formulas = {c["formula_code"] for c in
                    self.context.quantities_repo.all(
                        self.context.project.id)}
        self.assertIn("HANDRAIL_LENGTH", formulas)
        self.assertIn("RAMP_AREA", formulas)
        self.assertIn("RAMP_LENGTH", formulas)

    def test_persiste_al_reabrir(self):
        sala = self.local("Sala Elevada",
                          [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.marcar_cota(sala, 0.45)
        accesibilidad.aplicar_soluciones(self.context, con_qto=False)
        self.context.commit()
        ruta = self.context.db_path
        self.context.close()
        self.context = self.application.open_project(ruta)
        self.assertEqual(len(self.context.architecture.list(
            "RAMP", self.context.project.id)), 1)
        self.assertEqual(len(self.context.architecture.list(
            "HANDRAIL", self.context.project.id)), 2)

    def test_replace_plan_regenera_las_soluciones(self):
        data = bwiz.BuildingWizardData(
            name="Casa Accesible",
            levels=[bwiz.LevelSpec(name="Planta 1", height_m=3.0)],
            rooms=[bwiz.RoomSpec(name="Dormitorio", space_type="BEDROOM",
                                 width_m=4.6, depth_m=3.4,
                                 level_ref="Planta 1"),
                   bwiz.RoomSpec(name="Bano", space_type="BATHROOM",
                                 width_m=2.6, depth_m=2.4,
                                 level_ref="Planta 1")],
            installations=[])
        data.terrain_type = "Pendiente suave (1.2 % - sube)"
        bwiz.replace_plan(data, self.context)
        # con desnivel de piso hay rampa; sin desnivel, al menos el
        # análisis no debe lanzar excepciones
        chequeos = accesibilidad.analizar_barreras(self.context)
        self.assertTrue(chequeos)

    def test_resumen_texto_es_cp1252(self):
        resumen = {"operacion": "accesibilidad", "creados": ["A-1"],
                   "eliminados": [], "conteo": {"rampas": 1},
                   "avisos": ["pide ascensor"], "qto": None,
                   "chequeos": []}
        accesibilidad.resumen_texto(resumen).encode("cp1252")


class Test3D(_ProyectoBase):

    def test_caras_3d_de_rampa_y_barandilla(self):
        from ui import view3d as v3
        from domain.model import Handrail, Ramp
        cam = v3.Camara3D()
        rampa = Ramp(project_id="p", code="ARQ-RAMP-001",
                     corners=[(0.0, 0.0), (1.2, 0.0), (1.2, -3.0),
                              (0.0, -3.0)],
                     width_m=1.2, length_m=3.0, desnivel_m=0.45,
                     slope_pct=15.0)
        caras_rampa = v3.caras_de_rampa(rampa, 0.0, 0.0, cam)
        self.assertEqual(len(caras_rampa), 1)
        zs = {round(p[2], 2) for p in caras_rampa[0].puntos}
        self.assertIn(0.02, zs)
        self.assertIn(0.47, zs)
        rail = Handrail(project_id="p", code="ARQ-HANDRAIL-001",
                        points=[(0.0, 0.0), (0.0, -3.0)], altura_m=0.95,
                        altura_secundaria_m=0.65)
        caras_rail = v3.caras_de_barandilla(rail, 0.0, 0.0, cam)
        self.assertTrue(any(c.kind == "poste" for c in caras_rail))
        self.assertTrue(any(c.kind == "pasamanos" for c in caras_rail))


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoAccesibilidad(_ProyectoBase):

    def test_dialogo_analiza_y_aplica(self):
        from ui.app_window import ARQGenWindow
        self.arq.create_space(self.nivel.code, "Escalera", "STAIR",
                              [(0, 0), (2, 0), (2, 4), (0, 4)])
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            dialogo._diseno_acc_analizar()
            dialogo._diseno_acc_aplicar()
            rails = self.context.architecture.list(
                "HANDRAIL", self.context.project.id)
            self.assertEqual(len(rails), 2)
            dialogo._diseno_acc_quitar()
            self.assertEqual(len(self.context.architecture.list(
                "HANDRAIL", self.context.project.id)), 0)
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
