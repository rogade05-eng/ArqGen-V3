"""Catálogo maestro de viviendas (v3.23.0).

Integra en el programa el documento «Catálogo maestro de viviendas»
(81 secciones: 30 tipologías, 25 sistemas constructivos, 20
estructurales, 30 estilos con reglas, matriz de compatibilidad
estilo-sistema, rangos de locales, relaciones espaciales,
zonificación, validaciones VIV001-030 y conflictos) como datos
versionados bajo ``resources/knowledge/vivienda_catalogo.json`` —
nunca hardcodeados.

Dos piezas operativas:

1. CONSULTAS para el asistente de edificación: tipologías con
   etiquetas de GUI, compatibilidad estilo x sistema (escala 0-3 del
   §27: nunca bloquea, solo advierte) y rangos de locales del §7 para
   el programa paramétrico.

2. VALIDACIÓN DE VIVIENDA (§54): las 30 comprobaciones VIV001-030
   contra el proyecto — cada una queda «medido» (la geometría o la
   metadata puede decidir), «pendiente» (falta el dato configurable
   del §66) o «requiere cálculo» (la marca REQUIERE_CALCULO_ESPECIALIZADO
   del §81: cimentación, cargas, puesta a tierra...). Sólo LEE el
   proyecto: no crea entidades ni necesita commit.

Uso headless:
    from domain.vivienda_specs import cargar_catalogo, validar_vivienda
    informe = validar_vivienda(ctx)
    print(texto_validacion_vivienda(informe))
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.paths import resource_path
from core.errors import DomainError

_CATALOGO_CACHE: List["ViviendaCatalogo"] = []

# ancho de puerta accesible del catálogo (§41/§59) y el del asistente
ANCHO_PUERTA_ACCESIBLE_M = 0.90
ANCHO_PUERTA_MINIMO_M = 0.80

# Blondel aceptado por el catálogo/de escaleras (2h + p)
BLONDEL_MIN_M = 0.60
BLONDEL_MAX_M = 0.64

# estilos de la GUI -> clave del catálogo (§4); el resto sale informativo
MAPEO_ESTILOS_GUI: Dict[str, str] = {
    "Contemporáneo": "contemporaneo",
    "Colonial cubano": "colonial",
    "Vernáculo tropical": "tropical",
    "Racionalista": "racionalista",
    "Art déco": "art_deco",
    "Neoclásico": "neoclasico",
    "Modernista": "moderno",
    "Minimalista": "minimalista",
    "Brutalista": "brutalista",
    "Ecléctico": "eclectico",
    "High-tech": "high_tech",
    "Orgánico": "organico",
    "Sostenible (bioclimático)": "bioclimatico",
}

# tipologías constructivas de la GUI -> clave del catálogo (§2)
MAPEO_SISTEMAS_GUI: Dict[str, str] = {
    "Mampostería de bloque + losa de vigueta": "mamposteria_confinada",
    "Hormigón armado (monolítico)": "hormigon_aporticado",
    "Vigas y columnas prefabricadas": "paneles_hormigon",
    "Madera ligera": "entramado_madera",
    "Panel prefabricado (sandwich)": "sip",
    "Losa maciza de hormigón": "hormigon_armado",
    "Estructura metálica (acero)": "acero",
    "Muros de piedra": "mamposteria",
    "Tierra (adobe o tapial)": "adobe",
    "Estructura ligera de acero galvanizado + panel": "steel_framing",
}

# códigos de local de las relaciones del §8 -> space_types del DNA
RELACION_A_SPACE: Dict[str, str] = {
    "SALA": "LIVING_ROOM", "COMEDOR": "DINING_ROOM", "COCINA": "KITCHEN",
    "DESPENSA": "STOREROOM", "LAVANDERIA": "LAUNDRY",
    "DORMITORIO_PRINCIPAL": "BEDROOM", "DORMITORIOS": "BEDROOM",
    "BAÑO": "BATHROOM", "GARAJE": "PARKING", "VESTIBULO": "ENTRANCE",
    "VESTIDOR": "STOREROOM", "TERRAZA": "ROOM", "PATIO": "PATIO",
}

# VIV020: sistema vs condiciones locales (clima y tipología del §71/§72)
SISTEMA_CLIMA_AVISOS: Tuple[Tuple[str, str, str], ...] = (
    # (clave sistema, fragmento de clima, aviso)
    ("adobe", "álido húmedo",
     "la tierra (adobe/tapial) sufre con la humedad del clima cálido "
     "húmedo: protege zócalos y aleros (§71)"),
    ("tapial", "álido húmedo",
     "el tapial necesita protección de lluvia en clima húmedo: aleros "
     "generosos y zócalo impermeable (§71)"),
    ("bahareque", "álido húmedo",
     "el bahareque exige buen alero y mantenimiento en clima húmedo "
     "(§71)"),
    ("madera", "álido húmedo",
     "la madera en clima húmedo pide especie resistente, tratamiento "
     "biológico y ventilación (§20/§71)"),
    ("acero", "río (necesita",
     "en clima frío el acero y el steel framing pierden calor: valora "
     "aislamiento térmico (§74)"),
    ("entramado_madera", "río (necesita",
     "en clima frío el entramado ligero pide aislamiento y barrera de "
     "vapor (§21/§74)"),
)

# estados de los hallazgos
MEDIDO = "medido"
PENDIENTE = "pendiente"
REQUIERE_CALCULO = "requiere calculo"


@dataclass
class HallazgoV:
    """Resultado de una comprobación VIV del catálogo."""

    codigo: str
    severidad: str          # "ok" | "aviso" | "fallo" | "info"
    mensaje: str
    estado: str = MEDIDO    # medido | pendiente | requiere calculo
    fuente: str = "catálogo de viviendas"

    def como_dict(self) -> Dict[str, Any]:
        return {"codigo": self.codigo, "severidad": self.severidad,
                "mensaje": self.mensaje, "estado": self.estado,
                "fuente": self.fuente}


@dataclass
class ViviendaCatalogo:
    """Registro del catálogo maestro de viviendas versionado."""

    version: str = ""
    fuente_doc: str = ""
    advertencia: str = ""
    principio: Dict[str, Any] = field(default_factory=dict)
    tipologias: List[Dict[str, Any]] = field(default_factory=list)
    sistemas: List[Dict[str, Any]] = field(default_factory=list)
    estructurales: List[Dict[str, Any]] = field(default_factory=list)
    estilos: List[Dict[str, Any]] = field(default_factory=list)
    compatibilidad: Dict[str, Any] = field(default_factory=dict)
    rangos: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    relaciones: List[Dict[str, Any]] = field(default_factory=list)
    zonificacion: Dict[str, Any] = field(default_factory=dict)
    niveles_acabado: Dict[str, Any] = field(default_factory=dict)
    modulacion: Dict[str, Any] = field(default_factory=dict)
    progresiva: Dict[str, Any] = field(default_factory=dict)
    comparacion_sistemas: Dict[str, Any] = field(default_factory=dict)
    energia_solar: Dict[str, Any] = field(default_factory=dict)
    validaciones: List[Dict[str, Any]] = field(default_factory=list)
    conflictos: List[Dict[str, Any]] = field(default_factory=list)
    configurables: List[str] = field(default_factory=list)
    jurisdicciones: Dict[str, Any] = field(default_factory=dict)
    tropical: List[str] = field(default_factory=list)
    huracanes: List[str] = field(default_factory=list)
    fuentes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    @staticmethod
    def load_file(path: str) -> "ViviendaCatalogo":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("format") != "ARQ_GEN_VIVIENDA_CATALOGO":
            raise DomainError(
                message="El archivo del catálogo de viviendas no tiene "
                        "el formato esperado",
                code="ARQ-VIV-001",
                context={"format": data.get("format")},
                suggested_action="Restaure resources/knowledge/"
                                 "vivienda_catalogo.json del paquete.")
        return ViviendaCatalogo(
            version=str(data.get("version", "")),
            fuente_doc=str(data.get("source", "")),
            advertencia=str(data.get("advertencia", "")),
            principio=dict(data.get("principio_seguridad", {})),
            tipologias=list(data.get("tipologias", [])),
            sistemas=list(data.get("sistemas_constructivos", [])),
            estructurales=list(data.get("sistemas_estructurales", [])),
            estilos=list(data.get("estilos", [])),
            compatibilidad=dict(data.get("compatibilidad_estilo_sistema",
                                         {})),
            rangos=dict(data.get("rangos_locales", {})),
            relaciones=list(data.get("relaciones", [])),
            zonificacion=dict(data.get("zonificacion", {})),
            niveles_acabado=dict(data.get("niveles_acabado", {})),
            modulacion=dict(data.get("modulacion", {})),
            progresiva=dict(data.get("progresiva", {})),
            comparacion_sistemas=dict(
                data.get("comparacion_sistemas", {})),
            energia_solar=dict(data.get("energia_solar", {})),
            validaciones=list(data.get("validaciones", [])),
            conflictos=list(data.get("conflictos", [])),
            configurables=list(data.get("configurables", [])),
            jurisdicciones=dict(data.get("jurisdicciones", {})),
            tropical=list(data.get("tropical", [])),
            huracanes=list(data.get("huracanes", [])),
            fuentes=list(data.get("fuentes", [])),
        )

    # ------------------------------------------------------------------
    def etiquetas_tipologias(self) -> List[str]:
        return [str(t.get("etiqueta_gui") or t.get("nombre", ""))
                for t in self.tipologias]

    def tipologia_de_etiqueta(self, etiqueta: str) \
            -> Optional[Dict[str, Any]]:
        texto = str(etiqueta or "").strip().lower()
        for t in self.tipologias:
            candidatos = (str(t.get("etiqueta_gui", "")).lower(),
                          str(t.get("nombre", "")).lower(),
                          str(t.get("clave", "")).lower())
            if texto in candidatos:
                return t
        return None

    def tipologia_por_clave(self, clave: str) -> Optional[Dict[str, Any]]:
        texto = str(clave or "").strip().lower()
        for t in self.tipologias:
            if str(t.get("clave", "")).lower() == texto:
                return t
        return None

    def estilo_por_clave(self, clave: str) -> Optional[Dict[str, Any]]:
        texto = str(clave or "").strip().lower()
        for e in self.estilos:
            if str(e.get("clave", "")).lower() == texto:
                return e
        return None

    def sistema_por_clave(self, clave: str) -> Optional[Dict[str, Any]]:
        texto = str(clave or "").strip().lower()
        for s in self.sistemas:
            if str(s.get("clave", "")).lower() == texto:
                return s
        return None

    def nivel_compatibilidad(self, estilo_clave: str,
                             sistema_clave: str) \
            -> Optional[int]:
        """Nivel 0-3 del §27 para el par, o None si no consta."""
        pares = (self.compatibilidad or {}).get("pares", {})
        valor = pares.get(f"{estilo_clave}|{sistema_clave}")
        try:
            return int(valor) if valor is not None else None
        except (TypeError, ValueError):
            return None

    def texto_compatibilidad(self, nivel: int) -> str:
        escala = (self.compatibilidad or {}).get("escala", {})
        return str(escala.get(str(nivel), escala.get(nivel, "?")))

    def rango(self, clave: str) -> Optional[Dict[str, Any]]:
        return self.rangos.get(str(clave or ""))

    def nivel_de_relacion(self, a: str, b: str) -> Optional[str]:
        """«3»/«2»/«1»/«X» del §8 para el par (en cualquier orden)."""
        for r in self.relaciones:
            if (r.get("a") == a and r.get("b") == b) or \
                    (r.get("a") == b and r.get("b") == a):
                return str(r.get("nivel", ""))
        return None

    def regla_validacion(self, codigo: str) -> Optional[Dict[str, Any]]:
        texto = str(codigo or "").strip().upper()
        for v in self.validaciones:
            if str(v.get("codigo", "")).upper() == texto:
                return v
        return None

    def resumen(self) -> Dict[str, int]:
        return {
            "tipologias": len(self.tipologias),
            "sistemas_constructivos": len(self.sistemas),
            "sistemas_estructurales": len(self.estructurales),
            "estilos": len(self.estilos),
            "pares_compatibilidad": len(
                (self.compatibilidad or {}).get("pares", {})),
            "rangos_locales": len(self.rangos),
            "relaciones": len(self.relaciones),
            "reglas_zonificacion": len(
                (self.zonificacion or {}).get("reglas", [])),
            "validaciones": len(self.validaciones),
            "conflictos": len(self.conflictos),
            "jurisdicciones": len(
                (self.jurisdicciones or {}).get("lista", [])),
        }


# ----------------------------------------------------------------------
def cargar_catalogo() -> Optional[ViviendaCatalogo]:
    """Carga (una vez) el catálogo; None si falta el recurso.

    Sin el recurso el programa sigue funcionando como siempre: el
    catálogo aconseja, no bloquea (§27).
    """
    if _CATALOGO_CACHE:
        return _CATALOGO_CACHE[0]
    try:
        path = resource_path("knowledge", "vivienda_catalogo.json")
        if not os.path.exists(path):
            return None
        catalogo = ViviendaCatalogo.load_file(path)
        _CATALOGO_CACHE.append(catalogo)
        return catalogo
    except Exception:  # noqa: BLE001 — recurso dañado: sin catálogo
        return None


def compatibilidad_gui(estilo_label: str, sistema_label: str,
                       catalogo: Optional[ViviendaCatalogo] = None) \
        -> Optional[int]:
    """Compatibilidad 0-3 entre los NOMBRES de la GUI (§27)."""
    catalogo = catalogo or cargar_catalogo()
    if catalogo is None:
        return None
    estilo = MAPEO_ESTILOS_GUI.get(str(estilo_label or ""))
    sistema = MAPEO_SISTEMAS_GUI.get(str(sistema_label or ""))
    if estilo is None or sistema is None:
        return None
    return catalogo.nivel_compatibilidad(estilo, sistema)


# ----------------------------------------------------------------------
# VALIDACIÓN DE VIVIENDA (sección 54 del catálogo)
# ----------------------------------------------------------------------

def validar_vivienda(ctx: Any) -> Dict[str, Any]:
    """Las 30 comprobaciones VIV001-030 sobre el proyecto abierto.

    El origen preferido es la edificación generada por el asistente
    (su metadata «edificacion» trae tipología, estilo, sistema,
    clima y parcela); sin ella se validan igualmente los locales,
    vanos y cubiertas que existan. Sólo lectura.
    """
    catalogo = cargar_catalogo()
    if catalogo is None:
        raise DomainError(
            message="No se encontró el catálogo maestro de viviendas",
            code="ARQ-VIV-002",
            suggested_action="Verifique resources/knowledge/"
                             "vivienda_catalogo.json.")
    from ui.building_wizard import _wizard_building
    _edificio, edif = _wizard_building(ctx)
    uso = str(edif.get("uso_social", "")) if edif else ""
    viv_meta = edif.get("vivienda") or {} if isinstance(edif, dict) else {}
    dims = edif.get("dimensiones_max_m") or {} if isinstance(edif, dict) \
        else {}
    lot_w = _fl(dims.get("ancho"))
    lot_d = _fl(dims.get("fondo"))

    espacios = _lista(ctx, "SPACE")
    niveles = _lista(ctx, "LEVEL")
    muros = _lista(ctx, "WALL")
    puertas = _lista(ctx, "DOOR")
    ventanas = _lista(ctx, "WINDOW")
    muebles = _lista(ctx, "FURNITURE")
    cubiertas = _lista(ctx, "ROOF")
    escaleras = _lista(ctx, "STAIR")
    relaciones = _lista(ctx, "SPACE_RELATIONSHIP")

    vivos = [s for s in espacios if len(getattr(s, "boundary", []) or []) >= 3]
    habitables = [s for s in vivos
                  if str(getattr(s, "space_type", "")) not in
                  _TIPOS_TECNICOS]
    area_huella_pb = _huella_pb(vivos, niveles)
    area_total = sum(_area(s) for s in vivos)
    style = str(edif.get("estilo_arquitectonico", "")) if edif else ""
    sistema = str(edif.get("tipologia_constructiva", "")) if edif else ""
    estructura = str(edif.get("sistema_estructural", "")) if edif else ""
    clima = str(edif.get("clima", "")) if edif else ""
    instalaciones = list(edif.get("instalaciones") or []) \
        if isinstance(edif, dict) else []

    h: List[HallazgoV] = []

    # VIV001 superficie construida <= permitida --------------------------
    if lot_w > 0 and lot_d > 0:
        parcela = lot_w * lot_d
        if area_huella_pb + 1e-9 <= parcela:
            h.append(HallazgoV(
                "VIV001", "ok",
                f"huella de planta baja {area_huella_pb:.1f} m2 dentro "
                f"de la parcela {parcela:.1f} m2 (el máximo urbano "
                "exacto es configurable, sección 66)"))
        else:
            h.append(HallazgoV(
                "VIV001", "fallo",
                f"huella de planta baja {area_huella_pb:.1f} m2 supera "
                f"la parcela {parcela:.1f} m2"))
    else:
        h.append(HallazgoV(
            "VIV001", "info",
            "sin parcela definida: el máximo de superficie permitido es "
            "un parámetro urbano configurable (sección 66)",
            PENDIENTE))

    # VIV002 ocupación ----------------------------------------------------
    if lot_w > 0 and lot_d > 0:
        ocupacion = area_huella_pb / max(lot_w * lot_d, 1e-9)
        if ocupacion <= 1.0:
            h.append(HallazgoV(
                "VIV002", "ok",
                f"ocupación aproximada {ocupacion * 100:.0f} % de la "
                "parcela (el porcentaje permitido lo fija la norma "
                "local, sección 66)"))
        else:
            h.append(HallazgoV(
                "VIV002", "fallo",
                f"la edificación ocupa {ocupacion * 100:.0f} % de la "
                "parcela: no cabe"))
    else:
        h.append(HallazgoV(
            "VIV002", "info",
            "ocupación pendiente: define las dimensiones de la parcela "
            "en el asistente", PENDIENTE))

    # VIV003 altura <= máxima (configurable) -------------------------------
    h.append(HallazgoV(
        "VIV003", "info",
        f"{len(niveles)} nivel(es) generados; la altura máxima urbana es "
        "configurable (sección 66)", PENDIENTE))

    # VIV004 retiros -------------------------------------------------------
    h.append(HallazgoV(
        "VIV004", "info",
        "los retiros mínimos son parámetros urbanos configurables "
        "(sección 66); el catálogo de la tipología los recuerda",
        PENDIENTE))

    # VIV005 área libre ----------------------------------------------------
    if lot_w > 0 and lot_d > 0:
        libre = lot_w * lot_d - area_huella_pb
        if libre > 1e-9:
            h.append(HallazgoV(
                "VIV005", "ok",
                f"área libre de parcela {libre:.1f} m2"))
        else:
            h.append(HallazgoV(
                "VIV005", "fallo",
                "no queda área libre en la parcela"))
    else:
        h.append(HallazgoV(
            "VIV005", "info", "sin parcela definida", PENDIENTE))

    # VIV006 estacionamientos ----------------------------------------------
    plazas = [s for s in vivos
              if str(getattr(s, "space_type", "")) == "PARKING"]
    if plazas:
        h.append(HallazgoV(
            "VIV006", "ok",
            f"{len(plazas)} plaza(s) de estacionamiento en el programa"))
    else:
        h.append(HallazgoV(
            "VIV006", "aviso",
            "ninguna plaza de estacionamiento; el mínimo requerido es "
            "configurable (sección 66)"))

    # VIV007 dormitorios con luz y ventilación ------------------------------
    dormitorios = [s for s in vivos
                   if str(getattr(s, "space_type", "")) == "BEDROOM"]
    if dormitorios:
        sin_luz = [s for s in dormitorios
                   if not _tiene_vano(ctx, s, muros,
                                      puertas + ventanas)]
        if not sin_luz:
            h.append(HallazgoV(
                "VIV007", "ok",
                f"los {len(dormitorios)} dormitorio(s) tienen vano "
                "(luz y ventilación)"))
        else:
            nombres = ", ".join(_nombre(s) for s in sin_luz)
            h.append(HallazgoV(
                "VIV007", "fallo",
                f"dormitorio(s) {nombres} sin ventana ni puerta "
                "trazadas"))
    else:
        h.append(HallazgoV(
            "VIV007", "info", "no hay dormitorios en el proyecto"))

    # VIV008 baño con ventilación -------------------------------------------
    banos = [s for s in vivos
             if str(getattr(s, "space_type", "")) in ("BATHROOM",
                                                      "LAVATORY")]
    if banos:
        sin_vent = [s for s in banos
                    if not _vanos_de_tipo_en(ctx, s, "WINDOW", muros,
                                             ventanas)]
        if not sin_vent:
            h.append(HallazgoV(
                "VIV008", "ok", "todos los baños tienen ventilación "
                "natural por ventana"))
        else:
            nombres = ", ".join(_nombre(s) for s in sin_vent)
            h.append(HallazgoV(
                "VIV008", "aviso",
                f"baño(s) {nombres} sin ventana: necesita ventilación "
                "natural o mecánica (ducto extractor)"))
    else:
        h.append(HallazgoV(
            "VIV008", "info", "no hay baños en el proyecto"))

    # VIV009 cocina con extracción -------------------------------------------
    cocinas = [s for s in vivos
               if str(getattr(s, "space_type", "")) == "KITCHEN"]
    if cocinas:
        sin_vent = [s for s in cocinas
                    if not _vanos_de_tipo_en(ctx, s, "WINDOW", muros,
                                             ventanas)]
        if not sin_vent:
            h.append(HallazgoV(
                "VIV009", "ok", "la cocina tiene ventana de extracción "
                "natural"))
        else:
            h.append(HallazgoV(
                "VIV009", "aviso",
                "cocina sin ventana: prevé extracción mecánica"))
    else:
        h.append(HallazgoV(
            "VIV009", "info", "no hay cocina en el proyecto"))

    # VIV010 escalera con geometría normativa ---------------------------------
    if len(niveles) > 1:
        if escaleras:
            malas = []
            for esc in escaleras:
                ch = _fl(getattr(esc, "contrahuella_m", 0))
                hu = _fl(getattr(esc, "huella_m", 0))
                blondel = 2 * ch + hu
                if not (BLONDEL_MIN_M - 1e-9 <= blondel
                        <= BLONDEL_MAX_M + 1e-9):
                    malas.append(f"{_codigo(esc)} (Blondel "
                                 f"{blondel:.2f} m)")
            if malas:
                h.append(HallazgoV(
                    "VIV010", "aviso",
                    "escalera(s) " + ", ".join(malas)
                    + " fuera de Blondel 2h+p = 0,60-0,64 m"))
            else:
                h.append(HallazgoV(
                    "VIV010", "ok",
                    f"{len(escaleras)} escalera(s) dentro de Blondel "
                    "(2h+p = 0,60-0,64 m)"))
        else:
            h.append(HallazgoV(
                "VIV010", "aviso",
                "más de un nivel sin escalera trazada"))
    else:
        h.append(HallazgoV(
            "VIV010", "info", "edificación de un nivel: escalera no "
            "aplica"))

    # VIV011 puertas accesibles -----------------------------------------------
    if puertas:
        anchos = [_fl(p.width_m) for p in puertas]
        estrechas = [f"{_codigo(p)} ({_fl(p.width_m):.2f} m)"
                     for p in puertas
                     if _fl(p.width_m) + 1e-9 < ANCHO_PUERTA_MINIMO_M]
        if estrechas:
            h.append(HallazgoV(
                "VIV011", "fallo",
                "puerta(s) " + ", ".join(estrechas)
                + f" por debajo de {ANCHO_PUERTA_MINIMO_M:.2f} m"))
        else:
            minima = min(anchos)
            if minima + 1e-9 < ANCHO_PUERTA_ACCESIBLE_M:
                h.append(HallazgoV(
                    "VIV011", "aviso",
                    f"el ancho mínimo de puerta es {minima:.2f} m; para "
                    "el modo accesible se pide "
                    f"{ANCHO_PUERTA_ACCESIBLE_M:.2f} m (sección 59)"))
            else:
                h.append(HallazgoV(
                    "VIV011", "ok",
                    f"todas las puertas >= "
                    f"{ANCHO_PUERTA_ACCESIBLE_M:.2f} m"))
    else:
        h.append(HallazgoV(
            "VIV011", "info", "no hay puertas trazadas"))

    # VIV012 instalación eléctrica con protección ------------------------------
    if "Eléctrica" in instalaciones:
        h.append(HallazgoV(
            "VIV012", "ok",
            "módulo eléctrico activo: el motor calcula protecciones, "
            "caída de tensión y secciones"))
    else:
        h.append(HallazgoV(
            "VIV012", "aviso",
            "módulo eléctrico no activado: la protección de los "
            "circuitos queda pendiente"))

    # VIV013 puesta a tierra ---------------------------------------------------
    h.append(HallazgoV(
        "VIV013", "info",
        "puesta a tierra: REQUIERE_CALCULO_ESPECIALIZADO (sección 81) "
        "según la norma eléctrica adoptada", REQUIERE_CALCULO))

    # VIV014 cubierta con evacuación de agua ------------------------------------
    if cubiertas:
        tipos = [str(getattr(c, "tipologia", "") or "") for c in cubiertas]
        if any(t and t != "ninguna" for t in tipos):
            h.append(HallazgoV(
                "VIV014", "ok",
                f"cubierta generada ({tipos[0]}) con pendiente de "
                "evacuación"))
        else:
            h.append(HallazgoV(
                "VIV014", "aviso",
                "la cubierta es «ninguna»: define drenaje o transitable "
                "con pendientes"))
    else:
        h.append(HallazgoV(
            "VIV014", "aviso", "sin cubierta generada todavía"))

    # VIV015 bajantes dimensionadas ----------------------------------------------
    if "Sanitaria" in instalaciones:
        h.append(HallazgoV(
            "VIV015", "ok",
            "módulo sanitario activo: el motor dimensiona la red "
            "(pluviales con Q = C·i·A)"))
    else:
        h.append(HallazgoV(
            "VIV015", "info",
            "dimensionado de bajantes pendiente: activa el módulo "
            "sanitario", PENDIENTE))

    # VIV016 estructura definida ---------------------------------------------------
    if estructura:
        h.append(HallazgoV(
            "VIV016", "ok", f"sistema estructural definido: {estructura}"))
    else:
        h.append(HallazgoV(
            "VIV016", "aviso", "sin sistema estructural declarado"))

    # VIV017 suelo antes de cimentación / VIV018 cargas ---------------------------
    h.append(HallazgoV(
        "VIV017", "info",
        "tipo de suelo y capacidad portante antes de la cimentación "
        "definitiva: REQUIERE_CALCULO_ESPECIALIZADO (secciones 23 y 81)",
        REQUIERE_CALCULO))
    h.append(HallazgoV(
        "VIV018", "info",
        "cargas estructurales definitivas: REQUIERE_CALCULO_"
        "ESPECIALIZADO (sección 81)", REQUIERE_CALCULO))

    # VIV019 compatibilidad estilo-sistema (§27) ----------------------------------
    nivel = compatibilidad_gui(style, sistema, catalogo)
    if nivel is None:
        par = f"«{style or 'sin estilo'}» + «{sistema or 'sin sistema'}»"
        h.append(HallazgoV(
            "VIV019", "info",
            f"sin dato de compatibilidad para el par {par}; la matriz "
            "del catálogo cubre los pares de su documento (sección 27)"))
    elif nivel >= 2:
        h.append(HallazgoV(
            "VIV019", "ok",
            f"estilo «{style}» + sistema «{sistema}»: "
            f"{catalogo.texto_compatibilidad(nivel)} "
            f"(nivel {nivel}/3)"))
    else:
        h.append(HallazgoV(
            "VIV019", "aviso",
            f"estilo «{style}» + sistema «{sistema}»: "
            f"{catalogo.texto_compatibilidad(nivel)} "
            f"(nivel {nivel}/3); no bloquea, márcalo como excepción "
            "si se mantiene"))

    # VIV020 sistema vs condiciones locales ---------------------------------------
    clave_sistema = MAPEO_SISTEMAS_GUI.get(sistema, "")
    aviso_clima = next((texto for _clave, fragmento, texto
                        in SISTEMA_CLIMA_AVISOS
                        if _clave == clave_sistema
                        and fragmento in clima), None)
    tipologia_clave = str(viv_meta.get("clave", "") or "")
    if aviso_clima:
        h.append(HallazgoV("VIV020", "aviso", aviso_clima))
    elif tipologia_clave == "costera" and clave_sistema in (
            "acero", "steel_framing"):
        h.append(HallazgoV(
            "VIV020", "aviso",
            "vivienda costera con estructura de acero: prevé protección "
            "anticorrosión (salitre, sección 70)"))
    else:
        h.append(HallazgoV(
            "VIV020", "ok",
            f"sistema «{sistema or 'sin dato'}» sin conflicto conocido "
            f"con el clima «{clima or 'sin dato'}»"))

    # VIV021 costo <= presupuesto ---------------------------------------------------
    h.append(HallazgoV(
        "VIV021", "info",
        "control presupuestario: el presupuesto vivo del asistente "
        "estima el coste por calidad (5 niveles del §51); la comparación "
        "con tu presupuesto es configurable", PENDIENTE))

    # VIV022/VIV023 superficies -------------------------------------------------------
    h.append(HallazgoV(
        "VIV022", "ok",
        f"superficie total sumada por el programa: {area_total:.1f} m2 "
        f"en {len(vivos)} locales"))
    area_bbox = _area_envolvente(vivos, niveles)
    if area_bbox > 0:
        if area_total <= area_bbox + 1e-6:
            h.append(HallazgoV(
                "VIV023", "ok",
                f"superficie útil {area_total:.1f} m2 <= envolvente "
                f"aproximada {area_bbox:.1f} m2"))
        else:
            h.append(HallazgoV(
                "VIV023", "aviso",
                f"la suma de locales ({area_total:.1f} m2) supera la "
                f"envolvente aproximada ({area_bbox:.1f} m2): revisa "
                "solapes"))
    else:
        h.append(HallazgoV(
            "VIV023", "info", "sin locales para comparar envolvente"))

    # VIV024 locales con categoría -----------------------------------------------------
    genericos = [s for s in vivos
                 if str(getattr(s, "space_type", "") or "ROOM") == "ROOM"]
    if genericos:
        nombres = ", ".join(_nombre(s) for s in genericos[:6])
        h.append(HallazgoV(
            "VIV024", "aviso",
            f"{len(genericos)} local(es) con categoría ROOM genérica: "
            f"{nombres}"))
    else:
        h.append(HallazgoV(
            "VIV024", "ok", "todos los locales tienen categoría del DNA"))

    # VIV025 locales con relaciones -----------------------------------------------------
    servidos, huespedes = _locales_servidos(ctx, vivos, relaciones)
    if huespedes:
        nombres = ", ".join(_nombre(s) for s in huespedes[:6])
        h.append(HallazgoV(
            "VIV025", "aviso",
            f"{len(huespedes)} local(es) sin relación ni pasillo: "
            f"{nombres}"))
    else:
        h.append(HallazgoV(
            "VIV025", "ok", "todos los locales quedan servidos "
            "(relación, puerta o pasillo)"))

    # VIV026 equipos ubicados -------------------------------------------------------------
    if muebles:
        sueltos = [m for m in muebles
                   if not str(getattr(m, "space_id", "") or "").strip()]
        if sueltos:
            h.append(HallazgoV(
                "VIV026", "aviso",
                f"{len(sueltos)} pieza(s) de mobiliario sin local "
                "asignado"))
        else:
            h.append(HallazgoV(
                "VIV026", "ok",
                f"{len(muebles)} piezas de mobiliario con ubicación"))
    else:
        h.append(HallazgoV(
            "VIV026", "info", "sin mobiliario colocado"))

    # VIV027 instalaciones con origen/destino -----------------------------------------------
    redes = _lista(ctx, "NETWORK") + _lista(ctx, "NODE")
    if redes:
        h.append(HallazgoV(
            "VIV027", "ok",
            f"redes de instalaciones trazadas ({len(redes)} elementos): "
            "el motor valida topología radial y finales muertos"))
    elif instalaciones:
        h.append(HallazgoV(
            "VIV027", "info",
            "módulos activados (" + ", ".join(instalaciones)
            + "): las redes se generan al ejecutar las instalaciones"))
    else:
        h.append(HallazgoV(
            "VIV027", "info", "sin módulos de instalaciones activados"))

    # VIV028 puertas asociadas a muro ---------------------------------------------------------
    if puertas:
        huerfanas = [p for p in puertas
                     if not str(getattr(p, "wall_id", "") or "").strip()
                     or _muro_de(ctx, muros, getattr(p, "wall_id", "")) is None]
        if huerfanas:
            h.append(HallazgoV(
                "VIV028", "fallo",
                f"{len(huerfanas)} puerta(s) sin muro que las hospede"))
        else:
            h.append(HallazgoV(
                "VIV028", "ok", "todas las puertas cuelgan de un muro"))
    else:
        h.append(HallazgoV(
            "VIV028", "info", "no hay puertas que comprobar"))

    # VIV029 ventanas asociadas a fachada ------------------------------------------------------
    if ventanas:
        interiores = 0
        for v in ventanas:
            muro = _muro_de(ctx, muros, getattr(v, "wall_id", ""))
            if muro is not None and _muro_compartido(muro, vivos):
                interiores += 1
        if interiores:
            h.append(HallazgoV(
                "VIV029", "aviso",
                f"{interiores} ventana(s) en muro entre locales: la "
                "fachada pide muro perimetral"))
        else:
            h.append(HallazgoV(
                "VIV029", "ok", "todas las ventanas están en muros "
                "perimetrales (fachada)"))
    else:
        h.append(HallazgoV(
            "VIV029", "info", "no hay ventanas que comprobar"))

    # VIV030 habitaciones sin acceso --------------------------------------------------------------
    sin_acceso = [s for s in habitables
                  if not _vanos_de_tipo_en(ctx, s, "DOOR", muros, puertas)]
    if sin_acceso:
        nombres = ", ".join(_nombre(s) for s in sin_acceso[:6])
        h.append(HallazgoV(
            "VIV030", "fallo",
            f"local(es) sin puerta de acceso: {nombres}"))
    else:
        h.append(HallazgoV(
            "VIV030", "ok", "todas las habitaciones tienen puerta"))

    resumen = {"ok": 0, "avisos": 0, "fallos": 0, "pendientes": 0}
    for hallazgo in h:
        if hallazgo.estado != MEDIDO:
            resumen["pendientes"] += 1
        elif hallazgo.severidad == "ok":
            resumen["ok"] += 1
        elif hallazgo.severidad == "aviso":
            resumen["avisos"] += 1
        elif hallazgo.severidad == "fallo":
            resumen["fallos"] += 1
        else:
            resumen["pendientes"] += 1

    sin_viv = [c for c in catalogo.conflictos if not c.get("viv")]
    return {
        "edificacion": str(edif.get("nombre", "")) if edif else "",
        "uso": uso,
        "tipologia": str(viv_meta.get("tipologia", "") or ""),
        "tipologia_clave": tipologia_clave,
        "estilo": style,
        "sistema": sistema,
        "estructura": estructura,
        "clima": clima,
        "parcela": {"ancho": lot_w, "fondo": lot_d}
        if lot_w > 0 and lot_d > 0 else None,
        "hallazgos": [x.como_dict() for x in h],
        "resumen": resumen,
        "conflictos_no_geometricos": [
            f"{c['codigo']}: {c['texto']}" for c in sin_viv],
        "principio_seguridad": catalogo.principio,
        "advertencia": catalogo.advertencia,
        "fuentes": catalogo.fuentes,
        "catalogo": catalogo.resumen(),
    }


# ----------------------------------------------------------------------
def texto_validacion_vivienda(informe: Dict[str, Any]) -> str:
    """Informe VIV001-030 listo para consola o cuadro de texto
    (cp1252, sin flechas ni emojis)."""
    lineas: List[str] = []
    cabecera = "VALIDACIÓN DE VIVIENDA (catálogo §54)"
    if informe.get("edificacion"):
        cabecera += f" - {informe['edificacion']}"
    lineas.append(cabecera)
    datos = []
    if informe.get("tipologia"):
        datos.append(f"tipología {informe['tipologia']}")
    if informe.get("estilo"):
        datos.append(f"estilo {informe['estilo']}")
    if informe.get("sistema"):
        datos.append(f"sistema {informe['sistema']}")
    if informe.get("clima"):
        datos.append(f"clima {informe['clima']}")
    if datos:
        lineas.append(", ".join(datos))
    lineas.append("")
    for x in informe.get("hallazgos", []):
        marca = {"ok": "[OK]", "fallo": "[X]", "aviso": "[!]",
                 "info": "[i]"}.get(x["severidad"], "[?]")
        estado = {"medido": "", "pendiente": " (pendiente)",
                  "requiere calculo":
                      " (REQUIERE_CALCULO_ESPECIALIZADO)"}.get(
            x.get("estado", ""), "")
        lineas.append(f"{marca} {x['codigo']}: {x['mensaje']}{estado}")
    resumen = informe.get("resumen", {})
    lineas.append("")
    lineas.append(f"Resumen: {resumen.get('ok', 0)} cumplen, "
                  f"{resumen.get('avisos', 0)} avisos, "
                  f"{resumen.get('fallos', 0)} fallos, "
                  f"{resumen.get('pendientes', 0)} pendientes o de "
                  "cálculo.")
    no_geo = informe.get("conflictos_no_geometricos", [])
    if no_geo:
        lineas.append("")
        lineas.append("Conflictos del catálogo (§65) que detectan los "
                      "motores de clash/validación al regenerar:")
        for texto in no_geo:
            lineas.append(f"· {texto}")
    lineas.append("")
    lineas.append(str(informe.get("advertencia") or ""))
    return "\n".join(lineas)


# ----------------------------------------------------------------------
# helpers de lectura (sólo lectura, tolerantes a proyectos a medio hacer)
# ----------------------------------------------------------------------

_TIPOS_TECNICOS = ("CORRIDOR", "PATIO", "STAIR", "CORE")


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
    """Nombre legible del local (con su código si lo tiene)."""
    nombre = str(getattr(entidad, "name", "") or "").strip()
    codigo = _codigo(entidad)
    return f"{nombre} ({codigo})" if nombre else codigo


def _area(espacio: Any) -> float:
    try:
        return max(float(espacio.area_m2()), 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _huella_pb(vivos: List[Any], niveles: List[Any]) -> float:
    """Suma de áreas del nivel de cota más baja (planta baja)."""
    if not niveles or not vivos:
        return sum(_area(s) for s in vivos)
    primero = min(niveles, key=lambda lv: _fl(getattr(lv, "elevation_m",
                                                      0.0)))
    return sum(_area(s) for s in vivos
               if getattr(s, "level_id", "") == getattr(primero, "id", ""))


def _area_envolvente(vivos: List[Any], niveles: List[Any]) -> float:
    """Bbox por nivel sumado: aproximación de la superficie construida."""
    total = 0.0
    por_nivel: Dict[str, List[Any]] = {}
    for s in vivos:
        por_nivel.setdefault(getattr(s, "level_id", ""), []).append(s)
    for grupo in por_nivel.values():
        xs, ys = [], []
        for s in grupo:
            for p in s.boundary:
                xs.append(p[0])
                ys.append(p[1])
        if xs:
            total += (max(xs) - min(xs)) * (max(ys) - min(ys))
    return total


def _muro_de(ctx: Any, muros: List[Any], wall_id: str) -> Optional[Any]:
    for muro in muros:
        if str(getattr(muro, "id", "")) == str(wall_id or ""):
            return muro
    return None


def _punto_medio_vano(vano: Any, muro: Any) -> Optional[Tuple[float,
                                                              float]]:
    try:
        sx, sy = muro.start
        ex, ey = muro.end
    except Exception:  # noqa: BLE001
        return None
    largo = ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
    if largo <= 1e-9:
        return None
    t = (_fl(vano.offset_m) + _fl(vano.width_m) / 2.0) / largo
    return (sx + (ex - sx) * t, sy + (ey - sy) * t)


def _dist_punto_segmento(p: Tuple[float, float],
                         a: Tuple[float, float],
                         b: Tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    largo2 = dx * dx + dy * dy
    if largo2 <= 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / largo2))
    cx, cy = ax + dx * t, ay + dy * t
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _punto_en_borde(p: Tuple[float, float], boundary: List[Tuple[float,
                                                                  float]],
                    eps: float = 1e-6) -> bool:
    n = len(boundary)
    for i in range(n):
        if _dist_punto_segmento(p, boundary[i],
                                boundary[(i + 1) % n]) <= eps:
            return True
    return False


def _vanos_de_tipo_en(ctx: Any, espacio: Any, kind: str, muros: List[Any],
                      vanos: List[Any]) -> List[Any]:
    """Vanos del tipo pedido cuyo punto medio cae en el borde del local."""
    boundary = [tuple(p) for p in getattr(espacio, "boundary", []) or []]
    if not boundary:
        return []
    por_id = {str(getattr(m, "id", "")): m for m in muros}
    resultado = []
    for vano in vanos:
        if str(getattr(vano, "kind", "")) != kind:
            continue
        muro = por_id.get(str(getattr(vano, "wall_id", "")))
        if muro is None:
            continue
        punto = _punto_medio_vano(vano, muro)
        if punto is not None and _punto_en_borde(punto, boundary):
            resultado.append(vano)
    return resultado


def _tiene_vano(ctx: Any, espacio: Any, muros: List[Any],
                vanos: List[Any]) -> bool:
    return bool(_vanos_de_tipo_en(ctx, espacio, "WINDOW", muros, vanos)
                or _vanos_de_tipo_en(ctx, espacio, "DOOR", muros, vanos))


def _muro_compartido(muro: Any, vivos: List[Any]) -> bool:
    """True si los dos extremos del muro tocan >= 2 locales (interior)."""
    try:
        extremos = [tuple(muro.start), tuple(muro.end)]
    except Exception:  # noqa: BLE001
        return False
    tocan = 0
    for s in vivos:
        boundary = [tuple(p) for p in getattr(s, "boundary", []) or []]
        if boundary and all(_punto_en_borde(e, boundary, 1e-6)
                            for e in extremos):
            tocan += 1
    return tocan >= 2


def _locales_servidos(ctx: Any, vivos: List[Any], relaciones: List[Any]) \
        -> Tuple[List[Any], List[Any]]:
    """(servidos, huéspedes): un local está servido si participa en una
    relación, tiene puerta o toca un pasillo/patio/escalera/núcleo."""
    tecnicos = [s for s in vivos
                if str(getattr(s, "space_type", "")) in _TIPOS_TECNICOS]
    ids_con_relacion = set()
    for rel in relaciones:
        ids_con_relacion.add(str(getattr(rel, "from_space_id", "")))
        ids_con_relacion.add(str(getattr(rel, "to_space_id", "")))
    con_puerta: Dict[str, bool] = {}
    muros = _lista(ctx, "WALL")
    puertas = _lista(ctx, "DOOR")
    servidos, huespedes = [], []
    for s in vivos:
        if s in tecnicos:
            continue
        sid = str(getattr(s, "id", ""))
        if sid in ids_con_relacion:
            servidos.append(s)
            continue
        if con_puerta.get(sid) is None:
            con_puerta[sid] = bool(_vanos_de_tipo_en(ctx, s, "DOOR",
                                                     muros, puertas))
        if con_puerta[sid]:
            servidos.append(s)
            continue
        boundary = [tuple(p) for p in getattr(s, "boundary", []) or []]
        tocado = False
        for tecnico in tecnicos:
            otro = [tuple(p) for p in getattr(tecnico, "boundary", [])
                    or []]
            if otro and boundary and any(_punto_en_borde(p, otro, 1e-6)
                                         for p in boundary):
                tocado = True
                break
        (servidos if tocado else huespedes).append(s)
    return servidos, huespedes


__all__ = [
    "HallazgoV", "ViviendaCatalogo", "cargar_catalogo", "validar_vivienda",
    "texto_validacion_vivienda", "compatibilidad_gui", "RELACION_A_SPACE",
    "MAPEO_ESTILOS_GUI", "MAPEO_SISTEMAS_GUI", "ANCHO_PUERTA_ACCESIBLE_M",
    "ANCHO_PUERTA_MINIMO_M", "MEDIDO", "PENDIENTE", "REQUIERE_CALCULO",
]  # nivel_compatibilidad expuesto vía instancia
