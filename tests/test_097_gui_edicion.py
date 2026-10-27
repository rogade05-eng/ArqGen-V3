"""FASE 90.1 tests: editable GUI (property editing, create, delete,
zoom at cursor and keyboard accelerators).

Todo el comportamiento es headless (ui.models): la edición pasa por las
mismas fachadas que la CLI, deja auditoría §71 con snapshots completos
y es reversible con el undo persistente §77.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from ui.models import (CREATE_SPECS, EditService, ExplorerModel,
                       ObjectRow, PropertyEditor, Viewport)
from ui.app_window import ACCELERATORS, ARQGenWindow


class _EdicionBase(ARQGenTestCase):
    """Contexto de demo + servicios de edición."""

    def setUp(self) -> None:
        super().setUp()
        self.ctx = self.demo_context()
        self.explorer = ExplorerModel(self.ctx)
        self.edit = EditService(self.ctx, self.explorer)

    def _row(self, discipline: str, entity_type: str, index: int = 0):
        rows = [r for r in self.explorer.rows_for(discipline)
                if r.type == entity_type and r.entity is not None]
        if not rows:
            self.fail(f"Sin filas {entity_type} en {discipline}")
        return rows[index]

    def _audit_entries(self, command: str, object_id: str):
        return [e for e in self.ctx.audit_repo.recent(limit=500)
                if e["command"] == command and e["object_id"] == object_id]


class TestPropertyEditor(_EdicionBase):
    """Edición de propiedades con auditoría, eventos y undo."""

    def test_edit_str_field_persists(self):
        row = self._row("ARCHITECTURE", "SPACE")
        new_name = f"Local editado {row.code}"
        PropertyEditor.edit(self.ctx, row, "name", new_name)
        saved = self.ctx.architecture.get("SPACE", row.uid)
        self.assertEqual(saved.name, new_name)

    def test_edit_float_accepts_comma_decimal(self):
        row = self._row("ARCHITECTURE", "WALL")
        PropertyEditor.edit(self.ctx, row, "thickness_m", "0,35")
        self.assertAlmostEqual(
            self.ctx.architecture.get("WALL", row.uid).thickness_m, 0.35)

    def test_edit_point_tuple(self):
        row = self._row("ARCHITECTURE", "WALL")
        PropertyEditor.edit(self.ctx, row, "start", "(12, 4)")
        self.assertEqual(
            self.ctx.architecture.get("WALL", row.uid).start, (12.0, 4.0))
        # length_m es derivada: coherente tras mover el extremo.
        self.assertAlmostEqual(
            self.ctx.architecture.get("WALL", row.uid).length_m,
            ((12.0 - row.entity.end[0]) ** 2 + (4.0 - row.entity.end[1]) ** 2)
            ** 0.5)

    def test_edit_node_coordinates(self):
        row = self._row("INSTALLATIONS", "NODE")
        PropertyEditor.edit(self.ctx, row, "x", "55.5")
        self.assertAlmostEqual(
            self.ctx.installations.get("NODE", row.uid).x, 55.5)

    def test_edit_appends_update_entity_audit_with_snapshots(self):
        row = self._row("ARCHITECTURE", "SPACE")
        old_name = row.entity.name
        PropertyEditor.edit(self.ctx, row, "name", "Nombre nuevo")
        entries = self._audit_entries("UPDATE_ENTITY", row.uid)
        self.assertTrue(entries, "La edición debe auditar UPDATE_ENTITY")
        entry = entries[-1]
        self.assertEqual(entry["old_value"].get("name"), old_name)
        saved = self.ctx.architecture.get("SPACE", row.uid)
        self.assertEqual(saved.name, "Nombre nuevo")

    def test_edit_emits_object_updated(self):
        received = []
        self.ctx.event_bus.subscribe("OBJECT_UPDATED", received.append)
        row = self._row("ARCHITECTURE", "SPACE")
        PropertyEditor.edit(self.ctx, row, "name", "Con evento")
        self.assertTrue(any(
            getattr(e, "payload", {}).get("id") == row.uid
            for e in received))

    def test_edit_is_undoable(self):
        row = self._row("ARCHITECTURE", "WALL")
        old_thickness = row.entity.thickness_m
        PropertyEditor.edit(self.ctx, row, "thickness_m", "0.42")
        from app.undo_service import PersistentUndoService
        PersistentUndoService(self.ctx).undo()
        self.ctx.commit()
        self.assertAlmostEqual(
            self.ctx.architecture.get("WALL", row.uid).thickness_m,
            old_thickness)

    def test_rejects_non_editable_field(self):
        row = self._row("ARCHITECTURE", "WALL")
        with self.assertRaises(ValueError) as ctx:
            PropertyEditor.edit(self.ctx, row, "name", "XXX")
        self.assertIn("no es editable", str(ctx.exception))

    def test_rejects_synthetic_row(self):
        row = ObjectRow(uid="qto:WALL_LENGTH", type="QUANTITY",
                        discipline="QTO")
        with self.assertRaises(ValueError):
            PropertyEditor.edit(self.ctx, row, "name", "x")

    def test_rejects_bad_number(self):
        row = self._row("ARCHITECTURE", "WALL")
        with self.assertRaises(ValueError) as ctx:
            PropertyEditor.edit(self.ctx, row, "thickness_m", "abc")
        self.assertIn("no válido", str(ctx.exception))

    def test_editable_fields_whitelist_matches_entity(self):
        row = self._row("ARCHITECTURE", "DOOR")
        fields = dict(PropertyEditor.editable_fields(row.entity))
        self.assertIn("width_m", fields)
        self.assertNotIn("level_id", fields)


class TestEditServiceCreate(_EdicionBase):
    """Creación declarativa por las fachadas (mismo bus que la CLI)."""

    def test_create_level(self):
        level = self.edit.create("LEVEL", {"name": "Ático",
                                           "elevation_m": "9",
                                           "height_m": "3.2"})
        self.assertEqual(level.name, "Ático")
        self.assertAlmostEqual(level.elevation_m, 9.0)

    def test_create_zone(self):
        zone = self.edit.create("ZONE", {"name": "Zona técnica",
                                         "kind": "TECHNICAL"})
        self.assertEqual(zone.kind, "TECHNICAL")

    def test_create_space_with_default_boundary(self):
        space = self.edit.create("SPACE", {"level_ref": "Nivel 1",
                                           "name": "Almacén"})
        self.assertEqual(len(space.boundary), 4)
        # no solapa el origen: rectángulo desplazado por locales existentes
        xs = [p[0] for p in space.boundary]
        self.assertGreater(min(xs), 0.0)

    def test_create_space_with_explicit_boundary(self):
        space = self.edit.create("SPACE", {
            "level_ref": "Nivel 1", "name": "Oficina",
            "boundary": "20,0 24,0 24,3 20,3"})
        self.assertAlmostEqual(space.boundary[1][0], 24.0)

    def test_create_wall_and_door(self):
        wall = self.edit.create("WALL", {
            "level_ref": "Nivel 1", "start": "(50, 0)",
            "end": "(54, 0)", "thickness_m": "0.15"})
        self.assertAlmostEqual(wall.length_m, 4.0)
        door = self.edit.create("DOOR", {
            "wall_ref": wall.code, "width_m": "0.9",
            "height_m": "2.1", "offset_m": "0.5"})
        self.assertEqual(door.kind, "DOOR")
        self.assertEqual(door.wall_id, wall.id)

    def test_create_structure_entities(self):
        material = self.edit.create("MATERIAL", {"name": "HA-30"})
        self.assertEqual(material.kind, "CONCRETE")
        section = self.edit.create("SECTION", {
            "name": "TH-30x50", "shape": "RECTANGLE",
            "h_mm": "500", "b_mm": "300"})
        self.assertEqual(section.shape, "RECTANGLE")
        element = self.edit.create("ELEMENT", {
            "kind": "BEAM", "name": "V-101", "start": "(0,0)",
            "end": "(6,0)", "load_udl_kn_m": "12.5"})
        self.assertEqual(element.kind, "BEAM")

    def test_create_network_and_node(self):
        network = self.edit.create("NETWORK", {
            "name": "Riego jardín", "system": "COLD_WATER"})
        self.assertEqual(network.system, "COLD_WATER")
        node = self.edit.create("NODE", {
            "network_ref": network.code, "kind": "SOURCE",
            "x": "70", "y": "10"})
        self.assertEqual(node.network_id, network.id)

    def test_create_missing_required_field_fails(self):
        with self.assertRaises(ValueError) as ctx:
            self.edit.create("SPACE", {"name": "sin nivel"})
        self.assertIn("obligatorios", str(ctx.exception))

    def test_create_unknown_type_fails(self):
        with self.assertRaises(ValueError):
            self.edit.create("QUANTITY", {"name": "x"})

    def test_create_is_undoable(self):
        level = self.edit.create("LEVEL", {"name": "Temporal"})
        from app.undo_service import PersistentUndoService
        PersistentUndoService(self.ctx).undo()
        self.ctx.commit()
        self.assertIsNone(self.ctx.architecture.get("LEVEL", level.id))


class TestEditServiceDelete(_EdicionBase):
    """Borrado por fachada con cascada, auditoría y undo."""

    def test_delete_door(self):
        row = self._row("ARCHITECTURE", "DOOR")
        code = self.edit.delete(row)
        self.assertEqual(code, row.code)
        self.assertIsNone(self.ctx.architecture.get("DOOR", row.uid))

    def test_delete_node_cascades_and_undo_restores(self):
        row = self._row("INSTALLATIONS", "NODE", index=1)
        segments_before = len(self.ctx.installations.segments_of(
            row.entity.network_id))
        self.edit.delete(row)
        self.ctx.commit()
        self.assertIsNone(self.ctx.installations.get("NODE", row.uid))
        segments_after = len(self.ctx.installations.segments_of(
            row.entity.network_id))
        self.assertLess(segments_after, segments_before)
        from app.undo_service import PersistentUndoService
        PersistentUndoService(self.ctx).undo()
        self.ctx.commit()
        self.assertIsNotNone(self.ctx.installations.get("NODE", row.uid))
        self.assertEqual(len(self.ctx.installations.segments_of(
            row.entity.network_id)), segments_before)

    def test_delete_element_generic_path(self):
        row = self._row("STRUCTURE", "ELEMENT")
        self.edit.delete(row)
        self.ctx.commit()
        self.assertIsNone(self.ctx.structure.get("ELEMENT", row.uid))
        # audita DELETE_ENTITY con snapshot completo → undo posible
        entries = self._audit_entries("DELETE_ENTITY", row.uid)
        self.assertTrue(entries)
        self.assertIn("entity", entries[-1]["old_value"])

    def test_delete_rejects_synthetic_row(self):
        row = ObjectRow(uid="budget:x", type="BUDGET", discipline="BUDGET")
        with self.assertRaises(ValueError):
            self.edit.delete(row)

    def test_delete_rejects_non_deletable_type(self):
        row = self._row("COORDINATION", "CLASH")
        with self.assertRaises(ValueError) as ctx:
            self.edit.delete(row)
        self.assertIn("no se puede borrar", str(ctx.exception))

    def test_delete_drawing(self):
        from services.documentation_service import DocumentationService
        drawing = DocumentationService(self.ctx).create_drawing(
            sheet="A-101", sheet_size="A3", scale="1:50")
        from ui.models import ObjectRow as _Row
        row = _Row(uid=drawing.id, code=drawing.code, type="DRAWING",
                   discipline="DOCUMENTATION", entity=drawing)
        code = self.edit.delete(row)
        self.ctx.commit()
        self.assertEqual(code, drawing.code)
        self.assertIsNone(self.ctx.documentation.drawings.get(drawing.id))


class TestViewportZoomAt(unittest.TestCase):
    """Zoom anclado al cursor (mejora del lienzo)."""

    def test_point_under_cursor_stays_fixed(self):
        viewport = Viewport(center_x=10, center_y=5, scale=20)
        px, py, width, height = 300, 200, 800, 600
        wx, wy = viewport.from_screen(px, py, width, height)
        viewport.zoom_at(1.25, px, py, width, height)
        ax, ay = viewport.from_screen(px, py, width, height)
        self.assertAlmostEqual(wx, ax, places=9)
        self.assertAlmostEqual(wy, ay, places=9)
        self.assertGreater(viewport.scale, 20.0)

    def test_zoom_at_clamps_to_limits(self):
        viewport = Viewport(scale=Viewport.MAX_SCALE)
        viewport.zoom_at(2.0, 100, 100, 800, 600)
        self.assertEqual(viewport.scale, Viewport.MAX_SCALE)


class TestAcceleratorsAndSpecs(ARQGenTestCase):
    """Contrato de atajos §90 y formularios declarativos."""

    def test_accelerators_reference_existing_methods(self):
        self.assertIn("<Control-z>", ACCELERATORS)
        for sequence, method_name in ACCELERATORS.items():
            self.assertTrue(
                callable(getattr(ARQGenWindow, method_name, None)),
                f"El atajo {sequence} apunta a un método inexistente: "
                f"{method_name}")

    def test_create_specs_are_well_formed(self):
        self.assertGreaterEqual(len(CREATE_SPECS), 11)
        for entity_type, (discipline, fields) in CREATE_SPECS.items():
            self.assertTrue(fields, f"{entity_type} sin campos")
            params = [f[0] for f in fields]
            self.assertEqual(len(params), len(set(params)), entity_type)
            self.assertTrue(any(f[3] for f in fields),
                            f"{entity_type} sin campo obligatorio")

    def test_choice_sources_resolve_on_demo(self):
        context = self.demo_context()
        service = EditService(context, ExplorerModel(context))
        self.assertTrue(service.choices("levels"))
        self.assertTrue(service.choices("walls"))
        self.assertTrue(service.choices("networks"))
        self.assertIn("COLD_WATER", service.choices("systems"))
        self.assertIn("PANEL", service.choices("node_kinds"))


if __name__ == "__main__":
    unittest.main()
