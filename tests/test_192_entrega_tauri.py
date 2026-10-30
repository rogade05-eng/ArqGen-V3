"""Regresiones del shell Tauri y las puertas de calidad de entrega."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class TestEntregaTauri(unittest.TestCase):
    def test_version_shell_coincide_con_configuracion_y_motor(self):
        import core
        # tomllib es parte de Python 3.13, la versión soportada del proyecto.
        import tomllib
        with (ROOT / "src-tauri" / "Cargo.toml").open("rb") as archivo:
            version = tomllib.load(archivo)["package"]["version"]
        config = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(version, config["version"])
        self.assertEqual(version, core.APP_VERSION)

    def test_scripts_windows_tienen_atributo_crlf(self):
        atributos = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.bat -text", atributos)

    def test_ci_clasico_bloquea_la_entrega_si_fallan_pruebas(self):
        flujo = (ROOT / ".github/workflows/compilar.yml").read_text(encoding="utf-8")
        paso = flujo.split("Etapa 1 - Suite de pruebas", 1)[1].split("Etapa 2 -", 1)[0]
        self.assertNotIn("continue-on-error: true", paso)
        self.assertIn('throw "La suite de pruebas fallo', paso)
        self.assertIn("pull_request:", flujo)

    def test_ci_tauri_compila_y_ejecuta_pruebas_del_resolvedor(self):
        flujo = (ROOT / ".github/workflows/compilar_tauri.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", flujo)
        self.assertIn("python -m unittest discover -s tests", flujo)
        self.assertIn("throw 'La suite fallo; no se publicara Tauri'", flujo)
        self.assertIn("rustc --edition 2021 --test src-tauri/src/motor_path.rs", flujo)
        self.assertIn("cargo tauri build", flujo)

    def test_instalacion_cli_usa_requisito_semver_valido(self):
        # Cargo 1.99 rechaza el requisito ambiguo "2". Las comillas además
        # preservan el acento circunflejo en PowerShell y cmd.exe.
        for nombre in (".github/workflows/compilar_tauri.yml",
                       "LEEME_FASE_A_TAURI.md", "LEEME_FASE_C_TAURI.md"):
            with self.subTest(archivo=nombre):
                texto = (ROOT / nombre).read_text(encoding="utf-8")
                self.assertIn('cargo install tauri-cli --version "^2" --locked', texto)
                self.assertNotIn('cargo install tauri-cli --version 2 --locked', texto)

    @unittest.skipUnless(shutil.which("rustc"), "rustc no instalado")
    def test_resolvedor_motor_rust(self):
        # El módulo es std-only: sus pruebas no necesitan Tauri ni red.
        with tempfile.TemporaryDirectory() as carpeta:
            exe = Path(carpeta) / ("motor_path_tests.exe" if os.name == "nt" else "motor_path_tests")
            compilacion = subprocess.run(
                [shutil.which("rustc"), "--edition", "2021", "--test",
                 str(ROOT / "src-tauri/src/motor_path.rs"), "-o", str(exe)],
                capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(compilacion.returncode, 0, compilacion.stderr)
            ejecucion = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
            self.assertEqual(ejecucion.returncode, 0, ejecucion.stdout + ejecucion.stderr)


if __name__ == "__main__":
    unittest.main()
