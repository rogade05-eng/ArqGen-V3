"""Multiobjective optimization engine (spec section 19) — pure functions.

FASE 35 - OPTIMIZATION. Design principle taken literally from the spec:

    "No habrá un único 'score mágico'. Se conservarán los valores de
     cada objetivo."

Therefore the engine:

    * evaluates a design variant against a set of named objectives
      (AREA, COST, DISTANCE, ...) and keeps every objective value;
    * compares two variants objective by objective (deltas);
    * computes the Pareto front of a set of variants with explicit
      directions (minimize / maximize) — dominance is a partial order,
      never a weighted sum.

Deterministic: ties broken by variant name ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.errors import DomainError

# Spec 19: possible objectives of the multiobjective engine.
OBJECTIVES: tuple[str, ...] = (
    "AREA",          # m2 construidos / de locales
    "COST",          # presupuesto total
    "DISTANCE",      # recorridos medios (m)
    "CIRCULATION",   # área/longitud de circulación
    "LIGHTING",      # iluminación natural (ratio vano/superficie)
    "VENTILATION",   # ventilación natural (ratio aperturas/superficie)
    "PRIVACY",       # privacidad entre locales
    "ACCESSIBILITY", # accesibilidad (anchos de puertas, etc.)
    "SECURITY",      # cobertura de seguridad
    "MAINTENANCE",   # facilidad de mantenimiento
    "MATERIAL",      # volumen de material (m3)
    "COMPLEXITY",    # complejidad del diseño (objetos, aristas)
)

# Higher-is-better objectives; everything else is minimized.
MAXIMIZE: frozenset = frozenset({
    "AREA", "LIGHTING", "VENTILATION", "PRIVACY", "ACCESSIBILITY",
    "SECURITY", "MAINTENANCE",
})

DIRECTIONS: Dict[str, str] = {
    obj: ("maximize" if obj in MAXIMIZE else "minimize") for obj in OBJECTIVES
}


@dataclass
class Variant:
    """One design variant with its objective values (no global score)."""

    name: str
    objectives: Dict[str, float] = field(default_factory=dict)
    notes: str = ""

    def validate(self) -> None:
        if not self.name:
            raise DomainError(
                message="La variante exige un nombre", code="ARQ-OPT-001")
        unknown = set(self.objectives) - set(OBJECTIVES)
        if unknown:
            raise DomainError(
                message="Objetivos desconocidos: " + ", ".join(sorted(unknown)),
                code="ARQ-OPT-002",
                context={"unknown": sorted(unknown),
                         "allowed": list(OBJECTIVES)})


def dominates(a: Variant, b: Variant) -> bool:
    """True if ``a`` is at least as good in every objective and strictly
    better in at least one (Pareto dominance, spec 19: no magic score)."""
    a.validate()
    b.validate()
    shared = [o for o in OBJECTIVES
              if o in a.objectives and o in b.objectives]
    if not shared:
        return False
    at_least_as_good = True
    strictly_better = False
    for obj in shared:
        if obj in MAXIMIZE:
            if a.objectives[obj] < b.objectives[obj]:
                at_least_as_good = False
            if a.objectives[obj] > b.objectives[obj]:
                strictly_better = True
        else:
            if a.objectives[obj] > b.objectives[obj]:
                at_least_as_good = False
            if a.objectives[obj] < b.objectives[obj]:
                strictly_better = True
    return at_least_as_good and strictly_better


def pareto_front(variants: List[Variant]) -> List[str]:
    """Names of the non-dominated variants (the Pareto front).

    Deterministic order: the input order is preserved for the front,
    and ties (mutual domination impossible) keep input order.
    """
    for v in variants:
        v.validate()
    front: List[str] = []
    for candidate in variants:
        dominated = any(dominates(other, candidate)
                        for other in variants if other is not candidate)
        if not dominated:
            front.append(candidate.name)
    return front


def compare_solutions(a: Variant, b: Variant) -> Dict[str, Dict[str, float]]:
    """Objective-by-objective comparison: value_a, value_b, delta (b-a).

    Positive delta on a minimized objective means ``a`` is better;
    on a maximized objective it means ``b`` is better.
    """
    a.validate()
    b.validate()
    result: Dict[str, Dict[str, float]] = {}
    for obj in OBJECTIVES:
        if obj in a.objectives and obj in b.objectives:
            va = float(a.objectives[obj])
            vb = float(b.objectives[obj])
            result[obj] = {
                "a": va, "b": vb, "delta": round(vb - va, 6),
                "direction": DIRECTIONS[obj],
            }
    return result


def normalize_objectives(variants: List[Variant]) -> Dict[str, Dict[str, float]]:
    """Per-objective min/max across variants (for reports, not for scoring)."""
    stats: Dict[str, Dict[str, float]] = {}
    for obj in OBJECTIVES:
        values = [float(v.objectives[obj]) for v in variants
                  if obj in v.objectives]
        if values:
            stats[obj] = {"min": min(values), "max": max(values)}
    return stats


__all__ = [
    "OBJECTIVES", "MAXIMIZE", "DIRECTIONS", "Variant", "dominates",
    "pareto_front", "compare_solutions", "normalize_objectives",
]
