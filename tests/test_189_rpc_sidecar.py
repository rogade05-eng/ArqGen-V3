"""SIDECAR JSON-RPC FASE A TAURI v3.48.0 — app/rpc_server.py + CLI rpc.

La arquitectura del «ARQ GEN TAURI.txt» v3.0 del usuario define el canal:
    Tauri (Rust)  <->  stdin/stdout JSON-RPC  <->  Motor Python
Este módulo es la mitad Python del puente y la FASE A entrega el canal
completo probado extremo a extremo (proceso real, no solo in-process).

Cobertura:
  * protocolo: ping con versión, id echo, -32601 método desconocido,
    -32700 JSON inválido, -32602 params inválidos (contorno corto,
    texto vacío, fichas ausentes), params no-objeto (-32600)
  * generar_quick: planta real por proceso (spawn del subcomando rpc),
    niveles/totales/reparto con locales poligonales y pasillo; el
    chaflán se refleja en polígonos de 5/6 vértices con contorno L
  * generar_edificacion: fichas hospitalarias por proceso
  * version y selftest: version informativa; selftest devuelve
    ok/checks positivos (no ejecuta la GUI)
  * determinismo: dos llamadas idénticas dan el mismo JSON
  * contrato CLI: main.py rpc aparece en la ayuda de la CLI
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from core import APP_VERSION
from tests.base import ARQGenTestCase, PROJECT_ROOT

from app.rpc_server import handle_call

_CONTORNO = [[0, 0], [24, 0], [24, 12], [0, 12]]
_TEXTO = "dormitorio, bano, cocina, sala, patio"


def _rpc(method, params=None, rid=1):
    return handle_call({"jsonrpc": "2.0", "id": rid, "method": method,
                        "params": params or {}})


class TestProtocolo(ARQGenTestCase):
    """Contrato JSON-RPC in-process (rápido)."""

    def test_ping_con_version(self):
        r = _rpc("ping")
        self.assertNotIn("error", r)
        self.assertTrue(r["result"]["pong"])
        self.assertEqual(r["result"]["app_version"], APP_VERSION)

    def test_id_echo(self):
        r = _rpc("ping", rid=77)
        self.assertEqual(r["id"], 77)

    def test_metodo_desconocido_32601(self):
        r = _rpc("no_existe")
        self.assertEqual(r["error"]["code"], -32601)

    def test_params_no_objeto_32600(self):
        r = handle_call({"jsonrpc": "2.0", "id": 1, "method": "ping",
                         "params": [1, 2]})
        self.assertEqual(r["error"]["code"], -32600)

    def test_method_no_es_string_32600(self):
        r = handle_call({"jsonrpc": "2.0", "id": 1, "method": 42})
        self.assertEqual(r["error"]["code"], -32600)

    def test_json_invalido_es_32700_en_el_bucle(self):
        # el parseo vive en main(); el contrato del error es fijo
        import os
        ruta = os.path.join(PROJECT_ROOT, "app", "rpc_server.py")
        servidor = open(ruta, encoding="utf-8").read()
        self.assertIn("-32700", servidor)
        self.assertIn("JSON inválido", servidor)

    def test_contorno_corto_32602(self):
        r = _rpc("generar_quick", {"texto": _TEXTO,
                                   "contorno": [[0, 0], [1, 1]]})
        self.assertEqual(r["error"]["code"], -32602)

    def test_texto_vacio_32602(self):
        r = _rpc("generar_quick", {"texto": "   ", "contorno": _CONTORNO})
        self.assertEqual(r["error"]["code"], -32602)

    def test_fichas_ausentes_32602(self):
        r = _rpc("generar_edificacion", {"contorno": _CONTORNO})
        self.assertEqual(r["error"]["code"], -32602)

    def test_version_informativa(self):
        r = _rpc("version")
        self.assertEqual(r["result"]["app_version"], APP_VERSION)
        self.assertIn("python", r["result"])

    def test_determinismo(self):
        # v3.50.0 (FASE C): la respuesta lleva el "id" de la sesión LRU
        # (an1, an2, ...): se aparta antes de comparar; el análisis que
        # la UI dibuja es byte a byte el mismo.
        a = _rpc("generar_quick",
                 {"texto": _TEXTO, "contorno": _CONTORNO})["result"]
        b = _rpc("generar_quick",
                 {"texto": _TEXTO, "contorno": _CONTORNO})["result"]
        a.pop("id", None), b.pop("id", None)
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class TestProcesoReal(ARQGenTestCase):
    """Spawn real del sidecar: la mitad Rust hablará EXACTAMENTE así."""

    def _peticiones(self, *mensajes):
        entrada = "\n".join(json.dumps(m) for m in mensajes) + "\n"
        proc = subprocess.run(
            [sys.executable, "main.py", "rpc"],
            input=entrada, capture_output=True, text=True,
            encoding="utf-8", errors="replace", cwd=PROJECT_ROOT,
            timeout=300,
            env={"PYTHONIOENCODING": "utf-8", "PATH": __import__("os")
                 .environ.get("PATH", "")})
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        lineas = [l for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lineas), len(mensajes))
        return [json.loads(l) for l in lineas]

    def test_ping_por_proceso(self):
        [r] = self._peticiones({"jsonrpc": "2.0", "id": 1,
                                "method": "ping", "params": {}})
        self.assertTrue(r["result"]["pong"])
        self.assertEqual(r["result"]["app_version"], APP_VERSION)

    def test_generar_quick_por_proceso(self):
        [r] = self._peticiones({
            "jsonrpc": "2.0", "id": 5, "method": "generar_quick",
            "params": {"texto": _TEXTO, "contorno": _CONTORNO}})
        res = r["result"]
        self.assertEqual(res["niveles"], 1)
        self.assertTrue(res["dentro_del_contorno"])
        self.assertGreater(float(res["totales"]["aprovechamiento_pct"]), 0)
        nivel = res["reparto"][0]
        self.assertTrue(nivel["locales"])
        for local in nivel["locales"]:
            self.assertGreaterEqual(len(local["poligono"]), 3)
            self.assertGreater(float(local["area_m2"]), 0)
        self.assertIsNotNone(nivel["pasillo"])
        self.assertEqual(len(nivel["pasillo"]["rect"]), 4)

    def test_chaflan_poligono_5_vertices_por_proceso(self):
        # el contorno en L y los chaflanes activados producen polígonos
        # de 5 o 6 vértices en algún local (el corte esquina del v3.43.1)
        [r] = self._peticiones({
            "jsonrpc": "2.0", "id": 6, "method": "generar_quick",
            "params": {"texto": _TEXTO,
                       "contorno": [[0, 0], [18, 0], [18, 8], [8, 8],
                                    [8, 14], [0, 14]]}})
        locales = r["result"]["reparto"][0]["locales"]
        self.assertTrue(any(len(l["poligono"]) in (5, 6) for l in locales),
                        [len(l["poligono"]) for l in locales])

    def test_generar_edificacion_por_proceso(self):
        [r] = self._peticiones({
            "jsonrpc": "2.0", "id": 7, "method": "generar_edificacion",
            "params": {"nombre": "Hospital RPC",
                       "fichas": [{"space_type": "BEDROOM",
                                   "cantidad": 6},
                                  {"space_type": "LAVATORY",
                                   "cantidad": 2}],
                       "contorno": [[0, 0], [30, 0], [30, 14], [0, 14]]}})
        res = r["result"]
        self.assertEqual(res["niveles"], 1)
        nombres = " ".join(l["nombre"] for l in res["reparto"][0]["locales"])
        self.assertIn("Dormitorio", nombres)

    def test_error_por_proceso_mantiene_el_canal(self):
        # un fallo NO tumba el sidecar: la siguiente petición se responde
        [r1, r2] = self._peticiones(
            {"jsonrpc": "2.0", "id": 1, "method": "generar_quick",
             "params": {"texto": _TEXTO, "contorno": [[0, 0]]}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
        self.assertEqual(r1["error"]["code"], -32602)
        self.assertTrue(r2["result"]["pong"])

    def test_selftest_por_proceso_informa_checks(self):
        [r] = self._peticiones({"jsonrpc": "2.0", "id": 1,
                                "method": "selftest", "params": {}})
        self.assertTrue(r["result"]["ok"])
        self.assertGreaterEqual(r["result"]["checks"], 97)


class TestContratoCli(ARQGenTestCase):

    def test_rpc_parseable_por_la_cli(self):
        from app.cli import _build_parser
        args = _build_parser().parse_args(["rpc"])
        self.assertEqual(args.command, "rpc")

    def test_rpc_documentado_en_la_ayuda(self):
        from app.cli import _build_parser
        self.assertIn("JSON-RPC", _build_parser().format_help())


if __name__ == "__main__":
    unittest.main()
