"""Tests for PolicyManager — Control Plane.

Ref: RC16.7-B.4 PolicyManager
"""

import pytest

from core.control_plane.policy_manager import PolicyManager
from core.interfaces.control_plane import PolicyType, PolicyStatus


@pytest.fixture
def manager():
    return PolicyManager()


@pytest.fixture
def tenant_id():
    return "tenant-123"


@pytest.fixture
def org_id():
    return "org-456"


@pytest.fixture
def sample_policy(manager, tenant_id, org_id):
    return manager.create_policy(
        tenant_id=tenant_id,
        name="Max Agents Limit",
        policy_type=PolicyType.RESOURCE_LIMIT,
        rules={"max_count": 5},
        org_id=org_id,
    )


def test_create_policy(manager, tenant_id, org_id):
    policy = manager.create_policy(
        tenant_id, "Test Policy", PolicyType.ACCESS_CONTROL, {"role": "admin"}, org_id
    )
    assert policy.name == "Test Policy"
    assert policy.tenant_id == tenant_id
    assert policy.org_id == org_id
    assert policy.status == PolicyStatus.ACTIVE
    assert policy.id is not None


def test_get_policy(manager, tenant_id, org_id, sample_policy):
    retrieved = manager.get_policy(sample_policy.id)
    assert retrieved is not None
    assert retrieved.name == "Max Agents Limit"


def test_list_policies_by_tenant_and_org(manager, tenant_id, org_id):
    manager.create_policy(tenant_id, "Tenant Wide", PolicyType.ACCESS_CONTROL, {})
    manager.create_policy(
        tenant_id, "Org Specific", PolicyType.RESOURCE_LIMIT, {}, org_id
    )

    policies = manager.list_policies(tenant_id, org_id)
    assert len(policies) == 2

    other_policies = manager.list_policies(tenant_id, "other-org")
    assert len(other_policies) == 1
    assert other_policies[0].name == "Tenant Wide"


def test_update_policy_status(manager, tenant_id, org_id, sample_policy):
    assert (
        manager.update_policy_status(sample_policy.id, PolicyStatus.INACTIVE) is True
    )
    assert manager.get_policy(sample_policy.id).status == PolicyStatus.INACTIVE

    active_policies = manager.list_policies(tenant_id, org_id)
    assert sample_policy.id not in [p.id for p in active_policies]


def test_delete_policy(manager, tenant_id, org_id, sample_policy):
    assert manager.delete_policy(sample_policy.id) is True
    assert manager.get_policy(sample_policy.id) is None


def test_evaluate_resource_limit_allowed(manager, tenant_id, org_id):
    manager.create_policy(
        tenant_id, "Max 5 Agents", PolicyType.RESOURCE_LIMIT, {"max_count": 5}, org_id
    )

    result = manager.evaluate(
        tenant_id, org_id, "create_agent", {"current_count": 3}
    )
    assert result["allowed"] is True
    assert len(result["violations"]) == 0


def test_evaluate_resource_limit_denied(manager, tenant_id, org_id):
    manager.create_policy(
        tenant_id, "Max 5 Agents", PolicyType.RESOURCE_LIMIT, {"max_count": 5}, org_id
    )

    result = manager.evaluate(
        tenant_id, org_id, "create_agent", {"current_count": 5}
    )
    assert result["allowed"] is False
    assert len(result["violations"]) == 1
    assert "max_count (5) reached" in result["violations"][0]


def test_evaluate_approval_required(manager, tenant_id, org_id):
    manager.create_policy(
        tenant_id,
        "Require Approval",
        PolicyType.APPROVAL_REQUIRED,
        {"require_approval_for": ["delete_resource"]},
        org_id,
    )

    result = manager.evaluate(tenant_id, org_id, "delete_resource", {})
    assert result["allowed"] is False
    assert "requires human approval" in result["violations"][0]
