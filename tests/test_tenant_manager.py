"""Tests for TenantManager — Control Plane.

Ref: RC16.7-B Control Plane
"""

import pytest

from core.control_plane.tenant_manager import TenantManager


def test_create_tenant():
    manager = TenantManager()
    tenant = manager.create_tenant("Acme Corp")
    assert tenant.name == "Acme Corp"
    assert tenant.status == "active"
    assert tenant.id is not None


def test_get_tenant():
    manager = TenantManager()
    tenant = manager.create_tenant("Test Corp")
    retrieved = manager.get_tenant(tenant.id)
    assert retrieved is not None
    assert retrieved.name == "Test Corp"


def test_suspend_tenant():
    manager = TenantManager()
    tenant = manager.create_tenant("Suspend Me")
    assert manager.suspend_tenant(tenant.id) is True
    assert manager.get_tenant(tenant.id).status == "suspended"


def test_list_tenants_by_status():
    manager = TenantManager()
    manager.create_tenant("Active 1")
    manager.create_tenant("Active 2")
    t3 = manager.create_tenant("Suspended 1")
    manager.suspend_tenant(t3.id)

    active = manager.list_tenants(status="active")
    assert len(active) == 2

    suspended = manager.list_tenants(status="suspended")
    assert len(suspended) == 1
