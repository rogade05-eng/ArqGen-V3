"""IFC Exporter (spec section 67): mapping conceptual a IFC4 (ISO 10303-21).

Genera un archivo .ifc SPF (STEP Physical File) con la jerarquía
espacial y la geometría esencial del proyecto:

    IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey
    IfcSpace, IfcWall (IfcExtrudedAreaSolid sobre el contorno del muro),
    IfcDoor / IfcWindow (IfcOpeningElement en el muro), IfcSlab,
    IfcBeam / IfcColumn / IfcMember (estructura),
    IfcDistributionElement (redes y dispositivos, spec 67),
    IfcRelAggregates, IfcRelContainedInSpatialStructure,
    IfcRelVoidsElement / IfcRelFillsElement y IfcRelDefinesByProperties
    con Psets de propiedades.

El Core nunca depende del formato (spec 64): este adaptador vive en
exporters/ y solo consume la fachada BIM (services.bim_service).
Los GlobalId se derivan de forma determinista del UUID persistente
(compresión base64 de 22 caracteres del estándar IFC).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

_B64 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"


def ifc_guid(uuid_str: str) -> str:
    """GlobalId IFC (22 caracteres) determinista a partir de un UUID."""
    hex_digits = uuid_str.replace("-", "").ljust(32, "0")[:32]
    value = int(hex_digits, 16)
    chars: List[str] = []
    for _ in range(22):
        chars.append(_B64[value & 0x3F])
        value >>= 6
    return "".join(chars) or "0" * 22


class _IfcFile:
    """Escritor SPF mínimo: registra entidades y serializa con ids estables."""

    def __init__(self) -> None:
        self._lines: List[Tuple[int, str]] = []
        self._next = 1

    def add(self, entity: str) -> int:
        line_id = self._next
        self._next += 1
        self._lines.append((line_id, entity))
        return line_id

    def ref(self, line_id: Optional[int]) -> str:
        return f"#{line_id}" if line_id is not None else "$"

    def refs(self, line_ids: Sequence[Optional[int]]) -> str:
        ids = [self.ref(i) for i in line_ids if i is not None]
        return "(" + ",".join(ids) + ")" if ids else "$"

    def serialize(self, name: str) -> str:
        header = [
            "ISO-10303-21;",
            "HEADER;",
            "FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),"
            "'2;1');",
            f"FILE_NAME('{name}','2026-01-01T00:00:00',('ARQ GEN'),"
            "('ARQ GEN'),'ARQ GEN IFC4 Writer','ARQ GEN','');",
            "FILE_SCHEMA(('IFC4'));",
            "ENDSEC;",
            "DATA;",
        ]
        body = [f"#{line_id}= {entity};" for line_id, entity in self._lines]
        footer = ["ENDSEC;", "END-ISO-10303-21;", ""]
        return "\n".join(header + body + footer)


class IfcExporter:
    """Adaptador IFC4 (spec 64, 67)."""

    # -- public -------------------------------------------------------------
    def export(self, context, path: str, project_name: str = "") -> str:
        """Exporta el proyecto a IFC4 SPF (export(context, path), spec 95)."""
        from services.bim_service import BimService
        bim = BimService(context)
        tree = bim.bim_tree()
        model = IfcExporter._IfcModel(tree, project_name
                                      or tree["project"]["name"])
        content = model.f.serialize(path)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        return path

    # -- model builder ------------------------------------------------------
    class _IfcModel:
        def __init__(self, tree: Dict[str, Any], project_name: str) -> None:
            self.f = _IfcFile()
            self.tree = tree
            self._wall_refs: Dict[str, int] = {}
            # Eje/espesor/cota de cada muro (para colocar los vanos en
            # su sitio real sobre la cara del anfitrión, v3.13.0).
            self._wall_geom: Dict[str, Tuple[Any, float]] = {}
            self._wall_elev: Dict[str, float] = {}
            self._wall_storey: Dict[str, int] = {}
            self._build(project_name)

        # -- helpers ------------------------------------------------------
        def guid(self, code: str, kind: str) -> str:
            import hashlib
            digest = hashlib.md5(f"{kind}:{code}".encode()).hexdigest()
            return ifc_guid(digest)

        def placement(self, x: float = 0.0, y: float = 0.0, z: float = 0.0,
                      axis_z: Optional[Tuple[float, float, float]] = None,
                      ref_direction: Optional[Tuple[float, float]] = None) -> int:
            f = self.f
            context3d = f.add("IFCCARTESIANPOINT((%g,%g,%g))" % (x, y, z))
            if axis_z is None:
                axis_z = (0.0, 0.0, 1.0)
            if ref_direction is None:
                ref_direction = (1.0, 0.0)
            z_dir = f.add("IFCDIRECTION((%g,%g,%g))" % axis_z)
            x_dir = f.add("IFCDIRECTION((%g,%g,0.))" % ref_direction)
            axis = f.add(f"IFCAXIS2PLACEMENT3D({f.ref(context3d)},"
                         f"{f.ref(z_dir)},{f.ref(x_dir)})")
            return f.add(f"IFCLOCALPLACEMENT($,{f.ref(axis)})")

        def extruded_solid(self, footprint: Sequence[Sequence[float]],
                           height: float, placement: int) -> int:
            """IfcExtrudedAreaSolid con perfil poligonal cerrado."""
            f = self.f
            points = []
            for point in footprint:
                points.append(f.add("IFCCARTESIANPOINT((%g,%g))"
                                    % (point[0], point[1])))
            polyline = f.add(f"IFCPOLYLINE({f.refs(points + [points[0]])})")
            profile = f.add(f"IFCARBITRARYCLOSEDPROFILEDEF(.AREA.,$,"
                            f"{f.ref(polyline)})")
            position = f.add("IFCAXIS2PLACEMENT3D(IFCCARTESIANPOINT((0.,0.,0.)),$,$)")
            direction = f.add("IFCDIRECTION((0.,0.,1.))")
            return f.add(f"IFCEXTRUDEDAREASOLID({f.ref(profile)},"
                         f"{f.ref(position)},{f.ref(direction)},{height:g})")

        def product(self, ifc_class: str, guid: str, name: str,
                    placement: int, solid: int, tag: str = "") -> int:
            f = self.f
            shape_repr = f.add(
                "IFCSHAPEREPRESENTATION($,'Body','SweptSolid',"
                f"({f.ref(solid)}))")
            product_shape = f.add(f"IFCPRODUCTDEFINITIONSHAPE($,$,"
                                  f"({f.ref(shape_repr)}))")
            return f.add(
                f"{ifc_class.upper()}('{guid}',{f.ref(self.owner_history)},"
                f"'{self._esc(name)}',$,$,{f.ref(placement)},"
                f"{f.ref(product_shape)},'{self._esc(tag)}',$)")

        @staticmethod
        def _esc(text: str) -> str:
            return str(text).replace("'", "\\'")[:96] or "Object"

        # -- model ----------------------------------------------------------
        def _build(self, project_name: str) -> None:
            f = self.f
            tree = self.tree
            # --- Cabecera mínima obligatoria -----------------------------
            person = f.add("IFCPERSON($,'Demo','ARQ GEN User',$,$,$,$,$)")
            org = f.add("IFCORGANIZATION($,'ARQ GEN',$,$,$)")
            person_org = f.add(f"IFCPERSONANDORGANIZATION({f.ref(person)},"
                               f"{f.ref(org)},$)")
            application = f.add(
                "IFCAPPLICATION(" + f.ref(org) + ",'1.2.0','ARQ GEN','ARQGEN')")
            self.owner_history = f.add(
                f"IFCOWNERHISTORY({f.ref(person_org)},{f.ref(application)},"
                "$,.ADDED.,$,$,$,1770000000)")

            # Unidades SI.
            length_unit = f.add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
            area_unit = f.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
            volume_unit = f.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
            angle_unit = f.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
            units = f.add(f"IFCUNITASSIGNMENT(({f.ref(length_unit)},"
                          f"{f.ref(area_unit)},{f.ref(volume_unit)},"
                          f"{f.ref(angle_unit)}))")
            origin = f.add("IFCCARTESIANPOINT((0.,0.,0.))")
            true_dir = f.add("IFCDIRECTION((0.,0.,1.))")
            x_dir = f.add("IFCDIRECTION((1.,0.,0.))")
            world_coords = f.add(f"IFCAXIS2PLACEMENT3D({f.ref(origin)},"
                                 f"{f.ref(true_dir)},{f.ref(x_dir)})")
            self.context = f.add(
                "IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,"
                f"{f.ref(world_coords)},$)")

            # --- Jerarquía espacial ---------------------------------------
            project = tree["project"]
            project_placement = self.placement()
            project_entity = f.add(
                f"IFCPROJECT('{self.guid(project['code'], 'project')}',"
                f"{f.ref(self.owner_history)},'{self._esc(project_name or project['name'])}',"
                f"'Proyecto ARQ GEN',$,{f.ref(project_placement)},"
                f"{f.ref(self.context)},$,{f.refs([units])})")

            site = tree["site"]
            site_placement = self.placement()
            site_entity = self.product("IfcSite", self.guid(site["code"], "site"),
                                       site.get("name", "Site"), site_placement,
                                       self.extruded_solid(
                                           [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
                                           0.05, site_placement))
            f.add(f"IFCRELAGGREGATES('{self.guid('proj-site', 'rel')}',"
                  f"{f.ref(self.owner_history)},$,$,{f.ref(project_entity)},"
                  f"({f.ref(site_entity)}))")

            building = tree["building"]
            building_placement = self.placement()
            building_entity = self.product(
                "IfcBuilding", self.guid(building.get("code", "B"), "building"),
                building.get("name", "Edificio"), building_placement,
                self.extruded_solid([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
                                    0.05, building_placement))
            f.add(f"IFCRELAGGREGATES('{self.guid('site-bldg', 'rel')}',"
                  f"{f.ref(self.owner_history)},$,$,{f.ref(site_entity)},"
                  f"({f.ref(building_entity)}))")

            storey_refs: List[int] = []
            contained: List[Tuple[int, List[int]]] = []
            for index, storey in enumerate(tree["storeys"]):
                elevation = float(storey.get("elevation_m", 0.0))
                placement = self.placement(0.0, 0.0, elevation)
                storey_entity = self.product(
                    "IfcBuildingStorey",
                    self.guid(storey["code"], "storey"),
                    storey.get("name", f"Nivel {index + 1}"),
                    placement,
                    self.extruded_solid([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
                                        0.05, placement))
                storey_refs.append(storey_entity)
                elements: List[int] = []

                # Locales: IfcSpace con su contorno real.
                for space in storey.get("spaces", []):
                    footprint = space["geometry"].get("footprint") or \
                        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
                    # v3.46.0: los espacios generados no llevan
                    # height_m propio; heredan la altura del nivel en
                    # vez de un 3.0 m fijo (niveles de 2.7/3.2/4.0 m
                    # llegaban mal a los visores BIM)
                    height = space["geometry"].get("height") \
                        or storey.get("height_m") or 3.0
                    space_placement = self.placement(0.0, 0.0, elevation)
                    solid = self.extruded_solid(footprint, height,
                                                space_placement)
                    space_entity = self.product(
                        "IfcSpace", self.guid(space["code"], "space"),
                        space.get("name", space["code"]), space_placement,
                        solid, tag=space["code"])
                    elements.append(space_entity)

                # Muros: sólido extruido del contorno del eje con espesor.
                for wall in storey.get("walls", []):
                    axis = wall["geometry"].get("axis") or [[0.0, 0.0],
                                                            [1.0, 0.0]]
                    thickness = wall["geometry"].get("thickness", 0.2) or 0.2
                    height = wall["geometry"].get("height", 3.0) or 3.0
                    footprint = self._wall_footprint(axis, thickness)
                    wall_placement = self.placement(0.0, 0.0, elevation)
                    solid = self.extruded_solid(footprint, height,
                                                wall_placement)
                    wall_entity = self.product(
                        "IfcWall", self.guid(wall["code"], "wall"),
                        wall.get("name", wall["code"]), wall_placement, solid,
                        tag=wall["code"])
                    elements.append(wall_entity)
                    self._wall_refs[wall["code"]] = wall_entity
                    self._wall_geom[wall["code"]] = (axis, thickness)
                    self._wall_elev[wall["code"]] = elevation
                    self._wall_storey[wall["code"]] = storey_entity

                # Estructura (spec 33-34 → IfcBeam/IfcColumn/IfcMember).
                for element in storey.get("elements", []):
                    category = element.get("category", "IfcElement")
                    axis = element["geometry"].get("axis") or [[0.0, 0.0],
                                                               [0.0, 0.0],
                                                               [0.0, 1.0]]
                    start, end = axis[0], axis[-1]
                    length = max(math.hypot(end[0] - start[0],
                                            end[1] - start[1]), 0.1)
                    elevation_start = element["geometry"].get("elevation",
                                                              elevation)
                    placement = self.placement(start[0], start[1],
                                               elevation_start)
                    width = 0.2
                    solid = self.extruded_solid(
                        [(-width / 2, -width / 2), (width / 2, -width / 2),
                         (width / 2, width / 2), (-width / 2, width / 2)],
                        length, placement)
                    element_entity = self.product(
                        category if category != "IfcElement" else "IfcMember",
                        self.guid(element["code"], "element"),
                        element.get("name", element["code"]), placement,
                        solid, tag=element["code"])
                    elements.append(element_entity)

                # Dispositivos de instalaciones/seguridad (spec 67
                # IfcDistributionElement).
                for device in storey.get("devices", []):
                    position = device["geometry"].get("position", [0.0, 0.0])
                    device_placement = self.placement(position[0], position[1],
                                                      elevation)
                    solid = self.extruded_solid(
                        [(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1)],
                        0.2, device_placement)
                    device_entity = self.product(
                        "IfcDistributionElement",
                        self.guid(device["code"], "device"),
                        device.get("name", device["code"]), device_placement,
                        solid, tag=device["code"])
                    elements.append(device_entity)

                contained.append((storey_entity, elements))
            if storey_refs:
                f.add(f"IFCRELAGGREGATES('{self.guid('bldg-storeys', 'rel')}',"
                      f"{f.ref(self.owner_history)},$,$,"
                      f"{f.ref(building_entity)},{f.refs(storey_refs)})")
            for storey_entity, elements in contained:
                if elements:
                    f.add(f"IFCRELCONTAINEDINSPATIALSTRUCTURE("
                          f"'{self.guid(f'storey-{storey_entity}', 'rel')}',"
                          f"{f.ref(self.owner_history)},$,$,"
                          f"{f.refs(elements)},{f.ref(storey_entity)})")

            # Puertas y ventanas como IfcDoor/IfcWindow + vano en el muro
            # (colocado en su posición REAL sobre el anfitrión y a la
            # cota del nivel: sin esto los visores externos no cortan
            # el hueco — corregido en v3.13.0).
            vanos_por_storey: List[Tuple[int, int]] = []
            for opening in tree.get("openings", []):
                host_code = self._host_code(opening)
                host = self._wall_refs.get(host_code)
                geom_muro = self._wall_geom.get(host_code)
                if host is None or geom_muro is None:
                    continue
                axis, thickness = geom_muro
                ifc_class = opening.get("category", "IfcOpeningElement")
                geometry = opening["geometry"]
                width = geometry.get("width", 0.9) or 0.9
                height = geometry.get("height", 2.1) or 2.1
                sill = geometry.get("sill", 0.0) or 0.0
                offset = geometry.get("offset", 0.0) or 0.0
                (x1, y1), (x2, y2) = axis[0], axis[1]
                largo = math.hypot(x2 - x1, y2 - y1) or 1.0
                u = ((x2 - x1) / largo, (y2 - y1) / largo)
                n = (-u[1], u[0])
                offset = max(0.0, min(offset, max(0.0, largo - width)))
                half_across = thickness / 2.0 + 0.02
                cx = x1 + u[0] * (offset + width / 2.0)
                cy = y1 + u[1] * (offset + width / 2.0)
                footprint = [
                    (cx - u[0] * width / 2.0 + n[0] * half_across,
                     cy - u[1] * width / 2.0 + n[1] * half_across),
                    (cx + u[0] * width / 2.0 + n[0] * half_across,
                     cy + u[1] * width / 2.0 + n[1] * half_across),
                    (cx + u[0] * width / 2.0 - n[0] * half_across,
                     cy + u[1] * width / 2.0 - n[1] * half_across),
                    (cx - u[0] * width / 2.0 - n[0] * half_across,
                     cy - u[1] * width / 2.0 - n[1] * half_across)]
                z0 = self._wall_elev.get(host_code, 0.0) + sill
                placement = self.placement(0.0, 0.0, z0)
                solid = self.extruded_solid(footprint, height, placement)
                opening_entity = self.product(
                    "IfcOpeningElement", self.guid(opening["code"], "opening"),
                    opening.get("name", opening["code"]), placement, solid,
                    tag=opening["code"])
                f.add(f"IFCRELVOIDSELEMENT('{self.guid(opening['code'] + '-void', 'rel')}',"
                      f"{f.ref(self.owner_history)},$,$,{f.ref(host)},"
                      f"{f.ref(opening_entity)})")
                fill_entity = self.product(
                    ifc_class if ifc_class in ("IfcDoor", "IfcWindow")
                    else "IfcDoor",
                    self.guid(opening["code"], "fill"),
                    opening.get("name", opening["code"]), placement,
                    solid, tag=opening["code"])
                # IfcRelFillsElement(RelatingOpeningElement,
                # RelatedBuildingElement): apertura primero, relleno
                # después (estaba invertido hasta v3.12.0).
                f.add(f"IFCRELFILLELEMENT('{self.guid(opening['code'] + '-fill', 'rel')}',"
                      f"{f.ref(self.owner_history)},$,$,"
                      f"{f.ref(opening_entity)},{f.ref(fill_entity)})")
                storey_del_muro = self._wall_storey.get(host_code)
                if storey_del_muro is not None:
                    vanos_por_storey.append((storey_del_muro, fill_entity))
            # Las puertas/ventanas van CONTENIDAS en su piso (práctica
            # estándar: IfcRelContainedInSpatialStructure), además del
            # hueco en el muro: así cualquier importador las coloca.
            por_storey: Dict[int, List[int]] = {}
            for storey_del_muro, fill_entity in vanos_por_storey:
                por_storey.setdefault(storey_del_muro, []).append(
                    fill_entity)
            for storey_del_muro, fills in por_storey.items():
                f.add(f"IFCRELCONTAINEDINSPATIALSTRUCTURE("
                      f"'{self.guid(f'storey-vanos-{storey_del_muro}', 'rel')}',"
                      f"{f.ref(self.owner_history)},$,$,{f.refs(fills)},"
                      f"{f.ref(storey_del_muro)})")

            # Redes como IfcDistributionSystem (spec 67).
            for network in tree.get("networks", []):
                f.add(f"IFCDISTRIBUTIONSYSTEM('{self.guid(network['code'], 'system')}',"
                      f"{f.ref(self.owner_history)},"
                      f"'{self._esc(network.get('name', network['code']))}',"
                      f"'{network.get('system', '')}',$,$,$)")

        def _host_code(self, opening: Dict[str, Any]) -> str:
            for relation in opening.get("relationships", []):
                if relation.get("kind") == "inWall":
                    return relation.get("target", "")
            return ""

        @staticmethod
        def _wall_footprint(axis: Sequence[Sequence[float]],
                            thickness: float) -> List[Tuple[float, float]]:
            (x1, y1), (x2, y2) = axis[0], axis[1]
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length * thickness / 2.0, dx / length * thickness / 2.0
            return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
                    (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]


__all__ = ["IfcExporter", "ifc_guid"]
