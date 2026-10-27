"""Shared test helpers: isolated project fixtures (spec section 96)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

# Ensure the project root is on sys.path when running from any CWD.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.context import ApplicationContext  # noqa: E402
from app.demo import build_demo  # noqa: E402


class ARQGenTestCase(unittest.TestCase):
    """Base test case with a temporary workspace and a fresh application."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="arqgen_test_")
        self.application = ApplicationContext()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project_path(self, name: str = "test.arqgen") -> str:
        return os.path.join(self.tmp, name)

    def demo_context(self, name: str = "demo.arqgen"):
        return build_demo(self.application, self.project_path(name))


__all__ = ["ARQGenTestCase", "PROJECT_ROOT"]
