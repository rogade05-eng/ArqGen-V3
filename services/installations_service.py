"""InstallationsService (spec sections 24-29, 76, 82, 99).

Service of the installations module. All mutations go through the
CommandBus, write the audit trail, emit events (SYSTEM_CHANGED,
DEVICE_MOVED, ROUTE_CHANGED) and invalidate stale quantities. Network,
electrical, sanitary and HVAC calculations produce reproducible
CalculationResults (spec 102).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.calculations.contracts import CalculationMode, CalculationResult, CalculationStatus
from core.entities.base import new_uuid
from core.errors import DomainError
from core.validation.results import Finding, ValidationStatus
from domain.installations import (
    InstallNetwork, InstallNode, InstallSegment, SEGMENT_KINDS, NODE_KINDS,
    SYSTEMS, topology_of,
)
from engines.electrical_engine import (
    CONDUCTORS_1PH, CONDUCTORS_3PH, CircuitCheck, LoadSummary,
    current_a, demand_power, phase_balance, select_breaker, select_conduit,
    select_section, voltage_drop_pct, VD_LIMIT_BRANCH_PCT,
)
from engines.gas_engine import (
    DP_BUDGET_PA, MAX_GAS_VELOCITY_MS, MAX_RUN_M, MIN_GAS_VELOCITY_MS,
    SEPARATION_M, consumption_units, gas_flow_m3h, required_vent_area_m2,
    segment_dp_pa, select_gas_diameter, velocity_ms,
)
from engines.hvac_engine import (
    ThermalLoad, calculate_airflow, select_equipment, size_duct, thermal_load,
)
from engines.network_engine import NetworkGraph
from engines.routing_engine import Obstacle, RoutingEngine
from engines.sanitary_engine import (
    FIXTURE_FLOW_LS, design_flow_ls, manning_capacity_ls, min_slope_pct,
    segment_head_loss_m, select_drain_diameter, select_pressure_diameter,
    size_pump, tank_volume_ls, velocity_ms,
)
from engines.stormwater_engine import (
    DEFAULT_INTENSITY_MMH, DEFAULT_RETENTION_MIN, MIN_GUTTER_SLOPE_PCT,
    detention_volume_ls, downpipe_capacity_ls, gutter_capacity_ls,
    outfall_required_capacity, runoff_coefficient, runoff_ls, select_downpipe,
    select_gutter,
)
from engines.telecom_engine import (
    DEFAULT_RACK_U, FIBER_DEFAULT_BUDGET_DB, PATCH_PANEL_PORTS,
    SWITCH_PORTS, TELECOM_FILL_LIMIT_PCT, cable_diameter_mm,
    conduit_fill_pct, fiber_budget_findings, fiber_loss_db,
    link_length_findings, port_usage, rack_summary,
    select_conduit as select_telecom_conduit,
)
from engines.quantity_engine import FormulaSpec
from services.commands_impl import (
    CreateEntityCommand, DeleteEntityCommand, UpdateEntityCommand, entity_snapshot,
)
from services.context import ProjectContext

ELECTRICAL_SYSTEMS = ("POWER", "LIGHTING", "EMERGENCY")
SANITARY_SYSTEMS = ("COLD_WATER", "HOT_WATER", "SANITARY_DRAINAGE", "STORMWATER",
                    "PUMPING", "STORAGE")
HVAC_SYSTEMS = ("HVAC_SUPPLY", "HVAC_RETURN", "EXHAUST")


class InstallationsService:
    """Facade of the installations module (network + electrical + sanitary + HVAC)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context
        self.router = RoutingEngine()

    # -- helpers -----------------------------------------------------------
    def _audit(self, command: str, entity_type: str, entity_id: str,
               old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]],
               reason: str = "", result: str = "OK") -> None:
        from core.audit.models import make_audit_event
        event = make_audit_event(self.ctx.user, entity_id, entity_type, command,
                                 old, new, reason, result)
        self.ctx.audit_repo.append(event)

    def _finish(self, command_name: str, entity, old_snapshot: Optional[Dict[str, Any]] = None,
                events: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
                skip_invalidate: bool = False) -> Any:
        new_snapshot = entity_snapshot(entity)
        self._audit(command_name, entity.ENTITY_TYPE, entity.id, old_snapshot, new_snapshot)
        for event_type, payload in events or []:
            self.ctx.emit(event_type, {"id": entity.id, "type": entity.ENTITY_TYPE,
                                       "code": entity.code, **payload})
        if not skip_invalidate:
            self._invalidate_object(entity.id)
        return entity

    def _invalidate_object(self, object_id: str) -> int:
        count = self.ctx.calculations_repo.mark_stale_for_object(object_id)
        count += self.ctx.quantities_repo.mark_stale_for_object(object_id)
        return count

    def _persist_proposals(self, segments: List[InstallSegment]) -> int:
        """Persist sizing suggestions written into segment attrs.

        The proposals (diameter_mm_suggested, cables, ...) travel through
        the CommandBus so they are audited, undoable and visible to QTO
        and later validations in the same session.
        """
        persisted = 0
        for segment in segments:
            segment.touch()
            self.ctx.command_bus.execute(UpdateEntityCommand(segment), self.ctx)
            self._finish("UPDATE_ENTITY", segment, events=[("SYSTEM_CHANGED", {})],
                         skip_invalidate=True)
            persisted += 1
        return persisted

    def _store_calculation(self, calc_type: str, objects: List[Tuple[str, str, int]],
                           values: Dict[str, float], units: Dict[str, str],
                           parameters: Optional[Dict[str, Any]] = None,
                           errors: Optional[List[str]] = None,
                           status: CalculationStatus = CalculationStatus.COMPLETED) -> CalculationResult:
        result = CalculationResult(
            calculation_type=calc_type,
            input_objects=[{"type": t, "id": i, "revision": r} for t, i, r in objects],
            parameters=parameters or {},
            values={k: round(v, 4) for k, v in values.items()},
            units=units,
            errors=errors or [],
            mode=CalculationMode.BALANCED, status=status,
            objects_processed=len(objects),
        )
        self.ctx.calculations_repo.save(result, self.ctx.project.id)
        return result

    # -- resolution ----------------------------------------------------------
    def resolve_network(self, ref: str) -> InstallNetwork:
        network = self.ctx.installations.get_by_code("NETWORK", ref)
        if network is None:
            network = self.ctx.installations.get("NETWORK", ref)
        if network is None:
            for candidate in self.ctx.installations.list("NETWORK", self.ctx.project.id):
                if candidate.name.lower() == ref.lower():
                    network = candidate
                    break
        if network is None:
            raise DomainError(message=f"Red de instalaciones no encontrada: {ref}",
                              code="ARQ-MEP-010")
        return network

    def resolve_node(self, ref: str) -> InstallNode:
        node = self.ctx.installations.get_by_code("NODE", ref)
        if node is None:
            node = self.ctx.installations.get("NODE", ref)
        if node is None:
            for candidate in self.ctx.installations.list("NODE", self.ctx.project.id):
                if candidate.name.lower() == ref.lower():
                    node = candidate
                    break
        if node is None:
            raise DomainError(message=f"Nodo de red no encontrado: {ref}",
                              code="ARQ-MEP-011")
        return node

    def resolve_segment(self, ref: str) -> InstallSegment:
        segment = self.ctx.installations.get_by_code("SEGMENT", ref)
        if segment is None:
            segment = self.ctx.installations.get("SEGMENT", ref)
        if segment is None:
            raise DomainError(message=f"Tramo no encontrado: {ref}", code="ARQ-MEP-012")
        return segment

    # -- networks ---------------------------------------------------------
    def create_network(self, name: str, system: str,
                       description: str = "") -> InstallNetwork:
        if system not in SYSTEMS:
            raise DomainError(
                message=f"Sistema desconocido: {system}",
                code="ARQ-MEP-001", context={"allowed": sorted(SYSTEMS)})
        network = InstallNetwork(project_id=self.ctx.project.id,
                                 code=self.ctx.next_code("INSTALLATIONS", "NETWORK"),
                                 name=name, discipline=SYSTEMS[system], system=system,
                                 description=description)
        self.ctx.command_bus.execute(CreateEntityCommand(network), self.ctx)
        return self._finish("CREATE_ENTITY", network, events=[("SYSTEM_CHANGED", {})])

    def delete_entity(self, entity_type: str, ref: str) -> str:
        if entity_type in ("NETWORK", "NODE", "SEGMENT"):
            entity = (self.ctx.installations.get_by_code(entity_type, ref)
                      or self.ctx.installations.get(entity_type, ref))
        else:
            entity = (self.ctx.architecture.get_by_code(entity_type, ref)
                      or self.ctx.architecture.get(entity_type, ref))
        if entity is None:
            raise DomainError(message=f"Objeto no encontrado: {ref}", code="ARQ-MEP-013")
        command = DeleteEntityCommand(entity_type, entity.id)
        result = self.ctx.command_bus.execute(command, self.ctx)
        old_value = {"entity": (result or {}).get("snapshot", {}),
                     "cascade": (result or {}).get("cascade", [])}
        self._audit("DELETE_ENTITY", entity_type, entity.id, old_value, None)
        self.ctx.emit("OBJECT_DELETED", {"id": entity.id, "type": entity_type,
                                         "code": entity.code})
        for cascade in old_value["cascade"]:
            self.ctx.quantities_repo.delete_for_object(cascade.get("id", ""))
            self.ctx.calculations_repo.delete_for_object(cascade.get("id", ""))
        self._invalidate_object(entity.id)
        self.ctx.quantities_repo.delete_for_object(entity.id)
        self.ctx.calculations_repo.delete_for_object(entity.id)
        return entity.id

    # -- nodes --------------------------------------------------------------
    def add_node(self, network_ref: str, kind: str, x: float, y: float,
                 name: str = "", level_ref: str = "", space_ref: str = "",
                 elevation_m: float = 0.0,
                 attrs: Optional[Dict[str, Any]] = None) -> InstallNode:
        network = self.resolve_network(network_ref)
        if kind not in NODE_KINDS:
            raise DomainError(
                message=f"Tipo de nodo desconocido: {kind}",
                code="ARQ-MEP-004", context={"allowed": list(NODE_KINDS)})
        level_id = ""
        if level_ref:
            level = self.ctx.architecture.get_by_code("LEVEL", level_ref) \
                or self.ctx.architecture.get("LEVEL", level_ref)
            if level is None:
                raise DomainError(message=f"Nivel no encontrado: {level_ref}",
                                  code="ARQ-MEP-014")
            level_id = level.id
        space_id = ""
        if space_ref:
            space = self.ctx.architecture.get_by_code("SPACE", space_ref) \
                or self.ctx.architecture.get("SPACE", space_ref)
            if space is None:
                for candidate in self.ctx.architecture.list("SPACE", self.ctx.project.id):
                    if candidate.name.lower() == space_ref.lower():
                        space = candidate
                        break
            if space is None:
                raise DomainError(message=f"Local no encontrado: {space_ref}",
                                  code="ARQ-MEP-015")
            space_id = space.id
        node = InstallNode(project_id=self.ctx.project.id,
                           code=self.ctx.next_code("INSTALLATIONS", "NODE"),
                           network_id=network.id, kind=kind, name=name,
                           x=x, y=y, elevation_m=elevation_m,
                           space_id=space_id or None, attrs=attrs or {})
        if level_id:
            node.level_id = level_id
        self.ctx.command_bus.execute(CreateEntityCommand(node), self.ctx)
        return self._finish("CREATE_ENTITY", node, events=[("SYSTEM_CHANGED", {})])

    def move_node(self, node_ref: str, x: float, y: float) -> InstallNode:
        node = self.resolve_node(node_ref)
        old_snapshot = entity_snapshot(node)
        node.x, node.y = float(x), float(y)
        node.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(node), self.ctx)
        # Routed segments through this node are re-routed (length + crossings).
        for segment in self.ctx.installations.segments_of(node.network_id):
            if node.id not in (segment.from_node_id, segment.to_node_id):
                continue
            if segment.attrs.get("length_source") != "routing":
                continue
            other_id = segment.to_node_id if segment.from_node_id == node.id else segment.from_node_id
            other = self.ctx.installations.get("NODE", other_id)
            if other is None:
                continue
            seg_old = entity_snapshot(segment)
            if segment.routing == "STRAIGHT":
                route = self.router.route_straight((node.x, node.y), (other.x, other.y))
            else:
                route = self.router.route((node.x, node.y), (other.x, other.y),
                                          obstacles=self._wall_obstacles(node.level_id))
            segment.length_m = round(route.length_m, 4)
            segment.crossings = route.crossings
            segment.waypoints = route.waypoints
            segment.touch()
            self.ctx.command_bus.execute(UpdateEntityCommand(segment), self.ctx)
            self._finish("UPDATE_ENTITY", segment, seg_old,
                         events=[("ROUTE_CHANGED", {"crossings": route.crossings})])
        return self._finish("UPDATE_ENTITY", node, old_snapshot,
                            events=[("DEVICE_MOVED", {"x": x, "y": y})])

    def set_node_attrs(self, node_ref: str, attrs: Dict[str, Any]) -> InstallNode:
        node = self.resolve_node(node_ref)
        old_snapshot = entity_snapshot(node)
        node.attrs.update(attrs)
        node.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(node), self.ctx)
        return self._finish("UPDATE_ENTITY", node, old_snapshot,
                            events=[("SYSTEM_CHANGED", {})])

    # -- segments -------------------------------------------------------------
    def _wall_obstacles(self, level_id: Optional[str]) -> List[Obstacle]:
        obstacles: List[Obstacle] = []
        for wall in self.ctx.architecture.list("WALL", self.ctx.project.id):
            if level_id and wall.level_id and wall.level_id != level_id:
                continue
            obstacles.append(Obstacle(start=tuple(wall.start), end=tuple(wall.end),
                                      thickness_m=wall.thickness_m))
        return obstacles

    def connect(self, network_ref: str, from_ref: str, to_ref: str,
                kind: str = "CONDUIT", name: str = "",
                length_m: float = 0.0, diameter_mm: float = 0.0,
                slope_pct: float = 0.0, material: str = "",
                routing: str = "ORTHO",
                attrs: Optional[Dict[str, Any]] = None) -> InstallSegment:
        network = self.resolve_network(network_ref)
        node_from = self.resolve_node(from_ref)
        node_to = self.resolve_node(to_ref)
        if node_from.id == node_to.id:
            raise DomainError(message="Un tramo no puede conectar un nodo consigo mismo",
                              code="ARQ-MEP-016")
        if node_from.network_id != network.id or node_to.network_id != network.id:
            raise DomainError(
                message="Ambos nodos deben pertenecer a la red indicada",
                code="ARQ-MEP-017")
        if kind not in SEGMENT_KINDS:
            raise DomainError(message=f"Tipo de tramo desconocido: {kind}",
                              code="ARQ-MEP-005")
        duplicates = [s for s in self.ctx.installations.segments_of(network.id)
                      if {s.from_node_id, s.to_node_id} == {node_from.id, node_to.id}]
        if duplicates:
            raise DomainError(
                message=f"Ya existe un tramo entre {node_from.code} y {node_to.code}: "
                        f"{duplicates[0].code}",
                code="ARQ-MEP-018")

        start = (node_from.x, node_from.y)
        end = (node_to.x, node_to.y)
        waypoints: List[Tuple[float, float]] = []
        crossings = 0
        segment_attrs: Dict[str, Any] = dict(attrs or {})
        if length_m > 0:
            computed_length = length_m
            segment_attrs["length_source"] = "explicit"
        else:
            if routing.upper() == "STRAIGHT":
                route = self.router.route_straight(start, end)
            else:
                route = self.router.route(start, end, obstacles=self._wall_obstacles(node_from.level_id))
            computed_length = round(route.length_m, 4)
            crossings = route.crossings
            waypoints = route.waypoints
            segment_attrs["length_source"] = "routing"
        if computed_length <= 0:
            raise DomainError(
                message="La longitud del tramo calculada es nula; separe los nodos",
                code="ARQ-MEP-019")

        segment = InstallSegment(project_id=self.ctx.project.id,
                                 code=self.ctx.next_code("INSTALLATIONS", "SEGMENT"),
                                 network_id=network.id,
                                 from_node_id=node_from.id, to_node_id=node_to.id,
                                 kind=kind, name=name, length_m=computed_length,
                                 diameter_mm=diameter_mm, slope_pct=slope_pct,
                                 material=material, routing=routing.upper(),
                                 waypoints=waypoints, crossings=crossings,
                                 attrs=segment_attrs)
        self.ctx.command_bus.execute(CreateEntityCommand(segment), self.ctx)
        return self._finish("CREATE_ENTITY", segment,
                            events=[("ROUTE_CHANGED", {"crossings": crossings})])

    def disconnect(self, segment_ref: str) -> str:
        segment = self.resolve_segment(segment_ref)
        return self.delete_entity("SEGMENT", segment.code)

    def set_segment_params(self, segment_ref: str,
                           length_m: Optional[float] = None,
                           diameter_mm: Optional[float] = None,
                           slope_pct: Optional[float] = None,
                           attrs: Optional[Dict[str, Any]] = None) -> InstallSegment:
        segment = self.resolve_segment(segment_ref)
        old_snapshot = entity_snapshot(segment)
        if length_m is not None:
            segment.length_m = max(float(length_m), 0.0)
        if diameter_mm is not None:
            segment.diameter_mm = max(float(diameter_mm), 0.0)
        if slope_pct is not None:
            segment.slope_pct = float(slope_pct)
        if attrs:
            segment.attrs.update(attrs)
        segment.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(segment), self.ctx)
        return self._finish("UPDATE_ENTITY", segment, old_snapshot,
                            events=[("ROUTE_CHANGED", {})])

    # -- graph operations (spec 25) ---------------------------------------------
    def graph_of(self, network_ref: str) -> Tuple[InstallNetwork, NetworkGraph]:
        network = self.resolve_network(network_ref)
        graph = NetworkGraph.build(
            self.ctx.installations.nodes_of(network.id),
            self.ctx.installations.segments_of(network.id))
        return network, graph

    def trace(self, node_ref: str) -> Dict[str, Any]:
        node = self.resolve_node(node_ref)
        network = self.ctx.installations.get("NETWORK", node.network_id)
        graph = NetworkGraph.build(
            self.ctx.installations.nodes_of(network.id),
            self.ctx.installations.segments_of(network.id))
        path = graph.trace(node.id, topology_of(network.system))
        nodes = [graph.nodes[nid] for nid in path if nid in graph.nodes]
        total_length = 0.0
        for index in range(len(path) - 1):
            segment_id = graph._segment_between(path[index + 1], path[index]) \
                if topology_of(network.system) == "radial_from_source" \
                else graph._segment_between(path[index], path[index + 1])
            segment = graph.segments.get(segment_id)
            if segment:
                total_length += segment.length_m
        return {
            "network": network.code, "node": node.code, "topology": topology_of(network.system),
            "path": [n.code for n in nodes],
            "kinds": [n.kind for n in nodes],
            "length_m": round(total_length, 3),
        }

    def find_path(self, from_ref: str, to_ref: str, weight: str = "length") -> Dict[str, Any]:
        a = self.resolve_node(from_ref)
        b = self.resolve_node(to_ref)
        network = self.ctx.installations.get("NETWORK", a.network_id)
        graph = NetworkGraph.build(
            self.ctx.installations.nodes_of(network.id),
            self.ctx.installations.segments_of(network.id))
        path, cost = graph.calculate_path(a.id, b.id, weight=weight)
        nodes = [graph.nodes[nid] for nid in path if nid in graph.nodes]
        return {
            "network": network.code,
            "path": [n.code for n in nodes],
            "cost": cost,
            "weight": weight,
        }

    def validate_network(self, network_ref: str) -> Dict[str, Any]:
        network, graph = self.graph_of(network_ref)
        result = graph.validate_network(network.system)
        dead_ends = graph.detect_dead_end(topology_of(network.system))
        for dead in dead_ends:
            result.add(Finding(
                severity="WARNING", code="ARQ-NET-020",
                message="Nodo suelto (final muerto) no terminal: revise la continuación de la red",
                object_id=dead.id, object_type="NODE", source="NETWORK"))
        result.finalize()
        return {
            "network": network.code,
            "system": network.system,
            "status": result.status.value,
            "errors": [f.to_dict() for f in result.errors],
            "warnings": [f.to_dict() for f in result.warnings],
            "info": [f.to_dict() for f in result.info],
            "dead_ends": [dead.code for dead in dead_ends],
        }

    # -- electrical (spec 27) ------------------------------------------------------
    def _panel_of(self, graph: NetworkGraph, node: InstallNode) -> Optional[InstallNode]:
        path = graph.trace(node.id, "radial_from_source")
        for node_id in path:
            candidate = graph.nodes.get(node_id)
            if candidate and candidate.kind == "PANEL":
                return candidate
        return None

    def _circuit_devices(self, graph: NetworkGraph, circuit: InstallNode) -> List[InstallNode]:
        """Terminals/equipment fed by a protection node (radial subtree)."""
        devices: List[InstallNode] = []
        stack = list(graph.adjacency.get(circuit.id, []))
        while stack:
            node_id = stack.pop()
            node = graph.nodes.get(node_id)
            if node is None:
                continue
            if node.role in ("EQUIPMENT", "TERMINAL"):
                devices.append(node)
            stack.extend(graph.adjacency.get(node_id, []))
        return devices

    def circuit_check(self, circuit_ref: str) -> Dict[str, Any]:
        circuit = self.resolve_node(circuit_ref)
        if circuit.kind != "PROTECTION":
            raise DomainError(
                message=f"El nodo {circuit.code} no es una protección (kind={circuit.kind})",
                code="ARQ-MEP-020",
                suggested_action="Indique el código de un nodo PROTECTION.")
        network = self.ctx.installations.get("NETWORK", circuit.network_id)
        graph = NetworkGraph.build(
            self.ctx.installations.nodes_of(network.id),
            self.ctx.installations.segments_of(network.id))
        panel = self._panel_of(graph, circuit)
        voltage = float(circuit.num("voltage") or (panel.num("voltage") if panel else 220.0))
        phases = int(circuit.num("phases") or (panel.num("phases") if panel else 1) or 1)
        kind = str(circuit.attrs.get("kind_circuit", "POWER")).upper()
        devices = self._circuit_devices(graph, circuit)

        connected_w = sum(device.num("power_w") for device in devices)
        demand_w, demand_factor = demand_power(connected_w, kind,
                                               circuit.attrs.get("demand_factor"))
        pf = float(circuit.num("pf", 1.0))
        pf = pf if pf > 0 else 1.0
        design_i = current_a(demand_w, voltage, pf, phases)
        breaker_attr = circuit.num("rating_a") or 0.0
        breaker = breaker_attr if breaker_attr > 0 else select_breaker(design_i)

        check = CircuitCheck(
            circuit_code=circuit.code, circuit_kind=kind, voltage=voltage,
            phases=phases, power_factor=pf,
            load=LoadSummary(connected_w=connected_w, demand_w=demand_w,
                             demand_factor=demand_factor, devices=len(devices),
                             current_a=round(design_i, 2)),
            breaker_a=breaker_attr if breaker_attr > 0 else breaker,
            breaker_standard=breaker, conductors=CONDUCTORS_1PH if phases == 1 else CONDUCTORS_3PH,
        )

        # Radial hydraulics: per-segment current = downstream load; cumulative VD.
        segment_map: Dict[str, List[InstallNode]] = {}
        for device in devices:
            path = graph.trace(device.id, "radial_from_source")
            # path: device -> ... -> source; accumulate per segment
            for index in range(len(path) - 1):
                key = f"{path[index + 1]}->{path[index]}"
                segment_map.setdefault(key, []).append(device)
        segments = {s.id: s for s in self.ctx.installations.segments_of(network.id)}
        by_node_pair = {}
        for segment in segments.values():
            by_node_pair[(segment.from_node_id, segment.to_node_id)] = segment

        worst_vd = 0.0
        max_section = 0.0
        for device in devices:
            path = graph.trace(device.id, "radial_from_source")
            cumulative_vd = 0.0
            for index in range(len(path) - 1):
                segment = by_node_pair.get((path[index + 1], path[index]))
                if segment is None:
                    continue
                downstream = segment_map.get(f"{path[index + 1]}->{path[index]}", [])
                seg_w = sum(d.num("power_w") for d in downstream)
                seg_demand, _ = demand_power(seg_w, kind, circuit.attrs.get("demand_factor"))
                seg_i = current_a(seg_demand, voltage, pf, phases) if seg_w > 0 else 0.0
                section = segment.attrs.get("section_mm2")
                if section:
                    section = float(section)
                else:
                    try:
                        section, _amp = select_section(
                            seg_i, segment.length_m, voltage, phases,
                            max_vd_pct=VD_LIMIT_BRANCH_PCT,
                            breaker_a=breaker if breaker > 0 else None)
                    except Exception:
                        section = 0.0
                    segment.attrs["section_mm2_suggested"] = section
                max_section = max(max_section, section or 0.0)
                if section and section > 0:
                    cumulative_vd += voltage_drop_pct(
                        section, segment.length_m, seg_i, voltage, phases)
            worst_vd = max(worst_vd, cumulative_vd)
        check.worst_vd_pct = worst_vd
        if max_section > 0:
            check.section_mm2 = max_section
            check.ampacity_a = _ampacity_of(max_section)
            try:
                check.conduit_mm = select_conduit(max_section, check.conductors)
            except Exception:
                check.conduit_mm = 0.0

        if check.worst_vd_pct > VD_LIMIT_BRANCH_PCT:
            check.findings.append(
                f"Caída de tensión {check.worst_vd_pct:.2f} % supera el límite "
                f"{VD_LIMIT_BRANCH_PCT:.0f} %")
        if breaker_attr > 0 and breaker_attr < design_i:
            check.findings.append(
                f"La protección ({breaker_attr:.0f} A) es menor que la corriente de diseño "
                f"({design_i:.2f} A)")
        check.ok = not check.findings

        values = {
            "connected_w": connected_w, "demand_w": demand_w,
            "design_current_a": design_i, "breaker_a": breaker,
            "worst_vd_pct": worst_vd, "section_mm2": check.section_mm2,
        }
        self._store_calculation(
            "ELEC",
            [("NODE", circuit.id, circuit.revision)] + [("NODE", d.id, d.revision) for d in devices],
            values, {"connected_w": "W", "demand_w": "W", "design_current_a": "A",
                     "breaker_a": "A", "worst_vd_pct": "%", "section_mm2": "mm2"},
            parameters={"voltage": voltage, "phases": phases, "pf": pf, "kind": kind},
        )
        return check.to_dict()

    def panel_summary(self, panel_ref: str) -> Dict[str, Any]:
        panel = self.resolve_node(panel_ref)
        if panel.kind != "PANEL":
            raise DomainError(
                message=f"El nodo {panel.code} no es un panel (kind={panel.kind})",
                code="ARQ-MEP-021")
        network = self.ctx.installations.get("NETWORK", panel.network_id)
        graph = NetworkGraph.build(
            self.ctx.installations.nodes_of(network.id),
            self.ctx.installations.segments_of(network.id))
        voltage = panel.num("voltage", 220.0)
        phases = int(panel.num("phases", 1) or 1)
        circuits: List[Dict[str, Any]] = []
        phase_loads: Dict[int, float] = {p: 0.0 for p in range(1, phases + 1)}
        for node_id in graph.adjacency.get(panel.id, []):
            node = graph.nodes.get(node_id)
            if node is None or node.kind != "PROTECTION":
                continue
            devices = self._circuit_devices(graph, node)
            connected_w = sum(d.num("power_w") for d in devices)
            kind = str(node.attrs.get("kind_circuit", "POWER")).upper()
            demand_w, factor = demand_power(connected_w, kind, node.attrs.get("demand_factor"))
            pf = node.num("pf", 1.0) or 1.0
            design_i = current_a(demand_w, voltage, pf, phases)
            breaker = node.num("rating_a") or select_breaker(design_i)
            phase = int(node.num("phase", 1) or 1)
            if phase in phase_loads:
                phase_loads[phase] += connected_w
            circuits.append({
                "code": node.code, "name": node.name, "kind": kind,
                "connected_w": round(connected_w, 1), "demand_w": round(demand_w, 1),
                "current_a": round(design_i, 2), "breaker_a": breaker,
                "phase": phase, "devices": len(devices),
            })
        total_connected = sum(c["connected_w"] for c in circuits)
        total_demand = sum(c["demand_w"] for c in circuits)
        main_breaker = panel.num("main_breaker_a") or (
            select_breaker(current_a(total_demand, voltage, 1.0, phases)))
        balance = phase_balance(phase_loads) if phases > 1 else {
            "imbalance_pct": 0.0, "max_phase_w": total_connected, "min_phase_w": total_connected}
        result = {
            "panel": panel.code, "voltage": voltage, "phases": phases,
            "main_breaker_a": main_breaker,
            "circuits": circuits,
            "total_connected_w": round(total_connected, 1),
            "total_demand_w": round(total_demand, 1),
            "balance": balance,
        }
        self._store_calculation(
            "ELEC", [("NODE", panel.id, panel.revision)],
            {"connected_w": total_connected, "demand_w": total_demand,
             "main_breaker_a": main_breaker, "imbalance_pct": balance["imbalance_pct"]},
            {"connected_w": "W", "demand_w": "W", "main_breaker_a": "A",
             "imbalance_pct": "%"},
            parameters={"voltage": voltage, "phases": phases, "circuits": len(circuits)},
        )
        return result

    # -- sanitary (spec 28) ---------------------------------------------------------
    def _fixture_flow(self, node: InstallNode) -> float:
        if node.kind not in ("FIXTURE", "APPLIANCE"):
            return 0.0
        explicit = node.num("flow_ls")
        if explicit > 0:
            return explicit
        fixture_kind = str(node.attrs.get("fixture_kind", "")).upper()
        return FIXTURE_FLOW_LS.get(fixture_kind, 0.0)

    def _downstream_of(self, graph: NetworkGraph, node_id: str) -> List[str]:
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for neighbor in graph.adjacency.get(current, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        return list(seen)

    def _upstream_of(self, graph: NetworkGraph, node_id: str) -> List[str]:
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for neighbor in graph.reverse.get(current, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        return list(seen)

    def size_sanitary(self, network_ref: str) -> Dict[str, Any]:
        """Dimensiona la red: caudales, diámetros, pendientes y bombeo (spec 28)."""
        network, graph = self.graph_of(network_ref)
        nodes = graph.nodes
        segments = sorted(graph.segments.values(), key=lambda s: s.code)
        system = network.system
        rows: List[Dict[str, Any]] = []
        findings: List[str] = []

        if system in ("COLD_WATER", "HOT_WATER", "PUMPING"):
            for segment in segments:
                served_ids = [segment.to_node_id] + self._downstream_of(graph, segment.to_node_id)
                flows = [self._fixture_flow(nodes[nid]) for nid in served_ids
                         if nid in nodes]
                q = design_flow_ls(flows)
                diameter = segment.diameter_mm
                velocity = velocity_ms(q, diameter) if diameter else 0.0
                if diameter <= 0 and q > 0:
                    diameter, velocity = select_pressure_diameter(q, segment.material or "PVC")
                head = segment_head_loss_m(q, diameter, segment.length_m,
                                           segment.material or "PVC") if q > 0 else 0.0
                rows.append({
                    "segment": segment.code, "from": nodes[segment.from_node_id].code,
                    "to": nodes[segment.to_node_id].code,
                    "fixtures": len([f for f in flows if f > 0]),
                    "q_ls": q, "diameter_mm": diameter,
                    "velocity_ms": round(velocity, 2),
                    "head_loss_m": round(head, 3),
                    "length_m": round(segment.length_m, 2),
                })
                if velocity and velocity < 0.60:
                    findings.append(f"{segment.code}: velocidad {velocity:.2f} m/s baja (sedimentos)")
                if diameter != segment.diameter_mm:
                    segment.attrs["diameter_mm_suggested"] = diameter
        elif system in ("SANITARY_DRAINAGE", "STORMWATER"):
            for segment in segments:
                # Served fixtures are upstream of from_node in flow direction.
                upstream: set[str] = set()
                for node_id, node in nodes.items():
                    if node.kind not in ("FIXTURE", "APPLIANCE"):
                        continue
                    path = graph.trace(node_id, "converge_to_sink")
                    if segment.from_node_id in path or node_id == segment.from_node_id:
                        upstream.add(node_id)
                flows = [self._fixture_flow(nodes[nid]) for nid in upstream if nid in nodes]
                q = design_flow_ls(flows)
                diameter = segment.diameter_mm
                slope = segment.slope_pct
                capacity = manning_capacity_ls(diameter, slope, segment.material or "PVC") \
                    if diameter and slope > 0 else 0.0
                if q > 0 and (diameter <= 0 or capacity < q):
                    diameter, slope_needed, capacity = select_drain_diameter(
                        q, segment.material or "PVC")
                    if slope <= 0:
                        slope = slope_needed
                    if segment.slope_pct > 0 and segment.slope_pct < min_slope_pct(diameter):
                        findings.append(
                            f"{segment.code}: pendiente {segment.slope_pct:.2f} % menor que la "
                            f"mínima {min_slope_pct(diameter):.2f} % para DN{diameter:.0f}")
                rows.append({
                    "segment": segment.code, "from": nodes[segment.from_node_id].code,
                    "to": nodes[segment.to_node_id].code,
                    "fixtures": len([f for f in flows if f > 0]),
                    "q_ls": q, "diameter_mm": diameter, "slope_pct": slope,
                    "capacity_ls": round(capacity, 3),
                    "length_m": round(segment.length_m, 2),
                })
        else:
            raise DomainError(
                message=f"El sistema {system} no admite dimensionamiento automático todavía",
                code="ARQ-MEP-030")

        # Pumping / storage summary
        pump: Optional[Dict[str, Any]] = None
        tank: Optional[Dict[str, Any]] = None
        for node in nodes.values():
            if node.kind == "PUMP":
                worst = max((r["q_ls"] for r in rows), default=0.0)
                static = max((nodes[nid].elevation_m for nid in nodes
                              if nid in self._downstream_of(graph, node.id)), default=0.0) \
                    - node.elevation_m
                friction = sum(r.get("head_loss_m", 0.0) for r in rows)
                result_pump = size_pump(worst, max(static, 0.0), friction,
                                        node.num("residual_m", 5.0) or 5.0,
                                        node.num("efficiency", 0.7) or 0.7)
                pump = {"node": node.code, **result_pump.to_dict()}
            if node.kind == "TANK":
                volume = node.num("volume_l")
                if volume <= 0:
                    volume = tank_volume_ls(
                        node.num("l_per_person_day", 150.0),
                        int(node.num("persons", 0)) or 4,
                        node.num("autonomy_days", 1.0) or 1.0)
                tank = {"node": node.code, "volume_l": volume}

        values = {
            "segments": float(len(rows)),
            "max_q_ls": max((r["q_ls"] for r in rows), default=0.0),
            "total_length_m": sum(r["length_m"] for r in rows),
        }
        self._store_calculation(
            "SAN", [("NETWORK", network.id, network.revision)],
            values, {"max_q_ls": "L/s", "total_length_m": "m"},
            parameters={"system": system},
            errors=findings or None,
            status=CalculationStatus.COMPLETED if not findings else CalculationStatus.WARNING,
        )
        return {
            "network": network.code, "system": system, "rows": rows,
            "pump": pump, "tank": tank, "findings": findings,
        }

    # -- HVAC (spec 29) ----------------------------------------------------------------
    def _exposed_surfaces(self, space) -> Tuple[float, float]:
        """(exposed_wall_area, glazing_area) of a space by geometry."""
        level_id = space.level_id
        spaces = [s for s in self.ctx.architecture.list("SPACE", self.ctx.project.id)
                  if s.level_id == level_id]
        walls = [w for w in self.ctx.architecture.list("WALL", self.ctx.project.id)
                 if not w.level_id or w.level_id == level_id]
        openings = self.ctx.architecture.list("OPENING", self.ctx.project.id)
        from core.geometry.primitives import Point
        exposed_area = 0.0
        glazing_area = 0.0
        for wall in walls:
            mx, my = (wall.start[0] + wall.end[0]) / 2.0, (wall.start[1] + wall.end[1]) / 2.0
            dx, dy = wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]
            length = (dx * dx + dy * dy) ** 0.5 or 1e-9
            nx, ny = -dy / length, dx / length
            offset = wall.thickness_m / 2.0 + 0.05
            side_a = (mx + nx * offset, my + ny * offset)
            side_b = (mx - nx * offset, my - ny * offset)
            in_a = any(_polygon_contains(s, Point(*side_a)) for s in spaces)
            in_b = any(_polygon_contains(s, Point(*side_b)) for s in spaces)
            touches_space = (
                _polygon_contains(space, Point(*side_a)) or _polygon_contains(space, Point(*side_b)))
            shared = in_a and in_b
            if touches_space and not shared:
                exposed_area += wall.length_m * wall.height_m
                wall_openings = [o for o in openings if o.wall_id == wall.id]
                glazing_area += sum(o.width_m * o.height_m for o in wall_openings
                                    if o.kind == "WINDOW")
        return exposed_area, glazing_area

    def space_thermal_load(self, space_ref: str,
                           params: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        space = self.ctx.architecture.get_by_code("SPACE", space_ref) \
            or self.ctx.architecture.get("SPACE", space_ref)
        if space is None:
            for candidate in self.ctx.architecture.list("SPACE", self.ctx.project.id):
                if candidate.name.lower() == space_ref.lower():
                    space = candidate
                    break
        if space is None:
            raise DomainError(message=f"Local no encontrado: {space_ref}",
                              code="ARQ-MEP-015")
        level = self.ctx.architecture.get("LEVEL", space.level_id) if space.level_id else None
        height = level.height_m if level else 3.0
        exposed_wall, glazing = self._exposed_surfaces(space)
        # Roof exposed when this is the highest level with spaces.
        roof_area = space.area_m2()
        levels = sorted(self.ctx.architecture.list("LEVEL", self.ctx.project.id),
                        key=lambda l: l.elevation_m)
        if level and levels and levels[-1].id != level.id:
            roof_area = 0.0
        load = thermal_load(
            area_m2=space.area_m2(), height_m=height,
            exposed_wall_area_m2=exposed_wall, glazing_area_m2=glazing,
            roof_area_m2=roof_area, params=params)
        load.space_code = space.code
        selection = select_equipment(load.cooling_btu_h)
        airflow = calculate_airflow(load.cooling_sensible_w)
        self._store_calculation(
            "HVAC", [("SPACE", space.id, space.revision)],
            {"cooling_total_w": load.cooling_total_w,
             "cooling_btu_h": load.cooling_btu_h,
             "heating_w": load.heating_w, "airflow_m3h": airflow},
            {"cooling_total_w": "W", "cooling_btu_h": "BTU/h",
             "heating_w": "W", "airflow_m3h": "m3/h"},
            parameters=load.assumptions,
        )
        self.ctx.calculations_repo.mark_stale_for_object(space.id)
        return {
            **load.to_dict(),
            "airflow_m3h": airflow,
            "equipment": selection.to_dict(),
        }

    def hvac_loads_all(self) -> List[Dict[str, Any]]:
        rows = []
        for space in self.ctx.architecture.list("SPACE", self.ctx.project.id):
            try:
                rows.append(self.space_thermal_load(space.code))
            except Exception as exc:  # keep going; report per space
                rows.append({"space": space.code, "error": str(exc)})
        return rows

    def size_hvac_network(self, network_ref: str) -> Dict[str, Any]:
        """Dimensiona ductos de una red de aire por caudales acumulados (spec 29)."""
        network, graph = self.graph_of(network_ref)
        if network.system not in ("HVAC_SUPPLY", "HVAC_RETURN", "EXHAUST"):
            raise DomainError(
                message=f"La red {network.code} no es de aire ({network.system})",
                code="ARQ-MEP-031")
        nodes = graph.nodes
        rows: List[Dict[str, Any]] = []
        findings: List[str] = []
        converging = network.system in ("HVAC_RETURN", "EXHAUST")
        for segment in sorted(graph.segments.values(), key=lambda s: s.code):
            if converging:
                # Air collected from all grilles upstream of the segment start.
                served = [segment.from_node_id] + self._upstream_of(graph, segment.from_node_id)
            else:
                served = [segment.to_node_id] + self._downstream_of(graph, segment.to_node_id)
            airflow = sum(nodes[nid].num("air_flow_m3h") for nid in served if nid in nodes)
            if airflow <= 0:
                rows.append({"segment": segment.code, "airflow_m3h": 0.0,
                             "note": "sin difusores alimentados"})
                continue
            kind = str(segment.attrs.get("duct_kind", "BRANCH")).upper()
            shape = str(segment.attrs.get("shape", "ROUND")).upper()
            try:
                sizing = size_duct(airflow, kind=kind, shape=shape,
                                   target_velocity_ms=segment.num("v_target") or None)
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             **sizing.to_dict()})
                if not sizing.ok:
                    findings.extend(f"{segment.code}: {f}" for f in sizing.findings)
            except Exception as exc:
                findings.append(f"{segment.code}: {exc}")
        self._store_calculation(
            "HVAC", [("NETWORK", network.id, network.revision)],
            {"segments": float(len(rows)),
             "total_airflow_m3h": sum(r.get("airflow_m3h", 0.0) for r in rows)},
            {"total_airflow_m3h": "m3/h"},
            parameters={"system": network.system},
            errors=findings or None,
            status=CalculationStatus.COMPLETED if not findings else CalculationStatus.WARNING,
        )
        return {"network": network.code, "rows": rows, "findings": findings}

    # -- stormwater (spec 30) -------------------------------------------------------
    def _roof_drain_flow(self, node: InstallNode) -> float:
        """Captación de un sumidero de cubierta (método racional, captación)."""
        if node.kind != "ROOF_DRAIN":
            return 0.0
        area = node.num("area_m2")
        if area <= 0:
            return 0.0
        surface = str(node.attrs.get("surface", "ROOF"))
        intensity = node.num("intensity_mmh", DEFAULT_INTENSITY_MMH) or DEFAULT_INTENSITY_MMH
        coeff = node.num("runoff_coeff") or runoff_coefficient(surface)
        return runoff_ls(area, intensity, coeff)

    def size_stormwater(self, network_ref: str) -> Dict[str, Any]:
        """Dimensiona la red pluvial: captación, canalones, bajantes,
        colectores, detención y evacuación (spec 30)."""
        network, graph = self.graph_of(network_ref)
        if network.system != "STORMWATER":
            raise DomainError(
                message=f"La red {network.code} no es pluvial ({network.system})",
                code="ARQ-MEP-040")
        nodes = graph.nodes
        rows: List[Dict[str, Any]] = []
        findings: List[str] = []
        proposed: List[InstallSegment] = []

        # Caudal captado aguas arriba de cada nodo (captación).
        flow_at: Dict[str, float] = {}
        for node_id, node in nodes.items():
            flow_at[node_id] = self._roof_drain_flow(node)

        def upstream_flow(node_id: str) -> float:
            total = flow_at.get(node_id, 0.0)
            for upstream_id in self._upstream_of(graph, node_id):
                total += flow_at.get(upstream_id, 0.0)
            return total

        for segment in sorted(graph.segments.values(), key=lambda s: s.code):
            q = upstream_flow(segment.from_node_id)
            vertical = bool(segment.attrs.get("vertical"))
            if q <= 0:
                rows.append({
                    "segment": segment.code,
                    "from": nodes[segment.from_node_id].code,
                    "to": nodes[segment.to_node_id].code,
                    "q_ls": 0.0, "kind": "BAJANTE" if vertical else "COLECTOR",
                    "diameter_mm": segment.diameter_mm,
                    "slope_pct": segment.slope_pct, "capacity_ls": 0.0,
                    "note": "sin captación aguas arriba"})
                continue
            if vertical:
                # Bajante vertical: tabla de capacidad (bajantes).
                diameter = segment.diameter_mm
                capacity = downpipe_capacity_ls(diameter) if diameter else 0.0
                if diameter <= 0 or capacity < q:
                    suggested, capacity = select_downpipe(q)
                    if diameter <= 0:
                        diameter = suggested
                        segment.attrs["diameter_mm_suggested"] = suggested
                        proposed.append(segment)
                    elif capacity < q:
                        findings.append(
                            f"{segment.code}: bajante DN{segment.diameter_mm:.0f} con "
                            f"{capacity:.2f} L/s < captación {q:.2f} L/s")
                rows.append({
                    "segment": segment.code,
                    "from": nodes[segment.from_node_id].code,
                    "to": nodes[segment.to_node_id].code,
                    "q_ls": q, "kind": "BAJANTE", "diameter_mm": diameter,
                    "slope_pct": segment.slope_pct, "capacity_ls": capacity,
                })
            else:
                # Colector horizontal: Manning lámina 50 % (colectores).
                diameter = segment.diameter_mm
                slope = segment.slope_pct
                material = segment.material or "PVC"
                capacity = manning_capacity_ls(diameter, slope, material) \
                    if diameter and slope > 0 else 0.0
                if diameter <= 0 or capacity < q:
                    suggested, slope_needed, capacity = select_drain_diameter(q, material)
                    if diameter <= 0:
                        diameter = suggested
                        segment.attrs["diameter_mm_suggested"] = suggested
                    if slope <= 0:
                        slope = slope_needed
                        segment.attrs["slope_pct_suggested"] = slope_needed
                    proposed.append(segment)
                rows.append({
                    "segment": segment.code,
                    "from": nodes[segment.from_node_id].code,
                    "to": nodes[segment.to_node_id].code,
                    "q_ls": q, "kind": "COLECTOR", "diameter_mm": diameter,
                    "slope_pct": slope, "capacity_ls": round(capacity, 3),
                })

        # Canalones: capacidad frente a la captación que reciben (pendiente).
        gutters: List[Dict[str, Any]] = []
        for node in nodes.values():
            if node.kind != "GUTTER":
                continue
            inflow = upstream_flow(node.id)
            width = node.num("width_mm")
            depth = node.num("depth_mm")
            slope = node.num("slope_pct", MIN_GUTTER_SLOPE_PCT) or MIN_GUTTER_SLOPE_PCT
            if inflow <= 0:
                continue
            if width > 0 and depth > 0:
                capacity = gutter_capacity_ls(width, depth, slope)
                if capacity < inflow:
                    sw, sd, scap = select_gutter(inflow, slope)
                    findings.append(
                        f"{node.code}: canalón {width:.0f}x{depth:.0f} mm con "
                        f"{capacity:.2f} L/s < {inflow:.2f} L/s; sugerido "
                        f"{sw:.0f}x{sd:.0f} mm")
                    gutters.append({"node": node.code, "inflow_ls": inflow,
                                    "width_mm": width, "depth_mm": depth,
                                    "capacity_ls": round(capacity, 3),
                                    "suggested_width_mm": sw,
                                    "suggested_depth_mm": sd})
                else:
                    gutters.append({"node": node.code, "inflow_ls": inflow,
                                    "width_mm": width, "depth_mm": depth,
                                    "capacity_ls": round(capacity, 3)})
            else:
                sw, sd, scap = select_gutter(inflow, slope)
                gutters.append({"node": node.code, "inflow_ls": inflow,
                                "width_mm": 0.0, "depth_mm": 0.0,
                                "capacity_ls": 0.0,
                                "suggested_width_mm": sw,
                                "suggested_depth_mm": sd})

        # Almacenamiento de detención (almacenamiento).
        detention: Optional[Dict[str, Any]] = None
        for node in nodes.values():
            if node.kind == "TANK" and node.attrs.get("detention"):
                q = upstream_flow(node.id)
                retention = node.num("retention_min", DEFAULT_RETENTION_MIN) or DEFAULT_RETENTION_MIN
                result = detention_volume_ls(q, retention)
                detention = {"node": node.code, **result.to_dict()}

        # Evacuación: capacidad exigida al punto de evacuación (evacuación).
        total_q = sum(flow_at.values())
        outfall = outfall_required_capacity(total_q)
        self._persist_proposals(proposed)

        values = {
            "segments": float(len(rows)),
            "captured_ls": round(total_q, 4),
            "outfall_required_ls": outfall,
            "total_length_m": sum(r["q_ls"] * 0 for r in rows)
            + sum(s.length_m for s in graph.segments.values()),
        }
        self._store_calculation(
            "PLU", [("NETWORK", network.id, network.revision)],
            values, {"captured_ls": "L/s", "outfall_required_ls": "L/s",
                     "total_length_m": "m"},
            parameters={"system": network.system},
            errors=findings or None,
            status=CalculationStatus.COMPLETED if not findings else CalculationStatus.WARNING,
        )
        return {
            "network": network.code, "system": network.system, "rows": rows,
            "gutters": gutters, "detention": detention,
            "captured_ls": round(total_q, 3),
            "outfall_required_ls": outfall, "findings": findings,
        }

    # -- gas (spec 31) ----------------------------------------------------------------
    def _gas_appliance_flow(self, node: InstallNode) -> float:
        """Caudal de gas del aparato (puntos de consumo)."""
        if node.kind != "APPLIANCE":
            return 0.0
        power_kw = node.num("power_kw")
        if power_kw <= 0:
            return 0.0
        efficiency = node.num("efficiency", 1.0) or 1.0
        return gas_flow_m3h(power_kw, efficiency=efficiency)

    def size_gas(self, network_ref: str) -> Dict[str, Any]:
        """Dimensiona la red de gas: caudales, UC y diámetros (spec 31)."""
        network, graph = self.graph_of(network_ref)
        if network.system != "GAS":
            raise DomainError(
                message=f"La red {network.code} no es de gas ({network.system})",
                code="ARQ-MEP-041")
        nodes = graph.nodes
        rows: List[Dict[str, Any]] = []
        findings: List[str] = []
        appliances = [n for n in nodes.values() if n.kind == "APPLIANCE"]
        proposed: List[InstallSegment] = []
        for segment in sorted(graph.segments.values(), key=lambda s: s.code):
            served_ids = [segment.to_node_id] + self._downstream_of(graph, segment.to_node_id)
            q = sum(self._gas_appliance_flow(nodes[nid]) for nid in served_ids
                    if nid in nodes)
            uc = sum(consumption_units(nodes[nid].num("power_kw"))
                     for nid in served_ids if nid in nodes
                     and nodes[nid].kind == "APPLIANCE")
            length = segment.length_m
            diameter = segment.diameter_mm
            dp = 0.0
            velocity = 0.0
            if q <= 0:
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             "uc_served": 0.0, "q_m3h": 0.0,
                             "length_m": round(length, 2),
                             "diameter_mm": diameter,
                             "dp_pa": 0.0, "velocity_ms": 0.0,
                             "note": "sin aparatos alimentados"})
                continue
            if diameter > 0:
                dp = segment_dp_pa(q, diameter, length)
                velocity = velocity_ms(q, diameter)
                if dp > DP_BUDGET_PA:
                    suggested, dp_s, _v = select_gas_diameter(q, length)
                    findings.append(
                        f"{segment.code}: DN{diameter:.0f} pierde {dp:.0f} Pa > "
                        f"presupuesto {DP_BUDGET_PA:.0f} Pa; sugerido DN{suggested:.0f}")
                    segment.attrs["diameter_mm_suggested"] = suggested
                    proposed.append(segment)
                if velocity > MAX_GAS_VELOCITY_MS:
                    findings.append(
                        f"{segment.code}: velocidad {velocity:.2f} m/s > "
                        f"{MAX_GAS_VELOCITY_MS:.1f} m/s (ruido/impulsos)")
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             "uc_served": uc, "q_m3h": q,
                             "length_m": round(length, 2),
                             "diameter_mm": diameter,
                             "dp_pa": round(dp, 1),
                             "velocity_ms": round(velocity, 2)})
            else:
                suggested, dp, velocity = select_gas_diameter(q, length)
                segment.attrs["diameter_mm_suggested"] = suggested
                proposed.append(segment)
                if velocity < MIN_GAS_VELOCITY_MS:
                    findings.append(
                        f"{segment.code}: velocidad {velocity:.2f} m/s baja "
                        f"(suciedad/condensados)")
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             "uc_served": uc, "q_m3h": q,
                             "length_m": round(length, 2),
                             "diameter_mm": suggested,
                             "dp_pa": round(dp, 1),
                             "velocity_ms": round(velocity, 2)})
        total_q = sum(self._gas_appliance_flow(a) for a in appliances)
        self._persist_proposals(proposed)
        self._store_calculation(
            "GAS", [("NETWORK", network.id, network.revision)],
            {"segments": float(len(rows)), "appliances": float(len(appliances)),
             "total_q_m3h": round(total_q, 4),
             "installed_kw": sum(a.num("power_kw") for a in appliances)},
            {"total_q_m3h": "m3/h", "installed_kw": "kW"},
            parameters={"system": network.system},
            errors=findings or None,
            status=CalculationStatus.COMPLETED if not findings else CalculationStatus.WARNING,
        )
        return {"network": network.code, "rows": rows,
                "appliances": len(appliances), "findings": findings}

    def validate_gas(self, network_ref: str) -> Dict[str, Any]:
        """Validaciones del spec 31: diámetros, recorridos, válvulas,
        ventilación, separación y puntos de consumo."""
        network, graph = self.graph_of(network_ref)
        if network.system != "GAS":
            raise DomainError(
                message=f"La red {network.code} no es de gas ({network.system})",
                code="ARQ-MEP-041")
        nodes = graph.nodes
        segments = list(graph.segments.values())
        by_pair = {(s.from_node_id, s.to_node_id): s for s in segments}
        errors: List[str] = []
        warnings: List[str] = []
        infos: List[str] = []
        appliances = [n for n in nodes.values() if n.kind == "APPLIANCE"]

        # Diámetros (spec 31: diámetros).
        for segment in segments:
            diameter = segment.diameter_mm or segment.num("diameter_mm_suggested")
            if diameter <= 0:
                errors.append(f"{segment.code}: sin diámetro ni sugerencia "
                              f"(ejecute gas size)")
        # Recorridos, válvulas y ventilación por aparato.
        for appliance in appliances:
            path = graph.trace(appliance.id, "radial_from_source")
            path_nodes = [nodes[nid] for nid in path if nid in nodes]
            run_length = 0.0
            for index in range(len(path) - 1):
                seg = by_pair.get((path[index + 1], path[index]))
                if seg is not None:
                    run_length += seg.length_m
            if run_length > MAX_RUN_M + 1e-9:
                warnings.append(
                    f"{appliance.code}: recorrido {run_length:.1f} m > "
                    f"{MAX_RUN_M:.0f} m; revise pérdida de carga y accesibilidad")
            if not any(n.kind == "VALVE" for n in path_nodes):
                errors.append(f"{appliance.code}: sin válvula de paso accesible "
                              f"aguas arriba (válvulas)")
            power_kw = appliance.num("power_kw")
            if power_kw <= 0:
                warnings.append(f"{appliance.code}: sin potencia (power_kw) "
                                f"declarada; no se evalúa ventilación")
                continue
            required = 0.0
            room_area = 0.0
            if appliance.space_id:
                space = self.ctx.architecture.get("SPACE", appliance.space_id)
                if space is not None:
                    try:
                        room_area = abs(space.area_m2())
                    except Exception:
                        room_area = 0.0
            if room_area <= 0:
                room_area = appliance.num("room_area_m2")
            if room_area > 0:
                required = required_vent_area_m2(room_area)
                provided = appliance.num("vent_area_m2")
                if provided <= 0:
                    warnings.append(
                        f"{appliance.code}: ventilación no declarada "
                        f"(vent_area_m2); exigido ≥ {required:.3f} m2")
                elif provided + 1e-9 < required:
                    errors.append(
                        f"{appliance.code}: ventilación {provided:.3f} m2 < "
                        f"exigida {required:.3f} m2 (ventilación)")
            else:
                warnings.append(f"{appliance.code}: sin local asociado; "
                                f"ventilación no evaluable")

        # Separación gas ↔ eléctrico (spec 31: separación).
        electrical_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        electrical_nodes: List[Tuple[float, float]] = []
        for other in self.ctx.installations.list("NETWORK", self.ctx.project.id):
            if other.discipline != "ELECTRICAL":
                continue
            for seg in self.ctx.installations.segments_of(other.id):
                a = graph.nodes.get(seg.from_node_id)
                b = graph.nodes.get(seg.to_node_id)
                if a is not None:
                    electrical_nodes.append((a.x, a.y))
                if b is not None:
                    electrical_nodes.append((b.x, b.y))
                na = self.ctx.installations.get("NODE", seg.from_node_id)
                nb = self.ctx.installations.get("NODE", seg.to_node_id)
                if na and nb:
                    electrical_segments.append(((na.x, na.y), (nb.x, nb.y)))
        for seg in segments:
            na = nodes.get(seg.from_node_id)
            nb = nodes.get(seg.to_node_id)
            if na is None or nb is None:
                continue
            line = ((na.x, na.y), (nb.x, nb.y))
            for e_line in electrical_segments:
                distance = _segment_distance(line, e_line)
                if distance < SEPARATION_M - 1e-9:
                    errors.append(
                        f"{seg.code}: cruza o se aproxima a canalización eléctrica "
                        f"({distance * 100:.0f} cm < {SEPARATION_M * 100:.0f} cm; separación)")
                    break
            else:
                for e_point in electrical_nodes:
                    distance = _point_segment_distance(e_point, line)
                    if 0.0 < distance < SEPARATION_M - 1e-9:
                        warnings.append(
                            f"{seg.code}: nodo eléctrico a {distance * 100:.0f} cm "
                            f"de la tubería de gas (mínimo "
                            f"{SEPARATION_M * 100:.0f} cm; separación)")
                        break

        # Puntos de consumo (spec 31: puntos de consumo).
        infos.append(f"Puntos de consumo conectados: {len(appliances)} "
                     f"({sum(a.num('power_kw') for a in appliances):.1f} kW instalados)")

        status = "INVALID" if errors else ("VALID_WITH_WARNINGS" if warnings else "VALID")
        self._store_calculation(
            "GAS", [("NETWORK", network.id, network.revision)],
            {"appliances": float(len(appliances)), "segments": float(len(segments)),
             "errors": float(len(errors)), "warnings": float(len(warnings))},
            {"appliances": "und"},
            parameters={"system": network.system, "validation": True},
            errors=(errors + warnings) or None,
            status=CalculationStatus.FAILED if errors
            else (CalculationStatus.WARNING if warnings else CalculationStatus.COMPLETED),
        )
        return {
            "network": network.code, "system": network.system,
            "status": status, "errors": errors, "warnings": warnings,
            "infos": infos,
        }

    # -- telecom (spec 32) ----------------------------------------------------------------
    def size_telecom(self, network_ref: str) -> Dict[str, Any]:
        """Dimensiona la red de telecomunicaciones: llenado de canalización,
        enlaces horizontales, fibra, racks y puertos (spec 32)."""
        network, graph = self.graph_of(network_ref)
        if network.system != "TELECOM":
            raise DomainError(
                message=f"La red {network.code} no es de telecomunicaciones "
                        f"({network.system})", code="ARQ-MEP-042")
        nodes = graph.nodes
        rows: List[Dict[str, Any]] = []
        findings: List[str] = []
        proposed: List[InstallSegment] = []
        outlets_of = lambda node_id: [  # noqa: E731
            nodes[nid] for nid in self._outlet_ids_at_or_below(graph, node_id)]

        for segment in sorted(graph.segments.values(), key=lambda s: s.code):
            if segment.kind == "FIBER":
                connectors = int(segment.num("connectors", 2))
                splices = int(segment.num("splices", 0))
                budget = segment.num("budget_db", FIBER_DEFAULT_BUDGET_DB) or FIBER_DEFAULT_BUDGET_DB
                fiber_findings = fiber_budget_findings(segment.length_m, connectors,
                                                       splices, budget)
                findings.extend(f"{segment.code}: {f}" for f in fiber_findings)
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             "kind": "FIBER",
                             "length_m": round(segment.length_m, 2),
                             "loss_db": fiber_loss_db(segment.length_m, connectors, splices),
                             "budget_db": budget})
                continue
            if segment.kind == "CABLE":
                category = str(segment.attrs.get("cable_type", "CAT6"))
                link_findings = link_length_findings(segment.length_m, category)
                findings.extend(f"{segment.code}: {f}" for f in link_findings)
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             "kind": "CABLE", "cable_type": category,
                             "length_m": round(segment.length_m, 2)})
                continue
            if segment.kind in ("CONDUIT", "CABLE_TRAY"):
                # Cables transportados = rosetas alimentadas aguas abajo.
                cables_served = len(outlets_of(segment.to_node_id))
                if "cables" not in segment.attrs and cables_served > 0:
                    segment.attrs["cables"] = cables_served
                    proposed.append(segment)
                cables = int(segment.num("cables", cables_served) or cables_served)
                if cables <= 0:
                    rows.append({"segment": segment.code,
                                 "from": nodes[segment.from_node_id].code,
                                 "to": nodes[segment.to_node_id].code,
                                 "kind": "CONDUIT", "cables": 0,
                                 "fill_pct": 0.0,
                                 "note": "sin rosetas alimentadas"})
                    continue
                category = str(segment.attrs.get("cable_type", "CAT6"))
                cable_d = cable_diameter_mm(category)
                diameter = segment.diameter_mm
                fill = 0.0
                if diameter > 0:
                    fill = conduit_fill_pct(cables, cable_d, diameter)
                    if fill > TELECOM_FILL_LIMIT_PCT + 1e-9:
                        suggested, s_fill = select_telecom_conduit(cables, cable_d)
                        findings.append(
                            f"{segment.code}: llenado {fill:.1f} % > "
                            f"{TELECOM_FILL_LIMIT_PCT:.0f} %; sugerido "
                            f"Ø{suggested:.0f} mm")
                        segment.attrs["conduit_id_suggested"] = suggested
                        proposed.append(segment)
                else:
                    diameter, fill = select_telecom_conduit(cables, cable_d)
                    segment.attrs["conduit_id_suggested"] = diameter
                    proposed.append(segment)
                rows.append({"segment": segment.code,
                             "from": nodes[segment.from_node_id].code,
                             "to": nodes[segment.to_node_id].code,
                             "kind": "CONDUIT", "cable_type": category,
                             "cables": cables, "conduit_id_mm": diameter,
                             "fill_pct": fill})

        # Racks y puertos (spec 32: Rack/PatchPanel/Switch/Outlet).
        racks: List[Dict[str, Any]] = []
        panels: List[Dict[str, Any]] = []
        for node in nodes.values():
            if node.kind == "RACK":
                devices = [nodes[nid].kind for nid in self._circuit_device_ids(graph, node.id)
                           if nodes[nid].role == "EQUIPMENT"]
                capacity = node.num("u_capacity", DEFAULT_RACK_U) or DEFAULT_RACK_U
                summary = rack_summary(node.code, capacity, tuple(devices))
                findings.extend(f"{node.code}: {f}" for f in summary.findings)
                racks.append(summary.to_dict())
            if node.kind == "PATCH_PANEL":
                ports = int(node.num("ports", PATCH_PANEL_PORTS) or PATCH_PANEL_PORTS)
                used = len(outlets_of(node.id))
                usage = port_usage(ports, used)
                if used > ports:
                    findings.append(
                        f"{node.code}: {used} rosetas > {ports} puertos del patch panel")
                panels.append({"node": node.code, **usage})
            if node.kind == "TELECOM_SWITCH":
                ports = int(node.num("ports", SWITCH_PORTS) or SWITCH_PORTS)
                used = len(outlets_of(node.id))
                usage = port_usage(ports, used)
                if used > ports:
                    findings.append(
                        f"{node.code}: {used} rosetas > {ports} puertos del switch")
                panels.append({"node": node.code, **usage})

        self._persist_proposals(proposed)
        self._store_calculation(
            "TEL", [("NETWORK", network.id, network.revision)],
            {"segments": float(len(rows)), "outlets": float(sum(
                1 for n in nodes.values() if n.kind == "TELECOM_OUTLET")),
             "racks": float(len(racks)),
             "cable_m": sum(r.get("length_m", 0.0) for r in rows
                            if r.get("kind") in ("CONDUIT", "CABLE"))},
            {"outlets": "und", "racks": "und", "cable_m": "m"},
            parameters={"system": network.system},
            errors=findings or None,
            status=CalculationStatus.COMPLETED if not findings else CalculationStatus.WARNING,
        )
        return {"network": network.code, "rows": rows, "racks": racks,
                "panels": panels, "findings": findings}

    def _circuit_device_ids(self, graph: NetworkGraph, root_id: str) -> List[str]:
        """Ids de equipos/terminales alimentados desde un nodo (radial)."""
        devices: List[str] = []
        stack = list(graph.adjacency.get(root_id, []))
        while stack:
            node_id = stack.pop()
            node = graph.nodes.get(node_id)
            if node is None:
                continue
            if node.role in ("EQUIPMENT", "TERMINAL"):
                devices.append(node_id)
            stack.extend(graph.adjacency.get(node_id, []))
        return devices

    def _outlet_ids_at_or_below(self, graph: NetworkGraph, node_id: str) -> List[str]:
        """Rosetas en el nodo o aguas abajo de él (canalización de telecom)."""
        found: List[str] = []
        node = graph.nodes.get(node_id)
        if node is not None and node.kind == "TELECOM_OUTLET":
            found.append(node_id)
        stack = list(graph.adjacency.get(node_id, []))
        while stack:
            current = stack.pop()
            current_node = graph.nodes.get(current)
            if current_node is None:
                continue
            if current_node.kind == "TELECOM_OUTLET":
                found.append(current)
            stack.extend(graph.adjacency.get(current, []))
        return found


def _ampacity_of(section_mm2: float) -> float:
    from engines.electrical_engine import AMPACITY_CU
    return AMPACITY_CU.get(section_mm2, 0.0)


def _point_segment_distance(point: Tuple[float, float],
                            line: Tuple[Tuple[float, float], Tuple[float, float]]) -> float:
    """Distancia punto-segmento en metros (para la separación de gas)."""
    (px, py) = point
    (ax, ay), (bx, by) = line
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _segment_distance(line_a: Tuple[Tuple[float, float], Tuple[float, float]],
                      line_b: Tuple[Tuple[float, float], Tuple[float, float]]) -> float:
    """Distancia entre dos segmentos (aproximación por extremos y cruce)."""
    (a1, a2), (b1, b2) = line_a, line_b
    # Zero distance when the segments properly intersect.
    if _segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        _point_segment_distance(a1, line_b),
        _point_segment_distance(a2, line_b),
        _point_segment_distance(b1, line_a),
        _point_segment_distance(b2, line_a),
    )


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """Intersección propia de segmentos (producto cruzado estándar)."""
    def cross(ox, oy, ax, ay, bx, by):
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

    d1 = cross(p3[0], p3[1], p4[0], p4[1], p1[0], p1[1])
    d2 = cross(p3[0], p3[1], p4[0], p4[1], p2[0], p2[1])
    d3 = cross(p1[0], p1[1], p2[0], p2[1], p3[0], p3[1])
    d4 = cross(p1[0], p1[1], p2[0], p2[1], p4[0], p4[1])
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _polygon_contains(space, point) -> bool:
    try:
        from core.geometry.engine import contains
        return contains(space.polygon(), point)
    except Exception:
        return False


__all__ = ["InstallationsService"]
