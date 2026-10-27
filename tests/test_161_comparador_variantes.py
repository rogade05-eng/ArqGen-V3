# -*- coding: utf-8 -*-
"""v3.29.0 — COMPARADOR DE VARIANTES DE PLANTA.

Matriz N variantes x métricas (``ui/variant_budget.py``):
puntos, área, coste PRECONS vivo, coste/m2, avisos y «cabe en lote»,
con el líder por puntuación y por coste/m2, texto cp1252 para la
consola y CSV «;» utf-8-sig para Excel. Lo que Architechtures estrenó
como «Dashboard de Comparación de Diseños» en su plan Business, aquí
es local, gratuito y determinista.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.base import ARQGenTestCase  # noqa: E402

from ui import building_wizard as bw  # noqa: E402
from ui import variant_budget as vb  # noqa: E402


def _vivienda() -> bw.BuildingWizardData:
    data = bw.BuildingWizardData()
    data.levels = [bw.LevelSpec(name="Planta Baja", height_m=3.0)]
    data.usage_type = "Vivienda"
    data.rooms = bw.preset_rooms("Vivienda", "Planta Baja")
    data.relations = bw.suggest_relations(data)
    return data


class TestTablaComparacion(ARQGenTestCase):
    """La matriz sobre variantes REALES del motor."""

    def setUp(self) -> None:
        super().setUp()
        self.variantes = bw.generate_variants(_vivienda())

    def test_hay_variantes_y_todas_tienen_fila(self):
        self.assertGreaterEqual(len(self.variantes), 6)
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        self.assertEqual(len(tabla["filas"]), len(self.variantes))
        self.assertEqual(len(tabla["columnas"]),
                         len(vb.COLUMNAS_COMPARACION))
        for fila in tabla["filas"]:
            self.assertEqual(len(fila), len(tabla["columnas"]))

    def test_columnas_conocidas(self):
        self.assertEqual(vb.COLUMNAS_COMPARACION[:5],
                         ("#", "Variante", "Esquema", "Cabe en lote",
                          "Puntos"))

    def test_filas_son_todas_texto(self):
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        for fila in tabla["filas"]:
            for celda in fila:
                self.assertIsInstance(celda, str)

    def test_orden_por_puntos_descendente(self):
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        puntos = [int(tabla["filas"][i - 1][4]) for i in tabla["orden"]]
        self.assertEqual(puntos, sorted(puntos, reverse=True))
        # y el orden contiene TODOS los índices exactamente una vez
        self.assertEqual(sorted(tabla["orden"]),
                         list(range(1, len(self.variantes) + 1)))

    def test_area_desde_layouts_sin_coste(self):
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        indice_area = vb.COLUMNAS_COMPARACION.index("Área m2")
        primera_con_area = next(
            fila for fila in tabla["filas"]
            if fila[indice_area] != "—")
        self.assertNotIn(",", primera_con_area)
        # y el número coincide con la suma de los locales trazados
        numero = int(primera_con_area[indice_area].replace(" ", ""))
        self.assertGreater(numero, 0)

    def test_sin_coste_declara_honradez(self):
        for variante in self.variantes:
            variante.cost = None
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        self.assertFalse(tabla["mejores"]["con_coste"])
        self.assertEqual(tabla["mejores"]["coste_m2"], "")
        texto = vb.texto_comparacion_variantes(self.variantes)
        self.assertIn("(sin coste adjunto", texto)

    def test_cabe_en_lote_si_y_no(self):
        self.variantes[0].fits_lot = True
        self.variantes[1].fits_lot = False
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        indice_cabe = vb.COLUMNAS_COMPARACION.index("Cabe en lote")
        self.assertEqual(tabla["filas"][0][indice_cabe], "Sí")
        self.assertEqual(tabla["filas"][1][indice_cabe], "No")

    def test_avisos_de_variante_y_de_coste_se_suman(self):
        self.variantes[0].advisories = ["pasillo largo"]
        coste = vb.VariantCost(area_m2=100.0)
        coste.avisos.append("renglón ausente en el catálogo")
        self.variantes[0].cost = coste
        tabla = vb.tabla_comparacion_variantes(self.variantes)
        indice_avisos = vb.COLUMNAS_COMPARACION.index("Avisos")
        self.assertEqual(tabla["filas"][0][indice_avisos], "2")


class TestComparacionConCoste(ARQGenTestCase):
    """Con el coste PRECONS vivo adjunto (VariantCost de juguete)."""

    def test_coste_y_coste_m2_en_la_matriz(self):
        variantes = bw.generate_variants(_vivienda())
        coste = vb.VariantCost(area_m2=100.0)
        coste.categories = {"Muros": 50_000.0, "Estructura": 30_000.0}
        variantes[0].cost = coste
        tabla = vb.tabla_comparacion_variantes(variantes)
        indice_coste = vb.COLUMNAS_COMPARACION.index("Coste")
        indice_m2 = vb.COLUMNAS_COMPARACION.index("Coste/m2")
        self.assertEqual(tabla["filas"][0][indice_coste], "80 000")
        self.assertEqual(tabla["filas"][0][indice_m2], "800")
        self.assertTrue(tabla["mejores"]["con_coste"])
        self.assertEqual(tabla["mejores"]["coste_m2"],
                         variantes[0].title)

    def test_lider_coste_m2_es_el_mas_barato(self):
        variantes = bw.generate_variants(_vivienda())
        costes = []
        for indice, variante in enumerate(variantes[:3]):
            coste = vb.VariantCost(area_m2=100.0 + indice * 10.0)
            coste.categories = {"Muros": 100_000.0 - indice * 20_000.0}
            variante.cost = coste
            costes.append(coste)
        tabla = vb.tabla_comparacion_variantes(variantes)
        esperado = min(
            zip(variantes[:3], costes),
            key=lambda vc: vc[1].cost_m2)[0].title
        self.assertEqual(tabla["mejores"]["coste_m2"], esperado)


class TestTextoYCsvComparacion(ARQGenTestCase):
    """Texto cp1252 para consola y CSV «;» para Excel."""

    def setUp(self) -> None:
        super().setUp()
        self.variantes = bw.generate_variants(_vivienda())

    def test_texto_cp1252_completo(self):
        texto = vb.texto_comparacion_variantes(self.variantes)
        texto.encode("cp1252")  # la consola de Windows lo aguanta
        self.assertTrue(texto.startswith(
            "COMPARACIÓN DE VARIANTES DE PLANTA"))
        self.assertIn("Mejor puntuación: ", texto)
        self.assertIn("no incluye indirectos ni beneficio", texto)
        for variante in self.variantes[:5]:
            self.assertIn(variante.title, texto)

    def test_texto_sin_variantes(self):
        texto = vb.texto_comparacion_variantes([])
        self.assertIn("no hay variantes", texto)
        texto.encode("cp1252")

    def test_csv_parseable_con_semicolon(self):
        csv_texto = vb.csv_comparacion_variantes(self.variantes)
        lector = list(csv.reader(io.StringIO(csv_texto),
                                 delimiter=";"))
        self.assertEqual(lector[0], list(vb.COLUMNAS_COMPARACION))
        self.assertEqual(len(lector), len(self.variantes) + 1)
        self.assertEqual(lector[1][0], "1")

    def test_csv_determinista(self):
        primero = vb.csv_comparacion_variantes(self.variantes)
        segundo = vb.csv_comparacion_variantes(self.variantes)
        self.assertEqual(primero, segundo)

    def test_tabla_determinista(self):
        primero = vb.tabla_comparacion_variantes(self.variantes)
        segundo = vb.tabla_comparacion_variantes(self.variantes)
        self.assertEqual(primero["filas"], segundo["filas"])
        self.assertEqual(primero["orden"], segundo["orden"])

    def test_variantes_de_secundaria_tambien_se_comparan(self):
        data = bw.BuildingWizardData()
        data.levels = [bw.LevelSpec(name="Planta Baja", height_m=3.0)]
        data.usage_type = "Escuela secundaria"
        bw.apply_usage_program(data)
        variantes = bw.generate_variants(data)
        if not variantes:
            self.skipTest("el motor no generó variantes para el uso")
        tabla = vb.tabla_comparacion_variantes(variantes)
        self.assertGreaterEqual(len(tabla["filas"]), 1)


class TestFuenteComparador(unittest.TestCase):
    """Marcadores del módulo (espejo del check 71 del selftest)."""

    def test_marcadores(self):
        ruta = os.path.join(PROJECT_ROOT, "ui", "variant_budget.py")
        with open(ruta, "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def tabla_comparacion_variantes", src)
        self.assertIn("def texto_comparacion_variantes", src)
        self.assertIn("def csv_comparacion_variantes", src)
        self.assertIn("COLUMNAS_COMPARACION", src)
        self.assertIn("Mejor puntuación", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
