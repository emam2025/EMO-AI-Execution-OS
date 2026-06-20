"""Approval Manager — Control Plane Implementation.

Implements IApprovalManager Protocol for human-in-the-loop approval management.
In-memory storage only — no database in this phase.

Ref: RC16.7-C.1 ApprovalManager
"""

from typing import Dict, List, Optional, Any
import uuid
from datetime import datetime, timezone

from core.interfaces.control_plane import (
    IApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
)


class ApprovalManager(IApprovalManager):
    """Manages human approval requests."""

    def __init__(self) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}

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
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            org_id=org_id,
            action=action,
            requested_by=requested_by,
            status=ApprovalStatus.PENDING,
            reason=reason,
            reviewer=None,
            reviewed_at=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        self._requests[req.id] = req
        return req

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Retrieve a request by ID."""
        return self._requests.get(request_id)

    def list_pending_requests(
        self, tenant_id: str, org_id: Optional[str] = None
    ) -> List[ApprovalRequest]:
        """List pending requests with optional filters."""
        reqs = [
            r
            for r in self._requests.values()
            if r.status == ApprovalStatus.PENDING and r.tenant_id == tenant_id
        ]
        if org_id is not None:
            reqs = [r for r in reqs if r.org_id == org_id]
        return reqs

    def approve_request(self, request_id: str, reviewer: str) -> bool:
        """Approve a pending request. Returns True if successful."""
        if (
            request_id in self._requests
            and self._requests[request_id].status == ApprovalStatus.PENDING
        ):
            self._requests[request_id].status = ApprovalStatus.APPROVED
            self._requests[request_id].reviewer = reviewer
            self._requests[request_id].reviewed_at = datetime.now(
                timezone.utc
            ).isoformat()
            return True
        return False

    def reject_request(
        self, request_id: str, reviewer: str, reason: str
    ) -> bool:
        """Reject a pending request. Returns True if successful."""
        if (
            request_id in self._requests
            and self._requests[request_id].status == ApprovalStatus.PENDING
        ):
            self._requests[request_id].status = ApprovalStatus.REJECTED
            self._requests[request_id].reviewer = reviewer
            self._requests[request_id].reason = reason
            self._requests[request_id].reviewed_at = datetime.now(
                timezone.utc
            ).isoformat()
            return True
        return False
