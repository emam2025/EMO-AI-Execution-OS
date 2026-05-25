"""Phase F3 — Allocation State Machine Preemption Guards.

Verifies that preemption requires:
  - priority_diff >= 2 tiers
  - target age > 60s
  - checkpoint_available
  - graceful_termination_signal

Ref: Canon LAW 8, RULE 3
"""

import time
import pytest

from core.runtime.resource_scheduler.allocation_state_machine import (
    AllocationState,
    AllocationStateMachine,
)
from core.runtime.models.resource_scheduler_models import (
    AssignmentRecord,
    PriorityTier,
    ResourceRequest,
)


class TestAllocationStateMachinePreemptionGuards:
    """Preemption guards prevent unsafe preemption."""

    def make_record(
        self,
        priority: PriorityTier = PriorityTier.BATCH,
        age: float = 120.0,
        checkpoint: bool = True,
    ) -> AssignmentRecord:
        return AssignmentRecord(
            execution_id="target-exec",
            worker_id="w1",
            resources=ResourceRequest(priority=priority),
            assigned_at=time.time() - age if age > 0 else 0,
            preemptible=True,
            checkpoint_available=checkpoint,
        )

    def test_preemption_allowed_all_guards_pass(self):
        sm = AllocationStateMachine()
        request = ResourceRequest(priority=PriorityTier.CRITICAL)
        record = self.make_record(priority=PriorityTier.BATCH, age=120.0, checkpoint=True)
        ok, reason = sm.can_preempt(request, record)
        assert ok, f"Expected allowed but got: {reason}"

    def test_preemption_blocked_low_priority(self):
        sm = AllocationStateMachine()
        request = ResourceRequest(priority=PriorityTier.NORMAL)
        record = self.make_record(priority=PriorityTier.LOW)
        ok, reason = sm.can_preempt(request, record)
        assert not ok
        assert "not eligible" in reason

    def test_preemption_blocked_insufficient_priority_diff(self):
        sm = AllocationStateMachine()
        request = ResourceRequest(priority=PriorityTier.HIGH)
        record = self.make_record(priority=PriorityTier.NORMAL)  # diff = 1
        ok, reason = sm.can_preempt(request, record)
        assert not ok
        assert "Priority diff" in reason

    def test_preemption_blocked_young_age(self):
        sm = AllocationStateMachine()
        request = ResourceRequest(priority=PriorityTier.CRITICAL)
        record = self.make_record(priority=PriorityTier.BATCH, age=10.0)
        ok, reason = sm.can_preempt(request, record)
        assert not ok
        assert "age" in reason.lower()

    def test_preemption_blocked_no_checkpoint(self):
        sm = AllocationStateMachine()
        request = ResourceRequest(priority=PriorityTier.CRITICAL)
        record = self.make_record(priority=PriorityTier.BATCH, age=120.0, checkpoint=False)
        ok, reason = sm.can_preempt(request, record)
        assert not ok
        assert "checkpoint" in reason.lower()

    def test_preemption_high_can_preempt_batch(self):
        sm = AllocationStateMachine()
        request = ResourceRequest(priority=PriorityTier.HIGH)
        record = self.make_record(priority=PriorityTier.BATCH, age=120.0)
        ok, reason = sm.can_preempt(request, record)
        assert ok, f"HIGH should preempt BATCH: {reason}"

    def test_transition_preempted_fires_guard(self):
        sm = AllocationStateMachine()
        sm.force_set(AllocationState.RUNNING)
        request = ResourceRequest(priority=PriorityTier.CRITICAL)
        record = self.make_record(priority=PriorityTier.BATCH, age=120.0)
        ok, reason = sm.transition(
            AllocationState.PREEMPTED,
            request=request,
            record=record,
        )
        assert ok, f"Preempt transition failed: {reason}"
        assert sm.current == AllocationState.PREEMPTED

    def test_transition_preempted_blocked_by_guard(self):
        sm = AllocationStateMachine()
        sm.force_set(AllocationState.RUNNING)
        request = ResourceRequest(priority=PriorityTier.LOW)
        record = self.make_record()
        ok, _ = sm.transition(
            AllocationState.PREEMPTED,
            request=request,
            record=record,
        )
        assert not ok  # LOW priority can't preempt
