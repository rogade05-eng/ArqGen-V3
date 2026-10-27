"""ARQ GEN graphical UI (FASE 90, spec sections 90-93).

Layer discipline: UI → APPLICATION → DOMAIN → SERVICES → ENGINES →
PERSISTENCE. The window is a thin layer over the service facades;
all decisions live in ui.models (headless-testable).
"""

from ui import models  # noqa: F401

__all__ = ["models"]
