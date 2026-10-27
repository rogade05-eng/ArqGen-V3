"""Repositories for the architecture domain entities (spec section 20)."""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Type

from domain.model import (
    Building, Door, Elevator, FacadeSkin, Furniture, Handrail, Level,
    Opening, Parasol, Project, Ramp, Roof, Site, Space,
    SpaceRelationship, Stair, Wall, Window, Zone,
)
from persistence.repositories.base import EntityMapper, apply_common_fields, entity_common_row
from persistence.sqlite.connection import Session, json_dumps, json_loads


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    _COLS = (
        "id, name, client, address, description, units_length, ruleset_code, currency, "
        "code, discipline, level_id, status, revision, created_at, updated_at, metadata_json"
    )

    def save(self, project: Project) -> Project:
        row = {
            "id": project.id, "name": project.name, "client": project.client,
            "address": project.address, "description": project.description,
            "units_length": project.units_length, "ruleset_code": project.ruleset_code,
            "currency": project.currency,
            "code": project.code, "discipline": project.discipline,
            "level_id": project.level_id,
            "status": project.status.value if hasattr(project.status, "value") else str(project.status),
            "revision": project.revision,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "metadata_json": json_dumps(project.metadata),
        }
        self.session.execute(
            f"INSERT INTO projects ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)}) "
            f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in row if c != 'id')}",
            tuple(row.values()),
        )
        return project

    def get(self, project_id: str) -> Optional[Project]:
        row = self.session.query_one(f"SELECT {self._COLS} FROM projects WHERE id = ?", (project_id,))
        return self._from_row(row) if row else None

    def get_first(self) -> Optional[Project]:
        row = self.session.query_one(f"SELECT {self._COLS} FROM projects ORDER BY created_at LIMIT 1")
        return self._from_row(row) if row else None

    def exists(self) -> bool:
        row = self.session.query_one("SELECT 1 AS x FROM projects LIMIT 1")
        return row is not None

    def delete(self, project_id: str) -> bool:
        cursor = self.session.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cursor.rowcount > 0

    def _from_row(self, row: sqlite3.Row) -> Project:
        from core.entities.base import EntityStatus, parse_datetime
        project = Project(
            id=row["id"], name=row["name"], client=row["client"], address=row["address"],
            description=row["description"], units_length=row["units_length"],
            ruleset_code=row["ruleset_code"], currency=row["currency"],
        )
        project.code = row["code"]
        project.discipline = row["discipline"]
        project.level_id = row["level_id"]
        project.status = EntityStatus(row["status"]) if row["status"] in EntityStatus._value2member_map_ else EntityStatus.DRAFT
        project.revision = int(row["revision"])
        project.created_at = parse_datetime(row["created_at"]) or project.created_at
        project.updated_at = parse_datetime(row["updated_at"]) or project.updated_at
        project.metadata = json_loads(row["metadata_json"], {}) or {}
        return project


class SiteRepository(EntityMapper[Site]):
    table = "sites"
    entity_class = Site

    def to_row(self, e: Site) -> dict:
        return {**entity_common_row(e), "name": e.name, "area_m2": e.area_m2,
                "boundary_json": json_dumps(e.boundary)}

    def from_row(self, row: sqlite3.Row) -> Site:
        e = Site(id=row["id"], name=row["name"], area_m2=row["area_m2"],
                 boundary=json_loads(row["boundary_json"]))
        apply_common_fields(e, row)
        return e


class BuildingRepository(EntityMapper[Building]):
    table = "buildings"
    entity_class = Building

    def to_row(self, e: Building) -> dict:
        return {**entity_common_row(e), "site_id": e.site_id, "name": e.name,
                "floors": e.floors, "description": e.description}

    def from_row(self, row: sqlite3.Row) -> Building:
        e = Building(id=row["id"], site_id=row["site_id"], name=row["name"],
                     floors=int(row["floors"]), description=row["description"])
        apply_common_fields(e, row)
        return e


class LevelRepository(EntityMapper[Level]):
    table = "levels"
    entity_class = Level

    def to_row(self, e: Level) -> dict:
        return {**entity_common_row(e), "building_id": e.building_id, "name": e.name,
                "elevation_m": e.elevation_m, "height_m": e.height_m}

    def from_row(self, row: sqlite3.Row) -> Level:
        e = Level(id=row["id"], building_id=row["building_id"], name=row["name"],
                  elevation_m=row["elevation_m"], height_m=row["height_m"])
        apply_common_fields(e, row)
        return e


class ZoneRepository(EntityMapper[Zone]):
    table = "zones"
    entity_class = Zone

    def to_row(self, e: Zone) -> dict:
        return {**entity_common_row(e), "name": e.name, "kind": e.kind}

    def from_row(self, row: sqlite3.Row) -> Zone:
        e = Zone(id=row["id"], name=row["name"], kind=row["kind"])
        apply_common_fields(e, row)
        return e


class SpaceRepository(EntityMapper[Space]):
    table = "spaces"
    entity_class = Space

    def to_row(self, e: Space) -> dict:
        return {**entity_common_row(e), "zone_id": e.zone_id, "name": e.name,
                "space_type": e.space_type, "boundary_json": json_dumps(e.boundary)}

    def from_row(self, row: sqlite3.Row) -> Space:
        e = Space(id=row["id"], zone_id=row["zone_id"], name=row["name"],
                  space_type=row["space_type"],
                  boundary=[tuple(p) for p in json_loads(row["boundary_json"], [])])
        apply_common_fields(e, row)
        return e


class WallRepository(EntityMapper[Wall]):
    table = "walls"
    entity_class = Wall

    def to_row(self, e: Wall) -> dict:
        return {**entity_common_row(e), "start_json": json_dumps(list(e.start)),
                "end_json": json_dumps(list(e.end)), "thickness_m": e.thickness_m,
                "height_m": e.height_m, "base_offset_m": e.base_offset_m,
                "material_id": e.material_id, "structural": 1 if e.structural else 0}

    def from_row(self, row: sqlite3.Row) -> Wall:
        e = Wall(id=row["id"], level_id=row["level_id"],
                 start=tuple(json_loads(row["start_json"], [0, 0])),
                 end=tuple(json_loads(row["end_json"], [0, 0])),
                 thickness_m=row["thickness_m"], height_m=row["height_m"],
                 base_offset_m=row["base_offset_m"], material_id=row["material_id"],
                 structural=bool(row["structural"]))
        apply_common_fields(e, row)
        return e


class OpeningRepository(EntityMapper[Opening]):
    table = "openings"
    entity_class = Opening

    def to_row(self, e: Opening) -> dict:
        return {**entity_common_row(e), "wall_id": e.wall_id, "kind": e.kind,
                "width_m": e.width_m, "height_m": e.height_m, "offset_m": e.offset_m,
                "sill_height_m": e.sill_height_m, "swing": e.swing,
                "material_id": e.material_id}

    def from_row(self, row: sqlite3.Row) -> Opening:
        kind = row["kind"]
        cls: Type[Opening] = {"DOOR": Door, "WINDOW": Window}.get(kind, Opening)
        e = cls(id=row["id"], level_id=row["level_id"], wall_id=row["wall_id"],
                kind=kind, width_m=row["width_m"], height_m=row["height_m"],
                offset_m=row["offset_m"], sill_height_m=row["sill_height_m"],
                swing=row["swing"], material_id=row["material_id"])
        apply_common_fields(e, row)
        return e


class SpaceRelationshipRepository(EntityMapper[SpaceRelationship]):
    table = "space_relationships"
    entity_class = SpaceRelationship

    def to_row(self, e: SpaceRelationship) -> dict:
        return {**entity_common_row(e), "from_space_id": e.from_space_id,
                "to_space_id": e.to_space_id, "kind": e.kind, "source": e.source}

    def from_row(self, row: sqlite3.Row) -> SpaceRelationship:
        e = SpaceRelationship(id=row["id"], from_space_id=row["from_space_id"],
                              to_space_id=row["to_space_id"], kind=row["kind"],
                              source=row["source"])
        apply_common_fields(e, row)
        return e


class FurnitureRepository(EntityMapper[Furniture]):
    table = "furniture"
    entity_class = Furniture

    def to_row(self, e: Furniture) -> dict:
        return {**entity_common_row(e), "space_id": e.space_id, "kind": e.kind,
                "name": e.name, "x": e.x, "y": e.y,
                "rotation_deg": e.rotation_deg, "width_m": e.width_m,
                "depth_m": e.depth_m, "height_m": e.height_m}

    def from_row(self, row: sqlite3.Row) -> Furniture:
        e = Furniture(id=row["id"], level_id=row["level_id"],
                      space_id=row["space_id"], kind=row["kind"],
                      name=row["name"], x=row["x"], y=row["y"],
                      rotation_deg=row["rotation_deg"],
                      width_m=row["width_m"], depth_m=row["depth_m"],
                      height_m=row["height_m"])
        apply_common_fields(e, row)
        return e


class RoofRepository(EntityMapper[Roof]):
    table = "roofs"
    entity_class = Roof

    def to_row(self, e: Roof) -> dict:
        ridge_json = json_dumps(list(e.ridge)) if e.ridge else "null"
        return {**entity_common_row(e), "tipologia": e.tipologia,
                "material": e.material, "estructura": e.estructura,
                "pendiente_pct": e.pendiente_pct, "alero_m": e.alero_m,
                "altura_cumbrera_m": e.altura_cumbrera_m,
                "footprint_json": json_dumps(e.footprint),
                "ridge_json": ridge_json}

    def from_row(self, row: sqlite3.Row) -> Roof:
        ridge = json_loads(row["ridge_json"], None)
        if ridge is not None:
            ridge = (tuple(ridge[0]), tuple(ridge[1]))
        e = Roof(id=row["id"], level_id=row["level_id"],
                 tipologia=row["tipologia"], material=row["material"],
                 estructura=row["estructura"],
                 pendiente_pct=row["pendiente_pct"], alero_m=row["alero_m"],
                 altura_cumbrera_m=row["altura_cumbrera_m"],
                 footprint=[tuple(p) for p in
                            json_loads(row["footprint_json"], [])],
                 ridge=ridge)
        apply_common_fields(e, row)
        return e


class RampRepository(EntityMapper[Ramp]):
    table = "ramps"
    entity_class = Ramp

    def to_row(self, e: Ramp) -> dict:
        return {**entity_common_row(e), "space_id": e.space_id,
                "width_m": e.width_m, "length_m": e.length_m,
                "desnivel_m": e.desnivel_m, "slope_pct": e.slope_pct,
                "corners_json": json_dumps(e.corners)}

    def from_row(self, row: sqlite3.Row) -> Ramp:
        e = Ramp(id=row["id"], level_id=row["level_id"],
                 space_id=row["space_id"], width_m=row["width_m"],
                 length_m=row["length_m"], desnivel_m=row["desnivel_m"],
                 slope_pct=row["slope_pct"],
                 corners=[tuple(p) for p in
                          json_loads(row["corners_json"], [])])
        apply_common_fields(e, row)
        return e


class HandrailRepository(EntityMapper[Handrail]):
    table = "handrails"
    entity_class = Handrail

    def to_row(self, e: Handrail) -> dict:
        return {**entity_common_row(e), "space_id": e.space_id,
                "kind": e.kind, "points_json": json_dumps(e.points),
                "altura_m": e.altura_m,
                "altura_secundaria_m": e.altura_secundaria_m}

    def from_row(self, row: sqlite3.Row) -> Handrail:
        e = Handrail(id=row["id"], level_id=row["level_id"],
                     space_id=row["space_id"], kind=row["kind"],
                     points=[tuple(p) for p in
                             json_loads(row["points_json"], [])],
                     altura_m=row["altura_m"],
                     altura_secundaria_m=row["altura_secundaria_m"])
        apply_common_fields(e, row)
        return e


class ElevatorRepository(EntityMapper[Elevator]):
    table = "elevators"
    entity_class = Elevator

    def to_row(self, e: Elevator) -> dict:
        return {**entity_common_row(e), "tipo": e.tipo,
                "capacidad_kg": e.capacidad_kg, "personas": e.personas,
                "x": e.x, "y": e.y, "rotation_deg": e.rotation_deg,
                "width_m": e.width_m, "depth_m": e.depth_m,
                "puerta_m": e.puerta_m}

    def from_row(self, row: sqlite3.Row) -> Elevator:
        e = Elevator(id=row["id"], level_id=row["level_id"],
                     tipo=row["tipo"], capacidad_kg=int(row["capacidad_kg"]),
                     personas=int(row["personas"]), x=row["x"], y=row["y"],
                     rotation_deg=row["rotation_deg"],
                     width_m=row["width_m"], depth_m=row["depth_m"],
                     puerta_m=row["puerta_m"])
        apply_common_fields(e, row)
        return e


class ParasolRepository(EntityMapper[Parasol]):
    table = "parasols"
    entity_class = Parasol

    def to_row(self, e: Parasol) -> dict:
        return {**entity_common_row(e), "side": e.side, "tipo": e.tipo,
                "material": e.material, "x": e.x, "y": e.y,
                "rotation_deg": e.rotation_deg, "length_m": e.length_m,
                "profundidad_m": e.profundidad_m,
                "separacion_m": e.separacion_m, "n_lamas": e.n_lamas,
                "altura_inicio_m": e.altura_inicio_m,
                "altura_fin_m": e.altura_fin_m}

    def from_row(self, row: sqlite3.Row) -> Parasol:
        e = Parasol(id=row["id"], level_id=row["level_id"],
                    side=row["side"], tipo=row["tipo"],
                    material=row["material"], x=row["x"], y=row["y"],
                    rotation_deg=row["rotation_deg"],
                    length_m=row["length_m"],
                    profundidad_m=row["profundidad_m"],
                    separacion_m=row["separacion_m"],
                    n_lamas=int(row["n_lamas"]),
                    altura_inicio_m=row["altura_inicio_m"],
                    altura_fin_m=row["altura_fin_m"])
        apply_common_fields(e, row)
        return e


class StairRepository(EntityMapper[Stair]):
    table = "stairs"
    entity_class = Stair

    def to_row(self, e: Stair) -> dict:
        return {**entity_common_row(e), "space_id": e.space_id,
                "tipo": e.tipo, "x": e.x, "y": e.y,
                "rotation_deg": e.rotation_deg, "width_m": e.width_m,
                "desnivel_m": e.desnivel_m,
                "contrahuella_m": e.contrahuella_m,
                "huella_m": e.huella_m}

    def from_row(self, row: sqlite3.Row) -> Stair:
        e = Stair(id=row["id"], level_id=row["level_id"],
                  space_id=row["space_id"], tipo=row["tipo"],
                  x=row["x"], y=row["y"], rotation_deg=row["rotation_deg"],
                  width_m=row["width_m"], desnivel_m=row["desnivel_m"],
                  contrahuella_m=row["contrahuella_m"],
                  huella_m=row["huella_m"])
        apply_common_fields(e, row)
        return e


class FacadeSkinRepository(EntityMapper[FacadeSkin]):
    table = "skins"
    entity_class = FacadeSkin

    def to_row(self, e: FacadeSkin) -> dict:
        return {**entity_common_row(e), "side": e.side, "tipo": e.tipo,
                "material": e.material, "x": e.x, "y": e.y,
                "rotation_deg": e.rotation_deg, "length_m": e.length_m,
                "altura_m": e.altura_m, "separacion_m": e.separacion_m}

    def from_row(self, row: sqlite3.Row) -> FacadeSkin:
        e = FacadeSkin(id=row["id"], level_id=row["level_id"],
                       side=row["side"], tipo=row["tipo"],
                       material=row["material"], x=row["x"], y=row["y"],
                       rotation_deg=row["rotation_deg"],
                       length_m=row["length_m"], altura_m=row["altura_m"],
                       separacion_m=row["separacion_m"])
        apply_common_fields(e, row)
        return e


class ArchitectureRepository:
    """Facade over all architecture repositories with a typed registry."""

    OPENING_KIND_FILTER = {"DOOR": "DOOR", "WINDOW": "WINDOW"}
    # Note: entity_type "OPENING" is the superset (all kinds) and needs no filter.

    def __init__(self, session: Session) -> None:
        self.projects = ProjectRepository(session)
        self._mappers: Dict[str, EntityMapper] = {
            "SITE": SiteRepository(session),
            "BUILDING": BuildingRepository(session),
            "LEVEL": LevelRepository(session),
            "ZONE": ZoneRepository(session),
            "SPACE": SpaceRepository(session),
            "WALL": WallRepository(session),
            "DOOR": OpeningRepository(session),
            "WINDOW": OpeningRepository(session),
            "OPENING": OpeningRepository(session),
            "SPACE_RELATIONSHIP": SpaceRelationshipRepository(session),
            # Concepción de espacios (v3.15.0)
            "FURNITURE": FurnitureRepository(session),
            "ROOF": RoofRepository(session),
            "RAMP": RampRepository(session),
            "HANDRAIL": HandrailRepository(session),
            # Ascensores y fachada (v3.18.0)
            "ELEVATOR": ElevatorRepository(session),
            "PARASOL": ParasolRepository(session),
            "SKIN": FacadeSkinRepository(session),
            # Escaleras por tipología (v3.19.0)
            "STAIR": StairRepository(session),
        }

    @property
    def session(self) -> Session:
        return self.projects.session

    def mapper_for(self, entity_type: str) -> EntityMapper:
        mapper = self._mappers.get(entity_type)
        if mapper is None:
            raise KeyError(f"Sin repositorio para el tipo: {entity_type}")
        return mapper

    def _kind_filter(self, entity_type: str, where: str, params: tuple) -> tuple[str, tuple]:
        """DOOR/WINDOW/OPENING share one table: filter by kind column."""
        kind = self.OPENING_KIND_FILTER.get(entity_type)
        if kind is None:
            return where, params
        clause = "kind = ?"
        where = f"{where} AND {clause}" if where else clause
        return where, tuple(params) + (kind,)

    def save(self, entity) -> object:
        return self.mapper_for(entity.ENTITY_TYPE).save(entity)

    def get(self, entity_type: str, entity_id: str):
        entity = self.mapper_for(entity_type).get(entity_id)
        if entity is not None and entity_type in self.OPENING_KIND_FILTER:
            if entity.kind != entity_type:
                return None
        return entity

    def get_by_code(self, entity_type: str, code: str):
        entity = self.mapper_for(entity_type).get_by_code(code)
        if entity is not None and entity_type in self.OPENING_KIND_FILTER:
            if entity.kind != entity_type:
                return None
        return entity

    def list(self, entity_type: str, project_id: str, where: str = "", params: tuple = ()) -> list:
        where, params = self._kind_filter(entity_type, where, params)
        rows = self.mapper_for(entity_type).list(project_id, where, params)
        return rows

    def delete(self, entity_type: str, entity_id: str) -> bool:
        return self.mapper_for(entity_type).delete(entity_id)

    def count(self, entity_type: str, project_id: str) -> int:
        where, params = self._kind_filter(entity_type, "", ())
        row = self.session.query_one(
            f"SELECT COUNT(*) AS n FROM {self.mapper_for(entity_type).table} "
            f"WHERE project_id = ?" + (f" AND {where}" if where else ""),
            (project_id,) + params)
        return int(row["n"]) if row else 0

    def all_codes(self, project_id: str) -> List[str]:
        codes: set[str] = set()
        for entity_type, mapper in self._mappers.items():
            where, params = self._kind_filter(entity_type, "", ())
            sql = f"SELECT code FROM {mapper.table} WHERE project_id = ?"
            values: tuple = (project_id,)
            if where:
                sql += f" AND {where}"
                values = values + params
            for row in self.session.query_all(sql, values):
                if row["code"]:
                    codes.add(row["code"])
        return sorted(codes)

    def entity_counts(self, project_id: str) -> dict:
        return {t: self.count(t, project_id) for t in self._mappers}


__all__ = [
    "ArchitectureRepository", "ProjectRepository", "SiteRepository",
    "BuildingRepository", "LevelRepository", "ZoneRepository", "SpaceRepository",
    "WallRepository", "OpeningRepository", "SpaceRelationshipRepository",
    "FurnitureRepository", "RoofRepository", "RampRepository", "HandrailRepository",
    "ElevatorRepository", "ParasolRepository", "FacadeSkinRepository",
    "StairRepository",
]
