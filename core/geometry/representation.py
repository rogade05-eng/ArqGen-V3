"""Capa de representación arquitectónica (v2.6.0).

Pensado como un arquitecto: del mismo modelo de variantes del
asistente salen ahora las vistas técnicas del proyecto —

* PLANTA: muros con HATCH según el material, columnas de la
  tipología, arcos de giro de puertas, símbolo de ventana, norte,
  cotas totales y escala gráfica.
* ELEVACIONES: las cuatro fachadas cardinales con vanos proyectados,
  aleros, remate de cubierta según clima y estilo, zócalo, líneas de
  nivel y terreno escalonado por el desnivel.
* CORTES: transversal y longitudinal por la circulación, con
  cimentación (zapata + sobre-cimiento), muros cortados, losas con
  vanos sobre patios y escaleras, escalera en sección, cubierta y
  cotas verticales.
* DETALLES CONSTRUCTIVOS: biblioteca de nodos por tipología
  (cimentación, coronamiento, esquina confinada, vanos, alero,
  nudo de pórtico, escalera) con acotado real.

Todas las vistas se describen con PRIMITIVAS en metros (eje Y hacia
arriba) para que Tkinter y el exportador SVG dibujen exactamente lo
mismo. Todo determinista: sin azar, sin dependencias nuevas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.geometry.engine import exposed_outline_segments

# --------------------------------------------------------------------------
# Primitivas de dibujo (unidades: metros, Y hacia arriba)
# --------------------------------------------------------------------------

DASH_ALERO = (0.45, 0.25)
DASH_EJE = (0.30, 0.18)
DASH_COTA = (0.12, 0.08)


@dataclass
class PLine:
    """Segmento de recta."""

    x1: float
    y1: float
    x2: float
    y2: float
    color: str = "#37474f"
    width: float = 1.0
    dash: Optional[Tuple[float, float]] = None
    tag: str = ""


@dataclass
class PRect:
    """Rectángulo axis-aligned (hatch = clave de trama o '')."""

    x: float
    y: float
    w: float
    d: float
    fill: str = ""
    stroke: str = "#37474f"
    stroke_width: float = 1.0
    dash: Optional[Tuple[float, float]] = None
    hatch: str = ""
    tag: str = ""


@dataclass
class PText:
    """Texto (size en metros, anchor: middle | start | end)."""

    x: float
    y: float
    text: str
    size: float = 0.22
    color: str = "#37474f"
    anchor: str = "middle"
    bold: bool = False
    tag: str = ""


@dataclass
class PArc:
    """Arco (grados, sentido antihorario desde start_deg)."""

    cx: float
    cy: float
    r: float
    start_deg: float
    extent_deg: float
    color: str = "#2e7d32"
    width: float = 1.0
    dash: Optional[Tuple[float, float]] = None
    tag: str = ""


Prim = Any


@dataclass
class Drawing:
    """Una vista completa: primitivas + título."""

    caption: str
    prims: List[Prim] = field(default_factory=list)

    def bounds(self) -> Tuple[float, float, float, float]:
        """Caja (x0, y0, x1, y1) de todo lo dibujado."""
        xs: List[float] = []
        ys: List[float] = []
        for prim in self.prims:
            if isinstance(prim, PLine):
                xs += [prim.x1, prim.x2]
                ys += [prim.y1, prim.y2]
            elif isinstance(prim, PRect):
                xs += [prim.x, prim.x + prim.w]
                ys += [prim.y, prim.y + prim.d]
            elif isinstance(prim, PText):
                pad = max(prim.size, 0.2)
                xs += [prim.x - pad, prim.x + pad * 6.0]
                ys += [prim.y - pad, prim.y + pad]
            elif isinstance(prim, PArc):
                xs += [prim.cx - prim.r, prim.cx + prim.r]
                ys += [prim.cy - prim.r, prim.cy + prim.r]
        if not xs:
            return (0.0, 0.0, 10.0, 10.0)
        return (min(xs), min(ys), max(xs), max(ys))


# --------------------------------------------------------------------------
# TRAMAS (HATCH) según el material del muro
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HatchPattern:
    """Trama de un material (planos y cortes)."""

    kind: str            # diagonal | aridos | veta | sillares | tramas |
                         # solido | ninguno
    spacing: float       # separación entre líneas (m)
    color: str
    label: str


HATCH_PATTERNS: Dict[str, HatchPattern] = {
    "mamposteria": HatchPattern("diagonal", 0.22, "#8d6e63",
                                "Mampostería de bloque (soga 45°)"),
    "hormigon": HatchPattern("aridos", 0.32, "#78909c",
                             "Hormigón armado (áridos)"),
    "madera": HatchPattern("veta", 0.14, "#a1887f",
                           "Madera (veta)"),
    "piedra": HatchPattern("sillares", 0.22, "#8d6e63",
                           "Piedra (sillares)"),
    "tierra": HatchPattern("tramas", 0.12, "#795548",
                           "Adobe/tapial (trama densa)"),
    "acero": HatchPattern("solido", 0.0, "#455a64",
                          "Acero (relleno sólido)"),
    "panel": HatchPattern("ninguno", 0.0, "#90a4ae",
                          "Panel sandwich (autorp.)"),
    "galvanizado": HatchPattern("diagonal", 0.45, "#90a4ae",
                                "Acero galvanizado ligero"),
}

HATCH_PARTICION = HatchPattern("ninguno", 0.0, "#b0bec5",
                               "Tabiquería (poché ligero)")

_HATCH_BY_TYPE = {
    "Mampostería de bloque + losa de vigueta": "mamposteria",
    "Hormigón armado (monolítico)": "hormigon",
    "Vigas y columnas prefabricadas": "hormigon",
    "Madera ligera": "madera",
    "Panel prefabricado (sandwich)": "panel",
    "Losa maciza de hormigón": "hormigon",
    "Estructura metálica (acero)": "acero",
    "Muros de piedra": "piedra",
    "Tierra (adobe o tapial)": "tierra",
    "Estructura ligera de acero galvanizado + panel": "galvanizado",
}


def hatch_key_for(construction_type: str) -> str:
    """Clave de trama de la tipología (reserva: mampostería)."""
    return _HATCH_BY_TYPE.get(construction_type, "mamposteria")


def hatch_pattern(construction_type: str) -> HatchPattern:
    return HATCH_PATTERNS[hatch_key_for(construction_type)]


def hatch_segments(x: float, y: float, w: float, d: float,
                   key: str) -> List[Tuple[Tuple[float, float],
                                           Tuple[float, float]]]:
    """Tramas RECORTADAS dentro del rectángulo del muro.

    Devuelve segmentos ((x1, y1), (x2, y2)) listos para línea; los
    puntos de las tramas de áridos se expresan como micro-segmentos.
    Determinista: barrido ordenado por la constante de la recta.
    """
    pattern = HATCH_PATTERNS.get(key)
    if pattern is None or w <= 1e-6 or d <= 1e-6:
        return []
    x0, x1, y0, y1 = x, x + w, y, y + d
    kind, spacing = pattern.kind, pattern.spacing
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

    if kind in ("solido", "ninguno"):
        return segs

    if kind == "diagonal":
        # Rectas 45°: x - y = c, de (x0 - y1) a (x1 - y0).
        c = x0 - y1
        c_max = x1 - y0
        while c <= c_max + 1e-9:
            t_lo = max(y0, x0 - c)
            t_hi = min(y1, x1 - c)
            if t_hi > t_lo:
                segs.append(((c + t_lo, t_lo), (c + t_hi, t_hi)))
            c += spacing

    elif kind == "veta":
        # Vetas paralelas al lado mayor del muro.
        if w >= d:
            yy = y0 + spacing / 2.0
            while yy < y1:
                segs.append(((x0, yy), (x1, yy)))
                yy += spacing
        else:
            xx = x0 + spacing / 2.0
            while xx < x1:
                segs.append(((xx, y0), (xx, y1)))
                xx += spacing

    elif kind == "aridos":
        # Diagonales anchas + puntos (micro-segmentos) entre líneas.
        c = x0 - y1
        c_max = x1 - y0
        while c <= c_max + 1e-9:
            t_lo = max(y0, x0 - c)
            t_hi = min(y1, x1 - c)
            if t_hi > t_lo:
                segs.append(((c + t_lo, t_lo), (c + t_hi, t_hi)))
            c += spacing
        gy = y0 + 0.25
        row = 0
        while gy < y1:
            gx = x0 + (0.25 if row % 2 == 0 else 0.5)
            while gx < x1:
                dx = min(0.02, x1 - gx)
                dy = min(0.02, y1 - gy)
                segs.append(((gx, gy), (gx + dx, gy + dy)))
                gx += 0.5
            gy += 0.45
            row += 1

    elif kind == "sillares":
        # Hiladas de sillares desplazadas (soga alterna).
        yy = y0 + spacing / 2.0
        row = 0
        while yy < y1:
            offset = (row % 2) * 0.26
            gx = x0 + offset
            while gx < x1:
                piece = min(0.42, x1 - gx)
                if piece > 0.05:
                    segs.append(((gx, yy), (gx + piece, yy)))
                gx += 0.52
            yy += spacing
            row += 1

    elif kind == "tramas":
        # Trama densa de trazos cortos 45° (adobe/tapial).
        gy = y0 + 0.06
        row = 0
        while gy < y1:
            gx = x0 + (0.0 if row % 2 == 0 else 0.08)
            while gx < x1:
                t = min(0.08, x1 - gx, y1 - gy)
                segs.append(((gx, gy), (gx + t, gy + t)))
                gx += spacing
            gy += spacing
            row += 1

    # Cap de seguridad para muros anómalamente grandes.
    return segs[:400]


# --------------------------------------------------------------------------
# Cubierta y losas según clima / estilo / tipología
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RoofProfile:
    """Perfil de cubierta decidido por estilo y clima."""

    kind: str            # plana | un_agua | dos_aguas
    slope: float         # pendiente m/m
    description: str


_STYLE_FLAT = ("High-tech", "Posmoderno", "Minimalista", "Brutalista",
               "Racionalista")
_STYLE_PITCHED = ("Colonial cubano", "Vernáculo tropical", "Orgánico",
                  "Sostenible (bioclimático)", "Ecléctico", "Modernista")


def roof_profile(data) -> RoofProfile:
    """Cubierta coherente con el estilo y el clima del proyecto."""
    style = getattr(data, "architectural_style", "")
    climate = getattr(data, "climate", "")
    if style in _STYLE_FLAT:
        kind = "plana"
    elif style in _STYLE_PITCHED:
        kind = "un_agua" if climate.startswith("Cálido") else "dos_aguas"
    elif climate.startswith("Cálido húmedo") or climate.startswith("Frío") \
            or climate.startswith("Alta montaña"):
        kind = "dos_aguas"
    else:
        kind = "plana"
    slope = {"plana": 0.02, "un_agua": 0.15, "dos_aguas": 0.30}[kind]
    names = {"plana": "Plana con parapeto (pendiente 2 %)",
             "un_agua": "A un agua (pendiente 15 %)",
             "dos_aguas": "A dos aguas (pendiente 30 %)"}
    return RoofProfile(kind=kind, slope=slope, description=names[kind])


SLAB_THICKNESS: Dict[str, float] = {
    "Mampostería de bloque + losa de vigueta": 0.30,
    "Hormigón armado (monolítico)": 0.25,
    "Vigas y columnas prefabricadas": 0.30,
    "Madera ligera": 0.12,
    "Panel prefabricado (sandwich)": 0.10,
    "Losa maciza de hormigón": 0.25,
    "Estructura metálica (acero)": 0.15,
    "Muros de piedra": 0.30,
    "Tierra (adobe o tapial)": 0.25,
    "Estructura ligera de acero galvanizado + panel": 0.12,
}

PARAPET_M = 0.30
FOUNDATION_DEPTH_M = 0.90      # fondo de zapata bajo el nivel 0
GROUND_LINE_M = -0.30          # línea de terreno (sobre-cimiento visto)


def slab_thickness(construction_type: str) -> float:
    return SLAB_THICKNESS.get(construction_type, 0.25)


# --------------------------------------------------------------------------
# Clasificación de muros: envolvente (hatch de material) vs partición
# --------------------------------------------------------------------------

def exterior_wall_flags(layout, tol: float = 0.06) -> List[bool]:
    """True si el muro coincide con el contorno EXPUESTO del nivel.

    Los muros de envolvente (incluidos los que dan a un patio) llevan
    la trama del material; las particiones interiores van en poché.
    """
    rooms = layout.all_rooms
    outline = exposed_outline_segments(rooms)
    h_lines: List[Tuple[float, float, float]] = []   # (y, x0, x1)
    v_lines: List[Tuple[float, float, float]] = []   # (x, y0, y1)
    for x1, y1, x2, y2, _nx, _ny in outline:
        if abs(y1 - y2) <= tol:
            h_lines.append((round(y1, 3), min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) <= tol:
            v_lines.append((round(x1, 3), min(y1, y2), max(y1, y2)))
    flags: List[bool] = []
    for wall in layout.walls:
        (sx, sy), (ex, ey) = wall["start"], wall["end"]
        if abs(sy - ey) <= 1e-6:                     # horizontal
            lo, hi = min(sx, ex), max(sx, ex)
            hit = any(abs(sy - ly) <= tol and hi - lo >= 0.35
                      and lo < lx1 - tol and hi > lx0 + tol
                      for ly, lx0, lx1 in h_lines
                      if min(hi, lx1) - max(lo, lx0) >= 0.35)
        else:                                        # vertical
            lo, hi = min(sy, ey), max(sy, ey)
            hit = any(abs(sx - lx) <= tol and hi - lo >= 0.35
                      for lx, ly0, ly1 in v_lines
                      if min(hi, ly1) - max(lo, ly0) >= 0.35)
        flags.append(bool(hit))
    return flags


def wall_rect(wall: Dict[str, Any], thickness: float
              ) -> Tuple[float, float, float, float]:
    """Rect (x, y, w, d) del muro fusionado (axis-aligned)."""
    (sx, sy), (ex, ey) = wall["start"], wall["end"]
    if abs(sy - ey) <= 1e-6:                         # horizontal
        lo, hi = min(sx, ex), max(sx, ex)
        return (lo, sy - thickness / 2.0, hi - lo, thickness)
    lo, hi = min(sy, ey), max(sy, ey)
    return (sx - thickness / 2.0, lo, thickness, hi - lo)


def _layout_bounds(layouts: Sequence[Any]) -> Tuple[float, float, float,
                                                     float]:
    xs: List[float] = []
    ys: List[float] = []
    for layout in layouts:
        for pr in layout.all_rooms:
            xs += [pr.x, pr.x + pr.w]
            ys += [pr.y, pr.y + pr.d]
    if not xs:
        return (0.0, 0.0, 10.0, 10.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _opening_room(layout, opening) -> Optional[Any]:
    """Local anfitrión del vano (por la nota «entre X y Y» o el muro)."""
    note = getattr(opening, "note", "") or ""
    if "entre" in note:
        name = note.split("entre", 1)[1].split("y", 1)[0].strip(" «»")
        for pr in layout.all_rooms:
            if pr.name == name:
                return pr
    return None


# --------------------------------------------------------------------------
# ELEVACIONES (fachadas cardinales)
# --------------------------------------------------------------------------

ELEVATION_SIDES = ("Norte", "Sur", "Este", "Oeste")

# (eje del plano de fachada, es el máximo?, eje longitudinal, espejo)
_FACADE_GEOM = {
    "Norte": ("y", True, "x", False),
    "Sur": ("y", False, "x", True),
    "Este": ("x", True, "y", False),
    "Oeste": ("x", False, "y", True),
}


def _facade_touches(pr, side: str, plane: float, tol: float = 0.06) -> bool:
    if side == "Norte":
        return abs(pr.y + pr.d - plane) <= tol
    if side == "Sur":
        return abs(pr.y - plane) <= tol
    if side == "Este":
        return abs(pr.x + pr.w - plane) <= tol
    return abs(pr.x - plane) <= tol


def _facade_wall_on(wall: Dict[str, Any], side: str, plane: float,
                    tol: float = 0.06) -> bool:
    (sx, sy), (ex, ey) = wall["start"], wall["end"]
    if side in ("Norte", "Sur"):
        if abs(sy - ey) > 1e-6:
            return False
        return abs(sy - plane) <= tol
    if abs(sx - ex) > 1e-6:
        return False
    return abs(sx - plane) <= tol


def elevation_view(variant, data, side: str = "Norte") -> Drawing:
    """Elevación de una fachada cardinal del edificio.

    Proyecta los vanos de los muros que dan a esa fachada, apila los
    niveles, dibuja zócalo, terreno (escalonado si hay desnivel),
    remate de cubierta según clima/estilo y el alero. «(frente)» marca
    la fachada principal elegida en el paso 1.
    """
    if side not in ELEVATION_SIDES:
        side = "Norte"
    layouts = list(variant.layouts)
    x0, y0, x1, y1 = _layout_bounds(layouts)
    plane_axis, is_max, along_axis, mirror = _FACADE_GEOM[side]
    plane = (y1 if plane_axis == "y" else x1) if is_max \
        else (y0 if plane_axis == "y" else x0)
    a0 = x0 if along_axis == "x" else y0
    a1 = x1 if along_axis == "x" else y1
    width = max(a1 - a0, 1.0)

    def along_of(value: float) -> float:
        return (value - a0) if not mirror else (a1 - value)

    def room_span(pr) -> Tuple[float, float]:
        if along_axis == "x":
            lo, hi = pr.x, pr.x + pr.w
        else:
            lo, hi = pr.y, pr.y + pr.d
        lo_a, hi_a = along_of(lo), along_of(hi)
        return (min(lo_a, hi_a), max(lo_a, hi_a))

    heights = [float(lvl.height_m) for lvl in data.levels] or [3.0]
    floors = [0.0]
    for h in heights[:-1]:
        floors.append(floors[-1] + h)
    top_h = floors[-1] + heights[-1]
    profile = roof_profile(data)
    ridge_h = top_h + profile.slope * max(0.0, (
        (y1 - y0) if plane_axis == "x" else (x1 - x0))) / 2.0

    prims: List[Prim] = []
    facade = "frente" if side == data.facade_orientation or (
        data.facade_orientation.startswith(side[:3])) else "lateral"

    # Cara de la fachada y zócalo.
    prims.append(PRect(0.0, 0.0, width, top_h, fill="#f5f1e8",
                       stroke="#8d6e63", stroke_width=1.2))
    prims.append(PRect(0.0, GROUND_LINE_M, width, -GROUND_LINE_M,
                       fill="#d7ccc8", stroke="#5d4037",
                       stroke_width=1.0, tag="zocalo"))

    # Terreno: línea a -0.30 con escalones donde el piso se eleva.
    terrain: List[Tuple[float, float, float]] = []
    for layout in layouts:
        for pr in layout.all_rooms:
            if _facade_touches(pr, side, plane) and pr.floor_rise_m > 0.01:
                terrain.append((*room_span(pr), pr.floor_rise_m))
    terrain.sort()
    merged: List[List[float]] = []
    for lo, hi, rise in terrain:
        if merged and lo <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], hi)
            merged[-1][2] = max(merged[-1][2], rise)
        else:
            merged.append([lo, hi, rise])
    gx = 0.0
    for lo, hi, rise in merged:
        if lo > gx:
            prims.append(PLine(gx, GROUND_LINE_M, lo, GROUND_LINE_M,
                               color="#5d4037", width=1.6, tag="terreno"))
        prims.append(PLine(lo, GROUND_LINE_M, lo, GROUND_LINE_M + rise,
                           color="#5d4037", width=1.6, tag="terreno"))
        prims.append(PLine(lo, GROUND_LINE_M + rise, hi,
                           GROUND_LINE_M + rise,
                           color="#5d4037", width=1.6, tag="terreno"))
        gx = hi
    prims.append(PLine(gx, GROUND_LINE_M, width, GROUND_LINE_M,
                       color="#5d4037", width=1.6, tag="terreno"))
    if gx < width:            # relleno tras el último escalón
        prims.append(PLine(gx, GROUND_LINE_M + (merged[-1][2] if merged
                           else 0.0), width, GROUND_LINE_M,
                           color="#5d4037", width=1.0, dash=DASH_EJE,
                           tag="terreno"))

    # Vanos proyectados por nivel.
    for index, layout in enumerate(layouts):
        base_floor = floors[min(index, len(floors) - 1)]
        for wall_index, wall in enumerate(layout.walls):
            if not _facade_wall_on(wall, side, plane):
                continue
            (sx, sy), (ex, ey) = wall["start"], wall["end"]
            for opening in list(layout.doors) + list(layout.windows):
                if opening.wall_index != wall_index:
                    continue
                start_along = along_of(sx if along_axis == "x" else sy)
                a_lo = min(start_along,
                           start_along + opening.width_m *
                           (1.0 if not mirror else -1.0))
                host = _opening_room(layout, opening)
                rise = host.floor_rise_m if host is not None else 0.0
                if opening.is_door:
                    z0 = base_floor + rise
                else:
                    z0 = base_floor + rise + opening.sill_height_m
                prims.append(PRect(a_lo, z0, opening.width_m,
                                   opening.height_m, fill="#ffffff",
                                   stroke="#37474f", stroke_width=1.4,
                                   tag="vano"))
                if not opening.is_door:
                    mx = a_lo + opening.width_m / 2.0
                    prims.append(PLine(mx, z0, mx, z0 + opening.height_m,
                                       color="#37474f", width=0.8,
                                       tag="vano"))
        # Línea de nivel interior (forjado) entre niveles.
        if index >= 1:
            z = floors[min(index, len(floors) - 1)]
            prims.append(PLine(0.0, z, width, z, color="#8d6e63",
                               width=0.8, dash=DASH_EJE, tag="nivel"))

    # Remate: parapeto / cumbrera + alero.
    if profile.kind == "plana":
        prims.append(PRect(-0.05, top_h, width + 0.10, PARAPET_M,
                           fill="#e0e0e0", stroke="#546e7a",
                           stroke_width=1.2, tag="cubierta"))
    else:
        prims.append(PLine(0.0, top_h, width, top_h, color="#546e7a",
                           width=1.6, tag="cubierta"))
        prims.append(PLine(0.0, ridge_h, width, ridge_h,
                           color="#546e7a", width=1.0, dash=DASH_EJE,
                           tag="cubierta"))
        prims.append(PText(width / 2.0, ridge_h + 0.25,
                           f"cumbrera {ridge_h:.2f} m".replace(".", ","),
                           size=0.20, color="#546e7a", tag="cubierta"))
    if data.protection_solar and data.eaves_m > 0:
        z_alero = top_h + (PARAPET_M if profile.kind == "plana" else 0.0)
        prims.append(PLine(-data.eaves_m, z_alero,
                           width + data.eaves_m, z_alero,
                           color="#b45309", width=1.6, dash=DASH_ALERO,
                           tag="alero"))

    # Cotas verticales de nivel (a la derecha).
    dim_x = width + 0.55
    prims.append(PLine(dim_x, 0.0, dim_x, top_h, color="#455a64",
                       width=0.8, dash=DASH_COTA, tag="cota"))
    for index, z in enumerate(floors + [top_h]):
        if z <= 0:
            continue
        prims.append(PLine(dim_x - 0.12, z, dim_x + 0.12, z,
                           color="#455a64", width=0.8, tag="cota"))
        if index < len(floors):
            prims.append(PText(dim_x + 0.22, z + 0.16,
                               f"{heights[min(index, len(heights) - 1)]:.2f}"
                               .replace(".", ","), size=0.18,
                               anchor="start", tag="cota"))
    prims.append(PText(0.0, -0.95,
                       f"ELEVACIÓN {side.upper()} ({facade}) · "
                       f"cubierta: {profile.description}",
                       size=0.26, anchor="start", bold=True,
                       tag="titulo"))
    return Drawing(caption=f"Elevación {side}", prims=prims)


# --------------------------------------------------------------------------
# CORTES (transversal / longitudinal)
# --------------------------------------------------------------------------

SECTION_AXES = ("Transversal", "Longitudinal")


def _cut_coordinate(layouts, data, axis: str) -> float:
    """Coordenada del plano de corte.

    Transversal: plano perpendicular al pasillo (recorre el edificio
    de fachada a fachada pasando por la escalera o el local mayor).
    Longitudinal: plano paralelo al pasillo, por su centro.
    """
    x0, y0, x1, y1 = _layout_bounds(layouts)
    if axis == "Transversal":
        # Plano paralelo al eje Y: por la escalera o el local mayor.
        best_room: Optional[Any] = None
        for layout in layouts:
            for pr in layout.all_rooms:
                if pr.space_type == "STAIR":
                    return pr.x + pr.w / 2.0
                if best_room is None or pr.area_m2() > best_room.area_m2():
                    best_room = pr
        if best_room is not None:
            return best_room.x + best_room.w / 2.0
        return (x0 + x1) / 2.0
    # Longitudinal: plano paralelo al eje X, por el pasillo.
    best: Optional[Tuple[float, float]] = None
    for layout in layouts:
        for corridor in ([layout.corridor] if layout.corridor else []) \
                + list(layout.extra_corridors):
            length = corridor.w
            center = corridor.y + corridor.d / 2.0
            if best is None or length > best[0]:
                best = (length, center)
    return best[1] if best else (y0 + y1) / 2.0


def _spans_union(intervals: Sequence[Tuple[float, float]],
                 gap: float = 0.05) -> List[Tuple[float, float]]:
    """Unión ordenada de intervalos (para losas y huecos)."""
    out: List[List[float]] = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(lo, hi) for lo, hi in out]


def section_view(variant, data, axis: str = "Transversal") -> Drawing:
    """Corte del edificio con cimentación, losas, vanos y cubierta.

    Transversal: plano perpendicular al pasillo (de fachada a fachada,
    por la escalera o el local mayor). Longitudinal: plano paralelo
    al pasillo por su centro. Muestra zapatas, sobre-cimientos, muros
    cortados con sus vanos, losas escalonadas por el desnivel (con
    vanos sobre patios y escaleras), la escalera en sección y la
    cubierta.
    """
    if axis not in SECTION_AXES:
        axis = "Transversal"
    layouts = list(variant.layouts)
    x0, y0, x1, y1 = _layout_bounds(layouts)
    # Transversal: el eje del dibujo es Y (profundidad).
    # Longitudinal: el eje del dibujo es X (longitud).
    span_lo, span_hi = (y0, y1) if axis == "Transversal" else (x0, x1)
    span = max(span_hi - span_lo, 1.0)
    cut = _cut_coordinate(layouts, data, axis)
    thickness = data.wall_thickness_m
    slab_t = slab_thickness(data.construction_type)
    profile = roof_profile(data)
    eaves = data.eaves_m if data.protection_solar else 0.0

    heights = [float(lvl.height_m) for lvl in data.levels] or [3.0]
    floors = [0.0]
    for h in heights[:-1]:
        floors.append(floors[-1] + h)

    prims: List[Prim] = []

    # Terreno con dientes de hacha.
    prims.append(PLine(-0.4, GROUND_LINE_M, span + 0.4, GROUND_LINE_M,
                       color="#5d4037", width=1.6, tag="terreno"))
    gx = -0.4
    while gx < span + 0.4:
        prims.append(PLine(gx, GROUND_LINE_M, gx - 0.12,
                           GROUND_LINE_M - 0.14, color="#5d4037",
                           width=0.7, tag="terreno"))
        gx += 0.35

    # Huecos globales: patios y escaleras de CUALQUIER nivel abren las
    # losas superiores (el hueco de escalera sube hasta la cubierta).
    global_patios = [(pr.x, pr.y, pr.w, pr.d)
                     for layout in layouts for pr in layout.all_rooms
                     if pr.space_type == "PATIO"]
    global_stairs = [(pr.x, pr.y, pr.w, pr.d)
                     for layout in layouts for pr in layout.all_rooms
                     if pr.space_type == "STAIR"]

    def _void_intervals(layout, along_range,
                        level_index: int) -> List[Tuple[float, float]]:
        """Huecos de losa: patios (siempre) y escaleras (desde el
        nivel 2: el piso del arranque es sólido)."""
        voids: List[Tuple[float, float]] = []
        rects = [(rx, ry, rw, rd) for rx, ry, rw, rd in global_patios]
        if level_index >= 1:
            rects += [(rx, ry, rw, rd) for rx, ry, rw, rd in global_stairs]
        for rx, ry, rw, rd in rects:
            if axis == "Transversal":
                inside = rx - thickness / 2 <= cut <= rx + rw \
                    + thickness / 2
                span_of = (ry, ry + rd)
            else:
                inside = ry - thickness / 2 <= cut <= ry + rd \
                    + thickness / 2
                span_of = (rx, rx + rw)
            if inside:
                voids.append((max(span_of[0], along_range[0]),
                              min(span_of[1], along_range[1])))
        return [v for v in voids if v[1] > v[0]]

    for index, layout in enumerate(layouts):
        z_floor = floors[min(index, len(floors) - 1)]
        z_top = z_floor + heights[min(index, len(heights) - 1)]

        # --- Muros cortados (perpendiculares al plano) + cimentación.
        for wall_index, wall in enumerate(layout.walls):
            (sx, sy), (ex, ey) = wall["start"], wall["end"]
            horizontal = abs(sy - ey) <= 1e-6
            if axis == "Transversal":
                # El eje del dibujo es Y: se cortan los muros HORIZONTALES
                # (que cruzan el plano vertical x = cut de lado a lado).
                is_cut = horizontal and \
                    min(sx, ex) - thickness / 2 <= cut <= \
                    max(sx, ex) + thickness / 2
                fixed = sy
            else:
                is_cut = (not horizontal) and \
                    min(sy, ey) - thickness / 2 <= cut <= \
                    max(sy, ey) + thickness / 2
                fixed = sx
            if not is_cut:
                continue
            px = fixed - span_lo

            # Zapata + sobre-cimiento bajo el muro cortado.
            foot_w = max(0.60, 2.2 * thickness)
            prims.append(PRect(px - foot_w / 2.0, -FOUNDATION_DEPTH_M,
                               foot_w, FOUNDATION_DEPTH_M - GROUND_LINE_M,
                               fill="#eceff1", stroke="#455a64",
                               stroke_width=1.0, hatch="hormigon",
                               tag="cimentacion"))
            prims.append(PRect(px - thickness / 2.0, GROUND_LINE_M,
                               thickness, -GROUND_LINE_M,
                               fill="#f5f1e8", stroke="#455a64",
                               stroke_width=1.0, tag="sobrecimiento"))

            # Pilar/muro cortado del piso a la losa.
            prims.append(PRect(px - thickness / 2.0, z_floor, thickness,
                               z_top - z_floor, fill="#e8e2d5",
                               stroke="#37474f", stroke_width=1.2,
                               tag="muro"))

            # Vanos del muro cortado (huecos blancos).
            for opening in list(layout.doors) + list(layout.windows):
                if opening.wall_index != wall_index:
                    continue
                host = _opening_room(layout, opening)
                rise = host.floor_rise_m if host is not None else 0.0
                if opening.is_door:
                    z0 = z_floor + rise
                else:
                    z0 = z_floor + rise + opening.sill_height_m
                prims.append(PRect(px - thickness / 2.0 - 0.01, z0,
                                   thickness + 0.02, opening.height_m,
                                   fill="#ffffff", stroke="#37474f",
                                   stroke_width=1.0, tag="vano"))

            # Muro proyectado al fondo (paralelo al plano, cercano).
            for wall_b in layout.walls:
                (bx1, by1), (bx2, by2) = wall_b["start"], wall_b["end"]
                bh = abs(by1 - by2) <= 1e-6
                parallel = (not bh) if axis == "Transversal" else bh
                near = (abs(bx1 - cut) <= 2.0 if axis == "Transversal"
                        else abs(by1 - cut) <= 2.0)
                if parallel and near:
                    if axis == "Transversal":
                        ux0 = min(by1, by2) - span_lo
                        ux1 = max(by1, by2) - span_lo
                    else:
                        ux0 = min(bx1, bx2) - span_lo
                        ux1 = max(bx1, bx2) - span_lo
                    prims.append(PRect(ux0, z_floor, ux1 - ux0,
                                       z_top - z_floor, fill="",
                                       stroke="#b0bec5", stroke_width=0.7,
                                       dash=DASH_EJE, tag="fondo"))
                    break

        # --- Losas escalonadas con huecos (patios / escaleras).
        rises = sorted({round(pr.floor_rise_m, 3)
                        for pr in layout.all_rooms})
        for rise in rises:
            rooms_at = [pr for pr in layout.all_rooms
                        if round(pr.floor_rise_m, 3) == rise]
            intervals = []
            for pr in rooms_at:
                if axis == "Transversal":
                    intervals.append((pr.y, pr.y + pr.d))
                else:
                    intervals.append((pr.x, pr.x + pr.w))
            z_slab = z_floor + rise + heights[min(index, len(heights) - 1)]
            for lo, hi in _spans_union(intervals):
                # Resta de huecos: trocea el intervalo.
                cursor = lo
                voids = sorted(_void_intervals(layout, (lo, hi), index))
                for v_lo, v_hi in voids:
                    if v_lo > cursor + 0.05:
                        prims.append(PRect(cursor - span_lo,
                                           z_slab - slab_t,
                                           v_lo - cursor, slab_t,
                                           fill="#eceff1", stroke="#546e7a",
                                           stroke_width=1.0,
                                           hatch="hormigon",
                                           tag="losa"))
                    cursor = max(cursor, v_hi)
                if hi > cursor + 0.05:
                    prims.append(PRect(cursor - span_lo,
                                       z_slab - slab_t, hi - cursor,
                                       slab_t, fill="#eceff1",
                                       stroke="#546e7a", stroke_width=1.0,
                                       hatch="hormigon", tag="losa"))

        # --- Escalera en sección (zigzag de contrahuellas).
        for pr in layout.all_rooms:
            if pr.space_type != "STAIR":
                continue
            if axis == "Transversal":
                inside = pr.x - thickness / 2 <= cut <= pr.x + pr.w \
                    + thickness / 2
            else:
                inside = pr.y - thickness / 2 <= cut <= pr.y + pr.d \
                    + thickness / 2
            if not inside:
                continue
            run_lo = (pr.y if axis == "Transversal" else pr.x) - span_lo
            run_len = pr.d if axis == "Transversal" else pr.w
            riser, tread = 0.175, 0.28
            steps = int(min((heights[min(index, len(heights) - 1)])
                            / riser, run_len / tread))
            if steps < 2:
                continue
            z0 = z_floor + pr.floor_rise_m
            sx_, sy_ = run_lo, z0
            for _step in range(steps):
                prims.append(PLine(sx_, sy_, sx_ + tread, sy_,
                                   color="#37474f", width=1.2,
                                   tag="escalera"))
                sy_ += riser
                prims.append(PLine(sx_ + tread, sy_ - riser,
                                   sx_ + tread, sy_, color="#37474f",
                                   width=1.2, tag="escalera"))
                sx_ += tread
            prims.append(PLine(run_lo, z0, sx_, sy_, color="#b45309",
                               width=0.9, dash=DASH_EJE, tag="escalera"))

    # --- Cubierta.
    z_roof = floors[-1] + heights[-1]
    rises_top = sorted({round(pr.floor_rise_m, 3)
                        for pr in layouts[-1].all_rooms}) \
        if layouts else [0.0]
    for rise in rises_top:
        rooms_at = [pr for pr in layouts[-1].all_rooms
                    if round(pr.floor_rise_m, 3) == rise
                    and pr.space_type != "PATIO"]
        if not rooms_at:
            continue
        if axis == "Transversal":
            intervals = [(pr.y - span_lo, pr.y + pr.d - span_lo)
                         for pr in rooms_at]
        else:
            intervals = [(pr.x - span_lo, pr.x + pr.w - span_lo)
                         for pr in rooms_at]
        z_slab = z_roof + rise
        for lo, hi in _spans_union(intervals):
            if profile.kind == "plana":
                prims.append(PRect(lo, z_slab, hi - lo, slab_t,
                                   fill="#eceff1", stroke="#546e7a",
                                   stroke_width=1.0, hatch="hormigon",
                                   tag="cubierta"))
                prims.append(PRect(lo, z_slab + slab_t, 0.20, PARAPET_M,
                                   fill="#e0e0e0", stroke="#546e7a",
                                   stroke_width=1.0, tag="parapeto"))
                prims.append(PRect(hi - 0.20, z_slab + slab_t, 0.20,
                                   PARAPET_M, fill="#e0e0e0",
                                   stroke="#546e7a", stroke_width=1.0,
                                   tag="parapeto"))
            elif profile.kind == "dos_aguas":
                apex = (span_lo + span_hi) / 2.0 - span_lo
                slope_h = profile.slope * (span_hi - span_lo) / 2.0
                prims.append(PLine(lo - eaves, z_slab, apex, z_slab
                                   + slope_h, color="#546e7a", width=1.6,
                                   tag="cubierta"))
                prims.append(PLine(apex, z_slab + slope_h, hi + eaves,
                                   z_slab, color="#546e7a", width=1.6,
                                   tag="cubierta"))
            else:  # un_agua: sube hacia el fondo (y máximo)
                z_back = z_slab + profile.slope * (span_hi - span_lo)
                if axis == "Longitudinal":
                    prims.append(PLine(lo - eaves, z_slab, hi + eaves,
                                       z_slab, color="#546e7a", width=1.6,
                                       tag="cubierta"))
                    prims.append(PLine(lo, z_back, hi, z_back,
                                       color="#546e7a", width=0.9,
                                       dash=DASH_EJE, tag="cubierta"))
                else:
                    prims.append(PLine(lo - eaves, z_slab, hi + eaves,
                                       z_back, color="#546e7a", width=1.6,
                                       tag="cubierta"))

    # --- Cotas verticales (derecha) y nombres de nivel (izquierda).
    dim_x = span + 0.55
    prims.append(PLine(dim_x, 0.0, dim_x, z_roof, color="#455a64",
                       width=0.8, dash=DASH_COTA, tag="cota"))
    for index, z in enumerate(floors + [z_roof]):
        prims.append(PLine(dim_x - 0.12, z, dim_x + 0.12, z,
                           color="#455a64", width=0.8, tag="cota"))
    for index, layout in enumerate(layouts):
        z = floors[min(index, len(floors) - 1)]
        prims.append(PText(-0.35, z + 0.18, layout.level_name, size=0.20,
                           anchor="end", tag="nivel"))
    prims.append(PText(0.0, -1.35,
                       f"CORTE {axis.upper()} (A-A') · corte por la "
                       f"circulación · cubierta: {profile.description}",
                       size=0.26, anchor="start", bold=True, tag="titulo"))
    return Drawing(caption=f"Corte {axis}", prims=prims)


# --------------------------------------------------------------------------
# PLANTA COMPLETA (para SVG y render genérico)
# --------------------------------------------------------------------------

def _north_angle(facade_orientation: str) -> float:
    """Ángulo de la flecha de norte (0° = arriba) según la fachada.

    La convención es girar la lámina para que la fachada principal
    quede mirando al espectador (abajo): Norte 0°, Sur 180°,
    Este 90°, Oeste -90°; las diagonales van al cardinal más próximo.
    """
    first = facade_orientation[:3]
    return {"Nor": 0.0, "Sur": 180.0, "Est": 90.0, "Oes": -90.0}.get(
        first, 0.0)


def _door_arc(layout, opening, wall, thickness: float
              ) -> Tuple[Optional[PArc], Optional[PLine]]:
    """Arco de giro de una puerta hacia el local vecino mayor."""
    (sx, sy), (ex, ey) = wall["start"], wall["end"]
    horizontal = abs(sy - ey) <= 1e-6
    if horizontal:
        px, py = sx + opening.offset_m, sy
        center = px + opening.width_m / 2.0
    else:
        px, py = sx, sy + opening.offset_m
        center = py + opening.width_m / 2.0

    # Locales vecinos a ambos lados del muro.
    above: List[Any] = []
    for pr in layout.all_rooms:
        if horizontal:
            if abs(pr.y + pr.d - sy) <= thickness and \
                    pr.x - 0.05 <= center <= pr.x + pr.w + 0.05:
                above.append((pr, "up"))
            elif abs(pr.y - sy) <= thickness and \
                    pr.x - 0.05 <= center <= pr.x + pr.w + 0.05:
                above.append((pr, "down"))
        else:
            if abs(pr.x + pr.w - sx) <= thickness and \
                    pr.y - 0.05 <= center <= pr.y + pr.d + 0.05:
                above.append((pr, "right"))
            elif abs(pr.x - sx) <= thickness and \
                    pr.y - 0.05 <= center <= pr.y + pr.d + 0.05:
                above.append((pr, "left"))
    if not above:
        return None, None
    pr, sense = max(above, key=lambda item: item[0].area_m2())
    radius = opening.width_m
    hinge_at_lo = True      # bisagra en el extremo inicial del vano
    if horizontal:
        cx, cy = px, py
        if sense == "up":
            start, ext = (0.0, 90.0) if hinge_at_lo else (90.0, 90.0)
            leaf_end = (cx + radius, cy) if hinge_at_lo \
                else (cx, cy + radius)
        else:
            start, ext = (270.0, 90.0) if hinge_at_lo else (180.0, 90.0)
            leaf_end = (cx, cy - radius) if hinge_at_lo \
                else (cx + radius, cy)
    else:
        cx, cy = px, py
        if sense == "right":
            start, ext = (270.0, 90.0) if hinge_at_lo else (0.0, 90.0)
            leaf_end = (cx, cy + radius) if hinge_at_lo \
                else (cx + radius, cy)
        else:
            start, ext = (180.0, 90.0) if hinge_at_lo else (90.0, 90.0)
            leaf_end = (cx - radius, cy) if hinge_at_lo \
                else (cx, cy - radius)
    arc = PArc(cx, cy, radius, start, ext, color="#2e7d32",
               width=0.8, dash=DASH_COTA, tag="arco")
    leaf = PLine(cx, cy, leaf_end[0], leaf_end[1], color="#2e7d32",
                 width=1.0, tag="arco")
    return arc, leaf


def plan_view(variant, data, level_index: int = 0) -> Drawing:
    """Planta técnica completa del nivel (para SVG y render genérico).

    Incluye: locales rotulados, muros de envolvente con la trama del
    material, particiones en poché, vanos (arco de puerta, ventana de
    triple línea), columnas de la tipología, aleros, flecha de norte,
    cotas totales y escala gráfica.
    """
    from core.geometry import structural
    layouts = list(variant.layouts)
    if not layouts:
        return Drawing(caption="Planta (sin variantes)", prims=[])
    layout = layouts[min(level_index, len(layouts) - 1)]
    thickness = data.wall_thickness_m
    x0, y0, x1, y1 = _layout_bounds([layout])
    prims: List[Prim] = []

    # Locales.
    for pr in layout.all_rooms:
        if pr.space_type == "PATIO":
            fill = "#dcead8"
        elif pr.is_corridor:
            fill = "#dbe4ef"
        elif pr.space_type in ("KITCHEN", "BATHROOM"):
            fill = "#dde8f0"
        else:
            fill = "#eef3f7"
        prims.append(PRect(pr.x, pr.y, pr.w, pr.d, fill=fill,
                           stroke="#90a4ae", stroke_width=0.8,
                           tag="local"))
        if pr.w > 1.6 and pr.d > 1.0:
            prims.append(PText(pr.x + pr.w / 2.0, pr.y + pr.d / 2.0 + 0.15,
                               pr.name, size=0.22, tag="etiqueta"))
            prims.append(PText(pr.x + pr.w / 2.0,
                               pr.y + pr.d / 2.0 - 0.20,
                               f"{pr.area_m2():.1f} m²", size=0.18,
                               color="#607d8b", tag="etiqueta"))

    # Muros: envolvente con trama del material, partición en poché.
    hatch_key = hatch_key_for(data.construction_type)
    flags = exterior_wall_flags(layout)
    for index, wall in enumerate(layout.walls):
        wx, wy, ww, wd = wall_rect(wall, thickness)
        if flags[index]:
            prims.append(PRect(wx, wy, ww, wd, fill="#f5f1e8",
                               stroke="#37474f", stroke_width=1.2,
                               hatch=hatch_key, tag="muro"))
        else:
            prims.append(PRect(wx, wy, ww, wd, fill="#cfd8dc",
                               stroke="#37474f", stroke_width=1.0,
                               tag="muro"))

    # Vanos: hueco blanco + símbolo.
    for opening in layout.doors:
        if not (0 <= opening.wall_index < len(layout.walls)):
            continue
        wall = layout.walls[opening.wall_index]
        (sx, sy), (ex, ey) = wall["start"], wall["end"]
        if abs(sy - ey) <= 1e-6:
            gx, gy = sx + opening.offset_m, sy - thickness / 2.0
            gw, gd = opening.width_m, thickness
        else:
            gx, gy = sx - thickness / 2.0, sy + opening.offset_m
            gw, gd = thickness, opening.width_m
        prims.append(PRect(gx, gy, gw, gd, fill="#ffffff",
                           stroke="#2e7d32", stroke_width=1.0,
                           tag="vano"))
        arc, leaf = _door_arc(layout, opening, wall, thickness)
        if arc is not None:
            prims.append(arc)
            prims.append(leaf)
    for opening in layout.windows:
        if not (0 <= opening.wall_index < len(layout.walls)):
            continue
        wall = layout.walls[opening.wall_index]
        (sx, sy), (ex, ey) = wall["start"], wall["end"]
        if abs(sy - ey) <= 1e-6:
            gx, gy = sx + opening.offset_m, sy - thickness / 2.0
            gw, gd = opening.width_m, thickness
            prims.append(PRect(gx, gy, gw, gd, fill="#ffffff",
                               stroke="#1565c0", stroke_width=1.0,
                               tag="vano"))
            prims.append(PLine(gx, sy, gx + gw, sy, color="#1565c0",
                               width=0.7, tag="vano"))
        else:
            gx, gy = sx - thickness / 2.0, sy + opening.offset_m
            gw, gd = thickness, opening.width_m
            prims.append(PRect(gx, gy, gw, gd, fill="#ffffff",
                               stroke="#1565c0", stroke_width=1.0,
                               tag="vano"))
            prims.append(PLine(sx, gy, sx, gy + gd, color="#1565c0",
                               width=0.7, tag="vano"))

    # Columnas de la tipología constructiva.
    for column in structural.column_placements([layout], data):
        prims.append(PRect(column.x, column.y, column.w, column.d,
                           fill="#37474f", stroke="#263238",
                           stroke_width=1.0, tag="columna"))
        prims.append(PLine(column.x, column.y, column.x + column.w,
                           column.y + column.d, color="#eceff1",
                           width=0.6, tag="columna"))
        prims.append(PLine(column.x, column.y + column.d,
                           column.x + column.w, column.y,
                           color="#eceff1", width=0.6, tag="columna"))

    # Aleros (protección solar).
    if data.protection_solar and data.eaves_m > 0:
        from core.geometry.engine import eaves_outline_segments
        for ax1, ay1, ax2, ay2 in eaves_outline_segments(
                layout.all_rooms, data.eaves_m):
            prims.append(PLine(ax1, ay1, ax2, ay2, color="#b45309",
                               width=1.4, dash=DASH_ALERO, tag="alero"))

    # Flecha de norte (girada según la fachada principal).
    angle = _north_angle(data.facade_orientation)
    import math as _math
    nx = x1 + 1.2
    ny = y1 + 1.2
    rad = _math.radians(angle)
    tip_x = nx + 0.9 * _math.sin(rad)
    tip_y = ny + 0.9 * _math.cos(rad)
    prims.append(PLine(nx, ny, tip_x, tip_y, color="#37474f",
                       width=1.4, tag="norte"))
    prims.append(PText(tip_x + 0.25, tip_y + 0.25, "N", size=0.30,
                       bold=True, tag="norte"))

    # Cotas totales (ancho abajo, fondo a la derecha).
    dim_y = y0 - 0.8
    prims.append(PLine(x0, dim_y, x1, dim_y, color="#455a64",
                       width=0.8, dash=DASH_COTA, tag="cota"))
    prims.append(PLine(x0, dim_y - 0.15, x0, dim_y + 0.15,
                       color="#455a64", width=0.8, tag="cota"))
    prims.append(PLine(x1, dim_y - 0.15, x1, dim_y + 0.15,
                       color="#455a64", width=0.8, tag="cota"))
    prims.append(PText((x0 + x1) / 2.0, dim_y - 0.25,
                       f"{x1 - x0:.2f} m".replace(".", ","), size=0.20,
                       color="#455a64", tag="cota"))
    dim_x = x1 + 0.8
    prims.append(PLine(dim_x, y0, dim_x, y1, color="#455a64",
                       width=0.8, dash=DASH_COTA, tag="cota"))
    prims.append(PText(dim_x + 0.25, (y0 + y1) / 2.0,
                       f"{y1 - y0:.2f} m".replace(".", ","), size=0.20,
                       color="#455a64", anchor="start", tag="cota"))

    # Escala gráfica (5 m en tramos de 1 m).
    sx0, sy0 = x0, y0 - 1.6
    for step in range(5):
        fill = "#37474f" if step % 2 == 0 else "#ffffff"
        prims.append(PRect(sx0 + step, sy0, 1.0, 0.18, fill=fill,
                           stroke="#37474f", stroke_width=0.7,
                           tag="escala"))
    prims.append(PText(sx0 + 2.5, sy0 + 0.38,
                       "escala 0 – 5 m (tramos de 1 m)", size=0.18,
                       color="#455a64", tag="escala"))

    prims.append(PText(x0, y1 + 1.4,
                       f"PLANTA — {layout.level_name} · "
                       f"{data.construction_type}",
                       size=0.28, anchor="start", bold=True,
                       tag="titulo"))
    return Drawing(caption=f"Planta {layout.level_name}", prims=prims)


# --------------------------------------------------------------------------
# DETALLES CONSTRUCTIVOS (biblioteca de nodos por tipología)
# --------------------------------------------------------------------------

@dataclass
class DetailNode:
    """Un nodo constructivo: código, título, memoria y esquema."""

    code: str
    titulo: str
    descripcion: str
    prims: List[Prim] = field(default_factory=list)


def _sketch_ground(prims: List[Prim], width: float = 3.0,
                   z: float = 1.0) -> None:
    """Línea de terreno con dientes de hacha para un esquema."""
    prims.append(PLine(0.1, z, width, z, color="#5d4037", width=1.4,
                       tag="terreno"))
    gx = 0.15
    while gx < width:
        prims.append(PLine(gx, z, gx - 0.09, z - 0.12, color="#5d4037",
                           width=0.6, tag="terreno"))
        gx += 0.28


def _stairs_requested(data) -> bool:
    """Escaleras pedidas (réplica local para no romper capas)."""
    mode = str(getattr(data, "stairs_mode", ""))
    if "Siempre" in mode:
        return True
    if mode.endswith("No incluir"):
        return False
    levels = len(getattr(data, "levels", []) or [1])
    rise = 0.0
    terrain = str(getattr(data, "terrain_type", ""))
    if "ligera" in terrain:
        rise = 0.75
    elif "fuerte" in terrain:
        rise = 1.5
    return levels > 1 or rise > 0.01


def detail_library(data) -> List[DetailNode]:
    """Nodos constructivos de la tipología, con acotado real.

    Selecciona los detalles que le competen a cada tipología:
    cimentación (corrida y/o aislada), coronamiento, esquina
    confinada o nudo de pórtico, vanos, alero y escalera.
    """
    from core.geometry.structural import STRATEGY_GRID, STRATEGY_POST, \
        STRATEGY_TIE, column_rule
    rule = column_rule(data.construction_type)
    hatch = hatch_key_for(data.construction_type)
    thickness = data.wall_thickness_m
    slab_t = slab_thickness(data.construction_type)
    profile = roof_profile(data)
    eaves = data.eaves_m if data.protection_solar else 0.0
    nodes: List[DetailNode] = []
    foot_w = max(0.60, 2.2 * thickness)

    # DET-CIM-01 · Zapata corrida.
    prims: List[Prim] = []
    _sketch_ground(prims)
    prims.append(PRect(1.5 - thickness / 2.0, 1.0, thickness, 1.45,
                       fill="#e8e2d5", stroke="#37474f", stroke_width=1.2,
                       hatch=hatch, tag="muro"))
    prims.append(PRect(1.5 - thickness / 2.0, 0.70, thickness, 0.30,
                       fill="#f5f1e8", stroke="#455a64",
                       tag="sobrecimiento"))
    prims.append(PRect(1.5 - foot_w / 2.0, 0.10, foot_w, 0.60,
                       fill="#eceff1", stroke="#455a64", hatch="hormigon",
                       tag="cimentacion"))
    prims.append(PLine(1.5 + thickness / 2.0, 1.08, 2.9, 1.08,
                       color="#8d6e63", width=1.0, dash=DASH_EJE,
                       tag="piso"))
    prims.append(PText(2.95, 0.4,
                       f"zapata {foot_w * 100:.0f} cm × 90 cm",
                       size=0.16, anchor="end", tag="cota"))
    nodes.append(DetailNode(
        code="DET-CIM-01",
        titulo="Zapata corrida bajo muro portante",
        descripcion=(
            f"Cimentación profunda 0,90 m bajo el muro de "
            f"{thickness * 100:.0f} cm: zapata corrida de hormigón de "
            f"{foot_w * 100:.0f} cm de ancho (aprox. 2,2 veces el espesor), "
            f"sobre-cimiento hidrofugado de 0,30 m sobre el terreno y "
            f"piso flotante apoyado a +0,08 m. En terrenos "
            f"«{data.terrain_type}» conviene llegar a suelo firme y "
            f"prever el drenaje perimetral."),
        prims=prims))

    # DET-CIM-02 · Zapata aislada bajo columna (pórticos).
    if rule.strategy == STRATEGY_GRID:
        prims = []
        _sketch_ground(prims)
        half = rule.size_m / 2.0
        prims.append(PRect(1.5 - half, 1.0, rule.size_m, 1.2,
                           fill="#455a64", stroke="#263238",
                           tag="columna"))
        prims.append(PRect(1.5 - 0.45, 0.10, 0.90, 0.60, fill="#eceff1",
                           stroke="#455a64", hatch="hormigon",
                           tag="cimentacion"))
        prims.append(PLine(1.95, 0.55, 2.9, 0.55, color="#455a64",
                           width=1.0, dash=DASH_EJE, tag="viga"))
        prims.append(PText(2.95, 0.75, "viga de cimentación hacia la derecha",
                           size=0.15, anchor="end", tag="cota"))
        nodes.append(DetailNode(
            code="DET-CIM-02",
            titulo=f"Zapata aislada bajo columna "
                   f"({rule.size_m * 100:.0f}×{rule.size_m * 100:.0f} cm)",
            descripcion=(
                f"Columna de {rule.material.lower()} de "
                f"{rule.size_m * 100:.0f}×{rule.size_m * 100:.0f} cm "
                f"arrancando de zapata aislada de 90×90 cm y 60 cm de "
                f"canto, enlazada por vigas de cimentación rígidas. "
                f"{rule.note} La separación adoptada en este proyecto "
                f"es de {rule.spacing_m:.1f} m entre ejes."),
            prims=prims))

    # DET-MUR-01 · Coronamiento: viga collar + losa (+ alero).
    prims = []
    prims.append(PRect(0.6, 0.8, thickness, 1.5, fill="#e8e2d5",
                       stroke="#37474f", stroke_width=1.2, hatch=hatch,
                       tag="muro"))
    prims.append(PRect(0.6 - 0.05, 2.3 - 0.20, thickness + 0.10, 0.20,
                       fill="#eceff1", stroke="#455a64", hatch="hormigon",
                       tag="viga_collar"))
    prims.append(PRect(0.6 + thickness, 2.3 - slab_t - 0.20, 1.5, slab_t,
                       fill="#eceff1", stroke="#546e7a", hatch="hormigon",
                       tag="losa"))
    if eaves > 0:
        prims.append(PLine(0.6 - eaves, 2.62, 0.6 + thickness + 0.3,
                           2.48, color="#546e7a", width=1.4,
                           tag="cubierta"))
    prims.append(PText(2.2, 1.5, f"losa {slab_t * 100:.0f} cm",
                       size=0.16, tag="cota"))
    nodes.append(DetailNode(
        code="DET-MUR-01",
        titulo="Coronamiento: viga collar, losa y alero",
        descripcion=(
            f"Amarrado superior del muro: viga collar de 20 cm de "
            f"canto sobre el muro de {thickness * 100:.0f} cm, que "
            f"recibe la losa de {slab_t * 100:.0f} cm "
            f"({data.construction_type.lower()}). "
            + (f"El alero de {eaves * 100:.0f} cm protege el "
               f"paramento de la lluvia y el solaluces de las "
               f"aperturas." if eaves > 0 else
               "Sin alero: revisar la protección de la fachada.")
            + " La viga collar es obligatoria en sismorresistencia "
              "para atar muros y losa."),
        prims=prims))

    # DET-MUR-02 / DET-PIL-01 / DET-MUR-03 · según estrategia.
    if rule.strategy in (STRATEGY_GRID,):
        prims = []
        half = rule.size_m / 2.0
        prims.append(PRect(1.5 - half, 0.8, rule.size_m, 1.8,
                           fill="#455a64", stroke="#263238",
                           tag="columna"))
        prims.append(PRect(0.4, 2.4, 1.1 - half + 0.4, 0.22,
                           fill="#eceff1", stroke="#546e7a",
                           hatch="hormigon", tag="viga"))
        prims.append(PRect(1.5 + half, 2.4, 1.1, 0.22, fill="#eceff1",
                           stroke="#546e7a", hatch="hormigon",
                           tag="viga"))
        prims.append(PText(2.4, 2.8, "viga de pórtico", size=0.16,
                           tag="cota"))
        prims.append(PText(0.8, 0.55, f"pilar {rule.size_m * 100:.0f} cm",
                           size=0.16, tag="cota"))
        nodes.append(DetailNode(
            code="DET-PIL-01",
            titulo="Nudo columna–viga de pórtico",
            descripcion=(
                f"Nudo rígido del pórtico de {rule.material.lower()}: "
                f"columna de {rule.size_m * 100:.0f}×"
                f"{rule.size_m * 100:.0f} cm con vigas de borde de "
                f"22 cm de canto a ambos lados. Los muros de cierre "
                f"van embutidos sin trabajar; el encuentro se arriostra "
                f"con estribos cerrados. Separación de pórticos: "
                f"{rule.spacing_m:.1f} m."),
            prims=prims))
    elif rule.strategy == STRATEGY_TIE:
        prims = []
        # Planta de la esquina: dos muros en L + columna.
        t = thickness
        prims.append(PRect(1.2, 1.2, 1.6, t, fill="#e8e2d5",
                           stroke="#37474f", hatch=hatch, tag="muro"))
        prims.append(PRect(1.2, 1.2 + t, t, 1.4, fill="#e8e2d5",
                           stroke="#37474f", hatch=hatch, tag="muro"))
        c = rule.size_m
        prims.append(PRect(1.2, 1.2 + t, c, c, fill="#455a64",
                           stroke="#263238", tag="columna"))
        prims.append(PLine(1.2, 1.2 + t, 1.2 + c, 1.2 + t + c,
                           color="#eceff1", width=0.6, tag="columna"))
        prims.append(PText(2.0, 2.0,
                           f"columna de refuerzo {c * 100:.0f}×"
                           f"{c * 100:.0f} cm", size=0.15, tag="cota"))
        nodes.append(DetailNode(
            code="DET-MUR-02",
            titulo="Esquina confinada con columna de refuerzo",
            descripcion=(
                f"Encuentro en esquina de muros de "
                f"{data.construction_type.lower()}: columna de "
                f"refuerzo de hormigón de {c * 100:.0f}×{c * 100:.0f} "
                f"cm embutida, con amarres cada 2 hiladas de varilla "
                f"galvanizada. Repetir en todos los encuentros y cada "
                f"{rule.spacing_m:.1f} m en muros largos; encima corre "
                f"la viga collar que ata el confinamiento."),
            prims=prims))
    elif rule.strategy == STRATEGY_POST:
        prims = []
        prims.append(PRect(1.3, 0.8, rule.size_m, 1.8, fill="#8d6e63",
                           stroke="#5d4037", hatch="madera",
                           tag="pilar"))
        prims.append(PRect(0.5, 2.35, 2.0, 0.12, fill="#eceff1",
                           stroke="#546e7a", tag="viga"))
        prims.append(PText(2.4, 1.6, "viga de coronamiento", size=0.15,
                           tag="cota"))
        nodes.append(DetailNode(
            code="DET-MUR-03",
            titulo=f"Pilar de {rule.material.lower()} y coronamiento",
            descripcion=(
                f"Pilar de {rule.size_m * 100:.0f}×"
                f"{rule.size_m * 100:.0f} cm en esquinas y montantes "
                f"perimetrales cada {rule.spacing_m:.1f} m (donde "
                f"aplica), con viga de coronamiento continua de 12 cm. "
                f"{rule.note} El entablado o panel trabaja como "
                f"diafragma rígido."),
            prims=prims))

    # DET-VAN-01 · Vano de ventana.
    sill = data.window_sill_m
    wh = data.window_height_m
    ww = data.window_width_m
    prims = []
    _sketch_ground(prims)
    prims.append(PRect(1.5 - thickness / 2.0, 1.0, thickness, sill,
                       fill="#e8e2d5", stroke="#37474f", hatch=hatch,
                       tag="antepecho"))
    prims.append(PRect(1.5 - thickness / 2.0, 1.0 + sill, thickness, wh,
                       fill="#ffffff", stroke="#1565c0",
                       tag="vano"))
    prims.append(PLine(1.5 - thickness / 2.0, 1.0 + sill + wh + 0.15,
                       1.5 + thickness / 2.0, 1.0 + sill + wh + 0.15,
                       color="#455a64", width=2.0, tag="dintel"))
    prims.append(PRect(1.5 - thickness / 2.0,
                       1.0 + sill + wh, thickness, 0.15,
                       fill="#e8e2d5", stroke="#37474f", tag="dintel"))
    prims.append(PText(2.6, 1.2 + sill,
                       f"vano {ww:.2f}×{wh:.2f} m".replace(".", ","),
                       size=0.15, anchor="start", tag="cota"))
    prims.append(PText(2.6, 1.08, f"antepecho {sill:.2f} m"
                       .replace(".", ","), size=0.15, anchor="start",
                       tag="cota"))
    nodes.append(DetailNode(
        code="DET-VAN-01",
        titulo="Vano de ventana: antepecho, jambas y dintel",
        descripcion=(
            f"Ventana de {ww:.2f} m de ancho y {wh:.2f} m de alto con "
            f"antepecho a {sill:.2f} m (réguas del paso 4). Dintel de "
            f"0,15 m de canto apoyado 0,25 m por lado sobre el muro de "
            f"{thickness * 100:.0f} cm. En clima «{data.climate}» "
            f"convienen protecciones voladas o postigos para el sol "
            f"de poniente."),
        prims=prims))

    # DET-VAN-02 · Puerta exterior.
    dh = data.door_height_m
    dw = data.door_width_m
    prims = []
    _sketch_ground(prims)
    prims.append(PRect(1.5 - thickness / 2.0, 1.02, thickness, dh,
                       fill="#ffffff", stroke="#2e7d32", tag="vano"))
    prims.append(PRect(1.5 - thickness / 2.0, 1.02 + dh, thickness, 0.15,
                       fill="#e8e2d5", stroke="#37474f", tag="dintel"))
    prims.append(PRect(1.5 - foot_w / 2.0, 0.10, foot_w, 0.60,
                       fill="#eceff1", stroke="#455a64", hatch="hormigon",
                       tag="cimentacion"))
    prims.append(PLine(0.3, 1.02, 1.5 - thickness / 2.0, 1.02,
                       color="#8d6e63", width=1.2, tag="piso"))
    prims.append(PText(2.5, 1.35,
                       f"puerta {dw:.2f}×{dh:.2f} m".replace(".", ","),
                       size=0.15, anchor="start", tag="cota"))
    nodes.append(DetailNode(
        code="DET-VAN-02",
        titulo="Puerta exterior: dintel y umbral",
        descripcion=(
            f"Acceso principal de {dw:.2f}×{dh:.2f} m (regla del paso "
            f"4) con dintel de 0,15 m y umbral a +0,02 m sobre el "
            f"replanteado exterior para cortar el agua. El vano cae "
            f"entre columnas o refuerzos: nunca se abre en un pilar. "
            f"En fachada «{data.facade_orientation}» se sugiere "
            f"marquesina o retranqueo."),
        prims=prims))

    # DET-CUB-01 · Alero y cornisa (con protección solar).
    if eaves > 0:
        prims = []
        prims.append(PRect(1.2, 0.8, thickness, 1.6, fill="#e8e2d5",
                           stroke="#37474f", hatch=hatch, tag="muro"))
        prims.append(PLine(1.2 - eaves, 2.62, 1.2 + thickness + 0.3,
                           2.48, color="#546e7a", width=1.6,
                           tag="cubierta"))
        prims.append(PRect(1.2 - 0.05, 2.3 - 0.2, thickness + 0.10, 0.2,
                           fill="#eceff1", stroke="#455a64",
                           hatch="hormigon", tag="viga_collar"))
        prims.append(PLine(1.2 - eaves, 2.62, 1.2 - eaves, 2.40,
                           color="#546e7a", width=1.2, tag="cubierta"))
        prims.append(PText(0.5, 2.75,
                           f"alero {eaves:.2f} m".replace(".", ","),
                           size=0.16, anchor="start", tag="cota"))
        nodes.append(DetailNode(
            code="DET-CUB-01",
            titulo="Alero y cornisa con viga volada",
            descripcion=(
                f"Voladizo de cubierta de {eaves:.2f} m "
                f"(protección solar del paso 5) sobre viga de alero "
                f"arrastrada desde la viga collar, con gotera en el "
                f"canto para alejar el goteo del paramento. Cubierta "
                f"{profile.description.lower()}; el alero sombrea los "
                f"vanos en verano y defiende el muro de la lluvia "
                f"vertida."),
            prims=prims))

    # DET-ESC-01 · Escalera (huella y contrahuella).
    if _stairs_requested(data):
        prims = []
        _sketch_ground(prims)
        riser, tread = 0.175, 0.28
        sx_, sy_ = 0.6, 1.0
        for _step in range(5):
            prims.append(PLine(sx_, sy_, sx_ + tread, sy_,
                               color="#37474f", width=1.2,
                               tag="escalera"))
            sy_ += riser
            prims.append(PLine(sx_ + tread, sy_ - riser, sx_ + tread,
                               sy_, color="#37474f", width=1.2,
                               tag="escalera"))
            sx_ += tread
        prims.append(PLine(0.6, 1.0, sx_, sy_, color="#b45309",
                           width=0.9, dash=DASH_EJE, tag="escalera"))
        prims.append(PText(2.4, 1.7,
                           f"contrahuella {riser * 100:.1f} cm · "
                           f"huella {tread * 100:.0f} cm",
                           size=0.15, anchor="start", tag="cota"))
        nodes.append(DetailNode(
            code="DET-ESC-01",
            titulo="Escalera: huella, contrahuella y losa inclinada",
            descripcion=(
                f"Tramo recto con contrahuella de {riser * 100:.1f} cm "
                f"y huella de {tread * 100:.0f} cm (2h + c = 63 cm aprox.), "
                f"losa inclinada de 12 cm y barandal de 0,90 m. El "
                f"motor ya reserva el desarrollo necesario por nivel; "
                f"este nodo fija el encuentro del primer peldaño con "
                f"el piso y el remate en la losa superior."),
            prims=prims))

    return nodes
