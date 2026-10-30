"""DXF exporter via ezdxf (spec sections 64, 65, 69, 95).

Real multi-layer DXF: wall outlines, openings, space boundaries with
name/area labels, level separated by DXF layout. Units = meters.

v3.31.0 — ``version="R12"`` exporta DXF R12 ASCII de máxima
compatibilidad (AutoCAD R12, CNC, visores antiguos): entidades
clásicas LINE/ARC/TEXT (R12 no conoce LWPOLYLINE), todo en el
modelspace con un bloque desplazado por nivel y rotulado
«PLANTA_<NOMBRE>». El R2010 de siempre queda intacto.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from core.errors import ExportError
from domain.model import Level, Opening, Space, Wall

_Punto = Tuple[float, float]


class DXFExporter:
    LAYERS = {
        "ARQ-WALL": {"color": 7},
        "ARQ-OPENING": {"color": 3},
        "ARQ-SPACE": {"color": 8},
        "ARQ-TEXT": {"color": 1},
        "ARQ-AXIS": {"color": 5},
        "ARQ-STAIR": {"color": 4},
    }

    def export(self, context, out_path: str, level_ref: Optional[str] = None,
               version: str = "R2010") -> str:
        try:
            import ezdxf
        except ImportError as exc:  # pragma: no cover - dependency guarded by requirements
            raise ExportError(
                message="ezdxf no está instalado; ejecute el bat de instalación de dependencias",
                code="ARQ-EXP-030") from exc

        version = str(version or "R2010").upper()
        if version not in ("R2010", "R12"):
            raise ExportError(
                message=f"Versión DXF no soportada: {version}",
                code="ARQ-EXP-061",
                suggested_action="Use R2010 (por defecto) o R12 "
                                 "(compatibilidad).")

        project_id = context.project.id
        walls = context.architecture.list("WALL", project_id)
        openings = context.architecture.list("OPENING", project_id)
        spaces = context.architecture.list("SPACE", project_id)
        stairs = context.architecture.list("STAIR", project_id)
        levels = {l.id: l for l in context.architecture.list("LEVEL", project_id)}

        if level_ref:
            level = self._resolve_level(levels, level_ref)
            walls = [w for w in walls if w.level_id == level.id]
            openings = [o for o in openings if o.level_id == level.id]
            spaces = [s for s in spaces if s.level_id == level.id]
            stairs = [s for s in stairs if s.level_id == level.id]
            levels = {level.id: level}

        if not walls and not spaces and not any((s.metadata or {}).get("outline") for s in stairs):
            raise ExportError(
                message="No hay geometría que exportar (muros, locales o escaleras)",
                code="ARQ-EXP-031",
                suggested_action="Cree muros o locales antes de exportar el plano.",
            )

        doc = ezdxf.new("R12" if version == "R12" else "R2010",
                        setup=False if version == "R12" else True)
        # $INSUNITS llegó con AutoCAD 2000: en R12 se guarda sin
        # garantía, así que se intenta y se ignora si el lector no lo
        # pide.
        try:
            doc.header["$INSUNITS"] = 6  # meters
            doc.header["$MEASUREMENT"] = 1
        except Exception:  # noqa: BLE001 - cabecera R12 minimalista
            pass
        for layer, props in self.LAYERS.items():
            if layer not in doc.layers:
                doc.layers.add(name=layer, color=props["color"])

        openings_by_wall: Dict[str, List[Opening]] = {}
        for opening in openings:
            openings_by_wall.setdefault(opening.wall_id, []).append(opening)

        r12 = version == "R12"
        if r12:
            # R12: sin layouts de paperspace, todo al modelspace con un
            # desplazamiento vertical por nivel y un rótulo de planta.
            msp = doc.modelspace()
            for index, (level_id, level) in enumerate(levels.items()):
                offset_y = index * 100.0
                nombre = (level.name or f"NIVEL_{index + 1}").upper()
                msp.add_text(
                    f"PLANTA_{nombre.replace(' ', '_')}",
                    height=0.8,
                    dxfattribs={"layer": "ARQ-TEXT"},
                ).set_placement((-8.0, offset_y + 6.0))
                for wall in [w for w in walls if w.level_id == level_id]:
                    self._draw_wall(msp, wall,
                                    openings_by_wall.get(wall.id, []),
                                    offset_y, r12=True)
                for space in [s for s in spaces if s.level_id == level_id]:
                    self._draw_space(msp, space, offset_y, r12=True)
                for stair in [s for s in stairs if s.level_id == level_id]:
                    self._draw_stair(msp, stair, offset_y, r12=True)
        else:
            # One layout per level (paperspace layouts support the same entity factory).
            for index, (level_id, level) in enumerate(levels.items()):
                offset_y = index * 100.0
                layout_name = f"PLANTA_{(level.name or f'NIVEL_{index+1}').upper().replace(' ', '_')}"
                try:
                    target = doc.layouts.get(layout_name)
                except Exception:
                    target = doc.layouts.new(layout_name)

                for wall in [w for w in walls if w.level_id == level_id]:
                    self._draw_wall(target, wall,
                                    openings_by_wall.get(wall.id, []),
                                    offset_y)
                for space in [s for s in spaces if s.level_id == level_id]:
                    self._draw_space(target, space, offset_y)
                for stair in [s for s in stairs if s.level_id == level_id]:
                    self._draw_stair(target, stair, offset_y)

        directory = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(directory, exist_ok=True)
        try:
            doc.saveas(out_path)
        except Exception as exc:
            raise ExportError(
                message=f"No se pudo escribir el DXF: {exc}",
                code="ARQ-EXP-032", context={"path": out_path}) from exc
        context.emit("EXPORT_COMPLETED",
                     {"format": f"DXF {version}", "path": out_path})
        return out_path

    @staticmethod
    def _resolve_level(levels: Dict[str, Level], ref: str) -> Level:
        for level in levels.values():
            if level.id == ref or level.code == ref or level.name.lower() == ref.lower():
                return level
        raise ExportError(message=f"Nivel no encontrado: {ref}", code="ARQ-EXP-033")

    def _polilinea(self, msp, puntos: List[_Punto], capa: str,
                   r12: bool) -> None:
        """Polilínea cerrada: LWPOLYLINE en R2010, LINEs en R12."""
        if r12:
            for i in range(len(puntos)):
                a = puntos[i]
                b = puntos[(i + 1) % len(puntos)]
                msp.add_line(a, b, dxfattribs={"layer": capa})
        else:
            msp.add_lwpolyline(puntos, close=True,
                               dxfattribs={"layer": capa})

    def _draw_stair(self, msp, stair, offset_y: float, r12: bool = False) -> None:
        """Planta de la entidad: contorno y huellas en coordenadas de mundo."""
        meta = stair.metadata or {}
        def mundo(p):
            return (float(p[0]) + stair.x, float(p[1]) + stair.y + offset_y)
        outline = meta.get("outline") or []
        if len(outline) >= 3:
            self._polilinea(msp, [mundo(p) for p in outline], "ARQ-STAIR", r12)
        for tread in meta.get("treads") or []:
            if len(tread) >= 2:
                msp.add_line(mundo(tread[0]), mundo(tread[1]),
                             dxfattribs={"layer": "ARQ-STAIR"})

    def _draw_wall(self, msp, wall: Wall, openings: List[Opening],
                   offset_y: float, r12: bool = False) -> None:
        from core.geometry import engine as ge
        from core.geometry.primitives import Line, Point
        axis = Line(Point(*wall.start), Point(*wall.end))
        outline = ge.wall_outline(axis, wall.thickness_m)
        points = [(p.x, p.y + offset_y) for p in outline.points]
        self._polilinea(msp, points, "ARQ-WALL", r12)
        # Openings: rectangle on the wall + door swing arc
        if axis.length <= 0:
            return
        for opening in openings:
            self._draw_opening(msp, axis, wall, opening, offset_y,
                               r12=r12)

    def _draw_opening(self, msp, axis, wall: Wall, opening: Opening,
                      offset_y: float, r12: bool = False) -> None:
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
        right_a = ge.offset_line(Line(p_a, p_b), -half).start
        left_b = ge.offset_line(Line(p_a, p_b), half).end
        right_b = ge.offset_line(Line(p_a, p_b), -half).end
        rect = [left_a.to_tuple(), left_b.to_tuple(), right_b.to_tuple(),
                right_a.to_tuple()]
        shifted = [(x, y + offset_y) for x, y in rect]
        self._polilinea(msp, shifted, "ARQ-OPENING", r12)
        if opening.kind == "DOOR":
            # Swing arc (90°) from hinge at left_a
            radius = opening.width_m
            start_angle = Line(left_a, p_b).angle_deg()
            msp.add_arc(
                center=(left_a.x, left_a.y + offset_y), radius=radius,
                start_angle=start_angle, end_angle=start_angle + 90,
                dxfattribs={"layer": "ARQ-OPENING"})
        elif opening.kind == "WINDOW":
            mid = Point((left_a.x + right_b.x) / 2, (left_a.y + right_b.y) / 2)
            msp.add_line((left_a.x, left_a.y + offset_y),
                         (right_b.x, right_b.y + offset_y),
                         dxfattribs={"layer": "ARQ-OPENING"})

    def _draw_space(self, msp, space: Space, offset_y: float,
                    r12: bool = False) -> None:
        if len(space.boundary) < 3:
            return
        points = [(x, y + offset_y) for x, y in space.boundary]
        self._polilinea(msp, points, "ARQ-SPACE", r12)
        centroid_x = sum(p[0] for p in points) / len(points)
        centroid_y = sum(p[1] for p in points) / len(points)
        label = f"{space.name} ({space.area_m2():.1f} m2)"
        msp.add_text(
            label,
            height=0.2,
            dxfattribs={"layer": "ARQ-TEXT"},
        ).set_placement((centroid_x - 0.5, centroid_y + offset_y))
        area_text = f"AREA {space.area_m2():.2f} m2"
        msp.add_text(
            area_text,
            height=0.15,
            dxfattribs={"layer": "ARQ-TEXT"},
        ).set_placement((centroid_x - 0.5, centroid_y - 0.35 + offset_y))


__all__ = ["DXFExporter"]
