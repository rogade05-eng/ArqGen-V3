"""SOMBRAS SOLARES Y ORIENTACIÓN (v3.13.0) — el edificio a la luz del sol.

Matemática 100% pura (cero dependencias): posición solar por
declinación de Cooper + ángulo horario (sol de reloj, no de leyenda),
sombras proyectadas por rayos paralelos sobre el terreno, brújula con
el norte pintado de rojo y arco de la trayectoria solar del día.
La convención de azimut es la de los planos: 0° = NORTE, 90° = ESTE,
180° = SUR, 270° = OESTE, medido en el sentido horario visto desde
arriba. En el mundo de la app, +X es el ESTE y +Y es el NORTE.

Todo lo que devuelve son ``Cara3D`` del mismo motor de ui.view3d, así
que el lienzo Tk y el PNG determinista salen idénticos de fábrica.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ui.view3d import Cara3D, Modelo3D, _profundidad, _hex_a_rgb, sombrea

Punto2 = Tuple[float, float]
Punto3 = Tuple[float, float, float]

# Colores FIJOS (idénticos en Tk y PNG): la sombra es un gris pizarra
# apagado para que se lea sobre el fondo claro y sobre el terreno.
COLOR_SOMBRA = "#6b7480"
COLOR_BRUJULA_NORTE = "#c0392b"
COLOR_BRUJULA = "#8a93a0"
COLOR_SOL = "#f2b234"
COLOR_SOL_ACTUAL = "#e88b2d"

# El sol se considera "visible" por encima de esta elevación (grados):
# por debajo, las sombras son tan largas y rasantes que engañan.
ELEVACION_MINIMA = 0.5

# Fechas canónicas (día del año, año no bisiesto).
FECHAS_CANONICAS: Dict[str, int] = {
    "21 mar (equinoccio)": 80,
    "21 jun (solsticio)": 172,
    "21 sep (equinoccio)": 264,
    "21 dic (solsticio)": 355,
}


@dataclass
class SolarOpts:
    """Parámetros del sol: latitud del sitio, día del año y hora solar.

    ``latitud_deg`` es positiva al norte (La Habana +23.1, Santiago
    -33.4); ``dia_anio`` va de 1 a 365; ``hora`` es hora solar local
    (12.0 = mediodía solar, el sol cruza el meridiano del sitio).
    """

    latitud_deg: float = 23.1
    dia_anio: int = 172
    hora: float = 12.0


# -- posición solar ----------------------------------------------------------
def declinacion_solar(dia_anio: int) -> float:
    """Declinación del sol en grados (Cooper, 1969).

    Vale +23.44° en el solsticio de junio, -23.44° en el de diciembre
    y cruza por 0° en los equinoccios. Determinista y sin librerías.
    """
    n = max(1, min(365, int(dia_anio)))
    return 23.44 * math.sin(2.0 * math.pi * (284 + n) / 365.0)


def posicion_solar(latitud_deg: float, dia_anio: int,
                   hora: float) -> Tuple[float, float]:
    """Posición del sol como ``(azimut_deg, elevacion_deg)``.

    Azimut desde el norte, horario (0=N, 90=E, 180=S, 270=O);
    elevación sobre el horizonte (negativa de noche). Se deriva del
    vector sol en coordenadas ENU, que no admite ambigüedades de
    cuadrante:

        E = -cos(d)·sin(H)      H = ángulo horario (15° por hora)
        N = sin(d)·cos(f) - cos(d)·sin(f)·cos(H)
        U = sin(f)·sin(d) + cos(f)·cos(d)·cos(H)
    """
    phi = math.radians(latitud_deg)
    delta = math.radians(declinacion_solar(dia_anio))
    H = math.radians(15.0 * (float(hora) - 12.0))
    este = -math.cos(delta) * math.sin(H)
    norte = (math.sin(delta) * math.cos(phi)
             - math.cos(delta) * math.sin(phi) * math.cos(H))
    arriba = (math.sin(phi) * math.sin(delta)
              + math.cos(phi) * math.cos(delta) * math.cos(H))
    azimut = math.degrees(math.atan2(este, norte)) % 360.0
    elevacion = math.degrees(math.asin(max(-1.0, min(1.0, arriba))))
    return (azimut, elevacion)


def vector_al_sol(azimut_deg: float, elevacion_deg: float) -> Punto3:
    """Vector unitario DESDE el sitio HACIA el sol (x=E, y=N, z=arriba)."""
    az = math.radians(azimut_deg)
    el = math.radians(elevacion_deg)
    return (math.sin(az) * math.cos(el),
            math.cos(az) * math.cos(el),
            math.sin(el))


def sol_visible(elevacion_deg: float) -> bool:
    """True si el sol está lo bastante alto como para proyectar sombra."""
    return elevacion_deg > ELEVACION_MINIMA


# -- geometría de sombras ------------------------------------------------------
def envolvente_convexa(puntos: Sequence[Punto2]) -> List[Punto2]:
    """Envolvente convexa 2D (cadena monótona de Andrew).

    Para las sombras: la sombra de una caja bajo el sol es la envolvente
    de sus 8 esquinas proyectadas. Deduplica, tolera puntos colineales
    y devuelve el polígono en orden antihorario sin cerrar.
    """
    limpios = sorted(set((float(x), float(y)) for x, y in puntos))
    if len(limpios) <= 2:
        return list(limpios)

    def _giro(o: Punto2, a: Punto2, b: Punto2) -> float:
        return ((a[0] - o[0]) * (b[1] - o[1])
                - (a[1] - o[1]) * (b[0] - o[0]))

    inferior: List[Punto2] = []
    for p in limpios:
        while len(inferior) >= 2 and _giro(inferior[-2], inferior[-1], p) <= 0:
            inferior.pop()
        inferior.append(p)
    superior: List[Punto2] = []
    for p in reversed(limpios):
        while len(superior) >= 2 and _giro(superior[-2], superior[-1], p) <= 0:
            superior.pop()
        superior.append(p)
    return inferior[:-1] + superior[:-1]


def _clip_con_recto(poligono: Sequence[Punto2],
                    recto: Tuple[float, float, float, float]) -> List[Punto2]:
    """Intersección del polígono con el rectángulo (Sutherland-Hodgman).

    Cada paso recorta contra UN borde (x>=minx, x<=maxx, y>=miny,
    y<=maxy) y la intersección cae SIEMPRE en el límite de ese borde.
    Se usa para dejar las sombras solo en las franjas de terreno
    fuera de la huella del edificio.
    """
    minx, miny, maxx, maxy = recto
    if maxx <= minx or maxy <= miny:
        return list(poligono)
    salida = list(poligono)
    for dentro, coord, limite in (
            (lambda p: p[0] >= minx, 0, minx),
            (lambda p: p[0] <= maxx, 0, maxx),
            (lambda p: p[1] >= miny, 1, miny),
            (lambda p: p[1] <= maxy, 1, maxy)):
        if not salida:
            break
        entrada, salida = salida, []
        previo = entrada[-1]
        previo_dentro = dentro(previo)
        for actual in entrada:
            actual_dentro = dentro(actual)
            if actual_dentro != previo_dentro:
                if coord == 0:
                    dy = actual[1] - previo[1]
                    t = 0.0 if actual[0] == previo[0] else \
                        (limite - previo[0]) / (actual[0] - previo[0])
                    salida.append((limite, previo[1] + t * dy))
                else:
                    dx = actual[0] - previo[0]
                    t = 0.0 if actual[1] == previo[1] else \
                        (limite - previo[1]) / (actual[1] - previo[1])
                    salida.append((previo[0] + t * dx, limite))
            if actual_dentro:
                salida.append(actual)
            previo, previo_dentro = actual, actual_dentro
    return salida


def poligono_sombra(esquinas: Sequence[Punto3], azimut_deg: float,
                    elevacion_deg: float) -> Optional[List[Punto2]]:
    """Sombra (polígono 2D en el suelo z=0) de un prisma por sus esquinas.

    Proyección paralela: cada esquina (x, y, z) se desplaza sobre el rayo
    de luz hasta cortar el suelo. Devuelve None si el sol está bajo.
    """
    if not esquinas or not sol_visible(elevacion_deg):
        return None
    tangente = 1.0 / math.tan(math.radians(max(elevacion_deg,
                                               ELEVACION_MINIMA)))
    az = math.radians(azimut_deg)
    proyectadas: List[Punto2] = []
    for (x, y, z) in esquinas:
        caida = max(0.0, float(z)) * tangente
        proyectadas.append((x - caida * math.sin(az),
                            y - caida * math.cos(az)))
    return envolvente_convexa(proyectadas)


# -- caras para el render -----------------------------------------------------
def _bbox_total(modelo: Modelo3D) -> Optional[Tuple[float, float, float,
                                                    float]]:
    """Huella total del edificio (muros y locales de TODOS los niveles)."""
    xs: List[float] = []
    ys: List[float] = []
    for muro in modelo.muros:
        for punto in (muro.start, muro.end):
            xs.append(float(punto[0]))
            ys.append(float(punto[1]))
    for espacio in modelo.locales:
        for punto in (espacio.boundary or []):
            xs.append(float(punto[0]))
            ys.append(float(punto[1]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def caras_de_sombras(modelo: Modelo3D, opts: SolarOpts, camara: Any,
                     z_suelo: Optional[Callable[[float, float], float]] = None
                     ) -> List[Cara3D]:
    """Sombras de todos los muros del modelo sobre el terreno.

    Cada muro es una caja: su sombra es la envolvente convexa de las 8
    esquinas proyectadas, recortada para no invadir la huella del
    edificio y «pegada» al terreno cuando hay malla de terreno (la
    sombra se arruga siguiendo la pendiente).
    """
    az, el = posicion_solar(opts.latitud_deg, opts.dia_anio, opts.hora)
    if not sol_visible(el):
        return []
    recto = _bbox_total(modelo)
    if recto is None:
        return []
    # Las sombras se pintan SOLO en el suelo fuera de la huella: la
    # huella se expande en 4 franjas (norte/sur/este/oeste) y la sombra
    # se interseca con cada una (la parte que cae «debajo» del edificio
    # la tapan los propios muros y provocaría parpadeos coplanares).
    minx, miny, maxx, maxy = recto
    holgura = 0.06
    lejos = 10000.0
    franjas = (
        (minx - holgura, maxy + holgura, maxx + holgura, maxy + lejos),
        (minx - holgura, miny - lejos, maxx + holgura, miny - holgura),
        (maxx + holgura, miny - holgura, maxx + lejos, maxy + holgura),
        (minx - lejos, miny - holgura, minx - holgura, maxy + holgura))
    nivel_por_id = modelo.nivel_por_id
    caras: List[Cara3D] = []
    for muro in modelo.muros:
        n3 = nivel_por_id.get(getattr(muro, "level_id", ""))
        if n3 is None:
            continue
        x1, y1 = float(muro.start[0]), float(muro.start[1])
        x2, y2 = float(muro.end[0]), float(muro.end[1])
        dx, dy = x2 - x1, y2 - y1
        largo = math.hypot(dx, dy)
        espesor = float(getattr(muro, "thickness_m", 0.2) or 0.2)
        altura = float(getattr(muro, "height_m", 3.0) or 3.0)
        if largo <= 0.0 or espesor <= 0.0 or altura <= 0.0:
            continue
        u = (dx / largo, dy / largo)
        n = (-u[1], u[0])
        half = espesor / 2.0
        z0 = n3.base_z + float(getattr(muro, "base_offset_m", 0.0) or 0.0)
        z1 = z0 + altura
        apoyos = [(x1 + n[0] * half, y1 + n[1] * half),
                  (x2 + n[0] * half, y2 + n[1] * half),
                  (x2 - n[0] * half, y2 - n[1] * half),
                  (x1 - n[0] * half, y1 - n[1] * half)]
        esquinas = ([(px, py, z0) for (px, py) in apoyos]
                    + [(px, py, z1) for (px, py) in apoyos])
        sombra = poligono_sombra(esquinas, az, el)
        if not sombra:
            continue
        for franja in franjas:
            trozo = _clip_con_recto(sombra, franja)
            if len(trozo) < 3:
                continue
            if z_suelo is not None:
                puntos = [(px, py, z_suelo(px, py) + 0.004)
                          for (px, py) in trozo]
            else:
                puntos = [(px, py, 0.004) for (px, py) in trozo]
            caras.append(Cara3D(
                puntos=puntos, color=COLOR_SOMBRA, kind="sombra",
                profundidad=sum(_profundidad(p, camara)
                                for p in puntos) / len(puntos)))
    return caras


def caras_de_sol(modelo: Modelo3D, opts: SolarOpts, camara: Any) -> List[Cara3D]:
    """Brújula + trayectoria solar del día + disco del sol actual.

    - Brújula al sur de la huella: aguja NORTE roja, resto gris, con
      una plaquita base (todo polígonos, sin texto).
    - Arco solar: un disco pequeño por cada hora soleada de 5 a 19 h
      sobre la semiesfera de radio R; el disco de la hora elegida es
      mayor y naranja. De noche solo queda la brújula.
    """
    recto = _bbox_total(modelo)
    if recto is None:
        return []
    minx, miny, maxx, maxy = recto
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    extension = max(maxx - minx, maxy - miny, 6.0)
    radio = extension * 0.62
    caras: List[Cara3D] = []

    # -- brújula --------------------------------------------------------
    bx, by = cx, miny - max(3.5, extension * 0.30)
    _emite_disco(caras, (bx, by, 0.008), 0.42, COLOR_BRUJULA, "brujula",
                 camara)
    for azimut, color in ((0.0, COLOR_BRUJULA_NORTE), (90.0, COLOR_BRUJULA),
                          (180.0, COLOR_BRUJULA), (270.0, COLOR_BRUJULA)):
        az = math.radians(azimut)
        vx, vy = math.sin(az), math.cos(az)
        px, py = -vy, vx  # perpendicular
        largo, ancho = 1.7, 0.16
        punta = (bx + vx * largo, by + vy * largo)
        izq = (bx + px * ancho, by + py * ancho)
        der = (bx - px * ancho, by - py * ancho)
        puntos = [(izq[0], izq[1], 0.01), (der[0], der[1], 0.01),
                  (punta[0], punta[1], 0.01)]
        caras.append(Cara3D(
            puntos=puntos, color=color, kind="brujula",
            profundidad=sum(_profundidad(p, camara)
                            for p in puntos) / len(puntos)))

    # -- trayectoria solar ----------------------------------------------
    for hora in range(5, 20):
        az, el = posicion_solar(opts.latitud_deg, opts.dia_anio,
                                float(hora))
        if not sol_visible(el):
            continue
        actual = abs(float(hora) - opts.hora) < 0.5
        v = vector_al_sol(az, el)
        centro = (cx + v[0] * radio, cy + v[1] * radio, v[2] * radio)
        _emite_disco(caras, centro,
                     radio * (0.075 if actual else 0.03),
                     COLOR_SOL_ACTUAL if actual else COLOR_SOL,
                     "sol_actual" if actual else "sol", camara)
    return caras


def _emite_disco(caras: List[Cara3D], centro: Punto3, radio: float,
                 color: str, kind: str, camara: Any) -> None:
    """Disco regular de 8 lados horizontal (marcador de sol/brújula)."""
    cx, cy, cz = centro
    puntos: List[Punto3] = []
    for i in range(8):
        ang = math.pi / 4.0 * i
        puntos.append((cx + radio * math.cos(ang),
                       cy + radio * math.sin(ang), cz))
    caras.append(Cara3D(
        puntos=puntos, color=color, kind=kind,
        profundidad=sum(_profundidad(p, camara)
                        for p in puntos) / len(puntos)))


def resumen_solar(opts: SolarOpts) -> str:
    """Línea de estado: «sol az 180° el 44° (21 dic · 12 h)»."""
    az, el = posicion_solar(opts.latitud_deg, opts.dia_anio, opts.hora)
    fecha = next((nombre for nombre, dia in FECHAS_CANONICAS.items()
                  if dia == int(opts.dia_anio)),
                 "día %d" % int(opts.dia_anio))
    fecha = " ".join(fecha.split(" ")[:2])  # «21 jun» sin el paréntesis
    if not sol_visible(el):
        return "sol bajo el horizonte (%s · %02d h)" % (
            fecha, int(opts.hora) % 24)
    return "sol az %d° el %d° (%s · %02d h)" % (
        round(az) % 360, round(el), fecha, int(opts.hora) % 24)


def recomendacion_orientacion(latitud_deg: float,
                              recto: Tuple[float, float, float,
                                           float]) -> str:
    """Frase amable con la orientación recomendada para la latitud.

    Regla de oro: en el hemisferio norte la fachada principal agradece
    el SUR (sol de invierno bajo + aleros contra el de verano); en el
    austral, el NORTE; en la banda tórrida manda la sombra y el aire.
    """
    minx, miny, maxx, maxy = recto
    ancho = maxx - minx
    fondo = maxy - miny
    if ancho >= fondo:
        largas = "este-oeste (fachadas largas al norte y al sur)"
    else:
        largas = "norte-sur (fachadas largas al este y al oeste)"
    if abs(latitud_deg) < 15.0:
        consejo = "banda tórrida: manda la sombra (aleros amplios) y la ventilación cruzada"
    elif latitud_deg > 0.0:
        consejo = "fachada principal al SUR para el sol de invierno"
    else:
        consejo = "fachada principal al NORTE para el sol de invierno"
    return "Huella con ejes %s; a %.0f° de latitud: %s." % (
        largas, abs(latitud_deg), consejo)


__all__ = [
    "SolarOpts", "FECHAS_CANONICAS", "ELEVACION_MINIMA",
    "declinacion_solar", "posicion_solar", "vector_al_sol", "sol_visible",
    "envolvente_convexa", "poligono_sombra", "caras_de_sombras",
    "caras_de_sol", "resumen_solar", "recomendacion_orientacion",
    "_bbox_total",
]
