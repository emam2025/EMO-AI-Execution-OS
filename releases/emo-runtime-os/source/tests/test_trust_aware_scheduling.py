"""Tests for Phase E4 — Trust-Aware Scheduling.

Trust Levels, Trust Routing Rules, Worker Trust Classification.
"""

import pytest

from core.security.capabilities import TrustLevel
from core.control_plane.state.system_state import SystemStateBrain, LoadMetrics
from core.control_plane.orchestrator import ExecutionOrchestrator
from core.runtime.mesh.service_registry import ServiceInstance
from core.runtime.control.worker_orchestrator import Worker, WorkerState


# ═══════════════════════════════════════════════════════════════════
# E4 — TrustLevel Enum
# ═══════════════════════════════════════════════════════════════════

class TestTrustLevel:
    def test_enum_values(self):
        assert TrustLevel.UNVERIFIED.value == "unverified"
        assert TrustLevel.REMOTE.value == "remote"
        assert TrustLevel.TRUSTED.value == "trusted"

    def test_ordering(self):
        levels = [TrustLevel.UNVERIFIED, TrustLevel.TRUSTED, TrustLevel.REMOTE]
        assert TrustLevel.TRUSTED in levels


# ═══════════════════════════════════════════════════════════════════
# E4 — Trust Routing in ExecutionOrchestrator
# ═══════════════════════════════════════════════════════════════════

class TestTrustRouting:
    def test_trusted_node_scored_higher(self):
        state = SystemStateBrain()
        state.register_node("trusted_node")
        state.register_node("unverified_node")
        state.register_worker("w1", node_id="trusted_node", capacity=5)
        state.register_worker("w2", node_id="unverified_node", capacity=5)
        # Set trust levels
        w1 = state.get_worker("w1")
        w1.trust_level = TrustLevel.TRUSTED
        w2 = state.get_worker("w2")
        w2.trust_level = TrustLevel.UNVERIFIED
        state.update_load_metrics("trusted_node", LoadMetrics(cpu_avg=0.3))
        state.update_load_metrics("unverified_node", LoadMetrics(cpu_avg=0.3))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state)
        assert node == "trusted_node"

    def test_remote_node_middle_score(self):
        state = SystemStateBrain()
        state.register_node("trusted")
        state.register_node("remote")
        state.register_worker("w1", node_id="trusted", capacity=5)
        state.register_worker("w2", node_id="remote", capacity=5)
        w1 = state.get_worker("w1")
        w1.trust_level = TrustLevel.TRUSTED
        w2 = state.get_worker("w2")
        w2.trust_level = TrustLevel.REMOTE
        state.update_load_metrics("trusted", LoadMetrics(cpu_avg=0.3))
        state.update_load_metrics("remote", LoadMetrics(cpu_avg=0.3))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state)
        assert node == "trusted"

    def test_load_overrides_trust_when_significant(self):
        state = SystemStateBrain()
        state.register_node("trusted_loaded")
        state.register_node("remote_free")
        state.register_worker("w1", node_id="trusted_loaded", capacity=5)
        state.register_worker("w2", node_id="remote_free", capacity=5)
        w1 = state.get_worker("w1")
        w1.trust_level = TrustLevel.TRUSTED
        w2 = state.get_worker("w2")
        w2.trust_level = TrustLevel.REMOTE
        # trusted node is nearly full, remote is very free
        state.update_load_metrics("trusted_loaded", LoadMetrics(cpu_avg=0.95, error_rate=0.01))
        state.update_load_metrics("remote_free", LoadMetrics(cpu_avg=0.05, error_rate=0.01))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state)
        assert node == "remote_free"

    def test_select_worker_prefers_trusted(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w_trusted", node_id="n1", capacity=5)
        state.register_worker("w_unverified", node_id="n1", capacity=5)
        w1 = state.get_worker("w_trusted")
        w1.trust_level = TrustLevel.TRUSTED
        w2 = state.get_worker("w_unverified")
        w2.trust_level = TrustLevel.UNVERIFIED

        orch = ExecutionOrchestrator()
        wid = orch.select_worker("n1", {}, state)
        assert wid == "w_trusted"

    def test_select_worker_trusted_then_load(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w_trusted_busy", node_id="n1", capacity=5)
        state.register_worker("w_trusted_free", node_id="n1", capacity=5)
        w1 = state.get_worker("w_trusted_busy")
        w1.trust_level = TrustLevel.TRUSTED
        w1.active_tasks = 4
        w2 = state.get_worker("w_trusted_free")
        w2.trust_level = TrustLevel.TRUSTED

        orch = ExecutionOrchestrator()
        wid = orch.select_worker("n1", {}, state)
        assert wid == "w_trusted_free"

    def test_select_worker_no_workers_raises(self):
        state = SystemStateBrain()
        state.register_node("n1")
        orch = ExecutionOrchestrator()
        with pytest.raises(RuntimeError):
            orch.select_worker("n1", {}, state)


# ═══════════════════════════════════════════════════════════════════
# E4 — Worker & ServiceInstance Trust Level
# ═══════════════════════════════════════════════════════════════════

class TestWorkerTrustLevel:
    def test_worker_info_default_trusted(self):
        state = SystemStateBrain()
        w = state.register_worker("w1")
        assert w.trust_level == TrustLevel.TRUSTED

    def test_worker_info_set_trust_level(self):
        state = SystemStateBrain()
        w = state.register_worker("w1")
        w.trust_level = TrustLevel.REMOTE
        assert w.trust_level == TrustLevel.REMOTE

    def test_service_instance_default_trusted(self):
        si = ServiceInstance(service_name="test", instance_id="i1")
        assert si.trust_level == TrustLevel.TRUSTED

    def test_worker_orchestrator_default_trusted(self):
        w = Worker(worker_id="w1")
        assert w.trust_level == TrustLevel.TRUSTED

    def test_worker_orchestrator_trust_level_custom(self):
        w = Worker(worker_id="w1", trust_level=TrustLevel.UNVERIFIED)
        assert w.trust_level == TrustLevel.UNVERIFIED


# ═══════════════════════════════════════════════════════════════════
# E4 — Integration
# ═══════════════════════════════════════════════════════════════════

class TestTrustIntegration:
    def test_trusted_node_with_failure_penalty(self):
        state = SystemStateBrain()
        state.register_node("trusted_failing")
        state.register_node("remote_clean")
        state.register_worker("w1", node_id="trusted_failing", capacity=5)
        state.register_worker("w2", node_id="remote_clean", capacity=5)
        w1 = state.get_worker("w1")
        w1.trust_level = TrustLevel.TRUSTED
        w2 = state.get_worker("w2")
        w2.trust_level = TrustLevel.REMOTE
        state.update_load_metrics("trusted_failing", LoadMetrics(cpu_avg=0.3))
        state.update_load_metrics("remote_clean", LoadMetrics(cpu_avg=0.3))
        # Add failures to trusted node
        for i in range(5):
            state.record_failure("trusted_failing", f"e{i}", "timeout")

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state)
        # Remote node should win due to failure penalty on trusted
        assert node == "remote_clean"

    def test_mixed_trust_level_routing(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_node("n2")
        state.register_worker("w_trusted", node_id="n1", capacity=5)
        state.register_worker("w_unverified", node_id="n2", capacity=5)
        w1 = state.get_worker("w_trusted")
        w1.trust_level = TrustLevel.TRUSTED
        w2 = state.get_worker("w_unverified")
        w2.trust_level = TrustLevel.UNVERIFIED
        state.update_load_metrics("n1", LoadMetrics(cpu_avg=0.3))
        state.update_load_metrics("n2", LoadMetrics(cpu_avg=0.3))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "sensitive_task"}, state)
        assert node == "n1"
