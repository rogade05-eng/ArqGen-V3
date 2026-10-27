"""PUNTERO Y REFERENCIAS ESTILO AUTOCAD (v3.16.0, v3.38.0).

La mira de AutoCAD es una CRUZ de punta a punta que sigue al raton,
con referencias (osnap) que saltan a los puntos exactos, modo ORTO
que endereza los pasos y una rejilla a la que se puede imantar el
punto. Este modulo trae la logica PURA de todo eso:

- ConfigCursor: tamano en % del lienzo (100 = de punta a punta como
  AutoCAD), grosor en px, color (vacio = el del tema), paso de la
  rejilla y umbral de referencia.
- puntas_cruz(): los 4 extremos de la mira para dibujarla.
- fijaciones()/mejor_fijacion(): osnap con la FAMILIA CLASICA y su
  precedencia (v3.38.0): EXTREMO (cuadrado), INTERSECCION (X), PUNTO
  MEDIO (triangulo), CENTRO de locales (circulo), PERPENDICULAR
  (angulo recto) y MAS CERCANO (pajarita). "Un extremo le gana a una
  interseccion cercana, y esta a un medio, como el orden de
  prioridad del Snap clasico"; dentro de la misma marca, la mas
  proxima al cursor.
- aplicar_orto(): endereza el segundo punto (F8).
- imantar_rejilla(): redondea al paso de la rejilla (F9).
- aplicar_ayudas(): compone referencias + orto + imantacion con la
  precedencia de AutoCAD (una referencia ganada gana a orto/rejilla).

Cero Tk: dibuja quien llama (el lienzo). Mensajes cp1252.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

PT = Tuple[float, float]
# Familia clasica con su precedencia (menor = antes). El marcador de
# cada marca lo dibuja la GUI: cuadrado (extremo), X (interseccion),
# triangulo (medio), circulo (centro), angulo recto (perpendicular),
# pajarita (mas_cercano).
PRIORIDAD_MARCA: Dict[str, int] = {
    "extremo": 0, "interseccion": 1, "medio": 2, "centro": 3,
    "perpendicular": 4, "mas_cercano": 5,
}
MARCAS = tuple(PRIORIDAD_MARCA)        # compat v3.16: extremo/medio
MARCAS_V16 = ("extremo", "medio")      # las dos clasicas originales
# Marcas ACTIVAS de fabrica: las magneticas inofensivas. PER y
# MAS_CERCANO hay que activarlos (imantan la recta entera: sin
# opt-in rompen el dibujo libre junto a un muro, como el NEA del
# clasico que nunca viene encendido).
MARCAS_ACTIVAS_DEF = frozenset({"extremo", "medio", "interseccion",
                                "centro"})
UMBRAL_DEFECTO_PX = 10.0
# Color clasico del marcador de referencia (amarillo AutoSnap)
COLOR_MARCA_DEF = "#ffdc00"


@dataclass(frozen=True)
class ConfigCursor:
    """Ajustes del puntero, recordados en prefs['cursor'] (v3.16.0)."""

    mira: bool = True                  # mira visible
    mira_pct: float = 100.0            # 100 = de punta a punta (AutoCAD)
    mira_grosor: int = 1               # px de trazo
    mira_color: str = ""               # vacio = color del tema
    paso_rejilla: float = 0.5          # metros entre lineas de rejilla
    umbral_osnap_px: float = UMBRAL_DEFECTO_PX

    def normalizada(self) -> "ConfigCursor":
        """Copia acotada a valores sanos (tolerante a prefs corruptos)."""
        pct = min(max(float(self.mira_pct), 5.0), 100.0)
        grosor = min(max(int(self.mira_grosor), 1), 5)
        paso = min(max(float(self.paso_rejilla), 0.05), 10.0)
        umbral = min(max(float(self.umbral_osnap_px), 3.0), 40.0)
        return replace(self, mira_pct=pct, mira_grosor=grosor,
                       paso_rejilla=round(paso, 2),
                       umbral_osnap_px=umbral)


def config_de_datos(data: Any = None) -> ConfigCursor:
    """ConfigCursor desde un dict de prefs (tolerante y acotado)."""
    if not isinstance(data, dict):
        return ConfigCursor()
    try:
        return ConfigCursor(
            mira=bool(data.get("mira", True)),
            mira_pct=float(data.get("mira_pct", 100.0)),
            mira_grosor=int(data.get("mira_grosor", 1)),
            mira_color=str(data.get("mira_color", "") or ""),
            paso_rejilla=float(data.get("paso_rejilla", 0.5)),
            umbral_osnap_px=float(data.get("umbral_osnap_px",
                                           UMBRAL_DEFECTO_PX)),
        ).normalizada()
    except (TypeError, ValueError):
        return ConfigCursor()


# ---------------------------------------------------------------------------
# mira
# ---------------------------------------------------------------------------

def puntas_cruz(x: float, y: float, ancho: float, alto: float,
                pct: float = 100.0) -> Tuple[PT, PT, PT, PT]:
    """Extremos (horizontal izq-der, vertical arriba-abajo) de la mira.

    Con pct=100 la cruz cruza TODO el lienzo (AutoCAD por defecto);
    con pct menor queda una cruz de «pantalla * pct / 100» centrada.
    """
    mitad_x = max(2.0, ancho * min(max(pct, 5.0), 100.0) / 200.0)
    mitad_y = max(2.0, alto * min(max(pct, 5.0), 100.0) / 200.0)
    return ((x - mitad_x, y), (x + mitad_x, y),
            (x, y - mitad_y), (x, y + mitad_y))


# ---------------------------------------------------------------------------
# referencias (osnap)
# ---------------------------------------------------------------------------

def _dist(p: PT, q: PT) -> float:
    return math.hypot(q[0] - p[0], q[1] - p[1])


def _puntos_de_muro(muro: Any) -> Optional[Tuple[PT, PT]]:
    """(inicio, fin) del muro, o None si la entidad no lo trae."""
    try:
        a = (float(muro.start[0]), float(muro.start[1]))
        b = (float(muro.end[0]), float(muro.end[1]))
        return a, b
    except (TypeError, ValueError, IndexError, AttributeError):
        return None


def _proyeccion_punto(p: PT, a: PT, b: PT) -> Tuple[PT, float]:
    """Pie de la perpendicular de p sobre el segmento a-b y su t."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    if largo2 < 1e-12:
        return a, 0.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy)
                     / largo2))
    return (a[0] + t * dx, a[1] + t * dy), t


def _centroide(poligono: Sequence[PT]) -> PT:
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _boundary_de(espacio: Any) -> Optional[List[PT]]:
    try:
        boundary = [tuple(float(c) for c in p)
                    for p in (espacio.boundary or [])]
    except (TypeError, ValueError, AttributeError):
        return None
    return boundary if len(boundary) >= 3 else None


def fijaciones(muros: Sequence[Any], punto: PT,
               umbral_mundo: float,
               locales: Sequence[Any] = (),
               marcas: Optional[frozenset] = None) \
        -> List[Tuple[PT, str]]:
    """Candidatas (punto, marca) dentro del umbral, toda la familia.

    ``muros`` son entidades WALL (start/end); ``locales`` entidades
    SPACE (boundary) para el CENTRO. El umbral viene en UNIDADES DE
    MUNDO (la GUI convierte los px del ajuste). ``marcas`` filtra los
    modos activos (None = MARCAS_ACTIVAS_DEF). Marcas: extremo,
    interseccion (cruce de muros), medio, centro, perpendicular (pie
    sobre el muro) y mas_cercano (cualquier punto del muro, que con
    el segmento recto coincide con el pie: la marca difiere por
    precedencia, no por geometria).
    """
    activas = MARCAS_ACTIVAS_DEF if marcas is None else marcas
    salida: List[Tuple[PT, str]] = []
    if umbral_mundo <= 0:
        return salida
    segmentos: List[Tuple[PT, PT]] = []
    for muro in muros:
        par = _puntos_de_muro(muro)
        if par is None:
            continue
        a, b = par
        segmentos.append((a, b))
        for punto_candidato, marca in (
                (a, "extremo"), (b, "extremo"),
                (((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), "medio")):
            if marca in activas \
                    and _dist(punto, punto_candidato) <= umbral_mundo:
                salida.append((punto_candidato, marca))
    # interseccion: cruces de muros distintos dentro del umbral
    if "interseccion" in activas:
        for i in range(len(segmentos)):
            for j in range(i + 1, len(segmentos)):
                cruce = _interseccion_segmentos(segmentos[i],
                                                segmentos[j])
                if cruce is not None \
                        and _dist(punto, cruce) <= umbral_mundo:
                    salida.append((cruce, "interseccion"))
    # mas_cercano: el pie sobre el segmento mas proximo (opt-in)
    if "mas_cercano" in activas:
        mejor_pie: Optional[Tuple[PT, float]] = None
        for a, b in segmentos:
            pie, _t = _proyeccion_punto(punto, a, b)
            d = _dist(punto, pie)
            if d <= umbral_mundo \
                    and (mejor_pie is None or d < mejor_pie[1]):
                mejor_pie = (pie, d)
        if mejor_pie is not None:
            salida.append((mejor_pie[0], "mas_cercano"))
    # centro de locales (centroide del contorno)
    if "centro" in activas:
        for espacio in locales:
            boundary = _boundary_de(espacio)
            if boundary is None:
                continue
            centro = _centroide(boundary)
            if _dist(punto, centro) <= umbral_mundo:
                salida.append((centro, "centro"))
    return salida


def _interseccion_segmentos(seg1: Tuple[PT, PT],
                            seg2: Tuple[PT, PT]) -> Optional[PT]:
    """Cruce de dos segmentos (None si son paralelos o no se tocan)."""
    (a1, a2), (b1, b2) = seg1, seg2
    r = (a2[0] - a1[0], a2[1] - a1[1])
    s = (b2[0] - b1[0], b2[1] - b1[1])
    denominador = r[0] * s[1] - r[1] * s[0]
    if abs(denominador) < 1e-12:
        return None
    qp = (b1[0] - a1[0], b1[1] - a1[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / denominador
    u = (qp[0] * r[1] - qp[1] * r[0]) / denominador
    if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
        return (a1[0] + t * r[0], a1[1] + t * r[1])
    return None


def fijacion_perpendicular(origen: PT, muros: Sequence[Any],
                           punto: PT, umbral_mundo: float) \
        -> Optional[Tuple[PT, str]]:
    """PERPENDICULAR con origen de la orden: el punto de la recta del
    muro donde cae la NORMAL desde el punto anterior (la proyeccion
    del origen sobre la recta, sin cortar al segmento: el PER clasico
    trabaja sobre la recta). El cursor solo decide si el candidato
    esta a mano (dentro del umbral): asin el PER no dispara cuando el
    cursor rasa el muro por otro sitio."""
    if umbral_mundo <= 0:
        return None
    mejor: Optional[Tuple[PT, float]] = None
    for muro in muros:
        par = _puntos_de_muro(muro)
        if par is None:
            continue
        a, b = par
        dx, dy = b[0] - a[0], b[1] - a[1]
        largo2 = dx * dx + dy * dy
        if largo2 < 1e-12:
            continue
        t = ((origen[0] - a[0]) * dx + (origen[1] - a[1]) * dy) / largo2
        candidato = (a[0] + t * dx, a[1] + t * dy)
        d = _dist(punto, candidato)
        if d <= umbral_mundo and (mejor is None or d < mejor[1]):
            mejor = (candidato, d)
    if mejor is None:
        return None
    return (mejor[0], "perpendicular")


def mejor_fijacion(muros: Sequence[Any], punto: PT,
                   umbral_mundo: float,
                   locales: Sequence[Any] = (),
                   origen: Optional[PT] = None,
                   marcas: Optional[frozenset] = None
                   ) -> Optional[Tuple[PT, str]]:
    """La fijacion ganadora: primero la marca de MAYOR prioridad
    (extremo > interseccion > medio > centro > perpendicular >
    mas_cercano) y dentro de ella la mas proxima al cursor. El
    PERPENDICULAR solo entra si hay origen de la orden (la normal
    depende del tramo anterior) y su modo esta activo."""
    activas = MARCAS_ACTIVAS_DEF if marcas is None else marcas
    candidatas = fijaciones(muros, punto, umbral_mundo, locales,
                            activas)
    if origen is not None and "perpendicular" in activas:
        perp = fijacion_perpendicular(origen, muros, punto,
                                      umbral_mundo)
        if perp is not None:
            candidatas.append(perp)
    if not candidatas:
        return None
    candidatas.sort(key=lambda par: (PRIORIDAD_MARCA.get(par[1], 99),
                                     _dist(punto, par[0])))
    return candidatas[0]


# ---------------------------------------------------------------------------
# orto / rejilla / composicion
# ---------------------------------------------------------------------------

def aplicar_orto(origen: PT, destino: PT) -> PT:
    """ORTO (F8): el paso va recto — gana el eje con mayor delta."""
    dx, dy = destino[0] - origen[0], destino[1] - origen[1]
    if abs(dx) >= abs(dy):
        return (destino[0], origen[1])
    return (origen[0], destino[1])


def imantar_rejilla(punto: PT, paso: float) -> PT:
    """IMANTACION (F9): el punto cae en la rejilla mas proxima."""
    if paso <= 0:
        return punto
    return (round(punto[0] / paso) * paso, round(punto[1] / paso) * paso)


def aplicar_ayudas(origen: Optional[PT], destino: PT,
                   osnap: bool, orto: bool, imantacion: bool,
                   muros: Sequence[Any], config: ConfigCursor,
                   px_por_metro: float,
                   paso: Optional[float] = None,
                   locales: Sequence[Any] = ()
                   ) -> Tuple[PT, Optional[str]]:
    """Punto definitivo para un paso de una orden, con la precedencia
    de AutoCAD: la REFERENCIA ganada gana; si no, ORTO; y despues la
    IMANTACION redondea lo que quede.

    ``paso`` permite imantar con el paso ADAPTATIVO de la rejilla que
    se dibuja (v3.38: niveles anidados); si es None se usa el paso
    fijo de la configuracion. ``locales`` activa el CENTRO de los
    contornos de los locales (v3.38).

    Devuelve (punto, marca_de_referencia o None).
    """
    config = config.normalizada()
    if osnap and px_por_metro > 0:
        umbral = config.umbral_osnap_px / max(px_por_metro, 1e-9)
        ganada = mejor_fijacion(muros, destino, umbral,
                                locales, origen)
        if ganada is not None:
            return ganada[0], ganada[1]
    punto = destino
    if orto and origen is not None:
        punto = aplicar_orto(origen, punto)
    if imantacion:
        punto = imantar_rejilla(punto, paso or config.paso_rejilla)
    return punto, None


def color_mira(color_config: str, color_tema: str) -> str:
    """Color final de la mira: el configurado, o el del tema."""
    return color_config or color_tema or "#ffffff"


def dict_de_config(config: ConfigCursor) -> Dict[str, Any]:
    """Dict plano para prefs['cursor'] (solo claves ASCII)."""
    config = config.normalizada()
    return {
        "mira": bool(config.mira),
        "mira_pct": float(config.mira_pct),
        "mira_grosor": int(config.mira_grosor),
        "mira_color": str(config.mira_color),
        "paso_rejilla": float(config.paso_rejilla),
        "umbral_osnap_px": float(config.umbral_osnap_px),
    }


__all__ = [
    "ConfigCursor", "MARCAS", "MARCAS_V16", "PRIORIDAD_MARCA",
    "MARCAS_ACTIVAS_DEF", "COLOR_MARCA_DEF", "UMBRAL_DEFECTO_PX",
    "config_de_datos", "dict_de_config", "puntas_cruz", "fijaciones",
    "fijacion_perpendicular", "mejor_fijacion",
    "aplicar_orto", "imantar_rejilla", "aplicar_ayudas", "color_mira",
]
