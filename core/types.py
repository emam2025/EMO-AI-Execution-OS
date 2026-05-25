"""Shared type definitions for the AI Execution Cluster.

Centralizes data types used across multiple core modules to prevent
circular imports and enforce stable API boundaries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models.dag import DependencyGraph


# ═══════════════════════════════════════════════════════════════════════
# Intent — query classification labels
# ═══════════════════════════════════════════════════════════════════════

class Intent(str):
    """Query intent classification labels."""
    EXPLAIN = "explain"
    IMPACT = "impact"
    HOTSPOTS = "hotspots"
    WHY = "why"
    REFACTOR = "refactor"
    EXPLORE = "explore"
    SEMANTIC = "semantic"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════════════
# ExecutionPlan — planning result carrier
# ═══════════════════════════════════════════════════════════════════════

class ExecutionPlan:
    """Planning result: intent + target + DAG ready for the engine."""

    __slots__ = ("intent", "target", "target_type", "dag", "confidence", "planner_version")

    def __init__(
        self,
        intent: str = Intent.UNKNOWN,
        target: Optional[str] = None,
        target_type: str = "symbol",
        dag: Optional[DependencyGraph] = None,
        confidence: str = "high",
        planner_version: str = "",
    ):
        self.intent = intent
        self.target = target
        self.target_type = target_type
        self.dag = dag or DependencyGraph()
        self.confidence = confidence
        self.planner_version = planner_version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "target": self.target,
            "target_type": self.target_type,
            "confidence": self.confidence,
            "dag": self.dag.to_dict() if self.dag else {},
            "planner_version": self.planner_version,
        }
