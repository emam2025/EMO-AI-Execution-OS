from fastapi import APIRouter

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/")
async def list_approvals():
    return {"approvals": [], "status": "stub"}
