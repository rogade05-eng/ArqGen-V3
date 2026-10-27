"""ESPECIFICACIONES TÉCNICAS HOSPITALARIAS + VALIDACIÓN DIMENSIONAL
(v3.22.0) — domain/hospital_specs.py, resources/knowledge/
hospital_specs.json y las capas que alimentan.

El documento del usuario («Especificaciones técnicas integrales para
locales hospitalarios», 20 secciones) entra al programa como datos:

* Fichas cualitativas de 60 locales (función, relaciones, arquitectura,
  electricidad, iluminación, hidráulica, HVAC, gases, higiene...).
* Cuadro de cotas MIN/REC de 53 tipologías con su clasificación A-F
  (una cota de programación NUNCA se anuncia como normativa).
* Matriz de prioridad funcional, flujos incompatibles, cotas de
  puertas/mobiliario, checklist de validación (sección 19) y fuentes.
* CONTROL DE VALIDACIÓN DIMENSIONAL por local: superficie, ancho,
  altura, puertas y pasillos medidos contra el uso; el resto del
  checklist queda pendiente (cálculo o fabricante).
* 40 especialidades nuevas en el DNA (de la sala de autopsias a la
  UCI neonatal y el archivo clínico) con lux, mobiliario, equipos,
  pasillo y puerta de camilla.
* Ficha PDF del local con la ficha técnica, cotas de referencia,
  control §19 y fuentes; botón «Validar cotas» en el asistente.
"""

from __future__ import annotations

import os
import re
import unittest
import zlib

from core.errors import DomainError
from services.architecture_service import ArchitectureService
from tests.base import ARQGenTestCase

from ui import editor_espacios as edi


def _display_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


DISPLAY = _display_available()


class _Base(ARQGenTestCase):
    """Proyecto con un nivel de 3,2 m para montar locales de prueba."""

    def setUp(self) -> None:
        super().setUp()
        self.context = self.application.create_project(
            self.project_path("hospital.arqgen"), name="Hospital")
        self.arq = ArchitectureService(self.context)

    def _local(self, nombre, uso, x0, y0, x1, y1, con_puerta=False,
               ancho_puerta=None):
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                     ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            self.arq.create_wall(self.nivel.code, a, b, 0.2)
        local = self.arq.create_space(
            self.nivel.code, nombre, uso,
            [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        if con_puerta:
            edi.crear_acceso(self.context, local.id, ancho=ancho_puerta)
        return local


class TestDocumento(_Base):
    """El documento integrado: fichas, cuadro de cotas y matrices."""

    def setUp(self):
        super().setUp()
        from domain.hospital_specs import cargar_specs
        self.specs = cargar_specs()
        self.nivel = self.arq.create_level("PB", 0.0, 3.2)

    def test_documento_carga_y_esta_completo(self):
        self.assertIsNotNone(self.specs)
        self.assertEqual(len(self.specs.fichas), 60)
        self.assertEqual(len(self.specs.cotas_cuadro), 53)
        self.assertGreaterEqual(len(self.specs.checklist), 22)
        self.assertGreaterEqual(len(self.specs.flujos), 12)
        self.assertGreaterEqual(len(self.specs.fuentes), 5)
        self.assertTrue(self.specs.advertencia)
        self.assertIn("Nunca", self.specs.clasificacion.get("nota", ""))

    def test_carga_cacheada(self):
        from domain.hospital_specs import cargar_specs
        self.assertIs(cargar_specs(), self.specs)

    def test_fichas_tecnicas_de_los_tipos(self):
        morgue = self.specs.ficha("MORGUE")
        self.assertIn("función", morgue["campos"])
        self.assertIn("higiene", morgue["campos"])
        qui = self.specs.ficha("OPERATING_ROOM")
        self.assertIn("gases", qui["campos"])
        self.assertIn("presión", qui["campos"])
        self.assertTrue(any("oxígeno" in g
                            for g in qui["campos"]["gases"]))
        self.assertIn("ASHRAE", " ".join(qui["campos"]["hvac"]))
        autopsias = self.specs.ficha("AUTOPSY_ROOM")
        self.assertIn("relaciones", autopsias["campos"])
        self.assertTrue(any("morgue" in r.lower()
                            for r in autopsias["campos"]["relaciones"]))

    def test_cuadro_de_cotas_quirofano(self):
        item = self.specs.item_cotas("OPERATING_ROOM")
        self.assertEqual(item["nombre"], "Cota base")
        self.assertAlmostEqual(float(item["min_m2"]["min"]), 37.2,
                               places=2)
        self.assertAlmostEqual(float(item["rec_m2"]["min"]), 42.25,
                               places=2)
        self.assertIn("6.10 x 6.10", item["cota_tipica"])
        self.assertTrue(any("49" in n for n in item["notas"]))

    def test_item_de_cotas_por_tipo(self):
        autopsias = self.specs.item_cotas("AUTOPSY_ROOM")
        self.assertEqual(autopsias["nombre"], "Sala de autopsias")
        self.assertAlmostEqual(float(autopsias["min_m2"]["min"]), 20.0,
                               places=6)
        nicu = self.specs.item_cotas("NICU")
        self.assertAlmostEqual(float(nicu["rec_m2"]["min"]), 12.0,
                               places=6)
        tomografia = self.specs.item_cotas("CT_ROOM")
        self.assertEqual(tomografia["nombre"], "Sala de TC")
        self.assertAlmostEqual(float(tomografia["min_m2"]["min"]), 30.0,
                               places=6)

    def test_prioridad_funcional(self):
        self.assertEqual(self.specs.prioridad_de("OPERATING_ROOM"),
                         "critica")
        self.assertEqual(self.specs.prioridad_de("ICU"), "critica")
        self.assertEqual(self.specs.prioridad_de("EMERGENCY_ROOM"),
                         "alta")
        self.assertEqual(self.specs.prioridad_de("CONSULTATION_ROOM"),
                         "media")
        self.assertEqual(self.specs.prioridad_de("OFFICE"), "baja")
        self.assertEqual(self.specs.prioridad_de("ROOM"), "")

    def test_flujos_y_clasificacion_de_cotas(self):
        self.assertIn("material estéril", self.specs.flujos)
        self.assertIn("cadáveres", self.specs.flujos)
        clasif = self.specs.clasificacion
        self.assertIn("Normativa", clasif["A"])
        self.assertIn("programación", clasif["B"])
        self.assertIn("fabricante", clasif["D"])
        self.assertIn("Nunca", clasif["nota"])

    def test_cotas_de_puertas_y_mobiliario(self):
        morgue = next(p for p in self.specs.cotas_puertas
                      if "morgue" in p["nombre"].lower())
        self.assertIn("1.40-1.60", morgue["valor"])
        meseta = next(m for m in self.specs.cotas_mobiliario
                      if "Meseta" in m["nombre"])
        self.assertIn("0.60-0.75", meseta["valor"])


class TestDNAAmpliado(_Base):
    """Las 40 especialidades nuevas del documento en el DNA."""

    def setUp(self):
        super().setUp()
        self.registry = self.application.dna_registry

    def test_dna_con_las_especialidades_nuevas(self):
        self.assertGreaterEqual(len(self.registry), 75)
        for tipo in ("AUTOPSY_ROOM", "PREOP_ROOM", "RECOVERY_ROOM",
                     "MRI_ROOM", "ULTRASOUND_ROOM", "ICU_PEDIATRIC",
                     "NICU", "ISOLATION_ROOM", "MOLECULAR_BIOLOGY_LAB",
                     "BLOOD_BANK", "DIALYSIS_ROOM", "ENDOSCOPY_ROOM",
                     "STERILE_PHARMACY", "REHABILITATION",
                     "DELIVERY_ROOM", "NEONATOLOGY", "PEDIATRICS",
                     "CATH_LAB", "NUCLEAR_MEDICINE", "MEDICAL_GAS_PLANT",
                     "ELECTRICAL_ROOM", "GENERATOR_ROOM", "UPS_ROOM",
                     "LAUNDRY", "CLEAN_LINEN", "SOILED_LINEN",
                     "CLEANING_ROOM", "ADMINISTRATION",
                     "CLINICAL_ARCHIVE", "ADMISSION", "STERILE_STORE"):
            self.assertIsNotNone(self.registry.get(tipo), tipo)

    def test_valores_del_cuadro_en_el_dna(self):
        autopsias = self.registry.require("AUTOPSY_ROOM")
        self.assertEqual(autopsias.name_es, "Sala de autopsias")
        self.assertAlmostEqual(autopsias.minimum_area, 20.0, places=6)
        self.assertAlmostEqual(autopsias.preferred_area, 30.0, places=6)
        hemodinamia = self.registry.require("CATH_LAB")
        self.assertAlmostEqual(hemodinamia.minimum_area, 25.0, places=6)
        self.assertEqual(
            hemodinamia.metadata["neufert"]["puerta_m"], 1.4)
        limpieza = self.registry.require("CLEANING_ROOM")
        self.assertAlmostEqual(limpieza.minimum_area, 3.0, places=6)

    def test_metadata_tecnica_de_las_fichas(self):
        aislamiento = self.registry.require("ISOLATION_ROOM")
        self.assertIn("antecamara", aislamiento.metadata)
        self.assertIn("presion", aislamiento.metadata)
        neonatal = self.registry.require("NICU")
        self.assertIn("incubadoras", neonatal.metadata)
        self.assertEqual(neonatal.metadata["pasillo_m"], 2.4)
        hemo = self.registry.require("DIALYSIS_ROOM")
        self.assertIn("agua", hemo.metadata)
        gases = self.registry.require("MEDICAL_GAS_PLANT")
        self.assertIn("gases", gases.metadata)
        resonancia = self.registry.require("MRI_ROOM")
        self.assertIn("zonas_seguridad", resonancia.metadata)

    def test_adjacencias_clinicas(self):
        nicu = self.registry.require("NICU")
        self.assertIn("NEONATOLOGY", nicu.preferred_adjacencies)
        esterior = self.registry.require("STERILE_STORE")
        self.assertIn("STERILIZATION_ROOM",
                      esterior.preferred_adjacencies)
        partos = self.registry.require("DELIVERY_ROOM")
        self.assertIn("NICU", partos.functional_relationships)

    def test_pasillo_por_uso_en_el_asistente(self):
        from ui.building_wizard import pasillo_minimo_de_uso
        self.assertEqual(pasillo_minimo_de_uso("NICU"), 2.4)
        self.assertEqual(pasillo_minimo_de_uso("MOLECULAR_BIOLOGY_LAB"),
                         1.5)
        self.assertIsNone(pasillo_minimo_de_uso("ROOM"))


class TestCapasPorUso(_Base):
    """Lux, mobiliario y equipos de las especialidades nuevas."""

    def test_lux_por_uso_de_las_nuevas(self):
        from domain.iluminacion import LUX_POR_USO, lux_para
        self.assertEqual(LUX_POR_USO["DELIVERY_ROOM"], 500)
        self.assertEqual(LUX_POR_USO["MRI_ROOM"], 150)
        self.assertEqual(LUX_POR_USO["NICU"], 300)
        self.assertEqual(LUX_POR_USO["UPS_ROOM"], 500)
        self.assertEqual(LUX_POR_USO["CLEANING_ROOM"], 100)
        self.assertEqual(lux_para("NICU"), 300)

    def test_mobiliario_de_las_nuevas(self):
        from domain import mobiliario as mob
        for tipo in ("NICU", "LAUNDRY", "ADMINISTRATION",
                     "AUTOPSY_ROOM", "DIALYSIS_ROOM", "ADMISSION"):
            self.assertIn(tipo, mob.REGLAS, tipo)
        piezas = mob.proponer_piezas("NICU", 14.0, ambito="social")
        self.assertEqual([r.clave for r in piezas][0], "cuna")
        piezas2 = mob.proponer_piezas("LAUNDRY", 30.0, ambito="social")
        self.assertIn("lavadora", [r.clave for r in piezas2])
        # la cuna y la bañera ahora sirven también en salud
        self.assertEqual(mob.CATALOGO["cuna"].ambito, "ambos")
        self.assertEqual(mob.CATALOGO["bañera"].ambito, "ambos")

    def test_equipos_en_el_presupuesto_vivo(self):
        from ui.variant_budget import CATEGORIAS_SIN_CALIDAD, \
            EQUIPOS_POR_USO
        mri = EQUIPOS_POR_USO["MRI_ROOM"]
        self.assertEqual(mri[0][2], 5_200_000.0)
        self.assertGreaterEqual(len(EQUIPOS_POR_USO["DIALYSIS_ROOM"]), 2)
        self.assertIn("NICU", EQUIPOS_POR_USO)
        self.assertIn("Equipos", CATEGORIAS_SIN_CALIDAD)


class TestValidacionDimensional(_Base):
    """El control §19: superficie, ancho, altura, puertas, pasillos."""

    def setUp(self):
        super().setUp()
        self.nivel = self.arq.create_level("PB", 0.0, 3.2)

    def test_quirofano_escaso_se_senala(self):
        qui = self._local("Quirófano 1", "OPERATING_ROOM",
                          0.0, 0.0, 5.0, 5.0)
        informe = edi.validacion_local(self.context, qui.id)
        severidades = {h["codigo"]: h["severidad"]
                       for h in informe["hallazgos"]}
        self.assertEqual(severidades["V01"], "fallo")
        self.assertEqual(severidades["V02"], "fallo")
        self.assertIn("37.20", severidades and
                      next(h["mensaje"] for h in informe["hallazgos"]
                           if h["codigo"] == "V01"))
        self.assertEqual(informe["prioridad"], "critica")
        self.assertEqual(len(informe["checklist"]), 23)

    def test_morgue_conforme_pasa(self):
        morgue = self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5,
                             con_puerta=True)
        informe = edi.validacion_local(self.context, morgue.id)
        severidades = {h["codigo"]: h["severidad"]
                       for h in informe["hallazgos"]}
        self.assertEqual(severidades["V01"], "ok")
        self.assertEqual(severidades["V04"], "ok")
        self.assertEqual(informe["prioridad"], "media")
        texto = edi.texto_validacion(informe)
        texto.encode("cp1252")
        self.assertIn("VALIDACIÓN DIMENSIONAL", texto)
        self.assertIn("[x] SUPERFICIE", texto)

    def test_puerta_menor_que_la_del_uso(self):
        qui = self._local("Quirófano 2", "OPERATING_ROOM",
                          0.0, 0.0, 6.1, 6.1, con_puerta=True,
                          ancho_puerta=0.9)
        informe = edi.validacion_local(self.context, qui.id)
        severidades = {h["codigo"]: h["severidad"]
                       for h in informe["hallazgos"]}
        self.assertEqual(severidades["V01"], "ok")
        self.assertEqual(severidades["V04"], "fallo")
        v04 = next(h for h in informe["hallazgos"]
                   if h["codigo"] == "V04")
        self.assertIn("0.90", v04["mensaje"])

    def test_uso_sin_cotas_en_el_cuadro_usa_el_dna(self):
        sala = self._local("Estar", "LIVING_ROOM", 0.0, 0.0, 4.0, 3.0)
        informe = edi.validacion_local(self.context, sala.id)
        severidades = {h["codigo"]: h["severidad"]
                       for h in informe["hallazgos"]}
        # sin cuadro de cotas para el uso: la mínima sale del DNA
        self.assertIsNone(informe["cotas"])
        self.assertIn("V01", severidades)
        self.assertIn(severidades["V01"],
                      ("ok", "fallo", "aviso", "info"))

    def test_validar_proyecto_cuenta_por_severidad(self):
        self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5)
        self._local("Quirófano escaso", "OPERATING_ROOM",
                    6.0, 0.0, 11.0, 5.0)
        from domain.hospital_specs import validar_proyecto
        rep = validar_proyecto(self.context)
        self.assertEqual(len(rep["locales"]), 2)
        self.assertGreaterEqual(rep["resumen"]["fallos"], 2)
        self.assertGreaterEqual(rep["resumen"]["ok"], 1)

    def test_la_validacion_no_modifica_el_proyecto(self):
        self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5)
        antes = len(list(self.context.architecture.list(
            "SPACE", self.context.project.id)))
        muros_antes = len(list(self.context.architecture.list(
            "WALL", self.context.project.id)))
        from domain.hospital_specs import validar_proyecto
        validar_proyecto(self.context)
        despues = len(list(self.context.architecture.list(
            "SPACE", self.context.project.id)))
        muros_despues = len(list(self.context.architecture.list(
            "WALL", self.context.project.id)))
        self.assertEqual((antes, muros_antes), (despues,
                                                muros_despues))

    def test_checklist_geometrico_y_pendiente(self):
        morgue = self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5)
        informe = edi.validacion_local(self.context, morgue.id)
        estados = [p["estado"] for p in informe["checklist"]]
        self.assertEqual(estados[0], "cumple")      # SUPERFICIE
        self.assertEqual(estados[-1], "pendiente")  # NORMA LOCAL
        pendientes = [p for p in informe["checklist"]
                      if p["estado"] == "pendiente"]
        self.assertGreaterEqual(len(pendientes), 10)
        medidos = [p for p in informe["checklist"] if p["cota_tipo"]]
        self.assertTrue(all(p["cota_tipo"] in "BC" for p in medidos))

    def test_texto_validacion_es_cp1252(self):
        qui = self._local("Quirófano 1", "OPERATING_ROOM",
                          0.0, 0.0, 5.0, 5.0)
        informe = edi.validacion_local(self.context, qui.id)
        texto = edi.texto_validacion(informe)
        texto.encode("cp1252")
        self.assertIn("CRITICA", texto)
        self.assertIn("Control de validación dimensional", texto)
        self.assertIn("nunca son normativa", texto)


class TestFichaPDF(_Base):
    """La ficha del local imprime las capas hospitalarias."""

    def setUp(self):
        super().setUp()
        self.nivel = self.arq.create_level("PB", 0.0, 3.2)

    def _texto_pdf(self, ruta):
        raw = open(ruta, "rb").read()
        texto = b""
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
            try:
                texto += zlib.decompress(m.group(1))
            except Exception:  # noqa: BLE001 — stream sin comprimir
                texto += m.group(1)
        return texto.decode("latin-1", "ignore")

    def test_ficha_con_secciones_hospitalarias(self):
        morgue = self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5)
        from exporters.ficha_local import export_ficha_local_pdf
        ruta = os.path.join(self.tmp, "ficha_morgue.pdf")
        export_ficha_local_pdf(self.context, morgue.id, ruta)
        raw = open(ruta, "rb").read()
        self.assertTrue(raw.startswith(b"%PDF"))
        self.assertGreater(len(raw), 4000)
        texto = self._texto_pdf(ruta)
        self.assertIn("Especificaciones técnicas del uso", texto)
        self.assertIn("Control de validación dimensional", texto)
        self.assertIn("Cotas de referencia del uso", texto)
        self.assertIn("Fuentes y advertencia", texto)
        self.assertIn("MEDIA", texto)          # prioridad funcional
        self.assertIn("10 m2", texto)          # mínima del cuadro
        self.assertIn("12-16 m2", texto)       # recomendada del cuadro

    def test_ficha_de_local_no_hospitalario_no_falla(self):
        sala = self._local("Estar", "LIVING_ROOM", 0.0, 0.0, 4.0, 3.0)
        from exporters.ficha_local import export_ficha_local_pdf
        ruta = os.path.join(self.tmp, "ficha_estar.pdf")
        export_ficha_local_pdf(self.context, sala.id, ruta)
        self.assertTrue(open(ruta, "rb").read().startswith(b"%PDF"))

    def test_resumen_completo_trae_el_bloque_hospital(self):
        morgue = self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5)
        datos = edi.resumen_completo(self.context, morgue.id)
        self.assertEqual(datos["hospital"]["prioridad"], "media")
        self.assertIn("higiene",
                      datos["hospital"]["ficha"]["campos"])
        self.assertEqual(
            datos["hospital"]["cotas"]["nombre"],
            "Recepción técnica de cadáveres")
        self.assertIn("Prioridad funcional",
                      edi.texto_resumen_completo(datos))


class TestRecursoEmpaquetado(_Base):
    """El recurso viaja en el bundle y el botón existe."""

    def test_compilar_bundle_verifica_el_recurso(self):
        with open(os.path.join(PROJECT_ROOT, "compilar_bundle.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("knowledge/hospital_specs.json", src)

    def test_tooltip_del_boton_validar(self):
        from ui.help import TOOLTIPS
        self.assertIn("editor_local_validar", TOOLTIPS)
        self.assertIn("sección 19", TOOLTIPS["editor_local_validar"])

    def test_conexion_de_ciclo_de_vida_queda_ociosa(self):
        """v3.22.0: create/open NO dejan transacción abierta.

        El evento del ciclo de vida (PROJECT_CREATED/OPENED) se
        inserta después del commit de siempre; sin confirmarlo, un
        contexto descartado sin recoger por el GC retenía el LOCK de
        SQLite y tumbaba la siguiente escritura («database is
        locked», visible en el presupuesto PRECONS).
        """
        import gc
        import sqlite3
        ruta = self.project_path("ciclo.arqgen")
        self.application.create_project(ruta, "Ciclo")  # descartado
        self.context = self.application.open_project(ruta)
        gc.collect()  # igual que el GC del intérprete tarde o temprano
        conns = [o for o in gc.get_objects()
                 if isinstance(o, sqlite3.Connection)]
        pendientes = []
        for c in conns:
            if getattr(c, "_closed", False):
                continue
            try:
                dbs = [row[2] for row in
                       c.execute("PRAGMA database_list").fetchall()]
            except sqlite3.ProgrammingError:
                continue  # conexión cerrada entre medias
            if os.path.abspath(ruta) in [os.path.abspath(d) for d in dbs
                                         if d]:
                if c.in_transaction:
                    pendientes.append(True)
        self.assertEqual(pendientes, [])


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(DISPLAY, "requiere display Tk (Xvfb :99)")
class TestDialogoValidacion(_Base):
    """El botón «Validar cotas» del asistente de local (GUI)."""

    def _ventana(self):
        from ui.app_window import ARQGenWindow
        from ui import theme
        theme.set_mode("dark")
        window = ARQGenWindow(self.context, self.application)
        window.update()
        self.addCleanup(window.destroy)
        return window

    def test_boton_validar_muestra_el_informe(self):
        self.nivel = self.arq.create_level("PB", 0.0, 3.2)
        qui = self._local("Quirófano 1", "OPERATING_ROOM",
                          0.0, 0.0, 5.0, 5.0)
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        eid = qui.id
        window._validar_cotas_local(dialogo, lambda: eid,
                                    dialogo._editor_diag)
        texto = dialogo._editor_diag.get("1.0", "end")
        self.assertIn("VALIDACIÓN DIMENSIONAL", texto)
        self.assertIn("[X] V01", texto)
        self.assertIn("SUPERFICIE >= SUPERFICIE_MIN", texto)
        dialogo.destroy()

    def test_boton_validar_con_local_conforme(self):
        self.nivel = self.arq.create_level("PB", 0.0, 3.2)
        morgue = self._local("Morgue", "MORGUE", 0.0, 0.0, 5.0, 3.5,
                             con_puerta=True)
        window = self._ventana()
        window.open_editor_local_dialog()
        dialogo = window._editor_dialogo
        eid = morgue.id
        window._validar_cotas_local(dialogo, lambda: eid,
                                    dialogo._editor_diag)
        texto = dialogo._editor_diag.get("1.0", "end")
        self.assertIn("[OK] V01", texto)
        self.assertIn("[x] SUPERFICIE", texto)
        dialogo.destroy()


if __name__ == "__main__":
    unittest.main()
