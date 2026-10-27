"""Instantánea de coste para los informes de validación (v3.31.0).

«Coste ligado al check»: los informes de validación (vivienda §54,
comercial CC/OF y educacional ED) llevan una sección COSTE con la
instantánea del presupuesto PRECONS III activo del proyecto — total,
coeficientes y coste por m² — para que el check y el dinero se lean
juntos, como en las fichas de decisión.

Honradez: la instantánea es SOLO LECTURA (usa ``latest()``, nunca
``ensure_active()``: si no hay presupuesto con renglones, no se
inventa nada y el informe sale sin sección de coste). Si el catálogo
PRECONS no está disponible o algo falla, devuelve None: el coste es
informativo y jamás bloquea una validación.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.precons_budget_service import (DEFAULT_RULESET,
                                             PreconsBudgetService)

# reglaset cargado una sola vez por proceso (el catálogo es grande)
_RULESET_CACHE: Dict[str, Any] = {}


def _servicio(ctx: Any) -> Optional[PreconsBudgetService]:
    """Servicio con el ruleset por defecto cacheado, o None."""
    try:
        ruleset = _RULESET_CACHE.get(DEFAULT_RULESET)
        if ruleset is None:
            from app.paths import resource_path
            from engines.precons_engine import PreconsRuleset
            ruleset = PreconsRuleset.from_file(resource_path(
                "rulesets", f"{DEFAULT_RULESET}.json"))
            _RULESET_CACHE[DEFAULT_RULESET] = ruleset
        return PreconsBudgetService(ctx, ruleset=ruleset)
    except Exception:  # noqa: BLE001 — sin catálogo: sin coste
        return None


def _miles(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", " ")


def instantanea_coste(ctx: Any) -> Optional[Dict[str, Any]]:
    """Instantánea SOLO LECTURA del presupuesto activo, o None.

    Devuelve un dict listo para ``informe["coste"]`` del informe de
    validación: fuente, moneda, nº de renglones, directo, transporte,
    indirectos, beneficio, total, área del modelo y coste por m².
    Nunca lanza: cualquier problema devuelve None (honradez antes que
    decoración).
    """
    servicio = _servicio(ctx)
    if servicio is None:
        return None
    try:
        presupuesto = servicio.latest()
        if presupuesto is None:
            return None
        arbol = servicio.repo.budget_tree(presupuesto["id"])
        if not arbol["items"]:
            return None
        totales = servicio.totals()
        # área del modelo (sólo lectura, locales con frontera cerrada)
        from domain.vivienda_servicios import _area as _area_local
        espacios = []
        try:
            espacios = list(ctx.architecture.list(
                "SPACE", ctx.project.id))
        except Exception:  # noqa: BLE001 — sin arquitectura: sin m2
            espacios = []
        area = sum(_area_local(s) for s in espacios)
        por_m2 = (round(float(totales["total"]) / area, 2)
                  if area > 1e-9 else None)
        return {
            "fuente": "presupuesto PRECONS III activo",
            "ruleset": str(getattr(servicio.ruleset, "code", "")),
            "moneda": str(presupuesto.get("currency", "CUP")),
            "renglones": len(arbol["items"]),
            "directo": float(totales["direct"]),
            "transporte": float(totales["transport"]),
            "indirectos": float(totales["indirect"]),
            "beneficio": float(totales["benefit"]),
            "total": float(totales["total"]),
            "area_m2": round(area, 2) if area > 1e-9 else None,
            "total_por_m2": por_m2,
            "nota": "coste informativo del presupuesto activo; la "
                    "valoración oficial la fija el presupuesto "
                    "definitivo y los precios vigentes",
        }
    except Exception:  # noqa: BLE001 — el coste no bloquea nada
        return None


def texto_bloque_coste(coste: Dict[str, Any]) -> str:
    """Bloque de texto cp1252 con la instantánea (para el cuadro)."""
    if not coste or not coste.get("total"):
        return ""
    moneda = str(coste.get("moneda", "CUP"))
    lineas = ["COSTE DEL PROYECTO (" + str(coste.get("fuente", "")) + ")"]
    lineas.append(
        f"costo directo {_miles(coste.get('directo', 0.0))} {moneda} + "
        f"transporte {_miles(coste.get('transporte', 0.0))} {moneda} + "
        f"indirectos {_miles(coste.get('indirectos', 0.0))} {moneda} + "
        f"beneficio {_miles(coste.get('beneficio', 0.0))} {moneda}")
    lineas.append(
        f"TOTAL: {_miles(coste.get('total', 0.0))} {moneda} "
        f"({int(coste.get('renglones', 0))} renglón(es))")
    if coste.get("total_por_m2") is not None:
        lineas.append(
            f"coste por m2: {_miles(coste['total_por_m2'])} {moneda} "
            f"sobre {coste.get('area_m2', 0):.1f} m2 de locales")
    lineas.append(str(coste.get("nota", "")))
    return "\n".join(lineas)


def adjuntar_coste(ctx: Any, informe: Dict[str, Any]) -> str:
    """Añade ``informe["coste"]`` si hay presupuesto y devuelve el
    bloque de texto (cadena vacía si no hay nada que mostrar).

    Los tres informes de validación (vivienda, comercial y
    educacional) lo llaman justo antes de pintar el cuadro: así el
    check y el coste se ven juntos SIN acoplar el dominio al
    presupuesto.
    """
    try:
        coste = instantanea_coste(ctx)
    except Exception:  # noqa: BLE001 — el coste no bloquea nada
        coste = None
    if not coste:
        return ""
    informe["coste"] = coste
    return texto_bloque_coste(coste)


__all__ = ["instantanea_coste", "texto_bloque_coste", "adjuntar_coste"]
