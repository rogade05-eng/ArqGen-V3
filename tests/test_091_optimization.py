"""FASE 35 — Multiobjective optimization tests (spec 19, 73).

Expected values verified by hand:
    * Pareto front of A/B/C below: A dominates B; C trades off → front
      = [A, C] (A minimizes COST with same AREA; C has larger AREA)
    * dominates() respects per-objective directions (maximize/minimize)
    * demo project AREA = 80.0 m2 (4 locales), COMPLEXITY > 0
"""

from __future__ import annotations

import json
import os
import unittest

from tests.base import ARQGenTestCase

from core.errors import DomainError
from engines.optimization_engine import (
    DIRECTIONS, OBJECTIVES, Variant, compare_solutions, dominates,
    normalize_objectives, pareto_front,
)


def variant(name: str, **objectives: float) -> Variant:
    return Variant(name=name, objectives=dict(objectives))


class TestEngine(unittest.TestCase):
    def test_variant_validation(self):
        with self.assertRaises(DomainError) as ctx:
            Variant(name="", objectives={}).validate()
        self.assertEqual(ctx.exception.code, "ARQ-OPT-001")
        with self.assertRaises(DomainError) as ctx:
            Variant(name="X", objectives={"MAGIA": 1.0}).validate()
        self.assertEqual(ctx.exception.code, "ARQ-OPT-002")
        # Los 12 objetivos del spec 19 con dirección explícita
        self.assertEqual(len(OBJECTIVES), 12)
        for obj in OBJECTIVES:
            self.assertIn(DIRECTIONS[obj], ("minimize", "maximize"))

    def test_dominates_minimize(self):
        a = variant("A", COST=100.0, MATERIAL=5.0)
        b = variant("B", COST=120.0, MATERIAL=5.0)
        self.assertTrue(dominates(a, b))   # A mejor en COST, igual en MATERIAL
        self.assertFalse(dominates(b, a))

    def test_dominates_maximize(self):
        a = variant("A", LIGHTING=0.2)
        b = variant("B", LIGHTING=0.1)
        self.assertTrue(dominates(a, b))   # mayor iluminación es mejor
        self.assertFalse(dominates(b, a))

    def test_no_dominance_with_tradeoff(self):
        a = variant("A", COST=100.0, AREA=50.0)
        b = variant("B", COST=90.0, AREA=40.0)
        self.assertFalse(dominates(a, b))
        self.assertFalse(dominates(b, a))

    def test_pareto_front_known(self):
        a = variant("A", COST=100.0, AREA=50.0)
        b = variant("B", COST=120.0, AREA=50.0)   # dominada por A
        c = variant("C", COST=140.0, AREA=80.0)   # compromiso → frente
        d = variant("D", COST=150.0, AREA=40.0)   # dominada por A y B
        self.assertEqual(pareto_front([a, b, c, d]), ["A", "C"])

    def test_compare_solutions(self):
        a = variant("A", COST=100.0, AREA=50.0)
        b = variant("B", COST=110.0, AREA=60.0)
        result = compare_solutions(a, b)
        self.assertAlmostEqual(result["COST"]["delta"], 10.0)
        self.assertAlmostEqual(result["AREA"]["delta"], 10.0)
        self.assertEqual(result["COST"]["direction"], "minimize")
        self.assertEqual(result["AREA"]["direction"], "maximize")

    def test_normalize(self):
        stats = normalize_objectives([
            variant("A", COST=100.0), variant("B", COST=200.0)])
        self.assertEqual(stats["COST"], {"min": 100.0, "max": 200.0})


class TestOptimizationService(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_evaluate_current_known_values(self):
        from services.optimization_service import OptimizationService
        current = OptimizationService(self.ctx).evaluate_current()
        # 4 locales de la demo: 20+20+20+20 = 80 m2
        self.assertAlmostEqual(current.objectives["AREA"], 80.0, places=2)
        # Presupuesto determinista de la demo
        self.assertAlmostEqual(current.objectives["COST"], 1295093.90, places=1)
        # Objetivos derivados positivos
        self.assertGreater(current.objectives["COMPLEXITY"], 0.0)
        self.assertGreater(current.objectives["MATERIAL"], 0.0)
        self.assertGreater(current.objectives["SECURITY"], 0.0)
        self.assertEqual(current.objectives["MAINTENANCE"], 1.0)  # 12 redes válidas
        self.assertAlmostEqual(current.objectives["LIGHTING"], 0.0485, places=3)
        # Los 12 objetivos presentes
        self.assertEqual(set(current.objectives), set(OBJECTIVES))

    def test_distance_and_privacy_from_relationships(self):
        from services.architecture_service import ArchitectureService
        from services.optimization_service import OptimizationService
        architecture = ArchitectureService(self.ctx)
        spaces = self.ctx.architecture.list("SPACE", self.ctx.project.id)
        architecture.add_relationship(spaces[0].code, spaces[1].code,
                                      "acoustically_separated_from")
        current = OptimizationService(self.ctx).evaluate_current()
        self.assertEqual(current.objectives["PRIVACY"], 1.0)

    def test_pareto_with_current(self):
        from services.optimization_service import OptimizationService
        service = OptimizationService(self.ctx)
        current = service.evaluate_current()
        worse = Variant(name="PEOR",
                        objectives={**current.objectives,
                                    "COST": current.objectives["COST"] + 1})
        report = service.pareto([current, worse])
        self.assertEqual(report["pareto_front"], ["CURRENT"])
        self.assertEqual(report["dominated_by"], {"PEOR": "CURRENT"})
        # Direcciones incluidas en el informe
        self.assertEqual(report["objectives"]["COST"], "minimize")

    def test_load_variants_and_compare(self):
        from services.optimization_service import OptimizationService
        service = OptimizationService(self.ctx)
        path = os.path.join(self.tmp, "variants.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"variants": [
                {"name": "A", "objectives": {"COST": 100.0, "AREA": 50.0}},
                {"name": "B", "objectives": {"COST": 120.0, "AREA": 60.0}},
            ]}, handle)
        variants = service.load_variants(path)
        self.assertEqual([v.name for v in variants], ["A", "B"])
        with_current = service.load_variants(path, with_current=True)
        self.assertEqual(len(with_current), 3)
        report = service.compare(variants[0], variants[1])
        self.assertFalse(report["a_dominates_b"])   # B gana en AREA
        self.assertFalse(report["b_dominates_a"])   # A gana en COST
        with self.assertRaises(DomainError):
            service.pareto([])


if __name__ == "__main__":
    unittest.main()
