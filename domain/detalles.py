"""BIBLIOTECA DE DETALLES CONSTRUCTIVOS por ediciones regionales (v3.5.0).

El plano dice cómo se juntan los muros; el detalle constructivo dice
cómo se construye el muro mismo: capas, espesores, materiales y la
norma que los aconseja. Esta capa de dominio expone una biblioteca
consultable de soluciones constructivas típicas — cimentaciones,
muros, entrepisos, cubiertas, escaleras, humedades, carpintería y
acabados — organizada como un libro de detalles que se publica
adaptado por regiones.

* ``DetallesRegistry`` carga ``resources/knowledge/detalles/base.json``
  (biblioteca universal) y las EDICIONES REGIONALES
  (``resources/knowledge/detalles/<region>.json``). Igual que el libro
  de Neufert, la edición regional toca solo lo suyo:
    - ``overrides.detalles``: detalles que se AÑADEN o REEMPLAZAN por
      id (la edición aporta sus soluciones propias, p. ej. el muro
      confinado de block de México);
    - ``retirar``: ids que la edición RETIRA de la base (p. ej. Cuba
      retira el hormigón celular autoclavado, no corriente en el
      mercado nacional).
  Lo no tocado sigue siendo la biblioteca universal.
* ``set_region()`` / ``reset_region()`` cambian la edición activa sin
  corromper jamás la base (deepcopy); ``available_regions()`` lista las
  ediciones instaladas. Un fichero roto se salta y deja nota: la
  biblioteca aconseja, nunca bloquea.
* Búsqueda tolerante: ``list_details(categoria=…, texto=…)`` compara
  SIN acentos sobre id, nombre, resumen, norma, materiales y etiquetas.
* ``DetalleConstructivo`` es una ficha inmutable con su corte por
  ``capas`` (``CapaDetalle``), espesor total, usos, norma y notas;
  ``ficha()`` la imprime lista para CLI o GUI.
* ``get_registry()`` devuelve un registro único cargado de los
  recursos (silencioso si no hay ficheros).
* Vínculo con el asistente (v3.6.0): ``TIPOLOGIA_DETALLES`` mapea cada
  tipología constructiva de ``ui.building_wizard`` con sus detalles
  recomendados; ``detalles_para_tipologia()`` los devuelve ADAPTADOS
  a la edición activa y ``buscar_tipologia()`` resuelve el texto del
  usuario (sin acentos, exacta → única substring).

Todo son VALORES DE REFERENCIA: el proyectista decide y verifica la
norma local vigente.
"""

from __future__ import annotations

import copy
import json
import os
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Fichero de la biblioteca base (universal).
BASE_RESOURCE = ("knowledge", "detalles", "base.json")

#: Directorio de las ediciones regionales.
REGIONS_RESOURCE_DIR = ("knowledge", "detalles")

#: Código de la edición base (biblioteca universal, sin overrides).
REGION_BASE = "base"

#: Orden canónico de categorías (la tabla de contenidos del libro).
CATEGORIAS: Tuple[str, ...] = (
    "cimentaciones", "muros", "entrepisos", "cubiertas",
    "escaleras", "humedades", "carpinteria", "acabados",
)

#: Nombres legibles de las categorías para CLI/GUI.
CATEGORIA_NOMBRE: Dict[str, str] = {
    "cimentaciones": "Cimentaciones",
    "muros": "Muros",
    "entrepisos": "Entrepisos",
    "cubiertas": "Cubiertas",
    "escaleras": "Escaleras",
    "humedades": "Humedades",
    "carpinteria": "Carpintería (vanos)",
    "acabados": "Acabados",
}


def sin_acentos(texto: str) -> str:
    """Minúsculas sin acentos ni diéresis («cimentación» → «cimentacion»).

    La búsqueda de la biblioteca compara siempre sobre esta forma para
    que buscar «ventana», «ventana…» o «MOSAICO» encuentre lo mismo.
    """
    normalized = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).lower().strip()


@dataclass(frozen=True)
class CapaDetalle:
    """Una capa del corte constructivo (nombre, espesor, material)."""

    nombre: str
    espesor_mm: float
    material: str = ""

    def etiqueta(self) -> str:
        """«Enlucido de mortero · 15 mm»."""
        espesor = (f"{self.espesor_mm:g} mm"
                   if float(self.espesor_mm).is_integer()
                   else f"{self.espesor_mm:.1f} mm")
        return f"{self.nombre} · {espesor}"


@dataclass(frozen=True)
class DetalleConstructivo:
    """Ficha de un detalle constructivo: el corte por capas y su norma."""

    id: str
    categoria: str
    nombre: str
    resumen: str = ""
    sentido: str = "de exterior a interior"
    capas: Tuple[CapaDetalle, ...] = ()
    usos: Tuple[str, ...] = ()
    norma: str = ""
    notas: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    regional: bool = False
    fuente: Dict[str, str] = field(default_factory=dict)

    @property
    def espesor_total_mm(self) -> float:
        """Suma de los espesores de las capas (mm)."""
        return round(sum(capa.espesor_mm for capa in self.capas), 1)

    @property
    def espesor_total_m(self) -> float:
        return round(self.espesor_total_mm / 1000.0, 3)

    def etiqueta_corta(self) -> str:
        """«cimentaciones · Zapata corrida de HA»."""
        return f"{self.categoria} · {self.nombre}"

    def ficha(self) -> str:
        """Ficha completa multi-línea (CLI/GUI/selftest)."""
        lineas: List[str] = [self.nombre,
                             f"Categoría: {CATEGORIA_NOMBRE.get(self.categoria, self.categoria)}"]
        if self.resumen:
            lineas.append(self.resumen)
        if self.capas:
            lineas.append(f"Corte ({self.sentido}):")
            for index, capa in enumerate(self.capas, 1):
                material = f" — {capa.material}" if capa.material else ""
                lineas.append(f"  {index}. {capa.etiqueta()}{material}")
            lineas.append(f"Espesor total: {self.espesor_total_mm:g} mm "
                          f"({self.espesor_total_m:.2f} m)")
        if self.usos:
            lineas.append("Usos: " + ", ".join(self.usos))
        if self.norma:
            lineas.append("Norma/referencia: " + self.norma)
        for nota in self.notas:
            lineas.append("· " + nota)
        edicion = ("edición regional" if self.regional
                   else "biblioteca universal")
        if self.fuente.get("titulo"):
            edicion += f" — {self.fuente['titulo']}"
        lineas.append(f"[{edicion}]")
        return "\n".join(lineas)


def _detalle_from_dict(raw: Any) -> DetalleConstructivo:
    """Convierte un dict JSON en ficha; lanza ValueError si es inválido.

    Estricto a propósito: un detalle sin id, categoría o nombre no es
    un detalle, y mejor se salta con nota que publicar una ficha rota.
    """
    if not isinstance(raw, dict):
        raise ValueError("el detalle debe ser un objeto JSON")
    did = str(raw.get("id", "")).strip()
    categoria = str(raw.get("categoria", "")).strip().lower()
    nombre = str(raw.get("nombre", "")).strip()
    if not did or not categoria or not nombre:
        raise ValueError("id, categoria y nombre son obligatorios")
    capas: List[CapaDetalle] = []
    for capa_raw in raw.get("capas", []) or []:
        if not isinstance(capa_raw, dict):
            raise ValueError(f"capa inválida en {did}")
        try:
            espesor = float(capa_raw.get("espesor_mm", 0))
        except (TypeError, ValueError):
            raise ValueError(f"espesor_mm inválido en capa de {did}")
        capas.append(CapaDetalle(
            nombre=str(capa_raw.get("nombre", "Capa")),
            espesor_mm=espesor,
            material=str(capa_raw.get("material", "")),
        ))
    return DetalleConstructivo(
        id=did,
        categoria=categoria,
        nombre=nombre,
        resumen=str(raw.get("resumen", "")),
        sentido=str(raw.get("sentido", "de exterior a interior")),
        capas=tuple(capas),
        usos=tuple(str(u) for u in raw.get("usos", []) or []),
        norma=str(raw.get("norma", "")),
        notas=tuple(str(n) for n in raw.get("notas", []) or []),
        tags=tuple(sin_acentos(t) for t in raw.get("tags", []) or []),
        regional=bool(raw.get("regional", False)),
    )


class DetallesRegistry:
    """Biblioteca de detalles constructivos consultable por el motor,
    el CLI y la GUI, con ediciones regionales sobre una base universal.
    """

    def __init__(self) -> None:
        self._base: Dict[str, DetalleConstructivo] = {}
        self._detalles: Dict[str, DetalleConstructivo] = {}
        self.version: str = ""
        self.fuente: Dict[str, str] = {}
        self.disclaimer: str = ""
        self.criterio: str = ""
        self.region_code: str = REGION_BASE
        self.region_name: str = "Base (biblioteca universal)"
        self.region_edicion: str = ""
        self.region_referencias: str = ""
        self._base_disclaimer: str = ""
        self._base_criterio: str = ""
        self.load_notes: List[str] = []

    # -- carga -------------------------------------------------------------

    def load_file(self, path: str) -> int:
        with open(path, "r", encoding="utf-8") as fh:
            return self.load_dict(json.load(fh))

    def load_dict(self, data: Dict[str, Any]) -> int:
        if not isinstance(data, dict):
            from core.errors import DomainError
            raise DomainError(
                message="La biblioteca de detalles debe ser un objeto JSON",
                code="ARQ-DOM-013",
            )
        base: Dict[str, DetalleConstructivo] = {}
        for raw in data.get("detalles", []) or []:
            try:
                detalle = _detalle_from_dict(raw)
            except ValueError as exc:
                self.load_notes.append(f"detalle inválido: {exc}")
                continue
            base[detalle.id] = detalle
        self._base = base
        self._detalles = dict(base)
        self.version = str(data.get("version", ""))
        fuente = data.get("fuente")
        self.fuente = dict(fuente) if isinstance(fuente, dict) else {}
        self.disclaimer = str(data.get("disclaimer", ""))
        self.criterio = str(data.get("criterio", ""))
        self._base_disclaimer = self.disclaimer
        self._base_criterio = self.criterio
        return len(base)

    def __len__(self) -> int:
        return len(self._detalles)

    # -- ediciones regionales ----------------------------------------------

    def available_regions(self) -> List[Dict[str, Any]]:
        """Ediciones regionales instaladas (sin la base).

        Cada entrada lleva ``codigo``, ``nombre``, ``edicion`` y
        ``archivo``; un fichero roto se salta y deja nota.
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
            if not name.lower().endswith(".json") or name == "base.json":
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
        """Vuelve a la biblioteca universal."""
        self._detalles = dict(self._base)
        self.region_code = REGION_BASE
        self.region_name = "Base (biblioteca universal)"
        self.region_edicion = ""
        self.region_referencias = ""
        self.disclaimer = self._base_disclaimer
        self.criterio = self._base_criterio

    def set_region(self, code: str) -> bool:
        """Activa la edición regional ``code`` (fusión sobre la base).

        La edición AÑADE/REEMPLAZA detalles por id (``overrides``) y
        puede RETIRAR ids (``retirar``); lo no tocado sigue siendo la
        base universal. ``base`` limpia los overrides. Un código sin
        fichero devuelve False y la base queda intacta.
        """
        code = (code or REGION_BASE).strip().lower()
        if code in ("", REGION_BASE):
            self.reset_region()
            return True
        if code == self.region_code and self._detalles:
            return True  # ya activa (el singleton es del proceso)
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
        merged = dict(self._base)
        for rid in info.get("retirar", []) or []:
            merged.pop(str(rid), None)
        overrides = info.get("overrides")
        if isinstance(overrides, dict):
            for raw in overrides.get("detalles", []) or []:
                try:
                    detalle = _detalle_from_dict(raw)
                except ValueError as exc:
                    self.load_notes.append(
                        f"región {code}: detalle inválido: {exc}")
                    continue
                detalle = DetalleConstructivo(
                    id=detalle.id, categoria=detalle.categoria,
                    nombre=detalle.nombre, resumen=detalle.resumen,
                    sentido=detalle.sentido, capas=detalle.capas,
                    usos=detalle.usos, norma=detalle.norma,
                    notas=detalle.notas, tags=detalle.tags,
                    regional=True, fuente={
                        "titulo": (f"{info.get('nombre', code)} — "
                                   f"{info.get('edicion') or 'edición regional'}"),
                    })
                merged[detalle.id] = detalle
        self._detalles = merged
        self.region_code = str(info.get("code", code))
        self.region_name = str(info.get("nombre", code))
        self.region_edicion = str(info.get("edicion", ""))
        self.region_referencias = str(info.get("referencias", ""))
        self.disclaimer = str(info.get("disclaimer", self.disclaimer))
        self.criterio = str(info.get("criterio", self.criterio))
        return True

    def region_is_base(self) -> bool:
        return self.region_code == REGION_BASE

    def region_tag(self) -> str:
        """Etiqueta para avisos (« (edición México)»); vacía en base."""
        if self.region_is_base():
            return ""
        return f" (edición {self.region_name})"

    def region_block(self) -> Dict[str, Any]:
        """Bloque «edicion_regional» para metadata del proyecto."""
        return {
            "codigo": self.region_code,
            "nombre": self.region_name,
            "edicion": self.region_edicion,
            "referencias": self.region_referencias,
        }

    # -- consultas -----------------------------------------------------------

    def categories(self) -> List[str]:
        """Categorías presentes en la edición activa (orden canónico)."""
        presentes = {d.categoria for d in self._detalles.values()}
        return [c for c in CATEGORIAS if c in presentes]

    def get(self, detalle_id: str) -> Optional[DetalleConstructivo]:
        """Ficha por id (None si no existe en la edición activa)."""
        return self._detalles.get(str(detalle_id).strip())

    def list_details(self, categoria: str = "",
                     texto: str = "",
                     ids: Optional["list[str]"] = None
                     ) -> List[DetalleConstructivo]:
        """Detalles de la edición activa, filtrados y ordenados.

        ``categoria`` filtra por categoría exacta; ``texto`` busca sin
        acentos sobre id, nombre, resumen, norma, materiales de las
        capas, usos y etiquetas; ``ids`` (v3.6.0) restringe a esa lista
        blanca — así el filtro de tipología del navegador acota a los
        recomendados sin perder la búsqueda tolerante. Orden:
        categoría canónica, luego id.
        """
        needle = sin_acentos(texto)
        categoria = (categoria or "").strip().lower()
        permitidos = set(ids) if ids is not None else None
        out: List[DetalleConstructivo] = []
        for detalle in self._detalles.values():
            if permitidos is not None and detalle.id not in permitidos:
                continue
            if categoria and detalle.categoria != categoria:
                continue
            if needle and not self._match(detalle, needle):
                continue
            out.append(detalle)
        order = {cat: idx for idx, cat in enumerate(CATEGORIAS)}
        out.sort(key=lambda d: (order.get(d.categoria, 99), d.id))
        return out

    @staticmethod
    def _match(detalle: DetalleConstructivo, needle: str) -> bool:
        haystacks = [detalle.id, detalle.nombre, detalle.resumen,
                     detalle.norma, detalle.categoria,
                     " ".join(detalle.usos), " ".join(detalle.tags)]
        haystacks += [capa.nombre for capa in detalle.capas]
        haystacks += [capa.material for capa in detalle.capas]
        return any(needle in sin_acentos(h) for h in haystacks if h)

    # alias de legibilidad (tests/CLI usan search)
    def search(self, texto: str, categoria: str = ""
               ) -> List["DetalleConstructivo"]:
        return self.list_details(categoria=categoria, texto=texto)


# ==========================================================================
# VÍNCULO CON LA TIPOLOGÍA CONSTRUCTIVA DEL ASISTENTE (v3.6.0)
# ==========================================================================
#
# El asistente de edificación (ui.building_wizard.CONSTRUCTION_TYPES)
# pide «cómo se construyen los cerramientos»; esta tabla responde con
# los detalles de la biblioteca que explican ese sistema, ordenados
# de abajo arriba (cimentación → muro → entrepiso → cubierta → …).
#
# * Las claves son EXACTAMENTE los 10 literales de CONSTRUCTION_TYPES
#   (la suite vigila la paridad, como el spec contra el .bat).
# * Los valores son ids de la BIBLIOTECA UNIVERSAL: la edición
#   regional activa los ADAPTA sola — si la edición reemplaza un id
#   (p. ej. México reemplaza la azotea plana) se recibe la variante
#   regional, y si la edición lo RETIRA (Cuba retira el hormigón
#   celular) el detalle desaparece de la recomendación.
# * Los detalles propios que cada edición AÑADE (con *) siguen a un
#   clic: limpia el filtro de tipología y aparecen en la lista.

TIPOLOGIA_DETALLES: Dict[str, Tuple[str, ...]] = {
    "Mampostería de bloque + losa de vigueta": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_bloque_enlucido",
        "entrepisos/losa_vigueta_bovedilla",
        "cubiertas/cubierta_plana_losa",
        "escaleras/escalera_ha_baldosa",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Hormigón armado (monolítico)": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_bloque_enlucido",
        "entrepisos/losa_maciza_ha",
        "cubiertas/cubierta_plana_losa",
        "escaleras/escalera_ha_baldosa",
        "humedades/drenaje_perimetral",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Vigas y columnas prefabricadas": (
        "cimentaciones/zapata_aislada_pedestal",
        "muros/muro_bloque_enlucido",
        "entrepisos/losa_vigueta_bovedilla",
        "cubiertas/cubierta_chapa_metalica",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Madera ligera": (
        "cimentaciones/zapata_corrida_ha",
        "entrepisos/entrepiso_madera",
        "cubiertas/cubierta_inclinada_teja",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/piso_flotante_laminado",
    ),
    "Panel prefabricado (sandwich)": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_hormigon_celular",
        "entrepisos/losa_vigueta_bovedilla",
        "cubiertas/cubierta_chapa_metalica",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/piso_flotante_laminado",
    ),
    "Losa maciza de hormigón": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_bloque_enlucido",
        "entrepisos/losa_maciza_ha",
        "cubiertas/cubierta_plana_losa",
        "escaleras/escalera_ha_baldosa",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Estructura metálica (acero)": (
        "cimentaciones/zapata_aislada_pedestal",
        "muros/muro_bloque_enlucido",
        "entrepisos/losa_vigueta_bovedilla",
        "cubiertas/cubierta_chapa_metalica",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Muros de piedra": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_piedra_mamposteria",
        "entrepisos/entrepiso_madera",
        "cubiertas/cubierta_inclinada_teja",
        "humedades/drenaje_perimetral",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Tierra (adobe o tapial)": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_adobe_tapial",
        "entrepisos/entrepiso_madera",
        "cubiertas/cubierta_inclinada_teja",
        "humedades/drenaje_perimetral",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/solado_ceramico_mortero",
    ),
    "Estructura ligera de acero galvanizado + panel": (
        "cimentaciones/zapata_corrida_ha",
        "muros/muro_hormigon_celular",
        "entrepisos/entrepiso_madera",
        "cubiertas/cubierta_chapa_metalica",
        "humedades/zocalo_impermeable",
        "carpinteria/ventana_aluminio_alfizar",
        "carpinteria/puerta_interior_premarco",
        "acabados/piso_flotante_laminado",
    ),
}


def tipologias() -> Tuple[str, ...]:
    """Las tipologías con recomendación definida (orden estable)."""
    return tuple(TIPOLOGIA_DETALLES)


def buscar_tipologia(texto: str) -> str:
    """Resuelve una tipología por texto (sin acentos, tolerante).

    Coincidencia EXACTA primero; si no, la única que CONTIENE el
    texto. Devuelve "" si nada coincide y lanza ValueError con los
    candidatos cuando la búsqueda es ambigua («losa» pega con dos).
    """
    needle = sin_acentos(texto)
    if not needle:
        return ""
    for tipo in TIPOLOGIA_DETALLES:
        if sin_acentos(tipo) == needle:
            return tipo
    hits = [t for t in TIPOLOGIA_DETALLES
            if needle in sin_acentos(t)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ValueError(
            f"tipología ambigua «{texto}»: " + " | ".join(hits))
    return ""


def detalles_para_tipologia(registry: "DetallesRegistry",
                            construction_type: str,
                            categoria: str = ""
                            ) -> List["DetalleConstructivo"]:
    """Detalles recomendados para la tipología, ADAPTADOS a la edición.

    Recorre la recomendación de ``TIPOLOGIA_DETALLES`` en su orden
    narrativo (de abajo arriba) y devuelve los que existen en la
    edición activa del registro: si la edición regional reemplazó un
    id llega su variante, y si lo retiró no aparece. ``categoria``
    afina por categoría canónica. Tipología desconocida → lista vacía
    (la biblioteca aconseja, nunca bloquea).
    """
    ids = TIPOLOGIA_DETALLES.get(str(construction_type or "").strip())
    if not ids:
        return []
    out: List[DetalleConstructivo] = []
    categoria = (categoria or "").strip().lower()
    for did in ids:
        detalle = registry.get(did)
        if detalle is None:
            continue
        if categoria and detalle.categoria != categoria:
            continue
        out.append(detalle)
    return out


#: Registro único (singleton perezoso): se carga una vez por proceso.
_REGISTRY: Optional[DetallesRegistry] = None


def get_registry() -> DetallesRegistry:
    """Registro de detalles cargado de los recursos del proyecto."""
    global _REGISTRY
    if _REGISTRY is None:
        registry = DetallesRegistry()
        try:
            from app.paths import resource_path
            registry.load_file(resource_path(*BASE_RESOURCE))
        except Exception:  # noqa: BLE001 — sin biblioteca, sin aviso
            pass
        _REGISTRY = registry
    return _REGISTRY


def reset_registry() -> None:
    """Olvida el singleton (para pruebas y cambio de recursos)."""
    global _REGISTRY
    _REGISTRY = None


__all__ = [
    "BASE_RESOURCE", "REGIONS_RESOURCE_DIR", "REGION_BASE",
    "CATEGORIAS", "CATEGORIA_NOMBRE", "sin_acentos",
    "CapaDetalle", "DetalleConstructivo", "DetallesRegistry",
    "get_registry", "reset_registry",
    "TIPOLOGIA_DETALLES", "tipologias", "buscar_tipologia",
    "detalles_para_tipologia",
]
