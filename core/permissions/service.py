"""Permissions model (spec folder core/permissions).

Small but complete: users, roles, permission checks. The services consult
PermissionService before executing protected operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Set

from core.errors import PermissionDeniedError


class Permission(str, Enum):
    PROJECT_CREATE = "PROJECT_CREATE"
    PROJECT_OPEN = "PROJECT_OPEN"
    PROJECT_EDIT = "PROJECT_EDIT"
    PROJECT_DELETE = "PROJECT_DELETE"
    PRICE_EDIT = "PRICE_EDIT"
    BUDGET_EDIT = "BUDGET_EDIT"
    VERSION_RESTORE = "VERSION_RESTORE"
    BACKUP_RESTORE = "BACKUP_RESTORE"
    AUDIT_VIEW = "AUDIT_VIEW"
    EXPORT = "EXPORT"


@dataclass
class Role:
    name: str
    permissions: Set[Permission] = field(default_factory=set)

    def allows(self, permission: Permission) -> bool:
        return permission in self.permissions


ROLE_ARCHITECT = Role(
    "architect",
    {p for p in Permission},
)

ROLE_TECHNICIAN = Role(
    "technician",
    {
        Permission.PROJECT_CREATE, Permission.PROJECT_OPEN, Permission.PROJECT_EDIT,
        Permission.EXPORT, Permission.AUDIT_VIEW,
    },
)

ROLE_VIEWER = Role(
    "viewer",
    {Permission.PROJECT_OPEN, Permission.AUDIT_VIEW},
)


@dataclass
class User:
    name: str
    roles: Set[str] = field(default_factory=set)


class PermissionService:
    """Checks users against roles. Unknown roles are denied."""

    def __init__(self) -> None:
        self._roles: Dict[str, Role] = {
            r.name: r for r in (ROLE_ARCHITECT, ROLE_TECHNICIAN, ROLE_VIEWER)
        }

    def register_role(self, role: Role) -> None:
        self._roles[role.name] = role

    def check(self, user: User, permission: Permission) -> None:
        """Raise PermissionDeniedError if the user lacks the permission."""
        for role_name in user.roles:
            role = self._roles.get(role_name)
            if role and role.allows(permission):
                return
        raise PermissionDeniedError(user.name, permission.value)

    def has(self, user: User, permission: Permission) -> bool:
        try:
            self.check(user, permission)
            return True
        except PermissionDeniedError:
            return False


__all__ = [
    "Permission", "Role", "User", "PermissionService",
    "ROLE_ARCHITECT", "ROLE_TECHNICIAN", "ROLE_VIEWER",
]
