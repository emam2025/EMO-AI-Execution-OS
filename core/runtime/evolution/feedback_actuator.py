"""GAP 4 — FeedbackActuator: runtime → human → architecture bridge.

The final link in the feedback loop.

SAFETY CONSTRAINT:
  This module does NOT apply architecture mutations.
  It generates evolution REPORTS for human review.

Flow:
  Runtime data → RuleRefiner → CanonEvolver → FeedbackActuator
  → EvolutionReport → human review → (manual) apply

This closes the loop safely:
  Runtime reality → Drift detection → Rule refinement → Evolution report
  → Human approval → Architecture change → Runtime behavior change
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.runtime.evolution.canon_evolver import CanonEvolver, EvolutionReport
from core.runtime.evolution.rule_refiner import RefinementSuggestion

logger = logging.getLogger("emo_ai.evolution.actuator")


@dataclass
class FeedbackReport:
    """Complete feedback report for human review.

    Contains the evolution report plus context about what
    runtime data triggered the suggestions.
    """
    evolution: EvolutionReport
    runtime_snapshot: Dict[str, Any] = field(default_factory=dict)
    generated_at: float = 0.0


class FeedbackActuator:
    """Generates evolution reports for human review.

    Responsibilities:
      - Collect runtime data snapshot
      - Run CanonEvolver to produce suggestions
      - Package everything into a FeedbackReport
      - Support callbacks for notifying humans
      - Record all reports for audit

    Does NOT:
      - Apply mutations
      - Change Canon rules
      - Modify enforcement thresholds
    """

    def __init__(
        self,
        evolver: Optional[CanonEvolver] = None,
    ):
        self._evolver = evolver or CanonEvolver()
        self._reports: List[FeedbackReport] = []
        self._callbacks: List[Callable] = []

    @property
    def evolver(self) -> CanonEvolver:
        return self._evolver

    def on_report(self, callback: Callable) -> None:
        """Register a callback for when a feedback report is generated."""
        self._callbacks.append(callback)

    def generate_report(
        self,
        runtime_data: Dict[str, Any],
        snapshot: Optional[Dict[str, Any]] = None,
        *,
        approved_by: str = "",
    ) -> FeedbackReport:
        """Generate a feedback report from runtime data.

        1. Run CanonEvolver → EvolutionReport (with LAW 28-30 governance)
        2. Package with runtime snapshot
        3. Fire callbacks
        4. Return report

        Args:
            runtime_data: Runtime execution data.
            snapshot: Optional system state snapshot.
            approved_by: Human identifier approving this evolution.
                         LAW 28 — empty means not approved.

        Returns:
            FeedbackReport for human review.
        """
        import time

        evolution = self._evolver.evolve(runtime_data, approved_by=approved_by)

        report = FeedbackReport(
            evolution=evolution,
            runtime_snapshot=snapshot or {},
            generated_at=time.time(),
        )

        self._reports.append(report)

        for cb in self._callbacks:
            try:
                cb(report)
            except Exception as e:
                logger.error("Feedback callback failed: %s", e)

        if evolution.suggestions:
            logger.info(
                "Feedback report generated: %d suggestions",
                len(evolution.suggestions),
            )

        return report

    def recent_reports(self, limit: int = 10) -> List[FeedbackReport]:
        """Return recent feedback reports."""
        return self._reports[-limit:]

    def summarize(self) -> Dict[str, Any]:
        """Summarize all feedback activity."""
        total_suggestions = sum(
            len(r.evolution.suggestions) for r in self._reports
        )
        return {
            "total_reports": len(self._reports),
            "total_suggestions": total_suggestions,
        }
