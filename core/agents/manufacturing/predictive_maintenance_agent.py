"""PredictiveMaintenanceAgent — Predictive Failure Detection.

Monitors incoming metrics, detects patterns indicating imminent failures
(overheat, vibration), generates PredictiveAlerts via IEventBus.

Ref: RC17.2.2 — Predictive Maintenance Agent
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.agent import (
    AgentAudit,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentSkills,
)
from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.models.manufacturing_advanced import FailureMode, PredictiveAlert

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class PredictiveMaintenanceAgent:
    """Predictive maintenance agent — monitors metrics, detects failures.

    Subscribes to CONNECTOR_READ_SUCCESS events, applies heuristic rules,
    and publishes PREDICTIVE_ALERT events when thresholds are exceeded.
    """

    THRESHOLD_OVERHEAT: float = 95.0
    THRESHOLD_VIBRATION: float = 5.0
    OVERHEAT_CONFIDENCE: float = 0.85
    VIBRATION_CONFIDENCE: float = 0.80
    OVERHEAT_TTF_HOURS: float = 48.0
    VIBRATION_TTF_HOURS: float = 72.0

    def __init__(
        self,
        identity: AgentIdentity,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._identity = identity
        self._event_bus = event_bus
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["predictive_analyzer", "metric_monitor"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "monitor_metrics",
                "generate_alert",
                "publish_predictive_alert",
            ],
            requires_approval_for=[],
        )
        self._audit = AgentAudit()
        self._status = "created"
        self._subscription_id: Optional[str] = None

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    @property
    def skills(self) -> AgentSkills:
        return self._skills

    @property
    def permissions(self) -> AgentPermissions:
        return self._permissions

    @property
    def audit(self) -> AgentAudit:
        return self._audit

    def activate(self) -> None:
        self._status = "active"
        if self._event_bus is not None:
            self._subscription_id = self._event_bus.subscribe(
                EventTopic.CONNECTOR_READ_SUCCESS,
                self._handle_connector_read,
            )
        self._audit.record_action(
            action="agent.activate",
            context={"agent_id": self._identity.id},
            result={"status": "active"},
        )

    def suspend(self, reason: str) -> None:
        self._status = "suspended"
        if self._event_bus is not None and self._subscription_id is not None:
            self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        self._audit.record_action(
            action="agent.suspend",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "suspended"},
        )

    def terminate(self, reason: str) -> None:
        self._status = "terminated"
        if self._event_bus is not None and self._subscription_id is not None:
            self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        self._audit.record_action(
            action="agent.terminate",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "terminated"},
        )

    def process_metric(
        self, asset_id: str, metric_name: str, value: float
    ) -> Optional[PredictiveAlert]:
        """Process a single metric and return an alert if threshold exceeded."""
        alert: Optional[PredictiveAlert] = None

        if metric_name == "temperature" and value > self.THRESHOLD_OVERHEAT:
            alert = PredictiveAlert(
                asset_id=asset_id,
                failure_mode=FailureMode.OVERHEAT,
                confidence_score=self.OVERHEAT_CONFIDENCE,
                estimated_time_to_failure_hours=self.OVERHEAT_TTF_HOURS,
                recommended_action=(
                    f"Temperature {value}°C exceeds threshold {self.THRESHOLD_OVERHEAT}°C. "
                    f"Schedule cooling system inspection within {self.OVERHEAT_TTF_HOURS:.0f} hours."
                ),
            )
        elif metric_name == "vibration" and value > self.THRESHOLD_VIBRATION:
            alert = PredictiveAlert(
                asset_id=asset_id,
                failure_mode=FailureMode.VIBRATION,
                confidence_score=self.VIBRATION_CONFIDENCE,
                estimated_time_to_failure_hours=self.VIBRATION_TTF_HOURS,
                recommended_action=(
                    f"Vibration {value} exceeds threshold {self.THRESHOLD_VIBRATION}. "
                    f"Schedule bearing inspection within {self.VIBRATION_TTF_HOURS:.0f} hours."
                ),
            )

        if alert is not None:
            self._publish_alert(alert)

        return alert

    def _publish_alert(self, alert: PredictiveAlert) -> None:
        """Publish PREDICTIVE_ALERT event and record audit."""
        event = ExecutionEvent(
            topic=EventTopic.PREDICTIVE_ALERT,
            payload={
                "alert_id": alert.alert_id,
                "asset_id": alert.asset_id,
                "failure_mode": alert.failure_mode.value,
                "confidence_score": alert.confidence_score,
                "estimated_time_to_failure_hours": alert.estimated_time_to_failure_hours,
                "recommended_action": alert.recommended_action,
            },
            trace_id=alert.alert_id,
            metadata=EventMetadata(source=f"agent.{self._identity.id}"),
        )

        self._audit.record_action(
            action="predictive_alert.generated",
            context={
                "agent_id": self._identity.id,
                "asset_id": alert.asset_id,
                "failure_mode": alert.failure_mode.value,
                "confidence_score": alert.confidence_score,
            },
            result={"alert_id": alert.alert_id, "status": "published"},
        )

        if self._event_bus is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.PREDICTIVE_ALERT, event)
                )
            except RuntimeError:
                pass

    def _handle_connector_read(self, event: ExecutionEvent) -> None:
        """Handle incoming CONNECTOR_READ_SUCCESS event."""
        payload = event.payload
        asset_id = payload.get("asset_id", "")
        metric_name = payload.get("metric_name", "")
        value = payload.get("value", 0.0)

        if metric_name and asset_id:
            self.process_metric(asset_id, metric_name, value)
