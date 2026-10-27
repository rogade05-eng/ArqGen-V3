"""EDITOR PROFUNDO DE LOCALES (v3.16.0).

Cambiar el nombre no basta: un local se edita como se piensa —
DIMENSIONES (mover sus muros exclusivos y re-proyectar sus vanos),
ACCESO (puerta en el muro que se pida, con el ancho del uso),
VENTILACION (ventana con el hueco que pide el uso: habitables 1/6 de
la superficie, humedos 1/25) y MOBILIARIO que se vuelve a colocar
sobre la geometria nueva. El diagnostico inicial dice lo que falta
(sin puerta, sin ventana suficiente, sin mobiliario) para que el
cambio sea una decision informada.

Todo por los caminos oficiales del proyecto: mutaciones de cad_tools
(auditoria, undo persistente, QTO incremental), alta de vanos por el
ArchitectureService e instalaciones reancladas tras cada cambio.

Cero Tk. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from services.commands_impl import UpdateEntityCommand, entity_snapshot
from ui import cad_tools
from ui.cad_tools import ORIGEN_EDICION, MARCA_MANO

PT = Tuple[float, float]

# error propio: ARQ-EDI-001 local desconocido / ARQ-EDI-002 cambio imposible

TOL = 1e-3

# Ancho de puerta de acceso segun el uso del local (m): Neufert
# abreviado, en español y en inglés (los space_type del DNA son
# ingleses); lo especifico del proyecto puede mas.
ANCHO_PUERTA_POR_USO: Dict[str, float] = {
    "dormitorio": 0.9, "habitacion": 0.9, "bed": 0.9, "sala": 0.9,
    "estar": 0.9, "living": 0.9, "comedor": 0.9, "dining": 0.9,
    "cocina": 0.9, "kitchen": 0.9, "bano": 0.8, "ba\u00f1o": 0.8,
    "bath": 0.8, "aseo": 0.7, "toilet": 0.7, "lavanderia": 0.8,
    "laundry": 0.8, "garaje": 2.5, "garage": 2.5, "vestibulo": 1.0,
    "oficina": 0.9, "despacho": 0.9, "office": 0.9,
    "sala_de_espera": 1.0, "waiting": 1.0,
    "aula": 1.0, "class": 1.0, "biblioteca": 1.0, "library": 1.0,
    "consultorio": 0.9, "quirófano": 1.2, "laboratorio": 1.0,
    "lab": 1.0, "farmacia": 1.0, "enfermeria": 1.0, "almacen": 1.2,
    "store": 1.2, "corredor": 1.2,
    # salud (v3.20.0): los tipos del DNA hospitalario y sus palabras
    # clave — camillas piden 1,20 m; carga y desechos, 1,50 m.
    "morgue": 1.2, "anatom": 1.2, "tomograf": 1.2, "ct_room": 1.2,
    "fluoro": 1.2, "microbiolog": 1.0, "nodo": 1.0, "server": 1.0,
    "pgd": 1.2, "waste": 1.2, "warehouse": 1.5, "operating": 1.2,
    "icu": 1.2, "urgencias": 1.2, "emergency": 1.2,
    "imaging": 1.2, "ward": 1.2, "progressive": 1.2,
    "steriliz": 1.2, "esteriliz": 1.2,
}
ANCHO_PUERTA_DEFECTO = 0.9
PUERTA_ALTO = 2.1

# Ventilacion: hueco minimo como fraccion de la superficie del local
# (CTE DB-HS1: habitables 1/6; humedos 1/25). Los space_type del DNA
# vienen en ingles.
TIPOS_HUMEDOS = ("BANO", "BAÑO", "ASEO", "COCINA", "LAVANDERIA",
                 "LAVADO", "DEPOSITO", "ALMACEN", "LABORATORIO",
                 "ESTERILIZACION", "BATHROOM", "KITCHEN", "LAUNDRY",
                 "TOILET", "WC", "STORAGE", "CLEANING")
FRACCION_HABITABLE = 1.0 / 6.0
FRACCION_HUMEDO = 1.0 / 25.0
VENTANA_ALTO = 1.2
VENTANA_ANTEPECHO = 1.0


# ---------------------------------------------------------------------------
# consulta
# ---------------------------------------------------------------------------

def _resolver_local(ctx: Any, ref: str) -> Any:
    local = cad_tools.resolver(ctx, "SPACE", ref)
    if len(getattr(local, "boundary", []) or []) < 3:
        raise DomainError(
            message=f"El local {ref} no tiene geometría editable",
            code="ARQ-EDI-002",
            suggested_action="Genera antes la edificación.")
    return local


def _vanos_de_local(ctx: Any, local: Any) -> List[Tuple[Any, Any]]:
    """(vano, muro) de todos los vanos que perforan los muros del local."""
    exclusivos, compartidos = cad_tools.muros_de_local(ctx, local,
                                                       solo_exclusivos=False)
    salida: List[Tuple[Any, Any]] = []
    for muro in exclusivos + compartidos:
        for vano in cad_tools._vanos_de_muro(ctx, muro.id):
            salida.append((vano, muro))
    return salida


def datos_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Diagnostico COMPLETO del local: lo que el dialogo muestra y lo
    que las pruebas verifican (dimensiones, muros, vanos, avisos)."""
    local = _resolver_local(ctx, ref)
    boundary = [tuple(p) for p in local.boundary]
    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    ancho = max(xs) - min(xs)
    fondo = max(ys) - min(ys)
    area = max(local.area_m2(), 0.01)
    exclusivos, compartidos = cad_tools.muros_de_local(ctx, local)
    vanos = _vanos_de_local(ctx, local)
    puertas = [v for v, _m in vanos
               if str(getattr(v, "kind", "")) == "DOOR"]
    ventanas = [v for v, _m in vanos
                if str(getattr(v, "kind", "")) == "WINDOW"]
    hueco_ventilacion = sum(float(v.width_m) * float(v.height_m)
                            for v in ventanas)
    tipo = str(local.space_type or "").upper()
    fraccion = FRACCION_HUMEDO if tipo in TIPOS_HUMEDOS else FRACCION_HABITABLE
    hueco_necesario = area * fraccion

    avisos: List[str] = []
    if not puertas:
        avisos.append("sin puerta de acceso")
    if tipo not in TIPOS_HUMEDOS and hueco_ventilacion + 1e-9 < \
            hueco_necesario:
        avisos.append("ventilacion insuficiente para un local habitable "
                      f"({hueco_ventilacion:.2f} m2 de hueco, necesitan "
                      f"{hueco_necesario:.2f} m2 = 1/6 del suelo)")
    elif tipo in TIPOS_HUMEDOS and hueco_ventilacion + 1e-9 < \
            hueco_necesario:
        avisos.append("ventilacion insuficiente para un local humedo "
                      f"({hueco_ventilacion:.2f} m2 de hueco, necesitan "
                      f"{hueco_necesario:.2f} m2 = 1/25 del suelo)")
    else:
        avisos.append("ventilacion suficiente")
    if not ventanas and tipo not in TIPOS_HUMEDOS:
        avisos.append("sin ventana")
    muebles = [e for e in _lista_segura(ctx, "FURNITURE")
               if getattr(e, "space_id", None) == local.id]
    return {
        "codigo": local.code,
        "nombre": local.name,
        "uso": local.space_type,
        "ancho_m": round(ancho, 3),
        "fondo_m": round(fondo, 3),
        "area_m2": round(area, 3),
        "muros_exclusivos": [m.code for m in exclusivos],
        "muros_compartidos": [m.code for m in compartidos],
        "puertas": [v.code for v in puertas],
        "ventanas": [v.code for v in ventanas],
        "hueco_ventilacion_m2": round(hueco_ventilacion, 3),
        "hueco_necesario_m2": round(hueco_necesario, 3),
        "mobiliario": len(muebles),
        "avisos": avisos,
    }


def _lista_segura(ctx: Any, tipo: str) -> List[Any]:
    try:
        return list(ctx.architecture.list(tipo, ctx.project.id))
    except Exception:  # noqa: BLE001 — proyectos viejos sin migrar
        return []


# ---------------------------------------------------------------------------
# acceso (puerta)
# ---------------------------------------------------------------------------

def ancho_puerta_por_uso(uso: str) -> float:
    clave = str(uso or "").lower().strip()
    for fragmento, ancho in ANCHO_PUERTA_POR_USO.items():
        if fragmento in clave:
            return ancho
    return ANCHO_PUERTA_DEFECTO


def crear_acceso(ctx: Any, ref: str, muro_ref: Optional[str] = None,
                 ancho: Optional[float] = None,
                 swing: str = "LEFT") -> Dict[str, Any]:
    """Puerta de acceso en el muro pedido (o el primer exclusivo).

    La puerta se centra en el muro y se desplaza si no cabe; queda
    auditada, con undo persistente y QTO invalidado.
    """
    local = _resolver_local(ctx, ref)
    ancho_p = max(float(ancho), 0.6) if ancho else \
        ancho_puerta_por_uso(local.space_type)
    muro = _muro_para_vano(ctx, local, muro_ref, ancho_p)
    alto = min(PUERTA_ALTO, float(muro.height_m))
    offset = _offset_centrado(muro, ancho_p)
    from services.architecture_service import ArchitectureService
    # la puerta se crea por el camino oficial (CreateEntityCommand);
    # NO se retoca despues: el undo persistente debe poder eliminarla
    puerta = ArchitectureService(ctx).create_opening(
        "DOOR", muro.code, ancho_p, alto, offset_m=offset, swing=swing)
    resumen: Dict[str, Any] = {
        "operacion": "acceso", "locales": [local.code],
        "muros": [], "creados": [puerta.code], "vanos": 1,
        "vanos_eliminados": [], "avisos": [], "qto": None}
    resumen["texto"] = (f"Acceso {puerta.code}: puerta de {ancho_p:.2f} m "
                        f"en {muro.code}")
    _cierra(ctx, resumen)
    return resumen


def _cierra(ctx: Any, resumen: Dict[str, Any]) -> None:
    """QTO incremental (patron cad_tools.finalizar) en dict plano."""
    cad_tools.finalizar(ctx, resumen)
    qto = resumen.get("qto")
    if qto is not None and hasattr(qto, "to_dict"):
        resumen["qto"] = qto.to_dict()


# ---------------------------------------------------------------------------
# ventilacion (ventana)
# ---------------------------------------------------------------------------

def sugerir_ventana(ctx: Any, ref: str) -> Dict[str, Any]:
    """Propuesta determinista de ventilacion: hueco que falta y muro
    donde ponerlo (primer exclusivo con sitio)."""
    datos = datos_local(ctx, ref)
    deficit = max(datos["hueco_necesario_m2"] -
                  datos["hueco_ventilacion_m2"], 0.0)
    propuesta: Dict[str, Any] = {
        "deficit_m2": round(deficit, 3), "muro": None, "ancho_m": 0.0,
        "suficiente": deficit <= 1e-9}
    if deficit <= 1e-9:
        return propuesta
    local = _resolver_local(ctx, ref)
    exclusivos, _compartidos = cad_tools.muros_de_local(ctx, local)
    ancho_min = max(deficit / VENTANA_ALTO, 0.6)
    for muro in exclusivos:
        largo = float(muro.length_m)
        if largo >= ancho_min + 0.4:
            propuesta["muro"] = muro.code
            propuesta["ancho_m"] = round(
                min(max(ancho_min, 0.6), largo * 0.7), 2)
            break
    return propuesta


def crear_ventana(ctx: Any, ref: str, muro_ref: Optional[str] = None,
                  ancho: Optional[float] = None) -> Dict[str, Any]:
    """Ventana con el ancho pedido (o el que el deficit de ventilacion
    pida): antepecho 1.00 m, altura 1.20 m."""
    local = _resolver_local(ctx, ref)
    if ancho:
        ancho_v = max(float(ancho), 0.4)
        muro = _muro_para_vano(ctx, local, muro_ref, ancho_v)
    else:
        propuesta = sugerir_ventana(ctx, ref)
        if propuesta["suficiente"]:
            raise DomainError(
                message=f"El local {local.code} ya ventila lo que "
                        "necesita",
                code="ARQ-EDI-002",
                suggested_action="Pide un ancho concreto si quieres una "
                                 "ventana adicional.")
        if not propuesta["muro"]:
            raise DomainError(
                message=f"Sin muro exclusivo con sitio para ventilar "
                        f"{local.code}",
                code="ARQ-EDI-002",
                suggested_action="Redimensiona el local o elige un muro "
                                 "con hueco libre.")
        muro = cad_tools.resolver(ctx, "WALL", propuesta["muro"])
        ancho_v = float(propuesta["ancho_m"])
    alto = min(VENTANA_ALTO, float(muro.height_m) - VENTANA_ANTEPECHO
               - 0.1)
    if alto < 0.4:
        alto = max(float(muro.height_m) * 0.35, 0.4)
    offset = _offset_centrado(muro, ancho_v)
    from services.architecture_service import ArchitectureService
    # la ventana se crea por el camino oficial (CreateEntityCommand);
    # NO se retoca despues: el undo persistente debe poder eliminarla
    ventana = ArchitectureService(ctx).create_opening(
        "WINDOW", muro.code, ancho_v, alto, offset_m=offset,
        sill_height_m=VENTANA_ANTEPECHO)
    resumen: Dict[str, Any] = {
        "operacion": "ventilacion", "locales": [local.code],
        "muros": [], "creados": [ventana.code], "vanos": 1,
        "vanos_eliminados": [], "avisos": [], "qto": None}
    resumen["texto"] = (f"Ventilacion {ventana.code}: ventana de "
                        f"{ancho_v:.2f} x {alto:.2f} m en {muro.code}")
    _cierra(ctx, resumen)
    return resumen


def _muro_para_vano(ctx: Any, local: Any, muro_ref: Optional[str],
                    ancho_vano: float) -> Any:
    """El muro pedido, o el primer exclusivo donde el vano quepa."""
    if muro_ref:
        muro = cad_tools.resolver(ctx, "WALL", muro_ref)
        if float(muro.length_m) < ancho_vano - 1e-9:
            raise DomainError(
                message=f"El vano de {ancho_vano:.2f} m no cabe en "
                        f"{muro.code} ({muro.length_m:.2f} m)",
                code="ARQ-EDI-002",
                suggested_action="Un muro mas largo o un vano mas "
                                 "estrecho.")
        return muro
    exclusivos, _compartidos = cad_tools.muros_de_local(ctx, local)
    for muro in exclusivos + _compartidos:
        if float(muro.length_m) >= ancho_vano + 0.2:
            return muro
    raise DomainError(
        message=f"Ningun muro de {local.code} admite un vano de "
                f"{ancho_vano:.2f} m",
        code="ARQ-EDI-002",
        suggested_action="Redimensiona el local antes de abrir el vano.")


def _offset_centrado(muro: Any, ancho_vano: float) -> float:
    largo = float(muro.length_m)
    return max(0.0, min((largo - ancho_vano) / 2.0, largo - ancho_vano))


# ---------------------------------------------------------------------------
# redimensionar
# ---------------------------------------------------------------------------

def redimensionar_local(ctx: Any, ref: str, ancho: float, fondo: float,
                        con_mobiliario: bool = True) -> Dict[str, Any]:
    """Lleva el local a las dimensiones pedidas MOVIENDO sus muros
    exclusivos (los compartidos se quedan y se avisa), re-proyectando
    los vanos, re-colocando el mobiliario y reanclando instalaciones.

    Devuelve las dimensiones REALES conseguidas (si un lado es
    compartido, ese lado no se mueve y se explica).
    """
    local = _resolver_local(ctx, ref)
    ancho = float(ancho)
    fondo = float(fondo)
    if ancho <= 0.5 or fondo <= 0.5:
        raise DomainError(
            message="Las dimensiones nuevas deben superar 0.50 m",
            code="ARQ-EDI-002",
            context={"ancho": ancho, "fondo": fondo},
            suggested_action="Pide un ancho y un fondo mayores.")
    boundary = [tuple(p) for p in local.boundary]
    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    minx, miny = min(xs), min(ys)
    maxx, maxy = max(xs), max(ys)
    ancho_actual, fondo_actual = maxx - minx, maxy - miny

    exclusivos, compartidos = cad_tools.muros_de_local(ctx, local)
    if not exclusivos and compartidos:
        raise DomainError(
            message=f"Todos los muros de {local.code} son compartidos: "
                    "no se puede redimensionar sin mover los vecinos",
            code="ARQ-EDI-002",
            suggested_action="Mueve el local completo con la herramienta "
                             "mover, o edita sus vecinos.")

    avisos: List[str] = []
    resumen: Dict[str, Any] = {
        "operacion": "redimensionar", "locales": [local.code],
        "muros": [], "creados": [], "vanos": 0,
        "vanos_eliminados": [], "avisos": avisos, "qto": None}

    def _es_horizontal(muro: Any) -> bool:
        return abs(muro.end[1] - muro.start[1]) <= 1e-6

    def _lado_de(muro: Any) -> Optional[str]:
        if _es_horizontal(muro):
            y = (muro.start[1] + muro.end[1]) / 2.0
            if abs(y - miny) <= 1e-6:
                return "bottom"
            if abs(y - maxy) <= 1e-6:
                return "top"
            return None
        x = (muro.start[0] + muro.end[0]) / 2.0
        if abs(x - minx) <= 1e-6:
            return "left"
        if abs(x - maxx) <= 1e-6:
            return "right"
        return None

    # lados con muro EXCLUSIVO (movibles) y lados compartidos (fijos)
    movibles = {"bottom": False, "top": False, "left": False,
                "right": False}
    for muro in exclusivos:
        lado = _lado_de(muro)
        if lado:
            movibles[lado] = True
    for muro in compartidos:
        lado = _lado_de(muro)
        if lado:
            avisos.append(f"lado {lado} compartido ({muro.code}): se "
                          "queda donde esta")

    # objetivo: crecer hacia el lado libre; si ambos lados de un eje
    # son movibles, crece a la derecha/arriba (como AutoCAD: se tira
    # de la goma desde el lado fijo)
    if movibles["right"]:
        nuevos = {"left": minx, "right": minx + ancho}
    elif movibles["left"]:
        nuevos = {"left": maxx - ancho, "right": maxx}
    else:
        nuevos = {"left": minx, "right": maxx}
        ancho = ancho_actual
        avisos.append("ancho sin muro exclusivo que mover: se conserva")
    if movibles["top"]:
        nuevos["top"] = miny + fondo
        nuevos["bottom"] = miny
    elif movibles["bottom"]:
        nuevos["bottom"] = maxy - fondo
        nuevos["top"] = maxy
    else:
        nuevos["top"] = maxy
        nuevos["bottom"] = miny
        fondo = fondo_actual
        avisos.append("fondo sin muro exclusivo que mover: se conserva")

    lados_movedizos = {"bottom": False, "top": False,
                       "left": False, "right": False}
    # 1) muros paralelos al lado: se mueven rigidos (vanos intactos)
    for muro in exclusivos:
        lado = _lado_de(muro)
        if lado is None:
            continue
        destino = nuevos[lado]
        if _es_horizontal(muro):
            delta = destino - (muro.start[1] + muro.end[1]) / 2.0
            if abs(delta) <= 1e-6:
                continue
            cad_tools.mover(ctx, [("WALL", muro.code)], 0.0, delta)
        else:
            delta = destino - (muro.start[0] + muro.end[0]) / 2.0
            if abs(delta) <= 1e-6:
                continue
            cad_tools.mover(ctx, [("WALL", muro.code)], delta, 0.0)
        resumen["muros"].append(muro.code)
        lados_movedizos[lado] = True

    # 2) muros perpendiculares exclusivos: estirar su extremo hasta el
    #    nuevo rincón para que el local cierre de nuevo
    rincones = _rincones_objetivo(minx, miny, maxx, maxy, nuevos,
                                  lados_movedizos)
    for muro in exclusivos:
        if _lado_de(muro) is not None:
            continue
        for extremo, clave in (("inicio", "start"), ("fin", "end")):
            punto = (float(muro.start[0]), float(muro.start[1])) \
                if clave == "start" else \
                (float(muro.end[0]), float(muro.end[1]))
            objetivo = rincones.get(_clave_rincon(punto, minx, miny,
                                                  maxx, maxy))
            if objetivo is None:
                continue
            if _dist2(punto, objetivo) > 1e-9:
                cad_tools.estirar(ctx, muro.code, extremo, objetivo)
                resumen["muros"].append(muro.code)
                break  # un extremo por muro y por lado

    # 3) boundary del local: los vertices siguen a su lado
    vieja_boundary = [(round(float(x), 4), round(float(y), 4))
                      for x, y in boundary]
    local.boundary = [
        _sigue_vertice((float(x), float(y)), minx, miny, maxx, maxy,
                       nuevos, lados_movedizos)
        for x, y in boundary]
    cad_tools._cambio(ctx, local, {"boundary": vieja_boundary},
                      ("OBJECT_UPDATED",))

    # 4) mobiliario y instalaciones sobre la geometria nueva
    if con_mobiliario:
        try:
            from domain import mobiliario
            mobiliario.quitar_mobiliario(ctx, space_ids=[local.id])
            reglas = mobiliario.proponer_piezas(
                local.space_type, local.area_m2())
            piezas, _avisos_mob = mobiliario.colocar_en_local(
                local, reglas, "ambos", "estandar")
            from domain.diseno_base import alta_entidad, metadata_origen
            for pieza in piezas:
                entidad = _furniture_de(ctx, local, pieza)
                alta_entidad(ctx, entidad)
            resumen["mobiliario"] = len(piezas)
        except Exception as exc:  # noqa: BLE001 — avisar no frenar
            avisos.append(f"mobiliario: {exc}")
    cad_tools._reanclar_instalaciones(ctx, [local.id], resumen)
    _cierra(ctx, resumen)

    xs2 = [p[0] for p in local.boundary]
    ys2 = [p[1] for p in local.boundary]
    resumen["texto"] = (f"Local {local.code} a {max(xs2)-min(xs2):.2f} x "
                        f"{max(ys2)-min(ys2):.2f} m "
                        f"(antes {ancho_actual:.2f} x {fondo_actual:.2f})")
    return resumen


def _rincones_objetivo(minx: float, miny: float, maxx: float,
                       maxy: float, nuevos: Dict[str, float],
                       movedizos: Dict[str, bool]) -> Dict[str, PT]:
    """Esquinas del local tras el cambio, solo si su lado se movio."""
    right = nuevos["right"] if movedizos["right"] else maxx
    left = nuevos["left"] if movedizos["left"] else minx
    top = nuevos["top"] if movedizos["top"] else maxy
    bottom = nuevos["bottom"] if movedizos["bottom"] else miny
    return {
        "min_min": (left, bottom), "max_min": (right, bottom),
        "min_max": (left, top), "max_max": (right, top),
    }


def _clave_rincon(punto: PT, minx: float, miny: float, maxx: float,
                  maxy: float) -> Optional[str]:
    ex = "min" if abs(punto[0] - minx) <= 1e-6 else \
        "max" if abs(punto[0] - maxx) <= 1e-6 else None
    ey = "min" if abs(punto[1] - miny) <= 1e-6 else \
        "max" if abs(punto[1] - maxy) <= 1e-6 else None
    if ex is None or ey is None:
        return None
    return f"{ex}_{ey}"


def _sigue_vertice(punto: PT, minx: float, miny: float, maxx: float,
                   maxy: float, nuevos: Dict[str, float],
                   movedizos: Dict[str, bool]) -> PT:
    x, y = punto
    if movedizos["right"] and abs(x - maxx) <= 1e-6:
        x = nuevos["right"]
    elif movedizos["left"] and abs(x - minx) <= 1e-6:
        x = nuevos["left"]
    if movedizos["top"] and abs(y - maxy) <= 1e-6:
        y = nuevos["top"]
    elif movedizos["bottom"] and abs(y - miny) <= 1e-6:
        y = nuevos["bottom"]
    return (round(x, 4), round(y, 4))


def _dist2(p: PT, q: PT) -> float:
    return (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2


def _furniture_de(ctx: Any, local: Any, pieza: Dict[str, Any]) -> Any:
    from domain.model import Furniture
    from domain.diseno_base import metadata_origen
    return Furniture(
        project_id=ctx.project.id,
        code=ctx.next_code("ARCHITECTURE", "FURNITURE"),
        level_id=local.level_id, space_id=local.id,
        kind=pieza["kind"], name=pieza["nombre"],
        x=pieza["x"], y=pieza["y"], rotation_deg=pieza["rot"],
        width_m=pieza["w"], depth_m=pieza["d"], height_m=pieza["h"],
        metadata=metadata_origen(
            f"mobiliario de {local.name} ({local.code})",
            {"ambito": "auto", "densidad": "estandar",
             "categoria": pieza["categoria"]}))


# ---------------------------------------------------------------------------
# mobiliario / texto
# ---------------------------------------------------------------------------

def regenerar_mobiliario_local(ctx: Any, ref: str,
                               densidad: str = "estandar",
                               ambito: str = "ambos"
                               ) -> Dict[str, Any]:
    """Vuelve a amueblar UN local con su uso actual.

    El ámbito por defecto es «ambos»: el TIPO del local manda sobre su
    mobiliario (la morgue trae su mesa de autopsias aunque el proyecto
    no declare un uso social)."""
    local = _resolver_local(ctx, ref)
    from domain import mobiliario
    return mobiliario.generar_mobiliario(ctx, space_ids=[local.id],
                                         densidad=densidad, ambito=ambito)


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Una linea cp1252 para la barra de estado."""
    if resumen.get("texto"):
        partes = [resumen["texto"]]
    else:
        partes = [f"{resumen.get('operacion', 'operación')}:"] + \
            [f"creados {', '.join(resumen.get('creados', []))}"]
    if resumen.get("vanos_eliminados"):
        partes.append(f"vanos dados de baja: "
                      f"{', '.join(resumen['vanos_eliminados'])}")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


# ---------------------------------------------------------------------------
# ASISTENTE DE LOCAL — MODIFICAR (v3.20.0)
# ---------------------------------------------------------------------------
# El asistente de local ya no solo CREA: modifica un local existente
# controlando TODO lo que le es imputable — identidad (nombre y uso
# con su DNA), geometría (posición y espesor de sus muros, cota del
# piso), vanos (crear, retocar medidas o dar de baja), instalaciones
# (eléctrica y sanitaria, iluminación por lámparas, alarma) y
# mobiliario — todo por los caminos oficiales (comandos, auditoría,
# undo persistente y QTO) y con diagnóstico DNA al final.

def _dna_de(ctx: Any, uso: str) -> Any:
    """El DNA del uso, o None si el proyecto no trae registro."""
    registro = getattr(ctx, "dna_registry", None)
    if registro is None:
        return None
    try:
        return registro.get(str(uso or "").upper())
    except Exception:  # noqa: BLE001 — registro sin cargar
        return None


def _lista_vanos_local(ctx: Any, local: Any) -> List[Any]:
    return [vano for vano, _muro in _vanos_de_local(ctx, local)]


def _resuelve_vano_local(ctx: Any, local: Any, vano_ref: str) -> Any:
    """El vano del local pedido (por código o id); error amable si no."""
    objetivo = str(vano_ref or "").strip()
    for vano in _lista_vanos_local(ctx, local):
        if objetivo in (str(getattr(vano, "code", "")),
                        str(getattr(vano, "id", ""))):
            return vano
    raise DomainError(
        message=f"El vano {objetivo} no pertenece al local {local.code}",
        code="ARQ-EDI-002",
        suggested_action="Elige un vano de la lista del local.")


def cambiar_identidad(ctx: Any, ref: str, nombre: Optional[str] = None,
                      uso: Optional[str] = None,
                      con_mobiliario: bool = False) -> Dict[str, Any]:
    """Nombre y USO del local, con la validez que pide el DNA.

    Si el uso nuevo tiene DNA y el local queda por debajo del área
    mínima, se avisa (no se impide: lo decide el proyectista). Con
    ``con_mobiliario`` el mobiliario se re-coloca para el uso nuevo.
    """
    local = _resolver_local(ctx, ref)
    avisos: List[str] = []
    nombre_nuevo = str(nombre or "").strip()
    uso_nuevo = str(uso or "").strip()
    if not nombre_nuevo and not uso_nuevo:
        raise DomainError(
            message="No hay nada que cambiar: dame nombre o uso",
            code="ARQ-EDI-002",
            suggested_action="Escribe el nombre nuevo o elige un uso.")
    if uso_nuevo and uso_nuevo.upper() != \
            str(local.space_type or "").upper():
        dna = _dna_de(ctx, uso_nuevo)
        if dna is None:
            raise DomainError(
                message=f"El uso «{uso_nuevo}» no está en el catálogo "
                        "de tipos de local",
                code="ARQ-EDI-002",
                suggested_action="Elige un tipo de la lista (los del "
                                 "asistente de edificación).")
        if local.area_m2() + 1e-9 < float(dna.minimum_area or 0.0):
            avisos.append(
                f"el área ({local.area_m2():.2f} m2) queda por debajo "
                f"de la mínima del uso ({float(dna.minimum_area):.2f} "
                "m2)")
    old = entity_snapshot(local)
    if nombre_nuevo:
        local.name = nombre_nuevo
    if uso_nuevo:
        local.space_type = uso_nuevo.upper()
    cad_tools._cambio(ctx, local, old, ("OBJECT_UPDATED",))
    resumen: Dict[str, Any] = {
        "operacion": "identidad", "locales": [local.code], "muros": [],
        "creados": [], "vanos": 0, "vanos_eliminados": [],
        "avisos": avisos, "qto": None}
    resumen["texto"] = (f"Local {local.code}: "
                        f"«{local.name or local.space_type}» "
                        f"({local.space_type})")
    if con_mobiliario and uso_nuevo:
        try:
            mob = regenerar_mobiliario_local(ctx, ref)
            resumen["mobiliario"] = len(mob.get("creados", [])
                                        or mob.get("piezas", []))
        except Exception as exc:  # noqa: BLE001 — avisar no frenar
            avisos.append(f"mobiliario: {exc}")
    _cierra(ctx, resumen)
    return resumen


def mover_local(ctx: Any, ref: str, dx: float, dy: float
                ) -> Dict[str, Any]:
    """Desplaza el local completo (boundary + muros exclusivos).

    Los vanos viajan con su muro (viven en él) y el mobiliario se
    mueve con el local. Los muros COMPARTIDOS no se mueven: se avisa
    para que el vecino no sufra el empujón.
    """
    local = _resolver_local(ctx, ref)
    dx, dy = float(dx), float(dy)
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        raise DomainError(
            message="El desplazamiento es cero: no hay nada que mover",
            code="ARQ-EDI-002",
            suggested_action="Indica cuánto avanzar en X y en Y.")
    exclusivos, compartidos = cad_tools.muros_de_local(ctx, local)
    avisos: List[str] = []
    resumen: Dict[str, Any] = {
        "operacion": "mover_local", "locales": [local.code], "muros": [],
        "creados": [], "vanos": 0, "vanos_eliminados": [],
        "avisos": avisos, "qto": None}
    refs: List[Tuple[str, str]] = [("WALL", m.code) for m in exclusivos]
    for muro in compartidos:
        avisos.append(f"muro compartido {muro.code} no se mueve")
    if refs:
        cad_tools.mover(ctx, refs, dx, dy)
        resumen["muros"] = [code for _k, code in refs]
    vieja_boundary = [tuple(p) for p in local.boundary]
    local.boundary = [(round(float(x) + dx, 4), round(float(y) + dy, 4))
                      for x, y in local.boundary]
    cad_tools._cambio(ctx, local, {"boundary": vieja_boundary},
                      ("OBJECT_UPDATED",))
    muebles = [e for e in _lista_segura(ctx, "FURNITURE")
               if getattr(e, "space_id", None) == local.id]
    for mueble in muebles:
        old = entity_snapshot(mueble)
        mueble.x = float(mueble.x) + dx
        mueble.y = float(mueble.y) + dy
        cad_tools._cambio(ctx, mueble, old, ("OBJECT_UPDATED",))
    if muebles:
        resumen["mobiliario"] = len(muebles)
    cad_tools._reanclar_instalaciones(ctx, [local.id], resumen)
    _cierra(ctx, resumen)
    resumen["texto"] = (f"Local {local.code} desplazado "
                        f"({dx:+.2f}, {dy:+.2f}) m")
    return resumen


def espesor_muros_exclusivos(ctx: Any, ref: str, espesor: float
                             ) -> Dict[str, Any]:
    """Espesor nuevo para los muros EXCLUSIVOS del local."""
    local = _resolver_local(ctx, ref)
    espesor = float(espesor)
    boundary = [tuple(p) for p in local.boundary]
    xs = [p[0] for p in boundary]
    ys = [p[1] for p in boundary]
    menor = min(max(xs) - min(xs), max(ys) - min(ys))
    if espesor <= 0:
        raise DomainError(
            message="El espesor del muro debe ser positivo",
            code="ARQ-EDI-002",
            suggested_action="0,2 m (20 cm) es lo habitual.")
    if espesor * 2 >= menor:
        raise DomainError(
            message=f"Un espesor de {espesor:.2f} m se come el local "
                    f"({menor:.2f} m en su lado menor)",
            code="ARQ-EDI-002",
            suggested_action="Baja el espesor o agranda el local.")
    exclusivos, compartidos = cad_tools.muros_de_local(ctx, local)
    if not exclusivos:
        raise DomainError(
            message=f"{local.code} no tiene muros exclusivos que "
                    "retocar",
            code="ARQ-EDI-002",
            suggested_action="Sus muros son compartidos: edítalos con "
                             "la herramienta de muro.")
    avisos = [f"muro compartido {muro.code} no se toca"
              for muro in compartidos]
    resumen: Dict[str, Any] = {
        "operacion": "espesor", "locales": [local.code], "muros": [],
        "creados": [], "vanos": 0, "vanos_eliminados": [],
        "avisos": avisos, "qto": None}
    for muro in exclusivos:
        old = entity_snapshot(muro)
        muro.thickness_m = espesor
        cad_tools._cambio(ctx, muro, old, ("OBJECT_UPDATED",))
        resumen["muros"].append(muro.code)
    _cierra(ctx, resumen)
    resumen["texto"] = (f"Espesor {espesor:.2f} m en "
                        f"{len(resumen['muros'])} muro(s) de "
                        f"{local.code}")
    return resumen


def editar_vano(ctx: Any, ref: str, vano_ref: str, ancho: Optional[float]
                = None, alto: Optional[float] = None,
                antepecho: Optional[float] = None,
                offset: Optional[float] = None) -> Dict[str, Any]:
    """Retoca un vano DEL local: ancho, alto, antepecho y posición."""
    local = _resolver_local(ctx, ref)
    vano = _resuelve_vano_local(ctx, local, vano_ref)
    muro = None
    wall_id = getattr(vano, "wall_id", "")
    if wall_id:
        muro = ctx.architecture.get("WALL", wall_id)
    ancho_n = float(ancho) if ancho is not None else float(vano.width_m)
    alto_n = float(alto) if alto is not None else float(vano.height_m)
    antepecho_n = float(antepecho) if antepecho is not None \
        else float(getattr(vano, "sill_height_m", 0.0) or 0.0)
    offset_n = float(offset) if offset is not None \
        else float(vano.offset_m)
    if ancho_n <= 0 or alto_n <= 0:
        raise DomainError(
            message="El vano necesita ancho y alto positivos",
            code="ARQ-EDI-002")
    if antepecho_n < 0:
        raise DomainError(
            message="El antepecho no puede ser negativo",
            code="ARQ-EDI-002")
    if muro is not None:
        largo = float(muro.length_m)
        if offset_n < 0 or offset_n + ancho_n > largo + 1e-9:
            raise DomainError(
                message=f"El vano no cabe en {muro.code}: offset "
                        f"{offset_n:.2f} + ancho {ancho_n:.2f} > "
                        f"{largo:.2f} m",
                code="ARQ-EDI-002",
                suggested_action="Baja el ancho o adelanta el vano.")
        if alto_n + antepecho_n > float(muro.height_m) + 1e-9:
            raise DomainError(
                message=f"Alto {alto_n:.2f} m + antepecho "
                        f"{antepecho_n:.2f} m no cabe en el muro "
                        f"({float(muro.height_m):.2f} m)",
                code="ARQ-EDI-002")
    old = entity_snapshot(vano)
    vano.width_m = ancho_n
    vano.height_m = alto_n
    vano.offset_m = offset_n
    if hasattr(vano, "sill_height_m"):
        vano.sill_height_m = antepecho_n
    cad_tools._cambio(ctx, vano, old, ("OBJECT_UPDATED",))
    resumen: Dict[str, Any] = {
        "operacion": "editar_vano", "locales": [local.code], "muros": [],
        "creados": [], "vanos": 1, "vanos_eliminados": [],
        "avisos": [], "qto": None}
    resumen["texto"] = (f"Vano {vano.code}: {ancho_n:.2f} x "
                        f"{alto_n:.2f} m a {offset_n:.2f} m del "
                        f"extremo")
    _cierra(ctx, resumen)
    return resumen


def quitar_vano(ctx: Any, ref: str, vano_ref: str) -> Dict[str, Any]:
    """Da de baja un vano DEL local (puerta o ventana) por el camino
    oficial (auditoría + undo persistente)."""
    local = _resolver_local(ctx, ref)
    vano = _resuelve_vano_local(ctx, local, vano_ref)
    kind = str(getattr(vano, "kind", "OPENING")).upper() or "OPENING"
    from services.architecture_service import ArchitectureService
    ArchitectureService(ctx).delete_entity(kind, vano.id)
    resumen: Dict[str, Any] = {
        "operacion": "quitar_vano", "locales": [local.code], "muros": [],
        "creados": [], "vanos": 0,
        "vanos_eliminados": [vano.code], "avisos": [], "qto": None}
    resumen["texto"] = f"Vano {vano.code} dado de baja en {local.code}"
    _cierra(ctx, resumen)
    return resumen


def cota_piso_local(ctx: Any, ref: str, cota_m: float) -> Dict[str, Any]:
    """Cota del piso del local (metadata «arquitectonicos», el mismo
    sitio que usa el asistente de edificación y la vista 3D)."""
    local = _resolver_local(ctx, ref)
    cota = float(cota_m)
    if cota < 0:
        raise DomainError(
            message="La cota del piso no puede ser negativa",
            code="ARQ-EDI-002",
            suggested_action="Usa 0 para el piso del nivel.")
    nivel = ctx.architecture.get("LEVEL", local.level_id) \
        if getattr(local, "level_id", "") else None
    avisos: List[str] = []
    if nivel is not None and cota >= float(nivel.height_m):
        avisos.append(f"la cota {cota:.2f} m alcanza o supera la "
                      f"altura del nivel ({float(nivel.height_m):.2f} m)")
    meta = dict(getattr(local, "metadata", None) or {})
    req = dict(meta.get("requerimientos", {}) or {})
    arqui = dict(req.get("arquitectonicos", {}) or {})
    arqui["cota_piso_m"] = round(cota, 3)
    req["arquitectonicos"] = arqui
    meta["requerimientos"] = req
    old = entity_snapshot(local)
    local.metadata = meta
    cad_tools._cambio(ctx, local, old, ("OBJECT_UPDATED",))
    resumen: Dict[str, Any] = {
        "operacion": "cota_piso", "locales": [local.code], "muros": [],
        "creados": [], "vanos": 0, "vanos_eliminados": [],
        "avisos": avisos, "qto": None}
    resumen["texto"] = (f"Piso de {local.code} a {cota:.2f} m de cota")
    _cierra(ctx, resumen)
    return resumen


def conectar_instalaciones_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Conecta el local a las redes (luminaria + toma; agua y desagüe
    si es húmedo), el mismo camino del asistente de creación."""
    local = _resolver_local(ctx, ref)
    from services.installations_generator import connect_local
    inst = connect_local(ctx, local.code,
                         origin="asistente de local (modificar)")
    resumen: Dict[str, Any] = {
        "operacion": "instalaciones", "locales": [local.code],
        "muros": [], "creados": list(inst.get("nombres", []) or []),
        "vanos": 0, "vanos_eliminados": [],
        "avisos": list(inst.get("warnings", []) or []), "qto": None}
    resumen["instalaciones"] = {
        "redes": inst.get("redes", 0), "equipos": inst.get("equipos", 0),
        "tramos": inst.get("tramos", 0)}
    resumen["texto"] = (f"Instalaciones de {local.code}: "
                        f"{inst.get('equipos', 0)} equipo(s) en "
                        f"{inst.get('redes', 0)} red(es)")
    _cierra(ctx, resumen)
    return resumen


def iluminar_local(ctx: Any, ref: str, lampara: str = "led_panel",
                   lux: Optional[int] = None) -> Dict[str, Any]:
    """Dimensiona y coloca las luminarias de UN local (método de los
    lúmenes; las de este local se renuevan, el resto del proyecto se
    conserva)."""
    local = _resolver_local(ctx, ref)
    from domain import iluminacion
    base = iluminacion.generar_iluminacion(
        ctx, lampara=lampara, space_ids=[local.id], lux=lux)
    resumen: Dict[str, Any] = {
        "operacion": "iluminar", "locales": [local.code], "muros": [],
        "creados": list(base.get("creados", []) or []),
        "vanos": 0,
        "vanos_eliminados": list(base.get("eliminados", []) or []),
        "avisos": list(base.get("avisos", []) or []),
        "qto": base.get("qto")}
    locale_dato = (base.get("locales") or [{}])[0]
    resumen["texto"] = (
        f"Iluminación de {local.code}: {len(resumen['creados'])} "
        f"luminaria(s) «{iluminacion.datos_lampara(lampara)['etiqueta']}»"
        f" a {locale_dato.get('lux', lux or '-')} lux")
    return resumen


def alarmar_local(ctx: Any, ref: str, sirena_exterior: bool = False
                  ) -> Dict[str, Any]:
    """Protege UN local: PIR, contactos en sus vanos, panel, teclado y
    sirena; validado por el motor de intrusión."""
    local = _resolver_local(ctx, ref)
    from domain import alarmas
    base = alarmas.generar_alarma(
        ctx, space_ids=[local.id], panel_space_id=local.id,
        sirena_exterior=sirena_exterior)
    resumen: Dict[str, Any] = {
        "operacion": "alarmar", "locales": [local.code], "muros": [],
        "creados": list(base.get("creados", []) or []),
        "vanos": 0,
        "vanos_eliminados": list(base.get("eliminados", []) or []),
        "avisos": list(base.get("avisos", []) or []),
        "qto": base.get("qto")}
    zonas = base.get("zonas") or []
    resumen["texto"] = (f"Alarma en {local.code}: "
                        f"{len(resumen['creados'])} dispositivo(s)"
                        + (f", zona «{zonas[0].get('nombre', '')}»"
                           if zonas else ""))
    return resumen


def resumen_completo(ctx: Any, ref: str) -> Dict[str, Any]:
    """Diagnóstico TOTAL del local: lo que tiene y lo que le falta.

    Une el diagnóstico de siempre (dimensiones, ventilación,
    mobiliario) con el DNA del uso (área mínima, puerta por camilla),
    la cota del piso y un recuento de sus instalaciones (luminarias,
    alarma).
    """
    datos = datos_local(ctx, ref)
    local = _resolver_local(ctx, ref)
    avisos = list(datos["avisos"])
    dna = _dna_de(ctx, datos["uso"])
    ficha: Dict[str, Any] = {}
    if dna is not None:
        minima = float(dna.minimum_area or 0.0)
        ficha = {
            "nombre_es": getattr(dna, "name_es", "") or datos["uso"],
            "area_minima": minima,
            "altura_min": getattr(dna, "height", None),
            "puerta_min": (getattr(dna, "neufert", {}) or {}).get(
                "puerta_m"),
            "humedo": bool(getattr(dna, "wet_zone", False)),
        }
        if minima and datos["area_m2"] + 1e-9 < minima:
            avisos.append(
                f"área por debajo de la mínima del uso ({minima:.2f} m2)")
        puerta_min = (dna.metadata.get("neufert") or {}).get("puerta_m")
        ficha["puerta_min"] = puerta_min
        if puerta_min and datos["puertas"]:
            for vano, _muro in _vanos_de_local(ctx, local):
                if str(getattr(vano, "kind", "")) == "DOOR" and \
                        float(vano.width_m) + 1e-9 < float(
                            puerta_min):
                    avisos.append(
                        f"puerta {vano.code} de "
                        f"{float(vano.width_m):.2f} m: el uso pide "
                        f"{float(puerta_min):.2f} m")
    nodos: List[Any] = []
    try:
        nodos = list(ctx.installations.list("NODE", ctx.project.id))
    except Exception:  # noqa: BLE001 — base sin migrar aún
        nodos = []
    luminarias = [n for n in nodos
                  if str(getattr(n, "kind", "")) == "LUMINAIRE"
                  and getattr(n, "space_id", None) == local.id]
    alarmas_n = [n for n in nodos
                 if (n.attrs or {}).get("origen_alarma")
                 and getattr(n, "space_id", None) == local.id]
    from domain.diseno_base import cota_piso_de
    # especificaciones hospitalarias del uso (v3.22.0): prioridad
    # funcional, ficha técnica y cotas del cuadro MIN/REC
    hospital: Dict[str, Any] = {}
    try:
        from domain.hospital_specs import cargar_specs
        specs = cargar_specs()
    except Exception:  # noqa: BLE001 — sin recurso, sin capa hospitalaria
        specs = None
    if specs is not None:
        hospital = {
            "prioridad": specs.prioridad_de(datos["uso"]),
            "ficha": specs.ficha(datos["uso"]),
            "cotas": specs.item_cotas(datos["uso"]),
        }
    salida = dict(datos)
    salida.update({
        "dna": ficha,
        "dna_tecnico": dict(getattr(dna, "metadata", {}) or {}),
        "hospital": hospital,
        "cota_piso_m": round(cota_piso_de(local), 3),
        "luminarias": len(luminarias),
        "alarma": len(alarmas_n),
        "avisos": avisos,
    })
    return salida


def geometria_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Geometría del local para dibujar su PLANTA (v3.21.0).

    Devuelve ``{boundary, muros, vanos}``:

    * ``muros``: los muros que cierran el local RECORTADOS a sus
      aristas (los muros fusionados por eje son más largos que el
      local: aquí cada tramo es la porción que de verdad lo limita,
      con el papel «exclusivo» o «compartido» según si el tramo es
      también arista de otro local).
    * ``vanos``: con ``p1``/``p2`` (puntos globales en metros) listos
      para dibujarse, más el código del muro que los hospeda.

    Todo en metros, listo para escalar a lápiz o a PDF.
    """
    local = _resolver_local(ctx, ref)
    aristas = cad_tools._aristas(local.boundary or [])
    otros = [s for s in cad_tools._locales_de_nivel(ctx, local.level_id)
             if s.id != local.id]

    def _compartido(medio: PT) -> bool:
        for vecino in otros:
            for a, b in cad_tools._aristas(vecino.boundary or []):
                if cad_tools._dist_segmento(medio, a, b) \
                        <= cad_tools.TOL_ARISTA:
                    return True
        return False

    muros: List[Dict[str, Any]] = []
    muros_por_id: Dict[str, Dict[str, Any]] = {}
    for muro in cad_tools._muros_de_nivel(ctx, local.level_id):
        for q1, q2 in cad_tools._tramos_en_aristas(muro.start, muro.end,
                                                   aristas):
            medio = ((q1[0] + q2[0]) / 2.0, (q1[1] + q2[1]) / 2.0)
            ficha_muro = {
                "id": muro.id, "code": muro.code,
                "start": (round(q1[0], 9), round(q1[1], 9)),
                "end": (round(q2[0], 9), round(q2[1], 9)),
                "thickness_m": float(getattr(muro, "thickness_m", 0.2)
                                     or 0.2),
                "structural": bool(getattr(muro, "structural", False)),
                "papel": "compartido" if _compartido(medio)
                         else "exclusivo",
            }
            muros.append(ficha_muro)
            muros_por_id[muro.id] = ficha_muro
    vanos: List[Dict[str, Any]] = []
    # TODOS los vanos hospedados en muros que tocan el local (el vano
    # manda: su tramo global decide, no el muro entero).
    for muro in cad_tools._muros_de_nivel(ctx, local.level_id):
        for vano in cad_tools._vanos_de_muro(ctx, muro.id):
            # puntos GLOBALES del vano sobre el eje de su muro
            (sx, sy), (ex, ey) = tuple(muro.start), tuple(muro.end)
            largo = math.hypot(ex - sx, ey - sy)
            if largo <= TOL:
                continue
            ux, uy = (ex - sx) / largo, (ey - sy) / largo
            g1 = (sx + ux * float(vano.offset_m),
                  sy + uy * float(vano.offset_m))
            g2 = (sx + ux * (float(vano.offset_m)
                             + float(vano.width_m)),
                  sy + uy * (float(vano.offset_m)
                             + float(vano.width_m)))
            # el vano vive en la porción de muro que limita el local
            for q1, q2 in cad_tools._tramos_en_aristas(g1, g2, aristas):
                medio = ((q1[0] + q2[0]) / 2.0,
                         (q1[1] + q2[1]) / 2.0)
                codigo_muro = ""
                for candidato in muros:
                    if _punto_en_segmento(medio, candidato["start"],
                                          candidato["end"]):
                        codigo_muro = candidato["code"]
                        break
                vanos.append({
                    "kind": str(getattr(vano, "kind", "")),
                    "code": getattr(vano, "code", ""),
                    "wall_id": getattr(vano, "wall_id", ""),
                    "p1": (round(q1[0], 9), round(q1[1], 9)),
                    "p2": (round(q2[0], 9), round(q2[1], 9)),
                    "width_m": float(getattr(vano, "width_m", 0.0)
                                     or 0.0),
                    "height_m": float(getattr(vano, "height_m", 0.0)
                                      or 0.0),
                    "sill_m": float(getattr(vano, "sill_height_m", 0.0)
                                    or 0.0),
                    "swing": str(getattr(vano, "swing", "LEFT")
                                 or "LEFT"),
                    "muro": codigo_muro,
                })
    return {
        "boundary": [tuple(float(v) for v in p)
                     for p in (local.boundary or [])],
        "muros": muros,
        "vanos": vanos,
    }


def _punto_en_segmento(p: PT, a: PT, b: PT, tol: float = 1e-6) -> bool:
    """True si p cae sobre el segmento a-b (tolerancia fina)."""
    return cad_tools._dist_segmento(p, a, b) <= tol


def texto_resumen_completo(datos: Dict[str, Any]) -> str:
    """Las líneas cp1252 del diagnóstico para el cuadro del diálogo."""
    lineas = [f"Diagnóstico de {datos['codigo']} — "
              f"«{datos['nombre'] or datos['uso']}»"]
    dna = datos.get("dna") or {}
    hospital = datos.get("hospital") or {}
    if hospital.get("prioridad"):
        lineas.append(f"  Prioridad funcional: "
                      f"{str(hospital['prioridad']).upper()}")
    if dna:
        lineas.append(f"  Uso: {datos['uso']} ({dna.get('nombre_es', '')})")
    lineas.append(f"  Medidas: {datos['ancho_m']:g} x "
                  f"{datos['fondo_m']:g} m ({datos['area_m2']:g} m2)")
    if dna.get("area_minima"):
        lineas.append(f"  Área mínima del uso: "
                      f"{float(dna['area_minima']):g} m2")
    if datos.get("cota_piso_m"):
        lineas.append(f"  Cota del piso: {datos['cota_piso_m']:g} m")
    lineas.append(f"  Puertas: {', '.join(datos['puertas']) or 'ninguna'}")
    lineas.append(f"  Ventanas: "
                  f"{', '.join(datos['ventanas']) or 'ninguna'}")
    lineas.append(f"  Ventilación: {datos['hueco_ventilacion_m2']:g} m2 "
                  f"de hueco (necesita {datos['hueco_necesario_m2']:g})")
    lineas.append(f"  Mobiliario: {datos['mobiliario']} pieza(s) · "
                  f"Luminarias: {datos.get('luminarias', 0)} · "
                  f"Alarma: {datos.get('alarma', 0)}")
    for aviso in datos["avisos"]:
        lineas.append(f"  · {aviso}")
    return "\n".join(lineas)


def validacion_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Control de validación dimensional del local (§19, v3.22.0).

    Comprueba superficie, ancho, altura, puertas y pasillos contra las
    cotas del uso (cuadro MIN/REC + DNA) y adjunta el checklist del
    documento con lo medido y lo pendiente de cálculo o fabricante.
    """
    from domain.hospital_specs import validar_local as _validar
    return _validar(ctx, ref)


def texto_validacion(informe: Dict[str, Any]) -> str:
    """Informe de validación cp1252 para el diagnóstico o la consola."""
    from domain.hospital_specs import texto_validacion as _texto
    return _texto(informe)


__all__ = [
    "ANCHO_PUERTA_POR_USO", "ANCHO_PUERTA_DEFECTO", "FRACCION_HABITABLE",
    "FRACCION_HUMEDO", "datos_local", "ancho_puerta_por_uso",
    "crear_acceso", "sugerir_ventana", "crear_ventana",
    "redimensionar_local", "regenerar_mobiliario_local", "resumen_texto",
    "cambiar_identidad", "mover_local", "espesor_muros_exclusivos",
    "editar_vano", "quitar_vano", "cota_piso_local",
    "conectar_instalaciones_local", "iluminar_local", "alarmar_local",
    "resumen_completo", "texto_resumen_completo", "geometria_local",
    "validacion_local", "texto_validacion",
]
