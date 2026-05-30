"""Tests for Ownership Manager — distributed execution authority."""
import sys, os, time, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.ownership_manager import (
    OwnershipManager, LeaseStore, OWNERSHIP_VERSION,
    LEASE_DEFAULT_DURATION, LEASE_HEARTBEAT_INTERVAL,
)
from core.distributed_types import TaskAssignment, TaskStatus


# ═══════════════════════════════════════════════════════════════════
# LeaseStore tests
# ═══════════════════════════════════════════════════════════════════

def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "ownership.db"


def test_store_insert_and_get():
    store = LeaseStore(db_path=_db())
    ok = store.insert("t1", "lease1", "w1", "exec1", 0, time.time() + 60)
    assert ok is True
    row = store.get("t1")
    assert row is not None
    assert row["task_id"] == "t1"
    assert row["worker_id"] == "w1"
    assert row["status"] == "active"


def test_store_insert_duplicate_fails():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "lease1", "w1", "exec1", 0, time.time() + 60)
    ok = store.insert("t1", "lease2", "w2", "exec2", 1, time.time() + 60)
    assert ok is False


def test_store_get_nonexistent():
    store = LeaseStore(db_path=_db())
    assert store.get("nonexistent") is None


def test_store_update_heartbeat():
    store = LeaseStore(db_path=_db())
    deadline = time.time() + 60
    store.insert("t1", "lease1", "w1", "exec1", 0, deadline)
    new_deadline = time.time() + 120
    ok = store.update_heartbeat("t1", "lease1", new_deadline)
    assert ok is True
    row = store.get("t1")
    assert abs(row["leased_until"] - new_deadline) < 1.0


def test_store_update_heartbeat_wrong_lease_id():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "lease1", "w1", "exec1", 0, time.time() + 60)
    ok = store.update_heartbeat("t1", "wrong_lease", time.time() + 120)
    assert ok is False


def test_store_release():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "lease1", "w1", "exec1", 0, time.time() + 60)
    ok = store.release("t1", "lease1")
    assert ok is True
    row = store.get("t1")
    assert row["status"] == "released"


def test_store_release_wrong_lease_id():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "lease1", "w1", "exec1", 0, time.time() + 60)
    ok = store.release("t1", "wrong_lease")
    assert ok is False


def test_store_find_expired():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "l1", "w1", "e1", 0, time.time() - 10)  # expired
    store.insert("t2", "l2", "w2", "e2", 0, time.time() + 60)  # valid
    expired = store.find_expired()
    task_ids = {e["task_id"] for e in expired}
    assert "t1" in task_ids
    assert "t2" not in task_ids


def test_store_expire():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "l1", "w1", "e1", 0, time.time() + 60)
    ok = store.expire("t1")
    assert ok is True
    row = store.get("t1")
    assert row["status"] == "expired"


def test_store_owner_of():
    store = LeaseStore(db_path=_db())
    assert store.owner_of("nonexistent") is None
    store.insert("t1", "l1", "w1", "e1", 0, time.time() + 60)
    assert store.owner_of("t1") == "w1"


def test_store_owner_of_expired_lease():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "l1", "w1", "e1", 0, time.time() - 10)
    assert store.owner_of("t1") is None


def test_store_execution_attempt():
    store = LeaseStore(db_path=_db())
    assert store.execution_attempt("nonexistent") == ("", 0)
    store.insert("t1", "l1", "w1", "exec_id_1", 2, time.time() + 60)
    eid, attempt = store.execution_attempt("t1")
    assert eid == "exec_id_1"
    assert attempt == 2


def test_store_clear():
    store = LeaseStore(db_path=_db())
    store.insert("t1", "l1", "w1", "e1", 0, time.time() + 60)
    store.clear()
    assert store.lease_count() == 0


def test_store_counts():
    store = LeaseStore(db_path=_db())
    assert store.lease_count() == 0
    assert store.active_count() == 0
    store.insert("t1", "l1", "w1", "e1", 0, time.time() + 60)
    assert store.lease_count() == 1
    assert store.active_count() == 1


# ═══════════════════════════════════════════════════════════════════
# OwnershipManager tests
# ═══════════════════════════════════════════════════════════════════

def test_ownership_version():
    assert OWNERSHIP_VERSION == "1.0.0"


def test_claim_success():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    lease_id = mgr.claim("t1", "w1")
    assert lease_id is not None
    assert mgr.owner_of("t1") == "w1"


def test_claim_returns_none_if_already_owned():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    mgr.claim("t1", "w1")
    lease_id = mgr.claim("t1", "w2")
    assert lease_id is None
    assert mgr.owner_of("t1") == "w1"


def test_claim_reclaims_expired_lease():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    # Manually create a lease that is already expired
    store = mgr._store
    store.insert("t1", "expired_lease", "w1", "exec1", 0, time.time() - 10)
    # Now claim it — should succeed because the existing lease is expired
    lease_id = mgr.claim("t1", "w2")
    assert lease_id is not None
    assert mgr.owner_of("t1") == "w2"


def test_renew_lease():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    lease_id = mgr.claim("t1", "w1", lease_duration=10.0)
    assert mgr.renew_lease("t1", lease_id, lease_duration=20.0) is True


def test_renew_lease_fails_for_wrong_lease():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    mgr.claim("t1", "w1")
    assert mgr.renew_lease("t1", "wrong_lease") is False


def test_renew_lease_fails_for_expired_lease():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    lease_id = mgr.claim("t1", "w1", lease_duration=0.01)
    time.sleep(0.02)
    assert mgr.renew_lease("t1", lease_id) is False


def test_release():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    lease_id = mgr.claim("t1", "w1")
    assert mgr.release("t1", lease_id) is True
    assert mgr.owner_of("t1") is None


def test_release_fails_for_wrong_lease():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    mgr.claim("t1", "w1")
    assert mgr.release("t1", "wrong_lease") is False


def test_reassign_expired():
    mgr = OwnershipManager(
        lease_store=LeaseStore(db_path=_db()),
        default_lease_duration=0.01,
    )
    mgr.claim("t1", "w1")
    mgr.claim("t2", "w2", lease_duration=60.0)  # still valid
    time.sleep(0.02)
    reassigned = mgr.reassign_expired()
    assert "t1" in reassigned
    assert "t2" not in reassigned


def test_owner_of_nonexistent():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    assert mgr.owner_of("nonexistent") is None


def test_execution_attempt():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    mgr.claim("t1", "w1", execution_id="exec_abc", attempt_number=1)
    eid, attempt = mgr.execution_attempt("t1")
    assert eid == "exec_abc"
    assert attempt == 1


def test_execution_attempt_nonexistent():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    assert mgr.execution_attempt("nonexistent") == ("", 0)


def test_active_count():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    assert mgr.active_count() == 0
    mgr.claim("t1", "w1")
    assert mgr.active_count() == 1
    mgr.claim("t2", "w2")
    assert mgr.active_count() == 2


def test_lease_count():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    mgr.claim("t1", "w1")
    mgr.claim("t2", "w2")
    assert mgr.lease_count() == 2


def test_version_property():
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    assert mgr.version == "1.0.0"


def test_reclaim_after_release():
    """After release, a different worker can claim."""
    mgr = OwnershipManager(lease_store=LeaseStore(db_path=_db()))
    l1 = mgr.claim("t1", "w1")
    mgr.release("t1", l1)
    l2 = mgr.claim("t1", "w2")
    assert l2 is not None
    assert mgr.owner_of("t1") == "w2"
