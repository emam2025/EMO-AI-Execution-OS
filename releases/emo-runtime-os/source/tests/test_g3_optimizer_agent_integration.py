"""Phase G3 — Optimizer Agent Integration Tests.  # LAW-14 LAW-15 LAW-16 RULE-3

End-to-end integration tests: evaluate_plan → propose_optimization
→ apply_topology_patch → publish_report. Exercises safe patch guards,
DAG integrity enforcement, fairness validation, trace propagation,
and determinism guard.

Ref: Canon LAW 14, LAW 15, LAW 16, RULE 1, RULE 3, RULE 5
Ref: artifacts/design/g3/04_integration_blueprint.md
"""

from __future__ import annotations

import pytest

from core.runtime.optimizer.cost_optimizer import CostOptimizer
from core.runtime.optimizer.dag_topology_optimizer import DAGTopologyOptimizer
from core.runtime.optimizer.optimization_state_machine import (
    OptimizationState,
    OptimizationStateMachine,
)
from core.runtime.optimizer.optimizer_agent import OptimizerAgent
from core.runtime.optimizer.resource_balancer import ResourceBalancer
from core.runtime.optimizer.trace_correlator import OptimizerTraceCorrelator


class TestG3IntegrationHappyPath:
    """Happy path: evaluate → propose → apply → report."""

    @pytest.fixture
    def agent(self) -> OptimizerAgent:
        topology = DAGTopologyOptimizer()
        cost = CostOptimizer()
        balancer = ResourceBalancer()
        sm = OptimizationStateMachine()
        corr = OptimizerTraceCorrelator()
        return OptimizerAgent(topology, cost, balancer, sm, corr)

    @staticmethod
    def _plan() -> dict:
        return {
            "nodes": [{"node_id": "n1", "type": "task"}, {"node_id": "n2", "type": "task"}],
            "dag_topology": [{"from": "n1", "to": "n2"}],
        }

    def test_evaluate_plan_happy(self, agent: OptimizerAgent):
        evaluation = agent.evaluate_plan("plan_001", self._plan(), {"worker_snapshots": [], "node_assignments": {}})
        assert evaluation["evaluation_score"] > 0

    def test_propose_optimization_no_proposals_when_approved(self, agent: OptimizerAgent):
        evaluation = agent.evaluate_plan("plan_001", self._plan(), {"worker_snapshots": [], "node_assignments": {}})
        evaluation["evaluation_score"] = 0.98
        proposals = agent.propose_optimization("plan_001", evaluation, {"max_cpu": 1000})
        assert proposals == []

    def test_propose_optimization_returns_proposals(self, agent: OptimizerAgent):
        evaluation = agent.evaluate_plan("plan_p", self._plan(), {"worker_snapshots": [], "node_assignments": {}})
        proposals = agent.propose_optimization("plan_p", evaluation, {"max_cpu": 1000})
        assert len(proposals) > 0

    def test_apply_topology_patch_happy(self, agent: OptimizerAgent):
        p = self._plan()
        evaluation = agent.evaluate_plan("plan_a", p, {"worker_snapshots": [], "node_assignments": {}})
        proposals = agent.propose_optimization("plan_a", evaluation, {"max_cpu": 1000})
        if proposals:
            result = agent.apply_topology_patch("plan_a", proposals[0], p["dag_topology"])
            assert result["patch_applied"]
            assert result["integrity_check"]

    def test_full_lifecycle(self, agent: OptimizerAgent):
        p = self._plan()
        evaluation = agent.evaluate_plan("plan_f", p, {"worker_snapshots": [], "node_assignments": {}})
        proposals = agent.propose_optimization("plan_f", evaluation, {"max_cpu": 1000})
        if proposals:
            agent.apply_topology_patch("plan_f", proposals[0], p["dag_topology"])
        agent.publish_report("plan_f", {"optimizer_trace_id": proposals[0].get("optimizer_trace_id", "") if proposals else ""})


class TestG3IntegrationFailure:
    """Failure paths: missing DAG, invalid patches, integrity fail."""

    @pytest.fixture
    def agent(self) -> OptimizerAgent:
        topology = DAGTopologyOptimizer()
        cost = CostOptimizer()
        balancer = ResourceBalancer()
        sm = OptimizationStateMachine()
        corr = OptimizerTraceCorrelator()
        return OptimizerAgent(topology, cost, balancer, sm, corr)

    @staticmethod
    def _plan() -> dict:
        return {
            "nodes": [{"node_id": "n1", "type": "task"}, {"node_id": "n2", "type": "task"}],
            "dag_topology": [{"from": "n1", "to": "n2"}],
        }

    def test_evaluate_plan_missing_nodes_raises(self, agent: OptimizerAgent):
        plan = {"nodes": [], "dag_topology": []}
        with pytest.raises(RuntimeError, match="nodes or dag_topology"):
            agent.evaluate_plan("plan_e", plan, {})

    def test_apply_topology_patch_safe_guard_fail(self, agent: OptimizerAgent):
        p = self._plan()
        evaluation = agent.evaluate_plan("plan_b", p, {"worker_snapshots": [], "node_assignments": {}})
        proposals = agent.propose_optimization("plan_b", evaluation, {"max_cpu": 1000})
        if proposals:
            bad_patch = dict(proposals[0])
            bad_patch["estimated_cost_delta_pct"] = -1.0
            bad_patch["latency_impact_pct"] = -1.0
            with pytest.raises(RuntimeError, match="Safe Patch Guard rejected"):
                agent.apply_topology_patch("plan_b", bad_patch, p["dag_topology"])

    def test_reset_clears_state(self, agent: OptimizerAgent):
        agent.evaluate_plan("plan_r", self._plan(), {})
        agent.reset()
        assert agent.state_machine.current == OptimizationState.PLAN_RECEIVED


class TestG3Determinism:
    """Deterministic hashing stability (RULE 1)."""

    def test_deterministic_hash_stable(self):
        sm = OptimizationStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, {"c": 3})
        h2 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, {"c": 3})
        assert h1 == h2

    def test_deterministic_cache_hit(self):
        sm = OptimizationStateMachine()
        result = {"score": 0.9}
        sm.cache_deterministic_review({"a": 1}, {"b": 2}, {"c": 3}, result)
        hit, cached = sm.check_deterministic_review({"a": 1}, {"b": 2}, {"c": 3})
        assert hit
        assert cached == result
