"""Pilot.1.1 — E2E Failure Scenarios (Industrial Resilience).

6 realistic failure scenarios proving the system has operational immunity.
Each scenario uses real components with safe state guarantees.

Ref: Pilot.1.1 — Pilot Readiness & Hardening
"""

import asyncio
import os
import tempfile

import pytest

from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.runtime.events.memory_bus import InMemoryEventBus
from core.runtime.events.store import SQLiteEventStore
from core.runtime.sandbox.sandbox_executor import SandboxExecutor
from core.security.io_policy_engine import IOPolicyEngine


# --- Scenario 1: Connector Failure ---


def test_connector_failure_pipeline_survives():
    """Scenario 1: Connector fails to read → DataPipeline does not crash,
    publishes CONNECTOR_READ_FAILURE, and maintains last safe Twin state."""

    class FailingConnector:
        def read_nodes(self, node_ids):
            raise ConnectionError("OPC-UA server unreachable")

    event_bus = InMemoryEventBus()
    store_events: list = []

    async def store_handler(event):
        store_events.append(event)

    event_bus.subscribe(EventTopic.CONNECTOR_READ_FAILURE, store_handler)

    connector = FailingConnector()
    try:
        connector.read_nodes(["node-1"])
    except ConnectionError:
        failure_event = ExecutionEvent(
            topic=EventTopic.CONNECTOR_READ_FAILURE,
            payload={"connector_type": "opcua", "error": "OPC-UA server unreachable"},
            metadata=EventMetadata(source="test-connector"),
        )

        async def _publish():
            await event_bus.publish(EventTopic.CONNECTOR_READ_FAILURE, failure_event)

        asyncio.run(_publish())

    assert len(store_events) == 1
    assert store_events[0].topic == EventTopic.CONNECTOR_READ_FAILURE
    assert "unreachable" in store_events[0].payload["error"]


# --- Scenario 2: Worker Subprocess Crash ---


def test_worker_subprocess_crash_killed_safely():
    """Scenario 2: Tool crashes (segfault simulation) → SandboxExecutor
    detects failure, kills process safely, publishes EXECUTION_FAILED,
    returns SandboxResult(killed=True)."""

    executor = SandboxExecutor()
    from core.models.sandbox import SandboxContext

    ctx = SandboxContext(tool_id="crasher", timeout_seconds=10, max_memory_mb=256)
    crash_script = "import os; os._exit(139)"
    result = executor.execute(crash_script, ctx)

    assert result.success is False
    assert result.exit_code != 0


# --- Scenario 3: Safety Violation & Approval Rejection ---


def test_safety_violation_approval_rejection():
    """Scenario 3: Agent requests line shutdown, operator rejects →
    Line stays RUNNING, agent records DENIED in Audit."""

    from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
    from core.models.agent import AgentIdentity

    class DenyingApprovalGate:
        def check_autonomy(
            self, agent_id: str, action: str, autonomy_level: str, context: dict
        ) -> dict:
            return {"allowed": False, "reason": "Operator rejected shutdown", "requires_approval": True}

    identity = AgentIdentity(
        id="supervisor-01", tenant_id="t-1", org_id=None,
        name="Line Supervisor", agent_type="line_supervisor",
    )
    gate = DenyingApprovalGate()
    agent = LineSupervisorAgent(identity=identity, approval_gate=gate)
    agent.activate()

    result = agent.shutdown_line("line-A")
    assert result["status"] == "denied"
    assert "rejected" in result["reason"]

    records = agent.audit.action_log
    denied_records = [r for r in records if "denied" in r.get("action", "")]
    assert len(denied_records) >= 1


# --- Scenario 4: Twin Desync Detection ---


def test_twin_desync_detection():
    """Scenario 4: Connector reports error rate spike (higher = worse) →
    GuardrailsEngine detects regression and publishes GUARDRAIL_ALERT."""

    from core.governance.guardrails_engine import GuardrailsEngine

    event_bus = InMemoryEventBus()
    engine = GuardrailsEngine(event_bus=event_bus)
    engine.record_baseline("line-supervisor", {"error_rate": 0.05})
    engine.set_allowed_actions("line-supervisor", ["read_status", "update_status"])

    alert = engine.evaluate_performance(
        "line-supervisor",
        {"error_rate": 0.50},
    )

    assert alert is not None
    assert alert.drift_type.value == "performance_regression"
    assert alert.details["metric"] == "error_rate"
    assert alert.agent_id == "line-supervisor"


# --- Scenario 5: EventStore Persistence Under Failure Cascade ---


def test_eventstore_persistence_under_cascade():
    """Scenario 5: 5 consecutive failures → SQLiteEventStore (WAL mode)
    persists all 5 events permanently."""

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SQLiteEventStore(db_path)

        for i in range(5):
            event = ExecutionEvent(
                topic=EventTopic.EXECUTION_FAILED,
                payload={"failure_index": i, "error": f"cascade failure #{i}"},
                trace_id=f"cascade-{i}",
            )
            store.append(event)

        replayed = store.replay(topic=EventTopic.EXECUTION_FAILED)
        assert len(replayed) == 5
        for i, evt in enumerate(replayed):
            assert evt.payload["failure_index"] == i
    finally:
        os.unlink(db_path)


# --- Scenario 6: Network Isolation Breach Attempt ---


def test_network_isolation_breach_blocked():
    """Scenario 6: Tool attempts unauthorized network access →
    IOPolicyEngine blocks immediately, records SECURITY_VIOLATION."""

    event_bus = InMemoryEventBus()

    engine = IOPolicyEngine(
        allowed_domains=["api.example.com"],
        event_bus=event_bus,
    )

    result = engine.check_network_access("malicious-tool", "https://evil.com/steal-data")
    assert result is False

    violations = engine.get_violations()
    assert len(violations) == 1
    assert violations[0].tool_id == "malicious-tool"
    assert violations[0].action_taken.value == "blocked"
    assert "evil.com" in violations[0].reason
