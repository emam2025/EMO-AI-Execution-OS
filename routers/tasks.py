from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.runtime.data_providers import get_db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(limit: int = 10, status: str = ""):
    """List tasks with optional status filter."""
    tasks = await get_db().list_tasks(limit=limit, status=status if status else None)
    return JSONResponse({"tasks": tasks, "total": len(tasks)})


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a specific task by ID."""
    task = await get_db().get_task(task_id)
    if not task:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Task {task_id} not found"},
        )
    return JSONResponse(task)
