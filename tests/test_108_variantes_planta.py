"""Asistente de edificación v2.1.0: uso social, bioclimática e
instalaciones y el MOTOR DE VARIANTES DE PLANTA.

Lo pedido por el usuario: ventana 1 pide datos (dimensiones,
tipología constructiva, uso social), ventana 2 los locales sugeridos
según el uso con sus relaciones espaciales, ventana 3 los
requerimientos bioclimáticos y de instalaciones, y al final el motor
GENERA LA PLANTA ARQUITECTÓNICA CON SUS POSIBLES VARIANTES.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (
    BuildingWizardData, INSTALLATION_MODULES, PlantVariant, USAGE_TYPES,
)


def _consultorio(level: str = "Planta Baja") -> BuildingWizardData:
    """Datos del programa de un consultorio médico (uso social)."""
    data = BuildingWizardData()
    data.levels = [bw.LevelSpec(name=level, height_m=3.0)]
    data.usage_type = "Consultorio médico"
    data.rooms = bw.preset_rooms("Consultorio médico", level)
    data.relations = bw.suggest_relations(data)
    return data


def _vivienda(level: str = "Planta Baja") -> BuildingWizardData:
    data = BuildingWizardData()
    data.levels = [bw.LevelSpec(name=level, height_m=3.0)]
    data.usage_type = "Vivienda"
    data.rooms = bw.preset_rooms("Vivienda", level)
    data.relations = bw.suggest_relations(data)
    return data


class TestUsoSocial(ARQGenTestCase):
    """Paso 1: uso social y programa sugerido de locales."""

    def test_usages_and_presets_exist(self):
        self.assertGreaterEqual(len(USAGE_TYPES), 9)
        for usage in USAGE_TYPES:
            if usage in bw.USOS_COMERCIALES:
                # v3.25.0: el programa sale del documento CC/OF (§89-90)
                # vía comercial_specs, no del PROGRAM_PRESETS clásico
                self.assertIn(usage, bw.USAGE_HINTS)
                rooms = bw.preset_rooms(usage, "PB")
                self.assertGreaterEqual(len(rooms), 4, usage)
                continue
            self.assertIn(usage, bw.PROGRAM_PRESETS)
            self.assertIn(usage, bw.USAGE_HINTS)
            rooms = bw.preset_rooms(usage, "PB")
            self.assertGreaterEqual(len(rooms), 4, usage)

    def test_escuela_suggests_classrooms(self):
        rooms = bw.preset_rooms("Escuela primaria", "PB")
        aulas = [r for r in rooms if r.space_type == "CLASSROOM"]
        self.assertGreaterEqual(len(aulas), 3)

    def test_consultorio_suggests_waiting_and_consultations(self):
        rooms = bw.preset_rooms("Consultorio médico", "PB")
        types = {r.space_type for r in rooms}
        self.assertIn("WAITING_ROOM", types)
        self.assertIn("CONSULTATION_ROOM", types)

    def test_albergue_suggests_dormitories_and_bath(self):
        rooms = bw.preset_rooms("Albergue", "PB")
        dorms = [r for r in rooms if r.space_type == "BEDROOM"]
        self.assertGreaterEqual(len(dorms), 3)
        self.assertTrue(any(r.space_type == "BATHROOM" for r in rooms))

    def test_apply_usage_program_fills_rooms_and_relations(self):
        data = BuildingWizardData()
        data.usage_type = "Centro comunitario"
        rooms, relations = bw.apply_usage_program(data)
        self.assertGreaterEqual(rooms, 5)
        self.assertGreaterEqual(relations, 1)
        self.assertTrue(any(r.space_type == "MULTIUSE_HALL"
                            for r in data.rooms))
        # las relaciones sugeridas referencian locales del programa
        names = {r.name for r in data.rooms}
        for rel in data.relations:
            self.assertIn(rel.a_name, names)
            self.assertIn(rel.b_name, names)

    def test_new_dna_types_load(self):
        from app.paths import resource_path
        from domain.knowledge import SpaceDNARegistry
        registry = SpaceDNARegistry()
        count = registry.load_file(
            resource_path("knowledge", "space_dna.json"))
        self.assertGreaterEqual(count, 13)
        for space_type in ("CLASSROOM", "CONSULTATION_ROOM",
                           "WAITING_ROOM", "MULTIUSE_HALL"):
            dna = registry.get(space_type)
            self.assertIsNotNone(dna, space_type)
            self.assertTrue(dna.daylight)


class TestValidacionNueva(ARQGenTestCase):
    """Validación amable de los campos nuevos."""

    def test_dimensions_negative_rejected(self):
        data = BuildingWizardData()
        data.lot_width_m = -3.0
        errors = bw.validate_step(0, data)
        self.assertTrue(any("negativas" in e for e in errors))

    def test_dimensions_zero_mean_unlimited(self):
        data = BuildingWizardData()
        self.assertEqual(bw.validate_step(0, data), [])

    def test_construction_type_must_be_known(self):
        data = BuildingWizardData()
        data.construction_type = "Cartón"
        errors = bw.validate_step(0, data)
        self.assertTrue(any("tipología constructiva" in e.lower()
                            for e in errors))

    def test_usage_type_must_be_known(self):
        data = BuildingWizardData()
        data.usage_type = "Nave espacial"
        errors = bw.validate_step(0, data)
        self.assertTrue(any("uso social" in e.lower() for e in errors))

    def test_eaves_validation(self):
        data = BuildingWizardData()
        data.eaves_m = -0.5
        self.assertTrue(bw.validate_step(4, data))
        data.eaves_m = 4.0
        self.assertTrue(any("alero" in e.lower()
                            for e in bw.validate_step(4, data)))
        data.eaves_m = 0.6
        self.assertEqual(bw.validate_step(4, data), [])

    def test_unknown_installation_rejected(self):
        data = BuildingWizardData()
        data.installations = ["Eléctrica", "Gravedad"]
        errors = bw.validate_step(4, data)
        self.assertTrue(any("desconocidos" in e for e in errors))

    def test_variant_and_summary_steps_never_block(self):
        self.assertEqual(bw.validate_step(5, BuildingWizardData()), [])
        self.assertEqual(bw.validate_step(6, BuildingWizardData()), [])

    def test_data_from_values_step_four(self):
        data = BuildingWizardData()
        errors = bw.data_from_values(4, {
            "protection_solar": False,
            "eaves_m": "0,8",
            "installations": ["Eléctrica", "Gas", "No existe"],
        }, data)
        self.assertEqual(errors, [])
        self.assertFalse(data.protection_solar)
        self.assertAlmostEqual(data.eaves_m, 0.8)
        self.assertEqual(data.installations, ["Eléctrica", "Gas"])

    def test_data_from_values_step_zero(self):
        data = BuildingWizardData()
        errors = bw.data_from_values(0, {
            "name": "Escuela José Martí",
            "usage_type": "Escuela primaria",
            "construction_type": bw.CONSTRUCTION_TYPES[1],
            "lot_width_m": "20,5",
            "lot_depth_m": "15",
        }, data)
        self.assertEqual(errors, [])
        self.assertEqual(data.usage_type, "Escuela primaria")
        self.assertAlmostEqual(data.lot_width_m, 20.5)
        self.assertAlmostEqual(data.lot_depth_m, 15.0)
        self.assertEqual(data.construction_type, bw.CONSTRUCTION_TYPES[1])


class TestMotorVariantes(ARQGenTestCase):
    """El generador de plantas con sus posibles variantes."""

    def test_generates_variants_ranked(self):
        variants = bw.generate_variants(_vivienda())
        # v2.3.0: 9 esquemas (lineal, doble crujía, patio, en L, T, U,
        # H, cruz y articulada) × espejo = hasta 18 variantes.
        self.assertGreaterEqual(len(variants), 6)
        schemes = {v.scheme for v in variants}
        self.assertLessEqual(
            {"doble_crujia", "patio", "lineal", "en_L", "en_T", "en_U",
             "en_H", "en_cruz", "articulada"}, schemes)
        scores = [v.score for v in variants]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual([v.rank for v in variants],
                         list(range(1, len(variants) + 1)))

    def test_variants_are_deterministic(self):
        first = bw.generate_variants(_consultorio())
        second = bw.generate_variants(_consultorio())
        self.assertEqual([v.key for v in first], [v.key for v in second])
        self.assertEqual([v.score for v in first],
                         [v.score for v in second])

    def test_metrics_within_bounds_and_complete(self):
        for variant in bw.generate_variants(_consultorio()):
            self.assertGreaterEqual(variant.score, 0.0, variant.key)
            self.assertLessEqual(variant.score, 100.0, variant.key)
            for name, value in variant.metrics.items():
                self.assertGreaterEqual(value, 0.0, name)
                self.assertLessEqual(value, 1.0, name)
            for name in ("Adyacencias", "Luz natural", "Compacidad",
                         "Ventilación cruzada", "Afinidad al clima"):
                self.assertIn(name, variant.metrics)

    def test_double_bay_has_two_rows_with_central_corridor(self):
        data = _consultorio()
        variant = next(v for v in bw.generate_variants(data)
                       if v.scheme == "doble_crujia" and not v.mirror)
        layout = variant.layouts[0]
        front = [p for p in layout.rooms if p.y == 0.0]
        back = [p for p in layout.rooms if p.y > 0.0]
        self.assertTrue(front)
        self.assertTrue(back)
        corridor = layout.corridor
        self.assertIsNotNone(corridor)
        assert corridor is not None
        self.assertEqual(corridor.space_type, bw.CORRIDOR_TYPE)
        depth_front = max(p.y + p.d for p in front)
        self.assertAlmostEqual(corridor.y, depth_front)
        self.assertAlmostEqual(corridor.y + corridor.d,
                               min(p.y for p in back))
        # cada local recibe puerta al pasillo + entrada principal
        # (v2.2.0: la puerta clínica espera→consultorio sugerida por
        # el uso «Consultorio médico» se suma como EXTRA si quedó
        # pegada en su crujía)
        self.assertGreaterEqual(len(layout.doors),
                                len(layout.rooms) + 1)
        # ventanas en los DOS frentes de fachada
        self.assertTrue(layout.windows)

    def test_double_bay_openings_land_on_walls(self):
        data = _consultorio()
        variant = next(v for v in bw.generate_variants(data)
                       if v.scheme == "doble_crujia" and not v.mirror)
        layout = variant.layouts[0]
        for opening in layout.doors + layout.windows:
            wall = layout.walls[opening.wall_index]
            self.assertGreaterEqual(opening.offset_m, 0.0)
            self.assertLessEqual(
                opening.offset_m + opening.width_m, wall["length"] + 1e-6,
                opening.note)

    def test_patio_scheme_creates_patio_space(self):
        data = _consultorio()
        variant = next(v for v in bw.generate_variants(data)
                       if v.scheme == "patio" and not v.mirror)
        layout = variant.layouts[0]
        patio = layout.corridor
        self.assertIsNotNone(patio)
        assert patio is not None
        self.assertEqual(patio.space_type, bw.PATIO_TYPE)
        self.assertGreaterEqual(patio.d, 2.5)  # un patio habitable
        names = [p.name for p in layout.all_rooms]
        self.assertIn(patio.name, names)
        # y la variante se explica: aviso del patio
        self.assertTrue(any("patio" in a.lower()
                            for a in variant.advisories))

    def test_mirror_reflects_linear_layout(self):
        data = _vivienda()
        straight = next(v for v in bw.generate_variants(data)
                        if v.scheme == "lineal" and not v.mirror)
        mirrored = next(v for v in bw.generate_variants(data)
                        if v.scheme == "lineal" and v.mirror)
        s_layout = straight.layouts[0]
        m_layout = mirrored.layouts[0]
        # mismos locales, distinta disposición a lo largo de la fachada
        self.assertEqual({p.name for p in s_layout.rooms},
                         {p.name for p in m_layout.rooms})
        first = s_layout.rooms[0]
        # el primero de la recta (Sala) en x=0; en el espejo pasa al
        # extremo opuesto
        self.assertAlmostEqual(first.x, 0.0)
        m_first = next(p for p in m_layout.rooms
                       if p.name == first.name)
        total_w = max(p.x + p.w for p in m_layout.all_rooms)
        self.assertAlmostEqual(m_first.x + m_first.w, total_w)
        self.assertNotEqual([p.name for p in s_layout.rooms],
                            [p.name for p in m_layout.rooms])

    def test_lot_fit_penalises_oversized_variants(self):
        data = _consultorio()
        data.lot_width_m = 9.0
        data.lot_depth_m = 7.5
        variants = bw.generate_variants(data)
        oversized = [v for v in variants if not v.fits_lot]
        self.assertTrue(oversized)
        for variant in oversized:
            self.assertIn("No cabe", variant.fits_text)
            self.assertLess(variant.score, 30.0)
        fitting = [v for v in variants if v.fits_lot]
        if fitting:
            self.assertGreaterEqual(fitting[0].score,
                                    max(v.score for v in oversized))

    def test_share_wall_helper(self):
        a = bw.PlacedRoom(name="A", space_type="ROOM", level="PB",
                          x=0.0, y=0.0, w=3.0, d=3.0)
        b = bw.PlacedRoom(name="B", space_type="ROOM", level="PB",
                          x=3.0, y=0.5, w=2.0, d=3.0)
        self.assertTrue(bw.share_wall(a, b))
        c = bw.PlacedRoom(name="C", space_type="ROOM", level="PB",
                          x=10.0, y=0.0, w=2.0, d=3.0)
        self.assertFalse(bw.share_wall(a, c))

    def test_bay_alignment_advisories(self):
        """La crujía se alinea al fondo mayor y lo explica."""
        data = _vivienda()  # cocina 2,5 m y baño 2,0 m en la crujía trasera
        variant = next(v for v in bw.generate_variants(data)
                       if v.scheme == "doble_crujia" and not v.mirror)
        self.assertTrue(any("se alineó a la crujía" in a
                            for a in variant.advisories))


class TestPlanConVariante(ARQGenTestCase):
    """build_plan/apply_plan respetan la variante elegida."""

    def test_plan_uses_variant_layout(self):
        data = _consultorio()
        straight = next(v for v in bw.generate_variants(data)
                        if v.scheme == "doble_crujia" and not v.mirror)
        plan, layouts, _advisories = bw.build_plan(data,
                                                   variant=straight)
        self.assertEqual(len(layouts), len(straight.layouts))
        ops = [op for op, _params in plan]
        self.assertIn("BUILDING", ops)
        self.assertIn("WALL", ops)
        spaces = [params for op, params in plan if op == "SPACE"]
        # el pasillo entra como espacio sin room_ref
        pasillos = [s for s in spaces if s["is_corridor"]]
        self.assertTrue(pasillos)
        self.assertEqual(pasillos[0]["room_ref"], "")
        # y la metadata del edificio lleva la variante elegida
        building_meta = next(params for op, params in plan
                             if op == "BUILDING")["metadata"]
        self.assertEqual(
            building_meta["edificacion"]["variante_planta"]["clave"],
            straight.key)

    def test_apply_plan_with_variant_creates_geometry_and_metadata(self):
        ctx = self.demo_context()
        pid = ctx.project.id
        level_name = ctx.architecture.list("LEVEL", pid)[0].name
        before = len(ctx.architecture.list("SPACE", pid))
        before_walls = len(ctx.architecture.list("WALL", pid))
        before_doors = len(ctx.architecture.list("DOOR", pid))
        before_windows = len(ctx.architecture.list("WINDOW", pid))
        data = _consultorio(level_name)
        variant = next(v for v in bw.generate_variants(data)
                       if v.scheme == "patio" and not v.mirror)
        summary = bw.apply_plan(data, ctx, variant=variant)
        self.assertEqual(summary["levels_created"], 0)  # reutiliza nivel
        spaces = ctx.architecture.list("SPACE", pid)
        self.assertEqual(len(spaces), before + 7)  # 6 locales + patio
        walls = ctx.architecture.list("WALL", pid)
        self.assertEqual(len(walls),
                         before_walls + len(variant.layouts[0].walls))
        doors = ctx.architecture.list("DOOR", pid)
        self.assertEqual(len(doors),
                         before_doors + len(variant.layouts[0].doors))
        windows = ctx.architecture.list("WINDOW", pid)
        self.assertEqual(len(windows),
                         before_windows + len(variant.layouts[0].windows))
        building = ctx.architecture.list("BUILDING", pid)[0]
        meta = building.metadata["edificacion"]
        self.assertEqual(meta["uso_social"], "Consultorio médico")
        self.assertEqual(meta["variante_planta"]["titulo"],
                         variant.title)
        self.assertIn("Sanitaria", meta["instalaciones"])
        self.assertTrue(meta["bioclimatica"]["proteccion_solar"])
        self.assertEqual(meta["tipologia_constructiva"],
                         bw.CONSTRUCTION_TYPES[0])
        # el patio se creó como espacio de circulación
        patio_names = [s.name for s in spaces if s.name.startswith("Patio")]
        self.assertTrue(patio_names)
        ctx.close()

    def test_apply_plan_without_variant_keeps_linear(self):
        """Regresión: sin variante el trazado lineal clásico se mantiene."""
        ctx = self.demo_context()
        pid = ctx.project.id
        level_name = ctx.architecture.list("LEVEL", pid)[0].name
        before = len(ctx.architecture.list("SPACE", pid))
        data = _vivienda(level_name)
        layouts, _adv = bw.build_layout(data)
        expected_walls = sum(len(l.walls) for l in layouts)
        expected_doors = sum(len(l.doors) for l in layouts)
        summary = bw.apply_plan(data, ctx)
        spaces = ctx.architecture.list("SPACE", pid)
        self.assertEqual(len(spaces), before + 7)  # 6 locales + pasillo
        self.assertEqual(summary["walls"], expected_walls)
        self.assertEqual(summary["doors"], expected_doors)
        ctx.close()


class TestResumenYAyuda(ARQGenTestCase):
    """El resumen del último paso y la ayuda dinámica."""

    def test_summary_mentions_new_data(self):
        data = _consultorio()
        data.lot_width_m = 20.0
        data.lot_depth_m = 12.0
        data.installations = ["Eléctrica", "Energía solar"]
        variant = bw.generate_variants(data)[0]
        text = bw.step_summary(data, None, variant)
        self.assertIn("consultorio médico", text)  # uso social
        self.assertIn("Tipología constructiva", text)
        self.assertIn("ancho máx. 20.0 m", text)
        self.assertIn("Variante de planta", text)
        self.assertIn(variant.title, text)
        self.assertIn("Energía solar", text)
        self.assertIn("aleros", text)

    def test_summary_patio_mentions_patio_not_corridor(self):
        data = _consultorio()
        variant = next(v for v in bw.generate_variants(data)
                       if v.scheme == "patio" and not v.mirror)
        text = bw.step_summary(data, None, variant)
        self.assertIn("Patio central de", text)
        self.assertNotIn("Pasillo de 1.2 m", text)

    def test_building_field_names_complete(self):
        names = bw.building_field_names()
        for key in ("usage_type", "lot_width_m", "lot_depth_m",
                    "construction_type", "protection_solar", "eaves_m",
                    "installations"):
            self.assertIn(key, names)

    def test_help_tooltips_for_new_widgets(self):
        from ui.help import TOOLTIPS
        for key in ("bld_usage", "bld_lot_w", "bld_lot_d",
                    "bld_construction", "bld_eaves", "bld_inst",
                    "bld_variants"):
            self.assertIn(key, TOOLTIPS)

    def test_steps_now_seven(self):
        self.assertEqual(len(bw.BUILDING_STEPS), 7)
        self.assertIn("variante", bw.BUILDING_STEPS[5][1].lower())
        self.assertIn("Bioclimática", bw.BUILDING_STEPS[4][1])


if __name__ == "__main__":
    unittest.main()
