"""FASES 39-40 — Plugin system hardening and performance benchmark
(spec 88-89, 86-87).

Expected values verified by hand:
    * scaffold plugin validates OK (contract complete)
    * a file without ARQGenPlugin subclass → validation error
    * cache inventory includes the six caches of spec 87
    * benchmark produces the 8 standard operations with positive times
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase

from core.errors import PluginError
from plugins.plugin_api import (
    scaffold_plugin, validate_plugin_file,
)


class TestPlugins(ARQGenTestCase):
    def test_scaffold_then_validate_ok(self):
        path = os.path.join(self.tmp, "my_plugin.py")
        self.assertEqual(scaffold_plugin(path), path)
        result = validate_plugin_file(path)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["plugin_id"], "my_plugin")
        self.assertEqual(result["errors"], [])
        # Regenerar sobre el mismo destino → error de contrato
        with self.assertRaises(PluginError):
            scaffold_plugin(path)

    def test_validate_missing_and_non_plugin(self):
        result = validate_plugin_file(os.path.join(self.tmp, "nope.py"))
        self.assertFalse(result["ok"])
        self.assertIn("El archivo no existe", result["errors"])
        plain = os.path.join(self.tmp, "plain.py")
        with open(plain, "w", encoding="utf-8") as handle:
            handle.write("VALUE = 42\n")
        result = validate_plugin_file(plain)
        self.assertFalse(result["ok"])
        self.assertTrue(any("ARQGenPlugin" in e for e in result["errors"]))

    def test_validate_bad_declarations(self):
        broken = os.path.join(self.tmp, "broken.py")
        with open(broken, "w", encoding="utf-8") as handle:
            handle.write(
                "from plugins.plugin_api import ARQGenPlugin\n"
                "class P(ARQGenPlugin):\n"
                "    plugin_id = 'roto'\n"
                "    entities = 'no_soy_lista'\n")
        result = validate_plugin_file(broken)
        self.assertFalse(result["ok"])
        self.assertTrue(any("entities" in e for e in result["errors"]))

    def test_api_version_warning(self):
        mismatched = os.path.join(self.tmp, "api.py")
        with open(mismatched, "w", encoding="utf-8") as handle:
            handle.write(
                "from plugins.plugin_api import ARQGenPlugin\n"
                "class P(ARQGenPlugin):\n"
                "    plugin_id = 'viejo'\n"
                "    api_version = '0.0.1'\n")
        result = validate_plugin_file(mismatched)
        self.assertTrue(result["ok"])   # aviso, no error
        self.assertTrue(any("api_version" in w for w in result["warnings"]))

    def test_loader_info_lists_builtins(self):
        from app.bootstrap import bootstrap
        _, loader = bootstrap(type("Args", (), {"log_dir": self.tmp})())
        infos = loader.info()
        plugin_ids = {i["plugin_id"] for i in infos if i["status"] == "LOADED"}
        # Los módulos integrados se cargan como plugins (spec 88)
        self.assertTrue({"architecture", "installations"} <= plugin_ids)
        for info in infos:
            self.assertIn("source", info)


class TestBenchmark(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_run_benchmarks_standard_ops(self):
        from app.benchmark import run_benchmarks
        results = run_benchmarks(self.ctx, iterations={
            "geometry_area": 5, "spatial_adjacency": 2, "qto_compute_all": 1,
            "budget_compute": 1, "optimization_current": 1,
            "documentation_memoria": 1, "clash_detection": 1, "export_json": 1,
        })
        names = [r.name for r in results]
        self.assertEqual(names, [
            "geometry_area", "spatial_adjacency", "qto_compute_all",
            "budget_compute", "optimization_current",
            "documentation_memoria", "clash_detection", "export_json",
        ])
        for r in results:
            self.assertGreaterEqual(r.seconds, 0.0)
            self.assertGreater(r.iterations, 0)

    def test_format_results_deterministic(self):
        from app.benchmark import BenchResult, format_results
        rows = [BenchResult("op_a", 0.5, 10), BenchResult("op_b", 0.2, 10)]
        table = format_results(rows)
        self.assertIn("op_a", table)
        self.assertIn("op_b", table)
        self.assertIn("Ops/s", table)
        # ops/s = iteraciones / segundos, verificado a mano
        self.assertIn("20.0", table)  # 10 / 0.5

    def test_cache_inventory_spec87(self):
        from app.benchmark import cache_inventory
        caches = {c["cache"] for c in cache_inventory()}
        # Las seis cachés exigidas por el spec 87
        for required in ("geometry_cache", "rules_cache", "catalog_cache",
                         "calculation_cache", "routing_cache",
                         "coverage_cache"):
            self.assertIn(required, caches)
        for row in cache_inventory():
            self.assertIn("invalidation", row)
            self.assertTrue(row["invalidation"])


if __name__ == "__main__":
    unittest.main()
