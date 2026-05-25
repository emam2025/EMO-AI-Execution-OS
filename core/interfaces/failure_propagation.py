"""D8.2 — Failure Propagation Policy: formal cross-service failure model.

Defines what happens when each service domain fails —
how failures propagate to other domains and what recovery
actions are taken.

Failure Propagation Matrix::

    Source Domain     │ Effect On              │ Action
    ──────────────────┼────────────────────────┼───────────
    Dispatcher fails  │ Scheduler              → RETRY
                      │ RetryHandler           → CLASSIFY + BACKOFF
                      │ LeaseManager           → RELEASE
                      │ ExecutionCore          → NOTIFY
    ──────────────────┼────────────────────────┼───────────
    Lease expires     │ ExecutionEngine        → CANCEL + ROLLBACK
                      │ Scheduler              → REASSIGN
                      │ StateStore             → RECORD
    ──────────────────┼────────────────────────┼───────────
    StateStore fails  │ ExecutionCore          → DEGRADE
                      │ Scheduler              → BUFFER + CONTINUE
                      │ RetryHandler           → DEFER
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


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


# ── The authoritative propagation matrix ──

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


class FailurePropagationPolicy:
    """Evaluates failure propagation decisions.

    Usage::

        policy = FailurePropagationPolicy()
        actions = policy.evaluate(
            source=FailureDomain.DISPATCHER,
            context={"retry_count": 2},
        )
    """

    def evaluate(
        self,
        source: FailureDomain,
        context: Optional[Dict] = None,
    ) -> List[PropagationRule]:
        """Return all propagation rules for a given failure source."""
        return PROPAGATION_MATRIX.get(source, [])

    def should_retry(
        self,
        source: FailureDomain,
        fail_count: int,
    ) -> bool:
        """Determine whether a retry should be attempted."""
        rules = self.evaluate(source)
        for r in rules:
            if r.action == PropagationAction.RETRY:
                return fail_count < r.escalate_after
        return False

    def degrade_mode(
        self,
        source: FailureDomain,
    ) -> Optional[DegradeMode]:
        """Return the degrade mode for a failure, if any."""
        rules = self.evaluate(source)
        for r in rules:
            if r.action == PropagationAction.DEGRADE:
                return r.degrade_mode
        return None
