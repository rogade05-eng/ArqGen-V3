"""ProjectContext and DependencyContainer (spec sections 3, 101).

Layer discipline: UI → APPLICATION → DOMAIN → SERVICES → ENGINES →
PERSISTENCE. Modules never touch other modules' internals; everything is
reached through this context / public services.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from core.commands.bus import CommandBus
from core.events.bus import EventBus
from core.graphs.dependency import DependencyGraph
from core.ids.codes import CodeAllocator
from domain.knowledge import SpaceDNARegistry
from domain.model import Project
from persistence.migrations import MIGRATIONS, MigrationRunner
from persistence.migrations.runner import applied_versions
from persistence.repositories.architecture_repo import ArchitectureRepository
from persistence.repositories.core_repos import (
    AuditRepository, CalculationRepository, EventRepository, FormulaRepository,
    RuleRepository, SettingsRepository, VersionRepository,
)
from persistence.repositories.installations_repo import InstallationsRepository
from persistence.repositories.clash_repo import ClashRepository
from persistence.repositories.documentation_repo import DocTemplateRepository, DrawingRepository
from persistence.repositories.structure_repo import StructureRepository
from persistence.repositories.qto_budget_repos import BudgetRepository, QuantityRepository
from persistence.sqlite.connection import ConnectionManager, Session

MIGRATION_BACKUP_LABEL = "pre_migration"


class ProjectContext:
    """One open project file with all its services wired together."""

    def __init__(self, db_path: str, session: Session, project: Project,
                 dna_registry: Optional[SpaceDNARegistry] = None) -> None:
        self.db_path = db_path
        self.session = session
        self.project = project
        self.dna_registry = dna_registry or SpaceDNARegistry()

        # Repositories
        self.architecture = ArchitectureRepository(session)
        self.settings = SettingsRepository(session)
        self.events_repo = EventRepository(session)
        self.audit_repo = AuditRepository(session)
        self.rules_repo = RuleRepository(session)
        self.formulas_repo = FormulaRepository(session)
        self.calculations_repo = CalculationRepository(session)
        self.versions_repo = VersionRepository(session)
        self.quantities_repo = QuantityRepository(session)
        self.budget_repo = BudgetRepository(session)
        self.installations = InstallationsRepository(session)
        self.structure = StructureRepository(session)
        self.clash_repo = ClashRepository(session)
        self.documentation = _DocumentationRepos(
            DrawingRepository(session), DocTemplateRepository(session))

        # Core machinery
        self.event_bus = EventBus()
        self.command_bus = CommandBus()
        self.dependency_graph = DependencyGraph()
        self.code_allocator = CodeAllocator(
            self.architecture.all_codes(project.id)
            + self.installations.all_codes(project.id)
            + self.structure.all_codes(project.id)
            + self.clash_repo.all_codes(project.id)
            + self.documentation.all_codes(project.id))

        # User of this session (audit trail)
        self.user: str = "local"

    # -- helpers -----------------------------------------------------------
    def emit(self, event_type: str, payload: Dict[str, Any], source: str = "") -> list[str]:
        from core.events.bus import Event
        event = Event(type=event_type, payload=payload, source=source or "core")
        errors = self.event_bus.emit(event)
        try:
            self.events_repo.append(event)
        except Exception:  # pragma: no cover - persistence of events best effort
            pass
        return errors

    def next_code(self, discipline: str, entity_type: str) -> str:
        return self.code_allocator.next_code(discipline, entity_type)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()

    def rebuild_dependency_graph(self) -> None:
        """WALL → OPENINGS, WALL ↔ SPACE relationships and network topology (spec 74)."""
        graph = DependencyGraph()
        project_id = self.project.id
        openings = self.architecture.list("OPENING", project_id)
        for opening in openings:
            if opening.wall_id:
                graph.add_edge(opening.wall_id, opening.id, "wall→opening")
        walls = {w.id for w in self.architecture.list("WALL", project_id)}
        for rel in self.architecture.list("SPACE_RELATIONSHIP", project_id):
            if rel.from_space_id and rel.to_space_id:
                graph.add_edge(rel.from_space_id, rel.to_space_id, f"space→{rel.kind}")
        # Installations topology: network → node → segment (spec 74).
        for network in self.installations.list("NETWORK", project_id):
            for node in self.installations.nodes_of(network.id):
                graph.add_edge(network.id, node.id, "network→node")
            for segment in self.installations.segments_of(network.id):
                graph.add_edge(segment.from_node_id, segment.id, "node→segment")
                graph.add_edge(segment.id, segment.to_node_id, "segment→node")
        # Structure: element → material / section (spec 74).
        for element in self.structure.list("ELEMENT", project_id):
            if element.material_id:
                graph.add_edge(element.material_id, element.id, "material→element")
            if element.section_id:
                graph.add_edge(element.section_id, element.id, "section→element")
        self.dependency_graph = graph


class _DocumentationRepos:
    """Bundle of the two documentation repositories (spec 68-70)."""

    def __init__(self, drawings: DrawingRepository,
                 templates: DocTemplateRepository) -> None:
        self.drawings = drawings
        self.templates = templates

    def all_codes(self, project_id: str) -> list[str]:
        return (self.drawings.all_codes(project_id)
                + self.templates.all_codes(project_id))


class DependencyContainer:
    """Minimal, deterministic dependency container (no reflection magic)."""

    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._instances: Dict[str, Any] = {}

    def register(self, key: str, factory: Callable[[], Any], singleton: bool = True) -> None:
        self._factories[key] = factory
        if not singleton:
            self._instances.pop(key, None)

    def register_instance(self, key: str, instance: Any) -> None:
        self._instances[key] = instance

    def get(self, key: str) -> Any:
        if key in self._instances:
            return self._instances[key]
        if key not in self._factories:
            raise KeyError(f"Servicio no registrado en el contenedor: {key}")
        instance = self._factories[key]()
        self._instances[key] = instance
        return instance

    def keys(self) -> list[str]:
        return sorted(set(self._factories) | set(self._instances))

    def clear(self) -> None:
        self._instances.clear()


class ApplicationContext:
    """Application-wide services that do not depend on an open project."""

    def __init__(self, log_dir: Optional[str] = None, backup_dir: Optional[str] = None) -> None:
        self.container = DependencyContainer()
        self.log_dir = log_dir or ""
        self.backup_dir = backup_dir or ""
        self.dna_registry = SpaceDNARegistry()
        self._load_knowledge()

    def _load_knowledge(self) -> None:
        from app.paths import resource_path
        dna_path = resource_path("knowledge", "space_dna.json")
        if os.path.exists(dna_path):
            self.dna_registry.load_file(dna_path)

    # -- project lifecycle --------------------------------------------------
    def open_project(self, db_path: str) -> ProjectContext:
        if not os.path.exists(db_path):
            from core.errors import PersistenceError
            raise PersistenceError(
                message=f"El proyecto no existe: {db_path}",
                code="ARQ-PER-020",
                suggested_action="Créelo con 'project create' o verifique la ruta.",
            )
        conn = ConnectionManager(db_path).connect()
        session = Session(conn)
        try:
            runner = MigrationRunner(MIGRATIONS)
            pending = [m.version for m in MIGRATIONS if m.version not in applied_versions(session)]
            if pending:
                self.backup_before_migration(db_path)
                runner.migrate(session)
                # Persist the new schema versions before any service uses the DB.
                session.commit()
            else:
                runner.migrate(session)
            projects = ArchitectureRepository(session).projects
            project = projects.get_first()
            if project is None:
                from core.errors import PersistenceError
                raise PersistenceError(
                    message=f"El archivo no contiene un proyecto ARQ GEN válido: {db_path}",
                    code="ARQ-PER-021",
                )
            ctx = ProjectContext(db_path, session, project,
                                 dna_registry=self.dna_registry)
            ctx.emit("PROJECT_OPENED", {"path": db_path, "project": project.name})
            # v3.22.0: el INSERT del evento abre SU transacción después
            # de cualquier commit previo; sin este commit la conexión
            # queda con la escritura pendiente y un contexto descartado
            # sin recoger por el GC retiene el LOCK del fichero.
            session.commit()
            return ctx
        except Exception:
            session.close()
            raise

    def create_project(self, db_path: str, name: str, client: str = "", address: str = "",
                       description: str = "", ruleset_code: str = "",
                       currency: str = "CUP") -> ProjectContext:
        if os.path.exists(db_path):
            from core.errors import PersistenceError
            raise PersistenceError(
                message=f"Ya existe un archivo de proyecto en: {db_path}",
                code="ARQ-PER-022",
                suggested_action="Elija otro nombre de archivo o elimine el existente.",
            )
        conn = ConnectionManager(db_path).connect()
        session = Session(conn)
        project = Project(name=name, client=client, address=address,
                          description=description, ruleset_code=ruleset_code,
                          currency=currency)
        try:
            runner = MigrationRunner(MIGRATIONS)
            runner.migrate(session)
            repo = ArchitectureRepository(session).projects
            repo.save(project)
            SettingsRepository(session).set("app_version", "1.7.0")
            session.commit()
            ctx = ProjectContext(db_path, session, project,
                                 dna_registry=self.dna_registry)
            ctx.emit("PROJECT_CREATED", {"path": db_path, "project": name})
            # v3.22.0: mismo criterio que en open_project — el evento
            # del ciclo de vida se confirma aquí y la conexión queda
            # OCIOSA (sin transacción abierta que retenga el lock).
            session.commit()
            return ctx
        except Exception:
            session.close()
            raise

    def backup_before_migration(self, db_path: str) -> str:
        from persistence.backup.service import BackupService
        service = BackupService(self.backup_dir or os.path.join(
            os.path.dirname(db_path) or ".", "backups"))
        info = service.create_full_backup(db_path, label=MIGRATION_BACKUP_LABEL)
        return info.path


__all__ = ["ApplicationContext", "ProjectContext", "DependencyContainer"]
