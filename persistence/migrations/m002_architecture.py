"""Migration 002_architecture: site, building, level, zone, space, wall, openings, relationships."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 2
name = "architecture"

_ENTITY_COLUMNS = """
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    code          TEXT NOT NULL DEFAULT '',
    discipline    TEXT NOT NULL DEFAULT 'ARCHITECTURE',
    level_id      TEXT,
    status        TEXT NOT NULL DEFAULT 'DRAFT',
    revision      INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
"""

_UPGRADE_SQL = [
    f"CREATE TABLE IF NOT EXISTS sites ({_ENTITY_COLUMNS}, name TEXT NOT NULL DEFAULT '', area_m2 REAL NOT NULL DEFAULT 0, boundary_json TEXT)",
    f"CREATE TABLE IF NOT EXISTS buildings ({_ENTITY_COLUMNS}, site_id TEXT, name TEXT NOT NULL DEFAULT '', floors INTEGER NOT NULL DEFAULT 1, description TEXT NOT NULL DEFAULT '')",
    f"CREATE TABLE IF NOT EXISTS levels ({_ENTITY_COLUMNS}, building_id TEXT, name TEXT NOT NULL DEFAULT '', elevation_m REAL NOT NULL DEFAULT 0, height_m REAL NOT NULL DEFAULT 3)",
    f"CREATE TABLE IF NOT EXISTS zones ({_ENTITY_COLUMNS}, name TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'SERVICE')",
    f"""CREATE TABLE IF NOT EXISTS spaces (
        { _ENTITY_COLUMNS },
        zone_id     TEXT,
        name        TEXT NOT NULL DEFAULT '',
        space_type  TEXT NOT NULL DEFAULT 'ROOM',
        boundary_json TEXT NOT NULL DEFAULT '[]'
    )""",
    f"""CREATE TABLE IF NOT EXISTS walls (
        { _ENTITY_COLUMNS },
        start_json    TEXT NOT NULL,
        end_json      TEXT NOT NULL,
        thickness_m   REAL NOT NULL DEFAULT 0.2,
        height_m      REAL NOT NULL DEFAULT 3.0,
        base_offset_m REAL NOT NULL DEFAULT 0,
        material_id   TEXT,
        structural    INTEGER NOT NULL DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS openings (
        { _ENTITY_COLUMNS },
        wall_id        TEXT NOT NULL,
        kind           TEXT NOT NULL DEFAULT 'OPENING',
        width_m        REAL NOT NULL DEFAULT 0.9,
        height_m       REAL NOT NULL DEFAULT 2.1,
        offset_m       REAL NOT NULL DEFAULT 0,
        sill_height_m  REAL NOT NULL DEFAULT 0,
        swing          TEXT NOT NULL DEFAULT 'LEFT',
        material_id    TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_openings_wall ON openings (wall_id)",
    "CREATE INDEX IF NOT EXISTS idx_walls_level ON walls (level_id)",
    "CREATE INDEX IF NOT EXISTS idx_spaces_level ON spaces (level_id)",
    f"""CREATE TABLE IF NOT EXISTS space_relationships (
        { _ENTITY_COLUMNS },
        from_space_id TEXT NOT NULL,
        to_space_id   TEXT NOT NULL,
        kind          TEXT NOT NULL DEFAULT 'adjacent_to',
        source        TEXT NOT NULL DEFAULT 'manual'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_rel_from ON space_relationships (from_space_id)",
    "CREATE INDEX IF NOT EXISTS idx_rel_to ON space_relationships (to_space_id)",
]


def upgrade(session: Session) -> None:
    for sql in _UPGRADE_SQL:
        session.execute(sql)


def downgrade(session: Session) -> None:
    for sql in (
        "DROP TABLE IF EXISTS space_relationships",
        "DROP TABLE IF EXISTS openings",
        "DROP TABLE IF EXISTS walls",
        "DROP TABLE IF EXISTS spaces",
        "DROP TABLE IF EXISTS zones",
        "DROP TABLE IF EXISTS levels",
        "DROP TABLE IF EXISTS buildings",
        "DROP TABLE IF EXISTS sites",
    ):
        session.execute(sql)
