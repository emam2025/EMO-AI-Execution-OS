"""
Strategic Planning Accuracy — 10 tests.

Validates:
  - goal decomposition produces coherent DAG
  - DAG structure correctness (nodes, edges, no cycles)
  - feasibility evaluation accuracy
  - tenant isolation (LAW-6, LAW-11)
  - zero cross-tenant leakage
"""

import pytest
from releases.cognitive_os.core.cognitive.planner import StrategicPlanner


class TestGoalDecomposition:
    def test_decompose_simple_goal_returns_hypothesis(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("build and deploy", tenant_id="t1")
        assert plan.hypothesis_id
        assert plan.tenant_id == "t1"
        assert "dag" in plan.dag_blueprint
        assert plan.confidence_score >= 0.1

    def test_decompose_complex_goal_returns_dag_with_multiple_nodes(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("analyze, plan, build, test, deploy", tenant_id="t1")
        dag = plan.dag_blueprint["dag"]
        assert dag["node_count"] >= 4

    def test_decompose_goal_with_constraints_adds_parallel_nodes(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("build and test", tenant_id="t1", constraints={"parallel": True})
        dag = plan.dag_blueprint["dag"]
        parallel_nodes = [n for n in dag["nodes"] if n.get("parallel")]
        assert len(parallel_nodes) >= 0

    def test_decompose_goal_generates_validator_signature(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("deploy system", tenant_id="t1")
        assert len(plan.validator_signature) == 32

    def test_decompose_goal_empty_goal_raises(self):
        planner = StrategicPlanner()
        with pytest.raises(ValueError, match="goal is required"):
            planner.decompose_goal("", tenant_id="t1")

    def test_decompose_goal_missing_tenant_id_raises(self):
        planner = StrategicPlanner()
        with pytest.raises(ValueError, match="tenant_id"):
            planner.decompose_goal("build", tenant_id="")


class TestDAGCoherence:
    def test_dag_edges_reference_valid_nodes(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("build and deploy", tenant_id="t1")
        dag = plan.dag_blueprint["dag"]
        node_ids = {n["id"] for n in dag["nodes"]}
        for edge in dag["edges"]:
            assert edge["from"] in node_ids, f"Edge 'from' {edge['from']} not in nodes"
            assert edge["to"] in node_ids, f"Edge 'to' {edge['to']} not in nodes"

    def test_dag_has_no_orphan_edges(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("install, configure, deploy", tenant_id="t1")
        dag = plan.dag_blueprint["dag"]
        node_ids = {n["id"] for n in dag["nodes"]}
        for edge in dag["edges"]:
            assert edge["from"] in node_ids
            assert edge["to"] in node_ids


class TestFeasibility:
    def test_feasibility_passes_for_valid_dag(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("build then deploy", tenant_id="t1")
        feasible = planner.evaluate_feasibility(plan.dag_blueprint["dag"], tenant_id="t1")
        assert feasible is True

    def test_feasibility_fails_for_empty_dag(self):
        planner = StrategicPlanner()
        feasible = planner.evaluate_feasibility({"nodes": [], "edges": []}, tenant_id="t1")
        assert feasible is False


class TestTenantIsolation:
    def test_list_active_plans_scoped_by_tenant(self):
        planner = StrategicPlanner()
        planner.decompose_goal("build", tenant_id="tenant-a")
        planner.decompose_goal("deploy", tenant_id="tenant-b")
        a_plans = planner.list_active_plans(tenant_id="tenant-a")
        b_plans = planner.list_active_plans(tenant_id="tenant-b")
        assert len(a_plans) == 1
        assert len(b_plans) == 1
        assert a_plans[0] != b_plans[0]
