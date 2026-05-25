"""GAP 2 — ControlPlane: the system brain.

Controls all runtime decisions at the global level.
Responsibilities:
  - Global system state management
  - Worker lifecycle orchestration
  - Health monitoring + topology
  - Reconciliation loops
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.runtime.control.system_state import SystemState, SystemPhase
from core.runtime.control.reconciler import Reconciler
from core.runtime.control.worker_orchestrator import WorkerOrchestrator
from core.runtime.control.health_monitor import HealthMonitor

logger = logging.getLogger("emo_ai.control.plane")


class ControlAction(str, Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    RECONCILE = "reconcile"
    HEALTH_CHECK = "health_check"
    SHUTDOWN = "shutdown"
    EVOLVE = "evolve"


@dataclass
class ControlDecision:
    """A decision made by the control plane."""
    action: ControlAction
    reason: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    executed: bool = False


class ControlPlane:
    """System brain — controls all runtime decisions.

    The ControlPlane runs reconciliation loops, monitors health,
    orchestrates workers, and makes global system decisions.
    """

    def __init__(
        self,
        system_state: Optional[SystemState] = None,
        reconciler: Optional[Reconciler] = None,
        worker_orchestrator: Optional[WorkerOrchestrator] = None,
        health_monitor: Optional[HealthMonitor] = None,
    ):
        self._state = system_state or SystemState()
        self._reconciler = reconciler or Reconciler()
        self._orchestrator = worker_orchestrator or WorkerOrchestrator()
        self._health = health_monitor or HealthMonitor()
        self._decision_history: List[ControlDecision] = []
        self._lock = threading.Lock()
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._loop_interval: float = 5.0

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def reconciler(self) -> Reconciler:
        return self._reconciler

    @property
    def orchestrator(self) -> WorkerOrchestrator:
        return self._orchestrator

    @property
    def health(self) -> HealthMonitor:
        return self._health

    # ── Lifecycle ──

    def start(self, interval: float = 5.0) -> None:
        """Start the control plane loop."""
        if self._running:
            return
        self._running = True
        self._loop_interval = interval
        self._loop_thread = threading.Thread(
            target=self._reconciliation_loop,
            daemon=True,
            name="control-plane",
        )
        self._loop_thread.start()
        logger.info("Control plane started (interval=%.1fs)", interval)

    def shutdown(self) -> None:
        """Stop the control plane."""
        self._running = False
        self._state.set_phase(SystemPhase.SHUTTING_DOWN)
        logger.info("Control plane shutdown")

    # ── Public API ──

    def decide(self, action: ControlAction, reason: str,
               payload: Optional[Dict[str, Any]] = None) -> ControlDecision:
        """Record and execute a control decision."""
        decision = ControlDecision(
            action=action,
            reason=reason,
            payload=payload or {},
            timestamp=time.time(),
        )
        self._decision_history.append(decision)

        try:
            self._execute_decision(decision)
            decision.executed = True
            logger.info("Control decision: %s — %s", action.value, reason)
        except Exception as e:
            logger.error("Control decision failed: %s — %s", action.value, e)

        return decision

    def decisions(self, limit: int = 20) -> List[ControlDecision]:
        """Return recent control decisions."""
        return self._decision_history[-limit:]

    # ── Internal ──

    def _reconciliation_loop(self) -> None:
        """Background loop: health check → reconcile → decide."""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error("Reconciliation tick failed: %s", e)
            time.sleep(self._loop_interval)

    def _tick(self) -> None:
        """Single reconciliation tick."""
        # Phase: HEALTH CHECK
        unhealthy = self._health.check_all()
        for svc in unhealthy:
            self.decide(
                ControlAction.HEALTH_CHECK,
                f"Service unhealthy: {svc}",
                {"service": svc},
            )

        # Phase: RECONCILE
        diffs = self._reconciler.reconcile(self._state)
        for diff in diffs:
            self.decide(
                ControlAction.RECONCILE,
                diff["reason"],
                diff,
            )

        # Phase: SCALE (based on load)
        active_workers = self._orchestrator.active_count()
        pending = self._state.get("pending_tasks", 0)
        if pending > active_workers * 2:
            self.decide(
                ControlAction.SCALE_UP,
                f"Pending tasks ({pending}) > 2x active workers ({active_workers})",
                {"pending": pending, "active": active_workers},
            )

    def _execute_decision(self, decision: ControlDecision) -> None:
        """Execute a control decision."""
        action = decision.action
        if action == ControlAction.SCALE_UP:
            count = decision.payload.get("count", 1)
            self._orchestrator.scale_up(count)
        elif action == ControlAction.SCALE_DOWN:
            count = decision.payload.get("count", 1)
            self._orchestrator.scale_down(count)
        elif action == ControlAction.SHUTDOWN:
            self._orchestrator.shutdown_all()
            self._state.set_phase(SystemPhase.SHUTTING_DOWN)
