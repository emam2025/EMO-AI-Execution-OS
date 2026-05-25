"""Planning Layer — Phase 9 refactored.

QueryPlanner only: classifies intent, extracts target, builds a DAG.
No execution logic. No tool routing. No step loop.

Determinism contract:
  - Given the same query and same GraphQuery state, plan() returns the
    same ExecutionPlan (intent + target + DAG structure).
  - DAG node IDs are sorted alphabetically within each depth level.
  - Intent classification uses first-pattern-match against a priority-
    ordered list (deterministic).
  - Target extraction returns the *last* meaningful regex match, not the
    first, because users tend to put the symbol at the end of the query.

Planner versioning:
  - PLANNER_VERSION is set here and stamped onto every ExecutionPlan.
  - Bump when DAG structure, intent classification, or target extraction
    logic changes.

Architecture:
    UnifiedRuntime → QueryPlanner → DAG → ExecutionEngine
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Set

from .graph_query import GraphQuery
from .execution_engine import DAGBuilder
from .models.dag import DependencyGraph, PlanNode, NodeConfig
from .types import Intent, ExecutionPlan
from .api_compliance import verify_frozen_methods


# ======================================================================
# Intent classification
# ======================================================================

_INTENT_PATTERNS: List[Tuple[str, str, List[str]]] = [
    (Intent.IMPACT,   r"\b(impact(ing|s|ed)?|blast.radius|who (calls?|depend|use|import|depend)|what (breaks?|affect)|change (affect|impact)|would break|ripple)",
     ["impact", "blast radius", "who calls", "depend", "break", "affect", "ripple"]),
    (Intent.EXPLAIN,  r"\b(explain(s|ed)?|what (does|is|are) .{2,} (do|work)?|how (does|is|are) .{2,} work|describe|tell me|understand|show me)",
     ["explain", "what does", "how does", "describe", "tell me"]),
    (Intent.WHY,       r"\bwhy (is|are|does|would) .{2,} (important|critical|key|central|matter|exist)|importan(ce|t)|central|critical|key role|matter",
     ["why important", "why critical", "importance", "critical", "key role"]),
    (Intent.REFACTOR,  r"\b(refactor(s|ed|ing)?|improve|suggest(ion|ed|s)?|how (to|can|would) .{2,} (improve|fix|clean|better|make)|optimize|simplify|clean up|better way|code quality)",
     ["refactor", "improve", "suggestion", "clean", "optimize", "simplify"]),
    (Intent.HOTSPOTS,  r"\b(top( hotspots?| symbols?)?|hotspots?|bottleneck(s)?|most (called|used|impactful|important)|ranking|highest.impact|critical.point|frequently)",
     ["top", "hotspot", "bottleneck", "ranking", "most called", "most used"]),
    (Intent.SEMANTIC, r"\b(find|search|look.?up|locate|discover|related.to|similar.to|what.are)\b",
     ["find", "search", "locate", "discover", "related", "similar"]),
]

_TARGET_PATTERN = re.compile(r"['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?")

# Planner version — bump this whenever DAG structure, intent
# classification, or target extraction changes.
PLANNER_VERSION = "1.0.0"

# ── API Surface Freeze v2 ─────────────────────────────────────────
# The public API of QueryPlanner is frozen.
# Adding, removing, or changing any public method requires bumping
# PLANNER_API_VERSION and updating all callers.
PLANNER_API_VERSION = "2.0.0"
PLANNER_FROZEN_PUBLIC_METHODS = frozenset({
    "plan", "get_tool_weights", "get_confidence_adjustment",
})


# ======================================================================
# QueryPlanner
# ======================================================================

# Words to ignore during target extraction (deterministic filter).
_STOPWORDS: Set[str] = {
    "what", "how", "why", "who", "where", "when", "which",
    "does", "is", "are", "do", "did", "can", "will", "would",
    "the", "a", "an", "this", "that", "these", "those",
    "me", "my", "you", "your", "it", "its", "show", "tell",
    "describe", "explain", "impact", "refactor", "improve",
    "top", "hotspot", "hotspots", "bottleneck", "bottlenecks",
    "call", "called", "calls", "function", "symbol", "code",
    "file", "change", "changes", "most",
}


class QueryPlanner:
    """Analyzes user queries and builds DAG plans.

    API Version: {PLANNER_API_VERSION}
    Frozen methods (v2): {sorted(PLANNER_FROZEN_PUBLIC_METHODS)}

    Accepts optional bias providers from the feedback loop:
      - weights_provider(intent) → Dict[tool, weight]: 0.0–1.0 preference
        per tool for this intent. The planner uses this as advisory bias;
        it never changes DAG structure based on it.
      - calibration_provider(intent) → float: confidence multiplier.
        1.0 = neutral, <1.0 = less confident, >1.0 = more confident.

    These are the ONLY feedback signals that affect the planner.
    No DAG structure changes, no execution logic changes.
    """

    PLANNER_API_VERSION = PLANNER_API_VERSION
    FROZEN_PUBLIC_METHODS_V2 = PLANNER_FROZEN_PUBLIC_METHODS

    @classmethod
    def check_api_compliance(cls) -> None:
        """Verify all frozen public methods exist on the class.

        Raises ``APIViolationError`` if any method in the frozen set
        has been removed without a version bump.
        """
        verify_frozen_methods(
            cls, cls.FROZEN_PUBLIC_METHODS_V2, cls.PLANNER_API_VERSION,
        )

    def __init__(
        self,
        gq: GraphQuery,
        weights_provider: Optional[Callable[[str], Dict[str, float]]] = None,
        calibration_provider: Optional[Callable[[str], float]] = None,
    ):
        self.gq = gq
        self._weights_provider = weights_provider
        self._calibration_provider = calibration_provider

    def get_tool_weights(self, intent: str) -> Dict[str, float]:
        """Advisory per-tool bias weights for this intent.

        Returns empty dict if no provider configured (neutral).
        """
        if self._weights_provider:
            return self._weights_provider(intent)
        return {}

    def get_confidence_adjustment(self, intent: str) -> float:
        """Confidence multiplier based on historical success."""
        if self._calibration_provider:
            return self._calibration_provider(intent)
        return 1.0

    def plan(self, query: str) -> ExecutionPlan:
        q = query.strip()
        intent = self._classify_intent(q)
        target = self._extract_target(q)

        target_type = "symbol"
        if target:
            meta = self.gq.get_symbol_metadata(target)
            if meta is None:
                fmeta = self.gq.get_file_metadata(target)
                if fmeta:
                    target_type = "file"
                else:
                    return ExecutionPlan(
                        intent=intent, target=target, target_type="unknown",
                        confidence="low",
                    )

        dag, confidence = self._build_dag(intent, target, target_type)
        confidence = self._calibrate_confidence(confidence, intent)
        return ExecutionPlan(
            intent=intent, target=target, target_type=target_type,
            dag=dag, confidence=confidence,
            planner_version=PLANNER_VERSION,
        )

    def _calibrate_confidence(self, base: str, intent: str) -> str:
        """Apply feedback calibration to the base confidence level.

        Maps base {"high": 1.0, "medium": 0.7, "low": 0.4} →
        calibrated → back to string.
        """
        base_map = {"high": 1.0, "medium": 0.7, "low": 0.4}
        reverse_map = {1.0: "high", 0.7: "medium", 0.4: "low"}

        numeric = base_map.get(base, 0.4)
        adj = self.get_confidence_adjustment(intent)
        calibrated = min(1.0, max(0.3, numeric * adj))

        # Find nearest bucket
        return min(reverse_map.keys(), key=lambda k: abs(k - calibrated))

    def _classify_intent(self, query: str) -> str:
        q = query.lower().strip()
        for intent, pattern, _ in _INTENT_PATTERNS:
            if re.search(pattern, q):
                return intent
        return Intent.UNKNOWN

    def _extract_target(self, query: str) -> Optional[str]:
        """Extract the most likely symbol/file target from a query.

        Strategy (deterministic):
          1. Find all regex matches (symbol-like words).
          2. Filter stopwords.
          3. Of the remaining, return the *last* match — users typically
             place the target symbol at the end of the query
             (e.g. "explain authenticate_user", "impact export_data").
          4. If the last match exists in the graph (symbol or file),
             return it; otherwise return the raw match.

        Never falls back to "check the previous word" heuristics —
        those are non-deterministic and hard to test.
        """
        candidates = _TARGET_PATTERN.findall(query)
        meaningful = [
            w for w in candidates
            if w.lower() not in _STOPWORDS and len(w) >= 2
        ]
        if not meaningful:
            return None
        # Return the last meaningful match (stable: findall order is left→right)
        target = meaningful[-1]
        if self.gq.get_symbol_metadata(target):
            return target
        if self.gq.get_file_metadata(target):
            return target
        if target.isdigit():
            return target
        return target

    def _build_dag(
        self, intent: str, target: Optional[str], target_type: str,
    ) -> tuple[DependencyGraph, str]:
        """Build a DependencyGraph for the given intent.

        Returns (dag, confidence).

        Advisory bias (from feedback loop):
          - tool_weights are inspected for EXPLORE/UNKNOWN path selection
          - confidence is calibrated via _calibrate_confidence (called
            in plan(), not here)
        """
        builder = DAGBuilder()
        confidence = "high"

        # Advisory: fetch tool weights for this intent (never changes structure)
        weights = self.get_tool_weights(intent)

        resolved = self.gq.resolve_symbol_name(target) if target else None
        target_id = resolved or target

        if intent == Intent.HOTSPOTS:
            limit_val = int(target) if target and target.isdigit() else 10
            builder.add("hotspots", tool="graph_retrieval.ranked_hotspots",
                        inputs={"limit": limit_val})
            if target and not target.isdigit():
                builder.add("enrich", tool="agent.top_hotspots",
                            inputs={"limit": 10})
                builder.depends("enrich", "hotspots")
            if not target:
                confidence = "high"

        elif intent == Intent.IMPACT:
            if target is None:
                return DependencyGraph(), "low"
            builder.add("impact", tool="graph_retrieval.retrieve_impact_chain",
                        inputs={"symbol_id": target_id, "max_depth": 3})
            builder.add("heuristic", tool="graph_retrieval.heuristic_analysis",
                        inputs={"symbol_id": target_id})
            builder.add("agent", tool="agent.impact",
                        inputs={"symbol_id": target_id})
            builder.depends("heuristic", "impact")
            builder.depends("agent", "heuristic")

        elif intent == Intent.WHY:
            if target is None:
                return DependencyGraph(), "low"
            builder.add("heuristic", tool="graph_retrieval.heuristic_analysis",
                        inputs={"symbol_id": target_id})
            builder.add("agent", tool="agent.why",
                        inputs={"symbol_id": target_id})
            builder.depends("agent", "heuristic")

        elif intent == Intent.REFACTOR:
            if target is None:
                return DependencyGraph(), "low"
            builder.add("heuristic", tool="graph_retrieval.heuristic_analysis",
                        inputs={"symbol_id": target_id})
            builder.add("agent", tool="agent.suggest_refactor",
                        inputs={"symbol_id": target_id})
            builder.depends("agent", "heuristic")

        elif intent == Intent.SEMANTIC:
            builder.add("hybrid", tool="hybrid_retrieval.retrieve",
                        inputs={"query": target or "", "top_k": 10})
            if target:
                builder.add("core", tool="graph_retrieval.retrieve_symbol_core",
                            inputs={"symbol_id": target_id})
                builder.add("context", tool="context_compiler.build_llm_context",
                            inputs={"symbol_id": target_id})
                builder.add("agent", tool="agent.explain",
                            inputs={"symbol_id": target_id})
                builder.depends("core", "hybrid")
                builder.depends("context", "core")
                builder.depends("agent", "context")

        elif intent == Intent.EXPLAIN:
            if target is None:
                return DependencyGraph(), "low"
            builder.add("core", tool="graph_retrieval.retrieve_symbol_core",
                        inputs={"symbol_id": target_id})
            builder.add("heuristic", tool="graph_retrieval.heuristic_analysis",
                        inputs={"symbol_id": target_id})
            builder.add("context", tool="context_compiler.build_llm_context",
                        inputs={"symbol_id": target_id})
            builder.add("agent", tool="agent.explain",
                        inputs={"symbol_id": target_id})
            builder.depends("context", "core")
            builder.depends("agent", "context")
            builder.depends("agent", "heuristic")

        else:  # EXPLORE / UNKNOWN
            if target is None:
                builder.add("hotspots", tool="graph_retrieval.ranked_hotspots",
                            inputs={"limit": 10})
                enrich_weight = weights.get("agent.top_hotspots", 0.5)
                if enrich_weight >= 0.3:
                    confidence = "medium"
                else:
                    confidence = "low"
            else:
                builder.add("core", tool="graph_retrieval.retrieve_symbol_core",
                            inputs={"symbol_id": target_id})
                builder.add("heuristic", tool="graph_retrieval.heuristic_analysis",
                            inputs={"symbol_id": target_id})
                builder.add("context", tool="context_compiler.build_llm_context",
                            inputs={"symbol_id": target_id})
                builder.add("agent", tool="agent.explain",
                            inputs={"symbol_id": target_id})
                builder.depends("context", "core")
                builder.depends("agent", "context")
                builder.depends("agent", "heuristic")
                explain_weight = weights.get("agent.explain", 0.5)
                if explain_weight >= 0.6:
                    confidence = "medium"
                elif explain_weight >= 0.3:
                    confidence = "medium"
                else:
                    confidence = "low"

        return builder.build(), confidence


# ── Boot-time API compliance check ────────────────────────────────
QueryPlanner.check_api_compliance()
