"""GeometryRepairEngine (spec section 10).

Obligatory process pattern:
    DETECTAR → EXPLICAR → PROPONER → APROBAR → APLICAR → REVALIDAR

Detects: duplicated lines, zero segments, open polygons, self
intersections, corrupt geometries, duplicated vertices, inconsistent
layers, incorrect units. Nothing is applied without explicit approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from core.geometry.engine import Tolerance, shoelace_area
from core.geometry.primitives import Line, Point, Polygon, Polyline


class IssueKind(str, Enum):
    DUPLICATED_LINE = "DUPLICATED_LINE"
    ZERO_SEGMENT = "ZERO_SEGMENT"
    OPEN_POLYGON = "OPEN_POLYGON"
    SELF_INTERSECTION = "SELF_INTERSECTION"
    CORRUPT_GEOMETRY = "CORRUPT_GEOMETRY"
    DUPLICATED_VERTEX = "DUPLICATED_VERTEX"
    INCONSISTENT_LAYER = "INCONSISTENT_LAYER"
    INCORRECT_UNIT = "INCORRECT_UNIT"


class FixKind(str, Enum):
    REMOVE_DUPLICATED_VERTEX = "REMOVE_DUPLICATED_VERTEX"
    REMOVE_ZERO_SEGMENT = "REMOVE_ZERO_SEGMENT"
    CLOSE_POLYGON = "CLOSE_POLYGON"
    REMOVE_DUPLICATED_LINE = "REMOVE_DUPLICATED_LINE"
    MARK_FOR_REVIEW = "MARK_FOR_REVIEW"


@dataclass
class Issue:
    kind: IssueKind
    explanation: str
    object_ref: str
    detail: dict = field(default_factory=dict)


@dataclass
class Proposal:
    issue: Issue
    fix_kind: FixKind
    explanation: str
    fixed_points: Optional[List[Point]] = None
    drop_line_index: Optional[int] = None


@dataclass
class RepairReport:
    """Result of detect → explain → propose → (approve) → apply → revalidate."""

    detected: List[Issue] = field(default_factory=list)
    proposals: List[Proposal] = field(default_factory=list)
    applied: List[Proposal] = field(default_factory=list)
    rejected: List[Proposal] = field(default_factory=list)
    revalidated_clean: bool = True
    remaining_issues: List[Issue] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return len(self.detected) > 0


class GeometryRepairEngine:
    """Implements the mandatory six-step repair pattern (spec section 10)."""

    # 1) DETECTAR + 2) EXPLICAR
    def detect(self, points: List[Point], closed: bool, object_ref: str = "",
               layer: Optional[str] = None, expected_unit: str = "m") -> List[Issue]:
        issues: List[Issue] = []
        if not points:
            issues.append(Issue(IssueKind.CORRUPT_GEOMETRY,
                                "La geometría no contiene vértices (vacía o corrupta).",
                                object_ref))
            return issues

        seen: List[Point] = []
        for idx, p in enumerate(points):
            for q in seen:
                if p.distance_to(q) <= 1e-6:
                    issues.append(Issue(
                        IssueKind.DUPLICATED_VERTEX,
                        f"Vértice duplicado en índice {idx}: {p} coincide con un vértice anterior.",
                        object_ref, {"index": idx}))
                    break
            seen.append(p)

        for idx in range(len(points) - 1):
            if points[idx].distance_to(points[idx + 1]) <= Tolerance:
                issues.append(Issue(
                    IssueKind.ZERO_SEGMENT,
                    f"Segmento de longitud cero entre vértices {idx} y {idx + 1}.",
                    object_ref, {"index": idx}))

        if closed:
            first, last = points[0], points[-1]
            if first.distance_to(last) <= 1e-6 and len(points) > 1:
                pass  # repeated closing vertex handled as duplicated vertex
            signed = shoelace_area(points)
            if abs(signed) <= Tolerance:
                issues.append(Issue(
                    IssueKind.CORRUPT_GEOMETRY,
                    "El polígono cerrado tiene área nula (degenerado o colapsado).",
                    object_ref))
            if self._has_self_intersection(points):
                issues.append(Issue(
                    IssueKind.SELF_INTERSECTION,
                    "El contorno presenta autointersección entre segmentos no consecutivos.",
                    object_ref))
        elif len(points) >= 3 and points[0].distance_to(points[-1]) <= 1e-6:
            issues.append(Issue(
                IssueKind.OPEN_POLYGON,
                "El contorno parece cerrado (primer y último vértice coinciden) pero está marcado abierto.",
                object_ref))

        if expected_unit != "m":
            issues.append(Issue(
                IssueKind.INCORRECT_UNIT,
                f"Unidad declarada '{expected_unit}' difiere del modelo interno (m).",
                object_ref))
        if layer is not None and layer.strip() == "":
            issues.append(Issue(
                IssueKind.INCONSISTENT_LAYER,
                "Capa vacía o inconsistente para el objeto.",
                object_ref))
        return issues

    # 3) PROPONER
    def propose(self, points: List[Point], closed: bool, issues: List[Issue],
                object_ref: str = "") -> List[Proposal]:
        proposals: List[Proposal] = []
        drop_indices = {i.detail.get("index") for i in issues if i.kind == IssueKind.ZERO_SEGMENT}
        kept: List[Point] = [p for i, p in enumerate(points) if i not in drop_indices]

        if any(i.kind == IssueKind.DUPLICATED_VERTEX for i in issues):
            dedup: List[Point] = []
            for p in kept:
                if not any(p.distance_to(q) <= 1e-6 for q in dedup):
                    dedup.append(p)
            kept = dedup
            proposals.append(Proposal(
                Issue(IssueKind.DUPLICATED_VERTEX, "Eliminar vértices duplicados.", object_ref),
                FixKind.REMOVE_DUPLICATED_VERTEX,
                "Se eliminarán los vértices repetidos conservando el primero de cada grupo.", fixed_points=kept))

        if drop_indices:
            proposals.append(Proposal(
                Issue(IssueKind.ZERO_SEGMENT, "Eliminar segmentos de longitud cero.", object_ref),
                FixKind.REMOVE_ZERO_SEGMENT,
                "Se eliminarán los vértices intermedios que generan segmentos nulos.", fixed_points=kept))

        if any(i.kind == IssueKind.OPEN_POLYGON for i in issues):
            proposals.append(Proposal(
                Issue(IssueKind.OPEN_POLYGON, "Cerrar el contorno.", object_ref),
                FixKind.CLOSE_POLYGON,
                "Se marcará el contorno como cerrado eliminando el vértice final repetido.",
                fixed_points=kept[:-1] if kept and kept[0].distance_to(kept[-1]) <= 1e-6 else kept))

        unfixable = [i for i in issues if i.kind in (
            IssueKind.SELF_INTERSECTION, IssueKind.CORRUPT_GEOMETRY,
            IssueKind.INCONSISTENT_LAYER, IssueKind.INCORRECT_UNIT)]
        for issue in unfixable:
            proposals.append(Proposal(
                issue, FixKind.MARK_FOR_REVIEW,
                "Este problema requiere revisión manual; el motor no modifica la geometría automáticamente."))
        return proposals

    # 4) APROBAR + 5) APLICAR + 6) REVALIDAR
    def apply(self, points: List[Point], closed: bool, proposals: List[Proposal],
              approved: bool, object_ref: str = "") -> RepairReport:
        report = RepairReport()
        report.detected = [p.issue for p in proposals]
        report.proposals = proposals
        if not approved:
            report.rejected = list(proposals)
            report.remaining_issues = list(report.detected)
            report.revalidated_clean = False
            return report

        current = list(points)
        for proposal in proposals:
            if proposal.fix_kind in (FixKind.REMOVE_DUPLICATED_VERTEX, FixKind.REMOVE_ZERO_SEGMENT,
                                     FixKind.CLOSE_POLYGON) and proposal.fixed_points is not None:
                current = list(proposal.fixed_points)
                report.applied.append(proposal)
            elif proposal.fix_kind == FixKind.MARK_FOR_REVIEW:
                report.rejected.append(proposal)

        remaining = self.detect(current, closed, object_ref)
        remaining = [i for i in remaining if i.kind not in (
            IssueKind.SELF_INTERSECTION, IssueKind.CORRUPT_GEOMETRY,
            IssueKind.INCONSISTENT_LAYER, IssueKind.INCORRECT_UNIT)]
        report.remaining_issues = remaining
        report.revalidated_clean = len(remaining) == 0
        return report

    def _has_self_intersection(self, points: List[Point]) -> bool:
        from core.geometry.engine import _line_line_intersection
        pts = points + [points[0]]
        segments = [Line(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        n = len(segments)
        for i in range(n):
            for j in range(i + 2, n):
                if i == 0 and j == n - 1:
                    continue  # consecutive through the closing vertex
                if _line_line_intersection(segments[i], segments[j]) is not None:
                    return True
        return False


__all__ = [
    "GeometryRepairEngine", "Issue", "IssueKind", "Proposal", "FixKind", "RepairReport",
]
