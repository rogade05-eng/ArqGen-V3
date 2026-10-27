"""Migration framework (spec section 79).

Migrations are versioned, ordered and reversible when technically possible.
A backup is mandatory before running migrations (spec section 81).
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from core.errors import MigrationError
from persistence.sqlite.connection import Session


class Migration(Protocol):
    version: int
    name: str

    def upgrade(self, session: Session) -> None: ...

    def downgrade(self, session: Session) -> None: ...


def ensure_version_table(session: Session) -> None:
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def applied_versions(session: Session) -> List[int]:
    ensure_version_table(session)
    rows = session.query_all("SELECT version FROM schema_version ORDER BY version")
    return [int(r["version"]) for r in rows]


def record_version(session: Session, version: int, name: str) -> None:
    session.execute(
        "INSERT INTO schema_version (version, name) VALUES (?, ?)",
        (version, name),
    )


def remove_version(session: Session, version: int) -> None:
    session.execute("DELETE FROM schema_version WHERE version = ?", (version,))


class MigrationRunner:
    """Applies pending migrations in order; supports step rollback."""

    def __init__(self, migrations: List[Migration]) -> None:
        self.migrations = sorted(migrations, key=lambda m: m.version)
        seen = set()
        for m in self.migrations:
            if m.version in seen:
                raise MigrationError(
                    message=f"Versión de migración duplicada: {m.version}",
                    code="ARQ-MIG-001",
                )
            seen.add(m.version)

    def migrate(self, session: Session, target: Optional[int] = None) -> List[int]:
        done: List[int] = []
        current = applied_versions(session)
        for migration in self.migrations:
            if migration.version in current:
                continue
            if target is not None and migration.version > target:
                continue
            try:
                migration.upgrade(session)
                record_version(session, migration.version, migration.name)
                done.append(migration.version)
            except Exception as exc:
                raise MigrationError(
                    message=f"Fallo la migración {migration.version:03d} ({migration.name}): {exc}",
                    code="ARQ-MIG-002",
                    context={"version": migration.version, "name": migration.name},
                    suggested_action="Restaure el backup creado antes de migrar y reporte el error.",
                ) from exc
        return done

    def rollback_last(self, session: Session) -> Optional[int]:
        current = applied_versions(session)
        if not current:
            return None
        last = current[-1]
        migration = next((m for m in self.migrations if m.version == last), None)
        if migration is None:
            raise MigrationError(
                message=f"No existe migración registrada para versión {last}",
                code="ARQ-MIG-003",
            )
        migration.downgrade(session)
        remove_version(session, migration.version)
        return migration.version


__all__ = ["Migration", "MigrationRunner", "applied_versions", "ensure_version_table"]
