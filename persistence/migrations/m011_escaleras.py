"""Migration 011_escaleras: escaleras por tipología (v3.19.0).

Tabla nueva de ARQUITECTURA:
- stairs: escaleras reales por tipo (recta, en L, en U/doble piso y
  caracol) con Blondel (2h + p), mesetas y la geometría generada
  (contorno, huellas y mesetas) en metadata.
"""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 11
name = "escaleras_tipos"


def _columnas_comunes() -> str:
    return """
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            discipline    TEXT NOT NULL DEFAULT 'ARCHITECTURE',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'DRAFT',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
    """


def upgrade(session: Session) -> None:
    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS stairs (
            {_columnas_comunes()},
            space_id        TEXT NOT NULL DEFAULT '',
            tipo            TEXT NOT NULL DEFAULT 'recta',
            x               REAL NOT NULL DEFAULT 0.0,
            y               REAL NOT NULL DEFAULT 0.0,
            rotation_deg    REAL NOT NULL DEFAULT 0.0,
            width_m         REAL NOT NULL DEFAULT 1.1,
            desnivel_m      REAL NOT NULL DEFAULT 3.0,
            contrahuella_m  REAL NOT NULL DEFAULT 0.17,
            huella_m        REAL NOT NULL DEFAULT 0.29
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stairs_code "
                    "ON stairs (project_id, code)")


def downgrade(session: Session) -> None:
    session.execute("DROP TABLE IF EXISTS stairs")
