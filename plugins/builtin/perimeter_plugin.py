"""Perimeter protection module plugin (spec sections 48-49, 88, 89)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class PerimeterPlugin(ARQGenPlugin):
    plugin_id = "perimeter"
    name = "Protección perimetral"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations"]
    entities: list[str] = ["FENCE", "FENCE_SENSOR", "PERIMETER_CAMERA",
                           "BEAM_DETECTOR", "GATE"]
    services: list[str] = ["SecurityService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["sec net", "sec device-add",
                           "sec perimeter-check"]
    rules: list[str] = []
    calculators: list[str] = ["SEC_CABLE_LENGTH", "FENCE_SENSOR_COUNT",
                              "CAMERA_COUNT"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["perimeter_check", "security_bom"]
