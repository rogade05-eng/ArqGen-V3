"""TIPOS DE PUERTAS Y VENTANAS (v3.19.0): catálogos, asignación,
símbolos 2D, undo, resumen y GUI. Pedido del usuario: «ventanas,
puertas»."""

from __future__ import annotations

import math
import os
import unittest

from tests.base import ARQGenTestCase

try:  # pragma: no cover — igual que el resto de pruebas GUI
    DISPLAY = bool(os.environ.get("DISPLAY")) and os.environ.get(
        "DISPLAY") != ""
except Exception:  # noqa: BLE001
    DISPLAY = False


class _ProyectoBase(ARQGenTestCase):

    def setUp(self) -> None:
        super().setUp()
        from services.architecture_service import ArchitectureService
        self.context = self.application.create_project(
            self.project_path("aberturas.arqgen"), name="Aberturas")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.n2 = self.arq.create_level("P1", 3.0, 3.0)
        self.arq.create_space(self.n1.code, "Sala", "LIVING_ROOM",
                              [(0, 0), (8, 0), (8, 5), (0, 5)])
        self.arq.create_space(self.n2.code, "Sala1", "LIVING_ROOM",
                              [(0, 0), (8, 0), (8, 5), (0, 5)])
        self.w1 = self.arq.create_wall(self.n1.code, (0, 0), (8, 0))
        self.d1 = self.arq.create_opening("DOOR", self.w1.code, 0.9, 2.1,
                                          offset_m=1.0)
        self.w2 = self.arq.create_wall(self.n1.code, (8, 0), (8, 5))
        self.v1 = self.arq.create_opening("WINDOW", self.w2.code, 1.2, 1.4,
                                          offset_m=1.0, sill_height_m=0.9)
        self.w3 = self.arq.create_wall(self.n2.code, (0, 0), (8, 0))
        self.d2 = self.arq.create_opening("DOOR", self.w3.code, 1.0, 2.1,
                                          offset_m=2.0)


class TestCatalogos(unittest.TestCase):
    """Catálogos con hojas, apertura y símbolo."""

    def test_catalogo_puertas(self):
        from domain import aberturas as abe
        self.assertEqual(abe.tipos_puerta(),
                         ("abatible", "doble_hoja", "corredera", "plegable",
                          "vaiven", "pivote"))
        ficha = abe.datos_puerta("corredera")
        self.assertEqual(ficha["hojas"], 2)
        self.assertAlmostEqual(ficha["apertura_pct"], 50.0, places=6)

    def test_catalogo_ventanas(self):
        from domain import aberturas as abe
        self.assertEqual(abe.tipos_ventana(),
                         ("practicable", "oscilobatiente", "abatible",
                          "proyectante", "corredera", "guillotina", "fija",
                          "pivotante"))
        ficha = abe.datos_ventana("oscilobatiente")
        self.assertAlmostEqual(ficha["antepecho_m"], 0.90, places=6)
        fija = abe.datos_ventana("fija")
        self.assertAlmostEqual(fija["apertura_pct"], 0.0, places=6)

    def test_errores_propios(self):
        from core.errors import DomainError
        from domain import aberturas as abe
        with self.assertRaises(DomainError) as cm:
            abe.datos_puerta("giratoria")
        self.assertEqual(cm.exception.code, "ARQ-ABE-001")
        with self.assertRaises(DomainError) as cm:
            abe.datos_ventana("guillotina2")
        self.assertEqual(cm.exception.code, "ARQ-ABE-002")

    def test_tabla_cp1252(self):
        from domain import aberturas as abe
        lineas = abe.tabla_texto()
        self.assertEqual(len(lineas), 6 + 8 + 2)
        for linea in lineas:
            linea.encode("cp1252")


class TestSimbolos(unittest.TestCase):
    """Símbolos de planos por tipología."""

    def test_todos_los_tipos_dibujan(self):
        import math
        from domain import aberturas as abe
        for tipo in abe.tipos_puerta():
            trazos = abe.simbolo_puntos(tipo, True, (0.0, 0.0),
                                        (1.0, 0.0), 0.9)
            self.assertTrue(trazos, tipo)
            self.assertTrue(all(
                math.isfinite(x) for pol in trazos
                for p in pol for x in p), tipo)
        for tipo in abe.tipos_ventana():
            trazos = abe.simbolo_puntos(tipo, False, (0.0, 0.0),
                                        (0.0, 1.0), 1.2)
            self.assertTrue(trazos, tipo)

    def test_arco_del_abatible_toca_la_hoja(self):
        from domain import aberturas as abe
        trazos = abe.simbolo_puntos("abatible", True, (0.0, 0.0),
                                    (1.0, 0.0), 0.9)
        hoja, arco = trazos[0], trazos[1]
        # la hoja parte de la bisagra y mide el ancho del vano
        largo = math.hypot(hoja[1][0] - hoja[0][0],
                           hoja[1][1] - hoja[0][1])
        self.assertAlmostEqual(largo, 0.9, places=6)
        # el arco acaba en el eje del muro (radio = ancho)
        final = arco[-1]
        self.assertAlmostEqual(math.hypot(final[0] - hoja[0][0],
                                          final[1] - hoja[0][1]),
                               0.9, places=6)

    def test_corredera_dos_lineas_paralelas(self):
        from domain import aberturas as abe
        trazos = abe.simbolo_puntos("corredera", True, (0.0, 0.0),
                                    (1.0, 0.0), 0.9)
        self.assertEqual(len(trazos), 2)
        self.assertAlmostEqual(trazos[0][0][1], 0.03, places=6)
        self.assertAlmostEqual(trazos[1][0][1], 0.07, places=6)

    def test_sin_tipo_borde_simple(self):
        from domain import aberturas as abe
        trazos = abe.simbolo_puntos("xxx", True, (0.0, 0.0),
                                    (1.0, 0.0), 0.9)
        self.assertEqual(len(trazos), 1)


class TestAsignar(_ProyectoBase):
    """Asignación por nivel con undo y resumen."""

    def test_asignar_por_nivel(self):
        from domain import aberturas as abe
        r = abe.asignar_tipos(self.context, "DOOR", "abatible",
                              nivel_id=self.n1.id)
        self.assertEqual(r["asignadas"], 1)
        self.assertEqual(r["por_nivel"], {self.n1.id: 1})
        d = self.context.architecture.get("DOOR", self.d1.id)
        self.assertEqual(d.metadata["abertura"]["tipo"], "abatible")
        self.assertEqual(d.metadata["abertura"]["hojas"], 1)
        # P1 no se toca
        d2 = self.context.architecture.get("DOOR", self.d2.id)
        self.assertNotIn("abertura", d2.metadata or {})

    def test_asignar_todos_los_niveles(self):
        from domain import aberturas as abe
        r = abe.asignar_tipos(self.context, "DOOR", "vaiven")
        self.assertEqual(r["asignadas"], 2)
        self.assertEqual(r["por_nivel"], {self.n1.id: 1, self.n2.id: 1})

    def test_idempotente_reescribe(self):
        from domain import aberturas as abe
        abe.asignar_tipos(self.context, "WINDOW", "practicable")
        abe.asignar_tipos(self.context, "WINDOW", "oscilobatiente")
        v = self.context.architecture.get("WINDOW", self.v1.id)
        self.assertEqual(v.metadata["abertura"]["tipo"], "oscilobatiente")
        rec = abe.resumen_aberturas(self.context)
        self.assertEqual(rec["ventanas"], {"oscilobatiente": 1})

    def test_undo_persistente(self):
        from app.undo_service import PersistentUndoService
        from domain import aberturas as abe
        abe.asignar_tipos(self.context, "DOOR", "abatible",
                          nivel_id=self.n1.id)
        self.context.commit()
        self.assertTrue(PersistentUndoService(self.context).undo())
        d = self.context.architecture.get("DOOR", self.d1.id)
        self.assertNotIn("abertura", d.metadata or {})

    def test_quitar_tipos(self):
        from domain import aberturas as abe
        abe.asignar_tipos(self.context, "WINDOW", "fija")
        total = abe.quitar_tipos(self.context, "WINDOW")
        self.assertEqual(total, 1)
        v = self.context.architecture.get("WINDOW", self.v1.id)
        self.assertNotIn("abertura", v.metadata or {})
        rec = abe.resumen_aberturas(self.context)
        self.assertEqual(rec["sin_tipo"]["WINDOW"], 1)

    def test_resumen_y_recuento_cp1252(self):
        from domain import aberturas as abe
        abe.asignar_tipos(self.context, "DOOR", "plegable")
        abe.asignar_tipos(self.context, "WINDOW", "corredera")
        rec = abe.resumen_aberturas(self.context)
        self.assertEqual(rec["puertas"], {"plegable": 2})
        self.assertEqual(rec["ventanas"], {"corredera": 1})
        lineas = abe.recuento_texto(rec)
        self.assertTrue(any("plegable" in l for l in lineas))
        self.assertTrue(any("corredera" in l for l in lineas))
        for linea in lineas:
            linea.encode("cp1252")
        self.assertTrue(abe.resumen_texto(
            {"asignadas": 1, "kind": "DOOR", "etiqueta": "plegable "
             "(acordeón)", "hojas": 2, "apertura_pct": 85.0}
        ).encode("cp1252"))

    def test_sin_vanos_error_amable(self):
        from core.errors import DomainError
        from domain import aberturas as abe
        n3 = self.arq.create_level("P2", 6.0, 3.0)
        with self.assertRaises(DomainError) as cm:
            abe.asignar_tipos(self.context, "DOOR", "abatible",
                              nivel_id=n3.id)
        self.assertEqual(cm.exception.code, "ARQ-ABE-004")


class TestAberturas2D(_ProyectoBase):
    """El lienzo dibuja el símbolo cuando la metadata lleva tipo."""

    def test_primitiva_simbolo(self):
        from domain import aberturas as abe
        from ui.models import CanvasModel
        abe.asignar_tipos(self.context, "DOOR", "corredera")
        abe.asignar_tipos(self.context, "WINDOW", "oscilobatiente")
        explorer = _ExplorerStub(self.context)
        modelo = CanvasModel(self.context, explorer)
        prims = modelo._architecture_primitives(self.n1.id)
        simbolos = [p for p in prims if p.kind == "abertura_simbolo"]
        self.assertGreaterEqual(len(simbolos), 3)   # 2 líneas corredera + 1
        self.assertTrue(all(s.row.type in ("DOOR", "WINDOW")
                            for s in simbolos))

    def test_sin_tipo_no_dibuja_simbolo(self):
        from ui.models import CanvasModel
        explorer = _ExplorerStub(self.context)
        modelo = CanvasModel(self.context, explorer)
        prims = modelo._architecture_primitives(self.n1.id)
        self.assertFalse([p for p in prims
                          if p.kind == "abertura_simbolo"])


class _ExplorerStub:

    def __init__(self, ctx):
        self.ctx = ctx

    def rows_for(self, _key):
        return []


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoAberturas(_ProyectoBase):

    def test_dialogo_aberturas(self):
        from ui.app_window import ARQGenWindow
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            state["combo_nivel_abe"].current(1)   # nivel PB
            dialogo._diseno_abe_aplicar()
            self.assertIn("abatible",
                          state["salida_abe"].get("1.0", "end"))
            # cambio a ventanas con el binding
            state["combo_abe_kind"].set("ventanas")
            dialogo._diseno_abe_kind_changed()
            self.assertIn("practicable", state["combo_abe_tipo"]["values"])
            state["combo_abe_tipo"].set("guillotina")
            dialogo._diseno_abe_aplicar()
            v = self.context.architecture.get("WINDOW", self.v1.id)
            self.assertEqual(v.metadata["abertura"]["tipo"], "guillotina")
            dialogo._diseno_abe_recuento()
            self.assertIn("Ventanas:",
                          state["salida_abe"].get("1.0", "end"))
            dialogo._diseno_abe_quitar()
            v = self.context.architecture.get("WINDOW", self.v1.id)
            self.assertNotIn("abertura", v.metadata or {})
            # error amable: nivel sin ventanas (P1 solo tiene puerta)
            state["combo_nivel_abe"].current(2)
            state["combo_abe_kind"].set("ventanas")
            dialogo._diseno_abe_kind_changed()
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_abe_aplicar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
