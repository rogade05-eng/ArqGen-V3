#!/usr/bin/env python3
"""Compila y verifica el bundle PyInstaller de ARQ GEN (multiplataforma).

Complemento multiplataforma de 03_COMPILAR.bat (Windows): usa el mismo
ARQ_GEN.spec (datas, hiddenimports y exclusiones Qt del bat) y añade la
verificación post-compilación de recursos dentro del bundle.

Uso:
    python compilar_bundle.py                   # compila + verifica
    python compilar_bundle.py --full            # además 'precons certificar'
    python compilar_bundle.py --verify-only     # solo verifica dist/
    python compilar_bundle.py --verify-only DIR # verifica otro dist/

Salida: informe con marcas OK/FAIL; código de salida 0 (correcto) o 1.
Requiere: pip install -r requirements-build.txt (pyinstaller>=6.10).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIST = os.path.join(PROJECT_ROOT, "dist")

# (ruta relativa dentro de resources/, tamaño mínimo en bytes)
REQUIRED_RESOURCES = (
    ("rulesets/precons_iii_rospres_330.json", 1_000_000),
    ("rulesets/precons_cuba_v1.json", 100),
    ("rulesets/international_v1.json", 100),
    ("branding/logo.ico", 100),
    ("branding/logo.png", 100),
    ("knowledge/neufert_standards.json", 100),
    ("knowledge/space_dna.json", 100),
    ("knowledge/hospital_specs.json", 100_000),
    ("knowledge/vivienda_catalogo.json", 25_000),
    ("knowledge/comercial_specs.json", 25_000),
    ("knowledge/educacion_specs.json", 25_000),
    ("budget_templates/residential_v1.json", 100),
)


def binary_name() -> str:
    return "ARQ_GEN.exe" if os.name == "nt" else "ARQ_GEN"


def default_runner(args, timeout: float = 1800.0):
    """Ejecuta un comando del bundle y devuelve returncode/stdout/stderr."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, returncode=124,
                                           stdout="", stderr="timeout")
    return proc


def verificar_bundle(dist_dir: str, runner=None, full: bool = False
                     ) -> tuple:
    """Verifica el bundle compilado; devuelve ``(ok, [(marca, texto)])``.

    ``runner`` es inyectable para pruebas: firma ``runner(args_list)``
    devolviendo un objeto con ``returncode``/``stdout``/``stderr``.
    """
    checks = []
    state = {"ok": True}

    def note(good: bool, text: str) -> None:
        if not good:
            state["ok"] = False
        checks.append(("OK  " if good else "FAIL", text))

    app_dir = os.path.join(dist_dir, "ARQ_GEN")
    bin_path = os.path.join(app_dir, binary_name())
    if not os.path.isfile(bin_path):
        note(False, f"ejecutable presente: {bin_path}")
        return state["ok"], checks
    try:
        size_mb = os.path.getsize(bin_path) / (1024 * 1024)
    except OSError:
        size_mb = 0.0
    note(True, f"ejecutable presente: {bin_path} ({size_mb:.1f} MB)")

    internal = os.path.join(app_dir, "_internal")
    if not os.path.isdir(internal):  # PyInstaller < 6: sin _internal
        internal = app_dir
    for rel, min_size in REQUIRED_RESOURCES:
        path = os.path.join(internal, "resources",
                            rel.replace("/", os.sep))
        good = os.path.isfile(path) and os.path.getsize(path) >= min_size
        detail = ""
        if good:
            detail = f" ({os.path.getsize(path):,} bytes)"
        note(good, f"recurso {rel}{detail}")

    if runner is None:
        runner = default_runner
    proc = runner([bin_path, "selftest"])
    out = proc.stdout or ""
    note(proc.returncode == 0 and "RESULTADO: CORRECTO" in out,
         f"selftest del ejecutable (rc={proc.returncode})")
    if full:
        proc = runner([bin_path, "precons", "certificar"])
        out = proc.stdout or ""
        note(proc.returncode == 0 and "CERTIFICADO" in out,
             f"precons certificar del ejecutable (rc={proc.returncode})")
    return state["ok"], checks


def build() -> bool:
    """Compila con PyInstaller usando ARQ_GEN.spec; devuelve el éxito."""
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           os.path.join(PROJECT_ROOT, "ARQ_GEN.spec")]
    print("COMPILANDO:", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    except FileNotFoundError:
        print("ERROR: PyInstaller no está instalado. Ejecute:")
        print("  pip install -r requirements-build.txt")
        return False
    if proc.returncode != 0:
        print("ERROR: la compilación falló (ver el log de PyInstaller).")
        return False
    print("Compilación OK ->", os.path.join(DEFAULT_DIST, "ARQ_GEN"))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compila y verifica el bundle PyInstaller de ARQ GEN")
    parser.add_argument("--verify-only", action="store_true",
                        help="no compila: verifica un dist existente")
    parser.add_argument("--dist", default="",
                        help="directorio dist (por defecto ./dist)")
    parser.add_argument("--full", action="store_true",
                        help="verificación completa (incluye 'precons "
                             "certificar' del ejecutable)")
    args = parser.parse_args()

    dist_dir = os.path.abspath(args.dist) if args.dist else DEFAULT_DIST
    if not args.verify_only:
        if not build():
            return 1
    ok, checks = verificar_bundle(dist_dir, full=args.full)
    print("=" * 56)
    print("ARQ GEN — VERIFICACIÓN DEL BUNDLE PYINSTALLER")
    print("=" * 56)
    for marker, text in checks:
        print(f"[{marker}] {text}")
    print("=" * 56)
    print("RESULTADO:", "CORRECTO" if ok else "CON FALLOS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
