import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("emo_ai.security.identity")


class Role(Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: Role
    tenant_id: str = "default"
    source: str = "jwt"
    metadata: dict[str, Any] = field(default_factory=dict)


class IdentityBuilder:
    def from_jwt(self, payload: dict[str, Any], ip_address: str = "") -> Identity:
        role_str = payload.get("role", "viewer")
        try:
            role = Role(role_str)
        except ValueError:
            role = Role.VIEWER
        return Identity(
            user_id=payload.get("user_id", "unknown"),
            role=role,
            tenant_id=payload.get("tenant_id", "default"),
            source="jwt",
        )

    def migration_bypass(self) -> Identity:
        return Identity(
            user_id="migration",
            role=Role.SUPER_ADMIN,
            tenant_id="default",
            source="migration",
        )


def get_identity_builder() -> IdentityBuilder:
    return IdentityBuilder()
