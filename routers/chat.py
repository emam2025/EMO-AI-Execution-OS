import uuid
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from middleware.auth import require_auth
from fastapi.responses import JSONResponse

from core.runtime.data_providers import get_db, get_state
from routers.utils.context_builder import build_conversation_context
from routers.stream import (
    publish_step,
    publish_result,
    publish_error,
    publish_global,
    close_stream,
    generate_mission_id,
    register_mission,
    complete_mission,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _build_agent_identity(agent) -> dict:
    """Build the full agent identity object from a real Agent instance."""
    brain = getattr(agent, "brain", None)
    provider = getattr(brain, "provider", "") if brain else ""
    model = getattr(brain, "model", "") if brain else ""
    tools = []
    if agent.tools and hasattr(agent.tools, "to_list"):
        for t in agent.tools.to_list():
            tools.append(t.get("name", ""))
    # Mode
    from pathlib import Path
    import json as _json
    mode = "Manual"
    sf = Path(".emo_settings.json")
    if sf.exists():
        try:
            s = _json.loads(sf.read_text())
            if s.get("autonomous_mode"):
                mode = "Autonomous"
        except Exception:
            pass
    # Memory
    state = get_state()
    memory_label = "Session Memory"
    if state.memory and hasattr(state.memory, "store"):
        try:
            n = len(state.memory.store)
            if n > 0:
                memory_label = f"Project Memory ({n})"
        except Exception:
            pass
    # Permissions
    permissions = {"Sandbox"}
    if any("github" in t or "docker" in t or "vercel" in t or "supabase" in t or "firebase" in t for t in tools):
        permissions.add("Network")
    if any("file" in t or "directory" in t for t in tools):
        permissions.add("Filesystem")
    return {
        "name": agent.name,
        "role": agent.name.capitalize(),
        "model": f"{provider}/{model}" if provider and model else model or provider,
        "tools": tools,
        "memory": memory_label,
        "mode": mode,
        "permissions": sorted(permissions),
    }


class ChatRequest(BaseModel):
    message: str
    conversation_id: str = ""
    project_id: str = ""
    session_id: str = ""
    file_path: str = ""
    mode: str = ""  # "manual" or "autonomous"
    mission_id: str = ""  # optional pre-generated


@router.post("")
async def chat(req: ChatRequest, user: dict = Depends(require_auth())):
    task_id = str(uuid.uuid4())[:8]
    conversation_id = req.conversation_id
    mission_id = req.mission_id or generate_mission_id()

    # Create conversation if missing
    if conversation_id and conversation_id not in get_state().conversations:
        get_state().conversations[conversation_id] = {"messages": []}
        await get_db().create_conversation(conversation_id)

    # Save user message
    if conversation_id:
        get_state().conversations[conversation_id]["messages"].append({
            "role": "user",
            "content": req.message,
        })
        msg_id = str(uuid.uuid4())[:8]
        await get_db().add_message(msg_id, conversation_id, "user", req.message)

    # Create task in DB with project/session context
    await get_db().create_task(task_id, req.message, conversation_id)
    if req.project_id:
        await get_db().update_task(task_id, project_id=req.project_id)
    if req.session_id:
        await get_db().update_task(task_id, session_id=req.session_id)
    if req.file_path:
        await get_db().update_task(task_id, tool_used=req.file_path)
    await get_db().update_task(task_id, mission_id=mission_id, mode=req.mode or "manual")

    # Start background processing
    asyncio.create_task(
        process_task(task_id, req.message, conversation_id, req.project_id, req.session_id, req.file_path, mission_id, req.mode or "manual")
    )

    return JSONResponse({
        "task_id": task_id,
        "mission_id": mission_id,
        "status": "started",
    })


async def process_task(
    task_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    file_path: Optional[str] = None,
    mission_id: str = "",
    mode: str = "manual",
):
    """Background task processor with SSE streaming + Chat Identity."""
    try:
        # AUTONOMOUS MODE (v1.1 Phase 4): delegate to MissionController
        if mode == "autonomous":
            await _process_autonomous(
                task_id, message, conversation_id, project_id, session_id, file_path, mission_id
            )
            return
        # Update task status
        await get_db().update_task(task_id, status="running")

        # Build initial identity from the first agent (planner)
        planner = get_state().agents["planner"]
        identity = _build_agent_identity(planner)
        identity["mode"] = "Autonomous" if mode == "autonomous" else identity["mode"]

        register_mission(mission_id, task_id, "planner", mode)

        # Mission start step
        publish_step(
            task_id, "start",
            step="mission_start",
            agent="planner",
            progress=5,
            agent_identity=identity,
            execution={"phase": "Understanding", "tool": "", "status": "running", "input": message, "output": "", "duration_ms": 0},
            mission_id=mission_id,
        )
        publish_global("task_update", {
            "task_id": task_id,
            "mission_id": mission_id,
            "status": "running",
            "progress": 5,
        })

        # Get conversation history for context
        conversation_messages = []
        if conversation_id:
            if conversation_id not in get_state().conversations:
                get_state().conversations[conversation_id] = {"messages": []}
            conversation_messages = get_state().conversations[conversation_id]["messages"]

        publish_step(
            task_id, "complete",
            step="context_built",
            progress=15,
            agent_identity=identity,
            execution={"phase": "Understanding", "tool": "", "status": "complete", "input": message, "output": f"{len(conversation_messages)} msgs", "duration_ms": 0},
            mission_id=mission_id,
        )
        publish_global("task_update", {
            "task_id": task_id,
            "mission_id": mission_id,
            "status": "running",
            "progress": 15,
        })

        # Detect if user is asking about project contents
        project_keywords = [
            "files", "contents", "structure",
            "problems", "issues", "project analysis"
        ]
        is_project_query = any(kw in message.lower() for kw in project_keywords)

        # Auto-analyze project if user asks about contents
        project_context = ""
        if file_path:
            # User selected a specific file - read its content
            try:
                from project_tools import WORKSPACE_ROOT, _safe_path
                import json
                from pathlib import Path as P
                project_dir = str(WORKSPACE_ROOT)
                settings_file = P(".emo_settings.json")
                if settings_file.exists():
                    try:
                        settings = json.loads(settings_file.read_text())
                        pd = settings.get("project_dir", "")
                        if pd:
                            project_dir = str(_safe_path(P(pd)))
                    except Exception:
                        pass
                
                file_full_path = _safe_path(P(project_dir) / file_path)
                if file_full_path.exists():
                    ext = file_full_path.suffix.lower()
                    if ext in ['.xlsx', '.xls', '.xlsm']:
                        project_context = f"""📄 Selected File: {file_path}

This is an Excel file from the project.

"""
                    else:
                        content = file_full_path.read_text(encoding='utf-8', errors='replace')
                        if len(content) > 5000:
                            content = content[:5000] + "\n\n... (truncated)"
                        project_context = f"""📄 Selected File: {file_path}

File Content:
{content}

"""
                publish_step(
                    task_id, "complete",
                    step="file_read",
                    agent="planner",
                    result="File read",
                    progress=25,
                    agent_identity=identity,
                    execution={"phase": "Planning", "tool": "file_reader", "status": "complete", "input": file_path, "output": f"{len(project_context)} bytes", "duration_ms": 0},
                    mission_id=mission_id,
                )
            except Exception as e:
                project_context = f"Could not read file: {e}"
                
        elif is_project_query:
            publish_step(
                task_id, "start",
                step="analyzing_project",
                agent="planner",
                progress=20,
                agent_identity=identity,
                execution={"phase": "Planning", "tool": "project_analyzer", "status": "running", "input": message, "output": "", "duration_ms": 0},
                mission_id=mission_id,
            )
            try:
                from project_tools import ProjectAnalyzer, WORKSPACE_ROOT
                # Get project directory from settings
                import json
                from pathlib import Path as P
                project_dir = str(WORKSPACE_ROOT)
                settings_file = P(".emo_settings.json")
                if settings_file.exists():
                    try:
                        settings = json.loads(settings_file.read_text())
                        pd = settings.get("project_dir", "")
                        if pd:
                            # Ensure it's inside workspace
                            from project_tools import _safe_path
                            project_dir = str(_safe_path(P(pd)))
                    except Exception:
                        pass
                analyzer = ProjectAnalyzer()
                project_context = analyzer.run(project_dir=project_dir)
                publish_step(
                    task_id, "complete",
                    step="project_analyzed",
                    agent="planner",
                    result="Project analyzed",
                    progress=25,
                    agent_identity=identity,
                    execution={"phase": "Planning", "tool": "project_analyzer", "status": "complete", "input": message, "output": f"{len(project_context)} chars", "duration_ms": 0},
                    mission_id=mission_id,
                )
            except Exception as e:
                project_context = f"Could not analyze project: {e}"
                publish_step(
                    task_id, "error",
                    step="project_analysis_failed",
                    agent="planner",
                    result=str(e),
                    progress=25,
                    agent_identity=identity,
                    execution={"phase": "Planning", "tool": "project_analyzer", "status": "error", "input": message, "output": str(e), "duration_ms": 0},
                    mission_id=mission_id,
                )

        # Route to appropriate agent
        agent = get_state().agents["planner"]

        # Simple classification: if code-related → coder, else → planner
        code_keywords = ["code", "function", "class", "script"]
        if any(kw in message.lower() for kw in code_keywords):
            agent = get_state().agents.get("coder", agent)

        # Build identity for the selected agent
        identity = _build_agent_identity(agent)
        identity["mode"] = "Autonomous" if mode == "autonomous" else identity["mode"]

        publish_step(
            task_id, "start",
            step="agent_execution",
            agent=agent.name,
            progress=30,
            agent_identity=identity,
            execution={"phase": "Executing", "tool": "", "status": "running", "input": message, "output": "", "duration_ms": 0},
            mission_id=mission_id,
        )
        publish_global("task_update", {
            "task_id": task_id,
            "mission_id": mission_id,
            "status": "running",
            "progress": 30,
        })

        # Execute agent with conversation history
        # Prepend project context if available
        agent_message = message
        if project_context:
            agent_message = (
                f"CRITICAL INSTRUCTION: The following is the ACTUAL analysis of the user's project. "
                f"You MUST use ONLY this data to answer. DO NOT invent, hallucinate, or make up any files, "
                f"directories, or structures. If the project is empty, say so. If you don't know, say so.\n\n"
                f"=== ACTUAL PROJECT ANALYSIS ===\n"
                f"{project_context}\n"
                f"=== END OF PROJECT ANALYSIS ===\n\n"
                f"User question: {message}\n\n"
                f"Answer based ONLY on the project analysis above. Never list tools as project contents. "
                f"Never invent file names or directory structures."
            )

        import time
        t0 = time.time()
        result = await agent.run_async(
            agent_message,
            conversation_messages=conversation_messages,
        )
        duration_ms = int((time.time() - t0) * 1000)

        publish_step(
            task_id, "complete",
            step="agent_execution",
            agent=agent.name,
            progress=80,
            agent_identity=identity,
            execution={"phase": "Executing", "tool": "llm_brain", "status": "complete", "input": message[:120], "output": f"{len(result)} chars", "duration_ms": duration_ms},
            mission_id=mission_id,
        )
        publish_global("task_update", {
            "task_id": task_id,
            "mission_id": mission_id,
            "status": "running",
            "progress": 80,
        })

        # Save assistant response
        if conversation_id:
            get_state().conversations[conversation_id]["messages"].append({
                "role": "assistant",
                "content": result,
            })
            msg_id = str(uuid.uuid4())[:8]
            await get_db().add_message(msg_id, conversation_id, "assistant", result)

        # Complete task
        await get_db().update_task(
            task_id,
            status="complete",
            result=result,
            agent=agent.name,
            progress=100,
        )

        # Mission completion - emit step BEFORE result so client processes it
        complete_mission(mission_id, "complete")
        publish_step(
            task_id, "complete",
            step="mission_complete",
            agent=agent.name,
            progress=100,
            agent_identity=identity,
            execution={"phase": "Delivery", "tool": "", "status": "complete", "input": "", "output": "Mission delivered", "duration_ms": 0},
            mission_id=mission_id,
        )
        # Give the client time to process the step event
        await asyncio.sleep(0.1)

        # Now build final result event with full identity for the message bubble
        from routers.stream import publish_event
        publish_event(task_id, "result", {
            "content": result,
            "agent_identity": identity,
            "mission_id": mission_id,
            "tools_used": [],
        })

        publish_global("task_update", {
            "task_id": task_id,
            "mission_id": mission_id,
            "status": "complete",
            "progress": 100,
        })
        publish_global("play_sound", {"message": "task_complete"})

        publish_event(task_id, "done", {"task_id": task_id, "mission_id": mission_id})

    except Exception as e:
        await get_db().update_task(
            task_id,
            status="error",
            error=str(e),
        )
        publish_error(task_id, str(e))
        publish_global("task_update", {
            "task_id": task_id,
            "mission_id": mission_id,
            "status": "error",
            "progress": 0,
        })
        if mission_id:
            complete_mission(mission_id, "error")


async def _process_autonomous(
    task_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    file_path: Optional[str] = None,
    mission_id: str = "",
):
    """v1.1 Phase 4 — Autonomous mode: delegate to MissionController.

    Creates a real Mission in the DB, runs the full pipeline (intent → plan →
    agent selection → tool resolution → execution → validation → delivery),
    and streams progress as SSE events.
    """
    try:
        await get_db().update_task(task_id, status="running")

        # Lazy import the mission controller + grab brain/state/db/memory
        from core.runtime.autonomy import MissionController
        from brain import Brain as _BrainCls
        _brain = _BrainCls()
        state = get_state()
        memory = getattr(state, "memory", None)

        # SSE bridge: turn controller's event_emitter events into publish_step events
        def _event_bridge(event_type: str, data: dict):
            try:
                d = data or {}
                prog = int(d.get("progress", {}).get("percentage", 0)) if isinstance(d.get("progress"), dict) else 0
                scaled = 5 + int(prog * 0.90)
                phase = d.get("phase") or "Executing"
                agent_name = ""
                tool_name = ""
                # Pull the latest step's agent/tool if available
                plan = d.get("plan") or []
                if d.get("current_step") is not None and plan:
                    idx = int(d.get("current_step", 0))
                    if 0 <= idx < len(plan):
                        agent_name = plan[idx].get("agent_name", "")
                        tool_name = plan[idx].get("tool", "")
                publish_step(
                    task_id, "complete" if event_type in ("mission_completed", "mission_planned", "mission_step_complete", "mission_step_agent", "mission_step_tool") else "start",
                    step=event_type,
                    agent=agent_name,
                    tool=tool_name,
                    progress=scaled,
                    execution={
                        "phase": phase,
                        "tool": tool_name,
                        "status": "complete" if "complete" in event_type or "planned" in event_type or "started" in event_type or "step_complete" in event_type or "step_agent" in event_type or "step_tool" in event_type else ("error" if "failed" in event_type or "recovering" in event_type else "running"),
                        "input": message[:200],
                        "output": (d.get("result", {}).get("summary", "") if d.get("result") else "")[:200],
                        "duration_ms": 0,
                    },
                    mission_id=mission_id,
                )
            except Exception as _:
                pass

        controller = MissionController(
            brain=_brain,
            state=state,
            db=get_db(),
            memory=memory,
            event_emitter=_event_bridge,
        )

        # 1. Create mission (intent analysis happens here)
        publish_step(
            task_id, "start",
            step="autonomous_mission_create",
            agent="planner",
            progress=5,
            execution={"phase": "Understanding", "tool": "intent_analyzer", "status": "running", "input": message, "output": "", "duration_ms": 0},
            mission_id=mission_id,
        )
        mission = await controller.create_mission(
            goal=message,
            project_id=project_id or "",
            conversation_id=conversation_id or "",
        )
        await get_db().append_mission_log(mission.id, {"type": "linked_chat_mission", "chat_mission_id": mission_id})

        # 2. Run the full pipeline (plan → select → resolve → execute → validate → deliver)
        # with a 240s safety timeout
        try:
            mission = await asyncio.wait_for(controller.run(mission.id), timeout=240.0)
        except asyncio.TimeoutError:
            import logging as _logging2
            _logging2.getLogger("emo-chat-autonomous").error(f"[autonomous] controller.run timed out after 240s for mission={mission.id}")
            await get_db().update_mission_full(mission.id, {
                "status": "failed",
                "result": {"summary": "Controller timed out after 240s", "output": None, "all_outputs": []},
            })
            await get_db().update_task(task_id, status="error", error="Controller timed out")
            publish_step(task_id, "error", step="mission_timeout", agent="planner", progress=95,
                execution={"phase": "Delivery", "tool": "", "status": "error", "input": "", "output": "Timeout", "duration_ms": 0},
                mission_id=mission_id)
            complete_mission(mission_id, "error")
            return

        # 3. Persist final result + write assistant message
        final_output = ""
        if mission.result and mission.result.get("output"):
            final_output = mission.result["output"]
        elif mission.result and mission.result.get("all_outputs"):
            parts = []
            for i, o in enumerate(mission.result["all_outputs"]):
                step_name = (mission.plan[i].get("name") if i < len(mission.plan) else f"step_{i+1}")
                parts.append(f"### {step_name}\n{o}")
            final_output = "\n\n".join(parts)
        else:
            final_output = mission.result.get("summary", "Mission completed") if mission.result else "Mission completed"

        if mission.status == "completed":
            await get_db().update_task(task_id, status="complete", result=mission.result.get("summary", "") if mission.result else "", agent="planner", progress=100)
        else:
            await get_db().update_task(task_id, status="error", error=mission.result.get("summary", "Mission failed") if mission.result else "Mission failed")

        if conversation_id and final_output:
            state.conversations.setdefault(conversation_id, {"messages": []})
            state.conversations[conversation_id]["messages"].append({
                "role": "assistant",
                "content": final_output,
            })
            msg_id = str(uuid.uuid4())[:8]
            await get_db().add_message(msg_id, conversation_id, "assistant", final_output)

        # 4. Final SSE: complete step + result event
        planner = state.agents["planner"]
        identity = _build_agent_identity(planner)
        identity["mode"] = "Autonomous"
        complete_mission(mission_id, "complete" if mission.status == "completed" else "error")
        publish_step(
            task_id, "complete",
            step="mission_complete",
            agent="planner",
            progress=100,
            agent_identity=identity,
            execution={"phase": "Delivery", "tool": "", "status": "complete" if mission.status == "completed" else "error", "input": "", "output": final_output[:200], "duration_ms": 0},
            mission_id=mission_id,
        )
        await asyncio.sleep(0.1)
        from routers.stream import publish_event
        publish_event(task_id, "result", {
            "content": final_output,
            "agent_identity": identity,
            "mission_id": mission_id,
            "tools_used": [t.get("name", "") for t in (mission.tools or [])],
            "autonomous": True,
            "internal_mission_id": mission.id,
        })
        publish_global("task_update", {"task_id": task_id, "mission_id": mission_id, "status": mission.status, "progress": 100 if mission.status == "completed" else 0})
        publish_global("play_sound", {"message": "task_complete"})
        publish_event(task_id, "done", {"task_id": task_id, "mission_id": mission_id})

    except Exception as e:
        import traceback as _tb
        import logging
        _log = logging.getLogger("emo-chat-autonomous")
        _log.error(f"[autonomous] task={task_id} mission={mission_id} FAILED: {e}\n{_tb.format_exc()}")
        try:
            await get_db().update_task(task_id, status="error", error=str(e))
        except Exception:
            pass
        try:
            publish_error(task_id, str(e))
        except Exception:
            pass
        try:
            publish_global("task_update", {"task_id": task_id, "mission_id": mission_id, "status": "error", "progress": 0})
        except Exception:
            pass
        try:
            if mission_id:
                complete_mission(mission_id, "error")
        except Exception:
            pass
