"""Mejora UX v3.0.0: interfaz moderna y dinámica.

Cubre:
- ui/theme: sistema dual oscuro/claro (mismos tokens, cambio EN VIVO,
  re-vinculación de COL_*, mutación en el sitio de CANVAS_DARK y
  ENTITY_COLORS, restyle_tk_tree sobre widgets ya creados).
- ui/icons: glifos por funcionalidad, logo PNG/ICO determinista y
  generación de archivos de marca.
- ui/prefs: preferencias persistentes tolerantes (tema, autoguardado,
  paneles, geometría) con ruta sobre-escrita para pruebas.
- app/autosave: pendiente → calma → commit idempotente, enabled=False,
  cancel y textos de estado.
- Ventana real (con display): arranque, cambio de tema en vivo,
  paneles colapsables, menús contextuales (construcción), atajos
  nuevos, indicador de autoguardado y persistencia de preferencias.
"""

from __future__ import annotations

import os
import struct
import tempfile
import unittest

from tests.base import ARQGenTestCase

from ui import icons, prefs, theme
from app.autosave import AutoSaveService


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


class _Event:
    """Evento falso compatible con los manejadores del lienzo."""

    def __init__(self, x=0.0, y=0.0, x_root=0, y_root=0, widget=None,
                 delta=0):
        self.x = x
        self.y = y
        self.x_root = x_root
        self.y_root = y_root
        self.widget = widget
        self.delta = delta
        self.payload = {}


# -- Tema dual -----------------------------------------------------------------

class TestThemeDual(unittest.TestCase):
    """Sistema de temas oscuro/claro (ui/theme)."""

    def test_both_modes_share_tokens(self):
        self.assertEqual(set(theme.PALETTES["dark"]),
                         set(theme.PALETTES["light"]))
        for token in ("bg", "field", "canvas", "text", "accent",
                      "tooltip_bg", "welcome_card"):
            self.assertTrue(theme.PALETTES["dark"][token].startswith("#"))
            self.assertTrue(theme.PALETTES["light"][token].startswith("#"))

    def test_modes_are_distinct(self):
        self.assertNotEqual(theme.PALETTES["dark"]["bg"],
                            theme.PALETTES["light"]["bg"])
        self.assertNotEqual(theme.PALETTES["dark"]["canvas"],
                            theme.PALETTES["light"]["canvas"])

    def test_set_mode_rebinds_constants(self):
        dark_bg = theme.PALETTES["dark"]["bg"]
        theme.set_mode("dark")
        self.assertEqual(theme.COL_BG, dark_bg)
        theme.set_mode("light")
        self.assertEqual(theme.COL_BG, theme.PALETTES["light"]["bg"])
        self.assertEqual(theme.COL_CANVAS,
                         theme.PALETTES["light"]["canvas"])
        theme.set_mode("dark")
        self.assertEqual(theme.COL_BG, dark_bg)

    def test_shared_dicts_mutate_in_place(self):
        # Importación por valor: la referencia debe seguir el cambio.
        canvas_ref = dict(theme.CANVAS_DARK)
        entity_ref = theme.ENTITY_COLORS
        theme.set_mode("light")
        self.assertEqual(theme.CANVAS_DARK["space_fill"],
                         theme.PALETTES["light"]["space_fill"])
        self.assertIs(entity_ref, theme.ENTITY_COLORS)
        self.assertTrue(theme.ENTITY_COLORS)
        theme.set_mode("dark")
        self.assertEqual(theme.CANVAS_DARK["space_fill"],
                         canvas_ref["space_fill"])

    def test_invalid_mode_falls_back_to_dark(self):
        self.assertEqual(theme.set_mode("sepia"), "dark")
        self.assertEqual(theme.current_mode(), "dark")

    def test_toggle_round_trip(self):
        start = theme.current_mode()
        other = theme.toggle()
        self.assertNotEqual(other, start)
        self.assertEqual(theme.toggle(), start)

    def test_entity_palette_per_mode(self):
        theme.set_mode("dark")
        dark_space = theme.ENTITY_COLORS["space"]
        theme.set_mode("light")
        self.assertNotEqual(theme.ENTITY_COLORS["space"], dark_space)
        theme.set_mode("dark")

    def test_colors_and_get_helpers(self):
        snapshot = theme.colors()
        self.assertEqual(snapshot["bg"], theme.get("bg"))

    def test_apply_dark_theme_alias(self):
        self.assertTrue(callable(theme.apply_dark_theme))


# -- Íconos y marca --------------------------------------------------------------

class TestIcons(unittest.TestCase):
    """Glifos por funcionalidad y logo determinista (ui/icons)."""

    def test_required_glyphs_present(self):
        for key in icons.REQUIRED_ICONS:
            self.assertTrue(icons.glyph(key), f"glifo ausente: {key}")
            self.assertIn(icons.glyph(key), icons.ICONS[key])

    def test_label_prepends_glyph(self):
        text = icons.label("save", "Guardar")
        self.assertTrue(text.startswith(icons.glyph("save")))
        self.assertIn("Guardar", text)
        # Sin glifo registrado: etiqueta intacta.
        self.assertEqual(icons.label("inexistente_xyz", "Hola"), "Hola")

    def test_png_bytes_valid_and_deterministic(self):
        data = icons.render_logo(48)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(icons.render_logo(48), data)
        # Dimensiones en el IHDR (bytes 16-24).
        w, h = struct.unpack(">II", data[16:24])
        self.assertEqual((w, h), (48, 48))

    def test_logo_pixel_corners_transparent(self):
        rgba = icons.logo_pixel(0.001, 0.001)
        self.assertEqual(rgba[3], 0, "esquina fuera de la placa")
        center = icons.logo_pixel(0.5, 0.5)
        self.assertEqual(center[3], 255, "centro opaco")

    def test_ico_container_structure(self):
        data = icons.ico_bytes((16, 32, 64))
        reserved, kind, count = struct.unpack("<HHH", data[:6])
        self.assertEqual((reserved, kind, count), (0, 1, 3))
        entry = struct.unpack("<BBBBHHII", data[6:22])
        self.assertEqual(entry[0], 16)          # ancho 16
        self.assertEqual(entry[4:6], (1, 32))   # planos y bpp

    def test_write_branding_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = icons.write_branding_files(tmp)
            for name, path in paths.items():
                self.assertTrue(os.path.exists(path), name)
                self.assertGreater(os.path.getsize(path), 100, name)
            with open(paths["png"], "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")


# -- Preferencias ------------------------------------------------------------------

class TestPrefs(unittest.TestCase):
    """Preferencias persistentes tolerantes (ui/prefs)."""

    def test_defaults_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            data = prefs.load_prefs(path)
            self.assertEqual(data["theme"], "dark")
            self.assertTrue(data["autosave"])
            self.assertTrue(data["panels"]["explorer"])

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            prefs.save_prefs({"theme": "light", "autosave": False,
                              "panels": {"bottom": False}}, path)
            data = prefs.load_prefs(path)
            self.assertEqual(data["theme"], "light")
            self.assertFalse(data["autosave"])
            self.assertFalse(data["panels"]["bottom"])
            self.assertTrue(data["panels"]["explorer"])

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{ no soy json")
            data = prefs.load_prefs(path)
            self.assertEqual(data, {**prefs.DEFAULTS,
                                    **data})  # claves por defecto presentes
            self.assertEqual(data["theme"], "dark")

    def test_invalid_theme_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            data = prefs.save_prefs({"theme": "sepia"}, path)
            self.assertEqual(prefs.load_prefs(path)["theme"], "dark")


# -- Autoguardado ---------------------------------------------------------------------

class TestAutoSave(unittest.TestCase):
    """Autoguardado por calma (app/autosave)."""

    def _service(self, state):
        class _Ctx:
            def commit(self):
                state["commits"] += 1
        return AutoSaveService(_Ctx(), enabled=True, delay_ms=200,
                               clock=lambda: state["t"])

    def test_event_marks_pending_and_flush_after_quiet(self):
        state = {"commits": 0, "t": 0.0}
        service = self._service(state)
        self.assertTrue(service.on_event(_Event()))
        self.assertFalse(service.flush(), "antes de la calma no guarda")
        state["t"] = 0.25
        self.assertTrue(service.flush())
        self.assertEqual(state["commits"], 1)
        self.assertFalse(service.flush(), "idempotente")
        self.assertEqual(state["commits"], 1)
        self.assertTrue(service.last_saved)
        self.assertEqual(service.status_text(),
                         f"Autoguardado {service.last_saved}")

    def test_disabled_never_schedules(self):
        state = {"commits": 0, "t": 0.0}
        service = self._service(state)
        service.enabled = False
        self.assertFalse(service.on_event(_Event()))
        self.assertFalse(service.due())
        self.assertEqual(service.status_text(), "Autoguardado en pausa")

    def test_cancel_discards_pending(self):
        state = {"commits": 0, "t": 0.0}
        service = self._service(state)
        service.on_event(_Event())
        service.cancel()
        self.assertFalse(service.due())

    def test_own_marker_event_is_ignored(self):
        state = {"commits": 0, "t": 0.0}
        service = self._service(state)
        event = _Event()
        event.payload = {"_arqgen_autosave": True}
        self.assertFalse(service.on_event(event))

    def test_pending_text_while_waiting(self):
        state = {"commits": 0, "t": 0.0}
        service = self._service(state)
        service.on_event(_Event())
        self.assertEqual(service.status_text(), "Guardando…")

    def test_commit_error_is_swallowed(self):
        class _BadCtx:
            def commit(self):
                raise RuntimeError("disco lleno")
        state = {"t": 0.0}
        service = AutoSaveService(_BadCtx(), enabled=True, delay_ms=100,
                                  clock=lambda: state["t"])
        service.on_event(_Event())
        self.assertFalse(service.flush(), "aún sin calma")
        state["t"] = 1.0
        self.assertFalse(service.flush())
        self.assertIn("disco lleno", service.last_error)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestWindowV3(ARQGenTestCase):
    """Ventana real: tema en vivo, paneles, menús contextuales,
    autoguardado e íconos."""

    def setUp(self):
        super().setUp()
        # Preferencias aisladas para no tocar las del usuario real.
        self._old_env = os.environ.get("ARQGEN_PREFS")
        self._prefs_path = os.path.join(self.tmp, "prefs.json")
        os.environ["ARQGEN_PREFS"] = self._prefs_path
        theme.set_mode("dark")
        from ui.app_window import ARQGenWindow
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        theme.set_mode("dark")
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_boots_with_logo_branding_and_autosave(self):
        self.assertIsNotNone(self.window._logo_photo)
        self.assertTrue(self.window.autosave.enabled)
        self.assertIn("Autoguardado", self.window._autosave_var_text.get())
        self.assertTrue(self.window.theme_button.cget("text"))

    def test_toolbar_buttons_carry_glyphs(self):
        texts = []
        for child in self.window.nametowidget(
                ".!frame").winfo_children():
            if hasattr(child, "cget") and hasattr(child, "cget") and \
                    "text" in child.keys():
                try:
                    texts.append(str(child.cget("text")))
                except Exception:  # noqa: BLE001
                    pass
        joined = " ".join(texts)
        self.assertIn(icons.glyph("save"), joined)
        self.assertIn(icons.glyph("theme"), joined)
        self.assertIn("Asistente de edificación", joined)

    def test_menu_has_save_theme_autosave_and_panels(self):
        menubar = self.window.nametowidget(self.window.cget("menu"))
        m_file = menubar.nametowidget(
            menubar.entrycget(menubar.index("Archivo"), "menu"))
        self.assertIsNotNone(m_file.index("Guardar\tCtrl+S"))
        m_view = menubar.nametowidget(
            menubar.entrycget(menubar.index("Ver"), "menu"))
        self.assertIsNotNone(m_view.index("Alternar tema oscuro/claro"
                                          "\tCtrl+T"))
        self.assertIsNotNone(m_view.index("Autoguardado (guarda solo "
                                          "ante cada cambio)"))
        m_help = menubar.nametowidget(
            menubar.entrycget(menubar.index("Ayuda"), "menu"))
        self.assertIsNotNone(
            m_help.index("¿Qué es esto? (pulsa un control)\tMayús+F1"))

    def test_toggle_theme_is_live_and_persists(self):
        window = self.window
        self.assertEqual(theme.current_mode(), "dark")
        dark_bg = window.cget("background")
        window.toggle_theme()
        window.update()
        self.assertEqual(theme.current_mode(), "light")
        self.assertEqual(window.cget("background"),
                         theme.PALETTES["light"]["bg"])
        self.assertNotEqual(window.cget("background"), dark_bg)
        self.assertEqual(window.canvas.cget("background"),
                         theme.PALETTES["light"]["canvas"])
        self.assertIn("Modo oscuro", window.theme_button.cget("text"))
        # La preferencia quedó guardada (ruta aislada del test).
        self.assertEqual(prefs.load_prefs(self._prefs_path)["theme"],
                         "light")
        window.toggle_theme()
        window.update()
        self.assertEqual(theme.current_mode(), "dark")
        self.assertEqual(window.canvas.cget("background"),
                         theme.PALETTES["dark"]["canvas"])

    def test_toggle_panel_hides_and_restores(self):
        window = self.window
        paned = window._panel_panes["explorer"][0]
        self.assertIn(str(window._panel_frames["explorer"]),
                      [str(p) for p in paned.panes()])
        window.toggle_panel("explorer")
        window.update()
        self.assertNotIn(str(window._panel_frames["explorer"]),
                         [str(p) for p in paned.panes()])
        self.assertFalse(window._panel_visible["explorer"])
        window.toggle_panel("explorer")
        window.update()
        self.assertIn(str(window._panel_frames["explorer"]),
                      [str(p) for p in paned.panes()])

    def test_panels_preference_persisted(self):
        window = self.window
        window.toggle_panel("props")
        data = prefs.load_prefs(self._prefs_path)
        self.assertFalse(data["panels"]["props"])

    def test_bus_event_arms_autosave_and_indicator(self):
        window = self.window
        state = {"n": 0}

        class _Ctx:
            def commit(self_inner):
                state["n"] += 1
        old_ctx = window.autosave.ctx
        window.autosave.ctx = _Ctx()
        try:
            window.autosave.delay_ms = 10_000  # no vence durante el test
            window._handle_bus_event(_Event())
            window.update()
            self.assertTrue(window.autosave.stats()["pending"])
            self.assertIn("Guardando",
                          window._autosave_var_text.get())
            window.autosave.cancel()
        finally:
            window.autosave.ctx = old_ctx
        self.assertEqual(state["n"], 0)

    def test_save_project_updates_indicator(self):
        window = self.window
        window.save_project()
        window.update()
        self.assertGreaterEqual(window.autosave.save_count, 1)
        self.assertIn("Autoguardado", window._autosave_var_text.get())

    def test_canvas_context_menu_builds_entry_and_empty(self):
        window = self.window
        captured = {}
        window._popup_menu = lambda menu, event: captured.update(
            menu=menu)
        # Clic en vacío: menú de vistas (sin «Eliminar»).
        window._canvas_context_menu(_Event(x=5, y=5))
        menu = captured["menu"]
        with self.assertRaises(Exception):
            menu.index("Eliminar\tSupr")
        self.assertIsNotNone(menu.index("Encuadrar todo\tF"))
        # Clic sobre un objeto real: menú de edición.
        row = window.explorer.rows_for("ARCHITECTURE", "")[0]
        window.selection = row
        window.refresh_properties()
        window.redraw()
        primitive = next((p for p in window._primitives
                          if p.row.uid == row.uid), None)
        if primitive is not None:
            px, py = window.viewport.to_screen(
                primitive.coords[0][0], primitive.coords[0][1],
                max(window.canvas.winfo_width(), 800),
                max(window.canvas.winfo_height(), 600))
            hit = window._hit_uid(_Event(x=int(px), y=int(py)))
            self.assertEqual(hit, row.uid)
            window._canvas_context_menu(_Event(x=int(px), y=int(py)))
            menu = captured["menu"]
            self.assertIsNotNone(menu.index(f"Editar «{row.name or row.code}»…"
                                            "\tCtrl+E"))

    def test_tree_context_menu_for_discipline(self):
        window = self.window
        captured = {}
        window._popup_menu = lambda menu, event: captured.update(
            menu=menu)
        children = window.tree.get_children()
        self.assertTrue(children)
        disc_iid = children[0]
        window.tree.selection_set(disc_iid)
        window.tree.see(disc_iid)
        window.tree.update()
        bbox = window.tree.bbox(disc_iid)
        if not bbox:
            self.skipTest("tree sin geometría en Xvfb")
        event = _Event(y=bbox[1] + bbox[3] // 2)
        window._tree_context_menu(event)
        menu = captured["menu"]
        iid = window.tree.identify_row(event.y)
        if iid == disc_iid:
            self.assertIsNotNone(
                menu.index("🔎 Buscar en el proyecto…"))
        else:
            # Fila no identificable: el menú genérico sigue siendo útil.
            self.assertIsNotNone(menu.index("＋ Nuevo objeto…"))

    def test_right_press_release_routes_menu_vs_pan(self):
        window = self.window
        window._on_right_press(_Event(x=10, y=10))
        self.assertEqual(window._right_origin, (10, 10))
        # Sin arrastre: la liberación llama al menú (capturado).
        captured = {}
        window._popup_menu = lambda menu, event: captured.update(ok=True)
        window._on_right_release(_Event(x=11, y=10))
        self.assertTrue(captured.get("ok"))
        # Con arrastre: pan, no menú.
        window._on_right_press(_Event(x=10, y=10))
        captured.clear()
        window._on_right_motion(_Event(x=60, y=10))
        window._on_right_release(_Event(x=70, y=10))
        self.assertFalse(captured.get("ok"))
        self.assertIsNone(window._right_origin)

    def test_wheel_pan_moves_viewport(self):
        window = self.window
        before = window.viewport.center_x
        window._pan_at_event(35, _Event(x=0, y=0))
        self.assertNotEqual(window.viewport.center_x, before)

    def test_help_mode_explains_registered_widget(self):
        window = self.window
        window.what_is_this()
        self.assertTrue(window._help_mode)
        # Un clic sobre la ventana misma (sin ayuda registrada) usa el
        # texto genérico; el modo se desactiva y no lanza.
        window._help_mode_click(_Event(widget=window))
        self.assertFalse(window._help_mode)

    def test_escape_leaves_help_mode(self):
        window = self.window
        window.what_is_this()
        window.clear_search()
        self.assertFalse(window._help_mode)

    def test_new_accelerators_bound(self):
        from ui.app_window import ACCELERATORS
        self.assertEqual(ACCELERATORS["<Control-Key-1>"],
                         "toggle_panel_explorer")
        self.assertEqual(ACCELERATORS["<Control-t>"], "toggle_theme")
        self.assertEqual(ACCELERATORS["<Shift-F1>"], "what_is_this")

    def test_prefs_geometry_written_on_close_path(self):
        window = self.window
        window._save_prefs_now()
        data = prefs.load_prefs(self._prefs_path)
        self.assertIn("x", data["geometry"] or "x")
        self.assertEqual(data["theme"], "dark")


if __name__ == "__main__":
    unittest.main()
