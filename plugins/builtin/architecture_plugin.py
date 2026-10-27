"""Architecture module plugin (spec sections 20-23)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class ArchitecturePlugin(ARQGenPlugin):
    plugin_id = "architecture"
    name = "Arquitectura"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = []
    entities: list[str] = ["SITE", "BUILDING", "LEVEL", "ZONE", "SPACE", "WALL",
                           "DOOR", "WINDOW", "OPENING", "SPACE_RELATIONSHIP"]
    services: list[str] = ["ArchitectureService", "SpatialService", "ValidationService"]
    events: list[str] = ["OBJECT_CREATED", "OBJECT_UPDATED", "OBJECT_DELETED",
                         "GEOMETRY_CHANGED", "SPACE_CHANGED"]
    commands: list[str] = ["CREATE_ENTITY", "UPDATE_ENTITY", "DELETE_ENTITY"]
    rules: list[str] = []
    reports: list[str] = ["adjacency_report", "dna_findings"]
