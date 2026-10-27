"""Capa normativa NEUFERT (v2.8.0): reglas y ESPECIFICACIONES REGIONALES.

Perfecciona las reglas del asistente con «El arte de proyectar en
arquitectura» (Ernst Neufert): el libro que mide la arquitectura con el
cuerpo humano — su paso, su alcance, su mobiliario.

* ``NeufertRegistry`` carga ``resources/knowledge/neufert_standards.json``
  y expone consultas tipadas: pasillos y puertas por uso, escalera con
  la fórmula de Blondel, rampas, ventanas (1/8 – 1/6 del suelo),
  alturas libres, espesores de muro por tipología, recuento de aseos,
  estacionamiento…
* EDICIONES REGIONALES (v2.8.0): el libro se publica adaptado por
  regiones — clima, materiales y códigos locales cambian valores
  concretos (techos altos en el trópico, mampostería confinada en
  México, pendientes y rampas por código). ``set_region()`` mezcla el
  fichero de la edición (``neufert_regions/*.json``) SOBRE la base con
  una fusión profunda: lo no tocado sigue siendo Neufert universal.
* ``get_registry()`` devuelve un registro único cargado de los recursos
  (silencioso si no hay fichero: la norma aconseja, nunca bloquea).

Todo son VALORES DE REFERENCIA legibles: el motor los usa para sugerir
y avisar, y el proyectista decide (y verifica la norma local vigente).
"""

from __future__ import annotations

import copy
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: Texto de citación que llevan los avisos y los resúmenes.
FUENTE_TEXTO = ("Neufert — «El arte de proyectar en arquitectura» "
                "(Ernst Neufert)")

#: Fichero de recursos del catálogo normativo (base, 5.ª ed. en español).
STANDARDS_RESOURCE = ("knowledge", "neufert_standards.json")

#: Directorio de las ediciones regionales del libro (v2.8.0).
REGIONS_RESOURCE_DIR = ("knowledge", "neufert_regions")

#: Código de la edición base (sin overrides).
REGION_BASE = "base"


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Fusión profunda de diccionarios (la región toca solo lo suyo).

    Los dict se mezclan recursivamente; cualquier otro valor de ``src``
    reemplaza al de ``dst``. Devuelve ``dst`` por comodidad.
    """
    for key, value in src.items():
        if (key in dst and isinstance(dst[key], dict)
                and isinstance(value, dict)):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


@dataclass(frozen=True)
class StairRule:
    """Regla de escalera para un uso social (Neufert)."""

    contrahuella_m: float
    huella_m: float
    ancho_m: float
    usage: str = ""
    pendiente_grados: float = 30.0
    barandilla_m: float = 0.90
    descanso_tras: int = 16
    nota: str = ""

    @property
    def blondel_m(self) -> float:
        """Fórmula de Blondel: 2 × contrahuella + huella."""
        return round(2.0 * self.contrahuella_m + self.huella_m, 3)

    @property
    def blondel_ok(self) -> bool:
        """La fórmula de Blondel queda entre 0,60 y 0,64 m."""
        return 0.60 <= self.blondel_m <= 0.64


class NeufertRegistry:
    """Catálogo normativo Neufert consultable por el motor.

    Con ``set_region()`` la consulta devuelve los valores de la edición
    regional elegida (Cuba, México, Argentina…); lo que la edición no
    toca sigue siendo la base del libro.
    """

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._base: Dict[str, Any] = {}
        self.version: str = ""
        self.source: str = ""
        self.region_code: str = REGION_BASE
        self.region_name: str = "Base (5.ª ed. en español)"
        self.region_edicion: str = ""
        self.region_referencias: str = ""
        self.load_notes: List[str] = []

    # -- carga -----------------------------------------------------------

    def load_file(self, path: str) -> int:
        with open(path, "r", encoding="utf-8") as fh:
            return self.load_dict(json.load(fh))

    def load_dict(self, data: Dict[str, Any]) -> int:
        if not isinstance(data, dict):
            from core.errors import DomainError
            raise DomainError(
                message="El catálogo Neufert debe ser un objeto JSON",
                code="ARQ-DOM-012",
            )
        self._base = data
        self._data = copy.deepcopy(data)
        self.version = str(data.get("version", ""))
        self.source = str((data.get("fuente") or {}).get("titulo", ""))
        return len([k for k in data
                    if k not in ("format", "version", "fuente")])

    def __len__(self) -> int:
        return len([k for k in self._data
                    if k not in ("format", "version", "fuente")])

    # -- acceso genérico --------------------------------------------------

    def section(self, name: str) -> Dict[str, Any]:
        """Sección del catálogo (dict vacío si no existe)."""
        value = self._data.get(name)
        return dict(value) if isinstance(value, dict) else {}

    def has(self, name: str) -> bool:
        return name in self._data

    def fuente(self) -> str:
        fuente = self.section("fuente")
        titulo = fuente.get("titulo", "El arte de proyectar")
        autor = fuente.get("autor", "Ernst Neufert")
        return f"Neufert — «{titulo}» ({autor.split('(')[0].strip()})"

    # -- ediciones regionales (v2.8.0) ------------------------------------

    def available_regions(self) -> List[Dict[str, Any]]:
        """Ediciones regionales instaladas (sin la base).

        Cada entrada lleva ``codigo``, ``nombre`` y ``edicion``. Se
        listan los ficheros JSON del directorio de regiones; un fichero
        roto se salta y deja nota en ``load_notes``.
        """
        found: List[Dict[str, Any]] = []
        try:
            from app.paths import resource_path
            region_dir = resource_path(*REGIONS_RESOURCE_DIR)
            names = sorted(os.listdir(region_dir)) if os.path.isdir(
                region_dir) else []
        except Exception:  # noqa: BLE001 — sin recursos, solo base
            return found
        for name in names:
            if not name.lower().endswith(".json"):
                continue
            path = os.path.join(region_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    info = json.load(fh)
                found.append({
                    "codigo": str(info.get("code")
                                  or name[:-5].lower()),
                    "nombre": str(info.get("nombre", name[:-5])),
                    "edicion": str(info.get("edicion", "")),
                    "archivo": name,
                })
            except Exception as exc:  # noqa: BLE001
                self.load_notes.append(f"región {name}: {exc}")
        return found

    def reset_region(self) -> None:
        """Vuelve a la base del libro (5.ª ed. en español)."""
        self._data = copy.deepcopy(self._base)
        self.region_code = REGION_BASE
        self.region_name = "Base (5.ª ed. en español)"
        self.region_edicion = ""
        self.region_referencias = ""

    def set_region(self, code: str) -> bool:
        """Activa la edición regional ``code`` (fusiona sobre la base).

        ``base`` limpia los overrides. Un código sin fichero devuelve
        False y la base queda intacta (la norma aconseja, no bloquea).
        """
        code = (code or REGION_BASE).strip().lower()
        if code in ("", REGION_BASE):
            self.reset_region()
            return True
        if code == self.region_code and self._data:
            return True  # ya activa: no re-cargar (el singleton es del proceso)
        try:
            from app.paths import resource_path
            path = resource_path(*REGIONS_RESOURCE_DIR, f"{code}.json")
            if not os.path.isfile(path):
                self.reset_region()
                return False
            with open(path, "r", encoding="utf-8") as fh:
                info = json.load(fh)
        except Exception:  # noqa: BLE001 — región rota, queda la base
            self.reset_region()
            return False
        self._data = copy.deepcopy(self._base)
        overrides = info.get("overrides")
        if isinstance(overrides, dict):
            _deep_merge(self._data, overrides)
        self.region_code = str(info.get("code", code))
        self.region_name = str(info.get("nombre", code))
        self.region_edicion = str(info.get("edicion", ""))
        self.region_referencias = str(info.get("referencias", ""))
        return True

    def region_is_base(self) -> bool:
        return self.region_code == REGION_BASE

    def region_tag(self) -> str:
        """Etiqueta para avisos (« (edición Cuba)»); vacía en base."""
        if self.region_is_base():
            return ""
        return f" (edición {self.region_name})"

    def region_block(self) -> Dict[str, Any]:
        """Bloque «edicion_regional» para el metadata del edificio."""
        return {
            "codigo": self.region_code,
            "nombre": self.region_name,
            "edicion": self.region_edicion,
            "referencias": self.region_referencias,
        }

    # -- consultas tipadas -------------------------------------------------

    def corridor_for(self, usage: str) -> Optional[float]:
        """Ancho de pasillo recomendado para el uso (m)."""
        por_uso = self.section("pasillos").get("por_uso", {})
        value = por_uso.get(usage)
        if value is None:
            value = self.section("pasillos").get("dos_personas_m", 1.2)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def door_for(self, usage: str) -> Tuple[float, float]:
        """Puerta sugerida (ancho, alto) para el uso (m).

        La salud manda: donde pasa una camilla, 1,20 m (Neufert).
        """
        puertas = self.section("puertas")
        salud = usage in ("Hospital", "Policlínico", "Consultorio médico")
        ancho = (float(puertas.get("camilla_salud_m", 1.2)) if salud
                 else float(puertas.get("interior_comoda_m", 0.9)))
        alto = float(puertas.get("altura_vivienda_m", 2.1))
        if usage in ("Hospital", "Policlínico", "Escuela primaria",
                     "Centro comunitario", "Local comercial",
                     "Comedor social"):
            alto = float(puertas.get("altura_publica_m", 2.4))
        return ancho, alto

    def stair_rule(self, usage: str = "") -> StairRule:
        """Escalera del uso: Blondel (2h + p = 0,60–0,64 m) y ancho.

        La fórmula de Blondel manda; el ancho crece con el carácter
        público del uso (camillas en salud: 1,80 m).
        """
        escaleras = self.section("escaleras")
        por_uso = escaleras.get("ancho_por_uso", {})
        h_min = float(escaleras.get("contrahuella_min_m", 0.14))
        h_max = float(escaleras.get("contrahuella_max_m", 0.18))
        p_min = float(escaleras.get("huella_min_m", 0.26))
        p_max = float(escaleras.get("huella_max_m", 0.32))
        if usage == "Vivienda":
            h, p = 0.175, 0.28            # cómoda doméstica (≈32°)
        elif usage in ("Hospital", "Policlínico", "Consultorio médico"):
            h, p = 0.16, 0.30             # pública con camillas
        elif usage in ("Escuela primaria", "Círculo infantil"):
            h, p = 0.16, 0.30             # pública infantil
        else:
            h, p = 0.17, 0.29             # pública general
        h = min(max(h, h_min), h_max)
        p = min(max(p, p_min), p_max)
        try:
            ancho = float(por_uso.get(usage, 1.2))
        except (TypeError, ValueError):
            ancho = 1.2
        pendiente = math.degrees(math.atan(h / p))
        return StairRule(
            contrahuella_m=h, huella_m=p, ancho_m=ancho, usage=usage,
            pendiente_grados=round(pendiente, 1),
            barandilla_m=float(escaleras.get("barandilla_m", 0.9)),
            descanso_tras=int(escaleras.get("descanso_tras_contrahuellas",
                                            16)),
            nota=str(escaleras.get("nota", "")))

    def ramp_max_percent(self) -> float:
        """Pendiente máxima de rampa (%)."""
        return float(self.section("rampas").get("pendiente_max_porcentaje",
                                                8.0))

    def window_ratio(self) -> Tuple[float, float]:
        """Luz mínima y recomendada como fracción del suelo (1/8, 1/6)."""
        ventanas = self.section("ventanas")
        return (float(ventanas.get("ratio_luz_minimo", 0.125)),
                float(ventanas.get("ratio_luz_recomendado", 0.166)))

    def window_sill(self) -> float:
        return float(self.section("ventanas").get("antepecho_m", 0.9))

    def ceiling_for(self, usage: str) -> Optional[float]:
        """Altura libre recomendada para el uso (m)."""
        por_uso = self.section("alturas_libres").get("por_uso", {})
        value = por_uso.get(usage)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def wall_thickness_for(self, tipologia: str,
                           exterior: bool = True) -> Optional[float]:
        """Espesor de muro por tipología constructiva (m)."""
        por_tip = self.section("muros_espesor").get("por_tipologia", {})
        entry = por_tip.get(tipologia)
        if not isinstance(entry, dict):
            return None
        key = "exterior_m" if exterior else "interior_m"
        try:
            return float(entry.get(key))
        except (TypeError, ValueError):
            return None

    def wc_counts(self, usage: str, persons: int) -> Dict[str, int]:
        """Aseos necesarios según ocupación (tablas de Neufert)."""
        por_uso = self.section("aseo_recuento").get("por_uso", {})
        rule = por_uso.get(usage) or por_uso.get("Oficina") or {}
        out: Dict[str, int] = {}
        for key, target in (("inodoros", "inodoros_por_personas"),
                            ("urinarios", "urinarios_por_personas"),
                            ("lavabos", "lavabos_por_personas")):
            per = rule.get(target)
            if per:
                out[key] = max(1, math.ceil(persons / float(per)))
        return out

    def parking(self) -> Dict[str, Any]:
        return self.section("estacionamiento")

    def furniture(self, item: str) -> Optional[str]:
        """Dimensiones de un mueble de referencia («0.90x2.00»)."""
        value = self.section("mobiliario").get(item)
        return str(value) if value is not None else None

    def note(self, section_name: str) -> str:
        """Nota explicativa de la sección (para avisos amables)."""
        return str(self.section(section_name).get("nota", ""))


#: Registro único (singleton perezoso): se carga una vez por proceso.
_REGISTRY: Optional[NeufertRegistry] = None


def get_registry() -> NeufertRegistry:
    """Registro Neufert cargado de los recursos del proyecto."""
    global _REGISTRY
    if _REGISTRY is None:
        registry = NeufertRegistry()
        try:
            from app.paths import resource_path
            registry.load_file(resource_path(*STANDARDS_RESOURCE))
        except Exception:  # noqa: BLE001 — sin catálogo, valores por defecto
            pass
        _REGISTRY = registry
    return _REGISTRY


def reset_registry() -> None:
    """Olvida el singleton (para pruebas)."""
    global _REGISTRY
    _REGISTRY = None


__all__ = [
    "FUENTE_TEXTO", "STANDARDS_RESOURCE", "REGIONS_RESOURCE_DIR",
    "REGION_BASE", "_deep_merge", "StairRule", "NeufertRegistry",
    "get_registry", "reset_registry",
]
