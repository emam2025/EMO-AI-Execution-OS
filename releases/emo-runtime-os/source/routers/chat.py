import uuid
import asyncio
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from core.runtime.data_providers import get_db, get_state
from routers.utils.context_builder import build_conversation_context
from routers.stream import (
    publish_step,
    publish_result,
    publish_error,
    publish_global,
    close_stream,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str = ""
    project_id: str = ""
    session_id: str = ""
    file_path: str = ""


@router.post("")
async def chat(req: ChatRequest):
    task_id = str(uuid.uuid4())[:8]
    conversation_id = req.conversation_id

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

    # Start background processing
    asyncio.create_task(
        process_task(task_id, req.message, conversation_id, req.project_id, req.session_id, req.file_path)
    )

    return JSONResponse({
        "task_id": task_id,
        "status": "started",
    })


async def process_task(
    task_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    file_path: Optional[str] = None,
):
    """Background task processor with SSE streaming."""
    try:
        # Update task status
        await get_db().update_task(task_id, status="running")
        publish_step(task_id, "start", step="processing", agent="planner")
        publish_global("task_update", {
            "task_id": task_id,
            "status": "running",
            "progress": 10,
        })

        # Get conversation history for context
        conversation_messages = []
        if conversation_id:
            if conversation_id not in get_state().conversations:
                get_state().conversations[conversation_id] = {"messages": []}
            conversation_messages = get_state().conversations[conversation_id]["messages"]

        publish_step(task_id, "complete", step="context_built", progress=20)
        publish_global("task_update", {
            "task_id": task_id,
            "status": "running",
            "progress": 20,
        })

        # Detect if user is asking about project contents
        project_keywords = [
            "محتوي", "محتوى", "محتويات", "مكونات", "هيكل", "files", "contents", "structure",
            "تحليل", "اكتشف", "problems", "issues", "project analysis", "اخبرني"
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
                publish_step(task_id, "complete", step="file_read", agent="planner", result="File read", progress=30)
            except Exception as e:
                project_context = f"Could not read file: {e}"
                
        elif is_project_query:
            publish_step(task_id, "start", step="analyzing_project", agent="planner", progress=25)
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
                publish_step(task_id, "complete", step="project_analyzed", agent="planner", result="Project analyzed", progress=30)
            except Exception as e:
                project_context = f"Could not analyze project: {e}"
                publish_step(task_id, "error", step="project_analysis_failed", agent="planner", result=str(e), progress=30)

        # Route to appropriate agent
        agent = get_state().agents["planner"]

        # Simple classification: if code-related → coder, else → planner
        code_keywords = ["كود", "code", "دالة", "function", "class", "برمج", "script"]
        if any(kw in message.lower() for kw in code_keywords):
            agent = get_state().agents.get("coder", agent)

        publish_step(
            task_id, "start",
            step="agent_execution",
            agent=agent.name,
            progress=35 if is_project_query else 30,
        )
        publish_global("task_update", {
            "task_id": task_id,
            "status": "running",
            "progress": 35 if is_project_query else 30,
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

        result = await agent.run_async(
            agent_message,
            conversation_messages=conversation_messages,
        )

        publish_step(
            task_id, "complete",
            step="agent_execution",
            agent=agent.name,
            progress=80,
        )
        publish_global("task_update", {
            "task_id": task_id,
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

        publish_result(task_id, result)
        publish_global("task_update", {
            "task_id": task_id,
            "status": "complete",
            "progress": 100,
        })
        publish_global("play_sound", {"message": "task_complete"})

        close_stream(task_id)

    except Exception as e:
        await get_db().update_task(
            task_id,
            status="error",
            error=str(e),
        )
        publish_error(task_id, str(e))
        publish_global("task_update", {
            "task_id": task_id,
            "status": "error",
            "progress": 0,
        })
        close_stream(task_id)
