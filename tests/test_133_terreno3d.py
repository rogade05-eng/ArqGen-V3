"""TERRENO 3D (v3.13.0) — ui/terreno3d.py.

La malla del solar debe ser DETERMINISTA (misma semilla, misma tierra),
la pendiente debe cumplir la matemática exacta (10 % sobre 24 m = 2.40 m),
el pad bajo la huella queda nivelado a −1 cm y los quads bajo el
edificio se ceden a la plataforma del nivel 0.
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui import terreno3d as ter
from ui import view3d as v3
from ui.building_wizard import (BuildingWizardData, LevelSpec, RelationSpec,
                                RoomSpec)
from ui.view3d import Camara3D

RECTO = (0.0, 0.0, 8.0, 6.0)


def _display_ok() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001 - headless
        return False


class TestAlturaTerreno(ARQGenTestCase):

    def test_plano_sin_nada_pad_nivelado(self):
        opts = ter.TerrenoOpts()
        self.assertAlmostEqual(ter.altura_en(4, 3, opts, RECTO), -0.01,
                               places=12)
        # fuera de la huella el terreno natural vale 0
        self.assertAlmostEqual(ter.altura_en(20, 3, opts, RECTO), 0.0,
                               places=12)

    def test_pendiente_matematica_exacta(self):
        # 10 % bajando al ESTE: 24 m de recorrido → 2.40 m de caída
        opts = ter.TerrenoOpts(pendiente_pct=10.0, direccion_deg=90.0)
        oeste = ter.altura_en(-8, 3, opts, RECTO)
        este = ter.altura_en(16, 3, opts, RECTO)
        self.assertAlmostEqual(oeste - este, 2.40, places=9)
        self.assertGreater(oeste, este)

    def test_direcciones_cardinales(self):
        # bajar hacia el SUR: al sur más bajo, al norte más alto
        opts = ter.TerrenoOpts(pendiente_pct=10.0, direccion_deg=180.0)
        self.assertGreater(ter.altura_en(4, 12, opts, RECTO),
                           ter.altura_en(4, -6, opts, RECTO))
        # bajar hacia el NORTE: al revés
        opts_n = ter.TerrenoOpts(pendiente_pct=10.0, direccion_deg=0.0)
        self.assertLess(ter.altura_en(4, 12, opts_n, RECTO),
                        ter.altura_en(4, -6, opts_n, RECTO))

    def test_el_pad_nivelado_resiste_pendiente_y_relieve(self):
        for opts in (ter.TerrenoOpts(pendiente_pct=25.0, direccion_deg=180.0),
                     ter.TerrenoOpts(relieve_m=1.0, semilla=3),
                     ter.TerrenoOpts(pendiente_pct=15.0, direccion_deg=45.0,
                                     relieve_m=0.8, semilla=9)):
            self.assertAlmostEqual(ter.altura_en(4, 3, opts, RECTO), -0.01,
                                   places=12)

    def test_relieve_acotado_y_determinista(self):
        opts = ter.TerrenoOpts(relieve_m=0.5, semilla=7)
        self.assertAlmostEqual(ter.altura_en(12, 10, opts, RECTO),
                               ter.altura_en(12, 10, opts, RECTO),
                               places=15)
        _malla, hmin, hmax = ter.malla_terreno(RECTO, opts)
        self.assertGreater(hmax - hmin, 0.0)
        self.assertLessEqual(hmax - hmin, 1.05)  # 2× relieve como tope

    def test_otra_semilla_otra_tierra(self):
        a = ter.altura_en(12, 10, ter.TerrenoOpts(relieve_m=0.8, semilla=99),
                          RECTO)
        b = ter.altura_en(12, 10, ter.TerrenoOpts(relieve_m=0.8, semilla=98),
                          RECTO)
        self.assertNotAlmostEqual(a, b, places=3)


class TestMallaYCaras(ARQGenTestCase):

    def test_malla_dimensiones_y_rango(self):
        malla, hmin, hmax = ter.malla_terreno(
            RECTO, ter.TerrenoOpts(resolucion=20))
        self.assertEqual(len(malla), 21)          # filas (n+1)
        self.assertEqual(len(malla[0]), 21)       # columnas
        self.assertLessEqual(hmin, hmax)

    def test_caras_deterministas_con_hueco_bajo_la_huella(self):
        cam = Camara3D()
        opts = ter.TerrenoOpts(pendiente_pct=5.0, direccion_deg=0.0)
        caras = ter.caras_de_terreno(RECTO, opts, cam)
        de_nuevo = ter.caras_de_terreno(RECTO, opts, cam)
        llaves = [(c.color, tuple(map(tuple, c.puntos))) for c in caras]
        self.assertEqual(llaves, [(c.color, tuple(map(tuple, c.puntos)))
                                  for c in de_nuevo])
        self.assertTrue(all(c.kind == "terreno" for c in caras))
        # se omiten los quads íntegramente dentro de la huella
        total = 26 * 26
        self.assertGreater(len(caras), total // 2)
        self.assertLess(len(caras), total)
        for cara in caras:
            dentro = all(RECTO[0] < p[0] < RECTO[2]
                         and RECTO[1] < p[1] < RECTO[3]
                         for p in cara.puntos)
            self.assertFalse(dentro, "quad bajo la huella no omitido")

    def test_rampa_de_color_varia_con_la_pendiente(self):
        cam = Camara3D()
        plano = ter.caras_de_terreno(RECTO, ter.TerrenoOpts(), cam)
        ladera = ter.caras_de_terreno(
            RECTO, ter.TerrenoOpts(pendiente_pct=15.0, direccion_deg=90.0),
            cam)
        # en llano solo quedan los matices de la transición del pad; en
        # ladera la rampa despliega muchos más tonos
        self.assertGreater(len({c.color for c in ladera}),
                           len({c.color for c in plano}) * 2)


class TestEscenaTerreno(ARQGenTestCase):

    def _modelo(self):
        data = BuildingWizardData(name="Terreno QA")
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
            self.project_path("terreno.arqgen"), name="Terreno QA")
        bw.apply_plan(data, ctx,
                      variant=bw.generate_variants(data)[0])
        modelo, _ = v3.modelo3d_desde_proyecto(ctx)
        self.addCleanup(ctx.close)
        return modelo

    def test_construir_caras_con_terreno(self):
        modelo = self._modelo()
        cam = Camara3D()
        opts = ter.TerrenoOpts(pendiente_pct=5.0, direccion_deg=180.0,
                               relieve_m=0.3)
        caras = v3.construir_caras(modelo, cam, terreno=opts)
        terrenos = [c for c in caras if c.kind == "terreno"]
        self.assertGreater(len(terrenos), 300)
        # compatibilidad hacia atrás: sin terreno no aparece ninguno
        normales = v3.construir_caras(modelo, cam)
        self.assertFalse(any(c.kind == "terreno" for c in normales))

    def test_sombras_arrugan_sobre_el_terreno(self):
        from ui import solar as sol
        modelo = self._modelo()
        cam = Camara3D()
        sopts = sol.SolarOpts(latitud_deg=23.1, dia_anio=355, hora=12.0)
        topts = ter.TerrenoOpts(pendiente_pct=8.0, direccion_deg=90.0)
        caras = v3.construir_caras(modelo, cam, solar=sopts, terreno=topts)
        sombras = [c for c in caras if c.kind == "sombra"]
        self.assertTrue(sombras)
        for sombra in sombras:
            # la sombra reposa SOBRE la altura del terreno (+4 mm), no
            # flota a cero
            for (x, y, z) in sombra.puntos:
                esperado = ter.altura_en(x, y, topts,
                                         sol._bbox_total(modelo)) + 0.004
                self.assertAlmostEqual(z, esperado, places=9)

    def test_png_con_terreno_valido(self):
        modelo = self._modelo()
        cam = Camara3D()
        caras = v3.construir_caras(
            modelo, cam,
            terreno=ter.TerrenoOpts(pendiente_pct=5.0, direccion_deg=0.0,
                                    relieve_m=0.2))
        ruta = self.project_path("terreno.png")
        v3.export_vista3d_png(caras, cam, ruta, titulo="Terreno QA",
                              info_extra="terreno 5%")
        with open(ruta, "rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")


@unittest.skipUnless(_display_ok(), "requiere display Tk (Xvfb :99)")
class TestDialogoTerreno(ARQGenTestCase):

    def _ventana(self):
        from app.demo import build_demo
        from ui.app_window import ARQGenWindow
        self.context = build_demo(self.application,
                                  self.project_path("demo_ter.arqgen"))
        self.window = ARQGenWindow(self.context, self.application)
        self.addCleanup(self.window.destroy)
        return self.window

    def test_terreno_del_dialogo(self):
        from unittest import mock
        import ui.app_window as aw
        win = self._ventana()
        with mock.patch.object(aw, "messagebox"):
            win.open_view3d_dialog()
            dialogo = win._vista3d_dialog
            self.addCleanup(dialogo.destroy)
            state = dialogo._vista3d_state
            dialogo._vista3d_terreno_var.set(True)
            dialogo._vista3d_recalcula()
            self.assertIsNotNone(state["terreno"])
            self.assertGreater(state["caras"], 400)
            ruta = self.project_path("dialogo_terreno.png")
            dialogo._vista3d_export(ruta)
            self.assertTrue(os.path.isfile(ruta))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
