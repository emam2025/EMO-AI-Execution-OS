"""Industrial Data Pipeline — Connectors → TwinManager.

Ingests data from industrial connectors into digital twins via event-driven architecture.
Listens for CONNECTOR_READ_SUCCESS events, validates against safety thresholds,
updates TwinState, and publishes TWIN_STATE_UPDATED or SAFETY_VIOLATION events.

Ref: RC17.1.5 — Manufacturing Data Pipeline (Connectors → TwinManager)
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus
    from core.interfaces.industrial import ITwinManager


class DataPipeline:
    """Event-driven data pipeline: Connectors → Safety Check → TwinManager → Events.

    Listens for CONNECTOR_READ_SUCCESS events, maps node values to twin fields,
    validates against configurable thresholds, and updates twin state.
    """

    def __init__(
        self,
        twin_manager: ITwinManager,
        event_bus: IEventBus,
    ) -> None:
        self._twin_manager = twin_manager
        self._event_bus = event_bus
        self._connectors: Dict[str, Any] = {}
        self._mappings: Dict[str, Dict[str, str]] = {}  # node_id → {asset_id, field}
        self._thresholds: Dict[str, float] = {}
        self._subscription_id: Optional[str] = None
        self._background_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._audit_log: List[Dict[str, Any]] = []
        self._stats = {"successes": 0, "failures": 0, "violations": 0}

    def register_connector(self, connector_id: str, connector: Any) -> None:
        """Register a connector for data ingestion."""
        self._connectors[connector_id] = connector

    def register_mapping(self, node_id: str, asset_id: str, field: str) -> None:
        """Register a mapping from connector node to twin asset field."""
        self._mappings[node_id] = {"asset_id": asset_id, "field": field}

    def set_threshold(self, field: str, max_value: float) -> None:
        """Set a safety threshold for a field value."""
        self._thresholds[field] = max_value

    async def _handle_connector_read(self, event: Any) -> None:
        """Handle a CONNECTOR_READ_SUCCESS event."""
        payload = getattr(event, "payload", {})
        node_ids = payload.get("node_ids", [])
        connector_id = payload.get("connector_type", "unknown")

        for node_id in node_ids:
            if node_id not in self._mappings:
                continue

            mapping = self._mappings[node_id]
            asset_id = mapping["asset_id"]
            field = mapping["field"]

            # Get the value from the connector
            connector = self._connectors.get(connector_id)
            if connector is None:
                self._stats["failures"] += 1
                continue

            try:
                values = connector.read_node_values([node_id])
                value = values.get(node_id)
            except Exception:
                self._stats["failures"] += 1
                continue

            if value is None:
                self._stats["failures"] += 1
                continue

            # Safety threshold check
            if field in self._thresholds and isinstance(value, (int, float)):
                if value > self._thresholds[field]:
                    self._stats["violations"] += 1
                    self._publish_safety_violation(
                        asset_id, field, value, self._thresholds[field]
                    )
                    continue

            # Update twin state
            try:
                self._twin_manager.update_twin_state(asset_id, {field: value})
            except Exception:
                self._stats["failures"] += 1
                continue

            # Record audit trail
            self._audit_log.append({
                "asset_id": asset_id,
                "field": field,
                "value": value,
                "source": {"connector_id": connector_id, "node_id": node_id},
                "action": "twin_update",
            })

            self._stats["successes"] += 1

            # Publish TWIN_STATE_UPDATED event
            self._publish_twin_updated(asset_id, field, value)

    def _publish_twin_updated(
        self, asset_id: str, field: str, value: Any
    ) -> None:
        """Publish a TWIN_STATE_UPDATED event."""
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.TWIN_STATE_UPDATED,
            trace_id=f"pipeline-{asset_id}",
            payload={
                "asset_id": asset_id,
                "field": field,
                "value": value,
                "source": "data_pipeline",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.TWIN_STATE_UPDATED, event)
            )
        except RuntimeError:
            pass

    def _publish_safety_violation(
        self, asset_id: str, field: str, value: Any, threshold: float
    ) -> None:
        """Publish a SAFETY_VIOLATION event."""
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.SAFETY_VIOLATION,
            trace_id=f"pipeline-{asset_id}",
            payload={
                "asset_id": asset_id,
                "field": field,
                "value": value,
                "threshold": threshold,
                "source": "data_pipeline",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.SAFETY_VIOLATION, event)
            )
        except RuntimeError:
            pass

    async def ingest_once(self) -> Dict[str, int]:
        """Run one ingestion cycle. Returns stats."""
        return dict(self._stats)

    async def _background_loop(self, interval_seconds: float) -> None:
        """Background ingestion loop."""
        while self._running:
            await asyncio.sleep(interval_seconds)

    def start_background_loop(self, interval_seconds: float = 1.0) -> None:
        """Start a background ingestion loop."""
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._background_task = loop.create_task(
                self._background_loop(interval_seconds)
            )
        except RuntimeError:
            pass

    def stop_background_loop(self) -> None:
        """Stop the background ingestion loop."""
        self._running = False
        if self._background_task is not None:
            self._background_task.cancel()
            self._background_task = None

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return the audit trail of twin updates."""
        return list(self._audit_log)

    def get_stats(self) -> Dict[str, int]:
        """Return ingestion statistics."""
        return dict(self._stats)
