"""Coordination and clash detection module plugin (FASES 24-25, §88-89)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class CoordinationPlugin(ARQGenPlugin):
    plugin_id = "coordination"
    name = "Coordinación y detección de interferencias"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations", "structure"]
    entities: list[str] = ["CLASH"]
    services: list[str] = ["CoordinationService"]
    events: list[str] = ["CLASH_CREATED", "CLASH_RESOLVED"]
    commands: list[str] = ["clash run", "clash list", "clash status"]
    rules: list[str] = []
    calculators: list[str] = []
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["clash_summary"]
