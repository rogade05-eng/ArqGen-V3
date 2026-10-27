"""Repository for drawings and parametric doc templates (spec 68-70, 78)."""

from __future__ import annotations

from typing import List, Optional

from domain.documentation import Drawing, DocTemplate
from persistence.repositories.base import apply_common_fields, entity_common_row
from persistence.sqlite.connection import Session, json_dumps, json_loads


class DrawingRepository:
    """Mapper for the drawing register (one row per sheet)."""

    table = "drawings"

    def __init__(self, session: Session) -> None:
        self.session = session

    def to_row(self, e: Drawing) -> dict:
        return {**entity_common_row(e),
                "sheet": e.sheet, "sheet_size": e.sheet_size,
                "scale": e.scale, "orientation": e.orientation,
                "view": e.view, "level_id": e.level_id,
                "layers_json": json_dumps(e.layers),
                "annotations_json": json_dumps(e.annotations),
                "titleblock_json": json_dumps(e.titleblock)}

    def from_row(self, row) -> Drawing:
        e = Drawing(id=row["id"], sheet=row["sheet"],
                    sheet_size=row["sheet_size"], scale=row["scale"],
                    orientation=row["orientation"], view=row["view"],
                    level_id=row["level_id"],
                    layers=json_loads(row["layers_json"], []) or [],
                    annotations=json_loads(row["annotations_json"], []) or [],
                    titleblock=json_loads(row["titleblock_json"], {}) or {})
        apply_common_fields(e, row)
        return e

    def save(self, entity: Drawing) -> Drawing:
        data = self.to_row(entity)
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
        sql = (f"INSERT INTO {self.table} ({', '.join(columns)}) "
               f"VALUES ({placeholders}) "
               f"ON CONFLICT(id) DO UPDATE SET {updates}")
        self.session.execute(sql, tuple(data[c] for c in columns))
        return entity

    def get(self, entity_id: str) -> Optional[Drawing]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,))
        return self.from_row(row) if row else None

    def get_by_code(self, code: str) -> Optional[Drawing]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE code = ?", (code,))
        return self.from_row(row) if row else None

    def list(self, project_id: str, where: str = "", params: tuple = ()) -> List[Drawing]:
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

    def all_codes(self, project_id: str) -> List[str]:
        rows = self.session.query_all(
            f"SELECT code FROM {self.table} WHERE project_id = ?", (project_id,))
        return [r["code"] for r in rows if r["code"]]


class DocTemplateRepository:
    """Mapper for parametric document templates (spec 70)."""

    table = "doc_templates"

    def __init__(self, session: Session) -> None:
        self.session = session

    def to_row(self, e: DocTemplate) -> dict:
        return {**entity_common_row(e),
                "name": e.name, "body": e.body,
                "variables_json": json_dumps(e.variables),
                "sections_json": json_dumps(e.sections),
                "tables_json": json_dumps(e.tables),
                "styles_json": json_dumps(e.styles),
                "headers": e.headers, "footers": e.footers}

    def from_row(self, row) -> DocTemplate:
        e = DocTemplate(id=row["id"], name=row["name"], body=row["body"],
                        variables=json_loads(row["variables_json"], {}) or {},
                        sections=json_loads(row["sections_json"], []) or [],
                        tables=json_loads(row["tables_json"], []) or [],
                        styles=json_loads(row["styles_json"], {}) or {},
                        headers=row["headers"], footers=row["footers"])
        apply_common_fields(e, row)
        return e

    def save(self, entity: DocTemplate) -> DocTemplate:
        data = self.to_row(entity)
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "id")
        sql = (f"INSERT INTO {self.table} ({', '.join(columns)}) "
               f"VALUES ({placeholders}) "
               f"ON CONFLICT(id) DO UPDATE SET {updates}")
        self.session.execute(sql, tuple(data[c] for c in columns))
        return entity

    def get(self, entity_id: str) -> Optional[DocTemplate]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE id = ?", (entity_id,))
        return self.from_row(row) if row else None

    def get_by_code(self, code: str) -> Optional[DocTemplate]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE code = ?", (code,))
        return self.from_row(row) if row else None

    def get_by_name(self, name: str) -> Optional[DocTemplate]:
        row = self.session.query_one(
            f"SELECT * FROM {self.table} WHERE name = ?", (name,))
        return self.from_row(row) if row else None

    def list(self, project_id: str, where: str = "", params: tuple = ()) -> List[DocTemplate]:
        sql = f"SELECT * FROM {self.table} WHERE project_id = ?"
        parameters: list = [project_id]
        if where:
            sql += f" AND {where}"
            parameters.extend(params)
        sql += " ORDER BY name, created_at"
        return [self.from_row(r) for r in self.session.query_all(sql, tuple(parameters))]

    def delete(self, entity_id: str) -> bool:
        cursor = self.session.execute(
            f"DELETE FROM {self.table} WHERE id = ?", (entity_id,))
        return cursor.rowcount > 0

    def all_codes(self, project_id: str) -> List[str]:
        rows = self.session.query_all(
            f"SELECT code FROM {self.table} WHERE project_id = ?", (project_id,))
        return [r["code"] for r in rows if r["code"]]


__all__ = ["DrawingRepository", "DocTemplateRepository"]
