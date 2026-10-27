# -*- mode: python ; coding: utf-8 -*-
"""ARQ GEN — spec de PyInstaller (onedir, consola, Tkinter).

Espejo EXACTO de la etapa 2 de 03_COMPILAR.bat (scripts v1.6.4):
- punto de entrada main.py, nombre ARQ_GEN, modo onedir
- --collect-submodules ui / plugins.builtin  ->  hiddenimports
- --add-data "resources;resources"           ->  datas
- exclusión de TODOS los bindings Qt (PySide6/shiboken/PyQt5/PyQt6):
  ezdxf importa ezdxf.addons.xqt de forma perezosa y PyInstaller aborta
  con "attempt to collect multiple Qt bindings packages" si el equipo
  tiene varios bindings instalados. ARQ GEN usa Tkinter, no Qt.

Única diferencia deliberada: upx=False (estabilidad frente a antivirus;
el bat mantiene el comportamiento por defecto de PyInstaller).

Camino multiplataforma (Linux/macOS/CI):
    python compilar_bundle.py               # compila + verifica
    python compilar_bundle.py --verify-only # solo verifica dist/
En Windows el camino oficial sigue siendo 03_COMPILAR.bat. Este spec
debe mantenerse en sincronía con el bat: lo vigila
tests/test_121_dwg_bundle.py (paridad de datas, excludes y submódulos).
"""
from __future__ import annotations

import os
import sys

try:
    SPEC_DIR = SPECPATH  # noqa: F821 — global inyectada por PyInstaller
except NameError:  # ejecución fuera de PyInstaller (lint/tests)
    SPEC_DIR = os.path.dirname(os.path.abspath(__file__))


def _tkinter_libs() -> list:
    """Librerías compartidas Tcl/Tk del propio intérprete.

    En Linux, los layouts de intérpretes gestionados (uv/conda) guardan
    libtcl*/libtk* fuera de las rutas que PyInstaller rastrea y el
    bundle falla con 'libtcl9tk9.0.so: cannot open shared object file'.
    Se recolectan a mano desde LIBDIR/base_prefix/lib; en Windows y
    macOS el glob no produce nada (dll/dylib) y queda en no-op.
    """
    import glob
    try:
        import sysconfig
        libdirs = [sysconfig.get_config_var("LIBDIR") or "",
                   os.path.join(sys.base_prefix, "lib")]
    except Exception:  # noqa: BLE001 — sysconfig ausente: improbable
        return []
    out = []
    seen = set()
    for libdir in libdirs:
        if not libdir or libdir in seen:
            continue
        seen.add(libdir)
        for pattern in ("libtcl*.so*", "libtk*.so*"):
            for path in sorted(glob.glob(os.path.join(libdir, pattern))):
                out.append((path, "."))
    return out


def _submodules(package: str) -> list:
    """Submódulos del paquete por recorrido de ficheros (sin imports)."""
    pkg_dir = os.path.join(SPEC_DIR, package.replace(".", os.sep))
    found = []
    for name in sorted(os.listdir(pkg_dir)):
        full = os.path.join(pkg_dir, name)
        if name.endswith(".py") and name != "__init__.py":
            found.append(package + "." + name[:-3])
        elif os.path.isdir(full) and os.path.isfile(
                os.path.join(full, "__init__.py")):
            found.append(package + "." + name)
    return found


QT_EXCLUDES = ["PySide6", "shiboken6", "PySide2", "shiboken2",
               "PyQt5", "PyQt6"]

a = Analysis(
    ["main.py"],
    pathex=[SPEC_DIR],
    binaries=_tkinter_libs(),
    datas=[("resources", "resources")],
    hiddenimports=_submodules("ui") + _submodules("plugins.builtin"),
    hookspath=[],
    runtime_hooks=[],
    excludes=QT_EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="ARQ_GEN",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=(os.path.join(SPEC_DIR, "resources", "branding", "logo.ico")
          if os.name == "nt" else None),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ARQ_GEN",
)
