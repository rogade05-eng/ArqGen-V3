"""Application lifecycle: logging setup + operation logger (spec section 84).

File logs: logs/app/arqgen.log (DEBUG, rotating), logs/app/errors.log
(ERROR+). Console: INFO, Spanish format. Heavy operations record
start/end/duration/objects/result via OperationLogger.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from contextlib import contextmanager
from typing import Optional

from app.paths import ensure_dir

_FORMAT_FILE = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FORMAT_CONSOLE = "%(levelname)-8s %(message)s"

_configured = False


def setup_logging(log_dir: str, level: str = "INFO", console: bool = True) -> None:
    """Idempotent logging configuration."""
    global _configured
    app_dir = ensure_dir(os.path.join(log_dir, "app"))
    build_dir = ensure_dir(os.path.join(log_dir, "build"))
    tests_dir = ensure_dir(os.path.join(log_dir, "tests"))
    setup_dir = ensure_dir(os.path.join(log_dir, "setup"))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(app_dir, "arqgen.log"), maxBytes=5_000_000, backupCount=5,
        encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FORMAT_FILE))
    root.addHandler(file_handler)

    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(app_dir, "errors.log"), maxBytes=2_000_000, backupCount=5,
        encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(_FORMAT_FILE))
    root.addHandler(error_handler)

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        console_handler.setFormatter(logging.Formatter(_FORMAT_CONSOLE))
        root.addHandler(console_handler)

    logging.getLogger(__name__).debug(
        "Logging inicializado en %s (setup=%s build=%s tests=%s)",
        app_dir, setup_dir, build_dir, tests_dir)
    _configured = True


def is_configured() -> bool:
    return _configured


@contextmanager
def operation_logger(logger: logging.Logger, operation: str, **context):
    """Records start/end/duration/result of heavy operations (spec 84)."""
    started = time.perf_counter()
    logger.info("INICIO %s %s", operation, context or "")
    outcome = {"objects": 0}
    try:
        yield outcome
        duration = (time.perf_counter() - started) * 1000.0
        logger.info("FIN %s duración=%.1fms objetos=%s", operation, duration, outcome["objects"])
    except Exception as exc:
        duration = (time.perf_counter() - started) * 1000.0
        logger.error("ERROR %s tras %.1fms: %s", operation, duration, exc)
        raise


class OperationTimer:
    """Same as operation_logger but usable without context manager nesting."""

    def __init__(self, logger: logging.Logger, operation: str) -> None:
        self.logger = logger
        self.operation = operation
        self.started = time.perf_counter()

    def stop(self, objects: int = 0) -> float:
        duration = (time.perf_counter() - self.started) * 1000.0
        self.logger.info("FIN %s duración=%.1fms objetos=%d", self.operation, duration, objects)
        return duration


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = ["setup_logging", "operation_logger", "OperationTimer", "get_logger", "is_configured"]
