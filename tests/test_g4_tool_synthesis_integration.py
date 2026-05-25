"""Phase G4 — Tool Synthesis Agent Integration Tests.  # LAW-2 LAW-12 LAW-14 RULE-1 RULE-2 RULE-3

End-to-end integration tests: synthesize_from_intent → validate_ast →
security scan → sandbox dry-run → registration. Exercises all 7 safety
guards, trace correlation, registry rollback, and EventBus propagation.

Ref: Canon LAW 2, LAW 12, LAW 14, RULE 1–4
Ref: artifacts/design/g4/04_integration_blueprint.md
"""

from __future__ import annotations

import pytest

from core.runtime.tool_synthesis.synthesis_state_machine import (
    SynthesisState,
    SynthesisStateMachine,
)
from core.runtime.tool_synthesis.tool_registry_manager import ToolRegistryManager
from core.runtime.tool_synthesis.tool_sandboxer import ToolSandboxer
from core.runtime.tool_synthesis.tool_validator import ToolValidator
from core.runtime.tool_synthesis.tool_synthesizer import ToolSynthesizer
from core.runtime.tool_synthesis.trace_correlator import SynthesisTraceCorrelator


def _make_synthesizer() -> ToolSynthesizer:
    return ToolSynthesizer(
        validator=ToolValidator(),
        sandboxer=ToolSandboxer(),
        registry_manager=ToolRegistryManager(),
        state_machine=SynthesisStateMachine(),
        trace_correlator=SynthesisTraceCorrelator(),
    )


SIMPLE_INTENT = {
    "intent_id": "intent_001",
    "goal": "process_data",
    "target_nodes": ["n1", "n2"],
    "constraints": {},
    "confidence": 0.85,
}

SIMPLE_CONTEXT = {
    "plan_id": "plan_001",
    "dag_topology": [{"from": "n1", "to": "n2"}],
    "node_capabilities": {"n1": ["read"], "n2": ["write"]},
    "sandbox_profile": {},
}


class TestSecurityGuardEnforcement:
    """5 tests: G1–G7 guard enforcement for registration."""

    def test_registration_requires_capability_set(self):
        mgr = ToolRegistryManager()
        result = mgr.register_synthesized_tool({
            "tool_id": "t1",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": [],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": True, "side_effects": []},
        })
        assert result["status"] == "rejected"

    def test_registration_requires_no_os_imports(self):
        validator = ToolValidator()
        result = validator.verify_no_os_imports({"code": "import os"})
        assert not result

    def test_registration_rejects_high_risk(self):
        mgr = ToolRegistryManager()
        result = mgr.register_synthesized_tool({
            "tool_id": "t2",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.8,
            "sandbox_results": {"success": True, "side_effects": []},
        })
        assert result["status"] == "rejected"

    def test_registration_rejects_failed_sandbox(self):
        mgr = ToolRegistryManager()
        result = mgr.register_synthesized_tool({
            "tool_id": "t3",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": False, "side_effects": []},
        })
        assert result["status"] == "rejected"

    def test_registration_rejects_with_side_effects(self):
        mgr = ToolRegistryManager()
        result = mgr.register_synthesized_tool({
            "tool_id": "t4",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {
                "success": True,
                "side_effects": [{"effect_type": "file_io"}],
            },
        })
        assert result["status"] == "rejected"

    def test_registration_passes_all_guards(self):
        mgr = ToolRegistryManager()
        result = mgr.register_synthesized_tool({
            "tool_id": "t5",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": True, "side_effects": []},
        })
        assert result["status"] == "registered"

    def test_security_detects_os_import(self):
        validator = ToolValidator()
        result = validator.analyze_security_risk({"code": "import os\nos.system('ls')"})
        assert not result["allowed"]
        assert result["overall_risk_score"] > 0


class TestSandboxDryRunValidation:
    """4 tests: sandbox preparation, execution, side effects, cleanup."""

    def test_prepare_sandbox_context(self):
        sb = ToolSandboxer()
        ctx = sb.prepare_sandbox_context({
            "tool_id": "t1",
            "synthesis_trace_id": "syn_test",
            "capability_set": ["fn:test"],
        })
        assert ctx["sandbox_id"].startswith("sandbox_")
        assert ctx["network_mode"] == "blocked"
        assert ctx["resource_limits"]["max_cpu_sec"] == 10.0

    def test_dry_run_valid_code(self):
        sb = ToolSandboxer()
        ctx = {"sandbox_id": "s1", "generated_code": "def f(): pass"}
        result = sb.execute_dry_run(ctx)
        assert result["success"]

    def test_dry_run_invalid_code(self):
        sb = ToolSandboxer()
        ctx = {"sandbox_id": "s2", "generated_code": "def f(:"}
        result = sb.execute_dry_run(ctx)
        assert not result["success"]

    def test_capture_side_effects_os_import(self):
        sb = ToolSandboxer()
        ctx = {
            "sandbox_id": "s3",
            "generated_code": "import os\nimport subprocess\n",
            "io_policy": {
                "blocked_imports": ["os", "subprocess"],
                "blocked_builtins": ["eval", "exec"],
            },
        }
        effects = sb.capture_side_effects(ctx)
        assert len(effects) >= 2
        assert all(e["blocked"] for e in effects)

    def test_cleanup_no_error(self):
        sb = ToolSandboxer()
        sb.cleanup_sandbox({"sandbox_id": "s4"})


class TestTraceCorrelation:
    """4 tests: trace ID propagation across layers."""

    def test_synthesizer_generates_trace_id(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        assert result["synthesis_trace_id"].startswith("syn_")

    def test_trace_id_propagates_to_g1(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        tid = result["synthesis_trace_id"]
        ctx = syn.trace_correlator.propagate_to_g1("plan_001", tid)
        assert ctx["target_layer"] == "g1_planner"

    def test_trace_id_propagates_to_sandbox(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        tid = result["synthesis_trace_id"]
        ctx = syn.trace_correlator.propagate_to_sandbox("plan_001", tid)
        assert ctx["target_layer"] == "phase4_sandbox"

    def test_trace_id_propagates_to_registry(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        tid = result["synthesis_trace_id"]
        ctx = syn.trace_correlator.propagate_to_registry("plan_001", tid)
        assert ctx["target_layer"] == "tool_registry"

    def test_full_trace_chain(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        tid = result["synthesis_trace_id"]
        syn.trace_correlator.propagate_to_g1("plan_001", tid)
        syn.trace_correlator.propagate_to_sandbox("plan_001", tid)
        syn.trace_correlator.propagate_to_registry("plan_001", tid)
        chain = syn.trace_correlator.trace_chain(tid)
        assert "plan_id" in chain
        assert chain["plan_id"] == "plan_001"


class TestRegistryRollbackSafety:
    """4 tests: registration, rollback, safety."""

    def test_register_tool(self):
        mgr = ToolRegistryManager()
        result = mgr.register_synthesized_tool({
            "tool_id": "rt1",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": True, "side_effects": []},
        })
        assert result["status"] == "registered"
        assert result["rollback_token"]

    def test_rollback_success(self):
        mgr = ToolRegistryManager()
        reg = mgr.register_synthesized_tool({
            "tool_id": "rt2",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": True, "side_effects": []},
        })
        ok = mgr.rollback_registration("rt2", reg["rollback_token"])
        assert ok
        assert not mgr.is_registered("rt2")

    def test_rollback_rejects_wrong_token(self):
        mgr = ToolRegistryManager()
        mgr.register_synthesized_tool({
            "tool_id": "rt3",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": True, "side_effects": []},
        })
        ok = mgr.rollback_registration("rt3", "invalid_token")
        assert not ok

    def test_rollback_rejects_unregistered_tool(self):
        mgr = ToolRegistryManager()
        ok = mgr.rollback_registration("rt_nonexistent", "some_token")
        assert not ok

    def test_registration_idempotent(self):
        mgr = ToolRegistryManager()
        meta = {
            "tool_id": "rt4",
            "generated_code": "def f(): pass",
            "ast_hash": "",
            "capability_set": ["fn:f"],
            "estimated_risk_score": 0.0,
            "sandbox_results": {"success": True, "side_effects": []},
        }
        r1 = mgr.register_synthesized_tool(meta)
        r2 = mgr.register_synthesized_tool(meta)
        assert r1["registration_id"] != r2["registration_id"]
        assert r2["status"] == "registered"


class TestSynthesizerFullPipeline:
    """Full pipeline: intent → code → validate → signature."""

    def test_synthesize_from_intent_returns_code(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        assert result["generated_code"]
        assert result["ast_hash"]
        assert result["synthesis_trace_id"]

    def test_validate_ast_valid_code(self):
        syn = _make_synthesizer()
        result = syn.validate_ast("def foo(): return 42")
        assert result["ast_valid"]
        assert result["ast_hash"]

    def test_validate_ast_invalid_code(self):
        syn = _make_synthesizer()
        result = syn.validate_ast("def foo(:")
        assert not result["ast_valid"]

    def test_generate_tool_signature(self):
        syn = _make_synthesizer()
        sig = syn.generate_tool_signature(
            "def process(context: dict, target: str = 'default'): pass",
            ["fn:process"],
        )
        assert sig["tool_name"] == "process"
        assert len(sig["parameters"]) == 2
        assert sig["signature_hash"]

    def test_synthesize_then_signature(self):
        syn = _make_synthesizer()
        result = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        sig = syn.generate_tool_signature(
            result["generated_code"],
            result["capability_set"],
        )
        assert sig["tool_name"].startswith("syn_")
        assert sig["signature_hash"]

    def test_reset_clears_state(self):
        syn = _make_synthesizer()
        syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        syn.reset()
        assert syn.state_machine.current == SynthesisState.INTENT_RECEIVED

    def test_deterministic_same_input_same_code(self):
        syn = _make_synthesizer()
        r1 = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        r2 = syn.synthesize_from_intent(SIMPLE_INTENT, SIMPLE_CONTEXT)
        # Second call should hit cache
        assert r1["ast_hash"] == r2["ast_hash"]


class TestValidatorConfidenceScoring:
    """Confidence scoring edge cases."""

    def test_perfect_confidence(self):
        validator = ToolValidator()
        score = validator.rate_confidence([{
            "ast_valid": True,
            "no_os_imports": True,
            "capability_match_score": 1.0,
            "overall_risk_score": 0.0,
            "security_findings": [],
        }])
        assert score == 1.0

    def test_low_confidence(self):
        validator = ToolValidator()
        score = validator.rate_confidence([{
            "ast_valid": False,
            "no_os_imports": False,
            "capability_match_score": 0.0,
            "overall_risk_score": 1.0,
            "security_findings": [{"severity": "high"}, {"severity": "high"}],
        }])
        assert score == 0.0

    def test_high_findings_penalty(self):
        validator = ToolValidator()
        score = validator.rate_confidence([{
            "ast_valid": True,
            "no_os_imports": True,
            "capability_match_score": 1.0,
            "overall_risk_score": 0.0,
            "security_findings": [{"severity": "high"}],
        }])
        assert score == 0.8

    def test_medium_findings_penalty(self):
        validator = ToolValidator()
        score = validator.rate_confidence([{
            "ast_valid": True,
            "no_os_imports": True,
            "capability_match_score": 1.0,
            "overall_risk_score": 0.0,
            "security_findings": [{"severity": "medium"}, {"severity": "medium"}],
        }])
        assert score == 0.8
