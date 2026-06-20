"""Tests for Agent ↔ ApprovalGate Integration (L0-L4 Autonomy).

Ref: RC16.8.4 — Agent ↔ ApprovalGate Integration
"""

import pytest

from core.agents.approval_integration import AgentApprovalGate


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
def approval_manager():
    return MockApprovalManager()


@pytest.fixture
def gate(approval_manager):
    return AgentApprovalGate(approval_manager)


# ── Test L0 (Observe Only) ──────────────────────────────────────────────────


def test_l0_blocks_all_actions(gate):
    """L0 observe-only mode blocks all actions."""
    result = gate.check_autonomy("agent-001", "read_data", "L0", {})
    assert result["allowed"] is False
    assert "observe-only" in result["reason"].lower()


# ── Test L1 (Recommend Only) ────────────────────────────────────────────────


def test_l1_allows_read(gate):
    """L1 allows read actions."""
    result = gate.check_autonomy("agent-001", "read_data", "L1", {})
    assert result["allowed"] is True


def test_l1_blocks_write(gate):
    """L1 blocks write actions."""
    result = gate.check_autonomy("agent-001", "create_resource", "L1", {})
    assert result["allowed"] is False
    assert "write" in result["reason"].lower()


# ── Test L2 (Execute with Approval) ─────────────────────────────────────────


def test_l2_requires_approval_for_write(gate, approval_manager):
    """L2 requires approval for write actions."""
    result = gate.check_autonomy(
        "agent-001", "create_resource", "L2", {"tenant_id": "t1"}
    )
    assert result["allowed"] is False
    assert result["requires_approval"] is True
    assert len(approval_manager.requests) == 1


def test_l2_requires_approval_for_execute(gate, approval_manager):
    """L2 requires approval for execute actions."""
    result = gate.check_autonomy(
        "agent-001", "execute_task", "L2", {"tenant_id": "t1"}
    )
    assert result["allowed"] is False
    assert result["requires_approval"] is True


# ── Test L3 (Limited Autonomous) ────────────────────────────────────────────


def test_l3_allows_all_actions(gate):
    """L3 allows all actions within bounds."""
    result = gate.check_autonomy("agent-001", "execute_task", "L3", {})
    assert result["allowed"] is True


# ── Test L4 (Full Autonomy) ─────────────────────────────────────────────────


def test_l4_full_autonomy(gate):
    """L4 allows full autonomy."""
    result = gate.check_autonomy("agent-001", "deploy_production", "L4", {})
    assert result["allowed"] is True


# ── Test Invalid Autonomy Level ─────────────────────────────────────────────


def test_invalid_autonomy_level(gate):
    """Invalid autonomy level is rejected."""
    result = gate.check_autonomy("agent-001", "read_data", "L9", {})
    assert result["allowed"] is False
    assert "invalid" in result["reason"].lower()


# ── Test Audit Trail ────────────────────────────────────────────────────────


def test_audit_trail_recorded(gate):
    """Every autonomy check is recorded in audit."""
    gate.check_autonomy("agent-001", "read_data", "L3", {})
    gate.check_autonomy("agent-001", "write_data", "L1", {})

    assert len(gate._audit.action_log) == 2
    assert gate._audit.action_log[0]["result"]["decision"] == "ALLOW"
    assert gate._audit.action_log[1]["result"]["decision"] == "DENY"


# ── Test L2 Fallback to DENY ────────────────────────────────────────────────


def test_l2_no_approval_manager_falls_back_to_deny():
    """If no ApprovalManager, L2 write/execute becomes DENY."""
    gate = AgentApprovalGate(approval_manager=None)
    result = gate.check_autonomy(
        "agent-001", "create_resource", "L2", {"tenant_id": "t1"}
    )
    assert result["allowed"] is False
    assert result["requires_approval"] is False
    assert "no approval manager" in result["reason"].lower()
