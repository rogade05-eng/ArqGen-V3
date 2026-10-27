"""P2 de la comparación Architechtures (v3.31.0): DXF R12 ASCII y
COSTE LIGADO AL CHECK.

* DXF R12: el exportador DXF gana ``version="R12"`` — entities
  clásicas (LINE/ARC/TEXT, SIN LWPOLYLINE que R12 no conoce), modelspace
  con un bloque por nivel y cabecera AC1009 — la máxima compatibilidad
  con CAD viejos, CNC y visores; el R2010 de siempre queda intacto.
* Coste ligado al check: los tres informes de validación llevan la
  instantánea del presupuesto PRECONS activo (services/coste_informe.py,
  SOLO LECTURA vía ``latest()``, nunca ``ensure_active()``): si no hay
  presupuesto con renglones NO se inventa nada.

Valores esperados calculados con el catálogo oficial: el renglón
011111 x 500 cuesta 13 405.00 CUP directos (test_105).
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase

from services.architecture_service import ArchitectureService

REAL_CODE = "precons_iii_rospres_330"


def _service(context):
    from services.precons_budget_service import PreconsBudgetService
    service = PreconsBudgetService(context)
    service.load_ruleset(REAL_CODE)
    return service


class TestBaseGeo(ARQGenTestCase):
    """Proyecto con un local de 10x6, una puerta y una ventana."""

    def setUp(self):
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("r12.arqgen"), name="R12")
        self.arq = ArchitectureService(self.context)
        self.nivel = self.arq.create_level("PB", 0.0, 3.0)
        muros = (((0.0, 0.0), (10.0, 0.0)),
                 ((10.0, 0.0), (10.0, 6.0)),
                 ((10.0, 6.0), (0.0, 6.0)),
                 ((0.0, 6.0), (0.0, 0.0)))
        self.muros = [self.arq.create_wall(self.nivel.code, a, b, 0.2)
                      for a, b in muros]
        self.arq.create_space(self.nivel.code, "Sala R12", "LIVING_ROOM",
                              [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0),
                               (0.0, 6.0)])
        self.arq.create_opening("DOOR", self.muros[0].code, 0.9, 2.1,
                                offset_m=1.0)
        self.arq.create_opening("WINDOW", self.muros[1].code, 1.2, 1.2,
                                offset_m=2.0)

    def _exportar(self, path, **kwargs):
        from exporters.dxf_exporter import DXFExporter
        return DXFExporter().export(self.context, path, **kwargs)

    def _leer(self, path):
        with open(path, "r", encoding="cp437", errors="replace") as fh:
            return fh.read()


class TestDXFR12(TestBaseGeo):
    """El exportador R12: AC1009, LINE/ARC/TEXT y cero LWPOLYLINE."""

    def test_r12_cabecera_ac1009_y_entidades_clasicas(self):
        ruta = self._exportar(self.project_path("r12.dxf"),
                              version="R12")
        texto = self._leer(ruta)
        self.assertIn("$ACADVER", texto)
        self.assertIn("AC1009", texto)
        self.assertNotIn("LWPOLYLINE", texto)
        self.assertIn("LINE", texto)
        self.assertIn("ARC", texto)   # arco de giro de la puerta
        self.assertIn("TEXT", texto)  # rótulos del local
        self.assertIn("ARQ-WALL", texto)

    def test_r2010_queda_intacto(self):
        ruta = self._exportar(self.project_path("r2010.dxf"))
        texto = self._leer(ruta)
        self.assertIn("AC1024", texto)
        self.assertIn("LWPOLYLINE", texto)

    def test_r12_ascii_legible(self):
        ruta = self._exportar(self.project_path("ascii.dxf"),
                              version="R12")
        with open(ruta, "rb") as fh:
            bruto = fh.read()
        # ASCII: todo el archivo decodifica como texto sin NUL ni
        # cabecera binaria (el binario de DXF empieza con "AutoCAD
        # Binary DXF")
        self.assertFalse(bruto.startswith(b"AutoCAD Binary"))
        self.assertNotIn(b"\x00", bruto[:4096])

    def test_r12_dos_niveles_en_modelspace(self):
        self.arq.create_level("PA", 3.2, 3.0)
        texto = self._leer(self._exportar(
            self.project_path("r12_2n.dxf"), version="R12"))
        self.assertIn("PLANTA_PB", texto)
        self.assertIn("PLANTA_PA", texto)

    def test_sin_geometria_error_amable(self):
        context = self.application.create_project(
            self.project_path("vacio.arqgen"), name="Vacío")
        from exporters.dxf_exporter import DXFExporter
        from core.errors import ExportError
        with self.assertRaises(ExportError):
            DXFExporter().export(context,
                                 self.project_path("nada.dxf"),
                                 version="R12")


class TestExportServiceYCLI(TestBaseGeo):
    """El servicio y la CLI pasan la versión al exportador."""

    def test_export_service_opcion_version(self):
        from services.export_service import ExportService
        ruta = self.project_path("svc.dxf")
        ExportService().export(self.context, "DXF", ruta,
                               {"version": "R12"})
        self.assertIn("AC1009", self._leer(ruta))

    def test_cli_flag_r12(self):
        from app import cli
        parser = cli._build_parser()
        args = parser.parse_args(
            ["export", "proyecto.arqgen", "--format", "dxf",
             "--out", "salida.dxf", "--level", "PB", "--r12"])
        self.assertTrue(args.r12)
        args2 = parser.parse_args(
            ["export", "proyecto.arqgen", "--format", "dxf",
             "--out", "salida.dxf"])
        self.assertFalse(args2.r12)


class TestCosteLigadoAlCheck(ARQGenTestCase):
    """La instantánea SOLO LECTURA del presupuesto activo."""

    def _proyecto(self, nombre="coste.arqgen"):
        return self.application.create_project(
            self.project_path(nombre), name="Coste")

    def test_sin_presupuesto_devuelve_none_y_no_crea(self):
        context = self._proyecto()
        from services.coste_informe import instantanea_coste
        self.assertIsNone(instantanea_coste(context))
        # la instantánea NO crea presupuesto: sigue sin haber
        servicio = _service(context)
        self.assertIsNone(servicio.latest())

    def test_presupuesto_vacio_devuelve_none(self):
        context = self._proyecto("vacio2.arqgen")
        servicio = _service(context)
        servicio.create("Vacío")
        from services.coste_informe import instantanea_coste
        self.assertIsNone(instantanea_coste(context))

    def test_instantanea_con_renglones_oficiales(self):
        context = self._proyecto()
        servicio = _service(context)
        servicio.add_item("011111", 500)
        instantanea = None
        from services.coste_informe import instantanea_coste
        instantanea = instantanea_coste(context)
        self.assertIsNotNone(instantanea)
        self.assertEqual(instantanea["renglones"], 1)
        self.assertEqual(instantanea["moneda"], "CUP")
        totales = servicio.totals()
        self.assertAlmostEqual(instantanea["total"],
                               totales["total"], places=2)
        self.assertAlmostEqual(instantanea["directo"], 13405.0,
                               places=2)
        self.assertAlmostEqual(
            instantanea["indirectos"],
            totales["indirect"] + totales["transport"], places=2)

    def test_area_y_coste_por_m2(self):
        context = self._proyecto("area.arqgen")
        arq = ArchitectureService(context)
        nivel = arq.create_level("PB", 0.0, 3.0)
        for a, b in (((0.0, 0.0), (4.0, 0.0)), ((4.0, 0.0), (4.0, 5.0)),
                     ((4.0, 5.0), (0.0, 5.0)), ((0.0, 5.0), (0.0, 0.0))):
            arq.create_wall(nivel.code, a, b, 0.2)
        arq.create_space(nivel.code, "Local 20", "LIVING_ROOM",
                         [(0.0, 0.0), (4.0, 0.0), (4.0, 5.0),
                          (0.0, 5.0)])
        servicio = _service(context)
        servicio.add_item("011111", 500)
        from services.coste_informe import instantanea_coste
        instantanea = instantanea_coste(context)
        self.assertAlmostEqual(instantanea["area_m2"], 20.0, places=1)
        self.assertAlmostEqual(instantanea["total_por_m2"],
                               round(instantanea["total"] / 20.0, 2),
                               places=2)

    def test_adjuntar_coste_al_informe(self):
        context = self._proyecto("adj.arqgen")
        servicio = _service(context)
        servicio.add_item("011111", 500)
        from services.coste_informe import adjuntar_coste
        informe = {"hallazgos": []}
        bloque = adjuntar_coste(context, informe)
        self.assertIn("coste", informe)
        self.assertIn("TOTAL", bloque)
        bloque.encode("cp1252")
        # sin presupuesto: cadena vacía y el informe sin la clave
        context2 = self._proyecto("adj2.arqgen")
        informe2 = {"hallazgos": []}
        self.assertEqual(adjuntar_coste(context2, informe2), "")
        self.assertNotIn("coste", informe2)

    def test_informe_html_renderiza_el_coste(self):
        from exporters.informe_html import informe_html
        html = informe_html({
            "edificacion": "Casa",
            "hallazgos": [],
            "coste": {"fuente": "presupuesto PRECONS III activo",
                      "moneda": "CUP", "renglones": 2,
                      "directo": 1000.0, "transporte": 50.0,
                      "indirectos": 105.0, "beneficio": 115.5,
                      "total": 1270.5, "area_m2": 20.0,
                      "total_por_m2": 63.53,
                      "nota": "coste informativo"},
        }, "Con coste")
        self.assertIn("Coste del proyecto", html)
        self.assertIn("1 270.50", html)
        self.assertIn("63.53", html)
        self.assertIn("CUP", html)

    def test_informe_html_sin_coste_no_dibuja_seccion(self):
        from exporters.informe_html import informe_html
        html = informe_html({"hallazgos": []}, "Sin coste")
        self.assertNotIn("Coste del proyecto", html)

    def test_bloque_coste_cp1252(self):
        from services.coste_informe import texto_bloque_coste
        texto = texto_bloque_coste({
            "fuente": "presupuesto PRECONS III activo", "moneda": "CUP",
            "renglones": 3, "directo": 13405.0, "transporte": 100.0,
            "indirectos": 202.0, "beneficio": 222.2, "total": 13929.2,
            "area_m2": 20.0, "total_por_m2": 696.46, "nota": "informativo"})
        texto.encode("cp1252")
        self.assertIn("COSTE DEL PROYECTO", texto)
        self.assertIn("13 929.20 CUP", texto)
        self.assertIn("coste por m2: 696.46 CUP", texto)
        # sin coste: cadena vacía
        self.assertEqual(texto_bloque_coste({}), "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
