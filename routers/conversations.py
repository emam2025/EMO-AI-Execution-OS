import uuid
from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.runtime.data_providers import get_db, get_state
from middleware.auth import require_auth

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversation(BaseModel):
    name: str = "محادثة جديدة"
    project_id: str = ""
    session_id: str = ""


class UpdateConversation(BaseModel):
    name: str


@router.get("")
async def list_conversations(archived: bool = Query(False), project_id: str = "", session_id: str = "", user: dict = Depends(require_auth())):
    """List all conversations, optionally filtered by project or session."""
    convs = await get_db().get_conversations(archived=archived)
    if project_id:
        convs = [c for c in convs if c.get("project_id") == project_id]
    if session_id:
        convs = [c for c in convs if c.get("session_id") == session_id]
    active = get_state().active_conversation_id
    return JSONResponse({"conversations": convs, "active": active})


@router.post("")
async def create_conversation(req: CreateConversation, user: dict = Depends(require_auth())):
    """Create a new conversation."""
    conv_id = str(uuid.uuid4())
    await get_db().create_conversation(conv_id, name=req.name)
    if req.project_id:
        await get_db().update_conversation(conv_id, project_id=req.project_id)
    if req.session_id:
        await get_db().update_conversation(conv_id, session_id=req.session_id)
    get_state().conversations[conv_id] = {"messages": []}
    return JSONResponse({
        "id": conv_id,
        "name": req.name,
        "project_id": req.project_id,
        "session_id": req.session_id,
        "created_at": get_state().conversations[conv_id].get("created_at", ""),
    })


@router.post("/{conv_id}/activate")
async def activate_conversation(conv_id: str, user: dict = Depends(require_auth())):
    """Activate a conversation."""
    if conv_id not in get_state().conversations:
        get_state().conversations[conv_id] = {"messages": []}
    get_state().active_conversation_id = conv_id
    await get_db().activate_conversation(conv_id)
    return JSONResponse({"status": "activated", "conversation_id": conv_id})


@router.put("/{conv_id}")
async def update_conversation(conv_id: str, req: UpdateConversation, user: dict = Depends(require_auth())):
    """Rename a conversation."""
    await get_db().update_conversation_name(conv_id, req.name)
    if conv_id in get_state().conversations:
        get_state().conversations[conv_id]["name"] = req.name
    return JSONResponse({"status": "updated", "conversation_id": conv_id, "name": req.name})


@router.post("/{conv_id}/archive")
async def archive_conversation(conv_id: str, user: dict = Depends(require_auth())):
    """Archive a conversation."""
    await get_db().archive_conversation(conv_id)
    get_state().conversations.pop(conv_id, None)
    if get_state().active_conversation_id == conv_id:
        get_state().active_conversation_id = None
    return JSONResponse({"status": "archived", "conversation_id": conv_id})


@router.post("/{conv_id}/unarchive")
async def unarchive_conversation(conv_id: str, user: dict = Depends(require_auth())):
    """Unarchive a conversation."""
    await get_db().unarchive_conversation(conv_id)
    return JSONResponse({"status": "unarchived", "conversation_id": conv_id})


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str, user: dict = Depends(require_auth())):
    """Delete a conversation."""
    await get_db().delete_conversation(conv_id)
    get_state().conversations.pop(conv_id, None)
    if get_state().active_conversation_id == conv_id:
        get_state().active_conversation_id = None
    return JSONResponse({"status": "deleted", "conversation_id": conv_id})
