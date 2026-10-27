"""Representación arquitectónica v2.6.0: CORTES, ELEVACIONES, DETALLES,
TRAMAS (HATCH) POR MATERIAL y COLUMNAS SEGÚN TIPOLOGÍA CONSTRUCTIVA.

Lo pedido por el usuario: «piensa como arquitecto… cortes, elevaciones,
detalles, tipos de hatch para los muros, ubicación de columnas según
tipología constructiva, etc.».
"""

from __future__ import annotations

import os
import tempfile
import unittest
import xml.dom.minidom

from tests.base import ARQGenTestCase

from core.geometry import representation as rep
from core.geometry import structural as st
from exporters import view_exporter as ve
from ui import building_wizard as bw
from ui.building_wizard import BuildingWizardData, LevelSpec


def _data(usage: str = "Vivienda", niveles: int = 1,
          ctype: str = "Mampostería de bloque + losa de vigueta",
          terrain: str = "Regular (plano)",
          stairs: str = "Automática (según niveles y terreno)",
          climate: str = "Cálido húmedo (tropical lluvioso)",
          style: str = "Contemporáneo",
          scheme_key: str | None = None) -> BuildingWizardData:
    """Datos listos con el programa del uso social cargado."""
    data = BuildingWizardData()
    data.levels = [LevelSpec(f"Nivel {i + 1}", 3.0)
                   for i in range(niveles)]
    data.usage_type = usage
    data.terrain_type = terrain
    data.stairs_mode = stairs
    data.construction_type = ctype
    data.climate = climate
    data.architectural_style = style
    bw.apply_usage_program(data)
    return data


def _variant(data: BuildingWizardData, key: str | None = None):
    variants = bw.generate_variants(data)
    if not variants:
        raise AssertionError("sin variantes")
    if key:
        for variant in variants:
            if variant.key == key:
                return variant
        raise AssertionError(f"no está la variante {key}")
    return variants[0]


# ---------------------------------------------------------------------------
# TRAMAS POR MATERIAL
# ---------------------------------------------------------------------------

class TestTramasHatch(ARQGenTestCase):

    def test_catalogo_ocho_tramas(self):
        self.assertEqual(len(rep.HATCH_PATTERNS), 8)
        for key in ("mamposteria", "hormigon", "madera", "piedra",
                    "tierra", "acero", "panel", "galvanizado"):
            self.assertIn(key, rep.HATCH_PATTERNS)

    def test_todas_las_tipologias_tienen_trama(self):
        for ctype in bw.CONSTRUCTION_TYPES:
            key = rep.hatch_key_for(ctype)
            self.assertIn(key, rep.HATCH_PATTERNS, ctype)

    def test_trama_por_tipologia(self):
        self.assertEqual(rep.hatch_key_for(
            "Mampostería de bloque + losa de vigueta"), "mamposteria")
        self.assertEqual(rep.hatch_key_for(
            "Hormigón armado (monolítico)"), "hormigon")
        self.assertEqual(rep.hatch_key_for("Madera ligera"), "madera")
        self.assertEqual(rep.hatch_key_for("Muros de piedra"), "piedra")
        self.assertEqual(rep.hatch_key_for("Tierra (adobe o tapial)"),
                         "tierra")
        self.assertEqual(rep.hatch_key_for("Estructura metálica (acero)"),
                         "acero")
        self.assertEqual(rep.hatch_key_for(
            "Panel prefabricado (sandwich)"), "panel")

    def test_segmentos_dentro_del_rectangulo(self):
        for key in rep.HATCH_PATTERNS:
            for rect in ((0.0, 0.0, 0.2, 6.0), (2.0, 3.0, 5.0, 0.2),
                         (0.0, 0.0, 0.5, 0.5)):
                segs = rep.hatch_segments(*rect, key)
                x0, y0, w, d = rect
                for (ax1, ay1), (ax2, ay2) in segs:
                    self.assertGreaterEqual(min(ax1, ax2), x0 - 1e-9, key)
                    self.assertLessEqual(max(ax1, ax2), x0 + w + 1e-9, key)
                    self.assertGreaterEqual(min(ay1, ay2), y0 - 1e-9, key)
                    self.assertLessEqual(max(ay1, ay2), y0 + d + 1e-9, key)

    def test_tramas_solida_y_ninguno_no_dibujan(self):
        self.assertEqual(rep.hatch_segments(0, 0, 1, 1, "acero"), [])
        self.assertEqual(rep.hatch_segments(0, 0, 1, 1, "panel"), [])

    def test_determinismo(self):
        a = rep.hatch_segments(0, 0, 0.3, 5.0, "piedra")
        b = rep.hatch_segments(0, 0, 0.3, 5.0, "piedra")
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# COLUMNAS SEGÚN TIPOLOGÍA
# ---------------------------------------------------------------------------

class TestColumnas(ARQGenTestCase):

    def test_reglas_para_las_diez_tipologias(self):
        for ctype in bw.CONSTRUCTION_TYPES:
            rule = st.column_rule(ctype)
            self.assertTrue(rule.strategy, ctype)
            self.assertGreaterEqual(rule.size_m, 0.0, ctype)

    def test_estrategias_por_tipologia(self):
        self.assertEqual(st.column_rule(
            "Hormigón armado (monolítico)").strategy, st.STRATEGY_GRID)
        self.assertEqual(st.column_rule(
            "Mampostería de bloque + losa de vigueta").strategy,
            st.STRATEGY_TIE)
        self.assertEqual(st.column_rule("Madera ligera").strategy,
                         st.STRATEGY_POST)
        self.assertEqual(st.column_rule(
            "Panel prefabricado (sandwich)").strategy, st.STRATEGY_NONE)
        self.assertEqual(st.column_rule(
            "Tierra (adobe o tapial)").strategy, st.STRATEGY_NONE)

    def test_autoporante_sin_columnas(self):
        for ctype in ("Panel prefabricado (sandwich)",
                      "Tierra (adobe o tapial)"):
            data = _data(ctype=ctype)
            variant = _variant(data)
            self.assertEqual(
                st.column_placements(variant.layouts, data), [], ctype)

    def test_malla_de_portico_en_esquinas_del_envolvente(self):
        data = _data(ctype="Hormigón armado (monolítico)")
        variant = _variant(data)
        columns = st.column_placements(variant.layouts, data)
        self.assertTrue(columns)
        rooms = variant.layouts[0].all_rooms
        min_x = min(pr.x for pr in rooms)
        max_x = max(pr.x + pr.w for pr in rooms)
        min_y = min(pr.y for pr in rooms)
        max_y = max(pr.y + pr.d for pr in rooms)
        centers = [(round(c.x + c.w / 2, 2), round(c.y + c.d / 2, 2))
                   for c in columns]
        # Al menos 3 de las 4 esquinas del envolvente quedan columneadas
        # (la cuarta puede tener un vano justo en la esquina: ahí el
        # motor se niega, y es lo correcto).
        cubiertas = sum(
            1 for corner in ((min_x, min_y), (max_x, min_y),
                             (min_x, max_y), (max_x, max_y))
            if (round(corner[0], 2), round(corner[1], 2)) in centers)
        self.assertGreaterEqual(cubiertas, 3, centers)

    def test_refuerzo_en_mamposteria_y_separacion_maxima(self):
        data = _data(ctype="Mampostería de bloque + losa de vigueta")
        variant = _variant(data)
        columns = st.column_placements(variant.layouts, data)
        kinds = st.columns_summary(columns)
        self.assertIn("esquina", kinds)
        rule = st.column_rule(data.construction_type)
        self.assertEqual(rule.size_m, 0.20)
        # muros largos reciben refuerzos intermedios
        long_walls = [w for w in variant.layouts[0].walls
                      if float(w["length"]) > rule.spacing_m]
        if long_walls:
            self.assertIn("refuerzo", kinds)

    def test_columnas_fuera_de_vanos(self):
        for ctype in ("Hormigón armado (monolítico)",
                      "Mampostería de bloque + losa de vigueta"):
            data = _data(ctype=ctype)
            variant = _variant(data)
            layout = variant.layouts[0]
            openings = list(layout.doors) + list(layout.windows)
            for column in st.column_placements([layout], data):
                cx, cy = column.center
                for opening in openings:
                    wall = layout.walls[opening.wall_index]
                    (sx, sy), (ex, ey) = wall["start"], wall["end"]
                    if abs(sy - ey) <= 1e-6:
                        fixed, lo = sy, sx + opening.offset_m
                        axis = cx
                        self.assertFalse(
                            abs(cy - fixed) < 0.05
                            and lo - 0.28 < axis < lo
                            + opening.width_m + 0.28,
                            f"{ctype}: columna en vano")
                    else:
                        fixed, lo = sx, sy + opening.offset_m
                        axis = cy
                        self.assertFalse(
                            abs(cx - fixed) < 0.05
                            and lo - 0.28 < axis < lo
                            + opening.width_m + 0.28,
                            f"{ctype}: columna en vano")

    def test_columnas_dentro_de_la_envolvente(self):
        data = _data(ctype="Vigas y columnas prefabricadas")
        variant = _variant(data)
        for layout in variant.layouts:
            rooms = layout.all_rooms
            min_x = min(pr.x for pr in rooms)
            max_x = max(pr.x + pr.w for pr in rooms)
            min_y = min(pr.y for pr in rooms)
            max_y = max(pr.y + pr.d for pr in rooms)
            for column in st.column_placements([layout], data):
                # centrada en el eje del muro: sobresale media columna
                # como el propio muro (espesor/2) — tolerancia media col.
                self.assertGreaterEqual(
                    column.x, min_x - column.w / 2 - 0.01)
                self.assertLessEqual(column.x + column.w,
                                     max_x + column.w / 2 + 0.01)
                self.assertGreaterEqual(
                    column.y, min_y - column.d / 2 - 0.01)
                self.assertLessEqual(column.y + column.d,
                                     max_y + column.d / 2 + 0.01)

    def test_galeria_arcada_en_patio_para_porticos(self):
        data = _data(usage="Centro comunitario",
                     ctype="Hormigón armado (monolítico)")
        variants = bw.generate_variants(data)
        variant = next((v for v in variants if "patio" in v.key),
                       variants[0])
        layout = variant.layouts[0]
        patios = [pr for pr in layout.all_rooms
                  if pr.space_type == "PATIO"]
        if not patios:
            self.skipTest("la variante no trae patio")
        columns = st.column_placements([layout], data)
        galerias = [c for c in columns if c.kind == "galería"]
        self.assertTrue(galerias, "el patio no queda columneado")
        # y además rodeando el perímetro del patio (arcada)
        patio = patios[0]
        perimetro = [
            c for c in columns
            if patio.x - 0.35 <= c.x + c.w / 2 <= patio.x + patio.w + 0.35
            and patio.y - 0.35 <= c.y + c.d / 2 <= patio.y + patio.d + 0.35]
        self.assertGreaterEqual(len(perimetro), 4)

    def test_determinismo_y_dedupe(self):
        data = _data(ctype="Estructura metálica (acero)")
        variant = _variant(data)
        a = st.column_placements(variant.layouts, data)
        b = st.column_placements(variant.layouts, data)
        self.assertEqual([(c.x, c.y, c.kind) for c in a],
                         [(c.x, c.y, c.kind) for c in b])
        centers = [(round(c.x + c.w / 2, 2), round(c.y + c.d / 2, 2))
                   for c in a]
        self.assertEqual(len(centers), len(set(centers)))

    def test_incompatibilidad_sistema_estructural(self):
        aviso = st.structural_mismatch("Pórtico de hormigón",
                                       "Madera ligera")
        self.assertIsNotNone(aviso)
        self.assertIsNone(st.structural_mismatch(
            "Pórtico de hormigón", "Hormigón armado (monolítico)"))
        # autoporante: aviso informativo, no de error
        aviso2 = st.structural_mismatch("Pórtico de hormigón",
                                        "Tierra (adobe o tapial)")
        self.assertIsNotNone(aviso2)
        self.assertIn("autoportante", aviso2)


# ---------------------------------------------------------------------------
# ELEVACIONES
# ---------------------------------------------------------------------------

class TestElevaciones(ARQGenTestCase):

    def test_cuatro_fachadas(self):
        data = _data()
        variant = _variant(data)
        for side in rep.ELEVATION_SIDES:
            drawing = rep.elevation_view(variant, data, side)
            self.assertIn(side, drawing.caption)
            x0, y0, x1, y1 = drawing.bounds()
            self.assertLess(x0, x1)
            self.assertLess(y0, y1)
            self.assertLessEqual(y0, rep.GROUND_LINE_M + 1e-9)
            self.assertGreater(y1, 3.0)

    def test_frente_y_lateral(self):
        data = _data()
        data.facade_orientation = "Norte"
        variant = _variant(data)
        prims = rep.elevation_view(variant, data, "Norte").prims
        titulo = [p for p in prims if isinstance(p, rep.PText)
                  and p.tag == "titulo"]
        self.assertTrue(titulo)
        self.assertIn("frente", titulo[0].text)
        prims_sur = rep.elevation_view(variant, data, "Sur").prims
        texto_sur = [p for p in prims_sur if isinstance(p, rep.PText)
                     and p.tag == "titulo"][0].text
        self.assertIn("lateral", texto_sur)

    def test_vanos_proyectados_en_fachada_con_ventanas(self):
        data = _data()
        variant = _variant(data)
        # una fachada con vanos: busca la que tenga más muros con vanos
        counts = {}
        for side in rep.ELEVATION_SIDES:
            drawing = rep.elevation_view(variant, data, side)
            counts[side] = sum(1 for p in drawing.prims
                               if isinstance(p, rep.PRect)
                               and p.tag == "vano")
        self.assertGreater(max(counts.values()), 0)

    def test_alero_dibujado_solo_con_proteccion(self):
        data = _data()
        variant = _variant(data)
        con = rep.elevation_view(variant, data, "Norte")
        self.assertTrue(any(p.tag == "alero" for p in con.prims))
        data2 = _data()
        data2.protection_solar = False
        variant2 = _variant(data2)
        sin = rep.elevation_view(variant2, data2, "Norte")
        self.assertFalse(any(p.tag == "alero" for p in sin.prims))

    def test_terreno_escalones_con_desnivel(self):
        data = _data(terrain="Terreno con desnivel fuerte")
        variants = bw.generate_variants(data)
        variant = next((v for v in variants
                        if any(pr.floor_rise_m > 0.01
                               for layout in v.layouts
                               for pr in layout.all_rooms)), None)
        if variant is None:
            self.skipTest("ninguna variante aplica desnivel")
        pasos = 0
        for side in ("Norte", "Sur"):
            drawing = rep.elevation_view(variant, data, side)
            terreno = [p for p in drawing.prims
                       if isinstance(p, rep.PLine) and p.tag == "terreno"]
            # con desnivel hay líneas de terreno y algún peldaño elevado
            self.assertTrue(terreno, side)
            pasos += sum(1 for p in terreno
                         if max(p.y1, p.y2) > rep.GROUND_LINE_M + 0.01)
        self.assertGreater(pasos, 0)

    def test_cubierta_segun_clima_y_estilo(self):
        data = _data(climate="Frío (necesita calefacción)")
        self.assertEqual(rep.roof_profile(data).kind, "dos_aguas")
        data2 = _data(climate="Templado", style="Minimalista")
        self.assertEqual(rep.roof_profile(data2).kind, "plana")
        data3 = _data(climate="Cálido húmedo (tropical lluvioso)",
                      style="Vernáculo tropical")
        self.assertEqual(rep.roof_profile(data3).kind, "un_agua")


PLineAlias = rep.PLine  # alias de legibilidad para el test anterior


# ---------------------------------------------------------------------------
# CORTES
# ---------------------------------------------------------------------------

class TestCortes(ARQGenTestCase):

    def test_ambos_ejes_con_cimentacion(self):
        data = _data()
        variant = _variant(data)
        for axis in rep.SECTION_AXES:
            drawing = rep.section_view(variant, data, axis)
            tags = {p.tag for p in drawing.prims if p.tag}
            self.assertIn("cimentacion", tags, axis)
            self.assertIn("sobrecimiento", tags, axis)
            self.assertIn("losa", tags, axis)
            self.assertIn("terreno", tags, axis)
            self.assertIn("cota", tags, axis)

    def test_fundaciones_bajo_el_cero(self):
        data = _data()
        variant = _variant(data)
        drawing = rep.section_view(variant, data, "Transversal")
        for prim in drawing.prims:
            if isinstance(prim, rep.PRect) and prim.tag == "cimentacion":
                self.assertLessEqual(prim.y, rep.GROUND_LINE_M)
                break
        else:
            self.fail("sin zapatas")

    def test_losas_por_nivel(self):
        data = _data(usage="Hospital", niveles=2)
        variant = _variant(data)
        drawing = rep.section_view(variant, data, "Longitudinal")
        losas = [p for p in drawing.prims
                 if isinstance(p, rep.PRect) and p.tag == "losa"]
        self.assertTrue(losas)
        # al menos dos alturas de losa (nivel 1 y nivel 2)
        zetas = {round(p.y + p.d, 2) for p in losas}
        self.assertGreaterEqual(len(zetas), 2)

    def test_escaleria_y_su_vacio(self):
        """La escalera aparece en el corte y su vacío abre la losa del
        nivel 2 (el piso del arranque, en el nivel 1, queda sólido)."""
        data = _data(usage="Hospital", niveles=2,
                     stairs="Sí, incluir siempre")
        variant = _variant(data)
        layout1 = next((l for l in variant.layouts
                        if any(pr.space_type == "STAIR"
                               for pr in l.all_rooms)), None)
        self.assertIsNotNone(layout1, "sin escalera")
        stair = next(pr for pr in layout1.all_rooms
                     if pr.space_type == "STAIR")
        drawing = rep.section_view(variant, data, "Transversal")
        escalera = [p for p in drawing.prims if p.tag == "escalera"]
        self.assertTrue(escalera, "la escalera no aparece en el corte")
        losas = [p for p in drawing.prims
                 if isinstance(p, rep.PRect) and p.tag == "losa"]
        # nivel 1 (losa a 3.0): cubre la banda de la escalera
        nivel1 = [p for p in losas if abs((p.y + p.d) - 3.0) < 0.01]
        self.assertTrue(nivel1)
        self.assertTrue(any(
            p.x < stair.y + stair.d - 0.05
            and p.x + p.w > stair.y + 0.05 for p in nivel1))
        # TODA losa superior: NO cubre la banda de la escalera (el
        # hueco de escalera sube hasta la cubierta)
        superiores = [p for p in losas if (p.y + p.d) > 3.05]
        if superiores:
            for p in superiores:
                solapa = p.x < stair.y + stair.d - 0.05 \
                    and p.x + p.w > stair.y + 0.05
                self.assertFalse(solapa, "una losa superior tapa el "
                                         "hueco de la escalera")

    def test_vano_sobre_patio(self):
        data = _data(usage="Centro comunitario")
        variants = bw.generate_variants(data)
        # un patio PARCIAL: en_H_patio o similar (no el patio de todo
        # el ancho, cuyo vacío dejaría la losa entera abierta)
        variant = next((v for v in variants if v.key.startswith("en_H_patio")
                        or v.key.startswith("en_cruz_patio")
                        or v.key.startswith("en_L_patio")), None)
        if variant is None:
            variant = next((v for v in variants if "patio" in v.key),
                           variants[0])
        layout = variant.layouts[0]
        patios = [pr for pr in layout.all_rooms
                  if pr.space_type == "PATIO"]
        if not patios:
            self.skipTest("sin patio en la variante")
        patio = patios[0]
        drawing = rep.section_view(variant, data, "Longitudinal")
        losas = [p for p in drawing.prims
                 if isinstance(p, rep.PRect) and p.tag == "losa"]
        if not losas:
            self.skipTest("el corte no cruza losas con este patio")
        for losa in losas:
            x_lo, x_hi = losa.x, losa.x + losa.w
            solapa = x_lo < patio.x + patio.w - 0.05 and \
                x_hi > patio.x + 0.05
            self.assertFalse(solapa,
                             "una losa tapa el patio en el corte")

    def test_cubierta_dos_aguas_dibuja_cumbrera(self):
        data = _data(climate="Frío (necesita calefacción)")
        variant = _variant(data)
        drawing = rep.section_view(variant, data, "Transversal")
        cubierta = [p for p in drawing.prims
                    if isinstance(p, rep.PLine) and p.tag == "cubierta"]
        self.assertGreaterEqual(len(cubierta), 2)

    def test_respaldo_nivel_de_corte(self):
        data = _data()
        variant = _variant(data)
        drawing = rep.section_view(variant, data, "Transversal")
        titulo = [p.text for p in drawing.prims
                  if isinstance(p, rep.PText) and p.tag == "titulo"][0]
        self.assertIn("CORTE TRANSVERSAL", titulo)


# ---------------------------------------------------------------------------
# DETALLES CONSTRUCTIVOS
# ---------------------------------------------------------------------------

class TestDetalles(ARQGenTestCase):

    def test_todas_las_tipologias_tienen_nodos(self):
        for ctype in bw.CONSTRUCTION_TYPES:
            data = _data(ctype=ctype)
            nodes = rep.detail_library(data)
            self.assertGreaterEqual(len(nodes), 4, ctype)
            codes = [n.code for n in nodes]
            self.assertEqual(len(codes), len(set(codes)), ctype)

    def test_nodos_base(self):
        data = _data()
        codes = [n.code for n in rep.detail_library(data)]
        self.assertIn("DET-CIM-01", codes)
        self.assertIn("DET-MUR-01", codes)
        self.assertIn("DET-VAN-01", codes)
        self.assertIn("DET-VAN-02", codes)

    def test_nudo_de_portico_solo_en_mallas(self):
        data = _data(ctype="Hormigón armado (monolítico)")
        self.assertIn("DET-PIL-01",
                      [n.code for n in rep.detail_library(data)])
        data2 = _data(ctype="Mampostería de bloque + losa de vigueta")
        self.assertIn("DET-MUR-02",
                      [n.code for n in rep.detail_library(data2)])
        self.assertNotIn("DET-PIL-01",
                         [n.code for n in rep.detail_library(data2)])

    def test_escalera_solo_si_se_pide(self):
        data = _data(usage="Hospital", niveles=2)
        self.assertIn("DET-ESC-01",
                      [n.code for n in rep.detail_library(data)])
        data2 = _data(stairs="No incluir")
        self.assertNotIn("DET-ESC-01",
                         [n.code for n in rep.detail_library(data2)])

    def test_alero_solo_con_proteccion(self):
        data = _data()
        self.assertIn("DET-CUB-01",
                      [n.code for n in rep.detail_library(data)])
        data2 = _data()
        data2.protection_solar = False
        self.assertNotIn("DET-CUB-01",
                         [n.code for n in rep.detail_library(data2)])

    def test_memoria_sustantiva_y_esquema(self):
        data = _data()
        for node in rep.detail_library(data):
            self.assertGreater(len(node.descripcion), 90, node.code)
            self.assertTrue(node.prims, node.code)
            self.assertTrue(node.titulo, node.code)


# ---------------------------------------------------------------------------
# PLANTA COMPLETA
# ---------------------------------------------------------------------------

class TestPlantaCompleta(ARQGenTestCase):

    def test_tags_tecnicos(self):
        data = _data(ctype="Hormigón armado (monolítico)")
        variant = _variant(data)
        drawing = rep.plan_view(variant, data)
        tags = {p.tag for p in drawing.prims if p.tag}
        for expected in ("local", "muro", "vano", "columna", "norte",
                         "cota", "escala", "titulo"):
            self.assertIn(expected, tags, expected)

    def test_columnas_cruzadas_en_planta(self):
        data = _data(ctype="Mampostería de bloque + losa de vigueta")
        variant = _variant(data)
        drawing = rep.plan_view(variant, data)
        columnas = [p for p in drawing.prims
                    if isinstance(p, rep.PRect) and p.tag == "columna"]
        self.assertTrue(columnas)
        cruces = [p for p in drawing.prims
                  if isinstance(p, rep.PLine) and p.tag == "columna"]
        self.assertGreaterEqual(len(cruces), len(columnas) * 2)

    def test_arco_de_puerta_presente(self):
        data = _data()
        variant = _variant(data)
        drawing = rep.plan_view(variant, data)
        arcos = [p for p in drawing.prims
                 if isinstance(p, rep.PArc) and p.tag == "arco"]
        self.assertTrue(arcos)
        for arco in arcos:
            self.assertGreater(arco.r, 0.3)
            self.assertEqual(arco.extent_deg, 90.0)

    def test_norte_girado_por_fachada(self):
        self.assertEqual(rep._north_angle("Norte"), 0.0)
        self.assertEqual(rep._north_angle("Sur"), 180.0)
        self.assertEqual(rep._north_angle("Este"), 90.0)
        self.assertEqual(rep._north_angle("Oeste"), -90.0)


# ---------------------------------------------------------------------------
# SVG DE VISTAS
# ---------------------------------------------------------------------------

class TestSVGDeVistas(ARQGenTestCase):

    def _export(self, view: str, aux: str = "") -> str:
        data = _data(ctype="Mampostería de bloque + losa de vigueta")
        variant = _variant(data)
        out = os.path.join(self.tmp,
                           f"vista_{view}_{aux or 'x'}.svg"
                           .replace("ó", "o").replace(" ", "_"))
        ve.export_view_svg(variant, data, out, view=view, aux=aux,
                           title="Prueba v2.6.0")
        return out

    def test_planta_svg_con_patron_de_trama(self):
        out = self._export("Planta")
        xml.dom.minidom.parse(out)
        texto = open(out, encoding="utf-8").read()
        self.assertIn("<pattern", texto)
        self.assertIn("trama-mamposteria", texto)

    def test_elevacion_svg(self):
        out = self._export("Elevación", "Norte")
        xml.dom.minidom.parse(out)
        texto = open(out, encoding="utf-8").read()
        self.assertIn("ELEVACIÓN NORTE", texto)

    def test_corte_svg(self):
        out = self._export("Corte", "Transversal")
        xml.dom.minidom.parse(out)
        texto = open(out, encoding="utf-8").read()
        self.assertIn("CORTE TRANSVERSAL", texto)

    def test_detalles_svg_con_memoria(self):
        out = self._export("Detalles")
        xml.dom.minidom.parse(out)
        texto = open(out, encoding="utf-8").read()
        self.assertIn("DET-CIM-01", texto)
        self.assertIn("zapata", texto.lower())

    def test_dibujo_de_vista_devuelve_lo_mismo_que_el_svg(self):
        data = _data()
        variant = _variant(data)
        d1 = ve.view_drawing(variant, data, "Elevación", "Sur")
        d2 = rep.elevation_view(variant, data, "Sur")
        self.assertEqual(d1.caption, d2.caption)
        self.assertEqual(len(d1.prims), len(d2.prims))


# ---------------------------------------------------------------------------
# METADATA, RESUMEN Y AVISOS
# ---------------------------------------------------------------------------

class TestIntegracionWizard(ARQGenTestCase):

    def test_metadata_representacion(self):
        data = _data(ctype="Estructura metálica (acero)")
        meta = bw._building_metadata(data)
        reps = meta["edificacion"]["representacion"]
        self.assertEqual(reps["cubierta"]["tipo"], "dos_aguas")
        self.assertEqual(reps["columnas"]["estrategia"],
                         st.STRATEGY_GRID)
        self.assertEqual(reps["columnas"]["medida_m"], 0.30)
        self.assertEqual(reps["hatch_muros"], "acero")
        self.assertEqual(reps["vistas"], ["Planta", "Elevación", "Corte",
                                          "Detalles"])

    def test_resumen_menciona_representacion(self):
        data = _data()
        summary = bw.step_summary(data)
        self.assertIn("· Representación:", summary)
        self.assertIn("cubierta", summary.lower())

    def test_aviso_de_incoherencia_estructural(self):
        data = _data(ctype="Madera ligera")
        data.structural_system = "Pórtico de hormigón"
        avisos = bw.site_advisories(data)
        self.assertTrue(any("funciona mejor con pórtico" in a
                            for a in avisos))
        data2 = _data(ctype="Hormigón armado (monolítico)")
        data2.structural_system = "Pórtico de hormigón"
        self.assertFalse(any("funciona mejor con pórtico" in a
                             for a in bw.site_advisories(data2)))


# ---------------------------------------------------------------------------
# GUI: SELECTOR DE VISTAS
# ---------------------------------------------------------------------------

class TestGUISelectorDeVistas(ARQGenTestCase):

    def setUp(self):
        super().setUp()
        from ui.app_window import ARQGenWindow
        self.context = self.application.create_project(
            self.project_path("vistas_gui.arqgen"),
            name="Proyecto Vistas")
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        super().tearDown()

    def _open(self):
        self.window.open_building_wizard()
        return self.window._building_dialog

    def test_planta_con_tramas_columnas_y_arcos(self):
        dialog = self._open()
        try:
            dialog._bld_widgets["usage"].set("Vivienda")
            dialog._bld_load_usage()
            dialog._bld_generate_variants()
            self.window.update()
            canvas = dialog._bld_widgets["variant_canvas"]
            self.assertTrue(canvas.find_withtag("trama"))
            self.assertTrue(canvas.find_withtag("columna"))
            self.assertTrue(canvas.find_withtag("arco"))
            self.assertTrue(canvas.find_withtag("norte"))
            self.assertTrue(canvas.find_withtag("cota"))
            self.assertTrue(canvas.find_withtag("escala"))
            # los aleros de v2.4.0 siguen ahí
            self.assertTrue(canvas.find_withtag("alero"))
        finally:
            dialog.destroy()

    def test_cambio_a_elevacion_redibuja(self):
        dialog = self._open()
        try:
            dialog._bld_widgets["usage"].set("Vivienda")
            dialog._bld_load_usage()
            dialog._bld_generate_variants()
            self.window.update()
            canvas = dialog._bld_widgets["variant_canvas"]
            dialog._bld_widgets["view"].set("Elevación")
            dialog._bld_widgets["view"].event_generate(
                "<<ComboboxSelected>>")
            self.window.update()
            self.assertTrue(canvas.find_withtag("titulo"))
            textos = [canvas.itemcget(item, "text")
                      for item in canvas.find_withtag("titulo")]
            self.assertTrue(any("ELEVACIÓN" in t for t in textos))
        finally:
            dialog.destroy()

    def test_cambio_a_corte_y_detalles(self):
        dialog = self._open()
        try:
            dialog._bld_widgets["usage"].set("Vivienda")
            dialog._bld_load_usage()
            dialog._bld_generate_variants()
            self.window.update()
            widgets = dialog._bld_widgets
            widgets["view"].set("Corte")
            widgets["view"].event_generate("<<ComboboxSelected>>")
            self.window.update()
            self.assertEqual(widgets["view_aux"].cget("values"),
                             ("Transversal", "Longitudinal"))
            canvas = dialog._bld_widgets["variant_canvas"]
            self.assertTrue(canvas.find_withtag("cimentacion"))
            widgets["view"].set("Detalles")
            widgets["view"].event_generate("<<ComboboxSelected>>")
            self.window.update()
            textos = [canvas.itemcget(item, "text")
                      for item in canvas.find_withtag("titulo")]
            self.assertTrue(any("DET-" in t for t in textos))
        finally:
            dialog.destroy()


if __name__ == "__main__":
    unittest.main()
