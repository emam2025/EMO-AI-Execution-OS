"""Phase 4.4 — ResourceEnforcer isolation tests.

Tests:
  - Pre-check rejects when quota would be exceeded
  - enforce() returns False on quota breach (kill signal)
  - finish() archives telemetry
  - Three-phase lifecycle execution

Ref: DEVELOPER.md §15.15b §4.4
Ref: Canon LAW 10 (Workers are unreliable — enforce bounds)
Ref: Canon RULE 4 (Kill on limit exceed)
"""

import pytest

from core.runtime.isolation.resource_enforcer import ResourceEnforcer
from core.runtime.resources.resource_tracker import ResourceTracker
from core.runtime.resources.quota_manager import QuotaManager, Quota, QuotaExceeded


class TestResourceEnforcerKillsOnQuota:
    """Task 2: test_resource_enforcer_kills_on_quota.py"""

    def test_pre_check_passes(self):
        """Pre-check with reasonable estimates (no quota set = unlimited)."""
        enf = ResourceEnforcer()
        enf.check_before_scheduling("exec_001", "test_tool", 1.0, 1024)
        usage = enf.tracker.get_active("exec_001")
        assert usage is not None
        assert usage.execution_id == "exec_001"

    def test_pre_check_rejects_global_cpu_exceeded(self):
        """Pre-check rejects when global CPU quota exceeded."""
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=10.0))
        enf = ResourceEnforcer(quota_manager=qm)
        with pytest.raises(QuotaExceeded):
            enf.check_before_scheduling("exec_002", "test_tool", 99.0, 1024)

    def test_enforce_returns_true_within_limits(self):
        """enforce() returns True when within limits."""
        enf = ResourceEnforcer()
        enf.check_before_scheduling("exec_003", "test_tool", 1.0, 1024)
        assert enf.enforce("exec_003", cpu=0.5, memory=512, wall_time=1.0) is True

    def test_enforce_returns_false_when_exceeded(self):
        """enforce() returns False (kill signal) when global quota exceeded."""
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=5.0))
        enf = ResourceEnforcer(quota_manager=qm)
        enf.check_before_scheduling("exec_004", "test_tool", 1.0, 1024)
        assert enf.enforce("exec_004", cpu=99.0, memory=999, wall_time=99.0) is False

    def test_finish_archives_telemetry(self):
        """finish() archives usage and returns ResourceUsage."""
        enf = ResourceEnforcer()
        enf.check_before_scheduling("exec_005", "test_tool", 1.0, 1024)
        enf.enforce("exec_005", cpu=0.3, memory=256, wall_time=0.5)
        usage = enf.finish("exec_005")
        assert usage is not None
        assert usage.execution_id == "exec_005"
        assert usage.cpu_time >= 0.3

    def test_three_phase_lifecycle(self):
        """Full three-phase lifecycle: pre-check → enforce → finish."""
        enf = ResourceEnforcer()
        enf.check_before_scheduling("exec_006", "test_tool", 2.0, 2048)
        enf.enforce("exec_006", cpu=1.0, memory=1024, wall_time=2.0)
        usage = enf.finish("exec_006")
        assert usage is not None
        assert usage.tool == "test_tool"

    def test_global_memory_rejection(self):
        """Global memory quota enforcement."""
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_memory=1000))
        enf = ResourceEnforcer(quota_manager=qm)
        with pytest.raises(QuotaExceeded):
            enf.check_before_scheduling("exec_007", "big_tool", 0, 9999)

    def test_enforce_without_pre_check(self):
        """enforce() handles case where no pre-check was done gracefully."""
        enf = ResourceEnforcer()
        result = enf.enforce("exec_unknown", cpu=0.1, memory=64, wall_time=0.1)
        assert result is True
