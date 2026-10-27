"""Domain entities for the structure module (spec sections 33, 34).

Element catalogue (spec 33): Foundation, Column, Beam, Slab, Wall,
Truss, Brace, Connection, Plate, Bolt, Weld. The module also carries the
analysis supports: Loads, LoadCases, Combinations, Supports, Materials,
Sections, Members and Connections.

Like every other discipline, structural elements live in the ONE unique
semantic model: an element may attach to a Level, a Space or reference
an architectural Wall (shear walls reuse the architecture geometry).

Load flow convention:
  - LoadCase: one design action (DEAD / LIVE / WIND / SEISMIC / SNOW).
  - Combination: factors over load cases (e.g. 1.35·DEAD + 1.5·LIVE).
  - Analysis results travel as CalculationResult records (spec 102) and
    as numeric attrs of the element (axial_kN, moment_kNm, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.entities.base import Entity
from core.errors import DomainError

# -- element kinds (spec 33) ---------------------------------------------------
ELEMENT_KINDS: Tuple[str, ...] = (
    "FOUNDATION", "COLUMN", "BEAM", "SLAB", "WALL",
    "TRUSS", "BRACE", "CONNECTION", "PLATE", "BOLT", "WELD",
)

# Members that carry axial force / bending (analyzable).
LINEAR_KINDS: Tuple[str, ...] = ("COLUMN", "BEAM", "TRUSS", "BRACE")

# -- materials -------------------------------------------------------------------
MATERIAL_KINDS: Tuple[str, ...] = ("CONCRETE", "STEEL", "MASONRY", "TIMBER")

# -- section shapes ----------------------------------------------------------------
SECTION_SHAPES: Tuple[str, ...] = ("RECTANGLE", "CIRCLE", "I_PROFILE")

# -- load cases (spec 33 Loads/LoadCases) ---------------------------------------------
LOAD_CASE_KINDS: Tuple[str, ...] = ("DEAD", "LIVE", "WIND", "SEISMIC", "SNOW")

# -- supports (spec 33 Supports) ---------------------------------------------------
SUPPORT_KINDS: Tuple[str, ...] = ("PIN", "ROLLER", "FIXED", "FREE")

STEEL_E_GPA = 210.0          # acero estructural
CONCRETE_E_28_GPA = 21.0     # E28 ≈ 850·fck (MPa) para fck 25 MPa (aprox. 21 GPa)


def check_kind(kind: str, allowed: Tuple[str, ...], code: str, label: str) -> str:
    """Shared validation of catalogued kinds."""
    if kind not in allowed:
        raise DomainError(
            message=f"{label} desconocido: {kind}",
            code=code, context={"kind": kind, "allowed": list(allowed)})
    return kind


@dataclass
class StructuralMaterial(Entity):
    """Material of the structural module (spec 33 Materials)."""

    ENTITY_TYPE = "MATERIAL"
    name: str = ""
    kind: str = "CONCRETE"
    fck_mpa: float = 0.0        # resistencia característica hormigón
    fy_mpa: float = 0.0         # límite elástico acero
    e_gpa: float = 0.0          # módulo de elasticidad
    density_kn_m3: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        check_kind(self.kind, MATERIAL_KINDS, "ARQ-STR-001", "Tipo de material")
        if self.e_gpa <= 0:
            self.e_gpa = STEEL_E_GPA if self.kind == "STEEL" else CONCRETE_E_28_GPA
        if self.density_kn_m3 <= 0:
            self.density_kn_m3 = {"CONCRETE": 25.0, "STEEL": 78.5,
                                  "MASONRY": 18.0, "TIMBER": 6.0}.get(self.kind, 24.0)


@dataclass
class StructuralSection(Entity):
    """Cross section of a linear element (spec 33 Sections).

    shape RECTANGLE: h_mm × b_mm
    shape CIRCLE:    d_mm
    shape I_PROFILE: h_mm, b_mm, tw_mm, tf_mm
    """

    ENTITY_TYPE = "SECTION"
    name: str = ""
    shape: str = "RECTANGLE"
    h_mm: float = 0.0
    b_mm: float = 0.0
    tw_mm: float = 0.0
    tf_mm: float = 0.0
    d_mm: float = 0.0
    weight_kg_m: float = 0.0    # optional catalog value overrides computation

    def __post_init__(self) -> None:
        super().__post_init__()
        check_kind(self.shape, SECTION_SHAPES, "ARQ-STR-002", "Forma de sección")


@dataclass
class StructuralElement(Entity):
    """Structural element (spec 33).

    Geometry: ``start``/``end`` in model coordinates (m); ``z0``/``z1``
    elevations (m). Linear elements span start→end; SLAB uses ``attrs``
    polygon + thickness; FOUNDATION uses attrs (footing type, base area).

    Supports (spec 33 Supports) travel in ``attrs["support_a"]`` /
    ``attrs["support_b"]`` for beam-like analysis, or, for trusses, the
    full joint model travels in ``attrs`` of the TRUSS element:
    ``nodes``, ``members``, ``supports``, ``joint_loads`` (spec 34).
    """

    ENTITY_TYPE = "ELEMENT"
    kind: str = "BEAM"
    name: str = ""
    material_id: str = ""
    section_id: str = ""
    start: Tuple[float, float] = (0.0, 0.0)
    end: Tuple[float, float] = (0.0, 0.0)
    z0: float = 0.0
    z1: float = 0.0
    load_udl_kn_m: float = 0.0
    point_loads: List[Tuple[float, float]] = field(default_factory=list)  # (a_m, P_kN)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        check_kind(self.kind, ELEMENT_KINDS, "ARQ-STR-003", "Tipo de elemento")

    @property
    def length_m(self) -> float:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        dz = self.z1 - self.z0
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    def num(self, key: str, default: float = 0.0) -> float:
        try:
            value = self.attrs.get(key, default)
            return float(default if value is None else value)
        except (TypeError, ValueError):
            return default


@dataclass
class LoadCase(Entity):
    """Design action (spec 33 LoadCases)."""

    ENTITY_TYPE = "LOAD_CASE"
    name: str = ""
    kind: str = "DEAD"
    factor: float = 1.0
    description: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        check_kind(self.kind, LOAD_CASE_KINDS, "ARQ-STR-004", "Tipo de acción")


@dataclass
class Combination(Entity):
    """Load combination with factors per case (spec 33 Combinations)."""

    ENTITY_TYPE = "COMBINATION"
    name: str = ""
    case_factors: Dict[str, float] = field(default_factory=dict)  # case code → factor
    description: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.case_factors:
            raise DomainError(
                message="La combinación debe incluir al menos una acción",
                code="ARQ-STR-005")


__all__ = [
    "StructuralMaterial", "StructuralSection", "StructuralElement",
    "LoadCase", "Combination",
    "ELEMENT_KINDS", "LINEAR_KINDS", "MATERIAL_KINDS", "SECTION_SHAPES",
    "LOAD_CASE_KINDS", "SUPPORT_KINDS",
    "STEEL_E_GPA", "CONCRETE_E_28_GPA",
]
