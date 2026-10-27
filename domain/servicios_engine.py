"""MOTOR DE SERVICIOS COMPLETOS (v3.33.0) — domain/servicios_engine.py.

Del catálogo (servicios_specs.json) al PROYECTO: dado un servicio y
sus parámetros dinámicos produce el PROGRAMA dimensionado (locales
incluidos, áreas escaladas, dimensiones sugeridas, flujo y
requisitos), lo VALIDA contra el DNA y lo APLICA al proyecto por los
caminos oficiales: zona SERVICE, pasillo de distribución, espacios
reales, relaciones ADJACENT_TO y (opcional) muros perimetrales.

Es el asistente orientado a SERVICIOS: cuando al proyectista solo le
interesa UN servicio (una anatomía patológica, una hemodiálisis...)
sin generar la edificación completa. Si el proyecto no tiene niveles,
el destino se crea al vuelo (edificio mínimo con un nivel).

v3.35.0 — catálogo v2.0 (documento «servicios médicos»): el programa
lleva GRUPOS funcionales con subtotales (sección 20: área por
componentes, no un porcentaje universal); la validación incorpora
PUERTAS del catálogo (anchura de camilla/carro), CIRCULACION mínima,
CRITICIDAD por niveles (sección 25), RELACIONES PROHIBIDAS (regla 05)
y SEPARACION limpio/sucio (regla 06); y se generan los DOCUMENTOS del
servicio: ficha de local (sección 30), matriz de instalaciones
(sección 22), relaciones entre servicios (sección 17), flujos
hospitalarios (sección 18) y las 20 reglas de generación automática
de plantas (sección 24).

Todo lo creado son entidades REALES: entra en QTO, presupuesto,
explorador, informes y validación dimensional como lo generado por
el asistente de edificación.

Cero Tk. Mensajes 100 % codificables en cp1252 (sin flechas: usa
«->» en los flujos).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from domain import servicios_specs as specs
from services.architecture_service import ArchitectureService

PASILLO_ANCHO = 2.4       # salud con camillas (DNA pasillo_m 2.0-2.4)
PROPORCION_DEF = 1.3      # ancho:fondo de los locales empaquetados
ANCHO_MAX = 9.0
FONDO_MIN = 3.0
FONDO_MAX = 8.5
ESPESOR_MURO = 0.15

ORIGEN_SERVICIO = "asistente de servicios (v3.33.0)"

# errores propios: ARQ-SRV-003..008 (007: local inexistente para la ficha)


# ---------------------------------------------------------------------------
# 1) PARÁMETROS SANOS (nunca explota con lo que el usuario escriba)
# ---------------------------------------------------------------------------

def _norm_params(item: "specs.Servicio",
                 params: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any],
                                                            List[str]]:
    """Completa con defectos, fuerza tipo y acota al rango; cada
    corrección sale como aviso."""
    avisos: List[str] = []
    entrada = dict(params or {})
    out: Dict[str, Any] = {}
    for p in item.parametros:
        bruto = entrada.get(p.codigo, p.defecto)
        if p.tipo == "bool":
            if isinstance(bruto, str):
                valor = bruto.strip().lower() in ("1", "si", "sí", "true",
                                                  "x", "siempre")
            else:
                valor = bool(bruto)
            out[p.codigo] = valor
            continue
        try:
            valor = float(bruto)
        except (TypeError, ValueError):
            valor = float(p.defecto if p.defecto is not None else 0.0)
            avisos.append(
                f"{p.codigo}: valor ilegible, se usa el defecto "
                f"({p.defecto:g})")
        if p.maximo > p.minimo:
            if valor < p.minimo:
                avisos.append(
                    f"{p.codigo}: {valor:g} por debajo del mínimo "
                    f"({p.minimo:g}), se acota")
                valor = p.minimo
            elif valor > p.maximo:
                avisos.append(
                    f"{p.codigo}: {valor:g} por encima del máximo "
                    f"({p.maximo:g}), se acota")
                valor = p.maximo
        out[p.codigo] = int(round(valor))
    sobran = [k for k in entrada if k not in out]
    for k in sobran:
        avisos.append(f"parámetro ignorado: {k} (no existe en el "
                      "servicio)")
    return out, avisos


# ---------------------------------------------------------------------------
# 2) PROGRAMA DIMENSIONADO
# ---------------------------------------------------------------------------

def _area_de(local: "specs.ServicioLocal", params: Dict[str, Any],
             avisos: List[str]) -> float:
    """Área base más la contribución de cada parámetro, acotada al
    rango del catálogo (cada acotación avisa)."""
    area = local.area_base
    for codigo, por in local.area_por.items():
        area += float(params.get(codigo, 0) or 0) * float(por)
    if local.area_min and area < local.area_min:
        avisos.append(
            f"{local.codigo}: área calculada {area:.2f} m2 por debajo "
            f"del mínimo ({local.area_min:.2f} m2), se usa el mínimo")
        area = local.area_min
    if local.area_max and area > local.area_max:
        avisos.append(
            f"{local.codigo}: área calculada {area:.2f} m2 por encima "
            f"del máximo ({local.area_max:.2f} m2), se acota")
        area = local.area_max
    return area


def _dimensiones(area: float) -> Tuple[float, float]:
    """Ancho y fondo sugeridos con la proporción de trabajo, acotados."""
    ancho = max(2.0, min(math.sqrt(max(area, 1.0) / PROPORCION_DEF),
                         ANCHO_MAX))
    fondo = max(FONDO_MIN, min(area / ancho, FONDO_MAX))
    if fondo >= FONDO_MAX and area / fondo > ANCHO_MAX:
        ancho = ANCHO_MAX
    else:
        ancho = max(ancho, area / FONDO_MAX)
    return round(ancho, 2), round(fondo, 2)


def programa_servicio(codigo: str,
                      params: Optional[Dict[str, Any]] = None) \
        -> Dict[str, Any]:
    """Programa del servicio: locales incluidos, áreas, dimensiones,
    flujos y validación funcional. Solo datos: no toca el proyecto."""
    item = specs.servicio(codigo)
    usados, avisos = _norm_params(item, params)
    renglones: List[Dict[str, Any]] = []
    for local in item.locales:
        if local.condicion:
            p = item.param(local.condicion)
            activo = bool(usados.get(local.condicion)) if p else True
            if not activo:
                continue
        repeticiones = 1
        if local.repite_por and local.repite_por in usados:
            repeticiones = max(1, int(usados[local.repite_por]))
        for copia in range(1, repeticiones + 1):
            avisos_copia: List[str] = []
            area = _area_de(local, usados, avisos_copia)
            avisos.extend(avisos_copia)
            ancho, fondo = _dimensiones(area)
            nombre = local.nombre if copia == 1 \
                else f"{local.nombre} {copia}"
            renglones.append({
                "codigo": local.codigo, "nombre": nombre,
                "space_type": local.space_type, "area_m2": round(area, 2),
                "ancho_m": ancho, "fondo_m": fondo, "flujo": local.flujo,
                "critico": local.critico, "req": list(local.req),
                "adjacencias": list(local.adjacencias),
                "area_min": round(float(local.area_min or 0.0), 2),
                # v3.42.0: el máximo del catálogo llega al renglón:
                # techos del teselado completo (rellenar el contorno
                # sin desbordar el máximo admisible del local)
                "area_max": round(float(local.area_max or 0.0), 2),
                "descripcion": local.descripcion,
                "grupo": local.grupo, "criticidad": local.criticidad,
                "puerta_ancho": local.puerta_ancho,
                "circulacion_min": local.circulacion_min,
                "instalaciones": list(local.instalaciones),
                "copia": copia})
    total = round(sum(r["area_m2"] for r in renglones), 2)
    grupos: Dict[str, Dict[str, Any]] = {}
    for r in renglones:
        g = r.get("grupo", "") or "General"
        slot = grupos.setdefault(g, {"locales": 0, "area_m2": 0.0})
        slot["locales"] += 1
        slot["area_m2"] = round(slot["area_m2"] + r["area_m2"], 2)
    programa = {
        "servicio": item.codigo, "nombre": item.nombre,
        "descripcion": item.descripcion,
        "parametros": usados, "renglones": renglones,
        "totales": {"locales": len(renglones), "area_m2": total,
                    "grupos": grupos},
        "flujos": list(item.flujos), "notas": list(item.notas),
        "avisos": avisos,
    }
    programa["validacion"] = validar_programa(programa)
    return programa


# ---------------------------------------------------------------------------
# 3) VALIDACIÓN FUNCIONAL (DNA + catálogo)
# ---------------------------------------------------------------------------

def _dna_de(ctx_unused: Any, uso: str) -> Any:
    """DNA del uso sin depender de ctx (registry por defecto)."""
    try:
        from domain.knowledge import SpaceDNARegistry
        from app.paths import resource_path
        import os
        registro = SpaceDNARegistry()
        path = resource_path("knowledge", "space_dna.json")
        if os.path.exists(path):
            registro.load_file(path)
        return registro.get(uso)
    except Exception:  # noqa: BLE001 — sin DNA: sin reglas
        return None


def validar_programa(programa: Dict[str, Any]) -> List[Dict[str, str]]:
    """Checks del servicio: áreas vs DNA, críticos presentes,
    adyacencias a verificar, puertas recomendadas, flujos y notas.
    Estados: ok | aviso | info | fallo."""
    renglones = programa.get("renglones", [])
    resultado: List[Dict[str, str]] = []

    # AREAS vs DNA ---------------------------------------------------------
    fallos, avisos = [], []
    for r in renglones:
        dna = _dna_de(None, r["space_type"])
        minimo = float(getattr(dna, "minimum_area", 0.0) or 0.0) \
            if dna is not None else 0.0
        if minimo and r["area_m2"] + 1e-9 < minimo:
            (avisos if r["area_m2"] >= r.get("area_min", 0) else fallos
             ).append(f"{r['nombre']}: {r['area_m2']:.2f} m2 < mínimo "
                      f"del uso {r['space_type']} ({minimo:.2f} m2)")
    if fallos or avisos:
        resultado.append({
            "codigo": "AREAS", "nombre": "Áreas frente al DNA del uso",
            "estado": "fallo" if fallos else "aviso",
            "detalle": "; ".join(fallos + avisos)})
    else:
        resultado.append({
            "codigo": "AREAS", "nombre": "Áreas frente al DNA del uso",
            "estado": "ok",
            "detalle": f"los {len(renglones)} locales cumplen su "
                       "mínimo del uso"})

    # CRITICOS ---------------------------------------------------------------
    item = specs.servicio(programa.get("servicio", ""))
    criticos = [l.nombre for l in item.locales if l.critico]
    presentes = {r["nombre"].split(" 1")[0] for r in renglones}
    ausentes = [n for n in criticos
                if not any(p == n or p.startswith(n + " ") or
                           n.startswith(p) for p in presentes)]
    resultado.append({
        "codigo": "CRITICOS",
        "nombre": "Locales críticos presentes",
        "estado": "ok" if not ausentes else "aviso",
        "detalle": ("todos los críticos están en el programa" if not
                    ausentes else
                    "sin locales críticos: " + ", ".join(ausentes) +
                    " (el servicio queda mutilado)")})

    # ADYACENCIAS ------------------------------------------------------------
    pares = []
    nombres_de = {}
    for r in renglones:
        nombres_de.setdefault(r["codigo"], r["nombre"])
    vistos = set()
    for r in renglones:
        for adj in r["adjacencias"]:
            par = tuple(sorted((r["codigo"], adj)))
            if adj in nombres_de and par not in vistos:
                vistos.add(par)
                pares.append(
                    f"{nombres_de[r['codigo']]} con "
                    f"{nombres_de[adj]}")
    if pares:
        resultado.append({
            "codigo": "ADYACENCIAS",
            "nombre": "Conexiones directas a verificar",
            "estado": "info",
            "detalle": "; ".join(pares)})
    else:
        resultado.append({
            "codigo": "ADYACENCIAS",
            "nombre": "Conexiones directas a verificar",
            "estado": "info",
            "detalle": "el catálogo no exige pares concretos"})

    # PUERTAS recomendadas: catálogo v2.0 (todos los locales con ancho
    # declarado) + DNA de los críticos
    recomendadas = []
    vistas = set()
    for r in renglones:
        if r["nombre"] in vistas:
            continue
        ancho = float(r.get("puerta_ancho") or 0.0)
        fuente = ""
        if ancho:
            fuente = "catalogo"
        elif r["critico"]:
            dna = _dna_de(None, r["space_type"])
            if dna is not None:
                try:
                    neufert = dna.metadata.get("neufert") or {} \
                        if isinstance(dna.metadata, dict) else {}
                    ancho = float(neufert.get("puerta_m") or 0.0)
                except (TypeError, ValueError, AttributeError):
                    ancho = 0.0
                if ancho:
                    fuente = "DNA"
        if ancho:
            vistas.add(r["nombre"])
            recomendadas.append(
                f"{r['nombre']}: {ancho:.2f} m ({fuente})")
    if recomendadas:
        resultado.append({
            "codigo": "PUERTAS",
            "nombre": "Puertas recomendadas (catalogo/DNA)",
            "estado": "info",
            "detalle": "; ".join(recomendadas)})

    # CIRCULACION mínima del catálogo frente al pasillo del asistente
    circulas = [float(r.get("circulacion_min") or 0.0)
                for r in renglones]
    maxima = max(circulas) if circulas else 0.0
    if maxima > 0:
        if maxima > PASILLO_ANCHO + 1e-9:
            resultado.append({
                "codigo": "CIRCULACION",
                "nombre": "Circulacion minima del servicio",
                "estado": "aviso",
                "detalle": f"el servicio pide {maxima:.2f} m y el "
                           f"pasillo del asistente mide "
                           f"{PASILLO_ANCHO:.2f} m: amplielo al aplicar "
                           "o verifique recorridos"})
        else:
            resultado.append({
                "codigo": "CIRCULACION",
                "nombre": "Circulacion minima del servicio",
                "estado": "ok",
                "detalle": f"el pasillo del asistente "
                           f"({PASILLO_ANCHO:.2f} m) cubre la circulacion "
                           f"minima pedida ({maxima:.2f} m)"})

    # CRITICIDAD por niveles (seccion 25) -------------------------------
    niveles: Dict[int, int] = {}
    for r in renglones:
        nivel = int(r.get("criticidad") or 0)
        if nivel:
            niveles[nivel] = niveles.get(nivel, 0) + 1
    if niveles:
        detalle = "; ".join(
            f"nivel {n}: {c} local(es)" for n, c in sorted(niveles.items()))
        resultado.append({
            "codigo": "CRITICIDAD",
            "nombre": "Niveles de criticidad (seccion 25)",
            "estado": "info", "detalle": detalle})

    # RELACIONES PROHIBIDAS declaradas (regla 05) -----------------------
    prohibidas = []
    for l in item.locales:
        for texto in (l.relaciones.get("prohibidas") or []):
            prohibidas.append(f"{l.nombre}: evitar {texto}")
    if prohibidas:
        resultado.append({
            "codigo": "PROHIBIDAS",
            "nombre": "Relaciones prohibidas (regla 05)",
            "estado": "info",
            "detalle": "; ".join(prohibidas)})

    # SEPARACION limpio/sucio (regla 06) --------------------------------
    flujos_local = {r["flujo"] for r in renglones}
    if "limpio" in flujos_local and "sucio" in flujos_local:
        resultado.append({
            "codigo": "SEPARACION",
            "nombre": "Circuitos limpio y sucio (regla 06)",
            "estado": "info",
            "detalle": "el programa mezcla locales limpios y sucios: "
                       "colocalos en bandas separadas y nunca con "
                       "conexion directa"})

    # FLUJOS y NOTAS del catálogo ---------------------------------------------
    for i, flujo in enumerate(programa.get("flujos", []), start=1):
        resultado.append({"codigo": f"FLUJO{i}", "nombre": "Flujo "
                          "funcional", "estado": "info",
                          "detalle": flujo})
    for i, nota in enumerate(programa.get("notas", []), start=1):
        resultado.append({"codigo": f"NOTA{i}", "nombre": "Nota de "
                          "diseño", "estado": "info", "detalle": nota})
    # checks declarados del catálogo (recordatorio funcional)
    for c in item.checks:
        resultado.append({"codigo": c.get("codigo", "?"),
                          "nombre": c.get("nombre", ""),
                          "estado": "info",
                          "detalle": c.get("descripcion", "")})
    return resultado


# ---------------------------------------------------------------------------
# 4) APLICAR AL PROYECTO (entidades reales)
# ---------------------------------------------------------------------------

def _empaquetar(programa: Dict[str, Any],
                origen: Tuple[float, float]) -> List[Dict[str, Any]]:
    """Estrategia de pasillo: corredor central de 2.40 m y los locales
    a dos bandas (norte y sur) en filas empaquetadas. Devuelve cada
    renglón con su rectángulo (esquinas antihorarias) y el pasillo."""
    ox, oy = origen
    norte, sur = [], []
    for i, r in enumerate(programa["renglones"]):
        (norte if i % 2 == 0 else sur).append(r)
    def _fila(items: List[Dict[str, Any]]) -> List[float]:
        anchos: List[float] = []
        for r in items:
            anchos.append(max(r["ancho_m"], r["area_m2"] / FONDO_MAX))
        return anchos
    largo = max(6.0, max(sum(_fila(norte)) if norte else 0.0,
                         sum(_fila(sur)) if sur else 0.0))
    pasillo = {"nombre": f"Pasillo de {programa['nombre']}",
               "space_type": "CORRIDOR",
               "rect": [(ox, oy), (ox + largo, oy),
                        (ox + largo, oy + PASILLO_ANCHO),
                        (ox, oy + PASILLO_ANCHO)],
               "area_m2": round(largo * PASILLO_ANCHO, 2),
               "flujo": "publico", "critico": False, "req": [],
               "adjacencias": [], "descripcion":
                   "Distribución del servicio (salud con camillas)",
               "codigo": "PASILLO", "copia": 1,
               "ancho_m": round(largo, 2), "fondo_m": PASILLO_ANCHO}
    colocados: List[Dict[str, Any]] = []
    def _coloca(items: List[Dict[str, Any]], banda: int) -> None:
        x = ox
        for r in items:
            ancho = max(r["ancho_m"], r["area_m2"] / FONDO_MAX)
            fondo = r["fondo_m"]
            if banda > 0:      # norte: sube desde el pasillo
                rect = [(x, oy + PASILLO_ANCHO),
                        (x + ancho, oy + PASILLO_ANCHO),
                        (x + ancho, oy + PASILLO_ANCHO + fondo),
                        (x, oy + PASILLO_ANCHO + fondo)]
            else:              # sur: baja desde el pasillo
                rect = [(x, oy), (x + ancho, oy),
                        (x + ancho, oy - fondo), (x, oy - fondo)]
            r["rect"] = rect
            x += ancho
            colocados.append(r)
    _coloca(norte, 1)
    _coloca(sur, -1)
    colocados.insert(0, pasillo)
    return colocados


def _nivel_destino(ctx: Any, item: "specs.Servicio", nivel_ref: str) \
        -> Any:
    """El nivel pedido; si el proyecto no tiene ninguno, edificio
    mínimo con un nivel nuevo al vuelo."""
    arch = ArchitectureService(ctx)
    if nivel_ref:
        return arch.get_level_by_name_or_code(nivel_ref)
    niveles = ctx.architecture.list("LEVEL", ctx.project.id)
    if niveles:
        raise DomainError(
            message="Indique el nivel donde aplicar el servicio",
            code="ARQ-SRV-003",
            context={"niveles": [lv.name for lv in niveles]},
            suggested_action="Elija un nivel existente en el "
                             "asistente o use un proyecto vacío.")
    edificio = arch.create_building(f"Edificio {item.nombre}")
    return arch.create_level(f"Servicio {item.nombre}",
                             elevation_m=0.0, height_m=3.0,
                             building_id=edificio.id)


def _nombre_unico(ctx: Any, level_id: str, nombre: str,
                  usados: set) -> str:
    if not usados:
        usados.update(
            s.name.lower()
            for s in ctx.architecture.list("SPACE", ctx.project.id)
            if getattr(s, "level_id", None) == level_id)
    candidato = nombre
    n = 2
    while candidato.lower() in usados:
        candidato = f"{nombre} {n}"
        n += 1
    usados.add(candidato.lower())
    return candidato


def aplicar_servicio(ctx: Any, codigo: str,
                     params: Optional[Dict[str, Any]] = None,
                     nivel_ref: str = "",
                     origen: Tuple[float, float] = (0.0, 0.0),
                     trazar_muros: bool = False) -> Dict[str, Any]:
    """Aplica el servicio al proyecto: zona SERVICE, pasillo, locales
    del programa, relaciones con el pasillo y (opcional) muros.
    Devuelve un resumen con lo creado y la validación."""
    item = specs.servicio(codigo)
    programa = programa_servicio(codigo, params)
    arch = ArchitectureService(ctx)
    nivel = _nivel_destino(ctx, item, nivel_ref)
    colocados = _empaquetar(programa, tuple(origen))

    zona = arch.create_zone(f"Servicio {item.nombre}", "SERVICE")
    usados: set = set()
    creados: List[str] = []
    pasillo_code = ""
    relaciones = 0
    avisos = list(programa["avisos"])

    for r in colocados:
        es_pasillo = r["codigo"] == "PASILLO"
        nombre = _nombre_unico(ctx, nivel.id, r["nombre"], usados)
        espacio = arch.create_space(nivel.name, nombre, r["space_type"],
                                    [tuple(p) for p in r["rect"]])
        arch.set_space_zone(espacio.id, zona.id)
        if es_pasillo:
            pasillo_code = espacio.code
        else:
            if pasillo_code:
                arch.add_relationship(espacio.id, pasillo_code,
                                      "adjacent_to",
                                      source=ORIGEN_SERVICIO)
                relaciones += 1
        if trazar_muros and not es_pasillo:
            rect = r["rect"]
            for i in range(4):
                arch.create_wall(nivel.name, tuple(rect[i]),
                                 tuple(rect[(i + 1) % 4]),
                                 thickness_m=ESPESOR_MURO)
        creados.append(espacio.code)
        r["creado"] = espacio.code

    if trazar_muros:
        avisos.append("muros trazados por local: las aristas "
                      "compartidas quedan duplicadas, remátelas con "
                      "las herramientas CAD (recortar/alargar)")
    resumen = {
        "operacion": "aplicar servicio",
        "servicio": item.codigo, "nombre": item.nombre,
        "nivel": nivel.name, "zona": zona.code,
        "pasillo": pasillo_code, "locales": creados,
        "creados": creados, "relaciones": relaciones,
        "parametros": dict(programa["parametros"]),
        "totales": dict(programa["totales"]),
        "validacion": programa["validacion"],
        "avisos": avisos,
        "renglones": programa["renglones"],
    }
    return resumen


# ---------------------------------------------------------------------------
# 5) TEXTO (cp1252, sin flechas)
# ---------------------------------------------------------------------------

def texto_programa(programa: Dict[str, Any]) -> str:
    """El programa listo para consola/cuadro de texto; con subtotales
    por grupo funcional cuando el catálogo los declara (sección 20)."""
    lineas: List[str] = []
    lineas.append(f"PROGRAMA DEL SERVICIO - {programa['nombre']} "
                  f"({programa['servicio']})")
    lineas.append(f"Parámetros: " + ", ".join(
        f"{k}={v:g}" if isinstance(v, (int, float))
        else f"{k}={'sí' if v else 'no'}"
        for k, v in programa["parametros"].items()))
    lineas.append("")
    grupos = programa.get("totales", {}).get("grupos") or {}
    if grupos:
        vistos: set = set()
        for r in programa["renglones"]:
            g = r.get("grupo", "") or "General"
            if g in vistos:
                continue
            vistos.add(g)
            slot = grupos.get(g) or {"locales": 0, "area_m2": 0.0}
            lineas.append(f"--- {g}: {slot['locales']} local(es), "
                          f"{slot['area_m2']:.2f} m2")
            for x in programa["renglones"]:
                if (x.get("grupo", "") or "General") == g:
                    lineas.append(_linea_renglon(x))
            lineas.append("")
    else:
        for r in programa["renglones"]:
            lineas.append(_linea_renglon(r))
    lineas.append(f"TOTAL: {programa['totales']['locales']} local(es), "
                  f"{programa['totales']['area_m2']:.2f} m2")
    for aviso in programa["avisos"]:
        lineas.append(f"aviso: {aviso}")
    if programa["flujos"]:
        lineas.append("")
        lineas.append("Flujos funcionales:")
        for flujo in programa["flujos"]:
            lineas.append(f"  - {flujo}")
    return "\n".join(lineas)


def _linea_renglon(r: Dict[str, Any]) -> str:
    """La línea de tabla de un renglón del programa (formato único)."""
    marca = "[C]" if r["critico"] else "   "
    return (f"{marca} {r['nombre']:<34} {r['space_type']:<20} "
            f"{r['area_m2']:>7.2f} m2  ({r['ancho_m']:.2f} x "
            f"{r['fondo_m']:.2f} m)  flujo {r['flujo']}")


def texto_validacion(validacion: List[Dict[str, str]]) -> str:
    """Checks del servicio en líneas cp1252."""
    lineas: List[str] = ["VALIDACIÓN FUNCIONAL DEL SERVICIO", ""]
    for c in validacion:
        marca = {"ok": "[x]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(c["estado"], "[?]")
        detalle = f" - {c['detalle']}" if c.get("detalle") else ""
        lineas.append(f"{marca} {c['codigo']} {c['nombre']}{detalle}")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# 6) DOCUMENTOS DEL SERVICIO (catálogo v2.0, «servicios médicos»)
# ---------------------------------------------------------------------------

def texto_ficha_local(codigo_servicio: str, codigo_local: str) -> str:
    """La FICHA DE LOCAL de la sección 30 del documento médico:
    identificación, superficies, cotas, instalaciones, acabados,
    equipamiento y relaciones del local pedido."""
    item = specs.servicio(codigo_servicio)
    local = item.local(str(codigo_local or "").strip().upper())
    if local is None:
        raise DomainError(
            message=f"El servicio {item.nombre} no tiene un local "
                    f"con código {codigo_local}",
            code="ARQ-SRV-007",
            context={"servicio": item.codigo,
                     "locales": [l.codigo for l in item.locales]},
            suggested_action="Elija un local de la tabla del programa.")
    indice = item.locales.index(local) + 1
    sigla = item.codigo[:2] if len(item.codigo) >= 2 else item.codigo
    lineas: List[str] = [f"FICHA DE LOCAL {sigla}-{indice:03d}", ""]
    lineas.append(f"SERVICIO: {item.nombre}")
    lineas.append(f"LOCAL: {local.nombre} ({local.codigo})")
    lineas.append(f"USO (DNA): {local.space_type}")
    if local.grupo:
        lineas.append(f"GRUPO: {local.grupo}")
    if local.descripcion:
        lineas.append(f"FUNCION: {local.descripcion}")
    lineas.append("")
    lineas.append(f"SUPERFICIE_MIN: {local.area_min:.2f} m2"
                  if local.area_min else "SUPERFICIE_MIN: -")
    lineas.append(f"SUPERFICIE_MAX: {local.area_max:.2f} m2"
                  if local.area_max else "SUPERFICIE_MAX: abierta")
    if local.puerta_ancho:
        lineas.append(f"PUERTA: {local.puerta_ancho:.2f} m")
    if local.circulacion_min:
        lineas.append(f"CIRCULACION: {local.circulacion_min:.2f} m")
    if local.criticidad:
        lineas.append(f"CRITICIDAD: nivel {local.criticidad} "
                      f"({specs.NIVELES_CRITICIDAD.get(
                          local.criticidad, 'segun funcion')})")
    lineas.append(f"FLUJO: {local.flujo}")
    if local.instalaciones:
        lineas.append("")
        lineas.append("INSTALACIONES:")
        for codigo in local.instalaciones:
            etiqueta = specs.ETIQUETAS_INSTALACIONES.get(codigo, codigo)
            lineas.append(f"  - {etiqueta}: SI")
    if local.acabados:
        lineas.append("")
        lineas.append("ACABADOS:")
        for clave in ("piso", "paredes", "techo"):
            if local.acabados.get(clave):
                lineas.append(f"  - {clave.upper()}: "
                              f"{local.acabados[clave]}")
    if local.equipamiento:
        lineas.append("")
        lineas.append("EQUIPAMIENTO (generador de espacio, seccion 21):")
        for equipo in local.equipamiento:
            lineas.append(f"  - {equipo}")
    if local.req:
        lineas.append("")
        lineas.append("REQUISITOS:")
        for req in local.req:
            lineas.append(f"  - {req}")
    relaciones = local.relaciones or {}
    if any(relaciones.get(k) for k in
           ("obligatorias", "deseables", "prohibidas")):
        lineas.append("")
        lineas.append("RELACIONES:")
        for texto in relaciones.get("obligatorias") or []:
            lineas.append(f"  - OBLIGATORIA: {texto}")
        for texto in relaciones.get("deseables") or []:
            lineas.append(f"  - DESEABLE: {texto}")
        for texto in relaciones.get("prohibidas") or []:
            lineas.append(f"  - PROHIBIDA: {texto}")
    if local.observaciones:
        lineas.append("")
        lineas.append(f"OBSERVACION: {local.observaciones}")
    return "\n".join(lineas)


def texto_matriz_instalaciones(codigo_servicio: str) -> str:
    """La MATRIZ DE INSTALACIONES del servicio (sección 22)."""
    item = specs.servicio(codigo_servicio)
    lineas: List[str] = [f"MATRIZ DE INSTALACIONES - {item.nombre} "
                         "(seccion 22)", ""]
    if item.matriz_instalaciones:
        for concepto, nivel in item.matriz_instalaciones.items():
            lineas.append(f"  {concepto:<20} {nivel}")
    else:
        lineas.append("  el catalogo no declara matriz para este "
                      "servicio (niveles por local en la ficha)")
    lineas.append("")
    lineas.append("Niveles orientativos: el diseno definitivo los "
                  "confirma (normativa sanitaria, HVAC, electrica y "
                  "de radioproteccion).")
    return "\n".join(lineas)


def texto_relaciones_servicios(codigo_servicio: str) -> str:
    """Las RELACIONES CON OTROS SERVICIOS (sección 17), con la
    recomendación de proximidad correspondiente."""
    item = specs.servicio(codigo_servicio)
    lineas: List[str] = [f"RELACIONES ENTRE SERVICIOS - {item.nombre} "
                         "(seccion 17)", ""]
    if not item.relaciones_servicios:
        lineas.append("  el catalogo no declara relaciones para este "
                      "servicio")
        return "\n".join(lineas)
    disponibles = {s.codigo: s.nombre for s in specs.cargar_servicios()}
    for r in item.relaciones_servicios:
        nivel = r.get("nivel", "")
        marca = "[!]" if nivel in ("MUY ALTA", "ALTA") else "[i]"
        destino = r.get("servicio", "")
        nombre = disponibles.get(destino, destino + " (fuera del "
                                 "catalogo)")
        lineas.append(f"  {marca} {destino}: {nivel} - planifique "
                      f"proximidad con {nombre}")
    lineas.append("")
    lineas.append("MUY ALTA y ALTA: colas el servicio vecino en la "
                  "misma planta o con recorrido vertical directo; "
                  "MEDIA: planta cercana; CONTROLADA/BAJA: separado "
                  "del publico.")
    return "\n".join(lineas)


def texto_flujos(codigo_servicio: str) -> str:
    """Los FLUJOS del servicio (sección 18) más los cuatro flujos
    hospitalarios canónicos del catálogo."""
    item = specs.servicio(codigo_servicio)
    lineas: List[str] = [f"FLUJOS HOSPITALARIOS - {item.nombre}", ""]
    lineas.append("Flujos del servicio:")
    if item.flujos:
        for flujo in item.flujos:
            lineas.append(f"  - {flujo}")
    else:
        lineas.append("  (sin flujos declarados)")
    globales = specs.flujos_hospitalarios()
    if globales:
        lineas.append("")
        lineas.append("Flujos hospitalarios canonicos (seccion 18):")
        for flujo in globales:
            lineas.append(f"  - {flujo}")
    return "\n".join(lineas)


def texto_reglas_generacion() -> str:
    """Las 20 REGLAS de generación automática de plantas (sección 24)."""
    lineas: List[str] = ["REGLAS DE GENERACION AUTOMATICA DE PLANTAS "
                         "(seccion 24)", ""]
    for regla in specs.reglas_generacion():
        lineas.append(f"  {regla}")
    lineas.append("")
    lineas.append("El motor de generación y el asistente aplican las "
                  "que tienen soporte (superficies, puertas, "
                  "circulación, criticidad, separación limpio/sucio, "
                  "prohibidas); las demás quedan como verificación "
                  "de proyecto.")
    return "\n".join(lineas)


def texto_resumen_servicio(resumen: Dict[str, Any]) -> str:
    """Una línea amable tras aplicar (barra de estado)."""
    return (f"Servicio {resumen['nombre']} aplicado en "
            f"{resumen['nivel']}: {resumen['totales']['locales']} "
            f"local(es), {resumen['totales']['area_m2']:.2f} m2, zona "
            f"{resumen['zona']}, pasillo {resumen['pasillo'] or '-'}")


__all__ = [
    "programa_servicio", "validar_programa", "aplicar_servicio",
    "texto_programa", "texto_validacion", "texto_resumen_servicio",
    "texto_ficha_local", "texto_matriz_instalaciones",
    "texto_relaciones_servicios", "texto_flujos",
    "texto_reglas_generacion",
    "PASILLO_ANCHO", "ORIGEN_SERVICIO",
]
