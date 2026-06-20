"""Water SCADA Connector — Read-Only V1 Implementation.

Mock SCADA connector for reading telemetry from water treatment plants
and pump stations. Read-only: observe, never write control commands.
Publishes CONNECTOR_READ_SUCCESS / CONNECTOR_READ_FAILURE events.

Ref: RC17.4.2 — Water Connectors (Read-Only V1)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from core.connectors.manufacturing.connector_error import ConnectorError

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus


class WaterSCADAConnector:
    """Mock SCADA read-only connector for water infrastructure.

    Simulates reading telemetry tags from water treatment plants
    and pump stations. Read-only: never issues write/control commands.
    """

    def __init__(
        self,
        endpoint_url: str = "scada://localhost:502",
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._event_bus = event_bus
        self._tag_values: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Callable[[Any], None]] = {}

    def set_tag_value(self, tag_id: str, value: Any) -> None:
        """Pre-populate a tag value for testing."""
        self._tag_values[tag_id] = value

    def read_tags(self, tag_ids: List[str]) -> Dict[str, Any]:
        """Read values from SCADA tags (sync)."""
        results: Dict[str, Any] = {}
        for tid in tag_ids:
            if tid in self._tag_values:
                results[tid] = self._tag_values[tid]
            else:
                self._publish_read_event("read_tags", tag_ids, success=False)
                raise ConnectorError(
                    f"Water SCADA tag not found: {tid}",
                    connector_type="water_scada",
                    node_id=tid,
                )
        self._publish_read_event("read_tags", tag_ids, success=True)
        return results

    async def read_tags_async(self, tag_ids: List[str]) -> Dict[str, Any]:
        """Read values from SCADA tags (async)."""
        results: Dict[str, Any] = {}
        for tid in tag_ids:
            if tid in self._tag_values:
                results[tid] = self._tag_values[tid]
            else:
                self._publish_read_event("read_tags_async", tag_ids, success=False)
                raise ConnectorError(
                    f"Water SCADA tag not found: {tid}",
                    connector_type="water_scada",
                    node_id=tid,
                )
        self._publish_read_event("read_tags_async", tag_ids, success=True)
        return results

    def subscribe_readonly(
        self, tag_id: str, callback: Callable[[Any], None]
    ) -> str:
        """Subscribe to tag value changes (read-only)."""
        sub_id = f"sub_{tag_id}_{len(self._subscriptions)}"
        self._subscriptions[sub_id] = callback
        return sub_id

    def _publish_read_event(
        self, operation: str, tag_ids: List[str], success: bool
    ) -> None:
        """Publish a read event to the event bus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        topic = (
            EventTopic.CONNECTOR_READ_SUCCESS
            if success
            else EventTopic.CONNECTOR_READ_FAILURE
        )
        event = ExecutionEvent(
            topic=topic,
            trace_id=f"water_scada-{operation}",
            payload={
                "connector_type": "water_scada",
                "operation": operation,
                "tag_ids": tag_ids,
                "success": success,
                "endpoint_url": self._endpoint_url,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(topic, event))
        except RuntimeError:
            pass
