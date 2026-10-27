"""TEST-003/005 Space & Architecture: domain + service integration (spec 20, 97)."""

from __future__ import annotations

import unittest

from core.errors import DomainError
from tests.base import ARQGenTestCase


class TestArchitecture(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.project_path()
        self.ctx = self.application.create_project(self.path, name="Arq Test")
        self.ctx.user = "tester"
        from services.architecture_service import ArchitectureService
        self.service = ArchitectureService(self.ctx)

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_level_creation_and_height_rule(self):
        level = self.service.create_level("N1", 0.0, 3.0)
        self.assertEqual(level.code, "ARQ-LEVEL-001")
        with self.assertRaises(DomainError):
            self.service.create_level("N2", 0.0, -1.0)

    def test_codes_are_sequential_and_persistent(self):
        self.service.create_level("N1", 0.0, 3.0)
        self.service.create_level("N2", 3.0, 3.0)
        wall = self.service.create_wall("N1", (0, 0), (5, 0))
        self.assertEqual(wall.code, "ARQ-WALL-001")
        space = self.service.create_space("N1", "Sala", "LIVING_ROOM",
                                          [(0, 0), (4, 0), (4, 3), (0, 3)])
        self.assertEqual(space.code, "ARQ-SPACE-001")

    def test_wall_creation_rules(self):
        self.service.create_level("N1", 0.0, 3.0)
        with self.assertRaises(DomainError):
            self.service.create_wall("N1", (0, 0), (0, 0))       # longitud nula
        with self.assertRaises(DomainError):
            self.service.create_wall("N1", (0, 0), (5, 0), thickness_m=-0.2)
        wall = self.service.create_wall("N1", (0, 0), (5, 0), thickness_m=0.2)
        self.assertAlmostEqual(wall.length_m, 5.0, places=9)

    def test_space_area_and_zone(self):
        self.service.create_level("N1", 0.0, 3.0)
        zone = self.service.create_zone("Privada", "PRIVATE")
        space = self.service.create_space("N1", "Dormitorio", "BEDROOM",
                                          [(0, 0), (4, 0), (4, 4), (0, 4)])
        self.assertAlmostEqual(space.area_m2(), 16.0, places=9)
        zoned = self.service.set_space_zone(space.code, zone.id)
        self.assertEqual(zoned.zone_id, zone.id)

    def test_openings_fit_wall(self):
        self.service.create_level("N1", 0.0, 3.0)
        wall = self.service.create_wall("N1", (0, 0), (5, 0))
        door = self.service.create_opening("DOOR", wall.code, 0.9, 2.1, offset_m=1.0)
        self.assertAlmostEqual(door.area_m2, 1.89, places=9)
        with self.assertRaises(DomainError):
            self.service.create_opening("DOOR", wall.code, 0.9, 2.1, offset_m=4.5)
        with self.assertRaises(DomainError):
            self.service.create_opening("DOOR", wall.code, 0.9, 3.5, offset_m=0.0)

    def test_delete_wall_cascades_openings(self):
        self.service.create_level("N1", 0.0, 3.0)
        wall = self.service.create_wall("N1", (0, 0), (5, 0))
        door = self.service.create_opening("DOOR", wall.code, 0.9, 2.1)
        self.service.delete_entity("WALL", wall.code)
        self.assertIsNone(self.ctx.architecture.get("WALL", wall.id))
        self.assertIsNone(self.ctx.architecture.get("DOOR", door.id))

    def test_level_resolution_by_name_and_code(self):
        self.service.create_level("N1", 0.0, 3.0)
        level = self.service.get_level_by_name_or_code("n1")
        self.assertEqual(level.name, "N1")
        with self.assertRaises(DomainError):
            self.service.get_level_by_name_or_code("nope")


if __name__ == "__main__":
    unittest.main()
