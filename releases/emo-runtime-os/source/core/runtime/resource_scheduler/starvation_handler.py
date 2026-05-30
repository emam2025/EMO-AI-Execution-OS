"""Phase F3 — Starvation Prevention Handler.  # LAW-8 # RULE-3

Monitors queued requests, detects starvation based on wait time
thresholds, applies priority boosts, and falls back to alternative
workers when repeated starvation occurs.

Ref: Canon LAW 8 (Fairness), RULE 3 (Recoverability)
Ref: artifacts/design/f3/03_allocation_and_fairness_machine.md §3
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

from core.runtime.models.resource_scheduler_models import (
    PriorityTier,
    ResourceOffer,
    ResourceRequest,
    StarvationReport,
)

logger = logging.getLogger("emo_ai.resource_scheduler.starvation")


class StarvationHandler:  # §3 — Starvation Detection & Recovery
    """Detects and resolves starvation of queued resource requests.

    LAW 8: Starvation detected via wait time thresholds per priority.
    RULE 3: Fallback worker assigned when boost not sufficient.
    """

    BOOST_MAP = {
        PriorityTier.BATCH: PriorityTier.LOW,
        PriorityTier.LOW: PriorityTier.NORMAL,
        PriorityTier.NORMAL: PriorityTier.HIGH,
        PriorityTier.HIGH: PriorityTier.HIGH,
        PriorityTier.CRITICAL: PriorityTier.CRITICAL,
    }

    STARVATION_THRESHOLDS = {
        PriorityTier.BATCH: 300.0,
        PriorityTier.LOW: 120.0,
        PriorityTier.NORMAL: 60.0,
        PriorityTier.HIGH: 30.0,
        PriorityTier.CRITICAL: 10.0,
    }

    def __init__(self) -> None:
        self._queued: Dict[str, Tuple[ResourceRequest, float]] = {}
        self._boost_count: Dict[str, int] = {}
        self._fallback_assigned: Dict[str, bool] = {}
        self._reports: List[StarvationReport] = []

    @property
    def queued_requests(self) -> List[ResourceRequest]:
        return [r for r, _ in self._queued.values()]

    def enqueue(self, request: ResourceRequest) -> None:
        self._queued[request.execution_id] = (request, time.time())

    def dequeue(self, execution_id: str) -> Optional[ResourceRequest]:
        entry = self._queued.pop(execution_id, None)
        return entry[0] if entry else None

    # ── Starvation Detection ──────────────────────────────────

    def detect_starvation(  # LAW-8
        self,
        execution_id: str,
        wait_time_sec: float,
        current_priority: PriorityTier,
    ) -> StarvationReport:
        threshold = self.STARVATION_THRESHOLDS.get(current_priority, 120.0)

        if wait_time_sec <= threshold:
            return StarvationReport(
                execution_id=execution_id,
                wait_time_sec=wait_time_sec,
                priority=current_priority,
                boost_applied=False,
                new_priority=current_priority,
                action_taken="within threshold",
            )

        new_priority = self.apply_priority_boost(current_priority)
        boost_applied = new_priority != current_priority

        report = StarvationReport(
            execution_id=execution_id,
            wait_time_sec=wait_time_sec,
            priority=current_priority,
            boost_applied=boost_applied,
            new_priority=new_priority,
            action_taken=(
                f"Starvation: {current_priority.value} wait "
                f"{wait_time_sec:.0f}s"
            ),
        )

        if boost_applied:
            self._boost_count[execution_id] = self._boost_count.get(execution_id, 0) + 1
            report.action_taken += f" → boosted to {new_priority.value}"

        self._reports.append(report)
        logger.info("Starvation report: %s", report.action_taken)
        return report

    # ── Priority Boost ────────────────────────────────────────

    def apply_priority_boost(  # LAW-8
        self,
        current: PriorityTier,
    ) -> PriorityTier:
        return self.BOOST_MAP.get(current, current)

    # ── Fallback Worker ───────────────────────────────────────

    def find_fallback(  # RULE-3
        self,
        execution_id: str,
        request: ResourceRequest,
        offers: List[ResourceOffer],
    ) -> Optional[ResourceOffer]:
        if self._fallback_assigned.get(execution_id, False):
            return None

        for offer in offers:
            if offer.available_cpu >= request.cpu_cores * 0.5:
                if offer.available_mem >= request.memory_mb * 0.5:
                    self._fallback_assigned[execution_id] = True
                    return offer
        return None

    # ── Scan all queued for starvation ────────────────────────

    def scan_queued(  # LAW-8
        self,
        offers: List[ResourceOffer],
    ) -> List[Tuple[ResourceRequest, StarvationReport, Optional[ResourceOffer]]]:
        results: List[Tuple[ResourceRequest, StarvationReport, Optional[ResourceOffer]]] = []
        now = time.time()

        to_remove: List[str] = []
        for execution_id, (request, enqueued_at) in self._queued.items():
            wait_time = now - enqueued_at
            report = self.detect_starvation(execution_id, wait_time, request.priority)

            if report.boost_applied:
                request.priority = report.new_priority

            fallback: Optional[ResourceOffer] = None
            if report.boost_applied and self._boost_count.get(execution_id, 0) > 1:
                fallback = self.find_fallback(execution_id, request, offers)

            results.append((request, report, fallback))

        return results

    def reset(self) -> None:
        self._queued.clear()
        self._boost_count.clear()
        self._fallback_assigned.clear()
        self._reports.clear()
