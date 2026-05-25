from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.db import db
from core.state import state

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def get_history():
    """Get message history for the active conversation."""
    conv_id = state.active_conversation_id
    if not conv_id:
        # Return empty if no active conversation
        return JSONResponse({"messages": []})

    # Try DB first
    messages = await db.get_messages(conv_id)
    if messages:
        return JSONResponse({"messages": messages})

    # Fallback to in-memory
    conv = state.conversations.get(conv_id, {})
    msgs = conv.get("messages", [])
    return JSONResponse({"messages": msgs})
