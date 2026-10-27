"""HERRAMIENTAS DE EDICIÓN TIPO CAD (v3.14.0) — ui/cad_tools.py.

Mover, copiar, reflejar, girar, recortar, alargar, chaflán, dividir,
estirar y paralela sobre la EDIFICACIÓN REAL (muros, locales, vanos),
como AutoCAD pero con auditoría, undo persistente y regeneración.

Principios:
- Cero Tk: el mismo motor sirve a la paleta de herramientas de la
  GUI, al asistente de modificaciones, a la CLI y a las pruebas.
- Toda mutación pasa por los caminos oficiales: ArchitectureService
  (create_wall/create_space/create_opening/delete_entity) y
  UpdateEntityCommand con auditoría UPDATE_ENTITY, eventos
  GEOMETRY_CHANGED/SPACE_CHANGED e invalidación de QTO. El undo
  persistente (Ctrl+Z) deshace paso a paso, igual que en el resto de
  la app; el que llama hace ``ctx.commit()`` al terminar bien y
  ``ctx.rollback()`` si algo falla.
- Lo editado a mano SOBREVIVE a la regeneración: toda entidad
  generada por el asistente que toque una herramienta se re-marca
  (metadata «editada_a_mano» + origen «edición manual»), y
  building_wizard.collect_generated la respeta igual que un muro
  dibujado a mano.
- Al mover/reflejar/girar un LOCAL viajan con él sus muros
  EXCLUSIVOS (los que solo lo limitan a él); los muros compartidos
  con otros locales se quedan en su sitio (como en AutoCAD: mueves y
  luego rematas con recortar/alargar). Los vanos acompañan a su muro
  porque el movimiento es rígido (su offset sigue siendo válido).
- Si la operación afecta locales, las terminales de instalaciones
  ancladas a ellos se REANCLAN: se dan de baja con cascada y
  connect_local las vuelve a crear sobre la geometría nueva.
- finalizar() recalcula QTO de forma incremental al terminar.

Mensajes 100% codificables en cp1252 (disciplina v3.13.1: nada de
flechas ni emojis en texto que pueda ir a consola).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from core.geometry import engine as geo
from core.geometry.primitives import Line, Point
from services.architecture_service import ArchitectureService
from services.commands_impl import UpdateEntityCommand, entity_snapshot
from ui.building_wizard import WIZARD_ORIGIN

PT = Tuple[float, float]

TOL = 1e-6
TOL_ARISTA = 1e-3      # 1 mm: un muro "es" arista del local si cae entero a menos de esto

ORIGEN_EDICION = "edición manual (herramientas CAD v3.14.0)"
MARCA_MANO = "editada_a_mano"

# Códigos de error propios:
#   ARQ-CAD-001  objeto no encontrado
#   ARQ-CAD-002  tipo de entidad no soportado por la herramienta
#   ARQ-CAD-003  recortar: el corte no cae sobre el muro
#   ARQ-CAD-004  alargar: la intersección no queda más allá del extremo
#   ARQ-CAD-005  chaflán imposible (paralelos o distancia excesiva)
#   ARQ-CAD-006  dividir: el punto no está sobre el muro
#   ARQ-CAD-007  estirar: longitud nula


# ---------------------------------------------------------------------------
# resolución y marcas
# ---------------------------------------------------------------------------

def resolver(ctx: Any, tipo: str, ref: str) -> Any:
    """Entidad de arquitectura por id o por código (vanos por cualquiera
    de sus tres tipos). Lanza ARQ-CAD-001 si no aparece."""
    repo = ctx.architecture
    ent = repo.get(tipo, ref) or repo.get_by_code(tipo, ref)
    if ent is None and tipo in ("DOOR", "WINDOW", "OPENING"):
        for candidato in ("DOOR", "WINDOW", "OPENING"):
            ent = repo.get(candidato, ref) or repo.get_by_code(candidato, ref)
            if ent is not None:
                break
    if ent is None:
        raise DomainError(
            message=f"No se encontró {tipo} «{ref}» en el proyecto",
            code="ARQ-CAD-001",
            suggested_action="Actualiza el explorador y vuelve a elegir el objeto.")
    return ent


def _tipo_vano(ent: Any) -> str:
    """Tipo de borrado/consulta correcto para un vano (la tabla es única)."""
    return ent.kind if ent.kind in ("DOOR", "WINDOW") else "OPENING"


def _marca_manual(ent: Any) -> Dict[str, Any]:
    """Metadata que deja la huella de la edición manual.

    Si la entidad la generó el asistente, su «origen» pasa a «edición
    manual»: así collect_generated deja de considerarla generada y la
    siguiente regeneración la conserva igual que lo dibujado a mano.
    """
    meta = dict(ent.metadata or {})
    meta[MARCA_MANO] = True
    if str(meta.get("origen", "")).startswith(WIZARD_ORIGIN):
        meta["origen"] = ORIGEN_EDICION
    req = meta.get("requerimientos")
    if isinstance(req, dict) and str(req.get("origen", "")).startswith(WIZARD_ORIGIN):
        req = dict(req)
        req["origen"] = ORIGEN_EDICION
        meta["requerimientos"] = req
    return meta


def _cambio(ctx: Any, ent: Any, old: Dict[str, Any],
            eventos: Sequence[str]) -> None:
    """Persiste una entidad ya mutada con auditoría, eventos e
    invalidación de QTO (el patrón de ArchitectureService.move_wall)."""
    svc = ArchitectureService(ctx)
    ent.touch()
    ctx.command_bus.execute(UpdateEntityCommand(ent), ctx)
    svc._audit("UPDATE_ENTITY", ent.ENTITY_TYPE, ent.id, old,
               entity_snapshot(ent))
    for evento in eventos:
        ctx.emit(evento, {"id": ent.id, "type": ent.ENTITY_TYPE,
                          "code": ent.code})
    svc._invalidate_object(ent.id)


def _resumen(operacion: str) -> Dict[str, Any]:
    return {"operacion": operacion, "muros": [], "locales": [],
            "vanos": 0, "creados": [], "vanos_eliminados": [],
            "instalaciones": None, "avisos": [], "qto": None}


# ---------------------------------------------------------------------------
# capa pura de geometría (sin ctx: sirve al preview del asistente)
# ---------------------------------------------------------------------------

def interseccion_infinita(p1: PT, p2: PT, p3: PT, p4: PT) -> Optional[PT]:
    """Cruce de las INFINITAS p1-p2 y p3-p4 (None si son paralelas)."""
    denom = ((p1[0] - p2[0]) * (p3[1] - p4[1])
             - (p1[1] - p2[1]) * (p3[0] - p4[0]))
    if abs(denom) <= 1e-12:
        return None
    t = ((p1[0] - p3[0]) * (p3[1] - p4[1])
         - (p1[1] - p3[1]) * (p3[0] - p4[0])) / denom
    return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))


def _dist(p: PT, q: PT) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _dist_segmento(p: PT, a: PT, b: PT) -> float:
    """Distancia del punto p al segmento a-b."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    largo2 = ax * ax + ay * ay
    if largo2 <= TOL:
        return _dist(p, a)
    t = ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / largo2
    t = max(0.0, min(1.0, t))
    return _dist(p, (a[0] + t * ax, a[1] + t * ay))


def _unidad(p1: PT, p2: PT) -> PT:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    largo = math.hypot(dx, dy)
    if largo <= TOL:
        return (0.0, 0.0)
    return (dx / largo, dy / largo)


def g_trasladar(puntos: Sequence[PT], dx: float, dy: float) -> List[PT]:
    return [(x + dx, y + dy) for x, y in puntos]


def g_reflejar(puntos: Sequence[PT], eje1: PT, eje2: PT) -> List[PT]:
    a, b = Point(*eje1), Point(*eje2)
    return [Point(x, y).mirrored(a, b).to_tuple() for x, y in puntos]


def g_girar(puntos: Sequence[PT], centro: PT, angulo_deg: float) -> List[PT]:
    c = Point(*centro)
    return [Point(x, y).rotated(c, angulo_deg).to_tuple() for x, y in puntos]


def g_recortar(p1: PT, p2: PT, c1: PT, c2: PT,
               lado: str) -> Tuple[PT, PT]:
    """Recorta el muro p1-p2 contra la recta c1-c2 conservando el lado
    pedido; el corte debe caer sobre el muro (1 mm de gracia)."""
    if lado not in ("inicio", "fin"):
        raise DomainError(message="El lado a conservar es «inicio» o «fin»",
                          code="ARQ-CAD-003")
    cruce = interseccion_infinita(p1, p2, c1, c2)
    if cruce is None:
        raise DomainError(
            message="El muro de corte es paralelo al muro a recortar",
            code="ARQ-CAD-003",
            suggested_action="Elige otro muro que sí lo cruce.")
    total = _dist(p1, p2)
    ux, uy = _unidad(p1, p2)
    t = (cruce[0] - p1[0]) * ux + (cruce[1] - p1[1]) * uy
    if t < -1e-3 or t > total + 1e-3:
        raise DomainError(
            message="El corte no cae sobre el muro: la cuchilla no lo "
                    "alcanza",
            code="ARQ-CAD-003",
            suggested_action="Alarga primero uno de los dos muros "
                             "(herramienta Alargar).")
    t = max(0.0, min(total, t))
    cruce = (p1[0] + ux * t, p1[1] + uy * t)
    return (p1, cruce) if lado == "inicio" else (cruce, p2)


def g_alargar(p1: PT, p2: PT, t1: PT, t2: PT,
              extremo: str) -> Tuple[PT, PT]:
    """Alarga el muro p1-p2 por «extremo» hasta la recta t1-t2."""
    if extremo not in ("inicio", "fin"):
        raise DomainError(message="El extremo a alargar es «inicio» o «fin»",
                          code="ARQ-CAD-004")
    cruce = interseccion_infinita(p1, p2, t1, t2)
    if cruce is None:
        raise DomainError(
            message="El muro objetivo es paralelo: nunca lo alcanzaría",
            code="ARQ-CAD-004",
            suggested_action="Elige un muro objetivo que lo corte al "
                             "prolongarlo.")
    ux, uy = _unidad(p1, p2)
    if extremo == "fin":
        if (cruce[0] - p2[0]) * ux + (cruce[1] - p2[1]) * uy < -1e-9:
            raise DomainError(
                message="La intersección queda detrás del extremo fin: "
                        "eso sería recortar, no alargar",
                code="ARQ-CAD-004",
                suggested_action="Usa la herramienta Recortar o elige el "
                                 "otro extremo.")
        return (p1, cruce)
    if (cruce[0] - p1[0]) * ux + (cruce[1] - p1[1]) * uy > 1e-9:
        raise DomainError(
            message="La intersección queda detrás del extremo inicio: "
                    "eso sería recortar, no alargar",
            code="ARQ-CAD-004",
            suggested_action="Usa la herramienta Recortar o elige el "
                             "otro extremo.")
    return (cruce, p2)


def g_chaflan(a1: PT, a2: PT, b1: PT, b2: PT,
              distancia: float) -> Dict[str, Any]:
    """Chaflán entre dos muros: recorta cada uno a «distancia» de la
    esquina y devuelve los nuevos extremos y el segmento de unión.

    Devuelve {"nuevo_a": (p,q), "nuevo_b": (p,q), "union": (p,q),
    "esquina": pt}. Los muros pueden no tocarse: la esquina es el cruce
    de sus rectas (AutoCAD también prolonga).
    """
    if distancia <= 0:
        raise DomainError(message="La distancia del chaflán debe ser positiva",
                          code="ARQ-CAD-005")
    esquina = interseccion_infinita(a1, a2, b1, b2)
    if esquina is None:
        raise DomainError(
            message="Los muros son paralelos: no hay esquina que "
                    "chaflanear",
            code="ARQ-CAD-005",
            suggested_action="Elige dos muros con direcciones distintas.")
    if _dist(a1, a2) <= distancia + 1e-9 or _dist(b1, b2) <= distancia + 1e-9:
        raise DomainError(
            message="La distancia del chaflán excede el largo de un muro",
            code="ARQ-CAD-005",
            suggested_action="Reduce la distancia del chaflán.")

    def _corte(q1: PT, q2: PT) -> PT:
        lejos = q1 if _dist(q1, esquina) > _dist(q2, esquina) else q2
        ux, uy = _unidad(esquina, lejos)
        return (esquina[0] + ux * distancia, esquina[1] + uy * distancia)

    ca = _corte(a1, a2)
    cb = _corte(b1, b2)
    nuevo_a = (a1, ca) if _dist(a1, esquina) > _dist(a2, esquina) else (ca, a2)
    nuevo_b = (b1, cb) if _dist(b1, esquina) > _dist(b2, esquina) else (cb, b2)
    return {"nuevo_a": nuevo_a, "nuevo_b": nuevo_b, "union": (ca, cb),
            "esquina": esquina}


def g_dividir(p1: PT, p2: PT, punto: PT) -> Dict[str, Any]:
    """Divide el muro por el punto (proyectado) en dos partes."""
    ux, uy = _unidad(p1, p2)
    t = (punto[0] - p1[0]) * ux + (punto[1] - p1[1]) * uy
    total = _dist(p1, p2)
    if t <= 1e-3 or t >= total - 1e-3:
        raise DomainError(
            message="El punto de corte debe caer dentro del muro, no en "
                    "sus extremos",
            code="ARQ-CAD-006",
            suggested_action="Haz clic en un punto intermedio del muro.")
    corte = (p1[0] + ux * t, p1[1] + uy * t)
    return {"corte": corte, "parte1": (p1, corte), "parte2": (corte, p2),
            "largo1": t, "largo2": total - t}


def g_estirar(p1: PT, p2: PT, extremo: str,
              nuevo: PT) -> Tuple[PT, PT]:
    """Mueve el extremo elegido a la posición nueva."""
    if extremo not in ("inicio", "fin"):
        raise DomainError(message="El extremo a estirar es «inicio» o «fin»",
                          code="ARQ-CAD-007")
    if extremo == "inicio":
        if _dist(nuevo, p2) <= TOL:
            raise DomainError(message="El muro estirado tendría longitud nula",
                              code="ARQ-CAD-007")
        return (nuevo, p2)
    if _dist(p1, nuevo) <= TOL:
        raise DomainError(message="El muro estirado tendría longitud nula",
                          code="ARQ-CAD-007")
    return (p1, nuevo)


def g_paralela(p1: PT, p2: PT, distancia: float) -> Tuple[PT, PT]:
    """Copia paralela a distancia con signo (izquierda positiva según
    el sentido inicio-fin), igual que engine.offset_line."""
    linea = Line(Point(*p1), Point(*p2))
    off = geo.offset_line(linea, distancia)
    return (off.start.to_tuple(), off.end.to_tuple())


def _aristas(boundary: Sequence[PT]) -> List[Tuple[PT, PT]]:
    n = len(boundary)
    return [(tuple(boundary[i]), tuple(boundary[(i + 1) % n]))
            for i in range(n)]


def _area_firmada(puntos: Sequence[PT]) -> float:
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


# HERRAMIENTAS: (clave, glifo, etiqueta) — la paleta y el asistente las
# recorren en este orden. Glifos verificados en DejaVu/Segoe UI Symbol.
HERRAMIENTAS: Tuple[Tuple[str, str, str], ...] = (
    ("mover", "✚", "Mover"),
    ("copiar", "❐", "Copiar"),
    ("reflejar", "⇄", "Reflejar"),
    ("girar", "↻", "Girar"),
    ("recortar", "✂", "Recortar"),
    ("alargar", "⟶", "Alargar"),
    ("chaflan", "┌", "Chaflán"),
    ("dividir", "╪", "Dividir"),
    ("estirar", "⇥", "Estirar"),
    ("paralela", "∥", "Paralela"),
    ("borrar", "🗑", "Borrar"),
)

# Pasos que la barra de estado va anunciando por herramienta.
PROMPTS: Dict[str, Tuple[str, ...]] = {
    "mover": ("Clic sobre el muro o local a mover",
              "Clic en el punto base del desplazamiento",
              "Clic en el punto destino"),
    "copiar": ("Clic sobre el muro o local a copiar",
               "Clic en el punto base del desplazamiento",
               "Clic en el punto donde quieres la copia"),
    "reflejar": ("Clic sobre el muro o local a reflejar",
                 "Primer punto del eje de simetría",
                 "Segundo punto del eje de simetría"),
    "girar": ("Clic sobre el muro o local a girar",
              "Clic en el centro de giro",
              "Clic que marca el radio inicial",
              "Clic que marca el radio final (antihorario)"),
    "recortar": ("Clic sobre el muro a recortar",
                 "Clic sobre el muro que hace de cuchilla",
                 "Clic cerca del extremo que quieres CONSERVAR"),
    "alargar": ("Clic sobre el muro a alargar",
                "Clic sobre el muro hasta el que quieres llegar",
                "Clic cerca del extremo a alargar"),
    "chaflan": ("Clic sobre el primer muro, cerca de la esquina",
                "Clic sobre el segundo muro, cerca de la esquina"),
    "dividir": ("Clic sobre el muro a dividir",
                "Clic en el punto por el que cortarlo"),
    "estirar": ("Clic sobre el muro a estirar",
                "Clic cerca del extremo que quieres mover",
                "Clic en la nueva posición de ese extremo"),
    "paralela": ("Clic sobre el muro original",
                 "Clic al lado donde quieres la copia (la distancia es "
                 "la que hay hasta el clic)"),
    "borrar": ("Clic sobre el objeto a eliminar (muro, local o vano)"),
}

# Tipos de entidad admisibles como primer clic de cada herramienta.
TIPOS_POR_HERRAMIENTA: Dict[str, Tuple[str, ...]] = {
    "mover": ("WALL", "SPACE"),
    "copiar": ("WALL", "SPACE"),
    "reflejar": ("WALL", "SPACE"),
    "girar": ("WALL", "SPACE"),
    "recortar": ("WALL",),
    "alargar": ("WALL",),
    "chaflan": ("WALL",),
    "dividir": ("WALL",),
    "estirar": ("WALL",),
    "paralela": ("WALL",),
    "borrar": ("WALL", "SPACE", "DOOR", "WINDOW", "OPENING"),
}

# === PARTE 2: mutaciones (ctx) ===


# ---------------------------------------------------------------------------
# consultas de apoyo
# ---------------------------------------------------------------------------

def _vanos_de_muro(ctx: Any, wall_id: str) -> List[Any]:
    """Todos los vanos (DOOR/WINDOW/OPENING) alojados en el muro."""
    return list(ctx.architecture.list("OPENING", ctx.project.id,
                                      "wall_id = ?", (wall_id,)))


def _muros_de_nivel(ctx: Any, level_id: str) -> List[Any]:
    return list(ctx.architecture.list("WALL", ctx.project.id,
                                      "level_id = ?", (level_id,)))


def _locales_de_nivel(ctx: Any, level_id: str) -> List[Any]:
    return list(ctx.architecture.list("SPACE", ctx.project.id,
                                      "level_id = ?", (level_id,)))


def _muro_en_aristas(muro: Any, aristas: List[Tuple[PT, PT]]) -> bool:
    """El eje del muro cae entero (muestras 15-85 %) sobre alguna
    arista del local, con 1 mm de tolerancia."""
    p1, p2 = tuple(muro.start), tuple(muro.end)
    if _dist(p1, p2) <= TOL:
        return False
    for t in (0.15, 0.35, 0.5, 0.65, 0.85):
        q = (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)
        if min(_dist_segmento(q, a, b) for a, b in aristas) > TOL_ARISTA:
            return False
    return True


def _tramos_en_aristas(p1: PT, p2: PT,
                       aristas: List[Tuple[PT, PT]]) -> List[Tuple[PT, PT]]:
    """Porción(es) del segmento p1-p2 que caen sobre las aristas.

    Los muros fusionados por eje (merge_walls) suelen ser MÁS LARGOS
    que la arista del local: recortan el eje del muro a lo que de
    verdad limita el local, tramo a tramo (v3.21.0, ficha de local).
    Devuelve [(q1, q2), ...] en metros; vacío si el segmento no toca
    ninguna arista.
    """
    if _dist(tuple(p1), tuple(p2)) <= TOL:
        return []
    tramos: List[Tuple[PT, PT]] = []
    for a, b in aristas:
        lx, ly = b[0] - a[0], b[1] - a[1]
        largo = math.hypot(lx, ly)
        if largo <= TOL:
            continue
        ux, uy = lx / largo, ly / largo
        # el segmento debe ser COLINEAL con la arista
        d1 = (p1[0] - a[0]) * uy - (p1[1] - a[1]) * ux
        d2 = (p2[0] - a[0]) * uy - (p2[1] - a[1]) * ux
        if abs(d1) > TOL_ARISTA or abs(d2) > TOL_ARISTA:
            continue
        t1 = (p1[0] - a[0]) * ux + (p1[1] - a[1]) * uy
        t2 = (p2[0] - a[0]) * ux + (p2[1] - a[1]) * uy
        s0, s1 = max(0.0, min(t1, t2)), min(largo, max(t1, t2))
        if s1 - s0 <= TOL_ARISTA:
            continue
        tramos.append(((a[0] + ux * s0, a[1] + uy * s0),
                       (a[0] + ux * s1, a[1] + uy * s1)))
    return tramos


def muros_de_local(ctx: Any, space: Any,
                   solo_exclusivos: bool = True
                   ) -> Tuple[List[Any], List[Any]]:
    """(exclusivos, compartidos): muros que limitan el local.

    Un muro es COMPARTIDO si también es arista de OTRO local del mismo
    nivel — los muros fusionados por eje entre dos locales se detectan
    solos, sin necesidad de la lista de fuentes del trazado.
    """
    aristas = _aristas(space.boundary or [])
    propios = [m for m in _muros_de_nivel(ctx, space.level_id)
               if _muro_en_aristas(m, aristas)]
    if not solo_exclusivos:
        return propios, []
    otros = [s for s in _locales_de_nivel(ctx, space.level_id)
             if s.id != space.id]
    exclusivos: List[Any] = []
    compartidos: List[Any] = []
    for muro in propios:
        if any(_muro_en_aristas(muro, _aristas(s.boundary or []))
               for s in otros):
            compartidos.append(muro)
        else:
            exclusivos.append(muro)
    return exclusivos, compartidos


def _nivel_ref(ctx: Any, level_id: str) -> str:
    nivel = ctx.architecture.get("LEVEL", level_id)
    if nivel is None:
        raise DomainError(message=f"Nivel no encontrado: {level_id}",
                          code="ARQ-CAD-001")
    return nivel.code or nivel.name


# ---------------------------------------------------------------------------
# vanos: rehospedaje y volteo
# ---------------------------------------------------------------------------

def _rehospedar_vanos(ctx: Any, muro: Any, viejos: Tuple[PT, PT],
                      nuevos: Tuple[PT, PT], resumen: Dict[str, Any]) -> None:
    """Recalca los vanos del muro tras cambiar su geometría.

    El centro de cada vano se conserva en el mundo y se proyecta sobre
    el nuevo eje; los que ya no caben se DAN DE BAJA (auditoría) y el
    resto actualiza su offset. Si el eje invirtió el sentido (el
    arranque del muro cambió de extremo), las puertas voltean su
    apertura izquierda/derecha.
    """
    viejo1, viejo2 = viejos
    nuevo1, nuevo2 = nuevos
    largo_viejo = _dist(viejo1, viejo2)
    largo_nuevo = _dist(nuevo1, nuevo2)
    if largo_viejo <= TOL or largo_nuevo <= TOL:
        return
    u_viejo = _unidad(viejo1, viejo2)
    u_nuevo = _unidad(nuevo1, nuevo2)
    invierte = (u_viejo[0] * u_nuevo[0] + u_viejo[1] * u_nuevo[1]) < 0
    for vano in _vanos_de_muro(ctx, muro.id):
        centro = vano.offset_m + vano.width_m / 2.0
        mundo = (viejo1[0] + u_viejo[0] * centro,
                 viejo1[1] + u_viejo[1] * centro)
        t = ((mundo[0] - nuevo1[0]) * u_nuevo[0]
             + (mundo[1] - nuevo1[1]) * u_nuevo[1])
        t = max(0.0, min(largo_nuevo, t))
        offset_nuevo = t - vano.width_m / 2.0
        if offset_nuevo < -1e-9 or offset_nuevo + vano.width_m > largo_nuevo + 1e-9:
            ArchitectureService(ctx).delete_entity(_tipo_vano(vano), vano.id)
            resumen["vanos_eliminados"].append(vano.code)
            continue
        old = entity_snapshot(vano)
        vano.offset_m = max(round(offset_nuevo, 9), 0.0)
        if invierte and vano.kind == "DOOR":
            vano.swing = "RIGHT" if str(vano.swing).upper() == "LEFT" else "LEFT"
        _cambio(ctx, vano, old, ("OBJECT_UPDATED",))
        resumen["vanos"] += 1


def _voltear_swings(ctx: Any, muro: Any, resumen: Dict[str, Any]) -> None:
    """Reflejar invierte la orientación del muro: las puertas cambian
    de mano (izquierda <-> derecha) como en AutoCAD."""
    for vano in _vanos_de_muro(ctx, muro.id):
        if vano.kind != "DOOR":
            continue
        old = entity_snapshot(vano)
        vano.swing = "RIGHT" if str(vano.swing).upper() == "LEFT" else "LEFT"
        _cambio(ctx, vano, old, ("OBJECT_UPDATED",))
        resumen["vanos"] += 1


# ---------------------------------------------------------------------------
# muros y locales: traslación / copia / reflejo / giro
# ---------------------------------------------------------------------------

def _mueve_muro(ctx: Any, muro: Any, dx: float, dy: float,
                resumen: Dict[str, Any]) -> None:
    old = entity_snapshot(muro)
    muro.start = (muro.start[0] + dx, muro.start[1] + dy)
    muro.end = (muro.end[0] + dx, muro.end[1] + dy)
    muro.metadata = _marca_manual(muro)
    _cambio(ctx, muro, old, ("GEOMETRY_CHANGED",))
    resumen["muros"].append(muro.code)


def _mueve_local(ctx: Any, space: Any, dx: float, dy: float,
                 resumen: Dict[str, Any]) -> None:
    # los muros exclusivos se detectan ANTES de mover el polígono:
    # después ya no coincidirían con las aristas
    exclusivos, compartidos = muros_de_local(ctx, space)
    old = entity_snapshot(space)
    space.boundary = g_trasladar(space.boundary or [], dx, dy)
    space.metadata = _marca_manual(space)
    _cambio(ctx, space, old, ("SPACE_CHANGED",))
    resumen["locales"].append(space.code)
    for muro in exclusivos:
        _mueve_muro(ctx, muro, dx, dy, resumen)
    if compartidos:
        resumen["avisos"].append(
            f"{len(compartidos)} muro(s) compartido(s) con otros locales "
            f"se queda(n) en su sitio: remata con recortar o alargar si "
            f"hace falta")
    _reanclar_instalaciones(ctx, [space.id], resumen)


def mover(ctx: Any, refs: Sequence[Tuple[str, str]], dx: float,
          dy: float) -> Dict[str, Any]:
    """Traslada muros y/o locales (con sus muros exclusivos) por dx,dy."""
    resumen = _resumen("mover")
    if abs(dx) <= TOL and abs(dy) <= TOL:
        raise DomainError(message="El desplazamiento es nulo",
                          code="ARQ-CAD-002",
                          suggested_action="Indica dx,dy distintos de cero.")
    for tipo, ref in refs:
        ent = resolver(ctx, tipo, ref)
        if ent.ENTITY_TYPE == "WALL":
            _mueve_muro(ctx, ent, dx, dy, resumen)
        elif ent.ENTITY_TYPE == "SPACE":
            _mueve_local(ctx, ent, dx, dy, resumen)
        else:
            raise DomainError(
                message=f"Mover solo admite muros y locales (llegó "
                        f"{ent.ENTITY_TYPE})",
                code="ARQ-CAD-002")
    return resumen


def copiar(ctx: Any, tipo: str, ref: str, dx: float,
           dy: float) -> Dict[str, Any]:
    """Duplica un muro (con sus vanos) o un local (su polígono) con un
    desplazamiento dx,dy."""
    resumen = _resumen("copiar")
    if abs(dx) <= TOL and abs(dy) <= TOL:
        raise DomainError(message="El desplazamiento de la copia es nulo",
                          code="ARQ-CAD-002",
                          suggested_action="Indica dx,dy distintos de cero.")
    ent = resolver(ctx, tipo, ref)
    svc = ArchitectureService(ctx)
    if ent.ENTITY_TYPE == "WALL":
        nuevo = svc.create_wall(
            _nivel_ref(ctx, ent.level_id),
            (ent.start[0] + dx, ent.start[1] + dy),
            (ent.end[0] + dx, ent.end[1] + dy),
            thickness_m=ent.thickness_m, height_m=ent.height_m,
            material_id=ent.material_id, structural=ent.structural)
        nuevo.metadata = {"origen": ORIGEN_EDICION, "copia_de": ent.code,
                          MARCA_MANO: True}
        _cambio(ctx, nuevo, entity_snapshot(nuevo), ("OBJECT_UPDATED",))
        for vano in _vanos_de_muro(ctx, ent.id):
            svc.create_opening(vano.kind, nuevo.code, vano.width_m,
                               vano.height_m, offset_m=vano.offset_m,
                               sill_height_m=vano.sill_height_m,
                               swing=vano.swing)
            resumen["vanos"] += 1
        resumen["creados"].append(nuevo.code)
        resumen["muros"].append(ent.code)
    elif ent.ENTITY_TYPE == "SPACE":
        nuevo = svc.create_space(
            _nivel_ref(ctx, ent.level_id),
            f"{ent.name} (copia)", ent.space_type,
            g_trasladar(ent.boundary or [], dx, dy))
        nuevo.metadata = {"origen": ORIGEN_EDICION, "copia_de": ent.code}
        _cambio(ctx, nuevo, entity_snapshot(nuevo), ("OBJECT_UPDATED",))
        resumen["creados"].append(nuevo.code)
        resumen["locales"].append(ent.code)
        resumen["avisos"].append(
            "La copia del local es solo su polígono: los muros y vanos "
            "del original se quedan donde están")
    else:
        raise DomainError(
            message=f"Copiar solo admite muros y locales (llegó "
                    f"{ent.ENTITY_TYPE})",
            code="ARQ-CAD-002")
    return resumen


def _aplica_muro(ctx: Any, muro: Any, nuevos: Tuple[PT, PT],
                 resumen: Dict[str, Any]) -> None:
    """Nuevos extremos (inicio, fin) con marca manual y auditoría."""
    old = entity_snapshot(muro)
    muro.start = (round(nuevos[0][0], 9), round(nuevos[0][1], 9))
    muro.end = (round(nuevos[1][0], 9), round(nuevos[1][1], 9))
    muro.metadata = _marca_manual(muro)
    _cambio(ctx, muro, old, ("GEOMETRY_CHANGED",))
    resumen["muros"].append(muro.code)


def reflejar(ctx: Any, tipo: str, ref: str, eje1: PT,
             eje2: PT) -> Dict[str, Any]:
    """Refleja un muro o un local (con sus muros exclusivos) respecto
    del eje definido por dos puntos."""
    resumen = _resumen("reflejar")
    if _dist(tuple(eje1), tuple(eje2)) <= TOL:
        raise DomainError(message="El eje de simetría es degenerado",
                          code="ARQ-CAD-002",
                          suggested_action="Dame dos puntos distintos del eje.")
    ent = resolver(ctx, tipo, ref)
    if ent.ENTITY_TYPE == "WALL":
        viejos = (tuple(ent.start), tuple(ent.end))
        nuevos = tuple(g_reflejar(viejos, eje1, eje2))
        _aplica_muro(ctx, ent, nuevos, resumen)
        _voltear_swings(ctx, ent, resumen)
    elif ent.ENTITY_TYPE == "SPACE":
        exclusivos, compartidos = muros_de_local(ctx, ent)
        old = entity_snapshot(ent)
        boundary = g_reflejar(ent.boundary or [], eje1, eje2)
        if _area_firmada(boundary) < 0:
            boundary = list(reversed(boundary))
        ent.boundary = boundary
        ent.metadata = _marca_manual(ent)
        _cambio(ctx, ent, old, ("SPACE_CHANGED",))
        resumen["locales"].append(ent.code)
        for muro in exclusivos:
            viejos = (tuple(muro.start), tuple(muro.end))
            _aplica_muro(ctx, muro, tuple(g_reflejar(viejos, eje1, eje2)),
                         resumen)
            _voltear_swings(ctx, muro, resumen)
        if compartidos:
            resumen["avisos"].append(
                f"{len(compartidos)} muro(s) compartido(s) con otros "
                f"locales no se refleja(n)")
        _reanclar_instalaciones(ctx, [ent.id], resumen)
    else:
        raise DomainError(
            message=f"Reflejar solo admite muros y locales (llegó "
                    f"{ent.ENTITY_TYPE})",
            code="ARQ-CAD-002")
    return resumen


def girar(ctx: Any, tipo: str, ref: str, centro: PT,
          angulo_deg: float) -> Dict[str, Any]:
    """Gira un muro o un local (con sus muros exclusivos) alrededor de
    un centro; ángulo en grados antihorario."""
    resumen = _resumen("girar")
    if abs(angulo_deg % 360.0) <= TOL:
        raise DomainError(message="El ángulo de giro es nulo",
                          code="ARQ-CAD-002",
                          suggested_action="Indica un ángulo distinto de 0.")
    ent = resolver(ctx, tipo, ref)
    if ent.ENTITY_TYPE == "WALL":
        viejos = (tuple(ent.start), tuple(ent.end))
        _aplica_muro(ctx, ent, tuple(g_girar(viejos, centro, angulo_deg)),
                     resumen)
    elif ent.ENTITY_TYPE == "SPACE":
        exclusivos, compartidos = muros_de_local(ctx, ent)
        old = entity_snapshot(ent)
        ent.boundary = g_girar(ent.boundary or [], centro, angulo_deg)
        ent.metadata = _marca_manual(ent)
        _cambio(ctx, ent, old, ("SPACE_CHANGED",))
        resumen["locales"].append(ent.code)
        for muro in exclusivos:
            viejos = (tuple(muro.start), tuple(muro.end))
            _aplica_muro(ctx, muro,
                         tuple(g_girar(viejos, centro, angulo_deg)), resumen)
        if compartidos:
            resumen["avisos"].append(
                f"{len(compartidos)} muro(s) compartido(s) con otros "
                f"locales no gira(n)")
        _reanclar_instalaciones(ctx, [ent.id], resumen)
    else:
        raise DomainError(
            message=f"Girar solo admite muros y locales (llegó "
                    f"{ent.ENTITY_TYPE})",
            code="ARQ-CAD-002")
    return resumen


# === PARTE 3: recortar, alargar, chaflán, dividir, estirar, paralela ===


def recortar(ctx: Any, muro_ref: str, cuchilla_ref: str,
             lado: str) -> Dict[str, Any]:
    """Recorta un muro contra otro (cuchilla) conservando el lado dado.

    Los vanos que queden fuera del tramo conservado se dan de baja con
    aviso; el resto se re-proyecta.
    """
    resumen = _resumen("recortar")
    muro = resolver(ctx, "WALL", muro_ref)
    cuchilla = resolver(ctx, "WALL", cuchilla_ref)
    if muro.id == cuchilla.id:
        raise DomainError(message="El muro no puede ser cuchilla de sí mismo",
                          code="ARQ-CAD-003")
    viejos = (tuple(muro.start), tuple(muro.end))
    nuevos = g_recortar(viejos[0], viejos[1],
                        tuple(cuchilla.start), tuple(cuchilla.end), lado)
    if _dist(nuevos[0], nuevos[1]) <= TOL:
        raise DomainError(message="El recorte dejaría el muro sin longitud",
                          code="ARQ-CAD-003")
    _rehospedar_vanos(ctx, muro, viejos, nuevos, resumen)
    _aplica_muro(ctx, muro, nuevos, resumen)
    return resumen


def alargar(ctx: Any, muro_ref: str, objetivo_ref: str,
            extremo: str) -> Dict[str, Any]:
    """Alarga un muro por el extremo dado hasta el muro objetivo."""
    resumen = _resumen("alargar")
    muro = resolver(ctx, "WALL", muro_ref)
    objetivo = resolver(ctx, "WALL", objetivo_ref)
    if muro.id == objetivo.id:
        raise DomainError(message="El muro no puede alargarse hasta sí mismo",
                          code="ARQ-CAD-004")
    viejos = (tuple(muro.start), tuple(muro.end))
    nuevos = g_alargar(viejos[0], viejos[1],
                       tuple(objetivo.start), tuple(objetivo.end), extremo)
    _rehospedar_vanos(ctx, muro, viejos, nuevos, resumen)
    _aplica_muro(ctx, muro, nuevos, resumen)
    return resumen


def chaflan(ctx: Any, muro_a_ref: str, muro_b_ref: str,
            distancia: float) -> Dict[str, Any]:
    """Chaflán entre dos muros: recorta ambos a la distancia de la
    esquina y crea un muro nuevo que los une (hereda espesor, altura,
    material y nivel del primero)."""
    resumen = _resumen("chaflan")
    a = resolver(ctx, "WALL", muro_a_ref)
    b = resolver(ctx, "WALL", muro_b_ref)
    if a.id == b.id:
        raise DomainError(message="Elige dos muros distintos para el chaflán",
                          code="ARQ-CAD-005")
    datos = g_chaflan(tuple(a.start), tuple(a.end),
                      tuple(b.start), tuple(b.end), float(distancia))
    _rehospedar_vanos(ctx, a, (tuple(a.start), tuple(a.end)),
                      datos["nuevo_a"], resumen)
    _rehospedar_vanos(ctx, b, (tuple(b.start), tuple(b.end)),
                      datos["nuevo_b"], resumen)
    _aplica_muro(ctx, a, datos["nuevo_a"], resumen)
    _aplica_muro(ctx, b, datos["nuevo_b"], resumen)
    svc = ArchitectureService(ctx)
    union = svc.create_wall(_nivel_ref(ctx, a.level_id),
                            datos["union"][0], datos["union"][1],
                            thickness_m=a.thickness_m, height_m=a.height_m,
                            material_id=a.material_id,
                            structural=a.structural)
    union.metadata = {"origen": ORIGEN_EDICION,
                      "nota": f"chaflán entre {a.code} y {b.code}"}
    _cambio(ctx, union, entity_snapshot(union), ("OBJECT_UPDATED",))
    resumen["creados"].append(union.code)
    return resumen


def dividir(ctx: Any, muro_ref: str, punto: PT) -> Dict[str, Any]:
    """Divide un muro en dos en el punto dado; los vanos de la segunda
    mitad se re-acogen en el muro nuevo conservando su código."""
    resumen = _resumen("dividir")
    muro = resolver(ctx, "WALL", muro_ref)
    viejos = (tuple(muro.start), tuple(muro.end))
    datos = g_dividir(viejos[0], viejos[1], tuple(punto))
    svc = ArchitectureService(ctx)
    nuevo = svc.create_wall(_nivel_ref(ctx, muro.level_id),
                            datos["parte2"][0], datos["parte2"][1],
                            thickness_m=muro.thickness_m,
                            height_m=muro.height_m,
                            material_id=muro.material_id,
                            structural=muro.structural)
    nuevo.metadata = {"origen": ORIGEN_EDICION,
                      "nota": f"división de {muro.code}"}
    _cambio(ctx, nuevo, entity_snapshot(nuevo), ("OBJECT_UPDATED",))
    u_viejo = _unidad(viejos[0], viejos[1])
    for vano in _vanos_de_muro(ctx, muro.id):
        centro = vano.offset_m + vano.width_m / 2.0
        if centro <= datos["largo1"] + 1e-9:
            continue  # se queda en la primera parte con su offset intacto
        if centro - vano.width_m / 2.0 < datos["largo1"] - 1e-9:
            resumen["avisos"].append(
                f"El vano {vano.code} cruzaba el punto de corte: se "
                f"reubica entero en la segunda parte")
        old = entity_snapshot(vano)
        vano.wall_id = nuevo.id
        vano.offset_m = max(centro - datos["largo1"] - vano.width_m / 2.0,
                            0.0)
        _cambio(ctx, vano, old, ("OBJECT_UPDATED",))
        resumen["vanos"] += 1
    _aplica_muro(ctx, muro, datos["parte1"], resumen)
    resumen["creados"].append(nuevo.code)
    return resumen


def estirar(ctx: Any, muro_ref: str, extremo: str,
            nuevo: PT) -> Dict[str, Any]:
    """Mueve un extremo del muro a la posición nueva; los vanos se
    re-proyectan sobre el eje nuevo y los que no caben se dan de baja."""
    resumen = _resumen("estirar")
    muro = resolver(ctx, "WALL", muro_ref)
    viejos = (tuple(muro.start), tuple(muro.end))
    nuevos = g_estirar(viejos[0], viejos[1], extremo, tuple(nuevo))
    _rehospedar_vanos(ctx, muro, viejos, nuevos, resumen)
    _aplica_muro(ctx, muro, nuevos, resumen)
    return resumen


def paralela(ctx: Any, muro_ref: str,
             distancia: float) -> Dict[str, Any]:
    """Copia paralela del muro a la distancia con signo (izquierda
    positiva según inicio-fin), con los mismos vanos."""
    resumen = _resumen("paralela")
    muro = resolver(ctx, "WALL", muro_ref)
    if abs(float(distancia)) <= TOL:
        raise DomainError(message="La distancia de la paralela es nula",
                          code="ARQ-CAD-002",
                          suggested_action="Indica una distancia distinta "
                                           "de cero.")
    nuevos = g_paralela(tuple(muro.start), tuple(muro.end), float(distancia))
    svc = ArchitectureService(ctx)
    copia = svc.create_wall(_nivel_ref(ctx, muro.level_id),
                            nuevos[0], nuevos[1],
                            thickness_m=muro.thickness_m,
                            height_m=muro.height_m,
                            material_id=muro.material_id,
                            structural=muro.structural)
    copia.metadata = {"origen": ORIGEN_EDICION, "copia_de": muro.code,
                      MARCA_MANO: True}
    _cambio(ctx, copia, entity_snapshot(copia), ("OBJECT_UPDATED",))
    for vano in _vanos_de_muro(ctx, muro.id):
        svc.create_opening(vano.kind, copia.code, vano.width_m,
                           vano.height_m, offset_m=vano.offset_m,
                           sill_height_m=vano.sill_height_m,
                           swing=vano.swing)
        resumen["vanos"] += 1
    resumen["creados"].append(copia.code)
    resumen["muros"].append(muro.code)
    return resumen


def borrar(ctx: Any, tipo: str, ref: str) -> Dict[str, Any]:
    """Borra con cascada por el camino oficial (muro lleva sus vanos;
    los locales avisan de que muros y terminales se quedan)."""
    resumen = _resumen("borrar")
    ent = resolver(ctx, tipo, ref)
    tipo_real = _tipo_vano(ent) if ent.ENTITY_TYPE in (
        "DOOR", "WINDOW", "OPENING") else ent.ENTITY_TYPE
    if ent.ENTITY_TYPE == "SPACE":
        resumen["avisos"].append(
            "El local se elimina; sus muros y terminales de instalaciones "
            "se quedan: bórralos o reancla las instalaciones si toca")
    ArchitectureService(ctx).delete_entity(tipo_real, ent.id)
    resumen["muros" if ent.ENTITY_TYPE == "WALL"
            else "locales" if ent.ENTITY_TYPE == "SPACE"
            else "vanos_eliminados"].append(ent.code)
    return resumen


# ---------------------------------------------------------------------------
# instalaciones y cierre
# ---------------------------------------------------------------------------

def _reanclar_instalaciones(ctx: Any, space_ids: Sequence[str],
                            resumen: Dict[str, Any]) -> None:
    """Terminales de instalaciones de los locales tocados: baja con
    cascada y connect_local las recrea sobre la geometría nueva."""
    ids = {s for s in space_ids if s}
    if not ids:
        return
    from services.installations_generator import connect_local
    from services.installations_service import InstallationsService
    svc = InstallationsService(ctx)
    nodos = [n for n in ctx.installations.list("NODE", ctx.project.id)
             if getattr(n, "space_id", None) in ids]
    for nodo in nodos:
        svc.delete_entity("NODE", nodo.id)
    detalles: List[Dict[str, Any]] = []
    for sid in ids:
        space = ctx.architecture.get("SPACE", sid)
        if space is None:
            continue
        try:
            detalles.append(connect_local(ctx, space.id,
                                          origin=ORIGEN_EDICION))
        except Exception as exc:  # noqa: BLE001 — el aviso no frena la edición
            resumen["avisos"].append(
                f"Instalaciones del local {space.code}: {exc}")
    resumen["instalaciones"] = {"nodos_reanclados": len(nodos),
                                "detalle": detalles}


def finalizar(ctx: Any, resumen: Dict[str, Any]) -> Dict[str, Any]:
    """Cierra la operación: recálculo incremental de QTO. El que llama
    hace ctx.commit() y refresca la interfaz."""
    from services.quantity_service import QuantityService
    resumen["qto"] = QuantityService(ctx).compute_all()
    return resumen


def texto_resumen(resumen: Dict[str, Any]) -> str:
    """Una línea, amable y codificable en cp1252, para la barra de estado."""
    partes = [f"{resumen.get('operacion', 'operación')}:"]
    if resumen["muros"]:
        partes.append(f"{len(resumen['muros'])} muro(s)")
    if resumen["locales"]:
        partes.append(f"{len(resumen['locales'])} local(es)")
    if resumen["creados"]:
        partes.append(f"creados {', '.join(resumen['creados'])}")
    if resumen["vanos"]:
        partes.append(f"{resumen['vanos']} vano(s) tocado(s)")
    if resumen["vanos_eliminados"]:
        partes.append(f"vanos dados de baja: "
                      f"{', '.join(resumen['vanos_eliminados'])}")
    if isinstance(resumen.get("instalaciones"), dict):
        partes.append("instalaciones reancladas")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    for aviso in resumen["avisos"]:
        partes.append(f"aviso: {aviso}")
    return " · ".join(partes)


__all__ = [
    "HERRAMIENTAS", "PROMPTS", "TIPOS_POR_HERRAMIENTA", "MARCA_MANO",
    "ORIGEN_EDICION", "resolver", "muros_de_local", "mover", "copiar",
    "reflejar", "girar", "recortar", "alargar", "chaflan", "dividir",
    "estirar", "paralela", "borrar", "finalizar", "texto_resumen",
    "g_trasladar", "g_reflejar", "g_girar", "g_recortar", "g_alargar",
    "g_chaflan", "g_dividir", "g_estirar", "g_paralela",
]

