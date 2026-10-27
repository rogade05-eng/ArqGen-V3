#!/usr/bin/env python3
"""ARQ GEN entry point (spec section 4: main.py).

Works both from source (python main.py ...) and frozen (PyInstaller).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is importable when launched from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    # Ejecutable compilado lanzado por doble clic: abre la interfaz
    # grafica (FASE 90) directamente en lugar de imprimir la ayuda de la
    # CLI y cerrarse. Los .bat y la automatizacion siempre pasan un
    # subcomando explicito, asi que no se ven afectados.
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        sys.argv.append("gui")
    from app.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
