"""Presets de configuración del asistente de edificación (v3.28.0).

Un PRESET es la fotografía de la CONFIGURACIÓN del asistente (uso,
tipología, tamaño del documento ED, cotas de vanos, instalaciones,
cubierta, mobiliario...) guardada en un JSON aparte para reutilizarla
en otros proyectos: lo que Architechtures cobra en su plan Business
(«presets para cambiar rápidamente los parámetros») aquí es local,
gratuito y auditable.

Reglas de la casa:
- NADA de dependencias nuevas: stdlib ``json`` + ``os``.
- El preset NO guarda el PROGRAMA (niveles, locales, relaciones): ese
  se regenera con «Cargar programa del uso» o al generar la
  edificación, así el preset sigue válido aunque el motor mejore.
- Cada archivo lleva ``formato`` + ``version``; cargar uno de formato
  desconocido da error amable ARQ-PRE-006 en vez de romper la GUI.
- Sólo lectura del proyecto: los presets viven en ``presets/`` junto
  al programa (o donde apunte ``ARQ_GEN_PRESETS``), nunca en la base
  de datos.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import fields
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.errors import DomainError
from ui.building_wizard import (
    ARCHITECTURAL_STYLES, CLIMATE_ZONES, CONSTRUCTION_TYPES,
    CORE_MODES, DISTRIBUCION_CODES, INSTALLATION_MODULES,
    ORIENTATIONS, PLAN_SHAPES, STAIR_MODES, TERRAIN_TYPES, USAGE_TYPES,
    BuildingWizardData, neufert_region_choices, set_neufert_region,
)

FORMATO_PRESET = "ARQ_GEN_PRESET"
VERSION_PRESET = 1
ENV_CARPETA = "ARQ_GEN_PRESETS"

# error codes amables
COD_NOMBRE = "ARQ-PRE-001"     # nombre vacío/ilegal
COD_DATOS = "ARQ-PRE-002"      # datos no es un dict
COD_ESCRITURA = "ARQ-PRE-003"  # OSError al guardar
COD_AUSENTE = "ARQ-PRE-004"    # el preset no existe
COD_JSON = "ARQ-PRE-005"       # JSON corrupto
COD_FORMATO = "ARQ-PRE-006"    # formato/versión desconocidos

# Campos ESCALARES de BuildingWizardData que viajan en el preset
# (nivel/locales/relaciones NO: se regeneran desde el uso).
CAMPOS_PRESET: Tuple[str, ...] = (
    # paso 1
    "name", "usage_type", "lot_width_m", "lot_depth_m",
    "construction_type", "architectural_style", "plan_shape",
    "terrain_type", "stairs_mode", "core_mode", "climate",
    "structural_system", "facade_orientation", "neufert_region",
    "vivienda_tipologia", "vivienda_dormitorios", "vivienda_banos",
    "comercial_tipologia", "educacion_tamano",
    "distribucion", "curvatura_m", "semilla", "notes",
    # paso 4 (vanos y pasillo)
    "corridor_enabled", "corridor_width_m", "wall_thickness_m",
    "door_width_m", "door_height_m", "window_width_m",
    "window_height_m", "window_sill_m", "cross_ventilation",
    # paso 5 (bioclimática e instalaciones)
    "protection_solar", "eaves_m", "installations",
    # concepción de espacios (v3.15.0)
    "mobiliario", "mobiliario_ambito", "mobiliario_densidad",
    "cubierta_tipologia", "cubierta_material", "cubierta_pendiente_pct",
    "cubierta_alero_m", "accesibilidad_auto",
)

# campos booleanos / enteros / flotantes para coaccionar tipos al cargar
_BOOLEANOS = frozenset({
    "corridor_enabled", "cross_ventilation", "protection_solar",
    "mobiliario", "accesibilidad_auto",
})
_ENTEROS = frozenset({"vivienda_dormitorios", "vivienda_banos",
                      "semilla"})
_FLOTANTES = frozenset({
    "lot_width_m", "lot_depth_m", "curvatura_m", "corridor_width_m",
    "wall_thickness_m", "door_width_m", "door_height_m",
    "window_width_m", "window_height_m", "window_sill_m", "eaves_m",
    "cubierta_pendiente_pct", "cubierta_alero_m",
})
# campos con lista de opciones legal (lo que no está en la lista ->
# aviso y se conserva el valor actual de la data)
_LISTAS_LEGALES: Dict[str, Tuple[str, ...]] = {
    "usage_type": USAGE_TYPES,
    "construction_type": CONSTRUCTION_TYPES,
    "architectural_style": ARCHITECTURAL_STYLES,
    "plan_shape": PLAN_SHAPES,
    "terrain_type": TERRAIN_TYPES,
    "stairs_mode": STAIR_MODES,
    "core_mode": CORE_MODES,
    "climate": CLIMATE_ZONES,
    "structural_system": tuple(),  # se valida abajo con opciones reales
    "facade_orientation": ORIENTATIONS,
    "distribucion": DISTRIBUCION_CODES,
    "mobiliario_ambito": ("auto", "domestico", "social", "ambos"),
    "mobiliario_densidad": ("compacto", "estandar", "amplio"),
}


def _opciones_de(campo: str) -> Tuple[str, ...]:
    """Opciones legales del campo (algunas tuplas se calculan tarde)."""
    if campo == "structural_system":
        from ui.building_wizard import STRUCTURAL_SYSTEMS
        return STRUCTURAL_SYSTEMS
    return _LISTAS_LEGALES.get(campo, tuple())


def carpeta_presets(base: Optional[str] = None) -> str:
    """Carpeta de presets: ``ARQ_GEN_PRESETS`` o ``presets/`` del app."""
    elegida = base or os.environ.get(ENV_CARPETA) or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "presets")
    return os.path.abspath(elegida)


def slug(nombre: str) -> str:
    """Nombre de archivo seguro: letras, números, espacio, «-», «_»."""
    limpio = re.sub(r"[^0-9A-Za-zÀ-ÿ _\-]", "_",
                    str(nombre or "").strip())
    limpio = re.sub(r"\s+", " ", limpio).strip(" ._")
    return limpio


def guardar_preset(carpeta: str, nombre: str,
                   datos: Dict[str, Any]) -> str:
    """Escribe ``<slug>.json`` con formato/version y devuelve la ruta.

    Errores: ARQ-PRE-001 nombre ilegal, ARQ-PRE-002 datos no dict,
    ARQ-PRE-003 OSError (carpeta protegida, permisos...).
    """
    limpio = slug(nombre)
    if not limpio:
        raise DomainError(
            message="Necesito un nombre para el preset (por ejemplo, "
                    "«Escuela primaria 240»)",
            code=COD_NOMBRE,
            suggested_action="Escribe un nombre corto y descriptivo.")
    if not isinstance(datos, dict):
        raise DomainError(
            message="El contenido del preset debe ser un diccionario "
                    "de parámetros",
            code=COD_DATOS)
    destino = os.path.join(os.path.abspath(carpeta), limpio + ".json")
    documento = {
        "formato": FORMATO_PRESET,
        "version": VERSION_PRESET,
        "nombre": limpio,
        "creado": datetime.now().isoformat(timespec="seconds"),
        "datos": datos,
    }
    try:
        os.makedirs(carpeta, exist_ok=True)
        with open(destino, "w", encoding="utf-8") as fh:
            json.dump(documento, fh, ensure_ascii=False, indent=1)
    except OSError as exc:
        raise DomainError(
            message=f"No pude escribir el preset: {exc}",
            code=COD_ESCRITURA,
            context={"path": destino}) from exc
    return destino


def listar_presets(carpeta: str) -> List[Dict[str, Any]]:
    """Presets disponibles, alfabéticos; los corruptos se OMITEN (y
    viajan con ``corrupto`` y ``error`` para que la GUI avise)."""
    listado: List[Dict[str, Any]] = []
    if not os.path.isdir(carpeta):
        return listado
    for archivo in sorted(os.listdir(carpeta)):
        if not archivo.lower().endswith(".json"):
            continue
        ruta = os.path.join(carpeta, archivo)
        entrada: Dict[str, Any] = {
            "archivo": archivo, "ruta": ruta,
            "nombre": archivo[:-5], "creado": "", "uso": "",
            "resumen": "", "corrupto": False, "error": "",
        }
        try:
            with open(ruta, "r", encoding="utf-8") as fh:
                documento = json.load(fh)
            if not isinstance(documento, dict) \
                    or documento.get("formato") != FORMATO_PRESET:
                entrada["corrupto"] = True
                entrada["error"] = COD_FORMATO
            else:
                entrada["nombre"] = str(documento.get("nombre")
                                        or entrada["nombre"])
                entrada["creado"] = str(documento.get("creado") or "")
                datos = documento.get("datos") or {}
                entrada["datos"] = datos
                entrada["uso"] = str(datos.get("usage_type") or "")
                entrada["resumen"] = resumen_preset(datos)
        except (OSError, ValueError) as exc:
            entrada["corrupto"] = True
            entrada["error"] = f"{COD_JSON}: {exc}"
        listado.append(entrada)
    listado.sort(key=lambda e: e["nombre"].lower())
    return listado


def cargar_preset(ruta: str) -> Dict[str, Any]:
    """Lee y valida un preset; devuelve el documento completo.

    Errores: ARQ-PRE-004 ausente, ARQ-PRE-005 JSON corrupto,
    ARQ-PRE-006 formato/versión desconocidos.
    """
    if not os.path.isfile(ruta):
        raise DomainError(
            message=f"No encontré el preset: {ruta}",
            code=COD_AUSENTE,
            suggested_action="Comprueba la lista de presets de la "
                             "carpeta «presets».")
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            documento = json.load(fh)
    except (OSError, ValueError) as exc:
        raise DomainError(
            message=f"El preset está corrupto: {exc}",
            code=COD_JSON,
            context={"path": os.path.abspath(ruta)}) from exc
    if not isinstance(documento, dict) \
            or documento.get("formato") != FORMATO_PRESET \
            or not isinstance(documento.get("datos"), dict):
        raise DomainError(
            message="Este archivo no es un preset de ARQ_GEN "
                    f"(formato {FORMATO_PRESET} v{VERSION_PRESET})",
            code=COD_FORMATO,
            context={"path": os.path.abspath(ruta)})
    version = documento.get("version")
    if not isinstance(version, int) or version > VERSION_PRESET:
        raise DomainError(
            message=f"El preset pide versión {version} y este ARQ_GEN "
                    f"entiende hasta {VERSION_PRESET}",
            code=COD_FORMATO)
    return documento


def eliminar_preset(ruta: str) -> bool:
    """Borra el .json del preset; False si ya no existía."""
    try:
        os.remove(ruta)
        return True
    except FileNotFoundError:
        return False


def preset_de_data(data: BuildingWizardData) -> Dict[str, Any]:
    """Fotografía de la configuración escalar de la data del wizard."""
    snapshot: Dict[str, Any] = {}
    for campo in CAMPOS_PRESET:
        valor = getattr(data, campo)
        if isinstance(valor, list):
            valor = list(valor)
        snapshot[campo] = valor
    return snapshot


def aplicar_preset_a_data(datos: Dict[str, Any],
                          data: BuildingWizardData) -> List[str]:
    """Restaura el preset sobre ``data``; devuelve AVISOS (cp1252).

    Los valores ilegales (uso inexistente, texto donde va número, etc.)
    NO abortan: se ignoran y avisan, porque un preset de otra versión
    nunca debe dejar el asistente inservible.
    """
    avisos: List[str] = []
    if not isinstance(datos, dict):
        return ["El preset no trae parámetros legibles; no he "
                "cambiado nada."]
    legales = {f.name for f in fields(BuildingWizardData)}
    for campo in CAMPOS_PRESET:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo in _BOOLEANOS:
            setattr(data, campo, bool(valor))
            continue
        if campo in _ENTEROS:
            try:
                setattr(data, campo, int(float(
                    str(valor).replace(",", "."))))
            except (TypeError, ValueError):
                avisos.append(f"{campo}: «{valor}» no es un entero; "
                              "lo dejo como estaba")
            continue
        if campo in _FLOTANTES:
            try:
                setattr(data, campo,
                        float(str(valor).replace(",", ".")))
            except (TypeError, ValueError):
                avisos.append(f"{campo}: «{valor}» no es un número; "
                              "lo dejo como estaba")
            continue
        if campo == "installations":
            if isinstance(valor, list):
                validos = [str(nombre) for nombre in valor
                           if nombre in INSTALLATION_MODULES]
                descartados = [str(nombre) for nombre in valor
                               if nombre not in INSTALLATION_MODULES]
                data.installations = validos
                if descartados:
                    avisos.append("instalaciones desconocidas "
                                  "descartadas: "
                                  + ", ".join(descartados))
            else:
                avisos.append("installations: se esperaba una lista")
            continue
        if campo == "neufert_region":
            codigo = str(valor or "")
            if any(codigo == c for c, _l in neufert_region_choices()):
                data.neufert_region = codigo
                set_neufert_region(codigo)
            else:
                avisos.append(f"edición Neufert «{codigo}» "
                              "desconocida; conservo la actual")
            continue
        opciones = _opciones_de(campo)
        texto = str(valor or "")
        if opciones and texto not in opciones:
            avisos.append(f"{campo}: «{texto}» no está en la lista de "
                          "opciones de esta versión; conservo el "
                          "valor actual")
            continue
        if campo not in legales:
            continue
        setattr(data, campo, texto if opciones else valor)
    return avisos


def resumen_preset(datos: Dict[str, Any]) -> str:
    """Una línea cp1252 para la lista de la GUI y los tests."""
    if not isinstance(datos, dict):
        return ""
    uso = str(datos.get("usage_type") or "")
    partes = [uso] if uso else []
    if uso == "Vivienda":
        tipologia = str(datos.get("vivienda_tipologia") or "")
        if tipologia:
            partes.append(tipologia)
        partes.append(f"{datos.get('vivienda_dormitorios', '?')} "
                      "dorm / "
                      f"{datos.get('vivienda_banos', '?')} baños")
    elif str(datos.get("comercial_tipologia") or "") not in (
            "", "(sin tipología concreta)"):
        partes.append(str(datos.get("comercial_tipologia")))
    elif str(datos.get("educacion_tamano") or "") not in (
            "", "(programa básico)"):
        partes.append(str(datos.get("educacion_tamano")))
    clima = str(datos.get("climate") or "")
    if clima:
        partes.append("clima " + clima)
    return " | ".join(partes)


__all__ = [
    "FORMATO_PRESET", "VERSION_PRESET", "CAMPOS_PRESET", "COD_NOMBRE",
    "COD_DATOS", "COD_ESCRITURA", "COD_AUSENTE", "COD_JSON",
    "COD_FORMATO", "carpeta_presets", "slug", "guardar_preset",
    "listar_presets", "cargar_preset", "eliminar_preset",
    "preset_de_data", "aplicar_preset_a_data", "resumen_preset",
]
