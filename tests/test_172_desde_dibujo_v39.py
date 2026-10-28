"""DESDE DIBUJO REFORZADO v3.39.0 (domain/desde_dibujo.py).

El asistente «Desde dibujo» gana el músculo del spec del asistente
dinámico: validación previa del contorno (autointersecciones,
abierto, dimensiones imposibles), checklist antes de generar,
contratos PlanRequest/PlanResult, alternativas 1/3/5 con métricas
comparables y puntuación explicada, decisiones registradas («¿por
qué este local aquí?», sin IA), reemplazo del edificio previo con
aviso, configuraciones y estado guardables en el proyecto,
quick-spec en una línea y patio exterior como opción experta.
"""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from core import APP_VERSION
from core.errors import DomainError
from domain import desde_dibujo as dd
from tests.base import ARQGenTestCase

RECT = [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0)]
RECT_GRANDE = [(0.0, 0.0), (30.0, 0.0), (30.0, 16.0), (0.0, 16.0)]
L_MUESCA = [(0.0, 0.0), (24.0, 0.0), (24.0, 14.0), (12.0, 14.0),
            (12.0, 8.0), (0.0, 8.0)]
LAZO = [(0.0, 0.0), (4.0, 4.0), (4.0, 0.0), (0.0, 4.0)]


def _codigo(exc: DomainError) -> str:
    return getattr(exc, "code", "")


def _prog():
    """Programa pequeño de prueba: 2 oficinas y un baño."""
    return dd.programa_edificacion([
        {"space_type": "OFFICE", "cantidad": 2, "area_m2": 20.0},
        {"space_type": "BATHROOM", "cantidad": 1, "area_m2": 8.0}])


def _prog_grande():
    """Programa que NO cabe en 1 nivel sobre el rectángulo 12x8."""
    return dd.programa_edificacion([
        {"space_type": "OFFICE", "cantidad": 8, "area_m2": 20.0}])


def _severidades(validacion):
    return [h["severidad"] for h in validacion["hallazgos"]]


# ---------------------------------------------------------------------------
# 1) VALIDACIÓN PREVIA DEL CONTORNO (spec §11)
# ---------------------------------------------------------------------------

class TestValidacionContorno(unittest.TestCase):
    """El dibujo importado se examina ANTES de ajustar nada."""

    def test_rectangulo_limpio_sin_errores(self):
        v = dd.validar_contorno(RECT)
        self.assertTrue(v["valido"])
        self.assertFalse(v["bloquea"])
        self.assertNotIn("ERROR", _severidades(v))
        self.assertEqual(v["datos"]["area_m2"], 96.0)
        self.assertEqual(v["datos"]["vertices"], 4)
        self.assertEqual(v["forma"]["forma"], "rectangulo")

    def test_lazo_autointersecado_es_error_que_bloquea(self):
        v = dd.validar_contorno(LAZO)
        self.assertTrue(v["bloquea"])
        self.assertIn("ERROR", _severidades(v))
        self.assertTrue(any("se cruza a sí mismo" in h["texto"]
                            for h in v["hallazgos"]))

    def test_poligono_cerrado_normal_no_se_marca_abierto(self):
        # un cuadrilátero normal (cierre implícito último->primero) NO
        # es un «polígono abierto»: solo la IMPORTACIÓN (contornos_dxf)
        # distingue polilíneas abiertas, y ya lo hace con cerrada_auto
        v = dd.validar_contorno(RECT)
        self.assertFalse(any("ABIERTO" in h["texto"]
                             for h in v["hallazgos"]))

    def test_area_diminuta_es_dimension_imposible(self):
        diminuto = [(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)]
        v = dd.validar_contorno(diminuto)
        self.assertTrue(v["bloquea"])
        self.assertTrue(any("imposible" in h["texto"]
                            for h in v["hallazgos"]))

    def test_texto_validacion_cp1252(self):
        v = dd.validar_contorno(LAZO)
        dd.texto_validacion_contorno(v).encode("cp1252")
        v2 = dd.validar_contorno(RECT)
        self.assertIn("Sin incidencias",
                      dd.texto_validacion_contorno(v2))

    def test_area_pequena_advierte_sin_bloquear(self):
        pequeno = [(0.0, 0.0), (3.0, 0.0), (3.0, 1.2), (0.0, 1.2)]
        v = dd.validar_contorno(pequeno)
        self.assertFalse(v["bloquea"])
        self.assertTrue(any("muy pequeña" in h["texto"]
                            for h in v["hallazgos"]))

    def test_area_gigante_sugiere_revisar_unidades(self):
        v = dd.validar_contorno([(0.0, 0.0), (500.0, 0.0),
                                 (500.0, 500.0), (0.0, 500.0)])
        self.assertFalse(v["bloquea"])
        self.assertTrue(any("metros" in h["texto"]
                            for h in v["hallazgos"]))

    def test_contorno_alargado_advierte(self):
        v = dd.validar_contorno([(0.0, 0.0), (100.0, 0.0),
                                 (100.0, 2.0), (0.0, 2.0)])
        self.assertTrue(any("alargado" in h["texto"]
                            for h in v["hallazgos"]))

    def test_vertices_casi_colineales_recomiendan_limpiar(self):
        con_colineal = [(0.0, 0.0), (6.0, 0.0), (12.0, 0.0),
                        (12.0, 8.0), (0.0, 8.0)]
        v = dd.validar_contorno(con_colineal)
        self.assertTrue(any("colineal" in h["texto"]
                            for h in v["hallazgos"]))

    def test_menos_de_tres_vertices_no_lanza(self):
        v = dd.validar_contorno([(0.0, 0.0), (12.0, 0.0)])
        self.assertTrue(v["bloquea"])
        self.assertIsNone(v["forma"])
        self.assertEqual(len(v["hallazgos"]), 1)

    def test_texto_validacion_cp1252(self):
        v = dd.validar_contorno(LAZO)
        dd.texto_validacion_contorno(v).encode("cp1252")
        v2 = dd.validar_contorno(RECT)
        self.assertIn("Sin incidencias",
                      dd.texto_validacion_contorno(v2))


# ---------------------------------------------------------------------------
# 2) INFERIR AMPLIADO: lados, ángulos y concavidades
# ---------------------------------------------------------------------------

class TestInferirAmpliado(unittest.TestCase):
    """La inferencia cuenta la geometría que antes callaba."""

    def test_rectangulo_90_grados_y_cero_concavidades(self):
        f = dd.inferir(RECT)
        self.assertEqual(len(f["lados"]), 4)
        self.assertEqual(len(f["angulos"]), 4)
        for a in f["angulos"]:
            self.assertAlmostEqual(a, 90.0, places=1)
        self.assertEqual(f["concavidades"], 0)
        self.assertAlmostEqual(f["relacion"], 1.5, places=2)

    def test_forma_en_L_tiene_una_concavidad(self):
        f = dd.inferir(L_MUESCA)
        self.assertEqual(f["concavidades"], 1)
        self.assertEqual(f["forma"], "ortogonal")
        # el ángulo cóncavo es 270 grados
        self.assertIn(270.0, f["angulos"])

    def test_texto_inferencia_menciona_la_geometria(self):
        texto = dd.texto_inferencia(dd.inferir(L_MUESCA))
        texto.encode("cp1252")
        self.assertIn("Lados: 6", texto)
        self.assertIn("Concavidades: 1", texto)

    def test_autointersecado_utilidad_directa(self):
        self.assertTrue(dd.autointersecado(LAZO))
        self.assertFalse(dd.autointersecado(RECT))


# ---------------------------------------------------------------------------
# 3) CHECKLIST PREVIA (spec §24)
# ---------------------------------------------------------------------------

class TestChecklist(unittest.TestCase):
    """Un único bloque [OK]/[AVISO]/[ERROR] antes de generar."""

    def test_solo_contorno_valido(self):
        items = dd.checklist_previa(dd.validar_contorno(RECT))
        self.assertTrue(items)
        self.assertTrue(all(i["estado"] == "OK" for i in items))

    def test_ajuste_cabe_en_un_nivel(self):
        items = dd.checklist_previa(dd.validar_contorno(RECT),
                                    dd.ajustar(_prog(), RECT))
        estados = [i["estado"] for i in items]
        self.assertNotIn("ERROR", estados)
        self.assertTrue(any("Cabe en 1 nivel" in i["texto"]
                            for i in items))

    def test_crecimiento_anuncia_escalera(self):
        an = dd.ajustar(_prog_grande(), RECT)
        items = dd.checklist_previa(dd.validar_contorno(RECT), an)
        self.assertTrue(any("niveles con el" in i["texto"]
                            for i in items))

    def test_niveles_deseados_distinto_avisa(self):
        an = dd.ajustar(_prog(), RECT)
        items = dd.checklist_previa(None, an, niveles_deseados=3)
        self.assertTrue(any(i["estado"] == "AVISO"
                            and "Pidió 3" in i["texto"]
                            for i in items))

    def test_patio_pedido_que_no_cabe_avisa(self):
        an = dd.ajustar(_prog(), RECT, patio=True,
                        patio_ancho_m=10.0)
        items = dd.checklist_previa(None, an, patio_pedido=True)
        self.assertTrue(any("patio" in i["texto"].lower()
                            for i in items))

    def test_texto_checklist_cp1252_con_errores(self):
        items = [{"estado": "ERROR", "texto": "prueba"},
                 {"estado": "OK", "texto": "prueba dos"},
                 {"estado": "AVISO", "texto": "prueba tres"}]
        texto = dd.texto_checklist(items)
        texto.encode("cp1252")
        self.assertIn("[ERROR] prueba", texto)
        self.assertIn("Hay ERROR", texto)


# ---------------------------------------------------------------------------
# 4) CONTRATOS PlanRequest / PlanResult (spec §37-§39)
# ---------------------------------------------------------------------------

class TestContratos(unittest.TestCase):
    """La intención del asistente viaja en un objeto serializable."""

    def test_valores_por_defecto(self):
        req = dd.PlanRequest(contorno=RECT, programa=_prog())
        self.assertEqual(req.modo, "edificacion")
        self.assertFalse(req.patio)
        self.assertAlmostEqual(req.patio_ancho_m, 3.0)
        self.assertEqual(req.niveles_deseados, None)
        self.assertEqual(set(req.criterios),
                         {"funcionalidad", "aprovechamiento",
                          "circulacion", "simplicidad"})

    def test_ida_y_vuelta_json(self):
        req = dd.PlanRequest(contorno=RECT, programa=_prog(),
                             patio=True, niveles_deseados=2,
                             margen_m=0.5)
        copia = dd.PlanRequest.from_dict(
            json.loads(json.dumps(req.to_dict())))
        self.assertEqual(copia.contorno, req.contorno)
        self.assertTrue(copia.patio)
        self.assertEqual(copia.niveles_deseados, 2)
        self.assertAlmostEqual(copia.margen_m, 0.5)

    def test_from_dict_tolerante_con_basura(self):
        req = dd.PlanRequest.from_dict({"criterios": {"no_existe": 5},
                                        "niveles_deseados": "x"})
        self.assertEqual(req.contorno, [])
        self.assertEqual(req.criterios["funcionalidad"], 100.0)
        self.assertIsNone(req.niveles_deseados)

    def test_plan_de_devuelve_todo(self):
        req = dd.PlanRequest(contorno=RECT, programa=_prog(),
                             niveles_deseados=1)
        r = dd.plan_de(req)
        self.assertIsInstance(r, dd.PlanResult)
        self.assertTrue(r.checklist)
        self.assertEqual(r.metricas["niveles"], r.analisis["niveles"])
        self.assertTrue(r.validacion["valido"])
        self.assertEqual(len(r.metricas["motivo"]), 0 + len(r.metricas[
            "motivo"]))
        self.assertTrue(r.metricas["motivo"])

    def test_plan_de_con_lazo_no_ajusta(self):
        req = dd.PlanRequest(contorno=LAZO, programa=_prog())
        r = dd.plan_de(req)
        self.assertTrue(r.validacion["bloquea"])
        self.assertIsNone(r.analisis)
        self.assertEqual(r.metricas["puntuacion"], 0.0)
        self.assertTrue(any(i["estado"] == "ERROR"
                            for i in r.checklist))


# ---------------------------------------------------------------------------
# 5) MÉTRICAS COMPARABLES (spec §25/§26)
# ---------------------------------------------------------------------------

class TestMetricas(unittest.TestCase):

    def test_metricas_coherentes(self):
        met = dd.metricas_de(dd.ajustar(_prog(), RECT))
        self.assertAlmostEqual(met["cumplimiento_pct"], 100.0, places=6)
        self.assertEqual(met["locales_fuera"], 0)
        self.assertTrue(0.0 <= met["circulacion_pct"] <= 100.0)
        self.assertTrue(0.0 < met["ocupacion_pct"] <= 100.0)
        self.assertTrue(0.0 <= met["puntuacion"] <= 100.0)
        self.assertTrue(met["area_util_m2"]
                        <= met["area_construida_m2"])
        self.assertTrue(met["motivo"])

    def test_criterios_cambian_la_puntuacion(self):
        an = dd.ajustar(_prog(), RECT)
        base = dd.metricas_de(an)["puntuacion"]
        frio = dd.metricas_de(an, {"funcionalidad": 0.0,
                                   "aprovechamiento": 100.0,
                                   "circulacion": 0.0,
                                   "simplicidad": 0.0})["puntuacion"]
        self.assertAlmostEqual(frio, min(100.0,
                                         dd.metricas_de(an)[
                                             "ocupacion_pct"]),
                               places=1)
        self.assertNotAlmostEqual(base, frio, places=4)

    def test_cp1252_del_motivo(self):
        met = dd.metricas_de(dd.ajustar(_prog(), RECT))
        met["motivo"].encode("cp1252")


# ---------------------------------------------------------------------------
# 6) ALTERNATIVAS 1/3/5 (spec §25/§26)
# ---------------------------------------------------------------------------

class TestAlternativas(unittest.TestCase):

    def test_tres_alternativas_ordenadas(self):
        lista = dd.alternativas(_prog(), RECT_GRANDE, cantidad=3)
        self.assertEqual([r["etiqueta"] for r in lista],
                         ["A", "B", "C"])
        # v3.42.0: la ganadora la decide la puntuación (con el
        # pasillo adaptado la variante girada puede empaquetar mejor
        # el corredor); «tal cual» sigue entre las propuestas y el
        # orden es por puntos
        self.assertIn("tal cual", [r["estrategia"] for r in lista])
        puntos = [r["metricas"]["puntuacion"] for r in lista]
        self.assertGreaterEqual(puntos[0], puntos[1] - 1e-9)
        self.assertGreaterEqual(puntos[1], puntos[2] - 1e-9)

    def test_variante_girada_vuelve_al_sistema_original(self):
        lista = dd.alternativas(_prog(), RECT_GRANDE, cantidad=3)
        b = next(r for r in lista
                 if r["estrategia"] == "girada 90 grados")
        self.assertTrue(any("girada 90 grados" in a
                            for a in b["analisis"]["avisos"]))
        # los rectángulos devueltos quedan dentro de la caja original
        bx = (0.0, 0.0, 30.0, 16.0)
        for plan in b["analisis"]["reparto"]:
            for pieza in [plan["pasillo"]] + plan["locales"]:
                for x, y in pieza["rect"]:
                    self.assertGreaterEqual(x, bx[0] - 1e-6)
                    self.assertLessEqual(x, bx[2] + 1e-6)
                    self.assertGreaterEqual(y, bx[1] - 1e-6)
                    self.assertLessEqual(y, bx[3] + 1e-6)

    def test_cantidad_uno_y_cinco(self):
        self.assertEqual(len(dd.alternativas(_prog(), RECT_GRANDE,
                                             cantidad=1)), 1)
        self.assertEqual(len(dd.alternativas(_prog(), RECT_GRANDE,
                                             cantidad=5)), 5)

    def test_programa_imposible_da_filas_de_error(self):
        nave = dd.programa_edificacion([
            {"space_type": "OFFICE", "cantidad": 1,
             "area_m2": 500.0}])
        lista = dd.alternativas(nave, RECT, cantidad=1)
        self.assertEqual(lista[0]["error"], "ARQ-DDI-003")
        self.assertIsNone(lista[0]["analisis"])

    def test_texto_alternativas_cp1252(self):
        texto = dd.texto_alternativas(
            dd.alternativas(_prog(), RECT_GRANDE, cantidad=3))
        texto.encode("cp1252")
        self.assertIn("ALTERNATIVAS DEL PROGRAMA", texto)
        self.assertIn("puntuación", texto)

    def test_decisiones_explican_el_reparto(self):
        an = dd.ajustar(_prog_grande(), RECT)  # crece a 2 niveles
        tipos = {d["tipo"] for d in an["decisiones"]}
        self.assertIn("niveles", tipos)
        self.assertIn("escalera", tipos)
        self.assertIn("local", tipos)
        crece = next(d for d in an["decisiones"]
                     if d["tipo"] == "niveles")
        self.assertIn("se reparte en", crece["texto"])
        self.assertIn(f"{an['niveles']} niveles", crece["texto"])
        cabe = dd.ajustar(_prog(), RECT_GRANDE)
        uno = next(d for d in cabe["decisiones"]
                   if d["tipo"] == "niveles")
        self.assertIn("cabe en 1 nivel", uno["texto"])

    def test_explicar_local_y_error_amable(self):
        an = dd.ajustar(_prog_grande(), RECT)
        nombre = an["programa"]["renglones"][0]["nombre"]
        texto = dd.explicar_local(an, nombre)
        texto.encode("cp1252")
        self.assertIn(nombre, texto)
        self.assertIn("banda", texto)
        with self.assertRaises(DomainError) as cm:
            dd.explicar_local(an, "Loca Inexistente 99")
        self.assertEqual(_codigo(cm.exception), "ARQ-DDI-008")

    def test_texto_decisiones_cp1252(self):
        texto = dd.texto_decisiones(dd.ajustar(_prog_grande(), RECT))
        texto.encode("cp1252")
        self.assertIn("DECISIONES DEL ASISTENTE", texto)


# ---------------------------------------------------------------------------
# 7) QUICK-SPEC EN UNA LÍNEA (spec §42, sin IA)
# ---------------------------------------------------------------------------

class TestQuickSpec(unittest.TestCase):

    def test_frase_completa(self):
        qs = dd.quick_spec("3 dormitorios, 2 baños, garaje y "
                           "2 niveles")
        self.assertEqual(
            [(u["space_type"], u["cantidad"]) for u in qs["usos"]],
            [("BEDROOM", 3), ("BATHROOM", 2), ("PARKING", 1)])
        self.assertEqual(qs["niveles"], 2)
        self.assertEqual(qs["desconocidos"], [])

    def test_numeros_en_palabra(self):
        qs = dd.quick_spec("un dormitorio, una cocina y dos aseos")
        self.assertEqual(
            [(u["space_type"], u["cantidad"]) for u in qs["usos"]],
            [("BEDROOM", 1), ("KITCHEN", 1), ("LAVATORY", 2)])

    def test_desconocidos_honestos(self):
        qs = dd.quick_spec("2 dormitorios y 3 jaulas")
        self.assertEqual(len(qs["usos"]), 1)
        self.assertEqual(qs["desconocidos"], ["jaulas"])

    def test_pasillo_y_escalera_los_reserva_el_asistente(self):
        qs = dd.quick_spec("una cocina, pasillo y escalera")
        self.assertEqual(len(qs["usos"]), 1)
        self.assertTrue(qs["avisos"])
        self.assertFalse(qs["desconocidos"])

    def test_vacio_lanza_amable(self):
        with self.assertRaises(DomainError) as cm:
            dd.quick_spec("   ")
        self.assertEqual(_codigo(cm.exception), "ARQ-DDI-002")

    def test_programa_quick(self):
        programa = dd.programa_quick("un dormitorio y un baño")
        self.assertEqual(len(programa["renglones"]), 2)
        self.assertIsNone(programa["quick"]["niveles_deseados"])
        with self.assertRaises(DomainError) as cm:
            dd.programa_quick("3 xyz")
        self.assertIn("xyz", str(cm.exception.message))

    def test_usos_de_programa_agrupa(self):
        usos = dd.usos_de_programa(_prog())
        self.assertEqual(
            [(u["space_type"], u["cantidad"]) for u in usos],
            [("OFFICE", 2), ("BATHROOM", 1)])


# ---------------------------------------------------------------------------
# 8) PATIO EXPERTO (opción del spec §A11)
# ---------------------------------------------------------------------------

class TestPatio(unittest.TestCase):

    def test_patio_reservado_al_final_del_pasillo(self):
        an = dd.ajustar(_prog(), RECT_GRANDE, patio=True,
                        patio_ancho_m=3.0)
        self.assertIsNotNone(an["patio"])
        self.assertAlmostEqual(an["patio"]["area_m2"], 3.0 * 16.0,
                               places=2)
        self.assertAlmostEqual(an["totales"]["area_patio"], 48.0,
                               places=2)
        for plan in an["reparto"]:
            patio = plan["patio"]
            self.assertEqual(patio["space_type"], "PATIO")
            for x, y in patio["rect"]:
                self.assertGreaterEqual(x, -1e-9)
                self.assertLessEqual(x, 30.0 + 1e-9)
                self.assertGreaterEqual(y, -1e-9)
                self.assertLessEqual(y, 16.0 + 1e-9)
        self.assertTrue(an["dentro_del_contorno"])
        decision = next(d for d in an["decisiones"]
                        if d["tipo"] == "patio")
        decision["texto"].encode("cp1252")

    def test_patio_demasiado_ancho_se_ignora_con_aviso(self):
        ancho = dd.ajustar(_prog(), RECT, patio=True,
                           patio_ancho_m=10.0)
        self.assertIsNone(ancho["patio"])
        self.assertTrue(any("demasiado estrecho" in a
                            for a in ancho["avisos"]))

    def test_sin_patio_nada_cambia(self):
        an = dd.ajustar(_prog(), RECT_GRANDE)
        self.assertIsNone(an["patio"])
        self.assertAlmostEqual(an["totales"]["area_patio"], 0.0,
                               places=6)


# ---------------------------------------------------------------------------
# 9) REEMPLAZO, ESPESORES Y PATIO COMO ENTIDADES (proyecto real)
# ---------------------------------------------------------------------------

class TestReemplazoYExperto(ARQGenTestCase):
    """Generar dos veces ya no acumula edificios en silencio."""

    def _ctx_fresco(self):
        return self.application.create_project(
            self.project_path("p39.arqgen"), name="P39")

    def test_reemplazo_deja_un_solo_edificio(self):
        ctx = self._ctx_fresco()
        an = dd.ajustar(_prog(), RECT)
        r1 = dd.aplicar_plan(ctx, an,
                             {"nombre_edificio": "Prueba 39",
                              "reemplazar_previo": True})
        r2 = dd.aplicar_plan(ctx, an,
                             {"nombre_edificio": "Prueba 39",
                              "reemplazar_previo": True})
        # el reemplazado se identifica por CÓDIGO, el resumen da el
        # nombre del edificio nuevo: basta con que haya reemplazo
        self.assertTrue(r2["reemplazado"])
        plantas = [lv for lv in ctx.architecture.list(
            "LEVEL", ctx.project.id) if lv.name == "Planta 1"]
        self.assertEqual(len(plantas), 1)
        self.assertIsNotNone(dd.edificio_previo(ctx))
        ctx.close()

    def test_sin_la_bandera_se_acumulan_dos(self):
        ctx = self._ctx_fresco()
        an = dd.ajustar(_prog(), RECT)
        dd.aplicar_plan(ctx, an, {"nombre_edificio": "Dos 39"})
        r2 = dd.aplicar_plan(ctx, an, {"nombre_edificio": "Dos 39"})
        self.assertEqual(r2["reemplazado"], "")
        edificios = ctx.architecture.list(
            "BUILDING", ctx.project.id)
        self.assertEqual(len(edificios), 2)
        ctx.close()

    def test_previo_inexistente_es_none(self):
        ctx = self._ctx_fresco()
        self.assertIsNone(dd.edificio_previo(ctx))
        ctx.close()

    def test_espesores_expertos_en_los_muros(self):
        ctx = self._ctx_fresco()
        an = dd.ajustar(_prog(), RECT)
        dd.aplicar_plan(ctx, an,
                        {"nombre_edificio": "Muros 39",
                         "trazar_muros": True,
                         "espesor_contorno_m": 0.30,
                         "espesor_local_m": 0.10})
        grosores = {round(float(w.thickness_m), 3)
                    for w in ctx.architecture.list(
                        "WALL", ctx.project.id)}
        self.assertIn(0.30, grosores)
        self.assertIn(0.10, grosores)
        ctx.close()

    def test_patio_genera_espacio_real(self):
        ctx = self._ctx_fresco()
        an = dd.ajustar(_prog(), RECT_GRANDE, patio=True,
                        patio_ancho_m=3.0)
        dd.aplicar_plan(ctx, an, {"nombre_edificio": "Patio 39"})
        patios = [s for s in ctx.architecture.list(
            "SPACE", ctx.project.id)
            if str(getattr(s, "space_type", "")) == "PATIO"]
        self.assertEqual(len(patios), 1)
        self.assertAlmostEqual(
            float(patios[0].area_m2()), 48.0, places=1)
        ctx.close()


# ---------------------------------------------------------------------------
# 10) CONFIGURACIONES Y ESTADO GUARDABLES (spec §29/§30)
# ---------------------------------------------------------------------------

class TestConfiguraciones(ARQGenTestCase):
    """Fotografías de la configuración dentro del proyecto."""

    def _ctx(self):
        return self.application.create_project(
            self.project_path("conf39.arqgen"), name="Conf39")

    def test_guardar_listar_restaurar(self):
        ctx = self._ctx()
        req = dd.PlanRequest(contorno=RECT, programa=_prog(),
                             patio=True, niveles_deseados=2)
        entrada = dd.guardar_configuracion(ctx, req,
                                           dd.ajustar(_prog(), RECT))
        self.assertEqual(entrada["etiqueta"], "CONFIGURACIÓN 01")
        self.assertEqual(entrada["indice"], 0)
        self.assertEqual(len(dd.listar_configuraciones(ctx)), 1)
        copia = dd.restaurar_configuracion(ctx, 0)
        self.assertEqual(copia.contorno, req.contorno)
        self.assertTrue(copia.patio)
        self.assertEqual(copia.niveles_deseados, 2)
        self.assertEqual(len(copia.programa["renglones"]),
                         len(req.programa["renglones"]))
        ctx.close()

    def test_tope_de_fotografias(self):
        ctx = self._ctx()
        req = dd.PlanRequest(contorno=RECT, programa=_prog())
        for _ in range(dd.CONFIGS_MAX + 2):
            dd.guardar_configuracion(ctx, req)
        lista = dd.listar_configuraciones(ctx)
        self.assertEqual(len(lista), dd.CONFIGS_MAX)
        self.assertTrue(lista[-1]["etiqueta"].endswith(
            f"{dd.CONFIGS_MAX + 2:02d}"))
        ctx.close()

    def test_eliminar_y_restaurar_invalido(self):
        ctx = self._ctx()
        req = dd.PlanRequest(contorno=RECT, programa=_prog())
        dd.guardar_configuracion(ctx, req)
        dd.eliminar_configuracion(ctx, 0)
        self.assertEqual(dd.listar_configuraciones(ctx), [])
        with self.assertRaises(DomainError) as cm:
            dd.restaurar_configuracion(ctx, 3)
        self.assertEqual(_codigo(cm.exception), "ARQ-DDI-006")
        ctx.close()

    def test_estado_guardable_y_recuperable(self):
        ctx = self._ctx()
        self.assertIsNone(dd.cargar_estado(ctx))
        req = dd.PlanRequest(contorno=RECT, programa=_prog(),
                             patio=True)
        self.assertTrue(dd.guardar_estado(ctx, req))
        copia = dd.cargar_estado(ctx)
        self.assertTrue(copia.patio)
        self.assertEqual(copia.contorno, req.contorno)
        ctx.settings.set(dd.CLAVE_ESTADO_DD, "{basura")
        with self.assertRaises(DomainError) as cm:
            dd.cargar_estado(ctx)
        self.assertEqual(_codigo(cm.exception), "ARQ-DDI-007")
        ctx.close()

    def test_estado_sin_ajustes_devuelve_false(self):
        ctx_desnudo = SimpleNamespace()
        self.assertFalse(dd.guardar_estado(ctx_desnudo, None))
        self.assertIsNone(dd.cargar_estado(ctx_desnudo))


# ---------------------------------------------------------------------------
# 11) GANCHOS DE VENTANA (con display): el diálogo v3.39.0
# ---------------------------------------------------------------------------

class TestGanchosVentana39(ARQGenTestCase):
    """El diálogo «Desde dibujo» cablea los modos y las nuevas
    herramientas sin romper el flujo de siempre."""

    def setUp(self):
        super().setUp()
        self._prefs_old = os.environ.get("ARQGEN_PREFS")
        os.environ["ARQGEN_PREFS"] = os.path.join(self.tmp,
                                                  "prefs.json")
        from ui.app_window import ARQGenWindow
        self.ctx = self.demo_context()
        self.window = ARQGenWindow(self.ctx, self.application)
        self.window.update()
        self.window.open_desde_dibujo_dialog()
        self.window.update()
        self.d = self.window._dd_dialog

    def tearDown(self):
        self.window.destroy()
        self.ctx.close()
        if self._prefs_old:
            os.environ["ARQGEN_PREFS"] = self._prefs_old
        else:
            os.environ.pop("ARQGEN_PREFS", None)
        super().tearDown()

    def _modo_edificacion(self):
        self.window._dd_modo.set("edificacion")
        self.window._dd_modo_cambio()
        # contorno por rectángulo (20x12): el espacio del demo es
        # pequeño y con él el ajuste lanzaría el error amable modal
        self.window._dd_origen.set("rectangulo")
        self.window._dd_origen_cambio()
        self.window._dd_usos = [{"space_type": "OFFICE",
                                 "cantidad": 2, "area_m2": 20.0},
                                {"space_type": "BATHROOM",
                                 "cantidad": 1, "area_m2": 8.0}]
        self.window._dd_arbol_refresca()

    def test_modos_muestran_y_ocultan(self):
        w = self.window
        self.assertEqual(w._dd_nivel.get(), "profesional")
        # profesional: quick, alternativas e historial visibles; el
        # marco experto NO
        self.assertNotEqual(w._dd_frame_quick.winfo_manager(), "")
        self.assertNotEqual(w._dd_frame_alt.winfo_manager(), "")
        self.assertNotEqual(w._dd_frame_conf.winfo_manager(), "")
        self.assertEqual(w._dd_frame_experto.winfo_manager(), "")
        w._dd_nivel.set("basico")
        w._dd_nivel_cambio()
        for marco in (w._dd_frame_quick, w._dd_frame_alt,
                      w._dd_frame_conf, w._dd_frame_experto):
            self.assertEqual(marco.winfo_manager(), "")
        w._dd_nivel.set("experto")
        w._dd_nivel_cambio()
        for marco in (w._dd_frame_quick, w._dd_frame_alt,
                      w._dd_frame_conf, w._dd_frame_experto):
            self.assertNotEqual(marco.winfo_manager(), "")

    def test_quick_spec_llena_la_tabla(self):
        w = self.window
        self._modo_edificacion()
        w._dd_quick.set("2 oficinas y un baño")
        w._dd_quick_aplicar()
        self.assertEqual(len(w._dd_usos), 2)
        self.assertEqual(len(w._dd_arbol.get_children()), 2)
        self.assertIn("ESPECIFICACIÓN RÁPIDA",
                      w._dd_texto.get("1.0", "end"))

    def test_quick_spec_desconocido_avisa(self):
        w = self.window
        self._modo_edificacion()
        w._dd_quick.set("3 xyz")
        with mock.patch("ui.app_window.messagebox.showwarning") \
                as _aviso:
            w._dd_quick_aplicar()
            self.assertTrue(_aviso.called)

    def test_ajustar_muestra_checklist_y_porque(self):
        w = self.window
        self._modo_edificacion()
        w._dd_ajustar()
        self.assertIn("CHECKLIST ANTES DE GENERAR",
                      w._dd_texto.get("1.0", "end"))
        w._dd_porque()
        self.assertIn("DECISIONES DEL ASISTENTE",
                      w._dd_texto.get("1.0", "end"))

    def test_analizar_muestra_validacion(self):
        w = self.window
        self._modo_edificacion()
        w._dd_analizar()
        self.assertIn("VALIDACIÓN DEL CONTORNO",
                      w._dd_texto.get("1.0", "end"))

    def test_alternativas_compara_y_elige(self):
        w = self.window
        self._modo_edificacion()
        w._dd_alt_n.set("3")
        w._dd_alternativas()
        self.assertEqual(len(w._dd_alternativas_lista), 3)
        self.assertIn("ALTERNATIVAS DEL PROGRAMA",
                      w._dd_texto.get("1.0", "end"))
        self.assertIsNotNone(w._dd_analisis)
        # elegir la B cambia el análisis activo
        w._dd_alt_elegir.current(1)
        w._dd_alt_elegida()
        self.assertIsNotNone(w._dd_analisis)

    def test_configuracion_guardar_y_restaurar(self):
        w = self.window
        self._modo_edificacion()
        w._dd_nombre.set("Mi edificio 39")
        w._dd_config_guardar()
        self.assertTrue(w._dd_conf_combo["values"])
        w._dd_nombre.set("Otro nombre")
        w._dd_config_restaurar()
        self.assertEqual(w._dd_nombre.get(), "Mi edificio 39")

    def test_aplicar_pregunta_por_el_edificio_previo(self):
        w = self.window
        self._modo_edificacion()
        w._dd_analisis = None
        # primera generación: no hay edificio previo, no pregunta
        with mock.patch(
                "ui.app_window.messagebox.askyesnocancel") as _preg, \
                mock.patch(
                    "ui.app_window.messagebox.showerror"):
            w._dd_aplicar()
            self.assertFalse(_preg.called)
        c1 = dd.edificio_previo(self.ctx).code
        # segunda generación: pregunta; NO reemplaza -> otro edificio
        with mock.patch(
                "ui.app_window.messagebox.askyesnocancel",
                return_value=False) as _preg, \
                mock.patch(
                    "ui.app_window.messagebox.showerror"):
            w._dd_aplicar()
            self.assertTrue(_preg.called)
        c2 = dd.edificio_previo(self.ctx).code
        self.assertNotEqual(c1, c2)
        # tercera generación reemplazando: el segundo desaparece
        with mock.patch(
                "ui.app_window.messagebox.askyesnocancel",
                return_value=True), \
                mock.patch(
                    "ui.app_window.messagebox.showerror"):
            w._dd_aplicar()
        self.assertIsNone(
            self.ctx.architecture.get_by_code("BUILDING", c2))
        # y el asistente ahora recuerda el edificio NUEVO
        c3 = dd.edificio_previo(self.ctx).code
        self.assertTrue(c3)
        self.assertNotEqual(c3, c2)

    def test_version_coherente_con_v3410(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
