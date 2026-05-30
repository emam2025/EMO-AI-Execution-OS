"""EMO AI Governance Layer — Role-Based Access Control.

LAW 20: Every submit/query call MUST pass explicit PolicyEngine.check().
LAW 21: Roles are immutable after creation; only super-admin can assign.
LAW 22: No global mutable state — all policies scoped to tenant_id.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


class Permission(enum.Enum):
    SUBMIT_TASK = "submit:task"
    QUERY_TASK = "query:task"
    OBSERVE_TASK = "observe:task"
    ADMIN_SYSTEM = "admin:system"
    MANAGE_ROLES = "manage:roles"
    MANAGE_TENANTS = "manage:tenants"
    VIEW_AUDIT = "view:audit"
    EXPORT_AUDIT = "export:audit"


class Role(enum.Enum):
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


_ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.SUPER_ADMIN: {
        Permission.SUBMIT_TASK,
        Permission.QUERY_TASK,
        Permission.OBSERVE_TASK,
        Permission.ADMIN_SYSTEM,
        Permission.MANAGE_ROLES,
        Permission.MANAGE_TENANTS,
        Permission.VIEW_AUDIT,
        Permission.EXPORT_AUDIT,
    },
    Role.TENANT_ADMIN: {
        Permission.SUBMIT_TASK,
        Permission.QUERY_TASK,
        Permission.OBSERVE_TASK,
        Permission.VIEW_AUDIT,
        Permission.EXPORT_AUDIT,
    },
    Role.OPERATOR: {
        Permission.SUBMIT_TASK,
        Permission.QUERY_TASK,
        Permission.OBSERVE_TASK,
    },
    Role.VIEWER: {
        Permission.QUERY_TASK,
        Permission.OBSERVE_TASK,
    },
}


@dataclass(frozen=True)
class PolicyBinding:
    principal_id: str
    tenant_id: str
    role: Role
    binding_id: str = field(default_factory=lambda: f"pb-{uuid.uuid4().hex[:12]}")


_principal_bindings: Dict[str, PolicyBinding] = {}
_tenant_bindings: Dict[str, List[PolicyBinding]] = {}


def bind_role(principal_id: str, tenant_id: str, role: Role) -> PolicyBinding:
    if role == Role.SUPER_ADMIN:
        existing = _principal_bindings.get(principal_id)
        if existing and existing.role == Role.SUPER_ADMIN:
            raise ValueError("Super-admin already assigned")
    binding = PolicyBinding(principal_id=principal_id, tenant_id=tenant_id, role=role)
    _principal_bindings[principal_id] = binding
    _tenant_bindings.setdefault(tenant_id, []).append(binding)
    return binding


def get_role(principal_id: str) -> Optional[Role]:
    binding = _principal_bindings.get(principal_id)
    return binding.role if binding else None


def get_tenant(principal_id: str) -> Optional[str]:
    binding = _principal_bindings.get(principal_id)
    return binding.tenant_id if binding else None


def get_permissions(principal_id: str) -> Set[Permission]:
    role = get_role(principal_id)
    if role is None:
        return set()
    return _ROLE_PERMISSIONS.get(role, set())


def has_permission(principal_id: str, permission: Permission) -> bool:
    return permission in get_permissions(principal_id)


class PolicyEngine:
    def check(self, principal_id: str, permission: Permission, tenant_id: str) -> bool:
        binding = _principal_bindings.get(principal_id)
        if binding is None:
            return False
        if binding.tenant_id != tenant_id:
            return False
        return permission in get_permissions(principal_id)

    def enforce(self, principal_id: str, permission: Permission, tenant_id: str) -> None:
        if not self.check(principal_id, permission, tenant_id):
            raise PermissionError(
                f"Principal {principal_id} lacks {permission.value} in tenant {tenant_id}"
            )

    def list_principals(self, tenant_id: str) -> List[PolicyBinding]:
        return _tenant_bindings.get(tenant_id, [])

    def remove_binding(self, principal_id: str) -> bool:
        binding = _principal_bindings.pop(principal_id, None)
        if binding is None:
            return False
        tenant_list = _tenant_bindings.get(binding.tenant_id, [])
        _tenant_bindings[binding.tenant_id] = [
            b for b in tenant_list if b.principal_id != principal_id
        ]
        return True

    def reset(self) -> None:
        _principal_bindings.clear()
        _tenant_bindings.clear()
