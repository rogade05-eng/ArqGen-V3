"""Audit trail (spec section 71).

Every significant change generates an AuditEvent with user, timestamp,
object, old_value, new_value, command, reason and result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from core.entities.base import new_uuid, utc_now


@dataclass
class AuditEvent:
    user: str
    timestamp: datetime
    object_id: str
    object_type: str
    command: str
    old_value: Optional[Dict[str, Any]]
    new_value: Optional[Dict[str, Any]]
    reason: str = ""
    result: str = "OK"
    id: str = field(default_factory=new_uuid)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user": self.user,
            "timestamp": self.timestamp.isoformat(),
            "object_id": self.object_id,
            "object_type": self.object_type,
            "command": self.command,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "result": self.result,
        }


def make_audit_event(user: str, object_id: str, object_type: str, command: str,
                     old_value: Optional[Dict[str, Any]], new_value: Optional[Dict[str, Any]],
                     reason: str = "", result: str = "OK") -> AuditEvent:
    return AuditEvent(
        user=user,
        timestamp=utc_now(),
        object_id=object_id,
        object_type=object_type,
        command=command,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        result=result,
    )


__all__ = ["AuditEvent", "make_audit_event"]
