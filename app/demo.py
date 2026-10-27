"""Demo project: deterministic end-to-end verification (spec section 98).

Builds a small dwelling with exact numbers so tests can assert the full
chain: SPACES → WALLS → OPENINGS → QTO → BUDGET → EXPORTS.
All geometry in meters, model coordinates.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from app.lifecycle import get_logger
from services.architecture_service import ArchitectureService
from services.budget_service import BudgetService, PricingService
from services.context import ApplicationContext, ProjectContext
from services.installations_service import InstallationsService
from services.quantity_service import QuantityService
from services.analysis_service import RuleService, SpatialService

logger = get_logger("arqgen.demo")

# Deterministic plan (meters): outer rectangle 10.0 x 8.0
# Left column (x 0..6):  Cocina (y 0..2, 12 m2) + Sala (y 2..8, 36 m2)
# Right column (x 6..10): Bano (y 0..2, 8 m2) + Dormitorio (y 2..8, 24 m2)
POINTS: Dict[str, Tuple[float, float]] = {
    "P1": (0.0, 0.0), "P2": (10.0, 0.0), "P3": (10.0, 8.0), "P4": (0.0, 8.0),
    "P5": (6.0, 0.0), "P6": (6.0, 2.0), "P7": (6.0, 8.0),
    "P8": (0.0, 2.0), "P9": (10.0, 2.0),
}

WALLS: List[Tuple[str, Tuple[float, float], Tuple[float, float], float]] = [
    ("W-EXT-1", POINTS["P1"], POINTS["P2"], 0.20),   # south exterior, 10 m
    ("W-EXT-2", POINTS["P2"], POINTS["P3"], 0.20),   # east exterior, 8 m
    ("W-EXT-3", POINTS["P3"], POINTS["P4"], 0.20),   # north exterior, 10 m
    ("W-EXT-4", POINTS["P4"], POINTS["P1"], 0.20),   # west exterior, 8 m
    ("W-INT-1", POINTS["P5"], POINTS["P7"], 0.15),   # vertical partition x=6, 8 m
    ("W-INT-2", POINTS["P8"], POINTS["P6"], 0.15),   # left horizontal partition y=2, 6 m
    ("W-INT-3", POINTS["P6"], POINTS["P9"], 0.15),   # right horizontal partition y=2, 4 m
]

DOORS: List[Tuple[str, float, float, float]] = [
    ("W-EXT-1", 2.0, 0.95, 2.10),  # entrance (south, Sala side)
    ("W-INT-2", 2.5, 0.85, 2.10),  # Sala ↔ Cocina
    ("W-INT-1", 5.0, 0.85, 2.10),  # Sala ↔ Dormitorio
    ("W-INT-3", 1.0, 0.75, 2.10),  # Dormitorio ↔ Bano
]

WINDOWS: List[Tuple[str, float, float, float, float]] = [
    ("W-EXT-4", 3.0, 1.20, 1.20, 1.0),  # Sala west
    ("W-EXT-2", 4.0, 1.20, 1.20, 1.0),  # Dormitorio east
    ("W-EXT-1", 3.0, 1.00, 1.00, 1.0),  # Cocina south
]

SPACES: List[Tuple[str, str, List[Tuple[float, float]]]] = [
    ("Cocina", "KITCHEN", [POINTS["P1"], POINTS["P5"], POINTS["P6"], POINTS["P8"]]),
    ("Sala", "LIVING_ROOM", [POINTS["P8"], POINTS["P6"], POINTS["P7"], POINTS["P4"]]),
    ("Bano", "BATHROOM", [POINTS["P5"], POINTS["P2"], POINTS["P9"], POINTS["P6"]]),
    ("Dormitorio", "BEDROOM", [POINTS["P6"], POINTS["P9"], POINTS["P3"], POINTS["P7"]]),
]

RESOURCES: List[Tuple[str, str, str, str, float]] = [
    ("BLOQUE-20", "Bloque de hormigón 20x20x40 cm", "MATERIAL", "und", 32.50),
    ("CEMENTO", "Cemento Portland P-35", "MATERIAL", "saco", 185.00),
    ("ARENA", "Arena de río, lavada", "MATERIAL", "m3", 95.00),
    ("MO-ALBANIL", "Mano de obra albañil", "LABOR", "jornada", 450.00),
    ("MO-AYUDANTE", "Mano de obra ayudante", "LABOR", "jornada", 300.00),
    ("MO-CARPINTERO", "Mano de obra carpintero", "LABOR", "jornada", 480.00),
    ("PUERTA-MADERA", "Puerta interior de madera 0.85x2.10", "MATERIAL", "und", 3200.00),
    ("VENTANA-ALUMINIO", "Ventana de aluminio 1.20x1.20", "MATERIAL", "und", 5400.00),
    ("CABLE-25MM", "Cable Cu 2,5 mm2 750V", "MATERIAL", "m", 85.00),
    ("TUBO-PVC-25", "Tubo conduit PVC 25 mm", "MATERIAL", "m", 28.00),
    ("TUBO-PVC-19", "Tubería PVC agua 19 mm", "MATERIAL", "m", 45.00),
    ("TUBO-PVC-50", "Tubo PVC sanitario 50 mm", "MATERIAL", "m", 95.00),
    ("TUBO-PVC-110", "Tubo PVC sanitario 110 mm", "MATERIAL", "m", 220.00),
    ("TOMA-CORRIENTE", "Tomacorriente doble 220V", "MATERIAL", "und", 180.00),
    ("LUMINARIA-LED", "Luminaria LED 18 W", "MATERIAL", "und", 320.00),
    ("TABLERO-PANEL", "Tablero eléctrico 12 circuitos", "MATERIAL", "und", 4500.00),
    ("APARATO-SANITARIO", "Aparato sanitario con grifería", "MATERIAL", "und", 2500.00),
    ("LLAVE-PASO", "Llave de paso 1/2 pulgada", "MATERIAL", "und", 150.00),
    ("SUMIDERO-CUB", "Sumidero de cubierta PVC 75 mm", "MATERIAL", "und", 1200.00),
    ("CANALON-GALV", "Canalón galvanizado 150x75 mm", "MATERIAL", "m", 380.00),
    ("TUBO-PVC-75", "Tubo PVC pluvial 75 mm", "MATERIAL", "m", 145.00),
    ("TANQUE-2000", "Tanque de retención 2000 L", "MATERIAL", "und", 21000.00),
    ("TUBERIA-GAS", "Tubería de gas cobre 15 mm", "MATERIAL", "m", 120.00),
    ("REGULADOR-GAS", "Regulador de gas de media presión", "MATERIAL", "und", 4200.00),
    ("LLAVE-GAS", "Llave de paso de gas 1/2 pulgada", "MATERIAL", "und", 950.00),
    ("CALEFON-GAS", "Calefón de gas 12 kW", "MATERIAL", "und", 18500.00),
    ("ENCIMERA-GAS", "Encimera de gas 4 quemadores", "MATERIAL", "und", 9800.00),
    ("TUBO-TELECOM", "Tubo PVC telecom 25 mm", "MATERIAL", "m", 52.00),
    ("CABLE-CAT6", "Cable Cat6 UTP", "MATERIAL", "m", 210.00),
    ("ROS-RJ45", "Roseta RJ45 Cat6", "MATERIAL", "und", 850.00),
    ("RACK-PARED", "Rack de pared 12U con accesorios", "MATERIAL", "und", 18500.00),
    ("PATCH-24", "Patch panel 24 puertos Cat6", "MATERIAL", "und", 7800.00),
    ("SWITCH-24", "Switch 24 puertos gigabit", "MATERIAL", "und", 24500.00),
    ("FIBRA-OM3", "Fibra óptica OM3 duplex", "MATERIAL", "m", 680.00),
    ("SPLIT-12000", "Split pared 12000 BTU", "MATERIAL", "und", 38000.00),
    ("DUCTO-GALV", "Ducto galvanizado 200 mm", "MATERIAL", "m", 420.00),
    ("MO-ELECTRICISTA", "Mano de obra electricista", "LABOR", "jornada", 600.00),
    ("MO-PLOMERO", "Mano de obra plomero", "LABOR", "jornada", 550.00),
    ("MO-HVAC", "Mano de obra mecánico HVAC", "LABOR", "jornada", 650.00),
    # Estructura (spec 33-34)
    ("PIEDRA", "Picado 1-2 pulgadas", "MATERIAL", "m3", 120.00),
    ("ACERO-CA", "Acero corrugado CA-50", "MATERIAL", "kg", 28.00),
    ("ENCOFRADO", "Encofrado de madera", "MATERIAL", "m2", 85.00),
    ("MO-HORMIGONERO", "Mano de obra hormigonero", "LABOR", "jornada", 500.00),
    ("HORMIGONERA", "Hormigonera 9 pies3", "EQUIPMENT", "turno", 900.00),
    # Seguridad (spec 37-49)
    ("CAMARA-IP", "Cámara IP domo 1080P PoE", "MATERIAL", "und", 14500.00),
    ("NVR-16CH", "NVR 16 canales", "MATERIAL", "und", 46000.00),
    ("POE-SWITCH", "Switch PoE 8 puertos", "MATERIAL", "und", 21000.00),
    ("DETECTOR-HUMO", "Detector óptico de humo", "MATERIAL", "und", 1850.00),
    ("PULSADOR-ALARMA", "Pulsador manual de alarma", "MATERIAL", "und", 1200.00),
    ("SIRENA-INT", "Sirena interior 105 dB", "MATERIAL", "und", 3600.00),
    ("PIR-CABLE", "Detector volumétrico PIR", "MATERIAL", "und", 2400.00),
    ("CONTACTO-MAG", "Contacto magnético", "MATERIAL", "und", 650.00),
    ("LECTOR-RFID", "Lector RFID para control de acceso", "MATERIAL", "und", 5800.00),
    ("CERRADURA-MAG", "Cerradura electromagnética fail-safe", "MATERIAL", "und", 11500.00),
    ("SENSOR-VALLA", "Sensor de valla perimetral", "MATERIAL", "und", 4300.00),
    ("CABLE-SEC", "Cable de seguridad 2x18 AWG", "MATERIAL", "m", 95.00),
    ("MO-SEGURIDAD", "Mano de obra técnico de seguridad", "LABOR", "jornada", 700.00),
]


def build_demo(application: ApplicationContext, out_path: str) -> ProjectContext:
    """Creates the demo project file with the full integrated chain."""
    if os.path.exists(out_path):
        os.remove(out_path)
    context = application.create_project(
        out_path, name="Proyecto Demo Residencial", client="Cliente Demo",
        address="Calle Demo 101", description="Proyecto de demostración ARQ GEN",
        ruleset_code="international_v1", currency="CUP")
    context.user = "demo"
    arch = ArchitectureService(context)

    level = arch.create_level(name="Nivel 1", elevation_m=0.0, height_m=3.0)
    zone_int = arch.create_zone(name="Zona Privada", kind="PRIVATE")
    zone_serv = arch.create_zone(name="Zona Servicio", kind="SERVICE")

    for name, space_type, boundary in SPACES:
        space = arch.create_space("Nivel 1", name, space_type, boundary)
        if space.name in ("Dormitorio",):
            arch.set_space_zone(space.code, zone_int.id)
        if space.name in ("Cocina", "Bano"):
            arch.set_space_zone(space.code, zone_serv.id)
    wall_by_code: Dict[str, object] = {}
    for label, start, end, thickness in WALLS:
        wall = arch.create_wall("Nivel 1", start, end, thickness_m=thickness)
        wall_by_code[label] = wall

    code_map = {label: wall.code for label, wall in wall_by_code.items()}

    for wall_label, offset, width, height in DOORS:
        arch.create_opening("DOOR", code_map[wall_label], width, height, offset_m=offset)
    for wall_label, offset, width, height, sill in WINDOWS:
        arch.create_opening("WINDOW", code_map[wall_label], width, height,
                            offset_m=offset, sill_height_m=sill)

    # Relations + rules
    spatial = SpatialService(context)
    spatial.recompute_adjacencies()
    RuleService(context).load_ruleset_from_resources("international_v1")

    # QTO + pricing + budget
    quantity = QuantityService(context)
    quantity.install_default_formulas()
    quantity.compute_all()

    # Installations layer (spec 24-29): deterministic networks wired to the
    # same walls/spaces. All coordinates fixed → deterministic outputs.
    space_by_name = {}
    for space in context.architecture.list("SPACE", context.project.id):
        space_by_name[space.name] = space
    level = context.architecture.list("LEVEL", context.project.id)[0]

    installations = InstallationsService(context)

    # -- Electrical POWER network -------------------------------------------
    elec = installations.create_network("Fuerza e Iluminación", "POWER",
                                        description="Red eléctrica demo")
    panel = installations.add_node(elec.code, "PANEL", 1.0, 1.0, name="Tablero",
                                   level_ref=level.code,
                                   attrs={"voltage": 220, "phases": 1,
                                          "main_breaker_a": 63})
    c1 = installations.add_node(elec.code, "PROTECTION", 1.0, 0.5, name="C1 Tomas",
                                attrs={"rating_a": 16, "kind_circuit": "POWER",
                                       "voltage": 220, "phase": 1})
    c2 = installations.add_node(elec.code, "PROTECTION", 1.6, 1.4, name="C2 Luces",
                                attrs={"rating_a": 10, "kind_circuit": "LIGHTING",
                                       "voltage": 220, "phase": 1})
    c3 = installations.add_node(elec.code, "PROTECTION", 1.5, 0.5, name="C3 Clima",
                                attrs={"rating_a": 25, "kind_circuit": "CLIMATE",
                                       "voltage": 220, "phase": 1})
    outlets = [
        installations.add_node(elec.code, "OUTLET", 3.0, 4.0, name="Tomas Sala",
                               space_ref=space_by_name["Sala"].code,
                               attrs={"power_w": 600}),
        installations.add_node(elec.code, "OUTLET", 8.0, 5.0, name="Tomas Dormitorio",
                               space_ref=space_by_name["Dormitorio"].code,
                               attrs={"power_w": 500}),
        installations.add_node(elec.code, "OUTLET", 3.0, 1.0, name="Tomas Cocina",
                               space_ref=space_by_name["Cocina"].code,
                               attrs={"power_w": 1500}),
    ]
    luminaires = [
        installations.add_node(elec.code, "LUMINAIRE", 3.0, 5.0, name="Luz Sala",
                               space_ref=space_by_name["Sala"].code,
                               attrs={"power_w": 72}),
        installations.add_node(elec.code, "LUMINAIRE", 8.0, 5.5, name="Luz Dormitorio",
                               space_ref=space_by_name["Dormitorio"].code,
                               attrs={"power_w": 48}),
        installations.add_node(elec.code, "LUMINAIRE", 3.0, 1.5, name="Luz Cocina",
                               space_ref=space_by_name["Cocina"].code,
                               attrs={"power_w": 36}),
        installations.add_node(elec.code, "LUMINAIRE", 7.0, 1.0, name="Luz Bano",
                               space_ref=space_by_name["Bano"].code,
                               attrs={"power_w": 24}),
    ]
    installations.connect(elec.code, panel.code, c1.code, kind="CONDUIT",
                          attrs={"conductors": 3, "spare_pct": 10})
    installations.connect(elec.code, panel.code, c2.code, kind="CONDUIT",
                          attrs={"conductors": 3, "spare_pct": 10})
    installations.connect(elec.code, panel.code, c3.code, kind="CONDUIT",
                          attrs={"conductors": 3, "spare_pct": 10})
    for outlet in outlets:
        installations.connect(elec.code, c1.code, outlet.code, kind="CONDUIT",
                              attrs={"conductors": 3, "spare_pct": 10})
    for luminaire in luminaires:
        installations.connect(elec.code, c2.code, luminaire.code, kind="CONDUIT",
                              attrs={"conductors": 3, "spare_pct": 10})
    installations.circuit_check(c1.code)
    installations.circuit_check(c2.code)
    installations.panel_summary(panel.code)

    # -- Cold water network ---------------------------------------------------
    cold = installations.create_network("Agua Fría Sanitaria", "COLD_WATER",
                                        description="Red sanitaria demo")
    meter = installations.add_node(cold.code, "METER", 0.5, 7.5, name="Contador",
                                   level_ref=level.code,
                                   attrs={"pressure_m": 15.0, "elevation_m": 0.0})
    fixtures_cold = [
        installations.add_node(cold.code, "FIXTURE", 7.5, 1.0, name="Inodoro",
                               space_ref=space_by_name["Bano"].code,
                               attrs={"fixture_kind": "WC", "fixture_units": 3.0}),
        installations.add_node(cold.code, "FIXTURE", 8.0, 0.5, name="Ducha",
                               space_ref=space_by_name["Bano"].code,
                               attrs={"fixture_kind": "SHOWER", "fixture_units": 2.0}),
        installations.add_node(cold.code, "FIXTURE", 8.5, 1.0, name="Lavabo",
                               space_ref=space_by_name["Bano"].code,
                               attrs={"fixture_kind": "LAVATORY", "fixture_units": 1.0}),
        installations.add_node(cold.code, "FIXTURE", 3.0, 0.5, name="Fregadero",
                               space_ref=space_by_name["Cocina"].code,
                               attrs={"fixture_kind": "KITCHEN_SINK", "fixture_units": 2.0}),
        installations.add_node(cold.code, "FIXTURE", 0.5, 2.5, name="Lavadero",
                               space_ref=space_by_name["Sala"].code,
                               attrs={"fixture_kind": "LAUNDRY", "fixture_units": 3.0}),
    ]
    for fixture in fixtures_cold:
        installations.connect(cold.code, meter.code, fixture.code, kind="PIPE",
                              material="PVC", attrs={"spare_pct": 5})
    installations.size_sanitary(cold.code)

    # -- Sanitary drainage network ---------------------------------------------
    drain = installations.create_network("Desagüe Sanitario", "SANITARY_DRAINAGE",
                                         description="Gravedad demo")
    wc = installations.add_node(drain.code, "FIXTURE", 7.5, 1.0, name="Inodoro desagüe",
                                attrs={"fixture_kind": "WC", "fixture_units": 3.0})
    sink = installations.add_node(drain.code, "FIXTURE", 3.0, 0.5, name="Fregadero desagüe",
                                  attrs={"fixture_kind": "KITCHEN_SINK", "fixture_units": 2.0})
    junction = installations.add_node(drain.code, "JUNCTION", 5.55, 0.5, name="Bajada")
    outfall = installations.add_node(drain.code, "OUTFALL", 10.5, 0.5, name="Alcantarillado")
    installations.connect(drain.code, wc.code, junction.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"spare_pct": 5})
    installations.connect(drain.code, sink.code, junction.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"spare_pct": 5})
    installations.connect(drain.code, junction.code, outfall.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"spare_pct": 5})
    installations.size_sanitary(drain.code)

    # -- HVAC: thermal loads + splits (as climate loads fed by circuit C3
    #    of the electrical network, carrying their BTU metadata) + exhaust ducts --
    split_positions = {"Sala": (5.0, 5.0), "Dormitorio": (8.0, 4.0),
                       "Cocina": (2.0, 1.0), "Bano": (8.0, 1.5)}
    for space_name in ("Sala", "Dormitorio", "Cocina", "Bano"):
        load = installations.space_thermal_load(space_by_name[space_name].code)
        selection = load["equipment"]
        x, y = split_positions[space_name]
        split = installations.add_node(elec.code, "SPLIT", x, y,
                                       name=f"Split {space_name}",
                                       space_ref=space_by_name[space_name].code,
                                       attrs={"capacity_btu": selection["unit_btu_h"],
                                              "capacity_w": selection["unit_btu_h"] / 3.4121,
                                              "air_flow_m3h": load["airflow_m3h"],
                                              "power_w": 1100})
        installations.connect(elec.code, c3.code, split.code, kind="CONDUIT",
                              attrs={"conductors": 3, "spare_pct": 10})
    exhaust = installations.create_network("Extracción Baño", "EXHAUST",
                                           description="Ventilación demo")
    grille = installations.add_node(exhaust.code, "GRILLE", 8.5, 1.0, name="Rejilla bano",
                                    space_ref=space_by_name["Bano"].code,
                                    attrs={"air_flow_m3h": 60.0})
    fan = installations.add_node(exhaust.code, "FAN", 9.5, 2.45, name="Extractor")
    installations.connect(exhaust.code, grille.code, fan.code, kind="DUCT",
                          attrs={"duct_kind": "MAIN", "shape": "ROUND"})
    installations.size_hvac_network(exhaust.code)

    # -- Stormwater network (spec 30): captación, canalón, bajante,
    #    detención y evacuación. Lluvia de diseño 100 mm/h, C=0,90.
    storm = installations.create_network("Pluvial Cubierta", "STORMWATER",
                                         description="Pluviales demo")
    rd1 = installations.add_node(storm.code, "ROOF_DRAIN", 3.0, 5.0, name="Sumidero Sala",
                                 elevation_m=3.0,
                                 attrs={"area_m2": 45.0, "surface": "ROOF",
                                        "intensity_mmh": 100.0})
    rd2 = installations.add_node(storm.code, "ROOF_DRAIN", 8.0, 4.0, name="Sumidero Dormitorio",
                                 elevation_m=3.0,
                                 attrs={"area_m2": 35.0, "surface": "ROOF",
                                        "intensity_mmh": 100.0})
    gutter = installations.add_node(storm.code, "GUTTER", 5.0, 8.45, name="Canalón norte",
                                    elevation_m=2.9,
                                    attrs={"length_m": 10.0, "width_mm": 150.0,
                                           "depth_mm": 75.0, "slope_pct": 0.5})
    tank = installations.add_node(storm.code, "TANK", 11.2, 6.0, name="Tanque retención",
                                  elevation_m=0.0,
                                  attrs={"detention": 1, "retention_min": 15.0,
                                         "volume_l": 2000.0})
    storm_out = installations.add_node(storm.code, "OUTFALL", 11.8, 6.0,
                                       name="Evacuación exterior", elevation_m=-0.5)
    installations.connect(storm.code, rd1.code, gutter.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"spare_pct": 5})
    installations.connect(storm.code, rd2.code, gutter.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"spare_pct": 5})
    installations.connect(storm.code, gutter.code, tank.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"vertical": 1, "spare_pct": 5})
    installations.connect(storm.code, tank.code, storm_out.code, kind="DRAIN_PIPE",
                          material="PVC", attrs={"spare_pct": 5})
    installations.size_stormwater(storm.code)

    # -- Gas network (spec 31): regulación, válvulas por aparato y
    #    ventilación declarada. Los nodos se dibujan en la banda de
    #    distribución norte (esquema de plenum), alejados de la
    #    canalización eléctrica (separación ≥ 10 cm del spec 31).
    gas = installations.create_network("Gas Doméstico", "GAS",
                                       description="Gas demo")
    g_source = installations.add_node(gas.code, "SOURCE", 0.3, 8.4,
                                      name="Regulación de calle")
    g_meter = installations.add_node(gas.code, "METER", 0.9, 8.45, name="Contador gas")
    g_reg = installations.add_node(gas.code, "REGULATOR", 1.5, 8.45,
                                   name="Regulador vivienda")
    g_v1 = installations.add_node(gas.code, "VALVE", 2.5, 8.45, name="Llave cocina")
    g_ap1 = installations.add_node(gas.code, "APPLIANCE", 4.0, 8.45, name="Encimera cocina",
                                   space_ref=space_by_name["Cocina"].code,
                                   attrs={"power_kw": 3.5, "vent_area_m2": 0.25})
    g_v2 = installations.add_node(gas.code, "VALVE", 10.45, 7.3, name="Llave baño")
    g_ap2 = installations.add_node(gas.code, "APPLIANCE", 10.5, 7.0, name="Calefón baño",
                                   space_ref=space_by_name["Bano"].code,
                                   attrs={"power_kw": 12.0, "vent_area_m2": 0.20})
    installations.connect(gas.code, g_source.code, g_meter.code, kind="PIPE",
                          material="COPPER")
    installations.connect(gas.code, g_meter.code, g_reg.code, kind="PIPE",
                          material="COPPER")
    installations.connect(gas.code, g_reg.code, g_v1.code, kind="PIPE",
                          material="COPPER")
    installations.connect(gas.code, g_v1.code, g_ap1.code, kind="PIPE",
                          material="COPPER")
    installations.connect(gas.code, g_reg.code, g_v2.code, kind="PIPE",
                          material="COPPER")
    installations.connect(gas.code, g_v2.code, g_ap2.code, kind="PIPE",
                          material="COPPER")
    installations.size_gas(gas.code)
    gas_report = installations.validate_gas(gas.code)
    if gas_report["status"] == "INVALID":
        raise RuntimeError(f"Demo gas inválida: {gas_report['errors']}")

    # -- Telecom network (spec 32): rack, patch panel, switch, rosetas,
    #    canalización con recuento de cables y enlace de fibra (uplink).
    telecom = installations.create_network("Telecomunicaciones", "TELECOM",
                                           description="Voz y datos demo")
    rack = installations.add_node(telecom.code, "RACK", 9.0, 7.0, name="Rack pared",
                                  attrs={"u_capacity": 12.0})
    patch = installations.add_node(telecom.code, "PATCH_PANEL", 9.4, 6.5,
                                   name="Patch panel", attrs={"ports": 24, "u_size": 1.0})
    switch = installations.add_node(telecom.code, "TELECOM_SWITCH", 9.1, 6.5,
                                    name="Switch", attrs={"ports": 24, "u_size": 1.0})
    tel_outlets = [
        installations.add_node(telecom.code, "TELECOM_OUTLET", 4.0, 4.6, name="Roseta Sala",
                               space_ref=space_by_name["Sala"].code),
        installations.add_node(telecom.code, "TELECOM_OUTLET", 4.5, 1.5, name="Roseta Cocina",
                               space_ref=space_by_name["Cocina"].code),
        installations.add_node(telecom.code, "TELECOM_OUTLET", 9.0, 4.5,
                               name="Roseta Dormitorio",
                               space_ref=space_by_name["Dormitorio"].code),
        installations.add_node(telecom.code, "TELECOM_OUTLET", 8.8, 1.55, name="Roseta Baño",
                               space_ref=space_by_name["Bano"].code),
    ]
    installations.connect(telecom.code, rack.code, patch.code, kind="CONDUIT",
                          attrs={"cable_type": "CAT6", "spare_pct": 10})
    installations.connect(telecom.code, patch.code, tel_outlets[0].code, kind="CONDUIT",
                          attrs={"cable_type": "CAT6", "spare_pct": 10})
    installations.connect(telecom.code, patch.code, tel_outlets[1].code, kind="CABLE",
                          attrs={"cable_type": "CAT6"})
    installations.connect(telecom.code, rack.code, switch.code, kind="FIBER",
                          attrs={"connectors": 2, "splices": 0})
    installations.connect(telecom.code, switch.code, tel_outlets[2].code, kind="CONDUIT",
                          attrs={"cable_type": "CAT6", "spare_pct": 10})
    installations.connect(telecom.code, switch.code, tel_outlets[3].code, kind="CONDUIT",
                          attrs={"cable_type": "CAT6", "spare_pct": 10})
    installations.size_telecom(telecom.code)

    # -- Structure (spec 33-34): portico de hormigón + cercha de acero,
    #    analizadas con el motor estructural y combinaciones ULS/SLS.
    from services.structure_service import StructureService
    structure = StructureService(context)
    h25 = structure.create_material("Hormigón H-25", "CONCRETE", fck_mpa=25.0)
    s275 = structure.create_material("Acero S275", "STEEL", fy_mpa=275.0)
    col_sec = structure.create_section("Pilar 30x30", "RECTANGLE", h_mm=300,
                                       b_mm=300)
    ipesec = structure.create_section("IPE-300", "I_PROFILE", h_mm=300,
                                      b_mm=150, tw_mm=7.1, tf_mm=10.7)
    structure.create_element("COLUMN", "Pilar A", material_ref=h25.code,
                             section_ref=col_sec.code, start=(0.0, 0.0),
                             end=(0.0, 0.0), z0=0.0, z1=3.0,
                             attrs={"axial_kn": 320.0})
    structure.create_element("COLUMN", "Pilar B", material_ref=h25.code,
                             section_ref=col_sec.code, start=(6.0, 0.0),
                             end=(6.0, 0.0), z0=0.0, z1=3.0,
                             attrs={"axial_kn": 280.0})
    beam = structure.create_element("BEAM", "Viga pórtico", material_ref=s275.code,
                                    section_ref=ipesec.code, start=(0.0, 0.0),
                                    end=(6.0, 0.0), load_udl_kn_m=12.0)
    structure.create_element(
        "TRUSS", "Cercha cubierta", material_ref=s275.code,
        section_ref=ipesec.code, start=(0.0, 8.0), end=(6.0, 8.0),
        attrs={
            "nodes": [{"id": "A", "x": 0.0, "y": 8.0},
                      {"id": "B", "x": 6.0, "y": 8.0},
                      {"id": "C", "x": 3.0, "y": 10.2}],
            "members": [{"id": "AB", "a": "A", "b": "B"},
                        {"id": "AC", "a": "A", "b": "C"},
                        {"id": "BC", "a": "B", "b": "C"}],
            "supports": [{"node": "A", "kind": "PIN"},
                         {"node": "B", "kind": "ROLLER", "axis": "y"}],
            "joint_loads": [{"node": "C", "fx": 0.0, "fy": -12.0}],
        })
    structure.ensure_default_combinations()
    for element_code in ("STR-ELEMENT-001", "STR-ELEMENT-002",
                         "STR-ELEMENT-003"):
        structure.analyze_element(element_code, combination_ref="ULS-1")
    structure.analyze_truss("STR-ELEMENT-004")

    # -- Security (spec 37-49): CCTV, detección de incendios, intrusión,
    #    control de acceso y perímetro sobre el modelo genérico de redes.
    from services.security_service import SecurityService
    security = SecurityService(context)

    cctv = security.create_network("CCTV Residencial", "CCTV",
                                   description="Videovigilancia demo")
    cam1 = security.add_device(cctv.code, "CAMERA", 0.5, 0.5, name="Camara Sala",
                               level_ref=level.code,
                               space_ref=space_by_name["Sala"].code,
                               attrs={"direction_deg": 45.0, "fov_deg": 90.0,
                                      "range_m": 12.0, "resolution": "1080P",
                                      "power_w": 6.5})
    cam2 = security.add_device(cctv.code, "PERIMETER_CAMERA", 10.5, 7.5,
                               name="Camara perimetro", level_ref=level.code,
                               attrs={"direction_deg": 200.0, "fov_deg": 70.0,
                                      "range_m": 15.0, "resolution": "4MP"})
    poe = security.add_device(cctv.code, "POE_SWITCH", 8.6, 7.0,
                              name="Switch PoE", attrs={"u_size": 1.0})
    nvr = security.add_device(cctv.code, "NVR", 8.6, 6.6, name="NVR 16",
                              attrs={"u_size": 2.0})
    # Convención de flujo del spec 24: del origen hacia los terminales
    # (el hub NVR→PoE→cámaras alimenta el trazado y el cableado).
    security.connect_devices(cctv.code, nvr.code, poe.code)
    security.connect_devices(cctv.code, poe.code, cam1.code)
    security.connect_devices(cctv.code, poe.code, cam2.code)
    security.cctv_coverage(cctv.code)
    security.cctv_network(cctv.code, retention_days=30)
    security.cctv_cabling(cctv.code)

    fire = security.create_network("Detección de Incendios", "FIRE_ALARM",
                                   description="Detección demo")
    fpanel = security.add_device(fire.code, "FIRE_PANEL", 1.2, 7.0,
                                 name="Central incendios", level_ref=level.code,
                                 attrs={"u_size": 3.0})
    for space_name, x, y in (("Sala", 5.0, 4.0), ("Cocina", 2.0, 1.0),
                             ("Dormitorio", 8.0, 4.0), ("Bano", 8.5, 1.0)):
        detector = security.add_device(
            fire.code, "SMOKE_DETECTOR", x, y, name=f"DH {space_name}",
            level_ref=level.code, space_ref=space_by_name[space_name].code)
        security.connect_devices(fire.code, fpanel.code, detector.code)
    callpoint = security.add_device(fire.code, "CALL_POINT", 5.4, 0.45,
                                    name="Pulsador salida")
    sounder = security.add_device(fire.code, "SOUNDER", 5.0, 6.0,
                                  name="Sirena incendio")
    security.connect_devices(fire.code, fpanel.code, callpoint.code)
    security.connect_devices(fire.code, fpanel.code, sounder.code)
    fire_report = security.fire_check(fire.code)
    if fire_report["status"] == "INVALID":
        raise RuntimeError(f"Demo fuego inválida: {fire_report['findings']}")
    security.fire_cause_effect(fire.code, "SMOKE_DETECTOR", {"night_mode": 1})

    intrusion = security.create_network("Intrusión", "INTRUSION",
                                        description="Alarma demo")
    ipanel = security.add_device(intrusion.code, "INTRUSION_PANEL", 1.2, 5.8,
                                 name="Central intrusión", level_ref=level.code)
    keypad = security.add_device(intrusion.code, "KEYPAD", 1.6, 6.3,
                                 name="Teclado")
    security.connect_devices(intrusion.code, ipanel.code, keypad.code)
    for i, (x, y, zone) in enumerate(((3.0, 5.0, "ZONA-1"), (5.5, 3.0, "ZONA-1"),
                                      (8.0, 5.5, "ZONA-1"))):
        pir = security.add_device(intrusion.code, "PIR", x, y, name=f"PIR {i + 1}",
                                  level_ref=level.code,
                                  space_ref=space_by_name["Sala"].code,
                                  attrs={"zone": zone})
        security.connect_devices(intrusion.code, ipanel.code, pir.code)
    pir_kitchen = security.add_device(intrusion.code, "PIR", 2.0, 1.5,
                                      name="PIR cocina",
                                      level_ref=level.code,
                                      space_ref=space_by_name["Cocina"].code,
                                      attrs={"zone": "ZONA-2"})
    security.connect_devices(intrusion.code, ipanel.code, pir_kitchen.code)
    for x, y, name in ((0.45, 1.0, "Contacto entrada"),
                       (5.6, 7.5, "Contacto cocina")):
        contact = security.add_device(intrusion.code, "MAGNETIC_CONTACT", x, y,
                                      name=name, level_ref=level.code,
                                      attrs={"zone": "ZONA-1", "external": 1})
        security.connect_devices(intrusion.code, ipanel.code, contact.code)
    siren = security.add_device(intrusion.code, "SIREN", 9.5, 7.5,
                                name="Sirena exterior")
    security.connect_devices(intrusion.code, ipanel.code, siren.code)
    intrusion_report = security.intrusion_check(intrusion.code)
    if intrusion_report["status"] == "INVALID":
        raise RuntimeError(f"Demo intrusión inválida: "
                           f"{intrusion_report['findings']}")

    access = security.create_network("Control de Acceso", "ACCESS_CONTROL",
                                     description="Acceso demo")
    controller = security.add_device(access.code, "ACCESS_CONTROLLER", 8.4, 7.0,
                                     name="Controlador", level_ref=level.code,
                                     attrs={"supply_a": 2.0})
    reader = security.add_device(access.code, "READER", 2.1, 0.45,
                                 name="Lector entrada",
                                 space_ref=space_by_name["Sala"].code)
    lock = security.add_device(access.code, "LOCK", 1.9, 0.45,
                               name="Cerradura entrada",
                               space_ref=space_by_name["Sala"].code,
                               attrs={"evacuation": 1, "unlock_s": 0.5})
    rex = security.add_device(access.code, "REX", 2.5, 0.45, name="REX salida")
    security.connect_devices(access.code, controller.code, reader.code)
    security.connect_devices(access.code, controller.code, lock.code)
    security.connect_devices(access.code, controller.code, rex.code)
    access_report = security.access_check(access.code)
    if access_report["status"] == "INVALID":
        raise RuntimeError(f"Demo acceso inválida: {access_report['findings']}")

    perimeter = security.create_network("Perímetro", "PERIMETER",
                                        description="Perímetro demo")
    fence = security.add_device(perimeter.code, "FENCE", 0.0, -1.0,
                                name="Valla norte", attrs={"length_m": 40.0})
    for i, x in enumerate((10.0, 25.0, 38.0)):
        sensor = security.add_device(perimeter.code, "FENCE_SENSOR", x, -1.0,
                                     name=f"Sensor valla {i + 1}")
        security.connect_devices(perimeter.code, fence.code, sensor.code)
    gate = security.add_device(perimeter.code, "GATE", 15.0, -1.0, name="Portón")
    security.connect_devices(perimeter.code, fence.code, gate.code)
    perimeter_cam = security.add_device(perimeter.code, "PERIMETER_CAMERA",
                                        15.0, -1.5, name="Camara portón",
                                        attrs={"direction_deg": 90.0,
                                               "fov_deg": 70.0,
                                               "range_m": 15.0,
                                               "resolution": "4MP"})
    security.connect_devices(perimeter.code, fence.code, perimeter_cam.code)
    access_point = security.add_device(perimeter.code, "READER", 15.4, -1.0,
                                       name="Acceso portón")
    security.connect_devices(perimeter.code, fence.code, access_point.code)
    perimeter_report = security.perimeter_check(perimeter.code)
    if not perimeter_report["report"]["ok"]:
        raise RuntimeError(f"Demo perímetro inválida: "
                           f"{perimeter_report['report']['findings']}")

    # Recompute QTO including everything, then budget.
    quantity.compute_all()

    pricing = PricingService(context)
    pricing.ensure_price_list("GENERAL", name="Lista general demo", currency="CUP")
    for code, name, type_, unit, price in RESOURCES:
        pricing.add_resource(code, name, type_, unit)
        pricing.set_price(code, price, "GENERAL", date_iso="2026-01-01")

    budget = BudgetService(context)
    budget.compute_budget("residential_full_v1", name="Presupuesto Demo")

    # -- Coordination (spec 35-36): detección de interferencias. La demo
    #    está coordinada: no debe haber choques duros (HARD).
    from services.coordination_service import CoordinationService
    coordination = CoordinationService(context)
    clash_report = coordination.run_detection()
    if clash_report["by_type"].get("HARD"):
        raise RuntimeError("Demo con interferencias HARD no coordinada")
    logger.info("Detección de interferencias: %s nuevas, por tipo %s",
                clash_report["created"], clash_report["by_type"])

    # -- PRECONS (spec 59-60): análisis versionado del proyecto.
    from services.precons_service import PreconsService
    precons = PreconsService(context)
    precons.load_ruleset("precons_cuba_v1")
    precons_report = precons.analyze_project()
    logger.info("Análisis PRECONS: total %s %s (%s partidas)",
                precons_report["total"], precons_report["currency"],
                len(precons_report["analyses"]))

    context.commit()
    logger.info("Demo construida: %s", out_path)
    return context


__all__ = ["build_demo", "SPACES", "WALLS", "DOORS", "WINDOWS", "RESOURCES"]
