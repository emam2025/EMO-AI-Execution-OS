"""F4 — FailureExplorer: failure analysis and pattern detection.

Analyzes execution failures to identify:
  - Most common failure patterns
  - Failing services / workers / nodes
  - Failure cascades
  - Retry effectiveness
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.observability.failure_explorer")


@dataclass
class FailureRecord:
    execution_id: str
    timestamp: float
    service: str = ""
    worker_id: str = ""
    node_id: str = ""
    error: str = ""
    error_type: str = "unknown"
    retry_count: int = 0
    duration_ms: float = 0.0
    recovered: bool = False
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class FailurePattern:
    pattern_id: str
    error_substring: str
    count: int = 0
    services: Counter = field(default_factory=Counter)
    workers: Counter = field(default_factory=Counter)
    nodes: Counter = field(default_factory=Counter)
    avg_retries: float = 0.0
    recovery_rate: float = 0.0


class FailureExplorer:
    """Analyzes execution failures and identifies patterns.

    Stores failure records and provides aggregate analysis.
    """

    def __init__(self, max_records: int = 5000):
        self._records: List[FailureRecord] = []
        self._max_records = max_records

    def record_failure(self, execution_id: str, error: str,
                       service: str = "", worker_id: str = "",
                       node_id: str = "", error_type: str = "unknown",
                       retry_count: int = 0, duration_ms: float = 0.0,
                       recovered: bool = False,
                       tags: Optional[Dict[str, str]] = None) -> FailureRecord:
        self._evict_if_needed()
        record = FailureRecord(
            execution_id=execution_id,
            timestamp=time.time(),
            service=service,
            worker_id=worker_id,
            node_id=node_id,
            error=error,
            error_type=error_type,
            retry_count=retry_count,
            duration_ms=duration_ms,
            recovered=recovered,
            tags=tags or {},
        )
        self._records.append(record)
        return record

    # ── Analysis ──────────────────────────────────────────────

    def top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Most common error messages."""
        counter: Counter = Counter(r.error for r in self._records)
        return [{"error": err, "count": c} for err, c in counter.most_common(limit)]

    def top_error_types(self, limit: int = 10) -> List[Dict[str, Any]]:
        counter: Counter = Counter(r.error_type for r in self._records)
        return [{"type": t, "count": c} for t, c in counter.most_common(limit)]

    def top_failing_services(self, limit: int = 10) -> List[Dict[str, Any]]:
        counter: Counter = Counter(r.service for r in self._records)
        return [{"service": s, "failures": c} for s, c in counter.most_common(limit)]

    def top_failing_workers(self, limit: int = 10) -> List[Dict[str, Any]]:
        counter: Counter = Counter(r.worker_id for r in self._records if r.worker_id)
        return [{"worker": w, "failures": c} for w, c in counter.most_common(limit)]

    def top_failing_nodes(self, limit: int = 10) -> List[Dict[str, Any]]:
        counter: Counter = Counter(r.node_id for r in self._records if r.node_id)
        return [{"node": n, "failures": c} for n, c in counter.most_common(limit)]

    def failure_patterns(self, min_count: int = 2) -> List[FailurePattern]:
        """Find common patterns by grouping similar error messages."""
        substrings: Dict[str, List[FailureRecord]] = defaultdict(list)

        common_patterns = [
            "timeout", "connection refused", "connection reset",
            "out of memory", "out of disk", "permission denied",
            "not found", "already exists", "quota exceeded",
            "rate limit", "unavailable", "internal error",
            "cancelled", "killed", "segfault", "bus error",
        ]

        for rec in self._records:
            err_lower = rec.error.lower()
            for pattern in common_patterns:
                if pattern in err_lower:
                    substrings[pattern].append(rec)
                    break

        patterns: List[FailurePattern] = []
        for substr, records in substrings.items():
            if len(records) < min_count:
                continue
            services: Counter = Counter(r.service for r in records)
            workers: Counter = Counter(r.worker_id for r in records if r.worker_id)
            nodes: Counter = Counter(r.node_id for r in records if r.node_id)
            avg_retries = sum(r.retry_count for r in records) / len(records)
            recovery_rate = sum(1 for r in records if r.recovered) / len(records)

            patterns.append(FailurePattern(
                pattern_id=substr,
                error_substring=substr,
                count=len(records),
                services=services,
                workers=workers,
                nodes=nodes,
                avg_retries=avg_retries,
                recovery_rate=recovery_rate,
            ))

        patterns.sort(key=lambda p: p.count, reverse=True)
        return patterns

    def failure_trend(self, minutes: int = 30) -> Dict[str, Any]:
        """Show failure rate trend over the last N minutes."""
        cutoff = time.time() - (minutes * 60)
        recent = [r for r in self._records if r.timestamp >= cutoff]
        window = minutes / 5
        buckets: List[Dict[str, Any]] = []
        for i in range(int(window)):
            start = cutoff + (i * 300)
            end = start + 300
            bucket = [r for r in recent if start <= r.timestamp < end]
            recovered = sum(1 for r in bucket if r.recovered)
            buckets.append({
                "window": f"{i*5}-{(i+1)*5}m",
                "failures": len(bucket),
                "recovered": recovered,
                "recovery_rate": recovered / len(bucket) if bucket else 1.0,
            })

        return {
            "total_failures": len(recent),
            "unique_errors": len(set(r.error for r in recent)),
            "trend": buckets,
        }

    def cascade_analysis(self, window_seconds: float = 60.0) -> List[Dict[str, Any]]:
        """Detect failure cascades: failures that trigger other failures."""
        cascades: List[Dict[str, Any]] = []
        sorted_records = sorted(self._records, key=lambda r: r.timestamp)

        for i, rec in enumerate(sorted_records):
            if not rec.node_id:
                continue
            followers = [
                r for r in sorted_records[i + 1:]
                if r.node_id == rec.node_id
                and r.timestamp - rec.timestamp <= window_seconds
                and r.execution_id != rec.execution_id
            ]
            if followers:
                cascades.append({
                    "trigger": rec.execution_id,
                    "trigger_error": rec.error[:100],
                    "node_id": rec.node_id,
                    "timestamp": rec.timestamp,
                    "affected": len(followers),
                    "affected_ids": [f.execution_id for f in followers],
                })

        cascades.sort(key=lambda c: c["affected"], reverse=True)
        return cascades[:20]

    def retry_effectiveness(self) -> Dict[str, Any]:
        """Analyze how effective retries are."""
        retried = [r for r in self._records if r.retry_count > 0]
        recovered = [r for r in retried if r.recovered]
        return {
            "total_retried": len(retried),
            "recovered_after_retry": len(recovered),
            "effectiveness": len(recovered) / len(retried) * 100 if retried else 0.0,
            "avg_retries": sum(r.retry_count for r in retried) / len(retried) if retried else 0.0,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "total_failures": len(self._records),
            "unique_errors": len(set(r.error for r in self._records)),
            "recovery_rate": sum(1 for r in self._records if r.recovered) / len(self._records) * 100 if self._records else 0.0,
            "top_errors": self.top_errors(5),
            "top_services": self.top_failing_services(5),
            "top_nodes": self.top_failing_nodes(5),
            "retry_effectiveness": self.retry_effectiveness(),
        }

    def _evict_if_needed(self) -> None:
        if len(self._records) >= self._max_records:
            self._records = self._records[-self._max_records // 2:]

    def clear(self) -> None:
        self._records.clear()
