"""Geometric primitives (spec section 9).

Point, Line, Polyline, Arc, Circle, Ellipse, Polygon.
The P0 phase implements a complete, tested 2D engine; 3D primitives are
declared for later phases and intentionally absent (nothing incomplete).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def translated(self, dx: float, dy: float) -> "Point":
        return Point(self.x + dx, self.y + dy)

    def rotated(self, origin: "Point", angle_deg: float) -> "Point":
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        dx, dy = self.x - origin.x, self.y - origin.y
        return Point(origin.x + dx * cos_a - dy * sin_a, origin.y + dx * sin_a + dy * cos_a)

    def mirrored(self, axis_start: "Point", axis_end: "Point") -> "Point":
        ax, ay = axis_end.x - axis_start.x, axis_end.y - axis_start.y
        length2 = ax * ax + ay * ay
        if length2 == 0:
            return self
        px, py = self.x - axis_start.x, self.y - axis_start.y
        proj = (px * ax + py * ay) / length2
        # closest point on axis, then mirror
        cx, cy = axis_start.x + ax * proj, axis_start.y + ay * proj
        return Point(2 * cx - self.x, 2 * cy - self.y)

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class Line:
    start: Point
    end: Point
    length: float = field(init=False)

    def __post_init__(self) -> None:
        self.length = self.start.distance_to(self.end)

    def direction(self) -> Tuple[float, float]:
        if self.length == 0:
            return (0.0, 0.0)
        return ((self.end.x - self.start.x) / self.length, (self.end.y - self.start.y) / self.length)

    def angle_deg(self) -> float:
        dx, dy = self.end.x - self.start.x, self.end.y - self.start.y
        return math.degrees(math.atan2(dy, dx)) % 360.0

    def midpoint(self) -> Point:
        return Point((self.start.x + self.end.x) / 2, (self.start.y + self.end.y) / 2)


@dataclass
class Polyline:
    points: List[Point]
    closed: bool = False

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            from core.errors import GeometryError
            raise GeometryError(
                message="Una Polyline requiere al menos 2 puntos",
                code="ARQ-GEO-002",
            )

    @property
    def vertices(self) -> List[Point]:
        if self.closed and self.points and self.points[0] != self.points[-1]:
            return self.points + [self.points[0]]
        return self.points

    def segments(self) -> List[Line]:
        verts = self.vertices
        return [Line(verts[i], verts[i + 1]) for i in range(len(verts) - 1)]


@dataclass
class Arc:
    center: Point
    radius: float
    start_angle_deg: float
    end_angle_deg: float


@dataclass
class Circle:
    center: Point
    radius: float

    @property
    def area(self) -> float:
        return math.pi * self.radius ** 2

    @property
    def perimeter(self) -> float:
        return 2 * math.pi * self.radius


@dataclass
class Ellipse:
    center: Point
    rx: float
    ry: float


@dataclass
class Polygon:
    points: List[Point]  # open ring (first point is not repeated)

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            from core.errors import GeometryError
            raise GeometryError(
                message="Un Polygon requiere al menos 3 vértices",
                code="ARQ-GEO-003",
            )

    def segments(self) -> List[Line]:
        pts = self.points
        return [Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]

    def translated(self, dx: float, dy: float) -> "Polygon":
        return Polygon([p.translated(dx, dy) for p in self.points])

    def rotated(self, origin: Point, angle_deg: float) -> "Polygon":
        return Polygon([p.rotated(origin, angle_deg) for p in self.points])

    def mirrored(self, axis_start: Point, axis_end: Point) -> "Polygon":
        return Polygon([p.mirrored(axis_start, axis_end) for p in self.points])

    def scaled(self, origin: Point, factor: float) -> "Polygon":
        return Polygon([
            Point(origin.x + (p.x - origin.x) * factor, origin.y + (p.y - origin.y) * factor)
            for p in self.points
        ])


__all__ = ["Point", "Line", "Polyline", "Arc", "Circle", "Ellipse", "Polygon"]
