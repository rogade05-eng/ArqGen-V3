"""Persistence: migrations, repositories, audit, events (spec 78, 79, 97)."""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase


class TestPersistence(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.project_path()
        self.ctx = self.application.create_project(self.path, name="Persist")
        self.ctx.user = "tester"

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_migrations_reversible(self):
        from persistence.migrations import MIGRATIONS, MigrationRunner, applied_versions
        runner = MigrationRunner(MIGRATIONS)
        versions = applied_versions(self.ctx.session)
        self.assertEqual(versions, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        rolled = runner.rollback_last(self.ctx.session)
        self.assertEqual(rolled, 11)
        self.assertEqual(applied_versions(self.ctx.session),
                         [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        runner.migrate(self.ctx.session)
        self.assertEqual(applied_versions(self.ctx.session),
                         [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])

    def test_entity_roundtrip_wall(self):
        from services.architecture_service import ArchitectureService
        service = ArchitectureService(self.ctx)
        service.create_level("N1", 0.0, 3.0)
        wall = service.create_wall("N1", (1.5, 2.5), (7.25, 2.5), thickness_m=0.18,
                                   height_m=2.9, structural=True)
        self.ctx.commit()
        wall_id = wall.id
        self.ctx.close()
        ctx2 = self.application.open_project(self.path)
        loaded = ctx2.architecture.get("WALL", wall_id)
        self.assertIsNotNone(loaded)
        self.assertAlmostEqual(loaded.start[0], 1.5, places=6)
        self.assertAlmostEqual(loaded.length_m, 5.75, places=6)
        self.assertEqual(loaded.thickness_m, 0.18)
        self.assertTrue(loaded.structural)
        self.assertEqual(loaded.code, "ARQ-WALL-001")
        ctx2.close()

    def test_opening_kind_filtering(self):
        from services.architecture_service import ArchitectureService
        service = ArchitectureService(self.ctx)
        service.create_level("N1", 0.0, 3.0)
        wall = service.create_wall("N1", (0, 0), (8, 0))
        service.create_opening("DOOR", wall.code, 0.9, 2.1)
        service.create_opening("WINDOW", wall.code, 1.2, 1.2, sill_height_m=1.0)
        self.assertEqual(self.ctx.architecture.count("DOOR", self.ctx.project.id), 1)
        self.assertEqual(self.ctx.architecture.count("WINDOW", self.ctx.project.id), 1)
        self.assertEqual(self.ctx.architecture.count("OPENING", self.ctx.project.id), 2)
        # get_by_code with wrong kind returns None
        window = self.ctx.architecture.get_by_code("WINDOW", "ARQ-WINDOW-001")
        self.assertIsNotNone(window)
        self.assertIsNone(self.ctx.architecture.get_by_code("WINDOW", "ARQ-DOOR-001"))

    def test_audit_trail_records(self):
        from services.architecture_service import ArchitectureService
        service = ArchitectureService(self.ctx)
        service.create_level("N1", 0.0, 3.0)
        wall = service.create_wall("N1", (0, 0), (5, 0))
        entries = self.ctx.audit_repo.recent(limit=10, object_id=wall.id)
        self.assertTrue(entries)
        self.assertEqual(entries[0]["command"], "CREATE_ENTITY")
        self.assertEqual(entries[0]["user"], "tester")
        self.assertEqual(entries[0]["new_value"]["ENTITY_TYPE"], "WALL")

    def test_events_persisted(self):
        from services.architecture_service import ArchitectureService
        ArchitectureService(self.ctx).create_level("N1", 0.0, 3.0)
        events = self.ctx.events_repo.recent(limit=10)
        self.assertTrue(any(e["type"] == "OBJECT_CREATED" for e in events))


if __name__ == "__main__":
    unittest.main()
