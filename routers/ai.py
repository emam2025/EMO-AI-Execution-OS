"""AI API Router — Production Gateway for the Code Intelligence Layer.

Endpoints:
  POST /api/ai/run         — Full DAG execution (UnifiedRuntime)
  POST /api/ai/query        — Planner → DAG → execute
  POST /api/ai/explain      — Direct ai_agent call
  GET  /api/ai/status       — Health check for all AI subsystems
  GET  /api/ai/trace        — List recent sessions with DAG traces
  GET  /api/ai/trace/{sid}  — Session details + DAG trace
  GET  /api/ai/trace/{sid}/replay   — Step-by-step replay
  GET  /api/ai/trace/{sid}/visualize — ASCII DAG visualization
  POST /api/ai/trace/compare — Compare two session executions
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.execution_memory import ExecutionMemory
from core.metrics_store import MetricsStore
from core.graph_query import GraphQuery
from core.graph_retrieval import GraphRetrievalEngine
from core.ai_agent import CodeIntelligenceAgent
from core.ai_context_engine import AIContextEngine
from core.hybrid_retriever import HybridRetriever
from core.orchestrator import QueryPlanner
from core.unified_runtime import UnifiedRuntime
from core.dag_replay import DAGReplayEngine
from core.execution_engine import DAGBuilder
from core.types import Intent

logger = logging.getLogger("emo_ai.router")


# ======================================================================
# Pydantic-style request/response models (plain dict for simplicity)
# ======================================================================

class AIRouter:
    """Holds references to all AI components.

    Initialised once by main.py lifespan and injected into endpoints.
    """

    def __init__(self):
        self.initialized = False
        self.gq: Optional[GraphQuery] = None
        self.gre: Optional[GraphRetrievalEngine] = None
        self.agent: Optional[CodeIntelligenceAgent] = None
        self.ctx: Optional[AIContextEngine] = None
        self.hybrid: Optional[HybridRetriever] = None
        self.runtime: Optional[UnifiedRuntime] = None
        self.memory: Optional[ExecutionMemory] = None
        self.metrics: Optional[MetricsStore] = None
        self.replay: Optional[DAGReplayEngine] = None
        self.cache = None
        self.service_registry = None
        self.error: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        return {
            "initialized": self.initialized,
            "gq": self.gq is not None,
            "gre": self.gre is not None,
            "agent": self.agent is not None,
            "ctx": self.ctx is not None,
            "hybrid": self.hybrid is not None,
            "runtime": self.runtime is not None,
            "memory": self.memory is not None,
            "metrics": self.metrics is not None,
            "replay": self.replay is not None,
            "cache": self.cache is not None,
            "service_registry": self.service_registry is not None,
            "error": self.error,
        }


ai_state = AIRouter()
router = APIRouter(prefix="/api/ai", tags=["ai"])


# ======================================================================
# Helper: ensure AI is initialized
# ======================================================================

def _ensure_initialized():
    if not ai_state.initialized:
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
):
    """Full pipeline: plan → execute DAG → format answer."""
    _ensure_initialized()

    try:
        result = ai_state.runtime.execute(query)
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
# POST /api/ai/query — Planner → DAG (no execution)
# ======================================================================

@router.post("/query")
def plan_query(
    query: str = Query(..., description="Natural-language query"),
):
    """Classify intent and build a DAG plan without executing."""
    _ensure_initialized()

    try:
        plan = ai_state.runtime.planner.plan(query)
        dag_dict = plan.dag.to_dict() if plan.dag else {}
        return {
            "query": query,
            "intent": plan.intent,
            "target": plan.target,
            "target_type": plan.target_type,
            "confidence": plan.confidence,
            "dag": dag_dict,
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
):
    """Direct call to the AI reasoning agent for a symbol."""
    _ensure_initialized()

    try:
        method_map = {
            "explain": ai_state.agent.explain,
            "impact": ai_state.agent.impact,
            "why": ai_state.agent.why,
            "refactor": ai_state.agent.suggest_refactor,
        }
        fn = method_map.get(mode)
        if fn is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown mode '{mode}'. Choose: {list(method_map.keys())}",
            )
        result = fn(symbol_id)
        return {"symbol_id": symbol_id, "mode": mode, "result": result}
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("explain_symbol failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/status — Health check
# ======================================================================

@router.get("/status")
def ai_status():
    """Health check for all AI subsystems."""
    return ai_state.status()


# ======================================================================
# GET /api/ai/trace — List sessions
# ======================================================================

@router.get("/trace")
def list_traces(
    limit: int = Query(20, description="Max sessions"),
    has_trace: bool = Query(True, description="Only sessions with DAG traces"),
):
    """List recent execution sessions with DAG traces."""
    _ensure_initialized()

    try:
        sessions = ai_state.replay.available_sessions(limit=limit, has_trace=has_trace)
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/trace/{session_id} — Session details
# ======================================================================

@router.get("/trace/{session_id}")
def get_trace(session_id: str):
    """Get session metadata + DAG trace."""
    _ensure_initialized()

    try:
        sess = ai_state.memory.get_session(session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        trace = ai_state.memory.get_dag_trace(session_id)
        return {
            "session": {
                "session_id": sess.session_id,
                "query": sess.query,
                "strategy": sess.strategy,
                "status": sess.status,
                "started_at": sess.started_at,
                "completed_at": sess.completed_at,
            },
            "dag_trace": trace,
            "has_trace": trace is not None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/trace/{session_id}/replay — Step-by-step
# ======================================================================

@router.get("/trace/{session_id}/replay")
def replay_session(session_id: str):
    """Step-by-step chronological replay of a DAG execution."""
    _ensure_initialized()

    try:
        narrative = ai_state.replay.step_through(session_id)
        if narrative and "error" in narrative[0]:
            raise HTTPException(status_code=404, detail=narrative[0]["error"])
        return {"session_id": session_id, "steps": narrative}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# GET /api/ai/trace/{session_id}/visualize — ASCII DAG
# ======================================================================

@router.get("/trace/{session_id}/visualize")
def visualize_session(session_id: str):
    """ASCII-graph visualization of a DAG execution."""
    _ensure_initialized()

    try:
        viz = ai_state.replay.visualize(session_id)
        return {"session_id": session_id, "visualization": viz}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ======================================================================
# POST /api/ai/trace/compare — Compare two sessions
# ======================================================================

@router.post("/trace/compare")
def compare_sessions(
    session_a: str = Query(..., description="First session ID"),
    session_b: str = Query(..., description="Second session ID"),
):
    """Side-by-side comparison of two DAG executions."""
    _ensure_initialized()

    try:
        comp = ai_state.replay.compare(session_a, session_b)
        return {
            "session_a": {
                "session_id": comp.session_a,
                "query": comp.query_a,
            },
            "session_b": {
                "session_id": comp.session_b,
                "query": comp.query_b,
            },
            "duration_delta_ms": comp.total_duration_delta_ms,
            "node_count_delta": comp.node_count_delta,
            "status_match": comp.status_match,
            "tool_diff": comp.tool_diff,
            "node_comparisons": comp.node_comparisons,
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
