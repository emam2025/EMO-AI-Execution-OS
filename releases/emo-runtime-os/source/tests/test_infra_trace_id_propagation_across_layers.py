"""Phase I1 — Infra Trace ID Propagation Tests.  # LAW-5 LAW-12

Tests that infra_trace_id is correctly generated, propagated across
F2 → I1 → F4 layers, and never lost between infrastructure operations.

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
Ref: artifacts/design/i1/04_integration_blueprint.md §3
"""

from __future__ import annotations

import pytest

from core.runtime.infra.trace_correlator import InfraTraceCorrelator
from core.runtime.infra.kubernetes_deployer import KubernetesDeployer
from core.runtime.infra.distributed_queue import DistributedQueue
from core.runtime.infra.ha_orchestrator import HAOrchestrator
from core.runtime.infra.object_storage import ObjectStorage
from core.runtime.infra.ha_state_machine import HAStateMachine
from core.runtime.event_bus import InMemoryEventBus


# ── Test Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def correlator() -> InfraTraceCorrelator:
    return InfraTraceCorrelator()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def deployer(event_bus: InMemoryEventBus) -> KubernetesDeployer:
    return KubernetesDeployer(event_bus=event_bus)


@pytest.fixture
def queue(event_bus: InMemoryEventBus) -> DistributedQueue:
    return DistributedQueue(event_bus=event_bus)


@pytest.fixture
def orchestrator(event_bus: InMemoryEventBus) -> HAOrchestrator:
    return HAOrchestrator(event_bus=event_bus, state_machine=HAStateMachine())


@pytest.fixture
def storage() -> ObjectStorage:
    return ObjectStorage()


@pytest.fixture
def infra_trace_id(correlator: InfraTraceCorrelator) -> str:
    return correlator.generate_infra_trace_id("msn_test_001", "integration_test")


# ── TestTraceIdGeneration (4 tests) ─────────────────────────────────────────


class TestTraceIdGeneration:
    """LAW 12: Trace ID must be deterministic and unique."""

    def test_generates_valid_format(self, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_abc", "deploy")
        assert tid.startswith("infra_")
        assert len(tid) > 10

    def test_different_operations_different_ids(self, correlator: InfraTraceCorrelator):
        tid1 = correlator.generate_infra_trace_id("msn_abc", "deploy")
        tid2 = correlator.generate_infra_trace_id("msn_abc", "scale")
        assert tid1 != tid2

    def test_different_missions_different_ids(self, correlator: InfraTraceCorrelator):
        tid1 = correlator.generate_infra_trace_id("msn_abc", "deploy")
        tid2 = correlator.generate_infra_trace_id("msn_xyz", "deploy")
        assert tid1 != tid2

    def test_same_input_different_timestamps(self, correlator: InfraTraceCorrelator):
        tid1 = correlator.generate_infra_trace_id("msn_abc", "deploy")
        tid2 = correlator.generate_infra_trace_id("msn_abc", "deploy")
        assert tid1 != tid2  # timestamp ensures uniqueness


# ── TestTracePropagation (5 tests) ──────────────────────────────────────────


class TestTracePropagation:
    """LAW 5: infra_trace_id must propagate across all layers."""

    def test_propagates_to_f2(self, correlator: InfraTraceCorrelator, infra_trace_id: str):
        result = correlator.propagate_to_f2(infra_trace_id, "dep_001")
        assert result["target_layer"] == "f2_control_plane"
        assert result["infra_trace_id"] == infra_trace_id
        assert correlator.correlation_for(infra_trace_id, "f2_control_plane") == "dep_001"

    def test_propagates_to_f4(self, correlator: InfraTraceCorrelator, infra_trace_id: str):
        result = correlator.propagate_to_f4(infra_trace_id)
        assert result["target_layer"] == "f4_observability"
        assert result["infra_trace_id"] == infra_trace_id

    def test_propagates_to_queue(self, correlator: InfraTraceCorrelator, infra_trace_id: str):
        result = correlator.propagate_to_queue(infra_trace_id, "msg_001")
        assert result["target_layer"] == "i1_queue"
        assert correlator.correlation_for(infra_trace_id, "i1_queue") == "msg_001"

    def test_propagates_to_k8s(self, correlator: InfraTraceCorrelator, infra_trace_id: str):
        result = correlator.propagate_to_k8s(infra_trace_id, "dep_001")
        assert result["target_layer"] == "i1_k8s"

    def test_trace_chain_contains_all_layers(self, correlator: InfraTraceCorrelator, infra_trace_id: str):
        correlator.propagate_to_f2(infra_trace_id, "dep_001")
        correlator.propagate_to_f4(infra_trace_id)
        correlator.propagate_to_queue(infra_trace_id, "msg_001")
        chain = correlator.trace_chain(infra_trace_id)
        assert "f2_control_plane" in chain["layers"]
        assert "f4_observability" in chain["layers"]
        assert "i1_queue" in chain["layers"]


# ── TestEndToEndPropagation (5 tests) ───────────────────────────────────────


class TestEndToEndPropagation:
    """Full end-to-end: deploy → queue → HA → storage across layers."""

    def test_deploy_propagates_trace_id(self, deployer: KubernetesDeployer, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_e2e", "deploy")
        manifest = {"runtime_version": "v1.0.0", "worker_pods": 3, "namespace": "test"}
        result = deployer.deploy_runtime(manifest, tid)
        assert result["status"] == "deployed"
        correlator.propagate_to_k8s(tid, result["deployment_id"])
        assert correlator.correlation_for(tid, "i1_k8s") == result["deployment_id"]

    def test_queue_preserves_trace_id(self, queue: DistributedQueue, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_e2e", "queue")
        result = queue.enqueue({"action": "test"}, "runtime.execution", infra_trace_id=tid)
        assert result["msg_id"]
        correlator.propagate_to_queue(tid, result["msg_id"])
        assert correlator.correlation_for(tid, "i1_queue") == result["msg_id"]

    def test_ha_orchestrator_with_trace(self, orchestrator: HAOrchestrator, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_e2e", "ha")
        candidates = [{"node_id": "node1", "lease_holder": "node1"},
                      {"node_id": "node2", "lease_holder": ""},
                      {"node_id": "node3", "lease_holder": ""}]
        result = orchestrator.elect_leader("cluster_test", candidates, tid)
        correlator.propagate_to_ha(tid, "cluster_test", result.get("term", 0))
        assert correlator.correlation_for(tid, "i1_ha")

    def test_storage_preserves_trace_id(self, storage: ObjectStorage, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_e2e", "storage")
        uri = "s3://bucket/key"
        result = storage.store_artifact(uri, b"test data", "text/plain", infra_trace_id=tid)
        assert result["stored"]
        correlator.propagate_to_storage(tid, uri)
        assert correlator.correlation_for(tid, "i1_storage")

    def test_full_pipeline_trace(self, correlator: InfraTraceCorrelator):
        """Simulate full F2→I1→F4 trace flow."""
        mission_id = "msn_pipeline"
        tid = correlator.generate_infra_trace_id(mission_id, "pipeline")

        # F2 deploys
        correlator.propagate_to_f2(tid, "dep_pipeline")
        # I1 queue processes
        correlator.propagate_to_queue(tid, "msg_pipeline")
        # I1 K8s deploys
        correlator.propagate_to_k8s(tid, "dep_pipeline")
        # F4 observes
        correlator.propagate_to_f4(tid)

        chain = correlator.trace_chain(tid)
        assert len(chain["layers"]) == 4
        assert "f2_control_plane" in chain["layers"]
        assert "i1_queue" in chain["layers"]
        assert "i1_k8s" in chain["layers"]
        assert "f4_observability" in chain["layers"]

    def test_all_components_receive_infra_trace_id(
        self, deployer: KubernetesDeployer, queue: DistributedQueue,
        orchestrator: HAOrchestrator, storage: ObjectStorage,
        correlator: InfraTraceCorrelator,
    ):
        tid = correlator.generate_infra_trace_id("msn_all_comp", "test")
        manifest = {"runtime_version": "v1", "worker_pods": 2, "namespace": "test"}
        dep_result = deployer.deploy_runtime(manifest, tid)
        assert dep_result["status"] == "deployed"

        q_result = queue.enqueue({"action": "scale"}, "runtime.scaling", infra_trace_id=tid)
        assert q_result["msg_id"]

        candidates = [{"node_id": "n1", "lease_holder": "n1"}]
        ha_result = orchestrator.elect_leader("cluster_all", candidates, tid)
        assert ha_result.get("leader_id")

        s_result = storage.store_artifact("s3://b/k", b"data", "text/plain", infra_trace_id=tid)
        assert s_result["stored"]


# ── TestCorrelationResolution (3 tests) ─────────────────────────────────────


class TestCorrelationResolution:
    def test_resolve_mission_trace_id(self, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_abc123", "test")
        # correlation records layers
        correlator.propagate_to_f2(tid, "dep_001")
        correlator.propagate_to_f4(tid)
        assert tid in correlator.all_traces()

    def test_trace_chain_returns_empty_for_unknown(self, correlator: InfraTraceCorrelator):
        chain = correlator.trace_chain("unknown_id")
        assert chain == {}

    def test_reset_clears_all(self, correlator: InfraTraceCorrelator):
        tid = correlator.generate_infra_trace_id("msn_abc", "test")
        correlator.propagate_to_f2(tid, "dep_001")
        assert len(correlator.all_traces()) > 0
        correlator.reset()
        assert len(correlator.all_traces()) == 0
