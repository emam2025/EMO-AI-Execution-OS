"""Organization Manager — Control Plane Implementation.

Implements IOrganizationManager Protocol for hierarchical organization management.
In-memory storage only — no database in this phase.

Ref: RC16.7-B.2 OrganizationManager
"""

from typing import Dict, List, Optional, Any
import uuid
from datetime import datetime, timezone

from core.interfaces.control_plane import IOrganizationManager, Organization


class OrganizationManager(IOrganizationManager):
    """Manages organizational hierarchy within tenants."""

    def __init__(self) -> None:
        self._orgs: Dict[str, Organization] = {}

    def create_org(
        self,
        tenant_id: str,
        name: str,
        parent_id: Optional[str] = None,
        type: str = "department",
    ) -> Organization:
        """Create a new organization within a tenant."""
        org = Organization(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            parent_id=parent_id,
            type=type,
            metadata={},
            created_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )
        self._orgs[org.id] = org
        return org

    def get_org(self, org_id: str) -> Optional[Organization]:
        """Retrieve an organization by ID."""
        return self._orgs.get(org_id)

    def list_orgs(
        self, tenant_id: str, parent_id: Optional[str] = None
    ) -> List[Organization]:
        """List organizations within a tenant, optionally filtered by parent."""
        orgs = [o for o in self._orgs.values() if o.tenant_id == tenant_id]
        if parent_id is not None:
            orgs = [o for o in orgs if o.parent_id == parent_id]
        return orgs

    def get_hierarchy(self, org_id: str) -> List[Organization]:
        """Get full hierarchy from root to this org."""
        hierarchy: List[Organization] = []
        current = self._orgs.get(org_id)
        while current:
            hierarchy.insert(0, current)
            current = (
                self._orgs.get(current.parent_id) if current.parent_id else None
            )
        return hierarchy

    def delete_org(self, org_id: str) -> bool:
        """Delete an organization. Fails if has children."""
        if org_id in self._orgs:
            children = [
                o for o in self._orgs.values() if o.parent_id == org_id
            ]
            if children:
                return False
            del self._orgs[org_id]
            return True
        return False
