"""Asistente de EDIFICACIÓN completa (v1.8.0): arma tu edificio paso a paso.

El usuario pidió «generar una edificación completa, definiendo locales,
dimensiones, relaciones espaciales entre ellos y los distintos
requerimientos climáticos, arquitectónicos, estructurales, etc.».
Este módulo concentra TODA la lógica (headless, sin Tk) para que sea
verificable con unittest, siguiendo el patrón de ui.wizard:

- BUILDING_STEPS     — los 5 pasos y su texto orientador.
- LevelSpec/RoomSpec/RelationSpec/BuildingWizardData — los datos.
- validate_step()    — validación amable paso a paso (erroreS en español).
- build_layout()     — motor de trazado determinista: locales en fila
  pegados por sus particiones, pasillo opcional detrás de la fachada,
  muros FUSIONADOS (una pared compartida = UN muro), puertas
  (declaradas + automáticas al pasillo + entrada) y ventanas en
  fachada exterior.
- build_plan()       — plan declarativo de creación (edificio, niveles,
  locales, muros, vanos y relaciones) inspeccionable antes de ejecutar.
- apply_plan()       — ejecuta el plan por las mismas fachadas que la
  CLI (CommandBus §76, auditoría §71 y eventos §75), en una sola
  transacción, y deja los REQUERIMIENTOS (climáticos, arquitectónicos,
  estructurales) en el metadata de cada entidad.
- step_summary()     — resumen legible para el paso de revisión.
- dna_advisories()   — avisos del conocimiento Space DNA (áreas
  mínimas, ventilación, zonas húmedas) sin bloquear.
- PROGRAM_PRESETS / suggest_relations() — programas tipo y relaciones
  sugeridas desde el DNA.
- USAGE_TYPES / INSTALLATION_MODULES / CONSTRUCTION_TYPES — usos
  sociales con su programa de locales sugerido, módulos de
  instalaciones y tipologías constructivas (v2.1.0).
- TEMA HOSPITALARIO (v2.2.0): usos «Policlínico» y «Hospital» con
  su DNA técnico (quirófano, urgencias, esterilización,
  hospitalización, laboratorio, imagenología, farmacia, enfermería),
  PROGRAMA MULTI-NIVEL (LEVEL_PROGRAMS: PB urgencias/imagenología,
  P1 quirófanos, P2 hospitalización — crea los niveles que falten),
  USAGE_DOOR_PAIRS (puertas críticas: quirófano–esterilización,
  urgencias–rayos X, sala–enfermería) y suggested_installations()
  (A/C y gas medicinal sugeridos para la red hospitalaria).
- PlantVariant / generate_variants() — motor de VARIANTES de planta:
  nueve esquemas tipológicos (lineal, doble crujía, patio central, en
  L, en T, en U, en H, en cruz y articulada en eslabones) por cada
  orden (normal y espejo), con métricas explicadas (adyacencias,
  luz, compacidad, ventilación, clima, forma elegida, lote) y
  puntuación 0–100.
- FORMAS, ESTILOS, TERRENO y ESCALERAS (v2.3.0): PLAN_SHAPES con
  sugerencias por uso social, ARCHITECTURAL_STYLES con consejos,
  TERRAIN_TYPES que fuerzan DIFERENTES NIVELES DE PISO en una misma
  planta (cota por local) y colocación AUTOMÁTICA de escaleras
  (STAIR) entre niveles o para salvar el desnivel.
- PATIOS EN LAS ALAS, ALEROS y MÁS RELACIONES (v2.4.0): las alas
  largas de la L/T/U/cruz ganan un patio interior con puertas de
  galería (_stack_with_wing_patio); el contorno de los aleros se
  calcula con eaves_outline_segments (core.geometry) para dibujarse
  en la vista previa y en el SVG; ARCHITECTURAL_STYLES llega a
  catorce con sugerencia por uso (suggested_architectural_style),
  preferencia estilo↔forma (STYLE_SHAPE_PREFERENCE) y relaciones
  ampliadas por uso (USAGE_DOOR_PAIRS + USAGE_EXTRA_PAIRS).
- NORMATIVA NEUFERT (v2.7.0): todas las reglas dimensionales se
  apoyan en «El arte de proyectar en arquitectura» (Ernst Neufert)
  vía resources/knowledge/neufert_standards.json y domain/neufert.py:
  escalera por uso con la fórmula de BLONDEL (2h + p = 0,60–0,64 m),
  pasillos y puertas por uso social (1,20 m donde pasa camilla),
  espesor de muro por tipología, luz de las ventanas (1/8 del suelo),
  alturas libres, rampa máxima del 8 %, estacionamiento y avisos
  normativos no bloqueantes (neufert_advisories) en resumen y
  generación; metadata «normativa» en el edificio y «normativa_neufert»
  en cada local.

La ventana (ui.app_window.open_building_wizard) solo dibuja
formularios y llama a estas funciones.
"""

from __future__ import annotations

import math
import random
from copy import copy as _shallow_copy
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# Reutiliza el parseo con coma decimal del asistente de local.
from ui.wizard import parse_float_es  # noqa: F401  (re-export implícito)


def _neufert_registry() -> Any:
    """Registro normativo Neufert (v2.7.0); None sin catálogo.

    La norma ACONSEJA, nunca bloquea: sin el catálogo cargado, el
    asistente usa las reglas clásicas de siempre.
    """
    try:
        from domain.neufert import get_registry
        return get_registry()
    except Exception:  # noqa: BLE001 — sin norma, reglas clásicas
        return None


def _neufert_fuente() -> str:
    """Texto de citación del libro para metadata y avisos."""
    registry = _neufert_registry()
    if registry is not None:
        return registry.fuente()
    try:
        from domain.neufert import FUENTE_TEXTO
        return FUENTE_TEXTO
    except Exception:  # noqa: BLE001
        return "Neufert"

# -- Catálogos legibles (la interfaz nunca muestra claves crudas) ----------

CLIMATE_ZONES: Tuple[str, ...] = (
    "Cálido húmedo (tropical lluvioso)",
    "Tropical seco (poca lluvia)",
    "Templado",
    "Frío (necesita calefacción)",
    "Alta montaña",
)

STRUCTURAL_SYSTEMS: Tuple[str, ...] = (
    "Muros portantes",
    "Pórtico de hormigón",
    "Mixto (pórtico + muros)",
)

# Tipología constructiva: cómo se construyen los cerramientos
# (v2.1.0 con cinco; v2.3.0 amplía a diez sistemas reales).
CONSTRUCTION_TYPES: Tuple[str, ...] = (
    "Mampostería de bloque + losa de vigueta",
    "Hormigón armado (monolítico)",
    "Vigas y columnas prefabricadas",
    "Madera ligera",
    "Panel prefabricado (sandwich)",
    "Losa maciza de hormigón",
    "Estructura metálica (acero)",
    "Muros de piedra",
    "Tierra (adobe o tapial)",
    "Estructura ligera de acero galvanizado + panel",
)

# Estilos arquitectónicos (v2.3.0 con diez; v2.4.0 amplía a catorce):
# guían aleros, vanos y forma, y se SUGIEREN según el uso social.
ARCHITECTURAL_STYLES: Tuple[str, ...] = (
    "Contemporáneo",
    "Colonial cubano",
    "Vernáculo tropical",
    "Racionalista",
    "Art déco",
    "Neoclásico",
    "Modernista",
    "Minimalista",
    "Brutalista",
    "Ecléctico",
    "High-tech",
    "Orgánico",
    "Posmoderno",
    "Sostenible (bioclimático)",
)

STYLE_DESCRIPTIONS: Dict[str, str] = {
    "Contemporáneo": "volúmenes simples, grandes vanos y acabados "
                     "actuales; funciona con cualquier forma en planta.",
    "Colonial cubano": "portada con arcos, patio central y galerías "
                       "profundas: pide forma «Patio central» y aleros "
                       "generosos.",
    "Vernáculo tropical": "porche, techos altos y celosías: pide aleros "
                          "anchos y ventilación cruzada.",
    "Racionalista": "volúmenes puros, fachadas libres y ventanas "
                    "corridas: encaja con barras rectangulares y dobles "
                    "crujías.",
    "Art déco": "portadas en gradas y remates verticales: luce en "
                "fachadas simétricas y compactas.",
    "Neoclásico": "simetría, columnas y friso: pide forma rectangular "
                  "o en U con vestíbulo central.",
    "Modernista": "cubierta inclinada y aleros marcados: encaja con "
                  "formas lineales y en L.",
    "Minimalista": "planos limpios y luz cenital: pide pocos materiales "
                   "y esmero en los vanos.",
    "Brutalista": "hormigón visto y volúmenes escalonados: encaja con "
                  "formas articuladas.",
    "Ecléctico": "mezcla decorativa de épocas: unifica con color y "
                 "carpintería para no sobrecargar.",
    "High-tech": "estructura vista y tecnología a la vista: encaja con "
                 "formas en H o articuladas donde el servicio se ve "
                 "claro.",
    "Orgánico": "formas suaves y relación con el paisaje: pide patios y "
                "alas que abrazen el verde.",
    "Posmoderno": "juego de formas y guiños clásicos: luce en patios y "
                  "portadas centradas.",
    "Sostenible (bioclimático)": "diseña con el sol y el viento: pide "
                                 "aleros generosos, ventilación cruzada y "
                                 "orientación cuidada.",
}

# Forma en planta que favorece cada estilo (v2.4.0): solo para avisar
# con amabilidad; ninguna combinación queda bloqueada.
STYLE_SHAPE_PREFERENCE: Dict[str, Tuple[str, ...]] = {
    "Colonial cubano": ("Patio central", "En U", "En L"),
    "Vernáculo tropical": ("Rectangular", "Lineal (barra)", "En L"),
    "Racionalista": ("Rectangular", "Cuadrada", "Lineal (barra)"),
    "Art déco": ("Rectangular", "Cuadrada", "En L"),
    "Neoclásico": ("Rectangular", "En U", "Cuadrada"),
    "Modernista": ("Lineal (barra)", "En L", "Rectangular"),
    "Minimalista": ("Cuadrada", "Rectangular", "Lineal (barra)"),
    "Brutalista": ("Articulada (eslabones)", "En H", "En cruz"),
    "High-tech": ("En H", "Articulada (eslabones)", "En T"),
    "Orgánico": ("Patio central", "En L", "En U"),
    "Posmoderno": ("Patio central", "Cuadrada", "En U"),
    "Sostenible (bioclimático)": ("Patio central", "Rectangular", "En L"),
}

# Estilo arquitectónico sugerido por uso social (v2.4.0), en orden de
# preferencia (como las formas en planta).
USAGE_STYLE_SUGGESTIONS: Dict[str, Tuple[str, ...]] = {
    "Vivienda": ("Vernáculo tropical", "Contemporáneo", "Minimalista"),
    "Oficina": ("Racionalista", "High-tech", "Minimalista"),
    "Escuela primaria": ("Racionalista", "Sostenible (bioclimático)",
                         "Contemporáneo"),
    "Círculo infantil": ("Orgánico", "Vernáculo tropical",
                         "Contemporáneo"),
    "Consultorio médico": ("Racionalista", "Minimalista",
                           "Contemporáneo"),
    "Policlínico": ("Racionalista", "High-tech", "Contemporáneo"),
    "Hospital": ("High-tech", "Racionalista", "Sostenible (bioclimático)"),
    "Comedor social": ("Vernáculo tropical", "Contemporáneo",
                       "Racionalista"),
    "Centro comunitario": ("Posmoderno", "Orgánico", "Ecléctico"),
    "Albergue": ("Vernáculo tropical", "Sostenible (bioclimático)",
                 "Contemporáneo"),
    "Local comercial": ("Art déco", "Contemporáneo", "Posmoderno"),
}


# -- Catálogo maestro de viviendas (v3.23.0) -------------------------------------
# El catálogo vive en resources/knowledge/vivienda_catalogo.json (§1-§81):
# tipologías VIV-01..30, sistemas constructivos, estilos, compatibilidad
# estilo x sistema (0-3, §27: advierte, nunca bloquea), rangos de locales
# (§7) y relaciones (§8). Sin el recurso, la Vivienda usa su programa
# clásico de siempre.

VIVIENDA_TIPOLOGIA_CLASICA = "Programa clásico (6 locales)"

# locales extra por tipología del catálogo (nombre, rango §7, DNA, ventana)
VIVIENDA_EXTRAS: Dict[str, Tuple[Tuple[str, str, str, bool], ...]] = {
    "aislada": (("Garaje", "GARAJE", "PARKING", False),),
    "costera": (("Garaje", "GARAJE", "PARKING", False),),
    "premium": (("Estudio", "ESTUDIO", "OFFICE", True),
                ("Vestidor", "VESTIDOR", "STOREROOM", False)),
    "lujo": (("Estudio", "ESTUDIO", "OFFICE", True),
             ("Vestidor", "VESTIDOR", "STOREROOM", False)),
    "multigeneracional": (("Suite abuelos", "DORMITORIO_SECUNDARIO",
                           "BEDROOM", True),
                          ("Baño suite abuelos", "BANOS", "BATHROOM",
                           True)),
    "adulto_mayor": (("Suite accesible", "DORMITORIO_SECUNDARIO",
                      "BEDROOM", True),
                     ("Baño accesible", "BANOS", "BATHROOM", True)),
    "accesible": (("Baño accesible", "BANOS", "BATHROOM", True),),
    "progresiva": (("Cuarto técnico", "CUARTO_TECNICO",
                    "ELECTRICAL_ROOM", False),),
}

# tipologías que parten el programa: planta social + planta privada (§14)
VIVIENDA_DOS_NIVELES: Tuple[str, ...] = ("duplex", "triplex")

# Documento comercial CC/OF (v3.25.0): usos sociales del asistente
# (paso 1) y «sin tipología» del combo. El programa mínimo sale del
# documento (§89-90) vía domain/comercial_specs; la tipología CC/OF
# del §1 queda como metadata y como aviso de diseño.
USO_COMERCIAL_CC = "Centro comercial"
USO_COMERCIAL_OF = "Oficinas (torre/corporativo)"
USOS_COMERCIALES: Tuple[str, ...] = (USO_COMERCIAL_CC, USO_COMERCIAL_OF)

# -- DOCUMENTO EDUCACIONAL (v3.26.0): escuelas y círculos infantiles --
# Los cuatro usos del documento (primaria, secundaria, círculo infantil
# y albergue escolar) ganan un programa paramétrico por tamaño/
# capacidad (§4/§9/§48) con los programas mínimos del §106-109. El
# valor «(programa básico)» conserva los programas estáticos de
# siempre para no romper flujos existentes.
EDU_SIN_TAMANO = "(programa básico)"
USOS_EDUCATIVOS: Tuple[str, ...] = ("Escuela primaria",
                                    "Escuela secundaria",
                                    "Círculo infantil", "Albergue")
SIN_VENTANA_EDUCACION: frozenset = frozenset((
    "ENTRANCE", "BATHROOM", "CLEANING_ROOM", "WASTE_ROOM",
    "ELECTRICAL_ROOM", "PUMP_ROOM", "SERVER_ROOM", "SECURITY_ROOM",
    "STOREROOM", "LAUNDRY", "HIGIENE_CI", "PATIO", "JUEGO_EXTERIOR",
    "DRESSING_ROOM", "ISOLATION_ROOM",
))
COMERCIAL_SIN_TIPOLOGIA = "(sin tipología concreta)"

# Locales técnico/logísticos del programa CC/OF que NO llevan ventana
SIN_VENTANA_COMERCIAL: Tuple[str, ...] = (
    "WAREHOUSE", "LOADING_DOCK", "WASTE_ROOM", "ELECTRICAL_ROOM",
    "TELECOM_ROOM", "SERVER_ROOM", "CLEANING_ROOM", "DRESSING_ROOM",
    "PARKING", "HVAC_ROOM", "PUMP_ROOM", "STOREROOM",
    "COMMERCIAL_KITCHEN", "SECURITY_ROOM",
)

# Ítems del programa de OFICINAS (§90) que suben a la planta tipo en
# las tipologías verticales (torre / corporativo / uso mixto)
ITEMS_PLANTA_TIPO_OF: Tuple[str, ...] = (
    "OFICINAS", "PLANTA_ABIERTA", "DESPACHOS", "SALAS_REUNIONES",
    "SALA_CONFERENCIAS",
)
TIPOLOGIAS_VERTICALES_OF: Tuple[str, ...] = ("OF-03", "OF-04", "OF-10")


def _vivienda_catalogo() -> Any:
    """El catálogo de viviendas cargado (o None si falta el recurso)."""
    try:
        from domain.vivienda_specs import cargar_catalogo
        return cargar_catalogo()
    except Exception:  # noqa: BLE001 — sin recurso: programa clásico
        return None


def vivienda_tipologia_choices() -> List[str]:
    """Etiquetas del combo de tipología (clásica + catálogo §1)."""
    catalogo = _vivienda_catalogo()
    if catalogo is None:
        return [VIVIENDA_TIPOLOGIA_CLASICA]
    return [VIVIENDA_TIPOLOGIA_CLASICA] + catalogo.etiquetas_tipologias()


def _comercial_specs() -> Any:
    """El documento comercial CC/OF cargado (o None si falta)."""
    try:
        from domain.comercial_specs import cargar_specs
        return cargar_specs()
    except Exception:  # noqa: BLE001 — sin recurso: sin programa CC/OF
        return None


def comercial_tipologia_choices() -> List[str]:
    """Etiquetas del combo de tipología CC/OF (§1 del documento)."""
    specs = _comercial_specs()
    if specs is None:
        return [COMERCIAL_SIN_TIPOLOGIA]
    return [COMERCIAL_SIN_TIPOLOGIA] + specs.etiquetas_tipologias()


def _educacion_specs() -> Any:
    """El documento educacional cargado (o None si falta)."""
    try:
        from domain.educacion_specs import cargar_specs
        return cargar_specs()
    except Exception:  # noqa: BLE001 — sin recurso: sin programa ED
        return None


def educacion_tamano_choices() -> List[str]:
    """Etiquetas del combo de tamaño/capacidad del documento ED.

    Cada tamaño lleva el prefijo de su uso (los rangos de primaria y
    secundaria coinciden, así que el prefijo evita ambigüedades).
    """
    try:
        from domain.educacion_specs import (
            USOS_EDUCATIVOS as USOS, tamanos_parametricos)
        return [EDU_SIN_TAMANO] + [
            f"{uso}: {etq}" for uso in USOS
            for etq in tamanos_parametricos(uso)]
    except Exception:  # noqa: BLE001 — sin dominio: solo el básico
        return [EDU_SIN_TAMANO]


def _resuelve_tamano(uso_gui: str, seleccion: str) -> Optional[Any]:
    """Datos del tamaño elegido para el uso actual (o None).

    Acepta la etiqueta pura («Media (181-450 alumnos)») o la del combo
    con prefijo («Escuela primaria: Media (181-450 alumnos)») y sólo
    vale si pertenece al uso elegido.
    """
    texto = str(seleccion or "").strip()
    if not texto or texto == EDU_SIN_TAMANO:
        return None
    if ": " in texto:
        prefijo, resto = texto.split(": ", 1)
        if prefijo in USOS_EDUCATIVOS:
            texto = resto
    try:
        from domain.educacion_specs import tamano_de_etiqueta
        return tamano_de_etiqueta(uso_gui, texto)
    except Exception:  # noqa: BLE001 — sin dominio: sin tamaño
        return None


def suggested_architectural_style(usage_type: str) -> str:
    """Estilo arquitectónico recomendado para el uso social elegido."""
    return USAGE_STYLE_SUGGESTIONS.get(
        usage_type, (ARCHITECTURAL_STYLES[0],))[0]

# Formas de la edificación EN PLANTA (v2.3.0): el combo del paso 1
# orienta el motor de variantes (métrica «Forma elegida»). Cada forma
# con esquemas afines y sugerencia según el uso social.
PLAN_SHAPES: Tuple[str, ...] = (
    "Rectangular",
    "Cuadrada",
    "Lineal (barra)",
    "En L",
    "En T",
    "En U",
    "En H",
    "En cruz",
    "Patio central",
    "Articulada (eslabones)",
)

# -- Distribución interior (v3.2.0 — diseño orgánico) -------------------------
# Cómo se articulan los locales y sus muros:
#   ortogonal  — el trazado clásico: crujías rectas y esquinas vivas.
#   articulada — fondos escalonados por local (la fachada trasera
#                «respira»), chaflanes a 45° en las esquinas de la
#                envolvente y pasillo con cura suave.
#   organica   — todo lo anterior, con esquinas REDONDEADAS (radón),
#                fachada en arco y pasillo en curva serpenteante.
DISTRIBUCION_CODES: Tuple[str, ...] = ("ortogonal", "articulada", "organica")

DISTRIBUTION_LABELS: Dict[str, str] = {
    "ortogonal": "Ortogonal (clásica)",
    "articulada": "Articulada (fondos escalonados y chaflanes)",
    "organica": "Orgánica (curvas, radones y pasillo serpenteante)",
}

DISTRIBUTION_DESCRIPTIONS: Dict[str, str] = {
    "ortogonal": "Crujías rectas, esquinas vivas y pasillo alineado: "
                 "el trazado económico y predecible de siempre.",
    "articulada": "Los fondos de los locales se escalonan (la fachada "
                  "trasera juega), las esquinas de la envolvente llevan "
                  "chaflán a 45° y el pasillo toma una curva suave.",
    "organica": "Esquinas redondeadas con radón, fachada en arco, "
                "fondos escalonados y pasillo serpenteante: la planta "
                "gana movimiento sin perder superficie útil.",
}


def distribution_label(code: str) -> str:
    """Etiqueta amable de un código de distribución."""
    return DISTRIBUTION_LABELS.get(code, DISTRIBUTION_LABELS["ortogonal"])


def distribution_code(label: str) -> str:
    """Código de distribución desde su etiqueta (tolerante)."""
    for code, name in DISTRIBUTION_LABELS.items():
        if label == name or label == code:
            return code
    return "ortogonal"

SHAPE_DESCRIPTIONS: Dict[str, str] = {
    "Rectangular": "una sola manzana compacta, la más económica de "
                   "construir y mantener.",
    "Cuadrada": "proporción equilibrada: máxima compacidad y dos frentes "
                "de fachada.",
    "Lineal (barra)": "todos los locales en fila: ideal para parcelas "
                      "largas y estrechas.",
    "En L": "dos alas en ángulo que abrazan un patio lateral y dejan "
            "zona libre en el lote.",
    "En T": "cuerpo frontal con espina central: separa con claridad lo "
            "público de lo de servicio.",
    "En U": "dos alas y un patio trasero entre ellas: abraza el sol y "
            "el recreo.",
    "En H": "dos barras unidas por un puente central: mucha fachada y "
            "ventilación cruzada.",
    "En cruz": "brazos que se cruzan en el núcleo de circulación: "
               "clásico de hospitales y escuelas.",
    "Patio central": "locales alrededor de un patio que ilumina y "
                     "ventila todo el edificio.",
    "Articulada (eslabones)": "bloques unidos por eslabones: crece por "
                              "etapas y se adapta al terreno.",
}

# Forma sugerida por uso social (orden de preferencia).
USAGE_SHAPE_SUGGESTIONS: Dict[str, Tuple[str, ...]] = {
    "Vivienda": ("Rectangular", "En L", "Patio central",
                 "Articulada (eslabones)"),
    "Oficina": ("Rectangular", "Lineal (barra)", "En H", "Cuadrada"),
    "Escuela primaria": ("Articulada (eslabones)", "En L", "En cruz",
                         "En T"),
    "Círculo infantil": ("En L", "En U", "Rectangular"),
    "Consultorio médico": ("Rectangular", "Lineal (barra)", "En T"),
    "Policlínico": ("En H", "En T", "Rectangular"),
    "Hospital": ("En H", "En cruz", "En T", "Cuadrada"),
    "Comedor social": ("Rectangular", "En T", "En L"),
    "Centro comunitario": ("Patio central", "En U", "En L"),
    "Albergue": ("Rectangular", "En L", "Patio central"),
    "Local comercial": ("Rectangular", "Cuadrada", "Lineal (barra)"),
}


def suggested_plan_shape(usage_type: str) -> str:
    """Forma en planta recomendada para el uso social elegido."""
    return USAGE_SHAPE_SUGGESTIONS.get(usage_type, (PLAN_SHAPES[0],))[0]

# Módulos de instalaciones seleccionables en el paso bioclimático.
INSTALLATION_MODULES: Tuple[str, ...] = (
    "Eléctrica",
    "Sanitaria",
    "Ventilación mecánica / A/C",
    "Protección contra incendios",
    "Comunicaciones (voz y datos)",
    "Gas",
    "Energía solar",
)

# Orientación de la fachada principal: los ocho puntos cardinales
# (v2.3.0 pasa de cuatro a ocho para afinar la captación solar).
ORIENTATIONS: Tuple[str, ...] = (
    "Sur", "Norte", "Este", "Oeste",
    "Noreste", "Sureste", "Suroeste", "Noroeste",
)

# Terreno (v2.3.0): la pendiente OBLIGA a resolver diferentes niveles
# de piso dentro de una misma planta (split-level) y pide escalera.
TERRAIN_TYPES: Tuple[str, ...] = (
    "Regular (plano)",
    "Irregular con ligera pendiente",
    "Irregular con pendiente fuerte",
)

TERRAIN_DESCRIPTIONS: Dict[str, str] = {
    "Regular (plano)": "toda la planta a una sola cota: lo más simple "
                       "de construir.",
    "Irregular con ligera pendiente": "la parte trasera de la planta "
                                      "sube 0,75 m: umbrales con uno o "
                                      "dos escalones.",
    "Irregular con pendiente fuerte": "la parte trasera sube 1,50 m: "
                                      "verdadero nivel partido con "
                                      "escalera interior.",
}

TERRAIN_RISE_M: Dict[str, float] = {
    "Regular (plano)": 0.0,
    "Irregular con ligera pendiente": 0.75,
    "Irregular con pendiente fuerte": 1.5,
}


def terrain_rise_m(terrain_type: str) -> float:
    """Desnivel (m) que el terreno impone dentro de cada planta."""
    return TERRAIN_RISE_M.get(terrain_type, 0.0)


# Escaleras (v2.3.0): se colocan solas entre niveles y para salvar el
# desnivel del terreno; el usuario puede forzarlas o vetarlas.
STAIR_TYPE = "STAIR"

STAIR_MODES: Tuple[str, ...] = (
    "Automática (según niveles y terreno)",
    "Sí, incluir siempre",
    "No incluir",
)
STAIR_AUTO, STAIR_ALWAYS, STAIR_NEVER = STAIR_MODES

# Geometría de la escalera (v2.7.0 NORMATIVA NEUFERT): la fórmula de
# BLONDEL manda — 2 × contrahuella + huella = 0,60–0,64 m — y el ancho
# lo fija el uso social (camillas en salud: 1,80 m). Los valores
# clásicos (17,5 × 28 cm, caja de 1,40 m) quedan como base doméstica.
STAIR_RISER_M = 0.175
STAIR_TREAD_M = 0.28
STAIR_WIDTH_M = 1.4


def stair_geometry_for(usage: str = "") -> Tuple[float, float]:
    """(contrahuella, huella) del uso según Neufert (m).

    Vivienda: 17,5 × 28 cm (≈32°, Blondel 0,63); salud y escuelas:
    16 × 30 cm (pública con camillas, Blondel 0,62); resto: 17 × 29.
    """
    registry = _neufert_registry()
    if registry is not None:
        rule = registry.stair_rule(usage)
        return rule.contrahuella_m, rule.huella_m
    return STAIR_RISER_M, STAIR_TREAD_M


def stair_width_for(usage: str = "") -> float:
    """Ancho de la CAJA de escalera del uso (m).

    La caja nunca se encoge: si la norma pide menos que la caja
    clásica de 1,40 m, se mantiene 1,40 m; en salud crece a 1,80 m.
    """
    width = STAIR_WIDTH_M
    registry = _neufert_registry()
    if registry is not None:
        width = max(width, registry.stair_rule(usage).ancho_m)
    return round(width, 2)


def stair_geometry(rise_m: float, usage: str = "") -> Tuple[int, float]:
    """(escalones, desarrollo en m) para salvar «rise_m» de altura.

    Con «usage» aplica la contrahuella y huella de Neufert para el uso
    social (Blondel 2h + p = 0,60–0,64 m); el desarrollo se limita a
    2,4–4,8 m como siempre.
    """
    riser, tread = stair_geometry_for(usage)
    steps = max(3, math.ceil(rise_m / riser))
    run = round(min(4.8, max(2.4, steps * tread)), 2)
    return steps, run


def stairs_needed(data: "BuildingWizardData") -> bool:
    """¿La edificación necesita escalera (varios niveles o desnivel)?"""
    return len(data.levels) > 1 or terrain_rise_m(data.terrain_type) > 0.0


# SUGERENCIAS NORMATIVAS POR USO (v2.7.0, Neufert): pasillo, puerta y
# espesor de muro salen del catálogo; el usuario los puede cambiar
# (la norma aconseja, nunca obliga).

SALUD_USAGES: Tuple[str, ...] = ("Hospital", "Policlínico",
                                 "Consultorio médico")

USOS_CON_ESTACIONAMIENTO: Tuple[str, ...] = (
    "Oficina", "Escuela primaria", "Policlínico", "Hospital",
    "Comedor social", "Centro comunitario", "Local comercial",
    USO_COMERCIAL_CC, USO_COMERCIAL_OF)


# EDICIONES REGIONALES DE NEUFERT (v2.8.0): el libro se publica
# adaptado por regiones — clima, materiales y códigos locales cambian
# valores concretos. La base es la 5.ª ed. en español; cada región
# (Cuba, México, Argentina…) la ajusta con una fusión profunda.
NEUFERT_REGION_BASE = "base"
NEUFERT_REGION_BASE_LABEL = "Base — 5.ª ed. en español"


def neufert_region_choices() -> List[Tuple[str, str]]:
    """Ediciones regionales disponibles: [(codigo, etiqueta)].

    La base va siempre primera; las regiones salen del directorio de
    recursos (fichero roto se salta, la norma aconseja y no bloquea).
    """
    choices: List[Tuple[str, str]] = [(NEUFERT_REGION_BASE,
                                       NEUFERT_REGION_BASE_LABEL)]
    registry = _neufert_registry()
    if registry is not None:
        for info in registry.available_regions():
            label = info["nombre"]
            if info.get("edicion"):
                label = f"{label} ({info['edicion']})"
            choices.append((str(info["codigo"]), label))
    return choices


def neufert_region_code(label: str) -> str:
    """Código de la edición a partir de su etiqueta del combo."""
    if not label:
        return NEUFERT_REGION_BASE
    for code, choice_label in neufert_region_choices():
        if label == choice_label:
            return code
    return NEUFERT_REGION_BASE


def neufert_region_label(code: str) -> str:
    """Etiqueta del combo a partir del código de la edición."""
    for choice_code, label in neufert_region_choices():
        if choice_code == (code or NEUFERT_REGION_BASE):
            return label
    return NEUFERT_REGION_BASE_LABEL


def set_neufert_region(code: str) -> bool:
    """Activa la edición regional en el registro único del proceso.

    Devuelve True si la región se aplicó (base siempre; el resto
    exige su fichero). Sin registro, False amable.
    """
    registry = _neufert_registry()
    if registry is None:
        return False
    return registry.set_region(code or NEUFERT_REGION_BASE)


def _sync_region(data: "BuildingWizardData") -> None:
    """Alinea el registro único con la edición elegida en el paso 1.

    Así los avisos, defaults y metadata responden SIEMPRE a la región
    del asistente (GUI o pruebas), aunque el singleton sea del proceso.
    """
    registry = _neufert_registry()
    wanted = (data.neufert_region or NEUFERT_REGION_BASE) \
        if data is not None else NEUFERT_REGION_BASE
    if registry is not None and registry.region_code != wanted:
        registry.set_region(wanted)


def neufert_region_name(code: str = "") -> str:
    """Nombre corto de la edición (para avisos y resumen)."""
    registry = _neufert_registry()
    if registry is None:
        return ""
    if not code or code == NEUFERT_REGION_BASE:
        return "Base"
    if registry.region_code == code:
        return registry.region_name
    for info in registry.available_regions():
        if info["codigo"] == code:
            return str(info["nombre"])
    return ""


def suggested_corridor_width(usage: str) -> float:
    """Ancho de pasillo que Neufert recomienda para el uso (m).

    Vivienda 1,20 m; oficinas y comercios 1,50–1,80 m; escuelas y
    salud (pasa la camilla) 2,40 m.
    """
    registry = _neufert_registry()
    if registry is not None:
        value = registry.corridor_for(usage)
        if value is not None:
            return round(value, 2)
    return 1.2


# PASILLO POR LOCALES (v3.21.0): dentro de un mismo uso social NO
# todos los locales piden lo mismo — por tomografía, quirófano o
# hospitalización pasa una CAMILLA (2,40 m); hacia morgue, almacén o
# esterilización ruedan carros y camillas de servicio (2,00 m); el
# laboratorio y el local de desechos piden 1,80 m; el nodo informático
# 1,50 m. El DNA de cada espacio trae su «pasillo_m» como datos
# (resources/knowledge/space_dna.json) y el asistente sube el ancho
# del pasillo al máximo que pide el LOCALE más exigente del programa.

_DNA_CACHE: List[Any] = []


def _dna_registry(ctx: Any = None) -> Any:
    """Registro del DNA de espacios (v3.21.0); None sin catálogo.

    Con ``ctx`` usa el registro del proyecto (ya cargado); sin él,
    carga una copia cacheada de resources/knowledge/space_dna.json.
    La norma aconseja y no bloquea: sin DNA se siguen las reglas de
    siempre.
    """
    if ctx is not None:
        registry = getattr(ctx, "dna_registry", None)
        if registry is not None and len(registry) > 0:
            return registry
    if _DNA_CACHE:
        return _DNA_CACHE[0]
    try:
        import os as _os
        from app.paths import resource_path
        from domain.knowledge import SpaceDNARegistry
        registry = SpaceDNARegistry()
        path = resource_path("knowledge", "space_dna.json")
        if _os.path.exists(path):
            registry.load_file(path)
        _DNA_CACHE.append(registry)
        return registry
    except Exception:  # noqa: BLE001 — sin catálogo, reglas clásicas
        return None


def pasillo_minimo_de_uso(space_type: str, ctx: Any = None) -> Optional[float]:
    """Ancho de pasillo que el DNA del tipo de local pide (m) o None."""
    registry = _dna_registry(ctx)
    if registry is None:
        return None
    dna = registry.get(str(space_type or ""))
    if dna is None:
        return None
    try:
        value = float((dna.metadata or {}).get("pasillo_m", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    return round(value, 2) if value > 0.0 else None


def suggested_corridor_width_for_rooms(
        usage: str, room_types: Sequence[str], ctx: Any = None
        ) -> Tuple[float, str]:
    """Pasillo que piden el USO social y los LOCALES del programa (m).

    Parte del ancho base del uso (Neufert) y lo sube al máximo que
    pida el DNA de algún local del programa. Devuelve ``(ancho, "")``
    cuando manda el uso, y ``(ancho, tipo_de_local)`` cuando el que
    manda es un local concreto (p. ej. ``"CT_ROOM"`` por la camilla
    de tomografía), para que el aviso pueda citar al culpable.
    """
    requerido = suggested_corridor_width(usage)
    culpable = ""
    for space_type in room_types or []:
        value = pasillo_minimo_de_uso(space_type, ctx)
        if value is not None and value > requerido + 1e-9:
            requerido = value
            culpable = str(space_type)
    return round(requerido, 2), culpable


def _nombre_de_uso_espacio(space_type: str, ctx: Any = None) -> str:
    """Nombre en español del tipo de local (para avisos)."""
    registry = _dna_registry(ctx)
    if registry is not None:
        dna = registry.get(str(space_type or ""))
        if dna is not None and getattr(dna, "name_es", ""):
            return str(dna.name_es)
    return str(space_type or "")


def suggested_door_width(usage: str) -> float:
    """Ancho de puerta recomendado para el uso (m).

    Donde pasa una camilla (salud) la hoja es de 1,20 m; interior
    cómodo, 0,90 m.
    """
    registry = _neufert_registry()
    if registry is not None:
        ancho, _alto = registry.door_for(usage)
        return round(ancho, 2)
    return 1.2 if usage in SALUD_USAGES else 0.9


def suggested_wall_thickness(construction_type: str) -> float:
    """Espesor de muro exterior por tipología constructiva (m).

    Neufert: 0,20 m la mampostería confinada; 0,40 m la piedra;
    0,45 m la tierra; 0,10 m los paneles ligeros.
    """
    registry = _neufert_registry()
    if registry is not None:
        value = registry.wall_thickness_for(construction_type,
                                            exterior=True)
        if value is not None:
            return round(value, 2)
    return 0.2


def apply_neufert_defaults(data: "BuildingWizardData") -> List[str]:
    """Sube pasillo, puerta y muro a lo que Neufert pide para el uso.

    SOLO SUBE: nunca reduce lo que el usuario ya pidió. Se llama al
    cargar el programa del uso social y al cambiar de edición regional
    (v2.8.0); devuelve los cambios en texto amable para la GUI.
    Desde v3.21.0 el pasillo también atiende a los LOCALES del
    programa: si el DNA de alguno pide más que el uso (camillas de
    tomografía, carros de morgue…), el ancho sube a lo pedido.
    """
    _sync_region(data)
    changes: List[str] = []
    corridor, _culpable = suggested_corridor_width_for_rooms(
        data.usage_type, [r.space_type for r in (data.rooms or [])])
    if data.corridor_enabled and data.corridor_width_m + 1e-9 < corridor:
        data.corridor_width_m = corridor
        changes.append(f"pasillo a {corridor:.2f} m")
    door = suggested_door_width(data.usage_type)
    if data.door_width_m + 1e-9 < door:
        data.door_width_m = door
        changes.append(f"puerta a {door:.2f} m")
    wall = suggested_wall_thickness(data.construction_type)
    if data.wall_thickness_m + 1e-9 < wall:
        data.wall_thickness_m = wall
        changes.append(f"muro a {wall:.2f} m")
    return changes


def stairs_wanted(data: "BuildingWizardData") -> bool:
    """¿Se colocan escaleras según la decisión del usuario?"""
    if data.stairs_mode == STAIR_NEVER:
        return False
    if data.stairs_mode == STAIR_ALWAYS:
        return True
    return stairs_needed(data)


def _stair_rise_for(data: "BuildingWizardData") -> float:
    """Altura que salva la escalera: desnivel del terreno o entre plantas."""
    rise = terrain_rise_m(data.terrain_type)
    if rise > 0.0:
        return rise
    if len(data.levels) > 1:
        return data.levels[0].height_m
    return 3.0


# NÚCLEO RÍGIDO EN ESQUINAS (v2.5.0): caja de servicios (escalera,
# baños y ductos entre muros estructurales de refuerzo) colocada en la
# esquina frontal de la planta. Igual que las escaleras, el usuario
# decide: automática (edificios de varios niveles o con desnivel),
# siempre o nunca.
CORE_TYPE = "CORE"

CORE_MODES: Tuple[str, ...] = (
    "Automática (según niveles y terreno)",
    "Sí, núcleo en esquinas",
    "No incluir",
)
CORE_AUTO, CORE_ALWAYS, CORE_NEVER = CORE_MODES

CORE_WIDTH_M = 3.0   # ancho de la caja del núcleo
CORE_DEPTH_M = 4.2   # fondo de la caja del núcleo


def core_needed(data: "BuildingWizardData") -> bool:
    """¿Conviene núcleo rígido (varios niveles o desnivel)?"""
    return stairs_needed(data)


def core_wanted(data: "BuildingWizardData") -> bool:
    """¿Se coloca el núcleo rígido según la decisión del usuario?"""
    if data.core_mode == CORE_NEVER:
        return False
    if data.core_mode == CORE_ALWAYS:
        return True
    return core_needed(data)


def _core_spec(level_name: str) -> RoomSpec:
    """Local de núcleo rígido: escalera + baños + ductos en esquina."""
    return RoomSpec(name=f"Núcleo rígido {level_name}",
                    space_type=CORE_TYPE, width_m=CORE_WIDTH_M,
                    depth_m=CORE_DEPTH_M, level_ref=level_name,
                    with_window=False)


# Relación legible → kind del spec §8 (RELATIONSHIP_KINDS).
RELATION_KINDS_ES: Tuple[Tuple[str, str], ...] = (
    ("Adyacente a", "adjacent_to"),
    ("Comunicado con", "accessible_from"),
    ("Requiere acceso desde", "requires_access"),
    ("Relacionada visualmente", "visually_related_to"),
    ("Separada acústicamente", "acoustically_separated_from"),
    ("Relacionada por servicio", "service_related_to"),
)
KIND_BY_LABEL: Dict[str, str] = dict(RELATION_KINDS_ES)

CORRIDOR_TYPE = "CORRIDOR"

# -- Programas tipo (el usuario empieza con un clic) -------------------------

_PROGRAM_VIVIENDA: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Sala", "LIVING_ROOM", 4.0, 3.0, True),
    ("Comedor", "DINING_ROOM", 3.0, 3.0, True),
    ("Cocina", "KITCHEN", 3.0, 2.5, True),
    ("Dormitorio 1", "BEDROOM", 3.5, 3.0, True),
    ("Dormitorio 2", "BEDROOM", 3.0, 3.0, True),
    ("Baño", "BATHROOM", 1.8, 2.0, False),
)

_PROGRAM_OFICINA: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Recepción", "ENTRANCE", 3.0, 2.5, True),
    ("Oficina 1", "OFFICE", 3.0, 3.0, True),
    ("Oficina 2", "OFFICE", 3.0, 3.0, True),
    ("Sala de reuniones", "OFFICE", 4.0, 3.0, True),
    ("Baño", "BATHROOM", 1.8, 2.0, False),
    ("Depósito", "STOREROOM", 2.0, 1.5, False),
)

_PROGRAM_ESCUELA: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Porche de acceso", "ENTRANCE", 4.0, 2.5, True),
    # Aulas de 6,00 × 6,00 m = 36 m2 (Neufert: 2,0 m2 por alumno).
    ("Aula 1", "CLASSROOM", 6.0, 6.0, True),
    ("Aula 2", "CLASSROOM", 6.0, 6.0, True),
    ("Aula 3", "CLASSROOM", 6.0, 6.0, True),
    ("Biblioteca", "LIBRARY", 5.0, 4.0, True),
    ("Sala de profesores", "OFFICE", 4.0, 3.0, True),
    ("Dirección", "OFFICE", 3.0, 3.0, True),
    ("Baño alumnos", "BATHROOM", 2.0, 2.2, False),
    ("Baño profesores", "BATHROOM", 1.8, 2.0, False),
)

# v3.26.0: programa básico de secundaria (el paramétrico por capacidad
# sale del documento educacional §107 con NUM_AULAS = CEIL).
_PROGRAM_SECUNDARIA: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Acceso", "ENTRANCE", 4.0, 2.5, True),
    ("Aula 1", "CLASSROOM", 7.5, 8.0, True),
    ("Aula 2", "CLASSROOM", 7.5, 8.0, True),
    ("Laboratorio de ciencias", "LABORATORY", 9.0, 8.0, True),
    ("Laboratorio informático", "LAB_COMPUTACION", 8.0, 7.5, True),
    ("Taller", "TALLER_TECNOLOGICO", 9.0, 8.0, False),
    ("Biblioteca", "LIBRARY", 6.0, 5.0, True),
    ("Administración", "ADMINISTRATION", 4.0, 3.0, True),
    ("Vestuarios", "DRESSING_ROOM", 4.0, 3.0, False),
    ("Baño", "BATHROOM", 2.4, 2.2, False),
)

_PROGRAM_CIRCULO: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Vestíbulo", "ENTRANCE", 3.0, 2.5, True),
    ("Sala 1 (1-2 años)", "CLASSROOM", 5.0, 4.0, True),
    ("Sala 2 (3-4 años)", "CLASSROOM", 5.0, 4.0, True),
    ("Comedor", "DINING_ROOM", 5.0, 3.5, True),
    ("Cocina", "KITCHEN", 3.5, 3.0, True),
    ("Baño", "BATHROOM", 2.0, 2.2, False),
    ("Lactario", "CONSULTATION_ROOM", 2.5, 2.5, False),
)

_PROGRAM_CONSULTORIO: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Sala de espera", "WAITING_ROOM", 4.0, 3.0, True),
    ("Consultorio 1", "CONSULTATION_ROOM", 3.5, 3.0, True),
    ("Consultorio 2", "CONSULTATION_ROOM", 3.5, 3.0, True),
    ("Enfermería", "CONSULTATION_ROOM", 3.0, 2.5, True),
    ("Baño", "BATHROOM", 1.8, 2.0, False),
    ("Depósito", "STOREROOM", 2.0, 1.5, False),
)

_PROGRAM_COMEDOR: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Comedor social", "DINING_ROOM", 8.0, 6.0, True),
    ("Cocina", "KITCHEN", 5.0, 3.5, True),
    ("Despensa", "STOREROOM", 2.5, 2.0, False),
    ("Lavandería", "STOREROOM", 2.5, 2.0, False),
    ("Baño", "BATHROOM", 2.0, 2.2, False),
)

_PROGRAM_COMUNITARIO: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Vestíbulo", "ENTRANCE", 3.0, 2.5, True),
    ("Sala multiuso", "MULTIUSE_HALL", 8.0, 6.0, True),
    ("Sala de reuniones", "OFFICE", 4.0, 3.0, True),
    ("Biblioteca", "OFFICE", 4.0, 3.0, True),
    ("Baño", "BATHROOM", 2.0, 2.2, False),
    ("Depósito", "STOREROOM", 2.0, 1.5, False),
)

_PROGRAM_ALBERGUE: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Recepción", "ENTRANCE", 3.0, 2.5, True),
    ("Dormitorio 1", "BEDROOM", 4.0, 3.5, True),
    ("Dormitorio 2", "BEDROOM", 4.0, 3.5, True),
    ("Dormitorio 3", "BEDROOM", 4.0, 3.5, True),
    ("Baño común", "BATHROOM", 2.4, 2.2, False),
    ("Comedor", "DINING_ROOM", 5.0, 3.5, True),
    ("Cocina", "KITCHEN", 3.5, 3.0, True),
)

_PROGRAM_COMERCIO: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Área de ventas", "ROOM", 6.0, 5.0, True),
    ("Depósito", "STOREROOM", 3.0, 2.5, False),
    ("Oficina", "OFFICE", 3.0, 2.5, True),
    ("Baño", "BATHROOM", 1.8, 2.0, False),
)

# -- TEMA HOSPITALARIO (v2.2.0; especialidades v3.20.0) ---------------------
# Red de salud: policlínico en un nivel y hospital completo en tres
# niveles (PB accesos/urgencias/imagenología + especialidades
# diagnósticas y de apoyo, P1 quirófanos + cuidados progresivos,
# P2 hospitalización), con áreas orientadas a la práctica
# hospitalaria (quirófano ≥ 36 m², sala de camas ≥ 28 m²).
# v3.20.0: se suman las especialidades pedidas — tomografía,
# fluoroscopio, anatomía patológica, morgue, laboratorio de
# microbiología, nodo informático, local PGD y almacenes.

_PROGRAM_POLICLINICO: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Vestíbulo y admisión", "ENTRANCE", 4.0, 2.5, True),
    ("Sala de espera", "WAITING_ROOM", 6.0, 4.0, True),
    ("Consultorio 1", "CONSULTATION_ROOM", 3.5, 3.0, True),
    ("Consultorio 2", "CONSULTATION_ROOM", 3.5, 3.0, True),
    ("Urgencias", "EMERGENCY_ROOM", 4.5, 4.0, True),
    ("Laboratorio clínico", "LABORATORY", 4.0, 3.0, False),
    ("Sala de rayos X", "IMAGING_ROOM", 5.0, 4.0, False),
    ("Tomografía (TAC)", "CT_ROOM", 6.0, 5.0, False),
    ("Laboratorio de microbiología", "MICROBIOLOGY_LAB", 5.0, 3.5, False),
    ("Farmacia", "PHARMACY", 3.5, 2.5, True),
    ("Esterilización", "STERILIZATION_ROOM", 3.5, 3.0, False),
    ("Baño", "BATHROOM", 2.0, 2.2, False),
    ("Almacén", "WAREHOUSE", 4.0, 2.5, False),
    ("Local PGD (desechos)", "WASTE_ROOM", 3.0, 2.5, False),
)

_PROGRAM_HOSPITAL_PB: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Vestíbulo y admisión", "ENTRANCE", 5.0, 3.0, True),
    ("Sala de espera", "WAITING_ROOM", 6.0, 4.0, True),
    ("Urgencias", "EMERGENCY_ROOM", 6.0, 5.0, True),
    ("Farmacia", "PHARMACY", 4.0, 3.0, True),
    ("Laboratorio clínico", "LABORATORY", 5.0, 3.5, False),
    ("Sala de rayos X", "IMAGING_ROOM", 6.0, 5.0, False),
    ("Tomografía (TAC)", "CT_ROOM", 6.0, 5.0, False),
    ("Fluoroscopio", "FLUOROSCOPY_ROOM", 5.5, 4.5, False),
    ("Anatomía patológica", "ANATOMY_PATHOLOGY", 6.0, 4.0, False),
    ("Morgue", "MORGUE", 5.0, 3.5, False),
    ("Laboratorio de microbiología", "MICROBIOLOGY_LAB", 5.0, 3.5, False),
    ("Nodo informático", "SERVER_ROOM", 3.0, 2.8, False),
    ("Almacén general", "WAREHOUSE", 5.0, 3.0, False),
    ("Local PGD (desechos)", "WASTE_ROOM", 3.0, 2.5, False),
    ("Baño", "BATHROOM", 2.4, 2.2, False),
    ("Depósito general", "STOREROOM", 2.5, 2.0, False),
)

_PROGRAM_HOSPITAL_P1: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Quirófano 1", "OPERATING_ROOM", 7.0, 6.0, False),
    ("Quirófano 2", "OPERATING_ROOM", 7.0, 6.0, False),
    # UCI con 2 camas × 18 m2 (Neufert: cuidados intensivos).
    ("UCI (2 camas)", "ICU", 6.0, 6.0, False),
    ("Esterilización central", "STERILIZATION_ROOM", 4.0, 3.5, False),
    ("Recuperación (URPA)", "WARD", 6.0, 5.0, True),
    ("Cuidados progresivos", "PROGRESSIVE_CARE", 6.0, 5.0, True),
    ("Enfermería de cirugía", "NURSE_STATION", 3.5, 3.0, False),
    ("Baño de quirófanos", "BATHROOM", 2.0, 2.0, False),
)

_PROGRAM_HOSPITAL_P2: Tuple[Tuple[str, str, float, float, bool], ...] = (
    ("Sala de hospitalización 1", "WARD", 6.0, 5.0, True),
    ("Sala de hospitalización 2", "WARD", 6.0, 5.0, True),
    ("Estación de enfermería", "NURSE_STATION", 3.5, 3.0, False),
    ("Carrito de curas", "STOREROOM", 2.0, 1.5, False),
    ("Baño de pacientes", "BATHROOM", 2.4, 2.2, False),
    ("Sala de estar", "DINING_ROOM", 4.5, 3.5, True),
)

PROGRAM_PRESETS: Dict[str, Tuple[Tuple[str, str, float, float, bool], ...]] = {
    "Vivienda": _PROGRAM_VIVIENDA,
    "Oficina": _PROGRAM_OFICINA,
    "Escuela primaria": _PROGRAM_ESCUELA,
    "Escuela secundaria": _PROGRAM_SECUNDARIA,
    "Círculo infantil": _PROGRAM_CIRCULO,
    "Consultorio médico": _PROGRAM_CONSULTORIO,
    "Policlínico": _PROGRAM_POLICLINICO,
    "Hospital": _PROGRAM_HOSPITAL_PB + _PROGRAM_HOSPITAL_P1
                + _PROGRAM_HOSPITAL_P2,
    "Comedor social": _PROGRAM_COMEDOR,
    "Centro comunitario": _PROGRAM_COMUNITARIO,
    "Albergue": _PROGRAM_ALBERGUE,
    "Local comercial": _PROGRAM_COMERCIO,
}

# Programas MULTI-NIVEL: cada entrada es (nivel, programa). Al
# sugerir el uso, los locales se reparten por nivel; si faltan
# niveles se crean con altura 3,2 m (plenum de A/C hospitalario).
LEVEL_PROGRAMS: Dict[str, Tuple[Tuple[str, Tuple[Tuple[str, str, float, float, bool], ...]], ...]] = {
    "Hospital": (
        ("Planta Baja", _PROGRAM_HOSPITAL_PB),
        ("Planta 1", _PROGRAM_HOSPITAL_P1),
        ("Planta 2", _PROGRAM_HOSPITAL_P2),
    ),
}

# Usos sociales (el combo del paso 1 y el botón «Sugerir locales»).
# v3.25.0: «Centro comercial» y «Oficinas (torre/corporativo)» cargan
# el programa mínimo del documento CC/OF (§89-90).
USAGE_TYPES: Tuple[str, ...] = (
    "Vivienda", "Oficina", "Centro comercial",
    "Oficinas (torre/corporativo)", "Escuela primaria",
    "Escuela secundaria", "Círculo infantil", "Consultorio médico",
    "Policlínico", "Hospital", "Comedor social",
    "Centro comunitario", "Albergue", "Local comercial",
)

# Pares de TIPOS de local que reciben PUERTA sugerida según el uso
# (la relación sale del DNA; la puerta viene de aquí). Los pares no
# distinguen orden: urgencias→rayos X es lo mismo que rayos X→urgencias.
# v2.4.0: se amplía a TODOS los usos institucionales (la vivienda se
# queda sin puertas críticas sugeridas, como siempre).
USAGE_DOOR_PAIRS: Dict[str, Tuple[frozenset, ...]] = {
    "Oficina": (
        frozenset(("ENTRANCE", "OFFICE")),
        frozenset(("OFFICE", "BATHROOM")),
    ),
    "Escuela primaria": (
        frozenset(("ENTRANCE", "OFFICE")),
        frozenset(("CLASSROOM", "BATHROOM")),
        frozenset(("OFFICE", "BATHROOM")),
    ),
    "Escuela secundaria": (
        frozenset(("ENTRANCE", "ADMINISTRATION")),
        frozenset(("CLASSROOM", "BATHROOM")),
        frozenset(("LABORATORY", "STOREROOM")),
        frozenset(("DRESSING_ROOM", "GYMNASIO")),
    ),
    "Círculo infantil": (
        frozenset(("CLASSROOM", "BATHROOM")),
        frozenset(("CLASSROOM", "DINING_ROOM")),
        frozenset(("DINING_ROOM", "KITCHEN")),
        frozenset(("ENTRANCE", "CONSULTATION_ROOM")),
    ),
    "Consultorio médico": (
        frozenset(("WAITING_ROOM", "CONSULTATION_ROOM")),
        frozenset(("CONSULTATION_ROOM", "BATHROOM")),
    ),
    "Policlínico": (
        frozenset(("WAITING_ROOM", "CONSULTATION_ROOM")),
        frozenset(("WAITING_ROOM", "EMERGENCY_ROOM")),
        frozenset(("WAITING_ROOM", "PHARMACY")),
        frozenset(("EMERGENCY_ROOM", "IMAGING_ROOM")),
        frozenset(("EMERGENCY_ROOM", "LABORATORY")),
        frozenset(("EMERGENCY_ROOM", "CT_ROOM")),
        frozenset(("IMAGING_ROOM", "CT_ROOM")),
        frozenset(("LABORATORY", "MICROBIOLOGY_LAB")),
        frozenset(("CONSULTATION_ROOM", "BATHROOM")),
        frozenset(("PHARMACY", "STOREROOM")),
        frozenset(("WAREHOUSE", "WASTE_ROOM")),
    ),
    "Hospital": (
        frozenset(("WAITING_ROOM", "CONSULTATION_ROOM")),
        frozenset(("WAITING_ROOM", "EMERGENCY_ROOM")),
        frozenset(("WAITING_ROOM", "PHARMACY")),
        frozenset(("EMERGENCY_ROOM", "IMAGING_ROOM")),
        frozenset(("EMERGENCY_ROOM", "LABORATORY")),
        frozenset(("EMERGENCY_ROOM", "CT_ROOM")),
        frozenset(("EMERGENCY_ROOM", "FLUOROSCOPY_ROOM")),
        frozenset(("IMAGING_ROOM", "CT_ROOM")),
        frozenset(("CT_ROOM", "FLUOROSCOPY_ROOM")),
        frozenset(("LABORATORY", "MICROBIOLOGY_LAB")),
        frozenset(("EMERGENCY_ROOM", "OPERATING_ROOM")),
        frozenset(("OPERATING_ROOM", "STERILIZATION_ROOM")),
        frozenset(("OPERATING_ROOM", "NURSE_STATION")),
        frozenset(("WARD", "NURSE_STATION")),
        frozenset(("WARD", "BATHROOM")),
        frozenset(("WARD", "DINING_ROOM")),
        frozenset(("NURSE_STATION", "STOREROOM")),
        frozenset(("LABORATORY", "STOREROOM")),
        frozenset(("PHARMACY", "STOREROOM")),
        frozenset(("ANATOMY_PATHOLOGY", "MORGUE")),
        frozenset(("ANATOMY_PATHOLOGY", "MICROBIOLOGY_LAB")),
        frozenset(("MORGUE", "WASTE_ROOM")),
        frozenset(("WAREHOUSE", "WASTE_ROOM")),
        frozenset(("WAREHOUSE", "STOREROOM")),
        frozenset(("PROGRESSIVE_CARE", "NURSE_STATION")),
    ),
    "Comedor social": (
        frozenset(("DINING_ROOM", "KITCHEN")),
        frozenset(("KITCHEN", "STOREROOM")),
    ),
    "Centro comunitario": (
        frozenset(("ENTRANCE", "MULTIUSE_HALL")),
        frozenset(("OFFICE", "BATHROOM")),
    ),
    "Albergue": (
        frozenset(("BEDROOM", "BATHROOM")),
        frozenset(("DINING_ROOM", "KITCHEN")),
        frozenset(("ENTRANCE", "DINING_ROOM")),
    ),
    "Local comercial": (
        frozenset(("ROOM", "STOREROOM")),
        frozenset(("OFFICE", "STOREROOM")),
    ),
    USO_COMERCIAL_CC: (
        frozenset(("ENTRANCE", "VESTIBULE")),
        frozenset(("VESTIBULE", "GALLERY")),
        frozenset(("GALLERY", "RETAIL_LOCAL")),
        frozenset(("GALLERY", "BATHROOM")),
        frozenset(("RETAIL_LOCAL", "WAREHOUSE")),
    ),
    USO_COMERCIAL_OF: (
        frozenset(("ENTRANCE", "RECEPTION")),
        frozenset(("RECEPTION", "OFFICE")),
        frozenset(("OFFICE", "BATHROOM")),
        frozenset(("OPEN_OFFICE", "BATHROOM")),
        frozenset(("MEETING_ROOM", "OFFICE")),
    ),
}

# Pares de TIPOS con relación de ADYACENCIA extra por uso (v2.4.0):
# encadenan locales que el DNA no une por sí solo (aulas en cadena,
# salas de hospitalización contiguas…) SIN puerta automática: la
# puerta solo llega si el par está también en USAGE_DOOR_PAIRS.
USAGE_EXTRA_PAIRS: Dict[str, Tuple[frozenset, ...]] = {
    "Oficina": (frozenset(("OFFICE", "OFFICE")),),
    USO_COMERCIAL_CC: (
        frozenset(("RETAIL_LOCAL", "RETAIL_LOCAL")),
        frozenset(("GALLERY", "ATRIUM")),
    ),
    USO_COMERCIAL_OF: (
        frozenset(("OFFICE", "OFFICE")),
        frozenset(("MEETING_ROOM", "MEETING_ROOM")),
    ),
    "Escuela primaria": (frozenset(("CLASSROOM", "CLASSROOM")),),
    "Escuela secundaria": (
        frozenset(("CLASSROOM", "CLASSROOM")),
        frozenset(("CLASSROOM", "LABORATORY")),
    ),
    "Círculo infantil": (frozenset(("CLASSROOM", "CLASSROOM")),),
    "Consultorio médico": (
        frozenset(("CONSULTATION_ROOM", "CONSULTATION_ROOM")),),
    "Policlínico": (
        frozenset(("CONSULTATION_ROOM", "CONSULTATION_ROOM")),
        frozenset(("EMERGENCY_ROOM", "STERILIZATION_ROOM")),
    ),
    "Hospital": (
        frozenset(("WARD", "WARD")),
        frozenset(("WARD", "DINING_ROOM")),
        frozenset(("LABORATORY", "PHARMACY")),
        frozenset(("LABORATORY", "STOREROOM")),
        frozenset(("STERILIZATION_ROOM", "NURSE_STATION")),
        frozenset(("WARD", "PROGRESSIVE_CARE")),
        frozenset(("PROGRESSIVE_CARE", "ICU")),
        frozenset(("MORGUE", "ANATOMY_PATHOLOGY")),
        frozenset(("LABORATORY", "MICROBIOLOGY_LAB")),
        frozenset(("WAREHOUSE", "WAREHOUSE")),
    ),
    "Albergue": (frozenset(("BEDROOM", "BEDROOM")),),
    "Centro comunitario": (
        frozenset(("MULTIUSE_HALL", "OFFICE")),
        frozenset(("MULTIUSE_HALL", "ENTRANCE")),
    ),
    "Comedor social": (frozenset(("DINING_ROOM", "BATHROOM")),),
    "Local comercial": (
        frozenset(("ROOM", "STOREROOM")),
        frozenset(("ROOM", "OFFICE")),
    ),
}

# Módulos de instalaciones sugeridos según el uso social.
_INSTALLATION_PRESETS: Dict[str, Tuple[str, ...]] = {
    "Hospital": ("Eléctrica", "Sanitaria",
                 "Ventilación mecánica / A/C",
                 "Protección contra incendios",
                 "Comunicaciones (voz y datos)", "Gas"),
    USO_COMERCIAL_CC: ("Eléctrica", "Sanitaria",
                       "Ventilación mecánica / A/C",
                       "Protección contra incendios",
                       "Comunicaciones (voz y datos)"),
    USO_COMERCIAL_OF: ("Eléctrica", "Sanitaria",
                       "Ventilación mecánica / A/C",
                       "Protección contra incendios",
                       "Comunicaciones (voz y datos)"),
    "Escuela secundaria": ("Eléctrica", "Sanitaria",
                          "Ventilación mecánica / A/C",
                          "Protección contra incendios",
                          "Comunicaciones (voz y datos)"),
    "Policlínico": ("Eléctrica", "Sanitaria",
                    "Ventilación mecánica / A/C",
                    "Protección contra incendios",
                    "Comunicaciones (voz y datos)", "Gas"),
    "Consultorio médico": ("Eléctrica", "Sanitaria",
                           "Ventilación mecánica / A/C"),
    "Comedor social": ("Eléctrica", "Sanitaria", "Gas"),
    "Albergue": ("Eléctrica", "Sanitaria", "Gas"),
}


def suggested_installations(usage_type: str) -> Tuple[str, ...]:
    """Módulos de instalaciones razonables para el uso social elegido."""
    return _INSTALLATION_PRESETS.get(
        usage_type, ("Eléctrica", "Sanitaria"))

# Qué espera el conocimiento técnico de cada uso (texto amable).
USAGE_HINTS: Dict[str, str] = {
    "Vivienda": "sala, comedor, cocina, dormitorios y baño; la cocina "
                "cerca del comedor y los dormitorios en la zona más "
                "tranquila.",
    "Oficina": "recepción al frente, oficinas y sala de reuniones; los "
               "baños y el depósito hacia el fondo.",
    "Escuela primaria": "aulas con buena luz, sala de profesores junto "
                        "a dirección, baños separados por grupos.",
    "Escuela secundaria": "aulas, laboratorios y talleres en cadena "
                          "controlada, biblioteca y deportes con "
                          "vestuarios al alcance.",
    "Círculo infantil": "salas de actividad contiguas al comedor y "
                        "cocina, con lactario tranquilo y baños de "
                        "fácil acceso.",
    "Consultorio médico": "sala de espera junto a la entrada, "
                          "consultorios y enfermería en cadena, con "
                          "depósito aparte.",
    "Policlínico": "espera y admisión al frente; urgencias junto a "
                   "rayos X, tomografía y laboratorios; esterilización, "
                   "almacén y baños al fondo, lejos de la espera.",
    "Hospital": "PB con urgencias conectada a imagenología (rayos X, "
                "tomografía y fluoroscopio), laboratorios, anatomía "
                "patológica y morgue, con almacén, nodo informático y "
                "PGD en la zona de servicio; P1 quirófanos en cadena con "
                "esterilización central y cuidados progresivos; P2 salas "
                "de hospitalización junto a su estación de enfermería.",
    "Comedor social": "comedor amplio hacia la fachada y cocina de "
                      "servicio en cadena: despensa, cocción y "
                      "lavandería.",
    "Centro comunitario": "sala multiuso como corazón del edificio, con "
                          "vestíbulo, reuniones y biblioteca en el "
                          "entorno más público.",
    "Albergue": "dormitorios agrupados alrededor del baño común, con "
                "comedor y cocina de apoyo cercanos.",
    "Local comercial": "área de ventas dominante hacia la fachada, con "
                       "depósito comunicable y servicios discretos.",
    USO_COMERCIAL_CC: "galería como columna vertebral con locales y "
                      "ancla, sanitarios y seguridad en el recorrido; "
                      "carga, almacén y residuos sin cruzar al público.",
    USO_COMERCIAL_OF: "recepción y espera al frente; oficinas, planta "
                      "abierta y salas en el bloque de trabajo; baños, "
                      "comedor y técnicos hacia el fondo.",
}

PATIO_TYPE = "PATIO"


def preset_rooms(program: str = "Vivienda",
                 level_name: str = "Planta Baja") -> List["RoomSpec"]:
    """Locales de un programa tipo, listos para el árbol del paso 3."""
    if program in USOS_COMERCIALES:
        specs = _comercial_specs()
        familia = ""
        if specs is not None:
            try:
                from domain.comercial_specs import familia_de_uso
                familia = familia_de_uso(program) or ""
            except Exception:  # noqa: BLE001 — sin dominio: sin programa
                familia = ""
        if familia:
            return _locales_comercial(specs, familia, level_name,
                                      vertical=False)
    rooms: List[RoomSpec] = []
    for name, space_type, width, depth, window in PROGRAM_PRESETS.get(
            program, _PROGRAM_VIVIENDA):
        rooms.append(RoomSpec(name=name, space_type=space_type,
                              width_m=width, depth_m=depth,
                              level_ref=level_name, with_window=window))
    return rooms


def apply_usage_program(data: "BuildingWizardData") -> Tuple[int, int]:
    """Carga el programa del uso social + sus relaciones sugeridas.

    Sustituye locales y relaciones de «data» por la sugerencia del uso
    elegido en el paso 1 (el usuario luego edita todo lo que quiera).
    Para usos con LEVEL_PROGRAMS (v2.2.0: Hospital) reparte los locales
    por nivel y CREA los niveles que falten, sin renombrar los tuyos.
    Para «Vivienda» con tipología del catálogo (v3.23.0) genera el
    programa paramétrico del §7 con las relaciones del §8.
    Devuelve (locales cargados, relaciones sugeridas).
    """
    level_program = LEVEL_PROGRAMS.get(data.usage_type)
    if level_program is not None:
        return _apply_leveled_program(data, level_program)
    if data.usage_type == "Vivienda" \
            and data.vivienda_tipologia != VIVIENDA_TIPOLOGIA_CLASICA:
        return aplicar_programa_vivienda(data)
    if data.usage_type in USOS_COMERCIALES:
        return aplicar_programa_comercial(data)
    if data.usage_type in USOS_EDUCATIVOS:
        tamano = _resuelve_tamano(data.usage_type,
                                  data.educacion_tamano)
        if tamano is not None:
            return aplicar_programa_educacion(data, tamano)
    level_name = data.levels[0].name if data.levels else "Planta Baja"
    data.rooms = preset_rooms(data.usage_type, level_name)
    data.relations = suggest_relations(data)
    return len(data.rooms), len(data.relations)


def _medidas_de_rango(catalogo: Any, clave: str,
                      defecto: Tuple[float, float]) -> Tuple[float, float]:
    """Ancho/fondo desde el área media del rango §7 (proporción suave)."""
    rango = (catalogo.rango(clave) if catalogo is not None else None) or {}
    minimo = float(rango.get("min") or defecto[0] * defecto[1])
    maximo = float(rango.get("max") or minimo)
    area = max((minimo + maximo) / 2.0, 1.0)
    ancho = max(round((area * 1.2) ** 0.5 * 2.0) / 2.0, 1.5)
    fondo = max(round(area / ancho * 20.0) / 20.0, 1.2)
    return ancho, fondo


def _relaciones_vivienda(catalogo: Any, rooms: List["RoomSpec"]) \
        -> List[RelationSpec]:
    """Relaciones del §8 mapeadas a los locales generados.

    Nivel 3 = comunicado con puerta; 2 y 1 = adyacente; X no se crea
    (la vela vivienda_advisories, sección 8 del catálogo).
    """
    try:
        from domain.vivienda_specs import RELACION_A_SPACE
    except Exception:  # noqa: BLE001 — sin dominio no hay relaciones §8
        return []
    por_tipo: Dict[str, List[str]] = {}
    for r in rooms:
        por_tipo.setdefault(r.space_type, []).append(r.name)

    def _nombres_de(codigo: str) -> List[str]:
        tipo = RELACION_A_SPACE.get(str(codigo or ""))
        if tipo is None:
            return []
        return list(por_tipo.get(tipo, []))

    def _resuelve(codigo: str, principal: bool = False) -> List[str]:
        if str(codigo) == "DORMITORIO_PRINCIPAL":
            nombre = "Dormitorio principal"
            return [nombre] if any(r.name == nombre for r in rooms) else []
        if str(codigo) == "DORMITORIOS":
            return [r.name for r in rooms
                    if r.space_type == "BEDROOM"
                    and r.name != "Dormitorio principal"]
        return _nombres_de(codigo)

    relations: List[RelationSpec] = []
    vistos = set()
    for rel in (catalogo.relaciones if catalogo is not None else []):
        nivel = str(rel.get("nivel", ""))
        if nivel not in ("1", "2", "3"):
            continue  # «X»: relación a evitar, no se genera
        for a in _resuelve(rel.get("a")):
            for b in _resuelve(rel.get("b")):
                if a == b or (a, b) in vistos or (b, a) in vistos:
                    continue
                vistos.add((a, b))
                if nivel == "3":
                    relations.append(RelationSpec(
                        a_name=a, b_name=b, kind_es="Comunicado con",
                        with_door=True))
                else:
                    relations.append(RelationSpec(
                        a_name=a, b_name=b, kind_es="Adyacente a",
                        with_door=False))
    return relations


def aplicar_programa_vivienda(data: "BuildingWizardData") -> Tuple[int, int]:
    """Programa paramétrico del catálogo (§6 zonas + §7 rangos).

    Social (vestíbulo, sala, comedor, cocina), privada (dormitorios
    según el contador del usuario y sus baños) y servicio (lavandería,
    despensa), más los extras de la tipología (garaje de la aislada,
    suite de abuelos, cuarto técnico de la progresiva...). Dúplex y
    tríplex parten el programa en planta social y planta privada
    (creando la Planta Alta si falta). Devuelve (locales, relaciones).
    """
    catalogo = _vivienda_catalogo()
    tipologia = None
    if catalogo is not None:
        tipologia = catalogo.tipologia_de_etiqueta(data.vivienda_tipologia)
    clave = str((tipologia or {}).get("clave", "") or "")
    dormitorios = max(1, min(int(data.vivienda_dormitorios or 3), 6))
    banos = max(1, min(int(data.vivienda_banos or 2), 4))

    if not data.levels:
        data.levels.append(LevelSpec(name="Planta Baja", height_m=3.0))
    dos_niveles = clave in VIVIENDA_DOS_NIVELES
    if dos_niveles and len(data.levels) < 2:
        data.levels.append(LevelSpec(name="Planta Alta", height_m=3.0))
    nivel_social = data.levels[0].name
    nivel_privado = (data.levels[1].name if dos_niveles
                     and len(data.levels) > 1 else nivel_social)

    rooms: List[RoomSpec] = []

    def _local(nombre: str, rango: str, tipo_dna: str, nivel: str,
               ventana: bool) -> None:
        ancho, fondo = _medidas_de_rango(catalogo, rango, (3.0, 3.0))
        rooms.append(RoomSpec(name=nombre, space_type=tipo_dna,
                              width_m=ancho, depth_m=fondo,
                              level_ref=nivel, with_window=ventana))

    # ZONA SOCIAL (§6)
    _local("Vestíbulo", "VESTIBULO", "ENTRANCE", nivel_social, False)
    _local("Sala", "SALA", "LIVING_ROOM", nivel_social, True)
    _local("Comedor", "COMEDOR", "DINING_ROOM", nivel_social, True)
    _local("Cocina", "COCINA", "KITCHEN", nivel_social, True)
    # ZONA PRIVADA (§6) — dormitorios y baños según el programa pedido
    _local("Dormitorio principal", "DORMITORIO_PRINCIPAL", "BEDROOM",
           nivel_privado, True)
    for indice in range(2, dormitorios + 1):
        _local(f"Dormitorio {indice}", "DORMITORIO_SECUNDARIO", "BEDROOM",
               nivel_privado, True)
    _local("Baño principal", "BANOS", "BATHROOM", nivel_privado, True)
    if banos >= 2:
        _local("Baño social", "BANOS_SOCIAL", "BATHROOM", nivel_social,
               True)
    if banos >= 3:
        _local("Baño compartido", "BANOS", "BATHROOM", nivel_privado,
               True)
    if banos >= 4:
        _local("Baño de servicio", "BANOS", "BATHROOM", nivel_privado,
               True)
    # ZONA DE SERVICIO (§6)
    _local("Lavandería", "LAVANDERIA", "LAUNDRY", nivel_social, False)
    _local("Despensa", "DESPENSA", "STOREROOM", nivel_social, False)
    # EXTRAS DE LA TIPOLOGÍA (§10-15, §57-59)
    for nombre, rango, tipo_dna, ventana in VIVIENDA_EXTRAS.get(
            clave, ()):
        nivel_extra = nivel_privado if tipo_dna == "BEDROOM" \
            else nivel_social
        _local(nombre, rango, tipo_dna, nivel_extra, ventana)

    data.rooms = rooms
    data.relations = _relaciones_vivienda(catalogo, rooms)
    return len(data.rooms), len(data.relations)


def _medidas_de_cuadro(specs: Any, space_type: str,
                       defecto: Tuple[float, float] = (3.0, 3.0)) \
        -> Tuple[float, float]:
    """Ancho/fondo desde el cuadro MIN/REC del uso y su DNA.

    Regla honesta: el mínimo del cuadro manda; la base de la primera
    gama recomendada sube el área (nunca la media cuando la gama es
    abierta, p. ej. ancla 500-5000); sin cuadro de superficie, el área
    preferente del DNA da un local usable. El ancho respeta los
    mínimos del cuadro y del DNA (ignorando cotas de puertas).
    """
    area = 0.0
    ancho_min = 0.0
    if specs is not None:
        minimos = specs.minimos_de(space_type)
        area = float(minimos.get("area") or 0.0)
        ancho_min = float(minimos.get("ancho") or 0.0)
        if ancho_min < 1.5:
            ancho_min = 0.0  # es cota de puerta (p. ej. acceso 0.90 m)
    dna = None
    dna_min = dna_pref = ancho_dna = 0.0
    try:
        registry = _dna_registry()
        dna = registry.get(space_type) if registry else None
    except Exception:  # noqa: BLE001 — sin DNA: defecto
        dna = None
    if dna is not None:
        try:
            dna_min = float(getattr(dna, "minimum_area", 0.0) or 0.0)
            dna_pref = float(getattr(dna, "preferred_area", 0.0) or 0.0)
            ancho_dna = float(getattr(dna, "minimum_width", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
    gamas = specs.gamas_superficie(space_type) if specs is not None \
        else []
    if gamas:
        try:
            extremos = gamas[0].split(" ")[0].split("-")
            area = max(area, float(extremos[0]))
        except (ValueError, IndexError):
            pass
    elif area <= 0:
        area = dna_pref or dna_min
    elif dna_pref > area:
        area = dna_pref
    if area <= 0:
        area = defecto[0] * defecto[1]
    ancho = max(round((area * 1.2) ** 0.5 * 2.0) / 2.0, 1.5,
                round(ancho_min * 2.0) / 2.0, round(ancho_dna * 2.0) / 2.0)
    # el fondo se redondea hacia ARRIBA (paso 0.05 m): el local nunca
    # queda por debajo del área objetivo por el redondeo (el ancla
    # medía 499.8 m2 con un objetivo de 500)
    fondo = max(round(-(-area / ancho * 20.0 // 1) / 20.0, 2), 1.2)
    return ancho, fondo


def _locales_comercial(specs: Any, familia: str, nivel_pb: str,
                       vertical: bool, nivel_alto: str = "") \
        -> List["RoomSpec"]:
    """Locales del programa mínimo del §89-90 para la familia.

    Los ítems no locales (STAIR, CORE) los traza el motor de escaleras
    y núcleos, así que no entran al árbol. En tipologías verticales de
    OFICINAS el bloque de trabajo sube a la planta tipo.
    """
    rooms: List[RoomSpec] = []
    for item in specs.programa(familia):
        if not item.get("es_local", True):
            continue  # escaleras y núcleos: los dibuja el trazado
        tipo = str(item.get("space_type", ""))
        nombre = str(item.get("nombre", ""))
        nivel = nivel_pb
        if vertical and str(item.get("item", "")) in ITEMS_PLANTA_TIPO_OF:
            nivel = nivel_alto or nivel_pb
        ancho, fondo = _medidas_de_cuadro(specs, tipo)
        rooms.append(RoomSpec(
            name=nombre, space_type=tipo, width_m=ancho, depth_m=fondo,
            level_ref=nivel,
            with_window=tipo not in SIN_VENTANA_COMERCIAL))
    return rooms


def _relaciones_comercial(specs: Any, familia: str,
                          rooms: List["RoomSpec"]) -> List[RelationSpec]:
    """Relaciones del §78 mapeadas a los locales generados.

    Nivel 3 = comunicado con puerta; 1 y 2 = adyacente; 0 = prohibida,
    no se genera (los avisos la recuerdan).
    """
    if specs is None:
        return []
    por_tipo: Dict[str, List[str]] = {}
    for r in rooms:
        por_tipo.setdefault(r.space_type, []).append(r.name)
    relations: List[RelationSpec] = []
    vistos: set = set()
    for rel in specs.relaciones:
        if str(rel.get("familia", "")) != familia:
            continue
        nivel = str(rel.get("nivel", ""))
        if nivel not in ("1", "2", "3"):
            continue  # «0»: relación prohibida del §78
        a, b = str(rel.get("a", "")), str(rel.get("b", ""))
        nombres_a = list(por_tipo.get(specs.tipo_de_relacion(a) or "",
                                      []))
        nombres_b = list(por_tipo.get(specs.tipo_de_relacion(b) or "",
                                      []))
        for na in nombres_a:
            for nb in nombres_b:
                if na == nb or (na, nb) in vistos or (nb, na) in vistos:
                    continue
                vistos.add((na, nb))
                if nivel == "3":
                    relations.append(RelationSpec(
                        a_name=na, b_name=nb, kind_es="Comunicado con",
                        with_door=True))
                else:
                    relations.append(RelationSpec(
                        a_name=na, b_name=nb, kind_es="Adyacente a",
                        with_door=False))
    return relations


def aplicar_programa_comercial(data: "BuildingWizardData") \
        -> Tuple[int, int]:
    """Programa mínimo del documento CC/OF (§89-90) por familia.

    «Centro comercial» carga los 13 locales del §89; «Oficinas (torre/
    corporativo)» los 16 del §90, con el bloque de trabajo en planta
    tipo para las tipologías verticales (OF-03/OF-04/OF-10). Las
    medidas de cada local salen de los cuadros MIN/REC y las
    relaciones, del §78. Devuelve (locales, relaciones).
    """
    specs = _comercial_specs()
    if specs is None:
        # Sin documento: locales base honestos (el DNA los describe)
        return _apply_leveled_program(data, ())
    try:
        from domain.comercial_specs import familia_de_uso, FAMILIA_OF
        familia = familia_de_uso(data.usage_type) or FAMILIA_OF
    except Exception:  # noqa: BLE001 — sin dominio: sin familia
        return _apply_leveled_program(data, ())
    if not data.levels:
        data.levels.append(LevelSpec(name="Planta Baja", height_m=3.2))
    tipologia = None
    etiqueta = str(getattr(data, "comercial_tipologia", "") or "")
    if etiqueta and etiqueta != COMERCIAL_SIN_TIPOLOGIA:
        tipologia = specs.tipologia_de_etiqueta(etiqueta)
    clave = str((tipologia or {}).get("clave", "") or "")
    vertical = familia == FAMILIA_OF \
        and clave in TIPOLOGIAS_VERTICALES_OF
    if vertical and len(data.levels) < 2:
        data.levels.append(LevelSpec(name="Planta 1", height_m=3.2))
    nivel_pb = data.levels[0].name
    nivel_alto = (data.levels[1].name if vertical
                  and len(data.levels) > 1 else nivel_pb)
    data.rooms = _locales_comercial(specs, familia, nivel_pb, vertical,
                                    nivel_alto)
    data.relations = _relaciones_comercial(specs, familia, data.rooms)
    return len(data.rooms), len(data.relations)


def aplicar_programa_educacion(data: "BuildingWizardData",
                               tamano: Optional[Any] = None) \
        -> Tuple[int, int]:
    """Programa paramétrico del documento educacional (§106-109).

    Primaria/secundaria generan NUM_AULAS = CEIL(alumnos / alumnos
    por aula) del §4; el círculo infantil, un aula + higiene +
    descanso por grupo del §9; el albergue, dormitorios colectivos
    de 8 plazas del §48/§51. Las medidas salen de los cuadros MIN/REC
    y las relaciones, del §98-101. Devuelve (locales, relaciones).
    """
    specs = _educacion_specs()
    if specs is None:
        # Sin documento: programas básicos honestos (el DNA los
        # describe)
        level_name = data.levels[0].name if data.levels else "Planta Baja"
        data.rooms = preset_rooms(data.usage_type, level_name)
        data.relations = suggest_relations(data)
        return len(data.rooms), len(data.relations)
    try:
        from domain.educacion_specs import familia_de_uso
        familia = familia_de_uso(data.usage_type) or ""
    except Exception:  # noqa: BLE001 — sin dominio: sin familia
        familia = ""
    if not familia:
        return _apply_leveled_program(data, ())
    tamano = tamano or _resuelve_tamano(data.usage_type,
                                        data.educacion_tamano)
    if tamano is None:
        return _apply_leveled_program(data, ())
    if not data.levels:
        data.levels.append(LevelSpec(name="Planta Baja", height_m=3.2))
    nivel_pb = data.levels[0].name
    data.rooms = _locales_educacion(specs, familia, tamano, nivel_pb)
    data.relations = _relaciones_educacion(specs, familia, data.rooms)
    return len(data.rooms), len(data.relations)


def _locales_educacion(specs: Any, familia: str, tamano: Any,
                       nivel_pb: str) -> List["RoomSpec"]:
    """Locales del programa mínimo del §106-109 por capacidad.

    El ítem repetible (aulas / aulas infantiles / dormitorios) se
    expande según la capacidad del tamaño elegido; los espacios
    exteriores y técnicos entran sin ventana (los dibuja el terreno
    o el trazado).
    """
    capacidad = int(tamano.get("capacidad", 0) or 0)
    por_aula = float(tamano.get("por_aula_o_grupo", 25.0) or 25.0)

    def _repeticiones(item: str) -> int:
        # aulas de escuela (§4/§6): NUM_AULAS = CEIL(alumnos / por aula)
        if familia in ("ESCUELA_PRIMARIA", "ESCUELA_SECUNDARIA") \
                and item == "AULAS":
            return max(1, int(-(-capacidad // max(int(por_aula), 1))))
        # círculo infantil (§9): un aula, una higiene y un descanso
        # por grupo
        if familia == "CIRCULO_INFANTIL" \
                and item in ("AULAS_INFANTILES", "HIGIENE",
                             "DESCANSO"):
            return max(1, capacidad)
        # albergue (§48/§51): dormitorios colectivos de 8 plazas
        if familia == "ALBERGUE_ESCOLAR" and item == "DORMITORIOS":
            return max(1, int(-(-capacidad // 8)))
        return 1

    def _nombre_repetido(nombre: str, indice: int) -> str:
        return nombre if indice == 0 else f"{nombre} {indice + 1}"

    rooms: List[RoomSpec] = []
    for item in specs.programa(familia):
        if not item.get("es_local", True):
            continue  # evacuación/PCI: los informa la validación
        tipo = str(item.get("space_type", ""))
        nombre = str(item.get("nombre", ""))
        ancho, fondo = _medidas_de_cuadro(specs, tipo)
        if tipo == "DINING_HALL" and capacidad > 0:
            # comedor por capacidad (REGLA_08, §36/§56): comensales
            # simultáneos (50% del §56) x 1.40 m2 (punto medio de
            # 1.20-1.80), nunca por debajo del cuadro
            poblacion = capacidad if familia != "CIRCULO_INFANTIL" \
                else int(capacidad * por_aula)
            comensales = -(-max(poblacion, 1) // 2)
            area_obj = max(comensales * 1.4, ancho * fondo)
            if area_obj > ancho * fondo:
                ancho = max(round((area_obj * 1.2) ** 0.5 * 2.0) / 2.0,
                            ancho)
                fondo = max(round(-(-area_obj / ancho * 20.0 // 1) / 20.0,
                                  2), fondo)
        ventana = tipo not in SIN_VENTANA_EDUCACION
        for indice in range(_repeticiones(str(item.get("item", "")))):
            rooms.append(RoomSpec(
                name=_nombre_repetido(nombre, indice), space_type=tipo,
                width_m=ancho, depth_m=fondo, level_ref=nivel_pb,
                with_window=ventana))
    return rooms


def _relaciones_educacion(specs: Any, familia: str,
                          rooms: List["RoomSpec"]) -> List[RelationSpec]:
    """Relaciones del §98-101 mapeadas a los locales generados.

    Nivel 3 = comunicado con puerta; 1 y 2 = adyacente; 0 = prohibida
    (flujos del §102), no se genera (los avisos la recuerdan).
    """
    if specs is None:
        return []
    por_tipo: Dict[str, List[str]] = {}
    for r in rooms:
        por_tipo.setdefault(r.space_type, []).append(r.name)
    relations: List[RelationSpec] = []
    vistos: set = set()
    for rel in specs.relaciones:
        if str(rel.get("familia", "")) != familia:
            continue
        nivel = str(rel.get("nivel", ""))
        if nivel not in ("1", "2", "3"):
            continue  # «0»: flujo prohibido del §102
        a, b = str(rel.get("a", "")), str(rel.get("b", ""))
        nombres_a = list(por_tipo.get(
            specs.tipo_de_relacion(a, familia) or "", []))
        nombres_b = list(por_tipo.get(
            specs.tipo_de_relacion(b, familia) or "", []))
        for na in nombres_a:
            for nb in nombres_b:
                if na == nb or (na, nb) in vistos or (nb, na) in vistos:
                    continue
                vistos.add((na, nb))
                if nivel == "3":
                    relations.append(RelationSpec(
                        a_name=na, b_name=nb, kind_es="Comunicado con",
                        with_door=True))
                else:
                    relations.append(RelationSpec(
                        a_name=na, b_name=nb, kind_es="Adyacente a",
                        with_door=False))
    return relations


def _apply_leveled_program(
        data: "BuildingWizardData",
        level_program: Tuple[Tuple[str, Tuple[Tuple[str, str, float,
                                               float, bool], ...]], ...]
        ) -> Tuple[int, int]:
    """Programa multi-nivel: reparte locales y añade niveles faltantes.

    Los niveles existentes se usan en su orden actual (no se renombran
    ni se toca su altura); solo se añaden los que faltan, con los
    nombres del programa y 3,2 m de altura libre.
    """
    if not data.levels:
        data.levels.append(LevelSpec(name="Planta Baja", height_m=3.0))
    rooms: List[RoomSpec] = []
    for index, (_suggested_name, program) in enumerate(level_program):
        if index < len(data.levels):
            level = data.levels[index]
        else:
            level = LevelSpec(name=_suggested_name, height_m=3.2)
            data.levels.append(level)
        for name, space_type, width, depth, window in program:
            rooms.append(RoomSpec(name=name, space_type=space_type,
                                  width_m=width, depth_m=depth,
                                  level_ref=level.name, with_window=window))
    data.rooms = rooms
    data.relations = suggest_relations(data)
    return len(data.rooms), len(data.relations)


# -- Pasos del asistente ------------------------------------------------------

BUILDING_STEPS: Tuple[Tuple[str, str, str], ...] = (
    ("1", "¿Cómo es la edificación?",
     "Ponle nombre, dime el USO SOCIAL (te sugiero locales y "
     "relaciones), las dimensiones del terreno, la FORMA EN PLANTA, el "
     "estilo arquitectónico, el TERRENO (regular o con pendiente) y la "
     "tipología constructiva."),
    ("2", "¿Qué niveles tiene?",
     "Cada fila es un piso: nombre y altura libre. La cota se calcula "
     "sola. Lo normal: «Planta Baja» de 3 m."),
    ("3", "¿Qué locales necesitas?",
     "Lista los locales con su ancho y fondo (o carga el programa del "
     "uso social) y el nivel donde van."),
    ("4", "¿Cómo se relacionan?",
     "Declara qué locales deben quedar juntos o comunicados por puerta. "
     "Si activas el pasillo, cada local recibe su puerta hacia él."),
    ("5", "Bioclimática e instalaciones",
     "Protección solar (aleros) y módulos de instalaciones: eléctrica, "
     "sanitaria, A/C, incendios, comunicaciones, gas o energía solar."),
    ("6", "Elige la variante de planta",
     "El motor genera varias distribuciones posibles (lineal, doble "
     "crujía, patio…) con su puntuación y un dibujo: elige la tuya."),
    ("7", "Resumen y generación",
     "Revisa tranquilo lo que se va a crear (locales, muros, puertas, "
     "ventanas y requerimientos). «Atrás» para corregir cualquier cosa."),
)


# -- Datos que el usuario llena ------------------------------------------------

@dataclass
class LevelSpec:
    """Un nivel de la edificación (nombre + altura libre).

    v3.32.0 (P3 del análisis Architechtures): «repeat» es el
    MULTIPLICADOR de la planta — 1 significa «esta planta una vez»
    (comportamiento previo) y N significa «planta tipo repetida N
    veces»: el trazado, los locales y las cotas se multiplican.
    """

    name: str = "Planta Baja"
    height_m: float = 3.0
    repeat: int = 1


@dataclass
class RoomSpec:
    """Un local pedido por el usuario."""

    name: str = ""
    space_type: str = "ROOM"
    width_m: float = 3.0
    depth_m: float = 3.0
    level_ref: str = "Planta Baja"
    with_window: bool = True


@dataclass
class RelationSpec:
    """Relación espacial entre dos locales (spec §8, etiqueta ES)."""

    a_name: str = ""
    b_name: str = ""
    kind_es: str = "Adyacente a"
    with_door: bool = False


def _default_levels() -> List[LevelSpec]:
    return [LevelSpec()]


def _default_rooms() -> List[RoomSpec]:
    return []


@dataclass
class BuildingWizardData:
    """Datos que el usuario llena a lo largo de los pasos."""

    # Paso 1 — general (v2.1.0 añade uso social, dimensiones y
    # tipología constructiva; v2.3.0 añade forma, estilo, terreno y
    # escaleras)
    name: str = "Mi edificación"
    usage_type: str = USAGE_TYPES[0]
    lot_width_m: float = 0.0          # 0 = sin límite de parcela
    lot_depth_m: float = 0.0          # 0 = sin límite de parcela
    construction_type: str = CONSTRUCTION_TYPES[0]
    architectural_style: str = ARCHITECTURAL_STYLES[0]
    plan_shape: str = PLAN_SHAPES[0]
    terrain_type: str = TERRAIN_TYPES[0]
    stairs_mode: str = STAIR_MODES[0]
    core_mode: str = CORE_MODES[0]
    climate: str = CLIMATE_ZONES[0]
    structural_system: str = STRUCTURAL_SYSTEMS[0]
    facade_orientation: str = ORIENTATIONS[0]
    neufert_region: str = NEUFERT_REGION_BASE   # edición regional v2.8.0
    # Catálogo maestro de viviendas (v3.23.0): tipología del §1 y
    # programa paramétrico del §7. «Programa clásico» mantiene los seis
    # locales de siempre; cualquier tipología del catálogo genera el
    # programa completo con rangos del §7.
    vivienda_tipologia: str = VIVIENDA_TIPOLOGIA_CLASICA
    vivienda_dormitorios: int = 3
    vivienda_banos: int = 2
    # Documento comercial CC/OF (v3.25.0): tipología del §1; el
    # programa mínimo del §89-90 sale del uso social elegido.
    comercial_tipologia: str = COMERCIAL_SIN_TIPOLOGIA
    # Documento educacional (v3.26.0): tamaño/capacidad del §4/§9/§48;
    # con «(programa básico)» se conservan los programas estáticos.
    educacion_tamano: str = EDU_SIN_TAMANO
    # Distribución interior (v3.2.0): ortogonal / articulada / organica
    distribucion: str = "ortogonal"
    curvatura_m: float = 1.5         # flecha de arcos y radio de radones
    semilla: int = 0                 # semilla del gesto orgánico (0 = fija)
    notes: str = ""

    # Paso 2 — niveles
    levels: List[LevelSpec] = field(default_factory=_default_levels)

    # Paso 3 — locales
    rooms: List[RoomSpec] = field(default_factory=_default_rooms)

    # Paso 4 — relaciones y vanos (v2.7.0: ventana 1,40 m = ratio de
    # luz de Neufert, ≥ 1/8 del suelo en los locales del programa)
    relations: List[RelationSpec] = field(default_factory=_default_rooms)
    corridor_enabled: bool = True
    corridor_width_m: float = 1.2
    wall_thickness_m: float = 0.2
    door_width_m: float = 0.9
    door_height_m: float = 2.1
    window_width_m: float = 1.4
    window_height_m: float = 1.2
    window_sill_m: float = 0.9
    cross_ventilation: bool = True

    # Paso 5 — bioclimática e instalaciones (v2.1.0)
    protection_solar: bool = True     # aleros sobre fachada y patio
    eaves_m: float = 0.6              # alero recomendado
    installations: List[str] = field(
        default_factory=lambda: ["Eléctrica", "Sanitaria"])

    # Concepción de espacios (v3.15.0): mobiliario según el tema, cubierta
    # según estilo/tipología y accesibilidad (rampas, barandillas).
    mobiliario: bool = True
    mobiliario_ambito: str = "auto"      # auto | domestico | social | ambos
    mobiliario_densidad: str = "estandar"  # compacto | estandar | amplio
    cubierta_tipologia: str = "auto"     # auto | plana_* | un_agua | ...
    cubierta_material: str = "auto"      # auto | teja_* | chapa | ...
    cubierta_pendiente_pct: float = 0.0  # 0 = según tipología/estilo
    cubierta_alero_m: float = 0.0        # 0 = usa eaves_m
    accesibilidad_auto: bool = True

    # -- helpers -----------------------------------------------------------
    def level_names(self) -> List[str]:
        return [lv.name for lv in self.levels]

    def room_names(self) -> List[str]:
        return [r.name for r in self.rooms]

    def rooms_of_level(self, level_name: str) -> List[RoomSpec]:
        return [r for r in self.rooms if r.level_ref == level_name]

    def room(self, name: str) -> Optional[RoomSpec]:
        for r in self.rooms:
            if r.name == name:
                return r
        return None

    def corridor_name(self, level_name: str) -> str:
        return f"Pasillo {level_name}"

    def has_door_declared(self, room_name: str) -> bool:
        return any(r.with_door and room_name in (r.a_name, r.b_name)
                   for r in self.relations)


# -- Validación paso a paso ------------------------------------------------------

def validate_step(step: int, data: BuildingWizardData) -> List[str]:
    """Devuelve la lista de problemas del paso (vacía = todo bien).

    Los mensajes hablan en primera persona de la edificación para
    acompañar sin regañar, igual que el asistente de local.
    """
    errors: List[str] = []
    if step == 0:  # ¿Cómo es?
        if not data.name.strip():
            errors.append("Necesito un nombre para la edificación "
                          "(por ejemplo, «Casa de Marta»).")
        if data.usage_type not in USAGE_TYPES:
            errors.append("Elige el uso social de la lista: con él te "
                          "sugiero locales y relaciones.")
        if data.lot_width_m < 0 or data.lot_depth_m < 0:
            errors.append("Las dimensiones de la edificación no pueden "
                          "ser negativas (0 significa «sin límite»).")
        for label, value in (("ancho", data.lot_width_m),
                             ("fondo", data.lot_depth_m)):
            if value > 500:
                errors.append(f"¿Seguro con un {label} de {value:.0f} m? "
                              "Más de 500 m suele ser un error de "
                              "tecleo.")
        if data.construction_type not in CONSTRUCTION_TYPES:
            errors.append("Elige la tipología constructiva de la lista.")
        if data.architectural_style not in ARCHITECTURAL_STYLES:
            errors.append("Elige el estilo arquitectónico de la lista.")
        if data.plan_shape not in PLAN_SHAPES:
            errors.append("Elige la forma en planta de la lista: guía el "
                          "motor de variantes.")
        if data.distribucion not in DISTRIBUCION_CODES:
            errors.append("Elige la distribución interior de la lista.")
        if not 0.3 <= data.curvatura_m <= 4.0:
            errors.append("La curvatura orgánica debe estar entre 0,3 y "
                          "4,0 m.")
        if data.semilla < 0:
            errors.append("La semilla del gesto orgánico no puede ser "
                          "negativa.")
        if data.terrain_type not in TERRAIN_TYPES:
            errors.append("Elige el tipo de terreno de la lista.")
        if data.stairs_mode not in STAIR_MODES:
            errors.append("Elige cuándo colocar escaleras de la lista.")
        if data.core_mode not in CORE_MODES:
            errors.append("Elige cuándo colocar el núcleo rígido de la "
                          "lista.")
        if data.climate not in CLIMATE_ZONES:
            errors.append("Elige una zona climática de la lista: así "
                          "oriento ventanas y ventilación.")
        if data.structural_system not in STRUCTURAL_SYSTEMS:
            errors.append("Elige el sistema estructural de la lista.")
        if data.facade_orientation not in ORIENTATIONS:
            errors.append("Elige hacia dónde mira la fachada principal.")
        if data.neufert_region not in (
                code for code, _label in neufert_region_choices()):
            errors.append("Elige la edición regional de Neufert de la "
                          "lista (o la base del libro).")
        if data.vivienda_tipologia not in vivienda_tipologia_choices():
            errors.append("Elige la tipología de vivienda del catálogo "
                          "(o el programa clásico).")
        if data.usage_type in USOS_COMERCIALES and \
                data.comercial_tipologia not in comercial_tipologia_choices():
            errors.append("Elige la tipología del documento comercial "
                          "CC/OF o déjala sin tipología concreta.")
        if data.usage_type in USOS_EDUCATIVOS and \
                _resuelve_tamano(data.usage_type,
                                 data.educacion_tamano) is None \
                and data.educacion_tamano != EDU_SIN_TAMANO:
            errors.append("Elige un tamaño del documento educacional "
                          "que corresponda al uso elegido, o el "
                          "programa básico.")
        if not 1 <= int(data.vivienda_dormitorios) <= 6:
            errors.append("Los dormitorios de la vivienda van de 1 a 6: "
                          "el catálogo ajusta el programa con ellos.")
        if not 1 <= int(data.vivienda_banos) <= 4:
            errors.append("Los baños de la vivienda van de 1 a 4.")
    elif step == 1:  # ¿Niveles?
        if not data.levels:
            errors.append("Necesito al menos un nivel (por ejemplo, "
                          "«Planta Baja»).")
        names = [lv.name.strip().lower() for lv in data.levels]
        for lv in data.levels:
            if not lv.name.strip():
                errors.append("Cada nivel necesita un nombre.")
                break
            if names.count(lv.name.strip().lower()) > 1:
                errors.append(f"Hay niveles con el mismo nombre "
                              f"(«{lv.name.strip()}»): renombra alguno.")
                break
            if lv.height_m <= 0:
                errors.append(f"La altura del nivel «{lv.name.strip()}» "
                              "debe ser mayor que cero metros.")
            elif lv.height_m > 20:
                errors.append(f"¿Seguro? «{lv.name.strip()}» mide "
                              f"{lv.height_m:.1f} m de altura libre; más "
                              "de 20 m suele ser un error de tecleo.")
    elif step == 2:  # ¿Locales?
        if not data.rooms:
            errors.append("Añade al menos un local, o carga un programa "
                          "tipo para partir de una base razonable.")
        names = [r.name.strip().lower() for r in data.rooms]
        levels = set(data.level_names())
        for r in data.rooms:
            if not r.name.strip():
                errors.append("Cada local necesita un nombre.")
                break
            if names.count(r.name.strip().lower()) > 1:
                errors.append(f"Hay locales repetidos con el nombre "
                              f"«{r.name.strip()}»: los nombres deben ser "
                              "únicos para poder relacionarlos.")
                break
            if r.level_ref not in levels:
                errors.append(f"El local «{r.name.strip()}» apunta al "
                              f"nivel «{r.level_ref}», que no existe en "
                              "el paso 2.")
                break
            if r.width_m <= 0 or r.depth_m <= 0:
                errors.append(f"El local «{r.name.strip()}» necesita "
                              "ancho y fondo mayores que cero metros.")
                break
            if r.width_m > 500 or r.depth_m > 500:
                errors.append(f"¿Seguro con las medidas de "
                              f"«{r.name.strip()}»? Más de 500 m suele "
                              "ser un error de tecleo.")
                break
            if data.corridor_enabled and r.name.strip().lower().startswith(
                    "pasillo "):
                errors.append(f"El nombre «{r.name.strip()}» choca con "
                              "el pasillo automático: renombra el local "
                              "o desactiva el pasillo en el paso 4.")
                break
    elif step == 3:  # ¿Relaciones y vanos?
        names = set(data.room_names())
        for rel in data.relations:
            if not rel.a_name or not rel.b_name:
                errors.append("Cada relación necesita dos locales "
                              "elegidos.")
                break
            if rel.a_name == rel.b_name:
                errors.append("Un local no puede relacionarse consigo "
                              "mismo.")
                break
            if rel.a_name not in names or rel.b_name not in names:
                errors.append(f"La relación «{rel.a_name} — {rel.b_name}» "
                              "menciona un local que no está en la "
                              "lista del paso 3.")
                break
            if rel.kind_es not in KIND_BY_LABEL:
                errors.append(f"Tipo de relación desconocido: "
                              f"«{rel.kind_es}».")
                break
        if data.corridor_enabled:
            if data.corridor_width_m <= 0:
                errors.append("Si activas el pasillo, su ancho debe ser "
                              "mayor que cero.")
            elif data.corridor_width_m < max(data.door_width_m, 0.9):
                errors.append("El pasillo queda más estrecho que la "
                              "puerta de entrada: sube su ancho (1,2 m "
                              "es lo cómodo).")
        if data.wall_thickness_m <= 0:
            errors.append("El espesor de los muros debe ser positivo.")
        if data.door_width_m <= 0 or data.door_height_m <= 0:
            errors.append("Las puertas necesitan ancho y alto positivos.")
        if data.window_width_m <= 0 or data.window_height_m <= 0:
            errors.append("Las ventanas necesitan ancho y alto "
                          "positivos.")
        if data.window_sill_m < 0:
            errors.append("El antepecho de las ventanas no puede ser "
                          "negativo.")
        min_height = min((lv.height_m for lv in data.levels), default=0.0)
        if min_height > 0:
            if data.door_height_m > min_height:
                errors.append("Alguna puerta no cabe: mide más que la "
                              "altura libre del nivel más bajo.")
            if data.window_sill_m + data.window_height_m > min_height:
                errors.append("Las ventanas no caben: antepecho + alto "
                              "superan la altura libre del nivel más "
                              "bajo.")
        rooms_for_fit = [r for r in data.rooms
                         if r.width_m > 0 and r.depth_m > 0]
        if rooms_for_fit:
            narrowest = min(r.width_m for r in rooms_for_fit)
            if data.door_width_m > narrowest:
                errors.append(f"La puerta ({data.door_width_m:.2f} m) no "
                              f"cabe en el local más estrecho "
                              f"({narrowest:.2f} m): baja su ancho o "
                              "agranda ese local.")
            for r in rooms_for_fit:
                if r.with_window and data.window_width_m > r.width_m:
                    errors.append(f"La ventana ({data.window_width_m:.2f} "
                                  f"m) no cabe en la fachada de "
                                  f"«{r.name}» ({r.width_m:.2f} m).")
                    break
    elif step == 4:  # bioclimática e instalaciones
        if data.eaves_m < 0:
            errors.append("El alero no puede ser negativo.")
        elif data.eaves_m > 2.5:
            errors.append("¿Seguro? Un alero de más de 2,5 m es poco "
                          "práctico; 0,6 m es lo habitual.")
        unknown = [name for name in data.installations
                   if name not in INSTALLATION_MODULES]
        if unknown:
            errors.append("Hay módulos de instalación desconocidos: "
                          + ", ".join(unknown) + ".")
    # Paso 5 (variantes) y paso 6 (resumen) no bloquean: siempre se
    # puede revisar; si no hay variante elegida, el motor usa la mejor
    # puntuada.
    return errors


def data_from_values(step: int, values: Dict[str, Any],
                     data: BuildingWizardData) -> List[str]:
    """Vuelca un dict del formulario en «data» y devuelve errores.

    Solo convierte los campos numéricos simples de los pasos 1 y 4;
    los niveles, locales y relaciones los gestiona la GUI con árboles
    (ver templates en building_fields()).
    """
    conversion_errors: List[str] = []
    float_fields = {
        0: {"lot_width_m": "Ancho máximo de la edificación",
            "lot_depth_m": "Fondo máximo de la edificación"},
        3: {"corridor_width_m": "Ancho del pasillo",
            "wall_thickness_m": "Espesor de los muros",
            "door_width_m": "Ancho de las puertas",
            "door_height_m": "Alto de las puertas",
            "window_width_m": "Ancho de las ventanas",
            "window_height_m": "Alto de las ventanas",
            "window_sill_m": "Antepecho"},
        4: {"eaves_m": "Alero"},
    }.get(step, {})
    for key, label in float_fields.items():
        if key in values and values[key] not in ("", None):
            try:
                setattr(data, key,
                        parse_float_es(str(values[key]), label))
            except ValueError as exc:
                conversion_errors.append(str(exc))
    if step == 0:
        data.name = (values.get("name") or "").strip()
        data.usage_type = values.get("usage_type") or data.usage_type
        data.construction_type = (values.get("construction_type")
                                  or data.construction_type)
        data.architectural_style = (values.get("architectural_style")
                                    or data.architectural_style)
        data.plan_shape = (values.get("plan_shape")
                           or data.plan_shape)
        raw_dist = (values.get("distribucion") or "").strip()
        if raw_dist:
            data.distribucion = (raw_dist if raw_dist in DISTRIBUCION_CODES
                                 else distribution_code(raw_dist))
        try:
            raw_curv = str(values.get("curvatura_m") or "").strip()
            if raw_curv:
                data.curvatura_m = float(raw_curv.replace(",", "."))
        except (TypeError, ValueError):
            pass
        try:
            raw_seed = str(values.get("semilla") or "").strip()
            if raw_seed:
                data.semilla = int(float(raw_seed.replace(",", ".")))
        except (TypeError, ValueError):
            pass
        data.terrain_type = (values.get("terrain_type")
                             or data.terrain_type)
        data.stairs_mode = (values.get("stairs_mode")
                            or data.stairs_mode)
        data.core_mode = (values.get("core_mode")
                          or data.core_mode)
        data.climate = values.get("climate") or data.climate
        data.structural_system = (values.get("structural_system")
                                  or data.structural_system)
        data.facade_orientation = (values.get("facade_orientation")
                                   or data.facade_orientation)
        data.neufert_region = (values.get("neufert_region")
                               or data.neufert_region or NEUFERT_REGION_BASE)
        raw_viv = str(values.get("vivienda_tipologia") or "").strip()
        if raw_viv:
            data.vivienda_tipologia = raw_viv
        raw_com = str(values.get("comercial_tipologia") or "").strip()
        if raw_com:
            data.comercial_tipologia = raw_com
        raw_edu = str(values.get("educacion_tamano") or "").strip()
        if raw_edu:
            data.educacion_tamano = raw_edu
        try:
            raw_dorm = str(values.get("vivienda_dormitorios") or "").strip()
            if raw_dorm:
                data.vivienda_dormitorios = int(
                    float(raw_dorm.replace(",", ".")))
        except (TypeError, ValueError):
            pass
        try:
            raw_ban = str(values.get("vivienda_banos") or "").strip()
            if raw_ban:
                data.vivienda_banos = int(float(raw_ban.replace(",", ".")))
        except (TypeError, ValueError):
            pass
        data.notes = (values.get("notes") or "").strip()
    elif step == 3:
        data.corridor_enabled = bool(values.get("corridor_enabled"))
        data.cross_ventilation = bool(values.get("cross_ventilation"))
    elif step == 4:
        data.protection_solar = bool(values.get("protection_solar"))
        chosen = values.get("installations")
        if chosen is not None:
            data.installations = [name for name in INSTALLATION_MODULES
                                  if name in chosen]
    return conversion_errors


# -- Motor de trazado determinista ----------------------------------------------
# Layout en fila: los locales quedan pegados de lado a lado (partición
# compartida) con la fachada hacia y=0; el pasillo opcional corre por
# DETRÁS de la fachada (y negativo) para que cada local lo toque sin
# importar su fondo. Todo axis-aligned y determinista.

@dataclass
class PlacedRoom:
    """Local ya colocado en el plano del nivel."""

    name: str
    space_type: str
    level: str
    x: float
    y: float
    w: float
    d: float
    with_window: bool = False
    is_corridor: bool = False
    floor_rise_m: float = 0.0   # cota propia del local (terreno irregular)

    @property
    def rect(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.d)

    def boundary(self) -> List[Tuple[float, float]]:
        return [(self.x, self.y), (self.x + self.w, self.y),
                (self.x + self.w, self.y + self.d),
                (self.x, self.y + self.d)]

    def area_m2(self) -> float:
        return self.w * self.d


def order_rooms_for_level(rooms: Sequence[RoomSpec],
                          relations: Sequence[RelationSpec]) -> List[RoomSpec]:
    """Ordena los locales de un nivel siguiendo las relaciones.

    Recorrido en anchura desde el primer local de la lista: los vecinos
    declarados van quedando consecutivos (así comparten partición y la
    puerta declarada tiene muro donde apoyarse). El resto conserva el
    orden de la lista. Determinista: los vecinos se visitan por orden
    de lista.
    """
    if not rooms:
        return []
    index_of = {r.name: i for i, r in enumerate(rooms)}
    neighbors: Dict[str, List[str]] = {r.name: [] for r in rooms}
    for rel in relations:
        a, b = rel.a_name, rel.b_name
        if a in index_of and b in index_of:
            neighbors[a].append(b)
            neighbors[b].append(a)
    ordered: List[RoomSpec] = []
    seen: set = set()

    def visit(start: RoomSpec) -> None:
        queue = [start.name]
        seen.add(start.name)
        while queue:
            current = queue.pop(0)
            ordered.append(rooms[index_of[current]])
            for nb in sorted(neighbors.get(current, []),
                             key=lambda n: index_of.get(n, 0)):
                if nb in index_of and nb not in seen:
                    seen.add(nb)
                    queue.append(nb)

    for room in rooms:
        if room.name not in seen:
            visit(room)
    return ordered


def rect_segments(pr: PlacedRoom) -> List[Tuple[Tuple[float, float],
                                                Tuple[float, float]]]:
    """Los 4 lados del local, sentido horario desde (x, y)."""
    x, y, w, d = pr.x, pr.y, pr.w, pr.d
    return [
        ((x, y), (x + w, y)),          # frente (fachada o pasillo)
        ((x + w, y), (x + w, y + d)),  # derecha
        ((x + w, y + d), (x, y + d)),  # fondo (exterior)
        ((x, y + d), (x, y)),          # izquierda
    ]


def merge_walls(tagged: Iterable[Tuple[Tuple[Tuple[float, float],
                                        Tuple[float, float]], str]],
                tol: float = 1e-6) -> List[Dict[str, Any]]:
    """Fusiona segmentos colineales → UN muro por pared compartida.

    Devuelve dicts con start/end normalizados (horizontal: de izquierda
    a derecha; vertical: de abajo arriba), «length» y «sources»: qué
    locales/corredor contribuyen (para decidir portantes y particiones).
    """
    buckets: Dict[Tuple[str, float], List[Tuple[float, float, str]]] = {}
    for (start, end), source in tagged:
        (x1, y1), (x2, y2) = start, end
        if abs(y1 - y2) <= tol:  # horizontal
            key = ("H", round(y1, 3))
            lo, hi = min(x1, x2), max(x1, x2)
        elif abs(x1 - x2) <= tol:  # vertical
            key = ("V", round(x1, 3))
            lo, hi = min(y1, y2), max(y1, y2)
        else:  # no debería pasar (todo es axis-aligned)
            key = ("?", 0.0)
            lo, hi = 0.0, 0.0
        buckets.setdefault(key, []).append((lo, hi, source))

    walls: List[Dict[str, Any]] = []
    for (orient, fixed), intervals in sorted(buckets.items(),
                                             key=lambda kv: (kv[0][0],
                                                             kv[0][1])):
        intervals.sort(key=lambda t: (t[0], t[1]))
        merged: List[List[Any]] = []
        for lo, hi, source in intervals:
            if merged and lo <= merged[-1][1] + tol:
                if hi > merged[-1][1]:
                    merged[-1][1] = hi
                if source not in merged[-1][2]:
                    merged[-1][2].append(source)
            else:
                merged.append([lo, hi, [source]])
        for lo, hi, sources in merged:
            if hi - lo <= tol:
                continue
            if orient == "H":
                start, end = (lo, fixed), (hi, fixed)
            else:
                start, end = (fixed, lo), (fixed, hi)
            walls.append({"start": start, "end": end,
                          "length": round(hi - lo, 6),
                          "sources": sources})
    return walls


@dataclass
class OpeningPlacement:
    """Un vano ya resuelto sobre un muro fusionado."""

    kind: str                      # DOOR | WINDOW
    width_m: float
    height_m: float
    offset_m: float                # desde el inicio del muro fusionado
    sill_height_m: float = 0.0
    note: str = ""                 # «entre Sala y Cocina», «al pasillo»…
    wall_index: int = -1           # índice del muro en LevelLayout.walls

    @property
    def is_door(self) -> bool:
        return self.kind == "DOOR"


@dataclass
class LevelLayout:
    """Resultado del trazado de un nivel."""

    level_name: str
    rooms: List[PlacedRoom]
    corridor: Optional[PlacedRoom]
    walls: List[Dict[str, Any]]
    doors: List[OpeningPlacement]
    windows: List[OpeningPlacement]
    advisories: List[str] = field(default_factory=list)
    # Pasillos adicionales de las formas compuestas (espina, puente,
    # eslabón, pasillo trasero): se dibujan y cuentan como circulación.
    extra_corridors: List[PlacedRoom] = field(default_factory=list)

    @property
    def all_rooms(self) -> List[PlacedRoom]:
        return (self.rooms + ([self.corridor] if self.corridor else [])
                + self.extra_corridors)

    def total_area_m2(self) -> float:
        return sum(pr.area_m2() for pr in self.all_rooms)


def _wall_axis_start(wall: Dict[str, Any]) -> float:
    """Coordenada a lo largo del eje donde empieza el muro fusionado."""
    start = wall["start"]
    end = wall["end"]
    # Horizontal: el eje es x; vertical: el eje es y. start ya queda
    # normalizado al extremo menor por merge_walls.
    return start[0] if abs(start[1] - end[1]) <= 1e-6 else start[1]


def _clamp_offset(wall: Dict[str, Any], offset: float,
                  opening_len: float) -> float:
    room = wall["length"] - opening_len
    return max(0.0, min(offset, room)) if room > 0 else 0.0


def _wall_for_interval(walls: List[Dict[str, Any]], orientation: str,
                       fixed: float, lo: float, hi: float,
                       tol: float = 1e-3
                       ) -> Tuple[Optional[Dict[str, Any]], int]:
    """Busca el muro fusionado que contiene el intervalo pedido.

    Devuelve (muro, índice) para que cada vano sepa exactamente en qué
    muro va encastrado (la posición del muro en LevelLayout.walls es
    la misma que en el plan y en el proyecto).
    """
    for index, wall in enumerate(walls):
        start, end = wall["start"], wall["end"]
        if orientation == "H" and abs(start[1] - fixed) <= tol:
            axis = (start[0], end[0])
        elif orientation == "V" and abs(start[0] - fixed) <= tol:
            axis = (start[1], end[1])
        else:
            continue
        if axis[0] <= lo + tol and hi <= axis[1] + tol:
            return wall, index
    return None, -1


def _partition_wall(walls: List[Dict[str, Any]], x: float,
                    min_len: float) -> Optional[Dict[str, Any]]:
    """Partición vertical en x que arranca en y=0 y cubre min_len."""
    wall, _index = _wall_for_interval(walls, "V", x, 0.0, min_len)
    return wall


def _place_door(walls: List[Dict[str, Any]], data: BuildingWizardData,
                orientation: str, fixed: float, lo: float, hi: float,
                note: str, entrance: bool = False) -> Optional[OpeningPlacement]:
    wall, wall_index = _wall_for_interval(walls, orientation, fixed, lo, hi)
    if wall is None:
        return None
    span = hi - lo
    width = data.door_width_m
    if width > span + 1e-9:
        return None
    axis_start = _wall_axis_start(wall)
    # offset absoluto dentro del muro fusionado:
    offset = _clamp_offset(wall, (lo + (span - width) / 2.0) - axis_start,
                           width)
    return OpeningPlacement(kind="DOOR", width_m=width,
                            height_m=data.door_height_m,
                            offset_m=offset, note=note,
                            sill_height_m=0.0, wall_index=wall_index)


def _place_window(walls: List[Dict[str, Any]], data: BuildingWizardData,
                  fixed_y: float, lo: float, hi: float,
                  note: str) -> Optional[OpeningPlacement]:
    wall, wall_index = _wall_for_interval(walls, "H", fixed_y, lo, hi)
    if wall is None:
        return None
    span = hi - lo
    width = data.window_width_m
    if width > span + 1e-9:
        return None
    axis_start = _wall_axis_start(wall)
    offset = _clamp_offset(wall, (lo + (span - width) / 2.0) - axis_start,
                           width)
    return OpeningPlacement(kind="WINDOW", width_m=width,
                            height_m=data.window_height_m,
                            offset_m=offset,
                            sill_height_m=data.window_sill_m, note=note,
                            wall_index=wall_index)


def build_layout(data: BuildingWizardData,
                 with_core: bool = False) -> Tuple[List[LevelLayout],
                                                   List[str]]:
    """Traza TODOS los niveles de forma determinista.

    Devuelve (layouts, avisos): los avisos son amables y NO bloquean
    (por ejemplo, una puerta declarada entre locales que quedaron sin
    pared común se omite y se explica). Con «with_core» (v2.5.0) cada
    nivel con locales recibe su NÚCLEO RÍGIDO en la esquina frontal
    derecha de la fila.
    """
    layouts: List[LevelLayout] = []
    advisories: List[str] = []
    entrance_done = False
    first_roomy = True
    rise = terrain_rise_m(data.terrain_type)

    for level in data.levels:
        rooms = order_rooms_for_level(data.rooms_of_level(level.name),
                                      data.relations)
        if not rooms:
            continue
        # Escalera y desnivel (v2.3.0): la escalera se coloca entre los
        # dos grupos de la planta (o al final) y los locales de detrás
        # quedan a la cota que impone el terreno.
        with_stair = stairs_wanted(data) and (rise > 0.0 or first_roomy)
        ordered = list(rooms)
        split_at = len(ordered)
        if rise > 0.0:
            target = 0.6 * sum(r.width_m for r in ordered)
            acc = 0.0
            for index, room in enumerate(ordered[:len(ordered) - 1]):
                acc += room.width_m
                split_at = index + 1
                if acc >= target:
                    break
            split_at = max(1, split_at)
        if with_stair:
            _steps, run = stair_geometry(_stair_rise_for(data),
                                         data.usage_type)
            ordered.insert(split_at, _stair_spec(level.name, run, data.usage_type))
            split_at += 1
        if with_core:
            # Núcleo rígido al final de la fila: esquina frontal
            # derecha, junto a la fachada principal (v2.5.0).
            ordered.append(_core_spec(level.name))
        placed: List[PlacedRoom] = []
        x = 0.0
        # Distribución articulada/orgánica (v3.2.0): fondos escalonados
        # por local — la fachada trasera «juega» en profundidad. Solo
        # CRECE (nunca reduce áreas) y no toca escalera ni núcleo.
        rng_org = random.Random(((data.semilla or 0) + 20260927) * 31
                                + sum(ord(c) for c in level.name))
        articulated = False
        for index, room in enumerate(ordered):
            depth = room.depth_m
            if (data.distribucion in ("articulada", "organica")
                    and room.space_type not in (STAIR_TYPE, CORE_TYPE)
                    and depth >= 2.4):
                bump = rng_org.choice((0.0, 0.5, 0.9, 1.4)) \
                    * min(1.0, depth * 0.22)
                if bump > 0.05:
                    depth += bump
                    articulated = True
            placed.append(PlacedRoom(
                name=room.name, space_type=room.space_type,
                level=level.name, x=x, y=0.0, w=room.width_m,
                d=depth, with_window=room.with_window,
                floor_rise_m=(rise if index >= split_at else 0.0)
                if room.space_type != CORE_TYPE else 0.0))
            x += room.width_m
        total_w = x
        first_roomy = False
        corridor: Optional[PlacedRoom] = None
        if data.corridor_enabled:
            corridor = PlacedRoom(
                name=data.corridor_name(level.name),
                space_type=CORRIDOR_TYPE, level=level.name, x=0.0,
                y=-data.corridor_width_m, w=total_w,
                d=data.corridor_width_m, with_window=False,
                is_corridor=True)

        tagged: List[Tuple[Tuple[Tuple[float, float], Tuple[float, float]],
                           str]] = []
        for pr in placed + ([corridor] if corridor else []):
            for seg in rect_segments(pr):
                tagged.append((seg, pr.name))
        walls = merge_walls(tagged)

        level_advisories: List[str] = []
        if articulated:
            mode_name = distribution_label(
                data.distribucion).split(" (")[0].lower()
            level_advisories.append(
                "Fondos escalonados por la distribución " + mode_name + ": "
                "la fachada trasera juega en profundidad y las áreas "
                "solo crecen.")
        doors: List[OpeningPlacement] = []
        windows: List[OpeningPlacement] = []

        # 1) Puertas declaradas entre locales que compartan partición
        #    (conexiones EXTRA: el pasillo ya garantiza el acceso).
        position_of = {pr.name: i for i, pr in enumerate(placed)}
        for rel in data.relations:
            if not rel.with_door:
                continue
            if rel.a_name not in position_of or \
                    rel.b_name not in position_of:
                continue  # otro nivel (o no existe) — ya avisado en paso 3
            ia, ib = position_of[rel.a_name], position_of[rel.b_name]
            if abs(ia - ib) != 1:
                level_advisories.append(
                    f"La puerta «{rel.a_name} — {rel.b_name}» se omite: "
                    "esos locales no quedaron pegados en la fila; el "
                    "pasillo los comunica igualmente.")
                continue
            a, b = placed[min(ia, ib)], placed[max(ia, ib)]
            part_x = a.x + a.w  # pared entre ambos
            min_len = min(a.d, b.d)
            door = _place_door(walls, data, "V", part_x, 0.0, min_len,
                               f"entre {a.name} y {b.name}")
            if door is not None:
                doors.append(door)
            else:
                level_advisories.append(
                    f"La puerta «{rel.a_name} — {rel.b_name}» no cabe en "
                    f"la pared compartida de {min_len:.2f} m: revisa el "
                    "ancho de la puerta o el fondo de esos locales.")

        # 2) Puertas automáticas: con pasillo, CADA local recibe la suya
        #    (nadie queda aislado; las declaradas son extra). Sin
        #    pasillo: entrada por el primero y enfilada con el anterior.
        for position_i, pr in enumerate(placed):
            if data.corridor_enabled:
                door = _place_door(walls, data, "H", 0.0, pr.x,
                                   pr.x + pr.w, f"{pr.name} → pasillo")
            elif position_i == 0:
                # Sin pasillo: el primer local recibe la entrada al frente.
                door = _place_door(walls, data, "H", 0.0, pr.x,
                                   pr.x + pr.w, f"entrada por {pr.name}")
            else:
                # Enfilada: puerta con el local anterior.
                prev = placed[position_i - 1]
                part_x = prev.x + prev.w
                min_len = min(prev.d, pr.d)
                door = _place_door(walls, data, "V", part_x, 0.0,
                                   min_len,
                                   f"entre {prev.name} y {pr.name}")
            if door is not None:
                doors.append(door)
            else:
                level_advisories.append(
                    f"«{pr.name}» quedó sin puerta posible: revisa "
                    "anchos (pasillo, puerta o fondo del local).")

        # 3) Puerta de entrada del nivel inferior (exterior).
        #    Con pasillo: en el extremo derecho del pasillo. Sin
        #    pasillo la entrada ya la puso la enfilada (primer local),
        #    así que aquí no se repite.
        if not entrance_done and corridor is not None:
            door = _place_door(walls, data, "V", total_w,
                               corridor.y, corridor.y + corridor.d,
                               "entrada principal", entrance=True)
            if door is not None:
                doors.append(door)
                entrance_done = True
            else:
                level_advisories.append(
                    "La puerta de entrada no cabe: sube el ancho del "
                    "pasillo o baja el ancho de las puertas.")

        # 4) Ventanas en el fondo exterior de cada local que las pida.
        for pr in placed:
            if not pr.with_window:
                continue
            window = _place_window(walls, data, pr.y + pr.d, pr.x,
                                   pr.x + pr.w,
                                   f"{pr.name} → fachada")
            if window is not None:
                windows.append(window)
            else:
                level_advisories.append(
                    f"La ventana de «{pr.name}» no cabe en su fachada "
                    f"de {pr.w:.2f} m: revisa el ancho de las ventanas.")

        if rise > 0.0:
            risen = sum(1 for pr in placed if pr.floor_rise_m > 0.0)
            level_advisories.append(
                f"Por la pendiente del terreno, {risen} local(es) de "
                f"«{level.name}» quedan a la cota +{rise:.2f} m"
                + ("; la escalera los une con el resto de la planta"
                   if with_stair else "") + ".")

        layouts.append(LevelLayout(
            level_name=level.name, rooms=placed, corridor=corridor,
            walls=walls, doors=doors, windows=windows,
            advisories=level_advisories))

    if not layouts:
        advisories.append("No hay locales para trazar: añade locales en "
                          "el paso 3.")
    return layouts, advisories


def _is_partition(wall: Dict[str, Any]) -> bool:
    """Partición vertical entre EXACTAMENTE dos locales de la fila.

    Solo los muros VERTICALES pueden separar dos locales vecinos; un
    muro horizontal fusionado (p. ej. dos locales de igual fondo que
    comparten fachada trasera) sigue siendo fachada exterior, no
    partición.
    """
    start, end = wall["start"], wall["end"]
    is_vertical = abs(start[0] - end[0]) <= 1e-6
    if not is_vertical:
        return False
    sources = [s for s in wall.get("sources", [])]
    if len(sources) != 2:
        return False
    return CORRIDOR_TYPE not in (sources[0], sources[1]) and all(
        not s.startswith("Pasillo ") for s in sources)


def structural_flag(wall: Dict[str, Any],
                    system: str) -> bool:
    """¿Muro portante? Regla explicable según el sistema elegido."""
    if system not in ("Muros portantes", "Mixto (pórtico + muros)"):
        return False
    return not _is_partition(wall)


# -- Motor de VARIANTES de planta (v2.1.0) ---------------------------------
# Tres esquemas tipológicos (por nivel), cada uno con su espejo:
#
#   lineal        — locales en fila sobre la fachada + pasillo detrás
#                   (el trazado clásico de build_layout).
#   doble_crujia  — dos filas de locales a ambos lados de un pasillo
#                   central recto (fachada frontal y posterior).
#   patio         — dos crujías alrededor de un patio central que da
#                   luz y aire (la galería del trópico).
#
# Todo axis-aligned, determinista y explicable: cada variante trae sus
# métricas (adyacencias, luz, compacidad, ventilación, clima y si cabe
# en las dimensiones pedidas) y una puntuación 0–100.

SCHEME_LABELS: Dict[str, str] = {
    "lineal": "Lineal con pasillo posterior",
    "doble_crujia": "Doble crujía con pasillo central",
    "patio": "Patio central",
    "en_L": "En L (ala lateral)",
    "en_T": "En T (espina central)",
    "en_U": "En U (patio trasero)",
    "en_H": "En H (doble barra y puente)",
    "en_cruz": "En cruz (brazos cruzados)",
    "articulada": "Articulada en eslabones",
    "en_L_patio": "En L con patio abrazado",
    "en_T_patio": "En T con patio central",
    "en_H_patio": "En H con patio central",
    "en_cruz_patio": "En cruz con patio central",
    "articulada_patio": "Articulada con patio central",
}

SCHEME_DESCRIPTIONS: Dict[str, str] = {
    "lineal": "Todos los locales en una fila sobre la fachada, con el "
              "pasillo por detrás. Ideal para parcelas largas y "
              "estrechas; fachada única hacia el exterior.",
    "doble_crujia": "Dos filas de locales a ambos lados de un pasillo "
                    "central recto. Muy compacta y con dos frentes de "
                    "fachada: excelente para la ventilación cruzada.",
    "patio": "Dos crujías alrededor de un patio central que ilumina y "
             "ventila todo el edificio, con puertas a la galería del "
             "patio. La respuesta clásica de la arquitectura tropical.",
    "en_L": "Barra frontal con ala perpendicular hacia el fondo: abraza "
            "un patio lateral y deja zona libre en el lote.",
    "en_T": "Cuerpo frontal con espina central de circulación: separa "
            "lo público de lo de servicio y crece por la espina.",
    "en_U": "Dos alas que abrazan un patio trasero entre ellas: el "
            "recreo, el sol o la carga quedan dentro del edificio.",
    "en_H": "Dos barras unidas por un puente de pasillo: mucha fachada, "
            "ventilación cruzada y núcleo central claro.",
    "en_cruz": "Barra frontal, barra trasera y espina con locales a los "
               "lados: los brazos se cruzan en el núcleo; clásico de "
               "hospitales y escuelas.",
    "articulada": "Dos bloques desfasados unidos por un eslabón de "
                  "pasillo largo: crece por etapas y se adapta al "
                  "terreno.",
    "en_L_patio": "La L abraza un patio en su esquina interior: luz y "
                   "verde justo donde la barra encuentra a la ala.",
    "en_T_patio": "La espina de circulación se vuelve patio central: "
                   "las dos alas de locales miran a un jardín interior "
                   "y la entrada llega por el patio.",
    "en_H_patio": "Las dos barras de la H comparten un patio central "
                   "entre ellas: los locales pegados tienen puerta a su "
                   "galería.",
    "en_cruz_patio": "Los brazos de la cruz nacen de un patio central: "
                      "circulación abierta, luz y ventilación en el "
                      "corazón del edificio.",
    "articulada_patio": "El eslabón entre bloques se vuelve patio: "
                         "crece por etapas alrededor de un espacio "
                         "abierto compartido.",
}


# Afinidad entre la FORMA elegida en el paso 1 y cada esquema del
# motor (0–1): guía la puntuación sin excluir ninguna variante.
SHAPE_SCHEME_AFFINITY: Dict[str, Dict[str, float]] = {
    "Rectangular": {
        "lineal": 0.95, "doble_crujia": 1.0, "patio": 0.85,
        "en_L": 0.45, "en_T": 0.55, "en_U": 0.6, "en_H": 0.55,
        "en_cruz": 0.55, "articulada": 0.4, "en_L_patio": 0.5,
        "en_T_patio": 0.6, "en_H_patio": 0.6, "en_cruz_patio": 0.6,
        "articulada_patio": 0.45},
    "Cuadrada": {
        "lineal": 0.45, "doble_crujia": 1.0, "patio": 0.95,
        "en_L": 0.4, "en_T": 0.55, "en_U": 0.7, "en_H": 0.8,
        "en_cruz": 0.7, "articulada": 0.4, "en_L_patio": 0.5,
        "en_T_patio": 0.65, "en_H_patio": 0.85, "en_cruz_patio": 0.75,
        "articulada_patio": 0.45},
    "Lineal (barra)": {
        "lineal": 1.0, "doble_crujia": 0.7, "patio": 0.55,
        "en_L": 0.6, "en_T": 0.45, "en_U": 0.45, "en_H": 0.5,
        "en_cruz": 0.45, "articulada": 0.4, "en_L_patio": 0.55,
        "en_T_patio": 0.5, "en_H_patio": 0.5, "en_cruz_patio": 0.45,
        "articulada_patio": 0.4},
    "En L": {
        "lineal": 0.55, "doble_crujia": 0.5, "patio": 0.6,
        "en_L": 1.0, "en_T": 0.6, "en_U": 0.7, "en_H": 0.55,
        "en_cruz": 0.55, "articulada": 0.55, "en_L_patio": 0.95,
        "en_T_patio": 0.6, "en_H_patio": 0.55, "en_cruz_patio": 0.55,
        "articulada_patio": 0.5},
    "En T": {
        "lineal": 0.5, "doble_crujia": 0.55, "patio": 0.55,
        "en_L": 0.6, "en_T": 1.0, "en_U": 0.65, "en_H": 0.7,
        "en_cruz": 0.75, "articulada": 0.5, "en_L_patio": 0.55,
        "en_T_patio": 0.95, "en_H_patio": 0.7, "en_cruz_patio": 0.75,
        "articulada_patio": 0.5},
    "En U": {
        "lineal": 0.45, "doble_crujia": 0.55, "patio": 0.75,
        "en_L": 0.65, "en_T": 0.65, "en_U": 1.0, "en_H": 0.7,
        "en_cruz": 0.6, "articulada": 0.55, "en_L_patio": 0.6,
        "en_T_patio": 0.6, "en_H_patio": 0.7, "en_cruz_patio": 0.6,
        "articulada_patio": 0.55},
    "En H": {
        "lineal": 0.45, "doble_crujia": 0.6, "patio": 0.55,
        "en_L": 0.5, "en_T": 0.65, "en_U": 0.65, "en_H": 1.0,
        "en_cruz": 0.75, "articulada": 0.6, "en_L_patio": 0.5,
        "en_T_patio": 0.65, "en_H_patio": 0.95, "en_cruz_patio": 0.75,
        "articulada_patio": 0.6},
    "En cruz": {
        "lineal": 0.45, "doble_crujia": 0.55, "patio": 0.55,
        "en_L": 0.5, "en_T": 0.7, "en_U": 0.55, "en_H": 0.7,
        "en_cruz": 1.0, "articulada": 0.5, "en_L_patio": 0.5,
        "en_T_patio": 0.7, "en_H_patio": 0.7, "en_cruz_patio": 0.95,
        "articulada_patio": 0.5},
    "Patio central": {
        "lineal": 0.5, "doble_crujia": 0.6, "patio": 1.0,
        "en_L": 0.6, "en_T": 0.55, "en_U": 0.75, "en_H": 0.55,
        "en_cruz": 0.55, "articulada": 0.45, "en_L_patio": 0.75,
        "en_T_patio": 0.8, "en_H_patio": 0.8, "en_cruz_patio": 0.8,
        "articulada_patio": 0.6},
    "Articulada (eslabones)": {
        "lineal": 0.45, "doble_crujia": 0.5, "patio": 0.5,
        "en_L": 0.55, "en_T": 0.5, "en_U": 0.55, "en_H": 0.6,
        "en_cruz": 0.5, "articulada": 1.0, "en_L_patio": 0.55,
        "en_T_patio": 0.5, "en_H_patio": 0.6, "en_cruz_patio": 0.5,
        "articulada_patio": 0.95},
}


def shape_affinity(plan_shape: str, scheme: str) -> float:
    """Afinidad (0–1) entre la forma en planta y el esquema trazado."""
    return SHAPE_SCHEME_AFFINITY.get(plan_shape, {}).get(scheme, 0.5)


@dataclass
class PlantVariant:
    """Una variante de planta completa y puntuada."""

    key: str                        # «doble_crujia+espejo»
    scheme: str                     # lineal | doble_crujia | patio
    mirror: bool
    title: str
    description: str
    layouts: List[LevelLayout]
    advisories: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    fits_lot: bool = True
    lot_needed: Tuple[float, float] = (0.0, 0.0)
    rank: int = 0
    # Estimación PRECONS viva (v3.12.0, ui.variant_budget): derivada y
    # efímera, nunca persistida; None hasta que el llamador la adjunte.
    cost: Optional[Any] = None

    @property
    def fits_text(self) -> str:
        if self.fits_lot:
            return f"Cabe ({self.lot_needed[0]:.1f} × " \
                   f"{self.lot_needed[1]:.1f} m)"
        return (f"No cabe: necesita {self.lot_needed[0]:.1f} × "
                f"{self.lot_needed[1]:.1f} m")


def _split_two_bays(ordered: Sequence[RoomSpec]
                    ) -> Tuple[List[RoomSpec], List[RoomSpec]]:
    """Reparte los locales en dos crujías equilibradas por ancho.

    Greedy determinista: cada local va a la fila con menos ancho
    acumulado (empate → fila frontal). Así el pasillo/patio queda
    corto y las crujías parejas.
    """
    front: List[RoomSpec] = []
    back: List[RoomSpec] = []
    width_front = 0.0
    width_back = 0.0
    for room in ordered:
        if width_front <= width_back:
            front.append(room)
            width_front += room.width_m
        else:
            back.append(room)
            width_back += room.width_m
    return front, back


def _stair_spec(level_name: str, run: float,
                usage: str = "") -> RoomSpec:
    """Local de escalera: caja con el ancho que Neufert pide al uso.

    Doméstico: 1,40 m (caja clásica); salud: 1,80 m para la camilla.
    """
    return RoomSpec(name=f"Escalera {level_name}", space_type=STAIR_TYPE,
                    width_m=stair_width_for(usage), depth_m=run,
                    level_ref=level_name, with_window=False)


def _layout_two_bay_level(data: BuildingWizardData, level: LevelSpec,
                          ordered: Sequence[RoomSpec], patio: bool,
                          swap_rows: bool, with_entrance: bool,
                          entrance_done: bool,
                          with_stair: bool = False,
                          with_core: bool = False
                          ) -> Tuple[LevelLayout, bool]:
    """Traza un nivel en DOS crujías con pasillo o patio central.

    Los locales de cada crujía se alinean a su fondo mayor (como se
    hace en obra: la crujía es uniforme para que la circulación quede
    recta); las diferencias se explican en los avisos. Devuelve también
    el nuevo estado de «entrada ya puesta».
    """
    front, back = _split_two_bays(ordered)
    if swap_rows:
        front, back = back, front
    if with_core:
        # Núcleo rígido en la esquina frontal derecha de la crujía
        # frontal (v2.5.0), antes de alinear la crujía a su fondo.
        front = list(front) + [_core_spec(level.name)]
    depth_front = max((r.depth_m for r in front), default=0.0)
    depth_back = max((r.depth_m for r in back), default=0.0)
    if patio:
        band = max(data.corridor_width_m, 2.5)  # un patio habitable
    else:
        band = data.corridor_width_m
    total_w = max(sum(r.width_m for r in front),
                  sum(r.width_m for r in back))

    corridor_label = "Patio" if patio else "Pasillo"
    placed: List[PlacedRoom] = []
    advisories: List[str] = []

    def _row_fresh(specs: Sequence[RoomSpec], y: float, depth: float) -> None:
        x = 0.0
        for room in specs:
            aligned = depth if room.depth_m < depth - 1e-9 else room.depth_m
            if aligned != room.depth_m and room.space_type != STAIR_TYPE:
                advisories.append(
                    f"«{room.name}» se alineó a la crujía de {depth:.1f} m "
                    f"para que el {corridor_label.lower()} quede recto "
                    f"(antes {room.depth_m:.1f} m).")
            placed.append(PlacedRoom(
                name=room.name, space_type=room.space_type,
                level=level.name, x=x, y=y, w=room.width_m, d=aligned,
                with_window=room.with_window))
            x += room.width_m

    rise = terrain_rise_m(data.terrain_type)
    if with_stair:
        _steps, run = stair_geometry(_stair_rise_for(data),
                                     data.usage_type)
        if run > depth_front + 1e-9:
            advisories.append(
                f"La escalera de «{level.name}» no tiene desarrollo recto "
                f"suficiente en la crujía ({depth_front:.1f} m): se "
                "resolverá con tramo en U.")
            run = depth_front
        front = list(front) + [_stair_spec(level.name, run, data.usage_type)]
    _row_fresh(front, 0.0, depth_front)
    _row_fresh(back, depth_front + band, depth_back)
    if rise > 0.0:
        for pr in placed:
            if pr.y > depth_front + 1e-6:
                pr.floor_rise_m = rise
        advisories.append(
            f"Por la pendiente del terreno, la crujía trasera de "
            f"«{level.name}» sube a la cota +{rise:.2f} m"
            + (", con escalera en la crujía frontal" if with_stair
               else "") + ".")

    corridor = PlacedRoom(
        name=f"{corridor_label} {level.name}",
        space_type=PATIO_TYPE if patio else CORRIDOR_TYPE,
        level=level.name, x=0.0, y=depth_front, w=total_w, d=band,
        with_window=False, is_corridor=True)

    tagged: List[Tuple[Tuple[Tuple[float, float], Tuple[float, float]],
                       str]] = []
    for pr in placed + [corridor]:
        for seg in rect_segments(pr):
            tagged.append((seg, pr.name))
    walls = merge_walls(tagged)

    doors: List[OpeningPlacement] = []
    windows: List[OpeningPlacement] = []

    # 1) Puertas declaradas entre locales consecutivos de la MISMA fila.
    row_of: Dict[str, int] = {}
    position_in_row: Dict[str, int] = {}
    for row_id, row in ((0, front), (1, back)):
        for index, room in enumerate(row):
            row_of[room.name] = row_id
            position_in_row[room.name] = index
    for rel in data.relations:
        if not rel.with_door:
            continue
        if rel.a_name not in row_of or rel.b_name not in row_of:
            continue
        if row_of[rel.a_name] != row_of[rel.b_name]:
            advisories.append(
                f"La puerta «{rel.a_name} — {rel.b_name}» se omite: "
                f"quedaron en crujías distintas; el {corridor_label.lower()} "
                "los comunica igualmente.")
            continue
        row_id = row_of[rel.a_name]
        row = front if row_id == 0 else back
        ia, ib = position_in_row[rel.a_name], position_in_row[rel.b_name]
        if abs(ia - ib) != 1:
            advisories.append(
                f"La puerta «{rel.a_name} — {rel.b_name}» se omite: no "
                "quedaron pegados en su crujía.")
            continue
        # PlacedRoom (con x/w/d): el spec no sabe de geometría.
        placed_by_name = {pr.name: pr for pr in placed}
        a = placed_by_name[row[min(ia, ib)].name]
        b = placed_by_name[row[max(ia, ib)].name]
        part_x = a.x + a.w
        y0 = 0.0 if row_id == 0 else depth_front + band
        min_len = min(a.d, b.d)
        door = _place_door(walls, data, "V", part_x, y0, y0 + min_len,
                           f"entre {a.name} y {b.name}")
        if door is not None:
            doors.append(door)
        else:
            advisories.append(
                f"La puerta «{a.name} — {b.name}» no cabe en la pared "
                f"compartida de {min_len:.2f} m.")

    # 2) Puerta de cada local hacia el pasillo/patio.
    for pr in placed:
        y_wall = depth_front if pr.y == 0.0 else depth_front + band
        side = corridor_label.lower()
        door = _place_door(walls, data, "H", y_wall, pr.x, pr.x + pr.w,
                           f"{pr.name} → {side}")
        if door is not None:
            doors.append(door)
        else:
            advisories.append(
                f"«{pr.name}» quedó sin puerta al {side}: revisa anchos.")

    # 3) Entrada principal: extremo derecho del pasillo/patio, solo en
    #    el primer nivel con locales.
    if with_entrance and not entrance_done:
        door = _place_door(walls, data, "V", total_w, depth_front,
                           depth_front + band, "entrada principal",
                           entrance=True)
        if door is not None:
            doors.append(door)
        else:
            advisories.append(
                "La puerta de entrada no cabe en el extremo del "
                f"{corridor_label.lower()}: sube su ancho o baja el de "
                "las puertas.")

    # 4) Ventanas a fachada exterior: la crujía frontal mira al frente
    #    y la posterior al fondo.
    for pr in placed:
        if not pr.with_window:
            continue
        y_wall = 0.0 if pr.y == 0.0 else depth_front + band + depth_back
        window = _place_window(walls, data, y_wall, pr.x, pr.x + pr.w,
                               f"{pr.name} → fachada")
        if window is not None:
            windows.append(window)
        else:
            advisories.append(
                f"La ventana de «{pr.name}» no cabe en su fachada de "
                f"{pr.w:.2f} m.")

    if patio:
        advisories.append(
            f"El patio central de {band:.1f} m ilumina y ventila ambas "
            "crujías; cada local tiene su puerta a la galería.")

    layout = LevelLayout(level_name=level.name, rooms=placed,
                         corridor=corridor, walls=walls, doors=doors,
                         windows=windows, advisories=advisories)
    entrance_now = entrance_done or (
        with_entrance and any(d.is_door and "entrada" in d.note
                              for d in doors))
    return layout, entrance_now


# -- Motor de FORMAS COMPUESTAS (v2.3.0) ------------------------------------
# Esquemas en L, T, U, H, cruz y articulada: barras de locales unidas
# por pasillos (espinas, puentes o eslabones), todo axis-aligned y
# determinista. Cada forma devuelve sus piezas colocadas + pasillos +
# borde de entrada; el ensamblado (muros, puertas, ventanas, entrada)
# es común en _assemble_composed_level.

ShapedPlan = Tuple[List[PlacedRoom], List[PlacedRoom],
                   Optional[Tuple[str, float, float, float]], List[str]]


def _split_by_width(ordered: Sequence[RoomSpec], fraction: float,
                    reserve: int
                    ) -> Optional[Tuple[List[RoomSpec], List[RoomSpec]]]:
    """Corta la lista en dos grupos por ancho acumulado (determinista).

    El primer grupo acumula ~«fraction» del ancho total; al segundo se
    le reservan al menos «reserve» locales. None si no alcanzan los
    locales para repartir.
    """
    if len(ordered) <= reserve:
        return None
    total = sum(r.width_m for r in ordered)
    target = fraction * total
    acc = 0.0
    cut = 1
    for index, room in enumerate(ordered[:len(ordered) - reserve]):
        acc += room.width_m
        cut = index + 1
        if acc >= target:
            break
    return list(ordered[:cut]), list(ordered[cut:])


def _balance_columns(rooms: Sequence[RoomSpec], columns: int = 2
                     ) -> List[List[RoomSpec]]:
    """Reparte los locales en columnas equilibradas por ancho (greedy)."""
    cols: List[List[RoomSpec]] = [[] for _ in range(columns)]
    widths = [0.0] * columns
    for room in rooms:
        index = widths.index(min(widths))
        cols[index].append(room)
        widths[index] += room.width_m
    return cols


def _row_rooms(specs: Sequence[RoomSpec], x0: float, y0: float,
               level_name: str, rise: float = 0.0) -> List[PlacedRoom]:
    """Fila horizontal: el ancho corre por x y el fondo por y."""
    placed: List[PlacedRoom] = []
    x = x0
    for room in specs:
        placed.append(PlacedRoom(
            name=room.name, space_type=room.space_type,
            level=level_name, x=x, y=y0, w=room.width_m, d=room.depth_m,
            with_window=room.with_window, floor_rise_m=rise))
        x += room.width_m
    return placed


def _row_below(specs: Sequence[RoomSpec], x0: float, y_top: float,
               level_name: str, rise: float = 0.0) -> List[PlacedRoom]:
    """Fila horizontal que cuelga HACIA ABAJO de la cota «y_top»."""
    placed: List[PlacedRoom] = []
    x = x0
    for room in specs:
        placed.append(PlacedRoom(
            name=room.name, space_type=room.space_type,
            level=level_name, x=x, y=y_top - room.depth_m,
            w=room.width_m, d=room.depth_m,
            with_window=room.with_window, floor_rise_m=rise))
        x += room.width_m
    return placed


def _stack_rooms(specs: Sequence[RoomSpec], anchor: float, y_top: float,
                 level_name: str, rise: float = 0.0,
                 align: str = "left") -> List[PlacedRoom]:
    """Pila vertical hacia abajo: el ancho de cada local corre por y.

    «align=left» fija el borde izquierdo en «anchor»; «right» fija el
    borde derecho (x = anchor - fondo). Así el fondo del local mira al
    lado exterior de la ala.
    """
    placed: List[PlacedRoom] = []
    y = y_top
    for room in specs:
        x_left = anchor if align == "left" else anchor - room.depth_m
        placed.append(PlacedRoom(
            name=room.name, space_type=room.space_type,
            level=level_name, x=x_left, y=y - room.width_m,
            w=room.depth_m, d=room.width_m,
            with_window=room.with_window, floor_rise_m=rise))
        y -= room.width_m
    return placed


# PATIOS EN LAS ALAS (v2.4.0): las alas largas ganan un patio interior
# (pozo de luz habitable) por la mitad de la pila, con al menos un
# local a cada lado. Los locales pegados al patio reciben puerta a su
# galería en el ensamblado común y el patio entra a los métricos como
# el patio central (circulación abierta que ilumina y ventila).
WING_PATIO_MIN_ROOMS = 3       # patio + al menos 1 local a cada lado
WING_PATIO_MIN_LENGTH_M = 6.0  # longitud mínima de la ala para partir
WING_PATIO_WIDTH_M = 2.5       # ancho habitable (como el patio central)
WING_PATIO_DEPTH_M = 3.0       # fondo del patio de ala
WING_PATIO_MIN_DEPTH_M = 2.0   # no cabe un patio en alas muy rasas


def _wing_patio_cut(specs: Sequence[RoomSpec]
                    ) -> Optional[Tuple[int, float]]:
    """Punto de corte e intercalación de patio en una ala (o None).

    Devuelve (índice de corte, fondo del patio): la pila se parte tras
    acumular ~la mitad de su longitud, dejando SIEMPRE al menos un
    local a cada lado. Determinista; None si la ala es muy corta o
    demasiado rasa para un patio habitable.
    """
    if len(specs) < WING_PATIO_MIN_ROOMS:
        return None
    total = sum(r.width_m for r in specs)
    if total < WING_PATIO_MIN_LENGTH_M:
        return None
    shallow = min(r.depth_m for r in specs)
    if shallow < WING_PATIO_MIN_DEPTH_M:
        return None
    acc = 0.0
    cut = 1
    for index, room in enumerate(specs[:len(specs) - 1]):
        acc += room.width_m
        cut = index + 1
        if acc >= total / 2.0:
            break
    cut = max(1, min(cut, len(specs) - 1))
    return cut, min(WING_PATIO_DEPTH_M, shallow)


def _stack_with_wing_patio(specs: Sequence[RoomSpec], anchor: float,
                           y_top: float, level_name: str, rise: float,
                           align: str, label: str
                           ) -> Tuple[List[PlacedRoom], Optional[PlacedRoom]]:
    """Pila de ala con PATIO intercalado si la ala lo merece (v2.4.0).

    Misma colocación que _stack_rooms; si hay corte, entre ambos
    segmentos queda el patio de ala (is_corridor=True para que el
    ensamblado le dé puertas de galería y lo cuente como abierto).
    Devuelve (piezas colocadas, patio o None).
    """
    cut_info = _wing_patio_cut(specs)
    if cut_info is None:
        return _stack_rooms(specs, anchor, y_top, level_name, rise=rise,
                            align=align), None
    cut, patio_d = cut_info
    before, after = list(specs[:cut]), list(specs[cut:])
    placed = _stack_rooms(before, anchor, y_top, level_name, rise=rise,
                          align=align)
    y_after = y_top - sum(r.width_m for r in before)
    patio_x = anchor if align == "left" else anchor - patio_d
    patio = PlacedRoom(
        name=f"Patio de ala {label} · {level_name}",
        space_type=PATIO_TYPE, level=level_name, x=patio_x,
        y=y_after - WING_PATIO_WIDTH_M, w=patio_d,
        d=WING_PATIO_WIDTH_M, with_window=False, is_corridor=True)
    placed += _stack_rooms(after, anchor, y_after - WING_PATIO_WIDTH_M,
                           level_name, rise=rise, align=align)
    return placed, patio


def _wing_patio_advisory(patio: PlacedRoom) -> str:
    """Aviso amable del patio de ala recién colocado."""
    return (f"Patio de ala de {patio.w:.1f} × {patio.d:.1f} m "
            f"(«{patio.name}»): luz y ventilación para el fondo del ala; "
            "los locales pegados tienen puerta a su galería.")


def _shared_edge(a: PlacedRoom, b: PlacedRoom, tol: float = 1e-6
                 ) -> Optional[Tuple[str, float, float, float]]:
    """Pared común entre dos locales: (orientación, fija, lo, hi)."""
    vertical = abs(a.x + a.w - b.x) <= tol or abs(b.x + b.w - a.x) <= tol
    if vertical:
        fixed = a.x + a.w if abs(a.x + a.w - b.x) <= tol else b.x + b.w
        lo = max(a.y, b.y)
        hi = min(a.y + a.d, b.y + b.d)
        if hi - lo > 0.3:
            return ("V", fixed, lo, hi)
    horizontal = abs(a.y + a.d - b.y) <= tol or abs(b.y + b.d - a.y) <= tol
    if horizontal:
        fixed = a.y + a.d if abs(a.y + a.d - b.y) <= tol else b.y + b.d
        lo = max(a.x, b.x)
        hi = min(a.x + a.w, b.x + b.w)
        if hi - lo > 0.3:
            return ("H", fixed, lo, hi)
    return None


def _corridor_edge(pr: PlacedRoom, corridors: Sequence[PlacedRoom],
                   tol: float = 1e-6
                   ) -> Optional[Tuple[str, float, float, float]]:
    """Borde del local que toca algún pasillo (para su puerta)."""
    for cor in corridors:
        vertical = abs(cor.x + cor.w - pr.x) <= tol or \
            abs(pr.x + pr.w - cor.x) <= tol
        if vertical:
            fixed = cor.x + cor.w if abs(cor.x + cor.w - pr.x) <= tol \
                else pr.x + pr.w
            lo = max(pr.y, cor.y)
            hi = min(pr.y + pr.d, cor.y + cor.d)
            if hi - lo > 0.3:
                return ("V", fixed, lo, hi)
        horizontal = abs(cor.y + cor.d - pr.y) <= tol or \
            abs(pr.y + pr.d - cor.y) <= tol
        if horizontal:
            fixed = cor.y + cor.d if abs(cor.y + cor.d - pr.y) <= tol \
                else pr.y + pr.d
            lo = max(pr.x, cor.x)
            hi = min(pr.x + pr.w, cor.x + cor.w)
            if hi - lo > 0.3:
                return ("H", fixed, lo, hi)
    return None


def _edge_touching(pr: PlacedRoom, edge_index: int, other: PlacedRoom,
                   tol: float = 1e-6) -> bool:
    """¿«other» tapa el borde «edge_index» de «pr»?

    Bordes: 0 frente (y = pr.y), 1 derecha (x = pr.x + pr.w),
    2 fondo (y = pr.y + pr.d) y 3 izquierda (x = pr.x). Basta un
    solape de más de 0,3 m para considerar el borde ocupado.
    """
    overlap_v = min(pr.y + pr.d, other.y + other.d) - max(pr.y, other.y)
    overlap_h = min(pr.x + pr.w, other.x + other.w) - max(pr.x, other.x)
    if edge_index in (0, 2):  # frente / fondo: muro horizontal
        fixed = pr.y if edge_index == 0 else pr.y + pr.d
        other_fixed = other.y + other.d if edge_index == 0 else other.y
        return abs(other_fixed - fixed) <= tol and overlap_h > 0.3
    fixed = pr.x + pr.w if edge_index == 1 else pr.x
    other_fixed = other.x if edge_index == 1 else other.x + other.w
    return abs(other_fixed - fixed) <= tol and overlap_v > 0.3


def _exterior_edges(pr: PlacedRoom, pieces: Sequence[PlacedRoom],
                    tol: float = 1e-6) -> List[int]:
    """Índices de los bordes de «pr» sin vecino (fachada exterior)."""
    exterior: List[int] = []
    for edge_index in range(4):
        covered = False
        for other in pieces:
            if other is pr:
                continue
            if _edge_touching(pr, edge_index, other, tol):
                covered = True
                break
        if not covered:
            exterior.append(edge_index)
    return exterior


def _place_window_v(walls: List[Dict[str, Any]], data: BuildingWizardData,
                    fixed_x: float, lo: float, hi: float,
                    note: str) -> Optional[OpeningPlacement]:
    """Ventana sobre un muro VERTICAL (fachada lateral de las alas)."""
    wall, wall_index = _wall_for_interval(walls, "V", fixed_x, lo, hi)
    if wall is None:
        return None
    span = hi - lo
    width = data.window_width_m
    if width > span + 1e-9:
        return None
    axis_start = _wall_axis_start(wall)
    offset = _clamp_offset(wall, (lo + (span - width) / 2.0) - axis_start,
                           width)
    return OpeningPlacement(kind="WINDOW", width_m=width,
                            height_m=data.window_height_m,
                            offset_m=offset,
                            sill_height_m=data.window_sill_m, note=note,
                            wall_index=wall_index)


def _assemble_composed_level(data: BuildingWizardData, level: LevelSpec,
                             placed: List[PlacedRoom],
                             corridors: List[PlacedRoom],
                             entrance: Optional[Tuple[str, float, float,
                                                      float]],
                             entrance_done: bool, advisories: List[str]
                             ) -> Tuple[LevelLayout, bool]:
    """Muros, puertas, ventanas y entrada comunes a las formas compuestas.

    Las puertas declaradas se apoyan en CUALQUIER pared común (no hace
    falta ser consecutivos en una fila); cada local recibe puerta al
    pasillo que toque, la entrada va donde indique la forma y las
    ventanas buscan el primer borde exterior donde quepan.
    """
    tagged: List[Tuple[Tuple[Tuple[float, float], Tuple[float, float]],
                       str]] = []
    for pr in placed + corridors:
        for seg in rect_segments(pr):
            tagged.append((seg, pr.name))
    walls = merge_walls(tagged)
    doors: List[OpeningPlacement] = []
    windows: List[OpeningPlacement] = []
    by_name = {pr.name: pr for pr in placed}

    # 1) Puertas declaradas sobre paredes comunes.
    for rel in data.relations:
        if not rel.with_door:
            continue
        if rel.a_name not in by_name or rel.b_name not in by_name:
            continue
        edge = _shared_edge(by_name[rel.a_name], by_name[rel.b_name])
        if edge is None:
            advisories.append(
                f"La puerta «{rel.a_name} — {rel.b_name}» se omite: no "
                "quedaron con pared común en esta forma; el pasillo los "
                "comunica igualmente.")
            continue
        orientation, fixed, lo, hi = edge
        door = _place_door(walls, data, orientation, fixed, lo, hi,
                           f"entre {rel.a_name} y {rel.b_name}")
        if door is not None:
            doors.append(door)
        else:
            advisories.append(
                f"La puerta «{rel.a_name} — {rel.b_name}» no cabe en la "
                f"pared compartida de {hi - lo:.2f} m.")

    # 2) Puerta de cada local al pasillo que toque. Si el borde es la
    #    galería de un patio, la puerta se nombra como galería (v2.5.0).
    connected: set = set()
    used_edges: set = set()
    patios_centrales = [p for p in corridors if p.space_type == PATIO_TYPE]
    for pr in placed:
        edge = _corridor_edge(pr, corridors)
        if edge is None:
            continue
        orientation, fixed, lo, hi = edge
        clave = (orientation, round(fixed, 3), round(lo, 3), round(hi, 3))
        a_patio = any(
            (pedge := _corridor_edge(pr, [patio])) is not None and
            (pedge[0], round(pedge[1], 3), round(pedge[2], 3),
             round(pedge[3], 3)) == clave
            for patio in patios_centrales)
        door = _place_door(walls, data, orientation, fixed, lo, hi,
                           f"{pr.name} → " + ("galería del patio"
                                              if a_patio else "pasillo"))
        if door is not None:
            doors.append(door)
            connected.add(pr.name)
            used_edges.add(clave)
        else:
            advisories.append(
                f"«{pr.name}» quedó sin puerta posible: revisa anchos.")

    # 2a) Galería de los PATIOS (v2.4.0 alas, v2.5.0 también central):
    #     todo local pegado a un patio recibe puerta a él, ya tuviera
    #     puerta al pasillo o no; así los locales que quedaron al otro
    #     lado del patio quedan conectados antes de la enfilada. Si la
    #     pared con el patio ya recibió una puerta en el paso 2, no se
    #     repite (misma pared = una sola puerta).
    wing_patios = [p for p in corridors if p.space_type == PATIO_TYPE]
    for patio in wing_patios:
        for pr in placed:
            edge = _corridor_edge(pr, [patio])
            if edge is None:
                continue
            orientation, fixed, lo, hi = edge
            key = (orientation, round(fixed, 3), round(lo, 3),
                   round(hi, 3))
            if key in used_edges:
                connected.add(pr.name)
                continue
            door = _place_door(walls, data, orientation, fixed, lo, hi,
                               f"{pr.name} → galería del patio")
            if door is not None:
                doors.append(door)
                connected.add(pr.name)
                used_edges.add(key)

    # 2b) Ala enfilada: los locales sin pasillo propio (profundos en
    #     las alas de la L o la U) se encadenan con un local ya
    #     conectado por su pared común.
    for pr in placed:
        if pr.name in connected:
            continue
        link = None
        for other in placed:
            if other is pr or other.name not in connected:
                continue
            edge = _shared_edge(pr, other)
            if edge is not None:
                link = (other, edge)
                break
        if link is None:
            advisories.append(
                f"«{pr.name}» no toca ningún pasillo ni local conectado: "
                "quedó aislado en esta forma; revisa el trazado.")
            continue
        other, (orientation, fixed, lo, hi) = link
        door = _place_door(walls, data, orientation, fixed, lo, hi,
                           f"entre {other.name} y {pr.name}")
        if door is not None:
            doors.append(door)
            connected.add(pr.name)
        else:
            advisories.append(
                f"«{pr.name}» quedó sin puerta posible: revisa anchos.")

    # 3) Entrada principal donde la forma la reserva.
    if entrance is not None and not entrance_done:
        orientation, fixed, lo, hi = entrance
        door = _place_door(walls, data, orientation, fixed, lo, hi,
                           "entrada principal", entrance=True)
        if door is not None:
            doors.append(door)
        else:
            advisories.append(
                "La puerta de entrada no cabe en el extremo del "
                "pasillo: revisa anchos.")

    # 4) Ventanas en el primer borde exterior donde quepan.
    pieces = placed + corridors
    for pr in placed:
        if not pr.with_window:
            continue
        done = False
        for edge_index in _exterior_edges(pr, pieces):
            if edge_index in (0, 2):
                fixed = pr.y if edge_index == 0 else pr.y + pr.d
                lo, hi = pr.x, pr.x + pr.w
                window = _place_window(walls, data, fixed, lo, hi,
                                       f"{pr.name} → fachada")
            else:
                fixed = pr.x + pr.w if edge_index == 1 else pr.x
                lo, hi = pr.y, pr.y + pr.d
                window = _place_window_v(walls, data, fixed, lo, hi,
                                         f"{pr.name} → fachada")
            if window is not None:
                windows.append(window)
                done = True
                break
        if not done:
            advisories.append(
                f"La ventana de «{pr.name}» no cabe en sus fachadas "
                "exteriores: revisa el ancho de las ventanas.")

    main_corridor = corridors[0] if corridors else None
    layout = LevelLayout(level_name=level.name, rooms=placed,
                         corridor=main_corridor, walls=walls, doors=doors,
                         windows=windows, advisories=advisories,
                         extra_corridors=list(corridors[1:]))
    entrance_now = entrance_done or (
        entrance is not None and any(d.is_door and "entrada" in d.note
                                     for d in doors))
    return layout, entrance_now


def _rise_advisory(level_name: str, rise: float,
                   with_stair: bool) -> str:
    """Aviso amable del desnivel que impone el terreno."""
    return (f"Por la pendiente del terreno, parte de «{level_name}» "
            f"queda a la cota +{rise:.2f} m"
            + ("; la escalera une ambas cotas" if with_stair else "")
            + ".")


def _shape_L(data: BuildingWizardData, level: LevelSpec,
             ordered: Sequence[RoomSpec], mirror: bool, rise: float,
             with_stair: bool, with_core: bool = False,
             patio_center: bool = False) -> Optional[ShapedPlan]:
    """En L: barra frontal + ala perpendicular hacia el fondo del lote.

    Con «patio_center» (v2.5.0) la esquina interior que la L abraza se
    vuelve un patio central pegado al pasillo y a la primera pieza del
    ala (galería con puertas).
    """
    split = _split_by_width(ordered, 0.6, reserve=1)
    if split is None:
        return None
    front, wing = list(split[0]), list(split[1])
    c = data.corridor_width_m
    width_front = sum(r.width_m for r in front)
    max_depth = max(r.depth_m for r in wing)
    if with_stair:
        _steps, run = stair_geometry(_stair_rise_for(data),
                                     data.usage_type)
        if patio_center:
            # Con patio central la escalera va al FINAL del ala: la
            # esquina de arranque queda para locales que miran al
            # patio (v2.5.0).
            wing = wing + [_stair_spec(level.name, run, data.usage_type)]
        else:
            wing = [_stair_spec(level.name, run, data.usage_type)] + wing
    if with_core:
        # El núcleo rígido remata el ala: esquina posterior de la L,
        # siempre pegada a la envolvente (v2.5.0).
        wing = wing + [_core_spec(level.name)]
    advisories: List[str] = ["Forma en L: barra frontal con ala "
                             "perpendicular; el pasillo corre por la "
                             "esquina y reparte ambas alas."]
    if mirror:
        corridor_x = -max_depth
        entrance = ("V", width_front, -c, 0.0)
        wing_anchor, wing_align = -max_depth, "left"
    else:
        corridor_x = 0.0
        entrance = ("V", 0.0, -c, 0.0)
        wing_anchor, wing_align = width_front, "left"
    corridor = PlacedRoom(
        name=f"Pasillo {level.name}", space_type=CORRIDOR_TYPE,
        level=level.name, x=corridor_x, y=-c,
        w=width_front + max_depth, d=c, with_window=False,
        is_corridor=True)
    placed = _row_rooms(front, 0.0, 0.0, level.name)
    wing_placed, wing_patio = _stack_with_wing_patio(
        wing, wing_anchor, -c, level.name, rise, wing_align, "lateral")
    placed += wing_placed
    corridors = [corridor] + ([wing_patio] if wing_patio is not None
                              else [])
    if wing_patio is not None:
        advisories.append(_wing_patio_advisory(wing_patio))
    if patio_center:
        pw = pd = 3.0
        if mirror:
            # El ala crece hacia la derecha desde su ancla: el patio se
            # pega al borde de los locales de la franja superior (los
            # que quedan a la altura del patio, v2.5.0).
            acc = 0.0
            right_edge = -max_depth
            for room in wing:
                if acc >= pd:
                    break
                right_edge = max(right_edge,
                                 -max_depth + room.depth_m)
                acc += room.width_m
            patio_x = right_edge
        else:
            patio_x = width_front - pw
        patio = PlacedRoom(
            name=f"Patio central · {level.name}", space_type=PATIO_TYPE,
            level=level.name, x=patio_x, y=-c - pd, w=pw, d=pd,
            with_window=False, is_corridor=True)
        corridors.append(patio)
        advisories.append(
            f"Patio central de {pw:.1f} × {pd:.1f} m abrazado por la L: "
            "luz y verde en la esquina interior; los locales del ala "
            "pegados a él tienen puerta a su galería.")
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _shape_T(data: BuildingWizardData, level: LevelSpec,
             ordered: Sequence[RoomSpec], mirror: bool, rise: float,
             with_stair: bool, with_core: bool = False,
             patio_center: bool = False) -> Optional[ShapedPlan]:
    """En T: cuerpo frontal + espina central con locales a ambos lados.

    Con «patio_center» (v2.5.0) la espina se vuelve un patio central
    que ilumina las dos alas de locales que lo flanquean.
    """
    split = _split_by_width(ordered, 0.5, reserve=2)
    if split is None:
        return None
    front, spine_rooms = list(split[0]), list(split[1])
    if with_core:
        front = list(front) + [_core_spec(level.name)]
    left, right = _balance_columns(spine_rooms, 2)
    if mirror:
        left, right = right, left
    if with_stair:
        _steps, run = stair_geometry(_stair_rise_for(data),
                                     data.usage_type)
        target = left if sum(w.width_m for w in left) <= sum(
            w.width_m for w in right) else right
        target.insert(0, _stair_spec(level.name, run, data.usage_type))
    c = data.corridor_width_m
    width_front = sum(r.width_m for r in front)
    pw = max(c, WING_PATIO_WIDTH_M) if patio_center else c
    spine_x = (width_front - pw) / 2.0
    # v2.4.0: la espina cubre también el ancho del patio si la columna
    # lo gana, para que ninguna pieza cuelgue más allá de su extremo.
    left_extra = WING_PATIO_WIDTH_M \
        if _wing_patio_cut(left) is not None else 0.0
    right_extra = WING_PATIO_WIDTH_M \
        if _wing_patio_cut(right) is not None else 0.0
    spine_len = max(3.0,
                    sum(r.width_m for r in left) + left_extra,
                    sum(r.width_m for r in right) + right_extra)
    corridor_h = PlacedRoom(
        name=f"Pasillo {level.name}", space_type=CORRIDOR_TYPE,
        level=level.name, x=0.0, y=-c, w=width_front, d=c,
        with_window=False, is_corridor=True)
    if patio_center:
        spine = PlacedRoom(
            name=f"Patio central · {level.name}", space_type=PATIO_TYPE,
            level=level.name, x=spine_x, y=-c - spine_len, w=pw,
            d=spine_len, with_window=False, is_corridor=True)
    else:
        spine = PlacedRoom(
            name=f"Pasillo {level.name} (espina)",
            space_type=CORRIDOR_TYPE, level=level.name, x=spine_x,
            y=-c - spine_len, w=c, d=spine_len,
            with_window=False, is_corridor=True)
    placed = _row_rooms(front, 0.0, 0.0, level.name)
    advisories: List[str] = [
        "Forma en T: cuerpo frontal con espina central de circulación; "
        "separa con claridad lo público de lo de servicio."]
    left_placed, left_patio = _stack_with_wing_patio(
        left, spine_x, -c, level.name, rise, "right", "izquierda")
    right_placed, right_patio = _stack_with_wing_patio(
        right, spine_x + pw, -c, level.name, rise, "left", "derecha")
    placed += left_placed + right_placed
    corridors = [corridor_h, spine]
    for patio in (left_patio, right_patio):
        if patio is not None:
            corridors.append(patio)
            advisories.append(_wing_patio_advisory(patio))
    entrance = ("H", -c - spine_len, spine_x, spine_x + pw)
    if patio_center:
        advisories.append(
            f"Patio central de {pw:.1f} × {spine_len:.1f} m en lugar de "
            "la espina: las dos alas de locales miran a un jardín "
            "interior y la entrada llega por el patio.")
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _shape_U(data: BuildingWizardData, level: LevelSpec,
             ordered: Sequence[RoomSpec], mirror: bool, rise: float,
             with_stair: bool, with_core: bool = False
             ) -> Optional[ShapedPlan]:
    """En U: barra frontal + dos alas que abrazan un patio trasero."""
    split = _split_by_width(ordered, 0.5, reserve=2)
    if split is None:
        return None
    front, wing_rooms = list(split[0]), list(split[1])
    if with_core:
        front = list(front) + [_core_spec(level.name)]
    left, right = _balance_columns(wing_rooms, 2)
    if mirror:
        left, right = right, left
    if with_stair:
        _steps, run = stair_geometry(_stair_rise_for(data),
                                     data.usage_type)
        right.insert(0, _stair_spec(level.name, run, data.usage_type))
    c = data.corridor_width_m
    width_front = sum(r.width_m for r in front)
    left_depth = max((r.depth_m for r in left), default=0.0)
    corridor_h = PlacedRoom(
        name=f"Pasillo {level.name}", space_type=CORRIDOR_TYPE,
        level=level.name, x=0.0, y=-c, w=width_front, d=c,
        with_window=False, is_corridor=True)
    placed = _row_rooms(front, 0.0, 0.0, level.name)
    left_placed, left_patio = _stack_with_wing_patio(
        left, 0.0, -c, level.name, rise, "left", "izquierda")
    placed += left_placed
    corridors: List[PlacedRoom] = [corridor_h]
    if left_patio is not None:
        corridors.append(left_patio)
    advisories: List[str] = []
    if left_patio is not None:
        advisories.append(_wing_patio_advisory(left_patio))
    # Ala derecha: bucle propio (fondos alineados al borde derecho),
    # con patio de ala intercalado si la ala lo merece (v2.4.0).
    cut_info = _wing_patio_cut(right)
    right_cut, right_patio_d = cut_info if cut_info is not None else (0, 0.0)
    y = -c
    shifted = False
    for index, room in enumerate(right):
        if cut_info is not None and index == right_cut:
            patio_x = width_front - right_patio_d
            if patio_x < left_depth + 0.5:
                patio_x = left_depth + 0.5
                shifted = True
            patio = PlacedRoom(
                name=f"Patio de ala derecha · {level.name}",
                space_type=PATIO_TYPE, level=level.name, x=patio_x,
                y=y - WING_PATIO_WIDTH_M, w=right_patio_d,
                d=WING_PATIO_WIDTH_M, with_window=False,
                is_corridor=True)
            # Solo a «corridors»: all_rooms = rooms + corredores, y
            # meterlo también en «placed» lo duplicaría.
            corridors.append(patio)
            advisories.append(_wing_patio_advisory(patio))
            y -= WING_PATIO_WIDTH_M
        x_left = width_front - room.depth_m
        if x_left < left_depth + 0.5:
            x_left = left_depth + 0.5
            shifted = True
        placed.append(PlacedRoom(
            name=room.name, space_type=room.space_type,
            level=level.name, x=x_left, y=y - room.width_m,
            w=room.depth_m, d=room.width_m,
            with_window=room.with_window, floor_rise_m=rise))
        y -= room.width_m
    if shifted:
        advisories.append(
            "Las alas de la U se separaron para no solaparse: el patio "
            "trasero queda más estrecho.")
    entrance = ("V", width_front if mirror else 0.0, -c, 0.0)
    advisories.insert(0, "Forma en U: dos alas que abrazan un patio "
                         "trasero entre ellas, perfecto para recreo, "
                         "sol o carga y descarga.")
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _double_bar_layout(data: BuildingWizardData, level: LevelSpec,
                       front: List[RoomSpec], rear: List[RoomSpec],
                       spine_columns: Sequence[Tuple[Sequence[RoomSpec],
                                                     str]],
                       mirror: bool, rise: float, with_stair: bool,
                       link_len: float, link_label: str,
                       with_core: bool = False,
                       patio_center: bool = False
                       ) -> Optional[ShapedPlan]:
    """Núcleo común de «En H», «En cruz» y «Articulada»: dos barras
    unidas por un pasillo perpendicular (puente, espina o eslabón).

    «spine_columns» son pares (locales, alineación) para las columnas
    que cuelgan a los lados del pasillo central (solo la cruz).
    Con «patio_center» (v2.5.0) el pasillo central se vuelve un PATIO
    que además se come las bandas de pasillo frente a él: los locales
    de ambas barras le dan la puerta directamente a su galería.
    """
    if with_stair:
        _steps, run = stair_geometry(_stair_rise_for(data),
                                     data.usage_type)
        rear = [_stair_spec(level.name, run, data.usage_type)] + list(rear)
    if with_core:
        # Núcleo rígido al final de la crujía que REMATA la envolvente
        # (v2.7.0): con la escalera hospitalaria de 1,80 m (Neufert),
        # la crujía trasera puede quedar más ancha que la frontal y el
        # núcleo se va a ELLA para seguir tocando la esquina.
        _wf0 = sum(r.width_m for r in front)
        _wr0 = sum(r.width_m for r in rear)
        if not mirror and _wr0 > _wf0:
            rear = list(rear) + [_core_spec(level.name)]
        else:
            front = list(front) + [_core_spec(level.name)]
    c = data.corridor_width_m
    width_front = sum(r.width_m for r in front)
    width_rear = sum(r.width_m for r in rear)
    if width_front < c + 0.4 or width_rear < c + 0.4:
        return None
    rear_x0 = 0.0 if not mirror else max(0.0, width_front - width_rear)
    lo = max(0.0, rear_x0)
    hi = min(width_front, rear_x0 + width_rear)
    if hi - lo < c + 0.4:
        return None
    pw = max(c, WING_PATIO_WIDTH_M) if patio_center else c
    if patio_center and hi - lo - 0.4 < pw:
        pw = max(c, hi - lo - 0.4)
    spine_x = lo + (hi - lo - pw) / 2.0
    spine_len = link_len
    for column, _align in spine_columns:
        # v2.4.0: si la columna ganará patio de ala, su longitud total
        # crece el ancho del patio; la espina debe cubrirlo todo para
        # que la última pieza no se derrame sobre la barra trasera.
        extra = WING_PATIO_WIDTH_M \
            if _wing_patio_cut(column) is not None else 0.0
        spine_len = max(spine_len, sum(r.width_m for r in column) + extra)
    corridor_h = PlacedRoom(
        name=f"Pasillo {level.name}", space_type=CORRIDOR_TYPE,
        level=level.name, x=0.0, y=-c, w=width_front, d=c,
        with_window=False, is_corridor=True)
    if patio_center:
        # El patio ocupa el vano entre barras y se come las bandas de
        # pasillo frente a él: los locales de ambas barras quedan
        # pegados a su galería (v2.5.0).
        patio = PlacedRoom(
            name=f"Patio central · {level.name}", space_type=PATIO_TYPE,
            level=level.name, x=spine_x, y=-c - spine_len - c, w=pw,
            d=spine_len + 2 * c, with_window=False, is_corridor=True)
        corridors: List[PlacedRoom] = []
        if spine_x > 1.0:
            corridors.append(PlacedRoom(
                name=f"Pasillo {level.name}", space_type=CORRIDOR_TYPE,
                level=level.name, x=0.0, y=-c, w=spine_x, d=c,
                with_window=False, is_corridor=True))
        if width_front - (spine_x + pw) > 1.0:
            corridors.append(PlacedRoom(
                name=f"Pasillo {level.name} (derecho)",
                space_type=CORRIDOR_TYPE, level=level.name,
                x=spine_x + pw, y=-c, w=width_front - spine_x - pw, d=c,
                with_window=False, is_corridor=True))
        corridors.append(patio)
        if spine_x - rear_x0 > 1.0:
            corridors.append(PlacedRoom(
                name=f"Pasillo {level.name} (trasero)",
                space_type=CORRIDOR_TYPE, level=level.name, x=rear_x0,
                y=-c - spine_len - c, w=spine_x - rear_x0, d=c,
                with_window=False, is_corridor=True))
        if rear_x0 + width_rear - (spine_x + pw) > 1.0:
            corridors.append(PlacedRoom(
                name=f"Pasillo {level.name} (trasero derecho)",
                space_type=CORRIDOR_TYPE, level=level.name,
                x=spine_x + pw, y=-c - spine_len - c,
                w=rear_x0 + width_rear - spine_x - pw, d=c,
                with_window=False, is_corridor=True))
    else:
        spine = PlacedRoom(
            name=f"Pasillo {level.name} ({link_label})",
            space_type=CORRIDOR_TYPE, level=level.name, x=spine_x,
            y=-c - spine_len, w=c, d=spine_len, with_window=False,
            is_corridor=True)
        rear_corridor = PlacedRoom(
            name=f"Pasillo {level.name} (trasero)", space_type=CORRIDOR_TYPE,
            level=level.name, x=rear_x0, y=-c - spine_len - c,
            w=width_rear, d=c, with_window=False, is_corridor=True)
        corridors = [corridor_h, spine, rear_corridor]
    rear_y_top = -c - spine_len - c
    placed = _row_rooms(front, 0.0, 0.0, level.name)
    placed += _row_below(rear, rear_x0, rear_y_top, level.name,
                         rise=rise)
    wing_patios: List[PlacedRoom] = []
    for column, align in spine_columns:
        if not column:
            continue
        # «right» = la columna queda a la IZQUIERDA de la espina (su
        # borde derecho pegado a spine_x); «left» = a la DERECHA (su
        # borde izquierdo pegado a spine_x + ancho del eje central).
        anchor = spine_x if align == "right" else spine_x + pw
        label = "izquierda" if align == "right" else "derecha"
        column_placed, patio = _stack_with_wing_patio(
            column, anchor, -c, level.name, rise, align, label)
        placed += column_placed
        if patio is not None:
            wing_patios.append(patio)
    if patio_center:
        if width_front - (spine_x + pw) > 1.0:
            entrance = ("V", width_front, -c, 0.0)
        else:
            # El patio llega hasta la fachada: entrada por el patio.
            entrance = ("H", 0.0, spine_x, spine_x + pw)
    else:
        entrance = ("V", width_front if mirror else 0.0, -c, 0.0)
    return placed, corridors + wing_patios, entrance, []


def _shape_H(data: BuildingWizardData, level: LevelSpec,
             ordered: Sequence[RoomSpec], mirror: bool, rise: float,
             with_stair: bool, with_core: bool = False
             ) -> Optional[ShapedPlan]:
    """En H: dos barras unidas por un puente central de pasillo."""
    split = _split_by_width(ordered, 0.45, reserve=2)
    if split is None:
        return None
    result = _double_bar_layout(data, level, list(split[0]), list(split[1]),
                                (), mirror, rise, with_stair, 3.0,
                                "puente", with_core=with_core)
    if result is None:
        return None
    placed, corridors, entrance, advisories = result
    advisories = ["Forma en H: dos barras unidas por un puente de "
                  "pasillo; mucha fachada y ventilación cruzada."]
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _shape_cruz(data: BuildingWizardData, level: LevelSpec,
                ordered: Sequence[RoomSpec], mirror: bool, rise: float,
                with_stair: bool, with_core: bool = False
                ) -> Optional[ShapedPlan]:
    """En cruz: barra frontal + barra trasera + espina con locales."""
    split = _split_by_width(ordered, 0.35, reserve=3)
    if split is None:
        return None
    front, rest = list(split[0]), list(split[1])
    split2 = _split_by_width(rest, 0.5, reserve=2)
    if split2 is None:
        return None
    rear, spine_rooms = list(split2[0]), list(split2[1])
    columns = _balance_columns(spine_rooms, 2)
    left, right = columns
    if mirror:
        left, right = right, left
    result = _double_bar_layout(
        data, level, front, rear, ((left, "right"), (right, "left")),
        mirror, rise, with_stair,
        max(3.0, sum(r.width_m for r in left),
            sum(r.width_m for r in right)), "espina",
        with_core=with_core)
    if result is None:
        return None
    placed, corridors, entrance, advisories = result
    advisories = ["Forma en cruz: brazos que se cruzan en el núcleo de "
                  "circulación; el clásico de hospitales y escuelas."]
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _shape_articulada(data: BuildingWizardData, level: LevelSpec,
                      ordered: Sequence[RoomSpec], mirror: bool,
                      rise: float, with_stair: bool,
                      with_core: bool = False
                      ) -> Optional[ShapedPlan]:
    """Articulada: dos barras desfasadas unidas por un eslabón largo."""
    split = _split_by_width(ordered, 0.5, reserve=2)
    if split is None:
        return None
    result = _double_bar_layout(data, level, list(split[0]),
                                list(split[1]), (), mirror, rise,
                                with_stair, 3.0, "eslabón",
                                with_core=with_core)
    if result is None:
        return None
    placed, corridors, entrance, advisories = result
    advisories = ["Forma articulada: bloques unidos por un eslabón de "
                  "pasillo; crece por etapas y se adapta al terreno."]
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


# -- Formas compuestas + patio central (v2.5.0): envoltorios que piden
#    a cada forma su versión con el patio abrazado/como espina.

def _shape_L_patio(data: BuildingWizardData, level: LevelSpec,
                   ordered: Sequence[RoomSpec], mirror: bool, rise: float,
                   with_stair: bool, with_core: bool = False
                   ) -> Optional[ShapedPlan]:
    """En L con patio abrazado: la esquina interior se vuelve patio."""
    return _shape_L(data, level, ordered, mirror, rise, with_stair,
                    with_core=with_core, patio_center=True)


def _shape_T_patio(data: BuildingWizardData, level: LevelSpec,
                   ordered: Sequence[RoomSpec], mirror: bool, rise: float,
                   with_stair: bool, with_core: bool = False
                   ) -> Optional[ShapedPlan]:
    """En T con patio central: la espina se vuelve patio."""
    return _shape_T(data, level, ordered, mirror, rise, with_stair,
                    with_core=with_core, patio_center=True)


def _shape_H_patio(data: BuildingWizardData, level: LevelSpec,
                   ordered: Sequence[RoomSpec], mirror: bool, rise: float,
                   with_stair: bool, with_core: bool = False
                   ) -> Optional[ShapedPlan]:
    """En H con patio central: dos barras abrazan un patio con galería."""
    split = _split_by_width(ordered, 0.45, reserve=2)
    if split is None:
        return None
    result = _double_bar_layout(data, level, list(split[0]),
                                list(split[1]), (), mirror, rise,
                                with_stair, 3.0, "patio central",
                                with_core=with_core, patio_center=True)
    if result is None:
        return None
    placed, corridors, entrance, advisories = result
    advisories = ["Forma en H con patio central: dos barras abrazan un "
                  "patio entre ellas; los locales pegados tienen puerta "
                  "a su galería."]
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _shape_cruz_patio(data: BuildingWizardData, level: LevelSpec,
                      ordered: Sequence[RoomSpec], mirror: bool,
                      rise: float, with_stair: bool,
                      with_core: bool = False
                      ) -> Optional[ShapedPlan]:
    """En cruz con patio central: los brazos nacen del patio."""
    split = _split_by_width(ordered, 0.35, reserve=3)
    if split is None:
        return None
    front, rest = list(split[0]), list(split[1])
    split2 = _split_by_width(rest, 0.5, reserve=2)
    if split2 is None:
        return None
    rear, spine_rooms = list(split2[0]), list(split2[1])
    columns = _balance_columns(spine_rooms, 2)
    left, right = columns
    if mirror:
        left, right = right, left
    result = _double_bar_layout(
        data, level, front, rear, ((left, "right"), (right, "left")),
        mirror, rise, with_stair,
        max(3.0, sum(r.width_m for r in left),
            sum(r.width_m for r in right)), "patio central",
        with_core=with_core, patio_center=True)
    if result is None:
        return None
    placed, corridors, entrance, advisories = result
    advisories = ["Forma en cruz con patio central: los brazos nacen de "
                  "un patio que ilumina y ventila el corazón del "
                  "edificio."]
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


def _shape_articulada_patio(data: BuildingWizardData, level: LevelSpec,
                            ordered: Sequence[RoomSpec], mirror: bool,
                            rise: float, with_stair: bool,
                            with_core: bool = False
                            ) -> Optional[ShapedPlan]:
    """Articulada con patio central: el eslabón se vuelve patio."""
    split = _split_by_width(ordered, 0.5, reserve=2)
    if split is None:
        return None
    result = _double_bar_layout(data, level, list(split[0]),
                                list(split[1]), (), mirror, rise,
                                with_stair, 3.0, "patio central",
                                with_core=with_core, patio_center=True)
    if result is None:
        return None
    placed, corridors, entrance, advisories = result
    advisories = ["Forma articulada con patio central: los bloques "
                  "crecen alrededor de un patio abierto compartido."]
    if rise > 0.0:
        advisories.append(_rise_advisory(level.name, rise, with_stair))
    return placed, corridors, entrance, advisories


SHAPED_SCHEMES = {
    "en_L": _shape_L,
    "en_T": _shape_T,
    "en_U": _shape_U,
    "en_H": _shape_H,
    "en_cruz": _shape_cruz,
    "articulada": _shape_articulada,
    "en_L_patio": _shape_L_patio,
    "en_T_patio": _shape_T_patio,
    "en_H_patio": _shape_H_patio,
    "en_cruz_patio": _shape_cruz_patio,
    "articulada_patio": _shape_articulada_patio,
}


def share_wall(a: "PlacedRoom", b: "PlacedRoom",
               min_overlap: float = 0.3) -> bool:
    """¿Dos locales colocados comparten pared (con solape suficiente)?"""
    tol = 1e-6
    vertical_touch = abs((a.x + a.w) - b.x) <= tol or \
        abs((b.x + b.w) - a.x) <= tol
    if vertical_touch and min(a.y + a.d, b.y + b.d) - max(a.y, b.y) \
            >= min_overlap - tol:
        return True
    horizontal_touch = abs((a.y + a.d) - b.y) <= tol or \
        abs((b.y + b.d) - a.y) <= tol
    if horizontal_touch and min(a.x + a.w, b.x + b.w) - max(a.x, b.x) \
            >= min_overlap - tol:
        return True
    return False


def _bounds_of_layouts(layouts: Sequence[LevelLayout]
                       ) -> Tuple[float, float, float, float]:
    """Envolvente (min_x, min_y, max_x, max_y) de todos los trazados."""
    xs: List[float] = []
    ys: List[float] = []
    for layout in layouts:
        for pr in layout.all_rooms:
            xs.extend((pr.x, pr.x + pr.w))
            ys.extend((pr.y, pr.y + pr.d))
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _climate_affinity(scheme: str, climate: str) -> float:
    """Qué tan bien respeta el esquema al clima (0–1, explicable)."""
    # v2.5.0: las formas compuestas con patio central heredan la
    # respuesta climática del patio (la galería tropical).
    if scheme.endswith("_patio"):
        scheme = "patio"
    table: Dict[str, Dict[str, float]] = {
        "patio": {"Cálido húmedo (tropical lluvioso)": 1.0,
                  "Tropical seco (poca lluvia)": 0.9,
                  "Templado": 0.75,
                  "Frío (necesita calefacción)": 0.55,
                  "Alta montaña": 0.6},
        "doble_crujia": {"Cálido húmedo (tropical lluvioso)": 0.9,
                         "Tropical seco (poca lluvia)": 0.85,
                         "Templado": 0.8,
                         "Frío (necesita calefacción)": 0.9,
                         "Alta montaña": 0.85},
        "lineal": {"Cálido húmedo (tropical lluvioso)": 0.75,
                   "Tropical seco (poca lluvia)": 0.7,
                   "Templado": 0.75,
                   "Frío (necesita calefacción)": 0.85,
                   "Alta montaña": 0.8},
        "en_L": {"Cálido húmedo (tropical lluvioso)": 0.85,
                 "Tropical seco (poca lluvia)": 0.8,
                 "Templado": 0.8,
                 "Frío (necesita calefacción)": 0.7,
                 "Alta montaña": 0.75},
        "en_T": {"Cálido húmedo (tropical lluvioso)": 0.8,
                 "Tropical seco (poca lluvia)": 0.8,
                 "Templado": 0.8,
                 "Frío (necesita calefacción)": 0.75,
                 "Alta montaña": 0.75},
        "en_U": {"Cálido húmedo (tropical lluvioso)": 0.85,
                 "Tropical seco (poca lluvia)": 0.8,
                 "Templado": 0.75,
                 "Frío (necesita calefacción)": 0.6,
                 "Alta montaña": 0.65},
        "en_H": {"Cálido húmedo (tropical lluvioso)": 0.9,
                 "Tropical seco (poca lluvia)": 0.85,
                 "Templado": 0.8,
                 "Frío (necesita calefacción)": 0.7,
                 "Alta montaña": 0.75},
        "en_cruz": {"Cálido húmedo (tropical lluvioso)": 0.85,
                    "Tropical seco (poca lluvia)": 0.8,
                    "Templado": 0.8,
                    "Frío (necesita calefacción)": 0.7,
                    "Alta montaña": 0.7},
        "articulada": {"Cálido húmedo (tropical lluvioso)": 0.8,
                       "Tropical seco (poca lluvia)": 0.8,
                       "Templado": 0.8,
                       "Frío (necesita calefacción)": 0.8,
                       "Alta montaña": 0.8},
    }
    return table.get(scheme, {}).get(climate, 0.75)


def _variant_layouts(data: BuildingWizardData, scheme: str,
                     mirror: bool
                     ) -> Tuple[List[LevelLayout], List[str]]:
    """Traza todos los niveles del esquema pedido (con o sin espejo)."""
    core = core_wanted(data)
    if scheme == "lineal":
        if not mirror:
            return build_layout(data, with_core=core)
        data2 = _shallow_copy(data)
        data2.rooms = []
        for level in data.levels:
            rooms = data.rooms_of_level(level.name)
            data2.rooms.extend(reversed(rooms))
        return build_layout(data2, with_core=core)
    layouts: List[LevelLayout] = []
    advisories: List[str] = []
    entrance_done = False
    rise = terrain_rise_m(data.terrain_type)
    shape_fn = SHAPED_SCHEMES.get(scheme)
    core_noted = False
    for level in data.levels:
        rooms = order_rooms_for_level(data.rooms_of_level(level.name),
                                      data.relations)
        if not rooms:
            continue
        if shape_fn is not None:
            # Formas compuestas (v2.3.0): L, T, U, H, cruz, articulada
            # y sus versiones con patio central (v2.5.0).
            with_stair = stairs_wanted(data) and (rise > 0.0
                                                  or not entrance_done)
            result = shape_fn(data, level, rooms, mirror, rise,
                              with_stair, core)
            if result is None:
                advisories.append(
                    f"La forma «{SCHEME_LABELS[scheme]}» necesita más "
                    f"locales en «{level.name}»: ese nivel se omitió "
                    "en esta variante.")
                continue
            placed, corridors, entrance, shape_advisories = result
            advisories.extend(shape_advisories)
            if core and not core_noted:
                advisories.append(
                    "Núcleo rígido en la esquina frontal: concentra "
                    "escalera, baños y ductos entre muros estructurales.")
                core_noted = True
            layout, entrance_done = _assemble_composed_level(
                data, level, placed, corridors, entrance, entrance_done,
                advisories)
            layouts.append(layout)
            continue
        with_stair = stairs_wanted(data) and (rise > 0.0
                                              or not entrance_done)
        layout, entrance_done = _layout_two_bay_level(
            data, level, rooms, patio=(scheme == "patio"),
            swap_rows=mirror, with_entrance=True,
            entrance_done=entrance_done, with_stair=with_stair,
            with_core=core)
        layouts.append(layout)
        advisories.extend(layout.advisories)
    if not layouts:
        advisories.append("No hay locales para trazar: añade locales en "
                          "el paso de locales.")
    return layouts, advisories


def _variant_metrics(data: BuildingWizardData,
                     layouts: Sequence[LevelLayout],
                     scheme: str) -> Dict[str, float]:
    """Métricas explicables de una variante (todas 0–1)."""
    # Adyacencias declaradas satisfechas (comparten pared).
    total_rel = 0
    ok_rel = 0
    for rel in data.relations:
        for layout in layouts:
            rooms = {pr.name: pr for pr in layout.all_rooms}
            if rel.a_name in rooms and rel.b_name in rooms:
                total_rel += 1
                if share_wall(rooms[rel.a_name], rooms[rel.b_name]):
                    ok_rel += 1
                break
    adyacency = (ok_rel / total_rel) if total_rel else 0.7

    # Luz natural: ventanas colocadas frente a las pedidas.
    wanted = sum(1 for layout in layouts
                 for pr in layout.rooms if pr.with_window)
    got = sum(len(layout.windows) for layout in layouts)
    daylight = min(1.0, got / wanted) if wanted else 0.8

    # Compacidad: área útil entre la envolvente total.
    min_x, min_y, max_x, max_y = _bounds_of_layouts(layouts)
    envelope = max((max_x - min_x) * (max_y - min_y), 1e-6)
    useful = sum(layout.total_area_m2() for layout in layouts)
    compact = min(1.0, useful / envelope)

    # Ventilación cruzada: dos frentes de fachada ayudan mucho.
    vent = 1.0 if scheme != "lineal" else 0.55
    if not data.cross_ventilation:
        vent = round(vent * 0.85, 3)

    climate = _climate_affinity(scheme, data.climate)
    forma = shape_affinity(
        getattr(data, "plan_shape", PLAN_SHAPES[0]), scheme)
    return {
        "Adyacencias": round(adyacency, 3),
        "Luz natural": round(daylight, 3),
        "Compacidad": round(compact, 3),
        "Ventilación cruzada": round(vent, 3),
        "Afinidad al clima": round(climate, 3),
        "Forma elegida": round(forma, 3),
    }


def _weighted_score(metrics: Dict[str, float]) -> float:
    """Puntuación 0–100: adyacencias 25 %, luz 15 %, compacidad 15 %,
    ventilación 10 %, clima 15 % y forma elegida 20 %."""
    score = (0.25 * metrics["Adyacencias"]
             + 0.15 * metrics["Luz natural"]
             + 0.15 * metrics["Compacidad"]
             + 0.10 * metrics["Ventilación cruzada"]
             + 0.15 * metrics["Afinidad al clima"]
             + 0.20 * metrics["Forma elegida"])
    return round(100.0 * score, 1)


# -- DISEÑO ORGÁNICO (v3.2.0) --------------------------------------------------
# Distribución interior articulada: fondos escalonados, chaflanes a
# 45° o radones en las esquinas de la envolvente, fachada en arco y
# pasillo serpenteante. Todo se materializa como MUROS RECTOS CORTOS
# (polilíneas), así vanos, QTO, representación y exportadores no
# cambian. Reglas de seguridad:
#   - NUNCA se curva/recorta un muro con vanos (los vanos apuntan al
#     muro por índice y su posición es a lo largo del muro recto).
#   - NUNCA se toca una pared compartida entre dos espacios (los dos
#     lados tienen locales: se detecta GEOMÉTRICAMENTE, no por conteo
#     de fuentes, porque una fachada fusionada también tiene varias).
#   - El pasillo conserva su ancho mínimo (1,20 m) en todo punto.

_ORGANIC_SEG_M = 0.7          # longitud objetivo de cada tramo de arco
_ORGANIC_MIN_WALL_M = 4.5     # fachada mínima para arco/curva
_ORGANIC_MIN_CORNER_M = 1.6   # arista mínima para chaflán/radón


def _organic_is_exterior(wall: Dict[str, Any],
                         rooms: Dict[str, PlacedRoom]) -> bool:
    """¿El muro da al exterior? (ningún local al otro lado).

    Comparte pared = hay un local a cada lado. Una fachada fusionada
    tiene muchos «sources» pero TODOS del mismo lado; un pasillo que
    solo aparece en «sources» se resuelve igual (está en all_rooms).
    """
    (x1, y1), (x2, y2) = wall["start"], wall["end"]
    horizontal = abs(y1 - y2) <= 1e-6
    fixed = y1 if horizontal else x1
    sides: set = set()
    for name in wall.get("sources", []):
        room = rooms.get(name)
        if room is None:
            continue
        if horizontal:
            if abs((room.y + room.d) - fixed) <= 1e-6:
                sides.add(-1)   # local por debajo
            if abs(room.y - fixed) <= 1e-6:
                sides.add(+1)   # local por encima
        else:
            if abs((room.x + room.w) - fixed) <= 1e-6:
                sides.add(-1)   # local a la izquierda
            if abs(room.x - fixed) <= 1e-6:
                sides.add(+1)   # local a la derecha
    return sides != {+1, -1}


def _organic_room_side(wall: Dict[str, Any],
                       rooms: Dict[str, PlacedRoom]) -> int:
    """Lado donde está el local de un muro exterior: +1 = arriba/derecha,
    -1 = abajo/izquierda (para abultar el arco HACIA FUERA)."""
    (x1, y1), (x2, y2) = wall["start"], wall["end"]
    horizontal = abs(y1 - y2) <= 1e-6
    fixed = y1 if horizontal else x1
    for name in wall.get("sources", []):
        room = rooms.get(name)
        if room is None:
            continue
        if horizontal:
            if abs(room.y - fixed) <= 1e-6:
                return +1
            if abs((room.y + room.d) - fixed) <= 1e-6:
                return -1
        else:
            if abs(room.x - fixed) <= 1e-6:
                return +1
            if abs((room.x + room.w) - fixed) <= 1e-6:
                return -1
    return +1


def _organic_seg_dict(a: Tuple[float, float], b: Tuple[float, float],
                      sources: List[str], curve: bool = False,
                      tag: str = "") -> Dict[str, Any]:
    """Dict de muro para un tramo de polilínea orgánica.

    «tag» marca el origen del gesto («corner», «s», «arco») para que
    las pruebas y la representación sepan qué auditar.
    """
    seg: Dict[str, Any] = {
        "start": a, "end": b,
        "length": round(math.hypot(b[0] - a[0], b[1] - a[1]), 6),
        "sources": list(sources)}
    if curve:
        seg["curve"] = True
    if tag:
        seg[tag] = True
    return seg


def _organic_replace_with_polyline(wall: Dict[str, Any],
                                   points: List[Tuple[float, float]],
                                   curve: bool = True) -> List[Dict[str, Any]]:
    """Convierte un muro en los tramos rectos de su polilínea."""
    sources = list(wall.get("sources", []))
    segments: List[Dict[str, Any]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if math.hypot(b[0] - a[0], b[1] - a[1]) <= 1e-6:
            continue
        segments.append(_organic_seg_dict(a, b, sources, curve))
    return segments


def organicize_level(layout: "LevelLayout",
                     data: "BuildingWizardData") -> List[str]:
    """Aplica curvas y chaflanes a la envolvente de UN nivel.

    Devuelve notas amables (nunca lanza). Muta el layout: los muros
    curvos se expanden in-place a tramos rectos y los «wall_index» de
    los vanos se remapean por identidad del dict, así el plan, la
    preview y el proyecto final quedan consistentes. Un mismo muro
    puede recibir VARIOS gestos (p. ej. radón en ambos extremos): el
    trabajo corre sobre «piezas» actuales de cada muro original.
    """
    from core.geometry.organic import (arc_polyline, chamfer_points,
                                       fillet_points, s_curve_polyline)

    mode = data.distribucion
    if mode not in ("articulada", "organica"):
        return []
    curv = max(0.3, min(float(data.curvatura_m or 1.5), 3.0))
    walls = list(layout.walls)
    openings = list(layout.doors) + list(layout.windows)
    with_opening = {op.wall_index for op in openings
                    if 0 <= op.wall_index < len(walls)}
    rooms = {pr.name: pr for pr in layout.all_rooms}
    stats = {"esquinas": 0, "arco": 0, "pasillo": 0}

    # current[orig] -> piezas actuales del muro original (1 = intacto).
    current: Dict[int, List[Dict[str, Any]]] = {
        i: [walls[i]] for i in range(len(walls))}

    def piece_at_end(orig: int, pt: Tuple[float, float]
                     ) -> Optional[Dict[str, Any]]:
        for piece in current[orig]:
            for end in (piece["start"], piece["end"]):
                if abs(end[0] - pt[0]) <= 1e-6 \
                        and abs(end[1] - pt[1]) <= 1e-6:
                    return piece
        return None

    def piece_other_end(piece: Dict[str, Any],
                        pt: Tuple[float, float]) -> Tuple[float, float]:
        s, e = piece["start"], piece["end"]
        if abs(s[0] - pt[0]) <= 1e-6 and abs(s[1] - pt[1]) <= 1e-6:
            return e
        return s

    def replace_piece(orig: int, piece: Dict[str, Any],
                      new_pieces: List[Dict[str, Any]]) -> None:
        lst = current[orig]
        for k, p in enumerate(lst):
            if p is piece:
                lst[k:k + 1] = new_pieces
                return

    def usable(piece: Dict[str, Any], orig: int) -> bool:
        return (orig not in with_opening
                and piece["length"] > 1e-3
                and _organic_is_exterior(piece, rooms))

    # -- 1) esquinas de la envolvente: radón (orgánica) o chaflán 45° --
    max_corners = 4 if mode == "organica" else 3
    h_idx = [i for i, w in enumerate(walls)
             if abs(w["start"][1] - w["end"][1]) <= 1e-6]
    v_idx = [i for i, w in enumerate(walls)
             if abs(w["start"][0] - w["end"][0]) <= 1e-6]
    corners: List[Tuple[float, float, int, int]] = []
    for i in h_idx:
        for j in v_idx:
            wi, wj = walls[i], walls[j]
            for pi in (wi["start"], wi["end"]):
                for pj in (wj["start"], wj["end"]):
                    if abs(pi[0] - pj[0]) <= 1e-6 \
                            and abs(pi[1] - pj[1]) <= 1e-6:
                        corners.append((pi[0], pi[1], i, j))
    corners.sort(key=lambda c: (c[0], c[1]))

    # Vanos por muro ORIGINAL (offsets medidos desde el inicio del muro
    # normalizado). Los recortes de esquina MANTIENEN el muro recto, así
    # que un vano es compatible si el recorte no alcanza su rango; al
    # recortar por el inicio, los offsets de ese muro se corren -cut.
    by_orig: Dict[int, List["OpeningPlacement"]] = {}
    for op in openings:
        if 0 <= op.wall_index < len(walls):
            by_orig.setdefault(op.wall_index, []).append(op)

    def corner_limit(piece: Dict[str, Any], orig: int,
                     at_start: bool) -> Tuple[float, bool]:
        """(recorte máximo permitido por vanos, hay_vanos)."""
        ops = by_orig.get(orig) or []
        if not ops:
            return piece["length"], False
        margin = 0.25
        if at_start:
            nearest = min(op.offset_m for op in ops)
            return max(0.0, nearest - margin), True
        farthest = max(op.offset_m + op.width_m for op in ops)
        return max(0.0, piece["length"] - farthest - margin), True

    def shift_openings(orig: int, delta: float) -> None:
        for op in by_orig.get(orig, []):
            op.offset_m = max(0.0, op.offset_m + delta)

    for cx, cy, i, j in corners:
        if stats["esquinas"] >= max_corners:
            break
        piece_h = piece_at_end(i, (cx, cy))
        piece_v = piece_at_end(j, (cx, cy))
        if piece_h is None or piece_v is None or piece_h is piece_v:
            continue
        if piece_h["length"] < _ORGANIC_MIN_CORNER_M or \
                piece_v["length"] < _ORGANIC_MIN_CORNER_M:
            continue
        h_at_start = abs(piece_h["start"][0] - cx) <= 1e-6 and \
            abs(piece_h["start"][1] - cy) <= 1e-6
        v_at_start = abs(piece_v["start"][0] - cx) <= 1e-6 and \
            abs(piece_v["start"][1] - cy) <= 1e-6
        limit_h, has_h = corner_limit(piece_h, i, h_at_start)
        limit_v, has_v = corner_limit(piece_v, j, v_at_start)
        if i in with_opening and not has_h:
            continue   # vanos sin offset fiable: no tocar
        if j in with_opening and not has_v:
            continue
        if not _organic_is_exterior(piece_h, rooms):
            continue   # partición o pared compartida: nunca se toca
        if not _organic_is_exterior(piece_v, rooms):
            continue
        cut = min(curv, 0.45 * piece_h["length"],
                  0.45 * piece_v["length"], limit_h, limit_v)
        if cut < 0.4:
            continue
        h_other = piece_other_end(piece_h, (cx, cy))
        v_other = piece_other_end(piece_v, (cx, cy))
        sources = list(piece_h.get("sources", []))

        def resize(piece: Dict[str, Any], new_a: Tuple[float, float],
                   new_b: Tuple[float, float]) -> None:
            """Muta la pieza IN SITU (identidad preservada para vanos)."""
            piece["start"] = new_a
            piece["end"] = new_b
            piece["length"] = round(math.hypot(new_b[0] - new_a[0],
                                               new_b[1] - new_a[1]), 6)

        def arc_segs(points: List[Tuple[float, float]]
                     ) -> List[Dict[str, Any]]:
            segs: List[Dict[str, Any]] = []
            for k in range(len(points) - 1):
                a, b = points[k], points[k + 1]
                if math.hypot(b[0] - a[0], b[1] - a[1]) <= 1e-6:
                    continue
                segs.append(_organic_seg_dict(a, b, sources, curve=True,
                                              tag="corner"))
            return segs

        if mode == "organica":
            arc_pts = fillet_points((cx, cy), h_other, v_other, cut,
                                    segments=max(6, int(cut * 6)))
            if len(arc_pts) < 2:
                continue
            t1, t2 = arc_pts[0], arc_pts[-1]
            # La pieza original queda como el tramo recto con vanos.
            if h_at_start:
                resize(piece_h, t1, h_other)
            else:
                resize(piece_h, h_other, t1)
            if v_at_start:
                resize(piece_v, t2, v_other)
            else:
                resize(piece_v, v_other, t2)
            # El radón viaja con el muro H (dicts NUEVOS, sin vanos).
            replace_piece(i, piece_h,
                          [piece_h] + arc_segs(arc_pts))
            replace_piece(j, piece_v, [piece_v])
            stats["esquinas"] += 1
        else:
            a_h, a_v = chamfer_points((cx, cy), h_other, v_other, cut)
            if math.hypot(a_h[0] - a_v[0], a_h[1] - a_v[1]) <= 0.25:
                continue
            if h_at_start:
                resize(piece_h, a_h, h_other)
            else:
                resize(piece_h, h_other, a_h)
            if v_at_start:
                resize(piece_v, a_v, v_other)
            else:
                resize(piece_v, v_other, a_v)
            replace_piece(i, piece_h,
                          [piece_h,
                           _organic_seg_dict(a_h, a_v, sources,
                                             tag="corner")])
            replace_piece(j, piece_v, [piece_v])
            stats["esquinas"] += 1
        # El recorte por el inicio corre los vanos de ese muro (offset
        # medido desde el inicio normalizado).
        if h_at_start:
            shift_openings(i, -cut)
        if v_at_start:
            shift_openings(j, -cut)

    # -- 2) pasillo serpenteante: su muro exterior ondula en S ---------
    corridor_width = float(data.corridor_width_m or 1.2)
    amp_cap = (corridor_width - 1.2) * (0.5 if mode == "organica" else 0.35)
    if amp_cap > 0.15:
        best = None  # (length, orig, piece)
        for orig, pieces in current.items():
            for piece in pieces:
                sources = piece.get("sources", [])
                if len(sources) != 1 or \
                        not sources[0].startswith("Pasillo"):
                    continue
                if abs(piece["start"][1] - piece["end"][1]) > 1e-6:
                    continue
                if piece.get("corner"):
                    continue  # ya es remate de esquina
                if piece["length"] >= 6.0 and usable(piece, orig) and \
                        (best is None or piece["length"] > best[0]):
                    best = (piece["length"], orig, piece)
        if best is not None:
            _len, orig, piece = best
            amplitude = min(curv * 0.5, amp_cap)
            pts = s_curve_polyline(
                piece["start"], piece["end"], amplitude,
                segments=max(10, int(_len / _ORGANIC_SEG_M)))
            reemplazo = _organic_replace_with_polyline(piece, pts)
            for seg in reemplazo:
                seg["s"] = True
            replace_piece(orig, piece, reemplazo)
            stats["pasillo"] += 1

    # -- 3) fachada en arco (solo orgánica): la pieza exterior más ----
    #      larga sin vanos, en cualquier frente del bounding box.
    if mode == "organica":
        all_pieces = [p for pieces in current.values() for p in pieces]
        hz = [p for p in all_pieces
              if abs(p["start"][1] - p["end"][1]) <= 1e-6]
        vt = [p for p in all_pieces
              if abs(p["start"][0] - p["end"][0]) <= 1e-6]
        ys = [p["start"][1] for p in hz] or [0.0]
        xs = [p["start"][0] for p in vt] or [0.0]
        min_y, max_y, min_x, max_x = min(ys), max(ys), min(xs), max(xs)

        def on_face(piece: Dict[str, Any]) -> bool:
            if abs(piece["start"][1] - piece["end"][1]) <= 1e-6:
                y = piece["start"][1]
                return abs(y - min_y) <= 1e-6 or abs(y - max_y) <= 1e-6
            x = piece["start"][0]
            return abs(x - min_x) <= 1e-6 or abs(x - max_x) <= 1e-6

        best = None  # (length, orig, piece)
        for orig, pieces in current.items():
            for piece in pieces:
                if piece["length"] < _ORGANIC_MIN_WALL_M:
                    continue
                if not on_face(piece) or not usable(piece, orig):
                    continue
                if best is None or piece["length"] > best[0]:
                    best = (piece["length"], orig, piece)
        if best is not None:
            _len, orig, piece = best
            bulge = min(curv, 0.3 * _len)
            side = _organic_room_side(piece, rooms)
            # Avance normalizado (+x en horizontales, +y en verticales):
            # la izquierda del tramo es +y o -x respectivamente; abultar
            # hacia FUERA del local es siempre el lado contrario.
            direction = -side
            pts = arc_polyline(piece["start"], piece["end"],
                               direction * bulge,
                               segments=max(8, int(_len / _ORGANIC_SEG_M)))
            reemplazo = _organic_replace_with_polyline(piece, pts)
            for seg in reemplazo:
                seg["arco"] = True
            replace_piece(orig, piece, reemplazo)
            stats["arco"] += 1

    if not any(current.values()):
        return []

    # -- materializar: expandir in-place y remapear vanos por identidad -
    final: List[Dict[str, Any]] = []
    for i in range(len(walls)):
        final.extend(current[i])
    layout.walls = final
    id_map = {id(w): k for k, w in enumerate(final)}
    for op in openings:
        if 0 <= op.wall_index < len(walls):
            op.wall_index = id_map.get(id(walls[op.wall_index]),
                                       op.wall_index)

    notes: List[str] = []
    detail: List[str] = []
    if stats["esquinas"]:
        detail.append(f"{stats['esquinas']} esquinas "
                      + ("redondeadas" if mode == "organica"
                         else "con chaflán a 45°"))
    if stats["arco"]:
        detail.append("fachada en arco")
    if stats["pasillo"]:
        detail.append("pasillo serpenteante")
    if detail:
        mode_name = distribution_label(mode).split(" (")[0].lower()
        notes.append("Distribución " + mode_name + ": "
                     + ", ".join(detail) + ".")
    return notes


def apply_distribucion(data: "BuildingWizardData",
                       layouts: Sequence["LevelLayout"]) -> List[str]:
    """Aplica el estilo de distribución interior a los niveles trazados.

    «ortogonal» no hace nada. «articulada» y «organica» curvan la
    envolvente (esquinas, fachada y pasillo) SIN tocar paredes con
    vanos ni paredes compartidas. Idempotente por layout (marca
    ``_organic_done``), así generate_variants y build_plan nunca la
    aplican dos veces.
    """
    if getattr(data, "distribucion", "ortogonal") not in ("articulada",
                                                          "organica"):
        return []
    notes: List[str] = []
    for layout in layouts:
        if getattr(layout, "_organic_done", False):
            continue
        try:
            notes.extend(organicize_level(layout, data))
        except Exception:  # noqa: BLE001 — el gesto orgánico no bloquea
            continue
        layout._organic_done = True
    return notes


def generate_variants(data: BuildingWizardData) -> List[PlantVariant]:
    """Genera y puntúa todas las variantes de planta (14 esquemas × 2).

    Las variantes que no caben en las dimensiones del paso 1 no se
    excluyen: quedan al final con una nota de cuánto terreno piden, y
    su puntuación queda penalizada. La lista viene ordenada de mejor a
    peor; «rank» (1, 2, 3…) marca esa posición.

    v3.32.0: los multiplicadores de niveles se expanden primero — la
    variante se puntúa sobre el EDIFICIO entero (todas las copias de
    cada planta tipo), no sobre una sola planta.
    """
    data = expandir_datos(data)
    combos: Tuple[Tuple[str, bool], ...] = (
        ("doble_crujia", False), ("doble_crujia", True),
        ("patio", False), ("patio", True),
        ("lineal", False), ("lineal", True),
        ("en_L", False), ("en_L", True),
        ("en_L_patio", False), ("en_L_patio", True),
        ("en_T", False), ("en_T", True),
        ("en_T_patio", False), ("en_T_patio", True),
        ("en_U", False), ("en_U", True),
        ("en_H", False), ("en_H", True),
        ("en_H_patio", False), ("en_H_patio", True),
        ("en_cruz", False), ("en_cruz", True),
        ("en_cruz_patio", False), ("en_cruz_patio", True),
        ("articulada", False), ("articulada", True),
        ("articulada_patio", False), ("articulada_patio", True),
    )
    variants: List[PlantVariant] = []
    for scheme, mirror in combos:
        layouts, advisories = _variant_layouts(data, scheme, mirror)
        if not layouts:
            continue
        organic_notes = apply_distribucion(data, layouts)
        advisories.extend(organic_notes)
        metrics = _variant_metrics(data, layouts, scheme)
        score = _weighted_score(metrics)
        min_x, min_y, max_x, max_y = _bounds_of_layouts(layouts)
        needed = (round(max_x - min_x, 2), round(max_y - min_y, 2))
        fits = True
        if data.lot_width_m > 0 and needed[0] > data.lot_width_m + 1e-6:
            fits = False
        if data.lot_depth_m > 0 and needed[1] > data.lot_depth_m + 1e-6:
            fits = False
        if not fits:
            score = round(score * 0.15, 1)
        suffix = " · espejo" if mirror else ""
        variants.append(PlantVariant(
            key=f"{scheme}{'+' if mirror else ''}" +
                ("espejo" if mirror else ""),
            scheme=scheme, mirror=mirror,
            title=f"{SCHEME_LABELS[scheme]}{suffix}",
            description=SCHEME_DESCRIPTIONS[scheme],
            layouts=layouts, advisories=advisories,
            metrics=metrics, score=score, fits_lot=fits,
            lot_needed=needed))
    variants.sort(key=lambda v: (-v.score, v.key))
    for rank, variant in enumerate(variants, start=1):
        variant.rank = rank
    return variants


# -- Requerimientos (metadata de cada entidad) -----------------------------------

def _dna_of(ctx: Any, space_type: str) -> Any:
    """DNA del tipo de local: del proyecto, o del conocimiento base.

    Si no hay contexto (pruebas headless, CLI futura) se carga el
    registro de resources/knowledge: el DNA es ayuda, nunca bloquea.
    """
    registry = getattr(ctx, "dna_registry", None)
    if registry is None or len(registry) == 0:
        try:
            from app.paths import resource_path
            from domain.knowledge import SpaceDNARegistry
            registry = SpaceDNARegistry()
            registry.load_file(resource_path("knowledge",
                                             "space_dna.json"))
        except Exception:  # noqa: BLE001 — sin DNA no se sugiere nada
            return None
    try:
        return registry.get(space_type)
    except Exception:  # noqa: BLE001 — DNA es ayuda, nunca bloquea
        return None


def room_requirements(data: BuildingWizardData, room: RoomSpec,
                      ctx: Any = None) -> Dict[str, Any]:
    """Requerimientos climáticos/arquitectónicos/estructurales del local.

    Combina lo pedido por el usuario con el conocimiento Space DNA del
    tipo de local (ventilación, iluminación, zona húmeda, área mínima,
    accesibilidad…). Sin DNA registrado, devuelve lo básico.
    """
    dna = _dna_of(ctx, room.space_type)
    climatic: Dict[str, Any] = {
        "zona_climatica": data.climate,
        "ventilacion_cruzada": data.cross_ventilation,
    }
    architectural: Dict[str, Any] = {
        "tipo": room.space_type,
        "ancho_m": room.width_m,
        "fondo_m": room.depth_m,
    }
    structural: Dict[str, Any] = {
        "sistema": data.structural_system,
    }
    if dna is not None:
        climatic["ventilacion_natural"] = bool(getattr(dna, "ventilation",
                                                       False))
        climatic["iluminacion_natural"] = bool(getattr(dna, "daylight",
                                                       False))
        architectural.update({
            "nombre_conocido": getattr(dna, "name_es", ""),
            "area_minima_m2": getattr(dna, "minimum_area", None),
            "ancho_minimo_m": getattr(dna, "minimum_width", None),
            "altura_libre_min_m": getattr(dna, "height", None),
            "accesibilidad": bool(getattr(dna, "accessibility", False)),
            "zona_humeda": bool(getattr(dna, "wet_zone", False)),
            "privacidad_0a5": getattr(dna, "privacy", 0),
        })
        # Requerimientos técnicos del DNA hospitalario (v2.2.0).
        meta = getattr(dna, "metadata", {}) or {}
        if meta.get("requiere_hvac"):
            climatic["aire_acondicionado"] = True
        if meta.get("presion"):
            climatic["presion_requerida"] = meta["presion"]
        if meta.get("oxigeno_medicinal"):
            climatic["oxigeno_medicinal"] = True
        if meta.get("radiacion"):
            architectural["proteccion_radiologica"] = meta["radiacion"]
        if meta.get("extraccion_forzada"):
            climatic["extraccion_forzada"] = True
        # NORMATIVA NEUFERT (v2.7.0): criterios dimensionales del
        # libro para este tipo de local (puerta, referencia y regla).
        neufert = meta.get("neufert") or {}
        if neufert:
            architectural["normativa_neufert"] = {
                "fuente": _neufert_fuente(),
                "puerta_sugerida_m": neufert.get("puerta_m"),
                "referencia": neufert.get("ref", ""),
                "criterio": neufert.get("nota", ""),
            }
    return {
        "climaticos": climatic,
        "arquitectonicos": architectural,
        "estructurales": structural,
        "origen": "asistente de edificación v2.1.0",
    }


def dna_advisories(data: BuildingWizardData, ctx: Any = None) -> List[str]:
    """Avisos del conocimiento técnico (no bloquean la generación)."""
    advisories: List[str] = []
    seen: set = set()
    for room in data.rooms:
        dna = _dna_of(ctx, room.space_type)
        if dna is None:
            continue
        area = room.width_m * room.depth_m
        minimum = getattr(dna, "minimum_area", None)
        if minimum is not None and area + 1e-9 < minimum:
            advisories.append(
                f"«{room.name}» mide {area:.1f} m² y el conocimiento "
                f"técnico sugiere al menos {minimum:.1f} m² para "
                f"{getattr(dna, 'name_es', room.space_type)}.")
        minimum_width = getattr(dna, "minimum_width", None)
        if minimum_width is not None and room.width_m + 1e-9 < minimum_width:
            advisories.append(
                f"«{room.name}» tiene {room.width_m:.1f} m de ancho; el "
                f"conocimiento técnico sugiere {minimum_width:.1f} m "
                "como mínimo.")
        if getattr(dna, "wet_zone", False):
            advisories.append(
                f"«{room.name}» es zona húmeda: prevé agua, desagüe y "
                "ventilación forzada o natural.")
        # Requerimientos de instalaciones del DNA hospitalario (v2.2.0).
        meta = getattr(dna, "metadata", {}) or {}
        if meta.get("requiere_hvac") and \
                "Ventilación mecánica / A/C" not in data.installations:
            message = (
                f"«{room.name}» ({getattr(dna, 'name_es', '')}) requiere "
                "climatización mecánica: activa el módulo «Ventilación "
                "mecánica / A/C» en el paso bioclimático.")
            if message not in seen:
                seen.add(message)
                advisories.append(message)
        if meta.get("oxigeno_medicinal") and "Gas" not in data.installations:
            message = (
                f"«{room.name}» suele necesitar oxígeno medicinal y vacío "
                "técnico: considera el módulo «Gas».")
            if message not in seen:
                seen.add(message)
                advisories.append(message)
        if meta.get("radiacion"):
            message = (f"«{room.name}» emite radiación: prevé "
                       f"{meta['radiacion']}.")
            if message not in seen:
                seen.add(message)
                advisories.append(message)
    return advisories


def site_advisories(data: BuildingWizardData) -> List[str]:
    """Avisos de sitio: orientación, estilo, terreno y escaleras (v2.3.0).

    Amables y sin bloquear: convierten las decisiones del paso 1 en
    consejos de arquitectura bioclimática y composición.
    """
    advisories: List[str] = []

    # Orientación de la fachada según el clima.
    if data.climate.startswith("Cálido") and data.facade_orientation in (
            "Oeste", "Suroeste", "Noroeste"):
        advisories.append(
            "La fachada principal mira al poniente con clima cálido: "
            "sol fuerte de tarde; profundiza los aleros o añade un "
            "porche.")
    if data.climate.startswith("Frío") and data.facade_orientation in (
            "Norte", "Noreste", "Noroeste"):
        advisories.append(
            "Fachada al norte en clima frío: reserva las fachadas "
            "soleadas para sala, aulas o consultorios y deja la norte "
            "para servicios y depósitos.")
    if data.climate.startswith("Frío") and data.facade_orientation in (
            "Sur", "Sureste", "Suroeste"):
        advisories.append(
            "Fachada al sol en clima frío: excelente captación de "
            "invierno; prevé aleros para el verano.")

    # Estilo arquitectónico: consejo general + coherencia.
    tip = STYLE_DESCRIPTIONS.get(data.architectural_style)
    if tip:
        advisories.append(
            f"Estilo {data.architectural_style}: {tip}")
    if data.architectural_style in ("Colonial cubano",
                                    "Vernáculo tropical",
                                    "Modernista") and (
            not data.protection_solar or data.eaves_m < 0.8):
        advisories.append(
            f"El estilo {data.architectural_style} pide aleros "
            "generosos: sube el alero (0,8–1,0 m) o activa la "
            "protección solar.")
    if data.architectural_style == "Vernáculo tropical" and \
            not data.cross_ventilation:
        advisories.append(
            "El vernáculo tropical vive de la brisa: activa la "
            "ventilación cruzada en el paso 4.")
    affinity = shape_affinity(data.plan_shape, (
        {"En L": "en_L", "En T": "en_T", "En U": "en_U", "En H": "en_H",
         "En cruz": "en_cruz", "Patio central": "patio",
         "Articulada (eslabones)": "articulada",
         "Lineal (barra)": "lineal"}.get(data.plan_shape, "")))
    if data.plan_shape in ("En L", "En T", "En U", "En H", "En cruz",
                           "Patio central", "Articulada (eslabones)") \
            and affinity >= 0.99:
        advisories.append(
            f"La forma «{data.plan_shape}» se materializa en el paso 6: "
            "elige la variante correspondiente de la lista.")
    # v2.4.0: coherencia estilo ↔ forma en planta (solo sugerencia).
    preference = STYLE_SHAPE_PREFERENCE.get(data.architectural_style, ())
    if preference and data.plan_shape not in preference:
        advisories.append(
            f"El estilo {data.architectural_style} luce con formas "
            f"«{preference[0]}» (también {preference[1]}): considera "
            "cambiar la forma en planta del paso 1.")

    # Terreno y desnivel.
    rise = terrain_rise_m(data.terrain_type)
    if rise > 0.0:
        advisories.append(
            f"Terreno {data.terrain_type.lower()}: la planta se "
            f"resuelve con desnivel de {rise:.2f} m entre zonas; prevé "
            "rampa o escalones en los umbrales exteriores.")

    # Escaleras vetadas pero necesarias.
    if data.stairs_mode == STAIR_NEVER and stairs_needed(data):
        advisories.append(
            "Elegiste no colocar escaleras, pero la edificación las "
            "necesita (varios niveles o desnivel): revisa la decisión "
            "o los locales quedarán sin comunicación vertical.")
    # Núcleo rígido vetado pero recomendable (v2.5.0).
    if data.core_mode == CORE_NEVER and core_needed(data):
        advisories.append(
            "Elegiste no colocar núcleo rígido: con varios niveles o "
            "desnivel, concentrar escalera, baños y ductos entre muros "
            "estructurales gana rigidez y ahorro; revísalo si lo "
            "piensas mejor.")
    # Estructura vertical: coherencia tipología ↔ sistema (v2.6.0).
    from core.geometry.structural import structural_mismatch
    _mismatch = structural_mismatch(data.structural_system,
                                    data.construction_type)
    if _mismatch:
        advisories.append(_mismatch)
    return advisories


def neufert_advisories(data: BuildingWizardData, ctx: Any = None
                       ) -> List[str]:
    """Avisos NORMATIVOS de Neufert (v2.7.0): aconsejan, no bloquean.

    Comparemos lo pedido con «El arte de proyectar en arquitectura»:
    pasillo y puerta por uso social (camilla en salud), luz de las
    ventanas (el acristalado suma 1/8 del suelo), altura libre por
    nivel, rampa del desnivel, estacionamiento en usos públicos y el
    alero que la edición regional recomienda.
    """
    registry = _neufert_registry()
    if registry is None:
        return []
    _sync_region(data)
    advisories: List[str] = []

    # 1) Pasillo por uso y por LOCALES (v3.21.0): manda el más
    #    exigente — el uso (Neufert) o el DNA de algún local del
    #    programa (camilla de tomografía, carros de morgue…).
    if data.corridor_enabled:
        rec = registry.corridor_for(data.usage_type)
        rec_locales, culpable = suggested_corridor_width_for_rooms(
            data.usage_type, [r.space_type for r in (data.rooms or [])],
            ctx)
        requerido = max(rec or 0.0, rec_locales)
        if requerido > 0 and data.corridor_width_m + 1e-9 < requerido:
            if culpable:
                nombre = _nombre_de_uso_espacio(culpable, ctx)
                motivo = {
                    2.4: "por «{n}» pasa una camilla",
                    2.0: "hacia «{n}» ruedan camillas y carros",
                    1.8: "«{n}» trabaja con equipos y carros",
                    1.5: "«{n}» solo necesita flujo de personal",
                }.get(round(requerido, 2), "el DNA de «{n}» lo pide")
                reason = motivo.format(n=nombre)
            elif data.usage_type in SALUD_USAGES:
                reason = "pasa una camilla"
            else:
                reason = "el flujo de gente del uso"
            advisories.append(
                f"Pasillo de {data.corridor_width_m:.2f} m: el catálogo "
                f"Neufert pide {requerido:.2f} m ({reason}).")

    # 2) Puerta por uso: la camilla pide 1,20 m de hoja.
    ancho_p, _alto_p = registry.door_for(data.usage_type)
    if data.door_width_m + 1e-9 < ancho_p:
        if data.usage_type in SALUD_USAGES:
            advisories.append(
                f"Puerta de {data.door_width_m:.2f} m: donde pasa una "
                "camilla, Neufert pide una hoja de 1,20 m.")
        else:
            advisories.append(
                f"Puerta de {data.door_width_m:.2f} m: Neufert sugiere "
                f"{ancho_p:.2f} m para {data.usage_type.lower()}.")

    # 3) Luz natural: el acristalado suma 1/8 del suelo (mínimo).
    #    En el trópico la edición regional sube la regla (Cuba: 1/5).
    ratio_min, _ratio_rec = registry.window_ratio()
    window_area = data.window_width_m * data.window_height_m
    oscuras: List[str] = []
    for room in data.rooms:
        if not room.with_window:
            continue
        area = room.width_m * room.depth_m
        if area > 0 and window_area + 1e-9 < area * ratio_min:
            oscuras.append(room.name)
    if oscuras:
        shown = ", ".join(oscuras[:3])
        extra = f" …y {len(oscuras) - 3} más" if len(oscuras) > 3 else ""
        frac = 8
        if ratio_min >= 0.2:
            frac = 5
        elif ratio_min > 0.1251:
            frac = 6
        advisories.append(
            f"Luz natural (Neufert{registry.region_tag()}: el "
            f"acristalado suma al menos 1/{frac} del suelo): la ventana "
            f"de {window_area:.2f} m2 queda corta en {shown}{extra}.")

    # 4) Altura libre recomendada por uso (la edición regional manda:
    #    Cuba sube los techos por el calor; México los baja).
    rec_h = registry.ceiling_for(data.usage_type)
    if rec_h is not None:
        for level in data.levels:
            if level.height_m + 1e-9 < rec_h:
                advisories.append(
                    f"«{level.name}» mide {level.height_m:.2f} m de "
                    "altura libre: Neufert sugiere "
                    f"{rec_h:.2f} m para {data.usage_type.lower()}"
                    f"{registry.region_tag()} (plenum de A/C y aire "
                    "por persona).")

    # 5) Rampa del desnivel: máximo 8 % (o el de la edición).
    rise = terrain_rise_m(data.terrain_type)
    if rise > 0.0:
        max_slope = registry.ramp_max_percent()
        advisories.append(
            f"Desnivel de {rise:.2f} m: la rampa no debe pasar del "
            f"{max_slope:.0f} % (Neufert{registry.region_tag()}), con "
            "descansos cada 0,75 m de desnivel.")

    # 6) Estacionamiento en usos públicos (dimensión de la edición).
    if data.usage_type in USOS_CON_ESTACIONAMIENTO:
        parking = registry.parking()
        plaza = str(parking.get("plaza_estandar_m", "2.50x5.00"))
        accesible = str(parking.get("plaza_accesible_m", "3.50x5.00"))
        pasillo = parking.get("pasillo_90_grados_m", 6.0)
        try:
            pasillo_txt = f"{float(pasillo):.2f}"
        except (TypeError, ValueError):
            pasillo_txt = "6.00"
        advisories.append(
            "Estacionamiento (Neufert"
            f"{registry.region_tag()}): plaza de "
            f"{plaza.replace('x', ' × ')} m y una accesible de "
            f"{accesible.replace('x', ' × ')} m con pasillo de "
            f"maniobra de {pasillo_txt} m.")

    # 7) Alero recomendado de la edición (v2.8.0): el trópico pide
    #    más sombra (Cuba 1,20 m) que la base (0,90 m).
    bio = registry.section("bioclimatica")
    alero_rec = bio.get("alero_recomendado_m")
    try:
        alero_rec = float(alero_rec)
    except (TypeError, ValueError):
        alero_rec = 0.0
    if data.protection_solar and alero_rec > 0 and \
            data.eaves_m + 1e-9 < alero_rec:
        quien = ("el libro" if registry.region_is_base()
                 else f"la edición {registry.region_name}")
        advisories.append(
            f"Alero de {data.eaves_m:.2f} m: {quien} recomienda "
            f"{alero_rec:.2f} m para la protección solar (o un porche "
            f"de {float(bio.get('porche_m', 1.8)):.2f} m).")
    return advisories


def vivienda_advisories(data: BuildingWizardData,
                        ctx: Any = None) -> List[str]:
    """Avisos del CATÁLOGO MAESTRO DE VIVIENDAS (v3.23.0).

    Compatibilidad estilo x sistema (§27, escala 0-3: advierte sin
    bloquear), reglas de la tipología elegida (medianeras, escalera
    del dúplex, fases de la progresiva, retiros de la aislada...),
    la relación a evitar del §8 (baño-comedor) y la zonificación
    Z005 del §9. Solo para el uso «Vivienda» con tipología del
    catálogo; si el recurso falta, calla.
    """
    avisos: List[str] = []
    if data.usage_type != "Vivienda" \
            or data.vivienda_tipologia == VIVIENDA_TIPOLOGIA_CLASICA:
        return avisos
    catalogo = _vivienda_catalogo()
    if catalogo is None:
        return avisos
    tipologia = catalogo.tipologia_de_etiqueta(data.vivienda_tipologia)
    clave = str((tipologia or {}).get("clave", "") or "")
    try:
        from domain.vivienda_specs import compatibilidad_gui
        nivel = compatibilidad_gui(data.architectural_style,
                                   data.construction_type, catalogo)
    except Exception:  # noqa: BLE001 — sin dominio, sin compatibilidad
        nivel = None
    if nivel is not None and nivel < 2:
        avisos.append(
            f"El catálogo de viviendas da compatibilidad {nivel}/3 "
            f"({catalogo.texto_compatibilidad(nivel)}) a «"
            f"{data.architectural_style}» + «{data.construction_type}»: "
            "no bloquea, pero valora la excepción (§27).")
    if clave in ("pareada", "adosada", "hilera", "entre_medianeras"):
        avisos.append(
            "Medianera compartida: no generar ventanas principales "
            "hacia ella salvo solución legal, y comprobar acústica, "
            "incendio, privacidad y ventilación (§11/§12).")
    if clave in VIVIENDA_DOS_NIVELES:
        avisos.append(
            "Dúplex/tríplex: evita que la escalera ocupe el centro "
            "funcional salvo que forme parte del concepto (§14).")
    if clave == "multigeneracional":
        avisos.append(
            "Multigeneracional: suite accesible de abuelos con baño y, "
            "si procede, acceso independiente; la zona privada se "
            "aísla de la social (Z008/§58).")
    if clave == "progresiva":
        fases = " -> ".join(
            f"F{f.get('fase')} {f.get('nombre')}"
            for f in (catalogo.progresiva or {}).get("fases", []))
        avisos.append(
            f"Progresiva por fases: {fases}. Conserva ejes, "
            "cimentación, instalaciones, estructura y escalera (§57).")
    if clave == "aislada":
        avisos.append(
            "Aislada: verifica ocupación de parcela, retiros, altura "
            "máxima, área libre y estacionamiento (UFA001-005).")
    if clave in ("economica", "progresiva"):
        avisos.append(
            "Vivienda económica/progresiva: funcionalidad máxima con "
            "mínimo costo; el nivel 1 de acabado del §51 la ajusta.")
    # Relación a evitar (§8): baño - comedor con puerta directa
    for rel in data.relations:
        if not rel.with_door:
            continue
        a = data.room(rel.a_name)
        b = data.room(rel.b_name)
        tipos = {getattr(a, "space_type", ""), getattr(b, "space_type",
                                                       "")}
        if "BATHROOM" in tipos and tipos & {"DINING_ROOM", "KITCHEN"}:
            avisos.append(
                "Z005/§8: el catálogo pide evitar la relación directa "
                "baño-comedor (X): revisa esa puerta declarada.")
            break
    return avisos


def comercial_advisories(data: BuildingWizardData,
                         ctx: Any = None) -> List[str]:
    """Avisos del DOCUMENTO COMERCIAL CC/OF (v3.25.0).

    Separación logística-oficinas y accesos del uso mixto (§85),
    escaleras mecánicas pendientes de fabricante (§22), prohibiciones
    residuos/carga contra público (§78/§95), plantas tipo de la torre
    y honestidad de los temas de cálculo (§50-59/§101). Sólo para los
    dos usos comerciales; si el recurso falta, calla.
    """
    avisos: List[str] = []
    if data.usage_type not in USOS_COMERCIALES:
        return avisos
    etiqueta = str(getattr(data, "comercial_tipologia", "") or "")
    specs = _comercial_specs()
    clave = ""
    if specs is not None and etiqueta and \
            etiqueta != COMERCIAL_SIN_TIPOLOGIA:
        tipologia = specs.tipologia_de_etiqueta(etiqueta)
        clave = str((tipologia or {}).get("clave", "") or "")
    if clave in ("CC-07", "OF-09", "OF-10"):
        avisos.append(
            "Uso mixto comercio-oficinas (§85): separa la logística de "
            "carga y residuos del bloque de oficinas, con accesos y "
            "horarios independientes siempre que se pueda.")
    if data.usage_type == USO_COMERCIAL_CC:
        avisos.append(
            "Escaleras mecánicas (§22): dimensiones definitivas del "
            "fabricante; deja desembarque de 2.50 m (mejor 3.00-4.00 m).")
        avisos.append(
            "Carga y residuos (§78/§95): nunca contra el recorrido "
            "público; la galería y los locales se abren solo al «0» "
            "prohibido por el documento.")
    if clave in ("OF-03", "OF-04", "OF-10"):
        avisos.append(
            "Torre/corporativo: la planta tipo se repite por nivel; "
            "añade niveles y copia el bloque de trabajo, con núcleo y "
            "evacuación IBC 2024 revisados en cada planta (§61).")
    if data.usage_type == USO_COMERCIAL_OF:
        avisos.append(
            "Evacuación de oficinas (§17/§61): ancho por ocupación "
            "(capacidad x factor IBC 2024); el motor informa, la "
            "normativa manda.")
    return avisos


def educacion_advisories(data: BuildingWizardData,
                         ctx: Any = None) -> List[str]:
    """Avisos del DOCUMENTO EDUCACIONAL (v3.26.0).

    Seguridad infantil del §89 para círculo infantil y primaria,
    flujos limpio/sucio del §102, profundidad de aulas §76, dormitorios
    lejos del ruido §90 en albergues y honestidad de los temas de
    cálculo (§78/§83-85). Sólo para los usos educativos; si el recurso
    falta, calla.
    """
    avisos: List[str] = []
    if data.usage_type not in USOS_EDUCATIVOS:
        return avisos
    if data.usage_type in ("Círculo infantil", "Escuela primaria"):
        avisos.append(
            "Seguridad infantil (§89): sin esquinas cortantes, "
            "enchufes accesibles, vidrios peligrosos ni acceso de "
            "los niños a cocinas y químicos; con control visual y "
            "cierres seguros.")
    if data.usage_type == "Círculo infantil":
        avisos.append(
            "Recorridos infantiles (§98): cocina, almacén y residuos "
            "no cruzan las circulaciones de los niños (flujos del "
            "§102).")
    if data.usage_type == "Albergue":
        avisos.append(
            "Dormitorios (§90): lejos de talleres, cocinas, gimnasio, "
            "máquinas y descarga, con literas que no estorben la "
            "evacuación.")
    tamano = _resuelve_tamano(data.usage_type, data.educacion_tamano)
    if tamano is not None and data.usage_type in (
            "Escuela primaria", "Escuela secundaria"):
        capacidad = int(tamano.get("capacidad", 0) or 0)
        por_aula = max(int(tamano.get("por_aula_o_grupo", 25) or 25), 1)
        avisos.append(
            f"Capacidad (§4): {capacidad} alumnos piden "
            f"{int(-(-capacidad // por_aula))} aulas a {por_aula} por "
            "aula (el asistente ya las cargó; el programa mínimo "
            "pide aulas de 40-45 m2).")
    avisos.append(
        "Cálculo especializado (§78/§83-85): climatización, incendios "
        "y evacuación van por población y normativa; el motor informa, "
        "no inventa cotas.")
    if data.usage_type in ("Escuela primaria", "Escuela secundaria") \
            and any(r.space_type == "GYMNASIO" for r in data.rooms):
        avisos.append(
            "Área deportiva (§30): el gimnasio pide 6-9 m de altura "
            "libre (12 x 18 m mínimo); dale un nivel propio más alto "
            "o una planta única de doble altura, y vestuarios (§32) "
            "al lado.")
    if data.usage_type in ("Escuela primaria", "Escuela secundaria"):
        avisos.append(
            "Comedor (§36): puertas de 1.20-1.80 m para alta "
            "concentración y cocina del 25-40% del comedor (§37), "
            "con almacén de alimentos (§38) propio.")
    return avisos


def neufert_normativa_block(data: BuildingWizardData) -> Dict[str, Any]:
    """Bloque «normativa» del metadata del edificio (v2.8.0).

    La foto completa de las reglas Neufert aplicadas a la edificación,
    con la edición regional activa: escalera (Blondel), pasillo,
    puerta, ventana, rampa, alturas, accesibilidad, muros por
    tipología, estacionamiento, evacuación y la sección propia del uso
    (oficinas, comercio, alojamiento…).
    """
    registry = _neufert_registry()
    if registry is None:
        return {"fuente": _neufert_fuente()}
    _sync_region(data)
    rule = registry.stair_rule(data.usage_type)
    ancho_p, alto_p = registry.door_for(data.usage_type)
    ratio_min, _ratio_rec = registry.window_ratio()
    acceso = registry.section("accesibilidad")
    if ratio_min >= 0.2:
        ratio_txt = f"1/5 del suelo ({ratio_min:.3f})"
    elif ratio_min > 0.1251:
        ratio_txt = f"1/6 del suelo ({ratio_min:.3f})"
    else:
        ratio_txt = f"1/8 del suelo ({ratio_min:.3f})"
    block: Dict[str, Any] = {
        "fuente": registry.fuente(),
        "edicion_regional": registry.region_block(),
        "pasillo_recomendado_m": registry.corridor_for(data.usage_type),
        "puerta_sugerida_m": ancho_p,
        "puerta_alta_m": alto_p,
        "escalera": {
            "contrahuella_m": rule.contrahuella_m,
            "huella_m": rule.huella_m,
            "ancho_minimo_m": rule.ancho_m,
            "blondel_m": rule.blondel_m,
            "formula": "2 × contrahuella + huella = 0,60–0,64 m",
            "barandilla_m": rule.barandilla_m,
        },
        "rampa_max_porcentaje": registry.ramp_max_percent(),
        "altura_libre_recomendada_m": registry.ceiling_for(
            data.usage_type),
        "ventana": {
            "ratio_luz_minimo": ratio_txt,
            "antepecho_m": registry.window_sill(),
        },
        "accesibilidad": {
            "circulo_giro_m": float(acceso.get("circulo_giro_m", 1.5)),
            "puerta_libre_m": float(acceso.get("puerta_libre_m", 0.9)),
            "pasamanos_altura_m": float(
                acceso.get("pasamanos_altura_m", 0.9)),
        },
        "muro_exterior_m": registry.wall_thickness_for(
            data.construction_type, exterior=True),
        "muro_interior_m": registry.wall_thickness_for(
            data.construction_type, exterior=False),
    }
    if data.usage_type in USOS_CON_ESTACIONAMIENTO:
        parking = registry.parking()
        block["estacionamiento"] = {
            "plaza_m": parking.get("plaza_estandar_m"),
            "plaza_accesible_m": parking.get("plaza_accesible_m"),
            "pasillo_m": parking.get("pasillo_90_grados_m"),
        }
    # Evacuación de referencia (v2.8.0): hojas y distancias del libro.
    evac = registry.section("evacuacion")
    if evac:
        block["evacuacion"] = {
            "puerta_salida_min_m": float(
                evac.get("puerta_salida_min_m", 0.9)),
            "pasillo_min_m": float(evac.get("pasillo_min_m", 1.2)),
            "distancia_una_direccion_m": float(
                evac.get("distancia_salida_una_direccion_m", 30.0)),
            "distancia_dos_direcciones_m": float(
                evac.get("distancia_salida_dos_direcciones_m", 45.0)),
        }
    # Sección propia del uso social (v2.8.0): oficinas, comercio,
    # alojamiento y salud ya tienen tablas propias del libro.
    uso_secciones = {"Oficina": "oficinas", "Local comercial": "comercio",
                     "Albergue": "alojamiento", "Hospital": "salud",
                     "Policlínico": "salud", "Consultorio médico": "salud",
                     "Escuela primaria": "educacion",
                     "Comedor social": "comedor_colectivo"}
    seccion_uso = uso_secciones.get(data.usage_type)
    if seccion_uso and registry.has(seccion_uso):
        block["por_uso"] = {seccion_uso: registry.section(seccion_uso)}
    return block


def suggest_relations(data: BuildingWizardData) -> List[RelationSpec]:
    """Relaciones sugeridas desde el DNA (preferencias de adyacencia).

    Une locales del mismo nivel cuyo tipo figure en las adyacencias
    preferidas del otro. Determinista y sin duplicados.
    """
    registry_values: Dict[str, Any] = {}
    try:
        from app.paths import resource_path
        from domain.knowledge import SpaceDNARegistry
        registry = SpaceDNARegistry()
        registry.load_file(resource_path("knowledge", "space_dna.json"))
        for key in registry.types():
            registry_values[key] = registry.get(key)
    except Exception:  # noqa: BLE001 — sin DNA no se sugiere nada
        return []

    declared: set = set()
    suggestions: List[RelationSpec] = []
    extra_pairs = USAGE_EXTRA_PAIRS.get(
        getattr(data, "usage_type", ""), ())
    for room in data.rooms:
        dna = registry_values.get(room.space_type)
        # Sin DNA el local solo participa por los pares extra del uso
        # (p. ej. el área de ventas ROOM del comercio).
        preferred = list(getattr(dna, "preferred_adjacencies", [])) + \
            list(getattr(dna, "functional_relationships", [])) \
            if dna is not None else []
        for other in data.rooms:
            if other.name == room.name or \
                    other.level_ref != room.level_ref:
                continue
            pair_types = frozenset((room.space_type, other.space_type))
            if other.space_type not in preferred and \
                    pair_types not in extra_pairs:
                continue
            pair = (room.name, other.name)
            if pair in declared or (pair[1], pair[0]) in declared:
                continue
            declared.add(pair)
            declared.add((pair[1], pair[0]))
            # Puertas críticas del uso social (v2.2.0): quirófano–
            # esterilización, urgencias–rayos X, sala–enfermería…
            with_door = pair_types in USAGE_DOOR_PAIRS.get(
                getattr(data, "usage_type", ""), ())
            suggestions.append(RelationSpec(
                a_name=pair[0], b_name=pair[1],
                kind_es="Adyacente a", with_door=with_door))
    return suggestions


# -- Plan declarativo y ejecución -------------------------------------------------

def _educacion_metadata(data: BuildingWizardData) -> Dict[str, Any]:
    """Bloque «educacion» del metadata (v3.26.0): familia, tamaño y
    capacidad para la validación del documento (alumnos, grupos o
    plazas según el uso)."""
    bloque: Dict[str, Any] = {"tamano": data.educacion_tamano}
    familia = ""
    try:
        from domain.educacion_specs import familia_de_uso
        familia = familia_de_uso(data.usage_type) or ""
    except Exception:  # noqa: BLE001 — sin dominio: sin familia
        familia = ""
    bloque["familia"] = familia
    tamano = _resuelve_tamano(data.usage_type, data.educacion_tamano)
    if tamano is None:
        return bloque
    capacidad = int(tamano.get("capacidad", 0) or 0)
    por_aula = float(tamano.get("por_aula_o_grupo", 0.0) or 0.0)
    if familia in ("ESCUELA_PRIMARIA", "ESCUELA_SECUNDARIA"):
        bloque["alumnos"] = capacidad
        bloque["alumnos_por_aula"] = por_aula
    elif familia == "CIRCULO_INFANTIL":
        bloque["grupos"] = capacidad
        bloque["ninios"] = int(capacidad * por_aula)
    elif familia == "ALBERGUE_ESCOLAR":
        bloque["plazas"] = capacidad
    return bloque


def _building_metadata(data: BuildingWizardData,
                       variant: Optional["PlantVariant"] = None
                       ) -> Dict[str, Any]:
    """Metadata de la edificación: requerimientos globales."""
    from core.geometry.representation import hatch_key_for, roof_profile
    from core.geometry.structural import column_rule
    _roof = roof_profile(data)
    _rule = column_rule(data.construction_type)
    _hatch_key = hatch_key_for(data.construction_type)
    metadata: Dict[str, Any] = {
        "edificacion": {
            "nombre": data.name.strip(),
            "uso_social": data.usage_type,
            "dimensiones_max_m": {"ancho": data.lot_width_m,
                                  "fondo": data.lot_depth_m},
            "tipologia_constructiva": data.construction_type,
            "forma_en_planta": data.plan_shape,
            "estilo_arquitectonico": data.architectural_style,
            "terreno": data.terrain_type,
            "desnivel_pisos_m": terrain_rise_m(data.terrain_type),
            "escaleras": {
                "modo": data.stairs_mode,
                "colocadas": stairs_wanted(data),
            },
            "nucleo_rigido": {
                "modo": data.core_mode,
                "colocado": core_wanted(data),
            },
            "representacion": {
                "cubierta": {
                    "tipo": _roof.kind,
                    "pendiente_m_m": _roof.slope,
                    "descripcion": _roof.description,
                },
                "columnas": {
                    "estrategia": _rule.strategy,
                    "medida_m": _rule.size_m,
                    "separacion_m": _rule.spacing_m,
                    "material": _rule.material,
                },
                "hatch_muros": _hatch_key,
                "vistas": ["Planta", "Elevación", "Corte", "Detalles"],
            },
            "normativa": neufert_normativa_block(data),
            "clima": data.climate,
            "sistema_estructural": data.structural_system,
            "orientacion_fachada": data.facade_orientation,
            "ventilacion_cruzada": data.cross_ventilation,
            "pasillo": data.corridor_enabled,
            "ancho_pasillo_m": data.corridor_width_m,
            "espesor_muros_m": data.wall_thickness_m,
            "niveles": len(data.levels),
            "bioclimatica": {
                "proteccion_solar": data.protection_solar,
                "alero_m": data.eaves_m,
            },
            "instalaciones": list(data.installations),
            "ancho_puerta_m": data.door_width_m,
            "alto_puerta_m": data.door_height_m,
            "ancho_ventana_m": data.window_width_m,
            "alto_ventana_m": data.window_height_m,
            "derrame_ventana_m": data.window_sill_m,
            "region_neufert": data.neufert_region,
            "distribucion": data.distribucion,
            "semilla": data.semilla,
            "curvatura_m": data.curvatura_m,
            "mobiliario": {
                "activo": data.mobiliario,
                "ambito": data.mobiliario_ambito,
                "densidad": data.mobiliario_densidad,
            },
            "cubierta": {
                "tipologia": data.cubierta_tipologia,
                "material": data.cubierta_material,
                "pendiente_pct": data.cubierta_pendiente_pct,
                "alero_m": data.cubierta_alero_m,
            },
            "accesibilidad": {
                "auto": data.accesibilidad_auto,
            },
            "vivienda": {
                "tipologia": data.vivienda_tipologia,
                "dormitorios": int(data.vivienda_dormitorios),
                "banos": int(data.vivienda_banos),
            },
            "comercial": {
                "familia": (
                    "CENTRO_COMERCIAL"
                    if data.usage_type == USO_COMERCIAL_CC else
                    "OFICINAS" if data.usage_type == USO_COMERCIAL_OF
                    else ""),
                "tipologia": data.comercial_tipologia,
            },
            "educacion": _educacion_metadata(data),
            "notas": data.notes,
            "origen": "asistente de edificación v2.1.0",
        },
    }
    if variant is not None:
        metadata["edificacion"]["variante_planta"] = {
            "clave": variant.key,
            "titulo": variant.title,
            "puntuacion": variant.score,
            "metricas": dict(variant.metrics),
        }
    return metadata


# Multiplicadores de niveles (v3.32.0, P3 del análisis Architechtures):
# una misma planta se diseña UNA vez y se repite N veces (planta tipo).
# Con todos los multiplicadores a 1 el comportamiento es idéntico al
# previo: las tres funciones son IDENTIDAD.
REPEAT_MAX = 50


def repeat_de(level: LevelSpec) -> int:
    """Multiplicador SANO del nivel: entero entre 1 y REPEAT_MAX.

    Los valores raros (None, texto, 0, negativos, absurdos) se
    degradan a 1 o al techo — nunca lanzan: el asistente no debe
    bloquear el proyecto por un multiplicador mal escrito.
    """
    try:
        n = int(level.repeat)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return max(1, min(REPEAT_MAX, n))


def niveles_expandidos(data: BuildingWizardData) -> List[LevelSpec]:
    """Expanden los multiplicadores: cada nivel sale «repeat» veces.

    La primera copia conserva el nombre original; las demás reciben
    sufijos « 2», « 3»… Si un nombre generado ya se usó (por ejemplo
    porque otro nivel se llamaba así), se añade «_2», «_3»… hasta que
    sea único. El orden y las alturas se conservan: las cotas
    resultantes son exactamente las de listar las copias una a una.
    """
    expandidos: List[LevelSpec] = []
    usados: Set[str] = set()
    for spec in data.levels:
        nombre_base = spec.name.strip()
        copias = repeat_de(spec)
        for i in range(copias):
            candidato = nombre_base if i == 0 else f"{nombre_base} {i + 1}"
            clave = candidato.strip().lower()
            extra = 2
            while clave in usados:
                candidato = f"{candidato}_{extra}"
                clave = candidato.strip().lower()
                extra += 1
            usados.add(clave)
            expandidos.append(LevelSpec(name=candidato,
                                        height_m=spec.height_m,
                                        repeat=1))
    return expandidos


def expandir_datos(data: BuildingWizardData) -> BuildingWizardData:
    """Copia del asistente con niveles y locales YA multiplicados.

    Los locales de una planta repetida se DUPLICAN en cada copia con
    su «level_ref» apuntando a la copia correspondiente (mismo nombre,
    dimensiones y tipo); las relaciones espaciales son globales — van
    por NOMBRE de local, no por nivel — y NO se duplican. Si ningún
    multiplicador supera 1, devuelve EL MISMO objeto: cero impacto en
    los planes previos a v3.32.0.
    """
    niveles = niveles_expandidos(data)
    if len(niveles) == len(data.levels):
        return data  # identidad: nada que multiplicar
    propios_por_nombre = {spec.name.strip(): data.rooms_of_level(spec.name)
                          for spec in data.levels}
    locales: List[RoomSpec] = []
    idx = 0
    for spec in data.levels:
        copias = repeat_de(spec)
        propios = propios_por_nombre.get(spec.name.strip(), [])
        for i in range(copias):
            destino = niveles[idx + i].name
            for room in propios:
                locales.append(replace(room, level_ref=destino))
        idx += copias
    # locales atados a un nivel que ya no existe se conservan igual
    # (build_layout los salta con el mismo silencio de siempre)
    nombres = {spec.name.strip() for spec in data.levels}
    for room in data.rooms:
        if room.level_ref.strip() not in nombres:
            locales.append(room)
    return replace(data, levels=niveles, rooms=locales)


def level_elevations(data: BuildingWizardData) -> List[float]:
    """Cota de cada nivel = suma de las alturas de los anteriores.

    v3.32.0: recorre los niveles YA EXPANDIDOS por el multiplicador,
    así que una planta tipo ×3 empuja la cota de todo lo que viene
    después (con todos los «repeat» a 1 es el cálculo previo).
    """
    elevations: List[float] = []
    running = 0.0
    for lv in niveles_expandidos(data):
        elevations.append(round(running, 6))
        running += lv.height_m
    return elevations


def build_plan(data: BuildingWizardData,
               existing_levels: Sequence[str] = (),
               has_building: bool = False,
               variant: Optional["PlantVariant"] = None
               ) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[LevelLayout],
                          List[str]]:
    """Plan declarativo de creación a partir de los datos del asistente.

    Orden garantizado: (edificio) → niveles nuevos → locales por nivel
    (incluido el pasillo/patio) → muros fusionados → puertas → ventanas
    → relaciones espaciales. La GUI y las pruebas pueden inspeccionarlo
    antes de ejecutarlo. Si se pasa una «variant» del motor de variantes
    (v2.1.0) se usa SU trazado; si no, el lineal clásico. Devuelve
    también el trazado y los avisos.

    v3.32.0: los multiplicadores de niveles se expanden AQUÍ (y en
    generate_variants), de modo que niveles, locales, muros y cotas
    salgan ya multiplicados y coherentes entre sí.
    """
    data = expandir_datos(data)
    plan: List[Tuple[str, Dict[str, Any]]] = []
    if not has_building:
        plan.append(("BUILDING", {"name": data.name.strip(),
                                  "floors": len(data.levels),
                                  "metadata": _building_metadata(data,
                                                                 variant)}))
    if variant is not None:
        layouts = list(variant.layouts)
        advisories = list(variant.advisories)
    else:
        layouts, advisories = build_layout(data, with_core=core_wanted(data))
        advisories = advisories + apply_distribucion(data, layouts)
    elevations = level_elevations(data)
    existing = {name.strip().lower() for name in existing_levels}
    for position, level in enumerate(data.levels):
        if level.name.strip().lower() not in existing:
            plan.append(("LEVEL", {
                "name": level.name.strip(),
                "elevation_m": elevations[position],
                "height_m": level.height_m,
            }))
    for layout in layouts:
        level_name = layout.level_name
        for pr in layout.all_rooms:
            plan.append(("SPACE", {
                "level_ref": level_name, "name": pr.name,
                "space_type": pr.space_type,
                "boundary": pr.boundary(),
                "is_corridor": pr.is_corridor,
                "room_ref": "" if pr.is_corridor else pr.name,
                "floor_rise_m": pr.floor_rise_m,
            }))
        for wall in layout.walls:
            plan.append(("WALL", {
                "level_ref": level_name, "start": wall["start"],
                "end": wall["end"],
                "thickness_m": data.wall_thickness_m,
                "structural": structural_flag(wall,
                                              data.structural_system),
                "metadata": {"portante": structural_flag(
                    wall, data.structural_system),
                    "origen": "asistente de edificación"},
            }))
        for opening in layout.doors + layout.windows:
            kind = opening.kind
            plan.append((kind, {
                "width_m": opening.width_m,
                "height_m": opening.height_m,
                "offset_m": opening.offset_m,
                "sill_height_m": opening.sill_height_m,
                "note": opening.note,
                "level_ref": level_name,
                "wall_index": opening.wall_index,
            }))
    # Relaciones espaciales declaradas: UNA sola vez (son globales, no
    # por nivel).
    for rel in data.relations:
        kind = KIND_BY_LABEL.get(rel.kind_es, "adjacent_to")
        plan.append(("RELATION", {
            "a_name": rel.a_name, "b_name": rel.b_name, "kind": kind,
            "source": "manual",
        }))
    return plan, layouts, advisories


def _attach_metadata(ctx: Any, entity: Any, metadata: Dict[str, Any]) -> None:
    """Deja metadata en la entidad por el camino oficial.

    Igual que los servicios: Command §76 (deshacible) + auditoría §71
    con el antes y el después (UPDATE_ENTITY).
    """
    from services.commands_impl import UpdateEntityCommand, entity_snapshot
    from core.audit.models import make_audit_event
    old_snapshot = entity_snapshot(entity)
    entity.metadata = dict(entity.metadata or {})
    entity.metadata.update(metadata)
    entity.touch()
    ctx.command_bus.execute(UpdateEntityCommand(entity), ctx)
    event = make_audit_event(ctx.user, entity.id, entity.ENTITY_TYPE,
                             "UPDATE_ENTITY", old_snapshot,
                             entity_snapshot(entity))
    ctx.audit_repo.append(event)


def apply_plan(data: BuildingWizardData, ctx: Any,
               variant: Optional["PlantVariant"] = None) -> Dict[str, Any]:
    """Ejecuta el plan por las fachadas oficiales y devuelve resumen.

    Usa ArchitectureService (CommandBus §76, auditoría §71 y eventos
    §75) exactamente como la CLI, y confirma una sola vez al final:
    si algo falla, el proyecto queda como antes. Los requerimientos
    quedan en el metadata de edificio, locales y muros. Con «variant»
    se genera el trazado de esa variante del motor de variantes.
    """
    from services.architecture_service import ArchitectureService

    arch = ArchitectureService(ctx)
    repository = ctx.architecture
    pid = ctx.project.id
    existing_levels = [lv.name for lv in repository.list("LEVEL", pid)]
    building = repository.list("BUILDING", pid)
    plan, layouts, _layout_advisories = build_plan(
        data, existing_levels=existing_levels,
        has_building=bool(building), variant=variant)

    summary: Dict[str, Any] = {
        "building": building[0].code if building else "",
        "levels_created": 0, "levels_reused": len(existing_levels),
        "spaces": 0, "walls": 0, "doors": 0, "windows": 0,
        "relations": 0, "warnings": [],
    }

    wall_codes_by_level: Dict[str, List[str]] = {}
    space_codes_by_name: Dict[str, str] = {}

    # Primer pase: edificio, niveles, locales y muros.
    building_entity = building[0] if building else None
    for position, (op, params) in enumerate(plan):
        if op == "BUILDING":
            created = arch.create_building(name=params["name"],
                                           floors=params["floors"])
            _attach_metadata(ctx, created, params["metadata"])
            building_entity = created
            summary["building"] = created.code
        elif op == "LEVEL":
            level = arch.create_level(
                name=params["name"], elevation_m=params["elevation_m"],
                height_m=params["height_m"],
                building_id=building_entity.id if building_entity else None)
            summary["levels_created"] += 1
        elif op == "SPACE":
            space = arch.create_space(
                level_ref=params["level_ref"], name=params["name"],
                space_type=params["space_type"],
                boundary=params["boundary"])
            room = data.room(params["room_ref"]) \
                if params.get("room_ref") else None
            if room is not None:
                requirements = room_requirements(data, room, ctx)
                requirements["arquitectonicos"]["cota_piso_m"] = \
                    params.get("floor_rise_m", 0.0)
            else:
                space_kind = params["space_type"]
                if space_kind == STAIR_TYPE:
                    _stair_steps, _stair_run = stair_geometry(
                        _stair_rise_for(data), data.usage_type)
                    _riser_n, _tread_n = stair_geometry_for(
                        data.usage_type)
                    requirements = {
                        "climaticos": {
                            "zona_climatica": data.climate,
                            "ventilacion_natural_sugerida": True},
                        "arquitectonicos": {
                            "tipo": STAIR_TYPE,
                            "nombre_conocido": "Escalera",
                            "escalones_estimados": _stair_steps,
                            "desarrollo_m": _stair_run,
                            "contrahuella_m": _riser_n,
                            "huella_m": _tread_n,
                            "blondel_m": round(
                                2.0 * _riser_n + _tread_n, 3),
                            "norma": _neufert_fuente(),
                            "cota_piso_m": params.get("floor_rise_m",
                                                      0.0)},
                        "estructurales": {
                            "sistema": data.structural_system},
                        "origen": "asistente de edificación v2.1.0",
                    }
                elif space_kind == CORE_TYPE:
                    requirements = {
                        "climaticos": {
                            "zona_climatica": data.climate,
                            "ventilacion_natural_sugerida": False},
                        "arquitectonicos": {
                            "tipo": CORE_TYPE,
                            "nombre_conocido": "Núcleo rígido",
                            "contenido": "escalera, baños y ductos "
                                         "entre muros estructurales",
                            "esquina": True,
                            "cota_piso_m": params.get("floor_rise_m",
                                                      0.0)},
                        "estructurales": {
                            "sistema": data.structural_system,
                            "nucleo_rigido": True},
                        "origen": "asistente de edificación v2.1.0",
                    }
                else:
                    requirements = {
                        "climaticos": {"zona_climatica": data.climate,
                                       "ventilacion_cruzada":
                                       data.cross_ventilation,
                                       "ventilacion_forzada_sugerida":
                                       space_kind == CORRIDOR_TYPE},
                        "arquitectonicos": {
                            "tipo": space_kind,
                            "nombre_conocido":
                            "Patio" if space_kind == PATIO_TYPE
                            else "Pasillo",
                            "cota_piso_m": params.get("floor_rise_m",
                                                      0.0)},
                        "estructurales": {
                            "sistema": data.structural_system},
                        "origen": "asistente de edificación v2.1.0",
                    }
            _attach_metadata(ctx, space,
                             {"requerimientos": requirements})
            # Los vínculos (relaciones) usan CÓDIGO, no nombre: así una
            # relación nunca se cuela en un local homónimo preexistente.
            # Con nombres repetidos EN el lote (p. ej. mismo programa en
            # dos niveles) gana la primera aparición: determinista.
            space_codes_by_name.setdefault(params["name"], space.code)
            summary["spaces"] += 1
        elif op == "WALL":
            wall = arch.create_wall(
                level_ref=params["level_ref"], start=params["start"],
                end=params["end"], thickness_m=params["thickness_m"],
                structural=params["structural"])
            _attach_metadata(ctx, wall, params["metadata"])
            wall_codes_by_level.setdefault(params["level_ref"],
                                           []).append(wall.code)
            summary["walls"] += 1

    # Segundo pase: vanos (ya existen los muros) y relaciones.
    for position, (op, params) in enumerate(plan):
        if op in ("DOOR", "WINDOW"):
            level_name = params["level_ref"]
            codes = wall_codes_by_level.get(level_name) or [""]
            wall_index = params.get("wall_index", -1)
            wall_ref = codes[wall_index] if 0 <= wall_index < len(codes) \
                else codes[0]
            opening = arch.create_opening(
                kind=op, wall_ref=wall_ref, width_m=params["width_m"],
                height_m=params["height_m"],
                offset_m=params["offset_m"],
                sill_height_m=params.get("sill_height_m", 0.0) or 0.0)
            _attach_metadata(ctx, opening, {
                "origen": "asistente de edificación",
                "nota": params.get("note", "")})
            summary["doors" if op == "DOOR" else "windows"] += 1
        elif op == "RELATION":
            # Dentro del lote los locales se referencian por código;
            # si el nombre no vino de este asistente, se respeta tal
            # cual (serviría para relacionar con un local existente).
            arch.add_relationship(
                from_ref=space_codes_by_name.get(params["a_name"],
                                                 params["a_name"]),
                to_ref=space_codes_by_name.get(params["b_name"],
                                               params["b_name"]),
                kind=params["kind"], source=params["source"])
            summary["relations"] += 1

    # Avisos amables (no bloquean): trazado + DNA + normativa Neufert.
    for layout in layouts:
        summary["warnings"].extend(layout.advisories)
    summary["warnings"].extend(dna_advisories(data, ctx))
    summary["warnings"].extend(site_advisories(data))
    summary["warnings"].extend(neufert_advisories(data, ctx))
    # INSTALACIONES REALES (v3.8.0): los módulos elegidos en el paso 5
    # se convierten en redes del proyecto adaptadas a los locales
    # creados (antes solo quedaban como texto en los requerimientos).
    inst_summary: Dict[str, Any] = {"redes": 0, "equipos": 0, "tramos": 0,
                                    "nombres": []}
    if data.installations:
        from services.installations_generator import generate_installations
        inst_summary = generate_installations(
            ctx, data.installations, usage_type=data.usage_type,
            origin="asistente de edificación")
        summary["warnings"].extend(inst_summary.get("warnings", []))
    summary["instalaciones"] = inst_summary

    # CONCEPCIÓN DE ESPACIOS (v3.15.0): mobiliario, cubierta y
    # accesibilidad se REGENERAN con la edificación (nada de huérfanos).
    # Cada motor es idempotente y deja aviso amable si no puede.
    if bool(getattr(data, "mobiliario", True)):
        try:
            from domain import mobiliario as _mob
            summary["mobiliario"] = _mob.generar_mobiliario(
                ctx, data, ambito=str(getattr(data, "mobiliario_ambito",
                                              "auto")),
                densidad=str(getattr(data, "mobiliario_densidad",
                                     "estandar")), con_qto=False)
            summary["warnings"].extend(
                summary["mobiliario"].get("avisos", []))
        except Exception as exc:  # noqa: BLE001 - avisa, no bloquea el plan
            summary["mobiliario"] = {"creados": [], "conteo": {}}
            summary["warnings"].append(
                f"Mobiliario sin generar: {exc}")
    if str(getattr(data, "cubierta_tipologia", "auto")) != "ninguna":
        try:
            from domain import cubiertas as _cub
            summary["cubierta"] = _cub.generar_cubierta(
                ctx, data,
                tipologia=str(getattr(data, "cubierta_tipologia", "auto")),
                material=str(getattr(data, "cubierta_material", "auto")),
                pendiente_pct=float(getattr(data, "cubierta_pendiente_pct",
                                            0.0) or 0.0),
                alero_m=float(getattr(data, "cubierta_alero_m", 0.0) or 0.0)
                or None, con_qto=False)
        except Exception as exc:  # noqa: BLE001
            summary["cubierta"] = {"creados": [], "avisos": []}
            summary["warnings"].append(
                f"Cubierta sin generar: {exc}")
    if bool(getattr(data, "accesibilidad_auto", True)):
        try:
            from domain import accesibilidad as _acc
            summary["accesibilidad"] = _acc.aplicar_soluciones(
                ctx, data, con_qto=False)
            summary["warnings"].extend(
                summary["accesibilidad"].get("avisos", []))
        except Exception as exc:  # noqa: BLE001
            summary["accesibilidad"] = {"creados": [], "conteo": {}}
            summary["warnings"].append(
                f"Accesibilidad sin aplicar: {exc}")
    summary["layouts"] = layouts
    summary["areas"] = {layout.level_name: round(layout.total_area_m2(), 2)
                        for layout in layouts}
    ctx.commit()
    return summary


def step_summary(data: BuildingWizardData, ctx: Any = None,
                 variant: Optional["PlantVariant"] = None) -> str:
    """Resumen legible del último paso (lo que se va a crear)."""
    plan, layouts, advisories = build_plan(
        data, existing_levels=(), has_building=False, variant=variant)
    counts: Dict[str, int] = {}
    for op, _params in plan:
        counts[op] = counts.get(op, 0) + 1
    lines: List[str] = []
    lines.append(f"Edificación «{data.name.strip()}» — uso social: "
                 f"{data.usage_type.lower()}; "
                 f"({data.structural_system.lower()}, clima "
                 f"{data.climate.lower()})")
    lines.append(f"· Tipología constructiva: {data.construction_type}")
    lines.append(f"· Forma en planta: {data.plan_shape}")
    lines.append(f"· Estilo arquitectónico: {data.architectural_style}")
    if data.usage_type == "Vivienda" and \
            data.vivienda_tipologia != VIVIENDA_TIPOLOGIA_CLASICA:
        lines.append(
            f"· Vivienda: tipología «{data.vivienda_tipologia}» del "
            "catálogo — programa paramétrico del §7 ("
            f"{data.vivienda_dormitorios} dormitorios, "
            f"{data.vivienda_banos} baños)")
    if data.usage_type in USOS_COMERCIALES and \
            data.comercial_tipologia != COMERCIAL_SIN_TIPOLOGIA:
        lines.append(
            f"· {data.usage_type}: tipología «{data.comercial_tipologia}» "
            "del documento CC/OF — programa mínimo del §89-90")
    if data.usage_type in USOS_EDUCATIVOS and \
            data.educacion_tamano != EDU_SIN_TAMANO:
        lines.append(
            f"· {data.usage_type}: tamaño «{data.educacion_tamano}» del "
            "documento educacional — programa mínimo del §106-109")
    if data.distribucion != "ortogonal":
        _dist_desc = DISTRIBUTION_DESCRIPTIONS.get(data.distribucion, "")
        lines.append(f"· Distribución interior: "
                     f"{distribution_label(data.distribucion)} — "
                     f"{_dist_desc[0].lower() + _dist_desc[1:]}"
                     f" (curvatura {data.curvatura_m:.1f} m, semilla "
                     f"{data.semilla})")
    rise = terrain_rise_m(data.terrain_type)
    terrain_line = f"· Terreno: {data.terrain_type}"
    if rise > 0.0:
        terrain_line += f" (desnivel de {rise:.2f} m dentro de la planta)"
    lines.append(terrain_line)
    if stairs_wanted(data):
        _stair_steps, stair_run = stair_geometry(_stair_rise_for(data))
        lines.append(
            f"· Escaleras: caja de escalera incluida ({_stair_steps} "
            f"escalones, {stair_run:.1f} m de desarrollo)")
    else:
        lines.append("· Escaleras: no se colocan (según tu decisión)")
    if core_wanted(data):
        n_cores = sum(1 for layout in layouts for pr in layout.all_rooms
                      if pr.space_type == CORE_TYPE)
        lines.append(
            f"· Núcleo rígido en esquinas: {n_cores} caja(s) con "
            "escalera, baños y ductos entre muros estructurales")
    else:
        lines.append("· Núcleo rígido: no se coloca (según tu decisión)")
    # Representación arquitectónica (v2.6.0): cubierta, columnas y vistas.
    from core.geometry.representation import roof_profile
    from core.geometry.structural import column_rule
    _profile = roof_profile(data)
    _rule = column_rule(data.construction_type)
    lines.append(
        "· Representación: cubierta " + _profile.description.lower() + "; "
        + (f"columnas de {_rule.size_m * 100:.0f} cm cada "
           f"{_rule.spacing_m:.1f} m ({_rule.strategy})"
           if _rule.has_columns else
           "sin columnas (muros autoportantes)")
        + "; vistas planta / elevación / corte / detalles exportables a SVG")
    # CONCEPCIÓN DE ESPACIOS (v3.15.0): lo que se amuebla, cubre y
    # hace accesible al regenerar.
    if data.mobiliario:
        lines.append(
            f"· Mobiliario: los locales se amueblan según su uso "
            f"({data.mobiliario_ambito}, densidad "
            f"{data.mobiliario_densidad})")
    else:
        lines.append("· Mobiliario: no se coloca (según tu decisión)")
    _cub_line = (f"· Cubierta: {data.cubierta_tipologia} de "
                 f"{data.cubierta_material}")
    _cub_pend = f"{data.cubierta_pendiente_pct:g} %" \
        if data.cubierta_pendiente_pct > 0 else "pendiente según estilo"
    _cub_alero = data.cubierta_alero_m if data.cubierta_alero_m > 0 \
        else data.eaves_m
    lines.append(f"{_cub_line} ({_cub_pend}, alero {_cub_alero:.2f} m)")
    if data.accesibilidad_auto:
        lines.append(
            "· Accesibilidad: barandillas de escalera, rampas de "
            "desnivel con pasamanos doble y barras de apoyo automáticas")
    else:
        lines.append("· Accesibilidad: sin soluciones automáticas "
                     "(según tu decisión)")
    # NORMATIVA NEUFERT (v2.7.0; v2.8.0 con la edición regional): la
    # foto de las reglas aplicadas.
    _nreg = _neufert_registry()
    if _nreg is not None:
        _sync_region(data)
        _nrule = _nreg.stair_rule(data.usage_type)
        _ncorr = _nreg.corridor_for(data.usage_type)
        _ndoor, _nalt = _nreg.door_for(data.usage_type)
        _ratio_min, _ratio_rec = _nreg.window_ratio()
        _frac_luz = 8
        if _ratio_min >= 0.2:
            _frac_luz = 5
        elif _ratio_min > 0.1251:
            _frac_luz = 6
        _edicion = f" · Edición: {_nreg.region_name}" \
            if not _nreg.region_is_base() else ""
        lines.append(
            "· Normativa Neufert: pasillo ≥ "
            f"{(_ncorr if _ncorr is not None else data.corridor_width_m):.2f} m "
            f"· puerta {_ndoor:.2f} m · escalera "
            f"{_nrule.contrahuella_m * 100:.0f}×{_nrule.huella_m * 100:.0f} cm "
            f"(Blondel {_nrule.blondel_m:.2f} m) · rampa ≤ "
            f"{_nreg.ramp_max_percent():.0f} % · luz ≥ 1/{_frac_luz} del "
            f"suelo{_edicion}")
    dims = []
    if data.lot_width_m > 0:
        dims.append(f"ancho máx. {data.lot_width_m:.1f} m")
    if data.lot_depth_m > 0:
        dims.append(f"fondo máx. {data.lot_depth_m:.1f} m")
    if dims:
        lines.append("· Dimensiones máximas: " + ", ".join(dims))
    if variant is not None:
        lines.append(f"· Variante de planta: {variant.title} "
                     f"(puntuación {variant.score:.0f}/100, "
                     f"{variant.fits_text})")
    lines.append(f"· Fachada principal hacia el {data.facade_orientation.lower()} "
                 + ("con ventilación cruzada" if data.cross_ventilation
                    else "sin ventilación cruzada automática"))
    lines.append("· Bioclimática: "
                 + (f"aleros de {data.eaves_m:.1f} m" if data.protection_solar
                    else "sin protección solar automática")
                 + (" · ventilación cruzada" if data.cross_ventilation else ""))
    if data.installations:
        lines.append("· Instalaciones: " + ", ".join(data.installations))
    levels_text = ", ".join(
        f"{lv.name.strip()} ({lv.height_m:.1f} m)" for lv in data.levels)
    lines.append(f"· Niveles ({len(data.levels)}): {levels_text}")
    rooms_text = ", ".join(r.name.strip() for r in data.rooms)
    lines.append(f"· Locales ({len(data.rooms)}): {rooms_text}")
    if data.corridor_enabled:
        if variant is not None and variant.scheme == "patio":
            patio = next((layout.corridor for layout in layouts
                          if layout.corridor is not None), None)
            width = patio.d if patio is not None else data.corridor_width_m
            lines.append(f"· Patio central de {width:.1f} m: cada local "
                         "tiene su puerta a la galería del patio")
        else:
            lines.append(f"· Pasillo de {data.corridor_width_m:.1f} m que "
                         "conecta todos los locales (puerta automática a "
                         "cada uno)")
    lines.append(f"· Se crearán: {counts.get('BUILDING', 0)} edificio, "
                 f"{counts.get('LEVEL', 0)} nivel(es), "
                 f"{counts.get('SPACE', 0)} locales, "
                 f"{counts.get('WALL', 0)} muros (paredes compartidas "
                 "fusionadas), "
                 f"{counts.get('DOOR', 0)} puertas y "
                 f"{counts.get('WINDOW', 0)} ventanas, "
                 f"{counts.get('RELATION', 0)} relaciones espaciales")
    lines.append(f"· Requerimientos: quedarán guardados en cada objeto "
                 "(climáticos, arquitectónicos y estructurales)")
    total_area = sum(layout.total_area_m2() for layout in layouts)
    lines.append(f"· Área total construida aproximada: {total_area:.1f} m²")
    warnings = (advisories + [w for layout in layouts
                              for w in layout.advisories]
                + site_advisories(data) + neufert_advisories(data)
                + vivienda_advisories(data) + comercial_advisories(data)
                + educacion_advisories(data))
    if warnings:
        lines.append("")
        lines.append("Antes de generar, ten en cuenta:")
        for warning in warnings[:6]:
            lines.append(f"· {warning}")
        if len(warnings) > 6:
            lines.append(f"· …y {len(warnings) - 6} aviso(s) más.")
    return "\n".join(lines)


def building_field_names() -> List[str]:
    """Campos principales del asistente (para pruebas y ayuda)."""
    return [
        "name", "usage_type", "lot_width_m", "lot_depth_m",
        "construction_type", "climate", "structural_system",
        "facade_orientation", "neufert_region", "notes", "levels",
        "rooms", "relations", "corridor_enabled", "corridor_width_m",
        "wall_thickness_m", "door_width_m", "door_height_m",
        "window_width_m", "window_height_m", "window_sill_m",
        "cross_ventilation", "protection_solar", "eaves_m",
        "installations", "architectural_style", "plan_shape",
        "terrain_type", "stairs_mode", "core_mode",
        "distribucion", "curvatura_m", "semilla",
        "mobiliario", "mobiliario_ambito", "mobiliario_densidad",
        "cubierta_tipologia", "cubierta_material",
        "cubierta_pendiente_pct", "cubierta_alero_m", "accesibilidad_auto",
    ]


# ======================================================================
# REGENERACIÓN DE LA EDIFICACIÓN (v3.10.0) — NADA DE CAMBIOS HUÉRFANOS
#
# Lo pedido: «si hay algún local que quisiera mover hacia otro lugar
# debería tener alguna funcionalidad que me ayude a lograrlo pero que
# recalcule y redistribuya los otros locales así como las instalaciones
# y módulos… la idea sería hacer cualquier cambio pero que no sea un
# cambio huérfano sino que regenere todo y se redistribuya todo».
#
# El PROGRAMA de locales (BuildingWizardData) vuelve a ser la fuente de
# verdad: mover / añadir / eliminar / redimensionar un local edita el
# programa, y la SUSTITUCIÓN re-dispara el trazado completo (variantes
# puntuadas incluidas), los vanos, las relaciones y las instalaciones
# sobre la geometría nueva. Antes de crear, PURGA lo generado por el
# asistente en pasadas anteriores (reconocido por su metadata de
# origen); lo dibujado a mano se conserva intacto.
# ======================================================================

WIZARD_ORIGIN = "asistente de edificación"
_MARCA_MANO = "editada_a_mano"   # espejo de ui.cad_tools.MARCA_MANO (v3.14.0)
_SPECIAL_TRACE_TYPES = (CORRIDOR_TYPE, PATIO_TYPE, STAIR_TYPE, CORE_TYPE)
ORIGEN_DISENO = "diseño de espacios"   # espejo de domain.diseno_base (v3.15.0)


def _metadata_of(entity: Any) -> Dict[str, Any]:
    meta = getattr(entity, "metadata", None)
    return meta if isinstance(meta, dict) else {}


def _is_wizard_space(space: Any) -> bool:
    """Un local nacido del trazado del asistente (marca de origen)."""
    req = _metadata_of(space).get("requerimientos", {})
    origen = str(req.get("origen", "")) if isinstance(req, dict) else ""
    return origen.startswith(WIZARD_ORIGIN)


def _wizard_building(ctx: Any) -> Tuple[Any, Dict[str, Any]]:
    """El edificio generado por el asistente y su metadata, si existe."""
    for building in ctx.architecture.list("BUILDING", ctx.project.id):
        meta = _metadata_of(building).get("edificacion", {})
        if isinstance(meta, dict) \
                and str(meta.get("origen", "")).startswith(WIZARD_ORIGIN):
            return building, meta
    return None, {}


def program_from_project(ctx: Any) -> Tuple[BuildingWizardData, List[str]]:
    """Reconstruye el programa editable desde el proyecto abierto.

    Devuelve (data, avisos). Los parámetros del paso 1 salen del
    metadata «edificacion» del edificio generado; los locales, de los
    espacios marcados como generados (los pasillos, patios, escaleras
    y núcleos los recrea el trazado, así que NO entran al programa);
    las relaciones, de las relaciones entre locales normales.
    """
    avisos: List[str] = []
    data = BuildingWizardData()
    repository = ctx.architecture
    pid = ctx.project.id
    building, edif = _wizard_building(ctx)
    if building is None:
        avisos.append("Aún no hay edificación generada por el asistente: "
                      "génerala primero y después regenera aquí.")
        return data, avisos

    data.name = edif.get("nombre") or building.name
    data.usage_type = edif.get("uso_social", data.usage_type)
    dims = edif.get("dimensiones_max_m") or {}
    data.lot_width_m = float(dims.get("ancho", 0) or 0)
    data.lot_depth_m = float(dims.get("fondo", 0) or 0)
    data.construction_type = edif.get("tipologia_constructiva",
                                      data.construction_type)
    data.architectural_style = edif.get("estilo_arquitectonico",
                                        data.architectural_style)
    data.plan_shape = edif.get("forma_en_planta", data.plan_shape)
    data.terrain_type = edif.get("terreno", data.terrain_type)
    stairs = edif.get("escaleras") or {}
    data.stairs_mode = stairs.get("modo", data.stairs_mode)
    core = edif.get("nucleo_rigido") or {}
    data.core_mode = core.get("modo", data.core_mode)
    data.climate = edif.get("clima", data.climate)
    data.structural_system = edif.get("sistema_estructural",
                                      data.structural_system)
    data.facade_orientation = edif.get("orientacion_fachada",
                                       data.facade_orientation)
    data.cross_ventilation = bool(edif.get("ventilacion_cruzada",
                                           data.cross_ventilation))
    data.corridor_enabled = bool(edif.get("pasillo", data.corridor_enabled))
    data.corridor_width_m = float(edif.get("ancho_pasillo_m",
                                           data.corridor_width_m) or 1.2)
    data.wall_thickness_m = float(edif.get("espesor_muros_m",
                                           data.wall_thickness_m) or 0.2)
    data.door_width_m = float(edif.get("ancho_puerta_m",
                                       data.door_width_m) or 0.9)
    data.door_height_m = float(edif.get("alto_puerta_m",
                                        data.door_height_m) or 2.1)
    data.window_width_m = float(edif.get("ancho_ventana_m",
                                         data.window_width_m) or 1.4)
    data.window_height_m = float(edif.get("alto_ventana_m",
                                          data.window_height_m) or 1.2)
    data.window_sill_m = float(edif.get("derrame_ventana_m",
                                        data.window_sill_m) or 0.9)
    bio = edif.get("bioclimatica") or {}
    data.protection_solar = bool(bio.get("proteccion_solar",
                                         data.protection_solar))
    data.eaves_m = float(bio.get("alero_m", data.eaves_m) or 0.6)
    data.installations = list(edif.get("instalaciones") or [])
    data.notes = str(edif.get("notas", "") or "")
    data.distribucion = edif.get("distribucion", data.distribucion)
    data.semilla = int(edif.get("semilla", 0) or 0)
    data.curvatura_m = float(edif.get("curvatura_m", 0.0) or 0.0)
    if edif.get("region_neufert"):
        data.neufert_region = edif["region_neufert"]
    # Concepción de espacios (v3.15.0): preferencias guardadas.
    mob_meta = edif.get("mobiliario") or {}
    if isinstance(mob_meta, dict):
        data.mobiliario = bool(mob_meta.get("activo", data.mobiliario))
        data.mobiliario_ambito = str(mob_meta.get(
            "ambito", data.mobiliario_ambito))
        data.mobiliario_densidad = str(mob_meta.get(
            "densidad", data.mobiliario_densidad))
    cub_meta = edif.get("cubierta") or {}
    if isinstance(cub_meta, dict):
        data.cubierta_tipologia = str(cub_meta.get(
            "tipologia", data.cubierta_tipologia))
        data.cubierta_material = str(cub_meta.get(
            "material", data.cubierta_material))
        data.cubierta_pendiente_pct = float(cub_meta.get(
            "pendiente_pct", data.cubierta_pendiente_pct) or 0.0)
        data.cubierta_alero_m = float(cub_meta.get(
            "alero_m", data.cubierta_alero_m) or 0.0)
    acc_meta = edif.get("accesibilidad") or {}
    if isinstance(acc_meta, dict):
        data.accesibilidad_auto = bool(acc_meta.get(
            "auto", data.accesibilidad_auto))
    # Catálogo de viviendas (v3.23.0): tipología y programa pedido.
    viv_meta = edif.get("vivienda") or {}
    if isinstance(viv_meta, dict):
        etiqueta = str(viv_meta.get("tipologia", "") or "")
        if etiqueta and etiqueta in vivienda_tipologia_choices():
            data.vivienda_tipologia = etiqueta
        try:
            data.vivienda_dormitorios = max(1, min(6, int(
                float(viv_meta.get("dormitorios",
                                   data.vivienda_dormitorios) or 3))))
        except (TypeError, ValueError):
            pass
        try:
            data.vivienda_banos = max(1, min(4, int(
                float(viv_meta.get("banos",
                                   data.vivienda_banos) or 2))))
        except (TypeError, ValueError):
            pass
    # Documento comercial CC/OF (v3.25.0): tipología guardada.
    com_meta = edif.get("comercial") or {}
    if isinstance(com_meta, dict):
        etiqueta_com = str(com_meta.get("tipologia", "") or "")
        if etiqueta_com and etiqueta_com in comercial_tipologia_choices():
            data.comercial_tipologia = etiqueta_com
    # Documento educacional (v3.26.0): tamaño guardado.
    edu_meta = edif.get("educacion") or {}
    if isinstance(edu_meta, dict):
        etiqueta_edu = str(edu_meta.get("tamano", "") or "")
        if etiqueta_edu and etiqueta_edu in educacion_tamano_choices():
            data.educacion_tamano = etiqueta_edu

    levels = [lv for lv in repository.list("LEVEL", pid)
              if lv.building_id == building.id]
    levels.sort(key=lambda lv: (lv.elevation_m, lv.name))
    if not levels:
        avisos.append("El edificio generado no tiene niveles: revisa el "
                      "asistente.")
    data.levels = [LevelSpec(name=lv.name, height_m=lv.height_m)
                   for lv in levels]
    name_of_level = {lv.id: lv.name for lv in levels}

    generated_spaces = [s for s in repository.list("SPACE", pid)
                        if _is_wizard_space(s)]
    normal_spaces = [s for s in generated_spaces
                     if s.space_type not in _SPECIAL_TRACE_TYPES]
    rooms_by_level: Dict[str, List[Any]] = {}
    for space in normal_spaces:
        rooms_by_level.setdefault(space.level_id, []).append(space)
    for level_id, spaces in rooms_by_level.items():
        spaces.sort(key=lambda s: (round(s.boundary[0][1], 3),
                                   round(s.boundary[0][0], 3)))
        for space in spaces:
            xs = [round(p[0], 4) for p in space.boundary]
            ys = [round(p[1], 4) for p in space.boundary]
            data.rooms.append(RoomSpec(
                name=space.name, space_type=space.space_type,
                width_m=max(0.1, max(xs) - min(xs)),
                depth_m=max(0.1, max(ys) - min(ys)),
                level_ref=name_of_level.get(space.level_id,
                                            levels[0].name if levels
                                            else "Planta Baja"),
                with_window=True))

    normal_ids = {s.id for s in normal_spaces}
    name_of_space = {s.id: s.name for s in normal_spaces}
    kind_label = {v: k for k, v in KIND_BY_LABEL.items()}
    for rel in repository.list("SPACE_RELATIONSHIP", pid):
        if rel.from_space_id in normal_ids and rel.to_space_id in normal_ids:
            data.relations.append(RelationSpec(
                a_name=name_of_space.get(rel.from_space_id,
                                         rel.from_space_id),
                b_name=name_of_space.get(rel.to_space_id,
                                         rel.to_space_id),
                kind_es=kind_label.get(rel.kind, "Adyacente a")))
    avisos.append(
        f"Programa reconstruido: {len(data.levels)} nivel(es), "
        f"{len(data.rooms)} locale(s) y {len(data.relations)} "
        "relación(es) del trazado generado. Edítalo a tu gusto y "
        "sustituye la edificación.")
    return data, avisos


# -- edición pura del programa (sin Tk: testeable) -----------------------
def _find_room(data: BuildingWizardData, name: str) -> Optional[RoomSpec]:
    wanted = name.strip().casefold()
    for room in data.rooms:
        if room.name.strip().casefold() == wanted:
            return room
    return None


def move_room(data: BuildingWizardData, name: str,
              delta: int = 1) -> List[str]:
    """Reordena un local dentro de SU nivel (delta ±1).

    La posición en el programa decide dónde lo coloca el trazado:
    mover un local desplaza a los demás y el motor los redistribuye
    al regenerar. Devuelve avisos amables.
    """
    room = _find_room(data, name)
    if room is None:
        return [f"No encuentro el local «{name}» en el programa."]
    level_ref = room.level_ref
    group = [r for r in data.rooms if r.level_ref == level_ref]
    position = group.index(room)
    target = position + int(delta)
    if target < 0 or target >= len(group):
        return [f"«{room.name}» ya está en ese extremo del nivel "
                f"{level_ref}."]
    group.pop(position)
    group.insert(target, room)
    iterator = iter(group)
    data.rooms = [next(iterator) if r.level_ref == level_ref else r
                  for r in data.rooms]
    return [f"«{room.name}» movido: al regenerar, el trazado lo recoloca "
            "y redistribuye a los demás."]


def remove_room(data: BuildingWizardData, name: str) -> List[str]:
    """Quita un local del programa y sus relaciones (nada huérfano)."""
    room = _find_room(data, name)
    if room is None:
        return [f"No encuentro el local «{name}» en el programa."]
    data.rooms.remove(room)
    before = len(data.relations)
    data.relations = [rel for rel in data.relations
                      if rel.a_name != room.name and rel.b_name != room.name]
    cleaned = before - len(data.relations)
    return [f"«{room.name}» eliminado del programa "
            f"({cleaned} relación(es) asociada(s) fuera)."]


def resize_room(data: BuildingWizardData, name: str,
                width_m: float = 0.0, depth_m: float = 0.0) -> List[str]:
    """Cambia las dimensiones de un local (el trazado se recalcula)."""
    room = _find_room(data, name)
    if room is None:
        return [f"No encuentro el local «{name}» en el programa."]
    if width_m <= 0 or depth_m <= 0:
        return ["El ancho y el fondo deben ser mayores que cero."]
    room.width_m = float(width_m)
    room.depth_m = float(depth_m)
    return [f"«{room.name}» redimensionado a "
            f"{width_m:g} × {depth_m:g} m: al regenerar, los vecinos se "
            "redistribuyen."]


def add_room(data: BuildingWizardData, spec: RoomSpec) -> List[str]:
    """Añade un local al programa (crea el nivel si hace falta)."""
    existing = _find_room(data, spec.name)
    if existing is not None:
        return [f"Ya existe un local llamado «{spec.name}»: elige otro "
                "nombre."]
    if spec.level_ref not in data.level_names():
        data.levels.append(LevelSpec(name=spec.level_ref, height_m=3.0))
    data.rooms.append(spec)
    return [f"«{spec.name}» añadido a {spec.level_ref}: el trazado lo "
            "colocará y redistribuirá a los demás al regenerar."]


def move_room_to_level(data: BuildingWizardData, name: str,
                       level_name: str, height_m: float = 3.0) -> List[str]:
    """Mueve un local a OTRO nivel (el nivel nuevo se crea si falta)."""
    room = _find_room(data, name)
    if room is None:
        return [f"No encuentro el local «{name}» en el programa."]
    if level_name not in data.level_names():
        data.levels.append(LevelSpec(name=level_name, height_m=height_m))
    room.level_ref = level_name
    return [f"«{room.name}» pasa a {level_name}: el trazado lo coloca allí "
            "al regenerar."]


# -- purga y sustitución --------------------------------------------------
def collect_generated(ctx: Any) -> Dict[str, List[Any]]:
    """IDs de TODO lo generado por el asistente en el proyecto.

    Devuelve {"SPACE": [...], "WALL": [...], "OPENING": [(kind, id)...],
    "SPACE_RELATIONSHIP": [...], "NODE": [...]} — los terminales de
    instalaciones anclados a locales generados viajan también, porque
    quedarían huérfanos tras la sustitución. Las redes (NETWORK) y los
    niveles/edificio se conservan y se reutilizan.
    """
    repository = ctx.architecture
    pid = ctx.project.id
    # v3.14.0: lo tocado por las herramientas CAD lleva la marca
    # «editada_a_mano» y sobrevive a la regeneración, igual que lo
    # dibujado a mano.
    spaces = [s for s in repository.list("SPACE", pid)
              if _is_wizard_space(s)
              and not _metadata_of(s).get(_MARCA_MANO)]
    # Edificios generados antes de la marca en especiales (v3.9.x):
    # pasillo/patio/escalera/núcleo del edificio del asistente.
    building, _edif = _wizard_building(ctx)
    if building is not None:
        level_ids = {lv.id for lv in repository.list("LEVEL", pid)
                     if lv.building_id == building.id}
        specials = [s for s in repository.list("SPACE", pid)
                    if s.level_id in level_ids
                    and s.space_type in _SPECIAL_TRACE_TYPES
                    and not _is_wizard_space(s)
                    and not _metadata_of(s).get(_MARCA_MANO)]
        spaces.extend(specials)
    space_ids = {s.id for s in spaces}
    walls = [w.id for w in repository.list("WALL", pid)
             if str(_metadata_of(w).get("origen", "")).startswith(
                 WIZARD_ORIGIN)
             and not _metadata_of(w).get(_MARCA_MANO)]
    openings: List[Tuple[str, str]] = []
    seen_openings: set = set()
    for kind in ("DOOR", "WINDOW", "OPENING"):
        for opening in repository.list(kind, pid):
            if opening.id in seen_openings:
                continue
            if str(_metadata_of(opening).get("origen", "")).startswith(
                    WIZARD_ORIGIN) \
                    and not _metadata_of(opening).get(_MARCA_MANO):
                openings.append((kind, opening.id))
                seen_openings.add(opening.id)
    relations = [r.id for r in repository.list("SPACE_RELATIONSHIP", pid)
                 if getattr(r, "from_space_id", "") in space_ids
                 or getattr(r, "to_space_id", "") in space_ids]
    nodes = [n.id for n in ctx.installations.list("NODE", pid)
             if getattr(n, "space_id", "") in space_ids]
    # v3.15.0: mobiliario, cubiertas, rampas y barandillas generadas por
    # los motores de diseño también son «generadas» (lo editado a mano
    # y lo de otro origen sobreviven, igual que los muros).
    diseno: Dict[str, List[str]] = {"FURNITURE": [], "ROOF": [],
                                    "RAMP": [], "HANDRAIL": []}
    for tipo, ids in diseno.items():
        for entidad in repository.list(tipo, pid):
            meta = _metadata_of(entidad)
            if str(meta.get("origen", "")).startswith(ORIGEN_DISENO) \
                    and not meta.get(_MARCA_MANO):
                ids.append(entidad.id)
    return {"SPACE": [s.id for s in spaces], "WALL": walls,
            "OPENING": openings, "SPACE_RELATIONSHIP": relations,
            "NODE": nodes, "FURNITURE": diseno["FURNITURE"],
            "ROOF": diseno["ROOF"], "RAMP": diseno["RAMP"],
            "HANDRAIL": diseno["HANDRAIL"]}


def purge_generated(ctx: Any) -> Dict[str, int]:
    """Elimina lo generado por el asistente, en orden sin huérfanos.

    Terminales de instalaciones → relaciones → vanos → muros →
    locales. Cada baja pasa por los servicios oficiales (CommandBus,
    auditoría, QTO, grafo). Devuelve el recuento por familia.
    """
    from services.architecture_service import ArchitectureService
    from services.installations_service import InstallationsService
    arch = ArchitectureService(ctx)
    inst = InstallationsService(ctx)
    generated = collect_generated(ctx)
    purged = {"nodos": 0, "mobiliario": 0, "diseno_espacios": 0,
              "relaciones": 0, "vanos": 0,
              "muros": 0, "locales": 0}
    for node_id in generated["NODE"]:
        inst.delete_entity("NODE", node_id)
        purged["nodos"] += 1
    # v3.15.0: lo de los motores de diseño baja ANTES que los locales a
    # los que se ancla (mobiliario dentro del local; rampas y
    # barandillas atadas a escaleras/pisos).
    for piece_id in generated["FURNITURE"]:
        arch.delete_entity("FURNITURE", piece_id)
        purged["mobiliario"] += 1
    for tipo in ("ROOF", "RAMP", "HANDRAIL"):
        for entidad_id in generated[tipo]:
            arch.delete_entity(tipo, entidad_id)
            purged["diseno_espacios"] += 1
    for rel_id in generated["SPACE_RELATIONSHIP"]:
        arch.delete_entity("SPACE_RELATIONSHIP", rel_id)
        purged["relaciones"] += 1
    for kind, opening_id in generated["OPENING"]:
        arch.delete_entity(kind if kind in ("DOOR", "WINDOW") else "OPENING",
                           opening_id)
        purged["vanos"] += 1
    for wall_id in generated["WALL"]:
        arch.delete_entity("WALL", wall_id)
        purged["muros"] += 1
    for space_id in generated["SPACE"]:
        arch.delete_entity("SPACE", space_id)
        purged["locales"] += 1
    return purged


def replace_plan(data: BuildingWizardData, ctx: Any,
                 variant: Optional["PlantVariant"] = None) -> Dict[str, Any]:
    """SUSTITUYE la edificación generada: purga y regenera todo.

    Ningún cambio huérfano: primero se purga lo generado en pasadas
    anteriores (locales, muros, vanos, relaciones y terminales de
    instalaciones anclados a esos locales), y después `apply_plan`
    re-traza el edificio completo con la variante elegida, reutiliza
    los niveles y el edificio, y reconstruye las instalaciones sobre
    la geometría nueva. Lo dibujado a mano fuera del asistente se
    conserva. Un solo commit al final: si algo falla, el proyecto
    queda como estaba.
    """
    purged = purge_generated(ctx)
    summary = apply_plan(data, ctx, variant)
    summary["purga"] = purged
    summary["regeneracion"] = True
    return summary


__all__ = [
    "BUILDING_STEPS", "CLIMATE_ZONES", "STRUCTURAL_SYSTEMS", "ORIENTATIONS",
    "RELATION_KINDS_ES", "KIND_BY_LABEL", "CORRIDOR_TYPE", "PATIO_TYPE",
    "CONSTRUCTION_TYPES", "INSTALLATION_MODULES", "USAGE_TYPES",
    "USAGE_HINTS", "USAGE_DOOR_PAIRS", "USAGE_EXTRA_PAIRS", "LEVEL_PROGRAMS",
    "PROGRAM_PRESETS", "suggested_installations", "preset_rooms",
    "apply_usage_program",
    "LevelSpec", "RoomSpec", "RelationSpec", "BuildingWizardData",
    "validate_step", "data_from_values", "PlacedRoom", "order_rooms_for_level",
    "rect_segments", "merge_walls", "OpeningPlacement", "LevelLayout",
    "build_layout", "structural_flag", "PlantVariant", "SCHEME_LABELS",
    "SCHEME_DESCRIPTIONS", "generate_variants", "share_wall",
    "room_requirements", "dna_advisories", "suggest_relations",
    "site_advisories", "neufert_advisories", "neufert_normativa_block",
    "suggested_corridor_width", "suggested_door_width",
    "suggested_wall_thickness", "apply_neufert_defaults",
    "NEUFERT_REGION_BASE", "NEUFERT_REGION_BASE_LABEL",
    "neufert_region_choices", "neufert_region_code",
    "neufert_region_label", "set_neufert_region", "neufert_region_name",
    "stair_geometry_for", "stair_width_for", "SALUD_USAGES",
    "USOS_CON_ESTACIONAMIENTO",
    "ARCHITECTURAL_STYLES", "STYLE_DESCRIPTIONS", "STYLE_SHAPE_PREFERENCE",
    "USAGE_STYLE_SUGGESTIONS", "suggested_architectural_style",
    "DISTRIBUCION_CODES", "DISTRIBUTION_LABELS",
    "DISTRIBUTION_DESCRIPTIONS", "distribution_label",
    "distribution_code", "organicize_level", "apply_distribucion",
    "PLAN_SHAPES", "SHAPE_DESCRIPTIONS", "USAGE_SHAPE_SUGGESTIONS",
    "suggested_plan_shape", "SHAPE_SCHEME_AFFINITY", "shape_affinity",
    "WING_PATIO_WIDTH_M", "WING_PATIO_DEPTH_M",
    "TERRAIN_TYPES", "TERRAIN_DESCRIPTIONS", "terrain_rise_m",
    "STAIR_TYPE", "STAIR_MODES", "STAIR_AUTO", "STAIR_ALWAYS",
    "STAIR_NEVER", "stair_geometry", "stairs_needed", "stairs_wanted",
    "CORE_TYPE", "CORE_MODES", "CORE_AUTO", "CORE_ALWAYS", "CORE_NEVER",
    "CORE_WIDTH_M", "CORE_DEPTH_M", "core_needed", "core_wanted",
    "level_elevations", "build_plan", "apply_plan", "step_summary",
    "building_field_names", "_building_metadata", "parse_float_es",
    "WIZARD_ORIGIN", "program_from_project", "move_room", "remove_room",
    "resize_room", "add_room", "move_room_to_level", "collect_generated",
    "purge_generated", "replace_plan",
    "VIVIENDA_TIPOLOGIA_CLASICA", "vivienda_tipologia_choices",
    "aplicar_programa_vivienda", "vivienda_advisories",
    "USOS_COMERCIALES", "COMERCIAL_SIN_TIPOLOGIA",
    "USOS_EDUCATIVOS", "EDU_SIN_TAMANO", "educacion_tamano_choices",
    "aplicar_programa_educacion", "educacion_advisories",
    "comercial_tipologia_choices", "aplicar_programa_comercial",
    "comercial_advisories",
]
