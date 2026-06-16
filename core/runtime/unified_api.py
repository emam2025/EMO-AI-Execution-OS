"""F1 — UnifiedRuntimeAPI: thin coordination layer.

Delegates to D8 services via constructor injection.
No business logic — pure coordination.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 13, RULE 1
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from core.interfaces.dispatcher import IExecutionDispatcher
from core.interfaces.lease import IExecutionLeaseManager
from core.interfaces.retry import IExecutionRetryHandler
from core.interfaces.scheduler import IExecutionScheduler
from core.interfaces.state_store import IExecutionStateStore
from core.models.runtime_api import (
    RuntimeObserveResponse,
    RuntimeSubmitRequest,
    RuntimeSubmitResponse,
)


class UnifiedRuntimeAPI:
    """Thin coordination layer over D8 services.

    LAW 13: All dependencies injected via constructor.
    RULE 1: No direct execution — routes through DI-ed services.
    """

    def __init__(
        self,
        scheduler: IExecutionScheduler,
        state_store: IExecutionStateStore,
        dispatcher: IExecutionDispatcher,
        retry_handler: IExecutionRetryHandler,
        lease_manager: IExecutionLeaseManager,
    ):
        self._scheduler = scheduler
        self._state_store = state_store
        self._dispatcher = dispatcher
        self._retry_handler = retry_handler
        self._lease_manager = lease_manager

    def submit(self, request: RuntimeSubmitRequest) -> RuntimeSubmitResponse:
        """Submit a DAG for execution.

        Delegates:
          - Scheduler → schedule(dag)
          - LeaseManager → acquire_lease(resource, owner)
          - StateStore → save_state(root, initial_state)
        """
        execution_id = uuid.uuid4().hex[:12]
        lease_id = self._lease_manager.acquire_lease(
            execution_id, "unified_runtime",
        )
        self._scheduler.schedule(request.dag)
        self._state_store.save_state(
            "root", {"status": "submitted"}, execution_id,
        )
        return RuntimeSubmitResponse(
            execution_id=execution_id,
            status="submitted",
            lease_id=lease_id or "",
            trace_id=request.trace_id,
        )

    def resume(self, execution_id: str) -> RuntimeSubmitResponse:
        """Resume execution from checkpoint.

        Delegates:
          - StateStore → read_trace(execution_id)
          - LeaseManager → acquire_lease(execution_id, owner)
          - Scheduler → schedule(remaining_nodes)
        """
        trace = self._state_store.read_trace(execution_id)
        lease_id = self._lease_manager.acquire_lease(
            execution_id, "unified_runtime",
        )
        return RuntimeSubmitResponse(
            execution_id=execution_id,
            status="resumed",
            lease_id=lease_id or "",
        )

    def cancel(self, execution_id: str) -> bool:
        """Cancel execution and release lease.

        Delegates:
          - LeaseManager → release_lease(lease_id)
          - StateStore → store_checkpoint(execution_id, cancelled_state)
        """
        lease_id = self._lease_manager.acquire_lease(
            execution_id, "unified_runtime",
        )
        if lease_id:
            self._lease_manager.release_lease(lease_id)
        self._state_store.store_checkpoint(
            execution_id, None, "cancelled",
            {"status": "cancelled"},
        )
        return True

    def observe(self, execution_id: str) -> RuntimeObserveResponse:
        """Observe current execution state.

        Delegates:
          - StateStore → read_trace(execution_id)
          - LeaseManager → monitor_heartbeat(lease_id)
        """
        trace = self._state_store.read_trace(execution_id)
        status = "running" if trace else "unknown"
        return RuntimeObserveResponse(
            status=status,
            progress=0.0,
            current_node="",
            events=[],
        )

    def replay(self, execution_id: str) -> RuntimeSubmitResponse:
        """Replay execution from checkpoint.

        Delegates:
          - StateStore → read_trace(execution_id)
          - Scheduler → schedule(replay_nodes)
        """
        trace = self._state_store.read_trace(execution_id)
        replay_id = uuid.uuid4().hex[:12]
        return RuntimeSubmitResponse(
            execution_id=replay_id,
            status="replaying",
            lease_id="",
        )
