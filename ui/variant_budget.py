"""Presupuesto VIVO sobre las variantes (v3.12.0).

Del trazado de cada variante (muros, vanos, locales, losas, escaleras)
sale un takeoff paramétrico que se precia con renglones OFICIALES del
catálogo PRECONS III (RoPres 3.30). Nada se persiste y el presupuesto
del proyecto no se toca: la estimación es DERIVADA — vive en
``PlantVariant.cost`` y se recalcula al regenerar las variantes o al
cambiar la calidad de acabados; por eso el presupuesto está «vivo».

Contrato heredado de budget_service (spec 60):
    MODEL → QTO → WORK ITEMS → PRICES → TOTAL
con la particularidad de que el QTO sale del trazado del asistente
(sin pasar por la base de datos) y los precios son los oficiales de
lista (``price_ref``): el catálogo RoPres 3.30 no trae coeficientes de
transporte, indirectos ni beneficio (coefficients vacíos), así que
TOTAL = coste directo de los renglones, igual que en el presupuesto
por catálogo del mismo archivo.

EQUIPOS DE LAS ESPECIALIDADES (v3.21.0): los locales de salud
(tomografía, fluoroscopia, quirófano, UCI, morgue…) aportan sus
APARATOS al presupuesto vivo con la categoría «Equipos». El catálogo
oficial no publica el precio de lista de los aparatos médicos, así
que cada fila viaja con un precio de REFERENCIA (EQUIPOS_POR_USO,
visible y determinista — misma honradez que FACTOR_CALIDAD), no se
busca en el ruleset y la calidad de acabados no la toca.

Renglones usados (verificados contra el catálogo, todos con precio
oficial CUP y sin indicadores de recursos): 011111 manigua, 012224
zanjas, 041424 cimiento corrido, 042125 columnas, 042424 vigas,
042724 losas planas, 043424 escaleras inclinadas, 305356 malla
reticulada, 030121/030122/030123 bloque 0.10/0.15/0.20, 060112
tabiques madera, 035402 panel sándwich, 045124 muros de hormigón,
127121 losa de vigueta y bovedilla, 066914 enviguetado de madera,
124712 cubierta de panel, 110120 impermeabilización, 130112 repello,
130121 enlucido, 140118 losetas, 072111 puertas, 072213 ventana
Miami, 175111/175123/174202/175118/170306 aparatos sanitarios y
260210/260211 puntos eléctricos. Si un renglón faltara en otra
versión del catálogo, la estimación NO falla: anota un aviso y sigue
con el resto (VariantCost.avisos).

La clasificación de cada muro fusionado en EXTERIOR o INTERIOR es
geométrica: se muestrea a lo largo del muro y un tramo es exterior
cuando a un lado no hay local (incluido pasillo, patio, escalera o
núcleo). Así funcionan igual el lineal clásico, las formas L/T/U/H/
cruz/articulada y sus patios, sin reglas ad hoc por esquema.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.errors import DomainError
from ui.building_wizard import PATIO_TYPE, STAIR_TYPE

# -- renglones oficiales del estimador (code → categoría) ----------------------

CATEGORIAS: Tuple[str, ...] = (
    "Preparación", "Cimentación", "Estructura", "Muros", "Cubierta",
    "Revestimientos", "Pisos", "Carpintería", "Sanitaria", "Eléctrica",
    "Mobiliario", "Equipos", "Accesibilidad",
)

# Obra gruesa: la calidad de acabados NO la toca.
CATEGORIAS_DE_OBRA_GRUESA = frozenset({
    "Preparación", "Cimentación", "Estructura", "Muros",
})

# APARATOS Y EQUIPOS (v3.21.0): la calidad de acabados tampoco la
# toca — un tomógrafo no se «revestimenta».
CATEGORIAS_SIN_CALIDAD = frozenset({"Equipos"})

# EQUIPAMIENTO POR TIPO DE LOCAL (v3.21.0) — PRECIOS DE REFERENCIA.
#
# El catálogo oficial PRECONS III (RoPres 3.30) instrumenta la
# CONSTRUCCIÓN (obras, montajes, instalaciones) pero no publica el
# precio de lista de los APARATOS (tomógrafo, arco C, cabina de
# bioseguridad…). Para que el presupuesto vivo no se quede mudo ante
# las especialidades de salud, cada local contribuye sus equipos con
# una APRECIACIÓN de estimación — igual que FACTOR_CALIDAD: valor
# deliberadamente visible, determinista y NO oficial. Cada fila:
# (concepto, unidad, precio_unitario_de_referencia_CUP).
EQUIPOS_POR_USO: Dict[str, Tuple[Tuple[str, str, float], ...]] = {
    "CT_ROOM": (
        ("Tomógrafo helicoidal", "u", 2_400_000.0),
        ("Consola de adquisición y estación de reconstrucción", "u",
         380_000.0),
    ),
    "FLUOROSCOPY_ROOM": (
        ("Equipo de fluoroscopia con arco C", "u", 850_000.0),
    ),
    "IMAGING_ROOM": (
        ("Equipo de radiología convencional", "u", 420_000.0),
    ),
    "OPERATING_ROOM": (
        ("Lámpara escialítica de techo", "u", 220_000.0),
        ("Equipo de anestesia", "u", 480_000.0),
    ),
    "ICU": (
        ("Monitor de signos vitales", "u", 180_000.0),
        ("Ventilador mecánico", "u", 380_000.0),
    ),
    "PROGRESSIVE_CARE": (
        ("Monitor de signos vitales", "u", 180_000.0),
        ("Soporte de oxigenoterapia", "u", 60_000.0),
    ),
    "WARD": (
        ("Soporte de oxigenoterapia", "u", 60_000.0),
    ),
    "EMERGENCY_ROOM": (
        ("Carro de paro (desfibrilador y medicación)", "u", 150_000.0),
    ),
    "ANATOMY_PATHOLOGY": (
        ("Microtomo de tejidos", "u", 260_000.0),
        ("Autoclave de esterilización", "u", 140_000.0),
    ),
    "MORGUE": (
        ("Cámara frigorífica de cadáveres (3 cuerpos)", "u", 380_000.0),
    ),
    "MICROBIOLOGY_LAB": (
        ("Cabina de bioseguridad clase II", "u", 520_000.0),
    ),
    "LABORATORY": (
        ("Campana de extracción de laboratorio", "u", 95_000.0),
    ),
    "SERVER_ROOM": (
        ("SAI con baterías y rack de comunicaciones", "u", 420_000.0),
    ),
    "WASTE_ROOM": (
        ("Contenedor sanitario rígido de desechos", "u", 8_500.0),
    ),
    "WAREHOUSE": (
        ("Transpaleta de carga", "u", 24_000.0),
    ),
    "STERILIZATION_ROOM": (
        ("Autoclave de esterilización", "u", 140_000.0),
    ),
    # -- salud v3.22.0: equipos de las especialidades del documento de
    #    especificaciones técnicas (precios de referencia CUP)
    "MRI_ROOM": (
        ("Resonancia magnética 1.5T", "u", 5_200_000.0),
        ("Consola de operación", "u", 420_000.0),
    ),
    "ULTRASOUND_ROOM": (
        ("Ecógrafo con transductores", "u", 380_000.0),
    ),
    "ICU_PEDIATRIC": (
        ("Monitor pediátrico de signos vitales", "u", 180_000.0),
        ("Ventilador pediátrico", "u", 380_000.0),
    ),
    "NICU": (
        ("Incubadora neonatal", "u", 320_000.0),
        ("Equipo de fototerapia", "u", 90_000.0),
    ),
    "ISOLATION_ROOM": (
        ("Soporte de oxigenoterapia", "u", 60_000.0),
    ),
    "MOLECULAR_BIOLOGY_LAB": (
        ("Termociclador PCR", "u", 620_000.0),
        ("Cabina de bioseguridad clase II", "u", 520_000.0),
    ),
    "BLOOD_BANK": (
        ("Centrífuga refrigerada de sangre", "u", 120_000.0),
        ("Refrigerador de hemocomponentes", "u", 220_000.0),
    ),
    "SAMPLE_COLLECTION": (
        ("Refrigerador de muestras", "u", 120_000.0),
    ),
    "PROCEDURE_ROOM": (
        ("Carro de paro (desfibrilador y medicación)", "u", 150_000.0),
    ),
    "ENDOSCOPY_ROOM": (
        ("Torre de videoendoscopia", "u", 780_000.0),
    ),
    "DIALYSIS_ROOM": (
        ("Máquina de hemodiálisis", "u", 240_000.0),
        ("Sistema de tratamiento de agua", "u", 480_000.0),
    ),
    # -- comercial/oficinas v3.25.0: equipos de REFERENCIA del
    #    documento CC/OF (precios CUP sin calidad: la categoría
    #    «Equipos» no la escala el nivel de acabados).
    "TELECOM_ROOM": (
        ("Rack de telecomunicaciones 19 pulgadas", "u", 85_000.0),
    ),
    "SECURITY_ROOM": (
        ("Cámara de videovigilancia (CCTV)", "u", 12_000.0),
        ("Monitor de seguridad", "u", 18_000.0),
    ),
    "LOADING_DOCK": (
        ("Nivelador de andén", "u", 95_000.0),
        ("Sello de andén", "u", 25_000.0),
    ),
    "VESTIBULE": (
        ("Torniquete de control de accesos", "u", 60_000.0),
    ),
    "BICYCLE_PARKING": (
        ("Parillero para bicicletas (5 puestos)", "u", 6_500.0),
    ),
    "COMMERCIAL_KITCHEN": (
        ("Campana extractora industrial", "u", 42_000.0),
    ),
    "STERILE_PHARMACY": (
        ("Cabina de flujo laminar", "u", 520_000.0),
    ),
    "DELIVERY_ROOM": (
        ("Mesa de partos", "u", 95_000.0),
        ("Lámpara de parto", "u", 60_000.0),
    ),
    "NEONATOLOGY": (
        ("Incubadora neonatal", "u", 320_000.0),
    ),
    "PEDIATRICS": (
        ("Monitor de signos vitales", "u", 180_000.0),
    ),
    "DENTISTRY": (
        ("Sillón dental completo", "u", 380_000.0),
    ),
    "OPHTHALMOLOGY": (
        ("Lámpara de hendidura", "u", 120_000.0),
    ),
    "CARDIOLOGY": (
        ("Electrocardiógrafo", "u", 45_000.0),
        ("Ergómetro", "u", 180_000.0),
    ),
    "CATH_LAB": (
        ("Angiógrafo digital", "u", 3_800_000.0),
    ),
    "NUCLEAR_MEDICINE": (
        ("Gammacámara", "u", 4_500_000.0),
    ),
    "FORENSIC_PATHOLOGY": (
        ("Microtomo de tejidos", "u", 260_000.0),
    ),
    "MEDICAL_GAS_PLANT": (
        ("Manifold de oxígeno con reserva", "u", 240_000.0),
    ),
    "GENERATOR_ROOM": (
        ("Grupo electrógeno diésel", "u", 850_000.0),
    ),
    "UPS_ROOM": (
        ("SAI industrial con baterías", "u", 480_000.0),
    ),
    "PUMP_ROOM": (
        ("Batería de bombas hidroneumáticas", "u", 240_000.0),
    ),
    "LAUNDRY": (
        ("Lavadora industrial", "u", 950_000.0),
    ),
    "AUTOPSY_ROOM": (
        ("Conservador de cadáveres", "u", 180_000.0),
    ),
    "PREOP_ROOM": (
        ("Monitor de signos vitales", "u", 180_000.0),
    ),
    "RECOVERY_ROOM": (
        ("Monitor de signos vitales", "u", 180_000.0),
    ),
    # -- escuelas y círculos infantiles v3.26.0: equipos de REFERENCIA
    #    sin calidad (precios CUP orientativos, editables §66)
    "LAB_COMPUTACION": (
        ("PC de aula con monitor", "u", 28_000.0),
        ("Switch de red de 24 puertos", "u", 45_000.0),
    ),
    "TALLER_TECNOLOGICO": (
        ("Banco de trabajo con tornillo", "u", 16_000.0),
    ),
    "GYMNASIO": (
        ("Lote base de equipos de gimnasia", "u", 65_000.0),
    ),
    "INFIRMARY": (
        ("Camilla de observación", "u", 15_000.0),
    ),
    "SALA_CUNA": (
        ("Cuna estándar 0.60 x 1.20 m", "u", 7_200.0),
    ),
    "HIGIENE_CI": (
        ("Mesa de cambio con bañera", "u", 9_500.0),
    ),
    "DORMITORIO_COLETIVO": (
        ("Litera metálica 0.90 x 1.90 m", "u", 7_800.0),
    ),
    "SALA_MUSICA": (
        ("Piano vertical (referencia)", "u", 120_000.0),
    ),
}

RENGLONES: Dict[str, str] = {
    "011111": "Preparación",       # manigua manual (limpieza y trazo), m2
    "012224": "Preparación",       # zanjas en tierra mecanizada, m3
    "041424": "Cimentación",       # corridos vertido manual, m3
    "042125": "Estructura",        # columnas y pedestales, m3
    "042424": "Estructura",        # cerramientos, vigas y cabezales, m3
    "042724": "Estructura",        # losas planas vertido manual, m3
    "043424": "Estructura",        # escaleras y losas inclinadas, m3
    "305356": "Estructura",        # malla reticulada en losa, kg
    "030121": "Muros",             # muros bloque 0.10 m, m2
    "030122": "Muros",             # muros bloque 0.15 m, m2
    "030123": "Muros",             # muros bloque 0.20 m, m2
    "045124": "Muros",             # muros de hormigón 150-300 kg/cm2, m3
    "060112": "Muros",             # tabiques de madera, m2
    "035402": "Muros",             # panel sándwich en pared > 3 m, m2
    "127121": "Estructura",        # losa vigueta T-12-4 + bovedilla, m2
    "066914": "Estructura",        # enviguetado y entablado madera, m2
    "110120": "Cubierta",          # impermeabilización built-up, m2
    "124712": "Cubierta",          # cubierta de panel sándwich, m2
    "130112": "Revestimientos",    # repello en muros y columnas, m2
    "130121": "Revestimientos",    # enlucido con masilla en techos, m2
    "140118": "Pisos",             # losetas hidráulicas o mosaicos, m2
    "072111": "Carpintería",       # puertas hasta 2 m2 de área, m2
    "072213": "Carpintería",       # ventana Miami, m2
    "175111": "Sanitaria",         # inodoro, u
    "175123": "Sanitaria",         # lavamanos, u
    "174202": "Sanitaria",         # instalación de ducha (PPR), u
    "175118": "Sanitaria",         # fregadero, u
    "170306": "Sanitaria",         # fregadero y lavadero, u
    "260210": "Eléctrica",         # luminaria fluorescente adosada, u
    "260211": "Eléctrica",         # interruptor, u
    # Concepción de espacios (v3.15.0): cubiertas por material,
    # mobiliario y accesibilidad (verificados en el catálogo RoPres 3.30).
    "126211": "Cubierta",          # tejas planas/francesas s/ tablazón, m2
    "124151": "Cubierta",          # chapas de zinc galvanizado 0.65 mm, m2
    "072411": "Mobiliario",        # closet hasta 2.40 x 1.80 con jambas, m2
    "072351": "Mobiliario",        # mueble integral de cocina PVC, u
    "094211": "Accesibilidad",     # baranda de hierro en escaleras y pisos, m
}

# -- calidad de acabados --------------------------------------------------------

# Cinco niveles alineados con el §51 del catálogo de viviendas (v3.23.0):
# 1 Económico, 2 Estándar, 3 Medio, 4 Premium y 5 Lujo. «Económica»,
# «Estándar» y «Premium» conservan su nombre y factor históricos para no
# romper proyectos ni pruebas; «Media» y «Lujo» completan la escala.
CALIDADES: Tuple[str, ...] = ("Económica", "Media", "Estándar",
                              "Premium", "Lujo")
CALIDAD_DEFECTO = "Estándar"

# Factor sobre el coste DIRECTO de las categorías de acabado; la obra
# gruesa queda a 1.0 siempre. Constantes deliberadamente visibles: son
# una APRECIACIÓN de estimación, no un precio oficial.
FACTOR_CALIDAD: Dict[str, float] = {
    "Económica": 0.85,
    "Media": 0.95,
    "Estándar": 1.0,
    "Premium": 1.30,
    "Lujo": 1.60,
}

# -- constantes constructivas del estimador (transparentes) ---------------------

ESPESOR_LOSA_MACIZA_M = 0.20     # losa de hormigón (m3 = m2 × espesor)
ESCALERA_ESPESOR_M = 0.35        # cajón de escalera estimado
ALERO_ESPESOR_M = 0.12           # losa de alero perimetral
CIMIENTO_ANCHO_M = 0.20          # viga corrida bajo el muro
CIMIENTO_ALTO_M = 0.40
ZANJA_HOLGURA_M = 0.10           # holgura de excavación sobre el muro
ZANJA_PROFUNDA_M = 0.70
LOSA_ACERO_KG_M2 = 4.5           # malla electrosoldada en losas
COLUMNA_SEPARACION_M = 4.0       # tramo entre columnas de pórtico
COLUMNA_SECCION_M = 0.30
VIGA_SECCION_M = (0.20, 0.30)
PASO_MUESTREO_M = 1.0            # muestreo de exterior/interior a lo largo del muro

SISTEMAS_CON_PORTICO = ("Pórtico de hormigón", "Mixto (pórtico + muros)")

_MURO_BLOQUE_POR_ESPESOR: Tuple[Tuple[float, str], ...] = (
    (0.12, "030121"), (0.17, "030122"), (math.inf, "030123"),
)


def _renglon_muro(data: Any) -> Tuple[str, str]:
    """Renglón de muro según la tipología constructiva elegida."""
    tipo = str(getattr(data, "construction_type", ""))
    if tipo == "Madera ligera":
        return "060112", "m2"
    if tipo == "Panel prefabricado (sandwich)":
        return "035402", "m2"
    if tipo == "Hormigón armado (monolítico)":
        return "045124", "m3"
    espesor = float(getattr(data, "wall_thickness_m", 0.2) or 0.2)
    for limite, code in _MURO_BLOQUE_POR_ESPESOR:
        if espesor <= limite:
            return code, "m2"
    return "030123", "m2"


def _renglon_losa(data: Any) -> Tuple[str, str]:
    """Renglón de losa según la tipología constructiva elegida."""
    tipo = str(getattr(data, "construction_type", ""))
    if tipo == "Madera ligera":
        return "066914", "m2"
    if tipo in ("Losa maciza de hormigón",
                "Hormigón armado (monolítico)"):
        return "042724", "m3"
    return "127121", "m2"  # vigueta y bovedilla


# -- geometría: exterior vs interior --------------------------------------------

def _rects_del_nivel(layout: Any) -> List[Tuple[float, float, float, float]]:
    return [(r.x, r.y, r.w, r.d) for r in layout.all_rooms]


def _contiene(rect: Tuple[float, float, float, float],
              px: float, py: float) -> bool:
    # Estricto: un punto CAÍDO en el borde del local no lo cubre (así
    # las esquinas no «contaminan» la clasificación del muro vecino).
    x, y, w, d = rect
    return x < px < x + w and y < py < y + d


def _es_muro_horizontal(wall: Dict[str, Any]) -> bool:
    (x1, y1), (x2, y2) = wall["start"], wall["end"]
    return abs(y1 - y2) <= 1e-6


def _longitud_muro(wall: Dict[str, Any]) -> float:
    (x1, y1), (x2, y2) = wall["start"], wall["end"]
    return abs(x2 - x1) if _es_muro_horizontal(wall) else abs(y2 - y1)


def _lado_cubierto(rects: List[Tuple[float, float, float, float]],
                   px: float, py: float) -> bool:
    return any(_contiene(rect, px, py) for rect in rects)


def _longitudes_de_muros(layout: Any) -> Tuple[float, float]:
    """Metros de muro EXTERIOR e INTERIOR de un nivel trazado.

    Un muro fusionado se muestrea a lo largo de su eje (paso 1 m,
    mínimo 2 muestras): un tramo es exterior cuando a un lado no hay
    local (patio, pasillo, escalera y núcleo cuentan como lado
    cubierto). Es una clasificación geométrica: no hay reglas por
    esquema y funciona igual en L, T, U, H, cruz y articuladas.
    """
    rects = _rects_del_nivel(layout)
    if not rects:
        return 0.0, 0.0
    exterior = 0.0
    interior = 0.0
    for wall in layout.walls:
        longitud = float(wall.get("length", 0.0)) or _longitud_muro(wall)
        if longitud <= 0.0:
            continue
        (x1, y1), (x2, y2) = wall["start"], wall["end"]
        horizontal = _es_muro_horizontal(wall)
        # Muestreo en los PUNTOS MEDIOS de tramos iguales: nunca en los
        # extremos, donde el local perpendicular colindante haría
        # parecer interior una esquina de fachada.
        muestras = max(2, int(math.ceil(longitud / PASO_MUESTREO_M)) + 1)
        ext_tramos = 0
        for indice in range(muestras):
            t = (indice + 0.5) / muestras
            mx = x1 + (x2 - x1) * t
            my = y1 + (y2 - y1) * t
            if horizontal:
                a = _lado_cubierto(rects, mx, my - 0.05)
                b = _lado_cubierto(rects, mx, my + 0.05)
            else:
                a = _lado_cubierto(rects, mx - 0.05, my)
                b = _lado_cubierto(rects, mx + 0.05, my)
            if a and b:
                interior += longitud / muestras
            else:
                ext_tramos += 1
        exterior += longitud * ext_tramos / muestras
    return round(exterior, 3), round(interior, 3)


# -- takeoff paramétrico ----------------------------------------------------------

def variant_takeoff(data: Any, variant: Any) -> List[Dict[str, Any]]:
    """Cantidades del trazado de una variante, por renglón oficial.

    Devuelve filas ``{category, code, concept, unit, quantity}`` sin
    precios: el precio se resuelve después contra el ruleset para que
    la fuente de verdad sea siempre el catálogo.
    """
    filas: List[Dict[str, Any]] = []
    acumuladas: Dict[str, Dict[str, Any]] = {}

    def add(category: str, code: str, concept: str, unit: str,
            quantity: float) -> None:
        if quantity <= 1e-9:
            return
        fila = acumuladas.get(code)
        if fila is None:
            fila = {"category": category, "code": code,
                    "concept": concept, "unit": unit, "quantity": 0.0}
            acumuladas[code] = fila
        fila["quantity"] += float(quantity)

    muro_code, muro_unit = _renglon_muro(data)
    losa_code, losa_unit = _renglon_losa(data)
    monolitico = str(getattr(data, "construction_type", "")) == \
        "Hormigón armado (monolítico)"
    con_portico = str(getattr(data, "structural_system", "")) \
        in SISTEMAS_CON_PORTICO
    layouts = list(getattr(variant, "layouts", []) or [])

    ext_nivel_0 = 0.0
    int_nivel_0 = 0.0
    for indice, layout in enumerate(layouts):
        nivel = next((lv for lv in data.levels
                      if lv.name == layout.level_name), None)
        altura = float(nivel.height_m) if nivel is not None else 3.0
        locales = [r for r in layout.all_rooms
                   if r.space_type != PATIO_TYPE]
        area_nivel = sum(r.area_m2() for r in locales)
        ext_len, int_len = _longitudes_de_muros(layout)
        if indice == 0:
            ext_nivel_0, int_nivel_0 = ext_len, int_len

        vanos_m2 = sum(o.width_m * o.height_m
                       for o in (list(layout.doors) + list(layout.windows)))
        muro_area = max((ext_len + int_len) * altura - vanos_m2, 0.0)
        if muro_unit == "m3":
            add("Muros", muro_code, "Muros de hormigón armado", "m3",
                muro_area * 0.20)
        else:
            add("Muros", muro_code, "Muros y cerramientos", "m2",
                muro_area)

        if con_portico and ext_len > 0:
            columnas = math.ceil(ext_len / COLUMNA_SEPARACION_M)
            add("Estructura", "042125", "Columnas de pórtico", "m3",
                columnas * COLUMNA_SECCION_M * COLUMNA_SECCION_M * altura)
            add("Estructura", "042424", "Vigas de corona y amarre", "m3",
                ext_len * VIGA_SECCION_M[0] * VIGA_SECCION_M[1])

        for room in layout.all_rooms:
            if room.space_type == STAIR_TYPE:
                add("Estructura", "043424", "Escalera de hormigón", "m3",
                    room.w * room.d * ESCALERA_ESPESOR_M)

        if area_nivel > 0:
            if losa_unit == "m3":
                add("Estructura", losa_code, "Losa de hormigón", "m3",
                    area_nivel * ESPESOR_LOSA_MACIZA_M)
            else:
                add("Estructura", losa_code,
                    "Losa (vigueta y bovedilla / entablado)", "m2",
                    area_nivel)
            add("Estructura", "305356", "Malla electrosoldada en losas",
                "kg", area_nivel * LOSA_ACERO_KG_M2)
            add("Revestimientos", "130121", "Enlucido de techos", "m2",
                area_nivel)
            add("Pisos", "140118", "Piso de losetas o mosaico", "m2",
                area_nivel)
        add("Revestimientos", "130112", "Repello de muros (dos caras)",
            "m2", muro_area * 2.0)
        add("Carpintería", "072111", "Puertas de madera", "m2",
            sum(o.width_m * o.height_m for o in layout.doors))
        add("Carpintería", "072213", "Ventanas tipo Miami", "m2",
            sum(o.width_m * o.height_m for o in layout.windows))

        tipos = Counter(r.space_type for r in layout.all_rooms)
        banos = tipos.get("BATHROOM", 0)
        add("Sanitaria", "175111", "Inodoro", "u", banos)
        add("Sanitaria", "175123", "Lavamanos", "u", banos)
        add("Sanitaria", "174202", "Instalación de ducha", "u", banos)
        add("Sanitaria", "175118", "Fregadero de cocina", "u",
            tipos.get("KITCHEN", 0))
        add("Sanitaria", "170306", "Fregadero y lavadero", "u",
            tipos.get("LAUNDRY", 0))
        n_locales = len(layout.all_rooms)
        add("Eléctrica", "260210", "Luminaria fluorescente", "u",
            n_locales)
        add("Eléctrica", "260211", "Interruptor", "u", n_locales)

    if layouts:
        # Preparación y cimentación: una sola vez, con el nivel 0.
        rooms0 = layouts[0].all_rooms
        if rooms0:
            min_x = min(r.x for r in rooms0)
            min_y = min(r.y for r in rooms0)
            max_x = max(r.x + r.w for r in rooms0)
            max_y = max(r.y + r.d for r in rooms0)
            add("Preparación", "011111", "Limpieza y trazo (manigua)",
                "m2", (max_x - min_x) * (max_y - min_y))
        total_len_0 = ext_nivel_0 + int_nivel_0
        if total_len_0 > 0:
            add("Preparación", "012224", "Excavación de zanjas", "m3",
                total_len_0 * (float(getattr(data, "wall_thickness_m",
                                             0.2) or 0.2)
                               + ZANJA_HOLGURA_M) * ZANJA_PROFUNDA_M)
            add("Cimentación", "041424", "Cimiento corrido de hormigón",
                "m3", total_len_0 * CIMIENTO_ANCHO_M * CIMIENTO_ALTO_M)
        # Cubierta sobre el último nivel trazado.
        top = layouts[-1]
        area_top = sum(r.area_m2() for r in top.all_rooms
                       if r.space_type != PATIO_TYPE)
        if area_top > 0:
            from domain.cubiertas import resolver_parametros
            _cub = resolver_parametros(
                data,
                tipologia=str(getattr(data, "cubierta_tipologia", "auto")),
                material=str(getattr(data, "cubierta_material", "auto")),
                pendiente_pct=float(getattr(data, "cubierta_pendiente_pct",
                                            0.0) or 0.0),
                alero_m=float(getattr(data, "cubierta_alero_m", 0.0) or 0.0)
                or None)
            if _cub["tipologia"].startswith("plana"):
                if str(getattr(data, "construction_type", "")) == \
                        "Panel prefabricado (sandwich)":
                    add("Cubierta", "124712", "Cubierta de panel sándwich",
                        "m2", area_top)
                else:
                    add("Cubierta", "110120",
                        "Impermeabilización de cubierta", "m2", area_top)
            elif _cub["material"] == "chapa_metalica":
                _incl = area_top * math.sqrt(1.0 + (_cub["pendiente_pct"]
                                                    / 100.0) ** 2)
                add("Cubierta", "124151", "Cubierta de chapa de zinc "
                    "galvanizada", "m2", _incl)
            else:
                _incl = area_top * math.sqrt(1.0 + (_cub["pendiente_pct"]
                                                    / 100.0) ** 2)
                add("Cubierta", "126211", "Cubierta de tejas sobre "
                    "tablazón de madera", "m2", _incl)
            if bool(getattr(data, "protection_solar", False)):
                ext_top, _int_top = _longitudes_de_muros(top)
                add("Cubierta", "042724", "Alero perimetral (losa)",
                    "m3", ext_top * float(getattr(data, "eaves_m", 0.6)
                                           or 0.6) * ALERO_ESPESOR_M)
        # MOBILIARIO Y ACCESIBILIDAD (v3.15.0): los closets de los
        # dormitorios, el mueble integral de cada cocina y la barandilla
        # de las escaleras entran al estimador con renglones oficiales.
        if bool(getattr(data, "mobiliario", True)):
            dormitorios = sum(1 for layout in layouts
                              for r in layout.all_rooms
                              if r.space_type == "BEDROOM")
            cocinas = sum(1 for layout in layouts
                          for r in layout.all_rooms
                          if r.space_type == "KITCHEN")
            if dormitorios:
                add("Mobiliario", "072411", "Closet por dormitorio "
                    "(2.40 x 1.80 m)", "m2", dormitorios * 2.40 * 1.80)
            if cocinas:
                add("Mobiliario", "072351", "Mueble integral de cocina",
                    "u", cocinas)
        if bool(getattr(data, "accesibilidad_auto", True)):
            for layout in layouts:
                for room in layout.all_rooms:
                    if room.space_type == STAIR_TYPE:
                        add("Accesibilidad", "094211",
                            "Barandilla de escalera (ambos lados)", "m",
                            2.0 * max(room.w, room.d))

        # EQUIPOS DE LAS ESPECIALIDADES (v3.21.0): cada local de salud
        # contribuye sus APARATOS con precio de referencia (el catálogo
        # oficial no publica tomógrafos ni arcos C — ver
        # EQUIPOS_POR_USO). Van aparte (código vacío + precio en la
        # propia fila) para que el estimador no los busque en el
        # ruleset y la calidad de acabados no los toque.
        tipos_locales = Counter(r.space_type for layout in layouts
                                for r in layout.all_rooms)
        for space_type, aparatos in EQUIPOS_POR_USO.items():
            cuantos = tipos_locales.get(space_type, 0)
            if cuantos <= 0:
                continue
            for concepto, unidad, precio_ref in aparatos:
                acumuladas.setdefault(f"EQ::{concepto}", {
                    "category": "Equipos", "code": "",
                    "concept": concepto, "unit": unidad,
                    "quantity": 0.0, "unit_price": float(precio_ref),
                    "fuente": "referencia",
                })["quantity"] += float(cuantos)
    orden = {categoria: indice for indice, categoria
             in enumerate(CATEGORIAS)}
    filas.extend(sorted(acumuladas.values(),
                        key=lambda fila: (orden.get(fila["category"], 99),
                                          fila["code"])))
    for fila in filas:
        fila["quantity"] = round(fila["quantity"], 3)
    return filas


# -- resultado ----------------------------------------------------------------------

@dataclass
class VariantCost:
    """Estimación PRECONS de una variante (derivada, no persistida)."""

    calidad: str = CALIDAD_DEFECTO
    ruleset_code: str = ""
    currency: str = "CUP"
    area_m2: float = 0.0
    rows: List[Dict[str, Any]] = field(default_factory=list)
    categories: Dict[str, float] = field(default_factory=dict)
    avisos: List[str] = field(default_factory=list)

    @property
    def direct(self) -> float:
        return round(sum(self.categories.values()), 2)

    @property
    def total(self) -> float:
        # El catálogo RoPres 3.30 no trae coeficientes (indirectos,
        # beneficio, transporte): el total oficial es el directo.
        return self.direct

    @property
    def cost_m2(self) -> float:
        if self.area_m2 > 0:
            return round(self.total / self.area_m2, 2)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calidad": self.calidad,
            "ruleset_code": self.ruleset_code,
            "currency": self.currency,
            "area_m2": self.area_m2,
            "direct": self.direct,
            "total": self.total,
            "cost_m2": self.cost_m2,
            "categories": dict(self.categories),
            "rows": [dict(row) for row in self.rows],
            "avisos": list(self.avisos),
        }


def estimate_variant_cost(data: Any, variant: Any, ruleset: Any,
                          calidad: str = CALIDAD_DEFECTO) -> VariantCost:
    """Precia el takeoff de la variante con precios oficiales.

    Los renglones de acabado se escalan con el factor de calidad; la
    obra gruesa queda intacta. Un renglón ausente en el catálogo no
    detiene la estimación: se anota en ``avisos`` y se continúa.
    Los EQUIPOS de las especialidades (v3.21.0) viajan con su precio
    de referencia en la propia fila (código vacío): no se buscan en
    el ruleset y la calidad de acabados no los toca.
    """
    factor_calidad = FACTOR_CALIDAD.get(calidad, 1.0)
    resultado = VariantCost(
        calidad=calidad if calidad in FACTOR_CALIDAD else CALIDAD_DEFECTO,
        ruleset_code=str(getattr(ruleset, "code", "")),
        currency=str(getattr(ruleset, "currency", "CUP")),
        area_m2=round(sum(layout.total_area_m2()
                          for layout in (variant.layouts or [])), 2))
    for fila in variant_takeoff(data, variant):
        code = str(fila["code"])
        if not code:
            unit_price = float(fila.get("unit_price", 0.0) or 0.0)
            amount = fila["quantity"] * unit_price
            resultado.rows.append({**fila,
                                   "unit_price": round(unit_price, 2),
                                   "amount": round(amount, 2),
                                   "fuente": "referencia"})
            resultado.categories[fila["category"]] = \
                resultado.categories.get(fila["category"], 0.0) + amount
            continue
        try:
            oficial = ruleset.official_price(code)
        except DomainError as err:
            resultado.avisos.append(
                f"Renglón {code} ausente en el catálogo: "
                f"{getattr(err, 'message', err)}")
            continue
        unit_price = float(oficial.get("total", 0.0) or 0.0)
        if fila["category"] in CATEGORIAS_DE_OBRA_GRUESA \
                or fila["category"] in CATEGORIAS_SIN_CALIDAD:
            factor = 1.0
        else:
            factor = factor_calidad
        amount = fila["quantity"] * unit_price * factor
        resultado.rows.append({**fila,
                               "unit_price": round(unit_price, 2),
                               "amount": round(amount, 2)})
        resultado.categories[fila["category"]] = \
            resultado.categories.get(fila["category"], 0.0) + amount
    resultado.categories = {
        categoria: round(resultado.categories[categoria], 2)
        for categoria in CATEGORIAS
        if categoria in resultado.categories
    }
    resultado.rows.sort(key=lambda row: (row["category"], row["code"]))
    return resultado


def attach_costs(data: Any, variants: Sequence[Any], ruleset: Any,
                 calidad: str = CALIDAD_DEFECTO) -> None:
    """Adjunta ``VariantCost`` a cada variante (en ``variant.cost``).

    Recalcula SIEMPRE: llamarlo con otra calidad es la forma de que el
    presupuesto «viva» sin regenerar el trazado.
    """
    for variant in variants:
        variant.cost = estimate_variant_cost(data, variant, ruleset,
                                             calidad)


# -- texto para la GUI ----------------------------------------------------------------

def fmt_cup(value: float) -> str:
    """Miles con espacio y sin decimales: 1582457.4 → «1 582 457»."""
    return f"{value:,.0f}".replace(",", "@").replace(".", ",").replace("@", " ")


def desglose_texto(cost: VariantCost, top: int = 3) -> str:
    """«Estructura 43% · Muros 21% · Carpintería 12%» (mayores primero)."""
    if cost.direct <= 0 or not cost.categories:
        return ""
    pares = sorted(cost.categories.items(), key=lambda kv: -kv[1])[:max(1, top)]
    return " · ".join(
        f"{categoria} {importe / cost.direct * 100.0:.0f}%"
        for categoria, importe in pares)


# -- Comparación de variantes (v3.29.0) --------------------------------------

# Columnas de la matriz de comparación (orden fijo para GUI/CSV/texto).
COLUMNAS_COMPARACION: Tuple[str, ...] = (
    "#", "Variante", "Esquema", "Cabe en lote", "Puntos",
    "Área m2", "Coste", "Coste/m2", "Avisos",
)


def _area_de_variante(variant: Any) -> float:
    """Área construida de la variante: del coste vivo si ya está
    adjunto (consistente con el presupuesto) o sumando los locales
    trazados de todos los niveles (misma cuenta que ``total_area_m2``).
    """
    coste = getattr(variant, "cost", None)
    if coste is not None and getattr(coste, "area_m2", 0.0) > 0:
        return float(coste.area_m2)
    total = 0.0
    for layout in getattr(variant, "layouts", []) or []:
        try:
            total += layout.total_area_m2()
        except Exception:  # noqa: BLE001 - un nivel roto no tumba la tabla
            continue
    return total


def _celda(variant: Any, coste: Optional[VariantCost],
           selector: str) -> str:
    if selector == "cabe":
        return "Sí" if getattr(variant, "fits_lot", True) else "No"
    if selector == "puntos":
        return f"{getattr(variant, 'score', 0.0):.0f}"
    if selector == "area":
        area = _area_de_variante(variant)
        return f"{area:,.0f}".replace(",", " ") if area > 0 else "—"
    if selector == "coste":
        return fmt_cup(coste.total) if coste is not None else "—"
    if selector == "coste_m2":
        if coste is not None and coste.cost_m2 > 0:
            return fmt_cup(coste.cost_m2)
        return "—"
    if selector == "avisos":
        propios = len(getattr(variant, "advisories", []) or [])
        del_coste = len(getattr(coste, "avisos", []) or []) \
            if coste is not None else 0
        return str(propios + del_coste) \
            if (propios + del_coste) else "0"
    return ""


def tabla_comparacion_variantes(
        variantes: Sequence[Any]) -> Dict[str, Any]:
    """Matriz N variantes x métricas para la GUI, el CSV y el texto.

    Devuelve un dict con ``columnas``, ``filas`` (todas cadenas, listas
    alineadas con las columnas), ``orden`` (índices por puntos, mejor
    primero) y ``mejores`` con las etiquetas de las líderes: la
    variante MÁS PUNTUADA y la de MENOR coste por m2 con coste vivo
    (honradez: si no hay coste adjunto, el comparador lo dice).
    """
    filas: List[List[str]] = []
    entradas: List[Tuple[int, Any, Optional[VariantCost], float]] = []
    for indice, variant in enumerate(variantes, start=1):
        coste = getattr(variant, "cost", None)
        area = _area_de_variante(variant)
        entradas.append((indice, variant, coste, area))
        filas.append([
            str(indice),
            str(getattr(variant, "title", f"Variante {indice}")),
            str(getattr(variant, "scheme", "")),
            _celda(variant, coste, "cabe"),
            _celda(variant, coste, "puntos"),
            _celda(variant, coste, "area"),
            _celda(variant, coste, "coste"),
            _celda(variant, coste, "coste_m2"),
            _celda(variant, coste, "avisos"),
        ])
    con_coste = [(v, c) for _i, v, c, _a in entradas
                 if c is not None and c.cost_m2 > 0]
    mejor_puntos = max(
        entradas, key=lambda e: float(getattr(e[1], "score", 0.0)),
        default=None)
    mejor_coste = min(con_coste, key=lambda vc: vc[1].cost_m2,
                      default=None)
    orden = [e[0] for e in sorted(
        entradas, key=lambda e: (
            -float(getattr(e[1], "score", 0.0)),
            0 if getattr(e[1], "fits_lot", True) else 1,
            e[0]))]
    return {
        "columnas": list(COLUMNAS_COMPARACION),
        "filas": filas,
        "orden": orden,
        "mejores": {
            "puntos": (str(getattr(mejor_puntos[1], "title",
                                   f"Variante {mejor_puntos[0]}"))
                       if mejor_puntos else ""),
            "coste_m2": (str(getattr(mejor_coste[0], "title",
                                     ""))
                         if mejor_coste else ""),
            "con_coste": bool(con_coste),
        },
    }


def texto_comparacion_variantes(variantes: Sequence[Any]) -> str:
    """La matriz en texto cp1252 (consola y cuadros, sin flechas)."""
    tabla = tabla_comparacion_variantes(variantes)
    if not tabla["filas"]:
        return ("COMPARACIÓN DE VARIANTES\n"
                "(no hay variantes: genera primero las variantes de "
                "planta)")
    columnas = tabla["columnas"]
    lineas = ["COMPARACIÓN DE VARIANTES DE PLANTA"]
    anchos = [len(col) for col in columnas]
    for fila in tabla["filas"]:
        for indice, celda in enumerate(fila):
            anchos[indice] = max(anchos[indice], len(celda))
    linea = "  ".join(col.ljust(anchos[i])
                      for i, col in enumerate(columnas))
    lineas.append(linea)
    lineas.append("  ".join("-" * a for a in anchos))
    for fila in tabla["filas"]:
        lineas.append("  ".join(celda.ljust(anchos[i])
                                for i, celda in enumerate(fila)))
    lineas.append("")
    if tabla["mejores"]["puntos"]:
        lineas.append("Mejor puntuación: "
                      + tabla["mejores"]["puntos"])
    if tabla["mejores"]["con_coste"]:
        lineas.append("Menor coste por m2 (calidad elegida): "
                      + tabla["mejores"]["coste_m2"])
    else:
        lineas.append("(sin coste adjunto: el coste se calcula al "
                      "generar o cambiar la calidad de acabados)")
    lineas.append("El «coste» es la estimación PRECONS de obra directa "
                  "(RoPres 3.30): no incluye indirectos ni beneficio.")
    return "\n".join(lineas)


def csv_comparacion_variantes(variantes: Sequence[Any]) -> str:
    """La matriz como CSV con «;» (Excel España) y líneas \\r\\n."""
    import io as _io
    import csv as _csv
    tabla = tabla_comparacion_variantes(variantes)
    buffer = _io.StringIO()
    escritor = _csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(tabla["columnas"])
    escritor.writerows(tabla["filas"])
    return buffer.getvalue()


__all__ = [
    "CALIDADES", "CALIDAD_DEFECTO", "FACTOR_CALIDAD", "CATEGORIAS",
    "CATEGORIAS_DE_OBRA_GRUESA", "CATEGORIAS_SIN_CALIDAD",
    "EQUIPOS_POR_USO", "RENGLONES", "VariantCost",
    "variant_takeoff", "estimate_variant_cost", "attach_costs",
    "fmt_cup", "desglose_texto",
    "COLUMNAS_COMPARACION", "tabla_comparacion_variantes",
    "texto_comparacion_variantes", "csv_comparacion_variantes",
]
