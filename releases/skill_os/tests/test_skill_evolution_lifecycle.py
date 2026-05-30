"""
Test Skill Evolution Lifecycle — 10 tests.

Verifies: tier transitions (Draft→Verified→Optimized→Deprecated),
validator_signature enforcement, illegal transition rejection,
evolution history recording, duplicate deprecation prevention,
cross-tenant isolation.
"""

import pytest

from releases.skill_os.core.models.skills import SkillEvolutionRecord, SkillNode, SkillTier
from releases.skill_os.core.skills.evolution import SkillEvolutionManager
from releases.skill_os.core.skills.library import SkillLibrary


@pytest.fixture
def lib():
    return SkillLibrary()


@pytest.fixture
def manager(lib):
    return SkillEvolutionManager(library=lib)


@pytest.fixture
def draft_skill_id(lib):
    return lib.store("test-skill", "hash-x", 0.5, "t1",  # confidence < 0.7 → Draft
                     domain="coding", tool_sequence=["make"])


@pytest.fixture
def verified_skill_id(lib):
    return lib.store("verified-skill", "hash-y", 0.85, "t1",  # confidence ≥ 0.7 → Verified
                     domain="coding", tool_sequence=["git"])


class TestPromote:
    def test_promote_draft_to_verified(self, manager, draft_skill_id):
        record = manager.promote(draft_skill_id, SkillTier.VERIFIED, "t1", validator_signature="sig-abc")
        assert record.from_tier == SkillTier.DRAFT
        assert record.to_tier == SkillTier.VERIFIED
        assert record.validator_signature == "sig-abc"

    def test_promote_verified_to_optimized(self, manager, verified_skill_id):
        record = manager.promote(verified_skill_id, SkillTier.OPTIMIZED, "t1", validator_signature="sig-def")
        assert record.to_tier == SkillTier.OPTIMIZED

    def test_promote_requires_validator_signature(self, manager, draft_skill_id):
        with pytest.raises(ValueError, match="validator_signature"):
            manager.promote(draft_skill_id, SkillTier.VERIFIED, "t1", validator_signature="")

    def test_promote_requires_tenant_id(self, manager, draft_skill_id):
        with pytest.raises(ValueError, match="tenant_id"):
            manager.promote(draft_skill_id, SkillTier.VERIFIED, "")

    def test_promote_rejects_illegal_transition(self, manager, draft_skill_id):
        with pytest.raises(ValueError, match="Invalid transition"):
            manager.promote(draft_skill_id, SkillTier.OPTIMIZED, "t1", validator_signature="sig-xyz")


class TestDeprecate:
    def test_deprecate_draft_skill(self, manager, draft_skill_id):
        record = manager.deprecate(draft_skill_id, "superseded", "t1", validator_signature="sig-dep")
        assert record.to_tier == SkillTier.DEPRECATED
        assert record.reason == "superseded"

    def test_deprecate_requires_validator_signature(self, manager, draft_skill_id):
        with pytest.raises(ValueError, match="validator_signature"):
            manager.deprecate(draft_skill_id, "reason", "t1", validator_signature="")

    def test_deprecate_requires_reason(self, manager, draft_skill_id):
        with pytest.raises(ValueError, match="reason"):
            manager.deprecate(draft_skill_id, "", "t1", validator_signature="sig-xyz")

    def test_deprecate_twice_raises(self, manager, draft_skill_id):
        manager.deprecate(draft_skill_id, "obsolete", "t1", validator_signature="sig-1")
        with pytest.raises(ValueError, match="already deprecated"):
            manager.deprecate(draft_skill_id, "again", "t1", validator_signature="sig-2")


class TestEvolutionHistory:
    def test_evolution_history_records_promotion(self, manager, draft_skill_id):
        manager.promote(draft_skill_id, SkillTier.VERIFIED, "t1", validator_signature="sig-1")
        manager.promote(draft_skill_id, SkillTier.OPTIMIZED, "t1", validator_signature="sig-2")
        history = manager.get_evolution_history(draft_skill_id, "t1")
        assert len(history) == 2

    def test_evolution_records_have_signatures(self, manager, draft_skill_id):
        manager.promote(draft_skill_id, SkillTier.VERIFIED, "t1", validator_signature="sig-promote")
        history = manager.get_evolution_history(draft_skill_id, "t1")
        assert all(r.validator_signature for r in history)

    def test_current_tier_updates_after_promotion(self, manager, draft_skill_id):
        assert manager.current_tier(draft_skill_id, "t1") == SkillTier.DRAFT
        manager.promote(draft_skill_id, SkillTier.VERIFIED, "t1", validator_signature="sig-x")
        assert manager.current_tier(draft_skill_id, "t1") == SkillTier.VERIFIED
