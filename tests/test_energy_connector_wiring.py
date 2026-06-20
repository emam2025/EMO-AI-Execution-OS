"""Tests for RC17.3.4 — Energy Connector → Twin → DataPipeline Full Wiring.

6 tests covering:
- SCADA connector live read → pipeline → twin
- MQTT connector live read → pipeline → twin
- SCADA control write blocked at pipeline level
- Connector not registered returns error
- Connector read failure returns error
- Multi-connector multi-asset isolation
"""

from __future__ import annotations

import pytest

from core.connectors.energy.scada_connector import SCADAConnector
from core.connectors.energy.mqtt_connector import MQTTConnector
from core.connectors.manufacturing.connector_error import ConnectorError
from core.governance.energy_safety import EnergySafetyGate
from core.industrial.energy_twin import EnergyTwin
from core.industrial.energy_data_pipeline import EnergyDataPipeline


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


def _make_wired_pipeline() -> tuple:
    """Create a fully wired pipeline with SCADA + MQTT connectors."""
    event_bus = MockEventBus()
    twin = EnergyTwin(event_bus=event_bus)
    safety = EnergySafetyGate(event_bus=event_bus)
    pipeline = EnergyDataPipeline(
        energy_twin=twin,
        safety_gate=safety,
        event_bus=event_bus,
    )

    scada = SCADAConnector(endpoint_url="scada://plant-1:502", event_bus=event_bus)
    mqtt = MQTTConnector(broker_url="mqtt://grid-1:1883", event_bus=event_bus)

    pipeline.register_connector("scada", scada)
    pipeline.register_connector("mqtt", mqtt)

    pipeline.register_tag_mapping("PLANT1.OUTPUT", "plant-1", "current_output_mw")
    pipeline.register_tag_mapping("PLANT1.EFFICIENCY", "plant-1", "efficiency_pct")
    pipeline.register_tag_mapping("GRID1.LOAD", "grid-1", "current_load_mw")
    pipeline.register_tag_mapping("METER1.DRAW", "meter-1", "current_draw_kw")
    pipeline.register_tag_mapping("PLANT1.SETPOINT", "plant-1", "control_setpoint")

    return pipeline, twin, safety, event_bus, scada, mqtt


# ── Test 1: SCADA connector live read → pipeline → twin ────────────────────


def test_scada_connector_live_read_updates_twin():
    """SCADA connector: live read flows through pipeline to EnergyTwin."""
    pipeline, twin, _, _, scada, _ = _make_wired_pipeline()

    scada.set_tag_value("PLANT1.OUTPUT", 480.0)
    scada.set_tag_value("PLANT1.EFFICIENCY", 39.2)

    result = pipeline.ingest_from_connector(
        connector_id="scada",
        tag_ids=["PLANT1.OUTPUT", "PLANT1.EFFICIENCY"],
        trust_level="UNVERIFIED",
    )

    assert result["updated"] == 2
    assert result["blocked"] == 0

    twin_state = twin.get_twin_state("plant-1")
    assert twin_state.state["current_output_mw"] == 480.0
    assert twin_state.state["efficiency_pct"] == 39.2


# ── Test 2: MQTT connector live read → pipeline → twin ────────────────────


def test_mqtt_connector_live_read_updates_twin():
    """MQTT connector: live read flows through pipeline to EnergyTwin."""
    pipeline, twin, _, _, _, mqtt = _make_wired_pipeline()

    mqtt.set_topic_value("METER1.DRAW", 52.7)

    result = pipeline.ingest_from_connector(
        connector_id="mqtt",
        tag_ids=["METER1.DRAW"],
        trust_level="UNVERIFIED",
    )

    assert result["updated"] == 1
    assert result["blocked"] == 0

    twin_state = twin.get_twin_state("meter-1")
    assert twin_state.state["current_draw_kw"] == 52.7


# ── Test 3: SCADA control write blocked at pipeline level ──────────────────


def test_scada_control_write_blocked_at_pipeline_level():
    """SCADA connector: control write tag is blocked by safety gate."""
    pipeline, twin, _, _, scada, _ = _make_wired_pipeline()

    scada.set_tag_value("PLANT1.SETPOINT", 600.0)

    result = pipeline.ingest_from_connector(
        connector_id="scada",
        tag_ids=["PLANT1.SETPOINT"],
        trust_level="UNVERIFIED",
    )

    assert result["blocked"] == 1
    assert result["updated"] == 0

    twin_state = twin.get_twin_state("plant-1")
    assert "control_setpoint" not in twin_state.state


# ── Test 4: Connector not registered returns error ────────────────────────


def test_unregistered_connector_returns_error():
    """Pipeline: unregistered connector_id returns error status."""
    pipeline, twin, _, _, _, _ = _make_wired_pipeline()

    result = pipeline.ingest_from_connector(
        connector_id="nonexistent",
        tag_ids=["SOME.TAG"],
        trust_level="UNVERIFIED",
    )

    assert result["details"][0]["status"] == "error"
    assert result["details"][0]["reason"] == "connector_not_registered"

    # Twin should be unchanged
    assert twin.get_twin_state("nonexistent").state == {}


# ── Test 5: Connector read failure returns error ──────────────────────────


def test_connector_read_failure_returns_error():
    """Pipeline: connector read failure (missing tag) returns error."""
    pipeline, twin, _, _, scada, _ = _make_wired_pipeline()

    # Don't set tag value — read_tags will raise ConnectorError
    result = pipeline.ingest_from_connector(
        connector_id="scada",
        tag_ids=["NONEXISTENT.TAG"],
        trust_level="UNVERIFIED",
    )

    assert result["details"][0]["status"] == "error"
    assert "read_failed" in result["details"][0]["reason"]


# ── Test 6: Multi-connector multi-asset isolation ────────────────────────


def test_multi_connector_multi_asset_isolation():
    """Pipeline: SCADA + MQTT data stays isolated per asset."""
    pipeline, twin, _, _, scada, mqtt = _make_wired_pipeline()

    scada.set_tag_value("PLANT1.OUTPUT", 480.0)
    scada.set_tag_value("GRID1.LOAD", 150.0)
    mqtt.set_topic_value("METER1.DRAW", 52.7)

    pipeline.ingest_from_connector(
        connector_id="scada",
        tag_ids=["PLANT1.OUTPUT", "GRID1.LOAD"],
        trust_level="UNVERIFIED",
    )
    pipeline.ingest_from_connector(
        connector_id="mqtt",
        tag_ids=["METER1.DRAW"],
        trust_level="UNVERIFIED",
    )

    plant1 = twin.get_twin_state("plant-1")
    grid1 = twin.get_twin_state("grid-1")
    meter1 = twin.get_twin_state("meter-1")

    assert plant1.state["current_output_mw"] == 480.0
    assert grid1.state["current_load_mw"] == 150.0
    assert meter1.state["current_draw_kw"] == 52.7

    # No cross-contamination
    assert "current_load_mw" not in plant1.state
    assert "current_output_mw" not in grid1.state
    assert "current_draw_kw" not in plant1.state
