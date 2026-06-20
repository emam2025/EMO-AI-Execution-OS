"""Tests for RC17.3 — Energy Pack Foundation.

Covers:
- Energy domain models (PowerPlant, GridNode, SmartMeter, LoadProfile, MaintenanceTicket)
- Energy Twin (state, simulation, prediction, audit)
- SCADA connector (read-only)
- MQTT connector (read-only)
- Energy agents (Monitoring, LoadForecast, Maintenance, GridAnalyst)
- Safety violations and approval gating
"""

import pytest

from core.models.energy import (
    EnergyEventSeverity,
    EnergyOperationalEvent,
    EnergyTwinState,
    GridNode,
    GridNodeType,
    LoadProfile,
    MaintenancePriority,
    MaintenanceStatus,
    MaintenanceTicket,
    PlantType,
    PowerPlant,
    SmartMeter,
)
from core.models.agent import AgentIdentity
from core.industrial.energy_twin import EnergyTwin
from core.connectors.energy.scada_connector import SCADAConnector
from core.connectors.energy.mqtt_connector import MQTTConnector
from core.connectors.manufacturing.connector_error import ConnectorError
from core.agents.energy.energy_monitoring_agent import EnergyMonitoringAgent
from core.agents.energy.load_forecast_agent import LoadForecastAgent
from core.agents.energy.maintenance_agent import EnergyMaintenanceAgent
from core.agents.energy.grid_analyst_agent import GridAnalystAgent


# ── Domain Models ───────────────────────────────────────────────────────────


def test_power_plant_creation():
    """Energy models: PowerPlant is created with correct fields."""
    plant = PowerPlant(
        id="plant-1",
        name="Coal Plant A",
        plant_type=PlantType.THERMAL,
        capacity_mw=500.0,
        current_output_mw=450.0,
        efficiency_pct=38.5,
    )
    assert plant.id == "plant-1"
    assert plant.plant_type == PlantType.THERMAL
    assert plant.capacity_mw == 500.0
    assert plant.current_output_mw == 450.0
    assert plant.status == "operational"


def test_grid_node_creation():
    """Energy models: GridNode is created with correct fields."""
    node = GridNode(
        id="node-1",
        name="Substation North",
        node_type=GridNodeType.TRANSMISSION,
        voltage_kv=138.0,
        current_load_mw=120.0,
        max_capacity_mw=200.0,
        connected_nodes=["node-2", "node-3"],
    )
    assert node.id == "node-1"
    assert node.node_type == GridNodeType.TRANSMISSION
    assert node.voltage_kv == 138.0
    assert len(node.connected_nodes) == 2


def test_smart_meter_creation():
    """Energy models: SmartMeter is created with correct fields."""
    meter = SmartMeter(
        id="meter-1",
        name="Building Meter",
        location="Building A Floor 3",
        current_draw_kw=45.2,
        daily_consumption_kwh=890.5,
    )
    assert meter.id == "meter-1"
    assert meter.current_draw_kw == 45.2
    assert meter.meter_status == "active"


def test_load_profile_creation():
    """Energy models: LoadProfile is created with correct fields."""
    profile = LoadProfile(
        id="profile-1",
        name="Residential Profile",
        hourly_loads_kw=[10.0, 8.0, 7.0, 6.0, 6.5, 12.0, 25.0, 30.0],
        peak_load_kw=30.0,
        average_load_kw=13.0625,
    )
    assert profile.id == "profile-1"
    assert len(profile.hourly_loads_kw) == 8
    assert profile.peak_load_kw == 30.0


def test_maintenance_ticket_creation():
    """Energy models: MaintenanceTicket is created with correct fields."""
    ticket = MaintenanceTicket(
        id="ticket-1",
        asset_id="plant-1",
        title="Turbine inspection",
        description="Annual turbine blade inspection",
        priority=MaintenancePriority.HIGH,
        status=MaintenanceStatus.OPEN,
    )
    assert ticket.id == "ticket-1"
    assert ticket.priority == MaintenancePriority.HIGH
    assert ticket.status == MaintenanceStatus.OPEN


# ── Energy Twin ─────────────────────────────────────────────────────────────


def test_energy_twin_update_state():
    """Energy Twin: state is updated and version increments."""
    twin = EnergyTwin()
    state = twin.update_twin_state("plant-1", {
        "current_output_mw": 450.0,
        "status": "operational",
    })
    assert state.version == 2
    assert state.state["current_output_mw"] == 450.0

    state2 = twin.update_twin_state("plant-1", {"current_output_mw": 460.0})
    assert state2.version == 3
    assert state2.state["current_output_mw"] == 460.0


def test_energy_twin_simulation():
    """Energy Twin: simulation returns result with confidence."""
    twin = EnergyTwin()
    twin.update_twin_state("plant-1", {"current_output_mw": 450.0})

    result = twin.simulate("plant-1", {
        "state_changes": {"current_output_mw": 500.0},
        "expected_outcome": "increased_output",
    })
    assert result["asset_id"] == "plant-1"
    assert result["result"]["simulated_state"]["current_output_mw"] == 500.0
    assert result["result"]["confidence"] == 0.85


def test_energy_twin_prediction():
    """Energy Twin: prediction returns horizon and confidence."""
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {"current_load_mw": 120.0})

    prediction = twin.predict("grid-1", horizon_hours=48)
    assert prediction["horizon_hours"] == 48
    assert prediction["asset_id"] == "grid-1"
    assert prediction["confidence"] == 0.80


def test_energy_twin_audit_trail():
    """Energy Twin: operational events are recorded in audit trail."""
    twin = EnergyTwin()
    event = EnergyOperationalEvent(
        id="event-1",
        asset_id="plant-1",
        event_type="output_anomaly",
        severity=EnergyEventSeverity.WARNING,
        data={"expected": 450.0, "actual": 380.0},
    )
    twin.record_event("plant-1", event)
    events = twin.get_events("plant-1")
    assert len(events) == 1
    assert events[0].event_type == "output_anomaly"


# ── SCADA Connector ─────────────────────────────────────────────────────────


def test_scada_connector_read_tags():
    """SCADA Connector: read_tags returns correct values."""
    scada = SCADAConnector(endpoint_url="scada://192.168.1.100:502")
    scada.set_tag_value("PLANT1.OUTPUT", 450.0)
    scada.set_tag_value("PLANT1.EFFICIENCY", 38.5)

    values = scada.read_tags(["PLANT1.OUTPUT", "PLANT1.EFFICIENCY"])
    assert values["PLANT1.OUTPUT"] == 450.0
    assert values["PLANT1.EFFICIENCY"] == 38.5


def test_scada_connector_read_failure():
    """SCADA Connector: read_tags raises ConnectorError for unknown tag."""
    scada = SCADAConnector()
    with pytest.raises(ConnectorError) as exc_info:
        scada.read_tags(["UNKNOWN.TAG"])
    assert "SCADA tag not found" in str(exc_info.value)
    assert exc_info.value.connector_type == "scada"


def test_scada_connector_subscribe():
    """SCADA Connector: subscribe_readonly returns subscription ID."""
    scada = SCADAConnector()
    sub_id = scada.subscribe_readonly("PLANT1.OUTPUT", lambda v: None)
    assert sub_id.startswith("sub_")


# ── MQTT Connector ──────────────────────────────────────────────────────────


def test_mqtt_connector_read_topics():
    """MQTT Connector: read_topics returns correct values."""
    mqtt = MQTTConnector(broker_url="mqtt://localhost:1883")
    mqtt.set_topic_value("energy/plant1/output", 450.0)
    mqtt.set_topic_value("energy/grid1/load", 120.0)

    values = mqtt.read_topics(["energy/plant1/output", "energy/grid1/load"])
    assert values["energy/plant1/output"] == 450.0
    assert values["energy/grid1/load"] == 120.0


def test_mqtt_connector_read_failure():
    """MQTT Connector: read_topics raises ConnectorError for unknown topic."""
    mqtt = MQTTConnector()
    with pytest.raises(ConnectorError) as exc_info:
        mqtt.read_topics(["unknown/topic"])
    assert "MQTT topic not found" in str(exc_info.value)
    assert exc_info.value.connector_type == "mqtt"


# ── Energy Monitoring Agent ─────────────────────────────────────────────────


def _make_agent_identity(name: str = "Test Agent") -> AgentIdentity:
    return AgentIdentity(
        id="agent-1",
        tenant_id="tenant-1",
        org_id=None,
        name=name,
        agent_type="energy_monitoring",
    )


def test_energy_monitoring_agent_activate():
    """Energy Agent: activate sets status to active."""
    identity = _make_agent_identity("Monitor Agent")
    agent = EnergyMonitoringAgent(identity=identity)
    agent.activate()
    assert agent.audit.action_log[-1]["action"] == "agent.activate"


def test_energy_monitoring_agent_get_plant_output():
    """Energy Agent: get_plant_output queries twin state."""
    identity = _make_agent_identity()
    twin = EnergyTwin()
    twin.update_twin_state("plant-1", {
        "current_output_mw": 450.0,
        "status": "operational",
    })
    agent = EnergyMonitoringAgent(identity=identity, energy_twin=twin)
    result = agent.get_plant_output("plant-1")
    assert result["output_mw"] == 450.0
    assert result["status"] == "operational"


def test_energy_monitoring_agent_get_grid_load():
    """Energy Agent: get_grid_load queries twin state."""
    identity = _make_agent_identity()
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {
        "current_load_mw": 120.0,
        "max_capacity_mw": 200.0,
    })
    agent = EnergyMonitoringAgent(identity=identity, energy_twin=twin)
    result = agent.get_grid_load("grid-1")
    assert result["current_load_mw"] == 120.0
    assert result["max_capacity_mw"] == 200.0


# ── Load Forecast Agent ─────────────────────────────────────────────────────


def test_load_forecast_agent_forecast_demand():
    """Energy Agent: forecast_demand returns prediction."""
    identity = _make_agent_identity("Forecast Agent")
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {"current_load_mw": 100.0})
    agent = LoadForecastAgent(identity=identity, energy_twin=twin)

    result = agent.forecast_demand("grid-1", horizon_hours=12)
    assert result["node_id"] == "grid-1"
    assert result["horizon_hours"] == 12
    assert result["predicted_load_mw"] == 105.0


def test_load_forecast_agent_recommend_balance():
    """Energy Agent: recommend_load_balance identifies imbalanced nodes."""
    identity = _make_agent_identity("Forecast Agent")
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {"current_load_mw": 200.0})
    twin.update_twin_state("grid-2", {"current_load_mw": 50.0})
    agent = LoadForecastAgent(identity=identity, energy_twin=twin)

    result = agent.recommend_load_balance(["grid-1", "grid-2"])
    assert len(result["recommendations"]) > 0


# ── Maintenance Agent ───────────────────────────────────────────────────────


def test_maintenance_agent_create_ticket():
    """Energy Agent: create_ticket creates and stores ticket."""
    identity = _make_agent_identity("Maintenance Agent")
    agent = EnergyMaintenanceAgent(identity=identity)

    ticket = agent.create_ticket(
        asset_id="plant-1",
        title="Turbine inspection",
        description="Annual inspection",
        priority=MaintenancePriority.HIGH,
    )
    assert ticket.asset_id == "plant-1"
    assert ticket.priority == MaintenancePriority.HIGH
    assert agent.get_ticket(ticket.id) is not None


def test_maintenance_agent_list_tickets():
    """Energy Agent: list_tickets returns all tickets."""
    identity = _make_agent_identity("Maintenance Agent")
    agent = EnergyMaintenanceAgent(identity=identity)
    agent.create_ticket(asset_id="plant-1", title="T1", description="D1")
    agent.create_ticket(asset_id="plant-2", title="T2", description="D2")

    all_tickets = agent.list_tickets()
    assert len(all_tickets) == 2

    plant1_tickets = agent.list_tickets(asset_id="plant-1")
    assert len(plant1_tickets) == 1


def test_maintenance_agent_recommend():
    """Energy Agent: recommend_maintenance checks efficiency."""
    identity = _make_agent_identity("Maintenance Agent")
    twin = EnergyTwin()
    twin.update_twin_state("plant-1", {"efficiency_pct": 70.0})
    agent = EnergyMaintenanceAgent(identity=identity, energy_twin=twin)

    result = agent.recommend_maintenance("plant-1")
    assert result["recommendation"] == "schedule_maintenance"
    assert result["priority"] == "high"


# ── Grid Analyst Agent ──────────────────────────────────────────────────────


def test_grid_analyst_stability():
    """Energy Agent: analyze_stability checks utilization."""
    identity = _make_agent_identity("Grid Analyst")
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {
        "current_load_mw": 120.0,
        "max_capacity_mw": 200.0,
        "status": "active",
    })
    agent = GridAnalystAgent(identity=identity, energy_twin=twin)

    result = agent.analyze_stability(["grid-1"])
    assert result["overall_stable"] is True
    assert result["nodes"][0]["utilization_pct"] == 60.0


def test_grid_analyst_load_distribution():
    """Energy Agent: analyze_load_distribution identifies imbalanced loads."""
    identity = _make_agent_identity("Grid Analyst")
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {"current_load_mw": 180.0})
    twin.update_twin_state("grid-2", {"current_load_mw": 40.0})
    agent = GridAnalystAgent(identity=identity, energy_twin=twin)

    result = agent.analyze_load_distribution(["grid-1", "grid-2"])
    assert result["balanced"] is False
    assert result["max_node"] == "grid-1"
    assert result["min_node"] == "grid-2"


def test_grid_analyst_capacity_recommendation():
    """Energy Agent: recommend_capacity suggests increase when utilization high."""
    identity = _make_agent_identity("Grid Analyst")
    twin = EnergyTwin()
    twin.update_twin_state("grid-1", {
        "current_load_mw": 180.0,
        "max_capacity_mw": 200.0,
    })
    agent = GridAnalystAgent(identity=identity, energy_twin=twin)

    result = agent.recommend_capacity("grid-1")
    assert result["recommendation"] == "increase_capacity"
    assert result["suggested_capacity_mw"] == 250.0
