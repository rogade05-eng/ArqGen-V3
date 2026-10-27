"""TIPOS DE PUERTAS Y VENTANAS (v3.19.0).

El vano deja de ser un simple hueco: cada puerta y ventana lleva su
TIPOLOGÍA de funcionamiento — abatible, doble hoja, corredera,
plegable, vaivén o pivote en puertas; practicable, oscilobatiente,
abatible, proyectante, corredera, guillotina, fija o pivotante en
ventanas — con las reglas del libro:

* ``CATALOGO_PUERTAS`` / ``CATALOGO_VENTANAS``: hojas, porcentaje de
  apertura útil (lo que realmente ventila y pasa), símbolo de planos
  y uso recomendado; el libro aconseja la medida por uso (camilla en
  salud 1.20 m, interior cómoda 0.90 m, antepecho 0.90 m).
* ``asignar_tipos``: aplica una tipología a TODAS las puertas o
  ventanas del nivel (o del proyecto) por los caminos oficiales —
  auditoría, undo persistente e invalidación — dejando la metadata
  ``abertura`` con tipo, hojas y apertura.
* ``simbolo_puntos``: la polilínea de planos de cada tipo (arco de
  giro, doble hoja, corredera, zigzag plegable...) para que el lienzo
  2D dibuje el vano como manda la representación arquitectónica.
* ``resumen_aberturas``: recuento por tipología para la salida y la
  memoria.

Cero Tk y cero dependencias. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.audit.models import make_audit_event
from core.errors import DomainError
from domain.diseno_base import lista_tipos
from services.commands_impl import UpdateEntityCommand, entity_snapshot

PT = Tuple[float, float]

# error propio: ARQ-ABE-001 tipo de puerta desconocido
# error propio: ARQ-ABE-002 tipo de ventana desconocido

FUENTE = ("Neufert — puertas y ventanas: apertura y medidas por uso "
          "(5.ª ed.)")

# -- catálogos ---------------------------------------------------------------
# apertura_pct = paso libre / ventilación útil respecto del vano completo
CATALOGO_PUERTAS: Dict[str, Dict[str, Any]] = {
    "abatible": {"etiqueta": "abatible de una hoja", "hojas": 1,
                 "apertura_pct": 100.0, "simbolo": "abatible",
                 "uso": "interior cómoda (0.90 m)"},
    "doble_hoja": {"etiqueta": "abatible de dos hojas", "hojas": 2,
                   "apertura_pct": 100.0, "simbolo": "doble",
                   "uso": "entrada principal y salas (1.20-1.60 m)"},
    "corredera": {"etiqueta": "corredera", "hojas": 2,
                  "apertura_pct": 50.0, "simbolo": "corredera",
                  "uso": "armarios, división de espacios, transparencias"},
    "plegable": {"etiqueta": "plegable (acordeón)", "hojas": 2,
                 "apertura_pct": 85.0, "simbolo": "plegable",
                 "uso": "trasteros y locales donde no cabe el giro"},
    "vaiven": {"etiqueta": "vaivén (de doble oscilación)", "hojas": 1,
               "apertura_pct": 90.0, "simbolo": "vaiven",
               "uso": "cocinas de servicio, bares, tránsito con manos ocupadas"},
    "pivote": {"etiqueta": "de pivote central", "hojas": 1,
               "apertura_pct": 75.0, "simbolo": "pivote",
               "uso": "entradas de diseño, hojas grandes de vidrio"},
}

CATALOGO_VENTANAS: Dict[str, Dict[str, Any]] = {
    "practicable": {"etiqueta": "practicable (batiente)", "hojas": 1,
                    "apertura_pct": 100.0, "simbolo": "practicable",
                    "antepecho_m": 0.90,
                    "uso": "la clásica: abre al interior completa"},
    "oscilobatiente": {"etiqueta": "oscilobatiente", "hojas": 1,
                       "apertura_pct": 60.0, "simbolo": "oscilobatiente",
                       "antepecho_m": 0.90,
                       "uso": "ventila inclinada o abre batiente (dos modos)"},
    "abatible": {"etiqueta": "abatible (inclinación superior)", "hojas": 1,
                 "apertura_pct": 45.0, "simbolo": "abatible",
                 "antepecho_m": 1.00,
                 "uso": "baños y cocinas: ventila sin abrir el vano"},
    "proyectante": {"etiqueta": "proyectante (abre al exterior)", "hojas": 1,
                    "apertura_pct": 50.0, "simbolo": "proyectante",
                    "antepecho_m": 0.90,
                    "uso": "fachadas modernas: bandeja inclinada afuera"},
    "corredera": {"etiqueta": "corredera", "hojas": 2,
                  "apertura_pct": 50.0, "simbolo": "corredera",
                  "antepecho_m": 0.00,
                  "uso": "balcones y grandes cristales, nunca invade"},
    "guillotina": {"etiqueta": "guillotina (sube y baja)", "hojas": 2,
                   "apertura_pct": 50.0, "simbolo": "guillotina",
                   "antepecho_m": 0.90,
                   "uso": "clásica y ventanas de barra o café"},
    "fija": {"etiqueta": "fija (fija iluminante)", "hojas": 1,
             "apertura_pct": 0.0, "simbolo": "fija",
             "antepecho_m": 0.00,
             "uso": "iluminación pura: claraboyas y paños fijos"},
    "pivotante": {"etiqueta": "pivotante (eje central)", "hojas": 1,
                  "apertura_pct": 80.0, "simbolo": "pivotante",
                  "antepecho_m": 0.90,
                  "uso": "hojas grandes que giran sobre su eje"},
}


def tipos_puerta() -> Tuple[str, ...]:
    """Claves del catálogo de puertas (orden estable)."""
    return tuple(CATALOGO_PUERTAS)


def tipos_ventana() -> Tuple[str, ...]:
    """Claves del catálogo de ventanas (orden estable)."""
    return tuple(CATALOGO_VENTANAS)


def datos_puerta(tipo: str) -> Dict[str, Any]:
    """Ficha del tipo de puerta (ARQ-ABE-001 si no existe)."""
    datos = CATALOGO_PUERTAS.get(str(tipo or "").strip())
    if not datos:
        raise DomainError(
            message=f"Tipo de puerta desconocido: {tipo}",
            code="ARQ-ABE-001",
            context={"tipo": tipo, "permitidos": list(CATALOGO_PUERTAS)},
            suggested_action="Usa uno de: " + ", ".join(CATALOGO_PUERTAS))
    return dict(datos, tipo=tipo)


def datos_ventana(tipo: str) -> Dict[str, Any]:
    """Ficha del tipo de ventana (ARQ-ABE-002 si no existe)."""
    datos = CATALOGO_VENTANAS.get(str(tipo or "").strip())
    if not datos:
        raise DomainError(
            message=f"Tipo de ventana desconocido: {tipo}",
            code="ARQ-ABE-002",
            context={"tipo": tipo, "permitidos": list(CATALOGO_VENTANAS)},
            suggested_action="Usa uno de: " + ", ".join(CATALOGO_VENTANAS))
    return dict(datos, tipo=tipo)


def puerta_para_uso(uso: str) -> Tuple[float, float]:
    """(ancho, alto) aconsejados por el uso (Neufert)."""
    try:
        from domain.neufert import get_registry
        return get_registry().door_for(uso)
    except Exception:  # noqa: BLE001 — sin catálogo, cómoda general
        return (0.90, 2.10)


def _metadata_abertura(entity: Any) -> Dict[str, Any]:
    meta = getattr(entity, "metadata", None)
    valor = meta.get("abertura") if isinstance(meta, dict) else None
    return valor if isinstance(valor, dict) else {}


def tipo_de(entity: Any) -> str:
    """Tipo de abertura guardado en la metadata (vacío si no lleva)."""
    return str(_metadata_abertura(entity).get("tipo", ""))


# ---------------------------------------------------------------------------
# asignación por los caminos oficiales
# ---------------------------------------------------------------------------

def _actualizar(ctx: Any, entity: Any, ficha: Dict[str, Any]) -> None:
    """Metadata «abertura» con auditoría, undo persistente y eventos."""
    viejo = entity_snapshot(entity)
    meta = dict(getattr(entity, "metadata", None) or {})
    meta["abertura"] = {"tipo": ficha["tipo"],
                        "hojas": int(ficha["hojas"]),
                        "apertura_pct": float(ficha["apertura_pct"]),
                        "simbolo": ficha["simbolo"]}
    entity.metadata = meta
    entity.touch()
    ctx.command_bus.execute(UpdateEntityCommand(entity), ctx)
    evento = make_audit_event(
        ctx.user, entity.id, entity.ENTITY_TYPE, "UPDATE_ENTITY",
        viejo, entity_snapshot(entity))
    ctx.audit_repo.append(evento)
    ctx.emit("OBJECT_UPDATED", {"id": entity.id,
                                "type": entity.ENTITY_TYPE,
                                "code": entity.code})
    ctx.calculations_repo.mark_stale_for_object(entity.id)
    ctx.quantities_repo.mark_stale_for_object(entity.id)


def asignar_tipos(ctx: Any, kind: str, tipo: str,
                  nivel_id: str = "") -> Dict[str, Any]:
    """Aplica la tipología a TODAS las puertas o ventanas del nivel.

    ``kind`` es DOOR o WINDOW; ``nivel_id`` vacío = todo el proyecto.
    Idempotente: reasignar el mismo tipo reescribe la metadata sin
    duplicar nada. Devuelve el recuento por nivel y los avisos.
    """
    if kind not in ("DOOR", "WINDOW"):
        raise DomainError(
            message=f"Solo se tipifican DOOR o WINDOW (pedido: {kind})",
            code="ARQ-ABE-003", context={"kind": kind})
    ficha = (datos_puerta(tipo) if kind == "DOOR"
             else datos_ventana(tipo))
    abiertas = [a for a in lista_tipos(ctx, kind)
                if not nivel_id or a.level_id == nivel_id]
    if not abiertas:
        raise DomainError(
            message=("No hay " + ("puertas" if kind == "DOOR" else "ventanas")
                     + ("" if not nivel_id else " en ese nivel")
                     + " que tipificar"),
            code="ARQ-ABE-004",
            context={"kind": kind, "nivel_id": nivel_id},
            suggested_action="Dibuja primero los vanos con el asistente "
                             "o las herramientas CAD")
    por_nivel: Dict[str, int] = {}
    for vano in abiertas:
        _actualizar(ctx, vano, ficha)
        por_nivel[vano.level_id] = por_nivel.get(vano.level_id, 0) + 1
    return {"operacion": "aberturas", "kind": kind, "tipo": tipo,
            "etiqueta": ficha["etiqueta"], "hojas": ficha["hojas"],
            "apertura_pct": ficha["apertura_pct"],
            "asignadas": len(abiertas), "por_nivel": por_nivel,
            "codes": [v.code for v in abiertas], "avisos": []}


def quitar_tipos(ctx: Any, kind: str, nivel_id: str = "") -> int:
    """Limpia la metadata de abertura (los vanos siguen existiendo)."""
    if kind not in ("DOOR", "WINDOW"):
        raise DomainError(
            message=f"Solo DOOR o WINDOW (pedido: {kind})",
            code="ARQ-ABE-003", context={"kind": kind})
    total = 0
    for vano in lista_tipos(ctx, kind):
        if nivel_id and vano.level_id != nivel_id:
            continue
        if not _metadata_abertura(vano):
            continue
        viejo = entity_snapshot(vano)
        meta = dict(getattr(vano, "metadata", None) or {})
        meta.pop("abertura", None)
        vano.metadata = meta
        vano.touch()
        ctx.command_bus.execute(UpdateEntityCommand(vano), ctx)
        evento = make_audit_event(
            ctx.user, vano.id, vano.ENTITY_TYPE, "UPDATE_ENTITY",
            viejo, entity_snapshot(vano))
        ctx.audit_repo.append(evento)
        ctx.emit("OBJECT_UPDATED", {"id": vano.id,
                                    "type": vano.ENTITY_TYPE,
                                    "code": vano.code})
        total += 1
    return total


def resumen_aberturas(ctx: Any, nivel_id: str = "") -> Dict[str, Any]:
    """Recuento de vanos por tipología (y los sin tipo)."""
    salida: Dict[str, Any] = {"puertas": {}, "ventanas": {},
                              "sin_tipo": {"DOOR": 0, "WINDOW": 0}}
    for kind, clave in (("DOOR", "puertas"), ("WINDOW", "ventanas")):
        for vano in lista_tipos(ctx, kind):
            if nivel_id and vano.level_id != nivel_id:
                continue
            tipo = tipo_de(vano)
            if tipo:
                salida[clave][tipo] = salida[clave].get(tipo, 0) + 1
            else:
                salida["sin_tipo"][kind] += 1
    return salida


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con la asignación (o el recuento)."""
    if resumen.get("asignadas") is not None:
        texto = (f"{resumen['asignadas']} "
                 + ("puerta(s)" if resumen.get("kind") == "DOOR"
                    else "ventana(s)")
                 + f" tipificadas como {resumen.get('etiqueta', '')}"
                 f" ({resumen.get('hojas', 1)} hoja(s), apertura "
                 f"{resumen.get('apertura_pct', 0):.0f} %)")
    else:
        texto = "Recuento de aberturas"
    partes = [texto]
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    return " · ".join(partes)


def recuento_texto(resumen: Dict[str, Any]) -> List[str]:
    """Recuento por tipología en líneas cp1252 (GUI y CLI)."""
    lineas = ["Puertas:"]
    puertas = resumen.get("puertas") or {}
    lineas += [f"  {datos_puerta(t)['etiqueta']}: {n}"
               for t, n in sorted(puertas.items())] \
        or ["  (ninguna tipificada)"]
    sin_p = resumen.get("sin_tipo", {}).get("DOOR", 0)
    lineas.append(f"  sin tipo: {sin_p}")
    lineas.append("Ventanas:")
    ventanas = resumen.get("ventanas") or {}
    lineas += [f"  {datos_ventana(t)['etiqueta']}: {n}"
               for t, n in sorted(ventanas.items())] \
        or ["  (ninguna tipificada)"]
    sin_v = resumen.get("sin_tipo", {}).get("WINDOW", 0)
    lineas.append(f"  sin tipo: {sin_v}")
    return lineas


# ---------------------------------------------------------------------------
# símbolos de planos (el lienzo 2D dibuja estas polilíneas)
# ---------------------------------------------------------------------------

def _arco(hinge: PT, radio: float, ang0: float, ang1: float,
          pasos: int = 8) -> List[PT]:
    """Arco de giro de la hoja (aproximado con segmentos)."""
    return [(hinge[0] + radio * math.cos(ang0 + (ang1 - ang0) * i / pasos),
             hinge[1] + radio * math.sin(ang0 + (ang1 - ang0) * i / pasos))
            for i in range(pasos + 1)]


def _reborde(centro: PT, u: PT, n: PT, ancho: float,
             offset: float) -> List[PT]:
    """Línea del vano en el plano del muro, separada ``offset``."""
    half = ancho / 2.0
    p1 = (centro[0] - u[0] * half + n[0] * offset,
          centro[1] - u[1] * half + n[1] * offset)
    p2 = (centro[0] + u[0] * half + n[0] * offset,
          centro[1] + u[1] * half + n[1] * offset)
    return [p1, p2]


def simbolo_puntos(tipo: str, es_puerta: bool, centro: PT, u: PT,
                   ancho: float) -> List[List[PT]]:
    """Polilíneas del símbolo 2D para la tipología (en mundo).

    ``u`` es el rumbo del muro; el lado de apertura sale de la normal
    izquierda (-u[1], u[0]). Sin tipo conocido, dibuja el borde simple
    (una sola línea): el vano nunca queda sin representar.
    """
    half = ancho / 2.0
    n = (-u[1], u[0])                     # normal (lado de apertura)
    if es_puerta:
        ficha = CATALOGO_PUERTAS.get(tipo)
    else:
        ficha = CATALOGO_VENTANAS.get(tipo)
    if not ficha:
        return [_reborde(centro, u, n, ancho, 0.0)]
    simbolo = ficha["simbolo"]
    trazos: List[List[PT]] = []
    if simbolo in ("abatible",):
        p0 = _reborde(centro, u, n, ancho, 0.0)[0]      # bisagra izquierda
        hoja = [(p0[0] + n[0] * ancho, p0[1] + n[1] * ancho)]
        ang0 = math.atan2(n[1], n[0])
        trazos.append([p0, hoja[0]])
        trazos.append(_arco(p0, ancho, ang0, ang0 + math.pi / 2.0))
    elif simbolo == "doble":
        p0 = _reborde(centro, u, n, ancho, 0.0)[0]
        p1 = _reborde(centro, u, n, ancho, 0.0)[1]
        for bisagra, lado in ((p0, 1.0), (p1, -1.0)):
            hoja_len = ancho / 2.0
            punta = (bisagra[0] + n[0] * hoja_len * lado
                     + u[0] * 0.0, bisagra[1] + n[1] * hoja_len * lado)
            punta = (bisagra[0] + n[0] * hoja_len,
                     bisagra[1] + n[1] * hoja_len)
            trazos.append([bisagra, punta])
            ang0 = math.atan2(n[1] * lado, n[0] * lado)
            ang1 = ang0 + math.pi / 2.0 * lado
            trazos.append(_arco(bisagra, hoja_len, ang0, ang1))
    elif simbolo == "corredera":
        trazos.append(_reborde(centro, u, n, ancho * 0.96, +0.03))
        trazos.append(_reborde((centro[0] + u[0] * ancho * 0.46,
                                centro[1] + u[1] * ancho * 0.46),
                               u, n, ancho * 0.96, +0.07))
    elif simbolo == "plegable":
        p0 = _reborde(centro, u, n, ancho, 0.0)[0]
        p1 = _reborde(centro, u, n, ancho, 0.0)[1]
        m0 = (p0[0] + n[0] * ancho * 0.55 + u[0] * ancho * 0.25,
              p0[1] + n[1] * ancho * 0.55 + u[1] * ancho * 0.25)
        m1 = (p1[0] + n[0] * ancho * 0.55 - u[0] * ancho * 0.25,
              p1[1] + n[1] * ancho * 0.55 - u[1] * ancho * 0.25)
        trazos.append([p0, m0, m1, p1])
    elif simbolo == "vaiven":
        p0 = _reborde(centro, u, n, ancho, 0.0)[0]
        for lado in (1.0, -1.0):
            hoja = (p0[0] + n[0] * ancho * 0.7 * lado
                    + u[0] * ancho * 0.7 * lado,
                    p0[1] + n[1] * ancho * 0.7 * lado
                    + u[1] * ancho * 0.7 * lado)
            trazos.append([p0, hoja])
        trazos.append(_arco(p0, ancho,
                            math.atan2(n[1], n[0]),
                            math.atan2(n[1], n[0]) + math.pi))
    elif simbolo == "pivote":
        c = centro
        hoja = (c[0] + u[0] * ancho * 0.42 + n[0] * ancho * 0.42,
                c[1] + u[1] * ancho * 0.42 + n[1] * ancho * 0.42)
        hoja2 = (c[0] - u[0] * ancho * 0.42 + n[0] * ancho * 0.10,
                 c[1] - u[1] * ancho * 0.42 + n[1] * ancho * 0.10)
        trazos.append([hoja2, c, hoja])
    elif simbolo in ("practicable",):
        trazos.append(_reborde(centro, u, n, ancho, 0.0))
        p0 = _reborde(centro, u, n, ancho, 0.0)[0]
        medio = (centro[0] + n[0] * ancho * 0.25, centro[1] + n[1] * ancho * 0.25)
        trazos.append([p0, medio, (p0[0] + u[0] * ancho, p0[1] + u[1] * ancho)])
    elif simbolo in ("oscilobatiente", "abatible", "proyectante"):
        trazos.append(_reborde(centro, u, n, ancho, 0.0))
        half2 = ancho * 0.28
        apex = (centro[0] + n[0] * half2, centro[1] + n[1] * half2)
        b1 = (centro[0] - u[0] * ancho * 0.3, centro[1] - u[1] * ancho * 0.3)
        b2 = (centro[0] + u[0] * ancho * 0.3, centro[1] + u[1] * ancho * 0.3)
        trazos.append([b1, apex, b2])
    elif simbolo == "guillotina":
        trazos.append(_reborde((centro[0] - u[0] * ancho * 0.22,
                                centro[1] - u[1] * ancho * 0.22),
                               u, n, ancho * 0.56, 0.0))
        trazos.append(_reborde((centro[0] + u[0] * ancho * 0.22,
                                centro[1] + u[1] * ancho * 0.22),
                               u, n, ancho * 0.56, 0.0))
    elif simbolo == "fija":
        trazos.append(_reborde(centro, u, n, ancho, 0.0))
        p1 = _reborde(centro, u, n, ancho, 0.0)[0]
        p2 = _reborde(centro, u, n, ancho, 0.0)[1]
        trazos.append([p1, p2])
    elif simbolo == "pivotante":
        trazos.append(_reborde(centro, u, n, ancho, 0.0))
        c = centro
        hoja = (c[0] + u[0] * ancho * 0.35 + n[0] * ancho * 0.35,
                c[1] + u[1] * ancho * 0.35 + n[1] * ancho * 0.35)
        hoja2 = (c[0] - u[0] * ancho * 0.35 + n[0] * ancho * 0.12,
                 c[1] - u[1] * ancho * 0.35 + n[1] * ancho * 0.12)
        trazos.append([hoja2, c, hoja])
    else:
        trazos.append(_reborde(centro, u, n, ancho, 0.0))
    return trazos


def tabla_texto() -> List[str]:
    """Los dos catálogos en líneas cp1252 (GUI y CLI)."""
    lineas = ["Puertas (Neufert, referencia):"]
    for tipo, ficha in CATALOGO_PUERTAS.items():
        lineas.append(f"  {tipo:<12} {ficha['hojas']} hoja(s) · apertura "
                      f"{ficha['apertura_pct']:.0f} % · {ficha['uso']}")
    lineas.append("Ventanas:")
    for tipo, ficha in CATALOGO_VENTANAS.items():
        lineas.append(f"  {tipo:<16} apertura "
                      f"{ficha['apertura_pct']:.0f} % · antepecho "
                      f"{ficha['antepecho_m']:.2f} m · {ficha['uso']}")
    return lineas


__all__ = [
    "FUENTE", "CATALOGO_PUERTAS", "CATALOGO_VENTANAS",
    "tipos_puerta", "tipos_ventana", "datos_puerta", "datos_ventana",
    "puerta_para_uso", "tipo_de", "asignar_tipos", "quitar_tipos",
    "resumen_aberturas", "resumen_texto", "recuento_texto",
    "simbolo_puntos", "tabla_texto",
]
