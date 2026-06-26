"""Industrial Connector Protocols (Read-Only V1).

Defines read-only interfaces for industrial connectors.
No write/execute operations in this phase.

Ref: RC17.1.1 — Manufacturing Domain Models & Policies
Ref: RC17.1.4 — Manufacturing Connectors (Read-Only V1)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol


class IOPCUAConnector(Protocol):
    """Protocol for OPC-UA read-only connector."""

    def read_node_values(self, node_ids: List[str]) -> Dict[str, Any]:
        """Read values from OPC-UA nodes (sync)."""
        ...

    async def read_nodes(self, node_ids: List[str]) -> Dict[str, Any]:
        """Read values from OPC-UA nodes (async)."""
        ...

    def subscribe_readonly(
        self, node_id: str, callback: Callable[[Any], None]
    ) -> str:
        """Subscribe to node value changes (read-only)."""
        ...


class IMQTTConnector(Protocol):
    """Protocol for MQTT read-only connector."""

    def read_topic(self, topic: str) -> Dict[str, Any]:
        """Read the latest message from an MQTT topic (sync)."""
        ...

    async def read_topic_async(self, topic: str) -> Any:
        """Read the latest message from an MQTT topic (async)."""
        ...

    def subscribe_readonly(
        self, topic: str, callback: Callable[[Dict[str, Any]], None]
    ) -> str:
        """Subscribe to topic messages (read-only)."""
        ...


class IModbusConnector(Protocol):
    """Protocol for Modbus read-only connector."""

    def read_holding_registers(self, _address: int, count: int) -> List[int]:
        """Read holding registers from Modbus device (sync)."""
        ...

    async def read_holding_registers_async(
        self, _address: int, count: int
    ) -> List[int]:
        """Read holding registers from Modbus device (async)."""
        ...
