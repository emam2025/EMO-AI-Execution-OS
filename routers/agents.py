from fastapi import APIRouter, Depends
from middleware.auth import require_auth

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/")
async def list_agents(user: dict = Depends(require_auth())):
    return {"agents": [], "status": "stub"}


@router.post("/")
async def create_agent(user: dict = Depends(require_auth())):
    return {"status": "stub", "message": "Agent creation not yet implemented"}
