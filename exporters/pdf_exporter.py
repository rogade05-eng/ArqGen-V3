"""Exportador PDF 100% stdlib (v2.0.0, brecha #4).

Genera PDF 1.4 válido sin dependencias externas: fuentes base
(Helvetica regular/negrita/cursiva, WinAnsiEncoding), texto, líneas,
rectángulos y tablas con cabecera repetida y salto de página
automático. El presupuesto PRECONS III y los análisis de precio se
exportan con ``export_budget_pdf`` / ``export_analysis_pdf``.
"""

from __future__ import annotations

import math
import zlib
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

PAGE_W = 595.28   # A4
PAGE_H = 841.89
MARGIN = 42.0

# Anchos estándar Helvetica (1/1000 em) para alineación derecha exacta.
_HELV_WIDTH: Dict[str, float] = {
    " ": 278, "!": 278, "'": 191, "(": 333, ")": 333, "*": 389, "+": 584,
    ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584,
    "=": 584, ">": 584, "?": 556, "$": 556, "%": 889, "#": 556,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556,
    "6": 556, "7": 556, "8": 556, "9": 556,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
}


def _winansi(text: str) -> str:
    """Convierte a cp1252 con escapes PDF; los faltantes pasan a '?'."""
    out = []
    for ch in str(text):
        if ch in ("\\", "(", ")"):
            out.append("\\" + ch)
            continue
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def text_width(text: str, size: float, bold: bool = False) -> float:
    """Ancho del texto en puntos (Helvetica)."""
    total = 0.0
    for ch in str(text):
        if ch in ("\\", "(", ")"):
            continue
        total += _HELV_WIDTH.get(ch, 556)
    factor = 1.08 if bold else 1.0
    return total * size * factor / 1000.0


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "@").replace(".", ",") \
        .replace("@", " ")


class PdfDoc:
    """Documento PDF básico con fuentes base y WinAnsi."""

    FONTS = {"F1": "Helvetica", "F2": "Helvetica-Bold",
             "F3": "Helvetica-Oblique"}

    def __init__(self, title: str = "", author: str = "ARQ GEN") -> None:
        self.title = title
        self.author = author
        self.pages: List[List[str]] = []
        self._current: List[str] = []

    # -- primitivas (coordenadas: origen abajo-izquierda) -------------------
    def add_page(self) -> None:
        if self._current:
            self.pages.append(self._current)
        self._current = []

    def _ensure(self) -> None:
        if not self._current:
            self.add_page()

    def text(self, x: float, y: float, size: float, content: str,
             bold: bool = False, italic: bool = False,
             gray: float = 0.0, rgb: Optional[Tuple[float, float, float]] = None,
             angle: float = 0.0
             ) -> None:
        """Texto en (x, y); ``angle`` en grados CCW (v3.6.0: cotas
        verticales). Con angle=0 la matriz es idéntica a la histórica
        (los PDF anteriores quedan byte a byte iguales)."""
        self._ensure()
        font = "F2" if bold else ("F3" if italic else "F1")
        if rgb is not None:
            color = f"{rgb[0]:.2f} {rgb[1]:.2f} {rgb[2]:.2f} rg"
        else:
            color = f"{gray:.2f} g"
        if angle:
            rad = math.radians(angle)
            cos_v, sin_v = math.cos(rad), math.sin(rad)
            matrix = (f"{cos_v:.4f} {sin_v:.4f} {-sin_v:.4f} "
                      f"{cos_v:.4f} {x:.2f} {y:.2f} Tm")
        else:
            matrix = f"1 0 0 1 {x:.2f} {y:.2f} Tm"
        self._current.append(
            f"BT /{font} {size:.2f} Tf {color} "
            f"{matrix} ({_winansi(content)}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float,
             width: float = 0.6, gray: float = 0.0,
             rgb: Optional[Tuple[float, float, float]] = None,
             dash: Optional[Tuple[float, float]] = None) -> None:
        self._ensure()
        if rgb is not None:
            color = f"{rgb[0]:.2f} {rgb[1]:.2f} {rgb[2]:.2f} RG"
        else:
            color = f"{gray:.2f} G"
        d = f"[{dash[0]:.2f} {dash[1]:.2f}] 0 d " if dash else ""
        reset = " [] 0 d" if dash else ""
        self._current.append(
            f"{width:.2f} w {color} {d}{x1:.2f} {y1:.2f} m "
            f"{x2:.2f} {y2:.2f} l S{reset}")

    def rect(self, x: float, y: float, w: float, h: float,
             fill_gray: Optional[float] = None,
             stroke_gray: float = 0.0,
             fill_rgb: Optional[Tuple[float, float, float]] = None,
             stroke_rgb: Optional[Tuple[float, float, float]] = None,
             stroke_width: float = 0.5) -> None:
        self._ensure()
        if fill_gray is not None or fill_rgb is not None:
            fill = (f"{fill_rgb[0]:.2f} {fill_rgb[1]:.2f} {fill_rgb[2]:.2f} rg"
                    if fill_rgb is not None else f"{fill_gray:.2f} g")
            self._current.append(
                f"{fill} {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        if stroke_gray is not None:
            stroke = (f"{stroke_rgb[0]:.2f} {stroke_rgb[1]:.2f} "
                      f"{stroke_rgb[2]:.2f} RG"
                      if stroke_rgb is not None else f"{stroke_gray:.2f} G")
            self._current.append(
                f"{stroke} {stroke_width:.2f} w "
                f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def circle(self, cx: float, cy: float, r: float,
               fill_rgb: Optional[Tuple[float, float, float]] = None,
               fill_gray: Optional[float] = None,
               stroke_rgb: Optional[Tuple[float, float, float]] = None,
               stroke_gray: Optional[float] = None,
               stroke_width: float = 0.5) -> None:
        """Círculo por 4 curvas Bézier (v3.6.0: números de capa).

        Rellena con ``f``, traza con ``S`` o ambas con ``B`` según lo
        pedido; sin relleno ni trazo no dibuja nada.
        """
        self._ensure()
        r = max(float(r), 0.05)
        k = 0.5522847498 * r
        fill: Optional[str]
        if fill_rgb is not None:
            fill = (f"{fill_rgb[0]:.2f} {fill_rgb[1]:.2f} "
                    f"{fill_rgb[2]:.2f} rg")
        elif fill_gray is not None:
            fill = f"{fill_gray:.2f} g"
        else:
            fill = None
        stroke: Optional[str]
        if stroke_rgb is not None:
            stroke = (f"{stroke_rgb[0]:.2f} {stroke_rgb[1]:.2f} "
                      f"{stroke_rgb[2]:.2f} RG")
        elif stroke_gray is not None:
            stroke = f"{stroke_gray:.2f} G"
        else:
            stroke = None
        if fill is None and stroke is None:
            return
        paint = "B" if (fill and stroke) else ("f" if fill else "S")
        ops: List[str] = []
        if stroke:
            ops.append(stroke)
            ops.append(f"{stroke_width:.2f} w")
        if fill:
            ops.append(fill)
        ops.append(
            f"{cx + r:.2f} {cy:.2f} m "
            f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} "
            f"{cx:.2f} {cy + r:.2f} c "
            f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} "
            f"{cx - r:.2f} {cy:.2f} c "
            f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} "
            f"{cx:.2f} {cy - r:.2f} c "
            f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} "
            f"{cx + r:.2f} {cy:.2f} c h {paint}")
        self._current.append(" ".join(ops))

    # -- serialización ------------------------------------------------------
    def save(self, path: str) -> str:
        if self._current:
            self.pages.append(self._current)
            self._current = []
        if not self.pages:
            self.add_page()
            self.pages.append(self._current)
            self._current = []
        objects: List[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        font_ids: Dict[str, int] = {}
        for name, base in self.FONTS.items():
            font_ids[name] = add(
                f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
                f"/Encoding /WinAnsiEncoding >>".encode())
        font_res = " ".join(f"/{k} {v} 0 R" for k, v in font_ids.items())

        # Distribución de ids: fonts, pages tree, [page, content]*,
        # catalog, info. Se reservan placeholders para todos.
        pages_id = len(objects) + 1
        page_ids: List[int] = []
        content_ids: List[int] = []
        next_id = pages_id + 1
        for _index in range(len(self.pages)):
            page_ids.append(next_id)
            content_ids.append(next_id + 1)
            next_id += 2
        catalog_id = next_id
        info_id = next_id + 1
        while len(objects) < info_id:
            objects.append(b"")  # placeholders hasta completar el mapa

        compressed: List[bytes] = []
        for stream in self.pages:
            raw = "\n".join(stream).encode("cp1252", errors="replace")
            compressed.append(zlib.compress(raw))
        for index, blob in enumerate(compressed):
            page = (f"<< /Type /Page /Parent {pages_id} 0 R "
                    f"/MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
                    f"/Resources << /Font << {font_res} >> >> "
                    f"/Contents {content_ids[index]} 0 R >>")
            objects[page_ids[index] - 1] = page.encode()
            objects[content_ids[index] - 1] = (
                f"<< /Length {len(blob)} /Filter /FlateDecode >>".encode()
                + b"\nstream\n" + blob + b"\nendstream")
        kids_text = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects[pages_id - 1] = (
            f"<< /Type /Pages /Kids [{kids_text}] /Count "
            f"{len(page_ids)} >>").encode()
        objects[catalog_id - 1] = (
            f"<< /Type /Catalog /Pages {pages_id} 0 R >>").encode()
        objects[info_id - 1] = (
            f"<< /Title ({_winansi(self.title)}) /Author "
            f"({_winansi(self.author)}) /Producer (ARQ GEN PDF) >>".encode())

        out = bytearray(b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n")
        offsets = [0]
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
        xref_at = len(out)
        out += f"xref\n0 {len(objects) + 1}\n".encode()
        out += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            out += f"{offset:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R "
                f"/Info {info_id} 0 R >>\nstartxref\n{xref_at}\n%%EOF\n").encode()
        with open(path, "wb") as handle:
            handle.write(bytes(out))
        return path


class PdfReport:
    """Documento de reporte con cursor, tablas y salto de página."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        self.doc = PdfDoc(title=title)
        self.title = title
        self.subtitle = subtitle
        self.y = 0.0
        self._header()

    # -- internos -------------------------------------------------------------
    def _top(self, y: float) -> float:
        return PAGE_H - y

    def _header(self) -> None:
        self.doc.add_page()
        self.y = MARGIN
        self.doc.text(MARGIN, self._top(self.y + 14), 15, self.title,
                      bold=True)
        footer = date.today().strftime("%d/%m/%Y")
        self.doc.text(PAGE_W - MARGIN - text_width(footer, 9),
                      self._top(self.y + 14), 9, footer, gray=0.45)
        self.y += 20
        if self.subtitle:
            self.doc.text(MARGIN, self._top(self.y + 12), 10, self.subtitle,
                          gray=0.3)
            self.y += 18
        self.doc.line(MARGIN, self._top(self.y), PAGE_W - MARGIN,
                      self._top(self.y), 0.8)
        self.y += 14

    def _need(self, space: float) -> None:
        if self.y + space > PAGE_H - MARGIN:
            self._header()

    # -- API ---------------------------------------------------------------------
    def heading(self, text: str) -> None:
        self._need(46)
        self.y += 6
        self.doc.text(MARGIN, self._top(self.y + 12), 11.5, text, bold=True)
        self.y += 18
        self.doc.line(MARGIN, self._top(self.y), PAGE_W - MARGIN,
                      self._top(self.y), 0.4, gray=0.7)
        self.y += 8

    def para(self, text: str, size: float = 9.5, gray: float = 0.0) -> None:
        for line in self._wrap(text, size):
            self._need(20)
            self.doc.text(MARGIN, self._top(self.y + size + 2), size, line,
                          gray=gray)
            self.y += size + 5

    @staticmethod
    def _wrap(text: str, size: float) -> List[str]:
        words = str(text).split()
        lines: List[str] = []
        current = ""
        limit = PAGE_W - 2 * MARGIN
        for word in words:
            trial = f"{current} {word}".strip()
            if text_width(trial, size) > limit and current:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [""]

    def table(self, headers: Sequence[Tuple[str, str, float]],
              rows: Sequence[Sequence[str]],
              font_size: float = 8.2, row_h: float = 13.5,
              highlight_last: bool = False) -> None:
        """headers: [(texto, 'l'|'r'|'c', ancho)]; las filas ya vienen
        formateadas. Repite la cabecera en cada salto de página."""
        def draw_header() -> None:
            self._need(row_h * 3)
            self.doc.rect(MARGIN, self._top(self.y + row_h),
                          PAGE_W - 2 * MARGIN, row_h, fill_gray=0.88)
            x = MARGIN
            for text, align, width in headers:
                self._cell(text, x, width, align, font_size, bold=True)
                x += width
            self.y += row_h

        def draw_frame(top_y: float, bottom_y: float) -> None:
            """Marco exterior desde el inicio de cabecera hasta el final
            de la última fila dibujada en la página actual."""
            height = bottom_y - top_y
            if height > 0:
                self.doc.rect(MARGIN, self._top(bottom_y),
                              sum(w for _, _, w in headers), height,
                              stroke_gray=0.85)

        def draw_rows() -> None:
            nonlocal frame_top
            for index, row in enumerate(rows):
                if self.y + row_h > PAGE_H - MARGIN:
                    # cerrar el marco de la página antes del salto
                    draw_frame(frame_top, self.y)
                    draw_header()
                    frame_top = self.y
                if index % 2 == 1:
                    self.doc.rect(MARGIN, self._top(self.y + row_h),
                                  sum(w for _, _, w in headers), row_h,
                                  fill_gray=0.955)
                x = MARGIN
                for value, (_, align, width) in zip(row, headers):
                    self._cell(value, x, width, align, font_size)
                    x += width
                self.y += row_h
            draw_frame(frame_top, self.y)
            self.y += 6

        draw_header()
        frame_top = self.y - row_h  # el marco cubre también la cabecera
        draw_rows()

    def _cell(self, text: str, x: float, width: float, align: str,
              size: float, bold: bool = False) -> None:
        pad = 4.0
        if align == "r":
            tx = x + width - pad - text_width(text, size, bold)
        elif align == "c":
            tx = x + (width - text_width(text, size, bold)) / 2.0
        else:
            tx = x + pad
        self.doc.text(tx, self._top(self.y + row_text(size)), size, text,
                      bold=bold)

    def spacer(self, height: float = 8.0) -> None:
        self.y += height

    def save(self, path: str) -> str:
        return self.doc.save(path)


def row_text(size: float) -> float:
    return size + 3.0


# -- reportes de alto nivel -------------------------------------------------

def export_budget_pdf(tree: Dict[str, Any], out_path: str,
                      project_name: str = "") -> str:
    """Presupuesto PRECONS III completo → PDF (secciones y totales)."""
    currency = tree.get("currency", "CUP")
    subtitle = (f"Proyecto: {project_name} · Catálogo PRECONS III "
                f"v{tree.get('ruleset_version', '')} · precios oficiales "
                f"({currency})")
    report = PdfReport("Presupuesto por catálogo PRECONS III", subtitle)
    report.heading("Desglose por sección del catálogo")
    headers = [("Código", "l", 62), ("Descripción", "l", 240),
               ("Ud", "c", 34), ("Cantidad", "r", 62),
               ("Precio", "r", 74), ("Importe", "r", 85)]
    for chapter in tree.get("chapters", []):
        rows = [[item["code"], item["description"][:48], item["unit"],
                 _fmt_qty(item["quantity"]), _fmt_money(item["unit_price"]),
                 _fmt_money(item["amount"])]
                for item in chapter.get("items", [])]
        if not rows:
            continue
        report.para(f"{chapter['code']} — {chapter['name']}", size=9,
                    gray=0.25)
        report.table(headers, rows)
        report.para(f"Subtotal {chapter['code']}: "
                    f"{_fmt_money(chapter.get('direct', 0.0))} {currency}",
                    size=9, gray=0.0)
        report.spacer(6)
    totals = {key: tree.get(key, 0.0) for key in
              ("direct", "transport", "indirect", "benefit", "total")}
    report.heading("Resumen general")
    labels = [("Costo directo", totals["direct"]),
              ("Transporte", totals["transport"]),
              ("Gastos generales (indirectos)", totals["indirect"]),
              ("Beneficio", totals["benefit"])]
    for label, value in labels:
        report.para(f"{label}: {_fmt_money(value)} {currency}", size=10)
    report.spacer(4)
    report.para(f"TOTAL DEL PRESUPUESTO: {_fmt_money(totals['total'])} "
                f"{currency}", size=12)
    return report.save(out_path)


def export_analysis_pdf(analysis: Dict[str, Any], out_path: str,
                        project_name: str = "") -> str:
    """Análisis de precio unitario de un renglón → PDF."""
    currency = analysis.get("currency", "CUP")
    subtitle = (f"Proyecto: {project_name} · partida {analysis.get('item')} "
                f"· modo {analysis.get('mode', 'composition')}")
    report = PdfReport("Análisis de precio unitario", subtitle)
    report.heading("Datos de la partida")
    report.para(f"{analysis.get('item')} — {analysis.get('name')} "
                f"[{analysis.get('unit')}]")
    report.para(f"Cantidad: {_fmt_qty(analysis.get('quantity', 0.0))} · "
                f"Variante: {analysis.get('variant', 'BASE')}")
    report.heading("Desglose de costos")
    rows = [
        ["Materiales", _fmt_money(analysis.get("direct_material", 0.0))],
        ["Mano de obra", _fmt_money(analysis.get("direct_labor", 0.0))],
        ["Equipos", _fmt_money(analysis.get("direct_equipment", 0.0))],
        ["Transporte", _fmt_money(analysis.get("direct_transport", 0.0))],
        ["Costo directo", _fmt_money(analysis.get("direct_cost", 0.0))],
        ["Indirectos", _fmt_money(analysis.get("indirect_cost", 0.0))],
        ["Beneficio", _fmt_money(analysis.get("benefit", 0.0))],
        ["Precio unitario", _fmt_money(analysis.get("unit_price", 0.0))],
        ["TOTAL", _fmt_money(analysis.get("total_price", 0.0))],
    ]
    report.table([("Concepto", "l", 260), (f"Importe ({currency})", "r", 150)],
                 rows, font_size=9)
    return report.save(out_path)


def _fmt_qty(value: float) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", "@").replace(".", ",").replace("@", " ") or "0"
