"""Tests for Failure Governance Layer.

Covers:
  - FailureClassifier pattern matching
  - FixSuggestionEngine output
  - Integration with ExecutionEngine
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.failure_governance import (
    FailureClass, FailureClassifier, ClassifiedFailure,
    FixSuggestionEngine, FixSuggestion,
)
from core.execution_engine import (
    DependencyGraph, PlanNode, ExecutionEngine, ToolSpec, RetryPolicy, NodeConfig,
)


# ── Classification ────────────────────────────────────────────

def test_classify_timeout():
    cf = FailureClassifier.classify("explain", "timed out after 30s")
    assert cf.failure_class == FailureClass.TIMEOUT
    assert cf.confidence >= 0.9


def test_classify_contract():
    cf = FailureClassifier.classify("explain",
        "Contract violations on inputs: Missing required input 'symbol_id'")
    assert cf.failure_class == FailureClass.CONTRACT
    assert cf.confidence >= 0.9


def test_classify_data_not_found():
    cf = FailureClassifier.classify("explain", "Symbol 'foo' not found")
    assert cf.failure_class == FailureClass.DATA
    assert cf.confidence >= 0.8


def test_classify_tool_error():
    cf = FailureClassifier.classify("explain", "AttributeError: 'NoneType' object has no attribute 'x'")
    assert cf.failure_class == FailureClass.TOOL
    assert cf.confidence >= 0.8


def test_classify_engine():
    cf = FailureClassifier.classify("explain", "Worker exception: pool shutdown")
    assert cf.failure_class == FailureClass.ENGINE


def test_classify_remote():
    cf = FailureClassifier.classify("remote_tool", "Remote-ConnectionRefused: connection refused")
    assert cf.failure_class == FailureClass.ENGINE


def test_classify_unknown():
    cf = FailureClassifier.classify("weird", "Something completely unexpected happened")
    assert cf.failure_class == FailureClass.UNKNOWN
    assert cf.confidence < 0.5


def test_classify_no_error():
    cf = FailureClassifier.classify("tool", "success")
    assert cf.failure_class == FailureClass.UNKNOWN


# ── Suggestions ───────────────────────────────────────────────

def test_suggestion_from_timeout():
    cf = FailureClassifier.classify("agent.explain", "timed out after 30s")
    suggestion = FixSuggestionEngine.suggest(cf)
    assert suggestion.actionable
    assert suggestion.failure_class == FailureClass.TIMEOUT
    assert "timeout" in suggestion.description.lower()


def test_suggestion_from_contract():
    cf = FailureClassifier.classify("agent.explain",
        "Contract violations on outputs: Missing required output 'explanation'")
    suggestion = FixSuggestionEngine.suggest(cf)
    assert suggestion.actionable
    assert suggestion.failure_class == FailureClass.CONTRACT
    assert suggestion.priority == "high"


def test_suggestion_from_data():
    cf = FailureClassifier.classify("graph_retrieval.retrieve_symbol_core",
        "Symbol 's1' not found")
    suggestion = FixSuggestionEngine.suggest(cf)
    assert suggestion.actionable
    assert "index" in suggestion.description.lower()


def test_suggestion_unknown():
    cf = FailureClassifier.classify("weird", "gibberish error")
    suggestion = FixSuggestionEngine.suggest(cf)
    assert not suggestion.actionable
    assert suggestion.priority == "low"


def test_suggestion_batch():
    failures = [
        FailureClassifier.classify("a", "timed out"),
        FailureClassifier.classify("b", "not found"),
    ]
    suggestions = FixSuggestionEngine.suggest_batch(failures)
    assert len(suggestions) == 2
    assert suggestions[0].failure_class == FailureClass.TIMEOUT
    assert suggestions[1].failure_class == FailureClass.DATA


# ── Integration ──────────────────────────────────────────────

def test_engine_failure_governance_integration():
    """Engine produces failures that FailureClassifier can process."""
    engine = ExecutionEngine()

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="explain",
                          config=NodeConfig(
                              retry_policy=RetryPolicy(max_retries=0),
                          )))

    def failing_runner(node):
        raise RuntimeError("Symbol 'undefined' not found")

    result = engine.execute(dag, tool_runner=failing_runner)
    node_result = result["node_results"]["n1"]
    error = node_result.get("error", "")

    # Classify the failure
    cf = FailureClassifier.classify("explain", error)
    assert cf.failure_class == FailureClass.DATA
    assert cf.confidence >= 0.8


def test_engine_contract_failure_classifiable():
    """Contract violations produce classifiable failures."""
    from core.contracts import ToolContract, ParamSpec
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
    error = result["node_results"]["n1"].get("error", "")

    cf = FailureClassifier.classify("strict_tool", error)
    assert cf.failure_class == FailureClass.CONTRACT
    assert cf.confidence >= 0.9
    assert "required_field" in cf.suggestion or "contract" in cf.suggestion
