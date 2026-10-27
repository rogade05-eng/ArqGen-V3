"""MOBILIARIO SEGÚN EL TEMA Y EL USO SOCIAL/DOMÉSTICO (v3.15.0).

«el mobiliario... será vital para concebir los espacios»: este motor
AMUEBLA los locales de la edificación generada con piezas reales (cama,
sofá, sanitarios, mostrador, camillas...) dimensionadas a la Neufert y
colocadas contra los muros con su espacio de paso, de modo que el
plano cuente cómo se VIVE o se TRABAJA cada local, no solo cuánto mide.

Principios:
- Catálogo puro (CATALOGO): cada pieza con su ámbito (doméstico,
  social o ambos), sus tres dimensiones y su categoría.
- Reglas por TIPO DE LOCAL (REGLAS): qué piezas y dónde (anclas a
  paredes con fracciones deterministas). El USO SOCIAL de la
  edificación (Vivienda frente a institucional) decide el ámbito; la
  DENSIDAD (compacto/estándar/amplio) añade o quita piezas cómodas.
- Colocación determinista y a prueba de choques: cada pieza entra en
  el recinto, no pisa a su vecina (si no cabe se recorta con aviso) y
  deja PASO (0.75 m doméstico, 0.90 m social-accesible).
- Entidades FURNITURE reales: auditoría, undo persistente, códigos
  ARQ-FURNITURE-nnn, QTO (FURNITURE_COUNT/FURNITURE_AREA) y la
  regeneración de la edificación las re-crea (nada de huérfanos).
- Cero Tk. Mensajes 100 % codificables en cp1252.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from domain.model import Furniture
from domain.diseno_base import (
    MARCA_MANO, ORIGEN_BASE, bbox_de, cerrar_qto, dentro_de_recinto,
    espacios_objetivo, es_editado_a_mano, es_generado_diseno,
    hay_interseccion, alta_entidad, baja_entidad, lista_tipos,
    metadata_origen, poligono_rectangulo,
)

PT = Tuple[float, float]

# error propio: ARQ-MOB-001 datos de colocación imposibles

# -- catálogo -------------------------------------------------------------------
# (ancho a lo largo de la pared, fondo desde la pared, alto) en metros.
# Dimensiones de uso común (Neufert): cama 1.50x2.00, mesa 0.75 alto,
# encimera a 0.90, armario 2.20, paso entre muebles 0.75 m.

@dataclass(frozen=True)
class Pieza:
    clave: str
    nombre: str
    ambito: str          # domestico | social | ambos
    ancho_m: float
    fondo_m: float
    alto_m: float
    categoria: str       # descanso | estar | comedor | cocina | sanitaria |
                         # trabajo | docencia | atencion | almacenaje
    rotation: str = "muro"   # muro = contra el muro (fondo perpendicular)


CATALOGO: Dict[str, Pieza] = {p.clave: p for p in (
    # -- doméstico ---------------------------------------------------------
    Pieza("cama_doble", "Cama doble", "domestico", 1.50, 2.00, 0.55, "descanso"),
    Pieza("cama_individual", "Cama individual", "ambos", 0.95, 2.00, 0.55, "descanso"),
    Pieza("cuna", "Cuna", "ambos", 0.70, 1.30, 0.90, "descanso"),
    Pieza("mesita", "Mesita de noche", "domestico", 0.45, 0.40, 0.55, "descanso"),
    Pieza("sofa", "Sofá", "domestico", 2.10, 0.90, 0.85, "estar"),
    Pieza("tv_mueble", "Mueble de TV", "domestico", 1.40, 0.42, 0.50, "estar"),
    Pieza("mesa_cocina", "Mesa de cocina", "domestico", 1.10, 0.75, 0.75, "comedor"),
    Pieza("bañera", "Bañera", "ambos", 1.70, 0.75, 0.60, "sanitaria"),
    # -- ambos (doméstico y social) ----------------------------------------
    Pieza("silla", "Silla", "ambos", 0.45, 0.50, 0.90, "estar"),
    Pieza("sillon", "Sillón", "ambos", 0.85, 0.85, 0.85, "estar"),
    Pieza("mesa_auxiliar", "Mesa auxiliar", "ambos", 0.60, 0.40, 0.50, "estar"),
    Pieza("mesa_comedor", "Mesa de comedor", "ambos", 1.40, 0.90, 0.75, "comedor"),
    Pieza("encimera", "Banda de cocina (encimera)", "ambos", 2.00, 0.60, 0.90, "cocina"),
    Pieza("nevera", "Nevera", "ambos", 0.70, 0.70, 1.70, "cocina"),
    Pieza("lavadora", "Lavadora", "ambos", 0.60, 0.60, 0.85, "cocina"),
    Pieza("inodoro", "Inodoro", "ambos", 0.40, 0.65, 0.78, "sanitaria"),
    Pieza("lavabo", "Lavabo", "ambos", 0.60, 0.45, 0.85, "sanitaria"),
    Pieza("ducha", "Plato de ducha", "ambos", 0.90, 0.90, 0.12, "sanitaria"),
    Pieza("armario", "Armario/closet", "ambos", 1.80, 0.60, 2.20, "almacenaje"),
    Pieza("estanteria", "Estantería", "ambos", 0.90, 0.32, 1.80, "almacenaje"),
    Pieza("escritorio", "Escritorio", "ambos", 1.20, 0.60, 0.75, "trabajo"),
    Pieza("mesa_consulta", "Mesa de consulta", "ambos", 0.90, 0.60, 0.75,
          "trabajo"),
    Pieza("camilla", "Camilla", "ambos", 0.70, 1.90, 0.65, "atencion"),
    # -- social --------------------------------------------------------------
    Pieza("mesa_despacho", "Mesa de despacho", "social", 1.60, 0.80, 0.75, "trabajo"),
    Pieza("mesa_reunion", "Mesa de reunión", "social", 2.00, 1.00, 0.75, "trabajo"),
    Pieza("mesa_aula", "Mesa de aula (2 puestos)", "social", 1.20, 0.50, 0.75, "docencia"),
    Pieza("pizarra", "Pizarra", "social", 1.80, 0.08, 1.20, "docencia"),
    Pieza("mostrador", "Mostrador de atención", "social", 1.80, 0.60, 1.10, "atencion"),
    Pieza("archivador", "Archivador", "social", 0.85, 0.50, 1.80, "almacenaje"),
    Pieza("estanteria_libros", "Estantería de libros", "social", 1.80, 0.35, 2.00,
          "almacenaje"),
    Pieza("mesa_social", "Mesa colectiva (8 puestos)", "social", 1.80, 0.75, 0.75,
          "comedor"),
    # -- salud (v3.20.0): equipamiento específico -----------------------
    Pieza("mesa_operaciones", "Mesa de operaciones", "social", 0.70, 2.00,
          0.95, "atencion"),
    Pieza("mesa_autopsia", "Mesa de autopsias", "social", 2.00, 0.80, 0.90,
          "atencion"),
    Pieza("rack_servidor", "Rack de servidores", "social", 0.60, 1.00,
          2.00, "almacenaje"),
)}

AMBITOS: Tuple[str, ...] = ("auto", "domestico", "social", "ambos")
DENSIDADES: Tuple[str, ...] = ("compacto", "estandar", "amplio")

# Paso mínimo entre muebles: doméstico (Neufert 0.75) frente a social
# accesible (0.90 en itinerarios).
PASO_DOMESTICO_M = 0.75
PASO_SOCIAL_M = 0.90


# -- reglas por tipo de local -----------------------------------------------------
# Cada regla: (clave, anclaje, nivel). Anclajes:
#   ("muro", lado, fraccion)     centro a «fondo» de la pieza desde el muro
#   ("centro", fx, fy)           fracción del recinto
#   ("fila", lado, paso_m)       repite a lo largo del muro cada paso
#   ("sillas_mesa", lado, n)     n sillas alrededor de la mesa del centro
# nivel: "esencial" | "comodo" | "extra"  (la densidad decide)

@dataclass(frozen=True)
class Regla:
    clave: str
    anclaje: Tuple[str, ...]
    nivel: str = "esencial"


REGLAS: Dict[str, Tuple[Regla, ...]] = {
    "BEDROOM": (
        Regla("cama_doble", ("cama", )),
        Regla("mesita", ("mesita_cama", )),
        Regla("armario", ("opuesta_cama", 0.15), "comodo"),
        Regla("escritorio", ("muro", "derecha", 0.25), "extra"),
    ),
    "ROOM": (
        Regla("cama_individual", ("cama", )),
        Regla("armario", ("opuesta_cama", 0.15), "comodo"),
        Regla("escritorio", ("muro", "derecha", 0.25), "comodo"),
        Regla("estanteria", ("muro", "izquierda", 0.20), "extra"),
    ),
    "LIVING_ROOM": (
        Regla("sofa", ("muro", "superior", 0.50)),
        Regla("tv_mueble", ("muro", "inferior", 0.50), "comodo"),
        Regla("mesa_auxiliar", ("centro", 0.50, 0.50), "comodo"),
        Regla("estanteria", ("muro", "izquierda", 0.25), "extra"),
    ),
    "DINING_ROOM": (
        Regla("mesa_comedor", ("centro", 0.50, 0.50)),
        Regla("silla", ("sillas_mesa", "h", 4)),
        Regla("armario", ("muro", "inferior", 0.15), "extra"),
    ),
    "DINING_HALL": (
        Regla("mesa_social", ("rejilla", 2.2)),
        Regla("silla", ("sillas_rejilla", 4)),
    ),
    "KITCHEN": (
        Regla("encimera", ("muro", "superior", 0.12)),
        Regla("nevera", ("muro", "superior", 0.88)),
        Regla("mesa_cocina", ("centro", 0.50, 0.62), "comodo"),
        Regla("silla", ("sillas_mesa", "h", 2), "comodo"),
        Regla("lavadora", ("muro", "izquierda", 0.20), "extra"),
    ),
    "KITCHEN_INSTITUTIONAL": (
        Regla("encimera", ("muro", "superior", 0.12)),
        Regla("encimera", ("muro", "inferior", 0.12)),
        Regla("nevera", ("muro", "derecha", 0.20)),
    ),
    "BATHROOM": (
        Regla("inodoro", ("muro", "superior", 0.18)),
        Regla("lavabo", ("muro", "superior", 0.72)),
        Regla("ducha", ("muro", "inferior", 0.12), "comodo"),
        Regla("bañera", ("muro", "inferior", 0.12), "extra"),
    ),
    "LAVATORY": (
        Regla("inodoro", ("muro", "superior", 0.18)),
        Regla("lavabo", ("muro", "superior", 0.72)),
    ),
    "OFFICE": (
        Regla("mesa_despacho", ("muro", "superior", 0.50)),
        Regla("silla", ("silla_despacho", )),
        Regla("silla", ("sillas_frente_despacho", 2), "comodo"),
        Regla("archivador", ("muro", "izquierda", 0.20), "comodo"),
    ),
    "CLASSROOM": (
        Regla("pizarra", ("muro", "superior", 0.50)),
        Regla("mesa_aula", ("rejilla", 2.0)),
        Regla("silla", ("sillas_rejilla", 2)),
    ),
    "WAITING_ROOM": (
        Regla("sillon", ("muro", "superior", 0.30)),
        Regla("sillon", ("muro", "superior", 0.70)),
        Regla("mesa_auxiliar", ("centro", 0.50, 0.55), "comodo"),
    ),
    "CONSULTATION_ROOM": (
        Regla("mesa_consulta", ("muro", "superior", 0.35)),
        Regla("camilla", ("muro", "izquierda", 0.18)),
        Regla("silla", ("sillas_frente_despacho", 2), "comodo"),
    ),
    "EMERGENCY_ROOM": (
        Regla("camilla", ("centro", 0.50, 0.45)),
        Regla("mesa_auxiliar", ("muro", "derecha", 0.20)),
    ),
    "WARD": (
        Regla("cama_individual", ("rejilla", 6.5)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "NURSE_STATION": (
        Regla("mostrador", ("muro", "superior", 0.50)),
        Regla("silla", ("silla_despacho", )),
    ),
    "PHARMACY": (
        Regla("mostrador", ("muro", "superior", 0.50)),
        Regla("estanteria", ("muro", "inferior", 0.25), "comodo"),
        Regla("estanteria", ("muro", "izquierda", 0.25), "extra"),
    ),
    "STOREROOM": (
        Regla("estanteria", ("muro", "superior", 0.20)),
        Regla("estanteria", ("muro", "superior", 0.60), "comodo"),
        Regla("estanteria", ("muro", "inferior", 0.20), "comodo"),
    ),
    "LIBRARY": (
        Regla("estanteria_libros", ("muro", "superior", 0.25)),
        Regla("estanteria_libros", ("muro", "inferior", 0.25)),
        Regla("mesa_comedor", ("centro", 0.50, 0.50), "comodo"),
        Regla("silla", ("sillas_mesa", "h", 4), "comodo"),
    ),
    "LABORATORY": (
        Regla("mesa_aula", ("muro", "superior", 0.30)),
        Regla("mesa_aula", ("muro", "inferior", 0.30), "comodo"),
        Regla("estanteria", ("muro", "derecha", 0.20), "extra"),
    ),
    "MULTIUSE_HALL": (
        Regla("silla", ("rejilla", 1.2)),
        Regla("mesa_despacho", ("muro", "izquierda", 0.25), "comodo"),
    ),
    # -- salud (v3.20.0): quirófano, imagenología, UCI y las nuevas
    #    especialidades pedidas por el usuario --------------------------
    "OPERATING_ROOM": (
        Regla("mesa_operaciones", ("centro", 0.50, 0.50)),
        Regla("encimera", ("muro", "inferior", 0.12), "comodo"),
        Regla("lavabo", ("muro", "superior", 0.18), "comodo"),
    ),
    "IMAGING_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30), "comodo"),
    ),
    "ICU": (
        Regla("cama_individual", ("rejilla", 18.0)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "CT_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30)),
    ),
    "FLUOROSCOPY_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30)),
        Regla("lavabo", ("muro", "superior", 0.18), "comodo"),
    ),
    "ANATOMY_PATHOLOGY": (
        Regla("encimera", ("muro", "superior", 0.25)),
        Regla("encimera", ("muro", "inferior", 0.25), "comodo"),
        Regla("lavabo", ("muro", "derecha", 0.18), "comodo"),
        Regla("estanteria", ("muro", "derecha", 0.60), "extra"),
    ),
    "MORGUE": (
        Regla("mesa_autopsia", ("centro", 0.55, 0.45)),
        Regla("camilla", ("muro", "inferior", 0.08)),
        Regla("lavabo", ("muro", "superior", 0.18), "comodo"),
    ),
    "PROGRESSIVE_CARE": (
        Regla("cama_individual", ("rejilla", 12.0)),
        Regla("mesita", ("sillas_rejilla", 1)),
        Regla("lavabo", ("muro", "izquierda", 0.18), "comodo"),
    ),
    "MICROBIOLOGY_LAB": (
        Regla("mesa_aula", ("muro", "superior", 0.30)),
        Regla("mesa_aula", ("muro", "inferior", 0.30), "comodo"),
        Regla("lavabo", ("muro", "derecha", 0.18), "comodo"),
        Regla("estanteria", ("muro", "derecha", 0.75), "extra"),
    ),
    "SERVER_ROOM": (
        Regla("rack_servidor", ("fila", "superior", 1.5)),
        Regla("mesa_auxiliar", ("muro", "inferior", 0.25), "comodo"),
    ),
    "WAREHOUSE": (
        Regla("estanteria", ("fila", "superior", 1.85)),
        Regla("estanteria", ("fila", "inferior", 1.85), "comodo"),
        Regla("archivador", ("muro", "derecha", 0.50), "extra"),
    ),
    # -- salud v3.22.0: especialidades del documento de especificaciones
    #    técnicas hospitalarias (fichas 3.1-3.60) ------------------------
    "AUTOPSY_ROOM": (
        Regla("mesa_autopsia", ("centro", 0.55, 0.45)),
        Regla("lavabo", ("muro", "superior", 0.18), "comodo"),
        Regla("encimera", ("muro", "inferior", 0.12), "comodo"),
    ),
    "PREOP_ROOM": (
        Regla("camilla", ("rejilla", 5.5)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "RECOVERY_ROOM": (
        Regla("camilla", ("rejilla", 6.0)),
        Regla("mesita", ("sillas_rejilla", 1)),
        Regla("lavabo", ("muro", "izquierda", 0.18), "comodo"),
    ),
    "MRI_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30), "comodo"),
    ),
    "ULTRASOUND_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30), "comodo"),
    ),
    "ICU_PEDIATRIC": (
        Regla("cama_individual", ("rejilla", 16.0)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "NICU": (
        Regla("cuna", ("rejilla", 5.0)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "ISOLATION_ROOM": (
        Regla("cama_individual", ("centro", 0.50, 0.50)),
        Regla("lavabo", ("muro", "superior", 0.18), "comodo"),
    ),
    "MOLECULAR_BIOLOGY_LAB": (
        Regla("mesa_aula", ("muro", "superior", 0.30)),
        Regla("mesa_aula", ("muro", "inferior", 0.30), "comodo"),
        Regla("lavabo", ("muro", "derecha", 0.18), "comodo"),
    ),
    "BLOOD_BANK": (
        Regla("nevera", ("muro", "izquierda", 0.20)),
        Regla("mesa_aula", ("muro", "superior", 0.30), "comodo"),
    ),
    "SAMPLE_COLLECTION": (
        Regla("mesa_consulta", ("muro", "superior", 0.35)),
        Regla("camilla", ("muro", "izquierda", 0.18), "comodo"),
    ),
    "PROCEDURE_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("encimera", ("muro", "inferior", 0.12), "comodo"),
    ),
    "ENDOSCOPY_ROOM": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30), "comodo"),
    ),
    "DIALYSIS_ROOM": (
        Regla("camilla", ("rejilla", 5.5)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "STERILE_PHARMACY": (
        Regla("encimera", ("muro", "superior", 0.12)),
        Regla("estanteria", ("muro", "inferior", 0.25), "comodo"),
    ),
    "REHABILITATION": (
        Regla("sillon", ("muro", "superior", 0.30)),
        Regla("camilla", ("muro", "derecha", 0.20), "comodo"),
    ),
    "HYDROTHERAPY": (
        Regla("bañera", ("centro", 0.50, 0.50)),
        Regla("sillon", ("muro", "superior", 0.20), "comodo"),
    ),
    "DELIVERY_ROOM": (
        Regla("camilla", ("centro", 0.50, 0.50)),
        Regla("encimera", ("muro", "inferior", 0.12), "comodo"),
        Regla("lavabo", ("muro", "superior", 0.18), "comodo"),
    ),
    "NEONATOLOGY": (
        Regla("cuna", ("rejilla", 5.0)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "PEDIATRICS": (
        Regla("cama_individual", ("rejilla", 6.5)),
        Regla("mesita", ("sillas_rejilla", 1)),
    ),
    "DENTISTRY": (
        Regla("mesa_consulta", ("muro", "superior", 0.35)),
        Regla("silla", ("silla_despacho", )),
    ),
    "OPHTHALMOLOGY": (
        Regla("mesa_consulta", ("muro", "superior", 0.35)),
        Regla("camilla", ("muro", "izquierda", 0.18), "comodo"),
    ),
    "DERMATOLOGY": (
        Regla("mesa_consulta", ("muro", "superior", 0.35)),
        Regla("camilla", ("muro", "izquierda", 0.18), "comodo"),
    ),
    "CARDIOLOGY": (
        Regla("mesa_consulta", ("muro", "superior", 0.35)),
        Regla("camilla", ("muro", "izquierda", 0.18), "comodo"),
    ),
    "CATH_LAB": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30), "comodo"),
    ),
    "NUCLEAR_MEDICINE": (
        Regla("camilla", ("centro", 0.40, 0.50)),
        Regla("mesa_consulta", ("muro", "derecha", 0.30), "comodo"),
    ),
    "FORENSIC_PATHOLOGY": (
        Regla("encimera", ("muro", "superior", 0.25)),
        Regla("encimera", ("muro", "inferior", 0.25), "comodo"),
        Regla("estanteria", ("muro", "derecha", 0.60), "extra"),
    ),
    "MEDICAL_GAS_PLANT": (
        Regla("encimera", ("muro", "superior", 0.12)),
    ),
    "UPS_ROOM": (
        Regla("rack_servidor", ("fila", "superior", 1.5)),
    ),
    "LAUNDRY": (
        Regla("lavadora", ("fila", "superior", 0.85)),
        Regla("estanteria", ("muro", "inferior", 0.25), "comodo"),
    ),
    "CLEAN_LINEN": (
        Regla("estanteria", ("fila", "superior", 1.85)),
        Regla("estanteria", ("fila", "inferior", 1.85), "comodo"),
    ),
    "SOILED_LINEN": (
        Regla("estanteria", ("fila", "superior", 1.85)),
    ),
    "CLEANING_ROOM": (
        Regla("lavabo", ("muro", "superior", 0.18)),
        Regla("estanteria", ("muro", "inferior", 0.25), "comodo"),
    ),
    "ADMINISTRATION": (
        Regla("mesa_despacho", ("muro", "superior", 0.50)),
        Regla("silla", ("silla_despacho", )),
        Regla("archivador", ("muro", "izquierda", 0.20), "comodo"),
    ),
    "CLINICAL_ARCHIVE": (
        Regla("archivador", ("fila", "superior", 1.0)),
        Regla("archivador", ("fila", "inferior", 1.0), "comodo"),
    ),
    "ADMISSION": (
        Regla("mostrador", ("muro", "superior", 0.50)),
        Regla("silla", ("silla_despacho", )),
    ),
    "STERILE_STORE": (
        Regla("estanteria", ("fila", "superior", 1.85)),
        Regla("estanteria", ("fila", "inferior", 1.85), "comodo"),
    ),
}

# (la CONSULTATION_ROOM usa «mesa_consulta» propia de 0.90 m)

AMBITO_POR_DEFECTO_SOCIAL: Tuple[str, ...] = (
    "Oficina", "Escuela primaria", "Círculo infantil", "Consultorio médico",
    "Policlínico", "Hospital", "Comedor social", "Centro comunitario",
    "Albergue", "Local comercial",
)


def ambito_auto(usage_type: str = "") -> str:
    """Ámbito según el uso social: Vivienda es doméstica; el resto, social."""
    return "social" if str(usage_type) in AMBITO_POR_DEFECTO_SOCIAL \
        else "domestico"


# -- colocación -----------------------------------------------------------------

def _multiplica_muro(lado: str, recinto: Tuple[float, float, float, float]
                     ) -> Tuple[PT, PT]:
    minx, miny, maxx, maxy = recinto
    if lado == "superior":
        return (minx, maxy), (maxx, maxy)
    if lado == "inferior":
        return (minx, miny), (maxx, miny)
    if lado == "izquierda":
        return (minx, miny), (minx, maxy)
    return (maxx, miny), (maxx, maxy)


def _punto_en_muro(lado: str, recinto: Tuple[float, float, float, float],
                   fraccion: float) -> PT:
    (x1, y1), (x2, y2) = _multiplica_muro(lado, recinto)
    return (x1 + (x2 - x1) * fraccion, y1 + (y2 - y1) * fraccion)


def _rotacion_para_muro(lado: str, pieza: Pieza, horizontal: bool) -> float:
    """Giro del rectángulo para que el FONDO de la pieza quede contra el
    muro (la pieza se define mirando hacia dentro)."""
    if lado == "superior":
        return 0.0
    if lado == "inferior":
        return 180.0
    return 90.0 if lado == "izquierda" else 270.0


def _desplaza_desde_muro(lado: str, punto: PT, fondo: float) -> PT:
    """Empuja el centro hacia DENTRO del recinto media pieza."""
    dx, dy = 0.0, 0.0
    if lado == "superior":
        dy = -fondo / 2.0
    elif lado == "inferior":
        dy = fondo / 2.0
    elif lado == "izquierda":
        dx = fondo / 2.0
    else:
        dx = -fondo / 2.0
    return (punto[0] + dx, punto[1] + dy)


def _lado_opuesto(lado: str) -> str:
    return {"superior": "inferior", "inferior": "superior",
            "izquierda": "derecha", "derecha": "izquierda"}[lado]


def _pieza_cabe(pieza: Pieza, ancho_disponible: float) -> bool:
    return pieza.ancho_m <= ancho_disponible + 0.02


def proponer_piezas(space_type: str, area_m2: float,
                    ambito: str = "auto", densidad: str = "estandar",
                    usage_type: str = "") -> List[Regla]:
    """Reglas activas para un local: ámbito + densidad + área real."""
    if ambito == "auto":
        ambito = ambito_auto(usage_type)
    niveles: Tuple[str, ...] = ("esencial",)
    if densidad in ("estandar", "amplio"):
        niveles = ("esencial", "comodo")
    if densidad == "amplio":
        niveles = ("esencial", "comodo", "extra")
    reglas = [r for r in REGLAS.get(str(space_type).upper(), ())
              if r.nivel in niveles]
    # Área manda: en dormitorios pequeños, cama individual (y sin cuna).
    if str(space_type).upper() == "BEDROOM" and area_m2 < 9.0:
        reglas = [Regla("cama_individual", ("cama", ))] + [
            r for r in reglas if r.clave not in ("cama_doble", "cuna")]
    return reglas


def _resuelve_anclaje(anclaje: Tuple[str, ...], estado: Dict[str, Any]
                      ) -> List[Tuple[str, ...]]:
    """Expande anclajes especiales en anclajes elementales con contexto."""
    clase = anclaje[0]
    recinto = estado["recinto"]
    minx, miny, maxx, maxy = recinto
    horizontal = estado["horizontal"]
    salida: List[Tuple[str, ...]] = []
    if clase == "ignorar":
        return []
    if clase == "cama":
        # cama contra el muro más LARGO (cabecera), centrada
        lado = "izquierda" if not horizontal else "superior"
        salida.append(("cama_lado", lado))
        estado.setdefault("lado_cama", lado)
        return salida
    if clase == "mesita_cama":
        lado = estado.get("lado_cama", "superior")
        salida.append(("muro", lado, 0.86))
        return salida
    if clase == "opuesta_cama":
        lado = _lado_opuesto(estado.get("lado_cama", "superior"))
        return [("opuesta_cama_lado", lado, anclaje[1])]
    if clase == "opuesta_cama_lado":
        return [("muro", anclaje[1], anclaje[2])]
    if clase in ("muro", "fila", "rejilla", "centro", "sillas_mesa",
                 "sillas_rejilla", "silla_despacho",
                 "sillas_frente_despacho"):
        return [anclaje]
    return []


def _ancla_pieza(anclaje: Tuple[str, ...], pieza: Pieza,
                 estado: Dict[str, Any], ya_colocadas: List[Dict[str, Any]],
                 avisos: List[str]) -> Optional[Dict[str, Any]]:
    """Convierte una regla elemental en pieza(s) colocada(s)."""
    recinto = estado["recinto"]
    minx, miny, maxx, maxy = recinto
    ancho_r, fondo_r = maxx - minx, maxy - miny
    clase = anclaje[0]
    propuesta: List[Tuple[float, float, float]] = []  # (x, y, rot)

    if clase == "cama_lado":
        lado = anclaje[1]
        if pieza.ancho_m > (ancho_r if lado in ("superior", "inferior")
                            else fondo_r) + 0.02:
            avisos.append(f"La {pieza.nombre.lower()} no cabe en el local")
            return None
        punto = _punto_en_muro(lado, recinto, 0.42)
        punto = _desplaza_desde_muro(lado, punto, pieza.fondo_m)
        propuesta.append((punto[0], punto[1],
                          _rotacion_para_muro(lado, pieza, True)))
    elif clase == "muro":
        _, lado, fraccion = anclaje
        if lado not in ("superior", "inferior", "izquierda", "derecha"):
            avisos.append(f"{pieza.nombre}: anclaje de muro desconocido")
            return None
        if not _pieza_cabe(pieza, ancho_r if lado in ("superior", "inferior")
                           else fondo_r):
            avisos.append(f"{pieza.nombre}: no cabe en el muro elegido")
            return None
        punto = _punto_en_muro(lado, recinto, min(max(fraccion, 0.0), 1.0))
        punto = _desplaza_desde_muro(lado, punto, pieza.fondo_m)
        propuesta.append((punto[0], punto[1],
                          _rotacion_para_muro(lado, pieza, True)))
    elif clase == "fila":
        # repite la pieza a lo largo del muro cada «paso» metros
        # (estanterías de almacén, racks del nodo informático); el paso
        # nunca baja del ancho de la pieza para no amontonar
        _, lado, paso = anclaje
        if lado not in ("superior", "inferior", "izquierda", "derecha"):
            avisos.append(f"{pieza.nombre}: anclaje de fila desconocido")
            return None
        largo = ancho_r if lado in ("superior", "inferior") else fondo_r
        if not _pieza_cabe(pieza, largo):
            avisos.append(f"{pieza.nombre}: no cabe en el muro elegido")
            return None
        paso = max(float(paso), pieza.ancho_m + 0.05)
        unidades = int((largo - pieza.ancho_m / 2.0) // paso) + 1
        for indice in range(max(unidades, 1)):
            avance = pieza.ancho_m / 2.0 + indice * paso
            if avance > largo - pieza.ancho_m / 2.0 + 1e-9:
                break
            punto = _punto_en_muro(lado, recinto, avance / largo)
            punto = _desplaza_desde_muro(lado, punto, pieza.fondo_m)
            propuesta.append((punto[0], punto[1],
                              _rotacion_para_muro(lado, pieza, True)))
    elif clase == "centro":
        _, fx, fy = anclaje
        rot = 0.0 if pieza.ancho_m >= pieza.fondo_m else 90.0
        propuesta.append((minx + ancho_r * fx, miny + fondo_r * fy, rot))
    elif clase == "rejilla":
        # repite la pieza en una rejilla del área disponible (comedores,
        # aulas, salas con camas): paso = área por unidad
        _, paso_area = anclaje
        celdas = max(1, int(estado["area"] / max(paso_area, 1.0)))
        por_fila = max(1, int(ancho_r // max(pieza.ancho_m + 0.9, 1.0)))
        por_fila = min(por_fila, celdas)
        n_filas = max(1, math.ceil(celdas / max(por_fila, 1)))
        n_filas = min(n_filas, max(1, int(fondo_r // max(pieza.fondo_m + 0.9, 1.0))))
        total = min(celdas, por_fila * n_filas)
        for indice in range(total):
            fila, col = divmod(indice, por_fila)
            paso_x = ancho_r / (por_fila + 1)
            paso_y = fondo_r / (n_filas + 1)
            propuesta.append((minx + paso_x * (col + 1),
                              miny + paso_y * (fila + 1), 0.0))
        estado["ultima_rejilla"] = total
        estado["rejilla_geo"] = (por_fila, n_filas, paso_x, paso_y, minx, miny)
    elif clase == "sillas_rejilla":
        # sillas (o mesitas) alrededor de cada unidad de la última rejilla
        _, por_unidad = anclaje
        geo = estado.get("rejilla_geo")
        if not geo:
            return None
        por_fila, n_filas, paso_x, paso_y, minx0, miny0 = geo
        # una silla al frente de cada unidad de la fila inferior
        for fila in range(n_filas):
            for col in range(por_fila):
                x = minx0 + paso_x * (col + 1)
                y = miny0 + paso_y * (fila + 1) - paso_y / 2.0
                propuesta.append((x, y, 180.0))
                if len(propuesta) >= 24:
                    break
    elif clase == "sillas_mesa":
        _, forma, n_sillas = anclaje
        mesa = ya_colocadas[-1] if ya_colocadas else None
        if mesa is None:
            avisos.append("Sillas sin mesa donde anclarse: se omiten")
            return None
        cx, cy = mesa["x"], mesa["y"]
        if forma == "h":
            for signo in (-1.0, 1.0):
                for indice in range(max(1, n_sillas // 2)):
                    dx = (indice - (max(1, n_sillas // 2) - 1) / 2.0) * 0.60
                    propuesta.append((cx + dx, cy + signo * (mesa["d"] / 2.0 + 0.35),
                                      0.0 if signo > 0 else 180.0))
    elif clase == "silla_despacho":
        mesa = next((m for m in ya_colocadas if m["kind"] in
                     ("mesa_despacho", "escritorio", "mesa_consulta")), None)
        if mesa is None:
            return None
        propuesta.append((mesa["x"], mesa["y"] - mesa["d"] / 2.0 - 0.35, 0.0))
    elif clase == "sillas_frente_despacho":
        _, n = anclaje
        mesa = next((m for m in ya_colocadas if m["kind"] in
                     ("mesa_despacho", "escritorio", "mesa_consulta")), None)
        if mesa is None:
            return None
        for indice in range(n):
            dx = (indice - (n - 1) / 2.0) * 0.62
            propuesta.append((mesa["x"] + dx,
                              mesa["y"] + mesa["d"] / 2.0 + 0.35, 180.0))
    if not propuesta:
        return None

    # Ajuste fino: cada propuesta debe CAER DENTRO del recinto y no pisar
    # a nadie; si pisa, se desliza a lo largo de su eje hasta 6 intentos.
    colocadas_ahora: List[Dict[str, Any]] = []
    for (cx, cy, rot) in propuesta:
        ancho = pieza.ancho_m if abs(rot % 180.0) <= 1e-9 else pieza.fondo_m
        fondo = pieza.fondo_m if abs(rot % 180.0) <= 1e-9 else pieza.ancho_m
        for _intento in range(7):
            rect = poligono_rectangulo(cx, cy, ancho, fondo, 0.0)
            if dentro_de_recinto(rect, recinto) and not any(
                    hay_interseccion(rect, c["rect"]) for c in colocadas_ahora):
                break
            cx += 0.30
            if cx > maxx - ancho / 2.0:
                cx = minx + ancho / 2.0
                cy += 0.30
        else:
            avisos.append(f"{pieza.nombre}: sin sitio sin chocar, se omite")
            continue
        colocadas_ahora.append({
            "kind": pieza.clave, "nombre": pieza.nombre,
            "x": round(cx, 4), "y": round(cy, 4), "rot": float(rot),
            "w": pieza.ancho_m, "d": pieza.fondo_m, "h": pieza.alto_m,
            "rect": poligono_rectangulo(cx, cy, ancho, fondo, 0.0),
            "categoria": pieza.categoria})
    return {"piezas": colocadas_ahora} if colocadas_ahora else None


def verificar_pasos(piezas: Sequence[Dict[str, Any]],
                    recinto: Tuple[float, float, float, float],
                    paso_minimo: float) -> List[str]:
    """Avisos de paso estrecho ENTRE PIEZAS FRENTE A FRENTE.

    Dos piezas solo se comparan cuando quedan separadas en un eje y se
    SOLAPAN en el perpendicular (de verdad se cruzan de frente al
    caminar): así las piezas de muros distintos pero a distinta altura
    no dan falsos positivos.
    """
    avisos: List[str] = []

    def _rango(pieza: Dict[str, Any], eje: str) -> Tuple[float, float]:
        if eje == "y":
            return (pieza["y"] - pieza["d"] / 2.0,
                    pieza["y"] + pieza["d"] / 2.0)
        return (pieza["x"] - pieza["w"] / 2.0,
                pieza["x"] + pieza["w"] / 2.0)

    for eje in ("y", "x"):
        otro = "x" if eje == "y" else "y"
        for i in range(len(piezas)):
            for j in range(i + 1, len(piezas)):
                a, b = piezas[i], piezas[j]
                ra, rb = _rango(a, eje), _rango(b, eje)
                separados = ra[1] <= rb[0] + 1e-9 or rb[1] <= ra[0] + 1e-9
                if not separados:
                    continue
                paso = min(abs(rb[0] - ra[1]), abs(ra[0] - rb[1]))
                oa, ob = _rango(a, otro), _rango(b, otro)
                solapan = min(oa[1], ob[1]) - max(oa[0], ob[0]) > 0.05
                if solapan and 1e-9 < paso < paso_minimo:
                    avisos.append(
                        f"Paso de {paso:.2f} m entre {a['nombre'].lower()} "
                        f"y {b['nombre'].lower()}: menos de "
                        f"{paso_minimo:.2f} m recomendados")
                    return avisos
    return avisos


def colocar_en_local(espacio: Any, reglas: Sequence[Regla],
                     ambito: str, densidad: str) -> Tuple[List[Dict[str, Any]],
                                                          List[str]]:
    """Piezas colocadas en UN local (puro, sin ctx): determinista."""
    boundary = [tuple(p) for p in espacio.boundary]
    recinto = bbox_de(boundary)
    minx, miny, maxx, maxy = recinto
    ancho_r, fondo_r = maxx - minx, maxy - miny
    area = max(espacio.area_m2(), 0.01)
    estado: Dict[str, Any] = {
        "recinto": recinto, "horizontal": ancho_r >= fondo_r, "area": area}
    avisos: List[str] = []
    colocadas: List[Dict[str, Any]] = []
    paso_minimo = PASO_SOCIAL_M if ambito == "social" else PASO_DOMESTICO_M
    for regla in reglas:
        pieza = CATALOGO.get(regla.clave)
        if pieza is None:
            continue
        if ambito in ("domestico", "social") and pieza.ambito not in \
                (ambito, "ambos"):
            continue
        for anclaje in _resuelve_anclaje(regla.anclaje, estado):
            bloque = _ancla_pieza(anclaje, pieza, estado, colocadas, avisos)
            if bloque:
                colocadas.extend(bloque["piezas"])
    colocadas.sort(key=lambda p: (p["y"], p["x"]))
    avisos.extend(verificar_pasos(colocadas, recinto, paso_minimo))
    return colocadas, avisos


# -- generación en el proyecto ---------------------------------------------------

def quitar_mobiliario(ctx: Any, space_ids: Optional[Sequence[str]] = None,
                      solo_generados: bool = True) -> List[str]:
    """Da de baja el mobiliario (por defecto SOLO el de este motor y
    SIN marca de edición manual: lo retocado a mano sobrevive)."""
    bajas: List[str] = []
    ids = set(space_ids or ())
    for pieza in lista_tipos(ctx, "FURNITURE"):
        if ids and pieza.space_id not in ids:
            continue
        if solo_generados and not es_generado_diseno(pieza):
            continue
        if solo_generados and es_editado_a_mano(pieza):
            continue
        codigo = pieza.code
        baja_entidad(ctx, "FURNITURE", pieza.id)
        bajas.append(codigo)
    return bajas


def generar_mobiliario(ctx: Any, data: Any = None,
                       ambito: str = "auto",
                       densidad: str = "estandar",
                       space_ids: Optional[Sequence[str]] = None,
                       nivel_id: str = "",
                       con_qto: bool = True) -> Dict[str, Any]:
    """AMUEBLA los locales del proyecto con el catálogo del uso.

    Idempotente: primero quita el mobiliario generado por este motor
    (lo marcado «editada_a_mano» y lo ajeno se conservan) y después
    coloca de nuevo según el programa actual. Devuelve un resumen
    {operacion, creados, conteo, avisos, qto}.
    """
    if ambito not in AMBITOS:
        raise DomainError(
            message=f"Ámbito de mobiliario desconocido: {ambito}",
            code="ARQ-MOB-001",
            context={"ambito": ambito, "permitidos": list(AMBITOS)},
            suggested_action="Usa auto, domestico, social o ambos.")
    if densidad not in DENSIDADES:
        raise DomainError(
            message=f"Densidad de mobiliario desconocida: {densidad}",
            code="ARQ-MOB-001",
            context={"densidad": densidad, "permitidas": list(DENSIDADES)},
            suggested_action="Usa compacto, estandar o amplio.")
    usage_type = str(getattr(data, "usage_type", "") or "") if data else ""
    if ambito == "auto":
        ambito_resuelto = ambito_auto(usage_type)
    else:
        ambito_resuelto = ambito
    resumen: Dict[str, Any] = {
        "operacion": "mobiliario", "creados": [], "eliminados": [],
        "conteo": {}, "avisos": [], "qto": None, "ambito": ambito_resuelto,
        "densidad": densidad}
    resumen["eliminados"] = quitar_mobiliario(ctx, space_ids=space_ids)
    espacios = espacios_objetivo(ctx, space_ids=space_ids, nivel_id=nivel_id)
    if not espacios:
        resumen["avisos"].append(
            "No hay locales aptos para amueblar (genera antes la "
            "edificación o quita el filtro de nivel).")
        return resumen
    nivel_por_id = {lv.id: lv for lv in lista_tipos(ctx, "LEVEL")}
    for espacio in espacios:
        reglas = proponer_piezas(
            espacio.space_type, espacio.area_m2(), ambito=ambito_resuelto,
            densidad=densidad, usage_type=usage_type)
        piezas, avisos = colocar_en_local(espacio, reglas, ambito_resuelto,
                                          densidad)
        for aviso in avisos:
            resumen["avisos"].append(f"{espacio.name}: {aviso}")
        nivel = nivel_por_id.get(espacio.level_id)
        for pieza in piezas:
            entidad = Furniture(
                project_id=ctx.project.id,
                code=ctx.next_code("ARCHITECTURE", "FURNITURE"),
                level_id=espacio.level_id, space_id=espacio.id,
                kind=pieza["kind"], name=pieza["nombre"],
                x=pieza["x"], y=pieza["y"], rotation_deg=pieza["rot"],
                width_m=pieza["w"], depth_m=pieza["d"], height_m=pieza["h"],
                metadata=metadata_origen(
                    f"mobiliario de {espacio.name} ({espacio.code})",
                    {"ambito": ambito_resuelto, "densidad": densidad,
                     "categoria": pieza["categoria"],
                     "altura_nivel_m": float(nivel.height_m)
                     if nivel else 3.0}))
            alta_entidad(ctx, entidad)
            resumen["creados"].append(entidad.code)
            resumen["conteo"][pieza["kind"]] = \
                resumen["conteo"].get(pieza["kind"], 0) + 1
    if con_qto:
        cerrar_qto(ctx, resumen)
    return resumen


def conteo_por_tipo(ctx: Any) -> Counter:
    return Counter(p.kind for p in lista_tipos(ctx, "FURNITURE"))


def resumen_texto(resumen: Dict[str, Any]) -> str:
    """Texto corto (cp1252) con el resultado de la operación."""
    partes = [f"Mobiliario ({resumen.get('ambito', '')}, "
              f"{resumen.get('densidad', '')})"]
    if resumen.get("conteo"):
        conteo = resumen["conteo"]
        partes.append(", ".join(f"{clave} x{n}"
                                for clave, n in sorted(conteo.items())[:6])
                      + ("..." if len(conteo) > 6 else ""))
    if resumen.get("creados"):
        partes.append(f"{len(resumen['creados'])} pieza(s) creadas")
    if resumen.get("eliminados"):
        partes.append(f"{len(resumen['eliminados'])} baja(s)")
    for aviso in resumen.get("avisos", [])[:2]:
        partes.append(f"aviso: {aviso}")
    if isinstance(resumen.get("qto"), dict):
        partes.append("QTO recalculado")
    return " · ".join(partes)


__all__ = [
    "Pieza", "CATALOGO", "REGLAS", "Regla", "AMBITOS", "DENSIDADES",
    "PASO_DOMESTICO_M", "PASO_SOCIAL_M", "ambito_auto", "proponer_piezas",
    "colocar_en_local", "verificar_pasos", "generar_mobiliario",
    "quitar_mobiliario", "conteo_por_tipo", "resumen_texto",
]
