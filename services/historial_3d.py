"""Deshacer/rehacer limitado a ediciones y escaleras creadas en esta sesión 3D."""
from __future__ import annotations

import copy

from services.architecture_service import ArchitectureService
from services.commands_impl import (CreateEntityCommand, DeleteEntityCommand,
                                    UpdateEntityCommand, entity_snapshot,
                                    snapshot_to_entity)


def registrar(entrada: dict, antes, despues) -> None:
    """Registra solo mutaciones completadas; una nueva edición descarta redo."""
    undo = entrada.setdefault("undo_3d", [])
    undo.append({"antes": copy.deepcopy(antes), "despues": copy.deepcopy(despues),
                 "revision_maxima": (despues or antes)["revision"]})
    del undo[:-100]
    entrada["redo_3d"] = []


def cambiar(entrada: dict, rehacer: bool = False) -> dict:
    ctx = entrada["ctx"]
    origen = entrada.setdefault("redo_3d" if rehacer else "undo_3d", [])
    destino = entrada.setdefault("undo_3d" if rehacer else "redo_3d", [])
    if not origen:
        raise ValueError("No hay cambios 3D para " + ("rehacer" if rehacer else "deshacer"))
    registro = origen[-1]
    objetivo = registro["despues"] if rehacer else registro["antes"]
    referencia = registro["despues"] or registro["antes"]
    tipo, uid = referencia["ENTITY_TYPE"], referencia["id"]
    actual = ctx.architecture.get(tipo, uid)
    if actual is not None and actual.project_id != ctx.project.id:
        raise ValueError("El elemento no pertenece al proyecto")
    # Estado esperado justo antes de aplicar undo/redo. Creaciones y
    # borrados son transiciones inversas; las ediciones requieren existencia.
    esperado = registro["antes"] if rehacer else registro["despues"]
    if (actual is None) != (esperado is None):
        raise ValueError("El elemento cambió fuera del historial 3D")
    if objetivo is None and tipo != "STAIR":
        raise ValueError("Solo se pueden borrar escaleras desde el historial 3D")
    antes = entity_snapshot(actual) if actual else None
    bus = ctx.command_bus
    historial = (list(bus._undo_stack), list(bus._redo_stack), list(bus.executed))
    revision_maxima = max(registro["revision_maxima"], actual.revision if actual else 0)
    svc = ArchitectureService(ctx)
    try:
        if objetivo is None:
            bus.execute(DeleteEntityCommand(tipo, uid), ctx)
            despues = None
            evento = "OBJECT_DELETED"
        else:
            nuevo = snapshot_to_entity(copy.deepcopy(objetivo))
            nuevo.revision = revision_maxima
            nuevo.touch()  # nunca reutilizar una revisión de un editor obsoleto
            if actual is None:
                bus.execute(CreateEntityCommand(nuevo), ctx)
                evento = "OBJECT_CREATED"
            else:
                bus.execute(UpdateEntityCommand(nuevo), ctx)
                evento = "OBJECT_UPDATED"
            despues = entity_snapshot(nuevo)
            revision_maxima = nuevo.revision
        svc._audit("REDO_3D" if rehacer else "UNDO_3D", tipo, uid, antes, despues)
        ctx.emit(evento, {"id": uid, "type": tipo, "code": referencia.get("code", "")})
        svc._invalidate_object(uid)
        ctx.commit()
    except Exception:
        ctx.rollback()
        bus._undo_stack[:], bus._redo_stack[:], bus.executed[:] = historial
        raise
    registro["revision_maxima"] = revision_maxima
    destino.append(origen.pop())
    entrada["editado"] = True
    return {"tipo": tipo, "elemento_id": uid, "existe": objetivo is not None,
            "deshacer_disponible": bool(entrada.get("undo_3d")),
            "rehacer_disponible": bool(entrada.get("redo_3d"))}
