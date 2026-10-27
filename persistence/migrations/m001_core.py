"""Migration 001_core: projects, events, audit, rules, formulas, calculations, versions."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 1
name = "core"

_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS projects (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        client        TEXT NOT NULL DEFAULT '',
        address       TEXT NOT NULL DEFAULT '',
        description   TEXT NOT NULL DEFAULT '',
        units_length  TEXT NOT NULL DEFAULT 'm',
        ruleset_code  TEXT NOT NULL DEFAULT '',
        currency      TEXT NOT NULL DEFAULT 'CUP',
        code          TEXT NOT NULL DEFAULT '',
        discipline    TEXT NOT NULL DEFAULT 'GENERAL',
        level_id      TEXT,
        status        TEXT NOT NULL DEFAULT 'DRAFT',
        revision      INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id           TEXT PRIMARY KEY,
        type         TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        source       TEXT NOT NULL DEFAULT '',
        timestamp    TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_type ON events (type)",
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id            TEXT PRIMARY KEY,
        user          TEXT NOT NULL,
        timestamp     TEXT NOT NULL,
        object_id     TEXT NOT NULL,
        object_type   TEXT NOT NULL,
        command       TEXT NOT NULL,
        old_value_json TEXT,
        new_value_json TEXT,
        reason        TEXT NOT NULL DEFAULT '',
        result        TEXT NOT NULL DEFAULT 'OK'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_log (object_id)",
    """
    CREATE TABLE IF NOT EXISTS rulesets (
        code           TEXT PRIMARY KEY,
        jurisdiction   TEXT NOT NULL DEFAULT '',
        discipline     TEXT NOT NULL DEFAULT 'GENERAL',
        version        TEXT NOT NULL DEFAULT '1.0',
        effective_date TEXT NOT NULL DEFAULT '',
        source         TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rules (
        code            TEXT NOT NULL,
        ruleset_code    TEXT NOT NULL DEFAULT '',
        discipline      TEXT NOT NULL DEFAULT 'GENERAL',
        category        TEXT NOT NULL DEFAULT 'GENERAL',
        severity        TEXT NOT NULL DEFAULT 'WARNING',
        expression      TEXT NOT NULL,
        message         TEXT NOT NULL DEFAULT '',
        parameters_json TEXT NOT NULL DEFAULT '{}',
        source          TEXT NOT NULL DEFAULT 'ARQ GEN',
        version         TEXT NOT NULL DEFAULT '1.0',
        applies_to      TEXT NOT NULL DEFAULT '*',
        PRIMARY KEY (code, ruleset_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS formulas (
        code           TEXT PRIMARY KEY,
        target_type    TEXT NOT NULL,
        description    TEXT NOT NULL DEFAULT '',
        expression     TEXT NOT NULL,
        unit           TEXT NOT NULL DEFAULT '',
        waste_factor   REAL NOT NULL DEFAULT 0,
        variables_json TEXT NOT NULL DEFAULT '[]',
        version        TEXT NOT NULL DEFAULT '1.0',
        source         TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_formulas_target ON formulas (target_type)",
    """
    CREATE TABLE IF NOT EXISTS calculations (
        id                 TEXT PRIMARY KEY,
        calculation_type   TEXT NOT NULL,
        input_hash         TEXT NOT NULL,
        input_objects_json TEXT NOT NULL DEFAULT '[]',
        parameters_json    TEXT NOT NULL DEFAULT '{}',
        values_json        TEXT NOT NULL DEFAULT '{}',
        units_json         TEXT NOT NULL DEFAULT '{}',
        warnings_json      TEXT NOT NULL DEFAULT '[]',
        errors_json        TEXT NOT NULL DEFAULT '[]',
        formula_version    TEXT NOT NULL DEFAULT '1.0',
        ruleset_version    TEXT NOT NULL DEFAULT 'none',
        engine_version     TEXT NOT NULL DEFAULT '',
        mode               TEXT NOT NULL DEFAULT 'BALANCED',
        status             TEXT NOT NULL DEFAULT 'COMPLETED',
        duration_ms        REAL NOT NULL DEFAULT 0,
        objects_processed  INTEGER NOT NULL DEFAULT 0,
        timestamp          TEXT NOT NULL,
        stale              INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_calculations_hash ON calculations (calculation_type, input_hash)",
    "CREATE INDEX IF NOT EXISTS idx_calculations_stale ON calculations (stale)",
    """
    CREATE TABLE IF NOT EXISTS project_versions (
        id            TEXT PRIMARY KEY,
        number        INTEGER NOT NULL,
        author        TEXT NOT NULL DEFAULT '',
        description   TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL,
        snapshot_json TEXT NOT NULL
    )
    """,
]


def upgrade(session: Session) -> None:
    for sql in _UPGRADE_SQL:
        session.execute(sql)


def downgrade(session: Session) -> None:
    for sql in (
        "DROP TABLE IF EXISTS project_versions",
        "DROP TABLE IF EXISTS calculations",
        "DROP TABLE IF EXISTS formulas",
        "DROP TABLE IF EXISTS rules",
        "DROP TABLE IF EXISTS rulesets",
        "DROP TABLE IF EXISTS audit_log",
        "DROP TABLE IF EXISTS events",
        "DROP TABLE IF EXISTS settings",
        "DROP TABLE IF EXISTS projects",
    ):
        session.execute(sql)
