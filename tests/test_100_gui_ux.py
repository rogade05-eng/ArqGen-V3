"""Mejora UX v1.7.1: tema oscuro, ayuda dinámica y guía de flujo.

Cubre:
- ui/theme: paleta del lienzo completa y aplicación del tema ttk.
- ui/help: contenido de tooltips/ayudas de campos, motor de siguiente
  paso (next_hint) y guía rápida de 4 pasos.
- Ventana real (con display): tema aplicado, tooltips registrados,
  ecos en la barra de estado, mensajes dinámicos de búsqueda y
  validación, tarjeta de bienvenida en proyectos vacíos.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from ui import theme
from ui.disciplines import DISCIPLINES
from ui.help import (DEFAULT_HINT, FIELD_HINTS, GUIDE_STEPS, MENU_HINTS,
                     TOOLTIPS, next_hint)
from ui.models import CREATE_SPECS
from ui.app_window import ACCELERATORS, PALETTE


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

# Controles que DEBEN tener ayuda dinámica (barra de herramientas,
# paneles de propiedades y lienzo).
REQUIRED_TOOLTIPS = (
    "guide", "fit", "zoom_in", "zoom_out", "new_object", "edit",
    "search_field", "search_entry", "search_btn", "clear_btn",
    "level_combo", "props_edit", "state_btn", "canvas", "vista3d",
)

# Cascadas de menú que deben explicarse al abrirse.
REQUIRED_MENU_HINTS = ("Archivo", "Editar", "Ver", "Herramientas",
                       "Ayuda")


class TestTheme(unittest.TestCase):
    """Paleta y tema oscuro (ui/theme)."""

    def test_canvas_dark_palette_complete(self):
        for key in ("space_fill", "space_text", "wall", "grid", "axis",
                    "selection", "welcome_card", "welcome_border",
                    "welcome_title", "welcome_text"):
            self.assertIn(key, theme.CANVAS_DARK)
            self.assertTrue(theme.CANVAS_DARK[key].startswith("#"))

    def test_entity_colors_cover_original_keys(self):
        # La paleta de la ventana debe seguir resolviendo todos los
        # tipos/sistemas de la PALETTE histórica + selección/rejilla.
        for key in ("space", "wall", "DOOR", "WINDOW", "OPENING", "BEAM",
                    "COLUMN", "SLAB", "FOUNDATION", "POWER", "LIGHTING",
                    "HVAC", "WATER", "DRAINAGE", "STORMWATER", "GAS",
                    "TELECOM", "CCTV", "FIRE_ALARM", "INTRUSION",
                    "ACCESS_CONTROL", "PERIMETER", "DATA", "FIRE",
                    "ELECTRICAL", "SANITARY", "SECURITY"):
            self.assertIn(key, PALETTE, f"PALETTE sin {key}")
        self.assertEqual(PALETTE["selection"],
                         theme.CANVAS_DARK["selection"])

    def test_dark_text_is_light(self):
        # Contraste: el texto principal debe ser claro sobre fondo oscuro.
        r_text = int(theme.COL_TEXT[1:3], 16)
        r_bg = int(theme.COL_BG[1:3], 16)
        self.assertGreater(r_text, r_bg)

    @unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
    def test_apply_dark_theme_configures_styles(self):
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.withdraw()
        try:
            colors = theme.apply_dark_theme(root)
            style = ttk.Style(root)
            self.assertEqual(colors["bg"], theme.COL_BG)
            self.assertEqual(root.cget("background"), theme.COL_BG)
            self.assertEqual(
                style.lookup("TButton", "background"), theme.COL_RAISE)
            self.assertEqual(
                style.lookup("Treeview", "background"), theme.COL_FIELD)
            self.assertTrue(style.lookup("TNotebook.Tab", "background"))
        finally:
            root.destroy()


class TestHelpContent(unittest.TestCase):
    """Contenido de la ayuda (ui/help): completo y legible."""

    def test_required_tooltips_present(self):
        for key in REQUIRED_TOOLTIPS:
            self.assertIn(key, TOOLTIPS, f"falta tooltip «{key}»")
            self.assertGreater(len(TOOLTIPS[key].strip()), 10)
            self.assertLess(len(TOOLTIPS[key]), 220)

    def test_field_hints_cover_every_create_spec_param(self):
        for entity_type, (_discipline, fields) in CREATE_SPECS.items():
            for param, _label, _kind, _req, _opts, _default in fields:
                self.assertIn(
                    param, FIELD_HINTS,
                    f"{entity_type}.{param} sin ayuda dinámica")

    def test_menu_hints_cover_the_five_cascades(self):
        labels = {d.label for d in DISCIPLINES}
        for label in REQUIRED_MENU_HINTS:
            self.assertIn(label, MENU_HINTS)
            self.assertGreater(len(MENU_HINTS[label]), 20)
        # Ninguna pista de menú confunde disciplinas con menús.
        self.assertFalse(labels & set(MENU_HINTS))

    def test_guide_has_four_steps(self):
        self.assertEqual(len(GUIDE_STEPS), 4)
        for title, text in GUIDE_STEPS:
            self.assertTrue(title.strip())
            self.assertGreater(len(text.strip()), 40)

    def test_tooltips_are_orientation_language(self):
        # Lenguaje orientador: segunda persona, sin tecnicismos duros.
        joined = " ".join(TOOLTIPS.values()).lower()
        self.assertIn("para", joined)


class TestNextHint(unittest.TestCase):
    """Motor de siguiente paso: orden del flujo natural de trabajo."""

    def test_empty_project_suggests_first_space(self):
        hint = next_hint()
        # v1.8.0: la puerta de entrada es el asistente de EDIFICACIÓN
        # (con el de local como alternativa).
        self.assertIn("edificación", hint)
        self.assertIn("Asistente", hint)
        self.assertIn("local", hint)

    def test_spaces_suggest_walls(self):
        self.assertIn("muro", next_hint(spaces=3, walls=0))

    def test_walls_suggest_openings(self):
        self.assertIn("puerta", next_hint(spaces=2, walls=5, doors=0))

    def test_modelled_suggest_calculations(self):
        self.assertIn("Recalcular", next_hint(spaces=2, walls=5, doors=3,
                                              calculations=0))

    def test_calculated_suggest_export_or_review(self):
        clean = next_hint(spaces=2, walls=5, doors=3, calculations=2,
                          warnings=0)
        self.assertIn("exportar", clean.lower())
        with_warn = next_hint(spaces=2, walls=5, doors=3, calculations=2,
                              warnings=4)
        self.assertIn("Avisos", with_warn)

    def test_searching_has_priority(self):
        self.assertIn("resultado", next_hint(searching=True, spaces=0))

    def test_default_hint_is_friendly(self):
        self.assertIn("Guía rápida", DEFAULT_HINT)

    def test_warning_count_minus_one_means_not_validated(self):
        hint = next_hint(spaces=2, walls=5, doors=3, calculations=2,
                         warnings=-1)
        self.assertNotIn("exportar", hint.lower())


class TestAcceleratorsF1(unittest.TestCase):
    """F1 abre la guía rápida y todos los atajos siguen válidos."""

    def test_f1_maps_to_quick_guide(self):
        self.assertEqual(ACCELERATORS.get("<F1>"), "show_quick_guide")
        from ui.app_window import ARQGenWindow
        for sequence, method_name in ACCELERATORS.items():
            self.assertTrue(
                callable(getattr(ARQGenWindow, method_name, None)),
                f"{sequence} -> {method_name} inexistente")


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestWindowUX(ARQGenTestCase):
    """Ventana real: tema, tooltips y mensajes dinámicos."""

    def setUp(self):
        super().setUp()
        from ui.app_window import ARQGenWindow
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        super().tearDown()

    def test_window_boots_dark_with_13_disciplines(self):
        self.assertEqual(len(self.window.tree.get_children()), 13)
        self.assertEqual(self.window.canvas.cget("background"),
                         theme.COL_CANVAS)
        self.assertEqual(self.window.cget("background"), theme.COL_BG)

    def test_tooltips_registered_and_echo_status_bar(self):
        self.assertGreaterEqual(len(self.window._tooltips), 14)
        tooltip = self.window._tooltips[0]
        tooltip._on_enter()
        self.assertEqual(self.window.status_var.get(), tooltip.text)
        tooltip._on_leave()
        self.assertEqual(self.window.status_var.get(),
                         self.window._status_base)
        self.assertTrue(self.window._status_base)

    def test_search_messages_are_dynamic(self):
        self.window.search_entry.insert(0, "ARQ-WALL")
        self.window.run_search()
        self.assertIn("resultado", self.window.status_var.get())
        self.window.clear_search()
        self.assertTrue(self.window.status_var.get())

    def test_validation_reports_to_guidance_channel(self):
        self.window.run_validation()
        self.window.update()
        self.assertIn("Validación", self.window.status_var.get())
        self.assertTrue(self.window.warnings_text.get("1.0", "end").strip())

    def test_empty_project_draws_welcome_card(self):
        empty_path = self._tmp_path("ux_empty.arqgen")
        if empty_path.exists():
            empty_path.unlink()
        ctx = self.application.create_project(str(empty_path),
                                              name="UX vacío")
        try:
            win = type(self.window)(ctx, self.application)
            win.update()
            texts = [win.canvas.itemcget(item, "text")
                     for item in win.canvas.find_all()
                     if win.canvas.type(item) == "text"]
            self.assertTrue(any("Empecemos" in t for t in texts),
                            texts)
            self.assertIn("+ Objeto", " ".join(texts))
            win.destroy()
        finally:
            ctx.close()

    def test_quick_guide_opens_and_closes(self):
        import tkinter as tk
        self.window.after(200, lambda: [
            child.destroy() for child in self.window.winfo_children()
            if isinstance(child, tk.Toplevel)
            and "Gu" in child.title()])
        self.window.show_quick_guide()  # wait_window retorna al cerrar
        self.window.update()

    def test_menu_hints_attached_to_all_cascades(self):
        menubar = self.window.nametowidget(self.window.cget("menu"))
        for label in REQUIRED_MENU_HINTS:
            index = menubar.index(label)
            self.assertEqual(menubar.type(index), "cascade", label)
            submenu = menubar.nametowidget(menubar.entrycget(index, "menu"))
            self.assertTrue(submenu.cget("postcommand"), label)

    def _tmp_path(self, name: str):
        import tempfile
        from pathlib import Path
        return Path(tempfile.gettempdir()) / name


if __name__ == "__main__":
    unittest.main()
