"""Migration 006_structure: materials, sections, elements, load cases,
combinations (spec sections 33, 34)."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 6
name = "structure"


def upgrade(session: Session) -> None:
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS struct_materials (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            kind          TEXT NOT NULL DEFAULT 'CONCRETE',
            discipline    TEXT NOT NULL DEFAULT 'STRUCTURE',
            level_id      TEXT,
            fck_mpa       REAL NOT NULL DEFAULT 0,
            fy_mpa        REAL NOT NULL DEFAULT 0,
            e_gpa         REAL NOT NULL DEFAULT 0,
            density_kn_m3 REAL NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_struct_materials_code "
                    "ON struct_materials (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS struct_sections (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            shape         TEXT NOT NULL DEFAULT 'RECTANGLE',
            discipline    TEXT NOT NULL DEFAULT 'STRUCTURE',
            level_id      TEXT,
            h_mm          REAL NOT NULL DEFAULT 0,
            b_mm          REAL NOT NULL DEFAULT 0,
            tw_mm         REAL NOT NULL DEFAULT 0,
            tf_mm         REAL NOT NULL DEFAULT 0,
            d_mm          REAL NOT NULL DEFAULT 0,
            weight_kg_m   REAL NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_struct_sections_code "
                    "ON struct_sections (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS struct_elements (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            kind          TEXT NOT NULL DEFAULT 'BEAM',
            name          TEXT NOT NULL DEFAULT '',
            material_id   TEXT,
            section_id    TEXT,
            start_x       REAL NOT NULL DEFAULT 0,
            start_y       REAL NOT NULL DEFAULT 0,
            end_x         REAL NOT NULL DEFAULT 0,
            end_y         REAL NOT NULL DEFAULT 0,
            z0            REAL NOT NULL DEFAULT 0,
            z1            REAL NOT NULL DEFAULT 0,
            load_udl_kn_m REAL NOT NULL DEFAULT 0,
            point_loads_json TEXT NOT NULL DEFAULT '[]',
            attrs_json    TEXT NOT NULL DEFAULT '{}',
            level_id      TEXT,
            space_id      TEXT,
            discipline    TEXT NOT NULL DEFAULT 'STRUCTURE',
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_struct_elements_kind "
                    "ON struct_elements (project_id, kind)")
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_struct_elements_code "
                    "ON struct_elements (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS struct_load_cases (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            kind          TEXT NOT NULL DEFAULT 'DEAD',
            discipline    TEXT NOT NULL DEFAULT 'STRUCTURE',
            level_id      TEXT,
            factor        REAL NOT NULL DEFAULT 1.0,
            description   TEXT NOT NULL DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_struct_load_cases_code "
                    "ON struct_load_cases (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS struct_combinations (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            case_factors_json TEXT NOT NULL DEFAULT '{}',
            description   TEXT NOT NULL DEFAULT '',
            discipline    TEXT NOT NULL DEFAULT 'STRUCTURE',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_struct_combinations_code "
                    "ON struct_combinations (project_id, code)")


def downgrade(session: Session) -> None:
    for sql in (
        "DROP TABLE IF EXISTS struct_combinations",
        "DROP TABLE IF EXISTS struct_load_cases",
        "DROP TABLE IF EXISTS struct_elements",
        "DROP TABLE IF EXISTS struct_sections",
        "DROP TABLE IF EXISTS struct_materials",
    ):
        session.execute(sql)
