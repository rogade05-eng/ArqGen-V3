"""MOBILIARIO SEGÚN EL TEMA Y EL USO SOCIAL/DOMÉSTICO (v3.15.0).

Lo pedido: «vamos a introducir el tema del mobiliario, según el tema y
uso social y/o doméstico. será vital para concebir los espacios».

Cobertura:
* Catálogo: piezas con ámbito (doméstico/social/ambos) y dimensiones
  positivas; cobertura de los tipos de local habituales.
* Reglas por uso: dormitorio lleva cama, baño lleva inodoro y lavabo,
  despacho lleva mesa de despacho; el área manda (dormitorio pequeño
  cambia a cama individual); la densidad añade/quita cómodas.
* Colocación determinista, dentro del recinto, sin choques y con
  avisos de paso estrecho frente a frente (0.75 doméstico).
* Generación en el proyecto: entidades FURNITURE reales (códigos
  ARQ-FURNITURE-nnn), idempotente, persistente al reabrir, con undo
  persistente y QTO (FURNITURE_COUNT/FURNITURE_AREA).
* Regeneración: lo generado se purga y re-crea con replace_plan; lo
  editado a mano (metadata editada_a_mano) SOBREVIVE.
* Ámbito por uso social: Vivienda → doméstico; resto → social.
* Mensajes 100 % codificables en cp1252 y GUI (diálogo con ganchos).
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.errors import ARQGenError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from domain import mobiliario
from domain.diseno_base import bbox_de, poligono_rectangulo
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
    """Proyecto fresco con un nivel y locales de prueba."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("mob.arqgen"), name="Mobiliario")
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


class TestCatalogo(ARQGenTestCase):

    def test_todas_las_piezas_tienen_dimensiones_positivas(self):
        for clave, pieza in mobiliario.CATALOGO.items():
            self.assertGreater(pieza.ancho_m, 0.0, clave)
            self.assertGreater(pieza.fondo_m, 0.0, clave)
            self.assertGreater(pieza.alto_m, 0.0, clave)
            self.assertIn(pieza.ambito, ("domestico", "social", "ambos"),
                          clave)

    def test_hay_piezas_domesticas_y_sociales(self):
        ambitos = {p.ambito for p in mobiliario.CATALOGO.values()}
        self.assertIn("domestico", ambitos)
        self.assertIn("social", ambitos)
        self.assertIn("ambos", ambitos)

    def test_reglas_para_los_usos_habituales(self):
        for space_type in ("BEDROOM", "LIVING_ROOM", "DINING_ROOM",
                           "KITCHEN", "BATHROOM", "OFFICE", "CLASSROOM",
                           "WAITING_ROOM", "CONSULTATION_ROOM", "ROOM"):
            self.assertTrue(mobiliario.REGLAS.get(space_type),
                            f"sin reglas para {space_type}")

    def test_los_especiales_del_trazado_no_se_amueblan(self):
        for space_type in ("CORRIDOR", "PATIO", "STAIR", "CORE"):
            self.assertEqual(mobiliario.REGLAS.get(space_type), None)


class TestReglasYAmbito(ARQGenTestCase):

    def test_ambito_auto_vivienda_es_domestico(self):
        self.assertEqual(mobiliario.ambito_auto("Vivienda"), "domestico")

    def test_ambito_auto_institucional_es_social(self):
        for uso in ("Oficina", "Hospital", "Escuela primaria",
                    "Comedor social", "Local comercial"):
            self.assertEqual(mobiliario.ambito_auto(uso), "social", uso)

    def test_dormitorio_pequeno_cambia_a_cama_individual(self):
        reglas = mobiliario.proponer_piezas("BEDROOM", 7.0)
        claves = [r.clave for r in reglas]
        self.assertNotIn("cama_doble", claves)
        self.assertIn("cama_individual", claves)

    def test_densidad_compacta_quita_las_comodas(self):
        estandar = [r.clave for r in
                    mobiliario.proponer_piezas("BEDROOM", 14.0,
                                               densidad="estandar")]
        compacto = [r.clave for r in
                    mobiliario.proponer_piezas("BEDROOM", 14.0,
                                               densidad="compacto")]
        self.assertIn("armario", estandar)
        self.assertNotIn("armario", compacto)

    def test_ambito_social_excluye_piezas_domesticas(self):
        # el sofá es doméstico: en tema social un salón genérico no lo
        # pide (las reglas de LIVING_ROOM lo filtran por ámbito)
        piezas, _avisos = mobiliario.colocar_en_local(
            SimpleNamespace(
                name="Sala", code="S1", space_type="LIVING_ROOM",
                boundary=[(0, 0), (5, 0), (5, 4), (0, 4)],
                area_m2=lambda: 20.0),
            mobiliario.proponer_piezas("LIVING_ROOM", 20.0,
                                       ambito="social"),
            "social", "amplio")
        self.assertNotIn("sofa", [p["kind"] for p in piezas])


class TestColocacion(_ProyectoBase):

    def test_colocacion_determinista(self):
        espacio = self.local("Dormitorio",
                             [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)],
                             "BEDROOM")
        reglas = mobiliario.proponer_piezas("BEDROOM", 15.6,
                                            ambito="domestico")
        piezas_a, _ = mobiliario.colocar_en_local(espacio, reglas,
                                                  "domestico", "estandar")
        piezas_b, _ = mobiliario.colocar_en_local(espacio, reglas,
                                                  "domestico", "estandar")
        self.assertEqual([(p["kind"], p["x"], p["y"]) for p in piezas_a],
                         [(p["kind"], p["x"], p["y"]) for p in piezas_b])

    def test_todas_las_piezas_caben_dentro_del_recinto(self):
        espacio = self.local("Sala", [(0, 0), (5.5, 0), (5.5, 4), (0, 4)],
                             "LIVING_ROOM")
        reglas = mobiliario.proponer_piezas("LIVING_ROOM", 22.0,
                                            ambito="domestico",
                                            densidad="amplio")
        piezas, _ = mobiliario.colocar_en_local(espacio, reglas,
                                                "domestico", "amplio")
        recinto = bbox_de(espacio.boundary)
        self.assertGreater(len(piezas), 2)
        for pieza in piezas:
            # AABB real de la pieza (el giro de 90/180/270 intercambia
            # ancho y fondo, igual que hace el motor)
            a_lo_largo = abs(pieza["rot"] % 180.0) <= 1e-9
            ancho = pieza["w"] if a_lo_largo else pieza["d"]
            fondo = pieza["d"] if a_lo_largo else pieza["w"]
            self.assertTrue(
                mobiliario.dentro_de_recinto(
                    poligono_rectangulo(pieza["x"], pieza["y"],
                                        ancho, fondo),
                    recinto),
                f"{pieza['kind']} fuera del recinto")

    def test_piezas_no_se_chocan(self):
        espacio = self.local("Dormitorio",
                             [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)],
                             "BEDROOM")
        reglas = mobiliario.proponer_piezas("BEDROOM", 15.6,
                                            ambito="domestico",
                                            densidad="amplio")
        piezas, _ = mobiliario.colocar_en_local(espacio, reglas,
                                                "domestico", "amplio")
        for i in range(len(piezas)):
            for j in range(i + 1, len(piezas)):
                self.assertFalse(
                    mobiliario.hay_interseccion(piezas[i]["rect"],
                                                piezas[j]["rect"]),
                    f"{piezas[i]['kind']} pisa a {piezas[j]['kind']}")

    def test_bano_pequeno_avisa_de_paso_estrecho(self):
        espacio = self.local("Bano", [(0, 0), (1.8, 0), (1.8, 1.6),
                                      (0, 1.6)], "BATHROOM")
        reglas = mobiliario.proponer_piezas("BATHROOM", 2.88,
                                            ambito="domestico",
                                            densidad="amplio")
        _piezas, avisos = mobiliario.colocar_en_local(espacio, reglas,
                                                      "domestico", "amplio")
        self.assertTrue(any("Paso" in a for a in avisos), avisos)


class TestGeneracion(_ProyectoBase):

    def test_generar_crea_entidades_con_codigo_y_metadata(self):
        self.local("Dormitorio", [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)],
                   "BEDROOM")
        resumen = mobiliario.generar_mobiliario(self.context, None,
                                                con_qto=False)
        self.assertGreater(len(resumen["creados"]), 0)
        piezas = self.context.architecture.list(
            "FURNITURE", self.context.project.id)
        self.assertGreater(len(piezas), 0)
        for pieza in piezas:
            self.assertTrue(pieza.code.startswith("ARQ-FURNITURE-"),
                            pieza.code)
            self.assertEqual(str(pieza.metadata.get("origen", ""))[:7],
                             "diseño ")
            self.assertIn("categoria", pieza.metadata)

    def test_generar_es_idempotente(self):
        self.local("Oficina", [(0, 0), (4, 0), (4, 3), (0, 3)], "OFFICE")
        primero = mobiliario.generar_mobiliario(self.context, None,
                                                con_qto=False)
        segundo = mobiliario.generar_mobiliario(self.context, None,
                                                con_qto=False)
        self.assertEqual(len(segundo["creados"]), len(primero["creados"]))
        self.assertEqual(len(segundo["eliminados"]),
                         len(primero["creados"]))
        self.assertEqual(len(self.context.architecture.list(
            "FURNITURE", self.context.project.id)), len(primero["creados"]))

    def test_qto_cuenta_el_mobiliario(self):
        from services.quantity_service import QuantityService
        self.local("Dormitorio", [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)],
                   "BEDROOM")
        resumen = mobiliario.generar_mobiliario(self.context, None)
        self.assertIsNotNone(resumen["qto"])
        _stats = QuantityService(self.context).compute_all()
        cantidades = self.context.quantities_repo.all(
            self.context.project.id)
        formulas = {c["formula_code"] for c in cantidades}
        self.assertIn("FURNITURE_COUNT", formulas)
        self.assertIn("FURNITURE_AREA", formulas)

    def test_ambito_invalido_da_error_amable(self):
        with self.assertRaises(ARQGenError) as ctx_err:
            mobiliario.generar_mobiliario(self.context, None,
                                          ambito="vikingo")
        self.assertEqual(getattr(ctx_err.exception, "code", ""),
                         "ARQ-MOB-001")

    def test_persiste_al_reabrir_el_proyecto(self):
        self.local("Dormitorio", [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)],
                   "BEDROOM")
        primero = mobiliario.generar_mobiliario(self.context, None,
                                                con_qto=False)
        self.context.commit()
        ruta = self.context.db_path
        self.context.close()
        self.context = self.application.open_project(ruta)
        piezas = self.context.architecture.list(
            "FURNITURE", self.context.project.id)
        self.assertEqual(len(piezas), len(primero["creados"]))

    def test_undo_persistente_recupera_el_mobiliario(self):
        from app.undo_service import PersistentUndoService
        self.local("Dormitorio", [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)],
                   "BEDROOM")
        resumen = mobiliario.generar_mobiliario(self.context, None,
                                                con_qto=False)
        self.context.commit()
        self.assertTrue(PersistentUndoService(self.context).undo())
        self.context.commit()
        self.assertEqual(len(self.context.architecture.list(
            "FURNITURE", self.context.project.id)),
            len(resumen["creados"]) - 1)


class TestRegeneracion(_ProyectoBase):

    def _data(self):
        data = bwiz.BuildingWizardData(
            name="Casa Mobiliario", usage_type="Vivienda",
            levels=[bwiz.LevelSpec(name="Planta 1", height_m=3.0)],
            rooms=[bwiz.RoomSpec(name="Dormitorio", space_type="BEDROOM",
                                 width_m=4.6, depth_m=3.4,
                                 level_ref="Planta 1"),
                   bwiz.RoomSpec(name="Bano", space_type="BATHROOM",
                                 width_m=2.6, depth_m=2.4,
                                 level_ref="Planta 1")],
            installations=[])
        return data

    def test_replace_plan_amuebla_la_edificacion(self):
        bwiz.replace_plan(self._data(), self.context)
        piezas = self.context.architecture.list(
            "FURNITURE", self.context.project.id)
        self.assertGreater(len(piezas), 3)
        camas = [p for p in piezas if p.kind == "cama_doble"]
        self.assertEqual(len(camas), 1)

    def test_lo_generado_se_purga_y_recrea_sin_huerfanos(self):
        bwiz.replace_plan(self._data(), self.context)
        antes = len(self.context.architecture.list(
            "FURNITURE", self.context.project.id))
        # segunda pasada: purga y vuelve a crear
        purga = bwiz.purge_generated(self.context)
        self.assertEqual(purga["mobiliario"], antes)
        self.assertEqual(len(self.context.architecture.list(
            "FURNITURE", self.context.project.id)), 0)
        bwiz.replace_plan(self._data(), self.context)
        self.assertEqual(len(self.context.architecture.list(
            "FURNITURE", self.context.project.id)), antes)

    def test_lo_editado_a_mano_sobrevive(self):
        bwiz.replace_plan(self._data(), self.context)
        pieza = self.context.architecture.list(
            "FURNITURE", self.context.project.id)[0]
        pieza.metadata = dict(pieza.metadata or {})
        pieza.metadata["editada_a_mano"] = True
        pieza.x += 0.05
        from services.commands_impl import UpdateEntityCommand
        pieza.touch()
        self.context.command_bus.execute(UpdateEntityCommand(pieza),
                                         self.context)
        bwiz.replace_plan(self._data(), self.context)
        vivos = [p for p in self.context.architecture.list(
            "FURNITURE", self.context.project.id)
            if p.metadata.get("editada_a_mano")]
        self.assertEqual(len(vivos), 1)
        self.assertAlmostEqual(vivos[0].x, pieza.x, places=6)

    def test_preferencias_viajan_en_la_metadata_del_edificio(self):
        data = self._data()
        data.mobiliario_ambito = "social"
        data.mobiliario_densidad = "compacto"
        data.cubierta_tipologia = "dos_aguas"
        bwiz.replace_plan(data, self.context)
        edificio = bwiz._wizard_building(self.context)[0]
        edif = edificio.metadata["edificacion"]
        self.assertEqual(edif["mobiliario"]["ambito"], "social")
        self.assertEqual(edif["mobiliario"]["densidad"], "compacto")
        self.assertEqual(edif["cubierta"]["tipologia"], "dos_aguas")
        data2, _avisos = bwiz.program_from_project(self.context)
        self.assertEqual(data2.mobiliario_ambito, "social")
        self.assertEqual(data2.mobiliario_densidad, "compacto")
        self.assertEqual(data2.cubierta_tipologia, "dos_aguas")

    def test_mobiliario_desactivado_no_genera_nada(self):
        data = self._data()
        data.mobiliario = False
        bwiz.replace_plan(data, self.context)
        self.assertEqual(len(self.context.architecture.list(
            "FURNITURE", self.context.project.id)), 0)


class TestMensajesYGUI(ARQGenTestCase):

    def test_resumen_texto_es_cp1252(self):
        resumen = {"operacion": "mobiliario", "creados": ["A-1"],
                   "eliminados": [], "conteo": {"cama_doble": 1},
                   "avisos": ["paso estrecho"], "qto": {"computed": 1},
                   "ambito": "domestico", "densidad": "estandar"}
        mobiliario.resumen_texto(resumen).encode("cp1252")

    def test_field_names_incluyen_lo_nuevo(self):
        nombres = bwiz.building_field_names()
        for campo in ("mobiliario", "mobiliario_ambito",
                      "mobiliario_densidad", "cubierta_tipologia",
                      "cubierta_material", "cubierta_pendiente_pct",
                      "cubierta_alero_m", "accesibilidad_auto"):
            self.assertIn(campo, nombres)

    def test_step_summary_menciona_lo_nuevo(self):
        data = bwiz.BuildingWizardData()
        texto = bwiz.step_summary(data, None)
        self.assertIn("Mobiliario", texto)
        self.assertIn("Cubierta", texto)
        self.assertIn("Accesibilidad", texto)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoDiseno(_ProyectoBase):

    def test_dialogo_mobiliario_genera_y_quita(self):
        from ui.app_window import ARQGenWindow
        self.arq = ArchitectureService(self.context)
        nivel = self.arq.create_level("Planta GUI", 0.0, 3.0)
        self.arq.create_space(nivel.code, "Dormitorio", "BEDROOM",
                              [(0, 0), (4.6, 0), (4.6, 3.4), (0, 3.4)])
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            dialogo._diseno_mobiliario_generar()
            self.assertGreater(len(self.context.architecture.list(
                "FURNITURE", self.context.project.id)), 0)
            dialogo._diseno_mobiliario_quitar()
            self.assertEqual(len(self.context.architecture.list(
                "FURNITURE", self.context.project.id)), 0)
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
