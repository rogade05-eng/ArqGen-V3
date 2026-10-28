"""Acelerador opcional en Rust (FASE B, v3.49.0).

Puerto 1:1 de las funciones calientes de `domain/encaje.py` y generador
XLSX nativo, compilados con PyO3 en `rust/arqgen_core` (crate
`arqgen_core`). Si el módulo no está instalado, TODO el programa sigue
funcionando en modo Python puro: este puente es la única pieza que sabe
si el acelerador existe.

POLÍTICA DE ACTIVACIÓN (por diseño, no por descuido):
- El modo por defecto es PYTHON: el motor no cambia ni un resultado
  respecto a v3.48.0 y la suite determinista se mantiene blindada.
- El modo RUST es opt-in: variable de entorno ARQ_GEN_ACELERADOR=rust o
  parámetro explícito usar_rust=True en los puntos de entrada.
- La paridad Rust<->Python está vigilada por tests/test_190_fase_b_rust.py
  y por los checks 98-100 del selftest.

Dónde actúa cada pieza:
- geometría de encaje (contenedores/rectángulo inscrito): aquí
  `contenedores_de_rust()` replica el nivel alto de
  `domain.encaje.contenedores_de()`; `encaje.py` solo añade el switch.
- XLSX: `exporters/xlsx_exporter.py` consulta `disponible()` y
  `quiere_rust()` y delega en `arqgen_core.xlsx_escribir` (con fallback
  transparente a openpyxl ante cualquier fallo de escritura).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

try:  # el crate compilado con PyO3; ausente => modo python puro
    import arqgen_core as _rust
except ImportError:  # pragma: no cover - depende del entorno
    _rust = None

VAR_ENTORNO = "ARQ_GEN_ACELERADOR"


def disponible() -> bool:
    """True si el crate Rust está instalado e importable."""
    return _rust is not None


def modo() -> str:
    """«rust» o «python» (para selftest, resúmenes y diagnóstico)."""
    return "rust" if _rust is not None else "python"


def version_rust() -> str:
    """Versión del crate («3.49.0») o cadena vacía si no hay Rust."""
    if _rust is None:
        return ""
    try:
        return str(_rust.version())
    except Exception:  # pragma: no cover - defensa
        return ""


def quiere_rust(usar_rust: Optional[bool] = None) -> bool:
    """Decisión de activación: parámetro explícito gana; si es None manda
    la variable de entorno (valor «rust»). Con el crate ausente nunca
    activa (y los puntos de entrada caen al camino Python)."""
    if usar_rust is not None:
        return bool(usar_rust) and _rust is not None
    return _rust is not None and \
        os.environ.get(VAR_ENTORNO, "").strip().lower() == "rust"


# ---------------------------------------------------------------------------
# nivel alto de encaje con el núcleo Rust
# ---------------------------------------------------------------------------

PT = Tuple[float, float]


def contenedores_de_rust(poligono: List[PT], margen: float = 0.0,
                         min_lado: float = 1.0) -> Dict[str, Any]:
    """Réplica del nivel alto de `domain.encaje.contenedores_de()` con el
    núcleo Rust (estrategia, contenedores, áreas y avisos idénticos).
    Los dicts de contenedor los fabrica el crate con las mismas claves
    (x0, y0, x1, y1, ancho, fondo, area) y redondeo a 4 decimales."""
    if _rust is None:  # pragma: no cover - nunca llamado sin crate
        raise RuntimeError("contenedores_de_rust llamado sin arqgen_core")
    m = max(0.0, float(margen or 0.0))
    avisos: List[str] = []
    if _rust.es_ortogonal(poligono):
        xs = sorted({float(p[0]) for p in poligono})
        ys = sorted({float(p[1]) for p in poligono})
        es_rect = len(xs) == 2 and len(ys) == 2
        estrategia = "rectangulo" if es_rect else "descompuesto"
        bruta = _rust.contenedores_ortogonales(poligono, 0.0, min_lado)
        area_aprovechable = round(sum(c["area"] for c in bruta), 4)
        conts = _rust.contenedores_ortogonales(poligono, m, min_lado)
        if estrategia == "descompuesto" and area_aprovechable < \
                _rust.area_poligono(poligono) - 0.01:
            avisos.append(
                f"franjas menores de {min_lado:.2f} m descartadas "
                f"({round(_rust.area_poligono(poligono) - area_aprovechable, 2)} m2 "
                "sin uso posible: no admiten locales)")
    else:
        estrategia = "inscrito"
        r = _rust.rectangulo_inscrito(poligono, m)
        bruta = _rust.rectangulo_inscrito(poligono, 0.0)
        area_aprovechable = float(bruta["area"]) if bruta else 0.0
        conts = [r] if r else []
        if r:
            avisos.append(
                "el polígono tiene aristas inclinadas: los locales se "
                "colocan en el mayor rectángulo inscrito "
                f"({r['ancho']:.2f} x {r['fondo']:.2f} m); el resto de "
                "la parcela no admite locales ortogonales — para "
                "aprovecharla completa dibuje un contorno ortogonal")
        else:
            avisos.append("no se halló un rectángulo útil inscrito en "
                          "el polígono: reduzca el programa o dibuje "
                          "un contorno más regular")
    area_total = round(sum(c["area"] for c in conts), 4)
    return {"estrategia": estrategia,
            "contenedores": [dict(c) for c in conts],
            "area_contenedores": area_total,
            "area_aprovechable": area_aprovechable, "avisos": avisos}


__all__ = ["disponible", "modo", "version_rust", "quiere_rust",
           "contenedores_de_rust", "VAR_ENTORNO"]
