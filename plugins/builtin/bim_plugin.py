"""BIM module plugin (spec sections 63-67, 88, 89).

Expone el árbol espacial (BimService) y el exportador IFC4 SPF
(exporters/ifc_exporter.py) registrado en el comando
`export --format ifc`.
"""

from __future__ import annotations

from plugins.plugin_api import ARQGenPlugin


class BimPlugin(ARQGenPlugin):
    plugin_id = "bim"
    name = "BIM / IFC"
    version = "1.0"
    api_version = "1.0"

    dependencies: list[str] = ["architecture", "installations",
                               "structure"]
    entities: list[str] = ["IFC_PROJECT", "IFC_SITE", "IFC_BUILDING",
                           "IFC_STOREY", "IFC_ELEMENT"]
    services: list[str] = ["BimService"]
    events: list[str] = ["OBJECT_CREATED", "OBJECT_UPDATED",
                         "OBJECT_DELETED", "EXPORT_COMPLETED"]
    commands: list[str] = ["bim tree", "bim show", "export ifc"]
    rules: list[str] = []
    calculators: list[str] = []
    importers: list[str] = []
    exporters: list[str] = ["IFC4 (SPF)"]
    reports: list[str] = ["bim_tree", "bim_show"]
