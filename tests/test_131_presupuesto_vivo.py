"""PRESUPUESTO VIVO SOBRE LAS VARIANTES (v3.12.0).

Lo pedido: «presupuesto vivo sobre las variantes» — cada variante del
motor de plantas sabe CUÁNTO CUESTA en renglones OFICIALES del
catálogo PRECONS III, el coste se ve junto a la puntuación, cambia de
calidad de acabados y el presupuesto se recalcula al vivo sin
regenerar nada, y la comparativa sale en PNG.

Cobertura de estas pruebas:

* Takeoff paramétrico (ui.variant_budget, puro): muros por tipología
  (bloque 0.10/0.15/0.20, madera, panel sándwich, hormigón), losa por
  tipología (vigueta, maciza, madera), vanos que descuentan muro,
  escaleras, aparatos sanitarios por tipo de local, puntos eléctricos,
  preparación y cimentación solo en el nivel 0, cubierta y alero en el
  último nivel, columnas solo con pórtico.
* Clasificación geométrica exterior/interior: rectángulo exacto,
  forma en L y muestreo que no se deja engañar por las esquinas.
* Estimación: precios oficiales resueltos SIEMPRE del ruleset,
  renglones agregados por código, categorías ordenadas, coste/m2,
  determinismo estricto y renglón ausente que anota aviso sin caer.
* Calidad de acabados: Económica < Estándar < Premium, obra gruesa
  INTACTA, calidad inválida → Estándar, y re-estimación en vivo
  (attach_costs reemplaza).
* PNG comparativo determinista (exporters.png_exporter).
* GUI (Tk bajo Xvfb): el diálogo de regeneración y el paso 6 del
  asistente muestran la columna de coste, la calidad recalcula al
  vivo, el botón «PNG de costes» exporta y el mensaje tras sustituir
  anuncia la estimación.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui import variant_budget as vb
from ui.building_wizard import (BuildingWizardData, LevelLayout, LevelSpec,
                                OpeningPlacement, PlacedRoom, PlantVariant,
                                RelationSpec, RoomSpec)


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


# -- fixtures -------------------------------------------------------------------------

def _data_vivienda() -> BuildingWizardData:
    data = BuildingWizardData(name="Casa de Pruebas")
    data.levels = [LevelSpec(name="Planta Baja", height_m=3.0),
                   LevelSpec(name="Planta Alta", height_m=3.0)]
    data.rooms = [
        RoomSpec(name="Sala", space_type="ROOM", width_m=4.0, depth_m=5.0,
                 level_ref="Planta Baja", with_window=True),
        RoomSpec(name="Cocina", space_type="KITCHEN", width_m=3.0,
                 depth_m=2.5, level_ref="Planta Baja", with_window=True),
        RoomSpec(name="Bano", space_type="BATHROOM", width_m=1.8,
                 depth_m=2.0, level_ref="Planta Baja", with_window=False),
        RoomSpec(name="Dormitorio", space_type="ROOM", width_m=3.5,
                 depth_m=4.0, level_ref="Planta Alta", with_window=True),
    ]
    data.relations = [RelationSpec(a_name="Sala", b_name="Cocina",
                                   kind_es="Adyacente a", with_door=True)]
    return data


def _layout_rectangular(nombre: str = "PB") -> LevelLayout:
    """Dos locales que forman un rectángulo 7×4 con partición central."""
    a = PlacedRoom(name="A", space_type="ROOM", level=nombre,
                   x=0.0, y=0.0, w=4.0, d=4.0)
    b = PlacedRoom(name="B", space_type="ROOM", level=nombre,
                   x=4.0, y=0.0, w=3.0, d=4.0)
    tagged = []
    for room in (a, b):
        for segmento in bw.rect_segments(room):
            tagged.append((segmento, room.name))
    return LevelLayout(level_name=nombre, rooms=[a, b], corridor=None,
                       walls=bw.merge_walls(tagged), doors=[], windows=[])


def _layout_en_l(nombre: str = "PB") -> LevelLayout:
    """Forma en L: A (0,0,4×3) + B (4,0,4×6)."""
    a = PlacedRoom(name="A", space_type="ROOM", level=nombre,
                   x=0.0, y=0.0, w=4.0, d=3.0)
    b = PlacedRoom(name="B", space_type="ROOM", level=nombre,
                   x=4.0, y=0.0, w=4.0, d=6.0)
    tagged = []
    for room in (a, b):
        for segmento in bw.rect_segments(room):
            tagged.append((segmento, room.name))
    return LevelLayout(level_name=nombre, rooms=[a, b], corridor=None,
                       walls=bw.merge_walls(tagged), doors=[], windows=[])


def _variante(layouts, titulo="prueba") -> PlantVariant:
    return PlantVariant(key="prueba", scheme="lineal", mirror=False,
                        title=titulo, description="", layouts=list(layouts))


class TestBaseCatalogo(ARQGenTestCase):
    """Ruleset real cargado una vez por la batería."""

    @classmethod
    def setUpClass(cls):
        from app.paths import resource_path
        from engines.precons_engine import PreconsRuleset
        cls.ruleset = PreconsRuleset.from_file(resource_path(
            "rulesets", "precons_iii_rospres_330.json"))


class TestClasificacionGeometrica(TestBaseCatalogo):
    """Muros exterior/interior con muestreo geométrico."""

    def test_rectangulo_exacto(self):
        ext, inte = vb._longitudes_de_muros(_layout_rectangular())
        # perímetro 2×(7+4) = 22 y partición central de 4 m
        self.assertAlmostEqual(ext, 22.0, delta=0.6)
        self.assertAlmostEqual(inte, 4.0, delta=0.6)

    def test_forma_en_l(self):
        ext, inte = vb._longitudes_de_muros(_layout_en_l())
        # perímetro de la L = 28 m; partición compartida de 3 m
        self.assertAlmostEqual(ext, 28.0, delta=1.0)
        self.assertAlmostEqual(inte, 3.0, delta=1.0)

    def test_layout_vacio(self):
        vacio = LevelLayout(level_name="PB", rooms=[], corridor=None,
                            walls=[], doors=[], windows=[])
        self.assertEqual(vb._longitudes_de_muros(vacio), (0.0, 0.0))

    def test_patio_cuenta_como_interior(self):
        # Un local rodeado por un patio NO es fachada: el patio cubre.
        a = PlacedRoom(name="Sala", space_type="ROOM", level="PB",
                       x=0.0, y=0.0, w=4.0, d=4.0)
        patio = PlacedRoom(name="Patio", space_type="PATIO", level="PB",
                           x=4.0, y=0.0, w=3.0, d=4.0)
        tagged = [(seg, r.name) for r in (a, patio)
                  for seg in bw.rect_segments(r)]
        layout = LevelLayout(level_name="PB", rooms=[a], corridor=patio,
                             walls=bw.merge_walls(tagged), doors=[],
                             windows=[])
        _ext, inte = vb._longitudes_de_muros(layout)
        self.assertGreater(inte, 3.5)  # la pared compartida con el patio


class TestTakeoffParametrico(TestBaseCatalogo):
    """Cantidades del trazado, por renglón oficial."""

    def test_rectangulo_cantidades_basicas(self):
        variante = _variante([_layout_rectangular()])
        filas = {f["code"]: f for f in vb.variant_takeoff(_data_vivienda(),
                                                          variante)}
        # muros: perímetro 22 + partición 4 = 26 m × 3.0 m de altura
        self.assertAlmostEqual(filas["030123"]["quantity"], 78.0, delta=1.8)
        # losa de vigueta: 28 m2 útiles
        self.assertAlmostEqual(filas["127121"]["quantity"], 28.0,
                               delta=0.6)
        # pisos igual que la losa (sin el patio)
        self.assertAlmostEqual(filas["140118"]["quantity"], 28.0, delta=0.6)
        # manigua: huella 7×4
        self.assertAlmostEqual(filas["011111"]["quantity"], 28.0, delta=0.1)
        # cimiento corrido: 26 m × 0.20 × 0.40
        self.assertAlmostEqual(filas["041424"]["quantity"], 2.08, delta=0.2)

    def test_vanos_descuentan_muro(self):
        base = _layout_rectangular()
        con_vanos = _layout_rectangular()
        con_vanos.windows.append(OpeningPlacement(
            kind="WINDOW", width_m=1.4, height_m=1.2, offset_m=0.5,
            sill_height_m=0.9))
        con_vanos.doors.append(OpeningPlacement(
            kind="DOOR", width_m=0.9, height_m=2.1, offset_m=1.0))
        sin_muro = {f["code"]: f for f in vb.variant_takeoff(
            _data_vivienda(), _variante([base]))}
        con_muro = {f["code"]: f for f in vb.variant_takeoff(
            _data_vivienda(), _variante([con_vanos]))}
        hueco = 1.4 * 1.2 + 0.9 * 2.1
        self.assertAlmostEqual(
            sin_muro["030123"]["quantity"] - con_muro["030123"]["quantity"],
            hueco, delta=0.3)

    def test_escalera_y_sanitarios(self):
        layout = _layout_rectangular()
        layout.rooms.append(PlacedRoom(name="Escalera PB",
                                       space_type="STAIR", level="PB",
                                       x=0.0, y=4.0, w=1.4, d=2.5))
        filas = {f["code"]: f for f in vb.variant_takeoff(
            _data_vivienda(), _variante([layout]))}
        self.assertAlmostEqual(filas["043424"]["quantity"],
                               1.4 * 2.5 * 0.35, delta=0.05)
        data = _data_vivienda()  # cocina + baño declarados arriba
        # los tipos del LAYOUT mandan: el rectángulo solo tiene ROOM
        self.assertNotIn("175111", filas)
        data2 = BuildingWizardData(name="Baños")
        data2.levels = [LevelSpec()]
        data2.rooms = [RoomSpec(name="Bano", space_type="BATHROOM")]
        layout_bano = LevelLayout(
            level_name="Planta Baja",
            rooms=[PlacedRoom(name="Bano", space_type="BATHROOM",
                              level="Planta Baja", x=0.0, y=0.0,
                              w=1.8, d=2.0)],
            corridor=None,
            walls=bw.merge_walls([(seg, "Bano") for seg in
                                  bw.rect_segments(PlacedRoom(
                                      name="B", space_type="BATHROOM",
                                      level="PB", x=0.0, y=0.0,
                                      w=1.8, d=2.0))]),
            doors=[], windows=[])
        filas2 = {f["code"]: f for f in vb.variant_takeoff(
            data2, _variante([layout_bano]))}
        self.assertEqual(filas2["175111"]["quantity"], 1.0)   # inodoro
        self.assertEqual(filas2["175123"]["quantity"], 1.0)   # lavamanos
        self.assertEqual(filas2["174202"]["quantity"], 1.0)   # ducha

    def test_tipologias_constructivas(self):
        variante = _variante([_layout_rectangular()])
        data = _data_vivienda()
        data.construction_type = "Madera ligera"
        codigos = {f["code"] for f in vb.variant_takeoff(data, variante)}
        self.assertIn("060112", codigos)   # tabiques de madera
        self.assertIn("066914", codigos)   # enviguetado de madera
        data.construction_type = "Panel prefabricado (sandwich)"
        filas = {f["code"]: f for f in vb.variant_takeoff(data, variante)}
        self.assertIn("035402", filas)     # muro de panel
        self.assertIn("124712", filas)     # cubierta de panel
        self.assertNotIn("110120", filas)
        data.construction_type = "Hormigón armado (monolítico)"
        filas = {f["code"]: f for f in vb.variant_takeoff(data, variante)}
        self.assertEqual(filas["045124"]["unit"], "m3")
        data.construction_type = "Losa maciza de hormigón"
        data.protection_solar = False   # el alero también es 042724
        filas = {f["code"]: f for f in vb.variant_takeoff(data, variante)}
        self.assertEqual(filas["042724"]["unit"], "m3")
        self.assertAlmostEqual(filas["042724"]["quantity"],
                               28.0 * 0.20, delta=0.2)

    def test_espesor_de_bloque_elige_renglon(self):
        variante = _variante([_layout_rectangular()])
        data = _data_vivienda()
        for espesor, esperado in ((0.10, "030121"), (0.15, "030122"),
                                  (0.20, "030123")):
            data.wall_thickness_m = espesor
            filas = {f["code"] for f in vb.variant_takeoff(data, variante)}
            self.assertIn(esperado, filas)

    def test_portico_anade_columnas(self):
        variante = _variante([_layout_rectangular()])
        data = _data_vivienda()
        data.structural_system = "Pórtico de hormigón"
        filas = {f["code"] for f in vb.variant_takeoff(data, variante)}
        self.assertIn("042125", filas)   # columnas
        self.assertIn("042424", filas)   # vigas de corona
        data.structural_system = "Muros portantes"
        filas = {f["code"] for f in vb.variant_takeoff(data, variante)}
        self.assertNotIn("042125", filas)

    def test_alero_solo_con_proteccion_solar(self):
        variante = _variante([_layout_rectangular()])
        data = _data_vivienda()
        data.protection_solar = True
        filas = {f["code"]: f for f in vb.variant_takeoff(data, variante)}
        self.assertIn("042724", filas)   # alero perimetral
        data.protection_solar = False
        filas = {f["code"]: f for f in vb.variant_takeoff(data, variante)}
        self.assertNotIn("042724", filas)
        self.assertIn("110120", filas)   # la impermeabilización sigue

    def test_takeoff_vacio_amable(self):
        vacia = _variante([])
        self.assertEqual(vb.variant_takeoff(_data_vivienda(), vacia), [])
        costo = vb.estimate_variant_cost(_data_vivienda(), vacia,
                                         self.ruleset)
        self.assertEqual(costo.total, 0.0)
        self.assertEqual(costo.rows, [])


class TestEstimacion(TestBaseCatalogo):
    """Precios oficiales, categorías, determinismo y avisos."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = _data_vivienda()
        cls.variantes = bw.generate_variants(cls.data)
        vb.attach_costs(cls.data, cls.variantes, cls.ruleset, "Estándar")

    def test_todas_las_variantes_con_coste(self):
        self.assertGreaterEqual(len(self.variantes), 20)
        for variante in self.variantes:
            self.assertIsNotNone(variante.cost)
            self.assertGreater(variante.cost.total, 0.0)
            self.assertTrue(variante.cost.rows)
            self.assertIn("Muros", variante.cost.categories)
            self.assertIn("Estructura", variante.cost.categories)
            self.assertEqual(variante.cost.avisos, [])

    def test_precios_resueltos_del_ruleset(self):
        for fila in self.variantes[0].cost.rows:
            oficial = self.ruleset.official_price(fila["code"])
            self.assertEqual(fila["unit_price"], round(oficial["total"], 2))
            # la obra gruesa no lleva factor: importe = qty × precio
            if fila["category"] in vb.CATEGORIAS_DE_OBRA_GRUESA:
                self.assertAlmostEqual(
                    fila["amount"], round(fila["quantity"]
                                          * fila["unit_price"], 2),
                    delta=0.05)

    def test_renglones_agregados_sin_duplicados(self):
        codigos = [f["code"] for f in self.variantes[0].cost.rows]
        self.assertEqual(len(codigos), len(set(codigos)))

    def test_categorias_en_orden_del_catalogo(self):
        categorias = list(self.variantes[0].cost.categories)
        orden = [c for c in vb.CATEGORIAS if c in categorias]
        self.assertEqual(categorias, orden)

    def test_variantes_se_diferencian_en_coste(self):
        totales = [v.cost.total for v in self.variantes]
        self.assertGreater(max(totales) / min(totales), 1.02)
        # y todas viven en una banda sane: coste/m2 positivo y acotado
        for v in self.variantes:
            self.assertGreater(v.cost.cost_m2, 100.0)
            self.assertLess(v.cost.cost_m2, 5000.0)

    def test_coste_por_metro_cuadrado(self):
        costo = self.variantes[0].cost
        self.assertEqual(costo.cost_m2,
                         round(costo.total / costo.area_m2, 2))
        vacia = _variante([])
        self.assertEqual(
            vb.estimate_variant_cost(self.data, vacia, self.ruleset
                                     ).cost_m2, 0.0)

    def test_determinismo_estricto(self):
        variante = self.variantes[1]
        otra = vb.estimate_variant_cost(self.data, variante, self.ruleset,
                                        "Estándar")
        self.assertEqual(otra.to_dict(), variante.cost.to_dict())

    def test_calidad_monotona_y_obra_gruesa_intacta(self):
        variante = self.variantes[0]
        economica = vb.estimate_variant_cost(self.data, variante,
                                             self.ruleset, "Económica")
        estandar = variante.cost
        premium = vb.estimate_variant_cost(self.data, variante,
                                           self.ruleset, "Premium")
        self.assertLess(economica.total, estandar.total)
        self.assertLess(estandar.total, premium.total)
        for categoria in vb.CATEGORIAS_DE_OBRA_GRUESA:
            self.assertEqual(economica.categories.get(categoria, 0.0),
                             estandar.categories.get(categoria, 0.0))
            self.assertEqual(premium.categories.get(categoria, 0.0),
                             estandar.categories.get(categoria, 0.0))
        factor = vb.FACTOR_CALIDAD["Premium"]
        self.assertAlmostEqual(
            premium.categories["Pisos"],
            round(estandar.categories["Pisos"] * factor, 2), delta=0.05)

    def test_calidad_invalida_cae_en_estandar(self):
        variante = self.variantes[0]
        rara = vb.estimate_variant_cost(self.data, variante, self.ruleset,
                                        "Lujo imperial")
        self.assertEqual(rara.calidad, "Estándar")
        self.assertEqual(rara.total, variante.cost.total)

    def test_attach_costs_reemplaza_el_coste(self):
        variante = self.variantes[0]
        antes = variante.cost.total
        vb.attach_costs(self.data, [variante], self.ruleset, "Premium")
        self.assertGreater(variante.cost.total, antes)
        self.assertEqual(variante.cost.calidad, "Premium")
        vb.attach_costs(self.data, [variante], self.ruleset, "Estándar")
        self.assertEqual(variante.cost.total, antes)

    def test_renglon_ausente_anota_aviso_y_sigue(self):
        from engines.precons_engine import PreconsRuleset
        mini = PreconsRuleset.from_dict({
            "code": "mini",
            "work_items": [i for i in self.ruleset.work_items
                           if i["code"] in ("011111", "140118")],
            "resources": [],
        })
        costo = vb.estimate_variant_cost(self.data, self.variantes[0],
                                         mini, "Estándar")
        self.assertGreater(costo.total, 0.0)
        self.assertEqual({f["code"] for f in costo.rows},
                         {"011111", "140118"})
        self.assertTrue(costo.avisos)
        self.assertTrue(all("Renglón" in a for a in costo.avisos))

    def test_variants_sin_coste_por_defecto(self):
        variante = _variante([_layout_rectangular()])
        self.assertIsNone(variante.cost)


class TestTextosYPng(TestBaseCatalogo):
    """fmt_cup, desglose y PNG comparativo determinista."""

    def test_fmt_cup(self):
        self.assertEqual(vb.fmt_cup(1582457.4), "1 582 457")
        self.assertEqual(vb.fmt_cup(0), "0")
        self.assertEqual(vb.fmt_cup(999.99), "1 000")

    def test_desglose_texto(self):
        data = _data_vivienda()
        variante = _variante([_layout_rectangular()])
        costo = vb.estimate_variant_cost(data, variante, self.ruleset)
        texto = vb.desglose_texto(costo)
        partes = texto.split(" · ")
        self.assertGreaterEqual(len(partes), 2)
        self.assertTrue(partes[0].startswith("Estructura"))
        importes = [float(p.split()[-1].rstrip("%")) for p in partes]
        self.assertEqual(importes, sorted(importes, reverse=True))
        self.assertEqual(vb.desglose_texto(
            vb.VariantCost()), "")

    def test_png_determinista_valido_y_distinto(self):
        from exporters.png_exporter import export_variant_costs_png
        data = _data_vivienda()
        variantes = bw.generate_variants(data)
        vb.attach_costs(data, variantes, self.ruleset, "Estándar")
        entradas = [(v.title, v.cost.total) for v in variantes]
        tmp = tempfile.mkdtemp(prefix="t131_")
        primero = os.path.join(tmp, "a.png")
        segundo = os.path.join(tmp, "b.png")
        export_variant_costs_png(entradas, primero, project_name=data.name,
                                 calidad="Estándar")
        export_variant_costs_png(entradas, segundo, project_name=data.name,
                                 calidad="Estándar")
        with open(primero, "rb") as fh:
            raw1 = fh.read()
        with open(segundo, "rb") as fh:
            raw2 = fh.read()
        self.assertEqual(raw1, raw2)
        self.assertEqual(raw1[:8], b"\x89PNG\r\n\x1a\n")
        tercero = os.path.join(tmp, "c.png")
        export_variant_costs_png(entradas[:5], tercero,
                                 project_name="Otra", calidad="Premium")
        with open(tercero, "rb") as fh:
            self.assertNotEqual(fh.read(), raw1)
        vacio = os.path.join(tmp, "vacio.png")
        export_variant_costs_png([], vacio)
        with open(vacio, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDialogoRegeneracionCostes(ARQGenTestCase):
    """El diálogo de regeneración con el presupuesto vivo integrado."""

    def _make_window(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.application.create_project(
            self.project_path("vivo_regen.arqgen"), name="Vivo Regen")
        return ARQGenWindow(self.context, self.application)

    def test_coste_en_variantes_y_calidad_viva(self):
        window = self._make_window()
        try:
            data = _data_vivienda()
            bw.apply_plan(data, window.ctx)
            window.update()
            window.open_regen_dialog()
            dialog = window._regen_dialog
            dialog._regen_generate()
            tree = dialog._regen_variant_tree
            hijos = tree.get_children()
            self.assertGreaterEqual(len(hijos), 20)
            primera = tree.item(hijos[0], "values")
            coste_estandar = float(str(primera[5]).replace(" ", ""))
            self.assertGreater(coste_estandar, 0.0)
            # la variante seleccionada trae desglose en la línea de
            # métricas
            self.assertIn("Estimación:", _texto_label(dialog),
                          "desglose en métricas")
            # cambiar la calidad recalcula AL VIVO (misma geometría)
            dialog._regen_calidad_var.set("Premium")
            dialog._regen_recostear()
            window.update()
            primera = tree.item(hijos[0], "values")
            coste_premium = float(str(primera[5]).replace(" ", ""))
            self.assertGreater(coste_premium, coste_estandar)
            # y el coste adjunto sigue siendo determinista
            variante = dialog._regen_state["variant"]
            self.assertEqual(variante.cost.calidad, "Premium")
            dialog.destroy()
        finally:
            window.destroy()
            self.context.close()

    def test_png_de_costes_exporta(self):
        window = self._make_window()
        try:
            data = _data_vivienda()
            bw.apply_plan(data, window.ctx)
            window.update()
            window.open_regen_dialog()
            dialog = window._regen_dialog
            dialog._regen_generate()
            tmp = tempfile.mkdtemp(prefix="t131_gui_")
            destino = os.path.join(tmp, "comparativa.png")
            from ui import app_window as aw
            original = aw.filedialog.asksaveasfilename
            aw.filedialog.asksaveasfilename = (
                lambda **kwargs: destino)
            try:
                dialog._regen_png_costes()
            finally:
                aw.filedialog.asksaveasfilename = original
            self.assertTrue(os.path.exists(destino))
            with open(destino, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
            dialog.destroy()
        finally:
            window.destroy()
            self.context.close()

    def test_recostear_sin_variantes_no_rompe(self):
        window = self._make_window()
        try:
            data = _data_vivienda()
            bw.apply_plan(data, window.ctx)
            window.update()
            window.open_regen_dialog()
            dialog = window._regen_dialog
            dialog._regen_recostear()   # sin variantes generadas aún
            dialog.destroy()
        finally:
            window.destroy()
            self.context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestAsistentePaso6Costes(ARQGenTestCase):
    """El paso 6 del asistente de edificación también ve el coste."""

    def test_columna_coste_y_calidad(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.application.create_project(
            self.project_path("vivo_wizard.arqgen"), name="Vivo Wizard")
        window = ARQGenWindow(self.context, self.application)
        try:
            window.update()
            window.open_building_wizard()
            dialog = window._building_dialog
            dialog._bld_widgets["usage"].set("Vivienda")
            dialog._bld_load_usage()
            dialog._bld_generate_variants()
            tree = dialog._bld_widgets["variant_tree"]
            hijos = tree.get_children()
            self.assertGreaterEqual(len(hijos), 20)
            primera = tree.item(hijos[0], "values")
            coste_estandar = float(str(primera[4]).replace(" ", ""))
            self.assertGreater(coste_estandar, 0.0)
            self.assertIn("Estimación PRECONS",
                          dialog._bld_widgets["variant_desc"].cget("text"))
            dialog._bld_widgets["calidad"].set("Económica")
            dialog._bld_coste_on_calidad()
            window.update()
            primera = tree.item(hijos[0], "values")
            coste_economico = float(str(primera[4]).replace(" ", ""))
            self.assertLess(coste_economico, coste_estandar)
            dialog.destroy()
        finally:
            window.destroy()
            self.context.close()


def _texto_label(dialog) -> str:
    """Texto de la línea de métricas del diálogo (búsqueda recursiva)."""

    def visitar(widget) -> str:
        try:
            texto = str(widget.cget("text"))
        except Exception:  # noqa: BLE001 — sin opción text
            texto = ""
        if "Estimación" in texto:
            return texto
        for hijo in widget.winfo_children():
            encontrado = visitar(hijo)
            if encontrado:
                return encontrado
        return ""

    return visitar(dialog)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
