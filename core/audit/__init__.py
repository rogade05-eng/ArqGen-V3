"""Core audit package."""

from core.audit.models import AuditEvent, make_audit_event

__all__ = ["AuditEvent", "make_audit_event"]
