"""Event-sourced Metrics Store – Phase 13 Telemetry Layer.

Every operation in the self-tuning system emits an event.  Analytics,
timelines, dashboards, and explainability all derive from this single
source of truth.

Architecture:
    HybridRetriever ─┐
    AdaptiveWeight ──┤→ MetricsStore → SQLite (metrics.db)
    Guardrails ──────┘         ↓
                         TimelineBuilder
                         QueryAnalytics
                         LiveDashboard

Event Taxonomy:
    Event                  Purpose
    ───────────────────    ─────────────────────────────────
    query.executed         Any retrieval query
    retrieval.completed    Retrieval results produced
    ranking.adjusted       Adaptive weight changed
    drift.detected         Drift alert fired
    regression.detected    Performance regression detected
    rollback.executed      Rollback was triggered
    shadow.promoted        Shadow candidate promoted
    feedback.received      User/system feedback recorded
    weight.change          W_eight profile changed

Schema:
    metrics_events (central event store)
    drift_alerts
    rollback_events
    shadow_evaluations
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.metrics_store")

_DEFAULT_DB = str(Path(".ai") / "index" / "metrics.db")


# ======================================================================
# Event Taxonomy – fixed string constants
# ======================================================================

EVENT_QUERY_EXECUTED = "query.executed"
EVENT_RETRIEVAL_COMPLETED = "retrieval.completed"
EVENT_RANKING_ADJUSTED = "ranking.adjusted"
EVENT_DRIFT_DETECTED = "drift.detected"
EVENT_REGRESSION_DETECTED = "regression.detected"
EVENT_ROLLBACK_EXECUTED = "rollback.executed"
EVENT_SHADOW_PROMOTED = "shadow.promoted"
EVENT_FEEDBACK_RECEIVED = "feedback.received"
EVENT_WEIGHT_CHANGE = "weight.change"


# ======================================================================
# MetricsStore
# ======================================================================

class MetricsStore:
    """Event-sourced telemetry store.

    All writes are append-only events.  Read-side queries derive state
    from the event stream.

    Usage:
        store = MetricsStore()
        store.record_event("query.executed", query="find auth")
        events = store.query_events(event_type="query.executed", limit=10)
    """

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    # ═══════════════════════════════════════════════════════════════════
    # Event recording
    # ═══════════════════════════════════════════════════════════════════

    def record_event(
        self,
        event_type: str,
        query_id: Optional[str] = None,
        symbol_id: Optional[str] = None,
        strategy: Optional[str] = None,
        old_weights: Optional[Tuple[float, float]] = None,
        new_weights: Optional[Tuple[float, float]] = None,
        score_before: Optional[float] = None,
        score_after: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record an event in the central event store.

        Returns the event ID.
        """
        eid = self._insert_event(
            event_type=event_type,
            query_id=query_id,
            symbol_id=symbol_id,
            strategy=strategy,
            old_weights=json.dumps(old_weights) if old_weights else None,
            new_weights=json.dumps(new_weights) if new_weights else None,
            score_before=score_before,
            score_after=score_after,
            metadata=json.dumps(metadata) if metadata else None,
        )
        logger.debug("Recorded event %s (id=%d)", event_type, eid)
        return eid

    def record_drift_alert(
        self,
        drift_type: str,
        severity: str,
        details: Dict[str, Any],
    ) -> int:
        """Record a drift alert."""
        aid = self._insert_drift_alert(drift_type, severity, json.dumps(details))
        logger.info("Drift alert: %s (%s)", drift_type, severity)
        return aid

    def record_rollback(
        self,
        trigger_reason: str,
        previous_weights: Tuple[float, float],
        restored_weights: Tuple[float, float],
    ) -> int:
        """Record a rollback event."""
        rid = self._insert_rollback(
            trigger_reason,
            json.dumps(previous_weights),
            json.dumps(restored_weights),
        )
        logger.warning("Rollback recorded: %s", trigger_reason)
        return rid

    def record_shadow_evaluation(
        self,
        baseline_score: float,
        candidate_score: float,
        promoted: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record a shadow evaluation result."""
        sid = self._insert_shadow_evaluation(
            baseline_score, candidate_score,
            1 if promoted else 0,
            json.dumps(metadata) if metadata else None,
        )
        return sid

    # ═══════════════════════════════════════════════════════════════════
    # Read / Query
    # ═══════════════════════════════════════════════════════════════════

    def query_events(
        self,
        event_type: Optional[str] = None,
        strategy: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query central events with optional filters."""
        rows = self._fetch_events(event_type, strategy, since, limit)
        return [self._row_to_dict(r) for r in rows]

    def query_drift_alerts(
        self, since: Optional[float] = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_drift_alerts(since, limit)
        return [self._row_to_dict(r) for r in rows]

    def query_rollback_events(
        self, since: Optional[float] = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_rollbacks(since, limit)
        return [self._row_to_dict(r) for r in rows]

    def query_shadow_evaluations(
        self, since: Optional[float] = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_shadow_evaluations(since, limit)
        return [self._row_to_dict(r) for r in rows]

    # ── Aggregation helpers ──────────────────────────────────────────────

    def strategy_usage(self, since: Optional[float] = None) -> Dict[str, int]:
        """Count how many queries used each strategy."""
        return self._aggregate_strategy_usage(since)

    def weight_change_history(
        self, since: Optional[float] = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return ordered list of weight changes (ranking.adjusted + weight.change)."""
        rows = self._fetch_weight_changes(since, limit)
        return [self._row_to_dict(r) for r in rows]

    def rollback_count(self, since: Optional[float] = None) -> int:
        return self._count_rollbacks(since)

    def drift_alert_count(self, since: Optional[float] = None) -> int:
        return self._count_drift_alerts(since)

    def shadow_win_rate(self) -> float:
        """Fraction of shadow evaluations where candidate won."""
        return self._shadow_win_rate()

    def clear(self) -> None:
        """Delete all records (testing)."""
        with self._lock:
            conn = self._connect()
            try:
                for table in ("metrics_events", "drift_alerts", "rollback_events",
                              "shadow_evaluations"):
                    conn.execute(f"DELETE FROM {table}")
                conn.commit()
            finally:
                conn.close()

    # ═══════════════════════════════════════════════════════════════════
    # Schema & internals
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS metrics_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        event_type TEXT NOT NULL,
                        query_id TEXT,
                        symbol_id TEXT,
                        strategy TEXT,
                        old_weights TEXT,
                        new_weights TEXT,
                        score_before REAL,
                        score_after REAL,
                        metadata TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS drift_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        drift_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        details TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS rollback_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        trigger_reason TEXT NOT NULL,
                        previous_weights TEXT,
                        restored_weights TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS shadow_evaluations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        baseline_score REAL NOT NULL,
                        candidate_score REAL NOT NULL,
                        promoted INTEGER DEFAULT 0,
                        metadata TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_type
                    ON metrics_events(event_type)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_strategy
                    ON metrics_events(strategy)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_ts
                    ON metrics_events(timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_drift_ts
                    ON drift_alerts(timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_rollback_ts
                    ON rollback_events(timestamp)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_shadow_ts
                    ON shadow_evaluations(timestamp)
                """)
                conn.commit()
            finally:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── inserts ──────────────────────────────────────────────────────────

    def _insert_event(self, **kw) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """INSERT INTO metrics_events
                       (timestamp, event_type, query_id, symbol_id, strategy,
                        old_weights, new_weights, score_before, score_after, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        time.time(), kw["event_type"],
                        kw.get("query_id"), kw.get("symbol_id"),
                        kw.get("strategy"), kw.get("old_weights"),
                        kw.get("new_weights"), kw.get("score_before"),
                        kw.get("score_after"), kw.get("metadata"),
                    ),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def _insert_drift_alert(self, drift_type: str, severity: str,
                             details: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO drift_alerts (timestamp, drift_type, severity, details)"
                    " VALUES (?, ?, ?, ?)",
                    (time.time(), drift_type, severity, details),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def _insert_rollback(self, reason: str, prev: str, restored: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO rollback_events (timestamp, trigger_reason, "
                    "previous_weights, restored_weights) VALUES (?, ?, ?, ?)",
                    (time.time(), reason, prev, restored),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def _insert_shadow_evaluation(
        self, baseline: float, candidate: float,
        promoted: int, metadata: Optional[str],
    ) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO shadow_evaluations (timestamp, baseline_score, "
                    "candidate_score, promoted, metadata) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), baseline, candidate, promoted, metadata),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    # ── fetches ──────────────────────────────────────────────────────────

    def _fetch_events(self, event_type: Optional[str] = None,
                      strategy: Optional[str] = None,
                      since: Optional[float] = None,
                      limit: int = 100) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                parts = ["SELECT * FROM metrics_events WHERE 1=1"]
                params = []
                if event_type:
                    parts.append("AND event_type = ?")
                    params.append(event_type)
                if strategy:
                    parts.append("AND strategy = ?")
                    params.append(strategy)
                if since is not None:
                    parts.append("AND timestamp >= ?")
                    params.append(since)
                parts.append("ORDER BY timestamp DESC LIMIT ?")
                params.append(limit)
                return conn.execute(" ".join(parts), params).fetchall()
            finally:
                conn.close()

    def _fetch_drift_alerts(self, since: Optional[float],
                             limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                if since is not None:
                    return conn.execute(
                        "SELECT * FROM drift_alerts WHERE timestamp >= ?"
                        " ORDER BY timestamp DESC LIMIT ?",
                        (since, limit),
                    ).fetchall()
                return conn.execute(
                    "SELECT * FROM drift_alerts ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            finally:
                conn.close()

    def _fetch_rollbacks(self, since: Optional[float],
                          limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                if since is not None:
                    return conn.execute(
                        "SELECT * FROM rollback_events WHERE timestamp >= ?"
                        " ORDER BY timestamp DESC LIMIT ?",
                        (since, limit),
                    ).fetchall()
                return conn.execute(
                    "SELECT * FROM rollback_events ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            finally:
                conn.close()

    def _fetch_shadow_evaluations(self, since: Optional[float],
                                   limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                if since is not None:
                    return conn.execute(
                        "SELECT * FROM shadow_evaluations WHERE timestamp >= ?"
                        " ORDER BY timestamp DESC LIMIT ?",
                        (since, limit),
                    ).fetchall()
                return conn.execute(
                    "SELECT * FROM shadow_evaluations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            finally:
                conn.close()

    def _fetch_weight_changes(self, since: Optional[float],
                               limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                parts = [
                    "SELECT * FROM metrics_events"
                    " WHERE event_type IN (?, ?)"
                ]
                params = [EVENT_RANKING_ADJUSTED, EVENT_WEIGHT_CHANGE]
                if since is not None:
                    parts.append("AND timestamp >= ?")
                    params.append(since)
                parts.append("ORDER BY timestamp DESC LIMIT ?")
                params.append(limit)
                return conn.execute(" ".join(parts), params).fetchall()
            finally:
                conn.close()

    # ── aggregations ─────────────────────────────────────────────────────

    def _aggregate_strategy_usage(self, since: Optional[float]) -> Dict[str, int]:
        with self._lock:
            conn = self._connect()
            try:
                if since is not None:
                    rows = conn.execute(
                        "SELECT strategy, COUNT(*) as cnt FROM metrics_events"
                        " WHERE event_type = ? AND timestamp >= ?"
                        " AND strategy IS NOT NULL"
                        " GROUP BY strategy ORDER BY cnt DESC",
                        (EVENT_QUERY_EXECUTED, since),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT strategy, COUNT(*) as cnt FROM metrics_events"
                        " WHERE event_type = ? AND strategy IS NOT NULL"
                        " GROUP BY strategy ORDER BY cnt DESC",
                        (EVENT_QUERY_EXECUTED,),
                    ).fetchall()
                return {r["strategy"]: r["cnt"] for r in rows}
            finally:
                conn.close()

    def _count_rollbacks(self, since: Optional[float]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                if since is not None:
                    return conn.execute(
                        "SELECT COUNT(*) FROM rollback_events WHERE timestamp >= ?",
                        (since,),
                    ).fetchone()[0]
                return conn.execute(
                    "SELECT COUNT(*) FROM rollback_events",
                ).fetchone()[0]
            finally:
                conn.close()

    def _count_drift_alerts(self, since: Optional[float]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                if since is not None:
                    return conn.execute(
                        "SELECT COUNT(*) FROM drift_alerts WHERE timestamp >= ?",
                        (since,),
                    ).fetchone()[0]
                return conn.execute(
                    "SELECT COUNT(*) FROM drift_alerts",
                ).fetchone()[0]
            finally:
                conn.close()

    def _shadow_win_rate(self) -> float:
        with self._lock:
            conn = self._connect()
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM shadow_evaluations"
                ).fetchone()[0]
                if total == 0:
                    return 0.0
                wins = conn.execute(
                    "SELECT COUNT(*) FROM shadow_evaluations"
                    " WHERE candidate_score > baseline_score"
                ).fetchone()[0]
                return wins / total
            finally:
                conn.close()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)
