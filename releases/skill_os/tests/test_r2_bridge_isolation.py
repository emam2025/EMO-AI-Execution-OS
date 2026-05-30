"""
Test R2 Bridge Isolation — 5 tests.

Verifies: read-only contract, tenant_id enforcement, trace filtering,
list_project_traces isolation, and zero mutation capability.
"""

import pytest

from releases.skill_os.core.skills.r2_bridge import R2Bridge


@pytest.fixture
def bridge():
    b = R2Bridge()
    b.ingest_trace({
        "trace_id": "ct-1", "cognitive_trace_id": "ct-1",
        "tenant_id": "t1", "project_id": "p1", "agent_id": "a1",
        "steps": [{"action": "build", "tool": "make", "success": True}],
        "outcome": "success", "created_at": 1000.0,
    })
    b.ingest_trace({
        "trace_id": "ct-2", "cognitive_trace_id": "ct-2",
        "tenant_id": "t1", "project_id": "p2", "agent_id": "a2",
        "steps": [{"action": "deploy", "tool": "kubectl", "success": False}],
        "outcome": "failure", "created_at": 2000.0,
    })
    b.ingest_trace({
        "trace_id": "ct-3", "cognitive_trace_id": "ct-3",
        "tenant_id": "t2", "project_id": "p1", "agent_id": "a3",
        "steps": [], "outcome": "unknown", "created_at": 1500.0,
    })
    return b


class TestR2BridgeReadOnly:
    def test_fetch_trace_context_returns_data(self, bridge):
        data = bridge.fetch_trace_context("ct-1", "t1")
        assert data["trace_id"] == "ct-1"
        assert data["project_id"] == "p1"

    def test_fetch_trace_context_requires_tenant_id(self, bridge):
        with pytest.raises(ValueError, match="tenant_id"):
            bridge.fetch_trace_context("ct-1", "")

    def test_fetch_trace_context_cross_tenant_blocked(self, bridge):
        with pytest.raises(KeyError, match="not found"):
            bridge.fetch_trace_context("ct-1", "t2")

    def test_fetch_returns_copy_not_reference(self, bridge):
        data = bridge.fetch_trace_context("ct-1", "t1")
        data["_modified"] = True  # modify the copy
        original = bridge.fetch_trace_context("ct-1", "t1")
        assert "_modified" not in original

    def test_list_project_traces_filters_by_tenant(self, bridge):
        t1_traces = bridge.list_project_traces("p1", "t1")
        t2_traces = bridge.list_project_traces("p1", "t2")
        assert len(t1_traces) == 1
        assert t1_traces[0]["trace_id"] == "ct-1"
        assert len(t2_traces) == 1
        assert t2_traces[0]["trace_id"] == "ct-3"
