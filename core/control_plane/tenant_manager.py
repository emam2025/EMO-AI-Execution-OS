"""Tenant Manager — Control Plane Implementation.

Implements ITenantManager Protocol for multi-tenant lifecycle management.
In-memory storage only — no database in this phase.

Ref: RC16.7-B Control Plane
"""

from typing import Dict, List, Optional
import uuid
from datetime import datetime, timezone

from core.interfaces.control_plane import ITenantManager, Tenant


class TenantManager(ITenantManager):
    """Manages tenant lifecycle (create, get, list, suspend, update quota)."""

    def __init__(self) -> None:
        self._tenants: Dict[str, Tenant] = {}

    def create_tenant(
        self, name: str, quota: Optional[Dict[str, int]] = None
    ) -> Tenant:
        """Create a new tenant with optional quota."""
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=name,
            status="active",
            created_at=datetime.now(timezone.utc).isoformat(),
            quota=quota or {"max_agents": 10, "max_workflows": 50},
        )
        self._tenants[tenant.id] = tenant
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Retrieve a tenant by ID."""
        return self._tenants.get(tenant_id)

    def list_tenants(self, status: Optional[str] = None) -> List[Tenant]:
        """List tenants, optionally filtered by status."""
        if status:
            return [t for t in self._tenants.values() if t.status == status]
        return list(self._tenants.values())

    def suspend_tenant(self, tenant_id: str) -> bool:
        """Suspend a tenant. Returns True if successful."""
        if tenant_id in self._tenants:
            self._tenants[tenant_id].status = "suspended"
            return True
        return False

    def update_quota(self, tenant_id: str, new_quota: Dict[str, int]) -> bool:
        """Update tenant quota. Returns True if successful."""
        if tenant_id in self._tenants:
            self._tenants[tenant_id].quota.update(new_quota)
            return True
        return False
