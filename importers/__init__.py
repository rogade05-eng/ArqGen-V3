"""Importers package (spec 94): DETECT -> PARSE -> VALIDATE -> MAP ->
CONVERT -> PREVIEW -> APPROVE -> IMPORT -> AUDIT for external files.

Modules:
- tables:     PARSE stage for .xlsx/.csv/.txt -> normalized dict rows.
- catalog:    PRECONS III catalog -> ruleset (spec 59-60) with column mapping.
- dxf_reader: DXF entities -> wall/space candidates -> project entities.
- dwg_reader: DWG gateway -> local converter -> DXF -> spec 94 (v3.4.0).
"""

from importers.tables import read_table, is_table_file
from importers.catalog import CatalogImporter
from importers.dxf_reader import DxfImporter
from importers.dwg_reader import DWG_VERSIONS, DwgGateway, read_version

__all__ = ["read_table", "is_table_file", "CatalogImporter", "DxfImporter",
           "DWG_VERSIONS", "DwgGateway", "read_version"]
