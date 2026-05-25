"""D8.1 — IExecutionLeaseManager: distributed ownership only.

OWNERSHIP: distributed ownership
  - lease acquire / release
  - heartbeat ownership
  - lease expiration detection
  - worker assignment tracking

FORBIDDEN:
  - execution logic
  - retry decisions
  - state storage
  - scheduling
"""

from typing import Optional, Protocol


class IExecutionLeaseManager(Protocol):
    """Owns distributed ownership — nothing else."""

    def acquire(self, node_id: str, worker_id: str, ttl: float) -> bool:
        """Try to acquire a lease for a node. Return True if acquired."""

    def release(self, node_id: str, worker_id: str) -> bool:
        """Release a lease. Return True if released."""

    def heartbeat(self, node_id: str, worker_id: str) -> bool:
        """Renew a lease. Return True if still valid."""

    def is_expired(self, node_id: str) -> bool:
        """Check if a lease has expired."""

    def owner(self, node_id: str) -> Optional[str]:
        """Return the current owner of a node's lease."""

    def release_all(self, worker_id: str) -> int:
        """Release all leases held by a worker. Return count released."""
