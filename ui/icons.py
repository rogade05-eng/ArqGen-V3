"""Íconos y marca de ARQ GEN (mejora UX v3.0.0).

Dos responsabilidades, ambas 100 % offline y deterministas:

1. ICONS: registro de glifos por funcionalidad. La barra de
   herramientas y los diálogos anteponen el glifo a la etiqueta para
   que cada acción se reconozca de un vistazo (y el texto sigue
   explicándolo: no abruma ni depende de memoria).

2. Logo programático: dibuja el logotipo (chevron de cubierta sobre
   líneas de forjado, dentro de una placa redondeada con degradado)
   pixel a pixel con supermuestreo anti-aliasing y lo empaqueta en PNG
   y en ICO multi-tamaño SIN dependencias externas (solo zlib/struct).
   El mismo generador alimenta el ícono de la ventana principal
   (iconphoto) y el archivo resources/branding/logo.ico que PyInstaller
   usa como icono del EXE (03_COMPILAR.bat --icon).

Todo es puro (sin Tk) salvo los ayudantes opcionales que aceptan un
root ya creado.
"""

from __future__ import annotations

import base64
import os
import struct
import zlib
from typing import Callable, Dict, List, Optional, Tuple

# -- Glifos por funcionalidad -------------------------------------------------
# Caracteres seguros en Segoe UI Symbol / DejaVu (sin depender de emoji
# a color). Cada clave coincide con una acción de la interfaz.
ICONS: Dict[str, str] = {
    "building_wizard": "\U0001F3E0",   # 🏠
    "local_wizard": "✨",
    "guide": "🧭",
    "fit": "⛶",
    "zoom_in": "＋",
    "zoom_out": "－",
    "new_object": "＋",
    "edit": "✎",
    "delete": "🗑",
    "save": "💾",
    "open": "📂",
    "new_project": "📄",
    "search": "🔎",
    "theme": "🌓",
    "autosave": " autorescue",  # placeholder: se usa SOLO el texto
    "panels": "▤",
    "help_mode": "?",
    "export": "⤓",
    "calc": "∑",
    "levels": "⇕",
    # Herramientas de edición tipo CAD (v3.14.0): glifos verificados
    # en DejaVu Sans y Segoe UI Symbol.
    "cad_herramientas": "🛠",
    "cad_mover": "✚",
    "cad_copiar": "❐",
    "cad_reflejar": "⇄",
    "cad_girar": "↻",
    "cad_recortar": "✂",
    "cad_alargar": "⟶",
    "cad_chaflan": "┌",
    "cad_dividir": "╪",
    "cad_estirar": "⇥",
    "cad_paralela": "∥",
    "cad_borrar": "🗑",
    "cad_seleccionar": "↖",
    # Concepción de espacios (v3.15.0): glifos verificados en DejaVu
    # Sans (♿⌂) y en el bloque de pictogramas (🛋, como 🏠/🛠).
    "diseno_espacios": "🛋",
    "mobiliario": "🛋",
    "cubiertas": "⌂",
    "accesibilidad": "♿",
    # Ascensores y fachada (v3.18.0): pictograma de cabina y sol/nube
    # y tabla, verificados en Segoe UI Symbol / DejaVu Sans.
    "ascensores": "🛗",
    "parasoles": "🌤",
    "piel": "▤",
    # Escaleras, aberturas, iluminación y alarmas (v3.19.0)
    "escaleras": "🪜",
    "aberturas": "🚪",
    "iluminacion": "💡",
    "alarmas": "🔔",
}

# Acciones cuyo glifo es obligatorio (lo verifican las pruebas).
REQUIRED_ICONS = ("building_wizard", "local_wizard", "guide", "fit",
                  "zoom_in", "zoom_out", "new_object", "edit", "save",
                  "open", "new_project", "search", "theme", "export",
                  "calc")


def glyph(key: str) -> str:
    """Glifo de una funcionalidad ('' si no está registrado)."""
    return ICONS.get(key, "")


def label(key: str, text: str) -> str:
    """Etiqueta con glifo delante: `label('save', 'Guardar')` → '💾 Guardar'."""
    g = glyph(key)
    return f"{g} {text}" if g else text


# -- Escritor PNG mínimo (RGBA, 8 bits, sin filtros) ---------------------------

def png_bytes(width: int, height: int,
              pixel_fn: Callable[[float, float], Tuple[int, int, int, int]],
              supersample: int = 1) -> bytes:
    """Genera un PNG RGBA llamando a `pixel_fn(x, y)` en coordenadas
    normalizadas 0..1 (origen arriba-izquierda).

    Con `supersample > 1` promedia SS×SS muestras por píxel
    (anti-aliasing barato y determinista).
    """
    raw = bytearray()
    ss = max(1, int(supersample))
    inv = 1.0 / (ss * width)
    for py in range(height):
        raw.append(0)  # filtro "None" por fila
        for px in range(width):
            r = g = b = a = 0
            for sy in range(ss):
                fy = (py * ss + sy + 0.5) * inv
                for sx in range(ss):
                    fx = (px * ss + sx + 0.5) * inv
                    pr, pg, pb, pa = pixel_fn(fx, fy)
                    r += pr
                    g += pg
                    b += pb
                    a += pa
            n = ss * ss
            raw.extend((
                min(255, r // n), min(255, g // n),
                min(255, b // n), min(255, a // n)))
    return _png_container(width, height, bytes(raw))


def _png_container(width: int, height: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


# -- Geometría del logo ---------------------------------------------------------

def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _mix(c1: Tuple[int, int, int], c2: Tuple[int, int, int],
         t: float) -> Tuple[int, int, int]:
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def _capsule_dist(px: float, py: float, ax: float, ay: float,
                  bx: float, by: float) -> float:
    """Distancia punto–segmento (en coordenadas normalizadas)."""
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    t = 0.0 if vv <= 0 else _clamp01((wx * vx + wy * vy) / vv)
    dx, dy = wx - t * vx, wy - t * vy
    return (dx * dx + dy * dy) ** 0.5


def _rounded_plate_dist(px: float, py: float, radius: float) -> float:
    """SDF de placa redondeada 0..1; negativo dentro."""
    r = radius
    qx, qy = abs(px - 0.5) - (0.5 - r), abs(py - 0.5) - (0.5 - r)
    outside = ((max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2) ** 0.5) - r
    inside = min(max(qx, qy), 0.0)
    return outside + inside


# Paleta de marca (coherente con el acento del tema oscuro).
BRAND_TOP = (0x24, 0x3D, 0x66)
BRAND_BOTTOM = (0x0E, 0x18, 0x2B)
BRAND_ROOF = (0xF4, 0xF7, 0xFC)
BRAND_FLOOR_1 = (0x5B, 0x8D, 0xEF)
BRAND_FLOOR_2 = (0x7F, 0xA6, 0xE8)
BRAND_FLOOR_3 = (0xA9, 0xC1, 0xF0)

_ROOF_W = 0.052          # medio grosor del trazo del chevron
_FLOOR_W = 0.022         # medio grosor de las líneas de forjado
_CHEVRON = ((0.16, 0.58), (0.50, 0.22), (0.84, 0.58))
_FLOORS = ((0.32, 0.72, 0.68, 0.72, BRAND_FLOOR_1),
           (0.40, 0.82, 0.60, 0.82, BRAND_FLOOR_2),
           (0.47, 0.90, 0.53, 0.90, BRAND_FLOOR_3))


def logo_pixel(fx: float, fy: float) -> Tuple[int, int, int, int]:
    """Color del logo en (x, y) normalizado — determinista y puro."""
    d_plate = _rounded_plate_dist(fx, fy, 0.16)
    if d_plate > 0.008:
        return (0, 0, 0, 0)
    alpha = _clamp01(0.5 - d_plate / 0.008)
    base = _mix(BRAND_TOP, BRAND_BOTTOM, _clamp01(fy))
    color = base
    # Chevron (dos segmentos desde la cumbrera)
    (ax, ay), (mx, my), (bx, by) = _CHEVRON
    d_roof = min(_capsule_dist(fx, fy, ax, ay, mx, my),
                 _capsule_dist(fx, fy, mx, my, bx, by))
    if d_roof < _ROOF_W + 0.004:
        t = _clamp01((_ROOF_W + 0.004 - d_roof) / 0.008)
        color = _mix(color, BRAND_ROOF, t)
    # Forjados
    for x0, y0, x1, y1, tone in _FLOORS:
        d = _capsule_dist(fx, fy, x0, y0, x1, y1)
        if d < _FLOOR_W + 0.003:
            t = _clamp01((_FLOOR_W + 0.003 - d) / 0.006)
            color = _mix(color, tone, t)
    return (color[0], color[1], color[2], int(255 * alpha))


def render_logo(size: int, supersample: int = 4) -> bytes:
    """PNG del logo en `size` px (cuadrado)."""
    return png_bytes(size, size, logo_pixel, supersample=supersample)


def render_logo_b64(size: int, supersample: int = 4) -> str:
    """PNG del logo en base64 — válido para tk.PhotoImage(data=...)."""
    return base64.b64encode(render_logo(size, supersample)).decode("ascii")


# -- Escritor ICO (contenedor con PNG embebidos) ---------------------------------

def ico_bytes(sizes: Tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256),
              supersample: int = 4) -> bytes:
    """ICO multi-tamaño con PNG embebidos (Vista+). Determinista."""
    pngs = [render_logo(s, supersample) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = bytearray()
    offset = 6 + 16 * len(sizes)
    for size, data in zip(sizes, pngs):
        w = 0 if size >= 256 else size
        entries.extend(struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32,
                                   len(data), offset))
        offset += len(data)
    return header + bytes(entries) + b"".join(pngs)


def write_branding_files(out_dir: str) -> Dict[str, str]:
    """Escribe logo.png (256), logo_32.png y logo.ico; devuelve rutas."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {
        "png": os.path.join(out_dir, "logo.png"),
        "png_small": os.path.join(out_dir, "logo_32.png"),
        "ico": os.path.join(out_dir, "logo.ico"),
    }
    with open(paths["png"], "wb") as fh:
        fh.write(render_logo(256))
    with open(paths["png_small"], "wb") as fh:
        fh.write(render_logo(32))
    with open(paths["ico"], "wb") as fh:
        fh.write(ico_bytes())
    return paths


# -- Ayudantes Tk (opcionales) ----------------------------------------------------

def window_icon(root: Any = None, size: int = 64) -> Optional[Any]:
    """Ícono de ventana: usa resources/branding/logo.png si existe y si
    no lo genera en memoria. Devuelve el PhotoImage (guardar referencia)
    o None si Tk no está disponible.

    El PNG de branding es de 256 px (pensado para la barra de TÍTULO y
    el ícono del EXE): NO usar directamente en barras de herramientas.

    El PhotoImage se registra SIEMPRE en el intérprete de `root`:
    las imágenes viven por-intérprete y sin master explícito quedarían
    ancladas al primer root del proceso (invisible para cualquier otra
    ventana: «image does not exist»).
    """
    try:
        import tkinter as tk
        from app.paths import resource_path
        path = resource_path("branding", "logo.png")
        if os.path.exists(path):
            photo = tk.PhotoImage(master=root, file=path)
        else:
            photo = tk.PhotoImage(master=root, data=render_logo_b64(size))
        if root is not None:
            root.iconphoto(True, photo)
        return photo
    except Exception:  # noqa: BLE001 - sin display o Tk sin PNG: sin ícono
        return None


def toolbar_logo(size: int = 22, supersample: int = 6,
                 master: Any = None) -> Optional[Any]:
    """Logo PEQUEÑO para barras de herramientas (v3.9.0).

    Se genera en memoria al tamaño justo (22 px por defecto, con
    supermuestreo anti-aliasing) en lugar de reutilizar el PNG de 256 px
    del branding: ese tamaño gigante en la barra principal le robaba al
    plano más de 200 px de alto. Pasa `master` (la ventana dueña) para
    que el PhotoImage viva en SU intérprete Tk. Devuelve el PhotoImage
    (guardar referencia) o None si Tk no está disponible.
    """
    try:
        import tkinter as tk
        return tk.PhotoImage(master=master,
                             data=render_logo_b64(size, supersample))
    except Exception:  # noqa: BLE001 - sin display o Tk sin PNG: sin logo
        return None


__all__ = [
    "ICONS", "REQUIRED_ICONS", "glyph", "label", "png_bytes",
    "render_logo", "render_logo_b64", "ico_bytes",
    "write_branding_files", "window_icon", "toolbar_logo", "logo_pixel",
]
