import uuid
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.db import db
from core.state import state

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversation(BaseModel):
    name: str = "محادثة جديدة"
    project_id: str = ""
    session_id: str = ""


class UpdateConversation(BaseModel):
    name: str


@router.get("")
async def list_conversations(archived: bool = Query(False), project_id: str = "", session_id: str = ""):
    """List all conversations, optionally filtered by project or session."""
    convs = await db.get_conversations(archived=archived)
    if project_id:
        convs = [c for c in convs if c.get("project_id") == project_id]
    if session_id:
        convs = [c for c in convs if c.get("session_id") == session_id]
    active = state.active_conversation_id
    return JSONResponse({"conversations": convs, "active": active})


@router.post("")
async def create_conversation(req: CreateConversation):
    """Create a new conversation."""
    conv_id = str(uuid.uuid4())
    await db.create_conversation(conv_id, name=req.name)
    if req.project_id:
        await db.update_conversation(conv_id, project_id=req.project_id)
    if req.session_id:
        await db.update_conversation(conv_id, session_id=req.session_id)
    state.conversations[conv_id] = {"messages": []}
    return JSONResponse({
        "id": conv_id,
        "name": req.name,
        "project_id": req.project_id,
        "session_id": req.session_id,
        "created_at": state.conversations[conv_id].get("created_at", ""),
    })


@router.post("/{conv_id}/activate")
async def activate_conversation(conv_id: str):
    """Activate a conversation."""
    if conv_id not in state.conversations:
        state.conversations[conv_id] = {"messages": []}
    state.active_conversation_id = conv_id
    await db.activate_conversation(conv_id)
    return JSONResponse({"status": "activated", "conversation_id": conv_id})


@router.put("/{conv_id}")
async def update_conversation(conv_id: str, req: UpdateConversation):
    """Rename a conversation."""
    await db.update_conversation_name(conv_id, req.name)
    if conv_id in state.conversations:
        state.conversations[conv_id]["name"] = req.name
    return JSONResponse({"status": "updated", "conversation_id": conv_id, "name": req.name})


@router.post("/{conv_id}/archive")
async def archive_conversation(conv_id: str):
    """Archive a conversation."""
    await db.archive_conversation(conv_id)
    state.conversations.pop(conv_id, None)
    if state.active_conversation_id == conv_id:
        state.active_conversation_id = None
    return JSONResponse({"status": "archived", "conversation_id": conv_id})


@router.post("/{conv_id}/unarchive")
async def unarchive_conversation(conv_id: str):
    """Unarchive a conversation."""
    await db.unarchive_conversation(conv_id)
    return JSONResponse({"status": "unarchived", "conversation_id": conv_id})


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str):
    """Delete a conversation."""
    await db.delete_conversation(conv_id)
    state.conversations.pop(conv_id, None)
    if state.active_conversation_id == conv_id:
        state.active_conversation_id = None
    return JSONResponse({"status": "deleted", "conversation_id": conv_id})
