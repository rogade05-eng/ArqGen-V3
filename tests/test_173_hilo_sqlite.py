"""HILO SEGURO SQLITE v3.39.1 (persistence/sqlite/connection.py).

El usuario reportó al importar un plano en la GUI:

    ERROR AL IMPORTAR
    Error SQL: SQLite objects created in a thread can only be used in
    that same thread. The object was created in thread id 17124 and
    this is thread id 10716.

Causa: la conexión del proyecto se abre en el hilo principal (al abrir
o crear el archivo) y «Importar al proyecto» ejecuta
ArchitectureService en un hilo de fondo (_run_async del diálogo DXF/
DWG). Con el ajuste por defecto de sqlite3 ese cruce aborta siempre.
Las pruebas no lo vieron porque el diálogo GUI se ejercita con
_dxf_sync=True (camino síncrono).

Arreglo: check_same_thread=False + _DB_LOCK (RLock) que serializa
execute/commit/rollback/close. Estas pruebas replican el camino REAL:
proyecto creado en el hilo principal, trabajo pesado en un hilo ajeno.
"""

from __future__ import annotations

import os
import threading
import unittest

import ezdxf

from core import APP_VERSION
from persistence.sqlite.connection import ConnectionManager, Session
from tests.base import ARQGenTestCase

MURO = "ARQ-MURO"


def _dxf_minimo(path: str) -> str:
    """Plano mínimo con 4 LINE de muro formando un local cerrado."""
    doc = ezdxf.new("R12")
    msp = doc.modelspace()
    msp.add_line((0, 0), (6, 0), dxfattribs={"layer": MURO})
    msp.add_line((6, 0), (6, 4), dxfattribs={"layer": MURO})
    msp.add_line((6, 4), (0, 4), dxfattribs={"layer": MURO})
    msp.add_line((0, 4), (0, 0), dxfattribs={"layer": MURO})
    doc.saveas(path)
    return path


# ---------------------------------------------------------------------------
# 1) LA CONEXIÓN CRUZA HILOS (regresión del error del usuario)
# ---------------------------------------------------------------------------

class TestConexionCruzaHilos(ARQGenTestCase):
    """Proyecto abierto en el hilo principal, usado desde otro hilo."""

    def test_importar_plano_desde_hilo_de_fondo(self):
        # Reproducción LITERAL del diálogo: work() corre en un hilo y
        # usa ArchitectureService(self.ctx) sobre la conexión abierta
        # en el hilo principal. Antes: ProgrammingError de sqlite3.
        from importers.dxf_reader import DxfImporter
        from services.architecture_service import ArchitectureService
        context = self.application.create_project(
            self.project_path("hilo.arqgen"), name="Hilo")
        path = _dxf_minimo(os.path.join(self.tmp, "plano.dxf"))
        holder = {}

        def work():
            try:
                holder["ok"] = DxfImporter().apply(
                    path, ArchitectureService(context), "PB Hilo")
                context.commit()
            except Exception as exc:  # noqa: BLE001
                holder["error"] = exc

        h = threading.Thread(target=work, daemon=True)
        h.start()
        h.join(60)
        self.assertNotIn("error", holder, str(holder.get("error")))
        self.assertEqual(holder["ok"]["walls"], 4)
        muros = context.architecture.list("WALL", context.project.id)
        self.assertEqual(len(muros), 4)

    def test_settings_commit_y_lectura_desde_hilo_ajena(self):
        context = self.application.create_project(
            self.project_path("cfg.arqgen"), name="Cfg")
        holder = {}

        def work():
            try:
                context.settings.set("asistente_estado", "prueba-hilo")
                context.commit()
                holder["valor"] = context.settings.get("asistente_estado")
            except Exception as exc:  # noqa: BLE001
                holder["error"] = exc

        h = threading.Thread(target=work, daemon=True)
        h.start()
        h.join(30)
        self.assertNotIn("error", holder, str(holder.get("error")))
        self.assertEqual(holder["valor"], "prueba-hilo")

    def test_arquitectura_desde_hilo_ajena_auditoria_y_eventos(self):
        from services.architecture_service import ArchitectureService
        context = self.application.create_project(
            self.project_path("aud.arqgen"), name="Aud")
        holder = {}

        def work():
            try:
                arq = ArchitectureService(context)
                sitio = arq.create_site("Solar del hilo")
                context.commit()
                holder["id"] = sitio.id
            except Exception as exc:  # noqa: BLE001
                holder["error"] = exc

        h = threading.Thread(target=work, daemon=True)
        h.start()
        h.join(30)
        self.assertNotIn("error", holder, str(holder.get("error")))
        sitio = context.architecture.get("SITE", holder["id"])
        self.assertIsNotNone(sitio)
        self.assertEqual(sitio.name, "Solar del hilo")

    def test_rollback_desde_hilo_ajena(self):
        context = self.application.create_project(
            self.project_path("rb.arqgen"), name="Rb")
        errores = []

        def work():
            try:
                context.settings.set("temporal", "x")
                context.rollback()  # descarta sin confirmar
            except Exception as exc:  # noqa: BLE001
                errores.append(exc)

        h = threading.Thread(target=work, daemon=True)
        h.start()
        h.join(30)
        self.assertEqual(errores, [])
        # settings.get devuelve "" para claves ausentes.
        self.assertIn(context.settings.get("temporal"), ("", None))


# ---------------------------------------------------------------------------
# 2) CONCURRENCIA ORDENADA POR EL CANDADO
# ---------------------------------------------------------------------------

class TestConcurrenciaSerializada(ARQGenTestCase):
    """Varios hilos a la vez: el candado los pone en cola, nadie cae."""

    def test_ocho_hilos_escriben_configuraciones_distintas(self):
        context = self.application.create_project(
            self.project_path("conc.arqgen"), name="Conc")
        errores = []
        barrera = threading.Barrier(8)

        def work(n: int):
            try:
                barrera.wait(30)
                context.settings.set(f"clave_{n}", f"valor_{n}")
                context.commit()
            except Exception as exc:  # noqa: BLE001
                errores.append(exc)

        hilos = [threading.Thread(target=work, args=(n,), daemon=True)
                 for n in range(8)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(60)
        self.assertEqual(errores, [])
        for n in range(8):
            self.assertEqual(context.settings.get(f"clave_{n}"),
                             f"valor_{n}")

    def test_sesion_directa_desde_otro_hilo_y_verificacion(self):
        # Capa pura: conexión abierta aquí, Session usada allá.
        db = os.path.join(self.tmp, "pura.db")
        conn = ConnectionManager(db).connect()
        sesion = Session(conn)
        holder = {}

        def work():
            try:
                sesion.execute(
                    "CREATE TABLE IF NOT EXISTS t (v TEXT)")
                sesion.execute("INSERT INTO t (v) VALUES (?)", ("desde_hilo",))
                sesion.commit()
                holder["filas"] = [r["v"] for r in
                                   sesion.query_all("SELECT v FROM t")]
                holder["integridad"] = ConnectionManager.integrity_check(conn)
            except Exception as exc:  # noqa: BLE001
                holder["error"] = exc

        h = threading.Thread(target=work, daemon=True)
        h.start()
        h.join(30)
        self.assertNotIn("error", holder, str(holder.get("error")))
        self.assertEqual(holder["filas"], ["desde_hilo"])
        self.assertEqual(holder["integridad"], "ok")
        sesion.close()


# ---------------------------------------------------------------------------
# 3) VERSIÓN
# ---------------------------------------------------------------------------

class TestVersionV3391(unittest.TestCase):

    def test_version_coherente_con_v3410(self):
        self.assertEqual(APP_VERSION, "3.50.0")


if __name__ == "__main__":
    unittest.main()
