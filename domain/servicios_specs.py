"""Catálogo de SERVICIOS completos por temática (v3.33.0; v2.0 en
3.35.0 con los servicios médicos especializados; v3.0 en 3.36.0 con
catálogo UNIVERSAL por sectores).

Carga y valida ``resources/knowledge/servicios_specs.json``: cada
servicio (anatomía patológica, morgue, tomografía, UCI, cuidados
intermedios, urgencias, laboratorio clínico, imagenología,
hemodiálisis, CEyE, farmacia, y desde v3.0 los 23 servicios nuevos
de salud y los 11 de otros sectores) trae sus PARÁMETROS dinámicos,
los LOCALES que lo componen (tipo del DNA, área base, área por
parámetro, mínimos/máximos, flujo, requisitos y adyacencias), sus
FLUJOS y los CHECKS de validación funcional.

v2.0 del catálogo (documento «servicios médicos»): cada local lleva
además GRUPO funcional, CRITICIDAD (niveles 1-3 de la sección 25),
PUERTA_ANCHO y CIRCULACION_MIN del documento, INSTALACIONES (códigos
canon: gases, electricidad, iluminación, HVAC...), ACABADOS
(piso/paredes/techo), EQUIPAMIENTO, RELACIONES (obligatorias,
deseables, prohibidas) y OBSERVACIONES; cada servicio lleva su
MATRIZ_DE_INSTALACIONES (sección 22) y sus RELACIONES_CON_OTROS
SERVICIOS (sección 17); en la raíz viven las 20 REGLAS de generación
automática de plantas (sección 24) y los 4 FLUJOS hospitalarios
canónicos (sección 18).

v3.0 del catálogo (universal): cada servicio lleva su SECTOR
(SALUD, EDUCACION, ADMINISTRACION, COMERCIO, DEPORTIVO, CULTURAL,
RESIDENCIAL, LOGISTICA) y el catálogo crece a 34 servicios y ~400
locales: 23 de salud (consulta externa, bloque quirúrgico,
hospitalización, maternidad, cardiología/hemodinamia, endoscopia,
medicina nuclear, microbiología, banco de sangre, rehabilitación,
salud mental, odontología) y 11 de otros usos (círculo infantil,
primaria, secundaria, oficinas, restaurante, supermercado, hotel,
deportivo, cultural, residencia de adultos, almacén logístico).

Patrón idéntico a hospital_specs/comercial_specs: datos versionados
bajo resources/knowledge, cero hardcode, validador de formato con
error amable y caché por proceso. Solo lectura: nada del catálogo
toca el proyecto.

Uso headless:
    from domain.servicios_specs import cargar_servicios, servicio
    print([s.nombre for s in cargar_servicios()])
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.paths import resource_path
from core.errors import DomainError

_SERVICIOS_CACHE: List["Servicio"] = []
_REGLAS_CACHE: List[str] = []
_FLUJOS_CACHE: List[str] = []
_VERSION_CACHE: str = "1.0"

PARAM_TIPOS = ("int", "bool")

# Vocabulario canon de instalaciones del catálogo v2.0 y su etiqueta
# para la ficha de local (sección 30 del documento médico).
ETIQUETAS_INSTALACIONES = {
    "agua_fria": "Agua fria",
    "agua_caliente": "Agua caliente",
    "drenaje": "Drenaje",
    "drenaje_piso": "Drenaje de piso",
    "lavamanos": "Lavamanos",
    "lavadero": "Lavadero",
    "o2": "Oxigeno",
    "vacio": "Vacio",
    "aire_medicinal": "Aire medicinal",
    "elec_normal": "Electricidad normal",
    "elec_emergencia": "Electricidad de emergencia",
    "ups": "UPS",
    "puesta_tierra": "Puesta a tierra",
    "datos": "Datos",
    "telefonia": "Telefonia",
    "llamada": "Llamada de enfermeria",
    "cctv": "CCTV",
    "control_acceso": "Control de acceso",
    "deteccion_incendio": "Deteccion de incendio",
    "alarma": "Alarma",
    "iluminacion_general": "Iluminacion general",
    "iluminacion_tarea": "Iluminacion de tarea",
    "iluminacion_emergencia": "Iluminacion de emergencia",
    "hvac": "HVAC",
    "extraccion": "Extraccion",
    "presion": "Presion diferencial",
    "ventilacion": "Ventilacion",
    "vapor": "Vapor",
}

NIVELES_CRITICIDAD = {
    1: "critico nivel 1 (soporte vital)",
    2: "critico nivel 2 (asistencial avanzado)",
    3: "critico nivel 3 (diagnostico y apoyo)",
}

# Sectores del catálogo universal v3.0, en el orden de presentación
# del asistente (SALUD primero como legado v2.0).
ETIQUETAS_SECTORES = {
    "SALUD": "Salud",
    "EDUCACION": "Educación",
    "ADMINISTRACION": "Administración",
    "COMERCIO": "Comercio y hostelería",
    "DEPORTIVO": "Deportivo",
    "CULTURAL": "Cultural",
    "RESIDENCIAL": "Residencial asistido",
    "LOGISTICA": "Logística",
}


@dataclass
class ServicioParam:
    """Parámetro dinámico del asistente (spinbox en la GUI)."""

    codigo: str
    nombre: str
    tipo: str = "int"          # int | bool
    minimo: float = 0.0
    maximo: float = 0.0
    defecto: Any = 0
    unidad: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServicioParam":
        return cls(
            codigo=str(data.get("codigo", "")),
            nombre=str(data.get("nombre", "")),
            tipo=str(data.get("tipo", "int")),
            minimo=float(data.get("min", 0) or 0),
            maximo=float(data.get("max", 0) or 0),
            defecto=data.get("defecto", 0),
            unidad=str(data.get("unidad", "")),
        )


@dataclass
class ServicioLocal:
    """Local que compone el servicio, con su regla de área."""

    codigo: str
    nombre: str
    space_type: str = "ROOM"
    area_base: float = 0.0
    area_por: Dict[str, float] = field(default_factory=dict)
    area_min: float = 0.0
    area_max: float = 0.0
    flujo: str = "limpio"
    critico: bool = False
    req: List[str] = field(default_factory=list)
    adjacencias: List[str] = field(default_factory=list)
    descripcion: str = ""
    condicion: str = ""         # parámetro bool que lo excluye si es falso
    repite_por: str = ""        # parámetro int que lo replica N veces
    # -- catálogo v2.0 (documento «servicios médicos») ----------------
    grupo: str = ""             # área funcional del servicio (sección 2-7)
    criticidad: int = 0         # 0 = no crítico; 1..3 = sección 25
    puerta_ancho: float = 0.0   # m, ancho del catálogo (camilla, carro...)
    circulacion_min: float = 0.0  # m, circulación mínima del documento
    instalaciones: List[str] = field(default_factory=list)
    acabados: Dict[str, str] = field(default_factory=dict)
    equipamiento: List[str] = field(default_factory=list)
    relaciones: Dict[str, List[str]] = field(default_factory=dict)
    observaciones: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServicioLocal":
        relaciones = data.get("relaciones") or {}
        return cls(
            codigo=str(data.get("codigo", "")),
            nombre=str(data.get("nombre", "")),
            space_type=str(data.get("space_type", "ROOM")),
            area_base=float(data.get("area_base", 0) or 0),
            area_por={str(k): float(v)
                      for k, v in (data.get("area_por") or {}).items()},
            area_min=float(data.get("area_min", 0) or 0),
            area_max=float(data.get("area_max", 0) or 0),
            flujo=str(data.get("flujo", "limpio")),
            critico=bool(data.get("critico", False)),
            req=[str(r) for r in (data.get("req") or [])],
            adjacencias=[str(a) for a in (data.get("adjacencias") or [])],
            descripcion=str(data.get("descripcion", "")),
            condicion=str(data.get("condicion", "")),
            repite_por=str(data.get("repite_por", "")),
            grupo=str(data.get("grupo", "")),
            criticidad=int(data.get("criticidad", 0) or 0),
            puerta_ancho=float(data.get("puerta_ancho", 0) or 0),
            circulacion_min=float(
                data.get("circulacion_min", 0) or 0),
            instalaciones=[str(i) for i in
                           (data.get("instalaciones") or [])],
            acabados={str(k): str(v) for k, v in
                      (data.get("acabados") or {}).items()},
            equipamiento=[str(e) for e in
                          (data.get("equipamiento") or [])],
            relaciones={str(k): [str(x) for x in (v or [])]
                        for k, v in relaciones.items()},
            observaciones=str(data.get("observaciones", "")),
        )


@dataclass
class Servicio:
    """Servicio completo del catálogo versionado."""

    codigo: str
    nombre: str
    descripcion: str = ""
    parametros: List[ServicioParam] = field(default_factory=list)
    locales: List[ServicioLocal] = field(default_factory=list)
    flujos: List[str] = field(default_factory=list)
    checks: List[Dict[str, str]] = field(default_factory=list)
    notas: List[str] = field(default_factory=list)
    # -- catálogo v2.0 -------------------------------------------------
    matriz_instalaciones: Dict[str, str] = field(default_factory=dict)
    relaciones_servicios: List[Dict[str, str]] = \
        field(default_factory=list)
    # -- catálogo v3.0 (universal) -------------------------------------
    sector: str = "SALUD"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Servicio":
        return cls(
            codigo=str(data.get("codigo", "")),
            nombre=str(data.get("nombre", "")),
            descripcion=str(data.get("descripcion", "")),
            parametros=[ServicioParam.from_dict(p)
                        for p in (data.get("parametros") or [])],
            locales=[ServicioLocal.from_dict(l)
                     for l in (data.get("locales") or [])],
            flujos=[str(f) for f in (data.get("flujos") or [])],
            checks=[{k: str(v) for k, v in c.items()}
                    for c in (data.get("checks") or [])],
            notas=[str(n) for n in (data.get("notas") or [])],
            matriz_instalaciones={
                str(k): str(v) for k, v in
                (data.get("matriz_instalaciones") or {}).items()},
            relaciones_servicios=[
                {"servicio": str(r.get("servicio", "")),
                 "nivel": str(r.get("nivel", ""))}
                for r in (data.get("relaciones_servicios") or [])],
            sector=str(data.get("sector", "SALUD") or "SALUD"),
        )

    def param(self, codigo: str) -> Optional[ServicioParam]:
        return next((p for p in self.parametros if p.codigo == codigo),
                    None)

    def local(self, codigo: str) -> Optional[ServicioLocal]:
        """El local por código, o None si no existe."""
        return next((l for l in self.locales if l.codigo == codigo),
                    None)


def _cargar_archivo() -> List["Servicio"]:
    path = resource_path("knowledge", "servicios_specs.json")
    if not os.path.exists(path):
        raise DomainError(
            message="No se encontró el catálogo de servicios",
            code="ARQ-SRV-001",
            suggested_action="Restaure resources/knowledge/"
                             "servicios_specs.json del paquete.")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("format") != "ARQ_GEN_SERVICIOS":
        raise DomainError(
            message="El catálogo de servicios no tiene el formato "
                    "esperado",
            code="ARQ-SRV-001",
            context={"format": str(data.get("format"))},
            suggested_action="Restaure resources/knowledge/"
                             "servicios_specs.json del paquete.")
    global _REGLAS_CACHE, _FLUJOS_CACHE, _VERSION_CACHE
    _REGLAS_CACHE = [str(r) for r in (data.get("reglas_generacion") or [])]
    _FLUJOS_CACHE = [str(f) for f in
                     (data.get("flujos_hospitalarios") or [])]
    _VERSION_CACHE = str(data.get("version", "1.0"))
    servicios: List["Servicio"] = []
    for entrada in data.get("servicios") or []:
        item = Servicio.from_dict(entrada)
        if not item.codigo or not item.nombre:
            raise DomainError(
                message="Servicio del catálogo sin código o nombre",
                code="ARQ-SRV-001",
                context={"entrada": item.codigo or "?"})
        servicios.append(item)
    if not servicios:
        raise DomainError(
            message="El catálogo de servicios está vacío",
            code="ARQ-SRV-001")
    return servicios


def cargar_servicios() -> List["Servicio"]:
    """Carga (una vez) el catálogo; error amable si falta o está roto."""
    if _SERVICIOS_CACHE:
        return list(_SERVICIOS_CACHE)
    _SERVICIOS_CACHE.extend(_cargar_archivo())
    return list(_SERVICIOS_CACHE)


def servicio(codigo: str) -> "Servicio":
    """El servicio pedido; ARQ-SRV-002 si el código no existe."""
    for item in cargar_servicios():
        if item.codigo == str(codigo or "").strip().upper():
            return item
    raise DomainError(
        message=f"Servicio no encontrado en el catálogo: {codigo}",
        code="ARQ-SRV-002",
        context={"disponibles": [s.codigo for s in cargar_servicios()]},
        suggested_action="Elija uno de los servicios disponibles "
                         "del catálogo.")


def servicios_disponibles() -> List[Tuple[str, str]]:
    """[(codigo, nombre)] para comboboxes y CLI."""
    return [(s.codigo, s.nombre) for s in cargar_servicios()]


def servicios_por_sector() -> List[Tuple[str, List[Tuple[str, str]]]]:
    """[(etiqueta_sector, [(codigo, nombre), ...])] agrupado en el
    orden canon de sectores (SALUD primero); un sector desconocido
    cae al final. Para los filtros del asistente y del explorador del
    flujo «desde dibujo"."""
    grupos: Dict[str, List[Tuple[str, str]]] = {}
    for s in cargar_servicios():
        grupos.setdefault(s.sector, []).append((s.codigo, s.nombre))
    salida: List[Tuple[str, List[Tuple[str, str]]]] = []
    for clave in ETIQUETAS_SECTORES:
        if clave in grupos:
            salida.append((ETIQUETAS_SECTORES[clave],
                           grupos.pop(clave)))
    for clave, items in grupos.items():
        salida.append((ETIQUETAS_SECTORES.get(clave, clave), items))
    return salida


def reglas_generacion() -> List[str]:
    """Las 20 reglas de generación automática de plantas (sección 24)."""
    return list(_REGLAS_CACHE)


def flujos_hospitalarios() -> List[str]:
    """Los 4 flujos hospitalarios canónicos (sección 18)."""
    return list(_FLUJOS_CACHE)


def version_catalogo() -> str:
    """Versión del JSON del catálogo (3.0 desde v3.36.0)."""
    return str(_VERSION_CACHE)


def resumen_catalogo() -> Dict[str, Any]:
    """Cifras del catálogo para diagnósticos y selftest."""
    items = cargar_servicios()
    return {
        "servicios": len(items),
        "locales": sum(len(s.locales) for s in items),
        "parametros": sum(len(s.parametros) for s in items),
        "flujos": sum(len(s.flujos) for s in items),
        "checks": sum(len(s.checks) for s in items),
        "criticos": sum(1 for s in items for l in s.locales
                        if l.critico),
        "grupos": len({l.grupo for s in items for l in s.locales
                       if l.grupo}),
        "sectores": len({s.sector for s in items}),
        "reglas": len(_REGLAS_CACHE),
        "version": _VERSION_CACHE,
    }


__all__ = [
    "Servicio", "ServicioParam", "ServicioLocal", "cargar_servicios",
    "servicio", "servicios_disponibles", "servicios_por_sector",
    "resumen_catalogo", "reglas_generacion", "flujos_hospitalarios",
    "version_catalogo", "ETIQUETAS_INSTALACIONES",
    "NIVELES_CRITICIDAD", "ETIQUETAS_SECTORES",
]
