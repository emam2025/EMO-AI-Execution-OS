from fastapi import APIRouter

router = APIRouter(prefix="/api/digital-twin", tags=["digital_twin"])


@router.get("/")
async def list_twins():
    return {"twins": [], "status": "stub"}
