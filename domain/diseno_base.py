"""Base compartida de la CONCEPCIÓN DE ESPACIOS (v3.15.0).

Los tres motores nuevos (mobiliario, cubiertas y accesibilidad) crean
entidades de arquitectura por los caminos oficiales: CommandBus con
instantánea (undo persistente §77), auditoría §71, eventos §75 e
invalidación incremental de QTO §74. Este módulo concentra ese andamio
para no triplicarlo, junto con la geometría mínima común (bbox y
huella) y las marcas de origen que después respeta la regeneración.

Cero Tk y cero dependencias: igual que cad_tools, el mismo motor sirve
a la GUI, a la CLI y a las pruebas. Los mensajes son 100 % codificables
en cp1252 (disciplina v3.13.1: nada de flechas ni emojis).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.audit.models import make_audit_event
from services.commands_impl import CreateEntityCommand, entity_snapshot
from services.architecture_service import ArchitectureService

PT = Tuple[float, float]

ORIGEN_BASE = "diseño de espacios v3.15.0"
MARCA_MANO = "editada_a_mano"   # espejo de ui.cad_tools.MARCA_MANO

# Locales del trazado que NO reciben mobiliario (infraestructura).
TIPOS_ESPECIALES: Tuple[str, ...] = ("CORRIDOR", "PATIO", "STAIR", "CORE")


# ---------------------------------------------------------------------------
# alta / baja de entidades por los caminos oficiales
# ---------------------------------------------------------------------------

def alta_entidad(ctx: Any, entity: Any,
                 eventos: Sequence[str] = ("OBJECT_CREATED",)) -> Any:
    """Crea la entidad con auditoría, eventos e invalidación de QTO.

    Es el patrón de ArchitectureService._finish aplicado a los tipos
    nuevos: el undo persistente (journal CREATE_ENTITY) sale gratis.
    """
    entity.touch()
    ctx.command_bus.execute(CreateEntityCommand(entity), ctx)
    evento_auditoria = make_audit_event(
        ctx.user, entity.id, entity.ENTITY_TYPE, "CREATE_ENTITY",
        None, entity_snapshot(entity))
    ctx.audit_repo.append(evento_auditoria)
    for tipo in eventos:
        ctx.emit(tipo, {"id": entity.id, "type": entity.ENTITY_TYPE,
                        "code": entity.code})
    ctx.calculations_repo.mark_stale_for_object(entity.id)
    ctx.quantities_repo.mark_stale_for_object(entity.id)
    return entity


def baja_entidad(ctx: Any, entity_type: str, entity_id: str) -> None:
    """Baja por el servicio oficial (cascadas, auditoría y QTO)."""
    ArchitectureService(ctx).delete_entity(entity_type, entity_id)


def lista_tipos(ctx: Any, entity_type: str) -> List[Any]:
    """Entidades del proyecto de un tipo (protegido ante proyectos viejos)."""
    try:
        return list(ctx.architecture.list(entity_type, ctx.project.id))
    except Exception:  # noqa: BLE001 - base sin migrar aún
        return []


def metadata_origen(nota: str, extra: Optional[Dict[str, Any]] = None
                    ) -> Dict[str, Any]:
    """Metadata estándar de las piezas generadas por el diseño."""
    meta: Dict[str, Any] = {"origen": ORIGEN_BASE}
    if nota:
        meta["nota"] = nota
    if extra:
        meta.update(extra)
    return meta


def _metadata_of(entity: Any) -> Dict[str, Any]:
    meta = getattr(entity, "metadata", None)
    return meta if isinstance(meta, dict) else {}


def es_generado_diseno(entity: Any) -> bool:
    """La pieza nació de los motores de diseño (purgable al regenerar)."""
    return str(_metadata_of(entity).get("origen", "")).startswith(ORIGEN_BASE)


def es_editado_a_mano(entity: Any) -> bool:
    return bool(_metadata_of(entity).get(MARCA_MANO))


# ---------------------------------------------------------------------------
# espacios del proyecto
# ---------------------------------------------------------------------------

def espacios_objetivo(ctx: Any,
                      space_ids: Optional[Iterable[str]] = None,
                      nivel_id: str = "",
                      con_especiales: bool = False) -> List[Any]:
    """Locales del proyecto (o un subconjunto) aptos para diseño.

    Excluye por defecto los locales del trazado (pasillo, patio,
    escalera y núcleo): el mobiliario y las barras de apoyo viven en
    los locales USUALES.
    """
    espacios = lista_tipos(ctx, "SPACE")
    elegidos: List[Any] = []
    quiero = {s for s in (space_ids or ()) if s}
    for espacio in espacios:
        if quiero and espacio.id not in quiero:
            continue
        if nivel_id and espacio.level_id != nivel_id:
            continue
        if not con_especiales \
                and str(espacio.space_type or "").upper() in TIPOS_ESPECIALES:
            continue
        if len(getattr(espacio, "boundary", []) or []) < 3:
            continue
        elegidos.append(espacio)
    elegidos.sort(key=lambda s: (str(getattr(s, "code", "")),))
    return elegidos


def cota_piso_de(espacio: Any) -> float:
    """Cota del piso del local (terreno irregular del asistente)."""
    req = _metadata_of(espacio).get("requerimientos", {})
    arquitectonicos = req.get("arquitectonicos", {}) \
        if isinstance(req, dict) else {}
    try:
        return float(arquitectonicos.get("cota_piso_m", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# geometría mínima compartida
# ---------------------------------------------------------------------------

def bbox_de(boundary: Sequence[PT]) -> Tuple[float, float, float, float]:
    xs = [float(p[0]) for p in boundary]
    ys = [float(p[1]) for p in boundary]
    return (min(xs), min(ys), max(xs), max(ys))


def _area_firmada(puntos: Sequence[PT]) -> float:
    total = 0.0
    n = len(puntos)
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def poligono_rectangulo(cx: float, cy: float, ancho: float, fondo: float,
                        rotacion_deg: float = 0.0) -> List[PT]:
    """Esquinas del rectángulo (ancho × fondo) girado alrededor del centro."""
    hw, hf = ancho / 2.0, fondo / 2.0
    esquinas = [(-hw, -hf), (hw, -hf), (hw, hf), (-hw, hf)]
    if abs(rotacion_deg % 360.0) <= 1e-9:
        return [(cx + ex, cy + ey) for ex, ey in esquinas]
    ang = math.radians(rotacion_deg)
    cos_a, sen_a = math.cos(ang), math.sin(ang)
    return [(cx + ex * cos_a - ey * sen_a, cy + ex * sen_a + ey * cos_a)
            for ex, ey in esquinas]


def hay_interseccion(rect_a: Sequence[PT], rect_b: Sequence[PT]) -> bool:
    """Test de solape entre dos rectángulos (SAT de ejes del primero:
    todos son rectángulos alineados o girados 90°, basta AABB)."""
    ax = [p[0] for p in rect_a]
    ay = [p[1] for p in rect_a]
    bx = [p[0] for p in rect_b]
    by = [p[1] for p in rect_b]
    return not (max(ax) <= min(bx) + 1e-9 or min(ax) >= max(bx) - 1e-9
                or max(ay) <= min(by) + 1e-9 or min(ay) >= max(by) - 1e-9)


def dentro_de_recinto(rect: Sequence[PT],
                      recinto: Tuple[float, float, float, float],
                      holgura: float = 0.011) -> bool:
    """El rectángulo (AABB del polígono) cabe en el recinto con holgura."""
    minx, miny, maxx, maxy = recinto
    xs = [p[0] for p in rect]
    ys = [p[1] for p in rect]
    return (min(xs) >= minx - holgura and max(xs) <= maxx + holgura
            and min(ys) >= miny - holgura and max(ys) <= maxy + holgura)


def texto_resumen(resumen: Dict[str, Any]) -> str:
    """Una línea, amable y cp1252-segura, para la barra de estado."""
    partes: List[str] = [str(resumen.get("operacion", "operación"))]
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} pieza(s)")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    if resumen.get("conteo"):
        partes.append(", ".join(
            f"{clave} x{n}" for clave, n in
            sorted(resumen["conteo"].items())[:4]))
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    for aviso in resumen.get("avisos", []):
        partes.append(f"aviso: {aviso}")
    return " · ".join(partes)


def cerrar_qto(ctx: Any, resumen: Dict[str, Any]) -> Dict[str, Any]:
    """Cierra la operación: recálculo incremental de QTO (patrón
    cad_tools.finalizar). El que llama hace ctx.commit()."""
    from services.quantity_service import QuantityService
    resumen["qto"] = QuantityService(ctx).compute_all().to_dict()
    return resumen


__all__ = [
    "ORIGEN_BASE", "MARCA_MANO", "TIPOS_ESPECIALES", "PT",
    "alta_entidad", "baja_entidad", "lista_tipos", "metadata_origen",
    "es_generado_diseno", "es_editado_a_mano", "espacios_objetivo",
    "cota_piso_de", "bbox_de", "poligono_rectangulo", "hay_interseccion",
    "dentro_de_recinto", "texto_resumen", "cerrar_qto",
]
