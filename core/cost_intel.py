"""Cost & Performance Intelligence.

Tracks execution cost per node and per tool type, then uses that data
to make cost-aware scheduling decisions.

Key concepts:
  - NodeCost: time, estimated tokens, IO weight for a single node execution.
  - CostTracker: accumulates NodeCost records per tool type, computes
    P50 / P95 / P99 latency, and provides cost estimates for scheduling.
  - CostAwareScheduler: given a set of nodes at the same topological
    depth, returns them in "cheapest first" order to minimise time to
    first result.

All data is kept in-memory (backed by a small SQLite store on disk
via _persist_stats / _load_stats for crash resilience).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import statistics
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .models.dag import PlanNode, DependencyGraph

logger = logging.getLogger("emo_ai.cost_intel")

# Cost intel version — bump when stats schema changes.
COST_INTEL_VERSION = "1.0.0"

_DEFAULT_DB_PATH = Path(os.environ.get(
    "EMO_AI_COST_DB",
    ".ai/index/cost_stats.db",
))


@dataclass
class NodeCost:
    """Cost incurred by executing a single DAG node."""
    tool: str
    duration_seconds: float = 0.0
    estimated_tokens: int = 0
    io_weight: float = 1.0  # 1.0 = normal IO cost

    @property
    def total_cost(self) -> float:
        """Composite cost: time dominates, tokens add, IO multiplies."""
        base = self.duration_seconds + (self.estimated_tokens / 100_000)
        return base * self.io_weight


class CostTracker:
    """Per-tool-type cost histogram.

    Thread-safe. Stores raw durations per tool and computes percentiles
    on demand. Persists to SQLite for crash resilience.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        load_stats = self._load_stats()
        # tool → list of duration_seconds
        self._durations: Dict[str, List[float]] = {
            t: list(durs) for t, durs in load_stats.items()
        }

    # ── public API ────────────────────────────────────────────

    def record(self, cost: NodeCost) -> None:
        """Record a single node execution cost."""
        with self._lock:
            self._durations.setdefault(cost.tool, []).append(
                cost.duration_seconds,
            )
            self._persist(cost.tool, cost.duration_seconds)

    def p50(self, tool: str) -> float:
        """Median latency for a tool type (seconds)."""
        return self._percentile(tool, 50)

    def p95(self, tool: str) -> float:
        """P95 latency for a tool type (seconds)."""
        return self._percentile(tool, 95)

    def p99(self, tool: str) -> float:
        """P99 latency for a tool type (seconds)."""
        return self._percentile(tool, 99)

    def mean(self, tool: str) -> float:
        """Mean latency for a tool type (seconds)."""
        with self._lock:
            durs = self._durations.get(tool, [])
        return statistics.mean(durs) if durs else 0.0

    def count(self, tool: str) -> int:
        """Number of recorded executions for a tool type."""
        with self._lock:
            return len(self._durations.get(tool, []))

    def estimate_cost(self, node: PlanNode) -> float:
        """Return the P50 cost estimate for a node's tool.

        Falls back to 1.0 if no data exists yet.
        """
        return self.p50(node.tool) or 1.0

    def all_tools(self) -> List[str]:
        with self._lock:
            return sorted(self._durations.keys())

    def report(self) -> Dict[str, Any]:
        """Summary dictionary for observability."""
        result: Dict[str, Any] = {}
        with self._lock:
            for tool, durs in self._durations.items():
                if not durs:
                    continue
                sorted_d = sorted(durs)
                n = len(sorted_d)
                result[tool] = {
                    "count": n,
                    "p50": round(sorted_d[n // 2], 3) if n else 0,
                    "p95": round(sorted_d[int(n * 0.95)], 3) if n >= 20 else 0,
                    "p99": round(sorted_d[int(n * 0.99)], 3) if n >= 100 else 0,
                    "mean": round(statistics.mean(sorted_d), 3),
                    "max": round(sorted_d[-1], 3) if n else 0,
                }
        return result

    # ── percentiles ────────────────────────────────────────────

    def _percentile(self, tool: str, p: int) -> float:
        with self._lock:
            durs = self._durations.get(tool, [])
        if not durs:
            return 0.0
        sorted_d = sorted(durs)
        idx = max(0, min(len(sorted_d) - 1, int(len(sorted_d) * p / 100)))
        return sorted_d[idx]

    # ── persistence ────────────────────────────────────────────

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cost_stats (
                        tool TEXT NOT NULL,
                        duration REAL NOT NULL,
                        recorded_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cost_stats_tool
                    ON cost_stats(tool)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS cost_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO cost_meta (key, value)
                    VALUES ('version', ?)
                """, (COST_INTEL_VERSION,))
        except Exception as e:
            logger.warning("Cost stats DB init failed: %s", e)

    def _persist(self, tool: str, duration: float) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO cost_stats (tool, duration, recorded_at) "
                    "VALUES (?, ?, ?)",
                    (tool, duration, time.time()),
                )
        except Exception as e:
            logger.debug("Cost persist failed: %s", e)

    def _load_stats(self) -> Dict[str, List[float]]:
        result: Dict[str, List[float]] = {}
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                rows = conn.execute(
                    "SELECT tool, duration FROM cost_stats "
                    "ORDER BY recorded_at",
                ).fetchall()
                for tool, dur in rows:
                    result.setdefault(tool, []).append(dur)
        except Exception as e:
            logger.debug("Cost load failed: %s", e)
        return result


class CostAwareScheduler:
    """Orders nodes at the same depth by estimated cost (cheapest first).

    This lets cheaper nodes finish faster, reducing the time to first
    partial result — useful for streaming / progressive rendering.
    """

    def __init__(self, tracker: CostTracker):
        self._tracker = tracker

    def schedule(self, level: List[PlanNode]) -> List[PlanNode]:
        """Return nodes ordered by ascending estimated cost.

        Deterministic: nodes with equal estimated cost are sorted by
        node ID.
        """
        def sort_key(n: PlanNode) -> Tuple[float, str]:
            cost = self._tracker.estimate_cost(n)
            return (cost, n.id)
        return sorted(level, key=sort_key)
