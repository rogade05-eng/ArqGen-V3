"""Migration 004_budget: resources, price history, budgets (spec 53-62)."""

from __future__ import annotations

from persistence.sqlite.connection import Session

version = 4
name = "budget"


def upgrade(session: Session) -> None:
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            code          TEXT NOT NULL,
            name          TEXT NOT NULL,
            type          TEXT NOT NULL DEFAULT 'MATERIAL',
            unit          TEXT NOT NULL DEFAULT '',
            category      TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            discipline    TEXT NOT NULL DEFAULT 'BUDGET',
            level_id      TEXT,
            status        TEXT NOT NULL DEFAULT 'ACTIVE',
            revision      INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_resources_code ON resources (project_id, code)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS price_lists (
            id         TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            code       TEXT NOT NULL,
            name       TEXT NOT NULL DEFAULT '',
            currency   TEXT NOT NULL DEFAULT 'CUP',
            region     TEXT NOT NULL DEFAULT ''
        )
        """
    )
    session.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_price_lists_code ON price_lists (project_id, code)")
    # Prices are append-only: history is never silently overwritten (spec 61).
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            resource_id   TEXT NOT NULL,
            price_list_id TEXT NOT NULL,
            price         REAL NOT NULL,
            currency      TEXT NOT NULL DEFAULT 'CUP',
            region        TEXT NOT NULL DEFAULT '',
            valid_from    TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            note          TEXT NOT NULL DEFAULT ''
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_prices_lookup ON prices (resource_id, price_list_id, valid_from)")
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS budgets (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            name          TEXT NOT NULL DEFAULT '',
            currency      TEXT NOT NULL DEFAULT 'CUP',
            indirect_pct  REAL NOT NULL DEFAULT 0,
            other_pct     REAL NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'DRAFT',
            ruleset_code  TEXT NOT NULL DEFAULT '',
            price_list_code TEXT NOT NULL DEFAULT '',
            direct_cost   REAL NOT NULL DEFAULT 0,
            indirect_cost REAL NOT NULL DEFAULT 0,
            other_cost    REAL NOT NULL DEFAULT 0,
            total_cost    REAL NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
        """
    )
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_chapters (
            id         TEXT PRIMARY KEY,
            budget_id  TEXT NOT NULL,
            code       TEXT NOT NULL DEFAULT '',
            name       TEXT NOT NULL DEFAULT '',
            parent_id  TEXT,
            position   INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_items (
            id            TEXT PRIMARY KEY,
            chapter_id    TEXT NOT NULL,
            code          TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            unit          TEXT NOT NULL DEFAULT '',
            quantity      REAL NOT NULL DEFAULT 0,
            performance   REAL NOT NULL DEFAULT 0,
            source        TEXT NOT NULL DEFAULT '',
            formula_code  TEXT NOT NULL DEFAULT '',
            direct_cost   REAL NOT NULL DEFAULT 0
        )
        """
    )
    session.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_item_resources (
            id          TEXT PRIMARY KEY,
            item_id     TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            factor      REAL NOT NULL DEFAULT 0,
            waste_pct   REAL NOT NULL DEFAULT 0,
            kind        TEXT NOT NULL DEFAULT 'MATERIAL'
        )
        """
    )
    session.execute("CREATE INDEX IF NOT EXISTS idx_items_chapter ON budget_items (chapter_id)")
    session.execute("CREATE INDEX IF NOT EXISTS idx_item_res_item ON budget_item_resources (item_id)")


def downgrade(session: Session) -> None:
    for sql in (
        "DROP TABLE IF EXISTS budget_item_resources",
        "DROP TABLE IF EXISTS budget_items",
        "DROP TABLE IF EXISTS budget_chapters",
        "DROP TABLE IF EXISTS budgets",
        "DROP TABLE IF EXISTS prices",
        "DROP TABLE IF EXISTS price_lists",
        "DROP TABLE IF EXISTS resources",
    ):
        session.execute(sql)
