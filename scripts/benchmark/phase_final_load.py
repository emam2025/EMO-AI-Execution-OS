#!/usr/bin/env python3
"""Phase FINAL — Production Readiness Load Benchmark.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-15 LAW-20 RULE-1 RULE-2 RULE-3 RULE-5

Simulates 100 concurrent DAGs, applies CPU/memory pressure, measures
throughput and latency, and detects oscillation. Results are saved to
artifacts/certification/performance_benchmark.json.

Usage:
    python scripts/benchmark/phase_final_load.py

Ref: Canon LAW 3 (Deterministic), LAW 5 (Observability)
Ref: Canon LAW 8 (Recoverability), LAW 11 (No Global State)
Ref: Canon LAW 15 (Cost), LAW 20 (Failure Detection)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 5 (Recovery)
Ref: DEVELOPER.md §15.13, §16.1
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List

# Ensure core is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def generate_dag_template(dag_id: str, nodes: int = 10, edges: int = 15) -> Dict[str, Any]:
    return {
        "dag_id": dag_id,
        "nodes": nodes,
        "edges": edges,
        "base_runtime_ms": 10 + (hash(dag_id) % 20),
    }


def simulate_100_concurrent_dags(trace_id: str) -> Dict[str, Any]:
    from core.runtime.certification.load_generator import LoadGenerator

    generator = LoadGenerator(strict_certification_mode=True)
    template = generate_dag_template("benchmark_template")
    return generator.simulate_concurrent_dags(
        dag_count=100,
        dag_template=template,
        certification_trace_id=trace_id,
    )


def apply_resource_pressure(trace_id: str) -> Dict[str, Any]:
    from core.runtime.certification.load_generator import LoadGenerator

    generator = LoadGenerator(strict_certification_mode=True)
    return generator.apply_resource_pressure(
        cpu_percent=80.0,
        memory_mb=512,
        duration_sec=3.0,
        certification_trace_id=trace_id,
    )


def measure_throughput(trace_id: str) -> Dict[str, Any]:
    from core.runtime.certification.load_generator import LoadGenerator

    generator = LoadGenerator(strict_certification_mode=True)
    return generator.measure_throughput(
        operation_count=1000,
        batch_size=50,
        certification_trace_id=trace_id,
    )


def detect_oscillation(trace_id: str) -> Dict[str, Any]:
    from core.runtime.certification.load_generator import LoadGenerator

    generator = LoadGenerator(strict_certification_mode=True)
    samples: List[float] = []
    for i in range(50):
        base = 50.0 + (i % 10) * 15
        spike = 150.0 if i % 7 == 0 else 0.0
        samples.append(base + spike)
    return generator.detect_oscillation(
        latency_samples=samples,
        certification_trace_id=trace_id,
    )


def run_benchmark() -> Dict[str, Any]:
    trace_id = f"bench_{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]}"
    start = time.time()

    print(f"[benchmark] Starting Phase FINAL load benchmark (trace_id={trace_id})")
    print(f"[benchmark] 1/4 Simulating 100 concurrent DAGs...")
    dag_results = simulate_100_concurrent_dags(trace_id)
    print(f"  Executed: {dag_results['dags_executed']}, Failed: {dag_results['dags_failed']}")
    print(f"  Avg latency: {dag_results['avg_latency_ms']}ms, P99: {dag_results['p99_latency_ms']}ms")
    print(f"  Throughput: {dag_results['throughput']} DAGs/sec")

    print(f"[benchmark] 2/4 Applying resource pressure (CPU 80%, 512MB)...")
    pressure_results = apply_resource_pressure(trace_id)
    print(f"  CPU achieved: {pressure_results['cpu_achieved_pct']}%, Memory: {pressure_results['memory_used_mb']}MB")
    print(f"  Recovery time: {pressure_results['recovery_time_ms']}ms")

    print(f"[benchmark] 3/4 Measuring throughput (1000 ops)...")
    throughput_results = measure_throughput(trace_id)
    print(f"  Operations: {throughput_results['operations_completed']}")
    print(f"  Throughput: {throughput_results['throughput_ops_per_sec']} ops/sec")
    print(f"  P50: {throughput_results['p50_latency_ms']}ms, P90: {throughput_results['p90_latency_ms']}ms, P99: {throughput_results['p99_latency_ms']}ms")

    print(f"[benchmark] 4/4 Detecting oscillation...")
    oscillation_results = detect_oscillation(trace_id)
    print(f"  Oscillation detected: {oscillation_results['oscillation_detected']}")
    print(f"  Score: {oscillation_results['oscillation_score']}, Recommendation: {oscillation_results['recommendation']}")

    elapsed = round(time.time() - start, 2)
    print(f"[benchmark] Completed in {elapsed}s")

    benchmark = {
        "benchmark_id": f"bm_{trace_id}",
        "trace_id": trace_id,
        "started_at_ns": int(start * 1e9),
        "duration_sec": elapsed,
        "concurrent_dags": dag_results,
        "resource_pressure": pressure_results,
        "throughput": throughput_results,
        "oscillation": oscillation_results,
        "summary": {
            "total_dags": 100,
            "dags_executed": dag_results["dags_executed"],
            "dags_failed": dag_results["dags_failed"],
            "p99_latency_ms": dag_results["p99_latency_ms"],
            "throughput_dags_per_sec": dag_results["throughput"],
            "oscillation_detected": oscillation_results["oscillation_detected"],
            "stability_verdict": "stable" if not oscillation_results["oscillation_detected"] and dag_results["p99_latency_ms"] < 200 else "review_needed",
        },
    }

    # Save to artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "certification")
    os.makedirs(artifacts_dir, exist_ok=True)
    output_path = os.path.join(artifacts_dir, "performance_benchmark.json")
    with open(output_path, "w") as f:
        json.dump(benchmark, f, indent=2)
    print(f"[benchmark] Results saved to {output_path}")

    return benchmark


if __name__ == "__main__":
    run_benchmark()
