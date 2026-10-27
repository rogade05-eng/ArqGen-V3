"""Intrusion module plugin (spec section 45, 88, 89)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class IntrusionPlugin(ARQGenPlugin):
    plugin_id = "intrusion"
    name = "Intrusión"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations"]
    entities: list[str] = ["INTRUSION_PANEL", "PIR", "MAGNETIC_CONTACT",
                           "GLASS_BREAK", "DOOR_CONTACT", "KEYPAD",
                           "EXPANDER"]
    services: list[str] = ["SecurityService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["sec net", "sec device-add",
                           "sec intrusion-check"]
    rules: list[str] = []
    calculators: list[str] = ["SEC_CABLE_LENGTH", "INTRUSION_PANEL_COUNT",
                              "PIR_COUNT", "CONTACT_COUNT"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["intrusion_zones", "security_bom"]
