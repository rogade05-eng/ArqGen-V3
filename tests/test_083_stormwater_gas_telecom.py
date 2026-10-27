"""Stormwater, gas and telecom engine/service tests with hand-verified
values (spec sections 30, 31, 32)."""

from __future__ import annotations

from tests.base import ARQGenTestCase


class TestStormwaterEngine(ARQGenTestCase):
    """Pure calculations of the stormwater engine (spec 30)."""

    def test_runoff_rational_method(self):
        from engines.stormwater_engine import runoff_coefficient, runoff_ls
        # Q = C·i·A/3600 = 0.9·100·80/3600 = 2.0 L/s
        self.assertAlmostEqual(runoff_ls(80.0, 100.0, 0.90), 2.0, places=4)
        self.assertAlmostEqual(runoff_ls(100.0, 100.0, 1.0), 100.0 / 36.0, places=4)
        self.assertAlmostEqual(runoff_coefficient("ROOF"), 0.90)
        self.assertAlmostEqual(runoff_coefficient("GRASS"), 0.25)
        # Unknown surface falls back to the prudent default.
        self.assertAlmostEqual(runoff_coefficient("UNKNOWN"), 0.80)

    def test_runoff_rejects_invalid_input(self):
        from core.errors import CalculationError
        from engines.stormwater_engine import runoff_ls
        with self.assertRaises(CalculationError):
            runoff_ls(-1.0)
        with self.assertRaises(CalculationError):
            runoff_ls(10.0, 100.0, 1.5)  # coeff > 1

    def test_gutter_capacity_manning(self):
        from engines.stormwater_engine import gutter_capacity_ls
        # Demo gutter 150x75 at 0.5 %: capacity 7.427 L/s (hand-verified).
        self.assertAlmostEqual(gutter_capacity_ls(150, 75, 0.5), 7.427, places=3)
        self.assertEqual(gutter_capacity_ls(150, 75, 0.0), 0.0)
        # Larger slope -> more capacity.
        self.assertGreater(gutter_capacity_ls(150, 75, 1.0),
                           gutter_capacity_ls(150, 75, 0.5))

    def test_gutter_selection(self):
        from engines.stormwater_engine import select_gutter
        width, depth, capacity = select_gutter(2.0)
        self.assertEqual(width, 100.0)          # smallest commercial gutter
        self.assertEqual(depth, 50.0)
        self.assertGreaterEqual(capacity, 2.0)

    def test_downpipe_selection(self):
        from engines.stormwater_engine import downpipe_capacity_ls, select_downpipe
        self.assertAlmostEqual(downpipe_capacity_ls(75), 4.0)
        dn, capacity = select_downpipe(2.0)
        self.assertEqual(dn, 75.0)              # 50 mm carries only 1.5 L/s
        dn2, capacity2 = select_downpipe(5.0)
        self.assertEqual(dn2, 100.0)
        self.assertGreaterEqual(capacity2, 5.0)

    def test_detention_volume(self):
        from engines.stormwater_engine import detention_volume_ls
        result = detention_volume_ls(2.0, 15.0)
        self.assertAlmostEqual(result.volume_l, 1800.0, places=1)
        self.assertAlmostEqual(result.retention_min, 15.0)

    def test_outfall_margin(self):
        from engines.stormwater_engine import outfall_required_capacity
        self.assertAlmostEqual(outfall_required_capacity(2.0), 2.2, places=4)


class TestStormwaterService(ARQGenTestCase):
    """Stormwater network sizing on the demo network (spec 30)."""

    def test_size_stormwater_accumulates_flows(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        report = service.size_stormwater("Pluvial Cubierta")
        # Total captación: (45 + 35) m2 roof, C=0.9, i=100 mm/h.
        self.assertAlmostEqual(report["captured_ls"], 2.0, places=3)
        # Evacuación = captación + 10 %.
        self.assertAlmostEqual(report["outfall_required_ls"], 2.2, places=3)
        # Detention tank: 2.0 L/s during 15 min.
        self.assertAlmostEqual(report["detention"]["volume_l"], 1800.0, places=1)
        # Gutter capacity must exceed the inflow (spec: canalón dimensionado).
        for gutter in report["gutters"]:
            self.assertGreaterEqual(gutter["capacity_ls"], gutter["inflow_ls"])
        # The collector that gathers both drains carries the full 2.0 L/s.
        collectors = [r for r in report["rows"] if abs(r["q_ls"] - 2.0) < 1e-6]
        self.assertTrue(collectors, "ningún colector acumula el caudal total")
        for row in report["rows"]:
            self.assertGreater(row["diameter_mm"], 0)
            self.assertGreaterEqual(row["capacity_ls"], row["q_ls"])
        ctx.close()

    def test_stormwater_rejects_other_systems(self):
        from core.errors import DomainError
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        with self.assertRaises(DomainError):
            service.size_stormwater("Agua Fría Sanitaria")  # COLD_WATER
        ctx.close()


class TestGasEngine(ARQGenTestCase):
    """Pure calculations of the gas engine (spec 31)."""

    def test_gas_flow_and_units(self):
        from engines.gas_engine import consumption_units, gas_flow_m3h
        # q = P/PCI = 12/10.6 = 1.1321 m3/h
        self.assertAlmostEqual(gas_flow_m3h(12.0), 1.1321, places=4)
        self.assertAlmostEqual(gas_flow_m3h(3.5, efficiency=0.9), 3.5 / (10.6 * 0.9),
                               places=4)
        # UC = kW / 2.33
        self.assertAlmostEqual(consumption_units(12.0), 5.15, places=2)

    def test_gas_flow_rejects_invalid(self):
        from core.errors import CalculationError
        from engines.gas_engine import gas_flow_m3h
        with self.assertRaises(CalculationError):
            gas_flow_m3h(-1.0)
        with self.assertRaises(CalculationError):
            gas_flow_m3h(1.0, pci_kwh_m3=0.0)

    def test_darcy_weisbach_dp(self):
        from engines.gas_engine import segment_dp_pa, velocity_ms
        # Demo first segment: q=1.4623 m3/h, DN15, L=0.8 m -> v≈2.30 m/s, dp≈3.5 Pa.
        v = velocity_ms(1.4623, 15.0)
        self.assertAlmostEqual(v, 2.30, places=2)
        dp = segment_dp_pa(1.4623, 15.0, 0.8)
        self.assertAlmostEqual(dp, 3.5, places=1)
        # No flow, no loss.
        self.assertEqual(segment_dp_pa(0.0, 15.0, 0.8), 0.0)

    def test_gas_diameter_selection(self):
        from engines.gas_engine import MAX_GAS_VELOCITY_MS, select_gas_diameter
        dn, dp, v = select_gas_diameter(1.4623, 0.8)
        self.assertEqual(dn, 15.0)               # smallest DN fits
        self.assertLessEqual(dp, 5000.0)
        self.assertLessEqual(v, MAX_GAS_VELOCITY_MS)
        # A long run with high flow must upsize the diameter.
        dn_big, _, _ = select_gas_diameter(30.0, 40.0)
        self.assertGreater(dn_big, 15.0)

    def test_required_vent_area(self):
        from engines.gas_engine import required_vent_area_m2
        self.assertAlmostEqual(required_vent_area_m2(20.0), 0.4)   # 1/50 del suelo
        self.assertAlmostEqual(required_vent_area_m2(1.0), 0.02)   # mínimo absoluto


class TestGasService(ARQGenTestCase):
    """Gas sizing and validation on the demo network (spec 31)."""

    def test_size_gas_rows(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        report = service.size_gas("Gas Doméstico")
        self.assertEqual(len(report["rows"]), 6)   # 6 segments
        self.assertEqual(report["appliances"], 2)  # encimera + calefón
        # Downstream segments serve both appliances -> (3.5+12)/2.33 = 6.65 UC.
        rows = {r["segment"]: r for r in report["rows"]}
        max_uc = max(r["uc_served"] for r in report["rows"])
        self.assertAlmostEqual(max_uc, 6.65, places=2)
        for row in report["rows"]:
            self.assertGreater(row["diameter_mm"], 0)
            self.assertLessEqual(row["velocity_ms"], 5.0 + 1e-9)
        ctx.close()

    def test_validate_gas_ok(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        report = service.validate_gas("Gas Doméstico")
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(report["errors"], [])
        ctx.close()

    def test_validate_gas_detects_missing_valve(self):
        """An appliance without its shut-off valve must be flagged (spec 31)."""
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        # New network: appliance connected straight to the regulator.
        net = service.create_network("Gas prueba", "GAS")
        source = service.add_node(net.code, "SOURCE", 0.0, 0.0, name="Fuente")
        appliance = service.add_node(net.code, "APPLIANCE", 3.0, 0.0, name="Cocina",
                                     attrs={"power_kw": 3.5, "vent_area_m2": 0.25})
        service.connect(net.code, source.code, appliance.code, kind="PIPE",
                        material="COPPER")
        report = service.validate_gas(net.code)
        self.assertEqual(report["status"], "INVALID")
        self.assertTrue(any("válvula" in e.lower() or "valve" in e.lower()
                            for e in report["errors"]),
                        f"se esperaba aviso de válvula: {report['errors']}")
        ctx.close()


class TestTelecomEngine(ARQGenTestCase):
    """Pure calculations of the telecom engine (spec 32)."""

    def test_conduit_fill(self):
        from engines.telecom_engine import conduit_fill_pct, select_conduit
        # 4 Cat6 cables (6 mm) in a 20 mm conduit: 36 % (hand-verified).
        self.assertAlmostEqual(conduit_fill_pct(4, 6.0, 20.0), 36.0, places=1)
        dn, fill = select_conduit(4, 6.0)
        self.assertEqual(dn, 20.0)               # 16 mm gives > 40 %
        self.assertLessEqual(fill, 40.0)

    def test_link_length_findings(self):
        from engines.telecom_engine import link_length_findings
        self.assertEqual(link_length_findings(85.0), ())
        self.assertTrue(link_length_findings(95.0))  # TIA-568 90 m exceeded

    def test_cable_diameter_catalog(self):
        from engines.telecom_engine import cable_diameter_mm
        self.assertAlmostEqual(cable_diameter_mm("CAT6"), 6.0)
        self.assertAlmostEqual(cable_diameter_mm("cat7"), 8.5)   # case insensitive
        self.assertAlmostEqual(cable_diameter_mm("MYSTERY"), 6.0)  # default

    def test_rack_summary(self):
        from engines.telecom_engine import rack_summary
        summary = rack_summary("R1", 12.0, ("PATCH_PANEL", "TELECOM_SWITCH"))
        self.assertAlmostEqual(summary.used_u, 2.0)
        self.assertEqual(summary.devices, 2)
        self.assertEqual(summary.findings, ())
        saturated = rack_summary("R2", 1.0, ("PATCH_PANEL", "TELECOM_SWITCH"))
        self.assertTrue(saturated.findings)

    def test_fiber_optical_budget(self):
        from engines.telecom_engine import fiber_budget_findings, fiber_loss_db
        # 100 m OM3 + 2 connectors: 0.35 + 1.5 = 1.85 dB.
        self.assertAlmostEqual(fiber_loss_db(100.0, 2, 0), 1.85, places=3)
        self.assertEqual(fiber_budget_findings(100.0, 2, 0, 3.6), ())
        self.assertTrue(fiber_budget_findings(500.0, 2, 2, 3.6))


class TestTelecomService(ARQGenTestCase):
    """Telecom sizing on the demo network (spec 32)."""

    def test_size_telecom_rows(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        report = service.size_telecom("Telecomunicaciones")
        self.assertEqual(len(report["rows"]), 6)  # 6 links
        kinds = {r["kind"] for r in report["rows"]}
        self.assertIn("FIBER", kinds)
        for row in report["rows"]:
            if row["kind"] == "CONDUIT":
                self.assertLessEqual(row["fill_pct"], 40.0)
        # One rack with patch panel + switch = 2.0 U.
        self.assertEqual(len(report["racks"]), 1)
        self.assertAlmostEqual(report["racks"][0]["used_u"], 2.0)
        self.assertEqual(len(report["panels"]), 2)  # patch panel + switch ports
        ctx.close()


class TestSecurityQTOIntegration(ARQGenTestCase):
    """QTO integration of the new systems (spec 51-52)."""

    def test_new_system_formulas_in_qto(self):
        ctx = self.demo_context()
        totals = {}
        for row in ctx.quantities_repo.all(ctx.project.id):
            totals[row["formula_code"]] = \
                totals.get(row["formula_code"], 0.0) + row["final_quantity"]
        # Pluviales
        self.assertAlmostEqual(totals.get("ROOF_DRAIN_COUNT", 0), 2.0)
        self.assertAlmostEqual(totals.get("GUTTER_LENGTH", 0), 10.0)
        self.assertGreater(totals.get("STORM_TANK_VOLUME", 0), 0)
        self.assertGreater(totals.get("DRAIN_LENGTH", 0), 0)
        # Gas
        self.assertGreater(totals.get("GAS_PIPE_LENGTH", 0), 0)
        self.assertAlmostEqual(totals.get("GAS_APPLIANCE_COUNT", 0), 2.0)
        self.assertAlmostEqual(totals.get("GAS_INSTALLED_POWER", 0), 15500.0)
        # Telecom
        self.assertGreater(totals.get("TELECOM_CONDUIT_LENGTH", 0), 0)
        self.assertGreater(totals.get("FIBER_LENGTH", 0), 0)
        self.assertAlmostEqual(totals.get("TELECOM_OUTLET_COUNT", 0), 4.0)
        self.assertAlmostEqual(totals.get("RACK_COUNT", 0), 1.0)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
