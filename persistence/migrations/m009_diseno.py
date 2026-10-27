"""Migration 009_diseno: mobiliario, cubiertas, rampas y barandillas (v3.15.0).

Cuatro tablas nuevas de ARQUITECTURA para la concepción de espacios:
- furniture: piezas de mobiliario dentro de los locales (uso social y
  doméstico, catálogo de domain/mobiliario.py).
- roofs: la cubierta del edificio (tipología, material, estructura,
  pendiente, alero, contorno y cumbrera).
- ramps: rampas accesibles (huella, desnivel y pendiente).
- handrails: barandillas y barras de apoyo (polilínea + alturas).
"""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 9
name = "diseno_espacios"


def _columnas_comunes(disciplina: str = "ARCHITECTURE") -> str:
    return f"""
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            discipline    TEXT NOT NULL DEFAULT '{disciplina}',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'DRAFT',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{{}}'
    """


def upgrade(session: Session) -> None:
    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS furniture (
            {_columnas_comunes()},
            space_id      TEXT NOT NULL DEFAULT '',
            kind          TEXT NOT NULL DEFAULT 'MOB',
            name          TEXT NOT NULL DEFAULT '',
            x             REAL NOT NULL DEFAULT 0.0,
            y             REAL NOT NULL DEFAULT 0.0,
            rotation_deg  REAL NOT NULL DEFAULT 0.0,
            width_m       REAL NOT NULL DEFAULT 1.0,
            depth_m       REAL NOT NULL DEFAULT 0.5,
            height_m      REAL NOT NULL DEFAULT 0.75
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_furniture_code "
                    "ON furniture (project_id, code)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_furniture_space "
                    "ON furniture (project_id, space_id)")

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS roofs (
            {_columnas_comunes()},
            tipologia         TEXT NOT NULL DEFAULT 'plana_no_transitable',
            material          TEXT NOT NULL DEFAULT 'losa_impermeabilizada',
            estructura        TEXT NOT NULL DEFAULT 'hormigon',
            pendiente_pct     REAL NOT NULL DEFAULT 2.0,
            alero_m           REAL NOT NULL DEFAULT 0.6,
            altura_cumbrera_m REAL NOT NULL DEFAULT 0.0,
            footprint_json    TEXT NOT NULL DEFAULT '[]',
            ridge_json        TEXT NOT NULL DEFAULT 'null'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_roofs_code "
                    "ON roofs (project_id, code)")

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ramps (
            {_columnas_comunes()},
            space_id    TEXT NOT NULL DEFAULT '',
            width_m     REAL NOT NULL DEFAULT 1.2,
            length_m    REAL NOT NULL DEFAULT 1.5,
            desnivel_m  REAL NOT NULL DEFAULT 0.15,
            slope_pct   REAL NOT NULL DEFAULT 10.0,
            corners_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ramps_code "
                    "ON ramps (project_id, code)")

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS handrails (
            {_columnas_comunes()},
            space_id            TEXT NOT NULL DEFAULT '',
            kind                TEXT NOT NULL DEFAULT 'barandilla',
            points_json         TEXT NOT NULL DEFAULT '[]',
            altura_m            REAL NOT NULL DEFAULT 0.9,
            altura_secundaria_m REAL NOT NULL DEFAULT 0.0
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_handrails_code "
                    "ON handrails (project_id, code)")


def downgrade(session: Session) -> None:
    session.execute("DROP TABLE IF EXISTS handrails")
    session.execute("DROP TABLE IF EXISTS ramps")
    session.execute("DROP TABLE IF EXISTS roofs")
    session.execute("DROP TABLE IF EXISTS furniture")
