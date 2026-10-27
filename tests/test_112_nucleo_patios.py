"""Asistente de edificación v2.5.0: FORMAS COMPUESTAS + PATIO CENTRAL
COMBINADOS y NÚCLEO RÍGIDO EN ESQUINAS.

Lo pedido por el usuario: «pulir más el motor (variante con forma
compuesta + patio central combinados, esquinas con núcleo rígido)».
"""

from __future__ import annotations

import itertools
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (
    BuildingWizardData, CORE_ALWAYS, CORE_AUTO, CORE_MODES, CORE_NEVER,
    CORE_TYPE, LevelSpec, PLAN_SHAPES,
)


def _programa(usage: str, niveles: int = 1,
              terrain: str = "Regular (plano)") -> BuildingWizardData:
    """Datos con el programa del uso social cargado en cada nivel."""
    data = BuildingWizardData()
    data.levels = [LevelSpec(f"Nivel {i + 1}", 3.0)
                   for i in range(niveles)]
    data.usage_type = usage
    data.terrain_type = terrain
    data.rooms = []
    for lv in data.levels:
        data.rooms.extend(bw.preset_rooms(usage, lv.name))
    data.relations = bw.suggest_relations(data)
    return data


def _solapes(pieces):
    """Solapes físicos entre piezas colocadas (debe ser vacío)."""
    bad = []
    for a, b in itertools.combinations(pieces, 2):
        ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
        oy = min(a.y + a.d, b.y + b.d) - max(a.y, b.y)
        if ox > 1e-6 and oy > 1e-6:
            bad.append((a.name, b.name))
    return bad


def _variante(data, scheme, mirror=False):
    variants = bw.generate_variants(data)
    return next(v for v in variants
                if v.scheme == scheme and v.mirror == mirror)


def _patio_central(layout):
    return [p for p in layout.all_rooms
            if p.is_corridor and p.space_type == bw.PATIO_TYPE
            and p.name.startswith("Patio central")]


PATIO_COMBOS = ("en_L_patio", "en_T_patio", "en_H_patio",
                "en_cruz_patio", "articulada_patio")


class TestEsquemasConPatioCentral(ARQGenTestCase):
    """Cinco formas compuestas que ahora abrazan un patio central."""

    def test_catalogo_de_esquemas(self):
        self.assertEqual(len(bw.SCHEME_LABELS), 14)
        for scheme in PATIO_COMBOS:
            self.assertIn(scheme, bw.SCHEME_LABELS)
            self.assertIn(scheme, bw.SCHEME_DESCRIPTIONS)
            self.assertIn(scheme, bw.SHAPED_SCHEMES)
            self.assertTrue(bw.SCHEME_LABELS[scheme].strip())

    def test_envoltorio_en_h_patio_trae_patio_y_galeria(self):
        data = _programa("Hospital")
        variant = _variante(data, "en_H_patio")
        layout = variant.layouts[0]
        patios = _patio_central(layout)
        self.assertEqual(len(patios), 1)
        patio = patios[0]
        # Patio habitable entre las dos barras (ancho ≥ 2,5 m).
        self.assertGreaterEqual(patio.w, 2.5)
        self.assertGreaterEqual(patio.d, 3.0)
        # Los locales pegados al patio tienen puerta a su galería.
        self.assertTrue(any("galería del patio" in d.note
                            for d in layout.doors))
        self.assertFalse(_solapes(layout.all_rooms))

    def test_en_cruz_patio_con_brazos_al_patio(self):
        data = _programa("Hospital")
        variant = _variante(data, "en_cruz_patio")
        layout = variant.layouts[0]
        patios = _patio_central(layout)
        self.assertEqual(len(patios), 1)
        # Las columnas de la cruz cuelgan a los lados del patio.
        patio = patios[0]
        pegados = [p for p in layout.rooms
                   if abs(p.x + p.w - patio.x) < 1e-6
                   or abs(p.x - (patio.x + patio.w)) < 1e-6]
        self.assertGreaterEqual(len(pegados), 1)
        self.assertFalse(_solapes(layout.all_rooms))

    def test_en_t_patio_sustituye_la_espina(self):
        data = _programa("Consultorio médico")
        variant = _variante(data, "en_T_patio")
        layout = variant.layouts[0]
        self.assertEqual(len(_patio_central(layout)), 1)
        self.assertFalse(any("espina" in p.name
                             for p in layout.all_rooms))
        self.assertTrue(any("galería del patio" in d.note
                            for d in layout.doors))
        self.assertFalse(_solapes(layout.all_rooms))

    def test_en_l_patio_abraza_la_esquina(self):
        for usage in ("Vivienda", "Policlínico", "Comercio"):
            data = _programa(usage, niveles=2)
            for mirror in (False, True):
                variant = _variante(data, "en_L_patio", mirror)
                for layout in variant.layouts:
                    self.assertEqual(len(_patio_central(layout)), 1)
                    self.assertFalse(_solapes(layout.all_rooms))

    def test_articulada_patio_eslabon_verde(self):
        data = _programa("Centro comunitario")
        variant = _variante(data, "articulada_patio")
        layout = variant.layouts[0]
        self.assertEqual(len(_patio_central(layout)), 1)
        self.assertFalse(_solapes(layout.all_rooms))

    def test_patio_como_esquema_tambien_sigue_trazando(self):
        # El patio simple de dos crujías no cambió (puertas «→ patio»).
        data = _programa("Escuela primaria")
        variant = _variante(data, "patio")
        layout = variant.layouts[0]
        self.assertTrue(any("→ patio" in d.note for d in layout.doors))
        self.assertFalse(_solapes(layout.all_rooms))

    def test_afinidad_y_clima_cubren_los_nuevos_esquemas(self):
        for forma in PLAN_SHAPES:
            for scheme in PATIO_COMBOS:
                value = bw.shape_affinity(forma, scheme)
                self.assertGreaterEqual(value, 0.0, (forma, scheme))
                self.assertLessEqual(value, 1.0, (forma, scheme))
        for scheme in PATIO_COMBOS:
            self.assertGreaterEqual(
                bw._climate_affinity(scheme, "Cálido húmedo (tropical "
                                                  "lluvioso)"), 0.99)

    def test_variants_deterministas_con_patio(self):
        data = _programa("Policlínico")
        first = bw.generate_variants(data)
        second = bw.generate_variants(data)
        self.assertEqual([v.key for v in first], [v.key for v in second])
        self.assertEqual([v.score for v in first],
                         [v.score for v in second])

    def test_barrido_usos_sin_solapes_ni_aislados(self):
        for usage in ("Vivienda", "Escuela primaria", "Policlínico",
                      "Hospital", "Centro comunitario", "Comercio"):
            data = _programa(usage, niveles=2,
                             terrain="Irregular con pendiente fuerte")
            for scheme in PATIO_COMBOS:
                variant = _variante(data, scheme)
                for layout in variant.layouts:
                    self.assertFalse(
                        _solapes(layout.all_rooms),
                        f"{usage}/{scheme}: {layout.level_name}")
                    # Todo local llega a un corredor/patio o encadena
                    # con otro ya conectado (el ensamblado lo garantiza
                    # con puertas o avisos de aislado).
                    aislados = [a for a in layout.advisories
                                if "aislado" in a]
                    self.assertEqual(aislados, [],
                                     f"{usage}/{scheme}")


class TestNucleoRigidoEnEsquinas(ARQGenTestCase):
    """La caja de servicios (escalera + baños + ductos) en esquinas."""

    def test_catalogo_y_valores_por_defecto(self):
        self.assertEqual(len(CORE_MODES), 3)
        self.assertEqual(CORE_AUTO, CORE_MODES[0])
        data = BuildingWizardData()
        self.assertEqual(data.core_mode, CORE_AUTO)
        self.assertIn("core_mode", bw.building_field_names())

    def test_decision_automatica_siempre_nunca(self):
        data = _programa("Vivienda")           # 1 nivel, terreno regular
        self.assertFalse(bw.core_wanted(data))  # automática: no hace falta
        data.core_mode = CORE_ALWAYS
        self.assertTrue(bw.core_wanted(data))   # siempre, aunque no haga falta
        data.core_mode = CORE_NEVER
        self.assertFalse(bw.core_wanted(data))
        data2 = _programa("Vivienda", niveles=2)
        self.assertTrue(bw.core_wanted(data2))  # automática: varios niveles
        data2.terrain_type = "Irregular con pendiente fuerte"
        data3 = _programa("Vivienda")
        data3.terrain_type = "Irregular con pendiente fuerte"
        self.assertTrue(bw.core_wanted(data3))  # automática: desnivel

    def test_validacion_rechaza_modo_desconocido(self):
        data = BuildingWizardData()
        data.core_mode = "En el tejado"
        errores = bw.validate_step(0, data)
        self.assertTrue(any("núcleo rígido" in e.lower()
                            for e in errores))
        data.core_mode = CORE_NEVER
        self.assertEqual([e for e in bw.validate_step(0, data)
                          if "núcleo" in e.lower()], [])

    def test_nucleo_en_esquina_en_el_trazado_lineal(self):
        data = _programa("Escuela primaria")
        data.core_mode = CORE_ALWAYS
        layouts, _adv = bw.build_layout(data, with_core=True)
        rooms = layouts[0].rooms
        core = next(p for p in rooms if p.space_type == CORE_TYPE)
        # Esquina frontal derecha: remata la fila sobre la fachada.
        self.assertAlmostEqual(core.x + core.w,
                               max(p.x + p.w for p in rooms))
        self.assertAlmostEqual(core.y, 0.0)
        self.assertFalse(core.with_window)
        # Tiene su puerta al pasillo.
        self.assertTrue(any("Núcleo rígido" in d.note
                            for d in layouts[0].doors))
        self.assertFalse(_solapes(layouts[0].all_rooms))

    def test_nucleo_llega_a_todas_las_variantes(self):
        data = _programa("Hospital", niveles=2)
        data.core_mode = CORE_ALWAYS
        for scheme in ("lineal", "doble_crujia", "patio", "en_L",
                       "en_T", "en_U", "en_H", "en_cruz", "articulada",
                       "en_H_patio", "en_cruz_patio"):
            variant = _variante(data, scheme)
            for layout in variant.layouts:
                cores = [p for p in layout.rooms
                         if p.space_type == CORE_TYPE]
                self.assertEqual(len(cores), 1, scheme)
                # El núcleo toca la envolvente del trazado (esquina).
                min_x, min_y, max_x, max_y = bw._bounds_of_layouts(
                    [layout])
                self.assertTrue(
                    abs(cores[0].x - min_x) < 1e-6
                    or abs(cores[0].x + cores[0].w - max_x) < 1e-6
                    or abs(cores[0].y - min_y) < 1e-6
                    or abs(cores[0].y + cores[0].d - max_y) < 1e-6,
                    f"{scheme}: núcleo fuera de la envolvente")

    def test_nucleo_vetado_no_aparece(self):
        data = _programa("Hospital", niveles=2)
        data.core_mode = CORE_NEVER
        variant = _variante(data, "lineal")
        self.assertFalse(any(p.space_type == CORE_TYPE
                             for p in variant.layouts[0].rooms))

    def test_metadata_y_resumen_mencionan_el_nucleo(self):
        data = _programa("Hospital", niveles=2)
        meta = bw._building_metadata(data)
        self.assertEqual(meta["edificacion"]["nucleo_rigido"]["modo"],
                         CORE_AUTO)
        self.assertTrue(meta["edificacion"]["nucleo_rigido"]["colocado"])
        variant = _variante(data, "lineal")
        texto = bw.step_summary(data, variant=variant)
        self.assertIn("Núcleo rígido", texto)
        data.core_mode = CORE_NEVER
        texto2 = bw.step_summary(data)
        self.assertIn("Núcleo rígido: no se coloca", texto2)

    def test_aviso_cuando_se_veta_siendo_recomendable(self):
        data = _programa("Vivienda", niveles=2)
        data.core_mode = CORE_NEVER
        avisos = bw.site_advisories(data)
        self.assertTrue(any("núcleo rígido" in a.lower()
                            for a in avisos))
        data.core_mode = CORE_ALWAYS
        self.assertFalse(any("no colocar núcleo" in a.lower()
                             for a in bw.site_advisories(data)))

    def test_data_from_values_carga_el_modo(self):
        data = BuildingWizardData()
        errores = bw.data_from_values(0, {
            "name": "Casa prueba",
            "core_mode": "Sí, núcleo en esquinas",
        }, data)
        self.assertEqual(errores, [])
        self.assertEqual(data.core_mode, "Sí, núcleo en esquinas")

    def test_plan_con_nucleo_en_el_trazado_clasico(self):
        data = _programa("Oficina", niveles=2)
        plan, layouts, _adv = bw.build_plan(data)
        spaces = [params for op, params in plan if op == "SPACE"]
        nucleos = [s for s in spaces
                   if s["space_type"] == CORE_TYPE]
        self.assertEqual(len(nucleos), 2)  # uno por nivel con locales


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
