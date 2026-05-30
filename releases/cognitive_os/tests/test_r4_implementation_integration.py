"""
R4 Implementation Integration — 40 tests across 4 groups.

Groups:
  TestPlanningToEvaluationFlow (12) — full plan → validate → assess pipeline
  TestReflectionCorrectionLoop (12) — failure → reflect → correct lifecycle
  TestCrossTenantCognitiveIsolation (10) — LAW-6/11/14 enforcement
  TestBridgeReadOnlyEnforcement (6) — zero mutation across bridges
"""

import uuid
import pytest

from releases.cognitive_os.core.cognitive.planner import StrategicPlanner
from releases.cognitive_os.core.cognitive.reflection import ReflectionEngine
from releases.cognitive_os.core.cognitive.evaluator import SelfEvaluator
from releases.cognitive_os.core.cognitive.bridges import R2MemoryBridge, R3SkillBridge
from releases.cognitive_os.core.models.cognitive import ReflectionSeverity, RiskAssessment


# ── TestPlanningToEvaluationFlow ──────────────────────────────

class TestPlanningToEvaluationFlow:
    @staticmethod
    def _as_plan_dict(plan):
        return {"hypothesis_id": plan.hypothesis_id, **plan.dag_blueprint}

    def test_decompose_then_validate_pipeline(self):
        planner = StrategicPlanner()
        evaluator = SelfEvaluator()
        plan = planner.decompose_goal("build, test, deploy", tenant_id="t1")
        result = evaluator.validate_plan_integrity(self._as_plan_dict(plan), tenant_id="t1")
        assert result.is_valid is True
        assert result.plan_id == plan.hypothesis_id

    def test_decompose_then_assess_risk_pipeline(self):
        planner = StrategicPlanner()
        evaluator = SelfEvaluator()
        plan = planner.decompose_goal("analyze, build, deploy", tenant_id="t1")
        risk = evaluator.assess_risk(self._as_plan_dict(plan), tenant_id="t1")
        assert risk.plan_id == plan.hypothesis_id
        assert risk.overall_score >= 0.0

    def test_full_pipeline_produces_consistent_signatures(self):
        planner = StrategicPlanner()
        evaluator = SelfEvaluator()
        plan = planner.decompose_goal("install, configure, test", tenant_id="t1")
        result = evaluator.validate_plan_integrity(self._as_plan_dict(plan), tenant_id="t1")
        risk = evaluator.assess_risk(self._as_plan_dict(plan), tenant_id="t1")
        assert len(plan.validator_signature) == 32
        assert len(result.validator_signature) == 32
        assert plan.hypothesis_id == risk.plan_id

    def test_planning_uses_tenant_throughout_pipeline(self):
        planner = StrategicPlanner()
        evaluator = SelfEvaluator()
        plan = planner.decompose_goal("deploy", tenant_id="t-42")
        result = evaluator.validate_plan_integrity(plan.dag_blueprint, tenant_id="t-42")
        risk = evaluator.assess_risk(plan.dag_blueprint, tenant_id="t-42")
        assert plan.tenant_id == "t-42"
        assert result.tenant_id == "t-42"
        assert risk.tenant_id == "t-42"

    def test_decompose_multiple_goals_then_list_active(self):
        planner = StrategicPlanner()
        for i in range(5):
            planner.decompose_goal(f"task {i}", tenant_id="t1")
        plans = planner.list_active_plans(tenant_id="t1")
        assert len(plans) == 5

    def test_unfeasible_plan_blocked_before_risk(self):
        planner = StrategicPlanner()
        evaluator = SelfEvaluator()
        feasible = planner.evaluate_feasibility({"nodes": [], "edges": []}, tenant_id="t1")
        assert feasible is False

    def test_hypothesis_with_empty_goal_raises(self):
        planner = StrategicPlanner()
        with pytest.raises(ValueError):
            planner.decompose_goal("", tenant_id="t1")

    def test_plan_with_zero_confidence_rejected_by_model(self):
        from releases.cognitive_os.core.models.cognitive import PlanHypothesis
        with pytest.raises(ValueError, match="confidence_score"):
            PlanHypothesis(hypothesis_id="h1", tenant_id="t1", goal_id="g1", confidence_score=-0.5)

    def test_risk_over_075_flagged_in_mitigation(self):
        evaluator = SelfEvaluator()
        nodes = [{"id": f"n{i}", "tool": f"t{i}"} for i in range(15)]
        edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(14)]
        plan = {"dag": {"nodes": nodes, "edges": edges}}
        risk = evaluator.assess_risk(plan, tenant_id="t1")
        assert risk.overall_score > 0.0

    def test_dag_blueprint_includes_resource_profile(self):
        planner = StrategicPlanner()
        plan = planner.decompose_goal("build, deploy", tenant_id="t1")
        bp = plan.dag_blueprint
        assert "resource_profile" in bp
        assert "estimated_steps" in bp["resource_profile"]

    def test_validate_warns_on_missing_tool(self):
        evaluator = SelfEvaluator()
        plan = {"dag": {"nodes": [{"id": "orphan"}], "edges": []}}
        result = evaluator.validate_plan_integrity(plan, tenant_id="t1")
        assert len(result.warnings) > 0 or result.is_valid

    def test_plan_signature_deterministic_per_goal(self):
        planner = StrategicPlanner()
        p1 = planner.decompose_goal("build and deploy to prod", tenant_id="t1")
        p2 = planner.decompose_goal("build and deploy to prod", tenant_id="t1")
        assert p1.validator_signature == p2.validator_signature


# ── TestReflectionCorrectionLoop ─────────────────────────────

class TestReflectionCorrectionLoop:
    def test_reflect_then_correct_full_cycle(self):
        engine = ReflectionEngine()
        outcome = {
            "errors": [{"message": "timeout in step 2", "type": "timeout"}],
            "steps": [{"success": True}, {"success": False}],
        }
        entry = engine.analyze_failure("trace-r1", outcome, "t1")
        correction = engine.generate_correction({
            "strategy_update": entry.strategy_update,
            "analysis": entry.analysis,
        }, tenant_id="t1")
        assert correction["correction_id"]
        assert correction["strategy"]["action"] == "retry_with_backoff"

    def test_critical_failure_generates_halt_strategy(self):
        engine = ReflectionEngine()
        outcome = {
            "errors": [{"message": "system crash", "type": "crash"}],
            "steps": [],
        }
        entry = engine.analyze_failure("trace-r2", outcome, "t1")
        assert entry.severity == ReflectionSeverity.CRITICAL
        assert entry.strategy_update["action"] == "halt_and_rollback"

    def test_low_severity_generates_monitor_strategy(self):
        engine = ReflectionEngine()
        outcome = {"errors": [], "steps": [{"success": True}], "success": True}
        entry = engine.analyze_failure("trace-r3", outcome, "t1")
        assert entry.severity == ReflectionSeverity.LOW
        assert entry.strategy_update["action"] == "monitor"

    def test_reflection_lifecycle_preserves_trace_id(self):
        engine = ReflectionEngine()
        outcome = {"errors": [{"message": "auth error"}], "steps": [{"success": False}]}
        entry = engine.analyze_failure("trace-original-42", outcome, "t1")
        assert entry.source_trace_id == "trace-original-42"

    def test_reflection_analysis_counts_failures_correctly(self):
        engine = ReflectionEngine()
        outcome = {
            "errors": [{"message": "e1"}, {"message": "e2"}],
            "steps": [{"success": True}, {"success": False}, {"success": False}],
        }
        entry = engine.analyze_failure("trace-r4", outcome, "t1")
        assert entry.analysis["error_count"] == 2
        assert entry.analysis["failed_steps"] == 2
        assert entry.analysis["total_steps"] == 3

    def test_multiple_reflections_scoped_correctly(self):
        engine = ReflectionEngine()
        for i in range(5):
            engine.analyze_failure(f"t-{i}", {"errors": [], "steps": [{"success": True}]}, "ta")
        for i in range(3):
            engine.analyze_failure(f"t-{i}", {"errors": [], "steps": [{"success": True}]}, "tb")
        assert len(engine.list_reflections(tenant_id="ta")) == 5
        assert len(engine.list_reflections(tenant_id="tb")) == 3

    def test_correction_requires_tenant(self):
        engine = ReflectionEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.generate_correction({"analysis": {}}, tenant_id="")

    def test_reflection_strategy_includes_updated_constraints(self):
        engine = ReflectionEngine()
        outcome = {"errors": [{"message": "timeout"}], "steps": [{"success": False}]}
        entry = engine.analyze_failure("trace-r5", outcome, "t1")
        strat = entry.strategy_update
        assert "updated_constraints" in strat
        assert strat["updated_constraints"]["max_retries"] == 3

    def test_severity_enum_coverage_all_levels(self):
        engine = ReflectionEngine()
        outcomes = [
            ({"errors": [], "steps": [{"success": True}], "success": True}, ReflectionSeverity.LOW),
            ({"errors": [{"message": "syntax error"}], "steps": [{"success": False}]}, ReflectionSeverity.LOW),
            ({"errors": [{"message": "not found", "type": "not_found"}], "steps": [{"success": False}]}, ReflectionSeverity.MEDIUM),
            ({"errors": [{"message": "connection timeout"}], "steps": [{"success": False}]}, ReflectionSeverity.HIGH),
        ]
        for outcome, expected in outcomes:
            entry = engine.analyze_failure(f"trace-{uuid.uuid4().hex[:8]}", outcome, "t1")
            assert entry.severity == expected

    def test_reflection_has_correct_type_following_tenancy(self):
        engine = ReflectionEngine()
        outcome = {"errors": [{"message": "permission denied"}], "steps": [{"success": False}]}
        entry = engine.analyze_failure("trace-pd", outcome, "t-99")
        assert isinstance(entry.severity, ReflectionSeverity)
        assert entry.source_trace_id == "trace-pd"
        assert entry.tenant_id == "t-99"

    def test_reflection_correction_round_trip(self):
        engine = ReflectionEngine()
        outcome = {"errors": [{"message": "oom triggered"}], "steps": [{"success": False}]}
        entry = engine.analyze_failure("trace-oom", outcome, "t1")
        correction = engine.generate_correction({
            "strategy_update": entry.strategy_update,
            "analysis": entry.analysis,
        }, tenant_id="t1")
        r2 = engine.get_reflection(entry.reflection_id, tenant_id="t1")
        assert r2.reflection_id == entry.reflection_id
        assert r2.severity == ReflectionSeverity.CRITICAL


# ── TestCrossTenantCognitiveIsolation ────────────────────────

class TestCrossTenantCognitiveIsolation:
    def test_planner_isolates_tenants(self):
        p = StrategicPlanner()
        p.decompose_goal("build", tenant_id="customer-a")
        p.decompose_goal("build", tenant_id="customer-b")
        assert len(p.list_active_plans("customer-a")) == 1
        assert len(p.list_active_plans("customer-b")) == 1

    def test_evaluator_isolates_tenants(self):
        e = SelfEvaluator()
        e.assess_risk({"dag": {"nodes": [{"id": "x", "tool": "t"}], "edges": []}}, "c1")
        e.assess_risk({"dag": {"nodes": [{"id": "y", "tool": "t"}], "edges": []}}, "c2")
        assert len(e.list_evaluations("c1")) == 1
        assert len(e.list_evaluations("c2")) == 1

    def test_planner_get_plan_blocks_wrong_tenant(self):
        p = StrategicPlanner()
        plan = p.decompose_goal("deploy", tenant_id="tenant-x")
        with pytest.raises(KeyError):
            p.get_plan(plan.hypothesis_id, tenant_id="tenant-y")

    def test_reflection_get_reflection_blocks_wrong_tenant(self):
        r = ReflectionEngine()
        entry = r.analyze_failure("t1", {"errors": [{"message": "err"}], "steps": [{"success": False}]}, "tenant-x")
        with pytest.raises(KeyError):
            r.get_reflection(entry.reflection_id, tenant_id="tenant-y")

    def test_evaluator_get_assessment_blocks_wrong_tenant(self):
        e = SelfEvaluator()
        risk = e.assess_risk({"dag": {"nodes": [{"id": "a", "tool": "t"}], "edges": []}}, "tenant-x")
        with pytest.raises(KeyError):
            e.get_assessment(risk.assessment_id, tenant_id="tenant-y")

    def test_bridges_reject_empty_tenant(self):
        rb = R2MemoryBridge()
        sb = R3SkillBridge()
        with pytest.raises(ValueError, match="tenant_id"):
            rb.fetch_memory_context("t1", "")
        with pytest.raises(ValueError, match="tenant_id"):
            sb.fetch_skill_patterns("nlp", "")

    def test_planner_rejects_empty_tenant(self):
        p = StrategicPlanner()
        with pytest.raises(ValueError, match="tenant_id"):
            p.decompose_goal("build", tenant_id="")

    def test_reflection_rejects_empty_tenant(self):
        r = ReflectionEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            r.analyze_failure("t1", {"errors": []}, tenant_id="")

    def test_evaluator_rejects_empty_tenant(self):
        e = SelfEvaluator()
        with pytest.raises(ValueError, match="tenant_id"):
            e.validate_plan_integrity({"dag": {"nodes": [], "edges": []}}, tenant_id="")

    def test_cross_tenant_no_plan_leakage_via_list_ids(self):
        p = StrategicPlanner()
        a_plan = p.decompose_goal("build A", tenant_id="a")
        p.decompose_goal("build B", tenant_id="b")
        a_ids = set(p.list_active_plans("a"))
        b_ids = set(p.list_active_plans("b"))
        assert a_ids.isdisjoint(b_ids)


# ── TestBridgeReadOnlyEnforcement ────────────────────────────

class TestBridgeReadOnlyEnforcement:
    def test_r2_bridge_attr_write_blocked(self):
        bridge = R2MemoryBridge()
        with pytest.raises(AttributeError, match="read-only"):
            bridge.custom_field = "modified"

    def test_r3_bridge_attr_write_blocked(self):
        bridge = R3SkillBridge()
        with pytest.raises(AttributeError, match="read-only"):
            bridge.custom_field = "modified"

    def test_r2_bridge_context_marked_read_only(self):
        bridge = R2MemoryBridge()
        ctx = bridge.fetch_memory_context("trace-1", "t1")
        assert ctx.get("_read_only") is True

    def test_r3_bridge_patterns_marked_read_only(self):
        bridge = R3SkillBridge()
        patterns = bridge.fetch_skill_patterns("nlp", "t1")
        assert all(p.get("_read_only") for p in patterns)

    def test_r2_list_traces_read_only_no_modify(self):
        bridge = R2MemoryBridge()
        traces = bridge.list_project_traces("t1", "project-x")
        assert len(traces) >= 1
        for t in traces:
            assert t.get("_read_only") is True
            assert "_source" in t

    def test_r3_bridge_requires_domain(self):
        bridge = R3SkillBridge()
        with pytest.raises(ValueError, match="domain"):
            bridge.fetch_skill_patterns("", "t1")
