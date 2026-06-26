from fastapi import APIRouter

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/")
async def list_tools():
    return {"tools": [], "status": "stub"}


@router.post("/")
async def create_tool():
    return {"status": "stub", "message": "Tool creation not yet implemented"}
