"""Tests for Agent ↔ PolicyManager Integration.

Ref: RC16.8.3 — Agent ↔ PolicyManager Integration
"""

import pytest

from core.agents.policy_integration import AgentPolicyGate


class MockPolicyManager:
    """Mock IPolicyManager for testing."""

    def __init__(self, policy_response=None):
        self.policy_response = policy_response or {
            "allowed": True,
            "violations": [],
        }

    def evaluate(self, tenant_id, org_id, action, context):
        return self.policy_response


class MockApprovalManager:
    """Mock IApprovalManager for testing."""

    def __init__(self):
        self.requests = []

    def create_request(
        self, tenant_id, org_id, action, requested_by, reason, metadata=None
    ):
        class MockReq:
            id = f"req-{len(self.requests)}"

        req = MockReq()
        self.requests.append(req)
        return req


@pytest.fixture
def allow_policy():
    return MockPolicyManager({"allowed": True, "violations": []})


@pytest.fixture
def deny_policy():
    return MockPolicyManager(
        {"allowed": False, "violations": ["Resource limit exceeded"]}
    )


@pytest.fixture
def approval_policy():
    return MockPolicyManager(
        {
            "allowed": False,
            "violations": [
                "Policy 'X' requires human approval for action 'dangerous_action'."
            ],
        }
    )


@pytest.fixture
def approval_manager():
    return MockApprovalManager()


@pytest.fixture
def agent_policy_gate(allow_policy):
    return AgentPolicyGate(allow_policy)


# ── Test ALLOW ──────────────────────────────────────────────────────────────


def test_allow_action(agent_policy_gate):
    """Action allowed by policy."""
    result = agent_policy_gate.evaluate_action(
        agent_id="agent-001",
        tenant_id="tenant-123",
        org_id="org-456",
        action="read_data",
        context={},
    )
    assert result["decision"] == "ALLOW"
    assert result["approval_request_id"] is None


# ── Test DENY ───────────────────────────────────────────────────────────────


def test_deny_action(deny_policy):
    """Action denied by policy (hard violation)."""
    gate = AgentPolicyGate(deny_policy)
    result = gate.evaluate_action(
        agent_id="agent-001",
        tenant_id="tenant-123",
        org_id="org-456",
        action="delete_production",
        context={},
    )
    assert result["decision"] == "DENY"
    assert "limit exceeded" in result["reason"].lower()
    assert result["approval_request_id"] is None


# ── Test REQUIRE_APPROVAL ───────────────────────────────────────────────────


def test_require_approval(approval_policy, approval_manager):
    """Action requires human approval."""
    gate = AgentPolicyGate(approval_policy, approval_manager)
    result = gate.evaluate_action(
        agent_id="agent-001",
        tenant_id="tenant-123",
        org_id="org-456",
        action="dangerous_action",
        context={},
    )
    assert result["decision"] == "REQUIRE_APPROVAL"
    assert result["approval_request_id"] is not None
    assert len(approval_manager.requests) == 1


# ── Test Audit Trail ────────────────────────────────────────────────────────


def test_audit_trail_on_allow(allow_policy):
    """ALLOW decision recorded in audit."""
    gate = AgentPolicyGate(allow_policy)
    gate.evaluate_action("agent-001", "tenant-123", None, "read", {})
    assert len(gate._audit.action_log) == 1
    assert gate._audit.action_log[0]["result"]["decision"] == "ALLOW"


def test_audit_trail_on_deny(deny_policy):
    """DENY decision recorded in audit."""
    gate = AgentPolicyGate(deny_policy)
    gate.evaluate_action("agent-001", "tenant-123", None, "delete", {})
    assert len(gate._audit.action_log) == 1
    assert gate._audit.action_log[0]["result"]["decision"] == "DENY"


def test_audit_trail_on_approval(approval_policy, approval_manager):
    """REQUIRE_APPROVAL decision recorded in audit."""
    gate = AgentPolicyGate(approval_policy, approval_manager)
    gate.evaluate_action("agent-001", "tenant-123", None, "dangerous", {})
    assert len(gate._audit.action_log) == 1
    assert gate._audit.action_log[0]["result"]["decision"] == "REQUIRE_APPROVAL"


# ── Test Fallback to DENY ──────────────────────────────────────────────────


def test_no_approval_manager_falls_back_to_deny(approval_policy):
    """If no ApprovalManager, REQUIRE_APPROVAL becomes DENY."""
    gate = AgentPolicyGate(approval_policy, approval_manager=None)
    result = gate.evaluate_action(
        "agent-001", "tenant-123", None, "dangerous", {}
    )
    assert result["decision"] == "DENY"
    assert result["approval_request_id"] is None


# ── Test Context Forwarding ─────────────────────────────────────────────────


def test_context_passed_to_policy(allow_policy):
    """Context is passed to PolicyManager.evaluate()."""
    gate = AgentPolicyGate(allow_policy)
    result = gate.evaluate_action(
        agent_id="agent-001",
        tenant_id="tenant-123",
        org_id="org-456",
        action="read",
        context={"key": "value"},
    )
    assert result["decision"] == "ALLOW"
