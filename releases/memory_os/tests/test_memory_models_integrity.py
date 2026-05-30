"""Task 3 — Data model integrity: 5 tests enforcing strict validation."""

import time
import uuid
import pytest

from releases.memory_os.core.models.memory import (
    ContextWindow,
    ForgettingPolicy,
    MemoryEntry,
    MemoryLayer,
    MemoryScope,
    PruningPolicy,
    RouterQuery,
)


def _make_entry(tenant_id: str = "tenant-a", project_id: str = "proj-1", **kw):
    return MemoryEntry(
        entry_id=kw.get("entry_id", "e1"),
        tenant_id=tenant_id,
        project_id=project_id,
        agent_id=kw.get("agent_id", "agent-1"),
        layer=MemoryLayer.EPISODIC,
        key=kw.get("key", "k1"),
        content_hash=kw.get("content_hash", "abc123"),
        payload=kw.get("payload", {"msg": "hello"}),
        scope=MemoryScope.PROJECT,
    )


class TestMemoryEntryValidation:
    def test_empty_tenant_id_raises(self):
        with pytest.raises(ValueError, match="tenant_id"):
            _make_entry(tenant_id="")

    def test_empty_project_id_raises(self):
        with pytest.raises(ValueError, match="project_id"):
            _make_entry(project_id="")

    def test_empty_agent_id_raises(self):
        with pytest.raises(ValueError, match="agent_id"):
            _make_entry(agent_id="")

    def test_valid_entry_ok(self):
        entry = _make_entry()
        assert entry.tenant_id == "tenant-a"
        assert entry.project_id == "proj-1"
        assert entry.agent_id == "agent-1"


class TestContextWindowValidation:
    def test_empty_tenant_id_raises(self):
        with pytest.raises(ValueError, match="tenant_id"):
            ContextWindow(
                window_id="w1",
                tenant_id="",
                project_id="proj-1",
                cognitive_trace_id="ct1",
                trace_id="t1",
                entries=[],
            )

    def test_empty_project_id_raises(self):
        with pytest.raises(ValueError, match="project_id"):
            ContextWindow(
                window_id="w1",
                tenant_id="tenant-a",
                project_id="",
                cognitive_trace_id="ct1",
                trace_id="t1",
                entries=[],
            )
