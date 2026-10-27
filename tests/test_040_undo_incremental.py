"""TEST-022/025 Undo/Redo and incremental recalculation (spec 74, 77, 97)."""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase


class TestUndoRedoInProcess(ARQGenTestCase):
    """Undo/Redo transactional through the CommandBus (spec 77)."""

    def setUp(self):
        super().setUp()
        self.ctx = self.application.create_project(self.project_path(), name="Undo")
        self.ctx.user = "tester"
        from services.architecture_service import ArchitectureService
        self.service = ArchitectureService(self.ctx)
        self.service.create_level("N1", 0.0, 3.0)

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_command_bus_undo_redo_creates(self):
        wall = self.service.create_wall("N1", (0, 0), (5, 0))
        self.assertEqual(self.ctx.architecture.count("WALL", self.ctx.project.id), 1)
        self.ctx.command_bus.undo(self.ctx)  # undo of CREATE_ENTITY deletes
        self.assertEqual(self.ctx.architecture.count("WALL", self.ctx.project.id), 0)
        self.ctx.command_bus.redo(self.ctx)
        self.assertEqual(self.ctx.architecture.count("WALL", self.ctx.project.id), 1)
        restored = self.ctx.architecture.get("WALL", wall.id)
        self.assertEqual(restored.code, wall.code)

    def test_command_bus_undo_redo_update(self):
        wall = self.service.create_wall("N1", (0, 0), (5, 0))
        self.service.move_wall(wall.code, (0, 0), (9, 0))
        moved = self.ctx.architecture.get("WALL", wall.id)
        self.assertAlmostEqual(moved.length_m, 9.0, places=9)
        self.ctx.command_bus.undo(self.ctx)
        restored = self.ctx.architecture.get("WALL", wall.id)
        self.assertAlmostEqual(restored.length_m, 5.0, places=9)
        self.ctx.command_bus.redo(self.ctx)
        again = self.ctx.architecture.get("WALL", wall.id)
        self.assertAlmostEqual(again.length_m, 9.0, places=9)

    def test_persistent_undo_redo_across_sessions(self):
        wall = self.service.create_wall("N1", (0, 0), (5, 0))
        self.service.create_opening("WINDOW", wall.code, 1.2, 1.2, sill_height_m=1.0)
        self.ctx.commit()
        self.ctx.close()

        from app.undo_service import PersistentUndoService
        ctx = self.application.open_project(self.project_path())
        self.assertEqual(ctx.architecture.count("WINDOW", ctx.project.id), 1)
        result = PersistentUndoService(ctx).undo()
        self.assertEqual(result["command"], "CREATE_ENTITY")
        self.assertEqual(ctx.architecture.count("WINDOW", ctx.project.id), 0)
        PersistentUndoService(ctx).redo()
        self.assertEqual(ctx.architecture.count("WINDOW", ctx.project.id), 1)
        ctx.close()


class TestIncrementalRecalculation(ARQGenTestCase):
    """TEST-025: only affected objects are recomputed (spec 74, 99)."""

    def test_only_changed_wall_recomputed(self):
        ctx = self.demo_context()
        ctx.user = "tester"
        from services.architecture_service import ArchitectureService
        from services.quantity_service import QuantityService

        quantity = QuantityService(ctx)
        # The demo already computed QTO during build; this run must be 100% cache.
        # Architecture objects (walls + openings + spaces)
        # + nodes and segments of the installation networks (v1.2 demo:
        # POWER / COLD_WATER / SANITARY_DRAINAGE / EXHAUST / STORMWATER /
        # GAS / TELECOM).
        first = quantity.compute_all()
        self.assertEqual(first.cached, 164)
        self.assertEqual(first.computed, 0)

        # Change ONE wall (move) → revision bump invalidates only that wall's cache
        service = ArchitectureService(ctx)
        wall = ctx.architecture.get_by_code("WALL", "ARQ-WALL-001")
        hashes_before = {q["object_id"]: q["input_hash"]
                         for q in quantity.quantities()}
        service.move_wall("ARQ-WALL-001", (0, 0), (12, 0))
        ctx.commit()

        second = quantity.compute_all()
        # Only the moved wall recomputes (1 object); the rest come from cache.
        self.assertEqual(second.computed, 1)
        self.assertEqual(second.cached, 163)

        hashes_after = {q["object_id"]: q["input_hash"] for q in quantity.quantities()}
        # Other objects keep their hashes; the moved wall changed.
        self.assertNotEqual(hashes_after.get(wall.id), hashes_before.get(wall.id))
        other = ctx.architecture.get_by_code("WALL", "ARQ-WALL-003")
        self.assertEqual(hashes_after.get(other.id), hashes_before.get(other.id))
        ctx.close()

    def test_dependency_graph_impact(self):
        ctx = self.demo_context()
        ctx.rebuild_dependency_graph()
        wall = ctx.architecture.get_by_code("WALL", "ARQ-WALL-001")
        impact = ctx.dependency_graph.affected_descendants(wall.id)
        openings = [o for o in ctx.architecture.list("OPENING", ctx.project.id)
                    if o.wall_id == wall.id]
        self.assertTrue(openings)
        for opening in openings:
            self.assertIn(opening.id, impact)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
