#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARQ GEN — Servidor JSON-RPC 2.0 del SIDECAR (FASE A + FASE C Tauri).

Canal estándar de la arquitectura del «ARQ GEN TAURI.txt» v3.0:
    Tauri (Rust)  <->  stdin/stdout JSON-RPC  <->  Motor Python

Protocolo (1 petición por línea, 1 respuesta por línea, UTF-8):
    -> {"jsonrpc":"2.0","id":1,"method":"ping","params":{}}
    <- {"jsonrpc":"2.0","id":1,"result":{"pong":true,"app_version":"..."}}

Métodos FASE A (v3.48.0):
    ping                -> latido + versión (barato, para el estado de la UI)
    version             -> versión del motor, Python, plataforma y acelerador
    selftest            -> las comprobaciones internas completas (pesado)
    generar_quick       -> programa_quick(texto) + ajustar(contorno)
    generar_edificacion -> programa_edificacion(fichas) + ajustar(contorno)

Métodos FASE C (v3.50.0) — la UI web completa:
    catalogo            -> los space_types del DNA (selector de fichas)
    generar_radial      -> plan_radial (planta radial con núcleo circular)
    generar_y           -> plan_y (torre en Y real, alas desiguales)
    generar_x           -> plan_x (hospital en X real, barras cruzadas)
    generar_zonas       -> ajustar_zonas (multi-ala, compuesto "zonas")
    generar_rejilla     -> repartir_rejilla (edificio tipo, compuesto)
    aplicar_exportar    -> aplicar_(plan|zonas) + exportar_todo (7 formatos)
    proyecto_abrir      -> vista previa de una instantánea JSON (.json)
    vista_3d            -> caras proyectadas con identidad de entidad
    elemento_3d         -> propiedades editables de una entidad
    editar_3d           -> edición validada del modelo de sesión
    crear_escalera_3d   -> añadir escalera sin reemplazar las existentes
    borrar_escalera_3d  -> borrar una escalera con revisión y deshacer
    deshacer_3d / rehacer_3d -> historial de la sesión web
    proyecto_editar_3d  -> importar una instantánea a una sesión editable

SESIÓN: cada generar_* guarda el análisis COMPLETO en una sesión LRU
(máx. 8) y devuelve un ``id``. La vista 3D materializa un proyecto temporal
por sesión; al editarlo, la exportación reutiliza ese mismo proyecto.

Errores JSON-RPC: -32700 (JSON inválido), -32601 (método desconocido),
-32600 (petición mal formada), -32602 (parámetros/domain: DomainError
llega con data.codigo ARQ-DDI-0xx), -32603 (fallo interno con mensaje
corto). El stderr queda RESERVADO para diagnóstico; stdout es solo
protocolo. Determinista y offline: no lee red, no usa azar sin semilla.
"""
from __future__ import annotations

import atexit
import json
import math
import os
import platform
import sys
import tempfile
import traceback
from collections import OrderedDict
from contextlib import contextmanager, nullcontext

# Bootstrap de rutas: el sidecar puede lanzarse como script suelto
# (python app/rpc_server.py) o por el subcomando rpc del ejecutable.
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import core  # noqa: E402
import domain.desde_dibujo as dd  # noqa: E402
from core.errors import ARQGenError  # noqa: E402

# Métodos expuestos; el resto devuelve -32601.
_METODOS = ("ping", "version", "selftest", "generar_quick",
            "generar_edificacion", "catalogo", "generar_radial",
            "generar_y", "generar_x", "generar_zonas", "generar_rejilla",
            "aplicar_exportar", "proyecto_abrir", "vista_3d",
            "elemento_3d", "editar_3d", "crear_escalera_3d", "borrar_escalera_3d",
            "proyecto_editar_3d", "deshacer_3d", "rehacer_3d")

# Claves que se recortan de cada local para la UI (el motor devuelve más).
_LOCAL_KEYS = ("codigo", "nombre", "space_type", "area_m2", "area_min",
               "ancho_m", "fondo_m", "flujo", "critico", "copias", "copia")

_TOTALES_KEYS = ("area_programa", "area_pasillos", "area_escaleras",
                 "area_patio", "area_contorno", "area_aprovechada",
                 "aprovechamiento_pct", "altura_total")

# Tamaño de la sesión LRU de análisis completos.
_SESION_MAX = 8
_SESION: "OrderedDict[str, dict]" = OrderedDict()
_CONTADOR_SESION = {"n": 0}
# Los modelos editables viven mientras su análisis permanezca en la LRU.
_PROYECTOS = {}


def _cerrar_proyecto(sid):
    entrada = _PROYECTOS.pop(sid, None)
    if entrada:
        try:
            entrada["ctx"].close()
        finally:
            entrada["temporal"].cleanup()


def _cerrar_proyectos():
    for sid in list(_PROYECTOS):
        _cerrar_proyecto(sid)


atexit.register(_cerrar_proyectos)


def _guardar_sesion(analisis: dict) -> str:
    """Guarda el análisis íntegro y devuelve su id (an1, an2, ...)."""
    _CONTADOR_SESION["n"] += 1
    sid = "an%d" % _CONTADOR_SESION["n"]
    _SESION[sid] = analisis
    _SESION.move_to_end(sid)
    while len(_SESION) > _SESION_MAX:
        expirado, _ = _SESION.popitem(last=False)
        _cerrar_proyecto(expirado)
    return sid


def _analisis_de(params: dict) -> dict:
    """Recupera el análisis completo de la sesión por su id."""
    sid = str(params.get("id") or "")
    if not sid:
        raise ValueError("falta el id del análisis (lo devuelve cada "
                         "método generar_*)")
    analisis = _SESION.get(sid)
    if analisis is None:
        raise ValueError("id de análisis desconocido o expirado "
                         "(la sesión guarda los últimos %d): %s"
                         % (_SESION_MAX, sid))
    _SESION.move_to_end(sid)
    return analisis


def _rect_listas(rect) -> list:
    """Convierte rects del motor (tuplas) en listas JSON [[x,y],...]."""
    return [[round(float(x), 4), round(float(y), 4)] for x, y in rect]


def _poligono_listas(polig) -> list:
    return [[round(float(x), 4), round(float(y), 4)]
            for x, y in (polig or [])]


def _local_resumido(local: dict) -> dict:
    out = {k: local.get(k) for k in _LOCAL_KEYS if k in local}
    polig = local.get("poligono")
    if polig:
        out["poligono"] = _poligono_listas(polig)
    else:
        rect = local.get("rect")
        if rect:
            out["poligono"] = _rect_listas(rect)
    if "ala" in local:
        out["ala"] = local.get("ala")
    return out


def _pasillo_resumido(pas: dict) -> dict:
    # Contrato FASE A: nombre, area_m2 y rect SIEMPRE; FASE C añade
    # poligono (pasillos radiales/Y/X) y ala (corredor de cada brazo).
    out = {"nombre": pas.get("nombre"), "area_m2": pas.get("area_m2")}
    if "ala" in pas:
        out["ala"] = pas.get("ala")
    out["rect"] = _rect_listas(pas.get("rect") or [])
    if pas.get("poligono"):
        out["poligono"] = _poligono_listas(pas.get("poligono"))
    return out


def _reparto_resumido(nivel: dict) -> dict:
    pasillo = nivel.get("pasillo")
    escalera = nivel.get("escalera")
    patio = nivel.get("patio")
    res = {
        "nivel": nivel.get("nivel"),
        "pasillo": None if not pasillo else _pasillo_resumido(pasillo),
        "escalera": None if not escalera else {
            "nombre": escalera.get("nombre"),
            "area_m2": escalera.get("area_m2"),
            "rect": _rect_listas(escalera.get("rect") or []),
        },
        "patio": None if not patio else {
            "nombre": patio.get("nombre"),
            "area_m2": patio.get("area_m2"),
            "rect": _rect_listas(patio.get("rect") or []),
        },
        "locales": [_local_resumido(l) for l in nivel.get("locales") or []],
        "dentro": nivel.get("dentro"),
    }
    if nivel.get("pasillos"):
        res["pasillos"] = [_pasillo_resumido(p)
                           for p in nivel.get("pasillos") or []]
    return res


def _metricas_de(analisis: dict) -> dict:
    """Métricas explicadas (spec §25/§26); None si el análisis no las
    soporta (compuestos). Nunca lanza."""
    try:
        met = dd.metricas_de(analisis)
        return {k: met.get(k) for k in
                ("niveles", "area_construida_m2", "area_util_m2",
                 "circulacion_pct", "ocupacion_pct", "cumplimiento_pct",
                 "locales_fuera", "puntuacion", "motivo")}
    except Exception:  # noqa: BLE001 — métricas best effort
        return None


def _ajuste_resumido(aj: dict, con_id: bool = True) -> dict:
    """Recorta la salida de ajustar()/plan_* al contrato de la UI."""
    res = {
        "tipo": str(aj.get("tipo") or "edificacion"),
        "niveles": aj.get("niveles"),
        "dentro_del_contorno": aj.get("dentro_del_contorno"),
        "sala_distribuidora": bool(aj.get("sala_distribuidora")),
        "totales": {k: aj.get("totales", {}).get(k) for k in _TOTALES_KEYS},
        "reparto": [_reparto_resumido(n) for n in aj.get("reparto") or []],
        "chaflanes": [
            {"nivel": c.get("nivel"), "local": c.get("local"),
             "cateto_m": c.get("cateto_m"), "perdida_m2": c.get("perdida_m2")}
            for c in (aj.get("chaflanes") or [])
        ],
        "avisos": list(aj.get("avisos") or []),
        "circulacion": list(aj.get("circulacion") or []),
    }
    res["metricas"] = _metricas_de(aj)
    if con_id:
        res["id"] = _guardar_sesion(aj)
    return res


def _compuesto_resumido(comp: dict) -> dict:
    """Resumen de un análisis COMPUESTO (zonas | rejilla) para la UI:
    cada ala/celda con su reparto y el total del conjunto."""
    res = {
        "tipo": str(comp.get("tipo") or "zonas"),
        "niveles": comp.get("niveles"),
        "dentro_del_contorno": comp.get("dentro_del_contorno"),
        "sala_distribuidora": bool(comp.get("sala_distribuidora")),
        "totales": {k: comp.get("totales", {}).get(k)
                    for k in _TOTALES_KEYS if k in (comp.get("totales")
                                                    or {})},
        "avisos": list(comp.get("avisos") or []),
        "zonas": [],
    }
    if comp.get("contorno"):
        res["contorno"] = _rect_listas(comp.get("contorno"))
    pc = comp.get("pasillo_central")
    if pc:
        res["pasillo_central"] = _pasillo_resumido(pc)
    for zona in comp.get("zonas") or []:
        item = {
            "rol": (zona or {}).get("rol"),
            "area_m2": (zona or {}).get("area_m2"),
            "contorno": _rect_listas((zona or {}).get("contorno") or []),
        }
        aj = (zona or {}).get("analisis") or {}
        if aj:
            item["reparto"] = [_reparto_resumido(n)
                               for n in aj.get("reparto") or []]
            item["totales"] = {k: aj.get("totales", {}).get(k)
                               for k in _TOTALES_KEYS
                               if k in (aj.get("totales") or {})}
            item["avisos"] = list(aj.get("avisos") or [])
        res["zonas"].append(item)
    res["id"] = _guardar_sesion(comp)
    return res


def _contorno(params: dict, defecto=None) -> list:
    """Contorno [[x,y],...] desde params; valida >= 3 vértices."""
    cont = params.get("contorno") if "contorno" in params else defecto
    if not cont:
        raise ValueError("falta el contorno [[x,y],...]")
    cont = [list(p) for p in cont]
    if len(cont) < 3:
        raise ValueError("el contorno necesita al menos 3 vértices")
    return cont


def _programa_de(params: dict):
    """Programa desde texto quick (texto) o fichas [{space_type,
    cantidad}]; es el '¿qué se construye?' de la UI FASE C."""
    texto = params.get("texto")
    fichas = params.get("fichas")
    if texto and str(texto).strip():
        return dd.programa_quick(str(texto),
                                 str(params.get("nombre") or "Edificio"))
    if isinstance(fichas, list) and fichas:
        fichas = [{"space_type": str(f.get("space_type")),
                   "cantidad": int(f.get("cantidad", 1))} for f in fichas]
        return dd.programa_edificacion(
            fichas, str(params.get("nombre") or "Edificación RPC"))
    raise ValueError("falta el programa: {texto} o {fichas:[{space_type,"
                     " cantidad},...]}")

# ---------------------------------------------------------------- métodos ---
def _m_ping(_params: dict) -> dict:
    return {"pong": True, "app_version": core.APP_VERSION}


def _m_version(_params: dict) -> dict:
    modo = "python"
    try:
        from core import acelerador
        modo = acelerador.modo()
    except Exception:  # noqa: BLE001 — el informe del acelerador es best effort
        pass
    return {"app_version": core.APP_VERSION,
            "python": sys.version.split()[0],
            "plataforma": platform.platform(terse=True),
            "modo_acelerador": modo}


def _m_selftest(_params: dict) -> dict:
    from app.selftest import run_selftest
    ok, checks = run_selftest(console=False)
    return {"ok": bool(ok), "checks": len(checks)}


def _ajuste_valido(params: dict) -> str:
    """Ajuste libre del motor (ideal|minimo|medio|estricto); FASE C lo
    pasa tal cual, con ideal por defecto (compat FASE A)."""
    ajuste = str(params.get("ajuste") or "ideal").strip().lower()
    return ajuste if ajuste in ("ideal", "minimo", "medio", "estricto") \
        else "ideal"


def _m_generar_quick(params: dict) -> dict:
    texto = params.get("texto")
    if not texto or not str(texto).strip():
        raise ValueError("falta el texto del programa (quick-spec)")
    prog = dd.programa_quick(str(texto), str(params.get("clave") or "rpc"))
    cont = _contorno(params)
    aj = dd.ajustar(prog, cont,
                    encaje_estricto=True,
                    ajuste=_ajuste_valido(params),
                    patio=bool(params.get("patio", False)),
                    chaflanes=bool(params.get("chaflanes", True)))
    res = _ajuste_resumido(aj)
    res["programa"] = {"nombre": prog.get("nombre"),
                       "renglones": [
                           {k: r.get(k) for k in _LOCAL_KEYS if k in r}
                           for r in prog.get("renglones") or []],
                       "avisos": list(prog.get("avisos") or [])}
    return res


def _m_generar_edificacion(params: dict) -> dict:
    fichas = params.get("fichas")
    if not isinstance(fichas, list) or not fichas:
        raise ValueError("falta fichas [{space_type, cantidad}, ...]")
    fichas = [{"space_type": str(f.get("space_type")),
               "cantidad": int(f.get("cantidad", 1))} for f in fichas]
    nombre = str(params.get("nombre") or "Edificación RPC")
    prog = dd.programa_edificacion(fichas, nombre)
    cont = _contorno(params)
    niveles = params.get("niveles")
    if niveles is not None:
        niveles = int(niveles)
    aj = dd.ajustar(prog, cont,
                    encaje_estricto=True,
                    ajuste=_ajuste_valido(params),
                    patio=bool(params.get("patio", False)),
                    niveles_deseados=niveles,
                    chaflanes=bool(params.get("chaflanes", True)))
    return _ajuste_resumido(aj)


def _m_catalogo(_params: dict) -> dict:
    """Catálogo DNA completo para el selector de fichas de la UI."""
    reg = core.registry if hasattr(core, "registry") else None
    if reg is None:
        from services.context import ApplicationContext
        reg = ApplicationContext().dna_registry
    tipos = []
    for code in sorted(reg.types()):
        dna = reg.get(code)
        meta = getattr(dna, "metadata", {}) or {}
        tipos.append({
            "code": code,
            "nombre": getattr(dna, "name_es", "") or code,
            "area_min": getattr(dna, "minimum_area", None),
            "area_pref": getattr(dna, "preferred_area", None),
            "mojado": bool(getattr(dna, "wet_zone", False)),
            "dia": bool(getattr(dna, "daylight", False)),
            "flujo": meta.get("flujo") or meta.get("flujo_") or None,
        })
    return {"version": getattr(reg, "version", ""), "total": len(tipos),
            "tipos": tipos}


def _num(params: dict, clave: str, defecto: float) -> float:
    try:
        return float(params.get(clave, defecto))
    except (TypeError, ValueError):
        raise ValueError("el parámetro %s debe ser numérico" % clave)


def _niveles_de(params: dict) -> int:
    try:
        return int(params.get("niveles", 1))
    except (TypeError, ValueError):
        raise ValueError("niveles debe ser un entero (1-20)")


def _m_generar_radial(params: dict) -> dict:
    from domain.radial import plan_radial
    prog = _programa_de(params)
    aj = plan_radial(prog,
                     radio_ext=_num(params, "radio_ext", 12.0),
                     radio_int=_num(params, "radio_int", 0.0),
                     sectores=int(_num(params, "sectores", 8)),
                     corredor_m=_num(params, "corredor_m", 1.5),
                     radio_nucleo=_num(params, "radio_nucleo", 0.0),
                     niveles=_niveles_de(params))
    return _ajuste_resumido(aj)


def _m_generar_y(params: dict) -> dict:
    from domain.radial import plan_y
    prog = _programa_de(params)
    largos = params.get("largos_alas")
    if largos is not None and not (isinstance(largos, list) and largos):
        raise ValueError("largos_alas debe ser una lista de números")
    aj = plan_y(prog,
                radio_nucleo=_num(params, "radio_nucleo", 7.0),
                largo_ala=_num(params, "largo_ala", 16.0),
                ancho_ala=_num(params, "ancho_ala", 11.0),
                n_alas=int(_num(params, "n_alas", 3)),
                corredor_m=_num(params, "corredor_m", 1.5),
                cabecera_m=_num(params, "cabecera_m", 0.0),
                largos_alas=([float(x) for x in largos]
                             if largos else None),
                niveles=_niveles_de(params))
    return _ajuste_resumido(aj)


def _m_generar_x(params: dict) -> dict:
    from domain.radial import plan_x
    prog = _programa_de(params)
    aj = plan_x(prog,
                largo_barra=_num(params, "largo_barra", 64.0),
                ancho_barra=_num(params, "ancho_barra", 14.0),
                corredor_m=_num(params, "corredor_m", 2.0),
                cabecera_m=_num(params, "cabecera_m", 0.0),
                angulo=_num(params, "angulo_grados", 45.0) * 3.141592653589793
                / 180.0,
                niveles=_niveles_de(params))
    return _ajuste_resumido(aj)


def _m_generar_zonas(params: dict) -> dict:
    zonas = params.get("zonas")
    if not isinstance(zonas, list) or len(zonas) < 2:
        raise ValueError("generar_zonas necesita zonas: "
                         "[{contorno, rol}, ...] con 2 o más alas")
    preparadas = []
    for z in zonas:
        z = z or {}
        preparadas.append({"contorno": _contorno(z),
                           "rol": str(z.get("rol") or "")})
    prog = _programa_de(params)
    comp = dd.ajustar_zonas(prog, preparadas,
                            encaje_estricto=True,
                            ajuste="estricto" if params.get("ajuste")
                            == "estricto" else "ideal",
                            chaflanes=bool(params.get("chaflanes", True)))
    return _compuesto_resumido(comp)


def _m_generar_rejilla(params: dict) -> dict:
    prog = _programa_de(params)
    cont = _contorno(params)
    comp = dd.repartir_rejilla(prog, cont,
                               columnas=int(_num(params, "columnas", 3)),
                               filas=int(_num(params, "filas", 2)),
                               pasillo_m=_num(params, "pasillo_m", 1.6),
                               encaje_estricto=True,
                               ajuste="estricto" if params.get("ajuste")
                               == "estricto" else "ideal",
                               chaflanes=bool(params.get("chaflanes", True)))
    return _compuesto_resumido(comp)


def _m_aplicar_exportar(params: dict) -> dict:
    """FASE C: del análisis de la sesión a ARCHIVOS REALES en disco.

    Con ediciones 3D reutiliza el proyecto de sesión; sin ediciones crea
    uno temporal y aplica el análisis con las opciones de la UI. Exporta
    los formatos solicitados y, opcionalmente, la instantánea JSON.
    """
    analisis = _analisis_de(params)
    carpeta = str(params.get("carpeta") or "").strip()
    if not carpeta:
        raise ValueError("falta la carpeta de destino (ruta absoluta)")
    carpeta = os.path.abspath(carpeta)
    if os.path.exists(carpeta) and not os.path.isdir(carpeta):
        raise ValueError("la carpeta de destino no es un directorio: "
                         + carpeta)
    os.makedirs(carpeta, exist_ok=True)
    base = str(params.get("nombre_base") or "proyecto_arqgen").strip() \
        or "proyecto_arqgen"

    formatos = params.get("formatos")
    if formatos is not None:
        if not isinstance(formatos, list) or not formatos:
            raise ValueError("formatos debe ser una lista no vacía "
                             "(IFC, DXF, DXF_R12, JSON, CSV, XLSX, SVG)")
        formatos = [str(f) for f in formatos]

    mobiliario = params.get("mobiliario")
    if mobiliario is not None:
        mobiliario = bool(mobiliario)
    opciones = {
        "nombre_edificio": base,
        "trazar_muros": bool(params.get("trazar_muros", True)),
        "mobiliario": mobiliario,
        "modo": "servicio" if params.get("modo") == "servicio"
        else "edificacion",
    }

    from services.export_service import ExportService
    existente = _PROYECTOS.get(str(params.get("id") or ""))
    if existente and existente["editado"]:
        if not opciones["trazar_muros"] or opciones["mobiliario"] is not None or opciones["modo"] != "edificacion":
            raise ValueError("Para exportar el modelo 3D editado o importado, active muros "
                             "y seleccione mobiliario automático; no se regenerará el modelo.")
        proyecto = nullcontext((existente["ctx"], existente["aplicacion"]))
    else:
        proyecto = _proyecto_temporal(analisis, opciones)
    with proyecto as (ctx, _aplicacion):
        exportador = ExportService()
        res = exportador.exportar_todo(ctx, carpeta, base, formatos)
        archivos = {}
        for fmt, ruta in (res.get("archivos") or {}).items():
            archivos[fmt] = {"ruta": ruta, "bytes": os.path.getsize(ruta)}
        # Usar el mismo nombre saneado que el resto de exportaciones. El
        # texto introducido por el usuario nunca debe escapar de la carpeta.
        base_segura = res["base"]
        resultado = {"carpeta": carpeta, "base": base_segura,
                     "archivos": archivos,
                     "errores": dict(res.get("errores") or {})}
        if bool(params.get("con_proyecto", True)):
            from exporters.json_io import JSONExporter
            ruta_proy = os.path.join(carpeta, base_segura + "_proyecto.json")
            JSONExporter().export(ctx, ruta_proy)
            resultado["proyecto"] = {
                "ruta": ruta_proy, "bytes": os.path.getsize(ruta_proy)}
        return resultado


@contextmanager
def _proyecto_temporal(analisis: dict, opciones: dict):
    """Materializa el análisis para exportación o visualización sin guardarlo."""
    with tempfile.TemporaryDirectory(prefix="arqgen_rpc_") as tmp_db:
        from services.context import ApplicationContext
        app = ApplicationContext()
        nombre = str(opciones.get("nombre_edificio") or "Vista previa")
        ctx = app.create_project(os.path.join(tmp_db, "proyecto.arqgen"), nombre)
        try:
            if str(analisis.get("tipo") or "") in ("zonas", "rejilla"):
                aplicacion = dd.aplicar_zonas(ctx, analisis, opciones)
            else:
                aplicacion = dd.aplicar_plan(ctx, analisis, opciones)
            ctx.session.commit()
            yield ctx, aplicacion
        finally:
            ctx.close()


def _proyecto_sesion(params: dict):
    """Materializa una sola vez el proyecto de la sesión para editarlo."""
    analisis = _analisis_de(params)
    sid = str(params["id"])
    if sid in _PROYECTOS:
        return _PROYECTOS[sid]
    from services.context import ApplicationContext
    temporal = tempfile.TemporaryDirectory(prefix="arqgen_modelo_")
    ctx = None
    try:
        ctx = ApplicationContext().create_project(
            os.path.join(temporal.name, "proyecto.arqgen"), "Vista previa")
        opciones = {"nombre_edificio": "Vista previa", "trazar_muros": True,
                    "mobiliario": None, "modo": "edificacion"}
        if str(analisis.get("tipo") or "") in ("zonas", "rejilla"):
            aplicacion = dd.aplicar_zonas(ctx, analisis, opciones)
        else:
            aplicacion = dd.aplicar_plan(ctx, analisis, opciones)
        ctx.commit()
        entrada = {"temporal": temporal, "ctx": ctx,
                   "aplicacion": aplicacion, "editado": False}
        _PROYECTOS[sid] = entrada
        return entrada
    except Exception:
        if ctx is not None:
            ctx.close()
        temporal.cleanup()
        raise


def _m_vista_3d(params: dict) -> dict:
    """Proyecta el modelo real aplicado, con el motor 3D de la GUI clásica.

    El proyecto editable temporal conserva IDs y cambios durante la sesión.
    El filtro de nivel usa un índice estable, no IDs del cliente.
    """
    _analisis_de(params)
    azimut = _num(params, "azimut", 30.0)
    elevacion = _num(params, "elevacion", 35.0)
    explosion = _num(params, "explosion_m", 0.0)
    if not all(math.isfinite(v) for v in (azimut, elevacion, explosion)):
        raise ValueError("la cámara y la explosión deben ser números finitos")
    if not 8.0 <= elevacion <= 80.0:
        raise ValueError("elevacion debe estar entre 8 y 80 grados")
    if not 0.0 <= explosion <= 10.0:
        raise ValueError("explosion_m debe estar entre 0 y 10 metros")
    perspectiva = params.get("perspectiva", False)
    if not isinstance(perspectiva, bool):
        raise ValueError("perspectiva debe ser verdadera o falsa")
    nivel = params.get("nivel")
    if nivel is not None and (isinstance(nivel, bool) or not isinstance(nivel, int) or nivel < 0):
        raise ValueError("nivel debe ser un índice entero no negativo o null")

    from ui import view3d as v3
    entrada = _proyecto_sesion(params)
    ctx, aplicacion = entrada["ctx"], entrada["aplicacion"]
    modelo, avisos = v3.modelo3d_desde_proyecto(ctx)
    niveles = [{"nombre": n.name, "cota_m": n.base_z} for n in modelo.niveles]
    if nivel is not None and nivel >= len(modelo.niveles):
        raise ValueError("nivel fuera de rango")
    nivel_id = modelo.niveles[nivel].level_id if nivel is not None else ""
    camara = v3.Camara3D(azimuth_deg=azimut % 360.0,
                         elevacion_deg=elevacion, perspectiva=perspectiva)
    caras = v3.construir_caras(modelo, camara, explotar_m=explosion,
                               nivel_id=nivel_id)
    # encuadre prepara el centro y distancia antes de proyectar perspectiva.
    minx, miny, maxx, maxy = v3.encuadre(caras, camara)
    poligonos = []
    for cara in caras:
        puntos = []
        for punto in cara.puntos:
            x, y = v3.proyecta(punto, camara)
            puntos.append([round(x, 5), round(-y, 5)])
        centro_cara = [sum(p[i] for p in cara.puntos) / len(cara.puntos) for i in range(3)]
        poligonos.append({"puntos": puntos, "color": cara.color,
                          "tipo": cara.kind, "entidad_id": cara.entidad_id,
                          "entidad_tipo": cara.entidad_tipo,
                          "centro_mundo": centro_cara})
    return {"caras": poligonos,
            "encuadre": [minx, -maxy, maxx - minx, maxy - miny],
            "niveles": niveles,
            "camara": {"perspectiva": perspectiva, "azimut": camara.azimuth_deg,
                       "elevacion": camara.elevacion_deg,
                       "centro": list(camara.centro or (0.0, 0.0, 0.0)),
                       "distancia": camara.distancia_m,
                       "cerca_fraccion": camara.PERSP_CERCA_FRACC},
            "avisos": list(dict.fromkeys(avisos + list(aplicacion.get("avisos") or [])))}


def _m_elemento_3d(params: dict) -> dict:
    from services.edicion_3d import describir
    entrada = _proyecto_sesion(params)
    return describir(entrada["ctx"], params.get("tipo"), params.get("elemento_id"))


def _m_editar_3d(params: dict) -> dict:
    from services.edicion_3d import editar, entidad
    from services.commands_impl import entity_snapshot
    from services.historial_3d import registrar
    entrada = _proyecto_sesion(params)
    ctx = entrada["ctx"]
    antes = entity_snapshot(entidad(ctx, params.get("tipo"), params.get("elemento_id")))
    resultado = editar(ctx, params.get("tipo"), params.get("elemento_id"),
                       params.get("valores"), params.get("revision"))
    despues = entity_snapshot(entidad(ctx, resultado["tipo"], resultado["id"]))
    registrar(entrada, antes, despues)
    entrada["editado"] = True
    return resultado


def _m_crear_escalera_3d(params: dict) -> dict:
    from services.edicion_3d import crear_escalera, entidad
    from services.commands_impl import entity_snapshot
    from services.historial_3d import registrar
    entrada = _proyecto_sesion(params)
    resultado = crear_escalera(entrada["ctx"], params.get("tipo"), params.get("nivel"))
    registrar(entrada, None, entity_snapshot(entidad(entrada["ctx"], "STAIR", resultado["id"])))
    entrada["editado"] = True
    return resultado


def _m_borrar_escalera_3d(params: dict) -> dict:
    from services.edicion_3d import borrar_escalera, entidad
    from services.commands_impl import entity_snapshot
    from services.historial_3d import registrar
    entrada = _proyecto_sesion(params)
    ctx = entrada["ctx"]
    uid = params.get("elemento_id")
    antes = entity_snapshot(entidad(ctx, "STAIR", uid))
    borrar_escalera(ctx, uid, params.get("revision"))
    registrar(entrada, antes, None)
    entrada["editado"] = True
    return {"elemento_id": uid, "borrado": True}


def _m_deshacer_3d(params: dict) -> dict:
    from services.historial_3d import cambiar
    return cambiar(_proyecto_sesion(params))


def _m_rehacer_3d(params: dict) -> dict:
    from services.historial_3d import cambiar
    return cambiar(_proyecto_sesion(params), rehacer=True)


def _m_proyecto_editar_3d(params: dict) -> dict:
    """Importa una instantánea a un modelo de sesión aislado y editable."""
    from exporters.json_io import ENTITY_ORDER
    from services.context import ApplicationContext
    from services.import_service import ImportService

    texto = params.get("contenido")
    if not isinstance(texto, str):
        raise ValueError("La instantánea debe ser texto JSON de hasta 16 MiB")
    try:
        tamano = len(texto.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("La instantánea no contiene texto UTF-8 válido") from None
    if tamano > 16 * 1024 * 1024:
        raise ValueError("La instantánea debe ser texto JSON de hasta 16 MiB")
    try:
        def constante_invalida(_):
            raise ValueError("La instantánea no admite números no finitos")
        data = json.loads(texto, parse_constant=constante_invalida)
    except (ValueError, RecursionError) as exc:
        raise ValueError("Instantánea JSON inválida: " + str(exc)) from exc
    if not isinstance(data, dict) or data.get("format") != "ARQ_GEN_SNAPSHOT":
        raise ValueError("No es una instantánea ARQ_GEN_SNAPSHOT")
    pendientes = [data]
    while pendientes:
        valor = pendientes.pop()
        if isinstance(valor, float) and not math.isfinite(valor):
            raise ValueError("La instantánea no admite números no finitos")
        if isinstance(valor, dict):
            pendientes.extend(valor.values())
        elif isinstance(valor, list):
            pendientes.extend(valor)
    proyecto, entidades = data.get("project"), data.get("entities")
    if not isinstance(proyecto, dict) or not isinstance(proyecto.get("id"), str) or not proyecto["id"]:
        raise ValueError("La instantánea no tiene identificador de proyecto válido")
    if not isinstance(entidades, dict) or set(entidades) - set(ENTITY_ORDER):
        raise ValueError("La instantánea contiene tipos de entidad no admitidos")
    total = 0
    identidades = {}
    for tipo, filas in entidades.items():
        if not isinstance(filas, list):
            raise ValueError("Lista de entidades inválida: " + tipo)
        total += len(filas)
        if total > 20000:
            raise ValueError("La instantánea supera 20 000 registros de entidades")
        vistos = set()
        for fila in filas:
            if not isinstance(fila, dict) or not isinstance(fila.get("id"), str) or not fila["id"]:
                raise ValueError("Entidad sin identificador en " + tipo)
            if fila["id"] in vistos:
                raise ValueError("Identificador repetido en " + tipo)
            vistos.add(fila["id"])
            if fila.get("project_id") != proyecto["id"]:
                raise ValueError("Entidad de otro proyecto en " + tipo)
            if fila.get("ENTITY_TYPE") not in (("OPENING", "DOOR", "WINDOW") if tipo == "OPENING" else (tipo,)):
                raise ValueError("Tipo de entidad incompatible en " + tipo)
            anterior = identidades.get(fila["id"])
            if anterior:
                grupo, copia = anterior
                espejo_vano = (fila.get("ENTITY_TYPE") in ("DOOR", "WINDOW") and
                               {grupo, tipo} == {"OPENING", fila["ENTITY_TYPE"]} and copia == fila)
                if not espejo_vano:
                    raise ValueError("Identificador repetido entre entidades incompatibles")
            else:
                identidades[fila["id"]] = (tipo, fila)
    temporal = tempfile.TemporaryDirectory(prefix="arqgen_modelo_")
    ctx = None
    try:
        ruta_json = os.path.join(temporal.name, "instantanea.json")
        with open(ruta_json, "w", encoding="utf-8") as fh:
            fh.write(texto)
        ruta_db = os.path.join(temporal.name, "proyecto.arqgen")
        app = ApplicationContext()
        ImportService(app).import_snapshot(ruta_json, ruta_db, approve=True)
        ctx = app.open_project(ruta_db)
        niveles = ctx.architecture.count("LEVEL", ctx.project.id)
        sid = _guardar_sesion({"tipo": "proyecto_importado"})
        _PROYECTOS[sid] = {"temporal": temporal, "ctx": ctx,
                           "aplicacion": {"avisos": []}, "editado": True}
        return {"id": sid, "tipo": "proyecto_importado", "nombre": ctx.project.name,
                "niveles": niveles,
                "avisos": ["Se importaron las entidades arquitectónicas; las cantidades y cálculos no se restauran automáticamente."]}
    except Exception:
        if ctx is not None:
            ctx.close()
        temporal.cleanup()
        raise


def _m_proyecto_abrir(params: dict) -> dict:
    """Vista previa de una instantánea ARQ_GEN_SNAPSHOT (sin cambios)."""
    ruta = str(params.get("ruta") or "").strip()
    if not ruta:
        raise ValueError("falta la ruta del proyecto .json")
    from exporters.json_io import JSONImporter
    prev = JSONImporter().preview(ruta)
    return {"ruta": ruta,
            "nombre": str(prev.get("project") or ""),
            "recuentos": {str(k): int(v)
                          for k, v in (prev.get("counts") or {}).items()},
            "cantidades": int(prev.get("quantities") or 0),
            "errores": list(prev.get("errors") or [])}


_DISPATCH = {
    "ping": _m_ping,
    "version": _m_version,
    "selftest": _m_selftest,
    "generar_quick": _m_generar_quick,
    "generar_edificacion": _m_generar_edificacion,
    "catalogo": _m_catalogo,
    "generar_radial": _m_generar_radial,
    "generar_y": _m_generar_y,
    "generar_x": _m_generar_x,
    "generar_zonas": _m_generar_zonas,
    "generar_rejilla": _m_generar_rejilla,
    "aplicar_exportar": _m_aplicar_exportar,
    "proyecto_abrir": _m_proyecto_abrir,
    "proyecto_editar_3d": _m_proyecto_editar_3d,
    "vista_3d": _m_vista_3d,
    "elemento_3d": _m_elemento_3d,
    "editar_3d": _m_editar_3d,
    "crear_escalera_3d": _m_crear_escalera_3d,
    "borrar_escalera_3d": _m_borrar_escalera_3d,
    "deshacer_3d": _m_deshacer_3d,
    "rehacer_3d": _m_rehacer_3d,
}


# ---------------------------------------------------------------- núcleo ----
def handle_call(mensaje: dict) -> dict:
    """Procesa UN objeto petición JSON-RPC y devuelve el objeto respuesta."""
    rid = mensaje.get("id")
    metodo = mensaje.get("method")
    if not isinstance(metodo, str):
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32600, "message": "petición mal formada"}}
    if metodo not in _DISPATCH:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601,
                          "message": "método desconocido: " + str(metodo)}}
    params = mensaje.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32600,
                          "message": "params debe ser un objeto"}}
    try:
        result = _DISPATCH[metodo](params)
    except ARQGenError as exc:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32602, "message": str(exc.message),
                          "data": {"codigo": str(exc.code or ""),
                                   "accion": str(exc.suggested_action
                                                 or "")}}}
    except ValueError as exc:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32602, "message": str(exc)}}
    except Exception as exc:  # noqa: BLE001 — el protocolo nunca muere
        print("[rpc] error interno en %s: %s" % (metodo, exc),
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> int:
    # El protocolo es siempre UTF-8 aunque la consola de Windows use cp1252.
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — intérpretes sin reconfigure
        pass
    print("[rpc] ARQ GEN sidecar %s listo (FASE C)" % core.APP_VERSION,
          file=sys.stderr, flush=True)
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            mensaje = json.loads(linea)
            if not isinstance(mensaje, dict):
                raise ValueError("la petición no es un objeto")
        except ValueError as exc:
            respuesta = {"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32700,
                                   "message": "JSON inválido: " + str(exc)}}
        else:
            respuesta = handle_call(mensaje)
        sys.stdout.write(json.dumps(respuesta, ensure_ascii=False,
                                    separators=(",", ":")) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
