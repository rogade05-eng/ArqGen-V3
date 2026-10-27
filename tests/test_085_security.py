"""Security engines and service tests with hand-verified values
(spec sections 37-49): FOV, CCTV, fire, intrusion, access, perimeter."""

from __future__ import annotations

import math

from tests.base import ARQGenTestCase

ROOM_WALLS = [((0.0, 0.0), (10.0, 0.0)), ((10.0, 0.0), (10.0, 8.0)),
              ((10.0, 8.0), (0.0, 8.0)), ((0.0, 8.0), (0.0, 0.0))]


class TestFovEngine(ARQGenTestCase):
    """Motor FOV (spec 39): ray casting, cobertura y puntos ciegos."""

    def test_fan_geometry_open_room(self):
        from engines.fov_engine import field_of_view
        # Cámara en (0.5, 0.5) mirando a 45°, FOV 90°, alcance 12 m:
        # cubre casi todo el local de 10x8 salvo las bandas x<0.5, y<0.5.
        coverage = field_of_view("CAM1", (0.5, 0.5), 45.0, 90.0, 12.0, ROOM_WALLS)
        self.assertAlmostEqual(coverage.area_m2, 71.25, delta=1.5)
        self.assertEqual(len(coverage.polygon) >= 4, True)

    def test_wall_blocks_fov(self):
        from engines.fov_engine import field_of_view
        # Con tabique en x=5 y cámara mirando 0°, la cobertura queda
        # limitada a la mitad izquierda del local.
        walls = ROOM_WALLS + [((5.0, 0.0), (5.0, 8.0))]
        coverage = field_of_view("CAM1", (0.5, 0.5), 0.0, 90.0, 12.0, walls)
        self.assertLess(coverage.area_m2, 15.0)
        self.assertGreater(coverage.occluded_walls, 0)

    def test_target_detection(self):
        from engines.fov_engine import field_of_view, target_detection
        coverage = field_of_view("CAM1", (0.5, 0.5), 45.0, 90.0, 12.0, ROOM_WALLS)
        self.assertTrue(target_detection((4.0, 4.0), [coverage]))
        self.assertTrue(target_detection((9.0, 7.0), [coverage]))
        self.assertFalse(target_detection((0.2, 7.0), [coverage]))  # fuera del cono
        self.assertFalse(target_detection((9.0, 0.4), [coverage]))  # detrás

    def test_blind_spots_grid(self):
        from engines.fov_engine import blind_spots, field_of_view
        coverage = field_of_view("CAM1", (0.5, 0.5), 45.0, 90.0, 12.0, ROOM_WALLS)
        blind = blind_spots([(0, 0), (10, 0), (10, 8), (0, 8)], [coverage])
        self.assertAlmostEqual(blind["target_m2"], 80.0, delta=0.5)
        self.assertAlmostEqual(blind["blind_pct"],
                               100.0 - blind["covered_m2"] / 80.0 * 100.0,
                               delta=0.5)

    def test_candidates_deterministic(self):
        from engines.fov_engine import camera_position_candidates
        candidates = camera_position_candidates(
            [(0, 0), (10, 0), (10, 8), (0, 8)], 45.0, 90.0, 12.0,
            ROOM_WALLS, grid_m=2.0)
        self.assertTrue(candidates)
        areas = [area for _pos, area in candidates]
        self.assertEqual(areas, sorted(areas, reverse=True))


class TestCctvEngine(ARQGenTestCase):
    """Cableado (spec 41) y red (spec 42)."""

    def test_camera_cable_length(self):
        from engines.cctv_engine import camera_cable_length_m
        # ruta 20 m + rulo 3 m + desnivel 0 m → 23 × 1,10 = 25.3 m
        self.assertAlmostEqual(camera_cable_length_m(20.0), 25.3, places=2)
        self.assertAlmostEqual(camera_cable_length_m(20.0, vertical_rise_m=2.0),
                               27.5, places=2)

    def test_cabling_report(self):
        from engines.cctv_engine import cabling_report
        report = cabling_report([20.0, 10.0], vertical_rise_m=1.0)
        self.assertEqual(report.cameras, 2)
        self.assertAlmostEqual(report.service_loop_m, 6.0, places=2)
        self.assertAlmostEqual(report.total_route_m, 30.0, places=2)
        # (20+3+1)·1.1 + (10+3+1)·1.1 = 26.4 + 15.4 = 41.8
        self.assertAlmostEqual(report.total_cable_m, 41.8, places=2)

    def test_network_report_bandwidth_and_storage(self):
        from engines.cctv_engine import network_report
        # 4 cámaras 1080P a 4 Mbps: 16 Mbps → 20 Mbps con overhead.
        report = network_report(["1080P"] * 4, retention_days=30)
        self.assertAlmostEqual(report.total_bitrate_mbps, 16.0, places=3)
        self.assertAlmostEqual(report.bandwidth_mbps, 20.0, places=3)
        self.assertAlmostEqual(report.poe_demand_w, 26.0, places=2)
        # Storage = 4 Mbps/8 × 86400 s × 4 cámaras × 30 días / 1000 = 5184 GB
        self.assertAlmostEqual(report.storage_gb, 5184.0, delta=1.0)
        self.assertEqual(report.findings, [])

    def test_network_report_flags_poe_overload(self):
        from engines.cctv_engine import network_report
        # 4K = 12 W por cámara: 24 cámaras → 288 W > presupuesto 240 W.
        report = network_report(["4K"] * 24, poe_budget_w=240.0)
        self.assertTrue(any("PoE" in f for f in report.findings))
        self.assertTrue(any("switch" in f for f in report.findings))
        self.assertTrue(any("NVR" in f for f in report.findings))


class TestFireEngine(ARQGenTestCase):
    """Detección de incendios (spec 43) y causa/efecto (spec 44)."""

    def test_required_detectors(self):
        from engines.fire_engine import required_detectors
        # Local de 80 m2 con radio 7.5 m: π·56.25 = 176.7 m2 → 1 detector.
        self.assertEqual(required_detectors(80.0), 1)
        # Local grande: 500 m2 → ceil(500/176.7) = 3.
        self.assertEqual(required_detectors(500.0), 3)
        # Detector térmico R=5.3: π·28.09 = 88.2 → ceil(80/88.2) = 1;
        # con altura 6 m el radio se reduce 10 % → 4.77 m, 71.5 m2 → 2.
        self.assertEqual(required_detectors(80.0, "HEAT_DETECTOR", 6.0), 2)

    def test_space_coverage(self):
        from engines.fire_engine import check_space_coverage
        report = check_space_coverage("Sala", 80.0, 1)
        self.assertTrue(report.ok)
        report = check_space_coverage("Almacen", 500.0, 2)
        self.assertFalse(report.ok)
        self.assertTrue(report.findings)

    def test_loop_and_battery(self):
        from engines.fire_engine import loop_report
        # 10 detectores (0.1 mA) + 2 sirenas: reposo 1.2 mA (margen 1.2)
        # batería = (0.0012·24 + 0.7·0.5)·1.25 = 0.47375 Ah
        report = loop_report(["SMOKE_DETECTOR"] * 10 + ["SOUNDER"] * 2)
        self.assertAlmostEqual(report.standby_ma, 1.2, places=3)
        self.assertAlmostEqual(report.alarm_a, 0.7, places=3)
        self.assertAlmostEqual(report.battery_ah, 0.4735, places=4)
        self.assertTrue(report.ok)

    def test_loop_device_limit(self):
        from engines.fire_engine import loop_report
        report = loop_report(["SMOKE_DETECTOR"] * 130)
        self.assertFalse(report.ok)
        self.assertTrue(any("lazo" in f.lower() for f in report.findings))

    def test_cause_effect_matrix(self):
        from engines.fire_engine import evaluate_cause_effect
        rules = [
            {"code": "CE-001", "when": "SMOKE_DETECTOR",
             "actions": [{"action": "alarma", "output": "SOUNDER", "delay_s": 0},
                         {"action": "registro", "output": "LOG", "delay_s": 0}]},
            {"code": "CE-006", "when": "SMOKE_DETECTOR", "condition": "night_mode",
             "actions": [{"action": "desbloqueo", "output": "LOCK", "delay_s": 10}]},
        ]
        result = evaluate_cause_effect("SMOKE_DETECTOR", {"night_mode": True}, rules)
        self.assertEqual(len(result.triggered), 3)
        self.assertTrue(result.ok)
        result_day = evaluate_cause_effect("SMOKE_DETECTOR", {"night_mode": False}, rules)
        self.assertEqual(len(result_day.triggered), 2)
        unknown = evaluate_cause_effect("GLASS_BREAK", {}, rules)
        self.assertFalse(unknown.ok)
        self.assertEqual(unknown.missing_rules, ["GLASS_BREAK"])


class TestIntrusionEngine(ARQGenTestCase):
    """Intrusión (spec 45): zonas, panel y batería."""

    def test_required_pirs(self):
        from engines.intrusion_engine import required_pirs
        # Cuarto de círculo útil: π·36/4 = 28.27 m2 → 80 m2 exige 3.
        self.assertEqual(required_pirs(80.0), 3)

    def test_zone_check(self):
        from engines.intrusion_engine import check_zone
        report = check_zone("ZONA-1", 80.0, 3, 2, 2)
        self.assertTrue(report.ok)
        report = check_zone("ZONA-2", 80.0, 1, 0, 3)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.findings), 2)

    def test_panel_report(self):
        from engines.intrusion_engine import Partition, panel_report
        report = panel_report(
            zones=2,
            partitions=[Partition("P1", ("ZONA-1",), True)],
            expanders=1, sirens=1, siren_distance_m=3.0)
        # Batería = (0.06 + 0.04)·24 + 1.2·0.5)·1.25 = 3.75 Ah
        self.assertAlmostEqual(report.battery_ah, 3.75, places=3)
        self.assertTrue(report.ok)
        # Límite de zonas y duplicados.
        report = panel_report(zones=70, partitions=[])
        self.assertFalse(report.ok)
        dup = panel_report(zones=2, partitions=[
            Partition("P1", ("A", "B"), True),
            Partition("P2", ("B",), True)])
        self.assertTrue(any("más de una partición" in f for f in dup.findings))


class TestAccessEngine(ARQGenTestCase):
    """Control de acceso (spec 46)."""

    def test_controller_capacity(self):
        from engines.access_engine import check_controller
        report = check_controller("CTRL-1", 2, 2)
        self.assertTrue(report.ok)
        report = check_controller("CTRL-1", 5, 6)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.findings), 2)

    def test_power_report(self):
        from engines.access_engine import power_report
        # 1 controlador + 2 cerraduras: (0.10 + 0.9)·1.25 = 1.25 A
        report = power_report(1, 2, supply_a=2.0)
        self.assertAlmostEqual(report.demand_a, 1.25, places=3)
        self.assertTrue(report.ok)
        report = power_report(2, 4, supply_a=2.0)
        self.assertFalse(report.ok)

    def test_evacuation_check(self):
        from engines.access_engine import evacuation_check
        self.assertTrue(evacuation_check(True, 0.5, "PUERTA")["ok"])
        report = evacuation_check(True, 10.0, "PUERTA")
        self.assertFalse(report["ok"])
        self.assertTrue(evacuation_check(False, 30.0, "PUERTA")["ok"])


class TestPerimeterEngine(ARQGenTestCase):
    """Perímetro (spec 47)."""

    def test_ring_length(self):
        from engines.perimeter_engine import ring_length
        # Rectángulo 40x30 → anillo de 140 m.
        self.assertAlmostEqual(
            ring_length([(0, 0), (40, 0), (40, 30), (0, 30)]), 140.0, places=6)

    def test_check_perimeter(self):
        from engines.perimeter_engine import check_perimeter
        # Tramo de 40 m: ceil(40/30)+1 = 3 sensores.
        report = check_perimeter([40.0], 3, 1, 1, 1, 1)
        self.assertAlmostEqual(report.fence_length_m, 40.0)
        self.assertEqual(report.required_sensors, 3)
        self.assertTrue(report.ok)
        report = check_perimeter([40.0], 1, 0, 1, 0, 0)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.findings), 3)  # sensores, cámaras y acceso


class TestSecurityService(ARQGenTestCase):
    """SecurityService sobre redes del modelo semántico (spec 37-49)."""

    def _build_security(self, service):
        from services.architecture_service import ArchitectureService
        arch = ArchitectureService(service.ctx)
        level = arch.create_level("N1", 0.0, 3.0)
        space = arch.create_space("N1", "Sala", "LIVING_ROOM",
                                  [(0, 0), (10, 0), (10, 8), (0, 8)])
        # Perímetro del local para el ray casting del FOV.
        for start, end in (((0, 0), (10, 0)), ((10, 0), (10, 8)),
                           ((10, 8), (0, 8)), ((0, 8), (0, 0))):
            arch.create_wall("N1", start, end)
        return level, space

    def test_cctv_coverage_and_network(self):
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="CCTV")
        service = SecurityService(ctx)
        level, _space = self._build_security(service)
        cctv = service.create_network("CCTV Sala", "CCTV")
        service.add_device(cctv.code, "CAMERA", 0.5, 0.5, name="Cam",
                           level_ref=level.code,
                           attrs={"direction_deg": 45.0, "fov_deg": 90.0,
                                  "range_m": 12.0, "resolution": "1080P"})
        nvr = service.add_device(cctv.code, "NVR", 9.5, 7.5, name="NVR")
        service.connect_devices(cctv.code, "Cam", nvr.code)
        coverage = service.cctv_coverage(cctv.code)
        self.assertEqual(coverage["cameras"], 1)
        self.assertAlmostEqual(coverage["rows"][0]["area_m2"], 71.25, delta=1.5)
        network = service.cctv_network(cctv.code, retention_days=30)
        self.assertAlmostEqual(network["report"]["bandwidth_mbps"], 5.0, places=3)
        self.assertEqual(network["report"]["findings"], [])
        cabling = service.cctv_cabling(cctv.code)
        self.assertGreater(cabling["totals"]["total_cable_m"], 0.0)
        self.assertGreaterEqual(ctx.calculations_repo.count_fresh("SEC"), 3)
        ctx.close()

    def test_fire_check_and_cause_effect(self):
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="Fuego")
        service = SecurityService(ctx)
        _level, space = self._build_security(service)
        fire = service.create_network("Detección", "FIRE_ALARM")
        service.add_device(fire.code, "FIRE_PANEL", 1.0, 7.0, name="Panel")
        service.add_device(fire.code, "SMOKE_DETECTOR", 5.0, 4.0,
                           name="DH", space_ref=space.code)
        service.add_device(fire.code, "SOUNDER", 2.0, 6.0, name="Sirena")
        report = service.fire_check(fire.code)
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(len(report["coverage"]), 1)
        self.assertGreater(report["loop"]["battery_ah"], 0.0)
        cause = service.fire_cause_effect(fire.code, "SMOKE_DETECTOR",
                                          {"night_mode": True})
        # CE-001 (5 acciones) + CE-006 nocturna (2 acciones) = 7.
        self.assertEqual(len(cause["result"]["triggered"]), 7)
        ctx.close()

    def test_intrusion_check(self):
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="Intrusión")
        service = SecurityService(ctx)
        _level, space = self._build_security(service)
        intr = service.create_network("Intrusión", "INTRUSION")
        service.add_device(intr.code, "INTRUSION_PANEL", 1.0, 7.5, name="Panel")
        for i in range(3):
            service.add_device(intr.code, "PIR", 3.0 + i, 4.0, name=f"PIR{i}",
                               space_ref=space.code, attrs={"zone": "ZONA-1"})
        service.add_device(intr.code, "SIREN", 2.0, 7.0, name="Sirena")
        report = service.intrusion_check(intr.code)
        self.assertEqual(report["status"], "VALID")
        self.assertEqual(report["panel"]["zones"], 1)
        # Batería: (0.06·24 + 1.2·0.5)·1.25 = 2.55 Ah (sin expandidores).
        self.assertAlmostEqual(report["panel"]["battery_ah"], 2.55, places=3)
        ctx.close()

    def test_access_check(self):
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="Acceso")
        service = SecurityService(ctx)
        self._build_security(service)
        acc = service.create_network("Acceso", "ACCESS_CONTROL")
        service.add_device(acc.code, "ACCESS_CONTROLLER", 9.7, 3.0, name="Ctrl")
        service.add_device(acc.code, "READER", 9.6, 1.1, name="Lector")
        service.add_device(acc.code, "LOCK", 9.6, 0.9, name="Cerradura",
                           attrs={"evacuation": 1, "unlock_s": 0.5})
        report = service.access_check(acc.code)
        self.assertEqual(report["status"], "VALID")
        self.assertAlmostEqual(report["power"]["demand_a"], 0.69, places=2)
        ctx.close()

    def test_perimeter_check(self):
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="Perímetro")
        service = SecurityService(ctx)
        self._build_security(service)
        per = service.create_network("Perímetro", "PERIMETER")
        service.add_device(per.code, "FENCE", 0.0, -1.0, name="Valla",
                           attrs={"length_m": 40.0})
        service.add_device(per.code, "FENCE_SENSOR", 10.0, -1.0, name="S1")
        service.add_device(per.code, "FENCE_SENSOR", 30.0, -1.0, name="S2")
        service.add_device(per.code, "FENCE_SENSOR", 38.0, -1.0, name="S3")
        service.add_device(per.code, "GATE", 20.0, -1.0, name="Portón")
        service.add_device(per.code, "PERIMETER_CAMERA", 15.0, -1.5, name="CP")
        service.add_device(per.code, "ACCESS_CONTROLLER", 20.5, -1.2,
                           name="Acceso portón")
        report = service.perimeter_check(per.code)
        self.assertTrue(report["report"]["ok"])
        self.assertEqual(report["report"]["required_sensors"], 3)
        ctx.close()

    def test_security_bom(self):
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="BOM")
        service = SecurityService(ctx)
        self._build_security(service)
        fire = service.create_network("Detección", "FIRE_ALARM")
        service.add_device(fire.code, "FIRE_PANEL", 1.0, 7.0, name="Panel")
        service.add_device(fire.code, "SMOKE_DETECTOR", 5.0, 4.0, name="DH")
        bom = service.security_bom()
        kinds = {item["kind"]: item["count"] for item in bom["items"]}
        self.assertEqual(kinds.get("FIRE_PANEL"), 1)
        self.assertEqual(kinds.get("SMOKE_DETECTOR"), 1)
        ctx.close()

    def test_move_device_propagates(self):
        """Mover cámara → FOV recalculado (spec 49: propagación)."""
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="Prop")
        service = SecurityService(ctx)
        level, _space = self._build_security(service)
        cctv = service.create_network("CCTV", "CCTV")
        service.add_device(cctv.code, "CAMERA", 0.5, 0.5, name="Cam",
                           level_ref=level.code, attrs={"direction_deg": 45.0})
        before = service.cctv_coverage(cctv.code)["rows"][0]["area_m2"]
        service.move_device("Cam", 5.0, 4.0)
        after = service.cctv_coverage(cctv.code)["rows"][0]["area_m2"]
        self.assertNotEqual(before, after)
        ctx.close()


class TestSecurityQTO(ARQGenTestCase):
    """QTO de seguridad (spec 51-52)."""

    def test_security_formulas(self):
        from services.quantity_service import QuantityService
        from services.security_service import SecurityService
        ctx = self.application.create_project(self.project_path(), name="QTO SEC")
        ctx.user = "tester"
        QuantityService(ctx).install_default_formulas()
        service = SecurityService(ctx)
        cctv = service.create_network("CCTV", "CCTV")
        service.add_device(cctv.code, "CAMERA", 0.5, 0.5, name="Cam")
        service.add_device(cctv.code, "NVR", 9.5, 7.5, name="NVR")
        service.add_device(cctv.code, "POE_SWITCH", 9.2, 7.4, name="PoE")
        service.connect_devices(cctv.code, "Cam", "NVR")
        QuantityService(ctx).compute_all()
        totals = QuantityService(ctx).totals_by_formula()
        self.assertAlmostEqual(totals.get("CAMERA_COUNT", 0), 1.0)
        self.assertAlmostEqual(totals.get("RECORDER_COUNT", 0), 1.0)
        self.assertAlmostEqual(totals.get("SEC_CONTROLLER_COUNT", 0), 1.0)
        self.assertGreater(totals.get("SEC_CABLE_LENGTH", 0), 0.0)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
