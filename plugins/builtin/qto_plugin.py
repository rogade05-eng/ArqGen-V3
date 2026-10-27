"""QTO module plugin (spec sections 51, 52, 102, 103)."""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class QTOPlugin(ARQGenPlugin):
    plugin_id = "qto"
    name = "Cómputo de cantidades"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["architecture"]
    entities: list[str] = ["QUANTITY"]
    services: list[str] = ["QuantityService"]
    events: list[str] = ["QUANTITY_CHANGED"]
    calculators: list[str] = ["WALL_AREA_GROSS", "WALL_AREA_NET", "WALL_VOLUME",
                              "WALL_LENGTH", "OPENING_COUNT", "OPENING_AREA",
                              "SPACE_AREA", "SPACE_PERIMETER", "SPACE_VOLUME"]
    reports: list[str] = ["qto_totals"]
