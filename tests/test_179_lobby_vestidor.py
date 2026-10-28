"""LOBBY Y VESTIDOR v3.44.0 (FASE A) — space_dna.json +
domain/desde_dibujo.py.

Las villas de las imágenes de referencia usan LOBBY distribuidor
(VESTIBULE a escala de vivienda grande) y VESTIDOR/W.I.C junto al
dormitorio; el vocabulario no los traía:

  * VESTIDOR nuevo en el DNA (mín 2.0, pref 4.0, lado 1.2, ámbito
    vivienda) SIN tocar el DRESSING_ROOM de personal (6-12),
  * palabras del quick: vestidor/wic/closet -> VESTIDOR y
    lobby/foyer -> VESTIBULE (con plurales),
  * el umbral del modo sala distribuidora es PARAMETRIZABLE
    (``distribuidora_max_m2``): villas grandes con lobby piden el
    modo sin pasillo (60 por defecto, intacto),
  * sin sala, el HUB de los chaflanes es el LOBBY (VESTIBULE).

Cobertura:
  * DNA: VESTIDOR (2/4/1.2) y DRESSING_ROOM intacto (6/12)
  * quick: vestidor, vestidores, wic, closet, lobby, foyer
  * distribuidora_max_m2: 100 m2 con 120 -> distribuidora; sin el
    parámetro -> pasillo; con 50 en una casa de 40 -> distribuidora
  * hub: unidad con vestíbulo y sin sala corta chaflán hacia el lobby
  * contratos: APP_VERSION 3.44.0 y round-trip del PlanRequest
"""

from __future__ import annotations

import unittest

from core import APP_VERSION
from domain import desde_dibujo as dd

CASA_100 = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
CASA_40 = [(0.0, 0.0), (6.4, 0.0), (6.4, 6.4), (0.0, 6.4)]
UNIDAD_LOBBY = [(0.0, 0.0), (6.0, 0.0), (6.0, 7.5), (0.0, 7.5)]


def _dna_de(tipo: str) -> dict:
    import json
    from app.paths import resource_path
    ruta = resource_path("knowledge", "space_dna.json")
    with open(ruta, encoding="utf-8") as f:
        dna = json.load(f)
    for e in dna["space_types"]:
        if e.get("space_type") == tipo:
            return e
    raise AssertionError(f"{tipo} no está en el DNA")


class TestVestidorDNA(unittest.TestCase):

    def test_dna_vestidor_domestico(self):
        e = _dna_de("VESTIDOR")
        self.assertEqual(e["name_es"], "Vestidor (W.I.C)")
        self.assertEqual(float(e["minimum_area"]), 2.0)
        self.assertEqual(float(e["preferred_area"]), 4.0)
        self.assertEqual(float(e["minimum_width"]), 1.2)
        self.assertEqual((e.get("metadata") or {}).get("ambito"),
                         "vivienda")

    def test_dressing_room_de_personal_intacto(self):
        e = _dna_de("DRESSING_ROOM")
        self.assertEqual(float(e["minimum_area"]), 6.0)
        self.assertEqual(float(e["preferred_area"]), 12.0)

    def test_version_dna_v3440(self):
        import json
        from app.paths import resource_path
        ruta = resource_path("knowledge", "space_dna.json")
        with open(ruta, encoding="utf-8") as f:
            dna = json.load(f)
        self.assertIn("v3.44.0", str(dna.get("version")))


class TestQuickWords(unittest.TestCase):

    def test_vestidor_y_plural(self):
        prog = dd.programa_quick(
            "2 dormitorios, vestidor, bano, sala, 1 nivel", "t")
        tipos = [r["space_type"] for r in prog["renglones"]]
        self.assertIn("VESTIDOR", tipos)

    def test_wic_y_closet(self):
        for palabra in ("wic", "closet"):
            prog = dd.programa_quick(
                f"dormitorio, {palabra}, bano, 1 nivel", "t")
            tipos = [r["space_type"] for r in prog["renglones"]]
            self.assertIn("VESTIDOR", tipos, palabra)

    def test_lobby_y_foyer_son_vestibulo(self):
        for palabra in ("lobby", "foyer", "lobbys"):
            prog = dd.programa_quick(
                f"{palabra}, 2 dormitorios, bano, cocina, sala, "
                "1 nivel", "t")
            tipos = [r["space_type"] for r in prog["renglones"]]
            self.assertIn("VESTIBULE", tipos, palabra)


class TestDistribuidoraParametrizable(unittest.TestCase):

    def _casa(self) -> dict:
        return dd.programa_quick(
            "3 dormitorios, 2 banos, cocina, sala, comedor, "
            "1 nivel", "casa")

    def test_100m2_sin_parametro_usa_pasillo(self):
        aj = dd.ajustar(self._casa(), CASA_100, encaje_estricto=True,
                        ajuste="ideal")
        self.assertFalse(aj.get("sala_distribuidora"))

    def test_100m2_con_tope_120_es_distribuidora(self):
        aj = dd.ajustar(self._casa(), CASA_100, encaje_estricto=True,
                        ajuste="ideal", distribuidora_max_m2=120.0)
        self.assertTrue(aj.get("sala_distribuidora"))

    def test_tope_menor_mantiene_distribuidora(self):
        casa_chica = dd.programa_quick(
            "dormitorio, bano, cocina, sala, 1 nivel", "chica")
        aj = dd.ajustar(casa_chica, CASA_40, encaje_estricto=True,
                        ajuste="ideal", distribuidora_max_m2=50.0)
        self.assertTrue(aj.get("sala_distribuidora"))

    def test_aviso_menciona_el_tope(self):
        aj = dd.ajustar(self._casa(), CASA_100, encaje_estricto=True,
                        ajuste="ideal", distribuidora_max_m2=120.0)
        self.assertTrue(any("120" in a and "DISTRIBUIDORA" in a
                            for a in aj.get("avisos", [])))

    def test_plan_request_round_trip(self):
        datos = {
            "contorno": CASA_100,
            "programa": self._casa(),
            "distribuidora_max_m2": 120.0,
            "chaflan_propio": True,
        }
        pet = dd.PlanRequest.from_dict(datos)
        self.assertEqual(pet.distribuidora_max_m2, 120.0)
        self.assertTrue(pet.chaflan_propio)
        ciclo = dd.PlanRequest.from_dict(pet.to_dict())
        self.assertEqual(ciclo.distribuidora_max_m2, 120.0)
        self.assertTrue(ciclo.chaflan_propio)
        self.assertIsNone(
            dd.PlanRequest.from_dict({}).distribuidora_max_m2)


class TestHubLobbyChaflan(unittest.TestCase):

    def test_unidad_con_lobby_sin_sala_corta_hacia_lobby(self):
        prog = dd.programa_quick(
            "dormitorio, bano, lobby, 1 nivel", "u")
        aj = dd.ajustar(prog, UNIDAD_LOBBY, encaje_estricto=True,
                        ajuste="ideal", chaflanes=True)
        cortes = [c for c in aj.get("chaflanes", [])
                  if c.get("tipo") != "propio"]
        self.assertTrue(cortes)
        self.assertTrue(any(c.get("sala")
                            and "Vest" in str(c.get("sala"))
                            for c in cortes))


class TestContratos(unittest.TestCase):

    def test_version_3440(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
