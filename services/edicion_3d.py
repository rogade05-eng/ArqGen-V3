"""Edición explícita y validada de entidades seleccionadas en el visor 3D.

Solo se ofrecen propiedades que pueden cambiarse sin reconstruir geometrías
relacionadas. Esto no sustituye comprobaciones normativas ni de colisiones.
"""
from __future__ import annotations

import copy
import math

from services.commands_impl import UpdateEntityCommand, entity_snapshot
from services.architecture_service import ArchitectureService

# (campo, etiqueta, tipo, mínimo, máximo); límites defensivos, no normas.
CAMPOS = {
    "SPACE": [("name", "Nombre", "texto", None, None)],
    "STAIR": [("tipo", "Tipología", "opcion", None, None),
              ("x", "Centro X (m)", "numero", -100000.0, 100000.0),
              ("y", "Centro Y (m)", "numero", -100000.0, 100000.0),
              ("base_offset_m", "Desplazamiento Z desde el nivel (m)", "numero", -100.0, 100.0),
              ("rotation_deg", "Giro (°)", "numero", -3600.0, 3600.0),
              ("width_m", "Ancho (m)", "numero", 0.9, 2.5),
              ("desnivel_m", "Desnivel (m)", "numero", 0.1, 20.0),
              ("contrahuella_m", "Contrahuella objetivo (m)", "numero", 0.05, 1.0),
              ("huella_m", "Huella (m)", "numero", 0.05, 1.0)],
    "WALL": [("thickness_m", "Espesor (m)", "numero", 0.001, 10.0),
             ("height_m", "Altura (m)", "numero", 0.01, 100.0)],
    "DOOR": [("width_m", "Ancho (m)", "numero", 0.01, 100.0),
             ("height_m", "Altura (m)", "numero", 0.01, 100.0),
             ("offset_m", "Distancia desde inicio (m)", "numero", 0.0, 10000.0)],
    "WINDOW": [("width_m", "Ancho (m)", "numero", 0.01, 100.0),
               ("height_m", "Altura (m)", "numero", 0.01, 100.0),
               ("offset_m", "Distancia desde inicio (m)", "numero", 0.0, 10000.0),
               ("sill_height_m", "Antepecho (m)", "numero", 0.0, 100.0)],
    "OPENING": [("width_m", "Ancho (m)", "numero", 0.01, 100.0),
                ("height_m", "Altura (m)", "numero", 0.01, 100.0),
                ("offset_m", "Distancia desde inicio (m)", "numero", 0.0, 10000.0)],
    "FURNITURE": [("name", "Nombre", "texto", None, None),
                  ("x", "Centro X (m)", "numero", -100000.0, 100000.0),
                  ("y", "Centro Y (m)", "numero", -100000.0, 100000.0),
                  ("base_offset_m", "Desplazamiento Z desde el nivel (m)", "numero", -100.0, 100.0),
                  ("rotation_deg", "Giro (°)", "numero", -3600.0, 3600.0),
                  ("width_m", "Ancho (m)", "numero", 0.01, 100.0),
                  ("depth_m", "Fondo (m)", "numero", 0.01, 100.0),
                  ("height_m", "Altura (m)", "numero", 0.01, 100.0)],
    "ROOF": [("pendiente_pct", "Pendiente (%)", "numero", 0.0, 100.0)],
    "RAMP": [("desnivel_m", "Desnivel (m)", "numero", 0.0, 100.0)],
    "HANDRAIL": [("altura_m", "Altura (m)", "numero", 0.01, 10.0),
                 ("altura_secundaria_m", "Altura secundaria (m)", "numero", 0.0, 10.0)],
    "ELEVATOR": [("x", "Centro X (m)", "numero", -100000.0, 100000.0),
                 ("y", "Centro Y (m)", "numero", -100000.0, 100000.0),
                 ("rotation_deg", "Giro (°)", "numero", -3600.0, 3600.0)],
    "PARASOL": [("x", "Centro X (m)", "numero", -100000.0, 100000.0),
                ("y", "Centro Y (m)", "numero", -100000.0, 100000.0),
                ("rotation_deg", "Giro (°)", "numero", -3600.0, 3600.0),
                ("profundidad_m", "Profundidad (m)", "numero", 0.01, 20.0)],
    "SKIN": [("x", "Centro X (m)", "numero", -100000.0, 100000.0),
             ("y", "Centro Y (m)", "numero", -100000.0, 100000.0),
             ("rotation_deg", "Giro (°)", "numero", -3600.0, 3600.0),
             ("length_m", "Longitud (m)", "numero", 0.01, 1000.0),
             ("altura_m", "Altura (m)", "numero", 0.01, 100.0)],
}
TIPOS_VISIBLES = frozenset(CAMPOS) | {"RAMP", "HANDRAIL", "ELEVATOR", "PARASOL", "SKIN", "STAIR"}


def entidad(ctx, tipo: str, uid: str):
    if not isinstance(tipo, str) or tipo not in TIPOS_VISIBLES or not isinstance(uid, str) or not uid:
        raise ValueError("Tipo o identificador de elemento 3D inválido")
    obj = ctx.architecture.get(tipo, uid)
    if obj is None or obj.project_id != ctx.project.id:
        raise ValueError("El elemento ya no existe en este proyecto")
    return obj


def describir(ctx, tipo: str, uid: str) -> dict:
    obj = entidad(ctx, tipo, uid)
    campos = []
    for campo, etiqueta, clase, minimo, maximo in CAMPOS.get(tipo, ()):
        dato = {"campo": campo, "etiqueta": etiqueta, "tipo": clase,
                "valor": (float((obj.metadata or {}).get("editor_base_offset_m", 0.0))
                          if campo == "base_offset_m" else getattr(obj, campo)),
                "min": minimo, "max": maximo}
        if tipo == "STAIR" and campo == "tipo":
            from domain.escaleras import TIPOS
            dato["opciones"] = list(TIPOS)
        campos.append(dato)
    avisos = []
    if tipo == "STAIR":
        avisos = list((obj.metadata or {}).get("avisos_dimensionado") or [])
        if (obj.metadata or {}).get("aviso_ubicacion"):
            avisos.append(obj.metadata["aviso_ubicacion"])
        from services.avisos_3d import avisos_objeto
        avisos.extend(avisos_objeto(ctx, obj))
        avisos.append("Comprobación 3D parcial (muros, vanos, muebles y escaleras); revise estructura, instalaciones, conexión entre niveles y normativa.")
    elif tipo == "FURNITURE":
        from services.avisos_3d import avisos_objeto
        avisos.extend(avisos_objeto(ctx, obj))
        avisos.append("Interferencias parciales: revise estructura, instalaciones y espacios libres.")
    return {"id": obj.id, "tipo": tipo, "codigo": obj.code,
            "nombre": getattr(obj, "name", "") or obj.code,
            "revision": obj.revision, "campos": campos, "avisos": avisos}


def editar(ctx, tipo: str, uid: str, valores: dict, revision: int):
    obj = entidad(ctx, tipo, uid)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision != obj.revision:
        raise ValueError("El elemento cambió; vuelva a seleccionarlo antes de editar")
    if not isinstance(valores, dict) or not valores:
        raise ValueError("Indique al menos una propiedad para editar")
    permitidos = {f[0]: f for f in CAMPOS.get(tipo, ())}
    if not set(valores).issubset(permitidos):
        raise ValueError("Una o más propiedades no son editables para este elemento")
    nuevo = copy.deepcopy(obj)
    for campo, valor in valores.items():
        _, etiqueta, clase, minimo, maximo = permitidos[campo]
        if clase == "opcion":
            from domain.escaleras import TIPOS
            if not isinstance(valor, str) or valor not in TIPOS:
                raise ValueError("Tipología de escalera desconocida")
        elif clase == "texto":
            if not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > 200:
                raise ValueError(f"{etiqueta} debe tener entre 1 y 200 caracteres")
            valor = valor.strip()
        else:
            if isinstance(valor, bool):
                raise ValueError(f"{etiqueta} debe ser un número")
            try:
                valor = float(valor)
            except (TypeError, ValueError):
                raise ValueError(f"{etiqueta} debe ser un número") from None
            if not math.isfinite(valor) or valor < minimo or valor > maximo:
                raise ValueError(f"{etiqueta} debe estar entre {minimo} y {maximo}")
        if campo == "base_offset_m":
            nuevo.metadata = dict(nuevo.metadata or {})
            nuevo.metadata["editor_base_offset_m"] = valor
        else:
            setattr(nuevo, campo, valor)
    if tipo == "STAIR" and set(valores) & {"tipo", "rotation_deg", "width_m", "desnivel_m", "contrahuella_m", "huella_m"}:
        from domain.escaleras import geometria, metadata_geometria
        # Conservar el número de peldaños si solo se gira/cambia la planta:
        # la contrahuella persistida está redondeada y podría añadir uno.
        objetivo = nuevo.contrahuella_m
        n_anterior = (obj.metadata or {}).get("n_contrahuellas")
        if not set(valores) & {"desnivel_m", "contrahuella_m"} and isinstance(n_anterior, int) and n_anterior > 0:
            objetivo = nuevo.desnivel_m / n_anterior
        if nuevo.desnivel_m / objetivo > 200:
            raise ValueError("La escalera excede el límite de 200 contrahuellas")
        geo = geometria(nuevo.tipo, nuevo.desnivel_m, objetivo, nuevo.huella_m,
                        nuevo.width_m, nuevo.rotation_deg)
        nuevo.contrahuella_m = geo["contrahuella_m"]
        nuevo.huella_m = geo["huella_m"]
        meta = dict(nuevo.metadata or {})
        meta.pop("caracol", None)
        meta.update(metadata_geometria(geo))
        nuevo.metadata = meta
    if tipo == "STAIR" and set(valores) & {"x", "y", "base_offset_m"}:
        nuevo.metadata = dict(nuevo.metadata or {})
        nuevo.metadata["modo"] = "manual"
        nuevo.metadata["aviso_ubicacion"] = "La ubicación cambió; compruebe la relación con su recinto."
    if tipo == "ROOF" and "pendiente_pct" in valores and not nuevo.tipologia.startswith("plana"):
        if len(nuevo.footprint) < 3:
            raise ValueError("La cubierta no tiene huella válida")
        from domain.cubiertas import _cumbrera_para
        _, altura = _cumbrera_para(nuevo.footprint, nuevo.tipologia, nuevo.pendiente_pct / 100.0)
        nuevo.altura_cumbrera_m = round(altura, 4)
    if tipo == "RAMP" and "desnivel_m" in valores:
        if nuevo.length_m <= 0:
            raise ValueError("La rampa no tiene longitud válida")
        nuevo.slope_pct = nuevo.desnivel_m / nuevo.length_m * 100.0
    if tipo == "HANDRAIL" and nuevo.altura_secundaria_m > nuevo.altura_m:
        raise ValueError("La altura secundaria no puede superar la principal")
    nuevo.__post_init__()
    if tipo in ("DOOR", "WINDOW", "OPENING"):
        muro = ctx.architecture.get("WALL", nuevo.wall_id)
        if not muro or nuevo.offset_m + nuevo.width_m > muro.length_m + 1e-8:
            raise ValueError("El vano debe caber en la longitud de su muro")
        if nuevo.sill_height_m + nuevo.height_m > muro.height_m + 1e-8:
            raise ValueError("El vano debe caber en la altura de su muro")
    if tipo == "WALL":
        for vano in ctx.architecture.list("OPENING", ctx.project.id):
            if vano.wall_id == uid and vano.sill_height_m + vano.height_m > nuevo.height_m + 1e-8:
                raise ValueError("La altura dejaría un vano fuera del muro")
    antiguo = entity_snapshot(obj)
    nuevo.touch()
    bus = ctx.command_bus
    historial = (list(bus._undo_stack), list(bus._redo_stack), list(bus.executed))
    try:
        bus.execute(UpdateEntityCommand(nuevo), ctx)
        ArchitectureService(ctx)._finish("UPDATE_ENTITY", nuevo, antiguo,
            events=[("OBJECT_UPDATED", {"campos": list(valores)})])
        ctx.commit()
    except Exception:
        ctx.rollback()
        bus._undo_stack[:], bus._redo_stack[:], bus.executed[:] = historial
        raise
    return describir(ctx, tipo, uid)


def crear_escalera(ctx, tipo: str, nivel_indice: int | None = None) -> dict:
    """Añade una escalera, sin borrar ni reemplazar las existentes."""
    from domain.diseno_base import bbox_de, metadata_origen
    from domain.escaleras import TIPOS, FUENTE, geometria, metadata_geometria, sitio_para_escalera
    from domain.model import Stair
    from services.commands_impl import CreateEntityCommand

    if not isinstance(tipo, str) or tipo not in TIPOS:
        raise ValueError("Tipología de escalera desconocida")
    if nivel_indice is not None and (isinstance(nivel_indice, bool) or
                                     not isinstance(nivel_indice, int) or nivel_indice < 0):
        raise ValueError("Nivel de escalera inválido")
    niveles = ctx.architecture.list("LEVEL", ctx.project.id)
    niveles.sort(key=lambda lv: (lv.elevation_m, lv.name))
    indice = nivel_indice if nivel_indice is not None else 0
    if indice >= len(niveles):
        raise ValueError("No existe el nivel solicitado para la escalera")
    nivel = niveles[indice]
    altura = float(nivel.height_m)
    if not math.isfinite(altura) or not 0.1 <= altura <= 20:
        raise ValueError("La altura del nivel debe estar entre 0.1 y 20 m")
    geo = geometria(tipo, altura)
    minx, miny, maxx, maxy = bbox_de(geo["outline"])
    sitio = sitio_para_escalera(ctx, (minx, miny, maxx - minx, maxy - miny), nivel.id)
    espacio = ctx.architecture.get("SPACE", sitio.get("space_id") or "")
    # No vincular con un hueco de otro nivel si el buscador usa su fallback.
    if espacio is not None and espacio.level_id != nivel.id:
        sitio = {"x": 0.0, "y": 0.0, "space_id": "", "modo": "libre",
                 "aviso": "No se encontró un hueco en este nivel: revise y mueva la escalera."}
    meta = metadata_geometria(geo)
    meta.update({"modo": sitio["modo"], "fuente": FUENTE,
                 "aviso_ubicacion": sitio.get("aviso", "")})
    if sitio.get("space_id"):
        meta["space_id"] = sitio["space_id"]
    bus = ctx.command_bus
    historial = (list(bus._undo_stack), list(bus._redo_stack), list(bus.executed))
    try:
        obj = Stair(project_id=ctx.project.id,
                    code=ctx.next_code("ARCHITECTURE", "STAIR"),
                    level_id=nivel.id, space_id=sitio.get("space_id") or "",
                    tipo=tipo, x=float(sitio["x"]), y=float(sitio["y"]),
                    width_m=geo["ancho_m"], desnivel_m=altura,
                    contrahuella_m=geo["contrahuella_m"], huella_m=geo["huella_m"],
                    metadata=metadata_origen("escalera creada en vista 3D", meta))
        bus.execute(CreateEntityCommand(obj), ctx)
        ArchitectureService(ctx)._finish("CREATE_ENTITY", obj,
            events=[("OBJECT_CREATED", {})])
        ctx.commit()
    except Exception:
        ctx.rollback()
        bus._undo_stack[:], bus._redo_stack[:], bus.executed[:] = historial
        raise
    return describir(ctx, "STAIR", obj.id)


def borrar_escalera(ctx, uid: str, revision: int) -> None:
    """Borra una única escalera con revisión, auditoría y transacción."""
    from services.commands_impl import DeleteEntityCommand
    obj = entidad(ctx, "STAIR", uid)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision != obj.revision:
        raise ValueError("El elemento cambió; vuelva a seleccionarlo antes de borrar")
    antes = entity_snapshot(obj)
    bus = ctx.command_bus
    historial = (list(bus._undo_stack), list(bus._redo_stack), list(bus.executed))
    svc = ArchitectureService(ctx)
    try:
        bus.execute(DeleteEntityCommand("STAIR", uid), ctx)
        svc._audit("DELETE_ENTITY", "STAIR", uid, antes, None)
        ctx.emit("OBJECT_DELETED", {"id": uid, "type": "STAIR", "code": obj.code})
        svc._invalidate_object(uid)
        ctx.commit()
    except Exception:
        ctx.rollback()
        bus._undo_stack[:], bus._redo_stack[:], bus.executed[:] = historial
        raise
