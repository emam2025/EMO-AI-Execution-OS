"""Phase F1 — Unified Runtime API Protocol.

DESIGN ONLY — No runtime logic. This is the single entry-point Protocol
for the entire execution lifecycle, bridging ExecutionEngine and the D8 Service Mesh.

IUnifiedRuntimeAPI defines 7 operations:
  submit()    — Submit a DAG for execution
  resume()    — Resume from checkpoint
  cancel()    — Cancel a running execution
  observe()   — Stream live state
  replay()    — Deterministic replay
  scale()     — Scale worker pool
  register_worker() — Register a distributed worker

Ref: DEVELOPER.md §15.2 (High-Level Runtime Architecture)
Ref: DEVELOPER.md §15.12 (Runtime Decomposition Rules)
Ref: Canon LAW 1-13, RULE 1-5
Ref: Phase F1 — Computer Use Runtime (ROADMAP)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Protocol, runtime_checkable


# ═════════════════════════════════════════════════════════════════════
# Shared F1 Types — Tickets, Status, Receipts
# ═════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ExecutionTicket:
    """Issued by submit() — unique handle for an execution.

    LAW 12 enforcement: Every side effect has a traceable ticket.
    Ref: §15.2 — Execution Kernel
    """
    ticket_id: str
    dag_id: str
    session_id: str = ""
    trace_id: str = ""
    submitted_at: float = 0.0


@dataclass(frozen=True)
class ReplayTicket:
    """Issued by replay() — handle for deterministic re-execution.

    LAW 4 enforcement: Replay-safe execution.
    """
    execution_id: str
    replay_id: str
    trace_id: str = ""
    deterministic: bool = True
    checkpoint_id: str = ""


@dataclass(frozen=True)
class CancellationReceipt:
    """Returned by cancel() — proof of cancellation request.

    LAW 8 enforcement: State transitions MUST be recoverable.
    """
    ticket_id: str
    cancelled: bool
    terminated_state: str  # CANCELLED | ROLLED_BACK | RUNNING
    reason: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class ScalingReceipt:
    """Returned by scale() — confirmation of worker pool change.

    Ref: §15.4 — Distributed Worker Protocol
    """
    previous_count: int
    target_count: int
    actual_count: int
    policy: str = ""


@dataclass(frozen=True)
class WorkerRegistration:
    """Returned by register_worker() — confirmation of worker registration.

    Ref: §15.4 — Worker Endpoints (/health, /capabilities, /execute)
    """
    worker_id: str
    registered: bool
    lease_ttl: float = 30.0
    capabilities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveStateStream:
    """Streamed by observe() — real-time state snapshots.

    LAW 5 enforcement: Every execution MUST be observable.
    """
    ticket_id: str
    current_state: str
    progress: Dict[str, Any] = field(default_factory=dict)
    active_nodes: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutionStatus:
    """Runtime status response for resume() and observe().

    Ref: §15.2 — Execution State Machine
    """
    ticket_id: str
    state: str
    trace_id: str = ""
    node_states: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    progress_pct: float = 0.0
    checkpoint_available: bool = False


# ═════════════════════════════════════════════════════════════════════
# Options & Context Models
# ═════════════════════════════════════════════════════════════════════

@dataclass
class SubmissionOptions:
    """Options for submission.

    Ref: §15.3 — Runtime State Model
    Ref: Canon LAW 7 (Deterministic execution)
    """
    strategy: str = "balanced"
    priority: int = 0
    ttl: float = 300.0
    max_retries: int = 3
    checkpoint_interval: int = 0
    tags: Dict[str, str] = field(default_factory=dict)
    deterministic: bool = True


@dataclass
class ExecutionContext:
    """Execution context carrying trace and correlation IDs.

    LAW 12 enforcement: All side effects MUST be traceable.
    """
    session_id: str = ""
    trace_id: str = ""
    correlation_id: str = ""
    parent_ticket_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ScalingPolicy(str, Enum):
    """Policies for worker scaling.

    Ref: §15.4 — Distributed Worker Protocol
    """
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"
    MANUAL = "manual"


# ═════════════════════════════════════════════════════════════════════
# F1 — IUnifiedRuntimeAPI Protocol
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IUnifiedRuntimeAPI(Protocol):
    """Unified Runtime API — single entry point for all execution lifecycle.

    This protocol sits between the Multi-Agent Layer and the D8 Service Mesh.
    It is the ONLY public API for execution lifecycle management.

    All 7 methods route through CompositionRoot → D8 services → EventBus.
    No method may call D8 service implementations directly (LAW 13, RULE 1).

    Ref: DEVELOPER.md §15.2 (High-Level Runtime Architecture)
    Ref: DEVELOPER.md §15.12 (Runtime Decomposition Rules)
    Ref: Canon LAW 1-13, RULE 1-5
    """

    # ── Lifecycle Operations ──

    def submit(
        self,
        dag: Any,  # DependencyGraph
        context: Optional[ExecutionContext] = None,
        options: Optional[SubmissionOptions] = None,
    ) -> ExecutionTicket:
        """Submit a DAG for execution.

        Flow:
          1. Validate DAG structure (ExecutionCore)
          2. Acquire execution lease (IExecutionLeaseManager)
          3. Schedule nodes into levels (IExecutionScheduler)
          4. Persist initial state (IExecutionStateStore)
          5. Dispatch first level (IExecutionDispatcher)
          6. Return ticket for lifecycle tracking

        Args:
            dag: DependencyGraph to execute.
            context: Execution context (trace_id, session_id).
            options: Submission options (strategy, priority, ttl).

        Returns:
            ExecutionTicket — unique handle for all subsequent API calls.

        Raises:
            SubmissionRejected: If DAG validation fails.
            QuotaExceeded: If resource limits prevent execution.
            LeaseConflict: If lease cannot be acquired.

        Ref: §15.2 — DAG Runtime Engine
        Ref: Canon LAW 1 (no direct impl imports), LAW 3 (lease-aware)
        """
        ...

    def resume(
        self,
        ticket_id: str,
        from_checkpoint: Optional[str] = None,
    ) -> ExecutionStatus:
        """Resume execution from last checkpoint or specific checkpoint.

        Guard: StateStore.has_checkpoint(ticket_id) MUST return True.

        Flow:
          1. Load saved checkpoint (IExecutionStateStore)
          2. Restore DAG state (IExecutionStateStore)
          3. Re-acquire lease (IExecutionLeaseManager)
          4. Re-schedule remaining nodes (IExecutionScheduler)
          5. Resume dispatch from checkpoint (IExecutionDispatcher)

        Args:
            ticket_id: Execution ticket to resume.
            from_checkpoint: Optional checkpoint ID (default: latest).

        Returns:
            ExecutionStatus — current state after resume.

        Raises:
            CheckpointMissing: If no checkpoint exists for ticket.
            InvalidStateTransition: If ticket is not in a resumable state.

        Ref: §15.3 — Replay restores execution state
        Ref: Canon LAW 4 (replay-safe), LAW 8 (recoverable)
        """
        ...

    def cancel(
        self,
        ticket_id: str,
        reason: str = "",
        force: bool = False,
    ) -> CancellationReceipt:
        """Cancel a running execution.

        Flow:
          1. Set cancel flag (ExecutionEngine)
          2. Stop dispatching new nodes (IExecutionScheduler)
          3. Kill active node executions (ISandboxExecutor.kill)
          4. Release lease (IExecutionLeaseManager)
          5. Rollback partial execution state (IExecutionStateStore)
          6. Persist cancellation checkpoint (IExecutionStateStore)
          7. Emit EXECUTION_CANCELLED event (IEventBus)

        Args:
            ticket_id: Execution ticket to cancel.
            reason: Human-readable cancellation reason.
            force: If True, skip rollback and kill immediately.

        Returns:
            CancellationReceipt — proof of cancellation.

        Raises:
            InvalidStateTransition: If execution is already terminal.
            WorkerUnavailable: If force=True and worker cannot be reached.

        Ref: Canon LAW 10 (workers unreliable), RULE 4 (everything killable)
        """
        ...

    def observe(
        self,
        ticket_id: str,
        stream: bool = False,
    ) -> LiveStateStream:
        """Observe current execution state, optionally as a live stream.

        Flow:
          1. Load execution state (IExecutionStateStore)
          2. Query active leases (IExecutionLeaseManager)
          3. Build progress snapshot
          4. If stream=True, subscribe to EventBus for live updates

        Args:
            ticket_id: Execution ticket to observe.
            stream: If True, returns a generator of LiveStateStream events.

        Returns:
            LiveStateStream — current state snapshot (or generator if streaming).

        Raises:
            InvalidStateTransition: If ticket_id is unknown.

        Ref: §15.2 — Observability Plane
        Ref: Canon LAW 5 (observable), LAW 12 (traceable)
        """
        ...

    def replay(
        self,
        execution_id: str,
        deterministic: bool = True,
    ) -> ReplayTicket:
        """Deterministically replay an execution from its trace.

        Flow:
          1. Load execution trace (IExecutionStateStore)
          2. Create replay checkpoint
          3. Execute deterministically through D8 services
          4. Compare output hash with original

        Args:
            execution_id: ID of the execution to replay.
            deterministic: If True, freeze all random seeds.

        Returns:
            ReplayTicket — handle for the replay execution.

        Raises:
            CheckpointMissing: If execution trace is incomplete.
            ReplayError: If replay encounters non-determinism.

        Ref: §15.3 — Replay restores execution state
        Ref: Canon LAW 4 (replay-safe), LAW 7 (deterministic)
        """
        ...

    # ── Infrastructure Operations ──

    def scale(
        self,
        target_worker_count: int,
        policy: ScalingPolicy = ScalingPolicy.BALANCED,
    ) -> ScalingReceipt:
        """Scale the distributed worker pool.

        Flow:
          1. Calculate delta from current count
          2. If scaling up: register new workers (IExecutionLeaseManager)
          3. If scaling down: drain and deregister workers
          4. Update scheduler capacity (IExecutionScheduler)
          5. Emit WORKER_POOL_SCALED event (IEventBus)

        Args:
            target_worker_count: Desired number of workers.
            policy: Scaling policy (aggressive, balanced, conservative).

        Returns:
            ScalingReceipt — confirmation with actual worker count.

        Raises:
            ScaleError: If scaling operation fails.

        Ref: §15.4 — Distributed Worker Protocol
        Ref: Canon LAW 10 (workers unreliable)
        """
        ...

    def register_worker(
        self,
        worker_manifest: Dict[str, Any],
    ) -> WorkerRegistration:
        """Register a new distributed worker.

        Manifest includes: worker_id, capabilities, endpoints, lease_ttl.

        Flow:
          1. Validate worker manifest
          2. Register in worker registry
          3. Assign initial lease via IExecutionLeaseManager
          4. Emit WORKER_REGISTERED event (IEventBus)
          5. Return WorkerRegistration with assigned lease TTL

        Args:
            worker_manifest: Dict with worker_id, capabilities, endpoints.

        Returns:
            WorkerRegistration — confirmation with lease details.

        Raises:
            WorkerRegistrationError: If registration fails.

        Ref: §15.4 — Worker Endpoints (/health, /capabilities, /execute)
        Ref: Canon LAW 3 (lease-aware)
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# API → D8 Service Mesh Routing Table
# ═════════════════════════════════════════════════════════════════════

API_TO_D8_ROUTING: Dict[str, Dict[str, Any]] = {
    "submit": {
        "steps": [
            ("ExecutionCore", "validate_dag"),
            ("IExecutionLeaseManager", "acquire_lease"),
            ("IExecutionScheduler", "schedule"),
            ("IExecutionStateStore", "store_checkpoint"),
            ("IExecutionDispatcher", "dispatch_tool_call"),
        ],
        "events": ["EXECUTION_SUBMITTED", "EXECUTION_PLANNED", "EXECUTION_STARTED"],
        "consistency": "strong",
        "law_ref": "LAW 1, LAW 3, LAW 12",
    },
    "resume": {
        "steps": [
            ("IExecutionStateStore", "read_trace"),
            ("IExecutionStateStore", "load_state"),
            ("IExecutionLeaseManager", "acquire_lease"),
            ("IExecutionScheduler", "schedule"),
            ("IExecutionDispatcher", "dispatch_tool_call"),
        ],
        "events": ["EXECUTION_RESUMED", "EXECUTION_RESTARTED"],
        "consistency": "strong",
        "law_ref": "LAW 4, LAW 8, LAW 12",
    },
    "cancel": {
        "steps": [
            ("ExecutionEngine", "cancel"),
            ("IExecutionScheduler", "schedule"),  # drain remaining
            ("ISandboxExecutor", "kill"),
            ("IExecutionLeaseManager", "release_lease"),
            ("IExecutionStateStore", "store_checkpoint"),
        ],
        "events": ["EXECUTION_CANCELLED", "LEASE_RELEASED", "WORKER_KILLED"],
        "consistency": "strong",
        "law_ref": "LAW 10, RULE 4",
    },
    "observe": {
        "steps": [
            ("IExecutionStateStore", "read_trace"),
            ("IExecutionLeaseManager", "monitor_heartbeat"),
            ("IEventBus", "subscribe"),
        ],
        "events": ["STATE_SNAPSHOT", "EXECUTION_PROGRESS"],
        "consistency": "eventual",
        "law_ref": "LAW 5, LAW 12",
    },
    "replay": {
        "steps": [
            ("IExecutionStateStore", "read_trace"),
            ("IExecutionStateStore", "store_checkpoint"),
            ("IExecutionScheduler", "schedule"),
            ("IExecutionDispatcher", "dispatch_tool_call"),
            ("ExecutionCore", "validate_dag"),
        ],
        "events": ["REPLAY_STARTED", "REPLAY_COMPLETED", "REPLAY_MISMATCH"],
        "consistency": "strong",
        "law_ref": "LAW 4, LAW 7",
    },
    "scale": {
        "steps": [
            ("IExecutionLeaseManager", "acquire_lease"),
            ("IExecutionLeaseManager", "release_lease"),
            ("IExecutionScheduler", "schedule"),
        ],
        "events": ["WORKER_POOL_SCALED", "WORKER_DRAINED"],
        "consistency": "eventual",
        "law_ref": "LAW 10",
    },
    "register_worker": {
        "steps": [
            ("WorkerRegistry", "register"),
            ("IExecutionLeaseManager", "acquire_lease"),
        ],
        "events": ["WORKER_REGISTERED", "WORKER_LEASE_GRANTED"],
        "consistency": "strong",
        "law_ref": "LAW 3, LAW 10",
    },
}


# ═════════════════════════════════════════════════════════════════════
# Protocol Conformance Verification
# ═════════════════════════════════════════════════════════════════════

def verify_protocol_conformance() -> Dict[str, str]:
    """Verify UnifiedRuntimeAPI protocol signature compliance."""
    required_methods = [
        "submit", "resume", "cancel", "observe", "replay",
        "scale", "register_worker",
    ]

    # Check the protocol is valid
    protocol_ok = all(
        hasattr(IUnifiedRuntimeAPI, m) for m in required_methods
    )

    results: Dict[str, str] = {
        "IUnifiedRuntimeAPI — 7 methods defined": (
            "PASS" if protocol_ok
            else f"FAIL: missing {[m for m in required_methods if not hasattr(IUnifiedRuntimeAPI, m)]}"
        ),
    }

    # Check routing table covers all methods
    for method in required_methods:
        if method in API_TO_D8_ROUTING:
            steps = API_TO_D8_ROUTING[method]["steps"]
            events = API_TO_D8_ROUTING[method]["events"]
            results[f"  Route: {method} ({len(steps)} steps, {len(events)} events)"] = "PASS"
        else:
            results[f"  Route: {method}"] = "FAIL — missing routing entry"

    # Count optional types
    types = [
        ExecutionTicket, ReplayTicket, CancellationReceipt,
        ScalingReceipt, WorkerRegistration, LiveStateStream,
        ExecutionStatus, ExecutionContext, SubmissionOptions,
    ]
    results[f"Response models: {len(types)} dataclasses"] = "PASS"

    return results


if __name__ == "__main__":
    import json
    import pathlib

    results = verify_protocol_conformance()
    print("=" * 60)
    print("F1 — UnifiedRuntimeAPI Conformance Verification")
    print("=" * 60)
    for key, value in results.items():
        status = "✅" if value == "PASS" else "❌"
        print(f"  {status}  {key}")
    print()
    total = len(results)
    passed = sum(1 for v in results.values() if v == "PASS")
    print(f"Result: {passed}/{total} passed")
    print(f"Note: This is a Protocol definition — runtime implementation is future work.")

    output_path = pathlib.Path(__file__).parent / "01_protocol_conformance.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport → {output_path}")
