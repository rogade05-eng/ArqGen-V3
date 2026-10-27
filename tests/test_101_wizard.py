"""v1.7.2: asistente dinámico de diseño + fix del selector de niveles.

Cubre:
- ui.models.choice_values: el fix del bug por el que el desplegable de
  nivel mostraba letras sueltas (list("levels")) en lugar de consultar
  los niveles reales en el momento de abrir el formulario.
- Etiquetas en español: STATUS_ES / status_label (§93), EVENT_ES /
  describe_event (diario) y CALC_TYPE_ES / calc_type_label.
- ui.wizard: validación paso a paso, geometría de muros y vanos, plan
  declarativo y ejecución end-to-end por las fachadas oficiales.
- Ventana real: el botón «Asistente de local» abre el diálogo de 4
  pasos y el flujo completo crea el local con sus muros y vanos.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from ui import wizard as wiz
from ui.models import (CALC_TYPE_ES, EVENT_ES, STATUS_ES,
                       EntityStateFlow, choice_values, describe_event,
                       status_label, calc_type_label)
from ui.wizard import LocalWizardData


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


class TestChoiceValues(unittest.TestCase):
    """El fix del selector de niveles (bug del muro sin niveles)."""

    def test_dynamic_source_string_queries_resolver(self):
        levels = []
        values = choice_values("levels", lambda source: levels)
        # options="levels" NO debe partirse en letras: se consulta la
        # fuente dinámica.
        self.assertEqual(values, levels)

    def test_dynamic_source_returns_real_levels(self):
        fake = ["Planta baja", "Piso 2"]
        values = choice_values("levels", lambda source: fake)
        self.assertEqual(values, ["Planta baja", "Piso 2"])

    def test_fixed_tuple_untouched(self):
        kinds = ("PUBLIC", "PRIVATE")
        self.assertEqual(choice_values(kinds, lambda s: []),
                         ["PUBLIC", "PRIVATE"])

    def test_none_gives_empty(self):
        self.assertEqual(choice_values(None, lambda s: ["x"]), [])

    def test_wall_and_space_specs_use_dynamic_levels(self):
        from ui.models import CREATE_SPECS
        for entity_type in ("SPACE", "WALL", "ELEMENT"):
            spec = CREATE_SPECS[entity_type][1]
            level_field = next(f for f in spec if f[0] == "level_ref")
            self.assertEqual(level_field[2], "choice")
            self.assertIsInstance(level_field[4], str)


class TestSpanishLabels(unittest.TestCase):
    """La interfaz no debe mostrar inglés al usuario."""

    def test_status_labels_cover_all_spec93_states(self):
        from core.entities.base import EntityStatus
        for status in EntityStatus:
            self.assertIn(status.value, STATUS_ES)

    def test_status_label_translates_with_traceability(self):
        self.assertEqual(status_label("DRAFT"), "Borrador (DRAFT)")
        self.assertEqual(status_label("ACTIVE"), "Activo (ACTIVE)")
        self.assertEqual(status_label(""), "")

    def test_transitions_still_use_spec_values(self):
        self.assertEqual(EntityStateFlow.next_states("DRAFT"),
                         ("PROPOSED", "ARCHIVED"))

    def test_describe_event_keeps_code_for_traceability(self):
        text = describe_event("OBJECT_CREATED")
        self.assertIn("Objeto creado", text)
        self.assertIn("OBJECT_CREATED", text)

    def test_describe_event_unknown_passthrough(self):
        self.assertEqual(describe_event("WHATEVER"), "WHATEVER")
        self.assertEqual(describe_event(""), "")

    def test_event_dictionary_covers_creation_flow(self):
        for event in ("OBJECT_CREATED", "SPACE_CHANGED",
                      "GEOMETRY_CHANGED", "OBJECT_DELETED"):
            self.assertIn(event, EVENT_ES)

    def test_calc_type_labels(self):
        self.assertEqual(calc_type_label("QTO"), "Cantidades (QTO)")
        self.assertIn("QTO", CALC_TYPE_ES)
        self.assertEqual(calc_type_label("RARE"), "RARE")


class TestWizardValidation(unittest.TestCase):
    """Validación amable paso a paso (mensajes en español)."""

    def test_parse_float_accepts_comma_decimal(self):
        self.assertAlmostEqual(wiz.parse_float_es("3,5", "Ancho"), 3.5)
        self.assertAlmostEqual(wiz.parse_float_es(" 4.0 ", "Ancho"), 4.0)
        with self.assertRaises(ValueError):
            wiz.parse_float_es("abc", "Ancho")
        with self.assertRaises(ValueError):
            wiz.parse_float_es("", "Ancho")

    def test_step1_requires_level_and_name(self):
        errors = wiz.validate_step(0, LocalWizardData())
        self.assertTrue(any("nivel" in e.lower() for e in errors))
        self.assertTrue(any("nombre" in e.lower() for e in errors))

    def test_step1_ok_with_new_level(self):
        data = LocalWizardData(new_level=True, new_level_name="Piso 2",
                               name="Oficina")
        self.assertEqual(wiz.validate_step(0, data), [])

    def test_step1_ok_with_existing_level(self):
        data = LocalWizardData(level_ref="Nivel 1", name="Oficina")
        self.assertEqual(wiz.validate_step(0, data), [])

    def test_step2_rejects_zero_measures(self):
        data = LocalWizardData(width_m=0.0, depth_m=0.0, name="X",
                               level_ref="L")
        errors = wiz.validate_step(1, data)
        self.assertTrue(any("mayores que" in e for e in errors))

    def test_step2_rejects_wall_thickness_eating_room(self):
        data = LocalWizardData(width_m=0.3, depth_m=0.3,
                               thickness_m=0.2, name="X", level_ref="L")
        errors = wiz.validate_step(1, data)
        self.assertTrue(any("espesor" in e.lower() for e in errors))

    def test_step2_ok_with_defaults(self):
        data = LocalWizardData(name="X", level_ref="L")
        self.assertEqual(wiz.validate_step(1, data), [])

    def test_step3_door_does_not_fit(self):
        data = LocalWizardData(name="X", level_ref="L", width_m=0.5,
                               depth_m=3.0, with_door=True,
                               door_width_m=0.9, door_side="Frente")
        errors = wiz.validate_step(2, data)
        self.assertTrue(any("no cabe" in e for e in errors))

    def test_step3_door_and_window_same_side_overlap(self):
        data = LocalWizardData(name="X", level_ref="L", width_m=2.0,
                               depth_m=3.0, with_door=True,
                               door_width_m=1.2, door_side="Frente",
                               with_window=True, window_width_m=1.2,
                               window_side="Frente")
        errors = wiz.validate_step(2, data)
        self.assertTrue(any("juntas" in e for e in errors))

    def test_step3_ok_with_defaults(self):
        data = LocalWizardData(name="X", level_ref="L",
                               with_window=True)
        self.assertEqual(wiz.validate_step(2, data), [])

    def test_summary_step_always_passes(self):
        self.assertEqual(wiz.validate_step(3, LocalWizardData()), [])


class TestWizardGeometryAndPlan(unittest.TestCase):
    """Geometría de los 4 muros, vanos centrados y orden del plan."""

    def test_side_walls_clockwise(self):
        data = LocalWizardData(x0_m=1.0, y0_m=2.0, width_m=4.0,
                               depth_m=3.0)
        self.assertEqual(wiz.side_wall(data, "Frente"),
                         ((1.0, 2.0), (5.0, 2.0)))
        self.assertEqual(wiz.side_wall(data, "Derecha"),
                         ((5.0, 2.0), (5.0, 5.0)))
        self.assertEqual(wiz.side_wall(data, "Fondo"),
                         ((5.0, 5.0), (1.0, 5.0)))
        self.assertEqual(wiz.side_wall(data, "Izquierda"),
                         ((1.0, 5.0), (1.0, 2.0)))

    def test_plan_without_new_level(self):
        data = LocalWizardData(level_ref="Nivel 1", name="Sala",
                               with_door=True, with_window=True)
        plan = wiz.build_plan(data)
        ops = [op for op, _p in plan]
        self.assertEqual(ops, ["SPACE", "WALL", "WALL", "WALL", "WALL",
                               "DOOR", "WINDOW"])
        boundary = plan[0][1]["boundary"]
        self.assertEqual(len(boundary), 4)

    def test_plan_with_new_level_first(self):
        data = LocalWizardData(new_level=True, new_level_name="Piso 2",
                               name="Sala")
        plan = wiz.build_plan(data)
        self.assertEqual(plan[0][0], "LEVEL")
        self.assertEqual(plan[0][1]["name"], "Piso 2")

    def test_door_offset_centered_on_front(self):
        data = LocalWizardData(level_ref="L", name="S", width_m=4.0,
                               depth_m=3.0, with_door=True,
                               door_width_m=0.9, door_side="Frente")
        plan = wiz.build_plan(data)
        door = next(p for p in plan if p[0] == "DOOR")[1]
        self.assertAlmostEqual(door["offset_m"], (4.0 - 0.9) / 2.0)

    def test_window_offset_uses_its_own_side(self):
        data = LocalWizardData(level_ref="L", name="S", width_m=4.0,
                               depth_m=3.0, with_window=True,
                               window_width_m=1.2, window_side="Derecha")
        plan = wiz.build_plan(data)
        window = next(p for p in plan if p[0] == "WINDOW")
        self.assertAlmostEqual(window[1]["offset_m"], (3.0 - 1.2) / 2.0)

    def test_vano_wall_indexes_point_to_wall_commands(self):
        data = LocalWizardData(level_ref="L", name="S", with_door=True,
                               door_side="Derecha", with_window=True,
                               window_side="Fondo")
        plan = wiz.build_plan(data)
        wall_positions = [i for i, (op, _p) in enumerate(plan)
                          if op == "WALL"]
        door = next(p for p in plan if p[0] == "DOOR")
        window = next(p for p in plan if p[0] == "WINDOW")
        # Derecha = muro 1, Fondo = muro 2 (orden horario).
        self.assertEqual(door[1]["wall_ref"], wall_positions[1])
        self.assertEqual(window[1]["wall_ref"], wall_positions[2])

    def test_summary_mentions_pieces(self):
        data = LocalWizardData(level_ref="Nivel 1", name="Sala",
                               with_door=True)
        text = wiz.step_summary(data)
        for word in ("Sala", "Nivel 1", "Muros", "Puerta"):
            self.assertIn(word, text)

    def test_data_from_values_collects_errors(self):
        data = LocalWizardData()
        errors = wiz.data_from_values(
            1, {"x0_m": "1", "y0_m": "2", "width_m": "cuatro",
                "depth_m": "3", "thickness_m": "0,2"}, data)
        self.assertTrue(errors)
        self.assertAlmostEqual(data.x0_m, 1.0)
        self.assertAlmostEqual(data.thickness_m, 0.2)

    def test_field_names_complete(self):
        names = wiz.wizard_field_names()
        for expected in ("level_ref", "name", "width_m", "depth_m",
                         "door_side", "window_side"):
            self.assertIn(expected, names)


class TestWizardApply(ARQGenTestCase):
    """Ejecución end-to-end por las fachadas oficiales."""

    def _context(self):
        return self.application.create_project(
            self.project_path("wizard.arqgen"), name="Proyecto Asistente")

    def test_apply_with_new_level_and_vanos(self):
        context = self._context()
        try:
            data = LocalWizardData(new_level=True,
                                   new_level_name="Piso 1",
                                   name="Sala de ventas",
                                   width_m=4.0, depth_m=3.0,
                                   thickness_m=0.2, with_door=True,
                                   door_side="Frente", with_window=True,
                                   window_side="Fondo")
            created = wiz.apply_plan(data, context)
            self.assertTrue(created["level"])
            self.assertTrue(created["space"])
            self.assertEqual(len(created["walls"]), 4)
            self.assertTrue(created["door"])
            self.assertTrue(created["window"])
            pid = context.project.id
            spaces = context.architecture.list("SPACE", pid)
            self.assertEqual(len(spaces), 1)
            self.assertEqual(spaces[0].name, "Sala de ventas")
            walls = context.architecture.list("WALL", pid)
            self.assertEqual(len(walls), 4)
            # Los vanos quedaron colgados de muros reales.
            openings = (context.architecture.list("DOOR", pid)
                        + context.architecture.list("WINDOW", pid))
            self.assertEqual(len(openings), 2)
            wall_ids = {w.id for w in walls}
            for opening in openings:
                self.assertIn(opening.wall_id, wall_ids)
            # La geometría del local es el rectángulo pedido.
            self.assertEqual(len(spaces[0].boundary), 4)
        finally:
            context.close()

    def test_apply_on_existing_level_without_vanos(self):
        from services.architecture_service import ArchitectureService
        context = self._context()
        try:
            ArchitectureService(context).create_level(name="Planta baja")
            data = LocalWizardData(level_ref="Planta baja",
                                   name="Depósito", with_door=False,
                                   with_window=False)
            created = wiz.apply_plan(data, context)
            self.assertEqual(created["level"], "")
            self.assertFalse(created["door"])
            self.assertFalse(created["window"])
            pid = context.project.id
            self.assertEqual(
                len(context.architecture.list("WALL", pid)), 4)
        finally:
            context.close()

    def test_apply_is_audited_and_evented(self):
        context = self._context()
        try:
            data = LocalWizardData(new_level=True,
                                   new_level_name="Nivel W",
                                   name="Local W")
            wiz.apply_plan(data, context)
            events = context.events_repo.recent(limit=200)
            types = {e.get("type") for e in events}
            self.assertIn("OBJECT_CREATED", types)
            self.assertIn("SPACE_CHANGED", types)
            audits = context.audit_repo.recent(limit=200)
            commands = {a.get("command") for a in audits}
            self.assertIn("CREATE_ENTITY", commands)
        finally:
            context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestWizardWindow(ARQGenTestCase):
    """Ventana real: el asistente se abre y completa el flujo."""

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

    def _open(self):
        self.window.open_design_wizard()
        return self.window._wizard_dialog

    def test_wizard_tooltip_exists(self):
        from ui.help import TOOLTIPS
        self.assertIn("wizard", TOOLTIPS)

    def test_wizard_opens_with_four_steps(self):
        dialog = self._open()
        try:
            self.assertIn("Paso 1 de 4", dialog._wiz_step_var.get())
            self.assertEqual(dialog._wiz_state["step"], 0)
            self.assertIn("¿Dónde va el local?",
                          dialog._wiz_step_var.get())
        finally:
            dialog.destroy()

    def test_wizard_level_combo_lists_real_levels(self):
        """El desplegable del asistente ofrece los niveles REALES."""
        dialog = self._open()
        try:
            values = dialog._wiz_widgets["level_combo"].cget("values")
            levels = self.context.architecture.list(
                "LEVEL", self.context.project.id)
            names = [lv.name for lv in levels]
            for name in names:
                self.assertIn(name, values)
            # Y no la palabra partida en letras (bug v1.7.1).
            self.assertNotIn("l", values)
        finally:
            dialog.destroy()

    def test_wizard_full_flow_creates_local(self):
        pid = self.context.project.id
        before_space = len(self.context.architecture.list("SPACE", pid))
        before_walls = len(self.context.architecture.list("WALL", pid))
        before_doors = len(self.context.architecture.list("DOOR", pid))
        dialog = self._open()
        try:
            widgets = dialog._wiz_widgets
            # Paso 1: nivel preseleccionado + nombre del local.
            widgets["name"].delete(0, "end")
            widgets["name"].insert(0, "Local del asistente")
            dialog._wiz_next()
            # Paso 2: medidas por defecto (4×3, coma decimal).
            dialog._wiz_next()
            # Paso 3: puerta activada por defecto.
            dialog._wiz_next()
            # Paso 4: resumen visible y botón de creación.
            self.assertIn("Paso 4 de 4", dialog._wiz_step_var.get())
            summary = widgets["summary"].get("1.0", "end")
            self.assertIn("Local del asistente", summary)
            self.assertIn("Puerta", summary)
            dialog._wiz_next()  # crea
            self.window.update()
        finally:
            dialog.destroy()
        pid = self.context.project.id
        self.assertEqual(
            len(self.context.architecture.list("SPACE", pid)),
            before_space + 1)
        self.assertEqual(
            len(self.context.architecture.list("WALL", pid)),
            before_walls + 4)
        self.assertEqual(
            len(self.context.architecture.list("DOOR", pid)),
            before_doors + 1)

    def test_wizard_validation_blocks_empty_name(self):
        from unittest import mock
        dialog = self._open()
        try:
            widgets = dialog._wiz_widgets
            widgets["name"].delete(0, "end")  # obligatorio vacío
            with mock.patch("ui.app_window.messagebox.showwarning") as warn:
                dialog._wiz_next()
                warn.assert_called_once()  # aviso amable, sin bloquear
            # No avanza: sigue en el paso 1 (la validación lo bloquea).
            self.assertEqual(dialog._wiz_state["step"], 0)
            self.assertIn("Paso 1 de 4", dialog._wiz_step_var.get())
        finally:
            dialog.destroy()

    def test_wizard_back_button_preserves_data(self):
        dialog = self._open()
        try:
            widgets = dialog._wiz_widgets
            widgets["name"].delete(0, "end")
            widgets["name"].insert(0, "Mi local")
            dialog._wiz_next()  # → paso 2
            self.assertEqual(dialog._wiz_state["step"], 1)
            dialog._wiz_back()  # → paso 1
            self.assertEqual(dialog._wiz_state["step"], 0)
            self.assertEqual(dialog._wiz_data.name, "Mi local")
        finally:
            dialog.destroy()

    def test_wizard_new_level_option_switches_fields(self):
        dialog = self._open()
        try:
            widgets = dialog._wiz_widgets
            combo = widgets["level_combo"]
            combo.set(wiz.NUEVO_NIVEL)
            combo.event_generate("<<ComboboxSelected>>")
            dialog.update()
            self.assertTrue(dialog._wiz_data.new_level)
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
