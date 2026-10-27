"""Sanitary and HVAC engine/service tests with hand-verified values (spec 28, 29)."""

from __future__ import annotations

from tests.base import ARQGenTestCase


class TestSanitaryEngine(ARQGenTestCase):
    """Pure calculations of the sanitary engine (spec 28)."""

    def test_simultaneity_and_design_flow(self):
        from engines.sanitary_engine import simultaneity, design_flow_ls
        self.assertAlmostEqual(simultaneity(1), 1.0)
        self.assertAlmostEqual(simultaneity(4), 0.9)       # 1.8/2
        self.assertAlmostEqual(simultaneity(100), 0.18)    # 1.8/10
        # 4 fixtures of 0.10/0.10/0.15/0.15 -> k=0.9 * 0.5 = 0.45 L/s
        self.assertAlmostEqual(design_flow_ls([0.10, 0.10, 0.15, 0.15]), 0.45, places=4)

    def test_hazen_williams_monotonic(self):
        from engines.sanitary_engine import hazen_williams_j
        # Larger diameter -> smaller unit loss; larger flow -> larger loss.
        self.assertLess(hazen_williams_j(0.5, 25, "PVC"), hazen_williams_j(0.5, 19, "PVC"))
        self.assertGreater(hazen_williams_j(1.0, 25, "PVC"), hazen_williams_j(0.5, 25, "PVC"))
        self.assertAlmostEqual(hazen_williams_j(0.0, 25), 0.0)

    def test_pressure_diameter_selection(self):
        from engines.sanitary_engine import select_pressure_diameter, velocity_ms
        dn, v = select_pressure_diameter(0.5)
        self.assertEqual(dn, 19.0)
        self.assertAlmostEqual(v, velocity_ms(0.5, 19.0), places=6)

    def test_min_slope_table(self):
        from engines.sanitary_engine import min_slope_pct
        self.assertAlmostEqual(min_slope_pct(50), 2.08)
        self.assertAlmostEqual(min_slope_pct(75), 1.04)
        self.assertAlmostEqual(min_slope_pct(150), 0.52)

    def test_drain_diameter_selection(self):
        from engines.sanitary_engine import select_drain_diameter
        dn, slope, capacity = select_drain_diameter(0.6)
        self.assertEqual(dn, 50.0)
        self.assertAlmostEqual(slope, 2.08)
        self.assertGreaterEqual(capacity, 0.6)

    def test_pump_sizing_exact(self):
        from engines.sanitary_engine import size_pump
        result = size_pump(1.0, 8.0, 2.0)
        self.assertAlmostEqual(result.tdh_m, 15.0, places=3)
        # P = 1000 * 9.81 * 0.001 * 15 / 1000 = 0.147 kW (rounded to mm)
        self.assertAlmostEqual(result.hydraulic_kw, 0.147, places=3)
        self.assertAlmostEqual(result.electric_kw, 0.147 / 0.7, places=3)

    def test_tank_volume(self):
        from engines.sanitary_engine import tank_volume_ls
        self.assertAlmostEqual(tank_volume_ls(150, 4, 1.0), 600.0)


class TestSanitaryService(ARQGenTestCase):
    """Network sizing on the demo sanitary networks (spec 28)."""

    def test_cold_water_sizing(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        result = service.size_sanitary("Agua Fría Sanitaria")
        self.assertEqual(len(result["rows"]), 5)
        for row in result["rows"]:
            self.assertEqual(row["fixtures"], 1)
            self.assertGreater(row["diameter_mm"], 0)
            self.assertLessEqual(row["velocity_ms"], 2.0)
        ctx.close()

    def test_drainage_accumulates_flows(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        result = service.size_sanitary("Desagüe Sanitario")
        rows = {r["segment"]: r for r in result["rows"]}
        collector = [r for r in result["rows"] if r["fixtures"] == 2][0]
        self.assertAlmostEqual(collector["q_ls"], 0.25, places=3)  # 0.10 + 0.15
        self.assertGreater(collector["capacity_ls"], collector["q_ls"])
        ctx.close()

    def test_sizing_stores_san_calculation(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        service.size_sanitary("Agua Fría Sanitaria")
        self.assertGreaterEqual(ctx.calculations_repo.count_fresh("SAN"), 1)
        ctx.close()


class TestHVACEngine(ARQGenTestCase):
    """Pure calculations of the HVAC engine (spec 29)."""

    def test_thermal_load_components(self):
        from engines.hvac_engine import thermal_load
        load = thermal_load(area_m2=20, height_m=3, exposed_wall_area_m2=12,
                            glazing_area_m2=2.0, roof_area_m2=20)
        # transmission = (12*2.0 + 2*5.8 + 20*1.5) * 9 = 590.4 W
        self.assertAlmostEqual(load.transmission_w, 590.4, places=1)
        # solar = 2 * 180 = 360 W
        self.assertAlmostEqual(load.solar_w, 360.0, places=1)
        # internal sensible = 2*75 + 20*(10+5) = 450 W; latent = 2*55 = 110 W
        self.assertAlmostEqual(load.internal_sensible_w, 450.0, places=1)
        self.assertAlmostEqual(load.internal_latent_w, 110.0, places=1)
        # ventilation = 1.2*1005*60*0.5/3600*9 = 90.45 W
        self.assertAlmostEqual(load.ventilation_w, 90.45, places=1)
        self.assertAlmostEqual(load.cooling_total_w,
                               load.cooling_sensible_w + 110.0, places=1)
        self.assertAlmostEqual(load.cooling_btu_h, load.cooling_total_w * 3.4121, places=1)

    def test_airflow_exact(self):
        from engines.hvac_engine import calculate_airflow
        # Q = 1490.9 W / (1.2*1005*10) * 3600 = 445.0 m3/h
        self.assertAlmostEqual(calculate_airflow(1490.9, 10.0), 445.0, places=0)

    def test_duct_sizing_round(self):
        from engines.hvac_engine import size_duct
        sizing = size_duct(445.0, kind="MAIN")
        self.assertEqual(sizing.shape, "ROUND")
        self.assertEqual(sizing.diameter_mm, 180.0)
        self.assertLessEqual(sizing.velocity_ms, 8.0)
        self.assertTrue(sizing.ok)

    def test_duct_sizing_rect(self):
        from engines.hvac_engine import size_duct
        sizing = size_duct(1000.0, kind="BRANCH", shape="RECT")
        self.assertEqual(sizing.shape, "RECT")
        self.assertGreater(sizing.width_mm, sizing.height_mm)
        self.assertLessEqual(sizing.width_mm / sizing.height_mm, 4.0)

    def test_duct_velocity_limit(self):
        from engines.hvac_engine import size_duct
        from core.errors import CalculationError
        with self.assertRaises(CalculationError):
            size_duct(1000.0, kind="RETURN", target_velocity_ms=6.0)  # max 4

    def test_equipment_selection(self):
        from engines.hvac_engine import select_equipment
        # 5462 BTU/h * 1.1 = 6008 -> smallest unit 9000
        result = select_equipment(5462.0)
        self.assertEqual(result.units, 1)
        self.assertEqual(result.unit_btu_h, 9000.0)
        # 15000 * 1.1 = 16500 -> 18000
        self.assertEqual(select_equipment(15000.0).unit_btu_h, 18000.0)
        # 40000 * 1.1 = 44000 -> single 48000 unit (largest fitting the load)
        big = select_equipment(40000.0)
        self.assertEqual(big.units, 1)
        self.assertEqual(big.unit_btu_h, 48000.0)


class TestHVACService(ARQGenTestCase):
    """Thermal loads of the demo spaces and duct network sizing (spec 29)."""

    def test_demo_space_loads(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        loads = service.hvac_loads_all()
        self.assertEqual(len(loads), 4)
        by_code = {row["space"]: row for row in loads}
        sala = by_code.get([s.code for s in ctx.architecture.list("SPACE", ctx.project.id)
                            if s.name == "Sala"][0])
        self.assertEqual(sala["equipment"]["unit_btu_h"], 12000)
        self.assertGreater(sala["cooling_total_w"], 0)
        self.assertGreater(sala["airflow_m3h"], 0)
        ctx.close()

    def test_exhaust_network_sized(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        result = service.size_hvac_network("Extracción Baño")
        sized = [r for r in result["rows"] if r.get("airflow_m3h", 0) > 0]
        self.assertEqual(len(sized), 1)
        self.assertAlmostEqual(sized[0]["airflow_m3h"], 60.0, places=1)
        self.assertGreater(sized[0]["diameter_mm"], 0)
        ctx.close()

    def test_hvac_calculation_stored(self):
        from services.installations_service import InstallationsService
        ctx = self.demo_context()
        service = InstallationsService(ctx)
        space = [s for s in ctx.architecture.list("SPACE", ctx.project.id)
                 if s.name == "Dormitorio"][0]
        service.space_thermal_load(space.code)
        self.assertGreaterEqual(ctx.calculations_repo.count_fresh("HVAC"), 1)
        ctx.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
