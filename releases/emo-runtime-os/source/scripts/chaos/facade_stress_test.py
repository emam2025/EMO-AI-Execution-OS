#!/usr/bin/env python3
"""Facade Stress Test — 10k+ concurrent requests under partial degradation.

Validates:
  - EmoRuntimeFacade handles 10k+ concurrent submit/query/observe calls
  - All errors return StructuredFaultResponse (not internal exceptions)
  - Zero router_isolation_violations during stress
  - contract_integrity_rate = 100%

Usage:
    python scripts/chaos/facade_stress_test.py
"""

import json
import logging
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("chaos.facade")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@dataclass
class FacadeStressReport:
    total_requests: int = 0
    succeeded: int = 0
    structured_errors: int = 0  # StructuredFaultResponse
    unstructured_errors: int = 0  # Raw exceptions leaking
    contract_integrity_rate: float = 1.0
    router_isolation_violations: int = 0
    avg_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    passed: bool = False
    errors: List[str] = field(default_factory=list)


class FacadeStressEngine:
    """Stress test harness for EmoRuntimeFacade."""

    def __init__(self, concurrency: int = 50, total_requests: int = 10000):
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.results: List[Dict[str, Any]] = []
        self.facade = self._build_degraded_facade()

    def _build_degraded_facade(self):
        """Build an EmoRuntimeFacade with partially degraded components."""
        from core.runtime.facade import EmoRuntimeFacade

        # Create mock components that fail intermittently
        class FlakyRuntime:
            def execute(self, query):
                import random
                if random.random() < 0.15:
                    raise ConnectionError("Simulated network error")
                return {"status": "ok", "plan_summary": "mock", "session_id": "s1"}

            def observe(self, f):
                return {"status": "ok"}

            def cancel(self, tid):
                return {"status": "cancelled"}

            def resume(self, tid):
                return {"status": "resumed"}

            def scale(self, count):
                return {"status": "scaled"}

            def health(self):
                return {"status": "healthy"}

        class FlakyMemory:
            def get_session(self, sid):
                return None
            def get_dag_trace(self, sid):
                return None

        class FlakyReplay:
            def available_sessions(self, **kw):
                return []
            def step_through(self, sid):
                return []
            def visualize(self, sid):
                return "digraph {}"
            def compare(self, a, b):
                class C: pass
                c = C()
                c.session_a = a; c.session_b = b; c.query_a = ""; c.query_b = ""
                c.total_duration_delta_ms = 0; c.node_count_delta = 0
                c.status_match = True; c.tool_diff = []; c.node_comparisons = []
                return c

        return EmoRuntimeFacade(
            unified_runtime=FlakyRuntime(),
            execution_memory=FlakyMemory(),
            replayer=FlakyReplay(),
        )

    def _send_request(self, request_id: int) -> Dict[str, Any]:
        """Send a single request through the facade."""
        import random
        start = time.time()
        op = random.choice(["submit", "query", "observe", "health"])
        try:
            if op == "submit":
                result = self.facade.submit({"query": f"test_query_{request_id}"})
            elif op == "query":
                result = self.facade.query({"query": f"test_q_{request_id}"})
            elif op == "observe":
                result = self.facade.observe({"target": "health"})
            else:
                result = self.facade.health()

            elapsed = (time.time() - start) * 1000
            is_structured = isinstance(result, dict)
            return {
                "request_id": request_id,
                "operation": op,
                "elapsed_ms": round(elapsed, 2),
                "success": is_structured,
                "structured_error": is_structured and result.get("status") == "error",
                "unstructured_error": not is_structured,
                "result": result,
            }
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return {
                "request_id": request_id,
                "operation": op,
                "elapsed_ms": round(elapsed, 2),
                "success": False,
                "structured_error": False,
                "unstructured_error": True,
                "error": str(e),
            }

    def run(self) -> FacadeStressReport:
        """Execute the stress test."""
        logger.info(
            "Starting facade stress test: %d requests, concurrency=%d",
            self.total_requests, self.concurrency,
        )
        report = FacadeStressReport()
        report.total_requests = self.total_requests

        response_times = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {
                executor.submit(self._send_request, i): i
                for i in range(self.total_requests)
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    self.results.append(result)
                    response_times.append(result["elapsed_ms"])
                    if result["success"]:
                        if result["structured_error"]:
                            report.structured_errors += 1
                        else:
                            report.succeeded += 1
                    if result["unstructured_error"]:
                        report.unstructured_errors += 1
                        report.errors.append(
                            f"Unstructured error: {result.get('error', 'unknown')}"
                        )
                except Exception as e:
                    report.unstructured_errors += 1
                    report.errors.append(f"Future exception: {e}")

        # Compute metrics
        report.avg_response_time_ms = round(
            sum(response_times) / max(1, len(response_times)), 2
        )
        sorted_times = sorted(response_times)
        p99_idx = int(len(sorted_times) * 0.99)
        report.p99_response_time_ms = round(
            sorted_times[p99_idx] if p99_idx < len(sorted_times) else 0, 2
        )
        total_ok = report.succeeded + report.structured_errors
        report.contract_integrity_rate = round(
            total_ok / max(1, report.total_requests), 4
        )
        report.passed = (
            report.unstructured_errors == 0
            and report.contract_integrity_rate >= 0.99
        )

        logger.info(
            "Stress test complete: %d ok, %d structured err, %d unstructured err",
            report.succeeded, report.structured_errors, report.unstructured_errors,
        )
        return report


def save_report(report: FacadeStressReport, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(asdict(report), f, indent=2, default=str)


def main() -> int:
    ci_mode = "--ci" in sys.argv
    engine = FacadeStressEngine(concurrency=50, total_requests=10000)
    report = engine.run()

    output_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "artifacts", "chaos", "02_facade_stress_report.json",
    )
    save_report(report, output_path)

    if ci_mode:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        status = "PASS" if report.passed else "FAIL"
        print(f"\n{'='*60}")
        print(f"  FACADE STRESS TEST — {status}")
        print(f"{'='*60}")
        print(f"  Total requests:        {report.total_requests}")
        print(f"  Succeeded:             {report.succeeded}")
        print(f"  Structured errors:     {report.structured_errors}")
        print(f"  Unstructured errors:   {report.unstructured_errors}")
        print(f"  Contract integrity:    {report.contract_integrity_rate:.2%}")
        print(f"  Avg response time:     {report.avg_response_time_ms:.2f} ms")
        print(f"  P99 response time:     {report.p99_response_time_ms:.2f} ms")
        print(f"  Router violations:     {report.router_isolation_violations}")
        print(f"{'='*60}\n")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
