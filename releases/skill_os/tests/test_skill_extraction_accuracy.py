"""
Test Skill Extraction Accuracy — 10 tests.

Verifies: extraction precision, field completeness, domain detection,
confidence scoring, pattern hashing, guardrail extraction, tenant
isolation, and zero cross-tenant leakage.
"""

import pytest

from releases.skill_os.core.skills.extractor import SkillDraft, SkillExtractor
from releases.skill_os.core.models.skills import SkillDomain


@pytest.fixture
def extractor():
    return SkillExtractor()


@pytest.fixture
def sample_trace():
    return {
        "trace_id": "ct-build-001",
        "cognitive_trace_id": "ct-build-001",
        "tenant_id": "t1",
        "project_id": "p1",
        "agent_id": "agent-alpha",
        "steps": [
            {"action": "build", "tool": "docker", "success": True, "duration_ms": 1200},
            {"action": "test", "tool": "pytest", "success": True, "duration_ms": 3000},
            {"action": "deploy", "tool": "kubectl", "success": True, "duration_ms": 800},
        ],
        "decisions": [
            {"decision": "use_base_image", "rationale": "security_patch"},
        ],
        "outcome": "success",
        "total_tokens": 4500,
        "errors": [],
    }


class TestExtractionAccuracy:
    def test_extract_from_trace_returns_draft(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert isinstance(draft, SkillDraft)
        assert draft.tenant_id == "t1"
        assert draft.project_id == "p1"

    def test_extract_detects_correct_domain(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert draft.domain == SkillDomain.DEPLOYMENT

    def test_extract_confidence_in_range(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert 0.0 <= draft.confidence_score <= 1.0
        assert draft.confidence_score > 0.5  # all-success trace

    def test_extract_includes_tool_sequence(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert "docker" in draft.tool_sequence
        assert "pytest" in draft.tool_sequence
        assert "kubectl" in draft.tool_sequence

    def test_extract_generates_pattern_hash(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert len(draft.pattern_hash) == 32
        assert isinstance(draft.pattern_hash, str)

    def test_validate_pattern_accepts_valid_draft(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert extractor.validate_pattern(draft, "t1") is True

    def test_validate_pattern_rejects_wrong_tenant(self, extractor, sample_trace):
        draft = extractor.extract_from_trace(sample_trace, "t1", "p1")
        assert extractor.validate_pattern(draft, "t2") is False


class TestConfidenceAndEdgeCases:
    def test_calculate_confidence_all_success(self, extractor):
        assert extractor.calculate_confidence(1.0, 1.0) == 1.0

    def test_calculate_confidence_all_failure(self, extractor):
        assert extractor.calculate_confidence(0.0, 0.0) == 0.0

    def test_extract_empty_trace(self, extractor):
        draft = extractor.extract_from_trace({}, "t1")
        assert draft.skill_name.startswith("skill-")
        assert draft.confidence_score == 0.0

    def test_extract_trace_filters_by_tenant_id(self, extractor):
        t1_trace = {"trace_id": "ct-1", "tenant_id": "t1", "steps": [{"action": "build", "tool": "make", "success": True}]}
        t2_traces = [
            {"trace_id": "ct-2", "tenant_id": "t2", "steps": [{"action": "deploy", "success": True}]},
        ]
        eligible = extractor.list_extractable_traces(
            [t1_trace, *t2_traces], tenant_id="t1", min_confidence=0.0
        )
        assert "ct-1" in eligible
        assert "ct-2" not in eligible
