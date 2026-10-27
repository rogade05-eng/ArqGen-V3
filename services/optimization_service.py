"""OptimizationService (spec sections 19, 73) — FASE 35.

Computes the objective values of the current project from model data,
builds design variants and evaluates the Pareto front. Consistent with
the spec: every objective keeps its own value; there is no global score.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.errors import DomainError
from engines.optimization_engine import (
    DIRECTIONS, OBJECTIVES, Variant, compare_solutions, dominates,
    normalize_objectives, pareto_front,
)
from services.context import ProjectContext

MIN_DOOR_WIDTH_M = 0.9  # reference clear width for accessibility ratio


class OptimizationService:
    """Facade of the multiobjective engine (spec 19)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    # ------------------------------------------------------------------
    # Current project evaluation
    # ------------------------------------------------------------------
    def evaluate_current(self) -> Variant:
        """Evaluate the 12 objectives of spec 19 on the open project."""
        pid = self.ctx.project.id
        spaces = self.ctx.architecture.list("SPACE", pid)
        walls = self.ctx.architecture.list("WALL", pid)
        openings = [o for o in self.ctx.architecture.list("OPENING", pid)
                    if o.kind in ("DOOR", "WINDOW")]
        relationships = self.ctx.architecture.list("SPACE_RELATIONSHIP", pid)

        total_area = 0.0
        for s in spaces:
            try:
                total_area += s.area_m2()
            except Exception:
                pass

        wall_volume = 0.0
        wall_length = 0.0
        for w in walls:
            length = ((w.end[0] - w.start[0]) ** 2
                      + (w.end[1] - w.start[1]) ** 2) ** 0.5
            wall_length += length
            wall_volume += length * w.height_m * w.thickness_m

        window_area = 0.0
        for o in openings:
            if o.kind == "WINDOW":
                window_area += o.width_m * o.height_m

        # Circulation proxy: shared frontiers between spaces (adjacency).
        circulation = 0.0
        for rel in relationships:
            if rel.kind in ("ADJACENT", "CONNECTED", "ACCESS"):
                circulation += float(rel.metadata.get("boundary_length", 0.0))

        # Distance proxy: mean relationship distance stored by the spatial engine.
        distances = [float(r.metadata.get("distance", 0.0))
                     for r in relationships
                     if r.metadata.get("distance") is not None
                     and float(r.metadata.get("distance", 0.0)) > 0]
        mean_distance = (sum(distances) / len(distances)) if distances else 0.0

        # Privacidad: separación acústica registrada entre locales.
        privacy = sum(1 for r in relationships
                      if r.kind == "acoustically_separated_from")
        door_widths = [o.width_m for o in openings if o.kind == "DOOR"]
        accessibility = ((sum(door_widths) / len(door_widths)) / MIN_DOOR_WIDTH_M
                         if door_widths else 0.0)

        security_nodes = 0
        for network in self.ctx.installations.list("NETWORK", pid):
            if network.system in ("CCTV", "FIRE_ALARM", "INTRUSION",
                                  "ACCESS_CONTROL", "PERIMETER"):
                security_nodes += len(self.ctx.installations.nodes_of(network.id))
        security = (security_nodes / len(spaces)) if spaces else 0.0

        # Maintenance proxy: validated networks over total networks.
        networks = self.ctx.installations.list("NETWORK", pid)
        maintained = 0
        if networks:
            from services.installations_service import InstallationsService
            installations = InstallationsService(self.ctx)
            for network in networks:
                try:
                    result = installations.validate_network(network.code)
                except Exception:
                    continue
                if result.get("status") in ("VALID", "VALID_WITH_WARNINGS"):
                    maintained += 1
        maintenance = (maintained / len(networks)) if networks else 0.0

        structure_volume = 0.0
        for element in self.ctx.structure.list("ELEMENT", pid):
            structure_volume += float(element.metadata.get("volume_m3", 0.0))

        complexity = (len(spaces) + len(walls) + len(openings)
                      + len(relationships)
                      + self.ctx.installations.count("NODE", pid)
                      + self.ctx.installations.count("SEGMENT", pid)
                      + self.ctx.structure.count("ELEMENT", pid))

        budget_total = self._budget_total()

        objectives: Dict[str, float] = {
            "AREA": round(total_area, 3),
            "COST": round(budget_total, 2),
            "DISTANCE": round(mean_distance, 3),
            "CIRCULATION": round(circulation, 3),
            "LIGHTING": round((window_area / total_area) if total_area else 0.0, 4),
            "VENTILATION": round((window_area / total_area) if total_area else 0.0, 4),
            "PRIVACY": float(privacy),
            "ACCESSIBILITY": round(accessibility, 4),
            "SECURITY": round(security, 4),
            "MAINTENANCE": round(maintenance, 4),
            "MATERIAL": round(wall_volume + structure_volume, 3),
            "COMPLEXITY": float(complexity),
        }
        variant = Variant(name="CURRENT", objectives=objectives,
                          notes="Valores del proyecto abierto")
        variant.validate()
        return variant

    def variant_from_dict(self, data: Dict[str, Any]) -> Variant:
        variant = Variant(name=str(data.get("name", "")),
                          objectives={k: float(v) for k, v in
                                      (data.get("objectives") or {}).items()},
                          notes=str(data.get("notes", "")))
        variant.validate()
        return variant

    def load_variants(self, path: str,
                      with_current: bool = False) -> List[Variant]:
        """Load named variants from a JSON file (deterministic order)."""
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data = data.get("variants", [])
        variants = [self.variant_from_dict(item) for item in data]
        if with_current:
            variants.append(self.evaluate_current())
        return variants

    # ------------------------------------------------------------------
    # Pareto / comparison
    # ------------------------------------------------------------------
    def pareto(self, variants: List[Variant]) -> Dict[str, Any]:
        if not variants:
            raise DomainError(
                message="No hay variantes para evaluar",
                code="ARQ-OPT-003",
                suggested_action="Añada variantes al archivo JSON.")
        front = pareto_front(variants)
        dominated: Dict[str, str] = {}
        for candidate in variants:
            if candidate.name in front:
                continue
            for other in variants:
                if other is candidate:
                    continue
                if dominates(other, candidate):
                    dominated[candidate.name] = other.name
                    break
        return {
            "variants": [v.name for v in variants],
            "pareto_front": front,
            "dominated_by": dominated,
            "objectives": {o: DIRECTIONS[o] for o in OBJECTIVES
                           if any(o in v.objectives for v in variants)},
            "ranges": normalize_objectives(variants),
        }

    def compare(self, a: Variant, b: Variant) -> Dict[str, Any]:
        return {
            "a": a.name, "b": b.name,
            "comparison": compare_solutions(a, b),
            "a_dominates_b": dominates(a, b),
            "b_dominates_a": dominates(b, a),
        }

    # ------------------------------------------------------------------
    def _budget_total(self) -> float:
        try:
            from services.budget_service import BudgetService
            budget = BudgetService(self.ctx).latest_budget()
            return float(budget.get("total_cost", 0.0)) if budget else 0.0
        except Exception:
            return 0.0


__all__ = ["OptimizationService", "OBJECTIVES"]
