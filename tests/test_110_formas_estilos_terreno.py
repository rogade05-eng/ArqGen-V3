"""Asistente de edificación v2.3.0: FORMAS EN PLANTA, ESTILOS,
TERRENO CON DESNIVEL y ESCALERAS.

Lo pedido por el usuario: agregar tipologías constructivas, estilos
arquitectónicos, formas de las edificaciones en planta (rectangular,
cuadrada, articulada, patio central, cruz, H y más, según el uso
social), orientación de fachadas a los ocho puntos cardinales,
terrenos regulares o irregulares que OBLIGUEN a usar diferentes
niveles de piso en una misma planta y la colocación de escaleras.
"""

from __future__ import annotations

import itertools
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui.building_wizard import (
    ARCHITECTURAL_STYLES, BuildingWizardData, CONSTRUCTION_TYPES,
    ORIENTATIONS, PLAN_SHAPES, STAIR_MODES, TERRAIN_TYPES, USAGE_TYPES,
)


def _programa(usage: str, level: str = "Planta Baja") -> BuildingWizardData:
    """Datos con el programa del uso social ya cargado."""
    data = BuildingWizardData()
    data.levels = [bw.LevelSpec(name=level, height_m=3.0)]
    data.usage_type = usage
    data.rooms = bw.preset_rooms(usage, level)
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


class TestCatalogos(ARQGenTestCase):
    """Catálogos ampliados del paso 1."""

    def test_diez_tipologias_constructivas(self):
        # Las cinco originales se conservan y se amplían a diez.
        self.assertEqual(len(CONSTRUCTION_TYPES), 10)
        self.assertIn("Mampostería de bloque + losa de vigueta",
                      CONSTRUCTION_TYPES)
        self.assertIn("Estructura metálica (acero)", CONSTRUCTION_TYPES)
        self.assertIn("Tierra (adobe o tapial)", CONSTRUCTION_TYPES)

    def test_ocho_puntos_cardinales(self):
        self.assertEqual(len(ORIENTATIONS), 8)
        for punto in ("Norte", "Noreste", "Este", "Sureste", "Sur",
                      "Suroeste", "Oeste", "Noroeste"):
            self.assertIn(punto, ORIENTATIONS)

    def test_diez_formas_en_planta(self):
        self.assertEqual(len(PLAN_SHAPES), 10)
        for forma in ("Rectangular", "Cuadrada", "Lineal (barra)",
                      "En L", "En T", "En U", "En H", "En cruz",
                      "Patio central", "Articulada (eslabones)"):
            self.assertIn(forma, PLAN_SHAPES)
        for forma in PLAN_SHAPES:
            self.assertIn(forma, bw.SHAPE_DESCRIPTIONS)

    def test_catorce_estilos_arquitectonicos(self):
        # v2.3.0 trajo diez; v2.4.0 amplía a catorce.
        self.assertEqual(len(ARCHITECTURAL_STYLES), 14)
        for estilo in ARCHITECTURAL_STYLES:
            self.assertIn(estilo, bw.STYLE_DESCRIPTIONS)
            self.assertTrue(bw.STYLE_DESCRIPTIONS[estilo].strip())

    def test_terrenos_y_escaleras(self):
        self.assertEqual(len(TERRAIN_TYPES), 3)
        self.assertEqual(bw.terrain_rise_m(TERRAIN_TYPES[0]), 0.0)
        self.assertEqual(bw.terrain_rise_m(TERRAIN_TYPES[1]), 0.75)
        self.assertEqual(bw.terrain_rise_m(TERRAIN_TYPES[2]), 1.5)
        self.assertEqual(len(STAIR_MODES), 3)

    def test_forma_sugerida_por_uso(self):
        self.assertEqual(bw.suggested_plan_shape("Hospital"), "En H")
        self.assertEqual(bw.suggested_plan_shape("Escuela primaria"),
                         "Articulada (eslabones)")
        self.assertEqual(bw.suggested_plan_shape("Centro comunitario"),
                         "Patio central")
        for usage in USAGE_TYPES:
            self.assertIn(bw.suggested_plan_shape(usage), PLAN_SHAPES)

    def test_afinidad_forma_esquema(self):
        self.assertEqual(bw.shape_affinity("En L", "en_L"), 1.0)
        self.assertEqual(bw.shape_affinity("En H", "en_H"), 1.0)
        self.assertEqual(bw.shape_affinity("En cruz", "en_cruz"), 1.0)
        self.assertEqual(bw.shape_affinity("Patio central", "patio"), 1.0)
        # La matriz cubre todas las combinaciones forma × esquema.
        for forma in PLAN_SHAPES:
            for scheme in bw.SHAPE_SCHEME_AFFINITY["Rectangular"]:
                value = bw.shape_affinity(forma, scheme)
                self.assertGreaterEqual(value, 0.0, (forma, scheme))
                self.assertLessEqual(value, 1.0, (forma, scheme))


class TestDatosYValidacion(ARQGenTestCase):
    """Los cuatro campos nuevos del paso 1 se validan y cargan."""

    def test_valores_por_defecto(self):
        data = BuildingWizardData()
        self.assertEqual(data.architectural_style,
                         ARCHITECTURAL_STYLES[0])
        self.assertEqual(data.plan_shape, PLAN_SHAPES[0])
        self.assertEqual(data.terrain_type, TERRAIN_TYPES[0])
        self.assertEqual(data.stairs_mode, STAIR_MODES[0])

    def test_validacion_paso_cero_rechaza_desconocidos(self):
        data = BuildingWizardData()
        data.plan_shape = "En espiral"
        self.assertTrue(any("forma en planta" in e
                            for e in bw.validate_step(0, data)))
        data = BuildingWizardData()
        data.architectural_style = "Gótico"
        self.assertTrue(any("estilo" in e.lower()
                            for e in bw.validate_step(0, data)))
        data = BuildingWizardData()
        data.terrain_type = "Volcánico"
        self.assertTrue(any("terreno" in e.lower()
                            for e in bw.validate_step(0, data)))
        data = BuildingWizardData()
        data.stairs_mode = "Teletransporte"
        self.assertTrue(any("escalera" in e.lower()
                            for e in bw.validate_step(0, data)))

    def test_data_from_values_carga_los_cuatro_campos(self):
        data = BuildingWizardData()
        errors = bw.data_from_values(0, {
            "name": "Casa prueba",
            "plan_shape": "En U",
            "architectural_style": "Colonial cubano",
            "terrain_type": "Irregular con pendiente fuerte",
            "stairs_mode": "Sí, incluir siempre",
        }, data)
        self.assertEqual(errors, [])
        self.assertEqual(data.plan_shape, "En U")
        self.assertEqual(data.architectural_style, "Colonial cubano")
        self.assertEqual(data.terrain_type,
                         "Irregular con pendiente fuerte")
        self.assertEqual(data.stairs_mode, "Sí, incluir siempre")


class TestEscaleras(ARQGenTestCase):
    """Geometría y decisión automática de escaleras."""

    def test_geometria_de_escalera(self):
        steps, run = bw.stair_geometry(1.5)
        self.assertGreaterEqual(steps, 9)      # 1,5 / 0,175
        self.assertGreaterEqual(run, 2.4)
        self.assertLessEqual(run, 4.8)
        steps3, run3 = bw.stair_geometry(3.0)
        self.assertGreaterEqual(steps3, 18)
        self.assertLessEqual(run3, 4.8)        # se limita el desarrollo

    def test_escalera_automatica_por_niveles(self):
        data = _programa("Vivienda")
        data.levels.append(bw.LevelSpec(name="Planta Alta", height_m=3.0))
        data.rooms.extend(bw.preset_rooms(
            "Vivienda", "Planta Alta"))
        self.assertTrue(bw.stairs_needed(data))
        self.assertTrue(bw.stairs_wanted(data))
        layouts, _adv = bw.build_layout(data)
        names = [p.name for p in layouts[0].rooms]
        self.assertIn("Escalera Planta Baja", names)
        stair = next(p for p in layouts[0].rooms
                     if p.space_type == bw.STAIR_TYPE)
        self.assertFalse(stair.with_window)
        # Sin escaleras vetadas no se colocan.
        data.stairs_mode = bw.STAIR_NEVER
        layouts, _adv = bw.build_layout(data)
        self.assertFalse(any(p.space_type == bw.STAIR_TYPE
                             for p in layouts[0].rooms))

    def test_escalera_forzada_en_un_nivel(self):
        data = _programa("Vivienda")
        data.stairs_mode = bw.STAIR_ALWAYS
        self.assertTrue(bw.stairs_wanted(data))
        layouts, _adv = bw.build_layout(data)
        self.assertTrue(any(p.space_type == bw.STAIR_TYPE
                            for p in layouts[0].rooms))

    def test_aviso_si_se_vetan_y_son_necesarias(self):
        data = _programa("Vivienda")
        data.levels.append(bw.LevelSpec(name="Planta Alta", height_m=3.0))
        data.stairs_mode = bw.STAIR_NEVER
        avisos = bw.site_advisories(data)
        self.assertTrue(any("escaleras" in a.lower() for a in avisos))


class TestTerrenoDesnivel(ARQGenTestCase):
    """El terreno irregular obliga a DIFERENTES NIVELES DE PISO."""

    def test_terreno_regular_sin_desnivel(self):
        data = _programa("Vivienda")
        layouts, _adv = bw.build_layout(data)
        self.assertEqual({p.floor_rise_m for p in layouts[0].rooms},
                         {0.0})
        self.assertFalse(bw.stairs_needed(data))

    def test_pendiente_fuerte_parte_la_planta(self):
        data = _programa("Escuela primaria")
        data.terrain_type = TERRAIN_TYPES[2]
        self.assertTrue(bw.stairs_needed(data))
        layouts, advisories = bw.build_layout(data)
        rooms = layouts[0].rooms
        cotas = {p.floor_rise_m for p in rooms}
        self.assertIn(0.0, cotas)
        self.assertIn(1.5, cotas)
        # La escalera conecta ambas cotas y no tiene subida propia.
        stair = next(p for p in rooms if p.space_type == bw.STAIR_TYPE)
        self.assertEqual(stair.floor_rise_m, 0.0)
        self.assertTrue(any("1.50" in a or "1,50" in a
                            for a in layouts[0].advisories))

    def test_pendiente_ligera_sube_075(self):
        data = _programa("Vivienda")
        data.terrain_type = TERRAIN_TYPES[1]
        layouts, _adv = bw.build_layout(data)
        self.assertEqual(
            {p.floor_rise_m for p in layouts[0].rooms}, {0.0, 0.75})

    def test_doble_crujia_con_desnivel_en_crujia_trasera(self):
        data = _programa("Consultorio médico")
        data.terrain_type = TERRAIN_TYPES[2]
        variants = bw.generate_variants(data)
        variant = next(v for v in variants
                       if v.scheme == "doble_crujia" and not v.mirror)
        layout = variant.layouts[0]
        front = [p for p in layout.rooms if p.y == 0.0]
        back = [p for p in layout.rooms if p.y > 0.0]
        self.assertTrue(front and back)
        self.assertEqual({p.floor_rise_m for p in front}, {0.0})
        self.assertEqual({p.floor_rise_m for p in back}, {1.5})

    def test_cota_piso_llega_al_metadata_del_local(self):
        data = _programa("Vivienda")
        data.terrain_type = TERRAIN_TYPES[2]
        plan, _layouts, _adv = bw.build_plan(data)
        spaces = [params for op, params in plan if op == "SPACE"]
        self.assertTrue(all("floor_rise_m" in params
                            for params in spaces))
        self.assertTrue(any(params["floor_rise_m"] == 1.5
                            for params in spaces))


class TestFormasCompuestas(ARQGenTestCase):
    """El motor traza de verdad las formas en L, T, U, H, cruz y
    articulada, sin solapes y sin locales aislados."""

    def _variant(self, data, scheme):
        variants = bw.generate_variants(data)
        return next(v for v in variants
                    if v.scheme == scheme and not v.mirror)

    def test_los_nueve_esquemas_trazan_para_varios_usos(self):
        for usage in ("Vivienda", "Escuela primaria", "Policlínico",
                      "Hospital", "Centro comunitario"):
            data = _programa(usage)
            variants = bw.generate_variants(data)
            schemes = {v.scheme for v in variants}
            # v2.5.0: 14 esquemas (9 base + 5 compuestas con patio
            # central; la U ya trae el suyo trasero).
            self.assertEqual(
                {"lineal", "doble_crujia", "patio", "en_L", "en_T",
                 "en_U", "en_H", "en_cruz", "articulada", "en_L_patio",
                 "en_T_patio", "en_H_patio", "en_cruz_patio",
                 "articulada_patio"}, schemes,
                usage)

    def test_forma_en_l_con_ala(self):
        data = _programa("Vivienda")
        data.plan_shape = "En L"
        variant = self._variant(data, "en_L")
        layout = variant.layouts[0]
        front = [p for p in layout.rooms if p.y >= 0.0]
        wing = [p for p in layout.rooms if p.y < 0.0
                and not p.is_corridor]
        self.assertGreaterEqual(len(front), 2)
        self.assertGreaterEqual(len(wing), 1)
        # El ala crece hacia el fondo: su y mínimo está por debajo del
        # pasillo (que ocupa y en [-ancho, 0]).
        self.assertLess(min(p.y for p in wing), -data.corridor_width_m)
        self.assertFalse(_solapes(layout.all_rooms))

    def test_forma_en_t_con_espina(self):
        data = _programa("Consultorio médico")
        variant = self._variant(data, "en_T")
        layout = variant.layouts[0]
        spines = [p for p in layout.all_rooms
                  if p.is_corridor and "espina" in p.name]
        self.assertEqual(len(spines), 1)
        spine = spines[0]
        self.assertGreaterEqual(spine.d, 3.0)   # longitud de la espina
        # La entrada principal remata la espina.
        self.assertTrue(any(d.is_door and "entrada" in d.note
                            for d in layout.doors))
        self.assertFalse(_solapes(layout.all_rooms))

    def test_forma_en_u_con_patio_trasero(self):
        data = _programa("Círculo infantil")
        variant = self._variant(data, "en_U")
        layout = variant.layouts[0]
        self.assertFalse(_solapes(layout.all_rooms))
        # Cada local de las alas tiene puerta (al pasillo o enfilada).
        self.assertGreaterEqual(len(layout.doors), len(layout.rooms))

    def test_forma_en_h_doble_barra(self):
        data = _programa("Policlínico")
        variant = self._variant(data, "en_H")
        layout = variant.layouts[0]
        # Tres pasillos: frontal, puente y trasero.
        corridors = [p for p in layout.all_rooms if p.is_corridor]
        self.assertEqual(len(corridors), 3)
        self.assertEqual(len(layout.extra_corridors), 2)
        # Dos barras: locales al frente (y >= 0) y locales traseros.
        rear = [p for p in layout.rooms
                if p.y < -2 * data.corridor_width_m]
        self.assertGreaterEqual(len(rear), 1)
        self.assertFalse(_solapes(layout.all_rooms))

    def test_forma_en_cruz_con_hospital(self):
        data = BuildingWizardData()
        data.usage_type = "Hospital"
        bw.apply_usage_program(data)      # programa MULTI-NIVEL (3 niveles)
        self.assertEqual(len(data.levels), 3)
        variant = self._variant(data, "en_cruz")
        self.assertEqual(len(variant.layouts), 3)
        for layout in variant.layouts:
            spines = [p for p in layout.all_rooms
                      if p.is_corridor and "espina" in p.name]
            self.assertEqual(len(spines), 1, layout.level_name)
            self.assertFalse(_solapes(layout.all_rooms),
                             layout.level_name)

    def test_forma_articulada(self):
        data = _programa("Escuela primaria")
        variant = self._variant(data, "articulada")
        layout = variant.layouts[0]
        links = [p for p in layout.all_rooms
                 if p.is_corridor and "eslabón" in p.name]
        self.assertEqual(len(links), 1)
        self.assertFalse(_solapes(layout.all_rooms))

    def test_ningun_local_aislado_en_todas_las_formas(self):
        for usage in ("Vivienda", "Escuela primaria", "Policlínico",
                      "Hospital"):
            data = _programa(usage)
            for variant in bw.generate_variants(data):
                for layout in variant.layouts:
                    self.assertFalse(
                        any("aislado" in a or "no toca" in a
                            for a in layout.advisories),
                        (usage, variant.key, layout.level_name))

    def test_sin_solapes_en_todas_las_variantes(self):
        for usage in ("Vivienda", "Escuela primaria", "Hospital"):
            data = _programa(usage)
            data.terrain_type = TERRAIN_TYPES[2]
            for variant in bw.generate_variants(data):
                for layout in variant.layouts:
                    self.assertFalse(_solapes(layout.all_rooms),
                                     (usage, variant.key,
                                      layout.level_name))

    def test_puertas_y_entrada_en_formas_compuestas(self):
        data = _programa("Vivienda")
        data.plan_shape = "En T"
        variant = self._variant(data, "en_T")
        layout = variant.layouts[0]
        # Entrada + puerta por local (al pasillo o enfilada).
        self.assertTrue(any(d.is_door and "entrada" in d.note
                            for d in layout.doors))
        self.assertGreaterEqual(len(layout.doors), len(layout.rooms))

    def test_ventanas_en_fachadas_exteriores_de_las_alas(self):
        data = _programa("Vivienda")
        data.plan_shape = "En L"
        variant = self._variant(data, "en_L")
        layout = variant.layouts[0]
        con_ventana = [p for p in layout.rooms if p.with_window]
        self.assertTrue(con_ventana)
        self.assertEqual(len(layout.windows), len(con_ventana))


class TestVariantesConForma(ARQGenTestCase):
    """La forma elegida guía la puntuación sin excluir variantes."""

    def test_metrica_forma_elegida_presente(self):
        data = _programa("Consultorio médico")
        for variant in bw.generate_variants(data):
            self.assertIn("Forma elegida", variant.metrics)
            self.assertGreaterEqual(variant.metrics["Forma elegida"], 0.0)
            self.assertLessEqual(variant.metrics["Forma elegida"], 1.0)

    def test_forma_elegida_puntua_al_maximo(self):
        for shape, scheme in (("En L", "en_L"), ("En T", "en_T"),
                              ("En U", "en_U"), ("En H", "en_H"),
                              ("En cruz", "en_cruz"),
                              ("Articulada (eslabones)", "articulada"),
                              ("Patio central", "patio")):
            data = _programa("Escuela primaria")
            data.plan_shape = shape
            variants = bw.generate_variants(data)
            variant = next(v for v in variants if v.scheme == scheme
                           and not v.mirror)
            self.assertEqual(variant.metrics["Forma elegida"], 1.0,
                             (shape, scheme))

    def test_variants_son_deterministas_con_forma(self):
        data = _programa("Policlínico")
        data.plan_shape = "En cruz"
        first = bw.generate_variants(data)
        second = bw.generate_variants(data)
        self.assertEqual([v.key for v in first], [v.key for v in second])
        self.assertEqual([v.score for v in first],
                         [v.score for v in second])


class TestMetadataYResumen(ARQGenTestCase):
    """La edificación guarda forma, estilo, terreno y escaleras."""

    def test_metadata_del_edificio_completa(self):
        data = _programa("Vivienda")
        data.plan_shape = "En L"
        data.architectural_style = "Vernáculo tropical"
        data.terrain_type = TERRAIN_TYPES[1]
        data.stairs_mode = STAIR_MODES[0]
        metadata = bw._building_metadata(data)["edificacion"]
        self.assertEqual(metadata["forma_en_planta"], "En L")
        self.assertEqual(metadata["estilo_arquitectonico"],
                         "Vernáculo tropical")
        self.assertEqual(metadata["terreno"], TERRAIN_TYPES[1])
        self.assertEqual(metadata["desnivel_pisos_m"], 0.75)
        self.assertTrue(metadata["escaleras"]["colocadas"])

    def test_escalera_en_metadata_cuando_no_hay(self):
        data = _programa("Vivienda")
        data.stairs_mode = bw.STAIR_NEVER
        metadata = bw._building_metadata(data)["edificacion"]
        self.assertFalse(metadata["escaleras"]["colocadas"])

    def test_resumen_menciona_todo(self):
        data = _programa("Hospital")
        data.plan_shape = "En H"
        data.architectural_style = "Racionalista"
        data.terrain_type = TERRAIN_TYPES[2]
        texto = bw.step_summary(data)
        self.assertIn("Forma en planta: En H", texto)
        self.assertIn("Estilo arquitectónico: Racionalista", texto)
        self.assertIn("desnivel de 1.50", texto)
        self.assertIn("Escaleras", texto)

    def test_avisos_de_sitio_por_orientacion(self):
        data = _programa("Vivienda")
        data.climate = "Cálido húmedo (tropical lluvioso)"
        data.facade_orientation = "Oeste"
        avisos = bw.site_advisories(data)
        self.assertTrue(any("poniente" in a for a in avisos))
        data.facade_orientation = "Norte"
        data.climate = "Frío (necesita calefacción)"
        avisos = bw.site_advisories(data)
        self.assertTrue(any("norte" in a.lower() for a in avisos))

    def test_avisos_de_estilo_piden_aleros(self):
        data = _programa("Vivienda")
        data.architectural_style = "Colonial cubano"
        data.protection_solar = False
        avisos = bw.site_advisories(data)
        self.assertTrue(any("sube el alero" in a for a in avisos))
        # Con protección solar y alero generoso no insiste.
        data.protection_solar = True
        data.eaves_m = 1.0
        self.assertFalse(any("sube el alero" in a for a in
                             bw.site_advisories(data)))

    def test_avisos_de_terreno_y_estilo_general(self):
        data = _programa("Vivienda")
        data.terrain_type = TERRAIN_TYPES[2]
        avisos = bw.site_advisories(data)
        self.assertTrue(any("desnivel de 1.50" in a for a in avisos))
        self.assertTrue(any(a.startswith("Estilo ")
                            for a in avisos))  # consejo del estilo


class TestPlanConEscalera(ARQGenTestCase):
    """El plan declarativo incluye la escalera con su geometría."""

    def test_escalera_en_el_plan(self):
        data = _programa("Vivienda")
        data.levels.append(bw.LevelSpec(name="Planta Alta", height_m=3.0))
        plan, layouts, _adv = bw.build_plan(data)
        stairs = [params for op, params in plan
                  if op == "SPACE"
                  and params["space_type"] == bw.STAIR_TYPE]
        self.assertEqual(len(stairs), 1)
        self.assertEqual(stairs[0]["name"], "Escalera Planta Baja")
        # Con la variante del motor también aparece.
        variants = bw.generate_variants(data)
        plan2, _layouts2, _adv2 = bw.build_plan(
            data, variant=variants[0])
        stairs2 = [params for op, params in plan2
                   if op == "SPACE"
                   and params["space_type"] == bw.STAIR_TYPE]
        self.assertGreaterEqual(len(stairs2), 1)

    def test_escalera_sin_puerta_fantasma_en_ventanas(self):
        data = _programa("Vivienda")
        data.levels.append(bw.LevelSpec(name="Planta Alta", height_m=3.0))
        layouts, _adv = bw.build_layout(data)
        for layout in layouts:
            for window in layout.windows:
                # Las ventanas solo van a locales con ventana pedida.
                self.assertNotIn("Escalera", window.note)


def _display_available() -> bool:
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:  # noqa: BLE001 — sin display en CI
        return False


DISPLAY = _display_available()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestGUIPasoUno(ARQGenTestCase):
    """La ventana del asistente expone los cuatro combos nuevos."""

    def setUp(self):
        super().setUp()
        from ui.app_window import ARQGenWindow
        self.context = self.application.create_project(
            self.project_path("formas_gui.arqgen"),
            name="Proyecto Formas")
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        super().tearDown()

    def _open(self):
        self.window.open_building_wizard()
        return self.window._building_dialog

    def test_widgets_nuevos_en_paso_uno(self):
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            for key in ("shape", "style", "terrain", "stairs"):
                self.assertIn(key, widgets)
            self.assertEqual(widgets["shape"].get(), PLAN_SHAPES[0])
        finally:
            dialog.destroy()

    def test_coleccion_paso_cero_guarda_los_cuatro_campos(self):
        dialog = self._open()
        try:
            widgets = dialog._bld_widgets
            widgets["name"].delete(0, "end")
            widgets["name"].insert(0, "Casa en U")
            widgets["shape"].set("En U")
            widgets["style"].set("Art déco")
            widgets["terrain"].set("Irregular con ligera pendiente")
            widgets["stairs"].set("Sí, incluir siempre")
            dialog._bld_next()  # → paso 2, tras _collect(0)
            data = dialog._bld_data
            self.assertEqual(data.plan_shape, "En U")
            self.assertEqual(data.architectural_style, "Art déco")
            self.assertEqual(data.terrain_type,
                             "Irregular con ligera pendiente")
            self.assertEqual(data.stairs_mode, "Sí, incluir siempre")
        finally:
            dialog.destroy()

    def test_sugerir_uso_carga_forma_sugerida(self):
        dialog = self._open()
        try:
            dialog._bld_widgets["usage"].set("Hospital")
            dialog._bld_load_usage()
            data = dialog._bld_data
            self.assertEqual(data.plan_shape, "En H")
            self.assertEqual(data.usage_type, "Hospital")
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
