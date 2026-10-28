"""EXPORTAR TODO A BIM (v3.48.0) — IFC + DXF de todo lo generado.

La petición del usuario era literal: «no tengo una manera de exportar
todo lo generado a un formato BIM ó IFC, ó dxf». La sonda end-to-end
(los 5 caminos de generación) probó que el pipeline ya existía PERO:

  1. la TORRE EN Y y la RADIAL con «trazar muros» revientaban con
     ARQ-DOM-048 «El muro tiene longitud nula» (costuras del contorno
     con vértices duplicados de longitud 0.0): sin muros no hay BIM
     completo que exportar;
  2. los IfcSpace salían con altura fija 3.0 m aunque el nivel fuera
     de 2.7/3.2/4.0 m (los visores BIM mostraban mal las alturas);
  3. no había UN gesto que exportara TODO: había que exportar formato
     a formato desde el menú.

Cobertura:
  * motor: Y y radial con muros aplican (regresión del DOM-048);
    el contorno de la Y no lleva costuras degeneradas; dedupe unitario
  * paquete: exportar_todo escribe IFC + DXF R2010 + DXF R12 + JSON +
    CSV + XLSX + SVG en una carpeta; proyecto vacío degrada con
    gracia (errores por formato, sin excepción); zonas = 2 storeys
  * IFC: los espacios heredan la altura del nivel (3.2 m)
  * GUI: el menú «Exportar TODO (BIM + planos)» y el botón del
    asistente «Exportar BIM (IFC+DXF)» están cableados
"""

from __future__ import annotations

import os
import re
import unittest

from core import APP_VERSION
from domain import desde_dibujo as dd
from domain import radial as rd
from tests.base import ARQGenTestCase

CONTORNO = [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)]


def _hospital_y():
    return dd.programa_edificacion([
        {"space_type": "VESTIBULE", "cantidad": 1},
        {"space_type": "WARD", "cantidad": 10},
        {"space_type": "NURSE_STATION", "cantidad": 1},
        {"space_type": "BATHROOM", "cantidad": 4},
    ], "Hospital en Y")


class TestMurosDegenerados(ARQGenTestCase):
    """El DOM-048 que bloqueaba el BIM de la Y y la radial."""

    def test_torre_y_con_muros_aplica(self):
        aj = rd.plan_y(_hospital_y(), radio_nucleo=7.5,
                       largo_ala=18.0, ancho_ala=11.0, n_alas=3,
                       corredor_m=1.6, cabecera_m=4.0)
        ctx = self.application.create_project(
            self.project_path("y46.arqgen"), name="y46")
        res = dd.aplicar_plan(ctx, aj, {"trazar_muros": True,
                                        "mobiliario": False,
                                        "nombre_edificio": "Torre Y"})
        self.assertGreater(int(res["muros"]), 100)
        self.assertGreaterEqual(len(res["espacios"]), 20)
        ctx.close()

    def test_radial_con_muros_aplica(self):
        prog = dd.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "BEDROOM", "cantidad": 12},
            {"space_type": "BATHROOM", "cantidad": 6}], "Torre")
        aj = rd.plan_radial(prog, radio_ext=14.0, radio_nucleo=3.0,
                            sectores=8, corredor_m=1.6)
        ctx = self.application.create_project(
            self.project_path("r46.arqgen"), name="r46")
        res = dd.aplicar_plan(ctx, aj, {"trazar_muros": True,
                                        "nombre_edificio": "Torre radial"})
        self.assertGreater(int(res["muros"]), 500)
        ctx.close()

    def test_contorno_y_sin_costuras_degeneradas(self):
        aj = rd.plan_y(_hospital_y(), radio_nucleo=7.5, n_alas=3)
        v = aj["forma"]["vertices"]
        for i in range(len(v)):
            a = v[i]
            b = v[(i + 1) % len(v)]
            largo = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            self.assertGreaterEqual(largo, 1e-4,
                                    f"costura degenerada en {i}: {a} {b}")

    def test_dedupe_unitario(self):
        limpia = rd._dedup_poligonal(
            [(0.0, 0.0), (0.0, 0.0), (4.0, 0.0), (4.0, 3.0),
             (0.0, 3.0), (0.0, 0.0)])
        self.assertEqual(limpia, [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0),
                                  (0.0, 3.0)])


class TestExportarTodo(ARQGenTestCase):
    """El paquete BIM + planos en una carpeta (v3.48.0)."""

    def _aplicar_casa(self, ctx):
        prog = dd.programa_quick(
            "sala, cocina, 2 dormitorios, bano", "casa")
        aj = dd.ajustar(prog, CONTORNO, ajuste="ideal")
        aj["altura_nivel_m"] = 3.2
        dd.aplicar_plan(ctx, aj, {"nombre_edificio": "Casa B"})

    def test_paquete_completo(self):
        from services.export_service import ExportService
        ctx = self.application.create_project(
            self.project_path("pkg.arqgen"), name="Bundle test")
        self._aplicar_casa(ctx)
        salida = os.path.join(self.tmp, "salida")
        res = ExportService().exportar_todo(ctx, salida)
        self.assertEqual(sorted(res["archivos"]),
                         ["CSV", "DXF", "DXF_R12", "IFC", "JSON",
                          "SVG", "XLSX"])
        self.assertEqual(res["errores"], {})
        self.assertEqual(res["base"], "Bundle_test")
        for fmt, ruta in res["archivos"].items():
            self.assertTrue(os.path.isfile(ruta), fmt)
            self.assertGreater(os.path.getsize(ruta), 100, fmt)
        self.assertTrue(res["archivos"]["DXF"].endswith(".dxf"))
        self.assertTrue(res["archivos"]["DXF_R12"].endswith("_R12.dxf"))
        ctx.close()

    def test_paquete_proyecto_vacio_degrada_con_gracia(self):
        from services.export_service import ExportService
        ctx = self.application.create_project(
            self.project_path("vacio.arqgen"), name="Vacio")
        res = ExportService().exportar_todo(
            ctx, os.path.join(self.tmp, "sal2"))
        self.assertIn("DXF", res["errores"])
        self.assertIn("No hay geometría", res["errores"]["DXF"])
        for fmt in ("IFC", "JSON", "CSV", "XLSX"):
            self.assertIn(fmt, res["archivos"])
        ctx.close()

    def test_paquete_zonas_dos_storeys(self):
        from services.export_service import ExportService
        comp = dd.ajustar_zonas(_hospital_y(), [
            {"contorno": [(0, 0), (30, 0), (30, 12), (0, 12)],
             "rol": "ala norte"},
            {"contorno": [(0, 14), (26, 14), (26, 26), (0, 26)],
             "rol": "ala sur"}], ajuste="ideal")
        ctx = self.application.create_project(
            self.project_path("zonas.arqgen"), name="Zonas46")
        dd.aplicar_zonas(ctx, comp, {"nombre_edificio": "Hospital alas",
                                     "mobiliario": False})
        res = ExportService().exportar_todo(
            ctx, os.path.join(self.tmp, "sal3"),
            formatos=["IFC", "DXF"])
        self.assertEqual(res["errores"], {})
        with open(res["archivos"]["IFC"], encoding="utf-8") as fh:
            contenido = fh.read()
        self.assertEqual(contenido.count("IFCBUILDINGSTOREY("), 2)
        self.assertGreaterEqual(contenido.count("IFCSPACE("), 10)
        ctx.close()

    def test_ifc_espacios_con_altura_del_nivel(self):
        from services.export_service import ExportService
        ctx = self.application.create_project(
            self.project_path("alt.arqgen"), name="Altura 3 2")
        self._aplicar_casa(ctx)
        res = ExportService().exportar_todo(
            ctx, os.path.join(self.tmp, "sal4"), formatos=["IFC"])
        with open(res["archivos"]["IFC"], encoding="utf-8") as fh:
            contenido = fh.read()
        # :g formatea 3.0 como "3" (el defecto antiguo) y 3.2 como
        # "3.2": los espacios del nivel de 3.2 m ya NO salen como "3"
        profundidades = re.findall(
            r"IFCEXTRUDEDAREASOLID\([^)]*,([0-9.eE+-]+)\)", contenido)
        self.assertIn("3.2", profundidades)
        ctx.close()

    def test_gui_cableada(self):
        ruta = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui", "app_window.py")
        with open(ruta, "r", encoding="utf-8") as fh:
            fuente = fh.read()
        self.assertIn("Exportar TODO (BIM + planos)", fuente)
        self.assertIn("exportar_todo_paquete", fuente)
        self.assertIn("_dd_exportar_bim", fuente)
        self.assertIn("Exportar BIM (IFC+DXF)", fuente)


class TestContratos(unittest.TestCase):

    def test_version_3460(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
