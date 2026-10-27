"""Gas module plugin (spec sections 31, 88, 89).

El spec exige: "Debe quedar integrado como plugin del sistema de
instalaciones". Este plugin declara esa integración: depende del plugin
`installations`, reutiliza InstallationsService (size_gas) y el motor
engines/gas_engine.py, y registra las validaciones de la disciplina
§31 (diámetros, recorridos, válvulas, ventilación, separación y puntos
de consumo) como reglas declaradas del plugin.

Entidades §31 materializadas como kinds de nodo en redes de la
disciplina GAS: GasSource->SOURCE, GasMeter->METER, Pipe->SEGMENT,
Valve->VALVE, Regulator->REGULATOR, Appliance->APPLIANCE.
"""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class GasPlugin(ARQGenPlugin):
    plugin_id = "gas"
    name = "Gas (plugin del sistema de instalaciones)"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["installations"]
    entities: list[str] = ["GAS_SOURCE", "GAS_METER", "GAS_PIPE",
                           "GAS_VALVE", "GAS_REGULATOR", "GAS_APPLIANCE"]
    services: list[str] = ["InstallationsService"]
    events: list[str] = ["SYSTEM_CHANGED", "DEVICE_MOVED", "ROUTE_CHANGED"]
    commands: list[str] = ["gas size", "gas check"]
    rules: list[str] = ["GAS_DIAMETERS", "GAS_ROUTES", "GAS_VALVES",
                        "GAS_VENTILATION", "GAS_SEPARATION",
                        "GAS_CONSUMPTION_POINTS"]
    calculators: list[str] = ["GAS_PIPE_LENGTH", "GAS_APPLIANCE_COUNT",
                              "GAS_INSTALLED_POWER"]
    importers: list[str] = []
    exporters: list[str] = []
    reports: list[str] = ["gas_sizing", "gas_validation"]
