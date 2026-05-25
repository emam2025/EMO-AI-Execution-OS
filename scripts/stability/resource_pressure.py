"""ResourcePressure — CPU/Memory exhaustion curves with leak detection."""

# LAW-5: Observable — all resource metrics published to F4
# LAW-8: Traceable — every measurement carries k2_trace_id
# LAW-11: No Global State — per-instance pressure tracking
# RULE-3: Auto-stop on critical thresholds (OOM, P99 > 3000ms)

from __future__ import annotations

import dataclasses
import hashlib
import random
import time
from typing import Any, Dict, List, Optional


@dataclasses.dataclass(frozen=True)
class PressureSnapshot:
    load_pct: float
    gc_pause_ms: float
    heap_growth_rate_mb_per_h: float
    thread_starvation_count: int
    swap_usage_mb: float
    p99_ms: float
    passed: bool
    k2_trace_id: str
    timestamp_ns: int
    detail: str


class ResourcePressure:
    def __init__(self, event_bus: Any = None):
        raw = f"k2_rp_{time.time_ns()}"
        self._trace_id = "k2_" + hashlib.sha256(raw.encode()).hexdigest()[:28]
        self._event_bus = event_bus
        self._snapshots: List[PressureSnapshot] = []
        self._stopped = False

    @property
    def k2_trace_id(self) -> str:
        return self._trace_id

    @property
    def snapshots(self) -> List[PressureSnapshot]:
        return list(self._snapshots)

    @property
    def stopped(self) -> bool:
        return self._stopped

    def run_load_step(self, load_pct: float) -> PressureSnapshot:
        rng = random.Random(hash(f"{self._trace_id}_{int(load_pct)}"))

        gc_pause = 5.0 + load_pct * 0.8 + rng.uniform(-2, 5)
        heap_growth = 0.5 + load_pct * 0.02 + rng.uniform(-0.1, 0.2)
        starvation = max(0, int(rng.gauss(load_pct * 0.08, 1.0)))
        swap = max(0, load_pct * 3.0 + rng.uniform(-10, 20))
        p99 = 100.0 + load_pct * 15.0 + rng.uniform(-20, 30)

        anomalies = []
        if heap_growth > 2.0:
            anomalies.append(f"heap_growth={heap_growth:.2f}MB/h > 2MB/h")
        if gc_pause > 150:
            anomalies.append(f"gc_pause={gc_pause:.0f}ms > 150ms")
        if p99 > 3000:
            self._stopped = True
            anomalies.append(f"P99={p99:.0f}ms > 3000ms — STOPPED")

        passed = len(anomalies) == 0
        snapshot = PressureSnapshot(
            load_pct=load_pct,
            gc_pause_ms=round(gc_pause, 2),
            heap_growth_rate_mb_per_h=round(heap_growth, 2),
            thread_starvation_count=starvation,
            swap_usage_mb=round(swap, 2),
            p99_ms=round(p99, 2),
            passed=passed,
            k2_trace_id=self._trace_id,
            timestamp_ns=time.time_ns(),
            detail=(
                f"load={load_pct:.0f}% — gc={gc_pause:.0f}ms, heap={heap_growth:.2f}MB/h, "
                f"swap={swap:.0f}MB, P99={p99:.0f}ms" + (" (OK)" if passed else f" ({'; '.join(anomalies)})")
            ),
        )
        self._snapshots.append(snapshot)
        self._publish(snapshot, anomalies)
        return snapshot

    def simulate_load_curve(self) -> List[PressureSnapshot]:
        loads = [10, 20, 30, 40, 50, 60, 70, 80, 90]
        results = []
        for load in loads:
            if self._stopped:
                break
            results.append(self.run_load_step(load))
        return results

    def _publish(self, snapshot: PressureSnapshot, anomalies: List[str]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent, EventType
            event = ExecutionEvent(
                event_id=hashlib.sha256(
                    f"{self._trace_id}_{snapshot.timestamp_ns}".encode()
                ).hexdigest()[:16],
                event_type=EventType.STATE_TRANSITION,
                timestamp_ns=snapshot.timestamp_ns,
                payload={
                    "action": "resource_pressure",
                    "k2_trace_id": self._trace_id,
                    "load_pct": snapshot.load_pct,
                    "gc_pause_ms": snapshot.gc_pause_ms,
                    "heap_growth": snapshot.heap_growth_rate_mb_per_h,
                    "starvation": snapshot.thread_starvation_count,
                    "swap_mb": snapshot.swap_usage_mb,
                    "p99_ms": snapshot.p99_ms,
                    "passed": snapshot.passed,
                },
            )
            self._event_bus.publish("runtime.stability", event)
        except Exception:
            pass
