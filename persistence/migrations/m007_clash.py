"""Migration 007_clash: coordination clash register (spec sections 35, 36)."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 7
name = "clash"


def upgrade(session: Session) -> None:
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS clashes (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            object_a_type TEXT NOT NULL DEFAULT '',
            object_a_id   TEXT NOT NULL DEFAULT '',
            object_a_code TEXT NOT NULL DEFAULT '',
            object_b_type TEXT NOT NULL DEFAULT '',
            object_b_id   TEXT NOT NULL DEFAULT '',
            object_b_code TEXT NOT NULL DEFAULT '',
            type          TEXT NOT NULL DEFAULT 'HARD',
            severity      TEXT NOT NULL DEFAULT 'MEDIUM',
            rule          TEXT NOT NULL DEFAULT '',
            location_x    REAL NOT NULL DEFAULT 0,
            location_y    REAL NOT NULL DEFAULT 0,
            distance      REAL NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'OPEN',
            discipline    TEXT NOT NULL DEFAULT 'SECURITY',
            level_id      TEXT,
            resolved_at   TEXT,
            notes         TEXT NOT NULL DEFAULT '',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_clashes_project "
                    "ON clashes (project_id, status)")
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clashes_code "
                    "ON clashes (project_id, code)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_clashes_pair "
                    "ON clashes (object_a_id, object_b_id, type)")


def downgrade(session: Session) -> None:
    session.execute("DROP TABLE IF EXISTS clashes")
