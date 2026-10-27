"""Routing Engine (spec section 26).

Shared router for electricity, pipes, HVAC ducts, CCTV, fire, intrusion,
access and telecom. Variables of the spec: distance, obstacles, clearance,
preferred_corridors, cost, crossings, maintenance.

Deterministic algorithm (no randomness):
  1. Candidate orthogonal (axis-aligned) routes between two points:
     horizontal-first, vertical-first, and corridor detours at the
     preferred corridor coordinates.
  2. Each candidate is scored:
        cost = distance
             + crossings * crossing_penalty
             + obstacle_hits * obstacle_penalty
             + clearance_violations * clearance_penalty
     plus an optional corridor bonus when the route passes through a
     preferred corridor and a maintenance penalty along heavy zones.
  3. The best scored route wins; ties keep the first generated (stable).

Obstacles are line segments (typically wall centerlines with thickness):
a route crosses an obstacle when any of its legs intersects it with a
distance below the requested clearance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import List, Optional, Sequence, Tuple

RouteLeg = Tuple[Tuple[float, float], Tuple[float, float]]


@dataclass
class Obstacle:
    """Segment obstacle: usually a wall centerline with its thickness."""

    start: Tuple[float, float]
    end: Tuple[float, float]
    thickness_m: float = 0.2
    penetrable: bool = True          # crossing allowed but penalized
    maintenance_cost: float = 0.0    # extra cost per meter along the obstacle


@dataclass
class RouteResult:
    """Result of the routing engine (spec 26 metrics)."""

    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    length_m: float = 0.0
    crossings: int = 0
    obstacle_hits: int = 0
    clearance_violations: int = 0
    corridor_bonus_applied: bool = False
    maintenance_cost: float = 0.0
    total_cost: float = 0.0
    ok: bool = True
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "waypoints": [list(p) for p in self.waypoints],
            "length_m": round(self.length_m, 4),
            "crossings": self.crossings,
            "obstacle_hits": self.obstacle_hits,
            "clearance_violations": self.clearance_violations,
            "corridor_bonus_applied": self.corridor_bonus_applied,
            "maintenance_cost": round(self.maintenance_cost, 4),
            "total_cost": round(self.total_cost, 4),
            "ok": self.ok,
            "reason": self.reason,
        }


@dataclass
class RoutingConfig:
    """Tuning of the router; all defaults documented in the README."""

    crossing_penalty: float = 15.0        # per wall crossed
    obstacle_penalty: float = 100.0       # per impassable obstacle hit
    clearance_penalty: float = 40.0       # per clearance violation
    corridor_bonus_per_m: float = 0.5    # reward per meter run inside a corridor
    maintenance_penalty: float = 0.5      # per meter along maintenance zones
    clearance_m: float = 0.05             # required free distance to obstacles
    min_segment_m: float = 0.05           # collapse shorter legs


def _point_segment_distance(p: Tuple[float, float],
                            a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Distance from point p to segment ab (self-contained, no deps)."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return hypot(px - (ax + dx * t), py - (ay + dy * t))


def _segments_properly_intersect(a1, a2, b1, b2) -> bool:
    """True when segment a1a2 crosses segment b1b2 (orientation test)."""

    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1 = orient(b1, b2, a1)
    d2 = orient(b1, b2, a2)
    d3 = orient(a1, a2, b1)
    d4 = orient(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _leg_intersects_obstacle(a: Tuple[float, float], b: Tuple[float, float],
                             obstacle: Obstacle) -> Tuple[bool, bool, float]:
    """Returns (intersects, below_clearance, min_distance)."""
    sa = obstacle.start
    sb = obstacle.end
    # Shared endpoint = junction, not a crossing.
    for shared in (a, b):
        if (abs(shared[0] - sa[0]) < 1e-6 and abs(shared[1] - sa[1]) < 1e-6) or \
           (abs(shared[0] - sb[0]) < 1e-6 and abs(shared[1] - sb[1]) < 1e-6):
            return False, False, 0.0
    if _segments_properly_intersect(a, b, sa, sb):
        return True, True, 0.0
    distance = min(
        _point_segment_distance(a, sa, sb),
        _point_segment_distance(b, sa, sb),
        _point_segment_distance(sa, a, b),
        _point_segment_distance(sb, a, b),
    )
    intersects = distance <= (obstacle.thickness_m / 2.0 + 1e-9)
    below_clearance = distance < obstacle.thickness_m / 2.0 + _cfg_clearance
    return intersects, below_clearance, distance


_cfg_clearance: float = 0.05


def _path_length(points: Sequence[Tuple[float, float]]) -> float:
    total = 0.0
    for index in range(len(points) - 1):
        total += hypot(points[index + 1][0] - points[index][0],
                       points[index + 1][1] - points[index][1])
    return total


def _leg_maintenance(leg: RouteLeg, obstacles: Sequence[Obstacle]) -> float:
    """Maintenance cost of running a leg along (parallel to) obstacles."""
    cost = 0.0
    (ax, ay), (bx, by) = leg
    for obstacle in obstacles:
        if obstacle.maintenance_cost <= 0:
            continue
        qa, qb = obstacle.start, obstacle.end
        # Parallel bands: same axis and overlapping range.
        if abs(ax - bx) < 1e-9 and abs(qa[0] - qb[0]) < 1e-9:
            lo, hi = sorted((ay, by))
            lo2, hi2 = sorted((qa[1], qb[1]))
            overlap = min(hi, hi2) - max(lo, lo2)
            if overlap > 0 and abs(ax - qa[0]) < 1.0:
                cost += overlap * obstacle.maintenance_cost
        elif abs(ay - by) < 1e-9 and abs(qa[1] - qb[1]) < 1e-9:
            lo, hi = sorted((ax, bx))
            lo2, hi2 = sorted((qa[0], qb[0]))
            overlap = min(hi, hi2) - max(lo, lo2)
            if overlap > 0 and abs(ay - qa[1]) < 1.0:
                cost += overlap * obstacle.maintenance_cost
    return cost


class RoutingEngine:
    """Deterministic orthogonal router (spec section 26)."""

    def __init__(self, config: Optional[RoutingConfig] = None) -> None:
        self.config = config or RoutingConfig()

    # -- public API ------------------------------------------------------------
    def route(self, start: Tuple[float, float], end: Tuple[float, float],
              obstacles: Optional[Sequence[Obstacle]] = None,
              preferred_corridors: Optional[Sequence[float]] = None,
              corridor_axis: str = "x") -> RouteResult:
        """Best orthogonal route from start to end.

        preferred_corridors: coordinates (x or y axis) the installation
        prefers to travel along (bands near walls/ceilings). corridor_axis
        tells which coordinate the corridor values refer to.
        """
        global _cfg_clearance
        _cfg_clearance = self.config.clearance_m
        obstacles = list(obstacles or [])
        corridors = [float(c) for c in (preferred_corridors or [])]
        start = (float(start[0]), float(start[1]))
        end = (float(end[0]), float(end[1]))

        candidates: List[List[Tuple[float, float]]] = []
        # L-shapes: horizontal-first and vertical-first.
        candidates.append([start, (end[0], start[1]), end])
        candidates.append([start, (start[0], end[1]), end])
        # Z-detours through preferred corridors (both axes of interest).
        for corridor in corridors[:6]:
            if corridor_axis == "x":
                candidates.append([start, (corridor, start[1]), (corridor, end[1]), end])
            else:
                candidates.append([start, (start[0], corridor), (end[0], corridor), end])
        # Midpoint detours (classic Z) — help when both L-shapes hit a wall.
        mid_x = round((start[0] + end[0]) / 2.0, 4)
        mid_y = round((start[1] + end[1]) / 2.0, 4)
        candidates.append([start, (mid_x, start[1]), (mid_x, end[1]), end])
        candidates.append([start, (start[0], mid_y), (end[0], mid_y), end])

        best: Optional[RouteResult] = None
        for waypoints in candidates:
            result = self._score(waypoints, obstacles, corridors, corridor_axis)
            if best is None or result.total_cost < best.total_cost - 1e-9:
                best = result
        assert best is not None
        return best

    def route_straight(self, start: Tuple[float, float],
                       end: Tuple[float, float]) -> RouteResult:
        """Straight run; used when the user forces STRAIGHT routing."""
        global _cfg_clearance
        _cfg_clearance = self.config.clearance_m
        waypoints = [(float(start[0]), float(start[1])), (float(end[0]), float(end[1]))]
        return self._score(waypoints, [], [], "x")

    # -- internals -----------------------------------------------------------------
    def _score(self, waypoints: List[Tuple[float, float]], obstacles: List[Obstacle],
               corridors: Sequence[float], corridor_axis: str) -> RouteResult:
        config = self.config
        points = self._clean(waypoints)
        result = RouteResult(waypoints=points)
        if len(points) < 2:
            result.ok = False
            result.reason = "Ruta degenerada"
            return result

        result.length_m = _path_length(points)
        if result.length_m < 1e-9:
            result.ok = False
            result.reason = "Ruta de longitud nula"
            return result

        crossings = 0
        hits = 0
        violations = 0
        for index in range(len(points) - 1):
            leg = (points[index], points[index + 1])
            for obstacle in obstacles:
                intersects, below, _distance = _leg_intersects_obstacle(leg[0], leg[1], obstacle)
                if intersects and not obstacle.penetrable:
                    hits += 1
                elif intersects:
                    crossings += 1
                if below and not intersects:
                    violations += 1
            result.maintenance_cost += _leg_maintenance(leg, obstacles)

        result.crossings = crossings
        result.obstacle_hits = hits
        result.clearance_violations = violations

        used_corridor = False
        corridor_meters = 0.0
        for corridor in corridors:
            for index in range(len(points) - 1):
                (ax, ay), (bx, by) = points[index], points[index + 1]
                if corridor_axis == "x" and abs(ax - corridor) < 0.2 and abs(bx - corridor) < 0.2:
                    corridor_meters += abs(by - ay)
                    used_corridor = True
                elif corridor_axis == "y" and abs(ay - corridor) < 0.2 and abs(by - corridor) < 0.2:
                    corridor_meters += abs(bx - ax)
                    used_corridor = True
        result.corridor_bonus_applied = used_corridor

        result.total_cost = (
            result.length_m
            + crossings * config.crossing_penalty
            + hits * config.obstacle_penalty
            + violations * config.clearance_penalty
            + result.maintenance_cost * config.maintenance_penalty
            - corridor_meters * config.corridor_bonus_per_m
        )
        if hits > 0:
            result.ok = False
            result.reason = "La ruta atraviesa un obstáculo infranqueable"
        return result

    @staticmethod
    def _clean(points: List[Tuple[float, float]],
               min_segment: float = 0.05) -> List[Tuple[float, float]]:
        """Remove degenerate legs and collinear middle points (stable)."""
        cleaned: List[Tuple[float, float]] = []
        for point in points:
            if cleaned and abs(cleaned[-1][0] - point[0]) < min_segment \
                    and abs(cleaned[-1][1] - point[1]) < min_segment:
                continue
            cleaned.append(point)
        if len(cleaned) < 3:
            return cleaned
        stable: List[Tuple[float, float]] = [cleaned[0]]
        for index in range(1, len(cleaned) - 1):
            previous, current, nxt = cleaned[index - 1], cleaned[index], cleaned[index + 1]
            collinear_x = abs(previous[0] - current[0]) < 1e-9 and abs(current[0] - nxt[0]) < 1e-9
            collinear_y = abs(previous[1] - current[1]) < 1e-9 and abs(current[1] - nxt[1]) < 1e-9
            if not (collinear_x or collinear_y):
                stable.append(current)
        stable.append(cleaned[-1])
        return stable


__all__ = ["RoutingEngine", "RoutingConfig", "Obstacle", "RouteResult"]
