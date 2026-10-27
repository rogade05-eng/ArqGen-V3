"""Asistente de edificación v2.4.0: PATIOS EN LAS ALAS, ALEROS
DIBUJADOS y MÁS ESTILOS/RELACIONES POR USO.

Lo pedido por el usuario: refinar las formas (patios en las alas y
aleros dibujados), añadir más estilos y más relaciones por uso social.
"""

from __future__ import annotations

import itertools
import os
import unittest

from tests.base import ARQGenTestCase

from core.geometry.engine import eaves_outline_segments, \
    exposed_outline_segments
from ui import building_wizard as bw
from ui.building_wizard import (
    ARCHITECTURAL_STYLES, BuildingWizardData, PLAN_SHAPES, USAGE_TYPES,
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


def _patios_de_ala(layout):
    """Piezas PATIO de ala (corredores abiertos) de un trazado."""
    return [p for p in layout.all_rooms
            if p.is_corridor and p.space_type == bw.PATIO_TYPE
            and p.name.startswith("Patio de ala")]


class TestEstilosAmpliados(ARQGenTestCase):
    """Catorce estilos con sugerencia por uso y preferencia de forma."""

    def test_estilos_con_descripcion(self):
        self.assertEqual(len(ARCHITECTURAL_STYLES), 14)
        for nuevo in ("High-tech", "Orgánico", "Posmoderno",
                      "Sostenible (bioclimático)"):
            self.assertIn(nuevo, ARCHITECTURAL_STYLES)
            self.assertTrue(bw.STYLE_DESCRIPTIONS[nuevo].strip())
        for estilo in ARCHITECTURAL_STYLES:
            self.assertIn(estilo, bw.STYLE_DESCRIPTIONS)

    def test_estilo_sugerido_por_uso(self):
        self.assertEqual(bw.suggested_architectural_style("Hospital"),
                         "High-tech")
        self.assertEqual(bw.suggested_architectural_style("Escuela primaria"),
                         "Racionalista")
        self.assertEqual(bw.suggested_architectural_style("Local comercial"),
                         "Art déco")
        for usage in USAGE_TYPES:
            self.assertIn(bw.suggested_architectural_style(usage),
                          ARCHITECTURAL_STYLES, usage)

    def test_preferencia_estilo_forma_coherente(self):
        for estilo, formas in bw.STYLE_SHAPE_PREFERENCE.items():
            self.assertIn(estilo, ARCHITECTURAL_STYLES)
            for forma in formas:
                self.assertIn(forma, PLAN_SHAPES, (estilo, forma))

    def test_aviso_de_coherencia_estilo_forma(self):
        data = _programa("Vivienda")
        data.architectural_style = "Colonial cubano"
        data.plan_shape = "Rectangular"   # el colonial pide patio
        avisos = bw.site_advisories(data)
        self.assertTrue(any("Colonial cubano" in a and "Patio central" in a
                            for a in avisos))
        # Si la forma ya es la preferida, no insiste.
        data.plan_shape = "Patio central"
        avisos = bw.site_advisories(data)
        self.assertFalse(any("considera" in a and "Colonial cubano" in a
                             for a in avisos))


class TestRelacionesPorUso(ARQGenTestCase):
    """Más puertas críticas y más adyacencias sugeridas por uso."""

    def test_puertas_criticas_ampliadas(self):
        esperadas = {
            "Escuela primaria": frozenset(("CLASSROOM", "BATHROOM")),
            "Círculo infantil": frozenset(("DINING_ROOM", "KITCHEN")),
            "Comedor social": frozenset(("DINING_ROOM", "KITCHEN")),
            "Albergue": frozenset(("BEDROOM", "BATHROOM")),
            "Centro comunitario": frozenset(("ENTRANCE", "MULTIUSE_HALL")),
            "Local comercial": frozenset(("ROOM", "STOREROOM")),
            "Oficina": frozenset(("ENTRANCE", "OFFICE")),
        }
        for usage, pair in esperadas.items():
            data = _programa(usage)
            puertas = [frozenset((r.a_name, r.b_name))
                       for r in data.relations if r.with_door]
            tipos = {frozenset((data.room(a).space_type,
                                data.room(b).space_type))
                     for a, b in (tuple(p) for p in puertas)}
            self.assertIn(pair, tipos, usage)

    def test_hospital_suma_puertas_nuevas(self):
        data = _programa("Hospital")
        tipos_con_puerta = set()
        for rel in data.relations:
            if rel.with_door:
                a, b = data.room(rel.a_name), data.room(rel.b_name)
                assert a and b
                tipos_con_puerta.add(frozenset((a.space_type, b.space_type)))
        for par in (frozenset(("OPERATING_ROOM", "NURSE_STATION")),
                    frozenset(("WARD", "DINING_ROOM")),
                    frozenset(("LABORATORY", "STOREROOM"))):
            self.assertIn(par, tipos_con_puerta, par)

    def test_vivienda_sin_puertas_sugeridas_como_siempre(self):
        data = _programa("Vivienda")
        self.assertFalse(any(rel.with_door for rel in data.relations))

    def test_pares_extras_encadenan_mismos_tipos(self):
        # Hospital: salas de hospitalización contiguas (WARD–WARD).
        data = _programa("Hospital")
        salas = {r.name for r in data.rooms if r.space_type == "WARD"}
        misma_sala = [r for r in data.relations
                      if r.a_name in salas and r.b_name in salas]
        self.assertTrue(misma_sala)
        # Escuela: aulas en cadena (CLASSROOM–CLASSROOM).
        data = _programa("Escuela primaria")
        aulas = {r.name for r in data.rooms if r.space_type == "CLASSROOM"}
        self.assertTrue(any(r.a_name in aulas and r.b_name in aulas
                            for r in data.relations))

    def test_relaciones_sugeridas_no_se_duplican(self):
        data = _programa("Hospital")
        pares = [frozenset((r.a_name, r.b_name)) for r in data.relations]
        self.assertEqual(len(pares), len(set(pares)))


class TestPatiosEnAlas(ARQGenTestCase):
    """Las alas largas de L/T/U/cruz ganan un patio interior."""

    def _variante(self, data, scheme, mirror=False):
        variants = bw.generate_variants(data)
        return next(v for v in variants
                    if v.scheme == scheme and v.mirror == mirror)

    def test_ala_de_la_l_gana_patio(self):
        data = _programa("Escuela primaria")   # ala de 4 locales, 10,8 m
        variant = self._variante(data, "en_L")
        layout = variant.layouts[0]
        patios = _patios_de_ala(layout)
        self.assertEqual(len(patios), 1)
        patio = patios[0]
        self.assertEqual(patio.d, bw.WING_PATIO_WIDTH_M)
        self.assertGreaterEqual(patio.w, bw.WING_PATIO_MIN_DEPTH_M)
        self.assertFalse(_solapes(layout.all_rooms))

    def test_policlinico_u_y_t_con_patio_de_ala(self):
        for scheme in ("en_U", "en_T"):
            data = _programa("Policlínico")
            variant = self._variante(data, scheme)
            layout = variant.layouts[0]
            patios = _patios_de_ala(layout)
            self.assertGreaterEqual(len(patios), 1, scheme)
            self.assertFalse(_solapes(layout.all_rooms), scheme)

    def test_hospital_en_cruz_con_dos_patios(self):
        data = _programa("Hospital")           # 20 locales en un nivel
        variant = self._variante(data, "en_cruz")
        layout = variant.layouts[0]
        patios = _patios_de_ala(layout)
        self.assertEqual(len(patios), 2)
        nombres = {p.name for p in patios}
        self.assertEqual(len(nombres), 2)      # izquierda y derecha
        self.assertFalse(_solapes(layout.all_rooms))

    def test_alas_cortas_sin_patio(self):
        data = _programa("Vivienda")           # ala de 2 locales
        variant = self._variante(data, "en_L")
        layout = variant.layouts[0]
        self.assertEqual(len(_patios_de_ala(layout)), 0)

    def test_galeria_puertas_a_cada_patio(self):
        for usage, scheme in (("Escuela primaria", "en_L"),
                              ("Policlínico", "en_U"),
                              ("Hospital", "en_cruz")):
            data = _programa(usage)
            variant = self._variante(data, scheme)
            layout = variant.layouts[0]
            patios = _patios_de_ala(layout)
            self.assertTrue(patios, (usage, scheme))
            for patio in patios:
                vecinos = 0
                for room in layout.rooms:
                    edge = bw._corridor_edge(room, [patio])
                    if edge is not None:
                        vecinos += 1
                self.assertGreaterEqual(vecinos, 1,
                                        (usage, scheme, patio.name))
            # hay al menos una puerta explícita a la galería
            self.assertTrue(any("galería del patio" in d.note
                                for d in layout.doors), usage)

    def test_ningun_local_aislado_con_patios(self):
        for usage in ("Escuela primaria", "Policlínico", "Hospital",
                      "Albergue"):
            data = _programa(usage)
            data.terrain_type = bw.TERRAIN_TYPES[2]
            for variant in bw.generate_variants(data):
                for layout in variant.layouts:
                    self.assertFalse(
                        any("aislado" in a for a in layout.advisories),
                        (usage, variant.key))

    def test_sin_solapes_en_todas_las_variantes_con_patios(self):
        for usage in USAGE_TYPES:
            data = _programa(usage)
            data.terrain_type = bw.TERRAIN_TYPES[2]
            for variant in bw.generate_variants(data):
                for layout in variant.layouts:
                    self.assertFalse(_solapes(layout.all_rooms),
                                     (usage, variant.key,
                                      layout.level_name))

    def test_hospital_multinivel_en_cruz_sigue_trazando(self):
        data = BuildingWizardData()
        data.usage_type = "Hospital"
        bw.apply_usage_program(data)          # 3 niveles
        variant = self._variante(data, "en_cruz")
        self.assertEqual(len(variant.layouts), 3)
        for layout in variant.layouts:
            self.assertFalse(_solapes(layout.all_rooms), layout.level_name)

    def test_patios_de_ala_llegan_al_plan(self):
        data = _programa("Escuela primaria")
        variant = self._variante(data, "en_L")
        plan, _layouts, _adv = bw.build_plan(data, variant=variant)
        patios = [params for op, params in plan
                  if op == "SPACE"
                  and params["space_type"] == bw.PATIO_TYPE
                  and params["name"].startswith("Patio de ala")]
        self.assertEqual(len(patios), 1)
        self.assertFalse(patios[0]["is_corridor"] is False)


class TestAlerosDibujados(ARQGenTestCase):
    """El contorno del alero rodea el edificio sin atravesarlo."""

    EPS = 1e-9

    def _inside_any(self, px, py, rects):
        for r in rects:
            if (r.x + self.EPS < px < r.x + r.w - self.EPS
                    and r.y + self.EPS < py < r.y + r.d - self.EPS):
                return True
        return False

    def test_contorno_expuesto_de_barra_simple(self):
        layouts, _adv = bw.build_layout(_programa("Vivienda"))
        segments = exposed_outline_segments(layouts[0].all_rooms)
        self.assertTrue(segments)
        # Con pasillo, el frente exterior es el borde delantero del
        # propio pasillo (y = -1,2), no el de los locales (y = 0).
        frentes = [s for s in segments
                   if abs(s[1] - (-layouts[0].corridor.d)) < 1e-9
                   and s[5] == -1.0]
        self.assertTrue(frentes)

    def test_alero_nunca_dentro_del_edificio(self):
        for usage in ("Vivienda", "Escuela primaria", "Hospital",
                      "Centro comunitario"):
            data = _programa(usage)
            data.terrain_type = bw.TERRAIN_TYPES[2]
            for variant in bw.generate_variants(data)[:6]:
                for layout in variant.layouts:
                    pieces = layout.all_rooms
                    for x1, y1, x2, y2 in eaves_outline_segments(
                            pieces, 0.6):
                        for step in range(11):
                            t = step / 10.0
                            px = x1 + (x2 - x1) * t
                            py = y1 + (y2 - y1) * t
                            self.assertFalse(
                                self._inside_any(px, py, pieces),
                                (usage, variant.key, px, py))

    def test_alero_cero_y_negativo_no_dibuja(self):
        layouts, _adv = bw.build_layout(_programa("Vivienda"))
        self.assertEqual(eaves_outline_segments(layouts[0].all_rooms, 0.0),
                         [])
        self.assertEqual(eaves_outline_segments(layouts[0].all_rooms, -1.0),
                         [])

    def test_esquinas_convexas_cerradas_con_ingleta(self):
        class R:
            def __init__(self, x, y, w, d):
                self.x, self.y, self.w, self.d = x, y, w, d
        segments = eaves_outline_segments([R(0, 0, 6, 3)], 0.5)
        # la barra 6×3 produce un alero rectangular completo de 7×4
        xs = [x for x1, _y1, x2, _y2 in segments
              for x in (x1, x2)]
        ys = [y for _x1, y1, _x2, y2 in segments
              for y in (y1, y2)]
        self.assertAlmostEqual(min(xs), -0.5, places=6)
        self.assertAlmostEqual(max(xs), 6.5, places=6)
        self.assertAlmostEqual(min(ys), -0.5, places=6)
        self.assertAlmostEqual(max(ys), 3.5, places=6)


class TestAleroEnSVG(ARQGenTestCase):
    """El plano SVG dibuja el alero leyendo el metadata del edificio."""

    def _contexto_con_edificio(self, protection_solar=True):
        context = self.application.create_project(
            self.project_path("aleros.arqgen"), name="Aleros")
        data = _programa("Vivienda")
        data.protection_solar = protection_solar
        data.eaves_m = 0.6
        bw.apply_plan(data, context)
        return context

    def test_svg_contiene_alero(self):
        from exporters.svg_exporter import export_plan_svg
        context = self._contexto_con_edificio()
        try:
            out = os.path.join(self.tmp, "plano_aleros.svg")
            export_plan_svg(context, out)
            with open(out, "r", encoding="utf-8") as handle:
                svg = handle.read()
            self.assertIn('class="alero"', svg)
            self.assertIn("Alero 0.60 m", svg)
        finally:
            context.close()

    def test_svg_sin_proteccion_solar_no_dibuja_alero(self):
        from exporters.svg_exporter import export_plan_svg
        context = self._contexto_con_edificio(protection_solar=False)
        try:
            out = os.path.join(self.tmp, "plano_sin_aleros.svg")
            export_plan_svg(context, out)
            with open(out, "r", encoding="utf-8") as handle:
                svg = handle.read()
            self.assertNotIn('class="alero"', svg)
        finally:
            context.close()

    def test_alero_manual_anula_la_deteccion(self):
        from exporters.svg_exporter import export_plan_svg
        context = self._contexto_con_edificio()
        try:
            out = os.path.join(self.tmp, "plano_manual.svg")
            export_plan_svg(context, out, eaves_m=0.0)
            with open(out, "r", encoding="utf-8") as handle:
                svg = handle.read()
            self.assertNotIn('class="alero"', svg)
        finally:
            context.close()


def _display_available() -> bool:
    try:
        import tkinter
        tkinter.Tk().destroy()
        return True
    except Exception:  # noqa: BLE001 — sin display en CI
        return False


DISPLAY = _display_available()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestGUIAlerosYEstilo(ARQGenTestCase):
    """El preview dibuja los aleros y el paso 1 sugiere el estilo."""

    def setUp(self):
        super().setUp()
        from ui.app_window import ARQGenWindow
        self.context = self.application.create_project(
            self.project_path("aleros_gui.arqgen"),
            name="Proyecto Aleros")
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        super().tearDown()

    def _open(self):
        self.window.open_building_wizard()
        return self.window._building_dialog

    def test_preview_dibuja_alero_con_etiqueta(self):
        dialog = self._open()
        try:
            dialog._bld_widgets["usage"].set("Vivienda")
            dialog._bld_load_usage()
            dialog._bld_generate_variants()
            self.window.update()
            canvas = dialog._bld_widgets["variant_canvas"]
            self.assertTrue(canvas.find_withtag("alero"))
        finally:
            dialog.destroy()

    def test_sugerir_uso_carga_estilo_sugerido(self):
        dialog = self._open()
        try:
            dialog._bld_widgets["usage"].set("Hospital")
            dialog._bld_load_usage()
            data = dialog._bld_data
            self.assertEqual(data.architectural_style, "High-tech")
            self.assertEqual(dialog._bld_widgets["style"].get(),
                             "High-tech")
            # la elección manual del usuario se respeta (hecha en el
            # widget, como en la vida real: _collect lee el combo)
            dialog._bld_widgets["usage"].set("Escuela primaria")
            dialog._bld_widgets["style"].set("Brutalista")
            dialog._bld_load_usage()
            self.assertEqual(dialog._bld_data.architectural_style,
                             "Brutalista")
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
