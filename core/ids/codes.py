"""Identification: persistent UUID + human readable codes (spec section 6).

Example:
    ID:    550e8400-e29b-41d4-a716-446655440000
    Code:  ARQ-WALL-001
    Type:  WALL
    Discipline: ARCHITECTURE
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from core.errors import DomainError

DISCIPLINE_PREFIX = {
    "ARCHITECTURE": "ARQ",
    "STRUCTURE": "STR",
    "INSTALLATIONS": "MEP",
    "SECURITY": "SEC",
    "QTO": "QTO",
    "BUDGET": "BUD",
    "GENERAL": "GEN",
    "DOCUMENTATION": "DOC",
}

_CODE_RE = re.compile(r"^(?P<disc>[A-Z]{2,4})-(?P<etype>[A-Z_]+)-(?P<seq>\d{3,})$")


def parse_code(code: str) -> Optional[Dict[str, str]]:
    """Parse a human code like ARQ-WALL-001 into its parts."""
    match = _CODE_RE.match(code or "")
    if not match:
        return None
    return match.groupdict()


class CodeAllocator:
    """Allocates sequential human codes per (discipline, entity type).

    The allocator is seeded from the codes already present in the project,
    so it is stable across sessions without extra persistence.
    """

    def __init__(self, existing_codes: Optional[list[str]] = None) -> None:
        self._counters: Dict[tuple[str, str], int] = {}
        for code in existing_codes or []:
            parsed = parse_code(code)
            if parsed:
                key = (parsed["disc"], parsed["etype"])
                seq = int(parsed["seq"])
                if seq > self._counters.get(key, 0):
                    self._counters[key] = seq

    def next_code(self, discipline: str, entity_type: str) -> str:
        prefix = DISCIPLINE_PREFIX.get(discipline)
        if not prefix:
            raise DomainError(
                message=f"Disciplina desconocida: {discipline}",
                code="ARQ-DOM-010",
                context={"discipline": discipline},
                suggested_action="Use una disciplina registrada: " + ", ".join(sorted(DISCIPLINE_PREFIX)),
            )
        key = (prefix, entity_type.upper())
        self._counters[key] = self._counters.get(key, 0) + 1
        return f"{prefix}-{entity_type.upper()}-{self._counters[key]:03d}"


__all__ = ["CodeAllocator", "DISCIPLINE_PREFIX", "parse_code"]
