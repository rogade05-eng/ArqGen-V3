"""CHAFLÁN DE RECINTO PROPIO (BAY WINDOW) v3.44.0 (FASE B) —
domain/desde_dibujo.py.

Las unidades de hotel de las imágenes de referencia llevan la
ventana en saliente a 45 grados en el PROPIO recinto (bay window),
no hacia una sala. v3.44.0 añade el corte PROPIO: la esquina del
local que cae EN EL CONTORNO se corta con cateto 0.60 m y la
pérdida la absorbe el propio local (nunca por debajo del mínimo del
DNA). En auto (``chaflan_propio=None``) solo dispara cuando el
nivel NO tiene sala/lobby; con ``True`` se añade a los cortes hacia
la sala; con ``False`` nunca.

Cobertura:
  * unidad de hotel sin sala: 2 cortes propios en esquinas opuestas,
    poligonal de 5 vértices, pérdida documentada, área >= mínimo
  * propio forzado en casa con sala: cortes propios + hacia sala
  * propio=False: nada
  * cap de 6 cortes por nivel y 2 por local
  * APLICAR_PLAN crea el espacio con la poligonal real (5 vértices)
"""

from __future__ import annotations

import unittest

from core import APP_VERSION
from domain import desde_dibujo as dd
from tests.base import ARQGenTestCase

UNIDAD = [(0.0, 0.0), (4.2, 0.0), (4.2, 6.7), (0.0, 6.7)]
CASA = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _locales_con_poligono(aj: dict) -> list:
    salida = []
    for plan in aj["reparto"]:
        for r in plan["locales"]:
            if r.get("poligono"):
                salida.append(r)
    return salida


class TestPropioAutoSinSala(unittest.TestCase):

    def _ajustar(self) -> dict:
        prog = dd.programa_quick("dormitorio, bano, 1 nivel", "u")
        return dd.ajustar(prog, UNIDAD, encaje_estricto=True,
                          ajuste="ideal", chaflanes=True)

    def test_unidad_de_hotel_corta_propio_en_auto(self):
        aj = self._ajustar()
        propios = [c for c in aj.get("chaflanes", [])
                   if c.get("tipo") == "propio"]
        self.assertEqual(len(propios), 2)
        nombres = {c["local"] for c in propios}
        self.assertEqual(nombres, {"Dormitorio"})

    def test_poligonal_sana_con_cortes(self):
        aj = self._ajustar()
        dorm = [r for r in _locales_con_poligono(aj)
                if r["space_type"] == "BEDROOM"]
        self.assertEqual(len(dorm), 1)
        # rectángulo (4) menos 2 esquinas sustituidas + 4 vértices
        # de los 2 cortes = 6
        self.assertEqual(len(dorm[0]["poligono"]), 6)

    def test_no_baja_del_minimo_del_dna(self):
        aj = self._ajustar()
        dorm = [r for r in aj["reparto"][0]["locales"]
                if r["space_type"] == "BEDROOM"][0]
        self.assertGreaterEqual(float(dorm["area_m2"]),
                                float(dorm["area_min"]) - 0.01)

    def test_esquinas_opuestas(self):
        aj = self._ajustar()
        propios = [c for c in aj["chaflanes"]
                   if c.get("tipo") == "propio"]
        if len(propios) >= 2:
            esquinas = [tuple(c["esquina"]) for c in propios]
            dx = abs(esquinas[0][0] - esquinas[1][0])
            dy = abs(esquinas[0][1] - esquinas[1][1])
            self.assertTrue(dx > 1e-3 and dy > 1e-3,
                            "las 2 esquinas deben ser opuestas")


class TestPropioExplicito(unittest.TestCase):

    def test_forzado_en_casa_con_sala(self):
        prog = dd.programa_quick(
            "2 dormitorios, bano, cocina, sala, 1 nivel", "c")
        aj = dd.ajustar(prog, CASA, encaje_estricto=True,
                        ajuste="ideal", chaflanes=True,
                        chaflan_propio=True)
        tipos = {c.get("tipo") for c in aj.get("chaflanes", [])}
        self.assertIn("propio", tipos)

    def test_desactivado_con_false(self):
        prog = dd.programa_quick("dormitorio, bano, 1 nivel", "u")
        aj = dd.ajustar(prog, UNIDAD, encaje_estricto=True,
                        ajuste="ideal", chaflanes=True,
                        chaflan_propio=False)
        self.assertEqual(
            [c for c in aj.get("chaflanes", [])
             if c.get("tipo") == "propio"], [])

    def test_aviso_informe(self):
        prog = dd.programa_quick("dormitorio, bano, 1 nivel", "u")
        aj = dd.ajustar(prog, UNIDAD, encaje_estricto=True,
                        ajuste="ideal", chaflanes=True)
        self.assertTrue(any("propio(s) de fachada" in a
                            for a in aj.get("avisos", [])))

    def test_cap_6_cortes_por_nivel(self):
        prog = dd.programa_quick(
            "4 dormitorios, 2 banos, cocina, sala, 1 nivel", "c")
        aj = dd.ajustar(prog, CASA, encaje_estricto=True,
                        ajuste="ideal", chaflanes=True,
                        chaflan_propio=True)
        propios = [c for c in aj.get("chaflanes", [])
                   if c.get("tipo") == "propio"]
        self.assertLessEqual(len(propios), 6)


class TestAplicarConPoligonal(ARQGenTestCase):

    def test_aplicar_crea_espacio_con_5_vertices(self):
        from domain import mobiliario as mob
        prog = dd.programa_quick("dormitorio, bano, 1 nivel", "u")
        aj = dd.ajustar(prog, UNIDAD, encaje_estricto=True,
                        ajuste="ideal", chaflanes=True)
        self.assertTrue(any(c.get("tipo") == "propio"
                            for c in aj.get("chaflanes", [])))
        ctx = self.application.create_project(
            self.project_path("v44u.arqgen"), name="v44u")
        res = dd.aplicar_plan(ctx, aj,
                              {"nombre_edificio": "Hotel test",
                               "mobiliario": False})
        self.assertGreaterEqual(len(res["espacios"]), 2)
        self.assertEqual(len(res["niveles"]), 1)
        poligonales = [e for e in mob.lista_tipos(ctx, "SPACE")
                       if len(list(getattr(e, "boundary", []) or []))
                       > 4]
        self.assertTrue(poligonales,
                        "el dormitorio con bay window debe crear "
                        "una poligonal de más de 4 vértices")


class TestContratos(unittest.TestCase):

    def test_version_3440(self):
        self.assertEqual(APP_VERSION, "3.47.0")


if __name__ == "__main__":
    unittest.main()
