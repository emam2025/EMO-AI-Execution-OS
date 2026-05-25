"""Tests for ExecutionRuntime — infrastructure layer."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from core.execution_runtime import ExecutionRuntime
from core.execution_core import FailureIntelligence, ExecutionCore
from core.models.dag import DependencyGraph, NodeState, PlanNode, PlanEdge


@pytest.fixture
def runtime():
    pool = ThreadPoolExecutor(max_workers=2)
    cancel = threading.Event()
    fi = FailureIntelligence()
    event_bus = MagicMock()
    rt = ExecutionRuntime(
        pool=pool,
        cancel_flag=cancel,
        registry={},
        failure_intel=fi,
        event_bus=event_bus,
        contract_validator=MagicMock(),
    )
    return rt, pool, cancel, event_bus, fi


def make_dag_chain():
    dag = DependencyGraph()
    for nid in ("a", "b", "c"):
        dag.add_node(PlanNode(id=nid, tool="mock_tool"))
    dag.add_edge("a", "b")
    dag.add_edge("b", "c")
    return dag


class TestEmit:
    def test_emit_publishes_to_event_bus(self, runtime):
        rt, _, _, event_bus, _ = runtime
        rt.set_trace_id("trace-1")
        rt.emit("NODE_STARTED", node_id="n1", payload={"key": "val"}, session_id="s1")
        event_bus.publish.assert_called_once()
        args, _ = event_bus.publish.call_args
        assert args[0] == "execution"
        event = args[1]
        assert event.event_type == "NODE_STARTED"
        assert event.trace_id == "trace-1"
        assert event.session_id == "s1"

    def test_emit_no_event_bus_does_not_error(self, runtime):
        rt, _, _, _, _ = runtime
        rt._event_bus = None
        rt.emit("NODE_STARTED")
        assert rt._event_bus is None  # still None, no crash


class TestSetState:
    def test_set_state_mutates_node(self, runtime):
        rt, _, _, _, _ = runtime
        node = PlanNode(id="n1", state=NodeState.PLANNED)
        rt.set_state(node, NodeState.RUNNING, "s1")
        assert node.state == NodeState.RUNNING

    def test_set_state_emits_event(self, runtime):
        rt, _, _, event_bus, _ = runtime
        node = PlanNode(id="n1", state=NodeState.PLANNED)
        rt.set_state(node, NodeState.RUNNING, "s1")
        event_bus.publish.assert_called()

    def test_set_state_invalid_transition_logs(self, runtime):
        rt, _, _, _, _ = runtime
        node = PlanNode(id="n1", state=NodeState.COMPLETED)
        rt.set_state(node, NodeState.RUNNING)
        assert node.state == NodeState.RUNNING  # still mutates despite warning


class TestStoreDagTrace:
    def test_store_dag_trace_writes_to_memory(self, runtime):
        rt, _, _, _, _ = runtime
        memory = MagicMock()
        rt._memory = memory
        dag = make_dag_chain()
        rt.store_dag_trace("s1", dag, {}, "completed")
        memory.store_dag_trace.assert_called_once()
        args, _ = memory.store_dag_trace.call_args
        assert args[0] == "s1"
        assert "nodes" in args[1]
        assert "edges" in args[1]

    def test_store_dag_trace_no_memory_skips(self, runtime):
        rt, _, _, _, _ = runtime
        rt._memory = None
        rt.store_dag_trace("s1", make_dag_chain(), {}, "completed")
        assert rt._memory is None  # no memory set, no crash


class TestExecuteNodeSafe:
    def test_cache_hit_returns_cached(self, runtime):
        rt, _, _, _, fi = runtime
        cache = MagicMock()
        cache.get.return_value = {"output": "cached"}
        rt._cache = cache
        node = PlanNode(id="n1", tool="t1", inputs={"x": 1})
        dag = DependencyGraph()
        dag.add_node(node)
        result = rt.execute_node_safe(node, lambda n: {"output": "fresh"}, dag, None, "fast")
        assert result["status"] == "cached"
        assert result["result"] == {"output": "cached"}

    def test_cache_miss_executes_node(self, runtime):
        rt, _, _, _, fi = runtime
        cache = MagicMock()
        cache.get.return_value = None
        rt._cache = cache
        node = PlanNode(id="n1", tool="t1", inputs={"x": 1})
        dag = DependencyGraph()
        dag.add_node(node)
        rt._contract_validator.validate_inputs.return_value = []
        rt._contract_validator.validate_outputs.return_value = []
        result = rt.execute_node_safe(
            node, lambda n: {"output": f"executed_{n.tool}"}, dag, None, "fast",
        )
        assert result["status"] == "completed"

    def test_cancel_flag_skips_cache(self, runtime):
        rt, _, cancel, _, _ = runtime
        cache = MagicMock()
        rt._cache = cache
        cancel.set()
        node = PlanNode(id="n1", tool="t1")
        dag = DependencyGraph()
        dag.add_node(node)
        rt._contract_validator.validate_inputs.return_value = []
        rt._contract_validator.validate_outputs.return_value = []
        result = rt.execute_node_safe(
            node, lambda n: {"output": "ok"}, dag, None, "fast",
        )
        cache.get.assert_not_called()


class TestHandleNodeFailure:
    def test_retry_on_failure(self, runtime):
        rt, _, _, _, fi = runtime
        node = PlanNode(id="n1", tool="t1", retry_count=0,
                        config=MagicMock())
        node.config.retry_policy.max_retries = 3
        node.config.retry_policy.backoff_seconds = 0.01
        node.config.retry_policy.max_backoff_seconds = 0.05
        dag = DependencyGraph()
        dag.add_node(node)
        rt._contract_validator.validate_inputs.return_value = []
        rt._contract_validator.validate_outputs.return_value = []
        result = rt._handle_node_failure(
            node, "oops", lambda n: {"output": "retried"}, dag, None, "fast",
        )
        assert node.retry_count == 1
        assert node.state in (NodeState.RUNNING, NodeState.COMPLETED)

    def test_max_retries_exceeded_fails(self, runtime):
        rt, _, _, _, fi = runtime
        node = PlanNode(id="n1", tool="t1", retry_count=3,
                        config=MagicMock())
        node.config.retry_policy.max_retries = 3
        dag = DependencyGraph()
        dag.add_node(node)
        result = rt._handle_node_failure(
            node, "final error", lambda n: {}, dag, None, "fast",
        )
        assert result["status"] == "failed"
        assert node.state == NodeState.FAILED


class TestRollbackSubgraph:
    def test_rollback_successors(self, runtime):
        rt, _, _, event_bus, _ = runtime
        dag = make_dag_chain()
        for nid in ("b", "c"):
            dag.nodes[nid].state = NodeState.COMPLETED
        rt.rollback_subgraph(dag.nodes["a"], dag, "s1")
        assert dag.nodes["b"].state == NodeState.ROLLED_BACK
        assert dag.nodes["c"].state == NodeState.ROLLED_BACK

    def test_rollback_emits_events(self, runtime):
        rt, _, _, event_bus, _ = runtime
        dag = make_dag_chain()
        dag.nodes["b"].state = NodeState.COMPLETED
        rt.rollback_subgraph(dag.nodes["a"], dag, None)
        assert event_bus.publish.called


class TestShutdown:
    def test_shutdown_pool(self, runtime):
        rt, pool, _, _, _ = runtime
        assert not pool._shutdown
        rt.shutdown(wait=False)
        assert pool._shutdown
