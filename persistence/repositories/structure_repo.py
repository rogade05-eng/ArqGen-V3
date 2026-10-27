"""Repositories for the structure module (spec sections 33, 78)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from domain.structure import (
    Combination, LoadCase, StructuralElement, StructuralMaterial,
    StructuralSection,
)
from persistence.repositories.base import EntityMapper, apply_common_fields, entity_common_row
from persistence.sqlite.connection import Session, json_dumps, json_loads


class StructuralMaterialRepository(EntityMapper[StructuralMaterial]):
    table = "struct_materials"
    entity_class = StructuralMaterial

    def to_row(self, e: StructuralMaterial) -> dict:
        return {**entity_common_row(e), "name": e.name, "kind": e.kind,
                "fck_mpa": e.fck_mpa, "fy_mpa": e.fy_mpa, "e_gpa": e.e_gpa,
                "density_kn_m3": e.density_kn_m3}

    def from_row(self, row) -> StructuralMaterial:
        e = StructuralMaterial(id=row["id"], name=row["name"], kind=row["kind"],
                               fck_mpa=row["fck_mpa"], fy_mpa=row["fy_mpa"],
                               e_gpa=row["e_gpa"], density_kn_m3=row["density_kn_m3"])
        apply_common_fields(e, row)
        return e


class StructuralSectionRepository(EntityMapper[StructuralSection]):
    table = "struct_sections"
    entity_class = StructuralSection

    def to_row(self, e: StructuralSection) -> dict:
        return {**entity_common_row(e), "name": e.name, "shape": e.shape,
                "h_mm": e.h_mm, "b_mm": e.b_mm, "tw_mm": e.tw_mm,
                "tf_mm": e.tf_mm, "d_mm": e.d_mm, "weight_kg_m": e.weight_kg_m}

    def from_row(self, row) -> StructuralSection:
        e = StructuralSection(id=row["id"], name=row["name"], shape=row["shape"],
                              h_mm=row["h_mm"], b_mm=row["b_mm"], tw_mm=row["tw_mm"],
                              tf_mm=row["tf_mm"], d_mm=row["d_mm"],
                              weight_kg_m=row["weight_kg_m"])
        apply_common_fields(e, row)
        return e


class StructuralElementRepository(EntityMapper[StructuralElement]):
    table = "struct_elements"
    entity_class = StructuralElement

    def to_row(self, e: StructuralElement) -> dict:
        return {**entity_common_row(e), "kind": e.kind, "name": e.name,
                "material_id": e.material_id, "section_id": e.section_id,
                "start_x": e.start[0], "start_y": e.start[1],
                "end_x": e.end[0], "end_y": e.end[1],
                "z0": e.z0, "z1": e.z1, "load_udl_kn_m": e.load_udl_kn_m,
                "point_loads_json": json_dumps([list(p) for p in e.point_loads]),
                "attrs_json": json_dumps(e.attrs)}

    def from_row(self, row) -> StructuralElement:
        e = StructuralElement(
            id=row["id"], kind=row["kind"], name=row["name"],
            material_id=row["material_id"] or "", section_id=row["section_id"] or "",
            start=(row["start_x"], row["start_y"]),
            end=(row["end_x"], row["end_y"]),
            z0=row["z0"], z1=row["z1"], load_udl_kn_m=row["load_udl_kn_m"],
            point_loads=[(p[0], p[1])
                         for p in json_loads(row["point_loads_json"], [])],
            attrs=json_loads(row["attrs_json"], {}) or {})
        apply_common_fields(e, row)
        return e


class LoadCaseRepository(EntityMapper[LoadCase]):
    table = "struct_load_cases"
    entity_class = LoadCase

    def to_row(self, e: LoadCase) -> dict:
        return {**entity_common_row(e), "name": e.name, "kind": e.kind,
                "factor": e.factor, "description": e.description}

    def from_row(self, row) -> LoadCase:
        e = LoadCase(id=row["id"], name=row["name"], kind=row["kind"],
                     factor=row["factor"], description=row["description"])
        apply_common_fields(e, row)
        return e


class CombinationRepository(EntityMapper[Combination]):
    table = "struct_combinations"
    entity_class = Combination

    def to_row(self, e: Combination) -> dict:
        return {**entity_common_row(e), "name": e.name,
                "case_factors_json": json_dumps(e.case_factors),
                "description": e.description}

    def from_row(self, row) -> Combination:
        e = Combination(id=row["id"], name=row["name"],
                        case_factors=json_loads(row["case_factors_json"], {}) or {},
                        description=row["description"])
        apply_common_fields(e, row)
        return e


class StructureRepository:
    """Facade over the structure repositories with a typed registry."""

    def __init__(self, session: Session) -> None:
        self.materials = StructuralMaterialRepository(session)
        self.sections = StructuralSectionRepository(session)
        self.elements = StructuralElementRepository(session)
        self.load_cases = LoadCaseRepository(session)
        self.combinations = CombinationRepository(session)
        self._mappers: Dict[str, EntityMapper] = {
            "MATERIAL": self.materials,
            "SECTION": self.sections,
            "ELEMENT": self.elements,
            "LOAD_CASE": self.load_cases,
            "COMBINATION": self.combinations,
        }

    @property
    def session(self) -> Session:
        return self.materials.session

    def mapper_for(self, entity_type: str) -> EntityMapper:
        mapper = self._mappers.get(entity_type)
        if mapper is None:
            raise KeyError(f"Sin repositorio para el tipo: {entity_type}")
        return mapper

    def save(self, entity) -> object:
        return self.mapper_for(entity.ENTITY_TYPE).save(entity)

    def get(self, entity_type: str, entity_id: str):
        return self.mapper_for(entity_type).get(entity_id)

    def get_by_code(self, entity_type: str, code: str):
        return self.mapper_for(entity_type).get_by_code(code)

    def list(self, entity_type: str, project_id: str, where: str = "",
             params: tuple = ()) -> list:
        return self.mapper_for(entity_type).list(project_id, where, params)

    def delete(self, entity_type: str, entity_id: str) -> bool:
        return self.mapper_for(entity_type).delete(entity_id)

    def count(self, entity_type: str, project_id: str) -> int:
        return self.mapper_for(entity_type).count(project_id)

    def elements_of_kind(self, project_id: str, kind: str) -> List[StructuralElement]:
        return self.list("ELEMENT", project_id, "kind = ?", (kind,))

    def all_codes(self, project_id: str) -> List[str]:
        codes: set[str] = set()
        for mapper in self._mappers.values():
            for row in mapper.session.query_all(
                    f"SELECT code FROM {mapper.table} WHERE project_id = ?",
                    (project_id,)):
                if row["code"]:
                    codes.add(row["code"])
        return sorted(codes)

    def total_steel_weight(self, project_id: str) -> float:
        """Peso total de acero estimado a partir de secciones y longitudes."""
        sections = {s.id: s for s in self.list("SECTION", project_id)}
        from engines.structure_engine import section_properties
        total = 0.0
        for element in self.list("ELEMENT", project_id):
            section = sections.get(element.section_id)
            if section is None:
                continue
            props = section_properties(
                section.shape, h_mm=section.h_mm, b_mm=section.b_mm,
                tw_mm=section.tw_mm, tf_mm=section.tf_mm, d_mm=section.d_mm,
                weight_kg_m=section.weight_kg_m)
            total += props.weight_kg_m * element.length_m
        return total


__all__ = [
    "StructureRepository", "StructuralMaterialRepository",
    "StructuralSectionRepository", "StructuralElementRepository",
    "LoadCaseRepository", "CombinationRepository",
]
