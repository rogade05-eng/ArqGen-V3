"""Backup / recovery service (spec section 81).

FASE 38 completes the spec checklist: full backup, autosave (rolling),
incremental backup with manifest, journal checkpoint, integrity check,
recovery of a corrupt project and restore. Mandatory before: migrations,
massive imports and destructive operations (restore/version-restore).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List

from core.entities.base import utc_now
from core.errors import PersistenceError
from persistence.sqlite.connection import ConnectionManager

AUTOSAVE_KEEP = 5  # rolling autosave depth
MANIFEST_NAME = "manifest.json"


@dataclass
class BackupInfo:
    path: str
    created_at: datetime
    size_bytes: int
    integrity: str


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupService:
    def __init__(self, backup_dir: str) -> None:
        self.backup_dir = backup_dir

    # -- full backup -------------------------------------------------------
    def create_full_backup(self, db_path: str, label: str = "") -> BackupInfo:
        """Consistent backup of the project file (WAL checkpoint + copy)."""
        self._require_source(db_path)
        os.makedirs(self.backup_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = os.path.splitext(os.path.basename(db_path))[0]
        suffix = f"_{label}" if label else ""
        target = os.path.join(self.backup_dir, f"{base}{suffix}_backup_{stamp}.arqgen")
        self._checkpoint_wal(db_path)
        shutil.copy2(db_path, target)
        integrity = self.check_integrity(target)
        return BackupInfo(
            path=target,
            created_at=utc_now(),
            size_bytes=os.path.getsize(target),
            integrity=integrity,
        )

    # -- FASE 38: autosave (rolling) ---------------------------------------
    def autosave(self, db_path: str, keep: int = AUTOSAVE_KEEP) -> BackupInfo:
        """Rolling autosave keeping the last ``keep`` autosave copies."""
        info = self.create_full_backup(db_path, label="autosave")
        autosaves = [p for p in self.list_backups()
                     if "_autosave_" in os.path.basename(p)]
        # Oldest first removal to keep only ``keep`` copies.
        while len(autosaves) > keep:
            oldest = min(autosaves, key=os.path.getmtime)
            os.remove(oldest)
            autosaves.remove(oldest)
        return info

    # -- FASE 38: incremental backup ---------------------------------------
    def create_incremental_backup(self, db_path: str) -> dict:
        """Backup only when the file changed since the last stored hash.

        The manifest (manifest.json) records the hash chain; when nothing
        changed the result reports ``changed=False`` and no copy is made.
        """
        self._require_source(db_path)
        os.makedirs(self.backup_dir, exist_ok=True)
        manifest = self._load_manifest()
        current_hash = file_sha256(db_path)
        base = os.path.splitext(os.path.basename(db_path))[0]
        last = manifest.get(base, {})
        if last.get("sha256") == current_hash:
            return {"changed": False, "sha256": current_hash,
                    "backup": last.get("path", "")}
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = os.path.join(self.backup_dir,
                              f"{base}_incr_{stamp}.arqgen")
        self._checkpoint_wal(db_path)
        shutil.copy2(db_path, target)
        integrity = self.check_integrity(target)
        manifest[base] = {
            "sha256": current_hash,
            "path": target,
            "created_at": utc_now().isoformat(),
            "size_bytes": os.path.getsize(target),
            "integrity": integrity,
        }
        self._save_manifest(manifest)
        return {"changed": True, "sha256": current_hash,
                "backup": target, "integrity": integrity,
                "created_at": manifest[base]["created_at"]}

    def _load_manifest(self) -> dict:
        path = os.path.join(self.backup_dir, MANIFEST_NAME)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_manifest(self, manifest: dict) -> None:
        path = os.path.join(self.backup_dir, MANIFEST_NAME)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)

    # -- FASE 38: journal / checkpoint --------------------------------------
    def journal_status(self, db_path: str) -> dict:
        """SQLite journal state (WAL file sizes, page counts)."""
        self._require_source(db_path)
        wal = db_path + "-wal"
        shm = db_path + "-shm"
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            page_count = conn.execute("PRAGMA page_count").fetchone()[0]
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        return {
            "journal_mode": str(journal_mode),
            "wal_busy": int(row[0]) if row else 0,
            "wal_log_pages": int(row[1]) if row else 0,
            "wal_checkpointed_pages": int(row[2]) if row else 0,
            "wal_bytes": os.path.getsize(wal) if os.path.exists(wal) else 0,
            "shm_bytes": os.path.getsize(shm) if os.path.exists(shm) else 0,
            "page_count": int(page_count),
        }

    def checkpoint(self, db_path: str, mode: str = "TRUNCATE") -> dict:
        """Force a WAL checkpoint (journal) on the project (spec 81)."""
        self._require_source(db_path)
        if mode not in ("PASSIVE", "FULL", "RESTART", "TRUNCATE"):
            raise PersistenceError(
                message=f"Modo de checkpoint no válido: {mode}",
                code="ARQ-PER-015",
                context={"allowed": ["PASSIVE", "FULL", "RESTART", "TRUNCATE"]})
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
        finally:
            conn.close()
        return {"mode": mode, "busy": int(row[0]) if row else 0,
                "log_pages": int(row[1]) if row else 0,
                "checkpointed_pages": int(row[2]) if row else 0}

    # -- FASE 38: verification of every backup ------------------------------
    def verify_all(self) -> List[dict]:
        """Integrity check of every stored backup copy."""
        results = []
        for path in self.list_backups():
            results.append({
                "path": path,
                "size_bytes": os.path.getsize(path),
                "integrity": self.check_integrity(path),
            })
        return results

    # -- FASE 38: automatic recovery ----------------------------------------
    def recover(self, db_path: str, force: bool = False) -> dict:
        """Recover a project from the newest valid backup (spec 81).

        When the project file is corrupt (or ``force``), the newest backup
        with integrity ``ok`` is restored over it. A safety copy of the
        damaged file is kept with a ``.damaged`` suffix.
        """
        self._require_source(db_path)
        integrity = self.check_integrity(db_path)
        needs_recovery = force or integrity != "ok"
        if not needs_recovery:
            return {"recovered": False, "reason": "integridad ok",
                    "integrity": integrity}
        candidates = [p for p in sorted(self.list_backups(),
                                        key=os.path.getmtime, reverse=True)
                      if self.check_integrity(p) == "ok"]
        if not candidates:
            raise PersistenceError(
                message="No hay un backup válido para recuperar el proyecto",
                code="ARQ-PER-016",
                context={"project": db_path},
                suggested_action="Verifique el directorio de backups "
                                 "('backup verify') o cree uno manual.")
        newest = candidates[0]
        # Keep the damaged file for forensics.
        if integrity != "ok":
            damaged = db_path + ".damaged"
            shutil.copy2(db_path, damaged)
        for ext in ("-wal", "-shm"):
            side = db_path + ext
            if os.path.exists(side):
                os.remove(side)
        shutil.copy2(newest, db_path)
        return {"recovered": True, "from": newest,
                "integrity": self.check_integrity(db_path)}

    # -- existing API --------------------------------------------------------
    def check_integrity(self, db_path: str) -> str:
        if not os.path.exists(db_path):
            raise PersistenceError(
                message=f"Archivo inexistente para verificación: {db_path}",
                code="ARQ-PER-012",
            )
        try:
            conn = sqlite3.connect(db_path)
            result = ConnectionManager.integrity_check(conn)
            conn.close()
            return result
        except sqlite3.DatabaseError:
            return "corrupt"

    def list_backups(self) -> list[str]:
        if not os.path.isdir(self.backup_dir):
            return []
        return sorted(
            os.path.join(self.backup_dir, f)
            for f in os.listdir(self.backup_dir)
            if f.endswith(".arqgen")
        )

    def restore(self, backup_path: str, target_db_path: str) -> BackupInfo:
        """Restore a backup over the target project file (backup first)."""
        if not os.path.exists(backup_path):
            raise PersistenceError(
                message=f"El backup indicado no existe: {backup_path}",
                code="ARQ-PER-013",
                suggested_action="Liste los backups disponibles con backup list.",
            )
        integrity = self.check_integrity(backup_path)
        if integrity != "ok":
            raise PersistenceError(
                message=f"El backup está corrupto (integridad: {integrity})",
                code="ARQ-PER-014",
                context={"backup": backup_path, "integrity": integrity},
                suggested_action="Elija otro backup; no restaure archivos corruptos.",
            )
        # Safety copy of the current state before restoring.
        if os.path.exists(target_db_path):
            self.create_full_backup(target_db_path, label="pre_restore")
            os.remove(target_db_path)
        # Clean WAL/SHM leftovers of the target.
        for ext in ("-wal", "-shm"):
            side = target_db_path + ext
            if os.path.exists(side):
                os.remove(side)
        shutil.copy2(backup_path, target_db_path)
        return BackupInfo(
            path=backup_path,
            created_at=utc_now(),
            size_bytes=os.path.getsize(backup_path),
            integrity=integrity,
        )

    # -- helpers --------------------------------------------------------------
    def _require_source(self, db_path: str) -> None:
        if not os.path.exists(db_path):
            raise PersistenceError(
                message=f"No existe el proyecto a respaldar: {db_path}",
                code="ARQ-PER-010",
            )

    def _checkpoint_wal(self, db_path: str) -> None:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except sqlite3.Error as exc:
            raise PersistenceError(
                message=f"No se pudo preparar el backup (checkpoint WAL): {exc}",
                code="ARQ-PER-011",
            ) from exc


__all__ = ["BackupService", "BackupInfo", "file_sha256", "AUTOSAVE_KEEP"]
