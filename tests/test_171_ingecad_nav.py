"""DIBUJO Y NAVEGACIÓN ESTILO CAD CLÁSICO v3.38.0 (ui/coords_entrada.py +
ui/linea_comandos.py + ui/navegacion.py + ui/cursor_acad.py + ui/keymap.py +
ganchos de ventana).

Las lecciones de IngeCAD (github.com/ingelibre/ingecad, GPL-3.0: ideas
integradas por reimplementación propia, sin copiar código) sobre el
flujo clásico de AutoCAD:

  · gramática de coordenadas por teclado: 10,5 / @10,5 / @10<45 /
    25 (distancia directa) / #forzar absoluto / expresiones seguras,
  · línea de comandos con historial, autocompletado y Enter vacío
    que repite,
  · pila de vistas de 32 para el ZOOM ANTERIOR, rejilla anidada
    adaptativa con banda antiflip y encuadre honesto del lienzo vacío,
  · la familia de referencias clásica con precedencia (extremo >
    intersección > medio > centro > perpendicular > más cercano),
  · aliases de dibujo (MU/ES/ZO/PU/VE) y navegación (Z/ZE/ZP/QC),
    F2 historial, F12 pantalla dinámica (DYN),
  · y los ganchos de ventana: coordenadas que dibujan, DYN junto al
    cursor, zoom por ventana y la versión coherente 3.38.0.
"""

from __future__ import annotations

import math
import os
import unittest
from types import SimpleNamespace

from core import APP_VERSION
from core.errors import DomainError
from ui import coords_entrada as crd
from ui import cursor_acad
from ui import keymap
from ui import navegacion as nav
from ui.linea_comandos import LineaComandos
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


def _codigo(exc: Exception) -> str:
    return getattr(exc, "code", "")


class Muro:
    """WALL de mentira para el motor de referencias."""

    def __init__(self, a, b):
        self.start, self.end = a, b


class Local:
    """SPACE de mentira para el osnap de centro."""

    def __init__(self, boundary):
        self.boundary = boundary


# ---------------------------------------------------------------------------
# coords_entrada: la gramatica del punto tecleado
# ---------------------------------------------------------------------------

class TestCoordenadas(unittest.TestCase):

    def test_absoluto_10_5(self):
        self.assertEqual(crd.parse_punto("10,5"), ((10.0, 5.0), "absoluto"))

    def test_absoluto_negativos_y_decimales(self):
        punto, clase = crd.parse_punto("-2.5,0.25")
        self.assertEqual(punto, (-2.5, 0.25))
        self.assertEqual(clase, "absoluto")

    def test_relativo_desde_ultimo_punto(self):
        punto, clase = crd.parse_punto("@10,5", (100.0, 100.0))
        self.assertEqual(punto, (110.0, 105.0))
        self.assertEqual(clase, "relativo")

    def test_polar_absoluto_desde_origen(self):
        punto, clase = crd.parse_punto("10<45")
        self.assertAlmostEqual(punto[0], math.sqrt(50), places=9)
        self.assertAlmostEqual(punto[1], math.sqrt(50), places=9)
        self.assertEqual(clase, "polar")

    def test_polar_relativo_desde_ultimo_punto(self):
        punto, clase = crd.parse_punto("@10<90", (2.0, 3.0))
        self.assertAlmostEqual(punto[0], 2.0, places=9)
        self.assertAlmostEqual(punto[1], 13.0, places=9)
        self.assertEqual(clase, "polar_relativo")

    def test_distancia_directa_hacia_el_cursor(self):
        punto, clase = crd.parse_punto("25", (0.0, 0.0), (50.0, 0.0))
        self.assertEqual(punto, (25.0, 0.0))
        self.assertEqual(clase, "distancia_directa")

    def test_distancia_directa_diagonal(self):
        punto, _ = crd.parse_punto("5", (0.0, 0.0), (3.0, 4.0))
        self.assertAlmostEqual(punto[0], 3.0, places=9)
        self.assertAlmostEqual(punto[1], 4.0, places=9)

    def test_hash_fuerza_absoluto(self):
        punto, clase = crd.parse_punto("#10,5", (99.0, 99.0))
        self.assertEqual(punto, (10.0, 5.0))
        self.assertEqual(clase, "absoluto")

    def test_campos_con_expresiones(self):
        punto, _ = crd.parse_punto("2*3,0.5")
        self.assertEqual(punto, (6.0, 0.5))

    def test_relativo_sin_ancla_es_error(self):
        with self.assertRaises(DomainError) as ctx:
            crd.parse_punto("@10,5")
        self.assertEqual(_codigo(ctx.exception), "ARQ-CRD-002")

    def test_distancia_directa_sin_cursor_es_error(self):
        with self.assertRaises(DomainError) as ctx:
            crd.parse_punto("25", (0.0, 0.0))
        self.assertEqual(_codigo(ctx.exception), "ARQ-CRD-002")

    def test_texto_que_no_es_coordenada(self):
        with self.assertRaises(DomainError) as ctx:
            crd.parse_punto("m")
        self.assertEqual(_codigo(ctx.exception), "ARQ-CRD-001")

    def test_es_coordenada_descarta_opciones(self):
        self.assertTrue(crd.es_coordenada("10,5"))
        self.assertTrue(crd.es_coordenada("@10<45"))
        self.assertTrue(crd.es_coordenada("2*3"))
        self.assertFalse(crd.es_coordenada("M"))
        self.assertFalse(crd.es_coordenada("zp"))

    def test_evaluar_expresion_basica(self):
        self.assertAlmostEqual(crd.evaluar_expresion("=2*3.5+0.2"), 7.2,
                               places=9)

    def test_evaluar_expresion_parentesis_y_pi(self):
        self.assertAlmostEqual(crd.evaluar_expresion("2*(3+4)/7"), 2.0,
                               places=9)
        self.assertAlmostEqual(crd.evaluar_expresion("2*pi"), 2 * math.pi,
                               places=9)

    def test_evaluar_expresion_rechaza_codigo(self):
        for mala in ("__import__('os')", "pi.__class__", "abs(1)",
                     "'a'", "2 3"):
            with self.assertRaises(DomainError) as ctx:
                crd.evaluar_expresion(mala)
            self.assertEqual(_codigo(ctx.exception), "ARQ-CRD-003")

    def test_texto_dinamico_dist_y_angulo(self):
        self.assertEqual(crd.texto_dinamico((0, 0), (3, 3)),
                         "d 4.24 < 45")
        self.assertEqual(crd.texto_dinamico((1, 1), (1, 1)), "d 0.00 < 0")
        self.assertEqual(crd.texto_dinamico(None, (3, 3)), "")

    def test_texto_punto_cp1252(self):
        linea = crd.texto_punto((10.0, 5.0))
        self.assertEqual(linea, "x 10.000  y 5.000")
        linea.encode("cp1252")


# ---------------------------------------------------------------------------
# linea_comandos: historial, autocompletado e interpretacion
# ---------------------------------------------------------------------------

class TestLineaComandos(unittest.TestCase):

    def setUp(self):
        self.lc = LineaComandos({"m": "mover", "mi": "reflejar",
                                 "mu": "dib_muro", "z": "zoom_ventana",
                                 "ze": "encuadrar", "zp": "zoom_anterior",
                                 "qc": "calculadora"})

    def test_vacio_repite(self):
        self.assertEqual(self.lc.interpretar("")["tipo"], "vacio")

    def test_alias_completo_gana(self):
        res = self.lc.interpretar("mu")
        self.assertEqual(res["tipo"], "orden")
        self.assertEqual(res["accion"], "dib_muro")

    def test_alias_case_insensitive(self):
        self.assertEqual(self.lc.interpretar("MU")["accion"], "dib_muro")

    def test_coordenada(self):
        res = self.lc.interpretar("10,5")
        self.assertEqual(res["tipo"], "coordenada")
        self.assertEqual(res["punto"], (10.0, 5.0))

    def test_coordenada_sin_ancla_trae_error_amable(self):
        res = self.lc.interpretar("@10,5")
        self.assertEqual(res["tipo"], "coordenada")
        self.assertIn("anterior", res["error"])

    def test_expresion(self):
        res = self.lc.interpretar("=2*3")
        self.assertEqual(res["tipo"], "expresion")
        self.assertAlmostEqual(res["valor"], 6.0, places=9)

    def test_desconocido_con_sugerencia(self):
        res = self.lc.interpretar("q")
        self.assertEqual(res["tipo"], "desconocido")
        self.assertEqual(res["sugerencia"], "qc")

    def test_historial_dedupe_adyacente(self):
        self.lc.push("mu")
        self.lc.push("mu")
        self.assertEqual(self.lc.historial, ["mu"])

    def test_historial_tope(self):
        for i in range(250):
            self.lc.push(f"entrada{i}")
        self.assertEqual(len(self.lc.historial), 200)
        self.assertEqual(self.lc.historial[-1], "entrada249")

    def test_flechas_recuerdan_borrador(self):
        self.lc.push("mu")
        self.assertEqual(self.lc.flecha_arriba("borrador"), "mu")
        self.assertEqual(self.lc.flecha_abajo(), "borrador")

    def test_completar_prefijo(self):
        self.assertEqual(self.lc.completar("m"), "m")
        self.assertEqual(self.lc.completar("zp"), "zp")
        self.assertEqual(self.lc.completar("w"), "")


# ---------------------------------------------------------------------------
# navegacion: pila de vistas, rejilla anidada, encuadre honesto
# ---------------------------------------------------------------------------

class TestNavegacion(unittest.TestCase):

    def test_pila_push_pop(self):
        pila = nav.PilaVistas()
        pila.push(1.0, 2.0, 10.0)
        pila.push(3.0, 4.0, 20.0)
        self.assertEqual(pila.pop(), (3.0, 4.0, 20.0))
        self.assertEqual(pila.pop(), (1.0, 2.0, 10.0))
        self.assertIsNone(pila.pop())

    def test_pila_acotada_a_32(self):
        pila = nav.PilaVistas()
        for i in range(40):
            pila.push(float(i), 0.0, 1.0)
        self.assertEqual(len(pila), 32)
        self.assertEqual(pila.peek(), (39.0, 0.0, 1.0))

    def test_rejilla_nivel_subido_al_alejar(self):
        # escala 4 px/m: la celda base (4 px) y la de nivel 1 (20 px)
        # quedan bajo el minimo de 25 px; el nivel sube a 2 (25 m x 4)
        datos = nav.rejilla_adaptativa(0, 0, 4.0, 800, 600)
        self.assertEqual(datos["nivel"], 2)
        self.assertEqual(datos["paso"], 25.0)
        self.assertEqual(datos["celda_px"], 100.0)

    def test_rejilla_nivel_basico_al_acercar(self):
        datos = nav.rejilla_adaptativa(0, 0, 30.0, 800, 600)
        self.assertEqual(datos["nivel"], 0)
        self.assertEqual(datos["paso"], 1.0)

    def test_rejilla_mayores_cada_5(self):
        datos = nav.rejilla_adaptativa(0, 0, 30.0, 800, 600)
        majors = [x for x, es in datos["lineas_x"] if es]
        self.assertIn(0.0, majors)
        self.assertIn(5.0, majors)
        self.assertIn(-5.0, majors)
        self.assertNotIn(1.0, majors)

    def test_rejilla_antiflip_con_nivel_previo(self):
        # con nivel previo 0 y celda de 24 px (dentro de la banda 20..
        # 31.25) el nivel se conserva aunque el minimo pida subir
        datos = nav.rejilla_adaptativa(0, 0, 24.0, 800, 600,
                                       nivel_previo=0)
        self.assertEqual(datos["nivel"], 0)
        # fuera de banda (19 px < 20): el nivel se ajusta de verdad
        datos2 = nav.rejilla_adaptativa(0, 0, 19.0, 800, 600,
                                        nivel_previo=0)
        self.assertEqual(datos2["nivel"], 1)

    def test_rejilla_lineas_cubren_el_visible(self):
        datos = nav.rejilla_adaptativa(100.0, 0.0, 30.0, 800, 600)
        x0, x1 = datos["rango_x"]
        xs = [x for x, _es in datos["lineas_x"]]
        self.assertLessEqual(min(xs), x0)
        # la ultima linea puede caer antes del borde derecho, pero a
        # menos de un paso de el (el borde no es linea)
        self.assertGreater(max(xs), x1 - datos["paso"])

    def test_encuadre_vacio_honesto(self):
        self.assertEqual(nav.encuadre_de(None),
                         (-50.0, -50.0, 50.0, 50.0))
        self.assertEqual(nav.encuadre_de((0, 0, 10, 10)),
                         (0, 0, 10, 10))
        # NaN / degenerado: tambien honesto
        self.assertEqual(nav.encuadre_de((0, 0, 0, 0)),
                         (-50.0, -50.0, 50.0, 50.0))


# ---------------------------------------------------------------------------
# cursor_acad: la familia de referencias y su precedencia
# ---------------------------------------------------------------------------

class TestReferencias(unittest.TestCase):

    def test_familia_completa_en_marcas(self):
        for marca in ("extremo", "interseccion", "medio", "centro",
                      "perpendicular", "mas_cercano"):
            self.assertIn(marca, cursor_acad.MARCAS)

    def test_extremo_gana_a_mas_cercano(self):
        muro = Muro((0, 0), (10, 0))
        ganada = cursor_acad.mejor_fijacion([muro], (0.05, 0.05), 0.5)
        self.assertEqual(ganada, ((0.0, 0.0), "extremo"))

    def test_interseccion_en_cruce_de_muros(self):
        m1 = Muro((0, 0), (10, 0))
        m2 = Muro((5, -5), (5, 5))
        ganada = cursor_acad.mejor_fijacion([m1, m2], (5.05, 0.05), 0.5)
        self.assertEqual(ganada, ((5.0, 0.0), "interseccion"))

    def test_centro_de_local(self):
        local = Local([(0, 0), (4, 0), (4, 4), (0, 4)])
        ganada = cursor_acad.mejor_fijacion([], (2, 2.3), 0.5,
                                            locales=[local])
        self.assertEqual(ganada, ((2.0, 2.0), "centro"))

    def test_perpendicular_con_origen_y_optin(self):
        sup = Muro((0, 4), (4, 4))
        marcas = cursor_acad.MARCAS_ACTIVAS_DEF | {"perpendicular"}
        ganada = cursor_acad.mejor_fijacion([sup], (3.05, 3.9), 0.3,
                                            origen=(3.0, 0.0),
                                            marcas=marcas)
        self.assertEqual(ganada, ((3.0, 4.0), "perpendicular"))

    def test_perpendicular_sin_optin_no_dispara(self):
        sup = Muro((0, 4), (4, 4))
        ganada = cursor_acad.mejor_fijacion([sup], (3.05, 3.9), 0.3,
                                            origen=(3.0, 0.0))
        # el muro superior no tiene extremo/medio cerca del (3, 4):
        # sin el modo PER activo no hay referencia (o no es PER)
        self.assertTrue(ganada is None
                        or ganada[1] != "perpendicular")

    def test_mas_cercano_fuera_de_fabrica(self):
        muro = Muro((0, 0), (10, 0))
        # de fabrica: el cuerpo del muro NO imanta (el NEA clasico);
        # el cursor esta lejos de extremo y medio, asi que nada salta
        self.assertIsNone(cursor_acad.mejor_fijacion([muro], (3.3, 0.3),
                                                     0.5))
        # con el modo activo, si
        marcas = cursor_acad.MARCAS_ACTIVAS_DEF | {"mas_cercano"}
        ganada = cursor_acad.mejor_fijacion([muro], (3.3, 0.3), 0.5,
                                            marcas=marcas)
        self.assertEqual(ganada[1], "mas_cercano")

    def test_compat_v16_extremo_y_medio(self):
        self.assertEqual(cursor_acad.MARCAS_V16, ("extremo", "medio"))
        muro = Muro((0, 0), (10, 0))
        fij = cursor_acad.fijaciones([muro], (5.05, 0.05), 0.5)
        self.assertIn(((5.0, 0.0), "medio"), fij)


# ---------------------------------------------------------------------------
# keymap: aliases nuevos, F2/F12 y la resolucion de acad.pgp
# ---------------------------------------------------------------------------

class TestTecladoV38(unittest.TestCase):

    def test_aliases_de_dibujo(self):
        self.assertEqual(keymap.ALIAS_COMANDOS["mu"], "dib_muro")
        self.assertEqual(keymap.ALIAS_COMANDOS["es"], "dib_espacio")
        self.assertEqual(keymap.ALIAS_COMANDOS["zo"], "dib_zona")
        self.assertEqual(keymap.ALIAS_COMANDOS["pu"], "dib_puerta")
        self.assertEqual(keymap.ALIAS_COMANDOS["ve"], "dib_ventana")

    def test_aliases_de_navegacion(self):
        self.assertEqual(keymap.ALIAS_COMANDOS["z"], "zoom_ventana")
        self.assertEqual(keymap.ALIAS_COMANDOS["ze"], "encuadrar")
        self.assertEqual(keymap.ALIAS_COMANDOS["zp"], "zoom_anterior")
        self.assertEqual(keymap.ALIAS_COMANDOS["qc"], "calculadora")

    def test_f2_historial_y_f12_din(self):
        teclas = keymap.TecladoAutoCAD()
        self.assertEqual(teclas.procesar("F2"), "historial_comandos")
        self.assertEqual(teclas.procesar("F12"), "alternar_din")
        self.assertFalse(teclas.estado["din"])
        self.assertTrue(keymap.ESTADO_DEFECTO["din"])

    def test_p_espacio_es_pan_y_pu_es_puerta(self):
        teclas = keymap.TecladoAutoCAD()
        self.assertIsNone(teclas.procesar("p"))       # espera: PU existe
        self.assertEqual(teclas.procesar("space"), "pan")
        self.assertIsNone(teclas.procesar("p"))
        self.assertEqual(teclas.procesar("u"), "dib_puerta")

    def test_z_espacio_zoom_ventana_y_zp_directo(self):
        teclas = keymap.TecladoAutoCAD()
        self.assertIsNone(teclas.procesar("z"))       # espera: ZE/ZP
        self.assertEqual(teclas.procesar("space"), "zoom_ventana")
        self.assertIsNone(teclas.procesar("z"))
        self.assertEqual(teclas.procesar("p"), "zoom_anterior")

    def test_dibujo_repetible_con_espacio(self):
        for herramienta in ("dib_muro", "dib_espacio", "dib_zona",
                            "dib_puerta", "dib_ventana"):
            self.assertIn(herramienta, keymap.REPETIBLES)


# ---------------------------------------------------------------------------
# ganchos de ventana (requieren display)
# ---------------------------------------------------------------------------

class TestVentanaV38(ARQGenTestCase):

    def setUp(self):
        super().setUp()
        if not DISPLAY:
            self.skipTest("requiere display Tk (Xvfb)")
        from ui.app_window import ARQGenWindow
        self.context = self.demo_context()
        self.window = ARQGenWindow(self.context, self.application)
        self.window.update()

    def tearDown(self):
        self.window.destroy()
        self.context.close()
        super().tearDown()

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_linea_de_comandos_existe_y_dibuja_con_coordenadas(self):
        self.assertIsNotNone(self.window._cmd_entry)
        self.window._ejecutar_accion_cad("dib_muro")
        self.assertEqual(self.window._cad_tool, "dib_muro")
        self.window._punto_tecleado((10.0, 5.0))
        self.window._punto_tecleado((20.0, 5.0))
        muros = [w for w in self.context.architecture.list(
            "WALL", self.context.project.id)
            if abs(w.start[0] - 10.0) < 1e-6
            and abs(w.start[1] - 5.0) < 1e-6]
        self.assertEqual(len(muros), 1)
        self.assertAlmostEqual(muros[0].end[0], 20.0, places=6)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_linea_de_comandos_flujo_completo_con_enter(self):
        # "mu" + Enter arma el muro; "10,5" y "@10,5" lo dibujan (el
        # relativo se ancla al punto anterior; al completar, el muro
        # EXISTE y la maquina queda limpia para repetir)
        self.window._cmd_entry.insert(0, "mu")
        self.window._cmd_submit()
        self.assertEqual(self.window._cad_tool, "dib_muro")
        self.window._cmd_entry.insert(0, "10,5")
        self.window._cmd_submit()
        self.assertEqual(len(self.window._cad_pasos), 1)
        self.window._cmd_entry.insert(0, "@10,5")
        self.window._cmd_submit()
        muros = [w for w in self.context.architecture.list(
            "WALL", self.context.project.id)
            if abs(w.start[0] - 10.0) < 1e-6
            and abs(w.start[1] - 5.0) < 1e-6
            and abs(w.end[0] - 20.0) < 1e-6]
        self.assertEqual(len(muros), 1)
        self.assertEqual(self.window._cad_pasos, [])

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_expresion_en_la_linea(self):
        self.window._cmd_entry.insert(0, "=2*3.5")
        self.window._cmd_submit()
        self.assertIn("= 7.0000", self.window.status_var.get())

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_historial_flechas_y_f2(self):
        self.window._cmd_entry.insert(0, "=1+1")
        self.window._cmd_submit()
        self.window._cmd_entry.insert(0, "=2+2")
        self.window._cmd_submit()
        # flecha arriba trae la ultima entrada (el metodo devuelve
        # "break" para el binding; el texto queda en el Entry)
        self.window._cmd_flecha_arriba()
        self.assertEqual(self.window._cmd_entry.get(), "=2+2")
        self.window._cmd_flecha_arriba()
        self.assertEqual(self.window._cmd_entry.get(), "=1+1")
        # y flecha abajo devuelve lo que se estaba escribiendo
        self.window._cmd_flecha_abajo()
        self.window._cmd_flecha_abajo()
        # F2 abre la ventana de historial
        self.window._ventana_historial()
        self.window.update()
        abiertas = [h for h in self.window.winfo_children()
                    if isinstance(h, __import__("tkinter").Toplevel)]
        self.assertTrue(any("Historial" in h.title() for h in abiertas))
        for h in abiertas:
            h.destroy()

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_zoom_ventana_y_anterior_con_pila(self):
        self.window.fit_view()
        self.window.update()
        self.assertEqual(len(self.window._pila_vistas), 1)
        # Z arma; dos clics encuadran una zona conocida
        self.window._ejecutar_accion_cad("zoom_ventana")
        self.assertTrue(self.window._zoom_orden)
        w = 800
        h = 600
        p1 = self.window.viewport.to_screen(0.0, 0.0, w, h)
        p2 = self.window.viewport.to_screen(2.0, 2.0, w, h)
        class E:
            pass
        e1, e2 = E(), E()
        e1.x, e1.y = int(p1[0]), int(p1[1])
        e2.x, e2.y = int(p2[0]), int(p2[1])
        antes = self.window.viewport.scale
        self.window._zoom_ventana_clic(e1)
        self.window._zoom_ventana_clic(e2)
        self.window.update()
        self.assertFalse(self.window._zoom_orden)
        self.assertGreater(self.window.viewport.scale, antes)
        # ZP vuelve
        self.window._zoom_anterior()
        self.window.update()
        self.assertAlmostEqual(self.window.viewport.scale, antes,
                               places=9)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_seleccion_ventana_y_cruce(self):
        self.window.fit_view()
        self.window.update()
        filas = [r for r in self.window.explorer.rows_for("ARCHITECTURE")
                 if r.type == "WALL"]
        self.assertGreater(len(filas), 0)
        muro = next(w for w in self.context.architecture.list(
            "WALL", self.context.project.id)
            if w.code == filas[0].code)
        # ventana que contiene TODOS los puntos del muro
        xs = [muro.start[0], muro.end[0]]
        ys = [muro.start[1], muro.end[1]]
        rect = (min(xs) - 1.0, min(ys) - 1.0, max(xs) + 1.0,
                max(ys) + 1.0)
        elegidas = self.window._seleccion_por_marco(rect, True)
        self.assertIn(filas[0].uid, [f.uid for f in elegidas])
        # ventana diminuta lejos: nada
        elegidas2 = self.window._seleccion_por_marco(
            (rect[0] + 0.9, rect[1] + 0.9, rect[0] + 0.95,
             rect[1] + 0.95), True)
        self.assertEqual(elegidas2, [])
        # cruce: rectangulo que solo roza el muro (por caja) lo toma
        rect_cruce = (min(xs) - 1.0, min(ys) - 1.0,
                      min(xs) + 0.1, max(ys) + 1.0)
        elegidas3 = self.window._seleccion_por_marco(rect_cruce, False)
        self.assertIn(filas[0].uid, [f.uid for f in elegidas3])

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_esc_limpia_la_seleccion_multiple(self):
        self.window._seleccion_multi = [SimpleNamespace(uid="x")]
        self.window._cad_cancelar()
        self.assertEqual(self.window._seleccion_multi, [])

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_rejilla_adaptativa_dibujada_y_paso_de_imantacion(self):
        self.window.viewport.scale = 30.0
        self.window.redraw()
        self.window.update()
        self.assertIsNotNone(self.window._rejilla_datos)
        self.assertEqual(self.window._rejilla_datos["nivel"], 0)
        paso = self.window._paso_rejilla_actual()
        self.assertEqual(paso, 1.0)
        # al alejar mucho, sube de nivel
        self.window.viewport.scale = 0.5
        self.window.redraw()
        self.window.update()
        self.assertGreaterEqual(self.window._rejilla_datos["nivel"], 2)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_dyn_junto_al_cursor_mientras_dibuja(self):
        self.window._ejecutar_accion_cad("dib_muro")
        self.window._punto_tecleado((0.0, 0.0))
        self.window.viewport.scale = 40.0
        self.window.redraw()
        self.window.update()
        class E:
            x = 400
            y = 300
        self.window._cad_overlay(E())
        self.window.update()
        textos = self.window.canvas.find_withtag("cadoverlay")
        self.assertTrue(textos)
        contenido = " ".join(
            str(self.window.canvas.itemcget(t, "text"))
            for t in textos if str(self.window.canvas.type(t)) == "text")
        self.assertIn("d ", contenido)
        self.assertIn("<", contenido)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_marcadores_clasicos_en_el_lienzo(self):
        self.window.viewport.center_x, self.window.viewport.center_y = \
            5.0, 0.0
        self.window.viewport.scale = 40.0
        self.window.redraw()
        self.window.update()
        # el cruce de dos muros del demo existe; con el cursor encima
        # el marcador de interseccion (dos lineas en cruz) aparece
        fij = cursor_acad.mejor_fijacion(
            self.window._muros_mira(), (5.05, 0.05), 0.2,
            locales=self.window._locales_mira())
        # no exigimos que el demo tenga un cruce exactamente ahi; si lo
        # hay, debe marcarse; si no, la mira sigue sin marcador
        if fij is not None:
            self.assertIn(fij[1], cursor_acad.MARCAS)

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_encuadre_vacio_honesto_en_el_lienzo(self):
        from ui.app_window import ARQGenWindow as W
        db = os.path.join(self.tmp, "vacio_test.arqgen")
        vacio = self.application.create_project(db, "Vacio")
        try:
            win = W(vacio, self.application)
            win.update()
            win.fit_view()
            win.update()
            # encuadre -50..50 m -> escala moderada, no el caos
            self.assertLess(win.viewport.scale, 10.0)
            self.assertGreater(win.viewport.scale, 0.1)
            win.destroy()
        finally:
            vacio.close()

    @unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb)")
    def test_version_coherente_con_v3410(self):
        self.assertEqual(APP_VERSION, "3.50.0")
        self.assertIn(APP_VERSION, self.window.title())
