"""CCTV module plugin (spec sections 40-42, 88, 89).

Reutiliza el modelo genérico de redes (installations), el motor FOV
(engines/fov_engine.py) y el motor CCTV (engines/cctv_engine.py) a
través de SecurityService.
"""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class CctvPlugin(ARQGenPlugin):
    plugin_id = "cctv"
    name = "CCTV (circuito cerrado de televisión)"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations"]
    entities: list[str] = ["CAMERA", "NVR", "POE_SWITCH",
                           "STORAGE_CCTV", "SEC_CABLE"]
    services: list[str] = ["SecurityService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["sec net", "sec device-add", "sec coverage",
                           "sec network", "sec cabling", "sec bom"]
    rules: list[str] = []
    calculators: list[str] = ["SEC_CABLE_LENGTH", "CAMERA_COUNT",
                              "RECORDER_COUNT", "SEC_CONTROLLER_COUNT"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["cctv_coverage", "cctv_network", "cctv_cabling",
                          "security_bom"]
