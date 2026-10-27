"""VISTA 3D AXONOMÉTRICA y EN PERSPECTIVA (v3.11.0 / v3.17.0) — el
edificio que acabas de regenerar, ahora se gira.

Matemática 100% pura (cero dependencias): la cámara gira en AZIMUT e
inclina en ELEVACIÓN; cada muro del proyecto se extruye como caja con
eliminación de caras traseras (back-face culling), los pisos de los
locales se pintan por tipo, los vanos salen a su cota real (antepecho
incluido) sobre la cara visible del muro que los aloja, y cada nivel
descansa sobre una plataforma. La profundidad se resuelve con el
«orden del pintor» (lejos primero, cerca después) y la «explosión»
separa los niveles verticalmente para verlos uno a uno.

Proyección doble (v3.17.0): la AXONOMÉTRICA de siempre (ojo en el
infinito) y la PERSPECTIVA con punto de fuga — la cámara se coloca a
la distancia que el FOV pide respecto al centro del modelo y divide
por la profundidad, con los próximos puntos creciendo y los lejanos
encogiéndose, como se ve en la realidad.

Dos salidas con el MISMO motor: el lienzo Tk del diálogo (polygons)
y el PNG determinista 100% stdlib sobre exporters.png_exporter —
misma lista de caras, mismo encuadre y mismos colores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from exporters import png_exporter as png

Punto3 = Tuple[float, float, float]

# Paleta FIJA de la vista 3D (independiente del tema oscuro/claro para
# que el lienzo Tk y el PNG determinista coincidan siempre).
MURO_BASE = "#aeb9c4"
COLOR_VANO: Dict[str, str] = {
    "DOOR": "#f6ad55", "WINDOW": "#63b3ed", "OPENING": "#8b95a6"}
COLOR_TIPO: Dict[str, str] = {
    "PATIO": "#4a5d43", "PASILLO": "#3d4a5c", "HALL": "#3d4a5c",
    "KITCHEN": "#37505e", "BATHROOM": "#37505e", "BAÑO": "#37505e"}
COLOR_LOCAL_DEFECTO = "#546a7b"
COLOR_PLATAFORMA = "#8f9aa8"
COLOR_MONO_MURO = "#9fb0bd"
COLOR_MONO_PISO = "#cfd6dd"
COLOR_MONO_VANO = "#6b7684"
COLOR_MONO_PLATAFORMA = "#aab4bf"
# Concepción de espacios (v3.15.0): cubiertas por material, muebles por
# categoría y accesibilidad (rampa/barandilla) con colores fijos para
# que el lienzo Tk y el PNG coincidan.
COLOR_CUBIERTA: Dict[str, str] = {
    "teja_curva": "#a85d43", "teja_plana": "#b0654a", "pizarra": "#5c6670",
    "chapa_metalica": "#9aa5ad", "fibrocemento": "#a8adb0",
    "losa_impermeabilizada": "#8f99a3",
    "cubierta_vegetal": "#5d7d4b"}
COLOR_CUBIERTA_DEFECTO = "#8f99a3"
COLOR_MUEBLE: Dict[str, str] = {
    "descanso": "#b98a5e", "estar": "#8a7d66", "comedor": "#a5804e",
    "cocina": "#6f8b90", "sanitaria": "#cfd8dc", "trabajo": "#7f8c8d",
    "docencia": "#96705f", "atencion": "#8f7f9f", "almacenaje": "#6e5f4e"}
COLOR_MUEBLE_DEFECTO = "#8a7d66"
COLOR_RAMPA = "#7fb069"
COLOR_BARANDILLA = "#e07a5f"
COLOR_VIDRIO_DIENTE = "#a9c7e8"   # vidrio de los dientes de sierra
# Ascensores y fachada (v3.18.0): hueco y cabina, lamas por material y
# piel por tipo, con colores FIJOS para que el lienzo Tk y el PNG
# determinista coincidan siempre.
COLOR_ASCENSOR_HUECO = "#8b95a6"
COLOR_ASCENSOR_CABINA = "#5f6f80"
COLOR_PARASOL: Dict[str, str] = {
    "aluminio": "#b8c0c8", "madera": "#a97b50", "acero_corten": "#8a5a3b",
    "hormigon_grc": "#c3c8cc", "ceramica": "#c07d4a", "textil": "#e0d8c8"}
COLOR_PARASOL_DEFECTO = "#b8c0c8"
COLOR_PIEL: Dict[str, str] = {
    "doble_piel_vidrio": "#a9c7e8", "celosia_madera": "#a97b50",
    "malla_metalica": "#9aa5ad", "baguette_terracota": "#b96b4c",
    "panel_perforado": "#aab4bf", "jardin_vertical": "#5d7d4b",
    "grc": "#c3c8cc", "policarbonato": "#bcd9ea"}
COLOR_PIEL_DEFECTO = "#a9c7e8"
# Escaleras por tipología (v3.19.0): peldaños y mesetas, color FIJO
# para que el lienzo Tk y el PNG determinista coincidan siempre.
COLOR_ESCALERA = "#b9a184"
COLOR_ESCALERA_MESETA = "#8d7a63"

MARGEN_PNG = 70
TIRA_TITULO = 54


@dataclass
class Camara3D:
    """Cámara axonométrica ortográfica o EN PERSPECTIVA.

    ``azimuth_deg`` gira el modelo en planta; ``elevacion_deg`` inclina
    la vista (8° casi de frente, 80° casi en planta); ``zoom`` es un
    multiplicador sobre el encuadre automático. Con ``perspectiva``
    activo (v3.17.0) la proyección divide por la profundidad respecto
    a ``centro`` a la distancia ``distancia_m`` (0 = se calcula sola
    al encuadrar, con el FOV de fábrica), como una cámara real con
    punto de fuga.
    """

    azimuth_deg: float = 30.0
    elevacion_deg: float = 35.0
    zoom: float = 1.0
    perspectiva: bool = False
    distancia_m: float = 0.0
    centro: Optional[Tuple[float, float, float]] = None

    ELEV_MIN = 8.0
    ELEV_MAX = 80.0
    ZOOM_MIN = 0.2
    ZOOM_MAX = 8.0
    FOV_GRADOS = 50.0          # apertura del cono de visión en perspectiva
    PERSP_CERCA_FRACC = 0.12   # plano cercano: 12 % de la distancia

    def gira(self, delta_grados: float) -> "Camara3D":
        """Rota el azimut (se envuelve módulo 360°)."""
        self.azimuth_deg = (self.azimuth_deg + delta_grados) % 360.0
        return self

    def inclina(self, delta_grados: float) -> "Camara3D":
        """Sube/baja la elevación, sujeta entre ELEV_MIN y ELEV_MAX."""
        self.elevacion_deg = max(self.ELEV_MIN, min(
            self.ELEV_MAX, self.elevacion_deg + delta_grados))
        return self

    def acerca(self, factor: float) -> "Camara3D":
        """Multiplica el zoom, sujeto entre ZOOM_MIN y ZOOM_MAX."""
        self.zoom = max(self.ZOOM_MIN, min(
            self.ZOOM_MAX, self.zoom * factor))
        return self

    PASO_TECLA_GIRO = 10.0
    PASO_TECLA_ELEVACION = 5.0

    def tecla(self, keysym: str) -> bool:
        """NAVEGACION 3D CON TECLADO (v3.16.0), como un visor CAD:

        flechas izquierda/derecha giran el azimut, arriba/abajo
        inclinan, +/- acerca y aleja, Home vuelve al encuadre de
        fabrica, P conmuta AXONOMETRICA/PERSPECTIVA (v3.17.0).
        Devuelve True si la tecla era suya.
        """
        t = str(keysym).lower()
        if t == "left":
            self.gira(-self.PASO_TECLA_GIRO)
        elif t == "right":
            self.gira(self.PASO_TECLA_GIRO)
        elif t == "up":
            self.inclina(self.PASO_TECLA_ELEVACION)
        elif t == "down":
            self.inclina(-self.PASO_TECLA_ELEVACION)
        elif t in ("plus", "equal", "kp_add"):
            self.acerca(1.25)
        elif t in ("minus", "kp_subtract"):
            self.acerca(0.8)
        elif t == "home":
            self.azimuth_deg = 30.0
            self.elevacion_deg = 35.0
            self.zoom = 1.0
            self.distancia_m = 0.0   # la perspectiva se re-encuadra sola
        elif t == "p":
            self.perspectiva = not self.perspectiva
            self.distancia_m = 0.0   # recalcular distancia y centro
        else:
            return False
        return True


@dataclass
class Nivel3D:
    """Nivel plano listo para extruir: cota base y altura de piso."""

    level_id: str
    name: str
    base_z: float
    height_m: float
    index: int = 0


@dataclass
class Modelo3D:
    """Geometría del proyecto aplanada para la extrusión."""

    niveles: List[Nivel3D] = field(default_factory=list)
    muros: List[Any] = field(default_factory=list)
    locales: List[Any] = field(default_factory=list)
    vanos: List[Any] = field(default_factory=list)
    muro_por_id: Dict[str, Any] = field(default_factory=dict)
    nivel_por_id: Dict[str, Nivel3D] = field(default_factory=dict)
    # Concepción de espacios (v3.15.0)
    muebles: List[Any] = field(default_factory=list)
    cubiertas: List[Any] = field(default_factory=list)
    rampas: List[Any] = field(default_factory=list)
    barandillas: List[Any] = field(default_factory=list)
    # Ascensores y fachada (v3.18.0)
    ascensores: List[Any] = field(default_factory=list)
    parasoles: List[Any] = field(default_factory=list)
    pieles: List[Any] = field(default_factory=list)
    # Escaleras por tipología (v3.19.0)
    escaleras: List[Any] = field(default_factory=list)


@dataclass
class Cara3D:
    """Polígono 3D con color, orden de emisión y profundidad media.

    El «orden del pintor» dibuja primero las caras con MENOR
    profundidad (lejos) y al final las cercanas; a igual profundidad
    manda el orden de emisión (los vanos salen después que su muro).
    """

    puntos: List[Punto3]
    color: str
    kind: str = ""
    profundidad: float = 0.0
    orden: int = 0


# -- color -------------------------------------------------------------------
def _hex_a_rgb(color_hex: str) -> Tuple[int, int, int]:
    texto = (color_hex or "#000000").lstrip("#")
    if len(texto) != 6:
        return (0, 0, 0)
    try:
        return (int(texto[0:2], 16), int(texto[2:4], 16),
                int(texto[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _rgb_a_hex(rgb: Sequence[int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c)))
                                   for c in rgb)


def sombrea(color_hex: str, factor: float) -> str:
    """Aclara (factor > 1) u oscurece (factor < 1) un color hex."""
    r, g, b = _hex_a_rgb(color_hex)
    return _rgb_a_hex((r * factor, g * factor, b * factor))


# -- proyección --------------------------------------------------------------
def proyecta(punto: Punto3, camara: "Camara3D") -> Tuple[float, float]:
    """Mundo (x, y, z) → pantalla ``(sx, sy_arriba)``.

    Modo AXONOMÉTRICO (fábrica): primero rota el modelo en planta
    según el azimut; después inclina según la elevación. Modo
    PERSPECTIVA (v3.17.0, ``camara.perspectiva`` con distancia ya
    calculada): el mismo giro/inclinación respecto al CENTRO del
    modelo y después la división por la profundidad — los puntos
    cercanos a la cámara crecen y los lejanos encogen hacia el punto
    de fuga; en el plano del centro la escala es exactamente 1, así
    el encuadre automático de siempre sigue funcionando. ``sy_arriba``
    crece hacia ARRIBA (quien pinte sobre Tk/PNG debe voltearlo, allí
    el eje y crece hacia abajo).
    """
    az = math.radians(camara.azimuth_deg)
    el = math.radians(camara.elevacion_deg)
    px, py, pz = punto
    if camara.perspectiva and camara.distancia_m > 0.0:
        c = camara.centro or (0.0, 0.0, 0.0)
        px, py, pz = px - c[0], py - c[1], pz - c[2]
    xr = px * math.cos(az) - py * math.sin(az)
    yr = px * math.sin(az) + py * math.cos(az)
    sx = xr
    sy = pz * math.cos(el) - yr * math.sin(el)
    if camara.perspectiva and camara.distancia_m > 0.0:
        cz = yr * math.cos(el) + pz * math.sin(el)
        cerca = max(camara.PERSP_CERCA_FRACC * camara.distancia_m, 0.25)
        d = max(camara.distancia_m - cz, cerca)
        escala = camara.distancia_m / d
        sx *= escala
        sy *= escala
    return (sx, sy)


def prepara_perspectiva(caras: Sequence["Cara3D"],
                        camara: "Camara3D") -> None:
    """Fija CENTRO y DISTANCIA de la cámara en perspectiva (v3.17.0).

    El centro es el del bbox 3D de la escena y la distancia la que el
    FOV de fábrica pide para que todo el modelo quepa dentro del cono
    de visión (radio / tan(fov/2), con un pequeño margen). Solo actúa
    si la perspectiva está activa y la distancia no está ya fijada.
    """
    if not camara.perspectiva:
        return
    puntos = [p for c in caras for p in c.puntos]
    if not puntos:
        return
    xs = [p[0] for p in puntos]
    ys = [p[1] for p in puntos]
    zs = [p[2] for p in puntos]
    if camara.centro is None:
        camara.centro = ((min(xs) + max(xs)) / 2.0,
                         (min(ys) + max(ys)) / 2.0,
                         (min(zs) + max(zs)) / 2.0)
    if camara.distancia_m <= 0.0:
        c = camara.centro
        radio = max(math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2])
                    for p in puntos)
        radio = max(radio, 0.5)
        camara.distancia_m = (radio
                              / math.tan(math.radians(
                                  Camara3D.FOV_GRADOS / 2.0)) * 1.08)


def _profundidad(punto: Punto3, camara: Camara3D) -> float:
    """Distancia hacia la cámara (MAYOR = más cerca del espectador)."""
    az = math.radians(camara.azimuth_deg)
    el = math.radians(camara.elevacion_deg)
    yr = punto[0] * math.sin(az) + punto[1] * math.cos(az)
    return yr * math.cos(el) + punto[2] * math.sin(el)


def _dir_camara(camara: Camara3D) -> Tuple[float, float, float]:
    """Vector unitario desde la escena HACIA la cámara (mundo)."""
    az = math.radians(camara.azimuth_deg)
    el = math.radians(camara.elevacion_deg)
    return (-math.cos(el) * math.sin(az),
            math.cos(el) * math.cos(az),
            math.sin(el))


def _dot3(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def encuadre(caras: Sequence[Cara3D],
             camara: Camara3D) -> Tuple[float, float, float, float]:
    """Bbox proyectada ``(minx, miny, maxx, maxy)`` en ejes de pantalla
    con y hacia arriba (útil para ajustar lienzo Tk o PNG). En
    perspectiva calcula antes el centro y la distancia de la cámara
    si aún no están (v3.17.0)."""
    prepara_perspectiva(caras, camara)
    xs: List[float] = []
    ys: List[float] = []
    for cara in caras:
        for punto in cara.puntos:
            sx, sy = proyecta(punto, camara)
            xs.append(sx)
            ys.append(sy)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


# -- modelo desde el proyecto -------------------------------------------------
def modelo3d_desde_proyecto(ctx: Any) -> Tuple[Modelo3D, List[str]]:
    """Lee niveles/muros/locales/vanos del proyecto y los ordena.

    Los niveles se apilan por ``elevation_m`` (desempate por nombre) y
    cada muro conserva su propia ``height_m``. Devuelve avisos amables
    cuando la geometría es escasa; nunca lanza por falta de datos.
    """
    avisos: List[str] = []
    modelo = Modelo3D()
    try:
        niveles = list(ctx.architecture.list("LEVEL", ctx.project.id))
    except Exception:  # noqa: BLE001 - proyecto sin arquitectura
        niveles = []
    niveles.sort(key=lambda lv: (getattr(lv, "elevation_m", 0.0),
                                 getattr(lv, "name", "")))
    if not niveles:
        avisos.append("El proyecto no tiene niveles todavía.")
    for indice, nivel in enumerate(niveles):
        n3 = Nivel3D(
            level_id=nivel.id, name=nivel.name,
            base_z=float(getattr(nivel, "elevation_m", 0.0) or 0.0),
            height_m=float(getattr(nivel, "height_m", 3.0) or 3.0),
            index=indice)
        modelo.niveles.append(n3)
        modelo.nivel_por_id[n3.level_id] = n3

    try:
        muros = list(ctx.architecture.list("WALL", ctx.project.id))
    except Exception:  # noqa: BLE001
        muros = []
    for muro in muros:
        n3 = modelo.nivel_por_id.get(getattr(muro, "level_id", ""))
        if n3 is None:
            continue
        if muro.length_m <= 0.0 or muro.thickness_m <= 0.0 \
                or muro.height_m <= 0.0:
            continue
        modelo.muros.append(muro)
        modelo.muro_por_id[muro.id] = muro
        if getattr(muro, "code", ""):
            modelo.muro_por_id.setdefault(muro.code, muro)
    try:
        locales = list(ctx.architecture.list("SPACE", ctx.project.id))
    except Exception:  # noqa: BLE001
        locales = []
    for espacio in locales:
        if espacio.level_id in modelo.nivel_por_id \
                and len(getattr(espacio, "boundary", []) or []) >= 3:
            modelo.locales.append(espacio)
    try:
        puertas = list(ctx.architecture.list("DOOR", ctx.project.id))
        ventanas = list(ctx.architecture.list("WINDOW", ctx.project.id))
        genericos = list(ctx.architecture.list("OPENING", ctx.project.id))
    except Exception:  # noqa: BLE001
        puertas, ventanas, genericos = [], [], []
    vistos = set()
    for vano in list(puertas) + list(ventanas):
        if vano.id not in vistos:
            vistos.add(vano.id)
            modelo.vanos.append(vano)
    for vano in genericos:
        if vano.id not in vistos:
            vistos.add(vano.id)
            modelo.vanos.append(vano)

    if not modelo.muros and not modelo.locales:
        avisos.append("No hay muros ni locales dibujados aún.")
    # Concepción de espacios (v3.15.0): muebles, cubierta, rampas y
    # barandillas entran al modelo si el proyecto ya los tiene.
    for tipo, destino in (("FURNITURE", modelo.muebles),
                          ("ROOF", modelo.cubiertas),
                          ("RAMP", modelo.rampas),
                          ("HANDRAIL", modelo.barandillas),
                          ("ELEVATOR", modelo.ascensores),
                          ("PARASOL", modelo.parasoles),
                          ("SKIN", modelo.pieles),
                          ("STAIR", modelo.escaleras)):
        try:
            destino.extend(ctx.architecture.list(tipo, ctx.project.id))
        except Exception:  # noqa: BLE001 - proyecto sin esas tablas
            pass
    return (modelo, avisos)


# -- extrusión ----------------------------------------------------------------
def caras_de_muro(muro: Any, base_z: float, z_extra: float,
                  camara: Camara3D,
                  color: str = MURO_BASE) -> List[Cara3D]:
    """Extruye un muro como caja: 2 caras largas, 2 testas y tapa.

    Las caras cuyo normal apunta LEJOS de la cámara se eliminan
    (back-face culling); las visibles se sombrean según su inclinación
    ante la luz (que viene de la cámara) y la tapa siempre sale más
    clara, como pide una luz cenital.
    """
    x1, y1 = float(muro.start[0]), float(muro.start[1])
    x2, y2 = float(muro.end[0]), float(muro.end[1])
    dx, dy = x2 - x1, y2 - y1
    largo = math.hypot(dx, dy)
    espesor = float(getattr(muro, "thickness_m", 0.2) or 0.2)
    altura = float(getattr(muro, "height_m", 3.0) or 3.0)
    if largo <= 0.0 or espesor <= 0.0 or altura <= 0.0:
        return []
    u = (dx / largo, dy / largo)
    n = (-u[1], u[0])
    half = espesor / 2.0
    z0 = base_z + z_extra + float(getattr(muro, "base_offset_m", 0.0) or 0.0)
    z1 = z0 + altura
    apoyos = [(x1 + n[0] * half, y1 + n[1] * half),
              (x2 + n[0] * half, y2 + n[1] * half),
              (x2 - n[0] * half, y2 - n[1] * half),
              (x1 - n[0] * half, y1 - n[1] * half)]
    abajo = [(px, py, z0) for (px, py) in apoyos]
    arriba = [(px, py, z1) for (px, py) in apoyos]
    luz = _dir_camara(camara)

    candidatos = [
        ((abajo[0], abajo[1], arriba[1], arriba[0]), (n[0], n[1], 0.0)),
        ((abajo[2], abajo[3], arriba[3], arriba[2]),
         (-n[0], -n[1], 0.0)),
        ((abajo[1], abajo[2], arriba[2], arriba[1]), (u[0], u[1], 0.0)),
        ((abajo[3], abajo[0], arriba[0], arriba[3]),
         (-u[0], -u[1], 0.0)),
    ]
    caras: List[Cara3D] = []
    for puntos, normal in candidatos:
        verso = _dot3(normal, luz)
        if verso <= 0.0:
            continue  # cara trasera: no se ve
        nl = math.hypot(*normal) or 1.0
        factor = 0.62 + 0.38 * (verso / nl)
        caras.append(Cara3D(
            puntos=list(puntos), color=sombrea(color, factor),
            kind="muro",
            profundidad=sum(_profundidad(p, camara)
                            for p in puntos) / len(puntos)))
    caras.append(Cara3D(
        puntos=list(arriba), color=sombrea(color, 1.10), kind="tapa",
        profundidad=sum(_profundidad(p, camara)
                        for p in arriba) / len(arriba)))
    return caras


def caras_de_local(espacio: Any, base_z: float, z_extra: float,
                   color: str, camara: Camara3D) -> List[Cara3D]:
    """Piso del local: su contorno levantado 2 cm sobre la plataforma
    (y a su «cota_piso_m» si el terreno irregular del asistente lo
    elevó, v2.3.0)."""
    cota = float((getattr(espacio, "metadata", {}) or {}).get(
        "cota_piso_m", 0.0) or 0.0)
    puntos = [(float(px), float(py),
               base_z + z_extra + 0.02 + max(0.0, cota))
              for (px, py) in (espacio.boundary or [])]
    if len(puntos) < 3:
        return []
    return [Cara3D(puntos=puntos, color=color, kind="piso",
                   profundidad=sum(_profundidad(p, camara)
                                   for p in puntos) / len(puntos))]


def caras_de_vano(vano: Any, muro: Any, base_z: float,
                  z_extra: float, camara: Camara3D) -> List[Cara3D]:
    """Vano (puerta/ventana) como marco pintado sobre la cara VISIBLE
    del muro que lo aloja, a su cota real: sill + altura."""
    x1, y1 = float(muro.start[0]), float(muro.start[1])
    x2, y2 = float(muro.end[0]), float(muro.end[1])
    dx, dy = x2 - x1, y2 - y1
    largo = math.hypot(dx, dy)
    if largo <= 0.0:
        return []
    u = (dx / largo, dy / largo)
    n = (-u[1], u[0])
    espesor = float(getattr(muro, "thickness_m", 0.2) or 0.2)
    half = espesor / 2.0 + 0.006
    ancho = min(float(getattr(vano, "width_m", 0.9) or 0.9), largo)
    offset = max(0.0, min(float(getattr(vano, "offset_m", 0.0) or 0.0),
                          largo - ancho))
    cx = x1 + u[0] * (offset + ancho / 2.0)
    cy = y1 + u[1] * (offset + ancho / 2.0)
    desplante = float(getattr(muro, "base_offset_m", 0.0) or 0.0)
    z0 = base_z + z_extra + desplante + float(
        getattr(vano, "sill_height_m", 0.0) or 0.0)
    tope_muro = base_z + z_extra + desplante + float(
        getattr(muro, "height_m", 3.0) or 3.0)
    altura = min(float(getattr(vano, "height_m", 2.1) or 2.1),
                 tope_muro - z0)
    if altura <= 0.0 or ancho <= 0.0:
        return []
    color = COLOR_VANO.get(getattr(vano, "kind", "OPENING"),
                           COLOR_VANO["OPENING"])
    luz = _dir_camara(camara)
    caras: List[Cara3D] = []
    for sigo in (1.0, -1.0):
        normal = (n[0] * sigo, n[1] * sigo, 0.0)
        if _dot3(normal, luz) <= 0.0:
            continue
        ex = n[0] * half * sigo
        ey = n[1] * half * sigo
        puntos = [(cx - u[0] * ancho / 2.0 + ex, cy - u[1] * ancho / 2.0 + ey, z0),
                  (cx + u[0] * ancho / 2.0 + ex, cy + u[1] * ancho / 2.0 + ey, z0),
                  (cx + u[0] * ancho / 2.0 + ex, cy + u[1] * ancho / 2.0 + ey, z0 + altura),
                  (cx - u[0] * ancho / 2.0 + ex, cy - u[1] * ancho / 2.0 + ey, z0 + altura)]
        caras.append(Cara3D(
            puntos=puntos, color=color, kind="vano",
            profundidad=sum(_profundidad(p, camara)
                            for p in puntos) / len(puntos)))
    return caras


def caras_de_plataforma(nivel: Nivel3D, bbox: Tuple[float, float,
                                                    float, float],
                        z_extra: float,
                        camara: Camara3D,
                        color: str = COLOR_PLATAFORMA) -> List[Cara3D]:
    """Losa de apoyo del nivel: caja fina bajo la planta (es la que se
    ve de canto al hacer «explosión» y cierra el edificio por abajo)."""
    minx, miny, maxx, maxy = bbox
    if maxx <= minx or maxy <= miny:
        return []
    z_top = nivel.base_z + z_extra
    z_bot = z_top - 0.15
    abajo = [(minx, miny, z_bot), (maxx, miny, z_bot),
             (maxx, maxy, z_bot), (minx, maxy, z_bot)]
    arriba = [(px, py, z_top) for (px, py, _) in abajo]
    luz = _dir_camara(camara)
    normales = (((0.0, -1.0, 0.0), (abajo[0], abajo[1], arriba[1], arriba[0])),
                ((1.0, 0.0, 0.0), (abajo[1], abajo[2], arriba[2], arriba[1])),
                ((0.0, 1.0, 0.0), (abajo[2], abajo[3], arriba[3], arriba[2])),
                ((-1.0, 0.0, 0.0), (abajo[3], abajo[0], arriba[0], arriba[3])))
    caras: List[Cara3D] = []
    for normal, puntos in normales:
        verso = _dot3(normal, luz)
        if verso <= 0.0:
            continue
        nl = math.hypot(*normal) or 1.0
        caras.append(Cara3D(
            puntos=list(puntos), color=sombrea(color, 0.62 + 0.38 * verso / nl),
            kind="plataforma",
            profundidad=sum(_profundidad(p, camara)
                            for p in puntos) / len(puntos)))
    caras.append(Cara3D(
        puntos=arriba, color=sombrea(color, 1.05), kind="plataforma",
        profundidad=sum(_profundidad(p, camara)
                        for p in arriba) / len(arriba)))
    return caras


# -- concepción de espacios (v3.15.0) -------------------------------------------
def _caja(piso: Sequence[Tuple[float, float]], z0: float, z1: float,
          color: str, camara: Camara3D, kind: str,
          tapa: bool = True) -> List[Cara3D]:
    """Extruye un polígono CERRADO de planta entre z0 y z1 con back-face
    culling (patrón de caras_de_muro, reutilizado por muebles, parapetos
    y pasamanos)."""
    luz = _dir_camara(camara)
    n = len(piso)
    if n < 3 or z1 <= z0:
        return []
    abajo = [(px, py, z0) for (px, py) in piso]
    arriba = [(px, py, z1) for (px, py) in piso]
    caras: List[Cara3D] = []
    for i in range(n):
        p1, p2 = abajo[i], abajo[(i + 1) % n]
        ex, ey = p2[0] - p1[0], p2[1] - p1[1]
        largo = math.hypot(ex, ey)
        if largo <= 1e-9:
            continue
        normal = (ey / largo, -ex / largo, 0.0)
        verso = _dot3(normal, luz)
        if verso <= 0.0:
            continue
        nl = math.hypot(*normal) or 1.0
        cara = [p1, p2, (p2[0], p2[1], z1), (p1[0], p1[1], z1)]
        caras.append(Cara3D(
            puntos=cara, color=sombrea(color, 0.62 + 0.38 * verso / nl),
            kind=kind,
            profundidad=sum(_profundidad(p, camara) for p in cara)
            / len(cara)))
    if tapa:
        caras.append(Cara3D(
            puntos=arriba, color=sombrea(color, 1.10), kind=kind,
            profundidad=sum(_profundidad(p, camara) for p in arriba)
            / len(arriba)))
    return caras


def caras_de_mueble(mueble: Any, base_z: float, z_extra: float,
                    camara: Camara3D) -> List[Cara3D]:
    """Pieza de mobiliario como caja en su posición y giro (v3.15.0)."""
    ancho = float(getattr(mueble, "width_m", 1.0) or 1.0)
    fondo = float(getattr(mueble, "depth_m", 0.5) or 0.5)
    alto = float(getattr(mueble, "height_m", 0.75) or 0.75)
    if ancho <= 0 or fondo <= 0 or alto <= 0:
        return []
    cx, cy = float(mueble.x), float(mueble.y)
    rot = math.radians(float(getattr(mueble, "rotation_deg", 0.0) or 0.0))
    cos_a, sen_a = math.cos(rot), math.sin(rot)
    hw, hf = ancho / 2.0, fondo / 2.0
    esquinas = [(-hw, -hf), (hw, -hf), (hw, hf), (-hw, hf)]
    piso = [(cx + ex * cos_a - ey * sen_a, cy + ex * sen_a + ey * cos_a)
            for ex, ey in esquinas]
    meta = getattr(mueble, "metadata", {}) or {}
    color = COLOR_MUEBLE.get(str(meta.get("categoria", "")),
                             COLOR_MUEBLE_DEFECTO)
    z0 = base_z + z_extra + 0.02
    return _caja(piso, z0, z0 + alto, color, camara, "mueble")


def _puntos_lado(huella: Sequence[Tuple[float, float]], cx: float,
                 vertical: bool, lado: int
                 ) -> List[Tuple[float, float]]:
    """Puntos del hull a UN lado del eje de cumbrera, ordenados a lo
    largo de él (para cerrar el faldón sin cruces)."""
    tol = 1e-6
    if vertical:
        puntos = [p for p in huella if (p[0] - cx) * lado > tol]
        return sorted(puntos, key=lambda p: p[1])
    puntos = [p for p in huella if (p[1] - cx) * lado > tol]
    return sorted(puntos, key=lambda p: p[0])


def caras_de_cubierta(cubierta: Any, nivel: Nivel3D, z_extra: float,
                      camara: Camara3D) -> List[Cara3D]:
    """Cubierta REAL sobre el último nivel (v3.15.0): faldones con la
    pendiente guardada, cumbrera, frontones en color muro y parapeto en
    las planas. La geometría es la de la entidad (huella + cumbrera).
    Desde v3.17.0 la BASE se apoya en la cota de implantación: la
    metadata ``altura_base_m`` si el usuario la fijó, o el top de los
    muros del nivel cubierto (antes nacía en el piso y quedaba
    enterrada); ``z_extra`` (explosión) se suma siempre para que la
    cubierta acompañe a su nivel."""
    from domain.cubiertas import cota_base_cubierta
    huella = [(float(x), float(y))
              for x, y in (getattr(cubierta, "footprint", []) or [])]
    if len(huella) < 3:
        return []
    base_z = cota_base_cubierta(cubierta, nivel.base_z,
                                nivel.height_m) + z_extra
    pendiente = max(float(getattr(cubierta, "pendiente_pct", 0.0) or 0.0),
                    0.1) / 100.0
    color = COLOR_CUBIERTA.get(str(getattr(cubierta, "material", "")),
                               COLOR_CUBIERTA_DEFECTO)
    meta = getattr(cubierta, "metadata", {}) or {}
    if colores_mono(meta):
        color = COLOR_MONO_VANO
    color_vidrio = COLOR_MONO_VANO if color == COLOR_MONO_VANO \
        else COLOR_VIDRIO_DIENTE
    tipologia = str(getattr(cubierta, "tipologia", ""))
    caras: List[Cara3D] = []

    def _cara(puntos3: List[Punto3], col: str, kind: str) -> None:
        caras.append(Cara3D(
            puntos=puntos3, color=col, kind=kind,
            profundidad=sum(_profundidad(p, camara) for p in puntos3)
            / len(puntos3)))

    if tipologia.startswith("plana"):
        tapa = [(x, y, base_z + 0.12) for x, y in huella]
        _cara(tapa, color, "cubierta")
        # parapeto perimetral de 0.30 m (PARAPET_M de representation.py)
        n = len(huella)
        for i in range(n):
            p1, p2 = huella[i], huella[(i + 1) % n]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            largo = math.hypot(dx, dy)
            if largo <= 1e-9:
                continue
            ux, uy = dx / largo, dy / largo
            espesor = 0.06
            piso = [(p1[0] - uy * espesor, p1[1] + ux * espesor),
                    (p2[0] - uy * espesor, p2[1] + ux * espesor),
                    (p2[0] + uy * espesor, p2[1] - ux * espesor),
                    (p1[0] + uy * espesor, p1[1] - ux * espesor)]
            caras.extend(_caja(piso, base_z, base_z + 0.30, MURO_BASE,
                               camara, "parapeto"))
        return caras

    if tipologia == "serrena":
        # dientes de sierra: n faldones a un agua con vidrio vertical
        # al fondo de cada diente (v3.16.0)
        from domain.cubiertas import parametros_serrena
        xs = [p[0] for p in huella]
        ys = [p[1] for p in huella]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        n, _fondo, altura_diente = parametros_serrena(
            huella, pendiente * 100.0)
        vertical_diente = (maxx - minx) >= (maxy - miny)
        for i in range(n):
            if vertical_diente:
                c0 = minx + i * (maxx - minx) / n
                c1 = minx + (i + 1) * (maxx - minx) / n
                faldon = [(c0, miny, base_z), (c0, maxy, base_z),
                          (c1, maxy, base_z + altura_diente),
                          (c1, miny, base_z + altura_diente)]
                vidrio = [(c1, miny, base_z), (c1, maxy, base_z),
                          (c1, maxy, base_z + altura_diente),
                          (c1, miny, base_z + altura_diente)]
            else:
                c0 = miny + i * (maxy - miny) / n
                c1 = miny + (i + 1) * (maxy - miny) / n
                faldon = [(minx, c0, base_z), (maxx, c0, base_z),
                          (maxx, c1, base_z + altura_diente),
                          (minx, c1, base_z + altura_diente)]
                vidrio = [(minx, c1, base_z), (maxx, c1, base_z),
                          (maxx, c1, base_z + altura_diente),
                          (minx, c1, base_z + altura_diente)]
            _cara(faldon, color, "cubierta")
            _cara(vidrio, color_vidrio, "vidrio")
        return caras

    ridge = getattr(cubierta, "ridge", None)
    if not ridge:
        return caras
    r1 = (float(ridge[0][0]), float(ridge[0][1]))
    r2 = (float(ridge[1][0]), float(ridge[1][1]))
    altura = float(getattr(cubierta, "altura_cumbrera_m", 0.0) or 0.0)
    vertical = abs(r2[1] - r1[1]) > abs(r2[0] - r1[0])
    eje_r1 = (r1[0], r1[1], base_z + altura)
    eje_r2 = (r2[0], r2[1], base_z + altura)

    if tipologia == "un_agua":
        # el borde ALTO es la cumbrera: faldón único hacia el lado opuesto
        lado = 1
        puntos_lado = _puntos_lado(huella, r1[0] if vertical else r1[1],
                                   vertical, lado)
        if len(puntos_lado) >= 2:
            bajo1 = (puntos_lado[0][0], puntos_lado[0][1], base_z)
            bajo2 = (puntos_lado[-1][0], puntos_lado[-1][1], base_z)
            _cara([eje_r1, eje_r2, bajo2, bajo1], color, "cubierta")
        return caras

    if tipologia == "mariposa":
        # las aguas CAEN al centro: el eje es el VALLE (bajo) y los
        # aleros son la parte alta (v3.16.0)
        eje_bajo1 = (r1[0], r1[1], base_z)
        eje_bajo2 = (r2[0], r2[1], base_z)
        for lado in (-1, 1):
            puntos = _puntos_lado(huella, r1[0] if vertical else r1[1],
                                  vertical, lado)
            if len(puntos) < 2:
                continue
            alto1 = (puntos[0][0], puntos[0][1], base_z + altura)
            alto2 = (puntos[-1][0], puntos[-1][1], base_z + altura)
            _cara([eje_bajo1, eje_bajo2, alto2, alto1], color, "cubierta")
        return caras

    if tipologia == "mansarda":
        # DOS pendientes por faldon con codo al 55 % del semivano
        # (v3.16.0); el faldon bajo lleva la pendiente guardada y el
        # alto la mitad, igual que la entidad.
        from domain.cubiertas import parametros_mansarda
        minx, miny, maxx, maxy = 0.0, 0.0, 0.0, 0.0
        xs = [p[0] for p in huella]
        ys = [p[1] for p in huella]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        semivano = min(maxx - minx, maxy - miny) / 2.0
        codo, h1, _total = parametros_mansarda(semivano, pendiente * 100.0)
        perp = (1.0, 0.0) if vertical else (0.0, 1.0)
        for lado in (-1, 1):
            puntos = _puntos_lado(huella, r1[0] if vertical else r1[1],
                                  vertical, lado)
            if len(puntos) < 2:
                continue
            bajo1 = (puntos[0][0], puntos[0][1], base_z)
            bajo2 = (puntos[-1][0], puntos[-1][1], base_z)
            codo1 = (r1[0] + perp[0] * codo * lado,
                     r1[1] + perp[1] * codo * lado, base_z + h1)
            codo2 = (r2[0] + perp[0] * codo * lado,
                     r2[1] + perp[1] * codo * lado, base_z + h1)
            _cara([bajo1, bajo2, codo2, codo1], color, "cubierta")
            _cara([codo1, codo2, eje_r2, eje_r1], color, "cubierta")
        # frontones pentagonales: alero, codos y cima en cada extremo
        for extremo in (r1, r2):
            coord = extremo[1] if vertical else extremo[0]
            tol = 1e-6
            testas = sorted(
                [p for p in huella
                 if abs((p[1] if vertical else p[0]) - coord) < tol],
                key=lambda p: (p[0] if vertical else p[1]))
            if len(testas) < 2:
                continue
            bajo1 = (testas[0][0], testas[0][1], base_z)
            bajo2 = (testas[-1][0], testas[-1][1], base_z)
            perp_signo = 1.0 if (testas[-1][0] if vertical
                                 else testas[-1][1]) > coord else -1.0
            codo_alto = (extremo[0] + perp[0] * codo * perp_signo,
                         extremo[1] + perp[1] * codo * perp_signo)
            codo_bajo = (extremo[0] - perp[0] * codo * perp_signo,
                         extremo[1] - perp[1] * codo * perp_signo)
            cima = (extremo[0], extremo[1], base_z + altura)
            _cara([bajo1,
                   (codo_alto[0], codo_alto[1], base_z + h1),
                   cima,
                   (codo_bajo[0], codo_bajo[1], base_z + h1),
                   bajo2], MURO_BASE, "fronton")
        return caras

    # dos / cuatro aguas: faldones a ambos lados del eje
    for lado in (-1, 1):
        puntos = _puntos_lado(huella, r1[0] if vertical else r1[1],
                              vertical, lado)
        if len(puntos) < 2:
            continue
        if tipologia == "cuatro_aguas":
            # trapecio: extremos de cumbrera + esquinas del alero en ese
            # lado (las aguas laterales); los HIPS cierran los extremos
            bajo1 = (puntos[0][0], puntos[0][1], base_z)
            bajo2 = (puntos[-1][0], puntos[-1][1], base_z)
            _cara([eje_r1, eje_r2, bajo2, bajo1], color, "cubierta")
        else:
            bajo1 = (puntos[0][0], puntos[0][1], base_z)
            bajo2 = (puntos[-1][0], puntos[-1][1], base_z)
            _cara([eje_r1, eje_r2, bajo2, bajo1], color, "cubierta")
    # HIPS de cuatro aguas: triángulos en cada extremo de cumbrera
    if tipologia == "cuatro_aguas":
        for extremo in (r1, r2):
            for lado in (-1, 1):
                puntos = _puntos_lado(huella,
                                      extremo[1] if vertical else extremo[0],
                                      vertical, lado)
                if not puntos:
                    continue
                # el vértice del hip es el punto del lado más cercano al
                # extremo de la cumbrera
                cercano = min(puntos, key=lambda p: (
                    (p[1] if vertical else p[0]) - (
                        extremo[1] if vertical else extremo[0])) ** 2)
                opuestos = _puntos_lado(huella,
                                        extremo[1] if vertical
                                        else extremo[0], vertical, -lado)
                if not opuestos:
                    continue
                opuesto = min(opuestos, key=lambda p: (
                    (p[1] if vertical else p[0]) - (
                        extremo[1] if vertical else extremo[0])) ** 2)
                _cara([eje_r1 if extremo is r1 else eje_r2,
                       (cercano[0], cercano[1], base_z),
                       (opuesto[0], opuesto[1], base_z)], color, "cubierta")
    # FRONTONES (dos aguas): testas verticales bajo la cumbrera, en los
    # extremos del agua (solo cuando la cumbrera llega hasta el alero)
    if tipologia == "dos_aguas":
        for extremo in (r1, r2):
            coord = extremo[1] if vertical else extremo[0]
            tol = 1e-6
            testas = [p for p in huella
                      if abs((p[1] if vertical else p[0]) - coord) < tol]
            if len(testas) < 2:
                continue
            p1 = (testas[0][0], testas[0][1], base_z)
            p2 = (testas[1][0], testas[1][1], base_z)
            cima = (extremo[0], extremo[1], base_z + altura)
            _cara([p1, p2, cima], MURO_BASE, "fronton")
    return caras


def colores_mono(_meta: Dict[str, Any]) -> bool:
    """Gancho de modo monocromo (por ahora siempre color)."""
    return False


def caras_de_rampa(rampa: Any, base_z: float, z_extra: float,
                   camara: Camara3D) -> List[Cara3D]:
    """Rampa accesible como faja inclinada entre dos cotas (v3.15.0)."""
    corners = [tuple(p) for p in (getattr(rampa, "corners", []) or [])]
    if len(corners) < 4:
        return []
    desnivel = float(getattr(rampa, "desnivel_m", 0.15) or 0.15)
    z0 = base_z + z_extra + 0.02
    z1 = z0 + desnivel
    # corners: pie1, pie2, alto2, alto1 (o el par largo equivalente)
    puntos = [(corners[0][0], corners[0][1], z0),
              (corners[1][0], corners[1][1], z0),
              (corners[2][0], corners[2][1], z1),
              (corners[3][0], corners[3][1], z1)]
    if desnivel <= 1e-9:
        puntos = [(x, y, z0) for x, y, _z in puntos]
    return [Cara3D(puntos=puntos, color=COLOR_RAMPA, kind="rampa",
                   profundidad=sum(_profundidad(p, camara)
                                   for p in puntos) / len(puntos))]


def caras_de_barandilla(rail: Any, base_z: float, z_extra: float,
                        camara: Camara3D) -> List[Cara3D]:
    """Barandilla: pasamanos (y pasamanos bajo si lleva) + postes en los
    extremos y cada ~1.2 m (v3.15.0)."""
    puntos = [tuple(p) for p in (getattr(rail, "points", []) or [])]
    if len(puntos) < 2:
        return []
    altura = float(getattr(rail, "altura_m", 0.9) or 0.9)
    secundaria = float(getattr(rail, "altura_secundaria_m", 0.0) or 0.0)
    z0 = base_z + z_extra
    caras: List[Cara3D] = []
    for (p1, p2) in zip(puntos, puntos[1:]):
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        largo = math.hypot(dx, dy)
        if largo <= 1e-9:
            continue
        ux, uy = dx / largo, dy / largo
        half = 0.025
        piso = [(p1[0] - uy * half, p1[1] + ux * half),
                (p2[0] - uy * half, p2[1] + ux * half),
                (p2[0] + uy * half, p2[1] - ux * half),
                (p1[0] + uy * half, p1[1] - ux * half)]
        for cota in ((altura,) if secundaria <= 1e-9 else (altura,
                                                           secundaria)):
            caras.extend(_caja(piso, z0 + cota - 0.02, z0 + cota + 0.02,
                               COLOR_BARANDILLA, camara, "pasamanos",
                               tapa=False))
        # postes: extremos + intermedios cada 1.2 m
        n_postes = max(2, int(largo / 1.2) + 1)
        for indice in range(n_postes):
            t = indice / (n_postes - 1)
            px = p1[0] + ux * largo * t
            py = p1[1] + uy * largo * t
            poste = [(px - 0.03, py - 0.03), (px + 0.03, py - 0.03),
                     (px + 0.03, py + 0.03), (px - 0.03, py + 0.03)]
            caras.extend(_caja(poste, z0, z0 + altura, COLOR_BARANDILLA,
                               camara, "poste", tapa=False))
    return caras


# -- ascensores y fachada (v3.18.0) ---------------------------------------------
def _rect_girado(cx: float, cy: float, ancho: float, fondo: float,
                 rot_deg: float) -> List[Tuple[float, float]]:
    """Esquinas de un rectángulo (ancho × fondo) girado alrededor de su
    centro (la rotación del catálogo siempre es 0/90/180/270)."""
    rot = math.radians(float(rot_deg or 0.0))
    cos_a, sen_a = math.cos(rot), math.sin(rot)
    ha, hf = ancho / 2.0, fondo / 2.0
    esquinas = [(-ha, -hf), (ha, -hf), (ha, hf), (-ha, hf)]
    return [(cx + ex * cos_a - ey * sen_a, cy + ex * sen_a + ey * cos_a)
            for ex, ey in esquinas]


def _dir_fachada(piel_parasol: Any) -> Tuple[Tuple[float, float],
                                              Tuple[float, float]]:
    """(eje a lo largo de la fachada, normal saliente) de una pieza con
    ``rotation_deg`` (0 = corre en X con el sur saliendo en -Y)."""
    rot = math.radians(float(getattr(piel_parasol, "rotation_deg", 0.0)
                             or 0.0))
    eje = (math.cos(rot), math.sin(rot))
    normal = (-math.sin(rot), -math.cos(rot))
    return (eje, normal)


def _elementos_espaciados(n: int, maximo: int = 80) -> List[int]:
    """Índices a dibujar si ``n`` rebasa el tope (se salta parejo para
    no saturar el lienzo ni el PNG)."""
    if n <= maximo:
        return list(range(n))
    paso = n / float(maximo)
    return sorted({min(n - 1, int(i * paso)) for i in range(maximo)})


def caras_de_ascensor(ascensor: Any, base_z: float, z_extra: float,
                      camara: Camara3D) -> List[Cara3D]:
    """Hueco de ascensor (v3.18.0): caja del HUECO de la altura servida,
    cabina dentro (en el piso de base) y puerta central en el lado que
    la metadata indica. La explosión acompaña a su nivel."""
    ancho = float(getattr(ascensor, "width_m", 1.8) or 1.8)
    fondo = float(getattr(ascensor, "depth_m", 2.05) or 2.05)
    if ancho <= 0 or fondo <= 0:
        return []
    meta = getattr(ascensor, "metadata", {}) or {}
    try:
        altura = float(meta.get("altura_total_m", 3.0) or 3.0)
    except (TypeError, ValueError):
        altura = 3.0
    altura = max(altura, 3.0)
    rot = float(getattr(ascensor, "rotation_deg", 0.0) or 0.0)
    piso_hueco = _rect_girado(float(ascensor.x), float(ascensor.y),
                              ancho, fondo, rot)
    z0 = base_z + z_extra
    caras = _caja(piso_hueco, z0, z0 + altura, COLOR_ASCENSOR_HUECO,
                  camara, "ascensor")
    cab_a = float(meta.get("cabina_ancho_m", ancho - 0.4) or ancho - 0.4)
    cab_f = float(meta.get("cabina_fondo_m", fondo - 0.4) or fondo - 0.4)
    if cab_a > 0 and cab_f > 0:
        piso_cabina = _rect_girado(float(ascensor.x), float(ascensor.y),
                                   max(0.1, cab_a - 0.1),
                                   max(0.1, cab_f - 0.1), rot)
        caras.extend(_caja(piso_cabina, z0 + 0.02, z0 + 2.10,
                           COLOR_ASCENSOR_CABINA, camara, "cabina"))
    # puerta central: quad en la cara del hueco que mira a la calle
    lado = str(meta.get("puerta_lado", "")).upper()
    if not lado:
        giros = {0.0: "N", 90.0: "E", 180.0: "S", 270.0: "O"}
        lado = giros.get(round(rot) % 360, "N")
    puerta = float(getattr(ascensor, "puerta_m", 0.8) or 0.8)
    eje = {"N": (0.0, 1.0), "S": (0.0, -1.0),
           "E": (1.0, 0.0), "O": (-1.0, 0.0)}.get(lado, (0.0, 1.0))
    # el eje de la fachada corre perpendicular a la puerta
    perp = (-eje[1], eje[0])
    centro = (float(ascensor.x) + eje[0] * fondo / 2.0,
              float(ascensor.y) + eje[1] * fondo / 2.0, z0 + 1.05)
    half = min(puerta, ancho) / 2.0 + 0.006
    puntos = [(centro[0] - perp[0] * half,
               centro[1] - perp[1] * half, centro[2] - 1.05),
              (centro[0] + perp[0] * half,
               centro[1] + perp[1] * half, centro[2] - 1.05),
              (centro[0] + perp[0] * half,
               centro[1] + perp[1] * half, centro[2] + 1.05),
              (centro[0] - perp[0] * half,
               centro[1] - perp[1] * half, centro[2] + 1.05)]
    caras.append(Cara3D(
        puntos=puntos, color=COLOR_VANO["DOOR"], kind="vano",
        profundidad=sum(_profundidad(p, camara) for p in puntos)
        / len(puntos)))
    return caras


def caras_de_parasol(parasol: Any, base_z: float, z_extra: float,
                     camara: Camara3D) -> List[Cara3D]:
    """Parasol (v3.18.0): lámas HORIZONTALES apiladas en alto, ALETAS
    VERTICALES repartidas a lo largo de la fachada o la CRUZ completa
    (mixto); las orientables salen inclinadas a su ángulo guardado."""
    largo = float(getattr(parasol, "length_m", 1.0) or 1.0)
    vuelo = float(getattr(parasol, "profundidad_m", 0.5) or 0.5)
    tipo = str(getattr(parasol, "tipo", "horizontal") or "horizontal")
    meta = getattr(parasol, "metadata", {}) or {}
    n_h = int(meta.get("n_lamas_horizontales", 0) or 0)
    n_v = int(meta.get("n_lamas_verticales", 0) or 0)
    if n_h <= 0 and n_v <= 0:
        # entidades antiguas o a mano: derivar del tipo y la banda
        inicio = float(getattr(parasol, "altura_inicio_m", 0.0) or 0.0)
        fin = float(getattr(parasol, "altura_fin_m", 3.0) or 3.0)
        sep = float(getattr(parasol, "separacion_m", 0.6) or 0.6)
        if tipo in ("horizontal", "lamas_moviles", "mixto"):
            n_h = max(1, int(math.ceil((max(fin - inicio, 0.2) - 0.05)
                                       / max(sep, 0.15))))
        if tipo in ("vertical", "mixto"):
            n_v = max(1, int(largo / max(sep, 0.15)))
    material = str(getattr(parasol, "material", "") or "")
    color = COLOR_PARASOL.get(material, COLOR_PARASOL_DEFECTO)
    cx, cy = float(parasol.x), float(parasol.y)
    eje, normal = _dir_fachada(parasol)
    espesor = float(meta.get("espesor_lama_m", 0.04) or 0.04)
    ancho_lama = float(meta.get("ancho_lama_m", 0.18) or 0.18)
    angulo = math.radians(float(meta.get("angulo_deg", 0.0) or 0.0))
    inicio = float(getattr(parasol, "altura_inicio_m", 0.0) or 0.0)
    sep = float(getattr(parasol, "separacion_m", 0.6) or 0.6)
    z0 = base_z + z_extra
    caras: List[Cara3D] = []

    def _lama(rect: List[Tuple[float, float]], z_low: float,
              z_high: float) -> None:
        caras.extend(_caja(rect, z0 + z_low, z0 + z_high, color, camara,
                           "parasol"))

    # horizontales: cada lama corre a lo largo de la fachada y vuela
    # hacia fuera; la móvil se inclina (vuelo efectivo cos, alto sen).
    # En el sistema LOCAL de la pieza (rotación de la entidad) el eje X
    # es la propia fachada: largo en X y vuelo en Y, cualquier giro.
    if n_h > 0:
        vuelo_ef = vuelo * math.cos(angulo)
        alto_ef = ancho_lama + vuelo * math.sin(angulo)
        rot_ent = float(getattr(parasol, "rotation_deg", 0.0) or 0.0)
        for i in _elementos_espaciados(n_h):
            z_i = inicio + sep * i
            rect = _rect_girado(cx, cy, largo, max(vuelo_ef, 0.05),
                                rot_ent)
            _lama(rect, max(0.0, z_i - alto_ef / 2.0),
                  z_i + alto_ef / 2.0)
    # verticales: aletas perpendiculares a la fachada, repartidas
    if n_v > 0:
        alto_aleta = max(float(getattr(parasol, "altura_fin_m", 3.0)
                               or 3.0)
                         - inicio, 0.2)
        rot_ent = float(getattr(parasol, "rotation_deg", 0.0) or 0.0)
        for i in _elementos_espaciados(n_v):
            t = -largo / 2.0 + sep * (i + 0.5)
            ax = cx + eje[0] * t
            ay = cy + eje[1] * t
            rect = _rect_girado(ax, ay, espesor, vuelo, rot_ent)
            _lama(rect, inicio, inicio + alto_aleta)
    return caras


def caras_de_piel(piel: Any, base_z: float, z_extra: float,
                  camara: Camara3D) -> List[Cara3D]:
    """Piel exterior (v3.18.0): el PLANO de la piel paralelo a la
    fachada (cámara ventilada) con su retícula — montantes en la doble
    piel, listones densos en la celosía, baguettes verticales en la
    terracota y montantes largos en la malla."""
    largo = float(getattr(piel, "length_m", 1.0) or 1.0)
    alto = float(getattr(piel, "altura_m", 3.0) or 3.0)
    if largo <= 0 or alto <= 0:
        return []
    tipo = str(getattr(piel, "tipo", "") or "")
    color = COLOR_PIEL.get(tipo, COLOR_PIEL_DEFECTO)
    meta = getattr(piel, "metadata", {}) or {}
    if colores_mono(meta):
        color = COLOR_MONO_VANO
    cx, cy = float(piel.x), float(piel.y)
    eje, _normal = _dir_fachada(piel)
    rot = float(getattr(piel, "rotation_deg", 0.0) or 0.0)
    z0 = base_z + z_extra + float(meta.get("cota_base_m", 0.0) or 0.0)
    caras: List[Cara3D] = []
    # plano completo de la piel (quad vertical)
    half_a = largo / 2.0
    u = eje
    plano = [(cx - u[0] * half_a, cy - u[1] * half_a, z0),
             (cx + u[0] * half_a, cy + u[1] * half_a, z0),
             (cx + u[0] * half_a, cy + u[1] * half_a, z0 + alto),
             (cx - u[0] * half_a, cy - u[1] * half_a, z0 + alto)]
    caras.append(Cara3D(
        puntos=plano, color=color, kind="piel",
        profundidad=sum(_profundidad(p, camara) for p in plano)
        / len(plano)))
    color_pieza = sombrea(color, 0.82)

    def _pieza(t: float, ancho_pieza: float, z_low: float,
               z_high: float) -> None:
        px = cx + u[0] * t
        py = cy + u[1] * t
        rect = _rect_girado(px, py, ancho_pieza, 0.08, rot)
        caras.extend(_caja(rect, z0 + z_low, z0 + z_high, color_pieza,
                           camara, "piel_pieza", tapa=False))

    # retícula según el tipo de piel
    if tipo in ("doble_piel_vidrio", "panel_perforado", "grc",
                "policarbonato", "jardin_vertical"):
        paso = 1.5
        n_postes = max(2, int(largo / paso) + 1)
        for i in _elementos_espaciados(n_postes):
            t = -largo / 2.0 + largo * i / max(n_postes - 1, 1)
            _pieza(t, 0.08, 0.0, alto)
    elif tipo == "celosia_madera":
        paso = 0.20
        n_listones = max(2, int(alto / paso))
        for i in _elementos_espaciados(n_listones):
            z_low = alto * i / max(n_listones, 1)
            _pieza(0.0, largo, z_low, min(alto, z_low + 0.06))
    elif tipo == "baguette_terracota":
        paso = 0.30
        n_baguettes = max(2, int(largo / paso))
        for i in _elementos_espaciados(n_baguettes):
            t = -largo / 2.0 + paso * (i + 0.5)
            _pieza(t, 0.08, 0.0, alto)
    elif tipo == "malla_metalica":
        paso = 2.0
        n_postes = max(2, int(largo / paso) + 1)
        for i in _elementos_espaciados(n_postes):
            t = -largo / 2.0 + largo * i / max(n_postes - 1, 1)
            _pieza(t, 0.05, 0.0, alto)
        n_traves = max(2, int(alto / 1.0))
        for i in _elementos_espaciados(n_traves):
            z_low = alto * i / max(n_traves, 1)
            _pieza(0.0, largo, z_low, min(alto, z_low + 0.04))
    return caras


# -- ensamblaje ---------------------------------------------------------------
def _color_de_local(espacio: Any, modo: str) -> str:
    if modo == "mono":
        return COLOR_MONO_PISO
    tipo = (getattr(espacio, "space_type", "") or "ROOM").upper()
    return COLOR_TIPO.get(tipo, COLOR_LOCAL_DEFECTO)


def _bbox_nivel(modelo: Modelo3D, nivel: Nivel3D) -> Optional[
        Tuple[float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    for muro in modelo.muros:
        if modelo.nivel_por_id.get(muro.level_id) is nivel:
            for punto in (muro.start, muro.end):
                xs.append(float(punto[0]))
                ys.append(float(punto[1]))
    for espacio in modelo.locales:
        if espacio.level_id == nivel.level_id:
            for punto in espacio.boundary:
                xs.append(float(punto[0]))
                ys.append(float(punto[1]))
    if not xs:
        return None
    margen = 0.5
    return (min(xs) - margen, min(ys) - margen,
            max(xs) + margen, max(ys) + margen)


def construir_caras(modelo: Modelo3D,
                    camara: Camara3D,
                    colores: str = "tipo",
                    explotar_m: float = 0.0,
                    nivel_id: str = "",
                    mostrar_vanos: bool = True,
                    mostrar_plataformas: bool = True,
                    solar: Any = None,
                    terreno: Any = None,
                    mostrar_muebles: bool = True,
                    mostrar_cubierta: bool = True,
                    mostrar_accesibilidad: bool = True,
                    mostrar_fachada: bool = True) -> List[Cara3D]:
    """Extruye TODO el modelo y devuelve las caras listas para pintar,
    ordenadas por el «orden del pintor» (lejos → cerca).

    ``colores``: «tipo» pinta los pisos según el uso del local;
    «mono» usa una gama única. ``explotar_m`` separa cada nivel
    verticalmente (índice × metros) para verlos uno a uno. Con
    ``nivel_id`` se aísla un solo nivel. Con ``terreno`` (v3.13.0,
    ``ui.terreno3d.TerrenoOpts``) se pinta el solar debajo; con
    ``solar`` (v3.13.0, ``ui.solar.SolarOpts``) salen las sombras, la
    brújula y la trayectoria del sol — ambas se emiten ANTES que el
    edificio para que el orden del pintor las deje al fondo. Con los
    interruptores de v3.15.0 se apagan muebles, cubierta y elementos
    de accesibilidad por separado.
    """
    caras: List[Cara3D] = []
    contador = {"orden": 0}

    def _emite(cara: Cara3D) -> None:
        cara.orden = contador["orden"]
        contador["orden"] += 1
        caras.append(cara)

    # -- solar y terreno (v3.13.0): primero el suelo, luego el sol -----
    if terreno is not None or solar is not None:
        from ui import solar as _solar_mod
        recto_total = _solar_mod._bbox_total(modelo)
        z_suelo = None
        if recto_total is not None:
            if terreno is not None:
                from ui import terreno3d as _terreno_mod
                for cara in _terreno_mod.caras_de_terreno(
                        recto_total, terreno, camara):
                    _emite(cara)

                def z_suelo(px: float, py: float) -> float:
                    return _terreno_mod.altura_en(px, py, terreno,
                                                  recto_total)
            if solar is not None:
                for cara in _solar_mod.caras_de_sombras(
                        modelo, solar, camara,
                        z_suelo if terreno is not None else None):
                    _emite(cara)
                for cara in _solar_mod.caras_de_sol(modelo, solar,
                                                    camara):
                    _emite(cara)

    visibles = [n for n in modelo.niveles
                if not nivel_id or n.level_id == nivel_id]
    for nivel in visibles:
        z_extra = max(0.0, explotar_m) * nivel.index
        color_muro = COLOR_MONO_MURO if colores == "mono" else MURO_BASE
        color_plata = (COLOR_MONO_PLATAFORMA if colores == "mono"
                       else COLOR_PLATAFORMA)
        tope_plataforma: Optional[float] = None
        if mostrar_plataformas:
            bbox = _bbox_nivel(modelo, nivel)
            if bbox is not None:
                plataforma = caras_de_plataforma(
                    nivel, bbox, z_extra, camara, color_plata)
                for cara in plataforma:
                    _emite(cara)
                # la cara SUPERIOR de la plataforma es la última emitida
                if plataforma:
                    tope_plataforma = plataforma[-1].profundidad
        for espacio in modelo.locales:
            if espacio.level_id != nivel.level_id:
                continue
            for cara in caras_de_local(espacio, nivel.base_z, z_extra,
                                       _color_de_local(espacio, colores),
                                       camara):
                # el piso SIEMPRE se pinta sobre la plataforma de su
                # propio nivel, aunque su centroide quede más lejos
                # (polígono contenido en otro coplanario: después)
                if (tope_plataforma is not None
                        and cara.profundidad <= tope_plataforma):
                    cara.profundidad = tope_plataforma + 1e-4
                _emite(cara)
        muros_nivel = [m for m in modelo.muros
                       if modelo.nivel_por_id.get(m.level_id) is nivel]
        for muro in muros_nivel:
            for cara in caras_de_muro(muro, nivel.base_z, z_extra,
                                      camara, color_muro):
                _emite(cara)
        if mostrar_vanos:
            for vano in modelo.vanos:
                if modelo.nivel_por_id.get(
                        getattr(vano, "level_id", "")) is not nivel:
                    continue
                muro = modelo.muro_por_id.get(
                    getattr(vano, "wall_id", ""))
                if muro is None:
                    continue
                for cara in caras_de_vano(vano, muro, nivel.base_z,
                                          z_extra, camara):
                    _emite(cara)
        # MOBILIARIO (v3.15.0): cajas por pieza, dentro de su nivel.
        if mostrar_muebles:
            for mueble in modelo.muebles:
                if getattr(mueble, "level_id", "") != nivel.level_id:
                    continue
                for cara in caras_de_mueble(mueble, nivel.base_z,
                                            z_extra, camara):
                    _emite(cara)
        # ACCESIBILIDAD (v3.15.0): rampas y barandillas de su nivel.
        if mostrar_accesibilidad:
            for rampa in modelo.rampas:
                if getattr(rampa, "level_id", "") != nivel.level_id:
                    continue
                for cara in caras_de_rampa(rampa, nivel.base_z, z_extra,
                                           camara):
                    _emite(cara)
            for rail in modelo.barandillas:
                if getattr(rail, "level_id", "") != nivel.level_id:
                    continue
                for cara in caras_de_barandilla(rail, nivel.base_z,
                                                z_extra, camara):
                    _emite(cara)
        # CUBIERTA (v3.15.0): sobre SU nivel (el superior), tras muros.
        if mostrar_cubierta:
            for cubierta in modelo.cubiertas:
                if getattr(cubierta, "level_id", "") != nivel.level_id:
                    continue
                for cara in caras_de_cubierta(cubierta, nivel, z_extra,
                                              camara):
                    _emite(cara)
        # ASCENSOR (v3.18.0): el hueco sube de su nivel de base hasta
        # arriba (altura_total_m), como el resto del edificio.
        for ascensor in modelo.ascensores:
            if getattr(ascensor, "level_id", "") != nivel.level_id:
                continue
            for cara in caras_de_ascensor(ascensor, nivel.base_z,
                                          z_extra, camara):
                _emite(cara)
        # ESCALERA (v3.19.0): peldaños y mesetas desde su nivel de base.
        for escalera in modelo.escaleras:
            if getattr(escalera, "level_id", "") != nivel.level_id:
                continue
            for cara in caras_de_escalera(escalera, nivel.base_z,
                                          z_extra, camara):
                _emite(cara)
        # FACHADA (v3.18.0): parasoles y pieles de su nivel de base.
        if mostrar_fachada:
            for parasol in modelo.parasoles:
                if getattr(parasol, "level_id", "") != nivel.level_id:
                    continue
                for cara in caras_de_parasol(parasol, nivel.base_z,
                                             z_extra, camara):
                    _emite(cara)
            for piel in modelo.pieles:
                if getattr(piel, "level_id", "") != nivel.level_id:
                    continue
                for cara in caras_de_piel(piel, nivel.base_z,
                                          z_extra, camara):
                    _emite(cara)
    caras.sort(key=lambda c: (c.profundidad, c.orden))
    return caras


# -- escaleras por tipología (v3.19.0) -------------------------------------------
def caras_de_escalera(escalera: Any, base_z: float, z_extra: float,
                      camara: Camara3D) -> List[Cara3D]:
    """Peldaños y mesetas de la escalera (v3.19.0): la generación dejó
    las CAJAS 3D de cada peldaño (con sus cotas y su giro) en la
    metadata; aquí solo se extruyen ya colocadas, con la explosión
    acompañando a su nivel de base."""
    meta = getattr(escalera, "metadata", None) or {}
    pasos = meta.get("pasos") or []
    if not pasos:
        return []
    caras: List[Cara3D] = []
    for paso in pasos:
        try:
            cx, cy = float(paso["cx"]), float(paso["cy"])
            dx, dy = float(paso["dx"]), float(paso["dy"])
            rot = float(paso.get("rot", 0.0) or 0.0)
            z0, z1 = float(paso["z0"]), float(paso["z1"])
        except (KeyError, TypeError, ValueError):
            continue
        if dx <= 0 or dy <= 0:
            continue
        es_meseta = z1 <= z0 + 1e-9   # meseta: caja plana -> losa de 4 cm
        if es_meseta:
            z1 = z0 + 0.04
        if z1 <= z0:
            continue
        color = COLOR_ESCALERA_MESETA if es_meseta else COLOR_ESCALERA
        piso = _rect_girado(cx, cy, dx, dy, rot)
        caras.extend(_caja(piso, base_z + z_extra + z0,
                           base_z + z_extra + z1, color, camara,
                           "peldano"))
    return caras


# -- PNG determinista ----------------------------------------------------------
def export_vista3d_png(caras: Sequence[Cara3D],
                       camara: Camara3D,
                       ruta: str,
                       titulo: str = "",
                       ancho: int = 1600,
                       alto: int = 1000,
                       info_extra: str = "") -> Tuple[int, int]:
    """Rasteriza la vista 3D en un PNG determinista (100% stdlib).

    Misma lista de caras que el lienzo Tk, mismo encuadre; el título
    va en la tira inferior con la fuente bitmap del exportador (la
    des-accentuación es suya). ``info_extra`` añade datos al pie (sol,
    terreno…). Devuelve ``(ancho, alto)``.
    """
    lienzo = png.Canvas(int(ancho), int(alto), (250, 250, 250))
    tira = TIRA_TITULO if titulo else 30
    if caras:
        minx, miny, maxx, maxy = encuadre(caras, camara)
        base_w = max(maxx - minx, 1e-6)
        base_h = max(maxy - miny, 1e-6)
        k = min((ancho - 2 * MARGEN_PNG) / base_w,
                (alto - 2 * MARGEN_PNG - tira) / base_h)
        ox = ancho / 2.0 - (minx + maxx) / 2.0 * k
        oy = (alto - tira) / 2.0 + (miny + maxy) / 2.0 * k
        for cara in caras:
            pix = [(ox + sx * k, oy - sy * k)
                   for (sx, sy) in (proyecta(p, camara)
                                    for p in cara.puntos)]
            lienzo.polygon_fill(pix, _hex_a_rgb(cara.color))
            borde = _hex_a_rgb(sombrea(cara.color, 0.55))
            lienzo.polyline(pix + [pix[0]], borde, 1)
    info_base = "az %d / el %d%s" % (
        round(camara.azimuth_deg) % 360, round(camara.elevacion_deg),
        " / perspectiva" if camara.perspectiva and camara.distancia_m > 0.0
        else "")
    if info_extra:
        info_base += "  " + info_extra
    if titulo:
        y0 = alto - tira + 6
        lienzo.hline(MARGEN_PNG // 2, ancho - MARGEN_PNG // 2, y0,
                     (70, 80, 92))
        lienzo.text(MARGEN_PNG // 2, y0 + 12, titulo, scale=2,
                    color=(40, 48, 58))
        # el pie derecho se recorta para NUNCA pisar el título
        hueco = (ancho - MARGEN_PNG - (MARGEN_PNG // 2)
                 - png.Canvas.text_width(lienzo, titulo, 2) - 24)
        pie = info_base
        while pie and png.Canvas.text_width(lienzo, pie, 2) > hueco:
            pie = pie[:-2]
        if pie != info_base:
            pie = pie.rstrip() + "..."
        if pie:
            lienzo.text(ancho - MARGEN_PNG // 2 - png.Canvas.text_width(
                lienzo, pie, 2), y0 + 12, pie, scale=2,
                color=(90, 100, 112))
    else:
        lienzo.text(MARGEN_PNG // 2, alto - 24, info_base, scale=2,
                    color=(90, 100, 112))
    lienzo.save_png(ruta)
    return (int(ancho), int(alto))
