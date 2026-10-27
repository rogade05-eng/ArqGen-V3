"""HVAC Engine (spec section 29).

Entidades del spec: Zone, ThermalLoad, AHU, FCU, Split, Duct, Diffuser,
Grille, Fan, Exhaust. Funciones del spec:

    thermal_load()     carga térmica de un local (sensible + latente)
    select_equipment() selección de equipos del catálogo
    size_duct()        dimensionado de ducto (circular/rectangular)
    route_duct()       delega en el Routing Engine (spec 26)
    calculate_airflow() caudal de aire desde la carga sensible
    validate_clearance() holguras: cruces y distancias a obstáculos

Método de carga (herramienta de pre-dimensionado, supuestos por datos):
  - Transmisión:  Q = Σ U·A·ΔT   (muros expuestos, cubierta, suelo)
  - Solar:        Q = A_glazing · factor_solar
  - Interno:      ocupantes (75 W sensible + 55 W latente), iluminación y
                  equipos por m².
  - Ventilación:  infiltración por renovaciones horarias (ACH):
                  Q = ρ·cp·V·ACH/3600·ΔT.
Calefacción: transmisión + ventilación (sin aportes solares ni internos).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.errors import CalculationError

AIR_DENSITY = 1.2          # kg/m³
AIR_CP = 1005.0            # J/kg·K
BTU_PER_WH = 3.4121

# Supuestos por defecto (todos sobreescribibles por parámetros del servicio).
DEFAULT_U_WALL = 2.0       # W/m²·K mampostería sin aislar
DEFAULT_U_WINDOW = 5.8     # W/m²·K vidrio simple
DEFAULT_U_ROOF = 1.5       # W/m²·K cubierta ligera
DEFAULT_U_FLOOR = 0.0      # suelo sobre terreno: sin carga por defecto

DEFAULT_DT_COOLING_K = 9.0     # exterior 33 °C, interior 24 °C
DEFAULT_DT_HEATING_K = 10.0    # exterior 10 °C, interior 20 °C
DEFAULT_SOLAR_FACTOR = 180.0   # W/m² efectivo sobre vidrio
DEFAULT_OCCUPANCY_M2 = 10.0    # m² por ocupante
DEFAULT_SENSIBLE_W_PERSON = 75.0
DEFAULT_LATENT_W_PERSON = 55.0
DEFAULT_LIGHTING_WM2 = 10.0
DEFAULT_EQUIPMENT_WM2 = 5.0
DEFAULT_INFILTRATION_ACH = 0.5

DEFAULT_SUPPLY_DT_K = 10.0     # ΔT aire de impulsión

DUCT_VELOCITY_LIMITS: Dict[str, Tuple[float, float]] = {
    # kind: (recomendado, máximo) m/s
    "MAIN": (6.0, 8.0),
    "BRANCH": (4.0, 5.0),
    "RETURN": (3.0, 4.0),
}

ROUND_DUCT_DN_MM: Tuple[float, ...] = (100.0, 125.0, 150.0, 160.0, 180.0, 200.0,
                                       225.0, 250.0, 280.0, 315.0, 355.0, 400.0,
                                       450.0, 500.0, 560.0, 630.0, 710.0, 800.0)
RECT_DUCT_HEIGHTS_MM: Tuple[float, ...] = (120.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0)

# Catálogo de equipos (BTU/h nominales) — splits y FCU comerciales.
EQUIPMENT_CATALOG_BTU: Tuple[float, ...] = (9000.0, 12000.0, 18000.0, 24000.0,
                                            30000.0, 36000.0, 48000.0, 60000.0)
EQUIPMENT_MARGIN = 1.10


@dataclass
class ThermalLoad:
    """Resultado de thermal_load() (entidad ThermalLoad del spec 29)."""

    space_code: str = ""
    area_m2: float = 0.0
    volume_m3: float = 0.0
    transmission_w: float = 0.0
    solar_w: float = 0.0
    internal_sensible_w: float = 0.0
    internal_latent_w: float = 0.0
    ventilation_w: float = 0.0
    cooling_sensible_w: float = 0.0
    cooling_total_w: float = 0.0
    cooling_btu_h: float = 0.0
    heating_w: float = 0.0
    occupants: int = 0
    assumptions: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "space": self.space_code, "area_m2": round(self.area_m2, 2),
            "volume_m3": round(self.volume_m3, 2),
            "transmission_w": round(self.transmission_w, 1),
            "solar_w": round(self.solar_w, 1),
            "internal_sensible_w": round(self.internal_sensible_w, 1),
            "internal_latent_w": round(self.internal_latent_w, 1),
            "ventilation_w": round(self.ventilation_w, 1),
            "cooling_sensible_w": round(self.cooling_sensible_w, 1),
            "cooling_total_w": round(self.cooling_total_w, 1),
            "cooling_btu_h": round(self.cooling_btu_h, 0),
            "heating_w": round(self.heating_w, 1),
            "occupants": self.occupants,
            "assumptions": {k: round(v, 3) for k, v in self.assumptions.items()},
        }


def thermal_load(area_m2: float, height_m: float,
                 exposed_wall_area_m2: float = 0.0,
                 glazing_area_m2: float = 0.0,
                 roof_area_m2: float = 0.0,
                 floor_area_m2: float = 0.0,
                 params: Optional[Dict[str, float]] = None) -> ThermalLoad:
    """Carga térmica de un local (spec 29: thermal_load)."""
    p = params or {}
    dt_cool = p.get("dt_cooling_k", DEFAULT_DT_COOLING_K)
    dt_heat = p.get("dt_heating_k", DEFAULT_DT_HEATING_K)
    u_wall = p.get("u_wall", DEFAULT_U_WALL)
    u_win = p.get("u_window", DEFAULT_U_WINDOW)
    u_roof = p.get("u_roof", DEFAULT_U_ROOF)
    u_floor = p.get("u_floor", DEFAULT_U_FLOOR)
    solar = p.get("solar_factor", DEFAULT_SOLAR_FACTOR)
    occ_m2 = p.get("occupancy_m2", DEFAULT_OCCUPANCY_M2)
    w_sens = p.get("sensible_w_person", DEFAULT_SENSIBLE_W_PERSON)
    w_lat = p.get("latent_w_person", DEFAULT_LATENT_W_PERSON)
    light = p.get("lighting_w_m2", DEFAULT_LIGHTING_WM2)
    equip = p.get("equipment_w_m2", DEFAULT_EQUIPMENT_WM2)
    ach = p.get("infiltration_ach", DEFAULT_INFILTRATION_ACH)

    if area_m2 <= 0:
        raise CalculationError(
            message="El área del local debe ser positiva para calcular la carga térmica",
            code="ARQ-HVA-001", context={"area_m2": area_m2})

    volume = area_m2 * height_m
    occupants = int(max(1.0, area_m2 / occ_m2)) if occ_m2 > 0 else 1

    transmission = (exposed_wall_area_m2 * u_wall
                    + glazing_area_m2 * u_win
                    + roof_area_m2 * u_roof
                    + floor_area_m2 * u_floor) * dt_cool
    solar_w = glazing_area_m2 * solar
    internal_sensible = occupants * w_sens + area_m2 * (light + equip)
    internal_latent = occupants * w_lat
    ventilation = AIR_DENSITY * AIR_CP * volume * ach / 3600.0 * dt_cool

    cooling_sensible = transmission + solar_w + internal_sensible + ventilation
    cooling_total = cooling_sensible + internal_latent

    heating_transmission = (exposed_wall_area_m2 * u_wall
                            + glazing_area_m2 * u_win
                            + roof_area_m2 * u_roof
                            + floor_area_m2 * u_floor) * dt_heat
    heating_vent = AIR_DENSITY * AIR_CP * volume * ach / 3600.0 * dt_heat

    return ThermalLoad(
        space_code="", area_m2=area_m2, volume_m3=volume,
        transmission_w=transmission, solar_w=solar_w,
        internal_sensible_w=internal_sensible,
        internal_latent_w=internal_latent,
        ventilation_w=ventilation,
        cooling_sensible_w=cooling_sensible,
        cooling_total_w=cooling_total,
        cooling_btu_h=cooling_total * BTU_PER_WH,
        heating_w=heating_transmission + heating_vent,
        occupants=occupants,
        assumptions={
            "dt_cooling_k": dt_cool, "dt_heating_k": dt_heat,
            "u_wall": u_wall, "u_window": u_win, "u_roof": u_roof,
            "solar_factor": solar, "occupancy_m2": occ_m2,
            "lighting_w_m2": light, "equipment_w_m2": equip,
            "infiltration_ach": ach,
        },
    )


def calculate_airflow(sensible_w: float, supply_dt_k: float = DEFAULT_SUPPLY_DT_K) -> float:
    """Caudal de aire en m³/h desde la carga sensible (calculate_airflow)."""
    if sensible_w <= 0:
        raise CalculationError(
            message="La carga sensible debe ser positiva para calcular el caudal de aire",
            code="ARQ-HVA-002")
    if supply_dt_k <= 0:
        raise CalculationError(
            message="El ΔT de impulsión debe ser positivo", code="ARQ-HVA-003")
    q_m3s = sensible_w / (AIR_DENSITY * AIR_CP * supply_dt_k)
    return round(q_m3s * 3600.0, 1)


@dataclass
class DuctSizing:
    """Resultado de size_duct() (entidad Duct del spec 29)."""

    airflow_m3h: float = 0.0
    kind: str = "BRANCH"
    velocity_ms: float = 0.0
    area_m2: float = 0.0
    shape: str = "ROUND"
    diameter_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    findings: List[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict:
        return {
            "airflow_m3h": round(self.airflow_m3h, 1), "kind": self.kind,
            "velocity_ms": round(self.velocity_ms, 2),
            "area_m2": round(self.area_m2, 4), "shape": self.shape,
            "diameter_mm": round(self.diameter_mm, 0),
            "width_mm": round(self.width_mm, 0), "height_mm": round(self.height_mm, 0),
            "findings": self.findings, "ok": self.ok,
        }


def size_duct(airflow_m3h: float, kind: str = "BRANCH",
              shape: str = "ROUND",
              target_velocity_ms: Optional[float] = None) -> DuctSizing:
    """Dimensionado de ducto (spec 29: size_duct).

    kind: MAIN | BRANCH | RETURN (velocidades de DUCT_VELOCITY_LIMITS).
    shape: ROUND (diámetro comercial) o RECT (alto comercial, ancho
    redondeado a 10 mm, relación de aspecto ≤ 4).
    """
    if airflow_m3h <= 0:
        raise CalculationError(
            message="El caudal de aire debe ser positivo para dimensionar el ducto",
            code="ARQ-HVA-004")
    if kind not in DUCT_VELOCITY_LIMITS:
        raise CalculationError(
            message=f"Tipo de ducto desconocido: {kind}",
            code="ARQ-HVA-005", context={"allowed": list(DUCT_VELOCITY_LIMITS)})
    recommended, v_max = DUCT_VELOCITY_LIMITS[kind]
    velocity = target_velocity_ms if target_velocity_ms else recommended
    if velocity > v_max:
        raise CalculationError(
            message=f"La velocidad {velocity:.1f} m/s excede el máximo de {v_max:.0f} m/s para {kind}",
            code="ARQ-HVA-006")
    area = (airflow_m3h / 3600.0) / velocity
    result = DuctSizing(airflow_m3h=airflow_m3h, kind=kind,
                        velocity_ms=velocity, area_m2=area)
    if shape.upper() == "ROUND":
        result.shape = "ROUND"
        for dn in ROUND_DUCT_DN_MM:
            real_area = math.pi * (dn / 1000.0) ** 2 / 4.0
            if real_area >= area - 1e-9:
                result.diameter_mm = dn
                result.velocity_ms = (airflow_m3h / 3600.0) / real_area
                break
        if result.diameter_mm == 0:
            raise CalculationError(
                message=f"Caudal {airflow_m3h:.0f} m³/h fuera del catálogo de ductos circulares",
                code="ARQ-HVA-007")
    else:
        result.shape = "RECT"
        for height in RECT_DUCT_HEIGHTS_MM:
            width = area / (height / 1000.0) * 1000.0
            if width <= height:
                continue
            width_rounded = math.ceil(width / 10.0) * 10.0
            aspect = width_rounded / height
            if aspect <= 4.0:
                result.height_mm = height
                result.width_mm = width_rounded
                real_area = (width_rounded / 1000.0) * (height / 1000.0)
                result.velocity_ms = (airflow_m3h / 3600.0) / real_area
                break
        if result.width_mm == 0:
            raise CalculationError(
                message=f"Caudal {airflow_m3h:.0f} m³/h fuera de la gama rectangular con relación ≤ 4",
                code="ARQ-HVA-008")
    if result.velocity_ms > v_max + 1e-9:
        result.ok = False
        result.findings.append(
            f"Velocidad real {result.velocity_ms:.1f} m/s por encima del límite {v_max:.0f} m/s")
    return result


@dataclass
class EquipmentSelection:
    """Resultado de select_equipment() (spec 29)."""

    load_btu_h: float = 0.0
    units: int = 0
    unit_btu_h: float = 0.0
    total_btu_h: float = 0.0
    coverage_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "load_btu_h": round(self.load_btu_h, 0),
            "units": self.units,
            "unit_btu_h": round(self.unit_btu_h, 0),
            "total_btu_h": round(self.total_btu_h, 0),
            "coverage_pct": round(self.coverage_pct, 1),
        }


def select_equipment(load_btu_h: float,
                     catalog: Tuple[float, ...] = EQUIPMENT_CATALOG_BTU,
                     margin: float = EQUIPMENT_MARGIN) -> EquipmentSelection:
    """Selección de equipos del catálogo (spec 29: select_equipment).

    Elige el menor conjunto de unidades que cubre carga×margen,
    prefiriendo unidades grandes y repetibles (instalación homogénea).
    """
    if load_btu_h <= 0:
        raise CalculationError(
            message="La carga en BTU/h debe ser positiva para seleccionar equipos",
            code="ARQ-HVA-009")
    required = load_btu_h * margin
    largest = catalog[-1]
    if required <= largest:
        for capacity in catalog:
            if capacity >= required - 1e-9:
                return EquipmentSelection(
                    load_btu_h=load_btu_h, units=1, unit_btu_h=capacity,
                    total_btu_h=capacity, coverage_pct=capacity / load_btu_h * 100.0)
    units = int(math.ceil(required / largest))
    return EquipmentSelection(
        load_btu_h=load_btu_h, units=units, unit_btu_h=largest,
        total_btu_h=units * largest, coverage_pct=units * largest / load_btu_h * 100.0)


__all__ = [
    "ThermalLoad", "DuctSizing", "EquipmentSelection",
    "thermal_load", "calculate_airflow", "size_duct", "select_equipment",
    "DUCT_VELOCITY_LIMITS", "EQUIPMENT_CATALOG_BTU", "DEFAULT_SUPPLY_DT_K",
    "AIR_DENSITY", "AIR_CP", "BTU_PER_WH",
]
