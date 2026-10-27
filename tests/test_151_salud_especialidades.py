"""ESPECIALIDADES DE SALUD (v3.20.0) — space_dna, programas hospitalarios,
iluminación por uso y mobiliario específico.

El usuario pidió «agrega más especialidades dentro del tema de salud»:
anatomía patológica, morgue, cuidados progresivos, tomografía, rayos X
(ya estaba), fluoroscopio, laboratorios (clínico ya estaba + el de
microbiología nuevo), nodo informático, PGD y almacenes. Este módulo
verifica que TODO el taller conoce las nuevas tipologías:

* DNA (resources/knowledge/space_dna.json): área mínima, altura,
  puerta de camilla y metadata técnica (blindaje, extracción, frío).
* Programas del asistente de edificación: policlínico y hospital
  (PB/P1) ampliados con las nuevas salas, pares de puertas y hint.
* Iluminación: lux por uso para los tipos hospitalarios (el quirófano
  manda con 1000 lux).
* Mobiliario: piezas y reglas específicas (mesa de autopsias, mesa de
  operaciones, rack de servidores) + el anclaje «fila» documentado
  desde la v1 y funcional desde aquí.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from domain import iluminacion as ilu
from domain import mobiliario as mob
from ui import building_wizard as bw
from ui import editor_espacios as edi


class _LocalRecto:
    """Recinto rectangular puro para colocar_en_local."""

    def __init__(self, ancho: float, fondo: float) -> None:
        self.boundary = [(0.0, 0.0), (ancho, 0.0), (ancho, fondo),
                         (0.0, fondo)]
        self._area = ancho * fondo

    def area_m2(self) -> float:
        return self._area


class TestDNASalud(ARQGenTestCase):
    """Las 9 especialidades nuevas viven en el DNA del proyecto."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("salud.arqgen"), name="Salud")

    NUEVAS = {
        "CT_ROOM": ("Tomografía (TAC)", 28.0, 1.2),
        "FLUOROSCOPY_ROOM": ("Fluoroscopio", 24.0, 1.2),
        "ANATOMY_PATHOLOGY": ("Anatomía patológica", 24.0, 1.2),
        "MORGUE": ("Morgue", 12.0, 1.2),
        "PROGRESSIVE_CARE": ("Cuidados progresivos", 24.0, 1.2),
        "MICROBIOLOGY_LAB": ("Laboratorio de microbiología", 16.0, 1.0),
        "SERVER_ROOM": ("Nodo informático", 8.0, 1.0),
        "WASTE_ROOM": ("Local PGD", 6.0, 1.2),
        "WAREHOUSE": ("Almacén", 10.0, 1.5),
    }

    def test_tipos_registrados_con_dna(self):
        registry = self.context.dna_registry
        for tipo, (nombre, minima, puerta) in self.NUEVAS.items():
            dna = registry.get(tipo)
            self.assertIsNotNone(dna, tipo)
            self.assertEqual(dna.name_es[:len(nombre)], nombre,
                             f"{tipo}: {dna.name_es}")
            self.assertGreaterEqual(float(dna.minimum_area), minima)
            neufert = dna.metadata.get("neufert") or {}
            self.assertEqual(
                float(neufert.get("puerta_m")), puerta,
                f"{tipo}: puerta de camilla o carga {puerta} m")
            self.assertTrue(dna.height and float(dna.height) >= 2.5)

    def test_metadata_tecnica_por_especialidad(self):
        registry = self.context.dna_registry
        # imagenología moderna con barrera plomada
        self.assertIn("radiacion", registry.get("CT_ROOM").metadata)
        self.assertIn("radiacion", registry.get("FLUOROSCOPY_ROOM").metadata)
        # extracción independiente en lo que huele
        self.assertIn("extraccion", registry.get("MORGUE").metadata)
        self.assertIn("extraccion", registry.get("WASTE_ROOM").metadata)
        self.assertIn("extraccion", registry.get("ANATOMY_PATHOLOGY").metadata)
        # frío en la morgue y clima 24/7 en el nodo
        self.assertIn("friocamara", registry.get("MORGUE").metadata)
        self.assertIn("sai", registry.get("SERVER_ROOM").metadata)
        # bioseguridad en microbiología
        self.assertIn("biosafety", registry.get("MICROBIOLOGY_LAB").metadata)

    def test_adyacencias_sensatas(self):
        registry = self.context.dna_registry
        self.assertIn("MORGUE",
                      registry.get("ANATOMY_PATHOLOGY")
                      .preferred_adjacencies)
        self.assertIn("ICU", registry.get("PROGRESSIVE_CARE")
                      .preferred_adjacencies)
        self.assertIn("EMERGENCY_ROOM",
                      registry.get("CT_ROOM").preferred_adjacencies)
        self.assertIn("WAREHOUSE",
                      registry.get("WASTE_ROOM").preferred_adjacencies)


class TestProgramasSalud(ARQGenTestCase):
    """El asistente de edificación propone las especialidades nuevas."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("programa.arqgen"), name="Programa")

    def test_policlinico_con_especialidades(self):
        rooms = bw.preset_rooms("Policlínico", "Planta Baja")
        types = {r.space_type for r in rooms}
        for esperado in ("CT_ROOM", "MICROBIOLOGY_LAB", "WAREHOUSE",
                         "WASTE_ROOM", "IMAGING_ROOM", "LABORATORY"):
            self.assertIn(esperado, types)

    def test_hospital_pb_con_todas_las_especialidades(self):
        rooms = bw.preset_rooms("Hospital", "Planta Baja")
        types = {r.space_type for r in rooms}
        for esperado in ("CT_ROOM", "FLUOROSCOPY_ROOM",
                         "ANATOMY_PATHOLOGY", "MORGUE",
                         "MICROBIOLOGY_LAB", "SERVER_ROOM", "WAREHOUSE",
                         "WASTE_ROOM"):
            self.assertIn(esperado, types)

    def test_hospital_p1_con_cuidados_progresivos(self):
        programas = dict(bw.LEVEL_PROGRAMS["Hospital"])
        p1 = [t for _n, t in programas.items()] \
            if isinstance(programas, dict) else None
        # LEVEL_PROGRAMS es una tupla de pares (nombre, programa)
        for _nombre, programa in bw.LEVEL_PROGRAMS["Hospital"]:
            tipos = {r[1] for r in programa}
            if "OPERATING_ROOM" in tipos:
                self.assertIn("PROGRESSIVE_CARE", tipos)

    def test_area_de_la_morgue_y_del_tac_según_dna(self):
        for room in bw.preset_rooms("Hospital", "Planta Baja"):
            dna = self.context.dna_registry.get(room.space_type)
            if dna is None:
                continue
            area = room.width_m * room.depth_m
            self.assertGreaterEqual(
                area, float(dna.minimum_area),
                f"{room.name}: {area:.1f} m2 < mínima "
                f"{dna.minimum_area} m2")

    def test_pares_de_puertas_hospitalarios(self):
        pares = {frozenset(p) for p in bw.USAGE_DOOR_PAIRS["Hospital"]}
        self.assertIn(frozenset(("EMERGENCY_ROOM", "CT_ROOM")), pares)
        self.assertIn(frozenset(("ANATOMY_PATHOLOGY", "MORGUE")), pares)
        self.assertIn(frozenset(("PROGRESSIVE_CARE", "NURSE_STATION")),
                      pares)
        self.assertIn(frozenset(("WAREHOUSE", "WASTE_ROOM")), pares)
        policlinico = {frozenset(p)
                       for p in bw.USAGE_DOOR_PAIRS["Policlínico"]}
        self.assertIn(frozenset(("LABORATORY", "MICROBIOLOGY_LAB")),
                      policlinico)

    def test_extra_pairs_une_las_nuevas(self):
        pares = {frozenset(p) for p in bw.USAGE_EXTRA_PAIRS["Hospital"]}
        self.assertIn(frozenset(("WARD", "PROGRESSIVE_CARE")), pares)
        self.assertIn(frozenset(("PROGRESSIVE_CARE", "ICU")), pares)

    def test_hints_mencionan_las_especialidades(self):
        for palabra in ("tomografía", "morgue", "PGD", "almacén"):
            self.assertIn(palabra, bw.USAGE_HINTS["Hospital"])
        self.assertIn("tomografía", bw.USAGE_HINTS["Policlínico"])

    def test_programa_hospital_completo_aplica(self):
        data = bw.BuildingWizardData()
        data.usage_type = "Hospital"
        rooms, _relations = bw.apply_usage_program(data)
        self.assertGreaterEqual(rooms, 30)
        tipos = {r.space_type for r in data.rooms}
        self.assertIn("CT_ROOM", tipos)
        self.assertIn("MORGUE", tipos)
        self.assertIn("PROGRESSIVE_CARE", tipos)


class TestIluminacionSalud(ARQGenTestCase):
    """Lux por uso hospitalario: del lecho (100) al quirófano (1000)."""

    def test_lux_de_los_tipos_hospitalarios(self):
        esperados = {
            "OPERATING_ROOM": 1000, "ANATOMY_PATHOLOGY": 500,
            "MICROBIOLOGY_LAB": 500, "SERVER_ROOM": 500,
            "CT_ROOM": 300, "FLUOROSCOPY_ROOM": 300, "MORGUE": 200,
            "PROGRESSIVE_CARE": 200, "WARD": 100, "WAREHOUSE": 100,
            "WASTE_ROOM": 100, "IMAGING_ROOM": 150,
        }
        for tipo, lux in esperados.items():
            self.assertEqual(ilu.lux_para(tipo), lux, tipo)

    def test_los_tipos_viejos_no_cambian(self):
        self.assertEqual(ilu.lux_para("OFFICE"), 500)
        self.assertEqual(ilu.lux_para("BEDROOM"), 100)
        self.assertEqual(ilu.lux_para("ROOM"), 150)

    def test_dimensionar_quirofano_con_led_panel(self):
        # 36 m2 x 1000 lux: N = ceil(E*A/(F*CU*MF)) con panel 3600 lm
        dims = ilu.dimensionar(36.0, 1000, "led_panel")
        self.assertGreaterEqual(dims["n_lamparas"], 4)
        self.assertGreater(dims["potencia_total_w"], 0.0)


class TestMobiliarioSalud(ARQGenTestCase):
    """Equipamiento específico y el anclaje «fila» en marcha."""

    def test_piezas_nuevas_en_catalogo(self):
        for clave in ("mesa_operaciones", "mesa_autopsia",
                      "rack_servidor"):
            self.assertIn(clave, mob.CATALOGO)

    def test_morgue_con_mesa_de_autopsias(self):
        piezas, avisos = mob.colocar_en_local(
            _LocalRecto(5.0, 3.5),
            mob.proponer_piezas("MORGUE", 17.5, ambito="social"),
            "social", "estandar")
        claves = [p["kind"] for p in piezas]
        self.assertIn("mesa_autopsia", claves)
        self.assertIn("camilla", claves)
        self.assertEqual(avisos, [])

    def test_quirofano_con_mesa_de_operaciones(self):
        piezas, avisos = mob.colocar_en_local(
            _LocalRecto(7.0, 6.0),
            mob.proponer_piezas("OPERATING_ROOM", 42.0, ambito="social"),
            "social", "estandar")
        self.assertIn("mesa_operaciones", [p["kind"] for p in piezas])
        self.assertEqual(avisos, [])

    def test_nodo_con_racks_en_fila(self):
        piezas, avisos = mob.colocar_en_local(
            _LocalRecto(3.0, 2.8),
            mob.proponer_piezas("SERVER_ROOM", 8.4, ambito="social"),
            "social", "estandar")
        racks = [p for p in piezas if p["kind"] == "rack_servidor"]
        self.assertGreaterEqual(len(racks), 2,
                                "el anclaje fila repite la pieza")
        # espaciados sin amontonarse (paso 1.5 m con racks de 0.6)
        xs = sorted(p["x"] for p in racks)
        self.assertGreaterEqual(round(xs[1] - xs[0], 2), 1.5)
        self.assertEqual(avisos, [])

    def test_almacen_con_estanterias_a_dos_manos(self):
        piezas, avisos = mob.colocar_en_local(
            _LocalRecto(5.0, 3.0),
            mob.proponer_piezas("WAREHOUSE", 15.0, ambito="social",
                                densidad="amplio"),
            "social", "amplio")
        estanterias = [p for p in piezas if p["kind"] == "estanteria"]
        self.assertGreaterEqual(len(estanterias), 4)
        self.assertEqual(avisos, [])

    def test_progresivos_e_uci_con_camas(self):
        for tipo, paso_cama in (("PROGRESSIVE_CARE", 12.0),
                                ("ICU", 18.0)):
            piezas, _avisos = mob.colocar_en_local(
                _LocalRecto(6.0, 5.0),
                mob.proponer_piezas(tipo, 30.0, ambito="social"),
                "social", "estandar")
            camas = [p for p in piezas if p["kind"] == "cama_individual"]
            self.assertGreaterEqual(len(camas), 1, tipo)

    def test_imagen_tomografia_y_fluoro_con_camilla(self):
        for tipo in ("IMAGING_ROOM", "CT_ROOM", "FLUOROSCOPY_ROOM"):
            piezas, _avisos = mob.colocar_en_local(
                _LocalRecto(6.0, 5.0),
                mob.proponer_piezas(tipo, 30.0, ambito="social"),
                "social", "estandar")
            self.assertIn("camilla", [p["kind"] for p in piezas], tipo)


class TestPuertasPorUsoSalud(ARQGenTestCase):
    """El asistente de local abre puertas de camilla donde toca."""

    def test_anchos_de_puerta_de_los_tipos_nuevos(self):
        esperados = {
            "CT_ROOM": 1.2, "FLUOROSCOPY_ROOM": 1.2, "MORGUE": 1.2,
            "ANATOMY_PATHOLOGY": 1.2, "PROGRESSIVE_CARE": 1.2,
            "WASTE_ROOM": 1.2, "MICROBIOLOGY_LAB": 1.0,
            "SERVER_ROOM": 1.0, "WAREHOUSE": 1.5,
        }
        for tipo, ancho in esperados.items():
            self.assertEqual(edi.ancho_puerta_por_uso(tipo), ancho, tipo)


if __name__ == "__main__":
    unittest.main()
