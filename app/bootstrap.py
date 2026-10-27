"""Application bootstrap: wires the container, loads plugins (spec 88-89)."""

from __future__ import annotations

import os
from typing import Any, Tuple

from app.lifecycle import get_logger
from app.paths import PROJECT_ROOT
from plugins.plugin_api import PluginLoader
from services.context import ApplicationContext

logger = get_logger("arqgen.bootstrap")


def bootstrap(args: Any = None) -> Tuple[ApplicationContext, PluginLoader]:
    """Create the ApplicationContext and load all plugins."""
    log_dir = getattr(args, "log_dir", None) or os.path.join(os.getcwd(), "logs")
    backup_dir = getattr(args, "backup_dir", None) or os.path.join(os.getcwd(), "backups")
    application = ApplicationContext(log_dir=log_dir, backup_dir=backup_dir)

    # External plugins live in plugins/external (the plugins/ root is package code).
    external_dir = os.path.join(PROJECT_ROOT, "plugins", "external")
    loader = PluginLoader(application, external_dir=external_dir)
    loader.load_all()
    for entry in loader.loaded:
        if entry.error:
            logger.warning("Plugin con error: %s → %s", entry.source, entry.error)
        else:
            logger.debug("Plugin cargado: %s (%s)", entry.plugin.plugin_id, entry.source)
    return application, loader


__all__ = ["bootstrap"]
