"""
Self Evaluation & Risk — 10 tests.

Validates:
  - plan integrity validation detects invalid DAGs
  - risk scoring accuracy for complex/trivial plans
  - tenant isolation (LAW-6, LAW-11)
  - zero unauthorized risk bypass
  - validator_signature generation
"""

import uuid
import pytest
from releases.cognitive_os.core.cognitive.evaluator import SelfEvaluator, ValidationResult, RiskScore
from releases.cognitive_os.core.models.cognitive import RiskAssessment


class TestPlanIntegrity:
    def test_validate_healthy_dag_passes(self):
        evaluator = SelfEvaluator()
        plan = {
            "hypothesis_id": f"h-{uuid.uuid4().hex[:8]}",
            "dag": {
                "nodes": [{"id": "build", "tool": "builder"}, {"id": "deploy", "tool": "deployer"}],
                "edges": [{"from": "build", "to": "deploy"}],
            },
        }
        result = evaluator.validate_plan_integrity(plan, tenant_id="t1")
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.tenant_id == "t1"

    def test_validate_empty_dag_fails(self):
        evaluator = SelfEvaluator()
        plan = {"dag": {"nodes": [], "edges": []}}
        result = evaluator.validate_plan_integrity(plan, tenant_id="t1")
        assert result.is_valid is False
        errors_text = " ".join(result.errors)
        assert "no nodes" in errors_text.lower()

    def test_validate_dag_with_orphan_edge_fails(self):
        evaluator = SelfEvaluator()
        plan = {
            "dag": {
                "nodes": [{"id": "build", "tool": "builder"}],
                "edges": [{"from": "build", "to": "phantom"}],
            },
        }
        result = evaluator.validate_plan_integrity(plan, tenant_id="t1")
        assert result.is_valid is False
        assert any("phantom" in e for e in result.errors)

    def test_validate_generates_unique_signature(self):
        evaluator = SelfEvaluator()
        plan1 = {"dag": {"nodes": [{"id": "a", "tool": "t1"}], "edges": []}}
        plan2 = {"dag": {"nodes": [{"id": "b", "tool": "t2"}], "edges": []}}
        r1 = evaluator.validate_plan_integrity(plan1, tenant_id="t1")
        r2 = evaluator.validate_plan_integrity(plan2, tenant_id="t1")
        assert r1.validator_signature != r2.validator_signature

    def test_validate_rejects_empty_tenant(self):
        evaluator = SelfEvaluator()
        with pytest.raises(ValueError, match="tenant_id"):
            evaluator.validate_plan_integrity({"dag": {"nodes": [], "edges": []}}, tenant_id="")


class TestRiskAssessment:
    def test_assess_trivial_plan_returns_low_risk(self):
        evaluator = SelfEvaluator()
        plan = {"dag": {"nodes": [{"id": "x", "tool": "t"}], "edges": []}}
        risk = evaluator.assess_risk(plan, tenant_id="t1")
        assert risk.overall_score <= 0.1
        assert risk.tenant_id == "t1"

    def test_assess_complex_plan_returns_higher_risk(self):
        evaluator = SelfEvaluator()
        nodes = [{"id": f"n{i}", "tool": f"t{i}"} for i in range(10)]
        edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(9)]
        plan = {"dag": {"nodes": nodes, "edges": edges}}
        risk = evaluator.assess_risk(plan, tenant_id="t1")
        assert risk.overall_score > 0.2
        assert any(f["factor"] == "complexity" for f in risk.risk_factors)

    def test_assess_risk_includes_mitigation_plan(self):
        evaluator = SelfEvaluator()
        nodes = [{"id": f"n{i}", "tool": f"t{i}"} for i in range(10)]
        edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(9)]
        plan = {"dag": {"nodes": nodes, "edges": edges}}
        risk = evaluator.assess_risk(plan, tenant_id="t1")
        assert risk.mitigation_plan is not None
        assert "suggested_actions" in risk.mitigation_plan

    def test_assess_risk_rejects_empty_tenant(self):
        evaluator = SelfEvaluator()
        with pytest.raises(ValueError, match="tenant_id"):
            evaluator.assess_risk({"dag": {"nodes": [], "edges": []}}, tenant_id="")


class TestEvaluationListing:
    def test_list_evaluations_scoped_by_tenant(self):
        evaluator = SelfEvaluator()
        evaluator.assess_risk({"dag": {"nodes": [{"id": "a", "tool": "t"}], "edges": []}}, "tenant-a")
        evaluator.assess_risk({"dag": {"nodes": [{"id": "b", "tool": "t"}], "edges": []}}, "tenant-b")
        a_list = evaluator.list_evaluations(tenant_id="tenant-a")
        b_list = evaluator.list_evaluations(tenant_id="tenant-b")
        assert len(a_list) == 1
        assert len(b_list) == 1

    def test_risk_score_hard_bound_no_bypass(self):
        evaluator = SelfEvaluator()
        nodes = [{"id": f"n{i}", "tool": f"t{i}"} for i in range(50)]
        edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(49)]
        plan = {"dag": {"nodes": nodes, "edges": edges}}
        risk = evaluator.assess_risk(plan, tenant_id="t1")
        # LAW-14: overall_score caps at 0.95
        assert risk.overall_score <= 0.95
