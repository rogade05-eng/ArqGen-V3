"""VersionService (spec 80) — save / list / restore / compare / export /
branch project versions. FASE 37 adds export to file, branching into a
new project and a mandatory pre-restore backup (spec 81)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.errors import DomainError
from services.context import ProjectContext


class VersionService:
    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    def save_version(self, author: str, description: str,
                     snapshot_json: str) -> Dict[str, Any]:
        number = self.ctx.versions_repo.next_number()
        version_id = self.ctx.versions_repo.save(number, author, description, snapshot_json)
        self.ctx.emit("DOCUMENT_CHANGED", {"version": number, "action": "SAVED"})
        return {"id": version_id, "number": number, "author": author,
                "description": description}

    def list_versions(self) -> List[Dict[str, Any]]:
        return self.ctx.versions_repo.list()

    def get_snapshot(self, number: int) -> str:
        snapshot = self.ctx.versions_repo.get_snapshot(number)
        if snapshot is None:
            raise DomainError(
                message=f"Versión inexistente: {number}", code="ARQ-DOM-070",
                suggested_action="Liste las versiones disponibles con 'version list'.")
        return snapshot

    def restore_version(self, number: int, snapshot_json: str) -> None:
        """Replace current state with the snapshot (auto-backup first, spec 81)."""
        import json

        from persistence.backup.service import BackupService
        # Spec 81: backup before destructive operations.
        service = BackupService(self.backup_dir or "backups")
        service.create_full_backup(self.ctx.db_path, label="pre_restore")
        data = json.loads(snapshot_json)
        self._wipe_domain_tables()
        self._reload_from_snapshot(data)
        self.ctx.emit("DOCUMENT_CHANGED", {"version": number, "action": "RESTORED"})

    @property
    def backup_dir(self) -> str:
        import os
        return os.path.join(os.path.dirname(self.ctx.db_path) or ".", "backups")

    # -- FASE 37: export / branch / compare by numbers ---------------------
    def export_version(self, number: int, out_path: str) -> str:
        """Write the stored snapshot of a version to a JSON file."""
        snapshot = self.get_snapshot(number)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(snapshot)
        return out_path

    def branch_version(self, number: int, new_db_path: str) -> Dict[str, Any]:
        """Clone a version into a NEW project file (spec 80: clone/branch).

        Creates the target file with the full schema and reloads the
        snapshot of the requested version into it. The current project is
        not modified.
        """
        import json
        import os

        from persistence.repositories.architecture_repo import (
            ArchitectureRepository, ProjectRepository,
        )
        from persistence.sqlite.connection import ConnectionManager, Session
        from services.context import ProjectContext

        if os.path.exists(new_db_path):
            from core.errors import PersistenceError
            raise PersistenceError(
                message=f"Ya existe el archivo destino: {new_db_path}",
                code="ARQ-PER-022")
        snapshot_json = self.get_snapshot(number)
        data = json.loads(snapshot_json)
        conn = ConnectionManager(new_db_path).connect()
        session = Session(conn)
        try:
            from persistence.migrations import MIGRATIONS, MigrationRunner
            MigrationRunner(MIGRATIONS).migrate(session)
            project_data = data.get("project") or {}
            from domain.model import Project
            project = Project(
                id=project_data.get("id") or self.ctx.project.id,
                name=f"{project_data.get('name', 'proyecto')} (rama v{number})",
                client=project_data.get("client", ""),
                address=project_data.get("address", ""),
                description=project_data.get("description", ""),
                ruleset_code=project_data.get("ruleset_code", ""),
                currency=project_data.get("currency", "CUP"))
            ProjectRepository(session).save(project)
            session.commit()
            branch_ctx = ProjectContext(new_db_path, session, project,
                                        dna_registry=self.ctx.dna_registry)
            service = VersionService(branch_ctx)
            service._wipe_domain_tables()
            service._reload_from_snapshot(
                data, name_override=f"{project_data.get('name', 'proyecto')} (rama v{number})")
            branch_ctx.commit()
            branch_ctx.emit("DOCUMENT_CHANGED",
                            {"version": number, "action": "BRANCHED"})
            branch_ctx.commit()
            branch_ctx.close()
            return {"path": new_db_path, "version": number,
                    "project": (f"{project_data.get('name', 'proyecto')} "
                                f"(rama v{number})")}
        except Exception:
            session.close()
            raise

    def _wipe_domain_tables(self) -> None:
        for table in (
            "budget_item_resources", "budget_items", "budget_chapters", "budgets",
            "quantities", "prices", "price_lists", "resources",
            "calculations", "handrails", "ramps", "roofs", "furniture",
            "space_relationships", "openings", "walls",
            "spaces", "zones", "levels", "buildings", "sites",
        ):
            self.ctx.session.execute(f"DELETE FROM {table}")

    def _reload_from_snapshot(self, data: Dict[str, Any],
                              name_override: Optional[str] = None) -> None:
        from persistence.repositories.architecture_repo import ArchitectureRepository
        from services.commands_impl import snapshot_to_entity

        arch = ArchitectureRepository(self.ctx.session)
        # Re-create the project row first
        project_data = data.get("project")
        if project_data:
            from services.commands_impl import entity_snapshot
            from domain.model import Project
            from persistence.repositories.architecture_repo import ProjectRepository
            ProjectRepository(self.ctx.session).save(Project(
                id=project_data["id"], name=name_override or project_data.get("name", "proyecto"),
                client=project_data.get("client", ""), address=project_data.get("address", ""),
                description=project_data.get("description", ""),
                units_length=project_data.get("units_length", "m"),
                ruleset_code=project_data.get("ruleset_code", ""),
                currency=project_data.get("currency", "CUP")))
        # Insert entities in dependency order
        order = ("SITE", "BUILDING", "LEVEL", "ZONE", "SPACE", "WALL",
                 "DOOR", "WINDOW", "OPENING", "SPACE_RELATIONSHIP",
                 "FURNITURE", "ROOF", "RAMP", "HANDRAIL")
        for entity_type in order:
            for snapshot in data.get("entities", {}).get(entity_type, []):
                arch.save(snapshot_to_entity(snapshot))

    def compare_versions(self, snapshot_a: str, snapshot_b: str) -> Dict[str, Any]:
        """Structural diff: entity counts and code sets per type."""
        import json

        a = json.loads(snapshot_a)
        b = json.loads(snapshot_b)
        diff: Dict[str, Any] = {"types": {}}
        types = set(a.get("entities", {})) | set(b.get("entities", {}))
        for entity_type in sorted(types):
            codes_a = {e.get("code") for e in a.get("entities", {}).get(entity_type, [])}
            codes_b = {e.get("code") for e in b.get("entities", {}).get(entity_type, [])}
            diff["types"][entity_type] = {
                "count_a": len(codes_a), "count_b": len(codes_b),
                "added": sorted(codes_b - codes_a),
                "removed": sorted(codes_a - codes_b),
            }
        return diff

    def compare_by_numbers(self, number_a: int, number_b: int) -> Dict[str, Any]:
        """Diff two stored versions plus quick totals (FASE 37)."""
        diff = self.compare_versions(self.get_snapshot(number_a),
                                     self.get_snapshot(number_b))
        diff["a"] = number_a
        diff["b"] = number_b
        diff["changed_types"] = sorted(
            t for t, d in diff["types"].items()
            if d["added"] or d["removed"])
        return diff


__all__ = ["VersionService"]
