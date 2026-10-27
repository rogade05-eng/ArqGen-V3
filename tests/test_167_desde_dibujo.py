"""DESDE DIBUJO: GENERACIÓN INVERSA v3.34.0 (domain/desde_dibujo.py).

Partir de un dibujo del área o espacio (DXF, dibujado a dos clics o
rectángulo) y generar la edificación o el servicio completo: el
asistente infiere forma y medidas, arma el programa por tipo y uso
social, decide si los locales entran en el área suministrada y
sugiere el crecimiento en altura (otros niveles) con el recinto de
la escalera según Blondel.
"""

from __future__ import annotations

import os
import unittest

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from domain import servicios_engine as eng
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

RECT = [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0)]
L_MUESCA = [(0.0, 0.0), (24.0, 0.0), (24.0, 14.0), (12.0, 14.0),
            (12.0, 8.0), (0.0, 8.0)]


def _codigo(exc: DomainError) -> str:
    return getattr(exc, "code", "")


# ---------------------------------------------------------------------------
# 1) INFERIR forma y medidas del contorno
# ---------------------------------------------------------------------------

class TestInferencia(unittest.TestCase):
    """El dibujo se convierte en medidas honestas."""

    def test_rectangulo_alineado_12x8(self):
        f = dd.inferir(RECT)
        self.assertEqual(f["forma"], "rectangulo")
        self.assertTrue(f["alineado"])
        self.assertAlmostEqual(f["area_m2"], 96.0, places=3)
        self.assertAlmostEqual(f["perimetro_m"], 40.0, places=3)
        self.assertAlmostEqual(f["ancho_m"], 12.0, places=6)
        self.assertAlmostEqual(f["fondo_m"], 8.0, places=6)
        self.assertEqual(len(f["vertices"]), 4)
        self.assertAlmostEqual(f["centroide"][0], 6.0, places=6)
        self.assertAlmostEqual(f["centroide"][1], 4.0, places=6)

    def test_sentido_horario_se_normaliza_igual(self):
        a = dd.inferir(RECT)
        b = dd.inferir(list(reversed(RECT)))
        self.assertEqual(a["vertices"], b["vertices"])
        self.assertEqual(a["area_m2"], b["area_m2"])

    def test_repetidos_y_cierre_duplicado_se_limpian(self):
        # doble clic en el mismo vértice + cierre explícito con el
        # primero (lo que sale de un DXF o de dibujar a dos clics)
        sucio = RECT[:3] + [(12.0, 8.0), RECT[3], RECT[0]]
        f = dd.inferir(sucio)
        self.assertEqual(len(f["vertices"]), 4)
        self.assertAlmostEqual(f["area_m2"], 96.0, places=3)

    def test_menos_de_tres_vertices_error_amable(self):
        with self.assertRaises(DomainError) as ctx:
            dd.inferir([(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-001")

    def test_colineales_area_nula_error(self):
        with self.assertRaises(DomainError) as ctx:
            dd.inferir([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)])
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-001")

    def test_forma_en_L_ortogonal(self):
        f = dd.inferir([(0, 0), (12, 0), (12, 4), (6, 4), (6, 8), (0, 8)])
        self.assertEqual(f["forma"], "ortogonal")
        self.assertFalse(f["alineado"])
        self.assertAlmostEqual(f["area_m2"], 72.0, places=3)
        self.assertAlmostEqual(f["ancho_m"], 12.0, places=6)

    def test_poligono_general(self):
        f = dd.inferir([(0, 0), (10, 0), (8, 6), (2, 7)])
        self.assertEqual(f["forma"], "poligono")
        self.assertGreater(f["area_m2"], 0.0)

    def test_rectangulo_girado_detecta_forma(self):
        f = dd.inferir([(0, 0), (6, 8), (-2, 14), (-8, 6)])
        self.assertEqual(f["forma"], "rectangulo")
        self.assertFalse(f["alineado"])
        self.assertAlmostEqual(f["area_m2"], 100.0, places=3)


# ---------------------------------------------------------------------------
# 2) VERIFICACIÓN HONESTA: ¿el rectángulo queda dentro del contorno?
# ---------------------------------------------------------------------------

class TestRectDentro(unittest.TestCase):
    """No basta la caja envolvente: se verifica contra el polígono."""

    def test_rect_en_la_perna_de_la_L(self):
        self.assertTrue(dd.rect_dentro(
            [(14, 9), (22, 9), (22, 13), (14, 13)], L_MUESCA))

    def test_rect_que_cruza_la_muesca_fuera(self):
        self.assertFalse(dd.rect_dentro(
            [(2, 6), (10, 6), (10, 12), (2, 12)], L_MUESCA))

    def test_rasante_al_borde_cuenta_como_dentro(self):
        self.assertTrue(dd.rect_dentro(
            [(0, 0), (12, 0), (12, 4), (0, 4)], L_MUESCA))

    def test_rect_fuera_del_poligono(self):
        self.assertFalse(dd.rect_dentro(
            [(0, 10), (4, 10), (4, 13), (0, 13)], L_MUESCA))


# ---------------------------------------------------------------------------
# 3) CONTORNOS DESDE DXF
# ---------------------------------------------------------------------------

class TestContornosDxf(ARQGenTestCase):
    """Las polilíneas cerradas del DXF son los candidatos a contorno."""

    def _dxf(self, nombre: str, cerradas=True):
        import ezdxf
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        msp.add_lwpolyline(RECT, format="xy", close=cerradas,
                           dxfattribs={"layer": "AREAS"})
        if cerradas:
            msp.add_lwpolyline([(0, 0), (6, 0), (6, 4), (0, 4)],
                               format="xy", close=True,
                               dxfattribs={"layer": "ZONA"})
        msp.add_line((0, 0), (50, 0))
        path = self.project_path(nombre)
        doc.saveas(path)
        return path

    def test_dos_polilineas_ordenadas_por_area(self):
        contornos = dd.contornos_dxf(self._dxf("dos.dxf"))
        self.assertEqual(len(contornos), 2)
        self.assertAlmostEqual(contornos[0]["area_m2"], 96.0, places=2)
        self.assertAlmostEqual(contornos[1]["area_m2"], 24.0, places=2)
        self.assertIn("AREAS", contornos[0]["nombre"])
        self.assertIn("ZONA", contornos[1]["nombre"])
        self.assertEqual(contornos[0]["forma"], "rectangulo")

    def test_polilinea_abierta_se_ignora(self):
        self.assertEqual(dd.contornos_dxf(
            self._dxf("abierto.dxf", cerradas=False)), [])

    def test_archivo_inexistente_arq_ddi_004(self):
        with self.assertRaises(DomainError) as ctx:
            dd.contornos_dxf(self.project_path("nada.dxf"))
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-004")

    def test_dxf_ilegible_arq_ddi_005(self):
        path = self.project_path("malo.dxf")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("esto no es un DXF")
        with self.assertRaises(DomainError) as ctx:
            dd.contornos_dxf(path)
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-005")


# ---------------------------------------------------------------------------
# 4) PROGRAMA POR USOS DEL DNA (modo edificación)
# ---------------------------------------------------------------------------

class TestProgramaEdificacion(ARQGenTestCase):
    """Usos sociales del DNA con cantidades -> renglones compatibles."""

    def test_cantidad_numerada(self):
        prog = dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 3, "area_m2": 20}])
        self.assertEqual(len(prog["renglones"]), 3)
        nombres = [r["nombre"] for r in prog["renglones"]]
        self.assertEqual(len(set(nombres)), 3)
        self.assertTrue(all(r["area_m2"] == 20.0 for r in
                            prog["renglones"]))
        self.assertTrue(all(r["codigo"] == "OFFICE" for r in
                            prog["renglones"]))
        self.assertEqual(prog["totales"]["area_m2"], 60.0)

    def test_area_bajo_el_minimo_dna_avisa_y_sube(self):
        from domain.knowledge import SpaceDNARegistry
        from app.paths import resource_path
        registro = SpaceDNARegistry()
        registro.load_file(resource_path("knowledge", "space_dna.json"))
        dna = registro.get("BATHROOM")
        minimo = float(dna.minimum_area or 0.0)
        self.assertGreater(minimo, 0.0)
        prog = dd.programa_edificacion(
            [{"space_type": "BATHROOM", "area_m2": 1.0}])
        self.assertEqual(prog["renglones"][0]["area_m2"], minimo)
        self.assertTrue(any("mínimo" in a for a in prog["avisos"]))

    def test_area_por_defecto_sale_del_dna(self):
        from domain.knowledge import SpaceDNARegistry
        from app.paths import resource_path
        registro = SpaceDNARegistry()
        registro.load_file(resource_path("knowledge", "space_dna.json"))
        dna = registro.get("BATHROOM")
        esperado = float(dna.preferred_area or dna.minimum_area or 25.0)
        prog = dd.programa_edificacion([{"space_type": "BATHROOM"}])
        self.assertEqual(prog["renglones"][0]["area_m2"], esperado)

    def test_uso_fuera_del_dna_avisa(self):
        prog = dd.programa_edificacion(
            [{"space_type": "USO_INVENTADO", "area_m2": 30.0}])
        self.assertEqual(prog["renglones"][0]["area_m2"], 30.0)
        self.assertTrue(any("fuera del DNA" in a for a in
                            prog["avisos"]))
        self.assertTrue(any("USO_INVENTADO" in n for n in
                            prog["notas"]))

    def test_programa_vacio_arq_ddi_002(self):
        with self.assertRaises(DomainError) as ctx:
            dd.programa_edificacion([])
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-002")
        with self.assertRaises(DomainError) as ctx:
            dd.programa_edificacion([{"space_type": ""}])
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-002")


# ---------------------------------------------------------------------------
# 5) ¿CABE? ajuste y crecimiento en altura
# ---------------------------------------------------------------------------

class TestAjustar(ARQGenTestCase):
    """El corazón: empaquetado honesto y niveles sugeridos."""

    def setUp(self) -> None:
        super().setUp()
        self.ap = eng.programa_servicio("ANATOMIA_PATOLOGICA")

    def test_cabe_en_un_nivel_en_contorno_grande(self):
        a = dd.ajustar(self.ap, [(0, 0), (60, 0), (60, 25), (0, 25)])
        self.assertTrue(a["cabe_un_nivel"])
        self.assertEqual(a["niveles"], 1)
        self.assertTrue(a["dentro_del_contorno"])
        plan = a["reparto"][0]
        self.assertEqual(len(plan["locales"]),
                         self.ap["totales"]["locales"])
        self.assertIsNone(plan["escalera"])
        self.assertEqual(a["totales"]["area_contorno"], 1500.0)
        self.assertAlmostEqual(a["totales"]["altura_total"], 3.0,
                               places=6)

    def test_totales_coherentes_con_el_programa(self):
        a = dd.ajustar(self.ap, [(0, 0), (60, 0), (60, 25), (0, 25)])
        self.assertEqual(a["totales"]["area_programa"],
                         self.ap["totales"]["area_m2"])
        plan = a["reparto"][0]
        suma = plan["pasillo"]["area_m2"] + sum(
            r["area_m2"] for r in plan["locales"])
        self.assertAlmostEqual(plan["area_ocupada"], suma, places=2)

    def test_no_cabe_crece_en_altura_con_escalera(self):
        a = dd.ajustar(self.ap, [(0, 0), (20, 0), (20, 10), (0, 10)])
        self.assertFalse(a["cabe_un_nivel"])
        self.assertGreaterEqual(a["niveles"], 2)
        self.assertTrue(a["con_escalera"])
        self.assertIsNotNone(a["escalera"])
        self.assertIn("Blondel", a["escalera"]["descripcion"])
        for plan in a["reparto"]:
            self.assertIsNotNone(plan["escalera"])
            self.assertEqual(plan["escalera"]["space_type"], "STAIR")
        self.assertAlmostEqual(
            a["totales"]["altura_total"], a["niveles"] * 3.0, places=6)

    def test_local_imposible_arq_ddi_003(self):
        with self.assertRaises(DomainError) as ctx:
            dd.ajustar(self.ap, [(0, 0), (30, 0), (30, 4), (0, 4)])
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-003")

    def test_idempotente_mismo_dibujo_mismo_plan(self):
        a1 = dd.ajustar(self.ap, [(0, 0), (20, 0), (20, 10), (0, 10)])
        a2 = dd.ajustar(self.ap, [(0, 0), (20, 0), (20, 10), (0, 10)])
        self.assertEqual(a1["niveles"], a2["niveles"])
        for p1, p2 in zip(a1["reparto"], a2["reparto"]):
            self.assertEqual(p1["pasillo"]["rect"], p2["pasillo"]["rect"])
            self.assertEqual([r["nombre"] for r in p1["locales"]],
                             [r["nombre"] for r in p2["locales"]])

    def test_forma_L_encaja_estricta_todo_dentro(self):
        # v3.40.0: el encaje estricto tesela la L en contenedores y
        # NADA se sale del polígono (antes: locales fuera + aviso)
        prog = dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 7, "area_m2": 20.0}])
        a = dd.ajustar(prog, L_MUESCA)
        self.assertTrue(a["dentro_del_contorno"])
        self.assertTrue(a["reparto"][0]["dentro"])
        for r in a["reparto"][0]["locales"]:
            self.assertTrue(
                dd.rect_dentro([tuple(p) for p in r["rect"]],
                               L_MUESCA), r["nombre"])
        # el encaje estricto lo declara y el ala de la L se aprovecha
        self.assertTrue(any("encaje estricto" in x for x in a["avisos"]))
        self.assertGreaterEqual(
            len([r for r in a["reparto"][0]["locales"]
                 if r.get("contenedor", 0) > 0]), 1)

    def test_forma_L_camino_historico_mantiene_el_aviso(self):
        # el camino de caja envolvente (encaje_estricto=False) conserva
        # el comportamiento documentado: verifica y avisa lo que se sale
        prog = dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 7, "area_m2": 20.0}])
        a = dd.ajustar(prog, L_MUESCA, encaje_estricto=False)
        self.assertFalse(a["dentro_del_contorno"])
        self.assertTrue(any("fuera del polígono" in x
                            for x in a["avisos"]))

    def test_margen_reducela_caja_util(self):
        a = dd.ajustar(self.ap, [(0, 0), (60, 0), (60, 25), (0, 25)],
                       margen_m=3.0)
        self.assertEqual(a["reparto"][0]["area_disponible"], 1026.0)

    def test_aviso_si_el_contorno_no_es_rectangulo(self):
        prog = dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 2, "area_m2": 20.0}])
        # estricto: la parcela L se tesela en contenedores
        a = dd.ajustar(prog, L_MUESCA)
        self.assertTrue(any("encaje estricto" in x for x in a["avisos"]))
        # histórico: aviso clásico de caja envolvente
        b = dd.ajustar(prog, L_MUESCA, encaje_estricto=False)
        self.assertTrue(any("caja envolvente" in x
                            for x in b["avisos"]))


# ---------------------------------------------------------------------------
# 6) APLICAR: entidades reales por los caminos oficiales
# ---------------------------------------------------------------------------

class TestAplicarPlan(ARQGenTestCase):
    """Del análisis al proyecto: edificio, niveles, espacios, zona."""

    def setUp(self) -> None:
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("dibujo.arqgen"), name="Dibujo")
        self.arch = ArchitectureService(self.ctx)
        self.ap = eng.programa_servicio("ANATOMIA_PATOLOGICA")

    def tearDown(self) -> None:
        self.ctx.close()
        super().tearDown()

    def _prog(self):
        return dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 7, "area_m2": 20.0}])

    def test_proyecto_vacio_genera_edificio_con_niveles(self):
        a = dd.ajustar(self._prog(), [(0, 0), (12, 0), (12, 9),
                                      (0, 9)])
        self.assertGreaterEqual(a["niveles"], 2)
        resumen = dd.aplicar_plan(
            self.ctx, a, {"nombre_edificio": "Edificio Anexo"})
        self.assertEqual(resumen["edificio"], "Edificio Anexo")
        self.assertEqual(
            resumen["niveles"],
            [f"Planta {i}" for i in range(1, a["niveles"] + 1)])
        niveles = self.ctx.architecture.list("LEVEL",
                                             self.ctx.project.id)
        self.assertEqual(len(niveles), a["niveles"])
        cotas = sorted(float(n.elevation_m or 0.0) for n in niveles)
        self.assertEqual(cotas,
                         [round(i * 3.0, 4)
                          for i in range(a["niveles"])])
        espacios = self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)
        # por nivel: pasillo + escalera; los 7 locales repartidos
        self.assertEqual(len(espacios), a["niveles"] * 2 + 7)
        self.assertEqual(resumen["relaciones"], a["niveles"] + 7)
        self.ctx.commit()
        self.assertEqual(len(self.ctx.architecture.list(
            "SPACE", self.ctx.project.id)), len(espacios))

    def test_pasillo_y_escalera_reales_en_cada_nivel(self):
        a = dd.ajustar(self.ap, [(0, 0), (20, 0), (20, 10), (0, 10)])
        self.assertGreaterEqual(a["niveles"], 2)
        resumen = dd.aplicar_plan(self.ctx, a,
                                  {"modo": "servicio"})
        espacios = self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)
        por_tipo = {}
        for e in espacios:
            por_tipo[e.space_type] = por_tipo.get(e.space_type, 0) + 1
        self.assertGreaterEqual(por_tipo.get("STAIR", 0), a["niveles"])
        self.assertGreaterEqual(por_tipo.get("CORRIDOR", 0),
                                a["niveles"])
        self.assertEqual(por_tipo.get("AUTOPSY_ROOM", 0), 1)
        zonas = self.ctx.architecture.list("ZONE",
                                           self.ctx.project.id)
        self.assertTrue(any(z.kind == "SERVICE" for z in zonas))
        self.assertEqual(resumen["modo"], "servicio")

    def test_eliminar_boceto_borra_el_espacio_dado(self):
        self.arch.create_level("PB", 0.0, 3.0)
        boceto = self.arch.create_space(
            "PB", "Boceto del área", "ROOM",
            [(0, 0), (10, 0), (10, 6), (0, 6)])
        a = dd.ajustar(self._prog(), [(0, 0), (30, 0), (30, 12),
                                      (0, 12)])
        resumen = dd.aplicar_plan(
            self.ctx, a, {"eliminar_boceto": boceto.code})
        codigos = [e.code for e in
                   self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)]
        self.assertNotIn(boceto.code, codigos)
        self.assertTrue(any("boceto" in x for x in resumen["avisos"]))

    def test_trazar_muros_contorno_y_locales(self):
        prog = dd.programa_edificacion(
            [{"space_type": "OFFICE", "cantidad": 3, "area_m2": 20.0}])
        a = dd.ajustar(prog, [(0, 0), (24, 0), (24, 14), (0, 14)])
        self.assertEqual(a["niveles"], 1)
        resumen = dd.aplicar_plan(self.ctx, a, {"trazar_muros": True})
        # 4 del contorno + 4 por cada local (3 locales)
        self.assertEqual(resumen["muros"], 16)
        muros = self.ctx.architecture.list("WALL",
                                           self.ctx.project.id)
        self.assertEqual(len(muros), 16)
        self.assertTrue(any("duplicadas" in x
                            for x in resumen["avisos"]))

    def test_doble_aplicacion_dos_edificios(self):
        a = dd.ajustar(self._prog(), [(0, 0), (30, 0), (30, 12),
                                      (0, 12)])
        r1 = dd.aplicar_plan(self.ctx, a,
                             {"nombre_edificio": "Anexo A"})
        r2 = dd.aplicar_plan(self.ctx, a,
                             {"nombre_edificio": "Anexo B"})
        self.assertEqual(r1["edificio"], "Anexo A")
        self.assertEqual(r2["edificio"], "Anexo B")
        edificios = self.ctx.architecture.list("BUILDING",
                                               self.ctx.project.id)
        self.assertEqual(len(edificios), 2)


# ---------------------------------------------------------------------------
# 7) TEXTO cp1252 (sin flechas)
# ---------------------------------------------------------------------------

class TestTextos(ARQGenTestCase):
    """Todo lo que sale por consola o cuadro de texto es cp1252."""

    def setUp(self) -> None:
        super().setUp()
        self.ap = eng.programa_servicio("ANATOMIA_PATOLOGICA")
        self.a = dd.ajustar(self.ap, [(0, 0), (20, 0), (20, 10),
                                      (0, 10)])

    def test_textos_codifican_en_cp1252(self):
        for texto in (dd.texto_inferencia(self.a["forma"]),
                      dd.texto_ajuste(self.a),
                      dd.texto_resumen_generacion({
                          "edificio": "E", "niveles": ["a", "b"],
                          "altura_total_m": 6.0, "espacios": [1, 2],
                          "zona": "Z-1", "muros": 4})):
            texto.encode("cp1252")

    def test_ajuste_anuncia_niveles_y_escalera(self):
        texto = dd.texto_ajuste(self.a)
        self.assertIn("NO", texto)
        self.assertIn("niveles", texto)
        self.assertIn("Escalera", texto)
        self.assertIn("Nivel 1", texto)
        self.assertNotIn("\u2192", texto)
        self.assertIn("->", texto)

    def test_inferencia_nombra_la_forma(self):
        texto = dd.texto_inferencia(dd.inferir(RECT))
        self.assertIn("rectángulo", texto)
        self.assertIn("96.00 m2", texto)


# ---------------------------------------------------------------------------
# 8) GANCHOS DE VENTANA (con display)
# ---------------------------------------------------------------------------

class TestGanchosVentana(ARQGenTestCase):
    """El diálogo «Desde dibujo» está cableado a la ventana."""

    def setUp(self):
        super().setUp()
        old = os.environ.get("ARQGEN_PREFS")
        self._prefs = os.path.join(self.tmp, "prefs.json")
        os.environ["ARQGEN_PREFS"] = self._prefs
        from ui.app_window import ARQGenWindow
        self.ctx = self.demo_context()
        self.window = ARQGenWindow(self.ctx, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.ctx.close()
        os.environ["ARQGEN_PREFS"] = self._prefs if self._prefs else ""
        os.environ.pop("ARQGEN_PREFS", None)
        super().tearDown()

    def test_dialogo_abre_con_origenes(self):
        self.window.open_desde_dibujo_dialog()
        self.window.update()
        dialogo = self.window._dd_dialog
        self.assertTrue(dialogo.winfo_exists())
        # el combobox de espacios del proyecto trae candidatos
        self.assertTrue(self.window._dd_espacios_combo["values"])

    def test_dd_float_tolera_coma_y_basura(self):
        import tkinter as tk
        var = tk.StringVar(value="3,5")
        self.assertEqual(self.window._dd_float(var, 1.0), 3.5)
        var.set("abc")
        self.assertEqual(self.window._dd_float(var, 1.0), 1.0)

    def test_programa_en_modo_edificacion_desde_la_tabla(self):
        import tkinter as tk
        self.window.open_desde_dibujo_dialog()
        self.window._dd_modo.set("edificacion")
        self.window._dd_usos = [{"space_type": "OFFICE",
                                 "cantidad": 2, "area_m2": 20.0}]
        prog = self.window._dd_programa()
        self.assertEqual(len(prog["renglones"]), 2)

    def test_version_coherente_con_v3410(self):
        self.assertEqual(APP_VERSION, "3.47.0")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
