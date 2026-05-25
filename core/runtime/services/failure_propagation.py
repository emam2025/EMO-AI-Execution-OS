"""D8.2 — Failure Propagation Matrix.

Implements the failure propagation matrix from artifacts/design/d8/
02_failure_propagation_matrix.json.

Enforces LAW 20-22: Every service MUST have a defined failure propagation policy.
All failure events are published to EventBus.

Ref: DEVELOPER.md §15.15a D8.2
Ref: Canon LAW 20-22
Ref: Canon LAW 23-27
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.services.failure_propagation")


class FailureMode(str, Enum):
    """Failure handling strategies for service interaction failures.

    Ref: DEVELOPER.md §15.15a D8.2
    Ref: Canon LAW 20-22
    """
    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_BREAK = "circuit_break"
    FAIL_FAST = "fail_fast"
    DEGRADE = "degrade"
    BUFFER = "buffer"
    CONTINUE = "continue"
    DEFER = "defer"
    CANCEL = "cancel"
    ROLLBACK = "rollback"
    REASSIGN = "reassign"
    RECORD = "record"
    CLASSIFY = "classify"
    NOTIFY = "notify"
    RELEASE = "release"


@dataclass
class FailureEvent:
    """Immutable failure event for EventBus publication.

    LAW 20-22: All failures MUST be published to EventBus.
    """
    source_domain: str
    scenario_id: str
    failure: str
    action_sequence: List[str]
    timestamp: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = time.time()


class FailureMatrix:
    """Failure propagation matrix — maps source domain failures to action sequences.

    Based on F01-F08 scenarios from the D8.2 design.
    LAW 20-22: Every source domain MUST have a defined propagation policy.

    Ref: DEVELOPER.md §15.15a D8.2
    Ref: Canon LAW 20-22
    """

    # F01-F08 scenarios: source_domain → action_sequence
    _MATRIX: Dict[str, Dict[str, Any]] = {
        "Dispatcher": {
            "scenario_id": "F01",
            "failure": "dispatch_tool_call raises DispatchError or timeout",
            "effect_on": ["Scheduler", "RetryHandler", "LeaseManager", "Core"],
            "action": ["RETRY", "CLASSIFY", "RELEASE", "NOTIFY"],
            "consistency": "strong",
            "failure_mode": FailureMode.RETRY,
            "fallback": "FAIL_FAST after max_attempts",
            "can_retry": True,
        },
        "LeaseManager": {
            "scenario_id": "F02",
            "failure": "monitor_heartbeat returns False or lease TTL expired",
            "effect_on": ["Engine", "Scheduler", "StateStore"],
            "action": ["CANCEL", "ROLLBACK", "REASSIGN", "RECORD"],
            "consistency": "strong",
            "failure_mode": FailureMode.CIRCUIT_BREAK,
            "fallback": "FAIL_FAST",
            "can_retry": False,
        },
        "StateStore": {
            "scenario_id": "F03",
            "failure": "save_state or store_checkpoint raises PersistenceError",
            "effect_on": ["Core", "Scheduler", "RetryHandler"],
            "action": ["DEGRADE", "BUFFER", "CONTINUE", "DEFER"],
            "consistency": "eventual",
            "failure_mode": FailureMode.FALLBACK,
            "fallback": "BUFFER + CONTINUE",
            "can_retry": True,
        },
        "Scheduler": {
            "scenario_id": "F04",
            "failure": "schedule() raises SchedulingError (cycle, invalid deps)",
            "effect_on": ["Dispatcher", "Engine"],
            "action": ["FAIL_FAST", "RECORD", "NOTIFY"],
            "consistency": "strong",
            "failure_mode": FailureMode.FAIL_FAST,
            "fallback": "FAIL_FAST",
            "can_retry": False,
        },
        "RetryHandler": {
            "scenario_id": "F05",
            "failure": "decide_retry raises RetryDecisionError or max_attempts exhausted",
            "effect_on": ["Dispatcher", "LeaseManager", "StateStore"],
            "action": ["FAIL_FAST", "RELEASE", "RECORD", "NOTIFY"],
            "consistency": "strong",
            "failure_mode": FailureMode.CIRCUIT_BREAK,
            "fallback": "FAIL_FAST",
            "can_retry": False,
        },
        "Engine": {
            "scenario_id": "F06",
            "failure": "cancel() called during execute()",
            "effect_on": ["Scheduler", "LeaseManager", "StateStore"],
            "action": ["CANCEL", "RELEASE", "RECORD", "NOTIFY"],
            "consistency": "strong",
            "failure_mode": FailureMode.CANCEL,
            "fallback": "ROLLBACK",
            "can_retry": False,
        },
        "LeaseManager_acquire": {
            "scenario_id": "F07",
            "failure": "acquire_lease returns None or raises LeaseError",
            "effect_on": ["Scheduler", "Dispatcher"],
            "action": ["DEFER", "NOTIFY"],
            "consistency": "eventual",
            "failure_mode": FailureMode.FALLBACK,
            "fallback": "DEFER + RETRY",
            "can_retry": True,
        },
        "Core": {
            "scenario_id": "F08",
            "failure": "Node tool execution raises unhandled Exception",
            "effect_on": ["RetryHandler", "Dispatcher", "StateStore"],
            "action": ["CLASSIFY", "RETRY", "RELEASE", "RECORD"],
            "consistency": "strong",
            "failure_mode": FailureMode.RETRY,
            "fallback": "FAIL_FAST after max_attempts",
            "can_retry": True,
        },
    }

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._circuit_breakers: Dict[str, int] = {}
        self._failure_counts: Dict[str, int] = {}

    def apply(self, source_domain: str) -> List[str]:
        """Get the action sequence for a source domain failure.

        LAW 20-22: Returns the canonical action sequence for the failure.
        All failures are logged and published to EventBus.

        Args:
            source_domain: The service domain where the failure originated.

        Returns:
            List of FailureMode action codes to execute.

        Raises:
            KeyError: If source_domain has no defined propagation policy.
        """
        entry = self._MATRIX.get(source_domain)
        if entry is None:
            raise KeyError(
                f"LAW 20-22 VIOLATION: No propagation policy for '{source_domain}'. "
                f"Every source domain MUST have a defined failure propagation policy."
            )

        actions = list(entry["action"])
        self._failure_counts[source_domain] = self._failure_counts.get(source_domain, 0) + 1

        # Circuit breaker: if threshold > 0 and failure count exceeds it,
        # override to FAIL_FAST. Threshold of 0 means "no circuit breaker".
        cb_threshold = self._get_circuit_break_after(source_domain)
        cb_count = self._circuit_breakers.get(source_domain, 0)
        if cb_threshold > 0 and cb_count >= cb_threshold:
            actions = ["FAIL_FAST", "RECORD", "NOTIFY"]

        # Publish to EventBus (LAW 20-22: All failures MUST be published)
        self._publish_event(source_domain, entry, actions)

        logger.debug(
            "Failure matrix applied for %s: %s (circuit=%d/%d)",
            source_domain, actions, cb_count, cb_threshold,
        )
        return actions

    def record_circuit_break(self, source_domain: str) -> None:
        """Record a circuit break event for a source domain.

        Opens the circuit after consecutive failures exceeding threshold.
        """
        self._circuit_breakers[source_domain] = (
            self._circuit_breakers.get(source_domain, 0) + 1
        )

    def reset_circuit_breaker(self, source_domain: str) -> None:
        """Reset the circuit breaker for a source domain."""
        self._circuit_breakers.pop(source_domain, None)
        self._failure_counts.pop(source_domain, None)

    def get_all_scenarios(self) -> List[Dict[str, Any]]:
        """Return all F01-F08 scenarios for test verification."""
        return [
            {
                "scenario_id": entry["scenario_id"],
                "source_domain": domain,
                "failure": entry["failure"],
                "effect_on": list(entry["effect_on"]),
                "action": list(entry["action"]),
            }
            for domain, entry in self._MATRIX.items()
        ]

    def _publish_event(
        self,
        source_domain: str,
        entry: Dict[str, Any],
        actions: List[str],
    ) -> None:
        """Publish failure event to EventBus (if available)."""
        event = FailureEvent(
            source_domain=source_domain,
            scenario_id=entry["scenario_id"],
            failure=entry["failure"],
            action_sequence=actions,
            payload={
                "effect_on": entry["effect_on"],
                "consistency": entry["consistency"],
                "failure_mode": entry["failure_mode"].value,
            },
        )
        if self._event_bus is not None and hasattr(self._event_bus, "emit"):
            try:
                self._event_bus.emit(
                    "runtime.failure." + source_domain.lower(),
                    event,
                )
            except Exception:
                logger.exception("Failed to publish failure event to EventBus")

    @staticmethod
    def _get_circuit_break_after(source_domain: str) -> int:
        """Get the circuit break threshold for a source domain."""
        thresholds = {
            "Dispatcher": 3,
            "LeaseManager": 1,
            "StateStore": 0,
            "Scheduler": 1,
            "RetryHandler": 3,
            "Engine": 0,
            "LeaseManager_acquire": 5,
            "Core": 3,
        }
        return thresholds.get(source_domain, 3)
