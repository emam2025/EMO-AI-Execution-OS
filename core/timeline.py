"""Explainability Timeline – Phase 13.

Reads from MetricsStore and reconstructs a chronological narrative of
what happened, why, and when.

Usage:
    builder = TimelineBuilder(store)
    timeline = builder.build(days=30)
    # [
    #   {"day": "2026-05-01", "event": "graph-heavy shift",
    #    "reason": "large repository detected"},
    #   {"day": "2026-05-03", "event": "rollback",
    #    "reason": "semantic precision collapse"},
    # ]
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .metrics_store import MetricsStore, EVENT_QUERY_EXECUTED

logger = logging.getLogger("emo_ai.timeline")


class TimelineBuilder:
    """Builds an explainability timeline from stored events.

    Each entry has:
        day, event, reason, severity, detail
    """

    def __init__(self, store: MetricsStore):
        self._store = store

    def build(
        self,
        days: int = 30,
        include_queries: bool = False,
    ) -> List[Dict[str, Any]]:
        """Build timeline for the last N days.

        Args:
            days: How far back to look.
            include_queries: Include query.executed events (can be noisy).

        Returns:
            Sorted list of timeline entries (oldest first).
        """
        since = time.time() - (days * 86400)
        entries: List[Dict[str, Any]] = []

        # 1. Weight changes → strategy shifts
        weight_changes = self._store.weight_change_history(since=since, limit=200)
        for wc in weight_changes:
            meta = self._safe_json(wc.get("metadata", "{}"))
            entries.append({
                "day": self._ts_to_day(wc["timestamp"]),
                "event": "weight change",
                "reason": meta.get("reason",
                                   f"Strategy adjusted: {wc.get('strategy', 'unknown')}"),
                "severity": "info",
                "detail": {
                    "strategy": wc.get("strategy"),
                    "old_weights": self._safe_json(wc.get("old_weights", "null")),
                    "new_weights": self._safe_json(wc.get("new_weights", "null")),
                },
            })

        # 2. Drift alerts
        drift_alerts = self._store.query_drift_alerts(since=since, limit=100)
        for da in drift_alerts:
            details = self._safe_json(da.get("details", "{}"))
            entries.append({
                "day": self._ts_to_day(da["timestamp"]),
                "event": f"drift: {da['drift_type']}",
                "reason": details.get("message", f"Drift alert ({da['drift_type']})"),
                "severity": da.get("severity", "warning"),
                "detail": details,
            })

        # 3. Rollback events
        rollbacks = self._store.query_rollback_events(since=since, limit=50)
        for rb in rollbacks:
            entries.append({
                "day": self._ts_to_day(rb["timestamp"]),
                "event": "rollback",
                "reason": rb.get("trigger_reason", "Unknown reason"),
                "severity": "critical",
                "detail": {
                    "previous_weights": self._safe_json(
                        rb.get("previous_weights", "null")),
                    "restored_weights": self._safe_json(
                        rb.get("restored_weights", "null")),
                },
            })

        # 4. Shadow promotions
        shadows = self._store.query_shadow_evaluations(since=since, limit=100)
        for sh in shadows:
            if sh.get("promoted", 0) == 1:
                entries.append({
                    "day": self._ts_to_day(sh["timestamp"]),
                    "event": "shadow promotion",
                    "reason": (
                        f"Candidate ({sh['candidate_score']:.3f}) "
                        f"beat baseline ({sh['baseline_score']:.3f})"
                    ),
                    "severity": "info",
                    "detail": {
                        "baseline_score": sh["baseline_score"],
                        "candidate_score": sh["candidate_score"],
                    },
                })

        # 5. Regression alerts (from metrics_events)
        regression_events = self._store.query_events(
            event_type="regression.detected", since=since, limit=50,
        )
        for re in regression_events:
            meta = self._safe_json(re.get("metadata", "{}"))
            entries.append({
                "day": self._ts_to_day(re["timestamp"]),
                "event": "regression detected",
                "reason": meta.get(
                    "message",
                    f"Performance drop for {re.get('strategy', 'unknown')}",
                ),
                "severity": "warning",
                "detail": meta,
            })

        # 6. Query volume (summarised by day + strategy)
        if include_queries:
            query_events = self._store.query_events(
                event_type=EVENT_QUERY_EXECUTED, since=since, limit=500,
            )
            day_counts: Dict[str, Dict[str, int]] = {}
            for qe in query_events:
                day = self._ts_to_day(qe["timestamp"])
                strat = qe.get("strategy", "unknown")
                day_counts.setdefault(day, {}).setdefault(strat, 0)
                day_counts[day][strat] += 1
            for day, strats in sorted(day_counts.items()):
                total = sum(strats.values())
                dominant = max(strats, key=strats.get)
                entries.append({
                    "day": day,
                    "event": f"{total} queries ({dominant}-dominant)",
                    "reason": f"Strategies: {', '.join(f'{k}={v}' for k, v in strats.items())}",
                    "severity": "info",
                    "detail": {"counts": strats, "total": total},
                })

        # Sort oldest first
        entries.sort(key=lambda e: e["day"])
        return entries

    def summarise(
        self,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Short high-level summary — one entry per meaningful event.

        Skips routine weight changes and only reports: drift, regression,
        rollback, shadow promotions.
        """
        since = time.time() - (days * 86400)
        entries: List[Dict[str, Any]] = []

        # Drift alerts
        for da in self._store.query_drift_alerts(since=since, limit=50):
            details = self._safe_json(da.get("details", "{}"))
            entries.append({
                "day": self._ts_to_day(da["timestamp"]),
                "event": f"drift: {da['drift_type']}",
                "reason": details.get("message", ""),
                "severity": da.get("severity", "warning"),
            })

        # Rollback events
        for rb in self._store.query_rollback_events(since=since, limit=50):
            entries.append({
                "day": self._ts_to_day(rb["timestamp"]),
                "event": "rollback",
                "reason": rb.get("trigger_reason", ""),
                "severity": "critical",
            })

        # Shadow promotions
        for sh in self._store.query_shadow_evaluations(since=since, limit=100):
            if sh.get("promoted", 0) == 1:
                entries.append({
                    "day": self._ts_to_day(sh["timestamp"]),
                    "event": "shadow promoted",
                    "reason": f"Candidate {sh['candidate_score']:.3f} > "
                              f"baseline {sh['baseline_score']:.3f}",
                    "severity": "info",
                })

        # Regression events
        for re in self._store.query_events(
            event_type="regression.detected", since=since, limit=50,
        ):
            meta = self._safe_json(re.get("metadata", "{}"))
            entries.append({
                "day": self._ts_to_day(re["timestamp"]),
                "event": "regression",
                "reason": meta.get("message", ""),
                "severity": "warning",
            })

        entries.sort(key=lambda e: e["day"])
        return entries

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _ts_to_day(ts: float) -> str:
        """Convert Unix timestamp to 'YYYY-MM-DD' string."""
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _safe_json(raw: str) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
