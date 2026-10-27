"""ExportService: format registry and dispatch (spec section 95)."""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional

from core.errors import ExportError
from services.context import ProjectContext

ExportFunc = Callable[[ProjectContext, str], str]

# El paquete «Exportar TODO» (v3.46.0): BIM + planos + datos.
FORMATOS_TODO = ("IFC", "DXF", "DXF_R12", "JSON", "CSV", "XLSX", "SVG")
_EXTENSION = {"IFC": ".ifc", "DXF": ".dxf", "DXF_R12": ".dxf",
              "JSON": ".json", "CSV": ".csv", "XLSX": ".xlsx",
              "SVG": ".svg"}


class ExportService:
    """export(project, format, options) — spec 95 contract."""

    def __init__(self) -> None:
        self._formats: Dict[str, Callable[..., str]] = {}
        self._register_builtin()

    def _register_builtin(self) -> None:
        from exporters.csv_exporter import CSVExporter
        from exporters.dxf_exporter import DXFExporter
        from exporters.ifc_exporter import IfcExporter
        from exporters.json_io import JSONExporter
        from exporters.svg_exporter import export_plan_svg
        from exporters.xlsx_exporter import XLSXExporter

        self._formats["DXF"] = DXFExporter().export
        self._formats["JSON"] = JSONExporter().export
        self._formats["XLSX"] = XLSXExporter().export
        self._formats["CSV"] = CSVExporter().export
        self._formats["IFC"] = IfcExporter().export
        self._formats["SVG"] = export_plan_svg

    def register(self, fmt: str, func: ExportFunc) -> None:
        """Plugins may register additional exporters (spec 89)."""
        self._formats[fmt.upper()] = func

    def formats(self) -> list[str]:
        return sorted(self._formats)

    def export(self, context: ProjectContext, fmt: str, out_path: str,
               options: Optional[Dict[str, str]] = None) -> str:
        key = (fmt or "").upper()
        func = self._formats.get(key)
        if func is None:
            raise ExportError(
                message=f"Formato de exportación no soportado: {fmt}",
                code="ARQ-EXP-060",
                context={"supported": self.formats()},
            )
        options = options or {}
        if key == "CSV":
            return func(context, out_path, table=options.get("table", "quantities"))
        if key == "DXF":
            return func(context, out_path, level_ref=options.get("level"),
                        version=options.get("version", "R2010"))
        if key == "SVG":
            return func(context, out_path,
                        level_ref=options.get("level"),
                        title=options.get("title", ""))
        return func(context, out_path)

    # -- paquete «exportar todo» (v3.46.0) -------------------------------
    def exportar_todo(self, context: ProjectContext, carpeta: str,
                      nombre_base: Optional[str] = None,
                      formatos: Optional[List[str]] = None) -> Dict[str, Any]:
        """Exporta el proyecto COMPLETO a BIM + planos + datos en una
        carpeta, en una sola llamada: IFC4 (BIM), DXF R2010, DXF R12,
        JSON, CSV, XLSX y SVG.

        Cada formato se intenta por separado: si uno no puede (p. ej.
        DXF sin geometría en un proyecto recién creado) queda
        documentado en ``errores`` y los demás siguen. Devuelve::

            {"carpeta", "base", "archivos": {fmt: ruta},
             "errores": {fmt: mensaje}}
        """
        bruto = str(nombre_base or context.project.name or "proyecto")
        base = re.sub(r"[^\w\-]+", "_", bruto.strip()).strip("_") \
            or "proyecto"
        os.makedirs(carpeta, exist_ok=True)
        archivos: Dict[str, str] = {}
        errores: Dict[str, str] = {}
        for fmt in (formatos or list(FORMATOS_TODO)):
            extension = _EXTENSION.get(fmt, "." + fmt.lower())
            sufijo = "_R12" if fmt == "DXF_R12" else ""
            destino = os.path.join(carpeta,
                                   base + sufijo + extension)
            try:
                opciones = {"version": "R12"} if fmt == "DXF_R12" \
                    else None
                clave = "DXF" if fmt == "DXF_R12" else fmt
                archivos[fmt] = self.export(context, clave, destino,
                                            opciones)
            except Exception as exc:  # noqa: BLE001 — por formato
                errores[fmt] = str(getattr(exc, "message", None)
                                   or exc)
        return {"carpeta": carpeta, "base": base,
                "archivos": archivos, "errores": errores}


__all__ = ["ExportService", "FORMATOS_TODO"]
