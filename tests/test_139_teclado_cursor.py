"""TECLADO, PUNTERO Y REJILLA ESTILO AUTOCAD (v3.16.0).

* Motor de teclado sin Tk: F3/F7/F8/F9/F10 conmutan modos, ESC
  cancela, ESPACIO repite la ultima orden, alias letra a letra
  (M, CO, MI, RO, TR, EX, CHA, DIV, S, O, E, U, P) y combos Ctrl.
* Puntero: mira de punta a punta (100 %) o menor, grosor, color,
  referencias a extremos (cuadro) y puntos medios (triangulo),
  ORTO que endereza e IMANTACION que redondea, con la precedencia
  de AutoCAD (la referencia ganada gana).
* GUI real (Xvfb): F8/F9 en vivo, alias que activa la herramienta,
  ESPACIO que repite, mira dibujada en el Motion, marcador de
  referencia junto al extremo del muro, portapapeles Ctrl+C/Ctrl+V
  que duplica un local, pan con flechas y dialogo de puntero que
  persiste en prefs.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.errors import ARQGenError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from ui import cursor_acad, keymap

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


class _Muro:
    start = (0.0, 0.0)
    end = (10.0, 0.0)


class TestTecladoMotor(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.teclas = keymap.TecladoAutoCAD()

    def test_teclas_de_funcion_alternan_con_mensaje_cp1252(self):
        self.assertTrue(self.teclas.estado["osnap"])
        nuevo, mensaje = self.teclas.alternar("osnap")
        self.assertFalse(nuevo)
        self.assertIn("F3", mensaje)
        self.assertIn("DESACTIVADO", mensaje)
        mensaje.encode("cp1252")  # disciplina v3.13.1
        self.assertFalse(self.teclas.estado["orto"])
        self.teclas.alternar("orto")
        self.assertTrue(self.teclas.estado["orto"])

    def test_modo_desconocido_da_error_amable(self):
        with self.assertRaises(ARQGenError) as captura:
            self.teclas.alternar("modo_inexistente")
        self.assertEqual(getattr(captura.exception, "code", ""),
                         "ARQ-KEY-001")

    def test_procesar_traduce_las_teclas_f(self):
        accion = self.teclas.procesar("F8")
        self.assertEqual(accion, "alternar_orto")
        self.assertTrue(self.teclas.estado["orto"])
        accion = self.teclas.procesar("f7")
        self.assertEqual(accion, "alternar_rejilla")

    def test_esc_cancela_y_limpia_el_buffer(self):
        self.teclas.procesar("c")     # esperando CHA/CO
        self.assertEqual(self.teclas.buffer(), "c")
        self.assertEqual(self.teclas.procesar("escape"), "cancelar")
        self.assertEqual(self.teclas.buffer(), "")

    def test_espacio_repite_la_ultima_orden(self):
        self.assertIsNone(self.teclas.ultima_accion)
        self.assertEqual(self.teclas.procesar("s"), "estirar")
        self.assertEqual(self.teclas.procesar("space"), "repetir")
        self.assertEqual(self.teclas.ultima_accion, "estirar")
        # un F8 o un Ctrl+S NO son la ultima orden
        self.teclas.procesar("F8")
        self.teclas.procesar("s", ctrl=True)
        self.assertEqual(self.teclas.ultima_accion, "estirar")

    def test_espacio_ejecuta_el_alias_pendiente(self):
        # M es alias completo Y prefijo de MI: ESPACIO lo ejecuta
        self.assertIsNone(self.teclas.procesar("m"))
        self.assertEqual(self.teclas.procesar("space"), "mover")
        self.assertIsNone(self.teclas.procesar("e"))
        self.assertEqual(self.teclas.procesar("space"), "borrar")

    def test_alias_letra_a_letra_como_autocad(self):
        # prefijos que esperan mas letras
        self.assertIsNone(self.teclas.procesar("c"))
        self.assertEqual(self.teclas.buffer(), "c")
        self.assertEqual(self.teclas.procesar("o"), "copiar_objeto")
        # M espera: M+ESPACIO es mover, M+I es reflejar
        self.assertIsNone(self.teclas.procesar("m"))
        self.assertEqual(self.teclas.procesar("i"), "reflejar")
        self.assertIsNone(self.teclas.procesar("r"))
        self.assertEqual(self.teclas.procesar("o"), "girar")
        self.assertIsNone(self.teclas.procesar("t"))
        self.assertEqual(self.teclas.procesar("r"), "recortar")
        self.assertIsNone(self.teclas.procesar("e"))
        self.assertEqual(self.teclas.procesar("x"), "alargar")
        self.assertIsNone(self.teclas.procesar("c"))
        self.assertIsNone(self.teclas.procesar("h"))
        self.assertEqual(self.teclas.procesar("a"), "chaflan")
        self.assertIsNone(self.teclas.procesar("d"))
        self.assertIsNone(self.teclas.procesar("i"))
        self.assertEqual(self.teclas.procesar("v"), "dividir")
        # sin prefijo mas largo: se ejecutan al vuelo
        self.assertEqual(self.teclas.procesar("s"), "estirar")
        self.assertEqual(self.teclas.procesar("o"), "paralela")
        self.assertIsNone(self.teclas.procesar("e"))
        self.assertEqual(self.teclas.procesar("space"), "borrar")
        self.assertEqual(self.teclas.procesar("u"), "deshacer")
        # v3.38.0: PU existe, asi que P espera y P+ESPACIO es pan (la
        # misma resolucion de acad.pgp: P=PAN y PU=PURGE conviven)
        self.assertIsNone(self.teclas.procesar("p"))
        self.assertEqual(self.teclas.procesar("space"), "pan")
        # Z espera (ZE/ZP): Z+ESPACIO es zoom ventana, ZE encuadra
        self.assertIsNone(self.teclas.procesar("z"))
        self.assertEqual(self.teclas.procesar("e"), "encuadrar")
        self.assertIsNone(self.teclas.procesar("z"))
        self.assertEqual(self.teclas.procesar("p"), "zoom_anterior")
        # sin prefijo mas largo: se ejecutan al vuelo (MU muro)
        self.assertEqual(self.teclas.procesar("m"), None)
        self.assertEqual(self.teclas.procesar("u"), "dib_muro")
        self.assertEqual(self.teclas.procesar("s"), "estirar")
        self.assertEqual(self.teclas.procesar("o"), "paralela")
        self.assertIsNone(self.teclas.procesar("e"))
        self.assertEqual(self.teclas.procesar("space"), "borrar")

    def test_letra_fuera_de_alias_limpia_el_buffer(self):
        # una letra que no inicia ningun alias limpia el buffer
        self.assertIsNone(self.teclas.procesar("w"))
        self.assertEqual(self.teclas.buffer(), "")
        self.assertIsNone(self.teclas.procesar("m"))
        self.assertEqual(self.teclas.procesar("w"), None)
        self.assertEqual(self.teclas.buffer(), "")

    def test_combos_ctrl_estilo_autocad(self):
        self.assertEqual(self.teclas.procesar("z", ctrl=True), "deshacer")
        self.assertEqual(self.teclas.procesar("y", ctrl=True), "rehacer")
        self.assertEqual(self.teclas.procesar("z", ctrl=True, shift=True),
                         "rehacer")
        self.assertEqual(self.teclas.procesar("c", ctrl=True),
                         "copiar_seleccion")
        self.assertEqual(self.teclas.procesar("x", ctrl=True), "cortar")
        self.assertEqual(self.teclas.procesar("v", ctrl=True), "pegar")
        self.assertEqual(self.teclas.procesar("s", ctrl=True), "guardar")
        self.assertEqual(self.teclas.procesar("o", ctrl=True), "abrir")
        self.assertEqual(self.teclas.procesar("n", ctrl=True), "nuevo")
        self.assertEqual(self.teclas.procesar("a", ctrl=True),
                         "seleccionar_todo")
        self.assertEqual(self.teclas.procesar("p", ctrl=True), "imprimir")
        self.assertEqual(self.teclas.procesar("0", ctrl=True),
                         "encuadrar")

    def test_flechas_y_zoom(self):
        self.assertEqual(self.teclas.procesar("Left"), "pan_izquierda")
        self.assertEqual(self.teclas.procesar("Right"), "pan_derecha")
        self.assertEqual(self.teclas.procesar("Up"), "pan_arriba")
        self.assertEqual(self.teclas.procesar("Down"), "pan_abajo")
        self.assertEqual(self.teclas.procesar("plus"), "zoom+")
        self.assertEqual(self.teclas.procesar("minus"), "zoom-")

    def test_resumen_de_atajos_es_cp1252(self):
        for linea in keymap.resumen_atajos():
            linea.encode("cp1252")

    def test_estado_de_fabrica_como_autocad(self):
        t = keymap.TecladoAutoCAD()
        self.assertTrue(t.estado["osnap"])
        self.assertTrue(t.estado["rejilla"])
        self.assertFalse(t.estado["orto"])
        self.assertFalse(t.estado["imantacion"])
        self.assertFalse(t.estado["polar"])


class TestPunteroMotor(ARQGenTestCase):

    def test_mira_de_punta_a_punta_al_100(self):
        p1, p2, p3, p4 = cursor_acad.puntas_cruz(50, 40, 100, 80, 100.0)
        self.assertEqual(p1, (0.0, 40))
        self.assertEqual(p2, (100.0, 40))
        self.assertEqual(p3, (50, 0.0))
        self.assertEqual(p4, (50, 80.0))

    def test_mira_reducida_al_50(self):
        p1, p2, _p3, _p4 = cursor_acad.puntas_cruz(50, 40, 100, 80, 50.0)
        self.assertEqual(p1, (25.0, 40))
        self.assertEqual(p2, (75.0, 40))

    def test_referencias_a_extremos_y_puntos_medios(self):
        fij = cursor_acad.fijaciones([_Muro()], (0.2, 0.1), 0.5)
        self.assertIn(((0.0, 0.0), "extremo"), fij)
        fij = cursor_acad.fijaciones([_Muro()], (5.1, 0.2), 0.5)
        self.assertIn(((5.0, 0.0), "medio"), fij)
        self.assertEqual(cursor_acad.fijaciones([_Muro()],
                                                (7.0, 5.0), 0.5), [])

    def test_mejor_fijacion_elige_la_mas_cercana(self):
        ganada = cursor_acad.mejor_fijacion([_Muro()], (0.3, 0.2), 0.5)
        self.assertEqual(ganada[0], (0.0, 0.0))
        self.assertEqual(ganada[1], "extremo")

    def test_orto_endereza_al_eje_mayor(self):
        self.assertEqual(cursor_acad.aplicar_orto((0, 0), (3, 8)),
                         (0, 8))
        self.assertEqual(cursor_acad.aplicar_orto((0, 0), (9, 2)),
                         (9, 0))

    def test_imantacion_cae_en_la_rejilla(self):
        self.assertEqual(cursor_acad.imantar_rejilla((0.42, 1.61), 0.5),
                         (0.5, 1.5))

    def test_precedencia_la_referencia_ganada_gana(self):
        punto, marca = cursor_acad.aplicar_ayudas(
            None, (0.05, 0.04), True, True, True, [_Muro()],
            cursor_acad.ConfigCursor(), 100.0)
        self.assertEqual(punto, (0.0, 0.0))
        self.assertEqual(marca, "extremo")

    def test_sin_referencia_orto_y_luego_imantacion(self):
        punto, marca = cursor_acad.aplicar_ayudas(
            (0, 0), (0.45, 0.05), True, True, True, [_Muro()],
            cursor_acad.ConfigCursor(), 100.0)
        self.assertIsNone(marca)
        self.assertEqual(punto, (0.5, 0.0))

    def test_configuracion_tolerante_y_acotada(self):
        self.assertEqual(cursor_acad.config_de_datos(None),
                         cursor_acad.ConfigCursor())
        self.assertEqual(cursor_acad.config_de_datos("basura"),
                         cursor_acad.ConfigCursor())
        config = cursor_acad.config_de_datos(
            {"mira_pct": 1000, "mira_grosor": 99, "paso_rejilla": 0.01,
             "umbral_osnap_px": 0.0, "mira_color": "#ff0000"})
        self.assertEqual(config.mira_pct, 100.0)
        self.assertEqual(config.mira_grosor, 5)
        self.assertGreaterEqual(config.paso_rejilla, 0.05)
        self.assertGreaterEqual(config.umbral_osnap_px, 3.0)

    def test_configuracion_roundtrip_hacia_prefs(self):
        config = cursor_acad.ConfigCursor(mira_pct=75.0, mira_grosor=2,
                                          mira_color="#00ff00",
                                          paso_rejilla=0.25)
        datos = cursor_acad.dict_de_config(config)
        self.assertEqual(datos["mira_pct"], 75.0)
        self.assertEqual(datos["mira_grosor"], 2)
        vuelta = cursor_acad.config_de_datos(datos)
        self.assertEqual(vuelta, config.normalizada())

    def test_color_de_mira_lee_config_y_tema(self):
        self.assertEqual(cursor_acad.color_mira("#ff0000", "#000000"),
                         "#ff0000")
        self.assertEqual(cursor_acad.color_mira("", "#123456"), "#123456")
        self.assertEqual(cursor_acad.color_mira("", ""), "#ffffff")


class _GuiBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("teclado.arqgen"), name="Teclado")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("Planta", 0.0, 3.0)
        self.muro_a = self.arq.create_wall(self.nivel.code,
                                           (0.0, 0.0), (6.0, 0.0), 0.2)
        self.muro_b = self.arq.create_wall(self.nivel.code,
                                           (6.0, 0.0), (6.0, 4.0), 0.2)
        self.local = self.arq.create_space(
            self.nivel.code, "Sala", "ROOM",
            [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)])
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


class TestTecladoGUI(_GuiBase):

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_f8_y_f9_en_vivo(self):
        window = self._ventana()
        self.assertFalse(window.teclas.estado["orto"])
        window._tecla_modo(SimpleNamespace(keysym="F8"))
        self.assertTrue(window.teclas.estado["orto"])
        self.assertIn("orto", window.status_var.get())
        window._tecla_modo(SimpleNamespace(keysym="F9"))
        self.assertTrue(window.teclas.estado["imantacion"])
        # F7 sincroniza la casilla de la rejilla del lienzo
        window._tecla_modo(SimpleNamespace(keysym="F7"))
        self.assertFalse(window._grid_var().get())
        window._tecla_modo(SimpleNamespace(keysym="F7"))
        self.assertTrue(window._grid_var().get())

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_alias_m_activa_mover_y_esc_cancela(self):
        window = self._ventana()
        # M espera (es prefijo de MI); M+ESPACIO ejecuta MOVER
        window._tecla_canvas(SimpleNamespace(keysym="m", state=0))
        self.assertIsNone(window._cad_estado()["tool"])
        window._tecla_canvas(SimpleNamespace(keysym="space", state=0))
        self.assertEqual(window._cad_estado()["tool"], "mover")
        window._cad_cancelar()
        self.assertIsNone(window._cad_estado()["tool"])
        # CHA completo al vuelo
        window._tecla_canvas(SimpleNamespace(keysym="c", state=0))
        window._tecla_canvas(SimpleNamespace(keysym="h", state=0))
        window._tecla_canvas(SimpleNamespace(keysym="a", state=0))
        self.assertEqual(window._cad_estado()["tool"], "chaflan")

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_espacio_repite_la_ultima_herramienta(self):
        window = self._ventana()
        window._cad_set_tool("recortar")
        window._cad_cancelar()
        self.assertIsNone(window._cad_estado()["tool"])
        window._tecla_canvas(SimpleNamespace(keysym="space", state=0))
        self.assertEqual(window._cad_estado()["tool"], "recortar")

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_pan_temporal_con_p_y_esc(self):
        window = self._ventana()
        # v3.38.0: PU existe, asi que P espera y P+ESPACIO arma el pan
        # (la misma resolucion de acad.pgp: P=PAN y PU=PURGE conviven)
        window._tecla_canvas(SimpleNamespace(keysym="p", state=0))
        self.assertFalse(window._pan_temporal)
        window._tecla_canvas(SimpleNamespace(keysym="space", state=0))
        self.assertTrue(window._pan_temporal)
        window._tecla_canvas(SimpleNamespace(keysym="Escape", state=0))
        self.assertFalse(window._pan_temporal)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_flechas_desplazan_la_vista(self):
        window = self._ventana()
        window.redraw()
        antes_x = window.viewport.center_x
        window._tecla_canvas(SimpleNamespace(keysym="Right", state=0))
        self.assertAlmostEqual(
            window.viewport.center_x,
            antes_x + 60.0 / window.viewport.scale, places=9)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_mira_y_marco_de_referencia_en_el_lienzo(self):
        window = self._ventana()
        window.viewport.center_x, window.viewport.center_y = 3.0, 0.0
        window.viewport.scale = 60.0
        window.redraw()
        # cerca del extremo (0,0): mira + cuadro de extremo
        sx, sy = window.viewport.to_screen(0.0, 0.0, 800, 600)
        window._mira_redibuja(SimpleNamespace(x=sx + 3, y=sy + 2))
        self.assertGreater(
            len(window.canvas.find_withtag("acad_mira")), 0)
        self.assertIsNotNone(window._acad_marcador)
        self.assertEqual(window._acad_marcador[2], "extremo")
        # sin mira configurada no se dibuja nada
        window._acad = cursor_acad.ConfigCursor(mira=False)
        window._mira_redibuja(SimpleNamespace(x=sx, y=sy))
        self.assertEqual(len(window.canvas.find_withtag("acad_mira")), 0)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_orto_fija_el_paso_del_mover(self):
        window = self._ventana()
        window._cad_set_tool("mover")
        window.viewport.center_x, window.viewport.center_y = 3.0, 0.0
        window.viewport.scale = 60.0
        window.redraw()
        window._tecla_modo(SimpleNamespace(keysym="F8"))   # orto

        def _clic(x, y):
            sx, sy = window.viewport.to_screen(x, y, 800, 600)
            window._cad_click(SimpleNamespace(x=sx, y=sy))

        _clic(3.0, 0.0)        # seleccion del muro
        _clic(3.0, 0.0)        # punto base
        _clic(4.0, 1.5)        # destino: delta (1.0, 1.5), orto gana Y
        muro = self.context.architecture.get("WALL", self.muro_a.id)
        self.assertAlmostEqual(muro.start[1], 1.5, places=9)
        self.assertAlmostEqual(muro.start[0], 0.0, places=9)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_portapapeles_duplica_un_local(self):
        window = self._ventana()
        antes = len(self.context.architecture.list("SPACE",
                                                   self.context.project.id))
        window.selection = window._find_row(self.local.id)
        self.assertIsNotNone(window.selection)
        window._portapapeles_copiar()
        self.assertEqual(window._portapapeles, ("SPACE", self.local.id))
        window._portapapeles_pegar()
        despues = len(self.context.architecture.list(
            "SPACE", self.context.project.id))
        self.assertEqual(despues, antes + 1)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_dialogo_puntero_aplica_y_persiste_en_prefs(self):
        window = self._ventana()
        window.open_puntero_dialog()
        dialogo = window._puntero_dialogo
        dialogo._puntero_vars["mira_pct"].set("60")
        dialogo._puntero_vars["mira_grosor"].set("2")
        dialogo._puntero_vars["mira_color"].set("#ff8800")
        dialogo._puntero_aplicar()
        self.assertAlmostEqual(window._acad.mira_pct, 60.0)
        self.assertEqual(window._acad.mira_grosor, 2)
        self.assertEqual(window._acad.mira_color, "#ff8800")
        self.assertEqual(window.prefs["cursor"]["mira_pct"], 60.0)
        dialogo.destroy()

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
    def test_dialogo_puntero_rechaza_no_numericos(self):
        from unittest.mock import patch
        window = self._ventana()
        window.open_puntero_dialog()
        dialogo = window._puntero_dialogo
        dialogo._puntero_vars["mira_pct"].set("muy grande")
        with patch("ui.app_window.messagebox.showerror") as _falso:
            dialogo._puntero_aplicar()
        self.assertAlmostEqual(window._acad.mira_pct, 100.0)  # sin cambio
        dialogo.destroy()
