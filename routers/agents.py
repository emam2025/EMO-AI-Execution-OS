from fastapi import APIRouter

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/")
async def list_agents():
    return {"agents": [], "status": "stub"}


@router.post("/")
async def create_agent():
    return {"status": "stub", "message": "Agent creation not yet implemented"}
