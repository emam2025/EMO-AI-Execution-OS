"""Tests for Industrial ↔ Control Plane Integration.

Ref: RC16.9.4 — Industrial ↔ Control Plane Integration
"""

import pytest

from core.industrial.integration import IndustrialIntegration
from core.industrial.asset_manager import AssetManager
from core.industrial.twin_manager import TwinManager


class MockTenantManager:
    """Mock ITenantManager for testing."""

    def __init__(self):
        self.tenants = {
            "tenant-123": {"id": "tenant-123", "name": "Acme Corp", "status": "active"}
        }

    def get_tenant(self, tenant_id):
        class MockTenant:
            def __init__(self, data):
                self.id = data["id"]
                self.name = data["name"]
                self.status = data["status"]

        return MockTenant(self.tenants[tenant_id]) if tenant_id in self.tenants else None


class MockOrgManager:
    """Mock IOrganizationManager for testing."""

    def __init__(self):
        self.orgs = {
            "org-456": {"id": "org-456", "name": "Engineering", "type": "department"}
        }

    def get_org(self, org_id):
        class MockOrg:
            def __init__(self, data):
                self.id = data["id"]
                self.name = data["name"]
                self.type = data["type"]

        return MockOrg(self.orgs[org_id]) if org_id in self.orgs else None


class MockResourceManager:
    """Mock IResourceManager for testing."""

    def __init__(self):
        self.resources = {}
        self.counter = 0

    def create_resource(self, org_id, tenant_id, name, type, quota=None):
        self.counter += 1
        resource_id = f"resource-{self.counter}"
        self.resources[resource_id] = {"id": resource_id, "name": name}

        class MockResource:
            def __init__(self, id):
                self.id = id

        return MockResource(resource_id)

    def decommission_resource(self, resource_id):
        if resource_id in self.resources:
            del self.resources[resource_id]
            return True
        return False


@pytest.fixture
def asset_manager():
    return AssetManager()


@pytest.fixture
def twin_manager():
    return TwinManager()


@pytest.fixture
def tenant_manager():
    return MockTenantManager()


@pytest.fixture
def org_manager():
    return MockOrgManager()


@pytest.fixture
def resource_manager():
    return MockResourceManager()


@pytest.fixture
def integration(asset_manager, twin_manager, tenant_manager, org_manager, resource_manager):
    return IndustrialIntegration(
        asset_manager=asset_manager,
        twin_manager=twin_manager,
        tenant_manager=tenant_manager,
        org_manager=org_manager,
        resource_manager=resource_manager,
    )


def test_register_asset_success(integration):
    """Test successful asset registration with tenant/org validation."""
    result = integration.register_asset(
        tenant_id="tenant-123",
        org_id="org-456",
        name="CNC Machine",
        asset_type="machine",
        metadata={"location": "Plant A"},
    )
    assert result["success"] is True
    assert result["asset_id"] is not None
    assert result["resource_id"] is not None


def test_register_asset_invalid_tenant(integration):
    """Test asset registration with invalid tenant."""
    result = integration.register_asset(
        tenant_id="invalid-tenant",
        org_id="org-456",
        name="Machine",
        asset_type="machine",
        metadata={},
    )
    assert result["success"] is False
    assert "Tenant not found" in result["error"]


def test_register_asset_invalid_org(integration):
    """Test asset registration with invalid org."""
    result = integration.register_asset(
        tenant_id="tenant-123",
        org_id="invalid-org",
        name="Machine",
        asset_type="machine",
        metadata={},
    )
    assert result["success"] is False
    assert "Organization not found" in result["error"]


def test_register_asset_invalid_type(integration):
    """Test asset registration with invalid asset type."""
    result = integration.register_asset(
        tenant_id="tenant-123",
        org_id="org-456",
        name="Machine",
        asset_type="invalid_type",
        metadata={},
    )
    assert result["success"] is False
    assert "Invalid asset_type" in result["error"]


def test_unregister_asset(integration):
    """Test asset unregistration (cascade delete)."""
    # Register
    reg_result = integration.register_asset(
        tenant_id="tenant-123",
        org_id="org-456",
        name="Machine",
        asset_type="machine",
        metadata={},
    )
    asset_id = reg_result["asset_id"]

    # Update twin state
    integration._tm.update_twin_state(asset_id, {"temp": 75})

    # Unregister
    unreg_result = integration.unregister_asset(asset_id)
    assert unreg_result["success"] is True
    assert unreg_result["asset_deleted"] is True
    assert unreg_result["twin_cleared"] is True
    assert unreg_result["resource_decommissioned"] is True


def test_get_asset_with_tenant(integration):
    """Test getting asset with tenant/org info."""
    reg_result = integration.register_asset(
        tenant_id="tenant-123",
        org_id="org-456",
        name="CNC Machine",
        asset_type="machine",
        metadata={},
    )
    asset_id = reg_result["asset_id"]

    result = integration.get_asset_with_tenant(asset_id)
    assert result["exists"] is True
    assert result["asset"]["name"] == "CNC Machine"
    assert result["tenant"]["name"] == "Acme Corp"
    assert result["org"]["name"] == "Engineering"


def test_get_asset_not_found(integration):
    """Test getting non-existent asset."""
    result = integration.get_asset_with_tenant("nonexistent")
    assert result["exists"] is False
    assert result["asset"] is None


def test_register_without_resource_manager(asset_manager, twin_manager, tenant_manager, org_manager):
    """Test registration without resource_manager (optional)."""
    integration = IndustrialIntegration(
        asset_manager=asset_manager,
        twin_manager=twin_manager,
        tenant_manager=tenant_manager,
        org_manager=org_manager,
        resource_manager=None,  # No resource tracking
    )

    result = integration.register_asset(
        tenant_id="tenant-123",
        org_id="org-456",
        name="Machine",
        asset_type="machine",
        metadata={},
    )
    assert result["success"] is True
    assert result["asset_id"] is not None
    assert result["resource_id"] is None  # No resource created


def test_register_without_tenant_manager(asset_manager, twin_manager, org_manager, resource_manager):
    """Test registration without tenant_manager (no validation)."""
    integration = IndustrialIntegration(
        asset_manager=asset_manager,
        twin_manager=twin_manager,
        tenant_manager=None,  # No tenant validation
        org_manager=org_manager,
        resource_manager=resource_manager,
    )

    result = integration.register_asset(
        tenant_id="any-tenant",
        org_id="org-456",
        name="Machine",
        asset_type="machine",
        metadata={},
    )
    assert result["success"] is True  # No validation, so it succeeds


def test_multiple_assets(integration):
    """Test registering multiple assets."""
    result1 = integration.register_asset("tenant-123", "org-456", "Machine 1", "machine", {})
    result2 = integration.register_asset("tenant-123", "org-456", "Sensor 1", "sensor", {})

    assert result1["success"] is True
    assert result2["success"] is True
    assert result1["asset_id"] != result2["asset_id"]
