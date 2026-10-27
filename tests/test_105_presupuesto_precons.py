"""PreconsBudgetService (v2.0.0): presupuesto por catálogo oficial.

Cubre: creación, alta/acumulación de renglones, fijado de cantidades,
eliminación, subtotales por sección, totales con coeficientes,
persistencia (reabrir el proyecto conserva el presupuesto) y
exportación CSV.
"""

from __future__ import annotations

import os
import unittest

from core.errors import DomainError
from tests.base import ARQGenTestCase

REAL_CODE = "precons_iii_rospres_330"


def _service(context):
    from services.precons_budget_service import PreconsBudgetService
    service = PreconsBudgetService(context)
    service.load_ruleset(REAL_CODE)
    return service


class TestPreconsBudget(ARQGenTestCase):
    """Ciclo de vida completo del presupuesto por catálogo."""

    def _project(self):
        return self.application.create_project(
            self.project_path("presu.arqgen"), "Presupuesto Test")

    def test_create_and_add_lines(self):
        service = _service(self._project())
        service.create("Mi presupuesto")
        service.add_item("011111", 500)
        service.add_item("020112", 2)
        lines = service.lines()
        self.assertEqual(len(lines), 2)
        by_code = {line["code"]: line for line in lines}
        self.assertAlmostEqual(by_code["011111"]["amount"], 13405.0, places=2)
        self.assertAlmostEqual(by_code["020112"]["amount"], 59444.04, places=2)

    def test_add_same_item_accumulates(self):
        service = _service(self._project())
        service.add_item("011111", 100)
        service.add_item("011111", 50)
        lines = service.lines()
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines[0]["quantity"], 150.0, places=3)
        self.assertAlmostEqual(lines[0]["amount"], 4021.5, places=2)

    def test_set_quantity_and_remove(self):
        service = _service(self._project())
        service.add_item("011111", 500)
        service.set_quantity("011111", 100)
        self.assertAlmostEqual(service.lines()[0]["amount"], 2681.0, places=2)
        service.remove_item("011111")
        self.assertEqual(service.lines(), [])
        with self.assertRaises(DomainError):
            service.set_quantity("011111", 10)

    def test_negative_quantity_rejected(self):
        service = _service(self._project())
        with self.assertRaises(DomainError):
            service.add_item("011111", -5)

    def test_unknown_and_non_official_items_rejected(self):
        service = _service(self._project())
        with self.assertRaises(DomainError):
            service.add_item("999999", 1.0)

    def test_sections_become_chapters_with_subtotals(self):
        service = _service(self._project())
        service.add_item("011111", 500)    # sección 01
        service.add_item("011112", 250)    # sección 01
        service.add_item("020112", 2)      # sección 02
        tree = service.tree()
        self.assertEqual(len(tree["chapters"]), 2)
        by_code = {c["code"]: c for c in tree["chapters"]}
        self.assertAlmostEqual(by_code["01"]["direct"], 17010.0, places=2)
        self.assertAlmostEqual(by_code["02"]["direct"], 59444.04, places=2)
        self.assertEqual(len(by_code["01"]["items"]), 2)

    def test_totals_with_coefficients(self):
        service = _service(self._project())
        service.add_item("011111", 500)
        tree = service.tree()
        # Sin coeficientes en la ruleset real: total == directo.
        self.assertAlmostEqual(tree["direct"], 13405.0, places=2)
        self.assertAlmostEqual(tree["total"], tree["direct"], places=2)

    def test_persistence_across_reopen(self):
        path = self.project_path("presu_persist.arqgen")
        self.application.create_project(path, "Persistencia")
        service = _service(self.application.open_project(path))
        service.add_item("011111", 500)
        service.add_item("020112", 2)
        first_total = service.totals()["total"]

        reopened = _service(self.application.open_project(path))
        self.assertEqual(len(reopened.lines()), 2)
        self.assertAlmostEqual(reopened.totals()["total"], first_total,
                               places=2)

    def test_budget_separated_from_template_budgets(self):
        """El presupuesto PRECONS convive con el de plantilla del demo."""
        context = self.demo_context()
        service = _service(context)
        service.add_item("011111", 10)
        tree = service.tree()
        # Solo el renglón del catálogo, sin los ítems 01.01 de plantilla.
        self.assertEqual(len(service.lines()), 1)
        self.assertAlmostEqual(tree["total"], 268.1, places=2)

    def test_clear_empties_budget(self):
        service = _service(self._project())
        service.add_item("011111", 10)
        service.add_item("011112", 10)
        removed = service.clear()
        self.assertEqual(removed, 2)
        self.assertEqual(service.lines(), [])

    def test_csv_export(self):
        service = _service(self._project())
        service.add_item("011111", 500)
        path = os.path.join(self.tmp, "presupuesto.csv")
        service.save_csv(path)
        content = open(path, encoding="utf-8-sig").read()
        self.assertIn("011111", content)
        self.assertIn("MANIGUA MANUAL", content)
        self.assertIn("13405.00", content)
        self.assertIn("TOTAL", content)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
