"""QuantityService (QTO) with incremental recalculation (spec 51, 52, 74, 102)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.calculations.contracts import CalculationMode, CalculationResult, CalculationStatus
from core.errors import CalculationError
from domain.installations import InstallNode, InstallSegment
from domain.model import Level, Opening, Space, Wall
from engines.quantity_engine import (
    DEFAULT_FORMULAS, DESIGN_FORMULAS, INSTALL_FORMULAS, SECURITY_FORMULAS,
    STRUCT_FORMULAS, FormulaSpec, QuantityEngine,
)
from services.context import ProjectContext

CALC_TYPE = "QTO"


@dataclass
class QTOStats:
    computed: int = 0
    cached: int = 0
    invalidated: int = 0
    duration_ms: float = 0.0
    objects_processed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "computed": self.computed, "cached": self.cached,
            "invalidated": self.invalidated, "duration_ms": round(self.duration_ms, 2),
            "objects_processed": self.objects_processed,
        }


class QuantityService:
    """Geometry → Measurement → Formula → Quantity → Waste → Final.

    Incremental: only stale objects are recomputed; fresh cached results
    are reused (spec 74: never recalculate the whole project).
    """

    def __init__(self, context: ProjectContext, engine: Optional[QuantityEngine] = None) -> None:
        self.ctx = context
        self.engine = engine or QuantityEngine()

    def install_default_formulas(self) -> int:
        count = 0
        for spec in DEFAULT_FORMULAS:
            self.ctx.formulas_repo.save(
                code=spec.code, target_type=spec.target_type, expression=spec.expression,
                unit=spec.unit, description=spec.description,
                waste_factor=spec.waste_factor, variables=[], version=spec.version,
                source=spec.source or "ARQ GEN")
            count += 1
        for spec in INSTALL_FORMULAS:
            self.ctx.formulas_repo.save(
                code=spec.code, target_type=spec.target_type, expression=spec.expression,
                unit=spec.unit, description=spec.description,
                waste_factor=spec.waste_factor, variables=[], version=spec.version,
                source=spec.source or "ARQ GEN", condition=spec.condition)
            count += 1
        for spec in STRUCT_FORMULAS:
            self.ctx.formulas_repo.save(
                code=spec.code, target_type=spec.target_type, expression=spec.expression,
                unit=spec.unit, description=spec.description,
                waste_factor=spec.waste_factor, variables=[], version=spec.version,
                source=spec.source or "ARQ GEN", condition=spec.condition)
            count += 1
        for spec in SECURITY_FORMULAS:
            self.ctx.formulas_repo.save(
                code=spec.code, target_type=spec.target_type, expression=spec.expression,
                unit=spec.unit, description=spec.description,
                waste_factor=spec.waste_factor, variables=[], version=spec.version,
                source=spec.source or "ARQ GEN", condition=spec.condition)
            count += 1
        for spec in DESIGN_FORMULAS:
            self.ctx.formulas_repo.save(
                code=spec.code, target_type=spec.target_type, expression=spec.expression,
                unit=spec.unit, description=spec.description,
                waste_factor=spec.waste_factor, variables=[], version=spec.version,
                source=spec.source or "ARQ GEN", condition=spec.condition)
            count += 1
        return count

    def compute_all(self, mode: CalculationMode = CalculationMode.BALANCED) -> QTOStats:
        started = time.perf_counter()
        stats = QTOStats()
        # Count rows that arrived stale (invalidated by change events).
        stats.invalidated = len(self.ctx.quantities_repo.all(self.ctx.project.id, only_stale=True))
        project_id = self.ctx.project.id
        walls = self.ctx.architecture.list("WALL", project_id)
        openings = self.ctx.architecture.list("OPENING", project_id)
        spaces = self.ctx.architecture.list("SPACE", project_id)
        levels = {l.id: l for l in self.ctx.architecture.list("LEVEL", project_id)}
        openings_by_wall: Dict[str, List[Opening]] = {}
        for opening in openings:
            openings_by_wall.setdefault(opening.wall_id, []).append(opening)

        for wall in walls:
            self._compute_object(
                "WALL", wall.id, wall.code, wall.revision,
                lambda w=wall, o=openings_by_wall.get(wall.id, []): self.engine.measure_wall(w, o),
                stats, mode)
        for opening in openings:
            self._compute_object(
                "OPENING", opening.id, opening.code, opening.revision,
                lambda o=opening: self.engine.measure_opening(o), stats, mode)
        for space in spaces:
            level = levels.get(space.level_id)
            height = level.height_m if level else 3.0
            self._compute_object(
                "SPACE", space.id, space.code, space.revision,
                lambda s=space, h=height: self.engine.measure_space(s, h), stats, mode)

        # Installations (spec 24): segments and device nodes feed QTO too.
        # The network system travels with each object so the discipline
        # flags (is_gas, is_telecom_cond, is_detention, ...) are exact.
        segments: List[InstallSegment] = []
        nodes: List[InstallNode] = []
        segment_systems: Dict[str, str] = {}
        node_systems: Dict[str, str] = {}
        for network in self.ctx.installations.list("NETWORK", project_id):
            for segment in self.ctx.installations.segments_of(network.id):
                segments.append(segment)
                segment_systems[segment.id] = network.system
            for node in self.ctx.installations.nodes_of(network.id):
                nodes.append(node)
                node_systems[node.id] = network.system
        for segment in segments:
            system = segment_systems.get(segment.id, "")
            self._compute_object(
                "SEGMENT", segment.id, segment.code, segment.revision,
                lambda s=segment, sy=system: self.engine.measure_segment(s, sy), stats, mode)
        for node in nodes:
            system = node_systems.get(node.id, "")
            self._compute_object(
                "NODE", node.id, node.code, node.revision,
                lambda n=node, sy=system: self.engine.measure_node(n, sy), stats, mode)

        # Structure (spec 33-34): linear elements feed QTO (concrete volume,
        # steel weight, formwork). Measurements reuse the section properties.
        elements = self.ctx.structure.list("ELEMENT", project_id)
        for element in elements:
            self._compute_object(
                "ELEMENT", element.id, element.code, element.revision,
                lambda e=element: self._measure_element(e), stats, mode)

        # Concepción de espacios (v3.15.0): mobiliario, cubiertas, rampas
        # y barandillas entran al mismo pipeline incremental de QTO.
        furniture = self.ctx.architecture.list("FURNITURE", project_id)
        for piece in furniture:
            self._compute_object(
                "FURNITURE", piece.id, piece.code, piece.revision,
                lambda p=piece: self.engine.measure_furniture(p), stats, mode)
        roofs = self.ctx.architecture.list("ROOF", project_id)
        for roof in roofs:
            self._compute_object(
                "ROOF", roof.id, roof.code, roof.revision,
                lambda r=roof: self.engine.measure_roof(r), stats, mode)
        ramps = self.ctx.architecture.list("RAMP", project_id)
        for ramp in ramps:
            self._compute_object(
                "RAMP", ramp.id, ramp.code, ramp.revision,
                lambda r=ramp: self.engine.measure_ramp(r), stats, mode)
        handrails = self.ctx.architecture.list("HANDRAIL", project_id)
        for rail in handrails:
            self._compute_object(
                "HANDRAIL", rail.id, rail.code, rail.revision,
                lambda r=rail: self.engine.measure_handrail(r), stats, mode)
        # Ascensores y fachada (v3.18.0): huecos, parasoles y pieles
        # entran al mismo pipeline incremental de QTO.
        elevators = self.ctx.architecture.list("ELEVATOR", project_id)
        for ascensor in elevators:
            self._compute_object(
                "ELEVATOR", ascensor.id, ascensor.code, ascensor.revision,
                lambda e=ascensor: self.engine.measure_elevator(e),
                stats, mode)
        parasols = self.ctx.architecture.list("PARASOL", project_id)
        for parasol in parasols:
            self._compute_object(
                "PARASOL", parasol.id, parasol.code, parasol.revision,
                lambda p=parasol: self.engine.measure_parasol(p),
                stats, mode)
        skins = self.ctx.architecture.list("SKIN", project_id)
        for piel in skins:
            self._compute_object(
                "SKIN", piel.id, piel.code, piel.revision,
                lambda s=piel: self.engine.measure_skin(s), stats, mode)
        # Escaleras por tipología (v3.19.0): peldaños, huella, desarrollo
        # y barandilla entran al mismo pipeline incremental de QTO.
        stairs = self.ctx.architecture.list("STAIR", project_id)
        for escalera in stairs:
            self._compute_object(
                "STAIR", escalera.id, escalera.code, escalera.revision,
                lambda s=escalera: self.engine.measure_stair(s),
                stats, mode)

        stats.duration_ms = (time.perf_counter() - started) * 1000.0
        stats.objects_processed = (len(walls) + len(openings) + len(spaces)
                                   + len(segments) + len(nodes) + len(elements)
                                   + len(furniture) + len(roofs)
                                   + len(ramps) + len(handrails)
                                   + len(elevators) + len(parasols)
                                   + len(skins) + len(stairs))
        return stats

    def compute_object(self, entity_type: str, entity_id: str,
                       mode: CalculationMode = CalculationMode.BALANCED) -> QTOStats:
        stats = QTOStats()
        if entity_type in ("SEGMENT", "NODE"):
            entity = self.ctx.installations.get(entity_type, entity_id)
        elif entity_type == "ELEMENT":
            entity = self.ctx.structure.get("ELEMENT", entity_id)
        elif entity_type in ("FURNITURE", "ROOF", "RAMP", "HANDRAIL",
                             "ELEVATOR", "PARASOL", "SKIN", "STAIR"):
            entity = self.ctx.architecture.get(entity_type, entity_id)
        else:
            entity = self.ctx.architecture.get(entity_type, entity_id)
        if entity is None:
            raise CalculationError(
                message=f"Objeto inexistente para QTO: {entity_id}", code="ARQ-CAL-030",
                object_ids=[entity_id])
        if entity_type == "WALL":
            openings = [o for o in self.ctx.architecture.list("OPENING", self.ctx.project.id)
                        if o.wall_id == entity_id]
            measure = lambda: self.engine.measure_wall(entity, openings)  # noqa: E731
        elif entity_type in ("DOOR", "WINDOW", "OPENING"):
            measure = lambda: self.engine.measure_opening(entity)  # noqa: E731
        elif entity_type == "SPACE":
            level = self.ctx.architecture.get("LEVEL", entity.level_id) if entity.level_id else None
            height = level.height_m if level else 3.0
            measure = lambda: self.engine.measure_space(entity, height)  # noqa: E731
        elif entity_type == "SEGMENT":
            system = self._system_of_object(entity.network_id)
            measure = lambda: self.engine.measure_segment(entity, system)  # noqa: E731
        elif entity_type == "NODE":
            system = self._system_of_object(entity.network_id)
            measure = lambda: self.engine.measure_node(entity, system)  # noqa: E731
        elif entity_type == "ELEMENT":
            measure = lambda: self._measure_element(entity)  # noqa: E731
        elif entity_type == "FURNITURE":
            measure = lambda: self.engine.measure_furniture(entity)  # noqa: E731
        elif entity_type == "ROOF":
            measure = lambda: self.engine.measure_roof(entity)  # noqa: E731
        elif entity_type == "RAMP":
            measure = lambda: self.engine.measure_ramp(entity)  # noqa: E731
        elif entity_type == "HANDRAIL":
            measure = lambda: self.engine.measure_handrail(entity)  # noqa: E731
        elif entity_type == "ELEVATOR":
            measure = lambda: self.engine.measure_elevator(entity)  # noqa: E731
        elif entity_type == "PARASOL":
            measure = lambda: self.engine.measure_parasol(entity)  # noqa: E731
        elif entity_type == "SKIN":
            measure = lambda: self.engine.measure_skin(entity)  # noqa: E731
        elif entity_type == "STAIR":
            measure = lambda: self.engine.measure_stair(entity)  # noqa: E731
        else:
            raise CalculationError(message=f"Tipo sin fórmulas QTO: {entity_type}",
                                   code="ARQ-CAL-031")
        self._compute_object(entity_type, entity.id, entity.code, entity.revision, measure,
                             stats, mode)
        return stats

    # -- internals -------------------------------------------------------------
    def _measure_element(self, element) -> Dict[str, float]:
        """Medición QTO de un elemento estructural con su sección/material."""
        from engines.structure_engine import section_properties
        section = (self.ctx.structure.get("SECTION", element.section_id)
                   if element.section_id else None)
        material = (self.ctx.structure.get("MATERIAL", element.material_id)
                    if element.material_id else None)
        area = perimeter = weight_per_m = 0.0
        if section is not None:
            props = section_properties(
                section.shape, h_mm=section.h_mm, b_mm=section.b_mm,
                tw_mm=section.tw_mm, tf_mm=section.tf_mm, d_mm=section.d_mm,
                density_kn_m3=material.density_kn_m3 if material else 78.5,
                weight_kg_m=section.weight_kg_m)
            area = props.area_m2
            weight_per_m = props.weight_kg_m
            if section.shape == "RECTANGLE":
                perimeter = 2.0 * (section.h_mm + section.b_mm) / 1000.0
            elif section.shape == "CIRCLE":
                perimeter = section.d_mm * 3.141592653589793 / 1000.0
            else:
                perimeter = 2.0 * (section.h_mm + section.b_mm) / 1000.0
        return self.engine.measure_element(
            element, section_area_m2=area, perimeter_form_m=perimeter,
            steel_weight_kg=weight_per_m * element.length_m,
            material_kind=material.kind if material else "")

    def _system_of_object(self, network_id: str) -> str:
        """Sistema de la red a la que pertenece un objeto de instalaciones."""
        network = self.ctx.installations.get("NETWORK", network_id)
        return network.system if network else ""

    def _compute_object(self, entity_type: str, object_id: str, object_code: str,
                        revision: int, measure, stats: QTOStats,
                        mode: CalculationMode) -> None:
        try:
            variables = measure()
        except Exception as exc:
            # Store a failed calculation for traceability, keep going.
            self._store_result(entity_type, object_id, revision, {}, [], mode,
                               status=CalculationStatus.FAILED, errors=[str(exc)])
            self.ctx.quantities_repo.mark_stale_for_object(object_id)
            stats.computed += 1
            return

        formulas = self.engine.formulas_for(entity_type)
        formula_versions = [f"{f.code}:{f.version}" for f in formulas]
        fingerprint = self.engine.object_fingerprint(entity_type, object_id, revision,
                                                     variables, formula_versions)
        cached = self.ctx.calculations_repo.find_fresh(CALC_TYPE, fingerprint)
        if cached is not None:
            stats.cached += 1
            return

        computed = self.engine.compute_for_entity(entity_type, variables, object_id,
                                                  object_code, mode)
        for item in computed:
            self.ctx.quantities_repo.save(
                project_id=self.ctx.project.id, object_id=object_id,
                object_type=entity_type, object_code=object_code,
                formula_code=item.formula.code, formula_expression=item.formula.expression,
                variables=item.variables, raw_quantity=item.raw_quantity,
                waste_factor=item.formula.waste_factor, final_quantity=item.final_quantity,
                unit=item.unit, source=item.formula.source or "QTO",
                input_hash=fingerprint)
        self._store_result(entity_type, object_id, revision, variables,
                           [item.formula.code for item in computed], mode,
                           status=CalculationStatus.COMPLETED, input_hash=fingerprint)
        stats.computed += 1

    def _store_result(self, entity_type: str, object_id: str, revision: int,
                      variables: Dict[str, float], formula_codes: List[str],
                      mode: CalculationMode, status: CalculationStatus,
                      errors: Optional[List[str]] = None,
                      input_hash: str = "") -> None:
        result = CalculationResult(
            calculation_type=CALC_TYPE,
            input_objects=[{"type": entity_type, "id": object_id, "revision": revision}],
            parameters=dict(variables),
            values={}, units={},
            errors=errors or [],
            mode=mode, status=status, objects_processed=len(formula_codes),
            input_hash=input_hash,
        )
        self.ctx.calculations_repo.save(result, self.ctx.project.id)
        if errors:
            self.ctx.emit("QUANTITY_CHANGED", {"id": object_id, "status": "FAILED",
                                               "errors": errors})
        else:
            self.ctx.emit("QUANTITY_CHANGED", {"id": object_id, "status": "COMPLETED"})

    # -- reporting ----------------------------------------------------------------
    def quantities(self, only_stale: bool = False) -> List[Dict[str, Any]]:
        return self.ctx.quantities_repo.all(self.ctx.project.id, only_stale=only_stale)

    def totals_by_formula(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for row in self.quantities():
            totals[row["formula_code"]] = totals.get(row["formula_code"], 0.0) + row["final_quantity"]
        return totals


__all__ = ["QuantityService", "QTOStats"]
