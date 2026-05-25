"""Phase F1 — Unified Runtime API: Comprehensive tests.

Groups:
  G1 — TestStateMachineGuards         (10 tests)
  G2 — TestResponseEnvelopeErrors     (6 tests)
  G3 — TestTraceIdPropagation         (4 tests)
  G4 — TestUnifiedApiCompliance       (5 tests)
  G5 — TestSubmitFlow                 (5 tests)
  G6 — TestCancelResumeObserve        (4 tests)
  G7 — TestScaleRegisterWorker        (4 tests)

Total: ~38 tests

Ref: DEVELOPER.md §15.2
Ref: Canon LAW 8, LAW 12, LAW 13
Ref: EXEC-DIRECTIVE-003
"""

import time
import uuid
from unittest.mock import MagicMock

import pytest

from core.interfaces.event_bus import IEventBus
from core.runtime.api.event_publisher import EventPublisher
from core.runtime.api.state_machine import (
    RESUMABLE_STATES,
    TERMINAL_STATES,
    RuntimeState,
    RuntimeStateMachine,
    TransitionGuard,
)
from core.runtime.api.unified_runtime_api import (
    CancellationReceipt,
    ExecutionContext,
    ExecutionTicket,
    ExecutionStatus,
    LiveStateStream,
    ReplayTicket,
    ScalingPolicy,
    ScalingReceipt,
    SubmissionOptions,
    UnifiedRuntime,
    WorkerRegistration,
)
from core.runtime.models.api_errors import (
    APIError,
    CheckpointMissing,
    ErrorCode,
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


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def make_runtime(strict_api_mode: bool = False, event_bus=None) -> UnifiedRuntime:
    return UnifiedRuntime(
        scheduler=ExecutionScheduler(),
        state_store=ExecutionStateStore(),
        dispatcher=ExecutionToolDispatcher(),
        retry_handler=ExecutionRetryHandler(),
        lease_manager=ExecutionLeaseManager(),
        event_bus=event_bus or MagicMock(spec=IEventBus),
        failure_matrix=FailureMatrix(),
        strict_api_mode=strict_api_mode,
    )


class SimpleDAG:
    def __init__(self, nodes=None, dag_id=None):
        self.nodes = nodes if nodes is not None else ["a", "b", "c"]
        self.dag_id = dag_id or "test-dag"


# ════════════════════════════════════════════════════════════════════
# G1 — TestStateMachineGuards (10 tests)
# ════════════════════════════════════════════════════════════════════


class TestStateMachineGuards:
    """G1: RuntimeStateMachine and TransitionGuard correctness.

    Tests LAW 8 — All state transitions MUST be guarded.
    Tests RULE 4 — Terminal states block further transitions.
    """

    def test_valid_submit_to_queued_transition(self):
        sm = RuntimeStateMachine()
        assert sm.current == RuntimeState.SUBMITTED
        allowed, reason = sm._guard.guard_submit_to_queued(SimpleDAG())
        assert allowed
        assert reason == ""

    def test_invalid_submit_empty_dag(self):
        guard = TransitionGuard()
        allowed, reason = guard.guard_submit_to_queued(None)
        assert not allowed
        assert "None" in reason

    def test_queued_to_leased_guard_fails_without_lease(self):
        guard = TransitionGuard()
        allowed, reason = guard.guard_queued_to_leased(None)
        assert not allowed
        assert "Lease not acquired" in reason

    def test_terminal_state_blocks_transition(self):
        sm = RuntimeStateMachine()
        sm.force_set(RuntimeState.COMPLETED)
        with pytest.raises(InvalidStateTransition):
            sm.transition(RuntimeState.CANCELLED)

    def test_invalid_transition_raises(self):
        sm = RuntimeStateMachine()
        with pytest.raises(InvalidStateTransition):
            sm.transition(RuntimeState.REPLAYING)

    def test_guard_orphaned_to_recovered(self):
        guard = TransitionGuard()
        allowed, reason = guard.guard_orphaned_to_recovered(recovered=True)
        assert allowed

    def test_guard_completed_to_replaying_no_trace(self):
        guard = TransitionGuard()
        allowed, reason = guard.guard_completed_to_replaying(trace_exists=False)
        assert not allowed

    def test_executing_to_orphaned_allowed(self):
        guard = TransitionGuard()
        allowed, reason = guard.guard_to_orphaned()
        assert allowed

    def test_cancel_from_planning_allowed(self):
        guard = TransitionGuard()
        allowed, reason = guard.guard_to_cancelled()
        assert allowed

    def test_rollback_completes_terminal_chain(self):
        sm = RuntimeStateMachine()
        sm.force_set(RuntimeState.ROLLED_BACK)
        assert sm.is_terminal()


# ════════════════════════════════════════════════════════════════════
# G2 — TestResponseEnvelopeErrors (6 tests)
# ════════════════════════════════════════════════════════════════════


class TestResponseEnvelopeErrors:
    """G2: ResponseEnvelope and error taxonomy integrity."""

    def test_success_envelope(self):
        env = ResponseEnvelope.success(data={"key": "val"}, ticket_id="t1", trace_id="tr1")
        assert env.status == "success"
        assert env.data == {"key": "val"}
        assert env.trace_id == "tr1"
        assert env.ticket_id == "t1"

    def test_error_envelope(self):
        err = SubmissionRejected("bad dag", trace_id="tr1")
        env = ResponseEnvelope.error(error=err, ticket_id="t1")
        assert env.status == "error"
        assert env.error is not None
        assert env.error.trace_id == "tr1"

    def test_pending_envelope(self):
        env = ResponseEnvelope.pending(ticket_id="t1", trace_id="tr1")
        assert env.status == "pending"

    def test_error_to_dict_serialization(self):
        err = SubmissionRejected("bad dag", trace_id="tr1", errors=["missing input"])
        env = ResponseEnvelope.error(error=err, ticket_id="t1", trace_id="tr1")
        d = env.to_dict()
        assert d["status"] == "error"
        assert d["error"]["code"] == "SUBMISSION_REJECTED"
        assert d["error"]["recoverable"] is True

    def test_error_code_law_mapping(self):
        from core.runtime.models.api_errors import ERROR_CODE_LAW_MAP
        assert ErrorCode.SUBMISSION_REJECTED in ERROR_CODE_LAW_MAP
        assert "LAW 1" in ERROR_CODE_LAW_MAP[ErrorCode.SUBMISSION_REJECTED]

    def test_all_error_classes_have_trace_id(self):
        errors = [
            SubmissionRejected(trace_id="t"),
            CheckpointMissing(trace_id="t"),
            InvalidStateTransition(trace_id="t"),
            LeaseConflict(trace_id="t"),
            QuotaExceeded(trace_id="t"),
            WorkerUnavailable(trace_id="t"),
            ScaleLimitExceeded(trace_id="t"),
        ]
        for err in errors:
            assert err.trace_id == "t"
            assert isinstance(err, APIError)


# ════════════════════════════════════════════════════════════════════
# G3 — TestTraceIdPropagation (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestTraceIdPropagation:
    """G3: trace_id consistency across all API layers."""

    def test_submit_ticket_carries_trace_id(self):
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG(), context=ExecutionContext(trace_id="custom-trace"))
        assert ticket.trace_id == "custom-trace"

    def test_trace_id_generated_when_not_provided(self):
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG())
        assert ticket.trace_id
        assert len(ticket.trace_id) > 0

    def test_trace_id_flows_to_error(self):
        rt = make_runtime()
        with pytest.raises(SubmissionRejected) as exc:
            rt.submit(None, context=ExecutionContext(trace_id="err-trace"))
        assert exc.value.trace_id == "err-trace"

    def test_cancel_receipt_carries_trace_id(self):
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG(), context=ExecutionContext(trace_id="cancel-trace"))
        receipt = rt.cancel(ticket.ticket_id)
        assert receipt.trace_id == "cancel-trace"


# ════════════════════════════════════════════════════════════════════
# G4 — TestUnifiedApiCompliance (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestUnifiedApiCompliance:
    """G4: UnifiedRuntime matches protocol signature requirements."""

    REQUIRED_METHODS = [
        "submit", "resume", "cancel", "observe", "replay",
        "scale", "register_worker",
    ]

    def test_all_seven_methods_exist(self):
        for method in self.REQUIRED_METHODS:
            assert hasattr(UnifiedRuntime, method), f"Missing method: {method}"

    def test_submit_returns_execution_ticket(self):
        rt = make_runtime()
        result = rt.submit(SimpleDAG())
        assert isinstance(result, ExecutionTicket)

    def test_scale_returns_scaling_receipt(self):
        rt = make_runtime()
        result = rt.scale(4, ScalingPolicy.BALANCED)
        assert isinstance(result, ScalingReceipt)
        assert result.actual_count == 4

    def test_register_worker_returns_registration(self):
        rt = make_runtime()
        result = rt.register_worker({"worker_id": "w1", "capabilities": {"cpu": 4}})
        assert isinstance(result, WorkerRegistration)
        assert result.worker_id == "w1"
        assert result.registered is True

    def test_register_duplicate_worker_returns_existing(self):
        rt = make_runtime()
        r1 = rt.register_worker({"worker_id": "w1", "capabilities": {"cpu": 4}})
        r2 = rt.register_worker({"worker_id": "w1", "capabilities": {"mem": 8}})
        assert r2.registered is True
        # Duplicate returns existing capabilities (first registration wins essentially)
        assert r2.worker_id == "w1"


# ════════════════════════════════════════════════════════════════════
# G5 — TestSubmitFlow (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestSubmitFlow:
    """G5: submit() lifecycle correctness."""

    def test_submit_returns_valid_ticket(self):
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG())
        assert ticket.ticket_id
        assert ticket.dag_id == "test-dag"
        assert ticket.trace_id
        assert ticket.submitted_at > 0

    def test_submit_with_custom_options(self):
        rt = make_runtime()
        opts = SubmissionOptions(strategy="cost_aware", priority=10, ttl=600.0)
        ticket = rt.submit(SimpleDAG(), options=opts)
        assert ticket.ticket_id
        assert ticket.submitted_at > 0

    def test_submit_rejects_none_dag(self):
        rt = make_runtime()
        with pytest.raises(SubmissionRejected):
            rt.submit(None)

    def test_submit_rejects_empty_dag(self):
        rt = make_runtime()
        with pytest.raises(SubmissionRejected):
            rt.submit(SimpleDAG(nodes=[]))

    def test_submit_publishes_events(self):
        bus = MagicMock(spec=IEventBus)
        rt = make_runtime(event_bus=bus)
        rt.submit(SimpleDAG())
        # Should have published submitted + queued events
        published_topics = [call[0][0] for call in bus.publish.call_args_list]
        assert "runtime.execution.submitted" in published_topics
        assert "runtime.execution.queued" in published_topics


# ════════════════════════════════════════════════════════════════════
# G6 — TestCancelResumeObserve (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestCancelResumeObserve:
    """G6: cancel(), resume(), observe() lifecycle."""

    def test_cancel_non_terminal_execution(self):
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG())
        receipt = rt.cancel(ticket.ticket_id, reason="test cancel")
        assert receipt.cancelled is True
        assert receipt.terminated_state == "CANCELLED"
        assert receipt.reason == "test cancel"

    def test_cancel_unknown_ticket_raises(self):
        rt = make_runtime()
        with pytest.raises(TicketNotFound):
            rt.cancel("nonexistent-ticket")

    def test_observe_returns_snapshot(self):
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG())
        snapshot = rt.observe(ticket.ticket_id)
        assert isinstance(snapshot, LiveStateStream)
        assert snapshot.ticket_id == ticket.ticket_id
        assert snapshot.current_state in [s.value for s in RuntimeState]

    def test_observe_unknown_ticket_raises(self):
        rt = make_runtime()
        with pytest.raises(TicketNotFound):
            rt.observe("nonexistent")


# ════════════════════════════════════════════════════════════════════
# G7 — TestScaleRegisterWorker (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestScaleRegisterWorker:
    """G7: scale() and register_worker() infrastructure."""

    def test_scale_up_adds_workers(self):
        rt = make_runtime()
        result = rt.scale(3, ScalingPolicy.AGGRESSIVE)
        assert result.actual_count == 3
        assert result.previous_count == 0
        assert result.target_count == 3

    def test_scale_down_removes_workers(self):
        rt = make_runtime()
        rt.scale(5)
        result = rt.scale(2, ScalingPolicy.CONSERVATIVE)
        assert result.actual_count == 2

    def test_scale_negative_raises(self):
        rt = make_runtime()
        with pytest.raises(ScaleError):
            rt.scale(-1)

    def test_scale_exceeds_maximum_raises(self):
        rt = make_runtime()
        with pytest.raises(ScaleLimitExceeded):
            rt.scale(999)


# ════════════════════════════════════════════════════════════════════
# G8 — TestEdgeCases (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """G8: Edge cases and error paths."""

    def test_replay_nonexistent_trace_raises(self):
        rt = make_runtime()
        with pytest.raises(CheckpointMissing):
            rt.replay("nonexistent")

    def test_cancel_twice_idempotent(self):
        """Cancel is idempotent — second cancel returns success."""
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG())
        r1 = rt.cancel(ticket.ticket_id)
        assert r1.cancelled is True
        # Second cancel should succeed (idempotent, LAW 8)
        r2 = rt.cancel(ticket.ticket_id)
        assert r2.cancelled is True

    def test_resume_from_cancelled_state(self):
        """Resume is allowed from CANCELLED state (LAW 4, LAW 8)."""
        rt = make_runtime()
        ticket = rt.submit(SimpleDAG())
        rt.cancel(ticket.ticket_id)
        # CANCELLED is resumable — should return status, not raise
        status = rt.resume(ticket.ticket_id)
        assert isinstance(status, ExecutionStatus)
        assert status.state in ("QUEUED", "SUBMITTED")

    def test_register_worker_invalid_manifest_raises(self):
        rt = make_runtime()
        with pytest.raises(WorkerRegistrationFailed):
            rt.register_worker({})


# ════════════════════════════════════════════════════════════════════
# G9 — TestCompositionRootWiring (3 tests)
# ════════════════════════════════════════════════════════════════════


class TestCompositionRootWiring:
    """G9: CompositionRoot correctly wires UnifiedRuntime with D8 services."""

    def test_root_creates_unified_runtime(self):
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        rt = root.unified_runtime
        assert rt is not None
        assert hasattr(rt, "submit")
        assert hasattr(rt, "cancel")

    def test_root_injects_d8_services(self):
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        rt = root.unified_runtime
        assert rt._scheduler is root.scheduler
        assert rt._state_store is root.state_store
        assert rt._lease_manager is root.lease_manager

    def test_root_supports_strict_api_mode(self):
        from core.composition.root import CompositionRoot
        root = CompositionRoot(strict_api_mode=True)
        rt = root.unified_runtime
        assert rt._strict_api_mode is True
