"""BIBLIOTECA DE DETALLES CONSTRUCTIVOS por ediciones regionales (v3.5.0).

Lo pedido: «bibliotecas de detalles constructivos por ediciones
regionales».

Cobertura de estas pruebas:

* Registro (domain/detalles.py): carga de la base universal (20
  detalles en 8 categorías), fichas tipadas con corte por capas,
  espesor total coherente, ficha() legible y búsqueda SIN acentos.
* Ediciones regionales (México, Colombia, Argentina, Cuba): cada una
  AÑADE sus detalles propios (muro confinado de block, bahareque
  cementado, doble muro cerámico, teja criolla), México REEMPLAZA la
  azotea plana por su versión con prefabricado, Cuba RETIRA el
  hormigón celular autoclavado, y la BASE NUNCA SE CORROMPE
  (deepcopy) ni tras reemplazos ni tras regiones inválidas.
* Exportador SVG (exporters/detalle_svg.py): esquema determinista
  byte a byte con todas las capas, la cota del espesor total y el
  cajetín de la edición; sin capas no se rompe.
* CLI `detalles regiones|list|ver|svg`: sin proyecto, rc=0/1
  correctos, --region activa la edición y --categoria filtra.
* GUI (ui.app_window.open_detalles): diálogo con ganchos _det_*,
  cambio de edición, búsqueda, ficha en el panel y exportación SVG;
  menú Herramientas y tooltips det_*.
"""

from __future__ import annotations

import os
import unittest
from io import StringIO
from unittest.mock import patch

from tests.base import ARQGenTestCase

from app.paths import resource_path
from domain.detalles import (
    BASE_RESOURCE,
    CATEGORIAS,
    CapaDetalle,
    DetalleConstructivo,
    DetallesRegistry,
    get_registry,
    reset_registry,
    sin_acentos,
)


def run_cli(argv, log_dir):
    from app.cli import run
    with patch("sys.stdout", new=StringIO()) as out:
        code = run(["--log-dir", log_dir] + argv)
    return code, out.getvalue()


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


class TestBibliotecaBase(ARQGenTestCase):
    """La biblioteca universal carga con fichas tipadas y coherentes."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)

    def test_base_carga_20_detalles_en_8_categorias(self):
        registry = get_registry()
        self.assertEqual(len(registry), 20)
        self.assertEqual(registry.categories(), list(CATEGORIAS))
        self.assertEqual(registry.version, "1.1")
        self.assertTrue(registry.region_is_base())
        # todas las fichas son DetalleConstructivo con capas válidas
        for detalle in registry.list_details():
            self.assertIsInstance(detalle, DetalleConstructivo)
            self.assertTrue(detalle.capas, detalle.id)
            for capa in detalle.capas:
                self.assertIsInstance(capa, CapaDetalle)
                self.assertGreater(capa.espesor_mm, 0)

    def test_espesor_total_suma_las_capas(self):
        registry = get_registry()
        detalle = registry.get("muros/muro_bloque_enlucido")
        self.assertIsNotNone(detalle)
        self.assertEqual(detalle.espesor_total_mm, 230.0)
        self.assertEqual(detalle.espesor_total_m, 0.23)
        # capas de 15 + 200 + 15
        self.assertEqual([c.espesor_mm for c in detalle.capas],
                         [15.0, 200.0, 15.0])

    def test_ficha_incluye_corte_norma_y_edicion(self):
        registry = get_registry()
        ficha = registry.get("cimentaciones/zapata_corrida_ha").ficha()
        self.assertIn("Zapata corrida de hormigón armado", ficha)
        self.assertIn("Corte (de abajo arriba)", ficha)
        self.assertIn("Espesor total: 600 mm", ficha)
        self.assertIn("biblioteca universal", ficha)
        self.assertIn("tensión admisible", ficha)

    def test_busqueda_sin_acentos_y_por_material(self):
        registry = get_registry()
        ids = [d.id for d in registry.search("CIMENTACIÓN")]
        self.assertIn("cimentaciones/zapata_corrida_ha", ids)
        # busca por material de una capa («teja»), no solo por nombre
        tejas = {d.id for d in registry.search("teja")}
        self.assertIn("cubiertas/cubierta_inclinada_teja", tejas)
        # filtra por categoría exacta
        for detalle in registry.list_details(categoria="cubiertas"):
            self.assertEqual(detalle.categoria, "cubiertas")
        self.assertEqual(registry.list_details(categoria="no-existe"), [])

    def test_get_desconocido_devuelve_none_y_sin_acentos_normaliza(self):
        registry = get_registry()
        self.assertIsNone(registry.get("muros/no_existe"))
        self.assertEqual(sin_acentos("Cimentación SÍ"), "cimentacion si")

    def test_registro_independiente_sin_recursos_no_explota(self):
        registry = DetallesRegistry()
        # sin load: consultas vacías pero nunca excepciones
        self.assertEqual(len(registry), 0)
        self.assertEqual(registry.categories(), [])
        self.assertIsNone(registry.get("x/y"))
        # sin base cargada, la región se activa igual (comportamiento
        # tolerante): quedan SOLO los detalles de la edición
        self.assertTrue(registry.set_region("mexico"))
        self.assertEqual(len(registry), 6)
        self.assertIsNotNone(registry.get("muros/muro_confinado_block14"))


class TestEdicionesRegionales(ARQGenTestCase):
    """Las ediciones añaden, reemplazan y retiran sin tocar la base."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)

    def test_cuatro_ediciones_instaladas(self):
        registry = get_registry()
        codigos = {r["codigo"] for r in registry.available_regions()}
        self.assertTrue({"mexico", "colombia", "argentina", "cuba"}
                        <= codigos)
        for info in registry.available_regions():
            self.assertTrue(info["nombre"])
            self.assertTrue(info["edicion"])
            self.assertTrue(info["archivo"].endswith(".json"))

    def test_mexico_anade_confinado_y_reemplaza_azotea(self):
        registry = get_registry()
        base_azotea = registry.get("cubiertas/cubierta_plana_losa").nombre
        self.assertTrue(registry.set_region("mexico"))
        self.assertEqual(registry.region_code, "mexico")
        # añade los detalles propios (regional=True)
        confinado = registry.get("muros/muro_confinado_block14")
        self.assertIsNotNone(confinado)
        self.assertTrue(confinado.regional)
        self.assertIn("castillos", confinado.norma)
        self.assertIsNotNone(registry.get("muros/nodo_castillo_dala"))
        # reemplaza la azotea por la edición mexicana
        azotea = registry.get("cubiertas/cubierta_plana_losa")
        self.assertEqual(azotea.nombre,
                         "Azotea plana impermeabilizada (prefabricado 4 mm)")
        self.assertTrue(any(c.nombre.startswith("Prefabricado asfáltico")
                            for c in azotea.capas))
        self.assertNotEqual(azotea.nombre, base_azotea)
        # conserva lo universal (Blondel de la escalera, bloque 20 cm)
        self.assertIsNotNone(registry.get("escaleras/escalera_ha_baldosa"))
        self.assertIsNotNone(registry.get("muros/muro_bloque_enlucido"))
        self.assertEqual(len(registry), 25)  # 20 + 6 con 1 reemplazo

    def test_colombia_trae_bahareque_y_norma_nsr10(self):
        registry = get_registry()
        self.assertTrue(registry.set_region("colombia"))
        bahareque = registry.get("muros/bahareque_cementado")
        self.assertIsNotNone(bahareque)
        self.assertIn("guadua", bahareque.nombre)
        self.assertIn("NSR-10", bahareque.norma)
        losa = registry.get("entrepisos/losa_maciza_fc21")
        self.assertIn("21 MPa", losa.nombre)
        # el muro de México NO está en la edición colombiana
        self.assertIsNone(registry.get("muros/muro_confinado_block14"))

    def test_cuba_retira_el_celular_autoclavado(self):
        registry = get_registry()
        self.assertIsNotNone(registry.get("muros/muro_hormigon_celular"))
        self.assertTrue(registry.set_region("cuba"))
        self.assertIsNone(registry.get("muros/muro_hormigon_celular"))
        self.assertIsNotNone(registry.get("cubiertas/teja_criolla_cuba"))
        self.assertIsNotNone(registry.get("acabados/mosaico_granito_cuba"))
        self.assertEqual(len(registry), 25)  # 20 - 1 + 6

    def test_reset_vuelve_a_la_base_y_no_la_corrompe(self):
        registry = get_registry()
        base_nombres = {d.id: d.nombre for d in registry.list_details()}
        registry.set_region("mexico")
        registry.set_region("cuba")
        registry.reset_region()
        self.assertTrue(registry.region_is_base())
        self.assertEqual(len(registry), 20)
        for did, nombre in base_nombres.items():
            self.assertEqual(registry.get(did).nombre, nombre)
        # el disclaimer vuelve al de la base
        self.assertIn("norma local vigente", registry.disclaimer)

    def test_region_invalida_devuelve_false_y_queda_la_base(self):
        registry = get_registry()
        self.assertFalse(registry.set_region("atlantida"))
        self.assertTrue(registry.region_is_base())
        self.assertEqual(len(registry), 20)
        self.assertEqual(registry.region_tag(), "")

    def test_region_repetida_es_idempotente(self):
        registry = get_registry()
        self.assertTrue(registry.set_region("argentina"))
        primero = {d.id for d in registry.list_details()}
        self.assertTrue(registry.set_region("argentina"))
        self.assertEqual({d.id for d in registry.list_details()}, primero)
        self.assertEqual(len(registry), 25)


class TestExportadorSVG(ARQGenTestCase):
    """El esquema SVG del detalle es determinista y completo."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.registry = get_registry()

    def test_svg_determinista_byte_a_byte(self):
        from exporters.detalle_svg import export_detalle_svg
        self.registry.set_region("mexico")
        detalle = self.registry.get("muros/muro_confinado_block14")
        self.assertIsNotNone(detalle)
        a = os.path.join(self.tmp, "a.svg")
        b = os.path.join(self.tmp, "sub", "b.svg")  # crea directorio
        export_detalle_svg(detalle, a, region_label="México")
        export_detalle_svg(detalle, b, region_label="México")
        raw_a = open(a, "rb").read()
        raw_b = open(b, "rb").read()
        self.assertEqual(raw_a, raw_b)
        self.assertTrue(raw_a.startswith(b"<?xml"))
        self.assertIn(b"<svg", raw_a)

    def test_svg_contiene_capas_cota_y_cajetin(self):
        from exporters.detalle_svg import export_detalle_svg
        detalle = self.registry.get("cimentaciones/zapata_corrida_ha")
        path = os.path.join(self.tmp, "zapata.svg")
        export_detalle_svg(detalle, path, region_label="Base")
        raw = open(path, encoding="utf-8").read()
        for capa in detalle.capas:
            self.assertIn(capa.nombre, raw)
        self.assertIn("ESPESOR TOTAL 600 mm", raw)
        self.assertIn("LEYENDA", raw)
        self.assertIn("Biblioteca de detalles constructivos", raw)
        self.assertIn(detalle.id, raw)
        # los números de capa están como círculos
        self.assertEqual(raw.count("<circle"), len(detalle.capas))

    def test_svg_sin_capas_no_se_rompe_y_none_falla_controlado(self):
        from core.errors import ExportError
        from exporters.detalle_svg import export_detalle_svg
        vacio = DetalleConstructivo(id="x/vacio", categoria="muros",
                                    nombre="Detalle sin capas")
        path = os.path.join(self.tmp, "vacio.svg")
        export_detalle_svg(vacio, path)
        self.assertTrue(os.path.getsize(path) > 200)
        with self.assertRaises(ExportError):
            export_detalle_svg(None, os.path.join(self.tmp, "n.svg"))


class TestCLIDetalles(ARQGenTestCase):
    """CLI `detalles` sin proyecto: regiones, list, ver y svg."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.log_dir = os.path.join(self.tmp, "logs")

    def cli(self, argv):
        return run_cli(argv, self.log_dir)

    def test_regiones_lista_ediciones(self):
        code, out = self.cli(["detalles", "regiones"])
        self.assertEqual(code, 0, out)
        self.assertIn("biblioteca universal (20 detalles", out)
        for nombre in ("mexico", "colombia", "argentina", "cuba"):
            self.assertIn(nombre, out)

    def test_list_filtra_region_y_categoria(self):
        code, out = self.cli(["detalles", "list", "--region", "mexico",
                              "--categoria", "muros"])
        self.assertEqual(code, 0, out)
        self.assertIn("muros/muro_confinado_block14", out)
        self.assertNotIn("cimentaciones/zapata_corrida_ha", out)
        code, out = self.cli(["detalles", "list", "--region", "mexico",
                              "--categoria", "inyecciones"])
        self.assertEqual(code, 1)
        self.assertIn("Categoría desconocida", out)

    def test_ver_ficha_completa_y_desconocido_falla(self):
        code, out = self.cli(["detalles", "ver",
                              "muros/bahareque_cementado",
                              "--region", "colombia"])
        self.assertEqual(code, 0, out)
        self.assertIn("Bahareque cementado", out)
        self.assertIn("NSR-10", out)
        self.assertIn("Corte (de exterior a interior)", out)
        code, out = self.cli(["detalles", "ver", "muros/no_existe"])
        self.assertEqual(code, 1)
        self.assertIn("Detalle no encontrado", out)

    def test_svg_exporta_fichero_y_region_invalida_falla(self):
        path = os.path.join(self.tmp, "teja_criolla.svg")
        code, out = self.cli(["detalles", "svg", "cubiertas/teja_criolla_cuba",
                              path, "--region", "cuba"])
        self.assertEqual(code, 0, out)
        raw = open(path, encoding="utf-8").read()
        self.assertIn("<svg", raw)
        self.assertIn("Teja criolla 30×30", raw)
        code, out = self.cli(["detalles", "svg", "muros/muro_confinado_block14",
                              os.path.join(self.tmp, "x.svg"),
                              "--region", "atlantida"])
        self.assertEqual(code, 1)
        self.assertIn("Edición regional sin fichero", out)

    def test_buscar_sin_acentos_por_cli(self):
        code, out = self.cli(["detalles", "list", "--buscar", "sismo",
                              "--region", "mexico", "--limite", "0"])
        self.assertEqual(code, 0, out)
        self.assertIn("muro_confinado_block14", out)


class TestDetallesGUIHeadless(ARQGenTestCase):
    """Capa de diálogo sin display: método, tooltips y menú."""

    def test_dialogo_detalles_existe_en_la_ventana(self):
        from ui import app_window
        self.assertTrue(hasattr(app_window.ARQGenWindow, "open_detalles"))

    def test_tooltips_detalles_registrados(self):
        from ui.help import TOOLTIPS
        for key in ("det_region", "det_cat", "det_search", "det_tree",
                    "det_text", "det_svg"):
            self.assertIn(key, TOOLTIPS)
            self.assertTrue(TOOLTIPS[key].strip())


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDetallesGuiFlow(ARQGenTestCase):
    """Flujo completo del navegador de detalles en la ventana real."""

    def setUp(self):
        super().setUp()
        from ui import theme
        from ui.app_window import ARQGenWindow
        self._old_env = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp, "prefs.json")
        theme.set_mode("dark")
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()
        self.window.open_detalles()
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_dialogo_carga_la_base_y_cambia_de_edicion(self):
        window = self.window
        self.assertEqual(len(window._det_tree.get_children()), 20)
        self.assertIn("base", window._det_codes)
        # selecciona la edición argentina (índice por codes)
        index = window._det_codes.index("argentina")
        window._det_region.current(index)
        window._det_run_search()
        self.window.update()
        rows = window._det_tree.get_children()
        self.assertEqual(len(rows), 25)
        self.assertIn("muros/doble_muro_ceramico", rows)
        self.assertIn("Argentina", window._det_count.get())
        # al volver a la base, el confinado de México desaparece
        window._det_region.current(0)
        window._det_run_search()
        self.assertNotIn("muros/muro_confinado_block14",
                         window._det_tree.get_children())

    def test_ficha_y_exportacion_svg_desde_la_gui(self):
        window = self.window
        window._det_tree.selection_set("muros/muro_bloque_enlucido")
        window._det_show()
        ficha = window._det_text.get("1.0", "end")
        self.assertIn("Muro de bloque de hormigón", ficha)
        self.assertIn("Espesor total: 230 mm", ficha)
        path = os.path.join(self.tmp, "gui_detalle.svg")
        with patch("tkinter.filedialog.asksaveasfilename",
                   return_value=path):
            window._det_export()
        raw = open(path, encoding="utf-8").read()
        self.assertIn("<svg", raw)
        self.assertIn("ESPESOR TOTAL 230 mm", raw)

    def test_exportar_sin_seleccion_no_rompe(self):
        window = self.window
        window._det_tree.selection_remove(*window._det_tree.selection())
        with patch("ui.app_window.messagebox.showinfo") as info:
            window._det_export()
        info.assert_called_once()

    def test_busqueda_en_vivo_desde_la_gui(self):
        window = self.window
        window._det_search.insert(0, "ventana")
        window._det_run_search()
        rows = window._det_tree.get_children()
        self.assertIn("carpinteria/ventana_aluminio_alfizar", rows)
        window._det_search.delete(0, "end")
        window._det_search.insert(0, "NSR-10")
        window._det_region.current(
            window._det_codes.index("colombia"))
        window._det_run_search()
        rows = window._det_tree.get_children()
        self.assertTrue(rows)
        self.assertIn("muros/bahareque_cementado", rows)


if __name__ == "__main__":
    unittest.main()
