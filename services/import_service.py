"""ImportService: APPROVE → IMPORT → AUDIT stages of the pipeline (spec 94)."""

from __future__ import annotations

from typing import Any, Dict

from core.errors import ImportErrorARQ
from domain.model import Project
from exporters.json_io import JSONImporter
from services.commands_impl import snapshot_to_entity
from services.context import ApplicationContext, ProjectContext


class ImportService:
    """Creates a NEW project file from a validated ARQ GEN snapshot."""

    def __init__(self, application: ApplicationContext) -> None:
        self.application = application
        self.importer = JSONImporter()

    def preview(self, in_path: str) -> Dict[str, Any]:
        return self.importer.preview(in_path)

    def import_snapshot(self, in_path: str, out_db_path: str, approve: bool,
                        user: str = "local") -> Dict[str, Any]:
        data = self.importer.load(in_path)
        if not approve:
            return {"approved": False, "preview": self.importer.report}

        context: ProjectContext = self.application.create_project(
            out_db_path, name=data.get("project", {}).get("name", "importado"),
            client=data.get("project", {}).get("client", ""),
            address=data.get("project", {}).get("address", ""),
            description=data.get("project", {}).get("description", ""),
            ruleset_code=data.get("project", {}).get("ruleset_code", ""),
            currency=data.get("project", {}).get("currency", "CUP"))
        try:
            from persistence.repositories.architecture_repo import ProjectRepository

            # Replace the auto-created project row with the original identity so
            # every imported entity keeps its original project_id.
            project_data = data.get("project", {})
            ProjectRepository(context.session).delete(context.project.id)
            restored_project = Project(
                id=project_data.get("id", context.project.id),
                name=project_data.get("name", context.project.name),
                client=project_data.get("client", ""),
                address=project_data.get("address", ""),
                description=project_data.get("description", ""),
                units_length=project_data.get("units_length", "m"),
                ruleset_code=project_data.get("ruleset_code", ""),
                currency=project_data.get("currency", "CUP"))
            ProjectRepository(context.session).save(restored_project)
            context.project = restored_project

            order = ("SITE", "BUILDING", "LEVEL", "ZONE", "SPACE", "WALL",
                     "DOOR", "WINDOW", "OPENING", "SPACE_RELATIONSHIP")
            inserted = {}
            for entity_type in order:
                count = 0
                for snapshot in data.get("entities", {}).get(entity_type, []):
                    context.architecture.save(snapshot_to_entity(snapshot))
                    count += 1
                inserted[entity_type] = count
            context.commit()
            context.emit("DOCUMENT_CHANGED", {"action": "IMPORTED", "path": out_db_path})
            from core.audit.models import make_audit_event
            context.audit_repo.append(make_audit_event(
                user=user, object_id=context.project.id, object_type="PROJECT",
                command="IMPORT_JSON", old_value=None,
                new_value={"source": in_path}, reason="import", result="OK"))
            return {"approved": True, "inserted": inserted, "path": out_db_path}
        except Exception:
            context.rollback()
            raise
        finally:
            context.close()


__all__ = ["ImportService"]
