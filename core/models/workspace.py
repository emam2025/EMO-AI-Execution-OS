"""Workspace Models.

Pure models for Multi-tenancy and Workspace Isolation.
Frozen dataclasses only — stdlib only.

Ref: Phase P Batch 3 (P.3 — User Workspace Layer)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class UserRole(Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class WorkspaceStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class TenantStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"


@dataclass(frozen=True)
class Tenant:
    id: str = field(default_factory=lambda: f"t-{uuid.uuid4().hex[:12]}")
    name: str = ""
    status: TenantStatus = TenantStatus.ACTIVE
    max_workspaces: int = 10
    max_users_per_workspace: int = 25
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE


@dataclass(frozen=True)
class User:
    id: str = field(default_factory=lambda: f"u-{uuid.uuid4().hex[:12]}")
    tenant_id: str = ""
    email: str = ""
    display_name: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def belongs_to_tenant(self, tenant_id: str) -> bool:
        return self.tenant_id == tenant_id


@dataclass(frozen=True)
class WorkspaceMember:
    user_id: str = ""
    workspace_id: str = ""
    role: UserRole = UserRole.VIEWER
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def has_write_access(self) -> bool:
        return self.role in (UserRole.OWNER, UserRole.ADMIN, UserRole.EDITOR)

    def has_admin_access(self) -> bool:
        return self.role in (UserRole.OWNER, UserRole.ADMIN)


@dataclass(frozen=True)
class Workspace:
    id: str = field(default_factory=lambda: f"ws-{uuid.uuid4().hex[:12]}")
    tenant_id: str = ""
    name: str = ""
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_accessible(self) -> bool:
        return self.status == WorkspaceStatus.ACTIVE

    def belongs_to_tenant(self, tenant_id: str) -> bool:
        return self.tenant_id == tenant_id
