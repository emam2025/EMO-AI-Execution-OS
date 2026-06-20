"""MQTT Connector — Read-Only V1 Implementation.

Mock MQTT connector for subscribing to energy telemetry topics.
Read-only: subscribes to topics, never publishes control commands.
Publishes CONNECTOR_READ_SUCCESS / CONNECTOR_READ_FAILURE events.

Ref: RC17.3 — Energy Pack Foundation
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from core.connectors.manufacturing.connector_error import ConnectorError

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus


class MQTTConnector:
    """Mock MQTT read-only connector.

    Simulates subscribing to MQTT topics for energy telemetry.
    Read-only: subscribes to topics, never publishes.
    """

    def __init__(
        self,
        broker_url: str = "mqtt://localhost:1883",
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._broker_url = broker_url
        self._event_bus = event_bus
        self._topic_values: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Callable[[Any], None]] = {}

    def set_topic_value(self, topic: str, value: Any) -> None:
        """Pre-populate a topic value for testing."""
        self._topic_values[topic] = value

    def read_topics(self, topics: List[str]) -> Dict[str, Any]:
        """Read values from MQTT topics (sync)."""
        results: Dict[str, Any] = {}
        for topic in topics:
            if topic in self._topic_values:
                results[topic] = self._topic_values[topic]
            else:
                self._publish_read_event("read_topics", topics, success=False)
                raise ConnectorError(
                    f"MQTT topic not found: {topic}",
                    connector_type="mqtt",
                    node_id=topic,
                )
        self._publish_read_event("read_topics", topics, success=True)
        return results

    async def read_topics_async(self, topics: List[str]) -> Dict[str, Any]:
        """Read values from MQTT topics (async)."""
        results: Dict[str, Any] = {}
        for topic in topics:
            if topic in self._topic_values:
                results[topic] = self._topic_values[topic]
            else:
                self._publish_read_event("read_topics_async", topics, success=False)
                raise ConnectorError(
                    f"MQTT topic not found: {topic}",
                    connector_type="mqtt",
                    node_id=topic,
                )
        self._publish_read_event("read_topics_async", topics, success=True)
        return results

    def subscribe_topic(
        self, topic: str, callback: Callable[[Any], None]
    ) -> str:
        """Subscribe to an MQTT topic (read-only)."""
        sub_id = f"sub_{topic}_{len(self._subscriptions)}"
        self._subscriptions[sub_id] = callback
        return sub_id

    def _publish_read_event(
        self, operation: str, topics: List[str], success: bool
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
            trace_id=f"mqtt-{operation}",
            payload={
                "connector_type": "mqtt",
                "operation": operation,
                "topics": topics,
                "success": success,
                "broker_url": self._broker_url,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(topic, event))
        except RuntimeError:
            pass
