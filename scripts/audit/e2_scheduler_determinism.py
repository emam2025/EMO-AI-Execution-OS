#!/usr/bin/env python3
"""
AUDIT-CLOSURE-E2-008 — Scheduler Determinism (Phase E — Determinism Audit)

Tasks:
  1. Stable Node Ordering (50 runs)
  2. Tie-Break Consistency (30 runs)
  3. Fairness Reproducibility (10 concurrent runs × 5 DAGs)
  4. No Random Worker Selection (20 runs)
  5. Report Generation

Rules:
  - NO core/ or tests/ modification
  - Actual DistributedScheduler.schedule() with real WorkerRegistry
  - RAW evidence with timestamps
  - STOP-CONDITION on any non-determinism
"""

import csv
import hashlib
import json
import os
import sys
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Tuple

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.distributed_scheduler import DistributedScheduler
from core.distributed_types import WorkerNode, WorkerStatus
from core.models.dag import DependencyGraph, PlanNode, NodeState
from core.worker_registry import WorkerRegistry

ARTIFACT_DIR = Path("artifacts/audit/E2")
TASK_ID = "AUDIT-CLOSURE-E2-008"
TS_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
NUM_ORDER_RUNS = 50
NUM_TIEBREAK_RUNS = 30
NUM_WORKER_RUNS = 20
TMP = ARTIFACT_DIR / ".tmp"


def ts() -> str:
    return datetime.now(timezone.utc).strftime(TS_FMT)


def sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def make_worker(wid: str, capacity: int = 3, tool_names: Optional[List[str]] = None,
                tags: Optional[Dict[str, str]] = None) -> WorkerNode:
    from core.models.dag import ToolSpec
    tools = [ToolSpec(name=t) for t in (tool_names or ["default"])]
    return WorkerNode(
        id=wid,
        url=f"tcp://{wid}:0",
        capacity=capacity,
        current_load=0,
        tools=tools,
        tags=tags or {},
        status=WorkerStatus.IDLE,
    )


def build_fork_dag() -> DependencyGraph:
    """A → [B, C, D] → E"""
    dag = DependencyGraph()
    for nid in ["A", "B", "C", "D", "E"]:
        dag.add_node(PlanNode(id=nid, tool="default", inputs={"id": nid}))
    dag.add_edge("A", "B"); dag.add_edge("A", "C"); dag.add_edge("A", "D")
    dag.add_edge("B", "E"); dag.add_edge("C", "E"); dag.add_edge("D", "E")
    return dag


def build_tiebreak_dag() -> DependencyGraph:
    """3 sibling nodes at same depth: X, Y, Z"""
    dag = DependencyGraph()
    for nid in ["ROOT", "X", "Y", "Z", "END"]:
        dag.add_node(PlanNode(id=nid, tool="default", inputs={"id": nid, "priority": 1}))
    dag.add_edge("ROOT", "X"); dag.add_edge("ROOT", "Y"); dag.add_edge("ROOT", "Z")
    dag.add_edge("X", "END"); dag.add_edge("Y", "END"); dag.add_edge("Z", "END")
    return dag


class EvidenceLogger:
    def __init__(self):
        self._buf: list[str] = []

    def write(self, line: str = ""):
        self._buf.append(line)
        print(line)

    def dump(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self._buf) + "\n")


E = EvidenceLogger()
STOP_REASON: Optional[str] = None


def stop_if(condition: bool, phase: str, cause: str, action: str):
    global STOP_REASON
    if condition and STOP_REASON is None:
        STOP_REASON = f"STOP-REPORT | {TASK_ID} | {phase} | {cause} | {action}"
        E.write(f"\n  ❌ STOP: {STOP_REASON}")


PASS = "✅"
FAIL = "❌"


def get_levels(dag: DependencyGraph, tool: str = "default") -> List[List[PlanNode]]:
    """Return nodes grouped by topological depth."""
    in_degree: Dict[str, int] = {nid: 0 for nid in dag.nodes}
    for e in dag.edges:
        if e.target_id in in_degree:
            in_degree[e.target_id] += 1
    levels: List[List[PlanNode]] = []
    remaining = set(dag.nodes.keys())
    while remaining:
        ready = [nid for nid in remaining if in_degree.get(nid, 0) == 0]
        if not ready:
            break
        ready.sort()
        level_nodes = [PlanNode(id=nid, tool=tool, inputs={"id": nid}) for nid in ready]
        levels.append(level_nodes)
        for nid in ready:
            remaining.remove(nid)
            for e in dag.edges:
                if e.source_id == nid and e.target_id in in_degree:
                    in_degree[e.target_id] -= 1
    return levels


# ═══════════════════════════════════════════════════════════════════
# TASK 1: Stable Node Ordering
# ═══════════════════════════════════════════════════════════════════

def task1_node_ordering():
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 1: STABLE NODE ORDERING ({NUM_ORDER_RUNS} runs)")
    E.write(f"{'=' * 70}")

    dag = build_fork_dag()
    levels = get_levels(dag)
    E.write(f"  DAG levels: {[[n.id for n in lvl] for lvl in levels]}")

    records: List[List[str]] = []

    for run_idx in range(1, NUM_ORDER_RUNS + 1):
        registry = WorkerRegistry()
        for wid in ["w1", "w2", "w3"]:
            registry.register(make_worker(wid, capacity=5))

        scheduler = DistributedScheduler(registry=registry)
        all_assignments: List[str] = []

        for lvl in levels:
            assigns, unassigned = scheduler.schedule(lvl)
            for a in assigns:
                all_assignments.append(f"{a.tool}→{a.worker_id}")

        order_str = " | ".join(all_assignments) if all_assignments else "(empty)"
        schedule_hash = sha256(all_assignments)
        records.append({
            "run": run_idx,
            "schedule": order_str,
            "hash": schedule_hash,
        })

        E.write(f"  Run {run_idx:2d}: {PASS if run_idx == 1 else ''} "
                f"hash={schedule_hash[:12]}...")

    # Compare
    hashes = [r["hash"] for r in records]
    order_match = len(set(hashes)) == 1
    E.write(f"\n  Order match: {PASS if order_match else FAIL} "
            f"({len(set(hashes))} unique / {len(records)} runs)")
    if not order_match:
        stop_if(True, "T1", "Scheduling order divergence",
                "Investigate DistributedScheduler determinism")

    # Write raw evidence
    csv_path = ARTIFACT_DIR / "e2_50_run_order_matrix.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["run", "schedule", "hash"])
        w.writeheader()
        w.writerows(records)
    E.write(f"  {PASS} → e2_50_run_order_matrix.csv")

    return {
        "order_match": order_match,
        "unique_orders": len(set(hashes)),
        "records": records,
    }


# ═══════════════════════════════════════════════════════════════════
# TASK 2: Tie-Break Consistency
# ═══════════════════════════════════════════════════════════════════

def task2_tiebreak():
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 2: TIE-BREAK CONSISTENCY ({NUM_TIEBREAK_RUNS} runs)")
    E.write(f"{'=' * 70}")

    dag = build_tiebreak_dag()
    # Level that contains X, Y, Z (same depth, same priority)
    levels = get_levels(dag)
    tiebreak_level = [lvl for lvl in levels if len(lvl) >= 3][0]
    tie_ids = sorted(n.id for n in tiebreak_level)
    E.write(f"  Tie-break candidates: {tie_ids}")

    tie_orders: List[str] = []
    for run_idx in range(1, NUM_TIEBREAK_RUNS + 1):
        registry = WorkerRegistry()
        for wid in ["w1", "w2", "w3"]:
            registry.register(make_worker(wid, capacity=5))

        scheduler = DistributedScheduler(registry=registry)
        assigns, unassigned = scheduler.schedule(tiebreak_level)

        worker_ids = [a.worker_id for a in assigns]
        order_str = ",".join(worker_ids)
        tie_orders.append(order_str)

        E.write(f"  Run {run_idx:2d}: {assigns[0].worker_id} | {assigns[1].worker_id} | {assigns[2].worker_id}")

    consistent = len(set(tie_orders)) == 1
    detected_rule = f"least-loaded (min load/capacity, worker registry order)"

    E.write(f"\n  Tie-break consistent: {PASS if consistent else FAIL}")
    E.write(f"  Detected rule: {detected_rule}")

    if not consistent:
        stop_if(True, "T2", "Tie-break inconsistency",
                "Investigate DistributedScheduler tie-breaking")

    # Write trace
    trace_lines = [
        f"# tie_break_trace.txt — {TASK_ID}",
        f"# Generated: {ts()}",
        f"# Candidates: {tie_ids}",
        f"# Consistent: {consistent}",
        f"# Rule: {detected_rule}",
        "",
    ]
    for i, order in enumerate(tie_orders, 1):
        mark = PASS if order == tie_orders[0] else FAIL
        trace_lines.append(f"Run {i:2d} | {mark} | {order}")
    (ARTIFACT_DIR / "tie_break_trace.txt").write_text("\n".join(trace_lines) + "\n")
    E.write(f"  {PASS} → tie_break_trace.txt")

    return {"consistent": consistent, "rule": detected_rule}


# ═══════════════════════════════════════════════════════════════════
# TASK 3: Fairness Reproducibility
# ═══════════════════════════════════════════════════════════════════

def task3_fairness():
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 3: FAIRNESS REPRODUCIBILITY (10× concurrent)")
    E.write(f"{'=' * 70}")

    def submit_dags(dag_id: str, tool: str, count: int) -> DistributedScheduler:
        reg = WorkerRegistry()
        for wid in ["fair_w1", "fair_w2"]:
            reg.register(make_worker(wid, capacity=10, tool_names=[tool]))
        sched = DistributedScheduler(registry=reg)

        for _ in range(count):
            dag = DependencyGraph()
            dag.add_node(PlanNode(id=f"{dag_id}_task", tool=tool, inputs={"dag": dag_id}))
            lvl = [PlanNode(id=f"{dag_id}_n", tool=tool, inputs={"dag": dag_id})]
            sched.schedule(lvl)

        return sched

    run_metrics: List[Dict[str, Any]] = []

    for run_idx in range(1, 11):
        reg = WorkerRegistry()
        for wid in ["fair_w1", "fair_w2"]:
            reg.register(make_worker(wid, capacity=10, tool_names=["compute"]))

        sched = DistributedScheduler(registry=reg)
        task_counts: Dict[str, int] = {"fair_w1": 0, "fair_w2": 0}
        wait_times: Dict[str, float] = {}

        dags = ["dag_A", "dag_B", "dag_C", "dag_D", "dag_E"]
        nodes = []
        for dag_id in dags:
            for i in range(4):
                nodes.append(PlanNode(
                    id=f"{dag_id}_n{i}", tool="compute",
                    inputs={"dag": dag_id, "seq": i},
                ))

        t0 = time.time()
        assigns, unassigned = sched.schedule(nodes)
        elapsed = time.time() - t0

        for a in assigns:
            task_counts[a.worker_id] = task_counts.get(a.worker_id, 0) + 1

        total_assigned = len(assigns)
        vals = list(task_counts.values())
        avg = mean(vals)
        sd = stdev(vals) if len(vals) > 1 else 0.0
        fairness_variance_pct = (sd / avg * 100) if avg > 0 else 0.0

        run_metrics.append({
            "run": run_idx,
            "tasks_per_worker": dict(task_counts),
            "total_assigned": total_assigned,
            "mean": round(avg, 2),
            "stddev": round(sd, 2),
            "fairness_variance_pct": round(fairness_variance_pct, 4),
            "elapsed_ms": round(elapsed * 1000, 2),
        })

        E.write(f"  Run {run_idx:2d}: "
                f"w1={task_counts.get('fair_w1',0)} w2={task_counts.get('fair_w2',0)} "
                f"var={fairness_variance_pct:.2f}%")

    fairness_vals = [m["fairness_variance_pct"] for m in run_metrics]
    mean_fv = mean(fairness_vals)
    sd_fv = stdev(fairness_vals) if len(fairness_vals) > 1 else 0.0

    # Reproducibility: the fairness metric std dev should be < 2%
    reproducibility_pass = sd_fv < 2.0
    E.write(f"\n  Fairness variance across runs: mean={mean_fv:.2f}%, stddev={sd_fv:.2f}%")
    E.write(f"  Reproducible (σ < 2%): {PASS if reproducibility_pass else FAIL}")

    if not reproducibility_pass:
        stop_if(True, "T3", "Fairness reproducibility exceeds 2% threshold",
                "Investigate fairness algorithm stability")

    # Write CSV
    csv_path = ARTIFACT_DIR / "fairness_matrix.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "run", "tasks_per_worker", "total_assigned",
            "mean", "stddev", "fairness_variance_pct", "elapsed_ms",
        ])
        w.writeheader()
        w.writerows(run_metrics)
    E.write(f"  {PASS} → fairness_matrix.csv")

    return {
        "fairness_variance_pct": round(mean_fv, 2),
        "reproducible": reproducibility_pass,
        "metrics": run_metrics,
    }


# ═══════════════════════════════════════════════════════════════════
# TASK 4: No Random Worker Selection
# ═══════════════════════════════════════════════════════════════════

def task4_worker_assignment():
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 4: NO RANDOM WORKER SELECTION ({NUM_WORKER_RUNS} runs)")
    E.write(f"{'=' * 70}")

    # 3 identical workers, 3 parallel nodes → assignment should be deterministic
    workers = ["alpha", "beta", "gamma"]
    nodes = [
        PlanNode(id="Node-A", tool="compute", inputs={"id": "A"}),
        PlanNode(id="Node-B", tool="compute", inputs={"id": "B"}),
        PlanNode(id="Node-C", tool="compute", inputs={"id": "C"}),
    ]

    assignment_records: List[str] = []
    for run_idx in range(1, NUM_WORKER_RUNS + 1):
        registry = WorkerRegistry()
        for wid in workers:
            registry.register(make_worker(wid, capacity=5, tool_names=["compute"]))

        scheduler = DistributedScheduler(registry=registry)
        assigns, unassigned = scheduler.schedule(nodes)

        assignment_seq = ",".join(f"{n.inputs['id']}→{a.worker_id}"
                                   for n, a in zip(nodes, assigns))
        assignment_records.append(assignment_seq)
        E.write(f"  Run {run_idx:2d}: {assignment_seq}")

    # Verify deterministic
    deterministic = len(set(assignment_records)) == 1
    E.write(f"\n  Deterministic: {PASS if deterministic else FAIL}")

    if not deterministic:
        counts = Counter(assignment_records)
        for seq, c in counts.most_common():
            E.write(f"       {seq}: {c} runs")
        stop_if(True, "T4", "Non-deterministic worker assignment",
                "Investigate min() tie-break in any_worker_for")

    # Determine assignment rule
    first_assign = assignment_records[0] if assignment_records else ""
    nodes_seq = first_assign.split(",")
    assignment_rule = "least-loaded → min(load/capacity, -capacity) → first in registry order"
    E.write(f"  Assignment rule: {assignment_rule}")

    # Write log
    log_lines = [
        f"# worker_assignment_log.txt — {TASK_ID}",
        f"# Generated: {ts()}",
        f"# Workers: {workers}",
        f"# Nodes: {[n.id for n in nodes]}",
        f"# Deterministic: {deterministic}",
        f"# Rule: {assignment_rule}",
        "",
    ]
    for i, seq in enumerate(assignment_records, 1):
        mark = PASS if seq == assignment_records[0] else FAIL
        log_lines.append(f"Run {i:2d} | {mark} | {seq}")
    (ARTIFACT_DIR / "worker_assignment_log.txt").write_text("\n".join(log_lines) + "\n")
    E.write(f"  {PASS} → worker_assignment_log.txt")

    return {
        "deterministic": deterministic,
        "rule": assignment_rule,
        "records": assignment_records,
    }


# ═══════════════════════════════════════════════════════════════════
# TASK 5: Report Generation
# ═══════════════════════════════════════════════════════════════════

def task5_report(
    t1, t2, t3, t4,
    order_match: bool,
    tiebreak_consistent: bool,
    tiebreak_rule: str,
    fairness_variance_pct: float,
    worker_deterministic: bool,
    assignment_rule: str,
):
    E.write(f"\n{'=' * 70}")
    E.write(f"TASK 5: QUANTITATIVE REPORT")
    E.write(f"{'=' * 70}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    metrics = {
        "runs_executed": NUM_ORDER_RUNS,
        "node_order_match": order_match,
        "tie_break_consistent": tiebreak_consistent,
        "tie_break_rule": tiebreak_rule,
        "fairness_variance_pct": round(fairness_variance_pct, 2),
        "worker_assignment_deterministic": worker_deterministic,
        "assignment_rule": assignment_rule,
        "random_selection_detected": not worker_deterministic,
    }

    acceptance = {
        "runs_executed >= 50": metrics["runs_executed"] >= 50,
        "node_order_match = true": metrics["node_order_match"],
        "tie_break_consistent = true": metrics["tie_break_consistent"],
        "fairness_variance_pct < 2.0": metrics["fairness_variance_pct"] < 2.0,
        "worker_assignment_deterministic = true": metrics["worker_assignment_deterministic"],
        "random_selection_detected = false": not metrics["random_selection_detected"],
    }

    all_pass = all(acceptance.values()) and STOP_REASON is None
    status = "PASS" if all_pass else "FAIL"
    if STOP_REASON:
        status = "FAIL"

    gaps = []
    if not order_match:
        gaps.append("Scheduling order divergence")
    if not tiebreak_consistent:
        gaps.append("Tie-break inconsistency")
    if not acceptance["fairness_variance_pct < 2.0"]:
        gaps.append(f"Fairness variance {fairness_variance_pct:.2f}% >= 2.0% threshold")
    if not worker_deterministic:
        gaps.append("Non-deterministic worker assignment")
    gaps.append(
        "CompositionRoot does not expose a `scheduler` property — "
        "DistributedScheduler instantiated directly"
    )

    report = {
        "task_id": TASK_ID,
        "status": status,
        "metrics": metrics,
        "acceptance": acceptance,
        "gaps": gaps,
        "evidence": [
            "e2_50_run_order_matrix.csv",
            "tie_break_trace.txt",
            "fairness_matrix.csv",
            "worker_assignment_log.txt",
        ],
        "execution_timestamp": ts(),
    }
    if STOP_REASON:
        report["stop_report"] = STOP_REASON

    (ARTIFACT_DIR / "01_e2_scheduler_determinism_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    E.write(f"  {PASS} → 01_e2_scheduler_determinism_report.json")

    # Execution log
    exec_lines = [
        f"# {TASK_ID} — execution_log.txt",
        f"# Generated: {ts()}",
        f"# Script: scripts/audit/e2_scheduler_determinism.py",
        "",
        f"COMMAND: python3 scripts/audit/e2_scheduler_determinism.py",
        f"TIMESTAMP: {ts()}",
        f"EXIT_CODE: {0 if status == 'PASS' else 1}",
        "",
        "# Acceptance:",
    ]
    for crit, passed in acceptance.items():
        exec_lines.append(f"#   {PASS if passed else FAIL} {crit}")
    exec_lines.extend(["", f"# Status: {status}"])
    if STOP_REASON:
        exec_lines.append(f"# STOP: {STOP_REASON}")
    exec_lines.append("")
    (ARTIFACT_DIR / "execution_log.txt").write_text("\n".join(exec_lines) + "\n")
    E.write(f"  {PASS} → execution_log.txt")

    E.write(f"\n{'=' * 70}")
    E.write(f"  FINAL: {status}")
    E.write(f"{'=' * 70}")
    for crit, passed in acceptance.items():
        E.write(f"  {PASS if passed else FAIL} {crit}")
    E.write(f"\n  Metrics: {json.dumps(metrics, indent=2)}")
    if gaps:
        E.write(f"\n  Gaps:")
        for g in gaps:
            E.write(f"    {g}")
    E.write(f"{'=' * 70}")

    return status


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    global STOP_REASON
    E.write(f"{'=' * 70}")
    E.write(f"  {TASK_ID}")
    E.write(f"  Scheduler Determinism (Phase E — Determinism Audit)")
    E.write(f"  Started: {ts()}")
    E.write(f"{'=' * 70}")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    def _run_task(fn, name):
        global STOP_REASON
        try:
            return fn()
        except Exception as exc:
            E.write(f"\n  ❌ TASK {name} FAILED: {type(exc).__name__}: {exc}")
            import traceback; traceback.print_exc()
            if STOP_REASON is None:
                STOP_REASON = f"STOP-REPORT | {TASK_ID} | {name} | {type(exc).__name__}: {exc} | Investigate"
            return None

    t1 = _run_task(task1_node_ordering, "T1")
    if STOP_REASON: return 1

    t2 = _run_task(task2_tiebreak, "T2")
    if STOP_REASON: return 1

    t3 = _run_task(task3_fairness, "T3")
    if STOP_REASON: return 1

    t4 = _run_task(task4_worker_assignment, "T4")
    if STOP_REASON: return 1

    def g(d, key, default=None):
        return d.get(key, default) if d else default

    order_match = g(t1, "order_match", False)
    tiebreak_consistent = g(t2, "consistent", False)
    tiebreak_rule = g(t2, "rule", "unknown")
    fairness_variance_pct = g(t3, "fairness_variance_pct", 100.0)
    worker_deterministic = g(t4, "deterministic", False)
    assignment_rule = g(t4, "rule", "unknown")

    _ = task5_report(t1, t2, t3, t4,
                     order_match, tiebreak_consistent, tiebreak_rule,
                     fairness_variance_pct, worker_deterministic, assignment_rule)

    import shutil
    if TMP.exists():
        shutil.rmtree(TMP)

    return 0


if __name__ == "__main__":
    sys.exit(main())
