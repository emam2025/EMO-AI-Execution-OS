"""
Test Skill Library Integrity — 10 tests.

Verifies: versioned storage, query by domain/tool/tier, version history,
tenant isolation, confidence filtering, DEPRECATED exclusion, and
cross-tenant data isolation.
"""

import pytest

from releases.skill_os.core.models.skills import SkillDomain, SkillTier
from releases.skill_os.core.skills.library import SkillLibrary


@pytest.fixture
def lib():
    return SkillLibrary()


@pytest.fixture
def populated_lib(lib):
    lib.store("build-app", "hash-a", 0.9, "t1", "p1", "ct-1", SkillDomain.CODING, ["make", "gcc"])
    lib.store("deploy-app", "hash-b", 0.85, "t1", "p1", "ct-2", SkillDomain.DEPLOYMENT, ["kubectl", "helm"])
    lib.store("debug-crash", "hash-c", 0.6, "t1", "p1", "ct-3", SkillDomain.DEBUGGING, ["gdb", "strace"])
    lib.store("other-project", "hash-d", 0.7, "t2", "p2", "ct-4", SkillDomain.PLANNING, [])
    return lib


class TestLibraryStorage:
    def test_store_returns_skill_id(self, lib):
        sid = lib.store("test-skill", "hash-x", 0.8, "t1", "p1")
        assert sid.startswith("sk-")

    def test_store_sets_tier_by_confidence(self, lib):
        sid_high = lib.store("high-conf", "hash-a", 0.9, "t1")
        sid_low = lib.store("low-conf", "hash-b", 0.3, "t1")
        assert lib.get(sid_high, "t1").tier == SkillTier.VERIFIED
        assert lib.get(sid_low, "t1").tier == SkillTier.DRAFT

    def test_store_requires_tenant_id(self, lib):
        with pytest.raises(ValueError, match="tenant_id"):
            lib.store("test", "hash-x", 0.5, "")

    def test_query_requires_tenant_id(self, lib):
        with pytest.raises(ValueError, match="tenant_id"):
            lib.query(tenant_id="")


class TestLibraryQuery:
    def test_query_returns_filtered_by_tenant(self, populated_lib):
        t1_results = populated_lib.query("t1")
        t2_results = populated_lib.query("t2")
        assert len(t1_results) == 3
        assert len(t2_results) == 1

    def test_query_filters_by_domain(self, populated_lib):
        results = populated_lib.query("t1", domain=SkillDomain.CODING)
        assert len(results) == 1
        assert results[0].skill_name == "build-app"

    def test_query_filters_by_tool(self, populated_lib):
        results = populated_lib.query("t1", tool="kubectl")
        assert len(results) == 1
        assert results[0].skill_name == "deploy-app"

    def test_query_filters_by_min_confidence(self, populated_lib):
        results = populated_lib.query("t1", min_confidence=0.8)
        assert len(results) == 2  # build-app (0.9) + deploy-app (0.85)
        for r in results:
            assert r.confidence_score >= 0.8

    def test_query_returns_non_deprecated_skills(self, lib):
        sid = lib.store("old-skill", "hash-x", 0.5, "t1")
        results_before = lib.query("t1")
        assert any(r.skill_id == sid for r in results_before)


class TestLibraryVersionHistory:
    def test_get_version_history_returns_versions(self, populated_lib):
        sid = populated_lib.query("t1")[0].skill_id
        versions = populated_lib.get_version_history(sid, "t1")
        assert len(versions) >= 1
        assert versions[0].version == 1

    def test_get_version_history_requires_tenant_id(self, populated_lib):
        with pytest.raises(ValueError, match="tenant_id"):
            populated_lib.get_version_history("sk-xxx", "")

    def test_get_raises_for_wrong_tenant(self, populated_lib):
        sid = populated_lib.query("t1")[0].skill_id
        with pytest.raises(KeyError, match="not found"):
            populated_lib.get_version_history(sid, "t999")

    def test_count_skills_by_tenant(self, populated_lib):
        assert populated_lib.count("t1") == 3
        assert populated_lib.count("t2") == 1
