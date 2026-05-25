"""Tests for 3.4.5.3 — CanonValidator Runtime Enforcement Engine."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.canon import (
    DEFAULT_RULES,
    CanonRule,
    CanonValidationResult,
    CanonValidator,
    CanonViolation,
    ValidationContext,
    load_canon_from_markdown,
)
from core.canon.rules import LAW_FACTORY, law_14, law_15, law_16, law_28, law_29, law_30


# ── CanonRule Model ───────────────────────────────────────────────────────────

class TestCanonRule:

    def test_canon_rule_creation(self):
        rule = CanonRule(
            id="TEST_1",
            description="Test rule",
            severity="HIGH",
            evaluate=lambda ctx: True,
            message="Test message",
        )
        assert rule.id == "TEST_1"
        assert rule.severity == "HIGH"

# ── CanonRule Tests ───────────────────────────────────────────────────────────

class TestCanonViolation:

    def test_violation_string(self):
        v = CanonViolation(rule_id="LAW_14", message="Test", severity="HIGH")
        assert "LAW_14" in str(v)
        assert "HIGH" in str(v)

    def test_violation_with_context(self):
        v = CanonViolation(
            rule_id="LAW_16",
            message="High risk",
            severity="CRITICAL",
            context={"file": "core/x.py", "risk_score": 0.9},
        )
        assert v.context["risk_score"] == 0.9

# ── CanonValidationResult Tests ──────────────────────────────────────────────

class TestCanonValidationResult:

    def test_allowed_result(self):
        result = CanonValidationResult(allowed=True)
        assert result.allowed is True
        assert result.block is False

    def test_blocked_result(self):
        result = CanonValidationResult(allowed=False, severity="CRITICAL")
        assert result.block is True

    def test_violations_in_result(self):
        v = CanonViolation(rule_id="LAW_14", message="No graph", severity="HIGH")
        result = CanonValidationResult(allowed=False, violations=[v])
        assert len(result.violations) == 1

# ── Canon Rules Tests ─────────────────────────────────────────────────────────

class TestCanonRules:

    def test_law_14_with_graph(self):
        class MockGraph:
            pass
        ctx = ValidationContext(graph=MockGraph())
        assert law_14(ctx) is True

    def test_law_14_without_graph(self):
        ctx = ValidationContext(graph=None)
        assert law_14(ctx) is False

    def test_law_15_with_version(self):
        class MockGraph:
            version = "v1"
        ctx = ValidationContext(graph=MockGraph())
        assert law_15(ctx) is True

    def test_law_15_without_version(self):
        class MockGraph:
            version = None
        ctx = ValidationContext(graph=MockGraph())
        assert law_15(ctx) is False

    def test_law_15_no_graph(self):
        ctx = ValidationContext(graph=None)
        assert law_15(ctx) is True  # passes when no graph (can't check)

    def test_law_16_all_below_threshold(self):
        class MockNode:
            risk_score = 0.5
        class MockGraph:
            nodes = {"n1": MockNode()}
        ctx = ValidationContext(graph=MockGraph())
        assert law_16(ctx) is True

    def test_law_16_with_high_risk(self):
        class MockNode:
            risk_score = 0.9
        class MockGraph:
            nodes = {"n1": MockNode()}
        ctx = ValidationContext(graph=MockGraph())
        assert law_16(ctx) is False

    def test_law_16_no_graph(self):
        ctx = ValidationContext(graph=None)
        assert law_16(ctx) is True  # passes when no graph

    def test_law_16_node_without_risk_score(self):
        class MockNode:
            pass
        class MockGraph:
            nodes = {"n1": MockNode()}
        ctx = ValidationContext(graph=MockGraph())
        assert law_16(ctx) is True

    def test_law_28_with_approval_func(self):
        ctx = ValidationContext(evolution_approval_func=lambda s: True)
        assert law_28(ctx) is True

    def test_law_28_without_approval_func(self):
        ctx = ValidationContext()
        assert law_28(ctx) is False

    def test_law_29_with_audit_log(self):
        ctx = ValidationContext(evolution_audit_log=lambda e: None)
        assert law_29(ctx) is True

    def test_law_29_without_audit_log(self):
        ctx = ValidationContext()
        assert law_29(ctx) is False

    def test_law_30_with_rollback_func(self):
        ctx = ValidationContext(evolution_rollback_func=lambda t: True)
        assert law_30(ctx) is True

    def test_law_30_without_rollback_func(self):
        ctx = ValidationContext()
        assert law_30(ctx) is False

    def test_law_factory_contains_all(self):
        assert "LAW_14" in LAW_FACTORY
        assert "LAW_15" in LAW_FACTORY
        assert "LAW_16" in LAW_FACTORY
        assert "LAW_28" in LAW_FACTORY
        assert "LAW_29" in LAW_FACTORY
        assert "LAW_30" in LAW_FACTORY

# ── CanonValidator Tests ──────────────────────────────────────────────────────

class TestCanonValidator:

    @pytest.fixture
    def always_pass_rule(self):
        return CanonRule(
            id="PASS", description="Always passes",
            severity="LOW", evaluate=lambda ctx: True,
            message="Should not appear",
        )

    @pytest.fixture
    def always_fail_rule(self):
        return CanonRule(
            id="FAIL", description="Always fails",
            severity="HIGH", evaluate=lambda ctx: False,
            message="This rule always fails",
        )

    def test_validate_with_no_violations(self, always_pass_rule):
        validator = CanonValidator(rules=[always_pass_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is True
        assert len(result.violations) == 0

    def test_validate_with_violation(self, always_fail_rule):
        validator = CanonValidator(rules=[always_fail_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is False
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "FAIL"

    def test_validate_mixed_rules(self, always_pass_rule, always_fail_rule):
        validator = CanonValidator(rules=[always_pass_rule, always_fail_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is False
        assert len(result.violations) == 1

    def test_rule_execution_error_caught(self):
        broken_rule = CanonRule(
            id="BROKEN", description="Raises exception",
            severity="LOW", evaluate=lambda ctx: 1/0,
            message="Should not appear",
        )
        validator = CanonValidator(rules=[broken_rule])
        result = validator.validate(ValidationContext())
        assert len(result.violations) == 1
        assert "error" in result.violations[0].context

    def test_severity_low_does_not_block(self):
        low_rule = CanonRule(
            id="LOW_FAIL", description="Low severity fail",
            severity="LOW", evaluate=lambda ctx: False,
            message="Low severity",
        )
        validator = CanonValidator(rules=[low_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is True  # LOW severity allows

    def test_severity_medium_does_not_block(self):
        med_rule = CanonRule(
            id="MED_FAIL", description="Medium severity fail",
            severity="MEDIUM", evaluate=lambda ctx: False,
            message="Medium severity",
        )
        validator = CanonValidator(rules=[med_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is True  # MEDIUM severity allows

    def test_severity_high_blocks(self):
        high_rule = CanonRule(
            id="HIGH_FAIL", description="High severity fail",
            severity="HIGH", evaluate=lambda ctx: False,
            message="High severity",
        )
        validator = CanonValidator(rules=[high_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is False

    def test_severity_critical_blocks(self):
        crit_rule = CanonRule(
            id="CRIT_FAIL", description="Critical severity fail",
            severity="CRITICAL", evaluate=lambda ctx: False,
            message="Critical severity",
        )
        validator = CanonValidator(rules=[crit_rule])
        result = validator.validate(ValidationContext())
        assert result.allowed is False

    def test_default_rules_loaded(self):
        assert len(DEFAULT_RULES) >= 3
        ids = [r.id for r in DEFAULT_RULES]
        assert "LAW_14" in ids
        assert "LAW_15" in ids
        assert "LAW_16" in ids

    def test_validator_with_default_rules(self):
        """With no graph, LAW 14 should fail."""
        validator = CanonValidator()  # uses DEFAULT_RULES
        result = validator.validate(ValidationContext(graph=None))
        assert len(result.violations) >= 1
        # At least LAW_14 should trigger
        law_14_violations = [v for v in result.violations if v.rule_id == "LAW_14"]
        assert len(law_14_violations) >= 1

    def test_validator_with_graph_passes_law_14(self):
        class MockGraph:
            version = "v1"
            nodes = {}
        validator = CanonValidator()
        ctx = ValidationContext(graph=MockGraph())
        result = validator.validate(ctx)
        law_14_violations = [v for v in result.violations if v.rule_id == "LAW_14"]
        assert len(law_14_violations) == 0

# ── Markdown Loader Tests ─────────────────────────────────────────────────────

class TestMarkdownLoader:

    def test_load_table_format(self):
        md = """| **LAW 14** | All boundary decisions MUST be derived from CodeGraph analysis |
| **LAW 15** | No refactor is valid unless dependency graph is updated first |"""
        rules = load_canon_from_markdown(md)
        assert len(rules) >= 2
        assert rules[0]["id"] == "LAW_14"

    def test_load_inline_format(self):
        md = """
**LAW 14:** All boundary decisions MUST be derived from CodeGraph analysis.
**LAW 15:** No refactor is valid unless dependency graph is updated first.
"""
        rules = load_canon_from_markdown(md)
        assert len(rules) >= 2

    def test_load_empty_text(self):
        rules = load_canon_from_markdown("")
        assert rules == []

# ── Integration: CanonValidator + emo-guard ───────────────────────────────────

class TestIntegration:

    def test_emo_guard_with_canon(self):
        """emo-guard should report canon violations."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/emo-guard", "--diff-only"],
            capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        # emo-guard should run without crashes
        assert result.returncode == 0
        # Should report something (either pass or violations)
        assert "PASSED" in result.stdout or "BLOCKED" in result.stdout
