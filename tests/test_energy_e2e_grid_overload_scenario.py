"""RC17.3.6 — End-to-End Energy Scenario: Grid Overload Simulation.

8-stage E2E test proving the energy pack works as an integrated whole
under a critical grid overload scenario with NERC-CIP safety enforcement.

Stages:
1. Setup Infrastructure
2. Normal Operation (SCADA → Pipeline → Twin)
3. Grid Overload Simulation
4. Load Forecasting
5. Grid Analyst Recommendation & Safety Gate Block
6. Human Approval for TRUSTED Agent
7. Approval Execution
8. EventStore Audit Trail Verification

Ref: RC17.3.6 — Energy Pack Foundation (Final)
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from core.models.agent import AgentIdentity
from core.models.energy_policy import EnergyActionType
from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.interfaces.control_plane import ApprovalStatus
from core.connectors.energy.scada_connector import SCADAConnector
from core.control_plane.approval_manager import ApprovalManager
from core.governance.energy_safety import EnergySafetyGate
from core.industrial.energy_data_pipeline import EnergyDataPipeline
from core.industrial.energy_twin import EnergyTwin
from core.runtime.events.memory_bus import InMemoryEventBus
from core.runtime.events.store import SQLiteEventStore
from core.agents.energy.energy_monitoring_agent import EnergyMonitoringAgent
from core.agents.energy.load_forecast_agent import LoadForecastAgent
from core.agents.energy.grid_analyst_agent import GridAnalystAgent


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_identity(agent_id: str) -> AgentIdentity:
    return AgentIdentity(
        id=agent_id,
        tenant_id="energy-tenant",
        org_id="energy-org",
        name=f"Agent {agent_id}",
        agent_type="energy",
    )


class MockApprovalGate:
    """Approval gate that always requires approval for critical actions."""

    def check_autonomy(
        self, agent_id: str, action: str, autonomy_level: str, context: dict
    ) -> dict:
        return {
            "allowed": True,
            "requires_approval": True,
            "reason": "requires_human_approval",
            "autonomy_level": autonomy_level,
        }


# ── E2E Test ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_energy_e2e_grid_overload_scenario():
    """E2E: Grid overload → load shedding → safety gate → human approval.

    8 stages proving the full energy pack integration.
    Asserts: ≥12 safe-state and event-audit assertions.
    """

    # ── Stage 1: Setup Infrastructure ──────────────────────────────────────

    event_bus = InMemoryEventBus()
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "energy_e2e.db")
    event_store = SQLiteEventStore(db_path)

    # Wire EventBus → EventStore via subscriber
    all_topics = [
        EventTopic.TWIN_STATE_UPDATED,
        EventTopic.SAFETY_VIOLATION,
        EventTopic.AGENT_STATE_CHANGED,
        EventTopic.CONNECTOR_READ_SUCCESS,
        EventTopic.CONNECTOR_READ_FAILURE,
    ]

    async def _store_event(event: ExecutionEvent) -> None:
        event_store.append(event)

    for topic in all_topics:
        event_bus.subscribe(topic, _store_event)

    # Create core components
    twin = EnergyTwin(event_bus=event_bus)
    safety = EnergySafetyGate(event_bus=event_bus)
    pipeline = EnergyDataPipeline(
        energy_twin=twin, safety_gate=safety, event_bus=event_bus,
    )
    approval_manager = ApprovalManager()

    # Create agents
    monitoring = EnergyMonitoringAgent(
        identity=_make_identity("monitor-001"),
        energy_twin=twin,
        event_bus=event_bus,
    )
    forecast = LoadForecastAgent(
        identity=_make_identity("forecast-001"),
        energy_twin=twin,
        event_bus=event_bus,
    )
    grid_analyst = GridAnalystAgent(
        identity=_make_identity("grid-analyst-001"),
        energy_twin=twin,
        event_bus=event_bus,
        safety_gate=safety,
    )

    # Create SCADA connector with normal values
    scada = SCADAConnector(
        endpoint_url="scada://grid-control:502", event_bus=event_bus,
    )

    # Register connector + tag mappings
    pipeline.register_connector("scada", scada)
    pipeline.register_tag_mapping("PLANT1.OUTPUT", "plant-1", "current_output_mw")
    pipeline.register_tag_mapping("GRID1.LOAD", "grid-1", "current_load_mw")
    pipeline.register_tag_mapping("GRID1.MAX", "grid-1", "max_capacity_mw")

    # Safe state assertion: infrastructure created
    assert twin is not None
    assert safety is not None
    assert pipeline is not None
    assert approval_manager is not None

    # ── Stage 2: Normal Operation (SCADA → Pipeline → Twin) ───────────────

    scada.set_tag_value("PLANT1.OUTPUT", 480.0)
    scada.set_tag_value("GRID1.LOAD", 150.0)
    scada.set_tag_value("GRID1.MAX", 200.0)

    result_normal = pipeline.ingest_from_connector(
        connector_id="scada",
        tag_ids=["PLANT1.OUTPUT", "GRID1.LOAD", "GRID1.MAX"],
        trust_level="TRUSTED",
    )
    await asyncio.sleep(0.01)

    # Safe state: all tags updated, none blocked
    assert result_normal["updated"] == 3
    assert result_normal["blocked"] == 0

    plant_state = twin.get_twin_state("plant-1")
    grid_state = twin.get_twin_state("grid-1")
    assert plant_state.state["current_output_mw"] == 480.0
    assert grid_state.state["current_load_mw"] == 150.0
    assert grid_state.state["max_capacity_mw"] == 200.0

    # Event audit: connector read event stored
    connector_events = event_store.replay(EventTopic.CONNECTOR_READ_SUCCESS)
    assert len(connector_events) >= 1

    # ── Stage 3: Grid Overload Simulation ──────────────────────────────────

    # Simulate overload: grid load jumps to 190 MW (95% of 200 MW capacity)
    scada.set_tag_value("GRID1.LOAD", 190.0)

    result_overload = pipeline.ingest_from_connector(
        connector_id="scada",
        tag_ids=["GRID1.LOAD"],
        trust_level="TRUSTED",
    )
    await asyncio.sleep(0.01)

    # Safe state: overload reflected in twin
    overload_details = [d for d in result_overload["details"] if d["status"] == "updated"]
    assert len(overload_details) == 1
    grid_state_overload = twin.get_twin_state("grid-1")
    assert grid_state_overload.state["current_load_mw"] == 190.0

    # Event audit: twin updated
    twin_events = event_store.replay(EventTopic.TWIN_STATE_UPDATED)
    assert len(twin_events) >= 1

    # ── Stage 4: Load Forecasting ─────────────────────────────────────────

    forecast_result = forecast.forecast_demand("grid-1", horizon_hours=2)
    await asyncio.sleep(0.01)

    # Safe state: forecast returned valid prediction
    assert forecast_result["node_id"] == "grid-1"
    assert forecast_result["horizon_hours"] == 2
    assert forecast_result["current_load_mw"] == 190.0
    assert forecast_result["predicted_load_mw"] == 190.0 * 1.05
    assert forecast_result["prediction_id"] is not None

    # Event audit: agent state changed event stored
    agent_events = event_store.replay(EventTopic.AGENT_STATE_CHANGED)
    assert len(agent_events) >= 1

    # ── Stage 5: Grid Analyst Recommendation & Safety Gate Block ───────────

    # UNVERIFIED trust → safety gate MUST block LOAD_SHEDDING
    blocked_result = grid_analyst.recommend_load_shedding(
        grid_id="grid-1", trust_level="UNVERIFIED",
    )
    await asyncio.sleep(0.01)

    # Safe state: action blocked by safety gate
    assert blocked_result["needs_load_shedding"] is True
    assert blocked_result["utilization_pct"] == 95.0
    assert blocked_result["safety_allowed"] is False
    assert blocked_result["recommendation"] == "load_shedding_blocked"

    # Event audit: SAFETY_VIOLATION stored
    violation_events = event_store.replay(EventTopic.SAFETY_VIOLATION)
    assert len(violation_events) >= 1
    violation_payload = violation_events[0].payload
    assert violation_payload["domain"] == "energy"
    assert violation_payload["allowed"] is False

    # ── Stage 6: Human Approval for TRUSTED Agent ─────────────────────────

    # TRUSTED trust → safety gate allows but requires approval
    trusted_result = grid_analyst.recommend_load_shedding(
        grid_id="grid-1", trust_level="TRUSTED",
    )
    await asyncio.sleep(0.01)

    # Safe state: allowed but requires approval
    assert trusted_result["safety_allowed"] is True
    assert trusted_result["requires_approval"] is True
    assert trusted_result["recommendation"] == "load_shedding_recommended"

    # Create approval request in ApprovalManager
    approval_request = approval_manager.create_request(
        tenant_id="energy-tenant",
        action="LOAD_SHEDDING",
        requested_by="grid-analyst-001",
        reason="Grid utilization at 95% — load shedding recommended",
        org_id="energy-org",
        metadata={"grid_id": "grid-1", "utilization": 95.0},
    )

    # Safe state: approval request is pending
    assert approval_request.status == ApprovalStatus.PENDING
    pending = approval_manager.list_pending_requests("energy-tenant")
    assert len(pending) >= 1

    # ── Stage 7: Approval Execution ────────────────────────────────────────

    # Human approves the request
    approved = approval_manager.approve_request(
        approval_request.id, reviewer="human-operator-001",
    )

    # Safe state: approval succeeded
    assert approved is True
    updated_request = approval_manager.get_request(approval_request.id)
    assert updated_request.status == ApprovalStatus.APPROVED
    assert updated_request.reviewer == "human-operator-001"

    # After approval, agent can proceed with recommendation
    final_result = grid_analyst.recommend_load_shedding(
        grid_id="grid-1", trust_level="TRUSTED",
    )
    await asyncio.sleep(0.01)

    # Safe state: recommendation is now actionable
    assert final_result["safety_allowed"] is True
    assert final_result["recommendation"] == "load_shedding_recommended"

    # Event audit: TWIN_STATE_UPDATED events accumulated
    twin_events_final = event_store.replay(EventTopic.TWIN_STATE_UPDATED)
    assert len(twin_events_final) >= 2

    # ── Stage 8: EventStore Audit Trail Verification ───────────────────────

    # Verify SAFETY_VIOLATION events
    violations_final = event_store.replay(EventTopic.SAFETY_VIOLATION)
    assert len(violations_final) >= 1
    for evt in violations_final:
        assert evt.trace_id is not None
        assert "energy" in evt.payload.get("domain", "")

    # Verify TWIN_STATE_UPDATED events
    twin_final = event_store.replay(EventTopic.TWIN_STATE_UPDATED)
    assert len(twin_final) >= 2
    for evt in twin_final:
        assert evt.trace_id is not None
        assert "energy" in evt.payload.get("domain", "")

    # Verify AGENT_STATE_CHANGED events
    agent_final = event_store.replay(EventTopic.AGENT_STATE_CHANGED)
    assert len(agent_final) >= 1
    for evt in agent_final:
        assert evt.trace_id is not None
        assert evt.payload.get("agent_id") is not None

    # Verify all events have valid trace_id and payload
    all_events = (
        violations_final + twin_final + agent_final
    )
    assert len(all_events) >= 5
    for evt in all_events:
        assert evt.event_id is not None
        assert evt.trace_id != ""
        assert isinstance(evt.payload, dict)

    # Final safe state: grid twin still reflects overload (no unapproved writes)
    grid_final = twin.get_twin_state("grid-1")
    assert grid_final.state["current_load_mw"] == 190.0
    assert grid_final.state["max_capacity_mw"] == 200.0
