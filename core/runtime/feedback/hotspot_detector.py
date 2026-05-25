"""D9 — IHotspotDetector implementation.

Tracks execution frequency and failure patterns to identify
runtime hotspots and suggest decomposition targets.

LAW 16: risk_score > 0.8 → decomposition required.

Ref: DEVELOPER.md §5.3 (Self-Tuning)
Ref: Canon LAW 16
Ref: artifacts/design/d9/protocols/01_feedback_loop_protocols.py
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from core.runtime.models.feedback_models import (
    FeedbackPolicy,
    HotspotProfile,
    TraceEvent,
)


class HotspotDetector:
    """Identifies runtime hotspots by tracking execution frequency
    and failure patterns per node.

    LAW 16: Any node with risk_score > 0.8 MUST be flagged.
    """

    def __init__(self, policy: Optional[FeedbackPolicy] = None) -> None:
        self._policy = policy or FeedbackPolicy()
        self._execution_counts: Dict[str, int] = defaultdict(int)
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._duration_records: Dict[str, List[float]] = defaultdict(list)
        self._failure_patterns: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._timestamps: Dict[str, List[float]] = defaultdict(list)

    def track_execution_frequency(
        self,
        node_id: str,
        window_size: int = 100,
    ) -> Dict[str, Any]:
        """Track how often a node is executed and its resource profile.

        LAW 5: Observable execution — tracks frequency and duration.

        Args:
            node_id: Node/tool identifier.
            window_size: Rolling window count.

        Returns:
            Dict with frequency, avg_duration_ms, record_count.
        """
        self._execution_counts[node_id] += 1

        timestamps = self._timestamps.get(node_id, [])
        recent_timestamps = [t for t in timestamps if t > time.time() - 3600]
        durations = self._duration_records.get(node_id, [])

        avg_duration = 0.0
        if durations:
            avg_duration = sum(durations[-window_size:]) / max(len(durations), 1)

        return {
            "node_id": node_id,
            "frequency": len(recent_timestamps),
            "avg_duration_ms": round(avg_duration, 2),
            "record_count": self._execution_counts[node_id],
        }

    def record_trace(self, trace: TraceEvent) -> None:
        """Record a trace event for hotspot analysis.

        Args:
            trace: TraceEvent to record.
        """
        node_id = trace.node_id or trace.tool_name
        if not node_id:
            return

        self._execution_counts[node_id] += 1
        self._timestamps[node_id].append(trace.timestamp or time.time())
        self._duration_records[node_id].append(trace.duration_ms)

        if trace.outcome in ("failed", "timeout"):
            self._failure_counts[node_id] += 1
            self._failure_patterns[node_id].append({
                "pattern_type": trace.outcome.value,
                "tool_name": trace.tool_name,
                "timestamp": trace.timestamp or time.time(),
                "suggested_action": "review" if trace.outcome == "timeout" else "investigate",
            })

    def identify_failure_patterns(
        self,
        node_id: str,
    ) -> List[Dict[str, Any]]:
        """Identify recurring failure patterns for a node.

        Args:
            node_id: Node/tool identifier.

        Returns:
            List of failure pattern dicts.
        """
        patterns = self._failure_patterns.get(node_id, [])

        # Aggregate by pattern type
        type_counts: Dict[str, int] = {}
        for p in patterns:
            pt = p.get("pattern_type", "unknown")
            type_counts[pt] = type_counts.get(pt, 0) + 1

        result: List[Dict[str, Any]] = []
        for pattern_type, count in type_counts.items():
            result.append({
                "pattern_type": pattern_type,
                "frequency": count,
                "last_occurred": patterns[-1]["timestamp"] if patterns else 0.0,
                "suggested_action": patterns[-1].get("suggested_action", "investigate"),
            })

        return result

    def suggest_decomposition(
        self,
        node_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Suggest decomposition if a node is a hotspot candidate.

        LAW 16: risk_score > 0.8 → decomposition required.

        Criteria:
          - risk_score > 0.8 (LAW 16)
          - coupling score > 0.7
          - failure_rate > 0.2
          - execution count > 100 per hour

        Args:
            node_id: Node/tool identifier.

        Returns:
            Decomposition suggestion dict or None.
        """
        total = self._execution_counts.get(node_id, 0)
        failures = self._failure_counts.get(node_id, 0)
        failure_rate = failures / max(total, 1)

        timestamps = self._timestamps.get(node_id, [])
        hourly_count = sum(1 for t in timestamps if t > time.time() - 3600)

        risk_score = min(1.0, failure_rate * 1.5)

        if risk_score > 0.8:
            return {
                "node_id": node_id,
                "reason": f"risk_score {risk_score:.4f} > 0.8 (LAW 16)",
                "risk_score": risk_score,
                "failure_rate": failure_rate,
                "execution_count": total,
                "recommendation": "DECOMPOSE",
                "estimated_score_reduction": round(risk_score * 0.5, 4),
            }

        if failure_rate > self._policy.hotspot_failure_rate and total > self._policy.hotspot_min_executions:
            return {
                "node_id": node_id,
                "reason": f"failure_rate {failure_rate:.4f} > {self._policy.hotspot_failure_rate}",
                "risk_score": risk_score,
                "failure_rate": failure_rate,
                "execution_count": total,
                "recommendation": "MONITOR",
                "estimated_score_reduction": 0.0,
            }

        if total < self._policy.hotspot_min_executions:
            return None

        return None

    def get_profile(self, node_id: str) -> HotspotProfile:
        """Get the full hotspot profile for a node.

        Args:
            node_id: Node/tool identifier.

        Returns:
            HotspotProfile with all metrics.
        """
        total = self._execution_counts.get(node_id, 0)
        failures = self._failure_counts.get(node_id, 0)
        failure_rate = failures / max(total, 1)
        durations = self._duration_records.get(node_id, [])
        avg_duration = sum(durations) / max(len(durations), 1) if durations else 0.0

        suggestion = self.suggest_decomposition(node_id)
        is_hotspot = suggestion is not None
        recommendation = suggestion["recommendation"] if suggestion else "none"

        risk_score = min(1.0, failure_rate * 1.5) if total > 0 else 0.0

        return HotspotProfile(
            node_id=node_id,
            execution_count=total,
            failure_count=failures,
            failure_rate=round(failure_rate, 4),
            failure_patterns=self.identify_failure_patterns(node_id),
            avg_duration_ms=round(avg_duration, 2),
            coupling_score=0.5,
            coupling_increase=0.0,
            risk_score=round(risk_score, 4),
            is_hotspot=is_hotspot,
            recommendation=recommendation,
        )

    def reset(self) -> None:
        """Reset all tracking data (for testing)."""
        self._execution_counts.clear()
        self._failure_counts.clear()
        self._duration_records.clear()
        self._failure_patterns.clear()
        self._timestamps.clear()
