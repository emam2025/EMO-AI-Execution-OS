import asyncio
from datetime import datetime
from typing import Dict, Optional

# Optional persistence: use the async Database if available to make DB the
# source-of-truth for tasks. We import lazily to avoid circular imports at
# module import time when core.db imports this module.
_db = None

def _get_db():
    global _db
    if _db is None:
        try:
            from core.db import db as _db_instance
            _db = _db_instance
        except Exception:
            _db = None
    return _db


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
        now = datetime.utcnow().isoformat()
        # Persist to DB if available
        db = _get_db()
        if db:
            try:
                await db.create_task(task_id, message)
            except Exception:
                # Fall back to in-memory if DB write fails
                pass

        async with self._lock:
            self.tasks[task_id] = {
                "id": task_id,
                "message": message,
                "status": "pending",
                "created_at": now,
            }

    async def update_task(self, task_id: str, **kwargs) -> None:
        # Update DB first if available
        db = _get_db()
        if db:
            try:
                await db.update_task(task_id, **kwargs)
            except Exception:
                pass

        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)
            else:
                # If not in memory, try to fetch from DB to populate cache
                if db:
                    try:
                        row = await db.get_task(task_id)
                        if row:
                            self.tasks[task_id] = row
                            self.tasks[task_id].update(kwargs)
                    except Exception:
                        pass

    async def get_task(self, task_id: str) -> Optional[Dict]:
        async with self._lock:
            if task_id in self.tasks:
                return self.tasks.get(task_id)

        # If not in-memory, try DB
        db = _get_db()
        if db:
            try:
                row = await db.get_task(task_id)
                if row:
                    async with self._lock:
                        self.tasks[task_id] = row
                    return row
            except Exception:
                pass

        return None


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
