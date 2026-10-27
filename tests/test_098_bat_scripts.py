# -*- coding: utf-8 -*-
"""Tests de integridad de los scripts .bat (ops, spec 108).

Incidencia real: los .bat se generaron con fin de linea LF de Unix y
cmd.exe en Windows aborta de forma silenciosa (la ventana se cierra sin
ejecutar nada y sin crear ningun log). Estos tests impiden la regresion
y garantizan ademas: ASCII puro sin BOM, 'pause' en caminos de error,
cd /d al directorio del script y las marcas criticas de cada pipeline.
"""

from __future__ import annotations

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXPECTED_BATS = [
    "00_VERIFICAR_ENTORNO.bat",
    "01_INSTALAR_DEPENDENCIAS.bat",
    "02_PRUEBAS.bat",
    "03_COMPILAR.bat",
    "04_EJECUTAR.bat",
    "05_EJECUTAR_COMPILADO.bat",
    "06_DEMO.bat",
    "07_LIMPIAR.bat",
    "08_GUI.bat",
    "09_GUI_COMPILADO.bat",
]


def read_bat(name: str) -> bytes:
    with open(os.path.join(ROOT, name), "rb") as fh:
        return fh.read()


class BatIntegrityTest(unittest.TestCase):
    """Los .bat deben ser ejecutables por cmd.exe tal como salen del ZIP."""

    def test_01_todos_presentes(self) -> None:
        for name in EXPECTED_BATS:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, name)),
                            f"falta {name}")

    def test_02_sin_bom(self) -> None:
        for name in EXPECTED_BATS:
            raw = read_bat(name)
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"),
                             f"{name} tiene BOM UTF-8 (cmd.exe lo aborta)")

    def test_03_ascii_puro(self) -> None:
        for name in EXPECTED_BATS:
            try:
                read_bat(name).decode("ascii")
            except UnicodeDecodeError as exc:
                self.fail(f"{name} contiene bytes no ASCII (acentos "
                          f"prohibidos en .bat): {exc}")

    def test_04_fin_de_linea_crlf(self) -> None:
        for name in EXPECTED_BATS:
            raw = read_bat(name)
            lf = raw.count(b"\n")
            crlf = raw.count(b"\r\n")
            cr = raw.count(b"\r")
            self.assertGreater(lf, 0, f"{name} esta vacio")
            self.assertEqual(lf, crlf,
                             f"{name} tiene LF sin CR (fin de linea Unix: "
                             f"cmd.exe lo aborta sin dejar log)")
            self.assertEqual(cr, crlf, f"{name} tiene CR sueltos")

    def test_05_primera_linea_echo_off(self) -> None:
        for name in EXPECTED_BATS:
            first = read_bat(name).split(b"\r\n", 1)[0]
            self.assertEqual(first, b"@echo off",
                             f"{name} debe empezar con @echo off")

    def test_06_pausa_para_leer_errores(self) -> None:
        for name in EXPECTED_BATS:
            self.assertIn(b"pause", read_bat(name),
                          f"{name} sin pause: la ventana se cierra sin "
                          f"explicar el error")

    def test_07_cd_al_directorio_del_script(self) -> None:
        for name in EXPECTED_BATS:
            self.assertIn(b'cd /d "%ROOT%"', read_bat(name),
                          f"{name} sin cd /d %ROOT% (falla si se ejecuta "
                          f"como administrador)")

    def test_08_soporte_automatizacion_arq_nopause(self) -> None:
        for name in EXPECTED_BATS:
            self.assertIn(b"ARQ_NOPAUSE", read_bat(name),
                          f"{name} no respeta ARQ_NOPAUSE para automation")

    def test_09_compilar_incluye_gui_plugins_y_3_logs(self) -> None:
        raw = read_bat("03_COMPILAR.bat")
        self.assertIn(b"--collect-submodules ui", raw)
        self.assertIn(b"--collect-submodules plugins.builtin", raw)
        self.assertIn(b"--add-data \"resources;resources\"", raw)
        for marker in (b"pre_build_", b"build_", b"post_build_"):
            self.assertIn(marker, raw, f"03_COMPILAR.bat sin log {marker!r}")

    def test_10_detector_python_en_00(self) -> None:
        raw = read_bat("00_VERIFICAR_ENTORNO.bat")
        self.assertIn(b"py -3.13", raw)
        self.assertIn(b"python_home.txt", raw)
        self.assertIn(b"ARQ_PY_EXE", raw)

    def test_11_gui_lanza_main_gui(self) -> None:
        raw = read_bat("08_GUI.bat")
        self.assertIn(b"main.py gui", raw)

    def test_12_demo_guarda_goto_error(self) -> None:
        raw = read_bat("06_DEMO.bat")
        self.assertIn(b"goto error", raw)
        self.assertIn(b":error", raw)

    def test_13_resolvedor_en_cascada(self) -> None:
        # Los scripts que ejecutan Python usan el resolvedor en cascada:
        # .venv -> config\python_home.txt -> autodeteccion validada
        for name in ("02_PRUEBAS.bat", "03_COMPILAR.bat", "04_EJECUTAR.bat",
                     "06_DEMO.bat", "08_GUI.bat"):
            raw = read_bat(name)
            self.assertIn(b":resolve_py", raw, f"{name} sin resolvedor")
            self.assertIn(b".venv\\Scripts\\python.exe", raw)
            self.assertIn(b"python_home.txt", raw)
            self.assertIn(b"py -3.13", raw)

    # ------------------------------------------------------------------
    # Regression v1.6.2: un ')' literal dentro de un bloque if (...) de
    # cmd.exe cierra el bloque aunque este dentro del texto de un echo.
    # v1.6.1 introdujo `echo [ERROR] Etapa 1 (pruebas...) fallida` dentro
    # de bloques y 03_COMPILAR.bat abortaba tras las pruebas previas sin
    # compilar nunca (logs\build vacio). Este test parsea los bloques de
    # los 9 scripts y prohibe parentesis literales no estructurales.
    # ------------------------------------------------------------------

    FOR_IN_RE = re.compile(r" in \(.*\) do ")

    @staticmethod
    def _strip_quotes(line: str) -> str:
        out, in_dq, in_sq = [], False, False
        for ch in line:
            if ch == '"' and not in_sq:
                in_dq = not in_dq
                continue
            if ch == "'" and not in_dq:
                in_sq = not in_sq
                continue
            if not in_dq and not in_sq:
                out.append(ch)
        return "".join(out)

    def _block_violations(self, name: str) -> list:
        violations = []
        depth = 0
        text = read_bat(name).decode("ascii")
        for n, raw in enumerate(text.split("\r\n"), 1):
            s = self._strip_quotes(raw).strip()
            if not s:
                continue
            if depth == 0:
                if s.endswith("("):
                    depth = 1
                continue
            if s == ")":
                depth -= 1
                continue
            if s.startswith(")") and s.endswith("("):
                middle = s[1:-1]
                if "(" not in middle and ")" not in middle:
                    continue  # ') else (' cierra y reabre
                violations.append((n, raw))
                continue
            probe = self.FOR_IN_RE.sub(" do ", s)
            if probe.endswith("(") and probe.count("(") == 1 \
                    and probe.count(")") == 0:
                depth += 1  # apertura anidada
                continue
            if "(" in probe or ")" in probe:
                violations.append((n, raw))
        if depth != 0:
            violations.append(("EOF", f"bloque sin cerrar depth={depth}"))
        return violations

    def test_14_sin_parentesis_letales_en_bloques(self) -> None:
        for name in EXPECTED_BATS:
            violations = self._block_violations(name)
            self.assertEqual(
                violations, [],
                f"{name}: parentesis literales dentro de un bloque if/for "
                f"(cmd.exe rompe el bloque y el .bat aborta): {violations}")

    def test_15_latido_de_arranque_bat_boot(self) -> None:
        # Diagnostico: logs\bat_boot.log prueba que el script llego a
        # ejecutarse aunque falle todo lo demas.
        for name in EXPECTED_BATS:
            raw = read_bat(name)
            self.assertIn(b"bat_boot.log", raw, f"{name} sin latido INICIO")
            self.assertIn(b"INICIO", raw)
            self.assertIn(b"scripts v", raw, f"{name} sin marca de version")

    def test_16_stamp_fallback_sin_powershell(self) -> None:
        # Si powershell esta bloqueado por politica, STAMP queda vacio;
        # el fallback evita nombres de log invalidos.
        for name in ("00_VERIFICAR_ENTORNO.bat", "01_INSTALAR_DEPENDENCIAS.bat",
                     "02_PRUEBAS.bat", "03_COMPILAR.bat", "06_DEMO.bat"):
            self.assertIn(b"if not defined STAMP set \"STAMP=%RANDOM%%RANDOM%\"",
                          read_bat(name), f"{name} sin fallback de STAMP")

    # ------------------------------------------------------------------
    # Regression v1.6.3: PyInstaller aborta con "attempt to collect
    # multiple Qt bindings packages" cuando en el equipo estan instalados
    # PySide6 y PyQt5 a la vez (p.ej. Python global usado para otros
    # proyectos). La cadena es: ezdxf -> ezdxf.npshapes importa
    # ezdxf.addons.xqt (import perezoso, nunca ejecutado por ARQ GEN) y
    # xqt intenta PySide6 y PyQt5 con guardas try/except. La GUI de
    # ARQ GEN es Tkinter, asi que TODOS los bindings Qt se excluyen del
    # ejecutable con --exclude-module.
    # ------------------------------------------------------------------

    QT_EXCLUDES = (
        b"--exclude-module PySide6",
        b"--exclude-module shiboken6",
        b"--exclude-module PySide2",
        b"--exclude-module shiboken2",
        b"--exclude-module PyQt5",
        b"--exclude-module PyQt6",
    )

    def test_17_compilar_excluye_todos_los_bindings_qt(self) -> None:
        raw = read_bat("03_COMPILAR.bat")
        for flag in self.QT_EXCLUDES:
            self.assertIn(flag, raw,
                          f"03_COMPILAR.bat sin {flag.decode()!r}: la "
                          f"compilacion aborta si el equipo tiene varios "
                          f"bindings Qt instalados")

    def test_18_gui_compilada_con_lanzador_propio(self) -> None:
        # v1.6.4: la GUI del ejecutable debe ser alcanzable sin Python:
        # 09_GUI_COMPILADO.bat lanza 'ARQ_GEN.exe gui'; 05 anuncia la GUI
        # en su ayuda; y el exe sin argumentos abre la ventana (main.py).
        raw09 = read_bat("09_GUI_COMPILADO.bat")
        self.assertIn(b"dist\\ARQ_GEN\\ARQ_GEN.exe gui", raw09)
        self.assertIn(b"no existe dist", raw09,
                      "09 sin guard de ejecutable ausente")
        raw05 = read_bat("05_EJECUTAR_COMPILADO.bat")
        self.assertIn(b"09_GUI_COMPILADO.bat", raw05,
                      "05 no anuncia el lanzador de la GUI compilada")
        self.assertIn(b'len(sys.argv) == 1',
                      open(os.path.join(ROOT, "main.py"), "rb").read(),
                      "main.py sin apertura de GUI por defecto en el exe")


if __name__ == "__main__":
    unittest.main()
