"""v3.8.0: layout restaurable + 3 ediciones regionales + PDF de documentos.

Tres líneas de futuro cerradas de una vez:

* LAYOUT — botón «Ver ▸ Restaurar disposición por defecto» (Ctrl+0) y
  doble clic sobre un separador que colapsa el panel contiguo:
  acelerador, menú, guía, mapa sash→panel con paneles ocultos, y el
  flujo real sobre la ventana (ocultar tres paneles a doble clic y
  volver al estado de fábrica con prefs coherentes).
* REGIONES — ediciones España (CTE), Perú (RNE E.030/E.060/E.070) y
  Chile (DS 61/NCh) que añaden y reemplazan detalles sobre la base
  sin corromperla jamás; búsqueda por norma, adaptación de los
  recomendados de la tipología y CLI punta a punta.
* DOCS-PDF — la memoria y el pliego (especificaciones) llevan la
  sección «Detalles constructivos recomendados» según la tipología del
  asistente, y cualquier documento sale en PDF A4 determinista
  (exporters.markdown_pdf), desde el servicio, la CLI y la GUI.
"""

from __future__ import annotations

import os
import time
import unittest
import zlib
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from tests.base import ARQGenTestCase

from domain import detalles as det
from ui import prefs as prefs_mod


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


def _pdf_streams(raw: bytes) -> str:
    """Concatena y descomprime todos los flujos de contenido del PDF."""
    partes = []
    for chunk in raw.split(b"stream\n")[1:]:
        cuerpo = chunk.rsplit(b"\nendstream", 1)[0]
        try:
            partes.append(zlib.decompress(cuerpo).decode("cp1252",
                                                         "replace"))
        except Exception:  # noqa: BLE001 — xref u otro binario
            continue
    return "\n".join(partes)


class TestLayoutRestaurable(ARQGenTestCase):
    """Ctrl+0 + doble clic en separadores (ventana real bajo Xvfb)."""

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

    def test_acelerador_y_metodo_existentes(self):
        from ui.app_window import ACCELERATORS
        self.assertEqual(ACCELERATORS.get("<Control-Key-0>"),
                         "reset_layout")
        self.assertIn("reset_layout", ACCELERATORS.values())

    def test_guia_enseña_doble_clic_y_restauracion(self):
        from ui import help as help_mod
        pasos = " ".join(texto for _t, texto in help_mod.GUIDE_STEPS)
        self.assertIn("doble clic sobre un separador", pasos)
        self.assertIn("Restaurar disposición por defecto", pasos)

    def _ventana(self):
        from ui import theme
        from ui.app_window import ARQGenWindow
        theme.set_mode("dark")
        self.context = self.demo_context()
        window = ARQGenWindow(self.context, self.application)
        window.geometry("1280x800")
        for _ in range(200):
            window.update()
            if window.winfo_ismapped() \
                    and window._paned.winfo_ismapped():
                break
            time.sleep(0.01)
        for _ in range(30):
            window.update()
            time.sleep(0.01)
        window._apply_saved_sashes()
        window.update()
        return window

    def test_mapa_sash_panel_paneles_visibles(self):
        window = self._ventana()
        try:
            self.assertEqual(window._sash_panel_map(window._paned),
                             {0: "explorer", 1: "props"})
            self.assertEqual(window._sash_panel_map(window._outer_paned),
                             {0: "bottom"})
            # con el explorador oculto, el sash restante colapsa props
            window.toggle_panel("explorer")
            window.update()
            self.assertEqual(window._sash_panel_map(window._paned),
                             {0: "props"})
        finally:
            window.destroy()
            self.context.close()

    def test_menu_ver_trae_restaurar(self):
        window = self._ventana()
        try:
            menubar = window.nametowidget(window.cget("menu"))
            etiquetas = {}
            for i in range(menubar.index("last") + 1):
                nombre = menubar.entrycget(i, "label")
                etiquetas[nombre] = window.nametowidget(menubar.menuname
                                                        if False else
                                                        menubar)
            ver = None
            for i in range(menubar.index("last") + 1):
                if menubar.entrycget(i, "label") == "Ver":
                    ver = menubar.nametowidget(menubar.entrycget(
                        i, "menu"))
            self.assertIsNotNone(ver)
            encontradas = [
                ver.entrycget(i, "label").startswith(
                    "Restaurar disposición por defecto")
                for i in range(ver.index("last") + 1)
                if ver.type(i) == "command"]
            self.assertTrue(any(encontradas))
        finally:
            window.destroy()
            self.context.close()

    def test_doble_clic_oculta_los_tres_paneles(self):
        window = self._ventana()
        try:
            def doble(paned, x, y):
                window._on_sash_double_click(
                    SimpleNamespace(widget=paned, x=x, y=y))
            panes0 = [str(p) for p in window._paned.panes()]
            self.assertIn(str(window._panel_frames["explorer"]), panes0)
            x0 = window._paned.sashpos(0) + 2
            doble(window._paned, x0, 100)
            window.update()
            panes1 = [str(p) for p in window._paned.panes()]
            self.assertNotIn(str(window._panel_frames["explorer"]),
                             panes1)
            # el sash que queda entre plano y propiedades colapsa props
            x1 = window._paned.sashpos(0) + 2
            doble(window._paned, x1, 100)
            window.update()
            self.assertEqual(len(window._paned.panes()), 1)
            # panel inferior (avisos): doble clic en el separador externo
            yo = window._outer_paned.sashpos(0) + 2
            doble(window._outer_paned, 400, yo)
            window.update()
            self.assertEqual(len(window._outer_paned.panes()), 1)
            self.assertFalse(window._panel_visible["bottom"])
            # fuera de sash (y=-5 sobre el borde) no rompe ni cambia
            doble(window._outer_paned, 400, 5)
            self.assertEqual(len(window._outer_paned.panes()), 1)
        finally:
            window.destroy()
            self.context.close()

    def test_reset_layout_devuelve_fabrica_y_persiste(self):
        window = self._ventana()
        try:
            window.toggle_panel("bottom")
            window.toggle_panel("props")
            window.update()
            window._paned.sashpos(0, 120)
            window.reset_layout()
            window.update()
            # los tres paneles vuelven a estar
            self.assertEqual(len(window._paned.panes()), 3)
            self.assertEqual(len(window._outer_paned.panes()), 2)
            for nombre in ("explorer", "props", "bottom"):
                self.assertTrue(window._panel_visible[nombre])
                self.assertTrue(window.prefs["panels"][nombre])
            # separadores de fábrica: 240 / resto / avisos arriba
            self.assertEqual(window._paned.sashpos(0), 240)
            self.assertGreaterEqual(window._outer_paned.sashpos(0), 300)
        finally:
            window.destroy()
            self.context.close()
        # lo visto tras el reset es lo que habrá en la próxima sesión
        prefs = prefs_mod.load_prefs()
        self.assertTrue(all(prefs["panels"].values()))

    def test_reset_no_toca_dialogs_ni_tema(self):
        window = self._ventana()
        try:
            window.prefs["dialogs"]["detalles"] = "1140x780+10+10"
            window.prefs["theme"] = "light"
            window.reset_layout()
            self.assertEqual(window.prefs["dialogs"]["detalles"],
                             "1140x780+10+10")
            self.assertEqual(window.prefs["theme"], "light")
        finally:
            window.destroy()
            self.context.close()


class TestEdicionesEspanaPeruChile(ARQGenTestCase):
    """Los tres JSON nuevos sobre la biblioteca universal."""

    def setUp(self):
        super().setUp()
        det.reset_registry()

    def tearDown(self):
        det.reset_registry()
        super().tearDown()

    def test_hay_siete_ediciones_instaladas(self):
        registro = det.get_registry()
        codigos = {r["codigo"] for r in registro.available_regions()}
        self.assertTrue({"mexico", "colombia", "argentina", "cuba"}
                        <= codigos)
        self.assertTrue({"espana", "peru", "chile"} <= codigos)
        self.assertEqual(len(codigos), 7)

    def test_espana_reemplaza_y_anade(self):
        registro = det.get_registry()
        self.assertTrue(registro.set_region("espana"))
        self.assertEqual(registro.region_name, "España")
        regionales = [d for d in registro.list_details() if d.regional]
        self.assertEqual(len(regionales), 6)
        muro = registro.get("muros/muro_ladrillo_fabrica")
        self.assertTrue(muro.regional)
        self.assertEqual(round(muro.espesor_total_mm), 260)
        forjado = registro.get("entrepisos/losa_vigueta_bovedilla")
        self.assertTrue(forjado.regional)
        self.assertEqual(round(forjado.espesor_total_mm), 315)
        for nuevo in ("muros/sate_estuco_aislado",
                      "carpinteria/ventana_pvc_rpt",
                      "cubiertas/cubierta_plana_losa"):
            self.assertIsNotNone(registro.get(nuevo))
        self.assertEqual(round(registro.get(
            "cubiertas/cubierta_plana_losa").espesor_total_mm), 439)

    def test_peru_reemplaza_y_anade(self):
        registro = det.get_registry()
        self.assertTrue(registro.set_region("peru"))
        regionales = [d for d in registro.list_details() if d.regional]
        self.assertEqual(len(regionales), 5)
        muro = registro.get("muros/muro_bloque_enlucido")
        self.assertIn("E.070", muro.nombre)
        self.assertEqual(round(muro.espesor_total_mm), 160)
        self.assertIn("tejar",
                      registro.get(
                          "entrepisos/losa_vigueta_bovedilla").resumen)
        self.assertEqual(round(registro.get(
            "cimentaciones/viga_sobrecimiento_e070").espesor_total_mm),
            600)
        self.assertEqual(round(registro.get(
            "cubiertas/cubierta_teja_andina").espesor_total_mm), 145)

    def test_chile_reemplaza_y_anade(self):
        registro = det.get_registry()
        self.assertTrue(registro.set_region("chile"))
        regionales = [d for d in registro.list_details() if d.regional]
        self.assertEqual(len(regionales), 5)
        corte = registro.get("muros/muro_corte_hormigon")
        self.assertEqual(round(corte.espesor_total_mm), 200)
        self.assertIn("NCh433", corte.norma)
        madera = registro.get("entrepisos/entrepiso_madera")
        self.assertIn("NCh1198", madera.nombre)
        self.assertEqual(round(registro.get(
            "cimentaciones/cadena_desplante_nch").espesor_total_mm), 570)
        self.assertIn("volcometa",
                      registro.get(
                          "cubiertas/cubierta_chapa_metalica").resumen)

    def test_la_base_nunca_se_corrompe(self):
        registro = det.get_registry()
        # retrato del estado original ANTES de tocar regiones
        original = {d.id: round(d.espesor_total_mm)
                    for d in registro.list_details()}
        for codigo in ("espana", "peru", "chile"):
            registro.set_region(codigo)
        registro.reset_region()
        self.assertEqual(len(registro), 20)
        for detalle in registro.list_details():
            self.assertFalse(detalle.regional)
            self.assertEqual(round(detalle.espesor_total_mm),
                             original[detalle.id], detalle.id)

    def test_busqueda_por_norma_y_tag(self):
        registro = det.get_registry()
        registro.set_region("espana")
        self.assertTrue(any("SATE" in d.nombre
                            for d in registro.search("sate")))
        registro.set_region("peru")
        self.assertTrue(any("E.070" in d.norma
                            for d in registro.search("E070")))
        registro.set_region("chile")
        self.assertTrue(any("NCh433" in d.norma
                            for d in registro.search("nch433")))

    def test_recomendados_adaptados_a_la_edicion(self):
        registro = det.get_registry()
        tipo = "Mampostería de bloque + losa de vigueta"
        base_ids = [d.id for d in det.detalles_para_tipologia(
            registro, tipo)]
        registro.set_region("peru")
        peru_ids = [d.id for d in det.detalles_para_tipologia(
            registro, tipo)]
        registro.set_region("chile")
        chile_ids = [d.id for d in det.detalles_para_tipologia(
            registro, tipo)]
        registro.reset_region()
        # mismos ids en base y ediciones (reemplazo 1:1, sin retirar)
        self.assertEqual(base_ids, peru_ids)
        self.assertEqual(base_ids, chile_ids)
        registro.set_region("peru")
        adaptados = det.detalles_para_tipologia(registro, tipo)
        self.assertTrue(all(d.regional
                            for d in adaptados
                            if d.id in ("muros/muro_bloque_enlucido",
                                        "entrepisos/losa_vigueta_bovedilla",
                                        "cubiertas/cubierta_plana_losa")))
        registro.reset_region()

    def test_cli_regiones_y_lista(self):
        log = os.path.join(self.tmp, "logs")
        code, out = run_cli(["detalles", "regiones"], log)
        self.assertEqual(code, 0)
        for pais in ("España", "Perú", "Chile"):
            self.assertIn(pais, out)
        code, out = run_cli(
            ["detalles", "list", "--region", "espana", "--buscar",
             "SATE"], log)
        self.assertEqual(code, 0)
        self.assertIn("sate_estuco_aislado", out)

    def test_cli_ver_detalle_regional(self):
        log = os.path.join(self.tmp, "logs")
        code, out = run_cli(
            ["detalles", "ver", "muros/muro_corte_hormigon",
             "--region", "chile"], log)
        self.assertEqual(code, 0)
        self.assertIn("Muro de corte", out)
        self.assertIn("NCh433", out)


class _ProyectoConEdificio(ARQGenTestCase):
    """Base con un proyecto real generado por el asistente."""

    TIPologia = "Mampostería de bloque + losa de vigueta"

    def _proyecto(self, nombre="casa.arqgen"):
        from ui import building_wizard as bw
        from ui.building_wizard import (BuildingWizardData, LevelSpec)
        ctx = self.application.create_project(
            self.project_path(nombre), name="Casa Detalles")
        data = BuildingWizardData(name="Casa Detalles")
        data.construction_type = self.TIPologia
        data.levels = [LevelSpec(name="Planta Baja", height_m=3.0)]
        data.rooms = bw.preset_rooms("Vivienda", "Planta Baja")
        bw.apply_plan(data, ctx)
        return ctx


class TestDetallesEnDocumentos(_ProyectoConEdificio):
    """Memoria y pliego con la sección de detalles recomendados."""

    def setUp(self):
        super().setUp()
        det.reset_registry()

    def tearDown(self):
        det.reset_registry()
        super().tearDown()

    def _servicio(self, ctx):
        from services.documentation_service import DocumentationService
        return DocumentationService(ctx)

    def test_tipologia_leida_del_asistente(self):
        ctx = self._proyecto()
        try:
            self.assertEqual(
                self._servicio(ctx).tipologia_proyecto(), self.TIPologia)
        finally:
            ctx.close()

    def test_tipologia_vacia_sin_edificio(self):
        ctx = self.demo_context()
        try:
            servicio = self._servicio(ctx)
            self.assertEqual(servicio.tipologia_proyecto(), "")
            self.assertEqual(servicio.detalles_recomendados(), [])
            memoria = servicio.generate_memoria()
            self.assertNotIn("Detalles constructivos recomendados",
                             memoria)
        finally:
            ctx.close()

    def test_detalles_recomendados_filas_completas(self):
        ctx = self._proyecto()
        try:
            filas = self._servicio(ctx).detalles_recomendados()
            self.assertEqual(len(filas), 9)
            primero = filas[0]
            for clave in ("detalle", "nombre", "categoria",
                          "espesor_mm", "norma"):
                self.assertIn(clave, primero)
            self.assertEqual(primero["detalle"],
                             "cimentaciones/zapata_corrida_ha")
            self.assertTrue(all(isinstance(f["espesor_mm"], int)
                                for f in filas))
        finally:
            ctx.close()

    def test_memoria_lleva_seccion_y_es_determinista(self):
        ctx = self._proyecto()
        try:
            servicio = self._servicio(ctx)
            memoria_a = servicio.generate_memoria()
            memoria_b = servicio.generate_memoria()
            self.assertEqual(memoria_a, memoria_b)
            self.assertIn("Detalles constructivos recomendados",
                          memoria_a)
            self.assertIn(self.TIPologia, memoria_a)
            self.assertIn("cimentaciones/zapata_corrida_ha", memoria_a)
            self.assertIn("biblioteca universal (sin edición regional "
                          "activa)", memoria_a)
        finally:
            ctx.close()

    def test_memoria_adaptada_a_la_edicion_activa(self):
        ctx = self._proyecto()
        try:
            servicio = self._servicio(ctx)
            det.get_registry().set_region("peru")
            memoria = servicio.generate_memoria()
            self.assertIn("edición regional activa: Perú", memoria)
            self.assertIn("E.070", memoria)
            det.get_registry().reset_region()
        finally:
            ctx.close()

    def test_specs_lleva_seccion_y_cuadros_no(self):
        ctx = self._proyecto()
        try:
            servicio = self._servicio(ctx)
            specs = servicio.generate_especificaciones()
            self.assertIn("Detalles constructivos recomendados", specs)
            self.assertIn("cimentaciones/zapata_corrida_ha", specs)
            for documento in (servicio.generate_cuadros(),
                              servicio.generate_listados()):
                self.assertNotIn("Detalles constructivos recomendados",
                                 documento)
        finally:
            ctx.close()

    def test_export_document_pdf_valido(self):
        ctx = self._proyecto()
        try:
            servicio = self._servicio(ctx)
            memoria = servicio.generate_memoria()
            pdf = os.path.join(self.tmp, "memoria.pdf")
            servicio.export_document(memoria, pdf, "pdf")
            raw = open(pdf, "rb").read()
            self.assertTrue(raw.startswith(b"%PDF-1.4"))
            texto = _pdf_streams(raw)
            self.assertIn("Detalles constructivos recomendados", texto)
            self.assertIn("zapata_corrida_ha", texto)
            # determinista dentro del mismo día
            pdf2 = os.path.join(self.tmp, "memoria_b.pdf")
            servicio.export_document(memoria, pdf2, "pdf")
            self.assertEqual(open(pdf, "rb").read(),
                             open(pdf2, "rb").read())
        finally:
            ctx.close()

    def test_cli_docs_memoria_pdf_punta_a_punta(self):
        ctx = self._proyecto("casa_cli.arqgen")
        ctx.close()
        pdf = os.path.join(self.tmp, "memoria_cli.pdf")
        code, out = run_cli(["docs", "memoria",
                             self.project_path("casa_cli.arqgen"),
                             "--out", pdf], os.path.join(self.tmp,
                                                         "logs"))
        self.assertEqual(code, 0)
        self.assertIn("Documento escrito", out)
        raw = open(pdf, "rb").read()
        self.assertTrue(raw.startswith(b"%PDF-1.4"))
        self.assertIn("zapata_corrida_ha", _pdf_streams(raw))


class TestExportadorMarkdownPdf(ARQGenTestCase):
    """exporters.markdown_pdf: markdown ARQ GEN → PDF A4."""

    def _markdown(self):
        from engines.documentation_engine import (format_table,
                                                 render_markdown_document)
        return render_markdown_document("Prueba — Casa Uno", [
            ("Objeto", "Documento de **prueba** con símbolos: 3 m², "
                       "≥ 5 kg, viga → muro."),
            ("Niveles", "- **Planta Baja**: cota +0.00 m, altura 3.00 m\n"
                        "- **Piso 1**: cota +3.00 m"),
            ("Cuadro", format_table(
                [{"name": "Sala", "area": 12.5},
                 {"name": "Cocina", "area": 8.0}], ["name", "area"])),
        ])

    def test_pdf_valido_con_contenido(self):
        from exporters.markdown_pdf import export_markdown_pdf
        pdf = os.path.join(self.tmp, "doc.pdf")
        export_markdown_pdf(self._markdown(), pdf,
                            subtitle="edición de prueba")
        raw = open(pdf, "rb").read()
        self.assertTrue(raw.startswith(b"%PDF-1.4"))
        texto = _pdf_streams(raw)
        self.assertIn("Prueba", texto)
        self.assertIn("• Planta Baja", texto)
        self.assertIn("Sala", texto)

    def test_determinista_mismo_dia(self):
        from exporters.markdown_pdf import export_markdown_pdf
        pdf_a = os.path.join(self.tmp, "a.pdf")
        pdf_b = os.path.join(self.tmp, "b.pdf")
        export_markdown_pdf(self._markdown(), pdf_a)
        export_markdown_pdf(self._markdown(), pdf_b)
        self.assertEqual(open(pdf_a, "rb").read(),
                         open(pdf_b, "rb").read())

    def test_vacio_rechazado_con_codigo(self):
        from core.errors import ExportError
        from exporters.markdown_pdf import export_markdown_pdf
        with self.assertRaises(ExportError) as ctx:
            export_markdown_pdf("   \n  ", os.path.join(self.tmp,
                                                        "x.pdf"))
        self.assertEqual(ctx.exception.code, "ARQ-EXP-072")

    def test_tabla_ancha_y_celdas_largas_no_rompen(self):
        from exporters.markdown_pdf import export_markdown_pdf
        md = ("# Ancho\n\n| columna_muy_larga | otra | c |\n"
              "| - | - | - |\n")
        md += "| " + "x" * 220 + " | 12.5 | 3 |\n"
        pdf = os.path.join(self.tmp, "ancho.pdf")
        export_markdown_pdf(md, pdf)
        self.assertTrue(open(pdf, "rb").read(8) == b"%PDF-1.4")

    def test_encabezados_y_negritas_se_limpian(self):
        from exporters.markdown_pdf import export_markdown_pdf
        md = "# Título con **negrita**\n\n## Sección `con` código"
        pdf = os.path.join(self.tmp, "limpio.pdf")
        export_markdown_pdf(md, pdf)
        texto = _pdf_streams(open(pdf, "rb").read())
        self.assertIn("Título con negrita", texto)
        self.assertNotIn("**", texto)
        self.assertNotIn("`", texto)


class TestGuiInformePdf(ARQGenTestCase):
    """La GUI exporta el informe también en PDF (menú Herramientas)."""

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

    @unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
    def test_informe_pdf_desde_la_ventana(self):
        import tkinter as tk
        from ui import app_window, theme
        theme.set_mode("dark")
        ctx = self.demo_context()
        window = app_window.ARQGenWindow(ctx, self.application)
        try:
            window.update()
            pdf = os.path.join(self.tmp, "informe.pdf")
            with patch.object(app_window.filedialog,
                              "asksaveasfilename", return_value=pdf):
                window.export_report("pdf")
            raw = open(pdf, "rb").read()
            self.assertTrue(raw.startswith(b"%PDF-1.4"))
            self.assertIn("Informe", _pdf_streams(raw))
            # el menú Herramientas trae la entrada PDF
            menubar = window.nametowidget(window.cget("menu"))
            herramientas = None
            for i in range(menubar.index("last") + 1):
                if menubar.entrycget(i, "label") == "Herramientas":
                    herramientas = menubar.nametowidget(
                        menubar.entrycget(i, "menu"))
            etiquetas = [herramientas.entrycget(i, "label")
                         for i in range(herramientas.index("last") + 1)
                         if herramientas.type(i) == "command"]
            self.assertTrue(any(e.startswith(
                "Informe descriptivo (PDF)") for e in etiquetas))
            self.assertTrue(any(e.startswith(
                "Informe descriptivo (Markdown)") for e in etiquetas))
        finally:
            window.destroy()
            ctx.close()


if __name__ == "__main__":
    unittest.main()
