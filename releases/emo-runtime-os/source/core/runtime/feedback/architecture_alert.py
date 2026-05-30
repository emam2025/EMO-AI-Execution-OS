"""D9 — IRuntimeArchitectureAlert implementation.

Evaluates architectural violations at runtime, classifies severity,
and triggers the enforcement gate via EventBus.

LAW 14-16: CodeGraph-Driven Decomposition Laws enforcement.
§3.4.5: emo-guard thresholds for coupling and risk.

Ref: DEVELOPER.md §3.4.5, §15.6
Ref: Canon LAW 14-16
Ref: artifacts/design/d9/protocols/01_feedback_loop_protocols.py
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from core.runtime.models.feedback_models import (
    DriftAlert,
    DriftSeverity,
    FeedbackPolicy,
    ViolationType,
)

logger = logging.getLogger("emo_ai.feedback.architecture_alert")


SEVERITY_THRESHOLDS: Dict[str, float] = {
    "info": 0.05,
    "warning": 0.05,
    "critical": 0.1,
    "blocking": 0.2,
}


class ArchitectureAlert:
    """Evaluates architecture violations and triggers enforcement.

    LAW 14: Coupling thresholds enforce decomposition boundaries.
    LAW 16: Risk scores determine enforcement severity.
    """

    def __init__(self, policy: Optional[FeedbackPolicy] = None) -> None:
        self._policy = policy or FeedbackPolicy()

    def evaluate_violation(
        self,
        violation_type: ViolationType,
        source: str,
        target: str = "",
        score: float = 0.0,
    ) -> DriftAlert:
        """Evaluate an architectural violation and produce a DriftAlert.

        Args:
            violation_type: Type of architectural violation.
            source: Source node/module of the violation.
            target: Target node/module affected.
            score: Violation score (coupling delta, risk delta).

        Returns:
            DriftAlert with severity, deviation_score, action_required.
        """
        severity = self.classify_severity(score, violation_type)

        action_map: Dict[str, str] = {
            "coupling_increase": "Review and refactor cross-boundary dependencies",
            "risk_score_exceeded": "Decompose or redistribute node responsibilities",
            "boundary_violation": "Enforce boundary — move access behind interface",
            "infrastructure_leakage": "Isolate infrastructure behind abstraction layer",
            "circular_dependency": "Break cycle with interface extraction",
            "hotspot_detected": "Monitor and consider decomposition",
            "decomposition_required": "Immediate decomposition required (LAW 16)",
        }

        law_refs: list = []
        if violation_type in (ViolationType.COUPLING_INCREASE, ViolationType.BOUNDARY_VIOLATION):
            law_refs.append("LAW 14")
        if violation_type in (ViolationType.RISK_SCORE_EXCEEDED, ViolationType.DECOMPOSITION_REQUIRED):
            law_refs.append("LAW 16")
        if violation_type == ViolationType.INFRASTRUCTURE_LEAKAGE:
            law_refs.append("LAW 13")

        return DriftAlert(
            alert_id=uuid.uuid4().hex[:16],
            deviation_score=round(score, 4),
            violation_type=violation_type.value,
            severity=severity.value,
            source_module=source,
            target_module=target,
            action_required=action_map.get(violation_type.value, "Investigate"),
            law_refs=law_refs,
            timestamp=time.time(),
        )

    def classify_severity(
        self,
        deviation_score: float,
        violation_type: ViolationType,
    ) -> DriftSeverity:
        """Classify the severity of a deviation.

        Thresholds:
          - 0.0–0.05: INFO
          - 0.05–0.1: WARNING
          - 0.1–0.2: CRITICAL
          - >0.2: BLOCKING

        Special cases:
          - BOUNDARY_VIOLATION → always at least WARNING
          - INFRASTRUCTURE_LEAKAGE → always at least CRITICAL
          - CIRCULAR_DEPENDENCY → always at least CRITICAL
          - DECOMPOSITION_REQUIRED → always BLOCKING

        Args:
            deviation_score: Normalized deviation (0.0–1.0).
            violation_type: Type of violation.

        Returns:
            Classified DriftSeverity.
        """
        if violation_type == ViolationType.DECOMPOSITION_REQUIRED:
            return DriftSeverity.BLOCKING
        if violation_type == ViolationType.INFRASTRUCTURE_LEAKAGE:
            return DriftSeverity.CRITICAL
        if violation_type == ViolationType.CIRCULAR_DEPENDENCY:
            return DriftSeverity.CRITICAL
        if violation_type == ViolationType.BOUNDARY_VIOLATION:
            if deviation_score >= 0.1:
                return DriftSeverity.CRITICAL
            return DriftSeverity.WARNING
        if deviation_score > self._policy.drift_block_threshold:
            return DriftSeverity.BLOCKING
        if deviation_score > self._policy.drift_warning_threshold:
            return DriftSeverity.CRITICAL
        if deviation_score > self._policy.drift_warning_threshold / 2:
            return DriftSeverity.WARNING
        return DriftSeverity.INFO

    def trigger_enforcement_gate(
        self,
        alert: DriftAlert,
        event_bus: Optional[Any] = None,
    ) -> bool:
        """Trigger the enforcement gate for BLOCKING or CRITICAL alerts.

        Actions:
          - CRITICAL: Emit "runtime.drift.critical" → EventBus
          - BLOCKING: Emit "runtime.drift.blocking" + set flag
          - WARNING/INFO: Log only

        Args:
            alert: DriftAlert to act upon.
            event_bus: Optional IEventBus for event emission.

        Returns:
            True if enforcement gate was triggered.
        """
        severity = DriftSeverity(alert.severity)

        if severity == DriftSeverity.BLOCKING:
            logger.warning(
                "ENFORCEMENT GATE: %s — %s (score=%.4f, laws=%s)",
                alert.violation_type, alert.action_required,
                alert.deviation_score, alert.law_refs,
            )
            if event_bus is not None:
                try:
                    from core.models.events import ExecutionEvent
                    event = ExecutionEvent(
                        event_id=uuid.uuid4().hex[:16],
                        event_type="ENFORCEMENT_GATE",
                        timestamp=time.time(),
                        source="ArchitectureAlert",
                        payload=alert.__dict__,
                    )
                    event_bus.publish("runtime.drift.blocking", event)
                except Exception as e:
                    logger.error("Failed to publish blocking event: %s", e)
            return True

        if severity == DriftSeverity.CRITICAL:
            logger.info(
                "CRITICAL drift: %s (score=%.4f) — notifying",
                alert.violation_type, alert.deviation_score,
            )
            if event_bus is not None:
                try:
                    from core.models.events import ExecutionEvent
                    event = ExecutionEvent(
                        event_id=uuid.uuid4().hex[:16],
                        event_type="DRIFT_CRITICAL",
                        timestamp=time.time(),
                        source="ArchitectureAlert",
                        payload=alert.__dict__,
                    )
                    event_bus.publish("runtime.drift.critical", event)
                except Exception as e:
                    logger.error("Failed to publish critical event: %s", e)
            return True

        logger.debug(
            "Non-blocking drift: %s (severity=%s, score=%.4f)",
            alert.violation_type, severity.value, alert.deviation_score,
        )
        return False
