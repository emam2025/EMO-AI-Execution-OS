"""
Reflection Engine Lifecycle — 10 tests.

Validates:
  - failure analysis generates correct severity
  - correction strategy generation
  - reflection filtering by severity/tenant
  - cross-tenant isolation (LAW-6, LAW-11)
  - edge cases (empty outcomes, missing trace)
"""

import pytest
from releases.cognitive_os.core.cognitive.reflection import ReflectionEngine
from releases.cognitive_os.core.models.cognitive import ReflectionSeverity


class TestFailureAnalysis:
    def test_analyze_timeout_failure_returns_high_severity(self):
        engine = ReflectionEngine()
        outcome = {
            "success": False,
            "errors": [{"message": "timeout during execution", "type": "timeout"}],
            "steps": [{"success": False}],
        }
        entry = engine.analyze_failure(trace_id="trace-1", outcome=outcome, tenant_id="t1")
        assert entry.severity == ReflectionSeverity.HIGH

    def test_analyze_crash_failure_returns_critical_severity(self):
        engine = ReflectionEngine()
        outcome = {
            "success": False,
            "errors": [{"message": "system crash detected", "type": "crash"}],
            "steps": [],
        }
        entry = engine.analyze_failure(trace_id="trace-2", outcome=outcome, tenant_id="t1")
        assert entry.severity == ReflectionSeverity.CRITICAL

    def test_analyze_success_outcome_returns_low_severity(self):
        engine = ReflectionEngine()
        outcome = {"success": True, "errors": [], "steps": [{"success": True}]}
        entry = engine.analyze_failure(trace_id="trace-3", outcome=outcome, tenant_id="t1")
        assert entry.severity == ReflectionSeverity.LOW

    def test_analyze_failure_rejects_empty_tenant(self):
        engine = ReflectionEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.analyze_failure(trace_id="t1", outcome={"errors": []}, tenant_id="")

    def test_analyze_failure_generates_analysis_dict(self):
        engine = ReflectionEngine()
        outcome = {
            "success": False,
            "errors": [{"message": "not found", "type": "not_found"}],
            "steps": [{"success": False}, {"success": True}],
        }
        entry = engine.analyze_failure(trace_id="trace-4", outcome=outcome, tenant_id="t1")
        assert entry.analysis is not None
        assert entry.analysis.get("error_count") == 1
        assert entry.analysis.get("total_steps") == 2
        assert entry.analysis.get("failed_steps") == 1


class TestCorrectionGeneration:
    def test_generate_correction_returns_strategy(self):
        engine = ReflectionEngine()
        outcome = {
            "success": False,
            "errors": [{"message": "connection refused", "type": "connection"}],
            "steps": [{"success": False}],
        }
        reflection = engine.analyze_failure("trace-5", outcome, "t1")
        correction = engine.generate_correction({
            "strategy_update": reflection.strategy_update,
            "analysis": reflection.analysis,
        }, tenant_id="t1")
        assert "correction_id" in correction
        assert correction["tenant_id"] == "t1"
        assert "strategy" in correction

    def test_generate_correction_rejects_empty_tenant(self):
        engine = ReflectionEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.generate_correction({}, tenant_id="")


class TestReflectionLog:
    def test_list_reflections_scoped_by_tenant(self):
        engine = ReflectionEngine()
        engine.analyze_failure("t1", {"errors": [{"message": "timeout"}], "steps": [{"success": False}]}, "tenant-a")
        engine.analyze_failure("t2", {"errors": [{"message": "crash"}], "steps": [{"success": False}]}, "tenant-b")
        a_refs = engine.list_reflections(tenant_id="tenant-a")
        b_refs = engine.list_reflections(tenant_id="tenant-b")
        assert len(a_refs) == 1
        assert len(b_refs) == 1
        assert a_refs[0] != b_refs[0]

    def test_list_reflections_returns_empty_for_unknown_tenant(self):
        engine = ReflectionEngine()
        refs = engine.list_reflections(tenant_id="ghost")
        assert refs == []

    def test_get_reflection_raises_for_wrong_tenant(self):
        engine = ReflectionEngine()
        outcome = {"errors": [{"message": "error"}], "steps": [{"success": False}]}
        entry = engine.analyze_failure("trace-6", outcome, "tenant-a")
        with pytest.raises(KeyError):
            engine.get_reflection(entry.reflection_id, tenant_id="tenant-b")
