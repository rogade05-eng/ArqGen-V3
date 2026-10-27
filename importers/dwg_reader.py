"""DWG input gateway (spec 94, extensión v3.4.0).

DWG es el formato binario propietario de AutoCAD: reimplementarlo
completo y fiable no es viable offline, así que ARQ GEN entra por la
puerta honesta — pasarela de conversión local a DXF y luego el motor
§94 ya certificado (DxfImporter):

    .dwg ──(conversor local gratuito)──> .dxf ──> DxfImporter §94

Conversores soportados (todos locales, cero red):
- LibreDWG ``dwg2dxf`` (open source) — buscado en el PATH.
- ODA File Converter (gratuito, Open Design Alliance) — PATH y rutas
  de instalación típicas de Windows/macOS/Linux.
- Convertidor personalizado indicado por el usuario (GUI o variable de
  entorno ``ARQGEN_DWG2DXF``): se invoca como ``<exe> <entrada> <salida>``.
  Si necesita argumentos propios, envuélvalo en un .bat/.sh.

El módulo NUNCA lanza: ``prepare()`` devuelve un informe con ``errors``
y ``notes`` como el resto de los importadores del proyecto.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

# -- versiones DWG ----------------------------------------------------------
# código (6 primeros bytes del fichero) -> (etiqueta, año, familia)
DWG_VERSIONS: Dict[str, Tuple[str, int, str]] = {
    "MC0.0": ("DWG 1.0", 1982, "pre-r13"),
    "MC1.0": ("DWG 1.01", 1983, "pre-r13"),
    "MC1.50": ("DWG 1.50", 1984, "pre-r13"),
    "AC1.50": ("AutoCAD R2.0", 1984, "pre-r13"),
    "AC2.10": ("AutoCAD R2.1", 1985, "pre-r13"),
    "AC1002": ("AutoCAD R2.5", 1986, "pre-r13"),
    "AC1003": ("AutoCAD R2.6", 1987, "pre-r13"),
    "AC1004": ("AutoCAD R9", 1988, "pre-r13"),
    "AC1006": ("AutoCAD R10", 1988, "pre-r13"),
    "AC1009": ("AutoCAD R11/R12", 1990, "pre-r13"),
    "AC1012": ("AutoCAD R13", 1994, "r13_14"),
    "AC1014": ("AutoCAD R14", 1997, "r13_14"),
    "AC1015": ("AutoCAD 2000", 1999, "r2000"),
    "AC1018": ("AutoCAD 2004", 2003, "r2000"),
    "AC1021": ("AutoCAD 2007", 2006, "r2000"),
    "AC1024": ("AutoCAD 2010", 2009, "r2000"),
    "AC1027": ("AutoCAD 2013", 2012, "r2000"),
    "AC1032": ("AutoCAD 2018", 2017, "r2000"),
}

_INSTRUCTIONS = (
    "ARQ GEN no lee el binario DWG directamente: necesita un conversor "
    "local a DXF (todo queda en su equipo, sin red). Opciones gratuitas: "
    "1) ODA File Converter (Open Design Alliance), "
    "2) LibreDWG 'dwg2dxf', "
    "3) cualquier conversor propio declarándolo en la variable de "
    "entorno ARQGEN_DWG2DXF (se invoca <exe> <entrada> <salida>)."
)


def read_version(path: str) -> Dict[str, Any]:
    """Lee la cabecera de versión de un DWG (6 primeros bytes).

    Nunca lanza; ante cualquier problema devuelve ``ok=False`` con la
    razón en ``error``. Para códigos ``AC*`` no tabulados marca ok con
    etiqueta desconocida (podría ser una versión futura legible por el
    conversor de todos modos).
    """
    info: Dict[str, Any] = {"ok": False, "code": "", "label": "",
                            "year": 0, "family": "", "error": ""}
    try:
        with open(path, "rb") as handle:
            head = handle.read(6)
    except OSError as exc:
        info["error"] = f"No se pudo leer el fichero: {exc}"
        return info
    if len(head) < 6:
        info["error"] = "Fichero demasiado corto para ser un DWG"
        return info
    try:
        code = head.decode("ascii", errors="replace")
    except Exception as exc:  # pragma: no cover — decode con replace no lanza
        info["error"] = f"Cabecera ilegible: {exc}"
        return info
    info["code"] = code
    if code in DWG_VERSIONS:
        label, year, family = DWG_VERSIONS[code]
        info.update(ok=True, label=label, year=year, family=family)
        return info
    if code.startswith("AC") or code.startswith("MC"):
        info.update(ok=True, label=f"(versión no tabulada: {code})",
                    year=0, family="desconocida")
        return info
    info["error"] = (f"No parece un DWG: cabecera {code!r} no coincide "
                     "con ningún formato conocido")
    return info


# -- descubrimiento de conversores -------------------------------------------
def _oda_windows_candidates() -> List[str]:
    found: List[str] = []
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base = os.environ.get(var)
        if not base:
            continue
        pattern = os.path.join(base, "ODA", "ODAFileConverter*",
                               "ODAFileConverter.exe")
        found.extend(sorted(glob.glob(pattern), reverse=True))
    return found


def _mac_oda_candidates() -> List[str]:
    return ["/Applications/ODAFileConverter.app/Contents/MacOS/"
            "ODAFileConverter"]


def find_converters(preferred: str = "") -> List[Dict[str, Any]]:
    """Devuelve conversores DWG→DXF detectados en el equipo, en orden de
    prioridad. Nunca lanza.

    ``preferred`` (GUI/CLI) tiene prioridad absoluta: si se indica y
    existe, SOLO se devuelve ese; si se indica y no existe, la lista
    queda vacía (el informe explicará el problema).
    """
    converters: List[Dict[str, Any]] = []

    def add(kind: str, name: str, exe: str) -> None:
        if exe and os.path.isfile(exe):
            converters.append({"kind": kind, "name": name, "path": exe})

    preferred = (preferred or "").strip()
    if preferred:
        add("custom", "Convertidor indicado por el usuario", preferred)
        return converters

    env_exe = (os.environ.get("ARQGEN_DWG2DXF") or "").strip()
    if env_exe:
        add("custom", "Convertidor de ARQGEN_DWG2DXF", env_exe)
    which_dwg = shutil.which("dwg2dxf")
    if which_dwg:
        add("libredwg", "LibreDWG dwg2dxf", which_dwg)
    which_oda = shutil.which("ODAFileConverter")
    if which_oda:
        add("oda", "ODA File Converter", which_oda)
    if os.name == "nt":
        for exe in _oda_windows_candidates():
            add("oda", "ODA File Converter", exe)
    elif os.name == "posix":
        for exe in _mac_oda_candidates():
            add("oda", "ODA File Converter", exe)
    # dedupe por (kind, path) preservando el orden
    seen = set()
    unique = []
    for conv in converters:
        key = (conv["kind"], conv["path"])
        if key not in seen:
            seen.add(key)
            unique.append(conv)
    return unique


def build_command(conv: Dict[str, Any], src: str, out_dir: str
                  ) -> Tuple[List[str], str]:
    """Construye la línea de comando del conversor (función pura).

    Devuelve ``(args, salida_esperada)``. Se prueba cada conversor con
    ``subprocess`` SIN shell y con lista de argumentos (sin comillas ni
    expansión: robusto con espacios en Windows).
    """
    base = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(out_dir, base + ".dxf")
    exe = conv["path"]
    if conv["kind"] == "libredwg":
        # dwg2dxf -o <salida.dxf> <entrada.dwg>
        return [exe, "-o", out, src], out
    if conv["kind"] == "oda":
        # ODAFileConverter <dir_in> <dir_out> <versión> <tipo> <recursivo> <auditoría>
        return ([exe, os.path.dirname(os.path.abspath(src)), out_dir,
                 "ACAD2018", "DXF", "0", "1"], out)
    # custom: <exe> <entrada> <salida>
    return [exe, src, out], out


def _looks_like_dxf(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    if head.startswith(b"AutoCAD Binary DXF"):
        return True
    stripped = head.lstrip()
    return bool(stripped) and stripped[:1].isdigit()


# -- pasarela ----------------------------------------------------------------
class DwgGateway:
    """PREVIEW-stage del flujo DWG: convierte a DXF con un conversor
    local y entrega el resultado al motor §94 (DxfImporter)."""

    def __init__(self, timeout_s: float = 120.0) -> None:
        self.timeout_s = timeout_s
        self.report: Dict[str, Any] = {}

    def prepare(self, path: str, converter: str = "",
                out_dir: Optional[str] = None) -> Dict[str, Any]:
        """Convierte ``path`` (.dwg) a un DXF temporal. NUNCA lanza.

        Devuelve un informe con ``ok``, ``dxf_path``, ``version``,
        ``converter``, ``command``, ``errors`` y ``notes``. El DXF
        resultante vive en ``out_dir`` (por defecto un directorio
        temporal nuevo, devuelto como ``out_dir`` para que el llamador
        decida su limpieza).
        """
        report: Dict[str, Any] = {
            "file": path, "ok": False, "dxf_path": "", "out_dir": "",
            "version": {"ok": False, "code": "", "label": "", "year": 0,
                        "family": "", "error": ""},
            "converter": "", "command": [], "errors": [], "notes": [],
        }
        if not path or not os.path.isfile(path):
            report["errors"].append(f"Archivo DWG inexistente: {path}")
            self.report = report
            return report
        if os.path.splitext(path)[1].lower() != ".dwg":
            report["errors"].append(
                "Se esperaba un fichero .dwg; para DXF use el importador "
                "DXF directamente.")
            self.report = report
            return report

        version = read_version(path)
        report["version"] = version
        if not version["ok"]:
            report["errors"].append(version["error"] or
                                    "Cabecera DWG ilegible")
            self.report = report
            return report
        if version["family"] == "pre-r13":
            report["notes"].append(
                "DWG anterior a R13: formato antiguo; si el conversor "
                "falla, guarde el plano como DXF desde AutoCAD.")

        if out_dir is None:
            out_dir = tempfile.mkdtemp(prefix="arqgen_dwg_")
        os.makedirs(out_dir, exist_ok=True)
        report["out_dir"] = out_dir

        candidates = find_converters(converter)
        if not candidates:
            if converter and converter.strip():
                report["errors"].append(
                    f"El convertidor indicado no existe: {converter}")
            else:
                report["errors"].append(_INSTRUCTIONS)
            self.report = report
            return report

        last_error = ""
        for conv in candidates:
            args, expected = build_command(conv, path, out_dir)
            report["command"] = args
            report["converter"] = conv["name"]
            produced: List[str] = []
            try:
                proc = subprocess.run(
                    args, timeout=self.timeout_s, capture_output=True)
                if proc.returncode != 0:
                    tail = (proc.stderr or proc.stdout or b"")[-200:]
                    last_error = (
                        f"{conv['name']} terminó con código "
                        f"{proc.returncode}: "
                        f"{tail.decode('utf-8', errors='replace').strip()}")
                    continue
                if os.path.isfile(expected):
                    produced = [expected]
                else:
                    produced = sorted(
                        glob.glob(os.path.join(out_dir, "*.dxf")))
            except subprocess.TimeoutExpired:
                last_error = (f"{conv['name']} tardó más de "
                              f"{self.timeout_s:g} s: conversión cancelada.")
                continue
            except OSError as exc:
                last_error = f"No se pudo ejecutar {conv['name']}: {exc}"
                continue

            if not produced:
                last_error = (f"{conv['name']} terminó bien pero no "
                              f"produjo ningún DXF en {out_dir}")
                continue
            dxf_path = produced[0]
            try:
                size = os.path.getsize(dxf_path)
            except OSError as exc:
                last_error = f"DXF resultante ilegible: {exc}"
                continue
            if size <= 0:
                last_error = "El conversor produjo un DXF vacío"
                continue
            if not _looks_like_dxf(dxf_path):
                report["notes"].append(
                    "El resultado no parece DXF textual/binario estándar; "
                    "el importador §94 avisará si no puede leerlo.")
            report.update(ok=True, dxf_path=dxf_path)
            if proc.returncode == 0 and conv["kind"] == "oda":
                report["notes"].append(
                    "ODA File Converter procesa la carpeta completa; se "
                    "toma el primer DXF producido.")
            self.report = report
            return report

        report["errors"].append(
            last_error or "Ningún conversor pudo convertir el DWG.")
        report["errors"].append(_INSTRUCTIONS)
        self.report = report
        return report


__all__ = ["DWG_VERSIONS", "read_version", "find_converters",
           "build_command", "DwgGateway"]
