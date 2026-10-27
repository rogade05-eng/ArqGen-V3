"""ILUMINACIÓN ARTIFICIAL POR TIPOS DE LÁMPARAS (v3.19.0).

La iluminación se proyecta con LÚMENES, no con watios: este módulo
trae el catálogo de LÁMPARAS del taller — LED en todas sus formas
(bombilla, panel, downlight, regleta lineal, tira, campana industrial,
proyector) y las clásicas que siguen encontrándose (fluorescente T8 y
compacta, halógena, incandescente, sodio de alta presión) — y el
MÉTODO DE LOS LÚMENES del libro:

    N = (E x A) / (F x CU x MF)

donde E son los lux recomendados por uso (Neufert), A el área del
local, F el flujo de la lámpara, CU el coeficiente de utilización y
MF el factor de mantenimiento. El resultado se compara entre
tecnologías: la LED sirve la misma luz con una fracción de la
potencia (la eficacia lm/W manda).

* ``generar_iluminacion``: dimensiona y COLOCA las luminarias en una
  retícula dentro de cada local seleccionado, como nodos LUMINAIRE de
  una red LIGHTING real (mismos comandos, auditoría, undo y QTO que
  cualquier instalación), con la potencia y el flujo en sus atributos
  para el balance eléctrico.
* ``tabla_comparativa``: cuántas lámparas y cuántos watios pediría
  cada tecnología para el mismo local — la elección informada.

Cero Tk y cero dependencias. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain.diseno_base import (
    ORIGEN_BASE, cerrar_qto, espacios_objetivo, lista_tipos,
)

PT = Tuple[float, float]

# error propio: ARQ-ILU-001 lámpara desconocida
# error propio: ARQ-ILU-002 área/lux inválidos
# error propio: ARQ-ILU-003 sin locales que iluminar

FUENTE = ("Neufert — iluminación artificial: lux por uso y método de "
          "los lúmenes (5.ª ed.)")

ORIGEN_LUZ = "iluminacion v3.19.0"

# -- catálogo de lámparas -----------------------------------------------------
# (etiqueta, tecnología, potencia W, flujo lm, color K, vida h, uso típico)
LAMPARAS: Dict[str, Dict[str, Any]] = {
    "led_bombilla": {
        "etiqueta": "LED bombilla A60", "tecnologia": "LED",
        "potencia_w": 9.0, "flujo_lm": 806.0, "color_k": 2700,
        "vida_h": 25000, "uso": "dormitorios y salas (casquillo E27)",
        "dimerizable": True},
    "led_panel": {
        "etiqueta": "LED panel 60x60", "tecnologia": "LED",
        "potencia_w": 36.0, "flujo_lm": 3600.0, "color_k": 4000,
        "vida_h": 40000, "uso": "oficinas y aulas (empotrado)",
        "dimerizable": True},
    "led_downlight": {
        "etiqueta": "LED downlight empotrable", "tecnologia": "LED",
        "potencia_w": 12.0, "flujo_lm": 1100.0, "color_k": 3000,
        "vida_h": 35000, "uso": "pasillos, baños y comercio",
        "dimerizable": True},
    "led_lineal": {
        "etiqueta": "LED lineal / regleta", "tecnologia": "LED",
        "potencia_w": 40.0, "flujo_lm": 4400.0, "color_k": 4000,
        "vida_h": 40000, "uso": "tramos continuos: pasillos y talleres",
        "dimerizable": True},
    "led_tira": {
        "etiqueta": "LED tira (por metro)", "tecnologia": "LED",
        "potencia_w": 14.0, "flujo_lm": 1200.0, "color_k": 3000,
        "vida_h": 30000, "uso": "cunetas, estanterías y cenefas",
        "dimerizable": True},
    "led_campana": {
        "etiqueta": "LED campana industrial", "tecnologia": "LED",
        "potencia_w": 120.0, "flujo_lm": 14400.0, "color_k": 5000,
        "vida_h": 50000, "uso": "naves y gimnasios (alto monte)",
        "dimerizable": False},
    "led_proyector": {
        "etiqueta": "LED proyector exterior", "tecnologia": "LED",
        "potencia_w": 50.0, "flujo_lm": 5000.0, "color_k": 4000,
        "vida_h": 35000, "uso": "fachadas y patios (IP65)",
        "dimerizable": False},
    "fluorescente_t8": {
        "etiqueta": "Fluorescente T8 (32 W)", "tecnologia": "fluorescencia",
        "potencia_w": 32.0, "flujo_lm": 2500.0, "color_k": 4000,
        "vida_h": 15000, "uso": "clásica de oficinas y aulas",
        "dimerizable": False},
    "fluorescente_compacto": {
        "etiqueta": "Fluorescente compacta (CFL)", "tecnologia": "fluorescencia",
        "potencia_w": 20.0, "flujo_lm": 1200.0, "color_k": 2700,
        "vida_h": 8000, "uso": "sustituta doméstica del incandescente",
        "dimerizable": False},
    "halogena": {
        "etiqueta": "Halógena (50 W)", "tecnologia": "incandescencia halógena",
        "potencia_w": 50.0, "flujo_lm": 750.0, "color_k": 2900,
        "vida_h": 3000, "uso": "acento cálido y escaparates",
        "dimerizable": True},
    "incandescente": {
        "etiqueta": "Incandescente (60 W)", "tecnologia": "incandescencia",
        "potencia_w": 60.0, "flujo_lm": 710.0, "color_k": 2700,
        "vida_h": 1000, "uso": "fuera de uso: solo referencia",
        "dimerizable": True},
    "sodio_alta_presion": {
        "etiqueta": "Sodio alta presión (100 W)", "tecnologia": "descarga",
        "potencia_w": 100.0, "flujo_lm": 10000.0, "color_k": 2000,
        "vida_h": 20000, "uso": "alumbrado vial y exteriores",
        "dimerizable": False},
}

# Lux recomendados por tipo de local (Neufert; EN 12464 de referencia)
LUX_POR_USO: Dict[str, int] = {
    "LIVING_ROOM": 150, "DINING_ROOM": 150, "KITCHEN": 300,
    "BEDROOM": 100, "BATHROOM": 200, "TOILET": 200,
    "OFFICE": 500, "CLASSROOM": 300, "RETAIL": 300,
    "CONFERENCE": 500, "LIBRARY": 300, "LAB": 500,
    "HOSPITAL_ROOM": 100, "WAITING": 200, "CORRIDOR": 100,
    "STAIR": 150, "STORAGE": 100, "PARKING": 75, "GYM": 300,
    "WORKSHOP": 300, "CAFETERIA": 200, "LOBBY": 200, "ROOM": 150,
    # -- salud (v3.20.0): tipos del DNA hospitalario, de la consulta
    #    al quirófano. Neufert: explorar 300, lecho 100-200, laborar
    #    500 y quirófano 1000; imagenología se queda baja (lectura de
    #    pantallas) y almacén/nodo son locales de trabajo técnico.
    "CONSULTATION_ROOM": 300, "WAITING_ROOM": 200,
    "EMERGENCY_ROOM": 300, "OPERATING_ROOM": 1000,
    "STERILIZATION_ROOM": 300, "WARD": 100, "ICU": 300,
    "NURSE_STATION": 300, "LABORATORY": 500, "IMAGING_ROOM": 150,
    "PHARMACY": 300,
    "CT_ROOM": 300, "FLUOROSCOPY_ROOM": 300,
    "ANATOMY_PATHOLOGY": 500, "MORGUE": 200,
    "PROGRESSIVE_CARE": 200, "MICROBIOLOGY_LAB": 500,
    "SERVER_ROOM": 500, "WASTE_ROOM": 100, "WAREHOUSE": 100,
    # -- salud v3.22.0: especialidades del documento de especificaciones
    #    técnicas (exploración 300, laboratorio 500, lechos 100-200,
    #    imagenología 150, técnicas 150-200, almacén de servicio 100).
    "AUTOPSY_ROOM": 500, "PREOP_ROOM": 300, "RECOVERY_ROOM": 300,
    "MRI_ROOM": 150, "ULTRASOUND_ROOM": 150,
    "ICU_PEDIATRIC": 300, "NICU": 300, "ISOLATION_ROOM": 300,
    "MOLECULAR_BIOLOGY_LAB": 500, "BLOOD_BANK": 500,
    "SAMPLE_COLLECTION": 300, "PROCEDURE_ROOM": 500,
    "ENDOSCOPY_ROOM": 300, "DIALYSIS_ROOM": 300,
    "STERILE_PHARMACY": 500, "REHABILITATION": 300,
    "HYDROTHERAPY": 200, "DELIVERY_ROOM": 500, "NEONATOLOGY": 300,
    "PEDIATRICS": 300, "DENTISTRY": 500, "OPHTHALMOLOGY": 500,
    "DERMATOLOGY": 300, "CARDIOLOGY": 300, "CATH_LAB": 300,
    "NUCLEAR_MEDICINE": 300, "FORENSIC_PATHOLOGY": 500,
    "MEDICAL_GAS_PLANT": 200, "ELECTRICAL_ROOM": 200,
    "GENERATOR_ROOM": 200, "UPS_ROOM": 500, "PUMP_ROOM": 150,
    "LAUNDRY": 300, "CLEAN_LINEN": 100, "SOILED_LINEN": 100,
    "CLEANING_ROOM": 100, "ADMINISTRATION": 500,
    "CLINICAL_ARCHIVE": 200, "ADMISSION": 300, "STERILE_STORE": 100,
    # -- comercial/oficinas v3.25.0: tipos del documento CC/OF
    #    (venta 300-500, trabajo 500, circulación comercial 250,
    #    almacenaje/doca 100-150, restauración 200-500).
    "GALLERY": 250, "RETAIL_LOCAL": 300, "TIENDA_ANCLA": 300,
    "ATRIUM": 200, "VESTIBULE": 200,
    "OPEN_OFFICE": 500, "COWORKING": 500, "MEETING_ROOM": 500,
    "CONFERENCE_ROOM": 500, "RECEPTION": 300,
    "RESTAURANT": 200, "COMMERCIAL_KITCHEN": 500,
    "TELECOM_ROOM": 200, "LOADING_DOCK": 150,
    "BICYCLE_PARKING": 75, "SECURITY_ROOM": 300,
    "DRESSING_ROOM": 200, "CAFETERIA": 200, "DINING_HALL": 200,

    # -- escuelas y círculos infantiles v3.26.0 (§75: ningún lux único para todo el establecimiento)
    "AULA_INFANTIL": 300,
    "SALA_CUNA": 200,
    "DORMITORIO_COLETIVO": 100,
    "JUEGO_INTERIOR": 200,
    "JUEGO_EXTERIOR": 75,
    "PATIO": 50,
    "SALA_PROFESORES": 300,
    "LAB_COMPUTACION": 500,
    "TALLER_TECNOLOGICO": 300,
    "SALA_ARTE": 500,
    "SALA_MUSICA": 300,
    "GYMNASIO": 300,
    "INFIRMARY": 300,
    "SALA_ESTUDIO": 300,
    "MONITORES": 200,
    "HIGIENE_CI": 200,
    "SALA_CONVIVENCIA": 200,
}

CU_DEFECTO = 0.60          # coeficiente de utilización (interiores medios)
MF_DEFECTO = 0.80          # factor de mantenimiento (limpieza regular)
ALTURA_MONTE_M = 2.80      # cota de montaje de referencia


def tipos_lampara() -> Tuple[str, ...]:
    """Claves del catálogo (orden estable)."""
    return tuple(LAMPARAS)


def datos_lampara(clave: str) -> Dict[str, Any]:
    """Ficha de la lámpara con su eficacia (ARQ-ILU-001 si no existe)."""
    datos = LAMPARAS.get(str(clave or "").strip())
    if not datos:
        raise DomainError(
            message=f"Lámpara desconocida: {clave}",
            code="ARQ-ILU-001",
            context={"clave": clave, "permitidas": list(LAMPARAS)},
            suggested_action="Usa una de: " + ", ".join(LAMPARAS))
    ficha = dict(datos)
    ficha["eficacia_lm_w"] = round(ficha["flujo_lm"] / ficha["potencia_w"], 1)
    ficha["clave"] = str(clave or "").strip()
    return ficha


def lux_para(space_type: str) -> int:
    """Lux recomendados para el uso del local (150 si no consta)."""
    return int(LUX_POR_USO.get(str(space_type or "").upper(), 150))


def dimensionar(area_m2: float, lux: int, clave: str,
                cu: float = CU_DEFECTO, mf: float = MF_DEFECTO) -> Dict[str, Any]:
    """Método de los lúmenes: cuántas lámparas pide el local.

    N = ceil(E x A / (F x CU x MF)); devuelve también la potencia
    total y la densidad de instalación (W/m2) para comparar.
    """
    ficha = datos_lampara(clave)
    area = float(area_m2)
    if area <= 0:
        raise DomainError(
            message="El área a iluminar debe ser positiva",
            code="ARQ-ILU-002",
            context={"area_m2": area},
            suggested_action="Dibuja el local o indica un área positiva")
    if int(lux) <= 0:
        raise DomainError(
            message="Los lux objetivo deben ser positivos",
            code="ARQ-ILU-002",
            context={"lux": lux})
    if cu <= 0 or mf <= 0:
        raise DomainError(
            message="CU y MF deben ser positivos",
            code="ARQ-ILU-002", context={"cu": cu, "mf": mf})
    util = ficha["flujo_lm"] * cu * mf
    n = max(1, math.ceil(int(lux) * area / util))
    potencia = n * ficha["potencia_w"]
    return {"clave": ficha["clave"], "etiqueta": ficha["etiqueta"],
            "tecnologia": ficha["tecnologia"],
            "flujo_lm": ficha["flujo_lm"], "potencia_w": ficha["potencia_w"],
            "eficacia_lm_w": ficha["eficacia_lm_w"],
            "area_m2": round(area, 2), "lux": int(lux),
            "cu": cu, "mf": mf, "n_lamparas": n,
            "potencia_total_w": round(potencia, 1),
            "densidad_w_m2": round(potencia / area, 1)}


def tabla_comparativa(area_m2: float, lux: int,
                      cu: float = CU_DEFECTO,
                      mf: float = MF_DEFECTO) -> List[Dict[str, Any]]:
    """Cuántas lámparas y watios pediría CADA tecnología."""
    comparativa: List[Dict[str, Any]] = []
    for clave in LAMPARAS:
        try:
            comparativa.append(dimensionar(area_m2, lux, clave, cu, mf))
        except DomainError:  # noqa: PERF203 — nunca debe pasar; protege
            continue
    return comparativa


def tabla_texto(area_m2: float, lux: int) -> List[str]:
    """La comparativa en líneas cp1252 (GUI y CLI)."""
    lineas = [f"Comparativa para {area_m2:.1f} m2 a {lux} lux "
              "(método de los lúmenes):"]
    lineas.append("  lámpara                    N    W     W/m2   lm/W")
    for fila in tabla_comparativa(area_m2, lux):
        lineas.append(f"  {fila['etiqueta']:<26} {fila['n_lamparas']:>3} "
                      f"{fila['potencia_total_w']:>6.1f} "
                      f"{fila['densidad_w_m2']:>6.1f}  "
                      f"{fila['eficacia_lm_w']:>5.1f}")
    return lineas


# ---------------------------------------------------------------------------
# generación en el proyecto
# ---------------------------------------------------------------------------

def _red_alumbrado(ctx: Any, svc: Any) -> Any:
    """Red LIGHTING del diseño (la crea si no existe ninguna propia)."""
    redes = [r for r in lista_tipos_instalaciones(ctx, "NETWORK")
             if r.system == "LIGHTING"]
    propias = [r for r in redes
               if str((getattr(r, "metadata", None) or {}).get("origen", "")
                      ).startswith(ORIGEN_BASE)]
    if propias:
        return propias[0]
    if redes:
        return redes[0]
    red = svc.create_network(
        "Alumbrado artificial (diseño)", "LIGHTING",
        "Luminarias colocadas por el diseño de espacios")
    meta = dict(getattr(red, "metadata", None) or {})
    meta["origen"] = ORIGEN_BASE
    red.metadata = meta
    ctx.installations.save(red)
    return red


def lista_tipos_instalaciones(ctx: Any, entity_type: str) -> List[Any]:
    """Entidades de instalaciones (protegido ante proyectos viejos)."""
    try:
        return list(ctx.installations.list(entity_type, ctx.project.id))
    except Exception:  # noqa: BLE001 — base sin migrar aún
        return []


def quitar_iluminacion(ctx: Any,
                       space_ids: Optional[List[str]] = None) -> List[str]:
    """Retira SOLO las luminarias generadas por este módulo.

    Con ``space_ids`` limita las bajas a los locales indicados
    (v3.20.0, asistente de local): la iluminación del resto del
    proyecto se conserva.
    """
    from services.installations_service import InstallationsService
    svc = InstallationsService(ctx)
    solo = set(space_ids or [])
    bajas: List[str] = []
    for nodo in lista_tipos_instalaciones(ctx, "NODE"):
        if nodo.kind != "LUMINAIRE":
            continue
        if str((nodo.attrs or {}).get("origen_luz", "")) != ORIGEN_LUZ:
            continue
        if solo and str(getattr(nodo, "space_id", "") or "") not in solo:
            continue
        codigo = nodo.code
        svc.delete_entity("NODE", nodo.id)
        bajas.append(codigo)
    return bajas


def _reticula(n: int, ancho: float, fondo: float) -> List[PT]:
    """Posiciones en retícula repartidas por el local (en metros)."""
    if n <= 0:
        return []
    if n == 1:
        return [(0.0, 0.0)]
    lado = math.sqrt(max(ancho * fondo / n, 0.25))
    cols = max(1, min(n, int(round(ancho / lado))))
    filas = max(1, math.ceil(n / cols))
    margen_x = min(0.8, ancho * 0.1)
    margen_y = min(0.8, fondo * 0.1)
    paso_x = (ancho - 2 * margen_x) / max(1, cols - 1)
    paso_y = (fondo - 2 * margen_y) / max(1, filas - 1)
    puntos: List[PT] = []
    for fila in range(filas):
        for col in range(cols):
            if len(puntos) >= n:
                return puntos
            x = margen_x + col * paso_x
            y = margen_y + fila * paso_y
            puntos.append((x, y))
    return puntos


def generar_iluminacion(ctx: Any, data: Any = None,
                        lampara: str = "led_panel",
                        nivel_id: str = "",
                        space_ids: Optional[List[str]] = None,
                        lux: Optional[int] = None,
                        cu: float = CU_DEFECTO,
                        mf: float = MF_DEFECTO,
                        con_nodos: bool = True,
                        con_qto: bool = True) -> Dict[str, Any]:
    """Dimensiona y coloca las luminarias de los locales (v3.19.0).

    Por cada local: lux del uso (o los pedidos), lámpara del catálogo
    y método de los lúmenes; las luminarias entran como nodos
    LUMINAIRE de la red LIGHTING en retícula, con potencia, flujo y
    lux objetivo en sus atributos. Idempotente: las luminarias de
    pasadas se retiran antes (lo cableado a mano se conserva).
    """
    from services.installations_service import InstallationsService
    resumen: Dict[str, Any] = {"operacion": "iluminacion", "creados": [],
                               "eliminados": [], "avisos": [], "qto": None,
                               "locales": []}
    ficha = datos_lampara(lampara)
    objetivos = espacios_objetivo(ctx, space_ids or None, nivel_id)
    if not objetivos:
        raise DomainError(
            message="No hay locales que iluminar con esos criterios",
            code="ARQ-ILU-003",
            context={"nivel_id": nivel_id, "space_ids": space_ids or []},
            suggested_action="Genera primero la edificación con el "
                             "asistente o elige otros locales")
    if con_nodos:
        resumen["eliminados"] = quitar_iluminacion(
            ctx, [e.id for e in objetivos] if objetivos else None)
        svc = InstallationsService(ctx)
        red = _red_alumbrado(ctx, svc)
    else:
        red = None
    nivel_por_id = {lv.id: lv for lv in lista_tipos(ctx, "LEVEL")}
    potencia_total = 0.0
    for espacio in objetivos:
        area = espacio.area_m2()
        lux_local = int(lux) if lux else lux_para(espacio.space_type)
        dims = dimensionar(area, lux_local, ficha["clave"], cu, mf)
        # retícula sobre el AABB real del local (centrado)
        xs = [p[0] for p in espacio.boundary]
        ys = [p[1] for p in espacio.boundary]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        ancho, fondo = max(xs) - min(xs), max(ys) - min(ys)
        posiciones = _reticula(dims["n_lamparas"], ancho, fondo)
        nivel = nivel_por_id.get(espacio.level_id)
        codes: List[str] = []
        if con_nodos:
            for indice, (dx, dy) in enumerate(posiciones, start=1):
                nodo = svc.add_node(
                    red.code, "LUMINAIRE", cx + dx - ancho / 2.0 + 0.0,
                    cy + dy - fondo / 2.0 + 0.0,
                    name=f"Lum {espacio.name or espacio.code} {indice}",
                    level_ref=getattr(nivel, "code", "") or "",
                    space_ref=espacio.code,
                    elevation_m=ALTURA_MONTE_M,
                    attrs={"lampara": ficha["clave"],
                           "tecnologia": ficha["tecnologia"],
                           "potencia_w": ficha["potencia_w"],
                           "flujo_lm": ficha["flujo_lm"],
                           "lux_objetivo": lux_local,
                           "origen_luz": ORIGEN_LUZ})
                codes.append(nodo.code)
        potencia_total += dims["potencia_total_w"]
        resumen["locales"].append({
            "code": espacio.code, "nombre": espacio.name or espacio.code,
            "area_m2": dims["area_m2"], "lux": dims["lux"],
            "n_lamparas": dims["n_lamparas"],
            "potencia_w": dims["potencia_total_w"],
            "densidad_w_m2": dims["densidad_w_m2"],
            "codes": codes})
    resumen["parametros"] = {
        "lampara": ficha["clave"], "etiqueta": ficha["etiqueta"],
        "tecnologia": ficha["tecnologia"],
        "potencia_w": ficha["potencia_w"], "flujo_lm": ficha["flujo_lm"],
        "eficacia_lm_w": ficha["eficacia_lm_w"],
        "lux": int(lux) if lux else None, "cu": cu, "mf": mf,
        "con_nodos": con_nodos,
        "potencia_total_w": round(potencia_total, 1)}
    resumen["creados"] = [c for loc in resumen["locales"]
                          for c in loc["codes"]]
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Línea cp1252 con el resultado de la iluminación."""
    p = resumen.get("parametros") or {}
    if p:
        texto = (f"Iluminación con {p.get('etiqueta', '')}"
                 f" · {len(resumen.get('locales', []))} local(es)"
                 f" · {p.get('potencia_total_w', 0.0):.0f} W totales")
    else:
        texto = "Iluminación"
    partes = [texto]
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} LUMINAIRE colocada(s)")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


def locales_texto(resumen: Dict[str, Any]) -> List[str]:
    """Detalle por local en líneas cp1252."""
    lineas = ["Iluminación por local:"]
    lineas.append("  local              m2      lux   N    W     W/m2")
    for loc in resumen.get("locales", []):
        nombre = (loc.get("nombre") or "")[:18]
        lineas.append(f"  {nombre:<18} {loc['area_m2']:>6.1f} "
                      f"{loc['lux']:>6} {loc['n_lamparas']:>3} "
                      f"{loc['potencia_w']:>6.1f} "
                      f"{loc['densidad_w_m2']:>5.1f}")
    return lineas


__all__ = [
    "FUENTE", "ORIGEN_LUZ", "LAMPARAS", "LUX_POR_USO", "CU_DEFECTO",
    "MF_DEFECTO", "ALTURA_MONTE_M", "tipos_lampara", "datos_lampara",
    "lux_para", "dimensionar", "tabla_comparativa", "tabla_texto",
    "lista_tipos_instalaciones", "quitar_iluminacion", "_reticula",
    "generar_iluminacion", "resumen_texto", "locales_texto",
]
