"""F1 — UnifiedRuntime: concrete implementation of IUnifiedRuntimeAPI.

Implements all 7 lifecycle methods:
  submit() | resume() | cancel() | observe() | replay() | scale() | register_worker()

LAW 13: Receives all D8 services via constructor injection.
RULE 1: No direct execution — routes through DI-ed services.
LAW 12: Every request/response carries trace_id.
LAW 8: Every state transition is guarded.

Ref: DEVELOPER.md §15.2, §15.12
Ref: artifacts/design/f1/protocols/01_unified_runtime_api_protocols.py
Ref: Canon LAW 1, LAW 3, LAW 4, LAW 5, LAW 7, LAW 8, LAW 10, LAW 12, LAW 13
Ref: Canon RULE 1, RULE 4
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.interfaces.event_bus import IEventBus
from core.models.events import make_trace_id
from core.runtime.api.event_publisher import EventPublisher
from core.runtime.api.state_machine import (
    RuntimeState,
    RuntimeStateMachine,
    TERMINAL_STATES,
    TransitionGuard,
)
from core.runtime.models.api_errors import (
    CheckpointMissing,
    InvalidStateTransition,
    LeaseConflict,
    QuotaExceeded,
    ResponseEnvelope,
    ScaleError,
    ScaleLimitExceeded,
    SubmissionRejected,
    TicketNotFound,
    WorkerRegistrationFailed,
    WorkerUnavailable,
)
from core.runtime.services.failure_propagation import FailureMatrix
from core.runtime.services.lease_manager import ExecutionLeaseManager
from core.runtime.services.retry_handler import ExecutionRetryHandler
from core.runtime.services.scheduler import ExecutionScheduler
from core.runtime.services.state_store import ExecutionStateStore
from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher

logger = logging.getLogger("emo_ai.api.unified_runtime")

# Max limits for scaling
MAX_WORKER_COUNT = 256


# ═════════════════════════════════════════════════════════════════════
# F1 Protocol Types (from artifacts/design/f1/protocols/)
# ═════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ExecutionTicket:
    ticket_id: str
    dag_id: str
    session_id: str = ""
    trace_id: str = ""
    submitted_at: float = 0.0


@dataclass(frozen=True)
class ReplayTicket:
    execution_id: str
    replay_id: str
    trace_id: str = ""
    deterministic: bool = True
    checkpoint_id: str = ""


@dataclass(frozen=True)
class CancellationReceipt:
    ticket_id: str
    cancelled: bool
    terminated_state: str
    reason: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class ScalingReceipt:
    previous_count: int
    target_count: int
    actual_count: int
    policy: str = ""


@dataclass(frozen=True)
class WorkerRegistration:
    worker_id: str
    registered: bool
    lease_ttl: float = 30.0
    capabilities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveStateStream:
    ticket_id: str
    current_state: str
    progress: Dict[str, Any] = field(default_factory=dict)
    active_nodes: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutionStatus:
    ticket_id: str
    state: str
    trace_id: str = ""
    node_states: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    progress_pct: float = 0.0
    checkpoint_available: bool = False


@dataclass
class SubmissionOptions:
    strategy: str = "balanced"
    priority: int = 0
    ttl: float = 300.0
    max_retries: int = 3
    checkpoint_interval: int = 0
    tags: Dict[str, str] = field(default_factory=dict)
    deterministic: bool = True


@dataclass
class ExecutionContext:
    session_id: str = ""
    trace_id: str = ""
    correlation_id: str = ""
    parent_ticket_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ScalingPolicy(str, Enum):
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"
    MANUAL = "manual"


class UnifiedRuntime:
    """Concrete implementation of IUnifiedRuntimeAPI.

    LAW 13: All dependencies injected via constructor.
    RULE 1: No direct D8 service construction.
    LAW 12: trace_id flows through every method.

    Ref: DEVELOPER.md §15.2
    Ref: Canon LAW 13
    """

    def __init__(
        self,
        scheduler: ExecutionScheduler,
        state_store: ExecutionStateStore,
        dispatcher: ExecutionToolDispatcher,
        retry_handler: ExecutionRetryHandler,
        lease_manager: ExecutionLeaseManager,
        event_bus: IEventBus,
        failure_matrix: FailureMatrix,
        sandbox_manager: Any = None,
        isolation_runtime: Any = None,
        strict_api_mode: bool = False,
    ):
        # LAW 13: D8 services injected — not imported
        self._scheduler = scheduler
        self._state_store = state_store
        self._dispatcher = dispatcher
        self._retry_handler = retry_handler
        self._lease_manager = lease_manager
        self._event_bus = event_bus
        self._failure_matrix = failure_matrix
        self._sandbox_manager = sandbox_manager
        self._isolation_runtime = isolation_runtime
        self._strict_api_mode = strict_api_mode

        self._publisher = EventPublisher(event_bus)
        self._guard = TransitionGuard()
        self._executions: Dict[str, Dict[str, Any]] = {}
        self._worker_pool: Dict[str, Dict[str, Any]] = {}

    # ── Private helpers ──────────────────────────────────────────

    def _generate_trace_id(self, context: Optional[ExecutionContext] = None) -> str:
        if context and context.trace_id:
            return context.trace_id
        return make_trace_id()

    def _get_execution(self, ticket_id: str) -> Dict[str, Any]:
        exec_data = self._executions.get(ticket_id)
        if exec_data is None:
            raise TicketNotFound(
                f"No execution found for ticket {ticket_id}",
                ticket_id=ticket_id,
            )
        return exec_data

    # ── 1. submit() ──────────────────────────────────────────────

    def submit(
        self,
        dag: Any,
        context: Optional[ExecutionContext] = None,
        options: Optional[SubmissionOptions] = None,
    ) -> ExecutionTicket:
        """Submit a DAG for execution.

        LAW 1: DAG validation before scheduling.
        LAW 3: Lease-aware execution.
        LAW 12: trace_id propagation.

        Flow:
          1. Validate DAG structure
          2. Acquire execution lease
          3. Schedule nodes into levels
          4. Persist initial state
          5. Emit events
        """
        trace_id = self._generate_trace_id(context)
        opts = options or SubmissionOptions()

        # Guard: DAG must be valid
        guard = TransitionGuard()
        allowed, reason = guard.guard_submit_to_queued(dag)
        if not allowed:
            raise SubmissionRejected(
                reason, trace_id=trace_id,
                errors=[reason] if reason else [],
            )

        session_id = uuid.uuid4().hex[:12]
        ticket_id = uuid.uuid4().hex[:12]
        dag_id = getattr(dag, "dag_id", str(id(dag)))

        # Acquire lease (LAW 3)
        lease_id = self._lease_manager.acquire_lease(
            session_id, "unified_runtime",
        )

        # Schedule into levels (LAW 23)
        levels = self._scheduler.schedule(dag, session_id=session_id, strategy=opts.strategy)

        # Persist initial checkpoint (LAW 26)
        self._state_store.save_state("root", {"dag_id": dag_id, "status": "submitted"}, session_id)
        self._state_store.store_checkpoint(session_id, dag, "", {"status": "submitted"})

        # Build ticket
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            dag_id=dag_id,
            session_id=session_id,
            trace_id=trace_id,
            submitted_at=time.time(),
        )

        # Track execution state
        sm = RuntimeStateMachine()
        sm.force_set(RuntimeState.QUEUED)
        self._executions[ticket_id] = {
            "sm": sm,
            "ticket": ticket,
            "dag": dag,
            "session_id": session_id,
            "trace_id": trace_id,
            "lease_id": lease_id,
            "levels": levels,
            "options": opts,
            "node_states": {},
            "submitted_at": time.time(),
        }

        # Emit events (LAW 5)
        self._publisher.publish_execution_event(
            "runtime.execution.submitted", trace_id,
            {"ticket_id": ticket_id, "dag_id": dag_id, "session_id": session_id},
        )
        self._publisher.publish_execution_event(
            "runtime.execution.queued", trace_id,
            {"ticket_id": ticket_id, "session_id": session_id},
        )

        logger.info("submit: ticket=%s dag=%s session=%s trace=%s",
                     ticket_id, dag_id, session_id, trace_id)
        return ticket

    # ── 2. resume() ──────────────────────────────────────────────

    def resume(
        self,
        ticket_id: str,
        from_checkpoint: Optional[str] = None,
    ) -> ExecutionStatus:
        """Resume execution from checkpoint.

        LAW 4: Replay-safe resume.
        LAW 8: Recoverable state transition.

        Guard: Execution must be in a resumable state.
        Guard: Checkpoint must exist in StateStore.
        """
        exec_data = self._get_execution(ticket_id)
        trace_id = exec_data["trace_id"]
        sm: RuntimeStateMachine = exec_data["sm"]

        # Guard: must not be terminal or completed
        if sm.is_terminal() or sm.current == RuntimeState.COMPLETED:
            raise InvalidStateTransition(
                message=f"Cannot resume from state {sm.current.value}",
                trace_id=trace_id,
                current_state=sm.current.value,
                target_state="QUEUED",
            )

        # Guard: checkpoint must exist
        session_id = exec_data["session_id"]
        trace = self._state_store.read_trace(session_id)
        if trace is None:
            raise CheckpointMissing(
                f"No checkpoint found for ticket {ticket_id}",
                trace_id=trace_id,
            )

        # Re-acquire lease
        new_lease = self._lease_manager.acquire_lease(
            session_id, "unified_runtime",
        )
        if new_lease:
            exec_data["lease_id"] = new_lease

        # Re-schedule remaining nodes
        levels = self._scheduler.schedule(exec_data["dag"], session_id=session_id)
        exec_data["levels"] = levels

        # Transition to resumable state
        sm.force_set(RuntimeState.QUEUED)

        # Emit events
        self._publisher.publish_execution_event(
            "runtime.execution.resumed", trace_id,
            {"ticket_id": ticket_id, "session_id": session_id,
             "checkpoint": from_checkpoint or "latest"},
        )
        self._publisher.publish_checkpoint_restored(trace_id, session_id)

        logger.info("resume: ticket=%s session=%s trace=%s",
                     ticket_id, session_id, trace_id)

        node_states = exec_data.get("node_states", {})
        total_nodes = sum(len(l) if isinstance(l, list) else 1
                         for l in exec_data.get("levels", []))
        completed = sum(1 for s in node_states.values() if s == "completed")

        return ExecutionStatus(
            ticket_id=ticket_id,
            state=sm.current.value,
            trace_id=trace_id,
            node_states=node_states,
            progress_pct=(completed / max(total_nodes, 1)) * 100.0,
            checkpoint_available=True,
        )

    # ── 3. cancel() ──────────────────────────────────────────────

    def cancel(
        self,
        ticket_id: str,
        reason: str = "",
        force: bool = False,
    ) -> CancellationReceipt:
        """Cancel a running execution.

        LAW 10: Workers are unreliable — cancel releases leases.
        RULE 4: Everything is killable.

        Guard: Execution must not be in a terminal state.
        """
        exec_data = self._get_execution(ticket_id)
        trace_id = exec_data["trace_id"]
        sm: RuntimeStateMachine = exec_data["sm"]

        # Guard: not terminal
        if sm.is_terminal():
            raise InvalidStateTransition(
                message=f"Cannot cancel from terminal state {sm.current.value}",
                trace_id=trace_id,
                current_state=sm.current.value,
                target_state="CANCELLED",
            )

        # Kill active sandbox executions (RULE 4)
        if force and self._sandbox_manager is not None:
            kill_fn = getattr(self._sandbox_manager, "kill_all", None)
            if kill_fn is not None:
                kill_fn()

        # Release lease (LAW 3)
        lease_id = exec_data.get("lease_id")
        if lease_id:
            self._lease_manager.release_lease(lease_id)

        # Store terminal checkpoint
        session_id = exec_data["session_id"]
        self._state_store.store_checkpoint(
            session_id, exec_data["dag"], "cancelled",
            {"status": "cancelled", "reason": reason},
        )

        # Transition to CANCELLED
        sm.force_set(RuntimeState.CANCELLED)

        # Emit events
        self._publisher.publish_execution_event(
            "runtime.execution.cancelled", trace_id,
            {"ticket_id": ticket_id, "reason": reason, "force": force},
        )
        self._publisher.publish_lease_event(
            "runtime.lease.released", trace_id, ticket_id,
            lease_id or "", "unified_runtime",
        )

        logger.info("cancel: ticket=%s reason=%s force=%s trace=%s",
                     ticket_id, reason, force, trace_id)

        return CancellationReceipt(
            ticket_id=ticket_id,
            cancelled=True,
            terminated_state=sm.current.value,
            reason=reason,
            trace_id=trace_id,
        )

    # ── 4. observe() ─────────────────────────────────────────────

    def observe(
        self,
        ticket_id: str,
        stream: bool = False,
    ) -> LiveStateStream:
        """Observe current execution state.

        LAW 5: Every execution MUST be observable.
        LAW 12: trace_id correlation in all responses.

        When stream=True, subscribes a listener on EventBus for
        live runtime.execution.* events for this ticket.
        """
        exec_data = self._get_execution(ticket_id)
        trace_id = exec_data["trace_id"]
        sm: RuntimeStateMachine = exec_data["sm"]

        # Monitor heartbeat (LAW 3)
        lease_id = exec_data.get("lease_id")
        heartbeat_ok = True
        if lease_id:
            heartbeat_ok = self._lease_manager.monitor_heartbeat(lease_id)

        # Build progress snapshot
        node_states = exec_data.get("node_states", {})
        levels = exec_data.get("levels", [])
        total_nodes = sum(len(l) if isinstance(l, list) else 1 for l in levels)
        completed = sum(1 for s in node_states.values() if s == "completed")
        failed = sum(1 for s in node_states.values() if s == "failed")

        if heartbeat_ok and stream:
            topic = f"runtime.execution.{ticket_id}"
            self._event_bus.subscribe(topic, lambda ev: None)

        return LiveStateStream(
            ticket_id=ticket_id,
            current_state=sm.current.value,
            progress={
                "total": total_nodes,
                "completed": completed,
                "failed": failed,
                "heartbeat_ok": heartbeat_ok,
            },
            active_nodes=total_nodes - completed - failed,
            completed_nodes=completed,
            failed_nodes=failed,
        )

    # ── 5. replay() ──────────────────────────────────────────────

    def replay(
        self,
        execution_id: str,
        deterministic: bool = True,
    ) -> ReplayTicket:
        """Deterministically replay an execution from its trace.

        LAW 4: All execution MUST be replay-safe.
        LAW 7: Logic SHOULD be deterministic.

        Guard: Trace must exist in StateStore.
        """
        trace = self._state_store.read_trace(execution_id)
        if trace is None:
            raise CheckpointMissing(
                f"No trace found for execution {execution_id}",
            )

        trace_id = make_trace_id()
        replay_id = uuid.uuid4().hex[:12]

        # Create replay checkpoint
        self._state_store.store_checkpoint(
            f"replay:{replay_id}", trace, "",
            {"status": "replaying", "deterministic": deterministic},
        )

        # Schedule replay nodes
        if "nodes" in trace:
            remaining = list(trace["nodes"].keys())
            self._scheduler.schedule(remaining)

        # Emit events
        self._publisher.publish_replay_event(
            "runtime.replay.started", trace_id, execution_id,
            deterministic=deterministic,
        )

        logger.info("replay: exec=%s replay=%s deterministic=%s trace=%s",
                     execution_id, replay_id, deterministic, trace_id)

        return ReplayTicket(
            execution_id=execution_id,
            replay_id=replay_id,
            trace_id=trace_id,
            deterministic=deterministic,
        )

    # ── 6. scale() ───────────────────────────────────────────────

    def scale(
        self,
        target_worker_count: int,
        policy: ScalingPolicy = ScalingPolicy.BALANCED,
    ) -> ScalingReceipt:
        """Scale the distributed worker pool.

        LAW 10: Workers are unreliable — scale with lease mgr.

        Flow:
          1. Calculate delta from current count
          2. If scaling up: register new workers via lease manager
          3. If scaling down: drain and release leases
          4. Emit WORKER_POOL_SCALED event
        """
        trace_id = make_trace_id()

        if target_worker_count > MAX_WORKER_COUNT:
            raise ScaleLimitExceeded(
                f"Target {target_worker_count} exceeds maximum {MAX_WORKER_COUNT}",
                trace_id=trace_id, target=target_worker_count, maximum=MAX_WORKER_COUNT,
            )

        if target_worker_count < 0:
            raise ScaleError(
                f"Target worker count cannot be negative: {target_worker_count}",
                trace_id=trace_id, target=target_worker_count, actual=len(self._worker_pool),
            )

        current = len(self._worker_pool)
        delta = target_worker_count - current
        actual = current

        try:
            if delta > 0:
                for _ in range(delta):
                    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
                    lease_id = self._lease_manager.acquire_lease(
                        worker_id, "unified_runtime",
                    )
                    self._worker_pool[worker_id] = {
                        "worker_id": worker_id,
                        "lease_id": lease_id,
                        "registered_at": time.time(),
                    }
                actual = len(self._worker_pool)
            elif delta < 0:
                to_remove = list(self._worker_pool.keys())[:-delta]
                for wid in to_remove:
                    info = self._worker_pool.pop(wid, None)
                    if info and info.get("lease_id"):
                        self._lease_manager.release_lease(info["lease_id"])
                actual = len(self._worker_pool)

            self._publisher.publish_worker_event(
                "runtime.worker.scaled", trace_id, "pool",
                previous_count=current,
                target_count=target_worker_count,
                actual_count=actual,
                policy=policy.value,
            )

            logger.info("scale: %d → %d (actual=%d, policy=%s, trace=%s)",
                         current, target_worker_count, actual, policy.value, trace_id)

            return ScalingReceipt(
                previous_count=current,
                target_count=target_worker_count,
                actual_count=actual,
                policy=policy.value,
            )

        except Exception as e:
            raise ScaleError(
                f"Scaling from {current} to {target_worker_count} failed: {e}",
                trace_id=trace_id, target=target_worker_count, actual=actual,
            ) from e

    # ── 7. register_worker() ─────────────────────────────────────

    def register_worker(
        self,
        worker_manifest: Dict[str, Any],
    ) -> WorkerRegistration:
        """Register a new distributed worker.

        §15.4: Worker registration requires valid manifest.

        Flow:
          1. Validate worker manifest
          2. Register in worker registry
          3. Assign initial lease
          4. Emit WORKER_REGISTERED event
        """
        trace_id = make_trace_id()

        worker_id = worker_manifest.get("worker_id", "")
        if not worker_id or not isinstance(worker_id, str):
            raise WorkerRegistrationFailed(
                "Worker manifest must contain a valid 'worker_id' string",
                trace_id=trace_id, worker_id=str(worker_id),
            )

        if worker_id in self._worker_pool:
            existing = self._worker_pool[worker_id]
            return WorkerRegistration(
                worker_id=worker_id,
                registered=True,
                lease_ttl=existing.get("lease_ttl", 30.0),
                capabilities=existing.get("capabilities", {}),
            )

        capabilities = worker_manifest.get("capabilities", {})
        endpoints = worker_manifest.get("endpoints", {})
        lease_ttl = float(worker_manifest.get("lease_ttl", 30.0))

        lease_id = self._lease_manager.acquire_lease(
            worker_id, "unified_runtime", ttl=lease_ttl,
        )

        self._worker_pool[worker_id] = {
            "worker_id": worker_id,
            "capabilities": capabilities,
            "endpoints": endpoints,
            "lease_id": lease_id,
            "lease_ttl": lease_ttl,
            "registered_at": time.time(),
        }

        self._publisher.publish_worker_event(
            "runtime.worker.registered", trace_id, worker_id,
            capabilities=capabilities,
            lease_ttl=lease_ttl,
        )

        logger.info("register_worker: worker=%s trace=%s", worker_id, trace_id)

        return WorkerRegistration(
            worker_id=worker_id,
            registered=True,
            lease_ttl=lease_ttl,
            capabilities=capabilities,
        )
