import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("emo_ai.security.rbac")


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Resource(str, Enum):
    WORKSPACE = "workspace"
    WORKFLOW = "workflow"
    AGENT = "agent"
    PROJECT = "project"
    SETTINGS = "settings"
    SYSTEM = "system"
    USER = "user"


class Action(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    APPROVE = "approve"


class Scope(str, Enum):
    OWN = "own"
    TENANT = "tenant"
    GLOBAL = "global"


@dataclass(frozen=True)
class RBACDecision:
    allowed: bool
    reason: str = ""


@dataclass
class RoleDefinition:
    role: Role
    level: int
    description: str
    can_approve: bool = False
    can_deploy: bool = False


ROLE_DEFINITIONS: dict[str, RoleDefinition] = {
    "super_admin": RoleDefinition(role=Role.SUPER_ADMIN, level=40, description="Full system access", can_approve=True, can_deploy=True),
    "admin": RoleDefinition(role=Role.ADMIN, level=30, description="Tenant-wide administration", can_approve=True, can_deploy=True),
    "operator": RoleDefinition(role=Role.OPERATOR, level=20, description="Day-to-day operations within workspace", can_approve=True, can_deploy=False),
    "viewer": RoleDefinition(role=Role.VIEWER, level=10, description="Read-only access", can_approve=False, can_deploy=False),
}


@dataclass
class RBACEngine:
    role_hierarchy: dict[str, int] = field(default_factory=lambda: {
        "super_admin": 40,
        "admin": 30,
        "operator": 20,
        "viewer": 10,
    })

    def check(self, role_val: str, resource: Resource, action: Action, scope: Scope) -> RBACDecision:
        role_level = self.role_hierarchy.get(role_val, 0)
        if role_level >= 30:
            return RBACDecision(allowed=True, reason="Admin/SuperAdmin: full access")
        if role_level >= 20 and scope in (Scope.OWN, Scope.TENANT):
            return RBACDecision(allowed=True, reason=f"Operator: {scope.value} access")
        if role_level >= 10 and scope == Scope.OWN:
            return RBACDecision(allowed=True, reason="Viewer: own access only")
        return RBACDecision(allowed=False, reason=f"Insufficient role level ({role_level}) for {resource}:{action}:{scope}")


def get_rbac() -> RBACEngine:
    return RBACEngine()
