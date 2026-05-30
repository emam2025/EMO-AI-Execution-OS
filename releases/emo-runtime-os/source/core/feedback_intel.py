"""Intelligence Feedback Loop — Execution → Metrics → Weights → Planner bias.

Architecture (строго соблюдается):
  Execution Layer (frozen)  ← never modified by feedback
      ↓
  Observation Layer (passive)
      metrics_store, traces, cost, latency, failures
      ↓
  Feedback Layer
      pattern detection, correlation, success/failure signals
      ↓
  Planner Adjustment Layer (ONLY safe zone)
      → weight tweaks (NOT logic changes)
      → heuristic tuning
      → ranking shifts
      → confidence calibration

🚫 NOT allowed:
  - auto rewrite of DAG structure
  - self-modifying execution rules
  - dynamic tool behavior changes

✅ Allowed:
  - weighted adjustments per (intent, tool)
  - heuristic parameter tuning
  - ranking priority shifts
  - confidence calibration per intent
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("emo_ai.feedback_intel")

FEEDBACK_INTEL_VERSION = "1.0.0"

_DEFAULT_DB_PATH = Path(os.environ.get(
    "EMO_AI_FEEDBACK_DB",
    ".ai/index/feedback.db",
))

# Bayesian prior — assume 80% success rate before seeing any data.
_PRIOR_ALPHA = 4.0
_PRIOR_BETA = 1.0

# Minimum observations before a weight/calibration is surfaced.
_MIN_OBSERVATIONS = 5


@dataclass
class ToolOutcome:
    """Single tool execution outcome from a DAG node. Passive observation."""
    tool: str
    intent: str            # which intent triggered this tool
    status: str            # "completed", "failed", "cached", "error"
    duration: float = 0.0
    error_type: str = ""


@dataclass
class IntentToolWeight:
    """Bias weight for using a tool under a given intent.

    0.0 = strongly avoid, 0.5 = neutral, 1.0 = strongly prefer.

    The planner uses this as an advisory signal — it never changes
    DAG structure based on it.
    """
    intent: str
    tool: str
    weight: float = 0.5        # 0.0–1.0
    observations: int = 0


@dataclass
class ConfidenceCalibration:
    """Per-intent confidence calibration.

    The planner's base confidence (e.g. "high"/"medium"/"low") is
    adjusted by this factor. 1.0 = no adjustment, <1.0 = less
    confident, >1.0 = more confident.
    """
    intent: str
    adjustment: float = 1.0   # multiplier on planner confidence
    observations: int = 0


@dataclass
class RankingHeuristic:
    """Suggested tweak to a ranking parameter.

    Example: {"parameter": "incoming_call_weight", "delta": +0.05}
    means "increase the importance of incoming calls by 5%".

    These are passed to the formatter/ranker as advisory signals.
    """
    parameter: str
    delta: float = 0.0
    confidence: float = 0.0   # 0.0–1.0


class FeedbackIntelligence:
    """Execution → Metrics → Weights → Planner bias.

    Thread-safe. Persists to SQLite.

    Usage:
        fb = FeedbackIntelligence()
        fb.ingest(step_results, intent="explain")
        weights = fb.tool_weights("explain")     # → {tool: weight}
        calib = fb.confidence_adjustment("explain")  # → float
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

        # In-memory cache
        self._outcomes: List[ToolOutcome] = []
        self._load_outcomes()

    # ── public API ────────────────────────────────────────────

    def ingest(
        self,
        step_results: List[Dict[str, Any]],
        intent: str = "",
    ) -> None:
        """Process step results from an execution trace.

        The result at minimum should contain:
          - "tool": str
          - "status": str
          - "error": str (optional)
        """
        for sr in step_results:
            outcome = ToolOutcome(
                tool=sr.get("tool", ""),
                intent=intent,
                status=sr.get("status", "unknown"),
                duration=sr.get("duration", 0.0) or 0.0,
                error_type=self._classify_error(
                    sr.get("error", "") or "",
                    sr.get("result") or {},
                ),
            )
            self._outcomes.append(outcome)
            self._persist_outcome(outcome)

    def tool_weights(self, intent: str) -> Dict[str, float]:
        """Return weight per tool for a given intent.

        Weight = Bayesian success probability for (intent, tool).
        Higher weight = historically more reliable for this intent.
        Returns empty dict if insufficient data.
        """
        with self._lock:
            matches = [o for o in self._outcomes if o.intent == intent]

        if len(matches) < _MIN_OBSERVATIONS:
            return {}

        # Group by tool
        tool_stats: Dict[str, Dict[str, int]] = {}
        for o in matches:
            if o.tool not in tool_stats:
                tool_stats[o.tool] = {"success": 0, "total": 0}
            tool_stats[o.tool]["total"] += 1
            if o.status in ("completed", "cached"):
                tool_stats[o.tool]["success"] += 1

        weights: Dict[str, float] = {}
        for tool, stats in tool_stats.items():
            if stats["total"] < 2:
                weights[tool] = 0.5
                continue
            alpha = _PRIOR_ALPHA + stats["success"]
            beta = _PRIOR_BETA + (stats["total"] - stats["success"])
            weights[tool] = round(alpha / (alpha + beta), 3)

        return weights

    def confidence_adjustment(self, intent: str) -> float:
        """Return confidence multiplier for a given intent.

        1.0 = neutral. <1.0 means "be less confident" (past failures
        for this intent). >1.0 means "be more confident" (high
        success rate).
        """
        with self._lock:
            matches = [o for o in self._outcomes if o.intent == intent]

        if len(matches) < _MIN_OBSERVATIONS:
            return 1.0

        successes = sum(
            1 for o in matches if o.status in ("completed", "cached")
        )
        failures = len(matches) - successes
        if failures == 0:
            return 1.0  # no adjustments when perfect

        rate = successes / len(matches)
        # Map [0.0, 1.0] success rate → [0.5, 1.5] adjustment
        # 0.5 = halve confidence, 1.0 = no change, 1.5 = increase 50%
        adjustment = 0.5 + rate
        return round(adjustment, 3)

    def heuristic_tweaks(self, intent: str) -> List[RankingHeuristic]:
        """Return advisory ranking heuristic tweaks for an intent.

        Currently a lightweight implementation: when the system
        observes that certain tools under an intent consistently
        take longer, it flags the importance of latency in ranking.
        """
        with self._lock:
            matches = [o for o in self._outcomes if o.intent == intent]

        if len(matches) < _MIN_OBSERVATIONS:
            return []

        tweaks: List[RankingHeuristic] = []

        # If latency variance is high, flag it
        durations = [o.duration for o in matches if o.duration > 0]
        if len(durations) >= 10:
            avg = sum(durations) / len(durations)
            variance = sum((d - avg) ** 2 for d in durations) / len(durations)
            if variance > avg * 0.5:  # high variance relative to mean
                tweaks.append(RankingHeuristic(
                    parameter="latency_weight",
                    delta=round(min(variance / avg, 2.0), 2),
                    confidence=0.5,
                ))

        # If certain error types dominate, flag them
        error_types: Dict[str, int] = {}
        for o in matches:
            if o.error_type:
                error_types[o.error_type] = error_types.get(o.error_type, 0) + 1
        if error_types:
            dominant = max(error_types, key=error_types.get)
            dominant_count = error_types[dominant]
            if dominant_count >= 5 and dominant_count / len(matches) >= 0.2:
                tweaks.append(RankingHeuristic(
                    parameter=f"avoid_{dominant}_errors",
                    delta=1.0,
                    confidence=round(dominant_count / len(matches), 2),
                ))

        return tweaks

    def intent_success_rate(self, intent: str) -> float:
        """Overall success rate for an intent (0.0–1.0)."""
        with self._lock:
            matches = [o for o in self._outcomes if o.intent == intent]
        if not matches:
            return _PRIOR_ALPHA / (_PRIOR_ALPHA + _PRIOR_BETA)
        successes = sum(
            1 for o in matches if o.status in ("completed", "cached")
        )
        return successes / len(matches)

    def total_observations(self) -> int:
        with self._lock:
            return len(self._outcomes)

    def known_intents(self) -> List[str]:
        with self._lock:
            return sorted({o.intent for o in self._outcomes if o.intent})

    def report(self) -> Dict[str, Any]:
        """Summary for observability dashboard."""
        with self._lock:
            intents_seen = {o.intent for o in self._outcomes if o.intent}
            tools_seen = {o.tool for o in self._outcomes}
        return {
            "version": FEEDBACK_INTEL_VERSION,
            "total_observations": len(self._outcomes),
            "intents_tracked": sorted(intents_seen),
            "tools_tracked": sorted(tools_seen),
            "calibrations": {
                intent: self.confidence_adjustment(intent)
                for intent in intents_seen
            },
        }

    # ── internal ──────────────────────────────────────────────

    @staticmethod
    def _classify_error(error: str, result: Dict[str, Any]) -> str:
        error_lower = (error + (result.get("error", "") or "")).lower()
        if "timeout" in error_lower:
            return "timeout"
        if "contract" in error_lower:
            return "contract"
        if "not found" in error_lower or "lookup" in error_lower:
            return "lookup"
        if error:
            return "runtime"
        return ""

    # ── persistence ───────────────────────────────────────────

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS feedback_outcomes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tool TEXT NOT NULL,
                        intent TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL,
                        duration REAL NOT NULL DEFAULT 0.0,
                        error_type TEXT NOT NULL DEFAULT '',
                        recorded_at REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fb_intent
                    ON feedback_outcomes(intent)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fb_tool
                    ON feedback_outcomes(tool)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS feedback_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO feedback_meta (key, value)
                    VALUES ('version', ?)
                """, (FEEDBACK_INTEL_VERSION,))
        except Exception as e:
            logger.warning("Feedback DB init failed: %s", e)

    def _persist_outcome(self, outcome: ToolOutcome) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute(
                    "INSERT INTO feedback_outcomes "
                    "(tool, intent, status, duration, error_type, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (outcome.tool, outcome.intent, outcome.status,
                     outcome.duration, outcome.error_type, time.time()),
                )
        except Exception as e:
            logger.debug("Feedback persist failed: %s", e)

    def _load_outcomes(self) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                rows = conn.execute(
                    "SELECT tool, intent, status, duration, error_type "
                    "FROM feedback_outcomes ORDER BY recorded_at",
                ).fetchall()
                for tool, intent, status, duration, error_type in rows:
                    self._outcomes.append(ToolOutcome(
                        tool=tool, intent=intent, status=status,
                        duration=duration, error_type=error_type,
                    ))
        except Exception as e:
            logger.debug("Feedback load failed: %s", e)
