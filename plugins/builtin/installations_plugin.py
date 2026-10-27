"""Installations module plugin (spec sections 24-30, 32, 88, 89).

Alcance propio: redes genéricas, routing §26, eléctrica §27,
sanitaria §28, HVAC §29, pluviales §30 y telecomunicaciones §32.
Las disciplinas que el spec define como plugins independientes
(gas §31, estructura §33-34, seguridad §37-49, BIM §63-67) viven
en sus propios plugins builtin.
"""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class InstallationsPlugin(ARQGenPlugin):
    plugin_id = "installations"
    name = ("Instalaciones (redes, routing, eléctrica, sanitaria, "
            "pluviales, HVAC, telecom)")
    version = "1.4"
    api_version = "1.0"

    dependencies: list[str] = ["architecture", "qto"]
    entities: list[str] = ["NETWORK", "NODE", "SEGMENT"]
    services: list[str] = ["InstallationsService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["net", "node", "link", "elec", "san", "hvac",
                           "plu", "tel"]
    rules: list[str] = []
    calculators: list[str] = [
        "CONDUIT_LENGTH", "CONDUCTOR_LENGTH", "PIPE_LENGTH", "DRAIN_LENGTH",
        "DUCT_LENGTH", "SEGMENT_LENGTH", "DEVICE_COUNT", "TERMINAL_COUNT",
        "PANEL_COUNT", "FIXTURE_COUNT", "COOLING_UNITS", "COOLING_CAPACITY",
        "INSTALLED_POWER",
        "ROOF_DRAIN_COUNT", "GUTTER_LENGTH", "STORM_TANK_VOLUME",
        "TELECOM_CONDUIT_LENGTH", "TELECOM_CABLE_LENGTH", "FIBER_LENGTH",
        "TELECOM_OUTLET_COUNT", "RACK_COUNT", "RACK_UNITS_USED",
    ]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["network_validation", "electrical_summary",
                          "sanitary_sizing", "hvac_loads",
                          "stormwater_sizing", "telecom_sizing"]
