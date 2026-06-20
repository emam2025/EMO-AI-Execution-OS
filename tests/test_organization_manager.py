"""Tests for OrganizationManager — Control Plane.

Ref: RC16.7-B.2 OrganizationManager
"""

import pytest

from core.control_plane.organization_manager import OrganizationManager


@pytest.fixture
def manager():
    return OrganizationManager()


@pytest.fixture
def tenant_id():
    return "tenant-123"


@pytest.fixture
def sample_org(manager, tenant_id):
    return manager.create_org(tenant_id, "Engineering")


def test_create_org(manager, tenant_id):
    org = manager.create_org(tenant_id, "Engineering")
    assert org.name == "Engineering"
    assert org.tenant_id == tenant_id
    assert org.status == "active"
    assert org.id is not None


def test_get_org(manager, tenant_id, sample_org):
    retrieved = manager.get_org(sample_org.id)
    assert retrieved is not None
    assert retrieved.name == "Engineering"


def test_list_orgs_by_tenant(manager, tenant_id):
    manager.create_org(tenant_id, "Engineering")
    manager.create_org(tenant_id, "Marketing")
    manager.create_org("other-tenant", "Sales")

    tenant_orgs = manager.list_orgs(tenant_id)
    assert len(tenant_orgs) == 2


def test_list_orgs_by_parent(manager, tenant_id):
    parent = manager.create_org(tenant_id, "Engineering")
    manager.create_org(tenant_id, "Backend", parent_id=parent.id)
    manager.create_org(tenant_id, "Frontend", parent_id=parent.id)

    children = manager.list_orgs(tenant_id, parent_id=parent.id)
    assert len(children) == 2


def test_get_hierarchy(manager, tenant_id):
    root = manager.create_org(tenant_id, "Company")
    dept = manager.create_org(tenant_id, "Engineering", parent_id=root.id)
    team = manager.create_org(tenant_id, "Backend", parent_id=dept.id)

    hierarchy = manager.get_hierarchy(team.id)
    assert len(hierarchy) == 3
    assert hierarchy[0].name == "Company"
    assert hierarchy[1].name == "Engineering"
    assert hierarchy[2].name == "Backend"


def test_delete_org(manager, tenant_id, sample_org):
    assert manager.delete_org(sample_org.id) is True
    assert manager.get_org(sample_org.id) is None


def test_delete_org_with_children_fails(manager, tenant_id):
    parent = manager.create_org(tenant_id, "Engineering")
    manager.create_org(tenant_id, "Backend", parent_id=parent.id)

    assert manager.delete_org(parent.id) is False
    assert manager.get_org(parent.id) is not None
