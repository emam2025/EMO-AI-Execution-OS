from fastapi import APIRouter, Depends
from middleware.auth import require_auth

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/")
async def list_tools(user: dict = Depends(require_auth())):
    return {"tools": [], "status": "stub"}


@router.post("/")
async def create_tool(user: dict = Depends(require_auth())):
    return {"status": "stub", "message": "Tool creation not yet implemented"}
