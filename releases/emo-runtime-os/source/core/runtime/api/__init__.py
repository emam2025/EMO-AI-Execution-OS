"""F1 — Unified Runtime API layer.

Exports UnifiedRuntime (IUnifiedRuntimeAPI concrete implementation),
RuntimeStateMachine, TransitionGuard, EventPublisher, and all types from
the F1 protocol (ExecutionTicket, ReplayTicket, etc.).

Ref: DEVELOPER.md §15.2
Ref: Canon LAW 13, RULE 1
"""

from core.runtime.api.unified_runtime_api import UnifiedRuntime
from core.runtime.api.state_machine import (
    RuntimeState,
    RuntimeStateMachine,
    TransitionGuard,
    TERMINAL_STATES,
)
from core.runtime.api.event_publisher import EventPublisher

# F1 protocol types (re-exported from design protocol)
from core.runtime.api.unified_runtime_api import (
    ExecutionTicket,
    ReplayTicket,
    CancellationReceipt,
    ScalingReceipt,
    WorkerRegistration,
    LiveStateStream,
    ExecutionStatus,
    SubmissionOptions,
    ExecutionContext,
    ScalingPolicy,
)

__all__ = [
    "UnifiedRuntime",
    "RuntimeState",
    "RuntimeStateMachine",
    "TransitionGuard",
    "EventPublisher",
    "TERMINAL_STATES",
    "ExecutionTicket",
    "ReplayTicket",
    "CancellationReceipt",
    "ScalingReceipt",
    "WorkerRegistration",
    "LiveStateStream",
    "ExecutionStatus",
    "SubmissionOptions",
    "ExecutionContext",
    "ScalingPolicy",
]
