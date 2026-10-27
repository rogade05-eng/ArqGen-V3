"""TEMA HOSPITALARIO v2.2.0: policlínico y hospital en el asistente.

Lo pedido por el usuario («me falta el tema hospitalario»): la red de
salud completa en el asistente de edificación — usos Policlínico y
Hospital, DNA técnico de sus locales (quirófano, urgencias,
esterilización, hospitalización, laboratorio, imagenología, farmacia,
enfermería), programa MULTI-NIVEL del hospital, puertas críticas
sugeridas por uso e instalaciones recomendadas (A/C y gas medicinal).
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import BuildingWizardData


def _hospital_data() -> BuildingWizardData:
    """Hospital generado por el asistente (programa + relaciones)."""
    data = BuildingWizardData()
    data.usage_type = "Hospital"
    data.installations = list(bw.suggested_installations("Hospital"))
    bw.apply_usage_program(data)
    return data


class TestUsosHospitalarios(ARQGenTestCase):
    """Paso 1: la red de salud entre los usos sociales."""

    def test_usages_incluyen_red_de_salud(self):
        self.assertIn("Hospital", bw.USAGE_TYPES)
        self.assertIn("Policlínico", bw.USAGE_TYPES)
        for usage in ("Hospital", "Policlínico"):
            self.assertIn(usage, bw.PROGRAM_PRESETS)
            self.assertIn(usage, bw.USAGE_HINTS)
            self.assertTrue(bw.USAGE_HINTS[usage].strip())

    def test_preset_hospital_incluye_locales_criticos(self):
        rooms = bw.preset_rooms("Hospital", "Planta Baja")
        types = {r.space_type for r in rooms}
        for expected in ("OPERATING_ROOM", "STERILIZATION_ROOM", "WARD",
                         "EMERGENCY_ROOM", "IMAGING_ROOM", "LABORATORY",
                         "PHARMACY", "NURSE_STATION"):
            self.assertIn(expected, types)
        self.assertGreaterEqual(len(rooms), 18)

    def test_preset_policlinico_en_un_nivel(self):
        rooms = bw.preset_rooms("Policlínico", "Planta Baja")
        self.assertGreaterEqual(len(rooms), 9)
        types = {r.space_type for r in rooms}
        self.assertIn("EMERGENCY_ROOM", types)
        self.assertIn("IMAGING_ROOM", types)
        self.assertIn("LABORATORY", types)

    def test_quirofano_supera_36_m2(self):
        rooms = bw.preset_rooms("Hospital", "Planta Baja")
        quirófanos = [r for r in rooms if r.space_type == "OPERATING_ROOM"]
        self.assertTrue(quirófanos)
        for room in quirófanos:
            self.assertGreaterEqual(room.width_m * room.depth_m, 36.0)

    def test_hospitalizacion_supera_28_m2(self):
        rooms = bw.preset_rooms("Hospital", "Planta Baja")
        salas = [r for r in rooms if r.space_type == "WARD"]
        self.assertTrue(salas)
        for room in salas:
            self.assertGreaterEqual(room.width_m * room.depth_m, 28.0)


class TestProgramaMultiNivel(ARQGenTestCase):
    """El hospital se reparte en PB / P1 / P2 creando los niveles."""

    def test_hospital_crea_niveles_faltantes(self):
        data = BuildingWizardData()          # un solo nivel por defecto
        data.usage_type = "Hospital"
        rooms, relations = bw.apply_usage_program(data)
        self.assertGreaterEqual(rooms, 18)
        self.assertGreaterEqual(relations, 3)
        self.assertEqual(len(data.levels), 3)
        self.assertEqual(data.levels[0].name, "Planta Baja")
        self.assertEqual(data.levels[1].name, "Planta 1")
        self.assertEqual(data.levels[2].name, "Planta 2")
        # altura hospitalaria de los niveles añadidos (plenum de A/C)
        self.assertAlmostEqual(data.levels[1].height_m, 3.2)
        self.assertAlmostEqual(data.levels[2].height_m, 3.2)

    def test_locales_repartidos_por_nivel(self):
        data = _hospital_data()
        pb = data.rooms_of_level(data.levels[0].name)
        p1 = data.rooms_of_level(data.levels[1].name)
        p2 = data.rooms_of_level(data.levels[2].name)
        self.assertTrue(any(r.space_type == "EMERGENCY_ROOM" for r in pb))
        self.assertTrue(any(r.space_type == "IMAGING_ROOM" for r in pb))
        self.assertTrue(any(r.space_type == "OPERATING_ROOM" for r in p1))
        self.assertTrue(any(r.space_type == "STERILIZATION_ROOM"
                            for r in p1))
        self.assertTrue(any(r.space_type == "WARD" for r in p2))
        self.assertTrue(any(r.space_type == "NURSE_STATION" for r in p2))
        for room in data.rooms:
            self.assertIn(room.level_ref, data.level_names())

    def test_niveles_existentes_se_respetan(self):
        data = BuildingWizardData()
        data.usage_type = "Hospital"
        data.levels = [bw.LevelSpec(name="PB propia", height_m=3.4),
                       bw.LevelSpec(name="Alta", height_m=3.0),
                       bw.LevelSpec(name="Última", height_m=3.0)]
        bw.apply_usage_program(data)
        self.assertEqual([lv.name for lv in data.levels],
                         ["PB propia", "Alta", "Última"])
        self.assertAlmostEqual(data.levels[0].height_m, 3.4)
        # v2.7.0: el programa hospitalario suma la UCI (2 camas).
        # v3.20.0: las especialidades pedidas (tomografía, fluoroscopio,
        # anatomía patológica, morgue, microbiología, nodo informático,
        # PGD y almacén) elevan el total de 21 a 30 locales.
        self.assertEqual(len(data.rooms), 30)

    def test_policlinico_no_crea_niveles(self):
        data = BuildingWizardData()
        data.usage_type = "Policlínico"
        bw.apply_usage_program(data)
        self.assertEqual(len(data.levels), 1)
        self.assertGreaterEqual(len(data.rooms), 9)


class TestDNAHospitalario(ARQGenTestCase):
    """Conocimiento técnico de los locales de salud."""

    def test_dna_tipos_hospitalarios_cargan(self):
        from app.paths import resource_path
        from domain.knowledge import SpaceDNARegistry
        registry = SpaceDNARegistry()
        count = registry.load_file(
            resource_path("knowledge", "space_dna.json"))
        self.assertGreaterEqual(count, 21)
        quirófano = registry.get("OPERATING_ROOM")
        self.assertEqual(quirófano.name_es, "Quirófano")
        self.assertGreaterEqual(quirófano.minimum_area, 36.0)
        self.assertTrue(quirófano.metadata.get("requiere_hvac"))
        self.assertTrue(registry.get("EMERGENCY_ROOM").emergency_access)
        self.assertTrue(registry.get("WARD").daylight)
        self.assertTrue(registry.get("WARD").ventilation)
        self.assertIn("radiacion", registry.get("IMAGING_ROOM").metadata)
        self.assertIn("STERILIZATION_ROOM", quirófano.preferred_adjacencies)

    def test_requerimientos_quirofano(self):
        data = _hospital_data()
        quirófano = next(r for r in data.rooms
                         if r.space_type == "OPERATING_ROOM")
        req = bw.room_requirements(data, quirófano)
        self.assertTrue(req["climaticos"].get("aire_acondicionado"))
        self.assertEqual(req["climaticos"].get("presion_requerida"),
                         "positiva")
        self.assertTrue(req["climaticos"].get("oxigeno_medicinal"))
        self.assertTrue(req["arquitectonicos"].get("zona_humeda"))

    def test_requerimientos_rayos_x(self):
        data = _hospital_data()
        rayos = next(r for r in data.rooms if r.space_type == "IMAGING_ROOM")
        req = bw.room_requirements(data, rayos)
        self.assertIn("plomada",
                      req["arquitectonicos"].get("proteccion_radiologica",
                                                 ""))


class TestRelacionesYPuertas(ARQGenTestCase):
    """Relaciones del DNA con puertas críticas del uso social."""

    def test_puertas_criticas_hospital(self):
        data = _hospital_data()
        puertas = [(rel.a_name, rel.b_name) for rel in data.relations
                   if rel.with_door]
        self.assertTrue(puertas)
        quirófano = next(r for r in data.rooms
                         if r.space_type == "OPERATING_ROOM")
        esterilización = next(r for r in data.rooms
                              if r.space_type == "STERILIZATION_ROOM")
        self.assertTrue(any({a, b} == {quirófano.name, esterilización.name}
                            for a, b in puertas))
        ward = next(r for r in data.rooms if r.space_type == "WARD"
                    and r.level_ref == data.levels[2].name)
        enfermería = next(r for r in data.rooms
                          if r.space_type == "NURSE_STATION"
                          and r.level_ref == data.levels[2].name)
        self.assertTrue(any({a, b} == {ward.name, enfermería.name}
                            for a, b in puertas))

    def test_relaciones_hospitalarias_sin_puerta_explícita(self):
        data = _hospital_data()
        sin_puerta = [rel for rel in data.relations if not rel.with_door]
        self.assertTrue(sin_puerta)
        names = {r.name for r in data.rooms}
        for rel in data.relations:
            self.assertIn(rel.a_name, names)
            self.assertIn(rel.b_name, names)

    def test_relaciones_sin_puerta_para_usos_generales(self):
        data = BuildingWizardData()
        data.usage_type = "Vivienda"
        bw.apply_usage_program(data)
        for rel in data.relations:
            self.assertFalse(rel.with_door)


class TestInstalacionesYAvisos(ARQGenTestCase):
    """Módulos sugeridos y avisos técnicos sin bloquear."""

    def test_instalaciones_sugeridas_hospital(self):
        sugeridos = bw.suggested_installations("Hospital")
        for módulo in ("Eléctrica", "Sanitaria",
                       "Ventilación mecánica / A/C", "Gas"):
            self.assertIn(módulo, sugeridos)

    def test_instalaciones_sugeridas_policlinico(self):
        sugeridos = bw.suggested_installations("Policlínico")
        self.assertIn("Ventilación mecánica / A/C", sugeridos)
        self.assertIn("Gas", sugeridos)

    def test_instalaciones_sugeridas_por_defecto(self):
        self.assertEqual(bw.suggested_installations("Vivienda"),
                         ("Eléctrica", "Sanitaria"))

    def test_avisos_sin_a_c_en_quirofano(self):
        data = _hospital_data()
        data.installations = ["Eléctrica", "Sanitaria"]   # sin A/C ni gas
        avisos = bw.dna_advisories(data)
        self.assertTrue(any("climatización" in aviso for aviso in avisos))
        self.assertTrue(any("oxígeno medicinal" in aviso
                            for aviso in avisos))

    def test_sin_avisos_de_a_c_con_modulo_activo(self):
        data = _hospital_data()   # instalaciones sugeridas (A/C y gas)
        avisos = bw.dna_advisories(data)
        self.assertFalse(any("climatización" in aviso for aviso in avisos))
        self.assertFalse(any("oxígeno medicinal" in aviso
                             for aviso in avisos))

    def test_avisos_rayos_x_radiacion(self):
        data = _hospital_data()
        avisos = bw.dna_advisories(data)
        self.assertTrue(any("radiación" in aviso for aviso in avisos))


class TestValidacionYGeneracion(ARQGenTestCase):
    """El hospital completo pasa validación y genera planta/variantes."""

    def test_datos_hospitalarios_validos_todos_los_pasos(self):
        data = _hospital_data()
        for step in range(5):
            self.assertEqual(bw.validate_step(step, data), [],
                             f"paso {step + 1}")

    def test_trazado_en_tres_niveles(self):
        data = _hospital_data()
        layouts, _avisos = bw.build_layout(data)
        self.assertEqual(len(layouts), 3)
        nombres = {r.name for layout in layouts for r in layout.rooms}
        self.assertIn("Urgencias", nombres)
        self.assertIn("Quirófano 1", nombres)
        self.assertIn("Sala de hospitalización 1", nombres)

    def test_variantes_de_planta_hospital(self):
        data = _hospital_data()
        variants = bw.generate_variants(data)
        # v2.3.0: 9 esquemas × espejo; el hospital trae todos.
        self.assertGreaterEqual(len(variants), 6)
        schemes = {v.scheme for v in variants}
        self.assertIn("en_H", schemes)      # el H, clásico hospitalario
        self.assertIn("en_cruz", schemes)   # la cruz, también
        self.assertEqual(variants[0].rank, 1)
        self.assertGreaterEqual(variants[0].score, variants[-1].score)

    def test_resumen_menciona_uso_y_quirofano(self):
        data = _hospital_data()
        texto = bw.step_summary(data)
        self.assertIn("hospital", texto.lower())
        self.assertIn("Quirófano 1", texto)
        self.assertIn("Urgencias", texto)

    def test_metadata_edificacion_con_uso(self):
        data = _hospital_data()
        meta = bw._building_metadata(data)
        self.assertEqual(meta["edificacion"]["uso_social"], "Hospital")
        self.assertEqual(meta["edificacion"]["niveles"], 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
