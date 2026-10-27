"""BIM Service (spec section 63): modelo BIM interno ligero.

Cada objeto del proyecto se proyecta a un registro BIM con:

    category       categoría IFC conceptual (IfcWall, IfcSpace, ...)
    geometry       geometría del objeto (polígono, eje, alturas)
    level          nivel/edificación a la que pertenece
    material       material declarado (muro, elemento estructural)
    properties     propiedades planas (Psets conceptuales)
    classification clasificación (UniclassLite por tipo)
    systems        sistemas a los que sirve (redes de instalaciones)
    relationships  relaciones explícitas (contiene, conecta, hospeda)

El árbol espacial replica la jerarquía IFC (spec 67):
IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey → IfcSpace +
elementos. El exportador IFC y el CLI leen SOLO esta fachada: el núcleo
nunca depende del formato (spec 64).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.context import ProjectContext

# Clasificación conceptual ligera por categoría (UniclassLite).
CLASSIFICATION: Dict[str, str] = {
    "PROJECT": "EF_10", "SITE": "EF_20", "BUILDING": "EF_25",
    "LEVEL": "EF_25_50", "SPACE": "SL_20", "WALL": "EF_30_10",
    "DOOR": "EF_30_90", "WINDOW": "EF_30_95", "OPENING": "EF_30_99",
    "SLAB": "EF_30_20", "COLUMN": "EF_30_30", "BEAM": "EF_30_35",
    "FOUNDATION": "EF_30_15", "TRUSS": "EF_30_40", "BRACE": "EF_30_42",
    "CONNECTION": "EF_30_45", "PLATE": "EF_30_46", "BOLT": "EF_30_47",
    "WELD": "EF_30_48",
    "NETWORK": "Ss_25", "NODE": "Ss_25_10", "SEGMENT": "Ss_25_20",
    "ELEMENT": "EF_30", "MATERIAL": "Pr_20", "SECTION": "Pr_20",
}

IFC_CATEGORY: Dict[str, str] = {
    "PROJECT": "IfcProject", "SITE": "IfcSite", "BUILDING": "IfcBuilding",
    "LEVEL": "IfcBuildingStorey", "SPACE": "IfcSpace", "WALL": "IfcWall",
    "DOOR": "IfcDoor", "WINDOW": "IfcWindow", "OPENING": "IfcOpeningElement",
    "FOUNDATION": "IfcFooting", "COLUMN": "IfcColumn", "BEAM": "IfcBeam",
    "SLAB": "IfcSlab", "TRUSS": "IfcMember", "BRACE": "IfcMember",
    "CONNECTION": "IfcElementAssembly", "PLATE": "IfcPlate",
    "BOLT": "IfcMechanicalFastener", "WELD": "IfcElementAssembly",
    "MATERIAL": "IfcMaterial", "SECTION": "IfcProfileDef",
    "NETWORK": "IfcDistributionSystem", "NODE": "IfcDistributionElement",
    "SEGMENT": "IfcDistributionElement", "ELEMENT": "IfcElement",
    "LOAD_CASE": "IfcGroup", "COMBINATION": "IfcGroup",
}

# Categoría fina para elementos estructurales según su kind (spec 33).
ELEMENT_KIND_CATEGORY: Dict[str, str] = {
    "BEAM": "IfcBeam", "COLUMN": "IfcColumn", "SLAB": "IfcSlab",
    "FOUNDATION": "IfcFooting", "TRUSS": "IfcMember", "BRACE": "IfcMember",
    "CONNECTION": "IfcElementAssembly", "PLATE": "IfcPlate",
    "BOLT": "IfcMechanicalFastener", "WELD": "IfcElementAssembly",
}


class BimService:
    """Proyección BIM del modelo semántico (spec 63)."""

    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    # -- projection ------------------------------------------------------------
    def project_record(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """Registro BIM de un objeto (spec 63)."""
        repo_entity = self._load(entity_type, entity_id)
        if repo_entity is None:
            raise KeyError(f"Objeto no encontrado: {entity_type}/{entity_id}")
        return self._record(repo_entity)

    def _load(self, entity_type: str, entity_id: str):
        if entity_type == "ELEMENT":
            return self.ctx.structure.get("ELEMENT", entity_id)
        if entity_type in ("NETWORK", "NODE", "SEGMENT"):
            return self.ctx.installations.get(entity_type, entity_id)
        return self.ctx.architecture.get(entity_type, entity_id)

    def _record(self, entity) -> Dict[str, Any]:
        entity_type = entity.ENTITY_TYPE
        properties = self._properties(entity)
        geometry = self._geometry(entity)
        category = IFC_CATEGORY.get(entity_type, "IfcElement")
        if entity_type == "ELEMENT":
            kind = str(getattr(entity, "kind", "")).upper()
            category = ELEMENT_KIND_CATEGORY.get(kind, category)
        return {
            "id": entity.id,
            "code": entity.code,
            "category": category,
            "entity_type": entity_type,
            "name": getattr(entity, "name", "") or entity.code,
            "level": self._level_name(entity),
            "material": self._material_name(entity),
            "geometry": geometry,
            "properties": properties,
            "classification": CLASSIFICATION.get(entity_type, "EF_99"),
            "systems": self._systems_of(entity),
            "relationships": self._relationships(entity),
        }

    # -- property projection ----------------------------------------------------
    def _properties(self, entity) -> Dict[str, Any]:
        data: Dict[str, Any] = {"status": entity.status.value
                                if hasattr(entity.status, "value")
                                else str(entity.status)}
        for attr in ("kind", "system", "discipline", "length_m", "height_m",
                     "thickness_m", "width_m", "area_m2", "type"):
            value = getattr(entity, attr, None)
            if value is not None and not callable(value) and attr not in data:
                data[attr] = value
        attrs = getattr(entity, "attrs", None)
        if isinstance(attrs, dict) and attrs:
            data.update({f"attr_{k}": v for k, v in list(attrs.items())[:24]})
        return data

    def _geometry(self, entity) -> Dict[str, Any]:
        geometry: Dict[str, Any] = {}
        start = getattr(entity, "start", None)
        end = getattr(entity, "end", None)
        if start is not None and end is not None and isinstance(start, tuple):
            geometry["axis"] = [list(start), list(end)]
            geometry["length"] = round(entity.length_m, 4)
        boundary = getattr(entity, "boundary", None)
        if boundary:
            geometry["footprint"] = [list(p) for p in boundary]
            geometry["area"] = round(entity.area_m2(), 4)
            geometry["perimeter"] = round(entity.perimeter_m(), 4)
        thickness = getattr(entity, "thickness_m", None)
        if thickness is not None:
            geometry["thickness"] = thickness
        height = getattr(entity, "height_m", None)
        if height is not None:
            geometry["height"] = height
        width = getattr(entity, "width_m", None)
        if width is not None:
            geometry["width"] = width
        offset = getattr(entity, "offset_m", None)
        if offset is not None:
            geometry["offset"] = offset
        sill = getattr(entity, "sill_height_m", None)
        if sill is not None:
            geometry["sill"] = sill
        position = (getattr(entity, "x", None), getattr(entity, "y", None))
        if position[0] is not None:
            geometry["position"] = [position[0], position[1]]
        elevation = getattr(entity, "elevation_m", None)
        if elevation is not None:
            geometry["elevation"] = elevation
        return geometry

    def _level_name(self, entity) -> str:
        level_id = getattr(entity, "level_id", None)
        if not level_id:
            return ""
        level = self.ctx.architecture.get("LEVEL", level_id)
        return level.name if level else ""

    def _material_name(self, entity) -> str:
        material_id = getattr(entity, "material_id", "")
        if not material_id:
            material = getattr(entity, "material", "")
            return material or ""
        material = self.ctx.structure.get("MATERIAL", material_id)
        return material.name if material else ""

    def _systems_of(self, entity) -> List[str]:
        """Sistemas a los que sirve el objeto (redes de instalaciones)."""
        entity_type = entity.ENTITY_TYPE
        if entity_type == "NETWORK":
            return [entity.system]
        if entity_type == "NODE":
            network = self.ctx.installations.get("NETWORK", entity.network_id)
            return [network.system] if network else []
        if entity_type == "SEGMENT":
            network = self.ctx.installations.get("NETWORK", entity.network_id)
            return [network.system] if network else []
        # Elementos de arquitectura sirven a las redes que los referencian.
        systems: List[str] = []
        for network in self.ctx.installations.list("NETWORK",
                                                   self.ctx.project.id):
            for node in self.ctx.installations.nodes_of(network.id):
                if node.space_id == entity.id or node.wall_id == entity.id:
                    if network.system not in systems:
                        systems.append(network.system)
        return systems

    def _relationships(self, entity) -> List[Dict[str, str]]:
        relations: List[Dict[str, str]] = []
        entity_type = entity.ENTITY_TYPE
        project_id = self.ctx.project.id
        if entity_type == "WALL":
            for opening in self.ctx.architecture.list("OPENING", project_id):
                if opening.wall_id == entity.id:
                    relations.append({"kind": "hasOpening",
                                      "target": opening.code,
                                      "category": IFC_CATEGORY[opening.ENTITY_TYPE]})
        if entity_type in ("OPENING", "DOOR", "WINDOW") \
                and getattr(entity, "wall_id", None):
            wall = self.ctx.architecture.get("WALL", entity.wall_id)
            if wall is not None:
                relations.append({"kind": "inWall", "target": wall.code,
                                  "category": "IfcWall"})
        if entity_type == "SPACE":
            for node in self.ctx.installations.list("NODE", project_id):
                if node.space_id == entity.id:
                    relations.append({"kind": "hostsDevice",
                                      "target": node.code,
                                      "category": "IfcDistributionElement"})
            zone_id = getattr(entity, "zone_id", None)
            if zone_id:
                zone = self.ctx.architecture.get("ZONE", zone_id)
                if zone:
                    relations.append({"kind": "inZone", "target": zone.code,
                                      "category": "IfcZone"})
        if entity_type == "ELEMENT":
            if getattr(entity, "material_id", ""):
                material = self.ctx.structure.get("MATERIAL", entity.material_id)
                if material:
                    relations.append({"kind": "hasMaterial",
                                      "target": material.code,
                                      "category": "IfcMaterial"})
            if getattr(entity, "section_id", ""):
                section = self.ctx.structure.get("SECTION", entity.section_id)
                if section:
                    relations.append({"kind": "hasProfile",
                                      "target": section.code,
                                      "category": "IfcProfileDef"})
        return relations

    # -- spatial tree (spec 67) -----------------------------------------------------
    def bim_tree(self) -> Dict[str, Any]:
        """Jerarquía espacial completa Project → Site → Building → Storeys."""
        project = self.ctx.project
        site = self.ctx.architecture.projects.get_first()
        buildings = self.ctx.architecture.list("BUILDING", self.ctx.project.id)
        levels = self.ctx.architecture.list("LEVEL", self.ctx.project.id)
        spaces = self.ctx.architecture.list("SPACE", self.ctx.project.id)
        walls = self.ctx.architecture.list("WALL", self.ctx.project.id)
        openings = self.ctx.architecture.list("OPENING", self.ctx.project.id)
        elements = self.ctx.structure.list("ELEMENT", self.ctx.project.id)
        networks = self.ctx.installations.list("NETWORK", self.ctx.project.id)

        spaces_by_level: Dict[str, List] = {}
        for space in spaces:
            spaces_by_level.setdefault(space.level_id or "", []).append(space)
        walls_by_level: Dict[str, List] = {}
        for wall in walls:
            walls_by_level.setdefault(wall.level_id or "", []).append(wall)
        space_level = {s.id: (s.level_id or "") for s in spaces}
        nodes_by_level: Dict[str, List] = {}
        for network in networks:
            for node in self.ctx.installations.nodes_of(network.id):
                level_id = node.level_id or space_level.get(node.space_id or "", "")
                nodes_by_level.setdefault(level_id, []).append(node)

        storeys: List[Dict[str, Any]] = []
        if not levels:
            # Proyecto sin niveles: storey conceptual por defecto (spec 67
            # exige IfcBuildingStorey en la jerarquía).
            levels = [type("Level", (), {"id": "", "code": "LEVEL-DEFAULT",
                                         "name": "Nivel por defecto",
                                         "elevation_m": 0.0,
                                         "height_m": 3.0})()]
        for level_index, level in enumerate(levels):
            level_spaces = [self._record(s) for s in
                            spaces_by_level.get(level.id, [])]
            level_walls = [self._record(w) for w in
                           walls_by_level.get(level.id, [])]
            level_devices = [self._record(n) for n in
                             nodes_by_level.get(level.id, [])]
            level_elements = [self._record(e) for e in elements
                              if e.level_id == level.id]
            if level_index == 0:
                # Elementos y dispositivos sin nivel se adscriben al primer
                # storey (comportamiento documentado del mapeo conceptual).
                level_elements.extend(self._record(e) for e in elements
                                      if not e.level_id)
                level_devices.extend(self._record(n) for n in
                                     nodes_by_level.get("", []))
            storeys.append({
                "code": level.code, "name": level.name,
                "elevation_m": level.elevation_m, "height_m": level.height_m,
                "spaces": level_spaces, "walls": level_walls,
                "devices": level_devices, "elements": level_elements,
            })
        return {
            "project": {"code": project.code, "name": project.name,
                        "category": "IfcProject",
                        "classification": CLASSIFICATION["PROJECT"]},
            "site": {"code": site.code if site else "",
                     "name": getattr(site, "name", "Site"),
                     "category": "IfcSite"},
            "building": {"code": buildings[0].code if buildings else "",
                         "name": buildings[0].name if buildings else
                         "Edificio principal", "category": "IfcBuilding"},
            "storeys": storeys,
            "networks": [{"code": n.code, "name": n.name, "system": n.system,
                          "category": "IfcDistributionSystem"} for n in networks],
            "openings": [self._record(o) for o in openings],
        }


__all__ = ["BimService", "IFC_CATEGORY", "CLASSIFICATION"]
