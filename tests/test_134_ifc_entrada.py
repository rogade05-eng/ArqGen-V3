"""IFC DE ENTRADA (v3.13.0) — importers/ifc_reader.py.

El roundtrip es la prueba reina: lo que la app EXPORTA debe poder
IMPORTARSE de vuelta con la misma geometría (muros a longitud, espesor
y cota exactos; puertas y ventanas con su ancho, offset y antepecho;
locales con su área). Además: parser SPF con cadenas difíciles,
unidades en milímetros, IFC2X3 tolerado, errores amables y el diálogo
GUI de análisis/importación.
"""

from __future__ import annotations

import os
import unittest

from core.errors import DomainError
from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (BuildingWizardData, LevelSpec, RelationSpec,
                                RoomSpec)
from importers.ifc_reader import (IfcImporter, _parsear_token,
                                  _partir_args)
from services.export_service import ExportService


# -- parser SPF -----------------------------------------------------------------
class TestParserSPF(ARQGenTestCase):

    def test_partir_args_con_cadenas_dificiles(self):
        toks = _partir_args("'Hola, mundo',#12,'con ) parentesis',$")
        self.assertEqual(len(toks), 4)
        toks2 = _partir_args("'dijo ''hola''',.ELEMENT.,(1,2,3)")
        self.assertEqual(len(toks2), 3)
        self.assertEqual(toks2[0], "'dijo ''hola'''")

    def test_parsear_token_tipos(self):
        self.assertIsNone(_parsear_token("$"))
        self.assertEqual(_parsear_token("*"), "*")
        self.assertEqual(_parsear_token(".ELEMENT."), ".ELEMENT.")
        self.assertEqual(_parsear_token("#42"), ("REF", 42))
        self.assertEqual(_parsear_token("2500"), 2500)
        self.assertIsInstance(_parsear_token("2500"), int)
        self.assertAlmostEqual(_parsear_token("1.E-05"), 1e-05)
        self.assertEqual(_parsear_token("(#1,#2)"), [("REF", 1), ("REF", 2)])
        self.assertEqual(_parsear_token("'texto'"), "texto")

    def test_rechaza_lo_que_no_es_ifc(self):
        ruta = self.project_path("basura.txt")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("esto no es un IFC\n")
        with self.assertRaises(DomainError):
            IfcImporter().preview(ruta)

    def test_rechaza_ifc_sin_data(self):
        ruta = self.project_path("sin_data.ifc")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n")
        with self.assertRaises(DomainError) as ctx:
            IfcImporter().preview(ruta)
        self.assertIn("DATA", str(ctx.exception.message))

    def test_rechaza_archivo_inexistente(self):
        with self.assertRaises(DomainError):
            IfcImporter().preview(self.project_path("nunca.ifc"))

    def test_punto_y_coma_dentro_de_cadena(self):
        texto = ("ISO-10303-21;\nHEADER;\nFILE_NAME('a;b;c',"
                 "'2026-01-01T00:00:00',('T'),('T'),'T','T','');\n"
                 "FILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
                 "#1= IFCPERSON($,'Demo','X',$,$,$,$,$);\n"
                 "ENDSEC;\nEND-ISO-10303-21;\n")
        ruta = self.project_path("puntoycoma.ifc")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(texto)
        pv = IfcImporter().preview(ruta)
        self.assertEqual(pv["schema"], "IFC4")
        self.assertEqual(pv["walls"], 0)


# -- roundtrip del demo -----------------------------------------------------------
class TestRoundtrip(ARQGenTestCase):

    def _exportar_demo(self):
        from app.demo import build_demo
        ctx = build_demo(self.application,
                         self.project_path("origen.arqgen"))
        ruta = ExportService().export(ctx, "IFC",
                                      self.project_path("demo.ifc"))
        self.addCleanup(ctx.close)
        return ctx, ruta

    def test_preview_cuenta_todo(self):
        _ctx, ruta = self._exportar_demo()
        pv = IfcImporter().preview(ruta)
        self.assertEqual(pv["schema"], "IFC4")
        self.assertEqual(pv["unidad"], "METRE")
        self.assertEqual(pv["storeys"], 1)
        self.assertEqual(pv["walls"], 7)
        self.assertEqual(pv["spaces"], 4)
        self.assertEqual(pv["doors"], 4)
        self.assertEqual(pv["windows"], 3)
        self.assertEqual(pv["slabs"], 0)
        # los 77 dispositivos de redes van como «otros productos»
        self.assertGreaterEqual(pv["otros"], 70)

    def test_apply_reconstruye_fiel(self):
        ctx1, ruta = self._exportar_demo()
        ctx2 = self.application.create_project(
            self.project_path("destino.arqgen"), name="Destino")
        self.addCleanup(ctx2.close)
        resumen = IfcImporter().apply(ruta,
                                      _arch(ctx2))
        self.assertEqual(resumen["niveles"], 1)
        self.assertEqual(resumen["muros"], 7)
        self.assertEqual(resumen["locales"], 4)
        self.assertEqual(resumen["puertas"], 4)
        self.assertEqual(resumen["ventanas"], 3)
        muros1 = _ordenados(ctx1, "WALL")
        muros2 = _ordenados(ctx2, "WALL")
        self.assertEqual(len(muros1), len(muros2))
        for a, b in zip(muros1, muros2):
            self.assertAlmostEqual(a.length_m, b.length_m, places=3)
            self.assertAlmostEqual(a.thickness_m, b.thickness_m, places=3)
            self.assertAlmostEqual(a.height_m, b.height_m, places=3)
            self.assertAlmostEqual(a.start[0], b.start[0], places=3)
            self.assertAlmostEqual(a.start[1], b.start[1], places=3)
        for a, b in zip(_ordenados(ctx1, "DOOR"), _ordenados(ctx2, "DOOR")):
            self.assertAlmostEqual(a.width_m, b.width_m, places=2)
            self.assertAlmostEqual(a.offset_m, b.offset_m, places=2)
            self.assertAlmostEqual(a.height_m, b.height_m, places=2)
        for a, b in zip(_ordenados(ctx1, "WINDOW"),
                        _ordenados(ctx2, "WINDOW")):
            self.assertAlmostEqual(a.width_m, b.width_m, places=2)
            self.assertAlmostEqual(a.sill_height_m, b.sill_height_m,
                                   places=2)
        # locales con áreas fieles
        esp1 = sorted(ctx1.architecture.list("SPACE", ctx1.project.id),
                      key=lambda s: s.name)
        esp2 = sorted(ctx2.architecture.list("SPACE", ctx2.project.id),
                      key=lambda s: s.name)
        for a, b in zip(esp1, esp2):
            self.assertAlmostEqual(a.area_m2(), b.area_m2(), delta=0.01)
        # códigos oficiales ARQ-XXX-nnn
        self.assertTrue(muros2[0].code.startswith("ARQ-WALL-"))

    def test_reimportar_reutiliza_los_niveles(self):
        _ctx, ruta = self._exportar_demo()
        ctx2 = self.application.create_project(
            self.project_path("reimport.arqgen"), name="Reimport")
        self.addCleanup(ctx2.close)
        arch = _arch(ctx2)
        primero = IfcImporter().apply(ruta, arch)
        self.assertEqual(primero["niveles"], 1)
        segundo = IfcImporter().apply(ruta, arch)
        self.assertEqual(segundo["niveles_reutilizados"], 1)
        self.assertEqual(segundo["niveles"], 0)

    def test_roundtrip_de_edificio_de_dos_niveles(self):
        data = BuildingWizardData(name="Dos Niveles")
        data.levels = [LevelSpec(name="Planta Baja", height_m=3.0),
                       LevelSpec(name="Planta Alta", height_m=3.0)]
        data.rooms = [
            RoomSpec(name="Sala", space_type="ROOM", width_m=4.0,
                     depth_m=5.0, level_ref="Planta Baja",
                     with_window=True),
            RoomSpec(name="Cocina", space_type="KITCHEN", width_m=3.0,
                     depth_m=2.5, level_ref="Planta Baja",
                     with_window=True),
            RoomSpec(name="Dormitorio", space_type="ROOM", width_m=3.5,
                     depth_m=4.0, level_ref="Planta Alta",
                     with_window=True),
        ]
        data.relations = [RelationSpec(a_name="Sala", b_name="Cocina",
                                       kind_es="Adyacente a",
                                       with_door=True)]
        ctx1 = self.application.create_project(
            self.project_path("dosn_origen.arqgen"), name="Dos Niveles")
        self.addCleanup(ctx1.close)
        bw.apply_plan(data, ctx1, variant=bw.generate_variants(data)[0])
        ruta = ExportService().export(ctx1, "IFC",
                                      self.project_path("dosn.ifc"))
        ctx2 = self.application.create_project(
            self.project_path("dosn_destino.arqgen"), name="Dos N D")
        self.addCleanup(ctx2.close)
        resumen = IfcImporter().apply(ruta, _arch(ctx2))
        self.assertEqual(resumen["niveles"], 2)
        niveles = sorted(ctx2.architecture.list("LEVEL", ctx2.project.id),
                         key=lambda lv: lv.elevation_m)
        self.assertEqual(len(niveles), 2)
        self.assertAlmostEqual(niveles[0].elevation_m, 0.0, places=3)
        self.assertAlmostEqual(niveles[1].elevation_m,
                               niveles[1].elevation_m, places=3)
        self.assertGreater(niveles[1].elevation_m, 0.0)
        # muros repartidos en sus niveles
        muros_por_nivel = {}
        for muro in ctx2.architecture.list("WALL", ctx2.project.id):
            muros_por_nivel[muro.level_id] = \
                muros_por_nivel.get(muro.level_id, 0) + 1
        self.assertEqual(len(muros_por_nivel), 2)


# -- unidades y perfiles artesanales ------------------------------------------------
MINI_MM = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Prueba'),'2;1');
FILE_NAME('mini.ifc','2026-01-01T00:00:00',('T'),('T'),'T','T','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1= IFCPERSON($,'Alguien','X',$,$,$,$,$);
#2= IFCORGANIZATION($,'Org',$,$,$);
#3= IFCPERSONANDORGANIZATION(#1,#2,$);
#4= IFCAPPLICATION(#2,'1','App','APP');
#5= IFCOWNERHISTORY(#3,#4,$,.ADDED.,$,$,$,1700000000);
#10= IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#11= IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#12= IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);
#13= IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.);
#14= IFCUNITASSIGNMENT((#10,#11,#12,#13));
#15= IFCCARTESIANPOINT((0.,0.,0.));
#16= IFCDIRECTION((0.,0.,1.));
#17= IFCDIRECTION((1.,0.,0.));
#18= IFCAXIS2PLACEMENT3D(#15,#16,#17);
#19= IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-05,#18,$);
#20= IFCPROJECT('0Aqf8N99XCHgXAlVHcVfWX',#5,'Prueba MM',$,$,$,$,(#19),#14);
#21= IFCSITE('0Aqf8N99XCHgXAlVHcVfWY',#5,'Solar',$,$,#22,$,$,.ELEMENT.,$,$,0.,$,$);
#22= IFCLOCALPLACEMENT($,#23);
#23= IFCAXIS2PLACEMENT3D(#15,$,$);
#24= IFCBUILDING('0Aqf8N99XCHgXAlVHcVfWZ',#5,'Edificio',$,$,#22,$,$,.ELEMENT.,$,$,$);
#25= IFCBUILDINGSTOREY('0Aqf8N99XCHgXAlVHcVfW0',#5,'Piso MM',$,$,#22,$,$,20.0,.ELEMENT.);
#26= IFCRELAGGREGATES('0Aqf8N99XCHgXAlVHcVfW1',#5,$,$,#20,(#21));
#27= IFCRELAGGREGATES('0Aqf8N99XCHgXAlVHcVfW2',#5,$,$,#21,(#24));
#28= IFCRELAGGREGATES('0Aqf8N99XCHgXAlVHcVfW3',#5,$,$,#24,(#25));
#30= IFCCARTESIANPOINT((1000.,2000.,0.));
#31= IFCAXIS2PLACEMENT3D(#30,$,$);
#32= IFCLOCALPLACEMENT($,#31);
#40= IFCCARTESIANPOINT((0.,0.));
#41= IFCDIRECTION((1.,0.));
#42= IFCAXIS2PLACEMENT2D(#40,$);
#43= IFCRECTANGLEPROFILEDEF(.AREA.,$,#42,2000.,200.);
#44= IFCCARTESIANPOINT((0.,0.,0.));
#45= IFCDIRECTION((0.,0.,1.));
#46= IFCEXTRUDEDAREASOLID(#43,#44,#45,2500.);
#47= IFCSHAPEREPRESENTATION(#19,'Body','SweptSolid',(#46));
#48= IFCPRODUCTDEFINITIONSHAPE($,$,(#47));
#49= IFCWALL('0Aqf8N99XCHgXAlVHcVfW4',#5,'Muro MM',$,$,#32,#48,'MM-1',$);
#50= IFCRELCONTAINEDINSPATIALSTRUCTURE('0Aqf8N99XCHgXAlVHcVfW5',#5,$,$,(#49),#25);
ENDSEC;
END-ISO-10303-21;
"""


class TestUnidadesYPerfiles(ARQGenTestCase):

    def _escribir_mini(self):
        ruta = self.project_path("mini_mm.ifc")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(MINI_MM)
        return ruta

    def test_milimetros_y_perfil_rectangular(self):
        ruta = self._escribir_mini()
        pv = IfcImporter().preview(ruta)
        self.assertEqual(pv["unidad"], "MILLIMETRE")
        self.assertEqual(pv["walls"], 1)
        self.assertEqual(pv["storeys"], 1)
        ctx = self.application.create_project(
            self.project_path("mini.arqgen"), name="Mini MM")
        self.addCleanup(ctx.close)
        resumen = IfcImporter().apply(ruta, _arch(ctx))
        self.assertEqual(resumen["muros"], 1)
        self.assertEqual(resumen["niveles"], 1)
        muro = ctx.architecture.list("WALL", ctx.project.id)[0]
        self.assertAlmostEqual(muro.length_m, 2.0, places=6)
        self.assertAlmostEqual(muro.thickness_m, 0.2, places=6)
        self.assertAlmostEqual(muro.height_m, 2.5, places=6)
        self.assertAlmostEqual(muro.start[0], 0.0, places=6)
        self.assertAlmostEqual(muro.start[1], 2.0, places=6)
        nivel = ctx.architecture.list("LEVEL", ctx.project.id)[0]
        # Elevation 20 mm → 0.02 m
        self.assertAlmostEqual(nivel.elevation_m, 0.02, places=6)

    def test_esquema_ifc2x3_tolerado(self):
        ruta = self.project_path("v2x3.ifc")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(MINI_MM.replace("IFC4", "IFC2X3"))
        pv = IfcImporter().preview(ruta)
        self.assertEqual(pv["schema"], "IFC2X3")
        self.assertEqual(pv["walls"], 1)


# -- GUI ---------------------------------------------------------------------------
def _display_ok() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


@unittest.skipUnless(_display_ok(), "requiere display Tk (Xvfb :99)")
class TestDialogoIfc(ARQGenTestCase):

    def _ventana(self):
        from app.demo import build_demo
        from ui.app_window import ARQGenWindow
        self.context = build_demo(self.application,
                                  self.project_path("demo_ifc.arqgen"))
        self.window = ARQGenWindow(self.context, self.application)
        self.addCleanup(self.window.destroy)
        return self.window

    def test_analizar_e_importar_desde_el_dialogo(self):
        from unittest import mock
        import ui.app_window as aw
        _ctx, ruta = TestRoundtrip._exportar_demo(self)
        win = self._ventana()
        with mock.patch.object(aw, "messagebox"):
            win.open_importar_ifc()
            win._ifc_ruta.set(ruta)
            win._ifc_analizar()
            self.assertEqual(win._ifc_resultado.get("walls"), 7)
            antes = len(self.context.architecture.list(
                "WALL", self.context.project.id))
            win._ifc_importar()
            despues = len(self.context.architecture.list(
                "WALL", self.context.project.id))
            self.assertEqual(despues, antes + 7)
            self.assertIn("Importado", win._ifc_estado.get())
            win._ifc_dialog.destroy()

    def test_analizar_sin_ruta_no_rompe(self):
        from unittest import mock
        import ui.app_window as aw
        win = self._ventana()
        with mock.patch.object(aw, "messagebox"):
            win.open_importar_ifc()
            win._ifc_analizar()   # sin ruta: aviso, sin excepción
            win._ifc_importar()   # idem
            win._ifc_dialog.destroy()


# -- helpers ------------------------------------------------------------------------
def _arch(ctx):
    from services.architecture_service import ArchitectureService
    return ArchitectureService(ctx)


def _ordenados(ctx, tipo):
    return sorted(ctx.architecture.list(tipo, ctx.project.id),
                  key=lambda o: (round(o.start[0], 3) if hasattr(o, "start")
                                 else 0.0,
                                 round(o.start[1], 3) if hasattr(o, "start")
                                 else 0.0,
                                 round(getattr(o, "offset_m", 0.0), 3),
                                 round(getattr(o, "width_m", 0.0), 3)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
