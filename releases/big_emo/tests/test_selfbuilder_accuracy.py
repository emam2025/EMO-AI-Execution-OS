"""
Self-Builder Accuracy — 10 tests.

Validates:
  - tool proposal generates correct ToolDraft
  - sandbox validation passes/fails correctly
  - build recording with validator_signature
  - tenant isolation (LAW-6)
  - zero privilege escalation allowed
"""

import pytest
from releases.big_emo.core.self_governance.builder_engine import SelfBuilderEngine


class TestToolProposal:
    def test_propose_tool_returns_draft_with_fields(self):
        engine = SelfBuilderEngine()
        draft = engine.propose_tool("analyse memory usage", tenant_id="t1")
        assert draft.draft_id
        assert draft.tenant_id == "t1"
        assert draft.intent == "analyse memory usage"
        assert draft.risk_score >= 0.0
        assert draft.status == "draft"

    def test_propose_tool_with_constraints(self):
        engine = SelfBuilderEngine()
        draft = engine.propose_tool("build deployment pipeline", tenant_id="t1", constraints={"permissions": ["write"]})
        assert draft.risk_score > 0.1

    def test_propose_tool_empty_intent_raises(self):
        engine = SelfBuilderEngine()
        with pytest.raises(ValueError, match="intent"):
            engine.propose_tool("", tenant_id="t1")

    def test_propose_tool_missing_tenant_raises(self):
        engine = SelfBuilderEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.propose_tool("build tool", tenant_id="")


class TestSandboxValidation:
    def test_valid_tool_passes_sandbox(self):
        engine = SelfBuilderEngine()
        draft = engine.propose_tool("analyse logs", tenant_id="t1")
        passed = engine.validate_sandbox({"tool_spec": draft.tool_spec}, tenant_id="t1")
        assert passed is True

    def test_tool_with_forbidden_permission_fails(self):
        engine = SelfBuilderEngine()
        spec = {"permissions": ["admin"], "requires_tools": [], "dependencies": [], "steps": []}
        passed = engine.validate_sandbox({"tool_spec": spec}, tenant_id="t1")
        assert passed is False

    def test_tool_with_forbidden_tool_fails(self):
        engine = SelfBuilderEngine()
        spec = {"permissions": ["read"], "requires_tools": ["exec_shell"], "dependencies": [], "steps": []}
        passed = engine.validate_sandbox({"tool_spec": spec}, tenant_id="t1")
        assert passed is False

    def test_tool_with_excessive_deps_fails(self):
        engine = SelfBuilderEngine()
        spec = {"permissions": ["read"], "requires_tools": [], "dependencies": list(range(10)), "steps": []}
        passed = engine.validate_sandbox({"tool_spec": spec}, tenant_id="t1")
        assert passed is False


class TestBuildRecording:
    def test_record_build_creates_record(self):
        engine = SelfBuilderEngine()
        draft = engine.propose_tool("build tool", tenant_id="t1")
        record = engine.record_build({"draft_id": draft.draft_id, "proposal_id": "p1"}, validator_signature="test-sig-32", tenant_id="t1")
        assert record.record_id
        assert record.tenant_id == "t1"
        assert record.validator_signature == "test-sig-32"

    def test_record_build_rejects_empty_signature(self):
        engine = SelfBuilderEngine()
        with pytest.raises(ValueError, match="validator_signature"):
            engine.record_build({"draft_id": "d1"}, validator_signature="", tenant_id="t1")
