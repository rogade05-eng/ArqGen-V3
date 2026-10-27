"""Migration 003_qto: quantity results with full traceability (spec 51, 103)."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 3
name = "qto"


def upgrade(session: Session) -> None:
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS quantities (
            id                  TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL,
            object_id           TEXT NOT NULL,
            object_type         TEXT NOT NULL,
            object_code         TEXT NOT NULL DEFAULT '',
            formula_code        TEXT NOT NULL,
            formula_expression  TEXT NOT NULL DEFAULT '',
            variables_json      TEXT NOT NULL DEFAULT '{}',
            raw_quantity        REAL NOT NULL DEFAULT 0,
            waste_factor        REAL NOT NULL DEFAULT 0,
            final_quantity      REAL NOT NULL DEFAULT 0,
            unit                TEXT NOT NULL DEFAULT '',
            source              TEXT NOT NULL DEFAULT '',
            input_hash          TEXT NOT NULL DEFAULT '',
            stale               INTEGER NOT NULL DEFAULT 0,
            computed_at         TEXT NOT NULL
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_quantities_object ON quantities (object_id)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_quantities_stale ON quantities (stale)")


def downgrade(session: Session) -> None:
    session.execute("DROP TABLE IF EXISTS quantities")
