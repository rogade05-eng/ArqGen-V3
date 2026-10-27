"""Repository base: explicit, typed entity↔row mapping (spec 78)."""

from __future__ import annotations

import sqlite3
from dataclasses import fields as dataclass_fields
from typing import Any, Dict, Generic, Iterable, List, Optional, Sequence, Type, TypeVar

from core.entities.base import Entity, EntityStatus, parse_datetime
from persistence.sqlite.connection import Session, json_dumps, json_loads

EntityT = TypeVar("EntityT", bound=Entity)


def entity_common_row(entity: Entity) -> Dict[str, Any]:
    return {
        "id": entity.id,
        "project_id": entity.project_id,
        "code": entity.code,
        "discipline": entity.discipline,
        "level_id": entity.level_id,
        "status": entity.status.value if isinstance(entity.status, EntityStatus) else str(entity.status),
        "revision": entity.revision,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
        "metadata_json": json_dumps(entity.metadata),
    }


def apply_common_fields(entity: Entity, row: sqlite3.Row) -> None:
    entity.project_id = row["project_id"]
    entity.code = row["code"]
    entity.discipline = row["discipline"]
    entity.level_id = row["level_id"]
    entity.status = EntityStatus(row["status"]) if row["status"] in EntityStatus._value2member_map_ else EntityStatus.DRAFT
    entity.revision = int(row["revision"])
    entity.created_at = parse_datetime(row["created_at"]) or entity.created_at
    entity.updated_at = parse_datetime(row["updated_at"]) or entity.updated_at
    entity.metadata = json_loads(row["metadata_json"], {}) or {}


class EntityMapper(Generic[EntityT]):
    """Explicit mapper for one entity type against one table."""

    table: str = ""
    columns: Sequence[str] = ()
    entity_class: Type[EntityT]

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- to be overridden ----------------------------------------------
    def to_row(self, entity: EntityT) -> Dict[str, Any]:
        raise NotImplementedError

    def from_row(self, row: sqlite3.Row) -> EntityT:
        raise NotImplementedError

    # -- generic CRUD ----------------------------------------------------
    def save(self, entity: EntityT) -> EntityT:
        data = self.to_row(entity)
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
        sql = (
            f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self.session.execute(sql, tuple(data[c] for c in columns))
        return entity

    def get(self, entity_id: str) -> Optional[EntityT]:
        row = self.session.query_one(f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,))
        return self.from_row(row) if row else None

    def get_by_code(self, code: str) -> Optional[EntityT]:
        row = self.session.query_one(f"SELECT * FROM {self.table} WHERE code = ?", (code,))
        return self.from_row(row) if row else None

    def list(self, project_id: str, where: str = "", params: tuple = ()) -> List[EntityT]:
        sql = f"SELECT * FROM {self.table} WHERE project_id = ?"
        parameters: list[Any] = [project_id]
        if where:
            sql += f" AND {where}"
            parameters.extend(params)
        sql += " ORDER BY code, created_at"
        return [self.from_row(r) for r in self.session.query_all(sql, tuple(parameters))]

    def delete(self, entity_id: str) -> bool:
        cursor = self.session.execute(f"DELETE FROM {self.table} WHERE id = ?", (entity_id,))
        return cursor.rowcount > 0

    def count(self, project_id: str) -> int:
        row = self.session.query_one(f"SELECT COUNT(*) AS n FROM {self.table} WHERE project_id = ?", (project_id,))
        return int(row["n"]) if row else 0

    def all_codes(self, project_id: str) -> List[str]:
        rows = self.session.query_all(f"SELECT code FROM {self.table} WHERE project_id = ?", (project_id,))
        return [r["code"] for r in rows if r["code"]]


__all__ = ["EntityMapper", "entity_common_row", "apply_common_fields"]
