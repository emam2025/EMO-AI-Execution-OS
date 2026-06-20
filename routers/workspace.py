"""Workspace API Router.

Multi-tenant workspace endpoints with strict isolation checks.
Every request verifies workspace_id ↔ user_id before returning data.

Ref: Phase P Batch 3 (P.3 — User Workspace Layer)
Ref: Canon LAW 10, LAW 13
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.models.workspace import (
    User,
    Workspace,
    WorkspaceMember,
    UserRole,
    WorkspaceStatus,
    Tenant,
    TenantStatus,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

_tenant_store: Dict[str, Tenant] = {}
_user_store: Dict[str, User] = {}
_workspace_store: Dict[str, Workspace] = {}
_member_store: Dict[str, WorkspaceMember] = {}


def _get_current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        user_id = request.headers.get("X-User-Id", "u-default")
    return user_id


def _verify_workspace_access(user_id: str, workspace_id: str) -> Workspace:
    if workspace_id not in _workspace_store:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace = _workspace_store[workspace_id]
    if not workspace.is_accessible():
        raise HTTPException(status_code=403, detail="Workspace is not accessible")
    member_key = f"{user_id}:{workspace_id}"
    if member_key not in _member_store:
        raise HTTPException(status_code=403, detail="Access denied: not a workspace member")
    user = _user_store.get(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Access denied: user inactive")
    if not user.belongs_to_tenant(workspace.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied: tenant mismatch")
    return workspace


def _verify_write_access(user_id: str, workspace_id: str) -> WorkspaceMember:
    workspace = _verify_workspace_access(user_id, workspace_id)
    member_key = f"{user_id}:{workspace_id}"
    member = _member_store[member_key]
    if not member.has_write_access():
        raise HTTPException(status_code=403, detail="Access denied: insufficient role")
    return member


class UserRequest(BaseModel):
    email: str
    display_name: str
    tenant_id: str = "t-default"


class WorkspaceRequest(BaseModel):
    name: str
    description: str = ""
    tenant_id: str = "t-default"


class AddMemberRequest(BaseModel):
    user_id: str
    role: UserRole = UserRole.VIEWER


@router.post("/users", response_model=Dict[str, Any], status_code=201)
def create_user(request: UserRequest) -> Dict[str, Any]:
    user = User(
        tenant_id=request.tenant_id,
        email=request.email,
        display_name=request.display_name,
    )
    _user_store[user.id] = user
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "tenant_id": user.tenant_id}


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_workspace(request: WorkspaceRequest) -> Dict[str, Any]:
    workspace = Workspace(tenant_id=request.tenant_id, name=request.name, description=request.description)
    _workspace_store[workspace.id] = workspace
    return {"id": workspace.id, "name": workspace.name, "tenant_id": workspace.tenant_id, "status": workspace.status.value}


@router.get("/{workspace_id}", response_model=Dict[str, Any])
def get_workspace(workspace_id: str, request: Request) -> Dict[str, Any]:
    user_id = _get_current_user_id(request)
    workspace = _verify_workspace_access(user_id, workspace_id)
    return {"id": workspace.id, "name": workspace.name, "tenant_id": workspace.tenant_id, "status": workspace.status.value}


@router.post("/{workspace_id}/members", response_model=Dict[str, Any], status_code=201)
def add_member(workspace_id: str, request: AddMemberRequest, req: Request) -> Dict[str, Any]:
    user_id = _get_current_user_id(req)
    _verify_write_access(user_id, workspace_id)

    if request.user_id not in _user_store:
        raise HTTPException(status_code=404, detail="User not found")
    target_user = _user_store[request.user_id]
    workspace = _workspace_store[workspace_id]
    if not target_user.belongs_to_tenant(workspace.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied: user not in same tenant")

    member = WorkspaceMember(user_id=request.user_id, workspace_id=workspace_id, role=request.role)
    member_key = f"{request.user_id}:{workspace_id}"
    _member_store[member_key] = member
    return {"user_id": member.user_id, "workspace_id": member.workspace_id, "role": member.role.value}


@router.get("/{workspace_id}/members", response_model=List[Dict[str, Any]])
def list_members(workspace_id: str, request: Request) -> List[Dict[str, Any]]:
    user_id = _get_current_user_id(request)
    _verify_workspace_access(user_id, workspace_id)
    members = [
        {"user_id": m.user_id, "workspace_id": m.workspace_id, "role": m.role.value}
        for m in _member_store.values()
        if m.workspace_id == workspace_id
    ]
    return members
