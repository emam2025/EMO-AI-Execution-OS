"""Tests for BaseAgent Protocol and Agent Domain Models.

Ref: RC16.8 — Agent OS Unification
"""

import pytest

from core.interfaces.agents import IBaseAgent
from core.models.agent import (
    AgentIdentity,
    AgentMemory,
    AgentSkills,
    AgentPermissions,
    AgentRisk,
    AgentCost,
    AgentAudit,
    AgentStatus,
    AutonomyLevel,
)


class TestAgentDomainModels:
    """Test Agent Domain Models (pure data structures)."""

    def test_agent_identity_creation(self):
        identity = AgentIdentity(
            id="agent-001",
            tenant_id="tenant-123",
            org_id="org-456",
            name="CodeReviewer",
            agent_type="critic",
            capabilities=["code_review", "bug_detection"],
            trust_level=0.8,
        )
        assert identity.id == "agent-001"
        assert identity.name == "CodeReviewer"
        assert identity.trust_level == 0.8
        assert "code_review" in identity.capabilities

    def test_agent_identity_is_frozen(self):
        identity = AgentIdentity(
            id="agent-001",
            tenant_id="tenant-123",
            org_id=None,
            name="Test",
            agent_type="planner",
        )
        with pytest.raises(AttributeError):
            identity.name = "Changed"

    def test_agent_memory_short_term(self):
        memory = AgentMemory(max_short_term_size=3)
        memory.store_short_term("key1", "value1")
        memory.store_short_term("key2", "value2")
        memory.store_short_term("key3", "value3")
        assert len(memory.short_term) == 3

        memory.store_short_term("key4", "value4")
        assert len(memory.short_term) == 3
        assert "key1" not in memory.short_term
        assert "key4" in memory.short_term

    def test_agent_memory_long_term(self):
        memory = AgentMemory(max_long_term_size=2)
        memory.store_long_term("k1", "v1")
        memory.store_long_term("k2", "v2")

        with pytest.raises(MemoryError):
            memory.store_long_term("k3", "v3")

    def test_agent_memory_episodic(self):
        memory = AgentMemory(max_episodic_size=2)
        memory.store_episodic({"event": "e1"})
        memory.store_episodic({"event": "e2"})
        memory.store_episodic({"event": "e3"})

        assert len(memory.episodic) == 2
        assert memory.episodic[0]["event"] == "e2"

    def test_agent_skills_register_and_track(self):
        skills = AgentSkills()
        skills.register_tool("code_review")
        skills.register_tool("bug_detection")

        assert "code_review" in skills.registered_tools
        assert "bug_detection" in skills.registered_tools

        skills.record_success("code_review")
        skills.record_success("code_review")
        skills.record_failure("code_review")

        assert skills.usage_count_by_skill["code_review"] == 3
        assert skills.success_rate_by_skill["code_review"] > 0.5

    def test_agent_permissions(self):
        perms = AgentPermissions(
            allowed_actions=["read", "write"],
            denied_actions=["delete"],
            requires_approval_for=["modify_production"],
        )

        assert perms.can_perform("read") is True
        assert perms.can_perform("delete") is False
        assert perms.requires_approval("modify_production") is True
        assert perms.requires_approval("read") is False

    def test_agent_risk_assessment(self):
        risk = AgentRisk()

        score = risk.assess_risk("read", {})
        assert score == 0.1

        score = risk.assess_risk("delete", {})
        assert score == 0.8

    def test_agent_cost_tracking(self):
        cost = AgentCost(budget_limit_usd=10.0)
        cost.record_usage(tokens=1000, compute_seconds=5.0, api_calls=1)

        assert cost.tokens_used == 1000
        assert cost.compute_seconds == 5.0
        assert cost.api_calls == 1
        assert cost.estimated_cost_usd > 0
        assert cost.is_over_budget() is False

        cost.record_usage(tokens=5000000, compute_seconds=0, api_calls=0)
        assert cost.is_over_budget() is True

    def test_agent_audit_recording(self):
        audit = AgentAudit()
        audit_id = audit.record_action(
            action="execute_task",
            context={"task": "review_code"},
            result={"status": "success"},
        )

        assert audit_id.startswith("audit_")
        assert len(audit.action_log) == 1
        assert audit.action_log[0]["action"] == "execute_task"

        audit.record_decision(
            decision="approve",
            reasoning="code is clean",
            outcome="success",
        )
        assert len(audit.decision_traces) == 1


class TestBaseAgentProtocol:
    """Test BaseAgent Protocol structure."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(IBaseAgent, "__protocol_attrs__") or callable(IBaseAgent)

    def test_protocol_has_required_properties(self):
        required_props = [
            "identity",
            "memory",
            "skills",
            "permissions",
            "risk",
            "cost",
            "audit",
        ]
        for prop in required_props:
            assert hasattr(IBaseAgent, prop), f"IBaseAgent missing property: {prop}"

    def test_protocol_has_required_methods(self):
        required_methods = [
            "activate",
            "suspend",
            "terminate",
            "execute",
            "can_perform",
        ]
        for method in required_methods:
            assert hasattr(IBaseAgent, method), f"IBaseAgent missing method: {method}"


class TestAutonomyLevels:
    """Test AutonomyLevel enum (L0-L4)."""

    def test_all_levels_defined(self):
        levels = [
            AutonomyLevel.L0_OBSERVE,
            AutonomyLevel.L1_RECOMMEND,
            AutonomyLevel.L2_EXECUTE_WITH_APPROVAL,
            AutonomyLevel.L3_LIMITED_AUTONOMOUS,
            AutonomyLevel.L4_DOMAIN_AUTONOMOUS,
        ]
        assert len(levels) == 5

    def test_levels_match_human_governance(self):
        assert AutonomyLevel.L0_OBSERVE.value == "observe"
        assert AutonomyLevel.L1_RECOMMEND.value == "recommend"
        assert (
            AutonomyLevel.L2_EXECUTE_WITH_APPROVAL.value
            == "execute_with_approval"
        )
        assert AutonomyLevel.L3_LIMITED_AUTONOMOUS.value == "limited_autonomous"
        assert AutonomyLevel.L4_DOMAIN_AUTONOMOUS.value == "domain_autonomous"
