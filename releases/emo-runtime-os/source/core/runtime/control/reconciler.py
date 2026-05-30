"""GAP 2 — Reconciler: desired vs actual state reconciliation.

Compares the desired system state with actual runtime state
and produces a list of actions to close the gap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.runtime.control.system_state import SystemState, SystemPhase

logger = logging.getLogger("emo_ai.control.reconciler")


@dataclass
class DesiredState:
    """The desired target state for the system."""
    min_workers: int = 2
    max_workers: int = 10
    target_phase: SystemPhase = SystemPhase.ACTIVE
    max_pending_tasks: int = 50
    max_failure_rate: float = 0.1


class Reconciler:
    """Compares desired vs actual state and produces diff actions.

    Runs as part of the control plane tick cycle.
    """

    def __init__(self, desired: Optional[DesiredState] = None):
        self._desired = desired or DesiredState()

    @property
    def desired(self) -> DesiredState:
        return self._desired

    def reconcile(self, actual: SystemState) -> List[Dict[str, Any]]:
        """Compare desired vs actual state.

        Returns a list of diff actions (empty = no action needed).
        """
        diffs: List[Dict[str, Any]] = []
        snap = actual.snapshot()

        # Worker count
        if snap["workers"] < self._desired.min_workers:
            diffs.append({
                "reason": f"Workers ({snap['workers']}) below min ({self._desired.min_workers})",
                "field": "workers",
                "actual": snap["workers"],
                "desired": self._desired.min_workers,
                "action": "scale_up",
                "count": self._desired.min_workers - snap["workers"],
            })
        elif snap["workers"] > self._desired.max_workers:
            diffs.append({
                "reason": f"Workers ({snap['workers']}) above max ({self._desired.max_workers})",
                "field": "workers",
                "actual": snap["workers"],
                "desired": self._desired.max_workers,
                "action": "scale_down",
                "count": snap["workers"] - self._desired.max_workers,
            })

        # Pending tasks
        if snap["pending_tasks"] > self._desired.max_pending_tasks:
            diffs.append({
                "reason": f"Pending tasks ({snap['pending_tasks']}) above max ({self._desired.max_pending_tasks})",
                "field": "pending_tasks",
                "actual": snap["pending_tasks"],
                "desired": self._desired.max_pending_tasks,
                "action": "scale_up",
                "count": 1,
            })

        # Failure rate
        total = snap["completed_executions"] + snap["failed_executions"]
        if total > 0:
            failure_rate = snap["failed_executions"] / total
            if failure_rate > self._desired.max_failure_rate:
                diffs.append({
                    "reason": f"Failure rate ({failure_rate:.3f}) exceeds max ({self._desired.max_failure_rate})",
                    "field": "failure_rate",
                    "actual": failure_rate,
                    "desired": self._desired.max_failure_rate,
                    "action": "investigate",
                })

        if diffs:
            logger.info("Reconciliation: %d diffs found", len(diffs))

        return diffs
