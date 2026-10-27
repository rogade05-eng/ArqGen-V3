"""Sistema de temas dual de ARQ GEN (mejora UX v3.0.0).

Dos temas completos — OSCURO y CLARO — con un único lenguaje visual:
fondo por capas (general → panel → control → campo), un acento amable
y letras siempre legibles. Toda la interfaz consume la paleta desde
aquí; ningún módulo define colores sueltos.

Cambio EN VIVO: `apply(root, modo)` puede llamarse con la ventana ya
construida. Las constantes COL_* se re-vinculan a nivel de módulo, los
diccionarios compartidos (CANVAS_DARK, ENTITY_COLORS) se MUTAN en el
sitio (así las importaciones por valor siguen viendo los nuevos tonos)
y los estilos ttk se reconfiguran. Los widgets tk concretos (Text,
Canvas, Menu…) se restilizan con `restyle_tk_tree(root)`.

API:
- set_mode("light" | "dark")  → cambia la paleta global (puro, sin Tk)
- apply(root, modo)           → paleta + fuentes + estilos ttk
- apply_dark_theme(root)      → compatibilidad (= apply(root, "dark"))
- current_mode() / toggle()   → estado y cambio rápido
- restyle_tk_tree(root)       → re-colorea widgets tk ya creados
- colors()                    → copia del diccionario de tokens actual
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Dict

# -- Tokens por modo -----------------------------------------------------------
# Claves: bg, bg_alt, raise, field, hover, border, text, text_dim,
#         accent, accent_dark, ok, warn, error, canvas, selection,
#         sel_bg, sel_fg + tokens del lienzo (space_fill, space_text,
#         wall, grid, axis, welcome_*).

PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#15171C", "bg_alt": "#1B1E24", "raise": "#242832",
        "field": "#2A2F3A", "hover": "#323846", "border": "#3A4150",
        "text": "#E9ECF1", "text_dim": "#A6ADBA", "accent": "#5B8DEF",
        "accent_dark": "#3E68B8", "ok": "#63D69B", "warn": "#F2C14E",
        "error": "#F07171", "canvas": "#101216", "selection": "#FF7A88",
        "sel_bg": "#3D5A96", "sel_fg": "#FFFFFF",
        "space_fill": "#1C2534", "space_text": "#C7CFDC",
        "wall": "#8B95A6", "grid": "#1E222B", "axis": "#39414F",
        "welcome_card": "#1D2129", "welcome_border": "#3E68B8",
        "welcome_title": "#5B8DEF", "welcome_text": "#A6ADBA",
        "tooltip_bg": "#1D2129", "tooltip_text": "#E9ECF1",
        "tooltip_border": "#3E68B8",
    },
    "light": {
        "bg": "#F4F6FA", "bg_alt": "#FFFFFF", "raise": "#E8EDF5",
        "field": "#FFFFFF", "hover": "#D8E1EE", "border": "#C4CFDD",
        "text": "#1C2733", "text_dim": "#5A6678", "accent": "#3B7DE0",
        "accent_dark": "#2B5FB8", "ok": "#1F9D61", "warn": "#B27B10",
        "error": "#D64545", "canvas": "#EEF1F6", "selection": "#E5484D",
        "sel_bg": "#3B7DE0", "sel_fg": "#FFFFFF",
        "space_fill": "#DCE9FB", "space_text": "#223042",
        "wall": "#4A5568", "grid": "#E3E8EF", "axis": "#BCC7D6",
        "welcome_card": "#FFFFFF", "welcome_border": "#2B5FB8",
        "welcome_title": "#2B5FB8", "welcome_text": "#5A6678",
        "tooltip_bg": "#FFFFFF", "tooltip_text": "#1C2733",
        "tooltip_border": "#2B5FB8",
    },
}

# Tokens de color de entidades por modo (mismos matices, luminosidad
# distinta para contrastar sobre cada lienzo).
_ENTITY_LIGHT: Dict[str, str] = {
    "space": "#3E6FB8", "wall": "#5A6678", "DOOR": "#B25E12",
    "WINDOW": "#0E7FA8", "OPENING": "#5A6678",
    "SPACE": "#3E6FB8", "BEAM": "#4A55C4", "COLUMN": "#6B3FBF",
    "BRACE": "#7A3FD0", "SLAB": "#5461C9", "TRUSS": "#6C50C4",
    "FOUNDATION": "#9A6416",
    "POWER": "#C43A30", "LIGHTING": "#9A6E00", "HVAC": "#0F8A5F",
    "WATER": "#2A64C8", "DRAINAGE": "#6B3FBF", "STORMWATER": "#0E7FA8",
    "GAS": "#C25517", "TELECOM": "#1B8A44", "CCTV": "#0E7FA8",
    "FIRE_ALARM": "#D64545", "INTRUSION": "#7A3FD0",
    "ACCESS_CONTROL": "#0F8A80", "PERIMETER": "#5F8A18",
    "DATA": "#1B8A44", "FIRE": "#D64545", "ELECTRICAL": "#C43A30",
    "SANITARY": "#2A64C8", "SECURITY": "#7A3FD0",
}
_ENTITY_DARK: Dict[str, str] = {
    "space": "#7FA6E8", "wall": "#8B95A6", "DOOR": "#F0A64B",
    "WINDOW": "#4FC3F7", "OPENING": "#B9C2CF",
    "SPACE": "#7FA6E8", "BEAM": "#8E9BFF", "COLUMN": "#B18CFF",
    "BRACE": "#C084FC", "SLAB": "#A5B4FC", "TRUSS": "#A78BFA",
    "FOUNDATION": "#D3A05C",
    "POWER": "#FF7B72", "LIGHTING": "#FFD166", "HVAC": "#4ED9A4",
    "WATER": "#5B9BF5", "DRAINAGE": "#B18CFF", "STORMWATER": "#54C1F0",
    "GAS": "#FF9457", "TELECOM": "#4ADE80", "CCTV": "#4DD0E1",
    "FIRE_ALARM": "#FF6B6B", "INTRUSION": "#C084FC",
    "ACCESS_CONTROL": "#2DD4BF", "PERIMETER": "#A3D65C",
    "DATA": "#6EE787", "FIRE": "#FF6B6B", "ELECTRICAL": "#FF7B72",
    "SANITARY": "#5B9BF5", "SECURITY": "#C084FC",
}

MODES = ("dark", "light")
_mode = "dark"

# Grosor del separador arrastrable de los ttk.PanedWindow (v3.7.0):
# con 10 px el borde se ve y se agarra sin puntería; antes el sash
# nativo de clam (3 px) era casi imposible de tomar con el ratón.
SASH_THICKNESS = 10

# -- Estado dinámico: constantes COL_* (se re-vinculan con set_mode) -----------

COL_BG = "#15171C"
COL_BG_ALT = "#1B1E24"
COL_RAISE = "#242832"
COL_FIELD = "#2A2F3A"
COL_HOVER = "#323846"
COL_BORDER = "#3A4150"
COL_TEXT = "#E9ECF1"
COL_TEXT_DIM = "#A6ADBA"
COL_ACCENT = "#5B8DEF"
COL_ACCENT_DARK = "#3E68B8"
COL_OK = "#63D69B"
COL_WARN = "#F2C14E"
COL_ERROR = "#F07171"
COL_CANVAS = "#101216"
COL_SELECTION = "#FF7A88"
SEL_BG = "#3D5A96"
SEL_FG = "#FFFFFF"

# Diccionarios compartidos: se MUTAN en el sitio para que las
# importaciones por valor (p. ej. `from ui.theme import CANVAS_DARK`)
# sigan refleando el modo activo.
CANVAS_DARK: Dict[str, str] = {
    "space_fill": "#1C2534", "space_text": "#C7CFDC", "wall": "#8B95A6",
    "grid": "#1E222B", "axis": "#39414F", "selection": "#FF7A88",
    "welcome_card": "#1D2129", "welcome_border": "#3E68B8",
    "welcome_title": "#5B8DEF", "welcome_text": "#A6ADBA",
}
ENTITY_COLORS: Dict[str, str] = dict(_ENTITY_DARK)

_TOKEN_TO_COL = {
    "bg": "COL_BG", "bg_alt": "COL_BG_ALT", "raise": "COL_RAISE",
    "field": "COL_FIELD", "hover": "COL_HOVER", "border": "COL_BORDER",
    "text": "COL_TEXT", "text_dim": "COL_TEXT_DIM", "accent": "COL_ACCENT",
    "accent_dark": "COL_ACCENT_DARK", "ok": "COL_OK", "warn": "COL_WARN",
    "error": "COL_ERROR", "canvas": "COL_CANVAS",
    "selection": "COL_SELECTION", "sel_bg": "SEL_BG", "sel_fg": "SEL_FG",
}

_CANVAS_KEYS = ("space_fill", "space_text", "wall", "grid", "axis",
                "selection", "welcome_card", "welcome_border",
                "welcome_title", "welcome_text")


def current_mode() -> str:
    """Modo activo: 'dark' o 'light'."""
    return _mode


def colors() -> Dict[str, str]:
    """Copia del diccionario de tokens del modo activo."""
    return dict(PALETTES[_mode])


def get(key: str) -> str:
    """Token del modo activo (p. ej. get('canvas'))."""
    return PALETTES[_mode][key]


def set_mode(mode: str) -> str:
    """Cambia la paleta global (puro, sin Tk). Devuelve el modo activo.

    - Re-vincula las constantes COL_* del módulo.
    - Muta CANVAS_DARK y ENTITY_COLORS en el sitio.
    """
    global _mode, COL_BG, COL_BG_ALT, COL_RAISE, COL_FIELD, COL_HOVER, \
        COL_BORDER, COL_TEXT, COL_TEXT_DIM, COL_ACCENT, COL_ACCENT_DARK, \
        COL_OK, COL_WARN, COL_ERROR, COL_CANVAS, COL_SELECTION, \
        SEL_BG, SEL_FG
    if mode not in PALETTES:
        mode = "dark"
    _mode = mode
    palette = PALETTES[mode]
    for token, col_name in _TOKEN_TO_COL.items():
        globals()[col_name] = palette[token]
    CANVAS_DARK.clear()
    for key in _CANVAS_KEYS:
        CANVAS_DARK[key] = palette[key]
    ENTITY_COLORS.clear()
    ENTITY_COLORS.update(_ENTITY_LIGHT if mode == "light"
                         else _ENTITY_DARK)
    return _mode


def toggle() -> str:
    """Alterna oscuro ↔ claro (puro). Devuelve el nuevo modo."""
    return set_mode("light" if _mode == "dark" else "dark")


# -- Fuentes -------------------------------------------------------------------

def _configure_fonts(root: tk.Tk) -> None:
    """Tipografía legible y amable (sin forzar familia inexistente)."""
    for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10),
                       ("TkFixedFont", 9), ("TkMenuFont", 10),
                       ("TkHeadingFont", 10)):
        try:
            f = tkfont.nametofont(name)
            f.configure(size=size)
        except Exception:  # noqa: BLE001 - fuente no disponible
            pass


# -- Aplicación de estilos ttk ---------------------------------------------------

def _style_ttk(style: ttk.Style, p: Dict[str, str]) -> None:
    style.configure(".", background=p["bg"], foreground=p["text"],
                    fieldbackground=p["field"], bordercolor=p["border"],
                    lightcolor=p["raise"], darkcolor=p["bg_alt"],
                    troughcolor=p["bg_alt"], focuscolor=p["accent"],
                    selectbackground=p["sel_bg"],
                    selectforeground=p["sel_fg"],
                    font=("TkTextFont", 10))

    # Frames / paneles
    style.configure("TFrame", background=p["bg"])
    style.configure("Panel.TFrame", background=p["bg_alt"])
    style.configure("Card.TFrame", background=p["raise"], relief="flat")
    style.configure("TPanedwindow", background=p["border"])
    # Sash ancho y del color del borde: se VÉ dónde se arrastra (v3.7.0).
    style.configure("Sash", sashthickness=SASH_THICKNESS,
                    background=p["border"])
    style.configure("TSeparator", background=p["border"])

    # Etiquetas
    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Dim.TLabel", background=p["bg"],
                    foreground=p["text_dim"])
    style.configure("Hint.TLabel", background=p["bg_alt"],
                    foreground=p["text_dim"], padding=(6, 2))
    style.configure("Title.TLabel", background=p["bg"],
                    foreground=p["text"], font=("TkDefaultFont", 12, "bold"))
    style.configure("Accent.TLabel", background=p["bg"],
                    foreground=p["accent"])
    style.configure("Guide.TLabel", background=p["raise"],
                    foreground=p["text"])

    # Botones
    # Botones compactos (v3.9.0): menos aire regalado al plano.
    style.configure("TButton", background=p["raise"], foreground=p["text"],
                    bordercolor=p["border"], focuscolor=p["accent"],
                    padding=(8, 4), relief="flat", borderradius=6)
    style.map("TButton",
              background=[("active", p["hover"]),
                          ("pressed", p["accent_dark"])],
              foreground=[("disabled", p["text_dim"])],
              bordercolor=[("focus", p["accent"])])
    style.configure("Accent.TButton", background=p["accent_dark"],
                    foreground=p["text"], padding=(10, 4))
    style.map("Accent.TButton",
              background=[("active", p["accent"]),
                          ("pressed", p["accent_dark"])])
    style.configure("Guide.TButton", background=p["raise"],
                    foreground=p["accent"], padding=(8, 4))
    style.map("Guide.TButton",
              background=[("active", p["hover"])],
              foreground=[("active", p["text"])])

    # Entradas y combinaciones
    style.configure("TEntry", fieldbackground=p["field"],
                    foreground=p["text"], insertcolor=p["text"],
                    bordercolor=p["border"], lightcolor=p["field"],
                    darkcolor=p["field"], padding=(6, 4))
    style.map("TEntry", bordercolor=[("focus", p["accent"])])
    style.configure("TCombobox", fieldbackground=p["field"],
                    background=p["raise"], foreground=p["text"],
                    arrowcolor=p["text"], bordercolor=p["border"],
                    lightcolor=p["field"], darkcolor=p["field"],
                    padding=(4, 2))
    style.map("TCombobox",
              fieldbackground=[("readonly", p["field"])],
              foreground=[("readonly", p["text"])],
              bordercolor=[("focus", p["accent"])])

    # Treeviews
    style.configure("Treeview", background=p["field"],
                    foreground=p["text"], fieldbackground=p["field"],
                    bordercolor=p["bg"], rowheight=22,
                    font=("TkTextFont", 10))
    style.map("Treeview",
              background=[("selected", p["sel_bg"])],
              foreground=[("selected", p["sel_fg"])])
    style.configure("Treeview.Heading", background=p["bg_alt"],
                    foreground=p["text_dim"], relief="flat",
                    font=("TkDefaultFont", 9, "bold"), padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", p["hover"])])

    # Notebook
    style.configure("TNotebook", background=p["bg"],
                    bordercolor=p["border"], tabmargins=(4, 3, 4, 0))
    style.configure("TNotebook.Tab", background=p["bg_alt"],
                    foreground=p["text_dim"], padding=(10, 4),
                    font=("TkDefaultFont", 9))
    style.map("TNotebook.Tab",
              background=[("selected", p["raise"])],
              foreground=[("selected", p["text"])])

    # Checkbuttons / Radiobuttons
    style.configure("TCheckbutton", background=p["bg"],
                    foreground=p["text"], focuscolor=p["accent"],
                    padding=(4, 2))
    style.map("TCheckbutton",
              background=[("active", p["bg"])],
              indicatorcolor=[("selected", p["accent"]),
                              ("!selected", p["field"])])
    style.configure("TRadiobutton", background=p["bg_alt"],
                    foreground=p["text"], focuscolor=p["accent"],
                    padding=(4, 2))
    style.map("TRadiobutton",
              background=[("active", p["bg_alt"])],
              indicatorcolor=[("selected", p["accent"]),
                              ("!selected", p["field"])])

    # Scrollbars discretas
    style.configure("Vertical.TScrollbar", background=p["raise"],
                    troughcolor=p["bg_alt"], bordercolor=p["bg_alt"],
                    arrowcolor=p["text_dim"], gripcount=0)
    style.configure("Horizontal.TScrollbar", background=p["raise"],
                    troughcolor=p["bg_alt"], bordercolor=p["bg_alt"],
                    arrowcolor=p["text_dim"], gripcount=0)


def _option_add(root: tk.Tk, p: Dict[str, str]) -> None:
    root.option_add("*TCombobox*Listbox.background", p["field"])
    root.option_add("*TCombobox*Listbox.foreground", p["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["sel_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["sel_fg"])
    root.option_add("*TCombobox*Listbox.font", ("TkTextFont", 10))
    root.option_add("*Menu.background", p["bg_alt"])
    root.option_add("*Menu.foreground", p["text"])
    root.option_add("*Menu.activeBackground", p["accent_dark"])
    root.option_add("*Menu.activeForeground", p["text"])
    root.option_add("*Menu.borderWidth", 0)


# Restablecimiento de widgets tk concretos (los ttk siguen al estilo).


def restyle_tk_tree(root: tk.Tk) -> int:
    """Re-colorea los widgets tk ya creados (Text, Canvas, Menu, Label…).

    Recorre el árbol de widgets y sustituye los colores del modo ANTERIOR
    por los del modo ACTIVO en las opciones que cada widget admita
    (prueba de error silenciosa: ttk no acepta configure directo y hay
    widgets que no exponen todas las opciones). Devuelve cuántos cambió.
    """
    p = PALETTES[_mode]
    prev = PALETTES["light" if _mode == "dark" else "dark"]
    color_map = {v: p[k] for k, v in prev.items() if k in p}
    count = 0
    stack: list = [root]
    while stack:
        widget = stack.pop()
        try:
            for child in widget.winfo_children():
                stack.append(child)
        except Exception:  # noqa: BLE001 - widget muerto
            continue
        try:
            if isinstance(widget, tk.Menu):
                widget.configure(background=p["bg_alt"],
                                 foreground=p["text"],
                                 activebackground=p["accent_dark"],
                                 activeforeground=p["text"],
                                 disabledforeground=p["text_dim"],
                                 borderwidth=0)
                count += 1
                continue
            keys = set(widget.keys()) if hasattr(widget, "keys") else set()
            wants: Dict[str, Any] = {}
            for option in ("background", "foreground", "insertbackground",
                           "highlightbackground", "highlightcolor"):
                if option not in keys:
                    continue
                current = widget.cget(option)
                if current in color_map:
                    wants[option] = color_map[current]
            if isinstance(widget, tk.Canvas):
                wants["background"] = p["canvas"]
            if wants:
                widget.configure(**wants)
                count += 1
        except Exception:  # noqa: BLE001 - opción no soportada por el widget
            continue
    return count


def apply(root: tk.Tk, mode: str = "dark") -> Dict[str, str]:
    """Aplica el modo ("dark"|"light") — antes de crear widgets o EN
    VIVO con la ventana ya construida. Devuelve el diccionario de tokens.
    """
    set_mode(mode)
    _configure_fonts(root)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # el más configurable multiplataforma
    except Exception:  # noqa: BLE001 - mantener el nativo
        pass
    p = PALETTES[_mode]
    root.configure(background=p["bg"])
    _option_add(root, p)
    _style_ttk(style, p)
    return colors()


def apply_dark_theme(root: tk.Tk) -> Dict[str, str]:
    """Compatibilidad v1.7.1-v2.8.0: aplica el modo oscuro."""
    return apply(root, "dark")


def menu_kwargs() -> Dict[str, Any]:
    """Argumentos de color para crear tk.Menu coherentes con el tema."""
    p = PALETTES[_mode]
    return dict(tearoff=0, background=p["bg_alt"], foreground=p["text"],
                activebackground=p["accent_dark"],
                activeforeground=p["text"],
                disabledforeground=p["text_dim"], borderwidth=0)


__all__ = [
    "PALETTES", "MODES", "current_mode", "set_mode", "toggle", "colors",
    "get", "apply", "apply_dark_theme", "menu_kwargs", "restyle_tk_tree",
    "CANVAS_DARK", "ENTITY_COLORS", "SASH_THICKNESS",
    "COL_BG", "COL_BG_ALT", "COL_RAISE", "COL_FIELD", "COL_HOVER",
    "COL_BORDER", "COL_TEXT", "COL_TEXT_DIM", "COL_ACCENT",
    "COL_ACCENT_DARK", "COL_OK", "COL_WARN", "COL_ERROR", "COL_CANVAS",
    "COL_SELECTION", "SEL_BG", "SEL_FG",
]
