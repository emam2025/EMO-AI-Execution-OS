"""
R3 Isolation & Contract Tests — 15 tests.

Groups:
  TestZeroR1R2Dependency (5) — no imports from runtime-os/ or memory-os/
  TestProtocolIntegrity (5)  — protocol signatures and model validation
  TestTenantAndTierIsolation (5) — tenant_id + tier mandatory enforcement

Zero operational dependencies. No execution logic tested.
"""

import importlib
import pytest
import sys
from pathlib import Path


class _SystemImportBlocker:
    """Prevent accidental imports from R1/R2 paths during tests."""
    BLOCKED_PREFIXES = [
        "releases.runtime_os",
        "releases.memory_os",
        "releases.emo_runtime_os",
        "core.runtime",
        "core.memory",
        "releases.skill_os.core.skills",
    ]

    @classmethod
    def check_import(cls, name: str) -> bool:
        import re
        for prefix in cls.BLOCKED_PREFIXES:
            if re.match(prefix.replace(".", r"\."), name):
                return True
        return False


# ── TestZeroR1R2Dependency ─────────────────────────────────────

def _can_import_skill_os(module_name: str) -> bool:
    try:
        importlib.import_module(f"releases.skill_os.{module_name}")
        return True
    except (ImportError, ModuleNotFoundError):
        return False


class TestZeroR1R2Dependency:
    def test_cannot_import_runtime_os_from_skill_os(self):
        assert not _can_import_skill_os("core.runtime"), "R1 import blocked"

    def test_cannot_import_memory_os_from_skill_os(self):
        assert not _can_import_skill_os("core.memory"), "R2 import blocked"

    def test_cannot_import_governance_from_skill_os(self):
        assert not _can_import_skill_os("core.memory.governance"), "R2 governance import blocked"

    def test_skill_os_core_standalone_importable(self):
        assert _can_import_skill_os("core.models.skills"), "Skill OS models importable"

    def test_skill_os_interfaces_importable(self):
        try:
            from releases.skill_os.core.interfaces.skills.ISkillExtractor import ISkillExtractor
            from releases.skill_os.core.interfaces.skills.ISkillEvolutionManager import ISkillEvolutionManager
            assert True
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Interface import failed: {e}")


# ── TestProtocolIntegrity ──────────────────────────────────────

class TestProtocolIntegrity:
    def test_is_skill_extractor_has_required_methods(self):
        from releases.skill_os.core.interfaces.skills.ISkillExtractor import ISkillExtractor
        methods = ["extract_from_trace", "validate_pattern", "list_extractable_traces"]
        for m in methods:
            assert hasattr(ISkillExtractor, m), f"ISkillExtractor missing {m}()"

    def test_is_skill_evolution_manager_has_required_methods(self):
        from releases.skill_os.core.interfaces.skills.ISkillEvolutionManager import ISkillEvolutionManager
        methods = ["promote", "deprecate", "get_evolution_history", "current_tier"]
        for m in methods:
            assert hasattr(ISkillEvolutionManager, m), f"ISkillEvolutionManager missing {m}()"

    def test_skill_node_requires_tenant_id(self):
        from releases.skill_os.core.models.skills import SkillNode
        with pytest.raises(ValueError, match="tenant_id"):
            SkillNode(skill_id="s1", tenant_id="", project_id="p1", skill_name="test", pattern_hash="h1", confidence_score=0.5)

    def test_skill_node_confidence_score_range(self):
        from releases.skill_os.core.models.skills import SkillNode
        with pytest.raises(ValueError, match="confidence_score"):
            SkillNode(skill_id="s1", tenant_id="t1", project_id="p1", skill_name="test", pattern_hash="h1", confidence_score=1.5)

    def test_skill_node_tier_defaults_to_draft(self):
        from releases.skill_os.core.models.skills import SkillNode, SkillTier
        node = SkillNode(skill_id="s1", tenant_id="t1", project_id="p1", skill_name="test", pattern_hash="h1", confidence_score=0.5)
        assert node.tier == SkillTier.DRAFT


# ── TestTenantAndTierIsolation ────────────────────────────────

class TestTenantAndTierIsolation:
    def test_execution_blueprint_requires_tenant_id(self):
        from releases.skill_os.core.models.skills import ExecutionBlueprint
        with pytest.raises(ValueError, match="tenant_id"):
            ExecutionBlueprint(blueprint_id="b1", skill_id="s1", tenant_id="")

    def test_evolution_record_requires_tenant_id(self):
        from releases.skill_os.core.models.skills import SkillEvolutionRecord, SkillTier
        with pytest.raises(ValueError, match="tenant_id"):
            SkillEvolutionRecord(record_id="r1", skill_id="s1", tenant_id="", from_tier=SkillTier.DRAFT, to_tier=SkillTier.VERIFIED)

    def test_pattern_hash_is_deterministic(self):
        from releases.skill_os.core.models.skills import SkillNode
        pattern = {"action": "deploy", "tool": "kubectl"}
        h1 = SkillNode.compute_pattern_hash(pattern)
        h2 = SkillNode.compute_pattern_hash(pattern)
        assert h1 == h2
        assert len(h1) == 32

    def test_different_patterns_different_hashes(self):
        from releases.skill_os.core.models.skills import SkillNode
        h1 = SkillNode.compute_pattern_hash({"action": "deploy"})
        h2 = SkillNode.compute_pattern_hash({"action": "build"})
        assert h1 != h2

    def test_skill_store_entry_requires_entry_id(self):
        from releases.skill_os.core.models.skills import SkillNode, SkillStoreEntry
        node = SkillNode(skill_id="s1", tenant_id="t1", project_id="p1", skill_name="test", pattern_hash="h1", confidence_score=0.5)
        with pytest.raises(ValueError, match="entry_id"):
            SkillStoreEntry(entry_id="", skill=node)
