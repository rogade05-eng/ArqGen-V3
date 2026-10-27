"""Motor PRECONS con precio oficial directo (v2.0.0, catálogo real).

El catálogo PRECONS III real (RoPres 3.30) trae 15981 renglones con
desglose oficial CUP y sin indicadores de composición: el análisis
debe resolverlo sin lista de precios de recursos y cumpliendo
total = unit_price × quantity siempre.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

REAL_CODE = "precons_iii_rospres_330"


def _real_ruleset():
    from app.paths import resource_path
    from engines.precons_engine import PreconsRuleset
    return PreconsRuleset.from_file(
        resource_path("rulesets", f"{REAL_CODE}.json"))


class TestOfficialMode(ARQGenTestCase):
    """Análisis de precio por desglose oficial (sin composición)."""

    def test_direct_analysis_uses_official_prices(self):
        from engines.precons_engine import price_analysis
        ruleset = _real_ruleset()
        analysis = price_analysis(ruleset, "011111", 100.0, {})
        self.assertEqual(analysis.mode, "official")
        self.assertAlmostEqual(analysis.unit_price, 26.81, places=2)
        self.assertAlmostEqual(analysis.total_price, 2681.0, places=2)
        self.assertAlmostEqual(analysis.direct_material, 2681.0, places=2)
        self.assertAlmostEqual(analysis.direct_labor, 0.0, places=2)

    def test_labor_and_equipment_breakdown(self):
        from engines.precons_engine import price_analysis
        ruleset = _real_ruleset()
        # 011112 MANIGUA LIGERA MECANIZADA: 0.66 mat + 13.76 mo = 14.42
        analysis = price_analysis(ruleset, "011112", 10.0, {})
        self.assertAlmostEqual(analysis.direct_material, 6.6, places=2)
        self.assertAlmostEqual(analysis.direct_labor, 137.6, places=2)
        self.assertAlmostEqual(analysis.direct_equipment, 0.0, places=2)
        self.assertAlmostEqual(analysis.direct_cost, 144.2, places=2)

    def test_total_equals_unit_price_times_quantity(self):
        from engines.precons_engine import price_analysis
        ruleset = _real_ruleset()
        for code, qty in (("011111", 37.5), ("020112", 3.0),
                          ("011112", 123.45)):
            analysis = price_analysis(ruleset, code, qty, {})
            self.assertAlmostEqual(analysis.total_price,
                                   analysis.unit_price * qty, places=2)

    def test_empty_catalog_prices_rejected(self):
        from core.errors import CalculationError
        from engines.precons_engine import price_analysis
        ruleset = _real_ruleset()
        with self.assertRaises(CalculationError):
            price_analysis(ruleset, "011111", -1.0, {})

    def test_service_analyze_without_price_list(self):
        """analyze_item del servicio funciona sin lista de precios."""
        from services.precons_service import PreconsService
        context = self.application.create_project(
            self.project_path("pre.arqgen"), "Proyecto PRECONS")
        service = PreconsService(context)
        service.load_ruleset(REAL_CODE)
        analysis = service.analyze_item("011111", 50.0)
        self.assertEqual(analysis.mode, "official")
        self.assertAlmostEqual(analysis.total_price, 1340.5, places=2)

    def test_composition_mode_still_works(self):
        """El ruleset demo (con indicadores) sigue calculando igual."""
        from engines.precons_engine import price_analysis
        ruleset = _real_ruleset()
        demo = _ruleset_stub()
        analysis = price_analysis(demo, "E-01", 10.0, _stub_prices())
        self.assertEqual(analysis.mode, "composition")
        self.assertTrue(analysis.lines)
        self.assertGreater(analysis.direct_cost, 0.0)

    def test_search_and_sections_real_catalog(self):
        ruleset = _real_ruleset()
        self.assertEqual(len(ruleset.work_items), 15981)
        sections = ruleset.sections()
        self.assertEqual(len(sections), 38)
        hits = ruleset.search("hormigon", limit=5)
        self.assertTrue(hits)

    def test_is_official_item_helper(self):
        from engines.precons_engine import is_official_item
        real = _real_ruleset()
        self.assertTrue(is_official_item(real.item("011111")))
        stub = _ruleset_stub()
        self.assertFalse(is_official_item(stub.item("E-01")))


def _ruleset_stub():
    from app.paths import resource_path
    from engines.precons_engine import PreconsRuleset
    return PreconsRuleset.from_file(
        resource_path("rulesets", "precons_cuba_v1.json"))


def _stub_prices():
    return {
        "BLOQUE-20": 32.50, "CEMENTO": 185.0, "ARENA": 95.0,
        "PIEDRA": 120.0, "ACERO-CA": 28.0, "MO-ALBANIL": 450.0,
        "MO-AYUDANTE": 300.0, "MO-HORMIGONERO": 500.0,
        "HORMIGONERA": 900.0, "TRANSPORTE": 150.0,
    }


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
