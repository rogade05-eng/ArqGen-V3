"""MULTI-ALA Y MULTI-UNIDAD v3.44.0 (FASE C) — domain/desde_dibujo.py.

El hospital en alas, la residencia en Y y el edificio tipo de
viviendas repetidas de las imágenes de referencia no se podían
generar: el motor rellena UN contorno con UN programa. v3.44 añade:

  * ``ajustar_zonas``: reparte UN programa entre N contornos (alas)
    con reparto determinista por déficit de área; los hubs públicos
    (vestíbulo/entrada/sala) van al ala principal; ARQ-DDI-012 con el
    rol del ala si una ala no admite su parte.
  * ``repartir_rejilla``: edificio tipo: rejilla 2 bandas + corredor
    central con la MISMA unidad repetida (planta tipo del edificio
    plurifamiliar ruso).
  * ``aplicar_zonas``: UN edificio; cada ala es su nivel con sufijo
    de rol; en la rejilla TODAS las celdas comparten la planta.

Cobertura:
  * zonas: compuesto con totales sumados, hubs al principal,
    determinismo, errores (< 2 zonas; ala que no cabe -> 012 con rol)
  * rejilla: celdas iguales, pasillo central, dentro del contorno,
    errores (filas != 2; contorno no rectangular)
  * aplicar_zonas con proyecto real (alas y rejilla)
"""

from __future__ import annotations

import unittest

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from tests.base import ARQGenTestCase

ALA_NORTE = [(0.0, 0.0), (30.0, 0.0), (30.0, 12.0), (0.0, 12.0)]
ALA_SUR = [(0.0, 14.0), (26.0, 14.0), (26.0, 26.0), (0.0, 26.0)]
REJILLA = [(0.0, 0.0), (24.0, 0.0), (24.0, 11.5), (0.0, 11.5)]
NO_RECT = [(0.0, 0.0), (10.0, 0.0), (8.0, 8.0), (0.0, 10.0)]


def _hospital() -> dict:
    return dd.programa_edificacion([
        {"space_type": "WARD", "cantidad": 10},
        {"space_type": "NURSE_STATION", "cantidad": 1},
        {"space_type": "BATHROOM", "cantidad": 4},
    ], "Hospital en Y")


def _unidad() -> dict:
    return dd.programa_quick(
        "2 dormitorios, bano, cocina, sala, 1 nivel", "tipo")


class TestAjustarZonas(unittest.TestCase):

    def test_compuesto_con_totales(self):
        comp = dd.ajustar_zonas(_hospital(), [
            {"contorno": ALA_NORTE, "rol": "ala norte"},
            {"contorno": ALA_SUR, "rol": "ala sur"}], ajuste="ideal")
        self.assertEqual(comp["tipo"], "zonas")
        self.assertEqual(len(comp["zonas"]), 2)
        self.assertGreater(comp["totales"]["area_contorno"], 600.0)
        self.assertTrue(comp["dentro_del_contorno"])
        self.assertGreater(comp["totales"]["aprovechamiento_pct"],
                           50.0)

    def test_hubs_van_al_ala_principal(self):
        comp = dd.ajustar_zonas(_hospital(), [
            {"contorno": ALA_NORTE, "rol": "ala norte"},
            {"contorno": ALA_SUR, "rol": "principal"}],
            ajuste="ideal")
        principal = [z for z in comp["zonas"]
                     if z["rol"] == "principal"][0]
        norte = [z for z in comp["zonas"]
                 if z["rol"] == "ala norte"][0]
        # la estación de enfermería (hub del programa hospitalario)
        # la asigna el déficit, pero el SALA/VESTÍBULO/ENTRADA nunca:
        # con este programa no hay hubs: ambos lados reciben WARDs
        self.assertTrue(norte["renglones"])
        self.assertTrue(principal["renglones"])

    def test_hubs_con_vestibulo_al_principal(self):
        prog = dd.programa_edificacion([
            {"space_type": "VESTIBULE", "cantidad": 1},
            {"space_type": "BEDROOM", "cantidad": 8},
            {"space_type": "BATHROOM", "cantidad": 4},
        ], "Residencia")
        comp = dd.ajustar_zonas(prog, [
            {"contorno": ALA_NORTE, "rol": "ala norte"},
            {"contorno": ALA_SUR, "rol": "principal"}],
            ajuste="ideal")
        principal = [z for z in comp["zonas"]
                     if z["rol"] == "principal"][0]
        self.assertIn("Vestíbulo", " ".join(principal["renglones"]))

    def test_determinista(self):
        a = dd.ajustar_zonas(_hospital(), [
            {"contorno": ALA_NORTE}, {"contorno": ALA_SUR}],
            ajuste="ideal")
        b = dd.ajustar_zonas(_hospital(), [
            {"contorno": ALA_NORTE}, {"contorno": ALA_SUR}],
            ajuste="ideal")
        self.assertEqual([z["renglones"] for z in a["zonas"]],
                         [z["renglones"] for z in b["zonas"]])

    def test_menos_de_2_zonas_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            dd.ajustar_zonas(_hospital(),
                             [{"contorno": ALA_NORTE}])
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_ala_que_no_cabe_lanza_012_con_rol(self):
        prog = dd.programa_edificacion([
            {"space_type": "WARD", "cantidad": 12}], "Grande")
        with self.assertRaises(DomainError) as cm:
            dd.ajustar_zonas(prog, [
                {"contorno": ALA_NORTE, "rol": "ala norte"},
                {"contorno": [(0.0, 14.0), (4.0, 14.0),
                              (4.0, 18.0), (0.0, 18.0)],
                 "rol": "ala chica"}], ajuste="ideal")
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")
        self.assertIn("ala chica", str(cm.exception.message))


class TestRepartirRejilla(unittest.TestCase):

    def test_edificio_tipo_3x2(self):
        comp = dd.repartir_rejilla(_unidad(), REJILLA, columnas=3,
                                   ajuste="ideal")
        self.assertEqual(comp["tipo"], "rejilla")
        self.assertEqual(len(comp["zonas"]), 6)
        rej = comp["rejilla"]
        self.assertEqual((rej["columnas"], rej["filas"]), (3, 2))
        self.assertGreater(rej["celda_ancho_m"], 0.0)
        self.assertTrue(comp["pasillo_central"])
        self.assertEqual(comp["pasillo_central"]["space_type"],
                         "CORRIDOR")
        self.assertTrue(comp["dentro_del_contorno"])

    def test_celdas_iguales(self):
        comp = dd.repartir_rejilla(_unidad(), REJILLA, columnas=3,
                                   ajuste="ideal")
        primeras = [tuple(z["renglones"]) for z in comp["zonas"]]
        self.assertEqual(len(set(primeras)), 1)

    def test_filas_distinta_de_2_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            dd.repartir_rejilla(_unidad(), REJILLA, columnas=3,
                                filas=3)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")

    def test_contorno_no_rectangular_lanza_012(self):
        with self.assertRaises(DomainError) as cm:
            dd.repartir_rejilla(_unidad(), NO_RECT, columnas=2)
        self.assertEqual(cm.exception.code, "ARQ-DDI-012")


class TestAplicarZonas(ARQGenTestCase):

    def test_aplicar_alas(self):
        comp = dd.ajustar_zonas(_hospital(), [
            {"contorno": ALA_NORTE, "rol": "ala norte"},
            {"contorno": ALA_SUR, "rol": "ala sur"}], ajuste="ideal")
        ctx = self.application.create_project(
            self.project_path("v44a.arqgen"), name="v44a")
        res = dd.aplicar_zonas(ctx, comp,
                               {"nombre_edificio": "Hospital Y",
                                "mobiliario": False})
        self.assertGreaterEqual(res["niveles"], 1)
        self.assertTrue(any("· ala norte" in n
                            for n in res["niveles_nombres"]))
        self.assertTrue(any("· ala sur" in n
                            for n in res["niveles_nombres"]))

    def test_aplicar_rejilla_comparte_planta(self):
        comp = dd.repartir_rejilla(_unidad(), REJILLA, columnas=3,
                                   ajuste="ideal")
        ctx = self.application.create_project(
            self.project_path("v44r.arqgen"), name="v44r")
        res = dd.aplicar_zonas(ctx, comp,
                               {"nombre_edificio": "Edificio tipo",
                                "mobiliario": False})
        # UNA planta para las 6 celdas + corredor central
        self.assertEqual(len(res["niveles_nombres"]), 1)
        self.assertGreaterEqual(res["espacios"], 6 * 5)


class TestContratos(unittest.TestCase):

    def test_version_3440(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
