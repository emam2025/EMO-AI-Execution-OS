"""
Sustained Load Runner — Performance Benchmarking for EMO Final Delivery.

Launches 10 concurrent simulated tenants, each submitting 500 requests/min
for a 15-minute sustained period. Measures P50/P95/P99 latency, memory growth,
CPU utilization, DAG completion rate, and event bus lag.

Usage:
    python scripts/benchmark/sustained_load_runner.py
"""
import asyncio
import json
import os
import sys
import time
import statistics
import tracemalloc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.runtime.facade import EmoRuntimeFacade
from core.orchestration.planner_agent import PlannerAgent
from core.orchestration.critic_agent import CriticAgent
from core.orchestration.optimizer_agent import OptimizerAgent
from core.orchestration.orchestration_state_machine import OrchestrationStateMachine
from core.orchestration.trace_correlator import OrchestrationTraceCorrelator


TENANTS = [f"tenant_{i}" for i in range(10)]
INTENTS = ["summarize", "analyze", "translate", "refactor", "debug"]
DURATION_MINUTES = 15
TARGET_RATE_PER_TENANT = 500  # requests per minute
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                           "artifacts", "benchmark", "performance_baseline.jsonl")


def _build_facade() -> EmoRuntimeFacade:
    return EmoRuntimeFacade(
        planner_agent=PlannerAgent(),
        critic_agent=CriticAgent(),
        optimizer_agent=OptimizerAgent(),
        orchestration_state_machine=OrchestrationStateMachine(),
        orchestration_trace_correlator=OrchestrationTraceCorrelator(),
    )


async def _tenant_worker(
    tenant_id: str,
    facade: EmoRuntimeFacade,
    results: list,
    stop_event: asyncio.Event,
    phase: str,
):
    """Single tenant: submits orchestrate requests at target rate until stop."""
    import random
    interval = 60.0 / TARGET_RATE_PER_TENANT  # seconds between requests

    while not stop_event.is_set():
        intent = random.choice(INTENTS)
        t0 = time.monotonic()
        try:
            r = await facade.orchestrate(
                intent, tenant_id,
                {"trace_snippets": [{"id": random.randint(1, 100)}]},
                {"max_cost_units": "100"},
            )
        except Exception as exc:
            t1 = time.monotonic()
            results.append({
                "tenant": tenant_id,
                "phase": phase,
                "latency_s": t1 - t0,
                "status": "exception",
                "error": str(exc),
            })
        else:
            t1 = time.monotonic()
            results.append({
                "tenant": tenant_id,
                "phase": phase,
                "latency_s": t1 - t0,
                "status": r.get("status", "unknown"),
            })
        await asyncio.sleep(interval)


async def _measure_resources(snapshots: list, stop_event: asyncio.Event):
    """Sample memory and CPU every 10 seconds."""
    import psutil
    proc = psutil.Process()
    mem_start = proc.memory_info().rss / 1024 / 1024  # MB
    cpu_count = psutil.cpu_count()

    while not stop_event.is_set():
        await asyncio.sleep(10)
        mem = proc.memory_info().rss / 1024 / 1024
        cpu = proc.cpu_percent(interval=0.5) / cpu_count
        snapshots.append({
            "timestamp": time.time(),
            "memory_mb": mem,
            "cpu_percent_avg": cpu,
        })


async def main():
    print(f"[benchmark] Starting sustained load: {len(TENANTS)} tenants, "
          f"{TARGET_RATE_PER_TENANT} req/min/tenant, {DURATION_MINUTES}min")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    facade = _build_facade()
    results = []
    snapshots = []
    stop_event = asyncio.Event()

    # Warmup phase (30s)
    print("[benchmark] Warmup phase (30s)...")
    warmup_tasks = [
        _tenant_worker(t, facade, results, stop_event, "warmup")
        for t in TENANTS
    ]
    warmup_runner = asyncio.gather(*warmup_tasks)
    await asyncio.sleep(30)
    stop_event.set()
    await warmup_runner
    stop_event.clear()

    # Measure pre-bench resources
    import psutil
    proc = psutil.Process()
    mem_before = proc.memory_info().rss / 1024 / 1024
    print(f"[benchmark] Memory before sustained phase: {mem_before:.1f} MB")

    # Sustained phase (15 min)
    print("[benchmark] Sustained load phase (15 min)...")
    sustained_results = []
    sustained_tasks = [
        _tenant_worker(t, facade, sustained_results, stop_event, "sustained")
        for t in TENANTS
    ]
    resource_task = asyncio.create_task(
        _measure_resources(snapshots, stop_event)
    )
    sustained_runner = asyncio.gather(*sustained_tasks)

    await asyncio.sleep(DURATION_MINUTES * 60)
    stop_event.set()
    await sustained_runner
    resource_task.cancel()
    try:
        await resource_task
    except asyncio.CancelledError:
        pass

    # Post-bench resources
    mem_after = proc.memory_info().rss / 1024 / 1024
    mem_growth = mem_after - mem_before
    print(f"[benchmark] Memory after sustained phase: {mem_after:.1f} MB "
          f"(growth: {mem_growth:.2f} MB)")

    # Aggregate results
    latencies = [r["latency_s"] for r in sustained_results]
    statuses = [r["status"] for r in sustained_results]
    completed = sum(1 for s in statuses if s == "ok")
    rejected = sum(1 for s in statuses if s == "rejected")
    errors = sum(1 for s in statuses if s == "exception")

    summary = {
        "phase": "sustained",
        "duration_minutes": DURATION_MINUTES,
        "tenants": len(TENANTS),
        "target_rate_per_tenant": TARGET_RATE_PER_TENANT,
        "total_requests": len(sustained_results),
        "p50_s": statistics.median(latencies) if latencies else 0,
        "p95_s": statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0),
        "p99_s": statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else (max(latencies) if latencies else 0),
        "max_s": max(latencies) if latencies else 0,
        "completed": completed,
        "rejected": rejected,
        "errors": errors,
        "dag_completion_rate": completed / max(len(sustained_results), 1),
        "memory_before_mb": round(mem_before, 1),
        "memory_after_mb": round(mem_after, 1),
        "memory_growth_mb_per_h": round(mem_growth * (60 / DURATION_MINUTES), 2),
        "cpu_utilization_avg": round(
            statistics.mean([s["cpu_percent_avg"] for s in snapshots]), 1
        ) if snapshots else 0,
    }

    print(f"\n[benchmark] === RESULTS ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # Write time-series data
    with open(OUTPUT_PATH, "w") as f:
        for r in sustained_results:
            f.write(json.dumps(r) + "\n")
        for s in snapshots:
            f.write(json.dumps(s) + "\n")

    print(f"\n[benchmark] Results written to {OUTPUT_PATH}")
    return summary


if __name__ == "__main__":
    asyncio.run(main())
