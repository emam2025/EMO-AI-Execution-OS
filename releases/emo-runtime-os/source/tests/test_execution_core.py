"""Tests for ExecutionCore — pure logic layer."""

import pytest
from core.execution_core import ExecutionCore, FailureIntelligence, FailurePattern, DAGBuilder
from core.contracts import SUPPORTED_SCHEMA_VERSIONS
from core.models.dag import DependencyGraph, NodeState, PlanNode, PlanEdge


class TestFailureIntelligence:
    def test_record_and_query(self):
        fi = FailureIntelligence()
        fi.record_result("tool_a", "fast", success=True)
        fi.record_result("tool_a", "fast", success=False)
        assert fi.failure_rate("tool_a", "fast") == 0.5

    def test_no_data_returns_zero(self):
        fi = FailureIntelligence()
        assert fi.failure_rate("unknown", "fast") == 0.0

    def test_top_patterns_orders_by_rate(self):
        fi = FailureIntelligence()
        fi.record_result("t1", "s1", success=False)
        fi.record_result("t1", "s1", success=False)
        fi.record_result("t2", "s2", success=True)
        top = fi.top_patterns(5)
        assert len(top) == 2
        assert top[0].failure_rate >= top[1].failure_rate

    def test_suggest_alternative(self):
        fi = FailureIntelligence()
        fi.record_result("t", "slow", success=False)
        fi.record_result("t", "slow", success=False)
        fi.record_result("t", "slow", success=False)
        fi.record_result("t", "fast", success=True)
        fi.record_result("t", "fast", success=True)
        fi.record_result("t", "fast", success=True)
        suggestion = fi.suggest_alternative("t", "slow")
        assert suggestion == "fast"

    def test_suggest_returns_none_if_low_rate(self):
        fi = FailureIntelligence()
        fi.record_result("t", "s1", success=True)
        assert fi.suggest_alternative("t", "s1") is None

    def test_report_structure(self):
        fi = FailureIntelligence()
        fi.record_result("t", "s", success=False)
        report = fi.report()
        assert "patterns" in report
        assert "total_correlations" in report
        assert report["total_correlations"] == 1


class TestExecutionCoreValidation:
    def test_check_schema_version_passes(self):
        dag = DependencyGraph()
        ExecutionCore.check_schema_version(dag)
        assert dag.version in SUPPORTED_SCHEMA_VERSIONS

    def test_check_schema_version_raises_for_unknown(self):
        dag = DependencyGraph()
        dag.version = "0.0.0"
        with pytest.raises(Exception):
            ExecutionCore.check_schema_version(dag)

    def test_validate_transition_valid(self):
        node = PlanNode(id="n1")
        assert ExecutionCore.validate_transition(node, NodeState.PLANNED) is True

    def test_validate_transition_invalid(self):
        node = PlanNode(id="n1", state=NodeState.COMPLETED)
        assert ExecutionCore.validate_transition(node, NodeState.RUNNING) is False


class TestExecutionCoreTransitions:
    def test_get_event_type_for_transition_planned_to_running(self):
        t = ExecutionCore.get_event_type_for_transition(NodeState.PLANNED, NodeState.RUNNING)
        assert t == "NODE_STARTED"

    def test_get_event_type_for_transition_running_to_completed(self):
        t = ExecutionCore.get_event_type_for_transition(NodeState.RUNNING, NodeState.COMPLETED)
        assert t == "NODE_COMPLETED"

    def test_get_event_type_for_transition_unknown_falls_back(self):
        t = ExecutionCore.get_event_type_for_transition(NodeState.PENDING, NodeState.PLANNED)
        assert t == "STATE_TRANSITION"

    def test_all_specific_transitions(self):
        pairs = [
            ((NodeState.PLANNED, NodeState.RUNNING), "NODE_STARTED"),
            ((NodeState.RUNNING, NodeState.COMPLETED), "NODE_COMPLETED"),
            ((NodeState.RUNNING, NodeState.FAILED), "NODE_FAILED"),
            ((NodeState.PLANNED, NodeState.FAILED), "NODE_FAILED"),
            ((NodeState.FAILED, NodeState.RETRYING), "RETRY_DECISION"),
            ((NodeState.RETRYING, NodeState.RUNNING), "NODE_STARTED"),
        ]
        for (old, new), expected in pairs:
            assert ExecutionCore.get_event_type_for_transition(old, new) == expected


class TestExecutionCoreTopology:
    def test_collect_successors_simple(self):
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="a"))
        dag.add_node(PlanNode(id="b"))
        dag.add_edge("a", "b")
        succ = ExecutionCore.collect_successors("a", dag)
        assert succ == ["b"]

    def test_collect_successors_chain(self):
        dag = DependencyGraph()
        for nid in ("a", "b", "c"):
            dag.add_node(PlanNode(id=nid))
        dag.add_edge("a", "b")
        dag.add_edge("b", "c")
        succ = ExecutionCore.collect_successors("a", dag)
        assert set(succ) == {"b", "c"}

    def test_collect_successors_no_successors(self):
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="a"))
        assert ExecutionCore.collect_successors("a", dag) == []


class TestExecutionCoreDAGAlgorithms:
    def test_topo_sort_simple(self):
        dag = dag_with_chain()
        topo = ExecutionCore.topo_sort(dag)
        assert [n.id for n in topo] == ["a", "b", "c"]

    def test_topo_sort_diamond(self):
        dag = DependencyGraph()
        for nid in ("a", "b", "c", "d"):
            dag.add_node(PlanNode(id=nid))
        dag.add_edge("a", "b")
        dag.add_edge("a", "c")
        dag.add_edge("b", "d")
        dag.add_edge("c", "d")
        topo = ExecutionCore.topo_sort(dag)
        assert [n.id for n in topo] == ["a", "b", "c", "d"]

    def test_topo_sort_cycle_detected(self):
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="a"))
        dag.add_node(PlanNode(id="b"))
        dag.add_edge("a", "b")
        dag.add_edge("b", "a")
        with pytest.raises(ValueError, match="Cycle"):
            ExecutionCore.topo_sort(dag)

    def test_independent_branches(self):
        dag = dag_with_chain()
        branches = ExecutionCore.independent_branches(dag)
        assert len(branches) == 3
        assert branches[0][0].id == "a"
        assert branches[1][0].id == "b"
        assert branches[2][0].id == "c"

    def test_independent_branches_parallel(self):
        dag = DependencyGraph()
        for nid in ("a", "b", "c"):
            dag.add_node(PlanNode(id=nid))
        dag.add_edge("a", "b")
        dag.add_edge("a", "c")
        branches = ExecutionCore.independent_branches(dag)
        assert len(branches) == 2
        assert branches[0][0].id == "a"
        assert {n.id for n in branches[1]} == {"b", "c"}

    def test_validate_dag_clean(self):
        dag = dag_with_chain()
        errors = ExecutionCore.validate_dag(dag)
        assert errors == []

    def test_validate_dag_dangling_source(self):
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="a"))
        dag.add_edge("x", "a")
        errors = ExecutionCore.validate_dag(dag)
        assert any("not in nodes" in e for e in errors)

    def test_validate_dag_self_loop(self):
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="a"))
        dag.add_edge("a", "a")
        errors = ExecutionCore.validate_dag(dag)
        assert any("Self-loop" in e for e in errors)

    def test_validate_dag_cycle(self):
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="a"))
        dag.add_node(PlanNode(id="b"))
        dag.add_edge("a", "b")
        dag.add_edge("b", "a")
        errors = ExecutionCore.validate_dag(dag)
        assert any("Cycle" in e for e in errors)


class TestExecutionCoreMisc:
    def test_default_tool_runner(self):
        node = PlanNode(id="n1", tool="my_tool", inputs={"x": 1})
        result = ExecutionCore.default_tool_runner(node)
        assert result["tool"] == "my_tool"
        assert result["inputs"] == {"x": 1}
        assert "executed_my_tool" in result["output"]

    def test_compute_backoff_exponential(self):
        b1 = ExecutionCore.compute_backoff(1, 2.0, 60.0)
        assert b1 == 2.0
        b2 = ExecutionCore.compute_backoff(2, 2.0, 60.0)
        assert b2 == 4.0
        b3 = ExecutionCore.compute_backoff(3, 2.0, 60.0)
        assert b3 == 8.0

    def test_compute_backoff_caps_at_max(self):
        b = ExecutionCore.compute_backoff(10, 2.0, 60.0)
        assert b == 60.0

    def test_should_retry_under_limit(self):
        assert ExecutionCore.should_retry(0, 3) is True
        assert ExecutionCore.should_retry(2, 3) is True

    def test_should_retry_at_limit(self):
        assert ExecutionCore.should_retry(3, 3) is False
        assert ExecutionCore.should_retry(4, 3) is False


class TestDAGBuilder:
    def test_build_empty(self):
        dag = DAGBuilder().build()
        assert len(dag.nodes) == 0
        assert len(dag.edges) == 0

    def test_build_single_node(self):
        dag = DAGBuilder().add("a", tool="t").build()
        assert "a" in dag.nodes
        assert dag.nodes["a"].tool == "t"

    def test_build_with_dependency(self):
        dag = DAGBuilder() \
            .add("a", tool="t1") \
            .add("b", tool="t2") \
            .depends("b", "a") \
            .build()
        assert len(dag.edges) == 1
        assert dag.edges[0].source_id == "a"
        assert dag.edges[0].target_id == "b"

    def test_build_sorts_nodes(self):
        dag = DAGBuilder() \
            .add("z", tool="t") \
            .add("a", tool="t") \
            .add("m", tool="t") \
            .build()
        ids = list(dag.nodes.keys())
        assert ids == sorted(ids)

    def test_build_with_inputs(self):
        dag = DAGBuilder() \
            .add("a", tool="t", inputs={"x": 1}) \
            .build()
        assert dag.nodes["a"].inputs == {"x": 1}


# ── Helpers ──

def dag_with_chain() -> DependencyGraph:
    dag = DependencyGraph()
    for nid in ("a", "b", "c"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("a", "b")
    dag.add_edge("b", "c")
    return dag
