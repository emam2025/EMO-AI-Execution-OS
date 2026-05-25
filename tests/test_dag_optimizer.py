"""Tests for DAG Optimizer Engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.execution_engine import (
    DependencyGraph, PlanNode, PlanEdge, DAGBuilder, NodeConfig,
)
from core.dag_optimizer import DAGOptimizer, OPTIMIZER_VERSION


def test_optimizer_version():
    assert OPTIMIZER_VERSION == "1.0.0"


def test_single_node_noop():
    """One node with no edges → no change."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="test_tool", inputs={"x": 1}))
    opt = DAGOptimizer()
    result = opt.optimize(dag)
    assert "n1" in result.nodes
    assert len(result.nodes) == 1


def test_merge_same_tool_sequential():
    """Two same-tool nodes in sequence → merged into one."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="hybrid_retrieval.retrieve", inputs={"query": "auth"}))
    dag.add_node(PlanNode(id="n2", tool="hybrid_retrieval.retrieve", inputs={"top_k": 20}))
    dag.add_edge("n1", "n2")
    opt = DAGOptimizer(enable_merge=True, enable_dedup=False)
    result = opt.optimize(dag)
    # n1 and n2 should merge into n1 with combined inputs
    assert len(result.nodes) == 1
    assert "n1" in result.nodes
    assert "n2" not in result.nodes
    merged = result.nodes["n1"]
    assert merged.inputs.get("query") == "auth"
    assert merged.inputs.get("top_k") == 20


def test_no_merge_different_tool():
    """Different tools → no merge."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="graph_retrieval.ranked_hotspots"))
    dag.add_node(PlanNode(id="n2", tool="agent.top_hotspots"))
    dag.add_edge("n1", "n2")
    opt = DAGOptimizer()
    result = opt.optimize(dag)
    assert len(result.nodes) == 2


def test_no_merge_fan_out():
    """A → B and A → C (one-to-many) → no merge."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="tool_a"))
    dag.add_node(PlanNode(id="n2", tool="tool_a"))
    dag.add_node(PlanNode(id="n3", tool="tool_a"))
    dag.add_edge("n1", "n2")
    dag.add_edge("n1", "n3")
    opt = DAGOptimizer(enable_merge=True, enable_dedup=False)
    result = opt.optimize(dag)
    assert len(result.nodes) == 3


def test_dedup_identical_nodes():
    """Two nodes with same tool+inputs → one removed, edges rewired."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="graph_retrieval.heuristic_analysis",
                          inputs={"symbol_id": "foo"}))
    dag.add_node(PlanNode(id="n2", tool="graph_retrieval.heuristic_analysis",
                          inputs={"symbol_id": "foo"}))
    dag.add_node(PlanNode(id="n3", tool="agent.explain", inputs={"symbol_id": "foo"}))
    dag.add_edge("n1", "n3")
    dag.add_edge("n2", "n3")
    opt = DAGOptimizer(enable_merge=False, enable_dedup=True)
    result = opt.optimize(dag)
    assert len(result.nodes) == 2  # n1 kept, n2 removed
    assert "n2" not in result.nodes


def test_dedup_no_match():
    """Different inputs → no dedup."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain", inputs={"symbol_id": "foo"}))
    dag.add_node(PlanNode(id="n2", tool="explain", inputs={"symbol_id": "bar"}))
    opt = DAGOptimizer(enable_merge=False, enable_dedup=True)
    result = opt.optimize(dag)
    assert len(result.nodes) == 2


def test_dag_builder_sorted():
    """DAGBuilder creates nodes in sorted ID order."""
    builder = DAGBuilder()
    builder.add("z", tool="t").add("a", tool="t").add("m", tool="t")
    dag = builder.build()
    ids = list(dag.nodes.keys())
    assert ids == sorted(ids), f"Expected sorted, got {ids}"


def test_optimizer_preserves_version():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t"))
    dag.version = "1.0.0"
    opt = DAGOptimizer()
    result = opt.optimize(dag)
    assert result.version == "1.0.0"


def test_optimizer_no_mutation_of_original():
    """optimize() must not mutate the input DAG."""
    builder = DAGBuilder()
    builder.add("a", tool="hybrid_retrieval.retrieve", inputs={"query": "q"})
    builder.add("b", tool="hybrid_retrieval.retrieve", inputs={"top_k": 5})
    builder.depends("b", "a")
    original = builder.build()
    original_len = len(original.nodes)
    opt = DAGOptimizer(enable_merge=True, enable_dedup=True)
    _ = opt.optimize(original)
    assert len(original.nodes) == original_len, "Original mutated!"


def test_multiple_merge_passes():
    """Three nodes A→B→C with same tool → single node."""
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="same"))
    dag.add_node(PlanNode(id="n2", tool="same"))
    dag.add_node(PlanNode(id="n3", tool="same"))
    dag.add_edge("n1", "n2")
    dag.add_edge("n2", "n3")
    opt = DAGOptimizer(max_merge_passes=5)
    result = opt.optimize(dag)
    assert len(result.nodes) == 1
    assert "n1" in result.nodes
