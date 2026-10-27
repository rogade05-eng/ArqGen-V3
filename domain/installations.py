"""Domain entities for the installations module (spec sections 24, 25).

Model of the network engine (spec 25):

    Network
     |-- Node       connection point of the topology graph
     |-- Segment    edge between two nodes (conduit, pipe, duct, ...)
     +-- Equipment / Terminal
                     nodes of kind in EQUIPMENT_KINDS / TERMINAL_KINDS

Every installation element is part of the ONE unique semantic model
(spec 111): nodes may attach to a Level, a Space or a Wall, so all
disciplines read the same objects the architecture module owns.

Flow convention: every segment is stored in flow direction
(from = upstream, to = downstream):
  - pressurized networks (power, water, supply air): source -> terminals
  - gravity networks (drainage, stormwater):        fixtures -> outfall
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.entities.base import Entity, EntityStatus
from core.errors import DomainError

# -- disciplines (spec 24) ---------------------------------------------------
DISCIPLINES: Tuple[str, ...] = (
    "ELECTRICAL", "SANITARY", "HVAC", "GAS", "TELECOM", "STRUCTURE", "SECURITY",
)

# -- systems: one network carries exactly one system --------------------------
SYSTEMS: Dict[str, str] = {
    # ELECTRICAL
    "POWER": "ELECTRICAL",
    "LIGHTING": "ELECTRICAL",
    "EMERGENCY": "ELECTRICAL",
    # SANITARY
    "COLD_WATER": "SANITARY",
    "HOT_WATER": "SANITARY",
    "SANITARY_DRAINAGE": "SANITARY",
    "STORMWATER": "SANITARY",
    "PUMPING": "SANITARY",
    "STORAGE": "SANITARY",
    # HVAC
    "HVAC_SUPPLY": "HVAC",
    "HVAC_RETURN": "HVAC",
    "EXHAUST": "HVAC",
    # GAS / TELECOM
    "GAS": "GAS",
    "TELECOM": "TELECOM",
    # SECURITY (spec 37-49): CCTV, fuego, intrusión, acceso y perímetro
    "CCTV": "SECURITY",
    "FIRE_ALARM": "SECURITY",
    "INTRUSION": "SECURITY",
    "ACCESS_CONTROL": "SECURITY",
    "PERIMETER": "SECURITY",
}

# Network topology class:
#   radial_from_source : one source, tree towards terminals (validated as tree)
#   converge_to_sink   : several origins, one sink (validated reversing edges)
RADIAL_SYSTEMS: Tuple[str, ...] = (
    "POWER", "LIGHTING", "EMERGENCY", "COLD_WATER", "HOT_WATER", "PUMPING",
    "HVAC_SUPPLY", "GAS", "TELECOM",
    "CCTV", "FIRE_ALARM", "INTRUSION", "ACCESS_CONTROL", "PERIMETER",
)
GRAVITY_SYSTEMS: Tuple[str, ...] = (
    "SANITARY_DRAINAGE", "STORMWATER", "HVAC_RETURN", "EXHAUST", "STORAGE",
)

# -- node kinds (spec 25 Node/Equipment/Terminal + 27-32 entities) --------------
NODE_KINDS: Tuple[str, ...] = (
    # generic topology
    "SOURCE", "JUNCTION", "OUTFALL",
    # electrical (spec 27)
    "PANEL", "PROTECTION", "OUTLET", "SWITCH", "LUMINAIRE", "GROUNDING",
    # sanitary (spec 28)
    "METER", "PUMP", "TANK", "VALVE", "FIXTURE", "APPLIANCE", "ROOF_DRAIN",
    # stormwater (spec 30)
    "GUTTER",
    # HVAC (spec 29)
    "AHU", "FCU", "SPLIT", "DIFFUSER", "GRILLE", "FAN", "EXHAUST",
    # gas (spec 31)
    "REGULATOR",
    # telecom / security / low voltage (spec 32)
    "RACK", "PATCH_PANEL", "TELECOM_SWITCH", "TELECOM_OUTLET", "DEVICE_LV",
    # CCTV (spec 38)
    "CAMERA", "NVR", "DVR", "POE_SWITCH", "MONITOR", "UPS_SEC", "STORAGE_CCTV",
    # fuego (spec 43)
    "FIRE_PANEL", "SMOKE_DETECTOR", "HEAT_DETECTOR", "BEAM_DETECTOR",
    "CALL_POINT", "SOUNDER", "STROBE", "FIRE_MODULE",
    # intrusión (spec 45)
    "INTRUSION_PANEL", "PIR", "MAGNETIC_CONTACT", "GLASS_BREAK",
    "VIBRATION", "SIREN", "KEYPAD", "EXPANDER",
    # control de acceso (spec 46)
    "ACCESS_CONTROLLER", "READER", "LOCK", "EXIT_BUTTON", "REX",
    "DOOR_CONTACT", "POWER_SUPPLY",
    # perímetro (spec 47)
    "FENCE", "GATE", "BARRIER", "FENCE_SENSOR", "PERIMETER_CAMERA",
)

EQUIPMENT_KINDS: Tuple[str, ...] = (
    "PANEL", "PROTECTION", "PUMP", "TANK", "METER", "VALVE",
    "AHU", "FCU", "SPLIT", "FAN", "RACK",
    "REGULATOR", "PATCH_PANEL", "TELECOM_SWITCH",
    "NVR", "DVR", "POE_SWITCH", "MONITOR", "UPS_SEC", "STORAGE_CCTV",
    "FIRE_PANEL", "FIRE_MODULE",
    "INTRUSION_PANEL", "KEYPAD", "EXPANDER",
    "ACCESS_CONTROLLER", "POWER_SUPPLY",
    "GATE", "BARRIER",
)
TERMINAL_KINDS: Tuple[str, ...] = (
    "OUTLET", "SWITCH", "LUMINAIRE", "FIXTURE", "APPLIANCE", "DIFFUSER",
    "GRILLE", "EXHAUST", "ROOF_DRAIN", "DEVICE_LV", "OUTFALL",
    "TELECOM_OUTLET",
    "CAMERA", "PERIMETER_CAMERA",
    "SMOKE_DETECTOR", "HEAT_DETECTOR", "BEAM_DETECTOR", "CALL_POINT",
    "SOUNDER", "STROBE",
    "PIR", "MAGNETIC_CONTACT", "GLASS_BREAK", "VIBRATION", "SIREN",
    "READER", "LOCK", "EXIT_BUTTON", "REX", "DOOR_CONTACT",
    "FENCE_SENSOR",
)
SOURCE_KINDS: Tuple[str, ...] = ("SOURCE", "PANEL", "METER", "TANK", "AHU", "RACK",
                                 "FIRE_PANEL", "INTRUSION_PANEL",
                                 "ACCESS_CONTROLLER", "NVR", "FENCE")
SINK_KINDS: Tuple[str, ...] = ("OUTFALL", "FAN", "EXHAUST")

# -- segment kinds -------------------------------------------------------------
SEGMENT_KINDS: Tuple[str, ...] = (
    "CONDUIT",        # electrical raceway
    "CABLE_TRAY",     # bandeja portacables
    "CONDUCTOR_RUN",  # direct conductor run (no conduit accounting)
    "PIPE",           # pressurized pipe (water, gas)
    "DRAIN_PIPE",     # gravity pipe (drainage, stormwater)
    "DUCT",           # air duct
    "CABLE",          # telecom copper cable run (spec 32)
    "FIBER",          # fiber optic run (spec 32)
    "SEC_CABLE",      # security cabling (CCTV/fire/intrusion/access, spec 41)
)

SEGMENT_ROLES: Dict[str, str] = {
    "CONDUIT": "CONDUIT",
    "CABLE_TRAY": "CONDUIT",
    "CONDUCTOR_RUN": "CONDUIT",
    "PIPE": "PIPE",
    "DRAIN_PIPE": "DRAIN",
    "DUCT": "DUCT",
    "CABLE": "CABLE",
    "FIBER": "FIBER",
    "SEC_CABLE": "CABLE",
}


def system_of(system: str) -> str:
    """Discipline of a system name."""
    if system not in SYSTEMS:
        raise DomainError(
            message=f"Sistema de instalaciones desconocido: {system}",
            code="ARQ-MEP-001",
            context={"system": system, "allowed": sorted(SYSTEMS)},
        )
    return SYSTEMS[system]


def topology_of(system: str) -> str:
    """Topology class of a system (radial from source / converge to sink)."""
    return "radial_from_source" if system in RADIAL_SYSTEMS else "converge_to_sink"


def role_of_kind(kind: str) -> str:
    """EQUIPMENT / TERMINAL / JUNCTION role of a node kind."""
    if kind in EQUIPMENT_KINDS:
        return "EQUIPMENT"
    if kind in TERMINAL_KINDS:
        return "TERMINAL"
    return "JUNCTION"


@dataclass
class InstallNetwork(Entity):
    """One network of one system (spec 25)."""

    ENTITY_TYPE = "NETWORK"
    name: str = ""
    discipline: str = "ELECTRICAL"
    system: str = "POWER"
    description: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.discipline not in DISCIPLINES:
            raise DomainError(
                message=f"Disciplina de instalaciones inválida: {self.discipline}",
                code="ARQ-MEP-002",
                context={"discipline": self.discipline, "allowed": list(DISCIPLINES)},
            )
        if system_of(self.system) != self.discipline:
            raise DomainError(
                message=f"El sistema {self.system} no pertenece a la disciplina {self.discipline}",
                code="ARQ-MEP-003",
                context={"system": self.system, "expected": system_of(self.system)},
            )


@dataclass
class InstallNode(Entity):
    """Node of the network graph: equipment, terminal or junction (spec 25).

    Engineering attributes travel in ``attrs`` (JSON): power_w, voltage,
    phases, pf, rating_a, fixture_units, flow_ls, capacity_btu,
    air_flow_m3h, elevation_m, phase, fixture_kind, ...  Numeric attributes
    feed QTO formulas and the discipline engines.
    """

    ENTITY_TYPE = "NODE"
    network_id: str = ""
    kind: str = "JUNCTION"
    name: str = ""
    x: float = 0.0
    y: float = 0.0
    elevation_m: float = 0.0
    space_id: Optional[str] = None
    wall_id: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind not in NODE_KINDS:
            raise DomainError(
                message=f"Tipo de nodo desconocido: {self.kind}",
                code="ARQ-MEP-004",
                context={"kind": self.kind, "allowed": list(NODE_KINDS)},
            )

    @property
    def role(self) -> str:
        return role_of_kind(self.kind)

    def num(self, key: str, default: float = 0.0) -> float:
        """Numeric attribute (never raises; non-numeric values fall back)."""
        try:
            value = self.attrs.get(key, default)
            return float(default if value is None else value)
        except (TypeError, ValueError):
            return default


@dataclass
class InstallSegment(Entity):
    """Edge of the network graph, stored in flow direction (spec 25, 26).

    length_m == 0 means "compute from routing between node positions".
    Routing metrics (crossings, waypoints) are computed by the routing
    engine (spec 26) and stored for traceability.
    """

    ENTITY_TYPE = "SEGMENT"
    network_id: str = ""
    from_node_id: str = ""
    to_node_id: str = ""
    kind: str = "CONDUIT"
    name: str = ""
    length_m: float = 0.0
    diameter_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    slope_pct: float = 0.0
    material: str = ""
    routing: str = "ORTHO"            # ORTHO | STRAIGHT
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    crossings: int = 0
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.kind not in SEGMENT_KINDS:
            raise DomainError(
                message=f"Tipo de tramo desconocido: {self.kind}",
                code="ARQ-MEP-005",
                context={"kind": self.kind, "allowed": list(SEGMENT_KINDS)},
            )
        if self.length_m < 0 or self.diameter_mm < 0:
            raise DomainError(
                message="La longitud y el diámetro del tramo no pueden ser negativos",
                code="ARQ-MEP-006",
            )

    @property
    def role(self) -> str:
        return SEGMENT_ROLES.get(self.kind, "OTHER")

    def num(self, key: str, default: float = 0.0) -> float:
        """Numeric attribute (never raises; non-numeric values fall back)."""
        try:
            value = self.attrs.get(key, default)
            return float(default if value is None else value)
        except (TypeError, ValueError):
            return default


__all__ = [
    "InstallNetwork", "InstallNode", "InstallSegment",
    "DISCIPLINES", "SYSTEMS", "RADIAL_SYSTEMS", "GRAVITY_SYSTEMS",
    "NODE_KINDS", "EQUIPMENT_KINDS", "TERMINAL_KINDS", "SOURCE_KINDS",
    "SINK_KINDS", "SEGMENT_KINDS", "SEGMENT_ROLES",
    "system_of", "topology_of", "role_of_kind",
]
