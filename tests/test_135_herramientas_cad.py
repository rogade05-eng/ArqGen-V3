"""HERRAMIENTAS DE EDICIÓN TIPO CAD (v3.14.0) — ui/cad_tools.py + panel GUI.

* Motor sin Tk: mover, copiar, reflejar, girar, recortar, alargar,
  chaflán, dividir, estirar y paralela con valores verificados a mano.
* Vanos: viajan rígidos con el muro (offset intacto), se re-proyectan
  al recortar/dividir/estirar y se dan de baja si ya no caben; las
  puertas cambian de mano al reflejar.
* Locales: sus muros EXCLUSIVOS los acompañan; los compartidos con
  otros locales se quedan; las terminales de instalaciones se reanclan
  (baja con cascada + connect_local).
* Lo editado a mano (metadata «editada_a_mano») SOBREVIVE a
  collect_generated/purge_generated igual que lo dibujado a mano.
* Undo persistente restaura la coordenada exacta tras mover.
* GUI: paleta con iconos, máquina de estados por clics (eventos
  fingidos) y asistente de modificaciones con vista previa y aplicar.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.errors import ARQGenError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

import ui.cad_tools as cad

_WIZARD = "asistente de edificación"


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


class _MotorBase(ARQGenTestCase):
    """Proyecto fresco con un nivel y muros de prueba."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("cad.arqgen"), name="CAD")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta CAD", 0.0, 3.0)

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()

    def muro(self, p1, p2, espesor=0.2):
        return self.arq.create_wall(self.nivel.code, p1, p2, espesor)

    def local(self, nombre, rect, tipo="ROOM"):
        return self.arq.create_space(self.nivel.code, nombre, tipo,
                                     list(rect))


class TestMotorMoverCopiar(_MotorBase):

    def test_mover_muro_exacto_con_qto_y_resumen(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0))
        resumen = cad.mover(self.context, [("WALL", muro.id)], 1.5, 2.0)
        cad.finalizar(self.context, resumen)
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertEqual(muro.start, (1.5, 2.0))
        self.assertEqual(muro.end, (6.5, 2.0))
        self.assertTrue(muro.metadata.get(cad.MARCA_MANO))
        self.assertEqual(len(resumen["muros"]), 1)
        self.assertIsNotNone(resumen["qto"])
        self.assertIn("1 muro(s)", cad.texto_resumen(resumen))

    def test_mover_lleva_los_vanos_rigidos(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0))
        puerta = self.arq.create_opening("DOOR", muro.code, 0.9, 2.1,
                                         offset_m=1.0)
        cad.mover(self.context, [("WALL", muro.id)], 2.0, 3.0)
        puerta = cad.resolver(self.context, "DOOR", puerta.id)
        self.assertEqual(puerta.offset_m, 1.0)
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertEqual(muro.start, (2.0, 3.0))

    def test_mover_local_con_muros_exclusivos_y_compartidos(self):
        local_a = self.local("Sala", [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.local("Cocina", [(4, 0), (8, 0), (8, 3), (4, 3)])
        m_abajo = self.muro((0.0, 0.0), (4.0, 0.0))
        m_izq = self.muro((0.0, 0.0), (0.0, 3.0))
        m_arriba = self.muro((0.0, 3.0), (4.0, 3.0))
        m_compartido = self.muro((4.0, 0.0), (4.0, 3.0))
        m_der_b = self.muro((8.0, 0.0), (8.0, 3.0))
        resumen = cad.mover(self.context, [("SPACE", local_a.id)],
                            1.0, 0.5)
        self.assertEqual(cad.resolver(self.context, "WALL",
                                      m_abajo.id).start, (1.0, 0.5))
        self.assertEqual(cad.resolver(self.context, "WALL",
                                      m_izq.id).start, (1.0, 0.5))
        self.assertEqual(cad.resolver(self.context, "WALL",
                                      m_arriba.id).end, (5.0, 3.5))
        # el muro compartido con la Cocina se queda en su sitio
        self.assertEqual(cad.resolver(self.context, "WALL",
                                      m_compartido.id).start, (4.0, 0.0))
        self.assertEqual(cad.resolver(self.context, "WALL",
                                      m_der_b.id).start, (8.0, 0.0))
        local_a = cad.resolver(self.context, "SPACE", local_a.id)
        self.assertEqual(local_a.boundary[0], (1.0, 0.5))
        self.assertTrue(any("compartido" in a for a in resumen["avisos"]))
        # instalaciones reancladas: tablero + luminaria + toma del local
        nodos = [n for n in self.context.installations.list(
            "NODE", self.context.project.id)
            if getattr(n, "space_id", None) == local_a.id]
        self.assertEqual(len(nodos), 3)

    def test_copiar_muro_con_vanos(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0), 0.3)
        self.arq.create_opening("WINDOW", muro.code, 1.2, 1.1,
                                offset_m=2.0, sill_height_m=0.9)
        resumen = cad.copiar(self.context, "WALL", muro.id, 0.0, 4.0)
        self.assertEqual(len(resumen["creados"]), 1)
        self.assertEqual(resumen["vanos"], 1)
        copia = self.context.architecture.get_by_code(
            "WALL", resumen["creados"][0])
        self.assertEqual(copia.start, (0.0, 4.0))
        self.assertEqual(copia.thickness_m, 0.3)
        vanos = cad._vanos_de_muro(self.context, copia.id)
        self.assertEqual(len(vanos), 1)
        self.assertEqual(vanos[0].offset_m, 2.0)
        # el original queda intacto
        self.assertEqual(
            len(cad._vanos_de_muro(self.context, muro.id)), 1)

    def test_copiar_local_poligono(self):
        local = self.local("Estudio", [(0, 0), (3, 0), (3, 2), (0, 2)])
        resumen = cad.copiar(self.context, "SPACE", local.id, 5.0, 0.0)
        copia = self.context.architecture.get_by_code(
            "SPACE", resumen["creados"][0])
        self.assertIn("(copia)", copia.name)
        self.assertEqual(copia.boundary[0], (5.0, 0.0))


class TestMotorReflejarGirar(_MotorBase):

    def test_reflejar_muro_eje_vertical_y_voltea_puerta(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0))
        puerta = self.arq.create_opening("DOOR", muro.code, 0.9, 2.1,
                                         offset_m=0.5, swing="LEFT")
        cad.reflejar(self.context, "WALL", muro.id,
                     (2.5, -1.0), (2.5, 1.0))
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertEqual(muro.start, (5.0, 0.0))
        self.assertEqual(muro.end, (0.0, 0.0))
        puerta = cad.resolver(self.context, "DOOR", puerta.id)
        self.assertEqual(puerta.swing, "RIGHT")
        self.assertEqual(puerta.offset_m, 0.5)

    def test_reflejar_local_conserva_orientacion(self):
        local = self.local("Aula", [(0, 0), (4, 0), (4, 3), (0, 3)])
        cad.reflejar(self.context, "SPACE", local.id,
                     (2.0, 0.0), (2.0, 1.0))
        local = cad.resolver(self.context, "SPACE", local.id)
        # mismos vértices espejados (el orden interno se normaliza)
        self.assertEqual(set(local.boundary),
                         {(4.0, 0.0), (0.0, 0.0), (0.0, 3.0), (4.0, 3.0)})
        self.assertGreater(cad._area_firmada(local.boundary), 0.0)
        self.assertAlmostEqual(local.area_m2(), 12.0, places=6)

    def test_girar_muro_90_grados_exacto(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0))
        cad.girar(self.context, "WALL", muro.id, (0.0, 0.0), 90.0)
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertAlmostEqual(muro.end[0], 0.0, places=9)
        self.assertAlmostEqual(muro.end[1], 5.0, places=9)


class TestMotorRecortarAlargarChaflan(_MotorBase):

    def test_recortar_elimina_vano_fuera_y_conserva_dentro(self):
        muro = self.muro((0.0, 0.0), (6.0, 0.0))
        ventana = self.arq.create_opening("WINDOW", muro.code, 1.2, 1.1,
                                          offset_m=1.0)
        puerta = self.arq.create_opening("DOOR", muro.code, 0.9, 2.1,
                                         offset_m=5.0)
        cuchilla = self.muro((3.0, -1.0), (3.0, 4.0))
        resumen = cad.recortar(self.context, muro.id, cuchilla.id,
                               "inicio")
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertAlmostEqual(muro.end[0], 3.0, places=9)
        self.assertAlmostEqual(muro.length_m, 3.0, places=9)
        self.assertIn(puerta.code, resumen["vanos_eliminados"])
        self.assertRaises(ARQGenError, cad.resolver, self.context,
                          "DOOR", puerta.id)
        ventana = cad.resolver(self.context, "WINDOW", ventana.id)
        self.assertEqual(ventana.offset_m, 1.0)

    def test_recortar_lado_fin(self):
        muro = self.muro((0.0, 0.0), (6.0, 0.0))
        cuchilla = self.muro((2.0, -1.0), (2.0, 4.0))
        cad.recortar(self.context, muro.id, cuchilla.id, "fin")
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertAlmostEqual(muro.start[0], 2.0, places=9)
        self.assertAlmostEqual(muro.length_m, 4.0, places=9)

    def test_alargar_hasta_objetivo(self):
        muro = self.muro((0.0, 0.0), (3.0, 0.0))
        objetivo = self.muro((5.0, -1.0), (5.0, 1.0))
        cad.alargar(self.context, muro.id, objetivo.id, "fin")
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertAlmostEqual(muro.end[0], 5.0, places=9)
        self.assertAlmostEqual(muro.length_m, 5.0, places=9)

    def test_alargar_hacia_atras_es_error(self):
        muro = self.muro((0.0, 0.0), (3.0, 0.0))
        objetivo = self.muro((5.0, -1.0), (5.0, 1.0))
        with self.assertRaises(ARQGenError) as ctx_err:
            cad.alargar(self.context, muro.id, objetivo.id, "inicio")
        self.assertEqual(ctx_err.exception.code, "ARQ-CAD-004")

    def test_chaflan_90_exacto_con_muro_de_union(self):
        a = self.muro((0.0, 0.0), (4.0, 0.0))
        b = self.muro((4.0, 0.0), (4.0, 3.0))
        resumen = cad.chaflan(self.context, a.id, b.id, 0.5)
        a = cad.resolver(self.context, "WALL", a.id)
        b = cad.resolver(self.context, "WALL", b.id)
        self.assertAlmostEqual(a.end[0], 3.5, places=9)
        self.assertAlmostEqual(b.start[1], 0.5, places=9)
        self.assertEqual(len(resumen["creados"]), 1)
        union = self.context.architecture.get_by_code(
            "WALL", resumen["creados"][0])
        self.assertAlmostEqual(union.start[0], 3.5, places=9)
        self.assertAlmostEqual(union.end[1], 0.5, places=9)
        self.assertEqual(len(self.context.architecture.list(
            "WALL", self.context.project.id)), 3)

    def test_chaflan_entre_paralelos_es_error(self):
        a = self.muro((0.0, 0.0), (4.0, 0.0))
        b = self.muro((0.0, 2.0), (4.0, 2.0))
        with self.assertRaises(ARQGenError) as ctx_err:
            cad.chaflan(self.context, a.id, b.id, 0.5)
        self.assertEqual(ctx_err.exception.code, "ARQ-CAD-005")


class TestMotorDividirEstirarParalela(_MotorBase):

    def test_dividir_rehospeda_el_vano_de_la_segunda_mitad(self):
        muro = self.muro((0.0, 0.0), (8.0, 0.0))
        puerta = self.arq.create_opening("DOOR", muro.code, 0.9, 2.1,
                                         offset_m=5.0)
        resumen = cad.dividir(self.context, muro.id, (4.0, 0.0))
        self.assertEqual(len(resumen["creados"]), 1)
        nuevo = self.context.architecture.get_by_code(
            "WALL", resumen["creados"][0])
        self.assertAlmostEqual(nuevo.start[0], 4.0, places=9)
        self.assertAlmostEqual(nuevo.length_m, 4.0, places=9)
        puerta = cad.resolver(self.context, "DOOR", puerta.id)
        self.assertEqual(puerta.wall_id, nuevo.id)
        self.assertAlmostEqual(puerta.offset_m, 1.0, places=9)
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertAlmostEqual(muro.length_m, 4.0, places=9)
        self.assertEqual(len(cad._vanos_de_muro(self.context, muro.id)), 0)

    def test_dividir_punto_fuera_es_error(self):
        muro = self.muro((0.0, 0.0), (8.0, 0.0))
        with self.assertRaises(ARQGenError) as ctx_err:
            cad.dividir(self.context, muro.id, (9.0, 0.0))
        self.assertEqual(ctx_err.exception.code, "ARQ-CAD-006")

    def test_estirar_fin_y_inicio_reproyectan_vanos(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0))
        ventana = self.arq.create_opening("WINDOW", muro.code, 1.2, 1.1,
                                          offset_m=3.5)
        cad.estirar(self.context, muro.id, "fin", (7.0, 0.0))
        ventana = cad.resolver(self.context, "WINDOW", ventana.id)
        self.assertEqual(ventana.offset_m, 3.5)
        cad.estirar(self.context, muro.id, "inicio", (-1.0, 0.0))
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertAlmostEqual(muro.length_m, 8.0, places=9)
        ventana = cad.resolver(self.context, "WINDOW", ventana.id)
        self.assertAlmostEqual(ventana.offset_m, 4.5, places=9)

    def test_paralela_izquierda_positiva_con_vanos(self):
        muro = self.muro((0.0, 0.0), (5.0, 0.0))
        self.arq.create_opening("WINDOW", muro.code, 1.2, 1.1,
                                offset_m=2.0)
        resumen = cad.paralela(self.context, muro.id, 2.0)
        copia = self.context.architecture.get_by_code(
            "WALL", resumen["creados"][0])
        self.assertEqual(copia.start, (0.0, 2.0))
        self.assertEqual(copia.end, (5.0, 2.0))
        self.assertEqual(len(cad._vanos_de_muro(self.context, copia.id)), 1)
        paralela_neg = cad.paralela(self.context, muro.id, -1.0)
        copia2 = self.context.architecture.get_by_code(
            "WALL", paralela_neg["creados"][0])
        self.assertEqual(copia2.start, (0.0, -1.0))


class TestSupervivenciaYUndo(_MotorBase):

    def _entidad_generada(self):
        """Local y muros con marca de origen del asistente."""
        local = self.local("Dormitorio", [(0, 0), (4, 0), (4, 3), (0, 3)])
        local.metadata = {"requerimientos": {"origen": _WIZARD + " v2.1.0"}}
        self.context.architecture.save(local)
        muros = []
        for p1, p2 in (((0, 0), (4, 0)), ((4, 0), (4, 3)),
                       ((4, 3), (0, 3)), ((0, 3), (0, 0))):
            muro = self.muro(p1, p2)
            muro.metadata = {"origen": _WIZARD, "portante": True}
            self.context.architecture.save(muro)
            muros.append(muro)
        return local, muros

    def test_lo_editado_a_mano_sobrevive_a_la_regeneracion(self):
        from ui import building_wizard as bwiz
        local, muros = self._entidad_generada()
        colecta = bwiz.collect_generated(self.context)
        self.assertEqual(len(colecta["WALL"]), 4)
        self.assertIn(local.id, colecta["SPACE"])
        # el usuario mueve UN muro: él sobrevive, el resto sigue siendo
        # generado y la purga se lo lleva
        cad.mover(self.context, [("WALL", muros[0].id)], 0.5, 0.0)
        colecta = bwiz.collect_generated(self.context)
        self.assertNotIn(muros[0].id, colecta["WALL"])
        self.assertIn(muros[1].id, colecta["WALL"])
        bwiz.purge_generated(self.context)
        vivos = {w.id for w in self.context.architecture.list(
            "WALL", self.context.project.id)}
        self.assertEqual(vivos, {muros[0].id})
        # el local NO se tocó: sigue siendo generado y la purga lo baja
        self.assertEqual(len(self.context.architecture.list(
            "SPACE", self.context.project.id)), 0)

    def test_mover_el_local_marca_todos_sus_muros_exclusivos(self):
        from ui import building_wizard as bwiz
        local, muros = self._entidad_generada()
        cad.mover(self.context, [("SPACE", local.id)], 0.0, 1.0)
        colecta = bwiz.collect_generated(self.context)
        # el local y sus 4 muros exclusivos viajaron con él: nada se purga
        self.assertEqual(colecta["WALL"], [])
        self.assertNotIn(local.id, colecta["SPACE"])
        bwiz.purge_generated(self.context)
        self.assertEqual(len(self.context.architecture.list(
            "WALL", self.context.project.id)), 4)
        local = cad.resolver(self.context, "SPACE", local.id)
        self.assertEqual(local.boundary[0], (0.0, 1.0))

    def test_undo_persistente_restaura_el_muro(self):
        from app.undo_service import PersistentUndoService
        muro = self.muro((1.0, 1.0), (6.0, 1.0))
        self.context.commit()
        cad.mover(self.context, [("WALL", muro.id)], 1.0, 0.5)
        self.context.commit()
        resumen_undo = PersistentUndoService(self.context).undo()
        self.assertTrue(resumen_undo.get("ok", True), resumen_undo)
        muro = cad.resolver(self.context, "WALL", muro.id)
        self.assertEqual(muro.start, (1.0, 1.0))

    def test_errores_amables(self):
        with self.assertRaises(ARQGenError) as ctx_err:
            cad.resolver(self.context, "WALL", "WALL-NOEXISTE")
        self.assertEqual(ctx_err.exception.code, "ARQ-CAD-001")
        muro = self.muro((0.0, 0.0), (1.0, 0.0))
        with self.assertRaises(ARQGenError) as ctx_err:
            cad.mover(self.context, [("WALL", muro.id)], 0.0, 0.0)
        self.assertEqual(ctx_err.exception.code, "ARQ-CAD-002")

    def test_mensajes_cp1252(self):
        muro = self.muro((0.0, 0.0), (2.0, 0.0))
        resumen = cad.mover(self.context, [("WALL", muro.id)], 1.0, 1.0)
        texto = cad.texto_resumen(resumen)
        texto.encode("cp1252")  # no debe lanzar (disciplina v3.13.1)


class TestPanelYAsistenteGUI(ARQGenTestCase):
    """Paleta con iconos, máquina de estados y asistente de
    modificaciones, con ventana Tk real (Xvfb en CI)."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("cad_gui.arqgen"), name="CAD GUI")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta", 0.0, 3.0)
        self.muro_a = self.arq.create_wall(self.nivel.code,
                                           (0.0, 0.0), (6.0, 0.0), 0.2)
        self.muro_b = self.arq.create_wall(self.nivel.code,
                                           (6.0, 0.0), (6.0, 4.0), 0.2)
        self.context.commit()

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def _clic(self, window, x, y):
        w = max(window.canvas.winfo_width(), 800)
        h = max(window.canvas.winfo_height(), 600)
        sx, sy = window.viewport.to_screen(x, y, w, h)
        window._cad_click(SimpleNamespace(x=sx, y=sy))

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_paleta_abre_y_cancela(self):
        window = self._ventana()
        window.open_cad_palette()
        dialog = window._cad_palette
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(len(dialog._cad_botones),
                         len(cad.HERRAMIENTAS))
        window._cad_set_tool("mover")
        self.assertEqual(window._cad_estado()["tool"], "mover")
        window._cad_set_tool("mover")  # el mismo botón desactiva
        self.assertIsNone(window._cad_estado()["tool"])
        window._cad_set_tool("recortar")
        window._cad_cancelar()
        self.assertIsNone(window._cad_estado()["tool"])
        dialog.destroy()

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_flujo_mover_por_clics(self):
        window = self._ventana()
        window.open_cad_palette()
        window._cad_set_tool("mover")
        window.viewport.center_x, window.viewport.center_y = 3.0, 0.0
        window.viewport.scale = 40.0
        window.redraw()
        self._clic(window, 3.0, 0.0)          # sobre el muro A
        self.assertEqual(window._cad_estado()["ref"],
                         ("WALL", self.muro_a.id))
        self._clic(window, 3.0, 0.0)          # punto base
        self._clic(window, 4.0, 1.0)          # punto destino
        muro = cad.resolver(self.context, "WALL", self.muro_a.id)
        self.assertAlmostEqual(muro.start[0], 1.0, places=9)
        self.assertAlmostEqual(muro.start[1], 1.0, places=9)
        self.assertIn("mover", window.status_var.get())

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_asistente_modificaciones_mover_y_preview(self):
        window = self._ventana()
        window.open_mod_wizard()
        dialog = window._mod_dialog
        dialog._mod_elegir(self.muro_a.id)
        self.assertEqual(dialog._mod_state["uid"], self.muro_a.id)
        window._mod_campos["dx"].set("2.0")
        window._mod_campos["dy"].set("0.5")
        self.assertGreater(len(dialog._mod_canvas.find_all()), 0)
        dialog._mod_aplicar()
        muro = cad.resolver(self.context, "WALL", self.muro_a.id)
        self.assertAlmostEqual(muro.start[0], 2.0, places=9)
        self.assertAlmostEqual(muro.start[1], 0.5, places=9)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_asistente_chaflan_con_vista_previa(self):
        window = self._ventana()
        window.open_mod_wizard()
        dialog = window._mod_dialog
        dialog._mod_elegir(self.muro_a.id)
        dialog._mod_op_var.set("Chaflán")
        window._mod_pinta_params()
        window._mod_campos["otro"].set(self.muro_b.code)
        window._mod_campos["distancia"].set("0.4")
        dialog._mod_preview()
        self.assertIn("chaflan", dialog._mod_resultado.get())
        dialog._mod_aplicar()
        muros = self.context.architecture.list("WALL",
                                               self.context.project.id)
        self.assertEqual(len(muros), 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
