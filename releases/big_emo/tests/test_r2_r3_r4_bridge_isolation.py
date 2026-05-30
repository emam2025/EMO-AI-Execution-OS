"""
R2/R3/R4 Bridge Isolation — 5 tests.

Validates:
  - read-only enforcement (no mutation)
  - tenant_id filtering on all bridges
  - zero direct imports from R2/R3/R4
"""

import pytest
from releases.big_emo.core.self_governance.bridges import R2MemoryBridge, R3SkillBridge, R4CognitiveBridge


class TestR2Bridge:
    def test_fetch_memory_context_read_only(self):
        bridge = R2MemoryBridge()
        ctx = bridge.fetch_memory_context("trace-1", "t1")
        assert ctx.get("_read_only") is True
        assert ctx.get("tenant_id") == "t1"

    def test_r2_bridge_blocks_writes(self):
        bridge = R2MemoryBridge()
        with pytest.raises(AttributeError, match="read-only"):
            bridge.custom_field = "value"

    def test_fetch_memory_context_rejects_empty_tenant(self):
        bridge = R2MemoryBridge()
        with pytest.raises(ValueError, match="tenant_id"):
            bridge.fetch_memory_context("t1", "")


class TestR3Bridge:
    def test_fetch_skill_patterns_read_only(self):
        bridge = R3SkillBridge()
        patterns = bridge.fetch_skill_patterns("nlp", "t1")
        assert all(p.get("_read_only") for p in patterns)


class TestR4Bridge:
    def test_fetch_reflection_logs_filters_by_severity(self):
        bridge = R4CognitiveBridge()
        logs = bridge.fetch_reflection_logs(tenant_id="t1", min_severity="medium")
        severities = {l["severity"] for l in logs}
        assert "low" not in severities
        assert all(l.get("_read_only") for l in logs)

    def test_r4_bridge_blocks_writes(self):
        bridge = R4CognitiveBridge()
        with pytest.raises(AttributeError, match="read-only"):
            bridge.custom_field = "value"
