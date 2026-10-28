"""PATIO DOMÉSTICO Y CHAFLANES v3.43.1 — space_dna.json +
domain/desde_dibujo.py.

Los defectos descubiertos con las NUEVAS imágenes de referencia del
usuario (9 vistas: fachadas, formas y distribución interna; las 3 de
planta se sondearon contra el motor):

  * «patio» del quick-spec apuntaba al PATIO ESCOLAR (mín 100, pref
    300 m2, lado 10 m): la villa 50x90 lanzaba ARQ-DDI-011 y en la
    villa 50x100 el patio se comía el 64 % de la planta. Ahora el
    quick trae el PATIO_DOMESTICO (mín 4, pref 9, lado 2.0) y el
    escolar queda para los programas de educación.
  * los CHAFLANES a 45 grados estaban DORMIDOS sin «selección» de
    locales: el margen se medía contra los renglones del programa que
    el empaquetado ya había crecido (margen 0 siempre) y el caso Z de
    v3.43.0 disparaba por casualidad (2 dormitorios colisionaban en el
    dict de pisos por código). Ahora el piso es el MÍNIMO DEL DNA del
    propio local: el corte nunca baja de la norma y dispara también
    sin selección (suite de hotel de 51 m2, villas).

Cobertura:
  * DNA: PATIO_DOMESTICO (4/9/2.0, ámbito vivienda) y PATIO escolar
    INTACTO (100/300/10.0); quick patio/2 patios
  * villas de las imágenes: 50x90 con 2 patios entra en 1 nivel; la
    50x100 sin el patio devorando la planta; chaflanes en la villa;
    mínimos del DNA respetados (sin reducción no hay baja)
  * chaflanes v3.43.1: la SUITE de 51 m2 SIN selección corta esquina,
    poligonales sanas (local 5 vértices, sala absorbiendo), el corte
    no baja del mínimo del DNA, el Z con selección sigue disparando,
    desactivables y documentadas en el informe
  * contratos: APP_VERSION 3.43.1 y renglones del usuario intactos
"""

from __future__ import annotations

import unittest

from core import APP_VERSION
from domain import desde_dibujo as dd

E_VILLA_90 = [(0.0, 0.0), (15.24, 0.0), (15.24, 27.43), (0.0, 27.43)]
F_VILLA_100 = [(0.0, 0.0), (15.24, 0.0), (15.24, 30.48), (0.0, 30.48)]
G_SUITE = [(0.0, 0.0), (4.67, 0.0), (4.67, 10.925), (0.0, 10.925)]
Z_REAL = [(0.0, 2.9), (2.6, 2.9), (2.6, 0.0), (6.5, 0.0), (6.5, 2.9),
          (3.9, 2.9), (3.9, 6.4), (5.5, 6.4), (5.5, 10.4), (0.0, 10.4)]

SEL_Z = ["BEDROOM", "BATHROOM", "KITCHEN", "LIVING_ROOM",
         "DINING_ROOM"]


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


# ---------------------------------------------------------------------------
# 1) DNA: PATIO DOMÉSTICO
# ---------------------------------------------------------------------------

class TestPatioDomesticoDNA(unittest.TestCase):

    def test_dna_patio_domestico_existe_y_es_de_vivienda(self):
        e = _dna_de("PATIO_DOMESTICO")
        self.assertEqual(e["name_es"], "Patio")
        self.assertEqual(float(e["minimum_area"]), 4.0)
        self.assertEqual(float(e["preferred_area"]), 9.0)
        self.assertEqual(float(e["minimum_width"]), 2.0)
        self.assertEqual((e.get("metadata") or {}).get("ambito"),
                         "vivienda")

    def test_patio_escolar_intacto(self):
        e = _dna_de("PATIO")
        self.assertEqual(e["name_es"], "Patio escolar")
        self.assertEqual(float(e["minimum_area"]), 100.0)
        self.assertEqual(float(e["preferred_area"]), 300.0)
        self.assertEqual(float(e["minimum_width"]), 10.0)

    def test_quick_patio_da_el_domestico(self):
        prog = dd.programa_quick("dormitorio, bano, cocina, sala, patio",
                                 "t178")
        r = next(r for r in prog["renglones"]
                 if r["space_type"] == "PATIO_DOMESTICO")
        self.assertEqual(r["nombre"], "Patio")
        self.assertEqual(float(r["area_m2"]), 9.0)
        self.assertEqual(float(r["area_min"]), 4.0)

    def test_quick_dos_patios(self):
        prog = dd.programa_quick("2 patios", "t178")
        patios = [r for r in prog["renglones"]
                  if r["space_type"] == "PATIO_DOMESTICO"]
        self.assertEqual(len(patios), 2)
        self.assertEqual([r["nombre"] for r in patios],
                         ["Patio", "Patio 2"])

    def test_el_mobiliario_no_amuebla_el_patio(self):
        from domain import mobiliario as mob
        piezas = mob.proponer_piezas("PATIO_DOMESTICO", 9.0)
        self.assertEqual(piezas, [])


# ---------------------------------------------------------------------------
# 2) LAS VILLAS DE LAS IMÁGENES DEL USUARIO
# ---------------------------------------------------------------------------

class TestVillasDeLasImagenes(unittest.TestCase):

    def test_villa_50x90_con_2_patios_cabe_en_1_nivel(self):
        # antes: 2 x Patio escolar 300 m2 -> ARQ-DDI-011 SIEMPRE
        prog = dd.programa_quick(
            "2 dormitorios, 3 banos, cocina, sala, comedor, estudio, "
            "garaje, 2 patios, 1 nivel", "t178")
        aj = dd.ajustar(prog, E_VILLA_90, encaje_estricto=True,
                        ajuste="ideal")
        self.assertEqual(aj["niveles"], 1)
        self.assertTrue(aj["dentro_del_contorno"])
        patios = [r for r in aj["reparto"][0]["locales"]
                  if r["space_type"] == "PATIO_DOMESTICO"]
        self.assertEqual(len(patios), 2)

    def test_villa_50x90_patios_domesticos_pequenos(self):
        prog = dd.programa_quick(
            "2 dormitorios, 3 banos, cocina, sala, comedor, estudio, "
            "garaje, 2 patios, 1 nivel", "t178")
        aj = dd.ajustar(prog, E_VILLA_90, encaje_estricto=True,
                        ajuste="estricto")
        patios = [r for r in aj["reparto"][0]["locales"]
                  if r["space_type"] == "PATIO_DOMESTICO"]
        self.assertTrue(patios)
        for p in patios:
            # patio de VILLA (franja de fondo completo), no el escolar
            self.assertLess(float(p["area_m2"]), 30.0,
                            "el patio no puede acercarse al escolar")

    def test_villa_50x100_patio_no_devora_la_planta(self):
        # antes: el Patio escolar (300 m2) ocupaba el 64 % del centro
        prog = dd.programa_quick(
            "3 dormitorios, 3 banos, cocina, sala, comedor, recibidor, "
            "patio, 1 nivel", "t178")
        aj = dd.ajustar(prog, F_VILLA_100, encaje_estricto=True,
                        ajuste="ideal")
        self.assertEqual(aj["niveles"], 1)
        self.assertTrue(aj["dentro_del_contorno"])
        nombres = [r["nombre"] for r in aj["reparto"][0]["locales"]]
        self.assertNotIn("Patio escolar", nombres)
        patio = next(r for r in aj["reparto"][0]["locales"]
                     if r["space_type"] == "PATIO_DOMESTICO")
        self.assertLess(float(patio["area_m2"]), 25.0)
        # la vivienda (dormitorios) no queda reducida a tiras insanas:
        # sin reducción, ningún local baja de su mínimo del DNA
        for r in aj["reparto"][0]["locales"]:
            self.assertGreaterEqual(
                float(r["area_m2"]),
                float(r.get("area_min") or 0.0) - 1e-6,
                f"{r['nombre']} quedó por debajo de la norma")

    def test_la_villa_trae_chaflanes_hacia_la_sala(self):
        prog = dd.programa_quick(
            "3 dormitorios, 3 banos, cocina, sala, comedor, recibidor, "
            "patio, 1 nivel", "t178")
        aj = dd.ajustar(prog, F_VILLA_100, encaje_estricto=True,
                        ajuste="ideal")
        self.assertTrue(aj["chaflanes"],
                        "la villa de las imágenes debe abrir esquinas")


# ---------------------------------------------------------------------------
# 3) CHAFLANES v3.43.1 (el defecto de los pisos mutados)
# ---------------------------------------------------------------------------

class TestChaflanesV3431(unittest.TestCase):

    def _suite(self, **kw):
        prog = dd.programa_quick("dormitorio, bano, sala", "t178")
        return dd.ajustar(prog, G_SUITE, encaje_estricto=True, **kw)

    def test_suite_51m2_chaflan_sin_seleccion(self):
        # el DEFECTO: sin «selección» los chaflanes no disparaban
        aj = self._suite(ajuste="ideal")
        self.assertTrue(aj["chaflanes"],
                        "el corte debe disparar SIN selección de "
                        "locales (piso = mínimo del DNA)")
        h = aj["chaflanes"][0]
        self.assertGreaterEqual(float(h["cateto_m"]), 0.45)
        self.assertGreater(float(h["perdida_m2"]), 0.0)

    def test_poligonales_sanas_y_sala_absorbe(self):
        aj = self._suite(ajuste="ideal")
        locales = aj["reparto"][0]["locales"]
        cortados = [r for r in locales if r.get("chaflan")]
        self.assertTrue(cortados)
        for r in cortados:
            poly = r["poligono"]
            self.assertEqual(len(poly), 5)
            for a, b in zip(poly, poly[1:] + poly[:1]):
                self.assertGreater(
                    (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2, 1e-12,
                    "arista nula en la poligonal del chaflán")
        sala = next(r for r in locales
                    if r["space_type"] == "LIVING_ROOM")
        self.assertGreater(len(sala.get("poligono") or []), 4,
                           "la sala absorbe el triángulo (poligonal "
                           "de más vértices)")

    def test_el_corte_no_baja_del_minimo_del_dna(self):
        aj = self._suite(ajuste="ideal")
        for r in aj["reparto"][0]["locales"]:
            piso = float(r.get("area_min") or 0.0)
            self.assertGreaterEqual(
                float(r["area_m2"]), piso - 1e-6,
                f"{r['nombre']} quedó por debajo de la norma "
                f"({piso:.2f} m2)")

    def test_z_con_seleccion_sigue_disparando(self):
        prog = dd.programa_quick(
            "2 dormitorios, bano, cocina, comedor, sala", "t178")
        aj = dd.ajustar(prog, Z_REAL, encaje_estricto=True,
                        seleccion=SEL_Z)
        self.assertTrue(aj["chaflanes"])
        self.assertTrue(any(r.get("poligono")
                            for r in aj["reparto"][0]["locales"]))

    def test_chaflanes_desactivables(self):
        aj = self._suite(ajuste="ideal", chaflanes=False)
        self.assertEqual(aj["chaflanes"], [])
        self.assertFalse(any(r.get("poligono")
                             for r in aj["reparto"][0]["locales"]))

    def test_el_informe_documenta_los_chaflanes(self):
        aj = self._suite(ajuste="ideal")
        texto = dd.texto_ajuste(aj)
        self.assertIn("CHAFLANES A 45 GRADOS", texto)
        self.assertIn("cateto", texto)
        texto.encode("cp1252")

    def test_los_renglones_del_usuario_quedan_intactos(self):
        prog = dd.programa_quick("dormitorio, bano, sala", "t178")
        antes = [(r["nombre"], float(r["area_m2"]))
                 for r in prog["renglones"]]
        dd.ajustar(prog, G_SUITE, encaje_estricto=True)
        despues = [(r["nombre"], float(r["area_m2"]))
                   for r in prog["renglones"]]
        self.assertEqual(antes, despues)


# ---------------------------------------------------------------------------
# 4) CONTRATOS
# ---------------------------------------------------------------------------

class TestContratosV3431(unittest.TestCase):

    def test_version_coherente_con_v3431(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
