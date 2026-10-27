"""Event system (spec sections 49, 75).

Main event catalogue is fixed by the specification. Extra module events
may be registered by plugins at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from core.entities.base import utc_now


class EventType:
    """Main event catalogue (spec section 75)."""

    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_OPENED = "PROJECT_OPENED"
    OBJECT_CREATED = "OBJECT_CREATED"
    OBJECT_UPDATED = "OBJECT_UPDATED"
    OBJECT_DELETED = "OBJECT_DELETED"
    GEOMETRY_CHANGED = "GEOMETRY_CHANGED"
    SPACE_CHANGED = "SPACE_CHANGED"
    SYSTEM_CHANGED = "SYSTEM_CHANGED"
    DEVICE_MOVED = "DEVICE_MOVED"
    ROUTE_CHANGED = "ROUTE_CHANGED"
    RULE_CHANGED = "RULE_CHANGED"
    QUANTITY_CHANGED = "QUANTITY_CHANGED"
    PRICE_CHANGED = "PRICE_CHANGED"
    BUDGET_CHANGED = "BUDGET_CHANGED"
    CLASH_CREATED = "CLASH_CREATED"
    CLASH_RESOLVED = "CLASH_RESOLVED"
    DOCUMENT_CHANGED = "DOCUMENT_CHANGED"
    EXPORT_COMPLETED = "EXPORT_COMPLETED"

    ALL: tuple[str, ...] = (
        "PROJECT_CREATED", "PROJECT_OPENED", "OBJECT_CREATED", "OBJECT_UPDATED",
        "OBJECT_DELETED", "GEOMETRY_CHANGED", "SPACE_CHANGED", "SYSTEM_CHANGED",
        "DEVICE_MOVED", "ROUTE_CHANGED", "RULE_CHANGED", "QUANTITY_CHANGED",
        "PRICE_CHANGED", "BUDGET_CHANGED", "CLASH_CREATED", "CLASH_RESOLVED",
        "DOCUMENT_CHANGED", "EXPORT_COMPLETED",
    )


Handler = Callable[["Event"], None]


@dataclass
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=utc_now)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


class EventBus:
    """Synchronous in-process event bus.

    Handlers subscribed to the wildcard ``*`` receive every event.
    Handler failures never break the emitter: they are collected and
    returned so the caller can log them.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, list[Handler]] = {}
        self.history: list[Event] = []
        self.history_limit: int = 500

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event: Event) -> list[str]:
        """Dispatch an event; returns the list of handler error strings."""
        self.history.append(event)
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit:]
        errors: list[str] = []
        for handler in self._subscribers.get(event.type, []) + self._subscribers.get("*", []):
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 - resilience by design
                errors.append(f"handler '{getattr(handler, '__name__', repr(handler))}': {exc}")
        return errors

    def clear(self) -> None:
        self._subscribers.clear()
        self.history.clear()


__all__ = ["Event", "EventBus", "EventType"]
