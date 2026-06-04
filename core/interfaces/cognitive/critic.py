"""Phase G — ICritic Protocol.

Plan evaluation and risk assessment.

LAW 8: Every plan assessed before execution.
RULE 3: Adaptation requires ≥2 critic signals OR ≥0.8 confidence.

Ref: Canon LAW 8, RULE 3
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ICritic(Protocol):
    """Plan evaluation and risk assessment.

    evaluate_plan(plan_id):        Score a plan and return assessment.
    suggest_corrections(plan_id):  Recommend improvements.
    risk_assess(plan_id):          Evaluate risk level and failure modes.
    """

    def evaluate_plan(self, plan_id: str) -> Dict[str, Any]:
        """Evaluate plan quality.

        Returns dict with score, reason, and optional detailed_feedback.
        """
        ...

    def suggest_corrections(self, plan_id: str) -> List[str]:
        """Suggest corrections for a plan.

        Returns list of correction descriptions.
        """
        ...

    def risk_assess(self, plan_id: str) -> Dict[str, Any]:
        """Assess risk level and failure modes.

        Returns dict with risk_level (str), failure_modes (list).
        """
        ...
