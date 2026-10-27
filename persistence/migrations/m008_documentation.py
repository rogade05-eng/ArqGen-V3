"""Migration 008_documentation: drawings + doc templates (spec 68-70)."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 8
name = "documentation"


def upgrade(session: Session) -> None:
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS drawings (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            discipline    TEXT NOT NULL DEFAULT 'DOCUMENTATION',
            sheet         TEXT NOT NULL DEFAULT '',
            sheet_size    TEXT NOT NULL DEFAULT 'A3',
            scale         TEXT NOT NULL DEFAULT '1:50',
            orientation   TEXT NOT NULL DEFAULT 'LANDSCAPE',
            view          TEXT NOT NULL DEFAULT 'PLAN',
            level_id      TEXT,
            layers_json   TEXT NOT NULL DEFAULT '[]',
            annotations_json TEXT NOT NULL DEFAULT '[]',
            titleblock_json  TEXT NOT NULL DEFAULT '{}',
            status        TEXT NOT NULL DEFAULT 'DRAFT',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_drawings_code "
                    "ON drawings (project_id, code)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_drawings_project "
                    "ON drawings (project_id, view)")

    session.execute(
        """
        CREATE TABLE IF NOT EXISTS doc_templates (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            discipline    TEXT NOT NULL DEFAULT 'DOCUMENTATION',
            name          TEXT NOT NULL DEFAULT '',
            body          TEXT NOT NULL DEFAULT '',
            level_id      TEXT,
            variables_json   TEXT NOT NULL DEFAULT '{}',
            sections_json    TEXT NOT NULL DEFAULT '[]',
            tables_json      TEXT NOT NULL DEFAULT '[]',
            styles_json      TEXT NOT NULL DEFAULT '{}',
            headers       TEXT NOT NULL DEFAULT '',
            footers       TEXT NOT NULL DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'DRAFT',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_doc_templates_code "
                    "ON doc_templates (project_id, code)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_doc_templates_name "
                    "ON doc_templates (project_id, name)")


def downgrade(session: Session) -> None:
    session.execute("DROP TABLE IF EXISTS doc_templates")
    session.execute("DROP TABLE IF EXISTS drawings")
