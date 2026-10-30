"""Vista previa 3D de Tauri: el mismo motor y un proyecto temporal real."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from app.rpc_server import handle_call

ROOT = Path(__file__).resolve().parent.parent
FICHAS = [{"space_type": "ENTRANCE", "cantidad": 1},
          {"space_type": "OFFICE", "cantidad": 4},
          {"space_type": "LAVATORY", "cantidad": 2}]
RECT = [[0, 0], [24, 0], [24, 12], [0, 12]]


def rpc(method, params):
    return handle_call({"jsonrpc": "2.0", "id": 1, "method": method,
                        "params": params})


class TestVista3D(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res = rpc("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})
        cls.plan = res["result"]["id"]

    def vista(self, **kwargs):
        return rpc("vista_3d", {"id": self.plan, **kwargs})

    def test_vista_representa_entidades_reales_y_es_determinista(self):
        a = self.vista()["result"]
        b = self.vista()["result"]
        self.assertEqual(a, b)
        self.assertTrue(a["niveles"])
        self.assertTrue(a["caras"])
        self.assertTrue(any(c["tipo"].startswith("muro") for c in a["caras"]))
        for cara in a["caras"]:
            self.assertGreaterEqual(len(cara["puntos"]), 3)
            self.assertRegex(cara["color"], r"^#[0-9a-fA-F]{6}$")
            self.assertTrue(all(math.isfinite(coord)
                                for punto in cara["puntos"] for coord in punto))
        x, y, ancho, alto = a["encuadre"]
        self.assertGreater(ancho, 0)
        self.assertGreater(alto, 0)
        for cara in a["caras"]:
            for px, py in cara["puntos"]:
                self.assertLessEqual(x - 0.00001, px)
                self.assertLessEqual(px, x + ancho + 0.00001)
                self.assertLessEqual(y - 0.00001, py)
                self.assertLessEqual(py, y + alto + 0.00001)

    def test_camara_y_perspectiva_cambian_la_proyeccion(self):
        normal = self.vista()["result"]
        giro = self.vista(azimut=90)["result"]
        perspectiva = self.vista(perspectiva=True)["result"]
        self.assertNotEqual(normal["caras"], giro["caras"])
        self.assertNotEqual(normal["caras"], perspectiva["caras"])
        self.assertTrue(perspectiva["caras"])

    def test_niveles_y_explosion(self):
        res = rpc("generar_radial", {"fichas": FICHAS, "radio_ext": 14,
                                      "sectores": 8, "niveles": 2})
        plan = res["result"]["id"]
        entero = rpc("vista_3d", {"id": plan})["result"]
        self.assertEqual(len(entero["niveles"]), 2)
        separado = rpc("vista_3d", {"id": plan, "explosion_m": 3})["result"]
        aislado = rpc("vista_3d", {"id": plan, "nivel": 1})["result"]
        self.assertNotEqual(entero["caras"], separado["caras"])
        self.assertLess(len(aislado["caras"]), len(entero["caras"]))

    def test_sin_id_camara_invalida_y_nivel_inexistente(self):
        self.assertEqual(rpc("vista_3d", {})["error"]["code"], -32602)
        for parametros in ({"azimut": float("nan")}, {"elevacion": 90},
                           {"explosion_m": -1}, {"nivel": -1},
                           {"nivel": True}, {"nivel": 100},
                           {"perspectiva": "false"}):
            with self.subTest(parametros=parametros):
                self.assertEqual(self.vista(**parametros)["error"]["code"], -32602)
        self.assertTrue(rpc("ping", {})["result"]["pong"])

    def test_compuesto_rejilla_y_radial(self):
        unidad = [{"space_type": "BEDROOM", "cantidad": 2},
                  {"space_type": "LAVATORY", "cantidad": 1},
                  {"space_type": "KITCHEN", "cantidad": 1}]
        casos = [("generar_rejilla", {"fichas": unidad, "contorno": RECT,
                                      "columnas": 3, "filas": 2}),
                 ("generar_radial", {"fichas": FICHAS, "radio_ext": 14,
                                     "sectores": 8}),
                 ("generar_y", {"fichas": FICHAS, "radio_nucleo": 7,
                                "largos_alas": [18, 13, 20]}),
                 ("generar_x", {"fichas": FICHAS, "largo_barra": 64,
                                "ancho_barra": 14, "angulo_grados": 45}),
                 ("generar_zonas", {"fichas": FICHAS, "zonas": [
                     {"contorno": [[0, 0], [18, 0], [18, 12], [0, 12]], "rol": "norte"},
                     {"contorno": [[0, 0], [16, 0], [16, 10], [0, 10]], "rol": "sur"}]})]
        for metodo, params in casos:
            with self.subTest(metodo=metodo):
                generacion = rpc(metodo, params)
                self.assertIn("result", generacion, generacion)
                respuesta = rpc("vista_3d", {"id": generacion["result"]["id"]})
                self.assertIn("result", respuesta, respuesta)
                self.assertTrue(respuesta["result"]["caras"])

    def test_proyecto_vive_en_sesion_y_se_elimina_al_cerrar(self):
        from app import rpc_server
        res = rpc("generar_edificacion", {"fichas": FICHAS, "contorno": RECT})
        sid = res["result"]["id"]
        original = tempfile.TemporaryDirectory
        with original() as raiz:
            def crear_temporal(*args, **kwargs):
                kwargs["dir"] = raiz
                return original(*args, **kwargs)
            with mock.patch("app.rpc_server.tempfile.TemporaryDirectory", crear_temporal):
                self.assertIn("result", rpc("vista_3d", {"id": sid}))
                self.assertEqual(len(os.listdir(raiz)), 1)
                self.assertIn("error", rpc("vista_3d", {"id": sid, "nivel": 100}))
                self.assertEqual(len(os.listdir(raiz)), 1)
                rpc_server._cerrar_proyecto(sid)
                self.assertEqual(os.listdir(raiz), [])
        rpc_server._SESION.pop(sid, None)

    def test_vista_3d_por_proceso_json_rpc(self):
        peticiones = [
            {"jsonrpc": "2.0", "id": 1, "method": "generar_edificacion",
             "params": {"fichas": FICHAS, "contorno": RECT}},
            # Es un proceso nuevo: la primera sesión es an1.
            {"jsonrpc": "2.0", "id": 2, "method": "vista_3d",
             "params": {"id": "an1", "perspectiva": True}},
            {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}},
        ]
        entrada = "\n".join(json.dumps(p) for p in peticiones) + "\n"
        p = subprocess.run([sys.executable, str(ROOT / "main.py"), "rpc"],
                           input=entrada, capture_output=True, text=True,
                           encoding="utf-8", cwd=ROOT, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        respuestas = [json.loads(linea) for linea in p.stdout.splitlines()]
        self.assertEqual(len(respuestas), 3)
        self.assertEqual(respuestas[0]["result"]["id"], "an1")
        self.assertTrue(respuestas[1]["result"]["caras"])
        self.assertTrue(respuestas[2]["result"]["pong"])

    def test_nombre_de_instantanea_no_escapa_de_la_carpeta(self):
        with tempfile.TemporaryDirectory() as raiz:
            salida = os.path.join(raiz, "salida")
            exp = rpc("aplicar_exportar", {"id": self.plan, "carpeta": salida,
                "nombre_base": "../escape", "formatos": ["JSON"],
                "con_proyecto": True})
            self.assertIn("result", exp, exp)
            r = exp["result"]
            self.assertEqual(r["base"], "escape")
            self.assertEqual(os.path.dirname(r["proyecto"]["ruta"]), salida)
            self.assertTrue(os.path.isfile(r["proyecto"]["ruta"]))
            self.assertFalse(os.path.exists(os.path.join(raiz, "escape_proyecto.json")))
            self.assertEqual(rpc("proyecto_abrir", {"ruta": r["proyecto"]["ruta"]})
                             ["result"]["errores"], [])


class TestFrontend3D(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node no está instalado")
    def test_interaccion_y_respuestas_obsoletas(self):
        p = subprocess.run([shutil.which("node"), str(ROOT / "tests/visor_3d_node.js")],
                           cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_sintaxis_javascript(self):
        if not shutil.which("node"):
            self.skipTest("node no está instalado")
        p = subprocess.run([shutil.which("node"), "--check", str(ROOT / "src/app.js")],
                           text=True, capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
