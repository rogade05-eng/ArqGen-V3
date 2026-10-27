"""TEST-019/021/023/024: DXF export, XLSX/CSV, backup/recovery (spec 97)."""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase


class TestExports(ARQGenTestCase):
    def test_dxf_export_readable(self):
        ctx = self.demo_context()
        from services.export_service import ExportService
        path = ExportService().export(ctx, "DXF", os.path.join(self.tmp, "plan.dxf"))
        self.assertTrue(os.path.exists(path))
        import ezdxf
        doc = ezdxf.readfile(path)
        layers = {layer.dxf.name for layer in doc.layers}
        for expected in ("ARQ-WALL", "ARQ-OPENING", "ARQ-SPACE", "ARQ-TEXT"):
            self.assertIn(expected, layers)
        # Walls are drawn in a level layout
        layout_names = [name for name in doc.layouts.names() if name.startswith("PLANTA_")]
        self.assertTrue(layout_names)
        walls = [e for e in doc.layouts.get(layout_names[0]) if e.dxf.layer == "ARQ-WALL"]
        self.assertEqual(len(walls), 7)
        ctx.close()

    def test_xlsx_export_readable(self):
        ctx = self.demo_context()
        from services.export_service import ExportService
        path = ExportService().export(ctx, "XLSX", os.path.join(self.tmp, "planilla.xlsx"))
        from openpyxl import load_workbook
        wb = load_workbook(path)
        self.assertIn("Cantidades", wb.sheetnames)
        self.assertIn("Recursos", wb.sheetnames)
        ws = wb["Cantidades"]
        headers = [c.value for c in ws[1]]
        self.assertIn("Objeto", headers)
        self.assertIn("Final", headers)
        self.assertGreater(ws.max_row, 1)
        ctx.close()

    def test_csv_export(self):
        ctx = self.demo_context()
        from services.export_service import ExportService
        path = ExportService().export(ctx, "CSV", os.path.join(self.tmp, "q.csv"),
                                      options={"table": "quantities"})
        with open(path, "r", encoding="utf-8-sig") as fh:
            content = fh.read()
        self.assertIn("objeto", content.lower())
        self.assertIn("ARQ-WALL-001", content)
        path_b = ExportService().export(ctx, "CSV", os.path.join(self.tmp, "b.csv"),
                                        options={"table": "budget"})
        with open(path_b, "r", encoding="utf-8-sig") as fh:
            self.assertIn("TOTAL", fh.read())
        ctx.close()

    def test_unsupported_format_rejected(self):
        ctx = self.demo_context()
        from core.errors import ExportError
        from services.export_service import ExportService
        with self.assertRaises(ExportError):
            ExportService().export(ctx, "DWG", os.path.join(self.tmp, "x.dwg"))
        ctx.close()


class TestJSONRoundTrip(ARQGenTestCase):
    def test_export_import_full_cycle(self):
        ctx = self.demo_context()
        from services.export_service import ExportService
        json_path = ExportService().export(ctx, "JSON", os.path.join(self.tmp, "snap.json"))
        walls_before = ctx.architecture.count("WALL", ctx.project.id)
        spaces_before = ctx.architecture.count("SPACE", ctx.project.id)
        budget_before = ctx.budget_repo.latest_budget(ctx.project.id)["total_cost"]
        ctx.close()

        from services.import_service import ImportService
        importer = ImportService(self.application)
        # Preview first (no changes)
        preview = importer.preview(json_path)
        self.assertEqual(preview["counts"]["WALL"], walls_before)
        self.assertEqual(preview["errors"], [])
        result = importer.import_snapshot(json_path, self.project_path("restored.arqgen"),
                                          approve=True)
        self.assertTrue(result["approved"])

        ctx2 = self.application.open_project(self.project_path("restored.arqgen"))
        self.assertEqual(ctx2.architecture.count("WALL", ctx2.project.id), walls_before)
        self.assertEqual(ctx2.architecture.count("SPACE", ctx2.project.id), spaces_before)
        # QTO can be recomputed on the imported model
        from services.quantity_service import QuantityService
        stats = QuantityService(ctx2).compute_all()
        self.assertGreater(stats.objects_processed, 0)
        ctx2.close()


class TestBackupRecovery(ARQGenTestCase):
    def test_backup_create_restore(self):
        from persistence.backup.service import BackupService
        backup_dir = os.path.join(self.tmp, "backups")
        path = self.project_path()
        ctx = self.application.create_project(path, name="Backup")
        ctx.user = "tester"
        from services.architecture_service import ArchitectureService
        ArchitectureService(ctx).create_level("N1", 0.0, 3.0)
        ctx.commit()
        ctx.close()

        service = BackupService(backup_dir)
        info = service.create_full_backup(path)
        self.assertTrue(os.path.exists(info.path))
        self.assertEqual(info.integrity, "ok")
        self.assertEqual(len(service.list_backups()), 1)

        # Modify the original destructively
        ctx2 = self.application.open_project(path)
        ctx2.architecture.create = None  # no-op; drop tables instead
        ctx2.session.execute("DELETE FROM levels")
        ctx2.commit()
        self.assertEqual(ctx2.architecture.count("LEVEL", ctx2.project.id), 0)
        ctx2.close()

        # Restore
        service.restore(info.path, path)
        ctx3 = self.application.open_project(path)
        self.assertEqual(ctx3.architecture.count("LEVEL", ctx3.project.id), 1)
        ctx3.close()

    def test_restore_rejects_corrupt_backup(self):
        from core.errors import PersistenceError
        from persistence.backup.service import BackupService
        backup_dir = os.path.join(self.tmp, "backups")
        path = self.project_path()
        ctx = self.application.create_project(path, name="B2")
        ctx.close()
        service = BackupService(backup_dir)
        info = service.create_full_backup(path)
        with open(info.path, "wb") as fh:
            fh.write(b"corrupt garbage not sqlite")
        with self.assertRaises(PersistenceError):
            service.restore(info.path, path)

    def test_version_save_and_restore(self):
        ctx = self.demo_context()
        ctx.user = "tester"
        import json
        from exporters.json_io import JSONExporter
        from services.version_service import VersionService
        snapshot = JSONExporter.build_snapshot(ctx)
        info = VersionService(ctx).save_version(
            "tester", "estado inicial", json.dumps(snapshot, ensure_ascii=False))
        self.assertEqual(info["number"], 1)

        # Destructive change
        from services.architecture_service import ArchitectureService
        ArchitectureService(ctx).delete_entity("WALL", "ARQ-WALL-001")
        ctx.commit()
        self.assertEqual(ctx.architecture.count("WALL", ctx.project.id), 6)

        # Restore version 1 (with automatic pre-restore backup)
        import tempfile
        from app.paths import ensure_dir
        from persistence.backup.service import BackupService
        backup_dir = ensure_dir(os.path.join(self.tmp, "backups"))
        service = BackupService(backup_dir)
        service.create_full_backup(self.project_path("demo.arqgen"))

        snap = VersionService(ctx).get_snapshot(1)
        VersionService(ctx).restore_version(1, snap)
        ctx.commit()
        self.assertEqual(ctx.architecture.count("WALL", ctx.project.id), 7)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
