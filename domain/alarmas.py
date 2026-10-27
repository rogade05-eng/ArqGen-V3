"""ALARMAS CONTRA INTRUSOS POR LOCALES (v3.19.0).

La alarma se diseña LOCALE POR LOCAL: el proyectista elige qué
locales quiere proteger y este módulo arma el sistema de intrusión
según las reglas del módulo de seguridad (spec 45) — detectores
volumétricos PIR de esquina (1 por sector de ~12 m2), contactos
magnéticos en TODOS los vanos del perímetro del local y el equipo
central (panel, teclado y sirena) donde se pida:

* ``locales_protegibles``: los candidatos a proteger (con su área y
  sus vanos perimetrales) para que la GUI los liste con casillas.
* ``generar_alarma``: crea la red INTRUSION real (nodos PIR,
  MAGNETIC_CONTACT, INTRUSION_PANEL, KEYPAD y SIREN con la zona en
  sus atributos) por los caminos oficiales — comandos, auditoría,
  undo persistente e invalidación de QTO — y VALIDA la cobertura con
  el motor de intrusión (zonas, batería y sirenas).
* Idempotente: los dispositivos generados se retiran antes; lo
  cableado a mano se conserva.

Cero Tk y cero dependencias. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain.diseno_base import ORIGEN_BASE, cerrar_qto, lista_tipos
from engines.intrusion_engine import (
    PIR_AREA_M2, check_zone, panel_report,
)

PT = Tuple[float, float]

# error propio: ARQ-ALR-001 sin locales seleccionados
# error propio: ARQ-ALR-002 local inexistente

FUENTE = ("Neufert — seguridad: detección volumétrica y perimetral "
          "(módulo de intrusión spec 45)")

ORIGEN_ALARMA = "alarmas v3.19.0"

PIR_POR_SECTOR_M2 = 12.0     # criterio del motor: 1 PIR por ~12 m2
SEPARACION_EQUIPO_M = 0.60   # teclado y sirena junto al panel


def lista_tipos_instalaciones(ctx: Any, entity_type: str) -> List[Any]:
    """Entidades de instalaciones (protegido ante proyectos viejos)."""
    try:
        return list(ctx.installations.list(entity_type, ctx.project.id))
    except Exception:  # noqa: BLE001 — base sin migrar aún
        return []


# ---------------------------------------------------------------------------
# geometría mínima: vanos del perímetro de un local
# ---------------------------------------------------------------------------

def _punto_en_poligono(x: float, y: float,
                       poligono: List[PT]) -> bool:
    """Ray casting: punto dentro del contorno (borde inclusive ±tol)."""
    dentro = False
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < xin:
                dentro = not dentro
    return dentro


def _dist_a_segmento(px: float, py: float, ax: float, ay: float,
                     bx: float, by: float) -> float:
    """Distancia del punto al segmento AB (para el borde del local)."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _sobre_perimetro(centro: PT, poligono: List[PT],
                     tol_m: float = 0.15) -> bool:
    """El vano está en el perímetro: dentro del local o a menos de
    ``tol`` de su contorno (el centro del vano pisa el muro y los
    contornos de planta se dibujan por el eje del muro)."""
    if _punto_en_poligono(centro[0], centro[1], poligono):
        return True
    n = len(poligono)
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        if _dist_a_segmento(centro[0], centro[1], x1, y1, x2, y2) <= tol_m:
            return True
    return False


def _centro_vano(vano: Any, muro: Any) -> Optional[PT]:
    """Centro del vano sobre su muro (a su offset)."""
    if muro is None:
        return None
    sx, sy = float(muro.start[0]), float(muro.start[1])
    ex, ey = float(muro.end[0]), float(muro.end[1])
    largo = math.hypot(ex - sx, ey - sy)
    if largo <= 0:
        return None
    t = min(max((float(vano.offset_m) + float(vano.width_m) / 2.0)
                / largo, 0.0), 1.0)
    return (sx + (ex - sx) * t, sy + (ey - sy) * t)


def vanos_del_perimetro(espacio: Any, muros: Dict[str, Any],
                        vanos: List[Any]) -> List[Any]:
    """Vanos (puertas/ventanas) sobre el contorno del local (±tol)."""
    boundary = [(float(p[0]), float(p[1]))
                for p in (getattr(espacio, "boundary", None) or [])]
    if len(boundary) < 3:
        return []
    propios: List[Any] = []
    for vano in vanos:
        centro = _centro_vano(vano, muros.get(vano.wall_id or ""))
        if centro is None:
            continue
        if _sobre_perimetro(centro, boundary):
            propios.append(vano)
    return propios


def locales_protegibles(ctx: Any, nivel_id: str = "") -> List[Dict[str, Any]]:
    """Locales candidatos con su área y sus vanos perimetrales.

    Es la base de la selección en la GUI: cada fila lleva code,
    nombre, nivel, área, nº de vanos y los PIR exigidos por el motor.
    """
    muros = {m.id: m for m in lista_tipos(ctx, "WALL")}
    vanos: List[Any] = []
    vistos: set = set()
    for kind in ("DOOR", "WINDOW", "OPENING"):
        for vano in lista_tipos(ctx, kind):
            if vano.id in vistos:
                continue
            vistos.add(vano.id)
            vanos.append(vano)
    salida: List[Dict[str, Any]] = []
    for espacio in lista_tipos(ctx, "SPACE"):
        if nivel_id and espacio.level_id != nivel_id:
            continue
        if len(getattr(espacio, "boundary", None) or []) < 3:
            continue
        perimetro = vanos_del_perimetro(espacio, muros, vanos)
        area = espacio.area_m2()
        salida.append({
            "id": espacio.id, "code": espacio.code,
            "nombre": espacio.name or espacio.code,
            "nivel": espacio.level_id,
            "area_m2": round(area, 2),
            "vanos": len(perimetro),
            "pirs": max(1, math.ceil(area / PIR_POR_SECTOR_M2)) if area > 0 else 1,
            "space_type": str(espacio.space_type or "")})
    return salida


# ---------------------------------------------------------------------------
# generación en el proyecto
# ---------------------------------------------------------------------------

def _red_intrusion(ctx: Any, svc: Any) -> Any:
    """Red INTRUSION del diseño (reutiliza la primera o crea una)."""
    redes = [r for r in lista_tipos_instalaciones(ctx, "NETWORK")
             if r.system == "INTRUSION"]
    propias = [r for r in redes
               if str((getattr(r, "metadata", None) or {}).get("origen", "")
                      ).startswith(ORIGEN_BASE)]
    if propias:
        return propias[0]
    if redes:
        return redes[0]
    red = svc.create_network(
        "Intrusión (diseño)", "INTRUSION",
        "Alarmas contra intrusos del diseño de espacios")
    meta = dict(getattr(red, "metadata", None) or {})
    meta["origen"] = ORIGEN_BASE
    red.metadata = meta
    ctx.installations.save(red)
    return red


def quitar_alarmas(ctx: Any,
                   space_ids: Optional[List[str]] = None) -> List[str]:
    """Retira SOLO los dispositivos de intrusión generados aquí.

    Con ``space_ids`` limita las bajas a los locales indicados
    (v3.20.0, asistente de local): la alarma del resto del proyecto
    se conserva.
    """
    from services.installations_service import InstallationsService
    svc = InstallationsService(ctx)
    solo = set(space_ids or [])
    bajas: List[str] = []
    for nodo in lista_tipos_instalaciones(ctx, "NODE"):
        if str((nodo.attrs or {}).get("origen_alarma", "")) != ORIGEN_ALARMA:
            continue
        if solo and str(getattr(nodo, "space_id", "") or "") not in solo:
            continue
        codigo = nodo.code
        svc.delete_entity("NODE", nodo.id)
        bajas.append(codigo)
    return bajas


def generar_alarma(ctx: Any, data: Any = None,
                   space_ids: Optional[List[str]] = None,
                   nivel_id: str = "",
                   panel_space_id: str = "",
                   sirena_exterior: bool = False,
                   con_qto: bool = True) -> Dict[str, Any]:
    """Arma la alarma de los locales elegidos (v3.19.0).

    ``space_ids`` es la selección del proyectista: los locales a
    proteger. Para cada uno: PIR de esquina (1 por ~12 m2) y contactos
    magnéticos en todos sus vanos. El panel, el teclado y la sirena
    van al local indicado (o al primero protegido); con
    ``sirena_exterior`` una segunda sirena sale junto a la fachada
    sur. Cada zona lleva el nombre del local en los atributos y la
    cobertura se valida con el motor de intrusión.
    """
    from services.installations_service import InstallationsService
    resumen: Dict[str, Any] = {"operacion": "alarma", "creados": [],
                               "eliminados": [], "avisos": [], "qto": None,
                               "zonas": []}
    espacios = lista_tipos(ctx, "SPACE")
    por_id = {e.id: e for e in espacios}
    elegidos: List[Any] = []
    for sid in (space_ids or []):
        espacio = por_id.get(sid)
        if espacio is None:
            raise DomainError(
                message=f"Local inexistente: {sid}",
                code="ARQ-ALR-002",
                context={"space_id": sid},
                suggested_action="Elige locales de la lista de protegibles")
        if len(getattr(espacio, "boundary", None) or []) >= 3:
            elegidos.append(espacio)
    if not elegidos:
        raise DomainError(
            message="Ningún local seleccionado para proteger",
            code="ARQ-ALR-001",
            context={"space_ids": list(space_ids or [])},
            suggested_action="Marca al menos un local en la lista")
    elegidos.sort(key=lambda s: (str(s.code),))
    resumen["eliminados"] = quitar_alarmas(
        ctx, [s.id for s in elegidos])
    svc = InstallationsService(ctx)
    red = _red_intrusion(ctx, svc)
    nivel_por_id = {lv.id: lv for lv in lista_tipos(ctx, "LEVEL")}
    muros = {m.id: m for m in lista_tipos(ctx, "WALL")}
    vanos: List[Any] = []
    vistos: set = set()
    for kind in ("DOOR", "WINDOW", "OPENING"):
        for vano in lista_tipos(ctx, kind):
            if vano.id in vistos:
                continue
            vistos.add(vano.id)
            vanos.append(vano)
    # panel: local pedido, si no el primero protegido
    panel = por_id.get(panel_space_id) if panel_space_id else None
    if panel is None or panel not in elegidos:
        panel = elegidos[0]
    nivel_panel = nivel_por_id.get(panel.level_id)
    pxs = [p[0] for p in panel.boundary]
    pys = [p[1] for p in panel.boundary]
    pxc, pyc = (min(pxs) + max(pxs)) / 2.0, (min(pys) + max(pys)) / 2.0
    codes_panel: List[str] = []
    for kind, nombre, (dx, dy) in (
            ("INTRUSION_PANEL", "Panel intrusión", (0.0, 0.0)),
            ("KEYPAD", "Teclado alarma", (SEPARACION_EQUIPO_M, 0.0)),
            ("SIREN", "Sirena interior", (0.0, SEPARACION_EQUIPO_M))):
        nodo = svc.add_node(
            red.code, kind, pxc + dx, pyc + dy, name=nombre,
            level_ref=getattr(nivel_panel, "code", "") or "",
            space_ref=panel.code,
            attrs={"zona": panel.name or panel.code,
                   "origen_alarma": ORIGEN_ALARMA})
        codes_panel.append(nodo.code)
    if sirena_exterior:
        todos = [p for e in elegidos for p in e.boundary]
        miny = min(p[1] for p in todos)
        cx = sum(p[0] for p in todos) / len(todos)
        nodo = svc.add_node(
            red.code, "SIREN", cx, miny - 1.0, name="Sirena exterior",
            level_ref=getattr(nivel_panel, "code", "") or "",
            attrs={"zona": "perimetro",
                   "origen_alarma": ORIGEN_ALARMA})
        codes_panel.append(nodo.code)
    # detectores y contactos por local
    total_pirs = total_contactos = 0
    for espacio in elegidos:
        zona = espacio.name or espacio.code
        nivel = nivel_por_id.get(espacio.level_id)
        xs = [p[0] for p in espacio.boundary]
        ys = [p[1] for p in espacio.boundary]
        area = espacio.area_m2()
        n_pirs = max(1, math.ceil(area / PIR_POR_SECTOR_M2)) if area > 0 else 1
        codes: List[str] = []
        # el primer PIR en una esquina (montaje típico), el resto repartido
        esquinas = sorted(set(xs))[:2], sorted(set(ys))[:2]
        for indice in range(n_pirs):
            if indice == 0:
                x, y = esquinas[0][0] + 0.30, esquinas[1][0] + 0.30
            else:
                t = (indice + 1.0) / (n_pirs + 1.0)
                x, y = (min(xs) + (max(xs) - min(xs)) * t,
                        (min(ys) + max(ys)) / 2.0)
            nodo = svc.add_node(
                red.code, "PIR", x, y, name=f"PIR {zona} {indice + 1}",
                level_ref=getattr(nivel, "code", "") or "",
                space_ref=espacio.code,
                attrs={"zona": zona, "radio_m": 6.0,
                       "origen_alarma": ORIGEN_ALARMA})
            codes.append(nodo.code)
        perimetro = vanos_del_perimetro(espacio, muros, vanos)
        contactos = 0
        for indice, vano in enumerate(perimetro, start=1):
            centro = _centro_vano(vano, muros.get(vano.wall_id or ""))
            if centro is None:
                continue
            nodo = svc.add_node(
                red.code, "MAGNETIC_CONTACT", centro[0], centro[1],
                name=f"Contacto {vano.code}",
                level_ref=getattr(nivel, "code", "") or "",
                space_ref=espacio.code,
                attrs={"zona": zona, "vano": vano.code,
                       "origen_alarma": ORIGEN_ALARMA})
            codes.append(nodo.code)
            contactos += 1
        total_pirs += n_pirs
        total_contactos += contactos
        reporte = check_zone(zona, area, n_pirs, contactos, len(perimetro))
        resumen["zonas"].append({
            "code": espacio.code, "zona": zona,
            "area_m2": round(area, 2), "pirs": n_pirs,
            "contactos": contactos, "vanos": len(perimetro),
            "ok": reporte.ok, "hallazgos": list(reporte.findings),
            "codes": codes})
    resumen["creados"] = codes_panel + [c for z in resumen["zonas"]
                                        for c in z["codes"]]
    # validación de panel (zonas, batería, sirenas)
    sirenas = len(codes_panel) - 2  # interior (+ exterior si se pidió)
    informe = panel_report(
        zones=len(resumen["zonas"]), partitions=[], expanders=0,
        sirens=max(sirenas, 1))
    resumen["panel"] = {"zonas": informe.zones,
                        "bateria_ah": round(informe.battery_ah, 2),
                        "ok": informe.ok,
                        "hallazgos": list(informe.findings)}
    resumen["parametros"] = {
        "locales": len(elegidos), "pirs": total_pirs,
        "contactos": total_contactos,
        "sirenas": max(sirenas, 1),
        "panel_space": panel.code,
        "sirena_exterior": bool(sirena_exterior),
        "bateria_ah": round(informe.battery_ah, 2),
        "fuente": FUENTE}
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado de la alarma."""
    p = resumen.get("parametros") or {}
    if p:
        texto = (f"Alarma en {p.get('locales', 0)} local(es)"
                 f" · {p.get('pirs', 0)} PIR"
                 f" · {p.get('contactos', 0)} contactos"
                 f" · {p.get('sirenas', 0)} sirena(s)"
                 f" · batería {p.get('bateria_ah', 0.0):.1f} Ah"
                 f" · panel en {p.get('panel_space', '')}")
    else:
        texto = "Alarma"
    partes = [texto]
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} dispositivo(s)")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    malos = [z for z in resumen.get("zonas", []) if not z.get("ok")]
    if malos:
        partes.append(f"{len(malos)} zona(s) con hallazgos")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


def zonas_texto(resumen: Dict[str, Any]) -> List[str]:
    """Detalle por zona en líneas cp1252."""
    lineas = ["Zonas protegidas:"]
    lineas.append("  zona                   m2    PIR  contactos  vanos")
    for zona in resumen.get("zonas", []):
        nombre = (zona.get("zona") or "")[:22]
        lineas.append(f"  {nombre:<22} {zona['area_m2']:>6.1f} "
                      f"{zona['pirs']:>4} {zona['contactos']:>9} "
                      f"{zona['vanos']:>6}"
                      + ("" if zona.get("ok") else "  (revisar)"))
    for zona in resumen.get("zonas", []):
        for hallazgo in zona.get("hallazgos", []):
            lineas.append(f"  aviso: {hallazgo}")
    panel = resumen.get("panel") or {}
    for hallazgo in panel.get("hallazgos", []):
        lineas.append(f"  panel: {hallazgo}")
    return lineas


__all__ = [
    "FUENTE", "ORIGEN_ALARMA", "PIR_POR_SECTOR_M2", "SEPARACION_EQUIPO_M",
    "lista_tipos_instalaciones", "locales_protegibles", "quitar_alarmas",
    "generar_alarma", "resumen_texto", "zonas_texto",
    "_punto_en_poligono", "_centro_vano", "vanos_del_perimetro",
]
