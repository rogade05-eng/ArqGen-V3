"""P3 de la comparación Architechtures (v3.32.0): MULTIPLICADORES DE
NIVELES / REPETICIÓN DE PLANTAS.

La idea Architechtures que faltaba: diseñas la planta tipo UNA vez y
le pides «×N» — el edificio entero (niveles, locales, muros, puertas,
ventanas, cotas) sale multiplicado y coherente:

* ``LevelSpec.repeat`` (1 = planta única: identidad total, cero
  impacto en los planes previos).
* ``bwiz.repeat_de`` — multiplicador SANO (nunca lanza, techo 50).
* ``bwiz.niveles_expandidos`` — cada nivel sale «repeat» veces con
  nombres únicos («Planta Tipo 2», «Planta Tipo 3»…).
* ``bwiz.expandir_datos`` — niveles + locales duplicados por copia con
  «level_ref» apuntando a cada copia; las relaciones son globales (por
  nombre de local) y NO se duplican.
* ``bwiz.level_elevations`` — cotas sobre los niveles YA expandidos:
  una planta tipo ×3 empuja la cota de todo lo que sigue.
* ``build_plan`` y ``generate_variants`` expanden solos: el plan y la
  puntuación de variantes salen sobre el EDIFICIO entero.
"""

from __future__ import annotations

import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bwiz
from ui.building_wizard import (
    BuildingWizardData,
    LevelSpec,
    RelationSpec,
    RoomSpec,
)


def _data_con_planta_tipo() -> BuildingWizardData:
    """PB de 1 local + «Planta Tipo» (x3) de 2 locales, altura 3 m."""
    data = BuildingWizardData()
    data.levels = [LevelSpec(name="Planta Baja", height_m=3.0),
                   LevelSpec(name="Planta Tipo", height_m=3.0, repeat=3)]
    data.rooms = [
        RoomSpec(name="Sala PB", space_type="LIVING_ROOM",
                 width_m=4.0, depth_m=4.0, level_ref="Planta Baja"),
        RoomSpec(name="Aula 1", space_type="CLASSROOM",
                 width_m=6.0, depth_m=6.0, level_ref="Planta Tipo"),
        RoomSpec(name="Aula 2", space_type="CLASSROOM",
                 width_m=5.0, depth_m=5.0, level_ref="Planta Tipo"),
    ]
    data.relations = [RelationSpec(a_name="Aula 1", b_name="Aula 2",
                                   kind_es="Adyacente a")]
    data.corridor_enabled = False  # trazado mínimo determinista
    return data


class TestRepeatDe(ARQGenTestCase):
    """El multiplicador sano: nunca lanza, techo 50, base 1."""

    def test_default_es_1(self):
        self.assertEqual(LevelSpec().repeat, 1)

    def test_valores_sanos(self):
        self.assertEqual(bwiz.repeat_de(LevelSpec(repeat=3)), 3)
        self.assertEqual(bwiz.repeat_de(LevelSpec(repeat=50)), 50)

    def test_valores_raros_se_degradan_sin_lanzar(self):
        self.assertEqual(bwiz.repeat_de(LevelSpec(repeat=0)), 1)
        self.assertEqual(bwiz.repeat_de(LevelSpec(repeat=-4)), 1)
        raro = LevelSpec()
        raro.repeat = None  # type: ignore[assignment]
        self.assertEqual(bwiz.repeat_de(raro), 1)
        raro.repeat = "3"  # type: ignore[assignment]
        self.assertEqual(bwiz.repeat_de(raro), 3)
        raro.repeat = "no es número"  # type: ignore[assignment]
        self.assertEqual(bwiz.repeat_de(raro), 1)
        self.assertEqual(bwiz.repeat_de(LevelSpec(repeat=10_000)),
                         bwiz.REPEAT_MAX)


class TestNivelesExpandidos(ARQGenTestCase):
    """Nombres únicos y orden: la primera copia conserva el nombre."""

    def test_identidad_con_todos_a_1(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="PB", height_m=3.0),
                       LevelSpec(name="Piso 1", height_m=3.0)]
        expandidos = bwiz.niveles_expandidos(data)
        self.assertEqual([lv.name for lv in expandidos],
                         ["PB", "Piso 1"])

    def test_multiplicador_x3(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="Planta Tipo", height_m=3.0,
                                 repeat=3)]
        nombres = [lv.name for lv in bwiz.niveles_expandidos(data)]
        self.assertEqual(nombres,
                         ["Planta Tipo", "Planta Tipo 2",
                          "Planta Tipo 3"])

    def test_nombres_generados_unicos_ante_colision(self):
        # «Piso 1» x2 genera «Piso 1 2», pero ese nombre YA existe:
        # el dedup añade «_2» hasta encontrar uno libre.
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="Piso 1", height_m=3.0, repeat=2),
                       LevelSpec(name="Piso 1 2", height_m=3.0)]
        nombres = [lv.name for lv in bwiz.niveles_expandidos(data)]
        self.assertEqual(len(nombres), 3)
        self.assertEqual(len(set(n.lower() for n in nombres)), 3)
        self.assertEqual(nombres[1], "Piso 1 2")
        self.assertEqual(nombres[2], "Piso 1 2_2")

    def test_las_copias_conservan_altura(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="PT", height_m=3.6, repeat=3)]
        for lv in bwiz.niveles_expandidos(data):
            self.assertEqual(lv.height_m, 3.6)
            self.assertEqual(lv.repeat, 1)


class TestExpandirDatos(ARQGenTestCase):
    """Niveles y locales multiplicados; relaciones globales intactas."""

    def test_identidad_devuelve_el_mismo_objeto(self):
        data = BuildingWizardData()
        self.assertIs(bwiz.expandir_datos(data), data)

    def test_locales_duplicados_por_copia(self):
        data = _data_con_planta_tipo()
        expandido = bwiz.expandir_datos(data)
        self.assertEqual([lv.name for lv in expandido.levels],
                         ["Planta Baja", "Planta Tipo",
                          "Planta Tipo 2", "Planta Tipo 3"])
        aulas_por_copia = {
            nombre: len(expandido.rooms_of_level(nombre))
            for nombre in ("Planta Tipo", "Planta Tipo 2",
                           "Planta Tipo 3")}
        self.assertEqual(aulas_por_copia,
                         {"Planta Tipo": 2, "Planta Tipo 2": 2,
                          "Planta Tipo 3": 2})
        self.assertEqual(expandido.rooms_of_level("Planta Baja")[0].name,
                         "Sala PB")

    def test_las_relaciones_no_se_duplican(self):
        data = _data_con_planta_tipo()
        expandido = bwiz.expandir_datos(data)
        self.assertEqual(len(expandido.relations), 1)

    def test_locales_huerfanos_se_conservan(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="PB", height_m=3.0)]
        data.rooms = [RoomSpec(name="Fantasma", level_ref="Nivel ida")]
        expandido = bwiz.expandir_datos(data)
        self.assertIn("Fantasma", expandido.room_names())

    def test_el_original_no_se_toca(self):
        data = _data_con_planta_tipo()
        bwiz.expandir_datos(data)
        self.assertEqual(len(data.levels), 2)
        self.assertEqual(data.levels[1].repeat, 3)
        self.assertEqual(len(data.rooms), 3)


class TestLevelElevations(ARQGenTestCase):
    """Las cotas corren sobre los niveles YA expandidos."""

    def test_cotas_sin_multiplicador(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="PB", height_m=3.0),
                       LevelSpec(name="Piso 1", height_m=3.0)]
        self.assertEqual(bwiz.level_elevations(data), [0.0, 3.0])

    def test_planta_tipo_x3_empuja_las_cotas(self):
        data = _data_con_planta_tipo()
        # PB (3 m) + tres copias de 3 m = cotas 0 / 3 / 6 / 9
        self.assertEqual(bwiz.level_elevations(data),
                         [0.0, 3.0, 6.0, 9.0])


class TestBuildPlanMultiplicado(ARQGenTestCase):
    """El plan declarativo sale multiplicado y coherente."""

    def _plan(self, data, **kwargs):
        plan, _layouts, _avisos = bwiz.build_plan(data, **kwargs)
        return plan

    @staticmethod
    def _cuenta(plan, kind):
        return sum(1 for entry in plan if entry[0] == kind)

    def test_identidad_con_repeat_1(self):
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="PB", height_m=3.0)]
        data.rooms = [RoomSpec(name="Sala", space_type="LIVING_ROOM",
                               width_m=4.0, depth_m=4.0,
                               level_ref="PB")]
        data.corridor_enabled = False
        plan = self._plan(data)
        self.assertEqual(self._cuenta(plan, "BUILDING"), 1)
        self.assertEqual(plan[0][1]["floors"], 1)
        self.assertEqual(self._cuenta(plan, "LEVEL"), 1)
        self.assertEqual(self._cuenta(plan, "SPACE"), 1)

    def test_plan_x3_niveles_locales_y_cotas(self):
        data = _data_con_planta_tipo()
        plan = self._plan(data)
        self.assertEqual(plan[0][1]["floors"], 4)
        niveles = [e[1] for e in plan if e[0] == "LEVEL"]
        self.assertEqual([n["name"] for n in niveles],
                         ["Planta Baja", "Planta Tipo",
                          "Planta Tipo 2", "Planta Tipo 3"])
        self.assertEqual([n["elevation_m"] for n in niveles],
                         [0.0, 3.0, 6.0, 9.0])
        espacios = [e[1] for e in plan if e[0] == "SPACE"]
        # 1 sala PB + escalera + nucleo en PB y en cada copia +
        # 2 aulas x 3 copias (el corridor esta apagado aqui)
        self.assertEqual(len(espacios), 12)
        aulas_por_nivel = {}
        for espacio in espacios:
            if espacio["name"].startswith("Aula"):
                aulas_por_nivel[espacio["level_ref"]] = \
                    aulas_por_nivel.get(espacio["level_ref"], 0) + 1
        self.assertEqual(aulas_por_nivel,
                         {"Planta Tipo": 2, "Planta Tipo 2": 2,
                          "Planta Tipo 3": 2})
        # cada copia recibe SU escalera y SU nucleo con su propio nombre
        for nombre in ("Planta Tipo", "Planta Tipo 2",
                       "Planta Tipo 3"):
            nombres_copia = {e["name"] for e in espacios
                             if e["level_ref"] == nombre}
            self.assertIn(f"Núcleo rígido {nombre}", nombres_copia)

    def test_relaciones_del_plan_son_globales(self):
        data = _data_con_planta_tipo()
        plan = self._plan(data)
        relaciones = [e for e in plan if e[0] == "RELATION"]
        self.assertEqual(len(relaciones), 1)

    def test_muros_y_vanos_se_duplican_por_copia(self):
        # la misma planta trazada 3 veces da los mismos muros en cada
        # copia: cada «Planta Tipo N» tiene el mismo numero de WALL
        data = _data_con_planta_tipo()
        plan = self._plan(data)
        muros_por_nivel = {}
        for kind, payload in plan:
            if kind in ("WALL", "DOOR", "WINDOW"):
                muros_por_nivel.setdefault(payload["level_ref"], 0)
                muros_por_nivel[payload["level_ref"]] += 1
        copia_pb = muros_por_nivel["Planta Tipo"]
        self.assertEqual(muros_por_nivel["Planta Tipo 2"], copia_pb)
        self.assertEqual(muros_por_nivel["Planta Tipo 3"], copia_pb)
        self.assertGreater(copia_pb, 0)

    def test_pasillo_repetido_con_nombre_de_copia(self):
        data = _data_con_planta_tipo()
        data.corridor_enabled = True
        plan = self._plan(data)
        espacios = [e[1] for e in plan if e[0] == "SPACE"]
        pasillos = {e["name"] for e in espacios if e["is_corridor"]}
        self.assertIn("Pasillo Planta Tipo", pasillos)
        self.assertIn("Pasillo Planta Tipo 2", pasillos)
        self.assertIn("Pasillo Planta Tipo 3", pasillos)

    def test_multiplicador_grande_no_explota(self):
        # 50 copias x 2 aulas: el plan se inspecciona y no lanza
        data = BuildingWizardData()
        data.levels = [LevelSpec(name="Torre", height_m=3.0,
                                 repeat=bwiz.REPEAT_MAX)]
        data.rooms = [
            RoomSpec(name="Aula 1", space_type="CLASSROOM",
                     width_m=6.0, depth_m=6.0, level_ref="Torre"),
            RoomSpec(name="Aula 2", space_type="CLASSROOM",
                     width_m=5.0, depth_m=5.0, level_ref="Torre")]
        data.corridor_enabled = False
        plan = self._plan(data)
        self.assertEqual(self._cuenta(plan, "LEVEL"),
                         bwiz.REPEAT_MAX)
        aulas = sum(1 for kind, payload in plan
                    if kind == "SPACE"
                    and payload["space_type"] == "CLASSROOM")
        self.assertEqual(aulas, 2 * bwiz.REPEAT_MAX)


class TestVariantesMultiplicadas(ARQGenTestCase):
    """generate_variants puntúa el edificio entero (copias incluidas)."""

    def test_variantes_sobre_el_edificio_entero(self):
        # el mismo edificio escrito a mano (copias ya expandidas) debe
        # dar las mismas métricas que el multiplicador x3
        con_multiplicador = _data_con_planta_tipo()
        a_mano = _data_con_planta_tipo()
        a_mano.levels = [LevelSpec(name="Planta Baja", height_m=3.0),
                         LevelSpec(name="Planta Tipo", height_m=3.0),
                         LevelSpec(name="Planta Tipo 2", height_m=3.0),
                         LevelSpec(name="Planta Tipo 3", height_m=3.0)]
        variantes_x = bwiz.generate_variants(con_multiplicador)
        variantes_a_mano = bwiz.generate_variants(a_mano)
        self.assertTrue(variantes_x)
        self.assertEqual(len(variantes_x), len(variantes_a_mano))
        mejor_x = variantes_x[0]
        mejor_mano = variantes_a_mano[0]
        self.assertEqual(mejor_x.key, mejor_mano.key)
        self.assertEqual(len(mejor_x.layouts), 4)
        self.assertEqual(mejor_x.layouts[-1].level_name,
                         "Planta Tipo 3")
        for metrica, valor in mejor_x.metrics.items():
            self.assertAlmostEqual(
                valor, mejor_mano.metrics.get(metrica, -1.0), places=4,
                msg=f"métrica {metrica} distinta con multiplicador")

    def test_build_plan_con_variante_y_multiplicador(self):
        data = _data_con_planta_tipo()
        variante = bwiz.generate_variants(data)[0]
        plan, _layouts, _avisos = bwiz.build_plan(data,
                                                  variant=variante)
        nombres = [e[1]["name"] for e in plan if e[0] == "LEVEL"]
        self.assertEqual(nombres,
                         ["Planta Baja", "Planta Tipo",
                          "Planta Tipo 2", "Planta Tipo 3"])
        espacios = [e[1] for e in plan if e[0] == "SPACE"]
        self.assertEqual(
            {e["level_ref"] for e in espacios},
            {"Planta Baja", "Planta Tipo", "Planta Tipo 2",
             "Planta Tipo 3"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
