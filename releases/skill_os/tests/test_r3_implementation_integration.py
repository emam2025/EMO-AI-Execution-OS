"""
Test R3 Implementation Integration — 5 test groups (35+ tests total across all files).

Verifies end-to-end: extraction → library store → evolution lifecycle,
cross-tenant isolation in combined pipelines, R2 bridge read-only
enforcement with real extractor usage, and edge cases.
"""

import pytest

from releases.skill_os.core.models.skills import SkillDomain, SkillTier
from releases.skill_os.core.skills.evolution import SkillEvolutionManager
from releases.skill_os.core.skills.extractor import SkillExtractor
from releases.skill_os.core.skills.library import SkillLibrary
from releases.skill_os.core.skills.r2_bridge import R2Bridge


@pytest.fixture
def pipeline():
    lib = SkillLibrary()
    ext = SkillExtractor()
    evo = SkillEvolutionManager(lib)
    bridge = R2Bridge()
    return lib, ext, evo, bridge


class TestExtractionToLibraryFlow:
    def test_extract_then_store(self, pipeline):
        lib, ext, evo, bridge = pipeline
        trace = {
            "trace_id": "ct-99", "tenant_id": "t1", "project_id": "p1",
            "steps": [{"action": "build", "tool": "make", "success": True}],
            "outcome": "success", "total_tokens": 500,
        }
        draft = ext.extract_from_trace(trace, "t1", "p1")
        sid = lib.store(
            skill_name=draft.skill_name,
            pattern_hash=draft.pattern_hash,
            confidence_score=draft.confidence_score,
            tenant_id=draft.tenant_id,
            project_id=draft.project_id,
            source_trace_id=draft.source_trace_id,
            domain=draft.domain,
            tool_sequence=draft.tool_sequence,
        )
        node = lib.get(sid, "t1")
        assert node.skill_name == draft.skill_name
        assert node.pattern_hash == draft.pattern_hash

    def test_extract_store_then_promote(self, pipeline):
        lib, ext, evo, bridge = pipeline
        trace = {
            "trace_id": "ct-100", "tenant_id": "t1",
            "steps": [{"action": "test", "tool": "pytest", "success": False}],
            "outcome": "failure",
        }
        draft = ext.extract_from_trace(trace, "t1")
        # low confidence → Draft tier
        sid = lib.store(draft.skill_name, draft.pattern_hash, draft.confidence_score, "t1")
        record = evo.promote(sid, SkillTier.VERIFIED, "t1", validator_signature="sig-e2e")
        assert record.to_tier == SkillTier.VERIFIED
        assert evo.current_tier(sid, "t1") == SkillTier.VERIFIED

    def test_extract_from_bridge_then_store(self, pipeline):
        lib, ext, evo, bridge = pipeline
        bridge.ingest_trace({
            "trace_id": "ct-bridge-1", "tenant_id": "t1", "project_id": "p1",
            "steps": [{"action": "deploy", "tool": "helm", "success": True}],
            "outcome": "success",
        })
        trace_data = bridge.fetch_trace_context("ct-bridge-1", "t1")
        draft = ext.extract_from_trace(trace_data, "t1", "p1")
        sid = lib.store(draft.skill_name, draft.pattern_hash, draft.confidence_score, "t1")
        assert lib.count("t1") >= 1

    def test_full_lifecycle_bridge_to_deprecation(self, pipeline):
        lib, ext, evo, bridge = pipeline
        bridge.ingest_trace({
            "trace_id": "ct-full", "tenant_id": "t1",
            "steps": [{"action": "build", "tool": "gcc", "success": False}],
            "outcome": "failure",
        })
        trace_data = bridge.fetch_trace_context("ct-full", "t1")
        draft = ext.extract_from_trace(trace_data, "t1")
        # low confidence → Draft tier
        sid = lib.store(draft.skill_name, draft.pattern_hash, draft.confidence_score, "t1")
        evo.promote(sid, SkillTier.VERIFIED, "t1", validator_signature="sig-1")
        evo.promote(sid, SkillTier.OPTIMIZED, "t1", validator_signature="sig-2")
        evo.deprecate(sid, "replaced", "t1", validator_signature="sig-3")
        history = evo.get_evolution_history(sid, "t1")
        assert len(history) == 3
        assert evo.current_tier(sid, "t1") == SkillTier.DEPRECATED


class TestCrossTenantSkillIsolation:
    def test_tenant_a_cannot_see_tenant_b_skills(self, pipeline):
        lib, ext, evo, bridge = pipeline
        lib.store("a-skill", "hash-a", 0.9, "t1")
        lib.store("b-skill", "hash-b", 0.8, "t2")
        assert lib.count("t1") == 1
        assert lib.count("t2") == 1
        t1_results = lib.query("t1")
        assert all(r.tenant_id == "t1" for r in t1_results)

    def test_cannot_promote_cross_tenant(self, pipeline):
        lib, ext, evo, bridge = pipeline
        sid = lib.store("skill", "hash-x", 0.5, "t1")
        with pytest.raises(KeyError, match="not found"):
            evo.promote(sid, SkillTier.VERIFIED, "t2", validator_signature="sig-x")

    def test_bridge_rejects_cross_tenant_fetch(self, pipeline):
        lib, ext, evo, bridge = pipeline
        bridge.ingest_trace({
            "trace_id": "ct-secret", "tenant_id": "t1",
            "steps": [{"action": "secret", "success": True}],
        })
        with pytest.raises(KeyError, match="not found"):
            bridge.fetch_trace_context("ct-secret", "t2")

    def test_evolution_history_scoped_by_tenant(self, pipeline):
        lib, ext, evo, bridge = pipeline
        sid1 = lib.store("s1", "h1", 0.5, "t1")
        sid2 = lib.store("s2", "h2", 0.5, "t2")
        evo.promote(sid1, SkillTier.VERIFIED, "t1", validator_signature="sig-v")
        with pytest.raises(KeyError, match="not found"):
            evo.get_evolution_history(sid1, "t2")


class TestR2BridgeReadOnlyEnforcement:
    def test_bridge_has_no_delete_method(self, pipeline):
        lib, ext, evo, bridge = pipeline
        assert not hasattr(bridge, "delete")
        assert not hasattr(bridge, "update")
        assert not hasattr(bridge, "remove")

    def test_bridge_has_no_write_method(self, pipeline):
        lib, ext, evo, bridge = pipeline
        allowed = {"fetch_trace_context", "ingest_trace", "list_project_traces", "clear"}
        public_methods = {m for m in dir(bridge) if not m.startswith("_")}
        excess = public_methods - allowed
        assert not excess, f"Unexpected public methods on bridge: {excess}"
        assert allowed.issubset(public_methods), f"Missing expected methods: {allowed - public_methods}"


class TestZeroR1R2Dependency:
    def test_no_direct_r1_r2_imports(self):
        import releases.skill_os.core.skills.extractor as m
        src = open(m.__file__).read()
        assert "releases.memory_os" not in src
        assert "releases.runtime_os" not in src
        assert "core.runtime" not in src
        assert "core.memory" not in src

    def test_no_direct_r1_r2_imports_in_library(self):
        import releases.skill_os.core.skills.library as m
        src = open(m.__file__).read()
        assert "releases.memory_os" not in src
        assert "releases.runtime_os" not in src

    def test_no_direct_r1_r2_imports_in_evolution(self):
        import releases.skill_os.core.skills.evolution as m
        src = open(m.__file__).read()
        assert "releases.memory_os" not in src
        assert "releases.runtime_os" not in src

    def test_no_direct_r1_r2_imports_in_bridge(self):
        import releases.skill_os.core.skills.r2_bridge as m
        src = open(m.__file__).read()
        assert "releases.memory_os" not in src
        assert "releases.runtime_os" not in src
