"""JSON exporter/importer: full project round-trip (spec 64, 94)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from core.errors import ExportError, ImportErrorARQ
from services.commands_impl import entity_snapshot
from services.context import ProjectContext

ENTITY_ORDER = ("SITE", "BUILDING", "LEVEL", "ZONE", "SPACE", "WALL",
                "DOOR", "WINDOW", "OPENING", "SPACE_RELATIONSHIP",
                "FURNITURE", "ROOF", "RAMP", "HANDRAIL", "ELEVATOR",
                "PARASOL", "SKIN", "STAIR")


class JSONExporter:
    """Builds the canonical snapshot of the project (also used by versioning)."""

    @staticmethod
    def build_snapshot(context: ProjectContext) -> Dict[str, Any]:
        project = context.project
        entities: Dict[str, List[Dict[str, Any]]] = {}
        for entity_type in ENTITY_ORDER:
            rows = [entity_snapshot(e) for e in context.architecture.list(entity_type, project.id)]
            entities[entity_type] = rows
        return {
            "format": "ARQ_GEN_SNAPSHOT",
            "version": "1.0",
            "project": {
                "id": project.id, "name": project.name, "client": project.client,
                "address": project.address, "description": project.description,
                "units_length": project.units_length, "ruleset_code": project.ruleset_code,
                "currency": project.currency,
            },
            "entities": entities,
            "quantities": context.quantities_repo.all(project.id),
        }

    def export(self, context: ProjectContext, out_path: str) -> str:
        snapshot = self.build_snapshot(context)
        directory = os.path.dirname(os.path.abspath(out_path))
        os.makedirs(directory, exist_ok=True)
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False, indent=2, sort_keys=True)
        except OSError as exc:
            raise ExportError(
                message=f"No se pudo escribir el JSON: {exc}",
                code="ARQ-EXP-020",
                context={"path": out_path},
            ) from exc
        return out_path


class JSONImporter:
    """Import pipeline (spec section 94):
    DETECT → PARSE → VALIDATE → MAP → CONVERT → PREVIEW → APPROVE → IMPORT → AUDIT.
    """

    def __init__(self) -> None:
        self.report: Dict[str, Any] = {}

    def detect(self, in_path: str) -> Dict[str, Any]:
        if not os.path.exists(in_path):
            raise ImportErrorARQ(
                message=f"Archivo de importación inexistente: {in_path}",
                code="ARQ-IMP-020",
            )
        try:
            with open(in_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ImportErrorARQ(
                message=f"JSON ilegible: {exc}", code="ARQ-IMP-021",
                context={"path": in_path}) from exc
        if data.get("format") != "ARQ_GEN_SNAPSHOT":
            raise ImportErrorARQ(
                message="El archivo no es una instantánea ARQ GEN (format inválido)",
                code="ARQ-IMP-022",
                suggested_action="Exporte el proyecto con 'export --format json'.")
        return data

    def preview(self, in_path: str) -> Dict[str, Any]:
        """DETECT + PARSE + VALIDATE + MAP → preview report (no changes)."""
        data = self.detect(in_path)
        errors: List[str] = []
        counts: Dict[str, int] = {}
        for entity_type in ENTITY_ORDER:
            rows = data.get("entities", {}).get(entity_type, [])
            counts[entity_type] = len(rows)
            for row in rows:
                if not row.get("id"):
                    errors.append(f"{entity_type}: entidad sin id")
        self.report = {
            "project": data.get("project", {}).get("name", ""),
            "counts": counts,
            "errors": errors,
            "quantities": len(data.get("quantities", [])),
        }
        return self.report

    def load(self, in_path: str) -> Dict[str, Any]:
        """Validated data ready for the import stage (used by ImportService)."""
        report = self.preview(in_path)
        if report["errors"]:
            raise ImportErrorARQ(
                message=f"La importación tiene errores de validación: {report['errors'][:3]}",
                code="ARQ-IMP-023",
            )
        return self.detect(in_path)


__all__ = ["JSONExporter", "JSONImporter", "ENTITY_ORDER"]
