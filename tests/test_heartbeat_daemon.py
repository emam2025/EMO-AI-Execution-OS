"""Tests for WorkerHeartbeatDaemon — background lease renewal."""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.heartbeat_daemon import (
    WorkerHeartbeatDaemon, HeartbeatEntry,
    DEFAULT_HEARTBEAT_INTERVAL, DEFAULT_MAX_RETRIES,
)
from core.ownership_manager import OwnershipManager, LeaseStore


# ── Helpers ─────────────────────────────────────────────────────

class FakeOwnershipManager:
    """Mock that controls renew_lease success/failure."""

    def __init__(self):
        self.leases: dict = {}
        self.fail_renew: set = set()
        self.renew_calls: list = []
        self.release_calls: list = []

    def claim(self, task_id, worker_id, **kw):
        lease_id = f"lease_{task_id}"
        self.leases[task_id] = {
            "lease_id": lease_id,
            "worker_id": worker_id,
        }
        return lease_id

    def renew_lease(self, task_id, lease_id, lease_duration=None):
        self.renew_calls.append((task_id, lease_id))
        if task_id in self.fail_renew:
            return False
        return True

    def release(self, task_id, lease_id):
        self.release_calls.append((task_id, lease_id))
        self.leases.pop(task_id, None)
        return True


# ── HeartbeatEntry ──────────────────────────────────────────────

def test_heartbeat_entry_init():
    entry = HeartbeatEntry("task_1", "lease_1", "worker_1", 60.0)
    assert entry.task_id == "task_1"
    assert entry.lease_id == "lease_1"
    assert entry.worker_id == "worker_1"
    assert entry.lease_duration == 60.0
    assert entry.failure_count == 0
    assert entry.active is True


# ── Lifecycle ───────────────────────────────────────────────────

def test_daemon_version():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om)
    assert d.version == "1.0.0"


def test_start_stop():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om, heartbeat_interval=0.1)
    assert d.is_running is False
    d.start()
    assert d.is_running is True
    d.stop(timeout=2.0)
    assert d.is_running is False


def test_start_twice_noop():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om, heartbeat_interval=0.1)
    d.start()
    assert d.is_running
    d.start()  # should not crash
    assert d.is_running
    d.stop()


# ── Register / unregister ──────────────────────────────────────

def test_register_task():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om)
    assert d.registered_count() == 0
    d.register_task("task_1", "lease_1", "worker_1", 60.0)
    assert d.registered_count() == 1
    assert "task_1" in d.registered_tasks()


def test_unregister_task():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om)
    d.register_task("task_1", "lease_1", "worker_1", 60.0)
    assert d.registered_count() == 1
    d.unregister_task("task_1")
    assert d.registered_count() == 0


def test_unregister_unknown_noop():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om)
    d.unregister_task("nonexistent")
    assert not d.is_running  # not started, still no crash


def test_get_entry():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om)
    d.register_task("task_1", "lease_1", "worker_1", 60.0)
    entry = d.get_entry("task_1")
    assert entry is not None
    assert entry.task_id == "task_1"
    assert d.get_entry("nonexistent") is None


# ── Heartbeat loop / auto-renew ─────────────────────────────────

def test_heartbeat_loop_renews_leases():
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(
        om, heartbeat_interval=0.05, max_retries=3,
    )
    d.register_task("task_1", "lease_1", "worker_1", 60.0)
    d.register_task("task_2", "lease_2", "worker_2", 60.0)
    d.start()
    time.sleep(0.3)  # let a few cycles run
    d.stop()
    assert len(om.renew_calls) >= 2  # each task renewed at least once


def test_auto_disconnect_after_max_retries():
    expired_tasks = []
    def on_expired(task_id, worker_id):
        expired_tasks.append((task_id, worker_id))

    om = FakeOwnershipManager()
    om.fail_renew.add("task_fail")
    d = WorkerHeartbeatDaemon(
        om, heartbeat_interval=0.02, max_retries=3,
        on_task_expired=on_expired,
    )
    d.register_task("task_fail", "lease_fail", "worker_1", 60.0)
    d.register_task("task_ok", "lease_ok", "worker_2", 60.0)
    d.start()
    time.sleep(0.3)
    d.stop()

    assert len(expired_tasks) == 1
    assert expired_tasks[0][0] == "task_fail"
    assert expired_tasks[0][1] == "worker_1"

    # Release should have been called for the failed task
    assert len(om.release_calls) == 1
    assert om.release_calls[0][0] == "task_fail"

    # task_ok should still be registered after stop
    # (it might or might not — depends on timing)
    # But it should never have been expired
    ok_expired = any(t[0] == "task_ok" for t in expired_tasks)
    assert ok_expired is False


def test_auto_disconnect_does_not_expire_healthy():
    expired_tasks = []
    def on_expired(task_id, worker_id):
        expired_tasks.append((task_id, worker_id))

    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(
        om, heartbeat_interval=0.02, max_retries=3,
        on_task_expired=on_expired,
    )
    d.register_task("task_ok", "lease_ok", "worker_1", 60.0)
    d.start()
    time.sleep(0.3)
    d.stop()
    assert len(expired_tasks) == 0


def test_unregister_stops_heartbeats():
    """A task that completes should stop being renewed."""
    om = FakeOwnershipManager()
    d = WorkerHeartbeatDaemon(om, heartbeat_interval=0.02)
    d.register_task("task_1", "lease_1", "worker_1", 60.0)
    d.start()
    time.sleep(0.1)
    renews_before = len(om.renew_calls)
    d.unregister_task("task_1")
    time.sleep(0.2)
    renews_after = len(om.renew_calls)
    d.stop()
    # After unregister, no more renewals for task_1
    assert renews_after == renews_before


def test_rapid_failure_chain():
    """Multiple failures should trigger expiry exactly once."""
    expired_tasks = []
    def on_expired(task_id, worker_id):
        expired_tasks.append((task_id, worker_id))

    om = FakeOwnershipManager()
    om.fail_renew.add("task_bad")
    d = WorkerHeartbeatDaemon(
        om, heartbeat_interval=0.01, max_retries=2,
        on_task_expired=on_expired,
    )
    d.register_task("task_bad", "lease_bad", "worker_1", 60.0)
    d.start()
    time.sleep(0.3)
    d.stop()
    # Should have been expired exactly once
    assert len(expired_tasks) == 1
