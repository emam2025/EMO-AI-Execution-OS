"""Phase F1 — Unified Runtime API FastAPI Router.

Maps 7 lifecycle methods of IUnifiedRuntime to HTTP endpoints:
  POST /api/runtime/submit
  POST /api/runtime/{ticket_id}/resume
  POST /api/runtime/{ticket_id}/cancel
  GET  /api/runtime/{ticket_id}/observe
  POST /api/runtime/{execution_id}/replay
  POST /api/runtime/scale
  POST /api/runtime/workers

All responses use ResponseEnvelope for consistent trace_id
and error serialisation (LAW 5, LAW 12).

Ref: DEVELOPER.md §15.2
Ref: Canon LAW 5, LAW 12, RULE 1
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from middleware.auth import require_auth
from core.runtime.api.unified_runtime_api import (
    ExecutionTicket,
    ReplayTicket,
    CancellationReceipt,
    ScalingReceipt,
    WorkerRegistration,
    LiveStateStream,
    ExecutionStatus,
    ExecutionContext,
    SubmissionOptions,
    ScalingPolicy,
)
from core.runtime.models.api_errors import (
    APIError,
    ResponseEnvelope,
)

logger = logging.getLogger("emo_ai.routers.runtime_api")

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


def _get_runtime(request: Request) -> Any:
    """Get the UnifiedRuntime instance from app state."""
    emo = getattr(request.app.state, "runtime", None)
    if emo is None:
        raise RuntimeError("EmoRuntime not available")
    api = getattr(emo, "unified_runtime", None)
    if api is None:
        raise RuntimeError("UnifiedRuntime not available")
    return api


# ── Request Models ──────────────────────────────────────────────

class SubmitRequest(BaseModel):
    dag: Any
    session_id: str = ""
    trace_id: str = ""
    strategy: str = "balanced"
    priority: int = 0
    ttl: float = 300.0
    max_retries: int = 3
    deterministic: bool = True


class ResumeRequest(BaseModel):
    from_checkpoint: Optional[str] = None


class CancelRequest(BaseModel):
    reason: str = ""
    force: bool = False


class ReplayRequest(BaseModel):
    deterministic: bool = True


class ScaleRequest(BaseModel):
    target_worker_count: int
    policy: str = "balanced"


class RegisterWorkerRequest(BaseModel):
    worker_id: str
    capabilities: Dict[str, Any] = {}
    endpoints: Dict[str, Any] = {}
    lease_ttl: float = 30.0


# ── 1. submit ───────────────────────────────────────────────────

@router.post("/submit", response_model=Dict[str, Any])
async def submit_execution(
    req: SubmitRequest,
    request: Request,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        ctx = ExecutionContext(
            session_id=req.session_id,
            trace_id=req.trace_id,
        )
        opts = SubmissionOptions(
            strategy=req.strategy,
            priority=req.priority,
            ttl=req.ttl,
            max_retries=req.max_retries,
            deterministic=req.deterministic,
        )
        ticket: ExecutionTicket = api.submit(req.dag, context=ctx, options=opts)
        env = ResponseEnvelope.success(
            data={
                "ticket_id": ticket.ticket_id,
                "dag_id": ticket.dag_id,
                "session_id": ticket.session_id,
                "trace_id": ticket.trace_id,
                "submitted_at": ticket.submitted_at,
            },
            ticket_id=ticket.ticket_id,
            trace_id=ticket.trace_id,
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("submit failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()


# ── 2. resume ───────────────────────────────────────────────────

@router.post("/{ticket_id}/resume", response_model=Dict[str, Any])
async def resume_execution(
    ticket_id: str,
    req: ResumeRequest,
    request: Request,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        status: ExecutionStatus = api.resume(ticket_id, from_checkpoint=req.from_checkpoint)
        env = ResponseEnvelope.success(
            data={
                "ticket_id": status.ticket_id,
                "state": status.state,
                "trace_id": status.trace_id,
                "node_states": status.node_states,
                "progress_pct": status.progress_pct,
                "checkpoint_available": status.checkpoint_available,
            },
            ticket_id=ticket_id,
            trace_id=status.trace_id,
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("resume failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()


# ── 3. cancel ───────────────────────────────────────────────────

@router.post("/{ticket_id}/cancel", response_model=Dict[str, Any])
async def cancel_execution(
    ticket_id: str,
    req: CancelRequest,
    request: Request,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        receipt: CancellationReceipt = api.cancel(
            ticket_id, reason=req.reason, force=req.force,
        )
        env = ResponseEnvelope.success(
            data={
                "ticket_id": receipt.ticket_id,
                "cancelled": receipt.cancelled,
                "terminated_state": receipt.terminated_state,
                "reason": receipt.reason,
                "trace_id": receipt.trace_id,
            },
            ticket_id=ticket_id,
            trace_id=receipt.trace_id,
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("cancel failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()


# ── 4. observe ──────────────────────────────────────────────────

@router.get("/{ticket_id}/observe", response_model=Dict[str, Any])
async def observe_execution(
    ticket_id: str,
    request: Request,
    stream: bool = False,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        state: LiveStateStream = api.observe(ticket_id, stream=stream)
        env = ResponseEnvelope.success(
            data={
                "ticket_id": state.ticket_id,
                "current_state": state.current_state,
                "progress": state.progress,
                "active_nodes": state.active_nodes,
                "completed_nodes": state.completed_nodes,
                "failed_nodes": state.failed_nodes,
            },
            ticket_id=ticket_id,
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("observe failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()


# ── 5. replay ───────────────────────────────────────────────────

@router.post("/{execution_id}/replay", response_model=Dict[str, Any])
async def replay_execution(
    execution_id: str,
    req: ReplayRequest,
    request: Request,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        ticket: ReplayTicket = api.replay(execution_id, deterministic=req.deterministic)
        env = ResponseEnvelope.success(
            data={
                "execution_id": ticket.execution_id,
                "replay_id": ticket.replay_id,
                "trace_id": ticket.trace_id,
                "deterministic": ticket.deterministic,
                "checkpoint_id": ticket.checkpoint_id,
            },
            trace_id=ticket.trace_id,
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("replay failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()


# ── 6. scale ────────────────────────────────────────────────────

@router.post("/scale", response_model=Dict[str, Any])
async def scale_workers(
    req: ScaleRequest,
    request: Request,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        policy = ScalingPolicy(req.policy)
        receipt: ScalingReceipt = api.scale(req.target_worker_count, policy=policy)
        env = ResponseEnvelope.success(
            data={
                "previous_count": receipt.previous_count,
                "target_count": receipt.target_count,
                "actual_count": receipt.actual_count,
                "policy": receipt.policy,
            },
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("scale failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()


# ── 7. register_worker ──────────────────────────────────────────

@router.post("/workers", response_model=Dict[str, Any])
async def register_worker(
    req: RegisterWorkerRequest,
    request: Request,
    user: dict = Depends(require_auth()),
):
    try:
        api = _get_runtime(request)
        manifest = {
            "worker_id": req.worker_id,
            "capabilities": req.capabilities,
            "endpoints": req.endpoints,
            "lease_ttl": req.lease_ttl,
        }
        registration: WorkerRegistration = api.register_worker(manifest)
        env = ResponseEnvelope.success(
            data={
                "worker_id": registration.worker_id,
                "registered": registration.registered,
                "lease_ttl": registration.lease_ttl,
                "capabilities": registration.capabilities,
            },
        )
        return env.to_dict()
    except APIError as e:
        return ResponseEnvelope.error(e, trace_id=e.trace_id).to_dict()
    except Exception as e:
        logger.exception("register_worker failed")
        return ResponseEnvelope.error(
            APIError(message=str(e)), trace_id=""
        ).to_dict()
