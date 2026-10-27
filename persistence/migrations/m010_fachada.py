"""Migration 010_fachada: ascensores, parasoles y pieles (v3.18.0).

Tres tablas nuevas de ARQUITECTURA:
- elevators: huecos de ascensor según Neufert (tipo, capacidad,
  cabina, puerta, foso y recorrido en metadata).
- parasols: parasoles por lado de fachada (tipo, material, lamas,
  vuelo y separación).
- skins: pieles exteriores contemporáneas (doble piel, celosía,
  malla, terracota... con su cámara ventilada).
"""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 10
name = "fachada_ascensores"


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
        CREATE TABLE IF NOT EXISTS elevators (
            {_columnas_comunes()},
            tipo         TEXT NOT NULL DEFAULT 'pasajeros',
            capacidad_kg INTEGER NOT NULL DEFAULT 630,
            personas     INTEGER NOT NULL DEFAULT 8,
            x            REAL NOT NULL DEFAULT 0.0,
            y            REAL NOT NULL DEFAULT 0.0,
            rotation_deg REAL NOT NULL DEFAULT 0.0,
            width_m      REAL NOT NULL DEFAULT 1.8,
            depth_m      REAL NOT NULL DEFAULT 2.05,
            puerta_m     REAL NOT NULL DEFAULT 0.8
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_elevators_code "
                    "ON elevators (project_id, code)")

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS parasols (
            {_columnas_comunes()},
            side            TEXT NOT NULL DEFAULT 'S',
            tipo            TEXT NOT NULL DEFAULT 'horizontal',
            material        TEXT NOT NULL DEFAULT 'aluminio',
            x               REAL NOT NULL DEFAULT 0.0,
            y               REAL NOT NULL DEFAULT 0.0,
            rotation_deg    REAL NOT NULL DEFAULT 0.0,
            length_m        REAL NOT NULL DEFAULT 1.0,
            profundidad_m   REAL NOT NULL DEFAULT 0.5,
            separacion_m    REAL NOT NULL DEFAULT 0.6,
            n_lamas         INTEGER NOT NULL DEFAULT 0,
            altura_inicio_m REAL NOT NULL DEFAULT 0.0,
            altura_fin_m    REAL NOT NULL DEFAULT 3.0
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_parasols_code "
                    "ON parasols (project_id, code)")

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS skins (
            {_columnas_comunes()},
            side         TEXT NOT NULL DEFAULT 'S',
            tipo         TEXT NOT NULL DEFAULT 'doble_piel_vidrio',
            material     TEXT NOT NULL DEFAULT 'vidrio',
            x            REAL NOT NULL DEFAULT 0.0,
            y            REAL NOT NULL DEFAULT 0.0,
            rotation_deg REAL NOT NULL DEFAULT 0.0,
            length_m     REAL NOT NULL DEFAULT 1.0,
            altura_m     REAL NOT NULL DEFAULT 3.0,
            separacion_m REAL NOT NULL DEFAULT 0.6
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_skins_code "
                    "ON skins (project_id, code)")


def downgrade(session: Session) -> None:
    session.execute("DROP TABLE IF EXISTS skins")
    session.execute("DROP TABLE IF EXISTS parasols")
    session.execute("DROP TABLE IF EXISTS elevators")
