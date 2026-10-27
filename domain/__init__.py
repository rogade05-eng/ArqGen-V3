"""ARQ GEN domain layer: the unique semantic model."""

from domain.detalles import (
    CapaDetalle,
    DetalleConstructivo,
    DetallesRegistry,
)
from domain.knowledge import SpaceDNA, SpaceDNARegistry
from domain.neufert import NeufertRegistry, StairRule, get_registry
from domain.model import (
    Building,
    Door,
    Level,
    Opening,
    Project,
    RELATIONSHIP_KINDS,
    Site,
    Space,
    SpaceRelationship,
    Wall,
    Window,
    Zone,
)

__all__ = [
    "Project", "Site", "Building", "Level", "Zone", "Space",
    "SpaceRelationship", "RELATIONSHIP_KINDS", "Wall", "Opening",
    "Door", "Window", "SpaceDNA", "SpaceDNARegistry",
    "NeufertRegistry", "StairRule", "get_registry",
    "CapaDetalle", "DetalleConstructivo", "DetallesRegistry",
]
