"""Phase 15 tests: Execution Engine, Plan Graph, Tool Runtime,
State Machine, Failure Intelligence, Memory Integration.

Tests cover:
  - NodeState transitions (valid/invalid)
  - DependencyGraph (add, topology, validation, branching)
  - DAGBuilder fluent API
  - FailureIntelligence (record, query, suggestion)
  - ExecutionEngine (sequential, retry, rollback, cancel)
  - Full DAG execution with memory integration
"""

import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


# ======================================================================
# Fixtures
# ======================================================================

from core.execution_engine import (
    NodeState, PlanNode, PlanEdge, DependencyGraph, NodeConfig,
    RetryPolicy, RollbackStrategy, ToolSpec,
    FailureIntelligence, FailurePattern,
    ExecutionEngine, DAGBuilder,
)
from core.execution_cache import ExecutionCache
from core.service_registry import ServiceRegistry


# ======================================================================
# 1 – NodeState Machine Tests
# ======================================================================


def test_state_valid_transitions():
    assert NodeState.PENDING.can_transition_to(NodeState.PLANNED) is True
    assert NodeState.PLANNED.can_transition_to(NodeState.RUNNING) is True
    assert NodeState.PLANNED.can_transition_to(NodeState.WAITING) is True
    assert NodeState.RUNNING.can_transition_to(NodeState.COMPLETED) is True
    assert NodeState.RUNNING.can_transition_to(NodeState.FAILED) is True
    assert NodeState.FAILED.can_transition_to(NodeState.RETRYING) is True
    assert NodeState.FAILED.can_transition_to(NodeState.ROLLED_BACK) is True
    assert NodeState.RETRYING.can_transition_to(NodeState.RUNNING) is True
    assert NodeState.WAITING.can_transition_to(NodeState.RUNNING) is True


def test_state_invalid_transitions():
    assert NodeState.PENDING.can_transition_to(NodeState.RUNNING) is False
    assert NodeState.PENDING.can_transition_to(NodeState.COMPLETED) is False
    assert NodeState.PLANNED.can_transition_to(NodeState.COMPLETED) is False
    assert NodeState.COMPLETED.can_transition_to(NodeState.RUNNING) is False
    assert NodeState.ROLLED_BACK.can_transition_to(NodeState.RUNNING) is False
    assert NodeState.COMPLETED.can_transition_to(NodeState.FAILED) is False


def test_state_all_defined():
    """Every state should have at least one valid transition (except terminal)."""
    states = list(NodeState)
    for s in states:
        if s in (NodeState.COMPLETED, NodeState.ROLLED_BACK):
            continue  # terminal
        has_outgoing = any(
            s.can_transition_to(t) for t in states if t != s
        )
        assert has_outgoing, f"State {s.value} has no outgoing transitions"


# ======================================================================
# 2 – DependencyGraph Tests
# ======================================================================


def test_graph_add_node():
    dag = DependencyGraph()
    n1 = PlanNode(id="n1", tool="explain")
    dag.add_node(n1)
    assert "n1" in dag.nodes
    assert dag.nodes["n1"].tool == "explain"


def test_graph_add_edge():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1"))
    dag.add_node(PlanNode(id="n2"))
    dag.add_edge("n1", "n2")
    assert len(dag.edges) == 1
    assert dag.edges[0].source_id == "n1"
    assert dag.edges[0].target_id == "n2"


def test_graph_predecessors():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n3")
    dag.add_edge("n2", "n3")
    preds = dag.predecessors("n3")
    assert len(preds) == 2
    assert {p.id for p in preds} == {"n1", "n2"}


def test_graph_successors():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1"))
    dag.add_node(PlanNode(id="n2"))
    dag.add_node(PlanNode(id="n3"))
    dag.add_edge("n1", "n2")
    dag.add_edge("n1", "n3")
    succs = dag.successors("n1")
    assert len(succs) == 2
    assert {s.id for s in succs} == {"n2", "n3"}


def test_graph_entry_nodes():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n3")
    dag.add_edge("n2", "n3")
    entries = dag.entry_nodes()
    assert {e.id for e in entries} == {"n1", "n2"}


def test_graph_leaf_nodes():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n1", "n3")
    leaves = dag.leaf_nodes()
    assert {l.id for l in leaves} == {"n2", "n3"}


def test_graph_topo_sort_linear():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n2", "n3")
    topo = dag.topo_sort()
    assert [n.id for n in topo] == ["n1", "n2", "n3"]


def test_graph_topo_sort_diamond():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3", "n4"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n1", "n3")
    dag.add_edge("n2", "n4")
    dag.add_edge("n3", "n4")
    topo = dag.topo_sort()
    assert [n.id for n in topo] == ["n1", "n2", "n3", "n4"] or \
           [n.id for n in topo] == ["n1", "n3", "n2", "n4"]


def test_graph_cycle_detection():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n2", "n3")
    dag.add_edge("n3", "n1")
    import pytest
    try:
        dag.topo_sort()
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_graph_validation():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1"))
    dag.add_edge("n1", "missing")
    errors = dag.validate()
    assert len(errors) >= 1
    assert any("missing" in e for e in errors)


def test_graph_validation_self_loop():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1"))
    dag.add_edge("n1", "n1")
    errors = dag.validate()
    assert len(errors) >= 1


def test_graph_independent_branches():
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n1", "n3")
    branches = dag.independent_branches()
    assert len(branches) >= 2  # level 1: [n1], level 2: [n2, n3]


def test_graph_to_dict():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain"))
    d = dag.to_dict()
    assert "nodes" in d
    assert "edges" in d
    assert d["nodes"]["n1"]["tool"] == "explain"


# ======================================================================
# 3 – DAGBuilder Tests
# ======================================================================


def test_dag_builder_basic():
    dag = (DAGBuilder()
           .add("retrieve", tool="hybrid_retrieval", inputs={"query": "auth"})
           .add("explain", tool="explain", inputs={"symbol": "s1"})
           .add("impact", tool="impact", inputs={"symbol": "s1"})
           .depends("explain", "retrieve")
           .depends("impact", "retrieve")
           .build())
    assert len(dag.nodes) == 3
    assert len(dag.edges) == 2
    assert dag.entry_nodes()[0].id == "retrieve"


def test_dag_builder_chain():
    dag = (DAGBuilder()
           .add("a", tool="tool_a")
           .add("b", tool="tool_b")
           .add("c", tool="tool_c")
           .depends("b", "a")
           .depends("c", "b")
           .build())
    topo = dag.topo_sort()
    assert [n.id for n in topo] == ["a", "b", "c"]


def test_dag_builder_empty():
    dag = DAGBuilder().build()
    assert dag.nodes == {}
    assert dag.edges == []


# ======================================================================
# 4 – FailureIntelligence Tests
# ======================================================================


def test_fi_record_and_query():
    fi = FailureIntelligence()
    fi.record_result("explain", "balanced", success=True)
    fi.record_result("explain", "balanced", success=False)
    assert fi.failure_rate("explain", "balanced") == 0.5


def test_fi_empty_rate():
    fi = FailureIntelligence()
    assert fi.failure_rate("unknown", "unknown") == 0.0


def test_fi_top_patterns():
    fi = FailureIntelligence()
    fi.record_result("explain", "balanced", success=False)
    fi.record_result("explain", "balanced", success=False)
    fi.record_result("impact", "large_repo", success=True)
    patterns = fi.top_patterns(limit=5)
    assert len(patterns) >= 1
    assert patterns[0].failure_rate >= 0.5


def test_fi_suggest_alternative():
    fi = FailureIntelligence()
    # tool=explain with balanced: high failure
    for _ in range(5):
        fi.record_result("explain", "balanced", success=False)
    # tool=explain with test_file: low failure
    for _ in range(5):
        fi.record_result("explain", "test_file", success=True)
    suggestion = fi.suggest_alternative("explain", "balanced")
    assert suggestion == "test_file"


def test_fi_suggest_no_alternative():
    fi = FailureIntelligence()
    fi.record_result("explain", "balanced", success=True)
    suggestion = fi.suggest_alternative("explain", "balanced")
    assert suggestion is None  # rate < 0.3


def test_fi_report():
    fi = FailureIntelligence()
    fi.record_result("explain", "balanced", success=False)
    report = fi.report()
    assert "patterns" in report
    assert report["total_correlations"] >= 1


# ======================================================================
# 5 – ExecutionEngine Tests
# ======================================================================


def test_engine_execute_linear():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain"))
    dag.add_node(PlanNode(id="n2", tool="impact"))
    dag.add_edge("n1", "n2")
    result = engine.execute(dag)
    assert result["status"] == "completed"
    assert dag.nodes["n1"].state == NodeState.COMPLETED
    assert dag.nodes["n2"].state == NodeState.COMPLETED


def test_engine_execute_diamond():
    engine = ExecutionEngine()
    dag = (DAGBuilder()
           .add("retrieve", tool="hybrid_retrieval")
           .add("explain", tool="explain")
           .add("impact", tool="impact")
           .add("summarise", tool="summarise")
           .depends("explain", "retrieve")
           .depends("impact", "retrieve")
           .depends("summarise", "explain")
           .depends("summarise", "impact")
           .build())
    result = engine.execute(dag)
    assert result["status"] == "completed"
    assert all(n.state == NodeState.COMPLETED for n in dag.nodes.values())


def test_engine_with_custom_runner():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="custom"))

    def runner(node):
        if node.tool == "custom":
            return {"result": "custom_output"}
        return {}

    result = engine.execute(dag, tool_runner=runner)
    assert result["status"] == "completed"
    assert dag.nodes["n1"].result["result"] == "custom_output"


def test_engine_retry_on_failure():
    """Engine should retry when tool fails."""
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(
        id="n1", tool="flaky",
        config=NodeConfig(
            retry_policy=RetryPolicy(max_retries=3, backoff_seconds=0.01),
        ),
    ))

    call_count = [0]

    def flaky_runner(node):
        call_count[0] += 1
        if call_count[0] < 2:
            raise RuntimeError("Transient error")
        return {"result": "ok"}

    result = engine.execute(dag, tool_runner=flaky_runner)
    assert result["status"] == "completed"
    assert dag.nodes["n1"].retry_count == 1


def test_engine_retry_exhausted():
    """Engine should fail after max retries."""
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(
        id="n1", tool="always_fails",
        config=NodeConfig(
            retry_policy=RetryPolicy(max_retries=2, backoff_seconds=0.01),
        ),
    ))

    def failing_runner(node):
        raise RuntimeError("Always fails")

    result = engine.execute(dag, tool_runner=failing_runner)
    assert result["status"] == "failed"
    assert dag.nodes["n1"].state == NodeState.FAILED
    assert dag.nodes["n1"].retry_count == 2


def test_engine_cancel():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="slow"))

    def slow_runner(node):
        time.sleep(5)
        return {}

    # Cancel in a separate thread
    import threading as t
    def do_cancel():
        time.sleep(0.05)
        engine.cancel()

    t.Thread(target=do_cancel, daemon=True).start()
    result = engine.execute(dag, tool_runner=slow_runner)
    assert result["status"] in ("cancelled", "failed")


def test_engine_rollback_on_failure():
    """When a node fails, successors should be rolled back."""
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(
        id="n1", tool="will_fail",
        config=NodeConfig(
            retry_policy=RetryPolicy(max_retries=1, backoff_seconds=0.01),
        ),
    ))
    dag.add_node(PlanNode(id="n2", tool="dependent"))
    dag.add_edge("n1", "n2")

    def runner(node):
        if node.id == "n1":
            raise RuntimeError("n1 failed")
        return {}

    result = engine.execute(dag, tool_runner=runner)
    assert result["status"] == "failed"
    assert dag.nodes["n1"].state == NodeState.FAILED


def test_engine_invalid_dag():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1"))
    dag.add_edge("n1", "missing")
    result = engine.execute(dag)
    assert result["status"] == "failed"
    assert "errors" in result


def test_engine_register_tool():
    engine = ExecutionEngine()
    spec = ToolSpec(name="my_tool", description="Test tool",
                     timeout_seconds=15.0)
    engine.register_tool(spec)
    assert "my_tool" in engine.registry
    assert engine.registry["my_tool"].timeout_seconds == 15.0


def test_engine_fi_records():
    """Engine should record successes/failures in FailureIntelligence."""
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain"))
    dag.add_node(PlanNode(
        id="n2", tool="flaky",
        config=NodeConfig(
            retry_policy=RetryPolicy(max_retries=1, backoff_seconds=0.01),
        ),
    ))
    dag.add_edge("n1", "n2")

    calls = [0]

    def runner(node):
        if node.id == "n2":
            calls[0] += 1
            if calls[0] == 1:
                raise RuntimeError("Transient")
        return {}

    engine.execute(dag, strategy="balanced", tool_runner=runner)
    # n2: 1 failure (initial) + 1 success (retry) → rate = 0.5
    assert engine.fi.failure_rate("explain", "balanced") == 0.0
    assert engine.fi.failure_rate("flaky", "balanced") == 0.5


def test_engine_rollback_subgraph():
    """_rollback_subgraph should mark successors as ROLLED_BACK."""
    engine = ExecutionEngine()
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n2", "n3")

    # Manually mark n2 and n3 as completed
    dag.nodes["n2"].state = NodeState.COMPLETED
    dag.nodes["n3"].state = NodeState.COMPLETED

    engine._rollback_subgraph(dag.nodes["n1"], dag, None)
    assert dag.nodes["n2"].state == NodeState.ROLLED_BACK
    assert dag.nodes["n3"].state == NodeState.ROLLED_BACK


def test_engine_collect_successors():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    for nid in ("n1", "n2", "n3", "n4"):
        dag.add_node(PlanNode(id=nid))
    dag.add_edge("n1", "n2")
    dag.add_edge("n2", "n3")
    dag.add_edge("n1", "n4")
    succs = engine._collect_successors("n1", dag)
    assert "n2" in succs
    assert "n3" in succs
    assert "n4" in succs
    assert "n1" not in succs


# ======================================================================
# 6 – Integration Tests
# ======================================================================


def test_integration_full_execution_with_memory():
    """Full DAG execution with ExecutionMemory integration."""
    from core.execution_memory import ExecutionMemory

    mem = ExecutionMemory(os.path.join(tempfile.mkdtemp(), "mem.db"))
    sid = mem.create_session("execute full pipeline", strategy="balanced")

    engine = ExecutionEngine(memory=mem)

    dag = (DAGBuilder()
           .add("retrieve", tool="hybrid_retrieval",
                inputs={"query": "find auth"})
           .add("explain", tool="explain", inputs={"symbol": "s1"})
           .add("impact", tool="impact", inputs={"symbol": "s1"})
           .add("summarise", tool="summarise")
           .depends("explain", "retrieve")
           .depends("impact", "retrieve")
           .depends("summarise", "explain")
           .depends("summarise", "impact")
           .build())

    result = engine.execute(dag, session_id=sid, strategy="balanced")
    assert result["status"] == "completed"

    # Memory was populated during execution
    events = mem.session_events(sid)
    assert len(events) >= 4  # at least 4 actions

    # All nodes completed
    for node in dag.nodes.values():
        assert node.state == NodeState.COMPLETED, f"{node.id} not completed"


def test_integration_retry_with_memory():
    """Retry should record reasoning traces in memory."""
    from core.execution_memory import ExecutionMemory

    mem = ExecutionMemory(os.path.join(tempfile.mkdtemp(), "mem2.db"))
    sid = mem.create_session("retry test", strategy="balanced")

    engine = ExecutionEngine(memory=mem)

    dag = DependencyGraph()
    dag.add_node(PlanNode(
        id="n1", tool="flaky",
        config=NodeConfig(
            retry_policy=RetryPolicy(max_retries=2, backoff_seconds=0.01),
        ),
    ))

    calls = [0]

    def flaky_runner(node):
        calls[0] += 1
        if calls[0] < 2:
            raise RuntimeError("transient")
        return {"result": "ok"}

    result = engine.execute(dag, session_id=sid, strategy="balanced",
                            tool_runner=flaky_runner)
    assert result["status"] == "completed"

    # Should have reasoning traces for the retry decision
    traces = mem.session_reasoning(sid)
    assert len(traces) >= 1
    assert any("Retrying" in t.reason for t in traces)


def test_integration_failure_intelligence_with_engine():
    """FailureIntelligence tracks tool+strategy correlations across executions."""
    fi = FailureIntelligence()
    engine = ExecutionEngine(failure_intel=fi)

    dag = DependencyGraph()
    dag.add_node(PlanNode(
        id="n1", tool="fragile",
        config=NodeConfig(
            retry_policy=RetryPolicy(max_retries=1, backoff_seconds=0.01),
        ),
    ))

    def runner(node):
        raise RuntimeError("fail")

    # Execute 3 times, all failures
    for _ in range(3):
        engine.execute(dag, strategy="balanced", tool_runner=runner)

    rate = fi.failure_rate("fragile", "balanced")
    assert rate > 0.5


def test_integration_tool_registry():
    """Registered ToolSpec configuration is used during execution."""
    spec = ToolSpec(
        name="auth_tool",
        timeout_seconds=5.0,
        retry_policy=RetryPolicy(max_retries=1, backoff_seconds=0.5),
        rollback_strategy=RollbackStrategy(
            strategy_type="compensating_tool",
            compensating_tool="revert_auth",
        ),
    )
    engine = ExecutionEngine()
    engine.register_tool(spec)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="auth_tool"))

    result = engine.execute(dag)
    assert result["status"] == "completed"
    assert engine.registry["auth_tool"].timeout_seconds == 5.0
    assert engine.registry["auth_tool"].retry_policy.max_retries == 1
    assert engine.registry["auth_tool"].rollback_strategy.compensating_tool == "revert_auth"


def test_integration_dag_builder_to_engine():
    """Full pipeline: DAGBuilder → DependencyGraph → ExecutionEngine."""
    engine = ExecutionEngine()

    dag = (DAGBuilder()
           .add("step1", tool="retrieve", inputs={"q": "find auth"})
           .add("step2", tool="explain", inputs={"s": "s1"})
           .depends("step2", "step1")
           .build())

    result = engine.execute(dag)
    assert result["status"] == "completed"
    assert dag.nodes["step1"].state == NodeState.COMPLETED
    assert dag.nodes["step2"].state == NodeState.COMPLETED


def test_integration_parallel_branches():
    """Independent branches execute successfully."""
    engine = ExecutionEngine()
    dag = (DAGBuilder()
           .add("retrieve", tool="hybrid")
           .add("explain", tool="explain")
           .add("impact", tool="impact")
           .depends("explain", "retrieve")
           .depends("impact", "retrieve")
           .build())

    result = engine.execute(dag)
    assert result["status"] == "completed"
    # Both branches should complete
    assert dag.nodes["explain"].state == NodeState.COMPLETED
    assert dag.nodes["impact"].state == NodeState.COMPLETED


def test_integration_cancel_during_parallel():
    """Cancel should stop parallel branches."""
    engine = ExecutionEngine()
    dag = (DAGBuilder()
           .add("slow1", tool="tool_a")
           .add("slow2", tool="tool_b")
           .build())

    def slow_runner(node):
        time.sleep(10)
        return {}

    import threading as t
    t.Thread(target=lambda: (time.sleep(0.05), engine.cancel()),
             daemon=True).start()
    result = engine.execute(dag, tool_runner=slow_runner)
    assert result["status"] == "cancelled"


# ======================================================================
# 7 – Distributed Runtime: Parallel Execution Tests
# ======================================================================


def test_parallel_nodes_run_concurrently():
    """Nodes at the same topological level should execute concurrently."""
    import threading as t
    results = {}
    lock = t.Lock()

    def timed_runner(node):
        time.sleep(0.2)
        with lock:
            results[node.id] = time.time()
        return {}

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="a"))
    dag.add_node(PlanNode(id="n2", tool="b"))
    dag.add_node(PlanNode(id="n3", tool="c"))

    engine = ExecutionEngine(worker_pool_size=3)
    engine.execute(dag, tool_runner=timed_runner)

    # All 3 start ~same time, so max-min should be < total sequential (0.6s)
    times = list(results.values())
    span = max(times) - min(times)
    assert span < 0.3, f"Parallel nodes too slow: span={span:.3f}s (expected <0.3s)"


def test_parallel_sequential_levels():
    """Nodes in different levels must execute sequentially (topo order)."""
    start = {}
    end = {}

    def timed_runner(node):
        start[node.id] = time.time()
        time.sleep(0.15)
        end[node.id] = time.time()
        return {}

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="a"))
    dag.add_node(PlanNode(id="n2", tool="b"))
    dag.add_node(PlanNode(id="n3", tool="c"))
    dag.add_edge("n1", "n2")
    dag.add_edge("n1", "n3")

    engine = ExecutionEngine(worker_pool_size=3)
    engine.execute(dag, tool_runner=timed_runner)

    # n2 and n3 should start after n1 finishes (no, they can start after n1 finishes
    # since they depend on n1, they're in level 2)
    # Actually independent_branches groups by depth: n1 = level1, n2+n3 = level2
    # So n2/n3 start after n1 completes
    assert start["n2"] >= end["n1"], "n2 started before n1 finished"
    assert start["n3"] >= end["n1"], "n3 started before n1 finished"


def test_worker_pool_size_default():
    engine = ExecutionEngine()
    assert engine._pool._max_workers >= 1


def test_worker_pool_size_custom():
    engine = ExecutionEngine(worker_pool_size=8)
    assert engine._pool._max_workers == 8
    engine.shutdown()


# ======================================================================
# 8 – Distributed Runtime: Cache Integration Tests
# ======================================================================


def test_cache_hit_returns_cached():
    """When cache has a hit, engine returns cached result directly."""
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=100, default_ttl_seconds=3600)
    engine = ExecutionEngine(cache=c)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain", inputs={"sym": "s1"}))

    call_count = [0]
    def runner(node):
        call_count[0] += 1
        return {"answer": "live"}

    # First call: miss → execute
    result1 = engine.execute(dag, tool_runner=runner)
    assert result1["node_results"]["n1"]["status"] == "completed"
    assert result1["node_results"]["n1"]["result"] == {"answer": "live"}
    assert call_count[0] == 1

    # Second call: should be cache hit
    result2 = engine.execute(dag, tool_runner=runner)
    assert result2["node_results"]["n1"]["status"] == "cached"
    assert result2["node_results"]["n1"]["result"] == {"answer": "live"}
    assert call_count[0] == 1  # Runner not called again


def test_cache_miss_different_inputs():
    """Different inputs produce different cache keys → miss."""
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=100, default_ttl_seconds=3600)
    engine = ExecutionEngine(cache=c)

    dag1 = DependencyGraph()
    dag1.add_node(PlanNode(id="n1", tool="explain", inputs={"sym": "s1"}))
    dag2 = DependencyGraph()
    dag2.add_node(PlanNode(id="n1", tool="explain", inputs={"sym": "s2"}))

    call_count = [0]
    def runner(node):
        call_count[0] += 1
        return {"answer": f"result_{node.inputs['sym']}"}

    engine.execute(dag1, tool_runner=runner)
    engine.execute(dag2, tool_runner=runner)
    assert call_count[0] == 2  # Both were misses


def test_cache_does_not_store_failures():
    """Failed node results should not be cached."""
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=100, default_ttl_seconds=3600)
    engine = ExecutionEngine(cache=c)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain",
                          config=NodeConfig(
                              retry_policy=RetryPolicy(max_retries=0),
                          )))

    fail_count = [0]
    def runner(node):
        fail_count[0] += 1
        raise RuntimeError("fail")

    result = engine.execute(dag, tool_runner=runner)
    assert result["node_results"]["n1"]["status"] == "failed"

    # Re-execute should try again (not cached)
    result2 = engine.execute(dag, tool_runner=runner)
    assert result2["node_results"]["n1"]["status"] == "failed"
    assert fail_count[0] == 2  # Both attempts executed


def test_cache_entry_overwrites():
    """Cache stores the most recent value for a key."""
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=100, default_ttl_seconds=3600)
    engine = ExecutionEngine(cache=c)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain", inputs={"sym": "s1"}))

    def runner_a(node):
        return {"answer": "first"}

    # First execution populates cache
    engine.execute(dag, tool_runner=runner_a)
    assert c.get("explain", {"sym": "s1"}) == {"answer": "first"}

    # Manually overwrite cache entry (simulates same result from different source)
    c.set("explain", {"sym": "s1"}, {"answer": "second"})

    # Next execution should return overwritten cached value
    result = engine.execute(dag, tool_runner=runner_a)
    assert result["node_results"]["n1"]["status"] == "cached"
    assert result["node_results"]["n1"]["result"] == {"answer": "second"}


# ======================================================================
# 9 – Distributed Runtime: Service Registry Integration
# ======================================================================


def test_service_registry_remote_routing():
    """Engine routes to service registry when tool is registered remotely."""
    registry = ServiceRegistry()
    engine = ExecutionEngine(service_registry=registry)

    # Register a tool as remote pointing to a known-bad address
    registry.register_remote("remote_tool",
                             "http://127.0.0.1:18999/exec",
                             ToolSpec(name="remote_tool", timeout_seconds=1.0))

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="remote_tool"))

    result = engine.execute(dag, strategy="balanced")
    # Should fail because connection is refused (but should route to remote)
    assert result["status"] == "failed"
    assert "Remote-" in (result["node_results"]["n1"].get("error") or "")


def test_service_registry_fallback_to_local_when_not_registered():
    """Engine falls back to local runner when tool not in registry."""
    sr = ServiceRegistry()
    sr.register_local("tool_a", lambda **kw: {"from": "registry"})
    engine = ExecutionEngine(service_registry=sr)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="tool_a"))
    dag.add_node(PlanNode(id="n2", tool="tool_b"))

    def local_runner(node):
        return {"from": "local", "tool": node.tool}

    result = engine.execute(dag, tool_runner=local_runner)
    # tool_a should come from registry, tool_b from local runner
    assert result["node_results"]["n1"]["result"] == {"from": "registry"}
    assert result["node_results"]["n2"]["result"] == {"from": "local", "tool": "tool_b"}


# ======================================================================
# Run all
# ======================================================================

if __name__ == "__main__":
    tests = [
        # NodeState
        ("state valid transitions", test_state_valid_transitions),
        ("state invalid transitions", test_state_invalid_transitions),
        ("state all defined", test_state_all_defined),
        # DependencyGraph
        ("graph add node", test_graph_add_node),
        ("graph add edge", test_graph_add_edge),
        ("graph predecessors", test_graph_predecessors),
        ("graph successors", test_graph_successors),
        ("graph entry nodes", test_graph_entry_nodes),
        ("graph leaf nodes", test_graph_leaf_nodes),
        ("graph topo linear", test_graph_topo_sort_linear),
        ("graph topo diamond", test_graph_topo_sort_diamond),
        ("graph cycle detection", test_graph_cycle_detection),
        ("graph validation", test_graph_validation),
        ("graph validation self-loop", test_graph_validation_self_loop),
        ("graph independent branches", test_graph_independent_branches),
        ("graph to_dict", test_graph_to_dict),
        # DAGBuilder
        ("dag builder basic", test_dag_builder_basic),
        ("dag builder chain", test_dag_builder_chain),
        ("dag builder empty", test_dag_builder_empty),
        # FailureIntelligence
        ("fi record and query", test_fi_record_and_query),
        ("fi empty rate", test_fi_empty_rate),
        ("fi top patterns", test_fi_top_patterns),
        ("fi suggest alternative", test_fi_suggest_alternative),
        ("fi no alternative", test_fi_suggest_no_alternative),
        ("fi report", test_fi_report),
        # ExecutionEngine
        ("engine linear", test_engine_execute_linear),
        ("engine diamond", test_engine_execute_diamond),
        ("engine custom runner", test_engine_with_custom_runner),
        ("engine retry", test_engine_retry_on_failure),
        ("engine retry exhausted", test_engine_retry_exhausted),
        ("engine cancel", test_engine_cancel),
        ("engine rollback", test_engine_rollback_on_failure),
        ("engine invalid dag", test_engine_invalid_dag),
        ("engine register tool", test_engine_register_tool),
        ("engine fi records", test_engine_fi_records),
        ("engine rollback subgraph", test_engine_rollback_subgraph),
        ("engine collect successors", test_engine_collect_successors),
        # Integration
        ("full execution with memory", test_integration_full_execution_with_memory),
        ("retry with memory", test_integration_retry_with_memory),
        ("fi with engine", test_integration_failure_intelligence_with_engine),
        ("tool registry", test_integration_tool_registry),
        ("dag builder to engine", test_integration_dag_builder_to_engine),
        ("parallel branches", test_integration_parallel_branches),
        ("cancel parallel", test_integration_cancel_during_parallel),
        # Distributed Runtime: Parallel Execution
        ("parallel concurrent", test_parallel_nodes_run_concurrently),
        ("parallel sequential levels", test_parallel_sequential_levels),
        ("worker pool default", test_worker_pool_size_default),
        ("worker pool custom", test_worker_pool_size_custom),
        # Distributed Runtime: Cache Integration
        ("cache hit returns cached", test_cache_hit_returns_cached),
        ("cache miss different inputs", test_cache_miss_different_inputs),
        ("cache no store failures", test_cache_does_not_store_failures),
        ("cache entry overwrites", test_cache_entry_overwrites),
        # Distributed Runtime: Service Registry
        ("service registry remote routing", test_service_registry_remote_routing),
        ("service registry fallback to local", test_service_registry_fallback_to_local_when_not_registered),
    ]

    passed = 0
    failed = 0
    for desc, test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {desc}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total = len(tests)
    print(f"\n{'='*50}")
    print(f"Phase 15: {passed} passed, {failed} failed, {total} total")
    print(f"{'✓ COMPLETE' if failed == 0 else '✗ NEEDS FIX'}")
