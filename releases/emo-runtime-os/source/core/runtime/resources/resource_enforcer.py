"""Phase 4.4.3 — ResourceEnforcer: kill execution if exceeded, pre-check before scheduling.

The enforcement layer that ties ResourceTracker and QuotaManager
into the execution pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.runtime.resources.resource_tracker import ResourceTracker
from core.runtime.resources.quota_manager import QuotaManager, QuotaExceeded

logger = logging.getLogger("emo_ai.resources.enforcer")


class ResourceEnforcer:
    """Enforces resource limits before and during execution.

    Responsibilities:
      - Pre-check before scheduling (can this execution proceed?)
      - Kill execution if resource limits exceeded mid-flight
      - Telemetry collection via ResourceTracker
    """

    def __init__(
        self,
        tracker: Optional[ResourceTracker] = None,
        quota_manager: Optional[QuotaManager] = None,
    ):
        self._tracker = tracker or ResourceTracker()
        self._quota_manager = quota_manager or QuotaManager()

    @property
    def tracker(self) -> ResourceTracker:
        return self._tracker

    @property
    def quota_manager(self) -> QuotaManager:
        return self._quota_manager

    def check_before_scheduling(
        self,
        execution_id: str,
        tool: str,
        estimated_cpu: float = 0,
        estimated_memory: int = 0,
    ) -> None:
        """Pre-check if execution can proceed.

        Raises QuotaExceeded if global or worker quotas would be exceeded.
        """
        self._quota_manager.check(
            f"execution:{execution_id}",
            cpu=estimated_cpu,
            memory=estimated_memory,
        )
        self._tracker.start_execution(execution_id, tool)
        logger.debug("Pre-check passed for %s (%s)", execution_id, tool)

    def enforce(
        self,
        execution_id: str,
        cpu: float = 0,
        memory: int = 0,
        wall_time: float = 0,
    ) -> bool:
        """Enforce resource limits during execution.

        Returns True if execution should continue, False if it should
        be killed.
        """
        try:
            self._tracker.update(
                execution_id,
                cpu_time=cpu,
                memory_bytes=memory,
            )
            self._quota_manager.check(
                f"execution:{execution_id}",
                cpu=cpu,
                memory=memory,
                wall_time=wall_time,
            )
            return True
        except QuotaExceeded as e:
            logger.warning("Enforcement kill for %s: %s", execution_id, e)
            return False

    def finish(self, execution_id: str) -> None:
        """Finalize resource tracking for an execution."""
        usage = self._tracker.complete_execution(execution_id)
        if usage:
            self._quota_manager.record_usage(
                f"execution:{execution_id}",
                cpu=usage.cpu_time,
                memory=usage.memory_bytes,
                wall_time=usage.wall_time,
                io_bytes=usage.io_bytes,
            )
            logger.debug(
                "Finished %s: cpu=%.2fs memory=%d bytes wall=%.2fs",
                execution_id, usage.cpu_time, usage.memory_bytes, usage.wall_time,
            )
