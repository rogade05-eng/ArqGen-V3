"""Discipline navigation registry (spec section 91).

Las trece disciplinas del explorador de proyecto. Todas operan sobre
el MISMO proyecto abierto (spec 91: "todas utilizarán el mismo
proyecto"); las disciplinas de seguridad filtran las redes por
`system` sobre el modelo genérico de instalaciones (§24-25).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DisciplineSpec:
    """Una disciplina del explorador (§91)."""

    key: str                    # clave estable interna
    label: str                  # etiqueta visible (nombres del §91)
    systems: tuple[str, ...] = ()   # filtro por sistema de red (seguridad)
    spatial: bool = False       # dibujable en el canvas


DISCIPLINES: tuple[DisciplineSpec, ...] = (
    DisciplineSpec("ARCHITECTURE", "Arquitectura", spatial=True),
    DisciplineSpec("STRUCTURE", "Estructura", spatial=True),
    DisciplineSpec("INSTALLATIONS", "Instalaciones", spatial=True),
    DisciplineSpec("CCTV", "CCTV", ("CCTV",), spatial=True),
    DisciplineSpec("FIRE", "Incendio", ("FIRE_ALARM",), spatial=True),
    DisciplineSpec("INTRUSION", "Intrusión", ("INTRUSION",), spatial=True),
    DisciplineSpec("ACCESS", "Acceso", ("ACCESS_CONTROL",), spatial=True),
    DisciplineSpec("PERIMETER", "Perímetro", ("PERIMETER",), spatial=True),
    DisciplineSpec("QTO", "Cantidades"),
    DisciplineSpec("BUDGET", "Presupuesto"),
    DisciplineSpec("BIM", "BIM"),
    DisciplineSpec("COORDINATION", "Coordinación"),
    DisciplineSpec("DOCUMENTATION", "Documentación"),
)

DISCIPLINE_KEYS: tuple[str, ...] = tuple(d.key for d in DISCIPLINES)

# Sistemas de red que pertenecen a disciplinas de seguridad (§37-49).
SECURITY_SYSTEMS: frozenset[str] = frozenset(
    system for d in DISCIPLINES for system in d.systems)

DISCIPLINE_BY_KEY: dict[str, DisciplineSpec] = {d.key: d for d in DISCIPLINES}


def discipline_label(key: str) -> str:
    spec = DISCIPLINE_BY_KEY.get(key)
    return spec.label if spec else key


__all__ = [
    "DisciplineSpec", "DISCIPLINES", "DISCIPLINE_KEYS",
    "DISCIPLINE_BY_KEY", "SECURITY_SYSTEMS", "discipline_label",
]
