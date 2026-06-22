"""ExecutionEngine — thin coordinator over 5 bounded services.

Architecture (Phase 3.4 — Execution Boundary Isolation):
    ExecutionEngine (orchestration only)
        ├── ExecutionCore (pure logic, no IO)
        └── ExecutionRuntime (side-effect coordinator)
                ├── ExecutionScheduler      (LAW 23 — ordering)
                ├── ExecutionStateStore     (LAW 26 — persistence)
                ├── ExecutionToolDispatcher (LAW 24 — dispatch)
                ├── ExecutionRetryHandler   (LAW 25 — retry)
                └── ExecutionLeaseManager   (LAW 23 — ownership)

Phase 3.4 additions:
    - 5 D8 bounded services injected via constructor
    - All infrastructure delegated to services
    - Canon enforcement (pre-execution guard)
    - EventBus emission for all lifecycle transitions
    - CodeGraph aware execution context
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Dict, Iterator, List, Optional

from .canon.context import ValidationContext as CanonValidationContext
from .execution_core import (
    ExecutionCore,
    FailureIntelligence,
    FailurePattern,
    DAGBuilder,
)
from .execution_runtime import ExecutionRuntime
from .interfaces.event_bus import IEventBus
from .interfaces.execution_engine import IExecutionEngine
from .interfaces.execution import IDAGOptimizer
from .interfaces.systems import ICostTracker, IDAGSizeLimiter, ICheckpointManager
from .models.events import EventType, make_trace_id
from .models.dag import (
    NodeState, DependencyGraph, PlanNode,
)
from .adapters.governance_adapter import DefaultContractValidator, DefaultComplianceValidator
from .cost_intel import NodeCost
from .runtime.services.scheduler import ExecutionScheduler
from .runtime.services.state_store import ExecutionStateStore
from .runtime.services.tool_dispatcher import ExecutionToolDispatcher
from .runtime.services.retry_handler import ExecutionRetryHandler
from .runtime.services.lease_manager import ExecutionLeaseManager

# ── Backward-compatible re-exports for tests ──
from .models.dag import (
    DependencyGraph, PlanNode, PlanEdge, ToolSpec,
    NodeState, NodeConfig, RetryPolicy, RollbackStrategy,
    DAG_SCHEMA_VERSION,
)
from .execution_core import DAGBuilder, FailureIntelligence, FailurePattern

logger = logging.getLogger("emo_ai.execution_engine")

API_VERSION = "2.0.0"
_FROZEN_PUBLIC_METHODS_V2 = frozenset({
    "execute", "execute_streaming", "cancel", "shutdown", "register_tool",
})


class ExecutionEngine(IExecutionEngine):

    API_VERSION = API_VERSION
    FROZEN_PUBLIC_METHODS_V2 = _FROZEN_PUBLIC_METHODS_V2

    def __init__(
        self,
        tool_registry=None,
        memory=None,
        failure_intel=None,
        worker_pool_size: int = 4,
        cache=None,
        service_registry=None,
        optimizer: Optional[IDAGOptimizer] = None,
        cost_tracker: Optional[ICostTracker] = None,
        size_limiter: Optional[IDAGSizeLimiter] = None,
        checkpoint_manager: Optional[ICheckpointManager] = None,
        contract_validator=None,
        compliance_validator=None,
        event_bus: Optional[IEventBus] = None,
        canon_validator=None,
        codegraph: Any = None,
        # ── Phase 3.4 — 5 bounded services ──
        scheduler: Optional[ExecutionScheduler] = None,
        state_store: Optional[ExecutionStateStore] = None,
        dispatcher: Optional[ExecutionToolDispatcher] = None,
        retry_handler: Optional[ExecutionRetryHandler] = None,
        lease_manager: Optional[ExecutionLeaseManager] = None,
    ):
        # ── Core (pure logic) ──
        self._core = ExecutionCore()

        # ── Registry ──
        self._registry: Dict[str, Any] = tool_registry or {}
        self._optimizer = optimizer
        self._size_limiter = size_limiter
        self._cost_tracker = cost_tracker
        self._cost_scheduler = (
            self._try_import_cost_scheduler(cost_tracker) if cost_tracker else None
        )
        self._checkpoint_manager = checkpoint_manager

        # ── Infrastructure ──
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, worker_pool_size),
            thread_name_prefix="dag_worker",
        )
        self._cancel_flag = Event()
        self._has_shutdown = False
        self._event_bus = event_bus
        self._codegraph = codegraph
        self._trace_id: str = ""

        # ── Canon ──
        self._canon_validator = canon_validator

        # ── Runtime (infra layer with 5 bounded services) ──
        fi = failure_intel or FailureIntelligence()
        cv = contract_validator or DefaultContractValidator()
        self._runtime = ExecutionRuntime(
            pool=self._pool,
            cancel_flag=self._cancel_flag,
            registry=self._registry,
            failure_intel=fi,
            memory=memory,
            cache=cache,
            service_registry=service_registry,
            cost_tracker=cost_tracker,
            cost_scheduler=self._cost_scheduler,
            checkpoint_manager=checkpoint_manager,
            contract_validator=cv,
            event_bus=event_bus,
            canon_validator=canon_validator,
            codegraph=codegraph,
            # ── Phase 3.4 — 5 bounded services ──
            scheduler=scheduler,
            state_store=state_store,
            dispatcher=dispatcher,
            retry_handler=retry_handler,
            lease_manager=lease_manager,
        )

    @staticmethod
    def _try_import_cost_scheduler(cost_tracker):  # pragma: no cover
        from .cost_intel import CostAwareScheduler
        return CostAwareScheduler(cost_tracker)

    # ── Properties ──

    @property
    def registry(self) -> Dict[str, Any]:
        return dict(self._registry)

    @registry.setter
    def registry(self, value) -> None:
        self._registry = value

    @property
    def memory(self):
        return self._runtime.memory

    @property
    def fi(self):
        return self._runtime.fi

    # ── Public API : execute ──

    def execute(
        self,
        dag: DependencyGraph,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
        tool_runner: Optional[Callable] = None,
        preserve_states: bool = False,
    ) -> Dict[str, Any]:
        self._cancel_flag.clear()
        self._trace_id = make_trace_id()
        self._runtime.set_trace_id(self._trace_id)

        # ── Canon enforcement (pre-execution guard) ──
        if self._canon_validator is not None:
            ctx = CanonValidationContext(
                graph=self._codegraph,
                coupling_score=getattr(self, "_coupling_score", None),
                risk_score=getattr(self, "_risk_score", None),
            )
            result = self._canon_validator.validate(ctx)
            if not result.allowed:
                self._runtime.emit("EXECUTION_FAILED", payload={
                    "reason": "Canon validation blocked",
                    "violations": [str(v) for v in result.violations],
                }, session_id=session_id)
                return {
                    "status": "failed",
                    "errors": [str(v) for v in result.violations],
                    "dag": dag.to_dict(),
                    "node_results": {},
                }

        # ── Size limiter ──
        if self._size_limiter is not None:
            limit_errors = self._size_limiter.check(dag)
            if limit_errors:
                self._runtime.emit("EXECUTION_FAILED", payload={"errors": limit_errors}, session_id=session_id)
                return {"status": "failed", "errors": limit_errors,
                        "dag": dag.to_dict(), "node_results": {}}

        # ── DAG optimizer ──
        if self._optimizer is not None:
            dag = self._optimizer.optimize(dag)

        errors = self._core.validate_dag(dag)
        if errors:
            self._runtime.emit("EXECUTION_FAILED", payload={"errors": errors}, session_id=session_id)
            return {"status": "failed", "errors": errors,
                    "dag": dag.to_dict(), "node_results": {}}

        # ── Schema version validation ──
        self._core.check_schema_version(dag)

        self._runtime.emit("EXECUTION_PLANNED", payload={
            "dag_id": getattr(dag, "dag_id", ""),
            "node_count": len(dag.nodes),
        }, session_id=session_id)

        if not preserve_states:
            for node in dag.nodes.values():
                self._runtime.set_state(node, NodeState.PLANNED, session_id)

        runner = tool_runner or self._core.default_tool_runner

        results: Dict[str, Any] = {}
        overall_status = "completed"

        for level in self._core.independent_branches(dag):
            if self._cancel_flag.is_set():
                overall_status = "cancelled"
                break

            # ── Cost-aware ordering within level ──
            if self._cost_scheduler is not None:
                level = self._cost_scheduler.schedule(level)

            # ── Parallel execution via worker pool ──
            futures = {}
            for node in level:
                if preserve_states and node.state in (NodeState.COMPLETED, NodeState.FAILED):
                    if node.state == NodeState.COMPLETED:
                        results[node.id] = {
                            "status": "completed", "node_id": node.id,
                            "result": node.result,
                        }
                    continue
                future = self._pool.submit(
                    self._runtime.execute_node_safe, node, runner,
                    dag, session_id, strategy,
                )
                futures[future] = node

            level_results = []
            for future in as_completed(futures):
                node = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {"status": "failed", "node_id": node.id,
                              "error": f"Worker exception: {e}"}
                level_results.append(result)
                results[node.id] = result

                # ── Record cost ──
                if self._cost_tracker is not None and result.get("duration") is not None:
                    self._cost_tracker.record(NodeCost(
                        tool=node.tool,
                        duration_seconds=result["duration"],
                    ))

                if result["status"] == "failed":
                    self._runtime.rollback_subgraph(node, dag, session_id)
                    if overall_status not in ("rolled_back",):
                        overall_status = "failed"

                # ── Checkpoint progress ──
                if self._checkpoint_manager is not None and session_id:
                    self._checkpoint_manager.save(
                        session_id, dag, node.id, result,
                    )

            for r in level_results:
                if r["status"] == "cancelled":
                    overall_status = "cancelled"
                    break

        if self._runtime.memory and session_id:
            self._runtime.store_dag_trace(session_id, dag, results, overall_status)

        # Emit execution-level event
        if overall_status == "completed":
            self._runtime.emit("EXECUTION_COMPLETED", payload={
                "dag_id": getattr(dag, "dag_id", ""),
                "status": overall_status,
                "node_count": len(dag.nodes),
                "result_count": len(results),
            }, session_id=session_id)
        elif overall_status == "cancelled":
            self._runtime.emit("EXECUTION_CANCELLED", payload={
                "dag_id": getattr(dag, "dag_id", ""),
            }, session_id=session_id)
        else:
            self._runtime.emit("EXECUTION_FAILED", payload={
                "dag_id": getattr(dag, "dag_id", ""),
                "status": overall_status,
            }, session_id=session_id)

        return {
            "status": overall_status,
            "dag": dag.to_dict(),
            "node_results": results,
        }

    # ── Public API : execute_streaming ──

    def execute_streaming(
        self,
        dag: DependencyGraph,
        tool_runner: Optional[Callable] = None,
    ) -> Iterator[Dict[str, Any]]:
        if self._size_limiter is not None:
            limit_errors = self._size_limiter.check(dag)
            if limit_errors:
                yield {"status": "failed", "errors": limit_errors}
                return

        if self._optimizer is not None:
            dag = self._optimizer.optimize(dag)

        errors = self._core.validate_dag(dag)
        if errors:
            yield {"status": "failed", "errors": errors}
            return

        try:
            self._core.check_schema_version(dag)
        except Exception as e:
            yield {
                "status": "failed",
                "errors": [str(e)],
            }
            return

        runner = tool_runner or self._core.default_tool_runner
        executor = self._try_import_streaming_executor()

        for partial in executor.run(dag, runner):
            yield partial

    @staticmethod
    def _try_import_streaming_executor():  # pragma: no cover
        from .memory_pressure import StreamingExecutor
        return StreamingExecutor()

    # ── Public API : lifecycle ──

    def cancel(self) -> None:
        self._cancel_flag.set()

    def shutdown(self, wait: bool = True) -> None:
        if not self._has_shutdown:
            self._pool.shutdown(wait=wait)
            self._has_shutdown = True

    def __del__(self):
        if not self._has_shutdown:
            self._pool.shutdown(wait=False)

    @classmethod
    def check_api_compliance(cls) -> None:
        from .api_compliance import verify_frozen_methods
        verify_frozen_methods(
            cls, cls.FROZEN_PUBLIC_METHODS_V2, cls.API_VERSION,
        )

    # ── IExecutionEngine Protocol conformance ──

    def plan(self, nodes: List[PlanNode]) -> DependencyGraph:
        dag = DependencyGraph()
        for node in nodes:
            dag.add_node(node)
        self._runtime.emit("EXECUTION_PLANNED", payload={"node_count": len(nodes)})
        return dag

    def cancel(self, execution_id: str = "") -> bool:
        self._cancel_flag.set()
        self._runtime.emit("EXECUTION_CANCELLED", payload={"execution_id": execution_id})
        return True

    def status(self, execution_id: str) -> str:
        return "cancelled" if self._cancel_flag.is_set() else "running"

    # ── Backward-compatible delegates ──

    @staticmethod
    def _check_schema_version(dag):
        ExecutionCore.check_schema_version(dag)

    @staticmethod
    def _default_tool_runner(node):
        return ExecutionCore.default_tool_runner(node)

    @staticmethod
    def _collect_successors(node_id, dag):
        return ExecutionCore.collect_successors(node_id, dag)

    def _rollback_subgraph(self, failed_node, dag, session_id):
        self._runtime.rollback_subgraph(failed_node, dag, session_id)

    def _set_state(self, node, state, session_id=None):
        self._runtime.set_state(node, state, session_id)

    def _execute_node_safe(self, node, runner, dag, session_id, strategy):
        return self._runtime.execute_node_safe(node, runner, dag, session_id, strategy)

    def _store_dag_trace(self, session_id, dag, node_results, status):
        self._runtime.store_dag_trace(session_id, dag, node_results, status)

    def _emit(self, event_type, node_id="", payload=None, session_id=None):
        self._runtime.emit(event_type, node_id, payload, session_id)

    # ── Tool management ──

    def register_tool(self, spec) -> None:
        self._registry[spec.name] = spec
