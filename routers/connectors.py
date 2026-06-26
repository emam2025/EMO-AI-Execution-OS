from fastapi import APIRouter, Depends
from middleware.auth import require_auth

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/")
async def list_connectors(user: dict = Depends(require_auth())):
    return {"connectors": [], "status": "stub"}
