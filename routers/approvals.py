from fastapi import APIRouter, Depends
from middleware.auth import require_auth

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/")
async def list_approvals(user: dict = Depends(require_auth())):
    return {"approvals": [], "status": "stub"}
