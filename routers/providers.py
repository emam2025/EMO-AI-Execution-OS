"""Provider Marketplace Router.

Per-workspace provider configuration and usage tracking endpoints.
Every request verifies workspace access before returning data.

Ref: Phase P Batch 3 (P.4 — Provider Marketplace)
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from core.gateway.models import ProviderType
from core.models.provider_marketplace import (
    ProviderAccessDecision,
    ProviderUsage,
    WorkspaceProviderConfig,
)
from routers.workspace import _get_current_user_id, _verify_workspace_access, _verify_write_access
from middleware.auth import require_auth

router = APIRouter(prefix="/api/workspaces", tags=["providers"])

_provider_config_store: Dict[str, WorkspaceProviderConfig] = {}
_provider_usage_store: Dict[str, ProviderUsage] = {}


def _config_key(workspace_id: str, provider_type: ProviderType) -> str:
    return f"{workspace_id}:{provider_type.value}"


def _get_or_default_usage(workspace_id: str, provider_type: ProviderType) -> ProviderUsage:
    key = _config_key(workspace_id, provider_type)
    if key in _provider_usage_store:
        return _provider_usage_store[key]
    usage = ProviderUsage(workspace_id=workspace_id, provider_type=provider_type)
    _provider_usage_store[key] = usage
    return usage


class AddProviderRequest(BaseModel):
    provider_type: ProviderType
    api_key_env_var: str = ""
    quota_limit: int = 10000
    cost_limit: float = 100.0


@router.get("/{workspace_id}/providers", response_model=List[Dict[str, Any]])
def list_providers(workspace_id: str, request: Request, user: dict = Depends(require_auth())) -> List[Dict[str, Any]]:
    user_id = _get_current_user_id(request)
    _verify_workspace_access(user_id, workspace_id)
    providers = [
        {
            "workspace_id": p.workspace_id,
            "provider_type": p.provider_type.value,
            "api_key_env_var": p.api_key_env_var,
            "quota_limit": p.quota_limit,
            "cost_limit": p.cost_limit,
            "is_active": p.is_active,
        }
        for p in _provider_config_store.values()
        if p.workspace_id == workspace_id
    ]
    return providers


@router.post("/{workspace_id}/providers", response_model=Dict[str, Any], status_code=201)
def add_provider(workspace_id: str, request: AddProviderRequest, req: Request, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    user_id = _get_current_user_id(req)
    _verify_write_access(user_id, workspace_id)
    config = WorkspaceProviderConfig(
        workspace_id=workspace_id,
        provider_type=request.provider_type,
        api_key_env_var=request.api_key_env_var,
        quota_limit=request.quota_limit,
        cost_limit=request.cost_limit,
    )
    key = _config_key(workspace_id, request.provider_type)
    _provider_config_store[key] = config
    return {
        "workspace_id": config.workspace_id,
        "provider_type": config.provider_type.value,
        "quota_limit": config.quota_limit,
        "cost_limit": config.cost_limit,
        "is_active": config.is_active,
    }


@router.get("/{workspace_id}/providers/{provider_type}/usage", response_model=Dict[str, Any])
def get_provider_usage(workspace_id: str, provider_type: ProviderType, request: Request, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    user_id = _get_current_user_id(request)
    _verify_workspace_access(user_id, workspace_id)

    key = _config_key(workspace_id, provider_type)
    if key not in _provider_config_store:
        raise HTTPException(status_code=404, detail="Provider not configured for this workspace")

    config = _provider_config_store[key]
    usage = _get_or_default_usage(workspace_id, provider_type)

    if not config.is_accessible():
        decision = ProviderAccessDecision.DENIED_INACTIVE
    elif usage.is_over_quota(config.quota_limit):
        decision = ProviderAccessDecision.DENIED_QUOTA_EXCEEDED
    else:
        decision = ProviderAccessDecision.ALLOWED

    return {
        "workspace_id": usage.workspace_id,
        "provider_type": usage.provider_type.value,
        "requests_used": usage.requests_used,
        "tokens_used": usage.tokens_used,
        "cost_incurred": usage.cost_incurred,
        "quota_limit": config.quota_limit,
        "cost_limit": config.cost_limit,
        "remaining_requests": usage.remaining_requests(config.quota_limit),
        "remaining_cost": usage.remaining_cost(config.cost_limit),
        "access_decision": decision.value,
    }


@router.delete("/{workspace_id}/providers/{provider_type}", response_model=Dict[str, Any])
def remove_provider(workspace_id: str, provider_type: ProviderType, request: Request, user: dict = Depends(require_auth())) -> Dict[str, Any]:
    user_id = _get_current_user_id(request)
    _verify_write_access(user_id, workspace_id)

    key = _config_key(workspace_id, provider_type)
    if key not in _provider_config_store:
        raise HTTPException(status_code=404, detail="Provider not configured for this workspace")

    removed = _provider_config_store.pop(key)
    _provider_usage_store.pop(key, None)
    return {"removed": True, "provider_type": removed.provider_type.value, "workspace_id": removed.workspace_id}
