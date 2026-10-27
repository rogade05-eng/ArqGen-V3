"""ESCALERAS POR TIPOLOGÍA SEGÚN NEUFERT (v3.19.0).

El libro dedica un capítulo entero a la escalera: la escala de la
arquitectura vertical. Este módulo trae las TIPOLOGÍAS clásicas —
RECTA, en L, en U (doble piso) y CARACOL — dimensionadas con la
fórmula de BLONDEL (2·contrahuella + huella = 0.60-0.64 m) y las
reglas del libro (contrahuella 0.14-0.18 m, huella 0.26-0.32 m,
meseta cada 16 contrahuellas con un fondo igual al ancho del tramo):

* ``dimensionar``: reparte el desnivel en contrahuellas iguales y
  devuelve tramos, mesetas, pendiente y Blondel (aconseja, no bloquea).
* ``geometria``: genera la planta REAL de la escalera — contorno,
  líneas de huella de cada peldaño y las cajas 3D de cada uno — ya
  rotada y centrada en el punto pedido.
* ``generar_escalera``: levanta la entidad STAIR sobre la planta
  (dentro de un hueco de escalera o núcleo si cabe) por los caminos
  oficiales: auditoría, undo persistente, QTO e invalidación.
* ``sitio_para_escalera``: busca el recinto STAIR/CORE que acoja el
  AABB de la escalera; si no cabe, la coloca donde se pida con aviso.

Cero Tk y cero dependencias. Mensajes 100 % codificables en cp1252.
Los valores del libro ACONSEJAN, nunca bloquean: el proyectista
verifica siempre la norma local vigente.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain.diseno_base import (
    alta_entidad, baja_entidad, bbox_de, cerrar_qto, lista_tipos,
    metadata_origen,
)
from domain.model import Stair

PT = Tuple[float, float]

# error propio: ARQ-ESC-001 tipo desconocido
# error propio: ARQ-ESC-002 dimensiones fuera de rango
# error propio: ARQ-ESC-003 caracol con radio insuficiente

FUENTE = "Neufert — escaleras: fórmula de Blondel y tipologías (5.ª ed.)"

TIPOS: Tuple[str, ...] = ("recta", "L", "U", "caracol")

ETIQUETA_TIPO: Dict[str, str] = {
    "recta": "recta",
    "L": "en L (dos tramos con meseta)",
    "U": "en U / doble piso (tramos paralelos)",
    "caracol": "de caracol (helicoidal)",
}

# Límites del libro (aconsejan; la accesibilidad del CTE estrecha más)
CONTRAHUELLA_MIN_M = 0.14
CONTRAHUELLA_MAX_M = 0.18
HUELLA_MIN_M = 0.26
HUELLA_MAX_M = 0.32
BLONDEL_MIN_M = 0.60
BLONDEL_MAX_M = 0.64
DESCANSO_TRAS = 16            # meseta si un tramo excede 16 contrahuellas
ANCHO_MIN_M = 0.90            # interior privado; el público pide 1.20
ANCHO_MAX_M = 2.50
ANCHO_DEFECTO_M = 1.10
ALTO_DEFECTO_M = 3.0
CONTRAHUELLA_OBJETIVO_M = 0.17   # cómoda general (~30° con 0.29)

# Caracol: tubo central y línea de paso (Neufert: la huella se mide
# en la línea de paso, a 2/3 del radio exterior)
CARACOL_R_INTERIOR_M = 0.15
CARACOL_R_MIN_M = 0.75        # radio exterior mínimo del hueco
CARACOL_LINEA_PASO = 2.0 / 3.0


def blondel_m(contrahuella_m: float, huella_m: float) -> float:
    """Fórmula de Blondel: 2·h + p."""
    return 2.0 * float(contrahuella_m) + float(huella_m)


def blondel_ok(contrahuella_m: float, huella_m: float) -> bool:
    """El paso queda cómodo entre 0.60 y 0.64 m."""
    return BLONDEL_MIN_M <= blondel_m(contrahuella_m, huella_m) <= BLONDEL_MAX_M


def regla_para_uso(uso: str = "") -> Dict[str, float]:
    """Contrahuella, huella y ancho aconsejados para el uso.

    Consulta el catálogo Neufert del proyecto (edición regional
    incluida); si no lo conoce, cae a la cómoda general.
    """
    try:
        from domain.neufert import get_registry
        regla = get_registry().stair_rule(uso)
        return {"contrahuella_m": regla.contrahuella_m,
                "huella_m": regla.huella_m, "ancho_m": regla.ancho_m,
                "uso": uso}
    except Exception:  # noqa: BLE001 — sin catálogo, valores del libro
        return {"contrahuella_m": CONTRAHUELLA_OBJETIVO_M,
                "huella_m": 0.29, "ancho_m": ANCHO_DEFECTO_M, "uso": uso}


def dimensionar(desnivel_m: float,
                contrahuella_m: Optional[float] = None,
                huella_m: Optional[float] = None) -> Dict[str, Any]:
    """Reparte el desnivel en contrahuellas iguales (Neufert).

    Con ``contrahuella`` pedida se redondea el número de peldaños para
    que el ARRIBA caiga exacto (la última contrahuella absorbe el
    resto); sin ella se busca la cómoda de ~0.17 m. La huella sin
    pedir se deduce de Blondel. Devuelve tramos, mesetas, Blondel,
    pendiente y avisos amables (nunca errores por dimensiones).
    """
    desnivel = float(desnivel_m)
    if desnivel <= 0:
        raise DomainError(
            message="El desnivel a salvar debe ser positivo",
            code="ARQ-ESC-002",
            context={"desnivel_m": desnivel},
            suggested_action="Indica la altura entre pisos (p. ej. 3.0 m)")
    if contrahuella_m is not None and contrahuella_m <= 0:
        raise DomainError(
            message="La contrahuella debe ser positiva",
            code="ARQ-ESC-002",
            context={"contrahuella_m": contrahuella_m})
    if huella_m is not None and huella_m <= 0:
        raise DomainError(
            message="La huella debe ser positiva",
            code="ARQ-ESC-002",
            context={"huella_m": huella_m})
    avisos: List[str] = []
    if contrahuella_m is None:
        n = max(1, round(desnivel / CONTRAHUELLA_OBJETIVO_M))
    else:
        n = max(1, math.ceil(desnivel / float(contrahuella_m) - 1e-9))
    h = desnivel / n
    if h < CONTRAHUELLA_MIN_M - 1e-9:
        avisos.append(f"contrahuella {h:.3f} m por debajo de la cómoda "
                      f"({CONTRAHUELLA_MIN_M:.2f} m): el libro aconseja "
                      "menos peldaños o repartir en más tramos")
    if h > CONTRAHUELLA_MAX_M + 1e-9:
        avisos.append(f"contrahuella {h:.3f} m por encima del máximo "
                      f"({CONTRAHUELLA_MAX_M:.2f} m): añade un peldaño "
                      "o revisa el desnivel")
    if huella_m is None:
        p = min(max(BLONDEL_MAX_M - 2.0 * h, HUELLA_MIN_M), HUELLA_MAX_M)
    else:
        p = float(huella_m)
    if not blondel_ok(h, p):
        avisos.append(f"Blondel 2h + p = {blondel_m(h, p):.3f} m fuera "
                      f"de {BLONDEL_MIN_M:.2f}-{BLONDEL_MAX_M:.2f} m: "
                      "el paso no será cómodo")
    tramos = max(1, math.ceil(n / DESCANSO_TRAS))
    por_tramo = max(1, math.ceil(n / tramos))
    mesetas = tramos - 1
    pendiente = math.degrees(math.atan(h / p)) if p > 0 else 0.0
    return {"n_contrahuellas": n, "contrahuella_m": round(h, 6),
            "huella_m": round(p, 6), "blondel_m": round(blondel_m(h, p), 3),
            "blondel_ok": blondel_ok(h, p), "tramos": tramos,
            "por_tramo": por_tramo, "mesetas": mesetas,
            "pendiente_deg": round(pendiente, 1),
            "avisos": avisos}


# ---------------------------------------------------------------------------
# geometría de cada tipología
# ---------------------------------------------------------------------------

def _caja_peldano(cx: float, cy: float, dx: float, dy: float,
                  z0: float, z1: float, rot: float = 0.0) -> Dict[str, Any]:
    """Peldaño/meseta como caja 3D (para view3d, ya en mundo)."""
    return {"cx": round(cx, 4), "cy": round(cy, 4),
            "dx": round(dx, 4), "dy": round(dy, 4),
            "rot": round(rot, 2), "z0": round(z0, 4), "z1": round(z1, 4)}


def _geometria_recta(n: int, por_tramo: int, h: float, p: float,
                     a: float) -> Dict[str, Any]:
    """Escalera RECTA: un sentido, mesetas intermedias si hace falta."""
    lineas: List[List[PT]] = []
    cajas: List[Dict[str, Any]] = []
    y = 0.0
    pendientes = n
    z = 0.0
    desarrollo = 0.0
    while pendientes > 0:
        k = min(por_tramo, pendientes)
        for i in range(1, k):
            yy = y + i * p
            lineas.append([(-a / 2.0, yy), (a / 2.0, yy)])
        for i in range(1, k + 1):
            cajas.append(_caja_peldano(0.0, y + (i - 0.5) * p, a, p,
                                       z + (i - 1) * h, z + i * h))
        y += k * p
        z += k * h
        desarrollo += k * p
        pendientes -= k
        if pendientes > 0:
            lineas.append([(-a / 2.0, y), (a / 2.0, y)])
            cajas.append(_caja_peldano(0.0, y + a / 2.0, a, a, z, z))
            y += a                      # meseta: fondo = ancho del tramo
            desarrollo += a
    outline = [(-a / 2.0, 0.0), (a / 2.0, 0.0),
               (a / 2.0, y), (-a / 2.0, y)]
    return {"outline": outline, "treads": lineas,
            "pasos": cajas, "desarrollo_m": round(desarrollo, 3)}


def _geometria_L(n: int, h: float, p: float, a: float) -> Dict[str, Any]:
    """Escalera en L: dos tramos a 90 grados con meseta cuadrada."""
    n1 = math.ceil(n / 2)
    n2 = n - n1
    lineas: List[List[PT]] = []
    cajas: List[Dict[str, Any]] = []
    # tramo 1 sube en +Y, ancho en X [-a/2, a/2]
    for i in range(1, n1):
        lineas.append([(-a / 2.0, i * p), (a / 2.0, i * p)])
    for i in range(1, n1 + 1):
        cajas.append(_caja_peldano(0.0, (i - 0.5) * p, a, p,
                                   (i - 1) * h, i * h))
    # meseta cuadrada a×a a la cabeza del tramo 1 (a la cota n1*h)
    cajas.append(_caja_peldano(0.0, n1 * p + a / 2.0, a, a, n1 * h - h, n1 * h))
    # tramo 2 sale en +X desde el borde derecho, ancho en Y
    y0 = n1 * p
    for i in range(1, n2):
        xx = a / 2.0 + i * p
        lineas.append([(xx, y0), (xx, y0 + a)])
    for i in range(1, n2 + 1):
        cajas.append(_caja_peldano(a / 2.0 + (i - 0.5) * p, y0 + a / 2.0,
                                   p, a, n1 * h + (i - 1) * h,
                                   n1 * h + i * h))
    outline = [(-a / 2.0, 0.0), (a / 2.0, 0.0), (a / 2.0, y0),
               (a / 2.0 + n2 * p, y0), (a / 2.0 + n2 * p, y0 + a),
               (-a / 2.0, y0 + a)]
    desarrollo = n1 * p + a + n2 * p
    return {"outline": outline, "treads": lineas, "pasos": cajas,
            "desarrollo_m": round(desarrollo, 3), "tramos": 2,
            "mesetas": 1}


def _geometria_U(n: int, h: float, p: float, a: float) -> Dict[str, Any]:
    """Escalera en U (doble piso): dos tramos paralelos y meseta ancha."""
    n1 = math.ceil(n / 2)
    n2 = n - n1
    gap = p                                   # hueco entre tramos
    x2 = a / 2.0 + gap                        # borde interior del tramo 2
    lineas: List[List[PT]] = []
    cajas: List[Dict[str, Any]] = []
    # tramo 1 sube en +Y (franja izquierda)
    for i in range(1, n1):
        lineas.append([(-a / 2.0, i * p), (a / 2.0, i * p)])
    for i in range(1, n1 + 1):
        cajas.append(_caja_peldano(0.0, (i - 0.5) * p, a, p,
                                   (i - 1) * h, i * h))
    # meseta ancha (2a + gap) a la cabeza, a la cota n1*h
    ancho_meseta = 2.0 * a + gap
    cx_meseta = (a + gap) / 2.0
    cajas.append(_caja_peldano(cx_meseta, n1 * p + a / 2.0, ancho_meseta, a,
                               n1 * h - h, n1 * h))
    # tramo 2 baja en -Y por la franja derecha (sube la cota)
    y_tope = n1 * p
    for i in range(1, n2):
        yy = y_tope - i * p
        lineas.append([(x2, yy), (x2 + a, yy)])
    for i in range(1, n2 + 1):
        cajas.append(_caja_peldano(x2 + a / 2.0, y_tope - (i - 0.5) * p,
                                   a, p, n1 * h + (i - 1) * h,
                                   n1 * h + i * h))
    y_bajo = y_tope - n2 * p
    outline = [(-a / 2.0, 0.0), (-a / 2.0, y_tope + a),
               (x2 + a, y_tope + a), (x2 + a, y_bajo),
               (x2, y_bajo), (x2, y_tope), (a / 2.0, y_tope),
               (a / 2.0, 0.0)]
    desarrollo = n1 * p + a + n2 * p
    return {"outline": outline, "treads": lineas, "pasos": cajas,
            "desarrollo_m": round(desarrollo, 3), "tramos": 2,
            "mesetas": 1, "gap_m": round(gap, 3)}


def _geometria_caracol(n: int, h: float, p: float, ancho: float
                       ) -> Dict[str, Any]:
    """Escalera DE CARACOL: peldaños en abanico alrededor del tubo.

    La huella se mide en la LÍNEA DE PASO (a 2/3 del radio útil,
    Neufert): el giro por peldaño sale de p / r_linea. Los peldaños
    3D se aproximan con cajas giradas al centro del abanico.
    """
    R = CARACOL_R_INTERIOR_M + ancho          # radio exterior del hueco
    r_linea = CARACOL_R_INTERIOR_M + (R - CARACOL_R_INTERIOR_M) \
        * CARACOL_LINEA_PASO
    theta = p / r_linea                       # radianes por peldaño
    lineas: List[List[PT]] = []
    cajas: List[Dict[str, Any]] = []
    r_mid = (CARACOL_R_INTERIOR_M + R) / 2.0
    for i in range(1, n):
        ang = i * theta
        c, s = math.cos(ang), math.sin(ang)
        lineas.append([(CARACOL_R_INTERIOR_M * c, CARACOL_R_INTERIOR_M * s),
                       (R * c, R * s)])
    for i in range(1, n + 1):
        ang = (i - 0.5) * theta
        c, s = math.cos(ang), math.sin(ang)
        cajas.append(_caja_peldano(r_mid * c, r_mid * s, ancho, p * 0.92,
                                   (i - 1) * h, i * h,
                                   math.degrees(ang)))
    # contorno: anillo exterior + tubo interior (polígono de 40 vértices)
    lado = 40
    exterior = [(R * math.cos(2 * math.pi * i / lado),
                 R * math.sin(2 * math.pi * i / lado))
                for i in range(lado)]
    interior = [(CARACOL_R_INTERIOR_M * math.cos(2 * math.pi * i / lado),
                 CARACOL_R_INTERIOR_M * math.sin(2 * math.pi * i / lado))
                for i in range(lado - 1, -1, -1)]
    outline = exterior + interior
    total_ang = n * theta
    return {"outline": outline, "treads": lineas, "pasos": cajas,
            "desarrollo_m": round(n * p, 3), "tramos": 1, "mesetas": 0,
            "caracol": {"r_interior_m": CARACOL_R_INTERIOR_M,
                        "r_exterior_m": round(R, 3),
                        "r_linea_paso_m": round(r_linea, 3),
                        "giro_peldano_deg": round(math.degrees(theta), 2),
                        "giro_total_deg": round(math.degrees(total_ang), 1),
                        "vueltas": round(total_ang / (2 * math.pi), 2)}}


def _area_poligono(puntos: List[PT]) -> float:
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _recen_y_rota(geo: Dict[str, Any], rot_deg: float
                  ) -> Tuple[List[PT], List[List[PT]], List[Dict[str, Any]]]:
    """Recentra el bbox local en el origen y rota todo el conjunto."""
    outline = geo["outline"]
    minx, miny, maxx, maxy = bbox_de(outline)
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    ang = math.radians(float(rot_deg or 0.0))
    c, s = math.cos(ang), math.sin(ang)

    def mueve(p: PT) -> PT:
        x, y = p[0] - cx, p[1] - cy
        return (x * c - y * s, x * s + y * c)

    outline2 = [mueve(p) for p in outline]
    treads2 = [[mueve(p) for p in linea] for linea in geo.get("treads", [])]
    pasos2: List[Dict[str, Any]] = []
    for caja in geo.get("pasos", []):
        bx, by = mueve((caja["cx"], caja["cy"]))
        pasos2.append({**caja, "cx": round(bx, 4), "cy": round(by, 4),
                       "rot": round((caja.get("rot", 0.0) + rot_deg) % 360.0,
                                    2)})
    return outline2, treads2, pasos2


def geometria(tipo: str, desnivel_m: float,
              contrahuella_m: Optional[float] = None,
              huella_m: Optional[float] = None,
              ancho_m: float = ANCHO_DEFECTO_M,
              rot_deg: float = 0.0) -> Dict[str, Any]:
    """Planta y cajas 3D de la escalera, centradas en el origen.

    Devuelve ``outline`` (contorno cerrado), ``treads`` (líneas de
    huella), ``pasos`` (cajas 3D de peldaños y mesetas con sus cotas)
    y los parámetros de ``dimensionar``. Todo ya rotado ``rot_deg``;
    el que llama traslada al (x, y) de la entidad.
    """
    if tipo not in TIPOS:
        raise DomainError(
            message=f"Tipología de escalera desconocida: {tipo}",
            code="ARQ-ESC-001",
            context={"tipo": tipo, "permitidos": list(TIPOS)},
            suggested_action="Usa una de: " + ", ".join(TIPOS))
    ancho = float(ancho_m)
    if ancho < ANCHO_MIN_M or ancho > ANCHO_MAX_M:
        raise DomainError(
            message=(f"El ancho del tramo {ancho:.2f} m queda fuera del "
                     f"rango del libro ({ANCHO_MIN_M:.2f}-{ANCHO_MAX_M:.2f} m)"),
            code="ARQ-ESC-002",
            context={"ancho_m": ancho, "min": ANCHO_MIN_M,
                     "max": ANCHO_MAX_M},
            suggested_action=(f"Usa un ancho entre {ANCHO_MIN_M:.2f} y "
                              f"{ANCHO_MAX_M:.2f} m"))
    dims = dimensionar(desnivel_m, contrahuella_m, huella_m)
    n = dims["n_contrahuellas"]
    h = dims["contrahuella_m"]
    p = dims["huella_m"]
    if tipo == "recta":
        geo = _geometria_recta(n, dims["por_tramo"], h, p, ancho)
    elif tipo == "L":
        geo = _geometria_L(n, h, p, ancho)
    elif tipo == "U":
        geo = _geometria_U(n, h, p, ancho)
    else:
        R = CARACOL_R_INTERIOR_M + ancho
        if R < CARACOL_R_MIN_M:
            raise DomainError(
                message=(f"El hueco del caracol (radio {R:.2f} m) queda "
                         f"por debajo del mínimo ({CARACOL_R_MIN_M:.2f} m)"),
                code="ARQ-ESC-003",
                context={"radio_m": R, "min": CARACOL_R_MIN_M},
                suggested_action="Ensancha el ancho del tramo a "
                                 f"{CARACOL_R_MIN_M - CARACOL_R_INTERIOR_M:.2f} m")
        geo = _geometria_caracol(n, h, p, ancho)
    outline, treads, pasos = _recen_y_rota(geo, rot_deg)
    geo.update({"outline": outline, "treads": treads, "pasos": pasos,
                "n_contrahuellas": n, "contrahuella_m": h, "huella_m": p,
                "blondel_m": dims["blondel_m"],
                "blondel_ok": dims["blondel_ok"],
                "pendiente_deg": dims["pendiente_deg"],
                "por_tramo": dims["por_tramo"],
                "area_huella_m2": round(_area_poligono(outline), 3),
                "ancho_m": ancho, "rot_deg": float(rot_deg or 0.0),
                "avisos": list(dims["avisos"])})
    geo.setdefault("tramos", 1)
    geo.setdefault("mesetas", 0)
    return geo


# ---------------------------------------------------------------------------
# colocación y generación en el proyecto
# ---------------------------------------------------------------------------

def sitio_para_escalera(ctx: Any, aabb: Tuple[float, float, float, float],
                        nivel_id: str = "") -> Dict[str, Any]:
    """Busca recinto STAIR/CORE que acoja el AABB de la escalera.

    Escanea los locales del nivel pedido (o del primero) de mayor a
    menor área y devuelve ``{"x", "y", "space_id", "modo", "aviso"}``.
    """
    _minw, _minh, ancho, fondo = aabb
    espacios = [e for e in lista_tipos(ctx, "SPACE")
                if len(getattr(e, "boundary", []) or []) >= 3
                and str(e.space_type or "").upper() in ("STAIR", "CORE")]
    if nivel_id:
        propios = [e for e in espacios if e.level_id == nivel_id]
        espacios = propios or espacios
    for recinto in sorted(espacios, key=lambda e: -e.area_m2()):
        minx, miny, maxx, maxy = bbox_de(recinto.boundary)
        if (maxx - minx) >= ancho - 1e-6 and (maxy - miny) >= fondo - 1e-6:
            return {"x": round((minx + maxx) / 2.0, 4),
                    "y": round((miny + maxy) / 2.0, 4),
                    "space_id": recinto.id, "modo": "hueco", "aviso": ""}
    return {"x": 0.0, "y": 0.0, "space_id": "", "modo": "libre",
            "aviso": "sin hueco de escalera/núcleo que la acoja: "
                     "colocada en el origen; muévela con x/y o gira el "
                     "tipo de planta"}


def desnivel_del_proyecto(ctx: Any) -> Tuple[float, str]:
    """Altura del nivel base y su nombre (para el desnivel por defecto)."""
    niveles = lista_tipos(ctx, "LEVEL")
    if not niveles:
        return (ALTO_DEFECTO_M, "")
    niveles.sort(key=lambda lv: (float(getattr(lv, "elevation_m", 0.0)
                                     or 0.0), str(getattr(lv, "name", ""))))
    base = niveles[0]
    try:
        altura = float(getattr(base, "height_m", ALTO_DEFECTO_M)
                       or ALTO_DEFECTO_M)
    except (TypeError, ValueError):
        altura = ALTO_DEFECTO_M
    return (altura, str(getattr(base, "name", "") or ""))


def quitar_escaleras(ctx: Any) -> List[str]:
    """Da de baja las escaleras generadas (lo manual se conserva)."""
    bajas: List[str] = []
    for escalera in lista_tipos(ctx, "STAIR"):
        codigo = escalera.code
        baja_entidad(ctx, "STAIR", escalera.id)
        bajas.append(codigo)
    return bajas


def generar_escalera(ctx: Any, data: Any = None,
                     tipo: str = "recta",
                     desnivel_m: Optional[float] = None,
                     contrahuella_m: Optional[float] = None,
                     huella_m: Optional[float] = None,
                     ancho_m: float = ANCHO_DEFECTO_M,
                     uso: str = "",
                     x: Optional[float] = None,
                     y: Optional[float] = None,
                     rot_deg: float = 0.0,
                     nivel_id: str = "",
                     space_id: str = "",
                     con_qto: bool = True) -> Dict[str, Any]:
    """Levanta la escalera sobre la planta (v3.19.0).

    ``tipo`` elige la planta (recta/L/U/caracol); el desnivel sale del
    nivel base si no se pide, y la contrahuella y la huella de Blondel
    (o del uso, vía el catálogo Neufert). El sitio: si se dan ``x``/
    ``y`` se respetan; si no, un recinto STAIR o CORE que acoja el
    AABB. La geometría generada (contorno, huellas y cajas 3D) viaja
    en metadata; QTO cuenta peldaños, huella, desarrollo y barandilla
    (a los dos lados).
    """
    resumen: Dict[str, Any] = {"operacion": "escalera", "creados": [],
                               "eliminados": [], "avisos": [], "qto": None}
    if tipo not in TIPOS:
        raise DomainError(
            message=f"Tipología de escalera desconocida: {tipo}",
            code="ARQ-ESC-001",
            context={"tipo": tipo, "permitidos": list(TIPOS)},
            suggested_action="Usa una de: " + ", ".join(TIPOS))
    # IDEMPOTENTE (patrón de cubiertas y ascensores)
    resumen["eliminados"] = quitar_escaleras(ctx)
    nivel_base: Optional[Any] = None
    candidatas = lista_tipos(ctx, "LEVEL")
    if candidatas:
        candidatas.sort(key=lambda lv: (
            float(getattr(lv, "elevation_m", 0.0) or 0.0),
            str(getattr(lv, "name", ""))))
        nivel_base = candidatas[0]
        if nivel_id:
            nivel_base = next((lv for lv in candidatas
                               if lv.id == nivel_id), nivel_base)
    if desnivel_m is None:
        desnivel, nombre_nivel = desnivel_del_proyecto(ctx)
        if nombre_nivel:
            resumen["avisos"].append(
                f"desnivel tomado de la altura del nivel «{nombre_nivel}» "
                f"({desnivel:.2f} m)")
    else:
        desnivel = float(desnivel_m)
    if contrahuella_m is None and huella_m is None and uso:
        regla = regla_para_uso(uso)
        contrahuella_m = regla["contrahuella_m"]
        huella_m = regla["huella_m"]
        ancho_m = max(float(regla.get("ancho_m") or ancho_m), ancho_m)
        resumen["avisos"].append(
            f"medidas del uso «{uso}»: h {contrahuella_m:.3f} m, "
            f"p {huella_m:.2f} m, ancho {ancho_m:.2f} m")
    geo = geometria(tipo, desnivel, contrahuella_m, huella_m, ancho_m,
                    rot_deg=rot_deg)
    for aviso in geo.get("avisos", []):
        resumen["avisos"].append(aviso)
    minx, miny, maxx, maxy = bbox_de(geo["outline"])
    ancho_aabb, fondo_aabb = maxx - minx, maxy - miny
    if x is not None and y is not None:
        sitio = {"x": round(float(x), 4), "y": round(float(y), 4),
                 "space_id": space_id or "", "modo": "manual", "aviso": ""}
    else:
        sitio = sitio_para_escalera(ctx, (minx, miny, ancho_aabb, fondo_aabb),
                                    nivel_id=getattr(nivel_base, "id", ""))
    if sitio.get("aviso"):
        resumen["avisos"].append(sitio["aviso"])
    barra = 2.0 * float(geo.get("desarrollo_m", 0.0))
    extra_meta: Dict[str, Any] = {
        "outline": [[round(px, 4), round(py, 4)] for px, py in
                    geo["outline"]],
        "treads": [[[round(px, 4), round(py, 4)] for px, py in linea]
                   for linea in geo["treads"]],
        "pasos": geo["pasos"],
        "n_contrahuellas": geo["n_contrahuellas"],
        "contrahuella_m": geo["contrahuella_m"],
        "huella_m": geo["huella_m"], "blondel_m": geo["blondel_m"],
        "blondel_ok": geo["blondel_ok"],
        "pendiente_deg": geo["pendiente_deg"], "tramos": geo["tramos"],
        "mesetas": geo["mesetas"],
        "desarrollo_m": geo["desarrollo_m"],
        "area_huella_m2": geo["area_huella_m2"],
        "barandilla_m": round(barra, 3),
        "ancho_m": ancho_m, "modo": sitio["modo"], "fuente": FUENTE}
    if geo.get("caracol"):
        extra_meta["caracol"] = geo["caracol"]
    if sitio.get("space_id"):
        extra_meta["space_id"] = sitio["space_id"]
    entidad = Stair(
        project_id=ctx.project.id,
        code=ctx.next_code("ARCHITECTURE", "STAIR"),
        level_id=getattr(nivel_base, "id", ""),
        space_id=str(sitio.get("space_id") or ""),
        tipo=tipo, x=float(sitio["x"]), y=float(sitio["y"]),
        rotation_deg=float(rot_deg or 0.0),
        width_m=float(ancho_m), desnivel_m=float(desnivel),
        contrahuella_m=float(geo["contrahuella_m"]),
        huella_m=float(geo["huella_m"]),
        metadata=metadata_origen("escalera del asistente", extra_meta))
    alta_entidad(ctx, entidad)
    resumen["creados"].append(entidad.code)
    resumen["parametros"] = {
        "tipo": tipo, "etiqueta": ETIQUETA_TIPO.get(tipo, tipo),
        "desnivel_m": float(desnivel),
        "n_contrahuellas": geo["n_contrahuellas"],
        "contrahuella_m": geo["contrahuella_m"], "huella_m": geo["huella_m"],
        "blondel_m": geo["blondel_m"], "blondel_ok": geo["blondel_ok"],
        "tramos": geo["tramos"], "mesetas": geo["mesetas"],
        "pendiente_deg": geo["pendiente_deg"], "ancho_m": ancho_m,
        "desarrollo_m": geo["desarrollo_m"],
        "area_huella_m2": geo["area_huella_m2"],
        "barandilla_m": round(barra, 3),
        "x": float(sitio["x"]), "y": float(sitio["y"]),
        "modo": sitio["modo"]}
    if geo.get("caracol"):
        resumen["parametros"]["caracol"] = geo["caracol"]
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado (o el estado de la escalera)."""
    if resumen.get("parametros"):
        p = resumen["parametros"]
        texto = (f"Escalera {p['etiqueta']} de {p['desnivel_m']:.2f} m"
                 f" · {p['n_contrahuellas']} peldaños"
                 f" · h {p['contrahuella_m']:.3f} m / p {p['huella_m']:.2f} m"
                 f" · Blondel {p['blondel_m']:.3f} m"
                 f" · {p['pendiente_deg']:.0f} grados")
    else:
        texto = "Escalera"
    partes = [texto]
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} STAIR creada")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


def tabla_texto() -> List[str]:
    """Reglas del libro por uso (para la GUI y la CLI), cp1252."""
    usos = ("", "Vivienda", "Hospital", "Escuela primaria", "Oficina")
    lineas = ["Regla de escalera por uso (Neufert):"]
    lineas.append("  uso                h (m)   p (m)   ancho  Blondel")
    for uso in usos:
        regla = regla_para_uso(uso)
        h, p = regla["contrahuella_m"], regla["huella_m"]
        nombre = uso or "(general)"
        lineas.append(f"  {nombre:<18} {h:<7.3f} {p:<7.2f} "
                      f"{regla['ancho_m']:<6.2f} {blondel_m(h, p):.3f}"
                      + ("  ok" if blondel_ok(h, p) else ""))
    return lineas


__all__ = [
    "FUENTE", "TIPOS", "ETIQUETA_TIPO", "CONTRAHUELLA_MIN_M",
    "CONTRAHUELLA_MAX_M", "HUELLA_MIN_M", "HUELLA_MAX_M", "BLONDEL_MIN_M",
    "BLONDEL_MAX_M", "DESCANSO_TRAS", "ANCHO_MIN_M", "ANCHO_MAX_M",
    "ANCHO_DEFECTO_M", "ALTO_DEFECTO_M", "CONTRAHUELLA_OBJETIVO_M",
    "CARACOL_R_INTERIOR_M", "CARACOL_R_MIN_M", "CARACOL_LINEA_PASO",
    "blondel_m", "blondel_ok", "regla_para_uso", "dimensionar",
    "geometria", "sitio_para_escalera", "desnivel_del_proyecto",
    "quitar_escaleras", "generar_escalera", "resumen_texto", "tabla_texto",
]
