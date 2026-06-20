"""Tests for Manufacturing Agents Integration (RC17.1.3).

LineSupervisorAgent integrated with ITwinManager + IEventBus.

Ref: RC17.1.3 — Manufacturing Agents Integration (TwinManager + Event Fabric)
"""

import asyncio

import pytest

from core.agents.approval_integration import AgentApprovalGate
from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
from core.models.agent import AgentIdentity
from core.models.event import EventTopic, ExecutionEvent
from core.models.industrial import TwinState
from core.models.manufacturing import LineStatus


# ── Mocks ─────────────────────────────────────────────────────────────────────


class MockTwinManager:
    """Mock ITwinManager for testing."""

    def __init__(self) -> None:
        self.states: dict[str, TwinState] = {}
        self.update_calls: list[dict] = []

    def get_twin_state(self, asset_id: str) -> TwinState:
        if asset_id not in self.states:
            self.states[asset_id] = TwinState(
                asset_id=asset_id,
                state={"status": LineStatus.RUNNING.value},
            )
        return self.states[asset_id]

    def update_twin_state(self, asset_id: str, new_state: dict) -> TwinState:
        self.update_calls.append({"asset_id": asset_id, "new_state": new_state})
        old = self.states.get(
            asset_id,
            TwinState(asset_id=asset_id, state={}),
        )
        updated = TwinState(
            asset_id=asset_id,
            state={**old.state, **new_state},
            version=old.version + 1,
        )
        self.states[asset_id] = updated
        return updated

    def simulate(self, asset_id: str, scenario: dict) -> dict:
        return {"status": "simulated"}

    def record_event(self, asset_id: str, event) -> None:
        pass


class MockEventBus:
    """Mock IEventBus for testing (async publish matching InMemoryEventBus)."""

    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event: ExecutionEvent) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


class MockApprovalGate:
    """Mock IAgentApprovalGate — denies all approval-required actions."""

    def check_autonomy(
        self, agent_id: str, action: str, autonomy_level: str, context: dict
    ) -> dict:
        return {
            "allowed": False,
            "requires_approval": False,
            "reason": "Approval denied by mock gate",
            "autonomy_level": autonomy_level,
        }


class MockApprovalGateAllow:
    """Mock IAgentApprovalGate — allows all actions."""

    def check_autonomy(
        self, agent_id: str, action: str, autonomy_level: str, context: dict
    ) -> dict:
        return {
            "allowed": True,
            "requires_approval": False,
            "reason": "Approved",
            "autonomy_level": autonomy_level,
        }


def _make_identity() -> AgentIdentity:
    return AgentIdentity(
        id="agent-line-sup-int",
        tenant_id="tenant-1",
        org_id=None,
        name="line-sup-int",
        agent_type="manufacturing.line_supervisor",
    )


@pytest.fixture
def twin_manager() -> MockTwinManager:
    return MockTwinManager()


@pytest.fixture
def event_bus() -> MockEventBus:
    return MockEventBus()


@pytest.fixture
def agent_with_deps(twin_manager, event_bus) -> LineSupervisorAgent:
    """Agent with all optional dependencies injected."""
    return LineSupervisorAgent(
        identity=_make_identity(),
        twin_manager=twin_manager,
        event_bus=event_bus,
    )


@pytest.fixture
def agent_without_deps() -> LineSupervisorAgent:
    """Agent with NO optional dependencies — graceful degradation."""
    return LineSupervisorAgent(identity=_make_identity())


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_get_line_status_queries_twin_manager(twin_manager, event_bus):
    """get_line_status must query ITwinManager when injected."""
    agent = LineSupervisorAgent(
        identity=_make_identity(),
        twin_manager=twin_manager,
        event_bus=event_bus,
    )
    # TwinManager returns RUNNING by default
    status = agent.get_line_status("line-42")
    assert status == LineStatus.RUNNING

    # Verify TwinManager.get_twin_state was called (state exists)
    assert "line-42" in twin_manager.states


def test_shutdown_line_denied_by_approval_gate(twin_manager, event_bus):
    """shutdown_line must be denied when approval_gate denies the action."""
    gate = MockApprovalGate()
    agent = LineSupervisorAgent(
        identity=_make_identity(),
        twin_manager=twin_manager,
        event_bus=event_bus,
        approval_gate=gate,
    )
    result = agent.shutdown_line("line-10")
    assert result["status"] == "denied"
    assert "Approval denied" in result["reason"]
    # TwinManager should NOT be updated when denied
    assert len(twin_manager.update_calls) == 0


@pytest.mark.asyncio
async def test_shutdown_line_publishes_event_on_success(twin_manager, event_bus):
    """shutdown_line must publish TWIN_STATE_UPDATED event after success."""
    gate = MockApprovalGateAllow()
    agent = LineSupervisorAgent(
        identity=_make_identity(),
        twin_manager=twin_manager,
        event_bus=event_bus,
        approval_gate=gate,
    )
    result = agent.shutdown_line("line-20")
    assert result["status"] == "completed"

    # Allow create_task to execute
    await asyncio.sleep(0.01)

    # Event must be published
    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.TWIN_STATE_UPDATED
    assert published["event"].payload["line_id"] == "line-20"
    assert published["event"].payload["status"] == LineStatus.STOPPED.value
    assert published["event"].trace_id.startswith("line-supervisor-")


def test_shutdown_line_updates_twin_state(twin_manager, event_bus):
    """shutdown_line must update twin state to STOPPED."""
    gate = MockApprovalGateAllow()
    agent = LineSupervisorAgent(
        identity=_make_identity(),
        twin_manager=twin_manager,
        event_bus=event_bus,
        approval_gate=gate,
    )
    result = agent.shutdown_line("line-30")
    assert result["status"] == "completed"

    # Verify TwinManager.update_twin_state was called
    assert len(twin_manager.update_calls) == 1
    call = twin_manager.update_calls[0]
    assert call["asset_id"] == "line-30"
    assert call["new_state"]["status"] == LineStatus.STOPPED.value


def test_agent_works_without_optional_dependencies(agent_without_deps):
    """Agent must function when no twin_manager or event_bus is injected."""
    agent = agent_without_deps
    # activate/suspend/terminate must work
    agent.activate()
    agent.suspend("testing")
    agent.activate()
    agent.terminate("done")

    # get_line_status returns None (no twin_manager)
    status = agent.get_line_status("line-99")
    assert status is None

    # shutdown_line with no approval gate = allowed (no gate = skip check)
    # No twin_manager = skip twin update
    # No event_bus = skip event publish
    # Falls through to audit + completed
    result = agent.shutdown_line("line-99")
    assert result["status"] == "completed"

    # Verify audit trail recorded
    actions = [a["action"] for a in agent.audit.action_log]
    assert "line.shutdown.completed" in actions


def test_audit_trail_records_shutdown_attempt(twin_manager, event_bus):
    """shutdown_line must record approval check in audit trail."""
    gate = MockApprovalGate()
    agent = LineSupervisorAgent(
        identity=_make_identity(),
        twin_manager=twin_manager,
        event_bus=event_bus,
        approval_gate=gate,
    )
    agent.shutdown_line("line-50")

    # Find the denied action in audit
    actions = [a["action"] for a in agent.audit.action_log]
    assert "line.shutdown.denied" in actions
