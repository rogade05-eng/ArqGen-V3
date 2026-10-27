"""Electrical engine and service tests with hand-verified values (spec 27)."""

from __future__ import annotations

from tests.base import ARQGenTestCase


class TestElectricalEngine(ARQGenTestCase):
    """Pure calculations of the electrical engine (spec 27)."""

    def test_current_single_phase(self):
        from engines.electrical_engine import current_a
        self.assertAlmostEqual(current_a(2200, 220, 1.0), 10.0, places=9)
        self.assertAlmostEqual(current_a(1100, 220, 0.8), 6.25, places=6)

    def test_current_three_phase(self):
        from engines.electrical_engine import current_a
        # I = 5000 / (sqrt(3) * 380 * 0.8) = 9.4959 A
        self.assertAlmostEqual(current_a(5000, 380, 0.8, 3), 9.4959, places=3)

    def test_voltage_drop_single_phase(self):
        from engines.electrical_engine import voltage_drop_pct
        # dV = 2 * 0.0175 * 20 * 10 / 2.5 = 2.8 V -> 1.2727 %
        self.assertAlmostEqual(voltage_drop_pct(2.5, 20, 10, 220, 1),
                               1.2727, places=3)

    def test_voltage_drop_three_phase(self):
        from engines.electrical_engine import voltage_drop_pct
        # dV = sqrt(3) * 0.0175 * 50 * 30 / 16 = 2.8417 V -> 0.7478 % (380 V)
        self.assertAlmostEqual(voltage_drop_pct(16, 50, 30, 380, 3),
                               0.7478, places=3)

    def test_breaker_selection(self):
        from engines.electrical_engine import select_breaker
        self.assertEqual(select_breaker(9.9), 10.0)
        self.assertEqual(select_breaker(10.0), 10.0)
        self.assertEqual(select_breaker(10.1), 16.0)
        self.assertEqual(select_breaker(70.0), 80.0)

    def test_section_selection_coordination(self):
        from engines.electrical_engine import select_section
        # 10 A at 25 m, 1ph: 1.5 mm2 ampacity 19.5 >= 10 and VD 2.65% <= 3%
        section, ampacity = select_section(10.0, 25.0, 220, 1)
        self.assertEqual(section, 1.5)
        self.assertEqual(ampacity, 19.5)
        # A 16 A breaker forces 2.5 mm2 (1.5 ampacity 19.5 < 16? no: 19.5>=16).
        # Coordination uses breaker: In=16 -> 1.5 mm2 ampacity 19.5 OK, but the
        # design current doubles the load below to force a larger section.
        section2, _ = select_section(13.0, 60.0, 220, 1)
        # VD at 1.5: 2*0.0175*60*13/1.5 = 18.2 V = 8.27% > 3% -> next section...
        self.assertGreaterEqual(section2, 6.0)

    def test_conduit_selection(self):
        from engines.electrical_engine import select_conduit
        # 2.5 mm2 cable (outer 3.6 mm), 3 conductors -> 16 mm conduit
        self.assertEqual(select_conduit(2.5, 3), 16.0)
        # 10 mm2 cable (outer 5.6), 5 conductors -> larger conduit
        self.assertGreaterEqual(select_conduit(10.0, 5), 20.0)

    def test_phase_balance(self):
        from engines.electrical_engine import phase_balance
        result = phase_balance({1: 3000.0, 2: 2000.0, 3: 2500.0})
        self.assertAlmostEqual(result["imbalance_pct"], 40.0, places=2)


class TestElectricalService(ARQGenTestCase):
    """Circuit checks and panel summary over the demo networks (spec 27)."""

    def test_lighting_circuit_check(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        protection = [n for n in ctx.installations.nodes_of(network.id)
                      if n.attrs.get("kind_circuit") == "LIGHTING"][0]
        result = service.circuit_check(protection.code)
        self.assertEqual(result["load"]["connected_w"], 180)   # 72+48+36+24
        self.assertAlmostEqual(result["load"]["current_a"], 180 / 220, places=2)
        self.assertEqual(result["breaker_standard"], 10.0)     # attr rating_a
        self.assertEqual(result["load"]["devices"], 4)
        ctx.close()

    def test_power_circuit_demand(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        protection = [n for n in ctx.installations.nodes_of(network.id)
                      if n.attrs.get("kind_circuit") == "POWER"][0]
        result = service.circuit_check(protection.code)
        self.assertEqual(result["load"]["connected_w"], 2600)  # 600+500+1500
        self.assertAlmostEqual(result["load"]["current_a"], 2600 / 220, places=2)
        ctx.close()

    def test_climate_circuit_includes_splits(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        climate = [n for n in ctx.installations.nodes_of(network.id)
                   if n.attrs.get("kind_circuit") == "CLIMATE"][0]
        result = service.circuit_check(climate.code)
        self.assertEqual(result["load"]["connected_w"], 4400)  # 4 splits x 1100 W
        self.assertEqual(result["load"]["devices"], 4)
        self.assertAlmostEqual(result["load"]["current_a"], 20.0, places=2)
        ctx.close()

    def test_panel_summary_totals(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        panel = [n for n in ctx.installations.nodes_of(network.id)
                 if n.kind == "PANEL"][0]
        result = service.panel_summary(panel.code)
        self.assertEqual(result["total_connected_w"], 7180)
        self.assertEqual(len(result["circuits"]), 3)
        self.assertEqual(result["main_breaker_a"], 63)  # from panel attrs
        ctx.close()

    def test_oversized_load_flagged(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        protection = [n for n in ctx.installations.nodes_of(network.id)
                      if n.attrs.get("kind_circuit") == "POWER"][0]
        # Demand 3600 W -> 16.4 A above the 16 A protection.
        outlet = [n for n in ctx.installations.nodes_of(network.id)
                  if n.kind == "OUTLET"][0]
        service.set_node_attrs(outlet.code, {"power_w": 1600})
        result = service.circuit_check(protection.code)
        self.assertFalse(result["ok"])
        self.assertTrue(any("protección" in f for f in result["findings"]))
        ctx.close()

    def test_calculation_record_stored(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        network = service.resolve_network("Fuerza e Iluminación")
        protection = [n for n in ctx.installations.nodes_of(network.id)
                      if n.attrs.get("kind_circuit") == "POWER"][0]
        service.circuit_check(protection.code)
        self.assertGreaterEqual(ctx.calculations_repo.count_fresh("ELEC"), 1)
        ctx.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
