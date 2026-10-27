"""Installations module tests: networks, routing, QTO, undo, persistence (spec 24-26, 74, 77)."""

from __future__ import annotations

from tests.base import ARQGenTestCase


class TestNetworkCRUD(ARQGenTestCase):
    """CRUD through the service with commands, events and audit (spec 76)."""

    def test_create_network_and_nodes(self):
        from services.installations_service import InstallationsService
        from services.context import ApplicationContext
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network = service.create_network("Red prueba", "POWER")
        self.assertEqual(network.discipline, "ELECTRICAL")
        self.assertTrue(network.code.startswith("MEP-NETWORK"))
        panel = service.add_node(network.code, "PANEL", 0.0, 0.0,
                                 attrs={"voltage": 220, "phases": 1})
        outlet = service.add_node(network.code, "OUTLET", 4.0, 0.0,
                                  attrs={"power_w": 600})
        self.assertEqual(panel.role, "EQUIPMENT")
        self.assertEqual(outlet.role, "TERMINAL")
        self.assertEqual(ctx.installations.count("NODE", ctx.project.id), 2)
        ctx.close()

    def test_invalid_system_rejected(self):
        from services.installations_service import InstallationsService
        from core.errors import DomainError
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        with self.assertRaises(DomainError):
            service.create_network("Mala red", "POWER_OVER_9000")
        ctx.close()

    def test_connect_and_disconnect(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network = service.create_network("Red prueba", "POWER")
        panel = service.add_node(network.code, "PANEL", 0.0, 0.0)
        outlet = service.add_node(network.code, "OUTLET", 3.0, 0.0)
        segment = service.connect(network.code, panel.code, outlet.code)
        # 3 m axis-aligned: routing computes exact length, no crossings.
        self.assertAlmostEqual(segment.length_m, 3.0, places=3)
        self.assertEqual(segment.crossings, 0)
        self.assertEqual(len(ctx.installations.segments_of(network.id)), 1)

        # duplicate connection is rejected
        from core.errors import DomainError
        with self.assertRaises(DomainError):
            service.connect(network.code, panel.code, outlet.code)

        # disconnect removes the segment
        service.disconnect(segment.code)
        self.assertEqual(len(ctx.installations.segments_of(network.id)), 0)
        ctx.close()

    def test_delete_node_cascades_segments(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network = service.create_network("Red prueba", "POWER")
        panel = service.add_node(network.code, "PANEL", 0.0, 0.0)
        mid = service.add_node(network.code, "JUNCTION", 2.0, 0.0)
        outlet = service.add_node(network.code, "OUTLET", 4.0, 0.0)
        service.connect(network.code, panel.code, mid.code)
        service.connect(network.code, mid.code, outlet.code)
        service.delete_entity("NODE", mid.code)
        self.assertEqual(len(ctx.installations.segments_of(network.id)), 0)
        self.assertEqual(len(ctx.installations.nodes_of(network.id)), 2)
        ctx.close()


class TestGraphOperations(ARQGenTestCase):
    """trace / find_path / calculate_path / validate / dead ends (spec 25)."""

    def _radial(self, service):
        network = service.create_network("Radial", "POWER")
        panel = service.add_node(network.code, "PANEL", 0.0, 0.0)
        prot = service.add_node(network.code, "PROTECTION", 1.0, 0.0)
        outlet = service.add_node(network.code, "OUTLET", 3.0, 0.0, attrs={"power_w": 100})
        luminaire = service.add_node(network.code, "LUMINAIRE", 1.0, 2.0)
        service.connect(network.code, panel.code, prot.code)
        service.connect(network.code, prot.code, outlet.code)
        service.connect(network.code, prot.code, luminaire.code)
        return network, panel, prot, outlet

    def test_trace_upstream(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network, panel, prot, outlet = self._radial(service)
        result = service.trace(outlet.code)
        self.assertEqual(result["path"][0], outlet.code)
        self.assertEqual(result["path"][-1], panel.code)
        self.assertGreater(result["length_m"], 0)
        ctx.close()

    def test_find_path_between_branches(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network, panel, prot, outlet = self._radial(service)
        luminaire = [n for n in ctx.installations.nodes_of(network.id)
                     if n.kind == "LUMINAIRE"][0]
        result = service.find_path(outlet.code, luminaire.code)
        self.assertEqual(result["path"], [outlet.code, prot.code, luminaire.code])
        self.assertAlmostEqual(result["cost"], 4.0, places=2)
        ctx.close()

    def test_validate_radial_ok(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network, panel, prot, outlet = self._radial(service)
        result = service.validate_network(network.code)
        self.assertEqual(result["status"], "VALID")
        ctx.close()

    def test_validate_orphan_is_invalid(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network, panel, prot, outlet = self._radial(service)
        service.add_node(network.code, "OUTLET", 9.0, 9.0)  # orphan terminal
        result = service.validate_network(network.code)
        self.assertEqual(result["status"], "INVALID")
        self.assertTrue(any(f["code"] == "ARQ-NET-015" for f in result["errors"]))
        ctx.close()

    def test_validate_drainage_needs_outfall(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network = service.create_network("Desagüe", "SANITARY_DRAINAGE")
        fixture = service.add_node(network.code, "FIXTURE", 0.0, 0.0)
        junction = service.add_node(network.code, "JUNCTION", 2.0, 0.0)
        service.connect(network.code, fixture.code, junction.code)
        result = service.validate_network(network.code)
        self.assertEqual(result["status"], "INVALID")  # no OUTFALL yet
        outfall = service.add_node(network.code, "OUTFALL", 5.0, 0.0)
        service.connect(network.code, junction.code, outfall.code)
        result = service.validate_network(network.code)
        self.assertEqual(result["status"], "VALID")
        ctx.close()

    def test_dead_end_junction_detected(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Redes")
        service = InstallationsService(ctx)
        network, panel, prot, outlet = self._radial(service)
        # A junction stub connected only once is a forgotten continuation.
        stub = service.add_node(network.code, "JUNCTION", 6.0, 0.0)
        service.connect(network.code, prot.code, stub.code)
        result = service.validate_network(network.code)
        self.assertIn(stub.code, result["dead_ends"])
        self.assertEqual(result["status"], "VALID_WITH_WARNINGS")
        ctx.close()


class TestRouting(ARQGenTestCase):
    """Routing engine with wall obstacles (spec 26)."""

    def test_length_and_crossings(self):
        from services.installations_service import InstallationsService
        from services.architecture_service import ArchitectureService
        ctx = self.application.create_project(self.project_path(), "Rutas")
        service = InstallationsService(ctx)
        network = service.create_network("Red rutas", "POWER")
        panel = service.add_node(network.code, "PANEL", 0.0, 1.0)
        outlet = service.add_node(network.code, "OUTLET", 4.0, 1.0)
        arch = ArchitectureService(ctx)
        arch.create_level("N1", 0.0, 3.0)
        arch.create_wall("N1", (2.0, -1.0), (2.0, 3.0))   # wall between nodes
        segment = service.connect(network.code, panel.code, outlet.code)
        self.assertAlmostEqual(segment.length_m, 4.0, places=3)
        self.assertEqual(segment.crossings, 1)
        ctx.close()

    def test_move_node_recomputes_route_length(self):
        from services.installations_service import InstallationsService
        ctx = self.application.create_project(self.project_path(), "Rutas")
        service = InstallationsService(ctx)
        network = service.create_network("Red rutas", "POWER")
        panel = service.add_node(network.code, "PANEL", 0.0, 0.0)
        outlet = service.add_node(network.code, "OUTLET", 3.0, 0.0)
        segment = service.connect(network.code, panel.code, outlet.code)
        self.assertAlmostEqual(segment.length_m, 3.0, places=3)
        service.move_node(outlet.code, 3.0, 4.0)
        moved = ctx.installations.get("SEGMENT", segment.id)
        # New orthogonal route: 3 m horizontal + 4 m vertical.
        self.assertAlmostEqual(moved.length_m, 7.0, places=3)
        ctx.close()


class TestQTOIntegration(ARQGenTestCase):
    """Installation entities feed QTO with conditions and waste (spec 51-52)."""

    def test_installation_quantities_present(self):
        ctx = self.demo_context()
        totals = {}
        for row in ctx.quantities_repo.all(ctx.project.id):
            totals[row["formula_code"]] = totals.get(row["formula_code"], 0.0) + row["final_quantity"]
        self.assertGreater(totals.get("CONDUIT_LENGTH", 0), 0)
        self.assertGreater(totals.get("CONDUCTOR_LENGTH", 0), 0)
        self.assertGreater(totals.get("PIPE_LENGTH", 0), 0)
        self.assertGreater(totals.get("DRAIN_LENGTH", 0), 0)
        self.assertGreater(totals.get("DUCT_LENGTH", 0), 0)
        self.assertGreater(totals.get("DEVICE_COUNT", 0), 0)
        self.assertEqual(totals.get("PANEL_COUNT", 0), 1)
        self.assertGreaterEqual(totals.get("FIXTURE_COUNT", 0), 7)
        self.assertGreaterEqual(totals.get("COOLING_UNITS", 0), 4)
        self.assertGreater(totals.get("INSTALLED_POWER", 0), 0)
        ctx.close()

    def test_conductor_spare_pct_applied(self):
        # CONDUCTOR_LENGTH = length * conductors * (1 + spare/100); demo uses
        # conductors=3 and spare=10 for every electrical segment.
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        total = 0.0
        for segment in ctx.installations.segments_of(network.id):
            conductors = segment.num("conductors")
            total += segment.length_m * conductors * 1.10
        quantities = 0.0
        for row in ctx.quantities_repo.all(ctx.project.id):
            if row["formula_code"] == "CONDUCTOR_LENGTH" and row["object_type"] == "SEGMENT":
                for node in ctx.installations.list("NODE", ctx.project.id):
                    pass
                quantities += row["final_quantity"]
        self.assertAlmostEqual(quantities, total, places=1)
        ctx.close()

    def test_node_move_invalidates_stale(self):
        ctx = self.demo_context()
        from services.installations_service import InstallationsService
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        outlet = [n for n in ctx.installations.nodes_of(network.id)
                  if n.kind == "OUTLET"][0]
        stale_before = len(ctx.quantities_repo.all(ctx.project.id, only_stale=True))
        service.move_node(outlet.code, outlet.x + 1.0, outlet.y)
        stale_after = len(ctx.quantities_repo.all(ctx.project.id, only_stale=True))
        self.assertGreater(stale_after, stale_before)
        ctx.close()


class TestUndoRedoInstallations(ARQGenTestCase):
    """Transactional undo/redo reaches installation entities (spec 77)."""

    def test_undo_node_creation(self):
        from services.installations_service import InstallationsService
        from app.undo_service import PersistentUndoService
        ctx = self.application.create_project(self.project_path(), "Undo")
        service = InstallationsService(ctx)
        network = service.create_network("Red", "POWER")
        service.add_node(network.code, "OUTLET", 1.0, 1.0, attrs={"power_w": 100})
        self.assertEqual(len(ctx.installations.nodes_of(network.id)), 1)
        PersistentUndoService(ctx).undo()
        self.assertEqual(len(ctx.installations.nodes_of(network.id)), 0)
        PersistentUndoService(ctx).redo()
        self.assertEqual(len(ctx.installations.nodes_of(network.id)), 1)
        ctx.close()

    def test_undo_network_deletion_cascades(self):
        from services.installations_service import InstallationsService
        from app.undo_service import PersistentUndoService
        ctx = self.application.create_project(self.project_path(), "Undo")
        service = InstallationsService(ctx)
        network = service.create_network("Red", "POWER")
        panel = service.add_node(network.code, "PANEL", 0.0, 0.0)
        outlet = service.add_node(network.code, "OUTLET", 2.0, 0.0)
        service.connect(network.code, panel.code, outlet.code)
        service.delete_entity("NETWORK", network.code)
        self.assertEqual(ctx.installations.count("NODE", ctx.project.id), 0)
        self.assertEqual(ctx.installations.count("SEGMENT", ctx.project.id), 0)
        PersistentUndoService(ctx).undo()
        self.assertEqual(ctx.installations.count("NODE", ctx.project.id), 2)
        self.assertEqual(ctx.installations.count("SEGMENT", ctx.project.id), 1)
        ctx.close()


class TestPersistenceAndPlugin(ARQGenTestCase):
    """Round-trip persistence and plugin declaration (spec 78, 88)."""

    def test_reopen_keeps_networks(self):
        from services.installations_service import InstallationsService
        path = self.project_path("net.arqgen")
        ctx = self.application.create_project(path, "Persistente")
        service = InstallationsService(ctx)
        network = service.create_network("Red persistente", "COLD_WATER")
        meter = service.add_node(network.code, "METER", 0.0, 0.0)
        fixture = service.add_node(network.code, "FIXTURE", 2.0, 0.0,
                                   attrs={"fixture_kind": "WC", "fixture_units": 3})
        service.connect(network.code, meter.code, fixture.code, kind="PIPE")
        ctx.commit()
        ctx.close()

        ctx2 = self.application.open_project(path)
        self.assertEqual(ctx2.installations.count("NETWORK", ctx2.project.id), 1)
        self.assertEqual(ctx2.installations.count("NODE", ctx2.project.id), 2)
        self.assertEqual(ctx2.installations.count("SEGMENT", ctx2.project.id), 1)
        node = ctx2.installations.list("NODE", ctx2.project.id)[1]
        self.assertEqual(node.attrs.get("fixture_units"), 3)
        ctx2.close()

    def test_plugin_declares_installations(self):
        from app.bootstrap import bootstrap
        application, loader = bootstrap(type("Args", (), {"log_dir": self.tmp, "log_level": "ERROR"})())
        plugin_ids = [entry.plugin.plugin_id for entry in loader.loaded
                      if entry.plugin and not entry.error]
        self.assertIn("installations", plugin_ids)


if __name__ == "__main__":
    import unittest
    unittest.main()
