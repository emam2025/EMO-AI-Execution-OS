import asyncio
import pytest
from core.task_manager import AsyncTaskManager

@pytest.mark.asyncio
async def test_async_task_manager_create_update_get():
    manager = AsyncTaskManager()
    task_id = "t1"
    await manager.create_task(task_id, "hello")
    t = await manager.get_task(task_id)
    assert t is not None
    assert t["message"] == "hello"

    await manager.update_task(task_id, status="running")
    t2 = await manager.get_task(task_id)
    assert t2["status"] == "running"

    # Ensure non-existent returns None
    assert await manager.get_task("no-such") is None
