"""Navegación/selección: entidades persistentes y exportación de ediciones."""
from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from unittest import mock

from app import rpc_server as servidor
from domain.model import (Door, Furniture, Roof, Ramp, Handrail, Elevator,
                          Parasol, FacadeSkin, Stair)
from tests.test_193_vista_3d_web import FICHAS, RECT, rpc


class TestEdicion3D(unittest.TestCase):
    def setUp(self):
        self.sid = rpc("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})["result"]["id"]
        self.vista = rpc("vista_3d", {"id": self.sid})["result"]
        self.entrada = servidor._PROYECTOS[self.sid]
        self.ctx = self.entrada["ctx"]

    def tearDown(self):
        servidor._cerrar_proyecto(self.sid)
        servidor._SESION.pop(self.sid, None)

    def datos(self, tipo, uid):
        return {"id": self.sid, "tipo": tipo, "elemento_id": uid}

    def consultar(self, tipo, uid):
        return rpc("elemento_3d", self.datos(tipo, uid))

    def guardar(self, tipo, uid, valores, revision=1):
        return rpc("editar_3d", {**self.datos(tipo, uid), "valores": valores, "revision": revision})

    def test_muro_edicion_validada_auditada_y_exportada(self):
        cara = next(c for c in self.vista["caras"] if c["entidad_tipo"] == "WALL")
        uid = cara["entidad_id"]
        self.assertTrue(uid)
        self.assertTrue(any(not c["entidad_id"] for c in self.vista["caras"]))  # plataformas sintéticas
        info = self.consultar("WALL", uid)["result"]
        for invalido in (float("nan"), float("inf"), -1, 0, "no numero", True):
            with self.subTest(invalido=invalido):
                self.assertIn("error", self.guardar("WALL", uid, {"thickness_m": invalido}, info["revision"]))
        self.assertIn("error", self.guardar("WALL", uid, {"metadata": {}}, info["revision"]))
        self.assertFalse(self.entrada["editado"])
        resultado = self.guardar("WALL", uid, {"thickness_m": 0.47}, info["revision"])
        self.assertEqual(resultado["result"]["revision"], info["revision"] + 1)
        self.assertEqual(self.ctx.architecture.get("WALL", uid).thickness_m, 0.47)
        self.assertIn("error", self.guardar("WALL", uid, {"thickness_m": 0.5}, info["revision"]))
        nuevo = rpc("vista_3d", {"id": self.sid})["result"]
        self.assertNotEqual(self.vista["caras"], nuevo["caras"])
        self.assertTrue(any(c["entidad_id"] == uid for c in nuevo["caras"]))
        self.assertIn("UPDATE_ENTITY", self.ctx.command_bus.executed)
        with tempfile.TemporaryDirectory() as carpeta:
            incompatible = rpc("aplicar_exportar", {"id": self.sid, "carpeta": carpeta,
                "formatos": ["JSON"], "trazar_muros": False})
            self.assertIn("error", incompatible)
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": carpeta,
                "formatos": ["JSON", "DXF", "IFC"], "con_proyecto": True})
            self.assertIn("result", exp, exp)
            self.assertFalse(exp["result"]["errores"], exp)
            with open(exp["result"]["proyecto"]["ruta"], encoding="utf8") as f:
                snapshot = json.load(f)
            pared = next(w for w in snapshot["entities"]["WALL"] if w["id"] == uid)
            self.assertEqual(pared["thickness_m"], 0.47)
            self.assertTrue(os.path.getsize(exp["result"]["archivos"]["DXF"]["ruta"]))
            self.assertTrue(os.path.getsize(exp["result"]["archivos"]["IFC"]["ruta"]))

    def test_fallo_de_auditoria_revierte_cambio_e_historial(self):
        muro = self.ctx.architecture.list("WALL", self.ctx.project.id)[0]
        antes = list(self.ctx.command_bus.executed)
        with mock.patch("services.edicion_3d.ArchitectureService._finish", side_effect=ValueError("fallo")):
            self.assertIn("error", self.guardar("WALL", muro.id, {"thickness_m": 0.9}))
        self.assertEqual(self.ctx.architecture.get("WALL", muro.id).thickness_m, muro.thickness_m)
        self.assertEqual(self.ctx.command_bus.executed, antes)
        self.assertFalse(self.entrada["editado"])

    def test_mueble_y_cubierta_tienen_ids_reales_y_cambian_el_modelo(self):
        nivel = self.ctx.architecture.list("LEVEL", self.ctx.project.id)[0]
        espacio = self.ctx.architecture.list("SPACE", self.ctx.project.id)[0]
        m = Furniture(project_id=self.ctx.project.id, level_id=nivel.id, space_id=espacio.id,
                      name="Mesa", x=1, y=1, width_m=1, depth_m=1, height_m=1)
        techo = Roof(project_id=self.ctx.project.id, level_id=nivel.id, tipologia="dos_aguas",
                     pendiente_pct=20, altura_cumbrera_m=1, footprint=[(0, 0), (10, 0), (10, 10), (0, 10)],
                     ridge=((0, 5), (10, 5)))
        self.ctx.architecture.save(m)
        self.ctx.architecture.save(techo)
        self.ctx.commit()
        antes = rpc("vista_3d", {"id": self.sid})["result"]
        for tipo, uid in (("FURNITURE", m.id), ("ROOF", techo.id)):
            self.assertTrue(any(c["entidad_tipo"] == tipo and c["entidad_id"] == uid for c in antes["caras"]))
        self.assertIn("result", self.guardar("FURNITURE", m.id, {"height_m": 2.0, "x": 2}))
        self.assertIn("result", self.guardar("ROOF", techo.id, {"pendiente_pct": 40}))
        self.assertEqual(self.ctx.architecture.get("ROOF", techo.id).altura_cumbrera_m, 2)
        despues = rpc("vista_3d", {"id": self.sid})["result"]
        self.assertNotEqual([c for c in antes["caras"] if c["entidad_id"] == techo.id],
                            [c for c in despues["caras"] if c["entidad_id"] == techo.id])
        with tempfile.TemporaryDirectory() as d:
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": d, "formatos": ["JSON"], "con_proyecto": True})
            with open(exp["result"]["proyecto"]["ruta"], encoding="utf8") as f:
                snap = json.load(f)
            self.assertEqual(next(x for x in snap["entities"]["ROOF"] if x["id"] == techo.id)["pendiente_pct"], 40)
            self.assertEqual(next(x for x in snap["entities"]["FURNITURE"] if x["id"] == m.id)["height_m"], 2)
            from services.import_service import ImportService
            from services.context import ApplicationContext
            app = ApplicationContext()
            db = os.path.join(d, "importado.arqgen")
            resultado = ImportService(app).import_snapshot(exp["result"]["proyecto"]["ruta"], db, approve=True)
            self.assertTrue(resultado["approved"])
            restaurado = app.open_project(db)
            try:
                self.assertEqual(restaurado.architecture.get("FURNITURE", m.id).height_m, 2)
                self.assertEqual(restaurado.architecture.get("ROOF", techo.id).pendiente_pct, 40)
            finally:
                restaurado.close()

    def test_mas_tipos_y_roundtrip_instantanea(self):
        nivel = self.ctx.architecture.list("LEVEL", self.ctx.project.id)[0]
        common = {"project_id": self.ctx.project.id, "level_id": nivel.id}
        elementos = [
            Ramp(**common, corners=[(0, 0), (2, 0), (2, 1), (0, 1)], length_m=2, desnivel_m=.2),
            Handrail(**common, points=[(0, 0), (2, 0)]),
            Elevator(**common, x=3, y=3), Parasol(**common, x=3, y=3),
            FacadeSkin(**common, x=3, y=3), Stair(**common, x=3, y=3),
        ]
        for e in elementos:
            self.ctx.architecture.save(e)
        self.ctx.commit()
        cambios = [(elementos[0], {"desnivel_m": 0.4}),
                   (elementos[1], {"altura_m": 1.2}),
                   (elementos[2], {"x": 4}),
                   (elementos[3], {"profundidad_m": .8}),
                   (elementos[4], {"altura_m": 4})]
        for obj, valores in cambios:
            self.assertIn("result", self.guardar(obj.ENTITY_TYPE, obj.id, valores))
        self.assertEqual(self.ctx.architecture.get("RAMP", elementos[0].id).slope_pct, 20)
        with tempfile.TemporaryDirectory() as carpeta:
            exp = rpc("aplicar_exportar", {"id": self.sid, "carpeta": carpeta,
                "formatos": ["JSON"], "con_proyecto": True})
            self.assertIn("result", exp, exp)
            from services.import_service import ImportService
            from services.context import ApplicationContext
            app = ApplicationContext()
            db = os.path.join(carpeta, "roundtrip.arqgen")
            ImportService(app).import_snapshot(exp["result"]["proyecto"]["ruta"], db, approve=True)
            ctx = app.open_project(db)
            try:
                for obj in elementos:
                    self.assertIsNotNone(ctx.architecture.get(obj.ENTITY_TYPE, obj.id), obj.ENTITY_TYPE)
                self.assertEqual(ctx.architecture.get("ELEVATOR", elementos[2].id).x, 4)
                self.assertEqual(ctx.architecture.get("SKIN", elementos[4].id).altura_m, 4)
            finally:
                ctx.close()

    def test_restaurar_version_elimina_extras_y_recupera_tipos_nuevos(self):
        from exporters.json_io import JSONExporter
        from services.version_service import VersionService
        nivel = self.ctx.architecture.list("LEVEL", self.ctx.project.id)[0]
        a = Elevator(project_id=self.ctx.project.id, level_id=nivel.id, x=2)
        self.ctx.architecture.save(a)
        self.ctx.commit()
        snap = JSONExporter.build_snapshot(self.ctx)
        b = FacadeSkin(project_id=self.ctx.project.id, level_id=nivel.id)
        self.ctx.architecture.save(b)
        a.x = 8
        self.ctx.architecture.save(a)
        self.ctx.commit()
        service = VersionService(self.ctx)
        service.restore_version(1, json.dumps(snap))
        self.ctx.commit()
        self.assertEqual(self.ctx.architecture.get("ELEVATOR", a.id).x, 2)
        self.assertIsNone(self.ctx.architecture.get("SKIN", b.id))

    def test_vano_debe_caber_en_el_muro(self):
        muro = next(w for w in self.ctx.architecture.list("WALL", self.ctx.project.id) if w.length_m > 1)
        vano = Door(project_id=self.ctx.project.id, level_id=muro.level_id, wall_id=muro.id,
                    width_m=0.5, height_m=1, offset_m=0)
        self.ctx.architecture.save(vano)
        self.ctx.commit()
        self.assertIn("error", self.guardar("DOOR", vano.id, {"width_m": muro.length_m + 1}))
        self.assertIn("error", self.guardar("WALL", muro.id, {"height_m": 0.5}))
        self.assertIn("result", self.guardar("DOOR", vano.id, {"width_m": 0.6}))

    def test_identidad_invalida_y_limpieza_lru(self):
        self.assertIn("error", self.consultar("WALL", "inexistente"))
        self.assertIn("error", self.consultar("PROJECT", self.ctx.project.id))
        ruta = self.entrada["temporal"].name
        self.assertTrue(os.path.isdir(ruta))
        # Crea suficientes sesiones nuevas para expulsar la más antigua.
        for _ in range(8):
            servidor._guardar_sesion({})
        self.assertNotIn(self.sid, servidor._PROYECTOS)
        self.assertFalse(os.path.exists(ruta))
        self.assertIn("error", rpc("vista_3d", {"id": self.sid}))

    def test_fallo_materializacion_limpia_directorio(self):
        sid = rpc("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})["result"]["id"]
        original = tempfile.TemporaryDirectory
        with original() as raiz:
            def crear_temporal(*args, **kwargs):
                kwargs["dir"] = raiz
                return original(*args, **kwargs)
            with mock.patch("app.rpc_server.tempfile.TemporaryDirectory", crear_temporal), \
                 mock.patch("app.rpc_server.dd.aplicar_plan", side_effect=ValueError("fallo")):
                self.assertIn("error", rpc("vista_3d", {"id": sid}))
                self.assertEqual(os.listdir(raiz), [])
        servidor._SESION.pop(sid, None)


if __name__ == "__main__":
    unittest.main()
