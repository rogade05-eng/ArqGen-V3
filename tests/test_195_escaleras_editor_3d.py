"""Creación, edición coherente y persistencia de escaleras de la web 3D."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from app import rpc_server as servidor
from domain import escaleras as esc
from services.context import ApplicationContext
from services.import_service import ImportService
from tests.test_193_vista_3d_web import FICHAS, RECT, rpc
from ui import view3d


class TestEscalerasEditor3D(unittest.TestCase):
    def setUp(self):
        self.sid = rpc("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})["result"]["id"]
        self.ctx = servidor._proyecto_sesion({"id": self.sid})["ctx"]

    def tearDown(self):
        servidor._cerrar_proyecto(self.sid)
        servidor._SESION.pop(self.sid, None)

    def crear(self, tipo="L", **kw):
        return rpc("crear_escalera_3d", {"id": self.sid, "tipo": tipo, **kw})

    def editar(self, info, valores):
        return rpc("editar_3d", {"id": self.sid, "tipo": "STAIR", "elemento_id": info["id"],
                                 "revision": info["revision"], "valores": valores})

    def test_crear_varias_sin_borrar_y_seleccionar(self):
        a = self.crear("L")["result"]
        b = self.crear("U", nivel=0)["result"]
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(self.ctx.architecture.count("STAIR", self.ctx.project.id), 2)
        self.assertEqual(next(x for x in a["campos"] if x["campo"] == "tipo")["opciones"], list(esc.TIPOS))
        self.assertTrue(a["avisos"])
        vista = rpc("vista_3d", {"id": self.sid})["result"]
        for info in (a, b):
            self.assertTrue(any(c["entidad_tipo"] == "STAIR" and c["entidad_id"] == info["id"]
                                for c in vista["caras"]))
            obj = self.ctx.architecture.get("STAIR", info["id"])
            self.assertTrue(obj.metadata["pasos"])
        self.assertIn("error", self.crear("espiral"))
        self.assertIn("error", self.crear("L", nivel=999))
        self.assertIn("error", self.crear("L", nivel=True))
        self.assertEqual(self.ctx.architecture.count("STAIR", self.ctx.project.id), 2)

    def test_traslacion_en_2d_3d_sin_doble_rotacion(self):
        info = self.crear("L")["result"]
        obj = self.ctx.architecture.get("STAIR", info["id"])
        camara = view3d.Camara3D()
        antes = view3d.caras_de_escalera(obj, 0, 0, camara)
        actual = self.editar(info, {"x": obj.x + 10, "y": obj.y - 7})["result"]
        nuevo = self.ctx.architecture.get("STAIR", info["id"])
        despues = view3d.caras_de_escalera(nuevo, 0, 0, camara)
        self.assertEqual(obj.metadata["pasos"], nuevo.metadata["pasos"])
        self.assertEqual(len(antes), len(despues))
        for ca, cb in zip(antes, despues):
            for pa, pb in zip(ca.puntos, cb.puntos):
                self.assertAlmostEqual(pb[0] - pa[0], 10)
                self.assertAlmostEqual(pb[1] - pa[1], -7)
                self.assertAlmostEqual(pb[2], pa[2])
        self.assertEqual(actual["revision"], info["revision"] + 1)
        from ui.models import CanvasModel
        from tests.test_146_escaleras import _ExplorerStub
        modelo = CanvasModel(self.ctx, _ExplorerStub(self.ctx))
        prims = modelo._architecture_primitives(nuevo.level_id)
        planta = next(p for p in prims if p.kind == "stair" and p.row.uid == nuevo.id)
        self.assertAlmostEqual(planta.coords[0][0], nuevo.metadata["outline"][0][0] + nuevo.x)
        self.assertAlmostEqual(planta.coords[0][1], nuevo.metadata["outline"][0][1] + nuevo.y)

    def test_dimensiones_tipologias_avisos_y_validacion_atomica(self):
        info = self.crear("recta")["result"]
        uid = info["id"]
        original = self.ctx.architecture.get("STAIR", uid)
        for valores in ({"tipo": "arbitraria"}, {"width_m": 0.5}, {"x": float("nan")},
                        {"desnivel_m": 20, "contrahuella_m": 0.05}, {"huella_m": True},
                        {"metadata": {}}, {"tipo": "U", "width_m": -2}):
            with self.subTest(valores=valores):
                self.assertIn("error", self.editar(info, valores))
                self.assertEqual(self.ctx.architecture.get("STAIR", uid).revision, info["revision"])
        self.assertEqual(self.ctx.architecture.get("STAIR", uid).metadata, original.metadata)
        for tipo in esc.TIPOS:
            result = self.editar(info, {"tipo": tipo, "rotation_deg": 37,
                                       "width_m": 1.2, "desnivel_m": 3.2,
                                       "contrahuella_m": 0.17, "huella_m": 0.29})
            self.assertIn("result", result, result)
            info = result["result"]
            obj = self.ctx.architecture.get("STAIR", uid)
            self.assertEqual(obj.tipo, tipo)
            geo = esc.geometria(tipo, 3.2, .17, .29, 1.2, 37)
            self.assertEqual(obj.metadata["n_contrahuellas"], geo["n_contrahuellas"])
            self.assertEqual(obj.metadata["pasos"], geo["pasos"])
            self.assertAlmostEqual(obj.contrahuella_m, 3.2 / geo["n_contrahuellas"], places=6)
            self.assertAlmostEqual(max(c["z1"] for c in geo["pasos"]), 3.2, places=3)
            self.assertEqual("caracol" in obj.metadata, tipo == "caracol")
        viejo = dict(info)
        aviso = self.editar(info, {"huella_m": 0.9})["result"]
        self.assertTrue(any("Blondel" in x for x in aviso["avisos"]))
        self.assertIn("error", self.editar(viejo, {"x": 2}))

    def test_borrar_y_deshacer_revision_y_rollback(self):
        info = self.crear("L")["result"]
        otra = self.crear("U")["result"]
        args = {"id": self.sid, "elemento_id": info["id"], "revision": info["revision"]}
        self.assertIn("error", rpc("borrar_escalera_3d", {**args, "revision": True}))
        with mock.patch("services.edicion_3d.ArchitectureService._audit", side_effect=ValueError("fallo")):
            self.assertIn("error", rpc("borrar_escalera_3d", args))
        self.assertIsNotNone(self.ctx.architecture.get("STAIR", info["id"]))
        self.assertIn("result", rpc("borrar_escalera_3d", args))
        self.assertIsNone(self.ctx.architecture.get("STAIR", info["id"]))
        self.assertIsNotNone(self.ctx.architecture.get("STAIR", otra["id"]))
        with tempfile.TemporaryDirectory() as d:
            salida = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["JSON"]})["result"]
            with open(salida["proyecto"]["ruta"], encoding="utf8") as f:
                ids = [e["id"] for e in json.load(f)["entities"]["STAIR"]]
            self.assertNotIn(info["id"], ids)
        self.assertIn("result", rpc("deshacer_3d", {"id": self.sid}))
        recuperada = self.ctx.architecture.get("STAIR", info["id"])
        self.assertGreater(recuperada.revision, info["revision"])
        self.assertIn("error", rpc("borrar_escalera_3d", args))
        self.assertIn("result", rpc("rehacer_3d", {"id": self.sid}))
        self.assertIsNone(self.ctx.architecture.get("STAIR", info["id"]))
        self.assertIn("result", rpc("deshacer_3d", {"id": self.sid}))
        self.assertGreater(self.ctx.architecture.get("STAIR", info["id"]).revision, recuperada.revision)

    def test_avisos_interferencias_mismo_nivel_y_sin_interferencia(self):
        from services.avisos_3d import avisos_escalera, _solapan
        self.assertTrue(_solapan([(0,0),(2,0),(2,2),(0,2)], [(1,1),(3,1),(3,3),(1,3)]))
        self.assertFalse(_solapan([(0,0),(1,0),(1,1),(0,1)], [(2,2),(3,2),(3,3),(2,3)]))
        a = self.crear("recta")["result"]
        b = self.crear("recta")["result"]
        a = self.editar(a, {"x": 5000, "y": 5000})["result"]
        b = self.editar(b, {"x": 5000, "y": 5000})["result"]
        ea = self.ctx.architecture.get("STAIR", a["id"])
        eb = self.ctx.architecture.get("STAIR", b["id"])
        self.assertTrue(any(eb.code in aviso for aviso in avisos_escalera(self.ctx, ea)))
        b = self.editar(b, {"x": 5100})["result"]
        self.assertFalse(any(eb.code in aviso for aviso in avisos_escalera(self.ctx, ea)))

    def test_ifc_falla_si_escalera_no_tiene_geometria(self):
        from services.commands_impl import UpdateEntityCommand
        from exporters.ifc_exporter import IfcExporter
        info = self.crear()["result"]
        obj = self.ctx.architecture.get("STAIR", info["id"])
        obj.metadata = {}
        self.ctx.command_bus.execute(UpdateEntityCommand(obj), self.ctx)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "sin geometría"):
                IfcExporter().export(self.ctx, os.path.join(d, "sin_geometria.ifc"))
            self.assertFalse(os.path.exists(os.path.join(d, "sin_geometria.ifc")))

    def test_ifc_guid_y_texto_step_sin_perder_unicode(self):
        from exporters.ifc_exporter import ifc_guid, _step_text
        from importers.ifc_reader import _parsear_token
        self.assertEqual(ifc_guid("0123456789abcdef0123456789abcdef"), "018qLdYQlDxm4ZHMU9gytl")
        for texto in ("Niño O'Brien", "España 😀", "literal " + chr(92) + "X2" + chr(92) + "00F1" + chr(92) + "X0" + chr(92)):
            self.assertEqual(_parsear_token("'" + _step_text(texto) + "'"), texto)

    def test_ifc_escaleras_parser_externo_y_geometria(self):
        try:
            import ifcopenshell
            import ifcopenshell.validate
            import ifcopenshell.geom
        except ImportError:
            self.skipTest("ifcopenshell opcional no instalado")
        for i, tipo in enumerate(esc.TIPOS):
            info = self.crear(tipo)["result"]
            self.editar(info, {"x": 60 + i*20, "y": 80, "rotation_deg": 45})
        with tempfile.TemporaryDirectory() as d:
            res = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["IFC"]})["result"]
            self.assertFalse(res["errores"])
            modelo = ifcopenshell.open(res["archivos"]["IFC"]["ruta"])
            from exporters.ifc_exporter import _step_text
            texto = "Niño O'Brien 😀"
            with tempfile.NamedTemporaryFile(suffix=".ifc", mode="w", encoding="ascii", delete=False) as f:
                f.write("ISO-10303-21;HEADER;FILE_DESCRIPTION(('x'),'2;1');"
                        "FILE_NAME('x','2026-01-01T00:00:00',(''),(''),'','','');"
                        "FILE_SCHEMA(('IFC4'));ENDSEC;DATA;#1=IFCPERSON($,'" +
                        _step_text(texto) + "','Luis',$,$,$,$,$);ENDSEC;END-ISO-10303-21;")
                unicode_ifc = f.name
            self.addCleanup(lambda: os.path.exists(unicode_ifc) and os.unlink(unicode_ifc))
            self.assertEqual(ifcopenshell.open(unicode_ifc).by_type("IfcPerson")[0].FamilyName, texto)
            escaleras = modelo.by_type("IfcStair")
            self.assertEqual(len(escaleras), 4)
            self.assertEqual({e.PredefinedType for e in escaleras},
                             {"STRAIGHT_RUN_STAIR", "QUARTER_TURN_STAIR", "HALF_TURN_STAIR", "SPIRAL_STAIR"})
            logger = ifcopenshell.validate.json_logger()
            ifcopenshell.validate.validate(modelo, logger)
            self.assertFalse(logger.statements, logger.statements[:3])
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            for escalera in escaleras:
                self.assertTrue(escalera.ContainedInStructure)
                self.assertGreater(len(escalera.Representation.Representations[0].Items), 2)
                mesh = ifcopenshell.geom.create_shape(settings, escalera)
                self.assertTrue(mesh.geometry.verts)
                self.assertGreater(min(mesh.geometry.verts[::3]), 50)

    def test_rotacion_no_cambia_numero_por_redondeo(self):
        info = self.crear()["result"]
        uid = info["id"]
        info = self.editar(info, {"desnivel_m": 3.0, "contrahuella_m": 0.115})["result"]
        n = self.ctx.architecture.get("STAIR", uid).metadata["n_contrahuellas"]
        self.assertEqual(n, 27)
        info = self.editar(info, {"rotation_deg": 75})["result"]
        self.assertEqual(self.ctx.architecture.get("STAIR", uid).metadata["n_contrahuellas"], n)

    def test_exportar_planos_dxf_y_svg_con_posicion_y_nivel(self):
        import ezdxf
        import xml.etree.ElementTree as ET
        info = self.crear("L")["result"]
        self.editar(info, {"x": 70, "y": 80, "rotation_deg": 45})
        escalera = self.ctx.architecture.get("STAIR", info["id"])
        p0 = escalera.metadata["outline"][0]
        expected_x, expected_y = p0[0] + 70, p0[1] + 80
        with tempfile.TemporaryDirectory() as d:
            r = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d,
                "formatos": ["DXF", "DXF_R12", "SVG", "IFC"]})["result"]
            self.assertFalse(r["errores"], r["errores"])
            with open(r["archivos"]["IFC"]["ruta"], encoding="utf-8") as archivo:
                self.assertIn("IFCSTAIR(", archivo.read())
            dxf = ezdxf.readfile(r["archivos"]["DXF"]["ruta"])
            entities = [e for layout in dxf.layouts for e in layout if e.dxf.layer == "ARQ-STAIR"]
            polilinea = next(e for e in entities if e.dxftype() == "LWPOLYLINE")
            p = list(polilinea.get_points("xy"))[0]
            self.assertAlmostEqual(p[0], expected_x, places=3)
            self.assertAlmostEqual(p[1], expected_y, places=3)
            r12 = ezdxf.readfile(r["archivos"]["DXF_R12"]["ruta"])
            lines = [e for e in r12.modelspace() if e.dxf.layer == "ARQ-STAIR"]
            self.assertTrue(lines)
            self.assertTrue(all(e.dxftype() == "LINE" for e in lines))
            self.assertAlmostEqual(lines[0].dxf.start.x, expected_x, places=3)
            raiz = ET.parse(r["archivos"]["SVG"]["ruta"]).getroot()
            poligono = next(x for x in raiz.iter() if x.tag.endswith("polygon") and x.get("class") == "escalera")
            px, py = map(float, poligono.get("points").split()[0].split(","))
            self.assertAlmostEqual(px, expected_x, places=3)
            self.assertAlmostEqual(py, expected_y, places=3)
            x, y, w, h = map(float, raiz.attrib["viewBox"].split())
            self.assertTrue(x <= px <= x + w and y <= py <= y + h)

    def test_deshacer_rehacer_edicion_y_creacion_revisiones_monotonas(self):
        info = self.crear("L")["result"]
        uid = info["id"]
        anterior = self.ctx.architecture.get("STAIR", uid)
        info = self.editar(info, {"tipo": "caracol", "x": 9})["result"]
        revision_editada = info["revision"]
        undo = rpc("deshacer_3d", {"id": self.sid})
        self.assertIn("result", undo, undo)
        restaurada = self.ctx.architecture.get("STAIR", uid)
        self.assertEqual(restaurada.tipo, "L")
        self.assertEqual(restaurada.x, anterior.x)
        self.assertGreater(restaurada.revision, revision_editada)
        self.assertIn("error", self.editar(info, {"x": 99}))  # formulario obsoleto
        redo = rpc("rehacer_3d", {"id": self.sid})
        self.assertIn("result", redo, redo)
        restaurada = self.ctx.architecture.get("STAIR", uid)
        self.assertEqual((restaurada.tipo, restaurada.x), ("caracol", 9))
        self.assertGreater(restaurada.revision, revision_editada + 1)
        rpc("deshacer_3d", {"id": self.sid})  # deshace edición
        previo_borrado = self.ctx.architecture.get("STAIR", uid).revision
        self.assertIn("result", rpc("deshacer_3d", {"id": self.sid}))  # deshace creación
        self.assertIsNone(self.ctx.architecture.get("STAIR", uid))
        self.assertIn("result", rpc("rehacer_3d", {"id": self.sid}))
        recuperada = self.ctx.architecture.get("STAIR", uid)
        self.assertGreater(recuperada.revision, previo_borrado)
        self.assertEqual(recuperada.tipo, "L")
        self.assertIn("result", rpc("rehacer_3d", {"id": self.sid}))
        self.assertEqual(self.ctx.architecture.get("STAIR", uid).tipo, "caracol")
        self.assertIn("error", rpc("rehacer_3d", {"id": self.sid}))
        with tempfile.TemporaryDirectory() as d:
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["JSON"]})["result"]
            with open(exp["proyecto"]["ruta"], encoding="utf8") as f:
                snap = json.load(f)
            self.assertEqual(next(s for s in snap["entities"]["STAIR"] if s["id"] == uid)["tipo"], "caracol")

    def test_fallo_al_deshacer_no_pierde_historial_ni_mutacion(self):
        info = self.crear()["result"]
        info = self.editar(info, {"x": 5})["result"]
        with mock.patch("services.historial_3d.ArchitectureService._audit", side_effect=ValueError("fallo")):
            r = rpc("deshacer_3d", {"id": self.sid})
            self.assertIn("error", r)
        self.assertEqual(self.ctx.architecture.get("STAIR", info["id"]).x, 5)
        self.assertIn("result", rpc("deshacer_3d", {"id": self.sid}))
        self.assertNotEqual(self.ctx.architecture.get("STAIR", info["id"]).x, 5)

    def test_historial_tambien_funciona_en_muros(self):
        muro = self.ctx.architecture.list("WALL", self.ctx.project.id)[0]
        antes = muro.thickness_m
        datos = {"id": self.sid, "tipo": "WALL", "elemento_id": muro.id}
        resultado = rpc("editar_3d", {**datos, "revision": muro.revision,
                                      "valores": {"thickness_m": 0.8}})
        self.assertIn("result", resultado)
        self.assertIn("result", rpc("deshacer_3d", {"id": self.sid}))
        self.assertEqual(self.ctx.architecture.get("WALL", muro.id).thickness_m, antes)
        self.assertIn("result", rpc("rehacer_3d", {"id": self.sid}))
        self.assertEqual(self.ctx.architecture.get("WALL", muro.id).thickness_m, 0.8)

    def test_nueva_edicion_descarta_rehacer(self):
        info = self.crear()["result"]
        info = self.editar(info, {"x": 2})["result"]
        rpc("deshacer_3d", {"id": self.sid})
        actual = rpc("elemento_3d", {"id": self.sid, "tipo": "STAIR", "elemento_id": info["id"]})["result"]
        self.assertIn("result", self.editar(actual, {"y": 5}))
        self.assertIn("error", rpc("rehacer_3d", {"id": self.sid}))

    def test_reabrir_instantanea_en_sesion_y_editar_de_nuevo(self):
        info = self.crear("U")["result"]
        info = self.editar(info, {"x": 7, "y": 8})["result"]
        with tempfile.TemporaryDirectory() as d:
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["JSON"]})["result"]
            with open(exp["proyecto"]["ruta"], encoding="utf8") as f:
                texto = f.read()
            retorno = rpc("proyecto_editar_3d", {"contenido": texto})
            self.assertIn("result", retorno, retorno)
            sid2 = retorno["result"]["id"]
            try:
                self.assertNotEqual(self.sid, sid2)
                vista = rpc("vista_3d", {"id": sid2})["result"]
                self.assertTrue(any(c["entidad_id"] == info["id"] for c in vista["caras"]))
                actual = rpc("elemento_3d", {"id": sid2, "tipo": "STAIR", "elemento_id": info["id"]})["result"]
                self.assertIn("result", rpc("editar_3d", {"id": sid2, "tipo": "STAIR",
                    "elemento_id": info["id"], "revision": actual["revision"], "valores": {"x": 12}}))
                salida = rpc("aplicar_exportar", {"id": sid2, "carpeta": d, "nombre_base": "reeditado",
                    "formatos": ["JSON"]})["result"]
                with open(salida["proyecto"]["ruta"], encoding="utf8") as f:
                    snap = json.load(f)
                self.assertEqual(next(x for x in snap["entities"]["STAIR"] if x["id"] == info["id"])["x"], 12)
                self.assertEqual(self.ctx.architecture.get("STAIR", info["id"]).x, 7)
            finally:
                servidor._cerrar_proyecto(sid2)
                servidor._SESION.pop(sid2, None)

    def test_canal_rpc_real_crea_edita_y_deshace(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with subprocess.Popen([sys.executable, os.path.join(raiz, "main.py"), "rpc"], cwd=raiz,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, encoding="utf-8") as proceso:
            def llamar(metodo, params):
                proceso.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1,
                                                "method": metodo, "params": params}) + "\n")
                proceso.stdin.flush()
                return json.loads(proceso.stdout.readline())
            generado = llamar("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})["result"]
            sid = generado["id"]
            escalera = llamar("crear_escalera_3d", {"id": sid, "tipo": "L"})["result"]
            r = llamar("editar_3d", {"id": sid, "tipo": "STAIR", "elemento_id": escalera["id"],
                                      "revision": escalera["revision"], "valores": {"x": 9, "tipo": "U"}})
            self.assertIn("result", r, r)
            self.assertIn("result", llamar("deshacer_3d", {"id": sid}))
            consulta = llamar("elemento_3d", {"id": sid, "tipo": "STAIR", "elemento_id": escalera["id"]})["result"]
            self.assertEqual(next(c for c in consulta["campos"] if c["campo"] == "tipo")["valor"], "L")
            proceso.stdin.close()
            self.assertEqual(proceso.wait(timeout=30), 0)

    def test_importacion_admite_vanos_repetidos_en_la_seccion_opening(self):
        from domain.model import Door
        from exporters.json_io import JSONExporter
        muro = next(w for w in self.ctx.architecture.list("WALL", self.ctx.project.id) if w.length_m > 1)
        puerta = Door(project_id=self.ctx.project.id, level_id=muro.level_id, wall_id=muro.id,
                      width_m=0.5, height_m=1, offset_m=0)
        self.ctx.architecture.save(puerta); self.ctx.commit()
        snap = JSONExporter.build_snapshot(self.ctx)
        self.assertEqual(snap["entities"]["DOOR"][0], snap["entities"]["OPENING"][0])
        respuesta = rpc("proyecto_editar_3d", {"contenido": json.dumps(snap)})
        self.assertIn("result", respuesta, respuesta)
        sid = respuesta["result"]["id"]
        try:
            ctx2 = servidor._PROYECTOS[sid]["ctx"]
            self.assertIsNotNone(ctx2.architecture.get("DOOR", puerta.id))
        finally:
            servidor._cerrar_proyecto(sid)
            servidor._SESION.pop(sid, None)

    def test_importacion_con_fallo_limpia_archivos_temporales(self):
        from exporters.json_io import JSONExporter
        texto = json.dumps(JSONExporter.build_snapshot(self.ctx))
        original = tempfile.TemporaryDirectory
        with original() as raiz:
            def crear_temporal(*args, **kwargs):
                kwargs["dir"] = raiz
                return original(*args, **kwargs)
            with mock.patch("app.rpc_server.tempfile.TemporaryDirectory", crear_temporal), \
                 mock.patch("services.import_service.ImportService.import_snapshot", side_effect=ValueError("fallo")):
                self.assertIn("error", rpc("proyecto_editar_3d", {"contenido": texto}))
                self.assertEqual(os.listdir(raiz), [])

    def test_importacion_rechaza_datos_invalidos_sin_crear_sesion(self):
        from exporters.json_io import JSONExporter
        snap = JSONExporter.build_snapshot(self.ctx)
        casos = ["no json", "[]", "{\"format\": \"ARQ_GEN_SNAPSHOT\", \"x\": NaN}",
                 "{\"format\": \"ARQ_GEN_SNAPSHOT\", \"x\": 1e999}",
                 json.dumps({**snap, "project": {}}),
                 json.dumps({**snap, "entities": {"NO_EXISTE": []}})]
        malo = json.loads(json.dumps(snap))
        malo["entities"]["WALL"][0]["project_id"] = "otro"
        casos.append(json.dumps(malo))
        malo = json.loads(json.dumps(snap))
        malo["entities"]["WALL"].append(malo["entities"]["WALL"][0])
        casos.append(json.dumps(malo))
        for contenido in casos:
            with self.subTest(contenido=contenido[:80]):
                sesiones = set(servidor._PROYECTOS)
                respuesta = rpc("proyecto_editar_3d", {"contenido": contenido})
                self.assertEqual(respuesta.get("error", {}).get("code"), -32602, respuesta)
                self.assertEqual(set(servidor._PROYECTOS), sesiones)

    def test_exportacion_e_importacion_conservan_escalera_editada(self):
        info = self.crear("L")["result"]
        info = self.editar(info, {"tipo": "caracol", "x": 7, "y": 8, "width_m": 1.4})["result"]
        with tempfile.TemporaryDirectory() as d:
            res = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["JSON"], "con_proyecto": True})["result"]
            with open(res["proyecto"]["ruta"], encoding="utf8") as fh:
                snap = json.load(fh)
            stair = next(s for s in snap["entities"]["STAIR"] if s["id"] == info["id"])
            self.assertEqual(stair["tipo"], "caracol")
            self.assertEqual(stair["x"], 7)
            db = os.path.join(d, "importado.arqgen")
            app = ApplicationContext()
            ImportService(app).import_snapshot(res["proyecto"]["ruta"], db, approve=True)
            ctx = app.open_project(db)
            try:
                restaurada = ctx.architecture.get("STAIR", info["id"])
                self.assertEqual(restaurada.metadata, stair["metadata"])
                self.assertEqual((restaurada.x, restaurada.y), (7, 8))
                caras = view3d.caras_de_escalera(restaurada, 0, 0, view3d.Camara3D())
                self.assertTrue(caras)
                self.assertGreater(min(p[0] for c in caras for p in c.puntos), 4)
            finally:
                ctx.close()


class TestAbrirProyectoFrontend(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node no está instalado")
    def test_importacion_desde_interfaz(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = subprocess.run([shutil.which("node"), "tests/abrir_proyecto_3d_node.js"],
                           cwd=raiz, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
