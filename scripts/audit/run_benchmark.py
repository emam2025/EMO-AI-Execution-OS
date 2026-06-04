#!/usr/bin/env python3
"""EMO AI — Performance Benchmark Runner.

Measures throughput of EventStore append/replay, DistributedPublisher
publish/acknowledge, and HighAvailabilityManager failover detection.

Usage:
    python scripts/audit/run_benchmark.py [--output results.json]

Returns exit code 0 if all benchmarks pass threshold, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkResult:
    name: str
    ops: int
    elapsed_ms: float
    throughput_per_sec: float
    passed: bool
    threshold: str = ""


class EmoBenchmark:
    """Runs performance benchmarks against EMO AI components.

    Measures:
      - EventStore append_event throughput
      - DistributedPublisher publish/acknowledge latency
      - HighAvailabilityManager failover detection time
    """

    def __init__(self, composition: Any) -> None:
        self._comp = composition
        self._results: List[BenchmarkResult] = []

    def run_all(self, threshold_ops_per_sec: float = 100.0) -> List[BenchmarkResult]:
        """Run all benchmarks."""
        self._results.clear()
        self._bench_eventstore_append()
        self._bench_publisher_throughput()
        self._bench_failover_detection()
        self._bench_action_journal_integrity()
        return self._results

    def _bench_eventstore_append(self) -> None:
        """Benchmark EventStore.append_event throughput."""
        es = self._comp.event_store
        count = 500
        start = time.perf_counter()

        from core.models.events import ExecutionEvent
        for i in range(count):
            ev = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type="bench.append",
                timestamp=time.time(),
                source="benchmark",
                payload={"seq": i},
            )
            es.append_event(ev)

        elapsed_s = time.perf_counter() - start
        throughput = count / elapsed_s if elapsed_s > 0 else 0
        passed = throughput >= 100.0

        self._results.append(BenchmarkResult(
            name="EventStore.append_event",
            ops=count,
            elapsed_ms=round(elapsed_s * 1000, 2),
            throughput_per_sec=round(throughput, 1),
            passed=passed,
            threshold=">= 100 ops/sec",
        ))

    def _bench_publisher_throughput(self) -> None:
        """Benchmark DistributedPublisher publish/acknowledge throughput."""
        pub = self._comp.distributed_publisher
        count = 200
        start = time.perf_counter()

        from core.models.events import ExecutionEvent
        ids = []
        for i in range(count):
            ev = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type="bench.publish",
                timestamp=time.time(),
                source="benchmark",
                payload={"seq": i},
            )
            pub.publish(ev)
            ids.append(ev.event_id)

        for eid in ids:
            pub.acknowledge(eid)

        elapsed_s = time.perf_counter() - start
        throughput = (count * 2) / elapsed_s if elapsed_s > 0 else 0
        passed = throughput >= 50.0

        self._results.append(BenchmarkResult(
            name="DistributedPublisher.publish+ack",
            ops=count * 2,
            elapsed_ms=round(elapsed_s * 1000, 2),
            throughput_per_sec=round(throughput, 1),
            passed=passed,
            threshold=">= 50 ops/sec",
        ))

    def _bench_failover_detection(self) -> None:
        """Benchmark HighAvailabilityManager failover detection latency."""
        fm = self._comp.ha_failover_manager
        fm.register_node(node_id="bench-node", heartbeat_interval=0.01)
        fm.record_heartbeat(node_id="bench-node")

        time.sleep(0.05)
        start = time.perf_counter()
        failed = fm.detect_failure()
        elapsed_ms = (time.perf_counter() - start) * 1000
        passed = elapsed_ms < 1000

        self._results.append(BenchmarkResult(
            name="HighAvailabilityManager.failover_detection",
            ops=len(failed),
            elapsed_ms=round(elapsed_ms, 2),
            throughput_per_sec=round(1 / (elapsed_ms / 1000) if elapsed_ms > 0 else 0, 1),
            passed=passed,
            threshold="< 1000ms latency",
        ))

    def _bench_action_journal_integrity(self) -> None:
        """Benchmark ActionJournal.verify_integrity() performance."""
        aj = self._comp.action_journal
        count = 100
        for i in range(count):
            aj.record(
                action_type=f"bench.action.{i}",
                parameters={"seq": i},
                result={"ok": True},
                duration_ms=0.1,
            )

        start = time.perf_counter()
        aj.verify_integrity()
        elapsed_ms = (time.perf_counter() - start) * 1000
        passed = elapsed_ms < 500

        self._results.append(BenchmarkResult(
            name="ActionJournal.verify_integrity",
            ops=count,
            elapsed_ms=round(elapsed_ms, 2),
            throughput_per_sec=round(count / (elapsed_ms / 1000) if elapsed_ms > 0 else 0, 1),
            passed=passed,
            threshold="< 500ms for 100 entries",
        ))

    def export_results(self, filepath: str) -> None:
        """Export benchmark results to JSON."""
        data = {
            "timestamp": time.time(),
            "results": [asdict(r) for r in self._results],
            "all_passed": all(r.passed for r in self._results),
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def print_summary(self) -> None:
        """Print benchmark summary."""
        print("=" * 60)
        print("EMO AI — Performance Benchmark Results")
        print("=" * 60)
        for r in self._results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.name}")
            print(f"         {r.ops} ops in {r.elapsed_ms}ms "
                  f"({r.throughput_per_sec}/sec) — threshold: {r.threshold}")
        print("-" * 60)
        passed = sum(1 for r in self._results if r.passed)
        total = len(self._results)
        print(f"  {passed}/{total} benchmarks passed")
        print("=" * 60)


def main() -> int:
    """Run benchmarks and return exit code."""
    output = "benchmark_results.json"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    from core.composition.root import CompositionRoot

    class Env:
        env_type = "development"
        dsn = "mock://localhost"

    root = CompositionRoot(Env())
    root.initialize()

    bench = EmoBenchmark(root)
    results = bench.run_all()
    bench.print_summary()
    bench.export_results(output)

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
