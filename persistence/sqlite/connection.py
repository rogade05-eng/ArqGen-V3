"""SQLite connection management and session/transaction helpers (spec 78).

v3.39.1: la conexión del proyecto se abre en el hilo principal (al abrir
o crear el archivo) y la UI puede lanzar operaciones largas en hilos de
fondo (p. ej. «Importar al proyecto» del plano DXF/DWG usa
ArchitectureService en un hilo daemon). Con el ajuste por defecto de
sqlite3 eso aborta con "SQLite objects created in a thread can only be
used in that same thread". La conexión se crea ahora con
check_same_thread=False y TODO el acceso pasa por _DB_LOCK, un candado
reentrante que serializa las transacciones exactamente igual que la
serialización natural de un programa de un solo hilo: en una app de
escritorio monousuario no hay dos escritores legítimos a la vez.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from core.errors import PersistenceError

# Reentrante: una operación de repositorio puede ejecutar y confirmar en
# la misma llamada sin bloquearse consigo misma.
_DB_LOCK = threading.RLock()


class ConnectionManager:
    """Opens SQLite databases with the project's professional settings."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        directory = os.path.dirname(os.path.abspath(self.db_path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            # check_same_thread=False (v3.39.1): la MISMA conexión se usa
            # desde el hilo de la GUI y desde hilos de fondo; la
            # exclusión la da _DB_LOCK, no el hilo dueño.
            conn = sqlite3.connect(self.db_path, check_same_thread=False,
                                   timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            return conn
        except sqlite3.Error as exc:
            raise PersistenceError(
                message=f"No se pudo abrir la base de datos: {self.db_path}",
                code="ARQ-PER-002",
                context={"path": self.db_path, "detail": str(exc)},
                suggested_action="Verifique permisos de escritura en la carpeta del proyecto.",
            ) from exc

    @staticmethod
    def integrity_check(conn: sqlite3.Connection) -> str:
        with _DB_LOCK:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"


class Session:
    """Transaction-scoped access to one SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        # v3.39.1: el candado convierte el acceso multi-hilo en una cola
        # ordenada; antes de check_same_thread=False esto lanzaba
        # ProgrammingError al usar la conexión desde el hilo de fondo.
        with _DB_LOCK:
            try:
                return self.conn.execute(sql, params)
            except sqlite3.Error as exc:
                raise PersistenceError(
                    message=f"Error SQL: {exc}",
                    code="ARQ-PER-003",
                    context={"sql": sql[:200]},
                ) from exc

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self.execute(sql, params).fetchone()

    def commit(self) -> None:
        with _DB_LOCK:
            self.conn.commit()

    def rollback(self) -> None:
        with _DB_LOCK:
            self.conn.rollback()

    def close(self) -> None:
        # Si la ventana se cierra con una importación de fondo en marcha,
        # esperarla aquí es lo correcto (daemon o no, la transacción
        # termina antes de soltar el archivo).
        with _DB_LOCK:
            try:
                self.conn.close()
            except sqlite3.Error:  # pragma: no cover
                pass


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """All-or-nothing block: commit on success, rollback on exception."""
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def json_loads(value: Optional[str], default: Any = None) -> Any:
    import json
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


__all__ = ["ConnectionManager", "Session", "transaction", "json_dumps", "json_loads"]
