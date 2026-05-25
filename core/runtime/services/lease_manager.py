"""D8.1 — ExecutionLeaseManager: distributed ownership (LAW 23).

LAW 23 (complement): LeaseManager manages distributed ownership.
FORBIDDEN: retry, dispatch, state, scheduling.

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 23 (distributed ownership domain)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Dict, Optional

logger = logging.getLogger("emo_ai.services.lease_manager")


class LeaseError(Exception):
    """Raised when a lease operation encounters a system error."""


class HeartbeatError(Exception):
    """Raised when heartbeat monitoring fails."""


class ExecutionLeaseManager:
    """Distributed ownership service — owns leases, heartbeats, ownership.

    LAW 23: LeaseManager manages distributed ownership.
    Private state: _active_leases, _heartbeat_timers, _resource_owners.
    No access to scheduler, dispatcher, retry_handler, or state_store state.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 23 (distributed ownership domain)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_leases: Dict[str, Dict[str, any]] = {}
        self._heartbeat_timers: Dict[str, threading.Timer] = {}
        self._resource_owners: Dict[str, str] = {}

    def acquire_lease(
        self,
        resource_id: str,
        owner: str,
        ttl: float = 30.0,
    ) -> Optional[str]:
        """Acquire an execution lease for a distributed resource.

        LAW 23: Only LeaseManager may manage lease ownership.

        Args:
            resource_id: The resource to lease.
            owner: Identity of the requesting owner.
            ttl: Time-to-live in seconds.

        Returns:
            Lease ID if acquired, None if lease is held by another owner.

        Raises:
            LeaseError: If lease cannot be acquired due to system error.
        """
        try:
            with self._lock:
                existing_owner = self._resource_owners.get(resource_id)
                if existing_owner is not None and existing_owner != owner:
                    logger.info(
                        "Lease busy for %s: held by %s",
                        resource_id, existing_owner,
                    )
                    return None

                lease_id = uuid.uuid4().hex[:12]
                expires_at = time.time() + ttl
                self._active_leases[lease_id] = {
                    "resource_id": resource_id,
                    "owner": owner,
                    "ttl": ttl,
                    "acquired_at": time.time(),
                    "expires_at": expires_at,
                }
                self._resource_owners[resource_id] = owner
                logger.debug(
                    "Lease %s acquired for %s by %s (ttl=%.1f)",
                    lease_id, resource_id, owner, ttl,
                )
                return lease_id
        except Exception as e:
            raise LeaseError(
                f"Cannot acquire lease for {resource_id}: {e}"
            ) from e

    def renew_lease(
        self,
        lease_id: str,
        ttl: float = 30.0,
    ) -> bool:
        """Renew an existing lease to prevent expiry.

        Args:
            lease_id: The lease identifier to renew.
            ttl: New time-to-live in seconds.

        Returns:
            True if renewed, False if lease has expired or is invalid.

        Raises:
            LeaseError: If lease renewal encounters system error.
        """
        try:
            with self._lock:
                lease = self._active_leases.get(lease_id)
                if lease is None:
                    logger.warning("Lease %s not found for renewal", lease_id)
                    return False

                if time.time() > lease["expires_at"]:
                    logger.warning("Lease %s already expired", lease_id)
                    self._release_lease_internal(lease_id)
                    return False

                lease["expires_at"] = time.time() + ttl
                logger.debug("Lease %s renewed (ttl=%.1f)", lease_id, ttl)
                return True
        except Exception as e:
            raise LeaseError(
                f"Cannot renew lease {lease_id}: {e}"
            ) from e

    def release_lease(
        self,
        lease_id: str,
    ) -> bool:
        """Release a lease, making the resource available.

        Args:
            lease_id: The lease identifier to release.

        Returns:
            True if released, False if lease was not found.

        Raises:
            LeaseError: If lease release encounters system error.
        """
        try:
            with self._lock:
                return self._release_lease_internal(lease_id)
        except Exception as e:
            raise LeaseError(
                f"Cannot release lease {lease_id}: {e}"
            ) from e

    def monitor_heartbeat(
        self,
        lease_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """Monitor heartbeat for a leased resource.

        Args:
            lease_id: The lease identifier to monitor.
            timeout: Maximum time to wait for heartbeat.

        Returns:
            True if heartbeat received within timeout, False otherwise.

        Raises:
            HeartbeatError: If heartbeat monitoring fails.
        """
        try:
            with self._lock:
                lease = self._active_leases.get(lease_id)
                if lease is None:
                    return False

                if time.time() > lease["expires_at"]:
                    logger.warning("Heartbeat expired for lease %s", lease_id)
                    self._release_lease_internal(lease_id)
                    return False

                return True
        except Exception as e:
            raise HeartbeatError(
                f"Cannot monitor heartbeat for lease {lease_id}: {e}"
            ) from e

    def _release_lease_internal(self, lease_id: str) -> bool:
        """Internal lease release (lock must be held)."""
        lease = self._active_leases.pop(lease_id, None)
        if lease is None:
            return False
        resource_id = lease["resource_id"]
        current_owner = self._resource_owners.get(resource_id)
        if current_owner == lease["owner"]:
            del self._resource_owners[resource_id]
        timer = self._heartbeat_timers.pop(lease_id, None)
        if timer is not None:
            timer.cancel()
        logger.debug("Lease %s released for %s", lease_id, resource_id)
        return True
