"""Certificación del catálogo PRECONS III oficial (RoPres 3.30).

El catálogo embebido (resources/rulesets/precons_iii_rospres_330.json)
fue certificado 1:1 contra el XLSX oficial del repositorio de origen
(rogade05-eng/ArqGen-V2, Catalogo_PRECONS_III_Completo.xlsx): 15981
renglones y 4383 recursos (3569 materiales, 671 equipos, 143 mano de
obra) dict a dict, además de 38 secciones, 8 parámetros y 4 límites.
Estas pruebas fijan esa línea base para detectar cualquier corrupción
o actualización no controlada del recurso empaquetado.
"""

from __future__ import annotations

import os
import re
import unittest
from io import StringIO
from unittest.mock import patch

from services.precons_service import CATALOG_BASELINE, certificar_catalogo
from tests.base import ARQGenTestCase


class TestCertificacionCatalogo(ARQGenTestCase):
    """Integridad del catálogo embebido (sin proyecto)."""

    def setUp(self):
        super().setUp()
        self.report = certificar_catalogo("precons_iii_rospres_330")

    def test_reporte_ok(self):
        self.assertTrue(self.report["ok"], self.report["failures"])
        self.assertEqual(self.report["failures"], [])

    def test_recuentos_linea_base(self):
        self.assertEqual(self.report["counts"], CATALOG_BASELINE)
        self.assertEqual(self.report["counts"]["work_items"], 15981)
        self.assertEqual(self.report["counts"]["resources"], 4383)
        self.assertEqual(self.report["counts"]["materials"], 3569)
        self.assertEqual(self.report["counts"]["equipment"], 671)
        self.assertEqual(self.report["counts"]["labor"], 143)
        self.assertEqual(self.report["counts"]["sections"], 38)

    def test_version_y_sha256(self):
        self.assertEqual(self.report["version"], "3.30")
        sha = self.report["sha256"]
        self.assertRegex(sha, r"^[0-9a-f]{64}$")
        # estable entre llamadas (fichero inmutable en tiempo de ejecución)
        again = certificar_catalogo("precons_iii_rospres_330")
        self.assertEqual(again["sha256"], sha)
        self.assertEqual(again["bytes"], self.report["bytes"])
        self.assertGreater(self.report["bytes"], 8_000_000)

    def test_precios_oficiales_de_referencia(self):
        """Valores tomados del XLSX oficial certificado 1:1."""
        from app.paths import resource_path
        from engines.precons_engine import PreconsRuleset
        ruleset = PreconsRuleset.from_file(
            resource_path("rulesets", "precons_iii_rospres_330.json"))
        item = ruleset.official_price("011111")  # MANIGUA MANUAL
        self.assertAlmostEqual(item["total"], 26.81, places=2)
        self.assertAlmostEqual(item["material"], 26.81, places=2)
        item2 = ruleset.official_price("011121")  # MANIGUA TUPIDA MECANIZADA
        self.assertAlmostEqual(item2["total"], 62.57, places=2)
        self.assertEqual(item["currency"], "CUP")
        self.assertEqual(item["unit"], "m2")
        resource = next(r for r in ruleset.resources
                        if r["code"] == "0051110001")
        self.assertEqual(resource["kind"], "MATERIAL")
        self.assertAlmostEqual(resource["price_ref"], 0.25, places=2)

    def test_desglose_consistente_muestra(self):
        """price_ref = materiales + MO + equipos en la primera centena."""
        from app.paths import resource_path
        import json
        with open(resource_path("rulesets", "precons_iii_rospres_330.json"),
                  encoding="utf-8") as handle:
            data = json.load(handle)
        for w in data["work_items"][:100]:
            total = (w["price_material"] + w["price_labor"]
                     + w["price_equipment"])
            self.assertAlmostEqual(total, w["price_ref"], delta=0.011)

    def test_catalogo_inexistente_falla_sin_excepcion(self):
        report = certificar_catalogo("no_existe_v9")
        self.assertFalse(report["ok"])
        self.assertTrue(report["failures"])


class TestCertificacionTamper(ARQGenTestCase):
    """Un catálogo alterado debe detectarse."""

    def test_precio_alterado_detectado(self):
        import json
        from app import paths as app_paths
        src = app_paths.resource_path(
            "rulesets", "precons_iii_rospres_330.json")
        with open(src, encoding="utf-8") as handle:
            data = json.load(handle)
        data["work_items"][0]["price_ref"] = 999.0  # rompe el desglose
        tampered = os.path.join(self.tmp, "precons_tamper.json")
        with open(tampered, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        original = app_paths.resource_path

        def fake_resource_path(*parts):
            if parts[-1] == "precons_tamper.json":
                return tampered
            return original(*parts)

        with patch("app.paths.resource_path", fake_resource_path):
            report = certificar_catalogo("precons_tamper")
        self.assertFalse(report["ok"])
        self.assertTrue(any("desglose" in f for f in report["failures"]),
                        report["failures"])
        self.assertNotEqual(report["sha256"],
                            certificar_catalogo()["sha256"])

    def test_renglones_eliminados_detectados(self):
        import json
        from app import paths as app_paths
        src = app_paths.resource_path(
            "rulesets", "precons_iii_rospres_330.json")
        with open(src, encoding="utf-8") as handle:
            data = json.load(handle)
        del data["work_items"][0]  # 15981 -> 15980
        tampered = os.path.join(self.tmp, "precons_short.json")
        with open(tampered, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        original = app_paths.resource_path

        def fake_resource_path(*parts):
            if parts[-1] == "precons_short.json":
                return tampered
            return original(*parts)

        with patch("app.paths.resource_path", fake_resource_path):
            report = certificar_catalogo("precons_short")
        self.assertFalse(report["ok"])
        self.assertTrue(any("work_items" in f for f in report["failures"]),
                        report["failures"])


class TestCLICertificar(ARQGenTestCase):
    """El comando CLI no requiere proyecto y certifica en verde."""

    def test_cli_certificar_ok(self):
        from app.cli import run
        log_dir = os.path.join(self.tmp, "logs")
        with patch("sys.stdout", new=StringIO()) as out:
            code = run(["--log-dir", log_dir, "precons", "certificar"])
        self.assertEqual(code, 0, out.getvalue())
        text = out.getvalue()
        self.assertIn("CERTIFICADO", text)
        self.assertIn("15981", text)
        self.assertIn("4383", text)
        self.assertIn("3.30", text)
        self.assertRegex(text, r"sha256 [0-9a-f]{16}")

    def test_cli_certificar_falla_si_alterado(self):
        import json
        from app import paths as app_paths
        from app.cli import run
        src = app_paths.resource_path(
            "rulesets", "precons_iii_rospres_330.json")
        with open(src, encoding="utf-8") as handle:
            data = json.load(handle)
        data["resources"] = data["resources"][:-1]  # 4383 -> 4382
        tampered = os.path.join(self.tmp, "precons_cli.json")
        with open(tampered, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        original = app_paths.resource_path

        def fake_resource_path(*parts):
            if parts[-1] == "precons_cli.json":
                return tampered
            return original(*parts)

        log_dir = os.path.join(self.tmp, "logs")
        with patch("app.paths.resource_path", fake_resource_path), \
                patch("sys.stdout", new=StringIO()) as out:
            code = run(["--log-dir", log_dir, "precons", "certificar",
                        "--ruleset", "precons_cli"])
        self.assertEqual(code, 1)
        self.assertIn("ERRORES", out.getvalue())
        self.assertIn("resources", out.getvalue())


if __name__ == "__main__":
    unittest.main()
