"""Repositories for the installations module (spec sections 24, 25, 78)."""

from __future__ import annotations

from typing import Dict, List, Optional

from domain.installations import InstallNetwork, InstallNode, InstallSegment
from persistence.repositories.base import EntityMapper, apply_common_fields, entity_common_row
from persistence.sqlite.connection import Session, json_dumps, json_loads


class InstallNetworkRepository(EntityMapper[InstallNetwork]):
    table = "install_networks"
    entity_class = InstallNetwork

    def to_row(self, e: InstallNetwork) -> dict:
        return {**entity_common_row(e), "name": e.name, "discipline": e.discipline,
                "system": e.system, "description": e.description}

    def from_row(self, row) -> InstallNetwork:
        e = InstallNetwork(id=row["id"], name=row["name"], discipline=row["discipline"],
                           system=row["system"], description=row["description"])
        apply_common_fields(e, row)
        return e


class InstallNodeRepository(EntityMapper[InstallNode]):
    table = "install_nodes"
    entity_class = InstallNode

    def to_row(self, e: InstallNode) -> dict:
        return {**entity_common_row(e), "network_id": e.network_id, "kind": e.kind,
                "name": e.name, "x": e.x, "y": e.y, "elevation_m": e.elevation_m,
                "space_id": e.space_id, "wall_id": e.wall_id,
                "attrs_json": json_dumps(e.attrs)}

    def from_row(self, row) -> InstallNode:
        e = InstallNode(id=row["id"], network_id=row["network_id"], kind=row["kind"],
                        name=row["name"], x=row["x"], y=row["y"],
                        elevation_m=row["elevation_m"], space_id=row["space_id"],
                        wall_id=row["wall_id"], attrs=json_loads(row["attrs_json"], {}) or {})
        apply_common_fields(e, row)
        return e


class InstallSegmentRepository(EntityMapper[InstallSegment]):
    table = "install_segments"
    entity_class = InstallSegment

    def to_row(self, e: InstallSegment) -> dict:
        return {**entity_common_row(e), "network_id": e.network_id,
                "from_node_id": e.from_node_id, "to_node_id": e.to_node_id,
                "kind": e.kind, "name": e.name, "length_m": e.length_m,
                "diameter_mm": e.diameter_mm, "width_mm": e.width_mm,
                "height_mm": e.height_mm, "slope_pct": e.slope_pct,
                "material": e.material, "routing": e.routing,
                "waypoints_json": json_dumps([list(p) for p in e.waypoints]),
                "crossings": e.crossings, "attrs_json": json_dumps(e.attrs)}

    def from_row(self, row) -> InstallSegment:
        e = InstallSegment(id=row["id"], network_id=row["network_id"],
                           from_node_id=row["from_node_id"], to_node_id=row["to_node_id"],
                           kind=row["kind"], name=row["name"], length_m=row["length_m"],
                           diameter_mm=row["diameter_mm"], width_mm=row["width_mm"],
                           height_mm=row["height_mm"], slope_pct=row["slope_pct"],
                           material=row["material"], routing=row["routing"],
                           waypoints=[tuple(p) for p in json_loads(row["waypoints_json"], [])],
                           crossings=int(row["crossings"]),
                           attrs=json_loads(row["attrs_json"], {}) or {})
        apply_common_fields(e, row)
        return e


class InstallationsRepository:
    """Facade over the installation repositories with a typed registry."""

    def __init__(self, session: Session) -> None:
        self.networks = InstallNetworkRepository(session)
        self.nodes = InstallNodeRepository(session)
        self.segments = InstallSegmentRepository(session)
        self._mappers: Dict[str, EntityMapper] = {
            "NETWORK": self.networks,
            "NODE": self.nodes,
            "SEGMENT": self.segments,
        }

    @property
    def session(self) -> Session:
        return self.networks.session

    def mapper_for(self, entity_type: str) -> EntityMapper:
        mapper = self._mappers.get(entity_type)
        if mapper is None:
            raise KeyError(f"Sin repositorio para el tipo: {entity_type}")
        return mapper

    def save(self, entity) -> object:
        return self.mapper_for(entity.ENTITY_TYPE).save(entity)

    def get(self, entity_type: str, entity_id: str):
        return self.mapper_for(entity_type).get(entity_id)

    def get_by_code(self, entity_type: str, code: str):
        return self.mapper_for(entity_type).get_by_code(code)

    def list(self, entity_type: str, project_id: str, where: str = "", params: tuple = ()) -> list:
        return self.mapper_for(entity_type).list(project_id, where, params)

    def delete(self, entity_type: str, entity_id: str) -> bool:
        return self.mapper_for(entity_type).delete(entity_id)

    def count(self, entity_type: str, project_id: str) -> int:
        return self.mapper_for(entity_type).count(project_id)

    def nodes_of(self, network_id: str) -> List[InstallNode]:
        return self._list_network(self.nodes, network_id)

    def segments_of(self, network_id: str) -> List[InstallSegment]:
        return self._list_network(self.segments, network_id)

    def _list_network(self, mapper: EntityMapper, network_id: str) -> list:
        rows = mapper.session.query_all(
            f"SELECT * FROM {mapper.table} WHERE network_id = ? ORDER BY code, created_at",
            (network_id,))
        return [mapper.from_row(r) for r in rows]

    def all_codes(self, project_id: str) -> List[str]:
        codes: set[str] = set()
        for mapper in self._mappers.values():
            for row in mapper.session.query_all(
                    f"SELECT code FROM {mapper.table} WHERE project_id = ?", (project_id,)):
                if row["code"]:
                    codes.add(row["code"])
        return sorted(codes)


__all__ = [
    "InstallationsRepository", "InstallNetworkRepository",
    "InstallNodeRepository", "InstallSegmentRepository",
]
