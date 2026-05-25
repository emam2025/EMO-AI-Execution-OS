import asyncio
import json
from typing import AsyncGenerator
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/stream", tags=["stream"])

# In-memory queue for SSE events
# Key: task_id, Value: asyncio.Queue
_streams: dict = {}


def publish_event(task_id: str, event_type: str, data: dict) -> None:
    """Publish an SSE event for a given task_id."""
    if task_id in _streams:
        _streams[task_id].put_nowait({
            "event": event_type,
            "data": json.dumps(data, ensure_ascii=False),
        })


def publish_result(task_id: str, content: str) -> None:
    """Publish a final result event."""
    publish_event(task_id, "result", {"content": content})
    publish_event(task_id, "done", {"task_id": task_id})


def publish_error(task_id: str, message: str, code: str = "unknown") -> None:
    """Publish an error event."""
    publish_event(task_id, "error", {"message": message, "code": code})
    publish_event(task_id, "done", {"task_id": task_id})


def publish_step(
    task_id: str,
    status: str,
    step: str = "",
    agent: str = "",
    tool: str = "",
    result: str = "",
    progress: int = 0,
) -> None:
    """Publish a step event."""
    data = {"step": step, "status": status, "progress": progress}
    if agent:
        data["agent"] = agent
    if tool:
        data["tool"] = tool
    if result:
        data["result"] = result
    publish_event(task_id, f"step_{status}", data)


def close_stream(task_id: str) -> None:
    """Close and remove a stream."""
    if task_id in _streams:
        _streams[task_id].put_nowait(None)  # sentinel
        del _streams[task_id]


@router.get("/{task_id}")
async def stream_task(task_id: str) -> EventSourceResponse:
    """SSE endpoint for real-time task progress."""
    queue: asyncio.Queue = asyncio.Queue()
    _streams[task_id] = queue

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            while True:
                event = await queue.get()
                if event is None:  # sentinel = stream closed
                    break
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            _streams.pop(task_id, None)

    return EventSourceResponse(event_generator())


@router.get("/global")
async def global_stream() -> EventSourceResponse:
    """SSE endpoint for global events (task updates, notifications)."""
    queue: asyncio.Queue = asyncio.Queue()
    _streams["__global__"] = queue

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            _streams.pop("__global__", None)

    return EventSourceResponse(event_generator())


def publish_global(event_type: str, data: dict) -> None:
    """Publish a global SSE event."""
    if "__global__" in _streams:
        _streams["__global__"].put_nowait({
            "event": event_type,
            "data": json.dumps(data, ensure_ascii=False),
        })
