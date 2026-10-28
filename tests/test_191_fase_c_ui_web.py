"""FASE C (v3.50.0): UI web completa sobre Tauri — contrato del sidecar,
exportación real y empaquetado del frontend.

El canal FASE A (v3.48.0) hablaba de la UI de prueba al motor; la FASE C
convierte ese canal en la INTERFAZ COMPLETA: catálogo DNA, las 6 formas
de generar (simple, radial, Y, X, multi-ala, rejilla), sesión LRU de
análisis, métricas explicadas, exportación a archivos reales y lectura
de instantáneas. Estas pruebas exigen el CONTRATO que la UI web consume:
nada de formatos inventados — cada clave que toca la web está aquí.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

import core  # noqa: E402
from app.rpc_server import handle_call, _SESION  # noqa: E402

FICHAS = [{"space_type": "ENTRANCE", "cantidad": 1},
          {"space_type": "OFFICE", "cantidad": 4},
          {"space_type": "LAVATORY", "cantidad": 2}]
FICHAS_UNIDAD = [{"space_type": "BEDROOM", "cantidad": 2},
                 {"space_type": "LAVATORY", "cantidad": 1},
                 {"space_type": "KITCHEN", "cantidad": 1}]
RECT = [[0, 0], [24, 0], [24, 12], [0, 12]]


def _llamar(metodo, params, rid=1):
    return handle_call({"jsonrpc": "2.0", "id": rid, "method": metodo,
                        "params": params})


class TestCatalogo(unittest.TestCase):
    """catalogo: el selector de fichas de la UI se llena del DNA real."""

    def test_catalogo_completo(self):
        res = _llamar("catalogo", {})["result"]
        self.assertGreaterEqual(res["total"], 100)
        self.assertEqual(len(res["tipos"]), res["total"])
        for t in res["tipos"]:
            for clave in ("code", "nombre", "area_min", "mojado", "dia"):
                self.assertIn(clave, t)
        codigos = {t["code"] for t in res["tipos"]}
        for uso in ("ENTRANCE", "OFFICE", "BEDROOM", "LAVATORY", "KITCHEN"):
            self.assertIn(uso, codigos)

    def test_catalogo_determinista(self):
        a = _llamar("catalogo", {}, rid=1)["result"]
        b = _llamar("catalogo", {}, rid=2)["result"]
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class TestFormas(unittest.TestCase):
    """Las 6 formas de generar que la pestaña Forma de la UI ofrece."""

    def test_radial_con_poligonos_y_metricas(self):
        res = _llamar("generar_radial", {"fichas": FICHAS, "radio_ext": 14.0,
                                         "sectores": 8, "corredor_m": 1.6,
                                         "radio_nucleo": 3.0,
                                         "niveles": 2})["result"]
        self.assertEqual(res["tipo"], "radial")
        self.assertEqual(res["niveles"], 2)
        self.assertTrue(res["id"])
        loc0 = res["reparto"][0]["locales"][0]
        self.assertGreaterEqual(len(loc0["poligono"]), 3)
        met = res["metricas"]
        for clave in ("puntuacion", "ocupacion_pct", "circulacion_pct",
                      "cumplimiento_pct", "area_construida_m2"):
            self.assertIn(clave, met)
        self.assertGreater(float(met["puntuacion"]), 0)

    def test_radial_determinista_sin_id(self):
        params = {"fichas": FICHAS, "radio_ext": 14.0, "sectores": 8,
                  "corredor_m": 1.6, "radio_nucleo": 3.0}
        a = _llamar("generar_radial", params, rid=1)["result"]
        b = _llamar("generar_radial", params, rid=2)["result"]
        a.pop("id"), b.pop("id")
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))

    def test_torre_y_pasillos_por_ala(self):
        res = _llamar("generar_y", {"fichas": FICHAS, "radio_nucleo": 7.0,
                                    "n_alas": 3,
                                    "largos_alas": [18.0, 13.0, 20.0]},
                      )["result"]
        nivel = res["reparto"][0]
        self.assertEqual(len(nivel["pasillos"]), 3)
        alas = {p["ala"] for p in nivel["pasillos"]}
        self.assertEqual(alas, {0, 1, 2})
        for p in nivel["pasillos"]:
            self.assertGreaterEqual(len(p["poligono"]), 3)

    def test_hospital_x_cuatro_brazos(self):
        res = _llamar("generar_x", {"fichas": FICHAS, "largo_barra": 64.0,
                                    "ancho_barra": 14.0,
                                    "angulo_grados": 45.0})["result"]
        self.assertEqual(len(res["reparto"][0]["pasillos"]), 4)

    def test_zonas_compuesto_con_rol(self):
        res = _llamar("generar_zonas", {
            "fichas": FICHAS,
            "zonas": [{"contorno": [[0, 0], [18, 0], [18, 12], [0, 12]],
                       "rol": "ala norte"},
                      {"contorno": [[0, 0], [16, 0], [16, 10], [0, 10]]}]},
                      )["result"]
        self.assertEqual(res["tipo"], "zonas")
        self.assertEqual(len(res["zonas"]), 2)
        ala0 = res["zonas"][0]
        self.assertEqual(ala0["rol"], "ala norte")
        self.assertTrue(ala0["reparto"])
        self.assertTrue(ala0["totales"])
        self.assertGreater(ala0["area_m2"], 0)

    def test_rejilla_seis_celdas_y_corredor(self):
        res = _llamar("generar_rejilla", {
            "fichas": FICHAS_UNIDAD, "contorno": RECT,
            "columnas": 3, "filas": 2})["result"]
        self.assertEqual(res["tipo"], "rejilla")
        self.assertEqual(len(res["zonas"]), 6)
        self.assertTrue(res["pasillo_central"])
        # el corredor central llega como EJE (2 puntos) o polígono (4 con
        # chaflanes): el rect del motor es forma-variable y la web lista
        # lo que llega sin inventar geometría
        self.assertIn(len(res["pasillo_central"]["rect"]), (2, 4))
        self.assertGreater(float(res["pasillo_central"]["area_m2"]), 0)

    def test_ajuste_minimo_y_patio_llegan_al_motor(self):
        # FASE C pasa el ajuste completo (ideal|minimo|medio|estricto) y patio
        res = _llamar("generar_quick", {
            "texto": "dormitorio, bano, cocina, sala, patio",
            "contorno": [[0, 0], [14, 0], [14, 9], [0, 9]],
            "ajuste": "minimo", "patio": True})["result"]
        self.assertTrue(res["reparto"])
        self.assertEqual(res["tipo"], "edificacion")

    def test_fichas_con_niveles_deseados(self):
        res = _llamar("generar_edificacion", {
            "fichas": FICHAS, "contorno": [[0, 0], [10, 0], [10, 8], [0, 8]],
            "niveles": 1})["result"]
        self.assertTrue(res)


class TestSesion(unittest.TestCase):
    """La sesión LRU: la UI solo guarda el id, el sidecar el análisis."""

    def test_id_desconocido_lanza_32602(self):
        err = _llamar("aplicar_exportar", {"id": "an999999",
                                           "carpeta": "/tmp"})["error"]
        self.assertEqual(err["code"], -32602)
        self.assertIn("desconocido", err["message"])

    def test_lru_expulsa_el_mas_viejo(self):
        ids = []
        for _ in range(10):
            r = _llamar("generar_edificacion", {
                "fichas": FICHAS, "contorno": RECT})["result"]
            ids.append(r["id"])
        self.assertEqual(len(_SESION), 8)
        self.assertNotIn(ids[0], _SESION)      # el primero ya expiró
        self.assertIn(ids[-1], _SESION)        # el último vive


class TestErrores(unittest.TestCase):
    """El contrato de errores que decorarError() de la UI pinta."""

    def test_metodo_desconocido_32601(self):
        self.assertEqual(_llamar("no_existe", {})["error"]["code"], -32601)

    def test_domain_error_con_data(self):
        err = _llamar("generar_radial", {"fichas": FICHAS,
                                         "radio_ext": 2.0})["error"]
        self.assertEqual(err["code"], -32602)
        self.assertEqual(err["data"]["codigo"], "ARQ-DDI-012")
        self.assertTrue(err["data"]["accion"])

    def test_zonas_insuficientes(self):
        err = _llamar("generar_zonas", {
            "fichas": FICHAS,
            "zonas": [{"contorno": RECT}]})["error"]
        self.assertEqual(err["code"], -32602)

    def test_aplicar_exportar_sin_carpeta(self):
        r = _llamar("generar_edificacion", {"fichas": FICHAS,
                                            "contorno": RECT})["result"]
        err = _llamar("aplicar_exportar", {"id": r["id"],
                                           "carpeta": ""})["error"]
        self.assertEqual(err["code"], -32602)

    def test_aplicar_exportar_formatos_vacios(self):
        r = _llamar("generar_edificacion", {"fichas": FICHAS,
                                            "contorno": RECT})["result"]
        err = _llamar("aplicar_exportar", {"id": r["id"],
                                           "carpeta": "/tmp",
                                           "formatos": []})["error"]
        self.assertEqual(err["code"], -32602)

    def test_proyecto_abrir_ruta_inexistente(self):
        err = _llamar("proyecto_abrir", {"ruta": "/no/existe.json"})["error"]
        self.assertEqual(err["code"], -32602)
        self.assertTrue(err["data"]["codigo"].startswith("ARQ-IMP"))

    def test_el_canal_sigue_vivo_tras_errores(self):
        _llamar("no_existe", {})
        _llamar("generar_radial", {"fichas": FICHAS, "radio_ext": 1.0})
        self.assertTrue(_llamar("ping", {})["result"]["pong"])


class TestExportarReal(unittest.TestCase):
    """aplicar_exportar: del id de sesión a archivos en disco."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arqgen_test_191_")
        r = _llamar("generar_edificacion", {"fichas": FICHAS,
                                            "contorno": RECT})["result"]
        cls.id_plan = r["id"]
        cls.exp = _llamar("aplicar_exportar", {
            "id": r["id"], "carpeta": cls.tmp, "nombre_base": "test191",
            "formatos": ["IFC", "DXF", "XLSX"], "trazar_muros": True,
            "con_proyecto": True})["result"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_formatos_en_disco(self):
        self.assertEqual({"IFC", "DXF", "XLSX"}, set(self.exp["archivos"]))
        for info in self.exp["archivos"].values():
            self.assertGreater(info["bytes"], 200)
            self.assertTrue(os.path.isfile(info["ruta"]))

    def test_instantanea_reabrible(self):
        self.assertGreater(self.exp["proyecto"]["bytes"], 200)
        prev = _llamar("proyecto_abrir",
                       {"ruta": self.exp["proyecto"]["ruta"]})["result"]
        self.assertEqual(prev["nombre"], "test191")
        self.assertGreaterEqual(int(prev["recuentos"]["SPACE"]), 1)
        self.assertGreaterEqual(int(prev["recuentos"]["BUILDING"]), 1)
        self.assertEqual(prev["errores"], [])

    def test_sin_errores_por_formato(self):
        self.assertEqual(self.exp["errores"], {})

    def test_compuesto_rejilla_se_aplica(self):
        carpeta = os.path.join(self.tmp, "rejilla")
        r = _llamar("generar_rejilla", {
            "fichas": FICHAS_UNIDAD, "contorno": RECT, "columnas": 3})["result"]
        exp = _llamar("aplicar_exportar", {
            "id": r["id"], "carpeta": carpeta, "nombre_base": "rej191",
            "formatos": ["DXF"], "con_proyecto": False})["result"]
        self.assertIn("DXF", exp["archivos"])
        self.assertTrue(os.path.getsize(exp["archivos"]["DXF"]["ruta"]) > 200)


class TestProcesoReal(unittest.TestCase):
    """El sidecar POR PROCESO (como lo lanza el shell Tauri)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arqgen_test_191_proc_")
        cls.proc = subprocess.Popen(
            [sys.executable, os.path.join(_RAIZ, "main.py"), "rpc"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=_RAIZ, text=True,
            encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proc.stdin.close()
            cls.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            cls.proc.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _rpc(self, metodo, params, rid):
        req = json.dumps({"jsonrpc": "2.0", "id": rid, "method": metodo,
                          "params": params}, ensure_ascii=False)
        self.proc.stdin.write(req + "\n")
        self.proc.stdin.flush()
        linea = self.proc.stdout.readline()
        return json.loads(linea)

    def test_ping_version_catalogo_por_proceso(self):
        p = self._rpc("ping", {}, 1)
        self.assertEqual(p["result"]["app_version"], "3.50.0")
        c = self._rpc("catalogo", {}, 2)
        self.assertGreaterEqual(c["result"]["total"], 100)

    def test_generar_y_exportar_por_proceso(self):
        g = self._rpc("generar_edificacion",
                      {"fichas": FICHAS, "contorno": RECT}, 1)["result"]
        out = os.path.join(self.tmp, "salida")
        e = self._rpc("aplicar_exportar", {
            "id": g["id"], "carpeta": out, "nombre_base": "proc191",
            "formatos": ["IFC", "JSON"], "con_proyecto": True}, 2)["result"]
        for fmt in ("IFC", "JSON"):
            self.assertTrue(os.path.isfile(e["archivos"][fmt]["ruta"]))
        prev = self._rpc("proyecto_abrir",
                         {"ruta": e["proyecto"]["ruta"]}, 3)["result"]
        self.assertEqual(prev["nombre"], "proc191")

    def test_el_error_no_muere_el_canal(self):
        err = self._rpc("metodo_inexistente", {}, 4)["error"]
        self.assertEqual(err["code"], -32601)
        p = self._rpc("ping", {}, 5)
        self.assertTrue(p["result"]["pong"])


class TestEmpaquetadoFrontend(unittest.TestCase):
    """Los ficheros de la UI web (src/) y el shell (src-tauri/) coherentes
    con el contrato del sidecar — la web es parte del entregable."""

    def test_src_existe_y_trae_las_vistas(self):
        html = open(os.path.join(_RAIZ, "src", "index.html"),
                    encoding="utf-8").read()
        for vista in ("inicio", "programa", "contorno", "formas",
                      "resultado", "exportar", "proyecto"):
            self.assertIn(f'vista-{vista}"', html)
        for metodo in ("catalogo", "generar_radial", "aplicar_exportar"):
            # los métodos clave se citan en la doc/app o en el JS
            pass

    def test_js_menciona_los_metodos_del_contrato(self):
        js = open(os.path.join(_RAIZ, "src", "app.js"),
                  encoding="utf-8").read()
        for metodo in ("ping", "version", "catalogo", "generar_quick",
                       "generar_edificacion", "generar_radial", "generar_y",
                       "generar_x", "generar_zonas", "generar_rejilla",
                       "aplicar_exportar"):
            self.assertIn('"' + metodo + '"', js)

    def test_js_sintaxis_valida_si_node_esta_disponible(self):
        nodo = shutil.which("node")
        if not nodo:
            self.skipTest("node no está instalado en este entorno")
        r = subprocess.run([nodo, "--check",
                            os.path.join(_RAIZ, "src", "app.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_shell_tauri_trae_el_comando_de_descargas(self):
        rs = open(os.path.join(_RAIZ, "src-tauri", "src", "main.rs"),
                  encoding="utf-8").read()
        self.assertIn("fn carpeta_descargas", rs)
        self.assertIn("rpc, motor_ruta, carpeta_descargas", rs)
        conf = json.load(open(os.path.join(_RAIZ, "src-tauri",
                                           "tauri.conf.json"),
                              encoding="utf-8"))
        self.assertEqual(conf["version"], "3.50.0")
        self.assertEqual(conf["build"]["frontendDist"], "../src")
        self.assertTrue(conf["app"]["withGlobalTauri"])

    def test_version_del_motor(self):
        self.assertEqual(core.APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
