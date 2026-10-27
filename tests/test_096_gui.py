"""FASE 90 tests: graphical UI (spec sections 90-93).

Cubre: navegación por las 13 disciplinas (§91), buscador con los 9
campos (§92), sistema de estados de entidades y cálculos (§93), modelos
del lienzo (primitivas y viewport) y, si hay display disponible, un
smoke test de la ventana Tkinter real.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from core.entities.base import CalculationStatus, EntityStatus
from ui.disciplines import DISCIPLINES, DISCIPLINE_KEYS, SECURITY_SYSTEMS
from ui.models import (CanvasModel, EntityStateFlow, ExplorerModel,
                       ObjectRow, PropertiesModel, SEARCH_FIELDS,
                       SearchEngine, StateService, StatusModel, Viewport,
                       _wall_rectangle)


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - sin X/heroku/headless
        return False


DISPLAY = _display_available()


class TestDisciplines91(ARQGenTestCase):
    """§91: navegación por disciplina (todas sobre el mismo proyecto)."""

    def test_13_disciplines_in_spec_order(self):
        self.assertEqual(len(DISCIPLINES), 13)
        self.assertEqual(
            DISCIPLINE_KEYS,
            ("ARCHITECTURE", "STRUCTURE", "INSTALLATIONS", "CCTV", "FIRE",
             "INTRUSION", "ACCESS", "PERIMETER", "QTO", "BUDGET", "BIM",
             "COORDINATION", "DOCUMENTATION"))

    def test_security_disciplines_map_to_network_systems(self):
        systems = {d.key: d.systems for d in DISCIPLINES if d.systems}
        self.assertEqual(systems, {
            "CCTV": ("CCTV",), "FIRE": ("FIRE_ALARM",),
            "INTRUSION": ("INTRUSION",), "ACCESS": ("ACCESS_CONTROL",),
            "PERIMETER": ("PERIMETER",)})
        self.assertEqual(SECURITY_SYSTEMS,
                         {"CCTV", "FIRE_ALARM", "INTRUSION",
                          "ACCESS_CONTROL", "PERIMETER"})

    def test_explorer_rows_per_discipline_on_demo(self):
        context = self.demo_context()
        explorer = ExplorerModel(context)
        rows = explorer.all_rows()
        for discipline in ("ARCHITECTURE", "STRUCTURE", "INSTALLATIONS",
                           "CCTV", "FIRE", "INTRUSION", "ACCESS",
                           "PERIMETER", "QTO", "BUDGET", "BIM",
                           "COORDINATION"):
            self.assertGreater(
                len(rows[discipline]), 0,
                f"La disciplina {discipline} no tiene filas")
        # El demo no crea planos: Documentación puede estar vacía.
        self.assertIsInstance(rows["DOCUMENTATION"], list)
        context.close()

    def test_architecture_rows_carry_spec92_fields(self):
        context = self.demo_context()
        explorer = ExplorerModel(context)
        walls = [r for r in explorer.rows_for("ARCHITECTURE")
                 if r.type == "WALL"]
        self.assertTrue(walls)
        row = walls[0]
        self.assertTrue(row.uid)
        self.assertTrue(row.code)
        self.assertEqual(row.discipline, "ARCHITECTURE")
        self.assertTrue(row.level)
        context.close()


class TestSearch92(ARQGenTestCase):
    """§92: búsqueda por ID, código, nombre, descripción, tipo,
    disciplina, nivel, zona y etiqueta."""

    def test_search_fields_are_the_nine_of_spec(self):
        self.assertEqual(SEARCH_FIELDS, (
            "Todo", "ID", "Código", "Nombre", "Descripción", "Tipo",
            "Disciplina", "Nivel", "Zona", "Etiqueta"))

    def test_search_by_code_and_id(self):
        context = self.demo_context()
        engine = SearchEngine(ExplorerModel(context))
        by_code = engine.search("ARQ-WALL-001", "Código")
        self.assertEqual(len(by_code), 1)
        by_id = engine.search(by_code[0].uid, "ID")
        self.assertEqual(len(by_id), 1)
        self.assertEqual(by_id[0].uid, by_code[0].uid)
        context.close()

    def test_search_by_type_and_discipline(self):
        context = self.demo_context()
        engine = SearchEngine(ExplorerModel(context))
        cameras = engine.search("NODE", "Tipo")
        self.assertTrue(cameras)
        self.assertTrue(all(r.type == "NODE" for r in cameras))
        security = engine.search("CCTV", "Disciplina")
        self.assertTrue(security)
        self.assertTrue(all(r.discipline == "CCTV" for r in security))
        context.close()

    def test_search_by_level_zone_label(self):
        context = self.demo_context()
        engine = SearchEngine(ExplorerModel(context))
        level_name = explorer_level_name(context)
        hits = engine.search(level_name, "Nivel")
        self.assertTrue(hits)
        zones = engine.search("Zona", "Todo")  # no explota con vacío
        self.assertIsInstance(zones, list)
        context.close()

    def test_empty_query_returns_empty(self):
        context = self.demo_context()
        engine = SearchEngine(ExplorerModel(context))
        self.assertEqual(engine.search("", "Todo"), [])
        self.assertEqual(engine.search("   ", "Nombre"), [])
        context.close()


class TestStates93(ARQGenTestCase):
    """§93: sistema de estados de entidades y cálculos."""

    def test_entity_states_are_the_six_of_spec(self):
        self.assertEqual(
            [s.value for s in EntityStatus],
            ["DRAFT", "PROPOSED", "APPROVED", "ACTIVE", "SUPERSEDED",
             "ARCHIVED"])

    def test_calculation_states_are_the_six_of_spec(self):
        self.assertEqual(
            [s.value for s in CalculationStatus],
            ["PENDING", "RUNNING", "COMPLETED", "WARNING", "FAILED",
             "CANCELLED"])

    def test_transition_graph(self):
        self.assertEqual(EntityStateFlow.next_states("DRAFT"),
                         ("PROPOSED", "ARCHIVED"))
        self.assertEqual(EntityStateFlow.next_states("SUPERSEDED"),
                         ("ARCHIVED", "ACTIVE"))
        self.assertTrue(EntityStateFlow.can_transition("DRAFT", "PROPOSED"))
        self.assertFalse(EntityStateFlow.can_transition("DRAFT", "ACTIVE"))

    def test_state_change_persists_and_audits(self):
        context = self.demo_context()
        explorer = ExplorerModel(context)
        wall = [r for r in explorer.rows_for("ARCHITECTURE")
                if r.type == "WALL"][0]
        StateService(context).change_status(wall, "PROPOSED")
        self.assertEqual(wall.entity.status.value, "PROPOSED")
        self.assertEqual(wall.label, "PROPOSED")
        # Persistencia: recargar desde el repositorio
        reloaded = context.architecture.get("WALL", wall.uid)
        self.assertEqual(reloaded.status.value, "PROPOSED")
        # Auditoría del comando SET_STATUS
        audits = context.audit_repo.recent(limit=10,
                                           object_id=wall.uid)
        self.assertTrue(
            any(a.get("command") == "SET_STATUS" for a in audits))
        context.close()

    def test_invalid_transition_rejected(self):
        context = self.demo_context()
        explorer = ExplorerModel(context)
        wall = [r for r in explorer.rows_for("ARCHITECTURE")
                if r.type == "WALL"][0]
        with self.assertRaises(ValueError):
            StateService(context).change_status(wall, "ACTIVE")
        context.close()

    def test_synthetic_rows_have_no_states(self):
        context = self.demo_context()
        explorer = ExplorerModel(context)
        qto_row = explorer.rows_for("QTO")[0]
        with self.assertRaises(ValueError):
            StateService(context).change_status(qto_row, "PROPOSED")
        context.close()


class TestCanvasModels(ARQGenTestCase):
    """Primitivas del lienzo y viewport (§90)."""

    def test_architecture_primitives_demo(self):
        context = self.demo_context()
        model = CanvasModel(context, ExplorerModel(context))
        primitives = model.primitives("ARCHITECTURE")
        counts = {"space": 0, "wall": 0, "opening": 0}
        for primitive in primitives:
            counts[primitive.kind] = counts.get(primitive.kind, 0) + 1
        self.assertEqual(counts, {"space": 4, "wall": 7, "opening": 7})
        context.close()

    def test_network_primitives_follow_topology(self):
        context = self.demo_context()
        model = CanvasModel(context, ExplorerModel(context))
        primitives = model.primitives("CCTV")
        nodes = {p.row.uid: p.coords[0] for p in primitives
                 if p.kind == "node"}
        self.assertTrue(nodes)
        for primitive in primitives:
            if primitive.kind != "segment":
                continue
            start, end = primitive.coords
            # Extremos coinciden con posiciones de nodos de la red
            self.assertTrue(any(abs(start[0] - x) < 1e-9
                                and abs(start[1] - y) < 1e-9
                                for x, y in nodes.values()))
            self.assertTrue(any(abs(end[0] - x) < 1e-9
                                and abs(end[1] - y) < 1e-9
                                for x, y in nodes.values()))
        context.close()

    def test_structure_primitives(self):
        context = self.demo_context()
        model = CanvasModel(context, ExplorerModel(context))
        primitives = model.primitives("STRUCTURE")
        self.assertTrue(primitives)
        self.assertTrue(all(p.kind == "element" for p in primitives))
        context.close()

    def test_wall_rectangle_perpendicular_thickness(self):
        rect = _wall_rectangle((0, 0), (5, 0), 0.2)
        self.assertEqual(len(rect), 4)
        ys = sorted({round(p[1], 9) for p in rect})
        self.assertEqual(ys, [-0.1, 0.1])  # espesor perpendicular al eje

    def test_viewport_roundtrip_zoom_and_fit(self):
        viewport = Viewport()
        viewport.fit((0, 0, 30, 20), 800, 600)
        self.assertGreater(viewport.scale, Viewport.MIN_SCALE)
        self.assertLessEqual(viewport.scale, Viewport.MAX_SCALE)
        sx, sy = viewport.to_screen(10.0, 5.0, 800, 600)
        wx, wy = viewport.from_screen(sx, sy, 800, 600)
        self.assertAlmostEqual(wx, 10.0, places=6)
        self.assertAlmostEqual(wy, 5.0, places=6)
        for _ in range(50):  # el zoom queda acotado
            viewport.zoom(2.0)
        self.assertEqual(viewport.scale, Viewport.MAX_SCALE)
        for _ in range(80):
            viewport.zoom(0.5)
        self.assertEqual(viewport.scale, Viewport.MIN_SCALE)


class TestStatusPanel(ARQGenTestCase):
    """Panel inferior: avisos, log y estado de cálculos (§90/§93)."""

    def test_calculation_rows_use_spec93_statuses(self):
        context = self.demo_context()
        rows = StatusModel(context).calculation_rows()
        self.assertTrue(rows)
        valid = {s.value for s in CalculationStatus}
        for row in rows:
            self.assertIn(row["status"], valid)
        context.close()

    def test_log_lines_from_event_repository(self):
        context = self.demo_context()
        lines = StatusModel(context).log_lines(limit=400)
        self.assertTrue(lines)
        # PROJECT_CREATED es el primer evento del demo: puede quedar
        # fuera de las últimas N líneas, pero el log debe contener
        # eventos del ciclo de vida del proyecto.
        self.assertTrue(any("OBJECT_" in line or "PROJECT_" in line
                            for line in lines))
        context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestMainWindowTk(ARQGenTestCase):
    """Smoke test de la ventana real (se ejecuta con display o Xvfb)."""

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

    def test_window_boots_with_13_disciplines(self):
        self.assertIn("ARQ GEN", self.window.title())
        self.assertEqual(len(self.window.tree.get_children()), 13)

    def test_tree_selection_shows_properties_and_highlight(self):
        wall = [r for r in self.window.explorer.rows_for("ARCHITECTURE")
                if r.type == "WALL"][0]
        self.window.tree.selection_set(wall.uid)
        self.window.tree.focus(wall.uid)
        self.window.on_tree_select()
        self.window.update()
        self.assertIsNotNone(self.window.selection)
        self.assertEqual(self.window.selection.uid, wall.uid)
        self.assertGreater(len(self.window.props.get_children()), 5)

    def test_search_shows_results_in_tree(self):
        self.window.search_entry.insert(0, "ARQ-WALL")
        self.window.run_search()
        self.window.update()
        self.assertGreater(len(self.window._result_rows), 0)
        self.assertEqual(self.window.tree.get_children()[0], "results")

    def test_discipline_switch_draws_network(self):
        self.window.current_discipline = "CCTV"
        self.window.refresh_all()
        self.window.update()
        self.assertGreater(len(self.window._primitives), 0)
        # y vuelta a Arquitectura dibuja el plano
        self.window.current_discipline = "ARCHITECTURE"
        self.window.refresh_all()
        self.window.update()
        kinds = {p.kind for p in self.window._primitives}
        self.assertIn("wall", kinds)
        self.assertIn("space", kinds)

    def test_fit_and_zoom_update_canvas(self):
        self.window.fit_view()
        self.window.update()
        scale = self.window.viewport.scale
        self.window.zoom(1.25)
        self.window.update()
        self.assertGreater(self.window.viewport.scale, scale)

    def test_state_change_via_state_service(self):
        wall = [r for r in self.window.explorer.rows_for("ARCHITECTURE")
                if r.type == "WALL"][0]
        StateService(self.context).change_status(wall, "PROPOSED")
        self.assertEqual(wall.label, "PROPOSED")

    def test_status_panels_populated(self):
        self.window.refresh_calcs()
        self.assertGreater(len(self.window.calc_tree.get_children()), 0)
        self.window.run_validation()
        text = self.window.warnings_text.get("1.0", "end").strip()
        self.assertIsInstance(text, str)


def explorer_level_name(context) -> str:
    for level in context.architecture.list("LEVEL", context.project.id):
        if level.name:
            return level.name
    return ""


if __name__ == "__main__":
    unittest.main()
