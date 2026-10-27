"""DETALLES EN PDF/PNG + VÍNCULO CON LA TIPOLOGÍA (v3.6.0).

Lo pedido: «exportación del detalle también en PDF/PNG, y vincular el
detalle a la tipología constructiva elegida en el asistente de
edificación».

Cobertura de estas pruebas:

* Base ampliada a 20 detalles: muro de mampostería de piedra y muro de
  tierra (adobe o tapial) cubren las tipologías «Muros de piedra» y
  «Tierra (adobe o tapial)» del asistente (v3.5.0 traía 18).
* Vínculo (domain.detalles.TIPOLOGIA_DETALLES): PARIDAD con
  CONSTRUCTION_TYPES del asistente (10 tipologías), recomendaciones
  que existen en la base, orden de abajo arriba, filtro por categoría,
  ADAPTACIÓN a la edición regional (México reemplaza la azotea, Cuba
  retira el celular) y buscador tolerante buscar_tipologia().
* Exportador PDF (exporters/detalle_export.py): vectorial A4
  determinista byte a byte con círculos Bézier (uno por capa), cota
  rotada del espesor total, leyenda, notas transliteradas (λ→lambda,
  ≈→~) y cajetín; sin capas no se rompe, None es ExportError.
* Exportador PNG: raster 2x determinista con chunks IHDR/IDAT/IEND,
  distinto entre detalles, tolerante sin capas.
* Despachador export_detalle por extensión (.pdf/.png/.svg, mayús.
  incluida; extensión desconocida → SVG).
* CLI `detalles pdf|png|tipologia`: rc y textos, regiones, búsqueda
  ambigua y categoría desconocida.
* GUI: tooltips nuevos (det_tipo/det_png/det_pdf/bld_detalles),
  filtro de tipología en vivo, pre-selección desde el asistente
  (botón «Detalles constructivos…» con _bld_open_detalles) y
  exportación PNG/PDF desde el navegador.
"""

from __future__ import annotations

import inspect
import os
import struct
import unittest
import zlib
from io import StringIO
from unittest.mock import patch

from tests.base import ARQGenTestCase

from domain.detalles import (
    TIPOLOGIA_DETALLES,
    DetalleConstructivo,
    buscar_tipologia,
    detalles_para_tipologia,
    get_registry,
    reset_registry,
    tipologias,
)


def run_cli(argv, log_dir):
    from app.cli import run
    with patch("sys.stdout", new=StringIO()) as out:
        code = run(["--log-dir", log_dir] + argv)
    return code, out.getvalue()


def _pdf_stream(raw: bytes) -> str:
    blob = raw.split(b"stream\n")[1].rsplit(b"\nendstream", 1)[0]
    return zlib.decompress(blob).decode("cp1252", "replace")


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


class TestBaseAmpliada(ARQGenTestCase):
    """La base universal cubre ahora también piedra y tierra."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.registry = get_registry()

    def test_base_20_detalles_version_11(self):
        self.assertEqual(len(self.registry), 20)
        self.assertEqual(self.registry.version, "1.1")
        self.assertIsNotNone(self.registry.get("muros/muro_piedra_mamposteria"))
        self.assertIsNotNone(self.registry.get("muros/muro_adobe_tapial"))

    def test_muro_de_piedra_completo(self):
        from domain.detalles import sin_acentos
        detalle = self.registry.get("muros/muro_piedra_mamposteria")
        self.assertEqual(detalle.espesor_total_mm, 430.0)
        self.assertIn("piedra", detalle.nombre.lower())
        # los «llorones» (piedras atraviesadas) viven en el material
        self.assertTrue(any("lloron" in sin_acentos(c.material)
                            for c in detalle.capas))
        self.assertTrue(any("piedra" in c.material for c in detalle.capas))

    def test_muro_de_tierra_completo(self):
        detalle = self.registry.get("muros/muro_adobe_tapial")
        self.assertEqual(detalle.espesor_total_mm, 470.0)
        self.assertIn("adobe", detalle.nombre.lower())
        # la tierra se protege: zócalo en las notas, aleros en la norma
        texto = " ".join(detalle.notas).lower()
        self.assertIn("zócalo", texto)
        self.assertIn("aleros", detalle.norma.lower())


class TestVinculoTipologia(ARQGenTestCase):
    """TIPOLOGIA_DETALLES responde al asistente y se adapta a la edición."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.registry = get_registry()

    def test_paridad_con_construction_types_del_asistente(self):
        from ui.building_wizard import CONSTRUCTION_TYPES
        self.assertEqual(set(TIPOLOGIA_DETALLES), set(CONSTRUCTION_TYPES))
        self.assertEqual(len(TIPOLOGIA_DETALLES), 10)
        self.assertEqual(tipologias(), tuple(TIPOLOGIA_DETALLES))

    def test_toda_recomendacion_existe_en_la_base(self):
        for tipo, ids in TIPOLOGIA_DETALLES.items():
            self.assertTrue(ids, tipo)
            for did in ids:
                self.assertIsNotNone(self.registry.get(did),
                                     f"{tipo} → {did} no está en la base")

    def test_recomendados_de_mamposteria_en_orden_narrativo(self):
        rows = detalles_para_tipologia(
            self.registry, "Mampostería de bloque + losa de vigueta")
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0].categoria, "cimentaciones")
        self.assertIn("muros/muro_bloque_enlucido",
                      [d.id for d in rows])
        self.assertEqual(rows[-1].categoria, "acabados")

    def test_filtro_por_categoria(self):
        rows = detalles_para_tipologia(self.registry, "Muros de piedra",
                                       categoria="muros")
        self.assertEqual([d.id for d in rows],
                         ["muros/muro_piedra_mamposteria"])
        self.assertEqual(
            [d.id for d in detalles_para_tipologia(
                self.registry, "Muros de piedra", categoria="cubiertas")],
            ["cubiertas/cubierta_inclinada_teja"])

    def test_tipologia_desconocida_devuelve_vacia(self):
        self.assertEqual(
            detalles_para_tipologia(self.registry, "Hielo laminar"), [])
        self.assertEqual(detalles_para_tipologia(self.registry, ""), [])

    def test_mexico_adapta_la_recomendacion(self):
        self.registry.set_region("mexico")
        rows = detalles_para_tipologia(
            self.registry, "Mampostería de bloque + losa de vigueta")
        azotea = next(d for d in rows if d.id == "cubiertas/cubierta_plana_losa")
        self.assertTrue(azotea.regional)
        self.assertIn("prefabricado", azotea.nombre.lower())

    def test_cuba_retira_el_celular_de_panel_sandwich(self):
        tipo = "Panel prefabricado (sandwich)"
        self.assertEqual(len(detalles_para_tipologia(self.registry, tipo)), 7)
        self.registry.set_region("cuba")
        rows = detalles_para_tipologia(self.registry, tipo)
        self.assertEqual(len(rows), 6)
        self.assertNotIn("muros/muro_hormigon_celular",
                         [d.id for d in rows])

    def test_piedra_y_tierra_recomiendan_su_muro(self):
        piedra = detalles_para_tipologia(self.registry, "Muros de piedra")
        self.assertIn("muros/muro_piedra_mamposteria", [d.id for d in piedra])
        tierra = detalles_para_tipologia(self.registry, "Tierra (adobe o tapial)")
        self.assertIn("muros/muro_adobe_tapial", [d.id for d in tierra])
        # y la tierra pide protección de humedades (zócalo + drenaje)
        self.assertIn("humedades/zocalo_impermeable", [d.id for d in tierra])
        self.assertIn("humedades/drenaje_perimetral", [d.id for d in tierra])

    def test_buscar_tipologia_tolerante(self):
        self.assertEqual(buscar_tipologia("TIERRA (ADOBE O TAPIAL)"),
                         "Tierra (adobe o tapial)")
        self.assertEqual(buscar_tipologia("muros de piedra"), "Muros de piedra")
        self.assertEqual(buscar_tipologia("madera ligera"),
                         "Madera ligera")
        with self.assertRaises(ValueError):
            buscar_tipologia("losa")           # ambigua: pega con dos
        self.assertEqual(buscar_tipologia("hielo"), "")

    def test_list_details_con_lista_blanca(self):
        ids = ["muros/muro_bloque_enlucido", "acabados/solado_ceramico_mortero"]
        rows = self.registry.list_details(ids=ids)
        self.assertEqual([d.id for d in rows], ids)  # orden canónico
        # la búsqueda sigue operando dentro de la lista blanca
        rows = self.registry.list_details(ids=ids, texto="bloque")
        self.assertEqual([d.id for d in rows], ["muros/muro_bloque_enlucido"])
        rows = self.registry.list_details(ids=ids, texto="ventana")
        self.assertEqual(rows, [])


class TestExportadorPDF(ARQGenTestCase):
    """El PDF del detalle es vectorial, completo y determinista."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.registry = get_registry()
        from exporters.detalle_export import export_detalle_pdf
        self.export = export_detalle_pdf

    def test_pdf_determinista_byte_a_byte(self):
        self.registry.set_region("mexico")
        detalle = self.registry.get("muros/muro_confinado_block14")
        a = os.path.join(self.tmp, "a.pdf")
        b = os.path.join(self.tmp, "sub", "b.pdf")   # crea directorio
        self.export(detalle, a, region_label="México")
        self.export(detalle, b, region_label="México")
        raw_a = open(a, "rb").read()
        self.assertEqual(raw_a, open(b, "rb").read())
        self.assertTrue(raw_a.startswith(b"%PDF-1.4"))
        self.assertTrue(raw_a.rstrip().endswith(b"%%EOF"))
        self.assertEqual(raw_a.count(b"/Type /Page "), 1)

    def test_pdf_contiene_corte_cota_leyenda_y_cajetin(self):
        detalle = self.registry.get("cimentaciones/zapata_corrida_ha")
        path = os.path.join(self.tmp, "zapata.pdf")
        self.export(detalle, path, region_label="Base (biblioteca universal)")
        stream = _pdf_stream(open(path, "rb").read())
        # un círculo Bézier por capa, con su número
        self.assertEqual(stream.count(" c h "), len(detalle.capas))
        for index in range(1, len(detalle.capas) + 1):
            self.assertIn(f"({index}) Tj", stream)
        self.assertIn("ESPESOR TOTAL 600 mm", stream)
        self.assertIn("LEYENDA \\(materiales\\)", stream)
        for capa in detalle.capas:
            esperado = capa.nombre.replace("(", "\\(").replace(")", "\\)")
            self.assertIn(esperado, stream)
        self.assertIn("Biblioteca de detalles constructivos", stream)
        self.assertIn(detalle.id, stream)
        self.assertIn("Base \\(biblioteca universal\\)", stream)

    def test_pdf_sin_capas_ok_y_none_falla_controlado(self):
        from core.errors import ExportError
        vacio = DetalleConstructivo(id="x/vacio", categoria="muros",
                                    nombre="Detalle sin capas")
        path = os.path.join(self.tmp, "vacio.pdf")
        self.export(vacio, path)
        self.assertTrue(os.path.getsize(path) > 500)
        with self.assertRaises(ExportError) as ctx:
            self.export(None, os.path.join(self.tmp, "n.pdf"))
        self.assertEqual(ctx.exception.code, "ARQ-EXP-071")

    def test_pdf_translitera_lo_que_winansi_no_tiene(self):
        detalle = self.registry.get("muros/muro_hormigon_celular")
        path = os.path.join(self.tmp, "celular.pdf")
        self.export(detalle, path)
        stream = _pdf_stream(open(path, "rb").read())
        self.assertIn("lambda", stream)
        self.assertNotIn("λ", stream)
        self.assertNotIn("≈", stream)


class TestExportadorPNG(ARQGenTestCase):
    """El PNG del detalle es raster 2x, determinista y tolerante."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.registry = get_registry()
        from exporters.detalle_export import export_detalle_png
        self.export = export_detalle_png

    def test_png_determinista_con_chunks_validos(self):
        detalle = self.registry.get("muros/muro_ladrillo_fabrica")
        a = os.path.join(self.tmp, "a.png")
        b = os.path.join(self.tmp, "sub", "b.png")
        self.export(detalle, a, region_label="Base")
        self.export(detalle, b, region_label="Base")
        raw = open(a, "rb").read()
        self.assertEqual(raw, open(b, "rb").read())
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(raw.rstrip().endswith(b"IEND\xaeB\x60\x82"))
        for tag in (b"IHDR", b"IDAT", b"IEND"):
            self.assertIn(tag, raw)
        w, h = struct.unpack(">II", raw[16:24])
        self.assertGreaterEqual(w, 1600)     # 840 px SVG × 2
        self.assertGreaterEqual(h, 1100)

    def test_png_distinto_entre_detalles_y_sin_capas_ok(self):
        from core.errors import ExportError
        muro = self.registry.get("muros/muro_ladrillo_fabrica")
        losa = self.registry.get("entrepisos/losa_maciza_ha")
        self.export(muro, os.path.join(self.tmp, "muro.png"))
        self.export(losa, os.path.join(self.tmp, "losa.png"))
        self.assertNotEqual(
            open(os.path.join(self.tmp, "muro.png"), "rb").read(),
            open(os.path.join(self.tmp, "losa.png"), "rb").read())
        vacio = DetalleConstructivo(id="x/vacio", categoria="muros",
                                    nombre="Sin capas")
        path = os.path.join(self.tmp, "vacio.png")
        self.export(vacio, path)
        self.assertTrue(os.path.getsize(path) > 1000)
        with self.assertRaises(ExportError):
            self.export(None, os.path.join(self.tmp, "n.png"))


class TestDespachadorDetalle(ARQGenTestCase):
    """export_detalle() elige el canal por extensión."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.registry = get_registry()
        from exporters.detalle_export import export_detalle
        self.export = export_detalle
        self.detalle = self.registry.get("escaleras/escalera_ha_baldosa")

    def test_pdf_png_svg_y_mayusculas(self):
        p = os.path.join(self.tmp, "d")
        self.export(self.detalle, p + ".pdf", region_label="Base")
        self.export(self.detalle, p + ".PNG", region_label="Base")
        self.export(self.detalle, p + ".PDF", region_label="Base")
        self.export(self.detalle, p + ".svg", region_label="Base")
        self.assertTrue(open(p + ".pdf", "rb").read().startswith(b"%PDF-1.4"))
        self.assertTrue(open(p + ".PNG", "rb").read().startswith(b"\x89PNG"))
        self.assertTrue(open(p + ".PDF", "rb").read().startswith(b"%PDF-1.4"))
        self.assertTrue(open(p + ".svg", "rb").read().startswith(b"<?xml"))

    def test_extension_desconocida_cae_en_svg(self):
        path = os.path.join(self.tmp, "d.dib")
        self.export(self.detalle, path)
        self.assertTrue(open(path, "rb").read().startswith(b"<?xml"))

    def test_despachador_igual_a_los_exportadores_directos(self):
        from exporters.detalle_export import (export_detalle_pdf,
                                              export_detalle_png)
        base = os.path.join(self.tmp, "x")
        self.export(self.detalle, base + ".pdf", region_label="México")
        export_detalle_pdf(self.detalle, base + "_dir.pdf",
                           region_label="México")
        self.export(self.detalle, base + ".png", region_label="México")
        export_detalle_png(self.detalle, base + "_dir.png",
                           region_label="México")
        self.assertEqual(open(base + ".pdf", "rb").read(),
                         open(base + "_dir.pdf", "rb").read())
        self.assertEqual(open(base + ".png", "rb").read(),
                         open(base + "_dir.png", "rb").read())

    def test_none_falla_en_el_despachador(self):
        from core.errors import ExportError
        with self.assertRaises(ExportError):
            self.export(None, os.path.join(self.tmp, "x.svg"))


class TestCLIDetallesPDFPNGTipologia(ARQGenTestCase):
    """CLI `detalles pdf|png|tipologia` sin proyecto."""

    def setUp(self):
        super().setUp()
        reset_registry()
        self.addCleanup(reset_registry)
        self.log_dir = os.path.join(self.tmp, "logs")

    def cli(self, argv):
        return run_cli(argv, self.log_dir)

    def test_pdf_y_png_desde_cli(self):
        pdf = os.path.join(self.tmp, "cli.pdf")
        code, out = self.cli(["detalles", "pdf",
                              "muros/muro_bloque_enlucido", pdf])
        self.assertEqual(code, 0, out)
        self.assertIn("PDF del detalle generado", out)
        self.assertIn("230 mm", out)
        self.assertTrue(open(pdf, "rb").read().startswith(b"%PDF-1.4"))
        png = os.path.join(self.tmp, "cli.png")
        code, out = self.cli(["detalles", "png",
                              "cubiertas/teja_criolla_cuba", png,
                              "--region", "cuba"])
        self.assertEqual(code, 0, out)
        self.assertIn("PNG del detalle generado", out)
        self.assertIn("edición Cuba", out)
        self.assertTrue(open(png, "rb").read().startswith(b"\x89PNG"))

    def test_pdf_con_region_invalida_falla(self):
        code, out = self.cli(["detalles", "pdf", "muros/no_existe",
                              os.path.join(self.tmp, "x.pdf"),
                              "--region", "atlantida"])
        self.assertEqual(code, 1)
        self.assertIn("Edición regional sin fichero", out)
        code, out = self.cli(["detalles", "png", "muros/no_existe",
                              os.path.join(self.tmp, "y.png")])
        self.assertEqual(code, 1)
        self.assertIn("Detalle no encontrado", out)

    def test_tipologia_lista_recomendados(self):
        code, out = self.cli(["detalles", "tipologia",
                              "mampostería de bloque"])
        self.assertEqual(code, 0, out)
        self.assertIn("RECOMENDADOS PARA «Mampostería de bloque + losa "
                      "de vigueta»", out)
        self.assertIn("9 detalles", out)
        self.assertIn("muros/muro_bloque_enlucido", out)
        self.assertIn("(*) detalle propio de la edición regional", out)

    def test_tipologia_con_region_marca_el_reemplazo(self):
        code, out = self.cli(["detalles", "tipologia", "bloque",
                              "--region", "mexico"])
        self.assertEqual(code, 0, out)
        # la azotea reemplazada por México llega con marcador regional
        self.assertIn(" * cubiertas/cubierta_plana_losa", out)
        self.assertIn("edición México", out)

    def test_tipologia_ambigua_desconocida_y_categoria_mala(self):
        code, out = self.cli(["detalles", "tipologia", "losa"])
        self.assertEqual(code, 1)
        self.assertIn("tipología ambigua", out)
        self.assertIn("Mampostería", out)
        code, out = self.cli(["detalles", "tipologia", "hielo"])
        self.assertEqual(code, 1)
        self.assertIn("Tipología no reconocida", out)
        self.assertIn("Sugerencia:", out)
        code, out = self.cli(["detalles", "tipologia", "bloque",
                              "--categoria", "inyecciones"])
        self.assertEqual(code, 1)
        self.assertIn("Categoría desconocida", out)

    def test_tipologia_afina_por_categoria(self):
        code, out = self.cli(["detalles", "tipologia", "muros de piedra",
                              "--categoria", "muros"])
        self.assertEqual(code, 0, out)
        self.assertIn("1 detalles", out)
        self.assertIn("muros/muro_piedra_mamposteria", out)

    def test_tipologia_con_region_invalida_falla(self):
        code, out = self.cli(["detalles", "tipologia", "bloque",
                              "--region", "atlantida"])
        self.assertEqual(code, 1)
        self.assertIn("Edición regional sin fichero", out)


class TestDetallesGuiV36Headless(ARQGenTestCase):
    """Contrato headless: tooltips y firma del método."""

    def test_tooltips_nuevos_registrados(self):
        from ui.help import TOOLTIPS
        for key in ("det_tipo", "det_png", "det_pdf", "bld_detalles"):
            self.assertIn(key, TOOLTIPS)
            self.assertTrue(TOOLTIPS[key].strip())

    def test_open_detalles_acepta_tipologia(self):
        from ui import app_window
        firma = inspect.signature(app_window.ARQGenWindow.open_detalles)
        self.assertIn("tipologia", firma.parameters)


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestDetallesGuiFlowV36(ARQGenTestCase):
    """Flujo real del navegador con filtro de tipología y PDF/PNG."""

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

    def test_filtro_de_tipologia_en_vivo(self):
        window = self.window
        self.assertEqual(len(window._det_tree.get_children()), 20)
        valores = window._det_tipologia["values"]
        self.assertEqual(len(valores), 11)   # (Todas) + 10 tipologías
        indice = list(valores).index(
            "Mampostería de bloque + losa de vigueta")
        window._det_tipologia.current(indice)
        window._det_run_search()
        rows = window._det_tree.get_children()
        self.assertEqual(len(rows), 9)
        self.assertIn("muros/muro_bloque_enlucido", rows)
        self.assertIn("recomendados", window._det_count.get())
        self.assertIn("Mampostería", window._det_count.get())
        # sin el filtro, toda la edición vuelve
        window._det_tipologia.current(0)
        window._det_run_search()
        self.assertEqual(len(window._det_tree.get_children()), 20)

    def test_tipologia_y_busqueda_combinadas(self):
        window = self.window
        indice = list(window._det_tipologia["values"]).index(
            "Muros de piedra")
        window._det_tipologia.current(indice)
        window._det_search.insert(0, "mampostería")
        window._det_run_search()
        rows = window._det_tree.get_children()
        self.assertEqual(rows, ("muros/muro_piedra_mamposteria",))

    def test_open_detalles_preselecciona_tipologia_del_asistente(self):
        window = self.window
        window.open_detalles(tipologia="Muros de piedra")
        window.update()
        self.assertEqual(window._det_tipologia.get(), "Muros de piedra")
        rows = window._det_tree.get_children()
        self.assertEqual(len(rows), 9)
        self.assertIn("muros/muro_piedra_mamposteria", rows)

    def test_exportacion_png_y_pdf_desde_la_gui(self):
        window = self.window
        window._det_tree.selection_set("muros/muro_bloque_enlucido")
        window._det_show()
        png = os.path.join(self.tmp, "gui_detalle.png")
        with patch("tkinter.filedialog.asksaveasfilename",
                   return_value=png):
            window._det_export_png()
        self.assertTrue(open(png, "rb").read().startswith(b"\x89PNG"))
        pdf = os.path.join(self.tmp, "gui_detalle.pdf")
        with patch("tkinter.filedialog.asksaveasfilename",
                   return_value=pdf):
            window._det_export_pdf()
        self.assertTrue(open(pdf, "rb").read().startswith(b"%PDF-1.4"))
        # el despachador del gancho SVG sigue vivo (contrato test_122)
        svg = os.path.join(self.tmp, "gui_detalle.svg")
        with patch("tkinter.filedialog.asksaveasfilename",
                   return_value=svg):
            window._det_export()
        self.assertTrue(open(svg, "rb").read().startswith(b"<?xml"))

    def test_exportar_png_sin_seleccion_avisa(self):
        window = self.window
        window._det_tree.selection_remove(*window._det_tree.selection())
        with patch("ui.app_window.messagebox.showinfo") as info:
            window._det_export_png()
        info.assert_called_once()


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestAsistenteVinculoDetalles(ARQGenTestCase):
    """El asistente abre la biblioteca pre-filtrada a su tipología."""

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

    def tearDown(self):
        for dialog in (getattr(self.window, "_det_dialog", None),
                       getattr(self.window, "_building_dialog", None)):
            try:
                if dialog is not None:
                    dialog.destroy()
            except Exception:  # noqa: BLE001 — ya cerrado
                pass
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_boton_abre_la_biblioteca_con_la_tipologia(self):
        from ui.building_wizard import CONSTRUCTION_TYPES
        window = self.window
        window.open_building_wizard()
        dialog = window._building_dialog
        self.assertTrue(callable(dialog._bld_open_detalles))
        # la tipología por defecto del asistente es la primera
        self.assertEqual(dialog._bld_data.construction_type,
                         CONSTRUCTION_TYPES[0])
        dialog._bld_open_detalles()
        window.update()
        navegador = window._det_dialog
        self.assertIsNotNone(navegador)
        self.assertEqual(window._det_tipologia.get(),
                         CONSTRUCTION_TYPES[0])
        rows = window._det_tree.get_children()
        self.assertEqual(len(rows), 9)
        self.assertIn("recomendados", window._det_count.get())

    def test_tipologia_cambiada_se_refleja_al_reabrir(self):
        from ui.building_wizard import CONSTRUCTION_TYPES
        window = self.window
        window.open_building_wizard()
        dialog = window._building_dialog
        dialog._bld_data.construction_type = CONSTRUCTION_TYPES[7]  # piedra
        dialog._bld_open_detalles()
        window.update()
        self.assertEqual(window._det_tipologia.get(), "Muros de piedra")
        self.assertIn("muros/muro_piedra_mamposteria",
                      window._det_tree.get_children())


if __name__ == "__main__":
    unittest.main()
