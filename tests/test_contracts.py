"""Tests for Execution Contract Layer.

Covers:
  - ContractValidator input/output validation
  - Schema version enforcement
  - ToolContract definition correctness
  - Integration with ExecutionEngine
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

import pytest

from core.contracts import (
    ContractValidator, ContractViolation, SchemaVersionMismatch,
    ToolContract, ParamSpec, TOOL_CONTRACTS,
    DAG_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS,
)
from core.execution_engine import (
    DependencyGraph, PlanNode, NodeConfig,
    ExecutionEngine, ToolSpec, RetryPolicy,
)


# ── ContractValidator: inputs ─────────────────────────────────

def test_validate_inputs_passes():
    c = ToolContract(inputs=[ParamSpec("name", "str")])
    assert ContractValidator.validate_inputs(c, {"name": "foo"}) == []


def test_validate_inputs_missing_required():
    c = ToolContract(inputs=[ParamSpec("name", "str")])
    errors = ContractValidator.validate_inputs(c, {})
    assert len(errors) == 1
    assert "Missing required" in errors[0]


def test_validate_inputs_type_mismatch():
    c = ToolContract(inputs=[ParamSpec("limit", "int")])
    errors = ContractValidator.validate_inputs(c, {"limit": "ten"})
    assert len(errors) == 1
    assert "expected int" in errors[0]


def test_validate_inputs_unknown_strict():
    c = ToolContract(inputs=[ParamSpec("name", "str")], strict_inputs=True)
    errors = ContractValidator.validate_inputs(c, {"name": "a", "extra": 1})
    assert len(errors) == 1
    assert "Unknown input" in errors[0]


def test_validate_inputs_unknown_not_strict():
    c = ToolContract(inputs=[ParamSpec("name", "str")], strict_inputs=False)
    errors = ContractValidator.validate_inputs(c, {"name": "a", "extra": 1})
    assert errors == []


def test_validate_inputs_any_type():
    c = ToolContract(inputs=[ParamSpec("anything", "any")])
    assert ContractValidator.validate_inputs(c, {"anything": 42}) == []
    assert ContractValidator.validate_inputs(c, {"anything": "str"}) == []
    assert ContractValidator.validate_inputs(c, {"anything": [1, 2]}) == []


def test_validate_inputs_no_contract():
    c = ToolContract()
    assert ContractValidator.validate_inputs(c, {"whatever": 1}) == []


# ── ContractValidator: outputs ────────────────────────────────

def test_validate_outputs_passes():
    c = ToolContract(outputs=[ParamSpec("result", "dict")])
    assert ContractValidator.validate_outputs(c, {"result": {"ok": True}}) == []


def test_validate_outputs_missing_required():
    c = ToolContract(outputs=[ParamSpec("must_exist", "str")])
    errors = ContractValidator.validate_outputs(c, {})
    assert len(errors) == 1
    assert "Missing required" in errors[0]


def test_validate_outputs_type_mismatch():
    c = ToolContract(outputs=[ParamSpec("count", "int")])
    errors = ContractValidator.validate_outputs(c, {"count": "oops"})
    assert len(errors) == 1


def test_validate_outputs_unknown_strict():
    c = ToolContract(outputs=[ParamSpec("a", "str")], strict_outputs=True)
    errors = ContractValidator.validate_outputs(c, {"a": "ok", "b": "extra"})
    assert len(errors) == 1


# ── Schema versioning ─────────────────────────────────────────

def test_schema_version_valid():
    assert DAG_SCHEMA_VERSION in SUPPORTED_SCHEMA_VERSIONS


def test_dag_has_default_version():
    dag = DependencyGraph()
    assert dag.version == DAG_SCHEMA_VERSION


def test_engine_rejects_unknown_version():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.version = "0.0.0"
    dag.add_node(PlanNode(id="n1", tool="explain"))
    with pytest.raises(SchemaVersionMismatch) as exc:
        engine.execute(dag)
    assert exc.value.dag_version == "0.0.0"
    assert "1.0.0" in exc.value.supported


def test_check_schema_version_raises_for_unknown():
    dag = DependencyGraph()
    dag.version = "999.0.0"
    with pytest.raises(SchemaVersionMismatch):
        ExecutionEngine._check_schema_version(dag)


def test_check_schema_version_passes_for_known():
    dag = DependencyGraph()
    dag.version = DAG_SCHEMA_VERSION
    ExecutionEngine._check_schema_version(dag)
    assert dag.version == DAG_SCHEMA_VERSION


def test_execute_streaming_rejects_unknown_version():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.version = "0.0.0"
    dag.add_node(PlanNode(id="n1", tool="explain"))
    results = list(engine.execute_streaming(dag))
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert any("schema" in e.lower() for e in results[0].get("errors", []))


def test_register_tool_rejects_bad_version():
    engine = ExecutionEngine()
    bad_contract = ToolContract(
        tool_name="bad", version="999.0.0",
    )
    spec = ToolSpec(name="bad_tool", contract=bad_contract)
    with pytest.raises(ValueError, match="not in supported versions"):
        engine.register_tool(spec)


def test_register_tool_accepts_good_version():
    engine = ExecutionEngine()
    good_contract = ToolContract(
        tool_name="good", version=DAG_SCHEMA_VERSION,
    )
    spec = ToolSpec(name="good_tool", contract=good_contract)
    engine.register_tool(spec)  # Should not raise
    assert "good_tool" in engine.registry


def test_engine_accepts_known_version():
    engine = ExecutionEngine()
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain"))
    result = engine.execute(dag)
    assert result["status"] == "completed"


# ── Pre-built contracts correctness ──────────────────────────

def test_all_tools_have_contracts():
    expected = {
        "graph_retrieval.ranked_hotspots",
        "graph_retrieval.retrieve_impact_chain",
        "graph_retrieval.heuristic_analysis",
        "graph_retrieval.retrieve_symbol_core",
        "agent.explain",
        "agent.impact",
        "agent.why",
        "agent.suggest_refactor",
        "agent.top_hotspots",
        "hybrid_retrieval.retrieve",
        "context_compiler.build_llm_context",
        "context_compiler.build_symbol_context",
        "context_compiler.build_file_context",
    }
    assert set(TOOL_CONTRACTS.keys()) == expected


def test_each_contract_has_name():
    for name, c in TOOL_CONTRACTS.items():
        assert c.tool_name == name, f"{name}: tool_name mismatch"


# ── Integration: engine enforces contracts ───────────────────

def test_engine_rejects_violating_inputs():
    engine = ExecutionEngine()
    contract = ToolContract(
        inputs=[ParamSpec("required_field", "str")],
        strict_inputs=True,
    )
    spec = ToolSpec(name="strict_tool", contract=contract)
    engine.register_tool(spec)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="strict_tool", inputs={"wrong": 1}))

    result = engine.execute(dag)
    assert result["status"] == "failed"
    assert "Contract violations" in (result["node_results"]["n1"].get("error") or "")


def test_engine_passes_valid_inputs():
    engine = ExecutionEngine()
    contract = ToolContract(
        inputs=[ParamSpec("required_field", "str")],
    )
    spec = ToolSpec(name="valid_tool", contract=contract)
    engine.register_tool(spec)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="valid_tool", inputs={"required_field": "hello"}))

    result = engine.execute(dag)
    assert result["status"] == "completed"


def test_engine_uses_global_contract_if_no_spec_contract():
    """Engine falls back to TOOL_CONTRACTS if ToolSpec has no contract."""
    engine = ExecutionEngine()
    spec = ToolSpec(name="graph_retrieval.ranked_hotspots")  # no contract set
    engine.register_tool(spec)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="graph_retrieval.ranked_hotspots", inputs={"limit": 5}))

    def hotspots_runner(node):
        return {"hotspots": [{"name": "s1", "rank": 1}]}

    result = engine.execute(dag, tool_runner=hotspots_runner)
    assert result["status"] == "completed", f"Failed: {result.get('errors')}"

    # Same test with agent.explain and a compliant runner
    engine2 = ExecutionEngine()
    spec2 = ToolSpec(name="agent.explain")
    engine2.register_tool(spec2)

    dag2 = DependencyGraph()
    dag2.add_node(PlanNode(id="n1", tool="agent.explain", inputs={"symbol_id": "s1"}))

    def explain_runner(node):
        return {"explanation": "This symbol does X"}

    result2 = engine2.execute(dag2, tool_runner=explain_runner)
    assert result2["status"] == "completed", f"Failed: {result2.get('errors')}"


def test_engine_rejects_bad_outputs():
    """Engine catches contract violations in tool outputs."""
    engine = ExecutionEngine()
    contract = ToolContract(
        inputs=[],
        outputs=[ParamSpec("must_exist", "str")],
    )
    spec = ToolSpec(name="bad_output", contract=contract)
    engine.register_tool(spec)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="bad_output"))

    def bad_runner(node):
        return {"different_key": 123}  # missing "must_exist", extra unknown

    result = engine.execute(dag, tool_runner=bad_runner)
    assert result["status"] == "failed"
    assert "Contract violations" in (result["node_results"]["n1"].get("error") or "")


# ── DAG version in to_dict ───────────────────────────────────

def test_dag_to_dict_includes_version():
    dag = DependencyGraph()
    d = dag.to_dict()
    assert d.get("version") == DAG_SCHEMA_VERSION
