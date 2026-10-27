"""CLI integration tests: end-to-end command execution (spec 90-92, 97)."""

from __future__ import annotations

import os
import unittest
from io import StringIO
from unittest.mock import patch

from tests.base import ARQGenTestCase


def run_cli(argv, log_dir):
    from app.cli import run
    with patch("sys.stdout", new=StringIO()) as out:
        code = run(["--log-dir", log_dir] + argv)
    return code, out.getvalue()


class TestCLI(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.path = self.project_path()
        self.log_dir = os.path.join(self.tmp, "logs")

    def cli(self, argv):
        return run_cli(argv, self.log_dir)

    def test_full_command_sequence(self):
        code, out = self.cli(["project", "create", self.path, "--name", "CLI Test",
                              "--ruleset", "international_v1"])
        self.assertEqual(code, 0, out)
        self.assertIn("Proyecto creado", out)

        code, out = self.cli(["level", "add", self.path, "--name", "N1",
                              "--elevation", "0", "--height", "3"])
        self.assertEqual(code, 0, out)
        self.assertIn("ARQ-LEVEL-001", out)

        code, out = self.cli(["space", "add", self.path, "--level", "N1",
                              "--name", "Sala", "--type", "LIVING_ROOM",
                              "--polygon", "0,0", "4,0", "4,3", "0,3"])
        self.assertEqual(code, 0, out)
        self.assertIn("12.00 m2", out)

        code, out = self.cli(["wall", "add", self.path, "--level", "N1",
                              "--start", "0,0", "--end", "5,0",
                              "--thickness", "0.2", "--height", "3"])
        self.assertEqual(code, 0, out)
        self.assertIn("ARQ-WALL-001", out)

        code, out = self.cli(["door", "add", self.path, "--wall", "ARQ-WALL-001",
                              "--width", "0.9", "--height", "2.1", "--offset", "1"])
        self.assertEqual(code, 0, out)
        self.assertIn("ARQ-DOOR-001", out)

        code, out = self.cli(["qto", "compute", self.path])
        self.assertEqual(code, 0, out)
        self.assertIn("Cómputo QTO completado", out)

        code, out = self.cli(["qto", "show", self.path])
        self.assertEqual(code, 0, out)
        self.assertIn("WALL_AREA_NET", out)

        code, out = self.cli(["resource", "add", self.path, "--code", "CEM",
                              "--name", "Cemento", "--type", "MATERIAL",
                              "--unit", "saco"])
        self.assertEqual(code, 0, out)

        code, out = self.cli(["price", "set", self.path, "--resource", "CEM",
                              "--price", "180", "--list", "GENERAL"])
        self.assertEqual(code, 0, out)
        self.assertIn("histórico preservado", out)

        code, out = self.cli(["price", "history", self.path, "--resource", "CEM"])
        self.assertEqual(code, 0, out)
        self.assertIn("180.00", out)

        code, out = self.cli(["validate", self.path])
        self.assertEqual(code, 0, out)
        self.assertIn("VALID", out)

        code, out = self.cli(["audit", "show", self.path, "--limit", "5"])
        self.assertEqual(code, 0, out)
        self.assertIn("CREATE_ENTITY", out)

        code, out = self.cli(["backup", "create", self.path,
                              "--dir", os.path.join(self.tmp, "bk")])
        self.assertEqual(code, 0, out)
        self.assertIn("Integridad: ok", out)

    def test_error_exit_code_and_spanish_message(self):
        code, out = self.cli(["project", "create", self.path, "--name", "A"])
        self.assertEqual(code, 0)
        code, out = self.cli(["project", "create", self.path, "--name", "B"])
        self.assertEqual(code, 1)
        self.assertIn("ERROR [ARQ-PER-022]", out)
        self.assertIn("Ya existe un archivo de proyecto", out)

    def test_import_preview_then_approve(self):
        ctx = self.demo_context()
        ctx.close()
        from services.export_service import ExportService
        json_path = ExportService().export(
            self.application.open_project(self.project_path("demo.arqgen")),
            "JSON", os.path.join(self.tmp, "snap.json"))

        code, out = self.cli(["import", json_path, "--out", self.project_path("out.arqgen")])
        self.assertEqual(code, 0, out)
        self.assertIn("vista previa", out.lower())

        code, out = self.cli(["import", json_path, "--out", self.project_path("out.arqgen"),
                              "--approve"])
        self.assertEqual(code, 0, out)
        self.assertIn("Importación completada", out)

    def test_version_save_list(self):
        ctx = self.demo_context()
        ctx.close()
        code, out = self.cli(["version", "save", self.project_path("demo.arqgen"),
                              "--author", "tester", "--description", "base"])
        self.assertEqual(code, 0, out)
        code, out = self.cli(["version", "list", self.project_path("demo.arqgen")])
        self.assertEqual(code, 0, out)
        self.assertIn("base", out)


if __name__ == "__main__":
    unittest.main()
