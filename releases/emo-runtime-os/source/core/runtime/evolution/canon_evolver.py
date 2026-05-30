"""GAP 4 — CanonEvolver: suggestion-based Canon evolution.

IMPORTANT — SAFETY CONSTRAINT:
  This module does NOT auto-mutate Canon rules.
  It produces REFINEMENT SUGGESTIONS only.
  Human approval is required before any change.

  "Self-modifying systems are dangerous — we suggest, humans decide."

Flow:
  Runtime data → RuleRefiner → suggestions → CanonEvolver (filter + prioritize)
  → human review → apply (external)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.runtime.evolution.rule_refiner import RefinementSuggestion, RuleRefiner

logger = logging.getLogger("emo_ai.evolution.evolver")


@dataclass
class EvolutionReport:
    """A report of suggested Canon refinements for human review."""
    suggestions: List[RefinementSuggestion] = field(default_factory=list)
    generated_at: float = 0.0
    data_summary: Dict[str, Any] = field(default_factory=dict)
    approved: bool = False
    approved_by: str = ""
    audit_id: str = ""
    rollback_token: str = ""


class EvolutionPolicy:
    """Policy controlling suggestion filtering.

    - conservative: only surface high-confidence suggestions (conf > 0.8)
    - balanced: surface suggestions with conf > 0.5
    - verbose: surface all suggestions
    """

    MODES = ("conservative", "balanced", "verbose")

    def __init__(self, mode: str = "balanced"):
        if mode not in self.MODES:
            raise ValueError(f"Unknown evolution mode: {mode}")
        self._mode = mode
        self._min_confidence = {"conservative": 0.8, "balanced": 0.5, "verbose": 0.0}[mode]

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    @property
    def mode(self) -> str:
        return self._mode


class CanonEvolver:
    """Suggestion-based Canon evolution.

    Takes RuleRefiner suggestions and produces an EvolutionReport
    for human review. Does NOT apply mutations automatically.

    Usage:
        evolver = CanonEvolver()
        report = evolver.evolve({"failures": [...], "total_executions": 100})
        for suggestion in report.suggestions:
            print(f"Suggest: {suggestion.rule_id}.{suggestion.field}")
            print(f"  From {suggestion.current_value} → {suggestion.suggested_value}")
            print(f"  Confidence: {suggestion.confidence:.2f}")
            print(f"  Evidence: {suggestion.evidence}")
    """

    def __init__(
        self,
        refiner: Optional[RuleRefiner] = None,
        policy: Optional[EvolutionPolicy] = None,
        *,
        approval_func: Optional[Callable[[List[RefinementSuggestion]], bool]] = None,
        audit_log: Optional[Callable[[Dict[str, Any]], None]] = None,
        rollback_func: Optional[Callable[[str], bool]] = None,
    ):
        self._refiner = refiner or RuleRefiner()
        self._policy = policy or EvolutionPolicy()
        self._approval_func = approval_func
        self._audit_log = audit_log
        self._rollback_func = rollback_func
        self._audit_trail: List[Dict[str, Any]] = []

    @property
    def refiner(self) -> RuleRefiner:
        return self._refiner

    @property
    def policy(self) -> EvolutionPolicy:
        return self._policy

    @property
    def audit_trail(self) -> List[Dict[str, Any]]:
        return list(self._audit_trail)

    def rollback(self, token: str) -> bool:
        if self._rollback_func is None:
            logger.warning("No rollback function configured — rollback unavailable")
            return False
        return self._rollback_func(token)

    def request_approval(self, suggestions: List[RefinementSuggestion]) -> bool:
        if self._approval_func is None:
            logger.info("No approval gate configured — evolution proceeds unchecked")
            return True
        return self._approval_func(suggestions)

    def _record_audit(self, entry: Dict[str, Any]) -> None:
        self._audit_trail.append(entry)
        if self._audit_log:
            self._audit_log(entry)

    def evolve(
        self,
        runtime_data: Dict[str, Any],
        *,
        approved_by: str = "",
    ) -> EvolutionReport:
        """Analyze runtime data and produce an evolution report.

        Step 1: RuleRefiner analyzes execution data → refinement suggestions
        Step 2: Filter by policy confidence
        Step 3: Request approval (LAW 28 — human-in-the-loop gate)
        Step 4: Record audit trail (LAW 29 — immutable audit log)
        Step 5: Return EvolutionReport with rollback token (LAW 30)

        Args:
            runtime_data: Execution data including failures, latencies,
                         enforcement events, hotspots.
            approved_by: Human identifier who approved this evolution.
                         Empty string means approval was not given.

        Returns:
            EvolutionReport with filtered suggestions for human review.
        """
        import time

        raw_suggestions = self._refiner.analyze_execution_data(runtime_data)

        filtered = [
            s for s in raw_suggestions
            if s.confidence >= self._policy.min_confidence
        ]

        audit_id = uuid.uuid4().hex[:16]
        rollback_token = uuid.uuid4().hex[:24]
        approved = self.request_approval(filtered)

        report = EvolutionReport(
            suggestions=filtered,
            generated_at=time.time(),
            data_summary={
                "total_executions": runtime_data.get("total_executions", 0),
                "failure_count": len(runtime_data.get("failures", [])),
                "suggestion_count": len(filtered),
            },
            approved=approved,
            approved_by=approved_by if approved else "",
            audit_id=audit_id,
            rollback_token=rollback_token if approved else "",
        )

        # LAW 29 — immutable audit log
        audit_entry = {
            "audit_id": audit_id,
            "timestamp": time.time(),
            "approved": approved,
            "approved_by": approved_by if approved else "",
            "suggestion_count": len(filtered),
            "suggestions": [
                {
                    "rule_id": s.rule_id,
                    "field": s.field,
                    "current_value": s.current_value,
                    "suggested_value": s.suggested_value,
                    "confidence": s.confidence,
                    "evidence": s.evidence,
                }
                for s in filtered
            ],
            "policy_mode": self._policy.mode,
            "data_summary": report.data_summary,
        }
        self._record_audit(audit_entry)

        if filtered:
            logger.info(
                "Evolution report %s: %d suggestions (conf >= %.2f) "
                "approved=%s by=%s",
                audit_id, len(filtered), self._policy.min_confidence,
                approved, approved_by or "none",
            )
            for s in filtered:
                logger.info(
                    "  %s.%s: %.1f → %.1f (conf=%.2f) — %s",
                    s.rule_id, s.field,
                    s.current_value, s.suggested_value,
                    s.confidence, s.evidence[:60],
                )

        return report
