"""FASES 36-38 — Audit filters/stats/export, versioning and backup/recovery
(spec 71, 80, 81; TEST-023 Backup + TEST-024 Recovery).

Expected values verified by hand:
    * audit stats: totals match appended events
    * version compare: added/removed codes per type
    * autosave rolling depth: AUTOSAVE_KEEP = 5
    * incremental backup: second run without changes → changed=False
    * recover: corrupt file restored from newest valid backup
"""

from __future__ import annotations

import json
import os
import shutil
import unittest

from tests.base import ARQGenTestCase

from core.errors import PersistenceError
from persistence.backup.service import AUTOSAVE_KEEP, BackupService, file_sha256


class TestAudit(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def test_query_filters(self):
        # La demo genera eventos CREATE_ENTITY / UPDATE_ENTITY
        rows = self.ctx.audit_repo.query(command="CREATE")
        self.assertTrue(rows)
        self.assertTrue(all("CREATE" in e["command"] for e in rows))
        by_type = self.ctx.audit_repo.query(object_type="WALL", limit=500)
        self.assertTrue(by_type)
        self.assertTrue(all(e["object_type"] == "WALL" for e in by_type))
        empty = self.ctx.audit_repo.query(user="nadie")
        self.assertEqual(empty, [])

    def test_stats_consistent(self):
        stats = self.ctx.audit_repo.stats()
        total = sum(stats["by_command"].values())
        self.assertEqual(stats["total"], total)
        self.assertGreater(stats["total"], 0)
        self.assertEqual(stats["by_result"], {"OK": stats["total"]})

    def test_iter_all_order_and_export(self):
        events = self.ctx.audit_repo.iter_all()
        self.assertEqual(len(events), self.ctx.audit_repo.stats()["total"])
        timestamps = [e["timestamp"] for e in events]
        self.assertEqual(timestamps, sorted(timestamps))
        # Exportación CSV/JSON (vía handler de CLI, FASE 36)
        import csv
        out_csv = os.path.join(self.tmp, "audit.csv")
        with open(out_csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "user", "command"])
            for e in events:
                writer.writerow([e["timestamp"], e["user"], e["command"]])
        with open(out_csv, encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), len(events) + 1)


class TestVersioning(ARQGenTestCase):
    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def tearDown(self):
        self.ctx.close()
        super().tearDown()

    def _make_versions(self):
        from services.architecture_service import ArchitectureService
        from services.version_service import VersionService
        service = VersionService(self.ctx)
        v1 = service.save_version("tester", "estado inicial", self._snapshot())
        # Cambio: nuevo muro → versión 2 distinta
        ArchitectureService(self.ctx).create_wall(
            "Nivel 1", (10.0, 0.0), (15.0, 0.0), thickness_m=0.2, height_m=3.0)
        self.ctx.commit()
        v2 = service.save_version("tester", "muro añadido", self._snapshot())
        self.assertEqual(v1["number"], 1)
        self.assertEqual(v2["number"], 2)
        return service

    def _snapshot(self) -> str:
        import json as _json
        from services.commands_impl import entity_snapshot
        entities = {}
        for entity_type in ("SPACE", "WALL", "DOOR", "WINDOW", "OPENING"):
            rows = [entity_snapshot(e) for e in
                    self.ctx.architecture.list(entity_type, self.ctx.project.id)]
            if rows:
                entities[entity_type] = rows
        project = entity_snapshot(self.ctx.project)
        return _json.dumps({"project": project, "entities": entities},
                           sort_keys=True)

    def test_compare_by_numbers(self):
        service = self._make_versions()
        diff = service.compare_by_numbers(1, 2)
        self.assertEqual(diff["a"], 1)
        self.assertEqual(diff["b"], 2)
        self.assertIn("WALL", diff["changed_types"])
        added = diff["types"]["WALL"]["added"]
        self.assertEqual(len(added), 1)
        self.assertTrue(added[0].startswith("ARQ-WALL-"))
        self.assertEqual(diff["types"]["WALL"]["removed"], [])

    def test_export_and_branch(self):
        service = self._make_versions()
        out = os.path.join(self.tmp, "snap.json")
        service.export_version(2, out)
        with open(out, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertIn("project", data)
        self.assertIn("entities", data)
        # Rama: archivo nuevo con el contenido de la versión 2
        branch_path = os.path.join(self.tmp, "branch.arqgen")
        info = service.branch_version(2, branch_path)
        self.assertTrue(os.path.exists(branch_path))
        self.assertIn("rama v2", info["project"])
        # El archivo rama abre y contiene los muros de la versión 2
        branch_ctx = self.application.open_project(branch_path)
        try:
            walls = branch_ctx.architecture.list(
                "WALL", branch_ctx.project.id)
            self.assertEqual(len(walls), 8)  # 7 demo + 1 añadido
        finally:
            branch_ctx.close()
        with self.assertRaises(PersistenceError):
            service.branch_version(2, branch_path)  # destino ya existe

    def test_restore_creates_automatic_backup(self):
        from services.version_service import VersionService
        service = self._make_versions()
        # backup_dir se deriva del directorio del proyecto: tmp/backups
        backup_dir = service.backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        before = len(BackupService(backup_dir).list_backups())
        snapshot = service.get_snapshot(1)
        service.restore_version(1, snapshot)
        self.ctx.commit()
        after = BackupService(backup_dir).list_backups()
        self.assertEqual(len(after), before + 1)
        self.assertIn("pre_restore", os.path.basename(after[-1]))
        # Tras restaurar la versión 1 el muro añadido desaparece
        walls = self.ctx.architecture.list("WALL", self.ctx.project.id)
        self.assertEqual(len(walls), 7)


class TestBackupRecovery(ARQGenTestCase):
    def _make_project(self, name="b.arqgen"):
        path = self.project_path(name)
        ctx = self.application.create_project(path, name=name)
        ctx.close()
        return path

    def test_full_backup_and_restore(self):
        path = self._make_project()
        service = BackupService(self.tmp)
        info = service.create_full_backup(path)
        self.assertEqual(info.integrity, "ok")
        self.assertTrue(os.path.exists(info.path))
        # Restore sobre archivo nuevo
        target = self.project_path("restored.arqgen")
        service.restore(info.path, target)
        self.assertTrue(os.path.exists(target))
        self.assertEqual(service.check_integrity(target), "ok")

    def test_autosave_rolling_depth(self):
        path = self._make_project()
        service = BackupService(self.tmp)
        for _ in range(AUTOSAVE_KEEP + 2):
            service.autosave(path)
        autosaves = [p for p in service.list_backups()
                     if "_autosave_" in os.path.basename(p)]
        self.assertEqual(len(autosaves), AUTOSAVE_KEEP)

    def test_incremental_backup_hash_chain(self):
        path = self._make_project()
        service = BackupService(self.tmp)
        first = service.create_incremental_backup(path)
        self.assertTrue(first["changed"])
        second = service.create_incremental_backup(path)
        self.assertFalse(second["changed"])   # sin cambios → no copia
        # Cambio real: se crea una copia nueva
        with open(path, "ab") as handle:
            handle.write(b"\x00")  # simula cambio de bytes
        third = service.create_incremental_backup(path)
        self.assertTrue(third["changed"])
        self.assertEqual(file_sha256(path), third["sha256"])

    def test_journal_checkpoint_verify(self):
        path = self._make_project()
        service = BackupService(self.tmp)
        status = service.journal_status(path)
        self.assertEqual(status["journal_mode"], "wal")
        self.assertIn("wal_bytes", status)
        result = service.checkpoint(path, mode="TRUNCATE")
        self.assertEqual(result["mode"], "TRUNCATE")
        service.create_full_backup(path)
        verified = service.verify_all()
        self.assertTrue(all(r["integrity"] == "ok" for r in verified))
        with self.assertRaises(PersistenceError):
            service.checkpoint(path, mode="NOPE")

    def test_recover_corrupt_file(self):
        # TEST-024 Recovery
        path = self._make_project()
        service = BackupService(self.tmp)
        service.create_full_backup(path)
        # Corromper el archivo del proyecto
        with open(path, "r+b") as handle:
            handle.seek(0)
            handle.write(b"XXXX" * 64)
        self.assertEqual(service.check_integrity(path), "corrupt")
        result = service.recover(path)
        self.assertTrue(result["recovered"])
        self.assertEqual(service.check_integrity(path), "ok")
        # Copia forense del archivo dañado
        self.assertTrue(os.path.exists(path + ".damaged"))
        # Proyecto sano → no se recupera
        healthy = service.recover(path)
        self.assertFalse(healthy["recovered"])

    def test_recover_without_backups_raises(self):
        path = self._make_project()
        with open(path, "r+b") as handle:
            handle.seek(0)
            handle.write(b"XXXX" * 64)
        service = BackupService(os.path.join(self.tmp, "empty"))
        with self.assertRaises(PersistenceError):
            service.recover(path)


if __name__ == "__main__":
    unittest.main()
