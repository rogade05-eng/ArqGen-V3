# -*- coding: utf-8 -*-
"""DWG de entrada (pasarela a conversores locales) y bundle PyInstaller.

v3.4.0. Cubre:

- importers.dwg_reader: read_version (cabecera de 6 bytes), find_converters
  (env ARQGEN_DWG2DXF, PATH, rutas ODA), build_command (puro) y
  DwgGateway.prepare (nunca lanza: éxito, fallo del conversor, timeout).
- Pipeline §94 completo con un conversor FALSO (script local) y CLI
  `importar dwg`.
- GUI: open_importar_dxf acepta .dwg (conversión → análisis → importar).
- Bundle: ARQ_GEN.spec en paridad con 03_COMPILAR.bat y el verificador
  compilar_bundle.verificar_bundle con runner inyectable.
"""

from __future__ import annotations

import os
import tempfile
from io import StringIO
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch
import unittest

from tests.base import ARQGenTestCase, PROJECT_ROOT

ROOT = PROJECT_ROOT


# -- utilidades ---------------------------------------------------------------
def _make_dwg(path: str, code: bytes = b"AC1015", pad: int = 64) -> None:
    """DWG de prueba: cabecera de versión + relleno (el conversor falso
    ignora el contenido)."""
    with open(path, "wb") as fh:
        fh.write(code + b"\x00" * pad)


def _write_dxf(path: str) -> None:
    """DXF mínimo: 2 muros y 1 local — es lo que 'producirá' el falso."""
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (6, 0), dxfattribs={"layer": "ARQ-MUROS"})
    msp.add_line((6, 0), (6, 4), dxfattribs={"layer": "ARQ-MUROS"})
    msp.add_lwpolyline([(0.2, 0.2), (5.8, 0.2), (5.8, 3.8), (0.2, 3.8)],
                       close=True, dxfattribs={"layer": "ARQ-LOCAL"})
    msp.add_text("SALA", height=0.3).set_placement((2.0, 2.0))
    doc.saveas(path)


def _fake_converter(directory: str, fixed_dxf: str, name: str = "fakeconv",
                    sleep: bool = False) -> str:
    """Conversor falso: copia ``fixed_dxf`` a su argumento de salida.
    Sirve con el patrón custom (<exe> <in> <out>) y libredwg
    (-o <out> <in>): en ambos el OUT es el 2.º parámetro."""
    if os.name == "nt":
        path = os.path.join(directory, name + ".bat")
        body = "@echo off\r\n"
        if sleep:
            body += "ping -n 11 127.0.0.1 >nul\r\n"
        body += 'copy /y "%s" "%%~2" >nul\r\n' % fixed_dxf
    else:
        path = os.path.join(directory, name + ".sh")
        body = "#!/bin/sh\n"
        if sleep:
            body += "sleep 10\n"
        body += 'cp "%s" "$2"\n' % fixed_dxf
    with open(path, "w", newline="") as fh:
        fh.write(body)
    if os.name != "nt":
        os.chmod(path, 0o755)
    return path


def _fixture(tmp: str):
    """(dwg, conversor_falso, dxf_fijo) para todos los grupos."""
    fixed_dxf = os.path.join(tmp, "fixed.dxf")
    _write_dxf(fixed_dxf)
    converter = _fake_converter(tmp, fixed_dxf)
    dwg = os.path.join(tmp, "plano.dwg")
    _make_dwg(dwg)
    return dwg, converter, fixed_dxf


def _run_cli(argv, log_dir):
    from app.cli import run
    with patch("sys.stdout", new=StringIO()) as out:
        code = run(["--log-dir", log_dir] + list(argv))
    return code, out.getvalue()


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 — headless
        return False


DISPLAY = _display_available()


# -- read_version --------------------------------------------------------------
class TestReadVersion(ARQGenTestCase):

    def test_todas_las_versiones_tabuladas(self):
        from importers.dwg_reader import DWG_VERSIONS, read_version
        expected = {"AC1009": "AutoCAD R11/R12", "AC1015": "AutoCAD 2000",
                    "AC1018": "AutoCAD 2004", "AC1021": "AutoCAD 2007",
                    "AC1024": "AutoCAD 2010", "AC1027": "AutoCAD 2013",
                    "AC1032": "AutoCAD 2018"}
        for code, label in expected.items():
            path = os.path.join(self.tmp, code + ".dwg")
            _make_dwg(path, code.encode("ascii"))
            info = read_version(path)
            self.assertTrue(info["ok"], code)
            self.assertEqual(info["label"], label)
            self.assertGreater(info["year"], 1980)
        self.assertIn("AC1015", DWG_VERSIONS)

    def test_fichero_inexistente_sin_excepcion(self):
        from importers.dwg_reader import read_version
        info = read_version(os.path.join(self.tmp, "no", "existe.dwg"))
        self.assertFalse(info["ok"])
        self.assertTrue(info["error"])

    def test_cabecera_basura_y_corta(self):
        from importers.dwg_reader import read_version
        bad = os.path.join(self.tmp, "bad.dwg")
        with open(bad, "wb") as fh:
            fh.write(b"ZZZZZZ" + b"\x00" * 16)
        self.assertFalse(read_version(bad)["ok"])
        short = os.path.join(self.tmp, "short.dwg")
        with open(short, "wb") as fh:
            fh.write(b"AC")
        self.assertFalse(read_version(short)["ok"])

    def test_version_ac_no_tabulada_se_acepta(self):
        from importers.dwg_reader import read_version
        path = os.path.join(self.tmp, "futuro.dwg")
        _make_dwg(path, b"AC1099")
        info = read_version(path)
        self.assertTrue(info["ok"])
        self.assertEqual(info["family"], "desconocida")


# -- find_converters / build_command -------------------------------------------
class TestConverters(ARQGenTestCase):

    def test_env_arqgen_dwg2dxf_tiene_prioridad(self):
        from importers.dwg_reader import find_converters
        exe = os.path.join(self.tmp, "micv.bat" if os.name == "nt"
                           else "micv.sh")
        with open(exe, "w") as fh:
            fh.write("x")
        old = os.environ.get("ARQGEN_DWG2DXF")
        os.environ["ARQGEN_DWG2DXF"] = exe
        try:
            found = find_converters()
            self.assertEqual(found[0]["kind"], "custom")
            self.assertEqual(found[0]["path"], exe)
        finally:
            if old is None:
                os.environ.pop("ARQGEN_DWG2DXF", None)
            else:
                os.environ["ARQGEN_DWG2DXF"] = old

    def test_env_con_ruta_inexistente_se_ignora(self):
        from importers.dwg_reader import find_converters
        old = os.environ.get("ARQGEN_DWG2DXF")
        os.environ["ARQGEN_DWG2DXF"] = os.path.join(self.tmp, "falta.exe")
        try:
            for conv in find_converters():
                self.assertNotEqual(conv["kind"], "custom")
        finally:
            if old is None:
                os.environ.pop("ARQGEN_DWG2DXF", None)
            else:
                os.environ["ARQGEN_DWG2DXF"] = old

    def test_preferido_inexistente_devuelve_vacio(self):
        from importers.dwg_reader import find_converters
        self.assertEqual(find_converters(
            os.path.join(self.tmp, "no_esta.exe")), [])

    def test_build_command_tres_tipos(self):
        from importers.dwg_reader import build_command
        src = os.path.join("c", "carpeta con espacios", "plano.dwg")
        out_dir = os.path.join("c", "tmp")
        args, out = build_command({"kind": "libredwg", "path": "dwg2dxf",
                                   "name": "L"}, src, out_dir)
        self.assertEqual(args[0], "dwg2dxf")
        self.assertEqual(args[1], "-o")
        self.assertTrue(out.endswith("plano.dxf"))
        self.assertEqual(args[2], out)
        self.assertEqual(args[3], src)
        args, out = build_command({"kind": "oda", "path": "ODA",
                                   "name": "O"}, src, out_dir)
        self.assertEqual(args[0], "ODA")
        self.assertEqual(args[3:6], ["ACAD2018", "DXF", "0"])
        self.assertTrue(out.endswith("plano.dxf"))
        args, out = build_command({"kind": "custom", "path": "cv",
                                   "name": "C"}, src, out_dir)
        self.assertEqual(args, ["cv", src, out])


# -- DwgGateway ------------------------------------------------------------------
class TestDwgGateway(ARQGenTestCase):

    def test_exito_con_conversor_falso(self):
        from importers.dwg_reader import DwgGateway
        dwg, converter, _ = _fixture(self.tmp)
        prep = DwgGateway().prepare(dwg, converter=converter)
        self.assertTrue(prep["ok"], prep["errors"])
        self.assertTrue(os.path.isfile(prep["dxf_path"]))
        self.assertEqual(prep["version"]["code"], "AC1015")
        self.assertEqual(prep["command"][0], converter)
        self.assertTrue(prep["dxf_path"].endswith("plano.dxf"))

    def test_luego_del_gateway_el_dxf_pasa_por_el_94(self):
        from importers.dwg_reader import DwgGateway
        from importers.dxf_reader import DxfImporter
        dwg, converter, _ = _fixture(self.tmp)
        prep = DwgGateway().prepare(dwg, converter=converter)
        self.assertTrue(prep["ok"], prep["errors"])
        report = DxfImporter().preview(prep["dxf_path"])
        self.assertEqual(report["counts"]["walls"], 2)
        self.assertEqual(report["counts"]["spaces"], 1)
        self.assertEqual(report["spaces_preview"][0]["name"], "SALA")

    def test_instrucciones_cuando_no_hay_ningun_conversor(self):
        from importers.dwg_reader import DwgGateway
        dwg, _, _ = _fixture(self.tmp)
        with mock.patch("importers.dwg_reader.find_converters",
                        return_value=[]):
            prep = DwgGateway().prepare(dwg)
        self.assertFalse(prep["ok"])
        joined = " ".join(prep["errors"])
        self.assertIn("ODA File Converter", joined)
        self.assertIn("ARQGEN_DWG2DXF", joined)

    def test_convertidor_indicado_inexistente(self):
        from importers.dwg_reader import DwgGateway
        dwg, _, _ = _fixture(self.tmp)
        prep = DwgGateway().prepare(
            dwg, converter=os.path.join(self.tmp, "no_esta.exe"))
        self.assertFalse(prep["ok"])
        self.assertIn("no existe", " ".join(prep["errors"]))

    def test_conversor_que_falla_reporta_stderr(self):
        from importers.dwg_reader import DwgGateway
        dwg, _, _ = _fixture(self.tmp)
        if os.name == "nt":
            bad = os.path.join(self.tmp, "bad.bat")
            body = "@echo off\r\nexit /b 3\r\n"
        else:
            bad = os.path.join(self.tmp, "bad.sh")
            body = "#!/bin/sh\necho boom 1>&2\nexit 3\n"
        with open(bad, "w", newline="") as fh:
            fh.write(body)
        if os.name != "nt":
            os.chmod(bad, 0o755)
        prep = DwgGateway().prepare(dwg, converter=bad)
        self.assertFalse(prep["ok"])
        self.assertTrue(any("3" in err for err in prep["errors"]),
                        prep["errors"])

    def test_timeout_del_conversor(self):
        from importers.dwg_reader import DwgGateway
        dwg, _, fixed = _fixture(self.tmp)
        slow = _fake_converter(self.tmp, fixed, name="slow", sleep=True)
        prep = DwgGateway(timeout_s=0.5).prepare(dwg, converter=slow)
        self.assertFalse(prep["ok"])
        self.assertTrue(any("tard" in err for err in prep["errors"]),
                        prep["errors"])

    def test_entrada_no_dwg_y_archivo_inexistente(self):
        from importers.dwg_reader import DwgGateway
        gw = DwgGateway()
        prep = gw.prepare(os.path.join(self.tmp, "falta.dwg"))
        self.assertFalse(prep["ok"])
        dxf = os.path.join(self.tmp, "plano.dxf")
        _write_dxf(dxf)
        prep = gw.prepare(dxf)
        self.assertFalse(prep["ok"])
        self.assertIn(".dwg", prep["errors"][0])

    def test_aplicar_completo_a_traves_del_gateway(self):
        from importers.dwg_reader import DwgGateway
        from importers.dxf_reader import DxfImporter
        from services.architecture_service import ArchitectureService
        dwg, converter, _ = _fixture(self.tmp)
        context = self.demo_context()
        pid = context.project.id
        before = len(context.architecture.list("WALL", pid))
        prep = DwgGateway().prepare(dwg, converter=converter)
        self.assertTrue(prep["ok"], prep["errors"])
        counts = DxfImporter().apply(
            prep["dxf_path"], ArchitectureService(context), "Nivel DWG",
            thickness_m=0.15)
        self.assertEqual(counts["walls"], 2)
        self.assertEqual(counts["spaces"], 1)
        self.assertEqual(counts["level"], "Nivel DWG")
        self.assertEqual(
            len(context.architecture.list("WALL", pid)), before + 2)
        context.commit()
        context.close()


# -- CLI importar dwg ---------------------------------------------------------
class TestCLIDwg(ARQGenTestCase):

    def test_parser_dwg_acepta_convertidor(self):
        from app.cli import _build_parser
        args = _build_parser().parse_args(
            ["importar", "dwg", "plano.dwg", "--file", "p.arqgen",
             "--convertidor", "cv.exe", "--aplicar"])
        self.assertEqual(args.command, "importar")
        self.assertEqual(args.subcommand, "dwg")
        self.assertEqual(args.convertidor, "cv.exe")
        self.assertTrue(args.aplicar)

    def test_flujo_completo_cli_con_conversor_falso(self):
        dwg, converter, _ = _fixture(self.tmp)
        project = os.path.join(self.tmp, "cli.arqgen")
        log = os.path.join(self.tmp, "logs")
        rc, out = _run_cli(["project", "create", project, "--name",
                            "CLI DWG"], log)
        self.assertEqual(rc, 0, out)
        rc, out = _run_cli(["importar", "dwg", dwg, "--file", project,
                            "--convertidor", converter,
                            "--nivel", "Planta CLI", "--aplicar"], log)
        self.assertEqual(rc, 0, out)
        self.assertIn("convertido con", out)
        from services.context import ApplicationContext
        ctx = ApplicationContext().open_project(project)
        pid = ctx.project.id
        self.assertEqual(len(ctx.architecture.list("WALL", pid)), 2)
        self.assertEqual(len(ctx.architecture.list("SPACE", pid)), 1)
        ctx.close()

    def test_cli_sin_conversor_devuelve_1(self):
        dwg, _, _ = _fixture(self.tmp)
        log = os.path.join(self.tmp, "logs")
        rc, out = _run_cli(
            ["importar", "dwg", dwg, "--file",
             os.path.join(self.tmp, "x.arqgen"),
             "--convertidor", os.path.join(self.tmp, "no_esta.exe")], log)
        self.assertEqual(rc, 1)
        self.assertIn("ERROR", out)


# -- bundle: spec en paridad con el bat ----------------------------------------
class TestSpecBatParity(unittest.TestCase):

    def _read(self, name: str) -> str:
        with open(os.path.join(ROOT, name), "r", encoding="utf-8") as fh:
            return fh.read()

    def test_spec_existe_y_compila(self):
        path = os.path.join(ROOT, "ARQ_GEN.spec")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        compile(source, path, "exec")  # sintaxis válida

    def test_paridad_datas_y_entrada(self):
        spec = self._read("ARQ_GEN.spec")
        bat = self._read("03_COMPILAR.bat")
        self.assertIn('("resources", "resources")', spec)
        self.assertIn('--add-data "resources;resources"', bat)
        self.assertIn('["main.py"]', spec)
        self.assertIn("main.py", bat)
        self.assertIn('name="ARQ_GEN"', spec)
        self.assertIn("--name ARQ_GEN", bat)

    def test_paridad_submodulos(self):
        spec = self._read("ARQ_GEN.spec")
        bat = self._read("03_COMPILAR.bat")
        self.assertIn('_submodules("ui")', spec)
        self.assertIn('_submodules("plugins.builtin")', spec)
        self.assertIn("--collect-submodules ui", bat)
        self.assertIn("--collect-submodules plugins.builtin", bat)

    def test_paridad_exclusiones_qt(self):
        spec = self._read("ARQ_GEN.spec")
        bat = self._read("03_COMPILAR.bat")
        for qt in ("PySide6", "shiboken6", "PySide2", "shiboken2",
                   "PyQt5", "PyQt6"):
            self.assertIn('"%s"' % qt, spec, qt)
            self.assertIn("--exclude-module %s" % qt, bat, qt)

    def test_submodules_del_spec_recubre_ui_y_plugins(self):
        # evalúa _submodules extraída del spec (sin PyInstaller en el entorno)
        import re
        source = self._read("ARQ_GEN.spec")
        match = re.search(r"def _submodules\(package: str\) -> list:"
                          r".*?return found", source, re.S)
        self.assertIsNotNone(match)
        namespace = {"os": os, "SPEC_DIR": ROOT}
        exec("import os\n" + match.group(0), namespace)  # noqa: S102
        submods = namespace["_submodules"]("ui") + \
            namespace["_submodules"]("plugins.builtin")
        self.assertIn("ui.app_window", submods)
        self.assertIn("ui.building_wizard", submods)
        self.assertIn("plugins.builtin.precons_plugin", submods)
        self.assertNotIn("ui.__init__", submods)

    def test_bat_mantiene_pipeline_3_etapas_con_selftest(self):
        bat = self._read("03_COMPILAR.bat")
        self.assertIn("ARQ_GEN.exe selftest", bat)
        self.assertIn("--clean", bat)
        self.assertIn("pre_build_", bat)
        self.assertIn("post_build_", bat)


# -- verificador del bundle (runner inyectable) --------------------------------
class TestVerificarBundle(ARQGenTestCase):

    def _fake_dist(self) -> str:
        from compilar_bundle import binary_name
        dist = os.path.join(self.tmp, "dist")
        app = os.path.join(dist, "ARQ_GEN")
        internal = os.path.join(app, "_internal")
        os.makedirs(internal, exist_ok=True)
        with open(os.path.join(app, binary_name()), "wb") as fh:
            fh.write(b"\x7fELF-fake")
        res = os.path.join(internal, "resources")
        big = os.path.join(res, "rulesets",
                           "precons_iii_rospres_330.json")
        os.makedirs(os.path.dirname(big), exist_ok=True)
        with open(big, "wb") as fh:
            fh.write(b"{}" * 550_001)  # > 1_000_000 bytes
        for rel in ("rulesets/precons_cuba_v1.json",
                    "rulesets/international_v1.json",
                    "branding/logo.ico", "branding/logo.png",
                    "knowledge/neufert_standards.json",
                    "knowledge/space_dna.json",
                    "budget_templates/residential_v1.json"):
            path = os.path.join(res, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(b"x" * 128)
        # el documento hospitalario se exige con un mínimo real (100 KB)
        hsp = os.path.join(res, "knowledge", "hospital_specs.json")
        with open(hsp, "wb") as fh:
            fh.write(b"x" * 100_500)
        # el catálogo de viviendas se exige con un mínimo real (25 KB)
        viv = os.path.join(res, "knowledge", "vivienda_catalogo.json")
        with open(viv, "wb") as fh:
            fh.write(b"x" * 25_500)
        # el documento comercial se exige con un mínimo real (25 KB)
        com = os.path.join(res, "knowledge", "comercial_specs.json")
        with open(com, "wb") as fh:
            fh.write(b"x" * 25_500)
        # el documento educacional se exige con un mínimo real (25 KB)
        edu = os.path.join(res, "knowledge", "educacion_specs.json")
        with open(edu, "wb") as fh:
            fh.write(b"x" * 110_500)
        return dist

    @staticmethod
    def _runner(rc=0, stdout="RESULTADO: CORRECTO\n", stderr=""):
        def run(args, **_kw):
            if "certificar" in args:
                return SimpleNamespace(returncode=rc, stdout="CERTIFICADO "
                                       "PRECONS OK\n", stderr=stderr)
            return SimpleNamespace(returncode=rc, stdout=stdout,
                                   stderr=stderr)
        return run

    def test_verificacion_ok_con_runner_falso(self):
        from compilar_bundle import verificar_bundle
        dist = self._fake_dist()
        ok, checks = verificar_bundle(dist, runner=self._runner())
        self.assertTrue(ok, checks)
        self.assertNotIn("FAIL", [mark for mark, _ in checks])
        self.assertTrue(any("selftest" in text for _, text in checks))

    def test_falta_ejecutable_falla(self):
        from compilar_bundle import verificar_bundle
        ok, checks = verificar_bundle(os.path.join(self.tmp, "vacio"))
        self.assertFalse(ok)
        self.assertTrue(checks[0][0].startswith("FAIL"))

    def test_recurso_faltante_falla(self):
        from compilar_bundle import verificar_bundle
        dist = self._fake_dist()
        os.remove(os.path.join(dist, "ARQ_GEN", "_internal", "resources",
                               "branding", "logo.ico"))
        ok, checks = verificar_bundle(dist, runner=self._runner())
        self.assertFalse(ok)

    def test_selftest_fallido_falla(self):
        from compilar_bundle import verificar_bundle
        dist = self._fake_dist()
        ok, checks = verificar_bundle(
            dist, runner=self._runner(rc=1,
                                      stdout="RESULTADO: CON FALLOS"))
        self.assertFalse(ok)
        self.assertTrue(any(mark == "FAIL" and "selftest" in text
                            for mark, text in checks))

    def test_full_ejecuta_precons_certificar(self):
        from compilar_bundle import verificar_bundle
        dist = self._fake_dist()
        seen = []
        base = self._runner()

        def run(args, **kw):
            seen.append(list(args))
            return base(args, **kw)

        ok, checks = verificar_bundle(dist, runner=run, full=True)
        self.assertTrue(ok, checks)
        self.assertTrue(any("certificar" in arg for a in seen
                            for arg in a))
        self.assertTrue(any("precons certificar" in text
                            for _, text in checks))


# -- GUI: .dwg dentro del diálogo §94 ------------------------------------------
@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDWGGuiFlow(ARQGenTestCase):
    """Flujo DWG completo en el diálogo real: convertir → analizar →
    importar, con conversor falso."""

    def setUp(self):
        super().setUp()
        from ui import theme
        from ui.app_window import ARQGenWindow
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")
        theme.set_mode("dark")
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()
        self.window._dxf_sync = True
        self.dwg, self.converter, _ = _fixture(self.tmp)

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_analizar_dwg_muestra_conversion_y_conteos(self):
        window = self.window
        window.open_importar_dxf()
        window._dxf_path.insert(0, self.dwg)
        window._dxf_converter.insert(0, self.converter)
        window._dxf_analyze()
        report = window._dxf_report.get("1.0", "end")
        self.assertIn("CONVERSIÓN DWG → DXF TEMPORAL", report)
        self.assertIn("AutoCAD 2000", report)
        counts = window._dxf_result.get("counts", {})
        self.assertEqual(counts.get("walls"), 2)
        self.assertEqual(counts.get("spaces"), 1)
        self.assertTrue(window._dxf_source.endswith(".dxf"))

    def test_importar_dwg_crea_objetos_en_el_proyecto(self):
        from services.architecture_service import ArchitectureService
        window = self.window
        window.open_importar_dxf()
        window._dxf_path.insert(0, self.dwg)
        window._dxf_converter.insert(0, self.converter)
        window._dxf_level.delete(0, "end")
        window._dxf_level.insert(0, "Nivel DWG GUI")
        window._dxf_analyze()
        pid = self.context.project.id
        before = len(self.context.architecture.list("WALL", pid))
        window._dxf_apply()
        result = window._dxf_result
        self.assertEqual(result.get("walls"), 2)
        self.assertEqual(result.get("spaces"), 1)
        self.assertEqual(result.get("level"), "Nivel DWG GUI")
        self.assertEqual(
            len(self.context.architecture.list("WALL", pid)), before + 2)

    def test_aplicar_dwg_sin_analizar_avisa(self):
        window = self.window
        window.open_importar_dxf()
        window._dxf_path.insert(0, self.dwg)
        window._dxf_apply()
        self.assertIn("Primero analiza el plano .dwg",
                      window._dxf_status.get())

    def test_dwg_con_convertidor_inexistente_muestra_error(self):
        window = self.window
        window.open_importar_dxf()
        window._dxf_path.insert(0, self.dwg)
        window._dxf_converter.insert(
            0, os.path.join(self.tmp, "no_esta.exe"))
        window._dxf_analyze()
        report = window._dxf_report.get("1.0", "end")
        self.assertIn("ERROR", report)
        self.assertIn("no existe", report)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
