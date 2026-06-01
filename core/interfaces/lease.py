"""D8.1 — IExecutionLeaseManager: distributed ownership only.

LAW 23 (complement): LeaseManager manages distributed ownership.
FORBIDDEN: retry, dispatch, state, scheduling.

Source of Truth: core/runtime/services/lease_manager.py::ExecutionLeaseManager

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 23 (distributed ownership domain)
"""

from typing import Optional, Protocol, runtime_checkable


class LeaseError(Exception):
    """Raised when a lease operation encounters a system error."""


class HeartbeatError(Exception):
    """Raised when heartbeat monitoring fails."""


@runtime_checkable
class IExecutionLeaseManager(Protocol):
    """Owns distributed ownership — nothing else.

    Contract methods:
      acquire_lease(resource_id, owner, ttl?)  → Optional[str]
      renew_lease(lease_id, ttl?)  → bool
      release_lease(lease_id)  → bool
      monitor_heartbeat(lease_id, timeout?)  → bool
    """

    def acquire_lease(
        self,
        resource_id: str,
        owner: str,
        ttl: float = 30.0,
    ) -> Optional[str]:
        """Acquire an execution lease for a distributed resource."""

    def renew_lease(
        self,
        lease_id: str,
        ttl: float = 30.0,
    ) -> bool:
        """Renew an existing lease to prevent expiry."""

    def release_lease(
        self,
        lease_id: str,
    ) -> bool:
        """Release a lease, making the resource available."""

    def monitor_heartbeat(
        self,
        lease_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """Monitor heartbeat for a leased resource."""
