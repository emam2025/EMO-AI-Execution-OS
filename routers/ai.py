"""AI API Router — Production Gateway for the Code Intelligence Layer.

Endpoints:
  POST /api/ai/run         — Full DAG execution (UnifiedRuntime)
  POST /api/ai/query       — Planner → DAG (no execution)
  POST /api/ai/explain     — Direct ai_agent call
  GET  /api/ai/status      — Health check for all AI subsystems
  GET  /api/ai/trace       — List recent sessions with DAG traces
  GET  /api/ai/trace/{sid} — Session details + DAG trace
  GET  /api/ai/trace/{sid}/replay   — Step-by-step replay
  GET  /api/ai/trace/{sid}/visualize — ASCII DAG visualization
  POST /api/ai/trace/compare — Compare two session executions
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.runtime.facade import EmoRuntimeFacade
from middleware.auth import require_auth

logger = logging.getLogger("emo_ai.router")


# ======================================================================
# Pydantic-style request/response models (plain dict for simplicity)
# ======================================================================

class AIRouter:
    """Holds a reference to the EmoRuntimeFacade.

    Initialised once by main.py lifespan and injected into endpoints.
    """

    def __init__(self):
        self.initialized = False
        self.facade: Optional[EmoRuntimeFacade] = None
        self.error: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        if self.facade is not None:
            return self.facade.health()
        return {
            "initialized": False,
            "error": self.error or "Facade not set",
        }


ai_state = AIRouter()
router = APIRouter(prefix="/api/ai", tags=["ai"])


# ======================================================================
# Helper: ensure AI is initialized
# ======================================================================

def _ensure_initialized():
    if not ai_state.initialized or ai_state.facade is None:
        raise HTTPException(status_code=503, detail={
            "error": "AI layer not initialized",
            "detail": ai_state.error or "Call /api/ai/status for details",
        })


# ======================================================================
# POST /api/ai/run — Full DAG execution
# ======================================================================

@router.post("/run")
def run_query(
    query: str = Query(..., description="Natural-language query"),
    strategy: str = Query("balanced", description="Retrieval strategy"),
    user: dict = Depends(require_auth()),
):
    """Full pipeline: plan -> execute DAG -> format answer."""
    _ensure_initialized()
    try:
        result = ai_state.facade.submit({"query": query})
        return {
            "query": query,
            "plan": result.get("plan_summary"),
            "tools_used": result.get("tools_used"),
            "steps": result.get("step_results"),
            "answer": result.get("final_answer"),
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("run_query failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# POST /api/ai/query — Planner -> DAG (no execution)
# ======================================================================

@router.post("/query")
def plan_query(
    query: str = Query(..., description="Natural-language query"),
    user: dict = Depends(require_auth()),
):
    """Classify intent and build a DAG plan without executing."""
    _ensure_initialized()
    try:
        plan = ai_state.facade.query({"query": query, "mode": "plan"})
        return {
            "query": query,
            "intent": plan.get("intent"),
            "target": plan.get("target"),
            "target_type": plan.get("target_type"),
            "confidence": plan.get("confidence"),
            "dag": plan.get("dag", {}),
        }
    except Exception as e:
        logger.error("plan_query failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# POST /api/ai/explain — Direct ai_agent call
# ======================================================================

@router.post("/explain")
def explain_symbol(
    symbol_id: str = Query(..., description="Symbol ID or name"),
    mode: str = Query("explain", description="explain | impact | why | refactor"),
    user: dict = Depends(require_auth()),
):
    """Direct call to the AI reasoning agent for a symbol."""
    _ensure_initialized()
    try:
        result = ai_state.facade.query({
            "mode": mode,
            "symbol_id": symbol_id,
        })
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"symbol_id": symbol_id, "mode": mode, "result": result}
    except HTTPException:
        raise
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("explain_symbol failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/status — Health check
# ======================================================================

@router.get("/status")
def ai_status(user: dict = Depends(require_auth())):
    """Health check for all AI subsystems."""
    return ai_state.status()


# ======================================================================
# GET /api/ai/trace — List sessions
# ======================================================================

@router.get("/trace")
def list_traces(
    limit: int = Query(20, description="Max sessions"),
    has_trace: bool = Query(True, description="Only sessions with DAG traces"),
    user: dict = Depends(require_auth()),
):
    """List recent execution sessions with DAG traces."""
    _ensure_initialized()
    try:
        result = ai_state.facade.observe({
            "target": "trace_sessions",
            "limit": limit,
            "has_trace": has_trace,
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/trace/{session_id} — Session details
# ======================================================================

@router.get("/trace/{session_id}")
def get_trace(session_id: str, user: dict = Depends(require_auth())):
    """Get session metadata + DAG trace."""
    _ensure_initialized()
    try:
        result = ai_state.facade.observe({
            "target": "trace_session",
            "session_id": session_id,
        })
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/trace/{session_id}/replay — Step-by-step
# ======================================================================

@router.get("/trace/{session_id}/replay")
def replay_session(session_id: str, user: dict = Depends(require_auth())):
    """Step-by-step chronological replay of a DAG execution."""
    _ensure_initialized()
    try:
        result = ai_state.facade.observe({
            "target": "trace_replay",
            "session_id": session_id,
        })
        if result.get("steps") and isinstance(result["steps"], list) and \
           result["steps"] and "error" in result["steps"][0]:
            raise HTTPException(status_code=404, detail=result["steps"][0]["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/trace/{session_id}/visualize — ASCII DAG
# ======================================================================

@router.get("/trace/{session_id}/visualize")
def visualize_session(session_id: str, user: dict = Depends(require_auth())):
    """ASCII-graph visualization of a DAG execution."""
    _ensure_initialized()
    try:
        result = ai_state.facade.observe({
            "target": "trace_visualize",
            "session_id": session_id,
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# POST /api/ai/trace/compare — Compare two sessions
# ======================================================================

@router.post("/trace/compare")
def compare_sessions(
    session_a: str = Query(..., description="First session ID"),
    session_b: str = Query(..., description="Second session ID"),
    user: dict = Depends(require_auth()),
):
    """Side-by-side comparison of two DAG executions."""
    _ensure_initialized()
    try:
        result = ai_state.facade.observe({
            "target": "trace_compare",
            "session_a": session_a,
            "session_b": session_b,
        })
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("compare_sessions failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
