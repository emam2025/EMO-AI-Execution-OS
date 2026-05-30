"""Phase 4.4 — Isolation ResourceEnforcer.

Isolation-specific resource enforcement that wraps the base
ResourceEnforcer with explicit RLIMIT pre-checks and failure
propagation per the design execution flow.

Three-phase lifecycle:
  1. check_before_scheduling() — pre-execution quota validation.
  2. enforce() — mid-flight resource limit check.
  3. finish() — telemetry archiving + quota release.

Ref: DEVELOPER.md §15.15b §4.4
Ref: Canon LAW 10 (Workers are unreliable — must enforce bounds)
"""

from __future__ import annotations

import logging
from typing import Optional

from core.runtime.resources.resource_enforcer import (
    ResourceEnforcer as BaseResourceEnforcer,
)
from core.runtime.resources.quota_manager import QuotaManager, QuotaExceeded
from core.runtime.resources.resource_tracker import ResourceTracker, ResourceUsage

logger = logging.getLogger("emo_ai.isolation.resource_enforcer")


class ResourceLimitExceeded(Exception):
    """Raised when execution exceeds resource limits mid-flight.

    Ref: DEVELOPER.md §15.15b §4.4 — IResourceEnforcer
    Ref: Canon RULE 4 (Kill on limit exceed)
    """

    def __init__(self, execution_id: str, reason: str):
        self.execution_id = execution_id
        self.reason = reason
        super().__init__(f"Resource limit exceeded [{execution_id}]: {reason}")


class ResourceEnforcer:
    """Isolation-layer resource enforcer with three-phase lifecycle.

    Wraps BaseResourceEnforcer and adds isolation-specific logging,
    explicit failure propagation, and canon compliance.

    Ref: DEVELOPER.md §15.15b §4.4
    Ref: Canon LAW 10 (Workers are unreliable — enforce bounds)
    Ref: Canon RULE 4 (Everything is Killable)
    """

    def __init__(
        self,
        tracker: Optional[ResourceTracker] = None,
        quota_manager: Optional[QuotaManager] = None,
        base_enforcer: Optional[BaseResourceEnforcer] = None,
    ):
        self._base = base_enforcer or BaseResourceEnforcer(
            tracker=tracker or ResourceTracker(),
            quota_manager=quota_manager or QuotaManager(),
        )

    @property
    def tracker(self) -> ResourceTracker:
        return self._base.tracker

    @property
    def quota_manager(self) -> QuotaManager:
        return self._base.quota_manager

    def check_before_scheduling(
        self,
        execution_id: str,
        tool: str,
        estimated_cpu: float = 0.0,
        estimated_memory: int = 0,
    ) -> None:
        """Pre-check if execution can proceed.

        LAW 10: Validate bounds before scheduling.
        Raises QuotaExceeded if global or worker quotas would be exceeded.

        Args:
            execution_id: Unique execution identifier.
            tool: Tool name.
            estimated_cpu: Estimated CPU seconds required.
            estimated_memory: Estimated memory bytes required.

        Raises:
            QuotaExceeded: If quotas would be exceeded.
        """
        # LAW 10: Pre-check before scheduling — execution MUST NOT proceed
        # if quotas would be exceeded.
        try:
            self._base.check_before_scheduling(
                execution_id=execution_id,
                tool=tool,
                estimated_cpu=estimated_cpu,
                estimated_memory=estimated_memory,
            )
            logger.debug(
                "Pre-check passed for %s/%s: cpu=%.1f mem=%d",
                tool, execution_id, estimated_cpu, estimated_memory,
            )
        except QuotaExceeded:
            logger.warning(
                "Pre-check FAILED for %s/%s: quota exceeded",
                tool, execution_id,
            )
            raise

    def enforce(
        self,
        execution_id: str,
        cpu: float = 0.0,
        memory: int = 0,
        wall_time: float = 0.0,
    ) -> bool:
        """Enforce resource limits during execution.

        RULE 4: Kill execution if resource limits are exceeded mid-flight.

        Args:
            execution_id: Unique execution identifier.
            cpu: Current CPU seconds consumed.
            memory: Current memory bytes consumed.
            wall_time: Current wall-clock time in seconds.

        Returns:
            True if execution should continue, False if should be killed.
        """
        should_continue = self._base.enforce(
            execution_id=execution_id,
            cpu=cpu,
            memory=memory,
            wall_time=wall_time,
        )
        if not should_continue:
            logger.warning(
                "Enforcement kill for %s: cpu=%.1f mem=%d wall=%.1f",
                execution_id, cpu, memory, wall_time,
            )
        return should_continue

    def finish(self, execution_id: str) -> Optional[ResourceUsage]:
        """Finalize resource tracking and archive telemetry.

        LAW 10: All resource usage MUST be tracked and archived.

        Args:
            execution_id: Unique execution identifier to finalize.

        Returns:
            ResourceUsage record if tracking was active, None otherwise.
        """
        self._base.finish(execution_id=execution_id)
        usage = self._base.tracker.get_usage(execution_id)
        if usage:
            logger.debug(
                "Finished %s: cpu=%.2fs mem=%d wall=%.2f io=%d",
                execution_id, usage.cpu_time, usage.memory_bytes,
                usage.wall_time, usage.io_bytes,
            )
        return usage
