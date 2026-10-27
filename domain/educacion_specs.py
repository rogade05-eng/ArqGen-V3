"""Escuelas y círculos infantiles (v3.26.0).

Integra el documento «Especificaciones técnicas, funcionales y
dimensionales - Escuelas primarias, secundarias, círculos infantiles
y albergues escolares» (125 secciones) como datos versionados bajo
``resources/knowledge/educacion_specs.json`` — nunca hardcodeados:
4 tipologías ED-01..ED-04 (primaria, secundaria, círculo infantil y
albergue escolar), capacidades paramétricas del §4/§9/§48 con la
fórmula NUM_AULAS = CEIL(alumnos / alumnos_por_aula), 82 cuadros de
cotas MIN/REC con su unidad y nota, relaciones espaciales del §98-101
(escala 0-3) con las prohibiciones de flujo del §102 (alimentos-
residuos, estudiantes-carga, cocina-basura, ropa limpia-sucia),
programas mínimos del §106-109 (20/21/22/23 ítems), reglas de
validación del §111-112, conflictos del §115, climas del §116,
materiales del §92-94, seguridad infantil del §89, punto de reunión
del §104-105 y fuentes OMS/UNICEF del §124.

Tres piezas operativas:

1. CONSULTAS para el asistente de edificación: tipologías con
   etiquetas de GUI, tamaños paramétricos por capacidad, cuadros por
   space_type y programa mínimo por familia.

2. PROGRAMA PARAMÉTRICO: el asistente (``ui.building_wizard``) carga
   los locales del §106-109 por tamaño/capacidad (aulas con
   NUM_AULAS = CEIL, grupos del círculo infantil, dormitorios de
   albergue) con medidas derivadas de los cuadros MIN/REC y las
   relaciones del §98-101.

3. VALIDACIÓN: ``validar_local`` (control dimensional de UN local
   contra su cuadro: superficie, ancho, altura libre, puertas,
   pasillos y profundidad de aula §76) y ``validar_proyecto``
   (programa mínimo, relaciones, flujos del §102, aulas vs
   capacidad §111, dormitorios §49-51, comedor §36/§56, escaleras
   §45, punto de reunión §104-105, alturas libres §2 y seguridad
   infantil §89) con estados HONESTOS medido / pendiente / requiere
   cálculo (§74/§78/§83-85/§87/§90-91: HVAC, incendios, evacuación,
   CCTV, acústica y electricidad-hidráulica quedan marcados, sin
   inventar números). Sólo LEE el proyecto: no crea entidades ni
   necesita commit.

Uso headless:
    from domain.educacion_specs import cargar_specs, validar_proyecto
    informe = validar_proyecto(ctx)
    print(texto_validacion_educacion(informe))
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.paths import resource_path
from core.errors import DomainError

_SPECS_CACHE: List["EducacionSpecs"] = []

# estados de los hallazgos (los mismos del catálogo de viviendas)
MEDIDO = "medido"
PENDIENTE = "pendiente"
REQUIERE_CALCULO = "requiere calculo"

# familias del documento (claves de programa_minimo / relaciones)
FAMILIA_PRI = "ESCUELA_PRIMARIA"
FAMILIA_SEC = "ESCUELA_SECUNDARIA"
FAMILIA_CI = "CIRCULO_INFANTIL"
FAMILIA_ALB = "ALBERGUE_ESCOLAR"
FAMILIAS = (FAMILIA_PRI, FAMILIA_SEC, FAMILIA_CI, FAMILIA_ALB)

# usos de la GUI del asistente (paso 1) y su familia del documento
USO_GUI_PRI = "Escuela primaria"
USO_GUI_SEC = "Escuela secundaria"
USO_GUI_CI = "Círculo infantil"
USO_GUI_ALB = "Albergue"
FAMILIA_DE_USO: Dict[str, str] = {
    USO_GUI_PRI: FAMILIA_PRI, USO_GUI_SEC: FAMILIA_SEC,
    USO_GUI_CI: FAMILIA_CI, USO_GUI_ALB: FAMILIA_ALB,
}
USOS_EDUCATIVOS: Tuple[str, ...] = (
    USO_GUI_PRI, USO_GUI_SEC, USO_GUI_CI, USO_GUI_ALB)
SIN_TAMANO = "(programa básico)"

# cotas generales de referencia (el cuadro del JSON manda si consta)
ALTURA_ESCALERA_MIN_M = 1.20       # ED-ESC-001 (§45, mínimo funcional)
ANCHO_PUERTA_EVAC_M = 0.914        # IBC 2024: <50 ocupantes (§85)
PLAZA_ANCHO_MIN_M = 2.40           # ED-EST3-001 (§70)
PLAZA_ACCESIBLE_ANCHO_M = 3.60     # ED-EST3-001 (§70)
REUNION_M2_MIN = 0.5               # ED-PRE-001 (§104-105)
REUNION_M2_MAX = 1.0
PROF_AULA_ORIENT_M = 10.0          # ED-LUZ-001 (§76: 6-10 m)
PROF_AULA_MAX_M = 12.0             # §76: máxima inicial 10-12 m
ANCHO_PUERTA_GENERAL_M = 0.80      # ED-DOR-002: mínima del dormitorio

# alturas libres mínimas por familia (cuadro ED-GEN-001, §2)
ALTURA_LIBRE_MIN: Dict[str, float] = {
    FAMILIA_PRI: 2.70, FAMILIA_SEC: 2.70, FAMILIA_CI: 2.70,
    FAMILIA_ALB: 2.60,
}

# m2 por usuario según el local (para informar capacidad resultante)
M2_POR_USUARIO: Dict[str, Tuple[float, float]] = {
    "CLASSROOM": (1.8, 2.5),          # §5/§6
    "AULA_INFANTIL": (2.0, 3.0),      # §8
    "SALA_CUNA": (2.5, 4.0),          # §10
    "DORMITORIO_COLETIVO": (4.0, 6.0),  # §11/§51
    "BEDROOM": (4.0, 6.0),            # albergue: colectivo §51
    "SALA_PROFESORES": (1.5, 2.5),    # §21
    "SALA_ESTUDIO": (1.5, 2.5),       # §54
    "SALA_CONVIVENCIA": (1.5, 3.0),   # §55/§63
    "DINING_HALL": (1.20, 1.80),      # §36/§56
    "DRESSING_ROOM": (1.5, 2.5),      # §32
}

# pseudo-códigos de las relaciones del §98-102: «PÚBLICO»,
# «ESTUDIANTES» y «RUIDO» se expanden a space_types reales del DNA
PUBLICO = "__PUBLICO__"
ESTUDIANTES = "__ESTUDIANTES__"
RUIDO = "__RUIDO__"

TIPOS_PUBLICOS: Tuple[str, ...] = (
    "ENTRANCE", "VESTIBULE", "WAITING_ROOM", "PATIO",
    "JUEGO_EXTERIOR", "DINING_HALL", "LIBRARY", "MULTIUSE_HALL",
)
TIPOS_ESTUDIANTES: Tuple[str, ...] = (
    "CLASSROOM", "AULA_INFANTIL", "SALA_CUNA", "PATIO",
    "JUEGO_INTERIOR", "JUEGO_EXTERIOR", "DINING_HALL",
)
TIPOS_RUIDO: Tuple[str, ...] = (
    "TALLER_TECNOLOGICO", "KITCHEN_INSTITUTIONAL", "GYMNASIO",
    "ELECTRICAL_ROOM", "LAUNDRY", "LOADING_DOCK", "SALA_MUSICA",
)


@dataclass
class HallazgoE:
    """Resultado de una comprobación educacional del documento."""

    codigo: str
    severidad: str          # "ok" | "aviso" | "fallo" | "info"
    mensaje: str
    estado: str = MEDIDO    # medido | pendiente | requiere calculo
    fuente: str = "documento educacional"

    def como_dict(self) -> Dict[str, Any]:
        return {"codigo": self.codigo, "severidad": self.severidad,
                "mensaje": self.mensaje, "estado": self.estado,
                "fuente": self.fuente}


@dataclass
class EducacionSpecs:
    """Registro del documento educacional versionado."""

    version: str = ""
    fuente_doc: str = ""
    advertencia: str = ""
    principio: Dict[str, Any] = field(default_factory=dict)
    tipologias: List[Dict[str, Any]] = field(default_factory=list)
    capacidades: Dict[str, Any] = field(default_factory=dict)
    tamanos_parametricos: List[Dict[str, Any]] = \
        field(default_factory=list)
    cuadros: List[Dict[str, Any]] = field(default_factory=list)
    relaciones: List[Dict[str, Any]] = field(default_factory=list)
    escala_relaciones: Dict[str, str] = field(default_factory=dict)
    relacion_a_space: Dict[str, str] = field(default_factory=dict)
    relacion_a_space_familia: Dict[str, Dict[str, str]] = \
        field(default_factory=dict)
    programa_minimo: Dict[str, List[Dict[str, Any]]] = \
        field(default_factory=dict)
    reglas_validacion: List[Dict[str, Any]] = field(default_factory=list)
    conflictos: List[Dict[str, Any]] = field(default_factory=list)
    climas: Dict[str, Any] = field(default_factory=dict)
    materiales: Dict[str, Any] = field(default_factory=dict)
    seguridad_infantil: Dict[str, Any] = field(default_factory=dict)
    prioridades: Dict[str, str] = field(default_factory=dict)
    normativa: List[str] = field(default_factory=list)
    fuentes: List[str] = field(default_factory=list)
    documentacion: List[str] = field(default_factory=list)
    requiere_calculo: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    @staticmethod
    def load_file(path: str) -> "EducacionSpecs":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != "ARQ_GEN_EDUCACION_SPECS":
            raise DomainError(
                message="El archivo de especificaciones educacionales "
                        "no tiene el formato esperado",
                code="ARQ-EDU-001",
                context={"format": data.get("format")},
                suggested_action="Restaure resources/knowledge/"
                                 "educacion_specs.json del paquete.")
        return EducacionSpecs(
            version=str(data.get("version", "")),
            fuente_doc=str(data.get("source", "")),
            advertencia=str(data.get("advertencia", "")),
            principio=dict(data.get("principio", {})),
            tipologias=list(data.get("tipologias", [])),
            capacidades=dict(data.get("capacidades", {})),
            tamanos_parametricos=list(
                data.get("tamanos_parametricos", [])),
            cuadros=list(data.get("cuadros", [])),
            relaciones=list(data.get("relaciones", [])),
            escala_relaciones=dict(data.get("escala_relaciones", {})),
            relacion_a_space=dict(data.get("relacion_a_space", {})),
            relacion_a_space_familia=dict(
                data.get("relacion_a_space_familia", {})),
            programa_minimo=dict(data.get("programa_minimo", {})),
            reglas_validacion=list(data.get("reglas_validacion", [])),
            conflictos=list(data.get("conflictos", [])),
            climas=dict(data.get("climas", {})),
            materiales=dict(data.get("materiales", {})),
            seguridad_infantil=dict(data.get("seguridad_infantil",
                                             {})),
            prioridades=dict(data.get("prioridades", {})),
            normativa=list(data.get("normativa", [])),
            fuentes=list(data.get("fuentes", [])),
            documentacion=list(data.get("documentacion", [])),
            requiere_calculo=list(data.get("requiere_calculo", [])),
        )

    # ------------------------------------------------------------------
    # consultas
    # ------------------------------------------------------------------
    def etiquetas_tipologias(self, familia: str = "") -> List[str]:
        """Etiquetas «ED-01 - Escuela primaria» para la GUI."""
        return [f"{t.get('clave', '')} - {t.get('nombre', '')}"
                for t in self.tipologias
                if not familia or str(t.get("familia", "")) == familia]

    def tipologia_de_etiqueta(self, etiqueta: str) \
            -> Optional[Dict[str, Any]]:
        texto = str(etiqueta or "").strip().lower()
        for t in self.tipologias:
            candidatos = (str(t.get("clave", "")).lower(),
                          str(t.get("nombre", "")).lower(),
                          f"{t.get('clave', '')} - "
                          f"{t.get('nombre', '')}".lower())
            if texto in candidatos:
                return t
        return None

    def programa(self, familia: str) -> List[Dict[str, Any]]:
        """Ítems del programa mínimo del §106-109 para la familia."""
        return list(self.programa_minimo.get(str(familia or ""), []))

    def familias_de_space_type(self, space_type: str) -> List[str]:
        """Familias cuyo programa mínimo usa el space_type dado."""
        texto = str(space_type or "").upper()
        return [familia for familia, items in self.programa_minimo.items()
                if any(str(i.get("space_type", "")).upper() == texto
                       for i in items)]

    def capacidad(self, familia: str) -> Dict[str, Any]:
        return dict(self.capacidades.get(str(familia or ""), {}))

    def tamanos_de(self, familia: str) -> List[Dict[str, Any]]:
        """Tamaños paramétricos (etiqueta, capacidad, por aula/grupo)."""
        return [t for t in self.tamanos_parametricos
                if str(t.get("familia", "")) == str(familia or "")]

    def rango_entrepiso(self, familia: str) \
            -> Optional[Tuple[float, float]]:
        """Rango de altura entre pisos del §2 (cuadro ED-GEN-002)."""
        for c in self.cuadros:
            if str(c.get("id", "")) != "ED-GEN-002":
                continue
            for item in c.get("items", []):
                if str(item.get("parametro", "")) \
                        == familia.upper().replace("ESCUELA_", "") \
                        or str(item.get("parametro", "")) \
                        == familia.upper():
                    r1, r2 = item.get("rec_min"), item.get("rec_max")
                    if r1 is not None and r2 is not None:
                        return float(r1), float(r2)
        return None

    def cuadros_de(self, space_type: str) -> List[Dict[str, Any]]:
        """Cuadros de cotas MIN/REC asociados al space_type."""
        texto = str(space_type or "").strip().upper()
        return [c for c in self.cuadros
                if str(c.get("space_type") or "").upper() == texto]

    def minimos_de(self, space_type: str) -> Dict[str, Optional[float]]:
        """Mínimos (m2, m, m) entre todos los cuadros del space_type."""
        cuadros = self.cuadros_de(space_type)
        areas = [float(c["min_area_m2"]) for c in cuadros
                 if c.get("min_area_m2")]
        anchos = [float(c["min_ancho_m"]) for c in cuadros
                  if c.get("min_ancho_m")]
        alturas = [float(c["min_altura_m"]) for c in cuadros
                   if c.get("min_altura_m")]
        return {
            "area": min(areas) if areas else None,
            "ancho": min(anchos) if anchos else None,
            "altura": min(alturas) if alturas else None,
        }

    def gamas_superficie(self, space_type: str) -> List[str]:
        """Gamas recomendadas «a-b m2» de los ítems SUPERFICIE (m2)."""
        gamas: List[str] = []
        for c in self.cuadros_de(space_type):
            for item in c.get("items", []):
                if str(item.get("parametro", "")).upper() != "SUPERFICIE" \
                        or str(item.get("unidad", "")) != "m2":
                    continue
                rec_min = item.get("rec_min")
                rec_max = item.get("rec_max")
                if rec_min is None or rec_max is None:
                    continue
                texto = f"{float(rec_min):g}-{float(rec_max):g} m2"
                if texto not in gamas:
                    gamas.append(texto)
        return gamas

    def tipo_de_relacion(self, codigo: str, familia: str = "") \
            -> Optional[str]:
        """Space_type del DNA para el código del §98-102 (None si es
        un pseudo-código sin expandir o no consta). El override de la
        familia manda (p. ej. «AULA» es AULA_INFANTIL en el círculo
        infantil)."""
        override = self.relacion_a_space_familia.get(
            str(familia or ""), {})
        tipo = override.get(str(codigo or "")) \
            or self.relacion_a_space.get(str(codigo or ""))
        if tipo in (None, "", PUBLICO, ESTUDIANTES, RUIDO):
            return None
        return str(tipo)

    def tipos_de_relacion(self, codigo: str, familia: str = "") \
            -> Tuple[str, ...]:
        """Space_types que representa un código: un tipo concreto, o el
        conjunto de los pseudo-códigos PÚBLICO/ESTUDIANTES/RUIDO."""
        codigo = str(codigo or "")
        if codigo in (PUBLICO, "PUBLICO"):
            return TIPOS_PUBLICOS
        if codigo in (ESTUDIANTES, "ESTUDIANTES"):
            return TIPOS_ESTUDIANTES
        if codigo in (RUIDO, "RUIDO"):
            return TIPOS_RUIDO
        tipo = self.tipo_de_relacion(codigo, familia)
        return (tipo,) if tipo else ()

    def nivel_de_relacion(self, familia: str, a: str, b: str) \
            -> Optional[str]:
        """Nivel «0»-«3» del §98-102 para el par (en cualquier orden)."""
        for r in self.relaciones:
            if str(r.get("familia", "")) != str(familia or ""):
                continue
            if (r.get("a") == a and r.get("b") == b) or \
                    (r.get("a") == b and r.get("b") == a):
                return str(r.get("nivel", ""))
        return None

    def texto_relacion(self, nivel: str) -> str:
        return self.escala_relaciones.get(str(nivel), "?")

    def resumen(self) -> Dict[str, int]:
        return {
            "tipologias": len(self.tipologias),
            "cuadros": len(self.cuadros),
            "relaciones": len(self.relaciones),
            "programas": len(self.programa_minimo),
            "reglas": len(self.reglas_validacion),
            "conflictos": len(self.conflictos),
            "climas": len(self.climas),
            "prioridades": len(self.prioridades),
            "requiere_calculo": len(self.requiere_calculo),
            "fuentes": len(self.fuentes),
        }


# ----------------------------------------------------------------------
_SPECS_PATH = "educacion_specs.json"


def cargar_specs() -> Optional[EducacionSpecs]:
    """Carga (una vez) el documento educacional; None si falta.

    Sin el recurso el programa sigue funcionando como siempre: las
    especificaciones aconsejan, no bloquean.
    """
    if _SPECS_CACHE:
        return _SPECS_CACHE[0]
    try:
        path = resource_path("knowledge", _SPECS_PATH)
        if not os.path.exists(path):
            return None
        specs = EducacionSpecs.load_file(path)
        _SPECS_CACHE.append(specs)
        return specs
    except Exception:  # noqa: BLE001 — recurso dañado: sin catálogo
        return None


def vaciar_cache() -> None:
    """Suelta la caché (para pruebas con recursos sustituidos)."""
    _SPECS_CACHE.clear()


def familia_de_uso(uso_gui: str) -> Optional[str]:
    """Familia del documento para el uso social de la GUI (o None)."""
    return FAMILIA_DE_USO.get(str(uso_gui or ""))


def etiquetas_tipologias(familia: str = "") -> List[str]:
    """Etiquetas de tipologías para el combo del asistente."""
    specs = cargar_specs()
    if specs is None:
        return []
    return specs.etiquetas_tipologias(familia)


def tamanos_parametricos(uso_gui: str) -> List[str]:
    """Etiquetas del combo de tamaño/capacidad para el uso (o [])."""
    familia = familia_de_uso(uso_gui)
    if not familia:
        return []
    specs = cargar_specs()
    if specs is None:
        return []
    return [str(t.get("etiqueta", ""))
            for t in specs.tamanos_de(familia)]


def tamano_de_etiqueta(uso_gui: str, etiqueta: str) \
        -> Optional[Dict[str, Any]]:
    """Datos del tamaño elegido (capacidad y alumnos por aula/grupo)."""
    familia = familia_de_uso(uso_gui)
    if not familia:
        return None
    specs = cargar_specs()
    if specs is None:
        return None
    for t in specs.tamanos_de(familia):
        if str(t.get("etiqueta", "")) == str(etiqueta or ""):
            return dict(t)
    return None


# ----------------------------------------------------------------------
# VALIDACIÓN DIMENSIONAL DE UN LOCAL (cuadros MIN/REC del documento)
# ----------------------------------------------------------------------

def validar_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Control de validación dimensional de UN local contra su cuadro.

    Comprueba contra los cuadros MIN/REC del space_type y del DNA:
    superficie (E01), ancho (E02), altura libre (E03), puertas (E04),
    pasillos del nivel (E05) y profundidad de aula (E06, §76: 6-10 m
    orientativos, máx inicial 10-12 m). El resto del documento
    (HVAC §78, incendios §83-84, evacuación §85, CCTV §87, acústica
    §90-91, electricidad-hidráulica §74/§79-81) queda «requiere
    cálculo»: es de especialista, no de geometría. Sólo LEE el
    proyecto: no crea entidades ni necesita commit.
    """
    specs = cargar_specs()
    if specs is None:
        raise DomainError(
            message="No se encontró el documento de especificaciones "
                    "educacionales",
            code="ARQ-EDU-002",
            suggested_action="Verifique resources/knowledge/"
                             "educacion_specs.json.")
    from ui.editor_espacios import datos_local, _resolver_local
    datos = datos_local(ctx, ref)
    local = _resolver_local(ctx, ref)
    uso = str(datos.get("uso") or "ROOM")
    hallazgos: List[HallazgoE] = []
    minimos = specs.minimos_de(uso)
    dna = _dna_de(ctx, uso)

    # E01 superficie ------------------------------------------------------
    area = float(datos.get("area_m2") or 0.0)
    sup_min = minimos["area"]
    if sup_min is None and dna is not None:
        try:
            sup_min = float(getattr(dna, "minimum_area", 0.0) or 0.0) \
                or None
        except (TypeError, ValueError):
            sup_min = None
    gamas = specs.gamas_superficie(uso)
    nota_gamas = ("; gamas recomendadas del documento: "
                  + " / ".join(gamas)) if gamas else ""
    rango_usuario = M2_POR_USUARIO.get(uso)
    nota_usuario = ""
    if rango_usuario and area > 0:
        nota_usuario = (f"; admite {math.floor(area / rango_usuario[1])}"
                        f"-{math.floor(area / rango_usuario[0])} "
                        "usuarios (m2 por usuario del documento)")
    if sup_min:
        if area + 1e-9 >= sup_min:
            hallazgos.append(HallazgoE(
                "E01", "ok",
                f"superficie {area:.2f} m2 >= mínima de programación "
                f"{sup_min:.2f} m2{nota_gamas}{nota_usuario}", MEDIDO,
                "cuadros MIN/REC del documento / DNA del uso"))
        else:
            hallazgos.append(HallazgoE(
                "E01", "fallo",
                f"superficie {area:.2f} m2 < mínima de programación "
                f"{sup_min:.2f} m2{nota_gamas}", MEDIDO,
                "cuadros MIN/REC del documento / DNA del uso"))
    else:
        hallazgos.append(HallazgoE(
            "E01", "info",
            f"superficie {area:.2f} m2; el uso se dimensiona por "
            "capacidad o no tiene mínima en los cuadros"
            f"{nota_usuario}", MEDIDO,
            "cuadros MIN/REC del documento / DNA del uso"))

    # E02 ancho -------------------------------------------------------------
    ancho = float(datos.get("ancho_m") or 0.0)
    ancho_min = minimos["ancho"]
    ancho_dna = _ancho_minimo_dna(dna)
    candidatos = [v for v in (ancho_min, ancho_dna) if v]
    if candidatos:
        limite = max(candidatos)
        origen = "cuadros MIN/REC del documento"
        if ancho_dna and (not ancho_min or ancho_dna >= ancho_min):
            origen = "DNA del uso (minimum_width)"
        if ancho + 1e-9 >= limite:
            hallazgos.append(HallazgoE(
                "E02", "ok", f"ancho {ancho:.2f} m >= {limite:.2f} m",
                MEDIDO, origen))
        else:
            hallazgos.append(HallazgoE(
                "E02", "fallo",
                f"ancho {ancho:.2f} m < {limite:.2f} m del uso",
                MEDIDO, origen))

    # E03 altura libre (cota del nivel) ---------------------------------------
    altura_min = minimos["altura"]
    if altura_min is None:
        familias = specs.familias_de_space_type(uso)
        if familias:
            altura_min = min(ALTURA_LIBRE_MIN.get(f, 2.70)
                             for f in familias)
    altura_nivel = _altura_nivel(ctx, local)
    if altura_min and altura_nivel > 0:
        if altura_nivel + 1e-9 >= altura_min:
            hallazgos.append(HallazgoE(
                "E03", "ok",
                f"altura del nivel ({altura_nivel:.2f} m) >= mínima de "
                f"referencia del uso ({altura_min:.2f} m)", MEDIDO,
                "cuadros MIN/REC (§2)"))
        else:
            hallazgos.append(HallazgoE(
                "E03", "fallo",
                f"altura del nivel ({altura_nivel:.2f} m) < mínima de "
                f"referencia del uso ({altura_min:.2f} m); la cota "
                "definitiva la fija la normativa seleccionada (§121)",
                MEDIDO, "cuadros MIN/REC (§2)"))

    # E04 puertas ---------------------------------------------------------------
    puertas = list(datos.get("puertas") or [])
    puerta_min = _puerta_minima_dna(dna)
    limite_puerta = puerta_min or ANCHO_PUERTA_GENERAL_M
    origen_puerta = ("DNA del uso (neufert.puerta_m)"
                     if puerta_min else "cuadros MIN/REC "
                     "(mínima general del documento)")
    if not puertas:
        hallazgos.append(HallazgoE(
            "E04", "aviso", "el local no tiene puertas", MEDIDO,
            origen_puerta))
    else:
        anchos = [w for w in (_ancho_de_vano(ctx, p) for p in puertas)
                  if w is not None]
        estrechas = [f"{p} ({_ancho_de_vano(ctx, p) or 0.0:.2f} m)"
                     for p in puertas
                     if _ancho_de_vano(ctx, p) is not None
                     and _ancho_de_vano(ctx, p) + 1e-9 < limite_puerta]
        if estrechas:
            hallazgos.append(HallazgoE(
                "E04", "fallo",
                "puerta(s) " + ", ".join(estrechas)
                + f" por debajo de {limite_puerta:.2f} m del uso",
                MEDIDO, origen_puerta))
        else:
            mensaje = (f"todas las puertas >= {limite_puerta:.2f} m")
            severidad = "ok"
            if puerta_min is None and anchos and min(anchos) + 1e-9 \
                    < ANCHO_PUERTA_EVAC_M:
                mensaje += ("; la evacuación pide 0.914 m en vías "
                            "comunes (§85): revisa las puertas menores "
                            "si sirven a evacuación")
                severidad = "aviso"
            hallazgos.append(HallazgoE(
                "E04", severidad, mensaje, MEDIDO, origen_puerta))

    # E05 pasillo del nivel --------------------------------------------------------
    pasillo_min = _pasillo_minimo_dna(dna)
    if pasillo_min:
        estrechos = _pasillos_estrechos(ctx, datos, pasillo_min)
        if estrechos is None:
            hallazgos.append(HallazgoE(
                "E05", "info",
                "el nivel no tiene pasillos trazados que comprobar",
                MEDIDO, "DNA del uso (pasillo_m)"))
        elif estrechos:
            hallazgos.append(HallazgoE(
                "E05", "aviso",
                "pasillo(s) " + ", ".join(estrechos)
                + f" por debajo de {pasillo_min:.2f} m del uso",
                MEDIDO, "DNA del uso (pasillo_m)"))
        else:
            hallazgos.append(HallazgoE(
                "E05", "ok",
                f"pasillos del nivel >= {pasillo_min:.2f} m", MEDIDO,
                "DNA del uso (pasillo_m)"))

    # E06 profundidad del aula (§76) ----------------------------------------
    if uso in ("CLASSROOM", "AULA_INFANTIL", "LAB_COMPUTACION"):
        prof = _profundidad_bbox(local)
        if prof > 0:
            if prof + 1e-9 <= PROF_AULA_MAX_M:
                nota = ("dentro de la iluminación lateral"
                        if prof <= PROF_AULA_ORIENT_M
                        else "hasta el máximo inicial 10-12 m (§76)")
                hallazgos.append(HallazgoE(
                    "E06", "ok",
                    f"profundidad {prof:.2f} m {nota}", MEDIDO,
                    "iluminación natural de aulas (§76)"))
            else:
                hallazgos.append(HallazgoE(
                    "E06", "aviso",
                    f"aula profunda: {prof:.2f} m > 10-12 m del §76; "
                    "prevé patios, lucernarios, doble orientación o "
                    "claraboyas", MEDIDO,
                    "iluminación natural de aulas (§76)"))

    return {
        "local": datos.get("codigo"),
        "nombre": datos.get("nombre"),
        "uso": uso,
        "area_m2": area,
        "ancho_m": ancho,
        "hallazgos": [h.como_dict() for h in hallazgos],
        "pendientes_de_calculo": [
            {"tema": r.get("tema", ""), "seccion": r.get("seccion", ""),
             "motivo": r.get("motivo", "")}
            for r in specs.requiere_calculo],
        "advertencia": specs.advertencia,
        "fuentes": specs.fuentes,
        "specs": _resumen_specs(specs),
    }


# ----------------------------------------------------------------------
# VALIDACIÓN DEL PROYECTO (§89-§115, §2, §45, §104-105 + locales)
# ----------------------------------------------------------------------

def validar_proyecto(ctx: Any) -> Dict[str, Any]:
    """Validación educacional del edificio completo (sólo lectura).

    Devuelve ``{edificacion, familias, hallazgos (del edificio),
    locales (informe por local), resumen, prioridades, conflictos,
    reglas, normativa, documentacion, fuentes}``. Las familias se
    toman de la metadata del asistente («educacion.familia») o se
    infieren de los space_types presentes (huellas características).
    """
    specs = cargar_specs()
    if specs is None:
        raise DomainError(
            message="No se encontró el documento de especificaciones "
                    "educacionales",
            code="ARQ-EDU-002",
            suggested_action="Verifique resources/knowledge/"
                             "educacion_specs.json.")
    from ui.building_wizard import _wizard_building
    _edificio, edif = _wizard_building(ctx)
    meta = edif.get("educacion") or {} if isinstance(edif, dict) else {}
    uso_gui = str(edif.get("uso_social", "")) if edif else ""
    tamano = str(meta.get("tamano", "") or "")

    espacios = _lista(ctx, "SPACE")
    niveles = _lista(ctx, "LEVEL")
    escaleras = _lista(ctx, "STAIR")
    relaciones = _lista(ctx, "SPACE_RELATIONSHIP")
    vivos = [s for s in espacios
             if len(getattr(s, "boundary", []) or []) >= 3]
    por_tipo: Dict[str, List[Any]] = {}
    for s in vivos:
        por_tipo.setdefault(str(getattr(s, "space_type", "")) or "ROOM",
                            []).append(s)

    familias = _familias_presentes(specs, meta, por_tipo)
    hallazgos: List[HallazgoE] = []

    # EM01 programa mínimo del §106-109 ---------------------------------------
    if familias:
        for familia in familias:
            faltan, exteriores = [], []
            for item in specs.programa(familia):
                tipo = str(item.get("space_type", ""))
                presente = bool(por_tipo.get(tipo))
                if presente or not item.get("es_local", True):
                    continue
                if item.get("es_exterior", False):
                    exteriores.append(str(item.get("nombre", "")))
                else:
                    faltan.append(str(item.get("nombre", "")))
            if faltan:
                hallazgos.append(HallazgoE(
                    "EM01", "aviso",
                    f"programa mínimo {familia} (§106-109): falta "
                    + ", ".join(faltan), MEDIDO,
                    "programa mínimo del documento"))
            else:
                hallazgos.append(HallazgoE(
                    "EM01", "ok",
                    f"programa mínimo {familia} (§106-109) completo en "
                    f"el proyecto ({len(vivos)} locales)", MEDIDO,
                    "programa mínimo del documento"))
            if exteriores:
                hallazgos.append(HallazgoE(
                    "EM01", "aviso",
                    "espacios exteriores del terreno a verificar en el "
                    "sitio: " + ", ".join(exteriores)
                    + " (§13/§14/§68)", PENDIENTE,
                    "programa mínimo del documento"))

    # EM02 relaciones del §98-101 (prioritarias) --------------------------------
    for familia in familias:
        pares_3 = _pares_prioritarios(specs, familia, por_tipo, relaciones)
        if pares_3:
            faltan = [f"{a}-{b}" for a, b, presente in pares_3
                      if not presente]
            if faltan:
                hallazgos.append(HallazgoE(
                    "EM02", "aviso",
                    f"relaciones prioritarias del §98-101 sin trazar en "
                    f"{familia}: " + ", ".join(faltan)
                    + " (el asistente las sugiere; se revisan al "
                      "regenerar)", MEDIDO,
                    "relaciones del §98-101"))
            else:
                hallazgos.append(HallazgoE(
                    "EM02", "ok",
                    f"relaciones prioritarias del §98-101 presentes en "
                    f"{familia}", MEDIDO, "relaciones del §98-101"))

    # EM03 prohibiciones de flujo del §102 (limpio/sucio: nivel 0) ----
    if familias:
        prohibidas = _pares_prohibidos(specs, por_tipo, relaciones)
        if prohibidas:
            hallazgos.append(HallazgoE(
                "EM03", "fallo",
                "flujo NO recomendado (nivel 0 del §102) presente: "
                + "; ".join(prohibidas)
                + " (alimentos-residuos, estudiantes-carga, cocina-"
                  "basura y ropa limpia-sucia nunca se cruzan)",
                MEDIDO, "flujos del §102 (limpio/sucio)"))
        elif _hay_tipos_de_prohibidas(specs, por_tipo):
            hallazgos.append(HallazgoE(
                "EM03", "ok",
                "sin cruces de circulación limpia/sucia (§102)", MEDIDO,
                "flujos del §102 (limpio/sucio)"))

    indice = 4  # EM04 en adelante, renumerado dinámicamente abajo

    # EM04 aulas vs capacidad (§4/§6/§111 y REGLA_01/11) -------------------
    for familia in familias:
        cap = specs.capacidad(familia)
        if familia in (FAMILIA_PRI, FAMILIA_SEC):
            tipo_aula = "CLASSROOM"
            alumnos = _fl(meta.get("alumnos"))
            por_aula = _fl(meta.get("alumnos_por_aula")) or _fl(
                (cap.get("alumnos_por_aula") or {})
                .get("rec_max", 25.0))
            aulas = len(por_tipo.get(tipo_aula, []))
            if alumnos <= 0:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "info",
                    f"sin capacidad definida: con la metadata del "
                    "asistente se comprueba NUM_AULAS >= CEIL(alumnos / "
                    "alumnos por aula) del §4/§111", PENDIENTE,
                    "capacidad del documento (§4)"))
            else:
                requeridas = math.ceil(alumnos / max(por_aula, 1.0))
                if aulas >= requeridas:
                    hallazgos.append(HallazgoE(
                        f"EM{indice:02d}", "ok",
                        f"{aulas} aula(s) >= {requeridas} requeridas "
                        f"para {alumnos:.0f} alumnos a {por_aula:.0f} "
                        "por aula (REGLA_01/11)", MEDIDO,
                        "capacidad del documento (§4/§111)"))
                else:
                    hallazgos.append(HallazgoE(
                        f"EM{indice:02d}", "fallo",
                        f"{aulas} aula(s) < {requeridas} requeridas "
                        f"para {alumnos:.0f} alumnos a {por_aula:.0f} "
                        "por aula (REGLA_01/11: NUM_AULAS >= "
                        "CEIL(alumnos/alumnos por aula))", MEDIDO,
                        "capacidad del documento (§4/§111)"))
        elif familia == FAMILIA_CI:
            grupos = _fl(meta.get("grupos"))
            aulas_inf = len(por_tipo.get("AULA_INFANTIL", []))
            if grupos <= 0:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "info",
                    "sin grupos definidos: con la metadata se comprueba "
                    "un aula infantil por grupo (§9)", PENDIENTE,
                    "capacidad del documento (§9)"))
            elif aulas_inf >= grupos:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "ok",
                    f"{aulas_inf} aula(s) infantil(es) >= {grupos:.0f} "
                    "grupos del §9", MEDIDO,
                    "capacidad del documento (§9)"))
            else:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "fallo",
                    f"{aulas_inf} aula(s) infantil(es) < {grupos:.0f} "
                    "grupos (§9: cada grupo con su aula)", MEDIDO,
                    "capacidad del documento (§9)"))
        else:
            plazas = _fl(meta.get("plazas"))
            dorms = [s for s in por_tipo.get("BEDROOM", [])
                     + por_tipo.get("DORMITORIO_COLETIVO", [])]
            if plazas > 0 and dorms:
                # plazas admisibles a 4-6 m2/persona (§51) o 9 m2
                # individual (§49): techo por local
                area_dorms = sum(_area(s) for s in dorms)
                admite = math.floor(area_dorms / 4.0)
                if admite >= plazas:
                    hallazgos.append(HallazgoE(
                        f"EM{indice:02d}", "ok",
                        f"{len(dorms)} dormitorio(s) de "
                        f"{area_dorms:.0f} m2 admiten >= {plazas:.0f} "
                        "plazas a 4-6 m2/persona (§49-51)", MEDIDO,
                        "capacidad del documento (§48-51)"))
                else:
                    hallazgos.append(HallazgoE(
                        f"EM{indice:02d}", "fallo",
                        f"{len(dorms)} dormitorio(s) de "
                        f"{area_dorms:.0f} m2 admiten ~{admite} plazas "
                        f"< {plazas:.0f} pedidas a 4-6 m2/persona "
                        "(§49-51)", MEDIDO,
                        "capacidad del documento (§48-51)"))
            else:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "info",
                    "sin plazas definidas: con la metadata se comprueba "
                    "el área de dormitorios contra las plazas (REGLA_10)",
                    PENDIENTE, "capacidad del documento (§48-51)"))
        indice += 1

    # EM05+ dormitorios por local (REGLA_10) --------------------------------------
    dormitorios = por_tipo.get("DORMITORIO_COLETIVO", []) \
        + por_tipo.get("BEDROOM", [])
    if dormitorios:
        detalle, problemas = [], []
        for d in dormitorios:
            area = _area(d)
            if area <= 1e-6:
                continue
            detalle.append(f"{_codigo(d)} {area:.1f} m2")
            if area + 1e-9 < 16.0:
                problemas.append(_codigo(d))
        if detalle:
            texto = ("dormitorios: " + ", ".join(detalle[:6])
                     + ("; individuales 9-14 m2, 2 plazas 14-20 m2 y "
                        "colectivos 4-6 m2/persona (§49-51)"))
            if problemas:
                texto = (f"{len(problemas)} dormitorio(s) por debajo de "
                         "16 m2 (4 personas a 4 m2, §51): " +
                         ", ".join(problemas[:5]))
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "aviso", texto, MEDIDO,
                    "dormitorios del documento (§49-51)"))
            else:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "ok", texto, MEDIDO,
                    "dormitorios del documento (§49-51)"))
            indice += 1

    # EM06+ comedor por capacidad (REGLA_08, §36/§56) --------------------------
    comedores = por_tipo.get("DINING_HALL", []) \
        + por_tipo.get("DINING_ROOM", [])
    if comedores:
        area_com = sum(_area(s) for s in comedores)
        poblacion = _fl(meta.get("alumnos")) or _fl(meta.get("plazas")) \
            or _fl(meta.get("ninios"))
        if poblacion > 0:
            # simultaneidad del §56 (150 plazas x 50% = 75 comensales);
            # para escuelas el documento no fija turno, 50% es la
            # estimación conservadora informada
            comensales = math.ceil(poblacion * 0.5)
            requerido = comensales * 1.20
            if area_com + 1e-9 >= requerido:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "ok",
                    f"comedor(es) de {area_com:.0f} m2 >= "
                    f"{requerido:.0f} m2 para {comensales} comensales "
                    f"simultáneos a 1.20-1.80 m2 (REGLA_08; "
                    f"simultaneidad 50% del §56)", MEDIDO,
                    "comedor del documento (§36/§56)"))
            else:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "aviso",
                    f"comedor(es) de {area_com:.0f} m2 < "
                    f"{requerido:.0f} m2 para {comensales} comensales "
                    "simultáneos a 1.20 m2 mínimo (REGLA_08; ajusta "
                    "turnos o amplía)", MEDIDO,
                    "comedor del documento (§36/§56)"))
        else:
            hallazgos.append(HallazgoE(
                f"EM{indice:02d}", "info",
                f"comedor(es) de {area_com:.0f} m2; el dimensionado "
                "comprueba 1.20-1.80 m2 por comensal simultáneo "
                "(REGLA_08, §36/§56) con la capacidad definida",
                PENDIENTE, "comedor del documento (§36/§56)"))
        indice += 1

    # escaleras del §45 --------------------------------------------------------
    if escaleras or len(niveles) > 1:
        if not escaleras:
            hallazgos.append(HallazgoE(
                f"EM{indice:02d}", "aviso",
                "más de un nivel sin escalera trazada", MEDIDO,
                "circulación vertical (§45)"))
        else:
            estrechas = []
            for esc in escaleras:
                ancho = _fl(getattr(esc, "width_m", 0.0))
                if ancho > 0 and ancho + 1e-9 < ALTURA_ESCALERA_MIN_M:
                    estrechas.append(f"{_codigo(esc)} ({ancho:.2f} m)")
            if estrechas:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "aviso",
                    "escalera(s) por debajo del mínimo funcional "
                    f"{ALTURA_ESCALERA_MIN_M:.2f} m (§45): "
                    + ", ".join(estrechas), MEDIDO,
                    "circulación vertical (§45)"))
            else:
                hallazgos.append(HallazgoE(
                    f"EM{indice:02d}", "ok",
                    f"{len(escaleras)} escalera(s) >= "
                    f"{ALTURA_ESCALERA_MIN_M:.2f} m de ancho mínimo "
                    "funcional (§45; el ancho definitivo va por "
                    "ocupación §85)", MEDIDO,
                    "circulación vertical (§45)"))
        indice += 1

    # punto de reunión del §104-105 (informativo) ------------------------------
    if familias:
        poblacion = _fl(meta.get("alumnos")) or _fl(meta.get("plazas")) \
            or _fl(meta.get("ninios"))
        if poblacion > 0:
            area_min = poblacion * REUNION_M2_MIN
            area_max = poblacion * REUNION_M2_MAX
            hallazgos.append(HallazgoE(
                f"EM{indice:02d}", "info",
                f"punto de reunión (§104-105): AREA_REUNION = "
                f"{poblacion:.0f} x 0.5-1.0 = {area_min:.0f}-{area_max:.0f} "
                "m2 fuera del edificio, señalizado y fuera de la "
                "circulación vehicular", PENDIENTE,
                "punto de reunión (§104-105)"))
        else:
            hallazgos.append(HallazgoE(
                f"EM{indice:02d}", "info",
                "punto de reunión (§104-105): define la población "
                "evacuada para calcular AREA_REUNION = POBLACION x "
                "0.5-1.0 m2", PENDIENTE,
                "punto de reunión (§104-105)"))
        indice += 1

    # alturas libres del nivel (§2) ---------------------------------------------
    alturas_dna = ALTURA_LIBRE_MIN
    if familias and niveles:
        altura_min_fam = min(alturas_dna.get(f, 2.70)
                             for f in familias)
        bajas = []
        for niv in niveles:
            h = _fl(getattr(niv, "height_m", 0.0))
            if h > 0 and h + 1e-9 < altura_min_fam:
                bajas.append(f"{_codigo(niv)} ({h:.2f} m)")
        if bajas:
            hallazgos.append(HallazgoE(
                f"EM{indice:02d}", "aviso",
                "nivel(es) con altura libre por debajo de la mínima "
                f"de la tipología ({altura_min_fam:.2f} m, §2): "
                + ", ".join(bajas), MEDIDO, "alturas libres (§2)"))
        else:
            hallazgos.append(HallazgoE(
                f"EM{indice:02d}", "ok",
                f"alturas libres de los niveles >= "
                f"{altura_min_fam:.2f} m (§2)", MEDIDO,
                "alturas libres (§2)"))
        indice += 1

    # seguridad infantil del §89 (pendiente de verificación) ---------------
    if any(f in (FAMILIA_CI, FAMILIA_PRI) for f in familias):
        seg = specs.seguridad_infantil
        prohibido = "; ".join(seg.get("prohibido", [])[:6])
        hallazgos.append(HallazgoE(
            f"EM{indice:02d}", "info",
            "seguridad infantil (§89): verificar que no hay "
            f"{prohibido}; con control visual, cierres seguros y "
            "protección de ventanas y escaleras", PENDIENTE,
            "seguridad infantil (§89)"))
        indice += 1

    # temas que el documento remite a cálculo (§74/§78/§83-85/§87/§90-91)
    for pos, tema in enumerate(specs.requiere_calculo):
        hallazgos.append(HallazgoE(
            f"RC{pos + 1:02d}", "info",
            f"{tema.get('tema', '')} (§{tema.get('seccion', '')}): "
            f"{tema.get('motivo', '')}", REQUIERE_CALCULO,
            "REQUIERE_CALCULO_ESPECIALIZADO (§74/§78/§83-85)"))

    # locales (control dimensional por local, como el comercial) --------------
    informes: List[Dict[str, Any]] = []
    resumen = {"ok": 0, "avisos": 0, "fallos": 0, "pendientes": 0}

    def _cuenta(h: Dict[str, Any]) -> None:
        if h.get("estado") != MEDIDO:
            resumen["pendientes"] += 1
        elif h.get("severidad") == "ok":
            resumen["ok"] += 1
        elif h.get("severidad") == "aviso":
            resumen["avisos"] += 1
        elif h.get("severidad") == "fallo":
            resumen["fallos"] += 1
        else:
            resumen["pendientes"] += 1

    for hallazgo in hallazgos:
        _cuenta(hallazgo.como_dict())
    for local in vivos:
        try:
            informe = validar_local(ctx, local.id)
        except Exception:  # noqa: BLE001 — un local no tumba el resto
            continue
        informes.append(informe)
        for h in informe["hallazgos"]:
            _cuenta(h)

    return {
        "edificacion": str(edif.get("nombre", "")) if edif else "",
        "uso": uso_gui,
        "familias": familias,
        "tamano": tamano,
        "hallazgos": [h.como_dict() for h in hallazgos],
        "locales": informes,
        "resumen": resumen,
        "prioridades": dict(specs.prioridades),
        "conflictos": [f"{c.get('id', '')} "
                       f"({c.get('severidad', '')}): "
                       f"{c.get('condicion', '')} -> {c.get('check', '')}"
                       for c in specs.conflictos],
        "reglas": [f"{r.get('id', '')}: {r.get('regla', '')} "
                   f"-> {r.get('check', '')}"
                   for r in specs.reglas_validacion],
        "normativa": list(specs.normativa),
        "documentacion": list(specs.documentacion),
        "advertencia": specs.advertencia,
        "fuentes": specs.fuentes,
        "specs": _resumen_specs(specs),
    }


# ----------------------------------------------------------------------
# helpers de lectura (sólo lectura, tolerantes a proyectos a medio hacer)
# ----------------------------------------------------------------------

# huellas características por familia para INFERIR la familia cuando la
# metadata del asistente no la trae: evito tipos genéricos (CLASSROOM,
# BATHROOM, OFFICE...) que otros usos también generan
_HUELLAS_CI: Tuple[str, ...] = (
    "AULA_INFANTIL", "SALA_CUNA", "HIGIENE_CI", "JUEGO_INTERIOR",
)
_HUELLAS_SEC: Tuple[str, ...] = (
    "LAB_COMPUTACION", "TALLER_TECNOLOGICO", "SALA_ARTE", "SALA_MUSICA",
)
_HUELLAS_ALB: Tuple[str, ...] = (
    "DORMITORIO_COLETIVO", "SALA_ESTUDIO", "SALA_CONVIVENCIA",
    "MONITORES",
)


def _resumen_specs(specs: EducacionSpecs) -> Dict[str, int]:
    return specs.resumen()


def _fl(valor: Any) -> float:
    try:
        return float(valor or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _lista(ctx: Any, kind: str) -> List[Any]:
    try:
        return list(ctx.architecture.list(kind, ctx.project.id))
    except Exception:  # noqa: BLE001 — sin proyecto cargado
        return []


def _codigo(entidad: Any) -> str:
    return str(getattr(entidad, "code", "") or getattr(entidad, "id", "?"))


def _nombre(entidad: Any) -> str:
    nombre = str(getattr(entidad, "name", "") or "").strip()
    codigo = _codigo(entidad)
    return f"{nombre} ({codigo})" if nombre else codigo


def _area(espacio: Any) -> float:
    try:
        return max(float(espacio.area_m2()), 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _ancho_bbox(espacio: Any) -> float:
    xs = [p[0] for p in (getattr(espacio, "boundary", []) or [])]
    return (max(xs) - min(xs)) if len(xs) >= 2 else 0.0


def _profundidad_bbox(espacio: Any) -> float:
    ys = [p[1] for p in (getattr(espacio, "boundary", []) or [])]
    return (max(ys) - min(ys)) if len(ys) >= 2 else 0.0


def _area_envolvente(grupo: List[Any]) -> float:
    xs, ys = [], []
    for s in grupo:
        for p in getattr(s, "boundary", []) or []:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return 0.0
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _dna_de(ctx: Any, uso: str) -> Any:
    registro = getattr(ctx, "dna_registry", None)
    if registro is None:
        return None
    try:
        return registro.get(str(uso or ""))
    except Exception:  # noqa: BLE001
        return None


def _ancho_minimo_dna(dna: Any) -> Optional[float]:
    if dna is None:
        return None
    try:
        valor = float(getattr(dna, "minimum_width", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    return valor or None


def _puerta_minima_dna(dna: Any) -> Optional[float]:
    if dna is None:
        return None
    try:
        valor = float((dna.metadata.get("neufert") or {}).get("puerta_m")
                      or 0.0)
    except (TypeError, ValueError, AttributeError):
        return None
    return valor or None


def _pasillo_minimo_dna(dna: Any) -> Optional[float]:
    if dna is None:
        return None
    try:
        valor = float(dna.metadata.get("pasillo_m") or 0.0)
    except (TypeError, ValueError, AttributeError):
        return None
    return valor or None


def _altura_nivel(ctx: Any, local: Any) -> float:
    """Altura del nivel que hospeda al local (0 si no consta)."""
    try:
        nivel = ctx.architecture.get("LEVEL", local.level_id) \
            if getattr(local, "level_id", "") else None
        if nivel is not None:
            return float(getattr(nivel, "height_m", 0.0) or 0.0)
    except Exception:  # noqa: BLE001 — nivel ausente
        pass
    return 0.0


def _ancho_de_vano(ctx: Any, codigo: str) -> Optional[float]:
    try:
        for kind in ("DOOR", "WINDOW", "OPENING"):
            entidad = ctx.architecture.get_by_code(kind, codigo)
            if entidad is not None:
                return float(entidad.width_m)
    except Exception:  # noqa: BLE001 — código inexistente
        return None
    return None


def _pasillos_estrechos(ctx: Any, datos: Dict[str, Any],
                        minimo: float) -> Optional[List[str]]:
    """Códigos de pasillos (SP de uso CORRIDOR) del nivel < mínimo.

    None cuando el nivel no tiene pasillos que comprobar.
    """
    try:
        nivel = datos.get("level_id")
        pasillos = [s for s in ctx.architecture.list("SPACE",
                                                     ctx.project.id)
                    if getattr(s, "space_type", "") == "CORRIDOR"
                    and getattr(s, "level_id", None) == nivel
                    and len(getattr(s, "boundary", []) or []) >= 3]
    except Exception:  # noqa: BLE001 — sin arquitectura cargada
        return None
    if not pasillos:
        return None
    estrechos: List[str] = []
    for pasillo in pasillos:
        try:
            ancho = float(getattr(pasillo, "width_m", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if ancho <= 0:
            continue
        if ancho + 1e-9 < minimo:
            estrechos.append(str(getattr(pasillo, "code", "?")))
    return estrechos


def _familias_presentes(specs: EducacionSpecs, meta: Any,
                        por_tipo: Dict[str, List[Any]]) -> List[str]:
    """Familias educacionales del proyecto: metadata del asistente
    primero, huellas características después (nunca tipos genéricos)."""
    familias: List[str] = []
    f_meta = str((meta or {}).get("familia", "") or "").upper() \
        if isinstance(meta, dict) else ""
    if f_meta and f_meta in [k.upper()
                             for k in specs.programa_minimo.keys()]:
        familias.append(f_meta)
        return familias
    if any(t in por_tipo for t in _HUELLAS_CI):
        familias.append(FAMILIA_CI)
    if any(t in por_tipo for t in _HUELLAS_SEC):
        familias.append(FAMILIA_SEC)
    if any(t in por_tipo for t in _HUELLAS_ALB):
        familias.append(FAMILIA_ALB)
    if not familias and len(por_tipo.get("CLASSROOM", [])) >= 3:
        # primaria: aulas en serie sin huellas de los otros usos
        familias.append(FAMILIA_PRI)
    return familias


def _pares_prioritarios(specs: EducacionSpecs, familia: str,
                        por_tipo: Dict[str, List[Any]],
                        relaciones: List[Any]) -> List[Tuple[str, str,
                                                             bool]]:
    """Pares nivel 3 del §98-101 de la familia: (a, b, vinculados).

    «Vinculados» = existe una relación espacial trazada entre cualquier
    instancia de los dos space_types (en cualquier orden).
    """
    pares: List[Tuple[str, str, bool]] = []
    vistos: set = set()
    for r in specs.relaciones:
        if str(r.get("familia", "")) != familia \
                or str(r.get("nivel", "")) != "3":
            continue
        a, b = str(r.get("a", "")), str(r.get("b", ""))
        clave = frozenset((a, b))
        if clave in vistos:
            continue
        vistos.add(clave)
        presente = False
        tipos_a = specs.tipos_de_relacion(a, familia)
        tipos_b = specs.tipos_de_relacion(b, familia)
        # escaleras y núcleos no son locales: el trazado los dibuja
        # siempre, así que el par no se exige como relación espacial
        if any(t in ("STAIR", "CORE") for t in tipos_a + tipos_b):
            continue
        # un tipo ausente del proyecto no puede dar la cara: el
        # programa mínimo (EM01) ya avisa de que falta
        if not por_tipo.get(next(iter(tipos_a), "")) \
                or not por_tipo.get(next(iter(tipos_b), "")):
            continue
        for tipo_a in tipos_a:
            for tipo_b in tipos_b:
                if not por_tipo.get(tipo_a) or not por_tipo.get(tipo_b):
                    continue
                if _relacion_entre_tipos(relaciones, por_tipo,
                                         tipo_a, tipo_b):
                    presente = True
                    break
            if presente:
                break
        pares.append((a, b, presente))
    return pares


def _relacion_entre_tipos(relaciones: List[Any],
                          por_tipo: Dict[str, List[Any]],
                          tipo_a: str, tipo_b: str) -> bool:
    """True si alguna relación espacial une instancias de ambos tipos."""
    ids_a = {str(getattr(s, "id", "")) for s in por_tipo.get(tipo_a, [])}
    ids_b = {str(getattr(s, "id", "")) for s in por_tipo.get(tipo_b, [])}
    if not ids_a or not ids_b:
        return False
    for rel in relaciones:
        de = str(getattr(rel, "from_space_id", ""))
        a_ = str(getattr(rel, "to_space_id", ""))
        if (de in ids_a and a_ in ids_b) or (de in ids_b and a_ in ids_a):
            return True
    return False


def _pares_prohibidos(specs: EducacionSpecs,
                      por_tipo: Dict[str, List[Any]],
                      relaciones: List[Any]) -> List[str]:
    """Pares nivel 0 del §98-102 realmente trazados (máximo 5)."""
    detalles: List[str] = []
    vistos: set = set()
    for r in specs.relaciones:
        if str(r.get("nivel", "")) != "0":
            continue
        a, b = str(r.get("a", "")), str(r.get("b", ""))
        for tipo_a in specs.tipos_de_relacion(a):
            for tipo_b in specs.tipos_de_relacion(b):
                if not por_tipo.get(tipo_a) or not por_tipo.get(tipo_b):
                    continue
                for sa in por_tipo[tipo_a]:
                    for sb in por_tipo[tipo_b]:
                        if sa is sb:
                            continue
                        if not _relacion_entre_tipos(
                                relaciones, por_tipo, tipo_a, tipo_b):
                            continue
                        clave = f"{tipo_a}|{tipo_b}"
                        if clave in vistos:
                            continue
                        vistos.add(clave)
                        etiqueta = a if a not in (
                            PUBLICO, ESTUDIANTES, RUIDO) \
                            else tipo_a.lower()
                        detalles.append(
                            f"{_nombre(sa)} ({etiqueta}) con "
                            f"{_nombre(sb)} ({b.lower()})")
                        if len(detalles) >= 5:
                            return detalles
    return detalles


def _hay_tipos_de_prohibidas(specs: EducacionSpecs,
                             por_tipo: Dict[str, List[Any]]) -> bool:
    """True si en el proyecto hay tipos involucrados en prohibiciones
    del §102 (para dar el «ok» cuando no hay ninguna traza)."""
    for r in specs.relaciones:
        if str(r.get("nivel", "")) != "0":
            continue
        tipos_a = specs.tipos_de_relacion(str(r.get("a", "")))
        tipos_b = specs.tipos_de_relacion(str(r.get("b", "")))
        if any(t in por_tipo for t in tipos_a) \
                and any(t in por_tipo for t in tipos_b):
            return True
    return False


# ----------------------------------------------------------------------
def texto_validacion_educacion(informe: Dict[str, Any]) -> str:
    """Informe educacional listo para consola o cuadro de texto
    (cp1252, sin flechas ni emojis)."""
    lineas: List[str] = []
    cabecera = "VALIDACIÓN DE ESCUELA / CÍRCULO INFANTIL / ALBERGUE " \
               "(documento)"
    if informe.get("edificacion"):
        cabecera += f" - {informe['edificacion']}"
    lineas.append(cabecera)
    datos = []
    if informe.get("uso"):
        datos.append(f"uso {informe['uso']}")
    if informe.get("familias"):
        datos.append("familia(s): " + ", ".join(informe["familias"]))
    if informe.get("tamano"):
        datos.append(f"tamaño {informe['tamano']}")
    if datos:
        lineas.append(", ".join(datos))
    lineas.append("")

    lineas.append("Comprobaciones del edificio:")
    for x in informe.get("hallazgos", []):
        marca = {"ok": "[OK]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(x["severidad"], "[?]")
        estado = {"medido": "", "pendiente": " (pendiente)",
                  "requiere calculo":
                      " (REQUIERE_CALCULO_ESPECIALIZADO)"}.get(
            x.get("estado", ""), "")
        lineas.append(f"{marca} {x['codigo']}: {x['mensaje']}{estado}")
    lineas.append("")

    locales = informe.get("locales", [])
    if locales:
        con_fallos = [l for l in locales
                      if any(h.get("severidad") == "fallo"
                             for h in l.get("hallazgos", []))]
        lineas.append(f"Locales revisados: {len(locales)} "
                      f"({len(con_fallos)} con fallos dimensionales)")
        for l in con_fallos[:8]:
            for h in l.get("hallazgos", []):
                if h.get("severidad") != "fallo":
                    continue
                lineas.append(f"  [X] {l.get('local')} "
                              f"{l.get('nombre') or ''}: "
                              f"{h['codigo']} {h['mensaje']}")
        lineas.append("")

    resumen = informe.get("resumen", {})
    lineas.append(f"Resumen: {resumen.get('ok', 0)} cumplen, "
                  f"{resumen.get('avisos', 0)} avisos, "
                  f"{resumen.get('fallos', 0)} fallos, "
                  f"{resumen.get('pendientes', 0)} pendientes o de "
                  "cálculo.")

    reglas = informe.get("reglas", [])
    if reglas:
        lineas.append("")
        lineas.append("Reglas de validación del documento (§111-112):")
        for texto in reglas:
            lineas.append(f"· {texto}")

    prioridades = informe.get("prioridades", {})
    if prioridades:
        lineas.append("")
        lineas.append("Prioridades del documento:")
        for clave in sorted(prioridades.keys()):
            lineas.append(f"· {clave} {prioridades[clave]}")

    conflictos = informe.get("conflictos", [])
    if conflictos:
        lineas.append("")
        lineas.append("Conflictos del documento (§115) que detectan los "
                      "motores de clash/validación al regenerar:")
        for texto in conflictos:
            lineas.append(f"· {texto}")

    normativa = informe.get("normativa", [])
    if normativa:
        lineas.append("")
        lineas.append("Normativa seleccionable (§124): "
                      + ", ".join(str(n) for n in normativa))

    documentacion = informe.get("documentacion", [])
    if documentacion:
        lineas.append("Documentación de entrega (§120): "
                      + ", ".join(str(d) for d in documentacion))

    lineas.append("")
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


__all__ = [
    "HallazgoE", "EducacionSpecs", "cargar_specs", "vaciar_cache",
    "validar_local", "validar_proyecto", "texto_validacion_educacion",
    "etiquetas_tipologias", "tipologia_de_etiqueta", "familia_de_uso",
    "tamanos_parametricos", "tamano_de_etiqueta",
    "FAMILIA_PRI", "FAMILIA_SEC", "FAMILIA_CI", "FAMILIA_ALB",
    "FAMILIAS", "USOS_EDUCATIVOS", "SIN_TAMANO",
    "USO_GUI_PRI", "USO_GUI_SEC", "USO_GUI_CI", "USO_GUI_ALB",
    "MEDIDO", "PENDIENTE", "REQUIERE_CALCULO",
    "ALTURA_ESCALERA_MIN_M", "ANCHO_PUERTA_EVAC_M",
    "PLAZA_ANCHO_MIN_M", "PLAZA_ACCESIBLE_ANCHO_M",
    "REUNION_M2_MIN", "REUNION_M2_MAX", "PROF_AULA_MAX_M",
    "ALTURA_LIBRE_MIN",
]
