#!/usr/bin/env python3
"""
AUDIT-CLOSURE-C2-002 — Ownership & Lease Validation (Phase C — Execution Truth Audit)

Tasks:
  1. Lease Acquisition & Validation
  2. Heartbeat Renewal & Timeout Simulation
  3. Lease Expiration & Reassignment Logic
  4. Duplicate Execution Prevention (concurrent)
  5. Quantitative Report Generation

Rules:
  - NO core/ or tests/ modification
  - Use actual OwnershipManager / LeaseStore (no mocking)
  - RAW evidence saved verbatim
  - STOP on ImportError, silent lease override, or unhandled exception
"""

import json
import os
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path setup ────────────────────────────────────────────────────
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── Core imports (read-only) ──────────────────────────────────────
from core.ownership_manager import LeaseStore, OwnershipManager

# ── Constants ─────────────────────────────────────────────────────
ARTIFACT_DIR = Path("artifacts/audit/C2")
TASK_ID = "AUDIT-CLOSURE-C2-002"
TS_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
STORE_DB = ARTIFACT_DIR / "c2_lease_test.db"


def ts() -> str:
    return datetime.now(timezone.utc).strftime(TS_FMT)


def now() -> float:
    return time.time()


class EvidenceLogger:
    def __init__(self):
        self._buf: list[str] = []

    def write(self, line: str = ""):
        self._buf.append(line)
        print(line)

    def write_block(self, header: str, data: Any):
        self.write(f"\n─── {header} ───")
        if isinstance(data, str):
            for ln in data.split("\n"):
                self.write(f"  {ln}")
        elif isinstance(data, (dict, list)):
            for ln in json.dumps(data, indent=2).split("\n"):
                self.write(f"  {ln}")
        else:
            self.write(f"  {data}")

    def dump(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self._buf) + "\n")

    def dump_raw(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


E = EvidenceLogger()
STOP_REASON: Optional[str] = None


def stop_if(condition: bool, phase: str, cause: str, action: str):
    """Check stop-condition; sets STOP_REASON if triggered."""
    global STOP_REASON
    if condition and STOP_REASON is None:
        STOP_REASON = (
            f"STOP-REPORT | {TASK_ID} | {phase} | {cause} | {action}"
        )
        E.write(f"\n  ❌ STOP CONDITION TRIGGERED: {STOP_REASON}")


# ── Helpers ───────────────────────────────────────────────────────

def make_store(clean: bool = True) -> LeaseStore:
    if clean and STORE_DB.exists():
        STORE_DB.unlink()
    return LeaseStore(db_path=STORE_DB)


def lease_info(om: OwnershipManager, task_id: str) -> Optional[Dict[str, Any]]:
    """Return raw lease info for a task_id."""
    store = om._store
    return store.get(task_id)


# ═══════════════════════════════════════════════════════════════════
# TASK 1: Lease Acquisition & Validation
# ═══════════════════════════════════════════════════════════════════
def task1_lease_acquisition() -> Dict[str, Any]:
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 1: LEASE ACQUISITION & VALIDATION")
    E.write(f"{'=' * 70}")

    raw_lines: List[str] = []
    store = make_store(clean=True)
    om = OwnershipManager(lease_store=store, default_lease_duration=60.0)
    results: Dict[str, Any] = {}

    # ── 1a. Acquire lease on exec-001 ─────────────────────────────
    E.write(f"\n[1a] acquire_lease(execution_id='exec-001', worker_id='w1', ttl=5.0)")
    t_before = now()
    lease_id = om.claim(task_id="exec-001", worker_id="w1",
                        lease_duration=5.0, execution_id="exec-001")
    t_after = now()
    raw_lines.append(f"[{ts()}] CLAIM exec-001 w1 ttl=5.0 → lease_id={lease_id}")

    if lease_id is None:
        stop_if(True, "T1-1a", "claim returned None on first attempt",
                "LeaseManager.claim() must return lease_id on success")
        return {"status": "FAIL", "raw": raw_lines}

    info = lease_info(om, "exec-001")
    E.write(f"  lease_id          = {lease_id}")
    E.write(f"  expires_at        = {info['leased_until'] if info else 'N/A'}")
    E.write(f"  status            = {info['status'] if info else 'N/A'}")
    E.write(f"  worker_id         = {info['worker_id'] if info else 'N/A'}")

    assert lease_id is not None, "Lease ID must not be None"
    assert info is not None, "Lease info must exist"
    assert info["status"] == "active", f"Expected active, got {info['status']}"
    assert info["worker_id"] == "w1", f"Expected w1, got {info['worker_id']}"
    assert info["leased_until"] > t_before, "expires_at must be in the future"
    E.write(f"  ✅ Lease acquired: {lease_id} (valid until {info['leased_until']:.1f})")
    results["lease_id_1"] = lease_id

    # ── 1b. Owner_of verification ─────────────────────────────────
    owner = om.owner_of("exec-001")
    E.write(f"\n[1b] owner_of('exec-001') = {owner}")
    raw_lines.append(f"[{ts()}] OWNER_OF exec-001 → {owner}")
    assert owner == "w1", f"Expected w1, got {owner}"
    E.write(f"  ✅ Owner verified: w1")

    # ── 1c. Duplicate acquire → rejection ─────────────────────────
    E.write(f"\n[1c] acquire_lease(execution_id='exec-001', worker_id='w2', ttl=5.0) — DUPLICATE")
    lease_id_dup = om.claim(task_id="exec-001", worker_id="w2",
                            lease_duration=5.0, execution_id="exec-001")
    raw_lines.append(f"[{ts()}] CLAIM exec-001 w2 ttl=5.0 (duplicate) → {lease_id_dup}")

    if lease_id_dup is not None:
        stop_if(True, "T1-1c", "duplicate acquire succeeded",
                "LeaseManager must reject concurrent claim on same task_id")
        E.write(f"  ❌ STOP: Duplicate acquire returned {lease_id_dup} (expected None)")
    else:
        E.write(f"  ✅ Duplicate rejected (expected None)")

    results["duplicate_rejected"] = lease_id_dup is None
    results["raw"] = raw_lines

    # Verify original lease still intact
    info2 = lease_info(om, "exec-001")
    assert info2["worker_id"] == "w1", f"Original owner changed: {info2['worker_id']}"
    assert info2["status"] == "active", f"Original lease corrupted: {info2['status']}"
    E.write(f"  ✅ Original lease preserved: {info2['worker_id']} / {info2['status']}")

    results["lease_acquisitions_tested"] = 2
    results["duplicate_rejections"] = 1
    results["execution_attempt"] = om.execution_attempt("exec-001")
    return results


# ═══════════════════════════════════════════════════════════════════
# TASK 2: Heartbeat Renewal & Timeout Simulation
# ═══════════════════════════════════════════════════════════════════
def task2_heartbeat_renewal(prev_state: Dict[str, Any]) -> Dict[str, Any]:
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 2: HEARTBEAT RENEWAL & TIMEOUT SIMULATION")
    E.write(f"{'=' * 70}")

    raw_lines: List[str] = []
    lease_id = prev_state["lease_id_1"]

    # Lease is still active from T1 with TTL=5.0, ~1s elapsed
    # Use same store to keep state
    store = make_store(clean=False)
    om = OwnershipManager(lease_store=store, default_lease_duration=60.0)

    # ── 2a. Renew at ~2s ──────────────────────────────────────────
    E.write(f"\n[2a] renew_lease('exec-001', lease_id) at t≈2s")
    time.sleep(1.0)  # total ~1s from T1

    info_before = lease_info(om, "exec-001")
    old_deadline = info_before["leased_until"]

    ok = om.renew_lease("exec-001", lease_id, lease_duration=5.0)
    raw_lines.append(f"[{ts()}] RENEW exec-001 {lease_id[:12]}... ttl=5.0 → {ok}")

    info_after = lease_info(om, "exec-001")
    new_deadline = info_after["leased_until"]

    assert ok, "First renew must succeed"
    assert new_deadline > old_deadline, f"Deadline did not extend: {old_deadline} → {new_deadline}"
    E.write(f"  deadline: {old_deadline:.1f} → {new_deadline:.1f} (extended)")
    E.write(f"  ✅ Renewal #1 success")

    # ── 2b. Renew at ~4s ──────────────────────────────────────────
    E.write(f"\n[2b] renew_lease('exec-001', lease_id) at t≈4s")
    time.sleep(1.5)  # total ~2.5s from T1

    info_before2 = lease_info(om, "exec-001")
    old_deadline2 = info_before2["leased_until"]

    ok2 = om.renew_lease("exec-001", lease_id, lease_duration=5.0)
    raw_lines.append(f"[{ts()}] RENEW exec-001 {lease_id[:12]}... ttl=5.0 → {ok2}")

    info_after2 = lease_info(om, "exec-001")
    new_deadline2 = info_after2["leased_until"]

    assert ok2, "Second renew must succeed"
    assert new_deadline2 > old_deadline2, f"Deadline did not extend"
    E.write(f"  deadline: {old_deadline2:.1f} → {new_deadline2:.1f} (extended)")
    E.write(f"  ✅ Renewal #2 success")

    # ── 2c. Simulate missed heartbeat → expiry ────────────────────
    E.write(f"\n[2c] Miss heartbeat → wait for expiry")
    # Sleep past the 5s TTL (we're at ~2.5s, need ~4s more to exceed 6.5s from last renew)
    # Last renew set deadline to now+5. Sleep for 6s to definitely pass it.
    time.sleep(6.0)

    info_expired = lease_info(om, "exec-001")
    is_active = info_expired and info_expired["status"] == "active"
    deadline_passed = info_expired and info_expired["leased_until"] <= now()

    raw_lines.append(f"[{ts()}] CHECK_EXPIRED exec-001 → status={info_expired['status'] if info_expired else 'N/A'}, "
                     f"deadline_passed={deadline_passed}")

    E.write(f"  status:       {info_expired['status'] if info_expired else 'N/A'}")
    E.write(f"  deadline:     {info_expired['leased_until'] if info_expired else 'N/A'}")
    E.write(f"  now:          {now():.1f}")
    E.write(f"  passed:       {deadline_passed}")

    # Lease should still be 'active' in DB but past deadline
    # The DB row doesn't auto-expire; lease_manager.reassign_expired() finds it
    owner_after_expiry = om.owner_of("exec-001")
    E.write(f"  owner_of:     {owner_after_expiry} (should be None — deadline passed)")

    # owner_of checks time.time() >= leased_until and returns None
    stop_if(owner_after_expiry is not None, "T2-2c",
            "owner_of returned owner despite expired deadline",
            "OwnerOf must return None when deadline has passed")
    assert owner_after_expiry is None, f"Lease should be expired, owner={owner_after_expiry}"
    E.write(f"  ✅ Expiry detected: owner_of = None")

    results = {
        "heartbeats_renewed": 2,
        "expirations_detected": 1,
        "raw": raw_lines,
    }
    return results


# ═══════════════════════════════════════════════════════════════════
# TASK 3: Lease Expiration & Reassignment Logic
# ═══════════════════════════════════════════════════════════════════
def task3_reassignment() -> Dict[str, Any]:
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 3: LEASE EXPIRATION & REASSIGNMENT")
    E.write(f"{'=' * 70}")

    raw_lines: List[str] = []
    store = make_store(clean=True)
    om = OwnershipManager(lease_store=store, default_lease_duration=60.0)

    # ── 3a. Acquire exec-002 with short TTL ───────────────────────
    E.write(f"\n[3a] acquire_lease('exec-002', worker_id='w2', ttl=0.5)")
    lease_id_w2 = om.claim(task_id="exec-002", worker_id="w2",
                           lease_duration=0.5, execution_id="exec-002")
    raw_lines.append(f"[{ts()}] CLAIM exec-002 w2 ttl=0.5 → {lease_id_w2}")

    assert lease_id_w2 is not None, "First claim of exec-002 must succeed"
    E.write(f"  ✅ w2 acquired lease {lease_id_w2}")

    owner = om.owner_of("exec-002")
    assert owner == "w2", f"Expected w2, got {owner}"
    E.write(f"  owner_of('exec-002') = {owner}")

    # ── 3b. Wait for expiry ───────────────────────────────────────
    E.write(f"\n[3b] Wait for lease to expire (TTL=0.5s)")
    time.sleep(1.0)

    owner_expired = om.owner_of("exec-002")
    raw_lines.append(f"[{ts()}] OWNER_OF exec-002 after sleep → {owner_expired}")
    E.write(f"  owner_of after expiry: {owner_expired}")

    # ── 3c. Reassign expired ──────────────────────────────────────
    E.write(f"\n[3c] reassign_expired()")
    expired_tasks = om.reassign_expired()
    raw_lines.append(f"[{ts()}] REASSIGN_EXPIRED → {expired_tasks}")

    E.write(f"  expired tasks: {expired_tasks}")
    assert "exec-002" in expired_tasks, f"exec-002 should be in expired list"
    E.write(f"  ✅ Lease expired in store")

    info_after_expire = lease_info(om, "exec-002")
    raw_lines.append(f"[{ts()}] STATUS exec-002 after expire → {info_after_expire['status'] if info_after_expire else 'N/A'}")
    E.write(f"  status after expire: {info_after_expire['status'] if info_after_expire else 'N/A'}")
    assert info_after_expire["status"] == "expired", \
        f"Expected expired, got {info_after_expire['status']}"

    # ── 3d. Reassign to w3 ────────────────────────────────────────
    E.write(f"\n[3d] acquire_lease('exec-002', worker_id='w3', ttl=5.0) — reassign")
    lease_id_w3 = om.claim(task_id="exec-002", worker_id="w3",
                           lease_duration=5.0, execution_id="exec-002")
    raw_lines.append(f"[{ts()}] CLAIM exec-002 w3 ttl=5.0 → {lease_id_w3}")

    assert lease_id_w3 is not None, "Reassignment must succeed"
    owner_w3 = om.owner_of("exec-002")
    assert owner_w3 == "w3", f"Expected w3, got {owner_w3}"
    E.write(f"  ✅ Ownership transferred: w2 → w3 (lease={lease_id_w3})")
    E.write(f"  owner_of now: {owner_w3}")

    # ── 3e. Verify no dual active leases ───────────────────────────
    info_final = lease_info(om, "exec-002")
    E.write(f"  final status: {info_final['status']}, worker: {info_final['worker_id']}")
    assert info_final["status"] == "active", f"Expected active, got {info_final['status']}"
    assert info_final["worker_id"] == "w3", f"Expected w3, got {info_final['worker_id']}"

    # Check no other active lease on exec-002
    all_leases = store.find_expired()  # This returns active past-deadline; our lease is still active
    active_check = store.active_count()
    E.write(f"  active leases count: {active_check}")
    assert active_check == 1, f"Expected 1 active lease, got {active_check}"
    E.write(f"  ✅ No dual active leases")

    raw_lines.append(f"[{ts()}] FINAL exec-002 → status={info_final['status']}, owner={info_final['worker_id']}")

    results = {
        "reassignments_successful": 1,
        "old_owner": "w2",
        "new_owner": "w3",
        "lease_id_w2": lease_id_w2,
        "lease_id_w3": lease_id_w3,
        "raw": raw_lines,
    }
    return results


# ═══════════════════════════════════════════════════════════════════
# TASK 4: Duplicate Execution Prevention (Concurrent)
# ═══════════════════════════════════════════════════════════════════
def task4_concurrent_prevention() -> Dict[str, Any]:
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 4: CONCURRENT DUPLICATE PREVENTION")
    E.write(f"{'=' * 70}")

    raw_lines: List[str] = []
    store = make_store(clean=True)
    om = OwnershipManager(lease_store=store, default_lease_duration=60.0)

    results: Dict[str, Any] = {
        "concurrent_conflicts_caught": 0,
        "race_conditions_detected": False,
    }

    # ── 4a. Two threads racing on same task_id ────────────────────
    E.write(f"\n[4a] Two threads claim exec-003 simultaneously")

    winner: List[Optional[str]] = [None, None]  # lease_id per thread
    error_lines: List[str] = []
    barrier = threading.Barrier(2, timeout=5)

    def claimer(thread_id: int, worker_id: str):
        try:
            barrier.wait()
            lid = om.claim(task_id="exec-003", worker_id=worker_id,
                           lease_duration=10.0, execution_id="exec-003")
            winner[thread_id] = lid
            raw_lines.append(f"[{ts()}] THREAD-{thread_id} ({worker_id}) → lease_id={lid}")
            E.write(f"  Thread-{thread_id} ({worker_id}): claim → {lid}")
        except Exception as ex:
            error_lines.append(f"[{ts()}] THREAD-{thread_id} error: {ex}")
            raw_lines.append(f"[{ts()}] THREAD-{thread_id} error: {ex}")

    t1 = threading.Thread(target=claimer, args=(0, "w4"), name="claimer-0")
    t2 = threading.Thread(target=claimer, args=(1, "w5"), name="claimer-1")

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    if error_lines:
        E.write(f"\n  Thread errors:")
        for el in error_lines:
            E.write(f"    {el}")

    # Count results
    success_count = sum(1 for w in winner if w is not None)
    conflict_count = sum(1 for w in winner if w is None)

    E.write(f"\n  Successful claims:  {success_count}")
    E.write(f"  Conflicts (None):   {conflict_count}")

    if success_count == 1 and conflict_count == 1:
        E.write(f"  ✅ Exactly 1 winner, 1 conflict — no split-brain")
        results["concurrent_conflicts_caught"] = 1
        results["race_conditions_detected"] = False
    elif success_count > 1:
        stop_if(True, "T4-4a", f"dual lease granted ({success_count} winners)",
                "Concurrent claim must not grant more than 1 lease")
        results["race_conditions_detected"] = True
        results["concurrent_conflicts_caught"] = 0
    else:
        E.write(f"  ⚠️  0 winners (both got None) — unexpected, not a race condition")
        results["concurrent_conflicts_caught"] = 0
        results["race_conditions_detected"] = False

    # ── 4b. Verify only 1 active lease in store ──────────────────
    active = store.active_count()
    total = store.lease_count()
    E.write(f"\n  Active leases: {active}, Total: {total}")
    if active > 1:
        stop_if(True, "T4-4b", f"{active} active leases on same task_id",
                "LeaseStore must enforce exactly 1 active lease")
        results["race_conditions_detected"] = True

    assert active <= 1, f"Dual lease violation: {active} active leases"

    # ── 4c. Verify winner identity ────────────────────────────────
    actual_owner = om.owner_of("exec-003")
    E.write(f"  Actual owner: {actual_owner}")
    if success_count == 1:
        winner_idx = 0 if winner[0] is not None else 1
        expected_worker = f"w{4 + winner_idx}"
        E.write(f"  Expected:    {expected_worker}")
        assert actual_owner == expected_worker, \
            f"owner mismatch: {actual_owner} != {expected_worker}"
        E.write(f"  ✅ Winner correctly recorded in store")
    else:
        E.write(f"  ⚠️  Cannot verify winner identity (no winner)")

    results["raw"] = raw_lines
    return results


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    global STOP_REASON
    E.write(f"{'=' * 70}")
    E.write(f"  {TASK_ID}")
    E.write(f"  Ownership & Lease Validation (Phase C — Execution Truth Audit)")
    E.write(f"  Started: {ts()}")
    E.write(f"{'=' * 70}")

    # Track all raw evidence
    all_raw: Dict[str, List[str]] = {}

    try:
        # ── Task 1 ──────────────────────────────────────────────
        t1 = task1_lease_acquisition()
        all_raw["raw_lease_traces"] = t1.pop("raw", [])  # type: ignore[assignment]
        t1_metrics = {
            "lease_acquisitions_tested": t1.get("lease_acquisitions_tested", 2),
            "duplicate_rejections": t1.get("duplicate_rejections", 0),
        }

        # ── Task 2 ──────────────────────────────────────────────
        t2 = task2_heartbeat_renewal(t1)
        all_raw["heartbeat_renewal_log"] = t2.pop("raw", [])
        t2_metrics = {
            "heartbeats_renewed": t2.get("heartbeats_renewed", 0),
            "expirations_detected": t2.get("expirations_detected", 0),
        }

        # ── Task 3 ──────────────────────────────────────────────
        t3 = task3_reassignment()
        all_raw["reassignment_trace"] = t3.pop("raw", [])
        t3_metrics = {
            "reassignments_successful": t3.get("reassignments_successful", 0),
        }

        # ── Task 4 ──────────────────────────────────────────────
        t4 = task4_concurrent_prevention()
        all_raw["concurrent_lease_test"] = t4.pop("raw", [])
        t4_metrics = {
            "concurrent_conflicts_caught": t4.get("concurrent_conflicts_caught", 0),
            "race_conditions_detected": t4.get("race_conditions_detected", True),
        }

    except Exception as exc:
        E.write(f"\n  ❌ Unhandled exception: {type(exc).__name__}: {exc}")
        if STOP_REASON is None:
            STOP_REASON = (
                f"STOP-REPORT | {TASK_ID} | RUNTIME | {type(exc).__name__}: {exc} | Investigate"
            )
        t1_metrics = {}
        t2_metrics = {}
        t3_metrics = {}
        t4_metrics = {
            "concurrent_conflicts_caught": 0,
            "race_conditions_detected": True,
        }

    # ── Determine overall status ─────────────────────────────────
    all_metrics = {**t1_metrics, **t2_metrics, **t3_metrics, **t4_metrics}

    acceptance = {
        "duplicate_rejections >= 1": all_metrics.get("duplicate_rejections", 0) >= 1,
        "heartbeats_renewed >= 2": all_metrics.get("heartbeats_renewed", 0) >= 2,
        "expirations_detected >= 1": all_metrics.get("expirations_detected", 0) >= 1,
        "reassignments_successful >= 1": all_metrics.get("reassignments_successful", 0) >= 1,
        "concurrent_conflicts_caught >= 1": all_metrics.get("concurrent_conflicts_caught", 0) >= 1,
        "race_conditions_detected = false": not all_metrics.get("race_conditions_detected", True),
    }

    all_pass = all(acceptance.values()) and STOP_REASON is None
    status = "PASS" if all_pass else ("PARTIAL" if not any(
        not v for v in acceptance.values()) else "FAIL")
    # Override FAIL if stop condition triggered
    if STOP_REASON is not None:
        status = "FAIL"

    # ── Gaps ─────────────────────────────────────────────────────
    gaps = []
    if not acceptance.get("race_conditions_detected = false", False):
        gaps.append("Race condition detected: dual active leases granted under concurrent claim")
    if not acceptance.get("concurrent_conflicts_caught >= 1", False):
        gaps.append("Concurrent claim failed to produce a winner-loser outcome")
    gaps.append(
        "OwnershipManager.claim() returns None on conflict, not an exception — "
        "callers must check return value (no LeaseConflictError exists)"
    )
    gaps.append(
        "LeaseStore does not emit REASSIGNED events — events exist in "
        "distributed_replay.py LeaseEvent but are not wired into OwnershipManager"
    )
    gaps.append(
        "Time simulation uses real sleep with short TTLs — time.time() is not patchable "
        "without mocking stdlib"
    )
    gaps.append(
        "IExecutionLeaseManager Protocol uses acquire()→bool while OwnershipManager.claim()→Optional[str] — "
        "interface mismatch exists"
    )

    # ── Build report ─────────────────────────────────────────────
    report = {
        "task_id": TASK_ID,
        "status": status,
        "metrics": {
            "lease_acquisitions_tested": all_metrics.get("lease_acquisitions_tested", 0),
            "duplicate_rejections": all_metrics.get("duplicate_rejections", 0),
            "heartbeats_renewed": all_metrics.get("heartbeats_renewed", 0),
            "expirations_detected": all_metrics.get("expirations_detected", 0),
            "reassignments_successful": all_metrics.get("reassignments_successful", 0),
            "concurrent_conflicts_caught": all_metrics.get("concurrent_conflicts_caught", 0),
            "race_conditions_detected": all_metrics.get("race_conditions_detected", False),
            "acceptance": acceptance,
        },
        "gaps": gaps,
        "evidence": [
            "artifacts/audit/C2/raw_lease_traces.txt",
            "artifacts/audit/C2/heartbeat_renewal_log.txt",
            "artifacts/audit/C2/reassignment_trace.txt",
            "artifacts/audit/C2/concurrent_lease_test.txt",
        ],
        "execution_timestamp": ts(),
    }
    if STOP_REASON:
        report["stop_report"] = STOP_REASON

    # ── Write artifacts ──────────────────────────────────────────
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # Evidence files
    evidence_map = {
        "raw_lease_traces.txt": "\n".join(all_raw.get("raw_lease_traces", [])) + "\n",
        "heartbeat_renewal_log.txt": "\n".join(all_raw.get("heartbeat_renewal_log", [])) + "\n",
        "reassignment_trace.txt": "\n".join(all_raw.get("reassignment_trace", [])) + "\n",
        "concurrent_lease_test.txt": "\n".join(all_raw.get("concurrent_lease_test", [])) + "\n",
    }
    for fname, content in evidence_map.items():
        path = ARTIFACT_DIR / fname
        path.write_text(content)
        E.write(f"  ✅ → {fname}")

    # Report
    report_path = ARTIFACT_DIR / "01_c2_lease_validation_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    E.write(f"  ✅ → 01_c2_lease_validation_report.json")

    # execution_log.txt
    exec_lines = [
        f"# {TASK_ID} — execution_log.txt",
        f"# Generated: {ts()}",
        f"# Script: scripts/audit/c2_lease_validation.py",
        "",
        f"COMMAND: python3 scripts/audit/c2_lease_validation.py",
        f"TIMESTAMP: {ts()}",
        f"EXIT_CODE: {0 if status == 'PASS' else 1}",
        "",
        f"# Acceptance criteria:",
    ]
    for criterion, passed in acceptance.items():
        exec_lines.append(f"#   {criterion}: {'✅' if passed else '❌'}")
    exec_lines.append("")
    exec_lines.append(f"# Status: {status}")
    if STOP_REASON:
        exec_lines.append(f"# STOP_REASON: {STOP_REASON}")
    exec_lines.append("")
    (ARTIFACT_DIR / "execution_log.txt").write_text("\n".join(exec_lines) + "\n")
    E.write(f"  ✅ → execution_log.txt")

    # ── Final summary ───────────────────────────────────────────
    E.write(f"\n{'=' * 70}")
    E.write(f"  FINAL RESULT: {status}")
    E.write(f"{'=' * 70}")
    for criterion, passed in acceptance.items():
        E.write(f"  {'✅' if passed else '❌'} {criterion}")
    E.write(f"\n  Metrics:")
    for k, v in all_metrics.items():
        E.write(f"    {k}: {v}")
    if gaps:
        E.write(f"\n  Gaps:")
        for g in gaps:
            E.write(f"    ⚠️  {g}")
    if STOP_REASON:
        E.write(f"\n  STOP REASON:\n    {STOP_REASON}")
    E.write(f"{'=' * 70}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
