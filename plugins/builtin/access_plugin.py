"""Access control module plugin (spec sections 46-47, 88, 89)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class AccessPlugin(ARQGenPlugin):
    plugin_id = "access"
    name = "Control de acceso"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations"]
    entities: list[str] = ["ACCESS_CONTROLLER", "READER", "LOCK",
                           "EXIT_BUTTON", "REX", "BARRIER", "UPS_SEC"]
    services: list[str] = ["SecurityService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["sec net", "sec device-add", "sec access-check"]
    rules: list[str] = []
    calculators: list[str] = ["SEC_CABLE_LENGTH", "READER_COUNT",
                              "LOCK_COUNT", "SEC_CONTROLLER_COUNT"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["access_check", "security_bom"]
