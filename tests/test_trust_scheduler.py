"""Tests for Trust-Aware Scheduling.

6 tests covering worker registration, trust hierarchy, policy enforcement,
trust level upgrades, and audit trail.

Ref: Phase E.4 — Trust-Aware Scheduling
"""

import asyncio

import pytest

from core.models.event import EventTopic
from core.models.trust import TrustPolicy, WorkerTrustLevel
from core.runtime.trust_scheduler import TrustScheduler


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


# --- Tests ---


def test_register_worker_with_trust_level():
    """E.4.1: Worker registration stores trust level."""
    scheduler = TrustScheduler()

    scheduler.register_worker("worker-1", WorkerTrustLevel.TRUSTED)
    scheduler.register_worker("worker-2", WorkerTrustLevel.VERIFIED)
    scheduler.register_worker("worker-3", WorkerTrustLevel.UNVERIFIED)

    assert scheduler.get_worker_trust("worker-1") == WorkerTrustLevel.TRUSTED
    assert scheduler.get_worker_trust("worker-2") == WorkerTrustLevel.VERIFIED
    assert scheduler.get_worker_trust("worker-3") == WorkerTrustLevel.UNVERIFIED
    assert scheduler.get_worker_trust("unknown") is None

    workers = scheduler.list_workers()
    assert len(workers) == 3
    assert workers["worker-1"] == WorkerTrustLevel.TRUSTED


def test_trusted_worker_can_execute_critical_task():
    """E.4.1: TRUSTED worker is allowed to execute critical tasks."""
    scheduler = TrustScheduler()
    scheduler.register_worker("worker-1", WorkerTrustLevel.TRUSTED)
    scheduler.register_policy(
        "line_shutdown",
        TrustPolicy(task_type="line_shutdown", min_trust_level=WorkerTrustLevel.TRUSTED),
    )

    result = scheduler.schedule_task("line_shutdown", "worker-1")
    assert result is True

    log = scheduler.get_audit_log()
    assert len(log) == 1
    assert log[0]["decision"] == "allowed"
    assert log[0]["worker_id"] == "worker-1"


def test_unverified_worker_blocked_from_critical_task():
    """E.4.1: UNVERIFIED worker is blocked from critical tasks."""
    scheduler = TrustScheduler()
    scheduler.register_worker("worker-3", WorkerTrustLevel.UNVERIFIED)
    scheduler.register_policy(
        "line_shutdown",
        TrustPolicy(task_type="line_shutdown", min_trust_level=WorkerTrustLevel.TRUSTED),
    )

    result = scheduler.schedule_task("line_shutdown", "worker-3")
    assert result is False

    log = scheduler.get_audit_log()
    assert len(log) == 1
    assert log[0]["decision"] == "denied"
    assert "trust_level_insufficient" in log[0]["reason"]


def test_policy_enforcement():
    """E.4.1: Different task types enforce different trust policies."""
    scheduler = TrustScheduler()
    scheduler.register_worker("worker-1", WorkerTrustLevel.TRUSTED)
    scheduler.register_worker("worker-2", WorkerTrustLevel.VERIFIED)
    scheduler.register_worker("worker-3", WorkerTrustLevel.UNVERIFIED)

    scheduler.register_policy(
        "critical_ops",
        TrustPolicy(task_type="critical_ops", min_trust_level=WorkerTrustLevel.TRUSTED),
    )
    scheduler.register_policy(
        "read_ops",
        TrustPolicy(task_type="read_ops", min_trust_level=WorkerTrustLevel.UNVERIFIED),
    )

    assert scheduler.schedule_task("critical_ops", "worker-1") is True
    assert scheduler.schedule_task("critical_ops", "worker-2") is False
    assert scheduler.schedule_task("critical_ops", "worker-3") is False

    assert scheduler.schedule_task("read_ops", "worker-1") is True
    assert scheduler.schedule_task("read_ops", "worker-2") is True
    assert scheduler.schedule_task("read_ops", "worker-3") is True


def test_trust_level_upgrade():
    """E.4.1: Worker upgraded from UNVERIFIED to TRUSTED gains critical access."""
    scheduler = TrustScheduler()
    scheduler.register_worker("worker-1", WorkerTrustLevel.UNVERIFIED)
    scheduler.register_policy(
        "line_shutdown",
        TrustPolicy(task_type="line_shutdown", min_trust_level=WorkerTrustLevel.TRUSTED),
    )

    assert scheduler.schedule_task("line_shutdown", "worker-1") is False

    scheduler.register_worker("worker-1", WorkerTrustLevel.TRUSTED)
    assert scheduler.schedule_task("line_shutdown", "worker-1") is True

    log = scheduler.get_audit_log()
    denied = [e for e in log if e["decision"] == "denied"]
    allowed = [e for e in log if e["decision"] == "allowed"]
    assert len(denied) == 1
    assert len(allowed) == 1


def test_unregistered_worker_denied():
    """E.4.1: Unregistered workers are rejected (Default Deny)."""
    scheduler = TrustScheduler()

    result = scheduler.schedule_task("any_task", "unknown_worker")
    assert result is False

    log = scheduler.get_audit_log()
    assert len(log) == 1
    assert log[0]["decision"] == "denied"
    assert "unregistered_worker" in log[0]["reason"]


@pytest.mark.asyncio
async def test_scheduling_decision_publishes_audit_event():
    """E.4.1: Scheduling decision publishes SECURITY_VIOLATION audit event."""
    event_bus = MockEventBus()
    scheduler = TrustScheduler(event_bus=event_bus)
    scheduler.register_worker("worker-1", WorkerTrustLevel.TRUSTED)
    scheduler.register_policy(
        "line_shutdown",
        TrustPolicy(task_type="line_shutdown", min_trust_level=WorkerTrustLevel.TRUSTED),
    )

    scheduler.schedule_task("line_shutdown", "worker-1")
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.SECURITY_VIOLATION
    assert published["event"].payload["worker_id"] == "worker-1"
    assert published["event"].payload["task_type"] == "line_shutdown"
    assert published["event"].payload["decision"] == "allowed"
