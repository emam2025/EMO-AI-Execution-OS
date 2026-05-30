"""Phase F3 — Resource Scheduler & Quota Arbitration: Comprehensive tests.

Groups:
  G1 — TestQuotaEnforcement          (6 tests) — quota checks, limits, refund, cooldown
  G2 — TestFairnessEngine            (6 tests) — fair share, starvation, load balance
  G3 — TestTopologyMapping           (5 tests) — mapping, affinity, constraints, fallback
  G4 — TestAllocationSM              (5 tests) — transitions, terminal states, preemption
  G5 — TestResourceScheduler         (6 tests) — match, assign, preempt, release, queue
  G6 — TestCanonCompliance           (3 tests) — LAW/RULE comments, imports

Total: ~31 tests

Ref: DEVELOPER.md §15.9
Ref: Canon LAW 5, LAW 8, LAW 10, LAW 11, RULE 1-5
Ref: EXEC-DIRECTIVE-005
"""

import time
from unittest.mock import MagicMock

import pytest

from core.runtime.resource_scheduler.resource_scheduler import ResourceScheduler
from core.runtime.resource_scheduler.quota_arbitrator import QuotaArbitrator
from core.runtime.resource_scheduler.fairness_engine import FairnessEngine
from core.runtime.resource_scheduler.topology_mapper import TopologyMapper
from core.runtime.resource_scheduler.allocation_state_machine import (
    AllocationState,
    AllocationStateMachine,
)
from core.runtime.resource_scheduler.starvation_handler import StarvationHandler
from core.runtime.models.resource_scheduler_models import (
    AssignmentRecord,
    FairShareSnapshot,
    HardwareCapability,
    PriorityTier,
    QuotaPolicy,
    QuotaType,
    ResourceOffer,
    ResourceRequest,
    SchedulingDecision,
    SchedulingStatus,
    StarvationReport,
    TopologyMapping,
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def req(**kwargs) -> ResourceRequest:
    defaults = dict(execution_id="e1", cpu_cores=2.0, memory_mb=1024, priority=PriorityTier.NORMAL)
    defaults.update(kwargs)
    return ResourceRequest(**defaults)


def offer(worker_id: str = "w1", cpu: float = 8.0, mem: int = 16384,
          caps=None, tags=None) -> ResourceOffer:
    return ResourceOffer(
        worker_id=worker_id,
        available_cpu=cpu,
        available_mem=mem,
        total_cpu=cpu,
        total_mem=mem,
        hardware_topology=caps or [HardwareCapability.CPU_INTENSIVE],
        affinity_tags=tags or [],
    )


def policy(**kwargs) -> QuotaPolicy:
    defaults = dict(type=QuotaType.EXECUTION, limit=100.0, soft_limit=80.0, hard_limit=100.0)
    defaults.update(kwargs)
    return QuotaPolicy(**defaults)


def decision(**kwargs) -> SchedulingDecision:
    defaults = dict(status=SchedulingStatus.ASSIGNED, assigned_worker="w1")
    defaults.update(kwargs)
    return SchedulingDecision(**defaults)


# ════════════════════════════════════════════════════════════════════
# G1 — TestQuotaEnforcement (6 tests)
# ════════════════════════════════════════════════════════════════════


class TestQuotaEnforcement:
    """LAW 10: Resource limits enforced at execution/worker/global levels."""

    def test_check_quota_allows_within_limits(self):
        qa = QuotaArbitrator()
        assert qa.check_quota("e1", req(cpu_cores=2.0, memory_mb=512), policy(hard_limit=1000.0))

    def test_check_quota_rejects_exceeding_hard_limit(self):
        qa = QuotaArbitrator()
        qa.consume_usage("e1", req(cpu_cores=95.0))
        # 95 + 10 = 105 > 100 hard_limit
        assert not qa.check_quota("e1", req(cpu_cores=10.0), policy(hard_limit=100.0))

    def test_enforce_limit_rejects_hard_limit(self):
        qa = QuotaArbitrator()
        usage = qa.consume_usage("e2", req(cpu_cores=90.0))
        ok = qa.enforce_limit("e2", usage, policy(limit=100.0, hard_limit=90.0))
        assert not ok

    def test_enforce_limit_warns_on_soft_limit(self):
        qa = QuotaArbitrator()
        usage = qa.consume_usage("e3", req(cpu_cores=85.0))
        ok = qa.enforce_limit("e3", usage, policy(limit=100.0, soft_limit=80.0, hard_limit=100.0))
        assert ok  # soft limit warns but does not reject

    def test_refund_on_failure_clears_usage(self):
        qa = QuotaArbitrator()
        qa.consume_usage("e4", req())
        assert "e4" in qa.active_usage
        qa.refund_on_failure("e4", qa.active_usage["e4"])
        assert "e4" not in qa.active_usage

    def test_cooldown_blocks_quota_check(self):
        qa = QuotaArbitrator()
        usage = qa.consume_usage("e5", req(cpu_cores=99.0))
        # trigger cooldown by hitting hard limit
        qa.enforce_limit("e5", usage, policy(limit=100.0, hard_limit=80.0, cooldown_sec=60.0))
        assert qa._cooldowns.get("e5", 0) > 0
        assert not qa.check_quota("e5", req(cpu_cores=1.0), policy())


# ════════════════════════════════════════════════════════════════════
# G2 — TestFairnessEngine (6 tests)
# ════════════════════════════════════════════════════════════════════


class TestFairnessEngine:
    """LAW 8: Fair distribution — starvation detected and boosted."""

    def test_detect_starvation_boosts_low_to_normal(self):
        fe = FairnessEngine()
        r = fe.detect_starvation("e1", 9999, PriorityTier.LOW)
        assert r.boost_applied
        assert r.new_priority == PriorityTier.NORMAL

    def test_detect_starvation_boosts_batch_to_low(self):
        fe = FairnessEngine()
        r = fe.detect_starvation("e2", 9999, PriorityTier.BATCH)
        assert r.boost_applied
        assert r.new_priority == PriorityTier.LOW

    def test_detect_starvation_boosts_normal_to_high(self):
        fe = FairnessEngine()
        r = fe.detect_starvation("e3", 9999, PriorityTier.NORMAL)
        assert r.boost_applied
        assert r.new_priority == PriorityTier.HIGH

    def test_no_boost_within_threshold(self):
        fe = FairnessEngine()
        r = fe.detect_starvation("e4", 10.0, PriorityTier.NORMAL, starvation_threshold=60.0)
        assert not r.boost_applied
        assert r.action_taken == "within threshold"

    def test_compute_fair_share_single_execution(self):
        fe = FairnessEngine()
        o = offer(cpu=8.0, mem=16384)
        snap = fe.compute_fair_share("w1", o, 1)
        assert snap.fair_cpu == 8.0
        assert snap.fair_mem == 16384
        assert snap.worker_id == "w1"

    def test_balance_load_sorts_by_imbalance(self):
        fe = FairnessEngine()
        o1 = offer("w1", cpu=8.0)
        o2 = offer("w2", cpu=8.0)
        m1 = FairShareSnapshot(worker_id="w1", imbalance_ratio=0.5)
        m2 = FairShareSnapshot(worker_id="w2", imbalance_ratio=0.1)
        sorted_offers = fe.balance_load([o1, o2], [m2, m1])
        assert sorted_offers[0].worker_id == "w2"  # lower imbalance first


# ════════════════════════════════════════════════════════════════════
# G3 — TestTopologyMapping (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestTopologyMapping:
    """LAW 10: Topology-aware resource matching."""

    def test_map_to_hardware_selects_best_match(self):
        tm = TopologyMapper()
        r = req(gpu_memory_mb=4096)
        o = [
            offer("w1", caps=[HardwareCapability.CPU_INTENSIVE]),
            offer("w2", caps=[HardwareCapability.GPU_AVAILABLE]),
        ]
        mapping = tm.map_to_hardware(r, o)
        assert mapping.worker_id == "w2"

    def test_map_to_hardware_filters_insufficient_cpu(self):
        tm = TopologyMapper()
        r = req(cpu_cores=16.0)
        o = [offer("w1", cpu=8.0)]
        mapping = tm.map_to_hardware(r, o)
        assert not mapping.worker_id  # empty string = no match
        assert mapping.fallback_suggested

    def test_check_affinity_matches_tag(self):
        tm = TopologyMapper()
        r = req(execution_id="e1")
        o = offer(tags=["e1"])
        assert tm.check_affinity(r, o)

    def test_check_affinity_no_match(self):
        tm = TopologyMapper()
        r = req(execution_id="e1")
        o = offer(tags=["other"])
        assert not tm.check_affinity(r, o)

    def test_suggest_fallback_finds_alternative(self):
        tm = TopologyMapper()
        r = req(cpu_cores=4.0, memory_mb=2048)
        o = [offer("w1", cpu=2.0), offer("w2", cpu=8.0, mem=4096)]
        fallback = tm.suggest_fallback(r, o)
        assert fallback is not None
        assert fallback.worker_id == "w2"


# ════════════════════════════════════════════════════════════════════
# G4 — TestAllocationSM (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestAllocationSM:
    """RULE 4: Allocation transitions with guards."""

    def test_transition_queued_to_matched(self):
        sm = AllocationStateMachine()
        ok, _ = sm.transition(AllocationState.MATCHED)
        assert ok
        assert sm.current == AllocationState.MATCHED

    def test_transition_matched_to_reserved_with_offer(self):
        sm = AllocationStateMachine()
        sm.transition(AllocationState.MATCHED)
        ok, _ = sm.transition(AllocationState.RESERVED, offer_available=True)
        assert ok
        assert sm.current == AllocationState.RESERVED

    def test_transition_matched_to_reserved_blocked_no_offer(self):
        sm = AllocationStateMachine()
        sm.transition(AllocationState.MATCHED)
        ok, reason = sm.transition(AllocationState.RESERVED, offer_available=False)
        assert not ok
        assert "No matching offer" in reason

    def test_terminal_state_blocks_transitions(self):
        sm = AllocationStateMachine()
        sm.force_set(AllocationState.COMPLETED)
        ok, reason = sm.transition(AllocationState.MATCHED)
        assert not ok
        assert "Invalid transition" in reason or "Terminal state" in reason

    def test_preempted_requeues_correctly(self):
        sm = AllocationStateMachine()
        sm.force_set(AllocationState.PREEMPTED)
        ok, _ = sm.transition(AllocationState.QUEUED, preempted=True)
        assert ok
        assert sm.current == AllocationState.QUEUED


# ════════════════════════════════════════════════════════════════════
# G5 — TestResourceScheduler (6 tests)
# ════════════════════════════════════════════════════════════════════


class TestResourceSchedulerIntegration:
    """End-to-end resource scheduling with all subsystems."""

    def test_match_resources_success(self):
        rs = ResourceScheduler()
        r = req()
        o = [offer()]
        decision = rs.match_resources(r, o)
        assert decision.status == SchedulingStatus.ASSIGNED
        assert decision.assigned_worker == "w1"

    def test_match_resources_queued_when_no_match(self):
        rs = ResourceScheduler()
        r = req(cpu_cores=999.0)  # exceeds all offers
        o = [offer(cpu=8.0)]
        decision = rs.match_resources(r, o)
        assert decision.status == SchedulingStatus.QUEUED
        assert "queued" in decision.reason

    def test_assign_worker_adds_assignment(self):
        rs = ResourceScheduler()
        d = decision(assigned_worker="w1")
        ok = rs.assign_worker(d, offer())
        assert ok
        assert "w1" in rs.active_assignments

    def test_assign_worker_idempotent(self):
        rs = ResourceScheduler()
        d = decision(assigned_worker="w1")
        rs.assign_worker(d, offer())
        ok = rs.assign_worker(d, offer())  # second call
        assert ok  # idempotent — returns True

    def test_release_resources_removes_assignment(self):
        rs = ResourceScheduler()
        d = decision(assigned_worker="w1")
        rs.assign_worker(d, offer())
        ok = rs.release_resources("w1", d)
        assert ok
        assert "w1" not in rs.active_assignments

    def test_preemption_enqueues_preempted_request(self):
        rs = ResourceScheduler()
        d = decision(assigned_worker="w1")
        rs.assign_worker(d, offer())
        # preempt with HIGH priority request (diff >= 2 from BATCH)
        high_req = req(execution_id="e2", priority=PriorityTier.HIGH, cpu_cores=2.0)
        # set assignment record resources to BATCH priority for preemption
        rs._assignments["w1"].resources = req(priority=PriorityTier.BATCH)
        rs._assignments["w1"].assigned_at = time.time() - 120  # old enough
        result = rs.preempt_if_needed(high_req, [])
        assert result is not None
        assert result.status == SchedulingStatus.PREEMPTED


# ════════════════════════════════════════════════════════════════════
# G6 — TestCanonCompliance (3 tests)
# ════════════════════════════════════════════════════════════════════


class TestCanonCompliance:
    """LAW/RULE comment annotations and import hygiene."""

    def test_models_have_law_annotations(self):
        import inspect
        import core.runtime.models.resource_scheduler_models as m
        source = inspect.getsource(m)
        assert "# LAW-5" in source or "# LAW-8" in source
        assert "# LAW-10" in source

    def test_each_submodule_has_law_annotations(self):
        modules = [
            "core.runtime.resource_scheduler.resource_scheduler",
            "core.runtime.resource_scheduler.quota_arbitrator",
            "core.runtime.resource_scheduler.fairness_engine",
            "core.runtime.resource_scheduler.topology_mapper",
            "core.runtime.resource_scheduler.allocation_state_machine",
            "core.runtime.resource_scheduler.starvation_handler",
        ]
        for mod_name in modules:
            import importlib
            mod = importlib.import_module(mod_name)
            import inspect
            source = inspect.getsource(mod)
            assert "# LAW" in source, f"{mod_name} missing LAW annotation"
            assert "# RULE" in source, f"{mod_name} missing RULE annotation"

    def test_composition_root_exposes_resource_scheduler(self):
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        rs = root.resource_scheduler
        assert hasattr(rs, "match_resources")
        assert hasattr(rs, "assign_worker")
        assert hasattr(rs, "preempt_if_needed")
        assert hasattr(rs, "release_resources")
        assert hasattr(rs, "quota")
        assert hasattr(rs, "fairness")
        assert hasattr(rs, "topology")
