"""Tests for ApprovalManager — Control Plane.

Ref: RC16.7-C.1 ApprovalManager
"""

import pytest

from core.control_plane.approval_manager import ApprovalManager
from core.interfaces.control_plane import ApprovalStatus


@pytest.fixture
def manager():
    return ApprovalManager()


@pytest.fixture
def tenant_id():
    return "tenant-123"


@pytest.fixture
def org_id():
    return "org-456"


@pytest.fixture
def sample_request(manager, tenant_id, org_id):
    return manager.create_request(
        tenant_id=tenant_id,
        org_id=org_id,
        action="delete_production_db",
        requested_by="user-001",
        reason="Routine cleanup",
    )


def test_create_request(manager, tenant_id, org_id):
    req = manager.create_request(
        tenant_id, "deploy_code", "user-002", "New feature", org_id
    )
    assert req.action == "deploy_code"
    assert req.status == ApprovalStatus.PENDING
    assert req.id is not None


def test_get_request(manager, tenant_id, org_id, sample_request):
    retrieved = manager.get_request(sample_request.id)
    assert retrieved is not None
    assert retrieved.action == "delete_production_db"


def test_list_pending_requests(manager, tenant_id, org_id):
    manager.create_request(tenant_id, "action1", "user1", "reason1", org_id)
    manager.create_request(tenant_id, "action2", "user2", "reason2", org_id)

    pending = manager.list_pending_requests(tenant_id, org_id)
    assert len(pending) == 2


def test_approve_request(manager, tenant_id, org_id, sample_request):
    assert manager.approve_request(sample_request.id, "admin-001") is True
    updated = manager.get_request(sample_request.id)
    assert updated.status == ApprovalStatus.APPROVED
    assert updated.reviewer == "admin-001"
    assert updated.reviewed_at is not None


def test_reject_request(manager, tenant_id, org_id, sample_request):
    assert (
        manager.reject_request(sample_request.id, "admin-001", "Too risky") is True
    )
    updated = manager.get_request(sample_request.id)
    assert updated.status == ApprovalStatus.REJECTED
    assert updated.reviewer == "admin-001"
    assert "risky" in updated.reason.lower()


def test_cannot_approve_already_processed(manager, tenant_id, org_id, sample_request):
    manager.approve_request(sample_request.id, "admin-001")
    assert manager.approve_request(sample_request.id, "admin-002") is False
