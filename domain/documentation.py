"""Documentation domain (spec sections 68, 69, 70, 106).

FASE 34 - DOCUMENTATION. Two entities:

    Drawing       one sheet of the drawing set (spec 69): sheet code, scale,
                  orientation, view, layers, annotations, titleblock.
    DocTemplate   a parametric document template (spec 70): variables,
                  sections, tables, styles, headers, footers. Text uses
                  ``{{PROJECT.NAME}}`` style placeholders resolved by the
                  documentation engine.

Drawing elements (Dimension, Text, Leader, Symbol, Hatch, Block, Viewport)
are stored as annotation records inside the Drawing; each record is a dict
with a ``kind`` validated against DRAWING_ELEMENTS.

The module never computes geometry: it stores documentation intent and the
documentation engine/service turn project data into rendered documents
(memoria, especificaciones, cuadros, listados, informes - spec 68/106).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.entities.base import Entity, utc_now
from core.errors import DomainError

# Spec 69: drawing element kinds stored as annotations.
DRAWING_ELEMENTS: tuple[str, ...] = (
    "DIMENSION", "TEXT", "LEADER", "SYMBOL", "HATCH", "BLOCK", "VIEWPORT",
)

# Sheet catalog (mm). (width, height) portrait; landscape swaps them.
SHEET_SIZES: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
}

ORIENTATIONS: tuple[str, ...] = ("PORTRAIT", "LANDSCAPE")

# Normalized scales accepted on a sheet (1 : value).
SCALES: tuple[int, ...] = (1, 2, 5, 10, 20, 25, 50, 75, 100, 200, 250, 500, 1000)

VIEWS: tuple[str, ...] = (
    "PLAN", "SECTION", "ELEVATION", "DETAIL", "SCHEMATIC", "LAYOUT", "SITE",
)

# Spec 70: template building blocks.
TEMPLATE_BLOCKS: tuple[str, ...] = (
    "variables", "sections", "tables", "images", "drawings", "styles",
    "headers", "footers",
)

# Document kinds the system generates (spec 68).
DOCUMENT_KINDS: tuple[str, ...] = (
    "MEMORIA",           # memoria descriptiva
    "TECNICA",           # memoria técnica
    "SPECS",             # especificaciones
    "CUADROS",           # cuadros (áreas, vanos...)
    "LISTADOS",          # listados de elementos
    "INFORME",           # informe de validación/interferencias
    "MODULE",            # documentación automática de un módulo (spec 106)
    "TEMPLATE",          # documento renderizado desde una plantilla
)


def parse_scale(scale: str) -> int:
    """Parse "1:50" into the denominator 50 (deterministic, no eval)."""
    text = (scale or "").strip().upper()
    if not text.startswith("1:"):
        raise DomainError(
            message=f"Escala no válida: {scale!r}",
            code="ARQ-DOC-001",
            context={"scale": scale, "allowed": [f"1:{s}" for s in SCALES]},
            suggested_action="Use una escala normalizada, por ejemplo 1:50.")
    try:
        denominator = int(text.split(":", 1)[1])
    except ValueError as exc:
        raise DomainError(
            message=f"Escala no numérica: {scale!r}", code="ARQ-DOC-001") from exc
    if denominator not in SCALES:
        raise DomainError(
            message=f"Escala fuera del catálogo: {scale!r}",
            code="ARQ-DOC-001",
            context={"allowed": [f"1:{s}" for s in SCALES]})
    return denominator


@dataclass
class Drawing(Entity):
    """One sheet of the drawing set (spec 69)."""

    ENTITY_TYPE = "DRAWING"
    sheet: str = "A-01"
    sheet_size: str = "A3"
    scale: str = "1:50"
    orientation: str = "LANDSCAPE"
    view: str = "PLAN"
    level_id: Optional[str] = None
    layers: List[str] = field(default_factory=list)
    annotations: List[Dict[str, Any]] = field(default_factory=list)
    titleblock: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.sheet_size not in SHEET_SIZES:
            raise DomainError(
                message=f"Formato de hoja desconocido: {self.sheet_size}",
                code="ARQ-DOC-002",
                context={"allowed": sorted(SHEET_SIZES)})
        self.scale_denominator = parse_scale(self.scale)
        if self.orientation not in ORIENTATIONS:
            raise DomainError(
                message=f"Orientación desconocida: {self.orientation}",
                code="ARQ-DOC-003",
                context={"allowed": list(ORIENTATIONS)})
        if self.view not in VIEWS:
            raise DomainError(
                message=f"Tipo de vista desconocido: {self.view}",
                code="ARQ-DOC-004",
                context={"allowed": list(VIEWS)})

    def add_element(self, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Attach one documentation element (Dimension/Text/... spec 69)."""
        if kind not in DRAWING_ELEMENTS:
            raise DomainError(
                message=f"Elemento de plano desconocido: {kind}",
                code="ARQ-DOC-005",
                context={"allowed": list(DRAWING_ELEMENTS)})
        record = {"kind": kind, **payload}
        self.annotations.append(record)
        self.touch()
        return record

    def paper_size(self) -> tuple[float, float]:
        """Paper (width, height) in mm honoring the orientation."""
        width, height = SHEET_SIZES[self.sheet_size]
        if self.orientation == "LANDSCAPE":
            return (height, width)
        return (width, height)

    def real_length_mm(self, drawing_mm: float) -> float:
        """Convert a measured length on paper to real length (mm)."""
        return drawing_mm * self.scale_denominator

    def drawing_length_mm(self, real_mm: float) -> float:
        """Convert a real length (mm) to the length drawn on paper."""
        return real_mm / self.scale_denominator


@dataclass
class DocTemplate(Entity):
    """Parametric document template (spec 70)."""

    ENTITY_TYPE = "DOC_TEMPLATE"
    name: str = ""
    body: str = ""
    variables: Dict[str, str] = field(default_factory=dict)
    sections: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)
    styles: Dict[str, str] = field(default_factory=dict)
    headers: str = ""
    footers: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.name:
            raise DomainError(
                message="La plantilla exige un nombre", code="ARQ-DOC-006")

    def placeholder_names(self) -> List[str]:
        """All ``{{VAR}}`` names referenced by body/headers/footers."""
        import re

        text = "\n".join([self.body, self.headers, self.footers])
        return sorted(set(re.findall(r"\{\{([A-Z0-9_.]+)\}\}", text)))


__all__ = [
    "Drawing", "DocTemplate", "DRAWING_ELEMENTS", "SHEET_SIZES",
    "ORIENTATIONS", "SCALES", "VIEWS", "TEMPLATE_BLOCKS", "DOCUMENT_KINDS",
    "parse_scale",
]
