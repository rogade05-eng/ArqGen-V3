"""EDICIONES REGIONALES DE NEUFERT v2.8.0: el libro adaptado por región.

Lo pedido: «vamos aprovechar todo lo que se pueda del neufert, y si
podemos ajustar valores específicos del libro (ediciones por región)
mejor».

Cobertura de estas pruebas:

* Registro regional (domain/neufert.py): set_region con fusión profunda,
  available_regions, reset, región inexistente cae a la base y la BASE
  NUNCA SE CORROMPE (deepcopy).
* Ediciones instaladas (Cuba, México, Argentina, Colombia): cada una
  ajusta lo suyo — techos, luz de ventanas, aleros, estacionamiento,
  espesores de muro — y conserva lo universal (Blondel, pasillos de
  camillas, aseos).
* Asistente (ui/building_wizard.py): campo neufert_region, validación,
  avisos regionales (luz 1/5 en el trópico, alero, estacionamiento),
  bloque «edicion_regional» del metadata, evacuación y sección propia
  del uso, resumen con la edición.
* Defaults que solo suben al cambiar de región.
* GUI: combo «Edición regional Neufert» en el paso 1 que re-aplica los
  valores del libro y sincroniza los campos del paso 4.
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (
    BuildingWizardData,
    LevelSpec,
    NEUFERT_REGION_BASE,
)

from app.paths import resource_path
from domain.neufert import (
    REGIONS_RESOURCE_DIR,
    REGION_BASE,
    _deep_merge,
    get_registry,
    reset_registry,
)


def _programa(usage: str, level: str = "Planta Baja"
              ) -> BuildingWizardData:
    data = BuildingWizardData()
    data.levels = [LevelSpec(name=level, height_m=3.0)]
    data.usage_type = usage
    data.rooms = bw.preset_rooms(usage, level)
    data.relations = bw.suggest_relations(data)
    return data


def _base_ratios() -> dict:
    """Valores de la base del libro (para comprobar que no se tocan)."""
    reset_registry()
    registry = get_registry()
    return {
        "techo_hospital": registry.ceiling_for("Hospital"),
        "techo_vivienda": registry.ceiling_for("Vivienda"),
        "luz": registry.window_ratio(),
        "alero": registry.section("bioclimatica")["alero_recomendado_m"],
        "plaza": registry.parking()["plaza_estandar_m"],
    }


class TestRegistroRegional(ARQGenTestCase):
    """El registro carga regiones con fusión profunda sobre la base."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)

    def test_regiones_disponibles(self):
        registry = get_registry()
        regiones = registry.available_regions()
        codigos = {r["codigo"] for r in regiones}
        self.assertTrue({"cuba", "mexico", "argentina", "colombia"}
                        <= codigos)
        for info in regiones:
            self.assertTrue(info["nombre"])
            self.assertTrue(info["edicion"])
            self.assertTrue(info["archivo"].endswith(".json"))

    def test_base_es_la_region_por_defecto(self):
        registry = get_registry()
        self.assertTrue(registry.region_is_base())
        self.assertEqual(registry.region_code, REGION_BASE)
        self.assertEqual(registry.region_tag(), "")
        bloque = registry.region_block()
        self.assertEqual(bloque["codigo"], REGION_BASE)

    def test_cuba_activa_los_valores_tropicales(self):
        registry = get_registry()
        self.assertTrue(registry.set_region("cuba"))
        self.assertEqual(registry.region_name, "Cuba")
        self.assertTrue("edición Cuba" in registry.region_tag())
        self.assertAlmostEqual(registry.ceiling_for("Hospital"), 3.2)
        self.assertAlmostEqual(registry.ceiling_for("Vivienda"), 3.0)
        luz_min, luz_rec = registry.window_ratio()
        self.assertAlmostEqual(luz_min, 0.2)     # 1/5 del suelo
        self.assertAlmostEqual(luz_rec, 0.25)    # 1/4 del suelo
        bio = registry.section("bioclimatica")
        self.assertAlmostEqual(bio["alero_recomendado_m"], 1.2)
        self.assertAlmostEqual(bio["porche_m"], 2.4)   # el portal
        self.assertEqual(registry.parking()["plaza_estandar_m"],
                         "2.30x4.60")
        self.assertAlmostEqual(
            registry.section("puertas")["principal_vivienda_m"], 1.2)

    def test_cuba_conserva_lo_universal(self):
        """Lo que la edición no toca sigue siendo el libro."""
        registry = get_registry()
        registry.set_region("cuba")
        rule = registry.stair_rule("Hospital")
        self.assertTrue(rule.blondel_ok)
        self.assertAlmostEqual(rule.contrahuella_m, 0.16)
        self.assertAlmostEqual(rule.ancho_m, 1.8)
        self.assertAlmostEqual(registry.corridor_for("Hospital"), 2.4)
        self.assertAlmostEqual(registry.door_for("Hospital")[0], 1.2)
        self.assertTrue(registry.has("aseo_recuento"))
        self.assertTrue(registry.has("antropometria"))

    def test_mexico_techos_contenidos_y_block_de_14(self):
        registry = get_registry()
        registry.set_region("mexico")
        self.assertAlmostEqual(registry.ceiling_for("Vivienda"), 2.4)
        self.assertAlmostEqual(registry.ceiling_for("Hospital"), 2.7)
        self.assertAlmostEqual(
            registry.wall_thickness_for(
                "Mampostería de bloque + losa de vigueta", exterior=True),
            0.14)
        self.assertAlmostEqual(registry.ramp_max_percent(), 8.0)

    def test_argentina_ladrillo_de_18(self):
        registry = get_registry()
        registry.set_region("argentina")
        self.assertAlmostEqual(registry.ceiling_for("Vivienda"), 2.6)
        self.assertAlmostEqual(
            registry.wall_thickness_for(
                "Mampostería de bloque + losa de vigueta", exterior=True),
            0.18)

    def test_colombia_confinada_de_15(self):
        registry = get_registry()
        registry.set_region("colombia")
        self.assertAlmostEqual(registry.ceiling_for("Vivienda"), 2.5)
        self.assertAlmostEqual(
            registry.wall_thickness_for(
                "Mampostería de bloque + losa de vigueta", exterior=True),
            0.15)
        self.assertAlmostEqual(registry.ramp_max_percent(), 8.0)

    def test_region_inexistente_cae_a_la_base(self):
        registry = get_registry()
        registry.set_region("cuba")
        self.assertFalse(registry.set_region("brasil"))
        self.assertTrue(registry.region_is_base())
        self.assertAlmostEqual(registry.ceiling_for("Hospital"), 3.0)

    def test_la_base_nunca_se_corrompe(self):
        """Tras rondar todas las regiones, la base queda intacta."""
        originales = _base_ratios()
        registry = get_registry()
        for code in ("cuba", "mexico", "argentina", "colombia", "cuba",
                     "mexico"):
            registry.set_region(code)
        registry.reset_region()
        self.assertAlmostEqual(registry.ceiling_for("Hospital"),
                               originales["techo_hospital"])
        self.assertAlmostEqual(registry.ceiling_for("Vivienda"),
                               originales["techo_vivienda"])
        self.assertEqual(registry.window_ratio(), originales["luz"])
        self.assertEqual(
            registry.section("bioclimatica")["alero_recomendado_m"],
            originales["alero"])
        self.assertEqual(registry.parking()["plaza_estandar_m"],
                         originales["plaza"])

    def test_override_parcial_mantiene_el_resto_de_la_seccion(self):
        """La fusión es profunda: la región toca SOLO sus claves.

        México no toca la sección «aseos» y Cuba ajusta el ratio de
        luz de «ventanas» sin tocar el antepecho de la base.
        """
        reset_registry()
        registry = get_registry()
        base_aseos = registry.section("aseos")["bano_completo_min_m2"]
        base_antepecho = registry.section("ventanas")["antepecho_m"]
        registry.set_region("mexico")
        self.assertAlmostEqual(
            registry.section("aseos")["bano_completo_min_m2"],
            base_aseos)
        registry.set_region("cuba")
        self.assertAlmostEqual(
            registry.section("ventanas")["ratio_luz_minimo"], 0.2)
        self.assertAlmostEqual(
            registry.section("ventanas")["antepecho_m"], base_antepecho)

    def test_set_region_es_idempotente(self):
        registry = get_registry()
        self.assertTrue(registry.set_region("cuba"))
        primera = registry.window_ratio()
        self.assertTrue(registry.set_region("cuba"))
        self.assertEqual(registry.window_ratio(), primera)

    def test_blondel_universal_en_todas_las_regiones(self):
        registry = get_registry()
        regla_base = registry.stair_rule("Hospital")
        for code in ("cuba", "mexico", "argentina", "colombia"):
            registry.set_region(code)
            regla = registry.stair_rule("Hospital")
            self.assertEqual(regla.blondel_m, regla_base.blondel_m)
            self.assertEqual(regla.ancho_m, regla_base.ancho_m)

    def test_ficheros_de_region_completos(self):
        region_dir = resource_path(*REGIONS_RESOURCE_DIR)
        for name in ("cuba.json", "mexico.json", "argentina.json",
                     "colombia.json"):
            path = os.path.join(region_dir, name)
            self.assertTrue(os.path.isfile(path), name)
            import json
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["format"], "ARQ_GEN_NEUFERT_REGION")
            for key in ("code", "nombre", "edicion", "referencias",
                        "overrides"):
                self.assertIn(key, data, f"{name}: {key}")

    def test_deep_merge_funcion_pura(self):
        dst = {"a": {"x": 1, "y": 2}, "b": 1}
        _deep_merge(dst, {"a": {"x": 9, "z": 3}, "c": 4})
        self.assertEqual(dst, {"a": {"x": 9, "y": 2, "z": 3},
                               "b": 1, "c": 4})


class TestAsistenteRegional(ARQGenTestCase):
    """El asistente guarda la región y sus avisos citan la edición."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)

    def test_campo_y_validacion_de_la_region(self):
        data = BuildingWizardData()
        self.assertEqual(data.neufert_region, NEUFERT_REGION_BASE)
        self.assertIn("neufert_region", bw.building_field_names())
        data.neufert_region = "cuba"
        self.assertEqual(bw.validate_step(0, data), [])
        data.neufert_region = "brasil"
        self.assertTrue(any("edición regional" in e
                            for e in bw.validate_step(0, data)))

    def test_data_from_values_guarda_el_codigo(self):
        data = BuildingWizardData()
        bw.data_from_values(0, {"name": "Prueba", "neufert_region":
                                "cuba"}, data)
        self.assertEqual(data.neufert_region, "cuba")
        bw.data_from_values(0, {"name": "Prueba", "neufert_region":
                                ""}, data)
        self.assertEqual(data.neufert_region, "cuba")   # no se borra
        data2 = BuildingWizardData()
        bw.data_from_values(0, {"name": "Prueba"}, data2)
        self.assertEqual(data2.neufert_region, NEUFERT_REGION_BASE)

    def test_codigos_y_etiquetas_redondean(self):
        choices = bw.neufert_region_choices()
        self.assertEqual(choices[0][0], NEUFERT_REGION_BASE)
        self.assertGreaterEqual(len(choices), 5)
        for code, label in choices:
            self.assertEqual(bw.neufert_region_code(label), code)
            self.assertEqual(bw.neufert_region_label(code), label)
        self.assertEqual(bw.neufert_region_code("lo que sea"),
                         NEUFERT_REGION_BASE)
        self.assertEqual(bw.neufert_region_label("desconocido"),
                         "Base — 5.ª ed. en español")

    def test_avisos_citan_la_edicion(self):
        data = _programa("Hospital")
        data.neufert_region = "cuba"
        avisos = bw.neufert_advisories(data)
        self.assertTrue(avisos)
        self.assertTrue(any("(edición Cuba)" in a for a in avisos))
        data.neufert_region = NEUFERT_REGION_BASE
        self.assertFalse(any("(edición" in a
                             for a in bw.neufert_advisories(data)))

    def test_luz_1_5_en_el_tropico_y_1_8_en_la_base(self):
        data = _programa("Hospital")
        data.window_width_m = 1.4
        data.window_height_m = 1.2   # 1,68 m2 < 1/5 de 9 m2
        data.neufert_region = "cuba"
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("1/5" in a for a in avisos))
        data.neufert_region = NEUFERT_REGION_BASE
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("1/8" in a for a in avisos))

    def test_techo_hospitalario_por_region(self):
        data = _programa("Hospital")
        data.levels = [LevelSpec(name="Planta Baja", height_m=3.0)]
        data.neufert_region = "cuba"   # pide 3,20 m
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("3.20 m" in a and "edición Cuba" in a
                            for a in avisos))
        data.neufert_region = "mexico"   # pide 2,70 m: 3,0 sobra
        self.assertFalse(any("altura libre" in a
                             for a in bw.neufert_advisories(data)))

    def test_alero_recomendado_por_region(self):
        data = _programa("Vivienda")
        data.eaves_m = 0.6
        data.neufert_region = "cuba"   # pide 1,20 m
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("Alero" in a and "1.20 m" in a
                            for a in avisos))
        data.neufert_region = NEUFERT_REGION_BASE
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("Alero" in a and "el libro" in a
                            for a in avisos))
        # Con el alero del libro no hay aviso.
        data.eaves_m = 0.9
        self.assertFalse(any("Alero" in a
                             for a in bw.neufert_advisories(data)))

    def test_estacionamiento_de_la_edicion(self):
        data = _programa("Policlínico")
        data.neufert_region = "cuba"
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("2.30 × 4.60" in a and "5.50" in a
                            for a in avisos))
        data.neufert_region = NEUFERT_REGION_BASE
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("2.50 × 5.00" in a and "6.00" in a
                            for a in avisos))

    def test_normativa_block_lleva_la_edicion(self):
        data = _hospital_data()
        data.neufert_region = "cuba"
        bloque = bw.neufert_normativa_block(data)
        self.assertEqual(bloque["edicion_regional"]["codigo"], "cuba")
        self.assertEqual(bloque["edicion_regional"]["nombre"], "Cuba")
        self.assertTrue(bloque["edicion_regional"]["referencias"])
        self.assertAlmostEqual(
            bloque["altura_libre_recomendada_m"], 3.2)
        data.neufert_region = NEUFERT_REGION_BASE
        bloque = bw.neufert_normativa_block(data)
        self.assertEqual(bloque["edicion_regional"]["codigo"],
                         NEUFERT_REGION_BASE)
        self.assertAlmostEqual(
            bloque["altura_libre_recomendada_m"], 3.0)

    def test_normativa_block_evacuacion_y_por_uso(self):
        data = _hospital_data()
        bloque = bw.neufert_normativa_block(data)
        self.assertIn("evacuacion", bloque)
        self.assertAlmostEqual(
            bloque["evacuacion"]["puerta_salida_min_m"], 0.9)
        self.assertAlmostEqual(
            bloque["evacuacion"]["distancia_una_direccion_m"], 30.0)
        self.assertIn("salud", bloque.get("por_uso", {}))
        oficina = _programa("Oficina")
        bloque = bw.neufert_normativa_block(oficina)
        self.assertIn("oficinas", bloque.get("por_uso", {}))
        self.assertAlmostEqual(
            bloque["por_uso"]["oficinas"]["puesto_individual_m2"], 5.0)

    def test_metadata_del_edificio_incluye_la_edicion(self):
        data = _hospital_data()
        data.neufert_region = "cuba"
        meta = bw._building_metadata(data)
        normativa = (meta.get("edificacion", {})
                     .get("normativa", {}))
        self.assertEqual(normativa.get("edicion_regional", {})
                         .get("codigo"), "cuba")

    def test_resumen_menciona_la_edicion(self):
        data = _hospital_data()
        data.neufert_region = "cuba"
        resumen = bw.step_summary(data)
        self.assertIn("Edición: Cuba", resumen)
        data.neufert_region = NEUFERT_REGION_BASE
        resumen = bw.step_summary(data)
        self.assertNotIn("Edición:", resumen)
        self.assertIn("Normativa Neufert", resumen)

    def test_defaults_solo_suben_al_cambiar_de_region(self):
        data = _programa("Hospital")
        data.corridor_width_m = 1.2
        data.neufert_region = "cuba"
        cambios = bw.apply_neufert_defaults(data)
        self.assertTrue(any("pasillo" in c for c in cambios))
        self.assertAlmostEqual(data.corridor_width_m, 2.4)
        # Volver a la base NO baja lo ya aplicado.
        data.neufert_region = NEUFERT_REGION_BASE
        cambios = bw.apply_neufert_defaults(data)
        self.assertEqual(cambios, [])
        self.assertAlmostEqual(data.corridor_width_m, 2.4)


def _hospital_data() -> BuildingWizardData:
    data = BuildingWizardData()
    data.usage_type = "Hospital"
    data.levels = [LevelSpec(name="Planta Baja", height_m=3.0),
                   LevelSpec(name="Planta 1", height_m=3.2)]
    for level in data.levels:
        data.rooms.extend(bw.preset_rooms("Hospital", level.name))
    data.relations = bw.suggest_relations(data)
    return data


class TestGeneracionConRegiones(ARQGenTestCase):
    """El motor sigue generando sin solapes con cada edición activa."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)

    def _variantes_ok(self, data: BuildingWizardData) -> None:
        variantes = bw.generate_variants(data)
        self.assertGreaterEqual(len(variantes), 3)
        for variante in variantes[:4]:
            layout = variante.layouts[0]
            rects = [(r.x, r.y, r.w, r.d)
                     for r in layout.rooms if not r.is_corridor]
            for i, (x, y, w, d) in enumerate(rects):
                for (x2, y2, w2, d2) in rects[i + 1:]:
                    overlap_x = min(x + w, x2 + w2) - max(x, x2)
                    overlap_y = min(y + d, y2 + d2) - max(y, y2)
                    self.assertLessEqual(min(overlap_x, overlap_y),
                                         1e-6,
                                         "solape entre locales")

    def test_hospital_cuba_genera_variantes(self):
        data = _hospital_data()
        data.neufert_region = "cuba"
        self._variantes_ok(data)

    def test_escuela_mexico_genera_variantes(self):
        data = _programa("Escuela primaria")
        data.neufert_region = "mexico"
        self._variantes_ok(data)


# ---------------------------------------------------------------------------
# GUI: COMBO DE EDICIÓN REGIONAL EN EL PASO 1
# ---------------------------------------------------------------------------

class TestGUIRegionCombo(ARQGenTestCase):

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        from ui.app_window import ARQGenWindow
        self.context = self.application.create_project(
            self.project_path("region_gui.arqgen"),
            name="Proyecto Regiones")
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()
        self.addCleanup(self.window.destroy)
        self.addCleanup(self.context.close)

    def _open(self):
        self.window.open_building_wizard()
        return self.window._building_dialog

    def test_combo_presente_con_las_ediciones(self):
        dialog = self._open()
        try:
            combo = dialog._bld_widgets["region"]
            valores = list(combo["values"])
            self.assertGreaterEqual(len(valores), 5)
            self.assertIn("Base — 5.ª ed. en español", valores)
            self.assertTrue(any("Cuba" in v for v in valores))
        finally:
            dialog.destroy()

    def test_cambiar_region_reaplica_defaults_y_sincroniza(self):
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            widgets["usage"].set("Hospital")
            widgets["region"].set("Cuba (adaptación caribeña)")
            widgets["region"].event_generate("<<ComboboxSelected>>")
            self.window.update()
            self.assertEqual(dialog._bld_data.neufert_region, "cuba")
            # Cargar el programa hospitalario aplica la edición activa.
            dialog._bld_load_usage()
            self.assertAlmostEqual(dialog._bld_data.corridor_width_m,
                                   2.4)
            self.assertIn("Cuba", self.window.status_var.get())
            # La validación del paso 1 pasa con la región elegida.
            dialog._bld_data.name = "Hospital Regional"
            dialog._bld_next()
            self.assertEqual(dialog._bld_state["step"], 1)
        finally:
            dialog.destroy()

    def test_volver_a_la_base(self):
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            widgets["region"].set("Cuba (adaptación caribeña)")
            widgets["region"].event_generate("<<ComboboxSelected>>")
            widgets["region"].set("Base — 5.ª ed. en español")
            widgets["region"].event_generate("<<ComboboxSelected>>")
            self.window.update()
            self.assertEqual(dialog._bld_data.neufert_region,
                             NEUFERT_REGION_BASE)
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
