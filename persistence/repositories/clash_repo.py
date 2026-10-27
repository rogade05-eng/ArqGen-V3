"""Repository for the coordination clash register (spec sections 35, 36, 78)."""

from __future__ import annotations

from typing import List, Optional

from domain.clash import Clash
from persistence.repositories.base import apply_common_fields, entity_common_row
from persistence.sqlite.connection import Session, json_dumps, json_loads


class ClashRepository:
    """Mapper for the clash register (status column stores lifecycle)."""

    table = "clashes"

    def __init__(self, session: Session) -> None:
        self.session = session

    def to_row(self, e: Clash) -> dict:
        return {**entity_common_row(e),
                "object_a_type": e.object_a_type, "object_a_id": e.object_a_id,
                "object_a_code": e.object_a_code,
                "object_b_type": e.object_b_type, "object_b_id": e.object_b_id,
                "object_b_code": e.object_b_code,
                "type": e.type, "severity": e.severity, "rule": e.rule,
                "location_x": e.location[0], "location_y": e.location[1],
                "level_id": e.level_id, "distance": e.distance,
                "status": e.status, "resolved_at": e.resolved_at,
                "notes": e.notes}

    def from_row(self, row) -> Clash:
        e = Clash(id=row["id"],
                  object_a_type=row["object_a_type"], object_a_id=row["object_a_id"],
                  object_a_code=row["object_a_code"],
                  object_b_type=row["object_b_type"], object_b_id=row["object_b_id"],
                  object_b_code=row["object_b_code"],
                  type=row["type"], severity=row["severity"], rule=row["rule"],
                  location=(row["location_x"], row["location_y"]),
                  distance=row["distance"],
                  resolved_at=row["resolved_at"], notes=row["notes"])
        apply_common_fields(e, row)
        # El estado de la interferencia (spec 36) viaja en la columna status.
        e.status = row["status"]
        return e

    def save(self, entity: Clash) -> Clash:
        data = self.to_row(entity)
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
        sql = (f"INSERT INTO {self.table} ({', '.join(columns)}) "
               f"VALUES ({placeholders}) "
               f"ON CONFLICT(id) DO UPDATE SET {updates}")
        self.session.execute(sql, tuple(data[c] for c in columns))
        return entity

    def get(self, entity_id: str) -> Optional[Clash]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,))
        return self.from_row(row) if row else None

    def get_by_code(self, code: str) -> Optional[Clash]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE code = ?", (code,))
        return self.from_row(row) if row else None

    def list(self, project_id: str, where: str = "", params: tuple = ()) -> List[Clash]:
        sql = f"SELECT * FROM {self.table} WHERE project_id = ?"
        parameters: list = [project_id]
        if where:
            sql += f" AND {where}"
            parameters.extend(params)
        sql += " ORDER BY code, created_at"
        return [self.from_row(r) for r in self.session.query_all(sql, tuple(parameters))]

    def delete(self, entity_id: str) -> bool:
        cursor = self.session.execute(
            f"DELETE FROM {self.table} WHERE id = ?", (entity_id,))
        return cursor.rowcount > 0

    def count(self, project_id: str) -> int:
        row = self.session.query_one(
            f"SELECT COUNT(*) AS n FROM {self.table} WHERE project_id = ?",
            (project_id,))
        return int(row["n"]) if row else 0

    def find_pair(self, project_id: str, a_id: str, b_id: str,
                  clash_type: str) -> Optional[Clash]:
        """Existing clash for the same object pair and type (deduplication)."""
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE project_id = ? AND type = ? "
            "AND ((object_a_id = ? AND object_b_id = ?) "
            "OR (object_a_id = ? AND object_b_id = ?))",
            (project_id, clash_type, a_id, b_id, b_id, a_id))
        return self.from_row(row) if row else None

    def all_codes(self, project_id: str) -> List[str]:
        rows = self.session.query_all(
            f"SELECT code FROM {self.table} WHERE project_id = ?", (project_id,))
        return [r["code"] for r in rows if r["code"]]

    def status_counts(self, project_id: str) -> dict:
        rows = self.session.query_all(
            "SELECT status, COUNT(*) AS n FROM clashes WHERE project_id = ? "
            "GROUP BY status", (project_id,))
        return {r["status"]: int(r["n"]) for r in rows}


__all__ = ["ClashRepository"]
