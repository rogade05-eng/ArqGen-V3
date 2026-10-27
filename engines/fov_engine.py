"""FOV Engine (spec section 39).

Motor de campo visual para CCTV del spec 39:

    field_of_view()      polígono de cobertura por ray casting
    ray_casting()        distancia libre del rayo hasta el muro más cercano
    obstacle_detection() obstáculos que recortan el cono
    blind_spots()        zonas del objetivo sin cobertura
    coverage()           área cubierta y porcentaje sobre el objetivo
    overlap()            solapamiento entre dos coberturas
    target_detection()   ¿un punto objetivo es visible?

Algoritmo determinista del cono:
  1. Se generan los rayos del cono: dos bordes exteriores (FOV), un haz
     intermedio por paso fijo y un rayo hacia cada extremo de muro
     dentro del ángulo (evita "atravesar" esquinas).
  2. Cada rayo se trunca en el muro más cercano (ray casting contra
     segmentos) o en el alcance máximo de la cámara.
  3. El polígono de cobertura = vértices ordenados por ángulo.

El motor no consulta la base de datos: recibe posiciones y segmentos
(muros) puros, igual que el motor de rutas (§26).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
Wall = Tuple[Point, Point]

DEFAULT_FOV_DEG = 90.0
DEFAULT_RANGE_M = 12.0
RAY_STEP_DEG = 5.0


@dataclass
class CoverageResult:
    """Resultado de cobertura de una cámara (CoveragePolygon y métricas)."""

    camera: str = ""
    polygon: List[Point] = field(default_factory=list)
    area_m2: float = 0.0
    occluded_walls: int = 0
    range_m: float = DEFAULT_RANGE_M
    fov_deg: float = DEFAULT_FOV_DEG

    def to_dict(self) -> dict:
        return {
            "camera": self.camera,
            "polygon": [[round(x, 4), round(y, 4)] for x, y in self.polygon],
            "area_m2": round(self.area_m2, 3),
            "occluded_walls": self.occluded_walls,
            "range_m": self.range_m, "fov_deg": self.fov_deg,
        }


def _ray_segment_distance(origin: Point, direction: Point,
                          a: Point, b: Point) -> Optional[float]:
    """Distancia paramétrica del rayo al segmento ab (None si no corta)."""
    ox, oy = origin
    dx, dy = direction
    ax, ay = a
    bx, by = b
    ex, ey = bx - ax, by - ay
    denominator = dx * ey - dy * ex
    if abs(denominator) < 1e-12:
        return None                      # rayo paralelo al segmento
    t = ((ax - ox) * ey - (ay - oy) * ex) / denominator
    u = ((ax - ox) * dy - (ay - oy) * dx) / denominator
    if t <= 1e-9 or not -1e-9 <= u <= 1.0 + 1e-9:
        return None
    return t


def ray_casting(origin: Point, direction: Point, walls: Sequence[Wall],
                max_distance: float) -> float:
    """Distancia libre del rayo: hasta el muro más cercano o max_distance
    (ray_casting/obstacle_detection del spec 39)."""
    best = max_distance
    for wall in walls:
        t = _ray_segment_distance(origin, direction, wall[0], wall[1])
        if t is not None and t < best:
            best = t
    return best


def _polygon_area(points: Sequence[Point]) -> float:
    """Área con fórmula del cordón (autónomo, sin dependencias)."""
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def field_of_view(camera: str, position: Point, direction_deg: float,
                  fov_deg: float = DEFAULT_FOV_DEG,
                  range_m: float = DEFAULT_RANGE_M,
                  walls: Sequence[Wall] = ()) -> CoverageResult:
    """Polígono de cobertura por ray casting (field_of_view, spec 39).

    direction_deg: orientación del eje óptico en grados (0 = +x,
    antihorario positivo). El cono se abre fov_deg alrededor del eje.
    """
    if fov_deg <= 0 or fov_deg > 360:
        fov_deg = DEFAULT_FOV_DEG
    ox, oy = position
    half = fov_deg / 2.0
    start_angle = direction_deg - half
    end_angle = direction_deg + half

    angles: List[float] = [start_angle, end_angle]
    steps = max(1, int(math.ceil(fov_deg / RAY_STEP_DEG)))
    for i in range(1, steps):
        angles.append(start_angle + fov_deg * i / steps)
    # Rayos hacia los extremos de muro dentro del cono (esquinas).
    for wall in walls:
        for endpoint in wall:
            angle = math.degrees(math.atan2(endpoint[1] - oy,
                                            endpoint[0] - ox))
            # Normalizar al rango [start_angle, end_angle].
            while angle < start_angle - 1e-9:
                angle += 360.0
            while angle > end_angle + 1e-9:
                angle -= 360.0
            if start_angle - 1e-9 <= angle <= end_angle + 1e-9:
                angles.append(angle)
    angles.sort()

    polygon: List[Point] = [position]
    occluded = 0
    for angle in angles:
        radians = math.radians(angle)
        direction = (math.cos(radians), math.sin(radians))
        distance = ray_casting(position, direction, walls, range_m)
        if distance < range_m - 1e-9:
            occluded += 1
        polygon.append((ox + direction[0] * distance,
                        oy + direction[1] * distance))
    # El abanico cierra en la cámara: el polígono incluye el vértice del
    # cono (posición de la cámara) como primer/último punto.
    area = abs(_polygon_area(polygon)) if len(polygon) >= 3 else 0.0
    return CoverageResult(camera=camera, polygon=polygon, area_m2=area,
                          occluded_walls=occluded, range_m=range_m,
                          fov_deg=fov_deg)


def coverage_percentage(coverage: CoverageResult, target_area_m2: float) -> float:
    """Porcentaje del objetivo cubierto por la cámara (coverage)."""
    if target_area_m2 <= 0:
        return 0.0
    return round(min(coverage.area_m2 / target_area_m2 * 100.0, 100.0), 2)


def overlap_area(coverage_a: CoverageResult,
                 coverage_b: CoverageResult) -> float:
    """Área de solapamiento entre dos coberturas (overlap, spec 39)."""
    from core.geometry.engine import overlap_area as geo_overlap_area
    from core.geometry.primitives import Polygon
    if len(coverage_a.polygon) < 3 or len(coverage_b.polygon) < 3:
        return 0.0
    polygon_a = Polygon([list(p) for p in coverage_a.polygon])
    polygon_b = Polygon([list(p) for p in coverage_b.polygon])
    return abs(geo_overlap_area(polygon_a, polygon_b))


def blind_spots(target_polygon_points: Sequence[Point],
                coverages: Sequence[CoverageResult]) -> Dict[str, float]:
    """Puntos ciegos del objetivo respecto de las coberturas (blind_spots).

    Devuelve área total del objetivo, área cubierta (unión aproximada por
    adición de fracciones) y porcentaje ciego. La unión se calcula por
    integración numérica determinista en retícula fina.
    """
    if len(target_polygon_points) < 3:
        return {"target_m2": 0.0, "covered_m2": 0.0, "blind_pct": 100.0}
    target_area = abs(_polygon_area(list(target_polygon_points)))
    xs = [p[0] for p in target_polygon_points]
    ys = [p[1] for p in target_polygon_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    # Retícula determinista ~0.25 m, ajustada a la caja del objetivo.
    steps_x = max(2, min(120, int((max_x - min_x) / 0.25) + 1))
    steps_y = max(2, min(120, int((max_y - min_y) / 0.25) + 1))
    cell_area = (max_x - min_x) * (max_y - min_y) / (steps_x * steps_y)
    from core.geometry.engine import contains
    from core.geometry.primitives import Point as GeoPoint, Polygon as GeoPolygon
    target_poly = GeoPolygon([GeoPoint(p[0], p[1])
                              for p in target_polygon_points])
    covered_cells = 0
    total_cells = 0
    for i in range(steps_x):
        for j in range(steps_y):
            x = min_x + (i + 0.5) * (max_x - min_x) / steps_x
            y = min_y + (j + 0.5) * (max_y - min_y) / steps_y
            if not contains(target_poly, GeoPoint(x, y)):
                continue
            total_cells += 1
            for coverage in coverages:
                if len(coverage.polygon) < 3:
                    continue
                poly = GeoPolygon([GeoPoint(p[0], p[1])
                                   for p in coverage.polygon])
                if contains(poly, GeoPoint(x, y)):
                    covered_cells += 1
                    break
    if total_cells == 0:
        return {"target_m2": round(target_area, 3), "covered_m2": 0.0,
                "blind_pct": 100.0}
    covered = covered_cells * cell_area
    blind_pct = 100.0 - min(covered / target_area * 100.0, 100.0)
    return {"target_m2": round(target_area, 3), "covered_m2": round(covered, 3),
            "blind_pct": round(blind_pct, 2)}


def target_detection(point: Point, coverages: Sequence[CoverageResult]) -> bool:
    """¿El punto objetivo cae dentro de alguna cobertura? (target_detection)."""
    from core.geometry.engine import contains
    from core.geometry.primitives import Polygon as GeoPolygon
    from core.geometry.primitives import Point as GeoPoint

    def _on_edge(polygon: Sequence[Point], p: Point, tol: float = 1e-6) -> bool:
        """True cuando p yace sobre un borde del polígono (caso límite)."""
        px, py = p
        for i in range(len(polygon)):
            (ax, ay), (bx, by) = polygon[i], polygon[(i + 1) % len(polygon)]
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            if length2 <= 1e-18:
                continue
            t = ((px - ax) * dx + (py - ay) * dy) / length2
            if not -1e-9 <= t <= 1.0 + 1e-9:
                continue
            qx, qy = ax + dx * t, ay + dy * t
            if abs(px - qx) <= tol and abs(py - qy) <= tol:
                return True
        return False

    for coverage in coverages:
        if len(coverage.polygon) < 3:
            continue
        if _on_edge(coverage.polygon, point):
            return True
        poly = GeoPolygon([GeoPoint(p[0], p[1]) for p in coverage.polygon])
        if contains(poly, GeoPoint(point[0], point[1])):
            return True
    return False


def camera_position_candidates(target_polygon_points: Sequence[Point],
                               direction_deg: float = 0.0,
                               fov_deg: float = DEFAULT_FOV_DEG,
                               range_m: float = DEFAULT_RANGE_M,
                               walls: Sequence[Wall] = (),
                               grid_m: float = 1.0
                               ) -> List[Tuple[Point, float]]:
    """Candidatos de posición para optimización (spec 40).

    Genera una retícula determinista de posiciones dentro del objetivo y
    devuelve (posición, área_cubierta) ordenada por área descendente.
    El usuario elige la alternativa; el motor no impone la solución.
    """
    from core.geometry.engine import contains
    from core.geometry.primitives import Point as GeoPoint, Polygon as GeoPolygon
    if len(target_polygon_points) < 3:
        return []
    xs = [p[0] for p in target_polygon_points]
    ys = [p[1] for p in target_polygon_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    target_poly = GeoPolygon([GeoPoint(p[0], p[1])
                              for p in target_polygon_points])
    candidates: List[Tuple[Point, float]] = []
    nx = max(1, int((max_x - min_x) / grid_m))
    ny = max(1, int((max_y - min_y) / grid_m))
    for i in range(nx + 1):
        for j in range(ny + 1):
            x = min_x + i * grid_m
            y = min_y + j * grid_m
            if not contains(target_poly, GeoPoint(x, y)):
                continue
            coverage = field_of_view("candidate", (x, y), direction_deg,
                                     fov_deg, range_m, walls)
            candidates.append(((x, y), coverage.area_m2))
    candidates.sort(key=lambda item: (-item[1], item[0][0], item[0][1]))
    return candidates


__all__ = [
    "CoverageResult", "DEFAULT_FOV_DEG", "DEFAULT_RANGE_M", "RAY_STEP_DEG",
    "field_of_view", "ray_casting", "coverage_percentage", "overlap_area",
    "blind_spots", "target_detection", "camera_position_candidates",
]
