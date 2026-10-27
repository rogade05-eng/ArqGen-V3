"""Migration 005_installations: networks, nodes, segments (spec 24, 25)."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 5
name = "installations"


def upgrade(session: Session) -> None:
    # Formula catalogue gains the optional condition column (spec 58, 52).
    # ALTER with idempotent guard for SQLite versions without IF NOT EXISTS.
    try:
        session.execute("ALTER TABLE formulas ADD COLUMN condition_sql TEXT NOT NULL DEFAULT ''")
    except Exception:  # pragma: no cover - column already present
        pass
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS install_networks (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            discipline    TEXT NOT NULL DEFAULT 'ELECTRICAL',
            system        TEXT NOT NULL DEFAULT 'POWER',
            description   TEXT NOT NULL DEFAULT '',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_install_networks_code "
                    "ON install_networks (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS install_nodes (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            network_id    TEXT NOT NULL,
            kind          TEXT NOT NULL DEFAULT 'JUNCTION',
            name          TEXT NOT NULL DEFAULT '',
            discipline    TEXT NOT NULL DEFAULT 'INSTALLATIONS',
            x             REAL NOT NULL DEFAULT 0,
            y             REAL NOT NULL DEFAULT 0,
            elevation_m   REAL NOT NULL DEFAULT 0,
            space_id      TEXT,
            wall_id       TEXT,
            attrs_json    TEXT NOT NULL DEFAULT '{}',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_install_nodes_network "
                    "ON install_nodes (network_id)")
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_install_nodes_code "
                    "ON install_nodes (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS install_segments (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            network_id    TEXT NOT NULL,
            from_node_id  TEXT NOT NULL,
            to_node_id    TEXT NOT NULL,
            kind          TEXT NOT NULL DEFAULT 'CONDUIT',
            name          TEXT NOT NULL DEFAULT '',
            discipline    TEXT NOT NULL DEFAULT 'INSTALLATIONS',
            length_m      REAL NOT NULL DEFAULT 0,
            diameter_mm   REAL NOT NULL DEFAULT 0,
            width_mm      REAL NOT NULL DEFAULT 0,
            height_mm     REAL NOT NULL DEFAULT 0,
            slope_pct     REAL NOT NULL DEFAULT 0,
            material      TEXT NOT NULL DEFAULT '',
            routing       TEXT NOT NULL DEFAULT 'ORTHO',
            waypoints_json TEXT NOT NULL DEFAULT '[]',
            crossings     INTEGER NOT NULL DEFAULT 0,
            attrs_json    TEXT NOT NULL DEFAULT '{}',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_install_segments_network "
                    "ON install_segments (network_id)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_install_segments_from "
                    "ON install_segments (from_node_id)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_install_segments_to "
                    "ON install_segments (to_node_id)")
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_install_segments_code "
                    "ON install_segments (project_id, code)")


def downgrade(session: Session) -> None:
    for sql in (
        "DROP TABLE IF EXISTS install_segments",
        "DROP TABLE IF EXISTS install_nodes",
        "DROP TABLE IF EXISTS install_networks",
    ):
        session.execute(sql)
    try:  # reversible migration: remove the added column when SQLite allows
        session.execute("ALTER TABLE formulas DROP COLUMN condition_sql")
    except Exception:  # pragma: no cover - older SQLite cannot drop columns
        pass
