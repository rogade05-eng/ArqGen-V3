"""Puente asistentes → instalaciones (v3.8.0): redes reales, no promesas.

El usuario pidió «conectar los asistentes de generación a los demás
sistemas: cuando los uso se quedan en la arquitectura y no pasan a los
demás módulos y/o instalaciones».  Este módulo cierra ese hueco:

- ``generate_installations()`` convierte los módulos elegidos en el
  asistente de edificación («Eléctrica», «Sanitaria», …) en redes
  reales del proyecto, ADAPTADAS a los locales creados: luminarias y
  tomas en cada local, tableros por nivel, aparatos sanitarios donde
  hay baños y cocinas, difusores de aire en los locales ocupables,
  extractores en los húmedos, detectores de humo, tomas de datos y
  gas donde corresponde.

- ``connect_local()`` hace lo mismo para el asistente de local: el
  local creado queda conectado a las redes existentes (o crea la
  «Red eléctrica» si el proyecto no tiene ninguna) con su luminaria,
  su toma y sus aparatos si es un local húmedo.

Todo es aditivo e idempotente: si el asistente se ejecuta otra vez
(p. ej. para añadir un nivel), solo se añaden los terminales de los
locales que aún no están servidos, sin duplicar redes.  100 % headless
y verificable con unittest: la GUI solo muestra el resumen.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.geometry.engine import centroid, contains
from core.geometry.primitives import Point, Polygon

# -- Mapeo de módulos del asistente → sistemas de red --------------------------
# Las claves son EXACTAMENTE las de ui.building_wizard.INSTALLATION_MODULES;
# la paridad se vigila en pruebas y en el selftest.

MODULE_SYSTEMS: Dict[str, Tuple[str, ...]] = {
    "Eléctrica": ("POWER",),
    "Sanitaria": ("COLD_WATER", "SANITARY_DRAINAGE"),
    "Ventilación mecánica / A/C": ("HVAC_SUPPLY", "EXHAUST"),
    "Protección contra incendios": ("FIRE_ALARM",),
    "Comunicaciones (voz y datos)": ("TELECOM",),
    "Gas": ("GAS",),
    "Energía solar": ("POWER",),
}

# Nombre estable de cada red (se reutiliza si ya existe en el proyecto).
NETWORK_NAMES: Dict[str, str] = {
    "POWER": "Red eléctrica",
    "COLD_WATER": "Red de agua fría",
    "SANITARY_DRAINAGE": "Red de desagüe",
    "HVAC_SUPPLY": "Red de aire acondicionado",
    "EXHAUST": "Red de extracción",
    "FIRE_ALARM": "Red de detección de incendios",
    "TELECOM": "Red de voz y datos",
    "GAS": "Red de gas",
}

# Tipo de tramo por sistema (domain.installations.SEGMENT_KINDS).
SEGMENT_BY_SYSTEM: Dict[str, str] = {
    "POWER": "CONDUIT",
    "COLD_WATER": "PIPE",
    "SANITARY_DRAINAGE": "DRAIN_PIPE",
    "HVAC_SUPPLY": "DUCT",
    "EXHAUST": "DUCT",
    "FIRE_ALARM": "SEC_CABLE",
    "TELECOM": "CABLE",
    "GAS": "PIPE",
}

# -- Conocimiento de locales ---------------------------------------------------
# Húmedos: llevan aparatos sanitarios, desagüe y extractor.
WET_SPACE_TYPES: Tuple[str, ...] = (
    "BATHROOM", "KITCHEN", "LAUNDRY", "STERILIZATION_ROOM", "LABORATORY",
)
# De servicio: sin difusor de A/C ni toma de datos (sí detector/luminaria).
SERVICE_SPACE_TYPES: Tuple[str, ...] = (
    "STAIR", "CORE", "CORRIDOR", "PATIO", "STOREROOM", "ENTRANCE",
)
# Anclas para tableros, paneles de incendio y racks (en orden de preferencia).
ANCHOR_SPACE_TYPES: Tuple[str, ...] = ("CORE", "CORRIDOR", "ENTRANCE")

# Aparatos sanitarios por tipo de local (kind_civil → unidades Hunter).
FIXTURES_BY_TYPE: Dict[str, Tuple[Tuple[str, float], ...]] = {
    "BATHROOM": (("inodoro", 4.0), ("lavabo", 1.0), ("ducha", 2.0)),
    "KITCHEN": (("fregadero", 2.0),),
    "LAUNDRY": (("lavadero", 2.0),),
    "STERILIZATION_ROOM": (("lavabo", 1.0), ("fregadero", 2.0)),
    "LABORATORY": (("lavabo", 1.0),),
}

# Electrodomésticos a gas por tipo de local.
GAS_BY_TYPE: Dict[str, Tuple[str, ...]] = {
    "KITCHEN": ("cocina de gas",),
    "LAUNDRY": ("calentador de gas",),
}

# Aparatos eléctricos especiales por uso social (attrs de APPLIANCE).
SPECIAL_POWER: Dict[str, Tuple[str, ...]] = {
    "Hospital": ("panel de rayos X", "autoclave"),
    "Policlínico": ("autoclave",),
    "Consultorio médico": ("autoclave",),
}

# Cuántas tomas por local según su área (regla amable de la guía).
_OUTLETS_LARGE_AREA_M2 = 9.0

# Fracciones del cuadro delimitador para colocar nodos sin apilarlos.
_F_CENTROID = (0.5, 0.5)


class _Summary(dict):
    """Resumen acumulable con claves fijas (dict con ``add``)."""

    def __init__(self) -> None:
        super().__init__(redes=0, equipos=0, tramos=0, nombres=[],
                         warnings=[])
        self._seen_net: set = set()

    def node(self, n: int = 1) -> None:
        self["equipos"] += n

    def segment(self, n: int = 1) -> None:
        self["tramos"] += n

    def network(self, name: str) -> None:
        if name not in self._seen_net:
            self._seen_net.add(name)
            self["nombres"].append(name)
            self["redes"] = len(self["nombres"])

    def warn(self, text: str) -> None:
        if text not in self["warnings"]:
            self["warnings"].append(text)


# -- utilidades geométricas ----------------------------------------------------

def _bbox(points: Sequence[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _poly_contains(polygon: Polygon, x: float, y: float) -> bool:
    try:
        return contains(polygon, Point(x, y))
    except Exception:  # noqa: BLE001 - geometría degenerada
        return False


def _place_in_space(space, fx: float, fy: float) -> Tuple[float, float]:
    """Punto determinista dentro del local: fracción del cuadro del
    delimitador si cae dentro del contorno; centroide en caso contrario."""
    x0, y0, x1, y1 = _bbox(space.boundary)
    x = x0 + fx * (x1 - x0)
    y = y0 + fy * (y1 - y0)
    if fx == _F_CENTROID[0] and fy == _F_CENTROID[1]:
        try:
            c = centroid([Point(px, py) for px, py in space.boundary])
            return (round(c.x, 4), round(c.y, 4))
        except Exception:  # noqa: BLE001 - contorno degenerado
            return (round((x0 + x1) / 2.0, 4), round((y0 + y1) / 2.0, 4))
    if _poly_contains(space.polygon(), x, y):
        return (round(x, 4), round(y, 4))
    return _place_in_space(space, *_F_CENTROID)


def _outside_point(spaces: Sequence, dx: float, dy: float
                   ) -> Tuple[float, float]:
    """Punto exterior al volumen construido (medidor, sumidero, regulador)."""
    if not spaces:
        return (round(dx, 4), round(dy, 4))
    x0, y0, x1, y1 = _bbox([pt for s in spaces for pt in s.boundary])
    return (round(x0 + dx, 4), round(y0 + dy, 4))


# -- utilidades del modelo -----------------------------------------------------

def _spaces_of(ctx, spaces: Optional[Iterable]) -> List:
    if spaces is None:
        return list(ctx.architecture.list("SPACE", ctx.project.id))
    return list(spaces)


def _levels_by_id(ctx) -> Dict[str, Any]:
    return {lv.id: lv for lv in ctx.architecture.list("LEVEL", ctx.project.id)}


def _ensure_network(ctx, svc, system: str, origin: str):
    """Devuelve la red del sistema, creándola solo si no existe."""
    name = NETWORK_NAMES[system]
    for candidate in ctx.installations.list("NETWORK", ctx.project.id):
        if candidate.system == system and \
                candidate.name.lower() == name.lower():
            return candidate
    network = svc.create_network(
        name, system,
        description=f"Generada automáticamente ({origin})")
    return network


def _served_spaces(net_id: str, ctx, kinds: Sequence[str]) -> set:
    """IDs de locales que ya tienen terminales de estos tipos en la red."""
    wanted = set(kinds)
    served: set = set()
    for node in ctx.installations.nodes_of(net_id):
        if node.kind in wanted and node.space_id:
            served.add(node.space_id)
    return served


def _count_kind(net_id: str, ctx, kind: str) -> int:
    return sum(1 for n in ctx.installations.nodes_of(net_id)
               if n.kind == kind)


def _find_node(net_id: str, ctx, kind: str, name: str = "") -> Optional[Any]:
    """Primer nodo del tipo (y nombre exacto, si se da) en la red."""
    for node in ctx.installations.nodes_of(net_id):
        if node.kind == kind and (not name or node.name == name):
            return node
    return None


def _anchor_space(level_spaces: List) -> Optional[Any]:
    for wanted in ANCHOR_SPACE_TYPES:
        for space in level_spaces:
            if space.space_type == wanted:
                return space
    return level_spaces[0] if level_spaces else None


def _is_conditioned(space_type: str) -> bool:
    return (space_type not in SERVICE_SPACE_TYPES
            and space_type not in WET_SPACE_TYPES)


def _add_node(ctx, svc, net, kind: str, x: float, y: float, name: str,
              level_ref: str, space_ref: str = "", elevation_m: float = 0.0,
              attrs: Optional[Dict[str, Any]] = None):
    return svc.add_node(net.code, kind, x, y, name=name,
                        level_ref=level_ref, space_ref=space_ref,
                        elevation_m=elevation_m, attrs=attrs)


def _connect(ctx, svc, net, from_ref: str, to_ref: str, system: str,
             slope_pct: float = 0.0) -> int:
    svc.connect(net.code, from_ref, to_ref,
                kind=SEGMENT_BY_SYSTEM[system],
                slope_pct=slope_pct,
                routing="ORTHO")
    return 1


# -- ELÉCTRICA (POWER) ---------------------------------------------------------

def _build_power(ctx, svc, net, levels: Dict[str, Any],
                 spaces: List, origin: str, solar: bool, summary: _Summary
                 ) -> None:
    level_spaces: Dict[str, List] = {}
    for space in spaces:
        level_spaces.setdefault(space.level_id, []).append(space)

    # Niveles de abajo hacia arriba (por elevación) para encadenar los
    # tableros con un montante realista: tablero general → parciales.
    ordered_levels = sorted(
        level_spaces,
        key=lambda lid: (float(getattr(levels.get(lid), "elevation_m", 0.0)
                               or 0.0), lid))
    prev_panel_code = ""
    for level_id in ordered_levels:
        lv_spaces = level_spaces[level_id]
        level = levels.get(level_id)
        level_ref = level.code if level is not None else ""
        elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
        anchor = _anchor_space(lv_spaces)
        if anchor is None:
            continue

        panels = [n for n in ctx.installations.nodes_of(net.id)
                  if n.kind == "PANEL" and n.level_id == level_id]
        # Energía solar (v3.8.0): el arreglo fotovoltaico alimenta el
        # tablero general (primer nivel).  Se crea ANTES que el tablero
        # para que la raíz del árbol radial sea la fuente (validación
        # ARQ-NET-021 del motor: el alcance se mide desde el PRIMER
        # origen de la red).
        inverter_code = ""
        if solar and not prev_panel_code \
                and _find_node(net.id, ctx, "SOURCE") is None:
            if panels:
                summary.warn(
                    "Energía solar: la red eléctrica ya existía sin "
                    "arranque fotovoltaico; no se añadió el arreglo "
                    "(genérala junto con la edificación).")
            else:
                mx, my = _outside_point(spaces, 1.5, 3.0)
                source = _add_node(
                    ctx, svc, net, "SOURCE", mx, my,
                    "Arreglo fotovoltaico", level_ref,
                    elevation_m=elevation + 0.4,
                    attrs={"voltage": 120, "power_kw": 1.5,
                           "origin": origin})
                inverter = _add_node(
                    ctx, svc, net, "PROTECTION",
                    round(mx + 0.6, 4), round(my + 0.4, 4),
                    "Inversor fotovoltaico", level_ref,
                    elevation_m=elevation,
                    attrs={"rating_a": 20, "origin": origin})
                summary.node(2)
                _connect(ctx, svc, net, source.code, inverter.code, "POWER")
                summary.segment()
                inverter_code = inverter.code

        if panels:
            panel = panels[0]
        else:
            px, py = _place_in_space(anchor, 0.12, 0.85)
            panel = _add_node(
                ctx, svc, net, "PANEL", px, py,
                f"Tablero eléctrico {level.name if level is not None else ''}".strip(),
                level_ref, space_ref=anchor.code,
                elevation_m=elevation,
                attrs={"voltage": 120, "origin": origin})
            summary.node()
            summary.network(net.name)
            if inverter_code:
                _connect(ctx, svc, net, inverter_code, panel.code, "POWER")
                summary.segment()
            elif prev_panel_code:
                # Montante desde el tablero del nivel anterior.
                _connect(ctx, svc, net, prev_panel_code, panel.code, "POWER")
                summary.segment()
        prev_panel_code = panel.code

        # Un protector por familia de circuitos del nivel (reutilizados
        # si el asistente ya pasó por aquí: idempotente).
        light_name = (f"Circuito de alumbrado "
                      f"{level.name if level is not None else ''}").strip()
        socket_name = (f"Circuitos de tomas "
                       f"{level.name if level is not None else ''}").strip()
        lights = _find_node(net.id, ctx, "PROTECTION", light_name)
        if lights is None:
            lights = _add_node(
                ctx, svc, net, "PROTECTION",
                round(panel.x + 0.4, 4), round(panel.y - 0.3, 4),
                light_name, level_ref, elevation_m=elevation,
                attrs={"rating_a": 10, "origin": origin})
            summary.node()
            _connect(ctx, svc, net, panel.code, lights.code, "POWER")
            summary.segment()
        sockets = _find_node(net.id, ctx, "PROTECTION", socket_name)
        if sockets is None:
            sockets = _add_node(
                ctx, svc, net, "PROTECTION",
                round(panel.x + 0.4, 4), round(panel.y + 0.3, 4),
                socket_name, level_ref, elevation_m=elevation,
                attrs={"rating_a": 16, "origin": origin})
            summary.node()
            _connect(ctx, svc, net, panel.code, sockets.code, "POWER")
            summary.segment()
        summary.network(net.name)

        served = _served_spaces(net.id, ctx, ("LUMINAIRE", "OUTLET",
                                              "APPLIANCE"))
        n_lights = _count_kind(net.id, ctx, "LUMINAIRE")
        n_sockets = _count_kind(net.id, ctx, "OUTLET")
        n_appl = _count_kind(net.id, ctx, "APPLIANCE")
        for space in lv_spaces:
            if space.id in served:
                continue
            lum_x, lum_y = _place_in_space(space, *_F_CENTROID)
            luminaire = _add_node(
                ctx, svc, net, "LUMINAIRE", lum_x, lum_y,
                f"Luminaria {n_lights + 1}", level_ref,
                space_ref=space.code, elevation_m=elevation + 2.6,
                attrs={"voltage": 120, "power_w": 40, "origin": origin})
            n_lights += 1
            summary.node()
            _connect(ctx, svc, net, lights.code, luminaire.code, "POWER")
            summary.segment()
            area = space.area_m2()
            n_here = 1 if area < _OUTLETS_LARGE_AREA_M2 else 2
            for idx in range(n_here):
                fx = 0.25 if idx == 0 else 0.75
                sx, sy = _place_in_space(space, fx, 0.15)
                outlet = _add_node(
                    ctx, svc, net, "OUTLET", sx, sy,
                    f"Toma {n_sockets + 1}", level_ref,
                    space_ref=space.code, elevation_m=elevation + 0.3,
                    attrs={"voltage": 120, "power_w": 100,
                           "origin": origin})
                n_sockets += 1
                summary.node()
                _connect(ctx, svc, net, sockets.code, outlet.code, "POWER")
                summary.segment()
            if space.space_type in ("LABORATORY", "STERILIZATION_ROOM",
                                    "IMAGING_ROOM"):
                ax, ay = _place_in_space(space, 0.75, 0.7)
                appliance = _add_node(
                    ctx, svc, net, "APPLIANCE", ax, ay,
                    f"Equipo eléctrico {n_appl + 1}", level_ref,
                    space_ref=space.code,
                    elevation_m=elevation + 0.5,
                    attrs={"power_kw": 3.0, "origin": origin})
                n_appl += 1
                summary.node()
                _connect(ctx, svc, net, sockets.code, appliance.code,
                         "POWER")
                summary.segment()


# -- SANITARIA (agua fría + desagüe) -------------------------------------------

def _wet_fixtures(space_type: str) -> Tuple[Tuple[str, float], ...]:
    return FIXTURES_BY_TYPE.get(space_type, ())


def _build_sanitary(ctx, svc, cold, drain, levels: Dict[str, Any],
                    spaces: List, origin: str, summary: _Summary) -> None:
    wet = [s for s in spaces if s.space_type in WET_SPACE_TYPES]
    if not wet:
        summary.warn(
            "Sanitaria: no hay locales húmedos (baños, cocinas o "
            "lavanderías) en lo generado por el asistente; no se "
            "colocaron aparatos.")
        return
    if cold is None or drain is None:
        return  # los módulos del asistente siempre piden ambas redes

    meter_x, meter_y = _outside_point(spaces, -2.0, -1.0)
    meters = [n for n in ctx.installations.nodes_of(cold.id)
              if n.kind == "METER"]
    if meters:
        meter = meters[0]
    else:
        meter = _add_node(ctx, svc, cold, "METER", meter_x, meter_y,
                          "Medidor de agua", "", elevation_m=0.0,
                          attrs={"origin": origin})
        summary.node()
    summary.network(cold.name)

    valves = [n for n in ctx.installations.nodes_of(cold.id)
              if n.kind == "VALVE"]
    if valves:
        valve = valves[0]
    else:
        valve = _add_node(ctx, svc, cold, "VALVE",
                          round(meter_x + 0.8, 4), round(meter_y + 0.4, 4),
                          "Válvula de paso", "", elevation_m=0.0,
                          attrs={"origin": origin})
        summary.node()
        _connect(ctx, svc, cold, meter.code, valve.code, "COLD_WATER")
        summary.segment()

    outfalls = [n for n in ctx.installations.nodes_of(drain.id)
                if n.kind == "OUTFALL"]
    if outfalls:
        outfall = outfalls[0]
    else:
        ox, oy = _outside_point(spaces, -2.0, -2.2)
        outfall = _add_node(ctx, svc, drain, "OUTFALL", ox, oy,
                            "Sumidero exterior", "", elevation_m=-0.6,
                            attrs={"origin": origin})
        summary.node()
    summary.network(drain.name)

    n_fix_cold = _count_kind(cold.id, ctx, "FIXTURE")
    n_fix_drain = _count_kind(drain.id, ctx, "FIXTURE")
    served_cold = _served_spaces(cold.id, ctx, ("FIXTURE",))
    served_drain = _served_spaces(drain.id, ctx, ("FIXTURE",))

    # Posiciones cíclicas por local: cada aparato cae en un punto propio.
    POS = ((0.2, 0.3), (0.5, 0.3), (0.8, 0.3), (0.35, 0.6))
    for space in wet:
        fixtures = _wet_fixtures(space.space_type)
        if not fixtures:
            continue
        level = levels.get(space.level_id)
        level_ref = level.code if level is not None else ""
        elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
        if space.id not in served_cold:
            for idx, (label, units) in enumerate(fixtures):
                fx, fy = POS[idx % len(POS)]
                px, py = _place_in_space(space, fx, fy)
                node = _add_node(
                    ctx, svc, cold, "FIXTURE", px, py,
                    label.capitalize() + f" {n_fix_cold + 1}", level_ref,
                    space_ref=space.code, elevation_m=elevation,
                    attrs={"fixture_kind": label, "fixture_units": units,
                           "origin": origin})
                n_fix_cold += 1
                summary.node()
                _connect(ctx, svc, cold, valve.code, node.code, "COLD_WATER")
                summary.segment()
        if space.id not in served_drain:
            for idx, (label, units) in enumerate(fixtures):
                fx, fy = POS[idx % len(POS)]
                px, py = _place_in_space(space, fx, fy)
                node = _add_node(
                    ctx, svc, drain, "FIXTURE", px, py,
                    label.capitalize() + f" {n_fix_drain + 1}", level_ref,
                    space_ref=space.code, elevation_m=elevation,
                    attrs={"fixture_kind": label, "fixture_units": units,
                           "origin": origin})
                n_fix_drain += 1
                summary.node()
                _connect(ctx, svc, drain, node.code, outfall.code,
                         "SANITARY_DRAINAGE", slope_pct=2.0)
                summary.segment()


# -- HVAC (aire acondicionado + extracción) ------------------------------------

def _build_hvac(ctx, svc, supply, exhaust, levels: Dict[str, Any],
                spaces: List, origin: str, summary: _Summary) -> None:
    level_spaces: Dict[str, List] = {}
    for space in spaces:
        level_spaces.setdefault(space.level_id, []).append(space)

    # Difusores en locales ocupables, alimentados desde una AHU.
    conditioned = [s for s in spaces if _is_conditioned(s.space_type)]
    if conditioned:
        anchor = _anchor_space(spaces)
        ahux, ahuy = _place_in_space(anchor, 0.9, 0.9) if anchor \
            else _outside_point(spaces, 1.0, 1.0)
        ahus = [n for n in ctx.installations.nodes_of(supply.id)
                if n.kind == "AHU"]
        if ahus:
            ahu = ahus[0]
        else:
            ahu = _add_node(ctx, svc, supply, "AHU", ahux, ahuy,
                            "Unidad de tratamiento de aire", "",
                            elevation_m=0.4,
                            attrs={"capacity_btu": 24000,
                                   "origin": origin})
            summary.node()
        summary.network(supply.name)
        served = _served_spaces(supply.id, ctx, ("DIFFUSER",))
        n_diff = _count_kind(supply.id, ctx, "DIFFUSER")
        for space in conditioned:
            if space.id in served:
                continue
            level = levels.get(space.level_id)
            level_ref = level.code if level is not None else ""
            elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
            dx, dy = _place_in_space(space, *_F_CENTROID)
            node = _add_node(ctx, svc, supply, "DIFFUSER", dx, dy,
                             f"Difusor {n_diff + 1}", level_ref,
                             space_ref=space.code,
                             elevation_m=elevation + 2.7,
                             attrs={"air_flow_m3h": 300, "origin": origin})
            n_diff += 1
            summary.node()
            _connect(ctx, svc, supply, ahu.code, node.code, "HVAC_SUPPLY")
            summary.segment()
    else:
        summary.warn(
            "Ventilación mecánica / A/C: no hay locales ocupables para "
            "difusores; solo se generó extracción si procede.")

    # Extractores en locales húmedos hacia un ventilador (sumidero).
    wet = [s for s in spaces if s.space_type in WET_SPACE_TYPES]
    if wet:
        fans = [n for n in ctx.installations.nodes_of(exhaust.id)
                if n.kind == "FAN"]
        if fans:
            fan = fans[0]
        else:
            fx, fy = _outside_point(spaces, 2.2, -1.6)
            fan = _add_node(ctx, svc, exhaust, "FAN", fx, fy,
                            "Extractor principal", "", elevation_m=0.0,
                            attrs={"air_flow_m3h": 500, "origin": origin})
            summary.node()
        summary.network(exhaust.name)
        served = _served_spaces(exhaust.id, ctx, ("EXHAUST",))
        n_exh = _count_kind(exhaust.id, ctx, "EXHAUST")
        for space in wet:
            if space.id in served:
                continue
            level = levels.get(space.level_id)
            level_ref = level.code if level is not None else ""
            elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
            ex, ey = _place_in_space(space, 0.85, 0.85)
            node = _add_node(ctx, svc, exhaust, "EXHAUST", ex, ey,
                             f"Rejilla de extracción {n_exh + 1}",
                             level_ref, space_ref=space.code,
                             elevation_m=elevation + 2.6,
                             attrs={"air_flow_m3h": 120, "origin": origin})
            n_exh += 1
            summary.node()
            _connect(ctx, svc, exhaust, node.code, fan.code, "EXHAUST")
            summary.segment()


# -- INCENDIOS -----------------------------------------------------------------

def _build_fire(ctx, svc, net, levels: Dict[str, Any], spaces: List,
                origin: str, summary: _Summary) -> None:
    if not spaces:
        summary.warn(
            "Protección contra incendios: no hay locales donde colocar "
            "detectores.")
        return
    anchor = _anchor_space(spaces)
    panel_x, panel_y = _place_in_space(anchor, 0.1, 0.1) if anchor \
        else _outside_point(spaces, 0.5, 0.5)
    panels = [n for n in ctx.installations.nodes_of(net.id)
              if n.kind == "FIRE_PANEL"]
    if panels:
        panel = panels[0]
    else:
        panel = _add_node(ctx, svc, net, "FIRE_PANEL", panel_x, panel_y,
                          "Panel de incendios", "",
                          elevation_m=1.4,
                          attrs={"zones": max(1, len(spaces)),
                                 "origin": origin})
        summary.node()
    summary.network(net.name)

    served = _served_spaces(net.id, ctx,
                            ("SMOKE_DETECTOR", "CALL_POINT", "SOUNDER"))
    n_det = _count_kind(net.id, ctx, "SMOKE_DETECTOR")
    n_call = _count_kind(net.id, ctx, "CALL_POINT")
    n_sound = _count_kind(net.id, ctx, "SOUNDER")
    for space in spaces:
        if space.id in served:
            continue
        level = levels.get(space.level_id)
        level_ref = level.code if level is not None else ""
        elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
        dx, dy = _place_in_space(space, 0.5, 0.7)
        node = _add_node(ctx, svc, net, "SMOKE_DETECTOR", dx, dy,
                         f"Detector de humo {n_det + 1}", level_ref,
                         space_ref=space.code, elevation_m=elevation + 2.7,
                         attrs={"coverage_m2": 60, "origin": origin})
        n_det += 1
        summary.node()
        _connect(ctx, svc, net, panel.code, node.code, "FIRE_ALARM")
        if space.space_type == "ENTRANCE":
            cx, cy = _place_in_space(space, 0.3, 0.4)
            node = _add_node(ctx, svc, net, "CALL_POINT", cx, cy,
                             f"Pulsador de alarma {n_call + 1}", level_ref,
                             space_ref=space.code,
                             elevation_m=elevation + 1.2,
                             attrs={"origin": origin})
            n_call += 1
            summary.node()
            _connect(ctx, svc, net, panel.code, node.code, "FIRE_ALARM")
            summary.segment()


# -- TELECOM -------------------------------------------------------------------

def _build_telecom(ctx, svc, net, levels: Dict[str, Any], spaces: List,
                   origin: str, summary: _Summary) -> None:
    if not spaces:
        return
    anchor = _anchor_space(spaces)
    rack_x, rack_y = _place_in_space(anchor, 0.15, 0.5) if anchor \
        else _outside_point(spaces, 0.5, 0.5)
    racks = [n for n in ctx.installations.nodes_of(net.id)
             if n.kind == "RACK"]
    if racks:
        rack = racks[0]
    else:
        rack = _add_node(ctx, svc, net, "RACK", rack_x, rack_y,
                         "Gabinete de comunicaciones", "",
                         elevation_m=1.2,
                         attrs={"units": 12, "origin": origin})
        summary.node()
    summary.network(net.name)

    served = _served_spaces(net.id, ctx, ("TELECOM_OUTLET",))
    n_out = _count_kind(net.id, ctx, "TELECOM_OUTLET")
    for space in spaces:
        if space.id in served or not _is_conditioned(space.space_type):
            continue
        level = levels.get(space.level_id)
        level_ref = level.code if level is not None else ""
        elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
        tx, ty = _place_in_space(space, 0.6, 0.15)
        node = _add_node(ctx, svc, net, "TELECOM_OUTLET", tx, ty,
                         f"Toma de datos {n_out + 1}", level_ref,
                         space_ref=space.code, elevation_m=elevation + 0.3,
                         attrs={"jacks": 2, "origin": origin})
        n_out += 1
        summary.node()
        _connect(ctx, svc, net, rack.code, node.code, "TELECOM")
        summary.segment()


# -- GAS -----------------------------------------------------------------------

def _build_gas(ctx, svc, net, levels: Dict[str, Any], spaces: List,
               origin: str, summary: _Summary) -> None:
    targets = [s for s in spaces if s.space_type in GAS_BY_TYPE]
    if not targets:
        summary.warn(
            "Gas: no hay cocina ni lavandería donde colocar aparatos; "
            "no se generó la red de gas.")
        return
    reg_x, reg_y = _outside_point(spaces, -2.0, -3.2)
    # Raíz de la red de gas: el MEDIDOR (METER es origen válido según
    # SOURCE_KINDS; el regulador cuelga de él, como en la instalación
    # real: acometida → medidor → regulador → aparatos).
    meters = [n for n in ctx.installations.nodes_of(net.id)
              if n.kind == "METER"]
    if meters:
        meter = meters[0]
    else:
        mx, my = _outside_point(spaces, -2.0, -2.4)
        meter = _add_node(ctx, svc, net, "METER", mx, my,
                          "Medidor de gas", "", elevation_m=0.0,
                          attrs={"origin": origin})
        summary.node()
    regulators = [n for n in ctx.installations.nodes_of(net.id)
                  if n.kind == "REGULATOR"]
    regulator_created = False
    if regulators:
        regulator = regulators[0]
    else:
        regulator = _add_node(ctx, svc, net, "REGULATOR", reg_x, reg_y,
                              "Regulador de gas", "", elevation_m=0.0,
                              attrs={"pressure_kpa": 2.8, "origin": origin})
        summary.node()
        regulator_created = True
    if regulator_created or not any(
            s for s in ctx.installations.segments_of(net.id)
            if {s.from_node_id, s.to_node_id} == {meter.id, regulator.id}):
        _connect(ctx, svc, net, meter.code, regulator.code, "GAS")
        summary.segment()
    summary.network(net.name)

    served = _served_spaces(net.id, ctx, ("APPLIANCE",))
    n_app = _count_kind(net.id, ctx, "APPLIANCE")
    for space in targets:
        if space.id in served:
            continue
        level = levels.get(space.level_id)
        level_ref = level.code if level is not None else ""
        elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)
        for label in GAS_BY_TYPE[space.space_type]:
            ax, ay = _place_in_space(space, 0.7, 0.25)
            node = _add_node(ctx, svc, net, "APPLIANCE", ax, ay,
                             label.capitalize() + f" {n_app + 1}", level_ref,
                             space_ref=space.code,
                             elevation_m=elevation + 0.2,
                             attrs={"power_kw": 8.0 if "cocina" in label
                                    else 5.0, "origin": origin})
            n_app += 1
            summary.node()
            _connect(ctx, svc, net, regulator.code, node.code, "GAS")
            summary.segment()


# -- fachadas públicas ----------------------------------------------------------

def systems_for_modules(modules: Iterable[str]) -> List[str]:
    """Sistemas de red que abarcan los módulos elegidos, sin duplicados."""
    out: List[str] = []
    for module in modules:
        for system in MODULE_SYSTEMS.get(module.strip(), ()):
            if system not in out:
                out.append(system)
    return out


def generate_installations(ctx, modules: Iterable[str],
                           usage_type: str = "",
                           origin: str = "asistente de edificación",
                           spaces: Optional[Iterable] = None) -> Dict[str, Any]:
    """Genera (o amplía) las redes de los módulos elegidos.

    Devuelve un resumen: ``redes``/``equipos``/``tramos`` creados,
    ``nombres`` de redes y ``warnings`` amables. Nunca lanza: los
    problemas de un módulo no impiden los demás.
    """
    from services.installations_service import InstallationsService

    svc = InstallationsService(ctx)
    summary = _Summary()
    wanted = [m for m in (m.strip() for m in modules) if m]
    unknown = [m for m in wanted if m not in MODULE_SYSTEMS]
    if unknown:
        summary.warn(
            "Módulos sin generación automática (se ignoraron): "
            + ", ".join(unknown))
    systems = systems_for_modules(wanted)
    if not systems:
        return dict(summary)

    levels = _levels_by_id(ctx)
    all_spaces = _spaces_of(ctx, spaces)
    try:
        solar = "Energía solar" in wanted
        if "POWER" in systems:
            net = _ensure_network(ctx, svc, "POWER", origin)
            _build_power(ctx, svc, net, levels, all_spaces, origin,
                         solar, summary)
        if {"COLD_WATER", "SANITARY_DRAINAGE"} & set(systems):
            cold = _ensure_network(ctx, svc, "COLD_WATER", origin) \
                if "COLD_WATER" in systems else None
            drain = _ensure_network(ctx, svc, "SANITARY_DRAINAGE", origin) \
                if "SANITARY_DRAINAGE" in systems else None
            if cold is not None or drain is not None:
                _build_sanitary(ctx, svc, cold, drain, levels, all_spaces,
                                origin, summary)
        if {"HVAC_SUPPLY", "EXHAUST"} & set(systems):
            supply = _ensure_network(ctx, svc, "HVAC_SUPPLY", origin) \
                if "HVAC_SUPPLY" in systems else None
            exhaust = _ensure_network(ctx, svc, "EXHAUST", origin) \
                if "EXHAUST" in systems else None
            _build_hvac(ctx, svc, supply, exhaust, levels, all_spaces,
                        origin, summary)
        if "FIRE_ALARM" in systems:
            net = _ensure_network(ctx, svc, "FIRE_ALARM", origin)
            _build_fire(ctx, svc, net, levels, all_spaces, origin, summary)
        if "TELECOM" in systems:
            net = _ensure_network(ctx, svc, "TELECOM", origin)
            _build_telecom(ctx, svc, net, levels, all_spaces, origin,
                           summary)
        if "GAS" in systems:
            net = _ensure_network(ctx, svc, "GAS", origin)
            _build_gas(ctx, svc, net, levels, all_spaces, origin, summary)
    except Exception as exc:  # noqa: BLE001 - el asistente no se rompe
        summary.warn(
            f"No pude terminar toda la generación de instalaciones: {exc}")
    return dict(summary)


def connect_local(ctx, space_ref: str,
                  origin: str = "asistente de local") -> Dict[str, Any]:
    """Conecta UN local nuevo (asistente de local) a las instalaciones.

    - Añade luminaria + toma al local dentro de la «Red eléctrica»
      (conectadas al nodo más cercano; si el proyecto no tiene red,
      crea la red con su tablero).
    - Si el local es húmedo, añade sus aparatos a agua fría y desagüe
      (creando esas redes si no existen).
    """
    from services.installations_service import InstallationsService

    svc = InstallationsService(ctx)
    summary = _Summary()
    space = None
    try:
        space = ctx.architecture.get_by_code("SPACE", space_ref) or \
            ctx.architecture.get("SPACE", space_ref)
        if space is None:
            for candidate in ctx.architecture.list("SPACE", ctx.project.id):
                if candidate.name.lower() == space_ref.lower():
                    space = candidate
                    break
    except Exception:  # noqa: BLE001 - el explorador se validará luego
        space = None
    if space is None:
        return dict(summary)

    levels = _levels_by_id(ctx)
    level = levels.get(space.level_id)
    level_ref = level.code if level is not None else ""
    elevation = float(getattr(level, "elevation_m", 0.0) or 0.0)

    try:
        # Eléctrica mínima del local.
        net = _ensure_network(ctx, svc, "POWER", origin)
        nodes = ctx.installations.nodes_of(net.id)
        summary.network(net.name)
        lx, ly = _place_in_space(space, *_F_CENTROID)
        if not nodes:
            px, py = _place_in_space(space, 0.12, 0.85)
            panel = _add_node(ctx, svc, net, "PANEL", px, py,
                              "Tablero eléctrico", level_ref,
                              space_ref=space.code,
                              elevation_m=elevation,
                              attrs={"voltage": 120, "origin": origin})
            summary.node()
            parent = panel.code
        else:
            parent = min(
                nodes,
                key=lambda n: (n.x - lx) ** 2 + (n.y - ly) ** 2).code
        luminaire = _add_node(ctx, svc, net, "LUMINAIRE", lx, ly,
                              "Luminaria 1", level_ref,
                              space_ref=space.code,
                              elevation_m=elevation + 2.6,
                              attrs={"voltage": 120, "power_w": 40,
                                     "origin": origin})
        summary.node()
        _connect(ctx, svc, net, parent, luminaire.code, "POWER")
        sx, sy = _place_in_space(space, 0.25, 0.15)
        outlet = _add_node(ctx, svc, net, "OUTLET", sx, sy, "Toma 1",
                           level_ref, space_ref=space.code,
                           elevation_m=elevation + 0.3,
                           attrs={"voltage": 120, "power_w": 100,
                                  "origin": origin})
        summary.node()
        _connect(ctx, svc, net, parent, outlet.code, "POWER")
        summary.segment(2)

        # Local húmedo → agua fría + desagüe con sus aparatos.
        if space.space_type in WET_SPACE_TYPES:
            cold = _ensure_network(ctx, svc, "COLD_WATER", origin)
            drain = _ensure_network(ctx, svc, "SANITARY_DRAINAGE", origin)
            _build_sanitary(ctx, svc, cold, drain, levels, [space],
                            origin, summary)
    except Exception as exc:  # noqa: BLE001 - el local ya está creado
        summary.warn(f"No pude conectar el local a las instalaciones: {exc}")
    return dict(summary)


__all__ = [
    "MODULE_SYSTEMS", "NETWORK_NAMES", "SEGMENT_BY_SYSTEM",
    "WET_SPACE_TYPES", "SERVICE_SPACE_TYPES", "FIXTURES_BY_TYPE",
    "systems_for_modules", "generate_installations", "connect_local",
]
