"""Phase D8 — Service Mesh Protocol Definitions.

DESIGN ONLY — No runtime logic. These are typing.Protocol definitions
conforming to DEVELOPER.md §15.15a D8.1 and Architecture Canon LAW 23-27.

Each protocol defines exactly one service's domain boundary.
No service may expose methods belonging to another service's domain (LAW 27).

Protocols:
  IExecutionScheduler      — D8.1 | execution ordering (LAW 23)
  IExecutionStateStore     — D8.1 | persistence + traces (LAW 26)
  IExecutionDispatcher     — D8.1 | execution routing (LAW 24)
  IExecutionRetryHandler   — D8.1 | retry semantics (LAW 25)
  IExecutionLeaseManager   — D8.1 | distributed ownership (LAW 23)

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 23-27 (Service Ownership)
Ref: Canon RULE 2 (Interface Authority — contracts ONLY, no implementation assumptions)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


# ═════════════════════════════════════════════════════════════════════
# Shared Service Mesh Types
# ═════════════════════════════════════════════════════════════════════

class FailureMode(str, Enum):
    """Failure handling strategies for service interaction failures.

    Ref: DEVELOPER.md §15.15a D8.2
    Ref: Canon LAW 20-22 (Failure Propagation)
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


class ConsistencyLevel(str, Enum):
    """Consistency guarantees for service interactions.

    Ref: DEVELOPER.md §15.15a D8.2
    """
    STRONG = "strong"
    EVENTUAL = "eventual"
    NONE = "none"


class ServiceDomain(str, Enum):
    """The five bounded service domains (LAW 23-27).

    Ref: DEVELOPER.md §15.15a D8.4
    """
    SCHEDULER = "scheduler"
    DISPATCHER = "dispatcher"
    RETRY_HANDLER = "retry_handler"
    STATE_STORE = "state_store"
    LEASE_MANAGER = "lease_manager"
    ENGINE = "engine"
    CORE = "core"


@dataclass
class FailureContext:
    """Context propagated through the failure matrix.

    Attributes:
        source: The service domain where the failure originated.
        failure_mode: The classified failure mode.
        consistency: Required consistency level for recovery.
        effect_on: Ordered list of domains affected by this failure.
        action: Sequence of actions to execute.
        payload: Failure metadata (exception, timing, state).
        can_retry: Whether retry is semantically safe.
        retry_count: Number of retries already attempted.

    Ref: DEVELOPER.md §15.15a D8.2
    """
    source: ServiceDomain
    failure_mode: FailureMode
    consistency: ConsistencyLevel
    effect_on: List[ServiceDomain] = field(default_factory=list)
    action: List[FailureMode] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    can_retry: bool = False
    retry_count: int = 0


@dataclass
class ServiceStatus:
    """Health and ownership status of a service.

    Ref: Canon LAW 23-27 (Service Ownership)
    """
    domain: ServiceDomain
    healthy: bool = True
    lease_id: str = ""
    last_heartbeat: float = 0.0
    circuit_open: bool = False


# ═════════════════════════════════════════════════════════════════════
# D8.1 — IExecutionScheduler (LAW 23)
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IExecutionScheduler(Protocol):
    """Execution ordering — owns: schedule, concurrency, level dispatch.

    LAW 23: Scheduler owns execution ordering.
    FORBIDDEN: retry, dispatch, lease, state.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 23
    """

    def schedule(
        self,
        dag: Any,  # DependencyGraph
        session_id: Optional[str] = None,
        strategy: str = "balanced",
    ) -> List[List[Any]]:
        """Partition DAG nodes into execution levels.

        Args:
            dag: DependencyGraph to schedule.
            session_id: Optional session identifier.
            strategy: Scheduling strategy (balanced, cost_aware, etc.).

        Returns:
            List of levels, each level is a list of executable nodes.

        Raises:
            SchedulingError: If DAG contains cycles or invalid dependencies.
        """
        ...

    def run_with_timeout(
        self,
        node: Any,
        runner: Callable[..., Any],
        timeout: float = 30.0,
    ) -> Any:
        """Execute a single node with timeout enforcement.

        Args:
            node: The node to execute.
            runner: Callable that executes the node's tool.
            timeout: Maximum wall-clock seconds.

        Returns:
            Node execution result.

        Raises:
            TimeoutError: If execution exceeds timeout.
        """
        ...

    def collect_futures(
        self,
        futures: Dict[Any, Any],
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Collect and process completed futures from a level.

        Args:
            futures: Dict mapping Future → Node.
            session_id: Optional session identifier.

        Returns:
            List of results in completion order.

        Raises:
            CollectError: If future collection encounters unhandled errors.
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D8.1 — IExecutionStateStore (LAW 26)
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IExecutionStateStore(Protocol):
    """Persistence + traces — owns: state, cache, checkpoints, traces.

    LAW 26: StateStore owns persistence + traces.
    FORBIDDEN: dispatch, retry, lease, scheduling.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 26
    """

    def save_state(
        self,
        node_id: str,
        state: Any,
        session_id: str = "",
    ) -> None:
        """Persist a node's state.

        Args:
            node_id: Unique node identifier.
            state: Node state value to persist.
            session_id: Session identifier for trace grouping.

        Raises:
            PersistenceError: If state cannot be written.
        """
        ...

    def load_state(
        self,
        node_id: str,
        session_id: str = "",
    ) -> Optional[Any]:
        """Load a node's persisted state.

        Args:
            node_id: Unique node identifier.
            session_id: Session identifier.

        Returns:
            The persisted state, or None if not found.

        Raises:
            LoadError: If state cannot be read.
        """
        ...

    def store_checkpoint(
        self,
        session_id: str,
        dag: Any,
        last_node_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Store an execution checkpoint for resume.

        Args:
            session_id: Session identifier.
            dag: Current DependencyGraph state.
            last_node_id: ID of the last completed node.
            result: Execution result of the last node.

        Raises:
            CheckpointError: If checkpoint cannot be written.
        """
        ...

    def read_trace(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Read the full execution trace for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Execution trace dict, or None if no trace exists.

        Raises:
            TraceError: If trace cannot be read.
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D8.1 — IExecutionDispatcher (LAW 24)
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IExecutionDispatcher(Protocol):
    """Execution routing — owns: dispatch, contract validation, routing.

    LAW 24: Dispatcher owns execution routing.
    FORBIDDEN: state, lease, retry, scheduling.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 24
    """

    def dispatch_tool_call(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Route a tool call to the appropriate execution path.

        Args:
            tool_name: Name of the tool to dispatch.
            inputs: Input parameters for the tool.
            context: Optional execution context.

        Returns:
            Execution result dict.

        Raises:
            DispatchError: If routing fails.
            UnknownToolError: If tool_name is not registered.
        """
        ...

    def validate_contract(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
    ) -> bool:
        """Validate that a tool call conforms to its contract.

        Args:
            tool_name: Name of the tool.
            inputs: Input parameters to validate.

        Returns:
            True if valid, False otherwise.

        Raises:
            ContractViolationError: If contract is violated.
        """
        ...

    def route_service(
        self,
        service_domain: str,
        method: str,
        payload: Dict[str, Any],
    ) -> Any:
        """Route an inter-service call to the correct service.

        Args:
            service_domain: Target service domain name.
            method: Method name to invoke.
            payload: Method arguments.

        Returns:
            Service method result.

        Raises:
            RoutingError: If service domain or method is unknown.
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D8.1 — IExecutionRetryHandler (LAW 25)
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IExecutionRetryHandler(Protocol):
    """Retry semantics — owns: retry decision, backoff, failure recording.

    LAW 25: RetryHandler owns retry semantics.
    FORBIDDEN: scheduling, dispatch, state, lease.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 25
    """

    def decide_retry(
        self,
        node_id: str,
        error: Exception,
        attempt: int,
        max_attempts: int = 3,
    ) -> bool:
        """Decide whether a failed execution should be retried.

        Args:
            node_id: The failed node's identifier.
            error: The exception that caused the failure.
            attempt: Current attempt number (1-indexed).
            max_attempts: Maximum allowed attempts.

        Returns:
            True if retry should proceed, False if failure is terminal.

        Raises:
            RetryDecisionError: If retry decision cannot be computed.
        """
        ...

    def apply_backoff(
        self,
        attempt: int,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ) -> float:
        """Compute the backoff delay before the next retry.

        Args:
            attempt: Current attempt number.
            base_delay: Base delay in seconds.
            max_delay: Maximum delay cap in seconds.

        Returns:
            Delay in seconds before next retry attempt.
        """
        ...

    def record_failure(
        self,
        node_id: str,
        error: Exception,
        attempt: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a failure for telemetry and pattern detection.

        Args:
            node_id: The failed node's identifier.
            error: The exception that occurred.
            attempt: Attempt number when failure occurred.
            context: Optional metadata about the failure.

        Raises:
            RecordingError: If failure cannot be persisted.
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D8.1 — IExecutionLeaseManager (LAW 23)
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IExecutionLeaseManager(Protocol):
    """Distributed ownership — owns: leases, heartbeats, ownership coordination.

    LAW 23 (complement): LeaseManager manages distributed ownership.
    FORBIDDEN: retry, dispatch, state, scheduling.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 23 (distributed ownership domain)
    """

    def acquire_lease(
        self,
        resource_id: str,
        owner: str,
        ttl: float = 30.0,
    ) -> Optional[str]:
        """Acquire an execution lease for a distributed resource.

        Args:
            resource_id: The resource to lease.
            owner: Identity of the requesting owner.
            ttl: Time-to-live in seconds.

        Returns:
            Lease ID if acquired, None if lease is held by another owner.

        Raises:
            LeaseError: If lease cannot be acquired due to system error.
        """
        ...

    def renew_lease(
        self,
        lease_id: str,
        ttl: float = 30.0,
    ) -> bool:
        """Renew an existing lease to prevent expiry.

        Args:
            lease_id: The lease identifier to renew.
            ttl: New time-to-live in seconds.

        Returns:
            True if renewed, False if lease has expired or is invalid.

        Raises:
            LeaseError: If lease renewal encounters system error.
        """
        ...

    def release_lease(
        self,
        lease_id: str,
    ) -> bool:
        """Release a lease, making the resource available.

        Args:
            lease_id: The lease identifier to release.

        Returns:
            True if released, False if lease was not found.

        Raises:
            LeaseError: If lease release encounters system error.
        """
        ...

    def monitor_heartbeat(
        self,
        lease_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """Monitor heartbeat for a leased resource.

        Args:
            lease_id: The lease identifier to monitor.
            timeout: Maximum time to wait for heartbeat.

        Returns:
            True if heartbeat received within timeout, False otherwise.

        Raises:
            HeartbeatError: If heartbeat monitoring fails.
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# Compliance: Interaction Contract Matrix
# ═════════════════════════════════════════════════════════════════════

INTERACTION_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "Scheduler → Dispatcher": {
        "source": "IExecutionScheduler",
        "target": "IExecutionDispatcher",
        "method": "dispatch_tool_call",
        "consistency": ConsistencyLevel.STRONG,
        "failure_mode": FailureMode.RETRY,
        "law_ref": "LAW 23 → LAW 24",
    },
    "Scheduler → StateStore": {
        "source": "IExecutionScheduler",
        "target": "IExecutionStateStore",
        "method": "save_state / store_checkpoint",
        "consistency": ConsistencyLevel.EVENTUAL,
        "failure_mode": FailureMode.BUFFER,
        "law_ref": "LAW 23 → LAW 26",
    },
    "Dispatcher → RetryHandler": {
        "source": "IExecutionDispatcher",
        "target": "IExecutionRetryHandler",
        "method": "decide_retry / record_failure",
        "consistency": ConsistencyLevel.NONE,
        "failure_mode": FailureMode.CLASSIFY,
        "law_ref": "LAW 24 → LAW 25",
    },
    "RetryHandler → LeaseManager": {
        "source": "IExecutionRetryHandler",
        "target": "IExecutionLeaseManager",
        "method": "release_lease",
        "consistency": ConsistencyLevel.STRONG,
        "failure_mode": FailureMode.RELEASE,
        "law_ref": "LAW 25 → LAW 23",
    },
    "LeaseManager → Scheduler": {
        "source": "IExecutionLeaseManager",
        "target": "IExecutionScheduler",
        "method": "schedule / collect_futures",
        "consistency": ConsistencyLevel.STRONG,
        "failure_mode": FailureMode.REASSIGN,
        "law_ref": "LAW 23 (lease) → LAW 23 (scheduler)",
    },
    "StateStore → Core": {
        "source": "IExecutionStateStore",
        "target": "ExecutionCore",
        "method": "load_state / read_trace",
        "consistency": ConsistencyLevel.EVENTUAL,
        "failure_mode": FailureMode.DEGRADE,
        "law_ref": "LAW 26 → Core",
    },
}


# ═════════════════════════════════════════════════════════════════════
# Protocol Conformance Verification
# ═════════════════════════════════════════════════════════════════════

def verify_protocol_conformance() -> Dict[str, str]:
    """Verify that all D8 runtime types conform to their protocols.

    Returns dict mapping label → "PASS", "NOT_IMPLEMENTED", or "MISMATCH".
    D8 service extraction is design-target; modules may not exist yet.
    """
    _project_root = __file__.replace(
        "artifacts/design/d8/protocols/01_service_mesh_protocols.py", ""
    )
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    results: Dict[str, str] = {}

    checks = [
        ("IExecutionScheduler : ExecutionScheduler",
         "core.runtime.scheduler", "ExecutionScheduler",
         ["schedule", "run_with_timeout", "collect_futures"]),
        ("IExecutionStateStore : ExecutionStateStore",
         "core.runtime.state_store", "ExecutionStateStore",
         ["save_state", "load_state", "store_checkpoint", "read_trace"]),
        ("IExecutionDispatcher : ExecutionDispatcher",
         "core.runtime.tool_dispatcher", "ExecutionToolDispatcher",
         ["dispatch_tool_call", "validate_contract", "route_service"]),
        ("IExecutionRetryHandler : ExecutionRetryHandler",
         "core.runtime.retry_handler", "ExecutionRetryHandler",
         ["decide_retry", "apply_backoff", "record_failure"]),
        ("IExecutionLeaseManager : ExecutionLeaseManager",
         "core.runtime.lease_manager", "ExecutionLeaseManager",
         ["acquire_lease", "renew_lease", "release_lease", "monitor_heartbeat"]),
    ]

    for label, module_path, class_name, methods in checks:
        try:
            mod = __import__(module_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            conforms = all(hasattr(cls, m) for m in methods)
            results[label] = "PASS" if conforms else "MISMATCH"
        except (ImportError, AttributeError) as e:
            results[label] = f"NOT_IMPLEMENTED ({e})"

    return results


if __name__ == "__main__":
    import json
    import pathlib

    results = verify_protocol_conformance()
    print("=" * 60)
    print("D8 — Protocol Conformance Verification")
    print("=" * 60)
    all_conformant = True
    for key, value in results.items():
        if value == "PASS":
            print(f"  ✅  {key}")
        elif value.startswith("NOT_IMPLEMENTED"):
            print(f"  🔶  {key}  [NOT_IMPLEMENTED — design target]")
        else:
            print(f"  ❌  {key}  [MISMATCH]")
            all_conformant = False
    print()
    passed = sum(1 for v in results.values() if v == "PASS")
    not_impl = sum(1 for v in results.values() if v.startswith("NOT_IMPLEMENTED"))
    print(f"Result: {passed} PASS, {not_impl} NOT_IMPLEMENTED (design targets)")
    print(f"Overall: {'ALL CONFORMANT' if all_conformant else 'GAPS DETECTED (protocols)'}")
    print(f"Note: D8 services are design targets — extraction is future work.")
    print(f"      Protocol definitions themselves are validated by static type analysis.")

    # Write conformance report
    output_path = pathlib.Path(__file__).parent / "01_protocol_conformance.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport → {output_path}")
