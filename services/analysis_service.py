"""Analysis services: rules, validation and spatial relations (spec 12-23, 82)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.rules.models import Rule, Ruleset
from core.validation.results import Finding, ValidationResult, ValidationStatus
from engines.spatial_engine import SpatialEngine
from services.context import ProjectContext


class RuleService:
    """Rules are data: loaded from resources/rulesets and persisted (spec 12-13)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    def install_ruleset(self, ruleset: Ruleset, activate: bool = True) -> Ruleset:
        """Persist a ruleset; optionally make it the project's active one."""
        self.ctx.rules_repo.save_ruleset(ruleset)
        if activate and not self.ctx.project.ruleset_code:
            self.ctx.project.ruleset_code = ruleset.code
            self.ctx.project.touch()
            self.ctx.architecture.projects.save(self.ctx.project)
        self.ctx.emit("RULE_CHANGED", {"ruleset": ruleset.code, "rules": len(ruleset.rules)})
        return ruleset

    def load_ruleset_from_resources(self, code: str) -> Ruleset:
        from app.paths import resource_path
        path = resource_path("rulesets", f"{code}.json")
        if not os.path.exists(path):
            from core.errors import RuleError
            raise RuleError(
                message=f"Ruleset no encontrado en recursos: {code}",
                code="ARQ-RUL-020",
                context={"path": path},
                suggested_action="Use un ruleset incluido o copie el suyo a resources/rulesets.",
            )
        with open(path, "r", encoding="utf-8") as fh:
            import json
            data = json.load(fh)
        ruleset = Ruleset.from_dict(data)
        return self.install_ruleset(ruleset)

    def active_ruleset(self) -> Optional[Ruleset]:
        code = self.ctx.project.ruleset_code
        if not code:
            return None
        return self.ctx.rules_repo.load_ruleset(code)

    def list_installed(self) -> List[str]:
        return self.ctx.rules_repo.list_rulesets()


class ValidationService:
    """Built-in geometric/DNA validators + ruleset rules (spec 82)."""

    def __init__(self, context: ProjectContext, spatial: Optional[SpatialEngine] = None) -> None:
        self.ctx = context
        self.spatial = spatial or SpatialEngine(dna_registry=getattr(context, 'dna_registry', None))

    def validate_project(self) -> ValidationResult:
        result = ValidationResult()
        project_id = self.ctx.project.id
        arch = self.ctx.architecture

        self._check_duplicate_codes(result)
        self._check_walls(result)
        self._check_spaces(result)
        self._check_openings(result)
        self._run_ruleset(result)
        result.finalize()
        return result

    # -- built-in validators ------------------------------------------------
    def _check_duplicate_codes(self, result: ValidationResult) -> None:
        arch = self.ctx.architecture
        seen: Dict[str, str] = {}
        for entity_type in ("LEVEL", "ZONE", "SPACE", "WALL", "DOOR", "WINDOW"):
            for entity in arch.list(entity_type, self.ctx.project.id):
                if not entity.code:
                    continue
                if entity.code in seen:
                    result.add(Finding(
                        severity="ERROR", code="DUP_CODE",
                        message=f"Código duplicado '{entity.code}' entre {seen[entity.code]} y {entity_type}",
                        object_id=entity.id, object_type=entity_type))
                seen[entity.code] = entity_type

    def _check_walls(self, result: ValidationResult) -> None:
        for wall in self.ctx.architecture.list("WALL", self.ctx.project.id):
            if wall.thickness_m <= 0:
                result.add(Finding("ERROR", "WALL_THICKNESS",
                                   f"Muro {wall.code}: espesor no positivo",
                                   wall.id, "WALL"))
            if wall.height_m <= 0:
                result.add(Finding("ERROR", "WALL_HEIGHT",
                                   f"Muro {wall.code}: altura no positiva",
                                   wall.id, "WALL"))
            if wall.length_m < 0.05:
                result.add(Finding("WARNING", "WALL_SHORT",
                                   f"Muro {wall.code}: longitud menor que 5 cm",
                                   wall.id, "WALL"))

    def _check_spaces(self, result: ValidationResult) -> None:
        from core.geometry import engine as ge
        from core.geometry.primitives import Polygon
        for space in self.ctx.architecture.list("SPACE", self.ctx.project.id):
            if len(space.boundary) < 3:
                result.add(Finding("ERROR", "SPACE_BOUNDARY",
                                   f"Local {space.code or space.name}: contorno inválido",
                                   space.id, "SPACE"))
                continue
            if abs(ge.shoelace_area(space.polygon().points)) < 1e-9:
                result.add(Finding("ERROR", "SPACE_DEGENERATE",
                                   f"Local {space.code or space.name}: área nula",
                                   space.id, "SPACE"))
                continue
            dna = self.spatial.dna.get(space.space_type)
            if dna and dna.minimum_area is not None and space.area_m2() < dna.minimum_area:
                result.add(Finding(
                    "WARNING", "SPACE_MIN_AREA",
                    f"Local {space.code or space.name} ({space.space_type}): "
                    f"área {space.area_m2():.2f} m2 < mínimo DNA {dna.minimum_area:.2f} m2",
                    space.id, "SPACE"))

    def _check_openings(self, result: ValidationResult) -> None:
        for opening in self.ctx.architecture.list("OPENING", self.ctx.project.id):
            wall = self.ctx.architecture.get("WALL", opening.wall_id)
            if wall is None:
                result.add(Finding("ERROR", "ORPHAN_OPENING",
                                   f"Vano {opening.code}: muro inexistente",
                                   opening.id, opening.ENTITY_TYPE))
                continue
            if opening.offset_m + opening.width_m > wall.length_m + 1e-6:
                result.add(Finding("ERROR", "OPENING_OUT_OF_WALL",
                                   f"Vano {opening.code} fuera del muro {wall.code}",
                                   opening.id, opening.ENTITY_TYPE))
            if opening.sill_height_m + opening.height_m > wall.height_m + 1e-6:
                result.add(Finding("ERROR", "OPENING_TOO_TALL",
                                   f"Vano {opening.code} excede la altura del muro {wall.code}",
                                   opening.id, opening.ENTITY_TYPE))

    # -- ruleset rules --------------------------------------------------------
    def _run_ruleset(self, result: ValidationResult) -> None:
        ruleset = RuleService(self.ctx).active_ruleset()
        if not ruleset:
            return
        facts_by_object = self._collect_facts()
        for rule in ruleset.rules:
            targets = self._targets_for(rule, facts_by_object)
            for object_id, facts in targets:
                try:
                    variables = dict(facts)
                    variables.update(rule.parameters)
                    outcome = rule.compiled.evaluate(variables)
                except Exception as exc:
                    result.add(Finding("WARNING", "RULE_SKIPPED",
                                       f"Regla {rule.code} no evaluable para el objeto: {exc}",
                                       object_id, facts.get("type", "")))
                    continue
                if outcome:
                    result.add(Finding(
                        rule.severity.value, rule.code, rule.message, object_id,
                        facts.get("type", "")))

    def _collect_facts(self) -> Dict[str, Dict[str, Any]]:
        """Facts per object id for rule evaluation."""
        facts: Dict[str, Dict[str, Any]] = {}
        arch = self.ctx.architecture
        for wall in arch.list("WALL", self.ctx.project.id):
            facts[wall.id] = {"type": "WALL", "code": wall.code, "length": wall.length_m,
                              "height": wall.height_m, "thickness": wall.thickness_m,
                              "structural": 1.0 if wall.structural else 0.0}
        for opening in arch.list("OPENING", self.ctx.project.id):
            facts[opening.id] = {"type": opening.ENTITY_TYPE, "code": opening.code,
                                 "width": opening.width_m, "height": opening.height_m,
                                 "sill": opening.sill_height_m, "offset": opening.offset_m}
        for space in arch.list("SPACE", self.ctx.project.id):
            facts[space.id] = {"type": "SPACE", "code": space.code,
                               "name": space.name, "area": space.area_m2(),
                               "perimeter": space.perimeter_m(), "space_type": space.space_type}
        return facts

    def _targets_for(self, rule: Rule, facts_by_object: Dict[str, Dict[str, Any]]):
        if rule.applies_to == "*":
            return list(facts_by_object.items())
        return [(oid, f) for oid, f in facts_by_object.items() if f.get("type") == rule.applies_to]


class SpatialService:
    """Adjacency computation persisted as relationships (spec 8, 16, 23)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context
        self.engine = SpatialEngine(dna_registry=getattr(context, "dna_registry", None))

    def recompute_adjacencies(self) -> List[Dict[str, Any]]:
        """Geometry-sourced adjacent_to relationships, idempotent."""
        spaces = self.ctx.architecture.list("SPACE", self.ctx.project.id)
        adjacencies = self.engine.compute_adjacencies(spaces)
        code_by_name = {}
        for space in spaces:
            code_by_name[space.code or space.name] = space.id
        by_id = {s.id: s for s in spaces}

        existing = {}
        for rel in self.ctx.architecture.list("SPACE_RELATIONSHIP", self.ctx.project.id):
            if rel.source == "geometry":
                existing[(rel.from_space_id, rel.to_space_id, rel.kind)] = rel

        results: List[Dict[str, Any]] = []
        for adjacency in adjacencies:
            a_id = code_by_name.get(adjacency.space_a) or self._space_id_by_code(adjacency.space_a, by_id)
            b_id = code_by_name.get(adjacency.space_b) or self._space_id_by_code(adjacency.space_b, by_id)
            if not a_id or not b_id:
                continue
            key = (a_id, b_id, "adjacent_to")
            if key in existing:
                del existing[key]
                continue
            rel_key = (b_id, a_id, "adjacent_to")
            if rel_key in existing:
                del existing[rel_key]
                continue
            from domain.model import SpaceRelationship
            rel = SpaceRelationship(project_id=self.ctx.project.id, from_space_id=a_id,
                                    to_space_id=b_id, kind="adjacent_to", source="geometry")
            self.ctx.architecture.save(rel)
            results.append({"from": adjacency.space_a, "to": adjacency.space_b,
                            "shared_m": round(adjacency.shared_length_m, 3)})
        # Remove stale geometry relationships
        for rel in existing.values():
            self.ctx.architecture.delete("SPACE_RELATIONSHIP", rel.id)
        return results

    @staticmethod
    def _space_id_by_code(code: str, by_id) -> str:
        for space in by_id.values():
            if space.code == code or space.name == code:
                return space.id
        return ""

    def adjacency_report(self) -> List[str]:
        spaces = self.ctx.architecture.list("SPACE", self.ctx.project.id)
        adjacencies = self.engine.compute_adjacencies(spaces)
        return [a.explanation for a in adjacencies]

    def dna_findings(self) -> List[str]:
        spaces = self.ctx.architecture.list("SPACE", self.ctx.project.id)
        adjacencies = self.engine.compute_adjacencies(spaces)
        findings: List[str] = []
        for space in spaces:
            findings.extend(self.engine.analyze_space(space, adjacencies))
        return findings


__all__ = ["RuleService", "ValidationService", "SpatialService"]
