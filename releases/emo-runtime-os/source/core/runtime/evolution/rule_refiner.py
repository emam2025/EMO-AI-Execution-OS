"""GAP 4 — RuleRefiner: automatic rule refinement from runtime data.

Analyzes runtime data and suggests refinements to Canon rules,
thresholds, and enforcement policies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.evolution.refiner")


@dataclass
class RefinementSuggestion:
    """A suggested refinement to a Canon rule or threshold."""
    rule_id: str = ""
    field: str = ""
    current_value: Any = None
    suggested_value: Any = None
    confidence: float = 0.0
    evidence: str = ""
    severity: str = "info"


class RuleRefiner:
    """Analyzes runtime execution data and suggests rule refinements.

    Uses historical execution data, failure patterns, and performance
    metrics to recommend adjustments to:
      - Canon thresholds (e.g., risk_score > 0.8 → 0.7)
      - Enforcement severity (e.g., HIGH → MEDIUM)
      - Propagation rules
    """

    def __init__(self) -> None:
        self._suggestions: List[RefinementSuggestion] = []

    def analyze_execution_data(self, data: Dict[str, Any]) -> List[RefinementSuggestion]:
        """Analyze execution data and produce refinement suggestions.

        Args:
            data: Runtime execution data including failures, latencies,
                  and enforcement events.

        Returns:
            List of refinement suggestions.
        """
        suggestions: List[RefinementSuggestion] = []

        # Analyze failure rates for threshold refinement
        failures = data.get("failures", [])
        total_executions = data.get("total_executions", 0)
        if total_executions > 0:
            failure_rate = len(failures) / total_executions
            if failure_rate > 0.2:
                suggestions.append(RefinementSuggestion(
                    rule_id="LAW_16",
                    field="risk_threshold",
                    current_value=0.8,
                    suggested_value=0.7,
                    confidence=min(1.0, failure_rate * 2),
                    evidence=f"Failure rate {failure_rate:.2f} exceeds 0.2 — "
                             f"lowering risk threshold increases coverage",
                    severity="warning",
                ))

        # Analyze enforcement blocking rate
        blocked = data.get("blocked_executions", [])
        if blocked and total_executions > 0:
            block_rate = len(blocked) / total_executions
            if block_rate > 0.3:
                suggestions.append(RefinementSuggestion(
                    rule_id="LAW_14",
                    field="enforcement_severity",
                    current_value="CRITICAL",
                    suggested_value="HIGH",
                    confidence=0.6,
                    evidence=f"Block rate {block_rate:.2f} > 0.3 — "
                             f"reducing severity reduces false positives",
                    severity="info",
                ))

        # Analyze hotspot frequency
        hotspots = data.get("hotspots", [])
        if hotspots:
            most_frequent = hotspots[0]
            if most_frequent.get("frequency", 0) > 100:
                suggestions.append(RefinementSuggestion(
                    rule_id="LAW_19",
                    field="trace_detail_level",
                    current_value="full",
                    suggested_value="sampled",
                    confidence=0.5,
                    evidence=f"Tool '{most_frequent.get('tool', '?')}' executed "
                             f"{most_frequent.get('frequency', 0)} times — "
                             f"sampled tracing reduces overhead",
                    severity="info",
                ))

        self._suggestions.extend(suggestions)
        return suggestions

    def suggestions(self, limit: int = 20) -> List[RefinementSuggestion]:
        """Return recent suggestions."""
        return self._suggestions[-limit:]

    def apply_suggestion(self, suggestion: RefinementSuggestion) -> bool:
        """Mark a suggestion as applied."""
        logger.info(
            "Applied refinement: %s.%s %s → %s",
            suggestion.rule_id, suggestion.field,
            suggestion.current_value, suggestion.suggested_value,
        )
        return True
