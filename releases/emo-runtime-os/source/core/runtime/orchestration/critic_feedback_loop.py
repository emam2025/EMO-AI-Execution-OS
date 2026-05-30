"""Phase G1 — CriticFeedbackLoop implementation.  # LAW-8 # RULE-3

Evaluates ExecutionPlan quality and aggregates critic signals.
Adaptation requires ≥2 critic signals OR confidence ≥ 0.8 (RULE 3).

Ref: Canon LAW 8 (Governance), RULE 3 (Feedback-Adaptation)
Ref: artifacts/design/g1/02_models.md §3
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.planning_models import CriticAssessment

logger = logging.getLogger("emo_ai.orchestration.critic_feedback_loop")


class CriticFeedbackLoop:  # LAW-8
    """Evaluates plans and provides critic signals.

    RULE 3: Adaptation requires ≥ 2 critic signals OR ≥ 0.8 confidence.
    Up to max_critic_signals assessments per plan, then aggregated.
    """

    def __init__(self, max_critic_signals: int = 5) -> None:
        self._max = max_critic_signals
        self._assessments: Dict[str, List[CriticAssessment]] = {}

    @property
    def max_critic_signals(self) -> int:
        return self._max

    def evaluate(  # LAW-8
        self,
        plan_id: str,
    ) -> CriticAssessment:
        signals = self._assessments.get(plan_id, [])
        if not signals:
            return CriticAssessment(
                assessor_id="critic_default",
                plan_id=plan_id,
                score=0.0,
                reason="No critic signals recorded",
            )
        scores = [s.score for s in signals if s.score is not None]
        avg = sum(scores) / len(scores) if scores else 0.0
        return CriticAssessment(
            assessor_id="critic_aggregator",
            plan_id=plan_id,
            score=avg,
            reason=f"Aggregate of {len(scores)} critic signals",
            detailed_feedback=(
                [s.reason for s in signals if s.reason]
            ),
        )

    def add_assessment(  # LAW-8
        self,
        assessment: CriticAssessment,
    ) -> None:
        plan_id = assessment.plan_id
        if plan_id not in self._assessments:
            self._assessments[plan_id] = []
        if len(self._assessments[plan_id]) < self._max:
            self._assessments[plan_id].append(assessment)
            logger.debug(
                "Added critic assessment for %s (score=%s)",
                plan_id,
                assessment.score,
            )

    def signal_count(  # RULE-3
        self,
        plan_id: str,
    ) -> int:
        return len(self._assessments.get(plan_id, []))

    def feedback_confidence(  # RULE-3
        self,
        plan_id: str,
    ) -> float:
        signals = self._assessments.get(plan_id, [])
        scores = [s.score for s in signals if s.score is not None]
        return sum(scores) / len(scores) if scores else 0.0

    def meets_adaptation_threshold(  # RULE-3
        self,
        plan_id: str,
    ) -> Tuple[bool, str]:
        count = self.signal_count(plan_id)
        confidence = self.feedback_confidence(plan_id)
        if count >= 2:
            return True, f"Critic signals {count} ≥ 2"
        if confidence >= 0.8:
            return True, f"Confidence {confidence:.2f} ≥ 0.8"
        return False, (
            f"Need ≥ 2 critic signals (got {count}) OR "
            f"confidence ≥ 0.8 (got {confidence:.2f})"
        )

    def reset(self) -> None:
        self._assessments.clear()
