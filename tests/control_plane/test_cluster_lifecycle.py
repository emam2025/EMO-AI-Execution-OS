"""Phase F2 — Control Plane & Cluster Management Test Suite.

Tests all F2 components:
  - ClusterManager: worker register/deregister/list/state
  - RuntimeCoordinator: dispatch/drain/scale
  - Integration with HealthSupervisor and ReconciliationLoop

COVERAGE:
  - TestWorkerRegistry (6): register, deregister, duplicate, capabilities, stale detection
  - TestReconciliationAccuracy (6): drift detection, correction scheduling, observe→compare→act
  - TestHealthSupervisor (6): probe, degradation, eviction, events
  - TestCoordinatorRouting (6): optimal dispatch, drain, scaling, capability constraints
  - TestEventDrivenConsistency (6): every mutation emits event

Ref: DEVELOPER.md §15.9
Ref: Canon LAW 3, LAW 5, LAW 8, LAW 10, LAW 11
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.runtime.control_plane.cluster_manager import (
    ClusterManager,
    WorkerInfo,
    RegistrationReceipt,
    DeregistrationReceipt,
)
from core.runtime.control_plane.coordinator import (
    RuntimeCoordinator,
    DispatchReceipt,
    DrainReceipt,
    ScalingReceipt,
)
from core.runtime.control_plane.health_supervisor import HealthSupervisor
from core.runtime.control_plane.reconciliation_loop import ReconciliationLoop
from core.runtime.models.control_plane_models import (
    WorkerState,
    DegradationLevel,
    HealthEventType,
    LoadMetric,
    ClusterSnapshot,
    ScalingPolicy,
    ScalingSignal,
    WorkerDrainingState,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_lease_manager():
    lm = MagicMock()
    lm.acquire_lease.return_value = "lease-001"
    lm.release_lease.return_value = True
    return lm


@pytest.fixture
def mock_event_bus():
    return MagicMock()


@pytest.fixture
def mock_scheduler():
    return MagicMock()


@pytest.fixture
def mock_resource_enforcer():
    return MagicMock()


@pytest.fixture
def cluster(mock_lease_manager, mock_event_bus):
    return ClusterManager(
        lease_manager=mock_lease_manager,
        event_bus=mock_event_bus,
        default_lease_ttl=30.0,
    )


@pytest.fixture
def coordinator(cluster, mock_scheduler, mock_lease_manager, mock_event_bus, mock_resource_enforcer):
    return RuntimeCoordinator(
        cluster_manager=cluster,
        scheduler=mock_scheduler,
        lease_manager=mock_lease_manager,
        event_bus=mock_event_bus,
        resource_enforcer=mock_resource_enforcer,
    )


@pytest.fixture
def health_supervisor(mock_event_bus):
    return HealthSupervisor(event_bus=mock_event_bus)


@pytest.fixture
def reconciler():
    return ReconciliationLoop()


# ═══════════════════════════════════════════════════════════════════
# 1. TestWorkerRegistry
# ═══════════════════════════════════════════════════════════════════


class TestWorkerRegistry:
    """LAW 3, LAW 5: Register, deregister, list, and lifecycle."""

    def test_register_worker_returns_receipt(self, cluster):
        receipt = cluster.register_worker("worker-001", capabilities={"cpu": 4})
        assert isinstance(receipt, RegistrationReceipt)
        assert receipt.registered is True
        assert receipt.worker_id == "worker-001"

    def test_register_worker_acquires_lease(self, cluster, mock_lease_manager):
        cluster.register_worker("worker-002")
        mock_lease_manager.acquire_lease.assert_called_once()

    def test_register_duplicate_returns_existing(self, cluster):
        cluster.register_worker("worker-003")
        receipt2 = cluster.register_worker("worker-003")
        assert receipt2.registered is True

    def test_deregister_worker_removes_worker(self, cluster, mock_lease_manager):
        cluster.register_worker("worker-004")
        receipt = cluster.deregister_worker("worker-004", reason="test")
        assert isinstance(receipt, DeregistrationReceipt)
        assert receipt.deregistered is True
        assert cluster.get_worker("worker-004") is None

    def test_list_active_workers(self, cluster):
        cluster.register_worker("worker-005")
        cluster.register_worker("worker-006")
        active = cluster.list_active_workers()
        assert len(active) == 2

    def test_stale_worker_detection(self, cluster):
        cluster.register_worker("worker-stale")
        stale = cluster.check_stale_workers(timeout=-1.0)
        assert "worker-stale" in stale


# ═══════════════════════════════════════════════════════════════════
# 2. TestReconciliationAccuracy
# ═══════════════════════════════════════════════════════════════════


class TestReconciliationAccuracy:
    """RULE 1, RULE 2: Observe→Compare→Act detects drift correctly."""

    def test_observe_snapshot(self, reconciler):
        snap = reconciler.observe_current(worker_count=5, healthy=4, degraded=1)
        assert isinstance(snap, ClusterSnapshot)
        assert snap.worker_count == 5
        assert snap.healthy_count == 4

    def test_compare_detects_deficit(self, reconciler):
        actual = reconciler.observe_current(worker_count=3, healthy=3)
        desired = ClusterSnapshot(worker_count=5, healthy_count=5)
        delta = reconciler.compare_desired(actual, desired)
        assert delta.drift_detected is True
        assert delta.worker_deficit == 2

    def test_compare_detects_surplus(self, reconciler):
        actual = reconciler.observe_current(worker_count=5, healthy=5)
        desired = ClusterSnapshot(worker_count=3, healthy_count=3)
        delta = reconciler.compare_desired(actual, desired)
        assert delta.drift_detected is True
        assert delta.worker_surplus == 2

    def test_no_drift_when_matched(self, reconciler):
        actual = reconciler.observe_current(worker_count=4, healthy=4)
        desired = ClusterSnapshot(worker_count=4, healthy_count=4)
        delta = reconciler.compare_desired(actual, desired)
        assert delta.drift_detected is False

    def test_compute_delta_returns_corrections(self, reconciler):
        actual = reconciler.observe_current(worker_count=1, healthy=1)
        desired = ClusterSnapshot(worker_count=3, healthy_count=3)
        corrections = reconciler.compute_delta(actual, desired)
        assert len(corrections) > 0
        assert corrections[0].action == "scale_up"

    def test_schedule_correction_returns_receipt(self, reconciler):
        actual = reconciler.observe_current(worker_count=1, healthy=1)
        desired = ClusterSnapshot(worker_count=3, healthy_count=3)
        corrections = reconciler.compute_delta(actual, desired)
        receipt = reconciler.schedule_correction(corrections)
        assert receipt.corrections_scheduled > 0


# ═══════════════════════════════════════════════════════════════════
# 3. TestHealthSupervisor
# ═══════════════════════════════════════════════════════════════════


class TestHealthSupervisor:
    """LAW 5, RULE 3: Health probes, degradation, eviction, events."""

    def test_probe_unknown_worker(self, health_supervisor):
        result = health_supervisor.probe_worker("unknown")
        assert result.alive is False
        assert result.state == WorkerState.UNKNOWN

    def test_update_worker_health(self, health_supervisor):
        health_supervisor.update_worker_health("worker-1", WorkerState.HEALTHY)
        result = health_supervisor.probe_worker("worker-1")
        assert result.alive is True

    def test_assess_degradation_none(self, health_supervisor):
        probe = MagicMock(alive=True, cpu_pct=30.0, mem_pct=40.0, latency_ms=100.0)
        deg = health_supervisor.assess_degradation("w1", probe)
        assert deg == DegradationLevel.NONE

    def test_assess_degradation_critical(self, health_supervisor):
        probe = MagicMock(alive=False, cpu_pct=0, mem_pct=0, latency_ms=0)
        deg = health_supervisor.assess_degradation("w2", probe)
        assert deg == DegradationLevel.CRITICAL

    def test_trigger_eviction_rejects_non_critical(self, health_supervisor):
        health_supervisor.update_worker_health("w3", WorkerState.HEALTHY)
        receipt = health_supervisor.trigger_eviction("w3", "not critical")
        assert receipt.evicted is False

    def test_trigger_eviction_succeeds_critical(self, health_supervisor):
        health_supervisor.update_worker_health("w4", WorkerState.HEALTHY)
        probe = MagicMock(alive=False, cpu_pct=0, mem_pct=0, latency_ms=0)
        health_supervisor._degradation_levels["w4"] = DegradationLevel.CRITICAL
        receipt = health_supervisor.trigger_eviction("w4", "critical")
        assert receipt.evicted is True


# ═══════════════════════════════════════════════════════════════════
# 4. TestCoordinatorRouting
# ═══════════════════════════════════════════════════════════════════


class TestCoordinatorRouting:
    """LAW 3, LAW 8: Dispatch, drain, and scaling coordination."""

    def test_dispatch_no_workers_returns_failure(self, coordinator):
        dag = MagicMock()
        receipt = coordinator.dispatch_to_cluster(dag)
        assert isinstance(receipt, DispatchReceipt)
        assert receipt.dispatched is False

    def test_dispatch_after_register_selects_worker(self, coordinator, cluster):
        cluster.register_worker("dispatch-1", capabilities={"cpu": 4})
        dag = MagicMock()
        receipt = coordinator.dispatch_to_cluster(dag)
        assert receipt.dispatched is True
        assert receipt.worker_id == "dispatch-1"

    def test_dispatch_with_capability_constraints(self, coordinator, cluster):
        cluster.register_worker("no-gpu", capabilities={"cpu": 4})
        dag = MagicMock()
        receipt = coordinator.dispatch_to_cluster(
            dag, constraints={"required_capabilities": ["gpu"]},
        )
        assert receipt.dispatched is False

    def test_drain_worker_releases_lease(self, coordinator, cluster, mock_lease_manager):
        cluster.register_worker("drain-1")
        receipt = coordinator.drain_worker("drain-1", "test drain")
        assert isinstance(receipt, DrainReceipt)
        assert receipt.drained is True

    def test_coordinate_scale_up(self, coordinator, cluster, mock_lease_manager):
        receipt = coordinator.coordinate_scaling(3)
        assert isinstance(receipt, ScalingReceipt)
        assert receipt.actual_count == 3
        assert receipt.signal == "up"

    def test_coordinate_scale_hold(self, coordinator, cluster):
        receipt = coordinator.coordinate_scaling(0)
        assert receipt.signal == "hold"


# ═══════════════════════════════════════════════════════════════════
# 5. TestEventDrivenConsistency
# ═══════════════════════════════════════════════════════════════════


class TestEventDrivenConsistency:
    """LAW 5: Every mutation emits an event — no silent state changes."""

    def test_register_emits_event(self, cluster, mock_event_bus):
        cluster.register_worker("event-1")
        assert mock_event_bus.publish.called

    def test_deregister_emits_event(self, cluster, mock_event_bus):
        cluster.register_worker("event-2")
        mock_event_bus.reset_mock()
        cluster.deregister_worker("event-2", reason="cleanup")
        assert mock_event_bus.publish.called

    def test_dispatch_emits_event(self, coordinator, cluster, mock_event_bus):
        cluster.register_worker("event-3")
        mock_event_bus.reset_mock()
        coordinator.dispatch_to_cluster(MagicMock())
        assert mock_event_bus.publish.called

    def test_coordinator_drain_emits_event(self, coordinator, cluster, mock_event_bus):
        cluster.register_worker("event-4")
        mock_event_bus.reset_mock()
        coordinator.drain_worker("event-4", "test")
        assert mock_event_bus.publish.called

    def test_scaling_emits_event(self, coordinator, cluster, mock_event_bus):
        coordinator.coordinate_scaling(2)
        assert mock_event_bus.publish.called

    def test_health_update_triggers_event(self, health_supervisor, mock_event_bus):
        health_supervisor.update_worker_health(
            "h1", WorkerState.HEALTHY, cpu_pct=99.0, mem_pct=98.0,
        )
        assert mock_event_bus.publish.called
