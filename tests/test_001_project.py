"""TEST-001 Project: creation, persistence, reopening (spec 97)."""

from __future__ import annotations

import unittest

from core.errors import PersistenceError
from tests.base import ARQGenTestCase


class TestProject(ARQGenTestCase):
    def test_create_and_reopen(self):
        path = self.project_path()
        ctx = self.application.create_project(path, name="Proyecto A", client="Cliente X")
        self.assertEqual(ctx.project.name, "Proyecto A")
        self.assertTrue(ctx.project.id)
        self.assertEqual(ctx.project.status.value, "DRAFT")
        ctx.close()

        ctx2 = self.application.open_project(path)
        self.assertEqual(ctx2.project.id, ctx.project.id)
        self.assertEqual(ctx2.project.client, "Cliente X")
        ctx2.close()

    def test_duplicate_file_rejected(self):
        path = self.project_path()
        ctx = self.application.create_project(path, name="Uno")
        ctx.close()
        with self.assertRaises(PersistenceError):
            self.application.create_project(path, name="Dos")

    def test_open_missing_project_fails(self):
        with self.assertRaises(PersistenceError):
            self.application.open_project(self.project_path("missing.arqgen"))

    def test_project_requires_name(self):
        from domain.model import Project
        with self.assertRaises(Exception):
            Project(name="")

    def test_settings_roundtrip(self):
        path = self.project_path()
        ctx = self.application.create_project(path, name="S")
        ctx.settings.set("clave", "valor")
        ctx.commit()
        self.assertEqual(ctx.settings.get("clave"), "valor")
        ctx.close()


if __name__ == "__main__":
    unittest.main()
