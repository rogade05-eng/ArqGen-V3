"""v3.21.0 — PASILLOS POR USO HOSPITALARIO (DNA), EQUIPOS MÉDICOS EN
EL PRESUPUESTO VIVO y FICHA IMPRIMIBLE DEL LOCAL.

Lo pedido («posibles colas» de la v3.20.0):

* Pasillos por locales: el ancho del pasillo del asistente ya no mira
  solo el uso social — el DNA de cada LOCAL del programa trae su
  «pasillo_m» (camillas 2,40 m; carros de morgue/almacén 2,00 m;
  laboratorio y desechos 1,80 m; nodo 1,50 m) y el pasillo sube al
  máximo que pida el local más exigente, citándolo en el aviso.
* Presupuesto vivo de las especialidades: los locales de salud
  aportan sus APARATOS a la categoría «Equipos» con precios de
  REFERENCIA (el catálogo PRECONS III no publica tomógrafos ni arcos
  C): fila con código vacío + precio en la fila, la calidad de
  acabados no la toca y el total vive como el resto.
* Ficha imprimible del local: export_ficha_local_pdf reúne identidad,
  DNA (ficha técnica), vanos, mobiliario, instalaciones, PLANTA
  dibujada (muros recortados al local, vanos con arco de giro) y
  diagnóstico — el asistente de local, en papel.

Cobertura: DNA pasillo_m, sugerencia por locales (culpable citado),
apply_neufert_defaults que solo sube, avisos que nombran al local
culpable, vivienda intacta; equipos por tipo (tomógrafo, arco C,
cabina de bioseguridad…), estimación con categoría «Equipos»,
invariancia ante calidad, vivienda sin equipos; recorte de muros por
aristas (_tramos_en_aristas), geometria_local con vanos globales, PDF
válido y cp1252; GUI: botón «Ficha PDF...» del asistente que exporta.
"""

from __future__ import annotations

import os
import unittest

from tests.base import ARQGenTestCase

from ui import building_wizard as bw
from ui import variant_budget as vb


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


# -- pasillos por uso hospitalario --------------------------------------------

class TestPasillosPorLocales(ARQGenTestCase):

    def test_dna_trae_pasillo_m_de_las_especialidades(self):
        # camillas: 2,40 m — carros: 2,00 m — laboratorio: 1,80 — nodo: 1,50
        self.assertEqual(bw.pasillo_minimo_de_uso("CT_ROOM"), 2.4)
        self.assertEqual(bw.pasillo_minimo_de_uso("ICU"), 2.4)
        self.assertEqual(bw.pasillo_minimo_de_uso("OPERATING_ROOM"), 2.4)
        self.assertEqual(bw.pasillo_minimo_de_uso("MORGUE"), 2.0)
        self.assertEqual(bw.pasillo_minimo_de_uso("WAREHOUSE"), 2.0)
        self.assertEqual(bw.pasillo_minimo_de_uso("MICROBIOLOGY_LAB"), 1.8)
        self.assertEqual(bw.pasillo_minimo_de_uso("WASTE_ROOM"), 1.8)
        self.assertEqual(bw.pasillo_minimo_de_uso("SERVER_ROOM"), 1.5)
        # los usos domésticos NO piden pasillo propio: la vivienda igual
        self.assertIsNone(bw.pasillo_minimo_de_uso("ROOM"))
        self.assertIsNone(bw.pasillo_minimo_de_uso("KITCHEN"))
        self.assertIsNone(bw.pasillo_minimo_de_uso("BEDROOM"))

    def test_sugerencia_por_locales_con_culpable(self):
        # el uso base de oficina pide menos que la camilla del TAC
        ancho, culpable = bw.suggested_corridor_width_for_rooms(
            "Oficina", ["OFFICE", "OFFICE", "CT_ROOM"])
        self.assertEqual((ancho, culpable), (2.4, "CT_ROOM"))
        # sin locales exigentes manda el uso y no hay culpable
        ancho, culpable = bw.suggested_corridor_width_for_rooms(
            "Oficina", ["OFFICE", "WAITING_ROOM"])
        self.assertEqual(culpable, "")
        # hospital: el uso ya pide 2,40 — ningún local lo supera
        ancho, culpable = bw.suggested_corridor_width_for_rooms(
            "Hospital", ["MORGUE", "WARD", "ICU"])
        self.assertEqual((ancho, culpable), (2.4, ""))

    def test_apply_neufert_defaults_sube_por_locales(self):
        data = bw.BuildingWizardData(name="Mixto")
        data.usage_type = "Oficina"
        data.rooms = [
            bw.RoomSpec(name="Despacho", space_type="OFFICE",
                        width_m=3.0, depth_m=4.0),
            bw.RoomSpec(name="TAC", space_type="CT_ROOM",
                        width_m=7.0, depth_m=5.0),
        ]
        data.corridor_enabled = True
        data.corridor_width_m = 1.5
        cambios = bw.apply_neufert_defaults(data)
        self.assertIn("pasillo a 2.40 m", cambios)
        self.assertEqual(data.corridor_width_m, 2.4)
        # SOLO SUBE: un pasillo ya más ancho se respeta
        data.corridor_width_m = 3.0
        cambios = bw.apply_neufert_defaults(data)
        self.assertEqual(data.corridor_width_m, 3.0)
        self.assertNotIn("pasillo a 2.40 m", cambios)

    def test_aviso_nombra_al_local_culpable(self):
        data = bw.BuildingWizardData(name="Mixto")
        data.usage_type = "Oficina"
        data.rooms = [
            bw.RoomSpec(name="Despacho", space_type="OFFICE",
                        width_m=3.0, depth_m=4.0),
            bw.RoomSpec(name="TAC", space_type="CT_ROOM",
                        width_m=7.0, depth_m=5.0),
        ]
        data.corridor_enabled = True
        data.corridor_width_m = 1.5
        avisos = bw.neufert_advisories(data)
        pasillo = [a for a in avisos if a.startswith("Pasillo")]
        self.assertEqual(len(pasillo), 1)
        self.assertIn("2.40 m", pasillo[0])
        self.assertIn("Tomografía", pasillo[0])  # DNA name_es del TAC
        # y el texto completo sobrevive a cp1252 (consola de Windows)
        for aviso in avisos:
            aviso.encode("cp1252")

    def test_vivienda_sin_locales_de_camilla_no_cambia(self):
        data = bw.BuildingWizardData(name="Casa")
        data.usage_type = "Vivienda"
        data.rooms = [
            bw.RoomSpec(name="Sala", space_type="ROOM", width_m=4.0,
                        depth_m=5.0),
            bw.RoomSpec(name="Cocina", space_type="KITCHEN", width_m=3.0,
                        depth_m=2.5),
        ]
        data.corridor_enabled = True
        data.corridor_width_m = 1.2
        cambios = bw.apply_neufert_defaults(data)
        self.assertNotIn("pasillo a 2.40 m", cambios)
        self.assertEqual(data.corridor_width_m, 1.2)


# -- presupuesto vivo: equipos de las especialidades ----------------------------

def _data_hospital() -> bw.BuildingWizardData:
    data = bw.BuildingWizardData(name="Hospital de prueba")
    data.usage_type = "Hospital"
    bw.apply_usage_program(data)
    return data


def _data_vivienda() -> bw.BuildingWizardData:
    data = bw.BuildingWizardData(name="Casa")
    data.usage_type = "Vivienda"
    data.rooms = [
        bw.RoomSpec(name="Sala", space_type="ROOM", width_m=4.0,
                    depth_m=5.0),
        bw.RoomSpec(name="Cocina", space_type="KITCHEN", width_m=3.0,
                    depth_m=2.5),
        bw.RoomSpec(name="Baño", space_type="BATHROOM", width_m=1.8,
                    depth_m=2.0, with_window=False),
    ]
    return data


class TestEquiposEnPresupuestoVivo(ARQGenTestCase):

    @classmethod
    def setUpClass(cls):
        from app.paths import resource_path
        from engines.precons_engine import PreconsRuleset
        cls.ruleset = PreconsRuleset.from_file(resource_path(
            "rulesets", "precons_iii_rospres_330.json"))
        cls.hospital = _data_hospital()
        cls.variante_h = bw.generate_variants(cls.hospital)[0]
        cls.vivienda = _data_vivienda()
        cls.variante_v = bw.generate_variants(cls.vivienda)[0]

    def test_tabla_de_equipos_tiene_precios_de_referencia(self):
        for space_type, aparatos in vb.EQUIPOS_POR_USO.items():
            self.assertTrue(aparatos, f"{space_type} sin aparatos")
            for concepto, unidad, precio in aparatos:
                self.assertTrue(concepto)
                self.assertIn(unidad, ("u",))
                self.assertGreater(precio, 0.0,
                                   f"{concepto} sin precio de referencia")

    def test_hospital_factura_tomografo_y_arco_c(self):
        filas = vb.variant_takeoff(self.hospital, self.variante_h)
        equipos = [f for f in filas if f["category"] == "Equipos"]
        self.assertTrue(equipos, "el hospital aporta aparatos")
        conceptos = {f["concept"] for f in equipos}
        self.assertIn("Tomógrafo helicoidal", conceptos)
        self.assertIn("Equipo de fluoroscopia con arco C", conceptos)
        self.assertIn("Cabina de bioseguridad clase II", conceptos)
        self.assertIn("Cámara frigorífica de cadáveres (3 cuerpos)",
                      conceptos)
        # cada fila de equipo viaja sin código y con su precio de ref.
        for fila in equipos:
            self.assertEqual(fila["code"], "")
            self.assertGreater(fila.get("unit_price", 0.0), 0.0)
            self.assertEqual(fila.get("fuente"), "referencia")
        # los van por unidad de local: 2 quirófanos -> 2 lámparas
        lamparas = [f for f in equipos
                    if f["concept"] == "Lámpara escialítica de techo"]
        self.assertEqual(len(lamparas), 1)
        self.assertGreaterEqual(lamparas[0]["quantity"], 2.0)

    def test_estimacion_con_categoria_equipos(self):
        costo = vb.estimate_variant_cost(self.hospital, self.variante_h,
                                         self.ruleset)
        equipos = costo.categories.get("Equipos", 0.0)
        self.assertGreater(equipos, 0.0)
        # el tomógrafo (1 u) está íntegro en el total: costo directo =
        # suma de importes y los equipos entran con su precio de ref.
        filas_eq = [r for r in costo.rows if r["category"] == "Equipos"]
        tomografo = [r for r in filas_eq
                     if r["concept"] == "Tomógrafo helicoidal"]
        self.assertEqual(len(tomografo), 1)
        self.assertGreaterEqual(tomografo[0]["amount"], 2_400_000.0)
        self.assertEqual(tomografo[0]["fuente"], "referencia")
        # determinismo
        costo2 = vb.estimate_variant_cost(self.hospital,
                                          self.variante_h, self.ruleset)
        self.assertEqual(costo2.total, costo.total)

    def test_la_calidad_de_acabados_no_toca_los_equipos(self):
        eco = vb.estimate_variant_cost(self.hospital, self.variante_h,
                                       self.ruleset, calidad="Económica")
        pre = vb.estimate_variant_cost(self.hospital, self.variante_h,
                                       self.ruleset, calidad="Premium")
        self.assertGreater(eco.categories.get("Equipos", 0.0), 0.0)
        self.assertEqual(eco.categories.get("Equipos"),
                         pre.categories.get("Equipos"))
        # mientras el resto de la obra SÍ sube con la calidad
        self.assertGreater(pre.direct, eco.direct)

    def test_vivienda_no_factura_equipos(self):
        filas = vb.variant_takeoff(self.vivienda, self.variante_v)
        self.assertEqual([f for f in filas
                          if f["category"] == "Equipos"], [])


# -- ficha imprimible del local ---------------------------------------------------

class TestFichaImprimible(ARQGenTestCase):

    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def _sala(self):
        return next(e for e in self.ctx.architecture.list(
            "SPACE", self.ctx.project.id) if (e.name or "") == "Sala")

    def test_tramos_en_aristas_recorta_muros_largos(self):
        from ui import cad_tools as cad
        # muro de 10 m sobre una arista de 6 m: recorta a 6 m
        aristas = [((0.0, 2.0), (6.0, 2.0))]
        tramos = cad._tramos_en_aristas((-2.0, 2.0), (8.0, 2.0), aristas)
        self.assertEqual(len(tramos), 1)
        (q1, q2) = tramos[0]
        self.assertAlmostEqual(q1[0], 0.0, places=6)
        self.assertAlmostEqual(q2[0], 6.0, places=6)
        # un muro perpendicular no recorta nada
        self.assertEqual(cad._tramos_en_aristas(
            (1.0, 0.0), (1.0, 8.0), aristas), [])
        # un muro paralelo a 20 cm no es arista
        self.assertEqual(cad._tramos_en_aristas(
            (0.0, 2.2), (6.0, 2.2), aristas), [])

    def test_geometria_local_recorta_muros_y_ubica_vanos(self):
        from ui.editor_espacios import geometria_local
        sala = self._sala()
        geo = geometria_local(self.ctx, sala.code)
        self.assertGreaterEqual(len(geo["boundary"]), 4)
        # los muros recortados cubren todo el perímetro del local
        from ui import cad_tools as cad
        perimetro = sum(cad._dist(a, b)
                        for a, b in cad._aristas(sala.boundary))
        cubierto = sum(cad._dist(m["start"], m["end"])
                       for m in geo["muros"])
        self.assertGreaterEqual(cubierto, perimetro - 4e-3)
        # los vanos del local vienen con puntos globales y muro
        self.assertTrue(geo["vanos"])
        for vano in geo["vanos"]:
            self.assertIn(vano["kind"], ("DOOR", "WINDOW", "OPENING"))
            self.assertGreater(cad._dist(vano["p1"], vano["p2"]),
                               1e-6)
            self.assertTrue(vano.get("muro"))
        # la sala del demo tiene su ventana de verdad
        self.assertIn("WINDOW", {v["kind"] for v in geo["vanos"]})

    def test_resumen_completo_trae_dna_tecnico(self):
        from ui.editor_espacios import resumen_completo
        datos = resumen_completo(self.ctx, self._sala().code)
        self.assertIn("dna_tecnico", datos)
        self.assertIn("neufert", datos["dna_tecnico"])
        # el texto de diagnóstico sigue siendo cp1252-seguro
        from ui.editor_espacios import texto_resumen_completo
        texto_resumen_completo(datos).encode("cp1252")

    def test_export_produce_pdf_valido(self):
        from exporters.ficha_local import export_ficha_local_pdf
        ruta = os.path.join(self.tmp, "ficha_sala.pdf")
        salida = export_ficha_local_pdf(self.ctx, self._sala().code, ruta)
        self.assertEqual(salida, ruta)
        self.assertTrue(os.path.exists(ruta))
        with open(ruta, "rb") as fh:
            blob = fh.read()
        self.assertTrue(blob.startswith(b"%PDF"))
        self.assertGreater(len(blob), 2000)
        # la ficha de un local sin vanos también sale limpia
        bano = next(e for e in self.ctx.architecture.list(
            "SPACE", self.ctx.project.id)
            if not e.name or "Bano" in (e.name or ""))
        ruta2 = os.path.join(self.tmp, "ficha_bano.pdf")
        export_ficha_local_pdf(self.ctx, bano.code, ruta2)
        with open(ruta2, "rb") as fh:
            self.assertTrue(fh.read(4).startswith(b"%PDF"))


# -- GUI: el botón «Ficha PDF...» del asistente -----------------------------------

@unittest.skipUnless(DISPLAY, "sin display: pruebas GUI bajo Xvfb")
class TestDialogoFichaLocal(ARQGenTestCase):

    def setUp(self):
        super().setUp()
        self.ctx = self.demo_context()

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.ctx, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def test_asistente_trae_boton_ficha_y_exporta(self):
        import tkinter as tk
        from tkinter import ttk
        from ui import help
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        # el botón «Ficha PDF...» existe dentro del diálogo (recursivo)
        encontrados = []

        def _buscar(widget):
            for hijo in widget.winfo_children():
                if isinstance(hijo, ttk.Button) \
                        and str(hijo.cget("text")) == "Ficha PDF...":
                    encontrados.append(hijo)
                _buscar(hijo)

        _buscar(dialogo)
        self.assertEqual(len(encontrados), 1)
        # y su tooltip está documentado
        self.assertIn("editor_local_ficha", help.TOOLTIPS)
        self.assertIn("FICHA IMPRIMIBLE",
                      help.TOOLTIPS["editor_local_ficha"])
        _ = tk
        # exportar con el flujo real del botón (filedialog parcheado)
        from ui import app_window as aw
        ruta = os.path.join(self.tmp, "ficha_gui.pdf")
        original = aw.filedialog.asksaveasfilename
        aw.filedialog.asksaveasfilename = (
            lambda **kw: ruta)
        try:
            window._ficha_local_pdf(
                dialogo,
                (lambda: next(e for e in self.ctx.architecture.list(
                    "SPACE", self.ctx.project.id)
                    if (e.name or "") == "Sala").id))
        finally:
            aw.filedialog.asksaveasfilename = original
        self.assertTrue(os.path.exists(ruta))
        with open(ruta, "rb") as fh:
            self.assertEqual(fh.read(4), b"%PDF")
        dialogo.destroy()

    def test_ficha_sin_local_avisa_amable(self):
        from ui import app_window as aw
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        avisos = []
        original = aw.messagebox.showinfo
        aw.messagebox.showinfo = (
            lambda *a, **kw: avisos.append(a))
        try:
            window._ficha_local_pdf(dialogo, lambda: None)
        finally:
            aw.messagebox.showinfo = original
        self.assertEqual(len(avisos), 1)
        self.assertIn("Ficha de local", avisos[0][0])
        dialogo.destroy()


if __name__ == "__main__":
    unittest.main()
