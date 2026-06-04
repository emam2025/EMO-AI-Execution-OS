"""Phase F1 — Unified Runtime API Test Suite.

Tests all 7 lifecycle methods of the UnifiedRuntime API:
  submit() | resume() | cancel() | observe() | replay() | scale() | register_worker()

COVERAGE:
  - TestSubmitLeaseFlow (5): execution submission, lease acquisition, event publication
  - TestCancelIntegrity (5): safe cancellation, lease release, sandbox cleanup
  - TestResumeCheckpoint (5): checkpoint-based resume, state consistency
  - TestReplayDeterminism (5): deterministic replay, telemetry isolation
  - TestScaleQuotaEnforcement (5): worker scaling, quota enforcement
  - TestObserveStateStream (3): live state observation, heartbeat monitoring
  - TestRegisterWorkerFlow (3): worker registration, duplicate handling
  - TestAPIRoutingSecurity (4): capability guard, IO policy enforcement

Ref: DEVELOPER.md §15.2
Ref: Canon LAW 1, LAW 3, LAW 4, LAW 5, LAW 8, LAW 12, RULE 1, RULE 4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.runtime.api.unified_runtime_api import (
    UnifiedRuntime,
    ExecutionTicket,
    ReplayTicket,
    CancellationReceipt,
    ScalingReceipt,
    WorkerRegistration,
    LiveStateStream,
    ExecutionStatus,
    ExecutionContext,
    SubmissionOptions,
    ScalingPolicy,
    RuntimeState,
    RuntimeStateMachine,
)
from core.runtime.models.api_errors import (
    TicketNotFound,
    InvalidStateTransition,
    CheckpointMissing,
    ScaleLimitExceeded,
    ScaleError,
    WorkerRegistrationFailed,
    SubmissionRejected,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_services():
    scheduler = MagicMock()
    state_store = MagicMock()
    dispatcher = MagicMock()
    retry_handler = MagicMock()
    lease_manager = MagicMock()
    event_bus = MagicMock()
    failure_matrix = MagicMock()
    sandbox_manager = MagicMock()
    isolation_runtime = MagicMock()
    return {
        "scheduler": scheduler,
        "state_store": state_store,
        "dispatcher": dispatcher,
        "retry_handler": retry_handler,
        "lease_manager": lease_manager,
        "event_bus": event_bus,
        "failure_matrix": failure_matrix,
        "sandbox_manager": sandbox_manager,
        "isolation_runtime": isolation_runtime,
    }


@pytest.fixture
def runtime(mock_services):
    return UnifiedRuntime(
        scheduler=mock_services["scheduler"],
        state_store=mock_services["state_store"],
        dispatcher=mock_services["dispatcher"],
        retry_handler=mock_services["retry_handler"],
        lease_manager=mock_services["lease_manager"],
        event_bus=mock_services["event_bus"],
        failure_matrix=mock_services["failure_matrix"],
        sandbox_manager=mock_services["sandbox_manager"],
        isolation_runtime=mock_services["isolation_runtime"],
        strict_api_mode=True,
    )


@pytest.fixture
def mock_dag():
    dag = MagicMock()
    dag.dag_id = "test-dag-001"
    dag.nodes = ["node-1", "node-2"]
    dag.topological_sort.return_value = [["node-1", "node-2"]]
    return dag


# ═══════════════════════════════════════════════════════════════════
# 1. TestSubmitLeaseFlow
# ═══════════════════════════════════════════════════════════════════


class TestSubmitLeaseFlow:
    """LAW 1, LAW 3, LAW 12: Submit creates ticket + lease + events."""

    def test_submit_returns_ticket(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1", "node-2"]]
        ticket = runtime.submit(mock_dag)
        assert isinstance(ticket, ExecutionTicket)
        assert ticket.ticket_id
        assert ticket.dag_id == "test-dag-001"

    def test_submit_acquires_lease(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1", "node-2"]]
        runtime.submit(mock_dag)
        mock_services["lease_manager"].acquire_lease.assert_called_once()

    def test_submit_schedules_dag(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1", "node-2"]]
        runtime.submit(mock_dag)
        mock_services["scheduler"].schedule.assert_called_once()

    def test_submit_publishes_events(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1", "node-2"]]
        runtime.submit(mock_dag)
        assert mock_services["event_bus"].publish.call_count >= 2

    def test_submit_rejects_empty_dag(self, runtime):
        with pytest.raises(SubmissionRejected):
            runtime.submit(None)


# ═══════════════════════════════════════════════════════════════════
# 2. TestCancelIntegrity
# ═══════════════════════════════════════════════════════════════════


class TestCancelIntegrity:
    """LAW 10, RULE 4: Cancel releases lease + kills sandbox + emits event."""

    def test_cancel_releases_lease(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        ticket = runtime.submit(mock_dag)
        runtime.cancel(ticket.ticket_id, reason="test")
        mock_services["lease_manager"].release_lease.assert_called_once()

    def test_cancel_returns_receipt(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        ticket = runtime.submit(mock_dag)
        receipt = runtime.cancel(ticket.ticket_id)
        assert isinstance(receipt, CancellationReceipt)
        assert receipt.cancelled is True

    def test_cancel_emits_event(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        ticket = runtime.submit(mock_dag)
        runtime.cancel(ticket.ticket_id, reason="test")
        calls = mock_services["event_bus"].publish.call_args_list
        topics = [c[0][0] for c in calls]
        assert any("cancelled" in t for t in topics)

    def test_cancel_unknown_ticket_raises(self, runtime):
        with pytest.raises(TicketNotFound):
            runtime.cancel("nonexistent")

    def test_cancel_force_kills_sandbox(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        ticket = runtime.submit(mock_dag)
        runtime.cancel(ticket.ticket_id, force=True)
        mock_services["sandbox_manager"].kill_all.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# 3. TestResumeCheckpoint
# ═══════════════════════════════════════════════════════════════════


class TestResumeCheckpoint:
    """LAW 4, LAW 8: Resume from checkpoint restores state."""

    def test_resume_returns_status(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1", "nodes": {},
        }
        ticket = runtime.submit(mock_dag)
        status = runtime.resume(ticket.ticket_id)
        assert isinstance(status, ExecutionStatus)
        assert status.ticket_id == ticket.ticket_id

    def test_resume_reacquires_lease(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1", "nodes": {},
        }
        ticket = runtime.submit(mock_dag)
        runtime.resume(ticket.ticket_id)
        assert mock_services["lease_manager"].acquire_lease.call_count >= 2

    def test_resume_emits_event(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1", "nodes": {},
        }
        ticket = runtime.submit(mock_dag)
        runtime.resume(ticket.ticket_id)
        calls = mock_services["event_bus"].publish.call_args_list
        topics = [c[0][0] for c in calls]
        assert any("resumed" in t for t in topics)

    def test_resume_missing_checkpoint_raises(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        mock_services["state_store"].read_trace.return_value = None
        ticket = runtime.submit(mock_dag)
        with pytest.raises(CheckpointMissing):
            runtime.resume(ticket.ticket_id)

    def test_resume_unknown_ticket_raises(self, runtime):
        with pytest.raises(TicketNotFound):
            runtime.resume("nonexistent")


# ═══════════════════════════════════════════════════════════════════
# 4. TestReplayDeterminism
# ═══════════════════════════════════════════════════════════════════


class TestReplayDeterminism:
    """LAW 4, LAW 7: Replay returns identical trace deterministically."""

    def test_replay_returns_ticket(self, runtime, mock_services):
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1", "nodes": {"n1": {}},
        }
        ticket = runtime.replay("exec-001", deterministic=True)
        assert isinstance(ticket, ReplayTicket)
        assert ticket.execution_id == "exec-001"
        assert ticket.deterministic is True

    def test_replay_creates_checkpoint(self, runtime, mock_services):
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1",
            "nodes": {"n1": {"state": "completed", "timestamp": 1000.0}},
        }
        runtime.replay("exec-001")
        assert mock_services["state_store"].store_checkpoint.called

    def test_replay_emits_event(self, runtime, mock_services):
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1", "nodes": {"n1": {}},
        }
        runtime.replay("exec-001")
        calls = mock_services["event_bus"].publish.call_args_list
        topics = [c[0][0] for c in calls]
        assert any("replay" in t for t in topics)

    def test_replay_missing_trace_raises(self, runtime, mock_services):
        mock_services["state_store"].read_trace.return_value = None
        with pytest.raises(CheckpointMissing):
            runtime.replay("exec-unknown")

    def test_replay_defaults_deterministic(self, runtime, mock_services):
        mock_services["state_store"].read_trace.return_value = {
            "session_id": "session-1", "nodes": {"n1": {}},
        }
        ticket = runtime.replay("exec-001")
        assert ticket.deterministic is True


# ═══════════════════════════════════════════════════════════════════
# 5. TestScaleQuotaEnforcement
# ═══════════════════════════════════════════════════════════════════


class TestScaleQuotaEnforcement:
    """LAW 10: Scale respects worker limits and quota boundaries."""

    def test_scale_up_adds_workers(self, runtime, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        receipt = runtime.scale(3, policy=ScalingPolicy.BALANCED)
        assert isinstance(receipt, ScalingReceipt)
        assert receipt.target_count == 3

    def test_scale_down_releases_leases(self, runtime, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        runtime.scale(2)
        runtime.scale(0)
        assert mock_services["lease_manager"].release_lease.called

    def test_scale_exceeds_max_raises(self, runtime):
        with pytest.raises(ScaleLimitExceeded) as exc:
            runtime.scale(999)
        assert "exceeds maximum" in str(exc.value).lower()

    def test_scale_negative_raises(self, runtime):
        with pytest.raises(ScaleError):
            runtime.scale(-1)

    def test_scale_emits_event(self, runtime, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        runtime.scale(2)
        calls = mock_services["event_bus"].publish.call_args_list
        topics = [c[0][0] for c in calls]
        assert any("scaled" in t for t in topics)


# ═══════════════════════════════════════════════════════════════════
# 6. TestObserveStateStream
# ═══════════════════════════════════════════════════════════════════


class TestObserveStateStream:
    """LAW 5: Execution state is observable in real time."""

    def test_observe_returns_stream(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        ticket = runtime.submit(mock_dag)
        state = runtime.observe(ticket.ticket_id)
        assert isinstance(state, LiveStateStream)
        assert state.ticket_id == ticket.ticket_id

    def test_observe_checks_heartbeat(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        ticket = runtime.submit(mock_dag)
        runtime.observe(ticket.ticket_id)
        assert mock_services["lease_manager"].monitor_heartbeat.called

    def test_observe_unknown_ticket_raises(self, runtime):
        with pytest.raises(TicketNotFound):
            runtime.observe("nonexistent")


# ═══════════════════════════════════════════════════════════════════
# 7. TestRegisterWorkerFlow
# ═══════════════════════════════════════════════════════════════════


class TestRegisterWorkerFlow:
    """§15.4: Worker registration validates manifest and creates lease."""

    def test_register_worker_returns_registration(self, runtime, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        manifest = {"worker_id": "worker-001", "capabilities": {"cpu": 4}}
        reg = runtime.register_worker(manifest)
        assert isinstance(reg, WorkerRegistration)
        assert reg.worker_id == "worker-001"
        assert reg.registered is True

    def test_register_worker_acquires_lease(self, runtime, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        manifest = {"worker_id": "worker-002", "capabilities": {}}
        runtime.register_worker(manifest)
        mock_services["lease_manager"].acquire_lease.assert_called_once()

    def test_register_worker_invalid_manifest_raises(self, runtime):
        with pytest.raises(WorkerRegistrationFailed):
            runtime.register_worker({})


# ═══════════════════════════════════════════════════════════════════
# 8. TestAPIRoutingSecurity
# ═══════════════════════════════════════════════════════════════════


class TestAPIRoutingSecurity:
    """RULE 1, LAW 13: API routes through services — no direct execution."""

    def test_no_direct_instance_of_execution_engine(self, runtime):
        attrs = dir(runtime)
        engine_names = [a for a in attrs if "execution" in a.lower()]
        for name in engine_names:
            val = getattr(runtime, name, None)
            if val is not None:
                type_name = type(val).__name__
                assert "executionengine" not in type_name.lower(), (
                    f"Direct {type_name} reference found on runtime"
                )

    def test_all_events_carry_trace_id(self, runtime, mock_dag, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        runtime.submit(mock_dag)
        for call in mock_services["event_bus"].publish.call_args_list:
            event = call[0][1]
            assert event.trace_id, "Event missing trace_id"

    def test_strict_mode_rejects_submit_none(self, runtime):
        with pytest.raises(Exception):
            runtime.submit(None)

    def test_no_cross_service_state_leakage(self, runtime, mock_services):
        mock_services["lease_manager"].acquire_lease.return_value = "lease-001"
        mock_services["scheduler"].schedule.return_value = [["node-1"]]
        runtime.submit(MagicMock(nodes=["n1"]))
        assert mock_services["dispatcher"].register_tool.called is False
        assert mock_services["retry_handler"].decide_retry.called is False
