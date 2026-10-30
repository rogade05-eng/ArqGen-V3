"""Concrete commands (spec section 76).

CreateWallCommand, CreateSpaceCommand, MoveWallCommand... implemented as
generic snapshot commands: every mutation stores the complete entity
snapshot before and after, enabling transactional undo/redo (spec 77).
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional, Type

from core.commands.bus import Command
from core.entities.base import Entity
from core.errors import DomainError
from services.context import ProjectContext

UNDOABLE_COMMANDS = ("CREATE_ENTITY", "UPDATE_ENTITY", "DELETE_ENTITY")


def entity_snapshot(entity: Entity) -> Dict[str, Any]:
    """Full serializable snapshot of an entity (for audit + undo/redo)."""
    data: Dict[str, Any] = {}
    for f in entity.__dataclass_fields__:
        value = getattr(entity, f)
        if hasattr(value, "value") and hasattr(value, "name"):  # Enum
            value = value.value
        elif f in ("created_at", "updated_at") and value is not None:
            value = value.isoformat()
        data[f] = value
    data["ENTITY_TYPE"] = entity.ENTITY_TYPE
    return data


def snapshot_to_entity(snapshot: Dict[str, Any]) -> Entity:
    """Rebuild an entity from a snapshot (used by undo/redo)."""
    from domain import installations as domain_installations
    from domain import model as domain_model
    from domain import structure as domain_structure
    entity_type = snapshot.get("ENTITY_TYPE", "")
    registry: Dict[str, Type[Entity]] = {
        "PROJECT": domain_model.Project,
        "SITE": domain_model.Site,
        "BUILDING": domain_model.Building,
        "LEVEL": domain_model.Level,
        "ZONE": domain_model.Zone,
        "SPACE": domain_model.Space,
        "SPACE_RELATIONSHIP": domain_model.SpaceRelationship,
        "WALL": domain_model.Wall,
        "OPENING": domain_model.Opening,
        "DOOR": domain_model.Door,
        "WINDOW": domain_model.Window,
        "NETWORK": domain_installations.InstallNetwork,
        "NODE": domain_installations.InstallNode,
        "SEGMENT": domain_installations.InstallSegment,
        "MATERIAL": domain_structure.StructuralMaterial,
        "SECTION": domain_structure.StructuralSection,
        "ELEMENT": domain_structure.StructuralElement,
        "LOAD_CASE": domain_structure.LoadCase,
        "COMBINATION": domain_structure.Combination,
        # Concepción de espacios (v3.15.0)
        "FURNITURE": domain_model.Furniture,
        "ROOF": domain_model.Roof,
        "RAMP": domain_model.Ramp,
        "HANDRAIL": domain_model.Handrail,
        "ELEVATOR": domain_model.Elevator,
        "PARASOL": domain_model.Parasol,
        "SKIN": domain_model.FacadeSkin,
        "STAIR": domain_model.Stair,
    }
    cls = registry.get(entity_type)
    if cls is None:
        raise DomainError(
            message=f"Tipo de entidad desconocido para restaurar: {entity_type}",
            code="ARQ-DOM-040",
        )
    fields = {f for f in cls.__dataclass_fields__}
    kwargs: Dict[str, Any] = {}
    for key, value in snapshot.items():
        if key in fields and key not in ("status", "created_at", "updated_at"):
            kwargs[key] = value
    entity = cls(**kwargs)  # type: ignore[arg-type]
    from core.entities.base import EntityStatus, parse_datetime
    if snapshot.get("status") in EntityStatus._value2member_map_:
        entity.status = EntityStatus(snapshot["status"])
    if snapshot.get("created_at"):
        entity.created_at = parse_datetime(snapshot["created_at"]) or entity.created_at
    if snapshot.get("updated_at"):
        entity.updated_at = parse_datetime(snapshot["updated_at"]) or entity.updated_at
    return entity


def _repo_for(context: ProjectContext, entity_type: str):
    """Repository that owns an entity type (architecture, installations,
    structure or coordination)."""
    if entity_type in ("NETWORK", "NODE", "SEGMENT"):
        return context.installations
    if entity_type in ("MATERIAL", "SECTION", "ELEMENT", "LOAD_CASE",
                       "COMBINATION"):
        return context.structure
    if entity_type == "CLASH" and getattr(context, "clash_repo", None):
        return context.clash_repo
    return context.architecture


class CreateEntityCommand(Command[ProjectContext]):
    name = "CREATE_ENTITY"

    def __init__(self, entity: Entity) -> None:
        self.entity = entity

    def execute(self, context: ProjectContext) -> Dict[str, Any]:
        repo = _repo_for(context, self.entity.ENTITY_TYPE)
        repo.save(self.entity)
        snapshot = entity_snapshot(self.entity)
        return {"snapshot": snapshot}

    def undo(self, context: ProjectContext, result: Any = None) -> None:
        snapshot = (result or {}).get("snapshot", {})
        _repo_for(context, self.entity.ENTITY_TYPE).delete(
            self.entity.ENTITY_TYPE, self.entity.id)


class UpdateEntityCommand(Command[ProjectContext]):
    name = "UPDATE_ENTITY"

    def __init__(self, entity: Entity) -> None:
        self.entity = entity

    def execute(self, context: ProjectContext) -> Dict[str, Any]:
        repo = _repo_for(context, self.entity.ENTITY_TYPE)
        old = repo.get(self.entity.ENTITY_TYPE, self.entity.id)
        if old is None:
            raise DomainError(
                message=f"Objeto inexistente: {self.entity.id}",
                code="ARQ-DOM-041",
            )
        old_snapshot = entity_snapshot(old)
        repo.save(self.entity)
        return {"old_snapshot": old_snapshot, "new_snapshot": entity_snapshot(self.entity)}

    def undo(self, context: ProjectContext, result: Any = None) -> None:
        old_snapshot = (result or {}).get("old_snapshot")
        if old_snapshot:
            _repo_for(context, self.entity.ENTITY_TYPE).save(
                snapshot_to_entity(old_snapshot))


class DeleteEntityCommand(Command[ProjectContext]):
    name = "DELETE_ENTITY"

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id

    def execute(self, context: ProjectContext) -> Dict[str, Any]:
        repo = _repo_for(context, self.entity_type)
        entity = repo.get(self.entity_type, self.entity_id)
        if entity is None:
            raise DomainError(
                message=f"Objeto inexistente: {self.entity_id}",
                code="ARQ-DOM-041",
            )
        snapshot = entity_snapshot(entity)
        cascade_snapshots: list[dict] = []
        # Cascade: openings die with their wall; segments die with their
        # node; a whole network dies with its nodes and segments.
        if self.entity_type == "WALL":
            for opening in context.architecture.list("OPENING", context.project.id):
                if opening.wall_id == self.entity_id:
                    cascade_snapshots.append(entity_snapshot(opening))
                    context.architecture.delete("OPENING", opening.id)
        elif self.entity_type == "NODE":
            for segment in context.installations.segments_of(entity.network_id):
                if self.entity_id in (segment.from_node_id, segment.to_node_id):
                    cascade_snapshots.append(entity_snapshot(segment))
                    context.installations.delete("SEGMENT", segment.id)
        elif self.entity_type == "NETWORK":
            for node in context.installations.nodes_of(self.entity_id):
                cascade_snapshots.append(entity_snapshot(node))
                context.installations.delete("NODE", node.id)
            for segment in context.installations.segments_of(self.entity_id):
                cascade_snapshots.append(entity_snapshot(segment))
                context.installations.delete("SEGMENT", segment.id)
        repo.delete(self.entity_type, self.entity_id)
        return {"snapshot": snapshot, "cascade": cascade_snapshots}

    def undo(self, context: ProjectContext, result: Any = None) -> None:
        result = result or {}
        snapshot = result.get("snapshot")
        if snapshot:
            _repo_for(context, self.entity_type).save(snapshot_to_entity(snapshot))
        for cascade_snapshot in result.get("cascade", []):
            _repo_for(context, cascade_snapshot.get("ENTITY_TYPE", "")).save(
                snapshot_to_entity(cascade_snapshot))


__all__ = [
    "CreateEntityCommand", "UpdateEntityCommand", "DeleteEntityCommand",
    "entity_snapshot", "snapshot_to_entity", "UNDOABLE_COMMANDS",
]
