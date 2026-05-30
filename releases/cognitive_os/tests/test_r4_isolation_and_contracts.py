"""
R4 Isolation & Contract Tests — 15 tests.

Groups:
  TestZeroR1R2R3Dependency (5) — no imports from runtime-os/, memory-os/, or skill-os/
  TestProtocolIntegrity (5)     — protocol signatures and model validation
  TestTenantAndRiskIsolation (5) — tenant_id + risk_score mandatory enforcement

Zero operational dependencies. No execution logic tested.
"""

import importlib
import pytest
import sys


def _can_import_cognitive(module_name: str) -> bool:
    try:
        importlib.import_module(f"releases.cognitive_os.{module_name}")
        return True
    except (ImportError, ModuleNotFoundError):
        return False


# ── TestZeroR1R2R3Dependency ──────────────────────────────────

class TestZeroR1R2R3Dependency:
    def test_cannot_import_runtime_os(self):
        assert not _can_import_cognitive("core.runtime"), "R1 import blocked"

    def test_cannot_import_memory_os(self):
        assert not _can_import_cognitive("core.memory"), "R2 import blocked"

    def test_cannot_import_skill_os(self):
        assert not _can_import_cognitive("core.skills"), "R3 import blocked"

    def test_cognitive_core_standalone_importable(self):
        assert _can_import_cognitive("core.models.cognitive"), "Cognitive models importable"

    def test_cognitive_interfaces_importable(self):
        try:
            from releases.cognitive_os.core.interfaces.cognitive.IStrategicPlanner import IStrategicPlanner
            from releases.cognitive_os.core.interfaces.cognitive.IReflectionEngine import IReflectionEngine
            from releases.cognitive_os.core.interfaces.cognitive.ISelfEvaluator import ISelfEvaluator
            assert True
        except (ImportError, ModuleNotFoundError) as e:
            pytest.fail(f"Interface import failed: {e}")


# ── TestProtocolIntegrity ─────────────────────────────────────

class TestProtocolIntegrity:
    def test_strategic_planner_has_required_methods(self):
        from releases.cognitive_os.core.interfaces.cognitive.IStrategicPlanner import IStrategicPlanner
        methods = ["decompose_goal", "evaluate_feasibility", "list_active_plans"]
        for m in methods:
            assert hasattr(IStrategicPlanner, m), f"IStrategicPlanner missing {m}()"

    def test_reflection_engine_has_required_methods(self):
        from releases.cognitive_os.core.interfaces.cognitive.IReflectionEngine import IReflectionEngine
        methods = ["analyze_failure", "generate_correction", "list_reflections"]
        for m in methods:
            assert hasattr(IReflectionEngine, m), f"IReflectionEngine missing {m}()"

    def test_self_evaluator_has_required_methods(self):
        from releases.cognitive_os.core.interfaces.cognitive.ISelfEvaluator import ISelfEvaluator
        methods = ["validate_plan_integrity", "assess_risk", "list_evaluations"]
        for m in methods:
            assert hasattr(ISelfEvaluator, m), f"ISelfEvaluator missing {m}()"

    def test_strategic_goal_requires_tenant_id(self):
        from releases.cognitive_os.core.models.cognitive import StrategicGoal
        with pytest.raises(ValueError, match="tenant_id"):
            StrategicGoal(goal_id="g1", tenant_id="", project_id="p1", description="test")

    def test_risk_assessment_requires_tenant_id(self):
        from releases.cognitive_os.core.models.cognitive import RiskAssessment
        with pytest.raises(ValueError, match="tenant_id"):
            RiskAssessment(assessment_id="a1", tenant_id="", plan_id="p1")


# ── TestTenantAndRiskIsolation ────────────────────────────────

class TestTenantAndRiskIsolation:
    def test_plan_hypothesis_requires_tenant_id(self):
        from releases.cognitive_os.core.models.cognitive import PlanHypothesis
        with pytest.raises(ValueError, match="tenant_id"):
            PlanHypothesis(hypothesis_id="h1", tenant_id="", goal_id="g1")

    def test_reflection_entry_requires_tenant_id(self):
        from releases.cognitive_os.core.models.cognitive import ReflectionEntry
        with pytest.raises(ValueError, match="tenant_id"):
            ReflectionEntry(reflection_id="r1", tenant_id="", source_trace_id="ct-1")

    def test_risk_score_bounds(self):
        from releases.cognitive_os.core.models.cognitive import RiskAssessment
        with pytest.raises(ValueError, match="overall_score"):
            RiskAssessment(assessment_id="a1", tenant_id="t1", plan_id="p1", overall_score=1.5)

    def test_confidence_score_bounds(self):
        from releases.cognitive_os.core.models.cognitive import PlanHypothesis
        with pytest.raises(ValueError, match="confidence_score"):
            PlanHypothesis(hypothesis_id="h1", tenant_id="t1", goal_id="g1", confidence_score=-0.1)

    def test_strategic_goal_valid_creation(self):
        from releases.cognitive_os.core.models.cognitive import GoalStatus, StrategicGoal
        g = StrategicGoal(goal_id="g1", tenant_id="t1", project_id="p1", description="deploy system", priority=1)
        assert g.status == GoalStatus.DRAFT
        assert g.priority == 1
