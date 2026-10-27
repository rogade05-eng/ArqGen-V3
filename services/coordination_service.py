"""CoordinationService (spec sections 35, 36, 102).

Intermediary between disciplines: Architecture → Coordination → MEP /
Structure / Security / BIM. Runs the clash engine over the whole
project, persists new Clash entities (deduplicated by object pair +
type), tracks their lifecycle (OPEN → REVIEWED → ACCEPTED / RESOLVED /
IGNORED) and emits CLASH_CREATED / CLASH_RESOLVED events.

Clashes live in their own table (m007_clash) through ClashRepository;
undo/redo and generic commands route through services.commands_impl.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.entities.base import new_uuid
from core.errors import DomainError
from domain.clash import CLASH_STATUSES, Clash
from engines.clash_engine import (
    ACCESS_ZONE_M, CLEARANCE_MIN_M, DEVICE_RADIUS_M, MAINTENANCE_ZONE_M,
    SOFT_TOLERANCE_M, node_node_clashes, node_wall_clashes,
    segment_segment_clashes,
)
from services.context import ProjectContext


class CoordinationService:
    """Facade of the coordination / clash module (spec 35-36)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    # -- detection ------------------------------------------------------------
    def run_detection(self, systems_filter: Optional[List[str]] = None
                      ) -> Dict[str, Any]:
        """Detecta interferencias en todo el proyecto (spec 35)."""
        project_id = self.ctx.project.id
        walls = self._collect_walls()
        nodes = self._collect_nodes(systems_filter)
        segments = self._collect_segments(systems_filter)

        findings: List[Any] = []
        # Dispositivos ↔ muros (HARD / CLEARANCE / ACCESS).
        for node in nodes:
            radius = node.get("radius", 0.0)
            findings.extend(node_wall_clashes(
                (node["type"], node["id"], node["code"], node["position"],
                 radius),
                walls, clearance_m=CLEARANCE_MIN_M,
                access_zone_m=ACCESS_ZONE_M, device_radius_m=DEVICE_RADIUS_M))
        # Dispositivo ↔ dispositivo (SOFT / MAINTENANCE).
        findings.extend(node_node_clashes(
            [(n["type"], n["id"], n["code"], n["discipline"], n["position"],
              n.get("radius", 0.0)) for n in nodes],
            soft_tolerance_m=SOFT_TOLERANCE_M,
            maintenance_zone_m=MAINTENANCE_ZONE_M))
        # Tramo ↔ tramo (ROUTE).
        findings.extend(segment_segment_clashes(
            [(s["type"], s["id"], s["code"], s["network_id"], s["endpoints"],
              s.get("crossings", 0)) for s in segments]))

        created: List[Clash] = []
        skipped = 0
        for finding in findings:
            existing = self.ctx.clash_repo.find_pair(
                project_id, finding.object_a[1], finding.object_b[1],
                finding.type)
            if existing is not None:
                skipped += 1
                continue
            clash = Clash(
                id=new_uuid(), project_id=project_id,
                code=self.ctx.next_code("SECURITY", "CLASH"),
                object_a_type=finding.object_a[0], object_a_id=finding.object_a[1],
                object_a_code=finding.object_a[2],
                object_b_type=finding.object_b[0], object_b_id=finding.object_b[1],
                object_b_code=finding.object_b[2],
                type=finding.type, severity=finding.severity,
                rule=finding.rule, location=finding.location,
                distance=finding.distance, status="OPEN")
            self.ctx.clash_repo.save(clash)
            self.ctx.emit("CLASH_CREATED", {
                "id": clash.id, "code": clash.code, "type": clash.type,
                "severity": clash.severity, "a": clash.object_a_code,
                "b": clash.object_b_code})
            created.append(clash)
        self.ctx.commit()
        counts = self.ctx.clash_repo.status_counts(project_id)
        return {
            "created": len(created),
            "duplicates_skipped": skipped,
            "open": counts.get("OPEN", 0),
            "by_type": self._by_type(project_id),
            "clashes": [self._summary(c) for c in created[:20]],
        }

    def _by_type(self, project_id: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for clash in self.ctx.clash_repo.list(project_id):
            counts[clash.type] = counts.get(clash.type, 0) + 1
        return counts

    # -- collection helpers ------------------------------------------------------
    def _collect_walls(self) -> List[Tuple[str, str, str, Tuple[Any, Any], float]]:
        walls = []
        for wall in self.ctx.architecture.list("WALL", self.ctx.project.id):
            walls.append(("WALL", wall.id, wall.code,
                          ((wall.start[0], wall.start[1]),
                           (wall.end[0], wall.end[1])),
                          wall.thickness_m))
        return walls

    def _node_discipline(self, node) -> str:
        network = self.ctx.installations.get("NETWORK", node.network_id)
        return network.system if network else "INSTALLATIONS"

    def _node_radius(self, node) -> float:
        radius = node.num("radius_m", 0.0)
        if radius > 0:
            return radius
        # Equipos grandes llevan frente de maniobra (tableros, paneles, racks).
        return 0.25 if node.kind in ("PANEL", "FIRE_PANEL", "INTRUSION_PANEL",
                                     "ACCESS_CONTROLLER", "RACK", "NVR",
                                     "AHU", "TANK") else 0.0

    def _collect_nodes(self, systems_filter: Optional[List[str]] = None
                       ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        networks = {n.id: n for n in
                    self.ctx.installations.list("NETWORK", self.ctx.project.id)}
        for node in self.ctx.installations.list("NODE", self.ctx.project.id):
            network = networks.get(node.network_id)
            if network is None:
                continue
            if systems_filter and network.system not in systems_filter:
                continue
            rows.append({
                "type": "NODE", "id": node.id, "code": node.code,
                "kind": node.kind, "discipline": network.system,
                "network_id": node.network_id,
                "position": (node.x, node.y),
                "radius": self._node_radius(node),
            })
        return rows

    def _collect_segments(self, systems_filter: Optional[List[str]] = None
                          ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        networks = {n.id: n for n in
                    self.ctx.installations.list("NETWORK", self.ctx.project.id)}
        for segment in self.ctx.installations.list("SEGMENT", self.ctx.project.id):
            network = networks.get(segment.network_id)
            if network is None:
                continue
            if systems_filter and network.system not in systems_filter:
                continue
            from_node = self.ctx.installations.get("NODE", segment.from_node_id)
            to_node = self.ctx.installations.get("NODE", segment.to_node_id)
            if from_node is None or to_node is None:
                continue
            rows.append({
                "type": "SEGMENT", "id": segment.id, "code": segment.code,
                "network_id": segment.network_id,
                "endpoints": ((from_node.x, from_node.y),
                              (to_node.x, to_node.y)),
                "crossings": segment.crossings,
            })
        return rows

    # -- lifecycle ------------------------------------------------------------
    def list_clashes(self, status: str = "", clash_type: str = ""
                     ) -> List[Dict[str, Any]]:
        where_clauses = []
        params: List[Any] = []
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if clash_type:
            where_clauses.append("type = ?")
            params.append(clash_type)
        where = " AND ".join(where_clauses)
        clashes = self.ctx.clash_repo.list(self.ctx.project.id, where,
                                           tuple(params))
        return [self._summary(clash) for clash in clashes]

    @staticmethod
    def _summary(clash: Clash) -> Dict[str, Any]:
        return {
            "code": clash.code, "type": clash.type,
            "severity": clash.severity, "status": clash.status,
            "a": clash.object_a_code, "b": clash.object_b_code,
            "rule": clash.rule,
            "location": [round(clash.location[0], 3), round(clash.location[1], 3)],
            "distance": round(clash.distance, 3),
        }

    def set_status(self, clash_ref: str, new_status: str,
                   notes: str = "") -> Clash:
        """Ciclo de vida de la interferencia (spec 36)."""
        if new_status not in CLASH_STATUSES:
            raise DomainError(
                message=f"Estado desconocido: {new_status}",
                code="ARQ-CLS-003", context={"allowed": list(CLASH_STATUSES)})
        clash = (self.ctx.clash_repo.get_by_code(clash_ref)
                 or self.ctx.clash_repo.get(clash_ref))
        if clash is None:
            raise DomainError(message=f"Interferencia no encontrada: {clash_ref}",
                              code="ARQ-CLS-005")
        previous = clash.status
        clash.set_status(new_status)
        if notes:
            clash.notes = notes
        self.ctx.clash_repo.save(clash)
        if new_status == "RESOLVED":
            self.ctx.emit("CLASH_RESOLVED", {"id": clash.id, "code": clash.code})
        self.ctx.commit()
        return clash


__all__ = ["CoordinationService"]
