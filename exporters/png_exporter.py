"""Exportador PNG 100% stdlib (v2.0.0, brecha #4; v3.3.0 vistas).

Gráfico de barras del presupuesto PRECONS III rasterizado en Python
puro: buffer RGB, fuente bitmap 5x7 embebida, compresión zlib y
contenedores IHDR/IDAT/IEND escritos a mano. Sin Pillow ni otras
dependencias: funciona 100% offline igual que el resto del sistema.

v3.3.0: Canvas gana línea (Bresenham con grosor), polilínea, arco
paramétrico y relleno poligonal por scanline — con esto el rasterizador
de vistas (exporters.view_exporter) dibuja plantas, elevaciones, cortes
y detalles con las mismas primitivas que el lienzo Tkinter.
"""

from __future__ import annotations

import math
import struct
import zlib
from typing import Any, Dict, List, Sequence, Tuple

# -- fuente bitmap 5x7 (columnas LSB→MSB por fila) -----------------------------
# Cada glifo: 7 enteros, bit 0 = columna izquierda.
_FONT: Dict[str, Tuple[int, ...]] = {
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    " ": (0, 0, 0, 0, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 0x0C, 0x0C),
    ",": (0, 0, 0, 0, 0x0C, 0x04, 0x08),
    "-": (0, 0, 0, 0x1F, 0, 0, 0),
    "+": (0, 0x04, 0x04, 0x1F, 0x04, 0x04, 0),
    ":": (0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0),
    "/": (0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10),
    "%": (0x19, 0x1A, 0x02, 0x04, 0x08, 0x0B, 0x13),
    "$": (0x04, 0x0F, 0x14, 0x0E, 0x05, 0x1E, 0x04),
    "(": (0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02),
    ")": (0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08),
    "·": (0, 0, 0x0C, 0x0C, 0, 0, 0),
}


def _upper(text: str) -> str:
    """Mayúsculas y des-acentuación para la fuente bitmap."""
    mapping = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U",
               "Ñ": "N", "×": "X", "—": "-", "–": "-", "“": '"', "”": '"'}
    out = []
    for ch in str(text).upper():
        out.append(mapping.get(ch, ch if ch in _FONT or ch == '"' else
                               (ch if ord(ch) < 128 else "?")))
    return "".join(out)


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "@").replace(".", ",") \
        .replace("@", " ")


class Canvas:
    """Buffer RGB con primitivas mínimas y texto bitmap escalable."""

    def __init__(self, width: int, height: int,
                 background: Tuple[int, int, int] = (255, 255, 255)) -> None:
        self.w = width
        self.h = height
        self.buf = bytearray(background * (width * height))

    def px(self, x: int, y: int, color: Tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            index = (y * self.w + x) * 3
            self.buf[index:index + 3] = bytes(color)

    def rect_fill(self, x: int, y: int, w: int, h: int,
                  color: Tuple[int, int, int]) -> None:
        for yy in range(max(0, y), min(self.h, y + h)):
            base = (yy * self.w) * 3
            x0 = max(0, x) * 3
            x1 = min(self.w, x + w) * 3
            if x1 > x0:
                self.buf[base + x0:base + x1] = bytes(color) * ((x1 - x0) // 3)

    def rect_stroke(self, x: int, y: int, w: int, h: int,
                    color: Tuple[int, int, int]) -> None:
        for i in range(w):
            self.px(x + i, y, color)
            self.px(x + i, y + h - 1, color)
        for j in range(h):
            self.px(x, y + j, color)
            self.px(x + w - 1, y + j, color)

    def hline(self, x0: int, x1: int, y: int,
              color: Tuple[int, int, int]) -> None:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            self.px(x, y, color)

    # -- primitivas vectoriales (v3.3.0, vistas) ---------------------------
    def line(self, x0: int, y0: int, x1: int, y1: int,
             color: Tuple[int, int, int], thickness: int = 1) -> None:
        """Segmento Bresenham con grosor (pincel cuadrado centrado)."""
        thickness = max(1, int(thickness))
        half = thickness // 2
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = int(x0), int(y0)
        guard = 0
        limit = 4 * (self.w + self.h) + 4 * (dx + dy) + 16
        while True:
            if thickness <= 1:
                self.px(x, y, color)
            else:
                self.rect_fill(x - half, y - half, thickness, thickness,
                               color)
            if x == x1 and y == y1:
                break
            guard += 1
            if guard > limit:  # defensa contra bucles degenerados
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def polyline(self, points: Sequence[Tuple[float, float]],
                 color: Tuple[int, int, int], thickness: int = 1) -> None:
        """Segmentos encadenados (lista de puntos en píxeles)."""
        for index in range(len(points) - 1):
            self.line(int(points[index][0]), int(points[index][1]),
                      int(points[index + 1][0]), int(points[index + 1][1]),
                      color, thickness)

    def arc(self, cx: float, cy: float, r: float, a0_deg: float,
            a1_deg: float, color: Tuple[int, int, int],
            thickness: int = 1) -> None:
        """Arco paramétrico en grados (ángulos CCW desde el eje X)."""
        r = max(r, 0.5)
        sweep = abs(a1_deg - a0_deg)
        steps = max(12, min(int(sweep * r / 2.0) + 8, 720))
        prev: Tuple[float, float] = ()
        for index in range(steps + 1):
            angle = math.radians(a0_deg + (a1_deg - a0_deg) * index / steps)
            point = (cx + r * math.cos(angle), cy + r * math.sin(angle))
            if prev:
                self.line(prev[0], prev[1], point[0], point[1], color,
                          thickness)
            prev = point

    def polygon_fill(self, points: Sequence[Tuple[float, float]],
                     color: Tuple[int, int, int]) -> None:
        """Relleno par-impar por scanline (polígono simple, no convexo)."""
        if len(points) < 3:
            return
        ys = [p[1] for p in points]
        y_start = max(0, int(math.floor(min(ys))))
        y_end = min(self.h - 1, int(math.ceil(max(ys))))
        count = len(points)
        for y in range(y_start, y_end + 1):
            xs: List[float] = []
            j = count - 1
            for i in range(count):
                yi, yj = points[i][1], points[j][1]
                if (yi > y) != (yj > y):
                    xs.append(points[j][0] + (y - yj)
                              / (yi - yj + 1e-12)
                              * (points[i][0] - points[j][0]))
                j = i
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                a = int(math.ceil(xs[k]))
                b = int(math.floor(xs[k + 1]))
                if b < a:
                    continue
                base = (y * self.w) * 3
                lo = max(0, a) * 3
                hi = min(self.w, b + 1) * 3
                if hi > lo:
                    self.buf[base + lo:base + hi] = \
                        bytes(color) * ((hi - lo) // 3)

    def text(self, x: int, y: int, content: str, scale: int = 2,
             color: Tuple[int, int, int] = (30, 30, 30)) -> int:
        """Dibuja texto; devuelve el ancho ocupado."""
        cursor = x
        for ch in _upper(content):
            glyph = _FONT.get(ch, _FONT.get("?", (0x1F, 0x11, 0x01, 0x02,
                                                  0x04, 0, 0x04)))
            if ch == '"':
                cursor += 3 * scale
                continue
            for row, bits in enumerate(glyph):
                for col in range(5):
                    # La fuente se diseña MSB-primero (bit 4 = columna
                    # izquierda); leerla LSB-primero reflejaba cada
                    # glifo en espejo (defecto corregido en v3.11.0).
                    if bits & (1 << (4 - col)):
                        self.rect_fill(cursor + col * scale,
                                       y + row * scale, scale, scale, color)
            cursor += 6 * scale
        return cursor - x

    def text_width(self, content: str, scale: int = 2) -> int:
        return max(0, len(_upper(content)) * 6 * scale - scale)

    def save_png(self, path: str) -> str:
        raw = bytearray()
        for y in range(self.h):
            raw.append(0)  # filtro None
            raw += self.buf[y * self.w * 3:(y + 1) * self.w * 3]

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
            handle.write(chunk(b"IHDR", ihdr))
            handle.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
            handle.write(chunk(b"IEND", b""))
        return path


# Colores de barras (paleta sobria, cicla si hay más secciones que colores)
_BAR_COLORS = [(47, 84, 150), (68, 114, 196), (112, 173, 71),
               (237, 125, 49), (165, 165, 165), (99, 81, 148),
               (91, 155, 213), (180, 120, 60)]


def export_budget_chart_png(tree: Dict[str, Any], out_path: str,
                            project_name: str = "",
                            scale: int = 2) -> str:
    """Gráfico de barras horizontales: importe directo por sección.

    tree: salida de PreconsBudgetService.tree().
    """
    currency = tree.get("currency", "CUP")
    chapters = [c for c in tree.get("chapters", [])
                if c.get("direct", 0.0) > 0]
    scale = max(1, int(scale))
    margin = 14 * scale
    title = _upper(f"Presupuesto por sección — {project_name}".strip(" —"))

    if chapters:
        label_w = max((len(_upper(f"{c['code']} · {c['name']}"))
                       for c in chapters)) * 6 * scale
        label_w = min(label_w, 200 * scale)
        max_value = max(c["direct"] for c in chapters) or 1.0
        bar_h = 10 * scale
        gap = 7 * scale
        width = margin + label_w + 20 * scale + 12 * scale * 6 + margin
        height = margin + 8 * scale + (bar_h + gap) * len(chapters) \
            + 12 * scale + margin
        canvas = Canvas(width, height, background=(250, 250, 250))
        canvas.text(margin, margin - 4 * scale, title, scale=scale + 1,
                    color=(20, 30, 60))
        top = margin + 10 * scale
        for index, chapter in enumerate(chapters):
            y = top + index * (bar_h + gap)
            color = _BAR_COLORS[index % len(_BAR_COLORS)]
            label = f"{chapter['code']} · {chapter['name']}"
            clipped = label[:label_w // (6 * scale) - 1]
            canvas.text(margin, y + (bar_h - 7 * scale) // 2, clipped,
                        scale=scale, color=(60, 60, 60))
            bar_x = margin + label_w + 10 * scale
            bar_w = int((chapter["direct"] / max_value) * (20 * scale + 0))
            bar_w = max(bar_w, 2)
            canvas.rect_fill(bar_x, y, bar_w, bar_h, color)
            value_text = f"{_fmt_money(chapter['direct'])} {currency}"
            canvas.text(bar_x + bar_w + 3 * scale,
                        y + (bar_h - 7 * scale) // 2, value_text,
                        scale=scale, color=(30, 30, 30))
        bottom = top + len(chapters) * (bar_h + gap)
        canvas.hline(margin, width - margin, bottom + 2 * scale,
                     (200, 200, 200))
        total_line = (f"TOTAL {tree.get('total', 0.0)} {currency}")
        canvas.text(margin, bottom + 5 * scale, _upper(total_line),
                    scale=scale, color=(20, 30, 60))
    else:
        width, height = 420 * scale // 2 + 200, 120
        canvas = Canvas(width, height)
        canvas.text(20, 40, "PRESUPUESTO VACIO - ANADE RENGLONES DESDE "
                            "EL CATALOGO", scale=2)

    return canvas.save_png(out_path)


def export_variant_costs_png(entries: Sequence[Tuple[str, float]],
                             out_path: str, project_name: str = "",
                             calidad: str = "", scale: int = 2) -> str:
    """Comparativa de barras: coste estimado PRECONS por variante.

    entries: [(título de la variante, coste total)] en el orden del
    ranking; la primera (recomendada) se marca en la línea final si es
    también la más barata, y siempre se anota la más económica.
    """
    scale = max(1, int(scale))
    margin = 14 * scale
    currency = "CUP"
    data = [(str(title), float(value)) for title, value in entries
            if float(value) > 0]
    subtitle = _upper(f"Estimación PRECONS III · acabados {calidad}"
                      if calidad else "Estimación PRECONS III")
    title = _upper(f"Coste por variante — {project_name}".strip(" —"))

    if data:
        label_w = max(len(_upper(t)) for t, _v in data) * 6 * scale
        label_w = min(label_w, 250 * scale)
        max_value = max(v for _t, v in data) or 1.0
        bar_h = 10 * scale
        gap = 7 * scale
        value_w = 18 * 6 * scale
        width = margin + label_w + 10 * scale + 26 * scale + value_w + margin
        height = margin + 8 * scale + (bar_h + gap) * len(data) \
            + 12 * scale + margin
        canvas = Canvas(width, height, background=(250, 250, 250))
        canvas.text(margin, margin - 4 * scale, title, scale=scale + 1,
                    color=(20, 30, 60))
        canvas.text(margin, margin + 8 * scale, subtitle, scale=scale,
                    color=(90, 100, 110))
        top = margin + 22 * scale
        for index, (label, value) in enumerate(data):
            y = top + index * (bar_h + gap)
            color = _BAR_COLORS[index % len(_BAR_COLORS)]
            clipped = _upper(label)[:label_w // (6 * scale) - 1]
            canvas.text(margin, y + (bar_h - 7 * scale) // 2, clipped,
                        scale=scale, color=(60, 60, 60))
            bar_x = margin + label_w + 10 * scale
            bar_w = max(int((value / max_value) * (26 * scale)), 2)
            canvas.rect_fill(bar_x, y, bar_w, bar_h, color)
            value_text = f"{_fmt_money(value)} {currency}"
            canvas.text(bar_x + bar_w + 3 * scale,
                        y + (bar_h - 7 * scale) // 2, value_text,
                        scale=scale, color=(30, 30, 30))
        bottom = top + len(data) * (bar_h + gap)
        canvas.hline(margin, width - margin, bottom + 2 * scale,
                     (200, 200, 200))
        barato, costo_barato = min(data, key=lambda par: par[1])
        canvas.text(margin, bottom + 5 * scale,
                    _upper(f"MÁS ECONÓMICA: {barato} "
                           f"({_fmt_money(costo_barato)} {currency})"),
                    scale=scale, color=(20, 30, 60))
    else:
        width, height = 480, 120
        canvas = Canvas(width, height)
        canvas.text(20, 40, "SIN COSTES: GENERA VARIANTES CON EL "
                            "CATÁLOGO PRECONS III", scale=2)

    return canvas.save_png(out_path)


__all__ = ["export_budget_chart_png", "export_variant_costs_png",
           "Canvas"]
