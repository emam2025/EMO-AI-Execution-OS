"""Control Plane Interfaces.

Defines Protocols for multi-tenant control plane components.
Follows Canon LAW 1-27 — Protocol-first design.

Ref: RC16.7-B Control Plane
"""

from typing import Protocol, Dict, List, Optional, Any
from datetime import datetime, timezone
from enum import Enum


class Tenant:
    """Represents a tenant in the system."""

    id: str
    name: str
    status: str  # "active", "suspended", "archived"
    created_at: str
    quota: Dict[str, int]

    def __init__(
        self,
        id: str,
        name: str,
        status: str,
        created_at: str,
        quota: Dict[str, int],
    ) -> None:
        self.id = id
        self.name = name
        self.status = status
        self.created_at = created_at
        self.quota = quota


class ITenantManager(Protocol):
    """Protocol for tenant lifecycle management."""

    def create_tenant(
        self, name: str, quota: Optional[Dict[str, int]] = None
    ) -> Tenant:
        """Create a new tenant with optional quota."""
        ...

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Retrieve a tenant by ID."""
        ...

    def list_tenants(self, status: Optional[str] = None) -> List[Tenant]:
        """List tenants, optionally filtered by status."""
        ...

    def suspend_tenant(self, tenant_id: str) -> bool:
        """Suspend a tenant. Returns True if successful."""
        ...

    def update_quota(self, tenant_id: str, new_quota: Dict[str, int]) -> bool:
        """Update tenant quota. Returns True if successful."""
        ...


class Organization:
    """Represents an organizational unit within a tenant."""

    id: str
    tenant_id: str
    name: str
    parent_id: Optional[str]
    type: str  # "department", "division", "team"
    metadata: Dict[str, Any]
    created_at: str
    status: str  # "active", "archived"

    def __init__(
        self,
        id: str,
        tenant_id: str,
        name: str,
        parent_id: Optional[str],
        type: str,
        metadata: Dict[str, Any],
        created_at: str,
        status: str,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.name = name
        self.parent_id = parent_id
        self.type = type
        self.metadata = metadata
        self.created_at = created_at
        self.status = status


class IOrganizationManager(Protocol):
    """Protocol for organization lifecycle management."""

    def create_org(
        self,
        tenant_id: str,
        name: str,
        parent_id: Optional[str] = None,
        type: str = "department",
    ) -> Organization:
        """Create a new organization within a tenant."""
        ...

    def get_org(self, org_id: str) -> Optional[Organization]:
        """Retrieve an organization by ID."""
        ...

    def list_orgs(
        self, tenant_id: str, parent_id: Optional[str] = None
    ) -> List[Organization]:
        """List organizations within a tenant, optionally filtered by parent."""
        ...

    def get_hierarchy(self, org_id: str) -> List[Organization]:
        """Get full hierarchy from root to this org."""
        ...

    def delete_org(self, org_id: str) -> bool:
        """Delete an organization. Fails if has children."""
        ...


class ResourceType(Enum):
    """Types of resources in the system."""

    AGENT = "agent"
    WORKFLOW = "workflow"
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"


class ResourceStatus(Enum):
    """Status of a resource."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DECOMMISSIONED = "decommissioned"


class Resource:
    """Represents a resource within an organization."""

    id: str
    org_id: str
    tenant_id: str
    name: str
    type: ResourceType
    status: ResourceStatus
    quota: Dict[str, Any]
    metadata: Dict[str, Any]
    created_at: str

    def __init__(
        self,
        id: str,
        org_id: str,
        tenant_id: str,
        name: str,
        type: ResourceType,
        status: ResourceStatus,
        quota: Dict[str, Any],
        metadata: Dict[str, Any],
        created_at: str,
    ) -> None:
        self.id = id
        self.org_id = org_id
        self.tenant_id = tenant_id
        self.name = name
        self.type = type
        self.status = status
        self.quota = quota
        self.metadata = metadata
        self.created_at = created_at


class IResourceManager(Protocol):
    """Protocol for resource lifecycle management."""

    def create_resource(
        self,
        org_id: str,
        tenant_id: str,
        name: str,
        type: ResourceType,
        quota: Optional[Dict[str, Any]] = None,
    ) -> Resource:
        """Create a new resource within an organization."""
        ...

    def get_resource(self, resource_id: str) -> Optional[Resource]:
        """Retrieve a resource by ID."""
        ...

    def list_resources(
        self,
        org_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
    ) -> List[Resource]:
        """List resources with optional filters."""
        ...

    def suspend_resource(self, resource_id: str) -> bool:
        """Suspend a resource. Returns True if successful."""
        ...

    def decommission_resource(self, resource_id: str) -> bool:
        """Decommission a resource. Returns True if successful."""
        ...

    def update_quota(self, resource_id: str, new_quota: Dict[str, Any]) -> bool:
        """Update resource quota. Returns True if successful."""
        ...


class PolicyType(Enum):
    """Types of policies in the system."""

    RESOURCE_LIMIT = "resource_limit"
    APPROVAL_REQUIRED = "approval_required"
    ACCESS_CONTROL = "access_control"


class PolicyStatus(Enum):
    """Status of a policy."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Policy:
    """Represents a policy within the system."""

    id: str
    tenant_id: str
    org_id: Optional[str]
    name: str
    policy_type: PolicyType
    rules: Dict[str, Any]
    status: PolicyStatus
    created_at: str

    def __init__(
        self,
        id: str,
        tenant_id: str,
        org_id: Optional[str],
        name: str,
        policy_type: PolicyType,
        rules: Dict[str, Any],
        status: PolicyStatus,
        created_at: str,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.org_id = org_id
        self.name = name
        self.policy_type = policy_type
        self.rules = rules
        self.status = status
        self.created_at = created_at


class IPolicyManager(Protocol):
    """Protocol for policy lifecycle management."""

    def create_policy(
        self,
        tenant_id: str,
        name: str,
        policy_type: PolicyType,
        rules: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> Policy:
        """Create a new policy."""
        ...

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Retrieve a policy by ID."""
        ...

    def list_policies(
        self,
        tenant_id: str,
        org_id: Optional[str] = None,
        policy_type: Optional[PolicyType] = None,
    ) -> List[Policy]:
        """List policies with optional filters."""
        ...

    def update_policy_status(self, policy_id: str, status: PolicyStatus) -> bool:
        """Update policy status. Returns True if successful."""
        ...

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy. Returns True if successful."""
        ...

    def evaluate(
        self,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate all active policies against an action."""
        ...


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class ApprovalRequest:
    """Represents a human approval request."""

    id: str
    tenant_id: str
    org_id: Optional[str]
    action: str
    requested_by: str
    status: ApprovalStatus
    reason: str
    reviewer: Optional[str]
    reviewed_at: Optional[str]
    created_at: str
    metadata: Dict[str, Any]

    def __init__(
        self,
        id: str,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        requested_by: str,
        status: ApprovalStatus,
        reason: str,
        reviewer: Optional[str],
        reviewed_at: Optional[str],
        created_at: str,
        metadata: Dict[str, Any],
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.org_id = org_id
        self.action = action
        self.requested_by = requested_by
        self.status = status
        self.reason = reason
        self.reviewer = reviewer
        self.reviewed_at = reviewed_at
        self.created_at = created_at
        self.metadata = metadata


class IApprovalManager(Protocol):
    """Protocol for human approval management."""

    def create_request(
        self,
        tenant_id: str,
        action: str,
        requested_by: str,
        reason: str,
        org_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Create a new approval request."""
        ...

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Retrieve a request by ID."""
        ...

    def list_pending_requests(
        self, tenant_id: str, org_id: Optional[str] = None
    ) -> List[ApprovalRequest]:
        """List pending requests with optional filters."""
        ...

    def approve_request(self, request_id: str, reviewer: str) -> bool:
        """Approve a pending request. Returns True if successful."""
        ...

    def reject_request(
        self, request_id: str, reviewer: str, reason: str
    ) -> bool:
        """Reject a pending request. Returns True if successful."""
        ...
