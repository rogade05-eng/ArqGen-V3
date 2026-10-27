"""Preferencias del usuario de ARQ GEN (mejora UX v3.0.0).

Guarda en JSON las decisiones de presentación para que la app
«recuerde» cómo te gusta trabajar:

- theme:     "dark" | "light"        (modo de la interfaz)
- autosave:  bool (True)             (autoguardado ante cada cambio)
- panels:    {"explorer": bool, "props": bool, "bottom": bool}
             (paneles visibles de la ventana principal)
- geometry:  "1280x800" (tamaño de la ventana al cerrar)
- sashes:    {"paned": [px, px], "outer": [px]}  (posiciones de los
             separadores arrastrables de la ventana principal, v3.7.0)
- dialogs:   {"detalles": "1020x680+40+30", …}   (geometría recordada
             de cada ventana secundaria ajustable, v3.7.0)
- bottom_compact: bool (migración v3.9.1 del panel inferior compacto;
             solo las preferencias escritas por v3.9.1+ pueden traerla)

La ruta por defecto es un archivo por usuario (~/.arqgen/prefs.json),
seguro tanto en desarrollo como dentro del EXE congelado (nunca se
escribe dentro de la carpeta del programa). Toda lectura es tolerante:
un archivo ausente, corrupto o a medias devuelve las preferencias por
defecto sin romper el arranque.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, Optional

PREFS_VERSION = 2

DEFAULTS: Dict[str, Any] = {
    "version": PREFS_VERSION,
    "theme": "dark",
    "autosave": True,
    "panels": {"explorer": True, "props": True, "bottom": True},
    "geometry": "",
    "sashes": {},
    "dialogs": {},
    "bottom_compact": False,
}

_ENV_OVERRIDE = "ARQGEN_PREFS"


def default_prefs_path() -> str:
    """Ruta por usuario: ~/.arqgen/prefs.json (variable de entorno
    ARQGEN_PREFS para pruebas/uso avanzado)."""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".arqgen", "prefs.json")


def _merge_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    # COPIA PROFUNDA: un dict(DEFAULTS) superficial compartiría los
    # diccionarios anidados (panels/sashes/dialogs) entre TODAS las
    # ventanas del proceso — una ventana mutaba los defaults de todas.
    prefs = copy.deepcopy(DEFAULTS)
    for key in ("theme", "autosave", "geometry"):
        if key in data:
            prefs[key] = data[key]
    if isinstance(data.get("panels"), dict):
        panels = dict(DEFAULTS["panels"])
        for key in panels:
            if key in data["panels"]:
                panels[key] = bool(data["panels"][key])
        prefs["panels"] = panels
    for dict_key in ("sashes", "dialogs"):
        value = data.get(dict_key)
        if isinstance(value, dict):
            prefs[dict_key] = {
                str(k): v for k, v in value.items()
                if isinstance(k, str)}
    # Migración del panel inferior compacto (v3.9.1): la marca SOLO es
    # válida si vino de un archivo ya en formato v2 — un prefs.json
    # heredado de versiones anteriores no puede «colarla». Al guardar
    # un dict sin «version» (uso directo de save_prefs) se asume el
    # formato vigente.
    file_version = data.get("version", PREFS_VERSION)
    if not isinstance(file_version, int):
        file_version = 0
    prefs["bottom_compact"] = bool(data.get("bottom_compact")) \
        and file_version >= PREFS_VERSION
    if prefs["theme"] not in ("dark", "light"):
        prefs["theme"] = "dark"
    prefs["autosave"] = bool(prefs["autosave"])
    return prefs


def load_prefs(path: Optional[str] = None) -> Dict[str, Any]:
    """Lee las preferencias; ante cualquier problema devuelve los
    valores por defecto (nunca lanza)."""
    target = path or default_prefs_path()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return copy.deepcopy(DEFAULTS)
        return _merge_defaults(data)
    except Exception:  # noqa: BLE001 - ausente/corrupto: valores por defecto
        return copy.deepcopy(DEFAULTS)


def save_prefs(prefs: Dict[str, Any], path: Optional[str] = None) -> str:
    """Escribe las preferencias de forma atómica (tmp + replace)."""
    target = path or default_prefs_path()
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    data = _merge_defaults(prefs)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, target)
    return target


def update_prefs(**changes: Any) -> Dict[str, Any]:
    """Carga, actualiza las claves dadas y guarda. Devuelve el estado."""
    path = changes.pop("path", None) or default_prefs_path()
    prefs = load_prefs(path)
    panels = changes.pop("panels", None)
    for key, value in changes.items():
        if key in DEFAULTS:
            prefs[key] = value
    if isinstance(panels, dict):
        merged = dict(prefs["panels"])
        for key, value in panels.items():
            if key in merged:
                merged[key] = bool(value)
        prefs["panels"] = merged
    save_prefs(prefs, path)
    return prefs


__all__ = [
    "DEFAULTS", "PREFS_VERSION", "default_prefs_path", "load_prefs",
    "save_prefs", "update_prefs",
]
