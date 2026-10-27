"""Consola a prueba de Windows (v3.13.1).

La consola de Windows hereda una página de códigos local (cp1252 y
familia) que NO sabe representar símbolos como la flecha «→»
(U+2192): un print inocente lanzaba UnicodeEncodeError y tumbaba el
selftest del ejecutable justo al imprimir el último check — 54 líneas
OK y el pipeline en rojo.

``consola_segura()`` reconfigura stdout/stderr con ``errors="replace"``:
los acentos siguen intactos (cp1252 los tiene) y cualquier carácter
que la página de códigos no entienda sale como «?» en lugar de matar
el proceso. Es idempotente y nunca falla: si el flujo no soporta
``reconfigure`` (o es None bajo pythonw), se ignora en silencio.

El mensaje canónico del selftest no depende de este blindaje: las
cadenas que se imprimen en consola se escriben con caracteres
codificables en cp1252 (las flechas van como «->»); el blindaje es la
segunda barrera para cualquier texto futuro que se le escape.
"""

from __future__ import annotations

import sys


def consola_segura() -> None:
    """stdout/stderr ya no revientan por caracteres no codificables."""
    for nombre in ("stdout", "stderr"):
        flujo = getattr(sys, nombre, None)
        if flujo is None:
            continue
        try:
            flujo.reconfigure(errors="replace")
        except Exception:  # noqa: BLE001 — la consola nunca puede tumbar
            pass
