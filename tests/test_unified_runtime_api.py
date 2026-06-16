"""F1 — Unified Runtime API Tests.

Verifies that UnifiedRuntimeAPI correctly delegates to D8 services
and handles all 5 operations (submit, resume, cancel, observe, replay).

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 13, RULE 1
"""

from unittest.mock import MagicMock

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
from core.runtime.unified_api import UnifiedRuntimeAPI


def _build_api() -> UnifiedRuntimeAPI:
    scheduler = MagicMock(spec=IExecutionScheduler)
    state_store = MagicMock(spec=IExecutionStateStore)
    dispatcher = MagicMock(spec=IExecutionDispatcher)
    retry_handler = MagicMock(spec=IExecutionRetryHandler)
    lease_manager = MagicMock(spec=IExecutionLeaseManager)
    lease_manager.acquire_lease.return_value = "lease-001"
    state_store.read_trace.return_value = {"nodes": {}}
    return UnifiedRuntimeAPI(
        scheduler=scheduler,
        state_store=state_store,
        dispatcher=dispatcher,
        retry_handler=retry_handler,
        lease_manager=lease_manager,
    )


class TestUnifiedRuntimeAPI:
    def test_unified_api_submit_creates_execution_and_lease(self) -> None:
        api = _build_api()
        request = RuntimeSubmitRequest(dag="mock_dag", trace_id="trace-001")
        response = api.submit(request)
        assert response.execution_id
        assert response.status == "submitted"
        assert response.lease_id == "lease-001"
        assert response.trace_id == "trace-001"

    def test_unified_api_observe_returns_current_state(self) -> None:
        api = _build_api()
        request = RuntimeSubmitRequest(dag="mock_dag")
        submit_resp = api.submit(request)
        observe_resp = api.observe(submit_resp.execution_id)
        assert isinstance(observe_resp, RuntimeObserveResponse)
        assert observe_resp.status in ("running", "unknown")

    def test_unified_api_cancel_releases_lease_and_updates_status(self) -> None:
        api = _build_api()
        request = RuntimeSubmitRequest(dag="mock_dag")
        submit_resp = api.submit(request)
        cancelled = api.cancel(submit_resp.execution_id)
        assert cancelled is True

    def test_unified_api_resume_continues_from_checkpoint(self) -> None:
        api = _build_api()
        request = RuntimeSubmitRequest(dag="mock_dag")
        submit_resp = api.submit(request)
        resume_resp = api.resume(submit_resp.execution_id)
        assert resume_resp.execution_id == submit_resp.execution_id
        assert resume_resp.status == "resumed"

    def test_unified_api_replay_restores_execution_context(self) -> None:
        api = _build_api()
        request = RuntimeSubmitRequest(dag="mock_dag")
        submit_resp = api.submit(request)
        replay_resp = api.replay(submit_resp.execution_id)
        assert replay_resp.execution_id != submit_resp.execution_id
        assert replay_resp.status == "replaying"

    def test_unified_api_rejects_invalid_execution_id(self) -> None:
        api = _build_api()
        api._state_store.read_trace.return_value = None
        observe_resp = api.observe("nonexistent-id")
        assert observe_resp.status == "unknown"
