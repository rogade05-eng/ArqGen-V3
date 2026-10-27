"""Clash Detection Engine (spec sections 35, 36).

Detecta interferencias entre disciplinas con reglas geométricas
deterministas (todo en metros, coordenadas de modelo):

    HARD        solapamiento físico: un dispositivo cae dentro del
                contorno de un muro (distancia al eje < espesor/2).
    SOFT        proximidad incómoda entre dispositivos de disciplinas
                distintas por debajo de la tolerancia (sin choque).
    CLEARANCE   distancia libre alrededor de un equipo por debajo del
                mínimo exigido (respeto a muros).
    ACCESS      la zona de acceso de un tablero/equipo invade un muro.
    MAINTENANCE la zona de mantenimiento de dos equipos se solapa.
    ROUTE       dos rutas de disciplinas distintas se cruzan.

Cada regla devuelve hallazgos (ClashFinding) con el par de objetos,
ubicación, distancia y severidad; el servicio los persiste como
entidades Clash (spec 36) con deduplicación por par+tipo.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]
Segment = Tuple[Point, Point]

# Tolerancias por defecto (documentadas en README, ajustables por regla).
SOFT_TOLERANCE_M = 0.15          # proximidad incómoda entre dispositivos
CLEARANCE_MIN_M = 0.30           # distancia libre mínima equipo ↔ muro
ACCESS_ZONE_M = 0.80             # frente de maniobra de tableros
MAINTENANCE_ZONE_M = 0.50        # zona de retiro de equipos
DEVICE_RADIUS_M = 0.10           # radio físico estimado del dispositivo


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distancia de un punto a un segmento."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return hypot(px - (ax + dx * t), py - (ay + dy * t))


def segments_properly_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """True cuando los segmentos se cruzan (test de orientación)."""

    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1 = orient(b1, b2, a1)
    d2 = orient(b1, b2, a2)
    d3 = orient(a1, a2, b1)
    d4 = orient(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


@dataclass
class ClashFinding:
    """Hallazgo geométrico previo a la persistencia (spec 36)."""

    type: str
    severity: str
    object_a: Tuple[str, str, str]        # (type, id, code)
    object_b: Tuple[str, str, str]
    location: Point
    distance: float
    rule: str

    def to_dict(self) -> dict:
        return {
            "type": self.type, "severity": self.severity,
            "object_a": {"type": self.object_a[0], "id": self.object_a[1],
                         "code": self.object_a[2]},
            "object_b": {"type": self.object_b[0], "id": self.object_b[1],
                         "code": self.object_b[2]},
            "location": [round(self.location[0], 4), round(self.location[1], 4)],
            "distance": round(self.distance, 4),
            "rule": self.rule,
        }


def _projection_point(p: Point, a: Point, b: Point) -> Point:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return a
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return (ax + dx * t, ay + dy * t)


def node_wall_clashes(node: Tuple[str, str, str, Point, float],
                      walls: Sequence[Tuple[str, str, str, Segment, float]],
                      clearance_m: float = CLEARANCE_MIN_M,
                      access_zone_m: float = ACCESS_ZONE_M,
                      device_radius_m: float = DEVICE_RADIUS_M
                      ) -> List[ClashFinding]:
    """Dispositivo ↔ muros: HARD (dentro), CLEARANCE y ACCESS (maniobra).

    node:  (type, id, code, position, radius_m) — radius 0 usa el defecto.
    walls: (type, id, code, segment, thickness_m)
    """
    findings: List[ClashFinding] = []
    node_type, node_id, node_code, position, radius = node
    device_radius = radius or device_radius_m
    for wall_type, wall_id, wall_code, segment, thickness in walls:
        distance = point_segment_distance(position, segment[0], segment[1])
        if distance < thickness / 2.0 + device_radius - 1e-9:
            findings.append(ClashFinding(
                type="HARD", severity="CRITICAL",
                object_a=(node_type, node_id, node_code),
                object_b=(wall_type, wall_id, wall_code),
                location=_projection_point(position, segment[0], segment[1]),
                distance=distance,
                rule="clash/node_in_wall"))
        elif distance < thickness / 2.0 + clearance_m - 1e-9:
            findings.append(ClashFinding(
                type="CLEARANCE", severity="HIGH",
                object_a=(node_type, node_id, node_code),
                object_b=(wall_type, wall_id, wall_code),
                location=_projection_point(position, segment[0], segment[1]),
                distance=distance,
                rule="clash/clearance_wall"))
        # Frente de maniobra de equipos grandes (radius ≥ 0.25) hacia el muro.
        if radius >= 0.25 and distance < thickness / 2.0 + access_zone_m - 1e-9 \
                and not any(f.type == "HARD" and f.object_b[1] == wall_id
                            for f in findings):
            findings.append(ClashFinding(
                type="ACCESS", severity="HIGH",
                object_a=(node_type, node_id, node_code),
                object_b=(wall_type, wall_id, wall_code),
                location=_projection_point(position, segment[0], segment[1]),
                distance=distance,
                rule="clash/access_wall"))
    return findings


def node_node_clashes(nodes: Sequence[Tuple[str, str, str, str, Point, float]],
                      soft_tolerance_m: float = SOFT_TOLERANCE_M,
                      maintenance_zone_m: float = MAINTENANCE_ZONE_M
                      ) -> List[ClashFinding]:
    """Dispositivo ↔ dispositivo de otra red: SOFT y MAINTENANCE.

    nodes: (type, id, code, discipline, position, radius_m). Pares de la
    MISMA red se ignoran (misma disciplina, separación por diseño).
    """
    findings: List[ClashFinding] = []
    for i in range(len(nodes)):
        type_a, id_a, code_a, disc_a, pos_a, radius_a = nodes[i]
        for j in range(i + 1, len(nodes)):
            type_b, id_b, code_b, disc_b, pos_b, radius_b = nodes[j]
            if id_a == id_b or disc_a == disc_b:
                continue
            distance = hypot(pos_a[0] - pos_b[0], pos_a[1] - pos_b[1])
            maintenance = max(radius_a, radius_b, 0.0) * 2.0 + maintenance_zone_m
            if distance < soft_tolerance_m + (radius_a + radius_b) - 1e-9:
                findings.append(ClashFinding(
                    type="SOFT", severity="LOW",
                    object_a=(type_a, id_a, code_a),
                    object_b=(type_b, id_b, code_b),
                    location=((pos_a[0] + pos_b[0]) / 2.0,
                              (pos_a[1] + pos_b[1]) / 2.0),
                    distance=distance, rule="clash/device_proximity"))
            elif radius_a >= 0.25 and radius_b >= 0.25 \
                    and distance < maintenance - 1e-9:
                findings.append(ClashFinding(
                    type="MAINTENANCE", severity="MEDIUM",
                    object_a=(type_a, id_a, code_a),
                    object_b=(type_b, id_b, code_b),
                    location=((pos_a[0] + pos_b[0]) / 2.0,
                              (pos_a[1] + pos_b[1]) / 2.0),
                    distance=distance, rule="clash/maintenance_zone"))
    return findings


def segment_segment_clashes(
        segments: Sequence[Tuple[str, str, str, str, Segment, int]]
        ) -> List[ClashFinding]:
    """Tramo ↔ tramo de redes distintas que se cruzan (route clash).

    segments: (type, id, code, network_id, endpoints, crossing_count).
    Los tramos de la MISMA red se ignoran (convergencia normal).
    """
    findings: List[ClashFinding] = []
    for i in range(len(segments)):
        type_a, id_a, code_a, net_a, (a1, a2), _cross_a = segments[i]
        for j in range(i + 1, len(segments)):
            type_b, id_b, code_b, net_b, (b1, b2), _cross_b = segments[j]
            if net_a == net_b:
                continue
            if segments_properly_intersect(a1, a2, b1, b2):
                # Punto de cruce por intersección de rectas (aprox. media).
                location = ((a1[0] + a2[0] + b1[0] + b2[0]) / 4.0,
                            (a1[1] + a2[1] + b1[1] + b2[1]) / 4.0)
                findings.append(ClashFinding(
                    type="ROUTE", severity="MEDIUM",
                    object_a=(type_a, id_a, code_a),
                    object_b=(type_b, id_b, code_b),
                    location=location,
                    distance=0.0, rule="clash/route_crossing"))
    return findings


__all__ = [
    "ClashFinding", "SOFT_TOLERANCE_M", "CLEARANCE_MIN_M", "ACCESS_ZONE_M",
    "MAINTENANCE_ZONE_M", "DEVICE_RADIUS_M",
    "point_segment_distance", "segments_properly_intersect",
    "node_wall_clashes", "node_node_clashes", "segment_segment_clashes",
]
