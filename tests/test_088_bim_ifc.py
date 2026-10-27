"""BIM projection and IFC4 export tests (spec sections 63, 64, 67)."""

from __future__ import annotations

import re

from tests.base import ARQGenTestCase


class TestBimService(ARQGenTestCase):
    """Proyección BIM del modelo semántico (spec 63)."""

    def test_record_dimensions(self):
        from services.bim_service import BimService
        ctx = self.demo_context()
        service = BimService(ctx)
        wall = ctx.architecture.get_by_code("WALL", "ARQ-WALL-001")
        record = service._record(wall)
        # Las 8 dimensiones del spec 63.
        for key in ("category", "geometry", "level", "material",
                    "properties", "classification", "systems",
                    "relationships"):
            self.assertIn(key, record)
        self.assertEqual(record["category"], "IfcWall")
        self.assertEqual(record["classification"], "EF_30_10")
        self.assertEqual(record["level"], "Nivel 1")
        ctx.close()

    def test_space_record_hosts_devices(self):
        from services.bim_service import BimService
        ctx = self.demo_context()
        service = BimService(ctx)
        space = ctx.architecture.get_by_code("SPACE", "ARQ-SPACE-001")
        record = service._record(space)
        host_kinds = [r["kind"] for r in record["relationships"]]
        self.assertIn("hostsDevice", host_kinds)
        self.assertTrue(record["systems"])
        ctx.close()

    def test_bim_tree_hierarchy(self):
        from services.bim_service import BimService
        ctx = self.demo_context()
        service = BimService(ctx)
        tree = service.bim_tree()
        self.assertEqual(tree["project"]["category"], "IfcProject")
        self.assertEqual(tree["site"]["category"], "IfcSite")
        self.assertEqual(tree["building"]["category"], "IfcBuilding")
        self.assertEqual(len(tree["storeys"]), 1)
        storey = tree["storeys"][0]
        self.assertEqual(len(storey["walls"]), 7)
        self.assertEqual(len(storey["spaces"]), 4)
        # Vanos con relación al muro huesped (para IfcRelVoidsElement).
        self.assertEqual(len(tree["openings"]), 7)
        for opening in tree["openings"]:
            kinds = [r["kind"] for r in opening["relationships"]]
            self.assertIn("inWall", kinds)
        self.assertTrue(tree["networks"])
        ctx.close()

    def test_structure_record(self):
        from services.bim_service import BimService
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="BIM STR")
        ctx.user = "tester"
        structure = StructureService(ctx)
        material = structure.create_material("Acero S275", "STEEL", fy_mpa=275.0)
        section = structure.create_section("IPE-300", "I_PROFILE", h_mm=300,
                                           b_mm=150, tw_mm=7.1, tf_mm=10.7)
        structure.create_element("BEAM", "Viga", material_ref=material.code,
                                 section_ref=section.code, start=(0, 0),
                                 end=(6, 0))
        service = BimService(ctx)
        element = ctx.structure.get_by_code("ELEMENT", "STR-ELEMENT-001")
        record = service._record(element)
        self.assertEqual(record["category"], "IfcBeam")
        self.assertEqual(record["material"], "Acero S275")
        relation_kinds = [r["kind"] for r in record["relationships"]]
        self.assertIn("hasMaterial", relation_kinds)
        self.assertIn("hasProfile", relation_kinds)
        ctx.close()


class TestIfcExporter(ARQGenTestCase):
    """Exportador IFC4 SPF (spec 67)."""

    def _export(self, ctx, tmp_name="demo.ifc"):
        from services.export_service import ExportService
        exporter = ExportService()
        path = exporter.export(ctx, "IFC", self.project_path(tmp_name))
        with open(path, "r", encoding="utf-8") as handle:
            return path, handle.read()

    def test_spf_structure_and_header(self):
        ctx = self.demo_context()
        _path, content = self._export(ctx)
        self.assertTrue(content.startswith("ISO-10303-21;"))
        self.assertIn("FILE_SCHEMA(('IFC4'));", content)
        self.assertTrue(content.rstrip().endswith("END-ISO-10303-21;"))
        ctx.close()

    def test_entity_counts_demo(self):
        ctx = self.demo_context()
        _path, content = self._export(ctx)
        self.assertEqual(content.count("IFCPROJECT("), 1)
        self.assertEqual(content.count("IFCSITE("), 1)
        self.assertEqual(content.count("IFCBUILDING("), 1)
        self.assertEqual(content.count("IFCBUILDINGSTOREY("), 1)
        self.assertEqual(content.count("IFCWALL("), 7)
        self.assertEqual(content.count("IFCSPACE("), 4)
        self.assertEqual(content.count("IFCDOOR("), 4)
        self.assertEqual(content.count("IFCWINDOW("), 3)
        self.assertEqual(content.count("IFCRELVOIDSELEMENT("), 7)
        self.assertEqual(content.count("IFCRELFILLELEMENT("), 7)
        # Un elemento de distribución por dispositivo de red (77 nodos).
        self.assertEqual(content.count("IFCDISTRIBUTIONELEMENT("), 77)
        # Un sistema de distribución por red de instalaciones (12 redes).
        self.assertEqual(content.count("IFCDISTRIBUTIONSYSTEM("), 12)
        ctx.close()

    def test_no_dangling_references(self):
        ctx = self.demo_context()
        _path, content = self._export(ctx)
        ids = set(int(m) for m in re.findall(r"^#(\d+)= ", content, re.M))
        refs = set(int(m) for m in re.findall(r"#(\d+)", content))
        self.assertEqual(refs - ids, set())
        ctx.close()

    def test_structure_elements_exported(self):
        from services.structure_service import StructureService
        ctx = self.application.create_project(self.project_path(), name="IFC STR")
        ctx.user = "tester"
        service = StructureService(ctx)
        material = service.create_material("Hormigón 25", "CONCRETE", fck_mpa=25.0)
        section = service.create_section("Pilar 30x30", "RECTANGLE",
                                         h_mm=300, b_mm=300)
        service.create_element("COLUMN", "Pilar", material_ref=material.code,
                               section_ref=section.code, start=(0, 0),
                               end=(0, 0), z0=0.0, z1=3.0)
        service.create_element("BEAM", "Viga", material_ref=material.code,
                               section_ref=section.code, start=(0, 0),
                               end=(6, 0))
        _path, content = self._export(ctx, "struct.ifc")
        self.assertEqual(content.count("IFCCOLUMN("), 1)
        self.assertEqual(content.count("IFCBEAM("), 1)
        ctx.close()

    def test_global_ids_deterministic(self):
        from exporters.ifc_exporter import ifc_guid
        guid1 = ifc_guid("550e8400-e29b-41d4-a716-446655440000")
        guid2 = ifc_guid("550e8400-e29b-41d4-a716-446655440000")
        guid3 = ifc_guid("550e8400-e29b-41d4-a716-446655440001")
        self.assertEqual(guid1, guid2)
        self.assertNotEqual(guid1, guid3)
        self.assertEqual(len(guid1), 22)
        allowed = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                      "abcdefghijklmnopqrstuvwxyz_$")
        self.assertTrue(set(guid1) <= allowed)

    def test_roundtrip_json_untouched(self):
        """IFC no rompe los demás formatos (spec 64 interoperabilidad)."""
        from services.export_service import ExportService
        ctx = self.demo_context()
        exporter = ExportService()
        ifc_path = exporter.export(ctx, "IFC", self.project_path("a.ifc"))
        json_path = exporter.export(ctx, "JSON", self.project_path("a.json"))
        import os
        self.assertTrue(os.path.getsize(ifc_path) > 1000)
        self.assertTrue(os.path.getsize(json_path) > 1000)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
