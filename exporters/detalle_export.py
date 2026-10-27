"""Exportador PDF/PNG de DETALLES CONSTRUCTIVOS (v3.6.0).

Hermano menor de ``detalle_svg``: dibuja la MISMA ficha del corte
(bandas apiladas por espesor, números de capa con línea de referencia,
cota del espesor total, leyenda de materiales, notas de obra y cajetín
con la edición regional) en los dos formatos que faltaban:

* ``export_detalle_pdf`` — vectorial A4 vertical sobre ``PdfDoc``
  (curvas Bézier para los números de capa, texto rotado para la cota).
* ``export_detalle_png`` — raster sobre ``Canvas`` (fuente bitmap 5x7
  sin acentos, como el resto de los PNG del sistema) a escala 2x.
* ``export_detalle``    — despacha por extensión (.pdf/.png/.svg*).

100% stdlib y determinista: el mismo detalle produce siempre el mismo
fichero byte a byte (la suite lo vigila). Los cuatro caracteres que
Helvetica-WinAnsi no tiene (λ ≈ ≤ ≥) se transliteran al vuelo.
"""

from __future__ import annotations

import os
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from core.errors import ExportError

#: Transliteraciones para WinAnsi (Helvetica) — cp1252 no los trae.
_WINANSI_FALTANTES: Dict[str, str] = {
    "λ": "lambda ", "≈": "~", "≤": "<=", "≥": ">=",
}

# Paleta (idéntica a detalle_svg, en RGB 0-1 para PDF y 0-255 para PNG)
INK_HEX = "#37474f"
FILL_A_HEX = "#eceff1"
FILL_B_HEX = "#dde4e7"
ACCENT_HEX = "#b45309"
TEXT_HEX = "#b71c1c"
DIM_HEX = "#546e7a"

WRAP = 92              # envoltura de notas (igual que el SVG)


def _hex_rgb(value: str) -> Tuple[int, int, int]:
    """«#37474f» → (55, 71, 79); inválida → gris tinta."""
    try:
        value = str(value).strip().lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        return (int(value[0:2], 16), int(value[2:4], 16),
                int(value[4:6], 16))
    except Exception:  # noqa: BLE001 — color roto, queda el tinta
        return (55, 71, 79)


def _limpiar(texto: str) -> str:
    """Translitera los caracteres que WinAnsi no puede codificar."""
    for origen, destino in _WINANSI_FALTANTES.items():
        texto = texto.replace(origen, destino)
    return texto


def _wrap(texto: str, ancho: int = WRAP) -> List[str]:
    return textwrap.wrap(texto, ancho) or [""]


def _require(detalle: Any) -> Any:
    if detalle is None:
        raise ExportError(
            message="No hay detalle constructivo que exportar",
            code="ARQ-EXP-071",
            suggested_action="Elige un detalle de la biblioteca antes "
                             "de exportar.")
    return detalle


def _layout(detalle: Any) -> Dict[str, Any]:
    """Modelo de contenido compartido por los tres canales.

    Misma matemática que ``detalle_svg``: alturas de banda
    proporcionales con topes, textos envueltos y alto de página que
    crece con la leyenda y las notas.
    """
    capas = list(detalle.capas)
    total_mm = detalle.espesor_total_mm
    scale = (300.0 / total_mm) if total_mm > 0 else 1.0
    scale = min(scale, 62.0 / max(
        (capa.espesor_mm for capa in capas), default=1.0))
    band_heights = [
        min(62.0, max(8.0, capa.espesor_mm * scale)) for capa in capas]
    stack_h = sum(band_heights)
    notas: List[str] = []
    for nota in detalle.notas:
        notas.extend(textwrap.wrap(f"· {nota}", WRAP) or ["·"])
    norma_lines = _wrap(f"Norma: {detalle.norma}") if detalle.norma else []
    resumen_lines = _wrap(detalle.resumen) if detalle.resumen else []
    footer_y = 470 + 20 * (len(capas) + 1) + 26 \
        + 16 * (len(notas) + len(norma_lines) + len(resumen_lines)) \
        + (46 if detalle.norma else 30)
    page_h = max(560, footer_y + 44)
    return {
        "capas": capas,
        "band_heights": band_heights,
        "stack_h": stack_h,
        "notas": notas,
        "norma_lines": norma_lines,
        "resumen_lines": resumen_lines,
        "page_h": page_h,
    }


# ==========================================================================
# PDF vectorial (A4 vertical) sobre PdfDoc
# ==========================================================================

def export_detalle_pdf(detalle, out_path: str, title: str = "",
                       region_label: str = "") -> str:
    """Detalle constructivo → PDF vectorial A4 vertical determinista."""
    from exporters.pdf_exporter import PAGE_H, PAGE_W, PdfDoc, text_width

    _require(detalle)
    lay = _layout(detalle)
    capas: List[Any] = lay["capas"]
    heights: List[float] = lay["band_heights"]
    stack_h: float = lay["stack_h"]

    pdf = PdfDoc(title=title or detalle.nombre)
    pdf.rect(0, 0, PAGE_W, PAGE_H, fill_gray=1.0, stroke_gray=None)

    # -- cabecera ---------------------------------------------------------
    pdf.text(PAGE_W / 2.0, PAGE_H - 40, 16,
             _limpiar(title or detalle.nombre), bold=True,
             rgb=(0.216, 0.278, 0.310))
    sub = (f"{detalle.etiqueta_corta()}"
           f"{' — ' + detalle.sentido if detalle.sentido else ''}")
    pdf.text(PAGE_W / 2.0, PAGE_H - 57, 9, _limpiar(sub),
             rgb=(0.329, 0.431, 0.478))
    y_res = PAGE_H - 72
    for line in lay["resumen_lines"][:3]:
        pdf.text(PAGE_W / 2.0, y_res, 8.5, _limpiar(line),
                 rgb=(0.329, 0.431, 0.478))
        y_res -= 11.5

    # -- corte por capas ---------------------------------------------------
    top_y = PAGE_H - 124.0          # borde superior del apilado
    x0, x1 = 76.0, 330.0
    ink = (0.216, 0.278, 0.310)
    dim_rgb = (0.329, 0.431, 0.478)
    accent = (0.706, 0.325, 0.035)

    y = top_y
    for index, (capa, height) in enumerate(zip(capas, heights), 1):
        fill = ((0.925, 0.937, 0.945) if index % 2
                else (0.867, 0.894, 0.906))
        pdf.rect(x0, y - height, x1 - x0, height, fill_rgb=fill,
                 stroke_rgb=ink, stroke_width=1.0)
        cy = y - height / 2.0
        pdf.circle(x0 + 22, cy, 9.5, fill_rgb=accent)
        numero = str(index)
        pdf.text(x0 + 22 - text_width(numero, 9.5, True) / 2.0,
                 cy - 3.3, 9.5, numero, bold=True,
                 rgb=(1.0, 1.0, 1.0))
        pdf.line(x0 + 36, cy, x1 + 20, cy, width=0.7, rgb=dim_rgb)
        pdf.text(x1 + 26, cy - 3.0, 9, _limpiar(capa.etiqueta()),
                 rgb=ink)
        y -= height

    # -- cota del espesor total (línea + texto rotado) ----------------------
    if capas:
        cota_x = x0 - 20.0
        pdf.line(cota_x, top_y, cota_x, top_y - stack_h, width=0.9,
                 rgb=ink)
        for tip_y in (top_y, top_y - stack_h):
            pdf.line(cota_x - 5, tip_y, cota_x + 5, tip_y, width=0.9,
                     rgb=ink)
        espesor = (f"{detalle.espesor_total_mm:g}"
                   if float(detalle.espesor_total_mm).is_integer()
                   else f"{detalle.espesor_total_mm:.1f}")
        label = f"ESPESOR TOTAL {espesor} mm"
        mid_y = top_y - stack_h / 2.0
        pdf.text(cota_x - 10, mid_y - text_width(label, 8, True) / 2.0,
                 8, label, bold=True, angle=90, rgb=ink)

    # -- leyenda -------------------------------------------------------------
    legend_label_y = top_y - stack_h - 34.0
    pdf.text(x0, legend_label_y, 9, "LEYENDA (materiales)", bold=True,
             rgb=ink)
    legend_y = legend_label_y - 10.0
    pdf.line(x0, legend_y, PAGE_W - 40, legend_y, width=1.0, rgb=ink)
    header_y = legend_y - 13.0
    cols = (x0 + 2, x0 + 26, x0 + 160, x0 + 218)
    for text in ("Nº", "Capa", "Espesor", "Material"):
        pdf.text(cols[("Nº", "Capa", "Espesor",
                       "Material").index(text)], header_y, 8.5, text,
                 bold=True, rgb=ink)
    pdf.line(x0, header_y - 5, PAGE_W - 40, header_y - 5, width=0.5,
             rgb=ink)
    row_y = header_y - 16.0
    for index, (capa, _height) in enumerate(zip(capas, heights), 1):
        espesor = (f"{capa.espesor_mm:g} mm"
                   if float(capa.espesor_mm).is_integer()
                   else f"{capa.espesor_mm:.1f} mm")
        pdf.text(cols[0], row_y, 8.5, str(index), rgb=ink)
        pdf.text(cols[1], row_y, 8.5, _limpiar(capa.nombre), rgb=ink)
        pdf.text(cols[2], row_y, 8.5, espesor, rgb=ink)
        pdf.text(cols[3], row_y, 8.5, _limpiar(capa.material), rgb=ink)
        row_y -= 13.0
    if capas:
        pdf.line(x0, row_y + 6, PAGE_W - 40, row_y + 6, width=0.5,
                 rgb=ink)

    # -- notas, norma y resumen que no cupieron arriba ------------------------
    body_y = row_y - 20.0
    for line in lay["resumen_lines"][3:] + lay["norma_lines"] \
            + lay["notas"]:
        pdf.text(x0, body_y, 8, _limpiar(line), rgb=dim_rgb)
        body_y -= 11.5

    # -- cajetín ---------------------------------------------------------------
    pdf.line(40, 48, PAGE_W - 40, 48, width=1.0, rgb=ink)
    fuente = _limpiar(str(detalle.fuente.get("titulo", ""))) \
        if detalle.fuente else ""
    cajetin = "ARQ GEN · Biblioteca de detalles constructivos"
    if region_label:
        cajetin += f" · {_limpiar(region_label)}"
    if fuente:
        cajetin += f" · {fuente}"
    pdf.text(40, 36, 7.5, cajetin, rgb=dim_rgb)
    did = detalle.id
    pdf.text(PAGE_W - 40 - text_width(did, 7.5), 36, 7.5, did,
             rgb=dim_rgb)

    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    return pdf.save(out_path)


# ==========================================================================
# PNG raster (escala 2x sobre el espacio del SVG) sobre Canvas
# ==========================================================================

_S = 2            # factor de escala del raster
PAGE_W_PX = 840   # mismo lienzo que detalle_svg


def _draw_circle_png(canvas: Any, cx: float, cy: float, r: float,
                     fill: Tuple[int, int, int]) -> None:
    """Círculo relleno (polígono de 28 lados) + contorno por arco."""
    import math
    puntos = [(cx + r * math.cos(2 * math.pi * i / 28.0),
               cy + r * math.sin(2 * math.pi * i / 28.0))
              for i in range(28)]
    canvas.polygon_fill([(x * _S, y * _S) for x, y in puntos], fill)
    canvas.arc(cx * _S, cy * _S, r * _S, 0, 360, fill, max(1, _S))


def export_detalle_png(detalle, out_path: str, title: str = "",
                       region_label: str = "") -> str:
    """Detalle constructivo → PNG raster determinista (escala 2x).

    Misma composición que el SVG; el texto usa la fuente bitmap 5x7
    (mayúsculas sin acentos, como en todos los PNG del sistema).
    """
    from exporters.png_exporter import Canvas

    _require(detalle)
    lay = _layout(detalle)
    capas: List[Any] = lay["capas"]
    heights: List[float] = lay["band_heights"]
    page_h: int = int(lay["page_h"])

    width = PAGE_W_PX * _S
    height = page_h * _S
    canvas = Canvas(width, height, background=(255, 255, 255))

    ink = _hex_rgb(INK_HEX)
    dim = _hex_rgb(DIM_HEX)
    accent = _hex_rgb(ACCENT_HEX)
    fill_a = _hex_rgb(FILL_A_HEX)
    fill_b = _hex_rgb(FILL_B_HEX)
    white = (255, 255, 255)
    text_c = _hex_rgb(TEXT_HEX)

    def T(x: float, y: float, content: str, scale: int = _S,
          color: Tuple[int, int, int] = ink) -> None:
        canvas.text(int(x * _S), int(y * _S), content, scale=scale,
                    color=color)

    def TW(content: str, scale: int = _S) -> float:
        return canvas.text_width(content, scale) / _S

    # -- cabecera ---------------------------------------------------------
    titulo = (title or detalle.nombre).upper()
    T(PAGE_W_PX / 2.0 - TW(titulo, 3) / 2.0, 22, titulo, 3)
    sub = (f"{detalle.etiqueta_corta()}"
           f"{' — ' + detalle.sentido if detalle.sentido else ''}")
    sub = sub.upper()
    T(PAGE_W_PX / 2.0 - TW(sub, 2) / 2.0, 48, sub, 2, dim)
    y_res = 66.0
    for line in lay["resumen_lines"][:3]:
        line_u = line.upper()
        T(PAGE_W_PX / 2.0 - TW(line_u, 2) / 2.0, y_res, line_u, 2, dim)
        y_res += 14

    # -- corte por capas -----------------------------------------------------
    top_y = 118.0
    x0, x1 = 96.0, 400.0
    y = top_y
    for index, (capa, band_h) in enumerate(zip(capas, heights), 1):
        fill = fill_a if index % 2 else fill_b
        cy = y + band_h / 2.0
        canvas.rect_fill(int(x0 * _S), int(y * _S),
                         int((x1 - x0) * _S), int(band_h * _S), fill)
        for seg in (((x0, y), (x1, y)), ((x1, y), (x1, y + band_h)),
                    ((x1, y + band_h), (x0, y + band_h)),
                    ((x0, y + band_h), (x0, y))):
            canvas.line(seg[0][0] * _S, seg[0][1] * _S,
                        seg[1][0] * _S, seg[1][1] * _S, ink, _S)
        _draw_circle_png(canvas, x0 + 26, cy, 11, accent)
        numero = str(index)
        T(x0 + 26 - TW(numero, 2) / 2.0, cy - 7, numero, 2, white)
        canvas.line((x0 + 40) * _S, cy * _S, (x1 + 26) * _S, cy * _S,
                    dim, 1)
        T(x1 + 32, cy - 6, capa.etiqueta().upper(), 2)
        y += band_h

    # -- cota del espesor total -------------------------------------------------
    if capas:
        cota_x = 60.0
        canvas.line(cota_x * _S, top_y * _S, cota_x * _S,
                    (top_y + lay["stack_h"]) * _S, ink, _S)
        for tip_y in (top_y, top_y + lay["stack_h"]):
            canvas.line((cota_x - 5) * _S, tip_y * _S,
                        (cota_x + 5) * _S, tip_y * _S, ink, _S)
        espesor = (f"{detalle.espesor_total_mm:g}"
                   if float(detalle.espesor_total_mm).is_integer()
                   else f"{detalle.espesor_total_mm:.1f}")
        T(cota_x + 8, top_y + 4, f"ESPESOR TOTAL {espesor} MM", 2)

    # -- leyenda -----------------------------------------------------------------
    legend_label_y = 470.0
    T(x0, legend_label_y - 12, "LEYENDA (MATERIALES)", 2)
    canvas.line(x0 * _S, legend_label_y * _S, (PAGE_W_PX - 40) * _S,
                legend_label_y * _S, ink, _S)
    header_y = legend_label_y + 14.0
    cols = (x0 + 4, x0 + 40, x0 + 210, x0 + 280)
    for col, text in zip(cols, ("Nº", "CAPA", "ESPESOR", "MATERIAL")):
        T(col, header_y - 11, text, 2)
    line_y = header_y + 6.0
    canvas.line(x0 * _S, line_y * _S, (PAGE_W_PX - 40) * _S,
                line_y * _S, ink, 1)
    row_y = header_y + 20.0
    for index, (capa, _band) in enumerate(zip(capas, heights), 1):
        espesor = (f"{capa.espesor_mm:g} mm"
                   if float(capa.espesor_mm).is_integer()
                   else f"{capa.espesor_mm:.1f} mm")
        T(cols[0], row_y - 11, str(index), 2)
        T(cols[1], row_y - 11, capa.nombre.upper(), 2)
        T(cols[2], row_y - 11, espesor.upper(), 2)
        T(cols[3], row_y - 11, capa.material.upper(), 2)
        row_y += 20.0
    if capas:
        canvas.line(x0 * _S, (row_y - 20 + 14) * _S,
                    (PAGE_W_PX - 40) * _S, (row_y - 20 + 14) * _S,
                    ink, 1)

    # -- notas y norma ---------------------------------------------------------
    body_y = 470 + 20 * (len(capas) + 1) + 26
    for line in lay["resumen_lines"][3:] + lay["norma_lines"] \
            + lay["notas"]:
        T(x0, body_y - 11, line.upper(), 2, dim)
        body_y += 16

    # -- cajetín ------------------------------------------------------------------
    cajetin_y = page_h - 30
    canvas.line(40 * _S, (cajetin_y - 14) * _S, (PAGE_W_PX - 40) * _S,
                (cajetin_y - 14) * _S, ink, _S)
    fuente = str(detalle.fuente.get("titulo", "")) \
        if detalle.fuente else ""
    cajetin = "ARQ GEN · BIBLIOTECA DE DETALLES CONSTRUCTIVOS"
    if region_label:
        cajetin += f" · {region_label.upper()}"
    if fuente:
        cajetin += f" · {fuente.upper()}"
    T(40, cajetin_y, cajetin, 2, dim)
    did = detalle.id.upper()
    T(PAGE_W_PX - 40 - TW(did, 2), cajetin_y, did, 2, dim)

    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    return canvas.save_png(out_path)


# ==========================================================================
# Despachador por extensión
# ==========================================================================

def export_detalle(detalle, out_path: str, title: str = "",
                   region_label: str = "") -> str:
    """Despacha por extensión: .pdf → PDF, .png → PNG, resto → SVG.

    El SVG lo dibuja ``exporters.detalle_svg`` (v3.5.0): los tres
    canales comparten el mismo contenido de ficha.
    """
    _require(detalle)
    lower = str(out_path).lower()
    if lower.endswith(".pdf"):
        return export_detalle_pdf(detalle, out_path, title=title,
                                  region_label=region_label)
    if lower.endswith(".png"):
        return export_detalle_png(detalle, out_path, title=title,
                                  region_label=region_label)
    from exporters.detalle_svg import export_detalle_svg
    return export_detalle_svg(detalle, out_path, title=title,
                              region_label=region_label)


__all__ = ["export_detalle_pdf", "export_detalle_png", "export_detalle"]
