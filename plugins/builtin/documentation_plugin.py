"""Documentation module plugin (spec sections 68-70, 106, 88, 89)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class DocumentationPlugin(ARQGenPlugin):
    plugin_id = "documentation"
    name = "Documentación (memorias, cuadros, planos)"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["architecture", "qto", "budget"]
    entities: list[str] = ["DRAWING", "DOC_TEMPLATE"]
    services: list[str] = ["DocumentationService"]
    events: list[str] = ["DOCUMENT_CHANGED", "OBJECT_CREATED",
                         "OBJECT_UPDATED", "OBJECT_DELETED"]
    commands: list[str] = ["docs variables", "docs memoria",
                           "docs tecnica", "docs specs", "docs cuadros",
                           "docs listados", "docs informe", "docs module",
                           "docs drawing-add", "docs drawing-list",
                           "docs drawing-delete", "docs template-add",
                           "docs template-render"]
    rules: list[str] = []
    calculators: list[str] = []
    importers: list[str] = []
    exporters: list[str] = ["MARKDOWN (.md)", "HTML (.html)", "TXT (.txt)"]
    reports: list[str] = ["memoria_descriptiva", "memoria_tecnica",
                          "especificaciones", "cuadros", "listados",
                          "informe_proyecto", "module_docs",
                          "area_table", "openings_table"]
