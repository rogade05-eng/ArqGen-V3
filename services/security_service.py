"""SecurityService (spec sections 37-49, 76, 82, 102).

Facade of the security module: CCTV, fire, intrusion, access control
and perimeter. Reuses the ONE unique semantic model — devices are nodes
of the installations networks with security systems (CCTV, FIRE_ALARM,
INTRUSION, ACCESS_CONTROL, PERIMETER) and cabling goes through the
routing engine (spec 26). Nothing is duplicated (spec 37).

All mutations delegate to InstallationsService (CommandBus, audit,
events, QTO invalidation). Security calculations produce reproducible
CalculationResult records (calculation type SEC, spec 102) and follow
the propagation pattern of spec 49: move a camera → recalculate FOV →
blind spots → cabling → quantities → budget (via QTO invalidation).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from core.calculations.contracts import CalculationMode, CalculationResult, CalculationStatus
from core.errors import DomainError
from domain.installations import InstallNetwork, InstallNode, InstallSegment, SYSTEMS
from engines.access_engine import evacuation_check, power_report
from engines.cctv_engine import SERVICE_LOOP_M, cabling_report, network_report
from engines.fire_engine import check_space_coverage, evaluate_cause_effect, loop_report
from engines.intrusion_engine import check_zone, panel_report
from engines.fov_engine import blind_spots, field_of_view, target_detection
from engines.perimeter_engine import check_perimeter
from engines.routing_engine import RoutingEngine
from services.context import ProjectContext
from services.installations_service import InstallationsService

SECURITY_SYSTEMS: Tuple[str, ...] = ("CCTV", "FIRE_ALARM", "INTRUSION",
                                     "ACCESS_CONTROL", "PERIMETER")
CAUSE_EFFECT_RESOURCE = "fire_cause_effect_v1"


class SecurityService:
    """Facade of the security module (spec 37-49)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context
        self.installations = InstallationsService(context)
        self.router = RoutingEngine()

    # -- helpers -----------------------------------------------------------
    def _store_calculation(self, values: Dict[str, float], units: Dict[str, str],
                           objects: List[Tuple[str, str, int]],
                           parameters: Optional[Dict[str, Any]] = None,
                           errors: Optional[List[str]] = None,
                           status: CalculationStatus = CalculationStatus.COMPLETED
                           ) -> CalculationResult:
        result = CalculationResult(
            calculation_type="SEC",
            input_objects=[{"type": t, "id": i, "revision": r} for t, i, r in objects],
            parameters=parameters or {},
            values={k: round(v, 4) for k, v in values.items()},
            units=units, errors=errors or [], mode=CalculationMode.BALANCED,
            status=status, objects_processed=len(objects))
        self.ctx.calculations_repo.save(result, self.ctx.project.id)
        return result

    def resolve_network(self, ref: str) -> InstallNetwork:
        return self.installations.resolve_network(ref)

    def _devices_of(self, network: InstallNetwork) -> List[InstallNode]:
        return self.ctx.installations.nodes_of(network.id)

    def _segments_of(self, network: InstallNetwork) -> List[InstallSegment]:
        return self.ctx.installations.segments_of(network.id)

    # -- CRUD delegation (mismos comandos, auditoría y eventos del núcleo) ----
    def create_network(self, name: str, system: str, description: str = ""
                       ) -> InstallNetwork:
        if system not in SECURITY_SYSTEMS:
            raise DomainError(
                message=f"Sistema de seguridad desconocido: {system}",
                code="ARQ-SEC-001", context={"allowed": list(SECURITY_SYSTEMS)})
        return self.installations.create_network(name, system,
                                                 description=description)

    def add_device(self, network_ref: str, kind: str, x: float, y: float,
                   name: str = "", elevation_m: float = 0.0,
                   attrs: Optional[Dict[str, Any]] = None,
                   level_ref: str = "", space_ref: str = "") -> InstallNode:
        return self.installations.add_node(
            network_ref, kind, x, y, name=name, elevation_m=elevation_m,
            attrs=attrs or {}, level_ref=level_ref, space_ref=space_ref)

    def move_device(self, device_ref: str, x: float, y: float) -> InstallNode:
        """Mover dispositivo → propaga a FOV, cable y cantidades (spec 49)."""
        return self.installations.move_node(device_ref, x, y)

    def connect_devices(self, network_ref: str, from_ref: str, to_ref: str,
                        kind: str = "SEC_CABLE",
                        attrs: Optional[Dict[str, Any]] = None) -> InstallSegment:
        return self.installations.connect(network_ref, from_ref, to_ref,
                                          kind=kind, attrs=attrs or {})

    # -- CCTV: cobertura (spec 39-40) --------------------------------------------
    def _walls_of_level(self, level_id: Optional[str]):
        return self.installations._wall_obstacles(level_id)

    def cctv_coverage(self, network_ref: str,
                      space_ref: str = "") -> Dict[str, Any]:
        """FOV de cada cámara y puntos ciegos del objetivo (spec 39).

        El objetivo por defecto es el bounding box de los locales del
        nivel de las cámaras; con space_ref se evalúa un local concreto.
        """
        from core.geometry.engine import bounding_box
        network = self.resolve_network(network_ref)
        if network.system != "CCTV":
            raise DomainError(
                message=f"La red {network.code} no es CCTV ({network.system})",
                code="ARQ-SEC-010")
        cameras = [n for n in self._devices_of(network) if n.kind in
                   ("CAMERA", "PERIMETER_CAMERA")]
        if not cameras:
            raise DomainError(
                message=f"La red {network.code} no tiene cámaras",
                code="ARQ-SEC-011")
        walls = [((o.start[0], o.start[1]), (o.end[0], o.end[1]))
                 for o in self._walls_of_level(network.level_id)]
        coverages = []
        for camera in cameras:
            direction = camera.num("direction_deg", 0.0)
            fov = camera.num("fov_deg", 90.0) or 90.0
            range_m = camera.num("range_m", 12.0) or 12.0
            coverage = field_of_view(camera.code, (camera.x, camera.y),
                                     direction, fov, range_m, walls)
            coverages.append(coverage)
        # Objetivo: local concreto o nivel completo (bounding de locales).
        if space_ref:
            space = (self.ctx.architecture.get_by_code("SPACE", space_ref)
                     or self.ctx.architecture.get("SPACE", space_ref))
            if space is None:
                raise DomainError(message=f"Local no encontrado: {space_ref}",
                                  code="ARQ-DOM-001")
            target_points = [tuple(p) for p in space.boundary]
        else:
            spaces = self.ctx.architecture.list("SPACE", self.ctx.project.id)
            points: List[Tuple[float, float]] = []
            for space in spaces:
                points.extend(tuple(p) for p in space.boundary)
            if points:
                min_x = min(p[0] for p in points)
                min_y = min(p[1] for p in points)
                max_x = max(p[0] for p in points)
                max_y = max(p[1] for p in points)
                target_points = [(min_x, min_y), (max_x, min_y),
                                 (max_x, max_y), (min_x, max_y)]
            else:
                target_points = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        blind = blind_spots(target_points, coverages)
        rows = []
        for coverage in coverages:
            rows.append({
                "camera": coverage.camera,
                "area_m2": round(coverage.area_m2, 2),
                "fov_deg": coverage.fov_deg,
                "range_m": coverage.range_m,
                "occluded_rays": coverage.occluded_walls,
            })
        # Cámara con más área para optimización (spec 40: alternativas).
        candidates = sorted(rows, key=lambda r: -r["area_m2"])
        self._store_calculation(
            {"coverage_m2": sum(r["area_m2"] for r in rows),
             "blind_pct": blind["blind_pct"]},
            {"coverage_m2": "m2", "blind_pct": "%"},
            [("NETWORK", network.id, network.revision)],
            parameters={"cameras": len(cameras), "target": space_ref or "level"})
        self.ctx.commit()
        return {"network": network.code, "cameras": len(cameras), "rows": rows,
                "blind": blind, "best_camera": candidates[0] if candidates else None}

    def cctv_candidates(self, network_ref: str, space_ref: str,
                        grid_m: float = 1.0) -> Dict[str, Any]:
        """Candidatos de posición para optimización (spec 40)."""
        network = self.resolve_network(network_ref)
        if network.system != "CCTV":
            raise DomainError(
                message=f"La red {network.code} no es CCTV ({network.system})",
                code="ARQ-SEC-010")
        space = (self.ctx.architecture.get_by_code("SPACE", space_ref)
                 or self.ctx.architecture.get("SPACE", space_ref))
        if space is None:
            raise DomainError(message=f"Local no encontrado: {space_ref}",
                              code="ARQ-DOM-001")
        from engines.fov_engine import camera_position_candidates
        walls = [((o.start[0], o.start[1]), (o.end[0], o.end[1]))
                 for o in self._walls_of_level(network.level_id)]
        candidates = camera_position_candidates(
            [tuple(p) for p in space.boundary],
            direction_deg=0.0,
            fov_deg=90.0, range_m=12.0, walls=walls, grid_m=grid_m)
        return {"network": network.code, "space": space.code,
                "candidates": [[list(pos), round(area, 2)] for pos, area in candidates[:12]]}

    # -- CCTV: cableado y red (spec 41-42) ------------------------------------------
    def cctv_cabling(self, network_ref: str) -> Dict[str, Any]:
        """Cableado por cámara: ruta + rulo + desnivel + reserva (spec 41)."""
        network = self.resolve_network(network_ref)
        if network.system != "CCTV":
            raise DomainError(
                message=f"La red {network.code} no es CCTV ({network.system})",
                code="ARQ-SEC-010")
        nodes = {n.id: n for n in self._devices_of(network)}
        cameras = [n for n in nodes.values()
                   if n.kind in ("CAMERA", "PERIMETER_CAMERA")]
        if not cameras:
            raise DomainError(message=f"La red {network.code} no tiene cámaras",
                              code="ARQ-SEC-011")
        rise = max((n.elevation_m for n in nodes.values()), default=0.0)
        rows = []
        route_lengths = []
        for camera in cameras:
            # Ruta por cableado real de la red (tramos aguas arriba).
            route = self._upstream_route_length(network, camera)
            route_lengths.append(route)
            rows.append({"camera": camera.code, "route_m": round(route, 2),
                         "cable_m": None})
        report = cabling_report(route_lengths, vertical_rise_m=rise)
        cameras_count = max(len(cameras), 1)
        reserve_factor = 1.0 + 10.0 / 100.0   # INSTALL_RESERVE_PCT
        for row, route in zip(rows, route_lengths):
            # Cable por cámara: (ruta + rulo proporcional + desnivel) × 1,10.
            row["cable_m"] = round((route + SERVICE_LOOP_M
                                    + rise) * reserve_factor, 2)
        self._store_calculation(
            {"total_cable_m": report.total_cable_m,
             "cameras": float(report.cameras)},
            {"total_cable_m": "m", "cameras": "und"},
            [("NETWORK", network.id, network.revision)],
            parameters={"vertical_rise_m": rise})
        self.ctx.commit()
        return {"network": network.code, "rows": rows,
                "totals": report.to_dict()}

    def _upstream_route_length(self, network: InstallNetwork,
                               node: InstallNode) -> float:
        """Longitud de ruta aguas arriba de un dispositivo (cable tendido)."""
        segments = self._segments_of(network)
        by_to: Dict[str, List[InstallSegment]] = {}
        for segment in segments:
            by_to.setdefault(segment.to_node_id, []).append(segment)
        total = 0.0
        current = node.id
        visited = set()
        while current in by_to and current not in visited:
            visited.add(current)
            segment = by_to[current][0]
            total += segment.length_m
            current = segment.from_node_id
        return total

    def cctv_network(self, network_ref: str,
                     retention_days: float = 30.0) -> Dict[str, Any]:
        """Red CCTV: bandwidth, PoE, storage y capacidad (spec 42)."""
        network = self.resolve_network(network_ref)
        if network.system != "CCTV":
            raise DomainError(
                message=f"La red {network.code} no es CCTV ({network.system})",
                code="ARQ-SEC-010")
        cameras = [n for n in self._devices_of(network)
                   if n.kind in ("CAMERA", "PERIMETER_CAMERA")]
        if not cameras:
            raise DomainError(message=f"La red {network.code} no tiene cámaras",
                              code="ARQ-SEC-011")
        resolutions = [str(n.attrs.get("resolution", "1080P")) for n in cameras]
        report = network_report(resolutions, retention_days=retention_days)
        self._store_calculation(
            {"bandwidth_mbps": report.bandwidth_mbps,
             "storage_gb": report.storage_gb,
             "poe_demand_w": report.poe_demand_w},
            {"bandwidth_mbps": "Mbps", "storage_gb": "GB", "poe_demand_w": "W"},
            [("NETWORK", network.id, network.revision)],
            parameters={"retention_days": retention_days,
                        "cameras": len(cameras)},
            errors=report.findings,
            status=CalculationStatus.WARNING if report.findings
            else CalculationStatus.COMPLETED)
        self.ctx.commit()
        return {"network": network.code, "report": report.to_dict()}

    # -- FIRE (spec 43-44) ------------------------------------------------------------
    def fire_check(self, network_ref: str) -> Dict[str, Any]:
        """Cobertura por local, lazo y batería (spec 43)."""
        network = self.resolve_network(network_ref)
        if network.system != "FIRE_ALARM":
            raise DomainError(
                message=f"La red {network.code} no es detección de incendios "
                        f"({network.system})", code="ARQ-SEC-012")
        devices = self._devices_of(network)
        detectors = [n for n in devices if n.kind in
                     ("SMOKE_DETECTOR", "HEAT_DETECTOR", "BEAM_DETECTOR")]
        spaces = {s.id: s for s in
                  self.ctx.architecture.list("SPACE", self.ctx.project.id)}
        by_space: Dict[str, List[InstallNode]] = {}
        for detector in detectors:
            by_space.setdefault(detector.space_id or "", []).append(detector)
        coverage_rows = []
        findings: List[str] = []
        for space_id, group in by_space.items():
            space = spaces.get(space_id)
            if space is None:
                findings.append(f"{len(group)} detector(es) sin local asignado")
                continue
            report = check_space_coverage(
                space.code, space.area_m2(), len(group),
                kind=group[0].kind,
                ceiling_height_m=3.0)
            coverage_rows.append(report.to_dict())
            findings.extend(report.findings)
        loop = loop_report([n.kind for n in devices])
        findings.extend(loop.findings)
        status = "INVALID" if any("sin local" in f or "exige" in f
                                  for f in findings) else (
            "VALID" if not findings else "VALID_WITH_WARNINGS")
        self._store_calculation(
            {"devices": float(loop.devices),
             "battery_ah": loop.battery_ah,
             "standby_ma": loop.standby_ma},
            {"devices": "und", "battery_ah": "Ah", "standby_ma": "mA"},
            [("NETWORK", network.id, network.revision)],
            parameters={"detectors": len(detectors)},
            errors=findings,
            status=CalculationStatus.WARNING if findings
            else CalculationStatus.COMPLETED)
        self.ctx.commit()
        return {"network": network.code, "status": status,
                "coverage": coverage_rows, "loop": loop.to_dict(),
                "findings": findings}

    def fire_cause_effect(self, network_ref: str, input_event: str,
                          context_vars: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, Any]:
        """Matriz causa/efecto del ruleset (spec 44)."""
        network = self.resolve_network(network_ref)
        if network.system != "FIRE_ALARM":
            raise DomainError(
                message=f"La red {network.code} no es detección de incendios "
                        f"({network.system})", code="ARQ-SEC-012")
        rules = self._load_cause_effect_rules()
        result = evaluate_cause_effect(input_event, context_vars or {}, rules)
        self._store_calculation(
            {"actions": float(len(result.triggered))},
            {"actions": "und"},
            [("NETWORK", network.id, network.revision)],
            parameters={"input": input_event},
            errors=result.missing_rules,
            status=CalculationStatus.WARNING if result.missing_rules
            else CalculationStatus.COMPLETED)
        return {"network": network.code, "input": input_event,
                "result": result.to_dict()}

    def _load_cause_effect_rules(self) -> List[Dict[str, Any]]:
        from app.paths import resource_path
        path = resource_path("rulesets", f"{CAUSE_EFFECT_RESOURCE}.json")
        if not os.path.exists(path):
            raise DomainError(
                message=f"Ruleset causa/efecto no encontrado: {path}",
                code="ARQ-FIR-003")
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("rules", [])

    # -- INTRUSIÓN (spec 45) ----------------------------------------------------------
    def intrusion_check(self, network_ref: str) -> Dict[str, Any]:
        """Zonificación, cobertura PIR y panel (spec 45)."""
        network = self.resolve_network(network_ref)
        if network.system != "INTRUSION":
            raise DomainError(
                message=f"La red {network.code} no es intrusión ({network.system})",
                code="ARQ-SEC-013")
        devices = self._devices_of(network)
        zones: Dict[str, Dict[str, Any]] = {}
        for device in devices:
            zone_name = str(device.attrs.get("zone", "ZONA-1"))
            zone = zones.setdefault(zone_name, {"pirs": 0, "area": 0.0,
                                                "contacts": 0, "openings": 0})
            if device.kind == "PIR":
                zone["pirs"] += 1
            elif device.kind == "MAGNETIC_CONTACT":
                zone["contacts"] += 1
        # Áreas por zona: locales vinculados a los dispositivos (una vez
        # por espacio aunque compartan varios detectores).
        spaces = {s.id: s for s in
                  self.ctx.architecture.list("SPACE", self.ctx.project.id)}
        counted: set = set()
        for device in devices:
            zone_name = str(device.attrs.get("zone", "ZONA-1"))
            if device.space_id and device.space_id in spaces \
                    and (zone_name, device.space_id) not in counted:
                zones[zone_name]["area"] += spaces[device.space_id].area_m2()
                counted.add((zone_name, device.space_id))
        # Vanos perimetrales de los locales con contacto magnético:
        # se cuenta 1 apertura exterior por contacto declarado en exterior.
        from domain.model import Door, Window
        for device in devices:
            zone_name = str(device.attrs.get("zone", "ZONA-1"))
            if device.kind == "MAGNETIC_CONTACT" and device.attrs.get("external"):
                zones[zone_name]["openings"] += 1
        rows = []
        findings: List[str] = []
        for zone_name, data in sorted(zones.items()):
            if data["pirs"] == 0 and data["contacts"] == 0:
                continue
            report = check_zone(zone_name, data["area"], data["pirs"],
                                data["contacts"], data["openings"])
            report.spaces = 1
            rows.append(report.to_dict())
            findings.extend(report.findings)
        panel = panel_report(
            zones=len(zones),
            partitions=[],
            expanders=sum(1 for d in devices if d.kind == "EXPANDER"),
            sirens=sum(1 for d in devices if d.kind == "SIREN"))
        findings.extend(panel.findings)
        status = "INVALID" if any("exigidos" in f or "límite" in f
                                  for f in findings) else (
            "VALID" if not findings else "VALID_WITH_WARNINGS")
        self._store_calculation(
            {"zones": float(len(zones)), "devices": float(len(devices)),
             "battery_ah": panel.battery_ah},
            {"zones": "und", "devices": "und", "battery_ah": "Ah"},
            [("NETWORK", network.id, network.revision)],
            errors=findings,
            status=CalculationStatus.WARNING if findings
            else CalculationStatus.COMPLETED)
        self.ctx.commit()
        return {"network": network.code, "status": status, "zones": rows,
                "panel": panel.to_dict(), "findings": findings}

    # -- ACCESO (spec 46) ----------------------------------------------------------------
    def access_check(self, network_ref: str) -> Dict[str, Any]:
        """Controladores, alimentación y evacuación (spec 46)."""
        network = self.resolve_network(network_ref)
        if network.system != "ACCESS_CONTROL":
            raise DomainError(
                message=f"La red {network.code} no es control de acceso "
                        f"({network.system})", code="ARQ-SEC-014")
        devices = self._devices_of(network)
        controllers = [n for n in devices if n.kind == "ACCESS_CONTROLLER"]
        locks = [n for n in devices if n.kind == "LOCK"]
        readers = [n for n in devices if n.kind == "READER"]
        rows = []
        findings: List[str] = []
        for controller in controllers:
            own_readers = controller.num("readers") or self._children_count(
                network, controller, "READER")
            own_locks = controller.num("locks") or self._children_count(
                network, controller, "LOCK")
            from engines.access_engine import check_controller
            report = check_controller(controller.code, int(own_readers),
                                      int(own_locks))
            rows.append(report.to_dict())
            findings.extend(report.findings)
        power = power_report(len(controllers), len(locks),
                             supply_a=controllers[0].num("supply_a", 2.0)
                             if controllers else 2.0)
        findings.extend(power.findings)
        # Integración con arquitectura: puertas de evacuación (fuego).
        for lock in locks:
            if lock.attrs.get("evacuation"):
                unlock = lock.num("unlock_s", 0.5)
                check = evacuation_check(True, unlock, lock.code)
                if not check["ok"]:
                    findings.extend(check["findings"])
        status = "VALID" if not findings else "VALID_WITH_WARNINGS"
        self._store_calculation(
            {"controllers": float(len(controllers)),
             "locks": float(len(locks)), "demand_a": power.demand_a,
             "battery_ah": power.battery_ah},
            {"controllers": "und", "locks": "und", "demand_a": "A",
             "battery_ah": "Ah"},
            [("NETWORK", network.id, network.revision)],
            errors=findings,
            status=CalculationStatus.WARNING if findings
            else CalculationStatus.COMPLETED)
        self.ctx.commit()
        return {"network": network.code, "status": status,
                "controllers": rows, "power": power.to_dict(),
                "findings": findings}

    def _children_count(self, network: InstallNetwork, parent: InstallNode,
                        kind: str) -> int:
        """Dispositivos de un kind colgando de un controlador (topología)."""
        count = 0
        for segment in self._segments_of(network):
            if segment.from_node_id != parent.id:
                continue
            child = self.ctx.installations.get("NODE", segment.to_node_id)
            if child is not None and child.kind == kind:
                count += 1
                count += self._children_count(network, child, kind) * 0
        return count

    # -- PERÍMETRO (spec 47) ----------------------------------------------------------------
    def perimeter_check(self, network_ref: str) -> Dict[str, Any]:
        """Sensores, cámaras y accesos del perímetro (spec 47)."""
        network = self.resolve_network(network_ref)
        if network.system != "PERIMETER":
            raise DomainError(
                message=f"La red {network.code} no es perímetro ({network.system})",
                code="ARQ-SEC-015")
        devices = self._devices_of(network)
        fences = [n for n in devices if n.kind == "FENCE"]
        segments_length = [n.num("length_m") for n in fences]
        if not segments_length:
            # Sin FENCE declarados: usar la longitud de los tramos cableados.
            segments_length = [s.length_m for s in self._segments_of(network)
                               if s.length_m > 0]
        sensors = sum(1 for n in devices if n.kind == "FENCE_SENSOR")
        cameras = sum(1 for n in devices
                      if n.kind in ("PERIMETER_CAMERA", "CAMERA"))
        gates = sum(1 for n in devices if n.kind == "GATE")
        barriers = sum(1 for n in devices if n.kind == "BARRIER")
        access_points = sum(1 for n in devices if n.kind == "READER") + \
            sum(1 for n in devices if n.kind == "ACCESS_CONTROLLER")
        report = check_perimeter(segments_length, sensors, cameras,
                                 gates, barriers, access_points)
        self._store_calculation(
            {"fence_m": report.fence_length_m,
             "sensors": float(report.required_sensors),
             "cameras": float(report.required_cameras)},
            {"fence_m": "m", "sensors": "und", "cameras": "und"},
            [("NETWORK", network.id, network.revision)],
            errors=report.findings,
            status=CalculationStatus.WARNING if report.findings
            else CalculationStatus.COMPLETED)
        self.ctx.commit()
        return {"network": network.code, "report": report.to_dict()}

    # -- BOM (spec 48) ------------------------------------------------------------------
    def security_bom(self) -> Dict[str, Any]:
        """BOM de seguridad por tipo de dispositivo y red (spec 48)."""
        rows: Dict[str, Dict[str, Any]] = {}
        for network in self.ctx.installations.list("NETWORK",
                                                   self.ctx.project.id):
            if network.discipline != "SECURITY":
                continue
            for device in self._devices_of(network):
                row = rows.setdefault(device.kind, {
                    "kind": device.kind, "count": 0, "networks": set()})
                row["count"] += 1
                row["networks"].add(network.code)
        table = [{"kind": r["kind"], "count": r["count"],
                  "networks": sorted(r["networks"])}
                 for r in sorted(rows.values(), key=lambda r: r["kind"])]
        return {"items": table, "total_devices": sum(r["count"] for r in table)}


__all__ = ["SecurityService", "SECURITY_SYSTEMS", "CAUSE_EFFECT_RESOURCE"]
