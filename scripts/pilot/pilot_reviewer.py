"""Pilot Reviewer — generates weekly review reports.  # LAW-5

Generates WEEKLY_REVIEW_REPORT.md from pilot metrics after each review session.

Ref: EXEC-DIRECTIVE-PILOT-001 §Task-3
Ref: Canon LAW 5, LAW 12
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE = Path(__file__).resolve().parent.parent.parent


class PilotReviewer:
    """Generates weekly review reports from collected pilot metrics."""

    def __init__(self, metrics_path: Optional[Path] = None) -> None:
        self._metrics_path = metrics_path or (BASE / "artifacts" / "pilot" / "pilot_metrics.jsonl")

    def load_metrics(self) -> List[Dict[str, Any]]:
        if not self._metrics_path.exists():
            return []
        with open(self._metrics_path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def compute_summary(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        p99s = [m.get("p99_latency_ms", 0) for m in metrics if m.get("p99_latency_ms", -1) >= 0]
        drifts = [m.get("replay_drift", 0) for m in metrics if "replay_drift" in m]
        healthy = [m.get("healthy_workers", -1) for m in metrics if m.get("healthy_workers", -1) >= 0]
        degraded = [m.get("degraded_workers", 0) for m in metrics if "degraded_workers" in m]
        errors = [m for m in metrics if m.get("status") == "error"]

        return {
            "total_samples": len(metrics),
            "total_error_samples": len(errors),
            "p99_max_ms": max(p99s) if p99s else 0,
            "p99_avg_ms": round(sum(p99s) / len(p99s), 2) if p99s else 0,
            "replay_drift_max": max(drifts) if drifts else 0,
            "replay_drift_avg": round(sum(drifts) / len(drifts), 4) if drifts else 0,
            "healthy_workers_avg": round(sum(healthy) / len(healthy), 1) if healthy else 0,
            "degraded_workers_max": max(degraded) if degraded else 0,
            "uptime_pct": round((len(metrics) - len(errors)) / len(metrics) * 100, 2) if metrics else 0,
        }

    def generate_report(  # LAW-5
        self,
        week_number: int,
        output_path: Optional[Path] = None,
    ) -> str:
        metrics = self.load_metrics()
        summary = self.compute_summary(metrics)

        lines = [
            f"# Weekly Pilot Review — Week {week_number}",
            "",
            f"*Generated: {datetime.now(timezone.utc).isoformat()}*",
            f"*Metrics samples: {summary['total_samples']}*",
            "",
            "## Runtime Stability",
            "",
            "| Metric | Value | Threshold | Status |",
            "|--------|-------|-----------|--------|",
            f"| P99 Latency (max) | {summary['p99_max_ms']}ms | ≤ 2000ms | {'🟢 PASS' if summary['p99_max_ms'] <= 2000 else '🔴 FAIL'} |",
            f"| P99 Latency (avg) | {summary['p99_avg_ms']}ms | ≤ 1000ms | {'🟢 PASS' if summary['p99_avg_ms'] <= 1000 else '🔴 FAIL'} |",
            f"| Replay Drift (max) | {summary['replay_drift_max']} | ≤ 0.02 | {'🟢 PASS' if summary['replay_drift_max'] <= 0.02 else '🔴 FAIL'} |",
            f"| Healthy Workers (avg) | {summary['healthy_workers_avg']} | ≥ 2 | {'🟢 PASS' if summary['healthy_workers_avg'] >= 2 else '🔴 FAIL'} |",
            f"| Uptime | {summary['uptime_pct']}% | ≥ 99% | {'🟢 PASS' if summary['uptime_pct'] >= 99 else '🔴 FAIL'} |",
            "",
            "## Known Usability Frictions",
            "",
            "*To be filled after review session*",
            "",
            "## Action Items",
            "",
            "1. ",
            "2. ",
            "3. ",
            "",
            "---",
            f"*Week {week_number} review complete*",
            "",
        ]

        report = "\n".join(lines)

        out = output_path or (BASE / "artifacts" / "pilot" / f"WEEKLY_REVIEW_WEEK_{week_number}.md")
        with open(out, "w") as f:
            f.write(report)

        return report


def main() -> None:
    import sys
    week = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    reviewer = PilotReviewer()
    report = reviewer.generate_report(week_number=week)
    print(report[:500] + "\n...")


if __name__ == "__main__":
    main()
