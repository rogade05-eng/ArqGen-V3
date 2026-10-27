"""Fire alarm module plugin (spec sections 43-44, 88, 89).

La matriz causa/efecto (§44) se evalúa con el ruleset versionado
resources/rulesets/fire_cause_effect_v1.json declarado en `rules`.
"""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class FirePlugin(ARQGenPlugin):
    plugin_id = "fire"
    name = "Detección y alarma de incendios"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations"]
    entities: list[str] = ["FIRE_PANEL", "FIRE_MODULE", "SMOKE_DETECTOR",
                           "HEAT_DETECTOR", "CALL_POINT"]
    services: list[str] = ["SecurityService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["sec net", "sec device-add", "sec fire-check",
                           "sec cause-effect"]
    rules: list[str] = ["fire_cause_effect_v1"]
    calculators: list[str] = ["SEC_CABLE_LENGTH", "FIRE_DETECTOR_COUNT",
                              "CALL_POINT_COUNT", "SOUNDER_COUNT",
                              "FIRE_PANEL_COUNT"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["fire_check", "cause_effect_matrix",
                          "security_bom"]
