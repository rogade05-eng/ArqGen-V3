"""SERVICIOS MEDICOS v3.35.0 (catálogo v2.0 + documentos del servicio).

Perfeccionamiento del asistente con el documento «servicios
medicos.txt»: cinco servicios nuevos (morgue, tomografía computarizada,
UCI, cuidados intermedios, urgencias), anatomía patológica enriquecida
a 16 locales, grupos funcionales con subtotales (sección 20),
criticidad por niveles (sección 25), puertas y circulación del
catálogo, validación ampliada (prohibidas, regla 05; separación
limpio/sucio, regla 06) y los documentos: ficha de local (sección 30),
matriz de instalaciones (sección 22), relaciones entre servicios
(sección 17), flujos hospitalarios (sección 18) y las 20 reglas de
generación (sección 24).
"""

from __future__ import annotations

import os
import unittest

from core.errors import DomainError
from domain import servicios_engine as eng
from domain.servicios_specs import (ETIQUETAS_INSTALACIONES,
                                    ServicioLocal, cargar_servicios,
                                    flujos_hospitalarios, resumen_catalogo,
                                    servicio, version_catalogo)
from tests.base import ARQGenTestCase


# ---------------------------------------------------------------------------
# catálogo v2.0
# ---------------------------------------------------------------------------

class TestCatalogoV2(unittest.TestCase):
    """El catálogo crece con los servicios médicos y sus metadatos."""

    def setUp(self) -> None:
        self.items = cargar_servicios()
        self.codigos = {s.codigo for s in self.items}

    def test_once_servicios_medicos_presentes(self):
        self.assertGreaterEqual(len(self.items), 11)
        for esperado in ("MORGUE", "TOMOGRAFIA_COMPUTARIZADA", "UCI",
                         "CUIDADOS_INTERMEDIOS", "URGENCIAS",
                         "ANATOMIA_PATOLOGICA"):
            self.assertIn(esperado, self.codigos)

    def test_version_y_reglas_globales(self):
        self.assertEqual(version_catalogo(), "3.0")
        reglas = flujos_hospitalarios()  # saneamiento de carga
        self.assertEqual(len(eng.specs.reglas_generacion()), 20)
        self.assertIn("R01", eng.specs.reglas_generacion()[0])
        self.assertIn("R20", eng.specs.reglas_generacion()[-1])
        self.assertTrue(reglas)

    def test_flujos_hospitalarios_globales(self):
        flujos = flujos_hospitalarios()
        self.assertEqual(len(flujos), 4)
        for flujo in flujos:
            self.assertIn("->", flujo)
            self.assertNotIn("\u2192", flujo)
        self.assertTrue(any(f.startswith("cadaveres:") for f in flujos))
        self.assertTrue(any(f.startswith("urgencias:") for f in flujos))

    def test_anatomia_patologica_enriquecida(self):
        ap = servicio("ANATOMIA_PATOLOGICA")
        self.assertEqual(len(ap.locales), 17)   # + filtro v3.42.0
        nombres = {l.nombre for l in ap.locales}
        for esperado in ("Secretaria", "Sala de reuniones", "Microscopia",
                         "Almacen de reactivos", "Cuarto de limpieza",
                         "Deposito de residuos"):
            self.assertIn(esperado, nombres)
        macro = ap.local("SALA_CORTE")
        self.assertEqual(macro.grupo, "Procesamiento")
        self.assertEqual(macro.criticidad, 3)
        self.assertAlmostEqual(macro.puerta_ancho, 1.00)
        self.assertAlmostEqual(macro.circulacion_min, 1.50)
        self.assertIn("hvac", macro.instalaciones)
        self.assertEqual(macro.acabados.get("piso"),
                         "continuo, lavable, antideslizante")
        self.assertEqual(macro.relaciones.get("obligatorias"),
                         ["Recepcion de muestras / laboratorio"])
        self.assertEqual(macro.relaciones.get("prohibidas"),
                         ["Circulacion publica no controlada"])
        self.assertTrue(macro.observaciones)

    def test_matriz_de_instalaciones_por_servicio(self):
        tac = servicio("TOMOGRAFIA_COMPUTARIZADA")
        self.assertEqual(tac.matriz_instalaciones.get("Radioproteccion"),
                         "MUY ALTA")
        self.assertEqual(tac.matriz_instalaciones.get("Electricidad"),
                         "MUY ALTA")
        morgue = servicio("MORGUE")
        self.assertEqual(morgue.matriz_instalaciones.get("Drenaje"),
                         "MUY ALTA")
        # servicios del catálogo v1 sin matriz siguen cargando sanos
        self.assertEqual(servicio("FARMACIA").matriz_instalaciones, {})

    def test_relaciones_entre_servicios(self):
        uci = servicio("UCI").relaciones_servicios
        pares = {r["servicio"]: r["nivel"] for r in uci}
        self.assertEqual(pares.get("URGENCIAS"), "MUY ALTA")
        morgue = {r["servicio"]: r["nivel"] for r in
                  servicio("MORGUE").relaciones_servicios}
        self.assertEqual(morgue.get("ANATOMIA_PATOLOGICA"), "MUY ALTA")
        # todas las relaciones apuntan a servicios del catálogo
        for item in self.items:
            for r in item.relaciones_servicios:
                self.assertIn(r["servicio"], self.codigos,
                              f"{item.codigo} -> {r['servicio']}")

    def test_resumen_ampliado(self):
        resumen = resumen_catalogo()
        self.assertGreaterEqual(resumen["servicios"], 11)
        self.assertGreaterEqual(resumen["locales"], 140)
        self.assertGreaterEqual(resumen["criticos"], 20)
        self.assertGreaterEqual(resumen["grupos"], 15)
        self.assertEqual(resumen["reglas"], 20)
        self.assertEqual(resumen["version"], "3.0")

    def test_vocabulario_de_instalaciones(self):
        for item in self.items:
            for l in item.locales:
                for inst in l.instalaciones:
                    self.assertIn(inst, ETIQUETAS_INSTALACIONES,
                                  f"{item.codigo}.{l.codigo}: {inst}")
                    etiqueta = ETIQUETAS_INSTALACIONES[inst]
                    etiqueta.encode("cp1252")

    def test_criticidad_por_niveles_del_documento(self):
        self.assertEqual(
            servicio("UCI").local("CUBICULOS").criticidad, 1)
        self.assertEqual(
            servicio("CUIDADOS_INTERMEDIOS").local(
                "HABITACIONES").criticidad, 2)
        self.assertEqual(
            servicio("TOMOGRAFIA_COMPUTARIZADA").local(
                "SALA_CT").criticidad, 2)
        self.assertEqual(
            servicio("MORGUE").local("AUTOPSIAS").criticidad, 3)
        self.assertEqual(
            servicio("URGENCIAS").local("REANIMACION").criticidad, 1)

    def test_puertas_de_camilla_y_carros(self):
        self.assertAlmostEqual(
            servicio("UCI").local("CUBICULOS").puerta_ancho, 1.20)
        self.assertAlmostEqual(
            servicio("URGENCIAS").local("BAHIA_AMBULANCIAS")
            .puerta_ancho, 1.50)
        self.assertAlmostEqual(
            servicio("MORGUE").local("CONSERVACION").puerta_ancho, 1.20)

    def test_from_dict_tolerante_con_lo_nuevo(self):
        # sin los campos v2.0: defectos honestos
        viejo = ServicioLocal.from_dict({"codigo": "X", "nombre": "X"})
        self.assertEqual(viejo.grupo, "")
        self.assertEqual(viejo.criticidad, 0)
        self.assertEqual(viejo.puerta_ancho, 0.0)
        self.assertEqual(viejo.instalaciones, [])
        self.assertEqual(viejo.acabados, {})
        self.assertEqual(viejo.relaciones, {})
        # con claves desconocidas: se ignoran sin explotar
        raro = ServicioLocal.from_dict({"codigo": "Y", "nombre": "Y",
                                        "bogus": 3, "criticidad": "2"})
        self.assertEqual(raro.criticidad, 2)
        self.assertFalse(hasattr(raro, "bogus"))


# ---------------------------------------------------------------------------
# programas de los servicios médicos
# ---------------------------------------------------------------------------

class TestProgramaMedicos(unittest.TestCase):
    """programa_servicio sobre los cinco servicios nuevos."""

    def test_morgue_con_defectos(self):
        p = eng.programa_servicio("MORGUE")
        self.assertEqual(p["totales"]["locales"], 18)
        self.assertAlmostEqual(p["totales"]["area_m2"], 203.4, places=1)
        nombres = [r["nombre"] for r in p["renglones"]]
        for esperado in ("Conservacion refrigerada", "Sala de autopsias",
                         "Espera de familiares", "Area de entrega"):
            self.assertIn(esperado, nombres)

    def test_morgue_conservacion_por_capacidad(self):
        base = eng.programa_servicio("MORGUE", {"cadaveres": 6})
        area = next(r["area_m2"] for r in base["renglones"]
                    if r["codigo"] == "CONSERVACION")
        self.assertAlmostEqual(area, 26.4, places=6)   # 12 + 6 x 2.4
        grande = eng.programa_servicio("MORGUE", {"cadaveres": 20})
        area = next(r["area_m2"] for r in grande["renglones"]
                    if r["codigo"] == "CONSERVACION")
        self.assertAlmostEqual(area, 60.0, places=6)

    def test_morgue_sin_autopsias_propia(self):
        p = eng.programa_servicio("MORGUE", {"con_autopsias": False})
        self.assertEqual(p["totales"]["locales"], 17)
        self.assertFalse(any(r["codigo"] == "AUTOPSIAS"
                             for r in p["renglones"]))

    def test_tomografia_con_defectos(self):
        p = eng.programa_servicio("TOMOGRAFIA_COMPUTARIZADA")
        self.assertEqual(p["totales"]["locales"], 14)
        sala = next(r for r in p["renglones"] if r["codigo"] == "SALA_CT")
        self.assertAlmostEqual(sala["area_m2"], 28.0)
        control = next(r for r in p["renglones"]
                       if r["codigo"] == "CONTROL")
        self.assertAlmostEqual(control["area_m2"], 12.0)

    def test_tomografia_repite_salas_ct(self):
        p = eng.programa_servicio("TOMOGRAFIA_COMPUTARIZADA",
                                  {"equipos_ct": 3})
        salas = [r["nombre"] for r in p["renglones"]
                 if r["codigo"] == "SALA_CT"]
        self.assertEqual(salas, ["Sala de tomografo",
                                 "Sala de tomografo 2",
                                 "Sala de tomografo 3"])

    def test_tomografia_espera_por_persona(self):
        p = eng.programa_servicio("TOMOGRAFIA_COMPUTARIZADA",
                                  {"espera_personas": 20})
        area = next(r["area_m2"] for r in p["renglones"]
                    if r["codigo"] == "ESPERA")
        self.assertAlmostEqual(area, 37.0, places=6)   # 10 + 20 x 1.35

    def test_tomografia_sin_contraste(self):
        p = eng.programa_servicio("TOMOGRAFIA_COMPUTARIZADA",
                                  {"con_contraste": False})
        self.assertEqual(p["totales"]["locales"], 12)
        codigos = {r["codigo"] for r in p["renglones"]}
        self.assertNotIn("CONTRASTE", codigos)
        self.assertNotIn("RECUPERACION", codigos)

    def test_uci_con_defectos(self):
        p = eng.programa_servicio("UCI")
        # 8 cubiculos + 1 aislamiento + 16 locales de apoyo/personal
        self.assertEqual(p["totales"]["locales"], 26)
        self.assertAlmostEqual(p["totales"]["area_m2"], 343.0, places=1)
        cubiculos = [r for r in p["renglones"]
                     if r["codigo"] == "CUBICULOS"]
        self.assertEqual(len(cubiculos), 8)
        self.assertTrue(all(abs(r["area_m2"] - 18.0) < 1e-9
                            for r in cubiculos))

    def test_uci_sin_aislamiento(self):
        p = eng.programa_servicio("UCI", {"con_aislamiento": False})
        self.assertEqual(p["totales"]["locales"], 25)
        self.assertFalse(any(r["codigo"] == "AISLAMIENTO"
                             for r in p["renglones"]))

    def test_uci_cabecera_completa_del_puesto(self):
        uci = servicio("UCI")
        cubiculo = uci.local("CUBICULOS")
        for inst in ("o2", "vacio", "aire_medicinal", "elec_emergencia",
                     "datos", "llamada"):
            self.assertIn(inst, cubiculo.instalaciones)
        self.assertTrue(any("cabecera" in r.lower()
                            for r in cubiculo.req))

    def test_cuidados_intermedios_con_defectos(self):
        p = eng.programa_servicio("CUIDADOS_INTERMEDIOS")
        self.assertEqual(p["totales"]["locales"], 25)
        habitaciones = [r for r in p["renglones"]
                        if r["codigo"] == "HABITACIONES"]
        self.assertEqual(len(habitaciones), 10)
        self.assertTrue(all(abs(r["area_m2"] - 16.0) < 1e-9
                            for r in habitaciones))

    def test_urgencias_con_defectos(self):
        p = eng.programa_servicio("URGENCIAS")
        self.assertEqual(p["totales"]["locales"], 30)
        self.assertAlmostEqual(p["totales"]["area_m2"], 470.0, places=1)
        reanimacion = next(r for r in p["renglones"]
                           if r["codigo"] == "REANIMACION")
        self.assertAlmostEqual(reanimacion["area_m2"], 48.0)  # 2 x 24
        observacion = next(r for r in p["renglones"]
                           if r["codigo"] == "OBSERVACION")
        self.assertAlmostEqual(observacion["area_m2"], 80.0)  # 8 x 10

    def test_urgencias_escalas_por_puestos(self):
        p = eng.programa_servicio(
            "URGENCIAS", {"puestos_reanimacion": 4,
                          "puestos_observacion": 20, "consultorios": 2})
        reanimacion = next(r for r in p["renglones"]
                           if r["codigo"] == "REANIMACION")
        self.assertAlmostEqual(reanimacion["area_m2"], 96.0)
        observacion = next(r for r in p["renglones"]
                           if r["codigo"] == "OBSERVACION")
        self.assertAlmostEqual(observacion["area_m2"], 200.0)
        consultorios = [r for r in p["renglones"]
                        if r["codigo"] == "CONSULTORIOS"]
        self.assertEqual(len(consultorios), 2)

    def test_urgencias_flujo_general_en_el_catalogo(self):
        urg = servicio("URGENCIAS")
        self.assertTrue(any("acceso -> triage" in f
                            for f in urg.flujos))

    def test_grupos_con_subtotales_coherentes(self):
        p = eng.programa_servicio("URGENCIAS")
        grupos = p["totales"]["grupos"]
        self.assertEqual(set(grupos),
                         {"Accesos", "Asistencial", "Apoyo", "Personal"})
        self.assertEqual(sum(g["locales"] for g in grupos.values()),
                         p["totales"]["locales"])
        self.assertAlmostEqual(
            sum(g["area_m2"] for g in grupos.values()),
            p["totales"]["area_m2"], places=1)

    def test_total_coherente_en_los_cinco(self):
        for codigo in ("MORGUE", "TOMOGRAFIA_COMPUTARIZADA", "UCI",
                       "CUIDADOS_INTERMEDIOS", "URGENCIAS"):
            p = eng.programa_servicio(codigo)
            suma = sum(r["area_m2"] for r in p["renglones"])
            self.assertAlmostEqual(suma, p["totales"]["area_m2"],
                                   places=1, msg=codigo)

    def test_dimensiones_sugeridas_cierran_el_area(self):
        for codigo in ("MORGUE", "TOMOGRAFIA_COMPUTARIZADA", "UCI",
                       "URGENCIAS"):
            p = eng.programa_servicio(codigo)
            for r in p["renglones"]:
                producto = r["ancho_m"] * r["fondo_m"]
                # ventana completa: chicos por FONDO_MIN, grandes por
                # ANCHO_MAX (y ahí el empaquetado recomputa el ancho)
                if r["area_m2"] < 8.0:
                    self.assertGreaterEqual(producto, r["area_m2"] - 1e-6,
                                            f"{codigo}.{r['nombre']}")
                elif r["area_m2"] <= 72.0:
                    self.assertGreaterEqual(producto,
                                            r["area_m2"] * 0.98,
                                            f"{codigo}.{r['nombre']}")
                    self.assertLessEqual(producto,
                                         r["area_m2"] * 1.15,
                                         f"{codigo}.{r['nombre']}")
                else:
                    # el empaquetado real garantiza el área completa
                    ancho_real = max(r["ancho_m"],
                                     r["area_m2"] / eng.FONDO_MAX)
                    self.assertGreaterEqual(ancho_real * r["fondo_m"],
                                            r["area_m2"] - 1e-6,
                                            f"{codigo}.{r['nombre']}")


# ---------------------------------------------------------------------------
# validación ampliada
# ---------------------------------------------------------------------------

class TestValidacionMedicos(unittest.TestCase):
    """Los checks nuevos del catálogo v2.0 sobre programas reales."""

    def test_validacion_ok_en_los_medicos_con_defectos(self):
        for codigo in ("ANATOMIA_PATOLOGICA", "MORGUE",
                       "TOMOGRAFIA_COMPUTARIZADA", "UCI",
                       "CUIDADOS_INTERMEDIOS", "URGENCIAS"):
            p = eng.programa_servicio(codigo)
            estados = {c["codigo"]: c["estado"]
                       for c in p["validacion"]}
            self.assertEqual(estados.get("AREAS"), "ok", codigo)
            self.assertEqual(estados.get("CRITICOS"), "ok", codigo)

    def test_puertas_del_catalogo_y_del_dna(self):
        p = eng.programa_servicio("UCI")
        puertas = next(c for c in p["validacion"]
                       if c["codigo"] == "PUERTAS")
        self.assertEqual(puertas["estado"], "info")
        self.assertIn("1.20 m (catalogo)", puertas["detalle"])

    def test_circulacion_cubierta_por_el_pasillo(self):
        p = eng.programa_servicio("URGENCIAS")
        circula = next(c for c in p["validacion"]
                       if c["codigo"] == "CIRCULACION")
        self.assertEqual(circula["estado"], "ok")
        self.assertIn("2.40", circula["detalle"])
        self.assertIn("1.80", circula["detalle"])

    def test_criticidad_por_niveles_en_la_validacion(self):
        p = eng.programa_servicio("UCI")
        criticidad = next(c for c in p["validacion"]
                          if c["codigo"] == "CRITICIDAD")
        self.assertEqual(criticidad["estado"], "info")
        self.assertIn("nivel 1", criticidad["detalle"])

    def test_relaciones_prohibidas_se_echoan(self):
        p = eng.programa_servicio("ANATOMIA_PATOLOGICA")
        prohibidas = next(c for c in p["validacion"]
                          if c["codigo"] == "PROHIBIDAS")
        self.assertEqual(prohibidas["estado"], "info")
        self.assertIn("Sala de corte (macroscopia)", prohibidas["detalle"])
        self.assertIn("Circulacion publica no controlada",
                      prohibidas["detalle"])

    def test_separacion_limpio_sucio(self):
        p = eng.programa_servicio("UCI")
        separacion = next(c for c in p["validacion"]
                          if c["codigo"] == "SEPARACION")
        self.assertEqual(separacion["estado"], "info")
        self.assertIn("regla 06", separacion["nombre"])
        # farmacia no mezcla circuitos: sin check de separación
        p2 = eng.programa_servicio("FARMACIA")
        self.assertFalse(any(c["codigo"] == "SEPARACION"
                             for c in p2["validacion"]))

    def test_ficha_desconocida_error_amable(self):
        with self.assertRaises(DomainError) as ctxm:
            eng.texto_ficha_local("UCI", "NO_EXISTE")
        self.assertEqual(ctxm.exception.code, "ARQ-SRV-007")


# ---------------------------------------------------------------------------
# documentos del servicio
# ---------------------------------------------------------------------------

class TestDocumentos(unittest.TestCase):
    """Ficha de local, matriz, relaciones, flujos y reglas, en cp1252."""

    def test_ficha_seccion_30_de_la_macroscopia(self):
        texto = eng.texto_ficha_local("ANATOMIA_PATOLOGICA", "SALA_CORTE")
        texto.encode("cp1252")
        self.assertIn("FICHA DE LOCAL", texto)
        self.assertIn("Sala de corte (macroscopia)", texto)
        self.assertIn("SUPERFICIE_MIN: 24.00 m2", texto)
        self.assertIn("SUPERFICIE_MAX: 48.00 m2", texto)
        self.assertIn("PUERTA: 1.00 m", texto)
        self.assertIn("CIRCULACION: 1.50 m", texto)
        self.assertIn("CRITICIDAD: nivel 3", texto)
        self.assertIn("Agua fria: SI", texto)
        self.assertIn("PISO: continuo, lavable, antideslizante", texto)
        self.assertIn("banco de macroscopia", texto)
        self.assertIn("OBLIGATORIA: Recepcion de muestras / laboratorio",
                      texto)
        self.assertIn("PROHIBIDA: Circulacion publica no controlada",
                      texto)
        self.assertIn("OBSERVACION:", texto)
        self.assertNotIn("\u2192", texto)

    def test_ficha_del_cubiculo_uci(self):
        texto = eng.texto_ficha_local("UCI", "CUBICULOS")
        texto.encode("cp1252")
        self.assertIn("CRITICIDAD: nivel 1", texto)
        self.assertIn("Oxigeno: SI", texto)
        self.assertIn("Llamada de enfermeria: SI", texto)
        self.assertIn("cabecera", texto)

    def test_ficha_con_tabla_seleccione(self):
        # el flujo de la GUI: sin selección no explota, da error amable
        with self.assertRaises(DomainError):
            eng.texto_ficha_local("UCI", "")

    def test_matriz_de_instalaciones_cp1252(self):
        texto = eng.texto_matriz_instalaciones(
            "TOMOGRAFIA_COMPUTARIZADA")
        texto.encode("cp1252")
        self.assertIn("MATRIZ DE INSTALACIONES", texto)
        self.assertIn("Radioproteccion", texto)
        self.assertIn("MUY ALTA", texto)
        self.assertIn("orientativos", texto)

    def test_matriz_sin_matriz_declara_la_situacion(self):
        texto = eng.texto_matriz_instalaciones("FARMACIA")
        texto.encode("cp1252")
        self.assertIn("no declara matriz", texto)

    def test_relaciones_entre_servicios_cp1252(self):
        texto = eng.texto_relaciones_servicios("UCI")
        texto.encode("cp1252")
        self.assertIn("RELACIONES ENTRE SERVICIOS", texto)
        self.assertIn("URGENCIAS: MUY ALTA", texto)
        self.assertIn("proximidad", texto)

    def test_relaciones_vacias_avisan(self):
        texto = eng.texto_relaciones_servicios("LABORATORIO_CLINICO")
        texto.encode("cp1252")
        self.assertIn("no declara relaciones", texto)

    def test_flujos_cp1252_con_globales(self):
        texto = eng.texto_flujos("URGENCIAS")
        texto.encode("cp1252")
        self.assertIn("FLUJOS HOSPITALARIOS", texto)
        self.assertIn("acceso -> triage", texto)
        self.assertIn("Flujos hospitalarios canonicos", texto)
        self.assertIn("cadaveres:", texto)
        self.assertNotIn("\u2192", texto)

    def test_reglas_generacion_cp1252(self):
        texto = eng.texto_reglas_generacion()
        texto.encode("cp1252")
        self.assertIn("REGLAS DE GENERACION AUTOMATICA", texto)
        self.assertIn("R01", texto)
        self.assertIn("R20", texto)
        self.assertIn("Separar limpio y sucio", texto)
        self.assertNotIn("\u2192", texto)


# ---------------------------------------------------------------------------
# ganchos de ventana
# ---------------------------------------------------------------------------

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


@unittest.skipUnless(DISPLAY, "sin display: pruebas Tk omitidas")
class TestGanchosVentana(ARQGenTestCase):
    """El asistente en la ventana: tabla con grupos y selector de
    documento."""

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

    def _abrir(self):
        self.window.open_servicios_dialog()
        self.window.update()
        return self.window._servicios_dialog

    def test_dialogo_con_columna_grupo_y_selector(self):
        self._abrir()
        arbol = self.window._servicios_arbol
        self.assertIn("grupo", arbol["columns"])
        self.assertTrue(hasattr(self.window, "_servicios_doc"))
        self.assertEqual(self.window._servicios_doc.get(),
                         "Programa y validación")

    def test_selector_de_documento_cambia_el_texto(self):
        self._abrir()
        texto_programa = self.window._servicios_texto.get("1.0", "end")
        self.window._servicios_doc.set("Reglas de generación")
        self.window._servicios_muestra_doc()
        self.window.update()
        texto_reglas = self.window._servicios_texto.get("1.0", "end")
        self.assertIn("REGLAS DE GENERACION AUTOMATICA", texto_reglas)
        self.assertNotEqual(texto_programa, texto_reglas)
        self.window._servicios_doc.set("Matriz de instalaciones")
        self.window._servicios_muestra_doc()
        self.assertIn("MATRIZ DE INSTALACIONES",
                      self.window._servicios_texto.get("1.0", "end"))

    def test_ficha_del_local_seleccionado(self):
        self._abrir()
        arbol = self.window._servicios_arbol
        primera = arbol.get_children()[0]
        arbol.selection_set(primera)
        self.window._servicios_doc.set(
            "Ficha del local (seleccione en la tabla)")
        self.window._servicios_muestra_doc()
        texto = self.window._servicios_texto.get("1.0", "end")
        self.assertIn("FICHA DE LOCAL", texto)

    def test_ficha_sin_seleccion_invita_a_elegir(self):
        self._abrir()
        self.window._servicios_doc.set(
            "Ficha del local (seleccione en la tabla)")
        self.window._servicios_muestra_doc()
        texto = self.window._servicios_texto.get("1.0", "end")
        self.assertIn("Seleccione una fila", texto)

    def test_total_con_grupos_en_la_linea_resumen(self):
        self._abrir()
        self.window._servicios_codigo.set(
            "URGENCIAS - Urgencias / Emergencias")
        self.window._servicios_carga()
        self.window.update()
        total = self.window._servicios_total.get()
        self.assertIn("30 local(es)", total)
        self.assertIn("Accesos", total)
        self.assertIn("Personal", total)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
