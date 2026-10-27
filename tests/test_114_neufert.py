"""NORMATIVA NEUFERT v2.7.0: reglas y especificaciones del libro.

Lo pedido: «perfeccionar todas las reglas y especificaciones apoyándote
en el libro El arte de proyectar en la arquitectura (Neufert)».

Cobertura de estas pruebas:

* Catálogo normativo (resources/knowledge/neufert_standards.json):
  carga, secciones y citación de la fuente.
* Escalera por uso social con la FÓRMULA DE BLONDEL (2h + p entre
  0,60 y 0,64 m) y ancho de camillas en salud (1,80 m).
* Pasillos y puertas por uso (2,40 m y 1,20 m donde pasa la camilla).
* Espesores de muro por tipología constructiva.
* Recuento de aseos por ocupación y estacionamiento.
* Luz natural: ventana con al menos 1/8 del suelo.
* Avisos normativos no bloqueantes (pasillo, puerta, luz, altura,
  rampa, estacionamiento).
* Bloque «normativa» del metadata del edificio y «normativa_neufert»
  en los requerimientos de cada local.
* Integração: el asistente (variantes, resumen, generación) sigue
  funcionando con los presets afinados (aulas de 36 m², UCI).
"""

from __future__ import annotations

import json
import math
import os
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (
    BuildingWizardData,
    CONSTRUCTION_TYPES,
    LevelSpec,
    USAGE_TYPES,
)

from app.paths import resource_path
from domain.neufert import (
    FUENTE_TEXTO,
    NeufertRegistry,
    StairRule,
    get_registry,
    reset_registry,
)
from domain.knowledge import SpaceDNARegistry


def _programa(usage: str, level: str = "Planta Baja"
              ) -> BuildingWizardData:
    data = BuildingWizardData()
    data.levels = [LevelSpec(name=level, height_m=3.0)]
    data.usage_type = usage
    data.rooms = bw.preset_rooms(usage, level)
    data.relations = bw.suggest_relations(data)
    return data


def _hospital() -> BuildingWizardData:
    data = BuildingWizardData()
    data.usage_type = "Hospital"
    data.levels = [LevelSpec(name="Planta Baja", height_m=3.0),
                   LevelSpec(name="Planta 1", height_m=3.2),
                   LevelSpec(name="Planta 2", height_m=3.2)]
    for level in data.levels:
        data.rooms.extend(bw.preset_rooms("Hospital", level.name))
    data.relations = bw.suggest_relations(data)
    return data


class TestCatalogoNeufert(ARQGenTestCase):
    """El catálogo normativo carga y cita su fuente."""

    def test_registro_carga_el_catalogo(self):
        registry = get_registry()
        self.assertGreaterEqual(len(registry), 10)
        self.assertTrue(registry.has("pasillos"))
        self.assertTrue(registry.has("escaleras"))
        self.assertTrue(registry.has("salud"))
        self.assertIn("Neufert", registry.fuente())

    def test_carga_directa_desde_el_recurso(self):
        registry = NeufertRegistry()
        count = registry.load_file(resource_path(
            *FUENTE_RESOURCE))
        self.assertGreaterEqual(count, 10)

    def test_registro_vacio_consulta_sin_romper(self):
        registry = NeufertRegistry()
        # Sin catálogo, el pasillo cae al fallback clásico (1,20 m).
        self.assertAlmostEqual(registry.corridor_for("Hospital"), 1.2)
        self.assertEqual(registry.stair_rule("Hospital").ancho_m, 1.2)
        self.assertIsNone(registry.ceiling_for("Hospital"))
        self.assertEqual(registry.section("salud"), {})

    def test_stair_rule_dataclass(self):
        rule = StairRule(contrahuella_m=0.175, huella_m=0.28, ancho_m=1.0)
        self.assertAlmostEqual(rule.blondel_m, 0.63)
        self.assertTrue(rule.blondel_ok)


class TestEscaleraBlondel(ARQGenTestCase):
    """La fórmula de Blondel manda: 2 × contrahuella + huella."""

    def test_blondel_en_todos_los_usos(self):
        registry = get_registry()
        for usage in USAGE_TYPES:
            rule = registry.stair_rule(usage)
            self.assertTrue(rule.blondel_ok, usage)
            self.assertGreaterEqual(rule.blondel_m, 0.60)
            self.assertLessEqual(rule.blondel_m, 0.64)

    def test_contrahuella_y_huella_dentro_de_rangos(self):
        registry = get_registry()
        for usage in USAGE_TYPES:
            rule = registry.stair_rule(usage)
            self.assertGreaterEqual(rule.contrahuella_m, 0.14)
            self.assertLessEqual(rule.contrahuella_m, 0.18)
            self.assertGreaterEqual(rule.huella_m, 0.26)
            self.assertLessEqual(rule.huella_m, 0.32)

    def test_salud_escalera_de_camillas(self):
        rule = get_registry().stair_rule("Hospital")
        self.assertGreaterEqual(rule.ancho_m, 1.8)

    def test_vivienda_mantiene_geometria_clasica(self):
        rule = get_registry().stair_rule("Vivienda")
        self.assertAlmostEqual(rule.contrahuella_m, 0.175)
        self.assertAlmostEqual(rule.huella_m, 0.28)

    def test_stair_geometry_aplica_el_uso(self):
        steps_vivienda, run_vivienda = bw.stair_geometry(
            3.0, "Vivienda")
        steps_hospital, run_hospital = bw.stair_geometry(
            3.0, "Hospital")
        # La contrahuella hospitalaria (16 cm) genera más escalones.
        self.assertGreater(steps_hospital, steps_vivienda)
        # El desarrollo sigue limitado a 2,4–4,8 m.
        for run in (run_vivienda, run_hospital):
            self.assertGreaterEqual(run, 2.4)
            self.assertLessEqual(run, 4.8)

    def test_caja_de_escalera_nunca_se_encoge(self):
        # Doméstico: la caja clásica de 1,40 m se mantiene.
        self.assertGreaterEqual(bw.stair_width_for("Vivienda"), 1.4)
        # Salud: la caja crece a 1,80 m para la camilla.
        self.assertGreaterEqual(bw.stair_width_for("Hospital"), 1.8)

    def test_caja_hospitalaria_en_el_trazado(self):
        data = _programa("Hospital")
        data.levels.append(LevelSpec(name="Planta 1", height_m=3.0))
        data.rooms.extend(bw.preset_rooms("Hospital", "Planta 1"))
        data.stairs_mode = bw.STAIR_ALWAYS
        layouts, _avisos = bw.build_layout(data)
        stairs = [p for p in layouts[0].rooms
                  if p.space_type == bw.STAIR_TYPE]
        self.assertTrue(stairs)
        self.assertGreaterEqual(stairs[0].w, 1.8)


class TestPasilloYPuerta(ARQGenTestCase):
    """Anchos por uso social: la camilla manda en salud."""

    def test_pasillo_recomendado_por_uso(self):
        suggested = bw.suggested_corridor_width
        self.assertAlmostEqual(suggested("Vivienda"), 1.2)
        self.assertGreaterEqual(suggested("Hospital"), 2.4)
        self.assertGreaterEqual(suggested("Policlínico"), 2.4)
        self.assertGreaterEqual(suggested("Escuela primaria"), 2.4)
        self.assertGreaterEqual(suggested("Oficina"), 1.5)

    def test_puerta_recomendada_por_uso(self):
        suggested = bw.suggested_door_width
        self.assertAlmostEqual(suggested("Vivienda"), 0.9)
        self.assertGreaterEqual(suggested("Hospital"), 1.2)
        self.assertGreaterEqual(suggested("Consultorio médico"), 1.2)

    def test_aplicar_defaults_solo_suben(self):
        data = _programa("Hospital")
        data.corridor_width_m = 1.2
        data.door_width_m = 0.9
        cambios = bw.apply_neufert_defaults(data)
        self.assertTrue(any("pasillo" in c for c in cambios))
        self.assertTrue(any("puerta" in c for c in cambios))
        self.assertGreaterEqual(data.corridor_width_m, 2.4)
        self.assertGreaterEqual(data.door_width_m, 1.2)

    def test_aplicar_defaults_no_baja_lo_pedido(self):
        data = _programa("Vivienda")
        data.corridor_width_m = 1.5   # el usuario pidió más
        data.door_width_m = 1.0
        cambios = bw.apply_neufert_defaults(data)
        self.assertFalse(any("pasillo" in c for c in cambios))
        self.assertFalse(any("puerta" in c for c in cambios))
        self.assertAlmostEqual(data.corridor_width_m, 1.5)
        self.assertAlmostEqual(data.door_width_m, 1.0)


class TestMurosYTecnica(ARQGenTestCase):
    """Espesores por tipología, aseos, rampas y estacionamiento."""

    def test_espesor_por_tipologia(self):
        suggested = bw.suggested_wall_thickness
        self.assertAlmostEqual(suggested(
            "Mampostería de bloque + losa de vigueta"), 0.2)
        self.assertGreaterEqual(suggested("Muros de piedra"), 0.4)
        self.assertGreaterEqual(suggested("Tierra (adobe o tapial)"), 0.4)
        self.assertLessEqual(
            suggested("Panel prefabricado (sandwich)"), 0.15)
        # Las diez tipologías tienen espesor definido.
        for tip in CONSTRUCTION_TYPES:
            self.assertGreater(suggested(tip), 0.0, tip)

    def test_recuento_de_aseos(self):
        registry = get_registry()
        aseos = registry.wc_counts("Oficina", 60)
        self.assertGreaterEqual(aseos.get("inodoros", 0), 2)
        aseos_escuela = registry.wc_counts("Escuela primaria", 100)
        self.assertGreaterEqual(aseos_escuela.get("lavabos", 0), 6)
        # Ocupación pequeña: al menos un aseo.
        self.assertGreaterEqual(
            registry.wc_counts("Vivienda", 3).get("inodoros", 0), 1)

    def test_rampa_maxima(self):
        self.assertLessEqual(get_registry().ramp_max_percent(), 8.0)

    def test_ventana_ratio_de_luz(self):
        ratio_min, ratio_rec = get_registry().window_ratio()
        self.assertAlmostEqual(ratio_min, 0.125)   # 1/8 del suelo
        self.assertAlmostEqual(ratio_rec, 0.166)   # 1/6 del suelo

    def test_alturas_libres_por_uso(self):
        ceiling = get_registry().ceiling_for
        self.assertAlmostEqual(ceiling("Vivienda"), 2.7)
        self.assertGreaterEqual(ceiling("Hospital"), 3.0)
        self.assertGreaterEqual(ceiling("Escuela primaria"), 3.0)


class TestAvisosNormativos(ARQGenTestCase):
    """neufert_advisories: aconsejan, nunca bloquean."""

    def test_hospital_pasillo_corto_avisa(self):
        data = _hospital()
        data.corridor_width_m = 1.2
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("Pasillo" in a and "Neufert" in a
                            for a in avisos))

    def test_hospital_con_pasillo_normativo_no_avisa(self):
        data = _hospital()
        data.corridor_width_m = 2.4
        data.door_width_m = 1.2
        avisos = [a for a in bw.neufert_advisories(data)
                  if "Pasillo" in a or "Puerta" in a]
        self.assertEqual(avisos, [])

    def test_puerta_estrecha_en_salud_avisa_camilla(self):
        data = _programa("Consultorio médico")
        data.door_width_m = 0.9
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("camilla" in a for a in avisos))

    def test_luz_natural_corta_en_aulas(self):
        data = _programa("Escuela primaria")
        data.window_width_m = 1.0
        data.window_height_m = 1.0
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("Luz natural" in a for a in avisos))

    def test_luz_natural_suficiente_no_avisa(self):
        data = _programa("Vivienda")
        # Ventana 1,4 × 1,2 = 1,68 m² ≥ 1/8 de la Sala (12 m² = 1,5).
        self.assertFalse(any("Luz natural" in a
                             for a in bw.neufert_advisories(data)))

    def test_altura_libre_corta_avisa(self):
        data = _programa("Escuela primaria")
        data.levels = [LevelSpec(name="Planta Baja", height_m=2.5)]
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("altura libre" in a for a in avisos))

    def test_desnivel_pide_rampa(self):
        data = _programa("Vivienda")
        data.terrain_type = "Irregular con pendiente fuerte"
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("rampa" in a.lower() for a in avisos))

    def test_uso_publico_pide_estacionamiento(self):
        data = _programa("Policlínico")
        avisos = bw.neufert_advisories(data)
        self.assertTrue(any("Estacionamiento" in a for a in avisos))
        # La vivienda no pide estacionamiento normativo.
        self.assertFalse(any("Estacionamiento" in a
                             for a in bw.neufert_advisories(
                                 _programa("Vivienda"))))

    def test_registro_se_recarga_tras_reset(self):
        """Sin singleton el registro se recarga de los recursos solo."""
        data = _programa("Hospital")
        data.corridor_width_m = 1.2
        reset_registry()
        try:
            registry = get_registry()
            self.assertGreaterEqual(len(registry), 10)
            avisos = bw.neufert_advisories(data)
            self.assertTrue(any("Neufert" in a for a in avisos))
        finally:
            reset_registry()   # se recarga perezosamente en el siguiente uso


class TestMetadataNormativa(ARQGenTestCase):
    """El bloque «normativa» del edificio y el «normativa_neufert»."""

    def test_bloque_normativa_del_edificio(self):
        data = _hospital()
        block = bw.neufert_normativa_block(data)
        self.assertIn("Neufert", block["fuente"])
        self.assertGreaterEqual(block["pasillo_recomendado_m"], 2.4)
        self.assertGreaterEqual(block["puerta_sugerida_m"], 1.2)
        self.assertGreaterEqual(
            block["escalera"]["contrahuella_m"], 0.14)
        self.assertLessEqual(block["escalera"]["blondel_m"], 0.64)
        self.assertLessEqual(block["rampa_max_porcentaje"], 8)
        self.assertIn("estacionamiento", block)

    def test_metadata_del_edificio_incluye_normativa(self):
        data = _hospital()
        metadata = bw._building_metadata(data)
        normativa = metadata["edificacion"].get("normativa")
        self.assertIsInstance(normativa, dict)
        self.assertIn("fuente", normativa)

    def test_requerimientos_del_local_con_normativa(self):
        data = _hospital()
        ward = next(r for r in data.rooms if r.space_type == "WARD")
        req = bw.room_requirements(data, ward)
        normativa = req["arquitectonicos"].get("normativa_neufert")
        self.assertIsInstance(normativa, dict)
        self.assertIn("Neufert", normativa["fuente"])
        self.assertAlmostEqual(normativa["puerta_sugerida_m"], 1.2)
        self.assertTrue(normativa["criterio"].strip())

    def test_resumen_menciona_la_normativa(self):
        data = _hospital()
        texto = bw.step_summary(data)
        self.assertIn("Normativa Neufert", texto)

    def test_escalera_del_requerimiento_lleva_blondel(self):
        """apply_plan guarda contrahuella/huella del uso con Blondel."""
        context = self.application.create_project(
            self.project_path("neufert.arqgen"),
            name="Proyecto Neufert")
        try:
            data = _hospital()
            data.levels = [LevelSpec(name="Planta Baja", height_m=3.0)]
            data.rooms = [r for r in data.rooms
                          if r.level_ref == "Planta Baja"]
            data.stairs_mode = bw.STAIR_ALWAYS
            bw.apply_plan(data, context)
            stairs = [s for s in context.architecture.list(
                "SPACE", context.project.id)
                if s.metadata.get("requerimientos", {})
                .get("arquitectonicos", {}).get("tipo") == "STAIR"]
            self.assertTrue(stairs)
            arch = stairs[0].metadata["requerimientos"]["arquitectonicos"]
            blondel = 2.0 * arch["contrahuella_m"] + arch["huella_m"]
            self.assertGreaterEqual(blondel, 0.60)
            self.assertLessEqual(blondel, 0.64)
            self.assertIn("Neufert", arch["norma"])
        finally:
            context.close()


class TestDNAV2(ARQGenTestCase):
    """Space DNA v2.0: 28 tipos con su bloque Neufert."""

    def test_dna_carga_y_tipos(self):
        registry = SpaceDNARegistry()
        count = registry.load_file(resource_path(
            "knowledge", "space_dna.json"))
        self.assertGreaterEqual(count, 28)
        for space_type in ("LAVATORY", "ICU", "DINING_HALL",
                           "KITCHEN_INSTITUTIONAL", "LIBRARY", "PARKING"):
            self.assertIsNotNone(registry.get(space_type), space_type)

    def test_bloque_neufert_en_todos_los_tipos(self):
        registry = SpaceDNARegistry()
        registry.load_file(resource_path("knowledge", "space_dna.json"))
        for space_type in registry.types():
            dna = registry.get(space_type)
            self.assertIn("neufert", dna.metadata, space_type)
            self.assertIn("nota", dna.metadata["neufert"], space_type)

    def test_valores_clave_se_mantienen(self):
        registry = SpaceDNARegistry()
        registry.load_file(resource_path("knowledge", "space_dna.json"))
        self.assertGreaterEqual(
            registry.get("OPERATING_ROOM").minimum_area, 36.0)
        self.assertGreaterEqual(
            registry.get("WARD").minimum_area, 28.0)
        self.assertAlmostEqual(
            registry.get("CORRIDOR").minimum_width, 1.2)
        # UCI: 18 m² por cama (Neufert).
        self.assertGreaterEqual(registry.get("ICU").minimum_area, 18.0)

    def test_pasillo_hospitalario_en_dna(self):
        registry = SpaceDNARegistry()
        registry.load_file(resource_path("knowledge", "space_dna.json"))
        ward = registry.get("WARD")
        self.assertAlmostEqual(
            ward.metadata["neufert"]["puerta_m"], 1.2)


class TestIntegracionPresets(ARQGenTestCase):
    """Los presets afinados (aulas 36 m², UCI) siguen trazando bien."""

    def test_aulas_de_36_m2(self):
        rooms = bw.preset_rooms("Escuela primaria", "Planta Baja")
        aulas = [r for r in rooms if r.space_type == "CLASSROOM"]
        self.assertTrue(aulas)
        for aula in aulas:
            self.assertGreaterEqual(aula.width_m * aula.depth_m, 36.0)

    def test_hospital_con_uci(self):
        rooms = bw.preset_rooms("Hospital", "Planta 1")
        self.assertTrue(any(r.space_type == "ICU" for r in rooms))
        uci = next(r for r in rooms if r.space_type == "ICU")
        self.assertGreaterEqual(uci.width_m * uci.depth_m, 36.0)

    def test_variantes_del_hospital_siguian_generando(self):
        data = _hospital()
        variants = bw.generate_variants(data)
        self.assertGreaterEqual(len(variants), 20)
        self.assertGreater(variants[0].score, 0)

    def test_variantes_de_la_escuela_siguian_generando(self):
        data = _programa("Escuela primaria")
        variants = bw.generate_variants(data)
        self.assertGreaterEqual(len(variants), 20)

    def test_validacion_de_presets_en_verde(self):
        for usage in ("Vivienda", "Oficina", "Escuela primaria",
                      "Hospital", "Policlínico"):
            data = _programa(usage)
            for step in range(5):
                self.assertEqual(bw.validate_step(step, data),
                                 [], f"{usage} · paso {step + 1}")


# Ruta del recurso del catálogo (para la prueba de carga directa).
FUENTE_RESOURCE = ("knowledge", "neufert_standards.json")


if __name__ == "__main__":
    unittest.main()
