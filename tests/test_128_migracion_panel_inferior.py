"""MIGRACIÓN DEL PANEL INFERIOR COMPACTO (v3.9.1).

Lo pedido: «el espacio donde salen los recordatorios de los gestos del
lienzo es el espacio que está sobredimensionado, casi ocupa la mitad
del espacio de la ventana y se la resta al modelador».

Causa raíz: las preferencias heredadas de la v3.8.0 guardaban el
separador inferior con una colocación FIJA a 400 px desde arriba (el
default de aquella era), pensada para ventanas grandes; al restaurarse
tal cual en ventanas de 700-800 px de alto, el panel de avisos/registro
(donde aparecen consejos como «Arrastra los separadores a tu gusto»)
quedaba con la mitad de la ventana y se la robaba al plano.

Cobertura de estas pruebas:

* Preferencias (ui.prefs): PREFS_VERSION sube a 2; el marcador
  «bottom_compact» SOLO sobrevive en archivos de formato v2 (un
  prefs.json heredado v1 no puede «colarlo»); los sashes heredados se
  leen intactos (decide la ventana, no el lector).
* Migración one-shot (ui.app_window): la primera sesión que aplica
  sashes descarta el «outer» heredado, impone el default compacto
  (120 px por encima del mínimo), marca la preferencia y BORRA el
  guardado heredado para que los re-apliques del arranque (hay dos
  after() programados) ni reset_layout lo revivan.
* Segunda sesión: lo que el usuario deje tras la migración se respeta
  EXACTO (idéntico al ida-y-vuelta de la v3.7.0).
* De fábrica (sin prefs): el panel inferior nace compacto y el
  Treeview de «Estado de cálculos» también pide poco alto.
"""

from __future__ import annotations

import json
import os
import time
import unittest

from tests.base import ARQGenTestCase

from ui import prefs as prefs_mod
from ui.app_window import SASH_DEFAULT_BOTTOM_MARGIN


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


class TestPrefsCompactas(ARQGenTestCase):
    """El formato v2 de preferencias y su migración tolerante."""

    def test_version_subio_a_2(self):
        self.assertGreaterEqual(prefs_mod.PREFS_VERSION, 2)
        self.assertEqual(prefs_mod.DEFAULTS["bottom_compact"], False)

    def test_prefs_v2_conservan_bottom_compact(self):
        path = os.path.join(self.tmp, "prefs_v2.json")
        prefs_mod.save_prefs({"bottom_compact": True, "sashes": {}}, path)
        with open(path, "r", encoding="utf-8") as fh:
            crudo = json.load(fh)
        self.assertEqual(crudo["version"], 2)
        cargadas = prefs_mod.load_prefs(path)
        self.assertTrue(cargadas["bottom_compact"])

    def test_prefs_v1_no_cuelan_bottom_compact(self):
        # un archivo heredado con la marca falsificada (o basura) no
        # puede saltarse la migración: solo v2 es de confianza
        path = os.path.join(self.tmp, "prefs_v1.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "bottom_compact": True,
                       "sashes": {"outer": [400]}}, fh)
        cargadas = prefs_mod.load_prefs(path)
        self.assertFalse(cargadas["bottom_compact"])
        # los sashes heredados se leen INTACTOS: si la migración
        # procede es decisión de la ventana, no del lector
        self.assertEqual(cargadas["sashes"].get("outer"), [400])

    def test_archivo_corrupto_vuelve_a_fabrica(self):
        path = os.path.join(self.tmp, "prefs_roto.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{esto no es json")
        cargadas = prefs_mod.load_prefs(path)
        self.assertFalse(cargadas["bottom_compact"])
        self.assertEqual(cargadas["sashes"], {})


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestMigracionPanelInferior(ARQGenTestCase):
    """Ventana real: migración one-shot y respeto posterior."""

    def _prefs_path(self) -> str:
        return os.environ["ARQGEN_PREFS"]

    def _write_prefs(self, data: dict) -> None:
        with open(self._prefs_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def _read_prefs(self) -> dict:
        with open(self._prefs_path(), "r", encoding="utf-8") as fh:
            return json.load(fh)

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

    def _make_window(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.demo_context()
        return ARQGenWindow(self.context, self.application)

    def _esperar_mapeo(self, window) -> None:
        window.geometry("1280x800")
        for _ in range(100):
            window.update()
            if window.winfo_ismapped() and window._paned.winfo_ismapped():
                break
        for _ in range(30):
            window.update()
            time.sleep(0.01)

    def test_prefs_heredadas_se_migran_al_compacto(self):
        # exactamente el escenario del usuario: prefs de la v3.8.0 con
        # el separador inferior fijo a 400 px → media ventana robada
        self._write_prefs({"version": 1, "theme": "dark",
                           "sashes": {"paned": [240, 980],
                                      "outer": [400]}})
        window = self._make_window()
        try:
            self._esperar_mapeo(window)
            window._apply_saved_sashes()
            default = max(300, 800 - SASH_DEFAULT_BOTTOM_MARGIN)
            # Tk puede recortar por fuente/DPI: tolerancia 60 px
            self.assertAlmostEqual(window._outer_paned.sashpos(0),
                                   default, delta=60)
            # el panel inferior quedó PEQUEÑO (no a media ventana)
            self.assertGreater(window._outer_paned.sashpos(0), 500)
            # y la migración quedó marcada en memoria…
            self.assertTrue(window.prefs["bottom_compact"])
            # …el guardado heredado se borró de las prefs vivas, para
            # que un re-aplique no lo reviva
            self.assertNotIn("outer", window.prefs["sashes"])
            window._save_prefs_now()
        finally:
            window.destroy()
            self.context.close()
        # …y en el archivo (formato v2)
        crudo = self._read_prefs()
        self.assertEqual(crudo["version"], 2)
        self.assertTrue(crudo["bottom_compact"])

    def test_segunda_sesion_respeta_lo_guardado(self):
        self._write_prefs({"version": 2, "theme": "dark",
                           "bottom_compact": True,
                           "sashes": {"paned": [240, 980],
                                      "outer": [400]}})
        window = self._make_window()
        try:
            self._esperar_mapeo(window)
            window._apply_saved_sashes()
            # ya migrado: lo que el usuario dejó manda (400 válido
            # en una ventana de 800 px, sin recortes de por medio)
            self.assertAlmostEqual(window._outer_paned.sashpos(0),
                                   400, delta=10)
        finally:
            window.destroy()
            self.context.close()

    def test_fabrica_sin_prefs_nace_compacto(self):
        window = self._make_window()
        try:
            self._esperar_mapeo(window)
            window._apply_saved_sashes()
            default = max(300, 800 - SASH_DEFAULT_BOTTOM_MARGIN)
            self.assertAlmostEqual(window._outer_paned.sashpos(0),
                                   default, delta=60)
            self.assertGreater(window._outer_paned.sashpos(0), 500)
        finally:
            window.destroy()
            self.context.close()

    def test_reset_layout_no_revisa_la_migracion(self):
        self._write_prefs({"version": 1, "theme": "dark",
                           "sashes": {"outer": [400]}})
        window = self._make_window()
        try:
            self._esperar_mapeo(window)
            window.reset_layout()
            default = max(300, 800 - SASH_DEFAULT_BOTTOM_MARGIN)
            self.assertAlmostEqual(window._outer_paned.sashpos(0),
                                   default, delta=60)
            self.assertTrue(window.prefs["bottom_compact"])
        finally:
            window.destroy()
            self.context.close()
        # reset_layout guarda las posiciones VIVAS (visto == guardado):
        # lo persistido debe ser el compacto, jamás el 400 heredado
        crudo = self._read_prefs()
        guardado = (crudo.get("sashes") or {}).get("outer")
        self.assertIsInstance(guardado, list)
        self.assertEqual(len(guardado), 1)
        self.assertGreater(guardado[0], 500)

    def test_estado_de_calculos_pide_poco_alto(self):
        window = self._make_window()
        try:
            window.update()
            self.assertEqual(int(window.calc_tree.cget("height")), 4)
        finally:
            window.destroy()
            self.context.close()
