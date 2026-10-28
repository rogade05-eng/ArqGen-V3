"""CATALOGO UNIVERSAL DE SERVICIOS v3.0 (v3.36.0).

El catálogo crece de 11 a 34 servicios y de 140 a ~400 locales con el
campo SECTOR (salud, educación, administración, comercio y hostelería,
deportivo, cultural, residencial asistido y logística): 12 servicios
de salud nuevos (consulta externa, bloque quirúrgico, hospitalización,
maternidad, cardiología/hemodinamia, endoscopia, medicina nuclear,
microbiología, banco de sangre, rehabilitación, salud mental,
odontología) y 11 de otros usos (círculo infantil, primaria,
secundaria, oficinas, restaurante, supermercado, hotel, centro
deportivo, centro cultural, residencia de adultos, almacén logístico).
Además: explorador del catálogo en el flujo «desde dibujo»
(explorar_catalogo + texto_exploracion), recintos-nave en el
empaquetador (locales de superficie grande que van solos en su nivel)
y filtro por sector en ambos asistentes.
"""

from __future__ import annotations

import json
import os
import unittest

from core.errors import DomainError
from core import APP_VERSION
from domain import desde_dibujo as dd
from domain import servicios_engine as eng
from domain.servicios_specs import (ETIQUETAS_SECTORES,
                                    ETIQUETAS_INSTALACIONES,
                                    cargar_servicios, resumen_catalogo,
                                    servicio, servicios_por_sector,
                                    version_catalogo)
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NUEVOS_SALUD = ("CONSULTA_EXTERNA", "QUIROFANOS", "HOSPITALIZACION",
                "MATERNIDAD", "CARDIOLOGIA_HEMODINAMIA", "ENDOSCOPIA",
                "MEDICINA_NUCLEAR", "LABORATORIO_MICROBIOLOGIA",
                "BANCO_DE_SANGRE", "REHABILITACION_FISIOTERAPIA",
                "SALUD_MENTAL", "ODONTOLOGIA")
NUEVOS_OTROS = ("CIRCULO_INFANTIL", "ESCUELA_PRIMARIA",
                "ESCUELA_SECUNDARIA", "OFICINAS", "RESTAURANTE",
                "SUPERMERCADO", "HOTEL", "CENTRO_DEPORTIVO",
                "CENTRO_CULTURAL", "RESIDENCIA_ADULTOS",
                "ALMACEN_LOGISTICO")
RECT_GRANDE = [(0, 0), (60, 0), (60, 30), (0, 30)]


# ---------------------------------------------------------------------------
# catálogo v3.0
# ---------------------------------------------------------------------------

class TestCatalogoV3(unittest.TestCase):
    """34 servicios, 8 sectores, referencias sanas y cp1252."""

    def setUp(self) -> None:
        self.items = cargar_servicios()
        self.codigos = {s.codigo for s in self.items}

    def test_version_y_cifras_del_catalogo(self):
        self.assertEqual(version_catalogo(), "3.0")
        resumen = resumen_catalogo()
        self.assertEqual(resumen["version"], "3.0")
        self.assertGreaterEqual(resumen["servicios"], 34)
        self.assertGreaterEqual(resumen["locales"], 400)
        self.assertEqual(resumen["sectores"], 8)
        self.assertGreaterEqual(resumen["criticos"], 30)

    def test_los_23_servicios_nuevos_estan(self):
        for codigo in NUEVOS_SALUD + NUEVOS_OTROS:
            self.assertIn(codigo, self.codigos)

    def test_cada_servicio_lleva_sector_valido(self):
        for item in self.items:
            self.assertIn(item.sector, ETIQUETAS_SECTORES,
                          item.codigo)
            self.assertTrue(item.nombre, item.codigo)

    def test_sector_defecto_salud_en_lo_existentes(self):
        for codigo in ("ANATOMIA_PATOLOGICA", "MORGUE", "UCI",
                       "URGENCIAS", "FARMACIA"):
            self.assertEqual(servicio(codigo).sector, "SALUD")

    def test_servicios_por_sector_agrupa_y_ordena(self):
        grupos = servicios_por_sector()
        etiquetas = [et for et, _items in grupos]
        self.assertEqual(etiquetas[0], "Salud")
        self.assertEqual(len(etiquetas), 8)
        por_etiqueta = dict(grupos)
        self.assertEqual(len(por_etiqueta["Salud"]), 23)
        self.assertEqual(len(por_etiqueta["Educación"]), 3)
        self.assertEqual(len(por_etiqueta["Comercio y hostelería"]), 3)
        self.assertEqual(len(por_etiqueta["Administración"]), 1)
        self.assertEqual(len(por_etiqueta["Logística"]), 1)
        # todos los servicios aparecen exactamente una vez
        total = sum(len(items) for _et, items in grupos)
        self.assertEqual(total, len(self.items))

    def test_space_types_nuevos_existen_en_el_dna(self):
        with open(os.path.join(RAIZ, "resources", "knowledge",
                               "space_dna.json"),
                  encoding="utf-8") as fh:
            dna = {s["space_type"]
                   for s in json.load(fh)["space_types"]}
        for item in self.items:
            for local in item.locales:
                self.assertIn(local.space_type, dna,
                              f"{item.codigo}.{local.codigo}")

    def test_codigos_unicos_dentro_de_cada_servicio(self):
        for item in self.items:
            codigos = [l.codigo for l in item.locales]
            self.assertEqual(len(codigos), len(set(codigos)),
                             item.codigo)

    def test_vocabulario_instalaciones_incluye_vapor(self):
        self.assertIn("vapor", ETIQUETAS_INSTALACIONES)
        qx = servicio("QUIROFANOS")
        esteril = qx.local("ESTERILIZACION")
        self.assertIn("vapor", esteril.instalaciones)

    def test_nombres_del_catalogo_en_cp1252(self):
        for item in self.items:
            item.nombre.encode("cp1252")
            for local in item.locales:
                local.nombre.encode("cp1252")

    def test_relaciones_entre_servicios_nuevas(self):
        qx = servicio("QUIROFANOS")
        niveles = {r["servicio"]: r["nivel"]
                   for r in qx.relaciones_servicios}
        self.assertEqual(niveles.get("CEYE"), "obligatorio")
        ap = servicio("CONSULTA_EXTERNA")
        destino = {r["servicio"] for r in ap.relaciones_servicios}
        self.assertIn("LABORATORIO_CLINICO", destino)


# ---------------------------------------------------------------------------
# programas de los servicios nuevos
# ---------------------------------------------------------------------------

class TestProgramasNuevos(unittest.TestCase):
    """Programas dimensionados por los parámetros de cada servicio."""

    def test_bloque_quirurgico_con_quirofanos_repetidos(self):
        p = eng.programa_servicio("QUIROFANOS")
        self.assertEqual(p["totales"]["locales"], 16)   # + filtro v3.42
        qx = [r for r in p["renglones"] if r["space_type"]
              == "OPERATING_ROOM"]
        self.assertEqual(len(qx), 3)
        self.assertEqual(qx[1]["nombre"], "Quirofano 2")
        self.assertTrue(qx[0]["critico"])
        self.assertGreaterEqual(qx[0]["area_m2"], 36.0)

    def test_hospitalizacion_habitaciones_por_parametro(self):
        p = eng.programa_servicio("HOSPITALIZACION")
        ward = [r for r in p["renglones"]
                if r["space_type"] == "WARD"]
        self.assertEqual(len(ward), 12)
        self.assertAlmostEqual(ward[0]["area_m2"], 40.0)  # 28 + 2x6
        p2 = eng.programa_servicio(
            "HOSPITALIZACION", {"habitaciones": 20, "camas_habitacion": 1})
        ward2 = [r for r in p2["renglones"]
                 if r["space_type"] == "WARD"]
        self.assertEqual(len(ward2), 20)
        self.assertAlmostEqual(ward2[0]["area_m2"], 34.0)  # 28 + 1x6

    def test_consulta_externa_con_y_sin_toma_de_muestras(self):
        p = eng.programa_servicio("CONSULTA_EXTERNA")
        consultorios = [r for r in p["renglones"]
                        if r["space_type"] == "CONSULTATION_ROOM"]
        self.assertEqual(len(consultorios), 8)
        usos = {r["space_type"] for r in p["renglones"]}
        self.assertIn("SAMPLE_COLLECTION", usos)
        p2 = eng.programa_servicio("CONSULTA_EXTERNA",
                                   {"con_toma_muestras": False})
        usos2 = {r["space_type"] for r in p2["renglones"]}
        self.assertNotIn("SAMPLE_COLLECTION", usos2)

    def test_oficinas_area_por_puestos(self):
        p = eng.programa_servicio("OFICINAS")
        trabajo = next(r for r in p["renglones"]
                       if r["space_type"] == "OPEN_OFFICE")
        self.assertAlmostEqual(trabajo["area_m2"], 260.0)  # 20 + 40x6
        p2 = eng.programa_servicio("OFICINAS", {"puestos": 200})
        trabajo2 = next(r for r in p2["renglones"]
                        if r["space_type"] == "OPEN_OFFICE")
        self.assertAlmostEqual(trabajo2["area_m2"], 1220.0)

    def test_almacen_logistico_superficie_directa(self):
        p = eng.programa_servicio("ALMACEN_LOGISTICO")
        nave = next(r for r in p["renglones"]
                    if r["space_type"] == "WAREHOUSE")
        self.assertAlmostEqual(nave["area_m2"], 2100.0)
        muelles = next(r for r in p["renglones"]
                       if r["space_type"] == "LOADING_DOCK")
        self.assertAlmostEqual(muelles["area_m2"], 100.0)  # 20 + 4x20

    def test_hotel_habitaciones_repetidas(self):
        p = eng.programa_servicio("HOTEL")
        hab = [r for r in p["renglones"] if r["space_type"] == "BEDROOM"]
        self.assertEqual(len(hab), 60)
        p2 = eng.programa_servicio("HOTEL",
                                   {"con_restaurante": False})
        usos = {r["space_type"] for r in p2["renglones"]}
        self.assertNotIn("RESTAURANT", usos)
        self.assertNotIn("COMMERCIAL_KITCHEN", usos)

    def test_maternidad_salas_de_parto_y_cesarea(self):
        p = eng.programa_servicio("MATERNIDAD")
        partos = [r for r in p["renglones"]
                  if r["space_type"] == "DELIVERY_ROOM"]
        self.assertEqual(len(partos), 2)
        self.assertTrue(partos[0]["critico"])
        usos = {r["space_type"] for r in p["renglones"]}
        self.assertIn("OPERATING_ROOM", usos)  # cesarea por defecto
        p2 = eng.programa_servicio("MATERNIDAD",
                                   {"con_cesarea": False})
        usos2 = {r["space_type"] for r in p2["renglones"]}
        self.assertNotIn("OPERATING_ROOM", usos2)

    def test_escuela_primaria_aulas_y_escala(self):
        p = eng.programa_servicio("ESCUELA_PRIMARIA")
        aulas = [r for r in p["renglones"]
                 if r["space_type"] == "CLASSROOM"]
        self.assertEqual(len(aulas), 12)
        self.assertAlmostEqual(aulas[0]["area_m2"], 42.0)
        p2 = eng.programa_servicio("ESCUELA_PRIMARIA", {"aulas": 24})
        aulas2 = [r for r in p2["renglones"]
                  if r["space_type"] == "CLASSROOM"]
        self.assertEqual(len(aulas2), 24)

    def test_banco_de_sangre_criticos_y_escala(self):
        p = eng.programa_servicio("BANCO_DE_SANGRE")
        donacion = next(r for r in p["renglones"]
                        if r["codigo"] == "DONACION")
        self.assertAlmostEqual(donacion["area_m2"], 27.6)  # 18+12x0.8
        criticos = {r["codigo"] for r in p["renglones"] if r["critico"]}
        self.assertIn("FRACCIONAMIENTO", criticos)
        self.assertIn("ALMACEN_FRIO", criticos)

    def test_odontologia_sillones_y_opciones(self):
        p = eng.programa_servicio("ODONTOLOGIA")
        sillones = [r for r in p["renglones"]
                    if r["space_type"] == "DENTISTRY"]
        self.assertEqual(len(sillones), 2)
        p2 = eng.programa_servicio(
            "ODONTOLOGIA", {"sillones": 5, "con_laboratorio": True})
        sillones2 = [r for r in p2["renglones"]
                     if r["space_type"] == "DENTISTRY"]
        usos2 = {r["space_type"] for r in p2["renglones"]}
        self.assertEqual(len(sillones2), 5)
        self.assertIn("LABORATORY", usos2)

    def test_dimensiones_sugeridas_cierran_el_area_en_nuevos(self):
        for codigo in ("OFICINAS", "RESTAURANTE", "HOTEL",
                       "ESCUELA_PRIMARIA", "RESIDENCIA_ADULTOS"):
            p = eng.programa_servicio(codigo)
            for r in p["renglones"]:
                if r["area_m2"] > 72.0:
                    continue  # los grandes los empaqueta el explorador
                producto = r["ancho_m"] * r["fondo_m"]
                self.assertGreaterEqual(
                    producto, r["area_m2"] * 0.98,
                    f"{codigo}.{r['nombre']}")


# ---------------------------------------------------------------------------
# validación funcional de los nuevos
# ---------------------------------------------------------------------------

class TestValidacionNuevos(unittest.TestCase):
    """AREAS y CRITICOS limpios; puertas y separación del quirófano."""

    def test_validacion_ok_en_los_12_de_salud(self):
        for codigo in NUEVOS_SALUD:
            p = eng.programa_servicio(codigo)
            estados = {c["codigo"]: c["estado"] for c in p["validacion"]}
            self.assertEqual(estados.get("AREAS"), "ok", codigo)
            self.assertEqual(estados.get("CRITICOS"), "ok", codigo)

    def test_validacion_ok_en_los_11_de_otros_sectores(self):
        for codigo in NUEVOS_OTROS:
            p = eng.programa_servicio(codigo)
            estados = {c["codigo"]: c["estado"] for c in p["validacion"]}
            self.assertEqual(estados.get("AREAS"), "ok", codigo)

    def test_puertas_de_camilla_en_el_bloque_quirurgico(self):
        p = eng.programa_servicio("QUIROFANOS")
        puertas = next(c for c in p["validacion"]
                       if c["codigo"] == "PUERTAS")
        self.assertIn("1.20 m (catalogo)", puertas["detalle"])

    def test_separacion_limpio_sucio_en_quirofanos(self):
        p = eng.programa_servicio("QUIROFANOS")
        separacion = next(c for c in p["validacion"]
                          if c["codigo"] == "SEPARACION")
        self.assertIn("regla 06", separacion["nombre"])

    def test_criticidad_informativa_en_maternidad(self):
        p = eng.programa_servicio("MATERNIDAD")
        criticidad = next(c for c in p["validacion"]
                          if c["codigo"] == "CRITICIDAD")
        self.assertEqual(criticidad["estado"], "info")
        self.assertIn("nivel 1", criticidad["detalle"])


# ---------------------------------------------------------------------------
# explorador del catálogo (desde dibujo)
# ---------------------------------------------------------------------------

class TestExploradorCatalogo(unittest.TestCase):
    """El contorno se prueba contra TODO el catálogo, ordenado."""

    def setUp(self) -> None:
        self.resultados = dd.explorar_catalogo(RECT_GRANDE)

    def test_prueba_todos_los_servicios(self):
        self.assertEqual(len(self.resultados), 34)

    def test_orden_cabe_primero_y_errores_al_final(self):
        bandas = [(2 if r.get("error")
                   else (0 if r["cabe_un_nivel"] else 1))
                  for r in self.resultados]
        self.assertEqual(bandas, sorted(bandas))
        self.assertTrue(self.resultados[0]["cabe_un_nivel"])

    def test_farmacia_cabe_y_almacen_no_entra(self):
        codigo = {r["codigo"]: r for r in self.resultados}
        self.assertEqual(codigo["FARMACIA"]["cabe_un_nivel"], True)
        almacen = codigo["ALMACEN_LOGISTICO"]
        self.assertEqual(almacen["error"], "ARQ-DDI-003")
        self.assertIsNone(almacen["niveles"])

    def test_supermercado_usa_recinto_nave(self):
        a = dd.ajustar(eng.programa_servicio("SUPERMERCADO"),
                       RECT_GRANDE)
        ventas = [r for n in a["reparto"] for r in n["locales"]
                  if r["space_type"] == "RETAIL_LOCAL"]
        self.assertEqual(len(ventas), 1)
        self.assertGreater(ventas[0]["hall_fondo"], eng.FONDO_MAX - 1e-6)
        self.assertGreaterEqual(
            ventas[0]["hall_ancho"] * ventas[0]["hall_fondo"],
            ventas[0]["area_m2"] - 1.0)

    def test_gimnasio_cabe_en_banda_normal(self):
        # 216 m2 con fondo capado: fachada 25.4 m <= 60 m, no es nave.
        # v3.42.0: el pasillo adaptado puede re-dimensionarlo (cambia
        # fondo por ancho) pero su ÁREA se conserva íntegra
        a = dd.ajustar(eng.programa_servicio("CENTRO_DEPORTIVO"),
                       RECT_GRANDE)
        gym = [r for n in a["reparto"] for r in n["locales"]
               if r["space_type"] == "GYMNASIO"]
        self.assertEqual(len(gym), 1)
        self.assertGreaterEqual(
            gym[0]["hall_ancho"] * gym[0]["hall_fondo"],
            gym[0]["area_m2"] - 1.0)

    def test_contorno_pequeno_sin_excepciones(self):
        chico = dd.explorar_catalogo([(0, 0), (10, 0), (10, 6), (0, 6)])
        self.assertEqual(len(chico), 34)
        self.assertGreater(
            sum(1 for r in chico if r.get("error")), 0)

    def test_margen_reduce_los_que_caben(self):
        con_margen = dd.explorar_catalogo(RECT_GRANDE, 3.0, 4.0)
        cabe_base = sum(1 for r in self.resultados
                        if r["cabe_un_nivel"])
        cabe_margen = sum(1 for r in con_margen if r["cabe_un_nivel"])
        self.assertLessEqual(cabe_margen, cabe_base)

    def test_texto_exploracion_cp1252(self):
        texto = dd.texto_exploracion(self.resultados, 1800.0)
        texto.encode("cp1252")
        self.assertIn("EXPLORACION DEL CATALOGO", texto)
        self.assertIn("Area del contorno: 1800.00 m2", texto)
        self.assertIn("Servicios probados: 34", texto)
        self.assertIn("CABE EN 1 NIVEL", texto)
        self.assertIn("NO ENTRA (ARQ-DDI-003)", texto)
        self.assertIn("[Salud] FARMACIA", texto)
        self.assertNotIn("→", texto)


# ---------------------------------------------------------------------------
# aplicar servicios nuevos al proyecto
# ---------------------------------------------------------------------------

class TestAplicarNuevos(ARQGenTestCase):
    """Los servicios nuevos aplican entidades reales por los caminos
    oficiales."""

    def setUp(self) -> None:
        super().setUp()
        self.ctx = self.application.create_project(
            self.project_path("universal.arqgen"), name="Universal")
        self.arch = ArchitectureService(self.ctx)

    def tearDown(self) -> None:
        self.ctx.close()
        super().tearDown()

    def test_aplicar_oficinas_en_proyecto_vacio(self):
        resumen = eng.aplicar_servicio(self.ctx, "OFICINAS")
        espacios = self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)
        usos = {}
        for e in espacios:
            usos[e.space_type] = usos.get(e.space_type, 0) + 1
        self.assertEqual(usos.get("OPEN_OFFICE"), 1)
        self.assertEqual(usos.get("MEETING_ROOM"), 4)
        self.assertEqual(usos.get("SERVER_ROOM"), 1)
        self.assertEqual(usos.get("CORRIDOR"), 1)
        # proyecto vacío: edificio y nivel creados al vuelo
        self.assertEqual(resumen["nivel"], "Servicio Oficinas")
        niveles = self.ctx.architecture.list("LEVEL",
                                             self.ctx.project.id)
        self.assertEqual(len(niveles), 1)

    def test_aplicar_escuela_primaria_con_aulas(self):
        nivel = self.arch.create_level("PB", 0.0, 3.2)
        programa = eng.programa_servicio("ESCUELA_PRIMARIA")
        resumen = eng.aplicar_servicio(
            self.ctx, "ESCUELA_PRIMARIA", nivel_ref=nivel.code)
        espacios = self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)
        aulas = [e for e in espacios if e.space_type == "CLASSROOM"]
        self.assertEqual(len(aulas), 12)
        # cada renglón del programa + el pasillo de distribución
        self.assertEqual(len(resumen["creados"]),
                         programa["totales"]["locales"] + 1)

    def test_desde_dibujo_genera_escuela_con_crecimiento(self):
        programa = eng.programa_servicio("ESCUELA_PRIMARIA")
        analisis = dd.ajustar(programa, [(0, 0), (40, 0), (40, 18),
                                         (0, 18)])
        self.assertGreaterEqual(analisis["niveles"], 2)
        resumen = dd.aplicar_plan(
            self.ctx, analisis,
            {"nombre_edificio": "Escuela desde dibujo",
             "modo": "servicio"})
        niveles = self.ctx.architecture.list("LEVEL",
                                             self.ctx.project.id)
        self.assertEqual(len(niveles), analisis["niveles"])
        espacios = self.ctx.architecture.list("SPACE",
                                              self.ctx.project.id)
        aulas = [e for e in espacios if e.space_type == "CLASSROOM"]
        escaleras = [e for e in espacios if e.space_type == "STAIR"]
        self.assertEqual(len(aulas), 12)
        self.assertGreaterEqual(len(escaleras), analisis["niveles"])
        self.assertEqual(resumen["modo"], "servicio")
        self.ctx.commit()


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
    """Filtro de sector en ambos asistentes y explorador en la GUI."""

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

    def test_filtro_de_sector_en_el_asistente(self):
        self.window.open_servicios_dialog()
        self.window.update()
        filtro = self.window._servicios_filtro
        self.assertEqual(list(filtro["values"])[0], "Todos")
        self.assertEqual(len(list(filtro["values"])), 9)
        self.window._servicios_sector.set("Educación")
        self.window._servicios_aplica_filtro()
        valores = list(self.window._servicios_combo["values"])
        self.assertEqual(len(valores), 3)
        self.assertTrue(valores[0].startswith("CIRCULO_INFANTIL - "))
        self.assertEqual(self.window._servicios_sel(),
                         "CIRCULO_INFANTIL")

    def test_filtro_todos_devuelve_el_catalogo_completo(self):
        self.window.open_servicios_dialog()
        self.window.update()
        self.window._servicios_sector.set("Salud")
        self.window._servicios_aplica_filtro()
        self.assertEqual(
            len(list(self.window._servicios_combo["values"])), 23)
        self.window._servicios_sector.set("Todos")
        self.window._servicios_aplica_filtro()
        self.assertEqual(
            len(list(self.window._servicios_combo["values"])), 34)

    def test_filtro_y_explorador_en_desde_dibujo(self):
        self.window.open_desde_dibujo_dialog()
        self.window.update()
        self.assertEqual(list(self.window._dd_filtro["values"])[0],
                         "Todos")
        self.window._dd_sector.set("Comercio y hostelería")
        self.window._dd_aplica_filtro()
        valores = list(self.window._dd_combo_srv["values"])
        self.assertEqual(len(valores), 3)
        self.assertTrue(valores[0].startswith("RESTAURANTE - "))
        # explorador sobre el rectángulo por defecto (20 x 12)
        self.window._dd_origen.set("rectangulo")
        self.window._dd_origen_cambio()
        self.window._dd_explorar()
        texto = self.window._dd_texto.get("1.0", "end")
        self.assertIn("EXPLORACION DEL CATALOGO", texto)
        self.assertIn("CABE EN 1 NIVEL", texto)

    def test_version_coherente_con_v3410(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
