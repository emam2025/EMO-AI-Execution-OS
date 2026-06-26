"""Approval Manager — Control Plane Implementation.

Implements IApprovalManager Protocol for human-in-the-loop approval management.
Sync methods (in-memory) + async methods (DB-backed persistence).

Ref: RC16.7-C.1 ApprovalManager, P1-01 persistence
"""

from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone

from core.interfaces.control_plane import (
    IApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
)


class ApprovalManager(IApprovalManager):
    """Manages human approval requests.

    Sync methods work in-memory only (backward compat).
    Async methods work in-memory + persist to DB (P1-01).
    """

    def __init__(self, db: Any = None) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}
        self._db = db

    # ── Sync methods (in-memory only, backward compat) ────────────────

    def create_request(
        self,
        tenant_id: str,
        action: str,
        requested_by: str,
        reason: str,
        org_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
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
        return self._requests.get(request_id)

    def list_pending_requests(
        self, tenant_id: str, org_id: Optional[str] = None
    ) -> List[ApprovalRequest]:
        reqs = [
            r
            for r in self._requests.values()
            if r.status == ApprovalStatus.PENDING and r.tenant_id == tenant_id
        ]
        if org_id is not None:
            reqs = [r for r in reqs if r.org_id == org_id]
        return reqs

    def approve_request(self, request_id: str, reviewer: str) -> bool:
        if (
            request_id in self._requests
            and self._requests[request_id].status == ApprovalStatus.PENDING
        ):
            req = self._requests[request_id]
            req.status = ApprovalStatus.APPROVED
            req.reviewer = reviewer
            req.reviewed_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    def reject_request(
        self, request_id: str, reviewer: str, reason: str
    ) -> bool:
        if (
            request_id in self._requests
            and self._requests[request_id].status == ApprovalStatus.PENDING
        ):
            req = self._requests[request_id]
            req.status = ApprovalStatus.REJECTED
            req.reviewer = reviewer
            req.reason = reason
            req.reviewed_at = datetime.now(timezone.utc).isoformat()
            return True
        return False

    # ── Async methods (in-memory + DB persistence) ───────────────────

    async def async_create_request(
        self,
        tenant_id: str,
        action: str,
        requested_by: str,
        reason: str,
        org_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        req = self.create_request(
            tenant_id=tenant_id,
            action=action,
            requested_by=requested_by,
            reason=reason,
            org_id=org_id,
            metadata=metadata,
        )
        if self._db is not None:
            await self._db.create_approval_request({
                "id": req.id,
                "tenant_id": req.tenant_id,
                "org_id": req.org_id or "",
                "action": req.action,
                "requested_by": req.requested_by,
                "status": req.status.value if hasattr(req.status, "value") else req.status,
                "reason": req.reason,
                "reviewer": "",
                "reviewed_at": None,
                "metadata": "{}",
            })
        return req

    async def async_approve_request(self, request_id: str, reviewer: str) -> bool:
        ok = self.approve_request(request_id, reviewer)
        if ok and self._db is not None:
            req = self._requests.get(request_id)
            if req:
                await self._db.update_approval_request(
                    request_id,
                    status=req.status.value if hasattr(req.status, "value") else req.status,
                    reviewer=reviewer,
                    reviewed_at=req.reviewed_at,
                )
        return ok

    async def async_reject_request(
        self, request_id: str, reviewer: str, reason: str
    ) -> bool:
        ok = self.reject_request(request_id, reviewer, reason)
        if ok and self._db is not None:
            req = self._requests.get(request_id)
            if req:
                await self._db.update_approval_request(
                    request_id,
                    status=req.status.value if hasattr(req.status, "value") else req.status,
                    reviewer=reviewer,
                    reviewed_at=req.reviewed_at,
                    reason=reason,
                )
        return ok

    def set_db(self, db: Any) -> None:
        self._db = db

    async def load_from_db(self) -> int:
        if self._db is None:
            return 0
        try:
            rows = await self._db.list_approval_requests(limit=10000)
            if not rows:
                return len(self._requests)
            for row in rows:
                req = ApprovalRequest(
                    id=row.get("id", ""),
                    tenant_id=row.get("tenant_id", ""),
                    org_id=row.get("org_id", ""),
                    action=row.get("action", ""),
                    requested_by=row.get("requested_by", ""),
                    status=ApprovalStatus(row.get("status", "PENDING")),
                    reason=row.get("reason", ""),
                    reviewer=row.get("reviewer", ""),
                    reviewed_at=row.get("reviewed_at"),
                    created_at=row.get("created_at", ""),
                    metadata={},
                )
                self._requests[req.id] = req
            return len(rows)
        except Exception:
            return 0
