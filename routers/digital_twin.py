from fastapi import APIRouter, Depends
from middleware.auth import require_auth

router = APIRouter(prefix="/api/digital-twin", tags=["digital_twin"])


@router.get("/")
async def list_twins(user: dict = Depends(require_auth())):
    return {"twins": [], "status": "stub"}
