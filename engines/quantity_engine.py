"""QTO Engine: Geometry → Measurement → Formula → Quantity → Waste → Final (spec 51)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.calculations.contracts import CalculationMode, CalculationResult, input_hash_of
from core.errors import CalculationError, GeometryError
from core.geometry import engine as ge
from core.rules.evaluator import Expression
from domain.installations import InstallNode, InstallSegment
from domain.model import Door, Level, Opening, Space, Wall, Window

# QTO-0001 example (spec 51): object WALL-001, formula Length × Height - Openings → m2
WALL_VARIABLES = ("length", "height", "thickness", "openings_area", "openings_count")


@dataclass
class FormulaSpec:
    code: str
    target_type: str
    expression: str
    unit: str
    description: str = ""
    waste_factor: float = 0.0
    version: str = "1.0"
    source: str = ""
    condition: str = ""   # when set, formula only applies if it evaluates truthy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code, "target_type": self.target_type,
            "expression": self.expression, "unit": self.unit,
            "description": self.description, "waste_factor": self.waste_factor,
            "version": self.version, "source": self.source,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FormulaSpec":
        return cls(
            code=data["code"], target_type=data["target_type"],
            expression=data["expression"], unit=data["unit"],
            description=data.get("description", ""),
            waste_factor=float(data.get("waste_factor", 0.0)),
            version=data.get("version", "1.0"), source=data.get("source", ""),
            condition=data.get("condition", ""),
        )


@dataclass
class ComputedQuantity:
    object_id: str
    object_type: str
    object_code: str
    formula: FormulaSpec
    variables: Dict[str, float]
    raw_quantity: float
    final_quantity: float
    unit: str


DEFAULT_FORMULAS: List[FormulaSpec] = [
    FormulaSpec("WALL_AREA_GROSS", "WALL", "length * height", "m2",
                "Área bruta del muro", 0.0),
    FormulaSpec("WALL_AREA_NET", "WALL", "length * height - openings_area", "m2",
                "Área neta descontando vanos", 0.0),
    FormulaSpec("WALL_VOLUME", "WALL", "(length * height - openings_area) * thickness", "m3",
                "Volumen de mampostería", 0.0),
    FormulaSpec("WALL_LENGTH", "WALL", "length", "m", "Longitud de eje", 0.0),
    FormulaSpec("OPENING_COUNT", "OPENING", "1", "und", "Unidades de vano", 0.0),
    FormulaSpec("OPENING_AREA", "OPENING", "width * height", "m2", "Área de vano", 0.0),
    FormulaSpec("SPACE_AREA", "SPACE", "area", "m2", "Área del local", 0.0),
    FormulaSpec("SPACE_PERIMETER", "SPACE", "perimeter", "m", "Perímetro del local", 0.0),
    FormulaSpec("SPACE_VOLUME", "SPACE", "area * height", "m3", "Volumen del local", 0.0),
]

# Fórmulas del módulo de instalaciones (spec 24, 51-52). Los flags numéricos
# (is_elec, is_water, ...) permiten filtrar por disciplina sin duplicar tablas.
INSTALL_FORMULAS: List[FormulaSpec] = [
    FormulaSpec("CONDUIT_LENGTH", "SEGMENT", "length * (1 + spare_pct / 100)", "m",
                "Canalización eléctrica con desperdicio", 0.0, condition="is_elec > 0"),
    FormulaSpec("CONDUCTOR_LENGTH", "SEGMENT", "length * conductors * (1 + spare_pct / 100)", "m",
                "Conductores por fase y tierra", 0.0, condition="conductors > 0"),
    FormulaSpec("PIPE_LENGTH", "SEGMENT", "length * (1 + spare_pct / 100)", "m",
                "Tubería a presión", 0.0, condition="is_water > 0"),
    FormulaSpec("DRAIN_LENGTH", "SEGMENT", "length * (1 + spare_pct / 100)", "m",
                "Tubería de desagüe", 0.0, condition="is_drain > 0"),
    FormulaSpec("DUCT_LENGTH", "SEGMENT", "length", "m",
                "Ductería de aire", 0.0, condition="is_duct > 0"),
    FormulaSpec("SEGMENT_LENGTH", "SEGMENT", "length", "m",
                "Longitud total de tramos", 0.0),
    FormulaSpec("DEVICE_COUNT", "NODE", "1", "und",
                "Unidades de equipo/terminal", 0.0, condition="is_device > 0"),
    FormulaSpec("TERMINAL_COUNT", "NODE", "1", "und",
                "Terminales instalados", 0.0, condition="is_terminal > 0"),
    FormulaSpec("PANEL_COUNT", "NODE", "1", "und",
                "Tableros eléctricos", 0.0, condition="is_panel > 0"),
    FormulaSpec("FIXTURE_COUNT", "NODE", "1", "und",
                "Aparatos sanitarios", 0.0, condition="fixture_units > 0"),
    FormulaSpec("COOLING_UNITS", "NODE", "1", "und",
                "Equipos de climatización", 0.0, condition="capacity_btu > 0"),
    FormulaSpec("COOLING_CAPACITY", "NODE", "capacity_w", "W",
                "Capacidad frigorífica instalada", 0.0, condition="capacity_w > 0"),
    FormulaSpec("INSTALLED_POWER", "NODE", "power_w", "W",
                "Potencia eléctrica instalada", 0.0, condition="power_w > 0"),
    # Pluviales (spec 30)
    FormulaSpec("ROOF_DRAIN_COUNT", "NODE", "1", "und",
                "Sumideros de cubierta", 0.0, condition="is_roof_drain > 0"),
    FormulaSpec("GUTTER_LENGTH", "NODE", "gutter_length", "m",
                "Canalón instalado", 0.0, condition="gutter_length > 0"),
    FormulaSpec("STORM_TANK_VOLUME", "NODE", "tank_volume", "m3",
                "Volumen de tanque de retención pluvial", 0.0,
                condition="is_detention > 0"),
    # Gas (spec 31)
    FormulaSpec("GAS_PIPE_LENGTH", "SEGMENT", "length * (1 + spare_pct / 100)", "m",
                "Tubería de gas", 0.0, condition="is_gas > 0"),
    FormulaSpec("GAS_APPLIANCE_COUNT", "NODE", "1", "und",
                "Aparatos de gas", 0.0, condition="is_gas_appliance > 0"),
    FormulaSpec("GAS_INSTALLED_POWER", "NODE", "gas_power_w", "W",
                "Potencia térmica de gas instalada", 0.0, condition="gas_power_w > 0"),
    # Telecomunicaciones (spec 32)
    FormulaSpec("TELECOM_CONDUIT_LENGTH", "SEGMENT", "length * (1 + spare_pct / 100)", "m",
                "Canalización de telecomunicaciones", 0.0,
                condition="is_telecom_cond > 0"),
    FormulaSpec("TELECOM_CABLE_LENGTH", "SEGMENT", "length * cables", "m",
                "Cable de cobre tendido", 0.0, condition="cables > 0"),
    FormulaSpec("FIBER_LENGTH", "SEGMENT", "length", "m",
                "Fibra óptica tendida", 0.0, condition="is_fiber > 0"),
    FormulaSpec("TELECOM_OUTLET_COUNT", "NODE", "1", "und",
                "Rosetas de telecomunicaciones", 0.0, condition="is_telecom_outlet > 0"),
    FormulaSpec("RACK_COUNT", "NODE", "1", "und",
                "Racks de telecomunicaciones", 0.0, condition="is_rack > 0"),
    FormulaSpec("RACK_UNITS_USED", "NODE", "rack_units", "U",
                "Unidades U ocupadas", 0.0, condition="rack_units > 0"),
]

# Fórmulas del módulo de estructura (spec 33-34, 51-52).
STRUCT_FORMULAS: List[FormulaSpec] = [
    FormulaSpec("ELEMENT_LENGTH", "ELEMENT", "length", "m",
                "Longitud de elemento estructural", 0.0),
    FormulaSpec("CONCRETE_VOLUME", "ELEMENT", "length * section_area * (1 + waste_pct / 100)",
                "m3", "Volumen de hormigón de elemento lineal", 0.0,
                condition="is_concrete > 0"),
    FormulaSpec("STEEL_WEIGHT", "ELEMENT", "steel_weight * (1 + waste_pct / 100)",
                "kg", "Peso de acero del elemento", 0.0, condition="is_steel > 0"),
    FormulaSpec("FORMWORK_AREA", "ELEMENT", "length * (perimeter_form)",
                "m2", "Encofrado de elemento lineal", 0.0,
                condition="is_concrete > 0"),
]

# Fórmulas del módulo de seguridad (spec 37-49, 51-52).
SECURITY_FORMULAS: List[FormulaSpec] = [
    FormulaSpec("SEC_CABLE_LENGTH", "SEGMENT", "length * (1 + spare_pct / 100)",
                "m", "Cableado de seguridad tendido", 0.0,
                condition="is_sec_cable > 0"),
    FormulaSpec("CAMERA_COUNT", "NODE", "1", "und",
                "Cámaras instaladas", 0.0, condition="is_camera > 0"),
    FormulaSpec("RECORDER_COUNT", "NODE", "1", "und",
                "Grabadores NVR/DVR", 0.0, condition="is_nvr > 0"),
    FormulaSpec("FIRE_DETECTOR_COUNT", "NODE", "1", "und",
                "Detectores de incendio", 0.0, condition="is_fire_detector > 0"),
    FormulaSpec("CALL_POINT_COUNT", "NODE", "1", "und",
                "Pulsadores de alarma", 0.0, condition="is_call_point > 0"),
    FormulaSpec("SOUNDER_COUNT", "NODE", "1", "und",
                "Sirenas y estrobos", 0.0, condition="is_sounder > 0"),
    FormulaSpec("FIRE_PANEL_COUNT", "NODE", "1", "und",
                "Central de incendios", 0.0, condition="is_fire_panel > 0"),
    FormulaSpec("INTRUSION_PANEL_COUNT", "NODE", "1", "und",
                "Central de intrusión", 0.0, condition="is_intrusion_panel > 0"),
    FormulaSpec("PIR_COUNT", "NODE", "1", "und",
                "Detectores volumétricos", 0.0, condition="is_pir > 0"),
    FormulaSpec("CONTACT_COUNT", "NODE", "1", "und",
                "Contactos magnéticos", 0.0, condition="is_contact > 0"),
    FormulaSpec("READER_COUNT", "NODE", "1", "und",
                "Lectores de acceso", 0.0, condition="is_reader > 0"),
    FormulaSpec("LOCK_COUNT", "NODE", "1", "und",
                "Cerraduras electromagnéticas", 0.0, condition="is_lock > 0"),
    FormulaSpec("SEC_CONTROLLER_COUNT", "NODE", "1", "und",
                "Controladores de acceso y PoE", 0.0,
                condition="is_sec_controller > 0"),
    FormulaSpec("FENCE_SENSOR_COUNT", "NODE", "1", "und",
                "Sensores de perímetro", 0.0, condition="is_fence_sensor > 0"),
]

# Fórmulas de la concepción de espacios (v3.15.0): mobiliario, cubiertas
# y accesibilidad. Las variables (area_inclinada, length...) salen de
# measure_furniture/measure_roof/measure_ramp/measure_handrail.
DESIGN_FORMULAS: List[FormulaSpec] = [
    FormulaSpec("FURNITURE_COUNT", "FURNITURE", "1", "und",
                "Unidades de mobiliario", 0.0),
    FormulaSpec("FURNITURE_AREA", "FURNITURE", "area", "m2",
                "Superficie ocupada por mobiliario", 0.0),
    FormulaSpec("ROOF_AREA", "ROOF", "area_inclinada", "m2",
                "Superficie real de cubierta (con pendiente)", 0.0),
    FormulaSpec("ROOF_PROJECTED_AREA", "ROOF", "area_proyectada", "m2",
                "Proyección en planta de la cubierta", 0.0),
    FormulaSpec("RAMP_AREA", "RAMP", "area_inclinada", "m2",
                "Superficie inclinada de rampa", 0.0),
    FormulaSpec("RAMP_LENGTH", "RAMP", "length", "m",
                "Desarrollo horizontal de rampa", 0.0),
    FormulaSpec("HANDRAIL_LENGTH", "HANDRAIL", "length", "m",
                "Longitud de barandilla/pasamanos", 0.0),
    # Ascensores y fachada (v3.18.0)
    FormulaSpec("ELEVATOR_COUNT", "ELEVATOR", "count", "und",
                "Ascensores instalados", 0.0),
    FormulaSpec("ELEVATOR_SHAFT_AREA", "ELEVATOR", "shaft_area", "m2",
                "Área de hueco de ascensor en planta", 0.0),
    FormulaSpec("ELEVATOR_TRAVEL", "ELEVATOR", "travel", "m",
                "Recorrido vertical servido", 0.0),
    FormulaSpec("PARASOL_COUNT", "PARASOL", "count", "und",
                "Parasoles instalados", 0.0),
    FormulaSpec("PARASOL_LENGTH", "PARASOL", "length", "m",
                "Desarrollo total de lámas", 0.0),
    FormulaSpec("PARASOL_SHADE_AREA", "PARASOL", "shade_area", "m2",
                "Área de sombra proyectada", 0.0),
    FormulaSpec("SKIN_AREA", "SKIN", "area", "m2",
                "Superficie de piel exterior", 0.0),
    FormulaSpec("SKIN_LENGTH", "SKIN", "length", "m",
                "Longitud de fachada vestida", 0.0),
    # Escaleras por tipología (v3.19.0)
    FormulaSpec("STAIR_COUNT", "STAIR", "count", "und",
                "Escaleras proyectadas", 0.0),
    FormulaSpec("STAIR_RISERS", "STAIR", "risers", "und",
                "Peldaños (contrahuellas)", 0.0),
    FormulaSpec("STAIR_FOOTPRINT", "STAIR", "footprint", "m2",
                "Huella en planta de la escalera", 0.0),
    FormulaSpec("STAIR_RUN", "STAIR", "run", "m",
                "Desarrollo horizontal de la escalera", 0.0),
    FormulaSpec("STAIR_HANDRAIL", "STAIR", "handrail", "m",
                "Barandilla (dos lados)", 0.0),
]


class QuantityEngine:
    """Parametric quantities with traced origin (spec 52)."""

    def __init__(self, formulas: Optional[List[FormulaSpec]] = None) -> None:
        self.formulas: Dict[str, FormulaSpec] = {}
        for spec in (formulas if formulas is not None
                     else DEFAULT_FORMULAS + INSTALL_FORMULAS + STRUCT_FORMULAS
                     + SECURITY_FORMULAS + DESIGN_FORMULAS):
            self.register(spec)

    def register(self, spec: FormulaSpec) -> None:
        # Fail fast on invalid expressions.
        Expression(spec.expression)
        self.formulas[spec.code] = spec

    def formulas_for(self, entity_type: str) -> List[FormulaSpec]:
        return [f for f in self.formulas.values() if f.target_type == entity_type]

    # -- variable measurement --------------------------------------------
    def measure_wall(self, wall: Wall, openings: List[Opening]) -> Dict[str, float]:
        opening_area = sum(o.width_m * o.height_m for o in openings)
        return {
            "length": wall.length_m,
            "height": wall.height_m,
            "thickness": wall.thickness_m,
            "openings_area": opening_area,
            "openings_count": float(len(openings)),
        }

    def measure_opening(self, opening: Opening) -> Dict[str, float]:
        return {"width": opening.width_m, "height": opening.height_m,
                "sill": opening.sill_height_m}

    def measure_space(self, space: Space, height_m: float) -> Dict[str, float]:
        if len(space.boundary) < 3:
            raise GeometryError(
                message=f"El local '{space.code or space.name}' no tiene contorno válido",
                code="ARQ-GEO-040",
                object_ids=[space.id],
                suggested_action="Defina el contorno del local (mínimo 3 vértices).",
            )
        return {"area": space.area_m2(), "perimeter": space.perimeter_m(),
                "height": height_m}

    # -- installations measurements (spec 24) -----------------------------
    def measure_segment(self, segment: InstallSegment, system: str = "") -> Dict[str, float]:
        """Variables QTO de un tramo; flags numéricos por disciplina.

        ``system`` es el sistema de la red del tramo (STORMWATER, GAS,
        TELECOM, ...). Con system vacío se conservan los flags clásicos
        por rol (CONDUIT→eléctrico, PIPE→agua), compatibilidad con
        llamadas existentes.
        """
        attrs = segment.attrs or {}
        role = segment.role
        is_telecom_cond = 1.0 if (system == "TELECOM" and role == "CONDUIT") else 0.0
        is_gas = 1.0 if (system == "GAS" and role == "PIPE") else 0.0
        return {
            "length": max(segment.length_m, 0.0),
            "diameter": segment.diameter_mm,
            "slope": segment.slope_pct,
            "crossings": float(segment.crossings),
            "conductors": float(attrs.get("conductors", 0) or 0),
            "cables": float(attrs.get("cables", 0) or 0),
            "spare_pct": float(attrs.get("spare_pct", 0) or 0),
            "is_elec": 1.0 if (role == "CONDUIT" and not is_telecom_cond) else 0.0,
            "is_water": 1.0 if (role == "PIPE" and not is_gas) else 0.0,
            "is_drain": 1.0 if role == "DRAIN" else 0.0,
            "is_duct": 1.0 if role == "DUCT" else 0.0,
            "is_gas": is_gas,
            "is_telecom_cond": is_telecom_cond,
            "is_cable": 1.0 if role == "CABLE" else 0.0,
            "is_fiber": 1.0 if role == "FIBER" else 0.0,
            "is_sec_cable": 1.0 if (role == "CABLE" and system in (
                "CCTV", "FIRE_ALARM", "INTRUSION", "ACCESS_CONTROL",
                "PERIMETER")) else 0.0,
        }

    def measure_element(self, element, section_area_m2: float = 0.0,
                        perimeter_form_m: float = 0.0,
                        steel_weight_kg: float = 0.0,
                        material_kind: str = "") -> Dict[str, float]:
        """Variables QTO de un elemento estructural (spec 33-34).

        ``section_area_m2`` área de la sección, ``perimeter_form_m``
        perímetro de encofrado, ``steel_weight_kg`` peso por metro
        (kg/m · m ya calculado) y ``material_kind`` para los flags
        (CONCRETE / STEEL / ...).
        """
        kind = material_kind.upper()
        return {
            "length": element.length_m,
            "section_area": section_area_m2,
            "perimeter_form": perimeter_form_m,
            "steel_weight": steel_weight_kg,
            "waste_pct": float(element.attrs.get("waste_pct", 0) or 0),
            "is_struct": 1.0,
            "is_concrete": 1.0 if kind == "CONCRETE" else 0.0,
            "is_steel": 1.0 if kind == "STEEL" else 0.0,
        }

    def measure_node(self, node: InstallNode, system: str = "") -> Dict[str, float]:
        """Variables QTO de un nodo (equipos y terminales).

        ``system`` habilita los flags específicos de pluviales y gas que
        comparten kind con otras disciplinas (TANK, APPLIANCE).
        """
        role = node.role
        is_detention = 1.0 if (system == "STORMWATER" and node.kind == "TANK"
                               and node.attrs.get("detention")) else 0.0
        return {
            "is_device": 1.0 if role in ("EQUIPMENT", "TERMINAL") else 0.0,
            "is_terminal": 1.0 if role == "TERMINAL" else 0.0,
            "is_panel": 1.0 if node.kind == "PANEL" else 0.0,
            "power_w": node.num("power_w"),
            "fixture_units": node.num("fixture_units"),
            "capacity_w": node.num("capacity_w"),
            "capacity_btu": node.num("capacity_btu"),
            "air_flow": node.num("air_flow_m3h"),
            # pluviales (spec 30): atributos solo para nodos del sistema
            # (evita que un length_m de otra disciplina los contamine)
            "is_roof_drain": 1.0 if node.kind == "ROOF_DRAIN" else 0.0,
            "is_gutter": 1.0 if node.kind == "GUTTER" else 0.0,
            "gutter_length": node.num("length_m") if node.kind == "GUTTER" else 0.0,
            "tank_volume": (node.num("volume_l") / 1000.0
                            if node.kind == "TANK" else 0.0),
            "is_detention": is_detention,
            # gas (spec 31)
            "is_gas_appliance": 1.0 if (system == "GAS" and node.kind == "APPLIANCE") else 0.0,
            "gas_power_w": node.num("power_kw") * 1000.0 if system == "GAS" else 0.0,
            # telecom (spec 32)
            "is_telecom_outlet": 1.0 if node.kind == "TELECOM_OUTLET" else 0.0,
            "is_rack": 1.0 if node.kind == "RACK" else 0.0,
            "rack_units": node.num("u_size"),
            # seguridad (spec 37-49)
            "is_camera": 1.0 if node.kind in ("CAMERA", "PERIMETER_CAMERA") else 0.0,
            "is_nvr": 1.0 if node.kind in ("NVR", "DVR") else 0.0,
            "is_fire_detector": 1.0 if node.kind in (
                "SMOKE_DETECTOR", "HEAT_DETECTOR", "BEAM_DETECTOR") else 0.0,
            "is_call_point": 1.0 if node.kind == "CALL_POINT" else 0.0,
            "is_sounder": 1.0 if node.kind in ("SOUNDER", "STROBE", "SIREN") else 0.0,
            "is_fire_panel": 1.0 if node.kind == "FIRE_PANEL" else 0.0,
            "is_intrusion_panel": 1.0 if node.kind == "INTRUSION_PANEL" else 0.0,
            "is_pir": 1.0 if node.kind == "PIR" else 0.0,
            "is_contact": 1.0 if node.kind == "MAGNETIC_CONTACT" else 0.0,
            "is_reader": 1.0 if node.kind == "READER" else 0.0,
            "is_lock": 1.0 if node.kind == "LOCK" else 0.0,
            "is_sec_controller": 1.0 if node.kind in (
                "ACCESS_CONTROLLER", "POE_SWITCH") else 0.0,
            "is_fence_sensor": 1.0 if node.kind == "FENCE_SENSOR" else 0.0,
        }

    def measure_furniture(self, piece) -> Dict[str, float]:
        """Variables QTO de una pieza de mobiliario (v3.15.0)."""
        import math
        return {
            "area": float(piece.width_m) * float(piece.depth_m),
            "height": float(piece.height_m),
            "is_furniture": 1.0,
        }

    def measure_roof(self, roof) -> Dict[str, float]:
        """Variables QTO de una cubierta (v3.15.0).

        La superficie real (con pendiente) se recalcula de la huella y
        la cumbrera guardadas: la entidad ROOF no guarda cantidades, se
        DERIVAN (spec 52: origen trazable).
        """
        from domain.cubiertas import superficie_cubierta
        datos = superficie_cubierta(roof)
        return {
            "area_proyectada": datos["area_proyectada"],
            "area_inclinada": datos["area_inclinada"],
            "perimetro": datos["perimetro"],
            "pendiente": float(roof.pendiente_pct),
            "altura_cumbrera": float(roof.altura_cumbrera_m),
            "is_roof": 1.0,
        }

    def measure_ramp(self, ramp) -> Dict[str, float]:
        """Variables QTO de una rampa accesible (v3.15.0)."""
        return {
            "length": float(ramp.length_m),
            "width": float(ramp.width_m),
            "height": float(ramp.desnivel_m),
            "slope": float(ramp.slope_pct),
            "area_inclinada": float(ramp.length_m) * float(ramp.width_m) \
                * math.sqrt(1.0 + (float(ramp.slope_pct) / 100.0) ** 2),
            "is_ramp": 1.0,
        }

    def measure_handrail(self, rail) -> Dict[str, float]:
        """Variables QTO de una barandilla (v3.15.0): longitud 3D del
        desarrollo del pasamanos (con la pendiente de rampa si la lleva)."""
        puntos = list(getattr(rail, "points", []) or [])
        largo = 0.0
        for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
            largo += math.hypot(float(x2) - float(x1),
                                float(y2) - float(y1))
        return {"length": largo, "height": float(rail.altura_m),
                "is_handrail": 1.0}

    def measure_elevator(self, ascensor) -> Dict[str, float]:
        """Variables QTO de un ascensor (v3.18.0): el hueco mide en
        planta, el recorrido vertical sube en la metadata."""
        meta = getattr(ascensor, "metadata", {}) or {}
        try:
            travel = float(meta.get("altura_total_m", 0.0) or 0.0)
        except (TypeError, ValueError):
            travel = 0.0
        return {
            "count": 1.0,
            "shaft_area": float(ascensor.width_m) * float(ascensor.depth_m),
            "travel": travel,
            "is_elevator": 1.0,
        }

    def measure_parasol(self, parasol) -> Dict[str, float]:
        """Variables QTO de un parasol (v3.18.0): desarrollo de lámas
        y sombra proyectada (n x largo x vuelo)."""
        n = max(int(getattr(parasol, "n_lamas", 0) or 0), 0)
        largo = float(getattr(parasol, "length_m", 0.0) or 0.0)
        vuelo = float(getattr(parasol, "profundidad_m", 0.0) or 0.0)
        return {
            "count": 1.0,
            "length": n * largo,
            "shade_area": n * largo * vuelo,
            "is_parasol": 1.0,
        }

    def measure_skin(self, piel) -> Dict[str, float]:
        """Variables QTO de una piel exterior (v3.18.0): la superficie
        vestida (largo x alto) y su fachada cubierta."""
        largo = float(getattr(piel, "length_m", 0.0) or 0.0)
        alto = float(getattr(piel, "altura_m", 0.0) or 0.0)
        return {
            "area": largo * alto,
            "length": largo,
            "height": alto,
            "separacion": float(getattr(piel, "separacion_m", 0.0) or 0.0),
            "is_skin": 1.0,
        }

    def measure_stair(self, escalera) -> Dict[str, float]:
        """Variables QTO de una escalera (v3.19.0): peldaños, huella,
        desarrollo y barandilla (a dos lados), derivados de la metadata
        que generó la geometría (spec 52: origen trazable)."""
        meta = getattr(escalera, "metadata", {}) or {}
        def _num(clave: str, defecto: float = 0.0) -> float:
            try:
                return float(meta.get(clave, defecto) or defecto)
            except (TypeError, ValueError):
                return defecto
        return {
            "count": 1.0,
            "risers": float(meta.get("n_contrahuellas", 0) or 0),
            "footprint": _num("area_huella_m2"),
            "run": _num("desarrollo_m"),
            "handrail": _num("barandilla_m"),
            "riser_m": float(getattr(escalera, "contrahuella_m", 0.0) or 0.0),
            "tread_m": float(getattr(escalera, "huella_m", 0.0) or 0.0),
            "is_stair": 1.0,
        }

    # -- computation -------------------------------------------------------
    def compute_for_entity(self, entity_type: str, variables: Dict[str, float],
                           object_id: str, object_code: str,
                           mode: CalculationMode = CalculationMode.BALANCED) -> List[ComputedQuantity]:
        results: List[ComputedQuantity] = []
        for spec in self.formulas_for(entity_type):
            if spec.condition:
                condition = Expression(spec.condition)
                missing_condition = condition.variables - set(variables)
                if missing_condition:
                    continue  # condition references unknown variable: skip formula
                if not float(condition.evaluate(variables)) > 0:
                    continue
            expression = Expression(spec.expression)
            missing = expression.variables - set(variables)
            if missing:
                raise CalculationError(
                    message=f"Faltan variables para {spec.code}: {', '.join(sorted(missing))}",
                    code="ARQ-CAL-002",
                    context={"formula": spec.code, "missing": sorted(missing)},
                    object_ids=[object_id],
                )
            raw = float(expression.evaluate(variables))
            if spec.target_type == "SPACE" and spec.code == "SPACE_AREA":
                raw = abs(raw)  # boundary ring orientation must not change areas
            results.append(ComputedQuantity(
                object_id=object_id, object_type=entity_type, object_code=object_code,
                formula=spec, variables={k: round(v, 6) for k, v in variables.items()},
                raw_quantity=raw, final_quantity=raw * (1.0 + spec.waste_factor),
                unit=spec.unit,
            ))
        return results

    @staticmethod
    def object_fingerprint(entity_type: str, entity_id: str, revision: int,
                           variables: Dict[str, float], formula_versions: List[str]) -> str:
        return input_hash_of(
            [{"type": entity_type, "id": entity_id, "revision": revision}],
            parameters=variables,
            extra={"formulas": sorted(formula_versions)},
        )


__all__ = ["QuantityEngine", "FormulaSpec", "ComputedQuantity", "DEFAULT_FORMULAS",
           "INSTALL_FORMULAS", "STRUCT_FORMULAS", "SECURITY_FORMULAS", "DESIGN_FORMULAS"]