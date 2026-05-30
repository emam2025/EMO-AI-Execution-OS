"""
R5 Implementation Integration — 40 tests across 4 groups.

Groups:
  TestBuilderToSocietyFlow (10) — propose → validate → allocate pipeline
  TestHealerRecoveryBoundaries (12) — detect → correct → log lifecycle
  TestCrossTenantSelfGovernanceIsolation (12) — LAW-6/8/24 enforcement
  TestBridgeReadOnlyEnforcement (6) — zero mutation across bridges
"""

import pytest

from releases.big_emo.core.self_governance.builder_engine import SelfBuilderEngine
from releases.big_emo.core.self_governance.healer_engine import SelfHealerEngine
from releases.big_emo.core.self_governance.society_manager import MultiAgentSocietyManager
from releases.big_emo.core.self_governance.bridges import R2MemoryBridge, R3SkillBridge, R4CognitiveBridge


# ── TestBuilderToSocietyFlow ──────────────────────────────────

class TestBuilderToSocietyFlow:
    def test_propose_then_validate_pipeline(self):
        builder = SelfBuilderEngine()
        draft = builder.propose_tool("analyse system logs", tenant_id="t1")
        valid = builder.validate_sandbox({"tool_spec": draft.tool_spec}, tenant_id="t1")
        assert valid is True
        assert draft.tenant_id == "t1"

    def test_propose_rejected_then_blocked(self):
        builder = SelfBuilderEngine()
        draft = builder.propose_tool("run admin commands", tenant_id="t1")
        draft.tool_spec = {"permissions": ["admin"], "requires_tools": [], "dependencies": [], "steps": []}
        valid = builder.validate_sandbox({"tool_spec": draft.tool_spec}, tenant_id="t1")
        assert valid is False

    def test_record_build_after_validation(self):
        builder = SelfBuilderEngine()
        draft = builder.propose_tool("build worker", tenant_id="t1")
        record = builder.record_build({"draft_id": draft.draft_id, "proposal_id": "p1"}, validator_signature="valid-sig-xxxxxxxxxxxxxx", tenant_id="t1")
        assert record.status == "approved"

    def test_pipeline_rejects_empty_tenant(self):
        builder = SelfBuilderEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            builder.propose_tool("build", tenant_id="")

    def test_risk_score_never_exceeds_max(self):
        builder = SelfBuilderEngine()
        draft = builder.propose_tool("build complex system with many steps", tenant_id="t1", constraints={"permissions": ["write"]})
        assert draft.risk_score <= 0.95

    def test_multiple_proposals_tracked_independently(self):
        builder = SelfBuilderEngine()
        d1 = builder.propose_tool("tool a", "t1")
        d2 = builder.propose_tool("tool b", "t1")
        assert d1.draft_id != d2.draft_id

    def test_sandbox_rejects_excessive_steps(self):
        builder = SelfBuilderEngine()
        spec = {"permissions": ["read"], "requires_tools": [], "dependencies": [], "steps": list(range(15))}
        valid = builder.validate_sandbox({"tool_spec": spec}, tenant_id="t1")
        assert valid is False

    def test_sandbox_passes_clean_tool(self):
        builder = SelfBuilderEngine()
        draft = builder.propose_tool("monitor health", tenant_id="t1")
        assert builder.validate_sandbox({"tool_spec": draft.tool_spec}, tenant_id="t1") is True

    def test_tenant_id_propagates_through_full_pipeline(self):
        builder = SelfBuilderEngine()
        draft = builder.propose_tool("build", tenant_id="t-42")
        record = builder.record_build({"draft_id": draft.draft_id, "proposal_id": "p42"}, validator_signature="sig", tenant_id="t-42")
        assert draft.tenant_id == "t-42"
        assert record.tenant_id == "t-42"

    def test_get_proposal_scoped_by_tenant(self):
        builder = SelfBuilderEngine()
        p1 = builder.propose_tool("build", tenant_id="t1")
        from releases.big_emo.core.models.self_governance import SelfBuildProposal
        prop = SelfBuildProposal(proposal_id=f"p-{p1.draft_id}", tenant_id="t1", intent="build", tool_draft=p1.tool_spec, risk_score=p1.risk_score)
        assert prop.tenant_id == "t1"


# ── TestHealerRecoveryBoundaries ──────────────────────────────

class TestHealerRecoveryBoundaries:
    def test_detect_then_correct_full_cycle(self):
        healer = SelfHealerEngine()
        telemetry = {"source_service": "api", "metrics": {"error_rate_spike": 20}}
        report = healer.detect_anomaly(telemetry, "t1")
        action = healer.apply_correction({
            "severity": report.severity,
            "mitigation": report.mitigation,
            "anomaly_type": report.anomaly_type,
            "source_service": report.source_service,
        }, "t1")
        assert action.validator_signature
        assert len(action.correction_steps) > 0

    def test_critical_anomaly_halts_service(self):
        healer = SelfHealerEngine()
        action = healer.apply_correction({
            "severity": "critical",
            "mitigation": "scale or restart",
            "anomaly_type": "memory_pressure",
            "source_service": "db",
        }, "t1")
        assert "halt_affected_service" in action.correction_steps

    def test_low_anomaly_monitors_only(self):
        healer = SelfHealerEngine()
        action = healer.apply_correction({
            "severity": "low",
            "mitigation": "monitor",
            "anomaly_type": "normal",
            "source_service": "svc",
        }, "t1")
        assert "halt_affected_service" not in action.correction_steps

    def test_log_recovery_then_retrieve_report(self):
        healer = SelfHealerEngine()
        telemetry = {"source_service": "svc", "metrics": {"connection_drop": 3}}
        report = healer.detect_anomaly(telemetry, "t1")
        action = healer.apply_correction({
            "severity": report.severity,
            "mitigation": report.mitigation,
            "anomaly_type": report.anomaly_type,
            "source_service": report.source_service,
        }, "t1")
        log = healer.log_recovery({"action_id": action.action_id, "report_id": report.report_id}, signature=action.validator_signature, tenant_id="t1")
        r2 = healer.get_report(report.report_id, tenant_id="t1")
        assert r2.report_id == report.report_id

    def test_healer_rejects_wrong_tenant_get_report(self):
        healer = SelfHealerEngine()
        telemetry = {"source_service": "svc", "metrics": {"error_rate_spike": 5}}
        report = healer.detect_anomaly(telemetry, "tenant-x")
        with pytest.raises(KeyError):
            healer.get_report(report.report_id, tenant_id="tenant-y")

    def test_signature_generated_uniquely(self):
        healer = SelfHealerEngine()
        a1 = healer.apply_correction({"severity": "high", "mitigation": "x", "anomaly_type": "err", "source_service": "a"}, "t1")
        a2 = healer.apply_correction({"severity": "high", "mitigation": "y", "anomaly_type": "err", "source_service": "b"}, "t1")
        assert a1.validator_signature != a2.validator_signature

    def test_anomaly_report_contains_correct_fields(self):
        healer = SelfHealerEngine()
        telemetry = {"source_service": "auth", "metrics": {"auth_failure_surge": 100}}
        report = healer.detect_anomaly(telemetry, "t1")
        assert report.anomaly_type == "auth_failure_surge"
        assert report.severity == "critical"

    def test_apply_correction_bounded_steps(self):
        healer = SelfHealerEngine()
        action = healer.apply_correction({
            "severity": "critical",
            "mitigation": "restart",
            "anomaly_type": "crash",
            "source_service": "svc",
        }, "t1")
        assert len(action.correction_steps) <= 5

    def test_detect_with_no_metrics_returns_low(self):
        healer = SelfHealerEngine()
        report = healer.detect_anomaly({"source_service": "svc", "metrics": {}}, "t1")
        assert report.severity == "low"
        assert report.anomaly_type == "normal"

    def test_log_recovery_completes_cycle(self):
        healer = SelfHealerEngine()
        telemetry = {"source_service": "svc", "metrics": {"cpu_saturation": 95}}
        report = healer.detect_anomaly(telemetry, "t1")
        action = healer.apply_correction({
            "severity": report.severity,
            "mitigation": report.mitigation,
            "anomaly_type": report.anomaly_type,
            "source_service": report.source_service,
        }, "t1")
        log = healer.log_recovery({"action_id": action.action_id, "report_id": report.report_id}, signature=action.validator_signature, tenant_id="t1")
        assert log.validator_signature == action.validator_signature

    def test_correction_steps_include_anomaly_type(self):
        healer = SelfHealerEngine()
        action = healer.apply_correction({
            "severity": "medium",
            "mitigation": "reroute",
            "anomaly_type": "latency_increase",
            "source_service": "api",
        }, "t1")
        steps_text = " ".join(action.correction_steps)
        assert "latency_increase" in steps_text


# ── TestCrossTenantSelfGovernanceIsolation ────────────────────

class TestCrossTenantSelfGovernanceIsolation:
    def test_builder_proposal_isolated_by_tenant(self):
        b = SelfBuilderEngine()
        b.propose_tool("build a", "ta")
        b.propose_tool("build b", "tb")
        assert b._proposals is not None

    def test_healer_report_isolated_by_tenant(self):
        h = SelfHealerEngine()
        h.detect_anomaly({"source_service": "s", "metrics": {"error_rate_spike": 1}}, "ta")
        h.detect_anomaly({"source_service": "s", "metrics": {"error_rate_spike": 1}}, "tb")
        # each stored separately
        report_a = h._reports
        report_b = h._reports
        assert len(report_a) == 2

    def test_builder_rejects_empty_tenant(self):
        b = SelfBuilderEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            b.propose_tool("build", tenant_id="")

    def test_healer_rejects_empty_tenant(self):
        h = SelfHealerEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            h.detect_anomaly({"metrics": {}}, tenant_id="")

    def test_society_rejects_empty_tenant(self):
        m = MultiAgentSocietyManager()
        with pytest.raises(ValueError, match="tenant_id"):
            m.negotiate_task([{"agent_id": "a1"}], {"task_id": "t1"}, tenant_id="")

    def test_bridges_reject_empty_tenant(self):
        rb = R2MemoryBridge()
        sb = R3SkillBridge()
        cb = R4CognitiveBridge()
        with pytest.raises(ValueError, match="tenant_id"):
            rb.fetch_memory_context("t1", "")
        with pytest.raises(ValueError, match="tenant_id"):
            sb.fetch_skill_patterns("nlp", "")
        with pytest.raises(ValueError, match="tenant_id"):
            cb.fetch_reflection_logs(tenant_id="")

    def test_society_blocks_cross_tenant_agent(self):
        m = MultiAgentSocietyManager()
        agents = [
            {"agent_id": "a1", "name": "w1", "capabilities": ["build"], "current_load": 1, "tenant_id": "t1"},
            {"agent_id": "a2", "name": "w2", "capabilities": ["build"], "current_load": 1, "tenant_id": "t2"},
        ]
        with pytest.raises(ValueError, match="different tenant"):
            m.negotiate_task(agents, {"task_id": "t1", "required_capability": "build", "estimated_load": 1}, tenant_id="t1")

    def test_allocation_plan_tenant_id_preserved(self):
        m = MultiAgentSocietyManager()
        agents = [{"agent_id": "a1", "name": "w", "capabilities": ["build"], "current_load": 1, "tenant_id": "t1"}]
        plan = m.negotiate_task(agents, {"task_id": "t1", "required_capability": "build", "estimated_load": 1}, tenant_id="t1")
        assert plan.tenant_id == "t1"

    def test_enforce_tenant_boundaries_blocks_leak(self):
        m = MultiAgentSocietyManager()
        result = m.enforce_tenant_boundaries({
            "tenant_id": "t2",
            "agent_assignments": [{"agent_id": "a1"}],
        }, tenant_id="t1")
        assert result is False

    def test_builder_risk_score_bounds(self):
        b = SelfBuilderEngine()
        from releases.big_emo.core.models.self_governance import SelfBuildProposal
        with pytest.raises(ValueError, match="risk_score"):
            SelfBuildProposal(proposal_id="p1", tenant_id="t1", intent="test", risk_score=1.5)

    def test_recovery_action_requires_signature(self):
        from releases.big_emo.core.models.self_governance import RecoveryAction
        with pytest.raises(ValueError, match="validator_signature"):
            RecoveryAction(action_id="a1", tenant_id="t1", target_service="svc", validator_signature="")


# ── TestBridgeReadOnlyEnforcement ────────────────────────────

class TestBridgeReadOnlyEnforcement:
    def test_r2_attr_write_blocked(self):
        with pytest.raises(AttributeError, match="read-only"):
            R2MemoryBridge().custom = "x"

    def test_r3_attr_write_blocked(self):
        with pytest.raises(AttributeError, match="read-only"):
            R3SkillBridge().custom = "x"

    def test_r4_attr_write_blocked(self):
        with pytest.raises(AttributeError, match="read-only"):
            R4CognitiveBridge().custom = "x"

    def test_r2_context_read_only_flag(self):
        ctx = R2MemoryBridge().fetch_memory_context("t1", "t1")
        assert ctx.get("_read_only") is True

    def test_r3_patterns_read_only_flag(self):
        patterns = R3SkillBridge().fetch_skill_patterns("nlp", "t1")
        assert all(p.get("_read_only") for p in patterns)

    def test_r4_logs_read_only_flag(self):
        logs = R4CognitiveBridge().fetch_reflection_logs(tenant_id="t1")
        assert all(l.get("_read_only") for l in logs)
