"""Centros comerciales y edificios de oficinas (v3.25.0).

Integra el documento «Especificaciones técnicas y dimensionales -
Centros Comerciales y Edificios de Oficinas» v2.0 (104 secciones)
como datos versionados bajo ``resources/knowledge/comercial_specs.json``
— nunca hardcodeados: 20 tipologías CC-01..CC-10 / OF-01..OF-10,
59 cuadros de cotas MIN/REC con su unidad y nota, relaciones
espaciales del §78 (escala 0-3 con las prohibiciones duras
residuos/carga/técnicos contra público), programas mínimos del
§89-90, porcentajes de áreas del §81, eficiencia de planta del §82,
conflictos del §95 con las prioridades P01-P12, normativa
seleccionable del §97 y fuentes del §98 (IBC 2024).

Tres piezas operativas:

1. CONSULTAS para el asistente de edificación: tipologías con
   etiquetas de GUI, cuadros por space_type y programa mínimo por
   familia.

2. PROGRAMA PARAMÉTRICO: el asistente (``ui.building_wizard``) carga
   los locales del §89-90 con medidas derivadas de los cuadros MIN/REC
   y las relaciones del §78.

3. VALIDACIÓN: ``validar_local`` (control dimensional de UN local
   contra su cuadro: superficie, ancho, altura libre, puertas,
   pasillos) y ``validar_proyecto`` (programa mínimo, relaciones
   del §78, porcentajes del §81, eficiencia del §82, estacionamiento
   del §45, evacuación IBC 2024 del §17/§61 y galería del §6) con
   estados HONESTOS medido / pendiente / requiere cálculo (§58/§101/
   §103: HVAC, rociadores, CCTV, escaleras mecánicas y la evacuación
   por ocupación quedan marcados, sin inventar números). Sólo LEE el
   proyecto: no crea entidades ni necesita commit.

Uso headless:
    from domain.comercial_specs import cargar_specs, validar_proyecto
    informe = validar_proyecto(ctx)
    print(texto_validacion_comercial(informe))
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.paths import resource_path
from core.errors import DomainError

_SPECS_CACHE: List["ComercialSpecs"] = []

# estados de los hallazgos (los mismos del catálogo de viviendas)
MEDIDO = "medido"
PENDIENTE = "pendiente"
REQUIERE_CALCULO = "requiere calculo"

# familias del documento (claves de programa_minimo / relaciones)
FAMILIA_CC = "CENTRO_COMERCIAL"
FAMILIA_OF = "OFICINAS"

# usos de la GUI del asistente (paso 1) y su familia del documento
USO_GUI_CC = "Centro comercial"
USO_GUI_OF = "Oficinas (torre/corporativo)"
FAMILIA_DE_USO: Dict[str, str] = {USO_GUI_CC: FAMILIA_CC,
                                  USO_GUI_OF: FAMILIA_OF}

# cotas generales de referencia (el cuadro del JSON manda si consta)
ALTURA_LIBRE_MIN_CC_M = 3.0      # CC-GEN-001 (§3.01)
ALTURA_LIBRE_MIN_OF_M = 2.6      # OF-GEN-002 (§3.02)
ANCHO_GALERIA_MIN_M = 3.0        # CC-CIRC-001 (§6.01)
GALERIA_GRAN_CENTRO_M = 6.0      # gran centro comercial (§6.01)
AREA_GRAN_CENTRO_M2 = 5000.0
PLAZA_ANCHO_MIN_M = 2.40         # CC-EST-001 (§45)
PLAZA_ACCESIBLE_ANCHO_M = 3.60   # CC-EST-001 (§45)
ANCHO_ESCALERA_EVAC_M = 1.118    # OF-EVA-001 / IBC 2024 (§17/§61)
ANCHO_PUERTA_EVAC_M = 0.914      # IBC 2024: <50 ocupantes (§17/§61)
ALTURA_RUTA_EVAC_M = 2.286       # OF-EVA-001 / IBC 2024 (§61)
ANCHO_PUERTA_GENERAL_M = 0.80    # CC-PUE-001: mínima de despachos

# pseudo-códigos de las relaciones del §78: «PÚBLICO» y «TÉCNICOS»
# se expanden a los space_types reales del DNA
PUBLICO = "__PUBLICO__"
TECNICOS = "__TECNICOS__"

TIPOS_PUBLICOS: Tuple[str, ...] = (
    "ENTRANCE", "VESTIBULE", "GALLERY", "RETAIL_LOCAL", "TIENDA_ANCLA",
    "ATRIUM", "RECEPTION", "WAITING_ROOM", "RESTAURANT", "CAFETERIA",
    "DINING_HALL",
)
TIPOS_TECNICOS_REL: Tuple[str, ...] = (
    "ELECTRICAL_ROOM", "TELECOM_ROOM", "SERVER_ROOM", "HVAC_ROOM",
    "PUMP_ROOM",
)


@dataclass
class HallazgoC:
    """Resultado de una comprobación CC/OF del documento."""

    codigo: str
    severidad: str          # "ok" | "aviso" | "fallo" | "info"
    mensaje: str
    estado: str = MEDIDO    # medido | pendiente | requiere calculo
    fuente: str = "documento comercial"

    def como_dict(self) -> Dict[str, Any]:
        return {"codigo": self.codigo, "severidad": self.severidad,
                "mensaje": self.mensaje, "estado": self.estado,
                "fuente": self.fuente}


@dataclass
class ComercialSpecs:
    """Registro del documento comercial versionado."""

    version: str = ""
    fuente_doc: str = ""
    advertencia: str = ""
    principio: Dict[str, Any] = field(default_factory=dict)
    tipologias: List[Dict[str, Any]] = field(default_factory=list)
    cuadros: List[Dict[str, Any]] = field(default_factory=list)
    relaciones: List[Dict[str, Any]] = field(default_factory=list)
    escala_relaciones: Dict[str, str] = field(default_factory=dict)
    relacion_a_space: Dict[str, str] = field(default_factory=dict)
    programa_minimo: Dict[str, List[Dict[str, Any]]] = \
        field(default_factory=dict)
    porcentajes_area: List[Dict[str, Any]] = field(default_factory=list)
    eficiencia_planta: Dict[str, Any] = field(default_factory=dict)
    conflictos: List[Dict[str, Any]] = field(default_factory=list)
    prioridades: Dict[str, str] = field(default_factory=dict)
    normativa: List[str] = field(default_factory=list)
    fuentes: List[str] = field(default_factory=list)
    documentacion: List[str] = field(default_factory=list)
    requiere_calculo: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    @staticmethod
    def load_file(path: str) -> "ComercialSpecs":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != "ARQ_GEN_COMERCIAL_SPECS":
            raise DomainError(
                message="El archivo de especificaciones comerciales no "
                        "tiene el formato esperado",
                code="ARQ-CCM-001",
                context={"format": data.get("format")},
                suggested_action="Restaure resources/knowledge/"
                                 "comercial_specs.json del paquete.")
        return ComercialSpecs(
            version=str(data.get("version", "")),
            fuente_doc=str(data.get("source", "")),
            advertencia=str(data.get("advertencia", "")),
            principio=dict(data.get("principio", {})),
            tipologias=list(data.get("tipologias", [])),
            cuadros=list(data.get("cuadros", [])),
            relaciones=list(data.get("relaciones", [])),
            escala_relaciones=dict(data.get("escala_relaciones", {})),
            relacion_a_space=dict(data.get("relacion_a_space", {})),
            programa_minimo=dict(data.get("programa_minimo", {})),
            porcentajes_area=list(data.get("porcentajes_area", [])),
            eficiencia_planta=dict(data.get("eficiencia_planta", {})),
            conflictos=list(data.get("conflictos", [])),
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
        """Etiquetas «CC-01 - Galería comercial pequeña» para la GUI."""
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
        """Ítems del programa mínimo del §89-90 para la familia."""
        return list(self.programa_minimo.get(str(familia or ""), []))

    def familias_de_space_type(self, space_type: str) -> List[str]:
        """Familias cuyo programa mínimo usa el space_type dado."""
        texto = str(space_type or "").upper()
        return [familia for familia, items in self.programa_minimo.items()
                if any(str(i.get("space_type", "")).upper() == texto
                       for i in items)]

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

    def tipo_de_relacion(self, codigo: str) -> Optional[str]:
        """Space_type del DNA para el código del §78 (None si es un
        pseudo-código sin expandir o no consta)."""
        tipo = self.relacion_a_space.get(str(codigo or ""))
        if tipo in (None, "", PUBLICO, TECNICOS):
            return None
        return str(tipo)

    def tipos_de_relacion(self, codigo: str) -> Tuple[str, ...]:
        """Space_types que representa un código del §78: un tipo
        concreto, o el conjunto público/técnico de los pseudo-códigos.
        El código llega como «PUBLICO»/«TECNICOS» (clave de la
        relación) o como su valor «__PUBLICO__»/«__TECNICOS__»."""
        codigo = str(codigo or "")
        if codigo in (PUBLICO, "PUBLICO"):
            return TIPOS_PUBLICOS
        if codigo in (TECNICOS, "TECNICOS"):
            return TIPOS_TECNICOS_REL
        tipo = self.tipo_de_relacion(codigo)
        return (tipo,) if tipo else ()

    def nivel_de_relacion(self, familia: str, a: str, b: str) \
            -> Optional[str]:
        """Nivel «0»-«3» del §78 para el par (en cualquier orden)."""
        for r in self.relaciones:
            if str(r.get("familia", "")) != str(familia or ""):
                continue
            if (r.get("a") == a and r.get("b") == b) or \
                    (r.get("a") == b and r.get("b") == a):
                return str(r.get("nivel", ""))
        return None

    def texto_relacion(self, nivel: str) -> str:
        return self.escala_relaciones.get(str(nivel), "?")

    def rango_eficiencia(self, familia: str) -> Optional[Tuple[float,
                                                              float]]:
        rango = self.eficiencia_planta.get(str(familia or ""))
        if not rango or len(rango) != 2:
            return None
        return float(rango[0]), float(rango[1])

    def altura_libre_min(self, familia: str) -> float:
        """Altura libre mínima de referencia por familia (§3)."""
        return (ALTURA_LIBRE_MIN_CC_M if familia == FAMILIA_CC
                else ALTURA_LIBRE_MIN_OF_M)

    def resumen(self) -> Dict[str, int]:
        return {
            "tipologias": len(self.tipologias),
            "cuadros": len(self.cuadros),
            "relaciones": len(self.relaciones),
            "programas": len(self.programa_minimo),
            "porcentajes": len(self.porcentajes_area),
            "conflictos": len(self.conflictos),
            "prioridades": len(self.prioridades),
            "requiere_calculo": len(self.requiere_calculo),
            "fuentes": len(self.fuentes),
        }


# ----------------------------------------------------------------------
_SPECS_PATH = "comercial_specs.json"


def cargar_specs() -> Optional[ComercialSpecs]:
    """Carga (una vez) el documento comercial; None si falta el recurso.

    Sin el recurso el programa sigue funcionando como siempre: las
    especificaciones aconsejan, no bloquean.
    """
    if _SPECS_CACHE:
        return _SPECS_CACHE[0]
    try:
        path = resource_path("knowledge", _SPECS_PATH)
        if not os.path.exists(path):
            return None
        specs = ComercialSpecs.load_file(path)
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


def tipologia_de_etiqueta(etiqueta: str) -> Optional[Dict[str, Any]]:
    specs = cargar_specs()
    if specs is None:
        return None
    return specs.tipologia_de_etiqueta(etiqueta)


# ----------------------------------------------------------------------
# VALIDACIÓN DIMENSIONAL DE UN LOCAL (cuadros MIN/REC del documento)
# ----------------------------------------------------------------------

def validar_local(ctx: Any, ref: str) -> Dict[str, Any]:
    """Control de validación dimensional de UN local contra su cuadro.

    Comprueba contra los cuadros MIN/REC del space_type y del DNA:
    superficie (C01), ancho (C02), altura libre (C03), puertas (C04)
    y pasillos del nivel (C05). El resto del documento (HVAC §50-51,
    rociadores §59, CCTV §56, detección §58, escaleras mecánicas §22,
    evacuación por ocupación §17/§61, drenaje §72) queda «requiere
    cálculo»: es de especialista o de fabricante, no de geometría.
    Sólo LEE el proyecto: no crea entidades ni necesita commit.
    """
    specs = cargar_specs()
    if specs is None:
        raise DomainError(
            message="No se encontró el documento de especificaciones "
                    "comerciales y de oficinas",
            code="ARQ-CCM-002",
            suggested_action="Verifique resources/knowledge/"
                             "comercial_specs.json.")
    from ui.editor_espacios import datos_local, _resolver_local
    datos = datos_local(ctx, ref)
    local = _resolver_local(ctx, ref)
    uso = str(datos.get("uso") or "ROOM")
    hallazgos: List[HallazgoC] = []
    minimos = specs.minimos_de(uso)
    dna = _dna_de(ctx, uso)

    # C01 superficie ------------------------------------------------------
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
    if sup_min:
        if area + 1e-9 >= sup_min:
            hallazgos.append(HallazgoC(
                "C01", "ok",
                f"superficie {area:.2f} m2 >= mínima de programación "
                f"{sup_min:.2f} m2{nota_gamas}", MEDIDO,
                "cuadros MIN/REC del documento / DNA del uso"))
        else:
            hallazgos.append(HallazgoC(
                "C01", "fallo",
                f"superficie {area:.2f} m2 < mínima de programación "
                f"{sup_min:.2f} m2{nota_gamas}", MEDIDO,
                "cuadros MIN/REC del documento / DNA del uso"))
    else:
        hallazgos.append(HallazgoC(
            "C01", "info",
            f"superficie {area:.2f} m2; el uso no tiene mínima en los "
            "cuadros ni en el DNA", MEDIDO,
            "cuadros MIN/REC del documento / DNA del uso"))

    # C02 ancho -------------------------------------------------------------
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
            hallazgos.append(HallazgoC(
                "C02", "ok", f"ancho {ancho:.2f} m >= {limite:.2f} m",
                MEDIDO, origen))
        else:
            hallazgos.append(HallazgoC(
                "C02", "fallo",
                f"ancho {ancho:.2f} m < {limite:.2f} m del uso",
                MEDIDO, origen))

    # C03 altura libre (cota del nivel) ---------------------------------------
    altura_min = minimos["altura"]
    if altura_min is None:
        familias = specs.familias_de_space_type(uso)
        if familias:
            altura_min = min(specs.altura_libre_min(f)
                             for f in familias)
    altura_nivel = _altura_nivel(ctx, local)
    if altura_min and altura_nivel > 0:
        if altura_nivel + 1e-9 >= altura_min:
            hallazgos.append(HallazgoC(
                "C03", "ok",
                f"altura del nivel ({altura_nivel:.2f} m) >= mínima de "
                f"referencia del uso ({altura_min:.2f} m)", MEDIDO,
                "cuadros MIN/REC (§3)"))
        else:
            hallazgos.append(HallazgoC(
                "C03", "fallo",
                f"altura del nivel ({altura_nivel:.2f} m) < mínima de "
                f"referencia del uso ({altura_min:.2f} m); la cota "
                "definitiva la fija la normativa seleccionada (§97)",
                MEDIDO, "cuadros MIN/REC (§3)"))

    # C04 puertas ---------------------------------------------------------------
    puertas = list(datos.get("puertas") or [])
    puerta_min = _puerta_minima_dna(dna)
    limite_puerta = puerta_min or ANCHO_PUERTA_GENERAL_M
    origen_puerta = ("DNA del uso (neufert.puerta_m)"
                     if puerta_min else "CC-PUE-001 (mínima general)")
    if not puertas:
        hallazgos.append(HallazgoC(
            "C04", "aviso", "el local no tiene puertas", MEDIDO,
            origen_puerta))
    else:
        anchos = [w for w in (_ancho_de_vano(ctx, p) for p in puertas)
                  if w is not None]
        estrechas = [f"{p} ({_ancho_de_vano(ctx, p) or 0.0:.2f} m)"
                     for p in puertas
                     if _ancho_de_vano(ctx, p) is not None
                     and _ancho_de_vano(ctx, p) + 1e-9 < limite_puerta]
        if estrechas:
            hallazgos.append(HallazgoC(
                "C04", "fallo",
                "puerta(s) " + ", ".join(estrechas)
                + f" por debajo de {limite_puerta:.2f} m del uso",
                MEDIDO, origen_puerta))
        else:
            mensaje = (f"todas las puertas >= {limite_puerta:.2f} m")
            severidad = "ok"
            if puerta_min is None and anchos and min(anchos) + 1e-9 \
                    < ANCHO_PUERTA_EVAC_M:
                mensaje += ("; el IBC 2024 pide 0.914 m en vías de "
                            "evacuación (§61): revisa las puertas "
                            "menores si sirven a evacuación")
                severidad = "aviso"
            hallazgos.append(HallazgoC(
                "C04", severidad, mensaje, MEDIDO, origen_puerta))

    # C05 pasillo del nivel --------------------------------------------------------
    pasillo_min = _pasillo_minimo_dna(dna)
    if pasillo_min:
        estrechos = _pasillos_estrechos(ctx, datos, pasillo_min)
        if estrechos is None:
            hallazgos.append(HallazgoC(
                "C05", "info",
                "el nivel no tiene pasillos trazados que comprobar",
                MEDIDO, "DNA del uso (pasillo_m)"))
        elif estrechos:
            hallazgos.append(HallazgoC(
                "C05", "aviso",
                "pasillo(s) " + ", ".join(estrechos)
                + f" por debajo de {pasillo_min:.2f} m del uso",
                MEDIDO, "DNA del uso (pasillo_m)"))
        else:
            hallazgos.append(HallazgoC(
                "C05", "ok",
                f"pasillos del nivel >= {pasillo_min:.2f} m", MEDIDO,
                "DNA del uso (pasillo_m)"))

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
# VALIDACIÓN DEL PROYECTO (§89-§95, §6, §45, §61 + locales)
# ----------------------------------------------------------------------

def validar_proyecto(ctx: Any) -> Dict[str, Any]:
    """Validación CC/OF del edificio completo (sólo lectura).

    Devuelve ``{edificacion, familias, hallazgos (del edificio),
    locales (informe por local), resumen, prioridades, conflictos,
    normativa, documentacion, fuentes}``. Las familias se toman de la
    metadata del asistente («comercial.familia») o se infieren de los
    space_types presentes.
    """
    specs = cargar_specs()
    if specs is None:
        raise DomainError(
            message="No se encontró el documento de especificaciones "
                    "comerciales y de oficinas",
            code="ARQ-CCM-002",
            suggested_action="Verifique resources/knowledge/"
                             "comercial_specs.json.")
    from ui.building_wizard import _wizard_building
    _edificio, edif = _wizard_building(ctx)
    meta = edif.get("comercial") or {} if isinstance(edif, dict) else {}
    uso_gui = str(edif.get("uso_social", "")) if edif else ""
    tipologia = str(meta.get("tipologia", "") or "")

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
    area_total = sum(_area(s) for s in vivos)
    hallazgos: List[HallazgoC] = []

    # CM01 programa mínimo del §89-90 ---------------------------------------
    if familias:
        for familia in familias:
            faltan, faltan_tecnicos = [], []
            for item in specs.programa(familia):
                tipo = str(item.get("space_type", ""))
                presente = bool(por_tipo.get(tipo))
                if presente or not item.get("es_local", True):
                    if not item.get("es_local", True) and not presente \
                            and len(niveles) > 1:
                        faltan_tecnicos.append(str(item.get("nombre", "")))
                    continue
                faltan.append(str(item.get("nombre", "")))
            if faltan:
                hallazgos.append(HallazgoC(
                    "CM01", "aviso",
                    f"programa mínimo {familia} (§89-90): falta "
                    + ", ".join(faltan), MEDIDO,
                    "programa mínimo del documento"))
            elif faltan_tecnicos:
                hallazgos.append(HallazgoC(
                    "CM01", "aviso",
                    f"programa {familia}: sin "
                    + ", ".join(faltan_tecnicos)
                    + " con más de un nivel", MEDIDO,
                    "programa mínimo del documento"))
            else:
                hallazgos.append(HallazgoC(
                    "CM01", "ok",
                    f"programa mínimo {familia} (§89-90) completo en el "
                    f"proyecto ({len(vivos)} locales)", MEDIDO,
                    "programa mínimo del documento"))

    # CM02 relaciones del §78 (prioritarias) --------------------------------
    for familia in familias:
        pares_3 = _pares_prioritarios(specs, familia, por_tipo, relaciones)
        if pares_3:
            faltan = [f"{a}-{b}" for a, b, presente in pares_3
                      if not presente]
            if faltan:
                hallazgos.append(HallazgoC(
                    "CM02", "aviso",
                    f"relaciones prioritarias del §78 sin trazar en "
                    f"{familia}: " + ", ".join(faltan)
                    + " (el asistente las sugiere; se revisan al "
                      "regenerar)", MEDIDO, "relaciones del §78"))
            else:
                hallazgos.append(HallazgoC(
                    "CM02", "ok",
                    f"relaciones prioritarias del §78 presentes en "
                    f"{familia}", MEDIDO, "relaciones del §78"))

    # CM03 prohibiciones duras del §78 (residuos/carga/técnicos
    # contra público: nivel 0) — una sola vez, es familia-agnóstico
    if familias:
        prohibidas = _pares_prohibidos(specs, por_tipo, relaciones)
        if prohibidas:
            hallazgos.append(HallazgoC(
                "CM03", "fallo",
                "relación NO recomendada (nivel 0 del §78) presente: "
                + "; ".join(prohibidas)
                + " (residuos/carga/técnicos nunca contra público)",
                MEDIDO, "relaciones del §78 (prohibiciones)"))
        elif _hay_tipos_de_prohibidas(specs, por_tipo):
            hallazgos.append(HallazgoC(
                "CM03", "ok",
                "sin relaciones residuos/carga/técnicos contra público "
                "(§78)", MEDIDO, "relaciones del §78 (prohibiciones)"))

    indice = 4  # CM04 en adelante, renumerado dinámicamente abajo
    # CM04 porcentajes de áreas del §81 ----------------------------------------
    for familia in familias:
        fuera = _porcentajes_fuera(specs, familia, por_tipo, area_total)
        if fuera is None:
            continue
        if fuera:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "aviso",
                f"porcentajes de áreas fuera de rango en {familia} "
                "(§81): " + "; ".join(fuera), MEDIDO,
                "porcentajes del documento"))
        else:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "ok",
                f"porcentajes de áreas de {familia} dentro de los "
                "rangos del §81", MEDIDO,
                "porcentajes del documento"))
        indice += 1

    # CM05+ eficiencia de planta del §82 -----------------------------------------
    for familia in familias:
        rango = specs.rango_eficiencia(familia)
        if rango is None:
            continue
        detalle, fuera = [], False
        por_nivel: Dict[str, float] = {}
        for s in vivos:
            por_nivel.setdefault(getattr(s, "level_id", ""), []).append(s)
        for _nivel_id, grupo in por_nivel.items():
            util = sum(_area(s) for s in grupo)
            envolvente = _area_envolvente(grupo)
            if envolvente <= 1e-6:
                continue
            pct = 100.0 * util / envolvente
            detalle.append(f"{pct:.0f}%")
            if not (rango[0] - 1e-9 <= pct <= rango[1] + 1e-9):
                fuera = True
        if detalle:
            texto = (f"eficiencia de planta {familia} (§82): "
                     + ", ".join(detalle)
                     + f" (rango {rango[0]:.0f}-{rango[1]:.0f}%)")
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}",
                "aviso" if fuera else "ok",
                texto + (" fuera de rango: revisa muros y circulaciones"
                         if fuera else " dentro del rango"),
                MEDIDO, "eficiencia del documento"))
            indice += 1

    # estacionamiento del §45 --------------------------------------------------------
    if familias:
        plazas = por_tipo.get("PARKING", [])
        if not plazas:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "aviso",
                "sin plazas de estacionamiento; la razón local la fija "
                "la normativa urbana (§45/§97)", MEDIDO,
                "estacionamientos del documento"))
        else:
            estrechas = [s for s in plazas
                         if 0 < _ancho_bbox(s) + 1e-9 < PLAZA_ANCHO_MIN_M]
            accesibles = [s for s in plazas
                          if _ancho_bbox(s) + 1e-9 >=
                          PLAZA_ACCESIBLE_ANCHO_M]
            if estrechas:
                hallazgos.append(HallazgoC(
                    f"CM{indice:02d}", "fallo",
                    f"{len(estrechas)} plaza(s) por debajo de "
                    f"{PLAZA_ANCHO_MIN_M:.2f} m de ancho (§45)", MEDIDO,
                    "estacionamientos del documento"))
            elif not accesibles:
                hallazgos.append(HallazgoC(
                    f"CM{indice:02d}", "aviso",
                    "ninguna plaza accesible de "
                    f"{PLAZA_ACCESIBLE_ANCHO_M:.2f} m (§45)", MEDIDO,
                    "estacionamientos del documento"))
            else:
                hallazgos.append(HallazgoC(
                    f"CM{indice:02d}", "ok",
                    f"{len(plazas)} plaza(s) con mínimo de "
                    f"{PLAZA_ANCHO_MIN_M:.2f} m y "
                    f"{len(accesibles)} accesible(s) de "
                    f"{PLAZA_ACCESIBLE_ANCHO_M:.2f} m (§45)", MEDIDO,
                    "estacionamientos del documento"))
        indice += 1

    # evacuación del §17/§61 (IBC 2024) -----------------------------------------------
    if escaleras or len(niveles) > 1:
        if not escaleras:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "aviso",
                "más de un nivel sin escalera trazada", MEDIDO,
                "evacuación IBC 2024 (§17/§61)"))
        else:
            estrechas = []
            for esc in escaleras:
                ancho = _fl(getattr(esc, "width_m", 0.0))
                if ancho > 0 and ancho + 1e-9 < ANCHO_ESCALERA_EVAC_M:
                    estrechas.append(f"{_codigo(esc)} ({ancho:.2f} m)")
            if estrechas:
                hallazgos.append(HallazgoC(
                    f"CM{indice:02d}", "aviso",
                    "escalera(s) por debajo del mínimo IBC "
                    f"{ANCHO_ESCALERA_EVAC_M:.3f} m (§61): "
                    + ", ".join(estrechas), MEDIDO,
                    "evacuación IBC 2024 (§17/§61)"))
            else:
                hallazgos.append(HallazgoC(
                    f"CM{indice:02d}", "ok",
                    f"{len(escaleras)} escalera(s) >= "
                    f"{ANCHO_ESCALERA_EVAC_M:.3f} m (mínimo IBC general; "
                    "el ancho total va por ocupación)", MEDIDO,
                    "evacuación IBC 2024 (§17/§61)"))
        indice += 1

    # galería del §6 ---------------------------------------------------------------------
    galerias = por_tipo.get("GALLERY", [])
    if galerias:
        problema, nota_gran = [], False
        for g in galerias:
            ancho = _ancho_bbox(g)
            if ancho > 0 and ancho + 1e-9 < ANCHO_GALERIA_MIN_M:
                problema.append(f"{_codigo(g)} ({ancho:.2f} m)")
            elif ancho > 0 and ancho + 1e-9 < GALERIA_GRAN_CENTRO_M \
                    and area_total >= AREA_GRAN_CENTRO_M2:
                nota_gran = True
        if problema:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "fallo",
                "galería(s) por debajo del ancho mínimo de diseño "
                f"{ANCHO_GALERIA_MIN_M:.2f} m (§6): "
                + ", ".join(problema), MEDIDO, "galería comercial (§6)"))
        elif nota_gran:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "aviso",
                f"gran centro ({area_total:.0f} m2): la galería pide "
                f"{GALERIA_GRAN_CENTRO_M:.2f}-10.00 m (§6)", MEDIDO,
                "galería comercial (§6)"))
        else:
            hallazgos.append(HallazgoC(
                f"CM{indice:02d}", "ok",
                f"{len(galerias)} galería(s) >= "
                f"{ANCHO_GALERIA_MIN_M:.2f} m de ancho (§6)", MEDIDO,
                "galería comercial (§6)"))
        indice += 1

    # temas que el documento remite a cálculo o fabricante (§58/§101/§103)
    for pos, tema in enumerate(specs.requiere_calculo):
        hallazgos.append(HallazgoC(
            f"RC{pos + 1:02d}", "info",
            f"{tema.get('tema', '')} (§{tema.get('seccion', '')}): "
            f"{tema.get('motivo', '')}", REQUIERE_CALCULO,
            "REQUIERE_CALCULO_ESPECIALIZADO (§101)"))

    # locales (control dimensional por local, como el hospital) --------------
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
        "tipologia": tipologia,
        "hallazgos": [h.como_dict() for h in hallazgos],
        "locales": informes,
        "resumen": resumen,
        "prioridades": dict(specs.prioridades),
        "conflictos": [f"{c.get('id', '')} "
                       f"({c.get('severidad', '')}): "
                       f"{c.get('condicion', '')} -> {c.get('check', '')}"
                       for c in specs.conflictos],
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
# metadata del asistente no la trae: evito tipos genéricos (OFFICE,
# BATHROOM, RECEPTION...) que otros usos también generan
_HUELLAS_CC: Tuple[str, ...] = (
    "GALLERY", "RETAIL_LOCAL", "TIENDA_ANCLA", "ATRIUM", "LOADING_DOCK",
    "COMMERCIAL_KITCHEN", "RESTAURANT",
)
_HUELLAS_OF: Tuple[str, ...] = (
    "OPEN_OFFICE", "COWORKING", "CONFERENCE_ROOM", "TELECOM_ROOM",
    "DRESSING_ROOM", "BICYCLE_PARKING",
)


def _resumen_specs(specs: ComercialSpecs) -> Dict[str, int]:
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


def _familias_presentes(specs: ComercialSpecs, meta: Any,
                        por_tipo: Dict[str, List[Any]]) -> List[str]:
    """Familias CC/OF del proyecto: metadata del asistente primero,
    huellas características después (nunca tipos genéricos)."""
    familias: List[str] = []
    f_meta = str((meta or {}).get("familia", "") or "").upper() \
        if isinstance(meta, dict) else ""
    if f_meta and f_meta in [k.upper()
                             for k in specs.programa_minimo.keys()]:
        familias.append(f_meta)
        return familias
    if any(t in por_tipo for t in _HUELLAS_CC):
        familias.append(FAMILIA_CC)
    if any(t in por_tipo for t in _HUELLAS_OF):
        familias.append(FAMILIA_OF)
    return familias


def _pares_prioritarios(specs: ComercialSpecs, familia: str,
                        por_tipo: Dict[str, List[Any]],
                        relaciones: List[Any]) -> List[Tuple[str, str,
                                                             bool]]:
    """Pares nivel 3 del §78 de la familia: (a, b, vinculados).

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
        tipos_a = specs.tipos_de_relacion(a)
        tipos_b = specs.tipos_de_relacion(b)
        # escaleras y núcleos no son locales: el trazado los dibuja
        # siempre, así que el par no se exige como relación espacial
        if any(t in ("STAIR", "CORE") for t in tipos_a + tipos_b):
            continue
        # un tipo ausente del proyecto no puede dar la cara: el
        # programa mínimo (CM01) ya avisa de que falta
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


def _pares_prohibidos(specs: ComercialSpecs,
                      por_tipo: Dict[str, List[Any]],
                      relaciones: List[Any]) -> List[str]:
    """Pares nivel 0 del §78 realmente trazados (máximo 5 detalles)."""
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
                        etiqueta = a if a != PUBLICO and a != TECNICOS \
                            else tipo_a.lower()
                        detalles.append(
                            f"{_nombre(sa)} ({etiqueta}) con "
                            f"{_nombre(sb)} ({b.lower()})")
                        if len(detalles) >= 5:
                            return detalles
    return detalles


def _hay_tipos_de_prohibidas(specs: ComercialSpecs,
                             por_tipo: Dict[str, List[Any]]) -> bool:
    """True si en el proyecto hay tipos involucrados en prohibiciones
    del §78 (para dar el «ok» cuando no hay ninguna traza)."""
    for r in specs.relaciones:
        if str(r.get("nivel", "")) != "0":
            continue
        tipos_a = specs.tipos_de_relacion(str(r.get("a", "")))
        tipos_b = specs.tipos_de_relacion(str(r.get("b", "")))
        if any(t in por_tipo for t in tipos_a) \
                and any(t in por_tipo for t in tipos_b):
            return True
    return False


def _porcentajes_fuera(specs: ComercialSpecs, familia: str,
                       por_tipo: Dict[str, List[Any]],
                       area_total: float) -> Optional[List[str]]:
    """Bloques del §81 fuera de rango (None: nada que evaluar)."""
    if area_total <= 1e-6:
        return None
    fuera: List[str] = []
    hay_bloque = False
    for p in specs.porcentajes_area:
        if str(p.get("familia", "")) != familia:
            continue
        presentes = [str(t) for t in p.get("space_types", [])
                     if por_tipo.get(t)]
        if not presentes:
            continue
        hay_bloque = True
        area = sum(_area(s) for t in presentes for s in por_tipo[t])
        pct = 100.0 * area / area_total
        mn = float(p.get("min", 0) or 0)
        mx = float(p.get("max", 100) or 100)
        if not (mn - 1e-9 <= pct <= mx + 1e-9):
            fuera.append(f"{p.get('bloque', '')} {pct:.0f}% "
                         f"(rango {mn:.0f}-{mx:.0f}%)")
    return fuera if hay_bloque else None


# ----------------------------------------------------------------------
def texto_validacion_comercial(informe: Dict[str, Any]) -> str:
    """Informe CC/OF listo para consola o cuadro de texto (cp1252,
    sin flechas ni emojis)."""
    lineas: List[str] = []
    cabecera = "VALIDACIÓN DE CENTRO COMERCIAL / OFICINAS (documento v2.0)"
    if informe.get("edificacion"):
        cabecera += f" - {informe['edificacion']}"
    lineas.append(cabecera)
    datos = []
    if informe.get("uso"):
        datos.append(f"uso {informe['uso']}")
    if informe.get("familias"):
        datos.append("familia(s): " + ", ".join(informe["familias"]))
    if informe.get("tipologia"):
        datos.append(f"tipología {informe['tipologia']}")
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

    prioridades = informe.get("prioridades", {})
    if prioridades:
        lineas.append("")
        lineas.append("Prioridades del documento (§104):")
        for clave in sorted(prioridades.keys()):
            lineas.append(f"· {clave} {prioridades[clave]}")

    conflictos = informe.get("conflictos", [])
    if conflictos:
        lineas.append("")
        lineas.append("Conflictos del documento (§95) que detectan los "
                      "motores de clash/validación al regenerar:")
        for texto in conflictos:
            lineas.append(f"· {texto}")

    normativa = informe.get("normativa", [])
    if normativa:
        lineas.append("")
        lineas.append("Normativa seleccionable (§97): "
                      + ", ".join(str(n) for n in normativa))

    documentacion = informe.get("documentacion", [])
    if documentacion:
        lineas.append("Documentación de entrega (§100): "
                      + ", ".join(str(d) for d in documentacion))

    lineas.append("")
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


__all__ = [
    "HallazgoC", "ComercialSpecs", "cargar_specs", "vaciar_cache",
    "validar_local", "validar_proyecto", "texto_validacion_comercial",
    "etiquetas_tipologias", "tipologia_de_etiqueta", "familia_de_uso",
    "FAMILIA_CC", "FAMILIA_OF", "USO_GUI_CC", "USO_GUI_OF",
    "MEDIDO", "PENDIENTE", "REQUIERE_CALCULO",
    "ANCHO_PUERTA_EVAC_M", "ANCHO_ESCALERA_EVAC_M",
    "PLAZA_ANCHO_MIN_M", "PLAZA_ACCESIBLE_ANCHO_M",
    "ANCHO_GALERIA_MIN_M", "ALTURA_LIBRE_MIN_CC_M", "ALTURA_LIBRE_MIN_OF_M",
]
