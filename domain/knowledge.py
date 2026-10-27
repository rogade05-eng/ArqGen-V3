"""Space DNA / Knowledge Engine (spec sections 14, 15).

Space types carry their technical DNA as versioned JSON data under
resources/knowledge — never hardcoded in Python.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SpaceDNA:
    """DNA of a space type (spec section 15)."""

    space_type: str
    name_es: str = ""
    minimum_area: Optional[float] = None
    preferred_area: Optional[float] = None
    minimum_width: Optional[float] = None
    minimum_length: Optional[float] = None
    height: Optional[float] = None
    occupancy: Optional[float] = None       # m2 per person
    privacy: int = 0                        # 0 public .. 5 very private
    daylight: bool = False
    ventilation: bool = False
    wet_zone: bool = False
    noise_level: Optional[int] = None       # 0..10
    accessibility: bool = False
    emergency_access: bool = False
    adjacency_requirements: List[Dict[str, Any]] = field(default_factory=list)
    requires_water: bool = False
    requires_drainage: bool = False
    requires_ventilation: bool = False
    functional_relationships: List[str] = field(default_factory=list)
    preferred_adjacencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpaceDNA":
        known = {f for f in cls.__dataclass_fields__ if f != "space_type"}
        # La clave "metadata" del JSON se conserva: se fusiona con las
        # claves desconocidas de primer nivel (que también van a
        # metadata) sin perder ninguna (v2.2.0, DNA hospitalario).
        json_metadata = data.get("metadata") or {}
        extra = {k: v for k, v in data.items()
                 if k not in known and k != "space_type"}
        base = {k: v for k, v in data.items()
                if k in known and k != "metadata"}
        dna = cls(space_type=data["space_type"], **base)
        merged = dict(json_metadata)
        merged.update(extra)
        dna.metadata = merged
        return dna

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            value = getattr(self, f)
            if value is not None and value != [] and value != {}:
                out[f] = value
        return out


class SpaceDNARegistry:
    """Loads and validates Space DNA data files (JSON)."""

    def __init__(self) -> None:
        self._dna: Dict[str, SpaceDNA] = {}
        self.version: str = "1.0"
        self.source: str = ""

    def load_file(self, path: str) -> int:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return self.load_dict(data)

    def load_dict(self, data: Dict[str, Any]) -> int:
        if "space_types" not in data or not isinstance(data["space_types"], list):
            from core.errors import DomainError
            raise DomainError(
                message="El archivo Space DNA debe contener la lista 'space_types'",
                code="ARQ-DOM-009",
            )
        self.version = str(data.get("version", "1.0"))
        self.source = str(data.get("source", ""))
        count = 0
        for item in data["space_types"]:
            if "space_type" not in item:
                from core.errors import DomainError
                raise DomainError(
                    message="Entrada Space DNA sin clave 'space_type'",
                    code="ARQ-DOM-009",
                    context={"item": item},
                )
            self._dna[item["space_type"]] = SpaceDNA.from_dict(item)
            count += 1
        return count

    def get(self, space_type: str) -> Optional[SpaceDNA]:
        return self._dna.get(space_type)

    def require(self, space_type: str) -> SpaceDNA:
        dna = self._dna.get(space_type)
        if dna is None:
            from core.errors import DomainError
            raise DomainError(
                message=f"Tipo de espacio sin DNA registrado: {space_type}",
                code="ARQ-DOM-011",
                context={"space_type": space_type, "available": sorted(self._dna)},
                suggested_action="Registre el tipo en resources/knowledge/space_dna.json o use un tipo existente.",
            )
        return dna

    def types(self) -> List[str]:
        return sorted(self._dna.keys())

    def __len__(self) -> int:
        return len(self._dna)


__all__ = ["SpaceDNA", "SpaceDNARegistry"]
