"""Autoguardado de ARQ GEN (mejora UX v3.0.0).

«Apenas se produce un cambio, se guarda»: este servicio observa el bus
de eventos del proyecto y marca el proyecto como PENDIENTE en cuanto
pasa cualquier cosa (crear, editar, eliminar, calcular…). La ventana
principal, con su bucle `after`, consulta `due()` y ejecuta el volcado
a SQLite (ctx.commit(), el mismo mecanismo de Ctrl+S) pasado el retardo
de calma (1,2 s): escribe poco y nunca a mitad de una ráfaga de comandos.

Diseño probado headless:
- NO emite eventos por su cuenta → no puede provocar bucles.
- `flush()` es idempotente: si no hay nada pendiente no toca nada.
- `enabled=False` (preferencia del usuario) apaga el flujo sin romper
  el indicador de la barra de estado.
- El reloj se inyecta (`clock`) para pruebas deterministas sin sleep.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

DEFAULT_DELAY_MS = 1200


class AutoSaveService:
    """Buffer de pendientes + volcado por calma al almacén del proyecto."""

    def __init__(self, ctx: Any, enabled: bool = True,
                 delay_ms: int = DEFAULT_DELAY_MS,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self.ctx = ctx
        self.enabled = bool(enabled)
        self.delay_ms = max(150, int(delay_ms))
        self._clock = clock or time.monotonic
        self._pending_since: Optional[float] = None
        self.last_saved: Optional[str] = ""   # HH:MM:SS del último volcado
        self.save_count = 0
        self.last_error: str = ""

    # -- entrada ---------------------------------------------------------------
    def on_event(self, event: Any = None) -> bool:
        """El bus notifica un cambio: marca pendiente.

        Devuelve True si conviene (re)programar el volcado.
        Un evento con marca `_arqgen_autosave` (p. ej. emitido por el
        propio guardado) se ignora para evitar retroalimentación.
        """
        if not self.enabled:
            return False
        payload = getattr(event, "payload", None)
        if isinstance(payload, dict) and payload.get("_arqgen_autosave"):
            return False
        if self._pending_since is None:
            self._pending_since = self._clock()
        return True

    # -- programación ------------------------------------------------------------
    def due(self, now: Optional[float] = None) -> bool:
        """True cuando ya transcurrió el retardo de calma."""
        if not self.enabled or self._pending_since is None:
            return False
        current = self._clock() if now is None else now
        return (current - self._pending_since) * 1000.0 >= self.delay_ms

    def ms_until_due(self) -> int:
        if self._pending_since is None:
            return 0
        remaining = self.delay_ms - (self._clock() - self._pending_since) * 1000.0
        return max(0, int(remaining))

    def cancel(self) -> None:
        """Descarta el pendiente (p. ej. el usuario guardó a mano)."""
        self._pending_since = None

    # -- volcado -------------------------------------------------------------------
    def flush(self) -> bool:
        """Ejecuta el commit si hay pendientes. Devuelve True si guardó."""
        if not self.enabled or not self.due():
            return False
        try:
            self.ctx.commit()
        except Exception as exc:  # noqa: BLE001 - el fallo no debe tumbar la UI
            self.last_error = str(exc)
            self._pending_since = None
            return False
        self._pending_since = None
        self.save_count += 1
        self.last_saved = time.strftime("%H:%M:%S")
        self.last_error = ""
        return True

    # -- estado para la barra -----------------------------------------------------
    def status_text(self) -> str:
        """Texto del indicador de la barra de estado."""
        if not self.enabled:
            return "Autoguardado en pausa"
        if self._pending_since is not None:
            return "Guardando…"
        if self.last_saved:
            return f"Autoguardado {self.last_saved}"
        return "Autoguardado activo"

    def stats(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "pending": self._pending_since
                is not None, "save_count": self.save_count,
                "last_saved": self.last_saved,
                "last_error": self.last_error}


__all__ = ["AutoSaveService", "DEFAULT_DELAY_MS"]
