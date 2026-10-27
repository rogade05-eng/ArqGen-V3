"""Geometría orgánica (v3.2.0): arcos, chaflanes y curvas suaves.

Helpers PUROS para la capa de diseño orgánico del asistente: muros
curvos (arco con flecha dada), esquinas redondeadas o a 45°, y curvas
en S para pasillos que respiran. Todo se materializa como POLILÍNEAS
de puntos — el trazado del asistente los convierte en muros rectos
cortos, así el resto del motor (vanos, QTO, representación,
exportadores) no cambia.

El signo de «bulge» decide el lado de la flecha respecto del vector
p0→p1: positivo = a la izquierda del sentido de avance.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Point = Tuple[float, float]

TWO_PI = 2.0 * math.pi


# -- arcos --------------------------------------------------------------------

def _rotate_half(vx: float, vy: float, cos_a: float,
                 sin_a: float) -> Point:
    return (vx * cos_a - vy * sin_a, vx * sin_a + vy * cos_a)


def arc_polyline(p0: Point, p1: Point, bulge: float,
                 segments: int = 10) -> List[Point]:
    """Polilínea del arco circular de p0 a p1 con flecha «bulge».

    La flecha (sagitta) es la distancia del punto medio del arco a la
    cuerda p0→p1; su signo elige el lado. Con «bulge» ≈ 0 devuelve la
    cuerda en «segments» tramos. «segments» mínimo 2; el primero y el
    último punto SON p0 y p1.
    """
    if segments < 2:
        segments = 2
    chord_x, chord_y = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(chord_x, chord_y)
    if length <= 1e-9 or abs(bulge) <= 1e-9:
        step = 1.0 / (segments - 1)
        return [(p0[0] + chord_x * i * step,
                 p0[1] + chord_y * i * step) for i in range(segments)]

    # Circunferencia por las 3 condiciones: pasa por p0 y p1 y su punto
    # medio dista «bulge» de la cuerda (perpendicular a la izquierda).
    radius = (length * length / 4.0 + bulge * bulge) / (2.0 * abs(bulge))
    # Centro: sobre la mediatriz de la cuerda.
    half = length / 2.0
    offset = math.sqrt(max(radius * radius - half * half, 0.0))
    ux, uy = chord_x / length, chord_y / length
    # Signo: el centro queda al lado OPUESTO de la flecha.
    side = -1.0 if bulge > 0 else 1.0
    mx, my = p0[0] + chord_x / 2.0, p0[1] + chord_y / 2.0
    cx = mx + side * offset * (-uy)
    cy = my + side * offset * ux

    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    sweep = a1 - a0
    while sweep > math.pi:
        sweep -= TWO_PI
    while sweep < -math.pi:
        sweep += TWO_PI
    # El sentido correcto es el que pasa por el punto de flecha.
    mid_angle = a0 + sweep / 2.0
    mid = (cx + radius * math.cos(mid_angle),
           cy + radius * math.sin(mid_angle))
    # Distancia con signo del punto medio a la cuerda (lado izquierdo
    # positivo): si no coincide con el pedido, se invierte el sentido.
    cross = (chord_x * (mid[1] - p0[1]) - chord_y * (mid[0] - p0[0]))
    signed = cross / length
    if signed * bulge < 0:
        sweep = -sweep

    points: List[Point] = []
    for i in range(segments):
        angle = a0 + sweep * i / (segments - 1)
        points.append((cx + radius * math.cos(angle),
                       cy + radius * math.sin(angle)))
    points[0] = p0
    points[-1] = p1
    return points


def s_curve_polyline(p0: Point, p1: Point, amplitude: float,
                     segments: int = 12) -> List[Point]:
    """Polilínea en S suave de p0 a p1 (sin(p) escalado a «amplitude»).

    El desvío es CERO en los extremos y máximo en el centro, hacia la
    izquierda del tramo p0→p1 con «amplitude» positiva. Ideal para el
    muro libre de un pasillo: nunca roza los vanos de los extremos.
    """
    if segments < 2:
        segments = 2
    chord_x, chord_y = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(chord_x, chord_y)
    ux, uy = (chord_x / length, chord_y / length) if length > 1e-9 \
        else (1.0, 0.0)
    # Normal a la izquierda del avance.
    nx, ny = -uy, ux
    points: List[Point] = []
    for i in range(segments):
        t = i / (segments - 1)
        deviation = amplitude * math.sin(math.pi * t)
        points.append((p0[0] + chord_x * t + nx * deviation,
                       p0[1] + chord_y * t + ny * deviation))
    points[0] = p0
    points[-1] = p1
    return points


# -- esquinas ------------------------------------------------------------------

def chamfer_points(corner: Point, prev_pt: Point, next_pt: Point,
                   cut: float) -> Tuple[Point, Point]:
    """Los dos puntos del chaflán recto que sustituye a «corner».

    «cut» se mide SOBRE cada arista desde la esquina (se recorta si
    excede la mitad de la arista más corta).
    """
    def toward(corner_pt: Point, other: Point, dist: float) -> Point:
        dx, dy = other[0] - corner_pt[0], other[1] - corner_pt[1]
        d = math.hypot(dx, dy)
        if d <= 1e-9:
            return corner_pt
        dist = min(dist, d / 2.0)
        return (corner_pt[0] + dx / d * dist,
                corner_pt[1] + dy / d * dist)

    return (toward(corner, prev_pt, cut), toward(corner, next_pt, cut))


def fillet_points(corner: Point, prev_pt: Point, next_pt: Point,
                  radius: float, segments: int = 8) -> List[Point]:
    """Polilínea del RADO de esquina de radio «radius» (esquina curva).

    Devuelve [tangente_en_prev, … arco …, tangente_en_next]. Si el
    radio no cabe en las aristas, se recorta a la mitad de la más
    corta (nunca lanza).
    """
    def edge(corner_pt: Point, other: Point) -> Tuple[float, float, float]:
        dx, dy = other[0] - corner_pt[0], other[1] - corner_pt[1]
        d = math.hypot(dx, dy)
        return (dx / d, dy / d, d) if d > 1e-9 else (1.0, 0.0, 0.0)

    ux1, uy1, len1 = edge(corner, prev_pt)
    ux2, uy2, len2 = edge(corner, next_pt)
    radius = max(0.05, min(radius, len1 / 2.0, len2 / 2.0))

    # Ángulo interior entre las aristas (salir de la esquina).
    dot = max(-1.0, min(1.0, ux1 * ux2 + uy1 * uy2))
    theta = math.acos(dot)
    if theta < 1e-3 or abs(math.pi - theta) < 1e-3:
        # Aristas colineales: nada que redondear.
        return []
    # Distancia tangente desde la esquina.
    tangent = radius / math.tan(theta / 2.0)
    tangent = min(tangent, len1 / 2.0, len2 / 2.0)
    radius = tangent * math.tan(theta / 2.0)

    t1 = (corner[0] + ux1 * tangent, corner[1] + uy1 * tangent)
    t2 = (corner[0] + ux2 * tangent, corner[1] + uy2 * tangent)

    # Centro del arco: a distancia radius de ambas tangentes, hacia
    # dentro del ángulo (bisectriz).
    bx, by = ux1 + ux2, uy1 + uy2
    bnorm = math.hypot(bx, by)
    if bnorm <= 1e-9:
        return [t1, t2]
    bx, by = bx / bnorm, by / bnorm
    cx = t1[0] + bx * radius
    cy = t1[1] + by * radius

    a1 = math.atan2(t1[1] - cy, t1[0] - cx)
    a2 = math.atan2(t2[1] - cy, t2[0] - cx)
    sweep = a2 - a1
    while sweep > math.pi:
        sweep -= TWO_PI
    while sweep < -math.pi:
        sweep += TWO_PI
    points: List[Point] = []
    for i in range(max(2, segments)):
        angle = a1 + sweep * i / (max(2, segments) - 1)
        points.append((cx + radius * math.cos(angle),
                       cy + radius * math.sin(angle)))
    points[0] = t1
    points[-1] = t2
    return points


# -- utilidades ----------------------------------------------------------------

def polyline_length(points: Sequence[Point]) -> float:
    """Longitud total de la polilínea."""
    total = 0.0
    for i in range(1, len(points)):
        total += math.hypot(points[i][0] - points[i - 1][0],
                            points[i][1] - points[i - 1][1])
    return total


def wall_polyline(start: Point, end: Point, mode: str, size: float,
                  segments: int = 10) -> List[Point]:
    """Polilínea orgánica para sustituir un muro recto.

    - mode «arco»: arco de flecha «size» (izquierda del avance p0→p1).
    - mode «s»: curva en S de amplitud «size».
    - otro: cuerda recta (comportamiento neutro).
    """
    if mode == "arco":
        return arc_polyline(start, end, size, segments)
    if mode == "s":
        return s_curve_polyline(start, end, size, max(segments, 12))
    return [start, end]


__all__ = [
    "arc_polyline", "s_curve_polyline", "chamfer_points",
    "fillet_points", "polyline_length", "wall_polyline",
]
