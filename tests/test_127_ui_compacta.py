"""INTERFAZ COMPACTA, PLANO PRIMERO (v3.9.0).

Lo pedido: «hay botones que no veo por la escala (no veo el selector
de niveles), el logo de la ventana principal está muy grande y me
ocupa mucho espacio, quítale espacio a las ventanas o espacios que no
ameriten de tanto espacio, prioriza un buen espacio para donde se ven
los planos».

Causa raíz que estas pruebas dejan clavada:

* La barra de herramientas reutilizando el PNG de branding de 256 px
  como imagen de la marca medía ~260 px de ALTO: el logo solo le
  robaba al plano más espacio que el panel de avisos entero.
* TODA la barra (asistentes + zooms + buscador + filtro «Nivel:») iba
  en UNA fila de ~1500 px: con la escala de Windows el extremo derecho
  se cortaba y el selector de niveles quedaba invisible.

Cobertura de estas pruebas:

* ui.icons.toolbar_logo(): logo PEQUEÑO (22 px) generado en memoria,
  determinista; window_icon() conserva el grande SOLO para la barra
  de título del sistema.
* Ventana real (Tk bajo Xvfb): la barra vive en DOS filas (acciones |
  navegación+filtros), el filtro «Nivel:» queda DENTRO de los límites
  de la ventana aun en 1024x720 (peor caso razonable de portátil) y
  la fila de filtros es la segunda.
* Separadores de fábrica SASH_DEFAULT_* (240 / 300 / 120): el plano
  gana ~70 px de ancho y el panel inferior pide muy poco alto (100 px
  en v3.9.1, tras migrar las preferencias heredadas que lo dejaban a
  media ventana);
  coherencia entre constantes, restauración y reset de disposición.
* Tema: botones, pestañas y filas de árbol más compactos en ambos
  temas, SIN tocar el sash grueso de 10 px (v3.7.0).
"""

from __future__ import annotations

import os
import time
import unittest

from tests.base import ARQGenTestCase

from ui import icons
from ui.theme import SASH_THICKNESS


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


DISPLAY = _display_available()


def _padding_tuple(value) -> tuple:
    """Normaliza lo que devuelve style.lookup de un padding."""
    if isinstance(value, (tuple, list)):
        return tuple(int(v) for v in value)
    cleaned = str(value).replace(",", " ").replace("{", " ").replace(
        "}", " ")
    return tuple(int(part) for part in cleaned.split())


class TestLogoCompacto(ARQGenTestCase):
    """El logo de la barra es pequeño y el grande queda para el título."""

    def test_render_logo_pequeno_es_png_valido(self):
        data = icons.render_logo(22)
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(data), 0)

    def test_toolbar_logo_devuelve_photo_de_22_px(self):
        if not DISPLAY:
            self.skipTest("sin display")
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            photo = icons.toolbar_logo(22, master=root)
            self.assertIsNotNone(photo)
            self.assertEqual(photo.width(), 22)
            self.assertEqual(photo.height(), 22)
        finally:
            root.destroy()

    def test_toolbar_logo_es_determinista(self):
        self.assertEqual(icons.render_logo(22), icons.render_logo(22))


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestVentanaCompacta(ARQGenTestCase):
    """Barra en dos filas, nivel visible y sashes al servicio del plano."""

    def _make_window(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.demo_context()
        return ARQGenWindow(self.context, self.application)

    def setUp(self):
        super().setUp()
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    # -- logo -------------------------------------------------------------
    def test_la_barra_usa_el_logo_pequeno(self):
        window = self._make_window()
        try:
            window.update()
            self.assertIsNotNone(window._logo_small)
            self.assertLessEqual(window._logo_small.width(), 32)
            # el grande sigue vivo, pero SOLO para la barra de título
            self.assertIsNotNone(window._logo_photo)
            self.assertGreater(window._logo_photo.width(),
                               window._logo_small.width())
        finally:
            window.destroy()
            self.context.close()

    # -- dos filas --------------------------------------------------------
    def test_barra_en_dos_filas_con_filtros_en_la_segunda(self):
        window = self._make_window()
        try:
            window.update()
            fila_a = window.nametowidget(".!frame")     # primera creada
            fila_b = window.level_combo.master
            self.assertIsNot(fila_a, fila_b)
            self.assertEqual(str(fila_a.master), str(window))
            self.assertEqual(str(fila_b.master), str(window))
            # fila A: acciones (asistente + tema); fila B: filtros
            textos_a = " ".join(
                str(ch.cget("text")) for ch in fila_a.winfo_children()
                if hasattr(ch, "cget") and "text" in ch.keys())
            self.assertIn("Asistente de edificación", textos_a)
            self.assertIn("Modo", textos_a)  # Modo oscuro/claro
            self.assertIn("Nivel:", " ".join(
                str(ch.cget("text")) for ch in fila_b.winfo_children()
                if hasattr(ch, "cget") and "text" in ch.keys()))
            self.assertIn("Encuadrar", " ".join(
                str(ch.cget("text")) for ch in fila_b.winfo_children()
                if hasattr(ch, "cget") and "text" in ch.keys()))
        finally:
            window.destroy()
            self.context.close()

    def test_selector_de_nivel_dentro_de_ventana_estrecha(self):
        # 1024x720: peor caso razonable de portátil con escala alta.
        # En v3.8.0 el filtro «Nivel:» quedaba fuera de la ventana.
        window = self._make_window()
        try:
            window.geometry("1024x720")
            for _ in range(40):
                window.update()
                if window.winfo_ismapped():
                    break
                time.sleep(0.01)
            window.update()
            self.assertTrue(window.level_combo.winfo_ismapped())
            borde_combo = (window.level_combo.winfo_rootx()
                           + window.level_combo.winfo_width())
            borde_ventana = (window.winfo_rootx()
                             + window.winfo_width())
            self.assertLessEqual(borde_combo, borde_ventana)
            # y la entrada del buscador tampoco se corta
            borde_buscar = (window.search_entry.winfo_rootx()
                            + window.search_entry.winfo_width())
            self.assertLessEqual(borde_buscar, borde_ventana)
        finally:
            window.destroy()
            self.context.close()

    # -- separadores de fábrica -------------------------------------------
    def test_constantes_de_fabrica_para_el_plano(self):
        from ui.app_window import (SASH_DEFAULT_BOTTOM_MARGIN,
                                   SASH_DEFAULT_EXPLORER,
                                   SASH_DEFAULT_PROPS_MARGIN)
        self.assertEqual(SASH_DEFAULT_EXPLORER, 240)
        self.assertEqual(SASH_DEFAULT_PROPS_MARGIN, 300)
        self.assertEqual(SASH_DEFAULT_BOTTOM_MARGIN, 120)
        # el plano se lleva siempre la parte del león
        centro = 1280 - SASH_DEFAULT_EXPLORER - SASH_DEFAULT_PROPS_MARGIN \
            - 2 * SASH_THICKNESS
        self.assertGreaterEqual(centro, 720)

    def test_defaults_aplicados_dan_espacio_al_plano(self):
        window = self._make_window()
        try:
            from ui.app_window import (SASH_DEFAULT_BOTTOM_MARGIN,
                                       SASH_DEFAULT_EXPLORER,
                                       SASH_DEFAULT_PROPS_MARGIN)
            window.geometry("1280x800")
            for _ in range(100):
                window.update()
                if window.winfo_ismapped() \
                        and window._paned.winfo_ismapped():
                    break
            for _ in range(30):
                window.update()
                time.sleep(0.01)
            window._apply_saved_sashes()
            self.assertEqual(len(window._paned.panes()), 3)
            self.assertAlmostEqual(window._paned.sashpos(0),
                                   SASH_DEFAULT_EXPLORER, delta=40)
            self.assertAlmostEqual(
                window._paned.sashpos(1),
                max(620, 1280 - SASH_DEFAULT_PROPS_MARGIN), delta=60)
            ancho_centro = window._paned.sashpos(1) \
                - window._paned.sashpos(0) - SASH_THICKNESS
            self.assertGreaterEqual(ancho_centro, 700)
            self.assertAlmostEqual(
                window._outer_paned.sashpos(0),
                max(300, 800 - SASH_DEFAULT_BOTTOM_MARGIN), delta=40)
        finally:
            window.destroy()
            self.context.close()

    def test_panel_inferior_pide_menos_alto(self):
        window = self._make_window()
        try:
            window.update()
            bottom = window._panel_frames["bottom"]
            self.assertEqual(int(bottom.cget("height")), 100)
            self.assertEqual(int(window.warnings_text.cget("height")), 3)
            self.assertEqual(int(window.log_text.cget("height")), 3)
        finally:
            window.destroy()
            self.context.close()

    def test_reset_layout_respeta_los_nuevos_defaults(self):
        from ui.app_window import SASH_DEFAULT_EXPLORER
        window = self._make_window()
        try:
            window.geometry("1280x800")
            window.update()
            window._paned.sashpos(0, 120)
            window.reset_layout()
            window.update()
            self.assertEqual(window._paned.sashpos(0),
                             SASH_DEFAULT_EXPLORER)
        finally:
            window.destroy()
            self.context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestTemaCompacto(ARQGenTestCase):
    """Botones/pestañas/filas más bajos; el sash grueso NO se toca."""

    def test_estilos_compactos_en_ambos_temas(self):
        import tkinter as tk
        from tkinter import ttk
        from ui import theme
        root = tk.Tk()
        root.withdraw()
        try:
            for modo in ("dark", "light"):
                theme.apply(root, modo)
                style = ttk.Style(root)
                self.assertEqual(_padding_tuple(
                    style.lookup("TButton", "padding")), (8, 4))
                self.assertEqual(_padding_tuple(
                    style.lookup("Accent.TButton", "padding")), (10, 4))
                self.assertLessEqual(int(
                    style.lookup("Treeview", "rowheight")), 22)
                self.assertGreaterEqual(int(
                    style.lookup("Sash", "sashthickness")), 8)
        finally:
            root.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
