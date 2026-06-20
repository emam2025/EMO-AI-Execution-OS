"""Integration Hub Router.

Per-workspace multi-channel integration configuration and webhook endpoints.
Every request verifies workspace access before returning data.

Ref: Phase P Batch 4 (P.5 — Integration Hub)
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.models.integration import (
    IntegrationChannel,
    IntegrationConfig,
    IntegrationStatus,
    MessageEnvelope,
)
from routers.workspace import _get_current_user_id, _verify_workspace_access, _verify_write_access

router = APIRouter(prefix="/api/workspaces", tags=["integrations"])

_integration_store: Dict[str, IntegrationConfig] = {}


def _integration_key(workspace_id: str, channel_type: IntegrationChannel) -> str:
    return f"{workspace_id}:{channel_type.value}"


class AddIntegrationRequest(BaseModel):
    channel_type: IntegrationChannel
    bot_token_env_var: str = ""
    webhook_url: str = ""


class WebhookPayload(BaseModel):
    external_message_id: str = ""
    sender_id: str = ""
    content: str


@router.get("/{workspace_id}/integrations", response_model=List[Dict[str, Any]])
def list_integrations(workspace_id: str, request: Request) -> List[Dict[str, Any]]:
    user_id = _get_current_user_id(request)
    _verify_workspace_access(user_id, workspace_id)
    integrations = [
        {
            "workspace_id": i.workspace_id,
            "channel_type": i.channel_type.value,
            "bot_token_env_var": i.bot_token_env_var,
            "webhook_url": i.webhook_url,
            "is_active": i.is_active,
            "status": i.status.value,
        }
        for i in _integration_store.values()
        if i.workspace_id == workspace_id
    ]
    return integrations


@router.post("/{workspace_id}/integrations", response_model=Dict[str, Any], status_code=201)
def add_integration(workspace_id: str, request: AddIntegrationRequest, req: Request) -> Dict[str, Any]:
    user_id = _get_current_user_id(req)
    _verify_write_access(user_id, workspace_id)
    config = IntegrationConfig(
        workspace_id=workspace_id,
        channel_type=request.channel_type,
        bot_token_env_var=request.bot_token_env_var,
        webhook_url=request.webhook_url,
    )
    key = _integration_key(workspace_id, request.channel_type)
    _integration_store[key] = config
    return {
        "workspace_id": config.workspace_id,
        "channel_type": config.channel_type.value,
        "bot_token_env_var": config.bot_token_env_var,
        "webhook_url": config.webhook_url,
        "is_active": config.is_active,
        "status": config.status.value,
    }


@router.post("/{workspace_id}/integrations/{channel_type}/webhook", response_model=Dict[str, Any])
def receive_webhook(workspace_id: str, channel_type: IntegrationChannel, payload: WebhookPayload, request: Request) -> Dict[str, Any]:
    user_id = _get_current_user_id(request)
    _verify_workspace_access(user_id, workspace_id)

    key = _integration_key(workspace_id, channel_type)
    if key not in _integration_store:
        raise HTTPException(status_code=404, detail="Integration not configured for this workspace")

    config = _integration_store[key]
    if not config.is_accessible():
        raise HTTPException(status_code=403, detail="Integration is not active or in error state")

    envelope = MessageEnvelope(
        channel_type=channel_type,
        external_message_id=payload.external_message_id,
        sender_id=payload.sender_id,
        content=payload.content,
        workspace_id=workspace_id,
    )
    return {
        "received": True,
        "channel_type": envelope.channel_type.value,
        "workspace_id": envelope.workspace_id,
        "sender_id": envelope.sender_id,
        "content_length": len(envelope.content),
    }


@router.delete("/{workspace_id}/integrations/{channel_type}", response_model=Dict[str, Any])
def remove_integration(workspace_id: str, channel_type: IntegrationChannel, request: Request) -> Dict[str, Any]:
    user_id = _get_current_user_id(request)
    _verify_write_access(user_id, workspace_id)

    key = _integration_key(workspace_id, channel_type)
    if key not in _integration_store:
        raise HTTPException(status_code=404, detail="Integration not configured for this workspace")

    removed = _integration_store.pop(key)
    return {"removed": True, "channel_type": removed.channel_type.value, "workspace_id": removed.workspace_id}
