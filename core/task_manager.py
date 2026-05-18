import asyncio
from datetime import datetime
from typing import Dict, Optional


class AsyncTaskManager:
    """Async-friendly task manager using asyncio primitives.

    Provides the same logical API as the previous synchronous TaskManager
    but with async methods and an internal asyncio.Lock to avoid thread/loop
    contention. Kept lightweight and suitable as an in-memory cache.
    """

    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def create_task(self, task_id: str, message: str) -> None:
        async with self._lock:
            self.tasks[task_id] = {
                "id": task_id,
                "message": message,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat(),
            }

    async def update_task(self, task_id: str, **kwargs) -> None:
        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)

    async def get_task(self, task_id: str) -> Optional[Dict]:
        async with self._lock:
            return self.tasks.get(task_id)


# Backwards-compatible synchronous shim for code that expects TaskManager()
class TaskManager(AsyncTaskManager):
    """Synchronous adapter exposing the old method names for compatibility.

    These methods run the async counterparts using asyncio.get_event_loop().
    Prefer using AsyncTaskManager directly in async code. The shim ensures
    existing synchronous call sites continue to work temporarily.
    """

    def __init__(self):
        # Do not call super().__init__ directly if event loop isn't running;
        # we still initialize the data structures.
        super().__init__()

    def create_task(self, task_id, message):
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(super().create_task(task_id, message))

    def update_task(self, task_id, **kwargs):
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(super().update_task(task_id, **kwargs))

    def get_task(self, task_id):
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(super().get_task(task_id))


def _get_or_create_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        # No current event loop in thread — create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
