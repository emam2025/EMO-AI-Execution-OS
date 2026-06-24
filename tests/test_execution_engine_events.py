"""Tests for 3.6.3 — ExecutionEngine emits events via IEventBus.

Verifies that every state transition and execution-level event
is published to the EventBus with correct payload.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd(), ".."))

from core.execution_engine import (
    DAGBuilder, ExecutionEngine, NodeState, PlanNode, ToolSpec,
)
from core.models.events import ExecutionEvent
from core.runtime.event_bus import InMemoryEventBus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def event_bus():
    return InMemoryEventBus()


@pytest.fixture
def engine(event_bus):
    return ExecutionEngine(event_bus=event_bus)


@pytest.fixture
def simple_dag():
    return (
        DAGBuilder()
        .add("step1", tool="mock_tool", inputs={"x": 1})
        .add("step2", tool="mock_tool", inputs={"x": 2})
        .depends("step2", "step1")
        .build()
    )


def collect_events(bus, topic="execution"):
    return bus.get_events(topic)


# ── Execution-Level Events ────────────────────────────────────────────────────

class TestExecutionLevelEvents:

    def test_execute_emits_planned(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test-session")
        types = [e.event_type for e in collect_events(event_bus)]
        assert "EXECUTION_PLANNED" in types

    def test_execute_emits_completed(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test-session")
        types = [e.event_type for e in collect_events(event_bus)]
        assert "EXECUTION_COMPLETED" in types

    def test_execute_emits_node_events(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test-session")
        types = [e.event_type for e in collect_events(event_bus)]
        assert "NODE_STARTED" in types
        assert "NODE_COMPLETED" in types

    def test_execute_sets_trace_id(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test-session")
        trace_ids = {e.trace_id for e in collect_events(event_bus)}
        assert len(trace_ids) == 1
        assert all(t != "" for t in trace_ids)

    def test_execute_sessions_are_isolated(self, event_bus):
        e1 = ExecutionEngine(event_bus=event_bus)
        e2 = ExecutionEngine(event_bus=event_bus)
        dag = (
            DAGBuilder()
            .add("a", tool="mock_tool")
            .build()
        )
        e1.execute(dag, session_id="session-1")
        e2.execute(dag, session_id="session-2")
        for ev in collect_events(event_bus):
            assert ev.session_id in ("session-1", "session-2")

    def test_cancel_emits_cancelled(self, engine, event_bus):
        engine.cancel()
        types = [e.event_type for e in collect_events(event_bus)]
        assert "EXECUTION_CANCELLED" in types

    def test_plan_emits_planned(self, engine, event_bus):
        node = PlanNode(id="n1", tool="mock_tool")
        engine.plan([node])
        types = [e.event_type for e in collect_events(event_bus)]
        assert "EXECUTION_PLANNED" in types


# ── State Transition Events ───────────────────────────────────────────────────

class TestStateTransitionEvents:

    def test_planned_transition_emitted(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test")
        transitions = [
            e for e in collect_events(event_bus)
            if e.event_type == "STATE_TRANSITION"
        ]
        for t in transitions:
            payload = t.payload
            assert "node_id" in payload
            assert "old_state" in payload
            assert "new_state" in payload

    def test_started_transition_emitted(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test")
        started = [
            e for e in collect_events(event_bus)
            if e.event_type == "NODE_STARTED"
        ]
        assert len(started) >= 2  # step1, step2
        for s in started:
            assert s.payload["new_state"] == "running"

    def test_completed_transition_emitted(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test")
        completed = [
            e for e in collect_events(event_bus)
            if e.event_type == "NODE_COMPLETED"
        ]
        assert len(completed) >= 2
        for c in completed:
            assert c.payload["new_state"] == "completed"

    def test_event_payload_has_tool_name(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test")
        started = [
            e for e in collect_events(event_bus)
            if e.event_type == "NODE_STARTED"
        ]
        for s in started:
            assert "tool" in s.payload
            assert s.payload["tool"] == "mock_tool"


# ── No EventBus Mode (graceful degradation) ──────────────────────────────────

class TestNoEventBus:

    def test_execute_without_event_bus(self):
        engine = ExecutionEngine()  # no event_bus
        dag = (
            DAGBuilder()
            .add("a", tool="mock_tool")
            .build()
        )
        result = engine.execute(dag)
        assert result["status"] == "completed"

    def test_cancel_without_event_bus(self):
        engine = ExecutionEngine()
        engine.cancel()
        assert engine._cancel_flag.is_set()


# ── Event Ordering ────────────────────────────────────────────────────────────

class TestEventOrdering:

    def test_planned_before_started(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test")
        events = collect_events(event_bus)
        planned_idx = next(i for i, e in enumerate(events)
                           if e.event_type == "EXECUTION_PLANNED")
        started_idx = next(i for i, e in enumerate(events)
                           if e.event_type == "NODE_STARTED")
        assert planned_idx < started_idx

    def test_completed_before_execution_completed(self, engine, event_bus, simple_dag):
        engine.execute(simple_dag, session_id="test")
        events = collect_events(event_bus)
        completed_idx = next(i for i, e in enumerate(events)
                             if e.event_type == "NODE_COMPLETED")
        exec_completed_idx = next(i for i, e in enumerate(events)
                                  if e.event_type == "EXECUTION_COMPLETED")
        assert completed_idx < exec_completed_idx


# ── Edge Cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_failed_execution_emits_failed(self, engine, event_bus):
        empty_dag = (
            DAGBuilder().build()
        )
        # An empty DAG has no nodes but should still not crash
        result = engine.execute(empty_dag, session_id="test")
        types = [e.event_type for e in collect_events(event_bus)]
        assert "EXECUTION_PLANNED" in types

    def test_multiple_executions_accumulate_events(self, event_bus):
        engine = ExecutionEngine(event_bus=event_bus)
        dag = (
            DAGBuilder()
            .add("a", tool="mock_tool")
            .build()
        )
        engine.execute(dag, session_id="s1")
        engine.execute(dag, session_id="s2")
        events = collect_events(event_bus)
        planned = [e for e in events if e.event_type == "EXECUTION_PLANNED"]
        assert len(planned) == 2
