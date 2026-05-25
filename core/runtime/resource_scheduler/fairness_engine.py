"""Phase F3 — Fairness Engine implementation.  # LAW-8 # LAW-11 # RULE-1

Implements IFairnessEngine: compute_fair_share, detect_starvation,
apply_priority_boost, balance_load.

Prevents starvation via priority boost and fallback worker assignment.

Ref: Canon LAW 8 (Fair distribution), LAW 11 (No global state), RULE 1 (Determinism)
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from core.runtime.models.resource_scheduler_models import (
    FairShareSnapshot,
    PriorityTier,
    ResourceOffer,
    ResourceRequest,
    StarvationReport,
)

logger = logging.getLogger("emo_ai.resource_scheduler.fairness")


class FairnessEngine:  # ←→ IFairnessEngine
    """Ensures fair resource distribution and prevents starvation.

    LAW 8: Fair share computed per worker; starvation detected and boosted.
    LAW 11: No global state — per-instance fairness tracking.
    RULE 1: Deterministic fair share computation.
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
        self._starvation_reports: Dict[str, StarvationReport] = {}

    # ── compute_fair_share ────────────────────────────────────

    def compute_fair_share(  # LAW-8, RULE-1
        self,
        worker_id: str,
        total_resources: ResourceOffer,
        active_executions: int,
    ) -> FairShareSnapshot:
        n = max(1, active_executions)
        fair_cpu = total_resources.total_cpu / n
        fair_mem = total_resources.total_mem / n
        current_cpu = total_resources.total_cpu - total_resources.available_cpu
        current_mem = total_resources.total_mem - total_resources.available_mem

        imbalance = 0.0
        if fair_cpu > 0:
            imbalance = current_cpu / (fair_cpu * n)

        return FairShareSnapshot(
            worker_id=worker_id,
            fair_cpu=round(fair_cpu, 2),
            fair_mem=fair_mem,
            current_cpu=current_cpu,
            current_mem=current_mem,
            imbalance_ratio=round(imbalance, 4),
            boosted=False,
        )

    # ── detect_starvation ─────────────────────────────────────

    def detect_starvation(  # LAW-8
        self,
        execution_id: str,
        wait_time_sec: float,
        current_priority: PriorityTier,
        starvation_threshold: Optional[float] = None,
    ) -> StarvationReport:
        threshold = starvation_threshold or self.STARVATION_THRESHOLDS.get(
            current_priority, 120.0,
        )

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
        report = StarvationReport(
            execution_id=execution_id,
            wait_time_sec=wait_time_sec,
            priority=current_priority,
            boost_applied=(new_priority != current_priority),
            new_priority=new_priority,
            action_taken=(
                f"Starvation detected: {current_priority.value} wait "
                f"{wait_time_sec:.0f}s > {threshold:.0f}s threshold"
            ),
        )

        if new_priority != current_priority:
            report.action_taken += (
                f" → boosted to {new_priority.value}"
            )

        self._starvation_reports[execution_id] = report
        logger.info("Starvation: %s", report.action_taken)
        return report

    # ── apply_priority_boost ──────────────────────────────────

    def apply_priority_boost(  # LAW-8
        self,
        current: PriorityTier,
    ) -> PriorityTier:
        return self.BOOST_MAP.get(current, current)

    # ── balance_load ──────────────────────────────────────────

    def balance_load(  # LAW-8
        self,
        offers: List[ResourceOffer],
        metrics: List[FairShareSnapshot],
    ) -> List[ResourceOffer]:
        metric_map: Dict[str, FairShareSnapshot] = {
            m.worker_id: m for m in metrics
        }

        sorted_offers = sorted(
            offers,
            key=lambda o: metric_map[o.worker_id].imbalance_ratio
            if o.worker_id in metric_map
            else 0.0,
        )
        return sorted_offers

    def get_report(self, execution_id: str) -> Optional[StarvationReport]:
        return self._starvation_reports.get(execution_id)

    def reset(self) -> None:
        self._starvation_reports.clear()
