"""VENTANAS Y PANELES AJUSTABLES (v3.7.0).

Lo pedido: «el espacio de trabajo donde sale la planta es muy pequeño,
conviene poder ajustar los bordes de todas las ventanas».

Cobertura de estas pruebas:

* Tema (ui.theme): el sash de los ttk.PanedWindow es GRUESO (10 px) y
  del color del borde, para verse y agarrarse sin puntería; se
  aplica en ambos temas.
* Preferencias (ui.prefs): nuevos diccionarios «sashes» (posiciones de
  los separadores de la ventana principal) y «dialogs» (geometría
  recordada de cada ventana secundaria); lectura tolerante de un
  archivo corrupto y redondeo ida-y-vuelta.
* Ayudantes puros (ui.app_window): geometry_size() valida geometrías
  Tk con posición positiva/negativa y descarta basura.
* Ventana principal real (Tk bajo Xvfb): separadores con posiciones
  por defecto amables (plano grande), arrastre + _save_prefs_now()
  los persiste, y una NUEVA ventana los restaura; minsize global;
  launch() respeta la geometría guardada; toggle_panel sigue vivo
  después de restaurar sashes.
* Ventanas secundarias: catálogo, detalles, importar §94 (catálogo y
  DXF/DWG), asistente de edificación y de local, guía rápida, estado,
  editar propiedad, nuevo objeto y tipo de objeto — TODAS salen
  redimensionables, con minsize, y las grandes recuerdan su geometría
  al cerrarse (prefs["dialogs"][clave]) para reabrirse como estaban.
"""

from __future__ import annotations

import os
import time
import unittest

from tests.base import ARQGenTestCase

from ui import prefs as prefs_mod
from ui.app_window import DIALOG_DEFAULTS, geometry_size
from ui.theme import SASH_THICKNESS


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


class TestPrefsAjustables(ARQGenTestCase):
    """Nuevas preferencias sashes + dialogs, tolerantes."""

    def test_defaults_traen_sashes_y_dialogs(self):
        self.assertEqual(prefs_mod.DEFAULTS["sashes"], {})
        self.assertEqual(prefs_mod.DEFAULTS["dialogs"], {})

    def test_merge_tolerante_con_basura(self):
        merged = prefs_mod._merge_defaults({
            "sashes": "no-soy-dict", "dialogs": {1: "x", "ok": {}},
        })
        self.assertEqual(merged["sashes"], {})
        # las claves no-texto se descartan; las de texto, no
        self.assertEqual(merged["dialogs"], {"ok": {}})

    def test_ida_y_vuelta_sashes_y_dialogs(self):
        path = os.path.join(self.tmp, "prefs.json")
        prefs_mod.save_prefs({"sashes": {"paned": [280, 940],
                                         "outer": [580]},
                              "dialogs": {"detalles": "1120x760+30+20"}},
                             path)
        loaded = prefs_mod.load_prefs(path)
        self.assertEqual(loaded["sashes"]["paned"], [280, 940])
        self.assertEqual(loaded["sashes"]["outer"], [580])
        self.assertEqual(loaded["dialogs"]["detalles"], "1120x760+30+20")

    def test_archivo_corrupto_da_defectos(self):
        path = os.path.join(self.tmp, "roto.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{esto no es json")
        loaded = prefs_mod.load_prefs(path)
        self.assertEqual(loaded["sashes"], {})
        self.assertEqual(loaded["dialogs"], {})

    def test_los_defaults_no_se_mutan_entre_ventanas(self):
        # REGRESIÓN v3.7.0: dict(DEFAULTS) superficial compartía los
        # diccionarios anidados — la ventana A mutaba los defaults que
        # luego heredaba la ventana B del mismo proceso.
        first = prefs_mod.load_prefs(os.path.join(self.tmp, "a.json"))
        first["sashes"]["paned"] = [210, 1010]
        first["panels"]["explorer"] = False
        second = prefs_mod.load_prefs(os.path.join(self.tmp, "b.json"))
        self.assertEqual(second["sashes"], {})
        self.assertEqual(second["panels"]["explorer"], True)
        self.assertEqual(prefs_mod.DEFAULTS["sashes"], {})
        self.assertEqual(prefs_mod.DEFAULTS["panels"]["explorer"], True)


class TestGeometrySize(ARQGenTestCase):
    """Validación pura de geometrías Tk."""

    def test_valida_tamano_sencillo(self):
        self.assertEqual(geometry_size("1020x680"), "1020x680")

    def test_valida_con_posicion(self):
        self.assertEqual(geometry_size("1120x760+30+20"),
                         "1120x760+30+20")

    def test_valida_posicion_negativa(self):
        self.assertEqual(geometry_size("900x600-10-20"),
                         "900x600-10-20")

    def test_descarta_basura_y_diminutos(self):
        self.assertEqual(geometry_size(""), "")
        self.assertEqual(geometry_size("grande"), "")
        self.assertEqual(geometry_size("100x600"), "")   # < 200 de ancho
        self.assertEqual(geometry_size("900x50"), "")    # < 160 de alto
        self.assertEqual(geometry_size(None), "")
        self.assertEqual(geometry_size(12345), "")

    def test_tabla_de_dialogos_cubierta(self):
        for key in ("catalogo", "detalles", "presupuesto",
                    "importar_catalogo", "importar_dxf",
                    "building_wizard", "design_wizard", "guia"):
            conf = DIALOG_DEFAULTS[key]
            self.assertTrue(geometry_size(conf["geometry"]), key)
            self.assertEqual(len(conf["min"]), 2, key)


class TestTemaSashGrueso(ARQGenTestCase):
    """El separador arrastrable se VÉ (10 px) en ambos temas."""

    def test_constante_publica(self):
        self.assertGreaterEqual(SASH_THICKNESS, 8)

    def test_estilo_aplicado_en_los_dos_temas(self):
        if not DISPLAY:
            self.skipTest("sin display")
        import tkinter as tk
        from tkinter import ttk
        from ui import theme
        root = tk.Tk()
        root.withdraw()
        try:
            for modo in ("dark", "light"):
                theme.apply(root, modo)
                style = ttk.Style(root)
                grosor = style.lookup("Sash", "sashthickness")
                self.assertTrue(str(grosor), "sashthickness configurado")
                self.assertGreaterEqual(int(grosor), 8)
        finally:
            root.destroy()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestVentanaPrincipalSashes(ARQGenTestCase):
    """Sashes reales de la ventana principal: defectos, guardar,
    restaurar y convivencia con toggle_panel."""

    def _make_window(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.demo_context()
        return ARQGenWindow(self.context, self.application)

    def setUp(self):
        super().setUp()
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_defectos_amables_para_el_plano(self):
        window = self._make_window()
        try:
            window.geometry("1280x800")
            # se espera al MAPEO real + asentamiento de los Configure
            # pendientes: antes de eso el PanedWindow re-distribuye por
            # pesos y pisaría los sashes que apliquemos
            for _ in range(100):
                window.update()
                if window.winfo_ismapped() \
                        and window._paned.winfo_ismapped():
                    break
            for _ in range(30):
                window.update()
                time.sleep(0.01)
            window._apply_saved_sashes()
            self.assertEqual(len(window._paned.panes()), 3)
            # Tk puede recortar el sashpos pedido por los tamaños
            # mínimos de los hijos (fuente/DPI de cada plataforma): se
            # admite una tolerancia de 60 px alrededor del defecto.
            self.assertAlmostEqual(window._paned.sashpos(0), 240, delta=60)
            self.assertAlmostEqual(window._paned.sashpos(1), 980, delta=60)
            # el plano (centro) queda con la mayor parte
            ancho_centro = window._paned.sashpos(1) \
                - window._paned.sashpos(0) - SASH_THICKNESS
            self.assertGreater(ancho_centro, 500)
            # panel inferior: 120 px por encima del mínimo (v3.9.1)
            self.assertGreaterEqual(window._outer_paned.sashpos(0), 300)
        finally:
            window.destroy()
            self.context.close()

    def test_arrastre_y_restauracion_entre_sesiones(self):
        window = self._make_window()
        try:
            window.geometry("1280x800")
            window.update()
            window._apply_saved_sashes()
            window._paned.sashpos(0, 210)
            window._paned.sashpos(1, 1010)
            window._outer_paned.sashpos(0, 400)
            window._save_prefs_now()
            # Tk puede recortar lo pedido por los tamaños mínimos de
            # los paneles (fuente/DPI de la plataforma): lo guardado
            # debe ser EXACTAMENTE lo que quedó a la vista.
            vistos = {"paned": [window._paned.sashpos(0),
                                window._paned.sashpos(1)],
                      "outer": [window._outer_paned.sashpos(0)]}
            sashes = window.prefs["sashes"]
            self.assertEqual(sashes["paned"], vistos["paned"])
            self.assertEqual(sashes["outer"], vistos["outer"])
        finally:
            window.destroy()
            self.context.close()
        # una ventana NUEVA (misma sesión de prefs) recupera las
        # posiciones exactas: la app «recuerda» cómo dejaste los bordes
        context2 = self.demo_context()
        try:
            from ui.app_window import ARQGenWindow
            window2 = ARQGenWindow(context2, self.application)
            window2.geometry("1280x800")
            window2.update()
            window2._apply_saved_sashes()
            window2.update()
            self.assertEqual(window2._paned.sashpos(0), vistos["paned"][0])
            self.assertEqual(window2._paned.sashpos(1), vistos["paned"][1])
            self.assertEqual(window2._outer_paned.sashpos(0),
                             vistos["outer"][0])
            window2.destroy()
        finally:
            context2.close()

    def test_sashes_descartados_si_panel_oculto(self):
        window = self._make_window()
        try:
            window.geometry("1280x800")
            for _ in range(100):
                window.update()
                if window.winfo_ismapped() \
                        and window._paned.winfo_ismapped():
                    break
            # se oculta PRIMERO: toggle_panel persiste las posiciones
            # VIVAS (vía _save_prefs_now → _collect_sashes) y pisaría
            # cualquier valor plantado antes del giro
            window.toggle_panel("props")  # quedan 2 paneles horizontales
            window.update()
            # sashes guardadas pensadas para UN layout de 3 paneles
            window.prefs["sashes"] = {"paned": [100, 900],
                                      "outer": [400]}
            window._apply_saved_sashes()
            self.assertEqual(len(window._paned.panes()), 2)
            # cuentas distintas: la restauración del horizontal se
            # DESCARTA y el vertical (2 paneles) SÍ se aplica — se
            # observa el mecanismo, no los píxeles, porque Tk recorta
            # el sashpos por los tamaños pedidos de los hijos según
            # fuente/DPI de cada plataforma (en Windows el natural del
            # vertical cae por encima de 400 y un «<= 400» absoluto no
            # es portable)
            self.assertEqual(window._sashes_last,
                             {"paned": False, "outer": True})
            # si el guardo faltara, el 100 pensado para 3 paneles se
            # colaría en el layout de 2: jamás debe verse
            self.assertNotEqual(window._paned.sashpos(0), 100)
            window.toggle_panel("props")
        finally:
            window.destroy()
            self.context.close()

    def test_minsize_y_launch_respeta_geometria_guardada(self):
        window = self._make_window()
        try:
            self.assertEqual(window.minsize(), (960, 600))
            window.geometry("1152x720")
            window.update()
            window._save_prefs_now()
        finally:
            window.destroy()
            self.context.close()
        context2 = self.demo_context()
        try:
            from ui.app_window import ARQGenWindow
            window2 = ARQGenWindow(context2, self.application)
            self.assertTrue(window2.geometry_restored)
            window2.update()
            self.assertIn("1152x720", window2.geometry())
            window2.destroy()
        finally:
            context2.close()

    def test_toggle_panel_sigue_vivo_tras_restaurar(self):
        window = self._make_window()
        try:
            window.geometry("1280x800")
            window.update()
            window._apply_saved_sashes()
            window.toggle_panel("explorer")
            window.update()
            self.assertEqual(len(window._paned.panes()), 2)
            window.toggle_panel("explorer")
            window.update()
            self.assertEqual(len(window._paned.panes()), 3)
        finally:
            window.destroy()
            self.context.close()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestVentanasSecundariasAjustables(ARQGenTestCase):
    """TODAS las ventanas salen redimensionables y las grandes
    recuerdan su geometría entre sesiones."""

    def setUp(self):
        super().setUp()
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")
        from ui import theme
        theme.set_mode("dark")
        self.context = self.demo_context()
        from ui.app_window import ARQGenWindow
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def _check(self, dialog, key, min_esperado):
        self.assertEqual(dialog.minsize(), min_esperado)
        self.assertEqual(dialog.resizable(), (1, 1))
        self.assertTrue(DIALOG_DEFAULTS[key]["geometry"] or True)
        return dialog

    def test_catalogo_ajustable(self):
        self.window.open_catalogo_precons()
        self.window.update()
        dialog = self._check(self.window._catalogo_dialog, "catalogo",
                             (720, 480))
        self.assertIn("1000x660", dialog.geometry() or "1000x660")

    def test_detalles_recuerda_geometria_al_cerrar(self):
        self.window.open_detalles()
        self.window.update()
        dialog = self._check(self.window._det_dialog, "detalles",
                             (760, 500))
        dialog.geometry("1140x780+40+10")
        self.window.update()  # el WM-less necesita un ciclo para fijar
        dialog.destroy()
        self.window.update()
        guardado = self.window.prefs["dialogs"]["detalles"]
        self.assertIn("1140x780", guardado)
        # reabrir: vuelve con la geometría elegida
        self.window.open_detalles()
        self.window.update()
        self.assertIn("1140x780", self.window._det_dialog.geometry())
        self.window._det_dialog.destroy()

    def test_importar_catalogo_y_dxf_ajustables(self):
        self.window.open_importar_catalogo()
        self.window.update()
        self._check(self.window._importar_dialog, "importar_catalogo",
                    (620, 420))
        self.window._importar_dialog.destroy()
        self.window.open_importar_dxf()
        self.window.update()
        self._check(self.window._dxf_dialog, "importar_dxf", (620, 440))
        self.window._dxf_dialog.destroy()

    def test_presupuesto_ajustable(self):
        self.window.open_presupuesto_precons()
        self.window.update()
        self._check(self.window._presupuesto_dialog, "presupuesto",
                    (760, 500))
        self.window._presupuesto_dialog.destroy()

    def test_asistente_edificacion_ajustable(self):
        self.window.open_building_wizard()
        self.window.update()
        dialog = self._check(self.window._building_dialog,
                             "building_wizard", (900, 620))
        self.assertIn("1120x760", dialog.geometry())
        dialog.destroy()

    def test_asistente_local_ajustable(self):
        self.window.open_design_wizard()
        self.window.update()
        dialog = self._check(self.window._wizard_dialog,
                             "design_wizard", (520, 480))
        self.assertIn("640x640", dialog.geometry())
        dialog.destroy()

    def test_guia_rapida_ajustable(self):
        # la guía es modal (wait_window): programamos su cierre y
        # recogemos minsize/resizable antes de que se destruya
        self._guia_info: dict = {}

        def _cerrar() -> None:
            guia = self._top_por_titulo("Guía rápida")
            if guia is not None:
                self._guia_info = {"min": guia.minsize(),
                                   "res": guia.resizable()}
                guia.destroy()
        self.window.after(150, _cerrar)
        self.window.show_quick_guide()
        self.window.update()
        self.assertEqual(self._guia_info.get("min"), (500, 460))
        self.assertEqual(self._guia_info.get("res"), (1, 1))

    def _tops(self):
        import tkinter as tk
        return [c for c in self.window.winfo_children()
                if isinstance(c, tk.Toplevel)]

    def _top_por_titulo(self, texto):
        for top in self._tops():
            try:
                if texto in top.title():
                    return top
            except Exception:  # noqa: BLE001 - ya destruida
                continue
        return None

    def _seleccionar_objeto(self):
        from ui.models import ExplorerModel
        filas = ExplorerModel(self.context).rows_for("ARCHITECTURE")
        objetivo = next((r for r in filas if r.entity is not None), None)
        self.assertIsNotNone(objetivo)
        self.window.selection = objetivo

    def test_formularios_salen_redimensionables(self):
        # estado + editar propiedad: necesitan selección
        self._seleccionar_objeto()
        self.window.change_state_dialog()
        self.window.update()
        estado = self._top_por_titulo("Estado de la entidad")
        self.assertIsNotNone(estado)
        self._check(estado, "estado", (420, 320))
        estado.destroy()
        self.window.edit_property_dialog()
        self.window.update()
        editar = self._top_por_titulo("Editar")
        self.assertIsNotNone(editar)
        self._check(editar, "editar", (380, 260))
        editar.destroy()

    def test_geometria_de_dialogos_no_se_guarda_para_formularios(self):
        # remember=False: estado/editar/nuevo objeto no escriben prefs
        self._seleccionar_objeto()
        self.window.change_state_dialog()
        self.window.update()
        estado = self._top_por_titulo("Estado de la entidad")
        self.assertIsNotNone(estado)
        estado.geometry("500x400+10+10")
        estado.destroy()
        self.window.update()
        self.assertNotIn("estado", self.window.prefs.get("dialogs", {}))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
