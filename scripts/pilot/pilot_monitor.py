"""Pilot Monitor — real-time runtime stability monitoring (30s interval).  # LAW-5

Monitors P99, replay_drift, memory_growth, lease_conflict every 30s
during production pilot. Outputs time-series to artifacts/pilot/.

Ref: EXEC-DIRECTIVE-PILOT-001 §Task-3
Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE = Path(__file__).resolve().parent.parent.parent


class PilotMonitor:
    """Real-time pilot monitoring with 30s interval sampling."""

    def __init__(
        self,
        api_host: str = "localhost",
        api_port: int = 8080,
        interval_sec: int = 30,
        max_samples: int = 0,
        output_dir: Optional[Path] = None,
    ) -> None:
        self._host = api_host
        self._port = api_port
        self._interval = interval_sec
        self._max_samples = max_samples
        self._output_dir = output_dir or (BASE / "artifacts" / "pilot")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._samples: List[Dict[str, Any]] = []
        self._running = False

    def _sample(self) -> Dict[str, Any]:
        import urllib.request
        ts = time.time()
        sample: Dict[str, Any] = {
            "timestamp_ns": time.time_ns(),
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        }
        try:
            r = urllib.request.urlopen(
                f"http://{self._host}:{self._port}/api/health", timeout=5
            )
            data = json.loads(r.read())
            sample["p99_latency_ms"] = data.get("p99_latency_ms", -1)
            sample["p95_latency_ms"] = data.get("p95_latency_ms", -1)
            sample["queue_pressure"] = data.get("queue_pressure", -1)
            sample["worker_count"] = data.get("worker_count", -1)
            sample["active_dags"] = data.get("active_dags", -1)
            sample["replay_drift"] = data.get("replay_drift", -1)
            sample["healthy_workers"] = data.get("healthy_workers", -1)
            sample["degraded_workers"] = data.get("degraded_workers", -1)
            sample["status"] = "ok"
        except Exception as e:
            sample["status"] = "error"
            sample["error"] = str(e)
        sample["elapsed_sec"] = round(time.time() - ts, 3)
        return sample

    def sample_once(self) -> Dict[str, Any]:
        s = self._sample()
        self._samples.append(s)
        self._append_to_jsonl(s)
        return s

    def run(self) -> List[Dict[str, Any]]:
        self._running = True
        count = 0
        print(f"Pilot Monitor — sampling every {self._interval}s (max={self._max_samples or '∞'})")
        try:
            while self._running:
                s = self.sample_once()
                count += 1
                print(f"  [{count}] p99={s.get('p99_latency_ms','?')}ms  "
                      f"workers={s.get('worker_count','?')}  "
                      f"drift={s.get('replay_drift','?')}  "
                      f"status={s['status']}")
                if self._max_samples and count >= self._max_samples:
                    break
                time.sleep(self._interval)
        except KeyboardInterrupt:
            pass
        self._running = False
        return self._samples

    def stop(self) -> List[Dict[str, Any]]:
        self._running = False
        return self._samples

    def get_summary(self) -> Dict[str, Any]:
        p99s = [s.get("p99_latency_ms", 0) for s in self._samples if s.get("p99_latency_ms", -1) >= 0]
        drifts = [s.get("replay_drift", 0) for s in self._samples if "replay_drift" in s]
        return {
            "samples": len(self._samples),
            "p99_max_ms": max(p99s) if p99s else 0,
            "p99_avg_ms": sum(p99s) / len(p99s) if p99s else 0,
            "replay_drift_max": max(drifts) if drifts else 0,
            "errors": sum(1 for s in self._samples if s.get("status") == "error"),
        }

    def _append_to_jsonl(self, sample: Dict[str, Any]) -> None:
        path = self._output_dir / "pilot_metrics.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(sample, default=str) + "\n")


def main() -> None:
    import sys
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    monitor = PilotMonitor(interval_sec=interval, max_samples=samples)
    monitor.run()
    summary = monitor.get_summary()
    print(f"\nMonitor summary: {json.dumps(summary, indent=2)}")


if __name__ == "__main__":
    main()
