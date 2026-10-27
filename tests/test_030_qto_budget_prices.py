"""TEST-016/017/018 QTO, Budget, Prices with deterministic numbers (spec 51-62)."""

from __future__ import annotations

import unittest

from core.errors import CalculationError, DomainError
from tests.base import ARQGenTestCase


class TestQTO(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.project_path()
        self.ctx = self.application.create_project(self.path, name="QTO")
        self.ctx.user = "tester"

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_wall_quantities_exact(self):
        from services.architecture_service import ArchitectureService
        from services.quantity_service import QuantityService
        service = ArchitectureService(self.ctx)
        service.create_level("N1", 0.0, 3.0)
        wall = service.create_wall("N1", (0, 0), (5, 0), thickness_m=0.2)
        service.create_opening("DOOR", wall.code, 0.9, 2.1)  # 1.89 m2
        quantity = QuantityService(self.ctx)
        quantity.install_default_formulas()
        stats = quantity.compute_all()
        self.assertEqual(stats.objects_processed, 2)  # 1 wall + 1 door
        rows = {q["formula_code"]: q["final_quantity"]
                for q in quantity.quantities() if q["object_id"] == wall.id}
        self.assertAlmostEqual(rows["WALL_LENGTH"], 5.0, places=6)
        self.assertAlmostEqual(rows["WALL_AREA_GROSS"], 15.0, places=6)
        self.assertAlmostEqual(rows["WALL_AREA_NET"], 13.11, places=6)
        self.assertAlmostEqual(rows["WALL_VOLUME"], 2.622, places=6)

    def test_space_quantities(self):
        from services.architecture_service import ArchitectureService
        from services.quantity_service import QuantityService
        service = ArchitectureService(self.ctx)
        service.create_level("N1", 0.0, 3.0)
        service.create_space("N1", "Sala", "LIVING_ROOM",
                             [(0, 0), (4, 0), (4, 3), (0, 3)])
        quantity = QuantityService(self.ctx)
        quantity.install_default_formulas()
        quantity.compute_all()
        totals = QuantityService(self.ctx).totals_by_formula()
        self.assertAlmostEqual(totals["SPACE_AREA"], 12.0, places=6)
        self.assertAlmostEqual(totals["SPACE_VOLUME"], 36.0, places=6)


class TestPrices(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.application.create_project(self.project_path(), name="Prices")
        self.ctx.user = "tester"
        from services.budget_service import PricingService
        self.pricing = PricingService(self.ctx)
        self.pricing.add_resource("CEMENTO", "Cemento", "MATERIAL", "saco")
        self.pricing.ensure_price_list("GENERAL", name="General")

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_price_history_never_overwritten(self):
        self.pricing.set_price("CEMENTO", 100.0, "GENERAL", date_iso="2026-01-01")
        self.pricing.set_price("CEMENTO", 150.0, "GENERAL", date_iso="2026-03-01")
        p_jan = self.pricing.current_price("CEMENTO", "GENERAL", date_iso="2026-02-01")
        p_mar = self.pricing.current_price("CEMENTO", "GENERAL", date_iso="2026-04-01")
        self.assertEqual(p_jan, 100.0)
        self.assertEqual(p_mar, 150.0)
        history = self.pricing.price_history("CEMENTO", "GENERAL")
        self.assertEqual(len(history), 2)  # both rows preserved (spec 61)

    def test_unknown_price_raises_with_guidance(self):
        with self.assertRaises(CalculationError):
            self.pricing.current_price("CEMENTO", "GENERAL", date_iso="2025-01-01")

    def test_invalid_resource_type_rejected(self):
        with self.assertRaises(DomainError):
            self.pricing.add_resource("X", "X", "MAGIA", "und")

    def test_duplicate_resource_code_rejected(self):
        with self.assertRaises(DomainError):
            self.pricing.add_resource("CEMENTO", "Otro", "MATERIAL", "saco")


class TestBudget(ARQGenTestCase):
    def test_budget_math_exact(self):
        ctx = self.demo_context()
        ctx.user = "tester"
        from services.budget_service import BudgetService
        result = BudgetService(ctx).compute_budget("residential_v1")
        # Deterministic: recompute and compare
        result2 = BudgetService(ctx).compute_budget("residential_v1")
        self.assertAlmostEqual(result.direct_cost, result2.direct_cost, places=2)
        self.assertAlmostEqual(result.total,
                               result.direct_cost * (1 + 18 / 100 + 3 / 100), places=2)
        self.assertGreater(result.direct_cost, 0)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
