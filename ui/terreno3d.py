"""TERRENO 3D (v3.13.0) — el solar donde se posa el edificio.

Malla determinista de cuadrícula (cero dependencias): una pendiente
uniforme en la dirección que se pida, un relieve ondulado generado por
«ruido de valores» con semilla (mismo solar siempre, en cualquier
máquina) y una PLATAFORMA NIVELADA bajo la huella del edificio (el
terreno se allana a -1 cm dentro del solar para que la losa del nivel
0 no pelee con la malla). Los quads que caen por completo bajo la
huella se omiten: ahí manda la plataforma del edificio.

La altura del terreno alimenta también a las sombras (ui.solar), que
se arrugan siguiendo la pendiente en vez de flotar sobre ella.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

from ui.view3d import Cara3D, _profundidad, _rgb_a_hex

Recto = Tuple[float, float, float, float]

# Rampa de colores del terreno: verde de pradera abajo, tierra en
# medio, tierra clara arriba (colores FIJOS Tk/PNG).
_C_BAJA = (122, 141, 88)
_C_MEDIA = (164, 146, 106)
_C_ALTA = (198, 184, 152)

_PAD_Z = -0.01          # cota del terreno allanado bajo la huella
_SUAVIZADO_PAD = 2.5    # metros de transición huella → terreno libre


@dataclass
class TerrenoOpts:
    """Parámetros del solar.

    ``pendiente_pct`` es la inclinación uniforme (0-25 %) y
    ``direccion_deg`` el azimut HACIA EL QUE BAJA el terreno
    (0 = baja hacia el norte). ``relieve_m`` es la amplitud de las
    ondulaciones (ruido determinista con ``semilla``);
    ``extension_m`` es el margen de solar alrededor de la huella y
    ``resolucion`` las divisiones de la malla por eje.
    """

    pendiente_pct: float = 0.0
    direccion_deg: float = 0.0
    relieve_m: float = 0.0
    semilla: int = 42
    extension_m: float = 8.0
    resolucion: int = 26


# -- ruido de valores determinista -------------------------------------------
def _fraccion(valor: float) -> float:
    """Parte fraccionaria positiva de un valor (hash flotante)."""
    t = math.sin(valor) * 43758.5453
    return t - math.floor(t)


def _ruido_valor(x: float, y: float, celda: float, semilla: int) -> float:
    """Ruido bilineal de valores en una retícula de lado ``celda``.

    Continuo, determinista y sin dependencias: la misma esquina de la
    retícula produce siempre la misma altura (semilla fija).
    """
    if celda <= 1e-9:
        return 0.5
    gx = x / celda
    gy = y / celda
    x0, y0 = math.floor(gx), math.floor(gy)
    fx, fy = gx - x0, gy - y0
    fx = fx * fx * (3.0 - 2.0 * fx)  # smoothstep
    fy = fy * fy * (3.0 - 2.0 * fy)
    s = float(semilla) * 74.7

    def _esquina(ix: int, iy: int) -> float:
        return _fraccion(ix * 127.1 + iy * 311.7 + s)

    a = _esquina(x0, y0)
    b = _esquina(x0 + 1, y0)
    c = _esquina(x0, y0 + 1)
    d = _esquina(x0 + 1, y0 + 1)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


# -- altura -------------------------------------------------------------------
def altura_en(x: float, y: float, opts: TerrenoOpts,
              recto: Recto) -> float:
    """Altura del terreno natural (m) en el punto (x, y).

    Pendiente uniforme en la dirección pedida + ondulaciones de ruido
    + plataforma allanada bajo la huella (transición suave de
    ``_SUAVIZADO_PAD`` metros para que el edificio no quede colgando).
    """
    minx, miny, maxx, maxy = recto
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    az = math.radians(opts.direccion_deg)
    vx, vy = math.sin(az), math.cos(az)  # hacia donde BAJA
    pendiente = max(0.0, min(100.0, float(opts.pendiente_pct))) / 100.0
    h_llano = -pendiente * ((x - cx) * vx + (y - cy) * vy)
    extension = max(maxx - minx, maxy - miny, 1.0)
    celda = max(extension / 3.0, 1.5)
    ondulacion = max(0.0, float(opts.relieve_m)) * (
        2.0 * _ruido_valor(x, y, celda, opts.semilla) - 1.0)
    h_libre = h_llano + ondulacion
    # distancia FUERA de la huella (0 dentro)
    dx = max(minx - x, 0.0, x - maxx)
    dy = max(miny - y, 0.0, y - maxy)
    fuera = math.hypot(dx, dy)
    t = max(0.0, min(1.0, fuera / max(_SUAVIZADO_PAD, 1e-6)))
    t = t * t * (3.0 - 2.0 * t)
    return _PAD_Z + (h_libre - _PAD_Z) * t


# -- malla --------------------------------------------------------------------
def _color_terreno(t: float) -> str:
    """Interpola la rampa verde → tierra → tierra clara (t en 0..1)."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        k = t / 0.5
        a, b = _C_BAJA, _C_MEDIA
    else:
        k = t - 0.5
        a, b = _C_MEDIA, _C_ALTA
    return _rgb_a_hex((a[0] + (b[0] - a[0]) * k,
                       a[1] + (b[1] - a[1]) * k,
                       a[2] + (b[2] - a[2]) * k))


def malla_terreno(recto: Recto, opts: TerrenoOpts) -> Tuple[
        List[List[float]], float, float]:
    """Alturas de la malla ``(ny+1)x(nx+1)`` y rango [min, max].

    Fila 0 = sur (y mínimo), columna 0 = oeste (x mínimo). Determinista
    con la semilla; útil para pruebas y para acotar la rampa de color.
    """
    minx, miny, maxx, maxy = recto
    n = max(4, min(60, int(opts.resolucion)))
    extension_x = (maxx - minx) + 2.0 * max(0.5, opts.extension_m)
    extension_y = (maxy - miny) + 2.0 * max(0.5, opts.extension_m)
    paso_x = extension_x / n
    paso_y = extension_y / n
    alturas: List[List[float]] = []
    hmin = hmax = None
    for j in range(n + 1):
        fila: List[float] = []
        for i in range(n + 1):
            h = altura_en(minx - max(0.5, opts.extension_m) + i * paso_x,
                          miny - max(0.5, opts.extension_m) + j * paso_y,
                          opts, recto)
            fila.append(h)
            if hmin is None or h < hmin:
                hmin = h
            if hmax is None or h > hmax:
                hmax = h
        alturas.append(fila)
    if hmin is None:
        hmin = hmax = 0.0
    return alturas, hmin, hmax


def caras_de_terreno(recto: Recto, opts: TerrenoOpts,
                     camara: Any) -> List[Cara3D]:
    """Quads del solar listos para el orden del pintor.

    Se omiten los quads cuyas 4 esquinas caen DENTRO de la huella
    (ahí está la plataforma del edificio) y se colorea por altura con
    la rampa fija. El conjunto entero es determinista.
    """
    minx, miny, maxx, maxy = recto
    if maxx <= minx or maxy <= miny:
        return []
    n = max(4, min(60, int(opts.resolucion)))
    margen = max(0.5, float(opts.extension_m))
    extension_x = (maxx - minx) + 2.0 * margen
    extension_y = (maxy - miny) + 2.0 * margen
    paso_x = extension_x / n
    paso_y = extension_y / n
    x0 = minx - margen
    y0 = miny - margen
    alturas, hmin, hmax = malla_terreno(recto, opts)
    rango = max(hmax - hmin, 1e-6)
    caras: List[Cara3D] = []
    for j in range(n):
        for i in range(n):
            esquinas_xy = ((x0 + i * paso_x, y0 + j * paso_y),
                           (x0 + (i + 1) * paso_x, y0 + j * paso_y),
                           (x0 + (i + 1) * paso_x, y0 + (j + 1) * paso_y),
                           (x0 + i * paso_x, y0 + (j + 1) * paso_y))
            # bajo la huella del edificio manda la plataforma: se omite
            if all(minx < px < maxx and miny < py < maxy
                   for (px, py) in esquinas_xy):
                continue
            puntos = [(px, py, alturas[jj][ii])
                      for (px, py), (ii, jj) in
                      zip(esquinas_xy, ((i, j), (i + 1, j),
                                        (i + 1, j + 1), (i, j + 1)))]
            t = (sum(p[2] for p in puntos) / 4.0 - hmin) / rango
            caras.append(Cara3D(
                puntos=puntos, color=_color_terreno(t), kind="terreno",
                profundidad=sum(_profundidad(p, camara)
                                for p in puntos) / len(puntos)))
    return caras


__all__ = ["TerrenoOpts", "altura_en", "malla_terreno", "caras_de_terreno"]
