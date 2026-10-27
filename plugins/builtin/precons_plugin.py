"""PRECONS module plugin (FASES 30-31, §59-60, 88, 89).

Los indicadores, recursos y coeficientes viven en el ruleset
versionado resources/rulesets/precons_cuba_v1.json y pueden
importarse/mapearse (SIECONS-like) con `precons import`.
"""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class PreconsPlugin(ARQGenPlugin):
    plugin_id = "precons"
    name = "PRECONS (análisis de precios unitarios)"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["qto", "budget"]
    entities: list[str] = ["PRECONS_RULESET", "PRICE_ANALYSIS"]
    services: list[str] = ["PreconsService"]
    events: list[str] = ["PRICE_CHANGED", "QUANTITY_CHANGED"]
    commands: list[str] = ["precons list", "precons analyze",
                           "precons project", "precons compare",
                           "precons import"]
    rules: list[str] = ["precons_cuba_v1", "precons_iii_rospres_330"]
    calculators: list[str] = []
    importers: list[str] = ["PRECONS_RULESET_JSON (mapa de columnas)"]
    exporters: list[str] = []
    reports: list[str] = ["precons_analysis", "precons_comparison"]
