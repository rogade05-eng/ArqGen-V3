# -*- coding: utf-8 -*-
"""v3.44.0/v3.45.0 — GEOMETRÍA CURVA/RADIAL (FASE D del despliegue).

``plan_radial`` genera la planta de N SECTORES radiales alrededor de
un núcleo central circular, con corredor ANULAR opcional: el patrón
de las torres y hospitales radiantes de las imágenes de referencia
(núcleo de ascensores + corredor + locales en anillo).

``plan_y`` (v3.45.0) genera la TORRE EN Y REAL: núcleo central
CIRCULAR con el vestíbulo, N alas rectangulares radiantes (3 = la Y
de las residencias y hospitales; 2 = barra doble; 4 = torre X) con
CORREDOR por ala y locales a ambos lados, y cabecera transversal
opcional. El contorno es la Y real (arcos por cuerdas entre alas),
no una caja: el resultado se ve como el plano de referencia.

Los arcos se aproximan por CUERDAS de ``chord_m`` (poligonales de
muchos vértices): el modelo de datos sigue siendo de poligonales,
así que ``aplicar_plan``, el DXF y los renders funcionan sin
cambios. Cero IA, determinista, offline.

Reglas del reparto (explicables):
  * el área del ANILLO de locales (π·(R²−r²)) manda: si el programa
    preferido no cabe lanza ARQ-DDI-011; si sobra espacio, los
    locales CRECEN proporcionalmente hasta llenar el anillo (nunca
    por debajo del mínimo del DNA),
  * cada local ocupa un sub-sector anular con ángulo proporcional a
    su área (área del sector anular = θ/2·(R²−r²)),
  * el VESTÍBULO del programa (si lo hay) va al NÚCLEO (disco
    central), como el lobby de las torres,
  * un local cuyo borde interior es más estrecho que su
    ``minimum_width`` del DNA se documenta en los avisos (no
    bloquea: la geometría radial compromete),
  * la escalera NO se genera (el núcleo se reserva; use el
    asistente de Escaleras).

Reglas de la Y (v3.45.0):
  * el NÚCLEO circular exige VESTÍBULO/ENTRADA en el programa
    (ARQ-DDI-012 si no lo lleva) y las alas exigen que el radio del
    núcleo alcance (ancho_ala/2)/sin(π/n_alas): si no, los brazos
    se solapan junto al disco y lanza ARQ-DDI-012 con la fórmula,
  * el programa se ESCALA hasta llenar las filas de las alas
    (crecimiento proporcional, nunca por debajo del mínimo del
    DNA) y se reparte por DÉFICIT de ala (determinista),
  * cada ala lleva CORREDOR central (piece PASILLO con el campo
    ``ala``) y los locales se colocan al lado con más hueco
    restante, alternando ambas filas como en la planta real,
  * ``cabecera_m`` > 0 reserva el tramo final del ala como sala
    TRANSVERSAL de ancho completo (la cabeza de la Y del hospital):
    su uso es el mayor del programa y se documenta en avisos,
  * ``aplicar_plan`` conecta cada local con el corredor de SU ala
    (pasillos múltiples) y omite el mobiliario automático
    (geometría radiante), como en el anillo radial.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain.servicios_engine import _dna_de as _dna_objeto

PT = Tuple[float, float]


def _arco(centro: PT, radio: float, a0: float, a1: float,
          chord_m: float) -> List[PT]:
    """Puntos sobre el arco (CCW) de a0 a a1 con cuerdas <= chord_m."""
    cx, cy = centro
    if radio <= 0.0:
        return [(cx, cy)]
    span = (a1 - a0) % (2.0 * math.pi)
    if span < 1e-9:
        span = 2.0 * math.pi
    n = max(2, int(math.ceil(span * radio / max(0.05, chord_m))))
    pts: List[PT] = []
    for i in range(n + 1):
        a = a0 + span * i / n
        pts.append((round(cx + radio * math.cos(a), 4),
                    round(cy + radio * math.sin(a), 4)))
    return pts


def _dedup_poligonal(puntos: List[PT], tol: float = 1e-6) -> List[PT]:
    """Quita vértices duplicados CONSECUTIVOS (tol en metros) y el
    cierre repetido con el primero. v3.46.0: las costuras entre la
    esquina de un ala y el extremo del arco en la Y (y el cierre del
    círculo en plan_radial) dejaban aristas de longitud EXACTAMENTE
    0.0; el trazado de muros las rechaza (ARQ-DOM-048)."""
    limpia: List[PT] = []
    for p in puntos:
        if limpia and abs(p[0] - limpia[-1][0]) < tol \
                and abs(p[1] - limpia[-1][1]) < tol:
            continue
        limpia.append((float(p[0]), float(p[1])))
    if len(limpia) >= 2 and abs(limpia[0][0] - limpia[-1][0]) < tol \
            and abs(limpia[0][1] - limpia[-1][1]) < tol:
        limpia.pop()
    return limpia


def _poligono_sector_anular(centro: PT, r_in: float, r_out: float,
                            a0: float, a1: float,
                            chord_m: float) -> List[PT]:
    """Sector anular cerrado: arco exterior a0->a1 + arco interior
    a1->a0 (o el centro si r_in == 0)."""
    ext = _arco(centro, r_out, a0, a1, chord_m)
    if r_in <= 1e-9:
        return ext + [centro]
    int_rev = _arco(centro, r_in, a1, a0, chord_m)
    return _dedup_poligonal(ext + int_rev)


def _niveles_validos(niveles: Any) -> int:
    """v3.47.0: la planta tipo se repite en N niveles (1-20)."""
    nv = 1 if niveles is None else int(niveles)
    if nv < 1 or nv > 20:
        raise DomainError(
            message=f"niveles={nv} fuera de rango (1-20)",
            code="ARQ-DDI-012", context={"niveles": nv},
            suggested_action="Use entre 1 y 20 niveles de planta "
                             "tipo repetida.")
    return nv


def _area_firmada(poly: List[PT]) -> float:
    """Área con signo (positiva si el polígono es CCW)."""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _inter_seg_param(p: PT, q: PT, a: PT, b: PT) -> Optional[float]:
    """Parámetro t en (0,1) donde el segmento pq cruza la RECTA ab
    (solo si el cruce cae dentro del segmento ab); None si no
    cruza."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = dx * ey - dy * ex
    if abs(den) < 1e-12:
        return None
    apx, apy = a[0] - p[0], a[1] - p[1]
    t = (apx * ey - apy * ex) / den
    s = (apx * dy - apy * dx) / den
    if 1e-9 < t < 1.0 - 1e-9 and -1e-9 <= s <= 1.0 + 1e-9:
        return t
    return None


def _punto_en_convexo(p: PT, poly: List[PT], tol: float = 1e-9) \
        -> bool:
    """p dentro (o en el borde) del polígono convexo CCW."""
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cr = (x1 - x0) * (p[1] - y0) - (y1 - y0) * (p[0] - x0)
        if cr < -tol:
            return False
    return True


def _tramos_fuera(p: PT, q: PT, otro: List[PT]) \
        -> List[Tuple[PT, PT]]:
    """Sub-segmentos de [p, q] que caen FUERA del rectángulo
    convexo CCW «otro»: la arista se corta en cada cruce con las
    aristas del otro rect y se conservan los tramos cuyo punto medio
    queda fuera."""
    ts = [0.0, 1.0]
    m = len(otro)
    for i in range(m):
        t = _inter_seg_param(p, q, otro[i], otro[(i + 1) % m])
        if t is not None:
            ts.append(t)
    ts = sorted(ts)
    out: List[Tuple[PT, PT]] = []
    for t0, t1 in zip(ts, ts[1:]):
        if t1 - t0 < 1e-9:
            continue
        mx = p[0] + (q[0] - p[0]) * (t0 + t1) / 2.0
        my = p[1] + (q[1] - p[1]) * (t0 + t1) / 2.0
        if not _punto_en_convexo((mx, my), otro):
            out.append(((p[0] + (q[0] - p[0]) * t0,
                         p[1] + (q[1] - p[1]) * t0),
                        (p[0] + (q[0] - p[0]) * t1,
                         p[1] + (q[1] - p[1]) * t1)))
    return out


def _union_dos_rects(rA: List[PT], rB: List[PT]) -> List[PT]:
    """Contorno de la UNIÓN de dos rectángulos que comparten el
    centro (las barras cruzadas de la X): conserva los tramos de
    cada arista fuera del otro rect y los encadena recorriendo la
    frontera. Devuelve la poligonal cerrada CCW sin vértices
    duplicados (para dos barras perpendiculares son 12 vértices: 8
    esquinas de puntas + 4 entrantes del cruce)."""
    segs: List[Tuple[PT, PT]] = []
    for rect, otro in ((rA, rB), (rB, rA)):
        for i in range(4):
            p, q = rect[i], rect[(i + 1) % 4]
            segs.extend(_tramos_fuera(p, q, otro))
    segs = [((round(a[0], 4), round(a[1], 4)),
             (round(b[0], 4), round(b[1], 4))) for a, b in segs]
    # índice por AMBOS extremos: la frontera puede recorrer un
    # segmento en sentido inverso al de su rect de origen
    desde: Dict[PT, List[int]] = {}
    hasta: Dict[PT, List[int]] = {}
    for k, (a, b) in enumerate(segs):
        desde.setdefault(a, []).append(k)
        hasta.setdefault(b, []).append(k)
    loop: List[PT] = []
    usados: set = set()
    cur = segs[0][0]
    inicio = cur
    loop.append(cur)
    while True:
        k_found = None
        invertido = False
        for k in desde.get(cur, ()):
            if k not in usados:
                k_found = k
                break
        if k_found is None:
            for k in hasta.get(cur, ()):
                if k not in usados:
                    k_found = k
                    invertido = True
                    break
        if k_found is None:
            break
        usados.add(k_found)
        a, b = segs[k_found]
        cur = b if not invertido else a
        loop.append(cur)
    if len(usados) != len(segs) or cur != inicio:
        raise DomainError(
            message="plan_x: no se pudo cerrar el contorno de la "
                    "unión de las dos barras (caso geométrico no "
                    "soportado)",
            code="ARQ-DDI-012", context={"segmentos": len(segs)},
            suggested_action="Use dos barras perpendiculares que se "
                             "cruzan por su centro.")
    loop.pop()  # el último repite el inicio
    if _area_firmada(loop) < 0:
        loop.reverse()
    return _dedup_poligonal(loop)


def _area_poligono(poly: List[PT]) -> float:
    """Área con la fórmula del zapatero (absoluta)."""
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _normas_de(space_type: str) -> Dict[str, Any]:
    """Normas dimensionales del DNA para un space_type (0.0 si no
    está en el registro)."""
    dna = _dna_objeto(None, str(space_type or "").upper())
    if dna is None:
        return {"minimum_area": 0.0, "preferred_area": 0.0,
                "minimum_width": 0.0, "flujo": ""}
    return {
        "minimum_area": float(getattr(dna, "minimum_area", 0.0)
                              or 0.0),
        "preferred_area": float(getattr(dna, "preferred_area", 0.0)
                                or 0.0),
        "minimum_width": float(getattr(dna, "minimum_width", 0.0)
                               or 0.0),
        "flujo": str(getattr(dna, "flujo", "") or "")}


def plan_radial(programa: Dict[str, Any],
                centro: PT = (0.0, 0.0),
                radio_ext: float = 12.0,
                radio_int: float = 0.0,
                sectores: int = 8,
                corredor_m: float = 1.5,
                radio_nucleo: float = 0.0,
                angulo0: float = 0.0,
                chord_m: float = 0.35,
                altura_nivel_m: float = 3.0,
                niveles: int = 1) -> Dict[str, Any]:
    """Planta radial: N sectores de locales alrededor de un núcleo
    circular con corredor anular. Devuelve un análisis con la MISMA
    estructura de ``ajustar`` (``reparto`` por nivel con piezas
    poligonales) para reusar APLICAR_PLAN, métricas y DXF tal cual.
    v3.47.0: ``niveles`` repite la planta tipo en N plantas
    (1-20)."""
    R = float(radio_ext)
    if R < 4.0:
        raise DomainError(
            message=f"plan_radial: radio_ext={R:.2f} m es demasiado "
                    "pequeño (mínimo 4.0 m)",
            code="ARQ-DDI-012",
            context={"radio_ext": R},
            suggested_action="Amplíe el radio exterior del anillo.")
    sectores = max(3, int(sectores or 8))
    if sectores > 36:
        raise DomainError(
            message=f"plan_radial: {sectores} sectores supera el "
                    "tope de 36",
            code="ARQ-DDI-012",
            context={"sectores": sectores},
            suggested_action="Use 36 sectores o menos.")
    corredor_m = max(0.0, float(corredor_m or 0.0))
    radio_nucleo = max(0.0, float(radio_nucleo or 0.0))
    r_hub = max(0.0, float(radio_int or 0.0), radio_nucleo)
    r_locales = r_hub + corredor_m if corredor_m > 0.0 else r_hub
    if R - r_locales < 1.5:
        raise DomainError(
            message="plan_radial: el anillo de locales mide "
                    f"{R - r_locales:.2f} m de fondo (mínimo 1.5 m)",
            code="ARQ-DDI-012",
            context={"radio_ext": R, "r_locales": r_locales},
            suggested_action="Amplíe el radio exterior o reduzca "
                             "corredor/núcleo/radio_int.")
    renglones = [dict(r) for r in (programa.get("renglones") or [])]
    if not renglones:
        raise DomainError(
            message="plan_radial: el programa no lleva renglones",
            code="ARQ-DDI-012",
            context={},
            suggested_action="Genere el programa con programa_quick "
                             "o programa_edificacion.")
    # ---- el VESTÍBULO (o la ENTRADA) va al NÚCLEO ----
    hub: Optional[Dict[str, Any]] = None
    if radio_nucleo > 0.0:
        for r in renglones:
            if r.get("space_type") in ("VESTIBULE", "ENTRANCE"):
                hub = r
                break
        if hub is None:
            raise DomainError(
                message="plan_radial: pidió núcleo central pero el "
                        "programa no lleva vestíbulo/entrada para "
                        "ocuparlo",
                code="ARQ-DDI-012",
                context={"radio_nucleo": radio_nucleo},
                suggested_action="Añada «vestíbulo» al programa o "
                                 "ponga radio_nucleo=0.")
    ring = [r for r in renglones if r is not hub]
    if not ring:
        raise DomainError(
            message="plan_radial: todo el programa cabe en el "
                    "núcleo; no hay locales para el anillo",
            code="ARQ-DDI-012",
            context={},
            suggested_action="Añada locales al programa o reduzca "
                             "el núcleo.")
    # ---- presupuesto de área del anillo ----
    area_anillo = math.pi * (R * R - r_locales * r_locales)
    total_pref = sum(float(r["area_m2"]) for r in ring)
    if total_pref > area_anillo * 0.995:
        raise DomainError(
            message=f"El programa necesita {total_pref:.1f} m2 y el "
                    f"anillo radial ofrece {area_anillo:.1f} m2",
            code="ARQ-DDI-011",
            context={"area_programa": round(total_pref, 2),
                     "area_anillo": round(area_anillo, 2)},
            suggested_action="Amplíe el radio exterior, quite "
                             "locales o reduzca el corredor.")
    factor = area_anillo / max(0.01, total_pref)
    # crecimiento proporcional hasta llenar el anillo, SIN bajar del
    # mínimo del DNA (si el mínimo muerde, los demás absorben)
    escalados: List[Dict[str, Any]] = []
    for r in ring:
        nuevo = float(r["area_m2"]) * factor
        normas = _normas_de(str(r.get("space_type", "")))
        minimo = float(normas["minimum_area"])
        if minimo and nuevo < minimo:
            nuevo = minimo
        q = dict(r, area_m2=round(nuevo, 2))
        q["area_ideal_radial"] = round(float(r["area_m2"]), 2)
        escalados.append(q)
    exceso = sum(float(q["area_m2"]) for q in escalados) - area_anillo
    if exceso > 0.01:
        # los mínimos mordieron: repartir el exceso entre los que
        # están por encima de su mínimo (proporcional, 3 pasadas)
        for _ in range(3):
            flex = [q for q in escalados
                    if float(q["area_m2"])
                    > float(_normas_de(str(q["space_type"]))
                            ["minimum_area"]) + 0.05]
            if not flex:
                break
            suma_flex = sum(float(q["area_m2"]) for q in flex)
            for q in flex:
                q["area_m2"] = round(
                    float(q["area_m2"])
                    - exceso * float(q["area_m2"]) / suma_flex, 2)
            exceso = (sum(float(q["area_m2"])
                          for q in escalados) - area_anillo)
            if exceso <= 0.01:
                break

    altura = max(2.0, float(altura_nivel_m or 3.0))
    avisos: List[str] = [
        f"PLANTA RADIAL (v3.44): {sectores} sectores de "
        f"{2.0 * math.pi / sectores:.3f} rad en un anillo de "
        f"{R - r_locales:.2f} m de fondo; arcos por cuerdas de "
        f"{max(0.05, float(chord_m or 0.35)):.2f} m",
        "la escalera no se genera: reserve el núcleo con el "
        "asistente de Escaleras"]

    # ---- piezas ----
    locales_out: List[Dict[str, Any]] = []
    angulo = float(angulo0 or 0.0)
    # orden: desc por área para sectores sanos (determinista)
    cola = sorted(escalados, key=lambda q: -float(q["area_m2"]))
    indice_sector = 0
    for q in cola:
        area_q = float(q["area_m2"])
        # ángulo del sub-sector anular: A = θ/2 · (R² − r²)
        theta = 2.0 * area_q / max(1e-9, (R * R - r_locales ** 2))
        a0 = angulo
        a1 = angulo + theta
        angulo = a1
        poly = _poligono_sector_anular(centro, r_locales, R,
                                       a0, a1, chord_m)
        normas = _normas_de(str(q.get("space_type", "")))
        ancho_min = float(normas["minimum_width"])
        if ancho_min and r_locales * theta < ancho_min:
            avisos.append(
                f"{q.get('nombre', q.get('space_type'))}: borde "
                f"interior de {r_locales * theta:.2f} m por debajo "
                f"del mínimo del DNA ({ancho_min:.2f} m): la "
                "geometría radial compromete; documente la pieza")
        locales_out.append({
            "codigo": str(q.get("space_type", "ROOM")),
            "nombre": str(q.get("nombre", "Local")),
            "space_type": str(q.get("space_type", "ROOM")),
            "area_m2": round(area_q, 2),
            "flujo": str(q.get("flujo", "")
                         or normas["flujo"]),
            "rect": None, "poligono": poly,
            "contenedor": indice_sector,
            "sector": indice_sector % sectores,
            "area_min": round(float(normas["minimum_area"]), 2)})
        indice_sector += 1

    pasillo_piece: Optional[Dict[str, Any]] = None
    if corredor_m > 0.0:
        poly_cor = _poligono_sector_anular(
            centro, r_hub, r_locales, 0.0, 2.0 * math.pi, chord_m)
        pasillo_piece = {
            "codigo": "PASILLO", "nombre": "Corredor anular",
            "space_type": "CORRIDOR", "flujo": "publico",
            "rect": None, "poligono": poly_cor,
            "area_m2": round(math.pi * (r_locales ** 2
                                        - r_hub ** 2), 2),
            "ancho_m": round(corredor_m, 2), "area_min": 0.0}

    nubecillo: Optional[Dict[str, Any]] = None
    forma_vertices = _dedup_poligonal(
        _arco(centro, R, 0.0, 2.0 * math.pi, chord_m))
    if hub is not None:
        poly_hub = _poligono_sector_anular(
            centro, 0.0, radio_nucleo, 0.0, 2.0 * math.pi, chord_m)
        normas_hub = _normas_de(str(hub.get("space_type", "")))
        area_hub = _area_poligono(poly_hub)
        nubecillo = {
            "codigo": str(hub.get("space_type", "VESTIBULE")),
            "nombre": str(hub.get("nombre", "Núcleo central")),
            "space_type": str(hub.get("space_type", "VESTIBULE")),
            "area_m2": round(area_hub, 2),
            "flujo": "publico",
            "rect": None, "poligono": poly_hub,
            "contenedor": 0, "area_min": round(
                float(normas_hub["minimum_area"]), 2)}
        avisos.append(
            f"el {nubecillo['nombre']} ocupa el NÚCLEO circular de "
            f"{radio_nucleo:.2f} m de radio "
            f"({area_hub:.1f} m2)")

    # ---- validación: todo dentro del círculo (tolerancia de las
    # cuerdas redondeadas a 4 decimales: 1e-3 m) ----
    dentro = True
    piezas_all = ([pasillo_piece] if pasillo_piece else []) \
        + locales_out + ([nubecillo] if nubecillo else [])
    for pieza in piezas_all:
        for p in (pieza.get("poligono") or []):
            if math.hypot(p[0] - centro[0],
                          p[1] - centro[1]) > R + 1e-3:
                dentro = False
                break
        if not dentro:
            break

    area_ocupada = round(sum(float(p["area_m2"])
                             for p in piezas_all), 2)
    area_contorno = round(math.pi * R * R, 2)
    total_prog = round(sum(float(r["area_m2"])
                           for r in renglones), 2)
    renglones_salida = [dict(r) for r in renglones]
    mapa = {id(r): q for r, q in zip(ring, escalados)}
    for k, r in enumerate(renglones):
        q = mapa.get(id(r))
        if q is not None:
            renglones_salida[k]["area_m2"] = q["area_m2"]
    programa_salida = dict(
        programa, renglones=renglones_salida,
        totales=dict(programa.get("totales") or {},
                     area_m2=total_prog))
    nv = _niveles_validos(niveles)
    rep1 = {
        "nivel": 1,
        "pasillo": pasillo_piece,
        "escalera": None,
        "locales": (locales_out
                    + ([nubecillo] if nubecillo else [])),
        "patio": None,
        "area_ocupada": area_ocupada,
        "area_disponible": area_contorno,
        "dentro": dentro,
        "contenedores_usados": [0]}
    reparto = []
    for _k in range(nv):
        r_k = copy.deepcopy(rep1)
        r_k["nivel"] = _k + 1
        reparto.append(r_k)
    if nv > 1:
        avisos.append(
            f"planta tipo repetida en {nv} niveles: reserve las "
            "escaleras con el asistente de Escaleras")
    analisis = {
        "tipo": "radial",
        "forma": {"vertices": forma_vertices,
                  "area_m2": area_contorno,
                  "forma": "circulo",
                  "centro": [round(centro[0], 4),
                             round(centro[1], 4)],
                  "radio_m": round(R, 4)},
        "programa": programa_salida,
        "niveles": nv, "cabe_un_nivel": True,
        "con_escalera": 0, "escalera": None, "patio": None,
        "reparto": reparto,
        "dentro_del_contorno": dentro,
        "sala_distribuidora": False,
        "chaflanes": [],
        "tope_niveles": None,
        "encaje": {"estrategia": "radial",
                   "contenedores": [{
                       "ancho_m": round(2.0 * R, 2),
                       "fondo_m": round(2.0 * R, 2),
                       "area_m2": area_contorno,
                       "x0": round(centro[0] - R, 2),
                       "y0": round(centro[1] - R, 2),
                       "x1": round(centro[0] + R, 2),
                       "y1": round(centro[1] + R, 2)}],
                   "area_aprovechable": round(
                       area_anillo
                       + (math.pi * (r_locales ** 2 - r_hub ** 2)
                          if corredor_m > 0.0 else 0.0), 2)},
        "altura_nivel_m": altura,
        "decisiones": [],
        "radial": {"sectores": sectores,
                   "radio_ext": round(R, 3),
                   "radio_int": round(r_hub, 3),
                   "corredor_m": round(corredor_m, 3),
                   "radio_nucleo": round(radio_nucleo, 3),
                   "chord_m": round(float(chord_m or 0.35), 3)},
        "avisos": avisos,
        "totales": {
            "area_programa": total_prog,
            "area_pasillos": (pasillo_piece["area_m2"]
                              if pasillo_piece else 0.0),
            "area_escaleras": 0.0, "area_patio": 0.0,
            "area_contorno": area_contorno,
            "area_aprovechada": area_ocupada,
            "area_construida": area_ocupada,
            "aprovechamiento_pct": round(
                100.0 * area_ocupada / max(0.01, area_contorno), 2),
            "altura_total": round(float(nv) * altura, 2)},
    }
    return analisis


# ---------------------------------------------------------------------------
# v3.45.0 — TORRE EN Y REAL con núcleo central circular: N alas
# radiantes (3 = Y, 2 = barra doble, 4 = X) con corredor por ala,
# locales a ambos lados y cabecera transversal opcional. El contorno
# es la Y real: discos de cuerdas entre alas + brazos rectangulares.
# ---------------------------------------------------------------------------

_LETRAS_ALA = "ABCDEFGH"
_RETRA = 0.001  # retranqueo de 1 mm: las piezas jamás pisan el borde


def _rotar(p: PT, ct: float, st: float, centro: PT) -> PT:
    """Rota el punto del frame local del ala al sistema del mundo."""
    x, y = p
    return (round(centro[0] + x * ct - y * st, 4),
            round(centro[1] + x * st + y * ct, 4))


def _rect_rotado(x0: float, x1: float, y0: float, y1: float,
                 theta: float, centro: PT) -> List[PT]:
    """Poligonal de 4 vértices del rectángulo del frame local del ala
    (x a lo largo del ala, y perpendicular), rotado al mundo."""
    ct, st = math.cos(theta), math.sin(theta)
    return [_rotar(p, ct, st, centro)
            for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def plan_y(programa: Dict[str, Any],
           centro: PT = (0.0, 0.0),
           radio_nucleo: float = 7.0,
           largo_ala: float = 16.0,
           ancho_ala: float = 11.0,
           n_alas: int = 3,
           corredor_m: float = 1.5,
           cabecera_m: float = 0.0,
           angulo0: float = math.pi / 2.0,
           chord_m: float = 0.35,
           altura_nivel_m: float = 3.0,
           largos_alas: Optional[List[float]] = None,
           niveles: int = 1) -> Dict[str, Any]:
    """Planta de la TORRE EN Y REAL: núcleo circular con el vestíbulo,
    N alas radiantes con corredor central y locales a ambos lados.
    Devuelve un análisis con la MISMA estructura de ``ajustar`` y
    ``plan_radial`` (``reparto`` por nivel, ``pasillos`` múltiples con
    el campo ``ala``) para reusar APLICAR_PLAN, métricas y DXF tal
    cual. v3.47.0: ``largos_alas`` permite alas de longitudes
    DESIGUALES (la estrella radial del hospital oncológico) y
    ``niveles`` repite la planta tipo en N plantas (1-20)."""
    R = float(radio_nucleo)
    L = float(largo_ala)
    a = float(ancho_ala)
    n = int(n_alas or 3)
    cor = max(0.0, float(corredor_m or 0.0))
    cab = max(0.0, float(cabecera_m or 0.0))
    chord = max(0.05, float(chord_m or 0.35))
    if largos_alas:
        Ls = [float(x) for x in largos_alas]
        if len(Ls) != n:
            raise DomainError(
                message=f"plan_y: largos_alas trae {len(Ls)} valores "
                        f"y hay {n} alas",
                code="ARQ-DDI-012",
                context={"largos_alas": largos_alas, "n_alas": n},
                suggested_action="Pase un largo por cada ala.")
        if min(Ls) < 3.0:
            raise DomainError(
                message=f"plan_y: hay alas de {min(Ls):.2f} m "
                        "(mínimo 3.0 m)",
                code="ARQ-DDI-012", context={"largos_alas": Ls},
                suggested_action="Alargue las alas cortas.")
    else:
        Ls = [L] * n
    utils = [max(0.0, Li - cab) for Li in Ls]
    if n < 2 or n > 8:
        raise DomainError(
            message=f"plan_y: {n} alas fuera de rango (2-8; la Y son "
                    "3 alas)",
            code="ARQ-DDI-012", context={"n_alas": n},
            suggested_action="Use 2 (barra doble), 3 (Y) o 4 (X) "
                             "alas.")
    if L < 3.0:
        raise DomainError(
            message=f"plan_y: largo_ala={L:.2f} m es demasiado corto "
                    "(mínimo 3.0 m)",
            code="ARQ-DDI-012", context={"largo_ala": L},
            suggested_action="Alargue las alas de la Y.")
    if a < 4.0:
        raise DomainError(
            message=f"plan_y: ancho_ala={a:.2f} m no deja sitio a dos "
                    "filas de locales con corredor (mínimo 4.0 m)",
            code="ARQ-DDI-012", context={"ancho_ala": a},
            suggested_action="Ensanche las alas o quite el corredor.")
    if a - cor < 2.4:
        raise DomainError(
            message="plan_y: el corredor de "
                    f"{cor:.2f} m no deja dos filas de al menos 1.2 m "
                    f"en un ala de {a:.2f} m",
            code="ARQ-DDI-012",
            context={"ancho_ala": a, "corredor_m": cor},
            suggested_action="Reduzca el corredor o ensanche el ala.")
    if cab and (cab < 3.0 or cab > min(Ls) - 3.0):
        raise DomainError(
            message=f"plan_y: cabecera_m={cab:.2f} fuera de rango "
                    "(3.0 m mínimo y dejando 3.0 m de filas en la "
                    f"ala más corta de {min(Ls):.2f} m)",
            code="ARQ-DDI-012", context={"cabecera_m": cab,
                                         "largos_alas": Ls},
            suggested_action="Use una cabecera de 3.0 m o más sin "
                             "comerse las filas.")
    # ---- las alas no pueden solaparse junto al núcleo ----
    r_min = (a / 2.0) / math.sin(math.pi / n)
    if R + 1e-9 < r_min:
        raise DomainError(
            message="plan_y: con "
                    f"{n} alas de {a:.2f} m el núcleo necesita radio "
                    f"{r_min:.2f} m (pedido {R:.2f} m): los brazos se "
                    "solapan junto al disco",
            code="ARQ-DDI-012",
            context={"radio_nucleo": R, "radio_minimo":
                     round(r_min, 3), "n_alas": n,
                     "ancho_ala": a},
            suggested_action="Suba radio_nucleo a "
                             f"{math.ceil(r_min * 10) / 10:.1f} m o "
                             "reduzca el ancho de ala.")
    renglones = [dict(r) for r in (programa.get("renglones") or [])]
    if not renglones:
        raise DomainError(
            message="plan_y: el programa no lleva renglones",
            code="ARQ-DDI-012", context={},
            suggested_action="Genere el programa con programa_quick "
                             "o programa_edificacion.")
    hub: Optional[Dict[str, Any]] = None
    for r in renglones:
        if r.get("space_type") in ("VESTIBULE", "ENTRANCE"):
            hub = r
            break
    if hub is None:
        raise DomainError(
            message="plan_y: la Y exige un VESTÍBULO/ENTRADA para el "
                    "núcleo central y el programa no lo lleva",
            code="ARQ-DDI-012", context={"n_alas": n},
            suggested_action="Añada «vestíbulo» al programa (el núcleo "
                             "central de la Y lo ocupa).")
    ring = [r for r in renglones if r is not hub]
    if not ring:
        raise DomainError(
            message="plan_y: todo el programa es el vestíbulo; no hay "
                    "locales para las alas",
            code="ARQ-DDI-012", context={},
            suggested_action="Añada locales al programa.")
    # ---- presupuesto de área de las filas de las alas ----
    prof = (a - cor) / 2.0 - _RETRA      # fondo de fila (retranqueado)
    disp_total = sum(2.0 * prof * u for u in utils)
    total_pref = sum(float(r["area_m2"]) for r in ring)
    if total_pref > disp_total * 0.995:
        raise DomainError(
            message=f"El programa necesita {total_pref:.1f} m2 y las "
                    f"filas de {n} alas ofrecen {disp_total:.1f} m2",
            code="ARQ-DDI-011",
            context={"area_programa": round(total_pref, 2),
                     "area_alas": round(disp_total, 2)},
            suggested_action="Alargue o ensanche las alas, quite "
                             "locales o reduzca el corredor.")
    factor = disp_total / max(0.01, total_pref)
    escalados: List[Dict[str, Any]] = []
    for r in ring:
        nuevo = float(r["area_m2"]) * factor
        normas = _normas_de(str(r.get("space_type", "")))
        minimo = float(normas["minimum_area"])
        if minimo and nuevo < minimo:
            nuevo = minimo
        q = dict(r, area_m2=round(nuevo, 2))
        q["area_ideal_y"] = round(float(r["area_m2"]), 2)
        escalados.append(q)
    exceso = sum(float(q["area_m2"]) for q in escalados) - disp_total
    if exceso > 0.01:
        for _ in range(3):
            flex = [q for q in escalados
                    if float(q["area_m2"])
                    > float(_normas_de(str(q["space_type"]))
                            ["minimum_area"]) + 0.05]
            if not flex:
                break
            suma_flex = sum(float(q["area_m2"]) for q in flex)
            for q in flex:
                q["area_m2"] = round(
                    float(q["area_m2"])
                    - exceso * float(q["area_m2"]) / suma_flex, 2)
            exceso = (sum(float(q["area_m2"]) for q in escalados)
                      - disp_total)
            if exceso <= 0.01:
                break

    altura = max(2.0, float(altura_nivel_m or 3.0))
    ang_entre = 2.0 * math.pi / n
    desc_largos = (", ".join(f"{Li:.1f}" for Li in Ls)
                   if largos_alas else f"{L:.1f}")
    avisos: List[str] = [
        f"TORRE EN Y REAL (v3.45): {n} alas radiantes de "
        f"{desc_largos} m de largo x {a:.1f} m cada "
        f"{math.degrees(ang_entre):.0f} grados alrededor de un núcleo "
        f"circular de {R:.2f} m de radio; el radio mínimo sin "
        f"solapar alas es {r_min:.2f} m",
        f"filas de locales con {prof:.2f} m de fondo a ambos lados "
        f"del corredor de {cor:.2f} m",
        "la escalera no se genera: reserve el núcleo con el "
        "asistente de Escaleras"]
    if cab:
        avisos.append(
            f"cabecera transversal de {cab:.2f} m al fondo de cada "
            "ala con el uso mayor del programa")

    # ---- colocación GLOBAL en las 2·n filas: cada local va a la
    # fila con MÁS HUECO restante (tie-break: ala menor, luego el
    # lado +). Así se llena una ala antes de abrir la siguiente,
    # los dos lados van pareja y los anchos jamás desbordan la
    # fila (bin-packing 1D con capacidad = util por fila) ----
    locales_out: List[Dict[str, Any]] = []
    pasillos_out: List[Dict[str, Any]] = []
    cabeceras_out: List[Dict[str, Any]] = []
    mayor = max(escalados, key=lambda t: (
        float(t["area_m2"]), str(t.get("space_type", "")))) \
        if escalados else None
    dentro = True
    usados_fila: List[Dict[str, float]] = [
        {"+": 0.0, "-": 0.0} for _ in range(n)]
    ultimas: List[Dict[str, Dict[str, Any]]] = [
        {"+": None, "-": None} for _ in range(n)]
    sin_hueco: List[str] = []
    thetas = [float(angulo0) + i * ang_entre for i in range(n)]
    for i in range(n):
        theta = thetas[i]
        ct, st = math.cos(theta), math.sin(theta)
        letra = _LETRAS_ALA[i % len(_LETRAS_ALA)]
        if cor > 0.0:
            poly_cor = _rect_rotado(R, R + utils[i], -cor / 2.0,
                                    cor / 2.0, theta, centro)
            pasillos_out.append({
                "codigo": "PASILLO",
                "nombre": f"Corredor ala {letra}",
                "space_type": "CORRIDOR", "flujo": "publico",
                "rect": None, "poligono": poly_cor,
                "area_m2": round(utils[i] * cor, 2),
                "ancho_m": round(cor, 2), "ala": i,
                "area_min": 0.0})
        if cab:
            poly_cab = _rect_rotado(R + utils[i], R + Ls[i],
                                    -(a / 2.0 - _RETRA),
                                    a / 2.0 - _RETRA, theta, centro)
            normas_mayor = _normas_de(str(mayor.get("space_type", ""))
                                      if mayor else "ROOM")
            area_cab = round(cab * (a - 2.0 * _RETRA), 2)
            if float(normas_mayor["minimum_area"]) \
                    and area_cab < float(normas_mayor["minimum_area"]):
                avisos.append(
                    f"la cabecera del ala {letra} mide "
                    f"{area_cab:.1f} m2 por debajo del mínimo del "
                    f"{mayor.get('nombre', 'uso mayor')}: documente "
                    "la pieza")
            cabeceras_out.append({
                "codigo": str(mayor.get("space_type", "ROOM"))
                if mayor else "ROOM",
                "nombre": f"Cabecera ala {letra} ("
                          f"{mayor.get('nombre', 'uso mayor')})"
                if mayor else f"Cabecera ala {letra}",
                "space_type": str(mayor.get("space_type", "ROOM"))
                if mayor else "ROOM",
                "area_m2": area_cab,
                "flujo": str(normas_mayor["flujo"]),
                "rect": None, "poligono": poly_cab,
                "contenedor": i, "ala": i,
                "area_min": round(float(
                    normas_mayor["minimum_area"]), 2)})
    for q in sorted(escalados, key=lambda t: (
            -float(t["area_m2"]), str(t.get("space_type", "")),
            str(t.get("nombre", "")))):
        bins = []
        for i in range(n):
            for lado in ("+", "-"):
                bins.append((-(utils[i] - usados_fila[i][lado]), i,
                             lado))
        bins.sort(key=lambda t: (t[0], t[1],
                                 0 if t[2] == "+" else 1))
        _, i, lado = bins[0]
        resto = utils[i] - usados_fila[i][lado]
        if resto <= 0.05:
            sin_hueco.append(str(q.get("nombre",
                                       q.get("space_type"))))
            continue
        area_q = float(q["area_m2"])
        w = area_q / max(1e-9, prof)
        w_final = min(w, resto)
        theta = thetas[i]
        ct, st = math.cos(theta), math.sin(theta)
        letra = _LETRAS_ALA[i % len(_LETRAS_ALA)]
        x0 = R + usados_fila[i][lado]
        x1 = R + usados_fila[i][lado] + w_final
        if lado == "+":
            y0, y1 = cor / 2.0, a / 2.0 - _RETRA
        else:
            y0, y1 = -(a / 2.0 - _RETRA), -cor / 2.0
        poly = _rect_rotado(x0, x1, y0, y1, theta, centro)
        area_real = round(w_final * (y1 - y0), 2)
        nombre_ala = f"{q.get('nombre', 'Local')} (ala {letra})"
        normas = _normas_de(str(q.get("space_type", "")))
        pieza = {
            "codigo": str(q.get("space_type", "ROOM")),
            "nombre": nombre_ala,
            "space_type": str(q.get("space_type", "ROOM")),
            "area_m2": area_real,
            "flujo": str(q.get("flujo", "") or normas["flujo"]),
            "rect": None, "poligono": poly,
            "contenedor": i, "ala": i,
            "area_min": round(float(normas["minimum_area"]), 2)}
        if float(normas["minimum_width"]) \
                and (y1 - y0) < float(normas["minimum_width"]):
            avisos.append(
                f"{nombre_ala}: fondo de {y1 - y0:.2f} m por "
                "debajo del mínimo del DNA "
                f"({float(normas['minimum_width']):.2f} m): "
                "documente la pieza")
        if float(normas["minimum_area"]) \
                and area_real < float(normas["minimum_area"]) - 0.01:
            avisos.append(
                f"{nombre_ala}: {area_real:.2f} m2 por debajo del "
                f"mínimo del DNA "
                f"({float(normas['minimum_area']):.2f} m2) al "
                "cerrar la fila: documente la pieza")
        locales_out.append(pieza)
        ultimas[i][lado] = pieza
        usados_fila[i][lado] += w_final
        # verificación por franja (frame local): todo el ala. La
        # tolerancia cubre el redondeo de 4 decimales de las
        # poligonales (error ≈ 1.4e-4 al des-rotar)
        for px, py in poly:
            dx, dy = px - centro[0], py - centro[1]
            u = dx * ct + dy * st
            v = -dx * st + dy * ct
            if not (R - 1e-3 <= u <= R + Ls[i] + 1e-3
                    and -a / 2.0 - 1e-3 <= v <= a / 2.0 + 1e-3):
                dentro = False
    if sin_hueco:
        raise DomainError(
            message="plan_y: el programa apenas cabe: los mínimos "
                    f"del DNA llenaron las filas y {len(sin_hueco)} "
                    "local(es) no tienen hueco ("
                    + ", ".join(sin_hueco[:3]) + ")",
            code="ARQ-DDI-011",
            context={"n_alas": n, "sin_hueco": sin_hueco},
            suggested_action="Alargue o ensanche las alas, quite "
                             "locales o reduzca el corredor.")
    # ---- cierre fino: el ÚLTIMO local de cada fila crece hasta el
    # fondo del ala (la fila llega exacta a la cabecera o al
    # frente, como la planta real) ----
    for i in range(n):
        theta = thetas[i]
        ct_c, st_c = math.cos(theta), math.sin(theta)
        for lado in ("+", "-"):
            resto = utils[i] - usados_fila[i][lado]
            pieza = ultimas[i][lado]
            if resto > 0.02 and pieza is not None:
                poly_v = list(pieza["poligono"])
                us = [(dx * ct_c + dy * st_c, k)
                      for k, (dx, dy) in enumerate(
                          (p[0] - centro[0], p[1] - centro[1])
                          for p in poly_v)]
                u_max = max(u for u, _ in us)
                for u, k in us:
                    if u_max - u < 1e-4:
                        px, py = poly_v[k]
                        poly_v[k] = (round(
                            px + resto * ct_c, 4),
                            round(py + resto * st_c, 4))
                pieza["poligono"] = poly_v
                pieza["area_m2"] = round(
                    float(pieza["area_m2"]) + resto * prof, 2)
                usados_fila[i][lado] += resto
    # ---- cabeceras y pasillos también dentro de su franja ----
    for pieza in pasillos_out + cabeceras_out:
        i = int(pieza["ala"])
        theta = float(angulo0) + i * ang_entre
        ct, st = math.cos(theta), math.sin(theta)
        for px, py in pieza["poligono"]:
            dx, dy = px - centro[0], py - centro[1]
            u = dx * ct + dy * st
            v = -dx * st + dy * ct
            if not (R - 1e-3 <= u <= R + Ls[i] + 1e-3
                    and -a / 2.0 - 1e-3 <= v <= a / 2.0 + 1e-3):
                dentro = False
                break

    # ---- núcleo circular con el vestíbulo ----
    nubecillo: Dict[str, Any] = {
        "codigo": str(hub.get("space_type", "VESTIBULE")),
        "nombre": str(hub.get("nombre", "Núcleo central")),
        "space_type": str(hub.get("space_type", "VESTIBULE")),
        "area_m2": 0.0, "flujo": "publico",
        "rect": None, "poligono": _poligono_sector_anular(
            centro, 0.0, R - _RETRA, 0.0, 2.0 * math.pi, chord),
        "contenedor": 0, "ala": -1, "area_min": round(float(
            _normas_de(str(hub.get("space_type", "")))
            ["minimum_area"]), 2)}
    nubecillo["area_m2"] = round(
        _area_poligono(nubecillo["poligono"]), 2)
    for px, py in nubecillo["poligono"]:
        if math.hypot(px - centro[0], py - centro[1]) > R + 1e-3:
            dentro = False
            break
    avisos.append(
        f"el {nubecillo['nombre']} ocupa el NÚCLEO circular de "
        f"{R:.2f} m de radio ({nubecillo['area_m2']:.1f} m2) y "
        "reparte el acceso a los corredores de las "
        f"{n} alas")

    # ---- contorno: la Y REAL (arcos entre alas + brazos) ----
    s_borde = math.sqrt(max(0.0, R * R - (a / 2.0) ** 2))
    delta = math.atan2(a / 2.0, s_borde)
    vertices: List[PT] = []
    for i in range(n):
        theta = float(angulo0) + i * ang_entre
        ct, st = math.cos(theta), math.sin(theta)
        for p_local in ((s_borde, -a / 2.0), (R + Ls[i], -a / 2.0),
                        (R + Ls[i], a / 2.0), (s_borde, a / 2.0)):
            vertices.append(_rotar(p_local, ct, st, centro))
        a0 = theta + delta
        a1 = theta + ang_entre - delta
        span = (a1 - a0) % (2.0 * math.pi)
        if span > 1e-9:
            vertices.extend(_arco(centro, R, a0, a1, chord))
    # v3.46.0: las costuras esquina-de-ala -> arco repetían el vértice
    # (longitud 0.0) y el trazado de muros los rechazaba (DOM-048)
    vertices = _dedup_poligonal(vertices)
    area_contorno = round(_area_poligono(vertices), 2)

    piezas_all = locales_out + pasillos_out + cabeceras_out \
        + [nubecillo]
    area_ocupada = round(sum(float(p["area_m2"])
                             for p in piezas_all), 2)
    total_prog = round(sum(float(r["area_m2"])
                           for r in renglones), 2)
    renglones_salida = [dict(r) for r in renglones]
    mapa = {id(r): q for r, q in zip(ring, escalados)}
    for k, r in enumerate(renglones):
        q = mapa.get(id(r))
        if q is not None:
            renglones_salida[k]["area_m2"] = q["area_m2"]
    programa_salida = dict(
        programa, renglones=renglones_salida,
        totales=dict(programa.get("totales") or {},
                     area_m2=total_prog))
    xs = [p[0] for p in vertices]
    ys = [p[1] for p in vertices]
    perimetro = sum(
        math.hypot(vertices[(k + 1) % len(vertices)][0] - p[0],
                   vertices[(k + 1) % len(vertices)][1] - p[1])
        for k, p in enumerate(vertices))
    contenedores = []
    for i in range(n):
        theta = float(angulo0) + i * ang_entre
        ct, st = math.cos(theta), math.sin(theta)
        esquinas = [_rotar(p, ct, st, centro)
                    for p in ((R, -a / 2.0), (R + Ls[i], -a / 2.0),
                              (R + Ls[i], a / 2.0), (R, a / 2.0))]
        ex = [p[0] for p in esquinas]
        ey = [p[1] for p in esquinas]
        contenedores.append({
            "ancho_m": round(Ls[i], 2), "fondo_m": round(a, 2),
            "area_m2": round(Ls[i] * a, 2),
            "x0": round(min(ex), 2), "y0": round(min(ey), 2),
            "x1": round(max(ex), 2), "y1": round(max(ey), 2)})
    nv = _niveles_validos(niveles)
    rep1 = {
        "nivel": 1,
        "pasillo": (pasillos_out[0] if pasillos_out else None),
        "pasillos": pasillos_out,
        "escalera": None,
        "locales": (locales_out + cabeceras_out
                    + [nubecillo]),
        "patio": None,
        "area_ocupada": area_ocupada,
        "area_disponible": area_contorno,
        "dentro": dentro,
        "contenedores_usados": list(range(n))}
    reparto = []
    for _k in range(nv):
        r_k = copy.deepcopy(rep1)
        r_k["nivel"] = _k + 1
        reparto.append(r_k)
    if nv > 1:
        avisos.append(
            f"planta tipo repetida en {nv} niveles: reserve las "
            "escaleras con el asistente de Escaleras")
    analisis = {
        "tipo": "y_radial",
        "forma": {"vertices": vertices,
                  "area_m2": area_contorno,
                  "forma": "y_radial",
                  "centro": [round(centro[0], 4),
                             round(centro[1], 4)],
                  "radio_nucleo_m": round(R, 4),
                  "bbox": [round(min(xs), 3), round(min(ys), 3),
                           round(max(xs), 3), round(max(ys), 3)],
                  "alineado": False,
                  "ancho_m": round(max(xs) - min(xs), 2),
                  "fondo_m": round(max(ys) - min(ys), 2),
                  "perimetro_m": round(perimetro, 2)},
        "programa": programa_salida,
        "niveles": nv, "cabe_un_nivel": True,
        "con_escalera": 0, "escalera": None, "patio": None,
        "reparto": reparto,
        "dentro_del_contorno": dentro,
        "sala_distribuidora": False,
        "chaflanes": [],
        "tope_niveles": None,
        "encaje": {"estrategia": "y_radial",
                   "contenedores": contenedores,
                   "area_aprovechable": round(disp_total, 2)},
        "altura_nivel_m": altura,
        "decisiones": [],
        "y_radial": {"n_alas": n,
                     "radio_nucleo": round(R, 3),
                     "largo_ala": round(L, 3),
                     "largos_alas": ([round(x, 3) for x in Ls]
                                     if largos_alas else None),
                     "ancho_ala": round(a, 3),
                     "corredor_m": round(cor, 3),
                     "cabecera_m": round(cab, 3),
                     "angulo0_deg": round(
                         math.degrees(float(angulo0)), 1),
                     "chord_m": round(chord, 3)},
        "avisos": avisos,
        "totales": {
            "area_programa": total_prog,
            "area_pasillos": round(sum(float(p["area_m2"])
                                       for p in pasillos_out), 2),
            "area_escaleras": 0.0, "area_patio": 0.0,
            "area_contorno": area_contorno,
            "area_aprovechada": area_ocupada,
            "area_construida": area_ocupada,
            "aprovechamiento_pct": round(
                100.0 * area_ocupada / max(0.01, area_contorno), 2),
            "altura_total": round(float(nv) * altura, 2)},
    }
    return analisis


# ---------------------------------------------------------------------------
# v3.47.0 — HOSPITAL EN X REAL: dos barras perpendiculares que se
# CRUZAN por el centro (el cruce es el HUB con el vestíbulo, como la
# recepción del hospital en X de referencia), corredor por brazo y
# locales a ambos lados. El contorno es la UNIÓN de las dos barras
# (12 vértices: 8 esquinas de puntas + 4 entrantes del cruce),
# totalmente ortogonal — ideal para DXF/BIM. angulo rota la X entera
# (45 grados = X, 0 grados = cruz en +).
# ---------------------------------------------------------------------------

def plan_x(programa: Dict[str, Any],
           centro: PT = (0.0, 0.0),
           largo_barra: float = 64.0,
           ancho_barra: float = 14.0,
           corredor_m: float = 2.0,
           cabecera_m: float = 0.0,
           angulo: float = math.radians(45.0),
           altura_nivel_m: float = 3.2,
           niveles: int = 1) -> Dict[str, Any]:
    """Planta del HOSPITAL EN X REAL: dos barras perpendiculares de
    ``largo_barra`` x ``ancho_barra`` que se cruzan por el centro; el
    CRUCE es el hub central (el VESTÍBULO/ENTRADA del programa reparte
    el acceso a los 4 corredores de los brazos) y los locales van a
    ambos lados de cada corredor (8 filas). ``angulo`` rota la X
    entera (45 grados = X diagonal, 0 = cruz en +). Devuelve el
    análisis con la MISMA estructura de ``plan_y`` (``pasillos``
    múltiples con el campo ``ala``) para reusar APLICAR_PLAN,
    métricas y DXF tal cual. ``niveles`` repite la planta tipo."""
    L = float(largo_barra)
    a = float(ancho_barra)
    cor = max(0.0, float(corredor_m or 0.0))
    cab = max(0.0, float(cabecera_m or 0.0))
    th0 = float(angulo or 0.0)
    nv = _niveles_validos(niveles)
    brazo = L / 2.0 - a / 2.0   # largo útil de cada brazo (tras el cruce)
    if L < 6.0:
        raise DomainError(
            message=f"plan_x: largo_barra={L:.2f} m es demasiado corto "
                    "(mínimo 6.0 m)",
            code="ARQ-DDI-012", context={"largo_barra": L},
            suggested_action="Alargue las barras de la X.")
    if a < 4.0:
        raise DomainError(
            message=f"plan_x: ancho_barra={a:.2f} m no deja sitio a "
                    "dos filas de locales con corredor (mínimo 4.0 m)",
            code="ARQ-DDI-012", context={"ancho_barra": a},
            suggested_action="Ensanche las barras o quite el corredor.")
    if a - cor < 2.4:
        raise DomainError(
            message="plan_x: el corredor de "
                    f"{cor:.2f} m no deja dos filas de al menos 1.2 m "
                    f"en una barra de {a:.2f} m",
            code="ARQ-DDI-012",
            context={"ancho_barra": a, "corredor_m": cor},
            suggested_action="Reduzca el corredor o ensanche la barra.")
    if brazo < 3.0:
        raise DomainError(
            message="plan_x: el brazo tras el cruce mide "
                    f"{brazo:.2f} m (mínimo 3.0 m): la barra es "
                    "demasiado corta para su ancho",
            code="ARQ-DDI-012", context={"brazo": round(brazo, 3),
                                         "largo_barra": L,
                                         "ancho_barra": a},
            suggested_action="Alargue la barra (largo >= ancho + 6.0 "
                             "m).")
    if cab and (cab < 3.0 or cab > brazo - 3.0):
        raise DomainError(
            message=f"plan_x: cabecera_m={cab:.2f} fuera de rango "
                    "(3.0 m mínimo y dejando 3.0 m de filas por "
                    "brazo)",
            code="ARQ-DDI-012", context={"cabecera_m": cab,
                                         "brazo": round(brazo, 3)},
            suggested_action="Use una cabecera de 3.0 m o más sin "
                             "comerse las filas.")
    renglones = [dict(r) for r in (programa.get("renglones") or [])]
    if not renglones:
        raise DomainError(
            message="plan_x: el programa no lleva renglones",
            code="ARQ-DDI-012", context={},
            suggested_action="Genere el programa con programa_quick "
                             "o programa_edificacion.")
    hub: Optional[Dict[str, Any]] = None
    for r in renglones:
        if r.get("space_type") in ("VESTIBULE", "ENTRANCE"):
            hub = r
            break
    if hub is None:
        raise DomainError(
            message="plan_x: la X exige un VESTÍBULO/ENTRADA para el "
                    "hub central (el cruce de las barras) y el "
                    "programa no lo lleva",
            code="ARQ-DDI-012", context={},
            suggested_action="Añada «vestíbulo» al programa (el cruce "
                             "de las barras lo ocupa).")
    ring = [r for r in renglones if r is not hub]
    if not ring:
        raise DomainError(
            message="plan_x: todo el programa es el vestíbulo; no hay "
                    "locales para los brazos",
            code="ARQ-DDI-012", context={},
            suggested_action="Añada locales al programa.")
    # ---- presupuesto de área de las 8 filas (4 brazos x 2 lados) ----
    prof = (a - cor) / 2.0 - _RETRA
    util = brazo - cab
    disp_total = 8.0 * prof * util
    total_pref = sum(float(r["area_m2"]) for r in ring)
    if total_pref > disp_total * 0.995:
        raise DomainError(
            message=f"El programa necesita {total_pref:.1f} m2 y las "
                    f"filas de los 4 brazos ofrecen "
                    f"{disp_total:.1f} m2",
            code="ARQ-DDI-011",
            context={"area_programa": round(total_pref, 2),
                     "area_brazos": round(disp_total, 2)},
            suggested_action="Alargue o ensanche las barras, quite "
                             "locales o reduzca el corredor.")
    factor = disp_total / max(0.01, total_pref)
    escalados: List[Dict[str, Any]] = []
    for r in ring:
        nuevo = float(r["area_m2"]) * factor
        normas = _normas_de(str(r.get("space_type", "")))
        minimo = float(normas["minimum_area"])
        if minimo and nuevo < minimo:
            nuevo = minimo
        q = dict(r, area_m2=round(nuevo, 2))
        q["area_ideal_x"] = round(float(r["area_m2"]), 2)
        escalados.append(q)
    exceso = sum(float(q["area_m2"]) for q in escalados) - disp_total
    if exceso > 0.01:
        for _ in range(3):
            flex = [q for q in escalados
                    if float(q["area_m2"])
                    > float(_normas_de(str(q["space_type"]))
                            ["minimum_area"]) + 0.05]
            if not flex:
                break
            suma_flex = sum(float(q["area_m2"]) for q in flex)
            for q in flex:
                q["area_m2"] = round(
                    float(q["area_m2"])
                    - exceso * float(q["area_m2"]) / suma_flex, 2)
            exceso = (sum(float(q["area_m2"]) for q in escalados)
                      - disp_total)
            if exceso <= 0.01:
                break

    altura = max(2.0, float(altura_nivel_m or 3.2))
    thetas = [th0 + k * math.pi / 2.0 for k in range(4)]
    avisos: List[str] = [
        f"HOSPITAL EN X REAL (v3.47): 2 barras de {L:.1f} x {a:.1f} m "
        f"cruzadas a {math.degrees(th0) % 90.0:.0f} grados de la "
        "horizontal con el HUB central en el cruce ("
        f"{hub.get('nombre', 'vestíbulo')} de "
        f"{a:.1f} x {a:.1f} m); 4 brazos de {brazo:.1f} m con "
        f"corredor de {cor:.2f} m y locales a ambos lados",
        "la escalera no se genera: reserve el hub con el asistente "
        "de Escaleras"]
    if cab:
        avisos.append(
            f"cabecera transversal de {cab:.2f} m al fondo de cada "
            "brazo con el uso mayor del programa")

    # ---- colocación GLOBAL en las 8 filas: cada local va a la fila
    # con MÁS HUECO restante (tie-break: brazo menor, lado +), como
    # en plan_y; los anchos jamás desbordan la fila ----
    locales_out: List[Dict[str, Any]] = []
    pasillos_out: List[Dict[str, Any]] = []
    cabeceras_out: List[Dict[str, Any]] = []
    mayor = max(escalados, key=lambda t: (
        float(t["area_m2"]), str(t.get("space_type", "")))) \
        if escalados else None
    dentro = True
    usados_fila: List[Dict[str, float]] = [
        {"+": 0.0, "-": 0.0} for _ in range(4)]
    ultimas: List[Dict[str, Dict[str, Any]]] = [
        {"+": None, "-": None} for _ in range(4)]
    sin_hueco: List[str] = []
    for k in range(4):
        theta = thetas[k]
        letra = _LETRAS_ALA[k % len(_LETRAS_ALA)]
        if cor > 0.0:
            poly_cor = _rect_rotado(a / 2.0, a / 2.0 + util,
                                    -cor / 2.0, cor / 2.0, theta,
                                    centro)
            pasillos_out.append({
                "codigo": "PASILLO",
                "nombre": f"Corredor brazo {letra}",
                "space_type": "CORRIDOR", "flujo": "publico",
                "rect": None, "poligono": poly_cor,
                "area_m2": round(util * cor, 2),
                "ancho_m": round(cor, 2), "ala": k,
                "area_min": 0.0})
        if cab:
            poly_cab = _rect_rotado(a / 2.0 + util, L / 2.0,
                                    -(a / 2.0 - _RETRA),
                                    a / 2.0 - _RETRA, theta, centro)
            normas_mayor = _normas_de(str(mayor.get("space_type", ""))
                                      if mayor else "ROOM")
            area_cab = round(cab * (a - 2.0 * _RETRA), 2)
            if float(normas_mayor["minimum_area"]) \
                    and area_cab < float(normas_mayor["minimum_area"]):
                avisos.append(
                    f"la cabecera del brazo {letra} mide "
                    f"{area_cab:.1f} m2 por debajo del mínimo del "
                    f"{mayor.get('nombre', 'uso mayor')}: documente "
                    "la pieza")
            cabeceras_out.append({
                "codigo": str(mayor.get("space_type", "ROOM"))
                if mayor else "ROOM",
                "nombre": f"Cabecera brazo {letra} ("
                          f"{mayor.get('nombre', 'uso mayor')})"
                if mayor else f"Cabecera brazo {letra}",
                "space_type": str(mayor.get("space_type", "ROOM"))
                if mayor else "ROOM",
                "area_m2": area_cab,
                "flujo": str(normas_mayor["flujo"]),
                "rect": None, "poligono": poly_cab,
                "contenedor": k, "ala": k,
                "area_min": round(float(
                    normas_mayor["minimum_area"]), 2)})
    for q in sorted(escalados, key=lambda t: (
            -float(t["area_m2"]), str(t.get("space_type", "")),
            str(t.get("nombre", "")))):
        bins = []
        for k in range(4):
            for lado in ("+", "-"):
                bins.append((-(util - usados_fila[k][lado]), k,
                             lado))
        bins.sort(key=lambda t: (t[0], t[1],
                                 0 if t[2] == "+" else 1))
        _, k, lado = bins[0]
        resto = util - usados_fila[k][lado]
        if resto <= 0.05:
            sin_hueco.append(str(q.get("nombre",
                                       q.get("space_type"))))
            continue
        area_q = float(q["area_m2"])
        w = area_q / max(1e-9, prof)
        w_final = min(w, resto)
        theta = thetas[k]
        ct, st = math.cos(theta), math.sin(theta)
        letra = _LETRAS_ALA[k % len(_LETRAS_ALA)]
        x0 = a / 2.0 + usados_fila[k][lado]
        x1 = a / 2.0 + usados_fila[k][lado] + w_final
        if lado == "+":
            y0, y1 = cor / 2.0, a / 2.0 - _RETRA
        else:
            y0, y1 = -(a / 2.0 - _RETRA), -cor / 2.0
        poly = _rect_rotado(x0, x1, y0, y1, theta, centro)
        area_real = round(w_final * (y1 - y0), 2)
        nombre_brazo = f"{q.get('nombre', 'Local')} (brazo {letra})"
        normas = _normas_de(str(q.get("space_type", "")))
        pieza = {
            "codigo": str(q.get("space_type", "ROOM")),
            "nombre": nombre_brazo,
            "space_type": str(q.get("space_type", "ROOM")),
            "area_m2": area_real,
            "flujo": str(q.get("flujo", "") or normas["flujo"]),
            "rect": None, "poligono": poly,
            "contenedor": k, "ala": k,
            "area_min": round(float(normas["minimum_area"]), 2)}
        if float(normas["minimum_width"]) \
                and (y1 - y0) < float(normas["minimum_width"]):
            avisos.append(
                f"{nombre_brazo}: fondo de {y1 - y0:.2f} m por "
                "debajo del mínimo del DNA "
                f"({float(normas['minimum_width']):.2f} m): "
                "documente la pieza")
        if float(normas["minimum_area"]) \
                and area_real < float(normas["minimum_area"]) - 0.01:
            avisos.append(
                f"{nombre_brazo}: {area_real:.2f} m2 por debajo del "
                f"mínimo del DNA "
                f"({float(normas['minimum_area']):.2f} m2) al "
                "cerrar la fila: documente la pieza")
        locales_out.append(pieza)
        ultimas[k][lado] = pieza
        usados_fila[k][lado] += w_final
        # verificación por franja (frame local del brazo)
        for px, py in poly:
            dx, dy = px - centro[0], py - centro[1]
            u = dx * ct + dy * st
            v = -dx * st + dy * ct
            if not (a / 2.0 - 1e-3 <= u <= L / 2.0 + 1e-3
                    and -a / 2.0 - 1e-3 <= v <= a / 2.0 + 1e-3):
                dentro = False
    if sin_hueco:
        raise DomainError(
            message="plan_x: el programa apenas cabe: los mínimos "
                    f"del DNA llenaron las filas y {len(sin_hueco)} "
                    "local(es) no tienen hueco ("
                    + ", ".join(sin_hueco[:3]) + ")",
            code="ARQ-DDI-011",
            context={"sin_hueco": sin_hueco},
            suggested_action="Alargue o ensanche las barras, quite "
                             "locales o reduzca el corredor.")
    # ---- cierre fino: el ÚLTIMO local de cada fila crece hasta la
    # punta del brazo (la fila llega exacta a la cabecera o al
    # frente, como la planta real) ----
    for k in range(4):
        theta = thetas[k]
        ct_c, st_c = math.cos(theta), math.sin(theta)
        for lado in ("+", "-"):
            resto = util - usados_fila[k][lado]
            pieza = ultimas[k][lado]
            if resto > 0.02 and pieza is not None:
                poly_v = list(pieza["poligono"])
                us = [(dx * ct_c + dy * st_c, j)
                      for j, (dx, dy) in enumerate(
                          (p[0] - centro[0], p[1] - centro[1])
                          for p in poly_v)]
                u_max = max(u for u, _ in us)
                for u, j in us:
                    if u_max - u < 1e-4:
                        px, py = poly_v[j]
                        poly_v[j] = (round(
                            px + resto * ct_c, 4),
                            round(py + resto * st_c, 4))
                pieza["poligono"] = poly_v
                pieza["area_m2"] = round(
                    float(pieza["area_m2"]) + resto * prof, 2)
                usados_fila[k][lado] += resto
    # ---- cabeceras y pasillos también dentro de su franja ----
    for pieza in pasillos_out + cabeceras_out:
        k = int(pieza["ala"])
        theta = thetas[k]
        ct, st = math.cos(theta), math.sin(theta)
        for px, py in pieza["poligono"]:
            dx, dy = px - centro[0], py - centro[1]
            u = dx * ct + dy * st
            v = -dx * st + dy * ct
            if not (a / 2.0 - 1e-3 <= u <= L / 2.0 + 1e-3
                    and -a / 2.0 - 1e-3 <= v <= a / 2.0 + 1e-3):
                dentro = False
                break

    # ---- hub central: el CRUCE de las dos barras (cuadrado a x a
    # en el marco de la barra 1) con el vestíbulo del programa ----
    poly_hub = _rect_rotado(-a / 2.0 + _RETRA, a / 2.0 - _RETRA,
                            -a / 2.0 + _RETRA, a / 2.0 - _RETRA,
                            th0, centro)
    normas_hub = _normas_de(str(hub.get("space_type", "")))
    nubecillo: Dict[str, Any] = {
        "codigo": str(hub.get("space_type", "VESTIBULE")),
        "nombre": str(hub.get("nombre", "Hub central")),
        "space_type": str(hub.get("space_type", "VESTIBULE")),
        "area_m2": round(_area_poligono(poly_hub), 2),
        "flujo": "publico", "rect": None, "poligono": poly_hub,
        "contenedor": 0, "ala": -1,
        "area_min": round(float(normas_hub["minimum_area"]), 2)}
    avisos.append(
        f"el {nubecillo['nombre']} ocupa el CRUCE de las barras "
        f"({nubecillo['area_m2']:.1f} m2) y reparte el acceso a los "
        "corredores de los 4 brazos")

    # ---- contorno: la UNIÓN de las dos barras completas ----
    barra1 = _rect_rotado(-L / 2.0, L / 2.0, -a / 2.0, a / 2.0,
                          th0, centro)
    barra2 = _rect_rotado(-L / 2.0, L / 2.0, -a / 2.0, a / 2.0,
                          th0 + math.pi / 2.0, centro)
    if _area_firmada(barra1) < 0:
        barra1.reverse()
    if _area_firmada(barra2) < 0:
        barra2.reverse()
    vertices = _union_dos_rects(barra1, barra2)
    area_contorno = round(_area_poligono(vertices), 2)

    piezas_all = locales_out + pasillos_out + cabeceras_out \
        + [nubecillo]
    area_ocupada = round(sum(float(p["area_m2"])
                             for p in piezas_all), 2)
    total_prog = round(sum(float(r["area_m2"])
                           for r in renglones), 2)
    renglones_salida = [dict(r) for r in renglones]
    mapa = {id(r): q for r, q in zip(ring, escalados)}
    for k, r in enumerate(renglones):
        q = mapa.get(id(r))
        if q is not None:
            renglones_salida[k]["area_m2"] = q["area_m2"]
    programa_salida = dict(
        programa, renglones=renglones_salida,
        totales=dict(programa.get("totales") or {},
                     area_m2=total_prog))
    xs = [p[0] for p in vertices]
    ys = [p[1] for p in vertices]
    perimetro = sum(
        math.hypot(vertices[(j + 1) % len(vertices)][0] - p[0],
                   vertices[(j + 1) % len(vertices)][1] - p[1])
        for j, p in enumerate(vertices))
    contenedores = []
    for k in range(4):
        theta = thetas[k]
        ct, st = math.cos(theta), math.sin(theta)
        esquinas = [_rotar(p, ct, st, centro)
                    for p in ((a / 2.0, -a / 2.0),
                              (L / 2.0, -a / 2.0),
                              (L / 2.0, a / 2.0),
                              (a / 2.0, a / 2.0))]
        ex = [p[0] for p in esquinas]
        ey = [p[1] for p in esquinas]
        contenedores.append({
            "ancho_m": round(brazo, 2), "fondo_m": round(a, 2),
            "area_m2": round(brazo * a, 2),
            "x0": round(min(ex), 2), "y0": round(min(ey), 2),
            "x1": round(max(ex), 2), "y1": round(max(ey), 2)})
    rep1 = {
        "nivel": 1,
        "pasillo": (pasillos_out[0] if pasillos_out else None),
        "pasillos": pasillos_out,
        "escalera": None,
        "locales": (locales_out + cabeceras_out + [nubecillo]),
        "patio": None,
        "area_ocupada": area_ocupada,
        "area_disponible": area_contorno,
        "dentro": dentro,
        "contenedores_usados": [0, 1, 2, 3]}
    reparto = []
    for _k in range(nv):
        r_k = copy.deepcopy(rep1)
        r_k["nivel"] = _k + 1
        reparto.append(r_k)
    if nv > 1:
        avisos.append(
            f"planta tipo repetida en {nv} niveles: reserve las "
            "escaleras con el asistente de Escaleras")
    analisis = {
        "tipo": "x_radial",
        "forma": {"vertices": vertices,
                  "area_m2": area_contorno,
                  "forma": "x_radial",
                  "centro": [round(centro[0], 4),
                             round(centro[1], 4)],
                  "bbox": [round(min(xs), 3), round(min(ys), 3),
                           round(max(xs), 3), round(max(ys), 3)],
                  "alineado": False,
                  "ancho_m": round(max(xs) - min(xs), 2),
                  "fondo_m": round(max(ys) - min(ys), 2),
                  "perimetro_m": round(perimetro, 2)},
        "programa": programa_salida,
        "niveles": nv, "cabe_un_nivel": True,
        "con_escalera": 0, "escalera": None, "patio": None,
        "reparto": reparto,
        "dentro_del_contorno": dentro,
        "sala_distribuidora": False,
        "chaflanes": [],
        "tope_niveles": None,
        "encaje": {"estrategia": "x_radial",
                   "contenedores": contenedores,
                   "area_aprovechable": round(disp_total, 2)},
        "altura_nivel_m": altura,
        "decisiones": [],
        "x_radial": {"largo_barra": round(L, 3),
                     "ancho_barra": round(a, 3),
                     "corredor_m": round(cor, 3),
                     "cabecera_m": round(cab, 3),
                     "angulo_deg": round(math.degrees(th0), 1),
                     "brazo_m": round(brazo, 3)},
        "avisos": avisos,
        "totales": {
            "area_programa": total_prog,
            "area_pasillos": round(sum(float(p["area_m2"])
                                       for p in pasillos_out), 2),
            "area_escaleras": 0.0, "area_patio": 0.0,
            "area_contorno": area_contorno,
            "area_aprovechada": area_ocupada,
            "area_construida": area_ocupada,
            "aprovechamiento_pct": round(
                100.0 * area_ocupada / max(0.01, area_contorno), 2),
            "altura_total": round(float(nv) * altura, 2)},
    }
    return analisis
