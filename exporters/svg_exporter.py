"""Exportador SVG 100% stdlib (v2.0.0, brecha #4).

Plano del proyecto en SVG (una capa <g> por nivel): contornos de
muros, vanos y límites de locales con etiqueta de nombre/área.
Replica el acceso a datos del exportador DXF pero sin dependencias.

v2.4.0: dibuja los ALEROS del asistente de edificación como línea
discontinua alrededor del contorno exterior de cada nivel (se leen
del metadata del edificio; si un nivel tiene locales no rectangulares
se omite su alero con degradación amable).
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from core.errors import ExportError
from core.geometry.engine import eaves_outline_segments
from domain.model import Level, Opening, Space, Wall

PALETTE = {
    "wall": "#37474f",
    "wall_fill": "#eceff1",
    "opening": "#2e7d32",
    "space": "#1565c0",
    "space_fill": "#e3f2fd",
    "text": "#b71c1c",
    "eaves": "#b45309",
}


def export_plan_svg(context, out_path: str, level_ref: Optional[str] = None,
                    title: str = "", eaves_m: Optional[float] = None) -> str:
    """Plano del proyecto → SVG escalable (unidades: metros)."""
    project_id = context.project.id
    walls = context.architecture.list("WALL", project_id)
    openings = context.architecture.list("OPENING", project_id)
    spaces = context.architecture.list("SPACE", project_id)
    levels = {lvl.id: lvl for lvl in context.architecture.list("LEVEL", project_id)}

    if level_ref:
        level = _resolve_level(levels, level_ref)
        walls = [w for w in walls if w.level_id == level.id]
        openings = [o for o in openings if o.level_id == level.id]
        spaces = [s for s in spaces if s.level_id == level.id]
        levels = {level.id: level}

    if not walls and not spaces:
        raise ExportError(
            message="No hay geometría que exportar (muros o locales)",
            code="ARQ-EXP-034",
            suggested_action="Cree muros o locales antes de exportar el plano.")

    if eaves_m is None:
        eaves_m = _eaves_from_context(context)

    openings_by_wall: Dict[str, List[Opening]] = {}
    for opening in openings:
        openings_by_wall.setdefault(opening.wall_id, []).append(opening)

    bodies: List[str] = []
    for index, (level_id, level) in enumerate(levels.items()):
        offset_y = index * 100.0
        name = escape(level.name or f"NIVEL {index + 1}")
        bodies.append(f'<g id="nivel-{index + 1}" data-nombre="{name}">')
        bodies.append(f'<text x="0" y="{offset_y - 3:.2f}" '
                      f'class="nivel">{name}</text>')
        level_spaces = [s for s in spaces if s.level_id == level_id]
        for wall in [w for w in walls if w.level_id == level_id]:
            bodies.append(_wall_svg(wall,
                                    openings_by_wall.get(wall.id, []),
                                    offset_y))
        for space in level_spaces:
            bodies.append(_space_svg(space, offset_y))
        if eaves_m and eaves_m > 0:
            bodies.extend(_eaves_svg(level_spaces, eaves_m, offset_y))
        bodies.append("</g>")

    min_x, min_y, max_x, max_y = _bounds(walls, spaces, levels)
    pad = 5.0
    view = (f"{min_x - pad:.2f} {min_y - pad - 8:.2f} "
            f"{(max_x - min_x) + 2 * pad:.2f} "
            f"{(max_y - min_y) + 2 * pad + 12:.2f}")
    doc_title = escape(title or context.project.name)
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}"
     font-family="Helvetica, Arial, sans-serif">
  <title>{doc_title} — plano ARQ GEN</title>
  <desc>Plano exportado por ARQ GEN (v2.0.0). Unidades: metros.</desc>
  <style>
    .muro {{ fill: {PALETTE['wall_fill']}; stroke: {PALETTE['wall']};
             stroke-width: 0.02; }}
    .vano {{ fill: {PALETTE['opening']}; stroke: none; }}
    .local {{ fill: {PALETTE['space_fill']}; stroke: {PALETTE['space']};
              stroke-width: 0.02; fill-opacity: 0.75; }}
    .etq {{ fill: {PALETTE['text']}; font-size: 0.9px;
            text-anchor: middle; }}
    .nivel {{ fill: {PALETTE['wall']}; font-size: 1.6px; font-weight: bold; }}
    .arco {{ fill: none; stroke: {PALETTE['opening']};
             stroke-width: 0.02; stroke-dasharray: 0.1 0.06; }}
    .alero {{ fill: none; stroke: {PALETTE['eaves']};
              stroke-width: 0.05; stroke-dasharray: 0.45 0.25; }}
  </style>
  {chr(10).join('  ' + line for line in bodies)}
</svg>
"""
    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    context.emit("EXPORT_COMPLETED", {"format": "SVG", "path": out_path})
    return out_path


def _resolve_level(levels: Dict[str, Level], ref: str) -> Level:
    for level in levels.values():
        if level.id == ref or level.code == ref \
                or level.name.lower() == ref.lower():
            return level
    raise ExportError(message=f"Nivel no encontrado: {ref}",
                      code="ARQ-EXP-035")


def _eaves_from_context(context) -> float:
    """Alero a dibujar: del metadata del edificio del asistente.

    Solo con protección solar activada; 0.0 si no hay edificio, no hay
    metadata o el valor no es usable (el alero es un extra, nunca
    rompe la exportación).
    """
    try:
        pid = context.project.id
        for building in context.architecture.list("BUILDING", pid):
            edif = (building.metadata or {}).get("edificacion", {})
            bio = edif.get("bioclimatica", {})
            if bio.get("proteccion_solar"):
                value = float(bio.get("alero_m", 0.0) or 0.0)
                if value > 0.0:
                    return value
    except Exception:  # noqa: BLE001 — el alero nunca bloquea el plano
        return 0.0
    return 0.0


def _rect_of_space(space: Space) -> Optional[Tuple[float, float,
                                                  float, float]]:
    """(x, y, w, d) del local si es un rectángulo axis-aligned."""
    try:
        points = space.polygon().points
    except Exception:  # noqa: BLE001 — local degenerado
        return None
    if len(points) != 4:
        return None
    xs = [round(p.x, 6) for p in points]
    ys = [round(p.y, 6) for p in points]
    if len(set(xs)) != 2 or len(set(ys)) != 2:
        return None
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class _Rect:
    """Rectángulo mínimo (pato) para el motor geométrico del alero."""

    __slots__ = ("x", "y", "w", "d")

    def __init__(self, x: float, y: float, w: float, d: float) -> None:
        self.x, self.y, self.w, self.d = x, y, w, d


def _eaves_svg(spaces: List[Space], eaves_m: float,
               offset_y: float) -> List[str]:
    """Líneas discontinuas del alero alrededor del nivel (si cuadra).

    Si algún local del nivel no es un rectángulo axis-aligned, el
    contorno no sería fiel: se omite el alero de ese nivel.
    """
    rects: List[_Rect] = []
    for space in spaces:
        rect = _rect_of_space(space)
        if rect is None:
            return []
        rects.append(_Rect(*rect))
    parts: List[str] = []
    for x1, y1, x2, y2 in eaves_outline_segments(rects, eaves_m):
        parts.append(
            f'<line class="alero" x1="{x1:.3f}" '
            f'y1="{y1 + offset_y:.3f}" x2="{x2:.3f}" '
            f'y2="{y2 + offset_y:.3f}"><title>Alero '
            f'{eaves_m:.2f} m</title></line>')
    return parts


def _wall_svg(wall: Wall, openings: List[Opening],
              offset_y: float) -> str:
    from core.geometry import engine as ge
    from core.geometry.primitives import Line, Point
    axis = Line(Point(*wall.start), Point(*wall.end))
    outline = ge.wall_outline(axis, wall.thickness_m)
    points = " ".join(f"{p.x:.3f},{p.y + offset_y:.3f}"
                      for p in outline.points)
    parts = [f'<polygon class="muro" points="{points}">']
    parts.append(f'<title>Muro {escape(wall.code)} · '
                 f'{wall.thickness_m:.2f} m</title></polygon>')
    if axis.length > 0:
        for opening in openings:
            parts.append(_opening_svg(axis, wall, opening, offset_y))
    return "\n    ".join(parts)


def _opening_svg(axis, wall: Wall, opening: Opening,
                 offset_y: float) -> str:
    from core.geometry import engine as ge
    from core.geometry.primitives import Line, Point
    t0 = opening.offset_m / axis.length
    t1 = (opening.offset_m + opening.width_m) / axis.length
    p_a = Point(axis.start.x + (axis.end.x - axis.start.x) * t0,
                axis.start.y + (axis.end.y - axis.start.y) * t0)
    p_b = Point(axis.start.x + (axis.end.x - axis.start.x) * t1,
                axis.start.y + (axis.end.y - axis.start.y) * t1)
    half = wall.thickness_m / 2.0
    left_a = ge.offset_line(Line(p_a, p_b), half).start
    left_b = ge.offset_line(Line(p_a, p_b), half).end
    right_b = ge.offset_line(Line(p_a, p_b), -half).end
    right_a = ge.offset_line(Line(p_a, p_b), -half).start
    rect = [left_a, left_b, right_b, right_a]
    points = " ".join(f"{p.x:.3f},{p.y + offset_y:.3f}" for p in rect)
    parts = [f'<polygon class="vano" points="{points}"/>']
    if opening.kind == "DOOR" and axis.length > 0:
        radius = opening.width_m
        start = math.degrees(math.atan2(left_a.y - p_b.y,
                                        left_a.x - p_b.x))
        end = start - 90.0
        parts.append(
            f'<path class="arco" d="M {p_b.x:.3f} {p_b.y + offset_y:.3f} '
            f'A {radius:.3f} {radius:.3f} 0 0 '
            f'{1 if end < start else 0} '
            f'{left_b.x:.3f} {left_b.y + offset_y:.3f}"/>')
    return "\n    ".join(parts)


def _space_svg(space: Space, offset_y: float) -> str:
    try:
        polygon = space.polygon()
        area = space.area_m2()
    except Exception:  # noqa: BLE001 — local degenerado: se omite etiqueta
        polygon = None
        area = 0.0
    parts = []
    if polygon is not None and area > 0:
        points = " ".join(f"{p.x:.3f},{p.y + offset_y:.3f}"
                          for p in polygon.points)
        parts.append(f'<polygon class="local" points="{points}"/>')
        center = polygon.centroid() if hasattr(polygon, "centroid") else None
        if center is None:
            center = type(polygon.points[0])(
                sum(p.x for p in polygon.points) / len(polygon.points),
                sum(p.y for p in polygon.points) / len(polygon.points))
        label = f"{space.name} ({area:.1f} m2)"
        parts.append(
            f'<text class="etq" x="{center.x:.3f}" '
            f'y="{center.y + offset_y + 0.3:.3f}">{escape(label)}</text>')
    else:
        parts.append(f'<!-- local {escape(space.code)} sin polígono -->')
    return "\n    ".join(parts)


def _bounds(walls: List[Wall], spaces: List[Space],
            levels: Dict[str, Level]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for wall in walls:
        xs += [wall.start[0], wall.end[0]]
        ys += [wall.start[1], wall.end[1]]
    for space in spaces:
        try:
            polygon = space.polygon()
        except Exception:  # noqa: BLE001
            continue
        for point in polygon.points:
            xs.append(point.x)
            ys.append(point.y)
    for index, level in enumerate(levels.items()):
        ys.append(index * 100.0)
    if not xs:
        xs, ys = [0.0, 10.0], [0.0, 10.0]
    return min(xs), min(ys), max(xs), max(ys)
