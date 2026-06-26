from fastapi import APIRouter

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


@router.get("/")
async def list_enterprise():
    return {"enterprise": {}, "status": "stub"}
