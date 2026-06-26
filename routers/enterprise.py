from fastapi import APIRouter, Depends
from middleware.auth import require_auth

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


@router.get("/")
async def list_enterprise(user: dict = Depends(require_auth())):
    return {"enterprise": {}, "status": "stub"}
