"""v1.8.0: asistente de EDIFICACIÓN completa.

Cubre:
- Catálogos legibles (climas, sistemas, orientaciones, relaciones §8),
  programas tipo (Vivienda/Oficina) y el DNA ampliado (9 tipos).
- Validación amable paso a paso (5 pasos) y data_from_values con coma
  decimal.
- Motor de trazado determinista: orden por relaciones, locales en fila,
  pasillo que conecta TODOS los locales, muros FUSIONADOS (una pared
  compartida = UN muro), puertas declaradas + automáticas + entrada,
  ventanas en fachada exterior y reglas de muros portantes.
- Plan declarativo (orden de operaciones, niveles existentes, índice de
  muro de cada vano) y ejecución end-to-end por las fachadas oficiales
  (CommandBus, auditoría, eventos, metadata de requerimientos, niveles
  ligados al edificio y reutilización de niveles existentes).
- Ventana real: el botón «Asistente de edificación» abre el diálogo de
  5 pasos y el flujo completo genera el edificio.
"""

from __future__ import annotations

import unittest
from unittest import mock

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (
    BUILDING_STEPS, BuildingWizardData, CLIMATE_ZONES, LevelSpec,
    ORIENTATIONS, RelationSpec, RoomSpec, STRUCTURAL_SYSTEMS,
)
from domain.model import RELATIONSHIP_KINDS


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


DISPLAY = _display_available()


def _vivienda(level: str = "Planta Baja") -> BuildingWizardData:
    """Datos listos de una vivienda de 6 locales con pasillo."""
    data = BuildingWizardData(name="Casa Test")
    data.levels = [LevelSpec(name=level, height_m=3.0)]
    data.rooms = bw.preset_rooms("Vivienda", level)
    return data


class TestCatalogosYProgramas(unittest.TestCase):
    """Catálogos en español y programas tipo listos para usar."""

    def test_steps_are_seven_and_spanish(self):
        self.assertEqual(len(BUILDING_STEPS), 7)
        titles = " ".join(s[1] for s in BUILDING_STEPS)
        for word in ("edificación", "niveles", "locales", "relacionan",
                     "Bioclimática", "variante", "Resumen"):
            self.assertIn(word.lower(), titles.lower())

    def test_catalogs_present(self):
        self.assertGreaterEqual(len(CLIMATE_ZONES), 4)
        self.assertGreaterEqual(len(STRUCTURAL_SYSTEMS), 3)
        self.assertGreaterEqual(len(ORIENTATIONS), 4)

    def test_relation_labels_map_to_spec_kinds(self):
        from domain.model import RELATIONSHIP_KINDS as KINDS
        for _label, kind in bw.RELATION_KINDS_ES:
            self.assertIn(kind, KINDS)

    def test_preset_vivienda_has_six_rooms(self):
        rooms = bw.preset_rooms("Vivienda", "Planta Baja")
        self.assertEqual(len(rooms), 6)
        names = {r.name for r in rooms}
        self.assertIn("Sala", names)
        self.assertIn("Baño", names)

    def test_preset_oficina_and_unknown_fallback(self):
        self.assertEqual(len(bw.preset_rooms("Oficina", "P1")), 6)
        self.assertEqual(len(bw.preset_rooms("No existe", "P1")), 6)

    def test_dna_extended_to_thirteen_types(self):
        from app.paths import resource_path
        from domain.knowledge import SpaceDNARegistry
        registry = SpaceDNARegistry()
        count = registry.load_file(resource_path("knowledge",
                                                 "space_dna.json"))
        # v2.2.0: el DNA sigue creciendo (tema hospitalario: 22 tipos)
        self.assertGreaterEqual(count, 13)
        for tipo in ("DINING_ROOM", "ENTRANCE", "STOREROOM",
                     "CLASSROOM", "CONSULTATION_ROOM"):
            self.assertIsNotNone(registry.get(tipo))

    def test_field_names_complete(self):
        names = bw.building_field_names()
        for expected in ("name", "levels", "rooms", "relations",
                         "corridor_width_m", "cross_ventilation"):
            self.assertIn(expected, names)


class TestValidacion(unittest.TestCase):
    """Validación amable paso a paso (mensajes en español)."""

    def test_step1_name_required(self):
        data = BuildingWizardData(name="  ")
        errors = bw.validate_step(0, data)
        self.assertTrue(any("nombre" in e.lower() for e in errors))

    def test_step1_ok_with_defaults(self):
        self.assertEqual(bw.validate_step(0, BuildingWizardData()), [])

    def test_step2_needs_level(self):
        data = BuildingWizardData()
        data.levels = []
        errors = bw.validate_step(1, data)
        self.assertTrue(any("nivel" in e.lower() for e in errors))

    def test_step2_duplicate_level_names(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec("Piso", 3.0), LevelSpec("piso ", 3.0)]
        errors = bw.validate_step(1, data)
        self.assertTrue(any("mismo nombre" in e for e in errors))

    def test_step2_height_bounds(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec("PB", 0.0)]
        self.assertTrue(bw.validate_step(1, data))
        data.levels = [LevelSpec("PB", 25.0)]
        self.assertTrue(any("20 m" in e for e in bw.validate_step(1, data)))
        data.levels = [LevelSpec("PB", 3.0)]
        self.assertEqual(bw.validate_step(1, data), [])

    def test_step3_needs_rooms(self):
        errors = bw.validate_step(2, BuildingWizardData())
        self.assertTrue(any("local" in e.lower() for e in errors))

    def test_step3_level_ref_must_exist(self):
        data = _vivienda("Planta Baja")
        data.rooms[0].level_ref = "Piso 9"
        errors = bw.validate_step(2, data)
        self.assertTrue(any("no existe" in e for e in errors))

    def test_step3_dimensions_must_be_positive(self):
        data = _vivienda()
        data.rooms[0].width_m = 0.0
        errors = bw.validate_step(2, data)
        self.assertTrue(any("mayores que cero" in e for e in errors))

    def test_step3_corridor_name_collision(self):
        data = _vivienda()
        data.rooms.append(RoomSpec(name="Pasillo Planta Baja",
                                   level_ref="Planta Baja"))
        errors = bw.validate_step(2, data)
        self.assertTrue(any("choca con" in e for e in errors))

    def test_step3_ok_with_vivienda(self):
        self.assertEqual(bw.validate_step(2, _vivienda()), [])

    def test_step4_self_relation_rejected(self):
        data = _vivienda()
        data.relations = [RelationSpec("Sala", "Sala", "Adyacente a",
                                       False)]
        errors = bw.validate_step(3, data)
        self.assertTrue(any("consigo mismo" in e for e in errors))

    def test_step4_unknown_room_rejected(self):
        data = _vivienda()
        data.relations = [RelationSpec("Sala", "Terraza", "Adyacente a",
                                       False)]
        errors = bw.validate_step(3, data)
        self.assertTrue(any("no está" in e for e in errors))

    def test_step4_corridor_narrower_than_door(self):
        data = _vivienda()
        data.corridor_width_m = 0.5
        errors = bw.validate_step(3, data)
        self.assertTrue(any("más estrecho" in e for e in errors))

    def test_step4_vano_does_not_fit_narrowest_room(self):
        data = _vivienda()
        data.door_width_m = 2.0  # el Baño mide 1,8 m de ancho
        errors = bw.validate_step(3, data)
        self.assertTrue(any("local más estrecho" in e for e in errors))

    def test_step4_negative_sill(self):
        data = _vivienda()
        data.window_sill_m = -0.1
        errors = bw.validate_step(3, data)
        self.assertTrue(any("antepecho" in e.lower() for e in errors))

    def test_step4_ok_with_vivienda(self):
        self.assertEqual(bw.validate_step(3, _vivienda()), [])

    def test_step5_summary_always_passes(self):
        self.assertEqual(bw.validate_step(4, BuildingWizardData()), [])


class TestDataFromValues(unittest.TestCase):
    """Conversión con coma decimal y errores collectables."""

    def test_step1_text_fields(self):
        data = BuildingWizardData()
        errors = bw.data_from_values(
            0, {"name": "Torre Norte", "climate": CLIMATE_ZONES[2],
                "structural_system": STRUCTURAL_SYSTEMS[1],
                "facade_orientation": "Norte", "notes": "  mirador  "},
            data)
        self.assertEqual(errors, [])
        self.assertEqual(data.name, "Torre Norte")
        self.assertEqual(data.notes, "mirador")

    def test_step4_comma_decimals(self):
        data = BuildingWizardData()
        errors = bw.data_from_values(
            3, {"corridor_enabled": True, "cross_ventilation": False,
                "corridor_width_m": "1,5", "wall_thickness_m": "0,15",
                "door_width_m": "1,0", "door_height_m": "2,2",
                "window_width_m": "1,4", "window_height_m": "1,5",
                "window_sill_m": "1,0"}, data)
        self.assertEqual(errors, [])
        self.assertAlmostEqual(data.corridor_width_m, 1.5)
        self.assertAlmostEqual(data.wall_thickness_m, 0.15)
        self.assertFalse(data.cross_ventilation)

    def test_step4_conversion_error_collected(self):
        data = BuildingWizardData()
        errors = bw.data_from_values(
            3, {"corridor_enabled": True, "cross_ventilation": True,
                "corridor_width_m": "ancho", "wall_thickness_m": "0,2",
                "door_width_m": "0,9", "door_height_m": "2,1",
                "window_width_m": "1,2", "window_height_m": "1,2",
                "window_sill_m": "0,9"}, data)
        self.assertTrue(errors)
        self.assertIn("Ancho del pasillo", errors[0])


class TestOrdenYColocacion(unittest.TestCase):
    """Orden por relaciones, geometría en fila y muros fusionados."""

    def test_order_follows_relation_chains(self):
        data = BuildingWizardData()
        data.rooms = [RoomSpec(name="A"), RoomSpec(name="B"),
                      RoomSpec(name="C")]
        data.relations = [RelationSpec("A", "C", "Adyacente a", False)]
        ordered = bw.order_rooms_for_level(data.rooms, data.relations)
        # C es vecina declarada de A: queda consecutiva.
        self.assertEqual([r.name for r in ordered][:2], ["A", "C"])
        self.assertIn("B", [r.name for r in ordered])

    def test_order_ignores_relations_from_other_levels(self):
        data = BuildingWizardData()
        data.rooms = [RoomSpec(name="A", level_ref="PB"),
                      RoomSpec(name="B", level_ref="P1")]
        data.relations = [RelationSpec("A", "B", "Adyacente a", False)]
        ordered = bw.order_rooms_for_level(data.rooms, data.relations)
        self.assertEqual([r.name for r in ordered], ["A", "B"])

    def test_order_deterministic_without_relations(self):
        data = BuildingWizardData()
        rooms = [RoomSpec(name=n) for n in ("B", "A", "C")]
        self.assertEqual([r.name for r in
                          bw.order_rooms_for_level(rooms, [])],
                         ["B", "A", "C"])

    def test_rect_segments_clockwise(self):
        pr = bw.PlacedRoom(name="X", space_type="ROOM", level="PB",
                           x=1.0, y=2.0, w=4.0, d=3.0)
        self.assertEqual(bw.rect_segments(pr)[0],
                         ((1.0, 2.0), (5.0, 2.0)))
        self.assertEqual(bw.rect_segments(pr)[1],
                         ((5.0, 2.0), (5.0, 5.0)))
        self.assertEqual(bw.rect_segments(pr)[2],
                         ((5.0, 5.0), (1.0, 5.0)))
        self.assertEqual(bw.rect_segments(pr)[3],
                         ((1.0, 5.0), (1.0, 2.0)))

    def test_merge_walls_shared_partition_is_one_wall(self):
        data = _vivienda()
        layouts, _advisories = bw.build_layout(data)
        layout = layouts[0]
        # 6 locales + pasillo: sin fusión serían 28 muros; fusionados,
        # mucho menos. Y la partición Sala|Comedor es UN muro con dos
        # orígenes.
        self.assertEqual(len(layout.walls), 13)
        partition = next(w for w in layout.walls
                         if w["start"] == (4.0, 0.0)
                         and w["end"] == (4.0, 3.0))
        self.assertEqual(set(partition["sources"]), {"Sala", "Comedor"})

    def test_corridor_touches_every_room_via_front_wall(self):
        data = _vivienda()
        layout = bw.build_layout(data)[0][0]
        corridor = layout.corridor
        assert corridor is not None
        self.assertAlmostEqual(corridor.y, -data.corridor_width_m)
        front = next(w for w in layout.walls
                     if w["start"] == (0.0, 0.0)
                     and w["end"] == (18.3, 0.0))
        self.assertIn(corridor.name, front["sources"])
        self.assertEqual(len(front["sources"]), 7)  # 6 locales + pasillo

    def test_layout_deterministic(self):
        data = _vivienda()
        first = bw.build_layout(data)[0]
        second = bw.build_layout(data)[0]
        self.assertEqual([(w["start"], w["end"]) for w in first[0].walls],
                         [(w["start"], w["end"]) for w in second[0].walls])


class TestPuertasVentanas(unittest.TestCase):
    """Puertas declaradas + automáticas + entrada; ventanas de fachada."""

    def test_every_room_gets_corridor_door_plus_entrance(self):
        data = _vivienda()
        layout = bw.build_layout(data)[0][0]
        to_corridor = [d for d in layout.doors
                       if d.note.endswith("→ pasillo")]
        self.assertEqual(len(to_corridor), 6)
        entrance = [d for d in layout.doors if d.note == "entrada principal"]
        self.assertEqual(len(entrance), 1)

    def test_declared_door_is_extra_on_partition(self):
        data = _vivienda()
        data.relations = [RelationSpec("Sala", "Comedor", "Adyacente a",
                                       True)]
        layout = bw.build_layout(data)[0][0]
        between = [d for d in layout.doors
                   if d.note == "entre Sala y Comedor"]
        self.assertEqual(len(between), 1)
        self.assertAlmostEqual(between[0].offset_m, (3.0 - 0.9) / 2.0)
        # y el acceso al pasillo NO se pierde:
        self.assertEqual(
            len([d for d in layout.doors
                 if d.note.endswith("→ pasillo")]), 6)

    def test_declared_door_not_adjacent_is_omitted_with_advisory(self):
        data = _vivienda()
        # Sala queda en el centro de DOS cadenas: solo la primera
        # vecina (Comedor) comparte partición; Sala-Cocina no puede.
        data.relations = [RelationSpec("Sala", "Comedor", "Adyacente a",
                                       True),
                          RelationSpec("Sala", "Cocina", "Adyacente a",
                                       True)]
        layout, _ = bw.build_layout(data)
        notes = [d.note for d in layout[0].doors]
        self.assertIn("entre Sala y Comedor", notes)
        self.assertNotIn("entre Sala y Cocina", notes)
        self.assertTrue(any("no quedaron pegados" in a
                            for a in layout[0].advisories))

    def test_without_corridor_entrance_and_enfilade(self):
        data = _vivienda()
        data.corridor_enabled = False
        layout = bw.build_layout(data)[0][0]
        self.assertIsNone(layout.corridor)
        doors = layout.doors
        self.assertEqual(len(doors), 6)  # entrada (local 1) + 5 enfilada
        self.assertTrue(any(d.note == "entrada por Sala" for d in doors))
        self.assertTrue(any("entre Sala y Comedor" in d.note
                            for d in doors))
        # sin puerta duplicada de entrada:
        self.assertEqual(
            len([d for d in doors if d.note.startswith("entrada")]), 1)

    def test_windows_on_back_facade_only(self):
        data = _vivienda()
        layout = bw.build_layout(data)[0][0]
        # Baño no pide ventana; los otros 5 sí.
        self.assertEqual(len(layout.windows), 5)
        for window in layout.windows:
            self.assertTrue(window.note.endswith("→ fachada"))
            wall = layout.walls[window.wall_index]
            self.assertGreater(wall["end"][1], 0.0)  # fondo exterior

    def test_entrance_only_on_first_level(self):
        data = _vivienda()
        data.levels.append(LevelSpec("Piso 1", 3.0))
        data.rooms += bw.preset_rooms("Vivienda", "Piso 1")
        layouts, _ = bw.build_layout(data)
        self.assertEqual(len(layouts), 2)
        entrances = sum(1 for layout in layouts
                        for d in layout.doors
                        if d.note == "entrada principal")
        self.assertEqual(entrances, 1)

    def test_openings_carry_wall_index(self):
        data = _vivienda()
        layout = bw.build_layout(data)[0][0]
        for opening in layout.doors + layout.windows:
            self.assertGreaterEqual(opening.wall_index, 0)
            self.assertLess(opening.wall_index, len(layout.walls))


class TestEstructura(unittest.TestCase):
    """Regla explicable de muros portantes según el sistema."""

    def test_portantes_marks_exterior_not_partitions(self):
        data = _vivienda()
        data.structural_system = "Muros portantes"
        layout = bw.build_layout(data)[0][0]
        partition = next(w for w in layout.walls
                         if w["start"] == (4.0, 0.0)
                         and w["end"] == (4.0, 3.0))
        facade = next(w for w in layout.walls
                      if w["start"] == (0.0, 0.0))
        self.assertFalse(bw.structural_flag(partition,
                                            data.structural_system))
        self.assertTrue(bw.structural_flag(facade,
                                           data.structural_system))

    def test_portico_marks_nothing(self):
        for wall in bw.build_layout(_vivienda())[0][0].walls:
            self.assertFalse(bw.structural_flag(wall,
                                                "Pórtico de hormigón"))

    def test_horizontal_merged_facade_is_not_partition(self):
        # Sala y Comedor comparten fondo 3,0: su fachada trasera se
        # fusiona y NO es partición (es fachada exterior).
        data = _vivienda()
        data.structural_system = "Muros portantes"
        layout = bw.build_layout(data)[0][0]
        merged_back = next(w for w in layout.walls
                           if w["start"] == (0.0, 3.0)
                           and w["end"] == (7.0, 3.0))
        self.assertEqual(set(merged_back["sources"]),
                         {"Sala", "Comedor"})
        self.assertTrue(bw.structural_flag(merged_back,
                                           data.structural_system))


class TestRequerimientos(unittest.TestCase):
    """Requerimientos desde el DNA y avisos que no bloquean."""

    def test_room_requirements_sections(self):
        data = _vivienda()
        room = data.rooms[0]  # Sala → LIVING_ROOM
        req = bw.room_requirements(data, room)
        self.assertEqual(set(req), {"climaticos", "arquitectonicos",
                                    "estructurales", "origen"})
        self.assertIn("zona_climatica", req["climaticos"])
        self.assertEqual(req["arquitectonicos"]["tipo"], "LIVING_ROOM")
        # v3.43.0: el mínimo de la Sala baja de 12 a 9 m2 (DNA de
        # vivienda social)
        self.assertEqual(req["arquitectonicos"]["area_minima_m2"], 9.0)
        self.assertEqual(req["estructurales"]["sistema"],
                         data.structural_system)

    def test_room_requirements_with_unknown_type(self):
        """Un tipo sin DNA registrado no rompe: requerimientos básicos."""
        data = _vivienda()
        data.rooms[0].space_type = "SIN_DNA"
        req = bw.room_requirements(data, data.rooms[0], ctx=None)
        self.assertNotIn("area_minima_m2", req["arquitectonicos"])
        self.assertIn("zona_climatica", req["climaticos"])

    def test_dna_advisories_small_room_and_wet_zone(self):
        data = _vivienda()
        data.rooms[0].width_m = 2.0   # Sala de 6 m² < 9 m² mínimos
        data.rooms[0].depth_m = 3.0
        advisories = bw.dna_advisories(data)
        # v3.43.0: el mínimo de la Sala es 9 m2
        self.assertTrue(any("al menos 9.0" in a for a in advisories))
        self.assertTrue(any("zona húmeda" in a for a in advisories))

    def test_dna_advisories_clean_for_vivienda(self):
        area_advisories = [a for a in bw.dna_advisories(_vivienda())
                           if "al menos" in a]
        self.assertEqual(area_advisories, [])

    def test_suggest_relations_from_dna(self):
        data = _vivienda()
        suggestions = bw.suggest_relations(data)
        pairs = {(s.a_name, s.b_name) for s in suggestions}
        self.assertIn(("Sala", "Cocina"), pairs)
        # sin duplicados invertidos:
        self.assertNotIn(("Cocina", "Sala"), pairs)

    def test_suggest_respects_same_level(self):
        data = _vivienda()
        data.rooms.append(RoomSpec(name="Oficina P1", space_type="OFFICE",
                                   level_ref="Planta Baja"))
        data.levels.append(LevelSpec("Piso 1", 3.0))
        data.rooms.append(RoomSpec(name="Sala P1", space_type="LIVING_ROOM",
                                   level_ref="Piso 1"))
        pairs = {(s.a_name, s.b_name)
                 for s in bw.suggest_relations(data)}
        for a, b in pairs:
            room_a = data.room(a)
            room_b = data.room(b)
            assert room_a and room_b
            self.assertEqual(room_a.level_ref, room_b.level_ref)


class TestPlan(unittest.TestCase):
    """Plan declarativo: orden, niveles existentes y vanos apuntados."""

    def test_op_order_and_counts(self):
        data = _vivienda()
        data.relations = [RelationSpec("Sala", "Comedor", "Adyacente a",
                                       True)]
        plan, layouts, _ = bw.build_plan(data)
        ops = [op for op, _p in plan]
        self.assertEqual(ops[0], "BUILDING")
        self.assertEqual(ops[1], "LEVEL")
        self.assertEqual(ops.count("SPACE"), 7)   # 6 locales + pasillo
        self.assertEqual(ops.count("WALL"), 13)
        self.assertEqual(ops.count("DOOR"), 8)    # 6 pasillo + extra + entrada
        self.assertEqual(ops.count("WINDOW"), 5)
        self.assertEqual(ops.count("RELATION"), 1)
        self.assertEqual(len(layouts), 1)

    def test_existing_levels_and_building_are_reused(self):
        data = _vivienda()
        plan, _layouts, _ = bw.build_plan(data,
                                          existing_levels=["Planta Baja"],
                                          has_building=True)
        ops = [op for op, _p in plan]
        self.assertNotIn("BUILDING", ops)
        self.assertNotIn("LEVEL", ops)

    def test_level_elevations_cumulative(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec("PB", 3.0), LevelSpec("P1", 3.2),
                       LevelSpec("P2", 2.8)]
        self.assertEqual(bw.level_elevations(data), [0.0, 3.0, 6.2])

    def test_opening_wall_indexes_within_range(self):
        data = _vivienda()
        plan, layouts, _ = bw.build_plan(data)
        walls_per_level = {}
        for op, params in plan:
            if op == "WALL":
                walls_per_level[params["level_ref"]] = \
                    walls_per_level.get(params["level_ref"], 0) + 1
        for op, params in plan:
            if op in ("DOOR", "WINDOW"):
                self.assertLess(params["wall_index"],
                                walls_per_level[params["level_ref"]])
                self.assertGreaterEqual(params["wall_index"], 0)


class TestApplyEndToEnd(ARQGenTestCase):
    """Ejecución end-to-end por las fachadas oficiales."""

    def _context(self):
        return self.application.create_project(
            self.project_path("edificio.arqgen"),
            name="Proyecto Edificación")

    def test_apply_creates_full_building(self):
        context = self._context()
        try:
            data = _vivienda()
            data.relations = [RelationSpec("Sala", "Comedor",
                                           "Adyacente a", True)]
            created = bw.apply_plan(data, context)
            self.assertTrue(created["building"])
            self.assertEqual(created["levels_created"], 1)
            self.assertEqual(created["spaces"], 7)
            self.assertEqual(created["walls"], 13)
            self.assertEqual(created["doors"], 8)
            self.assertEqual(created["windows"], 5)
            self.assertEqual(created["relations"], 1)
            pid = context.project.id
            self.assertEqual(
                len(context.architecture.list("BUILDING", pid)), 1)
            self.assertEqual(
                len(context.architecture.list("SPACE", pid)), 7)
            self.assertEqual(
                len(context.architecture.list("WALL", pid)), 13)
            self.assertEqual(
                len(context.architecture.list("DOOR", pid)), 8)
            self.assertEqual(
                len(context.architecture.list("WINDOW", pid)), 5)
        finally:
            context.close()

    def test_levels_linked_to_building(self):
        context = self._context()
        try:
            data = _vivienda()
            data.levels.append(LevelSpec("Piso 1", 3.0))
            data.rooms += bw.preset_rooms("Vivienda", "Piso 1")
            created = bw.apply_plan(data, context)
            self.assertEqual(created["levels_created"], 2)
            pid = context.project.id
            building = context.architecture.list("BUILDING", pid)[0]
            levels = context.architecture.list("LEVEL", pid)
            self.assertEqual(len(levels), 2)
            for level in levels:
                self.assertEqual(level.building_id, building.id)
            self.assertEqual(building.floors, 2)
        finally:
            context.close()

    def test_requirements_metadata_persisted(self):
        context = self._context()
        try:
            data = _vivienda()
            bw.apply_plan(data, context)
            pid = context.project.id
            building = context.architecture.list("BUILDING", pid)[0]
            self.assertIn("edificacion", building.metadata)
            self.assertEqual(
                building.metadata["edificacion"]["clima"],
                data.climate)
            space = next(s for s in
                         context.architecture.list("SPACE", pid)
                         if s.name == "Sala")
            req = space.metadata["requerimientos"]
            self.assertEqual(req["arquitectonicos"]["tipo"],
                             "LIVING_ROOM")
            self.assertEqual(req["climaticos"]["zona_climatica"],
                             data.climate)
            wall = next(w for w in
                        context.architecture.list("WALL", pid)
                        if w.start == (4.0, 0.0)
                        and w.end == (4.0, 3.0))
            self.assertFalse(wall.metadata["portante"])
            door = context.architecture.list("DOOR", pid)[0]
            self.assertEqual(door.metadata["origen"],
                             "asistente de edificación")
        finally:
            context.close()

    def test_relationships_use_created_codes_not_names(self):
        context = self._context()
        try:
            # Un local homónimo PREEXISTENTE no debe capturar la relación.
            from services.architecture_service import ArchitectureService
            arch = ArchitectureService(context)
            arch.create_level(name="Planta Baja")
            arch.create_space(level_ref="Planta Baja", name="Sala",
                              space_type="ROOM",
                              boundary=[(100, 100), (104, 100),
                                        (104, 103), (100, 103)])
            data = _vivienda()
            data.relations = [RelationSpec("Sala", "Comedor",
                                           "Adyacente a", True)]
            bw.apply_plan(data, context)
            pid = context.project.id
            relationships = context.architecture.list(
                "SPACE_RELATIONSHIP", pid)
            self.assertEqual(len(relationships), 1)
            rel = relationships[0]
            spaces = {s.id: s for s in
                      context.architecture.list("SPACE", pid)}
            self.assertIn(rel.from_space_id, spaces)
            from_space = spaces[rel.from_space_id]
            to_space = spaces[rel.to_space_id]
            self.assertEqual(from_space.name, "Sala")
            self.assertEqual(to_space.name, "Comedor")
            # La Sala ligada es la del lote nuevo (metadatos), no la vieja.
            self.assertIn("requerimientos", from_space.metadata)
        finally:
            context.close()

    def test_openings_hang_on_real_walls(self):
        context = self._context()
        try:
            data = _vivienda()
            bw.apply_plan(data, context)
            pid = context.project.id
            walls = {w.id for w in context.architecture.list("WALL", pid)}
            openings = (context.architecture.list("DOOR", pid)
                        + context.architecture.list("WINDOW", pid))
            for opening in openings:
                self.assertIn(opening.wall_id, walls)
        finally:
            context.close()

    def test_apply_is_audited_and_evented(self):
        context = self._context()
        try:
            bw.apply_plan(_vivienda(), context)
            commands = {a.get("command") for a in
                        context.audit_repo.recent(limit=400)}
            self.assertIn("CREATE_ENTITY", commands)
            self.assertIn("UPDATE_ENTITY", commands)
            events = {e.get("type") for e in
                      context.events_repo.recent(limit=400)}
            self.assertIn("OBJECT_CREATED", events)
            self.assertIn("SPACE_CHANGED", events)
        finally:
            context.close()

    def test_second_run_reuses_level_and_building(self):
        context = self._context()
        try:
            data = _vivienda()
            bw.apply_plan(data, context)
            first_levels = len(context.architecture.list(
                "LEVEL", context.project.id))
            first_buildings = len(context.architecture.list(
                "BUILDING", context.project.id))
            # Segunda pasada: otro bloque de locales sobre el MISMO nivel.
            data2 = BuildingWizardData(name="Anexo")
            data2.levels = [LevelSpec(name="Planta Baja", height_m=3.0)]
            data2.rooms = [RoomSpec(name="Depósito Anexo",
                                    space_type="STOREROOM",
                                    width_m=2.0, depth_m=1.5,
                                    level_ref="Planta Baja",
                                    with_window=False)]
            created2 = bw.apply_plan(data2, context)
            self.assertEqual(created2["levels_created"], 0)
            self.assertEqual(created2["levels_reused"], 1)
            self.assertEqual(
                len(context.architecture.list("LEVEL",
                                              context.project.id)),
                first_levels)
            self.assertEqual(
                len(context.architecture.list("BUILDING",
                                              context.project.id)),
                first_buildings)
        finally:
            context.close()

    def test_summary_mentions_counts_and_advisories(self):
        context = self._context()
        try:
            data = _vivienda()
            text = bw.step_summary(data, context)
            for word in ("Casa Test", "Niveles", "Locales", "muros",
                         "puertas", "ventanas", "Requerimientos"):
                self.assertIn(word, text)
        finally:
            context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestBuildingWindow(ARQGenTestCase):
    """Ventana real: el asistente de edificación abre y genera."""

    def setUp(self):
        super().setUp()
        from ui.app_window import ARQGenWindow
        self.context = self._context_gui()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def _context_gui(self):
        return self.application.create_project(
            self.project_path("edificio_gui.arqgen"),
            name="Proyecto Edificación GUI")

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        super().tearDown()

    def _open(self):
        self.window.open_building_wizard()
        return self.window._building_dialog

    def test_button_tooltip_exists(self):
        from ui.help import TOOLTIPS
        self.assertIn("building_wizard", TOOLTIPS)

    def test_dialog_opens_with_seven_steps(self):
        dialog = self._open()
        try:
            self.assertIn("Paso 1 de 7",
                          dialog._bld_step_var.get())
            self.assertEqual(dialog._bld_state["step"], 0)
            # Los pasos nuevos existen: bioclima y variantes.
            for key in ("usage", "lot_w", "lot_d", "construction",
                        "protect", "eaves", "inst_vars",
                        "variant_tree", "variant_canvas"):
                self.assertIn(key, dialog._bld_widgets)
        finally:
            dialog.destroy()

    def test_validation_blocks_empty_name(self):
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            widgets["name"].delete(0, "end")
            with mock.patch("ui.app_window.messagebox.showwarning") as warn:
                dialog._bld_next()
                warn.assert_called_once()
            self.assertEqual(dialog._bld_state["step"], 0)
        finally:
            dialog.destroy()

    def test_full_flow_generates_building(self):
        pid = self.context.project.id
        before_space = len(self.context.architecture.list("SPACE", pid))
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            widgets["name"].delete(0, "end")
            widgets["name"].insert(0, "Edificio de pruebas")
            dialog._bld_next()  # → paso 2
            dialog._bld_data.levels.append(LevelSpec("Piso 1", 3.0))
            dialog._bld_refresh["levels"]()
            dialog._bld_next()  # → paso 3
            dialog._bld_data.rooms = bw.preset_rooms(
                "Vivienda", dialog._bld_data.levels[0].name)
            dialog._bld_refresh["rooms"]()
            dialog._bld_next()  # → paso 4
            dialog._bld_next()  # → paso 5 (bioclimática)
            dialog._bld_next()  # → paso 6 (variantes)
            self.assertTrue(dialog._bld_state["variants"])
            # el usuario elige la variante LINEAL (el trazado clásico)
            dialog._bld_state["variant"] = next(
                v for v in dialog._bld_state["variants"]
                if v.scheme == "lineal" and not v.mirror)
            dialog._bld_next()  # → paso 7 (resumen)
            self.assertIn("Paso 7 de 7", dialog._bld_step_var.get())
            summary = widgets["summary"].get("1.0", "end")
            self.assertIn("Edificio de pruebas", summary)
            with mock.patch("ui.app_window.messagebox.showinfo"), \
                    mock.patch("ui.app_window.messagebox.showwarning"):
                dialog._bld_next()  # genera
            self.window.update()
        finally:
            dialog.destroy()
        pid = self.context.project.id
        spaces = self.context.architecture.list("SPACE", pid)
        # v2.5.0: dos niveles → escalera automática y núcleo rígido en
        # esquina (6 locales + escalera + núcleo + pasillo = 9 en PB).
        self.assertEqual(len(spaces), before_space + 9)
        walls = self.context.architecture.list("WALL", pid)
        self.assertEqual(len(walls), 17)
        doors = self.context.architecture.list("DOOR", pid)
        self.assertEqual(len(doors), 9)  # 6 al pasillo + escalera + núcleo + entrada
        nucleo = next(s for s in spaces
                      if s.name.startswith("Núcleo rígido"))
        self.assertEqual(
            nucleo.metadata["requerimientos"]["arquitectonicos"]["tipo"],
            "CORE")
        levels = self.context.architecture.list("LEVEL", pid)
        self.assertEqual(len(levels), 2)
        sala = next(s for s in spaces
                    if s.name == "Sala"
                    and s.metadata.get("requerimientos"))
        self.assertEqual(
            sala.metadata["requerimientos"]["climaticos"]["zona_climatica"],
            CLIMATE_ZONES[0])

    def test_back_button_preserves_data(self):
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            widgets["name"].delete(0, "end")
            widgets["name"].insert(0, "Mi edificio")
            dialog._bld_next()
            self.assertEqual(dialog._bld_state["step"], 1)
            dialog._bld_back()
            self.assertEqual(dialog._bld_state["step"], 0)
            self.assertEqual(dialog._bld_data.name, "Mi edificio")
        finally:
            dialog.destroy()

    def test_room_level_combo_syncs_with_new_levels(self):
        dialog = self._open()
        try:
            dialog._bld_data.levels.append(LevelSpec("Piso 2", 2.8))
            dialog._bld_show(1)  # _show sincroniza combos
            combo = dialog._bld_widgets["room_level"]
            self.assertIn("Piso 2", combo.cget("values"))
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
