"""Structure module plugin (spec sections 33-34, 88, 89)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class StructurePlugin(ARQGenPlugin):
    plugin_id = "structure"
    name = "Estructura"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["architecture", "qto"]
    entities: list[str] = ["MATERIAL", "SECTION", "ELEMENT",
                           "LOAD_CASE", "COMBINATION"]
    services: list[str] = ["StructureService"]
    events: list[str] = ["OBJECT_CREATED", "OBJECT_UPDATED",
                         "OBJECT_DELETED"]
    commands: list[str] = ["struct material-add", "struct section-add",
                           "struct element-add", "struct element-list",
                           "struct element-delete", "struct case-add",
                           "struct combo-add", "struct defaults",
                           "struct analyze", "struct truss",
                           "struct connection-check", "struct report"]
    rules: list[str] = []
    calculators: list[str] = ["ELEMENT_LENGTH", "CONCRETE_VOLUME",
                              "STEEL_WEIGHT", "FORMWORK_AREA"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["structure_utilization", "structure_steel"]
