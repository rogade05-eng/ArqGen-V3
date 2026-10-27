"""StructureService (spec sections 33, 34, 76, 102).

Facade of the structural module. All mutations go through the
CommandBus, write the audit trail, emit events and invalidate stale
quantities. Analysis produces reproducible CalculationResult records
(calculation type STR, spec 102) and writes the key magnitudes back
into the element attrs for QTO, clash detection and documentation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.calculations.contracts import CalculationMode, CalculationResult, CalculationStatus
from core.errors import DomainError
from core.validation.results import Finding, ValidationStatus
from domain.structure import (
    ELEMENT_KINDS, LINEAR_KINDS, Combination, LoadCase, StructuralElement,
    StructuralMaterial, StructuralSection,
)
from engines.structure_engine import (
    beam_analysis, bolt_group_shear_kn, column_analysis, section_properties,
    steel_weight_kg, truss_solve, truss_utilization, weld_capacity_kn,
)
from engines.quantity_engine import FormulaSpec
from services.commands_impl import (
    CreateEntityCommand, DeleteEntityCommand, UpdateEntityCommand, entity_snapshot,
)
from services.context import ProjectContext

DEFAULT_COMBINATIONS: Tuple[Tuple[str, Tuple[Tuple[str, float], ...]], ...] = (
    ("ULS-1", (("DEAD", 1.35), ("LIVE", 1.5))),
    ("ULS-2", (("DEAD", 1.0), ("WIND", 1.5))),
    ("ULS-3", (("DEAD", 1.0), ("SEISMIC", 1.4))),
    ("SLS", (("DEAD", 1.0), ("LIVE", 1.0))),
)


class StructureService:
    """Facade of the structure module (spec 33-34)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    # -- helpers -----------------------------------------------------------
    def _audit(self, command: str, entity_type: str, entity_id: str,
               old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]],
               reason: str = "", result: str = "OK") -> None:
        from core.audit.models import make_audit_event
        event = make_audit_event(self.ctx.user, entity_id, entity_type, command,
                                 old, new, reason, result)
        self.ctx.audit_repo.append(event)

    def _finish(self, command_name: str, entity, old_snapshot: Optional[Dict[str, Any]] = None,
                events: Optional[List[Tuple[str, Dict[str, Any]]]] = None) -> Any:
        new_snapshot = entity_snapshot(entity)
        self._audit(command_name, entity.ENTITY_TYPE, entity.id, old_snapshot, new_snapshot)
        for event_type, payload in events or []:
            self.ctx.emit(event_type, {"id": entity.id, "type": entity.ENTITY_TYPE,
                                       "code": entity.code, **payload})
        self.ctx.quantities_repo.mark_stale_for_object(entity.id)
        return entity

    def _store_calculation(self, values: Dict[str, float], units: Dict[str, str],
                           objects: List[Tuple[str, str, int]],
                           parameters: Optional[Dict[str, Any]] = None,
                           errors: Optional[List[str]] = None,
                           status: CalculationStatus = CalculationStatus.COMPLETED
                           ) -> CalculationResult:
        result = CalculationResult(
            calculation_type="STR",
            input_objects=[{"type": t, "id": i, "revision": r} for t, i, r in objects],
            parameters=parameters or {},
            values={k: round(v, 4) for k, v in values.items()},
            units=units, errors=errors or [], mode=CalculationMode.BALANCED,
            status=status, objects_processed=len(objects))
        self.ctx.calculations_repo.save(result, self.ctx.project.id)
        return result

    # -- resolution ----------------------------------------------------------
    def _resolve(self, entity_type: str, ref: str):
        entity = (self.ctx.structure.get_by_code(entity_type, ref)
                  or self.ctx.structure.get(entity_type, ref))
        if entity is None:
            for candidate in self.ctx.structure.list(entity_type, self.ctx.project.id):
                if getattr(candidate, "name", "").lower() == ref.lower():
                    entity = candidate
                    break
        if entity is None:
            raise DomainError(message=f"Objeto estructural no encontrado: {ref}",
                              code="ARQ-STR-030", context={"type": entity_type})
        return entity

    # -- catalog: materials / sections -----------------------------------------
    def create_material(self, name: str, kind: str = "CONCRETE",
                        fck_mpa: float = 0.0, fy_mpa: float = 0.0,
                        e_gpa: float = 0.0, density_kn_m3: float = 0.0
                        ) -> StructuralMaterial:
        material = StructuralMaterial(
            project_id=self.ctx.project.id,
            code=self.ctx.next_code("STRUCTURE", "MATERIAL"),
            name=name, kind=kind, fck_mpa=fck_mpa, fy_mpa=fy_mpa,
            e_gpa=e_gpa, density_kn_m3=density_kn_m3)
        self.ctx.command_bus.execute(CreateEntityCommand(material), self.ctx)
        return self._finish("CREATE_ENTITY", material,
                            events=[("SYSTEM_CHANGED", {"system": "STRUCTURE"})])

    def create_section(self, name: str, shape: str, h_mm: float = 0.0,
                       b_mm: float = 0.0, tw_mm: float = 0.0, tf_mm: float = 0.0,
                       d_mm: float = 0.0, weight_kg_m: float = 0.0
                       ) -> StructuralSection:
        section = StructuralSection(
            project_id=self.ctx.project.id,
            code=self.ctx.next_code("STRUCTURE", "SECTION"),
            name=name, shape=shape, h_mm=h_mm, b_mm=b_mm, tw_mm=tw_mm,
            tf_mm=tf_mm, d_mm=d_mm, weight_kg_m=weight_kg_m)
        self.ctx.command_bus.execute(CreateEntityCommand(section), self.ctx)
        return self._finish("CREATE_ENTITY", section,
                            events=[("SYSTEM_CHANGED", {"system": "STRUCTURE"})])

    # -- load cases / combinations ------------------------------------------------
    def create_load_case(self, name: str, kind: str = "DEAD",
                         factor: float = 1.0, description: str = "") -> LoadCase:
        load_case = LoadCase(
            project_id=self.ctx.project.id,
            code=self.ctx.next_code("STRUCTURE", "LOAD_CASE"),
            name=name, kind=kind, factor=factor, description=description)
        self.ctx.command_bus.execute(CreateEntityCommand(load_case), self.ctx)
        return self._finish("CREATE_ENTITY", load_case,
                            events=[("SYSTEM_CHANGED", {"system": "STRUCTURE"})])

    def create_combination(self, name: str, case_factors: Dict[str, float],
                           description: str = "") -> Combination:
        combination = Combination(
            project_id=self.ctx.project.id,
            code=self.ctx.next_code("STRUCTURE", "COMBINATION"),
            name=name, case_factors=dict(case_factors), description=description)
        self.ctx.command_bus.execute(CreateEntityCommand(combination), self.ctx)
        return self._finish("CREATE_ENTITY", combination,
                            events=[("SYSTEM_CHANGED", {"system": "STRUCTURE"})])

    def ensure_default_combinations(self) -> List[Combination]:
        """ULS/SLS clásicas (1,35·G + 1,5·Q, viento, sismo y servicio)."""
        existing = {c.name for c in self.ctx.structure.list("COMBINATION",
                                                            self.ctx.project.id)}
        created: List[Combination] = []
        for name, factors in DEFAULT_COMBINATIONS:
            if name in existing:
                continue
            created.append(self.create_combination(
                name, {kind: factor for kind, factor in factors},
                description="Combinación estándar ARQ GEN"))
        return created

    # -- elements -----------------------------------------------------------------
    def create_element(self, kind: str, name: str, level_ref: str = "",
                       material_ref: str = "", section_ref: str = "",
                       start: Tuple[float, float] = (0.0, 0.0),
                       end: Tuple[float, float] = (0.0, 0.0),
                       z0: float = 0.0, z1: float = 0.0,
                       load_udl_kn_m: float = 0.0,
                       point_loads: Optional[List[Tuple[float, float]]] = None,
                       attrs: Optional[Dict[str, Any]] = None,
                       space_ref: str = "") -> StructuralElement:
        if kind not in ELEMENT_KINDS:
            raise DomainError(
                message=f"Tipo de elemento desconocido: {kind}",
                code="ARQ-STR-003", context={"kind": kind, "allowed": list(ELEMENT_KINDS)})
        level_id = None
        if level_ref:
            level = (self.ctx.architecture.get_by_code("LEVEL", level_ref)
                     or self.ctx.architecture.get("LEVEL", level_ref))
            if level is None:
                raise DomainError(message=f"Nivel no encontrado: {level_ref}",
                                  code="ARQ-DOM-001")
            level_id = level.id
        space_id = None
        if space_ref:
            space = (self.ctx.architecture.get_by_code("SPACE", space_ref)
                     or self.ctx.architecture.get("SPACE", space_ref))
            if space is None:
                raise DomainError(message=f"Local no encontrado: {space_ref}",
                                  code="ARQ-DOM-001")
            space_id = space.id
        material_id = ""
        if material_ref:
            material_id = self._resolve("MATERIAL", material_ref).id
        section_id = ""
        if section_ref:
            section_id = self._resolve("SECTION", section_ref).id
        element = StructuralElement(
            project_id=self.ctx.project.id,
            code=self.ctx.next_code("STRUCTURE", "ELEMENT"),
            kind=kind, name=name, material_id=material_id, section_id=section_id,
            start=tuple(start), end=tuple(end), z0=z0, z1=z1,
            load_udl_kn_m=load_udl_kn_m, point_loads=list(point_loads or []),
            attrs=dict(attrs or {}), level_id=level_id)
        if space_id:
            element.attrs["space_id"] = space_id
        self.ctx.command_bus.execute(CreateEntityCommand(element), self.ctx)
        return self._finish("CREATE_ENTITY", element,
                            events=[("GEOMETRY_CHANGED", {"element_kind": kind})])

    def set_element_attrs(self, element_ref: str, attrs: Dict[str, Any]
                          ) -> StructuralElement:
        element = self._resolve("ELEMENT", element_ref)
        old_snapshot = entity_snapshot(element)
        element.attrs.update(attrs)
        element.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(element), self.ctx)
        return self._finish("UPDATE_ENTITY", element, old_snapshot,
                            events=[("SYSTEM_CHANGED", {"system": "STRUCTURE"})])

    def delete_element(self, element_ref: str) -> str:
        element = self._resolve("ELEMENT", element_ref)
        command = DeleteEntityCommand("ELEMENT", element.id)
        self.ctx.command_bus.execute(command, self.ctx)
        self._audit("DELETE_ENTITY", "ELEMENT", element.id,
                    entity_snapshot(element), None)
        self.ctx.emit("OBJECT_DELETED", {"id": element.id, "type": "ELEMENT",
                                         "code": element.code})
        return element.code

    # -- section helpers -------------------------------------------------------------
    def _section_properties(self, section: StructuralSection,
                            material: Optional[StructuralMaterial] = None):
        density = material.density_kn_m3 if material is not None else 78.5
        return section_properties(
            section.shape, h_mm=section.h_mm, b_mm=section.b_mm,
            tw_mm=section.tw_mm, tf_mm=section.tf_mm, d_mm=section.d_mm,
            density_kn_m3=density, weight_kg_m=section.weight_kg_m)

    def _material_of(self, element: StructuralElement) -> Optional[StructuralMaterial]:
        return self.ctx.structure.get("MATERIAL", element.material_id) or None

    def _section_of(self, element: StructuralElement) -> Optional[StructuralSection]:
        return self.ctx.structure.get("SECTION", element.section_id) or None

    # -- analysis: beams / columns -------------------------------------------------
    def analyze_element(self, element_ref: str,
                        combination_ref: str = "") -> Dict[str, Any]:
        """Viga o pilar: reacciones, cortante, momento, flecha, pandeo y
        utilización (spec 34). Guarda CalculationResult STR."""
        element = self._resolve("ELEMENT", element_ref)
        if element.kind not in LINEAR_KINDS:
            raise DomainError(
                message=f"El tipo {element.kind} no admite análisis de miembro lineal",
                code="ARQ-STR-031", context={"kind": element.kind})
        section = self._section_of(element)
        material = self._material_of(element)
        if section is None:
            raise DomainError(
                message=f"El elemento {element.code} no tiene sección asignada",
                code="ARQ-STR-032", suggested_action="Asigne una sección con struct element-add.")
        props = self._section_properties(section, material)
        length = element.length_m
        combination_factor = 1.0
        if combination_ref:
            combination = self._resolve("COMBINATION", combination_ref)
            combination_factor = sum(combination.case_factors.values())
        udl = element.load_udl_kn_m * combination_factor
        point_loads = [(a, p * combination_factor) for a, p in element.point_loads]

        report: Dict[str, Any] = {"element": element.code, "kind": element.kind,
                                  "length_m": round(length, 4)}
        if element.kind in ("BEAM", "TRUSS"):
            support = str(element.attrs.get("support", "SIMPLE")).upper()
            e_gpa = material.e_gpa if material else 21.0
            beam = beam_analysis(length, udl_kn_m=udl, point_loads=point_loads,
                                 support=support, e_gpa=e_gpa, ix_m4=props.ix_m4)
            report["beam"] = beam.to_dict()
            values = {"reaction_a_kn": beam.reaction_a_kn,
                      "shear_max_kn": beam.shear_max_kn,
                      "moment_max_knm": beam.moment_max_knm,
                      "deflection_mm": beam.deflection_mm,
                      "steel_weight_kg": steel_weight_kg(props.weight_kg_m, length)}
            if element.kind == "BEAM":
                element.attrs.update({
                    "shear_max_kn": round(beam.shear_max_kn, 3),
                    "moment_max_knm": round(beam.moment_max_knm, 3),
                    "deflection_mm": round(beam.deflection_mm, 3)})
                if props.wel_cm3 > 0 and material is not None and material.fy_mpa > 0:
                    sigma_mpa = beam.moment_max_knm * 1e6 / (props.wel_cm3 * 1000.0)
                    utilization = sigma_mpa / (material.fy_mpa * 0.66)
                    report["bending"] = {
                        "sigma_mpa": round(sigma_mpa, 2),
                        "allowable_mpa": round(material.fy_mpa * 0.66, 2),
                        "utilization": round(utilization, 3), "ok": utilization <= 1.0}
                    values["bending_utilization"] = utilization
                    element.attrs["utilization"] = round(utilization, 3)
        else:  # COLUMN / BRACE under compression
            axial = udl * length + sum(p for _a, p in point_loads)
            if element.num("axial_kn") > 0:
                axial = element.num("axial_kn") * combination_factor
            f_y = material.fy_mpa if material else 0.0
            f_ck = material.fck_mpa if material else 0.0
            e_gpa = material.e_gpa if material else 21.0
            column = column_analysis(length, axial, e_gpa, props.area_m2,
                                     props.ix_m4, props.radius_gyration_m,
                                     f_yield_mpa=f_y, f_ck_mpa=f_ck,
                                     support=str(element.attrs.get("support", "PIN")).upper())
            report["column"] = column.to_dict()
            values = {"axial_kn": axial, "slenderness": column.slenderness,
                      "euler_critical_kn": column.euler_critical_kn,
                      "capacity_kn": column.capacity_kn,
                      "utilization": column.utilization,
                      "steel_weight_kg": steel_weight_kg(props.weight_kg_m, length)}
            element.attrs.update({
                "axial_kn": round(axial, 3),
                "utilization": round(column.utilization, 3),
                "capacity_kn": round(column.capacity_kn, 1)})
        element.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(element), self.ctx)
        self._audit("UPDATE_ENTITY", "ELEMENT", element.id, None,
                    entity_snapshot(element), reason="analysis STR")
        self._store_calculation(
            values, {"axial_kn": "kN", "moment_max_knm": "kN·m",
                     "shear_max_kn": "kN", "deflection_mm": "mm",
                     "steel_weight_kg": "kg", "utilization": "-"},
            [("ELEMENT", element.id, element.revision)],
            parameters={"combination": combination_ref,
                        "section": section.code,
                        "material": material.code if material else ""})
        self.ctx.commit()
        return report

    # -- analysis: trusses (spec 34 cerchas) --------------------------------------------
    def analyze_truss(self, element_ref: str,
                      f_allow_mpa: float = 0.0) -> Dict[str, Any]:
        """Cercha plana: fuerzas de barras por método de los nudos,
        reacciones, peso y utilización (spec 34)."""
        element = self._resolve("ELEMENT", element_ref)
        if element.kind != "TRUSS":
            raise DomainError(
                message=f"El elemento {element.code} no es una cercha",
                code="ARQ-STR-033", context={"kind": element.kind})
        nodes = {n["id"]: (n["x"], n["y"]) for n in element.attrs.get("nodes", [])}
        members = [(m["id"], m["a"], m["b"])
                   for m in element.attrs.get("members", [])]
        supports = {s["node"]: (s["kind"], s.get("axis", "y"))
                    for s in element.attrs.get("supports", [])}
        joint_loads = {j["node"]: (j.get("fx", 0.0), j.get("fy", 0.0))
                       for j in element.attrs.get("joint_loads", [])}
        for required, label in ((nodes, "nudos"), (members, "barras"),
                                (supports, "apoyos")):
            if not required:
                raise DomainError(
                    message=f"La cercha {element.code} no define {label}",
                    code="ARQ-STR-034", suggested_action="Defina el modelo en attrs.")
        result = truss_solve(nodes, members, supports, joint_loads)
        report: Dict[str, Any] = {"element": element.code, "result": result.to_dict()}
        values: Dict[str, float] = {"max_abs_force_kn": result.max_abs_kn}

        section = self._section_of(element)
        material = self._material_of(element)
        if section is not None and result.ok:
            props = self._section_properties(section, material)
            f_allow = f_allow_mpa or (material.fy_mpa * 0.6
                                      if material and material.fy_mpa > 0 else 160.0)
            utilization = truss_utilization(result.member_forces, props.area_m2,
                                            f_allow)
            report["utilization"] = {k: round(v, 3) for k, v in utilization.items()}
            values["max_utilization"] = max(utilization.values())
            total_weight = sum(
                steel_weight_kg(
                    props.weight_kg_m,
                    ((nodes[a][0] - nodes[b][0]) ** 2 +
                     (nodes[a][1] - nodes[b][1]) ** 2) ** 0.5)
                for _mid, a, b in members)
            report["steel_weight_kg"] = round(total_weight, 1)
            values["steel_weight_kg"] = total_weight
            report["quantities"] = self._truss_quantities(element, nodes, members,
                                                          props.weight_kg_m)
        element.attrs.update({
            "truss_max_kn": round(result.max_abs_kn, 3),
            "truss_ok": 1 if result.ok else 0})
        element.touch()
        self.ctx.command_bus.execute(UpdateEntityCommand(element), self.ctx)
        self._store_calculation(
            values, {"max_abs_force_kn": "kN", "steel_weight_kg": "kg",
                     "max_utilization": "-"},
            [("ELEMENT", element.id, element.revision)],
            parameters={"method": "method_of_joints",
                        "members": len(members), "nodes": len(nodes)},
            errors=[] if result.ok else [result.reason],
            status=CalculationStatus.COMPLETED if result.ok else CalculationStatus.FAILED)
        self.ctx.commit()
        return report

    @staticmethod
    def _truss_quantities(element: StructuralElement,
                          nodes: Dict[str, Tuple[float, float]],
                          members: List[Tuple[str, str, str]],
                          weight_kg_m: float) -> Dict[str, float]:
        """Geometría, cotas, perfiles, longitudes, peso, soldaduras, placas
        y cantidades de la cercha (spec 34: lo que debe generar)."""
        lengths = {}
        for mid, a, b in members:
            lengths[mid] = ((nodes[a][0] - nodes[b][0]) ** 2 +
                            (nodes[a][1] - nodes[b][1]) ** 2) ** 0.5
        total_length = sum(lengths.values())
        # Soldaduras y placas: un nudo congruente por barra conectada.
        welds_per_joint = 2.0
        joints = len(nodes)
        weld_total_mm = joints * welds_per_joint * 60.0     # 60 mm por barra soldada
        gusset_count = joints
        return {
            "member_count": float(len(members)),
            "total_length_m": round(total_length, 3),
            "max_member_length_m": round(max(lengths.values()), 3),
            "steel_weight_kg": round(total_length * weight_kg_m, 2),
            "weld_total_mm": round(weld_total_mm, 1),
            "gusset_plates": float(gusset_count),
        }

    # -- connections -----------------------------------------------------------------
    def check_connection(self, bolt_count: int, bolt_diameter_mm: float,
                         weld_length_mm: float, weld_throat_mm: float,
                         demand_kn: float) -> Dict[str, Any]:
        """Uniones: cortante de pernos y cordón de soldadura (spec 33-34)."""
        bolt_capacity = bolt_group_shear_kn(bolt_count, bolt_diameter_mm)
        weld_capacity = weld_capacity_kn(weld_length_mm, weld_throat_mm)
        governing = min(bolt_capacity, weld_capacity)
        utilization = demand_kn / governing if governing > 0 else float("inf")
        report = {
            "bolt_capacity_kn": round(bolt_capacity, 2),
            "weld_capacity_kn": round(weld_capacity, 2),
            "governing_kn": round(governing, 2),
            "demand_kn": round(demand_kn, 2),
            "utilization": round(utilization, 3),
            "ok": utilization <= 1.0,
        }
        self._store_calculation(
            {"bolt_capacity_kn": bolt_capacity, "weld_capacity_kn": weld_capacity,
             "utilization": utilization},
            {"bolt_capacity_kn": "kN", "weld_capacity_kn": "kN", "utilization": "-"},
            [], parameters={"bolt_count": bolt_count,
                            "bolt_diameter_mm": bolt_diameter_mm,
                            "weld_length_mm": weld_length_mm,
                            "weld_throat_mm": weld_throat_mm})
        return report

    # -- reports -----------------------------------------------------------------
    def utilization_report(self) -> Dict[str, Any]:
        """Informe de utilización de todos los elementos lineales (spec 34)."""
        rows: List[Dict[str, Any]] = []
        for element in self.ctx.structure.list("ELEMENT", self.ctx.project.id):
            if element.kind not in LINEAR_KINDS:
                continue
            utilization = element.num("utilization")
            rows.append({
                "element": element.code, "kind": element.kind,
                "name": element.name, "length_m": round(element.length_m, 3),
                "axial_kn": round(element.num("axial_kn"), 2),
                "moment_knm": round(element.num("moment_max_knm"), 2),
                "utilization": round(utilization, 3),
                "ok": utilization <= 1.0 + 1e-9,
            })
        rows.sort(key=lambda r: (-r["utilization"], r["element"]))
        return {"rows": rows, "count": len(rows)}

    def steel_quantities(self) -> Dict[str, float]:
        """Cantidades de acero del proyecto (peso/cantidades, spec 34)."""
        sections = {s.id: s for s in self.ctx.structure.list("SECTION",
                                                             self.ctx.project.id)}
        materials = {m.id: m for m in self.ctx.structure.list("MATERIAL",
                                                              self.ctx.project.id)}
        total_kg = 0.0
        total_length = 0.0
        for element in self.ctx.structure.list("ELEMENT", self.ctx.project.id):
            section = sections.get(element.section_id)
            if section is None:
                continue
            material = materials.get(element.material_id)
            props = section_properties(
                section.shape, h_mm=section.h_mm, b_mm=section.b_mm,
                tw_mm=section.tw_mm, tf_mm=section.tf_mm, d_mm=section.d_mm,
                density_kn_m3=material.density_kn_m3 if material else 78.5,
                weight_kg_m=section.weight_kg_m)
            total_kg += props.weight_kg_m * element.length_m
            total_length += element.length_m
        return {"steel_weight_kg": round(total_kg, 2),
                "total_length_m": round(total_length, 2)}


__all__ = ["StructureService", "DEFAULT_COMBINATIONS"]
