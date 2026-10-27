"""Exportador SVG de DETALLES CONSTRUCTIVOS (v3.5.0).

Dibuja el corte de un detalle de la biblioteca (domain.detalles) como
un esquema acotado: bandas de capas apiladas según su espesor, cada
capa numerada con su línea de referencia, cota del espesor total,
leyenda tabulada con materiales, notas de obra y cajetín con la
edición regional activa.

100% stdlib y determinista: el mismo detalle produce siempre el mismo
fichero byte a byte (la suite lo vigila). Como los planos SVG del
proyecto, se escribe en UTF-8 con la fuente genérica Helvetica.
"""

from __future__ import annotations

import os
import textwrap
from typing import List, Optional
from xml.sax.saxutils import escape

from core.errors import ExportError

#: Paleta (misma familia que los planos SVG del proyecto).
INK = "#37474f"
FILL_A = "#eceff1"
FILL_B = "#dde4e7"
ACCENT = "#b45309"
TEXT = "#b71c1c"
DIM = "#546e7a"

#: Geometría del esquema (píxeles SVG).
PAGE_W = 840
BAND_X0 = 96          # borde izquierdo de las bandas
BAND_X1 = 400         # borde derecho de las bandas
BAND_W = BAND_X1 - BAND_X0
TOP_Y = 118           # y del borde superior de la primera banda
MAX_STACK_H = 300.0   # altura disponible del apilado
MIN_BAND_H = 8.0      # banda mínima dibujable
MAX_BAND_H = 62.0     # banda máxima dibujable
LEGEND_Y0 = 470       # inicio de la leyenda tabulada
ROW_H = 20

WRAP = 92             # ancho de envoltura de notas (caracteres)


def export_detalle_svg(detalle, out_path: str, title: str = "",
                       region_label: str = "") -> str:
    """Detalle constructivo → SVG acotado y determinista.

    ``detalle`` es un ``domain.detalles.DetalleConstructivo``. Sin
    capas el corte queda vacío pero el fichero sigue siendo válido
    (degradación amable, como el resto de los exportadores).
    """
    if detalle is None:
        raise ExportError(
            message="No hay detalle constructivo que exportar",
            code="ARQ-EXP-070",
            suggested_action="Elige un detalle de la biblioteca antes "
                             "de exportar.")

    capas = list(detalle.capas)
    total_mm = detalle.espesor_total_mm
    # altura proporcional con topes: detalles gruesos y finos caben
    scale = (MAX_STACK_H / total_mm) if total_mm > 0 else 1.0
    scale = min(scale, MAX_BAND_H / max(
        (capa.espesor_mm for capa in capas), default=1.0))
    band_heights = [
        min(MAX_BAND_H, max(MIN_BAND_H, capa.espesor_mm * scale))
        for capa in capas]
    stack_h = sum(band_heights)
    # la leyenda y las notas crecen con el contenido
    notas: List[str] = []
    for nota in detalle.notas:
        notas.extend(textwrap.wrap(f"· {nota}", WRAP) or ["·"])
    norma_lines = textwrap.wrap(f"Norma: {detalle.norma}", WRAP) \
        if detalle.norma else []
    resumen_lines = textwrap.wrap(detalle.resumen, WRAP) \
        if detalle.resumen else []
    footer_y = LEGEND_Y0 + ROW_H * (len(capas) + 1) + 26 \
        + 16 * (len(notas) + len(norma_lines) + len(resumen_lines)) \
        + (46 if detalle.norma else 30)
    page_h = max(560, footer_y + 44)

    parts: List[str] = []
    # -- cabecera ---------------------------------------------------------
    heading = escape(title or detalle.nombre)
    parts.append(f'<text class="titulo" x="{PAGE_W / 2}" y="34" '
                 f'text-anchor="middle">{heading}</text>')
    sub = escape(f"{detalle.etiqueta_corta()}"
                 f"{' — ' + detalle.sentido if detalle.sentido else ''}")
    parts.append(f'<text class="sub" x="{PAGE_W / 2}" y="54" '
                 f'text-anchor="middle">{sub}</text>')
    for index, line in enumerate(resumen_lines[:3]):
        parts.append(f'<text class="resumen" x="{PAGE_W / 2}" '
                     f'y="{72 + index * 14}" text-anchor="middle">'
                     f'{escape(line)}</text>')
    # -- corte por capas ----------------------------------------------------
    y = TOP_Y
    for index, (capa, height) in enumerate(zip(capas, band_heights), 1):
        fill = FILL_A if index % 2 else FILL_B
        cy = y + height / 2.0
        parts.append(
            f'<rect x="{BAND_X0}" y="{y:.1f}" width="{BAND_W}" '
            f'height="{height:.1f}" fill="{fill}" stroke="{INK}" '
            f'stroke-width="1.2"><title>{escape(capa.etiqueta())}'
            f'</title></rect>')
        parts.append(
            f'<circle cx="{BAND_X0 + 26}" cy="{cy:.1f}" r="11" '
            f'fill="{ACCENT}"><title>Capa {index}</title></circle>')
        parts.append(
            f'<text class="numero" x="{BAND_X0 + 26}" y="{cy + 3.5:.1f}" '
            f'text-anchor="middle">{index}</text>')
        parts.append(
            f'<line x1="{BAND_X0 + 40}" y1="{cy:.1f}" '
            f'x2="{BAND_X1 + 26}" y2="{cy:.1f}" stroke="{DIM}" '
            f'stroke-width="0.8"/>')
        parts.append(
            f'<text class="capa" x="{BAND_X1 + 32}" y="{cy + 4:.1f}">'
            f'{escape(capa.etiqueta())}</text>')
        y += height
    # -- cota del espesor total ----------------------------------------------
    if capas:
        mid_y = TOP_Y + stack_h / 2.0
        parts.append(f'<line x1="60" y1="{TOP_Y}" x2="60" '
                     f'y2="{TOP_Y + stack_h:.1f}" stroke="{INK}" '
                     f'stroke-width="1"/>')
        for tip_y in (TOP_Y, TOP_Y + stack_h):
            parts.append(f'<line x1="55" y1="{tip_y:.1f}" x2="65" '
                         f'y2="{tip_y:.1f}" stroke="{INK}" '
                         f'stroke-width="1"/>')
        espesor = (f"{total_mm:g}" if float(total_mm).is_integer()
                   else f"{total_mm:.1f}")
        parts.append(f'<text class="cota" x="52" y="{mid_y + 4:.1f}" '
                     f'text-anchor="end" '
                     f'transform="rotate(-90 52 {mid_y + 4:.1f})">'
                     f'ESPESOR TOTAL {espesor} mm</text>')
    # -- leyenda -------------------------------------------------------------
    parts.append(f'<text class="leyenda" x="{BAND_X0}" y="{LEGEND_Y0 - 10}">'
                 f'LEYENDA (materiales)</text>')
    cols = (BAND_X0 + 4, BAND_X0 + 40, BAND_X0 + 210, BAND_X0 + 280)
    parts.append(f'<line x1="{BAND_X0}" y1="{LEGEND_Y0}" '
                 f'x2="{PAGE_W - 40}" y2="{LEGEND_Y0}" stroke="{INK}" '
                 f'stroke-width="1"/>')
    header_y = LEGEND_Y0 + 14
    parts.append(f'<text class="thead" x="{cols[0]}" y="{header_y}">Nº'
                 f'</text>')
    parts.append(f'<text class="thead" x="{cols[1]}" y="{header_y}">Capa'
                 f'</text>')
    parts.append(f'<text class="thead" x="{cols[2]}" y="{header_y}">'
                 f'Espesor</text>')
    parts.append(f'<text class="thead" x="{cols[3]}" y="{header_y}">'
                 f'Material</text>')
    parts.append(f'<line x1="{BAND_X0}" y1="{header_y + 6}" '
                 f'x2="{PAGE_W - 40}" y2="{header_y + 6}" '
                 f'stroke="{INK}" stroke-width="0.6"/>')
    row_y = header_y + ROW_H
    for index, (capa, height) in enumerate(zip(capas, band_heights), 1):
        espesor = (f"{capa.espesor_mm:g} mm"
                   if float(capa.espesor_mm).is_integer()
                   else f"{capa.espesor_mm:.1f} mm")
        parts.append(f'<text class="tcell" x="{cols[0]}" '
                     f'y="{row_y:.1f}">{index}</text>')
        parts.append(f'<text class="tcell" x="{cols[1]}" '
                     f'y="{row_y:.1f}">{escape(capa.nombre)}</text>')
        parts.append(f'<text class="tcell" x="{cols[2]}" '
                     f'y="{row_y:.1f}">{espesor}</text>')
        parts.append(f'<text class="tcell" x="{cols[3]}" '
                     f'y="{row_y:.1f}">{escape(capa.material)}</text>')
        row_y += ROW_H
    parts.append(f'<line x1="{BAND_X0}" y1="{row_y - ROW_H + 14}" '
                 f'x2="{PAGE_W - 40}" y2="{row_y - ROW_H + 14}" '
                 f'stroke="{INK}" stroke-width="0.6"/>')
    # -- notas y norma ----------------------------------------------------------
    body_y = LEGEND_Y0 + ROW_H * (len(capas) + 1) + 26
    for line in resumen_lines[3:]:
        parts.append(f'<text class="nota" x="{BAND_X0}" '
                     f'y="{body_y:.1f}">{escape(line)}</text>')
        body_y += 16
    for line in norma_lines:
        parts.append(f'<text class="nota" x="{BAND_X0}" '
                     f'y="{body_y:.1f}">{escape(line)}</text>')
        body_y += 16
    for line in notas:
        parts.append(f'<text class="nota" x="{BAND_X0}" '
                     f'y="{body_y:.1f}">{escape(line)}</text>')
        body_y += 16
    # -- cajetín -----------------------------------------------------------------
    cajetin_y = page_h - 30
    parts.append(f'<line x1="40" y1="{cajetin_y - 14}" x2="{PAGE_W - 40}" '
                 f'y2="{cajetin_y - 14}" stroke="{INK}" '
                 f'stroke-width="1"/>')
    fuente = escape(str(detalle.fuente.get("titulo", ""))) \
        if detalle.fuente else ""
    cajetin = "ARQ GEN · Biblioteca de detalles constructivos"
    if region_label:
        cajetin += f" · {escape(region_label)}"
    if fuente:
        cajetin += f" · {fuente}"
    parts.append(f'<text class="cajetin" x="40" y="{cajetin_y}">'
                 f'{cajetin}</text>')
    parts.append(f'<text class="cajetin" x="{PAGE_W - 40}" '
                 f'y="{cajetin_y}" text-anchor="end">'
                 f'{escape(detalle.id)}</text>')

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}" height="{page_h}"
     viewBox="0 0 {PAGE_W} {page_h}"
     font-family="Helvetica, Arial, sans-serif">
  <title>{escape(title or detalle.nombre)} — detalle constructivo ARQ GEN</title>
  <desc>Detalle {escape(detalle.id)} ({escape(detalle.categoria)})
exportado por ARQ GEN v3.5.0.</desc>
  <style>
    .titulo {{ fill: {INK}; font-size: 20px; font-weight: bold; }}
    .sub {{ fill: {DIM}; font-size: 12px; }}
    .resumen {{ fill: {DIM}; font-size: 11px; }}
    .numero {{ fill: #ffffff; font-size: 12px; font-weight: bold; }}
    .capa {{ fill: {INK}; font-size: 12px; }}
    .cota {{ fill: {INK}; font-size: 11px; font-weight: bold;
             letter-spacing: 1px; }}
    .leyenda {{ fill: {INK}; font-size: 11px; font-weight: bold;
                letter-spacing: 1px; }}
    .thead {{ fill: {INK}; font-size: 11px; font-weight: bold; }}
    .tcell {{ fill: {INK}; font-size: 11px; }}
    .nota {{ fill: {DIM}; font-size: 11px; }}
    .cajetin {{ fill: {DIM}; font-size: 10px; }}
  </style>
  <rect x="0" y="0" width="{PAGE_W}" height="{page_h}" fill="#ffffff"/>
  {chr(10).join('  ' + line for line in parts)}
</svg>
"""
    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    return out_path


__all__ = ["export_detalle_svg"]
