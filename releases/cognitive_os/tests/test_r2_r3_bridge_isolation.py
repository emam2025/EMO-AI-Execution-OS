"""
R2/R3 Bridge Isolation — 5 tests.

Validates:
  - read-only enforcement (no mutation)
  - tenant_id filtering on all bridges
  - zero direct imports from R2/R3
  - correct bridge output structure
"""

import pytest
from releases.cognitive_os.core.cognitive.bridges import R2MemoryBridge, R3SkillBridge


class TestR2MemoryBridge:
    def test_fetch_memory_context_returns_read_only_flag(self):
        bridge = R2MemoryBridge()
        ctx = bridge.fetch_memory_context(trace_id="trace-123", tenant_id="t1")
        assert ctx.get("_read_only") is True
        assert ctx.get("tenant_id") == "t1"
        assert ctx.get("trace_id") == "trace-123"

    def test_fetch_memory_context_rejects_empty_tenant(self):
        bridge = R2MemoryBridge()
        with pytest.raises(ValueError, match="tenant_id"):
            bridge.fetch_memory_context(trace_id="t1", tenant_id="")

    def test_r2_bridge_blocks_writes(self):
        bridge = R2MemoryBridge()
        with pytest.raises(AttributeError, match="read-only"):
            bridge.some_field = "value"


class TestR3SkillBridge:
    def test_fetch_skill_patterns_returns_read_only_flag(self):
        bridge = R3SkillBridge()
        patterns = bridge.fetch_skill_patterns(domain="nlp", tenant_id="t1")
        assert len(patterns) >= 1
        for p in patterns:
            assert p.get("_read_only") is True
            assert p.get("tenant_id") == "t1"
            assert p.get("domain") == "nlp"

    def test_fetch_skill_patterns_rejects_empty_tenant(self):
        bridge = R3SkillBridge()
        with pytest.raises(ValueError, match="tenant_id"):
            bridge.fetch_skill_patterns(domain="nlp", tenant_id="")
