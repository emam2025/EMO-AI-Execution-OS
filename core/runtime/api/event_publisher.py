"""F1 — Event Publisher for Unified Runtime API.

Publishes runtime.execution.*, runtime.worker.*, runtime.lease.*,
runtime.checkpoint.*, runtime.replay.*, runtime.state.* events to IEventBus.

LAW 5: Every execution MUST be observable.
LAW 12: Every event carries trace_id for correlation.

Ref: DEVELOPER.md §15.2 (Observability Plane)
Ref: artifacts/design/f1/04_integration_blueprint.md §3
Ref: Canon LAW 5, LAW 12
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from core.interfaces.event_bus import IEventBus
from core.models.events import ExecutionEvent, make_trace_id

logger = logging.getLogger("emo_ai.api.event_publisher")


class EventPublisher:
    """Publishes execution lifecycle events to EventBus.

    All events are published under the runtime.execution.* topic hierarchy.
    Every event carries trace_id for cross-layer correlation (LAW 12).
    """

    _EXECUTION_EVENTS = {
        "runtime.execution.submitted",
        "runtime.execution.queued",
        "runtime.execution.leased",
        "runtime.execution.planned",
        "runtime.execution.started",
        "runtime.execution.progress",
        "runtime.execution.completed",
        "runtime.execution.failed",
        "runtime.execution.cancelled",
        "runtime.execution.rolled_back",
        "runtime.execution.resumed",
        "runtime.worker.registered",
        "runtime.worker.scaled",
        "runtime.worker.unregistered",
        "runtime.worker.drained",
        "runtime.lease.acquired",
        "runtime.lease.released",
        "runtime.lease.expired",
        "runtime.checkpoint.saved",
        "runtime.checkpoint.restored",
        "runtime.replay.started",
        "runtime.replay.completed",
        "runtime.replay.mismatch",
        "runtime.state.transition",
    }

    def __init__(self, event_bus: IEventBus):
        self._event_bus = event_bus

    def publish_execution_event(
        self,
        topic: str,
        trace_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """Publish a runtime.execution.* event.

        LAW 5: Execution events are observable via EventBus.
        LAW 12: Every event carries trace_id.

        Args:
            topic: Event topic (e.g. runtime.execution.submitted).
            trace_id: Correlation ID across all layers.
            payload: Event payload.
        """
        if topic not in self._EXECUTION_EVENTS:
            logger.warning("Unknown event topic: %s", topic)

        event_type = topic.split(".")[-1].upper()
        event = ExecutionEvent(
            event_id=uuid.uuid4().hex[:16],
            event_type=event_type,
            timestamp=time.time(),
            source="UnifiedRuntime",
            payload=payload,
            trace_id=trace_id,
        )
        self._event_bus.publish(topic, event)
        logger.debug("Published %s (trace=%s)", topic, trace_id)

    def publish_state_transition(
        self,
        trace_id: str,
        ticket_id: str,
        from_state: str,
        to_state: str,
    ) -> None:
        """Publish a state transition event.

        Args:
            trace_id: Correlation ID.
            ticket_id: Execution ticket.
            from_state: Previous state.
            to_state: New state.
        """
        self.publish_execution_event(
            "runtime.state.transition",
            trace_id,
            {
                "ticket_id": ticket_id,
                "from": from_state,
                "to": to_state,
            },
        )

    def publish_checkpoint_saved(
        self,
        trace_id: str,
        session_id: str,
    ) -> None:
        """Publish a checkpoint saved event."""
        self.publish_execution_event(
            "runtime.checkpoint.saved",
            trace_id,
            {"session_id": session_id},
        )

    def publish_checkpoint_restored(
        self,
        trace_id: str,
        session_id: str,
    ) -> None:
        """Publish a checkpoint restored event."""
        self.publish_execution_event(
            "runtime.checkpoint.restored",
            trace_id,
            {"session_id": session_id},
        )

    def publish_lease_event(
        self,
        topic: str,
        trace_id: str,
        ticket_id: str,
        lease_id: str,
        owner: str,
    ) -> None:
        """Publish a runtime.lease.* event.

        Args:
            topic: runtime.lease.acquired | released | expired.
            trace_id: Correlation ID.
            ticket_id: Execution ticket.
            lease_id: Lease identifier.
            owner: Lease owner.
        """
        self.publish_execution_event(
            topic,
            trace_id,
            {
                "ticket_id": ticket_id,
                "lease_id": lease_id,
                "owner": owner,
            },
        )

    def publish_worker_event(
        self,
        topic: str,
        trace_id: str,
        worker_id: str,
        **extra: Any,
    ) -> None:
        """Publish a runtime.worker.* event.

        Args:
            topic: runtime.worker.registered | scaled | unregistered | drained.
            trace_id: Correlation ID.
            worker_id: Worker identifier.
            **extra: Additional payload fields.
        """
        payload: Dict[str, Any] = {"worker_id": worker_id}
        payload.update(extra)
        self.publish_execution_event(topic, trace_id, payload)

    def publish_replay_event(
        self,
        topic: str,
        trace_id: str,
        execution_id: str,
        **extra: Any,
    ) -> None:
        """Publish a runtime.replay.* event.

        Args:
            topic: runtime.replay.started | completed | mismatch.
            trace_id: Correlation ID.
            execution_id: Execution identifier.
            **extra: Additional payload fields.
        """
        payload: Dict[str, Any] = {"execution_id": execution_id}
        payload.update(extra)
        self.publish_execution_event(topic, trace_id, payload)
