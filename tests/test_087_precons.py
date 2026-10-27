"""PRECONS engine/service and SIECONS-like engine tests (spec 59, 60)."""

from __future__ import annotations

from core.errors import DomainError
from tests.base import ARQGenTestCase

RULESET_CODE = "precons_cuba_v1"


def _ruleset():
    from app.paths import resource_path
    from engines.precons_engine import PreconsRuleset
    return PreconsRuleset.from_file(
        resource_path("rulesets", f"{RULESET_CODE}.json"))


def _prices():
    """Lista de precios fija y verificable a mano (CUP)."""
    return {
        "BLOQUE-20": 32.50, "CEMENTO": 185.0, "ARENA": 95.0, "PIEDRA": 120.0,
        "ACERO-CA": 28.0, "MO-ALBANIL": 450.0, "MO-AYUDANTE": 300.0,
        "MO-HORMIGONERO": 500.0, "HORMIGONERA": 900.0, "TRANSPORTE": 150.0,
    }


class TestPreconsRuleset(ARQGenTestCase):
    """Ruleset versionado (spec 59)."""

    def test_load_versioned_ruleset(self):
        ruleset = _ruleset()
        self.assertEqual(ruleset.code, RULESET_CODE)
        self.assertTrue(ruleset.work_items)
        self.assertTrue(ruleset.resources)
        self.assertIn("indirect_pct", ruleset.coefficients)
        # El ruleset es datos, no código: tiene versión explícita.
        self.assertTrue(ruleset.version)

    def test_unknown_item_rejected(self):
        ruleset = _ruleset()
        with self.assertRaises(DomainError):
            ruleset.item("NO-EXISTE")


class TestTakeoff(ARQGenTestCase):
    """Renglones e indicadores (rendimientos, spec 60)."""

    def test_masonry_takeoff(self):
        from engines.precons_engine import takeoff
        ruleset = _ruleset()
        lines = takeoff(ruleset, "E-01", 10.0)
        by_resource = {line["resource"]: line["quantity"] for line in lines}
        # 10 m3 × 72 bloque/m3 × 1.05 desperdicio = 756 bloques
        self.assertAlmostEqual(by_resource["BLOQUE-20"], 756.0, places=2)
        # 10 × 18 × 1.03 = 185.4 sacos
        self.assertAlmostEqual(by_resource["CEMENTO"], 185.4, places=2)
        # 10 × 1.6 jornadas = 16.0 albañiles
        self.assertAlmostEqual(by_resource["MO-ALBANIL"], 16.0, places=2)

    def test_takeoff_rejects_negative(self):
        from core.errors import CalculationError
        from engines.precons_engine import takeoff
        with self.assertRaises(CalculationError):
            takeoff(_ruleset(), "E-01", -1.0)


class TestPriceAnalysis(ARQGenTestCase):
    """Análisis de precio con coeficientes e indirectos (spec 59-60)."""

    def test_masonry_unit_price(self):
        from engines.precons_engine import price_analysis
        analysis = price_analysis(_ruleset(), "E-01", 10.0, _prices())
        # Directo a mano:
        #   bloques  756.0 × 32.50 = 24570.00
        #   cemento  185.4 × 185.0 = 34299.00
        #   arena    10×0.09×1.05 = 0.945 m3 × 95 = 89.775
        #   albañil  16.0 × 450 = 7200.00
        #   ayudante 16.0 × 300 = 4800.00
        direct = 24570.0 + 34299.0 + 89.775 + 7200.0 + 4800.0
        # Transporte = 2.5 % del directo de materiales (58 958.775).
        materials = 24570.0 + 34299.0 + 89.775
        transport = materials * 0.025
        self.assertAlmostEqual(analysis.direct_transport, transport, places=2)
        # El costo directo incluye el coeficiente de transporte.
        self.assertAlmostEqual(analysis.direct_cost, direct + transport, places=2)
        self.assertAlmostEqual(analysis.indirect_cost,
                               (direct + transport) * 0.18, places=2)
        self.assertAlmostEqual(analysis.benefit, (direct + transport) * 0.08,
                               places=2)
        total = (direct + transport) * 1.26
        self.assertAlmostEqual(analysis.total_price, total, places=2)
        self.assertAlmostEqual(analysis.unit_price, total / 10.0, places=2)

    def test_missing_prices_rejected(self):
        from core.errors import CalculationError
        from engines.precons_engine import price_analysis
        with self.assertRaises(CalculationError):
            price_analysis(_ruleset(), "E-01", 10.0, {"BLOQUE-20": 32.5})

    def test_variant_multiplier(self):
        from engines.precons_engine import price_analysis
        ruleset = _ruleset()
        base = price_analysis(ruleset, "E-01", 10.0, _prices(), "BASE")
        economic = price_analysis(ruleset, "E-01", 10.0, _prices(), "ECONOMIC")
        # ECONOMIC multiplica renglones × 0.9 → total × 0.9.
        self.assertAlmostEqual(economic.total_price,
                               base.total_price * 0.9, places=2)

    def test_compare_and_update(self):
        from engines.precons_engine import (
            compare_analyses, price_analysis, update_analysis,
        )
        ruleset = _ruleset()
        base = price_analysis(ruleset, "E-01", 10.0, _prices())
        premium = price_analysis(ruleset, "E-01", 10.0, _prices(), "PREMIUM")
        comparison = compare_analyses([base, premium])
        self.assertEqual(len(comparison["rows"]), 2)
        # Actualización: los precios suben 10 % → total sube (aprox) 10 %.
        updated_prices = {k: v * 1.10 for k, v in _prices().items()}
        updated = update_analysis(ruleset, base, updated_prices)
        self.assertGreater(updated.total_price, base.total_price)
        self.assertAlmostEqual(updated.total_price / base.total_price, 1.10,
                               places=2)


class TestPreconsImporter(ARQGenTestCase):
    """Importador/mapeador con estructura externa no asumida (spec 60)."""

    def test_import_with_column_mapping(self):
        from engines.precons_engine import import_external, takeoff
        external = {
            "partidas": [
                {"codigo": "P-1", "descripcion": "Muro de bloque",
                 "um": "m3",
                 "rendimientos": [
                     {"insumo": "BLOQ", "cantidad": "72.0", "desperdicio": "5"},
                     {"insumo": "MO", "cantidad": 1.6},
                 ]},
            ],
            "recursos": [
                {"insumo": "BLOQ", "desc": "Bloque", "tipo": "MATERIAL", "um": "und"},
                {"insumo": "MO", "desc": "Albañil", "tipo": "LABOR", "um": "jornada"},
            ],
            "coeficientes": {"indirect_pct": 20.0},
        }
        mapping = {
            "work_items": "partidas", "resources": "recursos",
            "coefficients": "coeficientes",
            "code": "codigo", "name": "descripcion", "unit": "um",
            "indicators": "rendimientos", "resource": "insumo",
            "yield": "cantidad", "waste_pct": "desperdicio",
            "kind": "tipo",
        }
        ruleset = import_external(external, mapping, code="externa")
        self.assertEqual(ruleset.code, "externa")
        self.assertEqual(len(ruleset.work_items), 1)
        self.assertEqual(len(ruleset.resources), 2)
        self.assertEqual(ruleset.coefficients["indirect_pct"], 20.0)
        # El yield venía como texto "72.0": el mapeador lo normaliza.
        lines = takeoff(ruleset, "P-1", 1.0)
        self.assertAlmostEqual(lines[0]["quantity"], 75.6, places=2)

    def test_import_requires_mapping(self):
        from engines.precons_engine import import_external
        with self.assertRaises(DomainError):
            import_external({"x": []}, {})


class TestPreconsService(ARQGenTestCase):
    """Servicio PRECONS integrado con QTO y precios (spec 59-60)."""

    def test_analyze_item_stores_pre(self):
        from services.budget_service import PricingService
        from services.precons_service import PreconsService
        ctx = self.application.create_project(self.project_path(), name="PRE")
        ctx.user = "tester"
        pricing = PricingService(ctx)
        pricing.ensure_price_list("GENERAL", name="General", currency="CUP")
        for code, price in _prices().items():
            resource = _ruleset().resource(code)
            pricing.add_resource(code, resource["name"], resource["kind"],
                                 resource["unit"])
            pricing.set_price(code, price, "GENERAL", date_iso="2026-01-01")
        service = PreconsService(ctx)
        service.load_ruleset(RULESET_CODE)
        analysis = service.analyze_item("E-01", 10.0)
        self.assertAlmostEqual(analysis.unit_price,
                               analysis.total_price / 10.0, places=2)
        self.assertGreaterEqual(ctx.calculations_repo.count_fresh("PRE"), 1)
        ctx.close()

    def test_analyze_project_via_qto(self):
        from services.precons_service import PreconsService
        ctx = self.demo_context()
        ctx.user = "tester"
        service = PreconsService(ctx)
        service.load_ruleset(RULESET_CODE)
        report = service.analyze_project()
        self.assertEqual(report["ruleset"], RULESET_CODE)
        self.assertGreater(report["total"], 0.0)
        self.assertTrue(report["analyses"])
        for analysis in report["analyses"]:
            self.assertGreater(analysis["quantity"], 0.0)
        ctx.close()

    def test_compare_variants(self):
        from services.precons_service import PreconsService
        ctx = self.demo_context()
        ctx.user = "tester"
        service = PreconsService(ctx)
        service.load_ruleset(RULESET_CODE)
        comparison = service.compare_variants("E-01", 10.0,
                                              prices=_prices())
        self.assertEqual(len(comparison["rows"]), 3)
        prices = comparison["unit_prices_by_variant"]["E-01"]
        self.assertGreater(prices["PREMIUM"], prices["BASE"])
        self.assertLess(prices["ECONOMIC"], prices["BASE"])
        ctx.close()

    def test_requires_ruleset(self):
        from services.precons_service import PreconsService
        ctx = self.application.create_project(self.project_path(), name="PRE2")
        service = PreconsService(ctx)
        with self.assertRaises(DomainError):
            service.analyze_item("E-01", 1.0)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
