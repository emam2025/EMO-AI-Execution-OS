"""Tests for ApprovalGate — Runtime.

Ref: RC16.7-C.2 Human Governance Integration
"""

import pytest

from core.runtime.autonomy.approval_gate import ApprovalGate


class MockPolicyManager:
    def evaluate(self, tenant_id, org_id, action, context):
        if action == "safe_action":
            return {"allowed": True, "violations": []}
        elif action == "needs_approval":
            return {
                "allowed": False,
                "violations": [
                    "Policy 'X' requires human approval for action 'needs_approval'."
                ],
            }
        else:
            return {"allowed": False, "violations": ["Resource limit exceeded."]}


class MockApprovalManager:
    def __init__(self):
        self.requests = []

    def create_request(
        self, tenant_id, org_id, action, requested_by, reason, metadata=None
    ):
        req_id = "req-123"
        self.requests.append(req_id)

        class MockReq:
            id = req_id

        return MockReq()


@pytest.fixture
def gate():
    return ApprovalGate(MockPolicyManager(), MockApprovalManager())


def test_gate_approves_safe_action(gate):
    result = gate.check_and_request("t1", "o1", "safe_action", "user1", {})
    assert result["status"] == "APPROVED"
    assert result["request_id"] is None


def test_gate_pends_action_needing_approval(gate):
    result = gate.check_and_request(
        "t1", "o1", "needs_approval", "user1", {"key": "value"}
    )
    assert result["status"] == "PENDING"
    assert result["request_id"] == "req-123"
    assert "requires human approval" in result["reason"].lower()


def test_gate_rejects_hard_violations(gate):
    result = gate.check_and_request(
        "t1", "o1", "dangerous_action", "user1", {}
    )
    assert result["status"] == "REJECTED"
    assert result["request_id"] is None
    assert "limit exceeded" in result["reason"].lower()
