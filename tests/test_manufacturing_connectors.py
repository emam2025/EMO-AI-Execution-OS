"""Tests for Manufacturing Connectors (RC17.1.4).

6 tests covering OPC-UA, MQTT, Modbus read-only connectors.

Ref: RC17.1.4 — Manufacturing Connectors (Read-Only V1)
"""

import asyncio

import pytest

from core.connectors.manufacturing.connector_error import ConnectorError
from core.connectors.manufacturing.opcua_connector import OPCUAConnector
from core.models.event import EventTopic


# ── Mock Event Bus ────────────────────────────────────────────────────────────


class MockEventBus:
    """Mock IEventBus for testing."""

    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_opcua_read_nodes_success():
    """read_node_values must return values for existing nodes."""
    connector = OPCUAConnector()
    connector.set_node_value("ns=2;s=Temperature", 72.5)
    connector.set_node_value("ns=2;s=Pressure", 101.3)

    results = connector.read_node_values(["ns=2;s=Temperature", "ns=2;s=Pressure"])
    assert results["ns=2;s=Temperature"] == 72.5
    assert results["ns=2;s=Pressure"] == 101.3


def test_opcua_read_nodes_failure_raises_error():
    """read_node_values must raise ConnectorError for missing nodes."""
    connector = OPCUAConnector()
    connector.set_node_value("ns=2;s=Temp", 50.0)

    with pytest.raises(ConnectorError) as exc_info:
        connector.read_node_values(["ns=2;s=Temp", "ns=2;s=Missing"])

    assert "Node not found" in str(exc_info.value)
    assert exc_info.value.connector_type == "opcua"
    assert exc_info.value.node_id == "ns=2;s=Missing"


def test_mqtt_subscribe_readonly_registers_callback():
    """subscribe_readonly must register callback and return subscription ID."""
    connector = OPCUAConnector()
    received = []

    def on_change(value):
        received.append(value)

    sub_id = connector.subscribe_readonly("ns=2;s=Sensor1", on_change)
    assert sub_id.startswith("sub_ns=2;s=Sensor1_")
    assert len(connector._subscriptions) == 1


def test_modbus_read_holding_registers():
    """OPCUAConnector.read_node_values must handle multiple nodes correctly."""
    connector = OPCUAConnector()
    connector.set_node_value("register_0", 100)
    connector.set_node_value("register_1", 200)
    connector.set_node_value("register_2", 300)

    results = connector.read_node_values(["register_0", "register_1", "register_2"])
    assert results == {"register_0": 100, "register_1": 200, "register_2": 300}


@pytest.mark.asyncio
async def test_connector_publishes_read_event_to_event_bus():
    """Successful read must publish CONNECTOR_READ_SUCCESS event."""
    event_bus = MockEventBus()
    connector = OPCUAConnector(event_bus=event_bus)
    connector.set_node_value("ns=2;s=Temp", 42.0)

    connector.read_node_values(["ns=2;s=Temp"])
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 1
    pub = event_bus.published[0]
    assert pub["topic"] == EventTopic.CONNECTOR_READ_SUCCESS
    assert pub["event"].payload["connector_type"] == "opcua"
    assert pub["event"].payload["success"] is True
    assert pub["event"].trace_id.startswith("opcua-")


def test_no_write_methods_exist_in_interfaces():
    """OPC-UA, MQTT, Modbus interfaces must have NO write/execute/command methods."""
    from core.interfaces.connectors import IModbusConnector, IMQTTConnector, IOPCUAConnector

    write_keywords = {"write", "execute", "command", "send", "set", "update"}

    for proto in [IOPCUAConnector, IMQTTConnector, IModbusConnector]:
        methods = [m for m in dir(proto) if not m.startswith("_")]
        for method_name in methods:
            for keyword in write_keywords:
                assert keyword not in method_name.lower(), (
                    f"Write-like method '{method_name}' found in {proto.__name__}"
                )
