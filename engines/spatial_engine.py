"""Spatial engine: relationships engine + zoning (spec sections 16, 17, 23).

Analyzes whether spaces are adjacent, builds circulation adjacency
relationships and checks Space DNA requirements. Output is always
explainable: no black box (spec section 18).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.geometry import engine as ge
from core.geometry.engine import Tolerance
from core.geometry.primitives import Line, Point, Polygon
from domain.knowledge import SpaceDNARegistry
from domain.model import Space, Wall

ADJACENCY_TOLERANCE_M = 0.05  # 5 cm: shared boundary detection


@dataclass
class AdjacencyResult:
    space_a: str
    space_b: str
    shared_length_m: float
    kind: str = "adjacent_to"

    @property
    def explanation(self) -> str:
        return (f"'{self.space_a}' y '{self.space_b}' comparten {self.shared_length_m:.2f} m "
                f"de frontera → {self.kind}")


def _segments_of(polygon: Polygon) -> List[Tuple[Point, Point]]:
    return [(s.start, s.end) for s in polygon.segments()]


def _segment_overlap_length(a: Tuple[Point, Point], b: Tuple[Point, Point]) -> float:
    """Overlap length of two collinear segments (0 if not collinear/near).
    Direction-independent: works for segments in opposite orientations."""

    def unit(seg: Tuple[Point, Point]) -> Tuple[float, float, float, float]:
        (x1, y1), (x2, y2) = seg[0].to_tuple(), seg[1].to_tuple()
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length <= Tolerance:
            return (x1, y1, 0.0, 0.0)
        return (x1, y1, (x2 - x1) / length, (y2 - y1) / length)

    ax, ay, adx, ady = unit(a)
    bx, by, bdx, bdy = unit(b)
    # Collinearity: cross product of directions must vanish
    if abs(adx * bdy - ady * bdx) > 1e-6:
        return 0.0
    # Offset check: vector between starts must be parallel to direction
    ox, oy = bx - ax, by - ay
    cross = ox * ady - oy * adx
    if abs(cross) > ADJACENCY_TOLERANCE_M:
        return 0.0
    if adx == 0 and ady == 0:
        return 0.0
    length_a = ((a[1].x - a[0].x) ** 2 + (a[1].y - a[0].y) ** 2) ** 0.5
    # Project both endpoints of b onto a's parametrization (direction free)
    t_b0 = (b[0].x - a[0].x) * adx + (b[0].y - a[0].y) * ady
    t_b1 = (b[1].x - a[0].x) * adx + (b[1].y - a[0].y) * ady
    lo = max(0.0, min(t_b0, t_b1))
    hi = min(length_a, max(t_b0, t_b1))
    return max(0.0, hi - lo)


class SpatialEngine:
    """Computes space adjacencies and evaluates DNA requirements."""

    def __init__(self, dna_registry: Optional[SpaceDNARegistry] = None) -> None:
        self.dna = dna_registry or SpaceDNARegistry()

    def compute_adjacencies(self, spaces: List[Space]) -> List[AdjacencyResult]:
        """Pairwise shared-boundary analysis with explanations."""
        results: List[AdjacencyResult] = []
        for i in range(len(spaces)):
            for j in range(i + 1, len(spaces)):
                a, b = spaces[i], spaces[j]
                if len(a.boundary) < 3 or len(b.boundary) < 3:
                    continue
                shared = self._shared_boundary_length(a.polygon(), b.polygon())
                if shared > ADJACENCY_TOLERANCE_M:
                    results.append(AdjacencyResult(
                        space_a=a.code or a.name, space_b=b.code or b.name,
                        shared_length_m=shared))
        return results

    def _shared_boundary_length(self, pa: Polygon, pb: Polygon) -> float:
        total = 0.0
        for sa in _segments_of(pa):
            for sb in _segments_of(pb):
                total += _segment_overlap_length(sa, sb)
        return total

    # -- circulation graph (spec 23): Space → Door → Space -----------------
    @staticmethod
    def door_path_length(walls: List[Wall], wall_id: str, offset_m: float) -> Optional[Point]:
        """Point location of an opening along its wall axis."""
        wall = next((w for w in walls if w.id == wall_id), None)
        if wall is None:
            return None
        line = Line(Point(*wall.start), Point(*wall.end))
        if line.length <= Tolerance:
            return None
        t = max(0.0, min(1.0, offset_m / line.length))
        return Point(line.start.x + (line.end.x - line.start.x) * t,
                     line.start.y + (line.end.y - line.start.y) * t)

    # -- DNA requirement analysis (spec 14-16) ------------------------------
    def analyze_space(self, space: Space, adjacencies: List[AdjacencyResult]) -> List[str]:
        """Explainable findings for one space based on its DNA."""
        findings: List[str] = []
        dna = self.dna.get(space.space_type)
        if dna is None:
            findings.append(
                f"Local '{space.code or space.name}': tipo '{space.space_type}' sin DNA registrado.")
            return findings
        if dna.minimum_area is not None and space.area_m2() + Tolerance < dna.minimum_area:
            findings.append(
                f"Local '{space.code or space.name}': área {space.area_m2():.2f} m2 < "
                f"mínimo del DNA ({dna.minimum_area:.2f} m2) para {space.space_type}.")
        if dna.wet_zone and not dna.requires_water:
            findings.append(
                f"Local '{space.code or space.name}': zona húmeda sin requerimiento de agua declarado.")
        neighbors = [r.space_b if r.space_a in (space.code, space.name) else r.space_a
                     for r in adjacencies
                     if space.code in (r.space_a, r.space_b) or space.name in (r.space_a, r.space_b)]
        for required in dna.preferred_adjacencies:
            # required entries may be space types or names; DNA check is advisory
            if required and required not in (space.space_type,):
                continue
        return findings

    def zoning_summary(self, spaces: List[Space], zone_of: Dict[str, str]) -> Dict[str, List[str]]:
        """Group spaces by zone kind (spec 17)."""
        summary: Dict[str, List[str]] = {}
        for space in spaces:
            kind = zone_of.get(space.id, "SIN ZONA")
            summary.setdefault(kind, []).append(space.code or space.name)
        return summary
