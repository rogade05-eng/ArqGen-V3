"""HERRAMIENTAS DE DIBUJO (v3.33.0) — ui/dibujo_cad.py.

Dibujar como en ArchiCAD/AutoCAD: MUROS, ESPACIOS, ZONAS, PUERTAS y
VENTANAS nacen con dos clics (un clic sobre un muro para los vanos) y
cada entidad entra al proyecto POR LOS CAMINOS OFICIALES:
ArchitectureService (create_wall/create_space/create_zone/
set_space_zone/create_opening), con auditoria CREATE_ENTITY, eventos
OBJECT_CREATED/SPACE_CHANGED/GEOMETRY_CHANGED, invalidacion de QTO y
undo persistente. El que llama hace ctx.commit() al terminar y
ctx.rollback() si algo falla (mismo contrato que ui/cad_tools.py).

Como todo lo dibujado son entidades REALES, el impacto en el proyecto
es automatico: areas y longitudes para QTO/presupuesto, vanos para la
carpinteria, zonas para la organizacion y el control de validacion
dimensional (hospital_specs) juzga lo dibujado con las reglas del uso.

Las REGLAS DEL PROYECTO se consultan ANTES y DESPUES de crear (nunca
bloquean lo que el proyectista decide, siempre avisan):
- muro: espesor fino, altura mayor que la del nivel;
- espacio: area por debajo del minimo del uso (DNA), nombre duplicado;
- puerta: ancho por debajo del minimo del uso (DNA neufert.puerta_m);
- ventana: hueco por debajo del que pide el uso (habitables 1/6 de la
  superficie, humedos 1/25 — mismo criterio del editor de locales);
- zona: ningun espacio asignado.

Cero Tk: el mismo motor sirve a la paleta de la GUI, a la CLI y a las
pruebas. Los mensajes son 100 % codificables en cp1252 (disciplina
v3.13.1: sin flechas ni emojis en el texto que llega a la consola).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from services.architecture_service import ArchitectureService

PT = Tuple[float, float]

TOL = 1e-6
TOL_ARISTA = 1e-3        # un muro "toca" al local si coincide con su arista

# defaults de dibujo (la paleta los vuelve editables)
ESPESOR_MURO_DEF = 0.20
PUERTA_ANCHO_DEF = 0.90
PUERTA_ALTO_DEF = 2.10
VENTANA_ANCHO_DEF = 1.20
VENTANA_ALTO_DEF = 1.20
VENTANA_UMBRAL_DEF = 0.90
USO_ESPACIO_DEF = "ROOM"

REJILLA_DEF = 0.10       # paso de la rejilla de imantacion (m)
TOL_VERTICE_DEF = 0.35   # radio de iman sobre vertices existentes (m)

# HERRAMIENTAS_DIBUJO: (clave, glifo, etiqueta) — la seccion DIBUJAR de
# la paleta las recorre en este orden. Glifos geometricos verificados
# en DejaVu/Segoe UI Symbol.
HERRAMIENTAS_DIBUJO: Tuple[Tuple[str, str, str], ...] = (
    ("dib_muro", "▬", "Dibujar muro"),
    ("dib_espacio", "▭", "Dibujar espacio"),
    ("dib_zona", "◇", "Dibujar zona"),
    ("dib_puerta", "◠", "Dibujar puerta"),
    ("dib_ventana", "▤", "Dibujar ventana"),
)

# Tipos de zona válidos (domain/model.py, spec 17)
KINDS_ZONA: Tuple[str, ...] = ("PUBLIC", "PRIVATE", "SERVICE",
                               "TECHNICAL", "CIRCULATION", "EMERGENCY",
                               "EXTERIOR")
KIND_ZONA_DEF = "PUBLIC"

# Herramientas de un solo clic que exigen un MURO debajo del puntero.
ES_VANO_DIBUJO = ("dib_puerta", "dib_ventana")

# Clics que pide cada herramienta (los vanos ya llevan el muro).
PUNTOS_DIBUJO: Dict[str, int] = {
    "dib_muro": 2, "dib_espacio": 2, "dib_zona": 2,
    "dib_puerta": 1, "dib_ventana": 1,
}

# Pasos que la barra de estado va anunciando por herramienta.
PROMPTS_DIBUJO: Dict[str, Tuple[str, ...]] = {
    "dib_muro": ("Dibujo de MURO: clic en el punto inicial",
                 "Clic en el punto final del muro"),
    "dib_espacio": ("Dibujo de ESPACIO: clic en una esquina",
                    "Clic en la esquina opuesta (rectangulo)"),
    "dib_zona": ("Dibujo de ZONA: clic en una esquina del area",
                 "Clic en la esquina opuesta; los locales dentro "
                 "quedan asignados a la zona"),
    "dib_puerta": ("Dibujo de PUERTA: clic sobre el muro donde va "
                   "la puerta (queda centrada en el clic)"),
    "dib_ventana": ("Dibujo de VENTANA: clic sobre el muro donde va "
                    "la ventana (queda centrada en el clic)"),
}

# errores propios: ARQ-DIB-001..005


# ---------------------------------------------------------------------------
# resumen (compatible con cad.texto_resumen)
# ---------------------------------------------------------------------------

def _resumen(operacion: str) -> Dict[str, Any]:
    return {"operacion": operacion, "muros": [], "locales": [],
            "creados": [], "vanos": 0, "vanos_eliminados": [],
            "avisos": [], "datos": {}}


# ---------------------------------------------------------------------------
# geometria plana (m)
# ---------------------------------------------------------------------------

def _rectangulo(p1: PT, p2: PT) -> List[PT]:
    """Cuatro esquinas del rectangulo p1-p2 en sentido antihorario."""
    x1, y1 = p1
    x2, y2 = p2
    return [(min(x1, x2), min(y1, y2)), (max(x1, x2), min(y1, y2)),
            (max(x1, x2), max(y1, y2)), (min(x1, x2), max(y1, y2))]


def _area(poligono: Sequence[PT]) -> float:
    """Area (shoelace, absoluta) de un poligono."""
    total = 0.0
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _centroide(poligono: Sequence[PT]) -> PT:
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _punto_en_poligono(p: PT, poligono: Sequence[PT]) -> bool:
    """Ray casting con frontera inclusiva (tolerancia 1e-9)."""
    x, y = p
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9 \
                and min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9:
            return True
        if (y1 > y) != (y2 > y):
            x_cruce = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cruce:
                dentro = not dentro
    return dentro


def _proyeccion(p: PT, a: PT, b: PT) -> float:
    """Distancia de la proyeccion de p sobre el segmento a-b (0..len)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    if largo2 < TOL:
        return 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2
    return max(0.0, min(1.0, t)) * math.sqrt(largo2)


def _dist_segmento(p: PT, a: PT, b: PT) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    if largo2 < TOL:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy)
                     / largo2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


# ---------------------------------------------------------------------------
# DNA del uso (consultas de solo lectura, nunca lanzan)
# ---------------------------------------------------------------------------

def _dna(ctx: Any, uso: str) -> Any:
    registro = getattr(ctx, "dna_registry", None)
    if registro is None:
        return None
    try:
        return registro.get(str(uso or ""))
    except Exception:  # noqa: BLE001 — sin registro: sin reglas
        return None


def _float_dna(dna: Any, attr: str) -> Optional[float]:
    try:
        valor = float(getattr(dna, attr, 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    return valor or None


def _puerta_minima_dna(dna: Any) -> Optional[float]:
    try:
        neufert = dna.metadata.get("neufert") or {} \
            if isinstance(dna.metadata, dict) else {}
        valor = float(neufert.get("puerta_m") or 0.0)
    except (TypeError, ValueError, AttributeError):
        return None
    return valor or None


def _requiere_ventana(ctx: Any, uso: str, area_local: float) \
        -> Optional[float]:
    """Hueco de ventana que pide el uso: habitables 1/6 de la
    superficie, humedos 1/25; None si el uso no pide luz natural."""
    dna = _dna(ctx, uso)
    if dna is None:
        return None
    daylight = bool(getattr(dna, "daylight", False))
    humedo = bool(getattr(dna, "wet_zone", False))
    if not daylight:
        return None
    divisor = 25.0 if humedo else 6.0
    if area_local <= 0:
        return None
    return area_local / divisor


def _espacios_que_tocan(ctx: Any, muro: Any) -> List[Any]:
    """Locales del nivel con alguna arista EN el muro: el punto medio
    de la arista cae sobre el eje del muro (a menos de 1 mm, dentro de
    su alcance). Así una arista más corta que el muro también cuenta."""
    espacios: List[Any] = []
    a, b = tuple(muro.start), tuple(muro.end)
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    for s in ctx.architecture.list("SPACE", ctx.project.id):
        if getattr(s, "level_id", None) != getattr(muro, "level_id", None):
            continue
        boundary = [tuple(p) for p in (getattr(s, "boundary", []) or [])]
        if len(boundary) < 3:
            continue
        n = len(boundary)
        for i in range(n):
            e1, e2 = boundary[i], boundary[(i + 1) % n]
            mid = ((e1[0] + e2[0]) / 2.0, (e1[1] + e2[1]) / 2.0)
            if largo2 < TOL:
                continue
            t = ((mid[0] - a[0]) * dx + (mid[1] - a[1]) * dy) / largo2
            if t < -TOL_ARISTA or t > 1.0 + TOL_ARISTA:
                continue
            perp = abs((mid[0] - a[0]) * dy - (mid[1] - a[1]) * dx) \
                / math.sqrt(largo2)
            if perp <= TOL_ARISTA:
                espacios.append(s)
                break
    return espacios


def _nombre_unico(ctx: Any, level_id: str, nombre: str) -> str:
    usados = {s.name.lower()
              for s in ctx.architecture.list("SPACE", ctx.project.id)
              if getattr(s, "level_id", None) == level_id}
    if nombre.lower() not in usados:
        return nombre
    n = 2
    while f"{nombre} {n}".lower() in usados:
        n += 1
    return f"{nombre} {n}"


# ---------------------------------------------------------------------------
# imantacion headless (la GUI usa ademas _punto_ayudado / cursor_acad)
# ---------------------------------------------------------------------------

def snap_punto(ctx: Any, nivel_ref: str, punto: PT,
               rejilla: float = REJILLA_DEF,
               tol: float = TOL_VERTICE_DEF,
               base: Optional[PT] = None, orto: bool = False) \
        -> Tuple[PT, str]:
    """Imantacion AutoCAD headless: primero VERTICES de muros y
    locales del nivel (a menos de tol), despues la REJILLA y por
    ultimo ORTO (proyeccion al eje dominante desde base)."""
    arch = ArchitectureService(ctx)
    nivel_ids: List[str] = []
    try:
        if nivel_ref:
            nivel = arch.get_level_by_name_or_code(nivel_ref)
            nivel_ids = [nivel.id]
        else:
            nivel_ids = [lv.id for lv in
                         ctx.architecture.list("LEVEL", ctx.project.id)]
    except Exception:  # noqa: BLE001 — sin niveles: solo rejilla
        nivel_ids = []
    if tol > 0 and nivel_ids:
        mejor: Optional[PT] = None
        mejor_d = tol
        for muro in ctx.architecture.list("WALL", ctx.project.id):
            if muro.level_id not in nivel_ids:
                continue
            for v in (tuple(muro.start), tuple(muro.end)):
                d = math.hypot(punto[0] - v[0], punto[1] - v[1])
                if d <= mejor_d:
                    mejor, mejor_d = v, d
        for s in ctx.architecture.list("SPACE", ctx.project.id):
            if s.level_id not in nivel_ids:
                continue
            for v in (tuple(p) for p in
                      (getattr(s, "boundary", []) or [])):
                d = math.hypot(punto[0] - v[0], punto[1] - v[1])
                if d <= mejor_d:
                    mejor, mejor_d = v, d
        if mejor is not None:
            return (float(mejor[0]), float(mejor[1])), "vertice"
    if rejilla > 0:
        punto = (round(punto[0] / rejilla) * rejilla,
                 round(punto[1] / rejilla) * rejilla)
        # limpia el rastro binario del paso de rejilla (36 * 0.1)
        punto = (round(punto[0], 6), round(punto[1], 6))
    if orto and base is not None:
        dx, dy = abs(punto[0] - base[0]), abs(punto[1] - base[1])
        if dx >= dy:
            punto = (punto[0], base[1])
        else:
            punto = (base[0], punto[1])
    return (float(punto[0]), float(punto[1])), "rejilla"


# ---------------------------------------------------------------------------
# DIBUJAR: las cinco herramientas
# ---------------------------------------------------------------------------

def dibujar_muro(ctx: Any, nivel_ref: str, p1: PT, p2: PT,
                 espesor: float = ESPESOR_MURO_DEF,
                 altura: Optional[float] = None) -> Dict[str, Any]:
    """Muro por dos puntos; espesor y altura configurables (altura
    None = la del nivel). Avisa si el espesor es fino o el muro pasa
    de la altura del nivel."""
    resumen = _resumen("dibujar muro")
    espesor = float(espesor or 0.0)
    if espesor <= 0:
        raise DomainError(
            message="El espesor del muro debe ser positivo",
            code="ARQ-DIB-002",
            suggested_action="Indique un espesor mayor que cero "
                             "(0.20 m es lo corriente).")
    if espesor < 0.10:
        resumen["avisos"].append(
            f"espesor fino ({espesor:.2f} m): por debajo de lo "
            "corriente (0.10-0.20 m)")
    largo = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if largo < 0.20:
        resumen["avisos"].append(
            f"muro muy corto ({largo:.2f} m): compruebe que es lo "
            "que queria dibujar")
    arch = ArchitectureService(ctx)
    nivel = arch.get_level_by_name_or_code(nivel_ref)
    if altura is not None:
        altura_nivel = float(getattr(nivel, "height_m", 0.0) or 0.0)
        if altura_nivel > 0 and altura > altura_nivel + 1e-9:
            resumen["avisos"].append(
                f"altura del muro ({altura:.2f} m) mayor que la del "
                f"nivel ({altura_nivel:.2f} m)")
    muro = arch.create_wall(nivel_ref, tuple(p1), tuple(p2),
                            thickness_m=espesor, height_m=altura)
    resumen["muros"].append(muro.code)
    resumen["creados"].append(muro.code)
    resumen["datos"] = {"largo_m": round(largo, 3),
                        "espesor_m": espesor,
                        "altura_m": muro.height_m}
    return resumen


def dibujar_espacio(ctx: Any, nivel_ref: str, p1: PT, p2: PT,
                    nombre: str = "", uso: str = USO_ESPACIO_DEF) \
        -> Dict[str, Any]:
    """Espacio rectangular por dos esquinas; uso del DNA configurable.
    Avisa si el area queda por debajo del minimo del uso."""
    resumen = _resumen("dibujar espacio")
    esquinas = _rectangulo(tuple(p1), tuple(p2))
    area = _area(esquinas)
    if area <= TOL:
        raise DomainError(
            message="El espacio dibujado no tiene area",
            code="ARQ-DIB-004",
            suggested_action="Los dos clics no pueden coincidir; "
                             "separe las esquinas.")
    arch = ArchitectureService(ctx)
    nivel = arch.get_level_by_name_or_code(nivel_ref)
    if area < 0.5:
        resumen["avisos"].append(
            f"area muy pequeña ({area:.2f} m2): ¿era un espacio o "
            "queria dibujar un muro?")
    nombre = (nombre or "").strip()
    if not nombre:
        nombre = f"Local {len([s for s in ctx.architecture.list('SPACE', ctx.project.id) if s.level_id == nivel.id]) + 1}"
    nombre = _nombre_unico(ctx, nivel.id, nombre)
    dna = _dna(ctx, uso)
    minimo = _float_dna(dna, "minimum_area") if dna is not None else None
    if minimo and area + 1e-9 < minimo:
        resumen["avisos"].append(
            f"area {area:.2f} m2 por debajo del minimo del uso "
            f"{uso} ({minimo:.2f} m2)")
    espacio = arch.create_space(nivel_ref, nombre, uso,
                                [tuple(p) for p in esquinas])
    resumen["locales"].append(espacio.code)
    resumen["creados"].append(espacio.code)
    resumen["datos"] = {"nombre": nombre, "uso": uso,
                        "area_m2": round(area, 2),
                        "esquinas": esquinas}
    return resumen


def dibujar_zona(ctx: Any, nombre: str, p1: PT, p2: PT,
                 kind: str = KIND_ZONA_DEF, nivel_ref: str = "") \
        -> Dict[str, Any]:
    """Zona rectangular: nace la zona y los locales dibujados dentro
    del rectangulo quedan asignados a ella (como la zona de ArchiCAD)."""
    resumen = _resumen("dibujar zona")
    esquinas = _rectangulo(tuple(p1), tuple(p2))
    area = _area(esquinas)
    if area <= TOL:
        raise DomainError(
            message="La zona dibujada no tiene area",
            code="ARQ-DIB-005",
            suggested_action="Separe las dos esquinas del rectangulo.")
    arch = ArchitectureService(ctx)
    nombre = (nombre or "").strip() or "Zona dibujada"
    zona = arch.create_zone(nombre, kind if kind in KINDS_ZONA
                            else KIND_ZONA_DEF)
    asignados: List[str] = []
    try:
        nivel = arch.get_level_by_name_or_code(nivel_ref) \
            if nivel_ref else None
    except Exception:  # noqa: BLE001 — nivel inexistente: sin filtro
        nivel = None
    for s in ctx.architecture.list("SPACE", ctx.project.id):
        if nivel is not None and s.level_id != nivel.id:
            continue
        boundary = [tuple(p) for p in (s.boundary or [])]
        if len(boundary) < 3:
            continue
        if _punto_en_poligono(_centroide(boundary), esquinas):
            arch.set_space_zone(s.id, zona.id)
            asignados.append(s.code)
    resumen["creados"].append(zona.code)
    if not asignados:
        resumen["avisos"].append(
            "ningun local quedo dentro del area de la zona")
    resumen["datos"] = {"zona": zona.code, "nombre": nombre,
                        "area_m2": round(area, 2),
                        "asignados": asignados}
    return resumen


def dibujar_vano(ctx: Any, kind: str, muro_ref: str, punto: PT,
                 ancho: Optional[float] = None,
                 alto: Optional[float] = None,
                 sill: Optional[float] = None) -> Dict[str, Any]:
    """Puerta o ventana SOBRE un muro: queda centrada en el punto de
    clic (proyectado al eje del muro) y comprueba las reglas del uso
    de los locales que ese muro limita. kind: DOOR o WINDOW."""
    es_puerta = str(kind).upper() in ("DOOR", "PUERTA")
    resumen = _resumen("dibujar puerta" if es_puerta
                       else "dibujar ventana")
    tipo = "DOOR" if es_puerta else "WINDOW"
    arch = ArchitectureService(ctx)
    muro = arch._resolve_wall(muro_ref)
    largo = float(muro.length_m)
    if ancho is None:
        ancho = PUERTA_ANCHO_DEF if es_puerta else VENTANA_ANCHO_DEF
    if alto is None:
        alto = PUERTA_ALTO_DEF if es_puerta else VENTANA_ALTO_DEF
    if sill is None:
        sill = 0.0 if es_puerta else VENTANA_UMBRAL_DEF
    ancho, alto, sill = float(ancho), float(alto), float(sill)
    if ancho > largo + 1e-9:
        raise DomainError(
            message=f"El vano no cabe en el muro: ancho {ancho:.2f} m "
                    f"> longitud {largo:.2f} m",
            code="ARQ-DIB-001",
            suggested_action="Reduzca el ancho del vano o dibuje un "
                             "muro mas largo.")
    if ancho <= 0 or alto <= 0:
        raise DomainError(
            message="El ancho y el alto del vano deben ser positivos",
            code="ARQ-DIB-003")
    # centrado en el clic y sujeto al muro
    t = _proyeccion(tuple(punto), tuple(muro.start), tuple(muro.end))
    offset = max(0.0, min(t - ancho / 2.0, largo - ancho))
    # reglas del uso de los locales que el muro limita
    espacios = _espacios_que_tocan(ctx, muro)
    uso = ""
    if espacios:
        usos = {str(getattr(s, "space_type", "") or "ROOM")
                for s in espacios}
        uso = sorted(usos)[0]
        dna = _dna(ctx, uso)
        if es_puerta:
            minimo = _puerta_minima_dna(dna) if dna is not None else None
            if minimo and ancho + 1e-9 < minimo:
                resumen["avisos"].append(
                    f"puerta de {ancho:.2f} m por debajo del minimo "
                    f"del uso {uso} ({minimo:.2f} m)")
        else:
            area_local = max(
                (_area([tuple(p) for p in
                        (getattr(s, "boundary", []) or [])])
                 for s in espacios), default=0.0)
            requerido = _requiere_ventana(ctx, uso, area_local)
            if requerido and ancho * alto + 1e-9 < requerido:
                resumen["avisos"].append(
                    f"ventana aporta {ancho * alto:.2f} m2 y el uso "
                    f"{uso} pide {requerido:.2f} m2 de hueco "
                    "(1/6 habitable, 1/25 humedo)")
    else:
        resumen["datos"]["nota"] = ("el muro no limita ningun local: "
                                    "vano libre de reglas de uso")
    vano = arch.create_opening(kind=tipo, wall_ref=muro.id,
                               width_m=ancho, height_m=alto,
                               offset_m=offset, sill_height_m=sill)
    resumen["creados"].append(vano.code)
    resumen["vanos"] = 1
    resumen["datos"].update({
        "vano": vano.code, "tipo": tipo, "ancho_m": ancho,
        "alto_m": alto, "umbral_m": sill, "offset_m": round(offset, 3),
        "uso": uso or "-"})
    return resumen


# ---------------------------------------------------------------------------
# texto para la barra de estado y el informe (cp1252)
# ---------------------------------------------------------------------------

def texto_resumen_dibujo(resumen: Dict[str, Any]) -> str:
    """Una linea amable con lo dibujado y sus avisos."""
    base = f"{resumen.get('operacion', 'dibujo')}"
    datos = resumen.get("datos") or {}
    if datos.get("area_m2"):
        base += f" ({datos['area_m2']:.2f} m2"
        if datos.get("uso"):
            base += f", uso {datos['uso']}"
        base += ")"
    elif datos.get("largo_m"):
        base += f" ({datos['largo_m']:.2f} m x {datos['espesor_m']:.2f} m)"
    elif datos.get("asignados") is not None:
        base += f" ({len(datos['asignados'])} local(es) asignados)"
    if resumen["creados"]:
        base += f": {', '.join(resumen['creados'])}"
    for aviso in resumen["avisos"]:
        base += f" | aviso: {aviso}"
    return base


__all__ = [
    "HERRAMIENTAS_DIBUJO", "PROMPTS_DIBUJO", "PUNTOS_DIBUJO",
    "ES_VANO_DIBUJO", "KINDS_ZONA", "KIND_ZONA_DEF",
    "ESPESOR_MURO_DEF", "PUERTA_ANCHO_DEF",
    "PUERTA_ALTO_DEF", "VENTANA_ANCHO_DEF", "VENTANA_ALTO_DEF",
    "VENTANA_UMBRAL_DEF", "USO_ESPACIO_DEF", "REJILLA_DEF",
    "TOL_VERTICE_DEF", "snap_punto", "dibujar_muro", "dibujar_espacio",
    "dibujar_zona", "dibujar_vano", "texto_resumen_dibujo",
]
