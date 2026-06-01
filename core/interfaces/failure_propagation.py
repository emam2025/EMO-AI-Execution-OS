"""D8.2 — Failure Propagation Interfaces.

Backward-compatible layer that provides:
  - Old Protocol enums (FailureDomain, PropagationAction, DegradeMode)
  - Old data structures (PropagationRule, PROPAGATION_MATRIX)
  - Re-exported implementation (FailureMatrix, FailureMode, FailureEvent)

Source of Truth: core/runtime/services/failure_propagation.py::FailureMatrix

Ref: DEVELOPER.md §15.15a D8.2
Ref: Canon LAW 20-22
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from core.runtime.services.failure_propagation import (
    FailureEvent as FailureEvent,
    FailureMatrix as FailureMatrix,
    FailureMode as FailureMode,
)


# ── Backward-compatible enums (kept for test_service_isolation.py) ──


class FailureDomain(str, Enum):
    """The domain where a failure originates."""
    SCHEDULER = "scheduler"
    DISPATCHER = "dispatcher"
    RETRY_HANDLER = "retry_handler"
    LEASE_MANAGER = "lease_manager"
    STATE_STORE = "state_store"
    EXECUTION_CORE = "execution_core"
    EXECUTION_ENGINE = "execution_engine"


class PropagationAction(str, Enum):
    """Action to take when a failure propagates between domains."""
    RETRY = "retry"
    CANCEL = "cancel"
    RELEASE_LEASE = "release_lease"
    REASSIGN = "reassign"
    CLASSIFY = "classify"
    BACKOFF = "backoff"
    DEGRADE = "degrade"
    BUFFER = "buffer"
    CONTINUE = "continue"
    DEFER = "defer"
    RECORD = "record"
    NOTIFY = "notify"
    ROLLBACK = "rollback"
    IGNORE = "ignore"


class DegradeMode(str, Enum):
    """Degradation modes for graceful service degradation."""
    READ_ONLY = "read_only"
    CACHE_ONLY = "cache_only"
    FALLBACK = "fallback"
    DRAIN = "drain"


@dataclass
class PropagationRule:
    """A single propagation rule between domains."""
    source: FailureDomain
    target: FailureDomain
    action: PropagationAction
    escalate_after: int = 3
    degrade_mode: Optional[DegradeMode] = None
    description: str = ""


# ── Legacy propagation matrix (kept for test_service_isolation.py) ──

PROPAGATION_MATRIX: Dict[FailureDomain, List[PropagationRule]] = {
    FailureDomain.DISPATCHER: [
        PropagationRule(
            source=FailureDomain.DISPATCHER,
            target=FailureDomain.SCHEDULER,
            action=PropagationAction.RETRY,
            description="Dispatcher failure → scheduler retries the node",
        ),
        PropagationRule(
            source=FailureDomain.DISPATCHER,
            target=FailureDomain.RETRY_HANDLER,
            action=PropagationAction.CLASSIFY,
            description="Dispatcher failure → retry handler classifies error type",
        ),
        PropagationRule(
            source=FailureDomain.DISPATCHER,
            target=FailureDomain.LEASE_MANAGER,
            action=PropagationAction.RELEASE_LEASE,
            description="Dispatcher failure → lease is released for reassignment",
        ),
        PropagationRule(
            source=FailureDomain.DISPATCHER,
            target=FailureDomain.EXECUTION_CORE,
            action=PropagationAction.NOTIFY,
            description="Dispatcher failure → core is notified for analytics",
        ),
    ],
    FailureDomain.LEASE_MANAGER: [
        PropagationRule(
            source=FailureDomain.LEASE_MANAGER,
            target=FailureDomain.EXECUTION_ENGINE,
            action=PropagationAction.CANCEL,
            description="Lease expired → engine cancels the execution",
        ),
        PropagationRule(
            source=FailureDomain.LEASE_MANAGER,
            target=FailureDomain.EXECUTION_ENGINE,
            action=PropagationAction.ROLLBACK,
            description="Lease expired → engine initiates rollback of completed dependents",
        ),
        PropagationRule(
            source=FailureDomain.LEASE_MANAGER,
            target=FailureDomain.SCHEDULER,
            action=PropagationAction.REASSIGN,
            description="Lease expired → scheduler reassigns to another worker",
        ),
        PropagationRule(
            source=FailureDomain.LEASE_MANAGER,
            target=FailureDomain.STATE_STORE,
            action=PropagationAction.RECORD,
            description="Lease expired → state store records the failure",
        ),
    ],
    FailureDomain.STATE_STORE: [
        PropagationRule(
            source=FailureDomain.STATE_STORE,
            target=FailureDomain.EXECUTION_CORE,
            action=PropagationAction.DEGRADE,
            degrade_mode=DegradeMode.CACHE_ONLY,
            description="State store failure → core enters cache-only degraded mode",
        ),
        PropagationRule(
            source=FailureDomain.STATE_STORE,
            target=FailureDomain.SCHEDULER,
            action=PropagationAction.BUFFER,
            description="State store failure → scheduler buffers state updates",
        ),
        PropagationRule(
            source=FailureDomain.STATE_STORE,
            target=FailureDomain.SCHEDULER,
            action=PropagationAction.CONTINUE,
            description="State store failure → scheduler continues execution without persistence",
        ),
        PropagationRule(
            source=FailureDomain.STATE_STORE,
            target=FailureDomain.RETRY_HANDLER,
            action=PropagationAction.DEFER,
            description="State store failure → retry handler defers analytics recording",
        ),
    ],
    FailureDomain.RETRY_HANDLER: [
        PropagationRule(
            source=FailureDomain.RETRY_HANDLER,
            target=FailureDomain.SCHEDULER,
            action=PropagationAction.CONTINUE,
            description="Retry handler failure → scheduler continues without retry analytics",
        ),
    ],
    FailureDomain.SCHEDULER: [
        PropagationRule(
            source=FailureDomain.SCHEDULER,
            target=FailureDomain.EXECUTION_ENGINE,
            action=PropagationAction.CANCEL,
            description="Scheduler failure → engine cancels the entire execution",
        ),
        PropagationRule(
            source=FailureDomain.SCHEDULER,
            target=FailureDomain.EXECUTION_CORE,
            action=PropagationAction.NOTIFY,
            description="Scheduler failure → core is notified",
        ),
    ],
}


class FailurePropagationPolicy(FailureMatrix):
    """Backward-compatible alias for FailureMatrix.

    FailurePropagationPolicy was the original interface name before D8
    contract alignment. It now extends FailureMatrix directly so that
    all existing code continues to work without changes.
    """


__all__ = [
    "FailureDomain",
    "FailureEvent",
    "FailureMatrix",
    "FailureMode",
    "FailurePropagationPolicy",
    "PropagationAction",
    "DegradeMode",
    "PropagationRule",
    "PROPAGATION_MATRIX",
]
