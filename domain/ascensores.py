"""ASCENSORES SEGÚN NEUFERT (v3.18.0).

«El arte de proyectar en arquitectura» dedica un capítulo completo a
los ascensores: la cabina mide por las PERSONAS que lleva (6 a 26),
el hueco la envuelve con holgura de guía, la puerta central se abre
al pasillo y el foso la recibe abajo. Este módulo lleva las TABLAS DE
REFERENCIA del libro (5.ª ed. en español) — pasajeros, hospital (con
camillas), montacargas y panorámico — y genera el HUECO real sobre la
planta del proyecto:

* ``CATALOGO``: capacidad (kg/personas), cabina (ancho × fondo),
  hueco (ancho × fondo) y puerta central para cada tipo.
* ``recomendar_cantidad``: la regla de pulgar del libro (1 ascensor
  por ocupación según el uso) y el aviso de accesibilidad desde 4
  plantas.
* ``generar_ascensor``: coloca el hueco DENTRO de un núcleo o
  escalera existente (con la puerta hacia el lado libre) o ADOSADO a
  la fachada que se pida; todo por los caminos oficiales (auditoría,
  undo persistente, QTO, invalidación incremental).
* Entidad ELEVATOR real: código ARQ-ELEVATOR-nnn y 3D del hueco con
  la cabina y la puerta.

Cero Tk y cero dependencias. Mensajes 100 % codificables en cp1252.
Los valores del libro ACONSEJAN, nunca bloquean: el proyectista
verifica siempre la norma local y el fabricante elegido.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain.diseno_base import (
    alta_entidad, baja_entidad, bbox_de, cerrar_qto, lista_tipos,
    metadata_origen,
)
from domain.model import Elevator

PT = Tuple[float, float]

# error propio: ARQ-ELE-001 catálogo sin hueco para esa capacidad
# error propio: ARQ-ELE-002 tipo desconocido

FUENTE = "Neufert — tablas de ascensores (5.ª ed. en español)"

TIPOS: Tuple[str, ...] = ("pasajeros", "hospital", "montacargas",
                          "panoramico")

ETIQUETA_TIPO: Dict[str, str] = {
    "pasajeros": "de pasajeros",
    "hospital": "de hospital (con camillas)",
    "montacargas": "montacargas",
    "panoramico": "panorámico",
}

# Tablas de referencia del libro: cada entrada es
#   (capacidad_kg, personas, cabina_a, cabina_f, hueco_a, hueco_f,
#    puerta_m)
# para puertas CENTRALES de tracción eléctrica. El hueco envuelve a la
# cabina con las guías y el juego del libro.
PASAJEROS: Tuple[Tuple[int, int, float, float, float, float, float], ...] = (
    (450, 6, 1.40, 1.05, 1.60, 1.70, 0.70),
    (630, 8, 1.60, 1.40, 1.80, 2.05, 0.80),
    (800, 10, 2.00, 1.40, 2.20, 2.05, 0.80),
    (1000, 13, 2.00, 1.60, 2.30, 2.20, 0.90),
    (1275, 17, 2.40, 2.00, 2.70, 2.60, 1.10),
    (1600, 21, 2.40, 2.30, 2.70, 2.90, 1.10),
    (2000, 26, 2.60, 2.40, 2.90, 3.00, 1.30),
)
HOSPITAL: Tuple[Tuple[int, int, float, float, float, float, float], ...] = (
    (1275, 17, 2.40, 2.40, 2.70, 3.00, 1.20),
    (2000, 26, 2.50, 2.85, 2.80, 3.45, 1.30),
)
MONTACARGAS: Tuple[Tuple[int, int, float, float, float, float, float], ...] = (
    (500, 0, 1.50, 1.50, 2.10, 1.90, 1.10),
    (1000, 0, 1.90, 1.90, 2.50, 2.30, 1.30),
)
PANORAMICO: Tuple[Tuple[int, int, float, float, float, float, float], ...] = (
    (1000, 13, 2.00, 1.90, 2.40, 2.40, 0.90),
)

CATALOGO: Dict[str, Tuple[Tuple[int, int, float, float, float, float,
                          float], ...]] = {
    "pasajeros": PASAJEROS,
    "hospital": HOSPITAL,
    "montacargas": MONTACARGAS,
    "panoramico": PANORAMICO,
}

# Ocupación servida por ascensor según el uso (regla de pulgar del
# libro: viviendas ~1 por 60-80 personas, oficinas ~1 por 150-200...).
PERSONAS_POR_ASCENSOR: Dict[str, int] = {
    "Vivienda": 75,
    "Hotel": 100,
    "Oficina": 175,
    "Hospital": 120,
    "Policlínico": 120,
    "Escuela primaria": 250,
    "Local comercial": 200,
}

FOSO_BASE_M = 1.40          # foso mínimo (velocidades <= 1.6 m/s)
FOSO_ALTO_M = 1.60          # foso para velocidades mayores
RECORRIDO_BASE_M = 3.60     # paso libre superior hasta 6 niveles
RECORRIDO_ALTO_M = 4.20     # paso libre superior con más niveles
SALA_MAQUINAS_M = 2.30      # altura de la sala de máquinas sobre el paso
ALTURA_PLANTA_REF = 3.0     # para estimar la velocidad por niveles


def capacidad_siguiente(tipo: str, personas: int) -> Tuple[int, int]:
    """Primera capacidad del catálogo que lleva ``personas``.

    Los montacargas no llevan personas: se elige por la carga pedida
    en kg (``personas`` se interpreta como kg en ese caso). Devuelve
    (capacidad_kg, personas_de_la_tabla).
    """
    tabla = CATALOGO.get(tipo)
    if not tabla:
        raise DomainError(
            message=f"Tipo de ascensor desconocido: {tipo}",
            code="ARQ-ELE-002",
            context={"tipo": tipo, "permitidos": list(TIPOS)},
            suggested_action="Usa uno de: " + ", ".join(TIPOS))
    if tipo == "montacargas":
        kg = max(int(personas), 1)
        for capacidad, _p, *_resto in tabla:
            if capacidad >= kg:
                return (capacidad, 0)
        ultima = tabla[-1]
        return (ultima[0], 0)
    quiero = max(int(personas), 1)
    for capacidad, p, *_resto in tabla:
        if p >= quiero:
            return (capacidad, p)
    ultima = tabla[-1]
    return (ultima[0], ultima[1])


def dimensiones_hueco(tipo: str, capacidad_kg: int) -> Dict[str, Any]:
    """Dimensiones del catálogo para un tipo y capacidad (Neufert).

    Devuelve ``cabina`` (ancho × fondo), ``hueco`` (ancho × fondo) y
    ``puerta`` central, más el foso y el recorrido superior según la
    velocidad que la altura de referencia pide.
    """
    tabla = CATALOGO.get(tipo)
    if not tabla:
        raise DomainError(
            message=f"Tipo de ascensor desconocido: {tipo}",
            code="ARQ-ELE-002",
            context={"tipo": tipo, "permitidos": list(TIPOS)},
            suggested_action="Usa uno de: " + ", ".join(TIPOS))
    for capacidad, personas, ca, cf, ha, hf, puerta in tabla:
        if capacidad == int(capacidad_kg):
            return {"capacidad_kg": capacidad, "personas": personas,
                    "cabina_ancho_m": ca, "cabina_fondo_m": cf,
                    "hueco_ancho_m": ha, "hueco_fondo_m": hf,
                    "puerta_m": puerta,
                    "capacidades": [c[0] for c in tabla]}
    raise DomainError(
        message=(f"No hay hueco de {capacidad_kg} kg en el catálogo de "
                 f"ascensores {ETIQUETA_TIPO.get(tipo, tipo)}"),
        code="ARQ-ELE-001",
        context={"tipo": tipo, "capacidad_kg": capacidad_kg,
                 "permitidas": [c[0] for c in tabla]},
        suggested_action="Usa una capacidad del catálogo: "
                         + ", ".join(str(c[0]) for c in tabla))


def velocidad_para(niveles: int, altura_m: float) -> float:
    """Velocidad de referencia (m/s) para el recorrido pedido.

    El libro escala la velocidad con la altura del recorrido: hasta
    ~4 plantas basta 0.63 m/s; el edificio medio pide 1.0 m/s y los
    torres 1.6-2.5 m/s.
    """
    recorrido = max(float(niveles), 1) * max(float(altura_m), 0.1)
    if recorrido <= 12.0:
        return 0.63
    if recorrido <= 24.0:
        return 1.0
    if recorrido <= 45.0:
        return 1.6
    return 2.5


def foso_y_paso(niveles: int, altura_m: float) -> Tuple[float, float]:
    """Foso (profundidad bajo el piso de parada) y paso libre superior
    según la velocidad del recorrido (Neufert)."""
    velocidad = velocidad_para(niveles, altura_m)
    foso = FOSO_BASE_M if velocidad <= 1.6 else FOSO_ALTO_M
    paso = RECORRIDO_BASE_M if niveles <= 6 else RECORRIDO_ALTO_M
    return (foso, paso)


def recomendar_cantidad(personas: int, plantas: int,
                        uso: str = "Vivienda") -> Dict[str, Any]:
    """Cuántos ascensores pide el programa (regla de pulgar del libro).

    Devuelve ``cantidad``, el ``factor`` de ocupación usado y una
    ``nota`` amable (accesibilidad: desde 4 plantas se espera al menos
    uno; por encima de 6 se recomienda doble).
    """
    factor = PERSONAS_POR_ASCENSOR.get(uso, 75)
    cantidad = max(0, math.ceil(max(int(personas), 0) / float(factor)))
    notas: List[str] = []
    if int(plantas) >= 4 and cantidad == 0:
        cantidad = 1
        notas.append("desde 4 plantas la accesibilidad pide al menos "
                     "un ascensor")
    elif int(plantas) >= 7 and cantidad == 1:
        cantidad = 2
        notas.append("con más de 6 niveles el libro recomienda un "
                     "segundo ascensor (espera y mantenimiento)")
    return {"cantidad": cantidad, "factor_personas": factor,
            "uso": uso, "notas": notas}


# ---------------------------------------------------------------------------
# colocación del hueco
# ---------------------------------------------------------------------------

def _lados_de_recinto(minx: float, miny: float, maxx: float,
                      maxy: float) -> Dict[str, PT]:
    """Centro de cada lado del recinto (AABB) con su rumbo."""
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    return {"N": (cx, maxy), "S": (cx, miny),
            "E": (maxx, cy), "O": (minx, cy)}


def _lado_libre(recinto: Tuple[float, float, float, float],
                espacios: List[Any], propios_id: str) -> str:
    """El lado del recinto (N/S/E/O) que mira al VECINO más cercano.

    En un núcleo, la puerta del ascensor debe abrirse hacia el pasillo
    o el local que lo sirve: se mide del centro del recinto al centro
    de cada otro local y manda el eje de la menor distancia.
    """
    minx, miny, maxx, maxy = recinto
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    mejor: Optional[Tuple[float, str]] = None
    for espacio in espacios:
        if str(getattr(espacio, "id", "")) == propios_id:
            continue
        boundary = getattr(espacio, "boundary", None) or []
        if len(boundary) < 3:
            continue
        bx, by, _a, _b = bbox_de(boundary)
        # centroide tosco del AABB del vecino
        _bx0, _by0, bx1, by1 = bbox_de(boundary)
        centro = ((bx + bx1) / 2.0, (by + by1) / 2.0)
        d = math.hypot(centro[0] - cx, centro[1] - cy)
        if mejor is None or d < mejor[0]:
            mejor = (d, centro)
    if mejor is None:
        return "N"
    dx, dy = mejor[1][0] - cx, mejor[1][1] - cy
    if abs(dx) >= abs(dy):
        return "E" if dx >= 0 else "O"
    return "N" if dy >= 0 else "S"


def _rectangulo_hueco(cx: float, cy: float, ancho: float, fondo: float,
                      puerta_lado: str) -> Tuple[float, float, float]:
    """Centro del hueco y ROTACIÓN en planta para que la puerta mire a
    ``puerta_lado``. El hueco nace con la puerta al Norte (fondo en Y);
    girar 0/90/180/270 reencamina el lado. Devuelve (x, y, rot_deg)."""
    # rotación que lleva la puerta (N por defecto) al lado pedido
    giros = {"N": 0.0, "E": 90.0, "S": 180.0, "O": 270.0}
    return (cx, cy, giros.get(puerta_lado, 0.0))


def _lado_contra(puerta_lado: str) -> str:
    """Lado opuesto a la puerta (hacia donde se adosa el hueco)."""
    return {"N": "S", "S": "N", "E": "O", "O": "E"}.get(puerta_lado, "N")


ETIQUETA_LADO: Dict[str, str] = {"N": "norte", "S": "sur", "E": "este",
                                 "O": "oeste"}


def sitio_para_hueco(ctx: Any, hueco_a: float, hueco_f: float,
                     nivel_id: str = "",
                     fachada: str = "") -> Dict[str, Any]:
    """Busca sitio para el hueco sobre la planta del nivel base.

    Orden del libro: 1) dentro de un NÚCLEO (CORE) o ESCALERA (STAIR)
    que acoja el hueco EN LA ORIENTACIÓN que su puerta pide (la puerta
    abre al vecino más cercano), 2) adosado a la FACHADA pedida (o a
    la Sur por defecto, mirando al edificio). Devuelve
    ``{"x", "y", "rot_deg", "puerta_lado", "modo", "space_id",
    "aviso"}``.
    """
    espacios = [e for e in lista_tipos(ctx, "SPACE")
                if len(getattr(e, "boundary", []) or []) >= 3]
    if nivel_id:
        espacios = [e for e in espacios if e.level_id == nivel_id]
    nucleos = [e for e in espacios
               if str(e.space_type or "").upper() in ("CORE", "STAIR")]
    giros = {"N": 0.0, "E": 90.0, "S": 180.0, "O": 270.0}
    # 1) núcleos y escaleras, del más grande al más chico
    for especial in sorted(nucleos,
                           key=lambda e: -e.area_m2()):
        minx, miny, maxx, maxy = bbox_de(especial.boundary)
        ancho_x, ancho_y = maxx - minx, maxy - miny
        lado = _lado_libre((minx, miny, maxx, maxy), espacios,
                           especial.id)
        # el giro que pide la puerta decide qué medida corre en cada eje
        if giros[lado] in (0.0, 180.0):
            necesita_a, necesita_f = hueco_a, hueco_f
        else:
            necesita_a, necesita_f = hueco_f, hueco_a
        if necesita_a <= ancho_x + 1e-9 and necesita_f <= ancho_y + 1e-9:
            cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
            x, y, rot = _rectangulo_hueco(cx, cy, hueco_a, hueco_f, lado)
            return {"x": round(x, 4), "y": round(y, 4), "rot_deg": rot,
                    "puerta_lado": lado, "modo": "nucleo",
                    "space_id": especial.id, "aviso": ""}
    # 2) fachada: adosado por fuera, puerta mirando al edificio
    puntos = [tuple(p) for e in espacios for p in e.boundary]
    if not puntos:
        return {"x": 0.0, "y": 0.0, "rot_deg": 0.0, "puerta_lado": "N",
                "modo": "libre", "space_id": "",
                "aviso": "sin locales en el nivel: hueco en el origen"}
    minx, miny, maxx, maxy = bbox_de(puntos)
    lado = (fachada or "S").upper()
    if lado not in ("N", "S", "E", "O"):
        lado = "S"
    contra = _lado_contra(lado)          # la puerta mira al edificio
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    if lado == "S":
        x, y = cx, miny - hueco_f / 2.0 - 0.05
    elif lado == "N":
        x, y = cx, maxy + hueco_f / 2.0 + 0.05
    elif lado == "E":
        x, y = maxx + hueco_f / 2.0 + 0.05, cy
    else:
        x, y = minx - hueco_f / 2.0 - 0.05, cy
    return {"x": round(x, 4), "y": round(y, 4),
            "rot_deg": giros[contra],
            "puerta_lado": contra, "modo": "fachada", "space_id": "",
            "aviso": "hueco adosado a la fachada "
                     f"{ETIQUETA_LADO.get(lado, lado)}"}


# ---------------------------------------------------------------------------
# generación en el proyecto
# ---------------------------------------------------------------------------

def niveles_servidos(ctx: Any) -> Tuple[int, float]:
    """(n_niveles_con_espacios, altura_media_de_nivel) del proyecto."""
    espacios = {e.level_id for e in lista_tipos(ctx, "SPACE")}
    niveles = [lv for lv in lista_tipos(ctx, "LEVEL")
               if not espacios or lv.id in espacios]
    if not niveles:
        niveles = lista_tipos(ctx, "LEVEL")
    if not niveles:
        return (1, ALTURA_PLANTA_REF)
    altura = sum(float(getattr(lv, "height_m", 3.0) or 3.0)
                 for lv in niveles) / len(niveles)
    return (len(niveles), altura)


def quitar_ascensores(ctx: Any) -> List[str]:
    """Da de baja los ascensores generados (lo manual se conserva)."""
    bajas: List[str] = []
    for ascensor in lista_tipos(ctx, "ELEVATOR"):
        codigo = ascensor.code
        baja_entidad(ctx, "ELEVATOR", ascensor.id)
        bajas.append(codigo)
    return bajas


def generar_ascensor(ctx: Any, data: Any = None,
                     tipo: str = "pasajeros",
                     capacidad_kg: Optional[int] = None,
                     personas: Optional[int] = None,
                     x: Optional[float] = None,
                     y: Optional[float] = None,
                     fachada: str = "",
                     con_qto: bool = True) -> Dict[str, Any]:
    """Levanta el hueco del ascensor sobre la planta (v3.18.0).

    ``tipo`` elige la tabla del libro (pasajeros/hospital/montacargas/
    panorámico); la capacidad sale de ``capacidad_kg`` o del número de
    ``personas`` (la más chica del catálogo que las lleva). El sitio:
    si se dan ``x``/``y`` se respeta; si no, primero un NÚCLEO o
    ESCALERA que acoja el hueco (puerta al lado del vecino más
    cercano) y después la FACHADA pedida (Sur por defecto, adosado por
    fuera). La metadata lleva cabina, foso, paso libre, velocidad y
    niveles servidos; QTO cuenta el ascensor, su área de hueco y el
    recorrido vertical.
    """
    resumen: Dict[str, Any] = {"operacion": "ascensor", "creados": [],
                               "eliminados": [], "avisos": [],
                               "qto": None}
    if tipo not in TIPOS:
        raise DomainError(
            message=f"Tipo de ascensor desconocido: {tipo}",
            code="ARQ-ELE-002",
            context={"tipo": tipo, "permitidos": list(TIPOS)},
            suggested_action="Usa uno de: " + ", ".join(TIPOS))
    # IDEMPOTENTE (patrón de cubiertas): el hueco generado se sustituye;
    # lo editado a mano (sin origen del motor) se conserva.
    resumen["eliminados"] = quitar_ascensores(ctx)
    niveles, altura_media = niveles_servidos(ctx)
    if personas is not None and capacidad_kg is None:
        capacidad_kg, personas_tabla = capacidad_siguiente(tipo, personas)
        personas = personas_tabla
    if capacidad_kg is None:
        capacidad_kg = CATALOGO[tipo][1][0]   # 630 kg: el de 8 personas
    dims = dimensiones_hueco(tipo, capacidad_kg)
    personas = int(personas if personas else dims["personas"])
    hueco_a, hueco_f = dims["hueco_ancho_m"], dims["hueco_fondo_m"]
    foso, paso = foso_y_paso(niveles, altura_media)
    velocidad = velocidad_para(niveles, altura_media)

    nivel_base: Optional[Any] = None
    candidatas = lista_tipos(ctx, "LEVEL")
    if candidatas:
        candidatas.sort(key=lambda lv: (
            float(getattr(lv, "elevation_m", 0.0) or 0.0),
            str(getattr(lv, "name", ""))))
        nivel_base = candidatas[0]
    if x is not None and y is not None:
        cx, cy, rot = float(x), float(y), 0.0
        lado = fachada.upper() if fachada else "N"
        lado = lado if lado in ("N", "S", "E", "O") else "N"
        sitio = {"x": round(cx, 4), "y": round(cy, 4), "rot_deg": rot,
                 "puerta_lado": lado, "modo": "manual", "space_id": "",
                 "aviso": ""}
    else:
        sitio = sitio_para_hueco(ctx, hueco_a, hueco_f,
                                 nivel_id=getattr(nivel_base, "id", ""),
                                 fachada=fachada)
    if sitio.get("aviso"):
        resumen["avisos"].append(sitio["aviso"])
    if sitio.get("modo") == "fachada":
        resumen["avisos"].append(
            "el hueco queda ADOSADO por fuera: dentro de un núcleo o "
            "escalera quedaría mejor; muévelo con x/y si lo prefieres")
    altura_total = niveles * altura_media
    extra_meta: Dict[str, Any] = {
        "cabina_ancho_m": dims["cabina_ancho_m"],
        "cabina_fondo_m": dims["cabina_fondo_m"],
        "puerta_lado": sitio["puerta_lado"],
        "modo": sitio["modo"],
        "foso_m": foso, "paso_libre_superior_m": paso,
        "velocidad_m_s": velocidad,
        "niveles_servidos": niveles,
        "altura_total_m": round(altura_total, 3),
        "fuente": FUENTE}
    if sitio.get("space_id"):
        extra_meta["space_id"] = sitio["space_id"]
    entidad = Elevator(
        project_id=ctx.project.id,
        code=ctx.next_code("ARCHITECTURE", "ELEVATOR"),
        level_id=getattr(nivel_base, "id", ""),
        tipo=tipo, capacidad_kg=int(dims["capacidad_kg"]),
        personas=int(personas),
        x=float(sitio["x"]), y=float(sitio["y"]),
        rotation_deg=float(sitio["rot_deg"]),
        width_m=hueco_a, depth_m=hueco_f,
        puerta_m=dims["puerta_m"],
        metadata=metadata_origen("ascensor del asistente", extra_meta))
    alta_entidad(ctx, entidad)
    resumen["creados"].append(entidad.code)
    resumen["parametros"] = {
        "tipo": tipo, "etiqueta": ETIQUETA_TIPO.get(tipo, tipo),
        "capacidad_kg": dims["capacidad_kg"], "personas": personas,
        "cabina": (dims["cabina_ancho_m"], dims["cabina_fondo_m"]),
        "hueco": (hueco_a, hueco_f), "puerta_m": dims["puerta_m"],
        "foso_m": foso, "paso_libre_superior_m": paso,
        "velocidad_m_s": velocidad, "niveles_servidos": niveles,
        "altura_total_m": round(altura_total, 3),
        "puerta_lado": sitio["puerta_lado"], "modo": sitio["modo"],
        "x": float(sitio["x"]), "y": float(sitio["y"]),
        "rot_deg": float(sitio["rot_deg"])}
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado (o el estado del ascensor)."""
    if resumen.get("parametros"):
        p = resumen["parametros"]
        texto = (f"Ascensor {p['etiqueta']} de {p['capacidad_kg']} kg "
                 f"({p['personas']} personas)"
                 f" · hueco {p['hueco'][0]:.2f} x {p['hueco'][1]:.2f} m"
                 f" · puerta {p['puerta_m']:.2f} m"
                 f" · {p['velocidad_m_s']:.2f} m/s")
        if p.get("modo") == "nucleo":
            texto += " · dentro del núcleo"
        elif p.get("modo") == "fachada":
            texto += (f" · adosado a la fachada "
                      f"{ETIQUETA_LADO.get(p.get('puerta_lado', ''), '')}")
    else:
        texto = "Ascensor"
    partes = [texto]
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} ELEVATOR creado")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


def tabla_texto(tipo: str = "pasajeros") -> List[str]:
    """La tabla del libro en líneas cp1252 (para la GUI y la CLI)."""
    lineas = [f"Ascensor {ETIQUETA_TIPO.get(tipo, tipo)} (Neufert, "
              "referencia):"]
    lineas.append("  kg   pers.  cabina        hueco         puerta")
    for capacidad, personas, ca, cf, ha, hf, puerta in CATALOGO[tipo]:
        cabina = f"{ca:.2f}x{cf:.2f}"
        hueco = f"{ha:.2f}x{hf:.2f}"
        lineas.append(f"  {capacidad:<4} {personas or '-':<6} "
                      f"{cabina:<13} {hueco:<13} {puerta:.2f}")
    return lineas


__all__ = [
    "FUENTE", "TIPOS", "ETIQUETA_TIPO", "CATALOGO", "PASAJEROS",
    "HOSPITAL", "MONTACARGAS", "PANORAMICO", "PERSONAS_POR_ASCENSOR",
    "FOSO_BASE_M", "FOSO_ALTO_M", "RECORRIDO_BASE_M", "RECORRIDO_ALTO_M",
    "SALA_MAQUINAS_M", "ALTURA_PLANTA_REF", "ETIQUETA_LADO",
    "capacidad_siguiente", "dimensiones_hueco", "velocidad_para",
    "foso_y_paso", "recomendar_cantidad", "sitio_para_hueco",
    "niveles_servidos", "quitar_ascensores", "generar_ascensor",
    "resumen_texto", "tabla_texto",
]
