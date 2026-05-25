"""Phase F3 — Starvation Prevention: Priority Boost & Fallback.

Verifies that queued low-priority tasks receive priority boost
after exceeding threshold, and fallback worker on repeated starvation.

Ref: Canon LAW 8, RULE 3
"""

import time
import pytest

from core.runtime.resource_scheduler.starvation_handler import StarvationHandler
from core.runtime.models.resource_scheduler_models import (
    PriorityTier,
    ResourceOffer,
    ResourceRequest,
)


class TestStarvationPreventionBoostsLowPriorityTask:
    """Starvation handler detects and resolves starvation."""

    def make_request(self, priority: PriorityTier = PriorityTier.LOW) -> ResourceRequest:
        return ResourceRequest(
            execution_id="exec-1",
            dag_id="dag-1",
            cpu_cores=2.0,
            memory_mb=1024,
            priority=priority,
        )

    def make_offer(self, cpu: float = 4.0, mem: int = 2048) -> ResourceOffer:
        return ResourceOffer(
            worker_id="w1",
            available_cpu=cpu,
            available_mem=mem,
            total_cpu=8.0,
            total_mem=4096,
        )

    def test_batch_task_boosted_after_threshold(self):
        sh = StarvationHandler()
        report = sh.detect_starvation("e1", 9999, PriorityTier.BATCH)
        assert report.boost_applied
        assert report.new_priority == PriorityTier.LOW

    def test_low_task_boosted_after_threshold(self):
        sh = StarvationHandler()
        report = sh.detect_starvation("e2", 9999, PriorityTier.LOW)
        assert report.boost_applied
        assert report.new_priority == PriorityTier.NORMAL

    def test_normal_task_boosted_after_threshold(self):
        sh = StarvationHandler()
        report = sh.detect_starvation("e3", 9999, PriorityTier.NORMAL)
        assert report.boost_applied
        assert report.new_priority == PriorityTier.HIGH

    def test_high_task_not_boosted(self):
        sh = StarvationHandler()
        report = sh.detect_starvation("e4", 9999, PriorityTier.HIGH)
        assert not report.boost_applied  # already high
        assert report.new_priority == PriorityTier.HIGH

    def test_critical_task_not_boosted(self):
        sh = StarvationHandler()
        report = sh.detect_starvation("e5", 9999, PriorityTier.CRITICAL)
        assert not report.boost_applied

    def test_within_threshold_no_starvation(self):
        sh = StarvationHandler()
        report = sh.detect_starvation("e6", 1.0, PriorityTier.LOW)
        assert not report.boost_applied
        assert report.action_taken == "within threshold"

    def test_enqueue_and_dequeue_roundtrip(self):
        sh = StarvationHandler()
        req = self.make_request()
        sh.enqueue(req)
        assert len(sh.queued_requests) == 1
        popped = sh.dequeue("exec-1")
        assert popped is not None
        assert popped.execution_id == "exec-1"
        assert len(sh.queued_requests) == 0

    def test_fallback_worker_on_repeated_starvation(self):
        sh = StarvationHandler()
        request = self.make_request()
        offers = [self.make_offer(cpu=1.0, mem=512)]

        # Trigger first starvation manually (bypass clock dependency)
        r1 = sh.detect_starvation("exec-1", 9999, PriorityTier.LOW)
        assert r1.boost_applied

        # Simulate second starvation event
        sh._boost_count["exec-1"] = 2
        fallback = sh.find_fallback("exec-1", request, offers)
        assert fallback is not None
        assert fallback.worker_id == "w1"

        # After fallback assigned, second call returns None
        fallback2 = sh.find_fallback("exec-1", request, offers)
        assert fallback2 is None

    def test_reset_clears_all_state(self):
        sh = StarvationHandler()
        sh.enqueue(self.make_request())
        sh.detect_starvation("e1", 9999, PriorityTier.LOW)
        assert len(sh.queued_requests) > 0
        sh.reset()
        assert len(sh.queued_requests) == 0
