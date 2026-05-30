"""Phase G2 — Runtime Reviewer.  # LAW-12 RULE-1

Concrete implementation of IRuntimeReviewer.

Observes execution latency, detects resource leaks, flags determinism
violations, and suggests optimizations. All outputs are deterministic.

Ref: Canon LAW 12, RULE 1
Ref: artifacts/design/g2/protocols/01_critic_protocols.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.runtime.models.critic_models import (
    ReviewSignal,
    RuntimeReviewSnapshot,
)

logger = logging.getLogger("emo_ai.critic.runtime_reviewer")


class RuntimeReviewer:  # LAW-12 RULE-1
    """Reviews runtime execution health and flags violations.

    All review outputs are deterministic (RULE 1) — same inputs
    always produce the same outputs.
    """

    def observe_execution_latency(  # RULE-1
        self,
        execution_trace: List[Dict[str, Any]],
        threshold_ms: float = 1000.0,
    ) -> Dict[str, Any]:
        if not execution_trace:
            return {
                "max_latency": 0.0,
                "p95_latency": 0.0,
                "slowest_node": "",
                "threshold_breached": False,
            }

        latencies = []
        slowest_node = ""
        max_lat = 0.0

        for span in execution_trace:
            if isinstance(span, dict):
                dur = span.get("duration_ms", 0.0) or 0.0
                latencies.append(dur)
                if dur > max_lat:
                    max_lat = dur
                    slowest_node = span.get("node_id", "")

        latencies.sort()
        n = len(latencies)
        p95_idx = max(0, int(n * 0.95) - 1)
        p95 = latencies[p95_idx] if latencies else 0.0

        return {
            "max_latency": max_lat,
            "p95_latency": p95,
            "slowest_node": slowest_node,
            "threshold_breached": max_lat > threshold_ms,
        }

    def detect_resource_leak(  # LAW-12
        self,
        worker_snapshots: List[Dict[str, Any]],
        threshold_delta: float = 0.15,
    ) -> Dict[str, Any]:
        if len(worker_snapshots) < 2:
            return {
                "leak_detected": False,
                "affected_workers": [],
                "delta_percent": 0.0,
                "estimated_leak_bytes": 0,
            }

        first = worker_snapshots[0] if worker_snapshots else {}
        last = worker_snapshots[-1] if worker_snapshots else {}

        def _mem(snap: Dict) -> float:
            return float(snap.get("memory_bytes", 0))

        first_mem = _mem(first)
        last_mem = _mem(last)
        delta = last_mem - first_mem
        delta_pct = delta / max(first_mem, 1.0)

        return {
            "leak_detected": delta_pct > threshold_delta,
            "affected_workers": [first.get("worker_id", "")] if delta_pct > threshold_delta else [],
            "delta_percent": round(delta_pct * 100, 2),
            "estimated_leak_bytes": max(0, int(delta)),
        }

    def flag_determinism_violation(  # RULE-1
        self,
        expected_hash: str,
        actual_hash: str,
        execution_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        mismatch = expected_hash != actual_hash
        return {
            "violation_detected": mismatch,
            "hash_mismatch": actual_hash if mismatch else "",
            "context_snapshot": {
                "worker_id": execution_context.get("worker_id", ""),
                "plan_ids": execution_context.get("plan_ids", []),
            },
        }

    def suggest_optimization(  # RULE-1
        self,
        plan: Dict[str, Any],
        trace: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        if not trace:
            return suggestions

        trace_map: Dict[str, List[float]] = {}
        for span in trace:
            if isinstance(span, dict):
                nid = span.get("node_id", "")
                dur = span.get("duration_ms", 0.0) or 0.0
                if nid not in trace_map:
                    trace_map[nid] = []
                trace_map[nid].append(dur)

        for nid, durs in trace_map.items():
            avg = sum(durs) / len(durs)
            if avg > 500:
                suggestions.append({
                    "node_id": nid,
                    "current_cost": round(avg, 2),
                    "estimated_improvement": round(avg * 0.3, 2),
                    "suggestion_type": "optimize_node",
                })

        suggestions.sort(key=lambda s: s.get("current_cost", 0), reverse=True)
        return suggestions[:5]

    def review(  # LAW-12
        self,
        review_context: Dict[str, Any],
        critic_trace_id: str = "",
    ) -> RuntimeReviewSnapshot:
        execution_trace = review_context.get("execution_trace", [])
        worker_snapshots = review_context.get("worker_snapshots", [])
        expected_hash = review_context.get("determinism_hash", "")
        actual_hash = review_context.get("actual_hash", expected_hash)
        plan_ids = review_context.get("plan_ids", [])

        latency = self.observe_execution_latency(execution_trace)
        leak = self.detect_resource_leak(worker_snapshots)
        determinism = self.flag_determinism_violation(expected_hash, actual_hash, review_context)

        signal = ReviewSignal.APPROVE
        if determinism["violation_detected"]:
            signal = ReviewSignal.REJECT_PLAN
        elif latency["threshold_breached"]:
            signal = ReviewSignal.OPTIMIZE_RUNTIME
        elif leak["leak_detected"]:
            signal = ReviewSignal.CORRECT

        suggestions = self.suggest_optimization(
            review_context.get("plan", {}),
            execution_trace,
        )

        return RuntimeReviewSnapshot(
            plan_ids=plan_ids,
            critic_trace_id=critic_trace_id,
            signal=signal,
            max_latency_ms=latency["max_latency"],
            p95_latency_ms=latency["p95_latency"],
            slowest_node=latency["slowest_node"],
            resource_leak_detected=leak["leak_detected"],
            determinism_violation_detected=determinism["violation_detected"],
            optimization_suggestions=suggestions,
        )
