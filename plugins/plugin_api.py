"""Plugin API and loader (spec sections 88, 89).

Every plugin declares: dependencies, entities, services, events, commands,
rules, calculators, importers, exporters, reports. Built-in modules are
loaded as plugins; additional plugins may live in the plugins/ directory.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core import API_VERSION
from core.errors import PluginError
from services.context import ApplicationContext, ProjectContext


class ARQGenPlugin(ABC):
    """Plugin contract (spec section 88)."""

    plugin_id: str = ""
    name: str = ""
    version: str = "1.0"
    api_version: str = API_VERSION

    # Declarations (spec 89)
    dependencies: List[str] = []
    entities: List[str] = []
    services: List[str] = []
    events: List[str] = []
    commands: List[str] = []
    rules: List[str] = []
    calculators: List[str] = []
    importers: List[str] = []
    exporters: List[str] = []
    reports: List[str] = []

    def initialize(self, application: ApplicationContext) -> None:
        """Wire app-level services (called once at bootstrap)."""

    def on_project_open(self, context: ProjectContext) -> None:
        """Per-project hook."""

    def register_exporters(self, export_service: Any) -> None:
        """Optional: add exporters to the registry."""

    def register_rules(self, rule_service: Any) -> None:
        """Optional: install rulesets."""

    def shutdown(self) -> None:
        """Release resources."""


@dataclass
class LoadedPlugin:
    plugin: ARQGenPlugin
    source: str
    error: str = ""


class PluginLoader:
    """Loads built-in plugins and optional external plugins (plugins dir)."""

    def __init__(self, application: ApplicationContext,
                 external_dir: Optional[str] = None) -> None:
        self.application = application
        self.external_dir = external_dir
        self.loaded: List[LoadedPlugin] = []

    def load_all(self) -> List[LoadedPlugin]:
        self.loaded.clear()
        self._load_builtin()
        if self.external_dir and os.path.isdir(self.external_dir):
            self._load_external()
        return self.loaded

    def _load_builtin(self) -> None:
        import plugins.builtin
        for module_info in pkgutil.iter_modules(plugins.builtin.__path__):
            if module_info.name.startswith("_"):
                continue
            module_name = f"plugins.builtin.{module_info.name}"
            try:
                module = importlib.import_module(module_name)
                plugin = self._find_plugin(module)
                if plugin is None:
                    continue
                self._activate(plugin, source=module_name)
            except Exception as exc:
                self.loaded.append(LoadedPlugin(
                    plugin=None, source=module_name,  # type: ignore[arg-type]
                    error=f"{type(exc).__name__}: {exc}"))

    def _load_external(self) -> None:
        assert self.external_dir
        for entry in sorted(os.listdir(self.external_dir)):
            plugin_file = os.path.join(self.external_dir, entry)
            if entry.endswith(".py"):
                module_name = entry[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    plugin = self._find_plugin(module)
                    if plugin is None:
                        continue
                    self._activate(plugin, source=plugin_file)
                except Exception as exc:
                    self.loaded.append(LoadedPlugin(
                        plugin=None, source=plugin_file,  # type: ignore[arg-type]
                        error=f"{type(exc).__name__}: {exc}"))

    @staticmethod
    def _find_plugin(module) -> Optional[ARQGenPlugin]:
        for attribute in vars(module).values():
            if (isinstance(attribute, type) and issubclass(attribute, ARQGenPlugin)
                    and attribute is not ARQGenPlugin):
                return attribute()
        return None

    def _activate(self, plugin: ARQGenPlugin, source: str) -> None:
        if not plugin.plugin_id:
            raise PluginError(
                message=f"El plugin en {source} no define plugin_id",
                code="ARQ-PLG-001")
        plugin.initialize(self.application)
        self.loaded.append(LoadedPlugin(plugin=plugin, source=source))

    def notify_project_open(self, context: ProjectContext) -> None:
        for entry in self.loaded:
            if entry.plugin is not None and not entry.error:
                try:
                    entry.plugin.on_project_open(context)
                except Exception as exc:
                    entry.error = f"on_project_open: {exc}"

    def info(self) -> List[Dict[str, Any]]:
        """Detailed declaration info of every loaded plugin (FASE 39)."""
        rows: List[Dict[str, Any]] = []
        for entry in self.loaded:
            if entry.plugin is None or entry.error:
                rows.append({"source": entry.source, "error": entry.error,
                             "plugin_id": "", "status": "ERROR"})
                continue
            p = entry.plugin
            rows.append({
                "plugin_id": p.plugin_id, "name": p.name, "version": p.version,
                "api_version": p.api_version, "source": entry.source,
                "status": "LOADED",
                "dependencies": list(p.dependencies),
                "entities": list(p.entities), "services": list(p.services),
                "events": list(p.events), "commands": list(p.commands),
                "rules": list(p.rules), "calculators": list(p.calculators),
                "importers": list(p.importers), "exporters": list(p.exporters),
                "reports": list(p.reports),
            })
        return rows


# -- FASE 39: static validation, info and scaffolding ---------------------

def validate_plugin_file(path: str) -> Dict[str, Any]:
    """Validate a plugin file WITHOUT executing/activating it (FASE 39).

    Checks (in order): file exists, imports cleanly, declares exactly one
    ARQGenPlugin subclass, plugin_id non-empty, api_version matches the
    current core API, declarations are lists of strings.
    """
    from core import API_VERSION as _API_VERSION
    result: Dict[str, Any] = {"path": path, "ok": False, "errors": [],
                              "warnings": []}
    if not os.path.exists(path):
        result["errors"].append("El archivo no existe")
        return result
    module_name = "_arqgen_plugin_validation"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        result["errors"].append("No se pudo cargar el módulo")
        return result
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        result["errors"].append(f"Error de importación: {type(exc).__name__}: {exc}")
        return result
    candidates = []
    for attribute in vars(module).values():
        if (isinstance(attribute, type) and issubclass(attribute, ARQGenPlugin)
                and attribute is not ARQGenPlugin):
            candidates.append(attribute)
    if not candidates:
        result["errors"].append("No declara ninguna subclase de ARQGenPlugin")
        return result
    if len(candidates) > 1:
        result["warnings"].append(
            f"Declara {len(candidates)} plugins; se usará el primero")
    plugin_class = candidates[0]
    if not plugin_class.plugin_id:
        result["errors"].append("plugin_id vacío")
    if not plugin_class.name:
        result["warnings"].append("name vacío")
    if plugin_class.api_version != _API_VERSION:
        result["warnings"].append(
            f"api_version {plugin_class.api_version!r} != API del núcleo {_API_VERSION!r}")
    for declaration in ("dependencies", "entities", "services", "events",
                        "commands", "rules", "calculators", "importers",
                        "exporters", "reports"):
        value = getattr(plugin_class, declaration, None)
        if value is None or not isinstance(value, list) \
                or not all(isinstance(item, str) for item in value):
            result["errors"].append(f"Declaración '{declaration}' debe ser lista de str")
    result["ok"] = not result["errors"]
    result["plugin_id"] = plugin_class.plugin_id
    result["version"] = plugin_class.version
    return result


PLUGIN_TEMPLATE = '''"""External ARQ GEN plugin (scaffold generated by 'plugins new').

Edit the declarations and hooks. See plugins/plugin_api.py for the
contract (spec 88-89). Drop this file into plugins/external to load it.
"""

from __future__ import annotations

from typing import Any, Dict, List

from plugins.plugin_api import ARQGenPlugin
from services.context import ApplicationContext, ProjectContext


class MyPlugin(ARQGenPlugin):
    plugin_id = "my_plugin"
    name = "Mi plugin"
    version = "0.1.0"

    # Declarations (spec 89)
    dependencies: List[str] = []
    entities: List[str] = []
    services: List[str] = []
    events: List[str] = []
    commands: List[str] = []
    rules: List[str] = []
    calculators: List[str] = []
    importers: List[str] = []
    exporters: List[str] = []
    reports: List[str] = []

    def initialize(self, application: ApplicationContext) -> None:
        """Wire app-level services (called once at bootstrap)."""

    def on_project_open(self, context: ProjectContext) -> None:
        """Per-project hook."""
'''


def scaffold_plugin(out_path: str) -> str:
    """Generate a commented plugin template file (FASE 39)."""
    if os.path.exists(out_path):
        raise PluginError(
            message=f"Ya existe un archivo en: {out_path}",
            code="ARQ-PLG-002")
    directory = os.path.dirname(out_path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(PLUGIN_TEMPLATE)
    return out_path


__all__ = ["ARQGenPlugin", "PluginLoader", "LoadedPlugin",
           "validate_plugin_file", "scaffold_plugin"]
