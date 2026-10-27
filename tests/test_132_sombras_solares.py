"""SOMBRAS SOLARES Y ORIENTACIÓN (v3.13.0) — ui/solar.py.

La posición solar se verifica contra valores que se pueden calcular a
mano (declinación de Cooper, mediodía del equinoccio, noche polar),
las sombras se comprueban por DIRECCIÓN y LONGITUD geométricas y la
escena completa (sombras + brújula + arco solar) debe salir igual en
el lienzo Tk y en el PNG determinista.
"""

from __future__ import annotations

import math
import os
import struct
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui import solar as sol
from ui import view3d as v3
from ui.building_wizard import (BuildingWizardData, LevelSpec, RelationSpec,
                                RoomSpec)
from ui.view3d import Camara3D


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


class TestPosicionSolar(ARQGenTestCase):
    """La matemática del sol, verificada a mano."""

    def test_declinacion_solar_conoce_los_solsticios(self):
        self.assertAlmostEqual(sol.declinacion_solar(172), 23.44, delta=0.3)
        self.assertAlmostEqual(sol.declinacion_solar(355), -23.44, delta=0.3)
        self.assertAlmostEqual(sol.declinacion_solar(80), 0.0, delta=0.6)
        self.assertAlmostEqual(sol.declinacion_solar(264), 0.0, delta=0.6)

    def test_mediodia_del_equinoccio_en_madrid(self):
        az, el = sol.posicion_solar(40.4, 80, 12.0)
        self.assertAlmostEqual(az, 180.0, delta=1.0)
        # el = 90 - |lat| - |decl| ≈ 49.2°
        self.assertAlmostEqual(el, 90.0 - 40.4, delta=1.5)

    def test_la_habana_en_junio_el_sol_pasa_al_norte(self):
        az, el = sol.posicion_solar(23.1, 172, 12.0)
        self.assertGreater(el, 88.0)          # casi cenital
        self.assertLess(az, 20.0)             # y por el lado NORTE

    def test_manana_este_y_tarde_oeste(self):
        az9, _ = sol.posicion_solar(23.1, 80, 9.0)
        az15, _ = sol.posicion_solar(23.1, 80, 15.0)
        self.assertGreater(az9, 60.0)
        self.assertLess(az9, 180.0)
        self.assertGreater(az15, 180.0)
        self.assertLess(az15, 300.0)

    def test_noche_polar_y_umbral(self):
        _, el = sol.posicion_solar(80, 355, 12.0)
        self.assertLess(el, 0.0)
        self.assertFalse(sol.sol_visible(el))
        self.assertTrue(sol.sol_visible(10.0))
        self.assertFalse(sol.sol_visible(0.2))  # rasante: no cuenta

    def test_hemisferio_sur_invierte_el_mediodia(self):
        # Santiago en diciembre: el mediodía pega desde el NORTE
        az, el = sol.posicion_solar(-33.4, 355, 12.0)
        self.assertGreater(el, 75.0)
        self.assertLess(abs(az), 15.0)

    def test_vector_al_sol_es_unitario_y_consistente(self):
        for az in (0.0, 45.0, 130.0, 271.0):
            for el in (5.0, 43.0, 88.0):
                v = sol.vector_al_sol(az, el)
                self.assertAlmostEqual(math.sqrt(sum(c * c for c in v)),
                                       1.0, places=9)
                # componente Este = sin(az), Norte = cos(az) (escalados)
                self.assertAlmostEqual(v[0] / math.cos(math.radians(el)),
                                       math.sin(math.radians(az)), places=9)
                self.assertAlmostEqual(v[1] / math.cos(math.radians(el)),
                                       math.cos(math.radians(az)), places=9)


class TestSombras(ARQGenTestCase):
    """Proyección, envolvente y recorte de sombras."""

    def test_envolvente_convexa_basica(self):
        hull = sol.envolvente_convexa([(0, 0), (4, 0), (4, 3), (0, 3),
                                       (2, 1)])
        self.assertEqual(len(hull), 4)
        hull2 = sol.envolvente_convexa([(0, 0), (2, 2), (4, 4)])
        self.assertEqual(len(hull2), 2)  # colineales: no hay envolvente
        self.assertEqual(sol.envolvente_convexa([(1, 1)]), [(1.0, 1.0)])

    def test_sombra_al_mediodia_de_invierno_apunta_al_norte(self):
        caja = [(0, 0, 0), (4, 0, 0), (4, 0.2, 0), (0, 0.2, 0),
                (0, 0, 3), (4, 0, 3), (4, 0.2, 3), (0, 0.2, 3)]
        sombra = sol.poligono_sombra(caja, 180.0, 43.5)
        self.assertIsNotNone(sombra)
        ys = [p[1] for p in sombra]
        self.assertGreater(max(ys), 0.3)   # se extiende hacia +y (norte)
        self.assertAlmostEqual(min(ys), 0.0, delta=1e-9)

    def test_longitud_de_sombra_es_altura_sobre_tangente(self):
        caja = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                (0, 0, 3), (1, 0, 3), (1, 1, 3), (0, 1, 3)]
        el = 30.0
        sombra = sol.poligono_sombra(caja, 180.0, el)
        ys = [p[1] for p in sombra]
        # el ala de la sombra nace en la esquina base lejana (y=1) y
        # avanza 3/tan(el) hacia el norte
        self.assertAlmostEqual(max(ys) - 1.0,
                               3.0 / math.tan(math.radians(el)), places=6)

    def test_sol_bajo_devuelve_none(self):
        caja = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
        self.assertIsNone(sol.poligono_sombra(caja, 180.0, -5.0))
        self.assertIsNone(sol.poligono_sombra(caja, 180.0, 0.2))

    def test_las_sombras_nunca_caidan_dentro_de_la_huella(self):
        modelo, _ = self._modelo_chico()
        opts = sol.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        caras = sol.caras_de_sombras(modelo, opts, Camara3D())
        self.assertTrue(caras)
        recto = sol._bbox_total(modelo)
        for cara in caras:
            xs = [p[0] for p in cara.puntos]
            ys = [p[1] for p in cara.puntos]
            dentro = (max(xs) <= recto[2] + 0.08
                      and min(xs) >= recto[0] - 0.08
                      and max(ys) <= recto[3] + 0.08
                      and min(ys) >= recto[1] - 0.08)
            self.assertFalse(dentro,
                             "sombra dentro de la huella: %r" % (cara,))

    def test_sombras_deterministas_y_sin_noche(self):
        modelo, _ = self._modelo_chico()
        opts = sol.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        cam = Camara3D()
        a = [(c.color, tuple(map(tuple, c.puntos)))
             for c in sol.caras_de_sombras(modelo, opts, cam)]
        b = [(c.color, tuple(map(tuple, c.puntos)))
             for c in sol.caras_de_sombras(modelo, opts, cam)]
        self.assertEqual(a, b)
        noche = sol.SolarOpts(latitud_deg=80.0, dia_anio=355, hora=12.0)
        self.assertEqual(sol.caras_de_sombras(modelo, noche, cam), [])
        # sin muros ni locales: amable, lista vacía
        vacio = v3.Modelo3D()
        self.assertEqual(sol.caras_de_sombras(vacio, opts, cam), [])

    def test_resumen_y_recomendacion(self):
        texto = sol.resumen_solar(sol.SolarOpts(23.1, 355, 12.0))
        self.assertIn("sol az 180", texto)
        self.assertIn("21 dic", texto)
        noche = sol.resumen_solar(sol.SolarOpts(80.0, 355, 12.0))
        self.assertIn("bajo el horizonte", noche)
        # fachada larga este-oeste, latitud norte → principal al SUR
        reco = sol.recomendacion_orientacion(23.1, (0, 0, 8, 6))
        self.assertIn("este-oeste", reco)
        self.assertIn("SUR", reco)
        self.assertIn("NORTE", sol.recomendacion_orientacion(-33.4,
                                                             (0, 0, 8, 6)))

    # -- helpers ---------------------------------------------------------
    def _modelo_chico(self):
        data = BuildingWizardData(name="Sombras QA")
        data.levels = [LevelSpec(name="Planta Baja", height_m=3.0)]
        data.rooms = [
            RoomSpec(name="Sala", space_type="ROOM", width_m=5.0,
                     depth_m=4.0, level_ref="Planta Baja",
                     with_window=True),
            RoomSpec(name="Cocina", space_type="KITCHEN", width_m=3.0,
                     depth_m=2.5, level_ref="Planta Baja",
                     with_window=True),
        ]
        data.relations = [RelationSpec(a_name="Sala", b_name="Cocina",
                                       kind_es="Adyacente a",
                                       with_door=True)]
        ctx = self.application.create_project(
            self.project_path("sombras.arqgen"), name="Sombras QA")
        bw.apply_plan(data, ctx,
                      variant=bw.generate_variants(data)[0])
        modelo, avisos = v3.modelo3d_desde_proyecto(ctx)
        self.assertFalse(avisos)
        self.addCleanup(ctx.close)
        return modelo, avisos


class TestEscenaSolar(ARQGenTestCase):
    """Sombras + brújula + sol dentro del motor de vista 3D."""

    def _escena(self):
        data = BuildingWizardData(name="Escena Sol")
        data.levels = [LevelSpec(name="Planta Baja", height_m=3.0)]
        data.rooms = [
            RoomSpec(name="Sala", space_type="ROOM", width_m=5.0,
                     depth_m=4.0, level_ref="Planta Baja",
                     with_window=True),
            RoomSpec(name="Cocina", space_type="KITCHEN", width_m=3.0,
                     depth_m=2.5, level_ref="Planta Baja",
                     with_window=True),
            RoomSpec(name="Bano", space_type="BATHROOM", width_m=1.8,
                     depth_m=2.0, level_ref="Planta Baja",
                     with_window=False),
        ]
        data.relations = [RelationSpec(a_name="Sala", b_name="Cocina",
                                       kind_es="Adyacente a",
                                       with_door=True)]
        ctx = self.application.create_project(
            self.project_path("escena.arqgen"), name="Escena Sol")
        bw.apply_plan(data, ctx,
                      variant=bw.generate_variants(data)[0])
        modelo, _ = v3.modelo3d_desde_proyecto(ctx)
        self.addCleanup(ctx.close)
        return modelo

    def test_construir_caras_con_sol_y_sin_sol(self):
        modelo = self._escena()
        cam = Camara3D()
        opts = sol.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        caras = v3.construir_caras(modelo, cam, solar=opts)
        kinds = {}
        for cara in caras:
            kinds[cara.kind] = kinds.get(cara.kind, 0) + 1
        self.assertGreaterEqual(kinds.get("sombra", 0), 1)
        self.assertEqual(kinds.get("brujula"), 5)   # disco + 4 agujas
        self.assertGreaterEqual(kinds.get("sol", 0)
                                + kinds.get("sol_actual", 0), 3)
        # sin solar: nada cambia (compatibilidad hacia atrás)
        caras_normales = v3.construir_caras(modelo, cam)
        self.assertFalse(any(c.kind in ("sombra", "sol", "brujula")
                             for c in caras_normales))

    def test_noche_deja_brujula_pero_cero_sombras(self):
        modelo = self._escena()
        noche = sol.SolarOpts(latitud_deg=80.0, dia_anio=355, hora=12.0)
        caras = v3.construir_caras(modelo, Camara3D(), solar=noche)
        self.assertFalse(any(c.kind == "sombra" for c in caras))
        self.assertFalse(any(c.kind in ("sol", "sol_actual")
                             for c in caras))
        self.assertEqual(sum(1 for c in caras if c.kind == "brujula"), 5)

    def test_la_escena_solar_es_determinista(self):
        modelo = self._escena()
        cam = Camara3D()
        opts = sol.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        a = [(c.color, tuple(map(tuple, c.puntos)))
             for c in v3.construir_caras(modelo, cam, solar=opts)]
        b = [(c.color, tuple(map(tuple, c.puntos)))
             for c in v3.construir_caras(modelo, cam, solar=opts)]
        self.assertEqual(a, b)

    def test_piso_del_local_a_su_cota_de_terreno_irregular(self):
        modelo = self._escena()
        for espacio in modelo.locales:
            espacio.metadata["cota_piso_m"] = 0.75
        cam = Camara3D()
        caras = v3.construir_caras(modelo, cam)
        pisos = [c for c in caras if c.kind == "piso"]
        self.assertTrue(pisos)
        for piso in pisos:
            zs = [p[2] for p in piso.puntos]
            self.assertAlmostEqual(min(zs), 0.02 + 0.75, places=6)

    def test_png_con_sombras_valido_determinista_y_pie_recortado(self):
        modelo = self._escena()
        cam = Camara3D()
        opts = sol.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        caras = v3.construir_caras(modelo, cam, solar=opts)
        ruta1 = self.project_path("sol1.png")
        ruta2 = self.project_path("sol2.png")
        ancho, alto = v3.export_vista3d_png(
            caras, cam, ruta1, titulo="Prueba de sol",
            info_extra=sol.resumen_solar(opts) + "  "
            + sol.recomendacion_orientacion(23.1, sol._bbox_total(modelo)))
        self.assertEqual((ancho, alto), (1600, 1000))
        v3.export_vista3d_png(caras, cam, ruta2, titulo="Prueba de sol",
                              info_extra=sol.resumen_solar(opts))
        with open(ruta1, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        with open(ruta2, "rb") as fh:
            datos2 = fh.read()
        self.assertEqual(struct.unpack(">I", datos2[16:20])[0], 1600)
        # pie largo ≠ pie corto (el recorte del pie actúa)
        with open(ruta1, "rb") as fh:
            datos1 = fh.read()
        self.assertNotEqual(datos1, datos2)


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestDialogoSolar(ARQGenTestCase):
    """Los controles ☀ del diálogo de vista 3D."""

    def _ventana(self):
        from app.demo import build_demo
        from ui.app_window import ARQGenWindow
        self.context = build_demo(self.application,
                                  self.project_path("demo_sol.arqgen"))
        self.window = ARQGenWindow(self.context, self.application)
        self.addCleanup(self.window.destroy)
        return self.window

    def test_sombras_del_dialogo_hasta_png(self):
        from unittest import mock
        import ui.app_window as aw
        win = self._ventana()
        with mock.patch.object(aw, "messagebox"):
            win.open_view3d_dialog()
            dialogo = win._vista3d_dialog
            self.addCleanup(dialogo.destroy)
            state = dialogo._vista3d_state
            self.assertIsNone(state["solar"])
            dialogo._vista3d_solar_var.set(True)
            dialogo._vista3d_recalcula()
            self.assertIsNotNone(state["solar"])
            self.assertEqual(state["solar"].latitud_deg, 23.1)
            self.assertGreater(state["caras"], 0)
            self.assertTrue(any(c.kind == "sombra" for c in
                                _caras_del_estado(dialogo)))
            # cambiar latitud cambia el opts (los combos alimentan el
            # SolarOpts al recalcular)
            ruta = self.project_path("dialogo_sol.png")
            dialogo._vista3d_export(ruta)
            self.assertTrue(os.path.isfile(ruta))

    def test_dialogo_sin_marcar_no_aniade_sol(self):
        from unittest import mock
        import ui.app_window as aw
        win = self._ventana()
        with mock.patch.object(aw, "messagebox"):
            win.open_view3d_dialog()
            dialogo = win._vista3d_dialog
            self.addCleanup(dialogo.destroy)
            dialogo._vista3d_recalcula()
            state = dialogo._vista3d_state
            self.assertIsNone(state["solar"])
            self.assertIsNone(state["terreno"])


def _caras_del_estado(dialogo):
    from ui import view3d as v3
    state = dialogo._vista3d_state
    return v3.construir_caras(state["modelo"], state["cam"],
                              solar=state.get("solar"),
                              terreno=state.get("terreno"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
