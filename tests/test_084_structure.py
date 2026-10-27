"""Structure engine and service tests with hand-verified values (spec 33-34)."""

from __future__ import annotations

import math

from tests.base import ARQGenTestCase


class TestSectionProperties(ARQGenTestCase):
    """Secciones: áreas, inercias y pesos (perfiles)."""

    def test_rectangle(self):
        from engines.structure_engine import section_properties
        props = section_properties("RECTANGLE", h_mm=300, b_mm=300)
        self.assertAlmostEqual(props.area_m2, 0.09, places=6)
        self.assertAlmostEqual(props.ix_m4, 0.3 * 0.3 ** 3 / 12.0, places=9)
        self.assertAlmostEqual(props.radius_gyration_m,
                               math.sqrt(0.000675 / 0.09), places=6)

    def test_circle(self):
        from engines.structure_engine import section_properties
        props = section_properties("CIRCLE", d_mm=200)
        self.assertAlmostEqual(props.area_m2, math.pi * 0.01, places=6)
        self.assertAlmostEqual(props.ix_m4, math.pi * 0.1 ** 4 / 4.0, places=9)

    def test_i_profile(self):
        from engines.structure_engine import section_properties
        # IPE-300 aproximado: h=300, b=150, tw=7.1, tf=10.7
        props = section_properties("I_PROFILE", h_mm=300, b_mm=150,
                                   tw_mm=7.1, tf_mm=10.7)
        # Área = 2·150·10.7 + (300-21.4)·7.1 = 3209.7 + 1978.1 = 5187.8 mm2
        self.assertAlmostEqual(props.area_m2, 5187.8e-6, places=6)
        # El perfil I debe tener mucho más módulo resistente que un
        # rectángulo de la misma área.
        rect = section_properties("RECTANGLE", h_mm=300,
                                  b_mm=props.area_m2 * 1e6 / 300.0)
        self.assertGreater(props.wel_cm3, rect.wel_cm3)

    def test_rejects_invalid(self):
        from core.errors import CalculationError
        from engines.structure_engine import section_properties
        with self.assertRaises(CalculationError):
            section_properties("RECTANGLE", h_mm=0, b_mm=200)
        with self.assertRaises(CalculationError):
            section_properties("TRIANGLE", h_mm=100, b_mm=100)


class TestBeamAnalysis(ARQGenTestCase):
    """Viga: reacciones, cortante, momento y flecha (spec 34)."""

    def test_simple_beam_udl(self):
        from engines.structure_engine import beam_analysis
        result = beam_analysis(6.0, udl_kn_m=10.0)
        self.assertAlmostEqual(result.reaction_a_kn, 30.0, places=9)
        self.assertAlmostEqual(result.reaction_b_kn, 30.0, places=9)
        self.assertAlmostEqual(result.shear_max_kn, 30.0, places=9)
        self.assertAlmostEqual(result.moment_max_knm, 45.0, places=9)  # wL²/8

    def test_simple_beam_point_load_center(self):
        from engines.structure_engine import beam_analysis
        result = beam_analysis(4.0, point_loads=[(2.0, 20.0)])
        self.assertAlmostEqual(result.reaction_a_kn, 10.0, places=9)
        self.assertAlmostEqual(result.moment_max_knm, 20.0, places=9)  # PL/4

    def test_cantilever_udl(self):
        from engines.structure_engine import beam_analysis
        result = beam_analysis(2.0, udl_kn_m=5.0, support="CANTILEVER")
        self.assertAlmostEqual(result.reaction_a_kn, 10.0, places=9)
        self.assertAlmostEqual(result.moment_max_knm, 10.0, places=9)  # wL²/2

    def test_deflection_known_value(self):
        from engines.structure_engine import beam_analysis
        # δ = 5wL⁴/(384EI): w=10 kN/m, L=6, E=21 GPa, I=0.000675 m4
        # δ = 5·10000·1296/(384·21e9·0.000675) = 11.921 mm (aprox)
        result = beam_analysis(6.0, udl_kn_m=10.0, e_gpa=21.0, ix_m4=0.000675)
        expected = 5.0 * 10000.0 * 6.0 ** 4 / (384.0 * 21e9 * 0.000675) * 1000.0
        self.assertAlmostEqual(result.deflection_mm, expected, places=3)


class TestColumnAnalysis(ARQGenTestCase):
    """Pilar: esbeltez, pandeo y utilización (spec 34)."""

    def test_column_concrete(self):
        from engines.structure_engine import column_analysis
        result = column_analysis(
            3.0, 400.0, e_gpa=21.0, area_m2=0.09, ix_m4=0.000675,
            radius_gyration_m=math.sqrt(0.000675 / 0.09), f_ck_mpa=25.0)
        self.assertAlmostEqual(result.slenderness, 34.6, places=1)
        self.assertAlmostEqual(result.euler_critical_kn, 15544.6, places=1)
        self.assertAlmostEqual(result.capacity_kn, 787.5, places=1)
        self.assertAlmostEqual(result.utilization, 400.0 / 787.5, places=3)
        self.assertTrue(result.ok)

    def test_column_buckling_governs_for_steel(self):
        from engines.structure_engine import column_analysis
        # Pilar esbelto de acero: Ncr/2.5 < aplastamiento.
        i = 5187.8e-6 * 0.3 ** 2 / 100.0  # inercia pequeña (aprox)
        result = column_analysis(
            6.0, 100.0, e_gpa=210.0, area_m2=5187.8e-6, ix_m4=i,
            radius_gyration_m=math.sqrt(i / 5187.8e-6), f_yield_mpa=275.0)
        self.assertIn("Gobierna el pandeo", result.notes[0])

    def test_column_overload(self):
        from engines.structure_engine import column_analysis
        result = column_analysis(
            3.0, 2000.0, e_gpa=21.0, area_m2=0.09, ix_m4=0.000675,
            radius_gyration_m=0.0866, f_ck_mpa=25.0)
        self.assertFalse(result.ok)
        self.assertGreater(result.utilization, 1.0)


class TestTrussSolver(ARQGenTestCase):
    """Cerchas por método de los nudos (spec 34)."""

    def test_triangle_truss_analytic(self):
        from engines.structure_engine import truss_solve
        result = truss_solve(
            nodes={"A": (0.0, 0.0), "B": (4.0, 0.0), "C": (2.0, 3.0)},
            members=[("AB", "A", "B"), ("AC", "A", "C"), ("BC", "B", "C")],
            supports={"A": ("PIN", "y"), "B": ("ROLLER", "y")},
            joint_loads={"C": (0.0, -10.0)})
        self.assertTrue(result.ok)
        # Cordón inferior en tracción: N = 10/2 · 2/3 = 3.333 kN
        state, force = result.member_forces["AB"]
        self.assertEqual(state, "T")
        self.assertAlmostEqual(force, 10.0 / 3.0, places=3)
        # Pendientes en compresión: N = 10/(2·sin θ) con tan θ = 3/2
        sin_theta = 3.0 / math.sqrt(13.0)
        state_c, force_c = result.member_forces["AC"]
        self.assertEqual(state_c, "C")
        self.assertAlmostEqual(force_c, 5.0 / sin_theta, places=3)
        # Reacciones verticales 5/5, horizontales nulas.
        self.assertAlmostEqual(result.reactions["A"][1], 5.0, places=6)
        self.assertAlmostEqual(result.reactions["B"][1], 5.0, places=6)
        self.assertAlmostEqual(result.reactions["A"][0], 0.0, places=6)

    def test_unstable_truss_reported(self):
        from engines.structure_engine import truss_solve
        # Dos nudos y dos barras paralelas: 2 incógnitas para 4 ecuaciones.
        result = truss_solve(
            nodes={"A": (0.0, 0.0), "B": (1.0, 0.0)},
            members=[("AB1", "A", "B"), ("AB2", "A", "B")],
            supports={"A": ("PIN", "y")},
            joint_loads={})
        self.assertFalse(result.ok)
        self.assertIn("inestable", result.reason)

    def test_truss_utilization(self):
        from engines.structure_engine import truss_utilization
        utilization = truss_utilization({"AB": ("T", 30.0)}, area_m2=0.001,
                                        f_allow_mpa=100.0)
        self.assertAlmostEqual(utilization["AB"], 0.3, places=6)


class TestConnections(ARQGenTestCase):
    """Uniones: pernos y soldadura (spec 33-34)."""

    def test_bolt_group_shear(self):
        from engines.structure_engine import bolt_group_shear_kn
        # 4 pernos M16 (A=201.06 mm2) con τ=100 MPa: 4·201.06·100/1000 = 80.4 kN
        capacity = bolt_group_shear_kn(4, 16.0)
        self.assertAlmostEqual(capacity, 4 * math.pi * 8 ** 2 * 100.0 / 1000.0,
                               places=2)

    def test_weld_capacity(self):
        from engines.structure_engine import weld_capacity_kn
        # 200 mm de cordón con garganta 5 mm y fw=160: 200·5·160/1000 = 160 kN
        self.assertAlmostEqual(weld_capacity_kn(200.0, 5.0), 160.0, places=3)

    def test_steel_weight(self):
        from engines.structure_engine import steel_weight_kg
        self.assertAlmostEqual(steel_weight_kg(42.2, 6.0), 253.2, places=6)


class TestStructureService(ARQGenTestCase):
    """Service CRUD + analysis + undo (spec 33-34, 76-77)."""

    def _build_frame(self, service):
        material = service.create_material("Acero S275", "STEEL", fy_mpa=275.0)
        section = service.create_section("IPE-300", "I_PROFILE", h_mm=300,
                                         b_mm=150, tw_mm=7.1, tf_mm=10.7)
        return material, section

    def test_crud_and_undo(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Estructura")
        service = StructureService(ctx)
        material, section = self._build_frame(service)
        element = service.create_element(
            "BEAM", "Viga portico", material_ref=material.code,
            section_ref=section.code, start=(0.0, 0.0), end=(6.0, 0.0),
            load_udl_kn_m=8.0)
        self.assertEqual(ctx.structure.count("ELEMENT", ctx.project.id), 1)
        self.assertAlmostEqual(element.length_m, 6.0, places=6)
        ctx.commit()
        ctx.command_bus.undo(ctx)
        self.assertEqual(ctx.structure.count("ELEMENT", ctx.project.id), 0)
        ctx.command_bus.redo(ctx)
        self.assertEqual(ctx.structure.count("ELEMENT", ctx.project.id), 1)
        ctx.close()

    def test_beam_analysis_stores_calculation(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Estructura")
        service = StructureService(ctx)
        material, section = self._build_frame(service)
        service.create_element("BEAM", "Viga portico", material_ref=material.code,
                               section_ref=section.code, start=(0.0, 0.0),
                               end=(6.0, 0.0), load_udl_kn_m=10.0)
        report = service.analyze_element("STR-ELEMENT-001")
        beam = report["beam"]
        self.assertAlmostEqual(beam["reaction_a_kn"], 30.0, places=2)
        self.assertAlmostEqual(beam["moment_max_knm"], 45.0, places=2)
        self.assertGreater(beam["deflection_mm"], 0.0)
        self.assertGreaterEqual(ctx.calculations_repo.count_fresh("STR"), 1)
        # The analysis results must land in element attrs for QTO/Clash.
        element = ctx.structure.get_by_code("ELEMENT", "STR-ELEMENT-001")
        self.assertAlmostEqual(element.num("moment_max_knm"), 45.0, places=2)
        ctx.close()

    def test_column_analysis_with_combination(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Estructura")
        service = StructureService(ctx)
        material, section = self._build_frame(service)
        service.create_element("COLUMN", "Pilar P1", material_ref=material.code,
                               section_ref=section.code, start=(0.0, 0.0),
                               end=(0.0, 0.0), z0=0.0, z1=3.0,
                               attrs={"axial_kn": 200.0})
        service.ensure_default_combinations()
        report = service.analyze_element("STR-ELEMENT-001",
                                         combination_ref="ULS-1")
        # ULS-1 = 1.35 + 1.5 = 2.85 → N = 200·2.85 = 570 kN
        self.assertAlmostEqual(report["column"]["axial_kn"], 570.0, places=2)
        ctx.close()

    def test_truss_service_analytic(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Cercha")
        service = StructureService(ctx)
        material, section = self._build_frame(service)
        service.create_element(
            "TRUSS", "Cercha cubierta", material_ref=material.code,
            section_ref=section.code, start=(0.0, 0.0), end=(4.0, 0.0),
            attrs={
                "nodes": [{"id": "A", "x": 0.0, "y": 0.0},
                          {"id": "B", "x": 4.0, "y": 0.0},
                          {"id": "C", "x": 2.0, "y": 3.0}],
                "members": [{"id": "AB", "a": "A", "b": "B"},
                            {"id": "AC", "a": "A", "b": "C"},
                            {"id": "BC", "a": "B", "b": "C"}],
                "supports": [{"node": "A", "kind": "PIN"},
                             {"node": "B", "kind": "ROLLER", "axis": "y"}],
                "joint_loads": [{"node": "C", "fx": 0.0, "fy": -10.0}],
            })
        report = service.analyze_truss("STR-ELEMENT-001")
        members = report["result"]["members"]
        self.assertAlmostEqual(members["AB"][1], 10.0 / 3.0, places=2)
        self.assertEqual(members["AB"][0], "T")
        self.assertIn("steel_weight_kg", report)
        self.assertIn("quantities", report)
        # Cantidades de cercha (spec 34): longitudes, peso, soldaduras, placas.
        quantities = report["quantities"]
        self.assertAlmostEqual(quantities["member_count"], 3.0)
        self.assertGreater(quantities["steel_weight_kg"], 0.0)
        self.assertEqual(quantities["gusset_plates"], 3.0)
        ctx.close()

    def test_utilization_report_and_steel_quantities(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Estructura")
        service = StructureService(ctx)
        material, section = self._build_frame(service)
        service.create_element("BEAM", "Viga 1", material_ref=material.code,
                               section_ref=section.code, start=(0.0, 0.0),
                               end=(6.0, 0.0), load_udl_kn_m=10.0)
        service.create_element("COLUMN", "Pilar 1", material_ref=material.code,
                               section_ref=section.code, start=(0.0, 0.0),
                               end=(0.0, 0.0), z0=0.0, z1=3.0,
                               attrs={"axial_kn": 300.0})
        service.analyze_element("STR-ELEMENT-001")
        service.analyze_element("STR-ELEMENT-002")
        report = service.utilization_report()
        self.assertEqual(report["count"], 2)
        steel = service.steel_quantities()
        # IPE-300 por área calculada: ≈ 41.5 kg/m → (6+3) m ≈ 374 kg
        self.assertGreater(steel["steel_weight_kg"], 350.0)
        self.assertLess(steel["steel_weight_kg"], 400.0)
        ctx.close()

    def test_connection_check(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Uniones")
        service = StructureService(ctx)
        result = service.check_connection(4, 16.0, 200.0, 5.0, 60.0)
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["bolt_capacity_kn"], 80.4, places=1)
        self.assertAlmostEqual(result["weld_capacity_kn"], 160.0, places=1)
        self.assertAlmostEqual(result["governing_kn"], 80.4, places=1)
        ctx.close()

    def test_delete_element(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="Estructura")
        service = StructureService(ctx)
        material, section = self._build_frame(service)
        service.create_element("BEAM", "Viga", material_ref=material.code,
                               section_ref=section.code)
        code = service.delete_element("STR-ELEMENT-001")
        self.assertEqual(code, "STR-ELEMENT-001")
        self.assertEqual(ctx.structure.count("ELEMENT", ctx.project.id), 0)
        ctx.close()


class TestStructureQTO(ARQGenTestCase):
    """QTO integration for structural elements (spec 51-52)."""

    def test_concrete_and_steel_formulas(self):
        from services.structure_service import StructureService
        from services.quantity_service import QuantityService
        ctx = self.application.create_project(self.project_path(), name="QTO STR")
        ctx.user = "tester"
        service = StructureService(ctx)
        concrete = service.create_material("Hormigón 25", "CONCRETE", fck_mpa=25.0)
        steel = service.create_material("Acero S275", "STEEL", fy_mpa=275.0)
        col_section = service.create_section("Pilar 30x30", "RECTANGLE",
                                             h_mm=300, b_mm=300)
        steel_section = service.create_section("IPE-300", "I_PROFILE", h_mm=300,
                                               b_mm=150, tw_mm=7.1, tf_mm=10.7)
        service.create_element("COLUMN", "Pilar", material_ref=concrete.code,
                               section_ref=col_section.code, start=(0.0, 0.0),
                               end=(0.0, 0.0), z0=0.0, z1=3.0)
        service.create_element("BEAM", "Viga acero", material_ref=steel.code,
                               section_ref=steel_section.code, start=(0.0, 0.0),
                               end=(6.0, 0.0))
        quantity = QuantityService(ctx)
        quantity.install_default_formulas()
        quantity.compute_all()
        totals = quantity.totals_by_formula()
        # Concreto: 3.0 m · 0.09 m2 = 0.27 m3
        self.assertAlmostEqual(totals["CONCRETE_VOLUME"], 0.27, places=4)
        # Encofrado: 3.0 m · 1.2 m = 3.6 m2
        self.assertAlmostEqual(totals["FORMWORK_AREA"], 3.6, places=4)
        # Acero: IPE-300 ≈ 41.5 kg/m · 6 m ≈ 249 kg
        self.assertGreater(totals["STEEL_WEIGHT"], 240.0)
        self.assertLess(totals["STEEL_WEIGHT"], 260.0)
        self.assertAlmostEqual(totals["ELEMENT_LENGTH"], 9.0, places=4)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
