"""D8.2 — Failure Propagation Interfaces.

Backward-compatible layer that provides:
  - Old Protocol enums (FailureDomain, PropagationAction, DegradeMode)
  - Old data structures (PropagationRule, PROPAGATION_MATRIX)
  - Re-exported types (FailureMatrix, FailureMode, FailureEvent)

Source of Truth: core/runtime/services/failure_propagation.py::FailureMatrix

Ref: DEVELOPER.md §15.15a D8.2
Ref: Canon LAW 20-22
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol

if TYPE_CHECKING:
    from core.runtime.services.failure_propagation import (
        FailureEvent as FailureEvent,
        FailureMatrix as FailureMatrix,
        FailureMode as FailureMode,
    )


class FailureMatrix:
    """Runtime stub for backward compatibility.

    The real implementation lives in core/runtime/services/failure_propagation.py.
    This stub exists so that existing imports like
    `from core.interfaces.failure_propagation import FailureMatrix`
    continue to work at runtime. Type checkers will use the
    TYPE_CHECKING import above for proper type information.
    """

    def evaluate(self, source: FailureDomain, context: dict | None = None) -> list[PropagationRule]:
        return PROPAGATION_MATRIX.get(source, [])

    def apply(self, domain: str) -> list[str]:
        if domain not in _STRING_MATRIX:
            raise KeyError(f"Unknown failure domain: {domain}")
        return list(_STRING_MATRIX[domain])

    def should_retry(self, source: FailureDomain, fail_count: int) -> bool:
        rules = self.evaluate(source)
        for r in rules:
            if r.action == PropagationAction.RETRY:
                return fail_count < r.escalate_after
        return False

    def degrade_mode(self, source: FailureDomain) -> DegradeMode | None:
        rules = self.evaluate(source)
        for r in rules:
            if r.action == PropagationAction.DEGRADE:
                return r.degrade_mode
        return None


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


# String-based matrix matching runtime format (keys are PascalCase strings)
_STRING_MATRIX: Dict[str, List[str]] = {
    "Dispatcher": ["RETRY", "CLASSIFY", "RELEASE", "NOTIFY"],
    "LeaseManager": ["CANCEL", "ROLLBACK", "REASSIGN", "RECORD"],
    "StateStore": ["DEGRADE", "BUFFER", "CONTINUE", "DEFER"],
    "Scheduler": ["FAIL_FAST", "RECORD", "NOTIFY"],
    "RetryHandler": ["FAIL_FAST", "RELEASE", "RECORD", "NOTIFY"],
    "Engine": ["CANCEL", "RELEASE", "RECORD", "NOTIFY"],
    "Core": ["CLASSIFY", "RETRY", "RELEASE", "RECORD"],
}


class FailurePropagationPolicy:
    """Backward-compatible interface for failure propagation.

    Provides a minimal implementation using the local PROPAGATION_MATRIX.
    The full implementation lives in core/runtime/services/failure_propagation.py.
    """

    def evaluate(
        self,
        source: FailureDomain,
        context: Optional[Dict] = None,
    ) -> List[PropagationRule]:
        """Return all propagation rules for a given failure source."""
        return PROPAGATION_MATRIX.get(source, [])

    def apply(self, domain: str) -> List[str]:
        """Apply failure propagation for a domain name (case-insensitive).

        Returns list of action code strings matching the runtime format.
        """
        if domain not in _STRING_MATRIX:
            raise KeyError(f"Unknown failure domain: {domain}")
        return list(_STRING_MATRIX[domain])

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

    def get_all_scenarios(self) -> List[Dict]:
        """Return all F01-F08 scenarios for test verification."""
        _SCENARIO_MAP = {
            "Dispatcher": ("F01", "dispatch_tool_call raises DispatchError or timeout", ["Scheduler", "RetryHandler", "LeaseManager", "Core"]),
            "LeaseManager": ("F02", "monitor_heartbeat returns False or lease TTL expired", ["Engine", "Scheduler", "StateStore"]),
            "StateStore": ("F03", "save_state or store_checkpoint raises PersistenceError", ["Core", "Scheduler", "RetryHandler"]),
            "Scheduler": ("F04", "schedule() raises SchedulingError (cycle, invalid deps)", ["Dispatcher", "Engine"]),
            "RetryHandler": ("F05", "decide_retry raises RetryDecisionError or max_attempts exhausted", ["Dispatcher", "LeaseManager", "StateStore"]),
            "Engine": ("F06", "cancel() called during execute()", ["Scheduler", "LeaseManager", "StateStore"]),
            "LeaseManager_acquire": ("F07", "acquire_lease returns None or raises LeaseError", ["Scheduler", "Dispatcher"]),
            "Core": ("F08", "Node tool execution raises unhandled Exception", ["RetryHandler", "Dispatcher", "StateStore"]),
        }
        return [
            {
                "scenario_id": sid,
                "source_domain": domain,
                "failure": failure,
                "effect_on": list(effect_on),
                "action": list(_STRING_MATRIX.get(domain, [])),
            }
            for domain, (sid, failure, effect_on) in _SCENARIO_MAP.items()
        ]


__all__ = [
    "FailureDomain",
    "FailurePropagationPolicy",
    "PropagationAction",
    "DegradeMode",
    "PropagationRule",
    "PROPAGATION_MATRIX",
]
