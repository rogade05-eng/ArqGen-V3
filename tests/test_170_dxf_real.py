"""DXF REAL: IMPORTACIÓN ROBUSTA v3.37.0 (importers/dxf_reader.py +
domain/desde_dibujo.contornos_dxf + ganchos de ventana).

Réplica fiel del plano real «AP Y MORGUE.dxf»: UNA LWPOLYLINE abierta
(flag closed=False) de 9 vértices con el primero repetido al final en
capa 'MURO', 2 MTEXT vacíos en capa 'A-TEXTO' y $INSUNITS=4
(milímetros). El análisis v3.36.0 lo descartaba entero («LWPOLYLINE
de muro no rectangular ignorada», cero candidatos). Ahora:

  · las unidades $INSUNITS se escalan a metros (mm -> m),
  · el cierre geométrico (primero == último) cuenta como cerrado,
  · el contorno de planta de N lados en capa de muros se descompone
    en N segmentos de muro,
  · las polilíneas abiertas de muros dan un segmento por arista,
  · los textos vacíos se cuentan y avisan,
  · contornos_dxf enumera el contorno real (174.91 m2, ortogonal),
    cierra solo los huecos <= máx(2 cm, 1 por mil de la diagonal) y
  · el flujo desde dibujo -> servicio funciona extremo a extremo con
    el plano real: explorar catálogo (34), MORGUE crece a 2 niveles
    con escalera de Blondel y aplicar_plan genera el edificio.
"""

from __future__ import annotations

import os
import unittest

from core import APP_VERSION
from core.errors import DomainError, ImportErrorARQ
from domain import desde_dibujo as dd
from domain import servicios_engine as eng
from importers.dxf_reader import (DxfImporter, UNIDADES_DXF,
                                  _cierre_geometrico, escala_unidades_dxf)
from tests.base import ARQGenTestCase


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

# los 9 vértices EXACTOS del plano real del usuario (mm, capa 'MURO',
# flag closed=False, primero repetido al final)
VERTS_REAL = [(178.84, 3616.82), (178.84, 15006.94), (6828.84, 15006.94),
              (6828.84, 8176.82), (17680.98, 8176.82), (17680.98, 36.82),
              (3803.84, 36.82), (3803.84, 3616.82), (178.84, 3616.82)]


def _codigo(exc: Exception) -> str:
    return getattr(exc, "code", "")


def _dx_real(path: str, unidades: int = 4) -> str:
    """Réplica 1:1 de la estructura del plano «AP Y MORGUE.dxf»."""
    import ezdxf
    doc = ezdxf.new("R2013")
    doc.header["$INSUNITS"] = unidades
    doc.header["$MEASUREMENT"] = 1
    doc.layers.add(name="A-TEXTO", color=7)
    doc.layers.add(name="MURO", color=3)
    msp = doc.modelspace()
    msp.add_lwpolyline(VERTS_REAL, format="xy",
                       dxfattribs={"layer": "MURO"})
    for _ in range(2):
        msp.add_mtext("", dxfattribs={"layer": "A-TEXTO"})
    doc.saveas(path)
    return path


# ---------------------------------------------------------------------------
# 1) UNIDADES $INSUNITS
# ---------------------------------------------------------------------------

class TestUnidadesDxf(unittest.TestCase):
    """El plano en milímetros no puede importarse como 17 700 m."""

    def test_mapa_de_unidades_clave(self):
        self.assertEqual(UNIDADES_DXF[4], (0.001, "milímetros"))
        self.assertEqual(UNIDADES_DXF[6], (1.0, "metros"))
        self.assertEqual(UNIDADES_DXF[0], (1.0, "sin unidades (se asume metros)"))
        self.assertEqual(UNIDADES_DXF[2], (0.3048, "pies"))
        self.assertEqual(UNIDADES_DXF[5], (0.01, "centímetros"))
        self.assertEqual(UNIDADES_DXF[1], (0.0254, "pulgadas"))

    def test_escala_insunits_mm(self):
        import ezdxf
        doc = ezdxf.new("R2013")
        doc.header["$INSUNITS"] = 4
        codigo, escala, etiqueta = escala_unidades_dxf(doc)
        self.assertEqual((codigo, escala, etiqueta),
                         (4, 0.001, "milímetros"))

    def test_escala_metros_y_defecto(self):
        import ezdxf
        doc = ezdxf.new("R2010")
        # el defecto de un DXF nuevo (unitless/metros) es escala 1.0
        self.assertEqual(escala_unidades_dxf(doc)[1], 1.0)
        doc.header["$INSUNITS"] = 6
        self.assertEqual(escala_unidades_dxf(doc),
                         (6, 1.0, "metros"))

    def test_escala_codigo_desconocido_cae_a_metros(self):
        import ezdxf
        doc = ezdxf.new("R2013")
        doc.header["$INSUNITS"] = 99
        codigo, escala, etiqueta = escala_unidades_dxf(doc)
        self.assertEqual((codigo, escala), (99, 1.0))
        self.assertIn("sin unidades", etiqueta)

    def test_cierre_geometrico(self):
        self.assertTrue(_cierre_geometrico(
            [(0, 0), (10, 0), (10, 5), (0, 0)]))
        self.assertFalse(_cierre_geometrico([(0, 0), (10, 0), (10, 5)]))
        self.assertFalse(_cierre_geometrico([(0, 0), (1, 1)]))
        # hueco ínfimo sobre diagonal grande: tolerancia relativa
        self.assertTrue(_cierre_geometrico(
            [(0, 0), (20, 0), (20, 10), (1e-7, 1e-7)]))


# ---------------------------------------------------------------------------
# 2) PREVIEW del §94 contra la réplica del plano real
# ---------------------------------------------------------------------------

class TestPreviewReplicaReal(ARQGenTestCase):
    """Lo que antes daba «no se detectaron candidatos» ahora analiza."""

    def _preview(self, nombre="AP Y MORGUE.dxf", unidades=4):
        path = _dx_real(os.path.join(self.tmp, nombre), unidades)
        return DxfImporter().preview(path)

    def test_replica_detecta_8_muros(self):
        rep = self._preview()
        self.assertEqual(rep["counts"]["walls"], 8)
        self.assertEqual(rep["counts"]["spaces"], 0)
        self.assertEqual(rep["counts"]["texts"], 0)
        self.assertEqual(rep["counts"]["textos_vacios"], 2)
        self.assertEqual(rep["counts"]["zero_length_or_invalid"], 0)
        self.assertEqual(rep["counts"]["unclosed_polylines"], 0)
        self.assertEqual(rep["errors"], [])

    def test_replica_unidades_mm_y_coordenadas_en_metros(self):
        rep = self._preview()
        self.assertEqual(rep["unidades"]["codigo"], 4)
        self.assertEqual(rep["unidades"]["escala"], 0.001)
        self.assertEqual(rep["unidades"]["etiqueta"], "milímetros")
        puntos = [p for w in rep["_walls"]
                  for p in (w["start"], w["end"])]
        self.assertAlmostEqual(min(p[0] for p in puntos), 0.17884, places=4)
        self.assertAlmostEqual(max(p[0] for p in puntos), 17.68098, places=4)
        self.assertAlmostEqual(min(p[1] for p in puntos), 0.036822, places=4)
        self.assertAlmostEqual(max(p[1] for p in puntos), 15.006944, places=4)

    def test_replica_avisos_honestos_cp1252(self):
        rep = self._preview()
        texto = "\n".join(rep["warnings"]).encode("cp1252")
        self.assertIn("Contorno de planta con 8 lados en capa 'MURO'"
                      .encode("cp1252"), texto)
        self.assertIn(b"se descompone en 8 segmentos de muro", texto)
        self.assertIn("2 texto(s) vacío(s) ignorados en capa 'A-TEXTO'"
                      .encode("cp1252"), texto)
        self.assertNotIn(b"LWPOLYLINE de muro no rectangular", texto)

    def test_replica_perimetro_del_contorno(self):
        rep = self._preview()
        total = sum(((w["start"][0] - w["end"][0]) ** 2
                     + (w["start"][1] - w["end"][1]) ** 2) ** 0.5
                    for w in rep["_walls"])
        self.assertAlmostEqual(total, 64.94, places=2)

    def test_replica_capas_vistas(self):
        rep = self._preview()
        self.assertEqual(rep["layers_seen"]["MURO"], {"LWPOLYLINE": 1})
        self.assertEqual(rep["layers_seen"]["A-TEXTO"], {"MTEXT": 2})

    def test_replica_capa_explicita_muro(self):
        path = _dx_real(os.path.join(self.tmp, "capas.dxf"))
        rep = DxfImporter(layer_walls="MURO").preview(path)
        self.assertEqual(rep["counts"]["walls"], 8)


# ---------------------------------------------------------------------------
# 3) PREVIEW: variantes del lector robusto
# ---------------------------------------------------------------------------

class TestPreviewVariantes(ARQGenTestCase):
    """Un segmento por arista, ejes, cuerdas y textos vacíos."""

    def _doc(self, unidades=0):
        import ezdxf
        doc = ezdxf.new("R2010")
        if unidades:
            doc.header["$INSUNITS"] = unidades
        doc.layers.add(name="ARQ-MURO", color=7)
        doc.layers.add(name="ARQ-LOCAL", color=8)
        return doc

    def test_polilinea_abierta_de_muro_da_segmentos(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (4, 0), (4, 3)],
                           format="xy", dxfattribs={"layer": "ARQ-MURO"})
        path = os.path.join(self.tmp, "abierta.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 2)
        self.assertEqual(rep["errors"], [])

    def test_polilinea_de_2_vertices_es_un_segmento(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_lwpolyline([(1, 1), (5, 1)],
                           format="xy", dxfattribs={"layer": "ARQ-MURO"})
        path = os.path.join(self.tmp, "eje.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 1)
        self.assertEqual(rep["_walls"][0]["start"], (1.0, 1.0))
        self.assertEqual(rep["_walls"][0]["end"], (5.0, 1.0))

    def test_cerrado_de_4_lados_sigue_dando_eje_central(self):
        doc = self._doc()
        msp = doc.modelspace()
        pl = msp.add_lwpolyline([(0, 0), (6, 0), (6, 2), (0, 2)],
                                format="xy", dxfattribs={"layer": "ARQ-MURO"})
        pl.closed = True
        path = os.path.join(self.tmp, "rect.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 1)
        muro = rep["_walls"][0]
        self.assertAlmostEqual(muro["start"][1], 1.0, places=6)
        self.assertAlmostEqual(muro["end"][1], 1.0, places=6)
        self.assertAlmostEqual(abs(muro["end"][0] - muro["start"][0]),
                               6.0, places=6)

    def test_cerrado_con_cierre_duplicado_5_puntos(self):
        # flag closed + primero repetido: se limpia y da eje, no contorno
        doc = self._doc()
        msp = doc.modelspace()
        pl = msp.add_lwpolyline([(0, 0), (6, 0), (6, 2), (0, 2), (0, 0)],
                                format="xy", dxfattribs={"layer": "ARQ-MURO"})
        pl.closed = True
        path = os.path.join(self.tmp, "dup.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 1)
        self.assertIn("eje central", "\n".join(rep["warnings"]))

    def test_cerrado_geometrico_sin_flag_de_4_lados(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (6, 0), (6, 2), (0, 2), (0, 0)],
                           format="xy", dxfattribs={"layer": "ARQ-MURO"})
        path = os.path.join(self.tmp, "geo.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 1)
        self.assertIn("eje central", "\n".join(rep["warnings"]))

    def test_polilinea_muro_con_bulges_se_traza_por_cuerdas(self):
        doc = self._doc()
        msp = doc.modelspace()
        pl = msp.add_lwpolyline([(0, 0, 0.5), (6, 0, 0), (6, 2, 0),
                                 (0, 2, 0)], format="xyb",
                                dxfattribs={"layer": "ARQ-MURO"})
        pl.closed = True
        path = os.path.join(self.tmp, "bulge.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 1)
        self.assertIn("arcos", "\n".join(rep["warnings"]))
        self.assertIn("cuerdas", "\n".join(rep["warnings"]))

    def test_vertice_duplicado_consecutivo_cuenta_como_invalido(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (4, 0), (4, 0), (0, 3)],
                           format="xy", dxfattribs={"layer": "ARQ-MURO"})
        path = os.path.join(self.tmp, "dupv.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["walls"], 2)
        self.assertEqual(rep["counts"]["zero_length_or_invalid"], 1)

    def test_local_cerrado_geometrico_sin_flag(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (6, 0), (6, 4), (0, 4), (0, 0)],
                           format="xy", dxfattribs={"layer": "ARQ-LOCAL"})
        msp.add_text("SALA", dxfattribs={"layer": "ARQ-LOCAL",
                                         "insert": (1.5, 1.5)})
        path = os.path.join(self.tmp, "local.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["spaces"], 1)
        self.assertEqual(rep["spaces_preview"][0]["name"], "SALA")
        self.assertAlmostEqual(rep["spaces_preview"][0]["area_m2"], 24.0,
                               places=3)

    def test_local_abierto_sigue_avisando(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (6, 0), (6, 4), (0, 4)],
                           format="xy", dxfattribs={"layer": "ARQ-LOCAL"})
        path = os.path.join(self.tmp, "abierto.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["spaces"], 0)
        self.assertEqual(rep["counts"]["unclosed_polylines"], 1)
        self.assertIn("Polilínea abierta", "\n".join(rep["warnings"]))

    def test_textos_vacios_agrupados_por_capa(self):
        doc = self._doc()
        doc.layers.add(name="NOTAS", color=7)
        msp = doc.modelspace()
        msp.add_mtext("", dxfattribs={"layer": "ARQ-LOCAL"})
        msp.add_text("", dxfattribs={"layer": "NOTAS",
                                     "insert": (1, 1)})
        path = os.path.join(self.tmp, "vacios.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["textos_vacios"], 2)
        avisos = "\n".join(rep["warnings"])
        self.assertIn("1 texto(s) vacío(s) ignorados en capa 'ARQ-LOCAL'",
                      avisos)
        self.assertIn("1 texto(s) vacío(s) ignorados en capa 'NOTAS'",
                      avisos)
        self.assertLess(avisos.index("ARQ-LOCAL"), avisos.index("NOTAS"))

    def test_mtext_con_texto_se_cuenta_normal(self):
        doc = self._doc()
        msp = doc.modelspace()
        msp.add_mtext("CONSULTA 3", dxfattribs={"layer": "ARQ-LOCAL",
                                                "insert": (1, 1)})
        path = os.path.join(self.tmp, "mtext.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["counts"]["texts"], 1)
        self.assertEqual(rep["counts"]["textos_vacios"], 0)

    def test_escala_aplica_a_espacios_y_a_textos(self):
        doc = self._doc(unidades=4)
        msp = doc.modelspace()
        pl = msp.add_lwpolyline([(0, 0), (12000, 0), (12000, 8000),
                                 (0, 8000)], format="xy",
                                dxfattribs={"layer": "ARQ-LOCAL"})
        pl.closed = True
        msp.add_text("SALA", dxfattribs={"layer": "ARQ-LOCAL",
                                         "insert": (6000, 4000)})
        path = os.path.join(self.tmp, "mm.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        self.assertEqual(rep["unidades"]["escala"], 0.001)
        self.assertAlmostEqual(rep["spaces_preview"][0]["area_m2"], 96.0,
                               places=3)
        self.assertEqual(rep["spaces_preview"][0]["name"], "SALA")

    def test_escala_pies_aplica_a_muros(self):
        doc = self._doc(unidades=2)
        msp = doc.modelspace()
        msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "ARQ-MURO"})
        path = os.path.join(self.tmp, "pies.dxf")
        doc.saveas(path)
        rep = DxfImporter().preview(path)
        muro = rep["_walls"][0]
        self.assertAlmostEqual(muro["end"][0], 0.3048, places=6)

    def test_apply_crea_los_8_muros_del_plano_real_en_metros(self):
        from services.architecture_service import ArchitectureService
        path = _dx_real(os.path.join(self.tmp, "ap.dxf"))
        context = self.application.create_project(
            self.project_path("imp.arqgen"), name="AP Morgue")
        counts = DxfImporter().apply(path, ArchitectureService(context),
                                     "PB AP")
        context.commit()
        self.assertEqual(counts["walls"], 8)
        self.assertEqual(counts["spaces"], 0)
        walls = context.architecture.list("WALL", context.project.id)
        self.assertEqual(len(walls), 8)
        for w in walls:
            self.assertGreaterEqual(min(w.start[0], w.end[0]), 0.17)
            self.assertLessEqual(max(w.start[0], w.end[0]), 17.69)
        rows = context.audit_repo.query(command="IMPORT_DXF",
                                        object_id=context.project.id)
        self.assertTrue(rows)
        context.close()


# ---------------------------------------------------------------------------
# 4) CONTORNOS «desde dibujo» con el plano real
# ---------------------------------------------------------------------------

class TestContornosDxf(ARQGenTestCase):
    """El contorno del usuario aparece: 174.91 m2, ortogonal, en m."""

    def test_contorno_real_detectado(self):
        path = _dx_real(os.path.join(self.tmp, "real.dxf"))
        cs = dd.contornos_dxf(path)
        self.assertEqual(len(cs), 1)
        c = cs[0]
        self.assertEqual(c["nombre"], "Contorno 1 (MURO)")
        self.assertEqual(c["capa"], "MURO")
        self.assertEqual(c["forma"], "ortogonal")
        self.assertEqual(len(c["puntos"]), 8)
        self.assertAlmostEqual(c["area_m2"], 174.91, places=2)
        self.assertAlmostEqual(c["ancho_m"], 17.5021, places=3)
        self.assertAlmostEqual(c["fondo_m"], 14.9701, places=3)
        self.assertNotIn("cerrada_auto", c)

    def test_contorno_casi_cerrado_se_cierra_solo(self):
        import ezdxf
        doc = ezdxf.new("R2010")
        doc.layers.add(name="PLANTA", color=7)
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (24, 0), (24, 14), (0, 14), (0.012, 0)],
                           format="xy", dxfattribs={"layer": "PLANTA"})
        path = os.path.join(self.tmp, "hueco.dxf")
        doc.saveas(path)
        cs = dd.contornos_dxf(path)
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].get("cerrada_auto"))
        self.assertAlmostEqual(cs[0]["hueco_m"], 0.012, places=4)

    def test_contorno_abierto_de_verdad_no_se_incluye(self):
        import ezdxf
        doc = ezdxf.new("R2010")
        doc.layers.add(name="PLANTA", color=7)
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (24, 0), (24, 14), (0, 14)],
                           format="xy", dxfattribs={"layer": "PLANTA"})
        path = os.path.join(self.tmp, "abierto.dxf")
        doc.saveas(path)
        self.assertEqual(dd.contornos_dxf(path), [])

    def test_polilinea_clasica_cerrada_por_flag_sigue_igual(self):
        import ezdxf
        doc = ezdxf.new("R2010")
        doc.layers.add(name="PLANTA", color=7)
        msp = doc.modelspace()
        pl = msp.add_lwpolyline([(0, 0), (12, 0), (12, 8), (0, 8)],
                                format="xy", dxfattribs={"layer": "PLANTA"})
        pl.closed = True
        p3 = msp.add_polyline2d([(0, 0), (2, 0), (2, 2), (0, 2)])
        p3.dxf.flags = p3.dxf.flags | 1  # bit 1 = cerrada (persistente)
        path = os.path.join(self.tmp, "clasica.dxf")
        doc.saveas(path)
        cs = dd.contornos_dxf(path)
        self.assertEqual(len(cs), 2)
        self.assertAlmostEqual(cs[0]["area_m2"], 96.0, places=3)
        self.assertAlmostEqual(cs[1]["area_m2"], 4.0, places=3)

    def test_contorno_en_milimetros_se_escalaa_metros(self):
        # réplica con contorno recto de 12000 x 8000 mm en otra capa
        import ezdxf
        doc = ezdxf.new("R2013")
        doc.header["$INSUNITS"] = 4
        doc.layers.add(name="A-PISO", color=8)
        msp = doc.modelspace()
        pl = msp.add_lwpolyline([(0, 0), (12000, 0), (12000, 8000),
                                 (0, 8000)], format="xy",
                                dxfattribs={"layer": "A-PISO"})
        pl.closed = True
        path = os.path.join(self.tmp, "piso.dxf")
        doc.saveas(path)
        cs = dd.contornos_dxf(path)
        self.assertEqual(len(cs), 1)
        self.assertAlmostEqual(cs[0]["area_m2"], 96.0, places=3)
        self.assertEqual(cs[0]["forma"], "rectangulo")

    def test_inexistente_e_ilegible(self):
        with self.assertRaises(DomainError) as ctx:
            dd.contornos_dxf(os.path.join(self.tmp, "no.dxf"))
        self.assertEqual(_codigo(ctx.exception), "ARQ-DDI-004")
        basura = os.path.join(self.tmp, "basura.dxf")
        with open(basura, "wb") as fh:
            fh.write(b"esto no es un DXF")
        with self.assertRaises(DomainError) as ctx2:
            dd.contornos_dxf(basura)
        self.assertEqual(_codigo(ctx2.exception), "ARQ-DDI-005")


# ---------------------------------------------------------------------------
# 5) FLUJO desde dibujo -> servicio con el plano real
# ---------------------------------------------------------------------------

class TestFlujoDesdeDibujoServicio(ARQGenTestCase):
    """Explorar catálogo, crecer a 2 niveles y generar el edificio."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._dir = tempfile.mkdtemp(prefix="arq_dxf_real_")
        cls.contorno = dd.contornos_dxf(
            _dx_real(os.path.join(cls._dir, "real.dxf")))[0]

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._dir, ignore_errors=True)

    def test_exploracion_del_catalogo_ordenada(self):
        res = dd.explorar_catalogo(self.contorno["puntos"])
        self.assertEqual(len(res), 34)
        self.assertEqual(res[0]["codigo"], "FARMACIA")
        self.assertTrue(res[0]["cabe_un_nivel"])
        estados = [(0 if r["cabe_un_nivel"] else
                    (2 if r.get("error") else 1)) for r in res]
        self.assertEqual(estados, sorted(estados))
        errores = [r for r in res if r.get("error")]
        self.assertTrue(errores)
        almacen = next(r for r in res
                       if r["codigo"] == "ALMACEN_LOGISTICO")
        self.assertEqual(almacen["error"], "ARQ-DDI-003")
        morgue = next(r for r in res if r["codigo"] == "MORGUE")
        # v3.42.0: cada nivel lleva su pasillo servido por locales
        # re-dimensionados: con las áreas ídeas el servicio necesita
        # 3 niveles (con ajuste medio/estricto cabe en 1)
        self.assertEqual(morgue["niveles"], 3)
        self.assertFalse(morgue["cabe_un_nivel"])
        ap = next(r for r in res if r["codigo"] == "ANATOMIA_PATOLOGICA")
        self.assertEqual(ap["niveles"], 4)

    def test_texto_exploracion_cp1252(self):
        res = dd.explorar_catalogo(self.contorno["puntos"])
        texto = dd.texto_exploracion(res, self.contorno["area_m2"])
        data = texto.encode("cp1252")  # no debe lanzar
        self.assertIn(b"EXPLORACION DEL CATALOGO", data)
        self.assertIn(b"Area del contorno: 174.91 m2", data)
        self.assertIn(b"FARMACIA", data)

    def test_morgue_crece_a_dos_niveles_con_escalera(self):
        prog = eng.programa_servicio("MORGUE", {})
        self.assertEqual(prog["totales"]["locales"], 18)  # + filtro
        self.assertAlmostEqual(prog["totales"]["area_m2"], 203.4, places=1)
        aj = dd.ajustar(prog, self.contorno["puntos"])
        self.assertFalse(aj["cabe_un_nivel"])
        # v3.42.0: con las áreas ideales y pasillo en cada nivel son
        # 3 niveles ([10, 7, 1]); con ajuste medio/estricto cabe en 1
        self.assertEqual(aj["niveles"], 3)
        self.assertTrue(aj.get("con_escalera"))
        self.assertTrue(aj.get("escalera"))
        self.assertTrue(str(aj["escalera"]["descripcion"]).strip())
        self.assertEqual([len(p["locales"]) for p in aj["reparto"]],
                         [10, 7, 1])
        # TODOS los niveles llevan pasillo de distribución
        self.assertTrue(all(p["pasillo"] for p in aj["reparto"]))
        # v3.40.0: el encaje estricto pone TODO dentro del polígono
        # real (antes se salía y solo se avisaba)
        self.assertTrue(aj["dentro_del_contorno"])
        from domain.desde_dibujo import rect_dentro as _rd
        for p in aj["reparto"]:
            for r in p["locales"]:
                self.assertTrue(
                    _rd([tuple(q) for q in r["rect"]],
                        self.contorno["puntos"]), r["nombre"])
        avisos = "\n".join(aj.get("avisos", []))
        self.assertIn("encaje estricto", avisos)
        aj["programa"] = prog
        dd.texto_ajuste(aj).encode("cp1252")

    def test_ap_crece_a_tres_niveles(self):
        prog = eng.programa_servicio("ANATOMIA_PATOLOGICA", {})
        self.assertEqual(prog["totales"]["locales"], 17)  # + filtro
        self.assertAlmostEqual(prog["totales"]["area_m2"], 257.7, places=1)
        aj = dd.ajustar(prog, self.contorno["puntos"])
        self.assertEqual(aj["niveles"], 4)

    def test_aplicar_plan_genera_el_edificio_morgue(self):
        from services.architecture_service import ArchitectureService
        context = self.application.create_project(
            self.project_path("morgue.arqgen"), name="AP y Morgue")
        prog = eng.programa_servicio("MORGUE", {})
        aj = dd.ajustar(prog, self.contorno["puntos"])
        resumen = dd.aplicar_plan(
            context, aj, {"nombre_edificio": "AP y Morgue",
                          "modo": "servicio"})
        context.commit()
        self.assertEqual(resumen["edificio"], "AP y Morgue")
        self.assertEqual(resumen["niveles"],
                         ["Planta 1", "Planta 2", "Planta 3"])
        self.assertEqual(resumen["modo"], "servicio")
        # v3.40.0: los locales de la morgue son más profundos que
        # v3.42.0: 3 niveles CON pasillo de distribución en cada uno
        # (con ajuste estricto sería 1 nivel): 18 locales + 3 pasillos
        # + 3 escaleras
        self.assertEqual(len(resumen["espacios"]), 24)
        self.assertAlmostEqual(resumen["altura_total_m"], 9.0, places=3)
        self.assertAlmostEqual(resumen["area_contorno_m2"], 174.91,
                               places=2)
        espacios = context.architecture.list("SPACE", context.project.id)
        self.assertEqual(len(espacios), 24)
        usos = {s.space_type for s in espacios}
        # v3.42.0: la morgue sale CON pasillo y CON filtro sanitario
        self.assertIn("CORRIDOR", usos)
        self.assertIn("FILTER", usos)
        self.assertIn("STAIR", usos)
        # y NADA se sale del polígono dibujado
        from domain.desde_dibujo import rect_dentro as _rd
        for s in espacios:
            if s.space_type == "STAIR":
                continue
            pts_ = [tuple(p) for p in (s.boundary or [])]
            if len(pts_) == 4:
                self.assertTrue(_rd(pts_, self.contorno["puntos"]),
                                s.name)
        niveles = {s.level_id for s in espacios}
        self.assertEqual(len(niveles), 3)
        dd.texto_resumen_generacion(resumen).encode("cp1252")
        context.close()


# ---------------------------------------------------------------------------
# 6) GANCHOS DE VENTANA (con display)
# ---------------------------------------------------------------------------

@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestGanchosVentana(ARQGenTestCase):
    """El diálogo de importación y el panel desde dibujo muestran la
    nueva información del plano real."""

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
        self.window._dxf_sync = True

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        if self._old_env is None:
            os.environ.pop("ARQGEN_PREFS", None)
        else:
            os.environ["ARQGEN_PREFS"] = self._old_env
        super().tearDown()

    def test_analisis_del_plano_real_muestra_unidades_y_8_muros(self):
        path = _dx_real(os.path.join(self.tmp, "AP Y MORGUE.dxf"))
        self.window.open_importar_dxf()
        self.window._dxf_path.insert(0, path)
        self.window._dxf_analyze()
        report = self.window._dxf_report.get("1.0", "end")
        self.assertIn("ANÁLISIS COMPLETADO", report)
        self.assertIn("Unidades del plano: milímetros", report)
        self.assertIn("escala 0.001 a metros", report)
        self.assertIn("Contorno de planta con 8 lados", report)
        self.assertIn("texto(s) vacío(s)", report)
        counts = self.window._dxf_result.get("counts", {})
        self.assertEqual(counts.get("walls"), 8)
        self.assertEqual(counts.get("textos_vacios"), 2)
        self.assertIn("Listo para importar", self.window._dxf_status.get())

    def test_importar_el_plano_real_desde_la_ventana(self):
        path = _dx_real(os.path.join(self.tmp, "AP Y MORGUE.dxf"))
        self.window.open_importar_dxf()
        self.window._dxf_path.insert(0, path)
        self.window._dxf_level.delete(0, "end")
        self.window._dxf_level.insert(0, "PB AP")
        self.window._dxf_analyze()
        self.window._dxf_apply()
        report = self.window._dxf_report.get("1.0", "end")
        self.assertIn("PLANO IMPORTADO", report)
        self.assertIn("Muros creados: 8", report)
        # el proyecto demo ya trae muros: solo cuentan los del nivel
        # recién importado (level_id referencia el id interno del nivel)
        niveles = {lv.id: lv.name for lv in self.context.architecture
                   .list("LEVEL", self.context.project.id)}
        nivel_pb = next(c for c, n in niveles.items() if n == "PB AP")
        walls = [w for w in self.context.architecture.list(
            "WALL", self.context.project.id)
            if w.level_id == nivel_pb]
        self.assertEqual(len(walls), 8)
        for w in walls:
            self.assertLessEqual(max(w.start[0], w.end[0]), 17.69)
            self.assertGreaterEqual(min(w.start[0], w.end[0]), 0.17)

    def test_analisis_sin_unidades_no_muestra_linea_de_escala(self):
        import ezdxf
        doc = ezdxf.new("R2010")
        doc.layers.add(name="ARQ-MURO", color=7)
        doc.modelspace().add_line((0, 0), (2, 0),
                                  dxfattribs={"layer": "ARQ-MURO"})
        path = os.path.join(self.tmp, "plano.dxf")
        doc.saveas(path)
        self.window.open_importar_dxf()
        self.window._dxf_path.insert(0, path)
        self.window._dxf_analyze()
        self.assertNotIn("Unidades del plano",
                         self.window._dxf_report.get("1.0", "end"))

    def test_combobox_de_contornos_marca_el_cierre_automatico(self):
        from domain import desde_dibujo as dd
        real = _dx_real(os.path.join(self.tmp, "real.dxf"))
        hueco = os.path.join(self.tmp, "hueco.dxf")
        import ezdxf
        doc = ezdxf.new("R2010")
        doc.layers.add(name="PLANTA", color=7)
        doc.modelspace().add_lwpolyline(
            [(0, 0), (24, 0), (24, 14), (0, 14), (0.012, 0)],
            format="xy", dxfattribs={"layer": "PLANTA"})
        doc.saveas(hueco)
        self.window.open_desde_dibujo_dialog()
        self.window._dd_contornos = dd.contornos_dxf(real)
        self.window._dd_refresca_contornos()
        valores = list(self.window._dd_contornos_combo.cget("values"))
        self.assertEqual(valores[0], "Contorno 1 (MURO)")
        self.window._dd_contornos = dd.contornos_dxf(hueco)
        self.window._dd_refresca_contornos()
        valores = list(self.window._dd_contornos_combo.cget("values"))
        self.assertIn("cerrada automáticamente", valores[0])

    def test_version_coherente_con_v3410(self):
        from ui import help as h
        self.assertEqual(APP_VERSION, "3.50.0")
        self.assertIn("desde_dibujo", h.TOOLTIPS)


if __name__ == "__main__":
    unittest.main()
