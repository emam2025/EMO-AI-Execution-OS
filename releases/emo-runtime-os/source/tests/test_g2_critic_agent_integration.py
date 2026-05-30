"""Phase G2 — Critic Agent Integration Tests.  # RULE-3 LAW-12 LAW-20-22

Tests the complete G2 Critic Agent subsystem:
  1. TestDiagnosisAccuracy — failure diagnosis accuracy
  2. TestCorrectionGuardEnforcement — RULE 3 guard enforcement
  3. TestTraceCorrelation — LAW 12 traceability
  4. TestFailureMatrixIntegration — LAW 20-22 failure propagation
  5. TestEventBusPropagation — EventBus emissions

Tests are pure (no external state, no shared globals).

Ref: Canon LAW 7, LAW 8, LAW 12, LAW 20-22, RULE 1, RULE 3
Ref: artifacts/design/g2/protocols/01_critic_protocols.py
Ref: artifacts/design/g2/models/02_diagnosis_and_review_models.py
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pytest

from core.runtime.models.critic_models import (
    CorrectionGuardResult,
    CorrectionPayload,
    CorrectionType,
    DiagnosisReport,
    FailureSignature,
    RuntimeReviewSnapshot,
    ReviewSignal,
    SeverityLevel,
)
from core.runtime.critic.critic_agent import CriticAgent
from core.runtime.critic.failure_diagnoser import FailureDiagnoser
from core.runtime.critic.plan_correction_engine import PlanCorrectionEngine
from core.runtime.critic.runtime_reviewer import RuntimeReviewer
from core.runtime.critic.diagnosis_state_machine import DiagnosisStateMachine
from core.runtime.critic.trace_correlator import CriticTraceCorrelator


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def event_bus():
    """Simple in-memory event bus for testing."""
    class FakeEventBus:
        def __init__(self):
            self.events: List[Dict[str, Any]] = []

        def publish(self, topic: str, payload: Dict[str, Any]) -> None:
            self.events.append({"topic": topic, "payload": payload, "timestamp": time.time()})

    return FakeEventBus()


@pytest.fixture
def critic(event_bus):
    diagnoser = FailureDiagnoser()
    diagnoser.register_signature(FailureSignature(
        signature_id="sig_timeout",
        label="Connection timeout detected",
        error_type="timeout",
        stack_pattern="ConnectionError|TimeoutError",
        severity=SeverityLevel.ERROR,
        category="network",
    ))
    diagnoser.register_signature(FailureSignature(
        signature_id="sig_oom",
        label="Out of memory",
        error_type="oom",
        stack_pattern="MemoryError|OOM",
        severity=SeverityLevel.CRITICAL,
        category="resource",
    ))

    return CriticAgent(
        failure_diagnoser=diagnoser,
        correction_engine=PlanCorrectionEngine(),
        runtime_reviewer=RuntimeReviewer(),
        state_machine=DiagnosisStateMachine(),
        trace_correlator=CriticTraceCorrelator(),
        event_bus=event_bus,
        strict_critic_mode=True,
    )


# ═══════════════════════════════════════════════════════════════
# 1. TestDiagnosisAccuracy
# ═══════════════════════════════════════════════════════════════


class TestDiagnosisAccuracy:
    """G2-G1: Failure diagnosis accuracy tests."""

    def test_diagnose_timeout_error(self, critic):
        trace = {"error_type": "timeout", "stack_pattern": "ConnectionError to host"}
        result = critic.diagnose_failure("plan_t1", trace)
        assert result["plan_id"] == "plan_t1"
        assert result["critic_trace_id"]
        assert result["root_cause"]
        assert result["confidence_score"] >= 0.0
        assert result["severity_level"]

    def test_diagnose_oom_error(self, critic):
        trace = {"error_type": "oom", "stack_pattern": "MemoryError: cannot allocate"}
        result = critic.diagnose_failure("plan_oom", trace)
        assert result["root_cause"]
        assert result["confidence_score"] >= 0.0

    def test_diagnose_unknown_pattern(self, critic):
        trace = {"error_type": "unknown", "stack_pattern": "weird error"}
        result = critic.diagnose_failure("plan_unknown", trace)
        assert result["root_cause"]

    def test_diagnose_empty_trace_raises(self, critic):
        with pytest.raises(RuntimeError, match="Guard blocked"):
            critic.diagnose_failure("plan_empty", {})

    def test_diagnose_partial_trace_raises(self, critic):
        with pytest.raises(RuntimeError, match="Guard blocked"):
            critic.diagnose_failure("plan_partial", {"irrelevant": 1})


# ═══════════════════════════════════════════════════════════════
# 2. TestCorrectionGuardEnforcement
# ═══════════════════════════════════════════════════════════════


class TestCorrectionGuardEnforcement:
    """G2-G2: Correction guard enforcement (RULE 3)."""

    def test_propose_correction_guarded(self, critic):
        trace = {
            "error_type": "timeout",
            "stack_pattern": "ConnectionError",
            "nodes": [
                {"node_id": "n1", "timestamp": 1, "status": "error"},
                {"node_id": "n2", "timestamp": 2, "status": "timeout"},
                {"node_id": "n3", "timestamp": 3, "status": "error"},
            ],
        }
        diagnosis = critic.diagnose_failure("plan_c1", trace)
        payload = critic.propose_correction("plan_c1", diagnosis)
        assert payload["rollback_safe"] is True
        assert payload["patch_type"] == "semantic_fix"
        assert payload["critic_trace_id"]

    def test_propose_correction_no_signals_rejected(self, critic):
        diag = DiagnosisReport(
            plan_id="plan_no_signal",
            critic_trace_id="test_trace",
            evidence_chain=[],
            confidence_score=0.9,
            severity_level=SeverityLevel.ERROR,
        )
        with pytest.raises(RuntimeError, match="Correction guard rejected"):
            critic.propose_correction("plan_no_signal", {
                "plan_id": diag.plan_id,
                "critic_trace_id": diag.critic_trace_id,
                "evidence_chain": [],
                "confidence_score": 0.9,
                "severity_level": "error",
                "root_cause": "test",
                "root_cause_node": "n1",
                "correction_suggestion": "fix",
                "failure_trace": {},
                "matched_signature_id": "",
                "timestamp_ns": 0,
                "metadata": {},
            })

    def test_propose_correction_low_confidence_rejected(self, critic):
        diag = DiagnosisReport(
            plan_id="plan_low_conf",
            critic_trace_id="test_trace",
            evidence_chain=[{"n": "1"}],
            confidence_score=0.5,
            severity_level=SeverityLevel.WARNING,
        )
        with pytest.raises(RuntimeError, match="Correction guard rejected"):
            critic.propose_correction("plan_low_conf", {
                "plan_id": diag.plan_id,
                "critic_trace_id": diag.critic_trace_id,
                "evidence_chain": [{"n": "1"}],
                "confidence_score": 0.5,
                "severity_level": "warning",
                "root_cause": "test",
                "root_cause_node": "n1",
                "correction_suggestion": "fix",
                "failure_trace": {},
                "matched_signature_id": "",
                "timestamp_ns": 0,
                "metadata": {},
            })

    def test_propose_correction_with_critic_trace_id(self, critic):
        trace = {
            "error_type": "oom",
            "stack_pattern": "MemoryError",
            "nodes": [
                {"node_id": "n1", "timestamp": 1, "status": "error"},
                {"node_id": "n2", "timestamp": 2, "status": "oom"},
                {"node_id": "n3", "timestamp": 3, "status": "error"},
            ],
        }
        diagnosis = critic.diagnose_failure("plan_ctid", trace)
        payload = critic.propose_correction("plan_ctid", diagnosis)
        assert payload["critic_trace_id"] == diagnosis["critic_trace_id"]


# ═══════════════════════════════════════════════════════════════
# 3. TestTraceCorrelation
# ═══════════════════════════════════════════════════════════════


class TestTraceCorrelation:
    """G2-G3: critic_trace_id propagation (LAW 12)."""

    def test_diagnosis_has_critic_trace_id(self, critic):
        trace = {"error_type": "timeout", "stack_pattern": "ConnectionError"}
        result = critic.diagnose_failure("plan_tc1", trace)
        assert result["critic_trace_id"]
        assert result["critic_trace_id"].startswith("critic_")

    def test_correction_has_critic_trace_id(self, critic):
        trace = {
            "error_type": "timeout",
            "stack_pattern": "ConnectionError",
            "nodes": [
                {"node_id": "n1", "timestamp": 1, "status": "error"},
                {"node_id": "n2", "timestamp": 2, "status": "timeout"},
                {"node_id": "n3", "timestamp": 3, "status": "error"},
            ],
        }
        diagnosis = critic.diagnose_failure("plan_tc2", trace)
        payload = critic.propose_correction("plan_tc2", diagnosis)
        assert payload["critic_trace_id"]

    def test_critic_trace_id_matches_across_diagnose_and_correct(self, critic):
        trace = {
            "error_type": "timeout",
            "stack_pattern": "ConnectionError",
            "nodes": [
                {"node_id": "n1", "timestamp": 1, "status": "error"},
                {"node_id": "n2", "timestamp": 2, "status": "timeout"},
                {"node_id": "n3", "timestamp": 3, "status": "error"},
            ],
        }
        diagnosis = critic.diagnose_failure("plan_tc3", trace)
        payload = critic.propose_correction("plan_tc3", diagnosis)
        assert payload["critic_trace_id"] == diagnosis["critic_trace_id"]

    def test_correlator_records_all_layers(self, critic):
        trace = {"error_type": "timeout", "stack_pattern": "Error"}
        diag = critic.diagnose_failure("plan_tc4", trace)
        tid = diag["critic_trace_id"]
        critic.trace_correlator.propagate_to_g1("plan_tc4", tid)
        critic.trace_correlator.propagate_to_d9("plan_tc4", tid)
        critic.trace_correlator.propagate_to_f4("plan_tc4", tid)
        chain = critic.trace_correlator.trace_chain(tid)
        assert chain


# ═══════════════════════════════════════════════════════════════
# 4. TestFailureMatrixIntegration
# ═══════════════════════════════════════════════════════════════


class TestFailureMatrixIntegration:
    """G2-G4: FailureMatrix integration (LAW 20-22)."""

    def test_event_bus_emits_diagnosis_completed(self, critic, event_bus):
        trace = {"error_type": "timeout", "stack_pattern": "ConnectionError"}
        critic.diagnose_failure("plan_fm1", trace)
        topics = [e["topic"] for e in event_bus.events]
        assert "critic.diagnosis.completed" in topics

    def test_event_bus_emits_correction_proposed(self, critic, event_bus):
        trace = {
            "error_type": "timeout",
            "stack_pattern": "ConnectionError",
            "nodes": [
                {"node_id": "n1", "timestamp": 1, "status": "error"},
                {"node_id": "n2", "timestamp": 2, "status": "timeout"},
                {"node_id": "n3", "timestamp": 3, "status": "error"},
            ],
        }
        diag = critic.diagnose_failure("plan_fm2", trace)
        critic.propose_correction("plan_fm2", diag)
        topics = [e["topic"] for e in event_bus.events]
        assert "critic.correction.proposed" in topics

    def test_event_bus_emits_runtime_reviewed(self, critic, event_bus):
        critic.evaluate_runtime({
            "plan_ids": ["p1"],
            "execution_trace": [{"node_id": "n1", "duration_ms": 500}],
            "worker_snapshots": [{"worker_id": "w1", "memory_bytes": 100}],
            "determinism_hash": "abc",
            "actual_hash": "abc",
        })
        topics = [e["topic"] for e in event_bus.events]
        assert "critic.runtime.reviewed" in topics

    def test_escalation_triggered_on_severity_critical(self, critic, event_bus):
        trace = {"error_type": "oom", "stack_pattern": "MemoryError"}
        diag = critic.diagnose_failure("plan_fm4", trace)
        critic.publish_assessment("plan_fm4", {
            "severity_level": "critical",
            "critic_trace_id": diag["critic_trace_id"],
        })
        topics = [e["topic"] for e in event_bus.events]
        assert "critic.escalation.triggered" in topics


# ═══════════════════════════════════════════════════════════════
# 5. TestEventBusPropagation
# ═══════════════════════════════════════════════════════════════


class TestEventBusPropagation:
    """G2-G5: EventBus emission correctness."""

    def test_event_payload_contains_plan_id(self, critic, event_bus):
        trace = {"error_type": "timeout", "stack_pattern": "ConnectionError"}
        critic.diagnose_failure("plan_eb1", trace)
        diag_events = [e for e in event_bus.events if e["topic"] == "critic.diagnosis.completed"]
        assert diag_events
        assert diag_events[0]["payload"]["plan_id"] == "plan_eb1"

    def test_event_payload_contains_critic_trace_id(self, critic, event_bus):
        trace = {"error_type": "timeout", "stack_pattern": "ConnectionError"}
        diag = critic.diagnose_failure("plan_eb2", trace)
        events = [e for e in event_bus.events if e["topic"] == "critic.diagnosis.completed"]
        assert events
        assert events[0]["payload"]["critic_trace_id"] == diag["critic_trace_id"]

    def test_runtime_review_determinism_violation_emits_drift(self, critic, event_bus):
        critic.evaluate_runtime({
            "plan_ids": ["p1"],
            "execution_trace": [{"node_id": "n1", "duration_ms": 100}],
            "worker_snapshots": [],
            "determinism_hash": "abc",
            "actual_hash": "def",
        })
        topics = [e["topic"] for e in event_bus.events]
        assert "critic.drift.detected" in topics or "critic.runtime.reviewed" in topics


# ═══════════════════════════════════════════════════════════════
# 6. Edge Cases & Component Tests
# ═══════════════════════════════════════════════════════════════


class TestFailureDiagnoser:
    """IFailureDiagnoser component tests."""

    def test_analyze_error_pattern_match(self):
        fd = FailureDiagnoser()
        fd.register_signature(FailureSignature(
            signature_id="s1", stack_pattern="Timeout", category="network"
        ))
        result = fd.analyze_error_pattern(
            {"error_type": "timeout", "stack_pattern": "TimeoutError occurred"},
        )
        assert result["matched_pattern_id"] == "s1"
        assert result["match_confidence"] > 0.0

    def test_analyze_error_pattern_no_match(self):
        fd = FailureDiagnoser()
        result = fd.analyze_error_pattern(
            {"error_type": "ok", "stack_pattern": "all good"},
        )
        assert result["matched_pattern_id"] == ""

    def test_rate_confidence_empty(self):
        fd = FailureDiagnoser()
        assert fd.rate_confidence([]) == 0.0

    def test_rate_confidence_with_evidence(self):
        fd = FailureDiagnoser()
        evidence = [{"n": "1"}, {"n": "2"}, {"n": "3"}]
        assert fd.rate_confidence(evidence) > 0.0

    def test_diagnose_convenience(self):
        fd = FailureDiagnoser()
        report = fd.diagnose("p1", {"error_type": "err", "stack_pattern": "Error"})
        assert isinstance(report, DiagnosisReport)
        assert report.plan_id == "p1"


class TestPlanCorrectionEngine:
    """IPlanCorrectionEngine component tests."""

    def test_apply_semantic_fix(self):
        engine = PlanCorrectionEngine()
        plan = {"nodes": [{"node_id": "n1", "tool_params": {"x": 1}}]}
        correction = {"affected_nodes": ["n1"], "parameters": {"x": 2}}
        result = engine.apply_semantic_fix(plan, correction)
        assert result["nodes"][0]["tool_params"]["x"] == 2

    def test_adjust_topology_reorder(self):
        engine = PlanCorrectionEngine()
        dag = [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}]
        result = engine.adjust_topology(dag, ["n2"], "reorder")
        assert len(result) == 1

    def test_validate_constraint_compliance(self):
        engine = PlanCorrectionEngine()
        plan = {"nodes": [{"node_id": "n1"}], "dag_topology": [{"from": "n1", "to": "n2"}], "correction_count": 1}
        assert not engine.validate_constraint_compliance(plan)

    def test_estimate_impact(self):
        engine = PlanCorrectionEngine()
        impact = engine.estimate_impact("p1", {"affected_nodes": ["n1"], "estimated_risk": 0.3})
        assert impact["affected_node_count"] == 1
        assert "risk_score" in impact


class TestRuntimeReviewer:
    """IRuntimeReviewer component tests."""

    def test_observe_execution_latency(self):
        reviewer = RuntimeReviewer()
        trace = [
            {"node_id": "n1", "duration_ms": 100},
            {"node_id": "n2", "duration_ms": 2000},
        ]
        result = reviewer.observe_execution_latency(trace, threshold_ms=1500)
        assert result["max_latency"] == 2000
        assert result["threshold_breached"]
        assert result["slowest_node"] == "n2"

    def test_observe_execution_latency_empty(self):
        reviewer = RuntimeReviewer()
        result = reviewer.observe_execution_latency([])
        assert result["max_latency"] == 0.0

    def test_detect_resource_leak(self):
        reviewer = RuntimeReviewer()
        snapshots = [
            {"worker_id": "w1", "memory_bytes": 100},
            {"worker_id": "w1", "memory_bytes": 200},
        ]
        result = reviewer.detect_resource_leak(snapshots, threshold_delta=0.15)
        assert result["leak_detected"]
        assert result["delta_percent"] > 0

    def test_detect_resource_leak_no_leak(self):
        reviewer = RuntimeReviewer()
        snapshots = [
            {"worker_id": "w1", "memory_bytes": 100},
            {"worker_id": "w1", "memory_bytes": 105},
        ]
        result = reviewer.detect_resource_leak(snapshots, threshold_delta=0.15)
        assert not result["leak_detected"]

    def test_flag_determinism_violation(self):
        reviewer = RuntimeReviewer()
        result = reviewer.flag_determinism_violation("abc", "def", {"worker_id": "w1"})
        assert result["violation_detected"]
        assert result["hash_mismatch"] == "def"

    def test_suggest_optimization(self):
        reviewer = RuntimeReviewer()
        plan = {}
        trace = [{"node_id": "slow", "duration_ms": 1000}]
        suggestions = reviewer.suggest_optimization(plan, trace)
        assert len(suggestions) >= 1
        assert suggestions[0]["suggestion_type"] == "optimize_node"

    def test_review_snapshot(self):
        reviewer = RuntimeReviewer()
        ctx = {
            "plan_ids": ["p1"],
            "execution_trace": [{"node_id": "n1", "duration_ms": 100}],
            "worker_snapshots": [],
            "determinism_hash": "abc",
            "actual_hash": "abc",
        }
        snapshot = reviewer.review(ctx, "critic_test")
        assert isinstance(snapshot, RuntimeReviewSnapshot)
        assert snapshot.critic_trace_id == "critic_test"


class TestCriticAgentEdgeCases:
    """CriticAgent edge cases."""

    def test_reset(self, critic):
        trace = {"error_type": "timeout", "stack_pattern": "ConnectionError"}
        critic.diagnose_failure("plan_reset", trace)
        critic.reset()
        assert critic.state_machine.current.value == "failure_observed"

    def test_diagnose_multiple_plans(self, critic):
        t1 = critic.diagnose_failure("p1", {
            "error_type": "timeout",
            "stack_pattern": "Error",
            "nodes": [{"node_id": "n1", "timestamp": 1, "status": "error"}],
        })
        t2 = critic.diagnose_failure("p2", {
            "error_type": "oom",
            "stack_pattern": "MemoryError",
            "nodes": [{"node_id": "n2", "timestamp": 1, "status": "oom"}],
        })
        assert t1["plan_id"] != t2["plan_id"]
        assert t1["critic_trace_id"] != t2["critic_trace_id"]

    def test_evaluate_runtime_no_trace(self, critic):
        result = critic.evaluate_runtime({
            "plan_ids": [],
            "execution_trace": [],
            "worker_snapshots": [],
            "determinism_hash": "",
            "actual_hash": "",
        })
        assert result["signal"] == "approve"
        assert result["max_latency_ms"] == 0.0

    def test_publish_assessment_no_escalation(self, critic):
        critic.publish_assessment("plan_safe", {
            "severity_level": "info",
            "critic_trace_id": "test_trace",
        })
        assert critic.state_machine.current.value != "escalate"
