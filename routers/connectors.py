from fastapi import APIRouter

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("/")
async def list_connectors():
    return {"connectors": [], "status": "stub"}
