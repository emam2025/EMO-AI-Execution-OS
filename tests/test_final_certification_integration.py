"""Phase FINAL — Production Readiness & Certification Integration Tests.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-10 LAW-11 LAW-12 LAW-13 LAW-14 LAW-15 LAW-20 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Integration tests for SystemAuditor, LoadGenerator, SecurityValidator,
CertificationEngine, and CertificationStateMachine.

GROUP: TestCanonComplianceEnforcement (5 tests)
GROUP: TestLoadStabilityUnderPressure (4 tests)
GROUP: TestSecurityIsolationValidation (4 tests)
GROUP: TestTraceIntegrityAcrossLayers (4 tests)
GROUP: TestCertificateGeneration (3 tests)

Ref: DEVELOPER.md §15.13, §16.1
Ref: Canon LAW 1-27, RULE 1-5
"""

from __future__ import annotations

import hashlib
import time

import pytest

from core.runtime.certification.system_auditor import SystemAuditor
from core.runtime.certification.load_generator import LoadGenerator
from core.runtime.certification.security_validator import SecurityValidator
from core.runtime.certification.certification_engine import CertificationEngine
from core.runtime.certification.certification_state_machine import (
    CertificationStateMachine,
    CertificationTransition,
)
from core.runtime.event_bus import InMemoryEventBus


TRACE_ID = "cert_integration_test_001"


# ── TestCanonComplianceEnforcement (5 tests) ───────────────────────────


class TestCanonComplianceEnforcement:
    """Test SystemAuditor compliance scanning and enforcement."""

    def test_full_canon_compliance_passes(self) -> None:
        auditor = SystemAuditor(strict_certification_mode=True)
        result = auditor.scan_canon_compliance({
            "laws": {f"LAW-{i}": True for i in range(1, 28)},
            "rules": {f"RULE-{i}": True for i in range(1, 6)},
        }, TRACE_ID)
        assert result["compliance_pct"] == 100.0
        assert result["violations"] == []
        assert "canonical_hash" in result

    def test_missing_compliance_reported(self) -> None:
        auditor = SystemAuditor(strict_certification_mode=True)
        result = auditor.scan_canon_compliance({
            "laws": {f"LAW-{i}": True for i in range(1, 28)},
            "rules": {"RULE-1": False, "RULE-2": True, "RULE-3": True},
        }, TRACE_ID)
        assert result["compliance_pct"] < 100.0
        assert len(result["violations"]) > 0

    def test_compliance_hash_deterministic(self) -> None:
        auditor = SystemAuditor(strict_certification_mode=True)
        ctx = {
            "laws": {f"LAW-{i}": True for i in range(1, 28)},
            "rules": {f"RULE-{i}": True for i in range(1, 6)},
        }
        r1 = auditor.scan_canon_compliance(ctx, TRACE_ID)
        auditor.reset_audit_records()
        r2 = auditor.scan_canon_compliance(ctx, TRACE_ID)
        assert r1["canonical_hash"] == r2["canonical_hash"]

    def test_architectural_debt_detects_circular_deps(self) -> None:
        auditor = SystemAuditor(strict_certification_mode=True)
        graph = {
            "nodes": {"A": {}, "B": {}, "C": {}},
            "edges": [("A", "B"), ("B", "C"), ("C", "A")],
        }
        result = auditor.detect_architectural_debt(graph, TRACE_ID)
        assert len(result["circular_deps"]) > 0
        assert result["debt_score"] > 0

    def test_dependency_verification_reports_violations(self) -> None:
        auditor = SystemAuditor(strict_certification_mode=True)
        deps = {
            "ComponentA": ["core.runtime.valid_dep"],
            "ComponentB": ["missing_dep"],
        }
        result = auditor.verify_dependencies(deps, TRACE_ID)
        assert result["verified"] is False
        assert result["violated_deps"] > 0
        assert len(result["isolation_violations"]) > 0


# ── TestLoadStabilityUnderPressure (4 tests) ───────────────────────────


class TestLoadStabilityUnderPressure:
    """Test LoadGenerator stability under concurrent load."""

    def test_100_concurrent_dags_no_failures(self) -> None:
        gen = LoadGenerator(strict_certification_mode=True)
        result = gen.simulate_concurrent_dags(
            dag_count=100,
            dag_template={"nodes": 10, "edges": 15, "base_runtime_ms": 10},
            certification_trace_id=TRACE_ID,
        )
        assert result["dags_executed"] == 100
        assert result["dags_failed"] == 0
        assert result["p99_latency_ms"] < 200.0

    def test_p99_latency_stays_below_threshold(self) -> None:
        gen = LoadGenerator(strict_certification_mode=True)
        result = gen.simulate_concurrent_dags(
            dag_count=50,
            dag_template={"nodes": 20, "edges": 30, "base_runtime_ms": 5},
            certification_trace_id=TRACE_ID,
        )
        assert result["p99_latency_ms"] < 200.0

    def test_resource_pressure_recovers(self) -> None:
        gen = LoadGenerator(strict_certification_mode=True)
        result = gen.apply_resource_pressure(
            cpu_percent=80.0,
            memory_mb=256,
            duration_sec=1.0,
            certification_trace_id=TRACE_ID,
        )
        assert result["pressure_ok"]
        assert result["recovery_time_ms"] > 0

    def test_oscillation_detected_with_spikes(self) -> None:
        gen = LoadGenerator(strict_certification_mode=True)
        samples = [50.0, 200.0, 50.0, 200.0, 50.0, 200.0, 50.0, 50.0, 50.0]
        result = gen.detect_oscillation(samples, TRACE_ID)
        assert result["oscillation_detected"] is True
        assert result["oscillation_score"] >= 0.3


# ── TestSecurityIsolationValidation (4 tests) ─────────────────────────


class TestSecurityIsolationValidation:
    """Test SecurityValidator isolation and capability checks."""

    def test_all_boundaries_secure(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        config = {
            "boundaries": {
                "runtime": {"isolated": True, "sandboxed": True},
                "data": {"isolated": True, "sandboxed": True},
                "network": {"isolated": True, "sandboxed": True},
            },
            "sandbox_active": True,
            "network_policy_enforced": True,
        }
        result = validator.check_isolation_boundaries(config, TRACE_ID)
        assert result["boundaries_secure"] is True
        assert result["secure_boundaries"] == 3

    def test_boundary_violation_detected(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        config = {
            "boundaries": {
                "runtime": {"isolated": False, "sandboxed": False},
            },
            "sandbox_active": False,
            "network_policy_enforced": False,
        }
        result = validator.check_isolation_boundaries(config, TRACE_ID)
        assert result["boundaries_secure"] is False
        assert len(result["violations"]) > 0

    def test_capability_guards_validated(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        inventory = {
            "capabilities": {
                "dag_execution": {"guard_active": True},
                "tool_synthesis": {"guard_active": True},
                "data_migration": {"guard_active": True},
            },
            "enforcement_level": "strict",
        }
        result = validator.validate_capability_guards(inventory, TRACE_ID)
        assert result["all_guards_active"] is True
        assert result["guarded_capabilities"] == 3

    def test_rollback_safety_verified(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        caps = {
            "components": {
                "deployer": {"rollback_available": True, "data_preservation": True},
                "migrator": {"rollback_available": True, "data_preservation": True},
            }
        }
        result = validator.verify_rollback_safety(caps, TRACE_ID)
        assert result["rollback_safe"] is True
        assert result["safe_components"] == 2


# ── TestTraceIntegrityAcrossLayers (4 tests) ──────────────────────────


class TestTraceIntegrityAcrossLayers:
    """Test trace integrity across all observability layers."""

    def test_trace_integrity_ok_with_complete_chain(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        chain = {
            "layers": {
                "i2_data": "dt_abc123",
                "i3_reliability": "rec_def456",
                "i1_infra": "infra_789",
                "f2_control": "cp_012",
                "f4_observability": "span_345",
            },
            "chain_order": ["i2_data", "i3_reliability", "i1_infra", "f2_control", "f4_observability"],
        }
        result = validator.audit_trace_integrity(chain, TRACE_ID)
        assert result["trace_integrity_ok"] is True
        assert result["gap_count"] == 0

    def test_missing_trace_link_detected(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        chain = {
            "layers": {
                "i2_data": "dt_abc",
                "i3_reliability": "missing",
                "i1_infra": "",
            },
            "chain_order": ["i2_data", "i3_reliability", "i1_infra"],
        }
        result = validator.audit_trace_integrity(chain, TRACE_ID)
        assert result["trace_integrity_ok"] is False
        assert result["gap_count"] >= 2

    def test_audit_records_generated_for_trace_checks(self) -> None:
        validator = SecurityValidator(strict_certification_mode=True)
        chain = {
            "layers": {"i2_data": "dt_abc", "i3_reliability": "missing"},
            "chain_order": ["i2_data", "i3_reliability"],
        }
        validator.audit_trace_integrity(chain, TRACE_ID)
        entries = validator.audit_entries
        trace_entries = [e for e in entries if "trace" in e.check_name.lower()]
        assert len(trace_entries) > 0

    def test_trace_audit_deterministic(self) -> None:
        v1 = SecurityValidator(strict_certification_mode=True)
        v2 = SecurityValidator(strict_certification_mode=True)
        chain = {
            "layers": {"i2_data": "dt_abc", "i3_reliability": "rec_def"},
            "chain_order": ["i2_data", "i3_reliability"],
        }
        r1 = v1.audit_trace_integrity(chain, TRACE_ID)
        r2 = v2.audit_trace_integrity(chain, "different_trace")
        assert r1["trace_integrity_ok"] == r2["trace_integrity_ok"]
        assert r1["gap_count"] == r2["gap_count"]


# ── TestCertificateGeneration (3 tests) ──────────────────────────────


class TestCertificateGeneration:
    """Test CertificationEngine certificate generation and baseline freeze."""

    def test_certificate_generated_when_all_conditions_met(self) -> None:
        engine = CertificationEngine(strict_certification_mode=True)
        evaluation = {
            "ready": True,
            "evaluations": {"compliance": True, "performance": True, "security": True},
            "blocked_by": [],
            "readiness_pct": 100.0,
        }
        stability = {
            "stability_score": 0.98,
            "p99_latency_score": 0.95,
            "throughput_score": 0.99,
            "oscillation_score": 0.98,
            "reliability_score": 1.0,
            "overall_grade": "A",
        }
        result = engine.generate_certificate(evaluation, stability, TRACE_ID)
        assert result["status"] == "certified"
        assert result["stability_grade"] == "A"
        assert result["certificate_id"].startswith("cert_")

    def test_certificate_denied_when_not_ready(self) -> None:
        engine = CertificationEngine(strict_certification_mode=True)
        evaluation = {
            "ready": False,
            "evaluations": {"compliance": False, "performance": False, "security": False},
            "blocked_by": ["compliance", "performance", "security"],
            "readiness_pct": 50.0,
        }
        stability = {
            "stability_score": 0.5,
            "p99_latency_score": 0.3,
            "throughput_score": 0.4,
            "oscillation_score": 0.5,
            "reliability_score": 0.6,
            "overall_grade": "F",
        }
        result = engine.generate_certificate(evaluation, stability, TRACE_ID)
        assert result["status"] == "denied"
        assert len(result["conditions"]) > 0

    def test_baseline_freeze_creates_rollback_path(self) -> None:
        engine = CertificationEngine(strict_certification_mode=True)
        baseline_data = {
            "version": "4.5.0-prod-ready",
            "data_points": {
                "compliance_pct": 100,
                "p99_latency_ms": 45,
                "stability_score": 0.97,
            },
        }
        result = engine.freeze_baseline(baseline_data, TRACE_ID)
        assert result["baseline_id"].startswith("bl_")
        assert result["baseline_hash"] != ""
        assert result["rollback_available"] is True
        assert result["data_points_frozen"] == 3

        # Verify it was stored
        baseline = engine.get_baseline(result["baseline_id"])
        assert baseline is not None
        assert baseline.version == "4.5.0-prod-ready"

    def test_full_certification_pipeline_via_event_bus(self) -> None:
        """Integration of all 4 components in a certification pipeline."""
        bus = InMemoryEventBus()
        auditor = SystemAuditor(strict_certification_mode=True)
        generator = LoadGenerator(strict_certification_mode=True)
        validator = SecurityValidator(strict_certification_mode=True)
        engine = CertificationEngine(strict_certification_mode=True, event_bus=bus)

        trace_id = f"pipeline_{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]}"

        # Step 1: Audit
        audit_result = auditor.scan_canon_compliance({
            "laws": {f"LAW-{i}": True for i in range(1, 28)},
            "rules": {f"RULE-{i}": True for i in range(1, 6)},
        }, trace_id)
        # Include dependency verification in audit results
        deps_result = auditor.verify_dependencies({
            "ComponentA": ["core.runtime.valid"],
        }, trace_id)
        audit_result["dependencies"] = deps_result

        # Step 2: Load test
        load_result = generator.simulate_concurrent_dags(
            dag_count=20,
            dag_template={"nodes": 5, "edges": 8, "base_runtime_ms": 10},
            certification_trace_id=trace_id,
        )

        # Step 3: Security check
        security_isolation = validator.check_isolation_boundaries({
            "boundaries": {"runtime": {"isolated": True, "sandboxed": True}},
            "sandbox_active": True,
            "network_policy_enforced": True,
        }, trace_id)
        security_guards = validator.validate_capability_guards({
            "capabilities": {"exec": {"guard_active": True}},
            "enforcement_level": "strict",
        }, trace_id)
        security_trace = validator.audit_trace_integrity({
            "layers": {"i2_data": "dt_pipe"},
            "chain_order": ["i2_data"],
        }, trace_id)
        security_rollback = validator.verify_rollback_safety({
            "components": {"deployer": {"rollback_available": True, "data_preservation": True}},
        }, trace_id)

        # Step 4: Evaluate readiness
        evaluation = engine.evaluate_readiness(
            audit_results=audit_result,
            load_results=load_result,
            security_results={
                "isolation": security_isolation,
                "capability_guards": security_guards,
                "trace_integrity": security_trace,
                "rollback_safety": security_rollback,
            },
            readiness_guards={
                "audit_passed": audit_result["compliance_pct"] == 100,
                "load_stable": load_result["p99_latency_ms"] < 200,
                "security_passed": security_isolation["boundaries_secure"],
            },
            certification_trace_id=trace_id,
        )

        # Step 5: Compute stability
        oscillation = generator.detect_oscillation([50, 55, 48, 52], trace_id)
        stability = engine.compute_stability_score(load_result, oscillation, {}, trace_id)

        # Step 6: Generate certificate
        certificate = engine.generate_certificate(evaluation, stability, trace_id)

        # Step 7: Freeze baseline
        baseline = engine.freeze_baseline({
            "version": "4.5.0-prod-ready",
            "data_points": {
                "compliance_pct": audit_result["compliance_pct"],
                "p99_latency_ms": load_result["p99_latency_ms"],
                "stability_score": stability["stability_score"],
            },
        }, trace_id)

        # Assertions
        assert audit_result["compliance_pct"] == 100.0
        assert load_result["dags_failed"] == 0
        assert security_isolation["boundaries_secure"] is True
        assert evaluation["ready"] is True
        assert stability["overall_grade"] in ("A", "B")
        assert certificate["status"] in ("certified", "conditional")
        assert baseline["rollback_available"] is True

        # Verify event bus received certification events
        cert_events = bus.get_events("runtime.certification.certificate")
        assert len(cert_events) == 1
        assert cert_events[0].payload["status"] in ("certified", "conditional")

        baseline_events = bus.get_events("runtime.certification.baseline")
        assert len(baseline_events) == 1

    def test_certification_state_machine_full_pipeline(self) -> None:
        """Run the full C1-C5-C9 cycle through the state machine."""
        sm = CertificationStateMachine(strict_certification_mode=True)
        trace_id = "sm_pipeline_test"

        r1 = sm.transition(CertificationTransition.C1, certification_trace_id=trace_id)
        assert r1["to_state"] == "audit_start"

        r2 = sm.transition(CertificationTransition.C2, certification_trace_id=trace_id)
        assert r2["to_state"] == "load_test"

        r3 = sm.transition(CertificationTransition.C3, certification_trace_id=trace_id)
        assert r3["to_state"] == "security_check"

        r4 = sm.transition(CertificationTransition.C4, certification_trace_id=trace_id)
        assert r4["to_state"] == "compliance_verify"

        r5 = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100,
            "regressions": 0,
            "p99_latency_ms": 50,
            "oscillation_prevented": True,
            "trace_integrity": True,
        }, certification_trace_id=trace_id)
        assert r5["to_state"] == "certify"

        r9 = sm.transition(CertificationTransition.C9, certification_trace_id=trace_id)
        assert r9["to_state"] == "idle"

        assert len(sm.transition_history) == 6
