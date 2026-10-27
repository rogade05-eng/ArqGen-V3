"""Diseño orgánico (v3.2.0): distribución articulada, muros curvos,
diagonales y pasillos que respiran.

La capa orgánica (ui.building_wizard + core.geometry.organic) transforma
el trazado ortogonal: fondos escalonados, chaflanes a 45° o radones en
las esquinas de la envolvente, fachada en arco y pasillo serpenteante.
Reglas de seguridad verificadas aquí: nunca se reduce el área de un
local, nunca se toca una pared compartida, los vanos conservan su muro
(por identidad) y toda la geometría se materializa en muros rectos.
"""

from __future__ import annotations

import math
import os
import unittest

from core.geometry.organic import (arc_polyline, chamfer_points,
                                   fillet_points, polyline_length,
                                   s_curve_polyline)
from ui import building_wizard as bwiz
from tests.base import ARQGenTestCase


def _data(dist: str = "organica", seed: int = 7, curv: float = 1.5,
          corridor: float = 1.2) -> bwiz.BuildingWizardData:
    data = bwiz.BuildingWizardData()
    data.name = "Casa de prueba"
    bwiz.apply_usage_program(data)
    data.distribucion = dist
    data.semilla = seed
    data.curvatura_m = curv
    data.corridor_width_m = corridor
    return data


def _diagonals(layout: bwiz.LevelLayout) -> int:
    return sum(1 for w in layout.walls
               if abs(w["start"][0] - w["end"][0]) > 1e-6
               and abs(w["start"][1] - w["end"][1]) > 1e-6)


def _curved(layout: bwiz.LevelLayout) -> int:
    return sum(1 for w in layout.walls if w.get("curve"))


class TestGeometriaOrganica(unittest.TestCase):
    """Helpers puros de core.geometry.organic."""

    def test_arco_extremos_y_flecha(self):
        pts = arc_polyline((0.0, 0.0), (10.0, 0.0), 1.5, 12)
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertEqual(pts[-1], (10.0, 0.0))
        mid = pts[len(pts) // 2]
        self.assertAlmostEqual(mid[1], 1.5, delta=0.06)
        self.assertGreater(polyline_length(pts), 10.0)  # arco > cuerda

    def test_arco_signo_cambia_de_lado(self):
        up = arc_polyline((0.0, 0.0), (8.0, 0.0), 1.0, 10)
        down = arc_polyline((0.0, 0.0), (8.0, 0.0), -1.0, 10)
        self.assertGreater(up[len(up) // 2][1], 0.0)
        self.assertLess(down[len(down) // 2][1], 0.0)

    def test_s_extremos_libres_y_centro(self):
        pts = s_curve_polyline((0.0, 0.0), (12.0, 0.0), 0.8, 12)
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertEqual(pts[-1], (12.0, 0.0))
        self.assertAlmostEqual(pts[0][1], 0.0)          # sin salto
        self.assertAlmostEqual(pts[len(pts) // 2][1], 0.8, delta=0.03)

    def test_chaflan_45(self):
        a, b = chamfer_points((0.0, 0.0), (5.0, 0.0), (0.0, 5.0), 1.2)
        self.assertAlmostEqual(a[0], 1.2)
        self.assertAlmostEqual(b[1], 1.2)
        self.assertAlmostEqual(math.hypot(a[0], b[1]), 1.2 * math.sqrt(2),
                               delta=1e-9)

    def test_radon_no_toca_la_esquina(self):
        pts = fillet_points((0.0, 0.0), (6.0, 0.0), (0.0, 6.0), 1.5, 8)
        self.assertAlmostEqual(pts[0][0], 1.5)  # tangente en la arista
        self.assertAlmostEqual(pts[0][1], 0.0)
        self.assertAlmostEqual(pts[-1][0], 0.0)
        self.assertAlmostEqual(pts[-1][1], 1.5)
        interior = pts[1:-1]
        self.assertTrue(all(math.hypot(x, y) > 0.4 for x, y in interior),
                        "el arco debe alejarse de la esquina viva")


class TestValidacionYDatos(ARQGenTestCase):
    def test_campos_en_building_field_names(self):
        names = bwiz.building_field_names()
        for field in ("distribucion", "curvatura_m", "semilla"):
            self.assertIn(field, names)

    def test_data_from_values_distribucion(self):
        data = bwiz.BuildingWizardData()
        bwiz.data_from_values(0, {"distribucion": "Orgánica (curvas, "
                                                  "radones y pasillo "
                                                  "serpenteante)",
                                  "curvatura_m": "2,0",
                                  "semilla": "11"}, data)
        self.assertEqual(data.distribucion, "organica")
        self.assertAlmostEqual(data.curvatura_m, 2.0)
        self.assertEqual(data.semilla, 11)

    def test_data_from_values_tolerante(self):
        data = bwiz.BuildingWizardData()
        bwiz.data_from_values(0, {"curvatura_m": "no es número",
                                  "semilla": "-x"}, data)
        self.assertAlmostEqual(data.curvatura_m, 1.5)  # sin cambios
        self.assertEqual(data.semilla, 0)

    def test_validacion_rechaza_fuera_de_rango(self):
        data = _data()
        data.curvatura_m = 9.0
        errors = bwiz.validate_step(0, data)
        self.assertTrue(any("curvatura" in e.lower() for e in errors))
        data = _data()
        data.semilla = -3
        errors = bwiz.validate_step(0, data)
        self.assertTrue(any("semilla" in e.lower() for e in errors))

    def test_codigos_y_etiquetas_round_trip(self):
        for code in bwiz.DISTRIBUCION_CODES:
            self.assertEqual(bwiz.distribution_code(
                bwiz.distribution_label(code)), code)
        self.assertEqual(bwiz.distribution_code("algo raro"), "ortogonal")


class TestArticularFondos(ARQGenTestCase):
    """Distribución articulada/orgánica: fondos escalonados."""

    def test_fondos_escalonados_solo_crecen(self):
        base = _data("ortogonal")
        layouts_base, _ = bwiz.build_layout(base)
        specs = {r.name: r.depth_m for r in base.rooms}
        org = _data("organica", seed=7)
        layouts_org, _ = bwiz.build_layout(org)
        escalonado = False
        for layout in layouts_org:
            for pr in layout.rooms:
                ref = specs.get(pr.name)
                if ref is None or pr.space_type in ("STAIR", "CORE"):
                    continue
                if ref < 2.4:
                    continue
                self.assertGreaterEqual(pr.d, ref - 1e-9,
                                        "el fondo nunca se reduce")
                if pr.d > ref + 1e-6:
                    escalonado = True
        self.assertTrue(escalonado, "con semilla 7 debe escalonar algo")

    def test_determinismo_por_semilla(self):
        def trazar(seed):
            data = _data("organica", seed=seed)
            layouts, _ = bwiz.build_layout(data)
            bwiz.apply_distribucion(data, layouts)
            return [(w["start"], w["end"]) for l in layouts
                    for w in l.walls]
        self.assertEqual(trazar(7), trazar(7))
        self.assertNotEqual(trazar(7), trazar(8))


class TestOrganizarEnvolvente(ARQGenTestCase):
    """Curvas y chaflanes de la envolvente (muros, vanos, reglas)."""

    def test_organica_crea_curvas_y_arco(self):
        data = _data("organica", corridor=1.8)
        variants = bwiz.generate_variants(data)
        v = next(x for x in variants
                 if x.scheme == "doble_crujia" and not x.mirror)
        layout = v.layouts[0]
        self.assertGreater(_curved(layout), 0, "debe haber tramos curvos")
        self.assertTrue(any("Distribución orgánica" in a
                            for a in v.advisories))

    def test_articulada_crea_chaflanes(self):
        data = _data("articulada")
        variants = bwiz.generate_variants(data)
        v = next(x for x in variants
                 if x.scheme == "en_L" and not x.mirror)
        self.assertGreater(_diagonals(v.layouts[0]), 0,
                           "la L articulada debe tener chaflanes a 45°")

    def test_ortogonal_no_hace_nada(self):
        data = _data("ortogonal")
        variants = bwiz.generate_variants(data)
        for v in variants:
            self.assertEqual(_curved(v.layouts[0]), 0)
            self.assertEqual(_diagonals(v.layouts[0]), 0)
            self.assertFalse(any("Distribución" in a for a in v.advisories))

    def test_paredes_compartidas_intactas(self):
        """Ninguna pared entre dos locales recibe gesto orgánico."""
        data = _data("organica", corridor=1.8)
        variants = bwiz.generate_variants(data)
        for v in variants:
            for layout in v.layouts:
                rooms = {pr.name: pr for pr in layout.all_rooms}
                for wall in layout.walls:
                    if not wall.get("curve") \
                            and not _diagonal_wall(wall):
                        continue  # muros rectos sin gesto: no auditar
                    sides = set()
                    for name in wall.get("sources", []):
                        room = rooms.get(name)
                        if room is None:
                            continue
                        (x1, y1), (x2, y2) = wall["start"], wall["end"]
                        if abs(y1 - y2) <= 1e-6:
                            if abs(room.y - y1) <= 1e-6:
                                sides.add(+1)
                            if abs(room.y + room.d - y1) <= 1e-6:
                                sides.add(-1)
                        else:
                            if abs(room.x - x1) <= 1e-6:
                                sides.add(+1)
                            if abs(room.x + room.w - x1) <= 1e-6:
                                sides.add(-1)
                    if sides == {+1, -1}:
                        self.fail("pared compartida tocada: " + str(wall))

    def test_vanos_conservan_su_muro(self):
        """Cada vano cabe en el muro que le toca tras el gesto."""
        data = _data("organica", corridor=1.8, curv=2.0)
        variants = bwiz.generate_variants(data)
        for v in variants[:6]:
            for layout in v.layouts:
                for op in list(layout.doors) + list(layout.windows):
                    self.assertTrue(0 <= op.wall_index < len(layout.walls))
                    wall = layout.walls[op.wall_index]
                    self.assertLessEqual(
                        op.offset_m + op.width_m, wall["length"] + 1e-6,
                        f"{op.note}: {op.offset_m}+{op.width_m} > "
                        f"{wall['length']}")

    def test_pasillo_conserva_ancho_de_galibo(self):
        """La S del pasillo nunca baja el galibo por debajo de 1,20 m."""
        data = _data("organica", corridor=2.0, curv=1.5)
        variants = bwiz.generate_variants(data)
        v = next(x for x in variants
                 if x.scheme == "lineal" and not x.mirror)
        layout = v.layouts[0]
        corridor = next(pr for pr in layout.all_rooms if pr.is_corridor)
        cap = (data.corridor_width_m - 1.2) * 0.5
        piezas_s = [w for w in layout.walls
                    if w.get("sources") == [corridor.name] and w.get("s")]
        self.assertTrue(piezas_s, "el pasillo serpenteante existe")
        for wall in piezas_s:
            for px, py in (wall["start"], wall["end"]):
                # la S entra al pasillo desde su muro libre (y=corridor.y)
                deviation = py - corridor.y
                self.assertLessEqual(deviation, cap + 1e-9,
                                     "la S invade más del galibo seguro")
                self.assertGreaterEqual(deviation, -1e-9)

    def test_idempotencia(self):
        data = _data("organica")
        layouts, _ = bwiz.build_layout(data)
        antes = len(layouts[0].walls)
        notas1 = bwiz.apply_distribucion(data, layouts)
        despues1 = len(layouts[0].walls)
        notas2 = bwiz.apply_distribucion(data, layouts)
        self.assertEqual(len(layouts[0].walls), despues1)
        self.assertNotEqual(len(notas1), 0) if antes != despues1 else None
        self.assertEqual(notas2, [], "la segunda pasada no hace nada")


class TestPlanYProyecto(ARQGenTestCase):
    def test_apply_plan_organico_crea_todo(self):
        from app.demo import build_demo
        from services.context import ApplicationContext
        data = _data("organica", corridor=1.8)
        variants = bwiz.generate_variants(data)
        v = next(x for x in variants
                 if x.scheme == "doble_crujia" and not x.mirror)
        app = ApplicationContext()
        path = os.path.join(self.tmp, "organico.arqgen")
        ctx = build_demo(app, path)
        summary = bwiz.apply_plan(data, ctx, variant=v)
        ctx.close()
        total_walls = sum(len(l.walls) for l in v.layouts)
        self.assertEqual(summary["walls"], total_walls)
        self.assertGreater(summary["doors"], 0)
        self.assertGreater(summary["windows"], 0)
        self.assertGreater(summary["spaces"], 0)

    def test_step_summary_menciona_distribucion(self):
        data = _data("organica")
        text = bwiz.step_summary(data)
        self.assertIn("Distribución interior", text)
        self.assertIn("semilla 7", text)
        base = _data("ortogonal")
        self.assertNotIn("Distribución interior", bwiz.step_summary(base))


def _diagonal_wall(wall: dict) -> bool:
    (x1, y1), (x2, y2) = wall["start"], wall["end"]
    return (abs(x1 - x2) > 1e-6 and abs(y1 - y2) > 1e-6)


if __name__ == "__main__":
    unittest.main()
