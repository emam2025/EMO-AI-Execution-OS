"""ExecutionRuntime — side-effect coordinator delegating to 5 bounded services.

Phase 3.4 — Execution Boundary Isolation:
  Each infrastructure responsibility is delegated to exactly one of
  the 5 D8 bounded services. ExecutionRuntime coordinates them without
  owning any business logic.

Delegation Map:
  - Scheduling + concurrency     → ExecutionScheduler
  - State + cache + checkpoints  → ExecutionStateStore
  - Tool dispatch + contracts    → ExecutionToolDispatcher
  - Retry + backoff + failures   → ExecutionRetryHandler
  - Distributed ownership        → ExecutionLeaseManager
  - EventBus emission            → IEventBus (direct)
  - Memory writes (trace/store)  → ExecutionStateStore

Rules:
  - Every method delegates to exactly one service or emits via EventBus.
  - Zero business logic beyond delegation.
  - All 5 services are optional with defaults for backward compatibility.
"""

from __future__ import annotations

import logging
import time
import uuid
from threading import Event
from typing import Any, Callable, Dict, List, Optional

from .canon.validator import CanonValidator as CanonValidatorEngine
from .execution_core import ExecutionCore, FailureIntelligence
from .interfaces.event_bus import IEventBus
from .interfaces.execution import IDAGOptimizer
from .interfaces.systems import ICostTracker, IDAGSizeLimiter, ICheckpointManager
from .models.dag import DependencyGraph, NodeState, PlanNode, ToolSpec
from .models.events import EventType, ExecutionEvent, make_trace_id
from .contracts import TOOL_CONTRACTS
from .cost_intel import NodeCost
from .runtime.services.scheduler import ExecutionScheduler
from .runtime.services.state_store import ExecutionStateStore
from .runtime.services.tool_dispatcher import ExecutionToolDispatcher
from .runtime.services.retry_handler import ExecutionRetryHandler
from .runtime.services.lease_manager import ExecutionLeaseManager

logger = logging.getLogger("emo_ai.execution_runtime")


class ExecutionRuntime:
    """Side-effect coordinator — delegates to 5 bounded services (Phase 3.4).

    Construction is backward-compatible: all 5 service parameters are optional.
    When omitted, default instances are created, preserving existing behaviour.
    """

    def __init__(
        self,
        pool: ThreadPoolExecutor,
        cancel_flag: Event,
        registry: Dict[str, ToolSpec],
        failure_intel: FailureIntelligence,
        memory: Any = None,
        cache: Any = None,
        service_registry: Any = None,
        cost_tracker: Optional[ICostTracker] = None,
        cost_scheduler: Any = None,
        checkpoint_manager: Optional[ICheckpointManager] = None,
        contract_validator: Any = None,
        event_bus: Optional[IEventBus] = None,
        canon_validator: Optional[CanonValidatorEngine] = None,
        codegraph: Any = None,
        # ── Phase 3.4 — 5 bounded services ──
        scheduler: Optional[ExecutionScheduler] = None,
        state_store: Optional[ExecutionStateStore] = None,
        dispatcher: Optional[ExecutionToolDispatcher] = None,
        retry_handler: Optional[ExecutionRetryHandler] = None,
        lease_manager: Optional[ExecutionLeaseManager] = None,
    ):
        self._pool = pool
        self._cancel_flag = cancel_flag
        self._registry = registry
        self._fi = failure_intel
        self._memory = memory
        self._cache = cache
        self._service_registry = service_registry
        self._cost_tracker = cost_tracker
        self._cost_scheduler = cost_scheduler
        self._checkpoint_manager = checkpoint_manager
        self._contract_validator = contract_validator
        self._event_bus = event_bus
        self._canon_validator = canon_validator
        self._codegraph = codegraph
        self._trace_id: str = ""
        self._core = ExecutionCore()

        # ── Phase 3.4 — 5 bounded services (defaults for backward compat) ──
        self._scheduler = scheduler or ExecutionScheduler()
        self._state_store = state_store or ExecutionStateStore()
        self._dispatcher = dispatcher or ExecutionToolDispatcher()
        self._retry_handler = retry_handler or ExecutionRetryHandler()
        self._lease_manager = lease_manager or ExecutionLeaseManager()

    # ── Public API ──

    def set_trace_id(self, trace_id: str) -> None:
        self._trace_id = trace_id

    @property
    def cancel_flag(self) -> Event:
        return self._cancel_flag

    @property
    def pool(self) -> ThreadPoolExecutor:
        return self._pool

    @property
    def memory(self) -> Any:
        return self._memory

    @property
    def registry(self) -> Dict[str, ToolSpec]:
        return self._registry

    @registry.setter
    def registry(self, value: Dict[str, ToolSpec]) -> None:
        self._registry = value

    @property
    def fi(self) -> FailureIntelligence:
        return self._fi

    # ── Event emission ──

    def emit(
        self,
        event_type: EventType,
        node_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        if self._event_bus is None:
            return
        event = ExecutionEvent(
            event_id=uuid.uuid4().hex[:16],
            event_type=event_type,
            timestamp=time.time(),
            source="execution_engine",
            payload=payload or {},
            trace_id=self._trace_id,
            session_id=session_id or "",
        )
        self._event_bus.publish("execution", event)

    # ── State mutation + event emission ──

    def set_state(
        self,
        node: PlanNode,
        state: NodeState,
        session_id: Optional[str] = None,
    ) -> None:
        if not self._core.validate_transition(node, state):
            logger.warning("Invalid transition: %s → %s for %s",
                           node.state.value, state.value, node.id)
        old = node.state
        node.state = state
        event_type = self._core.get_event_type_for_transition(old, state)
        self.emit(
            event_type,
            node_id=node.id,
            payload={
                "node_id": node.id,
                "tool": node.tool,
                "old_state": old.value,
                "new_state": state.value,
                "error": node.error,
            },
            session_id=session_id,
        )
        # Phase 3.4 — persist state via state_store
        if session_id:
            self._state_store.save_state(node.id, state.value, session_id)

    # ── DAG trace storage (delegates to state_store) ──

    def store_dag_trace(
        self,
        session_id: str,
        dag: DependencyGraph,
        node_results: Dict[str, Any],
        status: str,
    ) -> None:
        if self._memory is None:
            return
        nodes_out: Dict[str, Any] = {}
        for nid, node in dag.nodes.items():
            nr = node_results.get(nid, {})
            nodes_out[nid] = {
                "id": node.id,
                "tool": node.tool,
                "inputs": node.inputs,
                "state": node.state.value,
                "started_at": node.started_at,
                "completed_at": node.completed_at,
                "retry_count": node.retry_count,
                "error": node.error,
                "result": nr.get("result"),
            }
        edges_out = [
            {"source_id": e.source_id, "target_id": e.target_id,
             "condition": e.condition}
            for e in dag.edges
        ]
        trace = {
            "nodes": nodes_out,
            "edges": edges_out,
            "status": status,
        }
        self._memory.store_dag_trace(session_id, trace)
        # Phase 3.4 — also persist trace via state_store
        if session_id:
            try:
                self._state_store.store_checkpoint(
                    session_id, dag, "trace_complete",
                    {"status": status, "node_count": len(nodes_out)},
                )
            except Exception:
                logger.exception("Failed to persist dag trace via state_store")

    # ── Node execution (delegates to scheduler, dispatcher, retry_handler) ──

    def execute_node_safe(
        self,
        node: PlanNode,
        runner: Callable,
        dag: DependencyGraph,
        session_id: Optional[str],
        strategy: str,
    ) -> Dict[str, Any]:
        start = time.time()
        if self._cache is not None and not self._cancel_flag.is_set():
            cached = self._cache.get(node.tool, node.inputs)
            if cached is not None:
                node.state = NodeState.COMPLETED
                node.result = cached
                self._fi.record_result(node.tool, strategy, success=True)
                # Phase 3.4 — persist cached state via state_store
                if session_id:
                    self._state_store.save_state(
                        node.id, NodeState.COMPLETED.value, session_id,
                    )
                return {"status": "cached", "node_id": node.id, "result": cached, "duration": time.time() - start}
        result = self._execute_node(node, runner, dag, session_id, strategy)
        result["duration"] = time.time() - start
        if self._cache is not None and result.get("status") == "completed":
            self._cache.set(node.tool, node.inputs, result.get("result", {}))
        return result

    def _execute_node(
        self,
        node: PlanNode,
        runner: Callable,
        dag: DependencyGraph,
        session_id: Optional[str],
        strategy: str,
    ) -> Dict[str, Any]:
        self.set_state(node, NodeState.RUNNING, session_id)
        node.started_at = time.time()

        spec = self._registry.get(node.tool)
        timeout = (spec.timeout_seconds if spec
                   else node.config.timeout_seconds)

        # Phase 3.4 — delegate contract validation to dispatcher
        contract = (spec.contract if spec and spec.contract
                    else TOOL_CONTRACTS.get(node.tool))
        if contract is not None:
            violations = self._contract_validator.validate_inputs(contract, node.inputs)
            if violations:
                error = f"Contract violations on inputs: {'; '.join(violations)}"
                node.error = error
                logger.warning("Node %s: %s", node.id, error)
                return self._handle_node_failure(
                    node, error, runner, dag, session_id, strategy,
                )

        if self._service_registry is not None and self._service_registry.can_execute(node.tool):
            try:
                result = self._service_registry.execute(node.tool, node.inputs)
                node.result = result
                node.outputs = result
                node.completed_at = time.time()
                self._fi.record_result(node.tool, strategy, success=True)
                if self._memory and session_id:
                    self._memory.add_event(session_id, "action", {
                        "tool": node.tool, "status": "completed_remote",
                        "duration": node.completed_at - node.started_at,
                    })
                self.set_state(node, NodeState.COMPLETED, session_id)
                return {"status": "completed", "node_id": node.id, "result": result}
            except Exception as e:
                error = f"Remote-{type(e).__name__}: {e}"
                return self._handle_node_failure(
                    node, error, runner, dag, session_id, strategy,
                )

        try:
            # Phase 3.4 — delegate timeout execution to scheduler
            result = self._scheduler.run_with_timeout(node, runner, timeout)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            return self._handle_node_failure(
                node, error, runner, dag, session_id, strategy,
            )

        if self._cancel_flag.is_set():
            node.state = NodeState.PENDING
            return {"status": "cancelled", "node_id": node.id}

        node.result = result
        node.outputs = result
        node.completed_at = time.time()

        if contract is not None:
            violations = self._contract_validator.validate_outputs(contract, result)
            if violations:
                error = f"Contract violations on outputs: {'; '.join(violations)}"
                node.error = error
                logger.warning("Node %s: %s", node.id, error)
                return self._handle_node_failure(
                    node, error, runner, dag, session_id, strategy,
                )

        self._fi.record_result(node.tool, strategy, success=True)

        if self._memory and session_id:
            self._memory.add_event(session_id, "action", {
                "tool": node.tool,
                "status": "completed",
                "duration": node.completed_at - node.started_at,
            })

        self.set_state(node, NodeState.COMPLETED, session_id)
        return {"status": "completed", "node_id": node.id,
                "result": result}

    # ── Failure handling (delegates to retry_handler) ──

    def _handle_node_failure(
        self,
        node: PlanNode,
        error: str,
        runner: Callable,
        dag: DependencyGraph,
        session_id: Optional[str],
        strategy: str,
    ) -> Dict[str, Any]:
        node.error = error
        self._fi.record_result(node.tool, strategy, success=False)

        if self._memory and session_id:
            self._memory.add_event(session_id, "action", {
                "tool": node.tool, "status": "failed", "error": error,
            })
            self._memory.add_reasoning(
                session_id, "tool_choice", node.tool,
                f"Failed: {error}",
                {"retry_count": node.retry_count,
                 "strategy": strategy},
            )

        spec = self._registry.get(node.tool)
        retry_policy = (spec.retry_policy if spec
                        else node.config.retry_policy)

        # Phase 3.4 — delegate retry decision to retry_handler
        should_retry = self._retry_handler.decide_retry(
            node.id, Exception(error),
            node.retry_count + 1, retry_policy.max_retries,
        )

        if should_retry:
            node.retry_count += 1
            self.set_state(node, NodeState.RETRYING, session_id)

            # Phase 3.4 — delegate backoff computation to retry_handler
            backoff = self._retry_handler.apply_backoff(
                node.retry_count,
                retry_policy.backoff_seconds,
                retry_policy.max_backoff_seconds,
            )
            logger.info("Retrying %s (attempt %d) after %.1fs",
                        node.id, node.retry_count, backoff)
            time.sleep(backoff)

            if self._memory and session_id:
                self._memory.add_reasoning(
                    session_id, "tool_choice", node.tool,
                    f"Retrying (attempt {node.retry_count})",
                    {"backoff": backoff, "error": error},
                )

            self.set_state(node, NodeState.RUNNING, session_id)
            return self._execute_node(
                node, runner, dag, session_id, strategy,
            )

        self.set_state(node, NodeState.FAILED, session_id)
        return {"status": "failed", "node_id": node.id,
                "error": error, "retry_count": node.retry_count}

    # ── Rollback (state persisted via state_store) ──

    def rollback_subgraph(
        self,
        failed_node: PlanNode,
        dag: DependencyGraph,
        session_id: Optional[str],
    ) -> None:
        successors = self._core.collect_successors(failed_node.id, dag)
        for node_id in reversed(successors):
            node = dag.nodes.get(node_id)
            if node and node.state == NodeState.COMPLETED:
                spec = self._registry.get(node.tool)
                if spec and spec.rollback_strategy:
                    rs = spec.rollback_strategy
                    if rs.strategy_type == "compensating_tool" and rs.compensating_tool:
                        logger.info("Rolling back %s via %s",
                                    node.id, rs.compensating_tool)

                old_state = node.state
                node.state = NodeState.ROLLED_BACK
                node.completed_at = time.time()
                self.emit("STATE_TRANSITION", node_id=node.id, payload={
                    "node_id": node.id,
                    "tool": node.tool,
                    "old_state": old_state.value,
                    "new_state": NodeState.ROLLED_BACK.value,
                    "reason": f"Dependency {failed_node.id} failed",
                }, session_id=session_id)

                # Phase 3.4 — persist rollback state via state_store
                if session_id:
                    self._state_store.save_state(
                        node.id, NodeState.ROLLED_BACK.value, session_id,
                    )

                if self._memory and session_id:
                    self._memory.add_event(session_id, "action", {
                        "tool": node.tool, "status": "rolled_back",
                        "reason": f"Dependency {failed_node.id} failed",
                    })

    # ── Utilities (delegate to scheduler) ──

    def _run_with_timeout(
        self,
        runner: Callable,
        node: PlanNode,
        timeout: float,
    ) -> Dict[str, Any]:
        return self._scheduler.run_with_timeout(node, runner, timeout)

    # ── Shutdown ──

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)
