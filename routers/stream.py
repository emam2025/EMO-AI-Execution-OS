import asyncio
import json
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from middleware.auth import require_auth

router = APIRouter(prefix="/api/stream", tags=["stream"])

# In-memory queue for SSE events
# Key: task_id, Value: asyncio.Queue
_streams: dict = {}

# Pre-connection buffer: events emitted before SSE client connects
# Key: task_id, Value: list of events
_pre_connect_buffer: dict = {}
# Task IDs that have had their SSE client connect
_clients_connected: set = set()

# Mission registry: mission_id -> {task_id, started_at, status, agent, mode}
_missions: dict = {}
_mission_seq: int = 0


def generate_mission_id() -> str:
    """Generate a sequential Mission ID: EMO-YYYY-NNNNN."""
    global _mission_seq
    from datetime import datetime
    _mission_seq += 1
    return f"EMO-{datetime.now().year}-{_mission_seq:05d}"


def publish_event(task_id: str, event_type: str, data: dict) -> None:
    """Publish an SSE event for a given task_id.

    If no SSE client is connected yet, buffer the event so it's not lost.
    """
    event = {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False),
    }
    if task_id in _streams:
        _streams[task_id].put_nowait(event)
    else:
        # Buffer until SSE client connects (cap at 100 events to avoid runaway)
        if task_id not in _pre_connect_buffer:
            _pre_connect_buffer[task_id] = []
        buf = _pre_connect_buffer[task_id]
        if len(buf) < 100:
            buf.append(event)


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
    agent_identity: Optional[dict] = None,
    execution: Optional[dict] = None,
    mission_id: str = "",
) -> None:
    """Publish a step event with full Chat Identity context.

    agent_identity: {name, role, model, tools[], memory, mode, permissions[]}
    execution: {phase, tool, status, input, output, duration_ms}
    """
    data = {"step": step, "status": status, "progress": progress}
    if agent:
        data["agent"] = agent
    if tool:
        data["tool"] = tool
    if result:
        data["result"] = result
    if agent_identity:
        data["agent_identity"] = agent_identity
    if execution:
        data["execution"] = execution
    if mission_id:
        data["mission_id"] = mission_id
    publish_event(task_id, f"step_{status}", data)


def close_stream(task_id: str) -> None:
    """Close and remove a stream."""
    if task_id in _streams:
        _streams[task_id].put_nowait(None)  # sentinel
        del _streams[task_id]
    _pre_connect_buffer.pop(task_id, None)


@router.get("/{task_id}")
async def stream_task(task_id: str, user: dict = Depends(require_auth())) -> EventSourceResponse:
    """SSE endpoint for real-time task progress."""
    queue: asyncio.Queue = asyncio.Queue()
    _streams[task_id] = queue
    _clients_connected.add(task_id)

    # Flush any pre-connection buffered events
    buffered = _pre_connect_buffer.pop(task_id, [])

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            # Yield buffered events first
            for event in buffered:
                yield event
            while True:
                event = await queue.get()
                if event is None:  # sentinel = stream closed
                    break
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            _streams.pop(task_id, None)
            _clients_connected.discard(task_id)

    return EventSourceResponse(event_generator())


@router.get("/global")
async def global_stream(user: dict = Depends(require_auth())) -> EventSourceResponse:
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


def register_mission(mission_id: str, task_id: str, agent: str, mode: str) -> None:
    """Register a new mission in the runtime state."""
    from datetime import datetime
    _missions[mission_id] = {
        "mission_id": mission_id,
        "task_id": task_id,
        "started_at": datetime.now().isoformat(),
        "status": "running",
        "agent": agent,
        "mode": mode,
    }


def complete_mission(mission_id: str, status: str = "complete") -> None:
    """Mark a mission as complete or error."""
    if mission_id in _missions:
        _missions[mission_id]["status"] = status


def list_missions() -> list:
    """Return the last 20 missions, newest first."""
    return sorted(_missions.values(), key=lambda m: m["started_at"], reverse=True)[:20]


@router.get("/runtime/state")
async def runtime_state(user: dict = Depends(require_auth())) -> dict:
    """Return the current Chat Runtime state for the header.

    Reads from real runtime registries:
    - active agent: from get_state().agents
    - model: from agent.brain
    - tools: from agent.tools (if any)
    - memory: from app state
    - mode: from settings (.emo_settings.json)
    - permissions: derived from tools
    """
    try:
        from core.runtime.data_providers import get_state
        from pathlib import Path
        import json as _json

        state = get_state()
        # Pick first agent (planner) as "active" baseline
        active = state.agents.get("planner") or next(iter(state.agents.values()))
        brain = active.brain if hasattr(active, "brain") else None
        provider = getattr(brain, "provider", "") if brain else ""
        model = getattr(brain, "model", "") if brain else ""

        # Tools: real from registry
        tools = []
        if state.tools and hasattr(state.tools, "to_list"):
            for t in state.tools.to_list():
                tools.append(t.get("name", ""))

        # Memory
        memory_label = "Session Memory" if state.memory else "No Memory"
        if state.memory and hasattr(state.memory, "store"):
            try:
                n = len(state.memory.store)
                if n > 0:
                    memory_label = f"Project Memory ({n})"
            except Exception:
                pass

        # Mode from settings
        mode = "Manual"
        settings_file = Path(".emo_settings.json")
        if settings_file.exists():
            try:
                s = _json.loads(settings_file.read_text())
                if s.get("autonomous_mode"):
                    mode = "Autonomous"
            except Exception:
                pass

        # Permissions derived from tools
        permissions_set = {"Sandbox"}
        if any(t for t in tools if "github" in t or "docker" in t or "vercel" in t or "supabase" in t or "firebase" in t):
            permissions_set.add("Network")
        if any(t for t in tools if "file" in t or "directory" in t):
            permissions_set.add("Filesystem")
        permissions = sorted(permissions_set)

        return {
            "online": True,
            "agent": {
                "name": active.name,
                "role": active.name.capitalize(),
            },
            "model": {
                "provider": provider,
                "name": model,
            },
            "tools": tools,
            "memory": memory_label,
            "mode": mode,
            "permissions": permissions,
            "missions": list_missions(),
        }
    except Exception as e:
        return {
            "online": False,
            "error": str(e),
            "agent": {"name": "unknown", "role": "unknown"},
            "model": {"provider": "", "name": ""},
            "tools": [],
            "memory": "Unknown",
            "mode": "Manual",
            "permissions": ["Sandbox"],
            "missions": [],
        }
