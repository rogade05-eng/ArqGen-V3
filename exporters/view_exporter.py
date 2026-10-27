"""Exportador SVG de VISTAS del asistente (v2.6.0, brecha #4 ampliada).

De la variante elegida y los datos del asistente exporta la vista
activa — PLANTA, ELEVACIÓN, CORTE o DETALLES — en SVG escalable.
Comparte las primitivas con el lienzo Tkinter (core.geometry.
representation), así que lienzo y archivo dibujan lo mismo.

Las tramas de material (hatch) se materializan como <pattern> SVG;
100 % stdlib, determinista y tolerante (una vista vacía no rompe).
"""

from __future__ import annotations

import math
import os
from typing import Any, List, Optional, Tuple
from xml.sax.saxutils import escape

from core.geometry import representation as rep

VIEWS = ("Planta", "Elevación", "Corte", "Detalles")


# --------------------------------------------------------------------------
# Tramas como <pattern>
# --------------------------------------------------------------------------

def _pattern_defs(keys: List[str]) -> str:
    """<defs> con un <pattern> por trama usada (unidades métricas)."""
    parts: List[str] = []
    for key in sorted(set(keys)):
        pattern = rep.HATCH_PATTERNS.get(key)
        if pattern is None or pattern.kind in ("solido", "ninguno"):
            continue
        color = pattern.color
        s = max(pattern.spacing, 0.05)
        if pattern.kind == "diagonal":
            tile = (f'<path d="M 0 {s:.3f} L {s:.3f} 0" '
                    f'stroke="{color}" stroke-width="0.02" fill="none"/>')
            size = s
        elif pattern.kind == "veta":
            tile = (f'<path d="M 0 0 H {s:.3f}" stroke="{color}" '
                    f'stroke-width="0.02" fill="none"/>')
            size = s
        elif pattern.kind == "aridos":
            tile = (
                f'<path d="M 0 {s:.3f} L {s:.3f} 0" stroke="{color}" '
                f'stroke-width="0.02" fill="none"/>'
                f'<circle cx="{s * 0.8:.3f}" cy="{s * 1.6:.3f}" '
                f'r="0.02" fill="{color}"/>')
            size = s * 2.0
        elif pattern.kind == "sillares":
            tile = (
                f'<path d="M 0 {s * 0.5:.3f} H {s * 1.8:.3f} '
                f'M {s * 0.9:.3f} {s * 1.5:.3f} H {s * 2.7:.3f}" '
                f'stroke="{color}" stroke-width="0.02" fill="none"/>')
            size = s * 2.0
        elif pattern.kind == "tramas":
            tile = (f'<path d="M 0 {s:.3f} L {s:.3f} 0" '
                    f'stroke="{color}" stroke-width="0.015" fill="none"/>')
            size = s * 1.6
        else:
            continue
        parts.append(
            f'  <pattern id="trama-{escape(key)}" '
            f'patternUnits="userSpaceOnUse" width="{size:.3f}" '
            f'height="{size:.3f}">{tile}</pattern>')
    if not parts:
        return ""
    return "  <defs>\n" + "\n".join(parts) + "\n  </defs>\n"


# --------------------------------------------------------------------------
# Primitiva → SVG (con volteo Y: las vistas usan metros, Y hacia arriba)
# --------------------------------------------------------------------------

def _dash(dash: Optional[Tuple[float, float]]) -> str:
    if not dash:
        return ""
    return f' stroke-dasharray="{dash[0]:.2f} {dash[1]:.2f}"'


def _rect_svg(prim: rep.PRect, oy: float) -> str:
    y = oy - (prim.y + prim.d)
    parts = []
    common = (f'x="{prim.x:.3f}" y="{y:.3f}" width="{max(prim.w, 0):.3f}" '
              f'height="{max(prim.d, 0):.3f}"')
    if prim.hatch and prim.fill:
        parts.append(f'<rect {common} fill="{prim.fill}" '
                     f'stroke="none"/>')
        parts.append(f'<rect {common} fill="url(#trama-{escape(prim.hatch)})"'
                     f' stroke="{prim.stroke}" '
                     f'stroke-width="{prim.stroke_width * 0.02:.3f}"'
                     f'{_dash(prim.dash)}/>')
    else:
        fill = prim.fill if prim.fill else "none"
        if prim.hatch:
            fill = f"url(#trama-{escape(prim.hatch)})"
        parts.append(f'<rect {common} fill="{fill}" '
                     f'stroke="{prim.stroke}" '
                     f'stroke-width="{prim.stroke_width * 0.02:.3f}"'
                     f'{_dash(prim.dash)}/>')
    return parts[0] if len(parts) == 1 else "\n    ".join(parts)


def _line_svg(prim: rep.PLine, oy: float) -> str:
    return (f'<line x1="{prim.x1:.3f}" y1="{oy - prim.y1:.3f}" '
            f'x2="{prim.x2:.3f}" y2="{oy - prim.y2:.3f}" '
            f'stroke="{prim.color}" '
            f'stroke-width="{max(prim.width * 0.02, 0.015):.3f}" '
            f'fill="none"{_dash(prim.dash)}/>')


def _text_svg(prim: rep.PText, oy: float) -> str:
    anchor = {"middle": "middle", "start": "start",
              "end": "end"}.get(prim.anchor, "middle")
    weight = "bold" if prim.bold else "normal"
    return (f'<text x="{prim.x:.3f}" y="{oy - prim.y:.3f}" '
            f'fill="{prim.color}" font-size="{max(prim.size * 0.9, 0.12):.2f}"'
            f' font-weight="{weight}" text-anchor="{anchor}">'
            f'{escape(prim.text)}</text>')


def _arc_svg(prim: rep.PArc, oy: float) -> str:
    a1 = math.radians(prim.start_deg)
    a2 = math.radians(prim.start_deg + prim.extent_deg)
    p1 = (prim.cx + prim.r * math.cos(a1),
          prim.cy + prim.r * math.sin(a1))
    p2 = (prim.cx + prim.r * math.cos(a2),
          prim.cy + prim.r * math.sin(a2))
    large = 1 if abs(prim.extent_deg) > 180 else 0
    # Tras el volteo Y el sentido se invierte (CCW → CW): sweep 1.
    sweep = 1 if prim.extent_deg > 0 else 0
    return (f'<path d="M {p1[0]:.3f} {oy - p1[1]:.3f} '
            f'A {prim.r:.3f} {prim.r:.3f} 0 {large} {sweep} '
            f'{p2[0]:.3f} {oy - p2[1]:.3f}" stroke="{prim.color}" '
            f'stroke-width="{max(prim.width * 0.02, 0.015):.3f}" '
            f'fill="none"{_dash(prim.dash)}/>')


# --------------------------------------------------------------------------
# Vistas → Drawing
# --------------------------------------------------------------------------

def view_drawing(variant, data, view: str, aux: str = "",
                 level_index: int = 0) -> rep.Drawing:
    """Drawing de la vista pedida (aux = cardinal o eje de corte)."""
    view_l = (view or "Planta").capitalize()
    if view_l == "Elevación" or view_l == "Elevacion":
        return rep.elevation_view(variant, data, aux or "Norte")
    if view_l == "Corte":
        return rep.section_view(variant, data, aux or "Transversal")
    if view_l == "Detalles":
        return _details_drawing(data)
    return rep.plan_view(variant, data, level_index)


def _details_drawing(data) -> rep.Drawing:
    """Cuadro de detalles constructivos (2 columnas + memoria)."""
    nodes = rep.detail_library(data)
    prims: List[Any] = []
    if not nodes:
        return rep.Drawing(caption="Detalles (sin datos)", prims=[])
    cell_w, cell_h = 4.2, 4.6
    cols = 2
    for index, node in enumerate(nodes):
        col = index % cols
        row = index // cols
        ox = col * cell_w
        oy = -row * cell_h
        prims.append(rep.PRect(ox + 0.1, oy - cell_h + 0.6,
                               cell_w - 0.2, cell_h - 0.8,
                               fill="#fafafa", stroke="#b0bec5",
                               stroke_width=0.8, tag="marco"))
        prims.append(rep.PText(ox + 0.25, oy - 0.35,
                               f"{node.code} · {node.titulo}",
                               size=0.22, anchor="start", bold=True,
                               tag="titulo"))
        for prim in node.prims:
            clone = _offset_prim(prim, ox, oy)
            prims.append(clone)
        # Memoria: texto envuelto bajo el esquema.
        words = node.descripcion.split()
        line = ""
        lines: List[str] = []
        for word in words:
            if len(line) + len(word) + 1 > 56:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            lines.append(line)
        for li, text in enumerate(lines[:9]):
            prims.append(rep.PText(ox + 0.25, oy - 2.05 - li * 0.28,
                                   text, size=0.15, anchor="start",
                                   color="#455a64", tag="memoria"))
    return rep.Drawing(caption="Detalles constructivos", prims=prims)


def _offset_prim(prim: Any, ox: float, oy: float) -> Any:
    """Clona una primitiva desplazada (para el cuadro de detalles)."""
    if isinstance(prim, rep.PLine):
        return rep.PLine(prim.x1 + ox, prim.y1 + oy, prim.x2 + ox,
                         prim.y2 + oy, prim.color, prim.width, prim.dash,
                         prim.tag)
    if isinstance(prim, rep.PRect):
        return rep.PRect(prim.x + ox, prim.y + oy, prim.w, prim.d,
                         prim.fill, prim.stroke, prim.stroke_width,
                         prim.dash, prim.hatch, prim.tag)
    if isinstance(prim, rep.PText):
        return rep.PText(prim.x + ox, prim.y + oy, prim.text, prim.size,
                         prim.color, prim.anchor, prim.bold, prim.tag)
    if isinstance(prim, rep.PArc):
        return rep.PArc(prim.cx + ox, prim.cy + oy, prim.r,
                        prim.start_deg, prim.extent_deg, prim.color,
                        prim.width, prim.dash, prim.tag)
    return prim


# --------------------------------------------------------------------------
# Exportador principal
# --------------------------------------------------------------------------

def export_view_svg(variant, data, out_path: str,
                    view: str = "Planta", aux: str = "",
                    level_index: int = 0,
                    title: str = "") -> str:
    """Exporta la vista activa de la variante a SVG (metros)."""
    drawing = view_drawing(variant, data, view, aux, level_index)
    x0, y0, x1, y1 = drawing.bounds()
    pad = max((x1 - x0), (y1 - y0), 1.0) * 0.06
    x0 -= pad
    x1 += pad
    y0 -= pad
    y1 += pad
    oy = y1                       # volteo Y: y' = oy - y
    hatch_keys = [prim.hatch for prim in drawing.prims
                  if isinstance(prim, rep.PRect) and prim.hatch]

    body: List[str] = [f'  <rect x="{x0:.2f}" y="{x0:.2f}" '
                       f'width="{max(x1 - x0, 0.1):.2f}" '
                       f'height="{max(y1 - y0, 0.1):.2f}" '
                       f'fill="#ffffff" stroke="none"/>']
    for prim in drawing.prims:
        if isinstance(prim, rep.PRect):
            body.append(_rect_svg(prim, oy))
        elif isinstance(prim, rep.PLine):
            body.append(_line_svg(prim, oy))
        elif isinstance(prim, rep.PText):
            body.append(_text_svg(prim, oy))
        elif isinstance(prim, rep.PArc):
            body.append(_arc_svg(prim, oy))

    doc_title = escape(title or f"{drawing.caption} — ARQ GEN")
    view_box = f"{x0:.2f} {-y1:.2f} {max(x1 - x0, 0.1):.2f} " \
               f"{max(y1 - y0, 0.1):.2f}"
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}"
     font-family="Helvetica, Arial, sans-serif">
  <title>{doc_title}</title>
  <desc>Vista «{escape(drawing.caption)}» exportada por ARQ GEN
(v2.6.0). Unidades: metros, orientación Y invertida en pantalla.</desc>
{_pattern_defs(hatch_keys)}  {chr(10).join(body)}
</svg>
"""
    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    return out_path


# ==========================================================================
# PDF de vistas (v3.3.0, brecha #4) — vectorial 100% stdlib sobre PdfDoc
# ==========================================================================

# Página A4 apaisada (puntos PDF, 1 pt = 1/72")
_PAGE_W = 842.0
_PAGE_H = 595.0
_MARGIN = 26.0          # margen lateral/superior
_BAND = 30.0            # cajetín inferior
_PT_PER_M_FALLBACK = 20.0


def _hex_rgb(value: str, fallback: str = "#37474f"
             ) -> Tuple[int, int, int]:
    """'#rrggbb' → (r, g, b) 0..255 (tolerante)."""
    text = str(value or "").strip()
    if text.startswith("#") and len(text) >= 7:
        try:
            return (int(text[1:3], 16), int(text[3:5], 16),
                    int(text[5:7], 16))
        except ValueError:
            pass
    named = {"red": (198, 40, 40), "green": (46, 125, 50),
             "blue": (21, 101, 192), "black": (33, 33, 33),
             "gray": (96, 125, 139), "grey": (96, 125, 139),
             "white": (255, 255, 255)}
    if text.lower() in named:
        return named[text.lower()]
    base = fallback.lstrip("#")
    if len(base) == 6:
        return (int(base[0:2], 16), int(base[2:4], 16), int(base[4:6], 16))
    return (55, 71, 79)


def _clip_segment(x0: float, y0: float, x1: float, y1: float,
                  rx0: float, ry0: float, rx1: float, ry1: float):
    """Liang-Barsky: recorta el segmento al rectángulo. None si no entra."""
    dx = x1 - x0
    dy = y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rx0), (dx, rx1 - x0),
                 (-dy, y0 - ry0), (dy, ry1 - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    return (x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy)


def _arc_points(prim: rep.PArc, max_seg: float = 0.12) -> List[Tuple[float, float]]:
    """Aproximación poligonal del arco (m), determinista."""
    r = max(prim.r, 1e-6)
    sweep = abs(prim.extent_deg)
    steps = max(8, min(int(math.radians(sweep) * r / max_seg) + 2, 240))
    pts: List[Tuple[float, float]] = []
    for index in range(steps + 1):
        ang = math.radians(prim.start_deg + prim.extent_deg * index / steps)
        pts.append((prim.cx + r * math.cos(ang),
                    prim.cy + r * math.sin(ang)))
    return pts


def _hatch_lines_pdf(pdf, x0: float, y0: float, w: float, h: float,
                     kind: str, spacing: float, color, s: float) -> None:
    """Trama del rectángulo (coordenadas de página en pt ya aplicadas).

    ``s`` = metros → pt. Recorta cada trazo al rectángulo (Liang-Barsky).
    """
    spacing = max(spacing, 0.05)
    step = spacing * s
    gray = (color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
    if kind in ("diagonal", "aridos", "tramas"):
        c = -h
        while c <= w:
            seg = _clip_segment(x0 + c, y0, x0 + c + h, y0 + h,
                                x0, y0, x0 + w, y0 + h)
            if seg:
                pdf.line(seg[0], seg[1], seg[2], seg[3],
                         width=0.35, rgb=gray)
            c += step
        if kind == "aridos":  # áridos: la diagonal + puntos gruesos
            yy = y0 + step * 0.5
            row = 0
            while yy < y0 + h:
                xx = x0 + (step if row % 2 else step * 0.5)
                while xx < x0 + w:
                    pdf.rect(xx, yy, 0.7, 0.7, fill_gray=None,
                             fill_rgb=gray, stroke_gray=None)
                    xx += step
                yy += step
                row += 1
    elif kind == "veta":
        yy = y0
        while yy <= y0 + h:
            pdf.line(x0, yy, x0 + w, yy, width=0.35, rgb=gray)
            yy += step
    elif kind == "sillares":
        yy = y0
        while yy <= y0 + h:
            pdf.line(x0, yy, x0 + w, yy, width=0.35, rgb=gray)
            yy += step * 1.5
        xx = x0
        while xx <= x0 + w:
            pdf.line(xx, y0, xx, y0 + h, width=0.3, rgb=gray)
            xx += step * 2.7
    # "solido"/"ninguno": nada extra (el relleno ya cubre)


def export_view_pdf(variant, data, out_path: str, view: str = "Planta",
                    aux: str = "", level_index: int = 0, title: str = "",
                    page_size: Tuple[float, float] = (_PAGE_W, _PAGE_H)
                    ) -> str:
    """Exporta la vista activa a PDF vectorial A4 apaisado (100% stdlib).

    Mismo Drawing que el lienzo y el SVG → los tres canales dibujan lo
    mismo. Determinista, con cajetín (título, vista y escala aproximada).
    """
    from exporters.pdf_exporter import PdfDoc, text_width

    drawing = view_drawing(variant, data, view, aux, level_index)
    x0, y0, x1, y1 = drawing.bounds()
    pad = max((x1 - x0), (y1 - y0), 1.0) * 0.06
    x0 -= pad
    x1 += pad
    y0 -= pad
    y1 += pad
    w_m = max(x1 - x0, 0.1)
    h_m = max(y1 - y0, 0.1)

    page_w, page_h = page_size
    usable_w = page_w - 2 * _MARGIN
    usable_h = page_h - _MARGIN - _BAND - 8.0
    s = min(usable_w / w_m, usable_h / h_m)
    s = max(s, 0.5)                      # nunca colapsar el dibujo
    ox = _MARGIN + (usable_w - w_m * s) / 2.0
    oy = _BAND + 6.0 + (usable_h - h_m * s) / 2.0

    pdf = PdfDoc(title=title or f"{drawing.caption} — ARQ GEN")
    pdf.rect(0, 0, page_w, page_h, fill_gray=1.0, stroke_gray=None)

    def px(xm: float) -> float:
        return ox + (xm - x0) * s

    def py(ym: float) -> float:
        return oy + (ym - y0) * s

    for prim in drawing.prims:
        if isinstance(prim, rep.PRect):
            rx, ry = px(prim.x), py(prim.y + prim.d)
            rw, rh = max(prim.w * s, 0.05), max(prim.d * s, 0.05)
            fill_rgb = None
            if prim.fill:
                fill_rgb = tuple(v / 255.0 for v in _hex_rgb(prim.fill))
            stroke_rgb = tuple(v / 255.0 for v in _hex_rgb(prim.stroke))
            pdf.rect(rx, ry, rw, rh, fill_rgb=fill_rgb,
                     stroke_rgb=stroke_rgb,
                     stroke_width=max(0.3, prim.stroke_width * 0.45))
            if prim.hatch:
                pattern = rep.HATCH_PATTERNS.get(prim.hatch)
                if pattern is not None and pattern.kind not in (
                        "solido", "ninguno"):
                    hatch_color = _hex_rgb(pattern.color)
                    _hatch_lines_pdf(pdf, rx, ry, rw, rh, pattern.kind,
                                     pattern.spacing, hatch_color, s)
        elif isinstance(prim, rep.PLine):
            rgb = tuple(v / 255.0 for v in _hex_rgb(prim.color))
            dash = None
            if prim.dash:
                dash = (max(prim.dash[0] * s, 0.8),
                        max(prim.dash[1] * s, 0.8))
            pdf.line(px(prim.x1), py(prim.y1), px(prim.x2), py(prim.y2),
                     width=max(0.3, prim.width * 0.45), rgb=rgb, dash=dash)
        elif isinstance(prim, rep.PArc):
            rgb = tuple(v / 255.0 for v in _hex_rgb(prim.color))
            pts = _arc_points(prim)
            for index in range(len(pts) - 1):
                pdf.line(px(pts[index][0]), py(pts[index][1]),
                         px(pts[index + 1][0]), py(pts[index + 1][1]),
                         width=max(0.3, prim.width * 0.45), rgb=rgb)
        elif isinstance(prim, rep.PText):
            rgb = tuple(v / 255.0 for v in _hex_rgb(prim.color))
            size_pt = max(4.5, prim.size * s * 0.85)
            anchor = prim.anchor
            if anchor == "middle":
                tx = px(prim.x) - text_width(prim.text, size_pt,
                                             prim.bold) / 2.0
            elif anchor == "end":
                tx = px(prim.x) - text_width(prim.text, size_pt, prim.bold)
            else:
                tx = px(prim.x)
            pdf.text(tx, py(prim.y), size_pt, prim.text, bold=prim.bold,
                     rgb=rgb)

    # cajetín
    band_y = _BAND
    pdf.line(_MARGIN, band_y + _BAND - 6.0, page_w - _MARGIN,
             band_y + _BAND - 6.0, width=0.8, rgb=(0.24, 0.31, 0.36))
    label = f"{drawing.caption}" + (f" · {aux}" if aux else "")
    pdf.text(_MARGIN, band_y + 2.0, 10.5, label, bold=True,
             rgb=(0.12, 0.16, 0.24))
    scale_x = 72.0 / (s * 0.0254)        # 1 m de dibujo = s pt de papel
    nice = max(1, int(round(scale_x)))
    right = (f"ARQ GEN · {title or 'Vista'} · ESC 1:{nice} aprox")
    tw = text_width(right, 7.5)
    pdf.text(page_w - _MARGIN - tw, band_y + 2.0, 7.5, right,
             rgb=(0.36, 0.44, 0.50))

    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    pdf.save(out_path)
    return out_path


# ==========================================================================
# PNG de vistas (v3.3.0, brecha #4) — raster 100% stdlib sobre Canvas
# ==========================================================================

def export_view_png(variant, data, out_path: str, view: str = "Planta",
                    aux: str = "", level_index: int = 0, title: str = "",
                    px_per_m: int = 48, max_px: int = 5200) -> str:
    """Exporta la vista activa a PNG raster (sin dependencias externas).

    ``px_per_m`` controla la resolución (48 px/m ≈ 122 dpi a escala 1:1
    del Drawing). Determinista: mismas entradas → mismos bytes.
    """
    from exporters.png_exporter import Canvas

    drawing = view_drawing(variant, data, view, aux, level_index)
    x0, y0, x1, y1 = drawing.bounds()
    pad = max((x1 - x0), (y1 - y0), 1.0) * 0.06
    x0 -= pad
    x1 += pad
    y0 -= pad
    y1 += pad
    w_m = max(x1 - x0, 0.1)
    h_m = max(y1 - y0, 0.1)

    px = max(8, int(px_per_m))
    scale = max(1.0, max(w_m, h_m) * px / max(max_px, 400.0))
    px = int(px / scale)
    band_px = 34 * (px // 12 or 1)       # franja inferior de título
    width = max(160, int(w_m * px) + 2 * 14)
    height = max(120, int(h_m * px) + 2 * 14 + band_px)
    canvas = Canvas(width, height, background=(255, 255, 255))

    ox = 14.0
    oy_top = height - 14.0 - band_px     # y del tope del dibujo (flip Y)

    def X(xm: float) -> float:
        return ox + (xm - x0) * px

    def Y(ym: float) -> float:
        return oy_top - (ym - y1) * px

    def _thick(width_units: float) -> int:
        return max(1, int(round(width_units * 0.02 * px)))

    for prim in drawing.prims:
        if isinstance(prim, rep.PRect):
            rx0, ry0 = X(prim.x), Y(prim.y + prim.d)
            rx1, ry1 = X(prim.x + prim.w), Y(prim.y)
            rw, rh = rx1 - rx0, ry1 - ry0
            if prim.fill:
                canvas.polygon_fill(
                    [(rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1)],
                    _hex_rgb(prim.fill, "#ffffff"))
            if prim.hatch:
                pattern = rep.HATCH_PATTERNS.get(prim.hatch)
                if pattern is not None and pattern.kind not in (
                        "solido", "ninguno"):
                    hc = _hex_rgb(pattern.color)
                    step = max(pattern.spacing, 0.05) * px
                    if pattern.kind in ("diagonal", "aridos", "tramas"):
                        c = -rh
                        while c <= rw:
                            seg = _clip_segment(rx0 + c, ry0, rx0 + c + rh,
                                                ry0 + rh, rx0, ry0,
                                                rx0 + rw, ry0 + rh)
                            if seg:
                                canvas.line(seg[0], seg[1], seg[2], seg[3],
                                            hc, max(1, px // 48))
                            c += step
                        if pattern.kind == "aridos":
                            yy = ry0 + step * 0.5
                            row = 0
                            while yy < ry0 + rh:
                                xx = rx0 + (step if row % 2 else step * 0.5)
                                while xx < rx0 + rw:
                                    canvas.rect_fill(int(xx), int(yy),
                                                     max(1, px // 48),
                                                     max(1, px // 48), hc)
                                    xx += step
                                yy += step
                                row += 1
                    elif pattern.kind == "veta":
                        yy = ry0
                        while yy <= ry0 + rh:
                            canvas.hline(int(rx0), int(rx0 + rw), int(yy),
                                         hc)
                            yy += step
                    elif pattern.kind == "sillares":
                        yy = ry0
                        while yy <= ry0 + rh:
                            canvas.hline(int(rx0), int(rx0 + rw), int(yy),
                                         hc)
                            yy += step * 1.5
                        xx = rx0
                        while xx <= rx0 + rw:
                            canvas.line(xx, ry0, xx, ry0 + rh, hc,
                                        max(1, px // 48))
                            xx += step * 2.7
            sc = _hex_rgb(prim.stroke)
            t = _thick(prim.stroke_width)
            canvas.line(rx0, ry0, rx1, ry0, sc, t)
            canvas.line(rx1, ry0, rx1, ry1, sc, t)
            canvas.line(rx1, ry1, rx0, ry1, sc, t)
            canvas.line(rx0, ry1, rx0, ry0, sc, t)
        elif isinstance(prim, rep.PLine):
            color = _hex_rgb(prim.color)
            t = _thick(prim.width)
            if prim.dash:
                length = math.hypot(prim.x2 - prim.x1, prim.y2 - prim.y1)
                if length < 1e-9:
                    continue
                on, off = prim.dash
                dist = 0.0
                while dist < length:
                    a = dist / length
                    b = min((dist + on) / length, 1.0)
                    canvas.line(X(prim.x1 + a * (prim.x2 - prim.x1)),
                                Y(prim.y1 + a * (prim.y2 - prim.y1)),
                                X(prim.x1 + b * (prim.x2 - prim.x1)),
                                Y(prim.y1 + b * (prim.y2 - prim.y1)),
                                color, t)
                    dist += on + off
            else:
                canvas.line(X(prim.x1), Y(prim.y1), X(prim.x2), Y(prim.y2),
                            color, t)
        elif isinstance(prim, rep.PArc):
            pts = _arc_points(prim)
            canvas.polyline([(X(a), Y(b)) for a, b in pts],
                            _hex_rgb(prim.color), _thick(prim.width))
        elif isinstance(prim, rep.PText):
            f_scale = max(1, int(round(prim.size * px / 7.0)))
            w_used = canvas.text_width(prim.text, f_scale)
            tx = X(prim.x)
            if prim.anchor == "middle":
                tx -= w_used / 2.0
            elif prim.anchor == "end":
                tx -= w_used
            canvas.text(int(tx), int(Y(prim.y) - 3.2 * f_scale),
                        prim.text, scale=f_scale, color=_hex_rgb(
                            prim.color, "#263238"))

    # franja de título
    band_line_y = height - band_px
    canvas.hline(14, width - 14, band_line_y - 6, (62, 79, 89))
    caption = drawing.caption + (f" · {aux}" if aux else "")
    canvas.text(14, band_line_y + 4, caption,
                scale=max(1, px // 24), color=(33, 43, 54))
    tail = f"ARQ GEN · {title or 'VISTA'}"
    canvas.text(width - 14 - canvas.text_width(tail, max(1, px // 48)),
                band_line_y + 4, tail, scale=max(1, px // 48),
                color=(96, 125, 139))

    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    canvas.save_png(out_path)
    return out_path


def export_view(variant, data, out_path: str, view: str = "Planta",
                aux: str = "", level_index: int = 0, title: str = "") -> str:
    """Despacha por extensión: .svg → SVG, .pdf → PDF, .png → PNG."""
    lower = out_path.lower()
    if lower.endswith(".pdf"):
        return export_view_pdf(variant, data, out_path, view, aux,
                               level_index, title)
    if lower.endswith(".png"):
        return export_view_png(variant, data, out_path, view, aux,
                               level_index, title)
    return export_view_svg(variant, data, out_path, view, aux,
                           level_index, title)


__all__ = ["VIEWS", "view_drawing", "export_view_svg", "export_view_pdf",
           "export_view_png", "export_view"]
