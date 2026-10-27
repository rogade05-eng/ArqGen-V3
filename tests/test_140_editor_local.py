"""EDITOR PROFUNDO DE LOCALES (v3.16.0) — ui/editor_espacios.py.

* Diagnostico completo: dimensiones, muros exclusivos/compartidos,
  puertas, ventanas, hueco de ventilacion (habitables 1/6 del suelo,
  humedos 1/25) y avisos amables (sin puerta, sin ventana...).
* Acceso: puerta con el ancho del uso, centrada y auditada.
* Ventilacion: ventana con el ancho que pide el deficit; error
  amable si ya ventila o ningun muro tiene sitio.
* Redimensionar: mueve SOLO los muros exclusivos (los compartidos se
  quedan y se avisa), re-proyecta los vanos, re-coloca el mobiliario,
  reancla instalaciones y recalcula QTO. Undo persistente restaura.
* GUI (Xvfb): dialogo con diagnostico y acciones.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.errors import ARQGenError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from ui import cad_tools as cad
from ui import editor_espacios as edi


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


class _LocalBase(ARQGenTestCase):
    """Dos locales contiguos: A (0..4) y B (4..8) comparten el muro x=4."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("editor.arqgen"), name="Editor")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta 1", 0.0, 3.0)
        self.muro_sur_a = self.arq.create_wall(self.nivel.code,
                                               (0.0, 0.0), (4.0, 0.0), 0.2)
        self.muro_oeste = self.arq.create_wall(self.nivel.code,
                                               (0.0, 0.0), (0.0, 3.0), 0.2)
        self.muro_norte_a = self.arq.create_wall(self.nivel.code,
                                                 (0.0, 3.0), (4.0, 3.0),
                                                 0.2)
        self.muro_compartido = self.arq.create_wall(self.nivel.code,
                                                    (4.0, 0.0), (4.0, 3.0),
                                                    0.2)
        self.muro_sur_b = self.arq.create_wall(self.nivel.code,
                                               (4.0, 0.0), (8.0, 0.0), 0.2)
        self.muro_norte_b = self.arq.create_wall(self.nivel.code,
                                                 (4.0, 3.0), (8.0, 3.0),
                                                 0.2)
        self.muro_este_b = self.arq.create_wall(self.nivel.code,
                                                (8.0, 0.0), (8.0, 3.0),
                                                0.2)
        self.local_a = self.arq.create_space(
            self.nivel.code, "Dormitorio", "BEDROOM",
            [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)])
        self.local_b = self.arq.create_space(
            self.nivel.code, "Sala", "LIVING_ROOM",
            [(4.0, 0.0), (8.0, 0.0), (8.0, 3.0), (4.0, 3.0)])

    def tearDown(self) -> None:
        try:
            self.context.close()
        except Exception:  # noqa: BLE001
            pass
        super().tearDown()


class TestDiagnostico(_LocalBase):

    def test_dimensiones_muros_y_avisos(self):
        datos = edi.datos_local(self.context, self.local_a.id)
        self.assertEqual(datos["codigo"], self.local_a.code)
        self.assertEqual(datos["uso"], "BEDROOM")
        self.assertAlmostEqual(datos["ancho_m"], 4.0, places=6)
        self.assertAlmostEqual(datos["fondo_m"], 3.0, places=6)
        self.assertAlmostEqual(datos["area_m2"], 12.0, places=6)
        self.assertIn(self.muro_compartido.code, datos["muros_compartidos"])
        self.assertIn(self.muro_oeste.code, datos["muros_exclusivos"])
        self.assertEqual(datos["puertas"], [])
        self.assertEqual(datos["ventanas"], [])
        self.assertIn("sin puerta de acceso", datos["avisos"])
        self.assertIn("sin ventana", datos["avisos"])

    def test_hueco_necesario_habitable_1_6(self):
        datos = edi.datos_local(self.context, self.local_a.id)
        self.assertAlmostEqual(datos["hueco_necesario_m2"], 2.0, places=6)
        self.assertIn("ventilacion insuficiente", datos["avisos"][1])

    def test_hueco_necesario_humedo_1_25(self):
        bano = self.arq.create_space(
            self.nivel.code, "Bano", "BATHROOM",
            [(0.0, 3.0), (2.0, 3.0), (2.0, 5.0), (0.0, 5.0)])
        datos = edi.datos_local(self.context, bano.id)
        self.assertAlmostEqual(datos["hueco_necesario_m2"], 0.16, places=6)

    def test_ventilacion_suficiente_sin_aviso_de_deficit(self):
        self.arq.create_opening("WINDOW", self.muro_oeste.code, 2.4, 1.2,
                                offset_m=0.5, sill_height_m=1.0)
        datos = edi.datos_local(self.context, self.local_a.id)
        self.assertAlmostEqual(datos["hueco_ventilacion_m2"], 2.88,
                               places=6)
        self.assertTrue(any("ventilacion suficiente" in a
                            for a in datos["avisos"]))

    def test_ancho_de_puerta_por_uso(self):
        self.assertAlmostEqual(edi.ancho_puerta_por_uso("BATHROOM"), 0.8)
        self.assertAlmostEqual(edi.ancho_puerta_por_uso("GARAGE"), 2.5)
        self.assertAlmostEqual(edi.ancho_puerta_por_uso("OFFICE"), 0.9)
        self.assertAlmostEqual(edi.ancho_puerta_por_uso("LOQUESEA"), 0.9)


class TestAcceso(_LocalBase):

    def test_puerta_en_el_muro_pedido_con_ancho_del_uso(self):
        resumen = edi.crear_acceso(self.context, self.local_a.id,
                                   muro_ref=self.muro_oeste.code)
        puertas = [e for e in self.context.architecture.list(
            "DOOR", self.context.project.id)]
        self.assertEqual(len(puertas), 1)
        puerta = puertas[0]
        self.assertAlmostEqual(puerta.width_m, 0.9, places=9)  # BEDROOM
        self.assertAlmostEqual(puerta.height_m, 2.1, places=9)
        self.assertEqual(puerta.wall_id, self.muro_oeste.id)
        # centrada en el muro de 3.0 m: offset (3.0-0.9)/2
        self.assertAlmostEqual(puerta.offset_m, 1.05, places=9)
        self.assertEqual(resumen["creados"], [puerta.code])
        self.assertIn("Acceso", resumen["texto"])
        self.assertIsInstance(resumen["qto"], dict)

    def test_ancho_explicito_gana(self):
        resumen = edi.crear_acceso(self.context, self.local_a.id,
                                   muro_ref=self.muro_sur_a.code,
                                   ancho=1.2)
        puerta = [e for e in self.context.architecture.list(
            "DOOR", self.context.project.id)][0]
        self.assertAlmostEqual(puerta.width_m, 1.2, places=9)

    def test_vano_que_no_cabe_da_error_amable(self):
        with self.assertRaises(ARQGenError) as captura:
            edi.crear_acceso(self.context, self.local_a.id,
                             muro_ref=self.muro_oeste.code, ancho=3.5)
        self.assertEqual(getattr(captura.exception, "code", ""),
                         "ARQ-EDI-002")

    def test_undo_persistente_devuelve_el_estado(self):
        from app.undo_service import PersistentUndoService
        self.context.commit()
        resumen = edi.crear_acceso(self.context, self.local_a.id,
                                   muro_ref=self.muro_oeste.code)
        self.context.commit()
        PersistentUndoService(self.context).undo()
        puertas = self.context.architecture.list(
            "DOOR", self.context.project.id)
        self.assertEqual(len(puertas), 0)


class TestVentilacion(_LocalBase):

    def test_sugerencia_con_deficit_y_muro_exclusivo(self):
        propuesta = edi.sugerir_ventana(self.context, self.local_a.id)
        self.assertAlmostEqual(propuesta["deficit_m2"], 2.0, places=6)
        self.assertFalse(propuesta["suficiente"])
        exclusivos = set(edi.datos_local(
            self.context, self.local_a.id)["muros_exclusivos"])
        self.assertIn(propuesta["muro"], exclusivos)
        # deficit 2.0 m2 / 1.2 m de alto = 1.67 m de ancho
        self.assertAlmostEqual(propuesta["ancho_m"], 1.67, places=6)

    def test_crear_ventana_con_el_ancho_que_pide_el_deficit(self):
        propuesta = edi.sugerir_ventana(self.context, self.local_a.id)
        resumen = edi.crear_ventana(self.context, self.local_a.id)
        ventanas = self.context.architecture.list(
            "WINDOW", self.context.project.id)
        self.assertEqual(len(ventanas), 1)
        ventana = ventanas[0]
        self.assertAlmostEqual(ventana.width_m, 1.67, places=6)
        self.assertAlmostEqual(ventana.height_m, 1.2, places=9)
        self.assertAlmostEqual(ventana.sill_height_m, 1.0, places=9)
        self.assertEqual(ventana.wall_id,
                         cad.resolver(self.context, "WALL",
                                      propuesta["muro"]).id)
        self.assertIn("Ventilacion", resumen["texto"])

    def test_sin_deficit_da_error_amable(self):
        self.arq.create_opening("WINDOW", self.muro_oeste.code, 2.4, 1.2,
                                offset_m=0.3, sill_height_m=1.0)
        with self.assertRaises(ARQGenError) as captura:
            edi.crear_ventana(self.context, self.local_a.id)
        self.assertEqual(getattr(captura.exception, "code", ""),
                         "ARQ-EDI-002")

    def test_ancho_explicito_en_otro_muro(self):
        resumen = edi.crear_ventana(self.context, self.local_a.id,
                                    muro_ref=self.muro_sur_a.code,
                                    ancho=1.0)
        ventana = self.context.architecture.list(
            "WINDOW", self.context.project.id)[0]
        self.assertAlmostEqual(ventana.width_m, 1.0, places=9)
        self.assertEqual(ventana.wall_id, self.muro_sur_a.id)


class TestRedimensionar(_LocalBase):

    def test_lleva_el_local_a_las_dimensiones_pedidas(self):
        # A: comparte el este (x=4); exclusivos sur/norte/oeste.
        # pedimos 5 x 4: crece hacia la IZQUIERDA (el oeste es el
        # exclusivo del eje X) y hacia ARRIBA
        resumen = edi.redimensionar_local(self.context, self.local_a.id,
                                          5.0, 4.0, con_mobiliario=False)
        datos = edi.datos_local(self.context, self.local_a.id)
        self.assertAlmostEqual(datos["ancho_m"], 5.0, places=6)
        self.assertAlmostEqual(datos["fondo_m"], 4.0, places=6)
        # el muro compartido se queda exactamente donde estaba
        compartido = cad.resolver(self.context, "WALL",
                                  self.muro_compartido.id)
        self.assertEqual(compartido.start, (4.0, 0.0))
        self.assertEqual(compartido.end, (4.0, 3.0))
        # el vecino B no se entera
        datos_b = edi.datos_local(self.context, self.local_b.id)
        self.assertAlmostEqual(datos_b["ancho_m"], 4.0, places=6)
        self.assertTrue(any("compartido" in a for a in resumen["avisos"]))

    def test_los_vanos_se_re_proyectan_sobre_el_muro_movido(self):
        self.arq.create_opening("WINDOW", self.muro_norte_a.code, 1.2,
                                1.2, offset_m=0.9, sill_height_m=1.0)
        edi.redimensionar_local(self.context, self.local_a.id, 4.0, 4.0,
                                con_mobiliario=False)
        norte = cad.resolver(self.context, "WALL", self.muro_norte_a.id)
        self.assertAlmostEqual(norte.start[1], 4.0, places=9)
        ventana = self.context.architecture.list(
            "WINDOW", self.context.project.id)[0]
        self.assertGreaterEqual(ventana.offset_m, 0.0)
        self.assertLessEqual(ventana.offset_m + ventana.width_m,
                             norte.length_m + 1e-9)

    def test_mobiliario_recolocado_sobre_la_geometria_nueva(self):
        resumen = edi.redimensionar_local(self.context, self.local_a.id,
                                          5.0, 4.0, con_mobiliario=True)
        self.assertGreater(resumen.get("mobiliario", 0), 0)
        piezas = [e for e in self.context.architecture.list(
            "FURNITURE", self.context.project.id)
            if e.space_id == self.local_a.id]
        self.assertGreater(len(piezas), 0)
        recinto_x_max = 4.0
        for pieza in piezas:
            self.assertLessEqual(pieza.x, recinto_x_max + 0.01)

    def test_dimensiones_no_validas_error(self):
        with self.assertRaises(ARQGenError):
            edi.redimensionar_local(self.context, self.local_a.id,
                                    0.2, 3.0)

    def test_resumen_y_qto(self):
        resumen = edi.redimensionar_local(self.context, self.local_a.id,
                                          5.0, 4.0, con_mobiliario=False)
        self.assertIsInstance(resumen["qto"], dict)
        texto = edi.resumen_texto(resumen)
        texto.encode("cp1252")
        self.assertIn("Local", texto)


class TestPersistencia(_LocalBase):

    def test_todo_persiste_al_reabrir(self):
        edi.crear_acceso(self.context, self.local_a.id,
                         muro_ref=self.muro_oeste.code)
        edi.crear_ventana(self.context, self.local_a.id)
        edi.redimensionar_local(self.context, self.local_a.id, 5.0, 4.0,
                                con_mobiliario=False)
        self.context.commit()
        ruta = self.context.db_path
        self.context.close()
        self.context = self.application.open_project(ruta)
        datos = edi.datos_local(self.context, self.local_a.id)
        self.assertAlmostEqual(datos["ancho_m"], 5.0, places=6)
        self.assertAlmostEqual(datos["fondo_m"], 4.0, places=6)
        self.assertEqual(len(datos["puertas"]), 1)
        self.assertEqual(len(datos["ventanas"]), 1)


class TestDialogoGUI(_LocalBase):

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_dialogo_carga_diagnostico_y_crea_acceso(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        dialogo._editor_cargar()
        texto = dialogo._editor_diag.get("1.0", "end")
        self.assertIn("Diagnóstico", texto)
        self.assertIn("sin puerta", texto)
        self.assertIsNone(dialogo._editor_resultado["resumen"])
        dialogo._editor_aplicar("acceso")
        resumen = dialogo._editor_resultado["resumen"]
        self.assertIsNotNone(resumen)
        puertas = self.context.architecture.list(
            "DOOR", self.context.project.id)
        self.assertEqual(len(puertas), 1)
        # el diagnóstico se refresca: ya no avisa de sin puerta
        self.assertNotIn("sin puerta",
                         dialogo._editor_diag.get("1.0", "end"))
        dialogo.destroy()

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_dialogo_redimensiona_desde_los_campos(self):
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        dialogo._editor_vars["ancho"].set("5.0")
        dialogo._editor_vars["fondo"].set("4.0")
        dialogo._editor_vars["amueblar"].set(False)
        dialogo._editor_aplicar("redimensionar")
        datos = edi.datos_local(self.context, self.local_a.id)
        self.assertAlmostEqual(datos["ancho_m"], 5.0, places=6)
        self.assertAlmostEqual(datos["fondo_m"], 4.0, places=6)
        dialogo.destroy()
