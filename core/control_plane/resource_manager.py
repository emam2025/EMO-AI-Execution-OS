"""Resource Manager — Control Plane Implementation.

Implements IResourceManager Protocol for resource lifecycle management.
In-memory storage only — no database in this phase.

Ref: RC16.7-B.3 ResourceManager
"""

from typing import Dict, List, Optional, Any
import uuid
from datetime import datetime, timezone

from core.interfaces.control_plane import (
    IResourceManager,
    Resource,
    ResourceType,
    ResourceStatus,
)


class ResourceManager(IResourceManager):
    """Manages resources within organizations."""

    def __init__(self) -> None:
        self._resources: Dict[str, Resource] = {}

    def create_resource(
        self,
        org_id: str,
        tenant_id: str,
        name: str,
        type: ResourceType,
        quota: Optional[Dict[str, Any]] = None,
    ) -> Resource:
        """Create a new resource within an organization."""
        resource = Resource(
            id=str(uuid.uuid4()),
            org_id=org_id,
            tenant_id=tenant_id,
            name=name,
            type=type,
            status=ResourceStatus.ACTIVE,
            quota=quota or {},
            metadata={},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._resources[resource.id] = resource
        return resource

    def get_resource(self, resource_id: str) -> Optional[Resource]:
        """Retrieve a resource by ID."""
        return self._resources.get(resource_id)

    def list_resources(
        self,
        org_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
    ) -> List[Resource]:
        """List resources with optional filters."""
        resources = list(self._resources.values())

        if org_id is not None:
            resources = [r for r in resources if r.org_id == org_id]
        if tenant_id is not None:
            resources = [r for r in resources if r.tenant_id == tenant_id]
        if type is not None:
            resources = [r for r in resources if r.type == type]
        if status is not None:
            resources = [r for r in resources if r.status == status]

        return resources

    def suspend_resource(self, resource_id: str) -> bool:
        """Suspend a resource. Returns True if successful."""
        if resource_id in self._resources:
            self._resources[resource_id].status = ResourceStatus.SUSPENDED
            return True
        return False

    def decommission_resource(self, resource_id: str) -> bool:
        """Decommission a resource. Returns True if successful."""
        if resource_id in self._resources:
            self._resources[resource_id].status = ResourceStatus.DECOMMISSIONED
            return True
        return False

    def update_quota(self, resource_id: str, new_quota: Dict[str, Any]) -> bool:
        """Update resource quota. Returns True if successful."""
        if resource_id in self._resources:
            self._resources[resource_id].quota.update(new_quota)
            return True
        return False
