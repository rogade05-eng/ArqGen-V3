"""TEST-004 Relationships: spatial engine and DNA knowledge (spec 8, 14-17, 97)."""

from __future__ import annotations

import unittest

from engines.spatial_engine import SpatialEngine
from tests.base import ARQGenTestCase


class TestSpatialRelations(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.engine = SpatialEngine(dna_registry=self.application.dna_registry)

    def test_adjacency_detection(self):
        from domain.model import Space
        a = Space(name="A", boundary=[(0, 0), (4, 0), (4, 3), (0, 3)])
        b = Space(name="B", boundary=[(4, 0), (8, 0), (8, 3), (4, 3)])
        c = Space(name="C", boundary=[(10, 0), (12, 0), (12, 2), (10, 2)])
        result = self.engine.compute_adjacencies([a, b, c])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].shared_length_m, 3.0, places=2)

    def test_service_persists_relationships(self):
        ctx = self.application.create_project(self.project_path(), name="Rel")
        ctx.user = "tester"
        from services.architecture_service import ArchitectureService
        from services.analysis_service import SpatialService
        service = ArchitectureService(ctx)
        service.create_level("N1", 0.0, 3.0)
        service.create_space("N1", "Sala", "LIVING_ROOM", [(0, 0), (6, 0), (6, 6), (0, 6)])
        service.create_space("N1", "Cocina", "KITCHEN", [(6, 0), (10, 0), (10, 6), (6, 6)])
        spatial = SpatialService(ctx)
        created = spatial.recompute_adjacencies()
        self.assertEqual(len(created), 1)
        # Idempotent: second run adds nothing new
        self.assertEqual(spatial.recompute_adjacencies(), [])
        rels = ctx.architecture.list("SPACE_RELATIONSHIP", ctx.project.id)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].kind, "adjacent_to")
        self.assertEqual(rels[0].source, "geometry")
        ctx.close()

    def test_dna_registry_loaded(self):
        # The application loads the Space DNA from resources/knowledge
        self.assertGreater(len(self.application.dna_registry), 0)
        kitchen = self.application.dna_registry.require("KITCHEN")
        self.assertTrue(kitchen.wet_zone)
        self.assertTrue(kitchen.requires_water)
        self.assertIsNotNone(kitchen.minimum_area)

    def test_dna_min_area_finding(self):
        from domain.model import Space
        small_bedroom = Space(name="Chico", space_type="BEDROOM",
                              boundary=[(0, 0), (2, 0), (2, 1.5), (0, 1.5)])
        findings = self.engine.analyze_space(small_bedroom, [])
        self.assertTrue(any("mínimo" in f for f in findings), findings)

    def test_zoning_summary(self):
        from domain.model import Space
        a = Space(name="A", boundary=[(0, 0), (1, 0), (1, 1)])
        b = Space(name="B", boundary=[(2, 0), (3, 0), (3, 1)])
        summary = self.engine.zoning_summary([a, b], {a.id: "PRIVATE"})
        self.assertEqual(summary, {"PRIVATE": ["A"], "SIN ZONA": ["B"]})


if __name__ == "__main__":
    unittest.main()
