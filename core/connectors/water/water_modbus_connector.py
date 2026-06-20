"""Water Modbus Connector — Read-Only V1 Implementation.

Mock Modbus connector for reading telemetry from water quality sensors
(pH, turbidity, chlorine). Read-only: observe, never write control commands.
Publishes CONNECTOR_READ_SUCCESS / CONNECTOR_READ_FAILURE events.

Ref: RC17.4.2 — Water Connectors (Read-Only V1)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from core.connectors.manufacturing.connector_error import ConnectorError

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus


class WaterModbusConnector:
    """Mock Modbus read-only connector for water quality sensors.

    Simulates reading telemetry from pH sensors, turbidity meters,
    and chlorine analyzers. Read-only: never issues write commands.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 502,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._event_bus = event_bus
        self._register_values: Dict[str, Any] = {}
        self._subscriptions: Dict[str, Callable[[Any], None]] = {}

    def set_register_value(self, register_id: str, value: Any) -> None:
        """Pre-populate a register value for testing."""
        self._register_values[register_id] = value

    def read_registers(self, register_ids: List[str]) -> Dict[str, Any]:
        """Read values from Modbus registers (sync)."""
        results: Dict[str, Any] = {}
        for rid in register_ids:
            if rid in self._register_values:
                results[rid] = self._register_values[rid]
            else:
                self._publish_read_event("read_registers", register_ids, success=False)
                raise ConnectorError(
                    f"Water Modbus register not found: {rid}",
                    connector_type="water_modbus",
                    node_id=rid,
                )
        self._publish_read_event("read_registers", register_ids, success=True)
        return results

    async def read_registers_async(self, register_ids: List[str]) -> Dict[str, Any]:
        """Read values from Modbus registers (async)."""
        results: Dict[str, Any] = {}
        for rid in register_ids:
            if rid in self._register_values:
                results[rid] = self._register_values[rid]
            else:
                self._publish_read_event(
                    "read_registers_async", register_ids, success=False
                )
                raise ConnectorError(
                    f"Water Modbus register not found: {rid}",
                    connector_type="water_modbus",
                    node_id=rid,
                )
        self._publish_read_event("read_registers_async", register_ids, success=True)
        return results

    def subscribe_readonly(
        self, register_id: str, callback: Callable[[Any], None]
    ) -> str:
        """Subscribe to register value changes (read-only)."""
        sub_id = f"sub_{register_id}_{len(self._subscriptions)}"
        self._subscriptions[sub_id] = callback
        return sub_id

    def _publish_read_event(
        self, operation: str, register_ids: List[str], success: bool
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
            trace_id=f"water_modbus-{operation}",
            payload={
                "connector_type": "water_modbus",
                "operation": operation,
                "register_ids": register_ids,
                "success": success,
                "host": self._host,
                "port": self._port,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(topic, event))
        except RuntimeError:
            pass
