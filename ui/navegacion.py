"""NAVEGACION DE VISTA (v3.38.0) — ui/navegacion.py.

Las piezas headless de la navegacion clasica (ideas del CAD clasico,
reimplementadas de cero):

- ``PilaVistas``: ZOOM ANTERIOR con pila acotada a 32 entradas. Cada
  zoom, pan o encuadre guarda (cx, cy, escala) antes de moverse;
  ``pop()`` devuelve la vista anterior y la elimina.
- ``rejilla_adaptativa``: rejilla ANIDADA por niveles (paso base x
  ``mayor_cada``^nivel). Al alejar, sube de nivel cuando la celda fina
  baja del minimo en pantalla; al acercar, vuelve a dividir; la BANDA
  ANTIFLIP evita que una muesca de rueda oscile entre dos niveles
  (el nivel previo se conserva mientras su celda siga en banda).
- ``ENCUADRE_VACIO``: el encuadre honesto de un lienzo sin nada
  (-50..50 m) para que el canvas nunca enmarque el caos.

Cero Tk: el mismo motor sirve a la GUI, a la CLI y a las pruebas.
Todos los mensajes son 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

TOPE_PILA = 32

# encuadre por defecto de un lienzo vacio (m)
ENCUADRE_VACIO: Tuple[float, float, float, float] = \
    (-50.0, -50.0, 50.0, 50.0)


class PilaVistas:
    """Pila acotada de vistas para ZOOM ANTERIOR."""

    def __init__(self, tope: int = TOPE_PILA) -> None:
        self._tope = max(1, int(tope))
        self._vistas: List[Tuple[float, float, float]] = []

    def push(self, cx: float, cy: float, escala: float) -> None:
        """Guarda la vista ACTUAL antes de cambiarla; si la pila esta
        llena, la mas vieja cae."""
        self._vistas.append((float(cx), float(cy), float(escala)))
        if len(self._vistas) > self._tope:
            del self._vistas[:-self._tope]

    def pop(self) -> Optional[Tuple[float, float, float]]:
        """La ultima vista guardada (y la quita). None si no hay."""
        if not self._vistas:
            return None
        return self._vistas.pop()

    def peek(self) -> Optional[Tuple[float, float, float]]:
        """La ultima vista guardada sin quitarla."""
        if not self._vistas:
            return None
        return self._vistas[-1]

    def __len__(self) -> int:
        return len(self._vistas)

    def limpiar(self) -> None:
        self._vistas.clear()


# ---------------------------------------------------------------------------
# rejilla anidada adaptativa
# ---------------------------------------------------------------------------

CELDA_MIN_PX = 25.0          # la celda visible nunca baja de esto
BANDA_FLIP_INFERIOR = 0.8    # antiflip: conservar nivel hasta 0.8x
BANDA_FLIP_SUPERIOR = 1.25   # ... y hasta 1.25x el minimo


def rejilla_adaptativa(cx: float, cy: float, escala: float,
                       ancho_px: float, alto_px: float,
                       paso_base: float = 1.0, mayor_cada: int = 5,
                       celda_min_px: float = CELDA_MIN_PX,
                       nivel_previo: Optional[int] = None) \
        -> Dict[str, object]:
    """El nivel de rejilla visible y sus lineas.

    Devuelve un dict con:
    - ``paso``: paso del nivel elegido en metros (base x mayor^nivel)
    - ``nivel``: profundidad anidada (0 = paso base)
    - ``celda_px``: tamano en pantalla de la celda del nivel
    - ``menores``: lineas finas ``[(x0, x1, y), (x, y0, y1)...]``? No:
      ``x``/``y`` por separado — ``lineas_x`` [(x, es_major)...] y
      ``lineas_y`` [(y, es_major)...] con ``es_major`` True en cada
      ``mayor_cada``-esima linea (la rejilla anidada clasica).
    """
    escala = max(float(escala or 0.0), 1e-9)
    base = max(float(paso_base or 0.0), 1e-9)
    mayor_cada = max(1, int(mayor_cada))
    celda_min_px = max(float(celda_min_px or 0.0), 1.0)
    # nivel tal que la celda >= minimo: al alejar sube, al acercar baja
    nivel = 0
    while base * (mayor_cada ** nivel) * escala < celda_min_px:
        nivel += 1
        if nivel > 64:               # blindaje: escala absurda
            break
    # banda antiflip: con nivel previo conocido, conservarlo mientras
    # su celda siga dentro de la banda (una muesca de rueda no oscila)
    if nivel_previo is not None and nivel_previo >= 0:
        celda_previa = base * (mayor_cada ** nivel_previo) * escala
        if celda_min_px * BANDA_FLIP_INFERIOR <= celda_previa \
                <= celda_min_px * BANDA_FLIP_SUPERIOR:
            nivel = nivel_previo
    paso = base * (mayor_cada ** nivel)
    celda_px = paso * escala
    # rectangulo visible en metros
    medio_x = (ancho_px / 2.0) / escala
    medio_y = (alto_px / 2.0) / escala
    x0, x1 = cx - medio_x, cx + medio_x
    y0, y1 = cy - medio_y, cy + medio_y
    lineas_x: List[Tuple[float, bool]] = []
    lineas_y: List[Tuple[float, bool]] = []
    # la primera linea MAYOR alineada: multiplos del paso x mayor_cada
    paso_mayor = paso * mayor_cada
    i = int(math.floor(x0 / paso))
    while i * paso <= x1:
        x = i * paso
        es_major = (i % mayor_cada == 0)
        lineas_x.append((round(x, 9), es_major))
        i += 1
    j = int(math.floor(y0 / paso))
    while j * paso <= y1:
        y = j * paso
        es_major = (j % mayor_cada == 0)
        lineas_y.append((round(y, 9), es_major))
        j += 1
    # blindaje de cantidad: mas de 400 lineas por eje es un error de
    # nivel (no deberia ocurrir con la seleccion anterior); se devuelve
    # el nivel igualmente para que la GUI decida no dibujar
    return {"paso": paso, "nivel": nivel, "celda_px": celda_px,
            "paso_mayor": paso_mayor,
            "lineas_x": lineas_x, "lineas_y": lineas_y,
            "rango_x": (x0, x1), "rango_y": (y0, y1)}


def encuadre_de(bounds: Optional[Tuple[float, float, float, float]]) \
        -> Tuple[float, float, float, float]:
    """El encuadre a usar: los bounds reales o el rectangulo honesto
    de un lienzo vacio (ENCUADRE_VACIO)."""
    if not bounds:
        return ENCUADRE_VACIO
    x0, y0, x1, y1 = bounds
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return ENCUADRE_VACIO
    if x1 - x0 < 1e-9 or y1 - y0 < 1e-9:
        return ENCUADRE_VACIO
    return (x0, y0, x1, y1)


__all__ = ["PilaVistas", "TOPE_PILA", "ENCUADRE_VACIO",
           "CELDA_MIN_PX", "BANDA_FLIP_INFERIOR", "BANDA_FLIP_SUPERIOR",
           "rejilla_adaptativa", "encuadre_de"]
