"""Base entity definition (spec sections 5.1, 6, 7, 93).

Every object in ARQ GEN inherits conceptually from Entity:
    id, type, project_id, created_at, updated_at, revision, status, metadata.
List indices are never used as identifiers (spec section 6).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class EntityStatus(str, Enum):
    """Entity lifecycle states (spec section 93)."""

    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class CalculationStatus(str, Enum):
    """Calculation states (spec section 93)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def new_uuid() -> str:
    """Generate a persistent UUID/GUID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class Entity:
    """Semantic base entity of the unique project model."""

    id: str = field(default_factory=new_uuid)
    type: str = "ENTITY"
    project_id: str = ""
    code: str = ""
    discipline: str = "GENERAL"
    level_id: Optional[str] = None
    status: EntityStatus = EntityStatus.DRAFT
    revision: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    ENTITY_TYPE = "ENTITY"

    def __post_init__(self) -> None:
        if not self.type or self.type == "ENTITY":
            self.type = self.ENTITY_TYPE

    def touch(self) -> None:
        """Bump revision and updated_at on every modification."""
        self.revision += 1
        self.updated_at = utc_now()


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse an ISO datetime coming from SQLite/JSON; None-safe."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


__all__ = [
    "Entity",
    "EntityStatus",
    "CalculationStatus",
    "new_uuid",
    "utc_now",
    "parse_datetime",
]
