"""Movimientos en Z y roundtrip paramétrico del IFC exportado por ARQ GEN."""
from __future__ import annotations

import os
import tempfile
import unittest

from app import rpc_server as servidor
from tests.test_193_vista_3d_web import FICHAS, RECT, rpc
from services.context import ApplicationContext
from services.architecture_service import ArchitectureService
from importers.ifc_reader import IfcImporter
from ui import view3d


class TestMovimientoEImportacion(unittest.TestCase):
    def setUp(self):
        self.sid = rpc("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})["result"]["id"]
        self.ctx = servidor._proyecto_sesion({"id": self.sid})["ctx"]

    def tearDown(self):
        servidor._cerrar_proyecto(self.sid)
        servidor._SESION.pop(self.sid, None)

    def test_z_persistente_y_deshacer(self):
        info = rpc("crear_escalera_3d", {"id": self.sid, "tipo": "L"})["result"]
        obj = self.ctx.architecture.get("STAIR", info["id"])
        antes = view3d.caras_de_escalera(obj, 0, 0, view3d.Camara3D())
        edit = rpc("editar_3d", {"id": self.sid, "tipo": "STAIR", "elemento_id": info["id"],
                                 "revision": info["revision"], "valores": {"base_offset_m": 1.25}})
        self.assertIn("result", edit, edit)
        obj2 = self.ctx.architecture.get("STAIR", info["id"])
        self.assertEqual(obj2.metadata["editor_base_offset_m"], 1.25)
        despues = view3d.caras_de_escalera(obj2, 0, 0, view3d.Camara3D())
        for a, b in zip(antes, despues):
            for pa, pb in zip(a.puntos, b.puntos):
                self.assertAlmostEqual(pb[2] - pa[2], 1.25)
        self.assertIn("result", rpc("deshacer_3d", {"id": self.sid}))
        self.assertNotIn("editor_base_offset_m", self.ctx.architecture.get("STAIR", info["id"]).metadata)
        self.assertIn("result", rpc("rehacer_3d", {"id": self.sid}))
        self.assertEqual(self.ctx.architecture.get("STAIR", info["id"]).metadata["editor_base_offset_m"], 1.25)

    def test_ifc_reimporta_cuatro_escaleras_con_parametros(self):
        originales = []
        for i, tipo in enumerate(("recta", "L", "U", "caracol")):
            info = rpc("crear_escalera_3d", {"id": self.sid, "tipo": tipo})["result"]
            edit = rpc("editar_3d", {"id": self.sid, "tipo": "STAIR", "elemento_id": info["id"],
                                     "revision": info["revision"], "valores": {
                                         "x": 20+i*10, "y": 40+i, "rotation_deg": 37,
                                         "base_offset_m": 0.25+i*0.1}})
            self.assertIn("result", edit, edit)
            originales.append(self.ctx.architecture.get("STAIR", info["id"]))
        with tempfile.TemporaryDirectory() as d:
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["IFC"]})["result"]
            self.assertFalse(exp["errores"], exp)
            ruta = exp["archivos"]["IFC"]["ruta"]
            # Si está disponible, un lector independiente valida esquema y
            # triangulación; el importador propio no demuestra interoperabilidad.
            try:
                import ifcopenshell
                import ifcopenshell.geom
                import ifcopenshell.validate
            except ImportError:
                pass
            else:
                ifc = ifcopenshell.open(ruta)
                registro = ifcopenshell.validate.json_logger()
                ifcopenshell.validate.validate(ifc, registro)
                self.assertEqual(registro.statements, [])
                elementos = ifc.by_type("IfcStair")
                self.assertEqual(len(elementos), 4)
                for escalera in elementos:
                    malla = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), escalera)
                    self.assertTrue(malla.geometry.verts)
                    self.assertTrue(malla.geometry.faces)
            imp = IfcImporter()
            self.assertEqual(imp.preview(ruta)["stairs"], 4)
            ctx2 = ApplicationContext().create_project(os.path.join(d, "destino.arqgen"), name="Destino")
            try:
                result = imp.apply(ruta, ArchitectureService(ctx2))
                self.assertEqual(result["escaleras"], 4, result)
                self.assertEqual(result["escaleras_omitidas"], 0, result)
                nuevas = ctx2.architecture.list("STAIR", ctx2.project.id)
                self.assertEqual(len(nuevas), 4)
                por_tipo = {o.tipo: o for o in nuevas}
                for a in originales:
                    b = por_tipo[a.tipo]
                    self.assertAlmostEqual(a.x, b.x)
                    self.assertAlmostEqual(a.y, b.y)
                    self.assertAlmostEqual(a.rotation_deg, b.rotation_deg)
                    self.assertAlmostEqual(a.metadata["editor_base_offset_m"], b.metadata["editor_base_offset_m"])
                    self.assertEqual(a.metadata["pasos"], b.metadata["pasos"])
            finally:
                ctx2.close()

    def test_escalera_ifc_sin_pset_se_omite_con_aviso(self):
        rpc("crear_escalera_3d", {"id": self.sid, "tipo": "L"})
        with tempfile.TemporaryDirectory() as d:
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["IFC"]})["result"]
            ruta = exp["archivos"]["IFC"]["ruta"]
            with open(ruta, encoding="utf-8") as archivo:
                texto = archivo.read().replace("Pset_ARQGEN_Stair", "Pset_Externo_Stair")
            with open(ruta, "w", encoding="utf-8") as archivo:
                archivo.write(texto)
            imp = IfcImporter()
            prev = imp.preview(ruta)
            self.assertEqual(prev["stairs"], 1)
            self.assertTrue(any("sin parámetros" in a for a in prev["avisos"]))
            ctx2 = ApplicationContext().create_project(os.path.join(d, "externo.arqgen"), name="Externo")
            try:
                resultado = imp.apply(ruta, ArchitectureService(ctx2))
                self.assertEqual(resultado["escaleras"], 0)
                self.assertEqual(resultado["escaleras_omitidas"], 1)
                self.assertTrue(any("Escalera" in a for a in resultado["avisos"]))
            finally:
                ctx2.close()

    def test_aviso_si_metadata_esta_danada(self):
        from types import SimpleNamespace as NS
        from services.avisos_3d import avisos_objeto
        class Repo:
            def list(self, tipo, _proyecto):
                return {"LEVEL": [NS(id="n1", elevation_m=0)], "OPENING": [],
                        "WALL": [], "FURNITURE": [], "STAIR": [rota]}.get(tipo, [])
            def get(self, *_args):
                return None
        rota = NS(ENTITY_TYPE="STAIR", id="s", level_id="n1", metadata={"pasos": [{}]},
                  space_id=None, x=0, y=0)
        ctx = NS(project=NS(id="p"), architecture=Repo())
        self.assertTrue(any("inválidos" in aviso for aviso in avisos_objeto(ctx, rota)))
        rota.metadata = ["metadatos corruptos"]
        self.assertTrue(any("inválidos" in aviso for aviso in avisos_objeto(ctx, rota)))

    def test_interferencias_3d_descuentan_vanos_y_respetan_cotas(self):
        from types import SimpleNamespace as NS
        from services.avisos_3d import _piezas, _prismas_solapan
        muro = NS(ENTITY_TYPE="WALL", level_id="n1", id="m1", metadata={},
                  start=(0.0, 0.0), end=(4.0, 0.0), thickness_m=0.2,
                  height_m=3.0, base_offset_m=0.0)
        vano = NS(offset_m=1.0, width_m=1.0, sill_height_m=0.0, height_m=2.0)
        mueble = NS(ENTITY_TYPE="FURNITURE", level_id="n1", id="f1", metadata={},
                    x=1.5, y=0.0, width_m=0.4, depth_m=0.3, height_m=1.0, rotation_deg=0.0)
        niveles = {"n1": 0.0, "n2": 5.0}
        def choca():
            a = _piezas(None, muro, niveles, {"m1": [vano]})
            b = _piezas(None, mueble, niveles, {})
            return any(_prismas_solapan(x, y) for x in a for y in b)
        self.assertFalse(choca(), "El objeto cabe dentro de un vano real")
        mueble.x = 0.5
        self.assertTrue(choca(), "La pieza atraviesa el muro macizo")
        mueble.x = 1.5
        mueble.metadata["editor_base_offset_m"] = 2.3
        self.assertTrue(choca(), "El objeto invade el dintel")
        mueble.level_id = "n2"
        self.assertFalse(choca(), "No hay solape vertical entre niveles separados")

    def test_vista_expone_camara_y_punto_real(self):
        info = rpc("crear_escalera_3d", {"id": self.sid, "tipo": "recta"})["result"]
        vista = rpc("vista_3d", {"id": self.sid, "perspectiva": True})["result"]
        self.assertGreater(vista["camara"]["distancia"], 0)
        self.assertEqual(len(vista["camara"]["centro"]), 3)
        cara = next(c for c in vista["caras"] if c["entidad_id"] == info["id"])
        self.assertEqual(len(cara["centro_mundo"]), 3)


if __name__ == "__main__":
    unittest.main()
