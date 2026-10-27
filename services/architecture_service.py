"""ArchitectureService (spec sections 20, 76, 99).

All mutations go through the CommandBus, emit events, write the audit
trail and trigger incremental invalidation. Example of propagation:
move a door → Space → Wall opening → QTO → Budget (spec 99).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.entities.base import new_uuid, utc_now
from core.errors import DomainError
from core.geometry.primitives import Point, Polygon
from domain.model import (
    Building, Door, Level, Opening, Site, Space, SpaceRelationship, Wall, Window, Zone,
)
from services.commands_impl import (
    CreateEntityCommand, DeleteEntityCommand, UpdateEntityCommand, entity_snapshot,
)
from services.context import ProjectContext


class ArchitectureService:
    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context
        self.arch = context.architecture

    # -- helpers -----------------------------------------------------------
    def _audit(self, command: str, entity_type: str, entity_id: str,
               old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]],
               reason: str = "", result: str = "OK") -> None:
        from core.audit.models import make_audit_event
        event = make_audit_event(self.ctx.user, entity_id, entity_type, command, old, new, reason, result)
        self.ctx.audit_repo.append(event)

    def _finish(self, command_name: str, entity, old_snapshot: Optional[Dict[str, Any]] = None,
                events: Optional[List[Tuple[str, Dict[str, Any]]]] = None) -> Any:
        new_snapshot = entity_snapshot(entity)
        self._audit(command_name, entity.ENTITY_TYPE, entity.id, old_snapshot, new_snapshot)
        for event_type, payload in events or []:
            self.ctx.emit(event_type, {"id": entity.id, "type": entity.ENTITY_TYPE,
                                       "code": entity.code, **payload})
        self._invalidate_object(entity.id)
        return entity

    def _invalidate_object(self, object_id: str) -> int:
        """Mark stale every calculation/quantity that used this object."""
        count = self.ctx.calculations_repo.mark_stale_for_object(object_id)
        count += self.ctx.quantities_repo.mark_stale_for_object(object_id)
        return count

    # -- site / building / level -------------------------------------------
    def create_site(self, name: str, area_m2: float = 0.0) -> Site:
        site = Site(project_id=self.ctx.project.id, code=self.ctx.next_code("ARCHITECTURE", "SITE"),
                    name=name, area_m2=area_m2)
        self.ctx.command_bus.execute(CreateEntityCommand(site), self.ctx)
        return self._finish("CREATE_ENTITY", site, events=[("OBJECT_CREATED", {})])

    def create_building(self, name: str, site_id: Optional[str] = None, floors: int = 1) -> Building:
        if site_id and not self.arch.get("SITE", site_id):
            raise DomainError(message=f"El terreno indicado no existe: {site_id}", code="ARQ-DOM-042")
        building = Building(project_id=self.ctx.project.id, site_id=site_id,
                            code=self.ctx.next_code("ARCHITECTURE", "BUILDING"),
                            name=name, floors=floors)
        self.ctx.command_bus.execute(CreateEntityCommand(building), self.ctx)
        return self._finish("CREATE_ENTITY", building, events=[("OBJECT_CREATED", {})])

    def create_level(self, name: str, elevation_m: float = 0.0, height_m: float = 3.0,
                     building_id: Optional[str] = None) -> Level:
        level = Level(project_id=self.ctx.project.id, building_id=building_id,
                      code=self.ctx.next_code("ARCHITECTURE", "LEVEL"),
                      name=name, elevation_m=elevation_m, height_m=height_m)
        self.ctx.command_bus.execute(CreateEntityCommand(level), self.ctx)
        return self._finish("CREATE_ENTITY", level, events=[("OBJECT_CREATED", {})])

    def get_level_by_name_or_code(self, ref: str) -> Level:
        level = self.arch.get_by_code("LEVEL", ref)
        if level is None:
            for candidate in self.arch.list("LEVEL", self.ctx.project.id):
                if candidate.name.lower() == ref.lower():
                    level = candidate
                    break
        if level is None:
            raise DomainError(
                message=f"Nivel no encontrado: {ref}",
                code="ARQ-DOM-043",
                suggested_action="Liste los niveles con 'level list'.",
            )
        return level

    # -- zones ---------------------------------------------------------------
    def create_zone(self, name: str, kind: str) -> Zone:
        zone = Zone(project_id=self.ctx.project.id,
                    code=self.ctx.next_code("ARCHITECTURE", "ZONE"), name=name, kind=kind)
        self.ctx.command_bus.execute(CreateEntityCommand(zone), self.ctx)
        return self._finish("CREATE_ENTITY", zone, events=[("OBJECT_CREATED", {})])

    def set_space_zone(self, space_ref: str, zone_id: str) -> Space:
        space = self._resolve_space(space_ref)
        if not self.arch.get("ZONE", zone_id):
            raise DomainError(message=f"Zona inexistente: {zone_id}", code="ARQ-DOM-044")
        old_snapshot = entity_snapshot(space)
        space.zone_id = zone_id
        space.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(space), self.ctx)
        return self._finish("UPDATE_ENTITY", space, old_snapshot,
                            events=[("SPACE_CHANGED", {"zone_id": zone_id})])

    # -- spaces ---------------------------------------------------------------
    def create_space(self, level_ref: str, name: str, space_type: str,
                     boundary: List[Tuple[float, float]]) -> Space:
        level = self.get_level_by_name_or_code(level_ref)
        if len(boundary) < 3:
            raise DomainError(
                message="El local requiere al menos 3 vértices de contorno",
                code="ARQ-DOM-045",
            )
        Polygon([Point(x, y) for x, y in boundary])  # validates geometry
        space = Space(project_id=self.ctx.project.id, level_id=level.id,
                      code=self.ctx.next_code("ARCHITECTURE", "SPACE"),
                      name=name, space_type=space_type, boundary=[tuple(p) for p in boundary])
        self.ctx.command_bus.execute(CreateEntityCommand(space), self.ctx)
        return self._finish("CREATE_ENTITY", space, events=[("SPACE_CHANGED", {})])

    def _resolve_space(self, ref: str) -> Space:
        space = self.arch.get_by_code("SPACE", ref)
        if space is None:
            for candidate in self.arch.list("SPACE", self.ctx.project.id):
                if candidate.name.lower() == ref.lower() or candidate.id == ref:
                    space = candidate
                    break
        if space is None:
            raise DomainError(message=f"Local no encontrado: {ref}", code="ARQ-DOM-046")
        return space

    # -- walls -----------------------------------------------------------------
    def create_wall(self, level_ref: str, start: Tuple[float, float], end: Tuple[float, float],
                    thickness_m: float = 0.2, height_m: Optional[float] = None,
                    material_id: Optional[str] = None, structural: bool = False) -> Wall:
        level = self.get_level_by_name_or_code(level_ref)
        if thickness_m <= 0:
            raise DomainError(message="El espesor del muro debe ser positivo", code="ARQ-DOM-047")
        from core.geometry.primitives import Point
        p1, p2 = Point(*start), Point(*end)
        if p1.distance_to(p2) < 1e-6:
            raise DomainError(message="El muro tiene longitud nula", code="ARQ-DOM-048")
        height = height_m if height_m is not None else level.height_m
        wall = Wall(project_id=self.ctx.project.id, level_id=level.id,
                    code=self.ctx.next_code("ARCHITECTURE", "WALL"),
                    start=tuple(start), end=tuple(end), thickness_m=thickness_m,
                    height_m=height, material_id=material_id, structural=structural)
        self.ctx.command_bus.execute(CreateEntityCommand(wall), self.ctx)
        self.ctx.emit("GEOMETRY_CHANGED", {"id": wall.id, "type": "WALL", "code": wall.code})
        return self._finish("CREATE_ENTITY", wall, events=[("OBJECT_CREATED", {})])

    def move_wall(self, wall_ref: str, start: Tuple[float, float], end: Tuple[float, float]) -> Wall:
        wall = self._resolve_wall(wall_ref)
        old_snapshot = entity_snapshot(wall)
        wall.start, wall.end = tuple(start), tuple(end)
        wall.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(wall), self.ctx)
        return self._finish("UPDATE_ENTITY", wall, old_snapshot,
                            events=[("GEOMETRY_CHANGED", {})])

    def _resolve_wall(self, ref: str) -> Wall:
        wall = self.arch.get_by_code("WALL", ref)
        if wall is None and ref:
            for candidate in self.arch.list("WALL", self.ctx.project.id):
                if candidate.id == ref:
                    wall = candidate
                    break
        if wall is None:
            raise DomainError(message=f"Muro no encontrado: {ref}", code="ARQ-DOM-049")
        return wall

    # -- openings ------------------------------------------------------------
    def create_opening(self, kind: str, wall_ref: str, width_m: float, height_m: float,
                       offset_m: float = 0.0, sill_height_m: float = 0.0,
                       swing: str = "LEFT") -> Opening:
        wall = self._resolve_wall(wall_ref)
        if offset_m < 0:
            raise DomainError(message="El offset del vano no puede ser negativo", code="ARQ-DOM-050")
        if offset_m + width_m > wall.length_m + 1e-9:
            raise DomainError(
                message=f"El vano no cabe en el muro: offset {offset_m:.2f} + ancho {width_m:.2f} "
                        f"> longitud {wall.length_m:.2f}",
                code="ARQ-DOM-051",
                object_ids=[wall.id],
            )
        if height_m > wall.height_m + 1e-9:
            raise DomainError(
                message=f"La altura del vano ({height_m:.2f}) excede la altura del muro ({wall.height_m:.2f})",
                code="ARQ-DOM-052",
                object_ids=[wall.id],
            )
        cls = Door if kind.upper() == "DOOR" else Window if kind.upper() == "WINDOW" else Opening
        code_type = kind.upper()
        opening = cls(project_id=self.ctx.project.id, level_id=wall.level_id, wall_id=wall.id,
                      code=self.ctx.next_code("ARCHITECTURE", code_type),
                      width_m=width_m, height_m=height_m, offset_m=offset_m,
                      sill_height_m=sill_height_m, swing=swing)
        self.ctx.command_bus.execute(CreateEntityCommand(opening), self.ctx)
        return self._finish("CREATE_ENTITY", opening, events=[("OBJECT_CREATED", {})])

    def move_opening(self, opening_ref: str, offset_m: float) -> Opening:
        opening = self.arch.get_by_code("OPENING", opening_ref)
        if opening is None:
            for kind in ("DOOR", "WINDOW", "OPENING"):
                opening = self.arch.get_by_code(kind, opening_ref)
                if opening:
                    break
        if opening is None:
            raise DomainError(message=f"Vano no encontrado: {opening_ref}", code="ARQ-DOM-053")
        wall = self.arch.get("WALL", opening.wall_id) if opening.wall_id else None
        if wall and offset_m + opening.width_m > wall.length_m + 1e-9:
            raise DomainError(message="El vano quedaría fuera del muro", code="ARQ-DOM-054")
        old_snapshot = entity_snapshot(opening)
        opening.offset_m = offset_m
        opening.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(opening), self.ctx)
        return self._finish("UPDATE_ENTITY", opening, old_snapshot,
                            events=[("OBJECT_UPDATED", {})])

    # -- relationships (spec 8) ----------------------------------------------
    def add_relationship(self, from_ref: str, to_ref: str, kind: str, source: str = "manual") -> SpaceRelationship:
        a = self._resolve_space(from_ref)
        b = self._resolve_space(to_ref)
        if a.id == b.id:
            raise DomainError(message="Un local no puede relacionarse consigo mismo", code="ARQ-DOM-055")
        relationship = SpaceRelationship(project_id=self.ctx.project.id,
                                         from_space_id=a.id, to_space_id=b.id,
                                         kind=kind, source=source)
        self.ctx.command_bus.execute(CreateEntityCommand(relationship), self.ctx)
        return self._finish("CREATE_ENTITY", relationship, events=[("OBJECT_CREATED", {})])

    # -- deletion --------------------------------------------------------------
    def delete_entity(self, entity_type: str, ref: str) -> str:
        entity = self.arch.get_by_code(entity_type, ref) or self.arch.get(entity_type, ref)
        if entity is None:
            raise DomainError(message=f"Objeto no encontrado: {ref}", code="ARQ-DOM-056")
        command = DeleteEntityCommand(entity_type, entity.id)
        result = self.ctx.command_bus.execute(command, self.ctx)
        old_value = {
            "entity": (result or {}).get("snapshot", {}),
            "cascade": (result or {}).get("cascade", []),
        }
        self._audit("DELETE_ENTITY", entity_type, entity.id, old_value, None)
        self.ctx.emit("OBJECT_DELETED", {"id": entity.id, "type": entity_type, "code": entity.code})
        for cascade in old_value["cascade"]:
            self.ctx.quantities_repo.delete_for_object(cascade.get("id", ""))
        self._invalidate_object(entity.id)
        self.ctx.quantities_repo.delete_for_object(entity.id)
        self.ctx.dependency_graph.remove_object(entity.id)
        return entity.id

    # -- queries ---------------------------------------------------------------
    def list_summary(self, entity_type: str) -> List[Dict[str, Any]]:
        rows = []
        for entity in self.arch.list(entity_type, self.ctx.project.id):
            row = {"id": entity.id, "code": entity.code, "status": entity.status.value,
                   "revision": entity.revision}
            if hasattr(entity, "name"):
                row["name"] = entity.name
            rows.append(row)
        return rows


__all__ = ["ArchitectureService"]
