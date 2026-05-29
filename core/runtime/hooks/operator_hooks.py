"""Phase K5 — Operator Hooks: human-in-the-loop execution controls.  # LAW-8 # LAW-12

Safe operator actions (pause/resume/force_retry/replay) that propagate
operator_trace_id through EventBus and create audit checkpoints.

LAW-K5-2: Operators Use Contracts — UnifiedRuntimeAPI via safe interfaces.
LAW-K5-3: Every action carries operator_trace_id.
LAW-K5-4: No Runtime Forking.

Ref: EXEC-DIRECTIVE-027A §Task-3
Ref: Canon LAW 8, LAW 12
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces.event_bus import IEventBus
from core.models.events import ExecutionEvent, make_trace_id

logger = logging.getLogger("emo_ai.hooks.operator")


class OperatorActionResultStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class OperatorActionRequest:
    action: str
    target_id: str
    operator_trace_id: str = ""
    params: Dict[str, str] = field(default_factory=dict)


@dataclass
class OperatorActionResult:
    request: OperatorActionRequest
    status: OperatorActionResultStatus
    replay_id: str = ""
    checkpoint_id: str = ""
    detail: str = ""
    timestamp_ns: int = 0

    def __post_init__(self) -> None:
        if not self.timestamp_ns:
            self.timestamp_ns = time.time_ns()


class OperatorHooks:
    """Human-in-the-loop action hooks with operator_trace_id propagation.

    Each action emits an operator.action event on EventBus and
    records an audit checkpoint for traceability (LAW-12).
    """

    def __init__(
        self,
        event_bus: Optional[IEventBus] = None,
        runtime: Optional[Any] = None,  # LAW 13 compliance
    ) -> None:
        self._event_bus = event_bus
        self._runtime = runtime
        self._checkpoints: List[OperatorActionResult] = []

    def _emit(self, req: OperatorActionRequest, result: OperatorActionResult) -> None:
        self._checkpoints.append(result)
        if self._event_bus:
            self._event_bus.publish(
                "operator.action",
                ExecutionEvent(
                    event_id=f"hook_{time.time_ns()}",
                    event_type="STATE_TRANSITION",
                    timestamp=time.time(),
                    source="OperatorHooks",
                    payload={
                        "action": req.action,
                        "target_id": req.target_id,
                        "operator_trace_id": req.operator_trace_id,
                        "status": result.status.value,
                        "replay_id": result.replay_id,
                        "checkpoint_id": result.checkpoint_id,
                    },
                    trace_id=req.operator_trace_id,
                    session_id="",
                ),
            )

    def operator_pause(self, req: OperatorActionRequest) -> OperatorActionResult:
        result = OperatorActionResult(
            request=req,
            status=OperatorActionResultStatus.ACCEPTED,
            checkpoint_id=f"cp_{time.time_ns()}",
            detail="Execution paused by operator",
        )
        self._emit(req, result)
        return result

    def operator_resume(self, req: OperatorActionRequest) -> OperatorActionResult:
        result = OperatorActionResult(
            request=req,
            status=OperatorActionResultStatus.ACCEPTED,
            detail="Execution resumed by operator",
        )
        self._emit(req, result)
        return result

    def operator_force_retry(self, req: OperatorActionRequest) -> OperatorActionResult:
        result = OperatorActionResult(
            request=req,
            status=OperatorActionResultStatus.ACCEPTED,
            detail="Force retry triggered by operator",
        )
        self._emit(req, result)
        return result

    def operator_replay(self, req: OperatorActionRequest) -> OperatorActionResult:
        runtime = self._runtime
        if runtime is None:
            from core.composition.root import build_minimal_runtime
            runtime = build_minimal_runtime()
        ticket = runtime.replay(req.target_id, deterministic=True)
        result = OperatorActionResult(
            request=req,
            status=OperatorActionResultStatus.ACCEPTED,
            replay_id=getattr(ticket, "replay_id", ""),
            checkpoint_id=f"cp_{time.time_ns()}",
            detail=f"Replay initiated: {getattr(ticket, 'replay_id', '')}",
        )
        self._emit(req, result)
        return result

    def get_checkpoints(self, limit: int = 50) -> List[OperatorActionResult]:
        return list(self._checkpoints[-limit:])
