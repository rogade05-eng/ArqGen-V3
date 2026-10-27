"""Motor de estructura vertical (v2.6.0): columnas según tipología.

Pensado como un arquitecto: cada tipología constructiva tiene su
estrategia estructural real —

* PÓRTICO (hormigón armado, prefabricado, metálico, losa maciza):
  malla de columnas embutida en los ejes de muros y en las esquinas
  del envolvente, con separación según el material (5,0–6,0 m).
* REFUERZO (mampostería de bloque, muros de piedra): los muros
  portantes llevan columnas de refuerzo (zunchos) en esquinas,
  encuentros y cada cierta distancia (4,8–5,0 m) para amarrar los
  muros a la losa — práctica caribeña de confinamiento.
* PILARES (madera ligera, acero galvanizado ligero): postes de
  esquina y montantes perimetrales cada 3,0 m.
* AUTOPORTANTE (panel sandwich, adobe/tapial): sin columnas —
  viga collar continua o paneles que trabajan solos.

Las columnas nunca caen dentro de un vano (puerta o ventana) y se
deduplican por posición redondeada. Todo determinista.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Estrategias ----------------------------------------------------------------

STRATEGY_GRID = "malla de pórtico"
STRATEGY_TIE = "columnas de refuerzo"
STRATEGY_POST = "pilares"
STRATEGY_NONE = "autoporante"

@dataclass(frozen=True)
class ColumnRule:
    """Regla de columnas para una tipología constructiva."""

    strategy: str                     # STRATEGY_*
    size_m: float = 0.0               # lado de la columna (0 = sin columnas)
    spacing_m: float = 0.0            # separación máxima (0 = solo esquinas)
    material: str = ""
    note: str = ""

    @property
    def has_columns(self) -> bool:
        return self.size_m > 0.0


#: Reglas por tipología constructiva (las 10 de CONSTRUCTION_TYPES).
COLUMN_RULES: Dict[str, ColumnRule] = {
    "Mampostería de bloque + losa de vigueta": ColumnRule(
        strategy=STRATEGY_TIE, size_m=0.20, spacing_m=4.8,
        material="Hormigón armado (confinamiento)",
        note="Columnas de refuerzo en esquinas, encuentros de muros "
             "y cada 4,8 m para amarrar muros y losa de vigueta."),
    "Hormigón armado (monolítico)": ColumnRule(
        strategy=STRATEGY_GRID, size_m=0.30, spacing_m=5.0,
        material="Hormigón armado monolítico",
        note="Pórticos embutidos en los ejes de muros cada 5,0 m; "
             "cruces rígidas viga-columna."),
    "Vigas y columnas prefabricadas": ColumnRule(
        strategy=STRATEGY_GRID, size_m=0.40, spacing_m=6.0,
        material="Hormigón prefabricado",
        note="Malla de pilares prefabricados cada 6,0 m con viga "
             "de coronamiento apoyada."),
    "Madera ligera": ColumnRule(
        strategy=STRATEGY_POST, size_m=0.15, spacing_m=0.0,
        material="Madera aserrada",
        note="Pilares de esquina; el entablado ligero trabaja como "
             "diafragma (sin malla intermedia)."),
    "Panel prefabricado (sandwich)": ColumnRule(
        strategy=STRATEGY_NONE, size_m=0.0, spacing_m=0.0,
        material="",
        note="Paneles autoportantes: no llevan columnas."),
    "Losa maciza de hormigón": ColumnRule(
        strategy=STRATEGY_GRID, size_m=0.30, spacing_m=5.5,
        material="Hormigón armado monolítico",
        note="Pórticos cada 5,5 m bajo losa maciza; el tamaño de "
             "columna crece con la luz."),
    "Estructura metálica (acero)": ColumnRule(
        strategy=STRATEGY_GRID, size_m=0.30, spacing_m=6.0,
        material="Perfil laminado de acero",
        note="Pórticos metálicos cada 6,0 m; arriostres en "
             "cruces de ejes."),
    "Muros de piedra": ColumnRule(
        strategy=STRATEGY_TIE, size_m=0.25, spacing_m=5.0,
        material="Mampostería confinada con zunchos",
        note="Esquinas y encuentros zunchados; columnas de refuerzo "
             "cada 5,0 m en muros largos."),
    "Tierra (adobe o tapial)": ColumnRule(
        strategy=STRATEGY_NONE, size_m=0.0, spacing_m=0.0,
        material="",
        note="Muro macizo autoportante con viga collar continua de "
             "madera o hormigón en el coronamiento."),
    "Estructura ligera de acero galvanizado + panel": ColumnRule(
        strategy=STRATEGY_POST, size_m=0.15, spacing_m=3.0,
        material="Acero galvanizado",
        note="Montantes perimetrales reforzados cada 3,0 m; "
             "esquinas con perfil doble."),
}

#: Correspondencia con el sistema estructural del paso 1: aviso si no
#: encajan (p. ej. «Pórtico de hormigón» con «Madera ligera»).
SYSTEM_MATCHES: Dict[str, Tuple[str, ...]] = {
    "Muros portantes": (STRATEGY_TIE, STRATEGY_NONE),
    "Pórtico de hormigón": (STRATEGY_GRID,),
    "Mixto (pórtico + muros)": (STRATEGY_GRID, STRATEGY_TIE,
                                STRATEGY_POST, STRATEGY_NONE),
}


def column_rule(construction_type: str) -> ColumnRule:
    """Regla de columnas de la tipología (con reserva por defecto)."""
    rule = COLUMN_RULES.get(construction_type)
    if rule is None:
        return ColumnRule(strategy=STRATEGY_TIE, size_m=0.20,
                          spacing_m=4.8, material="Hormigón armado",
                          note="Tipología no catalogada: se asume "
                               "confinamiento de mampostería.")
    return rule


def structural_mismatch(structural_system: str,
                        construction_type: str) -> Optional[str]:
    """Aviso si el sistema elegido no encaja con la tipología."""
    rule = column_rule(construction_type)
    allowed = SYSTEM_MATCHES.get(structural_system)
    if allowed is None or rule.strategy in allowed:
        return None
    if not rule.has_columns and rule.strategy == STRATEGY_NONE:
        return (f"«{construction_type}» trabaja como muro autoportante "
                f"(sin columnas): el sistema «{structural_system}» "
                f"queda cubierto por los propios muros y su viga collar.")
    return (f"«{construction_type}» funciona mejor con pórtico o "
            f"confinamiento: revisa el sistema estructural "
            f"«{structural_system}» del paso 1.")


# Colocación -----------------------------------------------------------------

@dataclass
class ColumnPlacement:
    """Una columna ya resuelta sobre la planta del nivel."""

    x: float                 # esquina inferior-izquierda (m)
    y: float
    w: float
    d: float
    level_name: str
    kind: str = "malla"      # esquina | encuentro | malla | refuerzo | pilar
    material: str = ""
    note: str = ""

    @property
    def center(self) -> Tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.d / 2.0)

    @property
    def section(self) -> str:
        return f"{self.w * 100:.0f}×{self.d * 100:.0f} cm"


_TOL = 0.10
_DUCT_HALF = 0.30        # la columna se centra en el eje del muro
_MAX_INTERIOR = 4.0      # no meter columnas sueltas dentro de locales


def _wall_rect(wall: Dict, thickness: float) -> Tuple[float, float,
                                                      float, float]:
    """Rect (x, y, w, d) del muro fusionado (axis-aligned)."""
    (sx, sy), (ex, ey) = wall["start"], wall["end"]
    if abs(sy - ey) <= 1e-6:                       # horizontal
        lo, hi = min(sx, ex), max(sx, ex)
        return (lo, sy - thickness / 2.0, hi - lo, thickness)
    lo, hi = min(sy, ey), max(sy, ey)
    return (sx - thickness / 2.0, lo, thickness, hi - lo)


def _opening_intervals(layout, wall_index: int) -> List[Tuple[float, float]]:
    """Intervalos ABSOLUTOS (sobre el eje del muro) de sus vanos.

    El offset del vano se mide desde el inicio del muro fusionado; se
    convierte a coordenada absoluta para compararla con las columnas.
    """
    wall = layout.walls[wall_index]
    (sx, sy), (ex, ey) = wall["start"], wall["end"]
    # Horizontal: el eje del muro es X (arranca en sx).
    # Vertical: el eje del muro es Y (arranca en sy).
    start = sx if abs(sy - ey) <= 1e-6 else sy
    out: List[Tuple[float, float]] = []
    for opening in list(layout.doors) + list(layout.windows):
        if opening.wall_index == wall_index:
            out.append((start + opening.offset_m - _DUCT_HALF,
                        start + opening.offset_m + opening.width_m
                        + _DUCT_HALF))
    return out


def _junction_points(walls: Sequence[Dict],
                     thickness: float) -> List[Tuple[float, float]]:
    """Puntos de encuentro entre muros (esquinas, T y cruces)."""
    points: List[Tuple[float, float]] = []
    for i, wall_a in enumerate(walls):
        (ax1, ay1), (ax2, ay2) = wall_a["start"], wall_a["end"]
        a_h = abs(ay1 - ay2) <= 1e-6
        for j in range(i + 1, len(walls)):
            wall_b = walls[j]
            (bx1, by1), (bx2, by2) = wall_b["start"], wall_b["end"]
            b_h = abs(by1 - by2) <= 1e-6
            if a_h == b_h:
                continue                            # paralelos: no hay nudo
            if a_h:                                 # A horizontal, B vertical
                x, y = bx1, ay1
                b_lo, b_hi = min(by1, by2), max(by1, by2)
                a_lo, a_hi = min(ax1, ax2), max(ax1, ax2)
                if b_lo - _TOL <= y <= b_hi + _TOL \
                        and a_lo - _TOL <= x <= a_hi + _TOL:
                    points.append((round(x, 3), round(y, 3)))
            else:                                   # A vertical, B horizontal
                x, y = ax1, by1
                a_lo, a_hi = min(ay1, ay2), max(ay1, ay2)
                b_lo, b_hi = min(bx1, bx2), max(bx1, bx2)
                if a_lo - _TOL <= y <= a_hi + _TOL \
                        and b_lo - _TOL <= x <= b_hi + _TOL:
                    points.append((round(x, 3), round(y, 3)))
    # Dedupe con tolerancia de media columna.
    unique: List[Tuple[float, float]] = []
    for x, y in points:
        if all(abs(x - ux) > thickness / 2 or abs(y - uy) > thickness / 2
               for ux, uy in unique):
            unique.append((x, y))
    return unique


def _inside_banned(x: float, y: float, rooms, ban_types) -> bool:
    """¿El punto cae dentro de un patio, escalera o núcleo?"""
    for pr in rooms:
        if pr.space_type in ban_types:
            if pr.x - _TOL <= x <= pr.x + pr.w + _TOL \
                    and pr.y - _TOL <= y <= pr.y + pr.d + _TOL:
                return True
    return False


def _on_wall_axis(walls: Sequence[Dict], thickness: float,
                  x: float, y: float) -> Optional[Dict]:
    """Muro cuyo eje pasa por (x, y) (± media columna)."""
    for wall in walls:
        (sx, sy), (ex, ey) = wall["start"], wall["end"]
        if abs(sy - ey) <= 1e-6:                    # horizontal
            if abs(y - sy) <= thickness / 2 + _DUCT_HALF \
                    and min(sx, ex) - _DUCT_HALF <= x \
                    <= max(sx, ex) + _DUCT_HALF:
                return wall
        elif abs(sx - ex) <= 1e-6:                  # vertical
            if abs(x - sx) <= thickness / 2 + _DUCT_HALF \
                    and min(sy, ey) - _DUCT_HALF <= y \
                    <= max(sy, ey) + _DUCT_HALF:
                return wall
    return None


def _opening_blocked(x: float, y: float, walls: Sequence[Dict],
                     thickness: float,
                     openings_map: Dict[Tuple[float, str],
                                        List[Tuple[float, float]]]
                     ) -> bool:
    """¿La posición (x, y) cae en un vano de CUALQUIER muro que pasa
    por ahí? (los encuentros en T cruzan muros con puertas propias)"""
    for wall in walls:
        (sx, sy), (ex, ey) = wall["start"], wall["end"]
        if abs(sy - ey) <= 1e-6:                    # horizontal
            if abs(y - sy) <= thickness / 2 + _DUCT_HALF \
                    and min(sx, ex) - _DUCT_HALF <= x \
                    <= max(sx, ex) + _DUCT_HALF:
                for lo, hi in openings_map.get((round(sy, 3), "H"), []):
                    if lo <= x <= hi:
                        return True
        elif abs(sx - ex) <= 1e-6:                  # vertical
            if abs(x - sx) <= thickness / 2 + _DUCT_HALF \
                    and min(sy, ey) - _DUCT_HALF <= y \
                    <= max(sy, ey) + _DUCT_HALF:
                for lo, hi in openings_map.get((round(sx, 3), "V"), []):
                    if lo <= y <= hi:
                        return True
    return False


def _place_column(x: float, y: float, rule: ColumnRule,
                  kind: str, accepted: List[Tuple[float, float]],
                  walls: Sequence[Dict], thickness: float,
                  openings_map: Dict[Tuple[float, str],
                                     List[Tuple[float, float]]],
                  wall: Optional[Dict] = None) -> Optional[int]:
    """Valida y añade la columna; devuelve su índice o None.

    Comprueba: no cae en un vano de ningún muro que pase por el
    punto, no duplica una columna ya aceptada.
    """
    cx, cy = x, y
    if wall is not None:
        # Centrar en el eje del muro anfitrión.
        (sx, sy), (ex, ey) = wall["start"], wall["end"]
        if abs(sy - ey) <= 1e-6:
            cy = sy
        else:
            cx = sx
    for ux, uy in accepted:
        if abs(cx - ux) < rule.size_m / 2 + _TOL \
                and abs(cy - uy) < rule.size_m / 2 + _TOL:
            return None
    if _opening_blocked(cx, cy, walls, thickness, openings_map):
        return None                          # dentro de un vano
    accepted.append((cx, cy))
    return len(accepted) - 1


def column_placements(layouts, data) -> List[ColumnPlacement]:
    """Columnas de TODOS los niveles según la tipología constructiva.

    Devuelve una lista determinista lista para dibujar (planta) y
    para el resumen estructural. No muta los layouts.
    """
    rule = column_rule(data.construction_type)
    if not rule.has_columns:
        return []
    thickness = data.wall_thickness_m
    half = rule.size_m / 2.0
    placements: List[ColumnPlacement] = []

    for layout in layouts:
        walls: List[Dict] = layout.walls
        rooms = layout.all_rooms
        if not walls:
            continue
        # Envolvente del nivel (para reconocer esquinas).
        xs = [pr.x for pr in rooms] + [pr.x + pr.w for pr in rooms]
        ys = [pr.y for pr in rooms] + [pr.y + pr.d for pr in rooms]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        openings_map: Dict[Tuple[float, str], List[Tuple[float, float]]] = {}
        for index, wall in enumerate(walls):
            (sx, sy), (ex, ey) = wall["start"], wall["end"]
            if abs(sy - ey) <= 1e-6:
                openings_map[(round(sy, 3), "H")] = \
                    _opening_intervals(layout, index)
            else:
                openings_map[(round(sx, 3), "V")] = \
                    _opening_intervals(layout, index)

        accepted: List[Tuple[float, float]] = []

        def add(x: float, y: float, kind: str, wall: Optional[Dict]) -> None:
            index = _place_column(x, y, rule, kind, accepted, walls,
                                  thickness, openings_map, wall)
            if index is None:
                return
            placements.append(ColumnPlacement(
                x=accepted[index][0] - half, y=accepted[index][1] - half,
                w=rule.size_m, d=rule.size_m,
                level_name=layout.level_name, kind=kind,
                material=rule.material, note=rule.note))

        # 1) Esquinas del envolvente — siempre.
        corners = [(min_x, min_y), (max_x, min_y),
                   (min_x, max_y), (max_x, max_y)]
        for cx, cy in corners:
            wall = _on_wall_axis(walls, thickness, cx, cy)
            add(cx, cy, "esquina", wall)

        # 2) Galería arcada: los pórticos columnean el patio ANTES que
        # los demás pases, para que sus columnas queden con su nombre.
        if rule.strategy == STRATEGY_GRID:
            for pr in rooms:
                if pr.space_type != "PATIO":
                    continue
                per = [(pr.x, pr.y), (pr.x + pr.w, pr.y),
                       (pr.x + pr.w, pr.y + pr.d), (pr.x, pr.y + pr.d)]
                for cx, cy in per:
                    wall = _on_wall_axis(walls, thickness, cx, cy)
                    if wall is not None:
                        add(cx, cy, "galería", wall)

        # 3) Encuentros entre muros (T, L, cruces).
        for jx, jy in _junction_points(walls, thickness):
            wall = _on_wall_axis(walls, thickness, jx, jy)
            add(jx, jy, "encuentro", wall)

        # 4) Intermedias según separación máxima.
        if rule.strategy == STRATEGY_GRID:
            # Malla: sobre los ejes de muros largos.
            for index, wall in enumerate(walls):
                length = float(wall["length"])
                if length < rule.spacing_m:
                    continue
                (sx, sy), (ex, ey) = wall["start"], wall["end"]
                horizontal = abs(sy - ey) <= 1e-6
                steps = int(length // rule.spacing_m)
                for step in range(1, steps + 1):
                    pos = step * rule.spacing_m
                    if length - pos < rule.spacing_m / 2.0:
                        continue                     # demasiado cerca del fin
                    if horizontal:
                        add(sx + pos, sy, "malla", wall)
                    else:
                        add(sx, sy + pos, "malla", wall)
        elif rule.spacing_m > 0.0:
            # Refuerzo / montantes: cada separación en muros largos.
            for index, wall in enumerate(walls):
                length = float(wall["length"])
                if length <= rule.spacing_m:
                    continue
                (sx, sy), (ex, ey) = wall["start"], wall["end"]
                horizontal = abs(sy - ey) <= 1e-6
                steps = int(round(length / rule.spacing_m))
                if steps < 2:
                    continue
                for step in range(1, steps):
                    pos = step * length / steps
                    if horizontal:
                        add(sx + pos, sy, "refuerzo", wall)
                    else:
                        add(sx, sy + pos, "refuerzo", wall)

    return placements


def columns_summary(placements: Sequence[ColumnPlacement]) -> Dict[str, int]:
    """Recuento por clase (para metadata y resumen)."""
    out: Dict[str, int] = {}
    for placement in placements:
        out[placement.kind] = out.get(placement.kind, 0) + 1
    return out
