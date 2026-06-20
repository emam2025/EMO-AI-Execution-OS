"""Tests for ResourceManager — Control Plane.

Ref: RC16.7-B.3 ResourceManager
"""

import pytest

from core.control_plane.resource_manager import ResourceManager
from core.interfaces.control_plane import ResourceType, ResourceStatus


@pytest.fixture
def manager():
    return ResourceManager()


@pytest.fixture
def org_id():
    return "org-123"


@pytest.fixture
def tenant_id():
    return "tenant-456"


@pytest.fixture
def sample_agent(manager, org_id, tenant_id):
    return manager.create_resource(org_id, tenant_id, "CodeReviewer", ResourceType.AGENT)


def test_create_resource(manager, org_id, tenant_id):
    resource = manager.create_resource(org_id, tenant_id, "CodeReviewer", ResourceType.AGENT)
    assert resource.name == "CodeReviewer"
    assert resource.type == ResourceType.AGENT
    assert resource.status == ResourceStatus.ACTIVE
    assert resource.org_id == org_id
    assert resource.tenant_id == tenant_id
    assert resource.id is not None


def test_get_resource(manager, org_id, tenant_id, sample_agent):
    retrieved = manager.get_resource(sample_agent.id)
    assert retrieved is not None
    assert retrieved.name == "CodeReviewer"


def test_list_resources_by_org(manager, org_id, tenant_id):
    manager.create_resource(org_id, tenant_id, "Agent1", ResourceType.AGENT)
    manager.create_resource(org_id, tenant_id, "Workflow1", ResourceType.WORKFLOW)
    manager.create_resource("other-org", tenant_id, "Agent2", ResourceType.AGENT)

    org_resources = manager.list_resources(org_id=org_id)
    assert len(org_resources) == 2


def test_list_resources_by_type(manager, org_id, tenant_id):
    manager.create_resource(org_id, tenant_id, "Agent1", ResourceType.AGENT)
    manager.create_resource(org_id, tenant_id, "Agent2", ResourceType.AGENT)
    manager.create_resource(org_id, tenant_id, "Workflow1", ResourceType.WORKFLOW)

    agents = manager.list_resources(org_id=org_id, type=ResourceType.AGENT)
    assert len(agents) == 2


def test_list_resources_by_status(manager, org_id, tenant_id):
    agent1 = manager.create_resource(org_id, tenant_id, "Agent1", ResourceType.AGENT)
    manager.create_resource(org_id, tenant_id, "Agent2", ResourceType.AGENT)
    manager.suspend_resource(agent1.id)

    active = manager.list_resources(org_id=org_id, status=ResourceStatus.ACTIVE)
    assert len(active) == 1

    suspended = manager.list_resources(org_id=org_id, status=ResourceStatus.SUSPENDED)
    assert len(suspended) == 1


def test_suspend_resource(manager, org_id, tenant_id, sample_agent):
    assert manager.suspend_resource(sample_agent.id) is True
    assert manager.get_resource(sample_agent.id).status == ResourceStatus.SUSPENDED


def test_decommission_resource(manager, org_id, tenant_id, sample_agent):
    assert manager.decommission_resource(sample_agent.id) is True
    assert manager.get_resource(sample_agent.id).status == ResourceStatus.DECOMMISSIONED


def test_update_quota(manager, org_id, tenant_id, sample_agent):
    assert manager.update_quota(sample_agent.id, {"max_calls": 1000}) is True
    assert manager.get_resource(sample_agent.id).quota["max_calls"] == 1000
