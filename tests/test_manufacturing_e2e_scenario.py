"""End-to-End Manufacturing Scenario (RC17.1.6).

CNC Production Line Overheat Scenario — 7 stages testing the full manufacturing stack:
Connectors → Pipeline → Twin → Agents → Approval → EventStore.

Ref: RC17.1.6 — End-to-End Manufacturing Scenario
"""

import asyncio
import os
import tempfile

import pytest

from core.agents.approval_integration import AgentApprovalGate
from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
from core.connectors.manufacturing.opcua_connector import OPCUAConnector
from core.control_plane.approval_manager import ApprovalManager
from core.industrial.data_pipeline import DataPipeline
from core.industrial.twin_manager import TwinManager
from core.interfaces.control_plane import ApprovalStatus
from core.models.agent import AgentIdentity
from core.models.event import EventTopic
from core.models.manufacturing import LineStatus, ProductionLine
from core.runtime.events.memory_bus import InMemoryEventBus
from core.runtime.events.store import SQLiteEventStore


# ── Approval Gate (Two-Phase for E2E) ────────────────────────────────────────


class TwoPhaseApprovalGate:
    """Approval gate that creates approval requests for L2 actions.

    For E2E testing: creates request in ApprovalManager, returns "pending".
    After human approves, shutdown_line is called again with gate=None to execute.
    """

    def __init__(self, approval_manager: ApprovalManager) -> None:
        self._am = approval_manager

    def check_autonomy(
        self, agent_id: str, action: str, autonomy_level: str, context: dict
    ) -> dict:
        """Create approval request and return pending status."""
        req = self._am.create_request(
            tenant_id="tenant-manufacturing",
            action=action,
            requested_by=agent_id,
            reason=f"L2 requires approval for {action}",
            metadata=context,
        )
        return {
            "allowed": False,
            "requires_approval": True,
            "reason": f"Approval request created: {req.id}",
            "autonomy_level": autonomy_level,
            "request_id": req.id,
        }


# ── Test ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manufacturing_e2e_cnc_overheat_scenario():
    """End-to-end: CNC line overheats → detected → shutdown requested → approved → executed."""

    # ── Stage 1: Setup infrastructure ─────────────────────────────────────
    event_bus = InMemoryEventBus()
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    event_store = SQLiteEventStore(db_path=tmp_db.name)
    twin_manager = TwinManager(event_bus=event_bus)
    approval_manager = ApprovalManager()

    # Bridge: subscribe EventStore to all EventBus topics
    async def _store_event(event):
        event_store.append(event)

    for topic in EventTopic:
        event_bus.subscribe(topic, _store_event)

    # ── Stage 2: Setup connectors + pipeline ──────────────────────────────
    opcua = OPCUAConnector(event_bus=event_bus)
    opcua.set_node_value("ns=2;s=CNC_Temperature", 75.0)  # Normal temp

    pipeline = DataPipeline(twin_manager=twin_manager, event_bus=event_bus)
    pipeline.register_connector("opcua-1", opcua)
    pipeline.register_mapping("ns=2;s=CNC_Temperature", "cnc-line-1", "temperature")
    pipeline.set_threshold("temperature", 100.0)  # Safety limit

    # ── Stage 3: Setup agent with approval gate ───────────────────────────
    approval_gate = TwoPhaseApprovalGate(approval_manager)
    agent_identity = AgentIdentity(
        id="line-sup-001",
        tenant_id="tenant-manufacturing",
        org_id=None,
        name="CNC Line Supervisor",
        agent_type="manufacturing.line_supervisor",
    )
    agent = LineSupervisorAgent(
        identity=agent_identity,
        twin_manager=twin_manager,
        event_bus=event_bus,
        approval_gate=approval_gate,
    )
    agent.register_line(
        ProductionLine(
            id="cnc-line-1",
            name="CNC Production Line 1",
            status=LineStatus.RUNNING,
        )
    )

    # ── Stage 4: Normal operation — temperature at 75°C ───────────────────
    read_event_normal = EventTopic.CONNECTOR_READ_SUCCESS
    from core.models.event import ExecutionEvent

    normal_event = ExecutionEvent(
        topic=read_event_normal,
        trace_id="cnc-normal-001",
        payload={
            "connector_type": "opcua-1",
            "node_ids": ["ns=2;s=CNC_Temperature"],
            "success": True,
        },
    )
    await pipeline._handle_connector_read(normal_event)
    await asyncio.sleep(0.01)

    twin_state = twin_manager.get_twin_state("cnc-line-1")
    assert twin_state.state["temperature"] == 75.0, (
        f"Expected 75.0, got {twin_state.state.get('temperature')}"
    )

    # ── Stage 5: Temperature rises to 105°C (exceeds threshold) ───────────
    opcua.set_node_value("ns=2;s=CNC_Temperature", 105.0)

    overheat_event = ExecutionEvent(
        topic=read_event_normal,
        trace_id="cnc-overheat-001",
        payload={
            "connector_type": "opcua-1",
            "node_ids": ["ns=2;s=CNC_Temperature"],
            "success": True,
        },
    )
    await pipeline._handle_connector_read(overheat_event)
    await asyncio.sleep(0.01)

    # Verify SAFETY_VIOLATION event was published
    safety_events = event_store.replay(EventTopic.SAFETY_VIOLATION)
    assert len(safety_events) >= 1, (
        f"Expected >=1 SAFETY_VIOLATION, got {len(safety_events)}"
    )

    # Verify twin was NOT updated (safety blocked it)
    twin_state = twin_manager.get_twin_state("cnc-line-1")
    assert twin_state.state["temperature"] == 75.0, (
        f"Expected 75.0 (blocked), got {twin_state.state.get('temperature')}"
    )

    # ── Stage 6: Agent requests shutdown (requires approval) ──────────────
    shutdown_result = agent.shutdown_line("cnc-line-1")
    assert shutdown_result["status"] == "denied", (
        f"Expected 'denied' (pending approval), got {shutdown_result['status']}"
    )

    # Verify approval request was created
    pending = approval_manager.list_pending_requests(
        tenant_id="tenant-manufacturing"
    )
    assert len(pending) >= 1, f"Expected >=1 pending request, got {len(pending)}"

    shutdown_request = None
    for req in pending:
        if req.action == "line_shutdown":
            shutdown_request = req
            break
    assert shutdown_request is not None, "No line_shutdown approval request found"
    assert shutdown_request.status == ApprovalStatus.PENDING

    # ── Stage 7: Human approves → shutdown executed ───────────────────────
    approved = approval_manager.approve_request(
        shutdown_request.id, reviewer="operator-001"
    )
    assert approved is True

    # Execute shutdown WITHOUT approval gate (approval already granted)
    approved_agent = LineSupervisorAgent(
        identity=agent_identity,
        twin_manager=twin_manager,
        event_bus=event_bus,
        approval_gate=None,  # No gate — approval already granted
    )
    approved_agent.register_line(
        ProductionLine(
            id="cnc-line-1",
            name="CNC Production Line 1",
            status=LineStatus.RUNNING,
        )
    )
    final_shutdown = approved_agent.shutdown_line("cnc-line-1")
    assert final_shutdown["status"] == "completed", (
        f"Expected 'completed', got {final_shutdown['status']}"
    )

    # Verify twin state updated to STOPPED
    twin_state = twin_manager.get_twin_state("cnc-line-1")
    assert twin_state.state["status"] == LineStatus.STOPPED.value, (
        f"Expected STOPPED, got {twin_state.state.get('status')}"
    )

    # Verify full audit trail in EventStore
    all_twin_events = event_store.replay(EventTopic.TWIN_STATE_UPDATED)
    assert len(all_twin_events) >= 2, (
        f"Expected >=2 TWIN_STATE_UPDATED events, got {len(all_twin_events)}"
    )

    # Verify agent audit trail
    audit_actions = [a["action"] for a in approved_agent.audit.action_log]
    assert "line.shutdown.completed" in audit_actions

    # Verify pipeline audit trail
    pipeline_audit = pipeline.get_audit_log()
    assert len(pipeline_audit) >= 1
    assert pipeline_audit[0]["source"]["connector_id"] == "opcua-1"

    # Cleanup temp DB
    os.unlink(tmp_db.name)
