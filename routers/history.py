from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from core.runtime.data_providers import get_db, get_state
from middleware.auth import require_auth

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def get_history(user: dict = Depends(require_auth())):
    """Get message history for the active conversation."""
    conv_id = get_state().active_conversation_id
    if not conv_id:
        # Return empty if no active conversation
        return JSONResponse({"messages": []})

    # Try DB first
    messages = await get_db().get_messages(conv_id)
    if messages:
        return JSONResponse({"messages": messages})

    # Fallback to in-memory
    conv = get_state().conversations.get(conv_id, {})
    msgs = conv.get("messages", [])
    return JSONResponse({"messages": msgs})
