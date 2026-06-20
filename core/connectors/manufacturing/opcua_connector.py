"""OPC-UA Connector — Read-Only V1 Implementation.

Mock OPC-UA connector for reading node values from simulated PLCs.
Publishes CONNECTOR_READ_SUCCESS / CONNECTOR_READ_FAILURE events.

Ref: RC17.1.4 — Manufacturing Connectors (Read-Only V1)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from core.connectors.manufacturing.connector_error import ConnectorError

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus


class OPCUAConnector:
    """Mock OPC-UA read-only connector.

    Simulates reading node values from a simulated PLC server.
    Publishes read events to IEventBus when available.
    """

    def __init__(
        self,
        endpoint_url: str = "opc.tcp://localhost:4840",
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._event_bus = event_bus
        self._node_values: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Callable[[Any], None]] = {}

    def set_node_value(self, node_id: str, value: Any) -> None:
        """Pre-populate a node value for testing."""
        self._node_values[node_id] = value

    def read_node_values(self, node_ids: List[str]) -> Dict[str, Any]:
        """Read values from OPC-UA nodes (sync)."""
        results: Dict[str, Any] = {}
        for nid in node_ids:
            if nid in self._node_values:
                results[nid] = self._node_values[nid]
            else:
                raise ConnectorError(
                    f"Node not found: {nid}",
                    connector_type="opcua",
                    node_id=nid,
                )
        self._publish_read_event("read_node_values", node_ids, success=True)
        return results

    async def read_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Read values from OPC-UA nodes (async)."""
        results: Dict[str, Any] = {}
        for nid in node_ids:
            if nid in self._node_values:
                results[nid] = self._node_values[nid]
            else:
                self._publish_read_event("read_nodes", node_ids, success=False)
                raise ConnectorError(
                    f"Node not found: {nid}",
                    connector_type="opcua",
                    node_id=nid,
                )
        self._publish_read_event("read_nodes", node_ids, success=True)
        return results

    def subscribe_readonly(
        self, node_id: str, callback: Callable[[Any], None]
    ) -> str:
        """Subscribe to node value changes (read-only)."""
        sub_id = f"sub_{node_id}_{len(self._subscriptions)}"
        self._subscriptions[sub_id] = callback
        return sub_id

    def _publish_read_event(
        self, operation: str, node_ids: List[str], success: bool
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
            trace_id=f"opcua-{operation}",
            payload={
                "connector_type": "opcua",
                "operation": operation,
                "node_ids": node_ids,
                "success": success,
                "endpoint_url": self._endpoint_url,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(topic, event))
        except RuntimeError:
            pass
