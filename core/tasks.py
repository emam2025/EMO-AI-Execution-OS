import asyncio
from core.db import db


async def cleanup_old_tasks_loop(_task_manager):
    """Background loop that cleans up old tasks every 5 minutes."""
    while True:
        await asyncio.sleep(300)  # 5 minutes
        try:
            deleted = await db.cleanup_old_tasks(max_age_hours=24)
            if deleted > 0:
                print(f"[cleanup] Deleted {deleted} old tasks")
        except Exception as e:
            print(f"[cleanup] Error: {e}")
