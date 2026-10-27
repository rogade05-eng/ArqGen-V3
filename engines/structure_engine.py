"""Structural Engine (spec section 34).

Cálculos deterministas y verificables a mano:

  - Secciones: A, Ix, Iy, Wel y peso propio por forma (RECTANGLE,
    CIRCLE, I_PROFILE).
  - Viga (Reactions, Shear, Moment, Deflection):
        simple     UDL:  R = wL/2,  V = wL/2,  M = wL²/8,  δ = 5wL⁴/(384EI)
        simple     punto: R = P/2,  M = PL/4,  δ = PL³/(48EI)  (centrada)
        empotrada  UDL:  R = wL/2,  V = wL/2,  M = wL²/12,  δ = wL⁴/(384EI)
  - Pilar (Axial, Buckling, Utilization): esbeltez λ = Le/i, carga
    crítica de Euler Ncr = π²E·I/Le², utilización = N/Nrd con Nrd
    limitado por aplastamiento del material y pandeo.
  - Torsión elástica de sección circular: T ≤ τadm · Ip / r.
  - Cercha (Node, Member, Support, Load): método de los nudos resuelto
    con eliminación gaussiana con pivoteo parcial — sin dependencias
    externas, resultado determinista.
  - Uniones: cortante de pernos (V_rd = n·A·τ) y cordón de soldadura
    (F = a · L · fw).

Todas las unidades: kN, kN·m, m, kN/m. El motor no consulta la base de
datos: recibe datos puros y devuelve resultados puros (§107).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.errors import CalculationError

E_ALLOWABLE_SHEAR_STEEL_MPA = 100.0     # τ admisible perno (informativo)
WELD_STRENGTH_N_MM2 = 160.0             # resistencia cordón electrodos rutilos


# -- Secciones -----------------------------------------------------------------

@dataclass
class SectionProperties:
    """Propiedades geométricas de la sección (perfiles)."""

    area_m2: float = 0.0
    ix_m4: float = 0.0        # inercia fuerte
    iy_m4: float = 0.0        # inercia débil
    wel_cm3: float = 0.0      # módulo resistente elástico (eje fuerte)
    radius_gyration_m: float = 0.0
    weight_kg_m: float = 0.0

    def to_dict(self) -> dict:
        return {
            "area_m2": round(self.area_m2, 6),
            "ix_m4": round(self.ix_m4, 9),
            "iy_m4": round(self.iy_m4, 9),
            "wel_cm3": round(self.wel_cm3, 3),
            "radius_gyration_m": round(self.radius_gyration_m, 5),
            "weight_kg_m": round(self.weight_kg_m, 2),
        }


def section_properties(shape: str, h_mm: float = 0.0, b_mm: float = 0.0,
                       tw_mm: float = 0.0, tf_mm: float = 0.0, d_mm: float = 0.0,
                       density_kn_m3: float = 78.5,
                       weight_kg_m: float = 0.0) -> SectionProperties:
    """Propiedades de sección por forma (perfiles)."""
    if shape == "RECTANGLE":
        if h_mm <= 0 or b_mm <= 0:
            raise CalculationError(
                message="La sección rectangular exige h y b positivos",
                code="ARQ-STR-010", context={"h_mm": h_mm, "b_mm": b_mm})
        h, b = h_mm / 1000.0, b_mm / 1000.0
        area = h * b
        ix = b * h ** 3 / 12.0
        iy = h * b ** 3 / 12.0
        wel = ix / (h / 2.0)
        i_min = iy
        weight = area * density_kn_m3 * 1000.0 / 9.80665
    elif shape == "CIRCLE":
        if d_mm <= 0:
            raise CalculationError(
                message="La sección circular exige d positivo",
                code="ARQ-STR-011", context={"d_mm": d_mm})
        d = d_mm / 1000.0
        area = math.pi * d ** 2 / 4.0
        ix = math.pi * d ** 4 / 64.0
        iy = ix
        wel = ix / (d / 2.0)
        i_min = ix
        weight = area * density_kn_m3 * 1000.0 / 9.80665
    elif shape == "I_PROFILE":
        if h_mm <= 0 or b_mm <= 0 or tw_mm <= 0 or tf_mm <= 0:
            raise CalculationError(
                message="El perfil I exige h, b, tw y tf positivos",
                code="ARQ-STR-012",
                context={"h_mm": h_mm, "b_mm": b_mm, "tw_mm": tw_mm, "tf_mm": tf_mm})
        h, b, tw, tf = h_mm / 1000.0, b_mm / 1000.0, tw_mm / 1000.0, tf_mm / 1000.0
        area = 2.0 * b * tf + (h - 2.0 * tf) * tw
        # Aproximación clásica: almas + inercia de alas por teorema de Steiner.
        hw = h - 2.0 * tf
        ix_web = tw * hw ** 3 / 12.0
        d_flange = hw / 2.0 + tf / 2.0
        ix_flange = 2.0 * (b * tf ** 3 / 12.0 + b * tf * d_flange ** 2)
        ix = ix_web + ix_flange
        iy = 2.0 * (tf * b ** 3 / 12.0) + hw * tw ** 3 / 12.0
        wel = ix / (h / 2.0)
        i_min = iy
        weight = area * density_kn_m3 * 1000.0 / 9.80665
    else:
        raise CalculationError(
            message=f"Forma de sección desconocida: {shape}",
            code="ARQ-STR-013", context={"shape": shape})
    return SectionProperties(
        area_m2=area, ix_m4=ix, iy_m4=iy, wel_cm3=wel * 1e6,
        radius_gyration_m=math.sqrt(i_min / area) if area > 0 else 0.0,
        weight_kg_m=weight_kg_m if weight_kg_m > 0 else weight)


# -- Viga: reacciones, cortante, momento y flecha ---------------------------------

@dataclass
class BeamResult:
    """Resultado del análisis de viga (reacciones/cortante/momento/flecha)."""

    support: str = "SIMPLE"
    length_m: float = 0.0
    reaction_a_kn: float = 0.0
    reaction_b_kn: float = 0.0
    shear_max_kn: float = 0.0
    moment_max_knm: float = 0.0
    deflection_mm: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "support": self.support, "length_m": round(self.length_m, 4),
            "reaction_a_kn": round(self.reaction_a_kn, 4),
            "reaction_b_kn": round(self.reaction_b_kn, 4),
            "shear_max_kn": round(self.shear_max_kn, 4),
            "moment_max_knm": round(self.moment_max_knm, 4),
            "deflection_mm": round(self.deflection_mm, 3),
            "notes": self.notes,
        }


def beam_analysis(length_m: float, udl_kn_m: float = 0.0,
                  point_loads: Optional[Sequence[Tuple[float, float]]] = None,
                  support: str = "SIMPLE", e_gpa: float = 21.0,
                  ix_m4: float = 0.0) -> BeamResult:
    """Viga isostática con carga uniforme y cargas puntuales (momento).

    Las cargas puntuales se superponen: reacciones lineales, momento
    máximo informado como envolvente P·a·b/L por carga.
    """
    if length_m <= 0:
        raise CalculationError(
            message="La luz de la viga debe ser positiva",
            code="ARQ-STR-014", context={"length_m": length_m})
    if support not in ("SIMPLE", "CANTILEVER"):
        raise CalculationError(
            message=f"Apoyo no soportado en viga: {support}",
            code="ARQ-STR-015", context={"support": support})
    loads = [(float(a), float(p)) for a, p in (point_loads or [])]
    result = BeamResult(support=support, length_m=length_m)

    if support == "SIMPLE":
        # Carga uniforme.
        result.reaction_a_kn += udl_kn_m * length_m / 2.0
        result.reaction_b_kn += udl_kn_m * length_m / 2.0
        result.shear_max_kn = max(result.shear_max_kn, udl_kn_m * length_m / 2.0)
        result.moment_max_knm = max(result.moment_max_knm,
                                    udl_kn_m * length_m ** 2 / 8.0)
        # Cargas puntuales.
        total_point = 0.0
        for a, p in loads:
            if not 0.0 <= a <= length_m:
                raise CalculationError(
                    message="La carga puntual debe situarse dentro de la luz",
                    code="ARQ-STR-016", context={"a_m": a, "length_m": length_m})
            b = length_m - a
            result.reaction_a_kn += p * b / length_m
            result.reaction_b_kn += p * a / length_m
            result.moment_max_knm = max(result.moment_max_knm, p * a * b / length_m)
            total_point += p
        result.shear_max_kn = max(result.shear_max_kn, result.reaction_a_kn,
                                  result.reaction_b_kn)
        # Flecha por superposición (elástica).
        if ix_m4 > 0:
            e = e_gpa * 1e9  # N/m²
            delta_udl = 5.0 * (udl_kn_m * 1000.0) * length_m ** 4 / (384.0 * e * ix_m4)
            delta_points = 0.0
            for a, p in loads:
                b = length_m - a
                delta_points += p * 1000.0 * b * a * (length_m ** 2 - a ** 2 - b ** 2) \
                    / (9.0 * math.sqrt(3.0) * e * ix_m4 * length_m)
            result.deflection_mm = (delta_udl + delta_points) * 1000.0
    else:  # CANTILEVER
        fixed = udl_kn_m * length_m + sum(p for _a, p in loads)
        result.reaction_a_kn = fixed
        result.reaction_b_kn = 0.0
        result.shear_max_kn = fixed
        moment = udl_kn_m * length_m ** 2 / 2.0
        for a, p in loads:
            moment += p * a
        result.moment_max_knm = moment
        if ix_m4 > 0:
            e = e_gpa * 1e9
            delta = (udl_kn_m * 1000.0) * length_m ** 4 / (8.0 * e * ix_m4)
            for a, p in loads:
                delta += p * 1000.0 * a ** 2 * (3.0 * length_m - a) / (6.0 * e * ix_m4)
            result.deflection_mm = delta * 1000.0
    return result


# -- Pilar: axial, esbeltez, pandeo y utilización ----------------------------------

@dataclass
class ColumnResult:
    """Resultado del análisis de pilar (axial/pandeo/utilización)."""

    length_m: float = 0.0
    axial_kn: float = 0.0
    slenderness: float = 0.0
    euler_critical_kn: float = 0.0
    capacity_kn: float = 0.0
    utilization: float = 0.0
    ok: bool = True
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "length_m": round(self.length_m, 3),
            "axial_kn": round(self.axial_kn, 2),
            "slenderness": round(self.slenderness, 1),
            "euler_critical_kn": round(self.euler_critical_kn, 1),
            "capacity_kn": round(self.capacity_kn, 1),
            "utilization": round(self.utilization, 3),
            "ok": self.ok, "notes": self.notes,
        }


def column_analysis(length_m: float, axial_kn: float, e_gpa: float,
                    area_m2: float, ix_m4: float, radius_gyration_m: float,
                    f_yield_mpa: float = 0.0, f_ck_mpa: float = 0.0,
                    support: str = "PIN", safety_factor: float = 2.5) -> ColumnResult:
    """Pilar comprimido: esbeltez, pandeo de Euler y utilización (axial).

    La capacidad se limita por aplastamiento (A·f) y por pandeo
    (Ncr/γ). Utilización = N / capacidad.
    """
    if length_m <= 0 or area_m2 <= 0 or radius_gyration_m <= 0:
        raise CalculationError(
            message="El pilar exige luz, área y radio de giro positivos",
            code="ARQ-STR-017",
            context={"length_m": length_m, "area_m2": area_m2})
    if axial_kn < 0:
        raise CalculationError(
            message="La carga axial de compresión no puede ser negativa",
            code="ARQ-STR-018", context={"axial_kn": axial_kn})
    # Longitud efectiva por tipo de apoyo (Le = k·L).
    k = {"PIN": 1.0, "FIXED": 0.7, "ROLLER": 1.0, "FREE": 2.0}.get(support, 1.0)
    le = k * length_m
    slenderness = le / radius_gyration_m
    e = e_gpa * 1e9  # N/m²
    ncr_n = math.pi ** 2 * e * ix_m4 / le ** 2
    ncr_kn = ncr_n / 1000.0
    # Aplastamiento admitible del material.
    if f_yield_mpa > 0:
        f_allow = f_yield_mpa * 0.6          # acero: 0,6·fy
    elif f_ck_mpa > 0:
        f_allow = f_ck_mpa * 0.35            # hormigón: ≈0,35·fck (sin armadura)
    else:
        raise CalculationError(
            message="Se exige fy (acero) o fck (hormigón) del material",
            code="ARQ-STR-019")
    squash_kn = area_m2 * f_allow * 1000.0
    buckling_allowable_kn = ncr_kn / safety_factor
    capacity = min(squash_kn, buckling_allowable_kn)
    utilization = axial_kn / capacity if capacity > 0 else float("inf")
    return ColumnResult(
        length_m=length_m, axial_kn=axial_kn, slenderness=slenderness,
        euler_critical_kn=ncr_kn, capacity_kn=capacity,
        utilization=utilization, ok=utilization <= 1.0 + 1e-9,
        notes=["Gobierna el pandeo" if buckling_allowable_kn < squash_kn
               else "Gobierna el aplastamiento"])


# -- Torsión elástica (sección circular) ----------------------------------------------

def circular_torsion_capacity_mpa(diameter_mm: float,
                                  tau_allow_mpa: float) -> float:
    """Par torsor admisible en kN·m de una sección circular (torsión).

    T = τ · Ip / r con Ip = π·d⁴/32.
    """
    if diameter_mm <= 0:
        raise CalculationError(
            message="El diámetro debe ser positivo",
            code="ARQ-STR-020", context={"diameter_mm": diameter_mm})
    d_m = diameter_mm / 1000.0
    ip = math.pi * d_m ** 4 / 32.0
    t_nm = tau_allow_mpa * 1e6 * ip / (d_m / 2.0)
    return t_nm / 1000.0


# -- Cerchas: método de los nudos -------------------------------------------------------

@dataclass
class TrussResult:
    """Resultado del análisis de cercha (cerchas)."""

    reactions: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    member_forces: Dict[str, Tuple[str, float]] = field(default_factory=dict)  # (T/C, kN)
    max_abs_kn: float = 0.0
    ok: bool = True
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "reactions": {k: [round(v[0], 3), round(v[1], 3)]
                          for k, v in self.reactions.items()},
            "members": {k: [state, round(force, 3)]
                        for k, (state, force) in self.member_forces.items()},
            "max_abs_kn": round(self.max_abs_kn, 3),
            "ok": self.ok, "reason": self.reason,
        }


def _gauss_solve(matrix: List[List[float]], rhs: List[float]) -> List[float]:
    """Eliminación gaussiana con pivoteo parcial (determinista)."""
    n = len(rhs)
    augmented = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot_row][col]) < 1e-12:
            raise CalculationError(
                message="Sistema singular: la cercha es inestable o hipostática",
                code="ARQ-STR-021", context={"pivot": col})
        augmented[col], augmented[pivot_row] = augmented[pivot_row], augmented[col]
        pivot = augmented[col][col]
        for j in range(col, n + 1):
            augmented[col][j] /= pivot
        for r in range(n):
            if r == col:
                continue
            factor = augmented[r][col]
            if abs(factor) < 1e-15:
                continue
            for j in range(col, n + 1):
                augmented[r][j] -= factor * augmented[col][j]
    return [augmented[i][n] for i in range(n)]


def truss_solve(nodes: Dict[str, Tuple[float, float]],
                members: Sequence[Tuple[str, str, str]],
                supports: Dict[str, Tuple[str, str]],
                joint_loads: Dict[str, Tuple[float, float]]) -> TrussResult:
    """Cercha plana por el método de los nudos (cerchas).

    nodes:      id → (x, y) en m
    members:    (id, nodo_a, nodo_b)
    supports:   nodo_id → ("PIN"|"ROLLER", eje_libre "x"|"y")
                PIN libera 0 reacciones (2 componentes), ROLLER libera el eje.
    joint_loads: nodo_id → (Fx, Fy) en kN
    """
    node_ids = list(nodes.keys())
    n = len(node_ids)
    m = len(members)
    # Incógnitas: fuerzas de barras (m) + reacciones (pin 2, roller 1).
    reaction_dofs: List[Tuple[str, str]] = []
    for node_id, (kind, axis) in supports.items():
        if kind == "PIN":
            reaction_dofs.append((node_id, "x"))
            reaction_dofs.append((node_id, "y"))
        elif kind == "ROLLER":
            reaction_dofs.append((node_id, "y" if axis == "y" else "x"))
        else:
            raise CalculationError(
                message=f"Apoyo de cercha no soportado: {kind}",
                code="ARQ-STR-022", context={"kind": kind})
    total = m + len(reaction_dofs)
    if total != 2 * n:
        return TrussResult(ok=False, reason=(
            f"Cercha estáticamente indeterminada o inestable: "
            f"{total} incógnitas para {2 * n} ecuaciones"))

    index = {nid: i for i, nid in enumerate(node_ids)}
    matrix = [[0.0] * total for _ in range(2 * n)]
    rhs = [0.0] * (2 * n)

    # Columnas de barras: contribución cos/sin al equilibrio del nudo.
    for m_idx, (mid, na, nb) in enumerate(members):
        (xa, ya), (xb, yb) = nodes[na], nodes[nb]
        length = math.hypot(xb - xa, yb - ya)
        if length < 1e-9:
            raise CalculationError(
                message=f"Barra {mid} de longitud nula",
                code="ARQ-STR-023", context={"member": mid})
        cos_ = (xb - xa) / length
        sin_ = (yb - ya) / length
        matrix[index[na] * 2][m_idx] += cos_        # ΣFx nudo a
        matrix[index[na] * 2 + 1][m_idx] += sin_    # ΣFy nudo a
        matrix[index[nb] * 2][m_idx] += -cos_
        matrix[index[nb] * 2 + 1][m_idx] += -sin_

    # Columnas de reacciones.
    for r_idx, (node_id, axis) in enumerate(reaction_dofs):
        dof = index[node_id] * 2 + (0 if axis == "x" else 1)
        matrix[dof][m + r_idx] = 1.0

    # Cargas exteriores van al lado derecho (equilibrio: A·u + P = 0).
    for node_id, (fx, fy) in joint_loads.items():
        rhs[index[node_id] * 2] = -fx
        rhs[index[node_id] * 2 + 1] = -fy

    solution: List[float]
    try:
        solution = _gauss_solve(matrix, rhs)
    except CalculationError as exc:
        return TrussResult(ok=False, reason=str(exc.message) if hasattr(exc, 'message') else str(exc))
    result = TrussResult()
    for r_idx, (node_id, axis) in enumerate(reaction_dofs):
        value = solution[m + r_idx]
        current = result.reactions.get(node_id, (0.0, 0.0))
        result.reactions[node_id] = (
            (value, current[1]) if axis == "x" else (current[0], value))
    for m_idx, (mid, _na, _nb) in enumerate(members):
        force = solution[m_idx]
        state = "T" if force >= 0 else "C"   # T tensión, C compresión
        result.member_forces[mid] = (state, abs(force))
        result.max_abs_kn = max(result.max_abs_kn, abs(force))
    return result


def truss_utilization(member_forces: Dict[str, Tuple[str, float]],
                      area_m2: float, f_allow_mpa: float
                      ) -> Dict[str, float]:
    """Utilización por barra: |N| / (A·f_adm) (utilization)."""
    capacity_kn = area_m2 * f_allow_mpa * 1000.0
    if capacity_kn <= 0:
        raise CalculationError(
            message="La capacidad de la barra debe ser positiva",
            code="ARQ-STR-024",
            context={"area_m2": area_m2, "f_allow_mpa": f_allow_mpa})
    return {mid: abs(force) / capacity_kn
            for mid, (_state, force) in member_forces.items()}


# -- Uniones: pernos y soldadura ---------------------------------------------------

def bolt_group_shear_kn(n_bolts: int, d_mm: float,
                        tau_allow_mpa: float = E_ALLOWABLE_SHEAR_STEEL_MPA) -> float:
    """Capacidad a cortante de un grupo de pernos (connections/bolt)."""
    if n_bolts <= 0 or d_mm <= 0:
        raise CalculationError(
            message="El grupo de pernos exige número y diámetro positivos",
            code="ARQ-STR-025",
            context={"n_bolts": n_bolts, "d_mm": d_mm})
    area_m2 = math.pi * (d_mm / 1000.0) ** 2 / 4.0
    return n_bolts * area_m2 * tau_allow_mpa * 1000.0


def weld_capacity_kn(length_mm: float, throat_mm: float,
                     fw_mpa: float = WELD_STRENGTH_N_MM2) -> float:
    """Capacidad de una soldadura de cordón (connections/weld)."""
    if length_mm <= 0 or throat_mm <= 0:
        raise CalculationError(
            message="La soldadura exige longitud y garganta positivas",
            code="ARQ-STR-026",
            context={"length_mm": length_mm, "throat_mm": throat_mm})
    # mm² · N/mm² = N; N → kN.
    return length_mm * throat_mm * fw_mpa / 1000.0


def steel_weight_kg(weight_kg_m: float, length_m: float) -> float:
    """Peso de acero de un miembro (peso)."""
    if length_m < 0:
        raise CalculationError(
            message="La longitud no puede ser negativa",
            code="ARQ-STR-027", context={"length_m": length_m})
    return weight_kg_m * length_m


__all__ = [
    "SectionProperties", "BeamResult", "ColumnResult", "TrussResult",
    "section_properties", "beam_analysis", "column_analysis",
    "circular_torsion_capacity_mpa", "truss_solve", "truss_utilization",
    "bolt_group_shear_kn", "weld_capacity_kn", "steel_weight_kg",
    "E_ALLOWABLE_SHEAR_STEEL_MPA", "WELD_STRENGTH_N_MM2",
]
