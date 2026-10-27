"""ESCALERAS POR TIPOLOGÍA (v3.19.0): Blondel, geometría, hueco, QTO,
2D, 3D, persistencia y GUI. Pedido del usuario: «distintos tipos de
escaleras»."""

from __future__ import annotations

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
            self.project_path("escaleras.arqgen"), name="Escaleras")
        self.arq = ArchitectureService(self.context)
        self.n1 = self.arq.create_level("PB", 0.0, 3.0)
        self.n2 = self.arq.create_level("P1", 3.0, 3.0)
        # hueco de escalera que acoge la L de 18 peldaños
        self.arq.create_space(self.n1.code, "Hueco", "STAIR",
                              [(0, 0), (4, 0), (4, 4.5), (0, 4.5)])
        self.arq.create_space(self.n1.code, "Sala", "LIVING_ROOM",
                              [(4, 0), (10, 0), (10, 5), (4, 5)])


class TestDimensionarBlondel(unittest.TestCase):
    """La fórmula de Blondel y el reparto de contrahuellas."""

    def test_blondel_exacto(self):
        from domain import escaleras as esc
        self.assertAlmostEqual(esc.blondel_m(0.17, 0.29), 0.63, places=9)
        self.assertTrue(esc.blondel_ok(0.17, 0.29))
        self.assertFalse(esc.blondel_ok(0.25, 0.25))

    def test_dimensionar_busca_la_comoda(self):
        from domain import escaleras as esc
        d = esc.dimensionar(3.0)
        self.assertEqual(d["n_contrahuellas"], 18)
        self.assertAlmostEqual(d["contrahuella_m"], 3.0 / 18.0, places=6)
        self.assertTrue(d["blondel_ok"])
        self.assertEqual(d["tramos"], 2)          # 18 > 16: meseta
        self.assertEqual(d["por_tramo"], 9)

    def test_contrahuella_pedida_cae_exacta(self):
        from domain import escaleras as esc
        d = esc.dimensionar(4.2, contrahuella_m=0.175)
        self.assertEqual(d["n_contrahuellas"], 24)
        self.assertAlmostEqual(d["contrahuella_m"], 0.175, places=6)

    def test_avisos_amables_sin_errores(self):
        from domain import escaleras as esc
        d = esc.dimensionar(3.0, contrahuella_m=0.30)
        self.assertTrue(any("por encima" in a for a in d["avisos"]))

    def test_desnivel_invalido_error(self):
        from core.errors import DomainError
        from domain import escaleras as esc
        with self.assertRaises(DomainError) as cm:
            esc.dimensionar(0.0)
        self.assertEqual(cm.exception.code, "ARQ-ESC-002")


class TestGeometria(unittest.TestCase):
    """Planta y cajas 3D de cada tipología."""

    def test_recta_con_meseta(self):
        from domain import escaleras as esc
        g = esc.geometria("recta", 3.0)
        self.assertEqual(len(g["pasos"]), 18 + 1)      # + meseta
        self.assertEqual(len(g["outline"]), 4)
        self.assertAlmostEqual(max(c["z1"] for c in g["pasos"]), 3.0,
                               places=3)

    def test_L_en_esquina(self):
        from domain import escaleras as esc
        from domain.diseno_base import bbox_de
        g = esc.geometria("L", 3.0)
        self.assertEqual(len(g["outline"]), 6)
        self.assertEqual(g["mesetas"], 1)
        minx, miny, maxx, maxy = bbox_de(g["outline"])
        self.assertAlmostEqual((minx + maxx) / 2.0, 0.0, places=6)

    def test_U_paralela(self):
        from domain import escaleras as esc
        g = esc.geometria("U", 3.0)
        self.assertEqual(len(g["outline"]), 8)
        self.assertEqual(g["tramos"], 2)
        self.assertAlmostEqual(max(c["z1"] for c in g["pasos"]), 3.0,
                               places=3)

    def test_caracol_en_abanico(self):
        from domain import escaleras as esc
        g = esc.geometria("caracol", 3.0, ancho_m=1.10)
        self.assertEqual(len(g["pasos"]), 18)
        carac = g["caracol"]
        self.assertGreater(carac["vueltas"], 0.9)
        self.assertLess(carac["vueltas"], 1.2)
        self.assertAlmostEqual(carac["r_exterior_m"], 1.25, places=3)
        # los peldaños giran: la rotación no es constante
        rots = {c["rot"] for c in g["pasos"]}
        self.assertGreater(len(rots), 4)

    def test_rotacion_conserva_area_y_centra(self):
        from domain import escaleras as esc
        g0 = esc.geometria("L", 3.0)
        g90 = esc.geometria("L", 3.0, rot_deg=90.0)
        self.assertAlmostEqual(g0["area_huella_m2"],
                               g90["area_huella_m2"], places=6)

    def test_tipo_y_rango_con_errores_propios(self):
        from core.errors import DomainError
        from domain import escaleras as esc
        with self.assertRaises(DomainError) as cm:
            esc.geometria("tornamesa", 3.0)
        self.assertEqual(cm.exception.code, "ARQ-ESC-001")
        with self.assertRaises(DomainError) as cm:
            esc.geometria("recta", 3.0, ancho_m=0.5)
        self.assertEqual(cm.exception.code, "ARQ-ESC-002")

    def test_regla_para_uso_desde_neufert(self):
        from domain import escaleras as esc
        regla = esc.regla_para_uso("Vivienda")
        self.assertAlmostEqual(regla["contrahuella_m"], 0.175, places=6)
        self.assertAlmostEqual(regla["huella_m"], 0.28, places=6)
        lineas = esc.tabla_texto()
        self.assertEqual(len(lineas), 7)
        for linea in lineas:
            linea.encode("cp1252")


class TestGenerarEscalera(_ProyectoBase):
    """Generación idempotente en el proyecto con QTO y undo."""

    def test_genera_L_dentro_del_hueco(self):
        from domain import escaleras as esc
        r = esc.generar_escalera(self.context, None, tipo="L")
        stairs = self.context.architecture.list("STAIR", self.context.project.id)
        self.assertEqual(len(stairs), 1)
        st = stairs[0]
        self.assertEqual(st.tipo, "L")
        self.assertTrue(st.space_id)          # dentro del hueco STAIR
        self.assertTrue(st.metadata.get("pasos"))
        self.assertEqual(st.metadata.get("n_contrahuellas"), 18)
        self.assertFalse(any("hueco" in a for a in r["avisos"]), r["avisos"])
        self.assertEqual(r["parametros"]["modo"], "hueco")

    def test_desnivel_del_nivel_base_por_defecto(self):
        from domain import escaleras as esc
        r = esc.generar_escalera(self.context, None, tipo="recta")
        self.assertTrue(any("desnivel" in a for a in r["avisos"]))
        self.assertAlmostEqual(r["parametros"]["desnivel_m"], 3.0,
                               places=6)

    def test_idempotente_y_quitar(self):
        from domain import escaleras as esc
        esc.generar_escalera(self.context, None, tipo="L")
        r2 = esc.generar_escalera(self.context, None, tipo="caracol",
                                  x=20.0, y=20.0)
        stairs = self.context.architecture.list("STAIR", self.context.project.id)
        self.assertEqual(len(stairs), 1)
        self.assertEqual(stairs[0].tipo, "caracol")
        self.assertEqual(len(r2["eliminados"]), 1)
        bajas = esc.quitar_escaleras(self.context)
        self.assertEqual(len(bajas), 1)
        self.assertEqual(len(self.context.architecture.list(
            "STAIR", self.context.project.id)), 0)

    def test_x_y_manual_respetado(self):
        from domain import escaleras as esc
        esc.generar_escalera(self.context, None, tipo="U", x=12.0, y=-3.0)
        st = self.context.architecture.list("STAIR",
                                            self.context.project.id)[0]
        self.assertAlmostEqual(st.x, 12.0, places=4)
        self.assertAlmostEqual(st.y, -3.0, places=4)
        self.assertEqual(st.metadata.get("modo"), "manual")

    def test_undo_persistente(self):
        from domain import escaleras as esc
        from app.undo_service import PersistentUndoService
        esc.generar_escalera(self.context, None, tipo="L")
        self.context.commit()
        self.assertTrue(PersistentUndoService(self.context).undo())
        self.assertEqual(len(self.context.architecture.list(
            "STAIR", self.context.project.id)), 0)

    def test_qto_peldanos_huella_desarrollo_barandilla(self):
        from domain import escaleras as esc
        from services.quantity_service import QuantityService
        esc.generar_escalera(self.context, None, tipo="L")
        self.context.commit()
        q = QuantityService(self.context)
        q.compute_all()
        st = self.context.architecture.list("STAIR",
                                            self.context.project.id)[0]
        rows = {r["formula_code"]: r["final_quantity"]
                for r in q.quantities() if r["object_id"] == st.id}
        self.assertEqual(rows["STAIR_COUNT"], 1.0)
        self.assertEqual(rows["STAIR_RISERS"], 18.0)
        self.assertGreater(rows["STAIR_FOOTPRINT"], 3.0)
        self.assertAlmostEqual(rows["STAIR_HANDRAIL"],
                               2.0 * st.metadata["desarrollo_m"], places=2)

    def test_persistencia_tras_reabrir(self):
        from domain import escaleras as esc
        from services.context import ApplicationContext
        esc.generar_escalera(self.context, None, tipo="U")
        self.context.commit()
        pid = self.context.project.id
        ruta = self.context.db_path if hasattr(self.context, "db_path") \
            else self.project_path("escaleras.arqgen")
        self.context.close()
        reabierto = ApplicationContext().open_project(ruta)
        stairs = reabierto.architecture.list("STAIR", pid)
        self.assertEqual(len(stairs), 1)
        self.assertEqual(stairs[0].tipo, "U")
        self.assertTrue(stairs[0].metadata.get("pasos"))
        reabierto.close()

    def test_resumen_cp1252(self):
        from domain import escaleras as esc
        r = esc.generar_escalera(self.context, None, tipo="recta")
        linea = esc.resumen_texto(r)
        self.assertTrue(linea)
        linea.encode("cp1252")


class TestEscalera2D3D(_ProyectoBase):
    """Lienzo 2D y extrusión 3D de los peldaños."""

    def _genera(self, tipo="L"):
        from domain import escaleras as esc
        esc.generar_escalera(self.context, None, tipo=tipo)
        return tipo

    def test_primitivas_2d_de_escalera(self):
        from ui.models import CanvasModel
        self._genera()
        explorer = _ExplorerStub(self.context)
        modelo = CanvasModel(self.context, explorer)
        prims = modelo._architecture_primitives(
            self.context.architecture.list(
                "LEVEL", self.context.project.id)[0].id)
        kinds = {p.kind for p in prims}
        self.assertIn("stair", kinds)
        self.assertIn("stair_tread", kinds)
        stair = [p for p in prims if p.kind == "stair"][0]
        self.assertEqual(stair.row.type, "STAIR")
        self.assertGreaterEqual(len(stair.coords), 4)

    def test_3d_peldanos_y_explosion(self):
        from ui import view3d as v3
        self._genera()
        modelo, _ = v3.modelo3d_desde_proyecto(self.context)
        self.assertEqual(len(modelo.escaleras), 1)
        caras = v3.construir_caras(modelo, v3.Camara3D())
        peld = [c for c in caras if c.kind == "peldano"]
        self.assertTrue(peld, "el 3D dibuja los peldaños")
        zs = [p[2] for c in peld for p in c.puntos]
        self.assertGreaterEqual(min(zs), -1e-6)
        self.assertLessEqual(max(zs), 3.001)

    def test_png_determinista(self):
        import tempfile
        import hashlib
        from ui import view3d as v3
        self._genera("recta")
        modelo, _ = v3.modelo3d_desde_proyecto(self.context)
        caras = v3.construir_caras(modelo, v3.Camara3D())
        rutas = []
        for nombre in ("a.png", "b.png"):
            ruta = os.path.join(tempfile.mkdtemp(), nombre)
            v3.export_vista3d_png(caras, v3.Camara3D(), ruta,
                                  titulo="escalera")
            with open(ruta, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
            rutas.append(ruta)
        h = [hashlib.sha256(open(r, "rb").read()).hexdigest()
             for r in rutas]
        self.assertEqual(h[0], h[1])


class _ExplorerStub:
    """Stub mínimo del explorer para CanvasModel (patrón de test_096)."""

    def __init__(self, ctx):
        self.ctx = ctx

    def rows_for(self, _key):
        return []


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas (Xvfb :99)")
class TestDialogoEscaleras(_ProyectoBase):

    def test_dialogo_escaleras(self):
        from ui.app_window import ARQGenWindow
        ventana = ARQGenWindow(self.context, self.application)
        try:
            ventana.open_diseno_dialog()
            dialogo = ventana._diseno_dialog
            state = dialogo._diseno_state
            etiquetas = [dialogo._diseno_state["notebook"].tab(
                t, "text") for t in
                dialogo._diseno_state["notebook"].tabs()]
            self.assertEqual(len(etiquetas), 9)
            self.assertTrue(any("Escaleras" in e for e in etiquetas))
            state["combo_esc_tipo"].set("L")
            dialogo._diseno_escalera_generar()
            stairs = self.context.architecture.list(
                "STAIR", self.context.project.id)
            self.assertEqual(len(stairs), 1)
            self.assertIn("Blondel",
                          state["salida_esc"].get("1.0", "end"))
            dialogo._diseno_escalera_quitar()
            self.assertEqual(len(self.context.architecture.list(
                "STAIR", self.context.project.id)), 0)
            # error amable con giro no numérico
            state["var_esc_rot"].set("malo")
            from ui import app_window as aw
            original = aw.messagebox.showerror
            capturado = {}
            aw.messagebox.showerror = lambda *a, **k: capturado.update(
                {"args": a})
            try:
                dialogo._diseno_escalera_generar()
            finally:
                aw.messagebox.showerror = original
            self.assertTrue(capturado, "esperaba el error amable")
        finally:
            ventana.destroy()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
