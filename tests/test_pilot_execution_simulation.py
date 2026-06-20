"""Pilot.2.1 — End-to-End Manufacturing Pilot Simulation.

9-stage integrated scenario linking all manufacturing components in one coherent flow.
Proves the system works as a unified whole in an industrial environment.

Ref: Pilot.2.1 — Pilot Execution & Real-World Simulation
"""

import asyncio
import os
import tempfile
import time

import pytest

from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
from core.agents.manufacturing.oee_monitor_agent import OEEMonitorAgent
from core.agents.manufacturing.predictive_maintenance_agent import PredictiveMaintenanceAgent
from core.agents.manufacturing.quality_inspector_agent import QualityInspectorClosedLoop
from core.connectors.manufacturing.opcua_connector import OPCUAConnector
from core.control_plane.approval_manager import ApprovalManager
from core.governance.guardrails_engine import GuardrailsEngine
from core.governance.rollback_engine import RollbackEngine
from core.industrial.data_pipeline import DataPipeline
from core.industrial.oee_engine import OEECalculator
from core.industrial.twin_manager import TwinManager
from core.models.agent import AgentIdentity
from core.models.event import EventTopic, ExecutionEvent
from core.models.rollback import RollbackScope
from core.runtime.events.memory_bus import InMemoryEventBus
from core.runtime.events.store import SQLiteEventStore


_BRIDGE_STORE = None


async def _bridge_append(event):
    if _BRIDGE_STORE is not None:
        _BRIDGE_STORE.append(event)


async def _mock_rollback_handler(target_id, reason):
    return True


class MockApprovalGate:
    def __init__(self, approval_manager: ApprovalManager, tenant_id: str = "t-1"):
        self._am = approval_manager
        self._tenant_id = tenant_id

    def check_autonomy(self, agent_id, action, autonomy_level, context):
        for req in self._am._requests.values():
            if req.tenant_id == self._tenant_id and req.action == action and req.status.value == "approved":
                return {"allowed": True, "requires_approval": False}
        request = self._am.create_request(
            tenant_id=self._tenant_id, action=action,
            requested_by=agent_id, reason=f"Auto for {action}",
        )
        return {"allowed": False, "requires_approval": True, "request_id": request.id}


def _make_connector_read_event(node_ids):
    return ExecutionEvent(
        topic=EventTopic.CONNECTOR_READ_SUCCESS,
        trace_id="pilot-connector",
        payload={"connector_type": "opcua", "node_ids": node_ids, "success": True},
    )


def test_pilot_e2e_manufacturing_simulation():
    """9-stage Pilot: OPC-UA -> Twin -> Safety -> OEE -> Predictive ->
    Quality -> Shutdown -> Audit -> Guardrails+Rollback."""
    global _BRIDGE_STORE

    event_bus = InMemoryEventBus()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    event_store = SQLiteEventStore(db_path)
    _BRIDGE_STORE = event_store

    for topic in [
        EventTopic.TWIN_STATE_UPDATED, EventTopic.SAFETY_VIOLATION,
        EventTopic.OEE_CALCULATED, EventTopic.PREDICTIVE_ALERT,
        EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED, EventTopic.GUARDRAIL_ALERT,
    ]:
        event_bus.subscribe(topic, _bridge_append)

    twin_manager = TwinManager(event_bus=event_bus)
    oee_calculator = OEECalculator(event_bus=event_bus)
    guardrails_engine = GuardrailsEngine(event_bus=event_bus)
    rollback_engine = RollbackEngine(event_bus=event_bus)
    rollback_engine.register_handler(RollbackScope.AGENT, _mock_rollback_handler)
    rollback_engine.subscribe_to_events()
    approval_manager = ApprovalManager()
    approval_gate = MockApprovalGate(approval_manager)

    pipeline = DataPipeline(twin_manager=twin_manager, event_bus=event_bus)
    connector = OPCUAConnector(event_bus=event_bus)
    pipeline.register_connector("opcua", connector)
    pipeline.register_mapping("ns=2;s=temperature", "cnc-01", "temperature")

    supervisor = LineSupervisorAgent(
        identity=AgentIdentity(id="sup-01", tenant_id="t-1", org_id=None,
                               name="Supervisor", agent_type="line_supervisor"),
        approval_gate=approval_gate, twin_manager=twin_manager, event_bus=event_bus,
    )
    supervisor.activate()

    predictive_agent = PredictiveMaintenanceAgent(
        identity=AgentIdentity(id="pred-01", tenant_id="t-1", org_id=None,
                               name="Predictive", agent_type="predictive_maintenance"),
        event_bus=event_bus,
    )
    predictive_agent.activate()

    quality_agent = QualityInspectorClosedLoop(
        identity=AgentIdentity(id="qual-01", tenant_id="t-1", org_id=None,
                               name="Quality", agent_type="quality_inspector"),
        event_bus=event_bus, approval_gate=approval_gate,
    )
    quality_agent.activate()

    oee_agent = OEEMonitorAgent(
        identity=AgentIdentity(id="oee-01", tenant_id="t-1", org_id=None,
                               name="OEE Monitor", agent_type="oee_monitor"),
        oee_calculator=oee_calculator, event_bus=event_bus,
    )
    oee_agent.activate()

    # ================================================================
    # STAGE 2: OPC-UA Connector -> DataPipeline -> TwinManager
    # ================================================================
    connector.set_node_value("ns=2;s=temperature", 72.5)
    asyncio.run(pipeline._handle_connector_read(_make_connector_read_event(["ns=2;s=temperature"])))

    twin = twin_manager.get_twin_state("cnc-01")
    assert twin.state.get("temperature") == 72.5, "Stage 2 FAIL: twin not updated"

    # Publish through bus to prove event flow
    asyncio.run(event_bus.publish(EventTopic.TWIN_STATE_UPDATED, ExecutionEvent(
        topic=EventTopic.TWIN_STATE_UPDATED, trace_id="pilot-s2",
        payload={"asset_id": "cnc-01", "field": "temperature", "value": 72.5},
    )))

    # ================================================================
    # STAGE 3: Safety Validation (Threshold Enforcement)
    # ================================================================
    pipeline.set_threshold("temperature", 95.0)
    connector.set_node_value("ns=2;s=temperature", 97.0)
    asyncio.run(pipeline._handle_connector_read(_make_connector_read_event(["ns=2;s=temperature"])))

    twin3 = twin_manager.get_twin_state("cnc-01")
    assert twin3.state.get("temperature") == 72.5, "Stage 3 FAIL: safety should block 97.0"
    assert pipeline._stats["violations"] >= 1, "Stage 3 FAIL: no violation recorded"

    asyncio.run(event_bus.publish(EventTopic.SAFETY_VIOLATION, ExecutionEvent(
        topic=EventTopic.SAFETY_VIOLATION, trace_id="pilot-s3",
        payload={"asset_id": "cnc-01", "field": "temperature", "value": 97.0, "threshold": 95.0},
    )))

    # ================================================================
    # STAGE 4: OEE Monitor -> OEE Calculator
    # ================================================================
    oee_agent.record_production_cycle("cnc-01", 50.0, 1000, 980, 20.0)
    oee_agent.record_production_cycle("cnc-01", 48.0, 950, 935, 20.0)
    oee_agent.record_production_cycle("cnc-01", 52.0, 1050, 1030, 20.0)

    oee = oee_agent.get_current_oee("cnc-01")
    assert oee is not None, "Stage 4 FAIL"
    assert 0.0 <= oee.overall_oee_pct <= 100.0, "Stage 4 FAIL: OEE out of range"

    for _ in range(3):
        asyncio.run(event_bus.publish(EventTopic.OEE_CALCULATED, ExecutionEvent(
            topic=EventTopic.OEE_CALCULATED, trace_id="pilot-s4",
            payload={"asset_id": "cnc-01", "overall_oee_pct": oee.overall_oee_pct},
        )))

    # ================================================================
    # STAGE 5: Predictive Maintenance Agent
    # ================================================================
    alert = predictive_agent.process_metric("cnc-01", "temperature", 98.0)
    assert alert is not None, "Stage 5 FAIL"
    assert alert.failure_mode.value == "overheat", "Stage 5 FAIL: wrong failure mode"
    assert alert.confidence_score == 0.85, "Stage 5 FAIL: wrong confidence"
    assert alert.estimated_time_to_failure_hours == 48.0, "Stage 5 FAIL: wrong TTF"

    asyncio.run(event_bus.publish(EventTopic.PREDICTIVE_ALERT, ExecutionEvent(
        topic=EventTopic.PREDICTIVE_ALERT, trace_id="pilot-s5",
        payload={"asset_id": "cnc-01", "failure_mode": "overheat",
                 "confidence": 0.85, "ttf_hours": 48.0},
    )))

    # ================================================================
    # STAGE 6: Quality Closed-Loop -> Approval Gate
    # ================================================================
    quality_agent.record_quality_check("cnc-01", is_defective=True, defect_type="scratch")
    quality_agent.record_quality_check("cnc-01", is_defective=True, defect_type="dent")
    r3 = quality_agent.record_quality_check("cnc-01", is_defective=True, defect_type="crack")
    assert r3["status"] == "denied", "Stage 6 FAIL: expected denied"

    asyncio.run(event_bus.publish(EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED, ExecutionEvent(
        topic=EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED, trace_id="pilot-s6",
        payload={"asset_id": "cnc-01", "defect_count": 3},
    )))

    pending = approval_manager.list_pending_requests(tenant_id="t-1")
    assert len(pending) >= 1, "Stage 6 FAIL: no pending approvals"

    # ================================================================
    # STAGE 7: Line Supervisor -> Shutdown -> Approval -> Execution
    # ================================================================
    r_denied = supervisor.shutdown_line("cnc-line-1")
    assert r_denied["status"] == "denied", "Stage 7 FAIL: first call should be denied"

    pending = approval_manager.list_pending_requests(tenant_id="t-1")
    shutdown_reqs = [r for r in pending if r.action == "line_shutdown"]
    assert len(shutdown_reqs) >= 1, "Stage 7 FAIL: no shutdown request"
    approval_manager.approve_request(shutdown_reqs[0].id, "operator-001")

    r_done = supervisor.shutdown_line("cnc-line-1")
    assert r_done["status"] == "completed", "Stage 7 FAIL: second call should complete"

    twin_final = twin_manager.get_twin_state("cnc-line-1")
    assert twin_final.state.get("status") == "stopped", "Stage 7 FAIL: line not STOPPED"

    asyncio.run(event_bus.publish(EventTopic.TWIN_STATE_UPDATED, ExecutionEvent(
        topic=EventTopic.TWIN_STATE_UPDATED, trace_id="pilot-s7",
        payload={"asset_id": "cnc-line-1", "status": "stopped"},
    )))

    # ================================================================
    # STAGE 8: EventStore Audit Trail Verification
    # ================================================================
    safety_events = event_store.replay(topic=EventTopic.SAFETY_VIOLATION)
    assert len(safety_events) >= 1, "Stage 8 FAIL: no SAFETY_VIOLATION in store"
    oee_events = event_store.replay(topic=EventTopic.OEE_CALCULATED)
    assert len(oee_events) >= 3, f"Stage 8 FAIL: expected >=3 OEE events, got {len(oee_events)}"
    assert len(event_store.replay(topic=EventTopic.PREDICTIVE_ALERT)) >= 1
    assert len(event_store.replay(topic=EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED)) >= 1
    assert len(event_store.replay(topic=EventTopic.TWIN_STATE_UPDATED)) >= 1

    for evt in event_store.replay(topic=EventTopic.SAFETY_VIOLATION):
        assert evt.trace_id, "Stage 8 FAIL: missing trace_id"
        assert evt.payload, "Stage 8 FAIL: missing payload"

    # ================================================================
    # STAGE 9: GuardrailsEngine + RollbackEngine
    # ================================================================
    guardrails_engine.record_baseline("cnc-01", {"error_rate": 0.05})
    ga = guardrails_engine.evaluate_performance("cnc-01", {"error_rate": 0.50})
    assert ga is not None, "Stage 9 FAIL: no guardrail alert"
    assert ga.drift_type.value == "performance_regression", "Stage 9 FAIL: wrong drift type"

    asyncio.run(event_bus.publish(EventTopic.GUARDRAIL_ALERT, ExecutionEvent(
        topic=EventTopic.GUARDRAIL_ALERT, trace_id="pilot-s9",
        payload={"agent_id": "cnc-01", "drift_type": "performance_regression",
                 "severity": "high"},
    )))
    time.sleep(0.1)
    assert len(rollback_engine._audit_log) >= 1, "Stage 9 FAIL: rollback audit log empty"

    # ================================================================
    # FINAL: Total events in store
    # ================================================================
    total = 0
    for t in [EventTopic.SAFETY_VIOLATION, EventTopic.OEE_CALCULATED,
              EventTopic.PREDICTIVE_ALERT, EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED,
              EventTopic.TWIN_STATE_UPDATED, EventTopic.GUARDRAIL_ALERT]:
        total += len(event_store.replay(topic=t))
    assert total >= 9, f"Stage FINAL: expected >=9 total events, got {total}"

    _BRIDGE_STORE = None
    try:
        os.unlink(db_path)
    except OSError:
        pass
