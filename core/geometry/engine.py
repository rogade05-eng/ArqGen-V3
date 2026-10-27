"""Geometry engine functions (spec section 9, minimum function catalogue).

All functions are pure, deterministic and unit-agnostic (they operate on
model coordinates in meters). Every function is covered by unit tests.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from core.errors import GeometryError
from core.geometry.primitives import Arc, Circle, Ellipse, Line, Point, Polygon, Polyline

Tolerance = 1e-9


# ---------------------------------------------------------------------------
# distance / angle
# ---------------------------------------------------------------------------
def distance(a: object, b: object) -> float:
    """Distance between two points, or point-to-line/polygon boundary."""
    if isinstance(a, Point) and isinstance(b, Point):
        return a.distance_to(b)
    if isinstance(a, Point) and isinstance(b, Line):
        return _point_to_segment(a, b.start, b.end)[1]
    if isinstance(a, Line) and isinstance(b, Point):
        return distance(b, a)
    if isinstance(a, Point) and isinstance(b, (Polygon, Polyline)):
        return min(_point_to_segment(a, s.start, s.end)[1] for s in b.segments())
    if isinstance(a, (Polygon, Polyline)) and isinstance(b, Point):
        return distance(b, a)
    raise GeometryError(
        message="Combinación de tipos no soportada por distance()",
        code="ARQ-GEO-010",
        context={"a": type(a).__name__, "b": type(b).__name__},
    )


def _point_to_segment(p: Point, a: Point, b: Point) -> Tuple[Point, float]:
    ax, ay = b.x - a.x, b.y - a.y
    length2 = ax * ax + ay * ay
    if length2 <= Tolerance:
        return a, p.distance_to(a)
    t = ((p.x - a.x) * ax + (p.y - a.y) * ay) / length2
    t = max(0.0, min(1.0, t))
    proj = Point(a.x + ax * t, a.y + ay * t)
    return proj, p.distance_to(proj)


def angle(line_or_p1: object, line_or_p2: Optional[object] = None) -> float:
    """Angle of a Line in degrees, or angle between two Lines (0..180)."""
    if line_or_p2 is None:
        if not isinstance(line_or_p1, Line):
            raise GeometryError(message="angle() requiere una Line", code="ARQ-GEO-011")
        return line_or_p1.angle_deg()
    l1, l2 = line_or_p1, line_or_p2  # type: ignore[assignment]
    if not isinstance(l1, Line) or not isinstance(l2, Line):
        raise GeometryError(message="angle() entre dos objetos requiere Lines", code="ARQ-GEO-011")
    a1 = math.radians(l1.angle_deg())
    a2 = math.radians(l2.angle_deg())
    diff = abs(math.degrees(a1 - a2)) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


# ---------------------------------------------------------------------------
# area / perimeter / centroid / volume
# ---------------------------------------------------------------------------
def shoelace_area(points: Sequence[Point]) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        p1, p2 = points[i], points[(i + 1) % n]
        total += p1.x * p2.y - p2.x * p1.y
    return total / 2.0


def area(obj: object) -> float:
    """Absolute area of a Polygon (signed area internally via shoelace)."""
    if isinstance(obj, Polygon):
        return abs(shoelace_area(obj.points))
    if isinstance(obj, Circle):
        return obj.area
    if isinstance(obj, Ellipse):
        return math.pi * obj.rx * obj.ry
    raise GeometryError(
        message="area() soporta Polygon, Circle y Ellipse",
        code="ARQ-GEO-012",
        context={"type": type(obj).__name__},
    )


def perimeter(obj: object) -> float:
    if isinstance(obj, Polygon):
        return sum(s.length for s in obj.segments())
    if isinstance(obj, Polyline):
        return sum(s.length for s in obj.segments())
    if isinstance(obj, Circle):
        return obj.perimeter
    raise GeometryError(
        message="perimeter() soporta Polygon, Polyline y Circle",
        code="ARQ-GEO-013",
        context={"type": type(obj).__name__},
    )


def centroid(points: Sequence[Point]) -> Point:
    """Centroid of a polygon ring (falls back to vertex mean for degenerate)."""
    n = len(points)
    if n == 0:
        raise GeometryError(message="centroid() requiere puntos", code="ARQ-GEO-014")
    signed = shoelace_area(points)
    if abs(signed) <= Tolerance:
        return Point(sum(p.x for p in points) / n, sum(p.y for p in points) / n)
    cx = cy = 0.0
    for i in range(n):
        p1, p2 = points[i], points[(i + 1) % n]
        cross = p1.x * p2.y - p2.x * p1.y
        cx += (p1.x + p2.x) * cross
        cy += (p1.y + p2.y) * cross
    return Point(cx / (6.0 * signed), cy / (6.0 * signed))


def extrude_volume(polygon: Polygon, height_m: float) -> float:
    """Volume of a prismatic solid: plan area × height (spec: volume())."""
    if height_m <= 0:
        raise GeometryError(
            message="La altura de extrusión debe ser positiva",
            code="ARQ-GEO-015",
            context={"height_m": height_m},
        )
    return area(polygon) * height_m


# ---------------------------------------------------------------------------
# transforms
# ---------------------------------------------------------------------------
def _transform_points(obj: object, mapper) -> object:
    """Applies a point mapper preserving Polygon/Polyline identity."""
    if isinstance(obj, Polygon):
        return Polygon([mapper(p) for p in obj.points])
    if isinstance(obj, Polyline):
        return Polyline([mapper(p) for p in obj.points], obj.closed)
    raise GeometryError(message="Transform no soporta el tipo", code="ARQ-GEO-016",
                        context={"type": type(obj).__name__})


def translate(obj: object, dx: float, dy: float) -> object:
    if isinstance(obj, Point):
        return obj.translated(dx, dy)
    if isinstance(obj, Line):
        return Line(obj.start.translated(dx, dy), obj.end.translated(dx, dy))
    if isinstance(obj, Circle):
        return Circle(obj.center.translated(dx, dy), obj.radius)
    return _transform_points(obj, lambda p: p.translated(dx, dy))


def rotate(obj: object, origin: Point, angle_deg: float) -> object:
    if isinstance(obj, Point):
        return obj.rotated(origin, angle_deg)
    if isinstance(obj, Line):
        return Line(obj.start.rotated(origin, angle_deg), obj.end.rotated(origin, angle_deg))
    return _transform_points(obj, lambda p: p.rotated(origin, angle_deg))


def mirror(obj: object, axis_start: Point, axis_end: Point) -> object:
    if isinstance(obj, Point):
        return obj.mirrored(axis_start, axis_end)
    if isinstance(obj, Line):
        return Line(obj.start.mirrored(axis_start, axis_end), obj.end.mirrored(axis_start, axis_end))
    return _transform_points(obj, lambda p: p.mirrored(axis_start, axis_end))


def scale(obj: object, origin: Point, factor: float) -> object:
    if factor <= 0:
        raise GeometryError(message="El factor de escala debe ser positivo", code="ARQ-GEO-019",
                            context={"factor": factor})

    def _scale_point(p: Point) -> Point:
        return Point(origin.x + (p.x - origin.x) * factor, origin.y + (p.y - origin.y) * factor)

    if isinstance(obj, Point):
        return _scale_point(obj)
    if isinstance(obj, Line):
        return Line(_scale_point(obj.start), _scale_point(obj.end))
    if isinstance(obj, Circle):
        return Circle(_scale_point(obj.center), obj.radius * factor)
    return _transform_points(obj, _scale_point)


# ---------------------------------------------------------------------------
# intersection / contains / overlaps
# ---------------------------------------------------------------------------
def _line_line_intersection(l1: Line, l2: Line) -> Optional[Point]:
    x1, y1, x2, y2 = l1.start.x, l1.start.y, l1.end.x, l1.end.y
    x3, y3, x4, y4 = l2.start.x, l2.start.y, l2.end.x, l2.end.y
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) <= Tolerance:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
    if -Tolerance <= t <= 1 + Tolerance and -Tolerance <= u <= 1 + Tolerance:
        return Point(x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def intersection(a: object, b: object) -> Optional[object]:
    """Intersection: Line×Line → Point | None; Polygon×Polygon → Polygon | None
    (clip window ``b`` must be convex); Point-in-polygon is contained()."""
    if isinstance(a, Line) and isinstance(b, Line):
        return _line_line_intersection(a, b)
    if isinstance(a, Polygon) and isinstance(b, Polygon):
        return _clip_polygon(a, b)
    raise GeometryError(
        message="intersection() soporta Line×Line y Polygon×Polygon",
        code="ARQ-GEO-021",
        context={"a": type(a).__name__, "b": type(b).__name__},
    )


def _clip_polygon(subject: Polygon, clip: Polygon) -> Optional[Polygon]:
    """Sutherland–Hodgman clipping of ``subject`` by convex ``clip``.
    Subject edges are cut against the INFINITE line of each clip edge
    (classic SH algorithm), not against the clip segment."""

    def inside(p: Point, edge: Line, ccw_clip: bool) -> bool:
        cross = (edge.end.x - edge.start.x) * (p.y - edge.start.y) - (
            edge.end.y - edge.start.y) * (p.x - edge.start.x)
        return cross >= -Tolerance if ccw_clip else cross <= Tolerance

    def intersect_segment_line(p1: Point, p2: Point, edge: Line) -> Optional[Point]:
        """Intersection of segment p1→p2 with the infinite line through edge.

        Solves p1 + t·d = s + u·e  →  t = ((s − p1) × e) / (d × e).
        """
        ex, ey = edge.end.x - edge.start.x, edge.end.y - edge.start.y
        dx, dy = p2.x - p1.x, p2.y - p1.y
        denom = dx * ey - dy * ex
        if abs(denom) <= Tolerance:
            return None
        t = ((edge.start.x - p1.x) * ey - (edge.start.y - p1.y) * ex) / denom
        if -Tolerance <= t <= 1 + Tolerance:
            return Point(p1.x + t * dx, p1.y + t * dy)
        return None

    signed = shoelace_area(clip.points)
    ccw = signed > 0
    output = list(subject.points)
    for edge in clip.segments():
        if not output:
            return None
        input_pts = output
        output = []
        prev = input_pts[-1]
        prev_in = inside(prev, edge, ccw)
        for current in input_pts:
            cur_in = inside(current, edge, ccw)
            if cur_in:
                if not prev_in:
                    inter = intersect_segment_line(prev, current, edge)
                    if inter:
                        output.append(inter)
                output.append(current)
            elif prev_in:
                inter = intersect_segment_line(prev, current, edge)
                if inter:
                    output.append(inter)
            prev, prev_in = current, cur_in
    if len(output) < 3:
        return None
    return Polygon(output)


def contains(polygon: Polygon, point: Point) -> bool:
    """Ray casting point-in-polygon test."""
    inside = False
    pts = polygon.points
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i].x, pts[i].y
        xj, yj = pts[j].x, pts[j].y
        if ((yi > point.y) != (yj > point.y)) and (
            point.x < (xj - xi) * (point.y - yi) / (yj - yi + Tolerance) + xi
        ):
            inside = not inside
        j = i
    return inside


def _convex(points: Sequence[Point]) -> bool:
    n = len(points)
    if n < 3:
        return True
    sign = 0
    for i in range(n):
        p0, p1, p2 = points[i], points[(i + 1) % n], points[(i + 2) % n]
        cross = (p1.x - p0.x) * (p2.y - p0.y) - (p1.y - p0.y) * (p2.x - p0.x)
        if abs(cross) <= Tolerance:
            continue
        current = 1 if cross > 0 else -1
        if sign == 0:
            sign = current
        elif sign != current:
            return False
    return True


def overlaps(a: Polygon, b: Polygon, min_area: float = Tolerance) -> bool:
    """True when the two polygons share an area greater than ``min_area``."""
    clipped = _clip_polygon(a, b) if _convex(b.points) else _clip_polygon(b, a)
    if clipped is None:
        return False
    return area(clipped) > min_area


def overlap_area(a: Polygon, b: Polygon) -> float:
    clipped = _clip_polygon(a, b) if _convex(b.points) else _clip_polygon(b, a)
    return area(clipped) if clipped else 0.0


# ---------------------------------------------------------------------------
# offset / trim / extend / split / join / fillet / chamfer
# ---------------------------------------------------------------------------
def offset_line(line: Line, distance_m: float) -> Line:
    """Parallel line at signed perpendicular distance (left positive)."""
    dx, dy = line.direction()
    nx, ny = -dy, dx
    return Line(
        Point(line.start.x + nx * distance_m, line.start.y + ny * distance_m),
        Point(line.end.x + nx * distance_m, line.end.y + ny * distance_m),
    )


def offset(obj: Line, distance_m: float) -> Line:
    return offset_line(obj, distance_m)


def wall_outline(line: Line, thickness_m: float) -> Polygon:
    """Closed rectangle outline of a wall centered on its axis line."""
    half = thickness_m / 2.0
    left = offset_line(line, half)
    right = offset_line(line, -half)
    return Polygon([left.start, left.end, right.end, right.start])


def trim(line: Line, cutter: Line, keep: str = "start") -> Line:
    """Trim ``line`` against ``cutter``; keeps the part nearest 'start' or 'end'."""
    inter = _line_line_intersection(line, cutter)
    if inter is None:
        raise GeometryError(
            message="trim(): la línea no corta al elemento de corte",
            code="ARQ-GEO-022",
        )
    if keep == "start":
        return Line(line.start, inter)
    if keep == "end":
        return Line(inter, line.end)
    raise GeometryError(message="trim(): keep debe ser 'start' o 'end'", code="ARQ-GEO-022")


def extend(line: Line, target: Line) -> Line:
    """Extend line (infinite) until it hits ``target`` line."""
    inter = _extend_line_to(line, target)
    if inter is None:
        raise GeometryError(
            message="extend(): no existe intersección con la línea objetivo",
            code="ARQ-GEO-023",
        )
    d_end = line.start.distance_to(inter) + line.end.distance_to(inter)
    d_start = line.end.distance_to(inter)
    if line.start.distance_to(inter) <= line.end.distance_to(inter):
        return Line(inter, line.end)
    return Line(line.start, inter)


def _extend_line_to(line: Line, target: Line) -> Optional[Point]:
    x1, y1, x2, y2 = line.start.x, line.start.y, line.end.x, line.end.y
    x3, y3, x4, y4 = target.start.x, target.start.y, target.end.x, target.end.y
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) <= Tolerance:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return Point(x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def split(line: Line, at: Point) -> Tuple[Line, Line]:
    """Split a line at a point lying on it (projection clamped)."""
    proj, dist = _point_to_segment(at, line.start, line.end)
    if dist > 1e-6:
        raise GeometryError(
            message="split(): el punto no pertenece a la línea",
            code="ARQ-GEO-024",
            context={"distance": dist},
        )
    if proj.distance_to(line.start) <= Tolerance or proj.distance_to(line.end) <= Tolerance:
        raise GeometryError(message="split(): el punto coincide con un extremo", code="ARQ-GEO-024")
    return Line(line.start, proj), Line(proj, line.end)


def join(polylines: Sequence[Polyline]) -> Polyline:
    """Join consecutive polylines sharing endpoints into one polyline."""
    if not polylines:
        raise GeometryError(message="join(): lista vacía", code="ARQ-GEO-025")
    merged = list(polylines[0].points)
    for pl in polylines[1:]:
        head = pl.points[0]
        tail = pl.points[-1]
        if merged[-1].distance_to(head) <= 1e-6:
            merged.extend(pl.points[1:])
        elif merged[-1].distance_to(tail) <= 1e-6:
            merged.extend(list(reversed(pl.points))[1:])
        elif merged[0].distance_to(head) <= 1e-6:
            merged = list(reversed(merged)) + []
            merged = list(reversed(pl.points)) + merged[1:]
        elif merged[0].distance_to(tail) <= 1e-6:
            merged = pl.points + merged[1:]
        else:
            raise GeometryError(
                message="join(): las polilíneas no comparten extremos",
                code="ARQ-GEO-025",
            )
    return Polyline(merged, closed=False)


def fillet(l1: Line, l2: Line, radius: float) -> Arc:
    """Tangent fillet arc between two lines sharing (or extended to share) a corner."""
    if radius <= 0:
        raise GeometryError(message="fillet(): radio debe ser positivo", code="ARQ-GEO-026")
    corner = _extend_line_to(l1, l2)
    if corner is None:
        corner = _line_line_intersection(l1, l2)
    if corner is None:
        raise GeometryError(message="fillet(): las líneas no concurren", code="ARQ-GEO-026")
    u1 = l1.direction()
    if (corner.x - l1.start.x) * u1[0] + (corner.y - l1.start.y) * u1[1] < 0:
        u1 = (-u1[0], -u1[1])
    u2 = l2.direction()
    if (corner.x - l2.start.x) * u2[0] + (corner.y - l2.start.y) * u2[1] < 0:
        u2 = (-u2[0], -u2[1])
    cos_half = math.cos(math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))) / 2.0)
    if cos_half <= Tolerance:
        raise GeometryError(message="fillet(): ángulo inválido", code="ARQ-GEO-026")
    d = radius / math.sqrt(max(1e-12, 1 - cos_half ** 2)) * cos_half
    t1 = Point(corner.x + u1[0] * d, corner.y + u1[1] * d)
    t2 = Point(corner.x + u2[0] * d, corner.y + u2[1] * d)
    bis = ((u1[0] + u2[0]), (u1[1] + u2[1]))
    blen = math.hypot(*bis)
    if blen <= Tolerance:
        raise GeometryError(message="fillet(): líneas opuestas", code="ARQ-GEO-026")
    center = Point(corner.x + bis[0] / blen * radius / max(1e-12, math.sqrt(max(1e-12, 1 - cos_half ** 2))),
                   corner.y + bis[1] / blen * radius / max(1e-12, math.sqrt(max(1e-12, 1 - cos_half ** 2))))
    a1 = math.degrees(math.atan2(t1.y - center.y, t1.x - center.x))
    a2 = math.degrees(math.atan2(t2.y - center.y, t2.x - center.x))
    return Arc(center=center, radius=radius, start_angle_deg=a1, end_angle_deg=a2)


def chamfer(l1: Line, l2: Line, distance_m: float) -> Line:
    """Chamfer segment between two concurrent lines at the given setback."""
    if distance_m <= 0:
        raise GeometryError(message="chamfer(): distancia debe ser positiva", code="ARQ-GEO-027")
    corner = _extend_line_to(l1, l2) or _line_line_intersection(l1, l2)
    if corner is None:
        raise GeometryError(message="chamfer(): las líneas no concurren", code="ARQ-GEO-027")
    u1 = l1.direction()
    if (corner.x - l1.start.x) * u1[0] + (corner.y - l1.start.y) * u1[1] < 0:
        u1 = (-u1[0], -u1[1])
    u2 = l2.direction()
    if (corner.x - l2.start.x) * u2[0] + (corner.y - l2.start.y) * u2[1] < 0:
        u2 = (-u2[0], -u2[1])
    p1 = Point(corner.x + u1[0] * distance_m, corner.y + u1[1] * distance_m)
    p2 = Point(corner.x + u2[0] * distance_m, corner.y + u2[1] * distance_m)
    return Line(p1, p2)


# ---------------------------------------------------------------------------
# project / nearest_point / bounding_box
# ---------------------------------------------------------------------------
def project(point: Point, line: Line) -> Point:
    """Orthogonal projection of a point onto the infinite line."""
    dx, dy = line.direction()
    if dx == 0 and dy == 0:
        return line.start
    t = (point.x - line.start.x) * dx + (point.y - line.start.y) * dy
    return Point(line.start.x + dx * t, line.start.y + dy * t)


def nearest_point(obj: object, point: Point) -> Point:
    if isinstance(obj, Line):
        return _point_to_segment(point, obj.start, obj.end)[0]
    if isinstance(obj, (Polygon, Polyline)):
        best: Tuple[Point, float] = (obj.points[0], float("inf"))
        for seg in obj.segments():
            proj, dist = _point_to_segment(point, seg.start, seg.end)
            if dist < best[1]:
                best = (proj, dist)
        return best[0]
    raise GeometryError(message="nearest_point() no soporta el tipo", code="ARQ-GEO-028",
                        context={"type": type(obj).__name__})


def bounding_box(points: Sequence[Point]) -> Tuple[Point, Point]:
    if not points:
        raise GeometryError(message="bounding_box(): lista vacía", code="ARQ-GEO-029")
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    return Point(min(xs), min(ys)), Point(max(xs), max(ys))


# ---------------------------------------------------------------------------
# contorno exterior y aleros (v2.4.0, asistente de edificación)
# ---------------------------------------------------------------------------
def exposed_outline_segments(rects: Sequence[object], tol: float = 1e-6
                             ) -> List[Tuple[float, float, float, float,
                                             float, float]]:
    """Segmentos EXPUESTOS del contorno de la unión de rectángulos.

    Cada rect se lee por pato (atributos «x», «y», «w», «d» axis-
    aligned, como PlacedRoom). Devuelve tuplas (x1, y1, x2, y2, nx, ny)
    donde (nx, ny) es la normal exterior unitaria del borde que originó
    el segmento. Determinista: recorre los rects por orden y cada borde
    en el sentido frente-derecha-fondo-izquierda; los solapes de
    cobertura se restan por unión de intervalos.

    Es el contorno sobre el que se dibujan los ALEROS del asistente.
    """
    solids = [r for r in rects
              if getattr(r, "w", 0.0) > tol and getattr(r, "d", 0.0) > tol]
    segments: List[Tuple[float, float, float, float, float, float]] = []
    for piece in solids:
        px, py = piece.x, piece.y
        edges = (
            ("H", py, px, px + piece.w, 0.0, -1.0),            # frente
            ("H", py + piece.d, px, px + piece.w, 0.0, 1.0),   # fondo
            ("V", px, py, py + piece.d, -1.0, 0.0),            # izquierda
            ("V", px + piece.w, py, py + piece.d, 1.0, 0.0),   # derecha
        )
        for orient, fixed, lo, hi, nx, ny in edges:
            covered: List[Tuple[float, float]] = []
            for other in solids:
                if other is piece:
                    continue
                if orient == "H":
                    touches = (abs(other.y + other.d - fixed) <= tol
                               or abs(other.y - fixed) <= tol)
                    if touches:
                        covered.append((other.x, other.x + other.w))
                else:
                    touches = (abs(other.x + other.w - fixed) <= tol
                               or abs(other.x - fixed) <= tol)
                    if touches:
                        covered.append((other.y, other.y + other.d))
            covered.sort()
            cursor = lo
            for c_lo, c_hi in covered:
                if c_hi <= cursor + tol:
                    continue
                start = max(cursor, c_lo)
                if start > cursor + tol:
                    if orient == "H":
                        segments.append((cursor, fixed, start, fixed,
                                         nx, ny))
                    else:
                        segments.append((fixed, cursor, fixed, start,
                                         nx, ny))
                cursor = max(cursor, c_hi)
            if hi > cursor + tol:
                if orient == "H":
                    segments.append((cursor, fixed, hi, fixed, nx, ny))
                else:
                    segments.append((fixed, cursor, fixed, hi, nx, ny))
    return segments


def eaves_outline_segments(rects: Sequence[object], eaves_m: float,
                           tol: float = 1e-6
                           ) -> List[Tuple[float, float, float, float]]:
    """Línea del ALERO: contorno exterior desplazado «eaves_m» afuera.

    Cada segmento se alarga «eaves_m» por ambos extremos para cerrar
    las esquinas convexas del quiebro (a 90° el alargamiento reproduce
    la ingleta exacta) y después se RECORTA contra los cuerpos: en las
    esquinas cóncavas o entre alas próximas el desplazado entraría en
    otro volumen, y esos tramos se eliminan para que la línea del
    alero nunca cruce el edificio. Devuelve (x1, y1, x2, y2) en
    metros. Con «eaves_m» <= 0 no hay alero: lista vacía.
    """
    if eaves_m <= 0.0:
        return []
    solids = [r for r in rects
              if getattr(r, "w", 0.0) > tol and getattr(r, "d", 0.0) > tol]
    outline: List[Tuple[float, float, float, float]] = []
    for x1, y1, x2, y2, nx, ny in exposed_outline_segments(rects, tol):
        ex1, ey1 = x1 + nx * eaves_m, y1 + ny * eaves_m
        ex2, ey2 = x2 + nx * eaves_m, y2 + ny * eaves_m
        length = math.hypot(x2 - x1, y2 - y1)
        if length > tol:
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            ex1 -= ux * eaves_m
            ey1 -= uy * eaves_m
            ex2 += ux * eaves_m
            ey2 += uy * eaves_m
        for ax, ay, bx, by in _intervals_outside_bodies(
                ex1, ey1, ex2, ey2, solids, tol):
            outline.append((ax, ay, bx, by))
    return outline


def _intervals_outside_bodies(ax: float, ay: float, bx: float, by: float,
                              solids: Sequence[object], tol: float
                              ) -> List[Tuple[float, float, float, float]]:
    """Partes del segmento axis-aligned que NO caen dentro de «solids».

    Devuelve subsegmentos (mismo sentido del original); los tramos que
    atraviesan un cuerpo (esquina cóncava, ala vecina) se recortan.
    """
    horizontal = abs(ay - by) <= tol
    if horizontal:
        lo, hi = min(ax, bx), max(ax, bx)
        covered: List[Tuple[float, float]] = []
        for r in solids:
            if r.y - tol <= ay <= r.y + r.d + tol:
                c_lo, c_hi = max(lo, r.x), min(hi, r.x + r.w)
                if c_hi > c_lo + tol:  # solo solapes reales (nunca invertidos)
                    covered.append((c_lo, c_hi))
        free: List[Tuple[float, float]] = []
        cursor = lo
        for c_lo, c_hi in sorted(covered):
            if c_hi <= cursor + tol:
                continue
            if c_lo > cursor + tol:
                free.append((cursor, c_lo))
            cursor = max(cursor, c_hi)
        if hi > cursor + tol:
            free.append((cursor, hi))
        return [(a, ay, b, ay) for a, b in free]
    if abs(ax - bx) <= tol:
        lo, hi = min(ay, by), max(ay, by)
        covered = []
        for r in solids:
            if r.x - tol <= ax <= r.x + r.w + tol:
                c_lo, c_hi = max(lo, r.y), min(hi, r.y + r.d)
                if c_hi > c_lo + tol:  # solo solapes reales (nunca invertidos)
                    covered.append((c_lo, c_hi))
        free = []
        cursor = lo
        for c_lo, c_hi in sorted(covered):
            if c_hi <= cursor + tol:
                continue
            if c_lo > cursor + tol:
                free.append((cursor, c_lo))
            cursor = max(cursor, c_hi)
        if hi > cursor + tol:
            free.append((cursor, hi))
        return [(ax, a, ax, b) for a, b in free]
    return []  # no debería pasar: todo el trazado es axis-aligned


__all__ = [
    "distance", "angle", "area", "perimeter", "centroid", "extrude_volume",
    "translate", "rotate", "mirror", "scale", "intersection", "contains",
    "overlaps", "overlap_area", "offset", "offset_line", "wall_outline",
    "trim", "extend", "split", "join", "fillet", "chamfer", "project",
    "nearest_point", "bounding_box", "shoelace_area",
    "exposed_outline_segments", "eaves_outline_segments",
]
