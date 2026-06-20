"""Guardrails Engine Implementation.

Monitors agent behavior and performance, detecting drifts and regressions.

Ref: P8.2 — Guardrails Engine
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

from core.models.guardrails import DriftType, GuardrailAlert, Severity


class GuardrailsEngine:
    """Monitors agent behavior and performance against baselines.

    Stateful: maintains per-agent baselines for regression detection.
    Evented: every alert is published via IEventBus.
    """

    # Regression threshold: 20% degradation triggers alert
    REGRESSION_THRESHOLD = 0.20

    # Behavioral drift: if write actions exceed 30% of total for a read-only agent
    BEHAVIORAL_DRIFT_THRESHOLD = 0.30

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._baselines: Dict[str, Dict[str, float]] = {}
        self._allowed_actions: Dict[str, List[str]] = {}

    def record_baseline(self, agent_id: str, baseline_metrics: Dict[str, float]) -> None:
        """Record baseline metrics for an agent."""
        self._baselines[agent_id] = baseline_metrics.copy()

    def set_allowed_actions(self, agent_id: str, allowed_actions: List[str]) -> None:
        """Define allowed actions for behavioral drift detection."""
        self._allowed_actions[agent_id] = list(allowed_actions)

    def _publish_alert(self, alert: GuardrailAlert) -> None:
        """Publish guardrail alert synchronously if event_bus is available."""
        if self._event_bus is not None:
            import asyncio
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.GUARDRAIL_ALERT,
                trace_id=f"guardrails-{alert.agent_id}",
                payload={
                    "alert_id": alert.alert_id,
                    "agent_id": alert.agent_id,
                    "drift_type": alert.drift_type.value,
                    "severity": alert.severity.value,
                    "details": alert.details,
                    "action_taken": alert.action_taken,
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.GUARDRAIL_ALERT, event)
                )
            except RuntimeError:
                pass

    def evaluate_performance(
        self, agent_id: str, metrics: Dict[str, float]
    ) -> Optional[GuardrailAlert]:
        """Compare current metrics against baseline. Alert if regression > threshold.

        Regression detected when current value exceeds baseline by more than threshold.
        For metrics where lower is better (e.g., latency), higher current = regression.
        """
        baseline = self._baselines.get(agent_id)
        if baseline is None:
            return None

        for metric_name, current_value in metrics.items():
            baseline_value = baseline.get(metric_name)
            if baseline_value is None or baseline_value == 0:
                continue

            # Regression: current exceeds baseline by more than threshold
            if current_value > baseline_value * (1 + self.REGRESSION_THRESHOLD):
                regression_pct = ((current_value - baseline_value) / baseline_value) * 100
                severity = Severity.HIGH if regression_pct > 50 else Severity.MEDIUM
                alert = GuardrailAlert(
                    agent_id=agent_id,
                    drift_type=DriftType.PERFORMANCE_REGRESSION,
                    severity=severity,
                    details={
                        "metric": metric_name,
                        "baseline": baseline_value,
                        "current": current_value,
                        "regression_pct": round(regression_pct, 1),
                    },
                    action_taken="performance_alert",
                )
                self._publish_alert(alert)
                return alert

        return None

    def evaluate_behavior(
        self, agent_id: str, recent_actions: List[Dict[str, Any]]
    ) -> Optional[GuardrailAlert]:
        """Detect behavioral drift by analyzing recent action patterns."""
        allowed = self._allowed_actions.get(agent_id)
        if allowed is None or not recent_actions:
            return None

        # Count disallowed actions
        disallowed_count = 0
        for action in recent_actions:
            action_type = action.get("type", "")
            if action_type not in allowed:
                disallowed_count += 1

        total = len(recent_actions)
        if total == 0:
            return None

        disallowed_ratio = disallowed_count / total

        if disallowed_ratio > self.BEHAVIORAL_DRIFT_THRESHOLD:
            severity = Severity.CRITICAL if disallowed_ratio > 0.50 else Severity.HIGH
            alert = GuardrailAlert(
                agent_id=agent_id,
                drift_type=DriftType.BEHAVIORAL_DRIFT,
                severity=severity,
                details={
                    "total_actions": total,
                    "disallowed_count": disallowed_count,
                    "disallowed_ratio": round(disallowed_ratio * 100, 1),
                    "allowed_actions": allowed,
                },
                action_taken="behavioral_alert",
            )
            self._publish_alert(alert)
            return alert

        return None
