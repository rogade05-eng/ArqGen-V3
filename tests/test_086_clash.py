"""Coordination and clash detection tests (spec sections 35, 36)."""

from __future__ import annotations

from core.errors import DomainError
from tests.base import ARQGenTestCase


class TestClashEngine(ARQGenTestCase):
    """Reglas geométricas puras (spec 35-36)."""

    def test_point_segment_distance(self):
        from engines.clash_engine import point_segment_distance
        self.assertAlmostEqual(point_segment_distance((5, 1), (0, 0), (10, 0)), 1.0)
        self.assertAlmostEqual(point_segment_distance((-1, 0), (0, 0), (10, 0)), 1.0)

    def test_segments_intersect(self):
        from engines.clash_engine import segments_properly_intersect
        self.assertTrue(segments_properly_intersect((0, 0), (10, 10),
                                                    (0, 10), (10, 0)))
        self.assertFalse(segments_properly_intersect((0, 0), (1, 1),
                                                     (5, 5), (6, 6)))

    def test_node_in_wall_is_hard(self):
        from engines.clash_engine import node_wall_clashes
        walls = [("WALL", "w1", "ARQ-WALL-001", ((0, 0), (10, 0)), 0.2)]
        findings = node_wall_clashes(
            ("NODE", "n1", "MEP-NODE-001", (5.0, 0.0), 0.0), walls)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].type, "HARD")
        self.assertEqual(findings[0].severity, "CRITICAL")

    def test_node_clearance_violation(self):
        from engines.clash_engine import CLEARANCE_MIN_M, node_wall_clashes
        walls = [("WALL", "w1", "ARQ-WALL-001", ((0, 0), (10, 0)), 0.2)]
        # A 0.35 m del eje con espesor 0.2: distancia libre 0.25 < 0.30.
        findings = node_wall_clashes(
            ("NODE", "n1", "MEP-NODE-001", (5.0, 0.35), 0.0), walls)
        self.assertEqual([f.type for f in findings], ["CLEARANCE"])
        # A 0.45 m no hay hallazgo: 0.35 m libres > 0.30 m.
        findings = node_wall_clashes(
            ("NODE", "n1", "MEP-NODE-001", (5.0, 0.45), 0.0), walls)
        self.assertEqual(findings, [])

    def test_access_zone_of_panel(self):
        from engines.clash_engine import node_wall_clashes
        walls = [("WALL", "w1", "ARQ-WALL-001", ((0, 0), (10, 0)), 0.2)]
        # Tablero (radio 0.25) a 0.85 m del eje: 0.75 m libres < 0.80 m de
        # frente de maniobra.
        findings = node_wall_clashes(
            ("NODE", "n1", "MEP-NODE-001", (5.0, 0.85), 0.25), walls)
        self.assertEqual([f.type for f in findings], ["ACCESS"])
        # A 0.95 m del eje (0.85 m libres) el frente de maniobra cabe.
        findings = node_wall_clashes(
            ("NODE", "n1", "MEP-NODE-001", (5.0, 0.95), 0.25), walls)
        self.assertEqual(findings, [])

    def test_node_node_soft_and_maintenance(self):
        from engines.clash_engine import node_node_clashes
        nodes = [
            ("NODE", "n1", "A", "POWER", (2.0, 2.0), 0.0),
            ("NODE", "n2", "B", "COLD_WATER", (2.1, 2.0), 0.0),
            ("NODE", "n3", "C", "POWER", (8.0, 8.0), 0.25),
            ("NODE", "n4", "D", "COLD_WATER", (8.9, 8.0), 0.25),
        ]
        findings = node_node_clashes(nodes)
        types = sorted(f.type for f in findings)
        self.assertEqual(types, ["MAINTENANCE", "SOFT"])
        # Pares de la misma disciplina se ignoran.
        same = [("NODE", "n1", "A", "POWER", (2.0, 2.0), 0.0),
                ("NODE", "n2", "B", "POWER", (2.05, 2.0), 0.0)]
        self.assertEqual(node_node_clashes(same), [])

    def test_route_crossing(self):
        from engines.clash_engine import segment_segment_clashes
        segments = [
            ("SEGMENT", "s1", "S1", "net-a", ((0, 0), (10, 0)), 0),
            ("SEGMENT", "s2", "S2", "net-b", ((5, -5), (5, 5)), 0),
            ("SEGMENT", "s3", "S3", "net-a", ((1, 1), (2, 2)), 0),
        ]
        findings = segment_segment_clashes(segments)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].type, "ROUTE")
        self.assertEqual(findings[0].object_a[1], "s1")
        self.assertEqual(findings[0].object_b[1], "s2")


class TestClashEntity(ARQGenTestCase):
    """Entidad Clash y ciclo de vida (spec 36)."""

    def test_lifecycle(self):
        from domain.clash import Clash
        clash = Clash(object_a_type="NODE", object_a_id="a", object_a_code="A",
                      object_b_type="WALL", object_b_id="b", object_b_code="B",
                      type="HARD", severity="CRITICAL")
        self.assertEqual(clash.status, "OPEN")
        clash.set_status("REVIEWED")
        clash.set_status("RESOLVED", )
        self.assertEqual(clash.status, "RESOLVED")
        self.assertIsNotNone(clash.resolved_at)
        with self.assertRaises(DomainError):
            clash.set_status("MAYBE")

    def test_invalid_type_rejected(self):
        from domain.clash import Clash
        with self.assertRaises(DomainError):
            Clash(object_a_type="NODE", object_a_id="a",
                  object_b_type="WALL", object_b_id="b", type="MAGIC")

    def test_requires_two_objects(self):
        from domain.clash import Clash
        with self.assertRaises(DomainError):
            Clash(object_a_type="NODE", object_a_id="",
                  object_b_type="WALL", object_b_id="b", type="HARD")


class TestCoordinationService(ARQGenTestCase):
    """Servicio de coordinación sobre el proyecto (spec 35-36)."""

    def _build_project(self, service_cls=None):
        ctx = self.application.create_project(self.project_path(), name="Clash")
        from services.architecture_service import ArchitectureService
        from services.installations_service import InstallationsService
        arch = ArchitectureService(ctx)
        arch.create_level("N1", 0.0, 3.0)
        arch.create_space("N1", "Sala", "LIVING_ROOM",
                          [(0, 0), (10, 0), (10, 8), (0, 8)])
        arch.create_wall("N1", (0, 0), (10, 0))
        installations = InstallationsService(ctx)
        power = installations.create_network("Elec", "POWER")
        # Dispositivo dentro del muro (HARD) y uno cerca (CLEARANCE).
        installations.add_node(power.code, "OUTLET", 5.0, 0.0, name="En muro")
        installations.add_node(power.code, "OUTLET", 5.0, 0.35, name="Cerca")
        water = installations.create_network("Agua", "COLD_WATER")
        installations.add_node(water.code, "FIXTURE", 5.0, 0.1, name="Fixture muro")
        return ctx, installations, power, water

    def test_detection_and_dedup(self):
        from services.coordination_service import CoordinationService
        ctx, _inst, _power, _water = self._build_project()
        service = CoordinationService(ctx)
        first = service.run_detection()
        self.assertGreaterEqual(first["created"], 3)
        self.assertIn("HARD", first["by_type"])
        second = service.run_detection()
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["duplicates_skipped"], first["created"])
        ctx.close()

    def test_systems_filter(self):
        from services.coordination_service import CoordinationService
        ctx, _inst, _power, _water = self._build_project()
        service = CoordinationService(ctx)
        report = service.run_detection(systems_filter=["POWER"])
        # Solo la red eléctrica: el fixture del muro (COLD_WATER) no cuenta.
        for row in report["clashes"]:
            self.assertNotIn("MEP-FIXTURE", (row["a"], row["b"]))
        ctx.close()

    def test_lifecycle_and_persistence(self):
        from services.coordination_service import CoordinationService
        ctx, _inst, _power, _water = self._build_project()
        service = CoordinationService(ctx)
        service.run_detection()
        open_rows = service.list_clashes(status="OPEN")
        self.assertTrue(open_rows)
        code = open_rows[0]["code"]
        service.set_status(code, "REVIEWED")
        service.set_status(code, "RESOLVED", notes="Reubicado el dispositivo")
        self.assertEqual(len(service.list_clashes(status="RESOLVED")), 1)
        self.assertEqual(len(service.list_clashes(status="OPEN")),
                         len(open_rows) - 1)
        with self.assertRaises(DomainError):
            service.set_status(code, "MAYBE")
        ctx.close()

    def test_events_emitted(self):
        from services.coordination_service import CoordinationService
        ctx, _inst, _power, _water = self._build_project()
        service = CoordinationService(ctx)
        created_events = []
        resolved_events = []
        ctx.event_bus.subscribe("CLASH_CREATED",
                                lambda e: created_events.append(e))
        ctx.event_bus.subscribe("CLASH_RESOLVED",
                                lambda e: resolved_events.append(e))
        service.run_detection()
        self.assertGreater(len(created_events), 0)
        code = service.list_clashes(status="OPEN")[0]["code"]
        service.set_status(code, "RESOLVED")
        self.assertEqual(len(resolved_events), 1)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
