"""Query Replay System – Phase 11 Self-Tuning Layer.

Stores every query + ranked results + weights used + feedback for later
analysis, replay, and comparison across system changes.

Architecture:
    HybridRetriever → QueryReplay → SQLite / JSONL
                            ↓
                     AdaptiveWeightEngine ← FeedbackLoop

Schema (SQLite):
    query_logs (
        id TEXT PRIMARY KEY,
        query TEXT,
        results TEXT,        -- JSON array of top-K results
        source TEXT,         -- "graph" | "semantic" | "hybrid"
        weights TEXT,        -- JSON of weights_used dict
        context TEXT,        -- JSON of repo/file context
        feedback REAL,       -- 0.0-1.0 feedback score
        strategy TEXT,       -- weight profile name
        success INTEGER,     -- 0/1 whether top-1 was accepted
        timestamp REAL
    )
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.query_replay")

_DEFAULT_DB = str(Path(".ai") / "index" / "query_logs.db")


@dataclass
class QueryLog:
    """Immutable record of a single retrieval query."""

    query_id: str = ""
    text: str = ""
    timestamp: float = 0.0
    results: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "hybrid"
    weights_used: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    feedback: Optional[float] = None
    strategy: str = "balanced"
    success: int = 0  # 0=unknown, 1=success, -1=failure


class QueryReplay:
    """Persistent query log store with replay capabilities.

    Usage:
        replay = QueryReplay()
        replay.log(query_text, results, weights, strategy="balanced")
        entry = replay.replay("some-uuid")
        history = replay.find_similar("auth login")
    """

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    # ── public API ──────────────────────────────────────────────────────

    def log(
        self,
        query: str,
        results: List[Dict[str, Any]],
        weights_used: Dict[str, Any],
        source: str = "hybrid",
        strategy: str = "balanced",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist a query execution record.

        Returns the query_id.
        """
        qid = str(uuid.uuid4())
        entry = QueryLog(
            query_id=qid,
            text=query,
            timestamp=time.time(),
            results=results,
            source=source,
            weights_used=weights_used,
            context=context or {},
            strategy=strategy,
        )
        self._insert(entry)
        logger.debug("Logged query %s: %s", qid[:8], query[:60])
        return qid

    def replay(self, query_id: str) -> Optional[QueryLog]:
        """Load a single query log by ID."""
        row = self._fetch_one(query_id)
        if row is None:
            return None
        return self._row_to_log(row)

    def find_similar(
        self,
        query_text: str,
        limit: int = 10,
    ) -> List[QueryLog]:
        """Find queries whose text contains the given keywords.

        Simple LIKE-based search.  In production, replace with embedding
        similarity search.
        """
        rows = self._fetch_similar(query_text, limit)
        return [self._row_to_log(r) for r in rows]

    def recent(self, n: int = 20) -> List[QueryLog]:
        """Return the *n* most recent query logs."""
        rows = self._fetch_recent(n)
        return [self._row_to_log(r) for r in rows]

    def update_feedback(
        self,
        query_id: str,
        feedback: float,
        success: Optional[int] = None,
    ) -> None:
        """Attach user/agent feedback to a previously logged query."""
        self._update_feedback(query_id, feedback, success)

    def compare_runs(
        self,
        query_text: str,
    ) -> Dict[str, Any]:
        """Compare the most recent two runs for the same query.

        Returns a dict with:
            previous_results, current_results, score_delta, weight_changes.
        """
        similar = self.find_similar(query_text, limit=2)
        if len(similar) < 2:
            return {
                "query": query_text,
                "previous_results": [],
                "current_results": [],
                "score_delta": 0.0,
                "note": "Need at least 2 runs for comparison.",
            }

        # similar is DESC by time: [0]=newest, [1]=oldest
        curr, prev = similar[0], similar[1]
        prev_top = prev.results[0] if prev.results else {}
        curr_top = curr.results[0] if curr.results else {}
        score_delta = (curr_top.get("score", 0) if isinstance(curr_top, dict) else 0) \
                      - (prev_top.get("score", 0) if isinstance(prev_top, dict) else 0)

        return {
            "query": query_text,
            "previous_strategy": prev.strategy,
            "current_strategy": curr.strategy,
            "previous_top": prev_top,
            "current_top": curr_top,
            "score_delta": round(score_delta, 4),
            "previous_weights": prev.weights_used,
            "current_weights": curr.weights_used,
        }

    def clear(self) -> None:
        """Delete all logged queries (for testing)."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM query_logs")
                conn.commit()
            finally:
                conn.close()

    def count(self) -> int:
        """Total number of logged queries."""
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute("SELECT COUNT(*) FROM query_logs").fetchone()[0]
            finally:
                conn.close()

    # ── internals ───────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS query_logs (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        results TEXT DEFAULT '[]',
                        source TEXT DEFAULT 'hybrid',
                        weights TEXT DEFAULT '{}',
                        context TEXT DEFAULT '{}',
                        feedback REAL,
                        strategy TEXT DEFAULT 'balanced',
                        success INTEGER DEFAULT 0,
                        timestamp REAL NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_query ON query_logs(query)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON query_logs(timestamp)")
                conn.commit()
            finally:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _insert(self, entry: QueryLog) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO query_logs
                       (id, query, results, source, weights, context, strategy, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.query_id,
                        entry.text,
                        json.dumps(entry.results),
                        entry.source,
                        json.dumps(entry.weights_used),
                        json.dumps(entry.context),
                        entry.strategy,
                        entry.timestamp,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def _fetch_one(self, qid: str) -> Optional[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM query_logs WHERE id = ?", (qid,)
                ).fetchone()
            finally:
                conn.close()

    def _fetch_similar(self, text: str, limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                like = f"%{text}%"
                return conn.execute(
                    "SELECT * FROM query_logs WHERE query LIKE ? "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (like, limit),
                ).fetchall()
            finally:
                conn.close()

    def _fetch_recent(self, n: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM query_logs ORDER BY timestamp DESC LIMIT ?",
                    (n,),
                ).fetchall()
            finally:
                conn.close()

    def _update_feedback(
        self, qid: str, feedback: float, success: Optional[int],
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                if success is not None:
                    conn.execute(
                        "UPDATE query_logs SET feedback=?, success=? WHERE id=?",
                        (feedback, success, qid),
                    )
                else:
                    conn.execute(
                        "UPDATE query_logs SET feedback=? WHERE id=?",
                        (feedback, qid),
                    )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _row_to_log(row: sqlite3.Row) -> QueryLog:
        return QueryLog(
            query_id=row["id"],
            text=row["query"],
            timestamp=row["timestamp"],
            results=json.loads(row["results"] or "[]"),
            source=row["source"],
            weights_used=json.loads(row["weights"] or "{}"),
            context=json.loads(row["context"] or "{}"),
            feedback=row["feedback"],
            strategy=row["strategy"],
            success=row["success"],
        )
